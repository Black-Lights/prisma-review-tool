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
- Keep queries focused — better to have 3-4 specific queries than 1 huge one

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

### Tuning

- Start with `min_include_hits: 2` — if too many papers pass, increase to 3
- If important papers are being excluded, check your exclude keywords
- The "maybe" category catches uncertain papers for manual/AI review

## Date Range

```yaml
date_range:
  start: "2020-01-01"    # Foundation models are recent — 2020 is a good start
  end: "2026-03-29"      # Today or your search cutoff
```

For reviews of more established fields, start earlier (e.g., 2015).

## Sources

```yaml
sources:
  - arxiv               # Best for: CS, ML, Physics, Math preprints
  - openalex            # Best for: Broad coverage across all fields (250M+ papers)
  - semantic_scholar    # Best for: CS, NLP, AI papers
  # - scopus            # Best for: High-quality indexed journals (needs API key)
```

All free sources are enabled by default. Add Scopus if you have institutional access.

## Fuzzy Dedup Threshold

```yaml
fuzzy_title_threshold: 90    # Default: 90
```

- **90** (default): Only very similar titles are matched as duplicates
- **85**: More aggressive — catches slight title variations
- **95**: Conservative — only near-identical titles

If you see false merges in `duplicates_log.csv`, increase the threshold.
