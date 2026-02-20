# Contributing to ContextWeaver

Thanks for your interest. ContextWeaver is early-stage and contributions have an outsized impact.

## Setup

```bash
git clone https://github.com/your-org/contextweaver
cd contextweaver
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
# Add CW_ANTHROPIC_API_KEY to .env
```

Run the test suite (no API key needed):

```bash
pytest tests/ -v
```

Run the linter and type checker:

```bash
ruff check src/ tests/
mypy src/contextweaver/
```

## Good First Issues

These are scoped, well-defined, and don't require deep knowledge of the whole codebase:

| Issue | Skill level | Area |
|-------|-------------|------|
| Add Bitbucket as an artifact source | Beginner | `mining_agent.py` |
| Add `contextweaver viz` — open decision graph in browser | Beginner | `cli/main.py` + HTML |
| Add Linear integration (mine issues as artifacts) | Intermediate | `integrations/` |
| Add Slack export parsing | Intermediate | `integrations/` |
| Add `--since` and `--until` flags to `mine local` | Beginner | `cli/main.py` |
| Write integration test for the FastAPI webhook endpoint | Beginner | `tests/` |
| Add Notion as a doc source | Intermediate | `mining_agent.py` |
| Improve debt scoring with a configurable rubric | Intermediate | `archaeology_agent.py` |
| Add `contextweaver export` to dump decisions as JSON/CSV | Beginner | `cli/main.py` |
| Add a `--dry-run` flag to `mine` commands | Beginner | `cli/main.py` |

If you want to work on one of these, open an issue first so we don't duplicate effort.

## How to Submit a PR

1. Fork the repo and create a branch: `git checkout -b feature/your-feature`
2. Make your changes
3. Add tests for new behaviour
4. Run `ruff check` and `mypy` — fix any issues
5. Open a PR with a clear description of what and why

## Architecture Overview

```
Orchestrator
    │
    ├── MiningAgent        Reads artifacts from GitHub / git / docs
    ├── ArchaeologyAgent   Extracts structured Decisions from raw artifacts (the core)
    ├── ConflictDetector   Checks new artifacts against the decision archive
    └── BriefingAgent      Answers "why?" and generates onboarding briefs

Shared storage (agents never call each other directly):
    VectorStore (ChromaDB)   — semantic search over decisions
    DecisionGraph (NetworkX) — temporal topology, ancestry, debt
```

The most important file is `src/contextweaver/agents/archaeology_agent.py`. The system prompt in `_ARCHAEOLOGY_SYSTEM` drives the quality of everything downstream — improvements here have the highest leverage.

## Reporting Bugs

Use the [bug report template](.github/ISSUE_TEMPLATE/bug_report.md). Include:
- Python version and OS
- The command or API call that failed
- Full error output
- Whether the issue is reproducible without an API key (storage/webhook tests)

## Questions

Open a [GitHub Discussion](https://github.com/your-org/contextweaver/discussions) for questions, ideas, or general chat.
