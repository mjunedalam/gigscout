"""Small text helpers shared by sources and scoring."""

import re
from collections.abc import Iterable

from bs4 import BeautifulSoup

_WS = re.compile(r"\s+")
MAX_DESCRIPTION_CHARS = 4000


def html_to_text(html: str | None, limit: int = MAX_DESCRIPTION_CHARS) -> str:
    if not html:
        return ""
    text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
    return _WS.sub(" ", text).strip()[:limit]


def contains_term(text: str, term: str) -> bool:
    """Case-insensitive whole-word match; handles terms like 'c++' and 'node.js'."""
    pattern = r"(?<![\w])" + re.escape(term.lower()) + r"(?![\w])"
    return re.search(pattern, text.lower()) is not None


def matches_any_query(text: str, queries: Iterable[str]) -> bool:
    """True if every word of at least one query appears in the text."""
    return any(all(contains_term(text, word) for word in q.split()) for q in queries if q.strip())
