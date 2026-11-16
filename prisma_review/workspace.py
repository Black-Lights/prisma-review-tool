"""Where review projects live and which one is active.

The web API and the MCP server are separate processes that must agree on
which ``config.yaml`` they read and write. Both resolve it here, in order:

1. ``PRISMA_CONFIG`` (environment) pins one config file, e.g. in ``.mcp.json``;
2. otherwise ``projects/.active_project`` names the active project;
3. only when there is no marker and no project at all, the root
   ``config.yaml`` applies (installs that never created a project).

A marker naming an invalid or missing project is an error, never a silent
fallback to some other review, and so is a missing marker while projects
exist (deleting the active project activates nothing). Project names are folder slugs: a name is valid
only if it equals ``slugify(name)`` and stays directly inside ``projects/``.

The workspace root (the folder holding ``config.yaml`` and ``projects/``) is
the install folder unless ``PRISMA_WORKSPACE`` points elsewhere.
"""

from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

import yaml

from .config import Config, load_raw_config, save_raw_config
from .storage import LOCK_FILENAME, atomic_write_text, project_lock, read_text

ENV_CONFIG = "PRISMA_CONFIG"
ENV_WORKSPACE = "PRISMA_WORKSPACE"
MARKER_NAME = ".active_project"
INSTALL_DIR = Path(__file__).resolve().parent.parent


class WorkspaceError(RuntimeError):
    """Base class for project resolution errors (the message is user-facing)."""


class InvalidProjectName(WorkspaceError, ValueError):
    """A project name that is not a plain folder slug inside projects/."""


class ProjectNotFound(WorkspaceError):
    """A named project has no folder or no config.yaml."""


class ProjectExists(WorkspaceError):
    """Creating a project whose folder already exists."""


class ActiveProjectError(WorkspaceError):
    """projects/.active_project is empty, invalid or names a missing project."""


class NoActiveProject(ActiveProjectError):
    """Projects exist but none is active (e.g. the active one was deleted)."""


class ConfigNotFound(WorkspaceError):
    """No config file to use (missing pinned file, or no project and no root config)."""


class ConfigPinned(WorkspaceError):
    """PRISMA_CONFIG pins the config, so switching the active project would not apply."""


@dataclass(frozen=True)
class Resolution:
    """The config file in use and why."""

    config_path: Path
    project: str | None  # project folder name, None for a config outside projects/
    source: str          # "env" (PRISMA_CONFIG), "marker" (.active_project) or "root"


# ---------------------------------------------------------------------------
# Paths and names
# ---------------------------------------------------------------------------


def workspace_root() -> Path:
    """The folder holding config.yaml and projects/ (PRISMA_WORKSPACE or the install folder)."""
    raw = os.environ.get(ENV_WORKSPACE, "").strip()
    return Path(raw).expanduser().resolve() if raw else INSTALL_DIR


def _root(root: str | Path | None) -> Path:
    return Path(root) if root is not None else workspace_root()


def projects_dir(root: str | Path | None = None) -> Path:
    return _root(root) / "projects"


def marker_path(root: str | Path | None = None) -> Path:
    return projects_dir(root) / MARKER_NAME


def template_path() -> Path:
    """config.template.yaml shipped with the tool."""
    return INSTALL_DIR / "config.template.yaml"


def slugify(text: str) -> str:
    """Convert a review title to a project folder name."""
    slug = str(text).lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug or "default-project"


def _same_path(a: Path, b: Path) -> bool:
    return os.path.normcase(str(a)) == os.path.normcase(str(b))


def validate_project_name(name: str, root: str | Path | None = None) -> str:
    """Return ``name`` if it is a project folder slug directly inside projects/, else raise.

    Rejects traversal ("../x", "..\\x"), absolute paths, drive letters and any
    other name that is not exactly its own slug.
    """
    if not isinstance(name, str) or not name or name != slugify(name):
        raise InvalidProjectName(
            f"Invalid project name {name!r}: use the project's folder name as listed "
            f"by list_projects (lowercase letters, digits and hyphens)."
        )
    base = projects_dir(root).resolve()
    if not _same_path((base / name).resolve().parent, base):
        raise InvalidProjectName(f"Invalid project name {name!r}.")
    return name


