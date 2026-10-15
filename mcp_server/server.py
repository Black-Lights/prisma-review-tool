"""MCP Server for PRISMA Review Tool.

Exposes screening tools so Claude Code can read papers,
make screening decisions, and generate reports — all via MCP.
"""

from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

import threading

import yaml
from mcp.server.fastmcp import FastMCP

# Add parent to path so we can import prisma_review
sys.path.insert(0, str(Path(__file__).parent.parent))

from prisma_review.config import Config
from prisma_review.models import Paper, save_papers, load_papers
from prisma_review.screen import get_by_decision, screen_by_rules, count_excluded_by_required
from prisma_review.export import export_bibtex, export_csv
from prisma_review.search.filters import filter_warnings
from prisma_review.download import download_papers
from prisma_review.diagram import (
    generate_markdown_diagram, generate_png_diagram,
    load_state, save_state,
)
from api.session import SessionManager

# Initialize MCP server
mcp = FastMCP("prisma-review")

# Config resolution — follow the web app's active-project selection so the MCP
# server and the web UI always read/write the SAME config.yaml. Falls back to
# the root config.yaml when no project is active (e.g. pure-CLI installs).
_ROOT = Path(__file__).parent.parent
_PROJECTS_DIR = _ROOT / "projects"
CONFIG_PATH = _ROOT / "config.yaml"  # fallback / default

# Shared file lock and singleton SessionManager for pipeline operations
_file_lock = threading.Lock()
_session_manager: SessionManager | None = None


def _active_project_name() -> str | None:
    """Active project name, mirroring the web app's projects/.active_project."""
    marker = _PROJECTS_DIR / ".active_project"
    if marker.exists():
        return marker.read_text(encoding="utf-8").strip() or None
    return None


def _resolve_config_path() -> Path:
    """Resolve config like api/main.py: active project's config, else root."""
    name = _active_project_name()
    if name:
        candidate = _PROJECTS_DIR / name / "config.yaml"
        if candidate.exists():
            return candidate
    return CONFIG_PATH


def _get_config() -> Config:
    return Config.load(_resolve_config_path())


def _slugify(text: str) -> str:
    """Mirror the web app's project slug rules (api/routes/projects.py)."""
    slug = text.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug or "default-project"


