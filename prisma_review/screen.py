"""Screen papers using keyword rules, and write screening and eligibility results.

Every writer of the screening and eligibility files goes through the helpers
here (keyword screening, rescreen, manual decisions in the web app, AI
decisions from the MCP server), so the files and the ``screen`` and
``eligibility`` blocks of review_state.json always agree and are always written
under the project lock.
"""

from __future__ import annotations

import html
import re
from pathlib import Path
from typing import Any, Iterable

import yaml

from .config import Config, load_raw_config, save_raw_config
from .models import Paper, load_papers, save_papers
from .storage import atomic_write_text, project_lock, read_text, update_state

# Reason recorded when a paper is excluded solely by the required-keywords gate.
NO_REQUIRED_KEYWORD_REASON = "no required keyword in title/abstract"
# Reason recorded when the gate cannot decide: no required keyword in the title
# and no abstract to check, so a person (or the AI) has to look at it.
NO_ABSTRACT_GATE_REASON = "no required keyword in title; no abstract to check"

DECISIONS = ("include", "exclude")
# Decisions a rescreen keeps: they were made by reading the paper, not by rules.
KEPT_METHODS = ("manual", "ai")

# Rows of the screen breakdown (WEB#4): one per method and decision, with the
# rule exclusions split by reason. Unknown methods get "other_<decision>" rows.
BREAKDOWN_KEYS = (
    "rule_include", "rule_exclude_keyword", "rule_exclude_required", "rule_maybe",
    "ai_include", "ai_exclude", "ai_maybe",
    "manual_include", "manual_exclude", "manual_maybe",
    "unscreened",
)

_TAG_RE = re.compile(r"<[^<>]{0,200}>")
# Hyphen, non-breaking hyphen, figure dash, en dash, em dash, minus sign.
_HYPHENS = dict.fromkeys(map(ord, "-\u2010\u2011\u2012\u2013\u2014\u2212"), " ")


def normalize_text(text: str | None) -> str:
    """Lowercase text with HTML tags removed, hyphens as spaces and whitespace collapsed."""
    text = html.unescape(_TAG_RE.sub(" ", text or ""))
    return " ".join(text.translate(_HYPHENS).split()).lower()


def _term_pattern(term: str) -> re.Pattern[str] | None:
    """Whole-word pattern for a required term; a plural "s"/"es" also matches."""
    words = normalize_text(term)
    if not words:
        return None
    return re.compile(r"(?<!\w)" + re.escape(words) + r"(?:s|es)?(?!\w)")


def screen_by_rules(papers: list[Paper], include_keywords: list[str],
                    exclude_keywords: list[str], min_include_hits: int = 2,
                    required_keywords: list[str] | None = None) -> list[Paper]:
    """Apply keyword-based screening rules to papers.

    Decision logic:
    - EXCLUDE if any exclude keyword found in title+abstract
    - EXCLUDE if ``required_keywords`` is non-empty and none of them are found
      (MAYBE instead when the paper has no abstract: the title alone is not enough)
    - INCLUDE if >= min_include_hits include keywords found
    - MAYBE otherwise (needs manual/AI review)

    Include and exclude keywords match as case-insensitive substrings, as
    they always have, so re-running an existing review gives the same
    decisions. ``required_keywords`` (optional; empty disables the gate) match
    whole words or phrases, case-insensitively, ignoring HTML tags, hyphens and
    extra whitespace, with a plural "s"/"es" accepted: "RAG" matches "RAGs"
    but not "storage". List other word forms separately.
    """
    patterns = [p for p in (_term_pattern(kw) for kw in (required_keywords or [])) if p]

    for paper in papers:
        # Skip papers already manually screened
        if paper.screen_method == "manual":
            continue

        abstract = paper.abstract or ""
        text = ((paper.title or "") + " " + abstract).lower()

        # Check exclude keywords
        exclude_hits = [kw for kw in exclude_keywords if kw.lower() in text]
        if exclude_hits:
            paper.screen_decision = "exclude"
            paper.screen_reason = f"matched exclude keyword: {exclude_hits[0]}"
            paper.screen_method = "rule"
            continue

        # Required-keywords gate: must contain at least one required term,
        # otherwise auto-exclude. Evaluated after exclude, before include.
        if patterns:
            normalized = normalize_text((paper.title or "") + " " + abstract)
            if not any(p.search(normalized) for p in patterns):
                paper.screen_method = "rule"
                if abstract.strip():
                    paper.screen_decision = "exclude"
                    paper.screen_reason = NO_REQUIRED_KEYWORD_REASON
                else:
                    paper.screen_decision = "maybe"
                    paper.screen_reason = NO_ABSTRACT_GATE_REASON
                continue

        # Check include keywords
        include_hits = [kw for kw in include_keywords if kw.lower() in text]
        if len(include_hits) >= min_include_hits:
            paper.screen_decision = "include"
            paper.screen_reason = f"matched {len(include_hits)} include keywords: {', '.join(include_hits[:5])}"
            paper.screen_method = "rule"
        else:
            paper.screen_decision = "maybe"
            paper.screen_reason = f"only {len(include_hits)} include keyword(s) matched (need {min_include_hits})"
            paper.screen_method = "rule"

    return papers


