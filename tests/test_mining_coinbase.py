"""
Integration test: MiningAgent against psreek-ai/CoinbaseTrading (local clone).

The mining layer (git commit extraction + doc scanning) requires no API key —
only the downstream ArchaeologyAgent calls Claude. This test validates that the
mining pipeline works end-to-end against a real-world repository.
"""

import os
import pytest

COINBASE_REPO = "/tmp/CoinbaseTrading"

# Skip entire module if repo not present
if not os.path.isdir(os.path.join(COINBASE_REPO, ".git")):
    pytest.skip("CoinbaseTrading repo not cloned at /tmp/CoinbaseTrading", allow_module_level=True)

# Ensure a dummy key is set before any import of contextweaver
os.environ.setdefault("CW_ANTHROPIC_API_KEY", "dummy-key-for-mining-tests")

from contextweaver.agents.mining_agent import MiningAgent  # noqa: E402
from contextweaver.models import ArtifactKind  # noqa: E402


@pytest.fixture(scope="module")
def agent():
    return MiningAgent()


class TestMineLocalGit:
    def test_returns_artifacts(self, agent):
        artifacts = agent.mine_local_git(COINBASE_REPO)
        assert len(artifacts) > 0, "Expected at least one commit artifact"

    def test_artifacts_sorted_chronologically(self, agent):
        artifacts = agent.mine_local_git(COINBASE_REPO)
        dates = [a.created_at for a in artifacts]
        assert dates == sorted(dates), "Artifacts must be sorted oldest-first"

    def test_artifact_fields_populated(self, agent):
        artifacts = agent.mine_local_git(COINBASE_REPO)
        for a in artifacts:
            assert a.source_id, "source_id must not be empty"
            assert a.title, "title (commit summary) must not be empty"
            assert a.created_at is not None

    def test_artifact_kind_is_commit(self, agent):
        artifacts = agent.mine_local_git(COINBASE_REPO)
        for a in artifacts:
            assert a.kind == ArtifactKind.COMMIT

    def test_content_hash_unique(self, agent):
        artifacts = agent.mine_local_git(COINBASE_REPO)
        hashes = [a.content_hash for a in artifacts]
        assert len(hashes) == len(set(hashes)), "Duplicate content hashes detected"

    def test_files_changed_metadata(self, agent):
        artifacts = agent.mine_local_git(COINBASE_REPO)
        with_files = [a for a in artifacts if a.metadata.get("files_changed")]
        assert len(with_files) > 0, "Expected file-change metadata on some commits"

    def test_max_commits_respected(self, agent):
        artifacts = agent.mine_local_git(COINBASE_REPO, max_commits=5)
        assert len(artifacts) <= 5

    def test_known_commit_subjects_present(self, agent):
        """Key CoinbaseTrading commit subjects should appear in the artifact titles."""
        artifacts = agent.mine_local_git(COINBASE_REPO)
        titles = " ".join(a.title.lower() for a in artifacts)
        assert any(kw in titles for kw in ("refactor", "fix", "feat", "implement"))


class TestMineDocs:
    def test_finds_markdown_docs(self, agent):
        artifacts = agent.mine_docs(COINBASE_REPO)
        assert len(artifacts) > 0, "Expected markdown doc artifacts"

    def test_readme_captured(self, agent):
        artifacts = agent.mine_docs(COINBASE_REPO)
        names = [a.title.lower() for a in artifacts]
        assert any("readme" in n for n in names)

    def test_doc_body_not_empty(self, agent):
        artifacts = agent.mine_docs(COINBASE_REPO)
        for a in artifacts:
            assert a.body.strip(), f"Empty body for doc: {a.title}"

    def test_body_capped_at_8000_chars(self, agent):
        artifacts = agent.mine_docs(COINBASE_REPO)
        for a in artifacts:
            assert len(a.body) <= 8000, f"Body exceeds 8000-char limit: {a.title}"

    def test_docs_sorted_chronologically(self, agent):
        artifacts = agent.mine_docs(COINBASE_REPO)
        dates = [a.created_at for a in artifacts]
        assert dates == sorted(dates)
