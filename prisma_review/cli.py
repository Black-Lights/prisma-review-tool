"""CLI entry point for PRISMA Review Tool."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .config import Config
from .models import Paper, save_papers, load_papers
from .search.runner import run_all_searches
from .dedup import deduplicate, save_dedup_log
from .screen import screen_by_rules, get_by_decision
from .export import export_bibtex, export_csv
from .download import download_papers
from .diagram import generate_markdown_diagram, generate_png_diagram, save_state, load_state


def cmd_search(config: Config) -> None:
    """Run search queries across all configured databases."""
    print(f"[SEARCH] Searching {len(config.sources)} source(s) with {len(config.queries)} query(ies)...")
    print(f"  Date range: {config.date_start} to {config.date_end}")

    results = run_all_searches(config)

    # Merge all papers
    all_papers: list[Paper] = []
    source_counts: dict[str, int] = {}

    for key, papers in results.items():
        source_name = key.split("_")[0]
        source_counts[source_name] = source_counts.get(source_name, 0) + len(papers)
        all_papers.extend(papers)

    # Save
    save_papers(all_papers, config.search_dir / "all_records.json")

    # Update state
    state = load_state(config.state_file)
    state["search"] = {**source_counts, "total": len(all_papers)}
    save_state(state, config.state_file)

    print(f"\n[SEARCH] Done! Total: {len(all_papers)} papers from {len(source_counts)} source(s)")
    for src, count in source_counts.items():
        print(f"  {src}: {count}")
    print(f"  Saved to: {config.search_dir / 'all_records.json'}")


def cmd_dedup(config: Config) -> None:
    """Remove duplicate papers."""
    papers = load_papers(config.search_dir / "all_records.json")
    if not papers:
        print("[DEDUP] No papers found. Run 'search' first.")
        return

    print(f"[DEDUP] Deduplicating {len(papers)} papers...")
    unique, log = deduplicate(papers, config.doi_match, config.fuzzy_threshold)

    save_papers(unique, config.dedup_dir / "deduplicated.json")
    save_dedup_log(log, config.dedup_dir / "duplicates_log.csv")

    state = load_state(config.state_file)
    state["dedup"] = {"duplicates_removed": len(papers) - len(unique), "remaining": len(unique)}
    save_state(state, config.state_file)

    print(f"[DEDUP] Done! Removed {len(papers) - len(unique)} duplicates, {len(unique)} unique papers remaining")
    print(f"  Saved to: {config.dedup_dir / 'deduplicated.json'}")
    if log:
        print(f"  Duplicate log: {config.dedup_dir / 'duplicates_log.csv'}")


def cmd_screen_rules(config: Config) -> None:
    """Apply keyword-based screening rules."""
    papers = load_papers(config.dedup_dir / "deduplicated.json")
    if not papers:
        print("[SCREEN] No papers found. Run 'dedup' first.")
        return

    print(f"[SCREEN] Screening {len(papers)} papers with keyword rules...")
    papers = screen_by_rules(papers, config.include_keywords, config.exclude_keywords, config.min_include_hits)

    included = get_by_decision(papers, "include")
    excluded = get_by_decision(papers, "exclude")
    maybe = get_by_decision(papers, "maybe")

    save_papers(papers, config.screen_dir / "screen_results.json")
    save_papers(included, config.screen_dir / "included.json")
    save_papers(excluded, config.screen_dir / "excluded.json")
    save_papers(maybe, config.screen_dir / "maybe.json")

    state = load_state(config.state_file)
    state["screen"] = {
        "total_screened": len(papers),
        "included": len(included),
        "excluded": len(excluded),
        "maybe": len(maybe),
    }
    save_state(state, config.state_file)

    print(f"[SCREEN] Done!")
    print(f"  Included: {len(included)}")
    print(f"  Excluded: {len(excluded)}")
    print(f"  Maybe (needs review): {len(maybe)}")


def cmd_report(config: Config) -> None:
    """Generate PRISMA flow diagram."""
    state = load_state(config.state_file)
    if not state:
        print("[REPORT] No state found. Run the pipeline first.")
        return

    print("[REPORT] Generating PRISMA flow diagram...")
    generate_markdown_diagram(state, config.export_dir / "prisma_flow.md")
    generate_png_diagram(state, config.export_dir / "prisma_flow.png")

    print(f"  Markdown: {config.export_dir / 'prisma_flow.md'}")
    print(f"  PNG: {config.export_dir / 'prisma_flow.png'}")


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
    import json
    log_path = pdf_dir / "_download_log.json"
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(stats["results"], f, indent=2, ensure_ascii=False)
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

    if "screen" in state:
        sc = state["screen"]
        print(f"  SCREEN: {sc.get('included', 0)} included, {sc.get('excluded', 0)} excluded, {sc.get('maybe', 0)} maybe")

    if "eligibility" in state:
        el = state["eligibility"]
        print(f"  ELIGIBILITY: {el.get('included', 0)} included, {el.get('excluded', 0)} excluded, {el.get('remaining', 0)} remaining")


def cmd_run_all(config: Config) -> None:
    """Run the full pipeline."""
    print("=" * 60)
    print(f"PRISMA Review Tool — Full Pipeline")
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
        description="PRISMA Review Tool — Automated systematic literature review",
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
