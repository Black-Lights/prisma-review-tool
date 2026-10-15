"""Source-side search filters (document type, abstract, open access, venue).

Two-channel model (see also :mod:`query_plan` for the *query* channel):

* **Request channel** — when a source exposes a filter as a native, structured
  facet, we send it in the request so the API filters server-side. This is
  independent of the plain-text degradation that hits the *query* channel of
  Crossref/Semantic Scholar: those sources still honour structured filters
  (e.g. Crossref ``filter=type:journal-article``) even though they ignore the
  Boolean query.

* **Post-request channel** — :func:`apply_post_filters` always runs after a
  fetch as a safety net. For facets the source applied server-side it is a
  no-op; for facets the source can't express it is the actual enforcement.
  It only excludes a paper when the relevant field is *present and fails*;
  missing/unknown metadata keeps the paper (conservative), except
  ``require_abstract`` where an empty abstract is itself the failing value.

:func:`filter_warnings` reports, per (source, filter), whether a filter runs at
the request (✓, no warning), is applied locally (⚠️), or is unsupported and
ignored (❌). Those warnings surface in the pipeline ``warnings`` field, exactly
like the query-plan warnings.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..models import Paper

# ISSN form: four digits, hyphen, three digits, then a digit or X (check digit).
_ISSN_RE = re.compile(r"^\d{4}-\d{3}[\dxX]$")

# Canonical document types we accept in config, mapped to each source's own
# vocabulary. A canonical type absent from a source's map has no equivalent
# there and is reported as ignored for that source.
_DOC_TYPE_MAP: dict[str, dict[str, str]] = {
    "openalex": {
        "journal-article": "article",
        "review": "review",
        "book-chapter": "book-chapter",
        "preprint": "preprint",
    },
    "crossref": {
        "journal-article": "journal-article",
        "conference-paper": "proceedings-article",
        "book-chapter": "book-chapter",
        "preprint": "posted-content",
    },
    "semantic_scholar": {
        "journal-article": "JournalArticle",
        "review": "Review",
        "conference-paper": "Conference",
        "book-chapter": "Book",
    },
    "scopus": {
        "journal-article": "ar",
        "review": "re",
        "conference-paper": "cp",
        "book-chapter": "ch",
    },
}

# How each source handles each filter: "request" (native server-side facet),
# "post" (only enforceable locally after fetch), or "unsupported" (cannot be
# evaluated at all — ignored). arXiv is preprint-only and open-access by
# nature, so document_types/venues are unsupported while open_access is
# inherently satisfied.
_FILTER_SUPPORT: dict[str, dict[str, str]] = {
    "openalex": {
        "document_types": "request", "require_abstract": "request",
        "open_access": "request", "venues_issn": "request", "venues_name": "post",
    },
    "crossref": {
        "document_types": "request", "require_abstract": "request",
        "open_access": "post", "venues_issn": "request", "venues_name": "post",
    },
    "semantic_scholar": {
        "document_types": "request", "require_abstract": "post",
        "open_access": "request", "venues_issn": "post", "venues_name": "request",
    },
    "scopus": {
        "document_types": "request", "require_abstract": "post",
        "open_access": "request", "venues_issn": "request", "venues_name": "request",
    },
    "arxiv": {
        "document_types": "unsupported", "require_abstract": "post",
        "open_access": "request", "venues_issn": "unsupported", "venues_name": "unsupported",
    },
}


@dataclass
class SearchFilters:
    """Canonical, source-agnostic filter selection from config."""

    document_types: list[str]
    require_abstract: bool
    open_access: bool
    venues: list[str]

    @classmethod
    def from_config(cls, config) -> "SearchFilters":
        return cls(
            document_types=list(getattr(config, "filter_document_types", []) or []),
            require_abstract=bool(getattr(config, "filter_require_abstract", False)),
            open_access=bool(getattr(config, "filter_open_access", False)),
            venues=list(getattr(config, "filter_venues", []) or []),
        )

    @property
    def is_empty(self) -> bool:
        return not (self.document_types or self.require_abstract
                    or self.open_access or self.venues)


def split_venues(venues: list[str]) -> tuple[list[str], list[str]]:
    """Partition venue tokens into (ISSNs, names) by shape."""
    issns, names = [], []
    for v in venues:
        v = str(v).strip()
        if not v:
            continue
        (issns if _ISSN_RE.match(v) else names).append(v)
    return issns, names


def _mapped_types(source: str, document_types: list[str]) -> list[str]:
    """The source-specific document-type values for the requested canonicals."""
    table = _DOC_TYPE_MAP.get(source, {})
    return [table[t] for t in document_types if t in table]


# --- Request-channel builders -------------------------------------------------
# Each returns the source-specific representation to merge into the request.
# Warnings are produced centrally by filter_warnings(), not here, so the
# builders stay pure and side-effect free.

def build_openalex_filters(f: SearchFilters) -> dict:
    """Keyword args for ``pyalex.Works().filter(**...)``."""
    out: dict = {}
    types = _mapped_types("openalex", f.document_types)
    if types:
        out["type"] = "|".join(types)
    if f.require_abstract:
        out["has_abstract"] = True
    if f.open_access:
        out["is_oa"] = True
    issns, _ = split_venues(f.venues)
    if issns:
        out["primary_location"] = {"source": {"issn": "|".join(issns)}}
    return out


def build_crossref_filter(f: SearchFilters) -> str:
    """Comma-joined fragment to append to Crossref's ``filter`` parameter."""
    parts: list[str] = []
    for t in _mapped_types("crossref", f.document_types):
        parts.append(f"type:{t}")          # repeated keys are OR'd by Crossref
    if f.require_abstract:
        parts.append("has-abstract:true")
    issns, _ = split_venues(f.venues)
    for issn in issns:
        parts.append(f"issn:{issn}")
    return ",".join(parts)


