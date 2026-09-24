"""Thin LLM client abstraction — decision #5: "a small internal
abstraction/interface is acceptable if it genuinely improves testing or
separation of concerns, but do not build a provider framework merely for
future extensibility." This is exactly that and nothing more: one
Protocol, one real implementation, no multi-provider machinery.

Its entire reason to exist is ADR-009's mocking discipline: every agent
module is written against `LLMClient`, never against `anthropic.Anthropic`
directly, so tests inject a fake implementation
(tests/fakes.py::FakeLLMClient) and never touch the network or the $0.50
budget. Only eval/run_baseline.py, run deliberately and only after
explicit review, constructs the real one.
"""

from dataclasses import dataclass
from typing import Any, Protocol

import anthropic

# ADR-010: forced tool use, not prompt instruction alone, is how
# structured output is actually enforced.
RETRYABLE_EXCEPTIONS = (
    anthropic.RateLimitError,
    anthropic.InternalServerError,
    anthropic.OverloadedError,
    anthropic.ServiceUnavailableError,
    anthropic.APIConnectionError,
    anthropic.APITimeoutError,
)


def is_retryable(exc: Exception) -> bool:
    """architecture.md's retry policy: retryable = timeout/5xx/rate-limit/
    overloaded/connection; everything else (bad request, auth, permission,
    not found, unprocessable, request-too-large) is not — retrying a
    malformed request just wastes budget repeating the same failure."""
    return isinstance(exc, RETRYABLE_EXCEPTIONS)


@dataclass
class ToolCallResult:
    """The one thing every agent call cares about: the tool's input (the
    structured payload), plus real usage/cost accounting."""

    tool_input: dict[str, Any]
    input_tokens: int
    output_tokens: int
    model: str


class LLMClient(Protocol):
    def call_with_forced_tool(
        self,
        *,
        model: str,
        system: str,
        user_message: str,
        tool_name: str,
        tool_description: str,
        tool_input_schema: dict[str, Any],
        max_tokens: int,
    ) -> ToolCallResult: ...


class AnthropicLLMClient:
    """The real implementation. Never constructed in a test — see the
    module docstring."""

    def __init__(self, api_key: str):
        self._client = anthropic.Anthropic(api_key=api_key)

    def call_with_forced_tool(
        self,
        *,
        model: str,
        system: str,
        user_message: str,
        tool_name: str,
        tool_description: str,
        tool_input_schema: dict[str, Any],
        max_tokens: int,
    ) -> ToolCallResult:
        response = self._client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user_message}],
            tools=[{
                "name": tool_name,
                "description": tool_description,
                "input_schema": tool_input_schema,
            }],
            tool_choice={"type": "tool", "name": tool_name},
        )

        tool_use_block = next(
            (block for block in response.content if block.type == "tool_use"), None
        )
        if tool_use_block is None:
            raise ValueError(
                "no tool_use block in response despite forced tool_choice — "
                f"stop_reason={response.stop_reason!r}"
            )

        return ToolCallResult(
            tool_input=tool_use_block.input,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            model=model,
        )
