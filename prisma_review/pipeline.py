"""Pipeline runs shared by the web API, the MCP server and the CLI.

Run ownership: a run is recorded in the ``pipeline`` block of
review_state.json together with the process that owns it (``owner_pid``,
``owner_host``), a ``heartbeat_at`` the owner refreshes while it runs, its
``session_id`` and a ``cancel_requested`` flag. Any process can then tell a live
run from one whose process died (a crash, Ctrl+C, ``--reload``, a closed Claude
session), refuse to start a second run on the same project, and ask the owner
to stop.

The web app and the MCP server run pipelines through ``api.session``; the CLI
and the synchronous API endpoints claim theirs with ``claimed_run``, so every
front end records its run the same way and refuses to start over another one.

Steps: ``search_step`` and ``dedup_step`` are the one implementation of those
steps (screening is ``screen.rescreen``), so the counts are the same whichever
front end runs them.
"""

from __future__ import annotations

import os
import shutil
import socket
import sys
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator

from . import workspace
from .config import KNOWN_SOURCES, Config
from .dedup import deduplicate, save_dedup_log
from .models import load_papers, save_papers
from .search.filters import filter_warnings
from .search.query_plan import query_warnings
from .search.runner import FAILED_SEARCH_LOG_NAME, run_all_searches, search_failed
from .stats import count_by_source
from .storage import atomic_write_json, project_lock, read_json, update_state

# The owner refreshes its heartbeat this often while a run is going ...
HEARTBEAT_SECONDS = 5.0
# ... and a "running" block whose heartbeat is older than this is not running.
STALE_SECONDS = 45.0

CANCEL_MESSAGE = "Cancellation requested, stopping after the current step..."
INTERRUPTED_MESSAGE = "Pipeline was interrupted: the process running it stopped before it finished"

STEPS = ("search", "dedup", "screen")

# 02_dedup/id_moves.json: {old id: kept id} for records a re-run of dedup merged
# into another one; screening reads it to carry their decisions across.
ID_MOVES_NAME = "id_moves.json"


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


class ClaimedRun:
    """A run this process recorded on disk with ``claimed_run``.

    A heartbeat thread keeps the record fresh and picks up a Stop requested
    from another process (``should_cancel``).
    """

    def __init__(self, state_file: Path, session_id: str) -> None:
        self.state_file = state_file
        self.session_id = session_id
        self.results: dict[str, Any] = {}
        self.warnings: list[str] = []
        self.outcome: tuple[str, str, str | None] | None = None  # (status, message, error)
        self._cancel = threading.Event()
        self._stop = threading.Event()

    def should_cancel(self) -> bool:
        return self._cancel.is_set()

    def _write(self, **fields: Any) -> bool:
        """Update this run's block (only while it is still this run's). False if it is not."""
        mine = {"ok": False}

        def apply(state: dict) -> None:
            block = state.get("pipeline")
            if not isinstance(block, dict) or block.get("session_id") != self.session_id:
                return
            mine["ok"] = True
            if block.get("cancel_requested"):
                self._cancel.set()
            block.update(fields)
            block["heartbeat_at"] = now_iso()

        update_state(self.state_file, apply)
        return mine["ok"]

    def step(self, name: str, message: str) -> None:
        """Record that step ``name`` starts."""
        self._write(current_step=name, progress_message=message)

    def step_done(self, name: str, result: Any = None, warnings: list[str] | None = None) -> None:
        """Record that step ``name`` finished with ``result`` (and its warnings)."""
        self.results[name] = result
        self.warnings.extend(warnings or [])
        self._write(completed_steps=list(self.results), warnings=list(self.warnings))

    def finish(self, status: str, message: str, error: str | None = None) -> None:
        """Set how the run ends (default: completed when the block exits normally)."""
        self.outcome = (status, message, error)

    def _beat(self) -> None:
        while not self._stop.wait(HEARTBEAT_SECONDS):
            try:
                if not self._write():
                    self._cancel.set()  # the record was replaced: stop at the next check
                    return
            except Exception:  # noqa: BLE001 - try again at the next beat
                pass


