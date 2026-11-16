"""Report generation and file export endpoints."""

from __future__ import annotations

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
from prisma_review.stats import load_papers_cached, project_stats
from prisma_review.storage import atomic_write_json, read_json

from api.deps import get_config

router = APIRouter(tags=["reports"])


@router.post("/reports/generate")
def generate_report(config: Config = Depends(get_config)):
    state = load_state(config.state_file)
    if not state:
        return {"error": "No pipeline state. Run the pipeline first."}

    flow = project_stats(config, state)["flow"]
    generate_markdown_diagram(flow, config.export_dir / "prisma_flow.md")
    generate_png_diagram(flow, config.export_dir / "prisma_flow.png")

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
        "flow": flow,
    }


def _search_log(config: Config) -> dict | None:
    """01_search/search_log.json of the active project: the search the results come from."""
    log = read_json(config.search_dir / "search_log.json", default=None)
    return log if isinstance(log, dict) else None


@router.get("/reports/search-log")
def search_log(config: Config = Depends(get_config)):
    """The search exactly as it ran (PRISMA 2020 item 7): 01_search/search_log.json.

    404 when no search has completed yet (the log is written at the end of a search).
    """
    log = _search_log(config)
    if log is None:
        raise HTTPException(status_code=404,
                            detail="No search log yet: it is written when a search completes.")
    return log


def _query_list(items) -> list[dict]:
    return [{"name": q.get("name") or "unnamed", "terms": str(q.get("terms", "") or "").strip()}
            for q in items or [] if isinstance(q, dict)]


@router.get("/reports/by-query")
def report_by_query(config: Config = Depends(get_config)):
    """Attribute results to each query of the search that produced them.

    The queries (names and terms) come from 01_search/search_log.json when it
    exists (``queries_from``: "search_log"), so the report describes the search
    that was run even after the settings changed; otherwise from the current
    settings ("settings"). Counts are *with overlap*: queries are OR'd, so a
    paper returned by more than one query is counted under each, and the
    per-query sums therefore exceed the distinct totals. ``found_raw`` is
    pre-dedup; the rest are on the deduplicated/screened set. ``untagged`` are
    papers with no recorded query (e.g. searched before per-query provenance
    was tracked). ``notes`` explains rows that are merged or missing."""
    configured = _query_list(getattr(config, "queries", []) or [])
    log = _search_log(config)
    logged = _query_list(log.get("queries")) if log is not None else []
    queries = logged if logged else configured
    queries_from = "search_log" if logged else "settings"

    raw = load_papers_cached(config.search_dir / "all_records.json")
    screened = load_papers_cached(config.screen_dir / "screen_results.json")
    if not screened:
        screened = load_papers_cached(config.dedup_dir / "deduplicated.json")

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

    notes = []
    names = [q["name"] for q in queries]
    for name in sorted({n for n in names if names.count(n) > 1}):
        notes.append(f"The name '{name}' is used by more than one query, so their results are "
                     f"merged into one row. Give each query a unique name.")
    current = [(q["name"], q["terms"]) for q in configured if q["terms"]]
    if logged and current != [(q["name"], q["terms"]) for q in logged]:
        notes.append("The queries in the settings changed after this search ran. The rows show "
                     "the queries of the search that produced these results (search log); run "
                     "the search again to report the new ones.")
    unnamed = sum(1 for q in queries if q["name"] == "unnamed")
    if unnamed:
        notes.append(f"{unnamed} quer{'y' if unnamed == 1 else 'ies'} without a name "
                     f"{'is' if unnamed == 1 else 'are'} reported as 'unnamed'.")
    if untagged_raw:
        one = untagged_raw == 1
        notes.append(f"{untagged_raw} record{'' if one else 's'} in the search results "
                     f"{'has' if one else 'have'} no query recorded, so "
                     f"{'it was' if one else 'they were'} found before per-query tracking was "
                     f"added. Re-run the search to attribute {'it' if one else 'them'}.")

    terms_by_name = {q["name"]: q["terms"] for q in queries}
    return {
        "queries_from": queries_from,
        "queries": [{"name": name, "terms": terms_by_name.get(name, ""), **counts}
                    for name, counts in rows.items()],
        "total_after_dedup": len(screened),
        "total_included": sum(1 for p in screened if (p.screen_decision or "").lower() == "include"),
        "untagged": {"raw": untagged_raw, "screened": untagged_screened},
        "notes": notes,
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

    entries = read_json(log_path, default=[])
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
    atomic_write_json(log_path, results, indent=2)

    return {
        "status": "ok",
        "source": source,
        "total": stats["total"],
        "downloaded": stats["downloaded"],
        "no_open_access": stats["no_open_access"],
        "failed": stats["failed"],
        "output_dir": str(pdf_dir),
    }
