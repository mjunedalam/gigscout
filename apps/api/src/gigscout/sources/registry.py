"""Builds the set of enabled pull sources. Add a new one here (see docs/SOURCES.md).

Inbound channels (Google Ads lead forms) push leads to the API instead; see `gigscout.inbound`.
"""

from gigscout.config import Settings
from gigscout.http import PoliteClient
from gigscout.sources.base import Source
from gigscout.sources.freelancer import FreelancerSource
from gigscout.sources.remoteok import RemoteOkSource
from gigscout.sources.remotive import RemotiveSource
from gigscout.sources.rss import RssSource

WWR_FEEDS = (
    "https://weworkremotely.com/categories/remote-programming-jobs.rss",
    "https://weworkremotely.com/categories/remote-devops-sysadmin-jobs.rss",
)


def build_sources(settings: Settings, client: PoliteClient) -> dict[str, Source]:
    sources: list[Source] = [
        FreelancerSource(client),
        RemoteOkSource(client),
        RemotiveSource(client),
        RssSource(client, "weworkremotely", WWR_FEEDS, kind="hiring"),
    ]
    if settings.rss_feeds:
        sources.append(RssSource(client, "rss", settings.rss_feeds, kind=settings.rss_feeds_kind))
    return {source.name: source for source in sources}
