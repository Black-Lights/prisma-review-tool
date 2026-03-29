# Full Workflow Tutorial

This guide walks through a complete systematic literature review from start to finish.

## Overview

```
Step 1: Configure    →  Define your research scope in config.yaml
Step 2: Search       →  Query 3 databases automatically
Step 3: Deduplicate  →  Remove duplicate papers
Step 4: Screen       →  Keyword-based first pass
Step 5: AI Review    →  AI screens "maybe" papers (optional, needs MCP)
Step 6: Eligibility  →  AI applies stricter criteria (optional, needs MCP)
Step 7: Export       →  BibTeX + CSV + PRISMA diagram
```

---

## Step 1: Configure Your Review

Create `config.yaml` from the template:

```bash
cp config.template.yaml config.yaml
```

Edit it for your topic. Example for a review of "Deep Learning for Medical Image Segmentation":

```yaml
project:
  name: "DL Medical Image Segmentation Review"
  output_dir: "./prisma_output"

search:
  date_range:
    start: "2018-01-01"
    end: "2026-03-29"
  max_results_per_query: 500
  sources:
    - arxiv
    - openalex
    - semantic_scholar
  queries:
    - name: "dl_segmentation"
      terms: >
        ("deep learning" OR "convolutional neural network" OR "transformer")
        AND ("medical image segmentation" OR "biomedical image segmentation")
    - name: "specific_methods"
      terms: >
        ("U-Net" OR "SegNet" OR "DeepLab" OR "Swin-Unet" OR "TransUNet")
        AND ("medical" OR "clinical" OR "pathology")

screening:
  rules:
    include_keywords:
      - deep learning
      - segmentation
      - medical imaging
      - neural network
      - U-Net
      - transformer
      - clinical
    exclude_keywords:
      - remote sensing
      - autonomous driving
      - natural language
      - robotics
    min_include_hits: 2
```

---

## Step 2: Search Databases

```bash
python -m prisma_review search
```

**What happens:**
1. Tool sends your queries to each database (arXiv, OpenAlex, Semantic Scholar)
2. Results are normalized into a unified format
3. All papers saved to `prisma_output/01_search/all_records.json`

**Expected output:**
```
[SEARCH] Searching 3 source(s) with 2 query(ies)...
  Date range: 2018-01-01 to 2026-03-29

[SEARCH] Done! Total: 1247 papers from 3 source(s)
  arxiv: 312
  openalex: 800
  semantic: 135
  Saved to: prisma_output/01_search/all_records.json
```

**Troubleshooting:**
- If Semantic Scholar returns 0: the API may be rate-limiting you. Wait a few minutes and retry.
- If arXiv returns 0: your query may use operators arXiv doesn't support. Simplify it.
- If the total seems low: broaden your date range or relax query terms.

---

## Step 3: Deduplicate

```bash
python -m prisma_review dedup
```

**What happens:**
1. **Pass 1**: Exact DOI matching (normalized — removes URL prefixes, lowercases)
2. **Pass 2**: Fuzzy title matching (papers grouped by year, then compared within each year)
3. When duplicates are found, the version with the best metadata is kept

**Expected output:**
```
[DEDUP] Deduplicating 1247 papers...
[DEDUP] Done! Removed 89 duplicates, 1158 unique papers remaining
```

**Check the results:**
- Open `prisma_output/02_dedup/duplicates_log.csv` to see which papers were merged
- If you see false merges (different papers treated as duplicates), increase `fuzzy_title_threshold` in config.yaml

---

## Step 4: First-Pass Keyword Screening

```bash
python -m prisma_review screen-rules
```

**What happens:**
- Each paper's title + abstract is checked against your keywords
- Papers are classified as **include**, **exclude**, or **maybe**

**Decision logic:**
```
IF any exclude_keyword matches → EXCLUDE
ELIF count(include_keywords matched) >= min_include_hits → INCLUDE
ELSE → MAYBE (needs review)
```

**Expected output:**
```
[SCREEN] Screening 1158 papers with keyword rules...
[SCREEN] Done!
  Included: 423
  Excluded: 312
  Maybe (needs review): 423
```

