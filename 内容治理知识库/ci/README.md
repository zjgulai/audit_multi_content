# KB 闸门 CI / 定时任务

把 `kb/l7/scripts/` 下的闸门脚本收成**一次调用、一张表、一个可判定退出码、一份机读产物**，
供 CI 或本机定时任务调用。

> **先读这一句**：这些闸门**只能在这台 Mac 上跑**。它们读的是本机活库的真实数据
> （`kb/l0…l7`）、用本机 `kb/.kb-python` 指定的解释器、路径写死在本机绝对路径上。
> **云端 runner 跑不了**（实测本机也没装任何 runner）。所以下面的 GitHub / GitLab 两份配置
> 是「等你有仓库 + 有 self-hosted runner 之后」才成立的**模板**；
> **今天真能跑的只有本机 launchd 定时任务**。

| 文件 | 作用 | 状态 |
|---|---|---|
| `run_gates.py` | 统一入口：跑 12 把闸门、汇总、落盘报告 | 实测跑通（12/12 已跑到，见 §6 当前状态） |
| `install-launchd.sh` | **装定时任务（推荐走它）**：核对路径、建日志目录、装完立刻验证 | **已实测**（exit 0/3 两条路都验过） |
| `launchd/com.kb.gates.plist` | 定时任务模板（每日 14:00 只读巡检） | 模板；`install-launchd.sh` 会按当前库根生成 |
| `github/kb-gates.yml` | GitHub Actions 工作流 | **待放** `.github/workflows/kb-gates.yml`（需仓库 + runner） |
| `gitlab/kb-gates.gitlab-ci.yml` | GitLab CI 流水线 | **待放** 仓库根 `.gitlab-ci.yml`（需仓库 + runner） |
| `out/gates-latest.{json,md}` | 最近一次机读产物 | 已生成 |

```bash
bash  ci/install-launchd.sh              # ★ 装本机定时任务 + 立刻验证一次
python3 ci/run_gates.py                 # 手工跑全部，人看表
python3 ci/run_gates.py --outdir ci/out # 落盘 JSON + Markdown
python3 ci/run_gates.py --only l0 l4 l7 # 只跑几把
python3 ci/run_gates.py --strict-warn   # 告警也算失败（发布前门禁用）
```

---

## 一、闸门清单与实测耗时

12 把，**都是只读档**，都支持机读输出（唯一的例外见 §3 末）。

| id | 脚本（相对 `kb/`） | blocking | 空闲实测 | **满载实测**（同机有别的会话在跑 L6） |
|---|---|---|---|---|
| `l0` | `l7/scripts/l0_gate.py` | 是 | 15–33s | 25–50s（**要联网对飞书**，见 §4.2） |
| `l1` | `l7/scripts/l1_gate.py` | 是 | 2.9s | 12.8–20.0s |
| `l2` | `l7/scripts/l2_gate.py` | 是 | 3.5s | 14.8s |
| `l3` | `l7/scripts/l3_gate.py` | 是 | 3.8s | 15.2s |
| `l4` | `l7/scripts/l4_gate.py` | 是 | 3.7s | 13.8s |
| `l5` | `l7/scripts/l5_gate.py` | 是 | 8.6s | 39.8s |
| `l6` | `l7/scripts/l6_gate.py` | 是 | **85.8s** | **311.6–337.1s** ← 最慢，且对并发极敏感 |
| `l7` | `l7/scripts/l7_gate.py` | 是 | 3.8s | 13.5s |
| `skills` | `l7/scripts/skills_check.py` | 是 | 4.1s | 21.0s |
| `layers` | `l7/scripts/layers_check.py` | 是 | 3.2s | 15.8s |
| `conformance` | `l7/scripts/skill_conformance.py` | 是 | 3.5s | 15.6s |
| `freshness` | `l7/scripts/freshness.py` | **否** | 25.8s | 142.1s |

- **空闲全量 ≈ 2.5 分钟**；**满载全量 ≈ 10–11 分钟**（2026-10-04 实测两次：625s / 约 640s，
  当时同机一直有 ~25 个 KB 进程在跑）。
- ⇒ CI 的 `timeout` 给 **30 分钟**是够的；`run_gates.py` 的单把超时默认 **600s**，
  满载下 `l6` 已到 **337.1s**（余量不到 2×）。要更稳可以传 `--timeout 900`。
- ⚠️ 别把「满载 10 分钟」当成故障。**先 `ps` 看有没有别的会话在同一台机上跑 L6。**

### 两个实测踩过的坑（已修在代码里，写下来免得再踩）

1. **`kbpy` 的路径基准是 `kb/`，不是库根。**
   `kb/kbpy` 内部 `cd` 到自己的目录，所以它接收的脚本路径必须写成 `l7/scripts/l0_gate.py`。
   传 `kb/l7/scripts/l0_gate.py` 会被拼成 `kb/kb/l7/scripts/...` 并报「找不到脚本」。
2. **参数不统一。** 八把层闸门支持 `--json --quiet`，但 `freshness.py` **没有 `--quiet`** ——
   传了会 argparse 报错、退出码 2（看着像「判据算不出来」）。→ `run_gates.py` 里每把闸门自带 flags。
3. **`plist` 里 `&&` 是 XML 转义的 `&amp;&amp;`**（2026-10-04 踩）。
   写脚本去解析模板里的库根时，正则里带 `&&` 会**一条都匹配不到**，然后静默装错路径。

---

## 二、退出码语义（CI 与定时任务照这个判）

`run_gates.py`：

| 码 | 含义 | 该做什么 |
|---|---|---|
| `0` | 全过 | — |
| `1` | 有闸门**判红** | 先看输出末尾的**成因提示**，再按 `kb/l7/registry/failure-playbook.yaml` 定位 |
| `2` | 有闸门**无法计算** | 判据算不出来（缺输入/空目录/注册表漂移），**不是数据错**，去补判据或登记漂移 |
| `3` | runner 故障 | 找不到解释器 / 脚本缺失 / 非 blocking 闸门自身报错 |

**`1` 与 `2` 分开是刻意的**：库内多把闸门都设了「拒答」档（`l1_gate.py` 的 C3 就明确写
「否则闸门会在空目录上**假过**（vacuous pass）」）。把「算不出来」混进「红」，
会让人把基础设施问题当成数据问题去改数据。

`install-launchd.sh`（另一个脚本，另一套码，别混）：

| 码 | 含义 |
|---|---|
| `0` | 装好了**且验证通过**（拿到本轮新报告） |
| `1` | 安装失败 |
| `2` | 用法错 |
| `3` | **装好了但没验成** —— 等待窗口内没等到新报告（任务可能仍在跑）。**这不是安装失败**，14:00 照样会跑 |

