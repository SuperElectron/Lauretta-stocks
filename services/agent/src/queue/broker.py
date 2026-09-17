"""The broker connection the worker opens."""

from redis.asyncio import Redis

from src.queue import consumer

# redis-py's default socket timeout (5s) would cut a blocking read of the same length short.
# This outlasts the longest `block` used, and still fails a command that hangs.
SOCKET_TIMEOUT_SECONDS = consumer.BLOCK_MS / 1000 + 5


def connect(url: str) -> Redis:
    return Redis.from_url(url, decode_responses=True, socket_timeout=SOCKET_TIMEOUT_SECONDS)
