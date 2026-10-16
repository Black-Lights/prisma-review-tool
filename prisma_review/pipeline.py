"""Pipeline runs shared by the web API, the MCP server and the CLI.

Run ownership: a run is recorded in the ``pipeline`` block of
review_state.json together with the process that owns it (``owner_pid``,
``owner_host``), a ``heartbeat_at`` the owner refreshes while it runs, its
``session_id`` and a ``cancel_requested`` flag. Any process can then tell a live
run from one whose process died (a crash, Ctrl+C, ``--reload``, a closed Claude
session), refuse to start a second run on the same project, and ask the owner
to stop.

Steps: ``search_step`` and ``dedup_step`` are the one implementation of those
steps (screening is ``screen.rescreen``), so the counts are the same whichever
front end runs them.
"""

from __future__ import annotations

import os
import shutil
import socket
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .config import KNOWN_SOURCES, Config
from .dedup import deduplicate, save_dedup_log
from .models import load_papers, save_papers
from .search.filters import filter_warnings
from .search.query_plan import query_warnings
from .search.runner import run_all_searches
from .stats import count_by_source
from .storage import project_lock, read_json, update_state

# The owner refreshes its heartbeat this often while a run is going ...
HEARTBEAT_SECONDS = 5.0
# ... and a "running" block whose heartbeat is older than this is not running.
STALE_SECONDS = 45.0

CANCEL_MESSAGE = "Cancellation requested, stopping after the current step..."
INTERRUPTED_MESSAGE = "Pipeline was interrupted: the process running it stopped before it finished"

STEPS = ("search", "dedup", "screen")


class RunActiveError(RuntimeError):
    """A pipeline is running on this project (in this or another process)."""


class StepError(RuntimeError):
    """A step has nothing to work on (e.g. dedup before any search)."""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Is the owner alive?
# ---------------------------------------------------------------------------

_win_api = None


def _windows_api():
    global _win_api
    if _win_api is None:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.GetExitCodeProcess.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
        kernel32.GetExitCodeProcess.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
        kernel32.CloseHandle.restype = wintypes.BOOL
        _win_api = (ctypes, wintypes, kernel32)
    return _win_api


def pid_alive(pid: Any) -> bool:
    """Whether a process with this id is running on this machine."""
    if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
        return False
    if pid == os.getpid():
        return True
    if sys.platform == "win32":
        # Never os.kill(pid, 0) on Windows: it terminates the process.
        ctypes, wintypes, kernel32 = _windows_api()
        handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return ctypes.get_last_error() == 5  # access denied: it exists, owned by someone else
        try:
            code = wintypes.DWORD()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return True
            return code.value == 259  # STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def owner_fields() -> dict:
    """The ``pipeline`` block fields that say this process owns a run, with a fresh heartbeat."""
    return {"owner_pid": os.getpid(), "owner_host": socket.gethostname(), "heartbeat_at": now_iso()}


def run_is_live(block: Any) -> bool:
    """True if ``block`` records a run whose owner is alive and still beating."""
    if not isinstance(block, dict) or block.get("status") != "running":
        return False
    beat = _parse_time(block.get("heartbeat_at"))
    if beat is None:  # written by an older version: nothing proves it still runs
        return False
    if (datetime.now(timezone.utc) - beat).total_seconds() > STALE_SECONDS:
        return False
    host = block.get("owner_host")
    if host and host != socket.gethostname():
        return True  # a shared folder used from another machine: trust the heartbeat
    return pid_alive(block.get("owner_pid"))


def read_run(state_file: str | Path | None) -> dict | None:
    """The ``pipeline`` block of a state file, or None."""
    if state_file is None:
        return None
    try:
        state = read_json(state_file, default={}, recover_trailing_data=True)
    except (OSError, ValueError):
        return None
    block = state.get("pipeline") if isinstance(state, dict) else None
    return block if isinstance(block, dict) else None


def active_run(state_file: str | Path | None) -> dict | None:
    """The live run recorded for a project, or None."""
    block = read_run(state_file)
    return block if run_is_live(block) else None


def describe_run(block: dict) -> str:
    step = block.get("current_step")
    return (f"A pipeline is running on this project (session {block.get('session_id') or '?'}, "
            f"process {block.get('owner_pid') or '?'}"
            + (f", step {step}" if step else "") + ").")


def interrupted(block: dict) -> dict:
    """``block`` recorded as failed because its owner stopped."""
    return {**block, "status": "failed", "progress_message": INTERRUPTED_MESSAGE,
            "error": block.get("error") or ("Interrupted: the process that ran this pipeline "
                                            "exited or stopped responding."),
            "finished_at": block.get("finished_at") or now_iso(), "cancel_requested": False}


