# Writing Your Methodology

This page provides a template for describing your prisma_tool-assisted review in a thesis, paper, or report. Adapt the bracketed sections to your specific review.

---

## Template: Methods Section

### 2.1 Review Protocol

This systematic literature review follows the PRISMA 2020 guidelines (Page et al., 2021). The review protocol, including search queries, screening criteria, and all decisions, is preserved in machine-readable format for full reproducibility.

In accordance with PRISMA 2020 Item 8, we report the use of automation tools at each stage of the selection process. We additionally follow PRISMA-trAIce recommendations for transparent reporting of AI involvement.

### 2.2 Information Sources (PRISMA Item 6)

The following databases were searched on [DATE]:

| Database | Type | Records Found |
|----------|------|---------------|
| [Source 1] | [Type] | [N] |
| [Source 2] | [Type] | [N] |
| [Source 3] | [Type] | [N] |
| **Total** | | **[N]** |

### 2.3 Search Strategy (PRISMA Item 7)

[N] query groups were constructed using Boolean operators:

1. **[Query name]**: `[Full Boolean query string]`
2. **[Query name]**: `[Full Boolean query string]`

Date range: [START] to [END].

The complete search protocol is preserved in `config.yaml` and is available as supplementary material [or at GitHub URL].

### 2.4 Study Selection (PRISMA Item 8)

Study selection followed a two-stage process combining automated and AI-assisted screening.

**Stage 1: Automated keyword screening.** An automated rule-based screening was applied to all titles and abstracts. Papers were classified as "include" (matching >=N inclusion keywords and 0 exclusion keywords), "exclude" (matching any exclusion keyword), or "maybe" (insufficient keyword matches).

- Inclusion keywords: [list]
- Exclusion keywords: [list]
- Minimum keyword threshold: [N]
- Papers classified as "maybe" were subsequently reviewed using AI-assisted screening.

**Stage 1b: AI-assisted review of uncertain papers.** Papers in the "maybe" category (n = [N]) were reviewed by [AI agent name], which read each paper's title and abstract and made include/exclude decisions based on the review's eligibility criteria. [N] papers were included and [N] were excluded in this step.

**Stage 2: AI-assisted eligibility screening.** The first-pass screening yielded [N] included papers — more than feasible for full-text review. A stricter second-pass eligibility screening was applied, where [AI agent name] reviewed each included paper's abstract against tighter criteria:

- [Specific stricter criteria]

This narrowed the included set to [N] papers for full-text review.

### 2.5 Automation Tools (PRISMA Item 8, continued)

| Aspect | Details |
|--------|---------|
| Tool | prisma_tool (v1.0, MIT license) |
| Available at | [GitHub URL] |
| AI agent | [Name and version, e.g., Claude Opus 4.6 via Claude Code] |
| Integration | Model Context Protocol (MCP), stdio transport |
| Cost | Zero additional API cost (agent subscription only) |
| Decision logging | Every decision stored with: paper_id, decision, reason, method (rule/ai/manual) |
| Human oversight | All AI decisions reviewable; researcher can override any decision |

The automation tool was used to eliminate records before review (keyword screening) and to assist in the eligibility assessment (AI screening). All AI-generated decisions were logged for transparency and are available as supplementary data.

### 2.6 Deduplication (PRISMA Item 9)

Duplicate removal followed a two-step process:
1. Exact DOI matching (after URL prefix removal and lowercasing)
2. Fuzzy title matching using token sort ratio (threshold: [N]/100)

When duplicates were found across sources, the version with the most complete metadata was retained.

### 2.7 PRISMA Flow

[Reference to your prisma_flow.png]

| Stage | n |
|-------|---|
| Records identified | [N] |
| Duplicates removed | [N] |
| Records screened | [N] |
| Excluded (keyword rules + AI) | [N] |
| First-pass included | [N] |
| Eligibility excluded | [N] |
| **Studies included in review** | **[N]** |

---

## Template: Limitations Paragraph

> The use of AI-assisted screening introduces limitations. AI decisions are based on titles and abstracts only, not full text; some relevant papers may be excluded, and some irrelevant papers may be included. The keyword-based first-pass screening depends on keyword selection and may miss papers using non-standard terminology. Free databases (arXiv, OpenAlex, Semantic Scholar) may have coverage gaps compared to subscription databases. While all AI decisions are logged and reproducible within the same session, AI outputs may vary slightly across sessions due to model stochasticity. Only English-language papers were included.

---

## Template: Data Availability Statement

> The complete review protocol (config.yaml), screening decisions (JSON), and the automation tool (prisma_tool) are available at [GitHub URL] under the MIT license. All AI screening decisions, including paper IDs, decisions, reasons, and methods, are preserved in the output files and available as supplementary material.

---

## References to Include

```bibtex
@article{page2021prisma,
  title={The PRISMA 2020 statement: an updated guideline for reporting systematic reviews},
  author={Page, Matthew J and McKenzie, Joanne E and others},
  journal={BMJ},
  volume={372},
  pages={n71},
  year={2021}
}
```
