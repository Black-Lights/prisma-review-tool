"""The MCP server over real stdio: identity, tools, and a stdout that carries only JSON-RPC."""

from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading

from conftest import REPO_ROOT, make_config, write_config, write_dataset


def _reader(stream, out: queue.Queue) -> None:
    for line in iter(stream.readline, b""):
        out.put(line)
    out.put(None)


def test_stdio_session(tmp_path):
    from mcp.types import LATEST_PROTOCOL_VERSION

    from prisma_review import __version__

    root = tmp_path / "ws"
    write_config(root / "projects" / "alpha" / "config.yaml", make_config("Alpha review"))
    write_dataset(root / "projects" / "alpha" / "prisma_output")
    (root / "projects" / ".active_project").write_text("alpha", encoding="utf-8")

    env = {**os.environ, "PRISMA_WORKSPACE": str(root)}
    env.pop("PRISMA_CONFIG", None)
    proc = subprocess.Popen([sys.executable, "run_mcp.py"], cwd=REPO_ROOT, env=env,
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    lines: queue.Queue = queue.Queue()
    threading.Thread(target=_reader, args=(proc.stdout, lines), daemon=True).start()

    def send(msg: dict) -> None:
        proc.stdin.write((json.dumps(msg) + "\n").encode())
        proc.stdin.flush()

    def receive() -> dict:
        line = lines.get(timeout=60)
        assert line is not None, "server closed stdout"
        return json.loads(line)  # anything but JSON-RPC on stdout fails here

    try:
        send({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": LATEST_PROTOCOL_VERSION, "capabilities": {},
            "clientInfo": {"name": "pytest", "version": "0"}}})
        init = receive()["result"]
        assert init["serverInfo"] == {**init["serverInfo"], "name": "prisma-review", "version": __version__}
        assert "get_review_config" in init["instructions"]
        send({"jsonrpc": "2.0", "method": "notifications/initialized"})

        send({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        names = {t["name"] for t in receive()["result"]["tools"]}
        assert {"get_review_config", "set_review_config", "switch_project", "start_pipeline"} <= names

        for i, tool in enumerate(("get_screening_stats", "list_projects"), start=3):
            send({"jsonrpc": "2.0", "id": i, "method": "tools/call",
                  "params": {"name": tool, "arguments": {}}})
            result = receive()["result"]
            assert not result.get("isError"), result
            payload = json.loads(result["content"][0]["text"])
            assert "error" not in payload
        assert payload["active"] == "alpha"
    finally:
        proc.stdin.close()
        try:
            proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            proc.kill()
    stderr = proc.stderr.read().decode(errors="replace")
    proc.stderr.close()
    proc.stdout.close()

    leftover = []
    while True:
        line = lines.get(timeout=10)
        if line is None:
            break
        leftover.append(line)
    for line in leftover:
        json.loads(line)
    assert f"prisma-review MCP server {__version__}" in stderr
    assert "project: alpha" in stderr
