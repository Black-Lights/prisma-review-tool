"""Safe reads, writes and locking for the files the web API and MCP server share.

The web API and the MCP server are separate processes that read and rewrite
the same review files (``config.yaml``, ``review_state.json``, the screening
JSON files). Two rules keep those files intact:

* every write goes to a temp file in the same directory and is moved into
  place with ``os.replace``, so a reader never sees a half-written file;
* every read-modify-write runs under ``project_lock``, so two writers cannot
  interleave and silently drop each other's updates.
"""

from __future__ import annotations

import json
import os
import stat
import sys
import tempfile
import threading
import time
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import Any, Callable, Iterator

import yaml
from filelock import FileLock

LOCK_FILENAME = ".prisma.lock"
DEFAULT_LOCK_TIMEOUT = 60.0

# Windows refuses to replace (or briefly to open) a file that another process
# has open, e.g. a reader mid-read or an anti-virus scan. Retry for a while.
_RETRY_SECONDS = 5.0

_MISSING = object()


def _retry_on_permission(fn: Callable[..., Any], *args: Any) -> Any:
    deadline = time.monotonic() + _RETRY_SECONDS
    delay = 0.01
    while True:
        try:
            return fn(*args)
        except PermissionError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(delay)
            delay = min(delay * 2, 0.2)


# ---------------------------------------------------------------------------
# Writes
# ---------------------------------------------------------------------------


def atomic_write_text(path: str | Path, text: str, *, encoding: str = "utf-8") -> None:
    """Write ``text`` to ``path`` atomically (temp file in the same directory + ``os.replace``)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding=encoding, newline="") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        # mkstemp creates the file owner-only; keep the permissions of the file we replace.
        try:
            os.chmod(tmp, stat.S_IMODE(os.stat(path).st_mode))
        except OSError:
            os.chmod(tmp, 0o644)
        _retry_on_permission(os.replace, tmp, path)
    except BaseException:
        with suppress(OSError):
            os.unlink(tmp)
        raise


def atomic_write_json(path: str | Path, data: Any, *, indent: int | None = 2,
                      ensure_ascii: bool = True, default: Callable[[Any], Any] | None = None) -> None:
    """Serialise ``data`` as JSON and write it atomically."""
    text = json.dumps(data, indent=indent, ensure_ascii=ensure_ascii, default=default)
    atomic_write_text(path, text)


def atomic_write_yaml(path: str | Path, data: Any) -> None:
    """Serialise ``data`` as YAML (the style config.yaml uses) and write it atomically."""
    text = yaml.safe_dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False)
    atomic_write_text(path, text)


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------


def read_text(path: str | Path, *, encoding: str = "utf-8") -> str:
    """Read a whole text file, retrying briefly on a Windows sharing violation."""
    return _retry_on_permission(Path(path).read_text, encoding)


def read_json(path: str | Path, default: Any = _MISSING, *, recover_trailing_data: bool = False) -> Any:
    """Load a JSON file. Returns ``default`` when the file does not exist (if given).

    ``recover_trailing_data`` accepts a file holding one complete document
    followed by leftover bytes, which is how the old in-place writers corrupted
    ``review_state.json`` when two processes wrote it at once. The complete
    leading document is the most recent write; the leftover is discarded.
    """
    path = Path(path)
    if default is not _MISSING and not path.exists():
        return default
    try:
        text = read_text(path)
    except FileNotFoundError:
        if default is _MISSING:
            raise
        return default
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        if not recover_trailing_data or exc.msg != "Extra data":
            raise
        text = text.lstrip()
        data, end = json.JSONDecoder().raw_decode(text)
        print(f"Warning: ignored {len(text) - end} trailing bytes in {path} "
              f"(left by an interrupted write)", file=sys.stderr)
        return data


# ---------------------------------------------------------------------------
# Locks
# ---------------------------------------------------------------------------


class _DirLock:
    """A directory lock held across threads (RLock) and processes (lock file)."""

    def __init__(self, lock_path: Path) -> None:
        self.thread_lock = threading.RLock()
        # Threads are already serialised by thread_lock, so one shared counter is right.
        self.file_lock = FileLock(str(lock_path), thread_local=False)
        self.depth = 0


_locks: dict[str, _DirLock] = {}
_locks_guard = threading.Lock()


def _lock_for(directory: str | Path) -> _DirLock:
    """The single cached lock object for ``directory`` (keyed by its resolved path)."""
    directory = Path(directory).resolve()
    key = os.path.normcase(str(directory))
    with _locks_guard:
        lock = _locks.get(key)
        if lock is None:
            lock = _locks[key] = _DirLock(directory / LOCK_FILENAME)
        return lock


@contextmanager
def project_lock(output_dir: str | Path, *, timeout: float = DEFAULT_LOCK_TIMEOUT) -> Iterator[None]:
    """Hold the lock for a project's output directory (or any directory).

    Excludes other threads in this process and other processes (through a
    ``.prisma.lock`` file in the directory). Reentrant within a thread, so a
    helper that locks can call another helper that locks. Raises
    ``TimeoutError`` if the lock is not free within ``timeout`` seconds.
    """
    lock = _lock_for(output_dir)
    if not lock.thread_lock.acquire(timeout=timeout):
        raise TimeoutError(f"Timed out waiting for the lock on {output_dir}")
    try:
        if lock.depth == 0:
            Path(output_dir).mkdir(parents=True, exist_ok=True)
            lock.file_lock.acquire(timeout=timeout)  # filelock.Timeout is a TimeoutError
        lock.depth += 1
        try:
            yield
        finally:
            lock.depth -= 1
            if lock.depth == 0:
                lock.file_lock.release()
    finally:
        lock.thread_lock.release()


def update_state(state_file: str | Path, fn: Callable[[dict], dict | None], *,
                 timeout: float = DEFAULT_LOCK_TIMEOUT) -> dict:
    """Read-modify-write ``review_state.json`` under the project lock.

    ``fn`` receives the current state (``{}`` if the file does not exist yet)
    and either mutates it in place (returning None) or returns a replacement.
    The result is written atomically and returned.
    """
    state_file = Path(state_file)
    with project_lock(state_file.parent, timeout=timeout):
        state = read_json(state_file, default={}, recover_trailing_data=True)
        if not isinstance(state, dict):
            state = {}
        new_state = fn(state)
        if new_state is not None:
            state = new_state
        atomic_write_json(state_file, state, indent=2)
        return state