def get_by_decision(papers: list[Paper], decision: str) -> list[Paper]:
    """Filter papers by screening decision."""
    return [p for p in papers if p.screen_decision == decision]


def count_excluded_by_required(papers: list[Paper]) -> int:
    """Count papers excluded specifically by the required-keywords gate."""
    return sum(1 for p in papers
               if p.screen_decision == "exclude"
               and p.screen_method in ("rule", None)
               and p.screen_reason == NO_REQUIRED_KEYWORD_REASON)


# ---------------------------------------------------------------------------
# Summaries (the "screen" and "eligibility" blocks of review_state.json)
# ---------------------------------------------------------------------------


def screen_summary(papers: Iterable[Paper], *, min_include_hits: int | None = None) -> dict:
    """Counts of a screening result, computed from the papers themselves.

    ``breakdown`` has one row per method and decision (rule exclusions split
    into exclude keyword and required-keyword gate), so manual and AI
    decisions never hide inside the keyword-rule numbers.
    """
    papers = list(papers)
    breakdown = dict.fromkeys(BREAKDOWN_KEYS, 0)
    for p in papers:
        decision = (p.screen_decision or "").lower()
        if decision not in ("include", "exclude", "maybe"):
            breakdown["unscreened"] += 1
            continue
        method = p.screen_method if p.screen_method in ("rule", "ai", "manual") else "other"
        if method == "rule" and decision == "exclude":
            key = ("rule_exclude_required" if p.screen_reason == NO_REQUIRED_KEYWORD_REASON
                   else "rule_exclude_keyword")
        else:
            key = f"{method}_{decision}"
        breakdown[key] = breakdown.get(key, 0) + 1

    summary: dict[str, Any] = {
        "total_screened": len(papers),
        "included": sum(v for k, v in breakdown.items() if k.endswith("_include")),
        "excluded": sum(v for k, v in breakdown.items() if "_exclude" in k),
        "maybe": sum(v for k, v in breakdown.items() if k.endswith("_maybe")),
        "unscreened": breakdown["unscreened"],
        "excluded_no_required_keyword": breakdown["rule_exclude_required"],
        "breakdown": breakdown,
    }
    if min_include_hits is not None:
        summary["min_include_hits"] = min_include_hits
    return summary


def eligibility_summary(first_pass: Iterable[Paper], results: Iterable[Paper]) -> dict:
    """Eligibility counts over the papers currently included at screening.

    Decisions about papers that are no longer included are ignored.
    """
    ids = {p.id for p in first_pass}
    decided = {p.id: p.eligibility_decision for p in results
               if p.id in ids and p.eligibility_decision in DECISIONS}
    included = sum(1 for d in decided.values() if d == "include")
    return {
        "input_from_screening": len(ids),
        "screened": len(decided),
        "included": included,
        "excluded": len(decided) - included,
        "remaining": len(ids) - len(decided),
    }


# ---------------------------------------------------------------------------
# Writers
# ---------------------------------------------------------------------------


def _save_eligibility_files(config: Config, results: list[Paper],
                            first_pass: list[Paper]) -> None:
    """Write every eligibility decision, and the per-decision files for the included papers.

    eligibility_results.json keeps the decisions about papers that are no
    longer included at screening (a re-screen or a changed first-pass
    decision): they are set aside, not deleted, and count again as soon as the
    paper is included again. eligible_included.json and eligible_excluded.json
    hold only papers that are currently included at screening.
    """
    ids = {p.id for p in first_pass}
    current = [p for p in results if p.id in ids]
    save_papers(results, config.eligibility_dir / "eligibility_results.json")
    save_papers([p for p in current if p.eligibility_decision == "include"],
                config.eligibility_dir / "eligible_included.json")
    save_papers([p for p in current if p.eligibility_decision == "exclude"],
                config.eligibility_dir / "eligible_excluded.json")


def set_aside_count(first_pass: Iterable[Paper], results: Iterable[Paper]) -> int:
    """Eligibility decisions kept on file about papers not included at screening now."""
    ids = {p.id for p in first_pass}
    return sum(1 for p in results if p.id not in ids and p.eligibility_decision in DECISIONS)


def _set_eligibility_block(state: dict, summary: dict | None) -> None:
    if summary and summary["screened"]:
        state["eligibility"] = summary
    else:
        state.pop("eligibility", None)


