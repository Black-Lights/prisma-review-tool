"""Launcher for the MCP server (puts the install folder on sys.path first)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from prisma_review.deps import MCP_MODULES, exit_if_missing

exit_if_missing(MCP_MODULES)  # an environment from an older version: say how to update it

from mcp_server.server import main  # noqa: E402

if __name__ == "__main__":
    main()
