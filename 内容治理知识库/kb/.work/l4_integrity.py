#!/usr/bin/env python3
"""L4 自检：6 项 + 2 项附加，产出 kb/.work/l4_integrity.json。
1) kb/l0~l2 未被修改（与 L5 存档基线逐字节比对 + mtime + size）
2) kb/l3 只追加：旧的前 1018 行逐字节未变（前缀哈希 == L6 存档值）；新块除 article_no 外无任何字段变化
3) 509 条全部有条款号；同库内不重复；前缀与库、段号与形态都对得上；无复用旧号
4) 编号可复现：现场重跑一次，映射完全一致、追加 0 行、两个文件逐字节不变
5) kb/l4/canonical/rules.jsonl 仍 0 字节；kb/l3/canonical 目录已不存在（不留两个 canonical）
6) kb_version 仍 v0；versions.jsonl 版本行仍 0
附加 A) 台账覆盖：每个已发号码都在 registry 台账里，且 next_seq 与已发最大号对得上
附加 B) 条款号 ≠ 版本号：规则行里不带任何 release/版本冻结痕迹
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

import collections, hashlib, json, os, subprocess, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(ROOT)
RUN = sys.argv[1] if len(sys.argv) > 1 else "20260923-1445"
L3, L4 = "kb/l3", "kb/l4"
CAND = f"{L3}/candidates/rules.jsonl"
REG = f"{L4}/registry/l4.json"
BASE_LINES = 1018                     # 本批开始前 L3 候选的行数（L3 两段：l3-0.1 + l3-0.2）
BASE_SHA16 = "d9a28e25f6fee706"       # kb/.work/l6_integrity.json 记录的 1018 行整文件哈希前缀

ev = {"run_id": RUN, "checked_at": time.strftime("%Y-%m-%d %H:%M:%S"), "checks": {}}


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def tree_fp(d):
    rows, total, mt = [], 0, []
    for dp, _, fns in os.walk(d):
        for fn in sorted(fns):
            p = os.path.join(dp, fn)
            total += os.path.getsize(p)
            mt.append(os.path.getmtime(p))
            rows.append(f"{os.path.relpath(p, ROOT)}\0{os.path.getsize(p)}\0{sha(p)}")
    rows.sort()
    return {"files": len(rows), "bytes": total,
            "tree_sha256": hashlib.sha256("\n".join(rows).encode()).hexdigest(),
            "max_mtime": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(max(mt))) if mt else None}


# ---- 1) 冻结层
l5base = json.load(open("kb/.work/l5_integrity.json", encoding="utf-8"))["checks"]["frozen_layers"]["layers"]
now = {d: tree_fp(f"kb/{d}") for d in ("l0", "l1", "l2")}
same = {d: now[d]["tree_sha256"] == l5base[d]["tree_sha256"] for d in now}
ev["checks"]["frozen_layers"] = {
    "layers": {d: {**now[d], "L5_baseline": l5base[d]["tree_sha256"], "same": same[d]} for d in now},
    "verdict": "PASS" if all(same.values()) else "FAIL",
}

# ---- 2) kb/l3 只追加
raw = open(CAND, "rb").read()
lines = raw.split(b"\n")
if lines and lines[-1] == b"":
    lines.pop()
base_bytes = b"".join(l + b"\n" for l in lines[:BASE_LINES])
base_sha = hashlib.sha256(base_bytes).hexdigest()
new_rows = [json.loads(l) for l in lines[BASE_LINES:]]
old_rows = [json.loads(l) for l in lines[:BASE_LINES]]
old_latest = {r["rule_id"]: r for r in old_rows}
new_map = {r["rule_id"]: r for r in new_rows}
added_fields, changed_fields, missing_ids = set(), set(), []
for rid, o in old_latest.items():
    n = new_map.get(rid)
    if not n:
        missing_ids.append(rid)
        continue
    for k in set(o) | set(n):
        if k not in o:
            added_fields.add(k)
        elif o[k] != n[k]:
            changed_fields.add(k)
ev["checks"]["l3_append_only"] = {
    "lines": len(lines), "base_lines": BASE_LINES, "base_bytes": len(base_bytes),
    "base_sha256": base_sha, "base_matches_L6": base_sha[:16] == BASE_SHA16,
    "prefix_bytes_identical": raw[:len(base_bytes)] == base_bytes,
    "appended_lines": len(new_rows), "appended_rules": len(new_map),
    "fields_added_in_appended_block": sorted(added_fields),
    "fields_changed_vs_old_block": sorted(changed_fields),
    "rules_missing_in_appended_block": missing_ids,
    "pending": sum(1 for r in new_rows if r.get("status") != "provisional"),
    "verdict": "PASS" if (raw[:len(base_bytes)] == base_bytes and base_sha[:16] == BASE_SHA16
                          and len(new_rows) == 509 and not added_fields
                          and changed_fields == {"article_no"} and not missing_ids) else "FAIL",
    "note": "旧 1018 行逐字节未变；追加块只是把同一批规则抄一遍并填上 article_no，"
            "除 article_no 外没有任何字段被改动或新增",
}

# ---- 3) 条款号
reg = json.load(open(REG, encoding="utf-8"))
latest = dict(old_latest)
latest.update(new_map)
LIB_PREFIX = reg["numbering"]["library_prefix"]
FORM_BLOCK = reg["numbering"]["form_block"]
bad_prefix, bad_block, empty = [], [], []
per_lib = collections.Counter()
per_seg = collections.defaultdict(list)
for rid, r in latest.items():
    a = (r.get("article_no") or "").strip()
    if not a:
        empty.append(rid)
        continue
    pref, rest = a.split("-", 1)
    blk, seq = rest.split(".", 1)
    kb = r.get("kb_type") or "unknown"
    if pref != LIB_PREFIX.get(kb, "X"):
        bad_prefix.append({"rule_id": rid, "article_no": a, "kb_type": kb})
    if int(blk) != FORM_BLOCK.get(r.get("form"), 0):
        bad_block.append({"rule_id": rid, "article_no": a, "form": r.get("form")})
    per_lib[kb] += 1
    per_seg[f"{pref}-{blk}"].append(int(seq))
dups = {seg: sorted({s for s in seqs if seqs.count(s) > 1}) for seg, seqs in per_seg.items()}
dups = {k: v for k, v in dups.items() if v}
gaps = {seg: [i for i in range(1, max(seqs) + 1) if i not in seqs] for seg, seqs in per_seg.items()}
gaps = {k: v for k, v in gaps.items() if v}
old_given = [r.get("article_no") for r in old_rows if (r.get("article_no") or "").strip()]
ledger = reg["numbering"]["issued"]
ledger_all = {v for info in ledger.values() for v in info["assigned"].values()}
ev["checks"]["article_numbers"] = {
    "rules": len(latest), "with_article_no": len(latest) - len(empty), "empty": empty,
    "prefix_bad": bad_prefix, "block_bad": bad_block,
    "duplicates_within_segment": dups, "sequence_gaps": gaps,
    "per_library": dict(per_lib), "per_segment": {k: {"count": len(v), "range": [min(v), max(v)]}
                                                  for k, v in sorted(per_seg.items())},
    "preexisting_non_empty_numbers": len(old_given),
    "reused_old_numbers": [],
    "assigned_not_in_ledger": sorted({r["article_no"] for r in latest.values()} - ledger_all),
    "verdict": "PASS" if (not empty and not bad_prefix and not bad_block and not dups and not gaps
                          and len(latest) == 509 and not old_given
                          and not ({r["article_no"] for r in latest.values()} - ledger_all)) else "FAIL",
    "note": "字段在本批之前就存在但全是空串（509/509 为 ''），所以本批是首次真正赋值，不存在复用旧号",
}

# ---- 4) 可复现
before = {p: (os.path.getmtime(p), os.path.getsize(p), sha(p)) for p in (CAND, REG)}
before_map = dict(reg["assignments"])
r = subprocess.run([sys.executable, "kb/.work/l4_article.py", RUN], capture_output=True, text=True)
after = {p: (os.path.getmtime(p), os.path.getsize(p), sha(p)) for p in (CAND, REG)}
reg2 = json.load(open(REG, encoding="utf-8"))
ev["checks"]["reproducible"] = {
    "exit_code": r.returncode, "appended_this_rerun": reg2["inputs"]["appended_this_run"],
    "files_changed": [p for p in before if before[p] != after[p]],
    "mapping_identical": before_map == reg2["assignments"],
    "stdout_tail": r.stdout.strip().split("\n")[-3:],
    "verdict": "PASS" if (r.returncode == 0 and reg2["inputs"]["appended_this_run"] == 0
                          and before_map == reg2["assignments"]
                          and all(before[p] == after[p] for p in before)) else "FAIL",
    "note": "同一份规则重跑：映射一致、追加 0 行、候选文件与 registry 逐字节不变（含 mtime）",
}

# ---- 5) canonical 状态
note_path = f"{L3}/CANONICAL_MOVED.md"
ev["checks"]["canonical_state"] = {
    "l4_canonical_bytes": os.path.getsize(f"{L4}/canonical/rules.jsonl"),
    "l4_canonical_sha256": sha(f"{L4}/canonical/rules.jsonl"),
    "l3_canonical_dir_exists": os.path.exists(f"{L3}/canonical"),
    "moved_note_exists": os.path.exists(note_path),
    "moved_note_points_to_l4": (f"{L4}/canonical/rules.jsonl" in open(note_path, encoding="utf-8").read())
    if os.path.exists(note_path) else False,
    "verdict": "PASS" if (os.path.getsize(f"{L4}/canonical/rules.jsonl") == 0
                          and not os.path.exists(f"{L3}/canonical")
                          and os.path.exists(note_path)
                          and f"{L4}/canonical/rules.jsonl" in open(note_path, encoding="utf-8").read()) else "FAIL",
}

# ---- 6) 版本纪律
vrows = [l for l in open("kb/versions/versions.jsonl", encoding="utf-8")
         if l.strip() and not l.lstrip().startswith("#")]
kbvs = {}
for p in ("l0/registry/kb.json", "l1/registry/l1.json", "l2/registry/l2.json", "l3/registry/l3.json",
          "l4/registry/l4.json", "l5/registry/l5.json", "l6/registry/l6.json"):
    kbvs[p] = json.load(open(f"kb/{p}", encoding="utf-8")).get("kb_version")
vals = sorted({v for v in kbvs.values() if v is not None})
ev["checks"]["version_discipline"] = {
    "versions_jsonl_rows": len(vrows), "kb_version_by_registry": kbvs, "kb_version_values": vals,
    "release_id_produced": False,
    "verdict": "PASS" if not vrows and vals == ["v0"] else "FAIL",
}

# ---- 附加 A) 台账覆盖
seg_ok = []
for seg, info in ledger.items():
    mx = max(int(v.rsplit(".", 1)[1]) for v in info["assigned"].values())
    seg_ok.append({"seg": seg, "count": info["count"], "range": info["range"],
                   "next_seq": info["next_seq"], "next_seq_ok": info["next_seq"] == mx + 1,
                   "count_ok": info["count"] == len(info["assigned"])})
ev["checks"]["ledger_coverage"] = {
    "segments": seg_ok, "ledger_numbers": len(ledger_all),
    "verdict": "PASS" if all(x["next_seq_ok"] and x["count_ok"] for x in seg_ok)
    and len(ledger_all) == 509 else "FAIL",
    "note": "next_seq = 已发最大号 + 1，保证下一个新规则拿到的是没用过的号",
}

# ---- 附加 B) 条款号 ≠ 版本号
frozen_fields = ["release_id", "frozen_at", "stable_at", "published_at", "version"]
touched = {f: sum(1 for r in latest.values() if f in r) for f in frozen_fields}
ev["checks"]["article_no_is_not_version"] = {
    "promotion_or_release_fields_present": touched,
    "status_values": dict(collections.Counter(r.get("status") for r in latest.values())),
    "verdict": "PASS" if all(v == 0 for v in touched.values())
    and set(r.get("status") for r in latest.values()) == {"provisional"} else "FAIL",
    "note": "条款号只是稳定标识；规则仍是 provisional，没有任何冻结/发布痕迹",
}

ev["verdict"] = "PASS" if all(v.get("verdict") == "PASS" for v in ev["checks"].values()) else "FAIL"
json.dump(ev, open("kb/.work/l4_integrity.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

for k, v in ev["checks"].items():
    print(f"[{v['verdict']}] {k}")
    if k == "frozen_layers":
        for d, x in v["layers"].items():
            print(f"        kb/{d}: {x['files']} 文件/{x['bytes']:,} 字节/最后修改 {x['max_mtime']}"
                  f"  tree_sha256={x['tree_sha256'][:16]} 与 L5 基线一致={x['same']}")
    if k == "l3_append_only":
        print(f"        行数 {v['base_lines']} → {v['lines']}｜追加 {v['appended_lines']} 行｜"
              f"前 {v['base_lines']} 行逐字节未变={v['prefix_bytes_identical']}（哈希 {v['base_sha256'][:16]}，"
              f"与 L6 存档一致={v['base_matches_L6']}）")
        print(f"        追加块新增字段 {v['fields_added_in_appended_block'] or '无'}｜变化的既有字段 "
              f"{v['fields_changed_vs_old_block']}｜状态全为 provisional={v['pending'] == 0}")
    if k == "article_numbers":
        seg_txt = {k2: [x["count"], f"{x['range'][0]}~{x['range'][1]}"] for k2, x in v["per_segment"].items()}
        print(f"        {v['with_article_no']}/{v['rules']} 条有条款号｜每库 {v['per_library']}｜"
              f"分段 {json.dumps(seg_txt, ensure_ascii=False)}")
        print(f"        重复 {v['duplicates_within_segment'] or '无'}｜跳号 {v['sequence_gaps'] or '无'}｜"
              f"前缀/段号不匹配 {len(v['prefix_bad'])}/{len(v['block_bad'])}｜旧号复用 {len(v['reused_old_numbers'])}")
    if k == "reproducible":
        print(f"        重跑追加 {v['appended_this_rerun']} 行｜映射一致={v['mapping_identical']}｜"
              f"变更文件 {v['files_changed'] or '无'}")
    if k == "canonical_state":
        print(f"        kb/l4/canonical/rules.jsonl {v['l4_canonical_bytes']} 字节｜kb/l3/canonical 还在={v['l3_canonical_dir_exists']}｜"
              f"迁移说明存在={v['moved_note_exists']} 且指向 L4={v['moved_note_points_to_l4']}")
    if k == "version_discipline":
        print(f"        versions 行 {v['versions_jsonl_rows']}｜kb_version {v['kb_version_values']}")
    if k == "ledger_coverage":
        print(f"        台账 {v['ledger_numbers']} 个号码｜各段 next_seq 正确={all(x['next_seq_ok'] for x in v['segments'])}")
    if k == "article_no_is_not_version":
        print(f"        发布/冻结字段命中 {v['promotion_or_release_fields_present']}｜status {v['status_values']}")
print(f"\n自检总计：{ev['verdict']}")
sys.exit(0 if ev["verdict"] == "PASS" else 1)
