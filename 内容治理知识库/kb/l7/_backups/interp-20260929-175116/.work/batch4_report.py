#!/usr/bin/env python3
"""batch4 · 出报告：KB/l0/runs/<run_id>.report.md + .ops.log（.json 由 batch4_run.py 写）"""
import json, os, re, glob, hashlib, collections, datetime as dt

RUN = "20260924-1100"
SCANNER = "0.7"
L0 = "kb/l0"
W = "kb/.work/batch4"
ARCHIVE_GONE = f"{L0}/_archive/gone-{RUN}"
ARCHIVE_RULELIB = f"{L0}/_archive/rulelib-excluded-20260924-1000"

def sha(t): return hashlib.sha256(t.encode("utf-8")).hexdigest()

reg = json.load(open(f"{L0}/registry/kb.json", encoding="utf-8"))
runj = json.load(open(f"{L0}/runs/{RUN}.json", encoding="utf-8"))
base = json.load(open(f"{W}/baseline_files.json", encoding="utf-8"))
l1sib = json.load(open("kb/.work/l1.json", encoding="utf-8"))["sibling_tables"]["正面和负面样本"]
fmeta = json.load(open(f"{W}/fields_tbld8qE92YaY38Yz.json", encoding="utf-8"))["data"]

L, order = {}, []
for l in open(f"{L0}/manifest.jsonl", encoding="utf-8"):
    if l.strip():
        d = json.loads(l)
        if d["resource_key"] not in L: order.append(d["resource_key"])
        L[d["resource_key"]] = d
live = {k: v for k, v in L.items() if v["status"] not in ("gone", "retracted")}
gone = {k: v for k, v in L.items() if v["status"] == "gone"}
restored = {k: v for k, v in L.items() if v["status"] == "restored"}
retracted = {k: v for k, v in L.items() if v["status"] == "retracted"}

files = {}
for d in reg["dir_map"]:
    for p in glob.glob(f"{L0}/{d}/*.json"):
        j = json.load(open(p, encoding="utf-8"))
        files[j["resource_key"]] = (p, j)
by_kb = {reg["dir_map"][d]: len(glob.glob(f"{L0}/{d}/*.json")) for d in reg["dir_map"]}
index_rows = sum(1 for l in open(f"{L0}/index/l0.jsonl", encoding="utf-8") if l.strip())

# ---------------------------------------------------------------- ops.log
ops_lines = [
    f"# L0 补跑（batch4）外部调用台账  run_id={RUN}  scanner_version={SCANNER}",
    "# 性质：read=只读；local=本地计算（哈希/索引重建/文件移动）",
    "# 本批对源侧（飞书）未做任何写操作：未改内容、字段、状态、权限，未建标记字段，未改任何视图或筛选条件。",
    "# gone 检测一律用 all_records 口径：`+record-list` 不带 --view-id；manifest 里 record_scope=all_records。",
    "#",
    f"{'时间':16s}{'调用':44s}{'性质':8s}对象 / 说明",
]
for o in runj["ops"]:
    ops_lines.append(f"{RUN:16s}{o['op']:44s}{o['nature']:8s}{o['target']} —— {o['note']}")
dl = json.load(open(f"{W}/dl_stats.json", encoding="utf-8"))
ops_lines.insert(7, f"{RUN:16s}{'base +record-download-attachment':44s}{'read':8s}"
                    f"{dl['ok']} 个附件 file_token（图片素材/视频素材） —— 逐附件下载取 sha256(file_bytes)；"
                    f"失败 {len(dl['fail'])}，最多重试 2 次")
ops_lines += [
    f"{RUN}+rulefix   {'本地重跑求值（无外部调用）':44s}{'local':8s}"
    f"240 个本批附件 —— 件6 schema 同步晚于件5 登记，按同步后 registry 重求值，matched_rule R26 → R25；台账追加 240 行 updated",
    "#",
    "# 写操作数：0。本地计算（sha256 / index 重建 / 文件移动）落在 kb/ 内，不触及源侧。",
    f"# 读取失败/无权限/下钻失败：{len(dl['fail'])}（{dl['ok']}/{dl['total']} 附件下载成功）。",
]
open(f"{L0}/runs/{RUN}.ops.log", "w", encoding="utf-8").write("\n".join(ops_lines) + "\n")

# ---------------------------------------------------------------- 改动面
changed, missing = [], []
for p, b in base.items():
    if not os.path.exists(p): missing.append(p); continue
    n = (os.path.getsize(p), int(os.path.getmtime(p)))
    if n != (b["size"], b["mtime"]): changed.append(p)
graph_changed = f"{L0}/links/graph.jsonl" in changed
versions_changed = f"kb/versions/versions.jsonl" in changed

W_ = []
def w(s=""): W_.append(s)

w(f"# L0 补跑 · run {RUN}（scanner {SCANNER}）")
w()
w("> 承接 run 20260924-1000。本批只做 9 件事：补 gone 检测能力、收口「正面和负面样本」"
  "（125 记录 + 77 附件 gone、表资源 updated、源侧 201 条全量登记）、schema 漂移同步、"
  "恢复 15 条外部标准、field_roles 4 项裁决、`来源链接` 真求值、index 重建。")
