"""
Cache service for managing application-level caching.

Provides centralized cache key management and TTL configuration
for frequently accessed data: GlobalSettings, Diet, daily stats, the admin
celok/prevádzka list and the gramage dashboard.

Includes fallback handling for Redis timeouts/connection failures to prevent
cache errors from crashing the application.
"""

import logging
from typing import Any, Optional

from django.core.cache import cache

logger = logging.getLogger(__name__)

# Cache key constants
GLOBAL_SETTINGS_CACHE_KEY = "global_settings"
DIET_LIST_CACHE_KEY = "diet_list"
DAILY_STATS_CACHE_KEY_PREFIX = "daily_stats"
ADMIN_CELOK_LIST_CACHE_KEY = "admin_celok_list"
GRAMAGE_DASHBOARD_CACHE_KEY_PREFIX = "gramage_dashboard"
CLOSED_DAY_PDF_CACHE_KEY_PREFIX = "closed_day_pdf"

# Cache timeout (TTL) constants in seconds
GLOBAL_SETTINGS_TIMEOUT = 3600  # 1 hour
DIET_LIST_TIMEOUT = 86400  # 24 hours (static data)
DAILY_STATS_TIMEOUT = 300  # 5 minutes
# Invalidated explicitly via signals on write (see api/signals.py), so the TTL
# here is only a poistka for writes that bypass the ORM (e.g. bulk_update).
ADMIN_CELOK_LIST_TIMEOUT = 3600  # 1 hour
# Ad-hoc order edits don't invalidate this (same tradeoff as daily stats) —
# too frequent to track per-write, so the TTL bounds that staleness. The bulk
# write points (day close, deadline auto-orders, EduPage scrape) do invalidate
# explicitly via clear_gramage_dashboard_cache().
GRAMAGE_DASHBOARD_TIMEOUT = 300  # 5 minutes
# Predgenerované PDF snapshot uzavretého dňa (#528). Objednávky uzavretého
# dňa sa už nedajú meniť, takže na rozdiel od GRAMAGE_DASHBOARD_TIMEOUT tu
# TTL nerieši čerstvosť dát — je to len horná hranica; skutočné zneplatnenie
# rieši `clear_closed_day_pdf_cache()` volaná pri odomknutí dňa.
CLOSED_DAY_PDF_TIMEOUT = 48 * 3600  # 48 hodín


def get_global_settings_cache_key() -> str:
    """Return the cache key for GlobalSettings."""
    return GLOBAL_SETTINGS_CACHE_KEY


def get_diet_list_cache_key() -> str:
    """Return the cache key for Diet list."""
    return DIET_LIST_CACHE_KEY


def get_daily_stats_cache_key(date_str: str) -> str:
    """Return the cache key for daily stats by date (YYYY-MM-DD format)."""
    return f"{DAILY_STATS_CACHE_KEY_PREFIX}:{date_str}"


def get_admin_celok_list_cache_key() -> str:
    """Return the cache key for the unfiltered admin celok/prevádzka list.

    Only the unfiltered (no ``?search=``) response is cached — that's the
    payload `FacilityManager.tsx` fetches on every page load (it filters
    client-side), so this key covers the common case.
    """
    return ADMIN_CELOK_LIST_CACHE_KEY


def get_gramage_dashboard_cache_key(date_str: str) -> str:
    """Return the cache key for the gramage dashboard by date (YYYY-MM-DD)."""
    return f"{GRAMAGE_DASHBOARD_CACHE_KEY_PREFIX}:{date_str}"


def get_closed_day_pdf_cache_key(date_str: str) -> str:
    """Return the cache key for a closed day's pre-rendered PDF snapshot (YYYY-MM-DD)."""
    return f"{CLOSED_DAY_PDF_CACHE_KEY_PREFIX}:{date_str}"


def get_cached(key: str) -> Optional[Any]:
    """
    Retrieve a value from cache with graceful fallback on connection errors.

    If Redis is unavailable or times out, returns None instead of raising an
    exception. This prevents cache errors from crashing the application.

    Args:
        key: The cache key.

    Returns:
        The cached value, None if not found or on connection error.
    """
    try:
        return cache.get(key)
    except Exception as exc:
        # Log Redis connection/timeout errors but don't crash
        logger.warning(
            "Cache get failed for key '%s': %s (%s). Falling back to None.",
            key,
            exc.__class__.__name__,
            exc,
        )
        return None


