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
    routes_insights,
    routes_integrations,
    routes_leads,
    routes_ops,
    routes_outreach,
    routes_public,
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
               routes_integrations)
    for module in routers:
        app.include_router(module.router)
    return app


async def _publish_metrics(platform: Platform) -> None:
    """Push a live metrics snapshot to every open dashboard on a fixed interval (only while someone listens)."""
    while True:
        await asyncio.sleep(platform.settings.metrics_interval_seconds)
        if not platform.bus.subscriber_count:
            continue
        try:
            data = await asyncio.to_thread(_snapshot, platform)
        except Exception as exc:  # a metrics hiccup must never kill the ticker
            log.warning("Metrics snapshot failed: %s", exc)
            continue
        platform.bus.publish("metrics.snapshot", data)


def _snapshot(platform: Platform) -> dict:
    with platform.sessions() as session:
        return routes_insights.snapshot(platform, session)


app = create_app()
