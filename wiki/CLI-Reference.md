# CLI Reference

All commands are run as:

```bash
python -m prisma_review <command> [options]
```

## Commands

### `search`

Search all configured databases with your queries.

```bash
python -m prisma_review search
```

**What it does:**
- Queries each database (arXiv, OpenAlex, Semantic Scholar) with each query from config.yaml
- Normalizes results into a unified Paper format
- Saves to `prisma_output/01_search/all_records.json`
- Updates `review_state.json` with source counts

**Output:** `prisma_output/01_search/all_records.json`

---

### `dedup`

Remove duplicate papers found across databases.

```bash
python -m prisma_review dedup
```

**What it does:**
- Pass 1: Exact DOI matching (after normalization)
- Pass 2: Fuzzy title matching within same-year papers (threshold from config)
- Keeps the version with the most complete metadata
- Source priority: Scopus > OpenAlex > Semantic Scholar > arXiv

**Output:**
- `prisma_output/02_dedup/deduplicated.json` — unique papers
- `prisma_output/02_dedup/duplicates_log.csv` — log of merged duplicates

---

### `screen-rules`

Apply keyword-based screening rules to classify papers.

```bash
python -m prisma_review screen-rules
```

**What it does:**
- Checks each paper's title + abstract against include/exclude keywords
- Classifies as: include, exclude, or maybe
- Preserves papers already marked as `screen_method: "manual"` (won't override)

**Decision logic:**
```
IF any exclude keyword → EXCLUDE
ELIF include keywords >= min_include_hits → INCLUDE
ELSE → MAYBE
```

**Output:**
- `prisma_output/03_screen/screen_results.json` — all papers with decisions
- `prisma_output/03_screen/included.json` — included papers
- `prisma_output/03_screen/excluded.json` — excluded papers
- `prisma_output/03_screen/maybe.json` — papers needing review

---

### `report`

Generate PRISMA 2020 flow diagram.

```bash
python -m prisma_review report
```

**Output:**
- `prisma_output/04_export/prisma_flow.png` — PNG image diagram
- `prisma_output/04_export/prisma_flow.md` — Markdown text diagram

The diagram automatically includes eligibility data if second-pass screening has been done.

---

### `export`

Export included papers to BibTeX and CSV formats.

```bash
python -m prisma_review export
```

**Output:**
- `prisma_output/04_export/included_papers.bib` — first-pass included (BibTeX)
- `prisma_output/04_export/included_papers.csv` — first-pass included (CSV)
- `prisma_output/04_export/eligible_papers.bib` — final papers after eligibility (BibTeX)
- `prisma_output/04_export/eligible_papers.csv` — final papers after eligibility (CSV)

The eligible files are only created if second-pass eligibility screening has been done.

> **Note:** CLI export always exports ALL included/eligible papers with a fixed set of columns. For filtered export with field selection (choose which columns to include, export only specific decision/source subsets), use the web app's Export Modal on the All Papers page.

---

### `status`

Show current pipeline state and counts.

```bash
python -m prisma_review status
```

**Example output:**
```
[STATUS] Project: My Review Title
  Output: ./prisma_output

  SEARCH: 1247 papers found
    arxiv: 312
    openalex: 800
    semantic: 135
  DEDUP: 89 duplicates removed, 1158 unique
  SCREEN: 423 included, 312 excluded, 423 maybe
  ELIGIBILITY: 67 included, 356 excluded, 0 remaining
```

The ELIGIBILITY line only appears after second-pass screening.

---

### `run-all`

Run the full automated pipeline end-to-end.

```bash
python -m prisma_review run-all
```

Equivalent to running in sequence: `search` → `dedup` → `screen-rules` → `report` → `export`

---

### REST API / Background Execution

The same pipeline steps are available as REST API endpoints via the FastAPI backend:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/pipeline/start` | POST | Start full pipeline in background thread |
| `/api/pipeline/start/{step}` | POST | Start a single step in background |
| `/api/pipeline/progress` | GET | Get current progress (fast, no disk I/O) |
| `/api/pipeline/stop` | POST | Cancel after current step |
| `/api/pipeline/status` | GET | Get pipeline state from disk |

Start the API server: `uvicorn api.main:app --port 8001`

See [Session System](../docs/SESSION_SYSTEM.md) for architecture details.

---

## Global Options

| Option | Description | Default |
|--------|-------------|---------|
| `--config PATH` | Path to config.yaml | `./config.yaml` |
| `--force` | Re-run step even if output exists | Off |

**Examples:**
```bash
# Use a different config file
python -m prisma_review search --config my_other_config.yaml

# Re-run search even if results exist
python -m prisma_review search --force
```

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Config file not found |
| 1 | Missing prerequisite (e.g., running `dedup` before `search`) |