def project_dir(name: str, root: str | Path | None = None) -> Path:
    """The folder of a validated project name (it may not exist)."""
    return projects_dir(root) / validate_project_name(name, root)


def project_config_path(name: str, root: str | Path | None = None) -> Path:
    return project_dir(name, root) / "config.yaml"


def list_project_names(root: str | Path | None = None) -> list[str]:
    """Folder names in projects/ (sorted, hidden entries skipped)."""
    pdir = projects_dir(root)
    if not pdir.is_dir():
        return []
    return sorted(e.name for e in pdir.iterdir() if e.is_dir() and not e.name.startswith("."))


def projects_with_config(root: str | Path | None = None) -> list[str]:
    """Project folders that hold a config.yaml (sorted)."""
    return [n for n in list_project_names(root) if (projects_dir(root) / n / "config.yaml").is_file()]


def project_for_config(config_path: str | Path, root: str | Path | None = None) -> str | None:
    """The project name if ``config_path`` is projects/<name>/config.yaml, else None."""
    path = Path(config_path).resolve()
    if path.name != "config.yaml" or not _same_path(path.parent.parent, projects_dir(root).resolve()):
        return None
    try:
        return validate_project_name(path.parent.name, root)
    except InvalidProjectName:
        return None


# ---------------------------------------------------------------------------
# Active project and config resolution
# ---------------------------------------------------------------------------


def read_active_project(root: str | Path | None = None) -> str | None:
    """The active project's name, or None when there is no marker file.

    Raises ActiveProjectError when the marker is empty, invalid, or names a
    project without a config.yaml.
    """
    marker = marker_path(root)
    try:
        # utf-8-sig: a marker saved by hand (e.g. PowerShell) may start with a BOM.
        name = read_text(marker, encoding="utf-8-sig").strip()
    except FileNotFoundError:
        return None
    hint = ("Switch to an existing project (list_projects / switch_project, or the "
            "web Projects page) or create one.")
    if not name:
        raise ActiveProjectError(f"{marker} is empty. {hint}")
    try:
        validate_project_name(name, root)
    except InvalidProjectName:
        raise ActiveProjectError(
            f"{marker} names {name!r}, which is not a valid project folder name. {hint}"
        ) from None
    cfg = projects_dir(root) / name / "config.yaml"
    if not cfg.is_file():
        raise ActiveProjectError(
            f"The active project {name!r} (from {marker}) has no config.yaml at {cfg}. {hint}"
        )
    return name


def pinned_config_path() -> Path | None:
    """The config file pinned by PRISMA_CONFIG (resolved against the cwd), or None."""
    raw = os.environ.get(ENV_CONFIG, "").strip()
    return Path(raw).expanduser().resolve() if raw else None


def ensure_not_pinned() -> None:
    """Raise ConfigPinned if PRISMA_CONFIG is set (switching projects would not apply)."""
    pin = pinned_config_path()
    if pin is not None:
        raise ConfigPinned(
            f"This process is pinned to {pin} by the {ENV_CONFIG} environment variable, "
            f"so it cannot switch projects. Remove {ENV_CONFIG} (e.g. from .mcp.json) "
            f"to follow the active project instead."
        )


def no_active_project_message(root: str | Path | None = None) -> str | None:
    """Why there is no review to use although projects exist (no marker), or None.

    Nothing picks a project on the user's behalf: after the active project is
    deleted, every tool asks for a choice instead of moving to another review.
    """
    if marker_path(root).exists() or not projects_with_config(root):
        return None
    msg = ("No active project is selected. Pick one with list_projects and switch_project, "
           "or on the web Projects page.")
    root_config = _root(root) / "config.yaml"
    if root_config.is_file():
        msg += (f" The root config.yaml ({root_config}) is not used while projects exist; "
                f"set {ENV_CONFIG}={root_config} to work on it.")
    return msg


