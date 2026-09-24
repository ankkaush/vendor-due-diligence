"""Generic bounded retry with exponential backoff and jitter.

architecture.md's "Retries, Idempotency, Concurrency" section: retryable
failures get backoff + jitter up to a max attempt count; non-retryable
failures fail immediately. Built now, in Phase 5, because it needs no
external I/O to write or test correctly — but its real customer is
Phase 6+'s LLM calls, which is why callers classify retryability
themselves (`is_retryable`) rather than this module guessing based on
exception type it can't know about yet.
"""

import random
import time
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")


class RetriesExhaustedError(Exception):
    """Raised when every attempt failed and none were left. Wraps the
    last underlying exception so the real cause isn't lost."""

    def __init__(self, attempts: int, last_exception: Exception):
        super().__init__(f"failed after {attempts} attempt(s): {last_exception!r}")
        self.attempts = attempts
        self.last_exception = last_exception


def call_with_retry(
    fn: Callable[[], T],
    *,
    is_retryable: Callable[[Exception], bool],
    max_attempts: int = 3,
    base_delay_s: float = 1.0,
    max_delay_s: float = 30.0,
    sleep: Callable[[float], None] = time.sleep,
    rand: Callable[[], float] = random.random,
) -> T:
    """Call fn(), retrying on exceptions `is_retryable` accepts.

    Backoff is base_delay_s * 2**attempt, capped at max_delay_s, plus full
    jitter (a random fraction of that value) so many concurrent callers
    don't retry in lockstep. `sleep`/`rand` are injectable purely so tests
    can run the full max_attempts path without actually waiting seconds or
    depending on real randomness.
    """
    if max_attempts < 1:
        raise ValueError("max_attempts must be >= 1")

    last_exception: Exception | None = None
    for attempt in range(max_attempts):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 — deliberately broad; retryability is the caller's call
            last_exception = exc
            if not is_retryable(exc):
                raise
            if attempt == max_attempts - 1:
                break
            delay = min(base_delay_s * (2**attempt), max_delay_s) * rand()
            sleep(delay)

    raise RetriesExhaustedError(max_attempts, last_exception)
