---
title: Scripts（脚本清单与用法）
doc_type: reference
module: kb-l0-feishu
topic: scripts
status: stable
created: 2026-09-29
updated: 2026-10-09
owner: self
source: human+ai
---

# 脚本清单与用法

**读取条件**：执行具体阶段前读对应小节。脚本全部位于库内 `kb/l8/`（`<KB>` = 库根）。

## 约定

- 统一 run_id：`RUN=<YYYYMMDD-HHMM>`；产物落 `kb/l8/runs/<RUN>-*.json`。
- 带 `--apply` 的脚本**先不带参数跑一遍**（预演），拿到差异再决定。
- 全部从库根执行，避免相对路径错位。
- **run_id 不是时间**：实测会话标号可能比机器墙钟快数小时；时间线以文件 mtime / `observed_at` 为准。

## 命令参数速查（2026-09-30 实测校正）

> 这一栏是踩出来的：`l6_build.py` 后来加了干跑档、`roundtrip_check.py` 要一个环境变量、
> 两个收口脚本根本不收 RUN —— 照旧写法跑会"看起来跑完了、其实什么都没做"。

| 脚本 | 收 RUN？ | 必需参数 / 环境变量 | 身份 | 备注 |
|---|---|---|---|---|
| `align_l0_feishu.py` | ✅ | — | `L8_AS`（默认 bot；**部分表须 user**） | `--check` 为只读档，快照落 /tmp |
| `align_l0_schema.py` | ✅ | `--apply` 才刷新快照 | **user**（bot 对第 2 Base 两张表读不到字段） | 字段读失败应拒写，不许写 0 字段快照 |
| `reconcile_l0_feishu.py` | ✅ | — | bot | 表整批替换的认领与归档 |
| `emit_l0_manifest_reconcile.py` | ✅ | `--apply` | bot | **先用一条既有行反向复现 sha256 再批量写** |
| `verify_l0_nonrecord.py` / `verify_l0_nonrecord2.py` | ✅ | `--apply` | user | |
| `refresh_l0_drifted.py` | ✅ | `--apply` | user | 漂移刷新，旧文件先归档 |
| `store_l0_attachments.py` | ✅ | `--apply` | **bot**（附件字节权限在应用侧） | 全量重扫，会给既有行重复追加 |
| `close_stale_scope_gaps.py` | ✅ | `--apply` | user | 关"登记时缺 scope"的欠账（红线 8） |
| `ingest_l0_new_records.py` | ✅ | `--apply`；`--restamp` / `--attachments` | user（附件下载转 bot） | 新增记录入库；台账**必需键**硬校验 |
| `ocr_attachments.py` | ✅ | `--apply` / `--purge-images` | bot | **输入快照必须按 RUN 绑定**，别读历史快照 |
| `apply_ocr_to_l1.py` | 两参：`<OCR_RUN> <L1_RUN>` | `--apply` | — | 与 OCR manifest 对账数字 |
| `fetch_video_bytes.py` | ✅ | `--apply`；`--only <tok>[,<tok>…]`；`L8_VIDEO_AS` | **bot**（实测 14/14） | 两级通道 `+preview --type source_file` → `docs +media-download`；**`drive +download` 返 403（通道问题，不是权限）** |
| `extract_video_keyframes.py` | ✅ | `--apply`；`--only <tok>[,…]`；`--no-asr`；`--min-frames`/`--every`/`--max-frames` | — | 帧落 `kb/l1/media/video_*/frames/`（**png**）；走既有图片 OCR 缓存；`--apply` **自动接**口播转写 |
| `extract_video_asr.mjs` | ❌ **不收 RUN** | `--apply`；`--only <单个 tok>`；`SHOUHENG_AGENT_DIR` | — | macOS Speech.framework 本机 ASR；**`--only` 只收一个 token**；`no_speech` 是读数不是失败 |
| `extract_l1_new_resources.py` | ✅ | `--apply` | — | |
| `l2_split_run.py` | ✅ | `--apply`（**不带即干跑**） | — | 缺口口径 = "没有当前 sha 的单元" |
| `l6_scope_append.py` | ✅ | `--resources a,b` `--note` `--apply` | — | 逐条校验后才写白名单 |
| `kb/.work/l6_build.py` | ✅ | **`--apply`**（否则只打 `[dry-run]` 就退）＋ `--accept-scope-delta` | — | |
| `kb/.work/l6_integrity.py` | ✅ | `--accept-frozen-baseline "<理由>"` 用于承认基线 | — | 10 项闸门 |
| `workflow_check.py` | ✅ | — | — | 同步当天部分判据**必然红**，见 SKILL.md 阶段 10 |
| `roundtrip_check.py` | ✅ | **`L8_KB_ROOT=<库根>/kb/view`** | — | 默认根是错的，会 FileNotFoundError |
| `projection_reconcile.py` | ❌ **不收位置参数** | 只吃 `--json` / `--json-out` | — | |
| `envelope_census.py` | ❌ **不收位置参数** | 只吃 `--json` | — | 活路径必须 0 |
| `build_view.py` | — | `--run $RUN` | — | 需刷新工作台投影时才做 |