def _reconcile_eligibility(config: Config, first_pass: list[Paper]) -> tuple[dict | None, int]:
    """Match the eligibility files to the papers included at screening now.

    Never deletes a decision (see ``_save_eligibility_files``). Returns the
    eligibility summary (None if no eligibility pass exists) and how many
    decisions are set aside because their paper is not included now.
    """
    path = config.eligibility_dir / "eligibility_results.json"
    if not path.exists():
        return None, 0
    results = load_papers(path)
    _save_eligibility_files(config, results, first_pass)
    return eligibility_summary(first_pass, results), set_aside_count(first_pass, results)


def _write_screen_results(config: Config, papers: list[Paper],
                          min_include_hits: int | None) -> tuple[dict, int]:
    with project_lock(config.output_dir):
        included = get_by_decision(papers, "include")
        save_papers(papers, config.screen_dir / "screen_results.json")
        save_papers(included, config.screen_dir / "included.json")
        save_papers(get_by_decision(papers, "exclude"), config.screen_dir / "excluded.json")
        save_papers(get_by_decision(papers, "maybe"), config.screen_dir / "maybe.json")
        elig_summary, dropped = _reconcile_eligibility(config, included)
        summary = screen_summary(papers, min_include_hits=min_include_hits)

        def apply(state: dict) -> None:
            previous = state.get("screen")
            # A manual or AI decision does not change the threshold rules used.
            if min_include_hits is None and isinstance(previous, dict) \
                    and previous.get("min_include_hits") is not None:
                summary["min_include_hits"] = previous["min_include_hits"]
            state["screen"] = summary
            if elig_summary is not None or "eligibility" in state:
                _set_eligibility_block(state, elig_summary)

        update_state(config.state_file, apply)
    return summary, dropped


def write_screen_results(config: Config, papers: list[Paper], *,
                         min_include_hits: int | None = None) -> dict:
    """Write a full screening result: screen_results.json, the per-decision files,
    the ``screen`` block of the state and the reconciled eligibility pass.

    The one writer every screening path uses (pipeline, CLI, rescreen, web
    manual decisions, MCP AI decisions). ``min_include_hits`` is the
    threshold the keyword rules used; omit it for decisions that do not
    re-run the rules. Returns the screen summary.
    """
    return _write_screen_results(config, papers, min_include_hits)[0]


def write_eligibility_results(config: Config, results: list[Paper],
                              first_pass: list[Paper]) -> dict:
    """Write the eligibility files and the ``eligibility`` block; returns its summary.

    ``results`` is every decision on file; decisions about papers outside
    ``first_pass`` are kept but not counted.
    """
    with project_lock(config.output_dir):
        _save_eligibility_files(config, results, first_pass)
        summary = eligibility_summary(first_pass, results)
        update_state(config.state_file, lambda state: _set_eligibility_block(state, summary))
    return summary


def _decision_fields(item: dict) -> tuple[str, str, str]:
    return (str(item.get("paper_id") or ""), str(item.get("decision") or ""),
            str(item.get("reason") or ""))


def apply_screen_decisions(config: Config, decisions: list[dict],
                           method: str) -> tuple[list[dict], dict]:
    """Record first-pass decisions ({paper_id, decision, reason}) made by ``method`` ("manual" or "ai").

    Reads, changes and writes screen_results.json under the project lock, so
    the web app and the MCP server never drop each other's decisions.
    Returns one result per decision and the screen summary.
    """
    results: list[dict] = []
    with project_lock(config.output_dir):
        papers = load_papers(config.screen_dir / "screen_results.json")
        by_id = {p.id: p for p in papers}
        changed = False
        for item in decisions:
            pid, decision, reason = _decision_fields(item)
            if decision not in DECISIONS:
                results.append({"paper_id": pid, "status": "error", "message": "invalid decision"})
                continue
            paper = by_id.get(pid)
            if paper is None:
                results.append({"paper_id": pid, "status": "error", "message": "not found"})
                continue
            paper.screen_decision, paper.screen_reason, paper.screen_method = decision, reason, method
            results.append({"paper_id": pid, "status": "ok", "decision": decision})
            changed = True
        summary = write_screen_results(config, papers) if changed else screen_summary(papers)
    return results, summary


