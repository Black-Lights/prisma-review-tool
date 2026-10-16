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
- Keep queries focused: better to have 3-4 specific queries than 1 huge one

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

**How each source reads your query**: OpenAlex, Scopus and arXiv run the Boolean query (`AND`/`OR`/`NOT`, quoted phrases, parentheses). Crossref and Semantic Scholar only use the quoted phrases. The pipeline warnings (and `get_review_config` in the MCP server) say what each source drops. Avoid `*` wildcards.

If a config has no `sources` key at all, the tool searches arXiv, OpenAlex and Semantic Scholar (the default since v1.0).

## API Keys

```yaml
api_keys:
  scopus: ""            # Scopus API key (institutional access)
  openalex_key: ""      # Free OpenAlex API key (strongly recommended)
  openalex_email: ""    # Optional contact email sent to OpenAlex
```

**OpenAlex key**: OpenAlex requires an API key to page past the first page of results. Without `openalex_key`, every OpenAlex query stops at 50 records. Create a free account at [openalex.org](https://openalex.org) and copy the API key from your account settings. The MCP tools and `GET /api/config/readiness` warn when OpenAlex is enabled without a key.

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

