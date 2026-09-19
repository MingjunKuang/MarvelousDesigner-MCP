"""Start the MCP listener inside Marvelous Designer.

Register this file using md-mcp install-plugin, or via
     `Plugins > Plug-in Manager > +ADD`, then click it under `Plugins > Plug-in`.
     One click instead of opening the editor and pasting.

Starts a nonblocking Windows GUI-thread timer listener on 127.0.0.1:7421.
The plugin returns immediately. Synchronous API calls still occupy the GUI
for their own duration. Stop it with the `shutdown_listener` MCP tool.

Repeated clicks reuse the active listener. Stop it before relaunching to pick up
code edits; restarting MD is not required.

Status / errors are appended to the user data directory's logs/listener.log,
where stdout may not be visible anywhere.
"""
import os
import sys
import traceback

from pathlib import Path
_PLUGIN_ROOT = Path(__file__).resolve().parent.parent
_DATA_FILE = _PLUGIN_ROOT / 'data-dir.txt'
_DATA_DIR = Path(os.environ.get('MD_MCP_DATA_DIR') or (
    _DATA_FILE.read_text(encoding='utf-8') if _DATA_FILE.is_file() else
    str(Path(os.environ.get('LOCALAPPDATA', Path.home() / '.local/share')) / 'marvelous-designer-mcp')))
(_DATA_DIR / 'logs').mkdir(parents=True, exist_ok=True)
_LOG_PATH = str(_DATA_DIR / 'logs' / 'listener.log')


def _log(msg: str) -> None:
    try:
        with open(_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(msg + "\n")
    except Exception:
        pass


# Locate md_addon relative to the registered launcher file.
try:
    _SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
    _ADDON_DIR = os.path.normpath(os.path.join(_SCRIPT_DIR, "..", "md_addon"))
except NameError:
    raise RuntimeError('Run this registered plugin file so __file__ is available')

if not os.path.isdir(_ADDON_DIR):
    raise RuntimeError('Cannot find md_addon next to this plugin: ' + _ADDON_DIR)

if _ADDON_DIR not in sys.path:
    sys.path.insert(0, _ADDON_DIR)

_log(f"--- md-mcp listener launch; addon dir = {_ADDON_DIR} ---")
try:
    import importlib
    import md_listener
    import md_event_listener
    _previous = getattr(sys, md_event_listener.STATE_KEY, None)
    if _previous is None or not _previous.running:
        importlib.reload(md_listener)
        importlib.reload(md_event_listener)
    _status = md_listener.serve_forever()
    _log('GUI timer listener started: ' + repr(_status))
except Exception:
    _log("LISTENER LAUNCH FAILED:\n" + traceback.format_exc())
    raise
