import asyncio
from typing import Dict, Any, Set
import os
import json
from loguru import logger
try:
    from redis import asyncio as aioredis
except Exception:
    aioredis = None

class EventBus:
    def __init__(self):
        self._subscribers: Set[asyncio.Queue] = set()
        self._lock = asyncio.Lock()
        self._loop = None
        # Optional Redis Pub/Sub
        self._use_redis = str(os.getenv("USE_REDIS", "false")).lower() == "true"
        self._redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self._redis = None
        self._redis_channel = os.getenv("REDIS_CHANNEL", "events")

    def set_loop(self, loop):
        """Set the event loop for sync context publishing"""
        self._loop = loop
        logger.info(f"EventBus: Set event loop {loop}")
        # Initialize Redis if enabled
        if self._use_redis and aioredis:
            async def _init():
                try:
                    self._redis = aioredis.from_url(self._redis_url)
                    asyncio.create_task(self._redis_listener())
                    logger.info(f"EventBus: Redis Pub/Sub enabled on {self._redis_url} channel={self._redis_channel}")
                except Exception as e:
                    logger.warning(f"EventBus: Redis init failed: {e}")
            asyncio.run_coroutine_threadsafe(_init(), loop)

    async def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        async with self._lock:
            self._subscribers.add(q)
        logger.info(f"EventBus: New subscriber, total={len(self._subscribers)}")
        return q

    async def unsubscribe(self, q: asyncio.Queue):
        async with self._lock:
            self._subscribers.discard(q)
        logger.info(f"EventBus: Subscriber left, total={len(self._subscribers)}")

    async def publish(self, event: Dict[str, Any]):
        async with self._lock:
            sub_count = len(self._subscribers)
            logger.info(f"EventBus: Publishing event type={event.get('type')} to {sub_count} subscribers")
            for q in list(self._subscribers):
                try:
                    q.put_nowait(event)
                except asyncio.QueueFull:
                    logger.warning(f"EventBus: Queue full, dropping event")
                    pass
        # Also publish to Redis channel if enabled
        try:
            if self._use_redis and self._redis:
                await self._redis.publish(self._redis_channel, json.dumps(event))
        except Exception as e:
            logger.warning(f"EventBus: Redis publish failed: {e}")

    def publish_sync(self, event: Dict[str, Any]):
        """Publish from sync context (like scheduler)"""
        logger.info(f"EventBus: publish_sync called, type={event.get('type')}, loop={self._loop}")
        if self._loop and self._loop.is_running():
            future = asyncio.run_coroutine_threadsafe(self.publish(event), self._loop)
            logger.info(f"EventBus: Scheduled coroutine, future={future}")
        else:
            logger.warning(f"EventBus: No running loop, event dropped")

    async def _redis_listener(self):
        """Listen to Redis Pub/Sub and forward messages to local subscribers"""
        try:
            pubsub = self._redis.pubsub()
            await pubsub.subscribe(self._redis_channel)
            logger.info("EventBus: Redis listener started")
            async for message in pubsub.listen():
                if message and message.get("type") == "message":
                    try:
                        event = json.loads(message.get("data"))
                        await self.publish(event)  # fan out locally
                    except Exception:
                        pass
        except Exception as e:
            logger.warning(f"EventBus: Redis listener error: {e}")

# Global bus instance
bus = EventBus()
