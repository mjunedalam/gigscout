from datetime import UTC, datetime, timedelta

from gigscout import quality
from tests.conftest import make_lead


def test_add_new_deduplicates_within_and_across_calls(index, sample_leads):
    fresh = index.add_new([*sample_leads, sample_leads[0]])
    assert len(fresh) == 3

    again = index.add_new(sample_leads)
    assert again == []
    assert index.count() == 3


def test_search_ranks_semantically_closest_first(index, sample_leads):
    index.add_new(sample_leads)

    results = index.search("python django api developer", k=3)

    assert results[0].lead.id == "fake:1"
    assert results[0].similarity > results[-1].similarity
    assert results[0].lead == quality.assessed(sample_leads[0])  # full payload round-trips, quality-checked


def test_search_filters_by_age_source_and_kind(index):
    old = make_lead("old", "python job", posted_at=datetime.now(UTC) - timedelta(days=60))
    other = make_lead("x", "python job", source="other")
    job = make_lead("j", "python job", kind="hiring")
    index.add_new([old, other, job, make_lead("new", "python job")])

    assert {c.lead.id for c in index.search("python", k=10, max_age_days=7, sources=["fake"])} == {
        "fake:new", "fake:j"}
    assert [c.lead.id for c in index.search("python", k=10, kinds=["hiring"])] == ["fake:j"]


def test_search_on_empty_index_returns_nothing(index):
    assert index.search("anything", k=5) == []
