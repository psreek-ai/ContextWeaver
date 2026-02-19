"""
GitHub Webhook Handler.

Processes GitHub webhook events and feeds them into ContextWeaver.

Supported events:
  - pull_request (opened, synchronize, reopened) → conflict check + index
  - issues (opened) → index for future archaeology
  - push → index commit messages

The handler is designed to be called from the FastAPI webhook endpoint.
In production, use GitHub Apps for webhook delivery with HMAC signature
verification (already implemented here via `verify_signature`).
"""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timezone
from typing import Any

import structlog

from contextweaver.models import ArtifactKind, ConflictReport, RawArtifact

log = structlog.get_logger()


class GitHubWebhookHandler:
    """Translates raw GitHub webhook payloads into ContextWeaver artifacts."""

    def __init__(self, webhook_secret: str = "") -> None:
        self._secret = webhook_secret

    def verify_signature(self, payload_bytes: bytes, signature_header: str) -> bool:
        """Verify GitHub's HMAC-SHA256 webhook signature."""
        if not self._secret:
            return True  # No secret configured → skip verification (dev mode)
        if not signature_header or not signature_header.startswith("sha256="):
            return False
        expected = "sha256=" + hmac.new(
            self._secret.encode(),
            payload_bytes,
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, signature_header)

    def parse_pull_request(self, payload: dict[str, Any]) -> RawArtifact | None:
        """Parse a pull_request webhook payload into a RawArtifact."""
        pr = payload.get("pull_request", {})
        if not pr:
            return None

        action = payload.get("action", "")
        if action not in ("opened", "synchronize", "reopened", "edited"):
            return None

        body_parts = [pr.get("body") or ""]
        # Append review comments if available
        repo = payload.get("repository", {})

        return RawArtifact(
            kind=ArtifactKind.PR,
            source_id=str(pr.get("number", "")),
            url=pr.get("html_url", ""),
            title=pr.get("title", ""),
            body="\n\n".join(filter(None, body_parts)),
            author=pr.get("user", {}).get("login", "unknown"),
            created_at=self._parse_dt(pr.get("created_at")),
            metadata={
                "action": action,
                "repo": repo.get("full_name", ""),
                "base_branch": pr.get("base", {}).get("ref", ""),
                "labels": [l.get("name") for l in pr.get("labels", [])],
                "merged": pr.get("merged", False),
            },
        )

    def parse_issue(self, payload: dict[str, Any]) -> RawArtifact | None:
        """Parse an issues webhook payload into a RawArtifact."""
        issue = payload.get("issue", {})
        if not issue:
            return None
        if payload.get("action") != "opened":
            return None

        return RawArtifact(
            kind=ArtifactKind.ISSUE,
            source_id=str(issue.get("number", "")),
            url=issue.get("html_url", ""),
            title=issue.get("title", ""),
            body=issue.get("body") or "",
            author=issue.get("user", {}).get("login", "unknown"),
            created_at=self._parse_dt(issue.get("created_at")),
            metadata={
                "repo": payload.get("repository", {}).get("full_name", ""),
                "labels": [l.get("name") for l in issue.get("labels", [])],
            },
        )

    def parse_push(self, payload: dict[str, Any]) -> list[RawArtifact]:
        """Parse a push webhook payload into commit artifacts."""
        artifacts = []
        for commit in payload.get("commits", []):
            msg = commit.get("message", "")
            if not msg or len(msg) < 20:
                continue  # Skip trivial commits
            artifacts.append(
                RawArtifact(
                    kind=ArtifactKind.COMMIT,
                    source_id=commit.get("id", "")[:12],
                    url=commit.get("url", ""),
                    title=msg.split("\n")[0],
                    body=msg,
                    author=commit.get("author", {}).get("email", "unknown"),
                    created_at=self._parse_dt(commit.get("timestamp")),
                    metadata={
                        "repo": payload.get("repository", {}).get("full_name", ""),
                        "added": commit.get("added", [])[:10],
                        "modified": commit.get("modified", [])[:10],
                    },
                )
            )
        return artifacts

    @staticmethod
    def _parse_dt(dt_str: str | None) -> datetime:
        if not dt_str:
            return datetime.now(tz=timezone.utc)
        try:
            return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            return datetime.now(tz=timezone.utc)
