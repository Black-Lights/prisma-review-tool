"""Source-side filters: what is applied where, and the local post-filter (SEARCH#2, 8, 9, 18)."""

from __future__ import annotations

import pytest

from prisma_review.models import Paper
from prisma_review.search.filters import (
    SearchFilters, apply_post_filters, build_crossref_filter, build_openalex_filters,
    build_scopus_clause, build_semantic_params, filter_modes, filter_plan, normalize_issn,
    source_filter_warnings, split_venues,
)


def F(**kw) -> SearchFilters:
    base = dict(document_types=[], require_abstract=False, open_access=False, venues=[])
    base.update(kw)
    return SearchFilters(**base)


class Cfg:
    """The attributes filter_plan/filter_warnings read from a Config."""

    def __init__(self, sources, **filters):
        self.sources = sources
        self.filter_document_types = filters.get("document_types", [])
        self.filter_require_abstract = filters.get("require_abstract", False)
        self.filter_open_access = filters.get("open_access", False)
        self.filter_venues = filters.get("venues", [])


def by_filter(plan: dict) -> dict:
    return {f["filter"]: f["by_source"] for f in plan["filters"]}


# --- SEARCH#2: request-mode facets are not re-checked locally ---------------------

@pytest.mark.parametrize("source", ["openalex", "crossref"])
def test_server_side_issn_match_is_not_deleted_locally(source):
    # The API matched the e-ISSN; the record stores the print ISSN (ISSN-L).
    p = Paper(title="t", venue="Remote Sensing of Environment", issn="0034-4257", source=source)
    assert apply_post_filters([p], F(venues=["1879-0704"]), source) == [p]


def test_scopus_unhyphenated_issn_is_kept():
    p = Paper(title="t", venue="Remote Sensing of Environment", issn="00344257", source="scopus")
    assert apply_post_filters([p], F(venues=["0034-4257"]), "scopus") == [p]


def test_issn_input_is_normalized():
    assert normalize_issn("00344257") == "0034-4257"
    assert normalize_issn("2045-322x") == "2045-322X"
    assert normalize_issn(" 1879-0704 ") == "1879-0704"
    assert normalize_issn("Remote Sensing") is None
    assert split_venues(["00344257", "0034-4257", "2045-322x", "Nature"]) == (
        ["0034-4257", "2045-322X"], ["Nature"])


def test_eight_digit_issn_is_sent_as_an_issn_everywhere():
    f = F(venues=["00344257"])
    assert build_scopus_clause(f) == " AND (ISSN(0034-4257))"
    assert build_semantic_params(f) == {}  # not a venue name
    assert build_crossref_filter(f) == "issn:0034-4257"
    assert build_openalex_filters(f) == {"primary_location.source.issn": "0034-4257"}


def test_semantic_scholar_issn_only_filter_is_unsupported_not_destructive():
    papers = [Paper(title="t", venue="Remote Sensing of Environment", source="semantic_scholar"),
              Paper(title="u", venue="", source="semantic_scholar")]
    f = F(venues=["0034-4257"])
    assert apply_post_filters(papers, f, "semantic_scholar") == papers
    assert filter_modes("semantic_scholar", f) == {"venues_issn": "unsupported"}
    assert any("not supported" in w for w in source_filter_warnings("semantic_scholar", f))


def test_post_mode_filters_are_still_enforced():
    keep = Paper(title="a", abstract="text", source="semantic_scholar")
    drop = Paper(title="b", abstract="", source="semantic_scholar")
    assert apply_post_filters([keep, drop], F(require_abstract=True), "semantic_scholar") == [keep]
    # ...unless the backend said the field is not available for this result.
    assert apply_post_filters([keep, drop], F(require_abstract=True), "scopus",
                              skip={"require_abstract"}) == [keep, drop]

    by_name = F(venues=["Remote Sensing"])
    rse = Paper(title="c", venue="Remote Sensing of Environment", source="openalex")
    other = Paper(title="d", venue="Nature", source="openalex")
    unknown = Paper(title="e", venue="", source="openalex")
    assert apply_post_filters([rse, other, unknown], by_name, "openalex") == [rse, unknown]


