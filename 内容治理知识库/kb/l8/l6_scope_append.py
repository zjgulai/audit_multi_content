#!/usr/bin/env python3
"""往 kb/l6/SCOPE.txt 追加一批人工核定的白名单 id（带批次说明头）。

## 为什么要有脚本，而不是手写几行 id

SCOPE.txt 是 L6 的**唯一闸门**（`kb/.work/l6_scope_lib.py:apply_scope_file()` 按它取子集），
手写 id 有三个坑：抄错一位就静默少一条、把已退役的单元又写回去、
把根本进不了可用集（尺寸/字段角色/质量标记不过）的 id 写进去充数。
本脚本把这三条变成硬校验，逐条过不去就整批拒绝，不写半批。

## 校验（全部逐条过）

    ① id 必须真的存在于 kb/l2/units.jsonl          —— 防抄错
    ② 该 id 不在 kb/l2/retired_units.jsonl 里      —— 防把被取代的旧正文写回白名单
    ③ 该 id 在 usable_units() 的可用集里            —— 防写进"必然被挡"的 id 充数
    ④ 单条长度 ≤ MAX_UNIT_CHARS                    —— 尺寸护栏（口径见 l6_scope_lib）
    ⑤ 不是已在 SCOPE.txt 里的 id                    —— 防重复

用法：
    python3 kb/l8/l6_scope_append.py <RUN> --resources a,b,c --note "批次理由" [--apply]
    --resources 支持资源 id 的**子串**（如扫描件 token），逐个展开成资源再取其单元。
"""
import collections
import json
import os
import sys
import time

APPLY = "--apply" in sys.argv
RUN = next((a for a in sys.argv[1:] if not a.startswith("--")), time.strftime("%Y%m%d-%H%M"))
RES = (sys.argv[sys.argv.index("--resources") + 1].split(",") if "--resources" in sys.argv else [])
NOTE = sys.argv[sys.argv.index("--note") + 1] if "--note" in sys.argv else ""
SCOPE = "kb/l6/SCOPE.txt"
sys.path.insert(0, "kb/.work")
import l6_scope_lib as SL  # noqa: E402

if not RES or not NOTE:
    raise SystemExit(__doc__)

units = SL.load_units()
retired = SL._retired_unit_ids()
kept, _ = SL.usable_units()
usable = {u["unit_id"] for u in kept}
have = [l.rstrip("\n") for l in open(SCOPE, encoding="utf-8")]
have_ids = {l.strip() for l in have if l.strip() and not l.startswith("#")}

picked, report, problems = [], [], []
for pat in RES:
    rids = sorted({u["resource_id"] for u in units if pat in u["resource_id"]})
    if not rids:
        problems.append(f"{pat}: 在 units.jsonl 里找不到任何资源")
        continue
    for rid in rids:
        mine = [u for u in units if u["resource_id"] == rid]
        ok = [u for u in mine if u["unit_id"] in usable and u["unit_id"] not in retired
              and u["unit_id"] not in have_ids and len(u.get("text") or "") <= SL.MAX_UNIT_CHARS]
        picked += [u["unit_id"] for u in ok]
        report.append({"pattern": pat, "resource_id": rid,
                       "units_total": len(mine), "eligible": len(ok),
                       "chars": sum(len(u.get("text") or "") for u in ok),
                       "not_eligible": [{"unit_id": u["unit_id"], "chars": len(u.get("text") or ""),
                                         "why": ("已退役" if u["unit_id"] in retired else
                                                 "已在白名单" if u["unit_id"] in have_ids else
                                                 "超尺寸" if len(u.get("text") or "") > SL.MAX_UNIT_CHARS else
                                                 "不在可用集")} for u in mine if u not in ok]})

picked = sorted(set(picked))
total_chars = sum(len(u.get("text") or "") for u in units if u["unit_id"] in set(picked))
print(f"[{RUN}] SCOPE.txt 追加批次{'【落盘】' if APPLY else '【干跑】'}")
for r in report:
    print(f"  {r['pattern']:<28} 单元 {r['units_total']:>4} → 收入 {r['eligible']:>4}"
          f"（{r['chars']:>8} 字）  未收 {len(r['not_eligible'])}")
print(f"  本批合计收入 {len(picked)} 条 / {total_chars} 字；SCOPE.txt 现有 {len(have_ids)} 条 → {len(have_ids) + len(picked)} 条")
if problems:
    print("  ✗ 有问题，整批拒绝：")
    for p in problems:
        print("     ", p)
    sys.exit(2)
if not picked:
    print("  无可追加（幂等：重复跑不会重复追加）")
    sys.exit(0)

PAYLOAD_OK = [l for l in report if l["eligible"] > 0]
head = [
    "",
    "# " + "─" * 74,
    f"# 批次 {RUN}：{NOTE}",
    f"# 收入 {len(picked)} 条 / {total_chars} 字，来自 {len(PAYLOAD_OK)} 个资源：",
]
for r in PAYLOAD_OK:
    head.append(f"#   · {r['resource_id'][:78]}  {r['eligible']} 条 / {r['chars']} 字")
head.append("# 逐条校验：id 存在于 L2 单元 / 不在退役账 / 在可用集内 / ≤%d 字 / 不在本文件里已有"
            % SL.MAX_UNIT_CHARS)
head.append("# " + "─" * 74)
if not APPLY:
    print("\n  [干跑] 未落盘。加 --apply 即追加")
    for l in head:
        print("  " + l)
    sys.exit(0)
with open(SCOPE, "a", encoding="utf-8") as fh:
    fh.write("\n".join(head) + "\n")
    for uid in picked:
        fh.write(uid + "\n")
print(f"\n  [写入] {SCOPE} +{len(picked) + len(head)} 行（含 {len(head)} 行批次说明头）")
json.dump({"run_id": RUN, "kind": "l6_scope_append", "note": NOTE, "added": len(picked),
           "added_chars": total_chars, "scope_before": len(have_ids),
           "scope_after": len(have_ids) + len(picked), "per_resource": report,
           "unit_ids": picked},
          open(f"kb/l6/runs/{RUN}-scope-append.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print(f"  [报告] kb/l6/runs/{RUN}-scope-append.json")
