import redis.asyncio as redis
from typing import Optional, Any
import json
from common.core.config import settings

class RedisManager:
    def __init__(self):
        self._redis: Optional[redis.Redis] = None

    async def connect(self):
        if self._redis is None:
            self._redis = redis.Redis(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                password=settings.REDIS_PASSWORD,
                decode_responses=True
            )

    async def disconnect(self):
        if self._redis:
            await self._redis.close()
            self._redis = None

    async def set_state(self, key: str, value: Any, expire: int = 3600):
        if self._redis is None:
            await self.connect()
        
        # Serialize if not a string
        if not isinstance(value, str):
            value = json.dumps(value)
            
        await self._redis.set(key, value, ex=expire)

    async def get_state(self, key: str) -> Optional[Any]:
        if self._redis is None:
            await self.connect()
        
        value = await self._redis.get(key)
        if value:
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value
        return None

redis_manager = RedisManager()
