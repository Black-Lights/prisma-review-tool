"""MCP Server for PRISMA Review Tool.

Exposes the review pipeline and screening tools so an AI agent can read
papers, make screening decisions, and generate reports, all via MCP (stdio).

stdout is the JSON-RPC channel: nothing in this process may print to it.
Diagnostics, including the startup line naming the review in use, go to stderr.
"""

from __future__ import annotations

import functools
import json
import re
import sys
import threading
import traceback
from datetime import date
from pathlib import Path
from typing import Any, Callable

from mcp.server.fastmcp import FastMCP
from typing_extensions import NotRequired, TypedDict

# Add parent to path so we can import prisma_review
sys.path.insert(0, str(Path(__file__).parent.parent))

from prisma_review import __version__, workspace
from prisma_review.config import (
    KNOWN_DOCUMENT_TYPES, KNOWN_SOURCES, Config, ConfigError, load_raw_config, save_raw_config,
)
from prisma_review.models import Paper, save_papers, load_papers
from prisma_review.screen import get_by_decision, screen_by_rules, count_excluded_by_required
from prisma_review.export import export_bibtex, export_csv
from prisma_review.search.filters import filter_warnings
from prisma_review.search.query_plan import query_warnings
from prisma_review.storage import project_lock
from prisma_review.download import download_papers
from prisma_review.diagram import (
    generate_markdown_diagram, generate_png_diagram,
    load_state, save_state,
)
from api.session import SessionManager

INSTRUCTIONS = """\
PRISMA Review Tool runs a PRISMA 2020 systematic literature review: database \
search, deduplication, keyword screening, AI-assisted screening of uncertain \
papers, a second eligibility pass, and the PRISMA flow diagram with BibTeX/CSV export.

Every tool acts on one review project: the config file pinned by the \
PRISMA_CONFIG environment variable, otherwise the active project named in \
projects/.active_project (shared with the web app). Tools that change anything \
return the project and config_path they acted on.

Start with get_review_config: it shows the project, whether its config is ready, \
and warnings such as a missing OpenAlex API key. Use list_projects, \
switch_project or create_project to pick a review and set_review_config to fill \
in queries and screening keywords. start_pipeline runs search, dedup and keyword \
screening in the background (replacing that project's earlier search results); \
poll get_pipeline_progress. Then screen the "maybe" papers with \
get_papers_to_screen and batch_screen_papers, run the eligibility pass with \
get_papers_for_eligibility and batch_eligibility_screen, and finish with \
generate_report. Every tool returns JSON; failures come back as {"error": ...}.
"""

# Initialize MCP server
mcp = FastMCP("prisma-review", instructions=INSTRUCTIONS)
# FastMCP reports the SDK version as the server version; report the tool's.
mcp._mcp_server.version = __version__

# Shared file lock and singleton SessionManager for pipeline operations
_file_lock = threading.Lock()
_session_manager: SessionManager | None = None


def _dumps(data: Any) -> str:
    # default=str: YAML can hold dates and other non-JSON scalars.
    return json.dumps(data, indent=2, default=str)


def _error(message: str, **extra: Any) -> str:
    return _dumps({"error": message, **extra})


def _tool(fn: Callable[..., str]) -> Callable[..., str]:
    """Register ``fn`` as an MCP tool whose failures come back as JSON errors."""

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> str:
        try:
            return fn(*args, **kwargs)
        except (workspace.WorkspaceError, ConfigError, FileNotFoundError) as exc:
            return _error(str(exc))
        except Exception as exc:  # noqa: BLE001 - an agent gets JSON, the log gets the trace
            traceback.print_exc(file=sys.stderr)
            return _error(f"{type(exc).__name__}: {exc}")

    return mcp.tool()(wrapper)


def _get_config() -> Config:
    """The config every tool acts on, resolved on each call (see prisma_review.workspace).

    PRISMA_CONFIG pins it; otherwise it follows the active project, including
    switches made in the web app. An invalid marker is an error, not a fallback.
    """
    return Config.load(workspace.resolve_config_path())


def _target(config: Config) -> dict:
    """Which review a response is about; echoed by every tool that changes something."""
    path = config.config_path
    return {
        "project": workspace.project_for_config(path) if path else None,
        "project_name": config.project_name,
        "config_path": str(path) if path else None,
    }


def _get_session_manager() -> SessionManager:
    """Get or create the singleton SessionManager for MCP context."""
    global _session_manager
    if _session_manager is None:
        config = _get_config()
        _session_manager = SessionManager(_file_lock, state_file=config.state_file)
    return _session_manager


def _pipeline_active() -> bool:
    """True while this server runs a pipeline: switching projects would orphan it."""
    return _session_manager is not None and _session_manager.is_running


_RUNNING_ERROR = ("A pipeline is running in this server. Wait for it to finish or call "
                  "stop_pipeline before switching projects.")


