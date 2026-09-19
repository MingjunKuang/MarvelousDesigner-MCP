# Repository development

Read DEVELOPMENT.md and INSTALLATION_REPORT.md before changes.

- Preserve Windows SetTimer/nonblocking transport and serial GUI-thread MD API calls.
- Never call scene APIs from background threads.
- Preserve stable refs; reject ambiguous/stale mappings.
- Never automatically retry UNKNOWN mutations.
- Keep runtime guidance in MCP instructions and tool descriptions.
- Keep runtime data outside the package; do not ship downloaded vendor docs.
- Run offline unit tests. Live tests require an inspected disposable scene.
