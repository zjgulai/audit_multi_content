#!/usr/bin/env python3
"""batch4 修正：schema 同步必须先于登记，本批顺序颠倒导致 240 个附件的 matched_rule 走了表级兜底 R26。

修正内容：
  ① 规则 pattern 按「同一 field_id 延续」重排：R25(scope=正面和负面样本) → 图片素材（fldnvxjaSr，
     与旧字段 具体内容（截图/文案/OCR）**同一 field_id**，既有 77 个附件就是 R25 命中的）；
     R17(全局) → 视频素材（fld87JUpEn，全新字段）。
  ② 对 240 个本批新登记附件**重跑 eval_rule 真求值**，追加 `updated` 行（台账只追加），
     并就地刷新这 240 个**本批自己新建**的资源文件的 matched_rule / kb_type_source。
  ③ index 重建。
"""
import json, glob, os, sys, collections

sys.path.insert(0, "kb/.work")
from kb_l0_scan_lib import SCANNER_VERSION, eval_rule

RUN = "20260924-1100"
FIX = f"{RUN}+rulefix"
L0 = "kb/l0"
TBL, TBL_NAME = "tbld8qE92YaY38Yz", "正面和负面样本"

reg = json.load(open(f"{L0}/registry/kb.json", encoding="utf-8"))
r17 = next(r for r in reg["rules"] if r["id"] == "R17")
r25 = next(r for r in reg["rules"] if r["id"] == "R25")

# ① 重排 pattern（延续同一 field_id 的历史归属）
pattern_before = {"R17": r17.get("pattern_before_schema_migration"), "R25": r25.get("pattern_before_schema_migration")}
r17["pattern"] = "视频素材"
r17["note"] = ("素材附件字段（视频素材 attachment，全局字段名规则），归内部正负样本库。"
               "schema 漂移同步：" + RUN + " 起 `具体内容（截图/文案/OCR）` 已不存在；"
               "本规则承接新拆分出的 `视频素材`（fld87JUpEn）。")
r25["pattern"] = "图片素材"
r25["note"] = ("「正面和负面样本」表的素材附件字段（图片素材 attachment，fldnvxjaSr），归内部正负样本库。"
               "schema 漂移同步：" + RUN + "：`具体内容（截图/文案/OCR）` 已改名为 `图片素材`（**同一 field_id**），"
               "本规则随之迁移，保持这 77+240 条附件的历史归属口径连续。")
r25["continuity_note"] = ("field_id fldnvxjaSr 未变；旧字段名下 77 个附件由 R25 命中，"
                          "改名后 240 个附件仍由 R25 命中，口径连续、非重新判定。")

# ② 重跑求值
latest = {}
for l in open(f"{L0}/manifest.jsonl", encoding="utf-8"):
    if l.strip():
        d = json.loads(l); latest[d["resource_key"]] = d

targets = [k for k, v in latest.items()
           if v.get("source_kind") == "feishu_attachment" and v.get("table_id") == TBL
           and v.get("observed_at") == RUN and v["status"] == "registered"]
print("待重求值的本批附件:", len(targets))

# 一次性建索引，避免 240×1469 次重复扫盘
file_index = {}
for d in reg["dir_map"]:
    for p in glob.glob(f"{L0}/{d}/*.json"):
        try:
            file_index[json.load(open(p, encoding="utf-8"))["resource_key"]] = p
        except Exception:
            pass
print("库目录文件索引:", len(file_index))