def _config_guard(config: Config, problems_key: str = "problems") -> str | None:
    """Return a JSON error if the config isn't ready for the given scope, else None.

    ``problems_key`` selects the relevant subset from ``Config.readiness()``:
    "problems" (everything), "search_problems", or "screen_problems".
    """
    readiness = config.readiness()
    problems = readiness.get(problems_key) or []
    if problems:
        if any("template" in p for p in problems):
            headline = "Config not ready: it still contains template placeholders."
        else:
            headline = "Config not ready."
        return _error(
            headline,
            **_target(config),
            problems=problems,
            hint="Inspect with get_review_config, fill in the missing fields with "
                 "set_review_config (or the web Settings page), then retry.",
        )
    return None


def _safe_warnings(fn: Callable[[Config], list[str]], config: Config) -> list[str]:
    try:
        return list(fn(config))
    except Exception as exc:  # noqa: BLE001 - a malformed config must not hide the rest
        return [f"Could not compute {fn.__name__}: {exc}"]


def log_startup() -> None:
    """Say which review this server will act on (stderr; stdout carries JSON-RPC)."""
    lines = [f"prisma-review MCP server {__version__}"]
    try:
        res = workspace.resolve()
        via = {"env": workspace.ENV_CONFIG, "marker": "projects/.active_project",
               "root": "root config.yaml, no active project"}[res.source]
        lines.append(f"  project: {res.project or '-'} | config: {res.config_path} (from {via})")
        try:
            lines += [f"  warning: {w}" for w in Config.load(res.config_path).readiness()["warnings"]]
        except (ConfigError, OSError) as exc:
            lines.append(f"  warning: {exc}")
    except workspace.WorkspaceError as exc:
        lines.append(f"  no usable config: {exc}")
    print("\n".join(lines), file=sys.stderr, flush=True)


def main() -> None:
    log_startup()
    mcp.run(transport="stdio")


class QueryDef(TypedDict):
    name: str
    terms: str


class Decision(TypedDict):
    paper_id: str
    decision: str
    reason: NotRequired[str]


def _decision_items(decisions: list[Decision] | str) -> list[dict] | str:
    """The decisions as a list of dicts, or a JSON error string."""
    if isinstance(decisions, str):
        try:
            decisions = json.loads(decisions)
        except json.JSONDecodeError:
            return _error("Invalid JSON in decisions parameter")
    if not isinstance(decisions, list) or not all(isinstance(d, dict) for d in decisions):
        return _error("decisions must be a list of objects with paper_id, decision and reason")
    return decisions


@_tool
def get_screening_stats() -> str:
    """Get current screening statistics: total papers, how many included, excluded, maybe, and remaining to screen."""
    config = _get_config()
    state = load_state(config.state_file)

    if not state:
        return _error("No pipeline state found. Run start_pipeline (or 'python -m prisma_review search') first.",
                      **_target(config))

    result = {
        **_target(config),
        "search": state.get("search", {}),
        "dedup": state.get("dedup", {}),
        "screen": state.get("screen", {}),
    }
    return _dumps(result)


@_tool
def get_review_config() -> str:
    """Inspect the review configuration this server will run (read-only). Call this first.

    Returns the project, config file path and how it was chosen
    (`resolved_from`: env = PRISMA_CONFIG, marker = active project, root),
    the sources, date window, queries, screening rules and source-side
    filters, plus `ready`, `problems` (what blocks a run) and `warnings`
    (what changes results, e.g. OpenAlex without an API key).
    `query_warnings` says, per source, which parts of each query it cannot
    use; `filter_warnings` says which filters are applied locally after fetch
    or ignored. Use set_review_config to change any of it.
    """
    res = workspace.resolve()
    config = Config.load(res.config_path)
    readiness = config.readiness()
    return _dumps({
        **_target(config),
        "resolved_from": res.source,
        "sources": config.sources,
        "date_range": {"start": config.date_start, "end": config.date_end},
        "max_results_per_query": config.max_results,
        "queries": config.queries,
        "screening_rules": {
            "include_keywords": config.include_keywords,
            "exclude_keywords": config.exclude_keywords,
            "min_include_hits": config.min_include_hits,
            "required_keywords": config.required_keywords,
        },
        "filters": {
            "document_types": config.filter_document_types,
            "require_abstract": config.filter_require_abstract,
            "open_access": config.filter_open_access,
            "venues": config.filter_venues,
        },
        "query_warnings": _safe_warnings(query_warnings, config),
        "filter_warnings": _safe_warnings(filter_warnings, config),
        "ready": readiness["ready"],
        "problems": readiness["problems"],
        "warnings": readiness["warnings"],
    })