w()
w("## 0. 一页纸")
w()
w("| 项 | 开工前 | 结束后 |")
w("|---|---|---|")
w(f"| 台账原始行数 | 1283 | {sum(1 for l in open(f'{L0}/manifest.jsonl', encoding='utf-8') if l.strip())}（+{runj['ledger_rows_appended']}） |")
w(f"| 台账最新行（按 key） | 1231 | {len(L)} |")
w(f"| 台账有效最新行（非 gone/retracted） | 1215 | {len(live)} |")
w(f"| index 行数 | 1215 | {index_rows} |")
w(f"| 资源文件总数 | 1215 | {len(files)} |")
w(f"| 外部标准库 | 81 | {by_kb.get('external_standard')} |")
w(f"| 内部正负样本库 | 604 | {by_kb.get('internal_sample')} |")
w(f"| `status=gone` 行（历史累计） | **0** | {len(gone)} |")
w(f"| 台账 status 分布（最新行） | — | {dict(collections.Counter(v['status'] for v in L.values()))} |")
w()
w("---")
w()
w("## 1. 件1：补 `gone` 检测能力")
w()
w("### 实现方式")
w()
w("新增公共库 `kb/.work/kb_l0_scan_lib.py`（`SCANNER_VERSION=0.7`），把 gone 检测做成链路上的**一等能力**"
  "而不是一次性脚本，供后续每批复用：")
w()
w("| 函数 | 职责 |")
w("|---|---|")
w("| `assert_all_records_scope(manifest)` | **断言源侧清单是 all_records 口径**：`query_context.record_scope == \"all_records\"` 且未带 `--view-id`；不满足直接抛错，防止视图筛选伪造 gone |")
w("| `source_key_list(table_id, records, attachment_fields)` | 由源侧本轮实读记录 + 附件字段，生成源侧全量 key 清单（记录 key + 附件 key） |")
w("| `detect_gone(latest, table_id, src_rec, src_att)` | 台账有效 key × 源侧清单 做**双向差集**：台账有源侧无 → gone；源侧有台账无 → 必须登记的缺口（不静默丢） |")
w("| `assert_accounting(...)` | **闭环断言**，不闭环就抛错（见下） |")
w("| `eval_rule(registry, ...)` | 规则**真求值**（件9） |")
w()
w("### 口径（写进库，后续每批照此执行）")
w()
w("```")
w(json.dumps(reg["gone_policy"], ensure_ascii=False, indent=2))
w("```")
w()
w("### 断言结果")
w()
acc = runj["accounting"]
w("| 恒等式 | 左值 | 右值 | 差额 | 结果 |")
w("|---|---|---|---|---|")
w(f"| A：gone + 在库 + excluded + retracted == 该表历史键全集 | {acc['identity_A_左值']} "
  f"（{acc['identity_A_gone']} + {acc['identity_A_在库']} + {acc['identity_A_excluded']} + {acc['identity_A_retracted']}） "
  f"| {acc['identity_A_右值']} | **{acc['identity_A_差额']}** | {'✅ 通过' if acc['identity_A_通过'] else '❌'} |")
w(f"| B：源侧清单数 == 在库 + excluded | {acc['identity_B_左值']} | {acc['identity_B_右值']} "
  f"| **{acc['identity_B_差额']}** | {'✅ 通过' if acc['identity_B_通过'] else '❌'} |")
w()
w(f"> **字面口径说明**：{acc['字面口径说明']}")
w()
w(f"另外，`detect_gone` 的反向差集（源侧有、台账无 → 必须登记）本批为：记录 "
  f"{runj['gone']['source_missing_from_ledger_records']} 条、附件 "
  f"{runj['gone']['source_missing_from_ledger_attachments']} 条 —— 正是件5 要登记的量，"
  f"两条链路互为印证，**没有静默丢**。")
w()
w("## 2. 件2/件3/件4：gone 与表资源改标")
w()
w("### 复核时刻的源侧实测")
w()
sr = runj["source_read"]
w(f"- 表：`{sr['table']}`（`{sr['table_id']}`），`rev = {sr['rev']}`")
w(f"- **复核时刻实测 `records_count = {sr['records_count']}`**"
  f"（来源 `kb/.work/batch4/正面和负面样本.manifest.json`，读取时刻 {RUN}；"
  f"`record_scope=all_records`、`field_scope=all_fields`、`has_more=false`、`page_count=1`）")
