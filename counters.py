import logging
from typing import Any, Callable, Dict
from functools import wraps
from collections import defaultdict
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


def get_team_calendar_counts() -> defaultdict[str, int]:
    """Parse the counts of each team/type calendar from the database."""
    counts: defaultdict[str, int] = defaultdict(int)
    # Get all counts that match the pattern of a team-type count.
    for k, v in cache.get_raw_values("\[COUNT\] ???-????-*").items():
        try:
            # Convert the count into a number so we can use it.
            new_count = int(v)
            # Keep track of each team-type's count separately.
            counts[k[8:16]] = new_count
            # But also accumulate it into a team's total count.
            counts[k[8:12] + "TOTAL"] += new_count
        except ValueError:
            # We don't expect value errors since we're filtering by count keys, but no harm in checking.
            # Also, since we're using a defaultdict, a count of 0 is already implied in case of error.
            continue
    return counts
