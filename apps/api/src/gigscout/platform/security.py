"""Password hashing (scrypt, stdlib), opaque session tokens and a small login rate limiter."""

import base64
import hashlib
import hmac
import secrets
import threading
import time
from collections import deque

SCRYPT_N, SCRYPT_R, SCRYPT_P = 2**14, 8, 1
SALT_BYTES = 16
TOKEN_BYTES = 32
MIN_PASSWORD_LENGTH = 10
ACCOUNT_MAX_FAILURES = 20  # per account from any address; higher than the per-address limit to blunt lockout abuse


class WeakPasswordError(ValueError):
    pass


def validate_password(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise WeakPasswordError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters")


def hash_password(password: str) -> str:
    validate_password(password)
    salt = secrets.token_bytes(SALT_BYTES)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P)
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt, digest = stored.split("$")
    except ValueError:
        return False
    if scheme != "scrypt":
        return False
    candidate = hashlib.scrypt(password.encode(), salt=_unb64(salt), n=int(n), r=int(r), p=int(p))
    return hmac.compare_digest(candidate, _unb64(digest))


def new_token() -> str:
    return secrets.token_urlsafe(TOKEN_BYTES)


def hash_token(token: str) -> str:
    """Only token hashes are stored, so a leaked database does not leak live sessions."""
    return hashlib.sha256(token.encode()).hexdigest()


class LoginLimiter:
    """Allows `max_failures` failed logins per key within `window_seconds`."""

    def __init__(self, max_failures: int = 5, window_seconds: float = 300) -> None:
        self._max = max_failures
        self._window = window_seconds
        self._failures: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def blocked(self, key: str) -> bool:
        with self._lock:
            return len(self._recent(key)) >= self._max

    def try_attempt(self, key: str) -> bool:
        """Reserves an attempt slot under the lock, so concurrent guesses cannot all slip past the check."""
        with self._lock:
            recent = self._recent(key)
            if len(recent) >= self._max:
                return False
            recent.append(time.monotonic())
            return True

    def record_failure(self, key: str) -> None:
        with self._lock:
            self._recent(key).append(time.monotonic())

    def reset(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)

    def _recent(self, key: str) -> deque[float]:
        entries = self._failures.setdefault(key, deque())
        cutoff = time.monotonic() - self._window
        while entries and entries[0] < cutoff:
            entries.popleft()
        return entries


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode()


def _unb64(text: str) -> bytes:
    return base64.b64decode(text)


# Checked when the email is unknown, so a missing account costs the same scrypt time as a wrong password.
DUMMY_PASSWORD_HASH = hash_password(secrets.token_urlsafe(16))
