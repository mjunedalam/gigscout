"""Plans, trials and what a workspace may do: the rules behind Stripe billing.

Billing is off until Stripe is configured (a secret key, a webhook secret and at least one plan price): a
self-hosted install has no limits. Once on, a new workspace gets a trial, then needs an active subscription to start
agent runs. Its data stays readable whatever happens. Workspaces listed as exempt (the operator's own) never pay.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from gigscout.config import Settings

TRIAL_DAYS = 14
PAYING = ("active", "trialing")  # Stripe subscription statuses that allow work


@dataclass(frozen=True)
class Plan:
    id: str
    label: str
    members: int
    runs_per_month: int
    price_setting: str  # the Settings field holding its Stripe price id


PLANS = {
    "starter": Plan("starter", "Starter", members=3, runs_per_month=300, price_setting="stripe_price_starter"),
    "growth": Plan("growth", "Growth", members=15, runs_per_month=2000, price_setting="stripe_price_growth"),
}
TRIAL_PLAN = PLANS["starter"]  # what a trial may use


@dataclass(frozen=True)
class Entitlement:
    billed: bool  # False: billing is off or the workspace is exempt, so nothing is limited
    plan: str  # trial | starter | growth | unlimited
    status: str  # unlimited | trialing | active | past_due | canceled | expired | ...
    members: int | None  # limits; None means no limit
    runs_per_month: int | None
    can_work: bool
    reason: str = ""  # why work is blocked, in words for the UI
    trial_ends_at: datetime | None = None
    current_period_end: datetime | None = None


def enabled(settings: Settings) -> bool:
    return bool(settings.stripe_secret_key and settings.stripe_webhook_secret and price_ids(settings))


def price_ids(settings: Settings) -> dict[str, str]:
    """plan id -> Stripe price id, for the plans that are set up."""
    return {plan.id: price for plan in PLANS.values() if (price := getattr(settings, plan.price_setting))}


def plan_for_price(settings: Settings, price_id: str | None) -> str | None:
    return next((plan for plan, price in price_ids(settings).items() if price == price_id), None)


def entitlement(settings: Settings, workspace_id: int, workspace_created: datetime, subscription,
                now: datetime | None = None) -> Entitlement:
    """What this workspace may do now. `subscription` is its Subscription row, or None if it never subscribed."""
    if not enabled(settings) or workspace_id in settings.billing_exempt_workspace_ids:
        return Entitlement(billed=False, plan="unlimited", status="unlimited", members=None, runs_per_month=None,
                           can_work=True)
    now = now or datetime.now(UTC)
    if subscription is not None and subscription.status in PAYING and subscription.plan in PLANS:
        plan = PLANS[subscription.plan]
        return Entitlement(billed=True, plan=plan.id, status=subscription.status, members=plan.members,
                           runs_per_month=plan.runs_per_month, can_work=True,
                           current_period_end=_aware(subscription.current_period_end))
    if subscription is not None and subscription.stripe_subscription_id:  # subscribed once, no longer paying
        reason = ("Your last payment did not go through: update your card to keep running the agents."
                  if subscription.status in ("past_due", "unpaid", "incomplete")
                  else "Your subscription has ended: choose a plan to run the agents again.")
        plan = PLANS.get(subscription.plan, TRIAL_PLAN)  # its limits still show; can_work is what pauses runs
        return Entitlement(billed=True, plan=subscription.plan, status=subscription.status, members=plan.members,
                           runs_per_month=plan.runs_per_month, can_work=False, reason=reason)
    trial_ends = _aware(workspace_created) + timedelta(days=TRIAL_DAYS)
    if now < trial_ends:
        return Entitlement(billed=True, plan="trial", status="trialing", members=TRIAL_PLAN.members,
                           runs_per_month=TRIAL_PLAN.runs_per_month, can_work=True, trial_ends_at=trial_ends)
    return Entitlement(billed=True, plan="trial", status="expired", members=TRIAL_PLAN.members,
                       runs_per_month=TRIAL_PLAN.runs_per_month, can_work=False, trial_ends_at=trial_ends,
                       reason="Your free trial has ended: choose a plan to keep running the agents.")


def month_start(now: datetime | None = None) -> datetime:
    now = now or datetime.now(UTC)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)
