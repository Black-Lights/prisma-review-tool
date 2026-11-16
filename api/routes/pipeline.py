"""Pipeline endpoints: trigger search, dedup, screening steps.

Supports both synchronous (blocking) and background (non-blocking) execution.
Every endpoint that writes results refuses (409) while a pipeline runs on the
project, in this process or in the MCP server.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from prisma_review import pipeline
from prisma_review.config import Config
from prisma_review.diagram import load_state
from prisma_review.pipeline import RunActiveError, StepError
from prisma_review.screen import rescreen

from api.deps import get_config, get_session_manager
from api.session import SessionManager

router = APIRouter(prefix="/pipeline", tags=["pipeline"])


def _ensure_idle(config: Config, session: SessionManager | None = None) -> None:
    """409 if a pipeline runs on this project (here or in another process)."""
    if session is not None and session.is_running:
        raise HTTPException(status_code=409, detail="Pipeline is already running")
    run = pipeline.active_run(config.state_file)
    if run is not None:
        raise HTTPException(status_code=409, detail=pipeline.describe_run(run))


# ── Status / progress ─────────────────────────────────────

@router.get("/status")
def pipeline_status(config: Config = Depends(get_config)):
    state = load_state(config.state_file)
    return {"project": config.project_name, "output_dir": str(config.output_dir), **state}


@router.get("/progress")
def pipeline_progress(
    config: Config = Depends(get_config),
    session: SessionManager = Depends(get_session_manager),
):
    """Polling endpoint: this process's run reconciled with the active
    project's state file, so MCP-driven runs are visible here too."""
    return session.get_progress(config.state_file)


# ── Background execution ────────────────────────────────

@router.post("/start")
def start_pipeline(
    config: Config = Depends(get_config),
    session: SessionManager = Depends(get_session_manager),
):
    """Start the full pipeline (search -> dedup -> screen) in a background thread."""
    _ensure_idle(config, session)
    try:
        session_id = session.start_full_pipeline(config)
    except RuntimeError as exc:  # includes RunActiveError (another process won the race)
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"status": "started", "session_id": session_id}


@router.post("/start/{step}")
def start_single_step(
    step: str,
    config: Config = Depends(get_config),
    session: SessionManager = Depends(get_session_manager),
):
    """Start a single pipeline step in a background thread."""
    if step not in pipeline.STEPS:
        raise HTTPException(status_code=400, detail=f"Unknown step: {step}")
    _ensure_idle(config, session)
    try:
        session_id = session.start_step(step, config)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"status": "started", "session_id": session_id, "step": step}


@router.post("/stop")
def stop_pipeline(
    config: Config = Depends(get_config),
    session: SessionManager = Depends(get_session_manager),
):
    """Request cancellation of the running pipeline (also one the MCP server started)."""
    if not session.request_cancel(config.state_file):
        raise HTTPException(status_code=409, detail="No pipeline is currently running")
    return {"status": "cancel_requested"}


# ── Synchronous (legacy) endpoints ────────────────────────
# Each claims the run on disk for as long as it works (pipeline.claimed_run),
# so the web app, the MCP server and the CLI refuse to start over it.


def _search(config: Config, run: pipeline.ClaimedRun) -> dict:
    run.step("search", "Searching databases...")
    outcome = pipeline.search_step(config, should_cancel=run.should_cancel)
    if outcome["status"] in ("failed", "cancelled"):
        error = outcome.get("error") or "The search was cancelled; the previous results were kept."
        run.finish(outcome["status"], f"Error in step 'search': {error}", error)
        return {"status": outcome["status"], "error": error, "warnings": outcome["warnings"]}
    result = {"status": "ok", "total": outcome["total"], "sources": outcome["sources"],
              "warnings": outcome["warnings"]}
    run.step_done("search", result, outcome["warnings"])
    return result


def _dedup(config: Config, run: pipeline.ClaimedRun) -> dict:
    run.step("dedup", "Removing duplicates...")
    try:
        result = pipeline.dedup_step(config)
    except StepError as exc:
        run.finish("failed", f"Error in step 'dedup': {exc}", str(exc))
        return {"error": str(exc)}
    run.step_done("dedup", result)
    return result


def _screen(config: Config, run: pipeline.ClaimedRun | None = None) -> dict:
    if run is not None:
        run.step("screen", "Keyword screening...")
    try:
        result = rescreen(config, persist_threshold=False, check_running=run is None)
    except RunActiveError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except StepError:
        if run is not None:
            run.finish("failed", "Error in step 'screen': no papers found", "No papers found.")
        return {"error": "No papers found. Run dedup first."}
    result = {key: result[key] for key in ("status", "included", "excluded", "maybe",
                                           "excluded_no_required_keyword")}
    if run is not None:
        run.step_done("screen", result)
    return result


def _claimed(config: Config, body):
    _ensure_idle(config)
    try:
        with pipeline.claimed_run(config, "api") as run:
            return body(run)
    except RunActiveError as exc:  # another process claimed it in the meantime
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/search")
def run_search(config: Config = Depends(get_config)):
    return _claimed(config, lambda run: _search(config, run))


@router.post("/dedup")
def run_dedup(config: Config = Depends(get_config)):
    return _claimed(config, lambda run: _dedup(config, run))


@router.post("/screen")
def run_screen(config: Config = Depends(get_config)):
    return _screen(config)


@router.post("/run-all")
def run_all(config: Config = Depends(get_config)):
    def steps(run: pipeline.ClaimedRun) -> dict:
        search_result = _search(config, run)
        if "error" in search_result:
            return search_result
        dedup_result = _dedup(config, run)
        if "error" in dedup_result:
            return dedup_result
        screen_result = _screen(config, run)
        if "error" in screen_result:
            return screen_result
        return {"status": "ok", "search": search_result, "dedup": dedup_result,
                "screen": screen_result}

    return _claimed(config, steps)
