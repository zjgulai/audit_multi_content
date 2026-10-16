---
title: CHANGELOG（本 skill 的改动台账）
doc_type: reference
module: kb-l0-feishu
topic: changelog
status: stable
created: 2026-09-30
updated: 2026-09-30
owner: self
source: human+ai
---

# CHANGELOG

规则（SKILL.md §8.3）：任何 skill 文件被改，同一次改动里必须
① 备份到 `~/.dsh/backups/kb-l0-feishu-<ts>/`；② 在本文件追加一条；
③ `SKILL.md` bump `version` 与 `last_updated`；④ 验一次明文（不是信封态）。

写"改了什么"时**必须写依据**（哪个 RUN / 哪次事故），否则后来人无从判断该不该回退。

---

## v1.2.3 · 2026-09-30

**依据**：用户明确要求 —— 「你每次跟我确认的所有事情，都需要带上你的建议」。
这不是文风偏好，是**交付契约**：把选择权交出去却不给判断，等于把活推回给人。

**SKILL.md**

- 新增 **§6.1 问人的格式**：每条待确认事项四要素俱全 ——
  ① 事实（实测数字 + 证据路径）② **我的建议（必须明确选一个）** ③ 理由（代价/风险/可逆性/口径冲突）
  ④ 取舍（其他选项差在哪、不做会怎样）；**建议项排第一**；
  允许"这条没建议"，但必须写明**缺哪条信息**才能形成建议；
  组织成"回一句『按你的建议做』即可整体放行"的形式。
- §5 交付物新增第 6 项：**待确认清单**（按 §6.1 写）。

**references**

- `gotchas.md` 新增 §五「问人的坑」：把选项丢给人不给建议 / 用"等你决定"掩盖"没想清楚"。

---

## v1.2.2 · 2026-09-30

**依据**：用户问"每次 L0 对齐会不会有重复项，比如同一张图存了几次"。做了一次真审计，
结果分三层，其中**只有台账那层是我们的问题**。证据：`kb/l8/runs/20260930-1045-l0-dup-audit.json`
（审计实跑）+ 飞书侧回源核对（`真实 token 数 = 21`）+ `/tmp/ledgertest` 单元测试（5 行台账 / 3 轮）。
备份：`~/.dsh/backups/kb-l0-feishu-20260930-1040/`。

**新增（库内脚本）**

- `kb/l8/audit_l0_duplicates.py`：L0 重复项审计，**只读**，一次出四段 ——
  A 磁盘字节重复（sha256 分组 + 可省字节）/ B 台账行重复（空转再登记，按写入者归类）/
  C 记录层（record_id 唯一性、记录内容重复）/ D 磁盘与台账的 token 双向差集。
  **不把 A/C 混成一句"有重复"**：C 的"同一素材被多条记录引用"是源侧事实。
- `kb/l8/l0_ledger.py`：台账写入助手 `append_changed()` —— 有变化才追加，未变的刷新
  `kb/l0/registry/last_seen.json`；判等只看 `status/sha256/sha256_input/sha256_state/revision`；
  **从不重写或删除已有行**；落盘走 `tempfile` + `/bin/cp`（避免信封态）。
- `kb/l8/audit_l0_duplicates.py` 接入日常：收尾阶段可与 `retro.py` 一起跑。

**修复（幂等性缺陷，不是数据缺陷）**

- `store_l0_attachments.py`、`verify_l0_urls.py`、`verify_l0_nonrecord2.py` 接入
  `append_changed()`：此前它们（以及另外 10 个写入者）**每轮无条件追加整行**。
  实测：附件脚本一次 `--apply` 会重开 304 行登记，修复后 **304/304 跳过**；
  URL 脚本 150 行里首轮有 150 行是"口径归一"（真变化，照写），次轮起为 0。
- 旧版脚本按库内惯例归档（后缀 `.before-ledger-guard-<hash>`）：
  `kb/l8/_archive/store_l0_attachments.py.before-ledger-guard-1b64d2dadf3c3752` 等 3 个，
  差异各 7–8 行。**未删任何文件、未改写任何历史行。**
- 剩余 10 个写入者**尚未接**（改的是台账语义，要先看空转量再逐个接）。

**references**

- `SKILL.md` §8.1：收尾除 `retro.py` 外**同时跑 `audit_l0_duplicates.py`**，并给出 A/B/C/D 四段的
  处置口径（A 位要人拍板、B 是工具问题、C 必修、D 给原因码）；写明"别把源侧重复当自己的 bug 去删"。
