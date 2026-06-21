"""A tiny minimum-interval throttle for free-tier REST APIs.

Free Finnhub / FMP plans have low rate limits, so we enforce a minimum spacing
between calls instead of bursting. Thread-safe and process-local.
"""
from __future__ import annotations

import threading
import time


class RateLimiter:
    def __init__(self, min_interval_seconds: float):
        self.min_interval = float(min_interval_seconds)
        self._lock = threading.Lock()
        self._last = 0.0

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            elapsed = now - self._last
            if elapsed < self.min_interval:
                time.sleep(self.min_interval - elapsed)
            self._last = time.monotonic()