### 为什么 `freshness` 不 blocking

`freshness.py` 超出阈值时退出码 `3`。库内口径原文：**「超期是去跑链路的理由，不是拒答的理由」**。
→ 它在 `run_gates.py` 里记 `WARN`，不单独把 CI 打红（否则红灯会变成没人看的噪音）。
要发布前门禁严格，加 `--strict-warn`。

### 异常路径已做故障注入验证（2026-10-04 独立复现）

不是只跑了 happy path。用**假库 + 假 kbpy**逐个注入退出码，复现了状态映射与整体退出码：

| 注入（blocking 闸门） | 状态 | 整体退出码 |
|---|---|---|
| 退出码 0 + `ok=true` | `PASS` | 0 |
| 退出码 1 + `ok=false` | `RED` | **1** |
| 退出码 2 | `BLOCKED` | **2** |
| **退出码 0 但 `ok=false`** | `RED`（以 `ok` 为准） | **1** |
| 退出码 7（未知码） | `FAILED` | **3** |
| 脚本不存在 | `MISSING_SCRIPT` | **3** |

| 注入（非 blocking `freshness`） | 状态 | 整体退出码 |
|---|---|---|
| 退出码 3（超期） | `WARN` | 0（除非 `--strict-warn`） |
| 退出码 1 / 2（自己报错） | `ERROR` | **3** |

最后两行是特意加的：**非 blocking 闸门自己报错绝不能被静默吞掉** —— 那比红更危险。

---

## 三、并发纪律（这条最容易出事）

本库已登记过事故：**同一循环同时只准一个会话跑**。两会话并发会导致
L6 记账与 L7 被 `exit 2` 挡回、同一 RUN 在 `index.jsonl` 落 **2 行**（双计）、
L7 记账行被后跑的会话覆盖。

2026-10-04 实测补充了一条**新的**并发代价（不是数据坏，是**读数失真**）：
同机有 ~25 个 KB 进程（多个会话在跑 `l6/retriever.py`、`l*_gate.py`、`workflow_check.py`）时，
`l6` 从 **85.8s → 311.6s**、全量从 **2.5min → 10.4min**。
→ **一条只读闸门被拖慢 3.6×**，看起来像"卡死"。这里没有锁可抢，纯 I/O 争用。

本 CI / 定时的口径：

- ✅ **只读**：不调 `kb_pipeline.py --apply`、不调 `kb_loop_claim.py`、不调 `daily_sync.py`。
  → **不抢** `kb/.work/.kb.lock`，任何时候都能跑。
- ✅ **时间错开**：现有写档任务是本机 **08:30**（`com.kb.pipeline-daily`，实测 08:45 跑完），
  CI cron 取 **18:15 本机**（10:15 UTC），launchd 取 **14:00**。都留了 5 小时以上余量。
  （闸门只读，撞上不会坏数据，但会读到**写了一半**的层而报**假红**。）
- ✅ **显式互斥**：GitHub 用 `concurrency: kb-gates`，GitLab 用 `resource_group: kb-gates`。
- ✅ **`install-launchd.sh` 自带在飞守卫**：若已有 `run_gates.py` 在往同一个报告目录写，
  就**不再 kickstart**（只等它出报告）—— 免得验证动作本身把并发问题放进来。
- ❌ **不要把 `daily_sync.py` 放进 CI**：它会写 `kb/l0…l6`。写档留在本机 launchd，
  CI 只做「写档之后的守门」。要迁移写档，先停掉 launchd 那一个，别两套并行。

### 唯一的"只读例外"（照实登记）

`l5_gate.py` 会写它自己的 `kb/.work/l5_integrity.json` —— 那是**自检器的证据件**，
不是层产物，闸门自己在文件头注明了。所以「本 CI 只读」严格说是
「**不写 `kb/l0…l7` 的数据与台账**」，`.work/` 下的自检证据件不算。

---

## 四、部署前必须满足的前提（**实测结论：今天一个都不满足**）

### 4.1 必须用**本机 self-hosted runner**（硬前提）

实测（2026-10-04）：

```
git rev-parse --show-toplevel   → fatal: not a git repository      # 不是 git 仓库
ls ~/actions-runner ~/gitlab-runner → （不存在）                    # 没装任何 runner
launchctl list | grep -i runner → （空）
```

而且库深度绑定本机：

- plist 里硬编码 `/Users/lute/Documents/skill-test/...` 绝对路径；
- `kb/kbpy` 要读 `kb/.kb-python` 指定的解释器（`/usr/bin/python3`；受管 python 缺 numpy/fastembed，L6 召回必需）；
- 闸门要读 `kb/l0…l7` 的**真实活数据**。

**GitHub 托管的 runner / GitLab shared runner 上这三样一个都没有**，跑出来只会是「找不到脚本」。
→ `runs-on` / `tags` 必须指向打在这台 Mac 上的 runner（模板里写的是 `kb-host`，换成你的标签）。

### 4.2 ★ 闸门读的是**活库**，不是 checkout 出来的副本（2026-10-04 修的真缺陷）

上一版两份配置有个会**直接跑挂**的问题：GitHub runner 的工作目录是 `_work/<repo>/<repo>`，
**没有 `actions/checkout` 就是个空目录**；而**即使 checkout 了**，那也是一份**快照副本**，
不是 08:30 写档任务正在改的那个活库 —— 于是闸门会去评一份**没人动的旧快照**，
或者干脆在第一步自检就报「不是权威库根」。

修法（两份配置同口径）：**故意不 checkout**，每一步 `cd "$KB_LIVE_ROOT"`，
并把 `KB_LIVE_ROOT` 提成显式变量强制你填对；GitLab 侧另加 `GIT_STRATEGY: none`（连 clone 都省掉）。
⚠️ **装之前必须把 `KB_LIVE_ROOT` 改成这台 runner 上的库根绝对路径。**

### 4.3 `l0` 闸门要**联网 + 要有 user 身份**

`l0_gate.py` 要对飞书侧做对账。两点都实测过：

1. **要联网**：runner 需要能访问飞书。离线环境里 `l0` 会失败 —— 那不是数据坏了，别照着红去改数据。
2. **要 `lark-cli` 的 user 身份**：有两张表挂在 wiki 上的 Base，**bot（守衡）整库级读不到**
   （实测 `code 91403 you don't have permission`），只能靠 `kb/l8/align_l0_feishu.py`
   的「按表身份回落」用**用户身份（刘华丽）**去取。
   ⇒ 用户令牌一失效，**`l0` 必红**，而且**不是数据错**。
   实测 2026-10-04 就是这个状态，详见 **§6**。
   ⇒ 本 CI 已在跑闸门前加了一步**只提示不判成败**的 `lark-cli auth status`，
   让值班的人一眼看到根因，不用去查数据。

