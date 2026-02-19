"""
ContextWeaver Quickstart Example

This script demonstrates the full ContextWeaver workflow:

1. Create some sample artifacts (simulating a project history)
2. Run decision archaeology to extract decisions
3. Generate a context briefing
4. Check a proposed approach for conflicts
5. Answer a "why?" question

To run:
  export CW_ANTHROPIC_API_KEY=your-key-here
  python examples/quickstart.py
"""

import os
import sys
from datetime import datetime, timezone

# Ensure src/ is on the path when running from project root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from contextweaver.agents.orchestrator import Orchestrator
from contextweaver.models import ArtifactKind, RawArtifact

# ---------------------------------------------------------------------------
# Sample artifacts that simulate a project's history
# ---------------------------------------------------------------------------

SAMPLE_ARTIFACTS = [
    RawArtifact(
        kind=ArtifactKind.PR,
        source_id="pr-1",
        title="Switch from MongoDB to PostgreSQL",
        body="""
## Summary
After evaluating our options, we're switching from MongoDB to PostgreSQL.

## Why
- We need ACID transactions for financial record processing
- Our data is highly relational (users → orders → line_items → products)
- MongoDB's lack of multi-document transactions was causing data integrity issues
- The team has more SQL expertise than NoSQL

## Alternatives considered
- MongoDB with manual transaction compensation logic (rejected: too complex)
- CockroachDB (rejected: operational overhead, overkill for current scale)
- MySQL (considered, but PostgreSQL has better JSON support for our hybrid needs)

## Trade-offs accepted
- Migration effort (~2 weeks of engineering time)
- Need to learn PostgreSQL-specific features (JSONB, advisory locks)
- Slightly higher memory usage than MongoDB at our current scale
        """.strip(),
        author="sarah@example.com",
        created_at=datetime(2022, 3, 15, tzinfo=timezone.utc),
        metadata={"labels": ["architecture", "database"], "merged": True},
    ),
    RawArtifact(
        kind=ArtifactKind.ISSUE,
        source_id="issue-42",
        title="Authentication service is a single point of failure",
        body="""
Our monolithic auth service handles all authentication synchronously.
If it goes down, the entire platform goes down.

We need to evaluate:
1. JWT tokens (stateless, no auth service dependency)
2. OAuth2 with token caching
3. Distributed auth service with Redis session storage

Given our 99.9% uptime SLA, this is critical to resolve.
        """.strip(),
        author="dev@example.com",
        created_at=datetime(2022, 6, 1, tzinfo=timezone.utc),
        metadata={"labels": ["architecture", "reliability", "security"]},
    ),
    RawArtifact(
        kind=ArtifactKind.PR,
        source_id="pr-87",
        title="Implement JWT-based stateless authentication",
        body="""
Closes #42

## Decision
Move to JWT tokens for stateless authentication.

## Rationale
- Eliminates auth service as SPOF
- Enables horizontal scaling without shared session state
- Standard, widely understood protocol
- 15-minute token expiry + refresh tokens balances security and UX

## What we're NOT doing
- We're NOT storing JWTs in localStorage (XSS risk) → using HttpOnly cookies
- We're NOT implementing our own JWT library → using PyJWT (battle-tested)
- We're NOT removing the auth service entirely → it still handles token refresh

## Security trade-offs
- JWT revocation requires a token blacklist (we'll use Redis)
- Tokens contain user claims - don't put sensitive data in payload
        """.strip(),
        author="alice@example.com",
        created_at=datetime(2022, 7, 12, tzinfo=timezone.utc),
        metadata={"labels": ["security", "authentication"], "merged": True},
    ),
    RawArtifact(
        kind=ArtifactKind.ADR,
        source_id="docs/adr/0003-api-versioning.md",
        title="0003-api-versioning.md",
        body="""
# ADR 003: API Versioning Strategy

## Status: Accepted

## Context
Our API is used by 3 mobile apps and 12 external partners.
Breaking changes to the API have caused production incidents twice.

## Decision
Use URL path versioning (/api/v1/, /api/v2/) rather than header-based versioning.

## Rationale
- More visible and debuggable than Accept headers
- Easier to document and communicate to partners
- Simpler to implement in our API gateway
- Industry standard (Stripe, Twilio, GitHub all use it)

## Rejected alternatives
- Header versioning (Accept: application/vnd.myapp.v2+json): harder to test in browsers
- Query string versioning (?version=2): pollutes request logs and caching keys
- Content negotiation: too complex for our team's current API design expertise

## Consequences
- Old API versions must be maintained for minimum 18 months after deprecation
- Deprecation notices must be sent 6 months in advance
- We need versioned API documentation (Swagger per version)
        """.strip(),
        author="tech-lead@example.com",
        created_at=datetime(2022, 9, 20, tzinfo=timezone.utc),
        metadata={},
    ),
]


