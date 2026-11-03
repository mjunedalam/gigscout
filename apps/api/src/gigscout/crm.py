"""Push a lead into the sales team's CRM as a deal, so it is worked where they already work."""

from dataclasses import dataclass
from typing import Protocol

import httpx

from gigscout.agent.nodes import budget_label
from gigscout.config import Settings
from gigscout.models import Lead

TIMEOUT = 15
DESCRIPTION_CHARS = 1500


@dataclass(frozen=True)
class CrmLink:
    crm: str
    external_id: str
    url: str | None = None


class CrmError(Exception):
    """The CRM refused or could not be reached. Messages never contain the token."""


class Crm(Protocol):
    name: str

    def push(self, lead: Lead, pitch: str) -> CrmLink: ...


def describe(lead: Lead, pitch: str) -> str:
    parts = [
        f"Found by GigScout on {lead.source} ({lead.kind}): {lead.url}",
        f"Budget: {budget_label(lead)}",
        f"Opening line: {pitch}" if pitch else "",
        lead.description[:DESCRIPTION_CHARS],
    ]
    return "\n\n".join(p for p in parts if p)


def _amount(lead: Lead) -> float | None:
    budget = lead.budget
    return None if budget is None else budget.maximum or budget.minimum


def _post(name: str, url: str, payload: dict, headers: dict[str, str]) -> dict:
    try:
        response = httpx.post(url, json=payload, headers=headers, timeout=TIMEOUT, follow_redirects=False)
    except httpx.HTTPError as exc:
        raise CrmError(f"{name} could not be reached ({type(exc).__name__})") from None
    if response.status_code >= 400:
        raise CrmError(f"{name} refused the request (HTTP {response.status_code})")
    return response.json()


class HubSpot:
    """A private-app token with the crm.objects.deals.write scope. Deals land in the default pipeline."""

    name = "hubspot"
    DEALS = "https://api.hubapi.com/crm/v3/objects/deals"

    def __init__(self, token: str) -> None:
        self._token = token

    def push(self, lead: Lead, pitch: str) -> CrmLink:
        properties = {
            "dealname": lead.title[:250], "description": describe(lead, pitch),
            "pipeline": "default", "dealstage": "appointmentscheduled",
        }
        if (amount := _amount(lead)) is not None:
            properties["amount"] = f"{amount:g}"
        data = _post("HubSpot", self.DEALS, {"properties": properties}, {"Authorization": f"Bearer {self._token}"})
        return CrmLink(crm=self.name, external_id=str(data["id"]))


class Pipedrive:
    """A personal API token. The deal gets the lead's details as a note."""

    name = "pipedrive"
    API = "https://api.pipedrive.com/v1"

    def __init__(self, token: str) -> None:
        self._token = token

    def push(self, lead: Lead, pitch: str) -> CrmLink:
        headers = {"x-api-token": self._token}
        deal = {"title": lead.title[:250]}
        if (amount := _amount(lead)) is not None:
            deal |= {"value": amount, "currency": (lead.budget.currency or "USD").upper()}
        deal_id = _post("Pipedrive", f"{self.API}/deals", deal, headers)["data"]["id"]
        _post("Pipedrive", f"{self.API}/notes", {"content": describe(lead, pitch), "deal_id": deal_id}, headers)
        return CrmLink(crm=self.name, external_id=str(deal_id))


def configured(settings: Settings) -> list[Crm]:
    crms: list[Crm] = []
    if settings.hubspot_token:
        crms.append(HubSpot(settings.hubspot_token.get_secret_value()))
    if settings.pipedrive_token:
        crms.append(Pipedrive(settings.pipedrive_token.get_secret_value()))
    return crms