### 4.4 库里含凭据，推远端前先定 `.gitignore`

实测库里存在 `kb/.work/.publish-api-key` 以及大量数据产物。
**要让 CI 用上，第一件事是「定 `.gitignore`」，不是「push」。**
别让 workflow 成为第一件把凭据推上去的事。

### 4.5 launchd 侧的两条（2026-10-04 修）

1. **`StandardOutPath` / `StandardErrorPath` 的目录 launchd 不会自建** —— 目录不存在任务起不来。
   → `install-launchd.sh` 会先 `mkdir -p`。手工装的话记得自己建。
2. **`HOME` 必须显式给**：`l0` 要调 `lark-cli`，它按 `~/.dsh` 找配置与 keychain；
   HOME 缺失时 `expanduser("~/.dsh/bin")` 会解析成字面量 `~/.dsh/bin` ⇒ 找不到 `lark-cli`
   ⇒ `l0` 报「拉取失败」而**看起来像数据错**。（实测同机的 `com.kb.pipeline-daily` 能跑通 L0，
   说明 HOME 实际有值，但**依赖隐式继承**不该留着 —— 现在显式写死。）
3. 顺带：`launchd` 的 `StandardOutPath` 是**追加**打开的，不是每次截断 ——
   日志会一直长，长期跑要自己轮转。
4. 顺带：plist 里的 python 调用用 `python3 -u`（**无缓冲**）。
   不带 `-u` 时输出被块缓冲，`out.log` 在前 10 分钟**完全是空的**，
   看起来像卡死（实测踩过）；带上就能实时看到每把闸门的进度。

---

## 五、安装

### 5.1 本机定时任务（**今天唯一真能跑的**）

```bash
bash ci/install-launchd.sh                 # ★ 推荐：核对路径 → 建日志目录 → 装载 → 立刻跑一次 → 验报告
bash ci/install-launchd.sh --no-run        # 只装，不立刻跑
bash ci/install-launchd.sh --wait 1800     # 验证等待窗口（秒，默认 900）
bash ci/install-launchd.sh --uninstall     # 卸载
```

实测输出（2026-10-04 00:41，`--wait 5` 那次演示了 exit 3 这条路）：

```
✅ 已装载 com.kb.gates ｜ 计划：每日 14:00（本机时区）
⚠️ 装好了，但**没验成**：等待窗口 5s 内没等到新报告。
   实测任务**仍在跑**（run_gates.py 进程还在）—— 多半只是被别的会话拖慢了。
   （这不是安装失败：计划任务已装载，14:00 照样会跑。）
```

装完以后本机就有**两个** KB 定时任务，**故意错开**：

| Label | 时间 | 跑什么 | 读写 |
|---|---|---|---|
| `com.kb.pipeline-daily` | 08:30 | `l7/scripts/daily_sync.py` | **会写** `kb/l0…l6`（L0 对齐 + 逐层写档 + 体检） |
| `com.kb.gates` | 14:00 | `ci/run_gates.py` | **只读**，只写 `~/Library/Logs/kb-gates/` |

为什么值得单独有一个只读巡检：08:30 那次是「**写完之后**顺手体检」，报的是写档那一刻的状态。
白天有人改数据、有人手工发号、飞书侧改源，都不会再被看第二眼。14:00 这次补的是**日间漂移**。

> ⚠️ **`com.kb.pipeline-daily.plist` 的注释是错的（待修，不是本文件范围）**：
> 它的文件头写「跑的是 `daily_health.py`…**只读**…不写 `kb/l0…l6` 的任何数据与台账」，
> 但它的 `ProgramArguments` 实际跑的是 **`daily_sync.py`** —— 依据该脚本自己的文件头，
> 它是「L0 对齐 + 逐层写档 L1→L6（`--apply`）+ 体检」的**写档**任务。
> 即：**注释说的是只读体检，实际跑的是日更写档**。
> 上一版 `ci/README.md` 把它当写档任务（对的），而这台机器上装着的 plist 注释说它是只读（错的）。
> 它的日志也印证是写档：`[daily 08:31:14] [L3] ✅ 已归档 kb/l3/rejected.jsonl`、
> `结论：L3 全部走完（写档（--apply））`。
> 建议把那段注释改掉 —— 谁按注释以为 08:30 是只读的，就会在 08:35 叠一个写档任务上去。

### 5.2 GitHub Actions（选它就把 GitLab 那份删掉）

```bash
mkdir -p .github/workflows
cp ci/github/kb-gates.yml .github/workflows/kb-gates.yml
# ★ 然后改文件里的 KB_LIVE_ROOT 为这台 runner 上的库根绝对路径
```

### 5.3 GitLab CI（选它就把 GitHub 那份删掉）

```bash
cp ci/gitlab/kb-gates.gitlab-ci.yml .gitlab-ci.yml
# ★ 同样先改 KB_LIVE_ROOT
```
再去 GitLab 的 *CI/CD → Schedules* 建一条每日 **18:15（本机）** 的 schedule（cron 用 **UTC** → `15 10 * * *`）。

### 5.4 手工装 launchd（不用安装脚本时）

```bash
mkdir -p ~/Library/Logs/kb-gates      # ★ launchd 不会自建
cp ci/launchd/com.kb.gates.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.kb.gates.plist
launchctl kickstart -p gui/$(id -u)/com.kb.gates    # 立刻验一次
```

⚠️ `launchd` **不会**因非 0 退出而通知你。要看结果读
`~/Library/Logs/kb-gates/gates-latest.json` 的 `exit_code` / `summary`。

---

## 六、★ 当前状态：`l0` 是**红的**（要人处理，CI 修不了）

`ci/README.md` 上一版记的基线是「**12/12 全绿、退出码 0**」（2026-10-03T23:33）。
**那个基线已经过期了。** 2026-10-04 00:2x 起实测：

```
汇总：过 11/12 ｜ 红 ['l0'] ｜ 无法计算 无 ｜ 非 blocking 报错 无 ｜ 基础设施 无 ｜ 告警 无
退出码 1 ｜ 有红
```

`l0` 真差异 = 2，两条都是**取数失败**，不是数据不一致：

```
[拉取失败] 专家修订汇总表 tbl8AI00JZO1iZtp
[拉取失败] 内容公式（仅供参考） tblVdl0jdK9G4ld3
  一致 612 | 飞书多 10 | L0多 0 | 值变 0 | 拉取失败 2 | 身份回落 0
```

