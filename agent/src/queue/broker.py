"""The broker connection the API and the worker open."""

from redis.asyncio import Redis

from src.queue import consumer, events

# redis-py's default socket timeout (5s) would cut a blocking read of the same length short.
# This outlasts the longest `block` used, and still fails a command that hangs.
SOCKET_TIMEOUT_SECONDS = max(events.READ_BLOCK_MS, consumer.BLOCK_MS) / 1000 + 5


def connect(url: str) -> Redis:
    return Redis.from_url(url, decode_responses=True, socket_timeout=SOCKET_TIMEOUT_SECONDS)
