"""CLI entry point for PRISMA Review Tool."""

from __future__ import annotations

import argparse
import sys

from . import pipeline
from .config import Config
from .models import load_papers
from .pipeline import RunActiveError, StepError
from .screen import rescreen
from .stats import project_stats
from .storage import atomic_write_json
from .export import export_bibtex, export_csv
from .download import download_papers
from .diagram import generate_markdown_diagram, generate_png_diagram, load_state


def cmd_search(config: Config) -> None:
    """Run search queries across all configured databases."""
    print(f"[SEARCH] Searching {len(config.sources)} source(s) with {len(config.queries)} query(ies)...")
    print(f"  Date range: {config.date_start} to {config.date_end}")

    # Transparency: how each source handles the query and the configured
    # filters (server-side vs applied locally vs ignored).
    for w in pipeline.pre_search_warnings(config):
        print(f"  [!] {w}")

    outcome = pipeline.search_step(config)
    source_counts = outcome["sources"]

    print(f"\n[SEARCH] Done! Total: {outcome['total']} papers from {len(source_counts)} source(s)")
    for src, count in source_counts.items():
        print(f"  {src}: {count}")
    for w in outcome["warnings"]:
        print(f"  [!] {w}")
    print(f"  Saved to: {config.search_dir / 'all_records.json'}")


def cmd_dedup(config: Config) -> None:
    """Remove duplicate papers."""
    print(f"[DEDUP] Deduplicating {config.search_dir / 'all_records.json'}...")
    try:
        result = pipeline.dedup_step(config)
    except StepError:
        print("[DEDUP] No papers found. Run 'search' first.")
        return

    print(f"[DEDUP] Done! Removed {result['duplicates_removed']} duplicates, "
          f"{result['remaining']} unique papers remaining")
    print(f"  Saved to: {config.dedup_dir / 'deduplicated.json'}")
    if result["duplicates_removed"]:
        print(f"  Duplicate log: {config.dedup_dir / 'duplicates_log.csv'}")


def cmd_screen_rules(config: Config) -> None:
    """Apply keyword-based screening rules (manual and AI decisions are kept)."""
    print(f"[SCREEN] Screening with keyword rules (min_include_hits = {config.min_include_hits})...")
    try:
        result = rescreen(config, persist_threshold=False)
    except StepError:
        print("[SCREEN] No papers found. Run 'dedup' first.")
        return
    except (RunActiveError, ValueError) as exc:
        print(f"[SCREEN] {exc}")
        return

    print(f"[SCREEN] Done!")
    print(f"  Included: {result['included']}")
    print(f"  Excluded: {result['excluded']}")
    if result["excluded_no_required_keyword"]:
        print(f"    (of which {result['excluded_no_required_keyword']} by required-keyword rule)")
    print(f"  Maybe (needs review): {result['maybe']}")
    if result["kept_manual"] or result["kept_ai"]:
        print(f"  Kept {result['kept_manual']} manual and {result['kept_ai']} AI decision(s)")
    if result["eligibility_dropped"]:
        print(f"  Dropped {result['eligibility_dropped']} eligibility decision(s) about papers "
              f"no longer included")


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
    print(f"    Screened: {flow['screened']} ({flow['screening_excluded']} excluded, "
          f"{flow['awaiting_screening']} awaiting screening)")
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

    cmd_search(config)
    print()
    cmd_dedup(config)
    print()
    cmd_screen_rules(config)
    print()
    cmd_report(config)
    print()
    cmd_export(config)
    print()
    print("=" * 60)
    print("Pipeline complete!")
    cmd_status(config)


def main():
    parser = argparse.ArgumentParser(
        prog="prisma-review",
        description="PRISMA Review Tool - Automated systematic literature review",
    )
    parser.add_argument("command", choices=["search", "dedup", "screen-rules", "report", "export", "download", "status", "run-all"],
                        help="Command to run")
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml (default: config.yaml)")
    parser.add_argument("--force", action="store_true", help="Re-run step even if output exists")

    args = parser.parse_args()

    try:
        config = Config.load(args.config)
    except FileNotFoundError as e:
        print(f"Error: {e}")
        sys.exit(1)

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