@_tool
def get_papers_to_screen(batch_size: int = 10, filter_type: str = "maybe") -> str:
    """Get a batch of papers that need screening.

    Args:
        batch_size: Number of papers to return (default 10)
        filter_type: "maybe" for uncertain papers, "unscreened" for all unscreened, "all" for everything
    """
    config = _get_config()

    if filter_type == "maybe":
        papers = load_papers(config.screen_dir / "maybe.json")
    elif filter_type == "unscreened":
        papers = load_papers(config.dedup_dir / "deduplicated.json")
        papers = [p for p in papers if p.screen_decision is None]
    else:
        papers = load_papers(config.screen_dir / "screen_results.json")

    batch = papers[:batch_size]
    result = []
    for p in batch:
        result.append({
            "id": p.id,
            "title": p.title,
            "authors": "; ".join(p.authors[:5]),
            "year": p.year,
            "abstract": p.abstract[:500] + ("..." if len(p.abstract) > 500 else ""),
            "venue": p.venue or "",
            "source": p.source,
            "doi": p.doi or "",
            "current_decision": p.screen_decision,
            "current_reason": p.screen_reason,
        })

    return _dumps({
        "total_matching": len(papers),
        "returned": len(batch),
        "papers": result,
    })


@_tool
def get_paper_details(paper_id: str) -> str:
    """Get full details of a specific paper by its ID.

    Args:
        paper_id: The paper's unique ID
    """
    config = _get_config()

    # Search across all result files
    for fname in ["screen_results.json", "included.json", "excluded.json", "maybe.json"]:
        papers = load_papers(config.screen_dir / fname)
        for p in papers:
            if p.id == paper_id:
                return _dumps({
                    "id": p.id,
                    "title": p.title,
                    "authors": p.authors,
                    "year": p.year,
                    "abstract": p.abstract,
                    "venue": p.venue,
                    "doi": p.doi,
                    "url": p.url,
                    "source": p.source,
                    "keywords": p.keywords,
                    "screen_decision": p.screen_decision,
                    "screen_reason": p.screen_reason,
                    "screen_method": p.screen_method,
                })

    # Also check dedup results
    papers = load_papers(config.dedup_dir / "deduplicated.json")
    for p in papers:
        if p.id == paper_id:
            return _dumps({"id": p.id, "title": p.title, "authors": p.authors,
                           "year": p.year, "abstract": p.abstract, "venue": p.venue,
                           "doi": p.doi, "url": p.url, "source": p.source})

    return _error(f"Paper with ID '{paper_id}' not found.")


@_tool
def screen_paper(paper_id: str, decision: str, reason: str) -> str:
    """Save a screening decision for a single paper.

    Args:
        paper_id: The paper's unique ID
        decision: "include" or "exclude"
        reason: Brief reason for the decision
    """
    if decision not in ("include", "exclude"):
        return _error("Decision must be 'include' or 'exclude'")

    config = _get_config()
    all_papers = load_papers(config.screen_dir / "screen_results.json")

    found = False
    for p in all_papers:
        if p.id == paper_id:
            p.screen_decision = decision
            p.screen_reason = reason
            p.screen_method = "ai"
            found = True
            break

    if not found:
        return _error(f"Paper '{paper_id}' not found in screen results.", **_target(config))

    # Save updated results
    save_papers(all_papers, config.screen_dir / "screen_results.json")
    included = get_by_decision(all_papers, "include")
    excluded = get_by_decision(all_papers, "exclude")
    maybe = get_by_decision(all_papers, "maybe")
    save_papers(included, config.screen_dir / "included.json")
    save_papers(excluded, config.screen_dir / "excluded.json")
    save_papers(maybe, config.screen_dir / "maybe.json")

    # Update state
    state = load_state(config.state_file)
    state["screen"] = {
        "total_screened": len(all_papers),
        "included": len(included),
        "excluded": len(excluded),
        "maybe": len(maybe),
    }
    save_state(state, config.state_file)

    return _dumps({
        "status": "ok",
        **_target(config),
        "paper_id": paper_id,
        "decision": decision,
        "remaining_maybe": len(maybe),
    })


@_tool
def batch_screen_papers(decisions: list[Decision] | str) -> str:
    """Save screening decisions for multiple papers at once.

    Args:
        decisions: List of {"paper_id", "decision" ("include"/"exclude"), "reason"},
                   e.g. [{"paper_id": "abc123", "decision": "include", "reason": "meets criterion 2"}].
                   A JSON string of the same list is also accepted.
    """
    items = _decision_items(decisions)
    if isinstance(items, str):
        return items

    config = _get_config()
    all_papers = load_papers(config.screen_dir / "screen_results.json")
    paper_map = {p.id: p for p in all_papers}

    results = []
    for item in items:
        pid = item.get("paper_id", "")
        dec = item.get("decision", "")
        reason = item.get("reason", "")

        if dec not in ("include", "exclude"):
            results.append({"paper_id": pid, "status": "error", "message": "invalid decision"})
            continue

        if pid not in paper_map:
            results.append({"paper_id": pid, "status": "error", "message": "not found"})
            continue

        paper_map[pid].screen_decision = dec
        paper_map[pid].screen_reason = reason
        paper_map[pid].screen_method = "ai"
        results.append({"paper_id": pid, "status": "ok", "decision": dec})

    # Save
    save_papers(all_papers, config.screen_dir / "screen_results.json")
    included = get_by_decision(all_papers, "include")
    excluded = get_by_decision(all_papers, "exclude")
    maybe = get_by_decision(all_papers, "maybe")
    save_papers(included, config.screen_dir / "included.json")
    save_papers(excluded, config.screen_dir / "excluded.json")
    save_papers(maybe, config.screen_dir / "maybe.json")

    state = load_state(config.state_file)
    state["screen"] = {
        "total_screened": len(all_papers),
        "included": len(included),
        "excluded": len(excluded),
        "maybe": len(maybe),
    }
    save_state(state, config.state_file)

    return _dumps({
        **_target(config),
        "processed": len(results),
        "remaining_maybe": len(maybe),
        "results": results,
    })


