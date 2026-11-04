"""Cloudflare Turnstile: the bot check on the company's own website form.

The widget on the website hands each real visitor a one-time token (form field `cf-turnstile-response`); we confirm it
with Cloudflare before storing the enquiry. The secret key goes only to Cloudflare's siteverify endpoint, never to
the browser, logs or API responses.
"""

import logging
from enum import Enum

import httpx
from pydantic import SecretStr

log = logging.getLogger(__name__)

VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
TOKEN_FIELD = "cf-turnstile-response"
MAX_TOKEN_CHARS = 2048  # Cloudflare's documented maximum
TIMEOUT_SECONDS = 10
SCRIPT_URL = "https://challenges.cloudflare.com/turnstile/v0/api.js"


class Check(Enum):
    PASSED = "passed"
    FAILED = "failed"
    UNAVAILABLE = "unavailable"  # Cloudflare could not be reached: the caller falls back to its own limits


async def verify(secret: SecretStr, token: str | None, remote_ip: str | None = None) -> Check:
    """Ask Cloudflare whether this token came from a visitor who passed the widget. Each token works once."""
    if not token or len(token) > MAX_TOKEN_CHARS:
        return Check.FAILED
    data = {"secret": secret.get_secret_value(), "response": token}
    if remote_ip:
        data["remoteip"] = remote_ip
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
            response = await client.post(VERIFY_URL, data=data)
        response.raise_for_status()
        result = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        log.warning("Turnstile check unavailable (%s)", type(exc).__name__)  # never the secret or the token
        return Check.UNAVAILABLE
    if isinstance(result, dict) and result.get("success") is True:
        return Check.PASSED
    codes = result.get("error-codes") if isinstance(result, dict) else None
    if isinstance(codes, list) and any(c in ("invalid-input-secret", "missing-input-secret") for c in codes):
        log.error("Turnstile rejected our secret key: check GIGSCOUT_TURNSTILE_SECRET_KEY")
        return Check.UNAVAILABLE  # our misconfiguration must not throw away real enquiries
    return Check.FAILED
