"""Paper endpoints — screening, eligibility, search, details, export."""

from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse

from prisma_review.models import Paper, load_papers, save_papers
from prisma_review.screen import get_by_decision
from prisma_review.config import Config
from prisma_review.diagram import load_state, save_state
from prisma_review.export import export_csv, export_bibtex, ALL_CSV_FIELDS

from api.deps import get_config, get_file_lock
from api.schemas import ScreenDecision, BatchScreenItem

router = APIRouter(tags=["papers"])


# ── Shared helpers ──────────────────────────────────────────────────────────

def _load_filtered_papers(
    config: Config,
    decision: str = "all",
    source: str = "all",
) -> list[Paper]:
    """Load papers from the pipeline state, filtered by decision and source."""
    papers = load_papers(config.screen_dir / "screen_results.json")
    if not papers:
        papers = load_papers(config.dedup_dir / "deduplicated.json")

    if decision == "eligible_included":
        elig_papers = load_papers(config.eligibility_dir / "eligible_included.json")
        elig_ids = {p.id for p in elig_papers}
        papers = [p for p in papers if p.id in elig_ids]
    elif decision == "eligible_excluded":
        elig_papers = load_papers(config.eligibility_dir / "eligible_excluded.json")
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
    state = load_state(config.state_file)
    if not state:
        return {"error": "No pipeline state found. Run the pipeline first."}
    return {
        "project": config.project_name,
        "search": state.get("search", {}),
        "dedup": state.get("dedup", {}),
        "screen": state.get("screen", {}),
        "eligibility": state.get("eligibility", {}),
    }


# ── Browse all papers (paginated) ─────────────────────────────────────────────

@router.get("/papers")
def list_all_papers(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    decision: str = Query("all"),
    source: str = Query("all"),
    config: Config = Depends(get_config),
):
    papers = _load_filtered_papers(config, decision, source)
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
    """Export filtered papers as CSV or BibTeX on demand."""
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
    filename = "_".join(parts) + f".{fmt}"

    # Write to temp file
    tmp = Path(tempfile.mktemp(suffix=f".{fmt}"))
    if fmt == "csv":
        field_list = [f.strip() for f in fields.split(",") if f.strip()] if fields else None
        # Validate fields
        if field_list:
            field_list = [f for f in field_list if f in ALL_CSV_FIELDS]
        export_csv(papers, tmp, fields=field_list or None)
        media = "text/csv"
    else:
        export_bibtex(papers, tmp)
        media = "application/x-bibtex"

    return FileResponse(tmp, media_type=media, filename=filename)


# ── First-pass screening ─────────────────────────────────────────────────────

@router.get("/papers/screen")
def get_papers_to_screen(
    batch_size: int = Query(20, ge=1, le=200),
    filter_type: str = Query("maybe", pattern="^(maybe|unscreened|all)$"),
    config: Config = Depends(get_config),
):
    if filter_type == "maybe":
        papers = load_papers(config.screen_dir / "maybe.json")
    elif filter_type == "unscreened":
        papers = load_papers(config.dedup_dir / "deduplicated.json")
        papers = [p for p in papers if p.screen_decision is None]
    else:
        papers = load_papers(config.screen_dir / "screen_results.json")

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
    lock=Depends(get_file_lock),
):
    with lock:
        all_papers = load_papers(config.screen_dir / "screen_results.json")

        found = False
        for p in all_papers:
            if p.id == paper_id:
                p.screen_decision = body.decision
                p.screen_reason = body.reason
                p.screen_method = "manual"
                found = True
                break

        if not found:
            return {"error": f"Paper '{paper_id}' not found."}

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

    return {
        "status": "ok",
        "paper_id": paper_id,
        "decision": body.decision,
        "remaining_maybe": len(maybe),
    }


@router.post("/papers/screen/batch")
def batch_screen(
    items: list[BatchScreenItem],
    config: Config = Depends(get_config),
    lock=Depends(get_file_lock),
):
    with lock:
        all_papers = load_papers(config.screen_dir / "screen_results.json")
        paper_map = {p.id: p for p in all_papers}

        results = []
        for item in items:
            if item.paper_id not in paper_map:
                results.append({"paper_id": item.paper_id, "status": "error", "message": "not found"})
                continue
            paper_map[item.paper_id].screen_decision = item.decision
            paper_map[item.paper_id].screen_reason = item.reason
            paper_map[item.paper_id].screen_method = "manual"
            results.append({"paper_id": item.paper_id, "status": "ok", "decision": item.decision})

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

    return {"processed": len(results), "remaining_maybe": len(maybe), "results": results}