@_tool
def get_papers_for_eligibility(batch_size: int = 10) -> str:
    """Get a batch of first-pass included papers that need eligibility screening (second pass).

    Args:
        batch_size: Number of papers to return (default 10)
    """
    config = _get_config()
    papers = load_papers(config.screen_dir / "included.json")

    # Load existing eligibility results to skip already-screened papers
    elig_results = load_papers(config.eligibility_dir / "eligibility_results.json")
    screened_ids = {p.id for p in elig_results if p.eligibility_decision is not None}

    unscreened = [p for p in papers if p.id not in screened_ids]
    batch = unscreened[:batch_size]

    result = []
    for p in batch:
        result.append({
            "id": p.id,
            "title": p.title,
            "authors": "; ".join(p.authors[:5]),
            "year": p.year,
            "abstract": p.abstract,
            "venue": p.venue or "",
            "source": p.source,
            "doi": p.doi or "",
            "screen_decision": p.screen_decision,
            "screen_reason": p.screen_reason,
        })

    return _dumps({
        "total_first_pass_included": len(papers),
        "already_screened": len(screened_ids),
        "remaining": len(unscreened),
        "returned": len(batch),
        "papers": result,
    })


@_tool
def eligibility_screen_paper(paper_id: str, decision: str, reason: str) -> str:
    """Save an eligibility screening decision for a single paper (second pass).

    Args:
        paper_id: The paper's unique ID
        decision: "include" or "exclude"
        reason: Brief reason for the decision
    """
    if decision not in ("include", "exclude"):
        return _error("Decision must be 'include' or 'exclude'")

    config = _get_config()
    all_papers = load_papers(config.screen_dir / "included.json")

    # Load or initialize eligibility results
    elig_path = config.eligibility_dir / "eligibility_results.json"
    elig_results = load_papers(elig_path)
    elig_map = {p.id: p for p in elig_results}

    # Find the paper and update
    found = False
    for p in all_papers:
        if p.id == paper_id:
            p.eligibility_decision = decision
            p.eligibility_reason = reason
            p.eligibility_method = "ai"
            elig_map[p.id] = p
            found = True
            break

    if not found:
        return _error(f"Paper '{paper_id}' not found in first-pass included papers.",
                      **_target(config))

    # Save all eligibility results
    all_elig = list(elig_map.values())
    save_papers(all_elig, elig_path)
    elig_included = [p for p in all_elig if p.eligibility_decision == "include"]
    elig_excluded = [p for p in all_elig if p.eligibility_decision == "exclude"]
    save_papers(elig_included, config.eligibility_dir / "eligible_included.json")
    save_papers(elig_excluded, config.eligibility_dir / "eligible_excluded.json")

    # Update state
    state = load_state(config.state_file)
    state["eligibility"] = {
        "input_from_screening": len(all_papers),
        "screened": len(all_elig),
        "included": len(elig_included),
        "excluded": len(elig_excluded),
        "remaining": len(all_papers) - len(all_elig),
    }
    save_state(state, config.state_file)

    return _dumps({
        "status": "ok",
        **_target(config),
        "paper_id": paper_id,
        "decision": decision,
        "remaining": len(all_papers) - len(all_elig),
    })


