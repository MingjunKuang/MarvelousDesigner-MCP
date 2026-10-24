# Trust model

Embedded Python runs with MD's privileges, including filesystem and process
capabilities. It is not a sandbox. Connect trusted MCP clients only. Do not
expose the loopback port through port forwarding or to untrusted hosts.

Each listener start writes a fresh random token to `<data dir>/listener.token`
(default `%LOCALAPPDATA%\marvelous-designer-mcp`). Every request, including
ping and shutdown, must carry it; others are rejected without running. The
bridge reads the file on every call, or `MD_MCP_TOKEN` if set. This blocks
other accounts and processes that cannot read your user profile. It does not
stop code already running as the same Windows user, which can read the token
file (and could drive MD in other ways anyway).

Requests are queued once fully received, so a long MD call cannot make the
requests behind it time out. When more than a few are already waiting, new ones
get a `busy` error and are not executed; retry after the running call ends.

MD_MCP_ALLOW_RAW_PYTHON=0 refuses the raw MCP tool while semantic tools continue
using the bridge. This is not a boundary against direct TCP access. AST guards
identify some known modal calls; they cannot prove arbitrary Python safe.

Journals, checkpoints and logs can contain scene names, paths, code and results.
Protect the user data directory and review it before sharing. Runtime artifacts
and downloaded official docs must not enter public distributions.

Timeouts do not cancel calls. Reconcile UNKNOWN and verify the scene. Keep durable
saves outside the automatically cleaned checkpoint cache.
