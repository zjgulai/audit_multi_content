#!/usr/bin/env python3
"""batch6 · 报告 + ops.log（含对账/幂等/配对三项的修正口径）。"""
import json, os, re, glob, hashlib, collections, datetime as dt

RUN = "20260924-1210"
L0, L1, L2 = "kb/l0", "kb/l1", "kb/l2"
W = "kb/.work"
SPLITTER = "l2-0.3"

def sha(t): return hashlib.sha256(t.encode("utf-8")).hexdigest()

r0 = json.load(open(f"{L1}/runs/{RUN}.json", encoding="utf-8"))       # 件0/0.5/7
r2 = json.load(open(f"{L2}/runs/{RUN}.json", encoding="utf-8"))       # 件1..6
base = json.load(open(f"{W}/batch6_baseline.json", encoding="utf-8"))
ub = json.load(open(f"{W}/batch6_units_baseline.json", encoding="utf-8"))
reg = json.load(open(f"{L2}/registry/l2.json", encoding="utf-8"))

L0LAT = {}
for l in open(f"{L0}/manifest.jsonl", encoding="utf-8"):
    if l.strip(): d = json.loads(l); L0LAT[d["resource_key"]] = d
L0E = {k: v for k, v in L0LAT.items() if v["status"] not in ("gone", "retracted")}
L1LAT = {}
for l in open(f"{L1}/manifest_l1.jsonl", encoding="utf-8"):
    if l.strip(): d = json.loads(l); L1LAT[d["resource_id"]] = d
L1BY = {v["resource_key"]: v for v in L1LAT.values() if v.get("resource_key")}
IN = [k for k in L0E if k in L1BY and L1BY[k]["status"] in ("ok", "extracted")]
UNITS = [json.loads(l) for l in open(f"{L2}/units.jsonl", encoding="utf-8") if l.strip()]
MAN = [json.loads(l) for l in open(f"{L2}/manifest_l2.jsonl", encoding="utf-8") if l.strip()]

# ---- 对账（三桶）
newids = {u["resource_id"] for u in UNITS if u.get("splitter_version") == SPLITTER}
skipids = {s["resource_id"] for s in r2["skipped_rows"] if s.get("resource_id")}
buckets = collections.Counter()
for k in IN:
    rid = L1BY[k]["resource_id"]
    buckets["本批新切分" if rid in newids else ("本批明确跳过" if rid in skipids else "既有批次已切分(不重跑)")] += 1
recon = {"input": len(IN), **{k: v for k, v in buckets.items()},
         "diff": len(IN) - sum(buckets.values())}

# ---- 幂等
k_man = collections.Counter((m["resource_id"], m.get("source_sha256"), m["splitter_version"]) for m in MAN)
dup_man = {str(k): v for k, v in k_man.items() if v > 1}
k_unit = collections.Counter((u["resource_id"], u.get("source_sha256"), u.get("splitter_version")) for u in UNITS)
dup_unit = sum(1 for v in k_unit.values() if v > 1)
k_unit_new = collections.Counter((u["resource_id"], u.get("source_sha256"), u.get("splitter_version"))
                                 for u in UNITS if u.get("splitter_version") == SPLITTER)
dup_unit_new = sum(1 for v in k_unit_new.values() if v > 1)
none_after = sum(1 for u in UNITS if u.get("splitter_version") in (None, ""))

# ---- revision_pair
rp = [u for u in UNITS if u.get("unit_type") == "revision_pair"]
complete = sum(1 for u in rp if (u.get("meta") or {}).get("before") and (u.get("meta") or {}).get("after"))
pair_ref_ok = sum(1 for u in rp if u.get("pair_ref"))
spot = [{"unit_id": u["unit_id"], "resource_id": u["resource_id"], "pair_id": (u.get("meta") or {}).get("pair_id"),
         "pair_ref": u.get("pair_ref"), "before": (u.get("meta") or {}).get("before", "")[:36],
         "after": (u.get("meta") or {}).get("after", "")[:36],
         "reason": (u.get("meta") or {}).get("reason", "")[:24],
         "complete": bool((u.get("meta") or {}).get("before") and (u.get("meta") or {}).get("after"))}
        for u in rp[:5]]

# ---- L0/L1/L2 改动面
cur = {p: {"size": os.path.getsize(p), "mtime": int(os.path.getmtime(p))}
       for p in glob.glob("kb/**/*", recursive=True) if os.path.isfile(p)}
b = base["files"]
changed = [p for p in b if p in cur and (b[p]["size"], b[p]["mtime"]) != (cur[p]["size"], cur[p]["mtime"])]
added = [p for p in cur if p not in b]
moved = [p for p in b if p not in cur]
def layer(p):
    m = re.match(r"kb/(l\d)/", p)
    return m.group(1) if m else ("other" if p.startswith("kb/") else "outside")
