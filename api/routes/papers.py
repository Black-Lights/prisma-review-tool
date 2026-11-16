"""Paper endpoints: screening, eligibility, search, details, export."""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from prisma_review.models import Paper
from prisma_review.pipeline import RunActiveError, StepError
from prisma_review.screen import apply_eligibility_decisions, apply_screen_decisions, rescreen
from prisma_review.stats import load_papers_cached, project_stats
from prisma_review.config import Config, config_version
from prisma_review.diagram import load_state
from prisma_review.export import ALL_CSV_FIELDS, bibtex_text, csv_text

from api.deps import get_config
from api.schemas import ScreenDecision, BatchScreenItem

router = APIRouter(tags=["papers"])


# ── Shared helpers ──────────────────────────────────────────────────────────

def _load_filtered_papers(
    config: Config,
    decision: str = "all",
    source: str = "all",
) -> list[Paper]:
    """Load papers from the pipeline state, filtered by decision and source (read-only)."""
    papers = load_papers_cached(config.screen_dir / "screen_results.json")
    if not papers:
        papers = load_papers_cached(config.dedup_dir / "deduplicated.json")

    if decision == "eligible_included":
        elig_papers = load_papers_cached(config.eligibility_dir / "eligible_included.json")
        elig_ids = {p.id for p in elig_papers}
        papers = [p for p in papers if p.id in elig_ids]
    elif decision == "eligible_excluded":
        elig_papers = load_papers_cached(config.eligibility_dir / "eligible_excluded.json")
        elig_ids = {p.id for p in elig_papers}
        papers = [p for p in papers if p.id in elig_ids]
    elif decision != "all":
        papers = [p for p in papers if (p.screen_decision or "").lower() == decision.lower()]

    if source != "all":
        papers = [p for p in papers if p.source.lower() == source.lower()]

    return papers


# ── Stats ────────────────────────────────────────────────────────────────────

@router.get("/stats")
def get_stats(config: Config = Depends(get_config)):
    """Counts per stage, the screen breakdown by method, and the PRISMA 2020 ``flow``.

    The screen and eligibility numbers are computed from the result files,
    so they stay right whichever process (web app, MCP server, CLI) wrote them.
    """
    state = load_state(config.state_file)
    if not state:
        return {"error": "No pipeline state found. Run the pipeline first."}
    computed = project_stats(config, state)
    return {
        "project": config.project_name,
        "search": state.get("search", {}),
        "dedup": state.get("dedup", {}),
        "screen": computed["screen"],
        "eligibility": computed["eligibility"],
        "flow": computed["flow"],
    }


# ── Browse all papers (paginated) ─────────────────────────────────────────────

_SORT_KEYS = {
    "title": lambda p: (p.title or "").lower(),
    "authors": lambda p: (p.authors[0].lower() if p.authors else ""),
    "year": lambda p: p.year or 0,
    "source": lambda p: (p.source or "").lower(),
    "decision": lambda p: (p.screen_decision or "").lower(),
}


@router.get("/papers")
def list_all_papers(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=1000),
    decision: str = Query("all"),
    source: str = Query("all"),
    sort: str = Query("", pattern="^(|title|authors|year|source|decision)$"),
    order: str = Query("asc", pattern="^(asc|desc)$"),
    config: Config = Depends(get_config),
):
    papers = _load_filtered_papers(config, decision, source)

    if sort:
        papers = sorted(papers, key=_SORT_KEYS[sort], reverse=(order == "desc"))

    total = len(papers)
    start = (page - 1) * per_page
    end = start + per_page
    page_papers = papers[start:end]

    return {
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": (total + per_page - 1) // per_page,
        "papers": [
            {
                "id": p.id,
                "title": p.title,
                "authors": "; ".join(p.authors[:3]) + ("..." if len(p.authors) > 3 else ""),
                "year": p.year,
                "source": p.source,
                "venue": p.venue or "",
                "doi": p.doi or "",
                "decision": p.screen_decision,
                "eligibility": p.eligibility_decision,
            }
            for p in page_papers
        ],
    }


# ── Export (on-demand, filtered) ─────────────────────────────────────────────

@router.get("/papers/export/{fmt}")
def export_papers(
    fmt: str,
    decision: str = Query("all"),
    source: str = Query("all"),
    fields: str = Query(""),
    config: Config = Depends(get_config),
):
    """Export filtered papers as CSV or BibTeX on demand (built in memory, no temp file)."""
    if fmt not in ("csv", "bib"):
        return {"error": "Format must be 'csv' or 'bib'"}

    papers = _load_filtered_papers(config, decision, source)
    if not papers:
        return {"error": "No papers match the current filters."}

    # Build filename
    parts = ["papers"]
    if decision != "all":
        parts.append(decision)
    if source != "all":
        parts.append(source)
    filename = re.sub(r"[^\w.-]", "_", "_".join(parts)) + f".{fmt}"

    if fmt == "csv":
        field_list = [f.strip() for f in fields.split(",") if f.strip()] if fields else None
        # Validate fields
        if field_list:
            field_list = [f for f in field_list if f in ALL_CSV_FIELDS]
        text = csv_text(papers, fields=field_list or None)
        media = "text/csv; charset=utf-8"
    else:
        text = bibtex_text(papers)
        media = "application/x-bibtex; charset=utf-8"

    return Response(content=text.encode("utf-8"), media_type=media,
                     headers={"Content-Disposition": f'attachment; filename="{filename}"'})


# ── Re-screen (keyword screening with different threshold) ───────────────────

