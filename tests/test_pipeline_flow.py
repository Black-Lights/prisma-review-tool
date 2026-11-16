"""PRISMA 2020 flow numbers: one compute_flow for /api/stats, the diagrams, the CLI and MCP.

Covers PIPE#12 and the /api/stats "flow" contract: automation exclusions counted once,
before screening; "maybe" papers nobody reviewed are awaiting, never excluded.
"""

from __future__ import annotations

import json
import random
import re

import pytest

from conftest import write_dataset
from prisma_review.config import Config
from prisma_review.models import Paper


def j(text: str) -> dict:
    return json.loads(text)


def assert_closes(flow: dict) -> None:
    removed = flow["removed_before_screening"]
    assert flow["identified"]["total"] - removed["duplicates"] - removed["automation_ineligible"] \
        - flow["awaiting_screening"] == flow["screened"]
    assert flow["screened"] - flow["screening_excluded"] == flow["sought_for_retrieval"]
    assert flow["sought_for_retrieval"] - flow["eligibility_excluded"] - flow["awaiting_eligibility"] \
        == flow["included"]
    assert removed["automation_ineligible"] == sum(removed["automation_by_reason"].values())


def test_stats_flow_of_a_fresh_review(api_client, workspace):
    write_dataset(workspace.output_dir("alpha"))
    flow = api_client.get("/api/stats").json()["flow"]
    assert flow["identified"] == {"total": 7, "by_source": {"openalex": 7}, "capped_searches": 0}
    assert flow["removed_before_screening"] == {
        "duplicates": 1, "automation_ineligible": 1,
        "automation_by_reason": {"keyword_rules": 1, "required_keywords": 0}}
    assert (flow["screened"], flow["included_by_automation"]) == (2, 2)
    assert (flow["screening_excluded"], flow["awaiting_screening"]) == (0, 3)
    assert flow["sought_for_retrieval"] == 2
    assert (flow["assessed_for_eligibility"], flow["eligibility_excluded"],
            flow["awaiting_eligibility"], flow["included"]) == (0, 0, 2, 0)
    assert_closes(flow)
    notes = " ".join(flow["notes"]).lower()
    assert "3 records are not yet screened" in notes and "keyword rules alone" in notes


def test_stats_flow_after_ai_manual_and_eligibility_decisions(api_client, mcp_server, workspace):
    write_dataset(workspace.output_dir("alpha"))
    j(mcp_server.batch_screen_papers([{"paper_id": "p4", "decision": "exclude", "reason": "off topic"}]))
    api_client.post("/api/papers/p5/screen", json={"decision": "include", "reason": "fits"})
    j(mcp_server.batch_eligibility_screen([
        {"paper_id": "p1", "decision": "include", "reason": "fits"},
        {"paper_id": "p5", "decision": "exclude", "reason": "no evaluation"}]))

    flow = api_client.get("/api/stats").json()["flow"]
    assert flow["removed_before_screening"]["automation_ineligible"] == 1
    assert flow["screened"] == 4
    assert (flow["screening_excluded"], flow["awaiting_screening"]) == (1, 1)
    assert flow["screening_excluded_by_method"] == {"ai": 1, "manual": 0}
    assert flow["sought_for_retrieval"] == 3
    assert (flow["assessed_for_eligibility"], flow["eligibility_excluded"],
            flow["awaiting_eligibility"], flow["included"]) == (2, 1, 1, 1)
    assert_closes(flow)


def test_required_keyword_gate_is_its_own_automation_reason(api_client, workspace):
    from conftest import make_config, write_config

    write_dataset(workspace.output_dir("alpha"))
    cfg = make_config()
    cfg["screening"]["rules"]["required_keywords"] = ["yield"]
    write_config(workspace.project_config("alpha"), cfg)
    api_client.post("/api/papers/rescreen?min_include_hits=2")
    flow = api_client.get("/api/stats").json()["flow"]
    assert flow["removed_before_screening"]["automation_by_reason"] == {
        "keyword_rules": 1, "required_keywords": 3}
    assert (flow["screened"], flow["awaiting_screening"], flow["sought_for_retrieval"]) == (2, 0, 2)
    assert_closes(flow)


def _random_review(rng: random.Random, n: int) -> tuple[dict, list[Paper], list[Paper]]:
    from prisma_review.screen import NO_REQUIRED_KEYWORD_REASON

    papers = []
    for i in range(n):
        method = rng.choice(["rule", "rule", "ai", "manual", None])
        decision = None if method is None else rng.choice(["include", "exclude", "maybe"])
        reason = NO_REQUIRED_KEYWORD_REASON if (method == "rule" and decision == "exclude"
                                                and rng.random() < 0.5) else "r"
        papers.append(Paper(id=f"x{i}", title=f"t{i}", source=rng.choice(["openalex", "scopus"]),
                            screen_decision=decision, screen_method=method, screen_reason=reason))
    included = [p for p in papers if p.screen_decision == "include"]
    elig = [Paper(id=p.id, title=p.title, eligibility_decision=rng.choice(["include", "exclude"]))
            for p in included if rng.random() < 0.6]
    dups = rng.randint(0, 50)
    state = {"search": {"openalex": n + dups, "total": n + dups},
             "dedup": {"duplicates_removed": dups, "remaining": n}}
    return state, papers, elig


