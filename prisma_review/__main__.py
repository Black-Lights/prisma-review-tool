"""Allow running as: python -m prisma_review <command>"""

from .deps import exit_if_missing

exit_if_missing()  # an environment from an older version: say how to update it

from .cli import main  # noqa: E402

main()
