"""
Circuit Breaker for provider health tracking.

States: CLOSED (normal) → OPEN (failing, reject all) → HALF_OPEN (test one request)
- N consecutive failures → OPEN
- Recovery timeout → HALF_OPEN
- 1 success in HALF_OPEN → CLOSED
"""

import logging
import time
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """Per-provider circuit breaker."""

    def __init__(self, name: str, failure_threshold: int = 5,
                 recovery_timeout: float = 300.0):
        """
        Args:
            name: Identifier (e.g. "blockfrost:cardano:index").
            failure_threshold: Consecutive failures before opening.
            recovery_timeout: Seconds to wait before half-open test.
        """
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout

        self._state = CircuitState.CLOSED
        self._consecutive_failures = 0
        self._last_failure_time: Optional[float] = None
        self._total_requests = 0
        self._total_failures = 0

    @property
    def state(self) -> CircuitState:
        """Current state, with automatic OPEN → HALF_OPEN transition."""
        if self._state == CircuitState.OPEN and self._last_failure_time:
            elapsed = time.monotonic() - self._last_failure_time
            if elapsed >= self.recovery_timeout:
                self._state = CircuitState.HALF_OPEN
                logger.info(f"Circuit '{self.name}' → HALF_OPEN (recovery timeout elapsed)")
        return self._state

    @property
    def is_available(self) -> bool:
        """Whether requests should be allowed through."""
        return self.state != CircuitState.OPEN

    def record_success(self):
        """Record a successful request."""
        self._total_requests += 1
        if self._state == CircuitState.HALF_OPEN:
            self._state = CircuitState.CLOSED
            self._consecutive_failures = 0
            logger.info(f"Circuit '{self.name}' → CLOSED (success in half-open)")
        elif self._state == CircuitState.CLOSED:
            self._consecutive_failures = 0

    def record_failure(self):
        """Record a failed request."""
        self._total_requests += 1
        self._total_failures += 1
        self._consecutive_failures += 1
        self._last_failure_time = time.monotonic()

        if self._state == CircuitState.HALF_OPEN:
            self._state = CircuitState.OPEN
            logger.warning(f"Circuit '{self.name}' → OPEN (failure in half-open)")
        elif self._consecutive_failures >= self.failure_threshold:
            self._state = CircuitState.OPEN
            logger.warning(
                f"Circuit '{self.name}' → OPEN "
                f"({self._consecutive_failures} consecutive failures)"
            )

    def reset(self):
        """Force-reset to CLOSED state."""
        self._state = CircuitState.CLOSED
        self._consecutive_failures = 0
        self._last_failure_time = None
        logger.info(f"Circuit '{self.name}' → CLOSED (force reset)")

    def to_dict(self) -> dict:
        """Export state for persistence/API."""
        return {
            'name': self.name,
            'state': self.state.value,
            'consecutive_failures': self._consecutive_failures,
            'total_requests': self._total_requests,
            'total_failures': self._total_failures,
            'is_available': self.is_available,
        }
