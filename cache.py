import logging
from datetime import datetime, timedelta, timezone
from os import getenv
from typing import Any, Callable, Optional

from pydantic import BaseModel
from upstash_redis import Redis

from utils import UPDATE_FREQ

logger = logging.getLogger(getenv("LOGGER_NAME", __name__))


class CacheEntry(BaseModel):
    """Holds the cached version of an NHL API response."""

    timestamp: datetime
    data: Any


class RedisCache:
    """Manages the connection to our redis cache."""

    def __init__(self) -> None:
        self._db = Redis(
            url=getenv("REDIS_URL", "XxYyZz"),
            token=getenv("REDIS_TOKEN", "XxYyZz"),
        )

    def set(self, key: str, data: Any) -> None:
        """Store the given data in the cache."""
        self._db.set(
            key,
            CacheEntry(
                timestamp=datetime.now(timezone.utc), data=data
            ).model_dump_json(),
        )

    def get(self, key: str) -> Optional[CacheEntry]:
        """Return the stored value for the key."""
        cached_json = self._db.get(key)
        if cached_json:
            return CacheEntry.model_validate_json(cached_json)
        return None


# Create a connection to our redis database.
cache: RedisCache = RedisCache()


def cache_this(func) -> Callable[[Any], Any]:
    """Decorator to cache method results."""

    freshness: timedelta = UPDATE_FREQ

    async def wrapper(*args, **kwargs):
        key = f"{func.__name__} ({args}, {kwargs})"
        logger.warning("Checking cache for '%s'", key)
        # Check if this method call has been cached.
        entry = cache.get(key)
        if entry:
            # Calculate how long this entry has been stored.
            entry_age = datetime.now(timezone.utc) - entry.timestamp
            logger.warning(
                "Cache entry found for '%s' (cached on %s); entry's age is %s",
                key,
                entry.timestamp.isoformat(),
                entry_age,
            )

            # Check if the cache entry is still fresh.
            if freshness >= entry_age:
                # If it is, return the stored result.
                logger.warning("Cache entry is fresh for '%s'; returning it.", key)
                return entry.data

        # If there is no fresh cache entry, call the function to get a new result.
        logger.warning("No fresh cache entry for '%s'; calling original function.", key)
        try:
            new_result = await func(*args, **kwargs)

        except Exception as e:
            logger.exception("Error calling original function ('%s'): %s", key, e)

            if entry:
                logger.warning("Returning non-fresh cache entry for '%s'", key)
                return entry.data

            else:
                logger.error("No entry exists for '%s', passing exception along.", key)
                raise e

        # Cache the new result and return it.
        cache.set(key, new_result)
        logger.warning("Updated cache with new results for '%s'.", key)
        return new_result

    return wrapper