@_tool
def batch_eligibility_screen(decisions: list[Decision] | str) -> str:
    """Save eligibility screening decisions for multiple papers at once (second pass).

    Args:
        decisions: List of {"paper_id", "decision" ("include"/"exclude"), "reason"},
                   e.g. [{"paper_id": "abc123", "decision": "exclude", "reason": "no empirical evaluation"}].
                   A JSON string of the same list is also accepted.
    """
    items = _decision_items(decisions)
    if isinstance(items, str):
        return items

    config = _get_config()
    all_papers = load_papers(config.screen_dir / "included.json")
    paper_map = {p.id: p for p in all_papers}

    # Load or initialize eligibility results
    elig_path = config.eligibility_dir / "eligibility_results.json"
    elig_results = load_papers(elig_path)
    elig_map = {p.id: p for p in elig_results}

    results = []
    for item in items:
        pid = item.get("paper_id", "")
        dec = item.get("decision", "")
        reason = item.get("reason", "")

        if dec not in ("include", "exclude"):
            results.append({"paper_id": pid, "status": "error", "message": "invalid decision"})
            continue

        if pid not in paper_map:
            results.append({"paper_id": pid, "status": "error", "message": "not found"})
            continue

        paper_map[pid].eligibility_decision = dec
        paper_map[pid].eligibility_reason = reason
        paper_map[pid].eligibility_method = "ai"
        elig_map[pid] = paper_map[pid]
        results.append({"paper_id": pid, "status": "ok", "decision": dec})

    # Save
    all_elig = list(elig_map.values())
    save_papers(all_elig, elig_path)
    elig_included = [p for p in all_elig if p.eligibility_decision == "include"]
    elig_excluded = [p for p in all_elig if p.eligibility_decision == "exclude"]
    save_papers(elig_included, config.eligibility_dir / "eligible_included.json")
    save_papers(elig_excluded, config.eligibility_dir / "eligible_excluded.json")

    # Update state
    state = load_state(config.state_file)
    state["eligibility"] = {
        "input_from_screening": len(all_papers),
        "screened": len(all_elig),
        "included": len(elig_included),
        "excluded": len(elig_excluded),
        "remaining": len(all_papers) - len(all_elig),
    }
    save_state(state, config.state_file)

    return _dumps({
        **_target(config),
        "processed": len(results),
        "remaining": len(all_papers) - len(all_elig),
        "results": results,
    })


@_tool
def search_in_papers(query: str) -> str:
    """Search within collected papers by keyword in title or abstract.

    Args:
        query: Search term to look for in titles and abstracts
    """
    config = _get_config()
    papers = load_papers(config.screen_dir / "screen_results.json")
    if not papers:
        papers = load_papers(config.dedup_dir / "deduplicated.json")

    query_lower = query.lower()
    matches = []
    for p in papers:
        text = (p.title + " " + p.abstract).lower()
        if query_lower in text:
            matches.append({
                "id": p.id,
                "title": p.title,
                "year": p.year,
                "source": p.source,
                "decision": p.screen_decision,
            })

    return _dumps({"query": query, "matches": len(matches), "papers": matches[:20]})


@_tool
def generate_report() -> str:
    """Generate PRISMA flow diagram and export included papers to .bib and .csv."""
    config = _get_config()
    state = load_state(config.state_file)

    if not state:
        return _error("No pipeline state. Run the search pipeline first.", **_target(config))

    # Generate diagrams
    generate_markdown_diagram(state, config.export_dir / "prisma_flow.md")
    generate_png_diagram(state, config.export_dir / "prisma_flow.png")

    # Export first-pass included papers
    included = load_papers(config.screen_dir / "included.json")
    if included:
        export_bibtex(included, config.export_dir / "included_papers.bib")
        export_csv(included, config.export_dir / "included_papers.csv")

    outputs = [
        str(config.export_dir / "prisma_flow.md"),
        str(config.export_dir / "prisma_flow.png"),
        str(config.export_dir / "included_papers.bib"),
        str(config.export_dir / "included_papers.csv"),
    ]

    # Export eligibility-screened papers if they exist
    eligible = load_papers(config.eligibility_dir / "eligible_included.json")
    if eligible:
        export_bibtex(eligible, config.export_dir / "eligible_papers.bib")
        export_csv(eligible, config.export_dir / "eligible_papers.csv")
        outputs.extend([
            str(config.export_dir / "eligible_papers.bib"),
            str(config.export_dir / "eligible_papers.csv"),
        ])

    return _dumps({
        "status": "ok",
        **_target(config),
        "included_papers": len(included),
        "eligible_papers": len(eligible),
        "outputs": outputs,
        "flow_summary": state,
    })


@_tool
def download_eligible_papers() -> str:
    """Download open access PDFs for eligible papers. Only downloads legally available open access papers (arXiv, Unpaywall, Semantic Scholar)."""
    config = _get_config()

    papers = load_papers(config.eligibility_dir / "eligible_included.json")
    source = "eligible"
    if not papers:
        papers = load_papers(config.screen_dir / "included.json")
        source = "included"

    if not papers:
        return _error("No papers found. Run screening first.", **_target(config))

    pdf_dir = config.output_dir / "05_pdfs"
    stats = download_papers(papers, pdf_dir, email=config.openalex_email, api_key=config.scopus_key)

    return _dumps({
        "status": "ok",
        **_target(config),
        "source": source,
        "total": stats["total"],
        "downloaded": stats["downloaded"],
        "no_open_access": stats["no_open_access"],
        "failed": stats["failed"],
        "output_dir": str(pdf_dir),
    })


# ── Configuration & Project Management ──────────────────────────────


_ISO_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