def build_scopus_clause(f: SearchFilters) -> str:
    """`` AND ...`` clause to append to a Scopus query string."""
    parts: list[str] = []
    types = _mapped_types("scopus", f.document_types)
    if types:
        parts.append("(" + " OR ".join(f"DOCTYPE({t})" for t in types) + ")")
    if f.open_access:
        parts.append("OPENACCESS(1)")
    issns, names = split_venues(f.venues)
    venue_terms = [f"ISSN({i})" for i in issns] + [f'SRCTITLE("{n}")' for n in names]
    if venue_terms:
        parts.append("(" + " OR ".join(venue_terms) + ")")
    return "".join(f" AND {p}" for p in parts)


def build_semantic_params(f: SearchFilters) -> dict:
    """Extra query params for the Semantic Scholar search endpoint."""
    out: dict = {}
    types = _mapped_types("semantic_scholar", f.document_types)
    if types:
        out["publicationTypes"] = ",".join(types)
    if f.open_access:
        out["openAccessPdf"] = ""          # presence-only flag
    _, names = split_venues(f.venues)
    if names:
        out["venue"] = ",".join(names)
    return out


# --- Post-request channel -----------------------------------------------------

def apply_post_filters(papers: list[Paper], f: SearchFilters, source: str) -> list[Paper]:
    """Filter a returned list as the always-on safety net.

    Conservative: a paper is dropped only when a field is present and fails the
    filter. Unknown metadata (``None``/empty for type, is_oa, issn) keeps the
    paper, so sources that don't expose a facet aren't wiped out. The one
    exception is ``require_abstract``: an empty abstract is the failing value.
    """
    if f.is_empty:
        return papers

    # Respect the support matrix: a filter marked "unsupported" for this source
    # is reported as ignored (see filter_warnings), so the post pass must not
    # silently enforce it and wipe out an entire source.
    support = _FILTER_SUPPORT.get(source, {})

    def on(key: str) -> bool:
        return support.get(key, "unsupported") != "unsupported"

    accept_types = set(_mapped_types(source, f.document_types))
    issns, names = split_venues(f.venues)
    names_lower = [n.lower() for n in names]
    check_issn = issns and on("venues_issn")
    check_name = names and on("venues_name")

    kept: list[Paper] = []
    for p in papers:
        if f.require_abstract and on("require_abstract") and not (p.abstract or "").strip():
            continue
        if accept_types and on("document_types") and p.type and p.type not in accept_types:
            continue
        if f.open_access and on("open_access") and p.is_oa is False:
            continue
        if check_issn or check_name:
            issn_ok = check_issn and bool(p.issn) and p.issn in issns
            name_ok = check_name and bool(p.venue) and any(n in p.venue.lower() for n in names_lower)
            has_info = bool(p.issn) or bool(p.venue)
            # Only exclude when we have venue info and it matches nothing.
            if has_info and not (issn_ok or name_ok):
                continue
        kept.append(p)
    return kept


# --- Warnings -----------------------------------------------------------------

def _filter_labels(f: SearchFilters) -> list[tuple[str, str]]:
    """Active (support_key, human_name) pairs for the configured filters."""
    out: list[tuple[str, str]] = []
    if f.document_types:
        out.append(("document_types", "document_types"))
    if f.require_abstract:
        out.append(("require_abstract", "require_abstract"))
    if f.open_access:
        out.append(("open_access", "open_access"))
    issns, names = split_venues(f.venues)
    if issns:
        out.append(("venues_issn", "venues (ISSN)"))
    if names:
        out.append(("venues_name", "venues (name)"))
    return out


def source_filter_warnings(source: str, f: SearchFilters) -> list[str]:
    """Transparency warnings for how ``source`` applies ``f``."""
    if f.is_empty:
        return []

    support = _FILTER_SUPPORT.get(source, {})
    label = f"{source} (filters)"
    warns: list[str] = []

    # Document types with no equivalent in this source are silently lost
    # server-side unless we flag them.
    if f.document_types:
        table = _DOC_TYPE_MAP.get(source, {})
        for t in f.document_types:
            if support.get("document_types") == "unsupported":
                continue  # whole filter reported below
            if t not in table:
                warns.append(
                    f"{label}: document type '{t}' has no equivalent here — ignored."
                )

    for key, name in _filter_labels(f):
        mode = support.get(key, "unsupported")
        if mode == "post":
            warns.append(
                f"{label}: '{name}' is not a server-side facet here — "
                f"applied locally after fetch."
            )
        elif mode == "unsupported":
            warns.append(
                f"{label}: '{name}' is not supported by this source — ignored."
            )
    return warns


def filter_warnings(config) -> list[str]:
    """Collect filter warnings across every enabled source."""
    f = SearchFilters.from_config(config)
    if f.is_empty:
        return []
    out: list[str] = []
    for source in getattr(config, "sources", []) or []:
        out.extend(source_filter_warnings(source, f))
    return out


def filter_plan(config) -> dict:
    """Machine-readable companion to :func:`filter_warnings`.

    Returns, for each active filter, how every enabled source applies it:
    ``"request"`` (server-side facet), ``"post"`` (enforced locally after the
    fetch), or ``"unsupported"`` (cannot be evaluated — ignored). Drives the
    "filtered at source vs. after the call" table in the report UI.
    """
    f = SearchFilters.from_config(config)
    sources = list(getattr(config, "sources", []) or [])
    filters = [
        {
            "filter": name,
            "by_source": {
                s: _FILTER_SUPPORT.get(s, {}).get(key, "unsupported")
                for s in sources
            },
        }
        for key, name in _filter_labels(f)
    ]
    return {"sources": sources, "filters": filters, "empty": f.is_empty}
