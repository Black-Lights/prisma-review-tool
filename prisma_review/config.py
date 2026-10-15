"""Load and validate config.yaml."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


# Template placeholder values, used to detect an unconfigured config.yaml.
# These mirror config.template.yaml; the real set is derived from that file at
# runtime (so it tracks template edits), with this list as a fallback.
_FALLBACK_PLACEHOLDERS = (
    "your review title here",
    "your key phrase 1", "your key phrase 2", "method or context",
    "another topic", "relevant method", "relevant tool", "domain or application",
    "keyword 1", "keyword 2", "keyword 3",
    "irrelevant topic 1", "irrelevant topic 2",
)

_placeholder_cache: set[str] | None = None


def _norm(value: object) -> str:
    """Whitespace-normalise and lowercase a value for placeholder comparison."""
    return " ".join(str(value).split()).lower()


def _placeholder_strings() -> set[str]:
    """Build the set of placeholder values from config.template.yaml (cached).

    Falls back to the hardcoded list if the template can't be read.
    """
    global _placeholder_cache
    if _placeholder_cache is not None:
        return _placeholder_cache

    strings: set[str] = set()
    tpl_path = Path(__file__).resolve().parent.parent / "config.template.yaml"
    try:
        if tpl_path.exists():
            with open(tpl_path, "r", encoding="utf-8") as f:
                tpl = yaml.safe_load(f) or {}
            strings.add(_norm(tpl.get("project", {}).get("name", "")))
            for q in tpl.get("search", {}).get("queries", []) or []:
                strings.add(_norm(q.get("terms", "")))
            rules = tpl.get("screening", {}).get("rules", {}) or {}
            for k in (rules.get("include_keywords") or []) + (rules.get("exclude_keywords") or []):
                strings.add(_norm(k))
    except Exception:
        pass

    strings.update(_norm(s) for s in _FALLBACK_PLACEHOLDERS)
    strings.discard("")
    _placeholder_cache = strings
    return strings


def _is_placeholder(value: object) -> bool:
    """True if ``value`` is still an unfilled template placeholder."""
    return _norm(value) in _placeholder_strings()


class Config:
    """Configuration loaded from YAML file."""

    def __init__(self, data: dict[str, Any], base_dir: Path = Path("."),
                 path: Path | None = None):
        self._data = data
        self._base_dir = base_dir
        self._path = path

    @classmethod
    def load(cls, path: str | Path = "config.yaml") -> Config:
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(
                f"Config file not found: {path}\n"
                f"Copy config.template.yaml to config.yaml and fill in your details."
            )
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return cls(data, base_dir=path.parent, path=path)

    @property
    def config_path(self) -> Path | None:
        """The file this config was loaded from (None if constructed in-memory)."""
        return self._path

    @property
    def project_name(self) -> str:
        return self._data.get("project", {}).get("name", "PRISMA Review")

    @property
    def output_dir(self) -> Path:
        raw = self._data.get("project", {}).get("output_dir", "./prisma_output")
        return (self._base_dir / raw).resolve()

    @property
    def search_dir(self) -> Path:
        return self.output_dir / "01_search"

    @property
    def dedup_dir(self) -> Path:
        return self.output_dir / "02_dedup"

    @property
    def screen_dir(self) -> Path:
        return self.output_dir / "03_screen"

    @property
    def eligibility_dir(self) -> Path:
        return self.output_dir / "03b_eligibility"

    @property
    def export_dir(self) -> Path:
        return self.output_dir / "04_export"

    @property
    def state_file(self) -> Path:
        return self.output_dir / "review_state.json"

    # API keys
    @property
    def scopus_key(self) -> str:
        return self._data.get("api_keys", {}).get("scopus", "")

    @property
    def openalex_email(self) -> str:
        return self._data.get("api_keys", {}).get("openalex_email", "")

    @property
    def openalex_key(self) -> str:
        return self._data.get("api_keys", {}).get("openalex_key", "")

    # Search config
    @property
    def date_start(self) -> str:
        return self._data.get("search", {}).get("date_range", {}).get("start", "2015-01-01")

    @property
    def date_end(self) -> str:
        return self._data.get("search", {}).get("date_range", {}).get("end", "2026-12-31")

    @property
    def max_results(self) -> int:
        return self._data.get("search", {}).get("max_results_per_query", 500)

    @property
    def sources(self) -> list[str]:
        return self._data.get("search", {}).get("sources", ["arxiv", "crossref", "openalex", "semantic_scholar"])

    @property
    def queries(self) -> list[dict]:
        return self._data.get("search", {}).get("queries", [])

    # Source-side filters (optional; all empty/false disables filtering).
    def _filters(self) -> dict:
        return self._data.get("search", {}).get("filters", {}) or {}

    @property
    def filter_document_types(self) -> list[str]:
        return [t for t in (self._filters().get("document_types") or []) if str(t).strip()]

    @property
    def filter_require_abstract(self) -> bool:
        return bool(self._filters().get("require_abstract", False))

    @property
    def filter_open_access(self) -> bool:
        return bool(self._filters().get("open_access", False))

    @property
    def filter_venues(self) -> list[str]:
        return [v for v in (self._filters().get("venues") or []) if str(v).strip()]

    # Dedup config
    @property
    def doi_match(self) -> bool:
        return self._data.get("dedup", {}).get("doi_match", True)

    @property
    def fuzzy_threshold(self) -> int:
        return self._data.get("dedup", {}).get("fuzzy_title_threshold", 90)

    # Screening config
    @property
    def include_keywords(self) -> list[str]:
        return self._data.get("screening", {}).get("rules", {}).get("include_keywords", [])

    @property
    def exclude_keywords(self) -> list[str]:
        return self._data.get("screening", {}).get("rules", {}).get("exclude_keywords", [])

    @property
    def min_include_hits(self) -> int:
        return self._data.get("screening", {}).get("rules", {}).get("min_include_hits", 2)

    @property
    def required_keywords(self) -> list[str]:
        """Optional gate: a paper must contain >=1 of these to pass screening.

        Empty/absent (the default) disables the gate — fully backward compatible.
        """
        return self._data.get("screening", {}).get("rules", {}).get("required_keywords", [])

    # Readiness
    def readiness(self) -> dict:
        """Report whether the config is filled in or still the template.

        Returns ``ready`` (all required fields filled) and ``problems`` (human
        readable issues), plus per-area lists used to guard specific pipeline
        steps: ``search_problems`` (name/queries/sources) and ``screen_problems``
        (include keywords).
        """
        search_problems: list[str] = []
        screen_problems: list[str] = []

        name = self.project_name.strip()
        if not name or _is_placeholder(name):
            search_problems.append(
                "project.name is still the template value — set your review title."
            )

        real_queries = [q for q in self.queries if str(q.get("terms", "")).strip()]
        if not real_queries:
            search_problems.append(
                "search.queries is empty — add at least one query with 'terms'."
            )
        elif all(_is_placeholder(q.get("terms", "")) for q in real_queries):
            search_problems.append(
                'search.queries still contains only template placeholders '
                '(e.g. "your key phrase 1").'
            )

        if not self.sources:
            search_problems.append(
                "search.sources is empty — enable at least one source (e.g. openalex)."
            )

        real_includes = [k for k in self.include_keywords if str(k).strip()]
        if not real_includes:
            screen_problems.append(
                "screening.rules.include_keywords is empty — add screening keywords."
            )
        elif all(_is_placeholder(k) for k in real_includes):
            screen_problems.append(
                'screening.rules.include_keywords still contains template '
                'placeholders (e.g. "keyword 1").'
            )

        problems = search_problems + screen_problems
        return {
            "ready": not problems,
            "problems": problems,
            "search_problems": search_problems,
            "screen_problems": screen_problems,
        }