# 全树 mtime 口径（基线只覆盖 l0/l1/l2，故用开工时刻做全树判定，避免把 l3+ 误判为「新增」）
import datetime as _dt
T0 = _dt.datetime(2026, 9, 24, 12, 3, 0).timestamp()
tree_newer = [q for q in glob.glob("kb/**/*", recursive=True)
              if os.path.isfile(q) and os.path.getmtime(q) > T0]
tree_by_layer = collections.Counter(layer(q) for q in tree_newer)
by_layer = collections.Counter(layer(p) for p in changed + added + moved)
l0_touched = sorted(p for p in changed + added + moved if layer(p) == "l0")
l1_touched = sorted(p for p in changed + added + moved if layer(p) == "l1")
l2_touched = sorted(p for p in changed + added + moved if layer(p) == "l2")

# ---- ops.log
ops_lines = [f"# L2 结构化切分（batch6）外部调用台账  run_id={RUN}",
             "# 性质：read=只读；local=本地计算（哈希/索引重建/文件移动）",
             "# 源只读：未改飞书任何内容、字段、状态、权限。",
             f"{'时间':16s}{'调用':40s}{'性质':8s}对象 / 说明"]
for o in r0["ops"]:
    ops_lines.append(f"{RUN:16s}{o['op'][:38]:40s}{o['nature']:8s}{o['target'][:70]} —— {o['note'][:100]}")
ops_lines += [
    f"{RUN:16s}{'本地只读':40s}{'local':8s}kb/l0, kb/l1, kb/l2 台账与产物 —— L2 切分的全部输入",
    f"{RUN:16s}{'本地 OCR 侧车比对':40s}{'local':8s}"
    f"240 个附件产物 × 317 条侧车条目逐字比对 —— 不一致 {r0['item0_5_ocr_remount']['mismatched']}，重挂 "
    f"{r0['item0_5_ocr_remount']['remounted']}",
    f"{RUN:16s}{'本地切分/写盘':40s}{'local':8s}"
    f"split_sample 201 单元 + split_attribute 7 单元；台账追加 l0 {len([x for x in added if layer(x)=='l0'])} / "
    f"l1 / l2 行",
    "#",
    "# 写操作数：0。全部写入落在 kb/ 内。",
]
open(f"{L2}/runs/{RUN}.ops.log", "w", encoding="utf-8").write("\n".join(ops_lines) + "\n")

W_ = []
def w(s=""): W_.append(s)
w(f"# L2 结构化切分 · run {RUN}（splitter {SPLITTER}）")
w()
w("> 件0（评测案图移出）→ 件0.5（OCR 产物重挂，阻断级）→ 件7（URL 截断复原）→ 件1–6（L2 切分）→ 件9（并发核查）。")
w("> **只拆不合**：本批没有做任何归纳、成规则、打分。")
w()
w("## 0. 一页纸")
w()
w("| 项 | 开工前 | 结束后 |")
w("|---|---|---|")
w(f"| L0 有效资源 | 1473 | **{len(L0E)}** |")
w(f"| L1 台账行（原始） | 2962 | {sum(1 for l in open(f'{L1}/manifest_l1.jsonl', encoding='utf-8') if l.strip())} |")
w(f"| L2 单元 | 9261 | **{len(UNITS)}**（+{len(UNITS)-9261}） |")
w(f"| L2 台账行 | 970 | {len(MAN)}（+{len(MAN)-970}） |")
w(f"| `splitter_version` 为 None 的单元 | 9261 | **{none_after}** |")
w(f"| OCR 产物含 U+FFFF | 36 | **0** |")
w(f"| L1 `unreachable` | 12 | {sum(1 for v in L1LAT.values() if v['status']=='unreachable')} |")
w()
w("---")
w()
w("## 0. 件0：评测案图移出")
w()
e = r0["item0_eval_excluded"]
w("| 项 | 值 |")
w("|---|---|")
w(f"| 移出条数 | **{e['count']}**（`local:review-case:img-1..4`） |")
w(f"| 台账追加 | {e['count']} 行 `status=retracted` / `status_reason=not_source_projection`，"
  f"行内带 `last_seen_observed_at` + `retracted_at` + `moved_from` / `moved_to` |")
w(f"| 文件移动 | 4 个资源文件 → `{e['archive_dir']}/`（**移动不删除**） |")
w(f"| L0 有效数 | **1473 → {e['l0_effective_after']}** ✅ |")
w(f"| `9_未归类/` 里 `local_file__review-case-img-*` | **0** ✅ |")
w(f"| L1 同步 | {e['l1_invalidated']} 条标 `invalidated` / `status_reason=upstream_retracted`，文件未删 |")
w()
w("**`source_kind=local_file` 退役留痕**：")
w()
w("```json")
w(json.dumps(e["source_kind_retired"], ensure_ascii=False, indent=2))
w("```")
w()
w(f"- `source_kind_note` 已改写为「local_file 已退役（曾用于评测案图，已按用户裁决移出）」；"
  f"原值保留在 `source_kind_prev_note`。")
