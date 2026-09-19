# Marvelous Designer MCP

[![English](https://img.shields.io/badge/English-selected-blue)](README.md) [![简体中文](https://img.shields.io/badge/简体中文-切换语言-green)](README.zh-CN.md)

Connect Claude, Codex and other MCP-compatible agents to local Marvelous Designer through its Python API.

## Quick Start

Requirements: Windows, Marvelous Designer **2026.0.315** with Python plug-ins, Python 3.10+ and pip or uv. Run MD and the MCP client as the same Windows user.

1. Install directly from GitHub (Git must be installed):

   ```powershell
   uv tool install git+https://github.com/Laboon2501/MarvelousDesigner-MCP.git
   # Alternative, in an activated Python environment:
   pip install git+https://github.com/Laboon2501/MarvelousDesigner-MCP.git
   ```

   Make the installed Scripts directory available on your MCP client's PATH. A local clone is only needed for development.

2. Launch MD once to create settings, close MD, then run `md-mcp install-plugin`.
   It prints the stable launcher path and registration result. If automatic registration cannot infer your menu language, follow the printed fallback: **Plugins → Plug-in Manager → +ADD**, select the printed `md_start_listener.py`, choose the plug-in menu and confirm. Alternatively pass `--menu "Plugins / Plug-in"` (Chinese: `--menu "插件 / 插件"`). Use `--config PATH` for a nonstandard pluginSettings.json.
3. Start MD and click **Plugins → Plug-in → md_start_listener** (Chinese: **插件 → 插件 → md_start_listener**). The launcher returns immediately. Run it again after restarting MD.
4. Run `md-mcp doctor`. Build optional documentation search with `md-mcp update-docs`.
5. Configure your client below, reload MCP connections and request `tools/list` and `ping`.

Starting the external server alone is insufficient: the MD listener must be running.

## Client configuration

Codex config.toml ([example](examples/codex-config.toml)):

```toml
[mcp_servers.marvelous-designer]
command = "md-mcp"
args = ["serve"]
startup_timeout_sec = 120
tool_timeout_sec = 660

[mcp_servers.marvelous-designer.env]
MD_MCP_TIMEOUT = "600"
PYTHONUTF8 = "1"
```

Claude Code project .mcp.json ([example](examples/claude-mcp.json)):

```json
{
  "mcpServers": {
    "marvelous-designer": {
      "command": "md-mcp",
      "args": ["serve"],
      "env": {"MD_MCP_TIMEOUT": "600", "PYTHONUTF8": "1"}
    }
  }
}
```

If a desktop client cannot find md-mcp, use the installed executable path reported by `Get-Command md-mcp`. Where supported, set client tool deadlines longer than the bridge timeout.

## Features and architecture

42 tools cover scene inspection, patterns, stable topology, whole-edge sewing, fabric/materials, OBJ avatars, simulation and mesh measurements, checkpoints, import/export, documentation search, runtime inspection and raw Python.

```text
Agent → MCP stdio → Marvelous Designer MCP Server
                         ↓ localhost TCP
                   MD Python Bridge Plugin
                         ↓
                   MD embedded Python API
```

The mandatory bridge uses Windows SetTimer and nonblocking sockets. MD API calls execute serially on the GUI thread. The GUI responds between requests; synchronous API calls can pause it until completion. See [GUI_FREEZE_FIX.md](GUI_FREEZE_FIX.md).

## Compatibility

| Environment | Status |
| --- | --- |
| Windows, MD 2026.0.315, embedded Python 3.11.8 | Verified |
| Other Windows MD versions | Unverified; inspect runtime APIs |
| CLO | Not tested |
| macOS/Linux MD bridge | Unsupported by the Windows timer implementation |
| External Python 3.10+ | Package requirement; CI matrix 3.10/3.13; live results in report |

Doctor compares the running version with the verified version. A match does not prove every possible API or workflow is tested. For a custom registry use `doctor --config PATH`. See [INSTALLATION_REPORT.md](INSTALLATION_REPORT.md) for validation coverage. Automatic registration against a real MD registry and startup from a newly registered menu still require independent verification.

## Plugin, data and documentation

Default data directory: `%LOCALAPPDATA%\marvelous-designer-mcp\`. Set `MD_MCP_DATA_DIR` to an absolute directory before installing/running to override. The copied launcher remembers that installation's data directory for logs.

```text
plugin/scripts/md_start_listener.py   # stable registered launcher
plugin/md_addon/                      # packaged bridge
operations/                          # journals and MD completion receipts
checkpoints/                         # ZPRJ and manifests
cache/simulation-samples/             # requested OBJ measurements
docs/html/                           # personally downloaded official pages
docs/md-docs.sqlite3                  # search index
logs/listener.log
```

Runtime writes never target the package or clone. To upgrade: stop the listener, upgrade the package, rerun install-plugin, then start the listener. Close MD before automated registration changes to prevent MD overwriting them at exit. Registry changes are backed up beside pluginSettings.json and preserve unrelated entries.

Official documentation bodies are **not distributed**. `md-mcp update-docs` downloads seven HTTPS pages from developer.marvelousdesigner.com and builds a local SQLite FTS5 index. `--offline` rebuilds cached HTML. Missing docs do not prevent server startup or scene tools. Documentation tools explain how to build the missing index. Runtime availability remains authoritative when docs lag MD.

| Variable | Default / meaning |
| --- | --- |
| MD_MCP_DATA_DIR | User data directory above |
| MD_MCP_DOCS_DB | Optional alternate docs database |
| MD_MCP_HOST / MD_MCP_PORT | Client endpoint 127.0.0.1:7421; listener remains loopback on 7421 |
| MD_MCP_TIMEOUT | 120 seconds; client examples use 600 |
| MD_MCP_ALLOW_RAW_PYTHON | Enabled; 0/false/no/off refuse the raw MCP tool |

## Security and safe operation

Connect trusted clients only. `execute_python` is **not a sandbox**: code can modify scenes and access files/process capabilities with MD's privileges. AST preflight is advisory. TCP is loopback-only but unauthenticated; other local processes can reach it. Disabling raw MCP execution is a client guard, not protection against direct TCP access. Semantic tools remain usable. See [SECURITY.md](SECURITY.md).

Inspect the scene and obtain stable refs from get_pattern_topology before changes; never guess indices. Use docs/runtime inspection for unfamiliar APIs. Verify each mutation. Orchestrate complex tasks incrementally.

Timeout does not cancel execution. Mutations are **UNKNOWN** until reconciled: pass the returned operation_id to reconcile_operation, inspect scene/output and never blindly retry. FAILED may include partial effects.

Prefer checkpoints before destructive changes. **create_checkpoint may affect the current project path depending on MD API behavior.** Do not assume the path remains unchanged. Restore replaces the scene and invalidates refs. Checkpoints retain at least the newest 20; older entries exceeding seven days are eligible for cleanup. Save durable projects elsewhere.

## Known limitations

- Whole outer/internal straight/curved edge sewing is verified; partial/free sewing and sewing deletion are not exposed as verified operations.
- pattern_arrangement controls arrangement parameters, **not a verified world-space transform** or Euler rotation. It replaces the pre-release pattern_placement name.
- Stable point movement supports verified outer endpoints; arbitrary spline controls/internal points remain unverified. Re-query after STALE_REFERENCE.
- Explicit OBJ avatar scale/axes/type=0 is verified; FBX/AVT avatar imports are unverified.
- OBJ mesh measurements have conditional index correspondence, not persistent vertex IDs, convergence or collision judgments.
- BACK/SIDE material edits unlink FRONT inheritance. Material faces differ from colorway assignment options.
- Long native calls/modal dialogs can still occupy the GUI. No cancellation is provided.

## Troubleshooting and uninstall

| Symptom | Action |
| --- | --- |
| Plugin absent | install-plugin; use manual fallback, refresh Plug-in Manager or restart MD |
| Listener unavailable | Start MD and run md_start_listener; check logs/listener.log |
| 7421 occupied | Doctor checks for a valid listener; stop it before restarting, do not kill unrelated processes |
| Version mismatch | Treat as unverified; inspect environment_info and inspect_md_api |
| Docs missing | update-docs; check network access to the official site |
| UNKNOWN timeout | Reconcile and inspect modal dialogs/scene/output before retry decisions |
| Client sees old tools | Reload MCP connection after upgrading |

Stop via shutdown_listener or close MD, then run `md-mcp uninstall-plugin`. Only the exact owned registration is removed, with a backup. Edited/manual entries require removal in Plug-in Manager. Copied bridge files, logs, checkpoints and user projects are retained. Remove the client configuration and uninstall the package with your original installer. Delete retained data manually only after preserving wanted files.

## Development

```powershell
uv sync --frozen
uv run python -m unittest discover -s tests -v
uv build
```

See [DEVELOPMENT.md](DEVELOPMENT.md). GitHub Actions runs offline unit tests; live MD integration is manual/local only. Runtime guidance is delivered through MCP server instructions and tool descriptions. Repository agent instruction files are development aids.

## License and acknowledgments

[MIT License](LICENSE). Based on [ysk424/marvelous-designer-mcp](https://github.com/ysk424/marvelous-designer-mcp); the original copyright and license notice are retained. Enhancements are distributed under the same license. See [NOTICE](NOTICE).

Marvelous Designer and its official documentation remain the property of their respective rights holders. This is an independent community project.
