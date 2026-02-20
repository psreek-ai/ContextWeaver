"""
MiningAgent - Harvests raw project artifacts from all available sources.

Sources supported:
  - GitHub (PRs, Issues, Comments, Reviews, Commits)
  - Local git repositories (commit messages, diffs)
  - Markdown documentation files (ADRs, RFCs, wiki pages)

The agent is intentionally dumb about what it reads - it just collects
raw artifacts as faithfully as possible. Interpretation is left to the
ArchaeologyAgent.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import structlog
from github import Github, GithubException

from contextweaver.agents.base import BaseAgent
from contextweaver.config import settings
from contextweaver.models import ArtifactKind, MiningStatus, RawArtifact

log = structlog.get_logger()


class MiningAgent(BaseAgent):
    NAME = "mining_agent"

    def __init__(self) -> None:
        super().__init__()
        self._gh = Github(settings.github_token) if settings.github_token else None

    def describe(self) -> str:
        return (
            "Harvests raw project artifacts from GitHub, local git repos, "
            "and documentation files. Feeds the ArchaeologyAgent."
        )

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def mine_github_repo(
        self,
        repo_name: str,
        lookback_days: int | None = None,
    ) -> tuple[list[RawArtifact], MiningStatus]:
        """
        Mine all PR / Issue / Comment artifacts from a GitHub repository.

        Returns artifacts sorted oldest-first so the ArchaeologyAgent can
        process them in chronological order (important for temporal reasoning).
        """
        if not self._gh:
            raise RuntimeError(
                "GitHub token not configured. Set CW_GITHUB_TOKEN in your environment."
            )

        days = lookback_days or settings.mining_lookback_days
        since = datetime.now(tz=timezone.utc) - timedelta(days=days)
        status = MiningStatus(repo=repo_name)
        artifacts: list[RawArtifact] = []

        try:
            repo = self._gh.get_repo(repo_name)
            self.log.info("mining.start", repo=repo_name, since=since.isoformat())

            # --- Pull Requests ---
            for pr in repo.get_pulls(state="all", sort="created", direction="asc"):
                if pr.created_at.replace(tzinfo=timezone.utc) < since:
                    continue
                artifacts.append(
                    RawArtifact(
                        kind=ArtifactKind.PR,
                        source_id=str(pr.number),
                        url=pr.html_url,
                        title=pr.title or "",
                        body=pr.body or "",
                        author=pr.user.login if pr.user else "unknown",
                        created_at=pr.created_at.replace(tzinfo=timezone.utc),
                        metadata={
                            "merged": pr.merged,
                            "labels": [l.name for l in pr.labels],
                            "base_branch": pr.base.ref,
                        },
                    )
                )
                # PR reviews
                for review in pr.get_reviews():
                    if review.body:
                        artifacts.append(
                            RawArtifact(
                                kind=ArtifactKind.REVIEW,
                                source_id=f"pr{pr.number}_rev{review.id}",
                                url=pr.html_url,
                                title=f"Review on PR #{pr.number}: {pr.title}",
                                body=review.body,
                                author=review.user.login if review.user else "unknown",
                                created_at=review.submitted_at.replace(tzinfo=timezone.utc)
                                if review.submitted_at
                                else pr.created_at.replace(tzinfo=timezone.utc),
                                metadata={"state": review.state, "pr_number": pr.number},
                            )
                        )
                status.artifacts_processed += 1

            # --- Issues ---
            for issue in repo.get_issues(state="all", since=since):
                if issue.pull_request:
                    continue  # PRs already captured above
                artifacts.append(
                    RawArtifact(
                        kind=ArtifactKind.ISSUE,
                        source_id=str(issue.number),
                        url=issue.html_url,
                        title=issue.title or "",
                        body=issue.body or "",
                        author=issue.user.login if issue.user else "unknown",
                        created_at=issue.created_at.replace(tzinfo=timezone.utc),
                        metadata={"labels": [l.name for l in issue.labels]},
                    )
                )
                status.artifacts_processed += 1

        except GithubException as exc:
            self.log.error("mining.github_error", error=str(exc))
            status.errors += 1

        # Sort chronologically
        artifacts.sort(key=lambda a: a.created_at)
        status.completed = True
        status.completed_at = datetime.utcnow()
        self.log.info(
            "mining.complete",
            repo=repo_name,
            artifacts=len(artifacts),
            errors=status.errors,
        )
        return artifacts, status

    def mine_local_git(
        self,
        repo_path: str,
        max_commits: int = 500,
        since: str | None = None,
        until: str | None = None,
    ) -> list[RawArtifact]:
        """
        Extract commit messages from a local git repository.
        Works without a GitHub token - great for private/air-gapped repos.

        Args:
            repo_path: Path to the git repository
            max_commits: Maximum number of commits to process
            since: Start date (YYYY-MM-DD or ISO format)
            until: End date (YYYY-MM-DD or ISO format)
        """
        try:
            import git  # type: ignore

            repo = git.Repo(repo_path)
        except Exception as exc:
            self.log.error("mining.git_error", path=repo_path, error=str(exc))
            return []

        # Parse date filters if provided
        since_dt = None
        until_dt = None
        if since:
            try:
                since_dt = datetime.fromisoformat(since).replace(tzinfo=timezone.utc)
            except ValueError:
                self.log.warning("mining.invalid_since_date", since=since)
        if until:
            try:
                until_dt = datetime.fromisoformat(until).replace(tzinfo=timezone.utc)
            except ValueError:
                self.log.warning("mining.invalid_until_date", until=until)

        artifacts = []
        for commit in list(repo.iter_commits())[:max_commits]:
            commit_dt = datetime.fromtimestamp(commit.committed_date, tz=timezone.utc)

            # Filter by date range if specified
            if since_dt and commit_dt < since_dt:
                continue
            if until_dt and commit_dt > until_dt:
                continue

            artifacts.append(
                RawArtifact(
                    kind=ArtifactKind.COMMIT,
                    source_id=commit.hexsha[:12],
                    url="",
                    title=commit.summary,
                    body=commit.message,
                    author=commit.author.email,
                    created_at=commit_dt,
                    metadata={"files_changed": list(commit.stats.files.keys())[:20]},
                )
            )
        artifacts.sort(key=lambda a: a.created_at)
        return artifacts

    def mine_docs(self, docs_dir: str) -> list[RawArtifact]:
        """
        Scan a directory for Markdown files and treat each as a documentation artifact.
        Detects ADR files by their naming convention (e.g. 0001-use-postgres.md).
        """
        artifacts = []
        for path in Path(docs_dir).rglob("*.md"):
            try:
                content = path.read_text(encoding="utf-8", errors="replace")
                # Detect ADR naming patterns: NNN-title.md
                name = path.stem
                kind = (
                    ArtifactKind.ADR
                    if len(name) > 3 and name[:4].isdigit()
                    else ArtifactKind.DOC
                )
                mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
                artifacts.append(
                    RawArtifact(
                        kind=kind,
                        source_id=str(path.relative_to(docs_dir)),
                        url=str(path.absolute()),
                        title=path.name,
                        body=content[:8000],  # Limit to avoid context overflow
                        author="unknown",
                        created_at=mtime,
                        metadata={"file_path": str(path.absolute())},
                    )
                )
            except OSError as exc:
                self.log.warning("mining.doc_read_error", path=str(path), error=str(exc))

        artifacts.sort(key=lambda a: a.created_at)
        return artifacts
