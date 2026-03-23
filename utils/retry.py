"""
retry.py — Retry with exponential backoff for network operations.

Usage:
    from utils.retry import retry_with_backoff

    @retry_with_backoff(max_retries=3, base_delay=1.0)
    def fetch_orders():
        return requests.get("https://api.example.com/orders")

    # Or use directly:
    result = retry_with_backoff(max_retries=3)(lambda: requests.get(url))()
"""

import functools
import logging
import random
import time
from typing import Callable, Optional, Tuple, Type

logger = logging.getLogger(__name__)

DEFAULT_RETRYABLE_EXCEPTIONS: Tuple[Type[Exception], ...] = (
    ConnectionError,
    TimeoutError,
    OSError,
)

try:
    import requests
    DEFAULT_RETRYABLE_EXCEPTIONS = DEFAULT_RETRYABLE_EXCEPTIONS + (
        requests.ConnectionError,
        requests.Timeout,
        requests.HTTPError,
    )
except ImportError:
    pass


def retry_with_backoff(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    jitter: bool = True,
    retryable_exceptions: Optional[Tuple[Type[Exception], ...]] = None,
):
    """
    Decorator that retries a function with exponential backoff.

    Args:
        max_retries: Maximum number of retry attempts.
        base_delay: Initial delay in seconds before first retry.
        max_delay: Maximum delay in seconds between retries.
        exponential_base: Base for exponential increase.
        jitter: Add random jitter to prevent thundering herd.
        retryable_exceptions: Tuple of exception types to retry on.
            Defaults to common network errors.
    """
    if retryable_exceptions is None:
        retryable_exceptions = DEFAULT_RETRYABLE_EXCEPTIONS

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None

            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except retryable_exceptions as e:
                    last_exception = e

                    if attempt == max_retries:
                        logger.error(
                            f"{func.__name__} failed after {max_retries + 1} attempts: {e}"
                        )
                        raise

                    delay = min(base_delay * (exponential_base ** attempt), max_delay)
                    if jitter:
                        delay = delay * (0.5 + random.random())

                    logger.warning(
                        f"{func.__name__} attempt {attempt + 1}/{max_retries + 1} failed: {e}. "
                        f"Retrying in {delay:.1f}s..."
                    )
                    time.sleep(delay)

            raise last_exception

        return wrapper
    return decorator


def retry_call(
    func: Callable,
    args: tuple = (),
    kwargs: dict = None,
    max_retries: int = 3,
    base_delay: float = 1.0,
    retryable_exceptions: Optional[Tuple[Type[Exception], ...]] = None,
):
    """
    Call a function with retry logic (non-decorator version).

    Args:
        func: Function to call.
        args: Positional arguments.
        kwargs: Keyword arguments.
        max_retries: Maximum retry attempts.
        base_delay: Initial delay in seconds.
        retryable_exceptions: Exception types to retry on.

    Returns:
        The return value of the function.
    """
    if kwargs is None:
        kwargs = {}

    @retry_with_backoff(
        max_retries=max_retries,
        base_delay=base_delay,
        retryable_exceptions=retryable_exceptions,
    )
    def _call():
        return func(*args, **kwargs)

    return _call()
