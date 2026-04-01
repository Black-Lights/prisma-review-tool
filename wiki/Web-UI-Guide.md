# Web UI Guide

The PRISMA Review Tool includes a full web dashboard for managing your systematic literature review. This guide covers every page, feature, and workflow available in the web interface.

## Getting Started

### Starting the App

```bash
cd prisma-review-tool
python start.py
```

This installs all dependencies (first run only), starts both the API server and web frontend, and opens the dashboard in your browser. Press **Ctrl+C** to stop.

See [Installation & Setup](Installation-and-Setup) for all launcher options (`--port`, `--no-browser`, etc.).

### First-Time Tutorial

When you open the app for the first time, an interactive guided tour walks you through all 7 pages with 17 steps. The tutorial highlights each UI element with a glassmorphism chat bubble explaining what it does.

- **Skip**: Click "Skip Tutorial" at any time
- **Restart**: Click the **"Take Tour"** button at the bottom of the sidebar
- The tutorial auto-navigates between pages as you click "Next"

---

## Pages

### 1. Dashboard (`/`)

The dashboard is your home page — it shows the current state of your review at a glance.

#### Stat Cards (top row)

Four cards showing key numbers from your pipeline:

| Card | What it shows |
|------|--------------|
| **Records Found** | Total papers found across all database searches |
| **After Dedup** | Papers remaining after duplicate removal |
| **First Pass Included** | Papers that passed keyword screening |
| **Final Eligible** | Papers that passed eligibility screening (2nd pass) |

When the pipeline is running, cards show `--` until their step completes. Stats refresh every 5 seconds during a run.

#### PRISMA 2020 Flow Diagram (left column)

An interactive flow diagram matching the official PRISMA 2020 template (Page et al., BMJ 2021;372:n71). It includes:

- **Identification phase**: Records identified from databases, records removed before screening (duplicates + automation exclusions)
- **Screening phase**: Records screened, records excluded, reports sought for retrieval, reports not retrieved, reports assessed for eligibility, reports excluded with reasons
- **Included phase**: Final studies included in review

The diagram **auto-updates** whenever you screen papers or run the pipeline. Click **"Download PNG"** to save a high-resolution image (3x pixel ratio) for your thesis or paper.

#### Pipeline Stepper (right column)

A vertical stepper showing the 5 pipeline stages:

1. **Search Databases** — query arXiv, OpenAlex, Semantic Scholar
2. **Deduplicate** — remove duplicate papers (DOI + fuzzy title matching)
3. **Keyword Screening** — apply include/exclude keyword rules
4. **Eligibility** — manual or AI-assisted second pass
5. **Export & Download** — generate reports and download PDFs

Each step shows a status icon:
- Gray circle = pending
- Animated blue dot = currently running
- Green checkmark = completed

The **"Run All"** button starts the pipeline (search + dedup + screen) in the background. You can navigate to other pages while it runs. The **"Stop"** button cancels after the current step finishes.

#### Pipeline Progress Bar

When the pipeline is running, a progress bar appears showing:
- Current step name and elapsed time
- A "Stop" button with confirmation modal
- Warning indicators if any sources were rate-limited

---

### 2. Screening (`/screening`)

The screening page is where you review papers that need manual decisions.

#### How it works

After the pipeline runs keyword screening, papers are classified as:
- **Included**: Matched enough include keywords
- **Excluded**: Matched an exclude keyword
- **Maybe**: Didn't clearly match either way — needs your review

#### Features

- **Search bar**: Search papers by title, author, or keyword
- **Filter pills**: Switch between All, Maybe, Included, Excluded views
- **Paper cards**: Each card shows title (clickable link to detail page), authors, year, source badge, and truncated abstract
- **Show More / Show Less**: Expand or collapse the full abstract
- **Include / Exclude buttons**: Make a screening decision with an optional reason
- **Load More**: Load additional papers (20 at a time)

#### Tips

- Start with the "Maybe" filter — these are the papers that need your attention
- Read the abstract before deciding. Use "Show More" to see the full text
- Add a brief reason for each decision — this is documented for PRISMA compliance
- Decisions are saved immediately and update the pipeline stats

---

### 3. Eligibility (`/eligibility`)

The eligibility page is for second-pass screening — applying stricter criteria to first-pass included papers.

#### When to use it

