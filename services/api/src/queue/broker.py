"""The broker connection the API opens."""

from redis.asyncio import Redis

from src.queue import events

# redis-py's default socket timeout (5s) would cut a blocking read of the same length short.
SOCKET_TIMEOUT_SECONDS = events.READ_BLOCK_MS / 1000 + 5


def connect(url: str) -> Redis:
    return Redis.from_url(url, decode_responses=True, socket_timeout=SOCKET_TIMEOUT_SECONDS)
