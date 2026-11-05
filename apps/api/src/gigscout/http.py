"""A polite HTTP client: identifies itself, obeys robots.txt, rate-limits per host, retries gently."""

import logging
import threading
import time
import zlib
from dataclasses import dataclass
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import httpx

from gigscout.config import Settings

log = logging.getLogger(__name__)

RETRYABLE_STATUS = {429, 500, 502, 503, 504}
BACKOFF_BASE_SECONDS = 1.5


class DisallowedByRobots(RuntimeError):
    pass


class TooLarge(RuntimeError):
    """A response that says (or turns out to be) bigger than the caller allows."""


@dataclass(frozen=True)
class Limited:
    """A response read with a size cap: the status, headers, and at most max_bytes of body."""

    status_code: int
    headers: httpx.Headers
    body: bytes
    is_redirect: bool
    truncated: bool


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

    def get(
        self, url: str, params: dict | None = None, follow_redirects: bool = True, headers: dict | None = None,
    ) -> httpx.Response:
        """GET politely. With follow_redirects=False a redirect is returned (not raised) so the caller can vet
        where it points before following it, which is how user-supplied websites are fetched."""
        return self._request("GET", url, params=params, follow_redirects=follow_redirects, headers=headers)

    def post_json(self, url: str, payload: dict):
        """POST a JSON query (search APIs such as EU TED) with the same manners as GET."""
        return self._request("POST", url, json=payload).json()

    def _request(self, method: str, url: str, follow_redirects: bool = True, **kwargs) -> httpx.Response:
        if not self._allowed(url):
            raise DisallowedByRobots(f"robots.txt disallows {url}")
        for attempt in range(1, self._settings.http_max_retries + 1):
            self._throttle(urlsplit(url).netloc)
            response = self._client.request(method, url, follow_redirects=follow_redirects, **kwargs)
            if response.is_redirect and not follow_redirects:
                return response
            if response.status_code not in RETRYABLE_STATUS or attempt == self._settings.http_max_retries:
                response.raise_for_status()
                return response
            wait = BACKOFF_BASE_SECONDS**attempt
            log.warning("HTTP %s from %s, retrying in %.1fs", response.status_code, url, wait)
            time.sleep(wait)
        raise AssertionError("unreachable")

    def get_limited(self, url: str, max_bytes: int, max_seconds: float = 30.0) -> Limited:
        """GET without following redirects, reading at most max_bytes and for at most max_seconds in total, so a
        huge or endless body never fills memory or holds a worker. Bodies declared too big are not read at all."""
        if not self._allowed(url):
            raise DisallowedByRobots(f"robots.txt disallows {url}")
        self._throttle(urlsplit(url).netloc)
        deadline = time.monotonic() + max_seconds
        # ask for the body as-is, and read raw bytes: a compressed body is only ever expanded within the cap
        with self._client.stream("GET", url, follow_redirects=False,
                                 headers={"Accept-Encoding": "identity"}) as response:
            if response.is_redirect:
                return Limited(response.status_code, response.headers, b"", True, False)
            response.raise_for_status()
            declared = response.headers.get("content-length", "")
            if declared.isdigit() and int(declared) > max_bytes:
                raise TooLarge(f"{url} is {int(declared):,} bytes")
            decoder = _bounded_decoder(response.headers.get("content-encoding", ""), url)
            body, truncated = bytearray(), False
            for chunk in response.iter_raw():
                room = max_bytes - len(body)
                body.extend(decoder(chunk, room) if decoder else chunk[:room])
                if len(body) >= max_bytes or time.monotonic() > deadline:
                    truncated = True
                    break
            return Limited(response.status_code, response.headers, bytes(body[:max_bytes]), False, truncated)

    def get_json(self, url: str, params: dict | None = None, headers: dict | None = None):
        return self.get(url, params, headers=headers).json()

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


def _bounded_decoder(encoding: str, url: str):
    """For a server that compresses anyway: expand gzip or deflate at most `room` bytes per chunk. Anything else
    cannot be expanded safely here and is refused."""
    encoding = encoding.strip().lower()
    if encoding in ("", "identity"):
        return None
    if encoding not in ("gzip", "x-gzip", "deflate"):
        raise TooLarge(f"{url} sent a {encoding} body, which is not read")
    inflater = zlib.decompressobj(zlib.MAX_WBITS | 32)  # gzip or zlib header, detected
    return lambda chunk, room: inflater.decompress(chunk, max(room, 0)) if room > 0 else b""
