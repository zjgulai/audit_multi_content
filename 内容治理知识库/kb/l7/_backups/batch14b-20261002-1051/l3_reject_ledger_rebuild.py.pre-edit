#!/usr/bin/env python3
"""L3 拒绝台账重建（事故修复 + 补全）。

事故：20260929-1300 我用 kb/l8/l3_distill_run.py 重跑 L3，脚本用 "w" 覆盖了
      kb/l3/rejected.jsonl —— 该文件此前被多个批次「追加」到 11,860 行（单元粒度），
      覆盖后只剩 1,053 行（资源粒度）。见 kb/l3/runs/20260929-1300.pre-snapshot.json
      记录了覆盖前的 bytes/lines/sha256。

修复：不伪造原行，而是**按同一判据重算一份更完整的账**：
      · 输入：kb/l2/units.jsonl（9,913）+ 现行规则（509，引用 959 单元）+ 现行样例（358，引用 3,204 单元）
      · 未被规则/样例引用的单元 → 逐单元记拒绝（带 unit_id，reason 按 kb_type/unit_type 派生）
      · 三类互斥：规则引用 / 样例引用 / 拒绝 = 9,913，可验证
      · 被覆盖后的 1,053 行资源粒度拒绝先归档，不动

产物：kb/l3/rejected.jsonl（追加重建行）、kb/l3/_archive/、kb/l3/runs/<RUN>-reject-rebuild.json
用法：python3 kb/l8/l3_reject_ledger_rebuild.py 20260929-1310 [--apply]
"""
# ── 解释器守卫（2026-09-29）：不合格就用 kb/.kb-python 指定的解释器重跑自己 ──
import os as _os, sys as _sys
if not _os.environ.get("KB_INTERP_OK"):
    _d = _os.path.dirname(_os.path.abspath(__file__)); _cfg = None
    while True:
        _p = _os.path.join(_d, ".kb-python")
        if _os.path.isfile(_p):
            _cfg = _p
            break
        _q = _os.path.dirname(_d)
        if _q == _d:
            break
        _d = _q
    if _cfg:
        _want = next((l.split("#", 1)[0].strip() for l in open(_cfg, encoding="utf-8")
                      if l.split("#", 1)[0].strip()), "")
        _want = _os.path.expanduser(_want)
        if (_want and _os.access(_want, _os.X_OK)
                and _os.path.realpath(_want) != _os.path.realpath(_sys.executable)):
            _os.environ["KB_INTERP_OK"] = "1"
            _os.execve(_want, [_want, _os.path.abspath(__file__)] + _sys.argv[1:], dict(_os.environ))
# ──────────────────────────────────────────────────────────────────────────

import collections
import hashlib
import json
import os
import shutil
import sys

RUN = sys.argv[1] if len(sys.argv) > 1 else "20260929-1310"
APPLY = "--apply" in sys.argv
CLOBBERED_AT = "20260929-1300"
L2, L3 = "kb/l2", "kb/l3"


def load(p):
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]


def ev_units(rows):
    s = set()
    for r in rows:
        for e in (r.get("evidence_units") or []):
            if isinstance(e, dict) and e.get("unit_id"):
                s.add(e["unit_id"])
        for k in ("unit_ids", "unit_id"):
            v = r.get(k)
            if isinstance(v, str):
                s.add(v)
            elif isinstance(v, list):
                s.update(x for x in v if isinstance(x, str))
    return s


units = load(f"{L2}/units.jsonl")
rules = load(f"{L3}/candidates/rules.jsonl")
cases = load(f"{L3}/candidates/sample_cases.jsonl") if os.path.exists(f"{L3}/candidates/sample_cases.jsonl") else []
RU, CU = ev_units(rules), ev_units(cases)
ALL = {u["unit_id"]: u for u in units}
rejected_units = [u for uid, u in ALL.items() if uid not in RU and uid not in CU]

REASON = {
    "sample": "纯文案样本：源表未给出命中判定或修订建议，无法产出可判定规则（sample_only_no_verdict）",
    "clause": "条款不可判定或已被同库其它条款覆盖，未产出「判定条件 + 阈值/词表」形态",
    "entry": "登记型字段值（元数据），不含可判定内容",
    "revision_pair": "修订对未构成「命中→替换」或「修订前→后」，或已作为对应规则的理由引用",
    "attribute": "属性型字段值（元数据），不含可判定内容",
}


def reason_of(u):
    kt = u.get("kb_type")
    ut = u.get("unit_type")
    txt = (u.get("text") or "")
    if kt == "external_standard" and ("<script" in txt.lower() or "base64" in txt.lower()):
        return ("条款文本不可判定：非自然语言条款（页面脚本 / base64 编码载荷），"
                "无法给出判定条件与阈值")
    if ut == "attribute":
        return "属性型字段值（元数据），不含可判定内容"
    return REASON.get(ut, "未产出可判定内容")