## 身份该用哪个（一句话）

| 操作 | 身份 | 依据 |
|---|---|---|
| 读 Base 记录 / 表清单 | bot（默认） | 实测可读；个别表见下 |
| **读字段定义 `+field-list`** | **user** | 实测 bot 对 `专家修订汇总表`、`内容公式（仅供参考）` 读不到 |
| **下载附件字节** | **bot** | 该权限在应用侧（守衡），用户身份反而不行 |
| 读 docx / slides / sheets 正文 | user | 对象级权限 |
| 读 wiki 节点 | user | 资源级 ACL |

## 阶段 1 · 记录层核对

```bash
python3 kb/l8/align_l0_feishu.py $RUN          # 只读全表逐字段对账
```

- 身份：默认 bot；`L8_AS=user` 可切用户身份。
- 产物：`kb/l8/runs/$RUN-l0-align.json`，看 `summary`：
  `same / only_feishu / only_l0 / changed` + `record_files_not_registered_total`。

## 阶段 2 · 结构层核对

```bash
python3 kb/l8/align_l0_schema.py $RUN [--apply]
```

- 比 `field_id ↔ 名 ↔ 类型`，刷新 `kb/l0/registry/kb.json` 的 `schema_snapshots`。

## 阶段 3 · 认领与归档

```bash
python3 kb/l8/reconcile_l0_feishu.py $RUN
```

- 处理"表整批替换"（新记录认领 + 旧记录归档）与 `材料收集` 只留「审核状态 = 通过」。

## 阶段 4 · 台账补齐

```bash
python3 kb/l8/emit_l0_manifest_reconcile.py $RUN [--apply]
```

- **反向复现校验**：先用一条既有 `manifest.jsonl` 行跑一遍 sha256 计算，确认口径一致再批量写。

## 阶段 5 · 非记录资源核验

```bash
python3 kb/l8/verify_l0_nonrecord.py  $RUN [--apply]
python3 kb/l8/verify_l0_nonrecord2.py $RUN [--apply]
python3 kb/l8/refresh_l0_drifted.py   $RUN [--apply]
python3 kb/l8/store_l0_attachments.py $RUN [--apply]
python3 kb/l8/sync_l0_changed_records.py        # 变更记录同步
```

## 阶段 6 · 图片 OCR

```bash
python3 kb/l8/ocr_attachments.py $RUN
python3 kb/l8/apply_ocr_to_l1.py <OCR_RUN> <L1_RUN> [--apply]
python3 kb/l8/verify_l0_nonrecord2.py $RUN [--apply]   # 复核归档 docx 与 OCR 覆盖
```

- 缓存闸门：`vision-jxa-2.0`；新旧图 `file_token` 交集为 0 → 缓存作废。

## 阶段 7 · 视频

