import time
from functools import wraps
from core.logger import logger


class LatencyTracker:
    def __init__(self):
        self._samples: dict[str, list[float]] = {}

    def record(self, name: str, ms: float) -> None:
        self._samples.setdefault(name, []).append(ms)
        if len(self._samples[name]) > 1000:
            self._samples[name] = self._samples[name][-500:]

    def avg(self, name: str) -> float:
        samples = self._samples.get(name, [])
        return sum(samples) / len(samples) if samples else 0.0

    def report(self) -> dict[str, float]:
        return {k: self.avg(k) for k in self._samples}


_tracker = LatencyTracker()


def measure(name: str):
    """Decorator to measure and log sync function latency in ms."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            start = time.perf_counter()
            result = func(*args, **kwargs)
            ms = (time.perf_counter() - start) * 1000
            _tracker.record(name, ms)
            if ms > 500:
                logger.warning(f"[latency] {name} took {ms:.1f} ms")
            return result
        return wrapper
    return decorator


def async_measure(name: str):
    """Decorator to measure and log async function latency in ms."""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            import asyncio
            start = time.perf_counter()
            result = await func(*args, **kwargs)
            ms = (time.perf_counter() - start) * 1000
            _tracker.record(name, ms)
            if ms > 500:
                logger.warning(f"[latency] {name} took {ms:.1f} ms")
            return result
        return wrapper
    return decorator


def get_latency_report() -> dict[str, float]:
    return _tracker.report()
