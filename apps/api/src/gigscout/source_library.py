"""A library of public websites worth searching, per kind of company, each added in one click.

Every entry was checked on 2026-11-03 with the connector probe itself: it is a public site, its robots.txt allows
automated access, and it returned listings. Sites that refused (robots.txt) or blocked automated requests were left
out. Adding still goes through the normal connector checks, so a site that changes its mind is refused then.

Public tenders (UK Contracts Finder, Find a Tender, EU TED, US SAM.gov) are built-in sources using their official
APIs, so they are not listed here.
"""

from dataclasses import dataclass

from gigscout.models import LeadKind
from gigscout.profile_templates import closest_template

SOFTWARE, MARKETING, DESIGN, RECRUITMENT = "Software agency", "Marketing agency", "Design studio", "Recruitment agency"
LAW, ACCOUNTING, CONSTRUCTION, IT = "Law firm", "Accounting firm", "Construction contractor", "IT services & support"
TENDER_LED = frozenset({LAW, CONSTRUCTION})  # their clients mostly buy through public tenders (built in)
CONSULTING, VIDEO, TRANSLATION = "Management consulting", "Video production", "Translation agency"


@dataclass(frozen=True)
class LibrarySource:
    name: str
    url: str
    description: str
    company_types: frozenset[str]
    lead_kind: LeadKind  # project = someone wants work done; hiring = a company hiring (pitch your services instead)
    region: str = "Worldwide"


def _src(name: str, url: str, description: str, types: tuple[str, ...], kind: LeadKind, region: str = "Worldwide"):
    return LibrarySource(name, url, description, frozenset(types), kind, region)


LIBRARY: tuple[LibrarySource, ...] = (
    _src("PeoplePerHour", "https://www.peopleperhour.com/freelance-jobs",
         "Freelance projects posted by clients", (SOFTWARE, MARKETING, DESIGN, VIDEO, TRANSLATION, ACCOUNTING),
         "project"),
    _src("Python.org jobs", "https://www.python.org/jobs/", "Python roles from the official job board",
         (SOFTWARE,), "hiring"),
    _src("Hacker News jobs", "https://hnrss.org/jobs", "Jobs posted by Y Combinator startups",
         (SOFTWARE, RECRUITMENT), "hiring"),
    _src("Hacker News: Who is hiring", "https://hnrss.org/whoishiring/jobs",
         "The monthly hiring thread, one entry per company", (SOFTWARE, RECRUITMENT, IT), "hiring"),
    _src("Larajobs", "https://larajobs.com/feed", "Laravel and PHP roles", (SOFTWARE,), "hiring"),
    _src("Crypto Jobs List", "https://cryptojobslist.com/rss", "Web3 and crypto company roles",
         (SOFTWARE, MARKETING, DESIGN), "hiring"),
    _src("Himalayas", "https://himalayas.app/jobs/rss", "Remote roles at tech companies",
         (SOFTWARE, MARKETING, DESIGN, RECRUITMENT), "hiring"),
    _src("Jobicy", "https://jobicy.com/?feed=job_feed", "Remote jobs across development, marketing and design",
         (SOFTWARE, MARKETING, DESIGN, RECRUITMENT), "hiring"),
    _src("Working Nomads", "https://www.workingnomads.com/jobs", "Curated remote jobs",
         (SOFTWARE, MARKETING, RECRUITMENT), "hiring"),
    _src("NoDesk", "https://nodesk.co/remote-jobs/", "Remote jobs at remote-first companies",
         (SOFTWARE, MARKETING, DESIGN), "hiring"),
    _src("Dribbble jobs", "https://dribbble.com/jobs", "Design roles and studios hiring designers",
         (DESIGN,), "hiring"),
    _src("Coroflot", "https://www.coroflot.com/design-jobs/rss", "Industrial, graphic and UX design jobs",
         (DESIGN,), "hiring"),
    _src("Mediabistro", "https://www.mediabistro.com/jobs/feed/", "Media, content, marketing and video roles",
         (MARKETING, VIDEO, TRANSLATION), "hiring", "US"),
    _src("ReliefWeb jobs", "https://reliefweb.int/jobs/rss.xml",
         "NGO and humanitarian roles and consultancies", (CONSULTING, TRANSLATION, ACCOUNTING), "contract"),
    _src("Idealist", "https://www.idealist.org/en/jobs", "Non-profit roles and consultancies",
         (CONSULTING, MARKETING, TRANSLATION), "contract"),
)


def for_company_type(company_type: str) -> list[LibrarySource]:
    """Sources for a company type: an exact match, else the closest template's type, else nothing."""
    exact = [s for s in LIBRARY if company_type in s.company_types]
    if exact:
        return exact
    template = closest_template(company_type)
    return [s for s in LIBRARY if template and template.company_type in s.company_types]
