"""Download open access PDFs for eligible papers.

Only downloads papers that are legally available as open access.
Uses Unpaywall API (free, legal) and arXiv direct links.
Paywalled papers are skipped and logged.
"""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Optional

import requests

from .models import Paper


def _sanitize_filename(text: str, max_len: int = 80) -> str:
    """Create a safe filename from text."""
    text = re.sub(r'[<>:"/\\|?*]', '', text)
    text = re.sub(r'\s+', '_', text.strip())
    return text[:max_len]


def _make_pdf_filename(paper: Paper) -> str:
    """Generate a descriptive filename: AuthorYear_ShortTitle.pdf"""
    first_author = "Unknown"
    if paper.authors:
        parts = paper.authors[0].replace(",", " ").split()
        first_author = parts[-1] if parts else "Unknown"

    year = str(paper.year) if paper.year else "XXXX"
    short_title = _sanitize_filename(paper.title[:60])
    return f"{first_author}{year}_{short_title}.pdf"


def _get_arxiv_pdf_url(doi: Optional[str], url: Optional[str]) -> Optional[str]:
    """Extract arXiv PDF URL from DOI or URL."""
    # DOI pattern: 10.48550/arxiv.XXXX.XXXXX
    if doi and "arxiv" in doi.lower():
        arxiv_id = doi.split("arxiv.")[-1] if "arxiv." in doi.lower() else None
        if arxiv_id:
            return f"https://arxiv.org/pdf/{arxiv_id}.pdf"

    # URL pattern
    if url and "arxiv.org" in url:
        # https://arxiv.org/abs/XXXX.XXXXX -> https://arxiv.org/pdf/XXXX.XXXXX.pdf
        arxiv_id = url.rstrip("/").split("/")[-1]
        return f"https://arxiv.org/pdf/{arxiv_id}.pdf"

    return None


