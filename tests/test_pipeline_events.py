"""Server-Sent Events (/api/events): bounded streams, versions and changed areas, one shared watcher.

Covers PIPE#3 (an open stream blocked shutdown and --reload), the server side of PIPE#4 and
PIPE#14 (version + areas so clients refetch only what changed) and PIPE#16 (config.yaml and the
download log watched, one stat per tick shared by every client, 15 s keepalive).
The endpoint is driven directly with a fake request so a never-ending stream fails, not hangs.
"""

from __future__ import annotations

import asyncio
import json
import threading

import pytest

from conftest import make_config, write_config, write_dataset
from prisma_review.diagram import load_state, save_state


class _FakeRequest:
    async def is_disconnected(self) -> bool:
        return False


def _collect(timeout: float = 6.0) -> str:
    """Run one /api/events stream to its end and return the raw body."""
    from api.routes import events

    async def run() -> str:
        response = await events.events(_FakeRequest())
        chunks: list[str] = []

        async def consume():
            async for chunk in response.body_iterator:
                chunks.append(chunk if isinstance(chunk, str) else chunk.decode())

        await asyncio.wait_for(consume(), timeout=timeout)
        return "".join(chunks)

    return asyncio.run(run())


def _data_events(body: str) -> list[dict]:
    return [json.loads(line[len("data: "):]) for line in body.splitlines() if line.startswith("data: ")]


@pytest.fixture
def fast_events(monkeypatch, workspace):
    import api.deps as deps
    from api.routes import events

    deps.reset_project_caches()
    monkeypatch.setattr(events, "POLL_SECONDS", 0.05, raising=False)
    monkeypatch.setattr(events, "STREAM_SECONDS", 1.2, raising=False)
    monkeypatch.setattr(events, "KEEPALIVE_SECONDS", 15.0, raising=False)
    write_dataset(workspace.output_dir("alpha"))
    yield events
    deps.reset_project_caches()


def _later(seconds: float, fn) -> threading.Timer:
    timer = threading.Timer(seconds, fn)
    timer.start()
    return timer


def test_stream_ends_by_itself_and_starts_with_retry_and_initial_event(fast_events):
    body = _collect()
    assert body.startswith("retry: 1000\n")
    first = _data_events(body)[0]
    assert first["initial"] is True and first["areas"] == ["all"]
    assert isinstance(first["version"], str) and first["version"]


@pytest.mark.parametrize("change, expected", [
    ("config", ["config"]),
    ("screen", ["screen"]),
    ("pipeline", ["pipeline"]),
    ("downloads", ["downloads"]),
])
def test_change_events_name_the_changed_area(fast_events, workspace, mcp_server, change, expected):
    out = workspace.output_dir("alpha")

    def make_change():
        if change == "config":
            write_config(workspace.project_config("alpha"), make_config("Renamed review"))
        elif change == "screen":
            mcp_server.screen_paper("p4", "include", "fits")
        elif change == "pipeline":
            state = load_state(out / "review_state.json")
            state["pipeline"] = {"status": "running", "heartbeat_at": "now"}
            save_state(state, out / "review_state.json")
        else:
            (out / "05_pdfs").mkdir(exist_ok=True)
            (out / "05_pdfs" / "_download_log.json").write_text("[]", encoding="utf-8")

    timer = _later(0.4, make_change)
    body = _collect()
    timer.join()
    events = _data_events(body)
    assert len(events) == 2, events
    assert events[1]["areas"] == expected
    assert events[1]["version"] != events[0]["version"]
    assert "initial" not in events[1]


def test_project_switch_is_its_own_area(fast_events, workspace):
    workspace.add_project("beta", active=False, dataset=True)
    timer = _later(0.4, lambda: workspace.set_marker("beta"))
    body = _collect()
    timer.join()
    events = _data_events(body)
    assert len(events) == 2 and "project" in events[1]["areas"]


def test_keepalive_comment_while_nothing_changes(fast_events, monkeypatch):
    monkeypatch.setattr(fast_events, "KEEPALIVE_SECONDS", 0.2, raising=False)
    body = _collect()
    assert ": keepalive" in body
    assert len(_data_events(body)) == 1


def test_one_disk_check_per_tick_for_all_clients(fast_events, monkeypatch):
    calls = [0]
    original = getattr(fast_events, "_compute_snapshot", None)

    def counting():
        calls[0] += 1
        return original()

    monkeypatch.setattr(fast_events, "_compute_snapshot", counting, raising=False)

    async def many():
        response_bodies = []

        async def one():
            response = await fast_events.events(_FakeRequest())
            async for _ in response.body_iterator:
                pass
            response_bodies.append(True)

        await asyncio.wait_for(asyncio.gather(*(one() for _ in range(8))), timeout=6)
        return response_bodies

    assert len(asyncio.run(many())) == 8
    # 8 clients polling every 0.05 s for 1.2 s would be ~190 checks if each did its own.
    assert 0 < calls[0] < 70, calls[0]