def resolve(root: str | Path | None = None) -> Resolution:
    """Resolve the config file to use: PRISMA_CONFIG, else the active project, else root.

    The root config.yaml applies only when there is no project at all (an
    install that never created one). Raises ConfigNotFound, ActiveProjectError
    or NoActiveProject instead of guessing.
    """
    pin = pinned_config_path()
    if pin is not None:
        if not pin.is_file():
            raise ConfigNotFound(f"{ENV_CONFIG} points to {pin}, which does not exist.")
        return Resolution(pin, project_for_config(pin, root), "env")

    name = read_active_project(root)
    if name is not None:
        return Resolution(projects_dir(root) / name / "config.yaml", name, "marker")
    missing = no_active_project_message(root)
    if missing:
        raise NoActiveProject(missing)

    root_config = _root(root) / "config.yaml"
    if not root_config.is_file():
        raise ConfigNotFound(
            f"No active project and no config.yaml in {_root(root)}. Create a project "
            f"(create_project, or the web Projects page) or copy config.template.yaml "
            f"to config.yaml."
        )
    return Resolution(root_config, None, "root")


def resolve_config_path(root: str | Path | None = None) -> Path:
    return resolve(root).config_path


# ---------------------------------------------------------------------------
# Where a project may write its results
# ---------------------------------------------------------------------------


def _is_relative_to(path: Path, other: Path) -> bool:
    """``path`` is ``other`` or inside it (case-insensitive where the OS is)."""
    a, b = os.path.normcase(str(path)), os.path.normcase(str(other))
    return a == b or a.startswith(b.rstrip("\\/") + os.sep)


class UnsafeOutputDir(WorkspaceError, ValueError):
    """project.output_dir points somewhere a run must not write or clean up."""


def output_dir_problem(config: Config, root: str | Path | None = None) -> str | None:
    """Why ``config.output_dir`` is unsafe to run in, or None.

    A new search removes 02_dedup to 04_export under the output folder, so the
    folder must belong to this review: never a drive root, the home folder,
    the workspace root, projects/, a folder that contains the config's own
    folder, or another project's folder. A project's ``./prisma_output`` and
    the legacy root install's ``./prisma_output`` are fine.
    """
    out = config.output_dir.resolve()
    base = _root(root).resolve()
    pdir = projects_dir(root).resolve()
    cfg_dir = Path(config.config_path).resolve().parent if config.config_path else None

    reason = None
    if out.parent == out:
        reason = "a drive or filesystem root"
    elif _same_path(out, Path.home().resolve()):
        reason = "your home folder"
    elif _same_path(out, base) or _same_path(out, pdir):
        reason = "the workspace folder" if _same_path(out, base) else "the projects folder"
    elif _is_relative_to(base, out) or _is_relative_to(pdir, out):
        reason = "a folder that contains the workspace"
    elif cfg_dir is not None and _is_relative_to(cfg_dir, out) and not _same_path(cfg_dir, out):
        reason = "a folder that contains this review's config"
    elif cfg_dir is not None and _is_relative_to(cfg_dir, pdir) and not _same_path(cfg_dir, pdir) \
            and _is_relative_to(out, pdir) and not _is_relative_to(out, cfg_dir):
        reason = "inside another project's folder"
    if reason is None:
        return None
    return (f"project.output_dir resolves to {out}, which is {reason}. A new search deletes the "
            f"result folders (02_dedup to 04_export) under it, so it must be a folder of its "
            f"own: set project.output_dir to ./prisma_output.")


def check_output_dir(config: Config, root: str | Path | None = None) -> None:
    """Raise UnsafeOutputDir if ``output_dir_problem`` finds a problem."""
    problem = output_dir_problem(config, root)
    if problem:
        raise UnsafeOutputDir(problem)


def set_active_project(name: str, root: str | Path | None = None) -> None:
    """Make ``name`` the active project (validated; the marker is written atomically)."""
    validate_project_name(name, root)
    cfg = projects_dir(root) / name / "config.yaml"
    if not cfg.is_file():
        raise ProjectNotFound(f"Project {name!r} not found (no {cfg}).")
    atomic_write_text(marker_path(root), name)


