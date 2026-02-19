"""
BriefingAgent - Generates Living Context Briefings.

When a new developer joins a project, they face months of context-gathering.
When a senior dev starts a major new feature, they risk repeating past mistakes.
When an incident happens, responders need instant context.

The BriefingAgent generates a "living context briefing" - a synthesized,
narrative explanation of the relevant decision history for any query topic.

Think of it as having a conversation with the collective institutional memory
of the project. No documentation tool does this today.
"""

from __future__ import annotations

from datetime import datetime

import structlog

from contextweaver.agents.base import BaseAgent
from contextweaver.models import ContextBriefing, Decision
from contextweaver.storage.decision_graph import DecisionGraph
from contextweaver.storage.vector_store import VectorStore

log = structlog.get_logger()

_BRIEFING_SYSTEM = """You are a senior software architect and historian of this project.
Your role is to onboard new team members and brief experienced developers on the
historical context relevant to their current work.

You have access to a curated list of historical decisions that are relevant to the
query topic. Your job is to synthesize them into a coherent briefing that:

1. Tells the story of how we got here (chronologically, if relevant)
2. Explains the KEY decisions and WHY they were made (not just what)
3. Highlights the critical constraints that must not be violated
4. Flags decision debt - old decisions that may need revisiting
5. Suggests 3-5 questions the developer should investigate before proceeding

Write in a clear, direct style as if briefing a smart colleague.
Reference specific decisions by name. Be honest about uncertainty.

Return a JSON object:
{
  "narrative": "...",
  "critical_constraints": ["..."],
  "active_debt": ["..."],
  "suggested_questions": ["..."]
}"""


class BriefingAgent(BaseAgent):
    NAME = "briefing_agent"

    def __init__(self, vector_store: VectorStore, decision_graph: DecisionGraph) -> None:
        super().__init__()
        self._vs = vector_store
        self._dg = decision_graph

    def describe(self) -> str:
        return (
            "Generates living context briefings for developers. Synthesizes decision "
            "history into narrative explanations of why the project is the way it is."
        )

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def generate_briefing(
        self,
        topic: str,
        subject: str = "developer",
        scope: str = "project",
        n_decisions: int = 10,
    ) -> ContextBriefing:
        """
        Generate a context briefing for a given topic/query.

        Args:
            topic: What the briefing is about (e.g. "authentication system",
                   "why do we use Postgres", "API versioning")
            subject: Who this briefing is for (e.g. "new backend engineer")
            scope: Scope of the briefing (e.g. "auth module", "whole project")
            n_decisions: Max number of historical decisions to include
        """
        self.log.info("briefing.start", topic=topic, subject=subject)

        # Retrieve relevant decisions via semantic search
        search_results = self._vs.search(topic, n_results=n_decisions)
        relevant_decisions = []
        for result in search_results:
            decision_id = result["metadata"].get("decision_id")
            if decision_id:
                node = self._dg.get_decision(decision_id)
                if node:
                    try:
                        decision = self._node_to_decision(decision_id, node)
                        relevant_decisions.append(decision)
                    except Exception:
                        pass

        # Add graph context: most critical decisions always included
        critical = self._dg.most_critical_decisions(top_n=3)
        for crit in critical:
            crit_id = crit.get("id")
            if crit_id and not any(d.id == crit_id for d in relevant_decisions):
                try:
                    decision = self._node_to_decision(crit_id, crit)
                    relevant_decisions.append(decision)
                except Exception:
                    pass

        # Generate narrative via Claude
        narrative_data = self._generate_narrative(topic, subject, scope, relevant_decisions)

        return ContextBriefing(
            subject=subject,
            scope=scope,
            generated_at=datetime.utcnow(),
            key_decisions=relevant_decisions[:n_decisions],
            critical_constraints=narrative_data.get("critical_constraints", []),
            active_debt=narrative_data.get("active_debt", []),
            narrative=narrative_data.get("narrative", ""),
            suggested_questions=narrative_data.get("suggested_questions", []),
        )

    def answer_why(self, question: str) -> str:
        """
        Direct "why?" question answering backed by the decision archive.
        Returns a flowing prose answer that cites specific decisions.
        """
        results = self._vs.search(question, n_results=6)
        if not results:
            return (
                "I don't have enough historical context to answer that question yet. "
                "Run `contextweaver mine` to index more project history."
            )

        decision_context = "\n\n".join(
            f"Decision: {r['metadata'].get('title', '?')}\n"
            f"Made: {r['metadata'].get('made_at', '?')}\n"
            f"Context: {r['document'][:600]}"
            for r in results
        )

        response = self._reason(
            system=(
                "You are the institutional memory of a software project. "
                "Answer the developer's question using the historical decisions provided. "
                "Be direct, specific, and cite which decision explains each point. "
                "If uncertain, say so. Write in flowing prose, not bullet points."
            ),
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Question: {question}\n\n"
                        f"Historical decisions to draw from:\n{decision_context}"
                    ),
                }
            ],
            max_tokens=1024,
        )
        return self._extract_text(response)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _generate_narrative(
        self,
        topic: str,
        subject: str,
        scope: str,
        decisions: list[Decision],
    ) -> dict[str, object]:
        if not decisions:
            return {
                "narrative": (
                    f"No historical decisions found for '{topic}'. "
                    "Run `contextweaver mine` to build the decision archive."
                ),
                "critical_constraints": [],
                "active_debt": [],
                "suggested_questions": [
                    "Why is there no documented decision history for this area?",
                    "Was this area built without explicit design decisions?",
                    "Should we document the current state as a baseline decision?",
                ],
            }

        decisions_context = "\n\n".join(
            f"[{i+1}] {d.title} ({d.made_at.strftime('%Y-%m-%d')}, "
            f"confidence: {d.confidence.value}, debt: {d.debt_score:.1f})\n"
            f"Summary: {d.summary}\n"
            f"Rationale: {d.rationale[:400]}\n"
            f"Trade-offs: {'; '.join(d.trade_offs[:3])}"
            for i, d in enumerate(decisions)
        )

        response = self._reason(
            system=_BRIEFING_SYSTEM,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"BRIEFING REQUEST\n"
                        f"Topic: {topic}\n"
                        f"For: {subject}\n"
                        f"Scope: {scope}\n\n"
                        f"RELEVANT HISTORICAL DECISIONS:\n{decisions_context}"
                    ),
                }
            ],
            max_tokens=2048,
        )

        try:
            return self._extract_json(response)  # type: ignore[return-value]
        except Exception as exc:
            self.log.warning("briefing.parse_error", error=str(exc))
            return {
                "narrative": self._extract_text(response),
                "critical_constraints": [],
                "active_debt": [],
                "suggested_questions": [],
            }

    @staticmethod
    def _node_to_decision(decision_id: str, node: dict) -> Decision:
        from contextweaver.models import DecisionConfidence
        from datetime import timezone

        made_at = node.get("made_at", datetime.utcnow().isoformat())
        if isinstance(made_at, str):
            try:
                made_at = datetime.fromisoformat(made_at)
            except ValueError:
                made_at = datetime.utcnow()

        return Decision(
            id=decision_id,
            title=node.get("title", "Unknown Decision"),
            summary=node.get("summary", ""),
            rationale=node.get("rationale", ""),
            alternatives_considered=[],
            trade_offs=[],
            confidence=DecisionConfidence(node.get("confidence", "medium")),
            authors=node.get("authors", []),
            made_at=made_at,
            source_artifacts=node.get("source_artifacts", []),
            tags=node.get("tags", []),
            debt_score=float(node.get("debt_score", 0.0)),
        )
