#!/usr/bin/env python3
"""第 7/8/9/10 项修正：
7) empty 与 failed 分开：结构资源改 status=no_content_expected（L1 文件 + 台账追加）
8) runs/<run_id>.json 增加 source_revision_* 三字段
9) registry 追加「锚点必须同时给 source_sha256」规范
10) 三个 scope 可用性检查；不可用则标 scope_missing 且不重试
"""
import json, os, re, glob, hashlib, collections, subprocess, sys
from datetime import datetime

RUN = sys.argv[1]
L0, L1 = "kb/l0", "kb/l1"
ENV = dict(os.environ, PATH=os.path.expanduser("~/.dsh/bin") + ":" + os.environ.get("PATH", ""))
BASE, ENTRY_TBL = "GnRZbIuXraCzf0sGr2UcmZ62nfc", "tblMGtPfe8ZUsEdP"
RULES = "id|title|type|sha256|anchor|artifact"

# ============================================================ 7) 状态拆分
targets = []
for d in ["1_外部标准库", "2_内部正负样本库", "3_措辞表达库", "4_产品描述库", "9_未归类"]:
    for p in glob.glob(f"{L1}/{d}/*.json"):
        o = json.load(open(p, encoding="utf-8"))
        if o.get("status") == "empty" and o.get("source_kind") in ("feishu_bitable_table", "feishu_bitable_base"):
            targets.append((p, o))
print(f"[7] 待改为 no_content_expected 的资源：{len(targets)} 条")
changed = []
MANP = f"{L1}/manifest_l1.jsonl"
for p, o in targets:
    old = o["status"]
    o["status"] = "no_content_expected"
    o["status_reason"] = ("结构资源（表/Base）本来就没有正文：字段名与选项属于 L0 结构指纹的职责，"
                          "L1 不把 schema 重复抽成内容，故不是失败")
    o["status_changed_by"] = RUN
    o["status_history"] = [*o.get("status_history", []),
                           {"run_id": RUN, "from": old, "to": "no_content_expected",
                            "reason": "empty 与 failed 分开计数：本来就无正文不算失败"}]
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(o, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    changed.append({"resource_id": o["resource_id"], "from": old, "to": "no_content_expected",
                    "source_kind": o["source_kind"], "kb_type": o["kb_type"]})
    with open(MANP, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"resource_id": o["resource_id"], "resource_key": o.get("resource_key"),
                             "kb_type": o["kb_type"], "source_kind": o["source_kind"],
                             "source_sha256": o.get("source_sha256"),
                             "extractor_version": o["extractor_version"],
                             "status": "no_content_expected", "status_reason": o["status_reason"],
                             "segment_count": o["segment_count"], "table_count": o["table_count"],
                             "media_count": o.get("media_count", 0), "char_count": o["char_count"],
                             "observed_at": RUN}, ensure_ascii=False, sort_keys=True) + "\n")

# 修正后的真实失败率
man_latest = {}
for line in open(MANP, encoding="utf-8"):
    if line.strip():
        r = json.loads(line)
        man_latest[r["resource_id"]] = r
st = collections.Counter(r["status"] for r in man_latest.values())
total_units = len(man_latest) - st.get("retracted", 0)
no_content = st.get("no_content_expected", 0)
pending = st.get("pending_ocr", 0) + st.get("pending_transcribe", 0)
failed = st.get("no_scope", 0) + st.get("forbidden", 0) + st.get("unreachable", 0)
attemptable = total_units - no_content - pending
real_fail_rate = failed / attemptable * 100 if attemptable else 0
print(f"[7] 状态分布: {dict(st)}")
print(f"[7] 真实失败率 = {failed}/{attemptable} = {real_fail_rate:.1f}%")

# ============================================================ 8) run 快照 source_revision_*
def src_rev():
    try:
        p = subprocess.run(["lark-cli", "base", "+table-list", "--base-token", BASE],
                           capture_output=True, text=True, env=ENV, timeout=120)
        d = json.loads(p.stdout)
        if d.get("ok"):
            return {t["name"]: t.get("rev") for t in d["data"]["tables"]}
    except Exception as e:
        return {"error": str(e)[:120]}
    return {}

rev_end = src_rev()
print(f"[8] 源 revision（本次结束）: {rev_end}")

