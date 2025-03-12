import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, Optional

from pydantic import BaseModel

from utils import UPDATE_FREQ

logger = logging.getLogger(__name__)


class CacheEntry(BaseModel):
    """Holds the cached version of an NHL API response."""

    timestamp: datetime
    data: Any


class DictCache:
    """Class that acts as an in-memory cache."""

    def __init__(self) -> None:
        self._db: Dict[str, CacheEntry] = {}

    def set(self, key: str, data: Any) -> None:
        """Store the given data in the cache."""
        self._db[key] = CacheEntry(timestamp=datetime.now(timezone.utc), data=data)

    def get(self, key: str) -> Optional[CacheEntry]:
        """Return the stored value for the key."""
        return self._db.get(key)


def cache_this(func) -> Callable[[Any], Any]:
    """Decorator to cache method results."""

    cache: DictCache = DictCache()
    freshness: timedelta = UPDATE_FREQ

    async def wrapper(*args, **kwargs):
        key = (func.__name__, f"{args}", f"{kwargs}")
        logger.info("Checking cache for '%s'", key)
        # Check if this method call has been cached.
        entry = cache.get(key)
        if entry:
            logger.info("Cache entry found for '%s'", key)
            # Check if the cache entry is still fresh.
            if freshness >= (datetime.now(timezone.utc) - entry.timestamp):
                # If it is, return the old result.
                logger.info(
                    "Cache entry is fresh for '%s' (cached on %s); returning it.",
                    key,
                    entry.timestamp.isoformat(),
                )
                return entry.data

        # If there is no fresh cache entry, call the function to get a new result.
        logger.info("No fresh cache entry for '%s'; calling original function.", key)
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
        logger.info("Updated cache with new results for '%s'.", key)
        return new_result

    return wrapper
