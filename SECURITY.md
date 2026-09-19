# Trust model

Embedded Python runs with MD's privileges, including filesystem and process
capabilities. It is not a sandbox. Connect trusted MCP clients only. Loopback
TCP is unauthenticated: local processes can send requests. Do not expose it
through port forwarding or to untrusted hosts.

MD_MCP_ALLOW_RAW_PYTHON=0 refuses the raw MCP tool while semantic tools continue
using the bridge. This is not a boundary against direct TCP access. AST guards
identify some known modal calls; they cannot prove arbitrary Python safe.

Journals, checkpoints and logs can contain scene names, paths, code and results.
Protect the user data directory and review it before sharing. Runtime artifacts
and downloaded official docs must not enter public distributions.

Timeouts do not cancel calls. Reconcile UNKNOWN and verify the scene. Keep durable
saves outside the automatically cleaned checkpoint cache.