def set_cached(key: str, value: Any, timeout: Optional[int] = None) -> None:
    """
    Set a value in cache with graceful fallback on connection errors.

    If Redis is unavailable or times out, logs the error but continues
    without caching. This prevents cache errors from crashing the application.

    Args:
        key: The cache key.
        value: The value to cache.
        timeout: TTL in seconds. If None, uses cache backend's default.
    """
    try:
        # Pass timeout as-is; Django will use backend default if None
        cache.set(key, value, timeout=timeout)
    except Exception as exc:
        # Log Redis connection/timeout errors but don't crash
        logger.warning(
            "Cache set failed for key '%s': %s (%s). Data will not be cached.",
            key,
            exc.__class__.__name__,
            exc,
        )


def delete_cached(key: str) -> None:
    """
    Delete a value from cache with graceful fallback on connection errors.

    If Redis is unavailable, logs the error but continues.

    Args:
        key: The cache key.
    """
    try:
        cache.delete(key)
    except Exception as exc:
        # Log but continue – cache delete failures shouldn't crash the app
        logger.warning(
            "Cache delete failed for key '%s': %s (%s)",
            key,
            exc.__class__.__name__,
            exc,
        )


def clear_global_settings_cache() -> None:
    """Clear the GlobalSettings cache."""
    delete_cached(get_global_settings_cache_key())


def clear_diet_list_cache() -> None:
    """Clear the Diet list cache, including keys from older paginated releases."""
    base_key = get_diet_list_cache_key()

    # django-redis supports wildcard invalidation via delete_pattern.
    # Use it when available so keys like diet_list:page=1 are all removed.
    try:
        if hasattr(cache, "delete_pattern"):
            cache.delete_pattern(f"{base_key}*")
            return
    except Exception as exc:
        logger.warning(
            "Cache delete_pattern failed for key prefix '%s*': %s (%s)",
            base_key,
            exc.__class__.__name__,
            exc,
        )

    # Backend-agnostic fallback: clear known keys.
    # (Safe fallback when wildcard delete is unsupported.)
    delete_cached(base_key)
    delete_cached(f"{base_key}:page=1")


def clear_admin_celok_list_cache() -> None:
    """Clear the cached admin celok/prevádzka list.

    Called from signal handlers whenever a model that feeds
    `AdminCelokViewSet.get_queryset()` changes (Celok, Prevádzka, prístupy,
    loginy/profily, aktívne reset tokeny).
    """
    delete_cached(get_admin_celok_list_cache_key())


def clear_daily_stats_cache(date_str: Optional[str] = None) -> None:
    """
    Clear the daily stats cache for a specific date.

    Args:
        date_str: Specific date (YYYY-MM-DD). If None, no action is taken.
    """
    if date_str:
        delete_cached(get_daily_stats_cache_key(date_str))
    else:
        # Global deletion of all daily stats keys is not implemented here because
        # the Django cache API does not support wildcard deletion in a backend-
        # agnostic way. Callers should explicitly clear known date keys instead.
        pass


def clear_gramage_dashboard_cache(date_str: str) -> None:
    """Clear the cached gramage dashboard data for a specific date.

    Called from the write points that make the 5-minute TTL not good enough
    on its own: closing a day (`ClosedDayViewSet.create`, ktorá si hneď potom
    dopredu vyrenderuje PDF a bez tohto by ho postavila na starých dátach),
    auto-objednávky po deadline (`apply_auto_orders_task`) a EduPage scrape
    (`scrape_edupage_orders_task`).
    """
    delete_cached(get_gramage_dashboard_cache_key(date_str))


GRAMAGE_DASHBOARD_REFRESH_DEBOUNCE_SECONDS = 3
GRAMAGE_DASHBOARD_REFRESH_LOCK_PREFIX = "gramage_dashboard_refresh_lock"


