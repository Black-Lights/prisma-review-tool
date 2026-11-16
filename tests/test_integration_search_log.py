"""search_log.json and all_records.json describe the same search (runner and pipeline together).

The runner writes 01_search/search_log.json once every (source, query) pair
has finished and none was cancelled. The pipeline's search step must then
save the records of that same search, even when Stop arrives a moment after
the last request: the step finished, and the run stops at the next step.
"""

from __future__ import annotations

import json

from conftest import make_config, write_config, write_dataset
from prisma_review.config import Config
from prisma_review.models import Paper, load_papers


def test_records_saved_match_the_search_log_when_stop_arrives_after_the_last_request(
        workspace, monkeypatch):
    from prisma_review import pipeline
    from prisma_review.search import runner

    cfg = make_config("Alpha review")
    cfg["search"]["sources"] = ["openalex", "arxiv"]
    config = Config.load(write_config(workspace.project_config("alpha"), cfg))
    write_dataset(config.output_dir)  # an earlier search: 7 records
    stop = {"pressed": False}
    pairs = []

    def backend(source, terms, start, end, config, filters, status, should_cancel):
        pairs.append(source)
        if len(pairs) == len(cfg["search"]["sources"]):
            stop["pressed"] = True  # Stop clicked while the last response was parsed
        status.executed = terms
        return [Paper(title=f"{source} paper {i}", abstract="crop yield prediction",
                      source=source, source_id=f"{source}-{i}", year=2023) for i in range(2)]

    monkeypatch.setattr(runner, "_run_backend", backend)
    outcome = pipeline.search_step(config, should_cancel=lambda: stop["pressed"],
                                   replace_downstream=True)

    log = json.loads((config.search_dir / runner.SEARCH_LOG_NAME).read_text(encoding="utf-8"))
    records = load_papers(config.search_dir / "all_records.json")
    assert outcome["status"] == "ok"
    assert log["totals"]["records"] == len(records) == 4
    assert {p.source for p in records} == {"openalex", "arxiv"}
