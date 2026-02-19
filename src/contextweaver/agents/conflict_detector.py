"""
ConflictDetectorAgent - Catches decision debt before it becomes technical debt.

This agent answers the question: "Does this new PR/commit contradict any
decisions we've made in the past?"

It works in two stages:
  1. SEMANTIC RETRIEVAL: Find historical decisions that are semantically
     related to the new artifact (via vector similarity search)
  2. REASONING: Ask Claude to determine if the artifact genuinely
     contradicts those decisions or is merely related

This two-stage approach avoids both false positives (generic similarity)
and false negatives (paraphrased contradictions that naive text-matching misses).

This is unprecedented in the software tooling ecosystem - no CI/CD tool,
code review bot, or static analysis tool does historical decision conflict detection.
"""

from __future__ import annotations

from typing import Any

import structlog

from contextweaver.agents.base import BaseAgent
from contextweaver.config import settings
from contextweaver.models import ConflictReport, RawArtifact
from contextweaver.storage.decision_graph import DecisionGraph
from contextweaver.storage.vector_store import VectorStore

log = structlog.get_logger()

_CONFLICT_SYSTEM = """You are an expert software architect reviewing a new pull request or commit
against the historical architectural decisions of the project.

Your task is to determine if the new work GENUINELY CONTRADICTS any of the provided
historical decisions. A genuine contradiction means:
- The new work does something that was explicitly or implicitly decided against
- The new work ignores a constraint that was established for good reason
- The new work introduces an approach that was considered and rejected

NOT a contradiction:
- The new work merely touches the same area
- The new work builds on top of an existing decision
- The new work supersedes an outdated decision with a valid new approach

For each genuine contradiction found, provide:
- which_decision: the decision title that is being contradicted
- explanation: a clear, developer-friendly explanation of the conflict
- severity: low | medium | high | critical
- suggested_action: what the developer should do (update the decision record, refactor, discuss)

Return JSON: {"conflicts": [{"which_decision": "...", "explanation": "...", "severity": "...",
"suggested_action": "..."}]}
If no genuine conflicts, return: {"conflicts": []}"""


class ConflictDetectorAgent(BaseAgent):
    NAME = "conflict_detector"

    def __init__(self, vector_store: VectorStore, decision_graph: DecisionGraph) -> None:
        super().__init__()
        self._vs = vector_store
        self._dg = decision_graph
        self._threshold = settings.conflict_threshold

    def describe(self) -> str:
        return (
            "Detects when new PRs/commits contradict historical decisions. "
            "Prevents decision debt at the point of code review."
        )

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def analyze_artifact(self, artifact: RawArtifact) -> list[ConflictReport]:
        """
        Analyze a new artifact for conflicts with historical decisions.
        Typically called from a GitHub webhook when a PR is opened.
        """
        if self._vs.count() == 0:
            self.log.info("conflict.skip", reason="no_decisions_indexed_yet")
            return []

        # Stage 1: Semantic retrieval
        query = f"{artifact.title}\n{artifact.body[:2000]}"
        candidates = self._vs.search(query, n_results=8)

        # Filter to semantically close candidates only
        close_candidates = [c for c in candidates if c["distance"] <= (1 - self._threshold)]

        if not close_candidates:
            return []

        # Stage 2: Reasoning over candidates
        return self._reason_about_conflicts(artifact, close_candidates)

    def analyze_text(self, text: str, label: str = "query") -> list[ConflictReport]:
        """
        Analyze free-form text (e.g. a proposed approach) for conflicts.
        Useful for 'conflict check' before writing any code.
        """
        from contextweaver.models import ArtifactKind
        from datetime import datetime

        pseudo_artifact = RawArtifact(
            kind=ArtifactKind.PR,
            source_id=label,
            title=label,
            body=text,
            author="analyst",
            created_at=datetime.utcnow(),
        )
        return self.analyze_artifact(pseudo_artifact)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _reason_about_conflicts(
        self,
        artifact: RawArtifact,
        candidates: list[dict[str, Any]],
    ) -> list[ConflictReport]:
        decisions_context = "\n\n".join(
            f"[{i+1}] DECISION: {c['metadata'].get('title', 'unknown')}\n"
            f"MADE: {c['metadata'].get('made_at', 'unknown')}\n"
            f"CONTENT: {c['document'][:800]}"
            for i, c in enumerate(candidates)
        )

        new_work = (
            f"NEW WORK TITLE: {artifact.title}\n"
            f"NEW WORK CONTENT:\n{artifact.body[:3000]}"
        )

        response = self._reason(
            system=_CONFLICT_SYSTEM,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"HISTORICAL DECISIONS:\n{decisions_context}\n\n"
                        f"---\n\n{new_work}\n\n"
                        "Does this new work contradict any of the historical decisions above?"
                    ),
                }
            ],
            max_tokens=2048,
        )

        try:
            data = self._extract_json(response)
        except Exception as exc:
            self.log.warning("conflict.parse_error", error=str(exc))
            return []

        # Map Claude's output back to ConflictReport objects
        reports = []
        for conflict in data.get("conflicts", []):
            # Find the matching candidate's decision ID
            conflicting_id = self._find_decision_id(
                conflict.get("which_decision", ""), candidates
            )
            reports.append(
                ConflictReport(
                    artifact_id=artifact.source_id,
                    conflicting_decision_id=conflicting_id,
                    similarity_score=0.85,  # Qualitative - Claude confirmed it
                    explanation=conflict.get("explanation", ""),
                    severity=conflict.get("severity", "medium"),
                    suggested_action=conflict.get("suggested_action", ""),
                )
            )
            # Mark contradicts edge in the decision graph
            if conflicting_id:
                # We'd normally add the new artifact's decision ID here;
                # for now we log the edge symbolically
                self.log.warning(
                    "conflict.detected",
                    artifact=artifact.source_id,
                    decision=conflicting_id,
                    severity=conflict.get("severity"),
                )

        return reports

    @staticmethod
    def _find_decision_id(title: str, candidates: list[dict[str, Any]]) -> str:
        title_lower = title.lower()
        for c in candidates:
            candidate_title = c["metadata"].get("title", "").lower()
            if candidate_title and title_lower and (
                title_lower in candidate_title or candidate_title in title_lower
            ):
                return c["metadata"].get("decision_id", c["id"])
        # Fallback: return first candidate's ID
        if candidates:
            return candidates[0]["metadata"].get("decision_id", candidates[0]["id"])
        return "unknown"