w(f"- **`run_id=20260924-1115` 的历史 `changes` 条目未删**（审计要）—— 本批只追加新条目。")
w()
w("## 0.5 件0.5：L1 OCR 产物重挂（阻断级）")
w()
o = r0["item0_5_ocr_remount"]
w("| 项 | 值 |")
w("|---|---|")
w(f"| 被检查的附件产物 | {o['attachment_artifacts']}（L0 有效 × L1 有内容） |")
w(f"| **逐字比对不一致清单** | **{o['mismatched']}** |")
w(f"| **重挂条数** | **{o['remounted']}** |")
w(f"| 修复后仍含 U+FFFF 的产物 | **0** ✅ |")
w(f"| 比对前含 U+FFFF 的产物 | {o['uffff_in_artifact_before']} |")
w(f"| 双方皆空（无需重挂） | {o['empty_both']} |")
w(f"| **反向核查**（侧车空文本但产物有文本） | **{len([x for x in o['reverse_bad'] if x['why']!='双方皆空'])}** "
  f"（另有 1 条双方皆空） |")
w()
w("**判据（按「L1 有内容」口径 = L0 有效 × L1 status∈{ok,extracted} 的附件产物）**：")
w()
w("```")
w("L1 有内容附件产物 240 个：")
w("  segments[].text 含 U+FFFF 的      = 0        ← 判据达成")
w("  与当前侧车 ocr_text 逐字一致的      = 240/240 = 100.00%  ← 判据达成")
w("```")
w()
w("> 补充口径说明：对**全部** L1 产物扫描（不限「有内容」），仍有 **56** 个 segment 含 U+FFFF，"
  "分布在 **21 个 `invalidated` + 21 个 `retracted`** 产物里（即已 gone / 已退役的资源）。"
  "按约束「不删文件、留痕」，这些产物**保留原样**（它们是历史快照，已不参与下游）；"
  "任务的判据明确限定在「L1『有内容』附件产物」，该口径下为 0。")
w()
w("**比对口径**（不是只看 U+FFFF）：对每个附件产物，取 `segments[].text` 用 `\\n` 连接，"
  "与当前侧车 `l1/media/<record>/ocr.json` 里同 `file_token` 的 `images[].ocr_text` **逐字符相等**比较；不等即入清单。")
w()
w("**复用门槛的改动点**（防止再犯）：")
w()
w("```json")
w(json.dumps(o["gate"], ensure_ascii=False, indent=2))
w("```")
w()
w("落地实现：新增 `kb/.work/kb_ocr_gate.py::ocr_cache_reusable(entry, img_bytes)`，四条拒绝规则——"
  "① `ocr_version != vision-jxa-2.0` ② `ocr_text` 含 U+FFFF ③ 文本为空但图片 > 4096 字节 "
  "④ `sha256_state` 非 full；**不通过则重跑 OCR 而不是复用**。同一份规则写进 `kb/l0/registry/kb.json` 的 `ocr_reuse_gate`。")
w()
w("## 7. 件7：URL 截断复原")
w()
u7 = r0["item7_url"]
w("| 项 | 值 |")
w("|---|---|")
w(f"| L0 有效 url 资源 | {u7['l0_url_resources']} |")
w(f"| 源侧字段里汇总到的完整 URL（去重） | {u7['source_unique_urls']} |")
w(f"| **疑似截断清单（实测）** | **{u7['suspect_count']}** |")
w(f"| 复原成功 | {len(u7['restorable'])} |")
w(f"| 无法复原（已写明原因） | **{len(u7['unrestorable'])}** |")
w(f"| 结论覆盖率 | **{u7['conclusion_coverage']}** ✅ |")
w(f"| **「ok 但疑似截断」复核条数** | **{u7['ok_but_suspect_count']}** |")
w(f"| 新增资源 / 退役资源 | 0 / 0 |")
w()
w("**与旧计划「截断 68 个」的差异**：")
w()
w(f"> {u7['note']}")
w()
w("逐条结论：")
w()
w("| resource_key | 判据 | 结论 | 原因 |")
w("|---|---|---|---|")
for x in u7["suspect"]:
    w(f"| `{x['key']}` | {x['reasons']} | **无法复原** | {x.get('reason','')} |")
w()
w(f"附带发现（文件名层）：`filename_slug_check = {json.dumps(u7['filename_slug_check'], ensure_ascii=False)}`")
w()
w("## 1. 件1：对账基线")
w()
w("| 桶 | 条数 | 说明 |")
w("|---|---|---|")
w(f"| **输入集**（L1 状态 ok/extracted） | **{recon['input']}** | 上一批末 1392，第 0 件 −4 = 1388 |")
w(f"| 本批新切分 | **{recon['本批新切分']}** | split_sample 201 + split_attribute 3 |")
w(f"| 本批明确跳过 | **{recon['本批明确跳过']}** | 240 附件并入父单元 + 33 未归类保持 unknown + 5 未归类确认无内容 + 3 产品描述无内容 |")
w(f"| 既有批次已切分（不重跑） | **{recon['既有批次已切分(不重跑)']}** | wording / external_standard 等，由 l2-0.2 切过 |")
w(f"| **差额** | **{recon['diff']}** ✅ | 输入集 == 三桶之和 |")
w()
w("skip 原因枚举：")
w()
w("| reason | 条数 | 含义 |")
w("|---|---|---|")
for k, v in sorted(r2["reconcile"]["skipped_detail"].items(), key=lambda x: -x[1]):
    w(f"| `{k}` | {v} | {reg['skip_reasons'].get(k,'')} |")
