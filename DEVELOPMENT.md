# Development

Run `uv sync --frozen`, then `uv run python -m unittest discover -s tests -v`.
Tests use authored HTML fixtures, topology captures and local fake transports;
they require neither MD nor downloaded official documentation.

`uv build` produces wheel and sdist. Hatch includes md_addon and the launcher.
The single version source is src/marvelous_designer_mcp/__init__.py.
Validate the wheel in a fresh environment outside the checkout with PYTHONPATH
cleared. Test the CLI and real stdio client; editable installs are insufficient.

Manual/local only: scripts/live_agent.py, verify_agent_edges.py,
verify_gui_listener.py, verify_listener_lifecycle.py and verify_agent_mcp.py.
Inspect their preconditions first. Mutation regressions need a disposable Agent
scene and must preserve existing work.

Preserve SetTimer, serial GUI-thread calls, stable-reference validation and
operation receipts. Never automatically retry UNKNOWN. Restore invalidates refs.
Legacy cpp_plugin is an unverified experiment, not the supported installation.
