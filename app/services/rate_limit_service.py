from __future__ import annotations

import logging
import os

try:
    import redis
except ImportError:  # pragma: no cover - runtime dependency guard
    redis = None

from ..env import load_env

logger = logging.getLogger(__name__)
_redis_client_cache = None
_redis_client_url = None


def get_query_cooldown_seconds() -> int:
    load_env()
    try:
        return max(1, int(os.getenv("QUERY_COOLDOWN_SECONDS", "30")))
    except ValueError:
        return 30


def _redis_client():
    global _redis_client_cache, _redis_client_url
    load_env()
    redis_url = os.getenv("REDIS_URL")
    if not redis_url:
        logger.error("REDIS_URL 未配置，公开查询限流降级为允许查询。")
        return None
    if redis is None:
        logger.error("redis 依赖未安装，公开查询限流降级为允许查询。")
        return None
    if _redis_client_cache is not None and _redis_client_url == redis_url:
        return _redis_client_cache
    _redis_client_url = redis_url
    _redis_client_cache = redis.Redis.from_url(
        redis_url,
        decode_responses=True,
        socket_connect_timeout=0.3,
        socket_timeout=0.3,
        retry_on_timeout=False,
        health_check_interval=30,
    )
    return _redis_client_cache


def check_query_rate_limit(ip: str) -> tuple[bool, int]:
    cooldown = get_query_cooldown_seconds()
    client = _redis_client()
    if client is None:
        return True, 0

    key = f"query:rate_limit:{ip}"
    try:
        ttl = client.ttl(key)
        if ttl and ttl > 0:
            return False, int(ttl)
        client.set(key, "1", ex=cooldown)
        return True, 0
    except Exception:
        logger.exception("Redis 查询限流失败，降级为允许查询。")
        return True, 0