### 根因（实测两条路都探过，不是推测）

| 身份 | 实测结果 |
|---|---|
| `bot`（守衡） | `{"code": 91403, "message": "you don't have permission"}` —— 整库级读不到 |
| `user`（刘华丽，回落用） | `{"type": "authentication", "subtype": "token_missing", "message": "need_user_authorization"}` |

`lark-cli auth status --profile dsh-kb` 直证：

```
"user": { "status": "missing",
          "message": "User identity: missing (no token in keychain for ou_af95e2a43871579692afbb25a529e77e)" }
```

⇒ **用户身份令牌没了**（keychain 里没有）。而 `kb/l7/registry/l0-expected-diffs.yaml`
早在 2026-10-03 就把这条风险写下来了：

> 「用户身份的令牌**没有 refresh token**（实测 device-flow 输出 `[WARN] no refresh_token in response`），
> 到期不续、要人重走一次 `lark-cli auth login`。**但失效是「响的」不是「哑的」**……
> 即「回落失效」以闸门红的形式暴露，不会变成一天静默的假绿。」

**所以这个红是设计内的行为，不是回归。** 闸门红得对。

### 要人做什么（registry 的 `owner_action` 原文两条）

1. **根治**：在飞书侧把 bot「守衡」加成那个 Base（`SKkkbdZi9aRuMzs7ob0cpSYHnQg`，
   节点「OGC内容生产与审核」）的**可阅读协作者** —— 加完 bot 直读成功，回落在该表自然不再触发，
   **不用改代码**。
2. **令牌到期时重跑**：
   `lark-cli auth login --profile dsh-kb --domain base --domain wiki`

> ⚠️ 这两条都是**要人做**的动作。**不要**为了把 CI 调绿去给这两张表加豁免声明 ——
> `l0-expected-diffs.yaml` 的纪律第 2/3 条就是防这个的（预期项必须带 `evidence` 与 `owner_action`）。

### 顺带发现：`reopen_when` 的判法与代码不一致（建议修，未改）

`l0-expected-diffs.yaml → resolved → reopen_when` 写的是：

> 「再次出现 `拉取失败 ≥ 1` 时，**先看报告里该表的 `identity` 与 `identity_fallback`** 再排查 ——
> 回落字段**在** = 是用户令牌失效或权限被收回；字段**不在** = bot 那条路出了新问题。」

但 `kb/l8/align_l0_feishu.py` 里 `ent["identity_fallback"]` 只在**回落成功**时赋值
（`if ok2:` 分支内）。**令牌失效时回落是失败的 ⇒ 字段不在** ⇒ 照上面这条规则会被判成
「bot 那条路出了新问题」，**指错方向**（实测 2026-10-04 正是这一格）。
建议：把「**尝试过回落**」与「**回落成功**」分开记字段（例如成功记 `identity_fallback`、
失败记 `identity_fallback_failed` 带两个身份各自的错误），`reopen_when` 按前者分路。
**这是一个真缺陷，改它要动 L0 对账器的报告结构，属于机制改动 —— 留给人裁。**

---

## 七、本次交付改了什么（2026-10-04）

相对上一版，改的是**会真跑挂 / 会误导人**的东西，闸门判据一律没动：

| # | 问题 | 严重度 | 改法 |
|---|---|---|---|
| 1 | GitHub 工作流**没有 `cd` 到活库、也没有 checkout** ⇒ 第一步自检必挂（或在空快照上评） | **会跑挂** | 两份配置都改成 `cd "$KB_LIVE_ROOT"`，`KB_LIVE_ROOT` 提成强制填的变量；GitLab 加 `GIT_STRATEGY: none` |
| 2 | launchd 日志目录不存在时任务起不来 | **会跑挂** | `install-launchd.sh` 先 `mkdir -p`，并写进 §5.4 手工步骤 |
| 3 | `HOME` 缺省依赖隐式继承 ⇒ `lark-cli` 找不到 ⇒ `l0` 报"拉取失败"而像数据错 | 高 | plist 显式写 `HOME` |
| 4 | plist 的 python 输出被块缓冲 ⇒ `out.log` 前 10 分钟全空，像卡死 | 中 | 改 `python3 -u`（实测已验证实时出图） |
| 5 | 验证等待窗口 300s 太短（满载全量 625s）⇒ 装对了却报失败 | 中 | `--wait`（默认 900s）+ `--only` 之外的 exit 3「装好了但没验成」，与"安装失败"分档 |
| 6 | 巡检与别的会话抢 I/O 会被拖慢 3.6×，验证动作还会再叠一次 | 中 | `install-launchd.sh` 加在飞守卫：已有同报告目录的 `run_gates.py` 就不再 kickstart |
| 7 | `l0` 红了只显示「拉取失败（没有声明）」，看不出根因，值班的会去查数据 | 中 | `run_gates.py` 末尾加**纯提示**（不改判据、不改退出码），把 registry 的 `owner_action` 两条印出来 |
| 8 | README 的「12/12 全绿」基线已过期 | 中 | §6 换成当前真实状态与根因 |

---

## 八、要你定（我按默认做了，不同意就推翻）

1. **你到底用哪个 CI 平台？** 我给的是 GitHub + GitLab 两份备选，**没有猜**。
   如果是 Jenkins，需要重写成 Jenkinsfile（`sh` 步骤 + `cron` 触发器），说一声我再补。
2. **runner 放哪？** 见 §4.1 —— **实测本机没装任何 runner**，所以两份 CI 配置现在都**跑不了**。
   若是云端托管 runner，那套方案里闸门跑不了真数据，只能降级成「脚本自身的语法/回归测试」，
   这会改变整个配置的意义，所以我没有默认按云端写。
3. **要不要把库纳入 git？** 目前不是仓库。纳入前先定 `.gitignore`（含凭据，见 §4.4）。
4. **`l0` 那两张表怎么办？** 走 §6 两条人做动作，还是先（按纪律带 evidence 地）声明预期差异？
   我**没有**替你动 `l0-expected-diffs.yaml`。
5. **闸门告警要不要推到飞书？** 库内 `feishu_publish.py` 是给**审查结论**用的，
   不是给闸门告警用的。要接告警请单独确认去向，我没有擅自复用那条通道。
6. **`com.kb.pipeline-daily.plist` 的错注释**（见 §5.1）要不要我改？
   我**没有**动你已装载的 LaunchAgent。

---

## 九、验证记录（我实测了什么 / 没测什么）

**实测通过**：

