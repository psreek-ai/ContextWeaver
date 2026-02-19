"""Tests for core domain models."""

from datetime import datetime, timezone

import pytest

from contextweaver.models import (
    ArtifactKind,
    ConflictReport,
    ContextBriefing,
    Decision,
    DecisionConfidence,
    MiningStatus,
    RawArtifact,
)


class TestRawArtifact:
    def test_content_hash_is_deterministic(self):
        a = RawArtifact(
            kind=ArtifactKind.PR,
            source_id="42",
            body="Use PostgreSQL for primary storage",
            author="alice",
            created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )
        assert a.content_hash == a.content_hash  # Deterministic

    def test_different_artifacts_have_different_hashes(self):
        a = RawArtifact(
            kind=ArtifactKind.PR,
            source_id="1",
            body="use postgres",
            author="alice",
            created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )
        b = RawArtifact(
            kind=ArtifactKind.PR,
            source_id="2",
            body="use mongodb",
            author="alice",
            created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )
        assert a.content_hash != b.content_hash


class TestDecision:
    def _make(self, **kwargs) -> Decision:
        defaults = dict(
            id="test123",
            title="Use PostgreSQL as primary datastore",
            summary="We chose PostgreSQL over MongoDB for transactional consistency.",
            rationale="We need ACID transactions for financial records.",
            made_at=datetime(2024, 3, 15, tzinfo=timezone.utc),
        )
        defaults.update(kwargs)
        return Decision(**defaults)

    def test_creation_succeeds(self):
        d = self._make()
        assert d.title == "Use PostgreSQL as primary datastore"
        assert d.confidence == DecisionConfidence.MEDIUM

    def test_debt_score_bounded(self):
        with pytest.raises(Exception):
            self._make(debt_score=1.5)

    def test_id_generated_if_empty(self):
        d = Decision(
            id="",
            title="Auto ID test",
            summary="s",
            rationale="r",
            made_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )
        assert len(d.id) > 0

    def test_high_confidence_decision(self):
        d = self._make(confidence=DecisionConfidence.HIGH)
        assert d.confidence == DecisionConfidence.HIGH


class TestConflictReport:
    def test_creation(self):
        r = ConflictReport(
            artifact_id="pr/42",
            conflicting_decision_id="abc123",
            similarity_score=0.92,
            explanation="PR introduces MongoDB, contradicting PostgreSQL decision",
            severity="high",
            suggested_action="Review the PostgreSQL decision before merging",
        )
        assert r.severity == "high"
        assert 0 <= r.similarity_score <= 1


class TestMiningStatus:
    def test_initial_state(self):
        s = MiningStatus(repo="owner/repo")
        assert s.artifacts_processed == 0
        assert s.decisions_extracted == 0
        assert not s.completed
