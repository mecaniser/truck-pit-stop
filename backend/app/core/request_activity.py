"""Short-lived request activity window for the local operations dashboard."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from math import ceil
from threading import Lock
from time import monotonic
from typing import Callable


DEFAULT_WINDOW_SECONDS = 300
_IGNORED_PATHS = {"/metrics", "/api/v1/admin/performance/stats"}


@dataclass(frozen=True)
class RequestSample:
    timestamp: float
    duration_ms: float
    status_code: int


class RequestActivityWindow:
    """A bounded, thread-safe rolling window owned by one API process."""

    def __init__(
        self,
        window_seconds: int = DEFAULT_WINDOW_SECONDS,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        self.window_seconds = window_seconds
        self._clock = clock
        self._samples: deque[RequestSample] = deque()
        self._lock = Lock()

    def record(self, path: str, duration_ms: float, status_code: int) -> None:
        if path in _IGNORED_PATHS or path.startswith("/health"):
            return

        now = self._clock()
        with self._lock:
            self._samples.append(RequestSample(now, duration_ms, status_code))
            self._discard_expired(now)

    def snapshot(self) -> dict[str, float | int]:
        now = self._clock()
        with self._lock:
            self._discard_expired(now)
            samples = list(self._samples)

        count = len(samples)
        observed_seconds = min(
            self.window_seconds,
            max(now - samples[0].timestamp, 1.0) if samples else 0.0,
        )
        client_errors = sum(400 <= sample.status_code < 500 for sample in samples)
        server_errors = sum(sample.status_code >= 500 for sample in samples)
        durations = sorted(sample.duration_ms for sample in samples)
        p95_index = max(ceil(count * 0.95) - 1, 0)

        return {
            "window_seconds": self.window_seconds,
            "observed_seconds": round(observed_seconds, 1),
            "request_count": count,
            "requests_per_minute": round((count / observed_seconds) * 60, 1)
            if observed_seconds
            else 0.0,
            "p95_latency_ms": round(durations[p95_index], 2) if durations else 0.0,
            "error_rate_percent": round(((client_errors + server_errors) / count) * 100, 2) if count else 0.0,
            "error_count": client_errors + server_errors,
            "client_error_rate_percent": round((client_errors / count) * 100, 2) if count else 0.0,
            "server_error_rate_percent": round((server_errors / count) * 100, 2) if count else 0.0,
        }

    def _discard_expired(self, now: float) -> None:
        cutoff = now - self.window_seconds
        while self._samples and self._samples[0].timestamp < cutoff:
            self._samples.popleft()


request_activity_window = RequestActivityWindow()
