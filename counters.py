import logging
from functools import wraps
from os import getenv
from typing import Any, Callable, Dict

# Use the redis cache to hold the counts.
from cache import cache

logger = logging.getLogger(getenv("LOGGER_NAME", __name__))


def create_counter_key(func_name: str, *args, **kwargs) -> str:
    """Create cache keys based on the main methods that will be counted."""
    return {
        "get_calendar": f"{kwargs['team'].name}-{kwargs['calendar_type'].name}-CAL",
        "get_next_game": f"{kwargs['team'].name}-{kwargs['calendar_type'].name}-NEXT",
        "get_last_game": f"{kwargs['team'].name}-{kwargs['calendar_type'].name}-LAST",
    }.get(func_name, f"{func_name} ({args}, {kwargs})")


def count_this(func) -> Callable[[Any], Any]:
    """Decorator to count how many times a method is called."""

    @wraps(func)
    async def wrapper(*args, **kwargs):
        logger.info("Counting call for '%s'", f"{func.__name__} ({args}, {kwargs})")
        counter = create_counter_key(func.__name__, *args, **kwargs)
        # Keeps counters for 3 categories of request:
        #   1. request type (next/last/calendar) + calendar type (full/home/away) + team
        #   2. calendar type (full/home/away) + team
        #   3. team
        # Since the number of teams is limited, the memory footprint is not significant
        # compared to the speedup when creating the homepage of the application.
        cache.set_field_incr(key="request_counts", field=counter)
        cache.set_field_incr(key="request_counts", field=counter[: len("???-????")])
        cache.set_field_incr(key="request_counts", field=counter[: len("???")])
        return await func(*args, **kwargs)

    return wrapper


def get_team_calendar_counts() -> Dict[str, str]:
    """Retrieve the counts stored in the database; counts are strings due to redis implementation."""
    return cache.get_set("request_counts")
