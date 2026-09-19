"""Compatibility entry point for the installed CLI."""
import sys
from marvelous_designer_mcp.cli import main

if __name__ == "__main__":
    raise SystemExit(main(['update-docs'] + sys.argv[1:]))