@router.post("/papers/rescreen")
def rescreen_papers(
    min_include_hits: int = Query(2, ge=1, le=10),
    config: Config = Depends(get_config),
):
    """Re-run keyword screening on existing deduplicated papers with a new threshold.

    Does NOT re-search or re-deduplicate: only re-applies screening rules.
    Keeps manual and AI decisions and every eligibility decision (set aside
    while its paper is not included), and saves the threshold in config.yaml (the response
    has the new ``config_version``). 409 while a pipeline runs on the project.
    """
    try:
        result = rescreen(config, min_include_hits)
    except RunActiveError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except StepError as exc:
        return {"error": str(exc)}
    if config.config_path is not None:
        result["config_version"] = config_version(config.config_path)
    return result


# ── First-pass screening ─────────────────────────────────────────────────────

@router.get("/papers/screen")
def get_papers_to_screen(
    batch_size: int = Query(20, ge=1, le=200),
    filter_type: str = Query("maybe", pattern="^(maybe|unscreened|all)$"),
    config: Config = Depends(get_config),
):
    if filter_type == "maybe":
        papers = load_papers_cached(config.screen_dir / "maybe.json")
    elif filter_type == "unscreened":
        papers = load_papers_cached(config.dedup_dir / "deduplicated.json")
        papers = [p for p in papers if p.screen_decision is None]
    else:
        papers = load_papers_cached(config.screen_dir / "screen_results.json")

    batch = papers[:batch_size]
    return {
        "total_matching": len(papers),
        "returned": len(batch),
        "papers": [
            {
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
            }
            for p in batch
        ],
    }


@router.post("/papers/{paper_id}/screen")
def screen_paper(
    paper_id: str,
    body: ScreenDecision,
    config: Config = Depends(get_config),
):
    results, summary = apply_screen_decisions(
        config, [{"paper_id": paper_id, "decision": body.decision, "reason": body.reason}], "manual")
    if results[0]["status"] != "ok":
        return {"error": f"Paper '{paper_id}' not found."}

    return {
        "status": "ok",
        "paper_id": paper_id,
        "decision": body.decision,
        "remaining_maybe": summary["maybe"],
    }


@router.post("/papers/screen/batch")
def batch_screen(
    items: list[BatchScreenItem],
    config: Config = Depends(get_config),
):
    results, summary = apply_screen_decisions(config, [item.model_dump() for item in items], "manual")
    return {"processed": len(results), "remaining_maybe": summary["maybe"], "results": results}


# ── Eligibility (second pass) ────────────────────────────────────────────────

@router.get("/papers/eligibility")
def get_papers_for_eligibility(
    batch_size: int = Query(20, ge=1, le=200),
    config: Config = Depends(get_config),
):
    papers = load_papers_cached(config.screen_dir / "included.json")
    elig_results = load_papers_cached(config.eligibility_dir / "eligibility_results.json")
    included_ids = {p.id for p in papers}
    screened_ids = {p.id for p in elig_results
                    if p.eligibility_decision is not None and p.id in included_ids}

    unscreened = [p for p in papers if p.id not in screened_ids]
    batch = unscreened[:batch_size]

    return {
        "total_first_pass_included": len(papers),
        "already_screened": len(screened_ids),
        "remaining": len(unscreened),
        "returned": len(batch),
        "papers": [
            {
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
            }
            for p in batch
        ],
    }


@router.post("/papers/{paper_id}/eligibility")
def eligibility_screen(
    paper_id: str,
    body: ScreenDecision,
    config: Config = Depends(get_config),
):
    results, summary = apply_eligibility_decisions(
        config, [{"paper_id": paper_id, "decision": body.decision, "reason": body.reason}], "manual")
    if results[0]["status"] != "ok":
        return {"error": f"Paper '{paper_id}' not found."}
    return {"status": "ok", "paper_id": paper_id, "decision": body.decision,
            "remaining": summary["remaining"]}


@router.post("/papers/eligibility/batch")
def batch_eligibility(
    items: list[BatchScreenItem],
    config: Config = Depends(get_config),
):
    results, summary = apply_eligibility_decisions(
        config, [item.model_dump() for item in items], "manual")
    return {"processed": len(results), "remaining": summary["remaining"], "results": results}


# ── Paper details & search ───────────────────────────────────────────────────

@router.get("/papers/search")
def search_papers(
    q: str = Query(..., min_length=1),
    config: Config = Depends(get_config),
):
    papers = load_papers_cached(config.screen_dir / "screen_results.json")
    if not papers:
        papers = load_papers_cached(config.dedup_dir / "deduplicated.json")

    query_lower = q.lower()
    matches = [
        {
            "id": p.id,
            "title": p.title,
            "year": p.year,
            "source": p.source,
            "decision": p.screen_decision,
            "eligibility": p.eligibility_decision,
        }
        for p in papers
        if query_lower in (p.title + " " + p.abstract).lower()
    ]
    return {"query": q, "matches": len(matches), "papers": matches[:50]}


@router.get("/papers/{paper_id}")
def get_paper(paper_id: str, config: Config = Depends(get_config)):
    for fname in ["screen_results.json", "included.json", "excluded.json", "maybe.json"]:
        papers = load_papers_cached(config.screen_dir / fname)
        for p in papers:
            if p.id == paper_id:
                return p.to_dict()

    papers = load_papers_cached(config.dedup_dir / "deduplicated.json")
    for p in papers:
        if p.id == paper_id:
            return p.to_dict()

    return {"error": f"Paper '{paper_id}' not found."}
