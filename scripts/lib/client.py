"""HTTP client and rate limiter for Sleeper API.

This module centralizes HTTP concerns:
- Simple monotonically-timed rate limiting (min interval between calls)
- Resilient requests.Session with retries and backoff for transient errors
- A tiny JSON helper bound to the configured base URL

The goal is to keep network behavior consistent and safe across scripts, while
leaving report outputs unchanged.
"""

from __future__ import annotations

import os
import time
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from scripts.lib.constants import DEFAULT_MIN_INTERVAL_SEC


class RateLimiter:
    """Wall-clock based rate limiter using a minimum interval between calls.

    This is intentionally simple and stateful for single-process scripts. It
    ensures at least ``min_interval_sec`` seconds elapse between consecutive
    ``wait()`` calls.
    """

    def __init__(self, min_interval_sec: float | None = None) -> None:
        self.min_interval = (
            float(min_interval_sec) if min_interval_sec else DEFAULT_MIN_INTERVAL_SEC
        )
        self._last = 0.0

    def wait(self) -> None:
        now = time.monotonic()
        if self._last:
            elapsed = now - self._last
            if elapsed < self.min_interval:
                time.sleep(self.min_interval - elapsed)
        self._last = time.monotonic()


class SleeperClient:
    """Thin wrapper around requests.Session for the Sleeper API.

    Environment variables can flow in via parameters:
    - base_url: defaults to https://api.sleeper.com/v1
    - rpm_limit: translated to a minimum interval of 60 / rpm seconds
    - min_interval_ms: explicit minimum interval in milliseconds (wins if larger)

    Only GET + JSON is implemented because report generation only needs reads.
    """

    def __init__(
        self,
        base_url: str | None = None,
        rpm_limit: float | None = None,
        min_interval_ms: float | None = None,
    ) -> None:
        self.base_url = base_url or os.environ.get(
            "SLEEPER_BASE_URL", "https://api.sleeper.com/v1"
        )
        # Translate env into min interval; mirror legacy behavior
        min_interval = None
        if rpm_limit and rpm_limit > 0:
            min_interval = max(min_interval or 0.0, 60.0 / rpm_limit)
        if min_interval_ms and min_interval_ms > 0:
            ms = float(min_interval_ms) / 1000.0
            min_interval = max(min_interval or 0.0, ms)
        self.rate = RateLimiter(min_interval)

        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "ff-weekly-report/1.0"})
        # Configure safe-idempotent retries for transient errors
        retry = Retry(
            total=5,
            connect=3,
            read=3,
            backoff_factor=0.5,
            status_forcelist=(408, 429, 500, 502, 503, 504),
            allowed_methods=("GET",),
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

    def get_json(self, path: str) -> Any:
        """GET ``base_url + path`` and return decoded JSON.

        Raises requests.HTTPError on non-2xx responses (after retries). A
        timeout is applied per request to avoid indefinite hangs.
        """
        self.rate.wait()
        r = self.session.get(self.base_url + path, timeout=20)
        r.raise_for_status()
        return r.json()
