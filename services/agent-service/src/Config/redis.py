from redis.asyncio import Redis, from_url
from src.Config.settings import settings

redis_client: Redis = None

async def init_redis() -> Redis:
    global redis_client
    try:
        redis_client = from_url(settings.REDIS_URL, decode_responses=True)
        # Test connection
        await redis_client.ping()
        return redis_client
    except Exception as e:
        raise RuntimeError(f"Redis connection error: failed to connect to Redis pool. Details: {str(e)}") from e

async def get_redis() -> Redis:
    if redis_client is None:
        raise RuntimeError("Redis client has not been initialized. Please run init_redis() first.")
    return redis_client

async def get_value(redis: Redis, key: str) -> str | None:
    return await redis.get(key)

async def set_value(redis: Redis, key: str, value: str, ttl: int):
    await redis.set(key, value, ex=ttl)

async def delete_value(redis: Redis, key: str):
    await redis.delete(key)