> **2026-10-09 补齐**：本节此前**只有一行注释、没有任何命令** ⇒ 「视频」这一类**在日更里没有落点**，
> 新视频永远不进 L0/L1，只有人手动跑时才动。口径本来就是全的（`coverage-matrix.md`：
> 「必须提字幕 + 抽关键帧，两条都要」），缺的只是命令。

```bash
python3 kb/l8/fetch_video_bytes.py       $RUN [--apply] [--only <tok>[,<tok>…]]
python3 kb/l8/extract_video_keyframes.py $RUN [--apply] [--only <tok>[,…]] [--no-asr]
node    kb/l8/extract_video_asr.mjs      --apply [--only <tok>]        # 通常由上一行自动接
```

- **① 字段级非空筛选（留证）**：对 `视频素材` 字段做**字段级**非空筛选并留证。
  结果为 0 条 ⇒ 结论写 `不适用（飞书侧视频素材 0 条，附筛选证据）`，**既不能跳过、也不能报成「缺失」**。
- **② 取字节** → `kb/l0/attachments/视频/`，回写 `media_refs[].media_path/sha256/sha256_state`。
  · 身份走 `L8_VIDEO_AS`（脚本默认 `user`；**实测 `bot` 跑通 14/14**）。
  · **两级通道**：`drive +preview --type source_file` → 失败降级 `docs +media-download`。
  · ⚠️ **`drive +download` 对这些 token 返 HTTP 403 —— 那不是权限问题，是通道不对。**
    别据此写 `no_scope` / `blocked_by_library_setting`：那两个结论要等**换过通道之后**才成立。
- **③ 抽帧 + 画面文字** → L1 `video_ocr_segments`。
  场景切换 `gt(scene,0.3)`；场景帧不足按 `--every` 秒补；上限 `--max-frames`（默认 40/视频）。
  帧落 `kb/l1/media/video_<slug>/frames/`（**png**），**走既有图片 OCR 通道**
  （同一台 macOS Vision、同一套 `_cache/<图片sha256>.json`），段锚点 `#t.MM:SS-MM:SS`。
- **④ 口播转写** → L1 `video_asr_segments`。`--apply` 时由 ③ **自动接**（逃生口 `--no-asr`）。
  · 引擎 = **macOS Speech.framework**（纯本机、零第三方、不出机器）；**不走 whisper / torch**。
  · 依赖跨仓 `tools/agent/asr.mjs`（`SHOUHENG_AGENT_DIR` 可覆盖）；缺了会**打印手动命令**，不静默。
  · **整段文本、没有逐句时间码** ⇒ 口播**不可按时间定位**（画面文字那半才有 `#t.`）。
  · `no_speech` / `no_audio_track` 是**读数**（人没说话 / 本来没音轨），**不是失败**；失败另记 `kind`。
- **⑤ 复核**：`verify_l0_nonrecord2.py $RUN [--apply]`。
- **实测基线（2026-10-09）**：登记 14 ｜ 有字节 **14**（647.0 MB）｜ 帧 **292** ｜ 画面文字 **11,291** 字 ｜
  口播 **13 条有文本 + 1 条 `no_speech`**。
- ⚠️ **`--only` 的形态两处不同**：两个 `.py` 收**逗号分隔多值**；`extract_video_asr.mjs` 只收**一个** token。

## 阶段 8 · 链接

```bash
python3 kb/l8/drill_links_2levels.py  $RUN
python3 kb/l8/fill_drill_failures.py  $RUN [--apply]
python3 kb/l8/verify_l0_urls.py       $RUN
python3 kb/l8/verify_urls_headless.py $RUN
python3 kb/l8/verify_urls_shingles.py $RUN                       # 词 8-gram 双向重叠
python3 kb/l8/recrawl_all_urls.py     $RUN [--apply] [--limit N]
python3 kb/l8/recrawl_jsnoise_urls.py $RUN [--apply]
```

## 阶段 9 · 下游重跑（不动 L0）

