"""Billing: the workspace's plan and usage, Stripe Checkout and portal links, and Stripe's webhook."""

import logging

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select

from gigscout import billing
from gigscout.platform.billing import BillingError
from gigscout.platform.tables import Subscription
from gigscout.web.deps import AdminDep, PlatformDep, SessionDep, WsDep, audit
from gigscout.web.routes_inbound import _body
from gigscout.web.schemas import BillingOut, CheckoutIn, PlanOut

log = logging.getLogger(__name__)
router = APIRouter(tags=["billing"])


@router.get("/api/billing")
def billing_status(platform: PlatformDep, session: SessionDep, ws: WsDep) -> BillingOut:
    allowed, used = platform.billing.entitlement(ws.id), platform.billing.usage(ws.id)
    prices = platform.billing.prices() if allowed.billed else {}
    configured = billing.price_ids(platform.settings)
    customer = session.scalar(select(Subscription.stripe_customer_id).where(Subscription.workspace_id == ws.id))
    return BillingOut(
        enabled=allowed.billed, plan=allowed.plan, status=allowed.status, can_work=allowed.can_work,
        reason=allowed.reason, trial_ends_at=allowed.trial_ends_at, current_period_end=allowed.current_period_end,
        members_limit=allowed.members, runs_limit=allowed.runs_per_month, members=used["members"],
        runs_this_month=used["runs_this_month"], can_manage=bool(customer) and allowed.billed,
        plans=[PlanOut(id=p.id, label=p.label, price=prices.get(p.id), members=p.members,
                       runs_per_month=p.runs_per_month) for p in billing.PLANS.values() if p.id in configured],
    )


@router.post("/api/billing/checkout")
def checkout(body: CheckoutIn, request: Request, platform: PlatformDep, session: SessionDep, ws: AdminDep) -> dict:
    """Where to pay: Stripe's hosted Checkout. The plan starts when Stripe confirms it (the webhook)."""
    try:
        url = platform.billing.checkout_url(ws.id, body.plan, ws.email, _base(platform, request))
    except BillingError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    audit(session, ws, "billing.checkout", body.plan)
    session.commit()
    return {"url": url}


@router.post("/api/billing/portal")
def portal(request: Request, platform: PlatformDep, ws: AdminDep) -> dict:
    """Stripe's customer portal: change card, switch plan, download invoices, cancel."""
    try:
        return {"url": platform.billing.portal_url(ws.id, _base(platform, request))}
    except BillingError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc


@router.post("/webhooks/stripe", tags=["public"])
async def stripe_webhook(request: Request, platform: PlatformDep) -> dict:
    payload = await _body(request)
    try:
        result = platform.billing.handle_webhook(payload, request.headers.get("stripe-signature"))
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid signature") from None
    except BillingError as exc:
        log.warning("Stripe webhook refused: %s", exc)
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from None
    return {"status": result}


def _base(platform, request: Request) -> str:
    return (platform.settings.public_url or str(request.base_url)).rstrip("/")