rows, fixed_files = [], []
for k in targets:
    v = latest[k]
    fld = v.get("field_name")
    kt, rid, kts, tr = eval_rule(reg, TBL_NAME, field_name=fld, scope_table=TBL_NAME,
                                 excluded_tables=tuple(reg.get("excluded_scope", {}).get("tables", [])))
    if rid == v.get("matched_rule") and kt == v.get("kb_type"):
        continue
    row = {kk: v.get(kk) for kk in
           ("resource_key", "source_kind", "table_name", "table_id", "record_id", "field_name",
            "field_id", "entry_url", "path", "depth", "kb_type", "sha256", "sha256_input",
            "sha256_state", "revision", "dup_of")}
    row.update({"matched_rule": rid, "kb_type": kt, "kb_type_source": kts,
                "status": "updated", "status_reason": "rule_eval_corrected_after_schema_sync",
                "rule_eval_mode": "evaluated", "rule_eval_trace": tr["trace"],
                "prev_matched_rule": v.get("matched_rule"), "prev_kb_type_source": v.get("kb_type_source"),
                "fix_note": "批次内 schema 同步(件6)晚于登记(件5)，登记时 R17/R25 的 pattern 仍是旧字段名，"
                            "附件落到表级兜底 R26；本修正行按同步后的 registry 重跑求值。",
                "downstream_invalidated": True, "observed_at": FIX,
                "scanner_version": SCANNER_VERSION})
    rows.append(row)
    p = file_index.get(k)
    if p:
        j = json.load(open(p, encoding="utf-8"))
        j.update({"matched_rule": rid, "kb_type": kt, "kb_type_source": kts,
                  "observed_at": FIX, "scanner_version": SCANNER_VERSION})
        j.setdefault("extra", {})["rule_eval_corrected"] = {
            "at": FIX, "prev_matched_rule": v.get("matched_rule"),
            "note": "件6 schema 同步晚于件5 登记，此处按同步后的 registry 重求值"}
        with open(p, "w", encoding="utf-8") as fh:
            json.dump(j, fh, ensure_ascii=False, indent=2); fh.write("\n")
        fixed_files.append(p)

with open(f"{L0}/manifest.jsonl", "a", encoding="utf-8") as fh:
    for r in rows:
        fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")

# ③ registry 记录本次修正
reg["schema_snapshots"][-1]["rules_synced"] = {
    "R17": {"before": pattern_before["R17"], "after": "视频素材"},
    "R25": {"before": pattern_before["R25"], "after": "图片素材",
            "continuity": "field_id fldnvxjaSr 未变，R25 随字段改名迁移"}}
reg.setdefault("changes", []).append({
    "run_id": FIX, "change": "update", "keys": ["rules[R17].pattern", "rules[R25].pattern"],
    "note": "修正件6/件5 的执行顺序缺陷：schema 同步须先于登记。240 个附件的 matched_rule 由 R26 纠正为 R25。",
    "scanner_version": SCANNER_VERSION})
with open(f"{L0}/registry/kb.json", "w", encoding="utf-8") as fh:
    json.dump(reg, fh, ensure_ascii=False, indent=2); fh.write("\n")

# ④ index 重建
latest = {}
for l in open(f"{L0}/manifest.jsonl", encoding="utf-8"):
    if l.strip():
        d = json.loads(l); latest[d["resource_key"]] = d
live = {k: v for k, v in latest.items() if v["status"] not in ("gone", "retracted")}
with open(f"{L0}/index/l0.jsonl", "w", encoding="utf-8") as fh:
    for k in sorted(live):
        r = live[k]
        fh.write(json.dumps({"resource_key": r["resource_key"], "kb_type": r["kb_type"],
                             "source_kind": r["source_kind"], "status": r["status"],
                             "entry_url": r["entry_url"]}, ensure_ascii=False, sort_keys=True) + "\n")

json.dump({"at": FIX, "attachments_reevaluated": len(targets), "rows_corrected": len(rows),
           "files_refreshed": len(fixed_files),
           "matched_rule_after": dict(collections.Counter(r["matched_rule"] for r in rows)),
           "rules": {"R17": r17["pattern"], "R25": r25["pattern"]}},
          open("kb/.work/batch4/rulefix.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(json.dumps({"rows_corrected": len(rows), "files_refreshed": len(fixed_files),
                  "matched_rule_after": dict(collections.Counter(r["matched_rule"] for r in rows))},
                 ensure_ascii=False))
print("index 重建:", sum(1 for l in open(f"{L0}/index/l0.jsonl", encoding="utf-8") if l.strip()))
