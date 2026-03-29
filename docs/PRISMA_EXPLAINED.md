# What is PRISMA?

[PRISMA 2020](https://www.prisma-statement.org/prisma-2020) (Preferred Reporting Items for Systematic Reviews and Meta-Analyses) is the international guideline for conducting standardized, reproducible, and transparent literature reviews.

**Key resources:**
- [PRISMA 2020 Statement](https://www.prisma-statement.org/prisma-2020)
- [PRISMA 2020 Checklist (27 items)](https://www.prisma-statement.org/prisma-2020-checklist)
- [PRISMA 2020 Flow Diagram Template](https://www.prisma-statement.org/prisma-2020-flow-diagram)
- [Full paper: Page et al. (2021), BMJ](https://doi.org/10.1136/bmj.n71)

## How This Tool Follows PRISMA 2020

| PRISMA Step | What You Do | Tool Command |
|-------------|-------------|--------------|
| Define search queries | Write `config.yaml` | — |
| Search databases (Item 6-7) | Tool searches arXiv, OpenAlex, etc. | `search` |
| Remove duplicates (Item 9) | Tool matches DOIs + fuzzy titles | `dedup` |
| Screen by title/abstract (Item 8) | Keyword rules + AI via MCP | `screen-rules` + MCP |
| Eligibility assessment (Item 8) | AI applies stricter criteria | MCP eligibility tools |
| Report automation tools (Item 8) | Method tags: rule/ai/manual | Automatic |
| Generate flow diagram (Item 16a) | Tool creates diagram with numbers | `report` |
| Export for writing | .bib for citations, .csv for data | `export` |

## The Flow Diagram

The [PRISMA 2020 flow diagram](https://www.prisma-statement.org/prisma-2020-flow-diagram) shows how many papers went through each stage. This tool generates it automatically:

```
IDENTIFICATION: Records identified from databases (per source)
    → Duplicates removed
    → Records marked as ineligible by automation tools

SCREENING: Records screened (title + abstract)
    → Records excluded (with reasons)

ELIGIBILITY: Reports assessed for eligibility (AI-assisted)
    → Reports excluded (stricter criteria)

INCLUDED: Studies included in review
```

Generated as both PNG image and Markdown text, following the [PRISMA 2020 template](https://www.prisma-statement.org/prisma-2020-flow-diagram).

## PRISMA 2020 vs PRISMA 2009

Key changes that this tool addresses:

| Change | PRISMA 2009 | PRISMA 2020 |
|--------|-------------|-------------|
| Automation tools | Not mentioned | Must report (Item 8) |
| AI in screening | Not mentioned | Document per [PRISMA-trAIce](https://doi.org/10.2196/70514) |
| Studies vs reports | Not distinguished | Must distinguish |
| Automation exclusions | Not in diagram | Separate box required |
