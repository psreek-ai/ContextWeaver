"""
ContextWeaver Agent Swarm.

Four specialized agents collaborate under the Orchestrator:

  MiningAgent         → Harvests raw artifacts from GitHub/git/docs
  ArchaeologyAgent    → Extracts Decisions from artifacts (the core innovation)
  ConflictDetector    → Detects when new work contradicts historical decisions
  BriefingAgent       → Generates living context briefings for humans

Each agent is powered by Claude claude-opus-4-6 and communicates through the
shared VectorStore + DecisionGraph rather than direct message passing,
enabling asynchronous, parallel operation.
"""

from contextweaver.agents.orchestrator import Orchestrator
from contextweaver.agents.mining_agent import MiningAgent
from contextweaver.agents.archaeology_agent import ArchaeologyAgent
from contextweaver.agents.conflict_detector import ConflictDetectorAgent
from contextweaver.agents.briefing_agent import BriefingAgent

__all__ = [
    "Orchestrator",
    "MiningAgent",
    "ArchaeologyAgent",
    "ConflictDetectorAgent",
    "BriefingAgent",
]
