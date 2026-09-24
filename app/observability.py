"""LLM tracing (Langfuse) and application error tracking (Sentry) —
observability.md's design, implemented (Phase 10).

Deliberately additive, not invasive: `TracedLLMClient` wraps any
`LLMClient` (app/llm/client.py) and implements the exact same Protocol,
so nothing above it — app/agents/*.py, app/reconcile.py,
app/reinvestigate.py, every existing test — needs to change at all. A
caller that wants tracing constructs `TracedLLMClient(AnthropicLLMClient(key))`
instead of the bare client; everything else is unaware of the difference.
This also means call_with_forced_tool's signature never grew case_id/
agent_run_id parameters that no live caller could supply yet anyway (no
orchestrator threads a case through a live LLM call — limitations.md) —
case-level correlation is a constructor-time argument instead
(`TracedLLMClient(client, trace_id=str(case.id))`), ready for whenever
that orchestrator exists, without having touched a single already-tested
Phase 6/7/8 call site to get there.

Both integrations are no-ops without real credentials — nothing here
requires signing up for anything to build or test it, and neither one
can ever break the LLM call or the app it's attached to: tracing
failures are caught and swallowed, never re-raised, because observability
must never take down the thing it observes.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from typing import Any

from app.config import settings
from app.llm.client import LLMClient, ToolCallResult

REDACTION_MAX_CHARS = 200


@dataclass
class Redacted:
    """observability.md's redaction policy, made a concrete, testable
    shape: a bounded excerpt plus a hash of the full text — enough to
    debug from, never the full document/prompt content leaving the
    local system."""

    excerpt: str
    sha256: str
    full_length: int

    def as_dict(self) -> dict[str, Any]:
        return {"excerpt": self.excerpt, "sha256": self.sha256, "full_length": self.full_length}


def redact_for_trace(text: str, max_chars: int = REDACTION_MAX_CHARS) -> Redacted:
    return Redacted(
        excerpt=text[:max_chars],
        sha256=hashlib.sha256(text.encode()).hexdigest(),
        full_length=len(text),
    )


def _get_langfuse_client() -> Any | None:
    """Returns a configured Langfuse client, or None if unconfigured —
    the one place that decides whether tracing is active at all."""
    if not (settings.langfuse_public_key and settings.langfuse_secret_key):
        return None
    try:
        from langfuse import Langfuse
    except ImportError:  # pragma: no cover - langfuse is a hard dependency once added
        return None
    return Langfuse(
        public_key=settings.langfuse_public_key,
        secret_key=settings.langfuse_secret_key,
        host=settings.langfuse_host,
    )


class TracedLLMClient:
    """Wraps any LLMClient with Langfuse tracing. Implements the same
    Protocol app.llm.client.LLMClient defines — structurally, not by
    inheritance, matching how FakeLLMClient already satisfies it."""

    def __init__(self, inner: LLMClient, *, trace_id: str | None = None, langfuse: Any = None):
        self._inner = inner
        self._trace_id = trace_id
        self._langfuse = langfuse if langfuse is not None else _get_langfuse_client()

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
        if self._langfuse is None:
            return self._inner.call_with_forced_tool(
                model=model, system=system, user_message=user_message, tool_name=tool_name,
                tool_description=tool_description, tool_input_schema=tool_input_schema,
                max_tokens=max_tokens,
            )

        generation = self._start_generation(model, system, user_message, tool_name)
        start = time.monotonic()
        try:
            result = self._inner.call_with_forced_tool(
                model=model, system=system, user_message=user_message, tool_name=tool_name,
                tool_description=tool_description, tool_input_schema=tool_input_schema,
                max_tokens=max_tokens,
            )
        except Exception as exc:
            error_message = str(exc)[:500]
            self._safely(lambda: generation.update(
                level="ERROR", status_message=error_message,
            ))
            self._safely(generation.end)
            raise
        latency_s = time.monotonic() - start
        self._safely(lambda: generation.update(
            output=redact_for_trace(json.dumps(result.tool_input)).as_dict(),
            usage_details={"input": result.input_tokens, "output": result.output_tokens},
            metadata={"latency_s": latency_s},
        ))
        self._safely(generation.end)
        return result

    def _start_generation(self, model: str, system: str, user_message: str, tool_name: str):
        def _start():
            kwargs: dict[str, Any] = {}
            if self._trace_id is not None:
                kwargs["trace_context"] = {"trace_id": self._trace_id}
            return self._langfuse.start_observation(
                name=tool_name, as_type="generation", model=model,
                input=redact_for_trace(f"{system}\n\n{user_message}").as_dict(),
                **kwargs,
            )
        return self._safely(_start)

    @staticmethod
    def _safely(fn):
        """Tracing must never break the traced operation — a Langfuse SDK
        error (network, auth, version mismatch) is logged-and-swallowed,
        never allowed to fail a real LLM call."""
        try:
            return fn()
        except Exception:  # noqa: BLE001 - deliberately broad, see docstring
            return _NoopObservation()


class _NoopObservation:
    """Returned when starting/updating/ending a real Langfuse observation
    failed — every call on it is a no-op, so the wrapped LLM call above
    never has to branch on whether tracing itself is working."""

    def update(self, *args: Any, **kwargs: Any) -> _NoopObservation:
        return self

    def end(self, *args: Any, **kwargs: Any) -> _NoopObservation:
        return self


def configure_sentry() -> None:
    """No-op without a DSN — called once at app startup
    (app.web.main.create_app)."""
    if not settings.sentry_dsn:
        return
    import sentry_sdk

    sentry_sdk.init(dsn=settings.sentry_dsn, environment=settings.app_env)
