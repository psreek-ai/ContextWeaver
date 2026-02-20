"""Tests for the DecisionGraph storage layer."""

import os
import tempfile
from datetime import datetime, timezone

import pytest

from contextweaver.models import Decision, DecisionConfidence
from contextweaver.storage.decision_graph import DecisionGraph


@pytest.fixture
def graph(tmp_path):
    return DecisionGraph(persist_path=str(tmp_path / "graph.json"))


def _make_decision(id: str, title: str, debt: float = 0.0) -> Decision:
    return Decision(
        id=id,
        title=title,
        summary=f"Summary of {title}",
        rationale=f"Rationale for {title}",
        made_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        debt_score=debt,
    )


class TestDecisionGraph:
    def test_add_and_get_decision(self, graph):
        d = _make_decision("abc", "Use PostgreSQL")
        graph.add_decision(d)
        node = graph.get_decision("abc")
        assert node is not None
        assert node["title"] == "Use PostgreSQL"

    def test_get_nonexistent_decision(self, graph):
        assert graph.get_decision("nonexistent") is None

    def test_add_edge(self, graph):
        d1 = _make_decision("id1", "Decision A")
        d2 = _make_decision("id2", "Decision B")
        graph.add_decision(d1)
        graph.add_decision(d2)
        graph.add_edge("id1", "id2", "depends_on")
        assert graph.edge_count() == 1

    def test_invalid_edge_type(self, graph):
        d1 = _make_decision("id1", "A")
        graph.add_decision(d1)
        with pytest.raises(ValueError):
            graph.add_edge("id1", "id1", "invalid_type")

    def test_decisions_in_debt(self, graph):
        graph.add_decision(_make_decision("low", "Low debt", debt=0.1))
        graph.add_decision(_make_decision("high", "High debt", debt=0.8))
        debts = graph.decisions_in_debt(threshold=0.5)
        assert len(debts) == 1
        assert debts[0]["id"] == "high"

    def test_node_count(self, graph):
        assert graph.node_count() == 0
        graph.add_decision(_make_decision("x", "X"))
        assert graph.node_count() == 1

    def test_save_and_reload(self, tmp_path):
        path = str(tmp_path / "graph.json")
        g1 = DecisionGraph(persist_path=path)
        g1.add_decision(_make_decision("saved", "Saved Decision"))
        g1.save()

        g2 = DecisionGraph(persist_path=path)
        node = g2.get_decision("saved")
        assert node is not None
        assert node["title"] == "Saved Decision"

    def test_to_dict(self, graph):
        graph.add_decision(_make_decision("x", "X"))
        data = graph.to_dict()
        assert "nodes" in data
        # NetworkX <3 uses "links"; NetworkX >=3 uses "edges"
        assert "links" in data or "edges" in data