@contextmanager
def claimed_run(config: Config, owner: str) -> Iterator[ClaimedRun]:
    """Record a run of this process on the project for the duration of the block.

    Used by the CLI (``owner`` "cli") and the synchronous API endpoints
    ("api") so that they, like the web and MCP pipelines, refuse to run over
    a live run of another process (``RunActiveError``) and make every other
    front end refuse to start one, change decisions or re-screen meanwhile.
    The block ends the run as completed, or failed (cancelled on Ctrl+C) when
    it raises; ``ClaimedRun.finish`` sets another outcome.
    """
    state_file = Path(config.state_file)
    session_id = f"{owner}-{uuid.uuid4().hex[:8]}"
    started = now_iso()
    block = {
        "session_id": session_id, "status": "running", "current_step": None,
        "progress_message": f"Running from the {'command line' if owner == 'cli' else 'API'}...",
        "started_at": started, "finished_at": None, "completed_steps": [], "warnings": [],
        "error": None, "result": None, "cancel_requested": False, "owner": owner,
        **owner_fields(),
    }

    def claim(state: dict) -> None:
        current = state.get("pipeline")
        if run_is_live(current):
            raise RunActiveError(describe_run(current))
        state["pipeline"] = block

    update_state(state_file, claim)
    run = ClaimedRun(state_file, session_id)
    beat = threading.Thread(target=run._beat, daemon=True)
    beat.start()
    status, message, error = "completed", "Pipeline completed successfully", None
    try:
        yield run
        if run.outcome is not None:
            status, message, error = run.outcome
    except BaseException as exc:
        cancelled = isinstance(exc, KeyboardInterrupt)
        status = "cancelled" if cancelled else "failed"
        message = "Pipeline cancelled by user" if cancelled else f"Error: {exc}"
        error = None if cancelled else f"{type(exc).__name__}: {exc}"
        raise
    finally:
        run._stop.set()
        try:
            run._write(status=status, progress_message=message, error=error,
                       current_step=None, finished_at=now_iso(), result=run.results,
                       warnings=list(run.warnings), cancel_requested=False)
        except Exception:  # noqa: BLE001 - an unfinished record expires with its heartbeat
            pass


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


def _cap_text(entry: dict) -> str:
    kept, total = int(entry.get("retrieved") or 0), int(entry.get("api_total") or 0)
    text = f"kept {kept:,} of {total:,} matches (search.max_results_per_query)"
    if entry.get("source") == "crossref":
        text += ("; Crossref ranks loosely matching records by relevance, so the cap keeps "
                 "the top-ranked ones")
    return text


def status_warnings(status_log: list[dict]) -> list[str]:
    """One warning per search request that did not return every match normally.

    Covers requests that failed, were skipped or returned partial results,
    searches cut at max_results_per_query (the API matched more records than
    were kept), local filters that removed more than half of the records,
    and the source's own notes about the result.
    """
    warnings = []
    for entry in status_log:
        status = entry.get("status")
        if status == "cancelled":
            continue
        parts = []
        if status not in ("ok", None):
            text = str(status)
            if entry.get("error"):
                text += f": {entry['error']}"
            if status == "partial" and entry.get("api_total") is not None:
                text += f" (retrieved {entry.get('retrieved')} of {entry['api_total']})"
            parts.append(text)
        elif entry.get("capped_by_max_results"):
            parts.append(_cap_text(entry))
        retrieved, after = int(entry.get("retrieved") or 0), entry.get("after_post_filter")
        lost = retrieved - int(after or 0)
        if retrieved and after is not None and lost * 2 > retrieved:
            by = entry.get("removed_by_filter") or {}
            named = ", ".join(f"{k} {v}" for k, v in sorted(by.items(), key=lambda kv: -kv[1]))
            parts.append(f"the filters applied after the request removed {lost} of {retrieved} "
                         f"records" + (f" ({named})" if named else "")
                         + "; check the filter values (e.g. a venue name spelled differently)")
        parts += [note for note in entry.get("notes") or [] if note != entry.get("error")]
        if parts:
            warnings.append(f"{entry.get('source')}, query '{entry.get('query')}': "
                            + "; ".join(parts))
    return warnings


