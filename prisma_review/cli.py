"""CLI entry point for PRISMA Review Tool."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Callable

from . import pipeline, workspace
from .config import Config
from .models import load_papers
from .pipeline import ClaimedRun, RunActiveError, StepError
from .screen import rescreen
from .stats import project_stats
from .storage import atomic_write_json
from .export import export_bibtex, export_csv
from .download import download_papers
from .diagram import generate_markdown_diagram, generate_png_diagram, load_state


def _claimed(config: Config, label: str, run: ClaimedRun | None,
             body: Callable[[ClaimedRun], bool]) -> bool:
    """Run ``body`` inside ``run``, or inside a run claimed for this command.

    A command that changes the results records its run on the project like
    the web app and the MCP server do, so neither starts a pipeline over it,
    and it refuses to start while one of theirs is running.
    """
    if run is not None:
        return body(run)
    try:
        with pipeline.claimed_run(config, "cli") as claimed:
            return body(claimed)
    except RunActiveError as exc:
        print(f"[{label}] {exc} Nothing was changed; try again when it has finished.")
        return False


def cmd_search(config: Config, run: ClaimedRun | None = None) -> bool:
    """Run search queries across all configured databases. False if the search failed."""
    return _claimed(config, "SEARCH", run, lambda r: _search(config, r))


def _search(config: Config, run: ClaimedRun) -> bool:
    print(f"[SEARCH] Searching {len(config.sources)} source(s) with {len(config.queries)} query(ies)...")
    print(f"  Date range: {config.date_start} to {config.date_end}")

    # Transparency: config warnings (e.g. OpenAlex without a key), then how
    # each source handles the query and the configured filters (server-side
    # vs applied locally vs ignored).
    for w in config.readiness()["warnings"] + pipeline.pre_search_warnings(config):
        print(f"  [!] {w}")

    run.step("search", "Searching databases...")
    outcome = pipeline.search_step(config, should_cancel=run.should_cancel)
    source_counts = outcome["sources"]
    if outcome["status"] == "cancelled":
        print("\n[SEARCH] Stopped (a Stop was requested from the web app or the MCP server). "
              "Nothing was saved; the previous results were kept.")
        run.finish("cancelled", "Pipeline cancelled during search; the previous results were kept")
        return False
    if outcome["status"] == "failed":
        for w in outcome["warnings"]:
            print(f"  [!] {w}")
        print(f"\n[SEARCH] Failed. {outcome['error']}")
        run.finish("failed", f"Error in step 'search': {outcome['error']}", outcome["error"])
        return False

    print(f"\n[SEARCH] Done! Total: {outcome['total']} papers from {len(source_counts)} source(s)")
    for src, count in source_counts.items():
        print(f"  {src}: {count}")
    for w in outcome["warnings"]:
        print(f"  [!] {w}")
    print(f"  Saved to: {config.search_dir / 'all_records.json'}")
    run.step_done("search", {"status": "ok", "total": outcome["total"], "sources": source_counts},
                  outcome["warnings"])
    return True


def cmd_dedup(config: Config, run: ClaimedRun | None = None) -> bool:
    """Remove duplicate papers. False if there was nothing to deduplicate."""
    return _claimed(config, "DEDUP", run, lambda r: _dedup(config, r))


def _dedup(config: Config, run: ClaimedRun) -> bool:
    print(f"[DEDUP] Deduplicating {config.search_dir / 'all_records.json'}...")
    run.step("dedup", "Removing duplicates...")
    try:
        result = pipeline.dedup_step(config)
    except StepError as exc:
        print("[DEDUP] No papers found. Run 'search' first.")
        run.finish("failed", f"Error in step 'dedup': {exc}", str(exc))
        return False

    print(f"[DEDUP] Done! Removed {result['duplicates_removed']} duplicates, "
          f"{result['remaining']} unique papers remaining")
    print(f"  Saved to: {config.dedup_dir / 'deduplicated.json'}")
    if result["duplicates_removed"]:
        print(f"  Duplicate log: {config.dedup_dir / 'duplicates_log.csv'}")
    run.step_done("dedup", result)
    return True


def cmd_screen_rules(config: Config, run: ClaimedRun | None = None) -> bool:
    """Apply keyword-based screening rules (manual and AI decisions are kept).

    On its own it refuses while a pipeline runs on the project; inside the
    CLI's own run (``run``) it is that run's screening step.
    """
    print(f"[SCREEN] Screening with keyword rules (min_include_hits = {config.min_include_hits})...")
    if run is not None:
        run.step("screen", "Keyword screening...")
    try:
        result = rescreen(config, persist_threshold=False, check_running=run is None)
    except StepError as exc:
        print("[SCREEN] No papers found. Run 'dedup' first.")
        if run is not None:
            run.finish("failed", f"Error in step 'screen': {exc}", str(exc))
        return False
    except (RunActiveError, ValueError) as exc:
        print(f"[SCREEN] {exc}")
        if run is not None:
            run.finish("failed", f"Error in step 'screen': {exc}", str(exc))
        return False

    print(f"[SCREEN] Done!")
    print(f"  Included: {result['included']}")
    print(f"  Excluded: {result['excluded']}")
    if result["excluded_no_required_keyword"]:
        print(f"    (of which {result['excluded_no_required_keyword']} by required-keyword rule)")
    print(f"  Maybe (needs review): {result['maybe']}")
    if result["kept_manual"] or result["kept_ai"]:
        print(f"  Kept {result['kept_manual']} manual and {result['kept_ai']} AI decision(s)")
    if result["eligibility_set_aside"]:
        print(f"  {result['eligibility_set_aside']} eligibility decision(s) set aside: their papers "
              f"are no longer included (kept on file, restored if they are included again)")
    if run is not None:
        run.step_done("screen", result)
    return True


def cmd_report(config: Config) -> None:
    """Generate PRISMA flow diagram."""
    state = load_state(config.state_file)
    if not state:
        print("[REPORT] No state found. Run the pipeline first.")
        return

    print("[REPORT] Generating PRISMA flow diagram...")
    flow = project_stats(config, state)["flow"]
    generate_markdown_diagram(flow, config.export_dir / "prisma_flow.md")
    generate_png_diagram(flow, config.export_dir / "prisma_flow.png")

    print(f"  Markdown: {config.export_dir / 'prisma_flow.md'}")
    print(f"  PNG: {config.export_dir / 'prisma_flow.png'}")
    for note in flow["notes"]:
        print(f"  [!] {note}")


def cmd_export(config: Config) -> None:
    """Export included papers to .bib and .csv."""
    papers = load_papers(config.screen_dir / "included.json")
    if not papers:
        print("[EXPORT] No included papers found. Run 'screen-rules' first.")
        return

    print(f"[EXPORT] Exporting {len(papers)} first-pass included papers...")
    export_bibtex(papers, config.export_dir / "included_papers.bib")
    export_csv(papers, config.export_dir / "included_papers.csv")
    print(f"  BibTeX: {config.export_dir / 'included_papers.bib'}")
    print(f"  CSV: {config.export_dir / 'included_papers.csv'}")

    # Also export eligibility-screened papers if they exist
    eligible = load_papers(config.eligibility_dir / "eligible_included.json")
    if eligible:
        print(f"[EXPORT] Exporting {len(eligible)} eligible papers (second pass)...")
        export_bibtex(eligible, config.export_dir / "eligible_papers.bib")
        export_csv(eligible, config.export_dir / "eligible_papers.csv")
        print(f"  BibTeX: {config.export_dir / 'eligible_papers.bib'}")
        print(f"  CSV: {config.export_dir / 'eligible_papers.csv'}")


def cmd_download(config: Config) -> None:
    """Download open access PDFs for eligible papers."""
    # Prefer eligible papers, fall back to first-pass included
    papers = load_papers(config.eligibility_dir / "eligible_included.json")
    source = "eligible"
    if not papers:
        papers = load_papers(config.screen_dir / "included.json")
        source = "included"

    if not papers:
        print("[DOWNLOAD] No papers found. Run screening first.")
        return

    pdf_dir = config.output_dir / "05_pdfs"
    print(f"[DOWNLOAD] Downloading open access PDFs for {len(papers)} {source} papers...")
    print(f"  Output: {pdf_dir}")
    print(f"  Only open access papers will be downloaded (arXiv, Unpaywall, Semantic Scholar)")
    print()

    stats = download_papers(papers, pdf_dir, email=config.openalex_email, api_key=config.scopus_key)

    print()
    print(f"[DOWNLOAD] Done!")
    print(f"  Downloaded: {stats['downloaded']}")
    print(f"  No open access: {stats['no_open_access']}")
    print(f"  Failed: {stats['failed']}")
    print(f"  Saved to: {pdf_dir}")

    # Save download log
    log_path = pdf_dir / "_download_log.json"
    atomic_write_json(log_path, stats["results"], indent=2, ensure_ascii=False)
    print(f"  Log: {log_path}")


def cmd_status(config: Config) -> None:
    """Show current pipeline status."""
    state = load_state(config.state_file)
    if not state:
        print("[STATUS] No pipeline state found. Run 'search' to start.")
        return

    print(f"[STATUS] Project: {config.project_name}")
    print(f"  Output: {config.output_dir}")
    print()

    if "search" in state:
        s = state["search"]
        print(f"  SEARCH: {s.get('total', 0)} papers found")
        for k, v in s.items():
            if k != "total":
                print(f"    {k}: {v}")

    if "dedup" in state:
        d = state["dedup"]
        print(f"  DEDUP: {d.get('duplicates_removed', 0)} duplicates removed, {d.get('remaining', 0)} unique")

    computed = project_stats(config, state)
    if computed["screen"]:
        sc = computed["screen"]
        print(f"  SCREEN: {sc.get('included', 0)} included, {sc.get('excluded', 0)} excluded, {sc.get('maybe', 0)} maybe")
        if sc.get("excluded_no_required_keyword"):
            print(f"    (of the excluded, {sc['excluded_no_required_keyword']} by required-keyword rule)")

    if computed["eligibility"]:
        el = computed["eligibility"]
        print(f"  ELIGIBILITY: {el.get('included', 0)} included, {el.get('excluded', 0)} excluded, {el.get('remaining', 0)} remaining")

    flow = computed["flow"]
    removed = flow["removed_before_screening"]
    print()
    print("  PRISMA 2020 flow:")
    print(f"    Identified: {flow['identified']['total']}")
    print(f"    Removed before screening: {removed['duplicates']} duplicates, "
          f"{removed['automation_ineligible']} by automation tools")
    if flow["awaiting_screening"]:
        print(f"    Not yet screened: {flow['awaiting_screening']} (no screening decision recorded)")
    screened = f"    Screened: {flow['screened']} ({flow['screening_excluded']} excluded"
    if flow.get("included_by_automation"):
        screened += f"; {flow['included_by_automation']} included by the keyword rules, no reviewer"
    print(screened + ")")
    print(f"    Sought for retrieval: {flow['sought_for_retrieval']}")
    print(f"    Assessed for eligibility: {flow['assessed_for_eligibility']} "
          f"({flow['eligibility_excluded']} excluded, {flow['awaiting_eligibility']} awaiting)")
    print(f"    Included: {flow['included']}")


def cmd_run_all(config: Config) -> None:
    """Run the full pipeline."""
    print("=" * 60)
    print(f"PRISMA Review Tool - Full Pipeline")
    print(f"Project: {config.project_name}")
    print("=" * 60)

    def steps(run: ClaimedRun) -> bool:
        if not cmd_search(config, run):
            print("Pipeline stopped: the search did not finish, nothing was changed.")
            return False
        print()
        if not cmd_dedup(config, run):
            return False
        print()
        return cmd_screen_rules(config, run)

    if not _claimed(config, "PIPELINE", None, steps):
        return
    print()
    cmd_report(config)
    print()
    cmd_export(config)
    print()
    print("=" * 60)
    print("Pipeline complete!")
    cmd_status(config)


def resolve_cli_config(arg: str | None) -> Path:
    """The config the CLI uses: --config, else the review the web app and MCP server use.

    Without --config: PRISMA_CONFIG, then a config.yaml in the current folder
    when that folder is not the workspace and PRISMA_WORKSPACE is not set
    (running the CLI from a review folder of its own), then the active
    project, then the root config.yaml (only when no project exists).
    Raises workspace.WorkspaceError.
    """
    if arg:
        return Path(arg)
    if workspace.pinned_config_path() is None and not os.environ.get(workspace.ENV_WORKSPACE, "").strip():
        here = Path.cwd() / "config.yaml"
        if here.is_file() and os.path.normcase(str(Path.cwd().resolve()))                 != os.path.normcase(str(workspace.workspace_root())):
            return here.resolve()
    return workspace.resolve_config_path()


def _describe_choice(arg: str | None, path: Path) -> str:
    if arg:
        return "--config"
    try:
        res = workspace.resolve()
    except workspace.WorkspaceError:
        return "config.yaml in the current folder"
    if os.path.normcase(str(res.config_path)) != os.path.normcase(str(path)):
        return "config.yaml in the current folder"
    return {"env": workspace.ENV_CONFIG, "marker": f"active project '{res.project}'",
            "root": "root config.yaml, no project"}[res.source]


def main(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(
        prog="prisma-review",
        description="PRISMA Review Tool - Automated systematic literature review",
    )
    parser.add_argument("command", choices=["search", "dedup", "screen-rules", "report", "export", "download", "status", "run-all"],
                        help="Command to run")
    parser.add_argument("--config", default=None,
                        help="Path to a config.yaml (default: the review the web app and the MCP "
                             "server use: PRISMA_CONFIG, else the active project, else config.yaml)")
    parser.add_argument("--force", action="store_true", help="Re-run step even if output exists")

    args = parser.parse_args(argv)

    try:
        path = resolve_cli_config(args.config)
        config = Config.load(path)
    except (FileNotFoundError, workspace.WorkspaceError, ValueError) as e:
        print(f"Error: {e}")
        sys.exit(1)
    print(f"Config: {path} ({_describe_choice(args.config, path)})")
    if not args.config:
        notice = workspace.root_config_notice()
        if notice:
            print(f"  [!] {notice}")

    commands = {
        "search": cmd_search,
        "dedup": cmd_dedup,
        "screen-rules": cmd_screen_rules,
        "report": cmd_report,
        "export": cmd_export,
        "download": cmd_download,
        "status": cmd_status,
        "run-all": cmd_run_all,
    }

    commands[args.command](config)


if __name__ == "__main__":
    main()
