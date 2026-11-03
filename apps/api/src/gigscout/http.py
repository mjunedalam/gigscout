"""A polite HTTP client: identifies itself, obeys robots.txt, rate-limits per host, retries gently."""

import logging
import threading
import time
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import httpx

from gigscout.config import Settings

log = logging.getLogger(__name__)

RETRYABLE_STATUS = {429, 500, 502, 503, 504}
BACKOFF_BASE_SECONDS = 1.5


class DisallowedByRobots(RuntimeError):
    pass


class PoliteClient:
    def __init__(self, settings: Settings, transport: httpx.BaseTransport | None = None) -> None:
        self._settings = settings
        self._client = httpx.Client(
            headers={"User-Agent": settings.user_agent, "Accept": "application/json, application/xml, */*"},
            timeout=settings.http_timeout,
            follow_redirects=True,
            transport=transport,
        )
        self._robots: dict[str, RobotFileParser | None] = {}
        self._last_call: dict[str, float] = {}
        self._lock = threading.Lock()

    def get(self, url: str, params: dict | None = None) -> httpx.Response:
        if not self._allowed(url):
            raise DisallowedByRobots(f"robots.txt disallows {url}")
        for attempt in range(1, self._settings.http_max_retries + 1):
            self._throttle(urlsplit(url).netloc)
            response = self._client.get(url, params=params)
            if response.status_code not in RETRYABLE_STATUS or attempt == self._settings.http_max_retries:
                response.raise_for_status()
                return response
            wait = BACKOFF_BASE_SECONDS**attempt
            log.warning("HTTP %s from %s, retrying in %.1fs", response.status_code, url, wait)
            time.sleep(wait)
        raise AssertionError("unreachable")

    def get_json(self, url: str, params: dict | None = None):
        return self.get(url, params).json()

    def get_text(self, url: str, params: dict | None = None) -> str:
        return self.get(url, params).text

    def close(self) -> None:
        self._client.close()

    def _throttle(self, host: str) -> None:
        with self._lock:
            elapsed = time.monotonic() - self._last_call.get(host, 0.0)
            wait = self._settings.http_min_interval - elapsed
            if wait > 0:
                time.sleep(wait)
            self._last_call[host] = time.monotonic()

    def _allowed(self, url: str) -> bool:
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin not in self._robots:
            self._robots[origin] = self._load_robots(origin)
        parser = self._robots[origin]
        return parser is None or parser.can_fetch(self._settings.user_agent, url)

    def _load_robots(self, origin: str) -> RobotFileParser | None:
        try:
            response = self._client.get(f"{origin}/robots.txt")
        except httpx.HTTPError as exc:
            log.info("No robots.txt for %s (%s); assuming allowed", origin, exc)
            return None
        if response.status_code >= 400:
            return None
        parser = RobotFileParser()
        parser.parse(response.text.splitlines())
        return parser
