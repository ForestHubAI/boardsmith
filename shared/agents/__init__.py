# SPDX-License-Identifier: AGPL-3.0-or-later
"""Agent layer for Boardsmith.

Agents combine LLM reasoning with tool execution (ReAct pattern)
to autonomously solve complex tasks like component research.

Quick start:
    from agents.knowledge_agent import KnowledgeAgent

    agent = KnowledgeAgent()
    result = await agent.find("SCD41")
    if result:
        print(result.mpn, result.confidence, result.source)
"""

from .firmware_review_agent import FirmwareReviewAgent, FirmwareReviewResult
from .iterative_orchestrator import (
    AuditTrail,
    BuildResult,
    IterationRecord,
    IterativeOrchestrator,
)
from .knowledge_agent import AgentComponentResult, KnowledgeAgent
from .react_loop import ReActResult, ReActStep, run_react_loop

__all__ = [
    "KnowledgeAgent",
    "AgentComponentResult",
    "run_react_loop",
    "ReActResult",
    "ReActStep",
    "FirmwareReviewAgent",
    "FirmwareReviewResult",
    "IterativeOrchestrator",
    "IterationRecord",
    "AuditTrail",
    "BuildResult",
]
