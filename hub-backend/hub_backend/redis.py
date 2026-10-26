"""Redis client factory and fallback support."""

from __future__ import annotations

import redis.asyncio as aioredis
from hub_backend.config import get_settings
from hub_backend.logging_config import get_logger
from redis.asyncio import Redis

log = get_logger(__name__)

_redis_client: Redis | None = None


async def get_redis() -> Redis:
    """Get or initialize the async Redis client."""
    global _redis_client
    if _redis_client is not None:
        return _redis_client

    settings = get_settings()
    try:
        client: Redis = aioredis.from_url(  # type: ignore[no-untyped-call]
            settings.redis_url,
            decode_responses=True,
            socket_timeout=2.0,
            socket_connect_timeout=2.0,
        )
        # Test ping
        await client.ping()
        _redis_client = client
        return _redis_client
    except Exception as exc:
        log.warning("redis_connection_failed_falling_back_to_fakeredis", error=str(exc))
        import fakeredis.aioredis

        _redis_client = fakeredis.aioredis.FakeRedis(decode_responses=True)
        return _redis_client


async def close_redis() -> None:
    """Close the Redis client connection."""
    global _redis_client
    if _redis_client is not None:
        await _redis_client.close()
        _redis_client = None