```bash
python3 kb/l8/extract_l1_new_resources.py $RUN [--apply]
python3 kb/l8/l2_split_run.py             $RUN
python3 kb/l8/l3_distill_run.py           <L3_RUN>
python3 kb/l8/l3_reject_ledger_rebuild.py <L3_RUN> [--apply]
python3 kb/l1/index/rebuild_l1_index.py
```

> `l3_distill_run.py` 以 `w` 模式覆盖 `rejected.jsonl`——跑前归档现状，跑后重建逐单元台账。

## 阶段 9.5 · 索引层（新数据"能被检索到"才算同步完）

```bash
python3 kb/l8/l6_scope_append.py $RUN --resources <资源或 token> --note "<理由>" [--apply]
python3 kb/.work/l6_build.py $RUN --accept-scope-delta --apply
python3 kb/.work/l6_integrity.py $RUN
python3 kb/l6/retriever.py --query "<新数据里的一个词>" --top 3
```

> L2 切出单元 ≠ 能被检索到。L6 是**人工核定白名单**（`kb/l6/SCOPE.txt`），
> 不 append 就永远查不到；改白名单必须带 `--accept-scope-delta` 重建并在 registry 留口径差额。
> **`l6_build.py` 不带 `--apply` 只会打一行 `[dry-run]` 就退出** —— 别以为它跑完了。

## 阶段 10 · 收口核验

```bash
python3 kb/l8/workflow_check.py $RUN
L8_KB_ROOT="$PWD/kb/view" python3 kb/l8/roundtrip_check.py $RUN
python3 kb/l8/projection_reconcile.py
python3 kb/l8/envelope_census.py
python3 kb/l8/build_view.py --run $RUN
```

## 收尾（本 skill 自带，不在库内）

```bash
bash  ~/.dsh/skills/kb-l0-feishu/scripts/preflight.sh            # 动手前跑：两身份 × 跨表跨 Base 能力矩阵（只读）
python3 kb/l7/skills/kb-l0-feishu/scripts/retro.py $RUN \
        [--align-run <别的RUN>] [--kb <库根>]                       # 收口后跑：记这一轮的事实 + 出升级候选
```

> **`retro.py` 的路径写「库内源」（`<库根>/l7/skills/kb-l0-feishu/`），不要写 `~/.dsh/skills/…`。**
> 2026-09-30 之前这里写的是装载位路径，而从装载位调用时脚本把候选写在**脚本自己旁边**
> → 写进装载位、源不动，`skills_check` 第 3 类（副本不一致）因此连红四次（13:10 / 13:38 / 13:46 / 14:50），
> 每次都要人把装位回灌源才收口。**该写法已废**：落点现按库根解析到库内源（`retro.py` 顶部 `PROPOSALS`），
> 并加了「候选落点命中装载位即拒跑」护栏；写完之后脚本会**当场把这一个文件镜像到装载位**
> （`mirror_to_install_slots`，只镜自己刚写的文件、且只在**权威库根**下发生）。
> → **一次 `retro.py` 跑完，源与装位逐字节相同：第 3 类两个方向都不会红，也不必再手工回灌。** 纪律见
> `l7/registry/skills.yaml` :: `meta.single_writer_rule`（一个 skill 只有一个可写位置 = 库内源；
> 装载位是只读运行副本）。

| 脚本 | 干什么 | 写哪里 | 关键约定 |
|---|---|---|---|
| `preflight.sh` | 设备码/登录态、两身份对**多张表**、附件字节、docx/slides/sheets 逐项探活；输出能力矩阵 | 只读（快照落 `/tmp`） | `ADVISORY` = 换身份即可，`BLOCKER` = 本阶段做不了 |
| `retro.py` | 从**既有产物**机械推导本轮事实：`summary`、原因码集合、与上轮差、重复码累计轮数、阶段产物齐不齐 | `kb/l8/retro/ledger.ndjson`（append-only）＋ `<库根>/l7/skills/kb-l0-feishu/references/gotchas.proposals.md`（**库内源**，不写装载位） | **只写这两个地方**：不写 SKILL.md、不改闸门（§8.2）。阶段产物**按关键词实际发现**，不写死名字 |

