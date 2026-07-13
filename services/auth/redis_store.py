import os
from typing import Any

import redis.asyncio as aioredis

_client: aioredis.Redis | None = None


async def get_redis() -> aioredis.Redis:
    global _client
    if _client is None:
        url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        _client = aioredis.from_url(url, decode_responses=True)
    return _client


async def close_redis() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


async def blocklist_jti(jti: str, ttl_seconds: int) -> None:
    redis = await get_redis()
    await redis.setex(f"jwt:blocklist:{jti}", ttl_seconds, "1")


async def is_jti_blocklisted(jti: str) -> bool:
    redis = await get_redis()
    return bool(await redis.exists(f"jwt:blocklist:{jti}"))


def reset_redis_for_tests(fake: Any) -> None:
    global _client
    _client = fake
