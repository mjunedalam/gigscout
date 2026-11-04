"""Stripe billing for workspaces: checkout, the customer portal, webhook sync and usage limits.

Card details never touch GigScout: people pay on Stripe's hosted Checkout and manage their plan in Stripe's portal.
Webhooks are verified with the signing secret, and the subscription is then read back from Stripe, so the stored
status is always Stripe's latest, whatever order events arrive in.
"""

import logging
import threading
import time
from datetime import UTC, datetime

from sqlalchemy import func, select

from gigscout import billing
from gigscout.billing import Entitlement
from gigscout.config import Settings
from gigscout.platform.db import SessionFactory
from gigscout.platform.tables import Membership, Run, Subscription, Workspace

log = logging.getLogger(__name__)

PRICE_CACHE_SECONDS = 3600
HANDLED = ("checkout.session.completed", "customer.subscription.created", "customer.subscription.updated",
           "customer.subscription.deleted", "invoice.paid", "invoice.payment_failed")


class BillingError(Exception):
    pass


class BillingService:
    def __init__(self, sessions: SessionFactory, settings: Settings, client_factory=None) -> None:
        self._sessions = sessions
        self._settings = settings
        self._client_factory = client_factory  # tests pass a fake Stripe client
        self._prices: tuple[float, dict[str, str]] = (0.0, {})
        self._lock = threading.Lock()

    @property
    def enabled(self) -> bool:
        return billing.enabled(self._settings)

    # --- what a workspace may do -----------------------------------------------------------------------------
    def entitlement(self, workspace_id: int) -> Entitlement:
        with self._sessions() as session:
            workspace = session.get(Workspace, workspace_id)
            subscription = session.get(Subscription, workspace_id)
            created = workspace.created_at if workspace else datetime.now(UTC)
        return billing.entitlement(self._settings, workspace_id, created, subscription)

    def usage(self, workspace_id: int) -> dict[str, int]:
        with self._sessions() as session:
            members = session.scalar(select(func.count()).select_from(Membership)
                                     .where(Membership.workspace_id == workspace_id))
            runs = session.scalar(select(func.count()).select_from(Run).where(
                Run.workspace_id == workspace_id, Run.created_at >= billing.month_start()))
        return {"members": members or 0, "runs_this_month": runs or 0}

    def run_blocked(self, workspace_id: int) -> str | None:
        """Why this workspace cannot start a run now, or None."""
        allowed = self.entitlement(workspace_id)
        if not allowed.can_work:
            return allowed.reason
        if allowed.runs_per_month is not None and self.usage(workspace_id)["runs_this_month"] >= allowed.runs_per_month:
            return (f"This month's {allowed.runs_per_month} runs are used up: upgrade your plan or wait for "
                    "next month.")
        return None

    def member_blocked(self, workspace_id: int) -> str | None:
        allowed = self.entitlement(workspace_id)
        if allowed.members is not None and self.usage(workspace_id)["members"] >= allowed.members:
            return f"Your plan includes {allowed.members} people: upgrade to add more."
        return None

    # --- Stripe ----------------------------------------------------------------------------------------------
    def prices(self) -> dict[str, str]:
        """plan -> price as people see it ("$49/month"), from Stripe, cached for an hour."""
        if not self.enabled:
            return {}
        with self._lock:
            fetched_at, cached = self._prices
            if time.monotonic() - fetched_at < PRICE_CACHE_SECONDS:
                return cached
        labels = {}
        for plan, price_id in billing.price_ids(self._settings).items():
            try:
                price = _plain(self._client().v1.prices.retrieve(price_id))
            except Exception:
                log.warning("Could not read the Stripe price for %s", plan, exc_info=True)
                continue
            labels[plan] = _price_label(price)
        with self._lock:
            self._prices = (time.monotonic(), labels)
        return labels

    def checkout_url(self, workspace_id: int, plan: str, email: str, base_url: str) -> str:
        price = billing.price_ids(self._settings).get(plan)
        if not self.enabled or price is None:
            raise BillingError("That plan is not available")
        with self._sessions() as session:
            row = session.get(Subscription, workspace_id)
            customer = row.stripe_customer_id if row else None
        params = {
            "mode": "subscription",
            "line_items": [{"price": price, "quantity": 1}],
            "client_reference_id": str(workspace_id),
            "metadata": {"workspace_id": str(workspace_id)},
            "subscription_data": {"metadata": {"workspace_id": str(workspace_id)}},
            "success_url": f"{base_url}/admin/billing?checkout=done",
            "cancel_url": f"{base_url}/admin/billing?checkout=cancelled",
            "allow_promotion_codes": True,
        }
        params.update({"customer": customer} if customer else {"customer_email": email})
        try:
            return self._client().v1.checkout.sessions.create(params=params).url
        except Exception as exc:  # a wrong key, Stripe down: say so instead of failing the request
            log.warning("Stripe Checkout failed", exc_info=True)
            raise BillingError(f"Stripe could not start checkout ({type(exc).__name__}); try again shortly") from exc

    def portal_url(self, workspace_id: int, base_url: str) -> str:
        with self._sessions() as session:
            row = session.get(Subscription, workspace_id)
            customer = row.stripe_customer_id if row else None
        if not self.enabled or not customer:
            raise BillingError("Subscribe to a plan first")
        try:
            session = self._client().v1.billing_portal.sessions.create(
                params={"customer": customer, "return_url": f"{base_url}/admin/billing"})
        except Exception as exc:
            log.warning("Stripe billing portal failed", exc_info=True)
            raise BillingError(f"Stripe could not open billing ({type(exc).__name__}); try again shortly") from exc
        return session.url

    def handle_webhook(self, payload: bytes, signature: str | None) -> str:
        """Verify and apply one Stripe event. Raises ValueError for a bad or missing signature."""
        if not self.enabled:
            raise ValueError("Billing is not configured")
        try:
            event = self._client().construct_event(payload, signature or "",
                                                   self._settings.stripe_webhook_secret.get_secret_value())
        except Exception as exc:  # stripe.SignatureVerificationError, or a malformed body
            raise ValueError("Invalid Stripe signature") from exc
        if event.type not in HANDLED:
            return "ignored"
        obj = _plain(event.data.object)
        subscription_id, workspace_id, customer = _ids(event.type, obj)
        if workspace_id is None and (subscription_id or customer):
            workspace_id = self._known_workspace(subscription_id, customer)
        if workspace_id is None or subscription_id is None:
            log.info("Stripe %s for an unknown workspace; ignored", event.type)
            return "ignored"
        self.sync(workspace_id, subscription_id, customer)
        return "synced"

    def sync(self, workspace_id: int, subscription_id: str, customer: str | None = None) -> Subscription:
        """Store Stripe's current view of a subscription (read back from Stripe, never taken from the event)."""
        sub = _plain(self._client().v1.subscriptions.retrieve(subscription_id))
        owner = (sub.get("metadata") or {}).get("workspace_id")
        if owner is not None and str(owner) != str(workspace_id):
            raise BillingError("This subscription belongs to another workspace")
        item = (sub.get("items") or {}).get("data", [{}])[0]
        price_id = (item.get("price") or {}).get("id")
        period_end = sub.get("current_period_end") or item.get("current_period_end")
        with self._sessions() as session:
            row = session.get(Subscription, workspace_id) or Subscription(workspace_id=workspace_id)
            row.stripe_subscription_id = sub.get("id")
            row.stripe_customer_id = customer or sub.get("customer") or row.stripe_customer_id
            row.status = sub.get("status") or "incomplete"
            row.plan = billing.plan_for_price(self._settings, price_id) or row.plan
            row.current_period_end = datetime.fromtimestamp(period_end, UTC) if period_end else None
            session.merge(row)
            session.commit()
            return row

    def _known_workspace(self, subscription_id: str | None, customer: str | None) -> int | None:
        with self._sessions() as session:
            known = Subscription.stripe_subscription_id == subscription_id
            if customer:
                known = known | (Subscription.stripe_customer_id == customer)
            stmt = select(Subscription.workspace_id).where(known)
            return session.scalar(stmt.limit(1))

    def _client(self):
        if self._client_factory is not None:
            return self._client_factory()
        from stripe import StripeClient

        return StripeClient(self._settings.stripe_secret_key.get_secret_value())