rows = []
for u in rejected_units:
    rows.append({
        "unit_id": u["unit_id"], "resource_id": u.get("resource_id"), "kb_type": u.get("kb_type"),
        "unit_type": u.get("unit_type"), "char_count": u.get("char_count"),
        "anchor": u.get("anchor"), "source_sha256": u.get("source_sha256"),
        "reason": reason_of(u), "kind": "unit_level",
        "rejected_at": RUN, "batch": RUN,
        "rebuild_note": f"重建行：原 {CLOBBERED_AT} 覆盖事故前的逐单元拒绝台账不可恢复，"
                        f"本行按同一判据从 kb/l2/units.jsonl 重算（非原始行）",
    })

# 三类互斥校验
inter1 = set(x["unit_id"] for x in rows) & RU
inter2 = set(x["unit_id"] for x in rows) & CU
cover = len(RU) + len(CU) + len(rows)
print(f"[重算] 单元 {len(ALL)} = 规则引用 {len(RU)} + 样例引用 {len(CU)} + 拒绝 {len(rows)} → {cover}")
print(f"       互斥校验：拒绝∩规则 {len(inter1)} | 拒绝∩样例 {len(inter2)}（都应为 0）")
print(f"       reason 分布：{dict(collections.Counter(r['reason'][:18] for r in rows).most_common(5))}")
assert cover == len(ALL) and not inter1 and not inter2

if not APPLY:
    print("\n未写入（加 --apply）")
    sys.exit(0)

# 1) 归档被覆盖后的现状
arch = f"{L3}/_archive/rejected-after-distill-{CLOBBERED_AT}"
os.makedirs(arch, exist_ok=True)
src = f"{L3}/rejected.jsonl"
shutil.copy2(src, f"{arch}/rejected.jsonl")
meta = {"archived": f"{arch}/rejected.jsonl", "from": src,
        "reason": f"{CLOBBERED_AT} L3 重建覆盖事故后的现状（1,053 行资源粒度）",
        "sha256": hashlib.sha256(open(src, "rb").read()).hexdigest(),
        "lines": sum(1 for _ in open(src, encoding="utf-8"))}
json.dump(meta, open(f"{arch}/_MANIFEST.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

# 2) 追加重建行
with open(src, "a", encoding="utf-8") as fh:
    for r in rows:
        fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")

after = sum(1 for _ in open(src, encoding="utf-8"))
rep = {"run": RUN, "layer": "l3", "kind": "incident_fix",
       "incident": {"at": CLOBBERED_AT, "file": src,
                    "before_lines": 11860, "before_sha256": None, "after_lines_before_fix": meta["lines"],
                    "cause": "l3_distill2.py 以 'w' 重建 L3；此前多批次以 'a' 追加的逐单元拒绝被覆盖",
                    "recoverable": False,
                    "searched": ["git（无仓库）", "APFS 本地快照（无）", "kb/.work 中间产物（无完整数组）",
                                 "kb/l8/_stage 与 ../_l8-sandbox-archive-20260923（无副本）",
                                 "~/.dsh/Momcozy知识库（符号链接，同一份）"]},
       "rebuild": {"method": "按同一判据从 kb/l2/units.jsonl 重算逐单元拒绝（非原始行，带 rebuild_note）",
                   "units": len(ALL), "rule_units": len(RU), "case_units": len(CU),
                   "rejected_rows_appended": len(rows), "partition_ok": True,
                   "lines_after": after},
       "unchanged_invariants": {"rules": len(rules),
                                "canonical_rules_bytes": os.path.getsize(f"{L3}/canonical/rules.jsonl")}}
json.dump(rep, open(f"{L3}/runs/{RUN}-reject-rebuild.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
# 补覆盖前 sha256 到快照引用
snap = f"{L3}/runs/{CLOBBERED_AT}.pre-snapshot.json"
if os.path.exists(snap):
    d = json.load(open(snap, encoding="utf-8"))
    rep["incident"]["before_sha256"] = (d["files"].get(src) or {}).get("sha256")
    json.dump(rep, open(f"{L3}/runs/{RUN}-reject-rebuild.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
print(f"[写入] rejected.jsonl {meta['lines']} → {after} 行（+{len(rows)}）")
print(f"       归档 kb/l3/_archive/rejected-after-distill-{CLOBBERED_AT}/")
print(f"       事故与重建记录 kb/l3/runs/{RUN}-reject-rebuild.json")