`retro.py` 读的几个量：`<RUN>-l0-align.json` 的 `summary` 与 `manifest`、各阶段产物是否存在、
`stage_products` 命中情况；再拿 `ledger.ndjson` 里的历史算"新原因码 / 累计 ≥2 轮"。
**缺的阶段产物分两种**——`stages_elsewhere`（本 RUN 没有、别的 RUN 下有；性质是 run_id 口径不统一）
与 `stages_missing`（哪儿都没有；性质是"以为跑了其实没跑"）。后者才生成 `stage_not_run` 候选。

> 落盘一律 `mkstemp` 到 `/tmp` → **子进程 `/bin/cp` 覆盖**：python 直接 `open(path,"w")` 建/截断会留下**信封态**
> （bash `stat` 虚高 4096，harness 的 read 工具判成 `binary file`）；`os.replace()` 当场看着正常、
> **下一轮 stat 又变信封**，别用。详见 `gotchas.md` §二。

## 台账写入（2026-09-30 起：只写变化，不写空转）

```bash
python3 kb/l8/audit_l0_duplicates.py $RUN            # 只读审计：A 磁盘字节 / B 台账行 / C 记录 / D 差集
```

- `kb/l8/l0_ledger.py`：**共享写入助手**。`append_changed(manifest, rows, run=…)` 只追加
  "和上次不一样"的行（`status / sha256 / sha256_input / sha256_state / revision` 任一不同）；
  没变化的资源改为刷新 sidecar `kb/l0/registry/last_seen.json`（保住"这轮还看见它"，又不让台账膨胀）。
  **从不重写、从不删除已有行。**
- 已接入：`store_l0_attachments.py`、`verify_l0_urls.py`、`verify_l0_nonrecord2.py`。
  其余写入者（`emit_l0_manifest_reconcile.py`、`verify_l0_nonrecord.py`、`ingest_l0_new_records.py`、
  `close_stale_scope_gaps.py`、`recrawl_*.py`、`ocr_scanned_pdfs.py` …）仍是**无条件追加**，
  再接之前先跑一次 `audit_l0_duplicates.py` 看它们的空转量。
- 依据（实测）：修复前所有写入者都无条件追加 —— 5,361 行台账 / 2,112 个唯一资源（膨胀 2.5 倍），
  其中 **1,621 行是空转再登记**；一次全量同步哪怕源侧没变也会再追加约 700 行。
  单看附件：`store_l0_attachments.py` 一次 `--apply` 会给 **304** 行（负面样本表活跃附件）
  重开一遍登记，修复后实测 **304/304 全部跳过**。

## 辅助脚本

| 脚本 | 用途 |
|---|---|
| `kb/l8/audit_l0_duplicates.py` | L0 重复项审计（A 磁盘字节 / B 台账行 / C 记录层 / D 差集），只读 |
| `kb/l8/l0_ledger.py` | 台账写入助手：只写变化，未变的记 `last_seen`（不做历史改写） |
| `kb/l8/projection_reconcile.py` | `kb/view` 投影 vs 权威库漂移 |
| `kb/l8/envelope_census.py` | 活路径信封普查 |
| `kb/l8/workflow_check.py` | 流程一致性检查 |
| `kb/l8/roundtrip_check.py` | 往返一致性检查 |

## lark-cli 常用命令

```bash
export PATH="$HOME/.dsh/bin:$PATH"
lark-cli auth status --profile dsh-kb
lark-cli base +url-resolve --url '<URL>' --as bot --profile dsh-kb
lark-cli base +record-list --base-token <T> --table-id <tbl> --page-size 1 --as bot --profile dsh-kb
lark-cli base +field-list  --base-token <T> --table-id <tbl> --as bot --profile dsh-kb
lark-cli drive +preview --type source_file --file-token <ft> --profile dsh-kb
lark-cli slides +xml-get  --file-token <ft> --profile dsh-kb
lark-cli sheets +workbook-* --file-token <ft> --profile dsh-kb
```
