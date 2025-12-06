"""
Retry utilities with exponential backoff for external service calls.

Usage:
    from services.retry import with_retry, RetryConfig

    @with_retry(max_retries=3, base_delay=1.0)
    def call_external_api():
        ...
"""

import logging
import random
import time
from functools import wraps
from typing import Callable, Type, Tuple, Optional

logger = logging.getLogger(__name__)


class RetryConfig:
    """Configuration for retry behavior."""
    
    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 30.0,
        exponential_base: float = 2.0,
        jitter: bool = True,
        retryable_exceptions: Tuple[Type[Exception], ...] = (Exception,),
    ):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.jitter = jitter
        self.retryable_exceptions = retryable_exceptions


def calculate_delay(
    attempt: int,
    base_delay: float,
    max_delay: float,
    exponential_base: float,
    jitter: bool,
) -> float:
    """Calculate delay with exponential backoff and optional jitter."""
    delay = min(base_delay * (exponential_base ** attempt), max_delay)
    if jitter:
        delay = delay * (0.5 + random.random())
    return delay


def with_retry(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    exponential_base: float = 2.0,
    jitter: bool = True,
    retryable_exceptions: Tuple[Type[Exception], ...] = (Exception,),
    on_retry: Optional[Callable[[Exception, int], None]] = None,
):
    """
    Decorator for retrying functions with exponential backoff.
    
    Args:
        max_retries: Maximum number of retry attempts
        base_delay: Initial delay in seconds
        max_delay: Maximum delay cap in seconds
        exponential_base: Base for exponential calculation
        jitter: Add randomness to prevent thundering herd
        retryable_exceptions: Tuple of exception types to retry on
        on_retry: Optional callback called on each retry (exception, attempt)
    
    Example:
        @with_retry(max_retries=3, base_delay=1.0)
        def fetch_data():
            response = requests.get(url)
            response.raise_for_status()
            return response.json()
    """
    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except retryable_exceptions as e:
                    last_exception = e
                    
                    if attempt == max_retries:
                        logger.error(
                            "Failed after %d retries: %s.%s - %s",
                            max_retries,
                            func.__module__,
                            func.__name__,
                            str(e),
                        )
                        raise
                    
                    delay = calculate_delay(
                        attempt, base_delay, max_delay, exponential_base, jitter
                    )
                    
                    logger.warning(
                        "Retry %d/%d for %s.%s after %.2fs - %s",
                        attempt + 1,
                        max_retries,
                        func.__module__,
                        func.__name__,
                        delay,
                        str(e),
                    )
                    
                    if on_retry:
                        on_retry(e, attempt + 1)
                    
                    time.sleep(delay)
            
            # Should not reach here, but just in case
            if last_exception:
                raise last_exception
                
        return wrapper
    return decorator


# Pre-configured retry decorators for common use cases
def retry_on_network_error(func: Callable) -> Callable:
    """Retry decorator for network-related errors."""
    import requests
    return with_retry(
        max_retries=3,
        base_delay=1.0,
        retryable_exceptions=(
            requests.exceptions.ConnectionError,
            requests.exceptions.Timeout,
            requests.exceptions.HTTPError,
        ),
    )(func)


def retry_on_transient_error(func: Callable) -> Callable:
    """Retry decorator for transient errors with longer delays."""
    return with_retry(
        max_retries=5,
        base_delay=2.0,
        max_delay=60.0,
    )(func)