After keyword screening includes too many papers (e.g., 200+), use eligibility screening to narrow down to only the most relevant studies for full-text review. Target: 50-80 final papers.

#### Features

- **Progress bar**: Shows how many papers you've screened out of the total
- **"Remaining" badge**: Number of papers still needing review
- **Paper cards**: Same as screening page, but also shows first-pass screening info (which keywords matched)
- **Load More**: Load additional papers in batches

#### Eligibility vs Screening

| | Screening (Pass 1) | Eligibility (Pass 2) |
|---|---|---|
| **Input** | All deduplicated papers | First-pass included papers only |
| **Criteria** | Keyword matching (automated) | Your domain-specific criteria |
| **Goal** | Remove obviously irrelevant papers | Narrow to most relevant studies |
| **Method** | Automated + manual review of "maybe" | Manual or AI-assisted |

---

### 4. All Papers (`/papers`)

Browse, search, and filter your entire paper collection.

#### Features

- **Search**: Full-text search across titles, abstracts, and keywords
- **Decision filter**: All, Included (1st pass), Excluded, Maybe, Eligible: Included, Eligible: Excluded
- **Source filter**: Filter by database (OpenAlex, arXiv, Semantic Scholar)
- **Pagination**: Navigate through pages of 25 papers each
- **Export buttons**: Download as CSV or BibTeX directly from this page
- **Clickable titles**: Click any paper title to view full details

#### Paper Detail Page (`/papers/[id]`)

Click a paper title from any page to see its full details:

- Title, authors, year, venue
- DOI (clickable link)
- Source database badge
- Full abstract (not truncated)
- Keywords
- Screening decision, reason, and method (rule/ai/manual)
- Eligibility decision, reason, and method
- "Go Back" button returns to the page you came from (preserves scroll position)

---

### 5. Settings (`/settings`)

Configure your entire review protocol — search queries, screening keywords, and database sources.

#### Sections

**Project**
- Project name and output directory

**Search Configuration**
- **Date range**: Start and end dates for your search
- **Max results per query**: Cap the number of results per source (default 500)
- **Sources**: Toggle databases on/off. Each source shows reliability info:
  - OpenAlex: "250M+ papers, most reliable" (recommended)
  - arXiv: "Rate-limits aggressively, may return partial results"
  - Semantic Scholar: "Heavy rate limits, often returns 0 results"
  - Scopus: "Requires API key"

**Search Queries**
- Add/remove Boolean search queries
- Each query has a name and terms field
- Use AND/OR operators: `("term A" OR "term B") AND "context"`
- Queries are sent to all enabled databases

**Screening Rules**
- **Include keywords**: Papers must match at least `min_include_hits` of these
- **Exclude keywords**: Papers matching any of these are auto-excluded
- **Minimum include hits**: How many include keywords must match (default 2)

**Save / Reset**
- Click "Save Configuration" to persist changes to config.yaml
- Click "Reset" to revert to the last saved state

---

### 6. Downloads (`/downloads`)

Download open access PDFs and view them directly in the app.

#### How it works

1. Click **"Start Download"** — the app tries to download PDFs for your eligible papers (or included papers if no eligibility screening was done)
2. Download strategies (tried in order):
   - **Elsevier/ScienceDirect** (if Scopus API key configured) — covers paywalled journals your institution subscribes to
   - **arXiv** — free preprints
   - **Unpaywall** — finds legal open access versions
   - **Semantic Scholar** — last resort OA check
3. Papers without any available source are marked "No Open Access"

#### Features

- **Filter pills**: All, Downloaded, No OA (no open access), Failed — with counts
- **Paper table**: Status icon, title, DOI link, and actions for each paper
- **View button**: Opens an inline PDF viewer directly on the page using the browser's native PDF renderer
- **PDF viewer toolbar**: Page navigation, zoom, print, "Open in new tab", and Close
- **Re-download button**: Run the download again (skips already-downloaded papers)

#### Status Types

| Status | Meaning |
|--------|---------|
| Downloaded | PDF successfully downloaded and available to view |
| No Open Access | No version found (not on arXiv, Unpaywall, S2, or Elsevier with your key) |
| Failed | Download attempted but failed (network error, invalid URL) |

---

### 7. Projects (`/projects`)

Manage multiple literature review projects from a single installation.

#### Features