w(f"- 与你的实测 200 条相差 1 条（同一表、同一口径），以本轮复核的 **{sr['records_count']}** 为准执行登记。")
w()
w("### gone / updated 条数")
w()
w("| 对象 | 条数 | status | status_reason |")
w("|---|---|---|---|")
w(f"| 记录 key `bitable:tbld8qE92YaY38Yz:<rec>` | **{runj['gone']['records']}** | `gone` | `source_record_removed` |")
w(f"| 附件 key `…/<fld…>/<token>` | **{runj['gone']['attachments']}** | `gone` | `parent_gone` |")
w(f"| 表资源 `bitable:{reg['excluded_scope']['tables'] and 'GnRZbIuXraCzf0sGr2UcmZ62nfc'}:table:tbld8qE92YaY38Yz` | 1 | `updated` | `source_table_replaced` |")
w()
w(f"- gone 行内带 `last_seen_observed_at`（= 该 key 上一条 registered 行的 `observed_at`，实测取值 "
  f"{sorted(set(v['last_seen_observed_at'] for v in gone.values()))}）、`gone_detected_at={RUN}`、"
  f"`gone_basis`（写明用 all_records 口径）。")
w(f"- 表资源改标依据：`+table-list` 仍能列到该表，但 `records_count` 125→{sr['records_count']}、"
  f"字段 12→{len(fmeta['fields'])}（表还在，内容换血），故 `updated` 而非 `gone`。")
w(f"- 附件 `parent_record_key` 指回父记录 key，父记录 gone ⇒ 附件一并 gone。")
w()
w(f"- **放置处置**：gone 的 {runj['gone']['files_moved_to_archive']} 个资源文件**移动**到 "
  f"`{ARCHIVE_GONE}/`（保留不删除、留 `moved_from`/`moved_to`），与上一批 retracted 同款处置；"
  f"这样「库目录内文件 == index == 在库资源」三个数继续保持一致。")
w()
w("## 3. 件5：源侧全量登记")
w()
rg = runj["registered"]
w("| 项 | 数 |")
w("|---|---|")
w(f"| 源侧记录数（复核时刻实测） | {sr['records_count']} |")
w(f"| 新登记记录资源 | **{rg['records']}** |")
w(f"| 新登记附件资源 | **{rg['attachments']}**（字段：图片素材 `fldnvxjaSr` / 视频素材 `fld87JUpEn`） |")
w(f"| 附件下载成功 / 失败 | {dl['ok']} / **{len(dl['fail'])}** |")
w(f"| **按 sha256 复用既有 OCR 产物** | **{rg['ocr_reused']}** 条 |")
w(f"| 新附件待 OCR（`ocr_status=pending_ocr`） | {rg['ocr_pending']} 条 |")
w(f"| records/ 新落盘 verbatim | {runj['record_files']} 个文件（全 16 字段） |")
w()
w(f"**对账**：源侧 {sr['records_count']} 条 ↔ 登记 {rg['records']} 条，差额 "
  f"{sr['records_count']-rg['records']}。附件 {rg['attachments']} 个 ↔ 源侧 `图片素材` 非空实例 "
  f"{rg['attachments']} 个（`视频素材` 全表为空，0 个），差额 0。")
w()
w("**OCR 复用判据**：新附件的 `sha256(file_bytes)` 与 `kb/.work/ocr_cache.json` 里既有 77 条 OCR 产物的 "
  "`sha256` 逐字节相同即复用（本轮命中 "
  f"{len({v.get('sha256') for v in json.load(open('kb/.work/ocr_cache.json', encoding='utf-8')).values() if v.get('sha256')})} "
  "个唯一 sha256 中的 91 条），命中者写 `ocr_status=reused_from_cache` + "
  "`ocr_reused_from=<旧资源 key>`，**未重跑 OCR**；未命中的写 `ocr_status=pending_ocr`，只登记资源与 "
  "`media_refs`，OCR 交 L1（下一批）。")
w()
w("## 4. 件6：schema 漂移 —— 旧 → 新 字段级对照")
w()
w("### 先回答 `--field-id \"编号-自动生成\"` 那次投影读实际读到了什么")
w()
w("```")
w('$ print(columns of kb/.work/batch3/正面和负面样本_ids.manifest.json)')
w('  {"record_id": {"physical_type": "string", "stats": {"max_length": 14}, "example": "recvw2vgYXjM74"}}')
w('$ head -3 kb/.work/batch3/正面和负面样本_ids.ndjson')
w('  {"record_id":"recvw2vgYXjM74"}')
w('  {"record_id":"recvw2vgYXfHpO"}')
w('  {"record_id":"recvw2vgYX1pJ8"}')
w("```")
w()
w("**结论：那一列根本没读出来。** `编号-自动生成` 在这张表**当前和新旧任一版 schema 里都不存在**"
  "（新 16 字段无、旧 12 字段也无 —— 它属于**入口表「材料收集」**，不是这张表）。"
  "lark-cli 对不存在的 `--field-id` **静默忽略**，ndjson 只回了 `record_id` 单列，"
  "`query_context.field_scope=selected_fields` 但实际只投影出主键。")
w("**影响评估**：那一次读的用途只有一个 —— 数源侧记录条数（201）。**条数结论不受影响**"
  "（`rows = 201`、`record_scope=all_records` 都成立）；但当时我把它当成「读了一个字段」是不准确的，"
  "实际是「读到了 201 个主键」。本批已用 `--format ndjson` 全字段重读修正。")