def main():
    print("=" * 70)
    print("ContextWeaver Quickstart Demo")
    print("Decision Archaeology & Living Project Intelligence")
    print("=" * 70)

    # Initialize the orchestrator
    print("\n[1/5] Initializing ContextWeaver...")
    orc = Orchestrator()
    print(f"      Currently indexed: {orc.stats()['decisions_indexed']} decisions")

    # Index sample artifacts
    print("\n[2/5] Running Decision Archaeology on sample project history...")
    all_decisions = []
    for artifact in SAMPLE_ARTIFACTS:
        print(f"      Processing: {artifact.title[:60]}...")
        decisions = orc.index_artifact(artifact)
        all_decisions.extend(decisions)
        for d in decisions:
            print(f"        → Found decision: [{d.confidence.value.upper()}] {d.title}")

    print(f"\n      Total decisions extracted: {len(all_decisions)}")

    # Generate a context briefing
    print("\n[3/5] Generating context briefing for 'authentication system'...")
    briefing = orc.brief(
        "authentication system",
        subject="new backend engineer",
        scope="auth module",
    )
    print("\n--- BRIEFING NARRATIVE ---")
    print(briefing.narrative)
    if briefing.critical_constraints:
        print("\n--- CRITICAL CONSTRAINTS ---")
        for c in briefing.critical_constraints:
            print(f"  • {c}")
    if briefing.suggested_questions:
        print("\n--- QUESTIONS TO INVESTIGATE ---")
        for q in briefing.suggested_questions:
            print(f"  ? {q}")

    # Answer a "why?" question
    print("\n[4/5] Answering: 'Why did we switch to PostgreSQL?'")
    answer = orc.why("Why did we switch to PostgreSQL?")
    print("\n--- ANSWER ---")
    print(answer)

    # Conflict detection
    print("\n[5/5] Checking proposed approach for conflicts...")
    proposed = """
    I'm proposing we store session state in MongoDB for the new user preferences feature.
    MongoDB's flexible schema is perfect for storing varied preference structures.
    We'll use MongoDB's built-in session TTL to automatically expire old sessions.
    """
    conflicts = orc.check_text_conflicts(proposed, label="mongodb-sessions-proposal")
    if conflicts:
        print(f"\n  ⚠ {len(conflicts)} conflict(s) detected!")
        for c in conflicts:
            print(f"\n  Severity: {c.severity.upper()}")
            print(f"  Explanation: {c.explanation}")
            print(f"  Action: {c.suggested_action}")
    else:
        print("  ✓ No conflicts detected.")

    print("\n" + "=" * 70)
    print("Demo complete. Final stats:")
    s = orc.stats()
    print(f"  Decisions indexed:  {s['decisions_indexed']}")
    print(f"  Graph nodes:        {s['graph_nodes']}")
    print(f"  Graph edges:        {s['graph_edges']}")
    print("=" * 70)


if __name__ == "__main__":
    main()
