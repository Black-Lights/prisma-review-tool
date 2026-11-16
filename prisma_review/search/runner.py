"""Orchestrate searches across all configured sources.

Besides the records, every run reports what happened to each
``(source, query)`` pair (``status_log``) and writes
``01_search/search_log.json``: the search exactly as executed per database
(PRISMA 2020 item 7), with the request sent, field scope, how each filter was
applied, the counts the API reported and retrieved, and the outcome.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Callable, Optional

from .. import __version__
from ..config import KNOWN_SOURCES, Config
from ..models import Paper
from ..storage import atomic_write_json
from .arxiv_search import search_arxiv
from .crossref_search import search_crossref
from .filters import SearchFilters, apply_post_filters, filter_modes, source_filter_warnings
from .http import SearchCancelled, SearchStatus, error_text
from .openalex_search import search_openalex
from .query_plan import date_range, plan_query
from .scopus_search import search_scopus
from .semantic_search import search_semantic_scholar

# Progress output must go to stderr: this module is imported by the stdio MCP
# server, where stdout is the JSON-RPC channel and any stray byte corrupts it.
import sys
import functools
print = functools.partial(print, file=sys.stderr)

SEARCH_LOG_NAME = "search_log.json"


def result_key(source: str, query_index: int, query_name: str) -> str:
    """Key of one ``(source, query)`` result: unique even for same-named queries."""
    return f"{source}:{query_index}:{query_name}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _run_backend(source: str, terms: str, start: str, end: str, config: Config,
                 filters: SearchFilters, status: SearchStatus,
                 should_cancel: Optional[Callable[[], bool]]) -> list[Paper]:
    kw = {"status": status, "should_cancel": should_cancel}
    n = config.max_results
    if source == "arxiv":
        return search_arxiv(terms, start, end, n, filters, **kw)
    if source == "crossref":
        return search_crossref(terms, start, end, n, config.openalex_email, filters, **kw)
    if source == "openalex":
        return search_openalex(terms, start, end, n, config.openalex_email, filters,
                               api_key=config.openalex_key, **kw)
    if source == "semantic_scholar":
        return search_semantic_scholar(terms, start, end, n, filters, **kw)
    if source == "scopus":
        return search_scopus(terms, config.scopus_key, start, end, n, filters, **kw)
    raise ValueError(f"no backend for source {source!r}")


def run_all_searches(config: Config, *, status_log: Optional[list] = None,
                     should_cancel: Optional[Callable[[], bool]] = None) -> dict[str, list[Paper]]:
    """Run every query on every enabled source.

    Returns the records per ``(source, query)`` pair, keyed by
    :func:`result_key`, after the local post-request filters. When
    ``status_log`` is a list, one dict per pair is appended as soon as the
    pair finishes: ``{source, query, query_index, status, error, api_total,
    retrieved, after_post_filter, executed}`` with ``status`` one of ok,
    partial, failed, skipped, cancelled. ``should_cancel`` is polled between
    pages and during retry waits; once it returns True the remaining pairs are
    reported as cancelled and ``01_search/search_log.json`` is left as it was.

    Raises ValueError when the configured date range is not a valid range.
    """
    try:
        start, end = date_range(config.date_start, config.date_end)
    except ValueError as exc:
        raise ValueError(f"search.date_range: {exc}") from None

    results: dict[str, list[Paper]] = {}
    filters = SearchFilters.from_config(config)
    started_at = _now()
    searches: list[dict] = []
    queries: list[dict] = []
    cancelled = False

    for index, query_def in enumerate(config.queries):
        query_name = str(query_def.get("name") or "unnamed")
        query_terms = str(query_def.get("terms") or "")
        if not query_terms.strip():
            continue
        queries.append({"index": index, "name": query_name, "terms": query_terms,
                        "terms_sha256": hashlib.sha256(query_terms.encode("utf-8")).hexdigest()})

        print(f"\n  Query: {query_name}")

        for source in config.sources:
            status = SearchStatus(source)
            plan = plan_query(source, query_name, query_terms, date_start=start, date_end=end,
                              filters=filters)
            pair_started = _now()
            papers: list[Paper] = []
            ran = False

            if cancelled or (should_cancel is not None and should_cancel()):
                cancelled = True
                status.cancel()
            elif source not in KNOWN_SOURCES:
                status.status = "skipped"
                status.error = f"unknown source '{source}' (known: {', '.join(KNOWN_SOURCES)})"
                print(f"    {source}: unknown source, skipping")
            else:
                print(f"    Searching {source}...", end=" ", flush=True)
                ran = True
                try:
                    papers = _run_backend(source, query_terms, start, end, config, filters,
                                          status, should_cancel)
                except SearchCancelled:
                    status.cancel()
                except Exception as exc:  # a backend bug must not end the whole search
                    secrets = [config.openalex_email, config.openalex_key, config.scopus_key]
                    status.stop(f"{source}: {error_text(exc, secrets)}", False)
                    papers = []
                if status.status == "cancelled":
                    cancelled = True

            retrieved = len(papers)
            kept = apply_post_filters(papers, filters, source, skip=status.skip_post_filters)

            # Provenance: dedup later unions these across merged duplicates.
            for p in kept:
                p.matched_queries = [query_name]
                p.found_in_sources = [source]
                p.source_ids = {source: p.source_id} if p.source_id else {}

            if ran:
                results[result_key(source, index, query_name)] = kept
                note = "" if status.status == "ok" else f" [{status.status}: {status.error}]"
                print(f"found {len(kept)} papers{note}")

            entry = {
                "source": source,
                "query": query_name,
                "query_index": index,
                "status": status.status,
                "error": status.error,
                "api_total": status.api_total,
                "retrieved": retrieved,
                "after_post_filter": len(kept),
                "executed": status.executed,
            }
            if status_log is not None:
                status_log.append(dict(entry))

            searches.append({
                **entry,
                "terms": query_terms,
                "syntax": plan.syntax,
                "field_scope": plan.field_scope,
                "date_filter": plan.date_filter,
                "filter_modes": filter_modes(source, filters),
                "request": status.request,
                "removed_by_post_filter": retrieved - len(kept),
                "capped_by_max_results": bool(status.api_total is not None
                                              and status.api_total > config.max_results
                                              and retrieved >= config.max_results),
                "warnings": plan.warnings + source_filter_warnings(source, filters) + status.notes,
                "started_at": pair_started,
                "finished_at": _now(),
            })

    if not cancelled:
        by_source: dict[str, int] = {}
        for s in searches:
            by_source[s["source"]] = by_source.get(s["source"], 0) + s["after_post_filter"]
        log = {
            "tool": "prisma-review-tool",
            "tool_version": __version__,
            "started_at": started_at,
            "finished_at": _now(),
            "project": config.project_name,
            "date_range": {"start": start, "end": end},
            "max_results_per_query": config.max_results,
            "sources": list(config.sources),
            "filters": {
                "document_types": filters.document_types,
                "require_abstract": filters.require_abstract,
                "open_access": filters.open_access,
                "venues": filters.venues,
            },
            "queries": queries,
            "complete": all(s["status"] == "ok" for s in searches),
            "searches": searches,
            "totals": {"records": sum(by_source.values()), "by_source": by_source},
        }
        atomic_write_json(config.search_dir / SEARCH_LOG_NAME, log, ensure_ascii=False)

    return results
