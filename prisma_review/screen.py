"""Screen papers using keyword rules."""

from __future__ import annotations

from .models import Paper

# Reason recorded when a paper is excluded solely by the required-keywords gate.
NO_REQUIRED_KEYWORD_REASON = "no required keyword in title/abstract"


def screen_by_rules(papers: list[Paper], include_keywords: list[str],
                    exclude_keywords: list[str], min_include_hits: int = 2,
                    required_keywords: list[str] | None = None) -> list[Paper]:
    """Apply keyword-based screening rules to papers.

    Decision logic:
    - EXCLUDE if any exclude keyword found in title+abstract
    - EXCLUDE if ``required_keywords`` is non-empty and none of them are found
    - INCLUDE if >= min_include_hits include keywords found
    - MAYBE otherwise (needs manual/AI review)

    ``required_keywords`` is optional and fully config-driven. When empty/None
    (after dropping blanks) the gate is disabled and behaviour is identical to
    before. Matching is substring + case-insensitive, same as the other keyword
    lists — list distinct surface forms of a concept separately.
    """
    # Drop blanks so an empty/whitespace term can't make the gate always pass
    # (``"" in text`` is always True). An empty list disables the gate.
    required = [kw for kw in (required_keywords or []) if kw.strip()]

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

        # Required-keywords gate: must contain at least one required term,
        # otherwise auto-exclude. Evaluated after exclude, before include.
        if required and not any(kw.lower() in text for kw in required):
            paper.screen_decision = "exclude"
            paper.screen_reason = NO_REQUIRED_KEYWORD_REASON
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


def count_excluded_by_required(papers: list[Paper]) -> int:
    """Count papers excluded specifically by the required-keywords gate."""
    return sum(1 for p in papers
               if p.screen_decision == "exclude"
               and p.screen_reason == NO_REQUIRED_KEYWORD_REASON)