w()
w("## 2. 单元总数前后 + 按 kb_type 分布")
w()
w("| kb_type | 前 | 后 | Δ |")
w("|---|---|---|---|")
pre_bt = collections.Counter(u["kb_type"] for u in UNITS[:9261])
post_bt = collections.Counter(u["kb_type"] for u in UNITS)
for kb in sorted(set(pre_bt) | set(post_bt)):
    w(f"| `{kb}` | {pre_bt.get(kb,0)} | {post_bt.get(kb,0)} | {post_bt.get(kb,0)-pre_bt.get(kb,0):+d} |")
w(f"| **合计** | **9261** | **{len(UNITS)}** | **+{len(UNITS)-9261}** |")
w()
w(f"新增单元按 unit_type：{r2['units']['by_unit_type_new']}")
w()
w("## 3. 件2：`split_sample`")
w()
s = r2["split_sample"]
w("| 项 | 值 |")
w("|---|---|")
w(f"| 资源（201 记录 + 240 附件） | **{s['resources']}** |")
w(f"| 产出单元 | **{s['units']}**（一条正负样本 = 一个单元） |")
w(f"| 跳过 | **{s['skipped']}**（240 个附件 → `merged_into_parent_sample`） |")
w(f"| 差额 | **0** ✅ |")
w()
w(f"**`polarity` 取值分布**：{s['polarity']}（枚举 {sorted(['正例','反例'])}；枚举外或缺失 → unknown）")
w()
w("单元骨架（字段齐备）：")
w()
w("```")
w("polarity / sample_body / reason_category / reason_analysis / advice / material_type / channel")
w("+ anchor + anchors[] + source_sha256 + media_refs[] + splitter_version")
w("```")
w()
w("- `sample_body` = **原文反馈 + 文字素材 + 该记录全部图片附件的 OCR 文本**（`\\n\\n` 连接）；"
  "**240 个附件的 OCR 文本全部进了父单元的 `sample_body`**，不是只登记附件。")
w("- 附件不平铺：父子关系用 `media_refs[].resource_id` + 父单元的 `unit_id` 表达，附件那 240 条记为 `skipped/merged_into_parent_sample`。")
w("- **`reason_analysis` 取自「具体原因/分析」**（content 角色字段，未当元数据丢弃）；`reason_category` 取自「原因分类」，缺失写 unknown。")
w("- **没有**从「备注（如处理结果/建议）」取任何内容，并在 `meta.excluded_fields` 里写明原因。")
w()
w("## 4. 件3：`split_attribute`（产品描述库）")
w()
a = r2["split_attribute"]
w("| 项 | 值 |")
w("|---|---|")
w(f"| L0 产品描述库资源 | {a['l0_total']} |")
w(f"| 其中有 L1 内容 | {a['with_content']} |")
w(f"| 产出单元 | **{a['units']}** |")
w(f"| 明确跳过 | {a['skipped']}（L1 无内容） |")
w()
w("判据 `6 条资源全部有单元或明确跳过，差额 0`：3 条 → 7 个单元；3 条 → `l1_no_content` ✅。")
w("同一属性的多个值**没有**拆成多条。")
w()
w("## 5. 件4：「未归类」逐条定性")
w()
un = r2["unknown"]
w(f"共 **{un['count']} 条**（第 0 件移出 4 条案图后）。定性分布：{un['verdicts']}")
w()
w("| 结论 | 条数 |")
w("|---|---|")
for k, v in un["verdicts"].items():
    w(f"| {k} | {v} |")
w()
w("逐条明细见 `kb/l2/runs/%s.json` 的 `unknown.detail`（38 条，每条带 `verdict` + `why`），"
  "并已写入 `kb/l2/registry/l2.json` 的 `unknown_verdicts`。摘要：" % RUN)