- **Project cards**: Each project shows its name, slug, paper counts (search, dedup, screened, eligible), and an "Active" badge
- **Create**: Click "New Project" to create a new review with a fresh config from the template
- **Switch**: Click "Switch" on any project card to load its config and data — all dashboard stats, screening decisions, and pipeline state switch instantly
- **Duplicate**: Clone an existing project (copies config + all data) to start a similar review
- **Export**: Download a project as a `.zip` archive for backup or sharing
- **Import**: Upload a `.zip` to create a new project from an archive
- **Delete**: Remove a project with confirmation modal (irreversible)

#### How it works

Each project is an isolated directory under `projects/`:
```
projects/
├── gfm-agriculture/
│   ├── config.yaml
│   └── prisma_output/
├── dl-medical/
│   ├── config.yaml
│   └── prisma_output/
└── .active_project
```

On first run, if you already have a `config.yaml` and `prisma_output/` at the repo root, they are **automatically migrated** into a new project directory. The originals are preserved for CLI backward compatibility.

#### Switching projects

When you switch projects:
1. The backend reloads the new project's config
2. The session manager resets (new pipeline state)
3. All frontend queries are invalidated — stats, papers, and pipeline status refresh
4. The pipeline cannot be running when you switch (the UI blocks this)

---

### 8. MCP Settings (`/mcp-settings`)

Configure AI agent connections for automated paper screening.

#### What is MCP?

Model Context Protocol (MCP) is an open standard that lets AI agents use external tools. The PRISMA Review Tool exposes 15 MCP tools that any compatible AI agent can use to search, screen, and manage your review.

#### Supported Agents

The page shows configuration snippets for:
- Claude Code (JSON)
- OpenAI Codex (TOML)
- GitHub Copilot (JSON)
- Cursor (JSON)
- Windsurf (JSON)
- Amazon Q (JSON)

Each snippet can be copied with one click.

---

## Navigation & UX Features

### Sidebar

The sidebar provides navigation to all 8 pages. The currently active page is highlighted in cyan.

- **Active project indicator**: Below the logo, a compact card shows the name of the current project. Click it to go to the Projects page.
- **"Take Tour"** button: Restart the interactive tutorial at any time
- Version number and GitHub link

### Scroll Restoration

When you navigate to a paper detail page and click "Go Back", the app returns to your exact scroll position on the previous page. This works across all list pages (Screening, Eligibility, All Papers).

### URL-Persisted State

Page numbers, filters, and batch sizes are saved in the URL (e.g., `/papers?page=3&decision=include`). This means:
- Refreshing the page preserves your current view
- The browser's back/forward buttons work correctly
- Bookmarking a filtered view works

### Dark Glassmorphism Theme

The entire app uses a dark theme with glassmorphism design:
- Background: `#0a0e1a` (deep navy)
- Text: `#e0e8f0` (off-white)
- Primary accent: `#7dd3fc` (cyan)
- Glass cards: semi-transparent with backdrop blur and subtle borders
- Status colors: green (success), amber (warning), red (error), purple (eligibility)

---

## Screenshots

> **Note**: Add screenshots of each page to this wiki for visual reference. Recommended screenshots:
>
> 1. Dashboard — full page showing stat cards, PRISMA diagram, and pipeline stepper
> 2. Dashboard — pipeline running with progress bar and animated stepper
> 3. Screening — paper cards with filter pills and search bar
> 4. Eligibility — papers with first-pass info badges and progress bar
> 5. All Papers — table view with filters and pagination
> 6. Paper Detail — full paper view with all metadata
> 7. Settings — search queries and screening rules sections
> 8. Downloads — PDF viewer showing a paper inline
> 9. Tutorial — welcome step with dark overlay
> 10. Tutorial — highlighted element with bubble card and arrow
>
> To add screenshots to the GitHub wiki:
> 1. Take a screenshot of each page
> 2. Upload to the wiki by dragging into the editor, or use `![Alt text](url)`
> 3. Replace the placeholder notes above with actual images

---

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| Escape | Close modal dialogs, close PDF viewer |

---

## Troubleshooting

See [Troubleshooting & FAQ](Troubleshooting-and-FAQ) for common issues including:
- Dashboard shows stale numbers
- PDF viewer shows "Failed to fetch"
- Filters not working
- Pipeline seems stuck
