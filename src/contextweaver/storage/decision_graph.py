"""
Decision Knowledge Graph - the temporal topology of all project decisions.

Uses NetworkX directed graph where:
  - Nodes  = Decisions
  - Edges  = Relationships (supersedes, depends_on, contradicts, related_to)

This graph makes it possible to:
  - Trace the full history of any architectural choice
  - Detect when a new decision creates contradictions
  - Find the "decision ancestry" of any current code path
  - Identify decision clusters (related architectural areas)
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any

import networkx as nx
import structlog

from contextweaver.models import Decision

log = structlog.get_logger()

EDGE_TYPES = {
    "supersedes",       # This decision replaces an older one
    "depends_on",       # This decision requires another to hold
    "contradicts",      # Detected tension between decisions
    "related_to",       # Semantic sibling (same domain, complementary)
    "motivated_by",     # This decision was triggered by a problem in another
}


class DecisionGraph:
    """
    In-memory directed graph with optional JSON persistence.

    The graph is small enough to live in memory for even large projects
    (50k decisions ≈ ~100MB RAM). Graph analytics like betweenness centrality
    surface the most architecturally critical decisions.
    """

    def __init__(self, persist_path: str) -> None:
        self._path = persist_path
        os.makedirs(os.path.dirname(persist_path), exist_ok=True)
        self._g: nx.DiGraph = nx.DiGraph()
        if os.path.exists(persist_path):
            self._load()
        log.info(
            "decision_graph.initialized",
            nodes=self._g.number_of_nodes(),
            edges=self._g.number_of_edges(),
        )

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def add_decision(self, decision: Decision) -> None:
        self._g.add_node(
            decision.id,
            title=decision.title,
            summary=decision.summary,
            rationale=decision.rationale,
            confidence=decision.confidence.value,
            made_at=decision.made_at.isoformat(),
            tags=decision.tags,
            authors=decision.authors,
            debt_score=decision.debt_score,
            source_artifacts=decision.source_artifacts,
        )
        # Wire supersession edge automatically
        if decision.superseded_by:
            self.add_edge(decision.id, decision.superseded_by, "supersedes")

    def add_edge(
        self,
        from_id: str,
        to_id: str,
        relationship: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if relationship not in EDGE_TYPES:
            raise ValueError(f"Unknown relationship type: {relationship}")
        self._g.add_edge(
            from_id,
            to_id,
            relationship=relationship,
            metadata=metadata or {},
            added_at=datetime.utcnow().isoformat(),
        )

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get_decision(self, decision_id: str) -> dict[str, Any] | None:
        if decision_id not in self._g:
            return None
        node = dict(self._g.nodes[decision_id])
        node["id"] = decision_id
        return node

    def get_ancestry(self, decision_id: str, depth: int = 5) -> list[dict[str, Any]]:
        """
        Walk backwards through 'depends_on' and 'supersedes' edges to surface
        the decision lineage - the chain of choices that led to this one.
        """
        ancestors: list[dict[str, Any]] = []
        visited: set[str] = set()

        def _walk(nid: str, remaining: int) -> None:
            if remaining == 0 or nid in visited:
                return
            visited.add(nid)
            for pred in self._g.predecessors(nid):
                edge_data = self._g.edges[pred, nid]
                if edge_data.get("relationship") in ("depends_on", "supersedes"):
                    node_data = self.get_decision(pred)
                    if node_data:
                        ancestors.append(node_data)
                    _walk(pred, remaining - 1)

        _walk(decision_id, depth)
        return ancestors

    def get_contradictions(self, decision_id: str) -> list[dict[str, Any]]:
        """Return all decisions that have a 'contradicts' edge with this one."""
        result = []
        for neighbor in list(self._g.predecessors(decision_id)) + list(
            self._g.successors(decision_id)
        ):
            for edge_data in [
                self._g.edges.get((decision_id, neighbor)),
                self._g.edges.get((neighbor, decision_id)),
            ]:
                if edge_data and edge_data.get("relationship") == "contradicts":
                    node = self.get_decision(neighbor)
                    if node:
                        result.append(node)
        return result

    def most_critical_decisions(self, top_n: int = 10) -> list[dict[str, Any]]:
        """
        Use betweenness centrality to find the decisions that most influence
        the rest of the decision graph - the architectural load-bearing walls.
        """
        if self._g.number_of_nodes() < 3:
            return [
                self.get_decision(n)
                for n in list(self._g.nodes)[:top_n]
                if self.get_decision(n)
            ]

        centrality = nx.betweenness_centrality(self._g)
        top = sorted(centrality.items(), key=lambda x: x[1], reverse=True)[:top_n]
        result = []
        for node_id, _ in top:
            node = self.get_decision(node_id)
            if node:
                result.append(node)
        return result

    def decisions_in_debt(self, threshold: float = 0.5) -> list[dict[str, Any]]:
        """Return decisions whose debt_score exceeds the threshold."""
        return [
            {**dict(self._g.nodes[n]), "id": n}
            for n in self._g.nodes
            if self._g.nodes[n].get("debt_score", 0) >= threshold
        ]

    def node_count(self) -> int:
        return self._g.number_of_nodes()

    def edge_count(self) -> int:
        return self._g.number_of_edges()

    def to_dict(self) -> dict[str, Any]:
        """Export graph as node-link JSON for API/visualization consumption."""
        return nx.node_link_data(self._g)  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self) -> None:
        data = nx.node_link_data(self._g)
        with open(self._path, "w") as f:
            json.dump(data, f, default=str)
        log.info("decision_graph.saved", path=self._path, nodes=self._g.number_of_nodes())

    def _load(self) -> None:
        with open(self._path) as f:
            data = json.load(f)
        self._g = nx.node_link_graph(data, directed=True)
        log.info("decision_graph.loaded", path=self._path, nodes=self._g.number_of_nodes())
