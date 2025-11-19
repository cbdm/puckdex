import logging
from typing import Any, Callable
from functools import wraps
from os import getenv

# Use the redis cache to hold the counts.
from cache import cache

logger = logging.getLogger(getenv("LOGGER_NAME", __name__))


def create_counter_key(func_name: str, *args, **kwargs) -> str:
    """Create cache keys based on the main methods that will be counted."""
    return "[COUNT] " + {
        "get_calendar": f"{kwargs['team'].name}-{kwargs['calendar_type'].name}-CAL",
        "get_next_game": f"{kwargs['team'].name}-{kwargs['calendar_type'].name}-NEXT",
        "get_last_game": f"{kwargs['team'].name}-{kwargs['calendar_type'].name}-LAST",
    }.get(func_name, f"{func_name} ({args}, {kwargs})")


def count_this(func) -> Callable[[Any], Any]:
    """Decorator to count how many times a method is called."""

    @wraps(func)
    async def wrapper(*args, **kwargs):
        logger.info(f"Counting call for '{func.__name__} ({args}, {kwargs})'")
        key = create_counter_key(func.__name__, *args, **kwargs)
        cache.incr(key)
        return await func(*args, **kwargs)

    return wrapper
