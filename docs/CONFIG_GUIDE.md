# Configuration Guide

How to write `config.yaml` for any research topic.

## Search Queries

Use Boolean operators to combine terms:

```yaml
queries:
  - name: "my_query"
    terms: >
      ("machine learning" OR "deep learning")
      AND ("healthcare" OR "medical")
      AND ("diagnosis" OR "prediction")
```

**Tips:**
- Use quotes for multi-word phrases: `"foundation model"`
- Use OR between synonyms: `"crop" OR "agriculture"`
- Use AND between different concepts: `"remote sensing" AND "deep learning"`
- Use parentheses to group: `("term A" OR "term B") AND "term C"`
- Write the operators in capitals (`AND`, `OR`, `NOT`); lowercase `and` is searched as a word
- Keep queries focused: better to have 3-4 specific queries than 1 huge one
- Give each query its own `name`: the report attributes papers to queries by name

**Wildcards** (`predict*`, `wom?n`): OpenAlex accepts them only in its unstemmed exact search, so the tool switches OpenAlex to that search for the whole query (the other terms then match only their exact spelling: `network` no longer finds `networks`). Semantic Scholar supports `*` but not `?`, Crossref ignores both, and arXiv does not document them. Stemmed search already matches word endings (`prediction` finds `predictions`), so most queries do not need wildcards.

## Screening Keywords

### Include keywords
Papers must mention at least `min_include_hits` of these in their title+abstract:

```yaml
include_keywords:
  - foundation model
  - deep learning
  - your domain term
```

### Exclude keywords
Papers matching ANY of these are automatically excluded:

```yaml
exclude_keywords:
  - irrelevant domain 1
  - irrelevant domain 2
```

### Required keywords (optional gate)
When set, a paper is excluded unless its title or abstract contains at least one of these terms. Leave it out (or empty) to disable the gate:

```yaml
required_keywords:
  - core term 1
  - core term 2
```

Write each term as a list item; a single string is treated as one term.

A required term must appear as a whole word or phrase: case, HTML markup, hyphens and extra spaces are ignored and a plural `s`/`es` is accepted, so `large language model` matches `Large-Language Models`, but `RAG` does not match `storage`. List other word forms separately (`optimise`, `optimize`). A paper with no abstract whose title has none of the terms is left as "maybe" for review instead of being excluded. Include and exclude keywords still match anywhere in the text.

### Tuning

- Start with `min_include_hits: 2`; if too many papers pass, increase to 3
- If important papers are being excluded, check your exclude keywords
- The "maybe" category catches uncertain papers for manual/AI review

## Date Range

```yaml
date_range:
  start: "2020-01-01"    # Foundation models are recent: 2020 is a good start
  end: "2026-03-29"      # Today or your search cutoff
```

For reviews of more established fields, start earlier (e.g., 2015).

`start` and `end` accept `YYYY-MM-DD`, `YYYY-MM` or `YYYY` (a year alone means 1 January for `start` and 31 December for `end`). A date that cannot be read is reported as a config problem before the search runs. OpenAlex, Crossref, Semantic Scholar and arXiv filter by the full date; Scopus filters by publication year only, and the pipeline warnings say so when your range does not start on 1 January and end on 31 December.

## Sources

```yaml
sources:
  - openalex            # Best for: Broad coverage across all fields (250M+ papers)
  # - crossref          # Canonical DOI source, but relevance-ranked: expect off-topic results
  # - arxiv             # Best for: CS, ML, Physics, Math preprints (rate-limited)
  # - semantic_scholar  # Best for: CS, NLP, AI papers (rate-limited)
  # - scopus            # Best for: High-quality indexed journals (needs API key)
```

**Recommended**: start with OpenAlex (free, reliable) and add its free API key (see below). Add arXiv and Semantic Scholar for broader coverage, but be aware of rate limits. Add Scopus if you have institutional access; it provides the best metadata quality.

**Crossref is opt-in**: Crossref ranks by relevance and does not understand Boolean queries, so every query adds up to `max_results_per_query` records, most of them off-topic. Enable it only if you need its DOI coverage.

**How each source reads your query**:

| Source | Query | Fields searched | Date filter |
|--------|-------|-----------------|-------------|
| OpenAlex | Boolean (`search.title_abstract_keywords`) | title, abstract, keywords (stemmed) | publication date |
| Scopus | Boolean inside `TITLE-ABS-KEY(...)` | title, abstract, keywords | publication year |
| Semantic Scholar | Boolean, through the bulk search endpoint (`AND` becomes `+`, `OR` becomes `\|`, `NOT x` becomes `-x`) | title and abstract (stemmed) | publication date |
| arXiv | Boolean, quoted phrases searched as `all:"..."` | all fields | submission date |
| Crossref | plain search terms ranked by relevance: terms from every `AND` group, `NOT` terms left out, at most 10 terms | all bibliographic metadata | publication date |

The pipeline warnings (and `get_review_config` in the MCP server) say what each source loses, and Crossref's warning shows the exact terms it searched. Every search is recorded in `01_search/search_log.json` (see [Search log](#search-log)).

Each query and source runs on its own, and its outcome is reported: `ok`, `partial` (some records came back, then the source stopped, for example a rate limit that outlasted the retries), `failed`, `skipped` (no Scopus key, unknown source) or `cancelled`. A partial or failed search is shown as a pipeline warning instead of looking like a small result. Rate limits (HTTP 429) and server errors are retried a few times with increasing waits.

