"""Allow running as: python -m mcp_server"""

from prisma_review.deps import MCP_MODULES, exit_if_missing

exit_if_missing(MCP_MODULES)

from .server import main  # noqa: E402

main()
