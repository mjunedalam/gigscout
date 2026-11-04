"""Accounts the company connects by signing in (OAuth), starting with Upwork."""

import logging
import secrets
import threading
import time
from datetime import UTC, datetime, timedelta
from functools import partial

from gigscout import upwork as upwork_lib
from gigscout.config import Settings
from gigscout.platform.db import SessionFactory
from gigscout.platform.tables import IntegrationToken, utcnow
from gigscout.sources.base import Source

log = logging.getLogger(__name__)

STATE_TTL_SECONDS = 600
REFRESH_MARGIN = timedelta(minutes=5)


class UpworkConnection:
    NAME = "upwork"

    def __init__(self, sessions: SessionFactory, settings: Settings) -> None:
        self._sessions = sessions
        self._settings = settings
        self._states: dict[str, tuple[str, int, float]] = {}  # state -> (admin email, workspace, expiry)
        self._lock = threading.Lock()

    @property
    def configured(self) -> bool:
        return bool(self._settings.upwork_client_id and self._settings.upwork_client_secret)

    def status(self, workspace_id: int) -> dict:
        with self._sessions() as session:
            row = session.get(IntegrationToken, (workspace_id, self.NAME))
            return {
                "configured": self.configured, "connected": row is not None,
                "connected_by": row.connected_by if row else None, "connected_at": row.connected_at if row else None,
            }

    def start(self, admin_email: str, workspace_id: int) -> str:
        """The Upwork sign-in URL; the state ties the callback to this admin and workspace, and expires in ten
        minutes."""
        state = secrets.token_urlsafe(24)
        with self._lock:
            now = time.monotonic()
            self._states = {s: v for s, v in self._states.items() if v[2] > now}
            self._states[state] = (admin_email, workspace_id, now + STATE_TTL_SECONDS)
        return upwork_lib.authorize_url(self._settings.upwork_client_id, self._settings.upwork_redirect_uri, state)

    def finish(self, code: str, state: str) -> tuple[str, int]:
        """Exchange the code for tokens and store them sealed. Returns the admin and workspace that started it."""
        with self._lock:
            started = self._states.pop(state, None)
        if started is None or started[2] < time.monotonic():
            raise upwork_lib.UpworkError("This Upwork sign-in expired or was not started here: try again")
        tokens = upwork_lib.exchange_code(self._settings.upwork_client_id, self._secret(),
                                          self._settings.upwork_redirect_uri, code)
        self._save(started[1], tokens, connected_by=started[0])
        return started[0], started[1]

    def disconnect(self, workspace_id: int) -> None:
        with self._sessions() as session:
            row = session.get(IntegrationToken, (workspace_id, self.NAME))
            if row is not None:
                session.delete(row)
                session.commit()

    def access_token(self, workspace_id: int) -> str:
        """A valid access token, refreshed when it is about to expire."""
        vault = upwork_lib.TokenVault(self._secret())
        with self._sessions() as session:
            row = session.get(IntegrationToken, (workspace_id, self.NAME))
            if row is None:
                raise upwork_lib.UpworkError("Upwork is not connected")
            expires = row.expires_at if row.expires_at.tzinfo else row.expires_at.replace(tzinfo=UTC)
            if expires - REFRESH_MARGIN > datetime.now(UTC):
                return vault.open(row.access_token)
            refresh_token = vault.open(row.refresh_token)
            connected_by = row.connected_by
        tokens = upwork_lib.refresh(self._settings.upwork_client_id, self._secret(), refresh_token)
        self._save(workspace_id, tokens, connected_by=connected_by)
        return tokens.access_token

    def sources(self, workspace_id: int) -> dict[str, Source]:
        """Upwork as a run source while it is configured and connected for this workspace."""
        if not self.configured or not self.status(workspace_id)["connected"]:
            return {}
        return {self.NAME: upwork_lib.UpworkSource(partial(self.access_token, workspace_id))}

    def _secret(self) -> str:
        return self._settings.upwork_client_secret.get_secret_value()

    def _save(self, workspace_id: int, tokens: upwork_lib.Tokens, connected_by: str) -> None:
        vault = upwork_lib.TokenVault(self._secret())
        with self._sessions() as session:
            row = session.get(IntegrationToken, (workspace_id, self.NAME))
            row = row or IntegrationToken(workspace_id=workspace_id, name=self.NAME, connected_by=connected_by)
            row.access_token, row.refresh_token = vault.seal(tokens.access_token), vault.seal(tokens.refresh_token)
            row.expires_at, row.updated_at = tokens.expires_at, utcnow()
            session.add(row)
            session.commit()