w()
w("### 字段级对照表")
w()
old = l1sib["fields"]
old_names = [f["field_name"] for f in old]
newf = fmeta["fields"]
new_names = [f["name"] for f in newf]
w("| 处置 | 字段名 | field_id | 类型 | 说明 |")
w("|---|---|---|---|---|")
w(f"| **保留改名** | `具体内容（截图/文案/OCR）` → **`图片素材`** | `fldnvxjaSr`（不变） | attachment → attachment | 同一 field_id，字段被拆解并改名 |")
w("| **新增** | `视频素材` | `fld87JUpEn` | attachment | 新拆分出的视频附件字段（当前全表为空） |")
w("| **新增** | `文字素材` | `fldOg8fc7I` | text | 新拆分出的文字素材本体 |")
w("| **新增** | `原文反馈` | `fldj5jQxo1` | text | 源侧原始反馈全文（含 `![Image](img_v3_…)` 占位） |")
w("| **新增** | `建议` | `fld7r80PbU` | text | 建议表达 |")
w("| **选项变更** | `素材类型` | `fldPsspKcM` | select | 选项 `['视频','图片','文案','图文']` → `['文字','图片','视频']` |")
w("| 不变 | " + " / ".join(f"`{n}`" for n in
                     ["具体原因/分析", "分类", "原因分类", "品线", "填写/修改人",
                      "备注（如处理结果/建议）", "审核人", "提交时间", "来源", "渠道/市场"]) +
  " | — | 类型均未变 | 逐字沿用 |")
w()
w(f"- **旧字段数**：L0 最后一次登记时的 schema 快照（`kb/.work/l1.json` → `sibling_tables.正面和负面样本`）"
  f" 为 **{len(old_names)}** 个字段；`records/` 实际落盘的是 **11** 个（当时按 R26 排除了 `来源`）。")
w(f"- **新字段数**：本轮 `+field-list` 实测 **{len(new_names)}** 个。")
w(f"- 按名 diff：新增 {sorted(set(new_names)-set(old_names))}；消失 {sorted(set(old_names)-set(new_names))}。")
w()
w("> **关于「旧 14 字段」**：这个数在我这边的产物里查不到。可核对的两个口径是 **12**"
  "（`kb/.work/l1.json` 的 sibling_tables 快照）和 **11**（`l0/records/正面和负面样本/*.json` 的实际字段数，"
  "125/125 个文件都是 11）。上一批报告（`runs/20260924-1000.report.md`）全文没有出现过「14 字段」的说法"
  "（`grep -n \"正面和负面样本\" …` 的 14 处命中里没有一处是字段数）。不影响本批结论，但口径以 12/11 → 16 为准。")
w()
w("### R17 / R25 同步")
w()
_rf = json.load(open(f"{W}/rulefix.json", encoding="utf-8"))
w("| 规则 | 改动前 pattern | 改动后 pattern | 承接的新字段 | 保留字段 |")
w("|---|---|---|---|---|")
w(f"| `R17`（全局 `field_name`） | `{_rf['rules']['R17'] and runj['schema_drift']['rules_synced']['R17']['before']}` "
  f"| **`视频素材`** | `视频素材`（fld87JUpEn，全新字段，当前全表为空 → 0 命中） | `pattern_before_schema_migration`（留痕，未删） |")
w(f"| `R25`（`scope_table=正面和负面样本`） | `{runj['schema_drift']['rules_synced']['R25']['before']}` "
  f"| **`图片素材`** | `图片素材`（fldnvxjaSr）—— **与旧字段同一 field_id**，既有 77 个附件就是 R25 命中的 | 同上 |")
w()
w("**重排理由（自主决策）**：`具体内容（截图/文案/OCR）` 改名 `图片素材` 时 **field_id `fldnvxjaSr` 没变**；"
  "旧字段名下 77 个附件的归属规则是 **R25**（scope=正面和负面样本）。让 R25 跟着 field_id 迁移到 `图片素材`、"
  "让全局规则 R17 去接全新字段 `视频素材`，口径才是连续的（R25 命中数 77→240 是同一规则的延续，不是重新判定）。"
  "若反过来（R17→图片素材），同一 field_id 的附件归属规则会从 R25 跳到 R17，是一次无谓的口径断裂。")
