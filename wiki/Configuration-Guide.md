# Configuration Guide

The entire review protocol is defined in `config.yaml`. This makes your review fully reproducible — anyone with the same config gets the same search results.

## File Structure

```yaml
project:
  name: "Your Review Title"
  output_dir: "./prisma_output"

api_keys:
  scopus: ""              # Optional
  openalex_email: ""      # Optional but recommended

search:
  date_range:
    start: "2020-01-01"
    end: "2026-12-31"
  max_results_per_query: 500
  sources:
    - arxiv
    - openalex
    - semantic_scholar
  queries:
    - name: "query_name"
      terms: >
        ("term A" OR "term B") AND ("term C")

dedup:
  doi_match: true
  fuzzy_title_threshold: 90

screening:
  rules:
    include_keywords:
      - keyword 1
      - keyword 2
    exclude_keywords:
      - irrelevant topic
    min_include_hits: 2
```

## Search Queries

### Writing Boolean Queries

Use standard Boolean operators:

```yaml
terms: >
  ("geospatial foundation model" OR "earth observation foundation model")
  AND ("embedding" OR "representation" OR "feature extraction")
  AND ("agriculture" OR "crop" OR "land cover")
```

**Rules:**
- Wrap multi-word phrases in quotes: `"foundation model"`
- Use `OR` between synonyms
- Use `AND` between different concepts
- Use parentheses to group terms
- The `>` after `terms:` allows multi-line YAML strings

### How Many Queries?

Recommended: **3-5 focused queries** rather than 1 massive query.

| Query | Focus |
|-------|-------|
| `main_topic` | Your core research question |
| `methods` | Specific methods/techniques you're reviewing |
| `applications` | Application domain |
| `specific_works` | Named models, datasets, or systems |

### Query Translation

Each database has different search syntax. The tool automatically translates your Boolean queries:

- **arXiv**: Converts to arXiv API field queries
- **OpenAlex**: Simplifies to text search (OpenAlex doesn't support full Boolean)
- **Semantic Scholar**: Simplifies to keyword search

This means your results may vary by source — this is expected and documented in PRISMA.

## Database Sources

| Source | Coverage | Speed | Best For |
|--------|----------|-------|----------|
| `arxiv` | CS, Physics, Math preprints | Fast | ML/AI papers, preprints |
| `openalex` | 250M+ works, all fields | Medium | Broad multidisciplinary coverage |
| `semantic_scholar` | Academic papers, strong CS | Slow (rate limited) | CS/AI papers with citations |
| `scopus` | High-quality indexed journals | Fast | Best metadata (needs API key) |

### API Keys

- **arXiv, OpenAlex, Semantic Scholar**: Free, no key needed
- **OpenAlex email**: Optional but recommended — increases rate limits
- **Scopus**: Requires institutional API key from [dev.elsevier.com](https://dev.elsevier.com)

## Screening Keywords

### Include Keywords

Papers must contain at least `min_include_hits` of these keywords in their title + abstract:

```yaml
include_keywords:
  - foundation model
  - remote sensing
  - crop
  - agriculture
  - change detection
  - embedding
```

**Tips:**
- Use lowercase (matching is case-insensitive)
- Include both specific terms ("foundation model") and broader terms ("remote sensing")
- Start with 8-15 keywords

### Exclude Keywords

Papers matching ANY of these are automatically excluded:

```yaml
exclude_keywords:
  - medical imaging
  - clinical
  - drug
  - genomics
```

**Tips:**
- Be specific — broad exclude terms may remove relevant papers
- Start with domains that are clearly irrelevant to your review

### Tuning min_include_hits

| Value | Effect |
|-------|--------|
| 1 | Very permissive — most papers pass |
| 2 | Balanced (recommended starting point) |
| 3 | Strict — fewer papers pass |
| 4+ | Very strict — only highly relevant papers |

**Strategy:**
1. Start with `min_include_hits: 2`
2. Run `python -m prisma_review screen-rules`
3. Check the counts — if too many papers pass, increase to 3
4. If important papers land in "maybe" or "excluded", adjust your keywords

## Deduplication Settings

```yaml
dedup:
  doi_match: true              # Match by DOI (recommended: always true)
  fuzzy_title_threshold: 90    # 0-100, higher = stricter
```

| Threshold | Behavior |
|-----------|----------|
| 85 | Aggressive — catches title variations but may false-match |
| 90 | Balanced (default) |
| 95 | Conservative — only near-identical titles |

Check `prisma_output/02_dedup/duplicates_log.csv` to verify dedup quality.

## Date Range

```yaml
date_range:
  start: "2020-01-01"    # When the topic became active
  end: "2026-03-29"      # Your search cutoff date
```

**Guidelines:**
- For new fields (foundation models, LLMs): start 2020+
- For established fields: start 2010-2015
- Always set end date to your actual search date for reproducibility

## Output Directory

```yaml
output_dir: "./prisma_output"    # Relative to config.yaml location
```

This is where all results are stored. The directory is created automatically. Structure:

```
prisma_output/
├── 01_search/        # Raw search results
├── 02_dedup/         # Deduplicated papers + log
├── 03_screen/        # Screening decisions
├── 03b_eligibility/  # Second-pass eligibility decisions
├── 04_export/        # BibTeX, CSV, PRISMA diagrams
└── review_state.json # Pipeline state
```