def clear_active_project(root: str | Path | None = None) -> None:
    try:
        marker_path(root).unlink()
    except FileNotFoundError:
        pass


# ---------------------------------------------------------------------------
# Creating projects
# ---------------------------------------------------------------------------


def _fallback_config() -> dict:
    return {
        "project": {},
        "api_keys": {"scopus": "", "openalex_key": "", "openalex_email": ""},
        "search": {"date_range": {"start": "2015-01-01", "end": "2026-12-31"},
                   "max_results_per_query": 500, "sources": ["openalex"], "queries": []},
        "dedup": {"doi_match": True, "fuzzy_title_threshold": 90},
        "screening": {"rules": {"include_keywords": [], "exclude_keywords": [],
                                "min_include_hits": 2, "required_keywords": []}},
    }


def _template_config() -> dict:
    try:
        return load_raw_config(template_path())
    except (OSError, ValueError, yaml.YAMLError):
        return _fallback_config()


def _current_api_keys(root: str | Path | None) -> dict:
    """API keys of the config currently in use, carried into new projects."""
    try:
        keys = load_raw_config(resolve(root).config_path).get("api_keys")
    except (WorkspaceError, OSError, ValueError):
        return {}
    return dict(keys) if isinstance(keys, dict) else {}


def create_project(display_name: str, root: str | Path | None = None) -> str:
    """Create projects/<slug>/ from the config template and return the slug.

    The new config carries the API keys of the config currently in use. Does
    not switch the active project.
    """
    display_name = str(display_name or "").strip()
    if not display_name:
        raise InvalidProjectName("The project name must not be empty.")
    slug = validate_project_name(slugify(display_name), root)
    pdir = projects_dir(root)
    with project_lock(pdir):
        dest = pdir / slug
        if dest.exists():
            raise ProjectExists(f"Project '{slug}' already exists.")
        cfg = _template_config()
        project = cfg.get("project") if isinstance(cfg.get("project"), dict) else {}
        project["name"] = display_name
        project["output_dir"] = "./prisma_output"
        cfg["project"] = project
        api_keys = _current_api_keys(root)
        if api_keys:
            cfg["api_keys"] = api_keys
        dest.mkdir(parents=True)
        save_raw_config(dest / "config.yaml", cfg)
        (dest / "prisma_output").mkdir(exist_ok=True)
    return slug


def migrate_root_to_projects(root: str | Path | None = None) -> str | None:
    """Move a root-only install into projects/ (config copied, output copied, marker set).

    Runs only when there is no marker, a root config.yaml exists and projects/
    holds no other project (so a deleted active project is never replaced by
    the root review); the root files are left in place. Never overwrites an
    existing project: if projects/<slug>/config.yaml already exists it is
    assumed to be an earlier migration of the same review and simply becomes
    active. Returns the project name that became active, or None if nothing
    was done.
    """
    base = _root(root)
    pdir = projects_dir(base)
    root_config = base / "config.yaml"
    if marker_path(base).exists() or not root_config.is_file():
        return None
    with project_lock(pdir):
        if marker_path(base).exists():
            return None
        cfg = load_raw_config(root_config)
        old_output = Config(cfg, base_dir=base).output_dir
        project = cfg.get("project") if isinstance(cfg.get("project"), dict) else {}
        slug = validate_project_name(slugify(project.get("name") or "default-project"), base)
        if any(name != slug for name in projects_with_config(base)):
            return None
        dest = pdir / slug
        if not (dest / "config.yaml").exists():
            dest.mkdir(parents=True, exist_ok=True)
            project["output_dir"] = "./prisma_output"
            cfg["project"] = project
            save_raw_config(dest / "config.yaml", cfg)
            dest_output = dest / "prisma_output"
            if old_output.is_dir() and not dest_output.exists():
                shutil.copytree(old_output, dest_output,
                                ignore=shutil.ignore_patterns(LOCK_FILENAME))
        atomic_write_text(marker_path(base), slug)
    return slug
