"""Tests for the GitHub webhook handler."""

import json
from datetime import datetime, timezone

import pytest

from contextweaver.integrations.github_webhook import GitHubWebhookHandler
from contextweaver.models import ArtifactKind


@pytest.fixture
def handler():
    return GitHubWebhookHandler(webhook_secret="test-secret")


class TestGitHubWebhookHandler:
    def _pr_payload(self, action="opened", title="Add GraphQL endpoint", body="We decided to add GraphQL"):
        return {
            "action": action,
            "pull_request": {
                "number": 42,
                "title": title,
                "body": body,
                "html_url": "https://github.com/org/repo/pull/42",
                "user": {"login": "alice"},
                "created_at": "2024-06-01T12:00:00Z",
                "merged": False,
                "labels": [],
                "base": {"ref": "main"},
            },
            "repository": {"full_name": "org/repo"},
        }

    def test_parse_pr_opened(self, handler):
        payload = self._pr_payload(action="opened")
        artifact = handler.parse_pull_request(payload)
        assert artifact is not None
        assert artifact.kind == ArtifactKind.PR
        assert artifact.source_id == "42"
        assert artifact.author == "alice"

    def test_parse_pr_closed_returns_none(self, handler):
        payload = self._pr_payload(action="closed")
        assert handler.parse_pull_request(payload) is None

    def test_parse_issue(self, handler):
        payload = {
            "action": "opened",
            "issue": {
                "number": 10,
                "title": "Performance regression in auth service",
                "body": "The auth service is 3x slower than last month",
                "html_url": "https://github.com/org/repo/issues/10",
                "user": {"login": "bob"},
                "created_at": "2024-05-15T09:00:00Z",
                "labels": [{"name": "performance"}],
            },
            "repository": {"full_name": "org/repo"},
        }
        artifact = handler.parse_issue(payload)
        assert artifact is not None
        assert artifact.kind == ArtifactKind.ISSUE
        assert "performance" in artifact.metadata["labels"]

    def test_parse_push(self, handler):
        payload = {
            "commits": [
                {
                    "id": "abc123456789",
                    "message": "feat: Switch authentication to JWT tokens for stateless operation\n\nThis allows horizontal scaling without shared session storage.",
                    "url": "https://github.com/org/repo/commit/abc123",
                    "author": {"email": "carol@example.com"},
                    "timestamp": "2024-07-01T10:00:00Z",
                    "added": [],
                    "modified": ["auth/handler.py"],
                },
                {
                    "id": "xyz",
                    "message": "fix typo",  # Too short, should be filtered
                    "url": "",
                    "author": {"email": "carol@example.com"},
                    "timestamp": "2024-07-01T10:05:00Z",
                    "added": [],
                    "modified": [],
                },
            ],
            "repository": {"full_name": "org/repo"},
        }
        artifacts = handler.parse_push(payload)
        assert len(artifacts) == 1  # Short commit filtered out
        assert artifacts[0].kind == ArtifactKind.COMMIT
        assert artifacts[0].author == "carol@example.com"

    def test_verify_signature_dev_mode(self):
        """Without a secret, verification always passes (dev mode)."""
        h = GitHubWebhookHandler(webhook_secret="")
        assert h.verify_signature(b"any payload", "sha256=anything") is True

    def test_verify_signature_correct(self, handler):
        import hashlib
        import hmac

        payload = b'{"action":"opened"}'
        sig = "sha256=" + hmac.new(b"test-secret", payload, hashlib.sha256).hexdigest()
        assert handler.verify_signature(payload, sig) is True

    def test_verify_signature_wrong(self, handler):
        assert handler.verify_signature(b"payload", "sha256=wrongsig") is False
