"""The web API: `gigscout serve`, then open http://127.0.0.1:8000/docs. The React app lives in apps/web."""

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from gigscout.config import get_settings
from gigscout.platform.container import Platform
from gigscout.web import (
    routes_admin,
    routes_auth,
    routes_billing,
    routes_competitors,
    routes_inbound,
    routes_insights,
    routes_integrations,
    routes_knowledge,
    routes_leads,
    routes_ops,
    routes_outreach,
    routes_pitches,
    routes_public,
    routes_replies,
    routes_reports,
    routes_research,
    routes_workspaces,
)

log = logging.getLogger(__name__)

PlatformFactory = Callable[[], Platform]


def create_app(platform_factory: PlatformFactory | None = None) -> FastAPI:
    """Build the app. Tests pass a factory that wires fakes; production builds everything from settings."""
    factory = platform_factory or (lambda: Platform.build(get_settings()))

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        platform = factory()
        platform.start()
        app.state.platform = platform
        ticker = asyncio.create_task(_publish_metrics(platform))
        try:
            yield
        finally:
            ticker.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await ticker
            platform.stop()

    app = FastAPI(
        title="GigScout",
        version="0.2.0",
        description="AI lead scout for software development agencies: finds, qualifies and briefs client leads.",
        lifespan=lifespan,
    )
    origins = get_settings().cors_origins
    if origins:
        app.add_middleware(
            CORSMiddleware, allow_origins=origins, allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"], allow_headers=["content-type", "authorization"],
        )
    routers = (routes_public, routes_auth, routes_leads, routes_ops, routes_insights, routes_admin, routes_outreach,
               routes_integrations, routes_inbound, routes_workspaces, routes_billing, routes_competitors,
               routes_pitches, routes_reports, routes_knowledge,
               routes_replies, routes_research)
    for module in routers:
        app.include_router(module.router)
    return app


async def _publish_metrics(platform: Platform) -> None:
    """Push a live metrics snapshot to every open dashboard on a fixed interval (only while someone listens)."""
    while True:
        await asyncio.sleep(platform.settings.metrics_interval_seconds)
        for workspace_id in platform.bus.watched_workspaces():  # only workspaces someone is looking at
            try:
                data = await asyncio.to_thread(_snapshot, platform, workspace_id)
            except Exception as exc:  # a metrics hiccup must never kill the ticker
                log.warning("Metrics snapshot failed: %s", exc)
                continue
            platform.bus.publish("metrics.snapshot", data, workspace_id)


def _snapshot(platform: Platform, workspace_id: int) -> dict:
    with platform.sessions() as session:
        return routes_insights.snapshot(platform, session, workspace_id)


app = create_app()
