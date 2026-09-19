"""Verify the active launcher's idempotence without altering the MD scene."""
import json
from pathlib import Path
from marvelous_designer_mcp.bridge import call

root = Path(__file__).resolve().parents[1]
launcher = str(root / 'scripts/md_start_listener.py')
code = (
    'import sys, runpy\n'
    'before = id(sys._md_mcp_event_listener)\n'
    f'runpy.run_path({launcher!r})\n'
    f'runpy.run_path({launcher!r})\n'
    'result = dict(reused=before == id(sys._md_mcp_event_listener), '
    'status=sys._md_mcp_event_listener.status())'
)
out = call('execute_python', {'code': code}, timeout=3)
assert out['error'] is None and out['result']['reused'], out
out['post_launch_ping'] = call('ping', timeout=3)
(root / 'evidence/gui-listener-lifecycle.json').write_text(json.dumps(out, indent=2), encoding='utf-8')
print(json.dumps(out, indent=2))
