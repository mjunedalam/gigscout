"""Prompt templates. Kept in one place so they can be versioned and logged to MLflow."""

PLAN_QUERIES = """You do business development for a software development agency, finding client projects to win.
Marketplace search boxes work best with short keyword queries (1-3 words), e.g. "mobile app", "saas mvp".

Agency profile:
{profile}

{extra}
Return up to {max_queries} distinct search queries that would surface client projects this agency can win."""

BROADEN_HINT = (
    "A previous search with these queries found too few good leads: {previous}.\n"
    "Suggest broader or adjacent queries (related services, frameworks, synonyms, industries)."
)

QUALIFY_LEAD = """You are a sharp business-development lead qualifying opportunities for a software agency.

Agency profile:
{profile}

Lead ({kind} from {source}):
Title: {title}
Client: {client}
Skills listed: {skills}
Budget: {budget}
Competing bids: {bids}
Description:
{description}

Lead kinds: project = client outsourcing a project; contract = company wants contractors; hiring = company hiring
in-house (pitch outsourcing or staff augmentation instead); inbound = prospect contacted the agency directly.

Score 0.0-1.0 how worth pursuing this is for the agency: service and stack fit, deal size versus the budget,
scope clarity, and how winnable it is given the competition.
Give reasons in ONE sentence of at most 25 words.
List red flags (scam signals, off-platform payment requests, unpaid tests, vague scope, budget far too low for an
agency) in at most 12 words, or leave empty if none.
Write a pitch: ONE opening line (at most 25 words) the agency could use to start the conversation."""

SUMMARIZE = """Write a 3-4 sentence briefing for the agency's sales team about today's best client leads.
Mention the strongest 2-3 by title, why, and the suggested next step. No preamble.

Agency:
{profile}

Leads:
{leads}"""

ANSWER_WITH_CONTEXT = """Answer the question using ONLY the leads below.
Cite leads as [n]. If the leads do not contain the answer, say so.

Leads:
{context}

Question: {question}"""
