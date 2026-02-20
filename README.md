# ContextWeaver

<div align="center">

**"Why is the auth service built like this?"**
**"Who decided we'd use Postgres and why?"**
**"Does this PR contradict a decision we made 2 years ago?"**

ContextWeaver answers all of these — automatically — from your existing git history.

[![Python](https://img.shields.io/badge/python-3.11+-3776AB?logo=python&logoColor=white)](https://python.org)
[![License: MIT](https://img.shields.io/badge/license-MIT-22c55e)](LICENSE)
[![Powered by Claude](https://img.shields.io/badge/powered%20by-Claude%20Opus%204-D97757?logo=anthropic&logoColor=white)](https://anthropic.com)
[![CI](https://img.shields.io/badge/CI-passing-22c55e)](#running-tests)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen)](CONTRIBUTING.md)

<!-- To regenerate: pip install agg && agg docs/demo.cast docs/demo.gif -->
![ContextWeaver Demo](docs/demo.gif)

</div>

---

## The Pain

Every codebase has this conversation:

> *"Why is the session service written this way?"*
> *"I have no idea — Sarah built it and she left 8 months ago."*

Git tracks **what** changed. Jira tracks **what** was requested. Nothing tracks **why** decisions were made — the actual reasoning that produced your architecture. When engineers leave, that reasoning leaves with them.

The result: new engineers spend months reconstructing context. PRs unknowingly undo past decisions. The same architecture debates get relitigated every 18 months.

**ContextWeaver mines that reasoning back out.**

---

## How It Works

ContextWeaver runs a swarm of four AI agents against your project history:

```
Your project history              Four AI agents                  What you get
──────────────────                ──────────────                  ────────────

GitHub PRs     ──┐
Commit messages──┤──▶  MiningAgent      ──▶  ArchaeologyAgent  ──▶  Decision archive
Issues/Reviews ──┤                               (Claude)             (the "why")
ADRs / Docs    ──┘                                   │
                                                     ▼
                                          ConflictDetector  ──▶  PR warnings
                                          BriefingAgent     ──▶  Onboarding briefs
```

The key agent is **ArchaeologyAgent**: it doesn't just extract what people explicitly wrote. It reconstructs the reasoning they *implied* — from rejected alternatives buried in review threads, from the "we considered X but..." in issue comments, from the tone of a commit message. This is the part no other tool does.

---

## Demo

```bash
# Index your project's decision history (works on local repos, no token needed)
contextweaver mine local ./my-project

# Ask why something was built the way it is
$ contextweaver why "Why do we use PostgreSQL instead of MongoDB?"

  The switch to PostgreSQL (PR #234, March 2022) was driven by the need for ACID
  transactions in financial record processing. The team explicitly evaluated MongoDB
  and CockroachDB — MongoDB was rejected due to lack of multi-document transactions
  that were causing data integrity issues in the order pipeline; CockroachDB was
  rejected due to operational overhead at the team's then-current scale.
  The trade-off accepted: ~2 weeks migration effort and higher memory usage.
  Source: PR #234, Issue #189, commit a3f9c12.

# Generate an onboarding brief for a new engineer
$ contextweaver brief "authentication system" --for "new backend engineer"

  [Generates a narrative briefing: key decisions, critical constraints,
   active decision debt, and questions to investigate before touching the code]

# Catch a PR that contradicts a past decision
$ contextweaver check "We should store sessions in MongoDB for the new feature"

  ⚠  CONFLICT DETECTED  [HIGH]
  In PR #234 (2022-03-15), the team explicitly rejected MongoDB for storage due
  to lack of ACID transactions. This proposal contradicts that decision.
  Suggested action: Review the PostgreSQL migration decision and update it
  if the context has changed before proceeding.
```

---

## Quickstart

```bash
git clone https://github.com/psreek-ai/ContextWeaver
cd contextweaver
pip install -e .

# Add your Anthropic API key
cp .env.example .env
# Edit .env: set CW_ANTHROPIC_API_KEY=sk-ant-...

# Run the demo with sample project history (no API key needed for the demo data)
python examples/quickstart.py

# Or mine your own local repo
contextweaver mine local /path/to/your/project
contextweaver why "why did we choose this database?"
```

**Requirements:** Python 3.11+ · Anthropic API key · GitHub token *(optional)*

---

## What Makes This Different

Most tools capture what was *explicitly documented*. ADRs require engineers to write them — fewer than 5% ever do. ContextWeaver recovers the other 95%: the reasoning embedded in PR discussions, review threads, rejected alternatives in issue comments, and the context implied by what engineers *chose not to do*.

| Tool | Captures | Misses |
|------|----------|--------|
| Git | File diffs | Why the change was made |
| GitHub PRs | Description text | Implicit reasoning in discussions |
| Confluence / Notion | What was written down | Unwritten tribal knowledge |
| ADRs | Explicit decisions | 95% of decisions that never got an ADR |
| Qodo / Greptile | Code patterns for review | Queryable decision archive, briefings |
| **ContextWeaver** | **Reconstructed WHY from all of the above** | — |

---

## Architecture

```
src/contextweaver/
├── agents/
│   ├── orchestrator.py        # Coordinates agents via shared storage (no direct messaging)
│   ├── mining_agent.py        # GitHub API, local git, markdown docs
│   ├── archaeology_agent.py   # Core: reconstructs WHY using Claude Opus 4
│   ├── conflict_detector.py   # Two-stage: vector similarity → Claude reasoning
│   └── briefing_agent.py      # Narrative context briefing generation
│
├── storage/
│   ├── vector_store.py        # ChromaDB: semantic search over decisions
│   └── decision_graph.py      # NetworkX: temporal decision topology (ancestry, debt)
│
├── integrations/
│   └── github_webhook.py      # Real-time PR/push/issue event processing
│
├── api/
│   └── routes.py              # FastAPI: /brief /why /conflicts /webhook/github
│
└── cli/
    └── main.py                # Rich CLI: mine · why · brief · check · stats · serve
```

**Design principles:**
- Agents share state through storage, never through direct calls — independently testable and parallelizable
- Two-stage conflict detection: vector similarity finds candidates, Claude reasoning confirms genuine contradictions (avoids false positives)
- Artifacts processed chronologically so the ArchaeologyAgent has temporal context

---

## REST API

```bash
contextweaver serve  # starts on http://localhost:8765

# Ask a why? question
curl -X POST http://localhost:8765/why \
  -H "Content-Type: application/json" \
  -d '{"question": "Why do we use Redis for sessions?"}'

# Generate a briefing
curl -X POST http://localhost:8765/brief \
  -H "Content-Type: application/json" \
  -d '{"topic": "database architecture", "subject": "new engineer"}'

# Check text for conflicts before writing code
curl -X POST http://localhost:8765/conflicts \
  -H "Content-Type: application/json" \
  -d '{"text": "We should rewrite the auth service in Go"}'
```

Point a GitHub webhook at `/webhook/github` to get automatic conflict detection on every PR.

---

## Running Tests

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

Tests for models, storage, and webhook parsing run without an API key.

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for setup instructions and a list of good first issues.

The most impactful areas right now:
- **New artifact sources** — Slack, Linear, Notion, Confluence
- **Graph visualization** — `contextweaver viz` to open an interactive decision graph in the browser
- **VS Code extension** — inline decision history while you code
- **Better embeddings** — evaluate custom fine-tuned embeddings vs. sentence-transformers

---

## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=psreek-ai/ContextWeaver&type=Date)](https://star-history.com/#psreek-ai/ContextWeaver&Date)

---

## Built With Claude Code

Designed and built entirely with [Claude Code](https://claude.ai/code). The multi-agent architecture, storage layer, API, and CLI were produced in a single session — a demonstration that Claude Code can generate production-quality, architecturally considered systems.

---

<div align="center">

MIT License · [Report a bug](https://github.com/psreek-ai/ContextWeaver/issues/new?template=bug_report.md) · [Request a feature](https://github.com/psreek-ai/ContextWeaver/issues/new?template=feature_request.md)

</div>
