# client.py
from __future__ import annotations
import os
import time
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from typing import Any
from scripts.lib.constants import DEFAULT_MIN_INTERVAL_SEC


class RateLimiter:
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
    def __init__(
        self,
        base_url: str | None = None,
        rpm_limit: float | None = None,
        min_interval_ms: float | None = None,
    ) -> None:
        self.base_url = base_url or os.environ.get("SLEEPER_BASE_URL", "https://api.sleeper.com/v1")
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
        self.rate.wait()
        r = self.session.get(self.base_url + path, timeout=20)
        r.raise_for_status()
        return r.json()
