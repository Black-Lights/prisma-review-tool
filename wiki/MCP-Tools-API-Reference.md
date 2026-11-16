# MCP Tools API Reference

The prisma_tool MCP server exposes 21 tools. All tools return JSON strings; a failure is `{"error": "..."}`. Every tool that changes something also returns `project`, `project_name` and `config_path`, so you can see which review it acted on. An argument of the wrong type (text for a number) is refused by the MCP library before the tool runs, with a plain-text validation error.

Every tool acts on one review: the config pinned by the `PRISMA_CONFIG` environment variable, otherwise the active project in `projects/.active_project` (the one the web app's project switcher sets). See [MCP and AI Screening](MCP-and-AI-Screening#which-review-the-server-uses).

---

## Configuration and Project Tools

### `get_review_config`

Show the review this server will run. Call it first.

**Parameters:** None

**Returns:** the project and config path, how it was chosen (`resolved_from`: `env` for `PRISMA_CONFIG`, `marker` for the active project, `root`), the sources, date window, queries, screening rules and filters, plus `ready`, `problems` (what blocks a run), `warnings` (what changes results, such as OpenAlex without an API key), `query_warnings` (per source, which parts of each query it cannot use) and `filter_warnings` (which filters are applied after the request or ignored).

---

### `set_review_config`

Change the config in use. Only the fields you pass change; everything is validated first, and nothing is written when a value is invalid (the error lists every problem).

**Parameters (all optional):**
| Param | Type | Description |
|-------|------|-------------|
| `name` | str | Review title |
| `sources` | list[str] | Any of `arxiv`, `crossref`, `openalex`, `semantic_scholar`, `scopus` |
| `date_start`, `date_end` | str | Publication window, `YYYY-MM-DD` |
| `queries` | list[{name, terms}] | Unique names; `terms` is a Boolean string. A JSON string of the list is also accepted |
| `include_keywords`, `exclude_keywords` | list[str] | Screening terms matched in title and abstract |
| `min_include_hits` | int | Include keywords a paper needs (1 to 10) |
| `required_keywords` | list[str] | Optional gate: papers with none of these whole words or phrases are excluded; `[]` disables it |
| `document_types` | list[str] | Any of `journal-article`, `review`, `conference-paper`, `book-chapter`, `preprint` |
| `require_abstract`, `open_access` | bool | Source filters |
| `venues` | list[str] | ISSNs (`1234-567X`) or journal names |

**Returns:** `project`, `config_path`, readiness (`ready`, `problems`, `warnings`) and the per-source query and filter warnings.

---

### `list_projects`

List the review projects.

**Parameters:** None

**Returns:**
```json
{
  "active": "crop-yield-review",
  "in_use": "crop-yield-review",
  "projects": [
    {"name": "crop-yield-review", "display_name": "Crop Yield Review", "is_active": true, "in_use": true, "ready": true}
  ],
  "warnings": []
}
```

`in_use` is the review every tool reads and writes: the active project, or the pinned one when `PRISMA_CONFIG` is set (then `pinned_config` gives its path and `switch_project` is disabled). `active_error` appears when no project is selected.

---

### `switch_project`

Make another project active (the same marker the web app's switcher writes).

**Parameters:**
| Param | Type | Description |
|-------|------|-------------|
| `name` | str | The project's folder name (`name` from `list_projects`) |

Refused while a pipeline runs, and while `PRISMA_CONFIG` pins the config.

---

### `create_project`

Create a project from the config template (API keys are carried over from the config in use).

**Parameters:**
| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `name` | str | | Review title; the folder name is derived from it |
| `switch` | bool | true | Make the new project active |

On an install that only has a root `config.yaml`, that review is first moved into `projects/` so it stays reachable. Names that Windows reserves for devices (`con`, `nul`, `com1`, ...) are refused.

---

### `rescreen`

Re-run keyword screening on the deduplicated papers with another threshold (no new search or dedup).

**Parameters:**
| Param | Type | Description |
|-------|------|-------------|
| `min_include_hits` | int | Include keywords a paper needs (1 to 10) |

Keeps every manual and AI decision and every eligibility decision (decisions about papers that leave the included set are set aside and come back if they return), and saves the threshold in the config. Refused while a pipeline runs on the project.

---

## First-Pass Screening Tools

### `get_screening_stats`

Get current pipeline statistics.

**Parameters:** None

**Returns:**
```json
{
  "project": "My Review Title",
  "search": {"arxiv": 312, "openalex": 800, "semantic": 135, "total": 1247},
  "dedup": {"duplicates_removed": 89, "remaining": 1158},
  "screen": {"records_in_screening": 1158, "included": 423, "excluded": 312, "maybe": 423, "breakdown": {"rule_include": 400, "ai_include": 23, "...": 0}},
  "eligibility": {"input_from_screening": 423, "screened": 423, "included": 67, "excluded": 356, "remaining": 0},
  "flow": {"identified": {"total": 1247}, "awaiting_screening": 0, "screened": 735, "...": "..."}
}
```

The `eligibility` key only appears after second-pass screening. `flow` holds the PRISMA 2020 numbers the diagram shows; `awaiting_screening` counts records nobody has screened yet (never counted as screened or excluded).

---

### `get_papers_to_screen`

Get a batch of papers that need screening.

**Parameters:**
| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `batch_size` | int | 10 | Number of papers to return |
| `filter_type` | str | "maybe" | "maybe", "unscreened", or "all" |

**Returns:**
```json
{
  "total_matching": 423,
  "returned": 10,
  "papers": [
    {
      "id": "a99d0ab0",
      "title": "Paper Title",
      "authors": "Smith, J.; Doe, A.",
      "year": 2024,
      "abstract": "First 500 chars of abstract...",
      "venue": "Nature",
      "source": "openalex",
      "doi": "10.1234/example",
      "current_decision": "maybe",
      "current_reason": "only 1 include keyword(s) matched (need 2)"
    }
  ]
}
```

Note: Abstract is **truncated to 500 characters** in this tool. Use `get_paper_details` for the full abstract.

---

### `get_paper_details`

Get full details of a specific paper.

**Parameters:**
| Param | Type | Description |
|-------|------|-------------|
| `paper_id` | str | The paper's unique ID |

**Returns:**
```json
{
  "id": "a99d0ab0",
  "title": "Full Paper Title",
  "authors": ["Smith, J.", "Doe, A."],
  "year": 2024,
  "abstract": "Full abstract text without truncation...",
  "venue": "Nature",
  "doi": "10.1234/example",
  "url": "https://doi.org/10.1234/example",
  "source": "openalex",
  "keywords": ["deep learning", "segmentation"],
  "screen_decision": "maybe",
  "screen_reason": "only 1 include keyword(s) matched (need 2)",
  "screen_method": null
}
```

---

### `screen_paper`

Save a screening decision for a single paper.

**Parameters:**
| Param | Type | Description |
|-------|------|-------------|
| `paper_id` | str | The paper's unique ID |
| `decision` | str | "include" or "exclude" |
| `reason` | str | Brief reason for the decision |

**Returns:**
```json
{
  "status": "ok",
  "paper_id": "a99d0ab0",
  "decision": "exclude",
  "remaining_maybe": 422
}
```

---

### `batch_screen_papers`

Save screening decisions for multiple papers at once.

**Parameters:**
| Param | Type | Description |
|-------|------|-------------|
| `decisions` | str | JSON string of list: `[{"paper_id": "...", "decision": "include"/"exclude", "reason": "..."}]` |

**Returns:**
```json
{
  "processed": 10,
  "remaining_maybe": 413,
  "results": [
    {"paper_id": "a99d0ab0", "status": "ok", "decision": "exclude"},
    {"paper_id": "b12c3d4e", "status": "ok", "decision": "include"}
  ]
}
```

---

### `search_in_papers`

Search within collected papers by keyword in title or abstract.

**Parameters:**
| Param | Type | Description |
|-------|------|-------------|
| `query` | str | Search term (case-insensitive) |

**Returns:**
```json
{
  "query": "foundation model",
  "matches": 42,
  "papers": [
    {"id": "abc123", "title": "...", "year": 2024, "source": "arxiv", "decision": "include"}
  ]
}
```

Returns up to 20 matches.

---

## Second-Pass Eligibility Tools

### `get_papers_for_eligibility`

Get first-pass included papers that need eligibility screening.

**Parameters:**
| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `batch_size` | int | 10 | Number of papers to return |

**Returns:**
```json
{
  "total_first_pass_included": 423,
  "already_screened": 50,
  "remaining": 373,
  "returned": 10,
  "papers": [
    {
      "id": "a99d0ab0",
      "title": "Paper Title",
      "authors": "Smith, J.; Doe, A.",
      "year": 2024,
      "abstract": "FULL abstract (not truncated)",
      "venue": "Nature",
      "source": "openalex",
      "doi": "10.1234/example",
      "screen_decision": "include",
      "screen_reason": "matched 3 include keywords"
    }
  ]
}
```

Note: Abstract is **NOT truncated** in this tool — the AI needs the full text for stricter review.

---

### `eligibility_screen_paper`

Save an eligibility screening decision for a single paper.

**Parameters:**
| Param | Type | Description |
|-------|------|-------------|
| `paper_id` | str | The paper's unique ID |
| `decision` | str | "include" or "exclude" |
| `reason` | str | Brief reason for the decision |

**Returns:**
```json
{
  "status": "ok",
  "paper_id": "a99d0ab0",
  "decision": "include",
  "remaining": 372
}
```

---

### `batch_eligibility_screen`

Save eligibility decisions for multiple papers at once.

**Parameters:**
| Param | Type | Description |
|-------|------|-------------|
| `decisions` | str | JSON string of list: `[{"paper_id": "...", "decision": "include"/"exclude", "reason": "..."}]` |

**Returns:**
```json
{
  "processed": 10,
  "remaining": 363,
  "results": [
    {"paper_id": "a99d0ab0", "status": "ok", "decision": "include"},
    {"paper_id": "b12c3d4e", "status": "ok", "decision": "exclude"}
  ]
}
```

---

## Reporting Tools

### `download_eligible_papers`

Download open-access PDFs for the eligibility-included papers (the first-pass included ones before eligibility screening): Elsevier with a Scopus key and institutional access, arXiv, Unpaywall (needs `openalex_email`) and Semantic Scholar.

**Parameters:** None

**Returns:** the counts downloaded, without an open-access copy and failed, and the folder (`prisma_output/05_pdfs/`).

---

### `generate_report`

Generate PRISMA flow diagram and export papers to BibTeX and CSV.

**Parameters:** None

**Returns:**
```json
{
  "status": "ok",
  "included_papers": 423,
  "eligible_papers": 67,
  "outputs": [
    "prisma_output/04_export/prisma_flow.md",
    "prisma_output/04_export/prisma_flow.png",
    "prisma_output/04_export/included_papers.bib",
    "prisma_output/04_export/included_papers.csv",
    "prisma_output/04_export/eligible_papers.bib",
    "prisma_output/04_export/eligible_papers.csv"
  ],
  "flow_summary": { ... }
}
```

Eligible paper exports only appear if eligibility screening has been done.

---

## Pipeline Management Tools

### `start_pipeline`

Start the full pipeline (search → dedup → screen) in a background thread.

**Parameters:** None

**Returns:**
```json
{
  "status": "started",
  "session_id": "fc7ca386f872"
}
```

If a pipeline is already running:
```json
{
  "error": "Pipeline is already running",
  "status": "running"
}
```

---

### `get_pipeline_progress`

Get the current pipeline progress. Fast (no disk I/O), safe to call frequently.

**Parameters:** None

**Returns:**
```json
{
  "session_id": "fc7ca386f872",
  "status": "running",
  "current_step": "dedup",
  "progress_message": "Removing duplicates...",
  "started_at": "2026-03-30T12:00:00+00:00",
  "finished_at": null,
  "completed_steps": ["search"],
  "warnings": ["semantic_scholar: returned 0 results (possible rate limiting or API error)"],
  "error": null,
  "result": null
}
```

Status values: `idle`, `running`, `completed`, `failed`, `cancelled`

When completed:
```json
{
  "session_id": "fc7ca386f872",
  "status": "completed",
  "current_step": null,
  "progress_message": "Pipeline completed successfully",
  "started_at": "2026-03-30T12:00:00+00:00",
  "finished_at": "2026-03-30T12:05:30+00:00",
  "completed_steps": ["search", "dedup", "screen"],
  "warnings": [],
  "error": null,
  "result": {
    "search": {"status": "ok", "total": 2821, "sources": {"arxiv": 0, "openalex": 1500, "semantic": 1321}},
    "dedup": {"status": "ok", "duplicates_removed": 135, "remaining": 2686},
    "screen": {"status": "ok", "included": 206, "excluded": 844, "maybe": 1636}
  }
}
```

---

### `stop_pipeline`

Request cancellation of the running pipeline. The pipeline stops after the current step finishes — results from completed steps are preserved.

**Parameters:** None

**Returns:**
```json
{
  "status": "cancel_requested"
}
```

If no pipeline is running:
```json
{
  "error": "No pipeline is currently running"
}
```

---

### `start_pipeline_step`

Start a single pipeline step in a background thread.

**Parameters:**
| Param | Type | Description |
|-------|------|-------------|
| `step` | str | The step to run: "search", "dedup", or "screen" |

**Returns:**
```json
{
  "status": "started",
  "session_id": "a261f3d89128",
  "step": "dedup"
}
```