RUNS = {
    "20260923-1055": {"rev_start": {"材料收集": 177, "知识库分类说明": 7, "正面和负面样本": 369, "规则库": 6},
                      "rev_used": {"材料收集": 177, "知识库分类说明": 7, "正面和负面样本": 369, "规则库": 6},
                      "note": "首次落库；快照取自 177"},
    "20260923-1117": {"rev_start": {"材料收集": 177, "知识库分类说明": 7, "正面和负面样本": 369, "规则库": 6},
                      "rev_used": {"材料收集": 181, "知识库分类说明": 7, "正面和负面样本": 369, "规则库": 6},
                      "note": "重跑落库；执行中发现材料收集 rev 由 177→181（recvw0o2T6HJwv 补填并通过），按最新状态整体重跑"},
    "20260923-1140": {"rev_start": {"材料收集": 181, "知识库分类说明": 7, "正面和负面样本": 369, "规则库": 6},
                      "rev_used": {"材料收集": 181, "知识库分类说明": 7, "正面和负面样本": 369, "规则库": 6},
                      "note": "L1 首次抽取"},
    "20260923-1215": {"rev_start": {"材料收集": 181, "知识库分类说明": 7, "正面和负面样本": 369, "规则库": 6},
                      "rev_used": {"材料收集": 181, "知识库分类说明": 7, "正面和负面样本": 369, "规则库": 6},
                      "note": "L0 补充登记（正面和负面样本）+ L1 重挂靠"},
    RUN: {"rev_start": rev_end, "rev_used": rev_end, "note": "本轮诊断+补齐；revision 字段自本次起生效"},
}
touched = []
for rid, meta in RUNS.items():
    for p in (f"{L0}/runs/{rid}.json", f"{L1}/runs/{rid}.json"):
        if not os.path.exists(p):
            continue
        d = json.load(open(p, encoding="utf-8"))
        d["source_revision_start"] = meta["rev_start"]
        d["source_revision_end"] = rev_end if rid == RUN else meta["rev_used"]
        d["source_revision_used"] = meta["rev_used"]
        d["source_revision_note"] = meta["note"]
        with open(p, "w", encoding="utf-8") as fh:
            json.dump(d, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        touched.append(p)
print(f"[8] 已写入 revision 字段的运行快照：{len(touched)} 个")
for t in touched:
    print("   ", t)

# ============================================================ 9) 锚点 ↔ sha256 绑定规范（只追加新键）
ANCHOR_BINDING_L0 = {
    "rule": "引用锚点时必须同时给出 source_sha256；只有锚点不算完整定位。",
    "why": "锚点（行号 / 标题路径 / #img.N）会随原文编辑而漂移；sha256 指向被锚定的那一版原文。"
           "锚点 + source_sha256 才是可复核的定位。",
    "applies_to": "L1 及下游（结构化切分、蒸馏）的一切引用",
    "required_pair": ["anchor", "source_sha256"],
    "artifact_lookup": "kb/l0/snapshots/<resource_key>@<sha256>.md（正文快照按 sha256 版本并存）",
    "on_mismatch": "锚点在当前正文中定位不到 → 视为失效引用，不得静默改写锚点；"
                   "应回到该 sha256 的快照核对，或重新抽取生成新版本。",
    "since": RUN,
}
reg = json.load(open(f"{L0}/registry/kb.json", encoding="utf-8"))
if "anchor_sha256_binding" not in reg:
    reg["anchor_sha256_binding"] = ANCHOR_BINDING_L0
    reg.setdefault("changes", []).append({"run_id": RUN, "change": "append",
                                          "key": "anchor_sha256_binding",
                                          "note": "仅追加新键，未修改任何既有键"})
    with open(f"{L0}/registry/kb.json", "w", encoding="utf-8") as fh:
        json.dump(reg, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    print("[9] kb/l0/registry/kb.json 追加 anchor_sha256_binding")

l1reg_p = f"{L1}/registry/l1.json"
l1reg = json.load(open(l1reg_p, encoding="utf-8"))
l1reg["anchor_sha256_binding"] = {
    **ANCHOR_BINDING_L0,
    "enforced_in": "kb/l1/index/l1.jsonl（每行可由此 join 到所属资源的 source_sha256）",
    "index_join": "index 行的 resource_id → 产物 json 的 source_sha256 → 快照文件",
}
if "anchor_sha256_binding" not in json.load(open(l1reg_p, encoding="utf-8")):
    with open(l1reg_p, "w", encoding="utf-8") as fh:
        json.dump(l1reg, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    print("[9] kb/l1/registry/l1.json 写入 anchor_sha256_binding")

# index 增加 source_sha256 列（使其可 join）
idx_p = f"{L1}/index/l1.jsonl"
prod = {}
for d in ["1_外部标准库", "2_内部正负样本库", "3_措辞表达库", "4_产品描述库", "9_未归类"]:
    for p in glob.glob(f"{L1}/{d}/*.json"):
        o = json.load(open(p, encoding="utf-8"))
        prod[o["resource_id"]] = o
n = 0
with open(idx_p, "w", encoding="utf-8") as fh:
    for d in ["1_外部标准库", "2_内部正负样本库", "3_措辞表达库", "4_产品描述库", "9_未归类"]:
        for p in sorted(glob.glob(f"{L1}/{d}/*.json")):
            o = json.load(open(p, encoding="utf-8"))
            si = 0
            for s in o["segments"]:
                si += 1
                fh.write(json.dumps({"seg_id": f"{o['resource_id']}#s{si}", "resource_id": o["resource_id"],
                                     "kb_type": o["kb_type"], "kind": s["kind"], "anchor": s["anchor"],
                                     "source_sha256": o.get("source_sha256"),
                                     "char_count": len(s["text"])}, ensure_ascii=False, sort_keys=True) + "\n")
                n += 1
            for t in o["tables"]:
                for rw in t["rows"]:
                    si += 1
                    fh.write(json.dumps({"seg_id": f"{o['resource_id']}#t{t['table_index']}r{rw['row_index']}",
                                         "resource_id": o["resource_id"], "kb_type": o["kb_type"],
                                         "kind": "table_row", "anchor": rw["anchor"],
                                         "source_sha256": o.get("source_sha256"),
                                         "char_count": len(rw["text"])}, ensure_ascii=False, sort_keys=True) + "\n")
                    n += 1
print(f"[9] index/l1.jsonl 重建，增加 source_sha256 列，共 {n} 行")

# ============================================================ 10) scope 检查
probe = {}
checks = [
    ("sheets", ["lark-cli", "sheets", "+workbook-info", "--url",
                "https://momcozy-in.feishu.cn/sheets/BX0QshqWThhY6HtDEFCcnMpsnRc"], "sheets:spreadsheet:read"),
    ("slides", ["lark-cli", "slides", "+xml-get", "--presentation",
                "https://momcozy-in.feishu.cn/slides/LDIIsI5SIl4ZumdW8XgcUIn8nTg"], "slides:presentation:read"),
    ("drive_download", ["lark-cli", "drive", "+download", "--file-token",
                        "T1tNbhPnmoq8gAxj4MZcHmX6nUc", "--output", "kb/.work/_scope_probe.bin"], "drive:file:download"),
]
for name, cmd, scope in checks:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, env=ENV, timeout=120)
        raw = p.stdout.strip()
        d = json.loads(raw[raw.index("{"):]) if "{" in raw else {}
        ok = d.get("ok", False)
        err = d.get("error", {})
        probe[name] = {"scope": scope, "available": ok, "error_subtype": err.get("subtype"),
                       "message": (err.get("message") or "")[:140]}
    except Exception as e:
        probe[name] = {"scope": scope, "available": False, "error_subtype": "probe_error", "message": str(e)[:140]}
for k, v in probe.items():
    print(f"[10] {k:16s} {v['scope']:28s} available={v['available']} {v.get('error_subtype') or ''}")

no_scope_res = [o for o in prod.values() if o.get("status") == "no_scope"]
scope_missing = [o["resource_id"] for o in no_scope_res]
need = sorted({probe[k]["scope"] for k in ("sheets", "slides", "drive_download") if not probe[k]["available"]})
any_available = any(probe[k]["available"] for k in probe)
print(f"[10] no_scope 资源 {len(no_scope_res)} 条；可用 scope 数 {sum(1 for k in probe if probe[k]['available'])}/3")
print(f"[10] 结论：{'可重抽（部分或全部）' if any_available else 'scope 仍缺失 → 标 scope_missing，不重试'}")

if os.path.exists("kb/.work/_scope_probe.bin"):
    os.remove("kb/.work/_scope_probe.bin")

json.dump({"status_split": {"changed": changed, "manifest_appended": len(changed),
                            "status_distribution": dict(st), "total_units": total_units,
                            "no_content_expected": no_content, "pending": pending, "failed": failed,
                            "attemptable": attemptable, "real_fail_rate_pct": round(real_fail_rate, 2)},
           "revision": {"rev_end": rev_end, "touched": touched, "runs": RUNS},
           "anchor_binding": ANCHOR_BINDING_L0, "index_rows": n,
           "scope": {"probe": probe, "scope_missing": scope_missing, "any_available": any_available,
                     "needed": need, "action": "re-extract" if any_available else "scope_missing_no_retry"}},
          open("kb/.work/fix_part2.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("第二部分修正数据已写出")
