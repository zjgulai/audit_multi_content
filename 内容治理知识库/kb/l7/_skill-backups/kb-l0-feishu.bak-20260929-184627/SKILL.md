---
name: kb-l0-feishu
description: |
  把 Momcozy 内容治理知识库的 L0（源层）与飞书侧源数据做每日同步与核对，飞书侧全程只读。
  当用户说「L0 同步 / L0 对齐 / L0 和飞书对一下 / 库和飞书一致吗 / 飞书侧数据变了吗 /
  跑一下每日同步 / 知识库该同步了 / 对账一下 / 核对一遍」时使用；
  当用户报「飞书侧改了什么」「库里这条怎么不见了」「图片/视频/链接有没有漏」，也使用。
  触发词：L0同步、L0 对齐、L0 落库、L0 对账、飞书侧对账、源数据同步、库和飞书一致、
  每日同步、daily sync、reconcile L0、sync L0、kb-l0-feishu。
  不适用：判断一段内容能不能发（走 kb-content-review）；问知识库怎么建的、字段与分层定义
  （读 _meta/GUIDE.md）；只改 L1–L7 的下游优化；没有飞书侧源、纯本地文件的场景。
version: "1.0.0"
last_updated: 2026-09-29
license: "Proprietary — Momcozy internal use only"
complexity: "complex"
compatibility:
  claude: { status: "native" }
  kimi: { status: "native" }
  cursor: { status: "native" }
  gpt: { status: "bridge", limitations: ["脚本执行需适配"] }
  minimax: { status: "bridge", limitations: ["长表格需简化"] }
  dsh: { status: "native", notes: "lark-cli + python3 同机可用" }
  codex: { status: "native" }
---

# L0 ↔ 飞书侧源数据 · 每日同步

## 0. 一句话

**L0 就是飞书侧源数据的副本，任何差异都算缺陷。**
本 skill 做两件事：① 把 L0 对齐到飞书侧（只读核对 → 按需认领 / 归档 / 补台账）；
② 按需把下游 L1→L2→L3 重跑到与 L0 一致（**重跑下游时不动 L0**）。

## 1. 红线（违反即中止并报告）

1. **飞书侧零改动**：不建字段、不改状态、不写回、不动权限。全程只读调用。
2. **L0 只与飞书对齐**：优化 L1–L7 时一律不碰 L0。
3. **不删除**：被替换 / 失效 / 退役的产物一律移入 `_archive/`，并留 manifest。
4. **不猜、不伪造**：读不到就写原因码（`gone` / `no_permission` / `no_scope` /
   `not_found` / `blocked_by_library_setting`）。**不许用占位或推测内容填充**，
   不许把 `forbidden` 含糊成 `pending`；OCR 认不出来就写认不出来。
5. **写操作默认预演**：带 `--apply` 的脚本先不带 `--apply` 跑一遍，拿到差异再决定。
6. **写入只落 `kb/` 下**；`kb/` 不得位于任何飞书同步目录内。
7. **不许"没提就不查"**：见 §2，每类资源在报告里都必须有结论。

## 2. 核对范围（硬性）

逐类字段口径见 `references/coverage-matrix.md`（**开始核对前先读**）。三条不可协商：

- **图片必须 OCR**：字节存 L0，OCR 文本落 **L1**。认不出来就写认不出来。
- **视频必须提字幕 + 抽关键帧**（关键帧按图片走 OCR）。若字段级筛选显示飞书侧为 0 条，
  结论写 **`不适用（附筛选证据）`** —— 既不跳过，也不报成"缺失"。
- **链接必须下钻两层**：第 1、2 层抓正文落快照，**第 3 层只记边、不抽内容**；
  外链用统一口径重抓后再比。

**四态制**：每类资源只能是
`已对齐` ｜ `不适用（附证据）` ｜ `读不到（原因码）` ｜ `不可核（原因码）`。
没有"没提就不查"这个选项。

**覆盖率闸门**（收尾必做）：算飞书侧实际资源类型集合 `S_feishu` 与报告出现过的 `S_report`，
必须满足 **`S_feishu ⊆ S_report`**，缺类回到矩阵补做，**不许收口**。

## 3. 库根与凭据

| 项 | 值 |
|---|---|
| 权威库根 | `<工作区>/知识库/内容治理/kb`（`~/.dsh/Momcozy知识库/kb` 是它的软链接） |
| 入口 Base | `GnRZbIuXraCzf0sGr2UcmZ62nfc`（`材料收集` = `tblMGtPfe8ZUsEdP`、`负面样本` = `tbld8qE92YaY38Yz`） |
| CLI | `~/.dsh/bin/lark-cli`（**不在 PATH**） |
| 可用身份 | profile `dsh-kb`（显示名 **「守衡」**`cli_aa2243de0438dcd7`）：**bot 身份可读 Base / 记录 / 附件** |
| 不可用身份 | 默认 profile「刘华丽的飞书CLI」（`cli_aa2e11d952f85be9`）**调不动 Base 接口**，别把授权加在它上面 |

