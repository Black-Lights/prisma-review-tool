# Troubleshooting & FAQ

## Common Issues

### Installation

**`ModuleNotFoundError: No module named 'prisma_review'`**

You're running Python from outside the prisma_tool directory, or the virtual environment isn't activated.

```bash
cd prisma_tool
source .venv/bin/activate    # Mac/Linux
.venv\Scripts\activate       # Windows
python -m prisma_review status
```

**`pip install` fails with permission errors**

Make sure you're using the virtual environment, not system Python:
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

### Search

**Semantic Scholar returns 0 results**

The Semantic Scholar API has aggressive rate limiting. Solutions:
- Wait 1-2 minutes and retry
- Reduce `max_results_per_query` in config.yaml
- The tool retries automatically (up to 3 times with backoff)

**arXiv returns 0 results**

arXiv's API doesn't support full Boolean syntax. The tool simplifies your query, but complex queries may not translate well. Try simpler queries for arXiv.

**OpenAlex returns too many irrelevant results**

OpenAlex uses text search, not strict Boolean matching. The screening step will filter irrelevant papers. This is by design — it's better to cast a wide net and filter than to miss papers.

**Search is very slow**

- Semantic Scholar: Throttled to ~1 request/second. Be patient.
- OpenAlex: Paginated at 50 results/page. Large result sets take time.
- arXiv: Generally fast, but can timeout during peak hours.

---

### Deduplication

**False merges — different papers treated as duplicates**

Increase `fuzzy_title_threshold` in config.yaml (e.g., from 90 to 95). Check `prisma_output/02_dedup/duplicates_log.csv` to see which papers were merged.

**Too many duplicates remaining**

Decrease `fuzzy_title_threshold` (e.g., from 90 to 85). This catches more title variations.

---

### Screening

**Too many papers in "maybe"**

Your include keywords are too narrow. Add more synonyms:
```yaml
include_keywords:
  - foundation model
  - pre-trained model        # Added synonym
  - self-supervised          # Added related term
```

Or decrease `min_include_hits` from 2 to 1 (but this may include too many papers).

**Too many papers included (e.g., 500+)**

This is normal for broad searches. Use the two-pass screening workflow:
1. First pass catches broadly relevant papers
2. Second pass (eligibility screening via MCP) narrows with stricter criteria

**Important papers are being excluded**

Check your `exclude_keywords` — they may be too broad. For example, `"model"` as an exclude keyword would exclude papers about "foundation models".

---

### MCP / AI Screening

**"Config file not found" error from MCP server**

The MCP server looks for `config.yaml` relative to the prisma_tool directory. Make sure:
1. You've created `config.yaml` from the template
2. The `cwd` in your MCP config points to the prisma_tool directory

**Agent can't find the MCP tools**

1. Check the config file is in the correct location for your agent
2. Paths must use forward slashes (even on Windows): `C:/Users/...` not `C:\Users\...`
3. The Python path must point to `.venv/Scripts/python.exe` (Windows) or `.venv/bin/python` (Mac/Linux)
4. Restart the agent after adding/changing the config

**Agent stops mid-screening**

The agent's context window may fill up after processing many papers. Just ask it to continue — the tool tracks which papers have been screened, so it picks up where it left off.

**Want to undo/change an AI decision**

Edit the JSON files directly:
- First pass: `prisma_output/03_screen/screen_results.json`
- Eligibility: `prisma_output/03b_eligibility/eligibility_results.json`

Change `screen_decision` or `eligibility_decision` and set the method to `"manual"`.

Then regenerate the split files:
```bash
python -m prisma_review screen-rules   # Re-splits into included/excluded/maybe
python -m prisma_review report         # Regenerates diagram
```

---

### Export

**BibTeX file has formatting issues**

The BibTeX export uses basic formatting. For best results, import into a reference manager (Zotero, Mendeley) and re-export.

**CSV doesn't open correctly in Excel**

The CSV uses UTF-8 encoding. In Excel: File → Open → select the CSV → choose "UTF-8" as the encoding.

---

## FAQ

### Can I use this tool for any research topic?

Yes. The tool is topic-agnostic — you define your search queries and screening criteria in config.yaml. See [Examples](https://github.com/Black-Lights/prisma-review-tool/blob/main/docs/EXAMPLES.md) for configs across different fields.

### Does AI screening cost money?

No additional cost beyond your existing AI agent subscription. The MCP integration uses your agent's capabilities directly — no API calls or tokens are billed separately.

### Is the screening reproducible?

Partially. The search, dedup, and keyword screening steps are fully reproducible (same config = same results). AI screening may produce slightly different decisions across sessions due to model stochasticity, but all decisions are logged for transparency.

### How many papers can it handle?

Tested with 1,600+ papers. The tool processes papers in batches, so memory usage stays low. AI screening of 965 papers was completed in a single session.

### Can I add more databases?

Yes. Create a new file in `prisma_review/search/` following the pattern of `arxiv_search.py`, then register it in `runner.py`. See [CONTRIBUTING.md](https://github.com/Black-Lights/prisma-review-tool/blob/main/CONTRIBUTING.md).

### Can multiple people screen papers?

Currently, the tool is single-user (decisions are stored in local files). Multi-user support is planned for the v2.0 web UI.

### How do I cite this tool?

```bibtex
@software{prisma_tool,
  author = {Mughees, Mohammad Ammar},
  title = {PRISMA Review Tool: AI-Assisted Systematic Literature Review},
  year = {2026},
  url = {https://github.com/Black-Lights/prisma-review-tool},
  license = {MIT}
}
```

### Can I use this for a Cochrane review?

The tool supports PRISMA 2020, which Cochrane reviews follow. However, Cochrane has additional requirements (risk of bias assessment, RevMan integration) that are beyond the scope of this tool. You would use prisma_tool for search and screening, then switch to RevMan for later stages.
