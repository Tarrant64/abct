"""
Token Bucket Rate Limiter

Per-provider rate limiting. Tokens refill at a steady rate up to burst_size.
try_acquire() is non-blocking; wait_for_token() blocks until a token is available.
"""

import asyncio
import time
import logging

logger = logging.getLogger(__name__)


class TokenBucket:
    """Async token bucket for rate limiting API calls to a provider."""

    def __init__(self, rate: float, burst: int):
        """
        Args:
            rate: Tokens added per second (e.g. 5.0 = 5 requests/sec).
            burst: Maximum tokens (bucket capacity).
        """
        self._rate = rate
        self._burst = burst
        self._tokens = float(burst)
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    def _refill(self):
        """Refill tokens based on elapsed time."""
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(self._burst, self._tokens + elapsed * self._rate)
        self._last_refill = now

    def try_acquire(self) -> bool:
        """Try to acquire a token without waiting. Returns True if acquired."""
        self._refill()
        if self._tokens >= 1.0:
            self._tokens -= 1.0
            return True
        return False

    async def wait_for_token(self):
        """Wait until a token is available, then acquire it."""
        async with self._lock:
            self._refill()
            if self._tokens >= 1.0:
                self._tokens -= 1.0
                return

            # Calculate wait time for next token
            deficit = 1.0 - self._tokens
            wait_time = deficit / self._rate
            await asyncio.sleep(wait_time)

            self._refill()
            self._tokens -= 1.0

    @property
    def available_tokens(self) -> float:
        """Current available tokens (approximate)."""
        self._refill()
        return self._tokens
