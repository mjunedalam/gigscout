"""Stripe billing: trials, plans and limits, Checkout and the portal, and the verified webhook."""

import hashlib
import hmac
import json
import time
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
import stripe
from pydantic import SecretStr

from gigscout import billing
from gigscout.platform.tables import Subscription, Workspace
from tests.conftest import PASSWORD, login

WHSEC = "whsec_test_secret"
BILLING = {"stripe_secret_key": SecretStr("sk_test_x"), "stripe_webhook_secret": SecretStr(WHSEC),
           "stripe_price_starter": "price_starter1", "stripe_price_growth": "price_growth1"}
OWNER = "boss@bright-studio.com"


class FakeStripe:
    """The parts of StripeClient GigScout uses; webhook signatures are checked by Stripe's real code."""

    def __init__(self, subscriptions: dict) -> None:
        self.subscriptions = subscriptions  # id -> what Stripe would return
        self.checkouts: list[dict] = []
        self.v1 = SimpleNamespace(
            checkout=SimpleNamespace(sessions=SimpleNamespace(create=self._checkout)),
            billing_portal=SimpleNamespace(sessions=SimpleNamespace(
                create=lambda params: SimpleNamespace(url=f"https://billing.stripe.test/{params['customer']}"))),
            subscriptions=SimpleNamespace(retrieve=lambda sub_id: self.subscriptions[sub_id]),
            prices=SimpleNamespace(retrieve=lambda price_id: {
                "unit_amount": 4900 if price_id == "price_starter1" else 14900, "currency": "usd",
                "recurring": {"interval": "month"}}),
        )

    def _checkout(self, params):
        self.checkouts.append(params)
        return SimpleNamespace(url="https://checkout.stripe.test/session")

    @staticmethod
    def construct_event(payload, signature, secret):
        return stripe.Webhook.construct_event(payload, signature, secret)


def signed(event: dict, secret: str = WHSEC) -> tuple[bytes, dict]:
    payload = json.dumps(event).encode()
    stamp = int(time.time())
    digest = hmac.new(secret.encode(), f"{stamp}.".encode() + payload, hashlib.sha256).hexdigest()
    return payload, {"stripe-signature": f"t={stamp},v1={digest}", "content-type": "application/json"}


def subscription(sub_id="sub_1", status="active", price="price_growth1", workspace="2", customer="cus_1"):
    return {"id": sub_id, "status": status, "customer": customer, "metadata": {"workspace_id": workspace},
            "items": {"data": [{"price": {"id": price}, "current_period_end": int(time.time()) + 30 * 86400}]}}


def event(kind: str, obj: dict) -> dict:
    return {"id": "evt_1", "object": "event", "type": kind, "data": {"object": obj}}


@pytest.fixture
def billed(web):
    """An app with billing on, a fake Stripe, and a second (paying) workspace whose owner is signed in."""
    fake = FakeStripe({})
    client, platform = web(**BILLING)
    platform.billing._client_factory = lambda: fake
    login(client)
    ws = client.post("/api/workspaces", json={"name": "Bright Studio"}).json()["id"]
    client.post("/api/admin/users", headers={"X-Workspace": str(ws)},
                json={"email": OWNER, "name": "Boss", "role": "owner", "password": PASSWORD})
    login(client, OWNER)
    return client, platform, fake, ws


# --- the rules -------------------------------------------------------------------------------------------------
def test_without_stripe_nothing_is_limited(settings):
    allowed = billing.entitlement(settings, 5, datetime(2020, 1, 1, tzinfo=UTC), None)
    assert allowed.can_work and allowed.plan == "unlimited" and allowed.runs_per_month is None


def test_the_operators_own_workspace_is_exempt(settings):
    configured = settings.model_copy(update=BILLING)
    assert billing.entitlement(configured, 1, datetime(2020, 1, 1, tzinfo=UTC), None).can_work


def test_a_trial_lasts_fourteen_days_with_starter_limits(settings):
    configured = settings.model_copy(update=BILLING)
    now = datetime(2026, 11, 4, tzinfo=UTC)
    fresh = billing.entitlement(configured, 2, now - timedelta(days=3), None, now=now)
    assert fresh.can_work and fresh.plan == "trial" and fresh.members == 3 and fresh.runs_per_month == 300
    over = billing.entitlement(configured, 2, now - timedelta(days=15), None, now=now)
    assert not over.can_work and "trial has ended" in over.reason


def test_lapsed_subscriptions_say_why(settings):
    configured = settings.model_copy(update=BILLING)
    created = datetime(2026, 1, 1, tzinfo=UTC)
    late = Subscription(workspace_id=2, plan="growth", status="past_due", stripe_subscription_id="sub_1")
    ended = Subscription(workspace_id=2, plan="growth", status="canceled", stripe_subscription_id="sub_1")
    assert "payment did not go through" in billing.entitlement(configured, 2, created, late).reason
    assert "subscription has ended" in billing.entitlement(configured, 2, created, ended).reason
    paying = Subscription(workspace_id=2, plan="growth", status="active", stripe_subscription_id="sub_1")
    assert billing.entitlement(configured, 2, created, paying).members == 15


