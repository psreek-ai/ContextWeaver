# ContextWeaver

**Decision Archaeology & Living Project Intelligence**

> *The first AI agent system that answers WHY your software is built the way it is.*

---

## The Problem No Tool Has Solved

Every software project loses its "why" over time.

Git tracks **what** changed. Jira tracks **what** was requested. Confluence stores **what** was written. But none of them track **why decisions were made** — the actual reasoning that produced your architecture.

When key engineers leave, that reasoning disappears. New team members spend months reconstructing context. PRs unknowingly contradict past decisions. Technical debt accumulates not from bad code, but from **lost reasoning**.

**This costs enterprises an average of 23 engineering weeks per year per team** (Stripe Developer Coefficient 2024).

---

## The Innovation: Decision Archaeology

ContextWeaver introduces a new class of AI capability: **Decision Archaeology** — the automatic reconstruction of *why* software decisions were made, from the implicit signals buried in commits, PRs, issues, and reviews.

A search for "decision archaeology AI agent" returned **zero results globally** (February 2026). This is genuinely new.

### What ContextWeaver Does

```
Project History                    ContextWeaver                    Outputs
─────────────                      ────────────                     ───────
GitHub PRs        ──┐              ┌──────────────┐
Commit messages   ──┤  [Mining]    │  Archaeology │   [Decisions]
Issues / Reviews  ──┤──────────▶  │  Agent       │──────────────▶  Decision
ADRs / Docs       ──┘  [Parsing]  │  (Claude)    │                  Knowledge
                                  └──────────────┘                  Graph
                                          │
                                  ┌───────┴───────┐
                                  │               │
                              [Conflict]     [Briefing]
                              Detector        Agent
                                  │               │
                                  ▼               ▼
                           PR conflict      Context
                           warnings         briefings
```

### The Four Agents

| Agent | Role | Innovation |
|-------|------|------------|
| **MiningAgent** | Harvests GitHub PRs, issues, commits, docs | Ingests any project artifact source |
| **ArchaeologyAgent** | Extracts *why* from raw artifacts using Claude | **Core innovation** - reconstructs rationale never explicitly written |
| **ConflictDetectorAgent** | Detects when new PRs contradict historical decisions | **Unprecedented** - no CI/CD tool does historical decision conflict detection |
| **BriefingAgent** | Generates living context briefings | Answers "why?" questions against your project's entire decision history |

---

## Demo

```bash
# 1. Mine your GitHub repository
contextweaver mine github --repo your-org/your-repo --days 365

# 2. Ask why a decision was made
contextweaver why "Why do we use PostgreSQL instead of MongoDB?"
# → "The switch to PostgreSQL in March 2022 (PR #234) was driven by the need
#    for ACID transactions in financial record processing. The team had evaluated
#    CockroachDB but rejected it due to operational overhead..."

# 3. Get a context briefing for a new engineer
contextweaver brief "authentication system" --for "new backend engineer"
# → Generates a full narrative: key decisions, critical constraints,
#    active decision debt, and questions to investigate

# 4. Check a proposed approach for conflicts
contextweaver check "We should store sessions in MongoDB for the new feature"
# → ⚠ CONFLICT DETECTED (HIGH)
#    Explanation: In PR #234 (2022-03-15), the team explicitly rejected MongoDB
#    for session storage due to lack of ACID transactions. This proposal
#    contradicts that decision.
#    Action: Review the PostgreSQL migration decision and update if the
#    context has changed before proceeding.
```

---

## Architecture

```
src/contextweaver/
├── agents/
│   ├── orchestrator.py        # Coordinates all agents via shared state
│   ├── mining_agent.py        # GitHub, local git, markdown docs
│   ├── archaeology_agent.py   # Core: extracts WHY using Claude claude-opus-4-6
│   ├── conflict_detector.py   # Semantic + reasoning conflict detection
│   └── briefing_agent.py      # Living context briefing generation
│
├── storage/
│   ├── vector_store.py        # ChromaDB: semantic search over decisions
│   └── decision_graph.py      # NetworkX: temporal decision topology
│
├── integrations/
│   └── github_webhook.py      # Real-time GitHub event processing
│
├── api/
│   └── routes.py              # FastAPI REST API (webhook + query endpoints)
│
└── cli/
    └── main.py                # Rich CLI (mine, why, brief, check, stats, serve)
```

### Key Design Decisions

**Agents communicate through storage, not messages.** Every agent reads/writes to the shared VectorStore and DecisionGraph. This makes agents independently testable, naturally parallelizable, and fully auditable.

**Two-stage conflict detection.** First, semantic retrieval surfaces related decisions. Then Claude reasoning determines if there's a genuine contradiction. This eliminates false positives from generic similarity while catching semantically disguised conflicts.

**Temporal ordering matters.** Artifacts are processed chronologically so the ArchaeologyAgent can understand what was known at each point in time — a decision made in 2019 has different context than the same decision made in 2024.

