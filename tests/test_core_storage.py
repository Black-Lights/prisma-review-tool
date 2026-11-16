"""Atomic writes and cross-process locking for the shared review files (MCP#11, PIPE#2)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
import threading
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _run_workers(script: str, args_list: list[list[str]], timeout: float = 180) -> list[str]:
    """Run ``script`` in one Python process per args entry, concurrently; return stdouts."""
    procs = [
        subprocess.Popen([sys.executable, "-c", script, *args], cwd=ROOT,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        for args in args_list
    ]
    outs = []
    for p in procs:
        out, err = p.communicate(timeout=timeout)
        assert p.returncode == 0, err
        outs.append(out.strip())
    return outs


# --------------------------------------------------------------------------- atomic writes


def test_atomic_write_json_leaves_no_temp_files(tmp_path):
    from prisma_review.storage import atomic_write_json, read_json

    target = tmp_path / "sub" / "data.json"
    atomic_write_json(target, {"a": 1})
    atomic_write_json(target, {"a": 2, "b": "é"}, ensure_ascii=False)
    assert read_json(target) == {"a": 2, "b": "é"}
    assert [p.name for p in target.parent.iterdir()] == ["data.json"]


def test_atomic_write_retries_windows_permission_error(tmp_path, monkeypatch):
    import prisma_review.storage as storage

    real_replace = os.replace
    calls = {"n": 0}

    def flaky_replace(src, dst):
        calls["n"] += 1
        if calls["n"] < 3:
            raise PermissionError(13, "The process cannot access the file")
        return real_replace(src, dst)

    monkeypatch.setattr(storage.os, "replace", flaky_replace)
    target = tmp_path / "state.json"
    storage.atomic_write_text(target, "ok")
    assert target.read_text(encoding="utf-8") == "ok"
    assert calls["n"] == 3


def test_atomic_write_failure_keeps_old_file_and_cleans_temp(tmp_path, monkeypatch):
    import prisma_review.storage as storage

    target = tmp_path / "state.json"
    target.write_text("old", encoding="utf-8")
    monkeypatch.setattr(storage, "_RETRY_SECONDS", 0.05)

    def always_denied(src, dst):
        raise PermissionError(13, "denied")

    monkeypatch.setattr(storage.os, "replace", always_denied)
    with pytest.raises(PermissionError):
        storage.atomic_write_text(target, "new")
    assert target.read_text(encoding="utf-8") == "old"
    assert [p.name for p in tmp_path.iterdir()] == ["state.json"]


def test_load_state_recovers_from_trailing_bytes(tmp_path):
    # The corruption the old in-place writers produced: a complete document
    # followed by the tail of a longer, older one.
    from prisma_review.diagram import load_state

    state_file = tmp_path / "review_state.json"
    state_file.write_text('{"screen": {"included": 3}}\n  "maybe": 4}\n}', encoding="utf-8")
    assert load_state(state_file) == {"screen": {"included": 3}}


# --------------------------------------------------------------------------- locks


def test_project_lock_is_reentrant_and_cached(tmp_path):
    from prisma_review.storage import project_lock, _lock_for

    with project_lock(tmp_path):
        with project_lock(tmp_path / "." ):
            pass
    assert _lock_for(tmp_path) is _lock_for(str(tmp_path) + os.sep)


def test_project_lock_excludes_other_threads(tmp_path):
    from prisma_review.storage import project_lock

    order: list[str] = []
    entered = threading.Event()

    def holder():
        with project_lock(tmp_path):
            order.append("holder-in")
            entered.set()
            time.sleep(0.3)
            order.append("holder-out")

    t = threading.Thread(target=holder)
    t.start()
    entered.wait(5)
    with project_lock(tmp_path):
        order.append("main-in")
    t.join()
    assert order == ["holder-in", "holder-out", "main-in"]


def test_project_lock_excludes_other_processes(tmp_path):
    from prisma_review.storage import project_lock

    probe = textwrap.dedent("""
        import sys
        from prisma_review.storage import project_lock
        try:
            with project_lock(sys.argv[1], timeout=0.3):
                print("acquired")
        except TimeoutError:
            print("timeout")
    """)
    with project_lock(tmp_path):
        assert _run_workers(probe, [[str(tmp_path)]]) == ["timeout"]
    assert _run_workers(probe, [[str(tmp_path)]]) == ["acquired"]


# --------------------------------------------------------------------------- two processes


_SAVE_STATE_WORKER = textwrap.dedent("""
    import json, sys
    from pathlib import Path
    from prisma_review.diagram import load_state, save_state
    role, path, n = sys.argv[1], Path(sys.argv[2]), int(sys.argv[3])
    errors = 0
    for i in range(n):
        try:
            st = load_state(path)
        except json.JSONDecodeError:
            errors += 1
            continue
        if role == "api":
            st["pipeline"] = {"status": "running", "msg": "x" * (i % 400), "seq": i}
        else:
            st["screen"] = {"included": i, "pad": "y" * (i % 700)}
        save_state(st, path)
    print(errors)
""")


def test_concurrent_save_state_never_corrupts_the_file(tmp_path):
    # PIPE#2 repro: the API pipeline thread and the MCP server rewrite
    # review_state.json from two processes. In-place writes left trailing
    # bytes ("Extra data") within seconds.
    state_file = tmp_path / "review_state.json"
    state_file.write_text(json.dumps({"search": {"total": 1}}), encoding="utf-8")
    outs = _run_workers(_SAVE_STATE_WORKER,
                        [["api", str(state_file), "200"], ["mcp", str(state_file), "200"]])
    assert outs == ["0", "0"], f"JSONDecodeError counts per process: {outs}"
    final = json.loads(state_file.read_text(encoding="utf-8"))
    assert final["search"] == {"total": 1}


_UPDATE_STATE_WORKER = textwrap.dedent("""
    import sys
    from pathlib import Path
    from prisma_review.storage import update_state
    key, path, n = sys.argv[1], Path(sys.argv[2]), int(sys.argv[3])

    def bump(state):
        state[key] = state.get(key, 0) + 1

    for _ in range(n):
        update_state(path, bump)
    print("done")
""")


def test_update_state_loses_no_updates_across_processes(tmp_path):
    state_file = tmp_path / "out" / "review_state.json"
    outs = _run_workers(_UPDATE_STATE_WORKER,
                        [["a", str(state_file), "100"], ["b", str(state_file), "100"]])
    assert outs == ["done", "done"]
    assert json.loads(state_file.read_text(encoding="utf-8")) == {"a": 100, "b": 100}


def test_update_state_returns_new_state_and_accepts_replacement(tmp_path):
    from prisma_review.storage import update_state

    state_file = tmp_path / "review_state.json"
    assert update_state(state_file, lambda s: s.update(x=1)) == {"x": 1}
    assert update_state(state_file, lambda s: {"y": 2}) == {"y": 2}
    assert json.loads(state_file.read_text(encoding="utf-8")) == {"y": 2}


def test_save_papers_is_atomic(tmp_path, monkeypatch):
    import prisma_review.storage as storage
    from prisma_review.models import Paper, load_papers, save_papers

    path = tmp_path / "03_screen" / "screen_results.json"
    save_papers([Paper(title="A", id="p1")], path)

    def boom(src, dst):
        raise PermissionError(13, "denied")

    monkeypatch.setattr(storage, "_RETRY_SECONDS", 0.05)
    monkeypatch.setattr(storage.os, "replace", boom)
    with pytest.raises(PermissionError):
        save_papers([Paper(title="B", id="p2")], path)
    assert [p.id for p in load_papers(path)] == ["p1"]
