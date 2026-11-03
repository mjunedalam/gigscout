"""Unauthenticated endpoints: health check and the Google Ads webhook (authenticated by its shared key)."""

import logging

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from gigscout.inbound.google_ads import GoogleAdsLeadForm, key_matches, to_lead
from gigscout.web.deps import PlatformDep

log = logging.getLogger(__name__)

router = APIRouter(tags=["public"])


class WebhookAck(BaseModel):
    status: str


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.post("/webhooks/google-ads")
def google_ads_lead(form: GoogleAdsLeadForm, platform: PlatformDep) -> WebhookAck:
    """Receiver for Google Ads lead form webhooks. Configure the same key here and in Google Ads."""
    service = platform.service
    expected = service.deps.settings.google_ads_webhook_key
    if expected is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Google Ads webhook is not enabled")
    if not key_matches(form, expected.get_secret_value()):
        log.warning("Rejected Google Ads webhook call with a wrong key (lead %s)", form.lead_id)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid google_key")
    if form.is_test:
        return WebhookAck(status="test_received")
    lead = to_lead(form)
    stored = service.ingest_inbound(lead)
    if stored:
        platform.bus.publish("lead.inbound", {"id": lead.id, "title": lead.title})
    return WebhookAck(status="stored" if stored else "duplicate")
