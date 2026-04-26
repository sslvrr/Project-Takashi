import asyncio
from functools import wraps
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)
from core.logger import logger


def with_retry(retries: int = 5, min_wait: float = 1.0, max_wait: float = 30.0):
    """Decorator — retry a sync function with exponential backoff."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exc = None
            for attempt in range(1, retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as exc:
                    last_exc = exc
                    wait = min(min_wait * (2 ** (attempt - 1)), max_wait)
                    logger.warning(f"[retry] {func.__name__} attempt {attempt}/{retries} failed: {exc}. Retrying in {wait:.1f}s")
                    import time
                    time.sleep(wait)
            raise last_exc
        return wrapper
    return decorator


def async_retry(retries: int = 5, min_wait: float = 1.0, max_wait: float = 30.0):
    """Decorator — retry an async function with exponential backoff."""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_exc = None
            for attempt in range(1, retries + 1):
                try:
                    return await func(*args, **kwargs)
                except Exception as exc:
                    last_exc = exc
                    wait = min(min_wait * (2 ** (attempt - 1)), max_wait)
                    logger.warning(f"[async_retry] {func.__name__} attempt {attempt}/{retries} failed: {exc}. Retrying in {wait:.1f}s")
                    await asyncio.sleep(wait)
            raise last_exc
        return wrapper
    return decorator