If a config has no `sources` key at all, the tool searches arXiv, OpenAlex and Semantic Scholar (the default since v1.0).

## API Keys

```yaml
api_keys:
  scopus: ""            # Scopus API key (institutional access)
  openalex_key: ""      # Free OpenAlex API key (strongly recommended)
  openalex_email: ""    # Optional contact email sent to OpenAlex
```

**OpenAlex key**: a free key raises OpenAlex's daily request budget 10 times, and only a key can page past 10,000 results per query. Without one the tool still pages normally up to 10,000 results, but a large search can run out of budget, and the query is then reported as partial. Create a key at [openalex.org/settings/api](https://openalex.org/settings/api) and put it under `api_keys.openalex_key`. The MCP tools and `GET /api/config/readiness` warn when OpenAlex is enabled without a key. The key travels in a request header, never in a URL, and is never written to the search log.

**Contact email**: `openalex_email` is sent to OpenAlex and Crossref as a contact address (their "polite" pools) and to Unpaywall, which needs one to find open-access PDFs. Leave it empty if you prefer; nothing else depends on it.

**Scopus setup**: Get an API key from [dev.elsevier.com](https://dev.elsevier.com), add it under `api_keys.scopus` in your config. Requires institutional network access (VPN or campus IP). Usage must comply with the Elsevier API Service Agreement (academic research only).

The web API never sends key values to the browser: `GET /api/config` shows a set key as `********`, and saving the form with `********` keeps the stored key.

## Fuzzy Dedup Threshold

```yaml
fuzzy_title_threshold: 90    # Default: 90
```

- **90** (default): Only very similar titles are matched as duplicates
- **85**: More aggressive, catches slight title variations
- **95**: Conservative, only near-identical titles

If you see false merges in `duplicates_log.csv`, increase the threshold.

When several records are the same paper, the most complete one is kept: one with an abstract first (keyword rules and AI screening read it), then one with a DOI, then one with authors; the source only breaks ties. The kept record takes any field it lacks (DOI, venue, year, ...) from its duplicates and lists every query (`matched_queries`) and every source (`found_in_sources`, `source_ids`) that found the paper, so a paper found on arXiv keeps its arXiv link for PDF download.

## Source-side filters

```yaml
search:
  filters:
    document_types: []        # journal-article, review, conference-paper, book-chapter, preprint
    require_abstract: false
    open_access: false
    venues: []                # ISSNs (1234-567X or 1234567X) or journal names
```

Each source applies a filter in one of three ways, and the pipeline warnings (plus the web report's filter table) say which:

- **at the request**: the database filters before returning results (for example OpenAlex `type`, Crossref `has-abstract`, Scopus `DOCTYPE`). These results are not re-checked locally, because the database matched them on data the tool does not fully store (a journal has several ISSNs).
- **after the fetch**: the source has no such filter, so the tool removes records locally (for example `require_abstract` for Semantic Scholar, Scopus and arXiv, or venue names for OpenAlex and Crossref). The search log records how many records each source lost this way.
- **not applied**: the source cannot evaluate it, so it is ignored there (for example `open_access` on Crossref, ISSNs on Semantic Scholar, a document type the source has no equivalent for).

Venues: give journals by ISSN where you can. OpenAlex and Crossref restrict by ISSN at the request, so when you mix ISSNs and names, papers from the journals you gave only by name cannot come back from those sources (a warning lists them). Semantic Scholar takes names only.

Scopus without institutional network access falls back to its STANDARD view, which has no abstracts: `require_abstract` is then not applied to Scopus records (it would remove all of them) and a warning says so.

## Search log

Every completed search writes `prisma_output/01_search/search_log.json`, the record PRISMA 2020 item 7 asks for ("the full search strategies for all databases"). For each query and source it holds:

- the query as written and as actually sent (`executed`), with the endpoint and parameters (`request`; API keys and the contact email are left out);
- the fields searched (`field_scope`), the date filter, and how each filter was applied (`filter_modes`);
- the number of matches the database reported (`api_total`), the records retrieved, how many the local filters removed, and whether `max_results_per_query` capped the search;
- the outcome (`status`, `error`), the warnings, and timestamps;

plus the tool version, the date range, the filters, and each query's terms with a SHA-256 hash, so a later edit of a query is detectable. A cancelled search does not overwrite the log of the last completed one.

## Projects and Environment Variables

The web app and the MCP server keep each review in its own folder under `projects/` (`projects/<name>/config.yaml` and `projects/<name>/prisma_output/`). They pick the config in this order:

1. `PRISMA_CONFIG`: a path to one config file (pins that review).
2. `projects/.active_project`: the project selected in the web app (or with the MCP `switch_project` tool).
3. The root `config.yaml`, only when there is no `projects/.active_project` (CLI-style installs). On first start the web app copies it into `projects/`.

A `projects/.active_project` that names a missing project is reported as an error rather than silently replaced by another config.

| Variable | Used by | Purpose |
|----------|---------|---------|
| `PRISMA_CONFIG` | MCP server, web API | Pin one config file, e.g. in `.mcp.json` |
| `PRISMA_WORKSPACE` | MCP server, web API | Folder holding `config.yaml` and `projects/` (default: the install folder) |
| `PRISMA_CORS_ORIGINS` | web API | Extra browser origins allowed to call the API, comma-separated (e.g. `http://my-host:4000`). By default only the local web app is allowed: port 3000 and the port `start.py` picks, on `localhost` and `127.0.0.1`. |

