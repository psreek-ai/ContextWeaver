"""
Orchestrator - Coordinates the ContextWeaver Agent Swarm.

The Orchestrator is the single entry point for all agent operations.
It instantiates and wires together:
  - MiningAgent
  - ArchaeologyAgent
  - ConflictDetectorAgent
  - BriefingAgent

It also manages the shared storage layer (VectorStore + DecisionGraph)
and provides the high-level API used by both the REST server and CLI.

Design principle: agents never talk to each other directly. All state
flows through the shared storage layer, which makes the system:
  - Parallelizable (agents can run concurrently)
  - Testable (each agent is independently testable)
  - Auditable (all decisions are stored, not in agent memory)
"""

from __future__ import annotations

import structlog

from contextweaver.agents.archaeology_agent import ArchaeologyAgent
from contextweaver.agents.briefing_agent import BriefingAgent
from contextweaver.agents.conflict_detector import ConflictDetectorAgent
from contextweaver.agents.mining_agent import MiningAgent
from contextweaver.config import settings
from contextweaver.models import (
    ContextBriefing,
    ConflictReport,
    Decision,
    MiningStatus,
    RawArtifact,
)
from contextweaver.storage.decision_graph import DecisionGraph
from contextweaver.storage.vector_store import VectorStore

log = structlog.get_logger()


class Orchestrator:
    """
    High-level coordinator for the ContextWeaver agent swarm.

    Usage:
        orc = Orchestrator()
        orc.mine_and_index("owner/repo")
        briefing = orc.brief("why did we choose PostgreSQL?")
        conflicts = orc.check_conflicts(pr_artifact)
    """

    def __init__(self) -> None:
        # Shared storage - the "nervous system" of the agent swarm
        self._vs = VectorStore(persist_dir=settings.chroma_persist_dir)
        self._dg = DecisionGraph(persist_path=settings.graph_persist_path)

        # Specialized agents
        self._miner = MiningAgent()
        self._archaeologist = ArchaeologyAgent(self._vs, self._dg)
        self._conflict_detector = ConflictDetectorAgent(self._vs, self._dg)
        self._briefer = BriefingAgent(self._vs, self._dg)

        log.info(
            "orchestrator.initialized",
            decisions_indexed=self._vs.count(),
            decision_graph_nodes=self._dg.node_count(),
        )

    # ------------------------------------------------------------------
    # Mining & Indexing
    # ------------------------------------------------------------------

    def mine_github(
        self,
        repo_name: str | None = None,
        lookback_days: int | None = None,
    ) -> tuple[list[Decision], MiningStatus]:
        """
        Mine a GitHub repository and index all extracted decisions.
        This is typically the first command a user runs.
        """
        repo = repo_name or settings.github_repo
        if not repo:
            raise ValueError(
                "No repo specified. Pass repo_name or set CW_GITHUB_REPO in environment."
            )

        log.info("orchestrator.mine_github.start", repo=repo)
        artifacts, status = self._miner.mine_github_repo(repo, lookback_days)
        decisions = self._archaeologist.process_batch(artifacts)
        status.decisions_extracted = len(decisions)

        # Persist the updated graph
        self._dg.save()

        log.info(
            "orchestrator.mine_github.complete",
            repo=repo,
            artifacts=len(artifacts),
            decisions=len(decisions),
        )
        return decisions, status

    def mine_local(
        self,
        repo_path: str,
        docs_dir: str | None = None,
    ) -> list[Decision]:
        """
        Mine a local git repository (and optional docs dir) and index decisions.
        Works without any GitHub token.
        """
        artifacts: list[RawArtifact] = self._miner.mine_local_git(repo_path)
        if docs_dir:
            artifacts.extend(self._miner.mine_docs(docs_dir))
        artifacts.sort(key=lambda a: a.created_at)

        decisions = self._archaeologist.process_batch(artifacts)
        self._dg.save()
        return decisions

    def index_artifact(self, artifact: RawArtifact) -> list[Decision]:
        """Index a single artifact (e.g. from a webhook)."""
        decisions = self._archaeologist.process_artifact(artifact)
        self._dg.save()
        return decisions

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def brief(
        self,
        topic: str,
        subject: str = "developer",
        scope: str = "project",
    ) -> ContextBriefing:
        """Generate a context briefing for the given topic."""
        return self._briefer.generate_briefing(topic, subject=subject, scope=scope)

    def why(self, question: str) -> str:
        """Answer a 'why?' question about the project's decisions."""
        return self._briefer.answer_why(question)

    def check_conflicts(self, artifact: RawArtifact) -> list[ConflictReport]:
        """Check an artifact for conflicts with historical decisions."""
        return self._conflict_detector.analyze_artifact(artifact)

    def check_text_conflicts(self, text: str, label: str = "analysis") -> list[ConflictReport]:
        """Check free-form text for conflicts."""
        return self._conflict_detector.analyze_text(text, label)

    # ------------------------------------------------------------------
    # Analytics
    # ------------------------------------------------------------------

    def stats(self) -> dict[str, object]:
        return {
            "decisions_indexed": self._vs.count(),
            "graph_nodes": self._dg.node_count(),
            "graph_edges": self._dg.edge_count(),
            "critical_decisions": self._dg.most_critical_decisions(top_n=5),
            "high_debt_decisions": self._dg.decisions_in_debt(threshold=0.6),
            "agent_tokens": {
                "miner": self._miner.token_stats,
                "archaeologist": self._archaeologist.token_stats,
                "conflict_detector": self._conflict_detector.token_stats,
                "briefer": self._briefer.token_stats,
            },
        }

    def graph_export(self) -> dict[str, object]:
        """Export the full decision graph for visualization."""
        return self._dg.to_dict()

    @property
    def vector_store(self) -> VectorStore:
        return self._vs

    @property
    def decision_graph(self) -> DecisionGraph:
        return self._dg
