"""Source-side search filters (document type, abstract, open access, venue).

Two-channel model (see also :mod:`query_plan` for the *query* channel):

* **Request channel**: when a source exposes a filter as a native, structured
  facet, it is sent in the request so the API filters server-side. Crossref
  honours structured filters (``filter=type:journal-article``) even though it
  ignores the Boolean query.

* **Post-request channel**: :func:`apply_post_filters` runs after a fetch and
  enforces only the filters a source cannot apply itself. A facet the source
  already applied is never re-checked locally: the server matched it on data
  we do not fully store (for example every ISSN of a journal), so a local
  re-check would delete correct results. Missing metadata keeps the paper,
  except ``require_abstract`` where an empty abstract is the failing value.

:func:`filter_modes` is the single place that decides, per source, whether a
filter is applied at the request, locally after the fetch, or not at all.
:func:`apply_post_filters`, :func:`source_filter_warnings` and
:func:`filter_plan` all derive from it, so the report can never say
"filtered at source" while the warnings say "ignored".
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..models import Paper

# ISSN: four digits, optional hyphen, three digits and a check digit or X.
_ISSN_RE = re.compile(r"^(\d{4})-?(\d{3}[\dX])$")

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
        "book-chapter": "BookSection",
    },
    "scopus": {
        "journal-article": "ar",
        "review": "re",
        "conference-paper": "cp",
        "book-chapter": "ch",
    },
}

# How each source can handle each filter: "request" (native server-side facet),
# "post" (only enforceable locally after fetch), or "unsupported" (cannot be
# evaluated: ignored). arXiv is preprint-only and open access by nature.
# Crossref has no open-access facet and its records carry no OA flag;
# Semantic Scholar has no ISSN facet and its records carry no ISSN.
_FILTER_SUPPORT: dict[str, dict[str, str]] = {
    "openalex": {
        "document_types": "request", "require_abstract": "request",
        "open_access": "request", "venues_issn": "request", "venues_name": "post",
    },
    "crossref": {
        "document_types": "request", "require_abstract": "request",
        "open_access": "unsupported", "venues_issn": "request", "venues_name": "post",
    },
    "semantic_scholar": {
        "document_types": "request", "require_abstract": "post",
        "open_access": "request", "venues_issn": "unsupported", "venues_name": "request",
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

_LABELS = {
    "document_types": "document_types",
    "require_abstract": "require_abstract",
    "open_access": "open_access",
    "venues_issn": "venues (ISSN)",
    "venues_name": "venues (name)",
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


def normalize_issn(value: object) -> str | None:
    """``0034-4257`` form (hyphen, capital X) for anything shaped like an ISSN, else None."""
    text = str(value or "").strip().upper().replace(" ", "")
    m = _ISSN_RE.match(text)
    return f"{m.group(1)}-{m.group(2)}" if m else None


def split_venues(venues: list[str]) -> tuple[list[str], list[str]]:
    """Partition venue tokens into (normalized ISSNs, names) by shape."""
    issns, names = [], []
    for v in venues:
        v = str(v).strip()
        if not v:
            continue
        issn = normalize_issn(v)
        if issn:
            if issn not in issns:
                issns.append(issn)
        else:
            names.append(v)
    return issns, names


def _mapped_types(source: str, document_types: list[str]) -> list[str]:
    """The source-specific document-type values for the requested canonicals."""
    table = _DOC_TYPE_MAP.get(source, {})
    return [table[t] for t in document_types if t in table]


def _s2_venue_names(names: list[str]) -> list[str]:
    # The venue parameter is comma-separated, so a name containing a comma
    # would be split into two wrong names: it is not sent (and reported).
    return [n for n in names if "," not in n]


def filter_modes(source: str, f: SearchFilters) -> dict[str, str]:
    """How ``source`` applies each active filter: request, post or unsupported.

    Only active filters are returned. A document-type filter with no
    equivalent type for this source is unsupported; venues given by name are
    unsupported where the source restricts by ISSN at the request (they could
    never come back) or where no name can be sent.
    """
    support = _FILTER_SUPPORT.get(source, {})
    modes: dict[str, str] = {}
    if f.document_types:
        mode = support.get("document_types", "unsupported")
        if mode == "request" and not _mapped_types(source, f.document_types):
            mode = "unsupported"
        modes["document_types"] = mode
    if f.require_abstract:
        modes["require_abstract"] = support.get("require_abstract", "unsupported")
    if f.open_access:
        modes["open_access"] = support.get("open_access", "unsupported")
    issns, names = split_venues(f.venues)
    if issns:
        modes["venues_issn"] = support.get("venues_issn", "unsupported")
    if names:
        mode = support.get("venues_name", "unsupported")
        if mode == "post" and issns and modes.get("venues_issn") == "request":
            mode = "unsupported"
        if mode == "request" and source == "semantic_scholar" and not _s2_venue_names(names):
            mode = "unsupported"
        modes["venues_name"] = mode
    return modes


# --- Request-channel builders -------------------------------------------------
# Each returns the source-specific representation to merge into the request.
# Warnings are produced centrally by source_filter_warnings(), not here.

def build_openalex_filters(f: SearchFilters) -> dict[str, str]:
    """Extra entries for OpenAlex's ``filter`` parameter (key -> value)."""
    out: dict[str, str] = {}
    types = _mapped_types("openalex", f.document_types)
    if types:
        out["type"] = "|".join(types)
    if f.require_abstract:
        out["has_abstract"] = "true"
    if f.open_access:
        out["is_oa"] = "true"
    issns, _ = split_venues(f.venues)
    if issns:
        out["primary_location.source.issn"] = "|".join(issns)
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
    # A double quote inside SRCTITLE("...") would end the phrase early.
    venue_terms = ([f"ISSN({i})" for i in issns]
                   + [f'SRCTITLE("{" ".join(n.replace(chr(34), " ").split())}")' for n in names])
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
    names = _s2_venue_names(names)
    if names:
        out["venue"] = ",".join(names)
    return out