def _valid_iso_date(value: object) -> bool:
    if not isinstance(value, str) or not _ISO_DATE_RE.fullmatch(value):
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def _clean_terms(field: str, values: list, errors: list[str]) -> list[str]:
    """Strip a list of terms, reporting entries that are not non-empty strings."""
    cleaned = []
    for v in values:
        if not isinstance(v, str) or not v.strip():
            errors.append(f"{field}: every entry must be a non-empty string (got {v!r}).")
        else:
            cleaned.append(v.strip())
    return cleaned


def _clean_choices(field: str, values: list, allowed: tuple[str, ...], errors: list[str]) -> list[str]:
    """Lowercase and de-duplicate a list of enum values, reporting unknown ones."""
    cleaned: list[str] = []
    for v in values:
        key = v.strip().lower() if isinstance(v, str) else v
        if key not in allowed:
            errors.append(f"{field}: unknown value {v!r}. Allowed: {', '.join(allowed)}.")
        elif key not in cleaned:
            cleaned.append(key)
    return cleaned


def _parse_queries(queries: list | str, errors: list[str]) -> list[dict] | None:
    if isinstance(queries, str):
        try:
            queries = json.loads(queries)
        except json.JSONDecodeError as e:
            errors.append(f"queries is not valid JSON: {e}")
            return None
    if not isinstance(queries, list) or not queries:
        errors.append('queries must be a non-empty list of {"name", "terms"} objects.')
        return None
    parsed, names = [], set()
    for i, q in enumerate(queries):
        if not isinstance(q, dict):
            errors.append(f'queries[{i}] must be an object with "name" and "terms".')
            continue
        name, terms = q.get("name"), q.get("terms")
        if not isinstance(name, str) or not name.strip():
            errors.append(f"queries[{i}].name must be a non-empty string.")
            continue
        if not isinstance(terms, str) or not terms.strip():
            errors.append(f"queries[{i}].terms must be a non-empty string.")
            continue
        if name.strip() in names:
            errors.append(f"queries[{i}].name {name.strip()!r} is used twice; names must be unique.")
            continue
        names.add(name.strip())
        parsed.append({"name": name.strip(), "terms": " ".join(terms.split())})
    return parsed


def _section(data: dict, key: str) -> dict:
    """``data[key]`` as a mapping, replacing null (a YAML section left empty)."""
    value = data.get(key)
    if not isinstance(value, dict):
        value = data[key] = {}
    return value


@_tool
def set_review_config(
    name: str | None = None,
    sources: list[str] | None = None,
    date_start: str | None = None,
    date_end: str | None = None,
    queries: list[QueryDef] | str | None = None,
    include_keywords: list[str] | None = None,
    exclude_keywords: list[str] | None = None,
    min_include_hits: int | None = None,
    required_keywords: list[str] | None = None,
    document_types: list[str] | None = None,
    require_abstract: bool | None = None,
    open_access: bool | None = None,
    venues: list[str] | None = None,
) -> str:
    """Change the review configuration (the config.yaml in use). Only passed fields change.

    Everything is validated first; nothing is written if any value is invalid.
    Returns the project, config_path, readiness (ready/problems/warnings) and
    the per-source query and filter warnings.

    Args:
        name: Review title.
        sources: Any of arxiv, crossref, openalex, semantic_scholar, scopus.
        date_start: Publication window start, YYYY-MM-DD.
        date_end: Publication window end, YYYY-MM-DD.
        queries: List of {"name", "terms"} with unique names; terms is a Boolean
            string, e.g. '("crop yield" OR harvest) AND "remote sensing"'.
            OpenAlex, Scopus and arXiv run the Boolean query; Crossref and
            Semantic Scholar only use its quoted phrases. Avoid * wildcards.
            A JSON string of the list is also accepted.
        include_keywords: Screening terms matched in title and abstract.
        exclude_keywords: Any match excludes the paper.
        min_include_hits: Include keywords a paper needs (1-10).
        required_keywords: Optional gate: papers with none of these terms are
            excluded. An empty list disables it.
        document_types: Any of journal-article, review, conference-paper,
            book-chapter, preprint.
        require_abstract: Drop records without an abstract.
        open_access: Keep only open-access records.
        venues: ISSNs ("1234-567X") or journal names.
    """
    errors: list[str] = []
    updates: dict[tuple[str, ...], Any] = {}

    if name is not None:
        if not name.strip():
            errors.append("name must not be empty.")
        updates[("project", "name")] = name.strip()
    if sources is not None:
        cleaned = _clean_choices("sources", sources, KNOWN_SOURCES, errors)
        if not sources:
            errors.append("sources must list at least one source.")
        updates[("search", "sources")] = cleaned
    for field, value in (("date_start", date_start), ("date_end", date_end)):
        if value is not None and not _valid_iso_date(value):
            errors.append(f"{field} must be an ISO date YYYY-MM-DD (got {value!r}).")
    if date_start is not None:
        updates[("search", "date_range", "start")] = date_start
    if date_end is not None:
        updates[("search", "date_range", "end")] = date_end
    if queries is not None:
        updates[("search", "queries")] = _parse_queries(queries, errors)
    for field, value in (("include_keywords", include_keywords),
                         ("exclude_keywords", exclude_keywords),
                         ("required_keywords", required_keywords)):
        if value is not None:
            updates[("screening", "rules", field)] = _clean_terms(field, value, errors)
    if min_include_hits is not None:
        if isinstance(min_include_hits, bool) or not 1 <= min_include_hits <= 10:
            errors.append(f"min_include_hits must be between 1 and 10 (got {min_include_hits!r}).")
        updates[("screening", "rules", "min_include_hits")] = min_include_hits
    if document_types is not None:
        updates[("search", "filters", "document_types")] = _clean_choices(
            "document_types", document_types, KNOWN_DOCUMENT_TYPES, errors)
    if require_abstract is not None:
        updates[("search", "filters", "require_abstract")] = require_abstract
    if open_access is not None:
        updates[("search", "filters", "open_access")] = open_access
    if venues is not None:
        updates[("search", "filters", "venues")] = _clean_terms("venues", venues, errors)

    path = workspace.resolve_config_path()
    with project_lock(path.parent):
        data = load_raw_config(path)
        if not errors:
            current = Config(data)
            start = date_start if date_start is not None else current.date_start
            end = date_end if date_end is not None else current.date_end
            if (date_start is not None or date_end is not None) and _valid_iso_date(start) \
                    and _valid_iso_date(end) and start > end:
                errors.append(f"date_start {start} is after date_end {end}.")
        if errors:
            return _error("Invalid values; nothing was written.", problems=errors,
                          config_path=str(path))
        for keys, value in updates.items():
            node = data
            for key in keys[:-1]:
                node = _section(node, key)
            node[keys[-1]] = value
        if updates:  # a call with no fields is a read; do not rewrite (and strip comments)
            save_raw_config(path, data)

    config = Config.load(path)
    readiness = config.readiness()
    return _dumps({
        "status": "ok",
        **_target(config),
        "changed": [".".join(k) for k in updates],
        "ready": readiness["ready"],
        "problems": readiness["problems"],
        "warnings": readiness["warnings"],
        "query_warnings": _safe_warnings(query_warnings, config),
        "filter_warnings": _safe_warnings(filter_warnings, config),
    })