- `scripts.md`：新增「台账写入（只写变化，不写空转）」小节 + 辅助脚本表两行。
- `gotchas.md` §三 新增 3 行：三种"重复"必须分开报 / 写入者无条件追加 / 别把源侧重复当自己的 bug 去删。

**待用户拍板（本 skill 不自动做）**

- 磁盘 A 层冗余 **468.4 MB（占 31.0%）**：是否合并？三条路 —— 保持镜像原样／硬链接去重（省空间、
  路径不变、风险低）／内容寻址 + 引用表（省最多，但改 L1/L6 读取路径）。默认**不动**。

---

## v1.2.1 · 2026-09-30

**依据**：v1.2.0 的 `retro.py` **第一次真跑就误报**，以及同一次真跑暴露的信封态。
证据：`kb/l8/retro/ledger.ndjson` 第 1–4 行（误报原样保留，append-only）＋ 第 7 行（更正说明）；
`/tmp` 对照实验（5 组写盘方式 × 信封判定）。
备份：`~/.dsh/backups/kb-l0-feishu-20260930-1030/`。

**scripts/retro.py（三处自身缺陷，全属"工具 bug 被读成数据缺陷"）**

- **阶段产物名写死**：三处与真实文件名不符（真实为 `<RUN>-l0-nonrecord-verify.json` /
  `-l0-nonrecord-verify2.json`，且 L6 的 `scope-append` 落在 `kb/l6/runs/`），
  于是**已跑过的阶段被报成缺失**。
  → 改为**按关键词从 `kb/l8/runs` 与 `kb/l6/runs` 实际发现**（`STAGE_PATTERNS`），
  并新增 `products_found` 记录本轮到底有哪些产物。
- **"缺跑"判定取反**：循环遍历的是**已找到的键**而不是"全部已知键 − 已找到"，
  于是本 RUN 明明有的阶段也进了 `missing`（实测一次报 9 个"漏跑"）。
- **"本 RUN 没有" ≠ "没跑"**：一次同步很容易跨多个 RUN 落盘（实测我用过 8 个）。
  新增 `stages_elsewhere`：本 RUN 没有、别的 RUN 下有的阶段单独归一类
  （性质是 run_id 口径不统一，生成 `run_id_split` 候选），**只有哪儿都没有才算 `stages_missing`**。
- 台账每行新增 `retro_version`（回答"这行是哪版工具写的"）；
  `correction: true` 的更正行**不计入轮数、不参与原因码累计**。

**信封态（新发现，已实测复现）**

- python 直接 `open(path,"w"/"a")` **建或截断**一个文件后，bash 侧 `stat`/`wc -c` 看到的是
  「真实长度 **+4096**」（内容其实是完整明文），harness 的 read 工具按这个尺寸去读，
  于是判成 `binary file`、**读不了** —— 实测 `references/gotchas.proposals.md` 被
  `retro.py` 追加后当场读不了。
- 对照实验（5 组写盘方式 × 信封判定）：python 直接建/截断 → 信封态；
  **子进程 `/bin/cp` 覆盖 → 明文（稳）**；`os.replace(tmp, path)` → **当场尺寸对得上、
  下一轮 `stat` 又变信封**（先按它改过一版，被实测打回）。
  → `retro.py` 两个落盘点改为 **`mkstemp` → 写 → 子进程 `/bin/cp` 覆盖**（`os.replace` 只留作目标不存在时的退路）；
  `append_lines()` 保留"只追加不改旧行"的语义。已信封的 `gotchas.proposals.md` 用 python→`/tmp`→`cp` 修复，
  修复后换一个新 shell 复查，bash `stat` 与 python `os.path.getsize` 一致。
- 候选块标题加上工具版本标记（`## <RUN>（<时间> · retro 1.2.1）`），
  并在 `gotchas.proposals.md` 顶部加「⚠ 历史更正」段：**10:27–10:29 之间的候选块全部作废**
  （它们是 1.2.0 的误报），无版本标记者即作废块 —— 文件照样追加，**不改写历史**。
- `gotchas.md` §二 新增 3 行（产物名写死+判定取反 / python 建截断→信封态），
  §一 也补了同类行；`scripts.md` 新增「收尾」小节（`preflight.sh` 与 `retro.py` 的调用式、
  写哪里、关键约定）。