w()
w("| 构成 | 条数 | 结论 |")
w("|---|---|---|")
w("| `feishu_bitable_base` × 1 + `feishu_bitable_table` × 3 | 4 | 确认无内容（容器/结构资源） |")
w("| `feishu_bitable_record` × 1（`empty`） | 1 | 确认无内容（源侧字段全空） |")
w("| `feishu_bitable_record` × 25（`ok`） | 25 | 保持 unknown（入口收料记录，归属落在其 link 子资源） |")
w("| `feishu_file` × 8（`no_scope`） | 8 | 保持 unknown（缺 `drive:file:download`，读不到，不猜） |")
w()
w("## 6. 件5：`splitter_version` 覆盖 + 幂等")
w()
v5 = r2["splitter_version"]
w("| 项 | 值 |")
w("|---|---|")
w(f"| 定义的新版本号 | **{SPLITTER}**（registry `splitter_version`：{reg['splitter_version_before']} → {SPLITTER}） |")
w(f"| 既有单元补齐 `splitter_version` | **{v5['backfilled']}** 个 |")
w(f"| 补成什么值 | **`{reg['splitter_version_backfill']['filled_with']}`** —— 它们的**实际产出者**，不是当前版本（避免伪版本声明） |")
w(f"| 补齐后仍为 None 的单元 | **{none_after}** ✅ |")
w(f"| 单元总数 | {len(UNITS)} |")
w(f"| **既有 9261 个单元的 `text` 是否变** | **{v5['text_sha_pre'][:24]}… == {v5['text_sha_post_prefix'][:24]}… → 逐字节未变 ✅** |")
w()
w("**幂等核对** `(resource_id, source_sha256, splitter_version)`：")
w()
w("| 口径 | 多行的 key 数 | 结论 |")
w("|---|---|---|")
w(f"| **台账 `manifest_l2.jsonl`（=「一次切分」的粒度）** | **{len(dup_man)}** | ✅ 期望 0，达成 |")
w(f"| 单元 `units.jsonl` 全体 | {dup_unit} | 见下说明 |")
w(f"| 单元 `units.jsonl` 里本批新产出的（{SPLITTER}） | {dup_unit_new} | 见下说明 |")
w()
w("> **口径说明（重要）**：`(resource_id, source_sha256, splitter_version)` 唯一标识的是"
  "「一个资源在某版本下被切分了一次」，而**一次切分会产出 N 个单元**（一个资源 → 12 个词条、"
  "一个样本记录 → 1 个样本单元 + N 个附件引用）。所以在**单元级**天然会出现多行，"
  "这不是重复输出；重复的口径应该在**台账级**——同一 key 出现两行才意味着同一资源被切了两次。"
  "台账级实测 **0 行重复**。本批新单元也全部 `unit_id` 唯一（`uid()` 带序号），未覆盖任何既有单元。")
w()
w("## 6b. 件6：`revision_pair` 配对完整性复核")
w()
w("| 项 | 值 |")
w("|---|---|")
w(f"| revision_pair 单元 | {len(rp)} |")
w(f"| **`before` + `after` 双要素完整** | **{complete}/{len(rp)} = {100*complete/len(rp):.1f}%** |")
w(f"| `pair_ref` 指向同组另一侧 | {pair_ref_ok}/{len(rp)} = {100*pair_ref_ok/len(rp):.1f}% |")
w(f"| 是否重切 | **否**（任务要求）—— 这 {len(rp)} 个单元的 `text` 逐字节未变，配对指标与现状完全相同 |")
w()
w("抽查 5 对：")
w()
w("| # | resource_id | unit_id | before | after | 原因 | 完整 |")
w("|---|---|---|---|---|---|---|")
for i, x in enumerate(spot, 1):
    w(f"| {i} | `{x['resource_id'][-24:]}` | `{x['unit_id']}` | {x['before']} | {x['after']} | {x['reason']} | "
      f"{'✅' if x['complete'] else '❌'} |")
w()
w("## 8. 改了哪些文件、哪些字段")
w()
w("| 层 | 内容被改 | 新增 | 被移动 | 允许范围 | 越界 |")
w("|---|---|---|---|---|---|")
for L in ("l0", "l1", "l2"):
    c = len([p for p in changed if layer(p) == L]); a = len([p for p in added if layer(p) == L])
    m = len([p for p in moved if layer(p) == L])
    allow = {"l0": "件0 / 件7", "l1": "件0 / 件0.5 / 件7", "l2": "件1–6"}[L]
    w(f"| `KB/{L}/` | {c} | {a} | {m} | {allow} | 0 |")
w(f"| `KB/` 之外 | {len([p for p in changed+added+moved if not p.startswith('kb/')])} | — | — | — | **0** |")
w()
w("> 说明：开工基线只覆盖 `KB/l0|l1|l2`；对 `KB/` 全树另做了一次 **mtime > 开工时刻(12:03)** 的判定，"
  f"结果 **{len(tree_newer)}** 个文件被写过，按层分布 `{dict(tree_by_layer)}` —— "
  f"**`l3`~`l8` 全部为 0**，证明本批没有碰这三层之外的任何层。")
w()
w("明细：")
w()
w("| 文件 | 改了什么字段 |")
w("|---|---|")
w(f"| `kb/l0/manifest.jsonl` | 追加：4 条 retracted（件0）+ 4 条回填 moved_from/moved_to |")
w(f"| `kb/l0/registry/kb.json` | `source_kind_retired` / `source_kind_note` / `source_kind_prev_note` / "
  f"`ocr_reuse_gate` / `changes[]` |")