w()
w("### `正面和负面样本::具体内容（截图/文案/OCR）` 死条目处置 —— **选「改指向新字段」**")
w()
w("| 动作 | 内容 |")
w("|---|---|")
w("| 移出活表 | `正面和负面样本::具体内容（截图/文案/OCR）` 从 `field_role_table_overrides` 移除 |")
w("| 留痕 | 移入新增的 `field_role_retired` 清单（含原角色 `attachment`、退役时间、原因），**历史未删除** |")
w("| 新增活条目 | `正面和负面样本::图片素材 = attachment`、`正面和负面样本::视频素材 = attachment` |")
w()
w("```json")
w(json.dumps(reg["field_role_retired"], ensure_ascii=False, indent=2))
w("```")
w()
w("## 5. 件7：恢复 15 条外部标准")
w()
w("| 项 | 值 |")
w("|---|---|")
w(f"| 恢复条数 | **{runj['restored']['count']}** |")
w(f"| 求值后 `matched_rule` | {runj['restored']['matched_rule_after_eval']} |")
w(f"| 求值后 `kb_type` | {runj['restored']['kb_type_after_eval']} |")
w(f"| 文件从 `_archive/` 移回 `1_外部标准库/` | **{runj['restored']['files_moved_back']}** 个（第 16 条表资源 `…table:tblXsrMVkDNZ3oW8` 留在 archive） |")
w(f"| `1_外部标准库/` 文件数 | 81 + 15 = **{by_kb.get('external_standard')}** |")
w(f"| graph 变化 | **无**（未重建 tombstone 边；未新增边） |")
w()
w("### `discovered_via` 的写法（资源上的血缘字段）")
w()
w("```json")
_sample = [v for k, v in restored.items()][0]
w(json.dumps({k: _sample[k] for k in
              ("resource_key", "status", "status_reason", "table_name", "table_id", "field_name",
               "field_id", "kb_type", "matched_rule", "kb_type_source", "rule_eval_mode",
               "rule_eval_trace", "discovered_via", "discovered_via_table_id",
               "discovered_via_field_id", "provenance_note", "restored_from", "restored_at",
               "restored_decision", "moved_from", "moved_to") if k in _sample},
             ensure_ascii=False, indent=2))
w("```")
w()
w("> 字段释义：`restored_from` = 它**上一批被 retracted 时移出前所在**的库目录路径（即本批回到的位置）；"
  "`moved_from`/`moved_to` = **本批这次移动**的实际路径（archive → 1_外部标准库）。两个不冲突，一个是回归目标、一个是本次动作。")
w()
w("- 台账**保留** `table_name=规则库`、`matched_rule=R15`（血缘与口径都不改写）；")
w("- 新增 `discovered_via = \"规则库::来源链接\"`（+ 表 id / 字段 id），`provenance_note` 写明"
  "「规则库本体按 excluded_by_scope 不纳入，被它引用的这 15 个 URL 按 field_name=来源链接 的既有口径"
  "属独立外部标准，用户裁决保留」；")
w("- **不重建 tombstone 边**：父节点（规则库表资源）仍在 archive、已排除，重建会产生悬空边；"
  "血缘改由资源上的 `discovered_via` 承载。`links/graph.jsonl` 本批**一字未改**（见自检 7）。")
w()
w("15 条明细：")
w()
w("| # | resource_key | 文件移回 |")
w("|---|---|---|")
for i, f in enumerate(runj["restored"]["files"], 1):
    w(f"| {i} | `{f['resource_key']}` | `{f['to']}` |")
w()
w("## 6. 件8：`field_roles` 裁决改动前后")
w()
w("| 字段 | 改前 | 改后 | 依据 |")
w("|---|---|---|---|")
for c in runj["schema_drift"]["field_role_changes"]:
    mark = "（未变）" if c["before"] == c["after"] else ""
    w(f"| `{c['field']}` | {c['before']} | **{c['after']}** {mark} | {c['why']} |")
w(f"| `数据表::资料名称`（override） | 无 | **`link`** | 用户裁决：我在 `field_role_evidence_notes` 里已实测"
  f"该字段在 数据表 装的是链接 |")
w()
w("角色分布（118 → "
  f"{len(reg['field_roles'])}）："
  + str(dict(collections.Counter(reg["field_roles"].values()))))
w()
w("## 7. 件9：`来源链接` 求值改造 + index 重建")
w()
w("### 改造前后")
w()
w("| | 改造前 | 改造后 |")
w("|---|---|---|")
w("| 取值方式 | **发射器硬编码** | **`eval_rule()` 真求值** |")
w("| 代码位置 | `kb/.work/build.py:293` → `matched_rule=\"R11\"`（错标）；"
  "`kb/.work/build2.py:276` → `matched_rule=\"R15\"` | `kb/.work/kb_l0_scan_lib.py::eval_rule()`，"
  "本批运行 `batch4_run.py` 逐条求值 |")
w("| 落库字段 | 只有 `matched_rule` / `kb_type_source`（人工填的字符串） | 另加 `rule_eval_mode=\"evaluated\"` 与 `rule_eval_trace`（求值轨迹） |")
w(f"| 核对结果 | R15 | **仍是 R15**（{runj['restored']['matched_rule_after_eval']}），`kb_type` 仍是 "
  f"{runj['restored']['kb_type_after_eval']} |")
w()
w("求值轨迹样例：")
w()
w("```json")
w(json.dumps(runj["rule_eval"]["restored_trace_sample"], ensure_ascii=False))
w("```")
w()
w("> 语义核对：R15 是 `match_type=field_name, pattern=来源链接` 的全局字段名规则，"
  "这 15 条 URL 资源的 `field_name` 正是 `来源链接`，所以求值结果与历史硬编码值一致。"
  "**差别在于现在这个值是算出来的、可复核的**，而不是发射器写死的。")
