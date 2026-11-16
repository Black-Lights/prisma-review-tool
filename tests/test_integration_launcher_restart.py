"""The launcher starts the web app again once if it quits with an error.

Next.js 16.4.4 quit on its first start after a security advisory (it prints a
notice and asks to be run again), and start.py then shut the whole app down.
"""

from __future__ import annotations

import importlib.util

from conftest import REPO_ROOT


def _load_launcher():
    spec = importlib.util.spec_from_file_location("prisma_start_launcher", REPO_ROOT / "start.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Proc:
    def __init__(self, code):
        self.code = code

    def poll(self):
        return self.code


def test_web_app_that_quits_with_an_error_is_started_once_more():
    launcher = _load_launcher()
    dead, fresh = _Proc(1), _Proc(None)
    processes = ["backend", dead]

    proc, left = launcher.restart_if_stopped(dead, lambda: fresh, processes, 1)

    assert proc is fresh and left == 0
    assert processes == ["backend", fresh]


def test_no_second_restart():
    launcher = _load_launcher()
    dead = _Proc(1)
    processes = [dead]

    proc, left = launcher.restart_if_stopped(dead, lambda: _Proc(None), processes, 0)

    assert proc is dead and left == 0 and processes == [dead]


def test_running_or_cleanly_stopped_web_app_is_left_alone():
    launcher = _load_launcher()
    for proc in (_Proc(None), _Proc(0)):
        processes = [proc]
        assert launcher.restart_if_stopped(proc, lambda: _Proc(None), processes, 1) == (proc, 1)
        assert processes == [proc]
