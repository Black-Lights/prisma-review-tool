"""PRISMA 2020 flow numbers and review statistics.

``compute_flow`` is the single source of the numbers in the PRISMA flow
diagram: /api/stats, the Markdown and PNG diagrams, the CLI and the MCP
generate_report tool all use it. The rules (PRISMA 2020, Page et al., BMJ 2021):

* records excluded by the keyword rules or the required-keyword gate are
  "Records marked as ineligible by automation tools", removed before
  screening, and counted only there;
* records nobody has screened yet ("maybe" from the keyword rules with no AI
  or manual decision, or every record before screening has run) are "not
  yet screened" (``awaiting_screening``): neither screened nor excluded;
* records screened = the records with a screening decision: the AI and
  manual decisions plus the inclusions by the keyword rules
  (``included_by_automation``, which reach retrieval without a reviewer);
* "Records excluded" at screening are the AI and manual exclusions only;
* reports sought for retrieval = papers included at screening, and the
  eligibility pass splits them into excluded, awaiting and included.

The numbers always add up: identified - duplicates - automation -
awaiting_screening = screened; screened - screening_excluded =
sought_for_retrieval; sought_for_retrieval - eligibility_excluded -
awaiting_eligibility = included.
"""

from __future__ import annotations

import os
import threading
from collections import OrderedDict
from pathlib import Path
from typing import Any, Iterable

from .models import Paper, load_papers
from .screen import eligibility_summary, screen_summary
from .storage import read_json


def count_by_source(papers: Iterable[Paper]) -> dict[str, int]:
    """Records per source, from each paper's own ``source`` field (never from a result key)."""
    counts: dict[str, int] = {}
    for p in papers:
        source = p.source or "unknown"
        counts[source] = counts.get(source, 0) + 1
    return counts


# ---------------------------------------------------------------------------
# Read-only paper cache
# ---------------------------------------------------------------------------

_CACHE_SIZE = 8
_cache: OrderedDict[str, tuple[tuple[int, int, int], list[Paper]]] = OrderedDict()
_cache_lock = threading.Lock()


def _fingerprint(path: Path) -> tuple[int, int, int] | None:
    try:
        st = os.stat(path)
    except OSError:
        return None
    # Every write replaces the file (os.replace), so the inode changes too.
    return (st.st_mtime_ns, st.st_size, st.st_ino)


def load_papers_cached(path: str | Path) -> list[Paper]:
    """Like ``models.load_papers`` but re-parses only when the file changed.

    The screening files of a real review are 10+ MB; the web app reads them on
    every refresh. Callers must treat the returned papers as read-only.
    """
    path = Path(path)
    fp = _fingerprint(path)
    if fp is None:
        return []
    key = os.path.normcase(str(path.resolve()))
    with _cache_lock:
        hit = _cache.get(key)
        if hit is not None and hit[0] == fp:
            _cache.move_to_end(key)
            return hit[1]
    papers = load_papers(path)
    if _fingerprint(path) == fp:  # not replaced while we read it
        with _cache_lock:
            _cache[key] = (fp, papers)
            _cache.move_to_end(key)
            while len(_cache) > _CACHE_SIZE:
                _cache.popitem(last=False)
    return papers


# ---------------------------------------------------------------------------
# Flow
# ---------------------------------------------------------------------------


def _int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _screen_from_state(state: dict) -> tuple[dict | None, list[str]]:
    """The screen summary stored in the state (older states have no breakdown)."""
    screen = state.get("screen")
    if not isinstance(screen, dict) or not screen:
        return None, []
    breakdown = screen.get("breakdown")
    if isinstance(breakdown, dict):
        return {**screen, "breakdown": {k: _int(v) for k, v in breakdown.items()}}, []
    gate = _int(screen.get("excluded_no_required_keyword"))
    excluded = _int(screen.get("excluded"))
    rebuilt = {
        "rule_include": _int(screen.get("included")),
        "rule_exclude_keyword": max(excluded - gate, 0),
        "rule_exclude_required": gate,
        "rule_maybe": _int(screen.get("maybe")),
    }
    note = ("The screening counts were saved by an older version without the split by "
            "method, so every screening exclusion is reported as an automation-tool "
            "exclusion. Re-screen (or record one decision) to refresh them.")
    total = _int(screen.get("records_in_screening")) or _int(screen.get("total_screened"))
    return {"records_in_screening": total or sum(rebuilt.values()), "breakdown": rebuilt}, [note]


