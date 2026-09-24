"""Tests for app.observability (Phase 10): the redaction policy as a pure
function, TracedLLMClient's no-op behavior without credentials, and that
it correctly wraps/records against a fake Langfuse client — never the
real SDK, so these stay zero-cost and zero-network like every other
LLM-adjacent test in this repo (ADR-009).
"""

import pytest

from app.llm.client import ToolCallResult
from app.observability import TracedLLMClient, configure_sentry, redact_for_trace
from tests.fakes import FakeLLMClient


def test_redact_for_trace_truncates_and_hashes_the_full_text():
    text = "x" * 500
    redacted = redact_for_trace(text, max_chars=200)
    assert redacted.excerpt == "x" * 200
    assert redacted.full_length == 500
    assert len(redacted.sha256) == 64  # hex sha256


def test_redact_for_trace_never_exceeds_max_chars_even_for_short_text():
    redacted = redact_for_trace("short", max_chars=200)
    assert redacted.excerpt == "short"
    assert redacted.full_length == 5


class _FakeObservation:
    def __init__(self):
        self.updates: list[dict] = []
        self.ended = False

    def update(self, **kwargs):
        self.updates.append(kwargs)
        return self

    def end(self, **kwargs):
        self.ended = True
        return self


class _FakeLangfuse:
    def __init__(self):
        self.observations: list[_FakeObservation] = []
        self.start_observation_calls: list[dict] = []

    def start_observation(self, **kwargs):
        self.start_observation_calls.append(kwargs)
        obs = _FakeObservation()
        self.observations.append(obs)
        return obs


class _RaisingLangfuse:
    """Simulates a broken/misconfigured Langfuse SDK — every call raises."""

    def start_observation(self, **kwargs):
        raise RuntimeError("simulated Langfuse SDK failure")


RESPONSE = {"claims": [], "injection_detected": False, "injection_note": ""}


def test_traced_client_is_a_pure_passthrough_without_a_langfuse_client():
    """No LANGFUSE_PUBLIC_KEY/SECRET_KEY configured -> TracedLLMClient
    behaves identically to the inner client, no tracing attempted."""
    inner = FakeLLMClient(responses=[RESPONSE])
    traced = TracedLLMClient(inner, langfuse=None)
    result = traced.call_with_forced_tool(
        model="m", system="s", user_message="u", tool_name="t",
        tool_description="d", tool_input_schema={}, max_tokens=100,
    )
    assert result.tool_input == RESPONSE
    assert len(inner.calls) == 1


def test_traced_client_records_a_generation_with_redacted_input_and_usage():
    inner = FakeLLMClient(responses=[RESPONSE])
    fake_langfuse = _FakeLangfuse()
    traced = TracedLLMClient(inner, langfuse=fake_langfuse)

    long_document_text = "CONFIDENTIAL VENDOR DOCUMENT CONTENT " * 20  # > 200 chars
    result = traced.call_with_forced_tool(
        model="claude-haiku-4-5-20251001", system="SECRET SYSTEM PROMPT",
        user_message=long_document_text,
        tool_name="submit_verification_findings", tool_description="d",
        tool_input_schema={}, max_tokens=100,
    )

    assert result.tool_input == RESPONSE
    assert len(fake_langfuse.observations) == 1
    started = fake_langfuse.start_observation_calls[0]
    assert started["name"] == "submit_verification_findings"
    assert started["as_type"] == "generation"
    # Redacted, not the raw prompt — observability.md's redaction policy:
    # a bounded excerpt (never the full document), plus a hash and true
    # length for debugging without ever transmitting the full text.
    assert len(started["input"]["excerpt"]) <= 200
    assert started["input"]["full_length"] > 200
    assert len(started["input"]["sha256"]) == 64

    obs = fake_langfuse.observations[0]
    final_update = obs.updates[-1]
    assert final_update["usage_details"] == {"input": 100, "output": 50}
    assert obs.ended is True


def test_traced_client_correlates_to_a_trace_id_when_given_one():
    inner = FakeLLMClient(responses=[RESPONSE])
    fake_langfuse = _FakeLangfuse()
    traced = TracedLLMClient(inner, trace_id="case-123", langfuse=fake_langfuse)
    traced.call_with_forced_tool(
        model="m", system="s", user_message="u", tool_name="t",
        tool_description="d", tool_input_schema={}, max_tokens=100,
    )
    assert fake_langfuse.start_observation_calls[0]["trace_context"] == {
        "trace_id": "case-123",
    }


def test_traced_client_records_error_level_and_still_raises_on_failure():
    inner = FakeLLMClient(responses=[])  # no scripted response -> raises
    fake_langfuse = _FakeLangfuse()
    traced = TracedLLMClient(inner, langfuse=fake_langfuse)
    with pytest.raises(AssertionError):
        traced.call_with_forced_tool(
            model="m", system="s", user_message="u", tool_name="t",
            tool_description="d", tool_input_schema={}, max_tokens=100,
        )
    obs = fake_langfuse.observations[0]
    assert obs.updates[0]["level"] == "ERROR"
    assert obs.ended is True


def test_traced_client_never_lets_a_broken_langfuse_sdk_break_the_real_call():
    """Tracing must never break the traced operation — a Langfuse call
    that raises (network error, auth failure, version mismatch) is
    swallowed, and the real LLM call still succeeds and returns normally."""
    inner = FakeLLMClient(responses=[RESPONSE])
    traced = TracedLLMClient(inner, langfuse=_RaisingLangfuse())
    result = traced.call_with_forced_tool(
        model="m", system="s", user_message="u", tool_name="t",
        tool_description="d", tool_input_schema={}, max_tokens=100,
    )
    assert result.tool_input == RESPONSE


def test_configure_sentry_is_a_noop_without_a_dsn(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "sentry_dsn", "")
    configure_sentry()  # must not raise, must not require sentry_sdk to do anything


def test_traced_llm_client_result_is_a_real_tool_call_result():
    inner = FakeLLMClient(responses=[RESPONSE])
    traced = TracedLLMClient(inner, langfuse=None)
    result = traced.call_with_forced_tool(
        model="m", system="s", user_message="u", tool_name="t",
        tool_description="d", tool_input_schema={}, max_tokens=100,
    )
    assert isinstance(result, ToolCallResult)
