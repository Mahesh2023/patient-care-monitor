"""Shared key-value + pub/sub layer.

`REDIS_URL` set  -> Redis / Render Key Value (required for >1 instance).
`REDIS_URL` empty -> in-process fallback (local dev, tests, single instance).

Pub/sub fan-out uses ONE upstream subscription connection per worker
process, multiplexed to any number of local subscribers (asyncio queues),
so watcher count does not translate into Redis connection count.
"""
from __future__ import annotations

import asyncio
import contextlib
import time
from collections import defaultdict
from typing import Optional
from collections.abc import AsyncIterator

from src.care_monitor.config import settings
from src.care_monitor.logging_utils import get_logger

log = get_logger(__name__)
_QUEUE_MAX = 100


class _LocalFanout:
    def __init__(self) -> None:
        self.subs: dict[str, set[asyncio.Queue]] = defaultdict(set)

    def deliver(self, channel: str, message: str) -> None:
        for q in list(self.subs.get(channel, ())):
            if q.full():  # slow consumer: drop oldest instead of blocking producers
                with contextlib.suppress(asyncio.QueueEmpty):
                    q.get_nowait()
            q.put_nowait(message)


class KV:
    backend = "abstract"

    def __init__(self) -> None:
        self._fan = _LocalFanout()

    async def start(self) -> None: ...
    async def close(self) -> None: ...
    async def ping(self) -> bool: return True
    async def incr_window(self, key: str, window_s: int) -> int: raise NotImplementedError
    async def get_int(self, key: str) -> int: raise NotImplementedError
    async def delete(self, key: str) -> None: raise NotImplementedError
    async def incr(self, key: str, delta: int, ttl_s: int) -> int: raise NotImplementedError
    async def acquire_lock(self, key: str, ttl_s: int) -> bool: raise NotImplementedError
    async def publish(self, channel: str, message: str) -> None: raise NotImplementedError
    async def _upstream_subscribe(self, channel: str) -> None: ...
    async def _upstream_unsubscribe(self, channel: str) -> None: ...

    @contextlib.asynccontextmanager
    async def subscribe(self, channel: str) -> AsyncIterator[asyncio.Queue]:
        q: asyncio.Queue = asyncio.Queue(maxsize=_QUEUE_MAX)
        first = not self._fan.subs.get(channel)
        self._fan.subs[channel].add(q)
        if first:
            await self._upstream_subscribe(channel)
        try:
            yield q
        finally:
            self._fan.subs[channel].discard(q)
            if not self._fan.subs[channel]:
                self._fan.subs.pop(channel, None)
                await self._upstream_unsubscribe(channel)


class MemoryKV(KV):
    backend = "memory"

    def __init__(self) -> None:
        super().__init__()
        self._counters: dict[str, tuple[int, float]] = {}

    def _gc(self) -> None:
        if len(self._counters) > 50_000:
            now = time.monotonic()
            self._counters = {k: v for k, v in self._counters.items() if v[1] > now}

    async def incr(self, key: str, delta: int, ttl_s: int) -> int:
        self._gc()
        now = time.monotonic()
        val, exp = self._counters.get(key, (0, 0.0))
        if exp <= now:
            val = 0
        val += delta
        self._counters[key] = (val, now + ttl_s)
        return val

    async def incr_window(self, key: str, window_s: int) -> int:
        self._gc()
        now = time.monotonic()
        val, exp = self._counters.get(key, (0, 0.0))
        if exp <= now:
            val, exp = 0, now + window_s
        self._counters[key] = (val + 1, exp)
        return val + 1

    async def get_int(self, key: str) -> int:
        val, exp = self._counters.get(key, (0, 0.0))
        return val if exp > time.monotonic() else 0

    async def delete(self, key: str) -> None:
        self._counters.pop(key, None)

    async def acquire_lock(self, key: str, ttl_s: int) -> bool:
        now = time.monotonic()
        _, exp = self._counters.get(key, (0, 0.0))
        if exp > now:
            return False
        self._counters[key] = (1, now + ttl_s)
        return True

    async def publish(self, channel: str, message: str) -> None:
        self._fan.deliver(channel, message)


class RedisKV(KV):
    backend = "redis"

    def __init__(self, url: str) -> None:
        super().__init__()
        import redis.asyncio as redis
        self._r = redis.from_url(url, decode_responses=True, health_check_interval=30,
                                 socket_timeout=5, socket_connect_timeout=5)
        self._pubsub = None
        self._reader: Optional[asyncio.Task] = None

    async def start(self) -> None:
        self._pubsub = self._r.pubsub(ignore_subscribe_messages=True)
        self._reader = asyncio.create_task(self._read_loop())

    async def _read_loop(self) -> None:
        while True:
            try:
                if not self._pubsub.subscribed:
                    await asyncio.sleep(0.25)
                    continue
                msg = await self._pubsub.get_message(timeout=1.0)
                if msg and msg.get("type") == "message":
                    self._fan.deliver(msg["channel"], msg["data"])
            except asyncio.CancelledError:
                raise
            except Exception as e:
                log.warning("redis pubsub read error: %s", e)
                await asyncio.sleep(1.0)

    async def close(self) -> None:
        if self._reader:
            self._reader.cancel()
            with contextlib.suppress(BaseException):
                await self._reader
        if self._pubsub is not None:
            with contextlib.suppress(Exception):
                await self._pubsub.aclose()
        await self._r.aclose()

    async def ping(self) -> bool:
        try:
            return bool(await self._r.ping())
        except Exception:
            return False

    async def incr(self, key: str, delta: int, ttl_s: int) -> int:
        async with self._r.pipeline(transaction=True) as p:
            p.incrby(key, delta)
            p.expire(key, ttl_s)
            val, _ = await p.execute()
        return int(val)

    async def incr_window(self, key: str, window_s: int) -> int:
        async with self._r.pipeline(transaction=True) as p:
            p.set(key, 0, nx=True, ex=window_s)  # starts the window once
            p.incr(key)
            _, val = await p.execute()
        return int(val)

    async def get_int(self, key: str) -> int:
        v = await self._r.get(key)
        return int(v) if v else 0

    async def delete(self, key: str) -> None:
        await self._r.delete(key)

    async def acquire_lock(self, key: str, ttl_s: int) -> bool:
        return bool(await self._r.set(key, "1", nx=True, ex=ttl_s))

    async def publish(self, channel: str, message: str) -> None:
        await self._r.publish(channel, message)

    async def _upstream_subscribe(self, channel: str) -> None:
        await self._pubsub.subscribe(channel)

    async def _upstream_unsubscribe(self, channel: str) -> None:
        with contextlib.suppress(Exception):
            await self._pubsub.unsubscribe(channel)


kv: KV = RedisKV(settings.redis_url) if settings.redis_url else MemoryKV()