def compute_flow(state: dict, screen: dict | None = None,
                 eligibility: dict | None = None, *, capped: list[dict] | None = None) -> dict:
    """The PRISMA 2020 flow numbers.

    ``screen`` is a ``screen.screen_summary`` of screen_results.json and
    ``eligibility`` an ``eligibility_summary``; when omitted, the summaries
    stored in ``state`` are used. ``capped`` lists the searches of
    search_log.json cut at max_results_per_query (a note says so).
    """
    state = state if isinstance(state, dict) else {}
    notes: list[str] = []

    search = state.get("search") if isinstance(state.get("search"), dict) else {}
    by_source = {k: _int(v) for k, v in search.items() if k != "total"}
    dedup = state.get("dedup") if isinstance(state.get("dedup"), dict) else {}
    duplicates = _int(dedup.get("duplicates_removed"))

    if screen is None:
        screen, extra = _screen_from_state(state)
        notes += extra
    b = dict((screen or {}).get("breakdown") or {})

    def total(suffix: str, methods: Iterable[str] | None = None) -> int:
        return sum(v for k, v in b.items() if k.endswith(suffix)
                   and (methods is None or k.split("_", 1)[0] in methods))

    keyword_rules = _int(b.get("rule_exclude_keyword"))
    required = _int(b.get("rule_exclude_required"))
    automation = keyword_rules + required
    by_method = {"ai": _int(b.get("ai_exclude")), "manual": _int(b.get("manual_exclude"))}
    screening_excluded = sum(v for k, v in b.items()
                             if k.endswith("_exclude") and not k.startswith("rule_"))
    sought = total("_include")
    included_by_automation = _int(b.get("rule_include"))
    awaiting_listed = total("_maybe") + _int(b.get("unscreened"))
    if screen:
        in_screening = _int(screen.get("records_in_screening")) or _int(screen.get("total_screened"))
    else:
        in_screening = _int(dedup.get("remaining"))

    if "total" in search:
        identified = _int(search.get("total"))
    else:
        identified = sum(by_source.values())
        if not identified and in_screening:
            identified = in_screening + duplicates
            notes.append("No search counts were recorded, so the records identified are taken "
                         "from the deduplicated set plus the duplicates removed.")

    # Records that reach screening, and those of them nobody has screened yet.
    reached = identified - duplicates - automation
    awaiting_screening = reached - screening_excluded - sought
    if screen is not None and awaiting_screening != awaiting_listed:
        notes.append(f"The screening results cover {in_screening} records but search and dedup "
                     f"report {identified - duplicates}. Re-run dedup and screening (or rescreen) "
                     f"so the counts agree.")
    if awaiting_screening < 0:
        awaiting_screening = 0
    screened = reached - awaiting_screening

    if eligibility is None:
        stored = state.get("eligibility")
        eligibility = stored if isinstance(stored, dict) else {}
    eligibility_excluded = _int(eligibility.get("excluded"))
    included = _int(eligibility.get("included"))
    awaiting_eligibility = sought - eligibility_excluded - included
    if awaiting_eligibility < 0:
        notes.append("Eligibility decisions do not match the papers included at screening; "
                     "re-screen to reconcile them.")
        awaiting_eligibility = 0

    if capped:
        worst = max(capped, key=lambda c: _int(c.get("api_total")) - _int(c.get("retrieved")))
        notes.append(
            f"Records identified are the records retrieved, not every match: {len(capped)} "
            f"search(es) matched more records than search.max_results_per_query let through "
            f"(largest: {worst.get('source')}, query '{worst.get('query')}', "
            f"{_int(worst.get('retrieved')):,} of {_int(worst.get('api_total')):,}). "
            f"See 01_search/search_log.json.")
    if screen is None:
        if awaiting_screening:
            notes.append(f"Screening has not run yet: the {awaiting_screening} records left after "
                         f"removing duplicates are not yet screened.")
    elif awaiting_screening:
        notes.append(f"{awaiting_screening} records are not yet screened: the keyword rules left "
                     f"them as \"maybe\" and no AI or manual decision has been recorded. They are "
                     f"neither screened nor excluded; screen them (or report how they were "
                     f"handled) before publishing these numbers.")
    if included_by_automation:
        notes.append(f"{included_by_automation} of the {sought} reports sought for retrieval were "
                     f"included by the keyword rules alone (enough include keywords), without AI "
                     f"or manual screening.")
    if sought and not (eligibility_excluded or included):
        notes.append(f"Eligibility assessment has not started: {sought} reports await it, so "
                     f"the number of included studies is pending.")
    elif awaiting_eligibility:
        notes.append(f"{awaiting_eligibility} reports are still awaiting the eligibility assessment.")

    return {
        "identified": {"total": identified, "by_source": by_source,
                       "capped_searches": len(capped or [])},
        "removed_before_screening": {
            "duplicates": duplicates,
            "automation_ineligible": automation,
            "automation_by_reason": {"keyword_rules": keyword_rules, "required_keywords": required},
        },
        "screening_started": screen is not None,
        "screened": screened,
        "included_by_automation": included_by_automation,
        "screening_excluded": screening_excluded,
        "screening_excluded_by_method": by_method,
        "awaiting_screening": awaiting_screening,
        "sought_for_retrieval": sought,
        "assessed_for_eligibility": eligibility_excluded + included,
        "eligibility_excluded": eligibility_excluded,
        "awaiting_eligibility": awaiting_eligibility,
        "included": included,
        "notes": notes,
    }