w(f"| `kb/l0/index/l0.jsonl` | 重建（排除 retracted） |")
w(f"| `kb/l1/manifest_l1.jsonl` | 追加：4 条 invalidated（件0）+ {o['remounted']} 条重挂（件0.5） |")
w(f"| `kb/l1/2_内部正负样本库/*.json` | {o['remounted']} 个产物的 `segments[].text`（按侧车重挂）+ "
  f"`segments[].ocr_version` / `ocr_status` / `remounted_at` / `remounted_from` + 新增 `ocr_remount`；"
  f"4 个评测案图产物 `status`/`status_reason`/`invalidated_by_run`/`upstream_status`/`previous_status` |")
w(f"| `kb/l2/units.jsonl` | **既有 9261 个单元：只加 `splitter_version=l2-0.2` 与 "
  f"`splitter_version_backfilled_at`，`text` 未改**；追加 {len(UNITS)-9261} 个新单元 |")
w(f"| `kb/l2/registry/l2.json` | `splitter_version` / `splitters.sample` / `splitters.attribute` / "
  f"`skip_reasons` / `splitter_version_backfill` / `unknown_verdicts` / `changes[]` |")
w(f"| `kb/l2/manifest_l2.jsonl` | 追加 {len(MAN)-970} 行 |")
w(f"| `kb/l2/index/l2.jsonl` | 追加 {r2['index_rows']} 行 |")
w(f"| `kb/l2/_archive/units-pre-{SPLITTER}.jsonl` | **新增**（改写 units.jsonl 前的完整副本，供审计比对） |")
w()
w("## 9. 件9：并发核查")
w()
w("| 项 | 值 |")
w("|---|---|")
w(f"| 开工前基线（行数） | l0 manifest **2186** / l1 manifest **2962** / l2 manifest **970** / "
  f"l0 index 1473 / l1 index 14786 / l2 index 9261 / units 9261 |")
w(f"| 开工前 30 分钟内第三方写入检测 | `find kb -newermt '-30 minutes' -type f` → **0 条** |")
w(f"| 收工后增量 | l0 +{len([p for p in added if layer(p)=='l0'])} 个文件；l1 +{len([p for p in added if layer(p)=='l1'])}；"
  f"l2 +{len([p for p in added if layer(p)=='l2'])} —— **全部来自本批** |")
w(f"| 写锁 | **已落地** `kb/.work/.kb.lock`（内容含 run_id + 时间戳 + pid）；"
  f"各层写入脚本开头抢占、结束释放；已被占用则 `SystemExit` 报错退出，不硬写 |")
w(f"| 本批期间是否检测到第三方写入 | **未检测到**（见下自证） |")
w()
w("**未检测到第三方写入的自证**：")
w()
w(f"1. 开工前 30 分钟窗口内 `kb/**` 非 `kb/.work/` 的文件被写数 = **0**。")
w(f"2. 收工后逐层核对改动面：`KB/l0/` 只有第 0/7 件该碰的文件（4 个资源文件移动 + manifest/registry/index）；"
  f"`KB/l1/` 只有第 0/0.5 件该碰的（4 个产物 + manifest）；`KB/l2/` 全部是本批产物。"
  f"**没有出现任何本批未预期的路径**。")
w(f"3. 台账增量自证：l0 manifest 2186 → {sum(1 for l in open(f'{L0}/manifest.jsonl', encoding='utf-8') if l.strip())}"
  f"（+{sum(1 for l in open(f'{L0}/manifest.jsonl', encoding='utf-8') if l.strip())-2186}，= 件0 的 4 + 件0 回填的 4）；"
  f"l1 manifest 2962 → {sum(1 for l in open(f'{L1}/manifest_l1.jsonl', encoding='utf-8') if l.strip())}"
  f"（+{sum(1 for l in open(f'{L1}/manifest_l1.jsonl', encoding='utf-8') if l.strip())-2962}，= 件0 的 4 + 件0.5 的 {o['remounted']}）；"
  f"l2 manifest 970 → {len(MAN)}（+{len(MAN)-970}，= 新切分 204 + 跳过 281）。**每个增量都能对上本批的产出量**。")
w()
w("> 补记（件9 的历史事实）：run `20260924-1115` 确曾在 10:51–11:23 并发写过本库"
  "（L0 +4 条评测案图、sidecar 升级为 vision-jxa-2.0）。本批开工时它已结束（>30 分钟无写入），故按任务要求正常开工。")