def _ids(event_type: str, obj) -> tuple[str | None, int | None, str | None]:
    """(subscription id, workspace id if the event names it, customer id) for the events we handle."""
    metadata = obj.get("metadata") or {}
    workspace = metadata.get("workspace_id")
    if event_type == "checkout.session.completed":
        workspace = obj.get("client_reference_id") or workspace
        subscription = obj.get("subscription")
    elif event_type.startswith("customer.subscription."):
        subscription = obj.get("id")
    else:  # invoices: the subscription moved under parent.subscription_details in newer API versions
        details = (obj.get("parent") or {}).get("subscription_details") or {}
        subscription = obj.get("subscription") or details.get("subscription")
        workspace = workspace or (details.get("metadata") or {}).get("workspace_id")
    try:
        workspace_id = int(workspace) if workspace is not None else None
    except (TypeError, ValueError):
        workspace_id = None
    return subscription, workspace_id, obj.get("customer")


def _plain(value) -> dict:
    """Stripe objects are not dicts (v12+): read them as plain data."""
    return value.to_dict() if hasattr(value, "to_dict") else dict(value)


def _price_label(price) -> str:
    amount = (price.get("unit_amount") or 0) / 100
    currency = (price.get("currency") or "usd").upper()
    symbol = {"USD": "$", "GBP": "£", "EUR": "€"}.get(currency, f"{currency} ")
    interval = (price.get("recurring") or {}).get("interval", "month")
    shown = f"{amount:,.0f}" if amount == int(amount) else f"{amount:,.2f}"
    return f"{symbol}{shown}/{interval}"
