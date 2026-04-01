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

- **OpenAlex**: Free, no key needed. Add your email for faster responses
- **arXiv**: Free, no key needed. Rate-limits aggressively on pagination
- **Semantic Scholar**: Free, no key needed. Heavy rate limits, may return 0 results
- **Scopus**: Requires institutional API key. Best metadata quality

#### Getting a Scopus API Key

1. Go to [dev.elsevier.com](https://dev.elsevier.com) and register (use your university email)
2. Create an API Key from the dashboard
3. Copy the key to `config.yaml` under `api_keys.scopus`
4. You must be on your institution's network (VPN or campus IP) for the API to work

**Legal notice**: Scopus API usage must comply with the [Elsevier API Service Agreement](https://dev.elsevier.com/api_service_agreement.html). The API is for academic research only. Raw Scopus data (abstracts, metadata) should not be redistributed. The tool's `.gitignore` already excludes `prisma_output/` to prevent accidental commits of downloaded data.

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
| 2 | Balanced (good starting point for small searches) |
| 3 | Moderate — reduces noise significantly |
| 4 | Strict — only highly relevant papers (recommended for large searches) |
| 5+ | Very strict — may miss borderline papers |

**Strategy — simulate before committing:**

You can simulate different thresholds without re-running the pipeline:

```python
python -c "
from prisma_review.config import Config
from prisma_review.models import load_papers
from prisma_review.screen import screen_by_rules, get_by_decision

config = Config.load('config.yaml')
papers = load_papers(config.dedup_dir / 'deduplicated.json')

for threshold in [2, 3, 4, 5]:
    screened = screen_by_rules(list(papers), config.include_keywords, config.exclude_keywords, threshold)
    inc = len(get_by_decision(screened, 'include'))
    print(f'min_hits={threshold}: {inc} included')
"
```

**Why this matters:** With broad searches (1000+ papers), `min_include_hits: 2` may pass too many papers for AI screening, wasting tokens. Increasing to 3-4 with a well-tuned exclusion list is more efficient. In our test, threshold 2 yielded 1,320 included papers; threshold 4 with enhanced exclusions yielded 206 — a 6x reduction with no loss of truly relevant papers.

### Tuning exclude_keywords

Start with domain-specific irrelevant terms (e.g., "medical imaging" for a remote sensing review), then add broader terms for domains that appear in your "included" set but shouldn't be there:

```yaml
exclude_keywords:
  # Domain-specific (always exclude)
  - medical imaging
  - clinical
  - genomics
  # Broader terms (add after reviewing first-pass results)
  - urban
  - flood
  - wildfire
  - disaster
  - marine
  - archaeology
```

**Tip:** Run screening with a low threshold first, spot-check the included papers, identify unwanted domains, add those as exclude keywords, then re-run with a higher threshold.

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
