"""Starting points for common kinds of company, so any business can set up a profile in a minute.

A template only prefills the form: the company edits it, or asks the LLM for a suggestion tailored to its own words.
"""

from dataclasses import dataclass

from gigscout.models import ALL_LEAD_KINDS, LeadKind

# Words too generic to identify a company type on their own.
GENERIC_WORDS = {"agency", "firm", "studio", "services", "and", "&", "company", "contractor", "support"}


@dataclass(frozen=True)
class ProfileTemplate:
    company_type: str
    description: str
    services: tuple[str, ...]
    skills: tuple[str, ...]
    keywords: tuple[str, ...]
    exclude: tuple[str, ...]
    kinds: tuple[LeadKind, ...] = ALL_LEAD_KINDS


TEMPLATES: tuple[ProfileTemplate, ...] = (
    ProfileTemplate(
        "Software agency", "Builds custom web, mobile and AI software for clients",
        ("web application development", "mobile app development", "api development", "ai integration"),
        ("python", "react", "node.js", "aws"),
        ("web app", "mobile app", "saas mvp", "api integration"),
        ("wordpress", "unpaid", "data entry"),
    ),
    ProfileTemplate(
        "Marketing agency", "Grows brands online with search, ads, social and content",
        ("seo", "google ads management", "social media marketing", "content marketing", "email marketing"),
        ("seo", "ppc", "meta ads", "google analytics", "copywriting"),
        ("seo", "ppc", "social media manager", "digital marketing", "content strategy"),
        ("unpaid", "followers", "fake reviews"),
    ),
    ProfileTemplate(
        "Design studio", "Brand identity, UI/UX and product design",
        ("brand identity", "ui/ux design", "website design", "packaging design"),
        ("figma", "branding", "illustration", "design systems"),
        ("ui ux design", "brand identity", "logo design", "web design"),
        ("unpaid", "spec work", "contest"),
    ),
    ProfileTemplate(
        "Recruitment agency", "Finds and places candidates for employers",
        ("permanent recruitment", "contract staffing", "executive search"),
        ("sourcing", "headhunting", "technical recruitment"),
        ("hiring", "recruiter", "staffing", "talent acquisition"),
        ("unpaid", "commission only"),
        ("hiring", "contract", "inbound"),
    ),
    ProfileTemplate(
        "Law firm", "Legal advice and representation for businesses",
        ("contract drafting", "corporate law", "employment law", "intellectual property", "compliance"),
        ("gdpr", "trademarks", "commercial contracts", "litigation"),
        ("legal counsel", "contract review", "trademark", "compliance"),
        ("free consultation", "unpaid"),
        ("project", "contract", "inbound"),
    ),
    ProfileTemplate(
        "Accounting firm", "Bookkeeping, tax and finance for small businesses",
        ("bookkeeping", "tax returns", "payroll", "financial reporting", "virtual cfo"),
        ("xero", "quickbooks", "vat", "ifrs"),
        ("bookkeeper", "accountant", "tax preparation", "payroll"),
        ("unpaid", "crypto tax evasion"),
    ),
    ProfileTemplate(
        "Construction contractor", "Builds and renovates residential and commercial property",
        ("renovation", "new build", "fit-out", "extensions", "project management"),
        ("planning permission", "building regulations", "health and safety"),
        ("renovation", "construction tender", "fit out", "building contractor"),
        ("diy", "unpaid quote"),
        ("project", "contract", "inbound"),
    ),
    ProfileTemplate(
        "IT services & support", "Managed IT, networks, cloud and cybersecurity for businesses",
        ("managed it services", "cloud migration", "cybersecurity", "network setup", "help desk"),
        ("microsoft 365", "azure", "aws", "firewalls", "backup"),
        ("it support", "managed services", "cybersecurity", "cloud migration"),
        ("unpaid", "hacking"),
    ),
    ProfileTemplate(
        "Management consulting", "Strategy, operations and transformation for organisations",
        ("strategy consulting", "operations improvement", "change management", "due diligence"),
        ("lean", "process mapping", "financial modelling"),
        ("consultant", "strategy", "business analysis", "process improvement"),
        ("unpaid", "equity only"),
    ),
    ProfileTemplate(
        "Video production", "Commercials, brand films and social video",
        ("brand films", "commercials", "animation", "event filming", "editing"),
        ("premiere pro", "after effects", "drone filming", "motion graphics"),
        ("video production", "videographer", "video editor", "animation"),
        ("unpaid", "exposure"),
    ),
    ProfileTemplate(
        "Translation agency", "Translation, localisation and interpreting",
        ("document translation", "website localisation", "interpreting", "subtitling"),
        ("certified translation", "legal translation", "medical translation"),
        ("translation", "localization", "translator", "interpreter"),
        ("unpaid", "machine translation post-editing at low rates"),
    ),
)


def closest_template(company_type: str) -> ProfileTemplate | None:
    """The template whose company type shares a distinctive word with what the user typed, if any."""
    words = {w for w in company_type.lower().replace("/", " ").split() if w not in GENERIC_WORDS}
    for template in TEMPLATES:
        if words & {w for w in template.company_type.lower().split() if w not in GENERIC_WORDS}:
            return template
    return None