def _get_unpaywall_pdf_url(doi: str, email: str) -> Optional[str]:
    """Query Unpaywall API for open access PDF URL.

    Unpaywall is free and legal — it finds legal open access versions of papers.
    See: https://unpaywall.org/products/api
    """
    if not doi or not email:
        return None

    # Skip arxiv DOIs — handled separately
    if "arxiv" in doi.lower():
        return None

    clean_doi = doi.strip()
    for prefix in ["https://doi.org/", "http://doi.org/", "doi:"]:
        if clean_doi.lower().startswith(prefix):
            clean_doi = clean_doi[len(prefix):]

    try:
        resp = requests.get(
            f"https://api.unpaywall.org/v2/{clean_doi}",
            params={"email": email},
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            best = data.get("best_oa_location")
            if best and best.get("url_for_pdf"):
                return best["url_for_pdf"]
            # Try other OA locations
            for loc in data.get("oa_locations", []):
                if loc.get("url_for_pdf"):
                    return loc["url_for_pdf"]
    except (requests.RequestException, ValueError):
        pass

    return None


def _get_semantic_scholar_pdf_url(doi: str) -> Optional[str]:
    """Check Semantic Scholar for open access PDF."""
    if not doi:
        return None

    clean_doi = doi.strip()
    for prefix in ["https://doi.org/", "http://doi.org/", "doi:"]:
        if clean_doi.lower().startswith(prefix):
            clean_doi = clean_doi[len(prefix):]

    try:
        resp = requests.get(
            f"https://api.semanticscholar.org/graph/v1/paper/DOI:{clean_doi}",
            params={"fields": "openAccessPdf"},
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            oa = data.get("openAccessPdf")
            if oa and oa.get("url"):
                return oa["url"]
    except (requests.RequestException, ValueError):
        pass

    return None


def _download_elsevier_pdf(doi: str, api_key: str, path: Path) -> bool:
    """Download a PDF directly from Elsevier/ScienceDirect using the Scopus API key.

    Works for papers the institution subscribes to (requires institutional network
    or VPN). Uses the Elsevier Article Retrieval API with Accept: application/pdf.
    """
    if not doi or not api_key:
        return False

    clean_doi = doi.strip()
    for prefix in ["https://doi.org/", "http://doi.org/", "doi:"]:
        if clean_doi.lower().startswith(prefix):
            clean_doi = clean_doi[len(prefix):]

    try:
        resp = requests.get(
            f"https://api.elsevier.com/content/article/doi/{clean_doi}",
            headers={
                "X-ELS-APIKey": api_key,
                "Accept": "application/pdf",
            },
            timeout=30,
            stream=True,
        )
        if resp.status_code == 200:
            content_type = resp.headers.get("content-type", "")
            if "pdf" in content_type:
                with open(path, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=8192):
                        f.write(chunk)
                # Verify PDF header
                with open(path, "rb") as f:
                    header = f.read(5)
                if header == b"%PDF-":
                    return True
                else:
                    path.unlink(missing_ok=True)
    except requests.RequestException:
        pass
    return False


def _download_pdf(url: str, path: Path) -> bool:
    """Download a PDF from a URL."""
    try:
        resp = requests.get(url, timeout=30, stream=True, headers={
            "User-Agent": "prisma-review-tool/1.0 (https://github.com/Black-Lights/prisma-review-tool)"
        })
        if resp.status_code == 200:
            content_type = resp.headers.get("content-type", "")
            # Verify it's actually a PDF
            if "pdf" in content_type or url.endswith(".pdf"):
                with open(path, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=8192):
                        f.write(chunk)
                # Verify file starts with PDF header
                with open(path, "rb") as f:
                    header = f.read(5)
                if header == b"%PDF-":
                    return True
                else:
                    path.unlink(missing_ok=True)
    except requests.RequestException:
        pass
    return False


def download_papers(
    papers: list[Paper],
    output_dir: Path,
    email: str = "",
    api_key: str = "",
    delay: float = 1.0,
) -> dict:
    """Download PDFs for a list of papers.

    Tries multiple strategies in order:
    0. Elsevier/ScienceDirect (if api_key provided — institutional access)
    1. arXiv (always free)
    2. Unpaywall (free OA finder)
    3. Semantic Scholar (free OA)

    Args:
        papers: List of Paper objects to download
        output_dir: Directory to save PDFs
        email: Email for Unpaywall API (required for non-arXiv papers)
        api_key: Elsevier/Scopus API key (for institutional full-text access)
        delay: Seconds between API calls (be polite to servers)

    Returns:
        Dict with download statistics and per-paper results
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    results = []
    downloaded = 0
    skipped = 0
    failed = 0

    for i, paper in enumerate(papers):
        filename = _make_pdf_filename(paper)
        filepath = output_dir / filename
        status = "skipped"
        pdf_url = None

        # Skip if already downloaded
        if filepath.exists():
            results.append({"id": paper.id, "title": paper.title, "file": filename, "status": "exists"})
            downloaded += 1
            continue

        # Strategy 0: Elsevier/ScienceDirect (institutional access via API key)
        if api_key and paper.doi:
            if _download_elsevier_pdf(paper.doi, api_key, filepath):
                status = "downloaded"
                downloaded += 1
                results.append({
                    "id": paper.id,
                    "title": paper.title[:80],
                    "file": filename,
                    "status": status,
                    "doi": paper.doi,
                })
                time.sleep(delay)
                if (i + 1) % 10 == 0:
                    print(f"  [{i + 1}/{len(papers)}] Downloaded: {downloaded}, No OA: {skipped}, Failed: {failed}")
                continue
            time.sleep(delay)

        # Strategy 1: arXiv (always free)
        pdf_url = _get_arxiv_pdf_url(paper.doi, paper.url)

        # Strategy 2: Unpaywall (free OA finder)
        if not pdf_url and email:
            pdf_url = _get_unpaywall_pdf_url(paper.doi, email)
            time.sleep(delay)

        # Strategy 3: Semantic Scholar
        if not pdf_url:
            pdf_url = _get_semantic_scholar_pdf_url(paper.doi)
            time.sleep(delay)

        # Download if URL found
        if pdf_url:
            if _download_pdf(pdf_url, filepath):
                status = "downloaded"
                downloaded += 1
            else:
                status = "failed"
                failed += 1
        else:
            status = "no_oa"
            skipped += 1

        results.append({
            "id": paper.id,
            "title": paper.title[:80],
            "file": filename if status == "downloaded" else None,
            "status": status,
            "doi": paper.doi,
        })

        if (i + 1) % 10 == 0:
            print(f"  [{i + 1}/{len(papers)}] Downloaded: {downloaded}, No OA: {skipped}, Failed: {failed}")

    return {
        "total": len(papers),
        "downloaded": downloaded,
        "no_open_access": skipped,
        "failed": failed,
        "output_dir": str(output_dir),
        "results": results,
    }