细节（设备码规则、ACL 判定、换通道取正文、复开条件）见 `references/auth-and-permissions.md`。

### 3.1 阶段 0：前置自检（必须先跑；不通过就停下来报"缺什么"）

```bash
bash scripts/preflight.sh
```

**bot 能读 → 记录层 / 结构层核对直接用 bot，不需要设备码。**
只有对象级权限必须走用户身份时才发设备码，且**一次只发一条**（10 分钟有效，连发会顶掉上一条），
码里**只放缺的那一个 scope**（不要全量重申请，会卡在管理员审核）。

### 3.2 权限问题判定顺序（照这个顺序问，别乱试）

1. `token expired` / `token_missing` → **不是权限，是登录态掉了** → 发一条设备码。
2. `91403` / `1063002` / `40403 DENY` → **资源级 ACL**：要所有者在**能调接口的那个应用（守衡）**上加协作者。
   注意：**「用户自己打开得开」≠「应用读得到」，是两套权限**。
3. 附件字节 `403` → 先做**决定性实验**：用**同一身份**上传一个小文件，再下载回来。
   - 下得回来 → **库级限制**（Base「禁止下载、复制、打印」）。加 scope 没用，**连所有者也被挡** →
     标 `blocked_by_library_setting` + 复开条件，**不再重试**。
   - 下不回来 → 才是缺 `drive:file:download`。
4. 拿不到正文但对象存在 → **换通道**：`drive +preview --type source_file`（原件，非预览）、
   `slides +xml-get`、`sheets +workbook-*`。

## 4. 执行序列

统一 run_id：`RUN=<YYYYMMDD-HHMM>`，所有产物挂在这个 RUN 下。
每个阶段的完整参数与要点见 `references/scripts.md`。

| 档位 | 跑到哪 | 谁触发 |
|---|---|---|
| `--check`（默认，每日自动） | 阶段 1、2 + 10（全只读），出报告不写 | 可无人值守 |
| `--sync` | 加阶段 3–8（含写操作，需人确认） | 有差异时人工放行 |
| `--full` | 再加阶段 9（下游 L1→L2→L3） | 人工指定 |

### 阶段 1 记录层核对（只读）
```bash
python3 kb/l8/align_l0_feishu.py $RUN
```
读 `kb/l8/runs/$RUN-l0-align.json` 的 `summary`：`same / only_feishu / only_l0 / changed`
与 `record_files_not_registered_total`。

- `only_feishu`：漏抓。**但 `材料收集` 里审核状态 ≠「通过」的记录本就不入 L0，属预期，不算差异。**
- `only_l0`：飞书侧被删或被整批替换。`changed`：值变了。
- `record_files_not_registered_total > 0` → **必须进阶段 4**，否则下游永远抽不出来。
- 除预期的 `only_feishu` 外全为 0，才叫记录层对齐。

### 阶段 2 结构层核对（字段 id / 名 / 类型）
```bash
python3 kb/l8/align_l0_schema.py $RUN            # 预演
python3 kb/l8/align_l0_schema.py $RUN --apply    # 刷新 schema_snapshots
```
只比值不看字段集合，会漏掉**改名 / 改类型 / 增删字段**；下游 L1/L2 是按字段名取角色的。

### 阶段 3 认领与归档（写操作）
```bash
python3 kb/l8/reconcile_l0_feishu.py $RUN
```
判"表是否被重建"的正确方法：比 **field_id 集合**（一致 → 表没重建，是记录被换），
再抽查旧 `record_id` 是否返回 `Record not found` 作为第二证据。

### 阶段 4 台账补齐（append-only）
```bash
python3 kb/l8/emit_l0_manifest_reconcile.py $RUN           # 预演
python3 kb/l8/emit_l0_manifest_reconcile.py $RUN --apply
```
**最容易漏、也最贵**：记录文件在但 `manifest.jsonl` 没行 → 下游算「L0 活跃集 ⊖ L1」得 0 →
**这批新记录永远抽不出来**。sha256 口径必须与既有行一致：**先用一条既有行反向复现**再批量写。

### 阶段 5 非记录资源
```bash
python3 kb/l8/verify_l0_nonrecord.py  $RUN [--apply]
python3 kb/l8/verify_l0_nonrecord2.py $RUN [--apply]
python3 kb/l8/refresh_l0_drifted.py   $RUN [--apply]     # 漂移刷新进 L0（旧文件先归档）
python3 kb/l8/store_l0_attachments.py $RUN [--apply]     # 附件字节落 L0（bot 身份）
```
字节级比 `sha256(file_bytes)`；文档类比 **`rev` + 字节指纹**（摘要口径天然不同，别用摘要判等）。
标 `gone` 要**双证**：用户确认 + API 报文件不存在（如 `981003`）。
别把"存在但无权限"误标成 `gone`（曾经 11 条误标又改回 4 条）。
逐类出结论，按 §2 打印覆盖率矩阵。