@_tool
def list_projects() -> str:
    """List all review projects, marking the active one (read-only).

    The active project decides which config.yaml every tool here reads and
    writes, unless PRISMA_CONFIG pins one (`pinned_config`).
    """
    active: str | None = None
    active_error: str | None = None
    try:
        active = workspace.read_active_project()
    except workspace.WorkspaceError as exc:
        active_error = str(exc)

    projects = []
    for entry_name in workspace.list_project_names():
        display_name = entry_name
        ready = False
        try:
            cfg = Config.load(workspace.projects_dir() / entry_name / "config.yaml")
            display_name = cfg.project_name
            ready = cfg.readiness()["ready"]
        except Exception:
            pass
        projects.append({
            "name": entry_name,
            "display_name": display_name,
            "is_active": entry_name == active,
            "ready": ready,
        })
    result: dict[str, Any] = {"active": active, "projects": projects}
    if active_error:
        result["active_error"] = active_error
    pin = workspace.pinned_config_path()
    if pin is not None:
        result["pinned_config"] = str(pin)
    return _dumps(result)


@_tool
def switch_project(name: str) -> str:
    """Switch the active project (mirrors the web app's project switcher).

    Refused while a pipeline runs in this server or when PRISMA_CONFIG pins the config.

    Args:
        name: The project's folder name: the 'name' field from list_projects().
    """
    global _session_manager
    workspace.validate_project_name(name)
    workspace.ensure_not_pinned()
    if _pipeline_active():
        return _error(_RUNNING_ERROR)
    workspace.set_active_project(name)
    _session_manager = None  # new project, new state file: drop the cached manager

    config = _get_config()
    readiness = config.readiness()
    return _dumps({
        "status": "switched",
        "active": name,
        **_target(config),
        "ready": readiness["ready"],
        "problems": readiness["problems"],
        "warnings": readiness["warnings"],
    })


@_tool
def create_project(name: str, switch: bool = True) -> str:
    """Create a new review project from the config template.

    On an install that only has a root config.yaml, that review is first
    moved into projects/ (files kept) so it stays reachable.

    Args:
        name: Human-readable review title (a folder name is derived from it).
        switch: If true (default), make the new project active. Refused while
            a pipeline runs here or when PRISMA_CONFIG pins the config.
    """
    global _session_manager
    if switch:
        workspace.ensure_not_pinned()
        if _pipeline_active():
            return _error(_RUNNING_ERROR + " Or create it with switch=false.")

    migrated = None
    if workspace.pinned_config_path() is None:
        migrated = workspace.migrate_root_to_projects()
    slug = workspace.create_project(name)

    result: dict[str, Any] = {"status": "created", "name": slug, "display_name": name.strip()}
    if migrated:
        result["migrated_root_project"] = migrated
        result["note"] = (f"The review in the root config.yaml was copied to projects/{migrated} "
                          f"so it stays listed and reachable.")
    if switch:
        workspace.set_active_project(slug)
        _session_manager = None
        result["active"] = slug
    result.update(_target(Config.load(workspace.project_config_path(slug))))
    return _dumps(result)