# --- SEARCH#8: Semantic Scholar types -------------------------------------------

def test_semantic_scholar_review_listed_second_is_kept():
    p = Paper(title="t", type="JournalArticle,Review", source="semantic_scholar")
    assert apply_post_filters([p], F(document_types=["review"]), "semantic_scholar") == [p]


def test_semantic_scholar_book_chapter_maps_to_book_section():
    assert build_semantic_params(F(document_types=["book-chapter"])) == {"publicationTypes": "BookSection"}


# --- SEARCH#9: one derivation for plan, warnings and enforcement --------------------

def test_crossref_open_access_is_reported_as_unsupported():
    f = F(open_access=True)
    assert filter_modes("crossref", f) == {"open_access": "unsupported"}
    warns = source_filter_warnings("crossref", f)
    assert warns and all("applied locally" not in w for w in warns)
    assert by_filter(filter_plan(Cfg(["crossref"], open_access=True)))["open_access"] == {
        "crossref": "unsupported"}


def test_filter_plan_accounts_for_unmapped_document_types():
    plan = by_filter(filter_plan(Cfg(["crossref", "openalex", "scopus"], document_types=["review"])))
    assert plan["document_types"] == {"crossref": "unsupported", "openalex": "request",
                                      "scopus": "request"}
    warns = source_filter_warnings("crossref", F(document_types=["review"]))
    assert any("ignored" in w for w in warns)


def test_partially_mapped_document_types_warn_per_type():
    warns = source_filter_warnings("crossref", F(document_types=["journal-article", "review"]))
    assert any("'review'" in w for w in warns)
    assert filter_modes("crossref", F(document_types=["journal-article", "review"])) == {
        "document_types": "request"}


@pytest.mark.parametrize("source", ["openalex", "crossref"])
def test_mixed_venues_warn_where_names_cannot_come_back(source):
    f = F(venues=["0034-4257", "Computers and Electronics in Agriculture"])
    assert filter_modes(source, f) == {"venues_issn": "request", "venues_name": "unsupported"}
    warns = source_filter_warnings(source, f)
    assert any("Computers and Electronics in Agriculture" in w and "ISSN" in w for w in warns)
    # The ISSN-matched records the API returned survive the post-filter.
    p = Paper(title="t", venue="Remote Sensing of Environment", issn="0034-4257", source=source)
    assert apply_post_filters([p], f, source) == [p]


def test_mixed_venues_on_semantic_scholar_warn_about_issn_only_venues():
    f = F(venues=["0034-4257", "Remote Sensing of Environment"])
    warns = source_filter_warnings("semantic_scholar", f)
    assert any("0034-4257" in w and "cannot be returned" in w for w in warns)


def test_plan_matches_post_filter_for_every_source_and_filter():
    f = F(document_types=["review"], require_abstract=True, open_access=True,
          venues=["0034-4257", "Nature"])
    for source in ("openalex", "crossref", "semantic_scholar", "scopus", "arxiv"):
        plan = by_filter(filter_plan(Cfg([source], document_types=["review"], require_abstract=True,
                                         open_access=True, venues=["0034-4257", "Nature"])))
        modes = filter_modes(source, f)
        assert {k: v[source] for k, v in plan.items()} == {
            {"venues_issn": "venues (ISSN)", "venues_name": "venues (name)"}.get(k, k): m
            for k, m in modes.items()}


# --- SEARCH#18: venue names in requests --------------------------------------------

def test_scopus_srctitle_strips_double_quotes():
    assert build_scopus_clause(F(venues=['Proc. "Big" Data'])) == ' AND (SRCTITLE("Proc. Big Data"))'


def test_semantic_scholar_drops_venue_names_with_commas():
    f = F(venues=["Journal of Things, Series B", "Nature"])
    assert build_semantic_params(f) == {"venue": "Nature"}
    assert any("comma" in w for w in source_filter_warnings("semantic_scholar", f))