# --- Post-request channel -----------------------------------------------------

def apply_post_filters(papers: list[Paper], f: SearchFilters, source: str,
                       skip: frozenset[str] | set[str] = frozenset()) -> list[Paper]:
    """Enforce the filters ``source`` cannot apply itself (mode "post").

    Filters applied at the request are not re-checked and unsupported ones
    are not enforced (both are reported by :func:`source_filter_warnings`).
    ``skip`` names filters to leave out for this result, e.g. when the source
    returned records without the field the filter needs.
    """
    if f.is_empty:
        return papers
    modes = filter_modes(source, f)
    post = {k for k, m in modes.items() if m == "post"} - set(skip)
    if not post:
        return papers

    accept_types = set(_mapped_types(source, f.document_types))
    issns, names = split_venues(f.venues)
    names_lower = [n.lower() for n in names]

    kept: list[Paper] = []
    for p in papers:
        if "require_abstract" in post and not (p.abstract or "").strip():
            continue
        if "document_types" in post and accept_types and p.type and p.type not in accept_types:
            continue
        if "open_access" in post and p.is_oa is False:
            continue
        if "venues_issn" in post or "venues_name" in post:
            issn_ok = "venues_issn" in post and normalize_issn(p.issn) in issns
            name_ok = ("venues_name" in post and bool(p.venue)
                       and any(n in p.venue.lower() for n in names_lower))
            has_info = bool(p.issn) or bool(p.venue)
            # Only exclude when we have venue info and it matches nothing.
            if has_info and not (issn_ok or name_ok):
                continue
        kept.append(p)
    return kept


# --- Warnings -----------------------------------------------------------------

def source_filter_warnings(source: str, f: SearchFilters) -> list[str]:
    """Transparency warnings for how ``source`` applies ``f``."""
    if f.is_empty:
        return []

    support = _FILTER_SUPPORT.get(source, {})
    modes = filter_modes(source, f)
    label = f"{source} (filters)"
    warns: list[str] = []
    issns, names = split_venues(f.venues)

    # Document types with no equivalent in this source are lost server-side
    # unless we flag them (when some other requested type is still sent).
    if modes.get("document_types") == "request":
        table = _DOC_TYPE_MAP.get(source, {})
        for t in f.document_types:
            if t not in table:
                warns.append(f"{label}: document type '{t}' has no equivalent here: ignored.")

    for key, mode in modes.items():
        name = _LABELS[key]
        if mode == "post":
            warns.append(f"{label}: '{name}' is not a server-side facet here: "
                         f"applied locally after fetch.")
        elif mode == "unsupported":
            if key == "venues_name" and support.get("venues_name") == "post":
                warns.append(
                    f"{label}: venues are restricted by ISSN at the source, so venues given only "
                    f"by name ({', '.join(names)}) cannot be returned. Add their ISSNs instead."
                )
            elif key == "document_types" and support.get("document_types") == "request":
                warns.append(f"{label}: none of the document types {f.document_types} has an "
                             f"equivalent here: ignored.")
            else:
                warns.append(f"{label}: '{name}' is not supported by this source: ignored.")

    # Mixed venues where only the names reach the source: ISSN-only venues are excluded.
    if (issns and modes.get("venues_name") == "request"
            and modes.get("venues_issn") == "unsupported"):
        warns.append(
            f"{label}: only venue names can be sent here, so papers from venues given only by "
            f"ISSN ({', '.join(issns)}) cannot be returned. Add their names too."
        )
    if source == "semantic_scholar" and modes.get("venues_name"):
        for n in names:
            if "," in n:
                warns.append(f"{label}: venue name '{n}' contains a comma and cannot be sent "
                             f"to Semantic Scholar: ignored.")
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
    fetch), or ``"unsupported"`` (cannot be evaluated: ignored). Drives the
    "filtered at source vs. after the call" table in the report UI.
    """
    f = SearchFilters.from_config(config)
    sources = list(getattr(config, "sources", []) or [])
    modes = {s: filter_modes(s, f) for s in sources}
    keys = list(filter_modes("", f))  # the active filters, in a stable order
    filters = [
        {"filter": _LABELS[key], "by_source": {s: modes[s].get(key, "unsupported") for s in sources}}
        for key in keys
    ]
    return {"sources": sources, "filters": filters, "empty": f.is_empty}
