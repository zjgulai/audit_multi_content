# 这个目录现在是空的（2026-09-23）

这里原来放「宿主知识库」的 md 条目，工作台（http://127.0.0.1:4317）直接读它做只读镜像。

**2026-09-23 起不再走这条路**：本机的加密代理（`/usr/local/.trld`，LaunchDaemon
`com.trld.tr_daemon`）会让 Electron/Node 读这里的文件时拿到密文 ——
实测同一路径 `fs.statSync` 报 13084 字节而 `python3` 看到 8988 字节，读出来不是合法 UTF-8，
镜像器 509 条条目全部被「跳过非 UTF-8」挡在门外（只有 2026-09-20 之前落盘的老文件两边都能读）。

现在的形态：

| 角色 | 位置 |
|---|---|
| 派生出的宿主库形态条目（509 条 md + manifest） | `<工作区>/知识库/内容治理/kb/.work/hostlib/` |
| 取数服务（python，读明文、发 HTTP） | `kb/.work/kb-hostlib-serve.py`，launchd 作业 `com.kb-hostlib`，`http://127.0.0.1:4508` |
| 工作台镜像器 | 已加远程通道（`WORKBENCH_MOMCOZY_KB_REMOTE`，写在 `~/Library/LaunchAgents/com.workbench.app.plist`） |
| 权威库（分层新库） | `<工作区>/知识库/内容治理/kb/l0…l6`（本目录与它无关） |

要改内容：改分层新库 → 跑 `kb/.work/gen-host-library.py --out kb/.work/hostlib` → 服务按 mtime
自动重载 → 工作台下一次对账（60 秒兜底，或点界面上的「立即同步」）跟上。
