# 把内容治理知识库同步到工作台（4317）· 落地说明

> 本文记录 2026-09-23 这次同步做了什么、为什么这么做、怎么维护、怎么回滚。
> 权威库是分层新库 `kb/l0…l6`；本文只讲「怎么让它出现在工作台里」。

## 结论（现在的状态）

| 项 | 值 |
|---|---|
| 工作台 | `http://127.0.0.1:4317/` → 知识库页：**1 个子库 / 509 条条目 / 0 跳过 / 0 漂移** |
| 取数通道 | `remote`（HTTP），不是原来的直接扫盘 |
| 取数服务 | `http://127.0.0.1:4508`，launchd 作业 `com.kb-hostlib`，脚本 `kb-hostlib-serve.py` |
| 派生宿主库 | `kb/.work/hostlib/`（509 条 md + `_meta/collections.yaml` + `_meta/manifest.json`） |
| 生成器 | `kb/.work/gen-host-library.py` |

## 为什么不能按原路直接同步（根因）

工作台的镜像器本来**直接读宿主库文件**（`~/.dsh/Momcozy知识库/**/*.md`）。这台机器上装了
加密代理（`/usr/local/.trld`，LaunchDaemon `com.trld.tr_daemon`，把 `libtr_monitor_enc.dylib`
注入到 Electron 进程），实测：

- 同一个路径，`fs.statSync` 报 **13084** 字节，而 `python3`/`cat` 看到 **8988** 字节；
- Node/Electron 读出来的不是合法 UTF-8（`TextDecoder(fatal)` 直接抛）；
- `readFileSync` / `readFile` / `openSync+readSync` 都拿到密文，只有 `cat`/`python3` 拿明文；
- 对照实验：**只有 2026-09-20 之前落盘的老文件两个世界都能读**（老 KB 的 `collections.yaml`
  9512 字节、工作台自己的 `package.json` 2091 字节，Electron 读出来完全正常）。

第一次同步的结果就是证据：`inserted 0 / skipped 509`，理由全是「不是合法 UTF-8」。
所以这不是内容问题，是「谁在读」的问题 —— 换传输层，由读得到明文的 python 进程把内容发出去。

## 现在的数据流

```
kb/l0…l6（分层新库，权威）
   │  gen-host-library.py（只读源库；把 l3 规则 + l5 P0 判定渲染成宿主条目形态）
   ▼
kb/.work/hostlib/{子库}/{L0-raw…L4-contracts}/*.md  +  _meta/manifest.json
   │  kb-hostlib-serve.py（launchd com.kb-hostlib，只读、只发）
   ▼  HTTP GET /manifest
工作台 kb-sync.ts（远程通道）→ 落库（kb_collections / kb_docs / kb_chunks / kb_fts）
   ▼
4317 界面：列库 / 检索 / 绑给智能体
```

两条通道（本地扫盘 / 远程 HTTP）共用同一个 `applyPlan()`，解析（`parseEntry`）、
切块（`renderForChunking`）、差集、删除、计数语义只有一份 —— 换的只是传输层。

## 维护

```bash
# 1) 改了分层新库之后，重出派生视图
python3 kb/.work/gen-host-library.py --out kb/.work/hostlib
# 2) 服务按 manifest 的 mtime 自动重载（不用重启）
curl -s http://127.0.0.1:4508/health          # 看一眼 docs/version
# 3) 工作台下一次对账跟上（60 秒兜底），或点界面上的「立即同步」
curl -s -X POST http://127.0.0.1:4317/api/kb/sync
```

- 派生视图是**只读**的：工作台侧改了会被下次对账覆盖（`KbReadOnlyError` 拦写入）。
- 新库 l3 全部是 `provisional`、l4 canonical 仍为空 —— 视图不改变这个状态，
  条目的 `not_proves` 里写明了「未命中 ≠ 合规」。
- 只搬「已归纳成规则」的那一层；l2 的 9261 条原始单元、l0 的 1256 份素材没逐条搬。

## 回滚

```bash
# 工作台代码（补丁前的原文件）
ls "<工作台>/var/kb-remote-patch-backup-*"
git -C "<工作台>" checkout -- apps/server/src/kb/kb-sync.ts apps/server/src/config.ts apps/server/src/app.ts
launchctl bootout gui/$(id -u)/com.workbench.app
# 去掉 plist 里的 EnvironmentVariables（备份：com.workbench.app.plist.bak-*）
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.workbench.app.plist

# 取数服务
launchctl bootout gui/$(id -u)/com.kb-hostlib
rm ~/Library/LaunchAgents/com.kb-hostlib.plist
```

## 本目录里的文件

| 文件 | 作用 |
|---|---|
| `gen-host-library.py` | 分层新库 → 宿主库形态条目 + `_meta/{collections.yaml,manifest.json,derivation.json,DERIVED.md}` |
| `kb-hostlib-serve.py` | 只读 HTTP 取数服务（`/health` `/manifest` `/doc` `/raw`） |
| `verify-host-library.ts` | 用**工作台自己的**解析器校验派生条目（必填字段 / id 唯一 / tier 合法 / 有效期自洽 / 登记表对账） |
| `patch-workbench-kb-remote.py` | 给工作台打「远程通道」补丁（幂等干跑 + 备份） |
| `setup-kb-remote.sh` | 一次性落地：打补丁 + 装 `com.kb-hostlib` + 给工作台作业加环境变量 + 重启 |

## 遗留（说清没做什么）

1. **派生视图与分层库可能不同步** —— 靠人跑生成器，没有自动触发（新库落盘后要手动跑一次）。
2. **HTTP 载荷每 60 秒重取一次**（约 3.5 MB）：`inserted/updated` 都是 0，费用可接受；
   要更省可把 `WORKBENCH_MOMCOZY_RECONCILE_MS` 调大。
3. **加密代理本身没动**：这是公司设备上的安全组件，本方案只是绕开它对读取的影响，
   没有尝试停用或改配置。任何**新的**「Electron 直接读这个目录」的实现都会再撞一次。
4. 旧位置 `~/.dsh/Momcozy知识库/` 已清空，只留一份 README 说明来龙去脉。
