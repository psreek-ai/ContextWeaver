"""
Base agent class for all ContextWeaver agents.

Wraps the Anthropic Python SDK with:
  - Structured logging
  - Retry logic (via tenacity)
  - Token usage tracking
  - A clean tool-calling interface
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any

import anthropic
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

from contextweaver.config import settings

log = structlog.get_logger()


class BaseAgent(ABC):
    """Abstract base class shared by all ContextWeaver agents."""

    #: Override in subclasses to give the agent a name for logging.
    NAME: str = "unnamed_agent"

    def __init__(self) -> None:
        key = settings.anthropic_api_key
        if key.startswith("sk-ant-si"):
            self._client = anthropic.Anthropic(auth_token=key)
        else:
            self._client = anthropic.Anthropic(api_key=key)
        self._model = settings.claude_model
        self._total_input_tokens = 0
        self._total_output_tokens = 0
        self.log = structlog.get_logger().bind(agent=self.NAME)

    # ------------------------------------------------------------------
    # Core reasoning call
    # ------------------------------------------------------------------

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        reraise=True,
    )
    def _reason(
        self,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 4096,
    ) -> anthropic.types.Message:
        """
        Single call to Claude with optional tool definitions.
        Handles token tracking and structured logging.
        """
        kwargs: dict[str, Any] = {
            "model": self._model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": messages,
        }
        if tools:
            kwargs["tools"] = tools

        response = self._client.messages.create(**kwargs)

        self._total_input_tokens += response.usage.input_tokens
        self._total_output_tokens += response.usage.output_tokens
        self.log.debug(
            "llm.call",
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            stop_reason=response.stop_reason,
        )
        return response

    def _extract_text(self, response: anthropic.types.Message) -> str:
        """Extract the first text block from a Claude response."""
        for block in response.content:
            if hasattr(block, "text"):
                return block.text
        return ""

    def _extract_json(self, response: anthropic.types.Message) -> Any:
        """
        Extract and parse JSON from a Claude response.
        Handles Claude's tendency to wrap JSON in markdown code fences.
        """
        text = self._extract_text(response)
        # Strip markdown fences if present
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()
        return json.loads(text)

    @property
    def token_stats(self) -> dict[str, int]:
        return {
            "input_tokens": self._total_input_tokens,
            "output_tokens": self._total_output_tokens,
            "total_tokens": self._total_input_tokens + self._total_output_tokens,
        }

    @abstractmethod
    def describe(self) -> str:
        """Return a human-readable description of this agent's role."""
