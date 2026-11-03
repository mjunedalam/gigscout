"""Prompt templates. Kept in one place so they can be versioned and logged to MLflow.

{company} is the profile's company, e.g. 'Marketing agency "Bright Lane"'. No prompt assumes an industry: the
company type and profile say what the business sells.
"""

PLAN_QUERIES = """You do business development for {company}, finding clients and work it can win.
Search boxes on job boards, marketplaces and tender sites work best with short keyword queries (1-3 words).

Company profile:
{profile}

{extra}
Return up to {max_queries} distinct search queries that would surface clients or projects this company can win."""

BROADEN_HINT = (
    "A previous search with these queries found too few good leads: {previous}.\n"
    "Suggest broader or adjacent queries (related services, synonyms, industries the company serves)."
)

QUALIFY_LEAD = """You are a sharp business-development lead qualifying opportunities for {company}.

Company profile:
{profile}

Lead ({kind} from {source}):
Title: {title}
Client: {client}
Skills listed: {skills}
Budget: {budget}
Competing bids: {bids}
Description:
{description}

Lead kinds: project = a client wants work done; contract = a company wants contractors; hiring = a company hiring
in-house (pitch the company's services instead); inbound = the prospect contacted the company directly.

Score 0.0-1.0 how worth pursuing this is for the company: fit with what it sells and is good at, deal size versus
its minimum, scope clarity, and how winnable it is given the competition.
Give reasons in ONE sentence of at most 25 words.
List red flags (scam signals, off-platform payment requests, unpaid tests, vague scope, budget far too low for this
company) in at most 12 words, or leave empty if none.
Write a pitch: ONE opening line (at most 25 words) the company could use to start the conversation."""

SUMMARIZE = """Write a 3-4 sentence briefing for the sales team of {company} about today's best leads.
Mention the strongest 2-3 by title, why, and the suggested next step. No preamble.

Company:
{profile}

Leads:
{leads}"""

SUGGEST_PROFILE = """A company is setting up a lead-finding assistant. Suggest how it should describe itself.

Company type: {company_type}
In its own words: {description}

Suggest services it sells, its capabilities or specialities, short search queries (1-3 words) that would find its
clients or projects on job boards, marketplaces and tender sites, topics it never wants to see, and the client
industries it serves best. Use short, plain phrases a client would use."""

ANSWER_WITH_CONTEXT = """Answer the question using ONLY the leads below.
Cite leads as [n]. If the leads do not contain the answer, say so.

Leads:
{context}

Question: {question}"""
