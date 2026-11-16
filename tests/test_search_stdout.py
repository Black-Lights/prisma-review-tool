"""stdout is the MCP JSON-RPC channel: searching and downloading must never write to it (SEARCH#17).

Runs in a fresh interpreter so the server module import itself is covered,
and checks the real file descriptor, not just sys.stdout. Every HTTP call is
answered offline by replacing ``requests.Session.request``.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

from conftest import REPO_ROOT

SCRIPT = r'''
import json, sys
from pathlib import Path

import requests
from requests.models import Response

TMP = Path(sys.argv[1])
ATOM = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/"
      xmlns:arxiv="http://arxiv.org/schemas/atom">
  <opensearch:totalResults>1</opensearch:totalResults>
  <entry>
    <id>http://arxiv.org/abs/2401.00001v1</id>
    <updated>2024-01-02T00:00:00Z</updated><published>2024-01-01T00:00:00Z</published>
    <title>An arXiv paper on crop yield</title><summary>Abstract text.</summary>
    <author><name>Ada Lovelace</name></author><category term="cs.LG"/>
  </entry>
</feed>"""


def body_for(url):
    if "api.openalex.org" in url:
        return {"meta": {"count": 1, "next_cursor": None}, "results": [
            {"id": "https://openalex.org/W1", "title": "An OpenAlex paper", "publication_year": 2023,
             "doi": "https://doi.org/10.1000/oa1", "abstract_inverted_index": {"Text": [0]}}]}
    if "api.crossref.org" in url:
        return {"message": {"total-results": 1, "next-cursor": None, "items": [
            {"title": ["A Crossref paper"], "DOI": "10.2000/cr1", "issued": {"date-parts": [[2023]]}}]}}
    if "/paper/search/bulk" in url:
        return {"total": 1, "data": [{"paperId": "p1", "title": "An S2 paper", "year": 2023,
                                      "externalIds": {"DOI": "10.3000/s21"}}]}
    if "api.semanticscholar.org" in url:  # OA lookup during download
        return {"openAccessPdf": {"url": "https://files.example.org/paper.pdf"}}
    if "api.elsevier.com" in url:
        return {"search-results": {"opensearch:totalResults": "1", "entry": [
            {"dc:title": "A Scopus paper", "prism:coverDate": "2023-01-01", "eid": "2-s2.0-1"}]}}
    raise AssertionError("unexpected URL " + url)


def fake_request(self, method, url, params=None, headers=None, **kwargs):
    full = requests.Request(method, url, params=params).prepare().url
    r = Response()
    r.status_code, r.url, r._content_consumed = 200, full, True
    if "export.arxiv.org" in full:
        r._content = ATOM
        r.headers["Content-Type"] = "application/atom+xml"
    elif full.endswith(".pdf"):
        r._content = b"%PDF-1.4 offline"
        r.headers["Content-Type"] = "application/pdf"
    else:
        r._content = json.dumps(body_for(full)).encode()
        r.headers["Content-Type"] = "application/json"
    return r


requests.Session.request = fake_request

import mcp_server.server  # noqa: F401  (the stdio server module, imported first like run_mcp.py)
from prisma_review.config import Config
from prisma_review.download import download_papers
from prisma_review.search.runner import run_all_searches

cfg = Config({
    "project": {"name": "Stdout check", "output_dir": str(TMP / "out")},
    "api_keys": {"scopus": "FAKE-SCOPUS", "openalex_key": "FAKE-OA", "openalex_email": ""},
    "search": {"date_range": {"start": "2020-01-01", "end": "2026-12-31"},
               "max_results_per_query": 5,
               "sources": ["arxiv", "crossref", "openalex", "semantic_scholar", "scopus"],
               "queries": [{"name": "main", "terms": '"crop yield" AND predict*'}]},
}, base_dir=TMP)
log = []
results = run_all_searches(cfg, status_log=log)
papers = [p for ps in results.values() for p in ps]
stats = download_papers(papers, TMP / "pdfs", email="", api_key="", delay=0)
sys.stderr.write("\nRESULT " + json.dumps({"statuses": [e["status"] for e in log],
                                            "papers": len(papers),
                                            "downloaded": stats["downloaded"]}) + "\n")
'''


def test_search_and_download_write_nothing_to_stdout(tmp_path):
    script = tmp_path / "run_search.py"
    script.write_text(SCRIPT, encoding="utf-8")
    workspace = tmp_path / "ws"
    workspace.mkdir()
    env = {**os.environ, "PYTHONPATH": str(REPO_ROOT), "PRISMA_WORKSPACE": str(workspace),
           "PYTHONIOENCODING": "utf-8"}
    env.pop("PRISMA_CONFIG", None)

    proc = subprocess.run([sys.executable, str(script), str(tmp_path)], cwd=REPO_ROOT, env=env,
                          capture_output=True, timeout=120)

    stderr = proc.stderr.decode("utf-8", "replace")
    assert proc.returncode == 0, stderr
    assert proc.stdout == b"", proc.stdout[:500]
    result = json.loads(stderr.rsplit("RESULT ", 1)[1])
    assert result["statuses"] == ["ok"] * 5, stderr
    assert result["papers"] == 5 and result["downloaded"] >= 2
    assert "Searching openalex" in stderr  # progress went to stderr instead
