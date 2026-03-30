"""MCP Server for PRISMA Review Tool.

Exposes screening tools so Claude Code can read papers,
make screening decisions, and generate reports — all via MCP.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import threading

from mcp.server.fastmcp import FastMCP

# Add parent to path so we can import prisma_review
sys.path.insert(0, str(Path(__file__).parent.parent))

from prisma_review.config import Config
from prisma_review.models import Paper, save_papers, load_papers
from prisma_review.screen import get_by_decision
from prisma_review.export import export_bibtex, export_csv
from prisma_review.download import download_papers
from prisma_review.diagram import (
    generate_markdown_diagram, generate_png_diagram,
    load_state, save_state,
)
from api.session import SessionManager

# Initialize MCP server
mcp = FastMCP("prisma-review")

# Load config — resolve relative to this file's parent (prisma_tool/)
CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"

# Shared file lock and singleton SessionManager for pipeline operations
_file_lock = threading.Lock()
_session_manager: SessionManager | None = None


def _get_config() -> Config:
    return Config.load(CONFIG_PATH)


def _get_session_manager() -> SessionManager:
    """Get or create the singleton SessionManager for MCP context."""
    global _session_manager
    if _session_manager is None:
        config = _get_config()
        _session_manager = SessionManager(_file_lock, state_file=config.state_file)
    return _session_manager


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
    stats = download_papers(papers, pdf_dir, email=config.openalex_email)

    return json.dumps({
        "status": "ok",
        "source": source,
        "total": stats["total"],
        "downloaded": stats["downloaded"],
        "no_open_access": stats["no_open_access"],
        "failed": stats["failed"],
        "output_dir": str(pdf_dir),
    }, indent=2)


# ── Pipeline Session Management ─────────────────────────────────────


@mcp.tool()
def start_pipeline() -> str:
    """Start the full pipeline (search → dedup → screen) in a background thread.

    Returns the session ID and status. Only one pipeline can run at a time.
    Use get_pipeline_progress() to monitor progress.
    """
    config = _get_config()
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
    session = _get_session_manager()

    if session.is_running:
        return json.dumps({"error": "Pipeline is already running", "status": "running"})

    session_id = session.start_step(step, config)
    return json.dumps({"status": "started", "session_id": session_id, "step": step})


if __name__ == "__main__":
    mcp.run()
