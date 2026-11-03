"""Upwork through its official API: OAuth 2.0 sign-in by an admin, then job search over GraphQL.

Needs an approved Upwork API key (https://www.upwork.com/developer/keys/apply) with the job-search scope. The
tokens Upwork returns are stored encrypted with a key derived from the client secret, so the database alone is
not enough to act as the company on Upwork.
"""

import base64
import hashlib
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import httpx
from cryptography.fernet import Fernet, InvalidToken

from gigscout.models import Budget, Client, Lead
from gigscout.text import html_to_text

AUTHORIZE_URL = "https://www.upwork.com/ab/account-security/oauth2/authorize"
TOKEN_URL = "https://www.upwork.com/api/v3/oauth2/token"
GRAPHQL_URL = "https://api.upwork.com/graphql"
JOB_URL = "https://www.upwork.com/jobs/~"
TIMEOUT = 20

SEARCH = """
query SearchJobs($filter: MarketplaceJobPostingsSearchFilter) {
  marketplaceJobPostingsSearch(
    marketPlaceJobFilter: $filter
    searchType: USER_JOBS_SEARCH
    sortAttributes: [{ field: RECENCY }]
  ) {
    edges {
      node {
        id title description ciphertext createdDateTime totalApplicants
        amount { rawValue currency }
        hourlyBudgetMin { rawValue currency }
        hourlyBudgetMax { rawValue currency }
        skills { name }
        client { location { country } }
      }
    }
  }
}
"""


class UpworkError(Exception):
    """Upwork refused or could not be reached. Messages never contain tokens or secrets."""


@dataclass(frozen=True)
class Tokens:
    access_token: str
    refresh_token: str
    expires_at: datetime


def authorize_url(client_id: str, redirect_uri: str, state: str) -> str:
    query = {"response_type": "code", "client_id": client_id, "redirect_uri": redirect_uri, "state": state}
    return f"{AUTHORIZE_URL}?{urlencode(query)}"


def exchange_code(client_id: str, client_secret: str, redirect_uri: str, code: str) -> Tokens:
    return _token_request({
        "grant_type": "authorization_code", "client_id": client_id, "client_secret": client_secret,
        "code": code, "redirect_uri": redirect_uri,
    })


def refresh(client_id: str, client_secret: str, refresh_token: str) -> Tokens:
    return _token_request({
        "grant_type": "refresh_token", "client_id": client_id, "client_secret": client_secret,
        "refresh_token": refresh_token,
    })


def _token_request(form: dict[str, str]) -> Tokens:
    try:
        response = httpx.post(TOKEN_URL, data=form, headers={"Accept": "application/json"}, timeout=TIMEOUT)
    except httpx.HTTPError as exc:
        raise UpworkError(f"Upwork could not be reached ({type(exc).__name__})") from None
    if response.status_code >= 400:
        raise UpworkError(f"Upwork refused the sign-in (HTTP {response.status_code})")
    data = response.json()
    expires = datetime.now(UTC) + timedelta(seconds=int(data.get("expires_in", 3600)))
    return Tokens(data["access_token"], data.get("refresh_token", form.get("refresh_token", "")), expires)


class TokenVault:
    """Encrypts tokens at rest with a key derived from the Upwork client secret."""

    def __init__(self, client_secret: str) -> None:
        digest = hashlib.sha256(b"gigscout/upwork-tokens/" + client_secret.encode()).digest()
        self._fernet = Fernet(base64.urlsafe_b64encode(digest))

    def seal(self, value: str) -> str:
        return self._fernet.encrypt(value.encode()).decode()

    def open(self, sealed: str) -> str:
        try:
            return self._fernet.decrypt(sealed.encode()).decode()
        except InvalidToken:
            raise UpworkError("The saved Upwork sign-in can no longer be read: connect Upwork again") from None


class UpworkSource:
    name = "upwork"

    def __init__(self, access_token: Callable[[], str]) -> None:
        self._access_token = access_token

    def fetch(self, queries: Sequence[str], limit: int) -> list[Lead]:
        headers = {"Authorization": f"Bearer {self._access_token()}", "Content-Type": "application/json"}
        leads: list[Lead] = []
        for query in queries:
            variables = {"filter": {"searchExpression_eq": query, "pagination_eq": {"first": min(limit, 50)}}}
            try:
                response = httpx.post(GRAPHQL_URL, json={"query": SEARCH, "variables": variables}, headers=headers,
                                      timeout=TIMEOUT)
            except httpx.HTTPError as exc:
                raise UpworkError(f"Upwork could not be reached ({type(exc).__name__})") from None
            if response.status_code >= 400:
                raise UpworkError(f"Upwork refused the search (HTTP {response.status_code})")
            payload = response.json()
            if payload.get("errors"):
                raise UpworkError(f"Upwork: {payload['errors'][0].get('message', 'search failed')}"[:300])
            edges = ((payload.get("data") or {}).get("marketplaceJobPostingsSearch") or {}).get("edges") or []
            leads.extend(lead for edge in edges if (lead := parse(edge.get("node") or {})))
        return leads


def _money(value: dict | None) -> tuple[float | None, str | None]:
    if not value:
        return None, None
    try:
        amount = float(value.get("rawValue"))
    except (TypeError, ValueError):
        return None, None
    return (amount if amount > 0 else None), (value.get("currency") or "USD").upper()


def parse(node: dict) -> Lead | None:
    if not node.get("id") or not node.get("title"):
        return None
    fixed, currency = _money(node.get("amount"))
    low, low_currency = _money(node.get("hourlyBudgetMin"))
    high, high_currency = _money(node.get("hourlyBudgetMax"))
    if fixed:
        budget = Budget(maximum=fixed, currency=currency, kind="fixed")
    elif low or high:
        budget = Budget(minimum=low, maximum=high, currency=high_currency or low_currency, kind="hourly")
    else:
        budget = None
    created = node.get("createdDateTime")
    country = ((node.get("client") or {}).get("location") or {}).get("country")
    ciphertext = node.get("ciphertext")
    return Lead(
        id=f"upwork:{node['id']}", source="upwork", title=node["title"].strip(),
        description=html_to_text(node.get("description")), kind="project",
        url=f"{JOB_URL}{ciphertext.lstrip('~')}" if ciphertext else "https://www.upwork.com/nx/find-work/",
        skills=tuple(s["name"] for s in node.get("skills") or [] if s.get("name")),
        budget=budget, bid_count=node.get("totalApplicants"),
        posted_at=datetime.fromisoformat(created.replace("Z", "+00:00")) if created else None,
        client=Client(country=country) if country else None,
    )