def _load_raw_config(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _save_raw_config(path: Path, data: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)


def _get_session_manager() -> SessionManager:
    """Get or create the singleton SessionManager for MCP context."""
    global _session_manager
    if _session_manager is None:
        config = _get_config()
        _session_manager = SessionManager(_file_lock, state_file=config.state_file)
    return _session_manager


def _config_guard(config: Config, problems_key: str = "problems") -> str | None:
    """Return a JSON error if the config isn't ready for the given scope, else None.

    ``problems_key`` selects the relevant subset from ``Config.readiness()``:
    "problems" (everything), "search_problems", or "screen_problems".
    """
    readiness = config.readiness()
    problems = readiness.get(problems_key) or []
    if problems:
        return json.dumps({
            "error": "Config not ready — your review configuration is still the template.",
            "config_path": str(config.config_path or CONFIG_PATH),
            "problems": problems,
            "hint": "Inspect with get_review_config, fill in the config file, then retry.",
        }, indent=2)
    return None


@mcp.tool()
def get_screening_stats() -> str:
    """Get current screening statistics: total papers, how many included, excluded, maybe, and remaining to screen."""
    config = _get_config()
    state = load_state(config.state_file)

    if not state:
        return json.dumps({"error": "No pipeline state found. Run 'python -m prisma_review search' first."})

    result = {
        "project": config.project_name,
        "search": state.get("search", {}),
        "dedup": state.get("dedup", {}),
        "screen": state.get("screen", {}),
    }
    return json.dumps(result, indent=2)


@mcp.tool()
def get_review_config() -> str:
    """Inspect the review configuration this server will run (read-only).

    Returns the config file path, project name, enabled sources, date window,
    queries, screening rules, and source-side `filters`, plus `ready` (whether
    the config is filled in or still the template) and `problems` listing
    anything left unconfigured. The `filter_warnings` list reports, per source,
    any configured filter that is applied locally after fetch (not server-side)
    or unsupported and ignored — inspect it before start_pipeline. Use
    set_review_config to change the filters.
    """
    config = _get_config()
    readiness = config.readiness()
    return json.dumps({
        "config_path": str(config.config_path or CONFIG_PATH),
        "project": config.project_name,
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
        "filter_warnings": filter_warnings(config),
        "ready": readiness["ready"],
        "problems": readiness["problems"],
    }, indent=2)


@mcp.tool()
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

    return json.dumps({
        "total_matching": len(papers),
        "returned": len(batch),
        "papers": result,
    }, indent=2)


@mcp.tool()
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
                return json.dumps({
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
                }, indent=2)

    # Also check dedup results
    papers = load_papers(config.dedup_dir / "deduplicated.json")
    for p in papers:
        if p.id == paper_id:
            return json.dumps({"id": p.id, "title": p.title, "authors": p.authors,
                               "year": p.year, "abstract": p.abstract, "venue": p.venue,
                               "doi": p.doi, "url": p.url, "source": p.source}, indent=2)

    return json.dumps({"error": f"Paper with ID '{paper_id}' not found."})


@mcp.tool()
def screen_paper(paper_id: str, decision: str, reason: str) -> str:
    """Save a screening decision for a single paper.

    Args:
        paper_id: The paper's unique ID
        decision: "include" or "exclude"
        reason: Brief reason for the decision
    """
    if decision not in ("include", "exclude"):
        return json.dumps({"error": "Decision must be 'include' or 'exclude'"})

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
        return json.dumps({"error": f"Paper '{paper_id}' not found in screen results."})

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

    return json.dumps({
        "status": "ok",
        "paper_id": paper_id,
        "decision": decision,
        "remaining_maybe": len(maybe),
    })


@mcp.tool()
def batch_screen_papers(decisions: str) -> str:
    """Save screening decisions for multiple papers at once.

    Args:
        decisions: JSON string of list of objects with keys: paper_id, decision ("include"/"exclude"), reason
                   Example: [{"paper_id": "abc123", "decision": "include", "reason": "relevant to GFMs"}]
    """
    try:
        items = json.loads(decisions)
    except json.JSONDecodeError:
        return json.dumps({"error": "Invalid JSON in decisions parameter"})

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

    return json.dumps({
        "processed": len(results),
        "remaining_maybe": len(maybe),
        "results": results,
    }, indent=2)


@mcp.tool()
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

    return json.dumps({
        "total_first_pass_included": len(papers),
        "already_screened": len(screened_ids),
        "remaining": len(unscreened),
        "returned": len(batch),
        "papers": result,
    }, indent=2)


@mcp.tool()
def eligibility_screen_paper(paper_id: str, decision: str, reason: str) -> str:
    """Save an eligibility screening decision for a single paper (second pass).

    Args:
        paper_id: The paper's unique ID
        decision: "include" or "exclude"
        reason: Brief reason for the decision
    """
    if decision not in ("include", "exclude"):
        return json.dumps({"error": "Decision must be 'include' or 'exclude'"})

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
        return json.dumps({"error": f"Paper '{paper_id}' not found in first-pass included papers."})

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

    return json.dumps({
        "status": "ok",
        "paper_id": paper_id,
        "decision": decision,
        "remaining": len(all_papers) - len(all_elig),
    })


@mcp.tool()
def batch_eligibility_screen(decisions: str) -> str:
    """Save eligibility screening decisions for multiple papers at once (second pass).

    Args:
        decisions: JSON string of list of objects with keys: paper_id, decision ("include"/"exclude"), reason
                   Example: [{"paper_id": "abc123", "decision": "include", "reason": "directly about GFMs"}]
    """
    try:
        items = json.loads(decisions)
    except json.JSONDecodeError:
        return json.dumps({"error": "Invalid JSON in decisions parameter"})

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

    return json.dumps({
        "processed": len(results),
        "remaining": len(all_papers) - len(all_elig),
        "results": results,
    }, indent=2)


@mcp.tool()
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

    return json.dumps({"query": query, "matches": len(matches), "papers": matches[:20]}, indent=2)


@mcp.tool()
def generate_report() -> str:
    """Generate PRISMA flow diagram and export included papers to .bib and .csv."""
    config = _get_config()
    state = load_state(config.state_file)

    if not state:
        return json.dumps({"error": "No pipeline state. Run the search pipeline first."})

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

    return json.dumps({
        "status": "ok",
        "included_papers": len(included),
        "eligible_papers": len(eligible),
        "outputs": outputs,
        "flow_summary": state,
    }, indent=2)


@mcp.tool()
def download_eligible_papers() -> str:
    """Download open access PDFs for eligible papers. Only downloads legally available open access papers (arXiv, Unpaywall, Semantic Scholar)."""
    config = _get_config()

    papers = load_papers(config.eligibility_dir / "eligible_included.json")
    source = "eligible"
    if not papers:
        papers = load_papers(config.screen_dir / "included.json")
        source = "included"

    if not papers:
        return json.dumps({"error": "No papers found. Run screening first."})

    pdf_dir = config.output_dir / "05_pdfs"
    stats = download_papers(papers, pdf_dir, email=config.openalex_email, api_key=config.scopus_key)

    return json.dumps({
        "status": "ok",
        "source": source,
        "total": stats["total"],
        "downloaded": stats["downloaded"],
        "no_open_access": stats["no_open_access"],
        "failed": stats["failed"],
        "output_dir": str(pdf_dir),
    }, indent=2)


# ── Configuration & Project Management ──────────────────────────────


@mcp.tool()
def set_review_config(
    name: str | None = None,
    sources: list[str] | None = None,
    date_start: str | None = None,
    date_end: str | None = None,
    queries: str | None = None,
    include_keywords: list[str] | None = None,
    exclude_keywords: list[str] | None = None,
    min_include_hits: int | None = None,
    required_keywords: list[str] | None = None,
    document_types: list[str] | None = None,
    require_abstract: bool | None = None,
    open_access: bool | None = None,
    venues: list[str] | None = None,
) -> str:
    """Write the review configuration (the active project's config.yaml).

    Only the fields you pass are changed; omit a field to leave it as-is. This
    is the structured equivalent of the web Settings page — use it to set up a
    review so the pipeline has real queries/criteria instead of the template.

    Args:
        name: Review/project title.
        sources: Search sources, e.g. ["openalex"] (free) or ["openalex", "scopus"].
        date_start: Publication window start, "YYYY-MM-DD".
        date_end: Publication window end, "YYYY-MM-DD".
        queries: JSON array string of {"name", "terms"} objects, e.g.
            '[{"name": "main", "terms": "\\"graph foundation model\\" \\"wireless\\""}]'.
            NOTE for OpenAlex (default free source): it ignores OR/NOT and uses
            only the first 5 quoted phrases — write terms as a few key phrases,
            not a full Boolean string. Call get_review_config afterwards to see
            the per-source transparency warnings.
        include_keywords: Screening include keywords.
        exclude_keywords: Screening exclude keywords.
        min_include_hits: How many include keywords must match to include a paper.
        required_keywords: Optional gate. If non-empty, a paper is auto-excluded
            unless it contains at least one of these terms in its title/abstract.
            Empty list disables the gate (default). Substring, case-insensitive.
        document_types: Source-side filter — restrict to these document types.
            Canonical values: "journal-article", "review", "conference-paper",
            "book-chapter", "preprint". Applied server-side where the source
            supports it (e.g. OpenAlex type, Crossref type:journal-article,
            Scopus DOCTYPE), and locally otherwise. Empty = no restriction.
            Not every type exists in every source (e.g. arXiv is preprint-only,
            Crossref has no "review") — call get_review_config afterwards and
            read `filter_warnings` to see what is dropped or applied locally.
        require_abstract: If true, drop records with no abstract (needed for
            keyword screening). Server-side on OpenAlex/Crossref; applied locally
            on the others.
        open_access: If true, keep only open-access records. Server-side on
            OpenAlex/Semantic Scholar/Scopus; applied locally on Crossref (it is
            not an open-access index). arXiv is open access by nature.
        venues: Restrict to these venues — give ISSNs ("1234-567X") and/or
            journal names. ISSNs filter server-side on OpenAlex/Crossref/Scopus;
            names match the venue field (locally on most sources). See
            `filter_warnings` for which apply where.

    Returns the resolved config path and the new readiness (ready/problems).
    NOTE: filters are applied at request when the source supports the facet and
    re-checked after fetch as a safety net; check `filter_warnings` from
    get_review_config to see per-source behaviour.
    """
    path = _resolve_config_path()
    if not path.exists():
        return json.dumps({"error": f"Config file not found: {path}"})

    parsed_queries = None
    if queries is not None:
        try:
            parsed_queries = json.loads(queries)
        except json.JSONDecodeError as e:
            return json.dumps({"error": f"queries is not valid JSON: {e}"})
        if (not isinstance(parsed_queries, list)
                or not all(isinstance(q, dict) and "name" in q and "terms" in q
                           for q in parsed_queries)):
            return json.dumps({
                "error": 'queries must be a JSON array of objects with "name" and "terms".',
                "example": '[{"name": "main", "terms": "\\"key phrase\\" \\"another phrase\\""}]',
            })

    data = _load_raw_config(path)
    data.setdefault("project", {})
    data.setdefault("search", {})
    data["search"].setdefault("date_range", {})
    data["search"].setdefault("filters", {})
    data.setdefault("screening", {})
    data["screening"].setdefault("rules", {})

    if name is not None:
        data["project"]["name"] = name
    if sources is not None:
        data["search"]["sources"] = sources
    if date_start is not None:
        data["search"]["date_range"]["start"] = date_start
    if date_end is not None:
        data["search"]["date_range"]["end"] = date_end
    if parsed_queries is not None:
        data["search"]["queries"] = parsed_queries
    if include_keywords is not None:
        data["screening"]["rules"]["include_keywords"] = include_keywords
    if exclude_keywords is not None:
        data["screening"]["rules"]["exclude_keywords"] = exclude_keywords
    if min_include_hits is not None:
        data["screening"]["rules"]["min_include_hits"] = min_include_hits
    if required_keywords is not None:
        data["screening"]["rules"]["required_keywords"] = required_keywords
    if document_types is not None:
        data["search"]["filters"]["document_types"] = document_types
    if require_abstract is not None:
        data["search"]["filters"]["require_abstract"] = require_abstract
    if open_access is not None:
        data["search"]["filters"]["open_access"] = open_access
    if venues is not None:
        data["search"]["filters"]["venues"] = venues

    _save_raw_config(path, data)

    config = Config.load(path)
    readiness = config.readiness()
    return json.dumps({
        "status": "ok",
        "config_path": str(path),
        "ready": readiness["ready"],
        "problems": readiness["problems"],
        "filter_warnings": filter_warnings(config),
        "note": "If the web app is running, it may need a refresh/switch to reload this config.",
    }, indent=2)


@mcp.tool()
def list_projects() -> str:
    """List all review projects, marking the active one (read-only).

    The active project decides which config.yaml every tool here reads and writes.
    """
    if not _PROJECTS_DIR.exists():
        return json.dumps({"active": None, "projects": []})

    active = _active_project_name()
    projects = []
    for entry in sorted(_PROJECTS_DIR.iterdir()):
        if not entry.is_dir() or entry.name.startswith("."):
            continue
        display_name = entry.name
        ready = False
        cfg_path = entry / "config.yaml"
        if cfg_path.exists():
            try:
                cfg = Config.load(cfg_path)
                display_name = cfg.project_name
                ready = cfg.readiness()["ready"]
            except Exception:
                pass
        projects.append({
            "name": entry.name,
            "display_name": display_name,
            "is_active": entry.name == active,
            "ready": ready,
        })
    return json.dumps({"active": active, "projects": projects}, indent=2)


@mcp.tool()
def switch_project(name: str) -> str:
    """Switch the active project (mirrors the web app's project switcher).

    Args:
        name: The project's slug — the 'name' field from list_projects().
    """
    config_path = _PROJECTS_DIR / name / "config.yaml"
    if not config_path.exists():
        return json.dumps({"error": f"Project '{name}' not found (no {config_path})."})

    global _session_manager
    _PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
    (_PROJECTS_DIR / ".active_project").write_text(name, encoding="utf-8")
    _session_manager = None  # new project → new state file; drop the cached manager

    config = Config.load(config_path)
    readiness = config.readiness()
    return json.dumps({
        "status": "switched",
        "active": name,
        "project": config.project_name,
        "ready": readiness["ready"],
        "problems": readiness["problems"],
    }, indent=2)


@mcp.tool()
def create_project(name: str, switch: bool = True) -> str:
    """Create a new review project from the config template.

    Args:
        name: Human-readable review title (a folder slug is derived from it).
        switch: If true (default), make the new project active.
    """
    global _session_manager
    slug = _slugify(name)
    project_dir = _PROJECTS_DIR / slug
    if project_dir.exists():
        return json.dumps({"error": f"Project '{slug}' already exists."})

    project_dir.mkdir(parents=True, exist_ok=True)
    dest_config = project_dir / "config.yaml"
    template = _ROOT / "config.template.yaml"

    # Carry over API keys from the active project, if any.
    active_api_keys: dict = {}
    active = _active_project_name()
    if active:
        active_cfg = _PROJECTS_DIR / active / "config.yaml"
        if active_cfg.exists():
            try:
                active_api_keys = _load_raw_config(active_cfg).get("api_keys", {}) or {}
            except Exception:
                pass

    if template.exists():
        shutil.copy2(template, dest_config)
        cfg = _load_raw_config(dest_config)
    else:
        cfg = {
            "project": {}, "api_keys": {"scopus": "", "openalex_email": ""},
            "search": {"date_range": {"start": "2015-01-01", "end": "2026-12-31"},
                       "max_results_per_query": 500, "sources": ["openalex"], "queries": []},
            "dedup": {"doi_match": True, "fuzzy_title_threshold": 90},
            "screening": {"rules": {"include_keywords": [], "exclude_keywords": [],
                                    "min_include_hits": 2, "required_keywords": []}},
        }
    cfg.setdefault("project", {})
    cfg["project"]["name"] = name
    cfg["project"]["output_dir"] = "./prisma_output"
    if active_api_keys:
        cfg["api_keys"] = active_api_keys
    _save_raw_config(dest_config, cfg)
    (project_dir / "prisma_output").mkdir(exist_ok=True)

    result = {"status": "created", "name": slug, "display_name": name}
    if switch:
        (_PROJECTS_DIR / ".active_project").write_text(slug, encoding="utf-8")
        _session_manager = None
        result["active"] = slug
    return json.dumps(result, indent=2)


@mcp.tool()
def rescreen(min_include_hits: int) -> str:
    """Re-run keyword screening on the deduplicated papers with a new threshold.

    Does NOT re-search or re-deduplicate — only re-applies the screening rules
    with a different min_include_hits. Manual decisions are preserved. Mirrors
    the web app's re-screen control.

    Args:
        min_include_hits: How many include keywords must match (1-10).
    """
    if not (1 <= min_include_hits <= 10):
        return json.dumps({"error": "min_include_hits must be between 1 and 10."})

    config = _get_config()
    papers = load_papers(config.dedup_dir / "deduplicated.json")
    if not papers:
        return json.dumps({"error": "No deduplicated papers found. Run the pipeline first."})

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

    return json.dumps({
        "status": "ok",
        "min_include_hits": min_include_hits,
        "included": len(included),
        "excluded": len(excluded),
        "maybe": len(maybe),
        "excluded_no_required_keyword": excluded_no_required,
    }, indent=2)


# ── Pipeline Session Management ─────────────────────────────────────


@mcp.tool()
def start_pipeline() -> str:
    """Start the full pipeline (search → dedup → screen) in a background thread.

    Returns the session ID and status. Only one pipeline can run at a time.
    Use get_pipeline_progress() to monitor progress.
    """
    config = _get_config()

    guard = _config_guard(config, "problems")
    if guard is not None:
        return guard

    session = _get_session_manager()

    if session.is_running:
        return json.dumps({"error": "Pipeline is already running", "status": "running"})

    session_id = session.start_full_pipeline(config)
    return json.dumps({"status": "started", "session_id": session_id})


@mcp.tool()
def get_pipeline_progress() -> str:
    """Get the current pipeline progress (status, current step, message, completed steps, warnings).

    This is fast (no disk I/O) and safe to call frequently.
    Status is one of: idle, running, completed, failed, cancelled.
    """
    session = _get_session_manager()
    return json.dumps(session.get_progress(), indent=2)


@mcp.tool()
def stop_pipeline() -> str:
    """Request cancellation of the running pipeline.

    The pipeline will stop after the current step finishes. Results from
    completed steps are preserved.
    """
    session = _get_session_manager()
    if not session.request_cancel():
        return json.dumps({"error": "No pipeline is currently running"})
    return json.dumps({"status": "cancel_requested"})


@mcp.tool()
def start_pipeline_step(step: str) -> str:
    """Start a single pipeline step in a background thread.

    Args:
        step: The step to run — one of "search", "dedup", or "screen"
    """
    if step not in ("search", "dedup", "screen"):
        return json.dumps({"error": f"Unknown step: {step}. Must be 'search', 'dedup', or 'screen'."})

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
        return json.dumps({"error": "Pipeline is already running", "status": "running"})

    session_id = session.start_step(step, config)
    return json.dumps({"status": "started", "session_id": session_id, "step": step})


if __name__ == "__main__":
    mcp.run()
