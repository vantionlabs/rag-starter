"""Fast-lane tests for retry backoff (no broker, no DB)."""

from app.worker.retry import backoff_seconds


# --- retry backoff ---
def test_backoff_is_exponential():
    b = backoff_seconds
    # base=10 by default: 10, 20, 40, 80, ...
    assert b(1) == 10
    assert b(2) == 20
    assert b(3) == 40


def test_backoff_is_capped():
    assert backoff_seconds(50) <= 600  # event_retry_max_delay_seconds


def test_backoff_never_negative():
    assert backoff_seconds(0) >= 0
