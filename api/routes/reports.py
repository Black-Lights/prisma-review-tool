"""Report generation and file export endpoints."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from prisma_review.config import Config
from prisma_review.models import load_papers
from prisma_review.export import export_bibtex, export_csv
from prisma_review.download import download_papers
from prisma_review.diagram import (
    generate_markdown_diagram, generate_png_diagram,
    load_state,
)

from api.deps import get_config

router = APIRouter(tags=["reports"])


@router.post("/reports/generate")
def generate_report(config: Config = Depends(get_config)):
    state = load_state(config.state_file)
    if not state:
        return {"error": "No pipeline state. Run the pipeline first."}

    generate_markdown_diagram(state, config.export_dir / "prisma_flow.md")
    generate_png_diagram(state, config.export_dir / "prisma_flow.png")

    included = load_papers(config.screen_dir / "included.json")
    if included:
        export_bibtex(included, config.export_dir / "included_papers.bib")
        export_csv(included, config.export_dir / "included_papers.csv")

    eligible = load_papers(config.eligibility_dir / "eligible_included.json")
    if eligible:
        export_bibtex(eligible, config.export_dir / "eligible_papers.bib")
        export_csv(eligible, config.export_dir / "eligible_papers.csv")

    return {
        "status": "ok",
        "included_papers": len(included),
        "eligible_papers": len(eligible),
    }


@router.get("/reports/by-query")
def report_by_query(config: Config = Depends(get_config)):
    """Attribute results to each configured query.

    Counts are *with overlap*: queries are OR'd, so a paper returned by more
    than one query is counted under each — the per-query sums therefore exceed
    the distinct totals. ``found_raw`` is pre-dedup; the rest are on the
    deduplicated/screened set. ``untagged`` are papers with no recorded query
    (e.g. searched before per-query provenance was tracked)."""
    queries = [
        {"name": q.get("name", "unnamed"), "terms": (q.get("terms", "") or "").strip()}
        for q in getattr(config, "queries", []) or []
    ]

    raw = load_papers(config.search_dir / "all_records.json")
    screened = load_papers(config.screen_dir / "screen_results.json")
    if not screened:
        screened = load_papers(config.dedup_dir / "deduplicated.json")

    def blank():
        return {"found_raw": 0, "after_dedup": 0, "included": 0, "maybe": 0, "excluded": 0}

    rows: dict[str, dict] = {q["name"]: blank() for q in queries}
    untagged_raw = 0
    for p in raw:
        mq = getattr(p, "matched_queries", None) or []
        if not mq:
            untagged_raw += 1
        for q in mq:
            rows.setdefault(q, blank())["found_raw"] += 1

    untagged_screened = 0
    for p in screened:
        mq = getattr(p, "matched_queries", None) or []
        dec = (p.screen_decision or "").lower()
        if not mq:
            untagged_screened += 1
        for q in mq:
            r = rows.setdefault(q, blank())
            r["after_dedup"] += 1
            if dec == "include":
                r["included"] += 1
            elif dec == "maybe":
                r["maybe"] += 1
            elif dec == "exclude":
                r["excluded"] += 1

    terms_by_name = {q["name"]: q["terms"] for q in queries}
    return {
        "queries": [{"name": name, "terms": terms_by_name.get(name, ""), **counts}
                    for name, counts in rows.items()],
        "total_after_dedup": len(screened),
        "total_included": sum(1 for p in screened if (p.screen_decision or "").lower() == "include"),
        "untagged": {"raw": untagged_raw, "screened": untagged_screened},
    }


@router.get("/reports/filter-plan")
def report_filter_plan(config: Config = Depends(get_config)):
    """How each active source filter is applied per source (request/post/ignored)."""
    from prisma_review.search.filters import filter_plan
    return filter_plan(config)


@router.get("/reports/prisma-flow")
def get_prisma_flow(config: Config = Depends(get_config)):
    png_path = config.export_dir / "prisma_flow.png"
    if not png_path.exists():
        return {"error": "PRISMA diagram not generated yet. Run /api/reports/generate first."}
    return FileResponse(png_path, media_type="image/png", filename="prisma_flow.png")


@router.get("/reports/export/{format}")
def export_file(format: str, source: str = "eligible", config: Config = Depends(get_config)):
    if format not in ("bib", "csv"):
        return {"error": "Format must be 'bib' or 'csv'"}

    prefix = "eligible_papers" if source == "eligible" else "included_papers"
    file_path = config.export_dir / f"{prefix}.{format}"

    if not file_path.exists():
        return {"error": f"File not found. Run /api/reports/generate first."}

    media = "application/x-bibtex" if format == "bib" else "text/csv"
    return FileResponse(file_path, media_type=media, filename=file_path.name)


@router.get("/papers/downloads")
def list_downloads(config: Config = Depends(get_config)):
    """List all downloaded PDFs from the download log."""
    pdf_dir = config.output_dir / "05_pdfs"
    log_path = pdf_dir / "_download_log.json"

    if not log_path.exists():
        return {"total": 0, "papers": []}

    entries = json.loads(log_path.read_text())
    return {
        "total": len(entries),
        "downloaded": sum(1 for e in entries if e.get("status") in ("downloaded", "exists")),
        "no_oa": sum(1 for e in entries if e.get("status") == "no_oa"),
        "failed": sum(1 for e in entries if e.get("status") == "failed"),
        "papers": entries,
    }


@router.get("/papers/downloads/{filename}")
def serve_pdf(filename: str, config: Config = Depends(get_config)):
    """Serve a downloaded PDF file."""
    # Sanitize filename to prevent path traversal
    safe_name = Path(filename).name
    pdf_path = config.output_dir / "05_pdfs" / safe_name

    if not pdf_path.exists() or not safe_name.endswith(".pdf"):
        raise HTTPException(status_code=404, detail="PDF not found")

    from starlette.responses import Response
    content = pdf_path.read_bytes()
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": "inline"},
    )


@router.post("/papers/download")
def download_pdfs(config: Config = Depends(get_config)):
    papers = load_papers(config.eligibility_dir / "eligible_included.json")
    source = "eligible"
    if not papers:
        papers = load_papers(config.screen_dir / "included.json")
        source = "included"

    if not papers:
        return {"error": "No papers found. Run screening first."}

    pdf_dir = config.output_dir / "05_pdfs"
    stats = download_papers(papers, pdf_dir, email=config.openalex_email, api_key=config.scopus_key)

    # Enrich results with DOI (download_papers doesn't include it)
    paper_map = {p.id: p for p in papers}
    results = stats.get("results", [])
    for entry in results:
        p = paper_map.get(entry.get("id"))
        if p:
            entry["doi"] = p.doi or ""

    # Save download log so the Downloads page can list papers
    log_path = pdf_dir / "_download_log.json"
    log_path.write_text(json.dumps(results, indent=2))

    return {
        "status": "ok",
        "source": source,
        "total": stats["total"],
        "downloaded": stats["downloaded"],
        "no_open_access": stats["no_open_access"],
        "failed": stats["failed"],
        "output_dir": str(pdf_dir),
    }
