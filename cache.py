import logging
from datetime import datetime, timedelta, timezone
from os import getenv
from typing import Any, Callable, Dict, List, Optional

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
            url=getenv("REDIS_URL", "http://localhost:8079"),
            token=getenv("REDIS_TOKEN", "example_token"),
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

    def get_raw_values(self, key_pattern: str) -> Dict[Any, Any]:
        """Return values for keys that match the given pattern without processing/validating."""
        # Finds all keys that match the pattern.
        keys_found: List[str] = []
        cursor = 0
        while True:
            cursor, keys = self._db.scan(cursor, match=key_pattern)
            keys_found.extend(keys)
            if cursor == 0:
                # no more keys to find
                break
        # Get the value for each key we found.
        return {k: self._db.get(k) for k in keys_found}

    def incr(self, key: str) -> int:
        """Increase and return the count for specified key."""
        return self._db.incr(key)

    def set_field_incr(self, key: str, field: str, increment: int = 1) -> int:
        """Increase and return the value of field inside the key set by increment."""
        return self._db.hincrby(key, field, increment)

    def get_set(self, key: str) -> Dict:
        """Return all field/value pairs in the key set."""
        return self._db.hgetall(key)


# Create a connection to our redis database.
cache: RedisCache = RedisCache()


def cache_this(store_transform=(lambda x: x), load_transform=(lambda x: x)):
    """Create a decorator that can transform the result before/after db operations."""

    def cache_decorator(func) -> Callable[[Any], Any]:
        """Real decorator to cache method results."""

        freshness: timedelta = UPDATE_FREQ

        async def wrapper(*args, **kwargs):
            key = f"[RESULT] {func.__name__} ({args}, {kwargs})"
            logger.info("Checking cache for '%s'", key)
            # Check if this method call has been cached.
            entry = cache.get(key)
            if entry:
                # Calculate how long this entry has been stored.
                entry_age = datetime.now(timezone.utc) - entry.timestamp
                logger.info(
                    "Cache entry found for '%s' (cached on %s); entry's age is %s",
                    key,
                    entry.timestamp.isoformat(),
                    entry_age,
                )

                # Check if the cache entry is still fresh.
                if freshness >= entry_age:
                    # If it is, return the stored result.
                    logger.info("Cache entry is fresh for '%s'; returning it.", key)
                    return load_transform(entry.data)

            # If there is no fresh cache entry, call the function to get a new result.
            logger.info(
                "No fresh cache entry for '%s'; calling original function.", key
            )
            try:
                new_result = await func(*args, **kwargs)

            except Exception as e:
                logger.exception("Error calling original function ('%s'): %s", key, e)

                if entry:
                    logger.info("Returning non-fresh cache entry for '%s'", key)
                    return entry.data

                else:
                    logger.error(
                        "No entry exists for '%s', passing exception along.", key
                    )
                    raise e

            # Cache the new result and return it.
            cache.set(key, store_transform(new_result))
            logger.info("Updated cache with new results for '%s'.", key)
            return new_result

        return wrapper

    return cache_decorator
