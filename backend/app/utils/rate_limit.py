"""Simple in-memory sliding-window rate limiter for login endpoints.

Kept in memory (no Redis dependency). Good enough for a single-process
deployment; if the API is ever scaled to multiple workers, replace this with
a shared store (e.g. Redis) behind the same interface.
"""

import threading
import time
from collections import defaultdict, deque


class RateLimiter:
    def __init__(self, limit: int, window_seconds: int):
        self.limit = limit
        self.window_seconds = window_seconds
        self._hits: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str) -> bool:
        """Record a hit for the key and return True if it is within the limit."""
        now = time.monotonic()
        with self._lock:
            queue = self._hits[key]
            while queue and now - queue[0] > self.window_seconds:
                queue.popleft()
            if len(queue) >= self.limit:
                return False
            queue.append(now)
            return True

    def reset(self, key: str | None = None) -> None:
        """Drop recorded hits for one key, or for all keys if key is None."""
        with self._lock:
            if key is None:
                self._hits.clear()
            else:
                self._hits.pop(key, None)
