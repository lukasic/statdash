import redis.asyncio as redis
from app.core.config import settings

valkey: redis.Redis = redis.from_url(settings.valkey_url, decode_responses=True)
