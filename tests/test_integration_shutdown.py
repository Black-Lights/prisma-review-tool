"""The launcher bounds uvicorn's graceful shutdown (integration of PIPE#3).

Each /api/events stream lasts up to about 55 s. Without a bound, Ctrl+C and
--reload wait for every open browser tab's stream to end.
"""

from __future__ import annotations

import importlib
import importlib.util

from conftest import REPO_ROOT


def _load_launcher():
    spec = importlib.util.spec_from_file_location("prisma_start_launcher", REPO_ROOT / "start.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_launcher_bounds_graceful_shutdown():
    from api.routes import events

    uvicorn_cli = importlib.import_module("uvicorn.main").main  # the click command
    cmd = _load_launcher().backend_command(8021)
    assert cmd[1:3] == ["-m", "uvicorn"]
    ctx = uvicorn_cli.make_context("uvicorn", list(cmd[3:]))
    timeout = ctx.params["timeout_graceful_shutdown"]
    assert timeout is not None and 0 < timeout <= 5
    assert timeout < events.STREAM_SECONDS
    assert ctx.params["host"] == "127.0.0.1" and ctx.params["port"] == 8021