def reconcile_stale_run(state_file: str | Path | None) -> dict | None:
    """Record a "running" block whose owner is gone as failed, on disk. Returns the block."""
    block = read_run(state_file)
    if block is None or block.get("status") != "running" or run_is_live(block):
        return block
    fixed: dict = {}

    def fix(state: dict) -> None:
        current = state.get("pipeline")
        if isinstance(current, dict) and current.get("status") == "running" \
                and not run_is_live(current):
            state["pipeline"] = interrupted(current)
        fixed["block"] = state.get("pipeline")

    try:
        update_state(state_file, fix, timeout=10)
    except (OSError, TimeoutError, ValueError):
        return interrupted(block)
    return fixed.get("block")


def request_cancel_on_disk(state_file: str | Path | None) -> bool:
    """Ask the process running this project's pipeline to stop. False if none is running."""
    if active_run(state_file) is None:
        return False
    done = {"ok": False}

    def mark(state: dict) -> None:
        block = state.get("pipeline")
        if run_is_live(block):
            block["cancel_requested"] = True
            block["progress_message"] = CANCEL_MESSAGE
            done["ok"] = True

    update_state(state_file, mark)
    return done["ok"]


# ---------------------------------------------------------------------------
# Steps
# ---------------------------------------------------------------------------


def pre_search_warnings(config: Config) -> list[str]:
    """How each source handles the queries and filters (shown before a search runs)."""
    warnings: list[str] = []
    for fn in (query_warnings, filter_warnings):
        try:
            warnings += list(fn(config))
        except Exception as exc:  # noqa: BLE001 - a malformed config must not stop the run
            warnings.append(f"Could not compute {fn.__name__}: {exc}")
    return warnings


def status_warnings(status_log: list[dict]) -> list[str]:
    """One warning per search request that did not complete normally."""
    warnings = []
    for entry in status_log:
        status = entry.get("status")
        if status in ("ok", "cancelled", None):
            continue
        text = f"{entry.get('source')}, query '{entry.get('query')}': {status}"
        if entry.get("error"):
            text += f": {entry['error']}"
        if status == "partial" and entry.get("api_total") is not None:
            text += f" (retrieved {entry.get('retrieved')} of {entry['api_total']})"
        warnings.append(text)
    return warnings


def _clear_downstream(config: Config) -> None:
    """Remove dedup, screening, eligibility and export results (they belong to the old search)."""
    for path in (config.dedup_dir, config.screen_dir, config.eligibility_dir, config.export_dir):
        if path.exists():
            shutil.rmtree(path)
        path.mkdir(parents=True, exist_ok=True)
    (config.output_dir / "05_pdfs" / "_download_log.json").unlink(missing_ok=True)


def search_step(config: Config, *, should_cancel: Callable[[], bool] | None = None,
                replace_downstream: bool = False) -> dict:
    """Search every configured source and save 01_search/all_records.json.

    Counts records per source from each paper's ``source``. Requests that
    failed or returned partial results become warnings, as does a source
    that returned nothing. A cancelled search saves nothing, so the previous
    results stay. With ``replace_downstream`` (the web and MCP pipelines) the
    old dedup, screening, eligibility and export results are removed once the
    new records are in. Returns {status, total, sources, warnings}.
    """
    status_log: list[dict] = []
    results = run_all_searches(config, status_log=status_log, should_cancel=should_cancel)
    papers = [p for batch in results.values() for p in batch]
    counts = count_by_source(papers)

    warnings = status_warnings(status_log)
    reported = {e.get("source") for e in status_log if e.get("status") not in ("ok", None)}
    for source in config.sources:
        if source in KNOWN_SOURCES and not counts.get(source) and source not in reported:
            warnings.append(f"{source}: returned 0 results"
                            + ("" if status_log else " (possible rate limiting or API error)"))

    cancelled = any(e.get("status") == "cancelled" for e in status_log) \
        or bool(should_cancel and should_cancel())
    outcome = {"status": "cancelled" if cancelled else "ok", "total": len(papers),
               "sources": counts, "warnings": warnings}
    if cancelled:
        return outcome

    with project_lock(config.output_dir):
        if replace_downstream:
            _clear_downstream(config)
        save_papers(papers, config.search_dir / "all_records.json")

        def apply(state: dict) -> None:
            if replace_downstream:
                for key in ("dedup", "screen", "eligibility"):
                    state.pop(key, None)
            state["search"] = {**counts, "total": len(papers)}

        update_state(config.state_file, apply)
    return outcome


def dedup_step(config: Config) -> dict:
    """Deduplicate 01_search/all_records.json into 02_dedup. Raises StepError without records."""
    papers = load_papers(config.search_dir / "all_records.json")
    if not papers:
        raise StepError("No papers found. Run search first.")
    unique, log = deduplicate(papers, config.doi_match, config.fuzzy_threshold)
    removed = len(papers) - len(unique)
    with project_lock(config.output_dir):
        save_papers(unique, config.dedup_dir / "deduplicated.json")
        save_dedup_log(log, config.dedup_dir / "duplicates_log.csv")
        update_state(config.state_file, lambda state: state.__setitem__(
            "dedup", {"duplicates_removed": removed, "remaining": len(unique)}))
    return {"status": "ok", "duplicates_removed": removed, "remaining": len(unique)}