**What to do with the results:**
- **Included**: Papers that clearly match your criteria
- **Excluded**: Papers that clearly don't match
- **Maybe**: Papers that partially match — these need manual or AI review

---

## Step 5: AI Review of "Maybe" Papers (Optional)

> Requires MCP setup. See [MCP & AI Screening](MCP-&-AI-Screening).

In your MCP-compatible agent (Claude Code, Codex, Copilot, etc.), say:

```
Screen my remaining 'maybe' papers using the prisma-review tools.
My research is about deep learning for medical image segmentation.
Include papers about: CNN/transformer architectures for segmentation,
medical imaging datasets, clinical validation of DL models.
Exclude papers about: non-medical applications, traditional methods
without deep learning, survey/review papers.
```

**What happens:**
1. Agent calls `get_papers_to_screen` to fetch batches of "maybe" papers
2. Agent reads each paper's title and abstract
3. Agent decides include/exclude based on your criteria
4. Agent calls `batch_screen_papers` to save decisions
5. Repeats until all "maybe" papers are processed

---

## Step 6: Eligibility Screening — Second Pass (Optional)

If Step 4+5 leaves too many included papers (e.g., 400+ is too many for manual full-text review), do a stricter second pass.

In your MCP agent, say:

```
Do eligibility screening on my included papers using prisma-review tools.
Apply stricter criteria: only include papers that are DIRECTLY about
deep learning architectures for medical image segmentation.
Exclude papers that are only tangentially related, such as general
computer vision papers that mention medical imaging briefly.
```

**What happens:**
1. Agent calls `get_papers_for_eligibility` to fetch first-pass included papers
2. Agent reads each paper's full abstract (not truncated)
3. Agent applies stricter criteria
4. Agent calls `batch_eligibility_screen` to save decisions
5. Results saved to `prisma_output/03b_eligibility/`

**Target:** Narrow to 50-80 papers for manual full-text review.

---

## Step 7: Generate Report & Export

```bash
python -m prisma_review report
python -m prisma_review export
```

Or ask your MCP agent: "Generate the PRISMA report using prisma-review tools."

**Outputs:**

| File | Purpose |
|------|---------|
| `prisma_flow.png` | PRISMA 2020 flow diagram (for thesis/paper) |
| `prisma_flow.md` | Same diagram as Markdown text |
| `included_papers.bib` | BibTeX for all first-pass included papers |
| `included_papers.csv` | CSV spreadsheet of first-pass included papers |
| `eligible_papers.bib` | BibTeX for final papers (after eligibility) |
| `eligible_papers.csv` | CSV spreadsheet of final papers |

**Using the BibTeX file:**
- Import into **Zotero**: File → Import → select `included_papers.bib`
- Use in **LaTeX**: Copy to your thesis directory, add `\bibliography{eligible_papers}`
- Import into **Mendeley**: File → Import → BibTeX

---

## Step 8: Check Status Anytime

```bash
python -m prisma_review status
```

```
[STATUS] Project: DL Medical Image Segmentation Review
  Output: ./prisma_output

  SEARCH: 1247 papers found
    arxiv: 312
    openalex: 800
    semantic: 135
  DEDUP: 89 duplicates removed, 1158 unique
  SCREEN: 423 included, 312 excluded, 423 maybe
  ELIGIBILITY: 67 included, 356 excluded, 0 remaining
```

---

## Complete Pipeline (One Command)

If you just want to run the automated steps without AI screening:

```bash
python -m prisma_review run-all
```

This runs: search → dedup → screen-rules → report → export

You can then use MCP for AI screening separately.

---

## Tips

1. **Save your config.yaml** — it IS your review protocol. Include it in your thesis supplementary materials.
2. **Check the dedup log** — false merges can lose important papers.
3. **Start broad, narrow later** — it's easier to exclude papers in the second pass than to re-run everything with broader queries.
4. **Use `status` often** — track your progress as you screen.
5. **Back up `prisma_output/`** — especially after AI screening. Decisions are stored in JSON files.
