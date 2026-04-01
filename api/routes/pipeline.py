"""Pipeline endpoints — trigger search, dedup, screening steps.

Supports both synchronous (blocking) and background (non-blocking) execution.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from prisma_review.config import Config
from prisma_review.models import load_papers, save_papers
from prisma_review.search.runner import run_all_searches
from prisma_review.dedup import deduplicate, save_dedup_log
from prisma_review.screen import screen_by_rules, get_by_decision
from prisma_review.diagram import load_state, save_state

from api.deps import get_config, get_file_lock, get_session_manager
from api.session import SessionManager

router = APIRouter(prefix="/pipeline", tags=["pipeline"])


# ── Status / progress ────────────────────────────────────────────────

@router.get("/status")
def pipeline_status(config: Config = Depends(get_config)):
    state = load_state(config.state_file)
    return {"project": config.project_name, "output_dir": str(config.output_dir), **state}


@router.get("/progress")
def pipeline_progress(session: SessionManager = Depends(get_session_manager)):
    """Fast polling endpoint — returns in-memory progress, no disk I/O."""
    return session.get_progress()


# ── Background execution ─────────────────────────────────────────────

@router.post("/start")
def start_pipeline(
    config: Config = Depends(get_config),
    session: SessionManager = Depends(get_session_manager),
):
    """Start the full pipeline (search -> dedup -> screen) in a background thread."""
    if session.is_running:
        raise HTTPException(status_code=409, detail="Pipeline is already running")
    session_id = session.start_full_pipeline(config)
    return {"status": "started", "session_id": session_id}


@router.post("/start/{step}")
def start_single_step(
    step: str,
    config: Config = Depends(get_config),
    session: SessionManager = Depends(get_session_manager),
):
    """Start a single pipeline step in a background thread."""
    if session.is_running:
        raise HTTPException(status_code=409, detail="Pipeline is already running")
    if step not in ("search", "dedup", "screen"):
        raise HTTPException(status_code=400, detail=f"Unknown step: {step}")
    session_id = session.start_step(step, config)
    return {"status": "started", "session_id": session_id, "step": step}


@router.post("/stop")
def stop_pipeline(session: SessionManager = Depends(get_session_manager)):
    """Request cancellation of the running pipeline."""
    if not session.request_cancel():
        raise HTTPException(status_code=409, detail="No pipeline is currently running")
    return {"status": "cancel_requested"}


# ── Synchronous (legacy) endpoints ───────────────────────────────────

@router.post("/search")
def run_search(config: Config = Depends(get_config), lock=Depends(get_file_lock)):
    with lock:
        results = run_all_searches(config)

        all_papers = []
        source_counts = {}
        for key, papers in results.items():
            source_name = key.split("_")[0]
            source_counts[source_name] = source_counts.get(source_name, 0) + len(papers)
            all_papers.extend(papers)

        save_papers(all_papers, config.search_dir / "all_records.json")

        state = load_state(config.state_file)
        state["search"] = {**source_counts, "total": len(all_papers)}
        save_state(state, config.state_file)

    return {"status": "ok", "total": len(all_papers), "sources": source_counts}


@router.post("/dedup")
def run_dedup(config: Config = Depends(get_config), lock=Depends(get_file_lock)):
    papers = load_papers(config.search_dir / "all_records.json")
    if not papers:
        return {"error": "No papers found. Run search first."}

    with lock:
        unique, log = deduplicate(papers, config.doi_match, config.fuzzy_threshold)
        save_papers(unique, config.dedup_dir / "deduplicated.json")
        save_dedup_log(log, config.dedup_dir / "duplicates_log.csv")

        state = load_state(config.state_file)
        state["dedup"] = {"duplicates_removed": len(papers) - len(unique), "remaining": len(unique)}
        save_state(state, config.state_file)

    return {"status": "ok", "duplicates_removed": len(papers) - len(unique), "remaining": len(unique)}


@router.post("/screen")
def run_screen(config: Config = Depends(get_config), lock=Depends(get_file_lock)):
    papers = load_papers(config.dedup_dir / "deduplicated.json")
    if not papers:
        return {"error": "No papers found. Run dedup first."}

    with lock:
        papers = screen_by_rules(papers, config.include_keywords, config.exclude_keywords, config.min_include_hits)
        included = get_by_decision(papers, "include")
        excluded = get_by_decision(papers, "exclude")
        maybe = get_by_decision(papers, "maybe")

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
        }
        save_state(state, config.state_file)

    return {"status": "ok", "included": len(included), "excluded": len(excluded), "maybe": len(maybe)}


@router.post("/run-all")
def run_all(config: Config = Depends(get_config), lock=Depends(get_file_lock)):
    search_result = run_search(config, lock)
    if "error" in search_result:
        return search_result

    dedup_result = run_dedup(config, lock)
    if "error" in dedup_result:
        return dedup_result

    screen_result = run_screen(config, lock)
    if "error" in screen_result:
        return screen_result

    return {
        "status": "ok",
        "search": search_result,
        "dedup": dedup_result,
        "screen": screen_result,
    }