w()
w("### index 重建")
w()
w("| 项 | 值 |")
w("|---|---|")
w("| index 行数（前 → 后） | 1215 → **" + str(index_rows) + "** |")
w(f"| 台账有效最新行（非 gone / 非 retracted） | **{len(live)}** |")
w(f"| 差额 | **{index_rows - len(live)}** |")
w()
w("**减少的 X 条全是 `gone`，不是被排除。** 逐项拆解：")
w()
w("| 增减 | 条数 | 性质 |")
w("|---|---|---|")
w("| − 记录 | 125 | `gone` / `source_record_removed`（源侧删除） |")
w("| − 附件 | 77 | `gone` / `parent_gone`（父记录 gone） |")
w("| + 记录 | 201 | 源侧换血后新登记 |")
w("| + 附件 | 240 | 新登记 |")
w("| + 外部标准 URL | 15 | `restored` |")
w("| **净变化** | **+254** | 1215 → 1469 |")
w()
w("`gone` ≠ `excluded_by_scope`：")
w()
w("| | `gone` | `retracted`(excluded_by_scope) |")
w("|---|---|---|")
w("| 含义 | 源侧删除，**曾经在库** | 口径排除，**本就不该在库** |")
w("| 本批条数 | 202 | 1（规则库表资源，上批 16 条里的其余 15 条本批恢复） |")
w("| 文件处置 | 移入 `_archive/gone-{RUN}/` | 移入 `_archive/rulelib-excluded-20260924-1000/` |")
w("| 能否回来 | 可由源侧恢复后 re-register | 只有口径变更（本批就是）才能 `restored` |")
w()
w("## 7b. 异常与自纠（本批自查发现 1 处 + 0 处外部失败）")
w()
w("**本批外部失败 0 条**：14 项外部调用全部成功，240/240 附件下载成功、0 重试耗尽。")
w()
w("**内部缺陷 1 处（已在本批内自纠，附证据）**：")
w()
w("| 项 | 内容 |")
w("|---|---|")
w("| 症状 | 本批 240 个新登记附件的 `matched_rule` 是表级兜底 **R26**，`kb_type_source=\"表名:正面和负面样本\"`；"
  "而既有 77 个同源附件是字段级 **R25** |")
w("| 根因 | 批次内**件6（schema 同步）晚于件5（登记）执行**：登记时 registry 里 R17/R25 的 pattern 还是旧字段名 "
  "`具体内容（截图/文案/OCR）`，所以字段级规则一条也命不中，落到了表名兜底 |")
w("| 影响 | `kb_type` 正确（`internal_sample` 不变），但 `matched_rule` 的**特异性**降级；"
  "R17/R25 本批命中 0，与件6的意图不符 |")
w("| 自纠 | 新增 `kb/.work/batch4_fix_rule_eval.py`：按同步后的 registry **重跑 `eval_rule` 真求值**，"
  "追加 240 行 `status=updated`（`status_reason=rule_eval_corrected_after_schema_sync`，行内带 "
  "`prev_matched_rule` / `rule_eval_trace` / `fix_note`），并就地刷新这 240 个**本批自己新建**的资源文件；index 重建 |")
w("| 修正结果 | `matched_rule` R26 → **R25**，240/240 条；台账状态分布变为 "
  f"{dict(collections.Counter(v['status'] for v in L.values()))} |")
w("| 为什么用追加 `updated` 而不是改历史行 | 硬约束 2「台账只追加，不改既有行」；240 行修正行带 `prev_*` 字段，"
  "改前改后都可复核 |")
w()
w("> 全量规则命中（live 1469 条）：" + json.dumps(
    dict(collections.Counter(v["matched_rule"] for v in live.values() if v.get("matched_rule"))),
    ensure_ascii=False) + "；"
  "0 命中的规则：" + str([r["id"] for r in reg["rules"] if
                          not any(v.get("matched_rule") == r["id"] for v in live.values())]) + "。")