### 阶段 6 图片 OCR
```bash
python3 kb/l8/ocr_attachments.py $RUN                    # 下载 → Vision OCR → 抽文案 → 删图
python3 kb/l8/apply_ocr_to_l1.py <OCR_RUN> <L1_RUN> [--apply]
```
缓存闸门 `vision-jxa-2.0`：**新旧图 file_token 交集为 0 时缓存不可复用**，别套旧缓存。

### 阶段 7 视频
先做字段级非空筛选、留证（飞书侧可能根本没有视频素材）。
有 → 下载字节 → 提字幕 + 抽关键帧 → 关键帧走 OCR → 文本落 **L1**。
取不到字节时按 §3.2 第 3 步区分 `no_scope` 与 `blocked_by_library_setting`。

### 阶段 8 链接：下钻两层 + 外链比对
```bash
python3 kb/l8/drill_links_2levels.py $RUN
python3 kb/l8/fill_drill_failures.py $RUN [--apply]
python3 kb/l8/verify_l0_urls.py       $RUN
python3 kb/l8/verify_urls_headless.py $RUN
python3 kb/l8/verify_urls_shingles.py $RUN                        # 词 8-gram 双向重叠判等
python3 kb/l8/recrawl_all_urls.py     $RUN [--apply] [--limit N]  # 统一口径重抓
python3 kb/l8/recrawl_jsnoise_urls.py $RUN [--apply]              # 抓到 JS 噪声的
```
- **混口径 = 没对齐**：同一层 `sha256_input` 口径必须统一（如全 `url_text_rendered_v1`）。
  三种口径混在一个字段里时，必须明说"**不能算严格一致**"。
- 判等用**词 8-gram 双向重叠**，不要整行逐字比。
- 飞书域名链接**走 API，不裸 HTTP**。反爬页先加渲染预算（TikTok ~20s），再考虑换 UA / 降级取文本。
- 源侧真失效（404 / 403 / 域名挂）单列，不混进"内容变了"。

### 阶段 9 下游重跑（**不动 L0**）
```bash
python3 kb/l8/extract_l1_new_resources.py $RUN [--apply]
python3 kb/l8/l2_split_run.py $RUN
python3 kb/l8/l3_distill_run.py <L3_RUN>
python3 kb/l8/l3_reject_ledger_rebuild.py <L3_RUN> [--apply]
```
> ⚠️ `l3_distill_run.py` 会以 `w` 模式覆盖 `rejected.jsonl`。跑前先归档现状，
> 跑后必须按既有口径把**逐单元**拒绝台账重建回来（否则重演 11,860 → 1,053 行回归，真实发生过）。

### 阶段 10 收口核验
```bash
python3 kb/l8/workflow_check.py $RUN
python3 kb/l8/roundtrip_check.py $RUN
python3 kb/l8/projection_reconcile.py    # kb/view 投影 vs 权威库漂移
python3 kb/l8/envelope_census.py         # 活路径不该有信封
python3 kb/l8/build_view.py --run $RUN   # 需刷新工作台投影时才做
```
外加强制项：§2 覆盖率自检（`S_feishu ⊆ S_report`），缺类不许收口。

## 5. 交付物

1. `kb/l8/runs/<RUN>-*.json`：各阶段运行记录（存原始数据，不转述）。
2. **一段结论，固定四段**：① 记录层四类计数 ② 结构层（改名/缺字段/类型漂移）
   ③ 非记录层按矩阵**逐类出结论**（四态之一，读不到/不可核的逐条列原因码）
   ④ 口径层：URL 是否统一口径，不统一就明说"不能算严格一致"。
3. **覆盖率矩阵**：每类一行 = 类型 + 状态 + 条数 + 原因码。
4. `_archive/` 归档记录 + manifest（有写操作时）。
5. **缺口清单**：对象 + 原因码 + **要人做什么**（如"把守衡加成可阅读协作者"）+ 复开条件。

## 6. 何时停下来问人

- 阶段 0 自检不过（凭据 / 库根 / 锁）→ 报"缺什么"，不绕路硬试。
- 存在 `.kb.lock`，或 `kb/.work` 近 30 分钟有大量写入 → **可能有另一批在跑**，先确认再动。
- 出现 `only_l0` / `changed` 且原因不明 → **先只读取证，不要先写**。
- 权限类硬缺口（库级禁止下载、所有者不给）→ 标原因收口，**不重试**。

## 7. 每次结束前

- 留一句"L0 本次有没有被改过"的弱证据（`manifest.jsonl` 行数 + 目录 mtime），
  没有版本控制就如实说这是弱证据。
- 报告必须区分「**库的问题**」和「**我的工具/脚本的问题**」。
  同一天两次事故都是后者（核验脚本把 `record_id` 当字段比、把 wiki token 当 base token），
  **不许把工具 bug 报成数据缺陷**。更多坑见 `references/gotchas.md`。
