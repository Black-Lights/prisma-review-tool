"""Load and validate config.yaml."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


class Config:
    """Configuration loaded from YAML file."""

    def __init__(self, data: dict[str, Any], base_dir: Path = Path(".")):
        self._data = data
        self._base_dir = base_dir

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
        return cls(data, base_dir=path.parent)

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
        return self._data.get("search", {}).get("sources", ["arxiv", "openalex", "semantic_scholar"])

    @property
    def queries(self) -> list[dict]:
        return self._data.get("search", {}).get("queries", [])

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