@_tool
def rescreen(min_include_hits: int) -> str:
    """Re-run keyword screening on the deduplicated papers with a new threshold.

    Does NOT re-search or re-deduplicate — only re-applies the screening rules
    with a different min_include_hits. Manual decisions are preserved. Mirrors
    the web app's re-screen control.

    Args:
        min_include_hits: How many include keywords must match (1-10).
    """
    if not (1 <= min_include_hits <= 10):
        return _error("min_include_hits must be between 1 and 10.")

    config = _get_config()
    guard = _config_guard(config, "screen_problems")
    if guard is not None:
        return guard

    papers = load_papers(config.dedup_dir / "deduplicated.json")
    if not papers:
        return _error("No deduplicated papers found. Run the pipeline first.", **_target(config))

    # Reset rule-based decisions, preserve manual ones.
    for p in papers:
        if p.screen_method != "manual":
            p.screen_decision = None
            p.screen_reason = None
            p.screen_method = None

    papers = screen_by_rules(papers, config.include_keywords, config.exclude_keywords,
                             min_include_hits, config.required_keywords)
    included = get_by_decision(papers, "include")
    excluded = get_by_decision(papers, "exclude")
    maybe = get_by_decision(papers, "maybe")
    excluded_no_required = count_excluded_by_required(excluded)

    with _file_lock:
        save_papers(papers, config.screen_dir / "screen_results.json")
        save_papers(included, config.screen_dir / "included.json")
        save_papers(excluded, config.screen_dir / "excluded.json")
        save_papers(maybe, config.screen_dir / "maybe.json")

        state = load_state(config.state_file)
        state["screen"] = {
            "total_screened": len(papers),
            "included": len(included),
            "excluded": len(excluded),
            "maybe": len(maybe),
            "excluded_no_required_keyword": excluded_no_required,
        }
        save_state(state, config.state_file)

    return _dumps({
        "status": "ok",
        **_target(config),
        "min_include_hits": min_include_hits,
        "included": len(included),
        "excluded": len(excluded),
        "maybe": len(maybe),
        "excluded_no_required_keyword": excluded_no_required,
    })


# ── Pipeline Session Management ─────────────────────────────────────


@_tool
def start_pipeline() -> str:
    """Start the full pipeline (search → dedup → screen) in a background thread.

    Replaces the project's earlier search, dedup, screening and eligibility
    results. Returns the session ID, the project it runs on and config
    warnings. Only one pipeline can run at a time. Use get_pipeline_progress()
    to monitor progress.
    """
    config = _get_config()

    guard = _config_guard(config, "problems")
    if guard is not None:
        return guard

    session = _get_session_manager()

    if session.is_running:
        return _error("Pipeline is already running", status="running", **_target(config))

    session_id = session.start_full_pipeline(config)
    return _dumps({"status": "started", "session_id": session_id, **_target(config),
                   "warnings": config.readiness()["warnings"]})


@_tool
def get_pipeline_progress() -> str:
    """Get the current pipeline progress (status, current step, message, completed steps, warnings).

    This is fast (no disk I/O) and safe to call frequently.
    Status is one of: idle, running, completed, failed, cancelled.
    """
    session = _get_session_manager()
    return _dumps(session.get_progress())


@_tool
def stop_pipeline() -> str:
    """Request cancellation of the running pipeline.

    The pipeline will stop after the current step finishes. Results from
    completed steps are preserved.
    """
    session = _get_session_manager()
    if not session.request_cancel():
        return _error("No pipeline is currently running")
    try:
        target = _target(_get_config())
    except Exception:  # noqa: BLE001 - the cancel itself already succeeded
        target = {}
    return _dumps({"status": "cancel_requested", **target})


@_tool
def start_pipeline_step(step: str) -> str:
    """Start a single pipeline step in a background thread.

    Args:
        step: The step to run — one of "search", "dedup", or "screen"
    """
    if step not in ("search", "dedup", "screen"):
        return _error(f"Unknown step: {step}. Must be 'search', 'dedup', or 'screen'.")

    config = _get_config()

    # Guard only the steps that consume config content: search needs queries,
    # screen needs include keywords; dedup operates on prior output only.
    guard_scope = {"search": "search_problems", "screen": "screen_problems"}.get(step)
    if guard_scope is not None:
        guard = _config_guard(config, guard_scope)
        if guard is not None:
            return guard

    session = _get_session_manager()

    if session.is_running:
        return _error("Pipeline is already running", status="running", **_target(config))

    session_id = session.start_step(step, config)
    return _dumps({"status": "started", "session_id": session_id, "step": step, **_target(config)})


if __name__ == "__main__":
    main()
