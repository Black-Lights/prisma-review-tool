# Installation & Setup

## Requirements

- **Python 3.10+** (check with `python --version`)
- **pip** (comes with Python)
- **Git** (optional, for cloning)
- No API keys needed for basic usage

## Step 1: Get the Code

```bash
# Clone from GitHub
git clone https://github.com/Black-Lights/prisma-review-tool.git
cd prisma_tool

# Or download and extract the ZIP
```

## Step 2: Create Virtual Environment

```bash
python -m venv .venv
```

Activate it:

```bash
# Windows (Command Prompt)
.venv\Scripts\activate

# Windows (PowerShell)
.venv\Scripts\Activate.ps1

# Mac/Linux
source .venv/bin/activate
```

You should see `(.venv)` in your terminal prompt.

## Step 3: Install Dependencies

```bash
pip install -r requirements.txt
```

This installs:
| Package | Purpose |
|---------|---------|
| `arxiv` | arXiv API search |
| `pyalex` | OpenAlex API search |
| `requests` | HTTP requests (Semantic Scholar) |
| `pandas` | Data processing and CSV export |
| `pyyaml` | YAML config parsing |
| `rapidfuzz` | Fuzzy string matching for deduplication |
| `matplotlib` | PRISMA flow diagram generation |
| `mcp` | Model Context Protocol server |

All dependencies are MIT/BSD/Apache 2.0 licensed.

## Step 4: Create Your Config

```bash
cp config.template.yaml config.yaml
```

Edit `config.yaml` with your research topic. See [Configuration Guide](Configuration-Guide) for details.

## Step 5: Verify Installation

```bash
python -m prisma_review status
```

Expected output:
```
[STATUS] Project: Your Review Title Here
  Output: ./prisma_output
```

If you see this, you're ready to go. Next: [Full Workflow Tutorial](Full-Workflow-Tutorial)

## Optional: MCP Setup for AI Screening

If you want AI-assisted screening, see [MCP & AI Screening](MCP-&-AI-Screening).

## Updating

```bash
git pull
pip install -r requirements.txt
```

## Uninstalling

Delete the `prisma_tool` folder and its `.venv`. No system-wide changes are made.