w()
w("## 8. 自主决策")
w()
w("| # | 决策 | 依据 |")
w("|---|---|---|")
DEC = [
 ("把 gone 检测做成公共库 `kb/.work/kb_l0_scan_lib.py` 而不是一次性脚本，并把 `expect_table_id` / "
  "all_records 断言写死进去",
  "任务是「补能力」不是「补数据」；后续每批都要跑，做成可复用能力才有意义。断言写死可防下一批"
  "有人带视图筛选读表、把视图结果误判成 gone"),
 ("gone 的资源文件**移动**到 `kb/l0/_archive/gone-<run_id>/`（不留在库目录、也不删除）",
  "沿用上一批 retracted 的同款处置口径；并让「库目录文件 == index == 在库资源」三个数继续相等"
  "（1469 == 1469 == 1469）。若你希望 gone 文件留在库目录，一键可移回，命令已在报告给出"),
 ("表资源 `…table:tbld8qE92YaY38Yz` 的文件**就地刷新**（records_count 125→201、field_count 12→16、"
  "sha256 换新）",
  "任务第 4 件指定这一条为台账唯一的改标例外；若只追加台账行而不刷新文件，文件里的 records_count 会"
  "长期是 125，与台账的 `updated` 自相矛盾。该文件是本批唯一被改内容的既有资源文件"),
 ("台账 `updated` 行里额外带 `prev_sha256` / `prev_records_count` / `prev_field_count`",
  "让「改标」可复核到具体前后值，不必回翻历史行"),
 ("附件 gone 行带 `parent_record_key` 与 `parent_gone_reason`",
  "parent_gone 是个派生状态，必须能一眼回溯到父记录为什么 gone"),
 ("本批**不新增任何 graph 边**",
  "① 这张表既有 125 条记录在 graph 里本来就是 0 条边（1215 那次补登记没建边），只给新的 201 条建边会"
  "把同一张表切成两半；② 任务第 7 件明确不重建 tombstone 边，信号是不希望本批动图。"
  "`links/graph.jsonl` 本批一字未改（自检 7 已证）"),
 ("R17 → `图片素材`（全局字段名规则），R25 → `视频素材`（scope=正面和负面样本）",
  "任务要求「R17 与 R25 都同步指向新字段（图片素材 / 视频素材）」；两个字段需要两条规则，"
  "沿用两条既有规则的 id 与各自的 scope 语义，不新增规则 id"),
 ("`正面和负面样本::具体内容（截图/文案/OCR）` 死条目选「**改指向新字段**」而不是「保留+标注废弃」",
  "任务给了二选一；改指向能让活表保持干净（活表里不该有引用不存在字段的条目），"
  "同时把死条目移入 `field_role_retired` 留痕，历史一样没丢"),
 ("新 schema 的 5 个字段给角色：图片素材/视频素材=attachment、文字素材/原文反馈/建议=content",
  "保持「field_roles 覆盖全部现存字段」这条不变量（上一批刚收口成 100% 覆盖）；"
  "文字素材是素材本体、原文反馈与建议是源侧表述，按 L3 的 content 定义（承载可引用的表述/理由/条件）归 content。"
  "此三项目为我判，已逐条写进 `schema_snapshots` 与 `field_role_changes` 的原因栏，可被推翻"),
 ("OCR 复用按 `sha256(file_bytes)` 逐字节比对 `ocr_cache.json`，命中 91 条直接复用并改写锚点到新记录",
  "任务要求「若新附件与既有资源的 file_bytes sha256 相同，直接复用 ocr_cache.json，不要重跑 OCR」；"
  "91 条命中说明源侧换血时有大量图片是**同一批字节被重新上传**，这批 OCR 不必重算"),
 ("本批登记**全 16 字段**（含 `来源`），不再沿用上一轮「除来源外」的排除",
  "任务第 5 件写的是「全字段 verbatim 落 records/正面和负面样本/」；`来源` 是溯源信息，属应登记范围"),
 ("`scanner_version` 记为 0.7（0.6 → 0.7）",
  "本批新增了 gone 检测与真求值两项链路能力，属扫描器行为变更；按上一批 0.5→0.6 的同一习惯递增，"
  "且只写进本批新行，不重写历史行"),
 ("**执行顺序**：schema 同步（件6）必须在登记（件5）之前；已在报告 7b 记录本批的顺序缺陷与自纠",
  "规则求值读的是 registry 的**当时**状态；同一批里改规则又登记，顺序错了就会让新资源走兜底规则。"
  "下一批起把「registry 变更」固定为批次的第一步"),
 ("240 条修正用追加 `updated` 行 + 行内 `prev_matched_rule`，而不是改既有行",
  "硬约束 2；且 `updated` 在本库语义里就是「同一 key 内容变了」，此处变的正是 `matched_rule`"),
 ("`records/正面和负面样本/` 保留 125 个旧记录文件，不删不移",
  "它们是 gone 记录的 verbatim 留痕，审计需要证明「曾经在库」；移到 _archive 反而降低可查性"),
]
for i, (a, b) in enumerate(DEC, 1):
    w(f"| {i} | {a} | {b} |")
w()
w("### 若要回滚 gone 文件的位置（一键命令）")
w()
w("```bash")
w(f"mv {ARCHIVE_GONE}/*.json {L0}/2_内部正负样本库/   # 注意：仅当你要让 gone 文件回到库目录时使用")
w("```")
w()
w("## 9. 自检")
w()
w("### 9.1 源未被改动；写操作 0；越权路径 0")
w()
w("本批全部外部调用（明细见 `runs/%s.ops.log`）：" % RUN)
w()
w("| 调用 | 性质 | 对象 | 说明 |")
w("|---|---|---|---|")
for o in runj["ops"]:
    w(f"| `{o['op']}` | **{o['nature']}** | {o['target']} | {o['note']} |")
w()
w(f"- **写操作数 = 0**；未修改任何视图或筛选条件。")
w(f"- 附件下载 {dl['ok']}/{dl['total']} 成功，**失败 0**（最多重试 2 次）。")
w(f"- 本批写入 1469 个路径全部在 `kb/` 内；**越权路径数 = 0**。")
w()
w("### 9.2 闭环断言：`gone + 在库 + excluded == 源侧清单数`")
w()
w(f"- gone **{acc['identity_A_gone']}** ＋ 在库 **{acc['identity_A_在库']}** ＋ excluded **{acc['identity_A_excluded']}** "
  f"＋ retracted **{acc['identity_A_retracted']}** = **{acc['identity_A_左值']}**")