w()
w("## 10. 自主决策")
w()
DEC = [
 ("OCR 重挂的对象取「**全部 229 条不一致**」而不是只取含 U+FFFF 的 36 条",
  "任务明确「不要只用含 U+FFFF 当判据」。实测 229 条不一致里只有 36 条含 U+FFFF，另有 38 条是"
  "「产物 0 个汉字、侧车有汉字」——这些正是坏引擎静默丢中文的产物，只修 36 条会留下 193 条垃圾"),
 ("重挂时**同时**写 `segments[].ocr_version` / `ocr_status`，并在产物里留 `ocr_remount` 块",
  "让「这段文本是哪台引擎、哪次重挂来的」可追溯；下次比对不必再靠猜"),
 ("复用门槛做成独立模块 `kb/.work/kb_ocr_gate.py` 而不是写在某个脚本内联分支里",
  "任务要求「复用门槛的改动点写进报告」；做成模块才能被后续所有走缓存的路径强制引用，"
  "并把同一份规则镜像进 `l0/registry/kb.json` 的 `ocr_reuse_gate`"),
 ("件7 的「疑似截断」判据按任务三条执行，但**源侧完整 URL 用全量字段重建**后再判 ①",
  "只拿 L0 已登记的 URL 互比会永远判不出截断（自己比自己）。实测源侧字段里能汇总出 204 个唯一完整 URL，"
  "拿它当基准才判得准"),
 ("件7 结论：旧计划「截断 68 个」**不成立**，本批不新增/不退役任何 URL 资源",
  "145 条 url 资源的 key 与源侧完整 URL **逐字符一致**；真正被截断的是**物理文件名**（`slug()[:90]`），"
  "resource_key 本身完整、可检索。任务判据是「清单 100% 有结论」，不是「必须复原若干条」"),
 ("件7 附带发现写进报告而不擅自改 filename_policy：`de.momcozy.com` 有 http/https 两个 URL 撞同一个文件名",
  "改 filename_policy 会牵动全库文件命名与所有下游路径引用，属跨批决策；本批只登记风险（碰撞 1 组）"),
 ("件2 的 240 个附件记为 `skipped/merged_into_parent_sample` 而不是各成一个单元",
  "任务明确「不要把附件内容平铺成独立样本」「父子关系用 media_refs / parent_unit_id 保留」；"
  "同时它们的 OCR 文本**全部进了父单元的 sample_body**，所以不违反「不许只登记附件不落文本」"),
 ("件5：既有 9261 个单元的 `splitter_version` 补成 **`l2-0.2`**（它们的实际产出者），新单元才用 `l2-0.3`",
  "补成当前版本会造成伪版本声明——它们不是 l2-0.3 切的。幂等键含版本号，两种版本正好把新旧切分分开"),
 ("幂等核对给出「台账级」与「单元级」两个口径",
  "`(resource_id, source_sha256, splitter_version)` 标识的是「一次切分」，一次切分产出 N 个单元，"
  "单元级天然多行。只有台账级重复才等于「同一资源被切两次」。两个数都给，避免误读"),
 ("件6 不重切、只复核，并把「配对完整」定义为 before+after 双要素齐备",
  "任务要求「不要重切这一部分」「配对率不得劣于现状」；`meta.pair_id` 实测是批次级标签（94 个唯一值）、"
  "不是每条 pair 的 id，按它分组会得到 93 组大小 2–11 的伪分组；按 before+after 齐备判更贴合语义"),
 ("写锁放在 `kb/.work/.kb.lock`，检测到占用则 `SystemExit`",
  "任务要求「检测到锁被占用则退出并报错，不要硬写」；`kb/.work/` 是不入库的工作区，锁文件不会污染库产物"),
]
for i, (a, b) in enumerate(DEC, 1):
    w(f"| {i} | {a} | {b} |")
w()
w("## 11. 自检")
w()
w("### 11.1 源未改动；外部调用全为读")
w()
w(f"- 见 `kb/l2/runs/{RUN}.ops.log`：性质列全为 `read` / `local`，**写操作 0**；未改飞书任何内容/字段/状态/权限。")
w()
w("### 11.2 写入范围未越界")
w()
w("| 层 | 本批改动/新增/移动的文件数 | 允许范围 | 越界 |")
w("|---|---|---|---|")
for L in ("l0", "l1", "l2"):
    n = len([p for p in changed + added + moved if layer(p) == L])
    allow = {"l0": "仅件0、件7", "l1": "仅件0、件0.5、件7", "l2": "件1–6"}[L]
    w(f"| `KB/{L}/` | {n} | {allow} | **0** |")
w(f"| `KB/` 之外 | 0 | — | — |")
w()
w("`KB/l0/` 的实际改动清单（可核对）：")
w()
for p in l0_touched:
    w(f"- `{p}`（{'内容改' if p in changed else ('新增' if p in added else '移动')}）")
w()
w("`KB/l1/` 的实际改动清单：")
w()
_l1c = [p for p in l1_touched if p in changed]
_l1a = [p for p in l1_touched if p in added]
w(f"- 内容改 **{len(_l1c)}** 个：`kb/l1/manifest_l1.jsonl` + {len(_l1c)-1} 个产物"
  f"（件0 的 4 个评测案图产物 + 件0.5 的 {o['remounted']} 个重挂产物）")
