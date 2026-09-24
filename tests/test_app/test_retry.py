import pytest

from app.retry import RetriesExhaustedError, call_with_retry


class RetryableError(Exception):
    pass


class NonRetryableError(Exception):
    pass


def test_succeeds_without_retry_when_first_call_works():
    calls = []

    def fn():
        calls.append(1)
        return "ok"

    result = call_with_retry(fn, is_retryable=lambda e: True, sleep=lambda s: None)
    assert result == "ok"
    assert len(calls) == 1


def test_retries_then_succeeds_within_max_attempts():
    calls = []

    def fn():
        calls.append(1)
        if len(calls) < 3:
            raise RetryableError("flaky")
        return "ok"

    result = call_with_retry(
        fn, is_retryable=lambda e: isinstance(e, RetryableError),
        max_attempts=5, sleep=lambda s: None,
    )
    assert result == "ok"
    assert len(calls) == 3


def test_non_retryable_exception_fails_immediately():
    calls = []

    def fn():
        calls.append(1)
        raise NonRetryableError("do not retry this")

    with pytest.raises(NonRetryableError):
        call_with_retry(
            fn, is_retryable=lambda e: isinstance(e, RetryableError),
            max_attempts=5, sleep=lambda s: None,
        )
    assert len(calls) == 1  # never retried


def test_exhausting_all_attempts_raises_retries_exhausted():
    calls = []

    def fn():
        calls.append(1)
        raise RetryableError("always fails")

    with pytest.raises(RetriesExhaustedError) as exc_info:
        call_with_retry(
            fn, is_retryable=lambda e: True,
            max_attempts=3, sleep=lambda s: None,
        )
    assert len(calls) == 3
    assert exc_info.value.attempts == 3
    assert isinstance(exc_info.value.last_exception, RetryableError)


def test_backoff_grows_and_is_bounded_by_max_delay():
    delays = []

    def fn():
        raise RetryableError("x")

    with pytest.raises(RetriesExhaustedError):
        call_with_retry(
            fn, is_retryable=lambda e: True, max_attempts=4,
            base_delay_s=1.0, max_delay_s=2.5,
            sleep=lambda s: delays.append(s),
            rand=lambda: 1.0,  # no jitter — makes the growth deterministic to assert on
        )
    # base*2**0, base*2**1, base*2**2 capped at max_delay_s -> 1.0, 2.0, 2.5
    assert delays == [1.0, 2.0, 2.5]
