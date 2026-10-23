"""Global error handling and safety decorators.

Why this file exists:
Enforces a global error contract (Section 3.C) across bot handlers so unhandled exceptions
never crash the server silently, emit tracebacks in logs, update failure metrics in metrics.json,
and provide graceful fallback messaging to users.
"""
import functools
import inspect
import json
import logging
from pathlib import Path
from typing import Callable, Any, Optional

logger = logging.getLogger(__name__)
METRICS_PATH = Path("metrics.json")


def increment_metric(metric_name: str, count: int = 1) -> int:
    """Increment an error or event counter stored in metrics.json.

    Why: Gives a lightweight, serverless metrics store to monitor error frequencies
    and stability without needing external observability infrastructure.
    """
    data = {}
    try:
        if METRICS_PATH.exists():
            with open(METRICS_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
        data[metric_name] = data.get(metric_name, 0) + count
        with open(METRICS_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        return data[metric_name]
    except Exception as e:
        logger.warning(f"Could not record metric {metric_name} in {METRICS_PATH}: {e}")
        return 0


def safe_handler(fallback_message: str = "❌ Something went wrong. Please try again."):
    """Decorator to catch exceptions, log tracebacks, track metrics, and return a fallback message.

    Why: Prevents unexpected runtime errors from bubbling up unhandled or breaking
    user sessions while guaranteeing structured error logs.
    """
    def decorator(func: Callable):
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                logger.exception(f"Unhandled exception in async handler {func.__name__}: {e}")
                increment_metric(f"error_{func.__name__}")
                return fallback_message

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                logger.exception(f"Unhandled exception in sync handler {func.__name__}: {e}")
                increment_metric(f"error_{func.__name__}")
                return fallback_message

        return async_wrapper if inspect.iscoroutinefunction(func) else sync_wrapper
    return decorator
