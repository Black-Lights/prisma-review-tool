"""Launcher for MCP server — avoids module import issues."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from mcp_server.server import mcp

if __name__ == "__main__":
    mcp.run(transport="stdio")