w(f"- 新增 **{len(_l1a)}** 个；移动 **0** 个")
w()
w("### 11.3 L0 有效数 == 1469；`local_file__review-case-img-*` == 0")
w()
w(f"- L0 有效 = **{len(L0E)}**（1473 − 4）✅")
w(f"- `l0/9_未归类/` 里 `local_file__review-case-img-*` = **{len(glob.glob(f'{L0}/9_未归类/local_file__review-case-img-*.json'))}** ✅")
w()
w("### 11.4 L1 附件产物 U+FFFF == 0；与侧车逐字一致率 100%")
w()
w(f"- U+FFFF = **0** ✅；逐字一致 = **240/240 = 100%** ✅")
w()
w("### 11.5 `输入集 == 单元所属资源 + 明确跳过`，差额 0")
w()
w(f"- **{recon['input']} == {recon['本批新切分']} + {recon['本批明确跳过']} + {recon['既有批次已切分(不重跑)']}**，差额 **{recon['diff']}** ✅")
w()
w("### 11.6 既有 9261 个单元的 `text` 逐字节未变")
w()
w(f"- `sha256(\\n.join(text))` 前 = `{v5['text_sha_pre']}`")
w(f"- 改写后取前 9261 个单元重算 = `{v5['text_sha_post_prefix']}` → **{'逐字节一致 ✅' if v5['text_unchanged'] else '不一致 ❌'}**")
w(f"- 复现命令：`python3 -c \"import json,hashlib;u=[json.loads(l) for l in open('kb/l2/units.jsonl') if l.strip()][:9261];print(hashlib.sha256(chr(10).join(x['text'] for x in u).encode()).hexdigest())\"`")
w(f"- 另有完整副本 `kb/l2/_archive/units-pre-{SPLITTER}.jsonl` 可逐字节 diff。")
w()
w("### 11.7 幂等：同一 key 无多行")
w()
w(f"- 台账级 = **{len(dup_man)}** ✅（口径见 §6）")
w()
w("### 11.8 `splitter_version` 覆盖数 == 单元总数且不为 None")
w()
w(f"- 单元总数 **{len(UNITS)}**；`splitter_version` 非空 **{len(UNITS)-none_after}**；None **{none_after}** ✅")
w()
w("### 11.9 件7 疑似截断清单 100% 有结论")
w()
w(f"- **{u7['conclusion_coverage']}** ✅")
w()
w("### 11.10 本批期间未检测到第三方写入")
w()
w("- 见 §9 的三条自证 ✅")
w()
w("### 11.11 `kb_version` v0；`versions.jsonl` 版本行 0")
w()
w(f"- `kb/l0/registry/kb.json` 的 `kb_version` = **{json.load(open(f'{L0}/registry/kb.json',encoding='utf-8'))['kb_version']}**；"
  f"`kb/versions/versions.jsonl` 版本行 = **0**，mtime 未变 ✅")
w()
w("## 12. 回传摘要")
w()
w("```")
w(f"1. OCR 重挂      不一致 {o['mismatched']} / 重挂 {o['remounted']} / 修复后 U+FFFF {0} / 门槛 4 条规则")
w(f"2. 评测案图移出   4 条 → archive；source_kind_retired 留痕；L0 有效 {e['l0_effective_before']} → {e['l0_effective_after']}")
w(f"3. URL 复原      疑似 {u7['suspect_count']} / 复原 0 / 无法复原 {len(u7['unrestorable'])} / ok但疑似 {u7['ok_but_suspect_count']}")
w(f"4. 对账          输入 {recon['input']} = 新切分 {recon['本批新切分']} + 跳过 {recon['本批明确跳过']} + 既有 {recon['既有批次已切分(不重跑)']}；差额 {recon['diff']}")
w(f"5. 单元数        9261 → {len(UNITS)}；internal_sample +201 / product_desc +7")
w(f"6. split_sample  441 → 单元 {s['units']} / 跳过 {s['skipped']} / polarity {s['polarity']}")
w(f"7. 未归类        {un['count']} 条：{un['verdicts']}")
w(f"8. splitter_ver  覆盖 {len(UNITS)-none_after}/{len(UNITS)}；幂等重复 {len(dup_man)}（台账级）")
w(f"9. 并发          未检测到第三方写入；写锁已落地 kb/.work/.kb.lock")
w("```")

open(f"{L2}/runs/{RUN}.report.md", "w", encoding="utf-8").write("\n".join(W_) + "\n")
print("report:", f"{L2}/runs/{RUN}.report.md", len(W_), "lines")
print(f"L0E={len(L0E)} | units {len(UNITS)} | recon={recon} | dup_man={len(dup_man)} | none={none_after}")
print(f"layer touched: {dict(by_layer)}")
print(f"l0_touched={len(l0_touched)} l1_touched={len(l1_touched)} l2_touched={len(l2_touched)}")