# ── Eligibility (second pass) ────────────────────────────────────────────────

@router.get("/papers/eligibility")
def get_papers_for_eligibility(
    batch_size: int = Query(20, ge=1, le=200),
    config: Config = Depends(get_config),
):
    papers = load_papers(config.screen_dir / "included.json")
    elig_results = load_papers(config.eligibility_dir / "eligibility_results.json")
    screened_ids = {p.id for p in elig_results if p.eligibility_decision is not None}

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
    lock=Depends(get_file_lock),
):
    with lock:
        all_papers = load_papers(config.screen_dir / "included.json")
        elig_path = config.eligibility_dir / "eligibility_results.json"
        elig_results = load_papers(elig_path)
        elig_map = {p.id: p for p in elig_results}

        found = False
        for p in all_papers:
            if p.id == paper_id:
                p.eligibility_decision = body.decision
                p.eligibility_reason = body.reason
                p.eligibility_method = "manual"
                elig_map[p.id] = p
                found = True
                break

        if not found:
            return {"error": f"Paper '{paper_id}' not found."}

        all_elig = list(elig_map.values())
        save_papers(all_elig, elig_path)
        elig_included = [p for p in all_elig if p.eligibility_decision == "include"]
        elig_excluded = [p for p in all_elig if p.eligibility_decision == "exclude"]
        save_papers(elig_included, config.eligibility_dir / "eligible_included.json")
        save_papers(elig_excluded, config.eligibility_dir / "eligible_excluded.json")

        state = load_state(config.state_file)
        state["eligibility"] = {
            "input_from_screening": len(all_papers),
            "screened": len(all_elig),
            "included": len(elig_included),
            "excluded": len(elig_excluded),
            "remaining": len(all_papers) - len(all_elig),
        }
        save_state(state, config.state_file)

    return {"status": "ok", "paper_id": paper_id, "decision": body.decision, "remaining": len(all_papers) - len(all_elig)}


@router.post("/papers/eligibility/batch")
def batch_eligibility(
    items: list[BatchScreenItem],
    config: Config = Depends(get_config),
    lock=Depends(get_file_lock),
):
    with lock:
        all_papers = load_papers(config.screen_dir / "included.json")
        paper_map = {p.id: p for p in all_papers}
        elig_path = config.eligibility_dir / "eligibility_results.json"
        elig_results = load_papers(elig_path)
        elig_map = {p.id: p for p in elig_results}

        results = []
        for item in items:
            if item.paper_id not in paper_map:
                results.append({"paper_id": item.paper_id, "status": "error", "message": "not found"})
                continue
            paper_map[item.paper_id].eligibility_decision = item.decision
            paper_map[item.paper_id].eligibility_reason = item.reason
            paper_map[item.paper_id].eligibility_method = "manual"
            elig_map[item.paper_id] = paper_map[item.paper_id]
            results.append({"paper_id": item.paper_id, "status": "ok", "decision": item.decision})

        all_elig = list(elig_map.values())
        save_papers(all_elig, elig_path)
        elig_included = [p for p in all_elig if p.eligibility_decision == "include"]
        elig_excluded = [p for p in all_elig if p.eligibility_decision == "exclude"]
        save_papers(elig_included, config.eligibility_dir / "eligible_included.json")
        save_papers(elig_excluded, config.eligibility_dir / "eligible_excluded.json")

        state = load_state(config.state_file)
        state["eligibility"] = {
            "input_from_screening": len(all_papers),
            "screened": len(all_elig),
            "included": len(elig_included),
            "excluded": len(elig_excluded),
            "remaining": len(all_papers) - len(all_elig),
        }
        save_state(state, config.state_file)

    return {"processed": len(results), "remaining": len(all_papers) - len(all_elig), "results": results}


# ── Paper details & search ───────────────────────────────────────────────────

@router.get("/papers/search")
def search_papers(
    q: str = Query(..., min_length=1),
    config: Config = Depends(get_config),
):
    papers = load_papers(config.screen_dir / "screen_results.json")
    if not papers:
        papers = load_papers(config.dedup_dir / "deduplicated.json")

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
        papers = load_papers(config.screen_dir / fname)
        for p in papers:
            if p.id == paper_id:
                return p.to_dict()

    papers = load_papers(config.dedup_dir / "deduplicated.json")
    for p in papers:
        if p.id == paper_id:
            return p.to_dict()

    return {"error": f"Paper '{paper_id}' not found."}
