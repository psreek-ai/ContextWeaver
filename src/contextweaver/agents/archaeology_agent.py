"""
ArchaeologyAgent - The Core Innovation of ContextWeaver.

This agent is the heart of Decision Archaeology. It reads raw project
artifacts and uses Claude to reconstruct:

  1. WHAT decision was made
  2. WHY it was made (the rationale, often never written down)
  3. WHAT alternatives were considered (explicit or implicit)
  4. WHAT trade-offs were accepted
  5. HOW confident we are in this reconstruction
  6. HOW much "decision debt" has accumulated

The ArchaeologyAgent processes artifacts in chronological order so it can
understand the temporal context - a decision made in 2021 means something
different from the same decision made in 2024.

This is the first AI system to do this systematically and at scale.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

import structlog

from contextweaver.agents.base import BaseAgent
from contextweaver.models import Decision, DecisionConfidence, RawArtifact
from contextweaver.storage.decision_graph import DecisionGraph
from contextweaver.storage.vector_store import VectorStore

log = structlog.get_logger()

_ARCHAEOLOGY_SYSTEM = """You are a Decision Archaeologist - an expert in reconstructing the reasoning behind
software engineering decisions from incomplete, implicit artifacts like commit messages,
PR descriptions, code reviews, and issue discussions.

Your job is to analyze project artifacts and extract explicit or implicit DECISIONS that were made.
A decision is any meaningful choice about architecture, technology, process, or design that has
lasting impact on the project.

For each decision you find, reconstruct:
- A clear, concise title (noun phrase, max 10 words)
- A one-paragraph summary of what was decided
- The full rationale: WHY this choice was made (even if not explicitly stated - infer from context)
- Alternatives that were considered (even if only implied)
- Trade-offs that were accepted
- Your confidence level: high (explicitly documented), medium (strongly implied), low (inferred)
- Relevant semantic tags from: [architecture, security, performance, scalability, reliability,
  maintainability, developer-experience, cost, compliance, data, api, database, frontend, backend,
  infrastructure, testing, deployment, monitoring, ai/ml, process, tooling]
- Decision debt score 0.0-1.0: how outdated/problematic is this decision today?
  (0 = still healthy, 0.5 = should be revisited, 1.0 = critically outdated)

Rules:
- Only extract REAL decisions, not observations, bugs, or feature requests
- If an artifact contains no decisions, return an empty list
- Prefer fewer, higher-quality decisions over many low-quality ones
- The rationale is the most important field - this is what humans lose over time

Return a JSON object with this exact schema:
{
  "decisions": [
    {
      "title": "string",
      "summary": "string",
      "rationale": "string",
      "alternatives_considered": ["string"],
      "trade_offs": ["string"],
      "confidence": "high|medium|low",
      "tags": ["string"],
      "debt_score": 0.0
    }
  ]
}"""


class ArchaeologyAgent(BaseAgent):
    NAME = "archaeology_agent"

    def __init__(self, vector_store: VectorStore, decision_graph: DecisionGraph) -> None:
        super().__init__()
        self._vs = vector_store
        self._dg = decision_graph

    def describe(self) -> str:
        return (
            "Extracts and reconstructs Decisions from raw project artifacts using "
            "Claude claude-opus-4-6. The core innovation: automated decision archaeology."
        )

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def process_artifact(self, artifact: RawArtifact) -> list[Decision]:
        """
        Extract decisions from a single artifact.
        Returns the list of Decision objects extracted and stored.
        """
        if not artifact.body.strip() and not artifact.title.strip():
            return []

        decisions = self._extract_decisions(artifact)
        for decision in decisions:
            self._dg.add_decision(decision)
            self._vs.upsert(decision)

        if decisions:
            self.log.info(
                "archaeology.extracted",
                artifact_id=artifact.source_id,
                artifact_kind=artifact.kind,
                decisions_found=len(decisions),
            )
        return decisions

    def process_batch(self, artifacts: list[RawArtifact]) -> list[Decision]:
        """
        Process a batch of artifacts chronologically.
        Returns all extracted decisions.
        """
        all_decisions: list[Decision] = []
        for i, artifact in enumerate(artifacts):
            try:
                decisions = self.process_artifact(artifact)
                all_decisions.extend(decisions)
            except Exception as exc:
                self.log.error(
                    "archaeology.batch_error",
                    artifact_id=artifact.source_id,
                    error=str(exc),
                    progress=f"{i+1}/{len(artifacts)}",
                )
        return all_decisions

    def score_decision_debt(self, decision: Decision, current_context: str) -> float:
        """
        Ask Claude to re-evaluate a historical decision's debt score given the
        current state of the project. Returns a debt score 0.0-1.0.
        """
        prompt = f"""Given this historical software decision:

TITLE: {decision.title}
MADE: {decision.made_at.strftime('%Y-%m-%d')}
RATIONALE: {decision.rationale}
TRADE-OFFS: {'; '.join(decision.trade_offs)}

And this current project context:
{current_context}

Rate the "decision debt" of this historical decision on a scale from 0.0 to 1.0:
- 0.0 = Still valid, no debt
- 0.3 = Some drift, worth revisiting within 6 months
- 0.6 = Significant debt, revisit soon
- 1.0 = Critically outdated, blocking progress

Return ONLY a JSON object: {{"debt_score": 0.0, "reason": "string"}}"""

        response = self._reason(
            system="You are a software architect assessing technical decision debt.",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=256,
        )
        try:
            result = self._extract_json(response)
            return float(result.get("debt_score", decision.debt_score))
        except Exception:
            return decision.debt_score

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _extract_decisions(self, artifact: RawArtifact) -> list[Decision]:
        artifact_text = self._format_artifact(artifact)

        response = self._reason(
            system=_ARCHAEOLOGY_SYSTEM,
            messages=[
                {
                    "role": "user",
                    "content": f"Analyze this project artifact and extract any decisions:\n\n{artifact_text}",
                }
            ],
            max_tokens=4096,
        )

        try:
            data = self._extract_json(response)
        except (json.JSONDecodeError, KeyError, ValueError) as exc:
            self.log.warning(
                "archaeology.parse_error",
                artifact_id=artifact.source_id,
                error=str(exc),
            )
            return []

        decisions = []
        for raw in data.get("decisions", []):
            try:
                decision_id = hashlib.sha256(
                    f"{raw.get('title', '')}:{artifact.created_at.isoformat()}".encode()
                ).hexdigest()[:20]

                decision = Decision(
                    id=decision_id,
                    title=raw["title"],
                    summary=raw["summary"],
                    rationale=raw["rationale"],
                    alternatives_considered=raw.get("alternatives_considered", []),
                    trade_offs=raw.get("trade_offs", []),
                    confidence=DecisionConfidence(raw.get("confidence", "medium")),
                    authors=[artifact.author] if artifact.author else [],
                    made_at=artifact.created_at,
                    source_artifacts=[artifact.url or artifact.source_id],
                    tags=raw.get("tags", []),
                    debt_score=float(raw.get("debt_score", 0.0)),
                )
                decisions.append(decision)
            except (KeyError, ValueError) as exc:
                self.log.warning("archaeology.decision_parse_error", error=str(exc), raw=raw)

        return decisions

    @staticmethod
    def _format_artifact(artifact: RawArtifact) -> str:
        lines = [
            f"TYPE: {artifact.kind.value.upper()}",
            f"DATE: {artifact.created_at.strftime('%Y-%m-%d')}",
            f"AUTHOR: {artifact.author}",
            f"TITLE: {artifact.title}",
            "",
            "CONTENT:",
            artifact.body[:6000],  # Respect context limits
        ]
        if artifact.metadata:
            meta_str = "; ".join(f"{k}={v}" for k, v in artifact.metadata.items() if v)
            if meta_str:
                lines.insert(4, f"METADATA: {meta_str}")
        return "\n".join(lines)