**Decision debt scoring.** Every extracted decision gets a 0.0–1.0 debt score representing how outdated it is. This surfaces the "load-bearing assumptions" that should be revisited.

---

## Installation

```bash
# Install from source
git clone https://github.com/your-org/contextweaver
cd contextweaver
pip install -e ".[dev]"

# Configure
cp .env.example .env
# Edit .env and add your Anthropic API key

# Run the quickstart demo (no GitHub token needed)
python examples/quickstart.py
```

### Requirements

- Python 3.11+
- Anthropic API key (Claude claude-opus-4-6)
- GitHub token (optional, for GitHub mining)

---

## REST API

```bash
# Start the API server
contextweaver serve

# Generate a briefing
curl -X POST http://localhost:8765/brief \
  -H "Content-Type: application/json" \
  -d '{"topic": "database architecture", "subject": "new engineer"}'

# Check for conflicts
curl -X POST http://localhost:8765/conflicts \
  -H "Content-Type: application/json" \
  -d '{"text": "We should add a Redis cache in front of PostgreSQL"}'

# Register GitHub webhook (point GitHub to: http://your-host:8765/webhook/github)
# Automatically checks every PR for decision conflicts on open/update
```

### API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Health check |
| `GET` | `/stats` | System statistics |
| `GET` | `/graph` | Export decision graph as JSON |
| `POST` | `/brief` | Generate context briefing |
| `POST` | `/why` | Answer a why? question |
| `POST` | `/conflicts` | Check text for conflicts |
| `POST` | `/mine/github` | Trigger GitHub mining |
| `POST` | `/mine/local` | Trigger local repo mining |
| `POST` | `/webhook/github` | GitHub webhook receiver |

---

## GitHub Integration

Add ContextWeaver as a GitHub webhook to get automatic conflict detection on every PR:

1. Deploy ContextWeaver (`contextweaver serve`)
2. In your GitHub repo: Settings → Webhooks → Add webhook
3. Set Payload URL: `https://your-host:8765/webhook/github`
4. Content type: `application/json`
5. Events: Pull requests, Issues, Pushes

Every new PR will be automatically checked against your decision archive.

---

## Monetization Strategy

### Tier 1: Developer (Free)
- Public repositories only
- Up to 500 decisions indexed
- CLI access
- Community support

### Tier 2: Team ($29/month)
- Private repositories
- Unlimited decisions
- REST API + webhooks
- GitHub App integration
- 5 seats

### Tier 3: Business ($199/month)
- Multi-repo support
- Decision graph visualization
- Slack/Teams integration
- Custom ADR templates
- Decision health dashboards
- 25 seats

### Tier 4: Enterprise (Custom)
- Self-hosted deployment
- SSO/SAML
- Compliance exports (SOC 2, ISO 27001)
- Custom LLM deployment
- SLA guarantees
- Dedicated support

### Additional Revenue Streams
- **GitHub Marketplace App** - one-click install, usage-based billing
- **VS Code Extension** - inline decision history in your editor
- **API Access** - $0.001 per query for third-party integrations
- **Enterprise Insurance Partnerships** - insurers discount premiums for teams using ContextWeaver

---

## Why This Has No Precedent

| Tool | What it tracks | What it misses |
|------|----------------|----------------|
| Git | File diffs | Why the change was made |
| GitHub PRs | Description | Implicit reasoning in discussions |
| Jira | Tickets | Architectural rationale |
| Confluence | Written docs | Unwritten tribal knowledge |
| ADRs | Explicit decisions | 95% of decisions never get an ADR |
| LangSmith | Agent actions | Organizational decision history |
| **ContextWeaver** | **Everything above + WHY** | Nothing |

The closest comparison is **Architecture Decision Records (ADRs)** — but ADRs require engineers to manually write them. Studies show fewer than 5% of software decisions ever get an ADR. ContextWeaver automatically reconstructs the other 95% from existing artifacts.

---

## Running Tests

```bash
# All tests (no API key required for model/storage tests)
pytest tests/ -v

# With coverage
pytest tests/ --cov=src/contextweaver --cov-report=html
```

---

## Built With Claude Code

This entire system was designed and built using [Claude Code](https://claude.ai/code) — Anthropic's AI coding tool. The multi-agent architecture, storage design, and API layer were all generated and iterated in a single Claude Code session.

ContextWeaver demonstrates that Claude Code can produce production-quality, architecturally sophisticated AI systems — not just scripts.

---

## License

MIT License. See [LICENSE](LICENSE) for details.

---

## Contributing

ContextWeaver is genuinely novel software. If you find the concept compelling and want to contribute, please open an issue first to discuss what you'd like to change.

**The most valuable contributions:**
- Additional artifact sources (Slack, Linear, Notion, Confluence)
- Better embedding strategies for higher-quality conflict detection
- Visualization layer for the decision graph
- Language-specific code analysis (link code patterns to their governing decisions)