# --- the app ---------------------------------------------------------------------------------------------------
def test_billing_page_shows_plan_usage_and_stripe_prices(billed):
    client, _, _, _ = billed
    info = client.get("/api/billing").json()
    assert info["enabled"] and info["plan"] == "trial" and info["can_work"] and info["members"] == 2
    assert {p["id"]: p["price"] for p in info["plans"]} == {"starter": "$49/month", "growth": "$149/month"}
    assert info["can_manage"] is False and client.post("/api/billing/portal").status_code == 409


def test_an_expired_trial_blocks_runs_but_not_reading(billed):
    client, platform, _, ws = billed
    with platform.sessions() as session:
        session.get(Workspace, ws).created_at = datetime.now(UTC) - timedelta(days=30)
        session.commit()
    profile = client.post("/api/profiles", json={"name": "Bright", "pitch": "Apps", "skills": ["react"]}).json()
    started = client.post("/api/runs", json={"profile_id": profile["id"], "mode": "pipeline"})
    assert started.status_code == 402 and "trial has ended" in started.json()["detail"]
    assert client.get("/api/leads").status_code == 200 and client.get("/api/runs").status_code == 200
    login(client)
    assert client.get("/api/billing", headers={"X-Workspace": "1"}).json()["can_work"]  # exempt


def test_a_plan_limits_the_team(billed):
    client, _, _, _ = billed
    added = client.post("/api/admin/users", json={"email": "third@b.com", "name": "Third", "password": PASSWORD})
    assert added.status_code == 201  # 3 of 3
    full = client.post("/api/admin/users", json={"email": "fourth@b.com", "name": "Fourth", "password": PASSWORD})
    assert full.status_code == 402 and "3 people" in full.json()["detail"]


def test_checkout_then_webhook_starts_the_plan(billed):
    client, _, fake, ws = billed
    assert client.post("/api/billing/checkout", json={"plan": "growth"}).json()["url"].startswith("https://checkout")
    params = fake.checkouts[0]
    assert params["client_reference_id"] == str(ws) and params["line_items"] == [{"price": "price_growth1",
                                                                                 "quantity": 1}]
    assert params["subscription_data"]["metadata"] == {"workspace_id": str(ws)} and params["customer_email"] == OWNER

    fake.subscriptions["sub_1"] = subscription(workspace=str(ws))
    payload, headers = signed(event("checkout.session.completed", {
        "object": "checkout.session", "client_reference_id": str(ws), "customer": "cus_1", "subscription": "sub_1"}))
    assert client.post("/webhooks/stripe", content=payload, headers=headers).json() == {"status": "synced"}

    info = client.get("/api/billing").json()
    assert info["plan"] == "growth" and info["status"] == "active" and info["members_limit"] == 15
    assert info["can_manage"] and client.post("/api/billing/portal").json()["url"].endswith("/cus_1")


def test_the_webhook_trusts_stripe_not_the_event_body(billed):
    client, _, fake, ws = billed
    fake.subscriptions["sub_1"] = subscription(workspace=str(ws))
    client.post("/webhooks/stripe", **dict(zip(("content", "headers"), signed(event(
        "checkout.session.completed", {"client_reference_id": str(ws), "customer": "cus_1", "subscription": "sub_1"})),
        strict=True)))
    fake.subscriptions["sub_1"] = subscription(workspace=str(ws), status="canceled")  # Stripe's latest
    stale = subscription(workspace=str(ws), status="active")  # an older event arriving late
    payload, headers = signed(event("customer.subscription.updated", stale))
    assert client.post("/webhooks/stripe", content=payload, headers=headers).status_code == 200
    assert client.get("/api/billing").json()["status"] == "canceled"


def test_forged_or_mismatched_webhooks_are_refused(billed):
    client, _, fake, ws = billed
    payload, headers = signed(event("checkout.session.completed", {"client_reference_id": str(ws),
                                                                    "subscription": "sub_1"}), secret="whsec_wrong")
    assert client.post("/webhooks/stripe", content=payload, headers=headers).status_code == 400
    assert client.post("/webhooks/stripe", content=payload).status_code == 400  # no signature at all

    fake.subscriptions["sub_9"] = subscription(sub_id="sub_9", workspace="1")  # paid for by someone else
    payload, headers = signed(event("checkout.session.completed", {"client_reference_id": str(ws),
                                                                    "subscription": "sub_9"}))
    assert client.post("/webhooks/stripe", content=payload, headers=headers).status_code == 400
    assert client.get("/api/billing").json()["plan"] == "trial"


def test_members_cannot_open_checkout(billed):
    client, _, _, _ = billed
    client.post("/api/admin/users", json={"email": "rep@b.com", "name": "Rep", "password": PASSWORD})
    login(client, "rep@b.com")
    assert client.post("/api/billing/checkout", json={"plan": "starter"}).status_code == 403


def test_when_stripe_fails_people_get_a_message_not_an_error(billed):
    client, _, fake, _ = billed

    def down(params):
        raise ConnectionError("stripe unreachable")

    fake.v1.checkout.sessions.create = down
    response = client.post("/api/billing/checkout", json={"plan": "starter"})
    assert response.status_code == 409 and "Stripe could not start checkout" in response.json()["detail"]