- `run_gates.py` 全量真跑**两次**（手工一次 + launchd 一次），12 把都跑到、报告都落盘。
- **故障注入 9 格**（blocking 5 + 非 blocking 4）独立复现了状态映射与整体退出码，见 §2。
- `plutil -lint` 语法过；两份 YAML 都能解析（GitHub 那份 `on:` 被 PyYAML 按 YAML 1.1 读成布尔 `True`，
  这是 GitHub 工作流的正常现象，不是错误）。
- `launchd`：**已装载并 kickstart 成功**，报告落到 `~/Library/Logs/kb-gates/gates-latest.md`。
- `-u` 无缓冲：实测 kickstart 后 ~75s 内 `out.log` 已有 l0/l1 的实时输出（改之前是 10 分钟全空）。
- `install-launchd.sh`：**exit 0 分支**（装好且验成）与 **exit 3 分支**（装好但没验成）**都实测跑过**，
  见 §10；`--dry-run` 实测生成件正确（含 `-u`、`HOME`、字面量 `--outdir`）；
  在飞守卫实测有效（重跑安装脚本不打断在飞那次，pid 不变）。
- `l0` 红的根因：**对两个身份各发了一次真实请求**取回错误码 + `auth status` 直证，见 §6。
- **（2026-10-04 01:05 复核轮补测，见 §十一）**两份 CI 配置里**原先声明"没验过"的那几步**已本地执行：
  GitHub 的环境自检（`KB_LIVE_ROOT` 存在 / `kb/KB-ROOT.json` / `kb/kbpy` 可执行）在真库根上逐条通过；
  `strict_warn` 三分支（空串 / `false` / `true`）真值判定正确；
  `install-launchd.sh --dry-run` 复跑仍 exit 0、生成件路径与当前库根一致；
  GitLab 的 `after_script → artifacts` 落盘顺序按官方文档核实**成立**（见 §十一）。

**没测（如实说）**：

- **两份 CI 配置没有端到端跑过** —— 本机既无 git 仓库也无 runner，物理上跑不了；
  已做的是 YAML 解析 + 逻辑审查 + §十一那几步本地执行。
  真放上去第一件事是核对 §4.1/§4.2 的前提是否满足。
- GitHub 的 `inputs.strict_warn` 在 `schedule` 触发下的实际取值（无 runner，**真机**验不了）——
  本地三分支已验，但 GitHub 侧的真实取值**未经真机验证**。
- 我没有修 `l0` 的红（那是人做的动作），也没有改任何闸门判据。

## 十、收口（本次交付的最终验证）

`bash ci/install-launchd.sh --wait 1200`（2026-10-04 00:44 发起）**退出码 0** =「装好**且**验成」，
它自己读回来的报告：

```
── 安装验证：本次实测 ──────────────────────────────
  时间      ：2026-10-04T00:54:48
  退出码    ：1   （0 全过 ｜ 1 有红 ｜ 2 无法计算 ｜ 3 runner 故障）
  过 11/12 ｜ 红 ['l0'] ｜ 无法计算 无 ｜ 告警 无
────────────────────────────────────────────────────
```

即：**定时任务这条路已经端到端跑通**（装载 → 触发 → 出报告 → 脚本判读），
它报的 `1` 是 §6 那个**真实的 `l0` 红**（用户令牌失效），不是配置问题。

⚠️ 本次全量耗时 **~10 分钟**（00:44 → 00:54），因为同机一直有别的会话在跑 L6：
`l6` 这一把 **337.1s**，空闲时是 **85.8s**。**别把「慢」当「挂」**——先 `ps` 看谁在同机跑。

---

## 十一、复核轮：CI 配置里"没验过"的那几步（2026-10-04 01:05）

`ci/` 这份交付写于 2026-10-04 00:29–00:57。本轮**唯一目的**是补上 §九 自己声明的空白
（「两份 CI 配置没有端到端跑过」）。**没有重写、没有复制第二份配置。**

### 11.1 本轮实测（都是本地可判定的）

| 项 | 命令 | 结果 |
|---|---|---|
| 定时任务**确实装着** | `launchctl list \| grep kb` | `com.kb.gates` 在册（last exit `1` = §6 那个真红） |
| 定时任务**确实跑过并落了盘** | `ls ~/Library/Logs/kb-gates/` | `gates-latest.json`(36KB) ／ `gates-latest.md` ／ `out.log`(5.9KB) ／ `err.log`(**0 字节**) |
| 报告**宿主读得动**（不是 4096 信封态） | 用 read 工具直读 `~/Library/Logs/kb-gates/gates-latest.md` | 20 行明文、表格完整 ⇒ `write_text_plain` 那条通道**有效** |
| 安装脚本幂等 | `bash ci/install-launchd.sh --dry-run` | exit 0；解析出的库根 == 当前库根；`plutil -lint` OK |
| GitHub 环境自检四行 | 在真库根上逐条执行 | 全过（`KB-ROOT.json` 在、`kb/kbpy` 可执行） |
| `strict_warn` 真值分支 | 空串 ／ `false` ／ `true` 三分支 | 空串与 `false` → 不加 flag；`true` → `--strict-warn`（**schedule 触发下 `inputs` 为空串 ⇒ 取 else 分支，正确**） |
| 两份 YAML 可解析 | `yaml.safe_load` | 均 OK（GitHub 那份 `on:` 读成 `True`，YAML 1.1 正常现象） |

### 11.2 GitLab 的 `after_script` 顺序：**核实成立**（这条本来最容易静默出错）

`ci/gitlab/kb-gates.gitlab-ci.yml` 把报告从活库 `cp` 进 `kb-gates-out/` 是放在 **`after_script`** 里的。
若 artifacts 在 `after_script` **之前**归档，产出的就是一个**空 artifact**，而且**不报错**。

按 GitLab 官方 *Job execution flow*，9 步顺序为
`… 4. script → 5. after_script → 6. 上传 cache → 7. 上传 artifacts …`，
原文另标注 **“CRITICAL: `after_script` runs BEFORE upload stages”** 与
**“Files created here are included.”**

