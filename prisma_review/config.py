"""Load and validate config.yaml."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

from .storage import atomic_write_yaml, read_text

# Search sources the runner knows. Configs may list them in any case.
KNOWN_SOURCES = ("arxiv", "crossref", "openalex", "semantic_scholar", "scopus")

# Sources used when a config has no ``search.sources`` key at all. Unchanged
# since v1.0 so re-running an old config gives the same PRISMA counts; Crossref
# is opt-in (its relevance-ranked results are mostly off-topic for Boolean queries).
DEFAULT_SOURCES = ("arxiv", "openalex", "semantic_scholar")

# Canonical document types accepted in ``search.filters.document_types``.
KNOWN_DOCUMENT_TYPES = ("journal-article", "review", "conference-paper", "book-chapter", "preprint")

# ``api_keys`` entries that are not secrets (shown as-is by the web API).
PUBLIC_API_KEY_FIELDS = ("openalex_email",)

OPENALEX_KEY_WARNING = (
    "OpenAlex is enabled but api_keys.openalex_key is empty. OpenAlex now requires a "
    "free API key to page past the first page of results, so without one every query "
    "stops at 50 records. Create a free account at https://openalex.org and add its "
    "API key under api_keys.openalex_key."
)


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


class ConfigError(ValueError):
    """config.yaml is not valid YAML or not a mapping."""


def load_raw_config(path: str | Path) -> dict:
    """Load a config file as a plain dict. Raises ConfigError unless it is a YAML mapping."""
    path = Path(path)
    try:
        data = yaml.safe_load(read_text(path))
    except yaml.YAMLError as exc:
        raise ConfigError(f"{path} is not valid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"{path} must be a YAML mapping (key: value pairs), "
                          f"got {type(data).__name__}.")
    return data


def save_raw_config(path: str | Path, data: dict) -> None:
    """Write a config dict atomically, refusing anything that is not a mapping."""
    if not isinstance(data, dict):
        raise ConfigError(f"Refusing to write config {path}: expected a mapping, "
                          f"got {type(data).__name__}.")
    atomic_write_yaml(path, data)


def config_version(path: str | Path) -> str | None:
    """Fingerprint of a config file, "<mtime_ns>-<size>", or None if it does not exist."""
    try:
        st = os.stat(path)
    except FileNotFoundError:
        return None
    return f"{st.st_mtime_ns}-{st.st_size}"


def _as_list(value: object) -> list:
    """A YAML list field as a list: None -> [], a lone scalar -> [scalar]."""
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return list(value)
    return [value]


def _str_list(value: object) -> list[str]:
    """A YAML list of terms as clean strings: drops nulls and blanks, stringifies numbers."""
    out = []
    for item in _as_list(value):
        if item is None or isinstance(item, (dict, list)):
            continue
        text = str(item).strip()
        if text:
            out.append(text)
    return out


class Config:
    """Configuration loaded from YAML file.

    Every getter tolerates sections or lists left empty in YAML (``filters:``
    with all children commented out reads as null) and returns clean values.
    """

    def __init__(self, data: dict[str, Any], base_dir: Path = Path("."),
                 path: Path | None = None):
        self._data = data if isinstance(data, dict) else {}
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
        return cls(load_raw_config(path), base_dir=path.parent, path=path)

    def _section(self, *keys: str) -> dict:
        """The nested mapping at ``keys``, or {} if any level is missing or not a mapping."""
        node: Any = self._data
        for key in keys:
            node = node.get(key) if isinstance(node, dict) else None
        return node if isinstance(node, dict) else {}

    @property
    def config_path(self) -> Path | None:
        """The file this config was loaded from (None if constructed in-memory)."""
        return self._path

    @property
    def project_name(self) -> str:
        name = self._section("project").get("name")
        return str(name) if name is not None and str(name).strip() else "PRISMA Review"

    @property
    def output_dir(self) -> Path:
        raw = self._section("project").get("output_dir") or "./prisma_output"
        return (self._base_dir / str(raw)).resolve()

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
    def _api_key(self, name: str) -> str:
        value = self._section("api_keys").get(name)
        return str(value).strip() if value is not None else ""

    @property
    def scopus_key(self) -> str:
        return self._api_key("scopus")

    @property
    def openalex_email(self) -> str:
        return self._api_key("openalex_email")

    @property
    def openalex_key(self) -> str:
        return self._api_key("openalex_key")

    # Search config
    @property
    def date_start(self) -> str:
        # str(): an unquoted YAML date (start: 2020-01-01) loads as datetime.date.
        value = self._section("search", "date_range").get("start")
        return str(value) if value else "2015-01-01"

    @property
    def date_end(self) -> str:
        value = self._section("search", "date_range").get("end")
        return str(value) if value else "2026-12-31"

    @property
    def max_results(self) -> int:
        try:
            return int(self._section("search").get("max_results_per_query", 500))
        except (TypeError, ValueError):
            return 500

    @property
    def sources(self) -> list[str]:
        search = self._section("search")
        if "sources" not in search:
            return list(DEFAULT_SOURCES)
        # Present but empty (every entry commented out) means none, not the default.
        return [s.lower() for s in _str_list(search.get("sources"))]

    @property
    def queries(self) -> list[dict]:
        return [q for q in _as_list(self._section("search").get("queries")) if isinstance(q, dict)]

    # Source-side filters (optional; all empty/false disables filtering).
    def _filters(self) -> dict:
        return self._section("search", "filters")

    @property
    def filter_document_types(self) -> list[str]:
        return _str_list(self._filters().get("document_types"))

    @property
    def filter_require_abstract(self) -> bool:
        return bool(self._filters().get("require_abstract", False))

    @property
    def filter_open_access(self) -> bool:
        return bool(self._filters().get("open_access", False))

    @property
    def filter_venues(self) -> list[str]:
        return _str_list(self._filters().get("venues"))

    # Dedup config
    @property
    def doi_match(self) -> bool:
        return bool(self._section("dedup").get("doi_match", True))

    @property
    def fuzzy_threshold(self) -> int:
        try:
            return int(self._section("dedup").get("fuzzy_title_threshold", 90))
        except (TypeError, ValueError):
            return 90

    # Screening config
    def _rules(self) -> dict:
        return self._section("screening", "rules")

    @property
    def include_keywords(self) -> list[str]:
        return _str_list(self._rules().get("include_keywords"))

    @property
    def exclude_keywords(self) -> list[str]:
        return _str_list(self._rules().get("exclude_keywords"))

    @property
    def min_include_hits(self) -> int:
        try:
            return int(self._rules().get("min_include_hits", 2))
        except (TypeError, ValueError):
            return 2

    @property
    def required_keywords(self) -> list[str]:
        """Optional gate: a paper must contain >=1 of these to pass screening.

        Empty/absent (the default) disables the gate, fully backward compatible.
        A single string is one term (not one term per character); numbers become
        strings and empty entries are dropped.
        """
        return _str_list(self._rules().get("required_keywords"))

    # Readiness
    def readiness(self) -> dict:
        """Report whether the config is filled in or still the template.

        Returns ``ready`` (all required fields filled) and ``problems`` (human
        readable issues), plus per-area lists used to guard specific pipeline
        steps: ``search_problems`` (name/queries/sources) and ``screen_problems``
        (include keywords). ``warnings`` lists things that do not block a run
        but change its results (e.g. OpenAlex without an API key).
        """
        search_problems: list[str] = []
        screen_problems: list[str] = []
        warnings: list[str] = []

        name = self.project_name.strip()
        if not name or _is_placeholder(name):
            search_problems.append(
                "project.name is still the template value: set your review title."
            )

        raw_queries = _as_list(self._section("search").get("queries"))
        if any(not isinstance(q, dict) for q in raw_queries):
            search_problems.append(
                'search.queries entries must each be a mapping with "name" and "terms".'
            )
        real_queries = [q for q in self.queries if str(q.get("terms") or "").strip()]
        if not real_queries:
            search_problems.append(
                "search.queries is empty: add at least one query with 'terms'."
            )
        elif all(_is_placeholder(q.get("terms", "")) for q in real_queries):
            search_problems.append(
                'search.queries still contains only template placeholders '
                '(e.g. "your key phrase 1").'
            )

        if not self.sources:
            search_problems.append(
                "search.sources is empty: enable at least one source (e.g. openalex)."
            )
        unknown = [s for s in self.sources if s not in KNOWN_SOURCES]
        if unknown:
            warnings.append(
                f"search.sources lists unknown source(s) {unknown}; they are skipped. "
                f"Known sources: {', '.join(KNOWN_SOURCES)}."
            )
        if "openalex" in self.sources and not self.openalex_key:
            warnings.append(OPENALEX_KEY_WARNING)

        real_includes = self.include_keywords
        if not real_includes:
            screen_problems.append(
                "screening.rules.include_keywords is empty: add screening keywords."
            )
        elif all(_is_placeholder(k) for k in real_includes):
            screen_problems.append(
                'screening.rules.include_keywords still contains template '
                'placeholders (e.g. "keyword 1").'
            )
        if self.min_include_hits < 1:
            screen_problems.append(
                "screening.rules.min_include_hits must be at least 1."
            )

        problems = search_problems + screen_problems
        return {
            "ready": not problems,
            "problems": problems,
            "search_problems": search_problems,
            "screen_problems": screen_problems,
            "warnings": warnings,
        }