@pytest.mark.parametrize("seed", range(20))
def test_flow_arithmetic_always_closes(seed):
    from prisma_review.screen import screen_summary
    from prisma_review.stats import compute_flow, eligibility_summary

    rng = random.Random(seed)
    state, papers, elig = _random_review(rng, rng.randint(1, 200))
    included = [p for p in papers if p.screen_decision == "include"]
    flow = compute_flow(state, screen_summary(papers), eligibility_summary(included, elig))
    assert_closes(flow)
    assert flow["awaiting_screening"] == sum(1 for p in papers if p.screen_decision in ("maybe", None))


def test_flow_from_state_alone_still_closes():
    from prisma_review.stats import compute_flow

    state = {"search": {"openalex": 10, "total": 10}, "dedup": {"duplicates_removed": 2, "remaining": 8},
             "screen": {"total_screened": 8, "included": 2, "excluded": 3, "maybe": 3}}
    flow = compute_flow(state)
    assert_closes(flow)
    assert flow["awaiting_screening"] == 3


# --------------------------------------------------------------------------- diagrams, CLI, MCP


@pytest.fixture
def drawn_text(monkeypatch) -> list[str]:
    import matplotlib.axes

    texts: list[str] = []
    original = matplotlib.axes.Axes.text

    def record(self, x, y, s, *args, **kwargs):
        texts.append(str(s))
        return original(self, x, y, s, *args, **kwargs)

    monkeypatch.setattr(matplotlib.axes.Axes, "text", record)
    return texts


def _n(text: str, label: str) -> int:
    match = re.search(re.escape(label) + r"[^\n]*?n = (\d+)", text)
    assert match, f"{label!r} not found in:\n{text}"
    return int(match.group(1))


def test_cli_report_diagrams_use_the_flow(workspace, drawn_text):
    from prisma_review import cli

    write_dataset(workspace.output_dir("alpha"))
    config = Config.load(workspace.project_config("alpha"))
    cli.cmd_report(config)

    md = (config.export_dir / "prisma_flow.md").read_text(encoding="utf-8")
    assert _n(md, "Records screened") == 2
    assert _n(md, "Records marked as ineligible by automation tools") == 1
    assert _n(md, "Records excluded") == 0
    assert _n(md, "Records not yet screened") == 3
    assert _n(md, "Included by the keyword rules without reviewer screening") == 2
    assert _n(md, "Reports sought for retrieval") == 2
    assert "Pending" in md  # no eligibility decisions yet

    assert (config.export_dir / "prisma_flow.png").is_file()
    screened_boxes = [t for t in drawn_text if t.startswith("Records screened")]
    assert screened_boxes and all("(n = 2)" in t for t in screened_boxes), screened_boxes
    not_yet = [t for t in drawn_text if t.startswith("Records not yet screened")]
    assert not_yet and all("(n = 3)" in t for t in not_yet), not_yet
    assert any("Note: 3 records are not yet screened" in t for t in drawn_text)
    excluded_boxes = [t for t in drawn_text if t.startswith("Records excluded")]
    assert excluded_boxes and all("(n = 0)" in t for t in excluded_boxes), excluded_boxes


def test_cli_status_prints_the_flow(workspace, capsys):
    from prisma_review import cli

    write_dataset(workspace.output_dir("alpha"))
    cli.cmd_status(Config.load(workspace.project_config("alpha")))
    out = capsys.readouterr().out
    assert "Not yet screened: 3 (no screening decision recorded)" in out
    assert "Screened: 2 (0 excluded; 2 included by the keyword rules, no reviewer)" in out
    assert "Removed before screening: 1 duplicates, 1 by automation tools" in out


def test_mcp_generate_report_returns_the_same_flow(api_client, mcp_server, workspace):
    write_dataset(workspace.output_dir("alpha"))
    out = j(mcp_server.generate_report())
    assert out["status"] == "ok" and out["project"] == "alpha"
    assert out["flow"] == api_client.get("/api/stats").json()["flow"]
    assert_closes(out["flow"])
    stats = j(mcp_server.get_screening_stats())
    assert stats["flow"] == out["flow"]


def test_api_generate_report_writes_flow_diagram(api_client, workspace):
    write_dataset(workspace.output_dir("alpha"))
    assert api_client.post("/api/reports/generate").json()["status"] == "ok"
    md = (workspace.output_dir("alpha") / "04_export" / "prisma_flow.md").read_text(encoding="utf-8")
    assert _n(md, "Records screened") == 2


def test_stats_without_any_state_is_an_error_message(api_client):
    assert "error" in api_client.get("/api/stats").json()


# --------------------------------------------------------------------------- R-13


def test_before_screening_nothing_is_reported_as_screened():
    from prisma_review.stats import compute_flow

    flow = compute_flow({"search": {"openalex": 100, "total": 100},
                         "dedup": {"duplicates_removed": 10, "remaining": 90}})
    assert flow["screening_started"] is False
    assert (flow["screened"], flow["awaiting_screening"], flow["sought_for_retrieval"]) == (0, 90, 0)
    assert_closes(flow)
    notes = " ".join(flow["notes"])
    assert "Screening has not run yet" in notes and "maybe" not in notes


def test_screen_summary_names_the_records_in_the_screening_file(mcp_server, workspace):
    write_dataset(workspace.output_dir("alpha"))
    stats = j(mcp_server.get_screening_stats())
    assert stats["screen"]["records_in_screening"] == 6
    assert "total_screened" not in stats["screen"]
    assert stats["flow"]["screened"] == 2 and stats["flow"]["awaiting_screening"] == 3
