"""Report endpoints: per-query attribution notes and read-only paper caching.

Covers PIPE#18 (duplicate or missing query names, untagged papers explained) and the
server-side cost part of PIPE#14 (parsed paper lists cached by file fingerprint).
"""

from __future__ import annotations

from conftest import make_config, write_config, write_dataset
from prisma_review.models import Paper, load_papers, save_papers


def test_by_query_explains_duplicate_names_and_untagged_papers(api_client, workspace):
    out = workspace.output_dir("alpha")
    write_dataset(out)
    cfg = make_config()
    cfg["search"]["queries"] = [{"name": "main", "terms": "a"}, {"name": "main", "terms": "b"},
                                {"terms": "c"}]
    write_config(workspace.project_config("alpha"), cfg)
    raw = load_papers(out / "01_search" / "all_records.json")
    raw[0].matched_queries = []
    save_papers(raw, out / "01_search" / "all_records.json")

    body = api_client.get("/api/reports/by-query").json()
    notes = " ".join(body["notes"]).lower()
    assert "main" in notes and "more than one query" in notes
    assert "without a name" in notes
    assert "1 record" in notes and "before" in notes
    assert body["untagged"] == {"raw": 1, "screened": 0}


def test_paper_cache_reloads_when_the_file_changes(tmp_path):
    from prisma_review.stats import load_papers_cached

    path = tmp_path / "papers.json"
    save_papers([Paper(id="a", title="A")], path)
    first = load_papers_cached(path)
    assert [p.id for p in first] == ["a"]
    assert load_papers_cached(path) is first  # unchanged file: no re-parse
    save_papers([Paper(id="a", title="A"), Paper(id="b", title="B")], path)
    assert [p.id for p in load_papers_cached(path)] == ["a", "b"]
    assert load_papers_cached(tmp_path / "missing.json") == []