⇒ 该写法**成立**，**不需要**把 `cp` 挪进 `script`。
来源：[Job execution flow — GitLab Docs](https://docs.gitlab.com/ci/jobs/job_execution/)

### 11.3 本轮**没有**做的事

- 没有新建 `.github/workflows/`、没有 `cp` 任何一份配置出去 —— **本目录不是 git 仓库**
  （§4.1 的前提本轮复扫到 `/` 再次确认无 `.git`）。
- 没有装 runner（`~/actions-runner` 不存在、`gitlab-runner` 不在 PATH）。
- **没有重跑 12 把闸门** —— §6 的 `l0` 红与 00:54 那版报告仍是当前状态；
  本轮只做静态 + 半静态核对，不声称刷新过闸门读数。
- 没有动 `l0-expected-diffs.yaml`、没有任何闸门判据、没有动已装载的 `com.kb.pipeline-daily`。
- 修了 §九 一处**重复段落**（同一段「没测（如实说）」写了两遍，且第二遍把「exit 0 分支」
  这条**已实测通过**的项混进了"没测"里）—— 只动文档表述，不动任何配置与判据。

---

## 十二、第二轮：把漏挂的闸门接上（2026-10-04 03:2x）

上一轮（§七 / §十 / §十一）交付的是「12 把 + 定时任务 + 两份 CI 模板」，并**如实登记了两件事没做**：
补挂漏掉的闸门、Jenkins 那份配置。本轮补这两件——**先实测再接线**，结果推翻了上一轮的两条写法。

### 12.1 实测推翻了上一轮的两个写法（已同步写进 `接线手札` 的勘误块）

| # | 上一轮怎么写的 | 本轮实测 | 照抄的后果 |
|---|---|---|---|
| 1 | 补丁片段 `("envelope", "l7/scripts/envelope_gate.py", …)` | **该路径不存在**；真身是**库根**下的 `tools/envelope_gate.py` | `MISSING_SCRIPT`(127)，闸门根本没跑 |
| 2 | 「`workflow_check.py` 要核权威库，必须显式传 `L8_KB_ROOT`」 | 传库根 ⇒ **崩溃**：`OSError: [Errno 7] Argument list too long`，**不落任何产物**；走默认（评 `kb/view`）能跑但 exit 1（②③ 属已登记合法红），**且每次运行写盘** | 进 CI 的是一把**必崩 / 必红 / 会写盘**的闸门 |

⇒ 本轮结论：**`workflow_check` 不挂**（崩、合法红、写盘三条都不适合当 CI 闸门；要挂得先修脚本本身，
那属库内脚本）；`routes_reconcile` 仍不挂（缺运行时输入 `winners`，设计上就 exit 2）。
**只补挂 `projection` + `envelope`**（两道都有真读数、都不写盘）。

### 12.2 改了什么

| 文件 | 改动 |
|---|---|
| `ci/run_gates.py` | ① 加**路径基准**两档（`base="kb"` / `base="root"`）——`tools/` 在库根下，原来的 `script_abs` 只会拼 `kb/`；② 加 `--scope core\|full`（**默认 core ⇒ 行为零改动**，也可用环境变量 `KB_GATES_SCOPE`）；③ 报告多一行 `范围：scope=…` |
| `ci/run-gates.sh` | **新**：平台无关单一入口（Jenkins / 内网自研 / cron / 任何 shell 都调它）。含前提自检（库根 / kbpy / run_gates.py），不满足时退出码 **90**——与四档闸门退出码**故意分开**，免得把「环境没配好」误读成「库里有红」 |
| `ci/Jenkinsfile` | **新**：§8 第 1 条点名缺的那份。`skipDefaultCheckout(true)`（同另两份的「读活库」设计）、`disableConcurrentBuilds()`、归档 + 构建描述；文件头写明 multibranch 下 `triggers` 无效这个坑 |
| `ci/cron/kb-gates.cron` | **新**：crontab 形态调度（给非 macOS 的调度机）。含 5 个坑，**尤其「别与已装的 launchd 双挂」** |
| `ci/github/kb-gates.yml`、`ci/gitlab/kb-gates.gitlab-ci.yml` | 调用行加 `--scope full` —— 否则「接上了」只是文件在、门是关的 |

### 12.3 本轮实测（命令 + 读数）

| 项 | 命令 | 读数 |
|---|---|---|
| `envelope_gate` 真身 | `/usr/bin/python3 tools/envelope_gate.py --json --quiet` | exit **0** ｜扫 1906 ｜过 1906 ｜信封 0 |
| `projection_reconcile` | `sh kb/kbpy l8/projection_reconcile.py --json` | exit **1** ｜ok=false ｜checks 6 / passed 3 / drift 3 |
| `workflow_check`（指权威库） | `L8_KB_ROOT=<库根> sh kb/kbpy l8/workflow_check.py CI-PROBE` | **崩**（Argument list too long），无产物 |
| `workflow_check`（默认 view） | `sh kb/kbpy l8/workflow_check.py CI-PROBE` | exit **1**（②③ FAIL）｜**写了** `kb/l8/workflow_check_CI-PROBE.json`(4757B) → 探完**已删** |
| `scope=core` 回归 | `python3 ci/run_gates.py --scope core --outdir /tmp/kb-regress-core` | **11/12 ｜红 ['l0'] ｜退出码 1** —— 与改动前逐字一致 ⇒ **默认行为零改动** |
| `scope=full` 端到端 | `python3 ci/run_gates.py --scope full --outdir ci/out` | **12/14 ｜红 ['l0','projection'] ｜退出码 1** ⇒ 两道补挂闸门**真的执行到了**（含库根基准那把） |
| `run-gates.sh` | `bash ci/run-gates.sh --scope full --only projection envelope` | 退出码 **1 原样透传**；`bash -n` 语法过 |
| 两份 YAML | `yaml.safe_load` + `grep` 调用行 | 均 OK；调用行确认带 `--scope full` |
| 本轮自己踩的坑 | `echo "$PY（…"` | `PY：: unbound variable` —— **bash 把紧跟变量的中文全角标点吞进了变量名**；已改 `${PY}`，并把这条写进 `run-gates.sh` 注释 |

### 12.4 ★ 今起这条流水线**就是红的**，而且是两把真红

挂 `scope=full` 的 CI 每天会红 2 把，**没有一把能靠改 CI 修绿**：

1. `l0` —— 取数身份坏（见 §6：bot「守衡」权限 / user 令牌 `token_missing`）
2. `projection` —— 投影漂移 3/6（`kb/view` 与权威库在 4 个字段上对不上；该 gate 自己给的修法原文：
   「确认投影生成器是否从规则行读这 4 个字段（F8）」）

要一条**绿基线**：调用退回 `--scope core`（或 `KB_GATES_SCOPE=core`），此时只剩 `l0` 一把红。

### 12.5 仍要你拍板的（§8 那 6 条一条都没变，本轮多两条）

1. **`scope` 默认取 full 还是 core？** 我按「你要求把闸门挂上 CI」取了 **full**，
   代价就是**预期每天红 2 把**；要绿基线一句话退回 core。
2. **`workflow_check` 要不要以「WARN 形态」挂？** 现在是**没挂**。要它可见但不拖垮流水线，
   机制上给每把闸门加一个「哪些退出码记 WARN」即可（约 5 行）——
   但那会改 runner 的判读语义，**我没有擅自动**。
3. §8 第 1 条（Jenkins）**已由本轮补上**，其余五条（平台 / runner / 仓库 / l0 处置 / 告警去向 / pipeline-daily 注释）**原样待定**。

---

## 十三、第三轮：**独立复跑**复核（2026-10-04 09:38，另一会话，不采信前两轮结论）

前两轮的读数由写配置的那个人自己报。本轮换一个会话**从头复跑 + 独立做语法核验**，
下面每条都是本轮实测，不是转抄。
命令与产物：`_ci-verify-gates-20261004-0938/gates-latest.{json,md}`（**单独一个目录**：
库根下已有一个**别的会话**在 09:36 建的同名 `_ci-verify-20261004/`，两边的产物不该混在一起）。

### 13.1 全量复跑：与 §12.3 逐项一致（可复现）

```
$ /usr/bin/python3 ci/run_gates.py --scope full --outdir _ci-verify-gates-20261004-0938
generated_at 2026-10-04T09:38:51 ｜ scope=full ｜ 退出码 1
total 14 ｜ passed 12 ｜ red ['l0','projection'] ｜ infra [] ｜ 告警 无
```

⇒ 两把补挂闸门**真的执行到了**（含 `base="root"` 那把 envelope），`l0` + `projection` 两把真红稳定复现。

### 13.2 语法核验：比前两轮多做了「内联 shell」这一层

| 核什么 | 命令 | 读数 |
|---|---|---|
| shell | `bash -n ci/run-gates.sh` / `ci/install-launchd.sh` | 均 OK |
| plist | `plutil -lint`（模板件 + `~/Library/LaunchAgents/` 已装件） | 均 OK |
| runner | `/usr/bin/python3 -m py_compile ci/run_gates.py` | OK |
| YAML | `yaml.safe_load`（GitHub / GitLab） | 均 OK（`on:`→`True` 是 YAML 1.1 正常现象） |
| **★ 内联 shell** | 把 GitHub 的 5 个 `run:\|` 块、Jenkinsfile 的 3 个 `sh '''…'''` 块**抠出来逐块 `bash -n`** | **8/8 OK** |
| Groovy | `command -v groovy` | **无 groovy ⇒ Jenkinsfile 的 Groovy 语法本轮仍无法校验**（如实登记，未验） |

「YAML 能解析」不等于「里面那段 shell 能跑」——13.2 最后两行就是补这个缺口。

### 13.3 已装 launchd 与模板的逐字 diff：只差一处

```
$ diff <(plutil -convert xml1 -o - ~/Library/LaunchAgents/com.kb.gates.plist) \
       <(plutil -convert xml1 -o - ci/launchd/com.kb.gates.plist)
22c22
< … exec /usr/bin/python3 -u ci/run_gates.py --outdir "/Users/lute/Library/Logs/kb-gates"
> … exec /usr/bin/python3 -u ci/run_gates.py --outdir "$HOME/Library/Logs/kb-gates"
```

安装器把 `$HOME` 展成了字面量，**语义相同**。但两边的命令行都**没有 `--scope`** ⇒ 已装那次的报告里
`scope` 字段为 `None`、红只有 `['l0']` ⇒ **本机唯一真在跑的定时任务跑的是 `core`（12 把）**。

### 13.4 ★ 本轮发现的**唯一一处真不一致**（要不要改，是你的决定，我没动）

| 谁 | scope | projection（实测真坏 3/6）在不在巡检范围内 |
|---|---|---|
| `ci/run-gates.sh` 默认、GitHub、GitLab、Jenkinsfile | **full** | 在 |
| **`com.kb.gates`（本机每日 14:00，唯一真在跑的）** | **core** | **不在** |

§12.2 自己立的标准是「调用行加 `--scope full` —— 否则『接上了』只是文件在、**门是关的**」。
按这条标准，**launchd 这扇门现在是关着的**：那道真坏的投影漂移，日常巡检看不见它。

要改的话是**两处**（不是一处，改完还得重装）：

1. `ci/launchd/com.kb.gates.plist` 的 `ProgramArguments` 命令行末尾加 `--scope full`；
2. `ci/install-launchd.sh` **目前对 scope 零感知**（实测 `grep -n scope install-launchd.sh` → 无命中），
   它只做路径替换 ⇒ 要么让它可选透传 `KB_GATES_SCOPE`，要么改完模板后直接手工重装。
3. 生效：`bash ci/install-launchd.sh`（幂等，含在飞守卫）。

**代价必须先说清**：切 full 后每日 14:00 的红从 **1 把（l0）变成 2 把（l0 + projection）**。
两把都是**人做**的动作、CI 修不了 ⇒ 这会改变日常信号强度，属 §12.5 第 1 条的同一件事，
**所以本轮没有替你改**。

> 转引（**不是本轮实测，我未独立复算**）：同机另一会话 09:36 的体检件称 `projection` 的 3/6 漂移
> **根因在权威侧 L3** —— `l3.json` 的 `changes[2]` 声称已回填 `owner / half_life_days / valid_until /
> effective_from` 各 509 行，实文件全空（2036 处）；并标了一条红线：**不许按脚本提示直接重生成视图**
> （修不了 R4，且会用统一常量覆盖逐条治理值 = 造假绿）。出处：`_ci-verify-20261004/msg-dryrun.txt`
> 与 `体检表-20261004-0915-逐层收口.md`。**要用这条结论请先自己复算**。

### 13.5 另一条如实登记：14:00 的「定点触发」至今**未被观测过**

`com.kb.gates` 装于 2026-10-04 00:41，最后一次报告是 **00:54:48** —— 那次是安装脚本
`kickstart` 拉起来的，**不是** 14:00 按点触发的。今天的 14:00 还没到。
⇒ 「装载 → 触发 → 出报告 → 判读」这条链里，**「按 StartCalendarInterval 定点触发」这一步仍未被实测**，
与 README 别处的措辞（「已装载、已执行」）不冲突，但**别把 kickstart 当成定点触发验过了**。

### 13.6 本轮没做的事（免得下一个人以为验过了）

- **没改任何闸门判据、没改阻断范围**（`--scope` 的默认值原样是 `core`）；
- **没动已装的 LaunchAgent**，也没重跑 `install-launchd.sh`（13.4 那两处补丁**未实装**）；
- 没碰 `kb/l7/registry/l0-expected-diffs.yaml`（`l0` 的红是取数身份问题，**不许靠豁免声明调绿**）；
- 没查 Groovy 语法（本机无 groovy），两份 CI 与 Jenkinsfile **仍未端到端跑过**（无仓库、无 runner）。


---

## 十四、第四轮：把**唯一真在跑的定时任务**那扇门打开（2026-10-04 14:1x）

背景：§13.4 如实登记了唯一一处真不一致 —— **launchd 跑 core（12 把），CI 四份配置跑 full（14 把）**，
⇒ projection（实测真坏 3/6）**不在日常巡检范围内**。§13.4 说「要改的话是两处，本轮没有替你改」，
并把它挂到 §12.5 第 1 条「scope 默认取 full 还是 core」上等拍板。本轮**按 CI 已在用的那一档把两者对齐**。

### 14.1 ★ 先更正 §13.5：14:00 的**定点触发已被观测到**（历史第一次）

§13.5 写「装于 00:41、最后一次报告 00:54:48，那次是安装脚本 kickstart 拉起来的，**不是** 14:00 按点触发」。
本轮实测推翻了这条的**现状**部分：

```
date → now=2026-10-04T14:07:51
stat -f "%Sm" ~/Library/Logs/kb-gates/gates-latest.json → 2026-10-04T14:07:14
gates-latest.json → generated_at 2026-10-04T14:07:14 ｜ scope: core ｜ total 12 ｜ exit 1 ｜ red ["l0"]
12 把闸门耗时合计 431.8s ≈ 7.2 分钟 ⇒ 起点 = 14:07:14 − 7.2min = **14:00:00**
```

⇒ 本次报告**不可能**来自 kickstart（`RunAtLoad=false`、无人手工触发），
起点与 `StartCalendarInterval` 的 14:00 严丝合缝 —— 即「装载 → **按点触发** → 出报告 → 判读」
这条链**今天已闭环**。§13.5 的说法在写它的时刻成立，现在**已过期**，故在此更正（不改原文，只登记更正）。

### 14.2 改了什么（两处，即 §13.4 点名的那两处）

| 文件 | 改动 |
|---|---|
| `ci/launchd/com.kb.gates.plist` | 命令行加 `--scope full`；文件头补「范围」一节，写明**为什么加**（与 CI 对齐）、**代价**（每日红 1 把 → 2 把）、**怎么退回 core** |
| `ci/install-launchd.sh` | ① 加 `--scope core\|full` / `--core` / `--full`，环境变量 `KB_GATES_SCOPE` 等效，优先级 `--scope > KB_GATES_SCOPE > 模板`；② 渲染时**幂等**替换 `--scope`（先归一化再写回，避免叠成 `--scope full --scope core`）；③ 非法值**拒装**（退出码 2）；④ dry-run 多打一行「生成件实际会用的 scope」（**从命令行抠出来，不是声明**） |

**没做的事**：**没有重装你已装载的 LaunchAgent**（那是改变本机日常行为、且会 bootout 掉在跑作业的动作）。
本机当前仍是 `core`，**要生效必须你跑一次**：

```bash
bash ci/install-launchd.sh          # 幂等；含在飞守卫，正在跑时会自己跳过重装
```

### 14.3 本轮实测（命令 + 读数）

| 核什么 | 命令 | 读数 |
|---|---|---|
| shell 语法 | `bash -n ci/install-launchd.sh` | OK |
| 模板 plist | `plutil -lint ci/launchd/com.kb.gates.plist` | OK |
| 模板命令行 | 抠 `ProgramArguments` | `--scope full --outdir "$HOME/Library/Logs/kb-gates"` |
| 不传 scope | `--dry-run` | 沿用模板 → `--scope full`；生成件 `plutil -lint` OK |
| 覆盖 | `--dry-run --scope core` | `--scope core`（**未叠加**，幂等成立） |
| 环境变量 | `KB_GATES_SCOPE=core --dry-run` | `--scope core` |
| 优先级 | `KB_GATES_SCOPE=core --dry-run --scope full` | `--scope full` ⇒ `--scope` 压过环境变量 |
| 简写 | `--dry-run --core` | `--scope core` |
| 非法值 | `--dry-run --scope Full` | `❌ --scope 只接受 core 或 full，收到的是：[Full]`，**退出码 2** |

**14.3 附带修掉一个自查出来的真 bug**：非法值分支最初写成
`echo "…（收到：$SCOPE）"` —— 全角 `）` 紧贴 `$SCOPE`，在 `set -u` 下参数名被读成 `SCOPE\ufffd`，
于是**拼错 scope 时你看到的是 bash 内部报错 `unbound variable`，不是人话**（功能没坏，错在错误分支）。
已改成 `printf '%s\n' "…[$SCOPE]"`（不靠相邻字符分词）并复测为 `exit 2` + 人话。
⇒ 这条**只有真去跑非法输入才会显形**，正常路径上是隐形的。

### 14.4 仍未做 / 仍未验（免得下一个人以为验过了）

- **未重装 LaunchAgent** ⇒ 模板改了，但**本机生效件仍是 `core`**（`launchctl` 里那条没动）。
- **CI 四份配置仍未端到端跑过** —— 硬前提今天**复测仍不满足**：
  `git rev-parse` → `fatal: not a git repository`；`~/actions-runner` / `~/gitlab-runner` **均不存在**；
  `launchctl list | grep -i runner` → 空。**这两步只能人做，runner 必须装在这台 Mac 上**。
- 切换后**每日 14:00 会红 2 把**（`l0` + `projection`），两把都是**人做**的动作、CI 修不了：
  `l0` = 取数身份（bot「守衡」未加成该 Base 可阅读协作者）；`projection` = 权威侧 L3 回填空值。
  **不许**靠写 `l0-expected-diffs.yaml` 或重生成视图调绿。
- 没改任何闸门判据、没动 `kb/l7/registry/l0-expected-diffs.yaml`、没碰 `scope` 的默认值（仍是 `core`）。

### 14.5 仍要你拍板的（承接 §12.5，本轮消掉 1 条）

- ~~scope 默认取 full 还是 core？~~ → **本轮按「与 CI 一致」定为 full，但决定权留在你手里**：
  不满意就 `bash ci/install-launchd.sh --scope core`，一条命令退回绿基线。
- **平台到底是哪个？**（§8 第 1 条）GitHub / GitLab / Jenkins 三份都在，**没有一份是你点过名的**。
- **runner 放哪 / 要不要把库纳入 git**（§8 第 2、3 条）—— 这两条不解决，CI 那三份配置永远只是文件。
- **`l0` 两张表怎么处置**（§8 第 4 条）、**闸门告警要不要推飞书**（§8 第 5 条）、
  **`com.kb.pipeline-daily.plist` 的错注释改不改**（§8 第 6 条）—— 原样待定。