def apply_eligibility_decisions(config: Config, decisions: list[dict],
                                method: str) -> tuple[list[dict], dict]:
    """Record eligibility (second pass) decisions about first-pass included papers."""
    results: list[dict] = []
    with project_lock(config.output_dir):
        first_pass = load_papers(config.screen_dir / "included.json")
        by_id = {p.id: p for p in first_pass}
        current = {p.id: p for p in load_papers(config.eligibility_dir / "eligibility_results.json")}
        for item in decisions:
            pid, decision, reason = _decision_fields(item)
            if decision not in DECISIONS:
                results.append({"paper_id": pid, "status": "error", "message": "invalid decision"})
                continue
            paper = by_id.get(pid)
            if paper is None:
                results.append({"paper_id": pid, "status": "error", "message": "not found"})
                continue
            paper.eligibility_decision, paper.eligibility_reason = decision, reason
            paper.eligibility_method = method
            current[pid] = paper
            results.append({"paper_id": pid, "status": "ok", "decision": decision})
        if any(r["status"] == "ok" for r in results):
            summary = write_eligibility_results(config, list(current.values()), first_pass)
        else:
            summary = eligibility_summary(first_pass, current.values())
    return results, summary


# ---------------------------------------------------------------------------
# Rescreen
# ---------------------------------------------------------------------------


_MIN_HITS_LINE = re.compile(r"(?m)^([ \t]*min_include_hits[ \t]*:[ \t]*)([^\s#]+)")


def save_min_include_hits(config_path: str | Path, hits: int) -> None:
    """Store ``screening.rules.min_include_hits`` in config.yaml.

    Edits the one line in place when it can, so comments survive; otherwise
    rewrites the whole file. Atomic, under the config folder's lock.
    """
    path = Path(config_path)
    with project_lock(path.parent):
        text = read_text(path)
        new_text, count = _MIN_HITS_LINE.subn(lambda m: m.group(1) + str(hits), text)
        if count == 1:
            try:
                ok = Config(yaml.safe_load(new_text)).min_include_hits == hits
            except yaml.YAMLError:
                ok = False
            if ok:
                atomic_write_text(path, new_text)
                return
        data = load_raw_config(path)
        node = data
        for key in ("screening", "rules"):
            if not isinstance(node.get(key), dict):
                node[key] = {}
            node = node[key]
        node["min_include_hits"] = hits
        save_raw_config(path, data)


def rescreen(config: Config, min_include_hits: int | None = None, *,
             check_running: bool = True, persist_threshold: bool = True) -> dict:
    """Re-run the keyword rules on the deduplicated papers (no new search or dedup).

    Keeps every manual and AI decision and every eligibility decision (those
    about papers no longer included are set aside until they are included
    again, ``eligibility_set_aside``), records the threshold used in the
    state and (``persist_threshold``) in config.yaml. Raises ``RunActiveError``
    while a pipeline runs on the project (``check_running``), ``StepError``
    when there is nothing to screen and ``ValueError`` for a bad threshold.
    Used by the pipeline, the CLI, the web app and the MCP server.
    """
    from .pipeline import RunActiveError, StepError, active_run, describe_run

    if min_include_hits is None:
        hits = config.min_include_hits
        if hits < 1:
            raise ValueError(f"screening.rules.min_include_hits must be at least 1 (got {hits}).")
    else:
        hits = min_include_hits
        if isinstance(hits, bool) or not isinstance(hits, int) or not 1 <= hits <= 10:
            raise ValueError(f"min_include_hits must be between 1 and 10 (got {hits!r}).")

    with project_lock(config.output_dir):
        if check_running:
            run = active_run(config.state_file)
            if run is not None:
                raise RunActiveError(describe_run(run) + " Re-screening would overwrite its results.")
        papers = load_papers(config.dedup_dir / "deduplicated.json")
        if not papers:
            raise StepError("No deduplicated papers found. Run the pipeline first.")
        previous = {p.id: p for p in load_papers(config.screen_dir / "screen_results.json")}

        for p in papers:
            p.screen_decision = p.screen_reason = p.screen_method = None
        screen_by_rules(papers, config.include_keywords, config.exclude_keywords,
                        hits, config.required_keywords)
        kept = dict.fromkeys(KEPT_METHODS, 0)
        for p in papers:
            prev = previous.get(p.id)
            if prev is not None and prev.screen_method in KEPT_METHODS and prev.screen_decision:
                p.screen_decision, p.screen_reason = prev.screen_decision, prev.screen_reason
                p.screen_method = prev.screen_method
                kept[prev.screen_method] += 1

        summary, dropped = _write_screen_results(config, papers, hits)

    threshold_saved = False
    if persist_threshold and config.config_path is not None and hits != config.min_include_hits:
        save_min_include_hits(config.config_path, hits)
        threshold_saved = True

    return {
        "status": "ok",
        "min_include_hits": hits,
        "included": summary["included"],
        "excluded": summary["excluded"],
        "maybe": summary["maybe"],
        "excluded_no_required_keyword": summary["excluded_no_required_keyword"],
        "kept_manual": kept["manual"],
        "kept_ai": kept["ai"],
        "eligibility_set_aside": dropped,
        "threshold_saved": threshold_saved,
    }
