"""Tell the user how to fix an install whose Python packages are out of date.

An existing virtual environment keeps the packages of the version it was
created for. After an update that adds a dependency (1.6 added filelock), the
CLI, the MCP server and the web API would otherwise die on a bare
ModuleNotFoundError. The entry points call :func:`exit_if_missing` first.
"""

from __future__ import annotations

import importlib.util
import sys

# Importable module name -> pip package name.
CORE_MODULES = {
    "arxiv": "arxiv", "requests": "requests", "yaml": "pyyaml", "numpy": "numpy",
    "pandas": "pandas", "rapidfuzz": "rapidfuzz", "matplotlib": "matplotlib",
    "filelock": "filelock",
}
MCP_MODULES = {"mcp": "mcp"}
API_MODULES = {"fastapi": "fastapi", "uvicorn": "uvicorn", "multipart": "python-multipart"}


def missing_packages(extra: dict[str, str] | None = None) -> list[str]:
    """The pip names of required packages that cannot be imported."""
    modules = {**CORE_MODULES, **(extra or {})}
    return [pkg for mod, pkg in modules.items() if importlib.util.find_spec(mod) is None]


def install_hint(missing: list[str]) -> str:
    return (
        f"PRISMA Review Tool: missing Python package(s): {', '.join(missing)}.\n"
        f"This environment was installed for an older version. Update it with\n"
        f"    python start.py --install\n"
        f"or\n"
        f"    \"{sys.executable}\" -m pip install -r requirements.txt -r api/requirements.txt\n"
        f"(run from the tool's folder), then start it again."
    )


def exit_if_missing(extra: dict[str, str] | None = None) -> None:
    """Print how to update the environment (stderr) and exit 1 if a package is missing."""
    missing = missing_packages(extra)
    if missing:
        print(install_hint(missing), file=sys.stderr, flush=True)
        raise SystemExit(1)
