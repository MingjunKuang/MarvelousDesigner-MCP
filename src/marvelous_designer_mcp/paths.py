"""Writable per-user state; never write into the installed package."""
import os
from pathlib import Path


def data_dir():
    override = os.environ.get('MD_MCP_DATA_DIR')
    if override:
        return Path(override).expanduser().resolve()
    base = Path(os.environ.get('LOCALAPPDATA', Path.home() / '.local' / 'share'))
    return base / 'marvelous-designer-mcp'


DATA_DIR = data_dir()