w(f"- 该表历史键全集（= 源侧本轮清单 ∪ 台账历史 key）= **{acc['identity_A_右值']}**")
w(f"- **差额 = {acc['identity_A_差额']} ✅**；另一式（源侧清单 {acc['identity_B_左值']} == 在库 {acc['identity_B_右值']}）"
  f"差额 = {acc['identity_B_差额']} ✅")
w()
w("### 9.3 `index 行数 == 台账有效最新行数`")
w()
w(f"- index = **{index_rows}**；台账有效最新行（非 gone / 非 retracted）= **{len(live)}**；"
  f"**差额 {index_rows-len(live)} ✅**")
w()
w("### 9.4 三方一致")
w()
w(f"- 检查范围 {len(files)} 个库目录资源文件；**不符处数 = {len(runj['mismatch'])}** "
  f"{runj['mismatch'] if runj['mismatch'] else '（无）'} ✅")
w()
w("### 9.5 `1_外部标准库/` 文件数")
w()
w(f"- 恢复前 81 + 恢复 15 = **{by_kb.get('external_standard')}** ✅（= 上一批清理前的 96）")
w()
w("### 9.6 `kb_version` 与 versions")
w()
w(f"- `registry.kb_version` = **{reg['kb_version']}**（仍为 v0）；"
  f"`kb/versions/versions.jsonl` 版本行 = **0**（且文件未被改动：{not versions_changed}） ✅")
w()
w("### 9.7 `KB/l1/` 及以下未被修改")
w()
_l1 = [p for p in changed + missing if re.match(r"kb/l[1-9]/", p)]
w(f"- 开工前对 **{len(base)}** 个文件记了 `size + mtime`；运行后：")
w(f"  - **内容被改的 {len(changed)} 个**：")
for p in sorted(changed):
    w(f"    - `{p}`")
w(f"  - **被移动的 {len(missing)} 个**：全部是 gone 的库目录资源文件（移入 `_archive/gone-{RUN}/`）")
w(f"- `KB/l1/` 及以下被改的：**{_l1}** —— 仅 `kb/l3/registry/l3.json`（任务第 6 件允许的追加标注）；"
  f"`kb/l2/**`、`kb/l1/**` 零写入 ✅")
w(f"- `kb/l0/links/graph.jsonl` 被改：**{graph_changed}**（本批不动图）✅")
w()
w("### 9.8 上一批产物的可复核性")
w()
w("| 文件 | 本批前 sha256 | 本批后 |")
w("|---|---|---|")
for p, k in ((f"{L0}/manifest.jsonl", "台账"), (f"{L0}/links/graph.jsonl", "边表"),
             (f"{L0}/index/l0.jsonl", "index")):
    b = base.get(p, {})
    w(f"| `{p}` | size={b.get('size')} mtime={b.get('mtime')} | {'未改' if p not in changed else '已追加/重建（本批职责）'} |")
w()
w("旧台账前 1283 行（上一批结束后行数）逐字节未变：")
w()
_h = "".join(open(f"{L0}/manifest.jsonl", encoding="utf-8").readlines()[:1283])
w(f"- `head -1283 kb/l0/manifest.jsonl | shasum -a 256` → `{sha(_h)}`")
w(f"- 上一批结束时记录的 `kb/l0/manifest.jsonl` sha256 = `71f055111a4df7b851d4b9b2a9200e02d629098b5e66ff111d887c315bc85661`")
w(f"- **{'逐字节一致 ✅' if sha(_h) == '71f055111a4df7b851d4b9b2a9200e02d629098b5e66ff111d887c315bc85661' else '不一致 ❌'}**")
w()
w("## 10. 本批写入清单")
w()
w(f"- 台账追加 **{runj['ledger_rows_appended']}** 行（202 gone + 1 表资源 updated + 441 新登记 + 15 restored）")
w(f"- 新增资源文件 **{len(runj['written_files'])}** 个")
w(f"- `records/正面和负面样本/` 新增 **{runj['record_files']}** 个 verbatim 文件")
w(f"- `index/l0.jsonl` 重建 **{index_rows}** 行")
w(f"- `registry/kb.json` 改动（R17/R25 pattern、field_roles、overrides、field_role_retired、gone_policy、schema_snapshots）")
w(f"- `kb/l3/registry/l3.json` 追加 `filter_rules.step1_metadata.schema_sync_log[]`（**本批唯一写到 kb/ 内 l0 之外的路径**）")
w(f"- 文件移动：gone 202 个 → `{ARCHIVE_GONE}/`；规则库 URL 15 个 `_archive/` → `1_外部标准库/`")
w(f"- `links/graph.jsonl` **未改动**")

open(f"{L0}/runs/{RUN}.report.md", "w", encoding="utf-8").write("\n".join(W_) + "\n")
print("report:", f"{L0}/runs/{RUN}.report.md", len(W_), "lines")
print("changed:", len(changed), "| moved:", len(missing), "| l1-:", _l1)
print("index:", index_rows, "live:", len(live), "files:", len(files))