**README.md / `.skill-meta/manifest.yaml`**

- `README.md`：目录树补 `gotchas.proposals.md` / `CHANGELOG.md` / `retro.py`；
  新增「自成长（SKILL.md §8）」小节（事实层全自动 / 规则层永不自动改 / 落盘留痕）；
  渐进式披露表补 `retro.py`。
- `manifest.yaml` 补齐漂移：`version` 1.0.0 → 1.2.1；`scripts.count` 1 → 2（加 `retro.py`）；
  `references.count` 4 → 6（加 `gotchas.proposals.md`、`CHANGELOG.md`）；`updated_at` 刷新；
  `workflow.modes` / `steps` 补上 v1.2.0 新增的**阶段 9.5**（原表里没有，属登记表漂移）。

---

## v1.2.0 · 2026-09-30

**依据**：一次完整的 L0 增量对齐（飞书侧新增 7 条负面样本）暴露出的 12 处可优化点。
证据 RUN：`20260930-0930`（对账+入库）、`20260930-0950`（复验）、`20260930-1100/1105`（结构层）、
`20260930-1115/1120`（非记录）、`20260930-1135`（URL 判等）、`20260930-1140`（scope 缺口）、
`20260930-1150`（阶段 10）。原始记录：`kb/l8/runs/20260930-0150-batch-notes.json`（R1–R13）。

**SKILL.md**

- 红线新增第 8 条：**对象存在但拿不到正文 → 换通道**；并明确 `sha256_state=no_scope`
  的行是**每轮必修的欠账**，不是终态。
  > 依据：3 个 slides + 1 个 sheet 因"缺 scope"挂了一整天没人回头，而 scope 早已具备。
- §2 补：`不适用` 的"证据"格式固定（字段名+筛选条件+条数+快照路径+RUN）；
  `S_feishu` 的机器来源改为 `kb/l0/manifest.jsonl` 的 `source_kind` 分布。
- §3.1 身份结论由"bot 能读 → 直接用 bot"改为**按能力矩阵逐 Base 选身份**，
  并写明 bot 对第 2 个 Base 的两张表读不到 `+field-list`；要求字段读失败时**拒写快照**。
  > 依据：preflight 只探一张表就外推，导致两张表快照被刷成 0 字段。
- §3.1 补：取设备码必须 `--no-wait --json > 文件` 再解析（`head/tail` 会截断 URL 与 device_code）。
  > 依据：本次因此重发了一条码，违反"一次只发一条"。
- §4 新增"阶段 → 该先读哪份 reference"对照表（"读取条件"落地成清单）。
- §4 新增**阶段 9.5 索引层**（`l6_scope_append` → `l6_build --accept-scope-delta --apply`
  → `l6_integrity` → retriever 抽查）；并写明 `l6_build.py` **已有干跑档**。
  > 依据：7 条新记录走完 L0→L1→L2 后，不补这一段一条也搜不到。
- §4 阶段 10 更正调用式：`roundtrip_check.py` 必须带 `L8_KB_ROOT=<kb>/view`；
  `projection_reconcile.py` / `envelope_census.py` **不收位置参数**；
  并新增 **FAIL 分级**（同步当天"权威库被改动"必然红 → 判据是"变的是不是本轮造成的"；
  一次性快照型基线要有承认通道）。
- §7 弱证据给出固定命令，并写明 **run_id 不能当时间读**（实测比墙钟快数小时）。
- 新增 **§8 自成长**：事实层全自动（`scripts/retro.py`）、规则层不许自动改、落盘留痕三件套。

**references**

- `gotchas.md`：新增 3 条（管道截断取码 / OCR 脚本读死历史快照 / 一次性基线必红）。
- `coverage-matrix.md`：`no_scope` 标注为欠账；补"不适用"证据模板。
- `scripts.md`：命令表补必需参数 / 必需环境变量 / 是否收 RUN / 该用哪个身份；
  补阶段 9.5 与 `close_stale_scope_gaps.py`。
- 新增 `gotchas.proposals.md`（脚本生成的候选，与已确认坑分开）、`CHANGELOG.md`（本文件）。

**scripts**

- 新增 `retro.py`（自成长事实层：记账 + 与上轮做差 + 重复计数 + 生成候选；只写台账与候选）。
- `preflight.sh`：由"探一张表"改为**跨表跨 Base 抽样 + 输出能力矩阵**。
