"""Fakes shared across test modules. FakeLLMClient is the entire reason
Phase 6+ agent code can be tested at all without spending real API budget
(ADR-009) — it implements the same app.llm.client.LLMClient protocol the
real Anthropic-backed client does, so agent modules never know the
difference.
"""

from dataclasses import dataclass, field
from typing import Any

import httpx2

from app.llm.client import ToolCallResult


def fake_api_error(error_cls: type[Exception], status_code: int) -> Exception:
    """Build a real instance of an anthropic.APIStatusError subclass —
    these require a genuine response object, not just a message string
    (their __init__ is `(message, *, response, body)`). Constructing the
    real type, not a look-alike, means is_retryable() and any isinstance
    check downstream sees exactly what the real SDK would raise."""
    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    response = httpx2.Response(status_code=status_code, request=request)
    return error_cls("scripted failure", response=response, body=None)


@dataclass
class FakeLLMClient:
    """Scripted responses, played back in call order. Each entry in
    `responses` is either a dict (returned as tool_input, wrapped in a
    ToolCallResult with token counts from `usage`) or an Exception
    instance (raised instead — build one with fake_api_error for a real
    anthropic error type) — lets a single test script "fail twice, then
    succeed" to exercise app/retry.py against a real call site, not just
    retry.py's own unit tests in isolation."""

    responses: list[Any] = field(default_factory=list)
    default_usage: tuple[int, int] = (100, 50)  # (input_tokens, output_tokens)
    calls: list[dict[str, Any]] = field(default_factory=list)
    _index: int = 0

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
        self.calls.append({
            "model": model, "system": system, "user_message": user_message,
            "tool_name": tool_name, "max_tokens": max_tokens,
        })
        if self._index >= len(self.responses):
            raise AssertionError(
                f"FakeLLMClient exhausted: {len(self.responses)} scripted "
                f"response(s), but call #{self._index + 1} was made"
            )
        item = self.responses[self._index]
        self._index += 1

        if isinstance(item, Exception):
            raise item

        input_tokens, output_tokens = self.default_usage
        return ToolCallResult(
            tool_input=item, input_tokens=input_tokens, output_tokens=output_tokens,
            model=model,
        )
