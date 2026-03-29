"""Screen papers using keyword rules."""

from __future__ import annotations

from .models import Paper


def screen_by_rules(papers: list[Paper], include_keywords: list[str],
                    exclude_keywords: list[str], min_include_hits: int = 2) -> list[Paper]:
    """Apply keyword-based screening rules to papers.

    Decision logic:
    - EXCLUDE if any exclude keyword found in title+abstract
    - INCLUDE if >= min_include_hits include keywords found
    - MAYBE otherwise (needs manual/AI review)
    """
    for paper in papers:
        # Skip papers already manually screened
        if paper.screen_method == "manual":
            continue

        text = (paper.title + " " + paper.abstract).lower()

        # Check exclude keywords
        exclude_hits = [kw for kw in exclude_keywords if kw.lower() in text]
        if exclude_hits:
            paper.screen_decision = "exclude"
            paper.screen_reason = f"matched exclude keyword: {exclude_hits[0]}"
            paper.screen_method = "rule"
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
