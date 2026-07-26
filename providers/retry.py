"""Shared provider retry policy."""


def retry_delay(attempt: int) -> float:
    """Exponential backoff in seconds for a zero-based attempt index."""
    return float(2 ** max(0, attempt))


def is_retryable_status(status_code: int) -> bool:
    return status_code == 429 or status_code >= 500
