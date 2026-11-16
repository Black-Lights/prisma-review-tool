"""What the web app's MCP Settings page shows: how to start the server and its tools.

The MCP server speaks stdio only: an agent starts ``run_mcp.py`` with the
install's Python. ``GET /api/mcp/setup`` gives the paths for this install
and the tools the server registers, so the page never goes out of date.
"""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi import APIRouter

from prisma_review import workspace

router = APIRouter(prefix="/mcp", tags=["mcp"])


def _python() -> Path:
    """The install's virtualenv Python (the one start.py creates), else this interpreter."""
    venv = workspace.INSTALL_DIR / ".venv"
    for candidate in (venv / "Scripts" / "python.exe", venv / "bin" / "python"):
        if candidate.is_file():
            return candidate
    return Path(sys.executable)


async def _tools() -> tuple[list[dict], str | None]:
    """Name and one-line summary of every tool the MCP server registers."""
    try:
        from mcp_server.server import mcp
        tools = await mcp.list_tools()
    except Exception as exc:  # noqa: BLE001 - the page then links to the docs instead
        return [], f"{type(exc).__name__}: {exc}"
    out = []
    for tool in tools:
        summary = (tool.description or "").strip().split("\n\n")[0]
        out.append({"name": tool.name, "description": " ".join(summary.split())})
    return out, None


@router.get("/setup")
async def mcp_setup():
    """Paths an agent's MCP config needs on this install, plus the tool list."""
    try:
        pinned_example = str(workspace.resolve().config_path)
    except workspace.WorkspaceError:
        pinned_example = None
    tools, tools_error = await _tools()
    return {
        "transport": "stdio",
        "command": _python().as_posix(),
        "script": (workspace.INSTALL_DIR / "run_mcp.py").as_posix(),
        "cwd": workspace.INSTALL_DIR.as_posix(),
        "active_config": Path(pinned_example).as_posix() if pinned_example else None,
        "tools": tools,
        "tools_error": tools_error,
    }
