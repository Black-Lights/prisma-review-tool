# Installation & Setup

## Requirements

- **Python 3.10+** (check with `python --version`)
- **Node.js 18+** (for the web app; not needed for CLI-only usage — check with `node --version`)
- **Git** (optional, for cloning)
- No API keys needed for basic usage

## Step 1: Get the Code

```bash
git clone https://github.com/Black-Lights/prisma-review-tool.git
cd prisma_tool
```

## Step 2: Launch

### Option A: Web App (Recommended)

```bash
python start.py
```

This single command handles everything:
1. Creates a Python virtual environment (`.venv/`)
2. Installs all Python dependencies (requirements.txt + uvicorn + fastapi)
3. Installs Node.js dependencies for the web frontend (`web/node_modules/`)
4. Creates `config.yaml` from the template if missing
5. Starts the API server and web frontend on available ports
6. Opens the dashboard in your browser

Press **Ctrl+C** to stop — both backend and frontend are killed automatically.

#### Launcher Options

| Flag | Description |
|------|-------------|
| `--install` | Force reinstall all dependencies |
| `--port 9000` | Set backend port (frontend = port + 1000) |
| `--no-browser` | Don't auto-open browser |
| `--cli` | CLI mode only — set up venv without starting the web app |

```bash
python start.py --port 9000        # Custom ports (9000 backend, 10000 frontend)
python start.py --no-browser       # Start without opening browser
python start.py --install          # Force reinstall everything
```

On subsequent runs, `start.py` skips installation (deps are cached) and starts in seconds.

### Option B: CLI Only

```bash
python start.py --cli
```

This creates the venv and installs Python deps, then prints activation instructions:

```bash
# Windows
.venv\Scripts\activate

# Mac/Linux
source .venv/bin/activate

# Run the pipeline
python -m prisma_review run-all
```

### Option C: Manual Setup

If you prefer full control:

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate
# Mac/Linux
source .venv/bin/activate

pip install -r requirements.txt

# For CLI usage
python -m prisma_review status

# For web app (two terminals)
pip install uvicorn fastapi python-multipart
uvicorn api.main:app --port 8000

# In a second terminal
cd web
npm install
NEXT_PUBLIC_API_URL=http://localhost:8000 npm run dev
```

## Dependencies

| Package | Purpose |
|---------|---------|
| `arxiv` | arXiv API search |
| `pyalex` | OpenAlex API search |
| `requests` | HTTP requests (Semantic Scholar, Scopus) |
| `pandas` | Data processing and CSV export |
| `pyyaml` | YAML config parsing |
| `rapidfuzz` | Fuzzy string matching for deduplication |
| `matplotlib` | PRISMA flow diagram generation |
| `mcp` | Model Context Protocol server |
| `uvicorn` | ASGI server for FastAPI (installed by start.py) |
| `fastapi` | REST API framework (installed by start.py) |

All dependencies are MIT/BSD/Apache 2.0 licensed.

## Step 3: Configure

```bash
cp config.template.yaml config.yaml
```

Or use the **Settings** page in the web app. See [Configuration Guide](Configuration-Guide) for details.

## Step 4: Verify

**Web app:** Open the URL shown by `start.py` (default: http://localhost:8000 for API, http://localhost:9000 for frontend).

**CLI:**
```bash
python -m prisma_review status
```

Expected output:
```
[STATUS] Project: Your Review Title Here
  Output: ./prisma_output
```

Next: [Full Workflow Tutorial](Full-Workflow-Tutorial)

## Optional: MCP Setup for AI Screening

If you want AI-assisted screening, see [MCP & AI Screening](MCP-and-AI-Screening).

## Updating

```bash
git pull
python start.py --install    # Reinstalls all deps
```

## Uninstalling

Delete the `prisma_tool` folder and its `.venv`. No system-wide changes are made.
