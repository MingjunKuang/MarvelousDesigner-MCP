# Release installation validation — 0.3.0

Date: 2026-09-19. Scope: packaging, installation, diagnostics, runtime guidance,
security and documentation. Existing FastMCP/stdio/TCP/Windows SetTimer architecture
is preserved. **42 tools; 66 passing offline unit tests.**

## Release status

Wheel installation and live stdio operations passed in a fresh environment outside
the clone. The copied bridge ran inside real MD, with both module paths verified
to point into the copied installation directory.

The complete newcomer GUI registration flow needs independent verification.
Bridge deployment and registration/uninstall were tested with MD_MCP_DATA_DIR
and a temporary version-2 registry. The copied launcher ran on the real MD GUI
thread via an existing bridge session. Default registry registration and startup
from a newly registered menu item remain unverified.

## Installation and public entry points

- `uv tool install <release.whl>` or `pip install <release.whl>`.
- Both accept `git+https://github.com/Laboon2501/MarvelousDesigner-MCP.git`.
- `md-mcp install-plugin` copies the packaged bridge into
  `%LOCALAPPDATA%\marvelous-designer-mcp\plugin\` by default.
- Registered launcher: `plugin/scripts/md_start_listener.py`; companion modules
  live in `plugin/md_addon/`. No installed plugin path points at the clone.
- Installer backs up valid version-2 settings, preserves unrelated plugins and
  reports accurate manual +ADD steps when registry/menu discovery is insufficient.
- Use `--menu` for a localized menu tree and `--config` for a custom registry.
- Start MD, then Plugins → Plug-in → md_start_listener; Chinese UI:
  插件 → 插件 → md_start_listener. Close MD before automatic registry edits.
- Client command: `md-mcp serve`. Codex and Claude stdio configurations are in
  examples/codex-config.toml and examples/claude-mcp.json.
- CLI also provides doctor, update-docs, uninstall-plugin and version.

## New-user package validation

External Python 3.13.5, Windows 11, MD API 2026.0.315, embedded Python 3.11.8.
The final environment was created empty and installed from the wheel using
`uv pip install`; it was not an editable installation. A prior clean test found
that unconstrained mcp pulled SDK 2.x, where FastMCP had been removed. The package
now declares `mcp>=1.26,<2`; the final clean resolution selected 1.30.0.

| Check | Result |
| --- | --- |
| Wheel + sdist build | Passed; wheel built from sdist |
| Wheel assets | Packaged launcher and both bridge modules present |
| Distribution contents | No runtime artifacts, downloaded HTML or SQLite docs index |
| CLI help/version | Passed, 0.3.0 |
| Fresh installed-package unit tests | 66 passed |
| Plugin copying | Passed using explicit temporary user-data override |
| Registry backup/install/uninstall | Passed against temporary version-2 registry |
| Real default registry / new menu launch | Pending independent GUI verification |
| Copied bridge inside real MD | Passed; loaded module paths checked |
| Doctor with explicit test registry | Version, plugin files, TCP ping, runtime APIs and docs checked |
| Actual stdio initialize/tools/list | Passed, instructions delivered and 42 schemas |
| ping/environment_info/scene/topology | Passed |
| Checkpoint → create test pattern → readback | Passed, count and name verified |
| ZPRJ save / OBJ export | Passed, fresh file evidence and SHA-256 |
| Restore checkpoint → verify | Passed, original two-pattern test scene restored |
| shutdown_listener | Passed; subsequent doctor reports unavailable without traceback |
| Uninstall | Removed exactly the owned temporary registration; retained files |

The server subprocess used an output directory outside the checkout as cwd and
had PYTHONPATH removed. The validation script was copied outside the clone and
run with the fresh installed environment. See scripts/verify_release.py for the
reproducible manual test. Local evidence is intentionally excluded from Git.

Final artifacts: ZPRJ **170657 bytes**, valid ZIP CRC; OBJ **28854 bytes**,
**189 vertices / 307 faces**. Test pattern was removed by checkpoint restore.
The listener is stopped after the shutdown test. The original real MD plugin
registration and client configuration were preserved.

## Doctor output example

Sanitized summary of the actual explicit-test-registry run (not default registry):

```text
Marvelous Designer MCP Doctor
OS: Windows 11
Python: 3.13.5
MCP version: 0.3.0
data directory: <MD_MCP_DATA_DIR>
data writable: OK
MD Plugin: OK
TCP: 127.0.0.1:7421
listener ping: pong=true; windows_main_thread_timer
MD version: [2026, 0, 315]
runtime API: OK
docs index: 530 entries
Compatibility: VERIFIED version (Windows MD 2026.0.315)
```

With MD stopped or listener absent, doctor gives the menu startup instruction and
nonzero status; it does not dump a traceback. Registry presence alone is identified
as evidence of settings, not proof that an executable remains installed.

## Runtime guidance, security and storage

Server instructions and tool descriptions communicate inspection, stable refs,
runtime/doc validation, verification, checkpoints, UNKNOWN/reconciliation and
incremental orchestration. AGENTS.md is limited to repository development.
The pre-release pattern_placement tool is now **pattern_arrangement**; tool count
remains 42. No world-space transform semantics are claimed.

Raw Python can modify the scene and access embedded Python's filesystem/process
capabilities. It is not sandboxed. MD_MCP_ALLOW_RAW_PYTHON=0 refuses that MCP tool
without disabling internal semantic operations. Local TCP remains unauthenticated;
this switch does not block direct TCP clients. Connect trusted local clients only.

Default state root: `%LOCALAPPDATA%\marvelous-designer-mcp\`, overridable through
MD_MCP_DATA_DIR. Operations, checkpoints, docs, cache and logs live there, not in
site-packages. The copied launcher records its data root for logs. Package files
are only read during operation. Journals and scene caches can contain private data.

Official documentation is fetched by `md-mcp update-docs`, not redistributed.
The fresh download built **530 entries**. Observed documentation version 0.1 and
latest changelog 2025.1.201 lag MD 2026.0.315. `--offline` rebuilds downloaded pages.
CI parser/search tests use small authored synthetic fixtures, not this download.

Uninstall removes only an exact owned registration and backs up settings. It
retains projects, checkpoints, logs and bridge files. Externally edited/manual
entries are preserved with a manual-removal instruction.

## Checkpoint save-path investigation

Inspected official ExportZPrjW documentation and the running export_api signatures.
The available explicit overload takes `(path, bool)`; the bool creates thumbnails,
not a save-copy / preserve-active-path flag. No reliable path-preserving alternative
was established. No path-reset hack was introduced. Server instructions, tool help
and README disclose that checkpoint creation may change the active project path.

Restore checks hash/CRC and readable geometry, sewing ranges/directions, material
colors and avatar identity/properties. It does not prove every binary project field
is equivalent. IDs regenerated on reopen invalidate previous topology references.
Keep durable project saves outside the cache; at least the newest 20 checkpoints
are retained, older entries exceeding seven days are eligible for cleanup.

## Verified feature boundaries

Earlier live regressions on the same MD version established:

- UUID/name/native topology matching, stale/ambiguous reference rejection, outer
  endpoint edits; spline controls are distinct from native movable endpoints.
- Whole straight/curved outer/internal sewing including outer→internal and
  internal→internal cases. Partial/free sewing and deletion remain unverified.
- OBJ avatar import through ImportOBJW, type 0, explicit scale/axes; Unicode paths,
  append, scale 2 and Y/Z swap verified. FBX/AVT avatar assets remain unverified.
- FRONT/BACK/SIDE are 0/1/2. Independent BACK/SIDE color requires unlinking both
  material and color inheritance. Colorway assignment options are separate.
- Arrangement offsets 40/60/30 read back exactly; world XYZ/Euler semantics are
  not established.
- Explicit OBJ garment sampling can compare matching topology/UUID/epoch; no
  persistent vertex IDs, collision contacts or convergence guarantee. Native
  GetClothPositions returned an empty output list on the tested binding.
- Simulate steps are frames. Deliberately timed-out simulation/export could be
  reconciled after completion without resubmitting mutations.
- Earlier FBX export: 38864 bytes with valid binary header. This release's fresh
  installation smoke test exports ZPRJ/OBJ; it does not repeat every asset format.

Windows MD 2026.0.315 is the only live-verified version. Other Windows MD versions
are unverified, CLO is untested, and the timer bridge does not support macOS/Linux.
Synchronous MD calls can still pause the GUI; transport responsiveness is not API
asynchrony or cancellation. Large production projects need separate load testing.

## Tests and CI

66 offline tests: existing 58 plus 8 packaging/CLI/storage/raw-guard/registration/
runtime-description checks. New tests cover exact ownership, preserving unrelated
plugins/projects, external edits, unsupported schemas and unknown menu language.
The same suite passed against the final installed wheel.

GitHub Actions is configured for Windows/Linux and Python 3.10/3.13, offline unit
tests only. Remote workflow status is available on the repository Actions page.
Linux CI validates portable Python logic, not a Linux MD listener. All live tests
remain manual/local. Remaining release gate is the real default plugin registration
and GUI startup described above.
