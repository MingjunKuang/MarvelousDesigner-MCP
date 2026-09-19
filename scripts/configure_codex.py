"""Append only this MCP entry; validate TOML and retain an exact backup."""
from pathlib import Path
import datetime
import json
import os
import shutil
import tomllib

root = Path(__file__).resolve().parents[1]
config = Path(os.environ.get('CODEX_HOME', Path.home() / '.codex')) / 'config.toml'
before = config.read_bytes()
parsed = tomllib.loads(before.decode('utf-8'))
name = 'marvelous-designer'
if name in parsed.get('mcp_servers', {}):
    raise SystemExit('Entry already exists; inspect before changing it.')
executable = shutil.which('md-mcp')
if not executable:
    raise SystemExit('Install the package first so md-mcp is on PATH')
block = '\n\n[mcp_servers.marvelous-designer]\n'
block += 'command = ' + json.dumps(executable) + '\n'
block += 'args = ' + json.dumps(['serve']) + '\n'
block += 'startup_timeout_sec = 120\ntool_timeout_sec = 660\n'
block += '\n[mcp_servers.marvelous-designer.env]\nMD_MCP_TIMEOUT = "600"\nPYTHONUTF8 = "1"\n'
after = before + block.encode('utf-8')
checked = tomllib.loads(after.decode('utf-8'))
del checked['mcp_servers'][name]
assert checked == parsed, 'Unrelated configuration changed'
backup = config.with_name(config.name + '.before-md-' + datetime.datetime.now().strftime('%Y%m%d-%H%M%S') + '.bak')
backup.write_bytes(before)
assert config.read_bytes() == before, 'Config changed concurrently'
with config.open('ab') as f:
    f.write(block.encode('utf-8'))
assert config.read_bytes() == after
print(f'Added {name} to {config}; backup: {backup}')