def schedule_gramage_dashboard_refresh(date_str: str) -> None:
    """Asynchrónne prepočíta a nacachuje gramage dashboard pre daný deň.

    Nahrádza čisté `clear_gramage_dashboard_cache` tam, kde vieme presne, ktorý
    deň sa zmenil (`DailyOrder` save/delete) — namiesto toho, aby ďalší admin,
    ktorý si tabuľku otvorí, čakal na synchrónny prepočet, ho spustí Celery
    task (`refresh_gramage_dashboard_cache_task`) na pozadí a dashboard má
    novú verziu už nacachovanú skôr, než si ju niekto vôbec vypýta.

    Debounce cez `cache.add()` lock (TTL = `GRAMAGE_DASHBOARD_REFRESH_DEBOUNCE_SECONDS`)
    — séria rýchlych editov toho istého dňa (typicky viac riadkov v jednej
    EduPage scrape dávke) tak spustí jeden prepočet namiesto jedného za každý
    zápis, ktorý by inak zbytočne zaťažoval worker rovnakou drahou agregáciou.
    """
    lock_key = f"{GRAMAGE_DASHBOARD_REFRESH_LOCK_PREFIX}:{date_str}"
    try:
        lock_acquired = cache.add(
            lock_key, 1, timeout=GRAMAGE_DASHBOARD_REFRESH_DEBOUNCE_SECONDS
        )
    except Exception as exc:
        logger.warning(
            "Cache add failed for gramage refresh lock '%s': %s (%s)",
            lock_key,
            exc.__class__.__name__,
            exc,
        )
        return
    if not lock_acquired:
        return  # Prepočet pre tento deň je už naplánovaný.

    from api.tasks import refresh_gramage_dashboard_cache_task

    refresh_gramage_dashboard_cache_task.apply_async(
        args=[date_str], countdown=GRAMAGE_DASHBOARD_REFRESH_DEBOUNCE_SECONDS
    )


def clear_gramage_dashboard_cache_all() -> None:
    """Clear cached gramage dashboard data for every date (wildcard).

    `clear_gramage_dashboard_cache()` needs to know which date to drop — fine
    for the write points above, but a `Prevadzka` field edit (napr. pencil
    poznámka alebo Nastavenia prevádzky, #573) affects whatever date the admin
    has open, not one we know here. Rather than plumb a date through the whole
    admin CRUD path, drop every cached date the same way `clear_diet_list_cache`
    does — cheap (a handful of keys at most) and it's the only way the note
    actually shows up immediately instead of within the 5-minute TTL.
    """
    try:
        if hasattr(cache, "delete_pattern"):
            cache.delete_pattern(f"{GRAMAGE_DASHBOARD_CACHE_KEY_PREFIX}:*")
            return
    except Exception as exc:
        logger.warning(
            "Cache delete_pattern failed for key prefix '%s:*': %s (%s)",
            GRAMAGE_DASHBOARD_CACHE_KEY_PREFIX,
            exc.__class__.__name__,
            exc,
        )
    # Backend bez delete_pattern (napr. LocMemCache v testoch) — bez wildcard
    # zmazania ostáva len 5-minútové TTL ako poistka, rovnako ako predtým.


def clear_closed_day_pdf_cache(date_str: str) -> None:
    """Clear the pre-rendered PDF snapshot cached for a closed day.

    Called when the day is unlocked (`ClosedDayViewSet.unlock`) — the "48h
    alebo dokým sa neodomkne" tradeoff from #528, since orders become
    editable again and the cached PDF would otherwise outlive its validity.
    """
    delete_cached(get_closed_day_pdf_cache_key(date_str))


def get_cache_stats() -> dict:
    """
    Get cache hit/miss statistics and metrics (Redis only).

    Returns:
        Dictionary with cache statistics, or empty dict if Redis is unavailable.

    Works with both django-redis and Django's built-in RedisCache backends.
    """
    try:
        redis_client = None

        # Try django-redis: cache.client.get_client()
        client = getattr(cache, "client", None)
        if client is not None and hasattr(client, "get_client"):
            redis_client = client.get_client()
        # For Django's built-in RedisCache, cache.client may be a redis client
        elif client is not None and hasattr(client, "info"):
            redis_client = client
        # Some backends may expose get_client() directly on the cache
        elif hasattr(cache, "get_client"):
            redis_client = cache.get_client()  # type: ignore[call-arg]
        # As last resort, treat the cache itself as a redis client if it has info()
        elif hasattr(cache, "info"):
            redis_client = cache  # type: ignore[assignment]

        if redis_client is None or not hasattr(redis_client, "info"):
            # Not a Redis cache or unsupported backend
            return {}

        info = redis_client.info()
        return {
            "connected": True,
            "memory_used_mb": info.get("used_memory", 0) / (1024 * 1024),
            "connected_clients": info.get("connected_clients", 0),
            "total_commands_processed": info.get("total_commands_processed", 0),
        }
    except Exception:  # noqa: BLE001
        # Redis unavailable or unexpected backend behavior
        pass
    return {}
