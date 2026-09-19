# Marvelous Designer MCP

[![English](https://img.shields.io/badge/English-Switch-blue)](README.md) [![简体中文](https://img.shields.io/badge/简体中文-当前语言-green)](README.zh-CN.md)

通过 Marvelous Designer 的 Python API，让 Codex、Claude 和其他支持 MCP 的智能体控制本机 MD。

## 快速开始

环境要求：Windows、支持 Python 插件的 **Marvelous Designer 2026.0.315**、Python 3.10+，以及 pip 或 uv。MD 与 MCP 客户端应使用同一个 Windows 用户运行。

1. 从 GitHub 安装（需要已安装 Git）：

   ```powershell
   uv tool install git+https://github.com/Laboon2501/MarvelousDesigner-MCP.git
   # 或在已激活的 Python 环境中使用 pip：
   pip install git+https://github.com/Laboon2501/MarvelousDesigner-MCP.git
   ```

   确保安装环境的 Scripts 目录位于 MCP 客户端可见的 PATH 中。普通用户无需手动克隆源码。

2. 先启动一次 MD，让它生成配置，然后关闭 MD，运行：

   ```powershell
   md-mcp install-plugin
   ```

   命令会打印插件的安装路径和注册结果。如果无法自动判断菜单语言，按输出提示进入 **插件 → 插件管理器 → +ADD**，选择打印出来的 `md_start_listener.py`，选择插件菜单并确认。也可以指定菜单：

   ```powershell
   md-mcp install-plugin --menu "插件 / 插件"
   # 英文界面：--menu "Plugins / Plug-in"
   ```

   非标准配置路径可通过 `--config PATH` 指定 `pluginSettings.json`。

3. 启动 MD，点击 **插件 → 插件 → md_start_listener**；英文界面为 **Plugins → Plug-in → md_start_listener**。启动脚本会立即返回。每次重启 MD 后需要重新启动 listener。
4. 检查连接，并按需建立官方文档索引：

   ```powershell
   md-mcp doctor
   md-mcp update-docs
   ```

5. 将下方配置添加到客户端，重新加载 MCP 连接，然后调用 `tools/list` 和 `ping`。

仅启动外部 MCP server 不够：MD 内部的 listener 必须已经启动。

## 客户端配置

Codex 的 `config.toml`，也可参考 [配置示例](examples/codex-config.toml)：

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

Claude Code 项目的 `.mcp.json`，也可参考 [配置示例](examples/claude-mcp.json)：

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

如果桌面客户端找不到 `md-mcp`，运行 `Get-Command md-mcp` 获取安装后的可执行文件路径，并将它填入 `command`。客户端支持设置工具超时时，应让该时间大于 bridge 超时时间。

## 功能与架构

目前提供 **42 个工具**，覆盖场景查询、纸样、稳定拓扑引用、整条边缝纫、面料与材质、OBJ 人台、模拟与网格测量、检查点、导入导出、官方文档搜索、运行时 API 查询及原始 Python 执行。

```text
智能体 → MCP stdio → Marvelous Designer MCP Server
                             ↓ 本机 TCP
                       MD Python Bridge Plugin
                             ↓
                       MD 内嵌 Python API
```

必需的 Python bridge 使用 Windows SetTimer 和非阻塞 socket。MD API 在 GUI 线程串行执行，请求之间界面可响应；同步模拟、导入、导出在执行期间仍可能使界面暂停。详见 [GUI Freeze 修复说明](GUI_FREEZE_FIX.md)。

## 兼容性

| 环境 | 状态 |
| --- | --- |
| Windows、MD 2026.0.315、内嵌 Python 3.11.8 | 已验证 |
| 其他 Windows MD 版本 | 未验证，使用前应查询运行时 API |
| CLO | 未测试 |
| macOS / Linux 中的 MD bridge | 当前 Windows timer 实现不支持 |
| 外部 Python 3.10+ | 安装要求；CI 配置覆盖 3.10 / 3.13，实测范围见报告 |

doctor 会将当前 MD 版本与已验证版本比较。版本一致不代表所有 API 或工作流均经过测试。自定义注册表可用 `doctor --config PATH`。详见 [安装验证报告](INSTALLATION_REPORT.md)。真实 MD 注册表的自动注册，以及从新注册菜单项启动的完整流程，仍需要独立验证。

## 插件、运行数据与文档

默认数据目录为 `%LOCALAPPDATA%\marvelous-designer-mcp\`。可在安装和运行之前，将 `MD_MCP_DATA_DIR` 设置为其他绝对路径。复制后的启动脚本会记录该安装的数据目录，用于写入日志。

```text
plugin/scripts/md_start_listener.py   # 注册的稳定启动入口
plugin/md_addon/                      # Python bridge
operations/                          # 操作日志和 MD 完成回执
checkpoints/                         # ZPRJ 检查点与验证清单
cache/simulation-samples/             # 主动请求的 OBJ 测量数据
docs/html/                           # 用户下载的官方文档
docs/md-docs.sqlite3                  # 本地搜索索引
logs/listener.log
```

运行数据不写入源码或 site-packages。升级时先停止 listener，更新安装包，重新运行 `install-plugin`，再启动 listener。自动修改注册表前请关闭 MD，避免 MD 退出时覆盖配置。修改前会在 `pluginSettings.json` 旁建立备份，并保留其他插件。

安装包不分发官方文档正文。`md-mcp update-docs` 从 `developer.marvelousdesigner.com` 下载七个 HTTPS 页面，建立本地 SQLite FTS5 索引。`--offline` 从已经下载的 HTML 重建。缺少索引不会阻止 server 启动或场景工具运行；文档工具会提示如何建立索引。官方文档可能落后于 MD，实际 API 可用性以运行时查询为准。

| 环境变量 | 默认值 / 用途 |
| --- | --- |
| `MD_MCP_DATA_DIR` | 上述用户数据目录 |
| `MD_MCP_DOCS_DB` | 可选的文档索引路径 |
| `MD_MCP_HOST` / `MD_MCP_PORT` | 外部客户端连接地址，默认 127.0.0.1:7421；listener 固定在本机 7421 |
| `MD_MCP_TIMEOUT` | 默认 120 秒；客户端示例使用 600 秒 |
| `MD_MCP_ALLOW_RAW_PYTHON` | 默认开启；0 / false / no / off 拒绝原始 Python 工具调用 |

## 安全与操作规则

只连接可信客户端。`execute_python` **不是沙箱**：代码能修改场景，并使用 MD 进程权限访问文件、进程等能力。AST 预检查只提供辅助提示。本机 TCP 没有身份认证，其他本机进程也能访问。禁用原始 MCP 工具不能阻止直接 TCP 请求；内部语义工具仍可工作。详见 [安全说明](SECURITY.md)。

修改前先检查场景，使用 `get_pattern_topology` 获取稳定引用，不要猜测索引。陌生 API 应先查询文档和运行时签名。每次修改后验证结果，复杂任务分步执行。

超时不会取消操作。发生超时的修改应视为 **UNKNOWN**：使用返回的 `operation_id` 调用 `reconcile_operation`，检查场景和输出，再决定下一步；不要盲目重试。FAILED 也可能已经产生部分修改。

破坏性操作前建议建立检查点。**create_checkpoint 可能改变当前项目路径，具体取决于 MD API 行为。** 不要假设保存前后路径一致。恢复检查点会替换场景并使旧拓扑引用失效。至少保留最新 20 份检查点；超过七天且不在保留集合内的旧文件可被清理。正式工程应另存到缓存以外。

## 已知限制

- 已验证外轮廓及内部直线/曲线的整条边缝纫；部分边、自由缝纫及缝纫删除尚未作为已验证操作提供。
- `pattern_arrangement` 控制 arrangement 参数，不是已验证的世界坐标变换或 Euler 旋转接口；它替代早期的 `pattern_placement` 名称。
- 稳定点修改支持已验证的外轮廓端点；任意样条控制点和内部点尚未验证。遇到 STALE_REFERENCE 后重新查询。
- OBJ 人台导入的显式比例、轴向及 type=0 已验证；FBX / AVT 人台导入未验证。
- OBJ 测量仅在满足条件时比较顶点索引，不能提供持久顶点身份、收敛或碰撞判断。
- BACK / SIDE 材质修改会解除 FRONT 继承；材质面与配色方案分配选项含义不同。
- 长时间原生调用和模态窗口仍会占用 GUI；不提供取消能力。

## 排错与卸载

| 问题 | 处理方法 |
| --- | --- |
| 找不到插件 | 运行 install-plugin，按提示手动注册，刷新插件管理器或重启 MD |
| listener 未连接 | 启动 MD 并运行 md_start_listener；查看 logs/listener.log |
| 7421 被占用 | 用 doctor 检查是否为已有 listener，停止后再启动；不要终止无关进程 |
| MD 版本不一致 | 按未验证版本处理，查询 environment_info / inspect_md_api |
| 缺少文档 | 运行 update-docs，检查能否访问官方站点 |
| 超时 UNKNOWN | 核查回执、模态窗口、场景和文件，再决定是否重试 |
| 客户端工具列表过旧 | 升级后重新加载 MCP 连接 |

调用 `shutdown_listener` 或关闭 MD 后，运行 `md-mcp uninstall-plugin`。它只删除完全匹配且由本安装拥有的注册项，并建立备份；人工注册或被外部修改的条目需要在插件管理器中移除。复制的 bridge、日志、检查点及用户工程会保留。随后删除客户端配置，并使用原安装工具卸载 Python 包。手动清理数据前先保存需要的文件。

## 开发

```powershell
uv sync --frozen
uv run python -m unittest discover -s tests -v
uv build
```

详见 [开发说明](DEVELOPMENT.md)。GitHub Actions 运行离线单元测试，真实 MD 集成测试只在本地手动运行。运行规则通过 MCP server instructions 和工具描述提供；仓库中的 Agent 指令文件仅用于开发。

## 许可证与致谢

采用 [MIT License](LICENSE)。基于 [ysk424/marvelous-designer-mcp](https://github.com/ysk424/marvelous-designer-mcp)，保留原作者版权与许可证声明，增强部分使用相同许可证。详见 [NOTICE](NOTICE)。

Marvelous Designer 及其官方文档的权利归各自权利人所有。本项目为独立社区项目。