def project_stats(config: Any, state: dict | None = None) -> dict:
    """The screen and eligibility summaries computed from the project's files, and the flow.

    Returns {"screen", "eligibility", "flow"}. Each summary comes from the
    result files when they exist (so a writer that dropped a counter cannot
    change the numbers) and from review_state.json otherwise.
    """
    if state is None:
        loaded = read_json(config.state_file, default={}, recover_trailing_data=True)
        state = loaded if isinstance(loaded, dict) else {}

    screen_file = config.screen_dir / "screen_results.json"
    stored_screen = state.get("screen") if isinstance(state.get("screen"), dict) else {}
    screen_input: dict | None = None
    if screen_file.exists():
        papers = load_papers_cached(screen_file)
        computed = screen_summary(papers, min_include_hits=stored_screen.get("min_include_hits"))
        # "total_screened" (before 1.6) counted every record in the file, not
        # the screened ones; records_in_screening replaced it.
        stored = {k: v for k, v in stored_screen.items() if k != "total_screened"}
        screen = {**stored, **computed}
        screen_input = computed
        first_pass = [p for p in papers if p.screen_decision == "include"]
    else:
        screen = dict(stored_screen)
        first_pass = None

    elig_file = config.eligibility_dir / "eligibility_results.json"
    elig_input: dict | None = None
    if first_pass is not None and elig_file.exists():
        elig_input = eligibility_summary(first_pass, load_papers_cached(elig_file))
        eligibility = elig_input if elig_input["screened"] else {}
    elif first_pass is not None:
        elig_input = eligibility_summary(first_pass, [])
        eligibility = {}
    else:
        stored = state.get("eligibility")
        eligibility = stored if isinstance(stored, dict) else {}

    log = read_json(config.search_dir / "search_log.json", default=None)
    searches = log.get("searches") if isinstance(log, dict) else None
    capped = ([s for s in searches if isinstance(s, dict) and s.get("capped_by_max_results")]
              if isinstance(searches, list) else [])

    return {"screen": screen, "eligibility": eligibility,
            "flow": compute_flow(state, screen_input, elig_input, capped=capped)}


def project_flow(config: Any, state: dict | None = None) -> dict:
    """``compute_flow`` for a project, from its state file and result files."""
    return project_stats(config, state)["flow"]
