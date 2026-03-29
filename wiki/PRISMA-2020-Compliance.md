# PRISMA 2020 Compliance

This page maps prisma_tool features to the PRISMA 2020 checklist items.

## Checklist Mapping

The PRISMA 2020 checklist has 27 items. This tool directly supports reporting for 7 of them. The remaining items require human input (research questions, risk of bias, discussion, etc.).

### Items Directly Supported by the Tool

| Item | Requirement | How the Tool Addresses It |
|------|-------------|--------------------------|
| **6. Information sources** | List databases searched, date of search | `config.yaml` records all sources and date range; `review_state.json` stores per-source counts |
| **7. Search strategy** | Full search strategy for all databases | `config.yaml` preserves exact Boolean queries used |
| **8. Selection process** | Describe screening, automation tools used | Two-pass screening with method tags (rule/ai/manual); tool name and version logged |
| **9. Data collection** | Describe data extraction, automation tools | Automated extraction from APIs; structured JSON format |
| **16a. Study selection results** | Flow diagram with numbers | Auto-generated PRISMA flow diagram (PNG + Markdown) |
| **16b. Excluded studies** | List excluded studies with reasons | All exclusion reasons stored in JSON |
| **27. Data availability** | State where data/code available | Tool is open-source; all decisions exportable |

### Items Requiring Human Input

| Item | Requirement | What You Need to Write |
|------|-------------|----------------------|
| 1 | Title | Identify as systematic review |
| 2 | Abstract | Structured abstract |
| 3 | Rationale | Why this review is needed |
| 4 | Objectives | Research questions |
| 5 | Eligibility criteria | Inclusion/exclusion criteria (human-defined, tool-enforced) |
| 10-15 | Risk of bias, outcomes, synthesis | Study-level analysis (beyond screening) |
| 17-22 | Results, synthesis | Content analysis of included papers |
| 23-26 | Discussion, limitations, registration, funding | Human-written sections |

## PRISMA 2020 Flow Diagram Compliance

The PRISMA 2020 flow diagram has specific required elements. Here's how our generated diagram maps:

### Required Boxes (PRISMA 2020)

| Box | Required Content | Our Implementation |
|-----|-----------------|-------------------|
| **Identification** | Records from databases (with source counts) | Shows per-source counts (arXiv, OpenAlex, etc.) |
| **Removal before screening** | Duplicates removed + automation tool exclusions | Shows duplicates AND keyword rule exclusions separately |
| **Screening** | Records screened, records excluded | Shows screened count and excluded count with method |
| **Eligibility** | Reports assessed, reports excluded with reasons | Shows second-pass numbers (when eligibility screening is done) |
| **Included** | Studies included + reports included | Shows final included count |

### PRISMA 2020 vs PRISMA 2009 Changes We Follow

| Change | PRISMA 2009 | PRISMA 2020 | Our Tool |
|--------|-------------|-------------|----------|
| Automation tools | Not mentioned | Must report (Item 8) | Method tags: rule/ai/manual |
| Studies vs reports | Not distinguished | Must distinguish | Tracked separately |
| Automation exclusions | Not in diagram | Separate box required | "Automation tool exclusions" in removal box |
| Multiple databases | Shown combined | Can show separately | Per-source counts in identification |

## PRISMA-trAIce Compliance

PRISMA-trAIce (2025) extends PRISMA 2020 for AI transparency. Our tool supports:

| PRISMA-trAIce Item | Our Implementation |
|--------------------|-------------------|
| AI tool identification | Claude via MCP (logged per decision) |
| Human vs AI separation | `screen_method` field: "rule", "ai", "manual" |
| AI decision logging | Every decision has reason + method |
| Reproducibility | Full config.yaml preserves protocol |
| Validation capability | Decision logs enable manual spot-checking |

## What PRISMA 2020 Requires That We Don't Automate

These are intentionally left to the researcher:

1. **Risk of bias assessment** — requires reading full papers, not just abstracts
2. **Data extraction** — extracting specific variables from included studies
3. **Synthesis/meta-analysis** — statistical analysis across studies
4. **Discussion** — interpreting results, comparing with prior reviews
5. **Registration** — registering the protocol (e.g., PROSPERO)

These are beyond the scope of a screening tool and require domain expertise.

## Reporting Template

When writing your methods section, use this structure:

```
2.1 Search Strategy
- Databases: [list from config.yaml sources]
- Date range: [from config.yaml]
- Queries: [from config.yaml, include full Boolean strings]

2.2 Study Selection
- Stage 1: Automated keyword screening using prisma_tool
  - Include keywords: [list]
  - Exclude keywords: [list]
  - Threshold: [min_include_hits] keywords required

- Stage 2: AI-assisted eligibility screening
  - Tool: [Agent name] via MCP integration with prisma_tool
  - Criteria: [your stricter criteria]
  - All decisions logged with reasons

2.3 Automation Tools (PRISMA Item 8)
- Tool: prisma_tool (MIT license, available at [GitHub URL])
- Screening automation: Rule-based keyword screening eliminates
  ineligible records before AI review
- AI integration: [Agent] via Model Context Protocol
- Human oversight: All decisions reviewable and overridable
```

See [Writing Your Methodology](Writing-Your-Methodology) for the full template.