def capped_searches(status_log: list[dict]) -> list[dict]:
    """The (source, query) searches cut at max_results_per_query: {source, query, kept, matches}."""
    return [{"source": e.get("source"), "query": e.get("query"),
             "kept": int(e.get("retrieved") or 0), "matches": int(e.get("api_total") or 0)}
            for e in status_log if e.get("capped_by_max_results")]


def _clear_downstream(config: Config) -> None:
    """Remove dedup, screening, eligibility and export results (they belong to the old search).

    Raises ``workspace.UnsafeOutputDir`` (nothing removed) when the output
    folder is not one this review owns, e.g. a config that points it at the
    workspace or a drive root.
    """
    workspace.check_output_dir(config)
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
    that returned nothing. A cancelled search saves nothing, and neither does
    a failed one (no record came back and some request failed or was skipped,
    e.g. the network is down): the previous results stay and the status is
    ``failed`` with an ``error``. With ``replace_downstream`` (the web and MCP
    pipelines) the old dedup, screening, eligibility and export results are
    removed once the new records are in. Returns {status, total, sources,
    warnings} (plus ``error`` when failed).
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

    # Cancelled only if a request was: once every request has finished, the
    # runner has written search_log.json for this search, so its records are
    # saved to match, and a Stop that came later ends the run at the next step.
    cancelled = any(e.get("status") == "cancelled" for e in status_log)
    outcome = {"status": "cancelled" if cancelled else "ok", "total": len(papers),
               "sources": counts, "warnings": warnings}
    if cancelled:
        return outcome
    if search_failed(status_log):
        bad = sum(1 for e in status_log if e.get("status") in ("failed", "skipped"))
        outcome.update(status="failed", error=(
            f"The search returned no records: {bad} of {len(status_log)} requests failed or were "
            f"skipped (see the warnings and 01_search/{FAILED_SEARCH_LOG_NAME}). The previous "
            f"search results and everything based on them were kept."))
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


def _previous_ids(config: Config) -> set[str]:
    """Ids the current dedup and screening results use (decisions are keyed to them)."""
    ids = {p.id for p in load_papers(config.dedup_dir / "deduplicated.json")}
    ids |= {p.id for p in load_papers(config.screen_dir / "screen_results.json")}
    return ids


def _merge_moves(old: dict, new: dict, kept: set[str]) -> dict:
    """Old and new id moves with chains followed to a record that is still kept."""
    moves = {**(old if isinstance(old, dict) else {}), **new}
    out = {}
    for start in moves:
        target, seen = moves[start], {start}
        while target in moves and target not in seen and target not in kept:
            seen.add(target)
            target = moves[target]
        if target in kept and target != start:
            out[start] = target
    return out


def dedup_step(config: Config) -> dict:
    """Deduplicate 01_search/all_records.json into 02_dedup. Raises StepError without records.

    Re-running dedup over the same records keeps the ids the previous run
    kept, so screening and eligibility decisions stay attached. A record that
    was kept before and is now merged into another one is recorded in
    02_dedup/id_moves.json (old id -> kept id); the next screening carries its
    manual and AI decisions, and its eligibility decision, across the move.
    """
    papers = load_papers(config.search_dir / "all_records.json")
    if not papers:
        raise StepError("No papers found. Run search first.")
    previous = _previous_ids(config)
    unique, log = deduplicate(papers, config.doi_match, config.fuzzy_threshold,
                              prefer_ids=previous)
    removed = len(papers) - len(unique)
    kept = {p.id for p in unique}
    moved = {e["duplicate_id"]: e["canonical_id"] for e in log if e["duplicate_id"] in previous}
    with project_lock(config.output_dir):
        save_papers(unique, config.dedup_dir / "deduplicated.json")
        save_dedup_log(log, config.dedup_dir / "duplicates_log.csv")
        moves_file = config.dedup_dir / ID_MOVES_NAME
        moves = _merge_moves(read_json(moves_file, default={}), moved, kept)
        if moves:
            atomic_write_json(moves_file, moves, indent=2)
        else:
            moves_file.unlink(missing_ok=True)
        update_state(config.state_file, lambda state: state.__setitem__(
            "dedup", {"duplicates_removed": removed, "remaining": len(unique)}))
    return {"status": "ok", "duplicates_removed": removed, "remaining": len(unique),
            "ids_moved": len(moved)}
