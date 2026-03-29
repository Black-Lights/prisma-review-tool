"""Report generation and file export endpoints."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends
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
    stats = download_papers(papers, pdf_dir, email=config.openalex_email)

    return {
        "status": "ok",
        "source": source,
        "total": stats["total"],
        "downloaded": stats["downloaded"],
        "no_open_access": stats["no_open_access"],
        "failed": stats["failed"],
        "output_dir": str(pdf_dir),
    }
