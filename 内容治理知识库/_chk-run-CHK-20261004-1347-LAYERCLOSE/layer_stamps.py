#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""逐层收口证据（只读）：逐份读 kb/l{0..6}/runs/*.json 的字段，不按文件名猜。
输出：每层最近 3 份落章 + 最近一次「真落盘」(applied=True 且 dry_run 不为 True)。"""
import json, os, glob, collections

ROOT = "/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理"
os.chdir(ROOT)


def truthy(v):
    return v is True or (isinstance(v, str) and v.strip().lower() in ("true", "yes", "1"))


def falsy(v):
    return v is False or (isinstance(v, str) and v.strip().lower() in ("false", "no", "0"))


def applied_of(doc):
    """返回 (applied, dry_run) —— 逐份读字段；缺失记 None。"""
    a = dr = None
    for k in ("applied", "write_applied", "written"):
        if k in doc:
            a = doc[k]
            break
    for k in ("dry_run", "dryrun", "is_dry_run"):
        if k in doc:
            dr = doc[k]
            break
    if a is None:
        wg = doc.get("write_gate")
        if isinstance(wg, dict) and "resolved" in wg:
            a = wg.get("resolved")
    return a, dr


print("逐层落章读数（只读；逐份读字段）")
print("=" * 78)
summary = {}
for L in [f"l{i}" for i in range(0, 7)]:
    files = glob.glob(f"kb/{L}/runs/*.json")
    rows = []
    for f in files:
        try:
            doc = json.load(open(f, encoding="utf-8"))
        except Exception as e:
            rows.append((0, f, None, None, f"PARSE_ERR {e}"))
            continue
        mt = os.path.getmtime(f)
        a, dr = applied_of(doc)
        rows.append((mt, f, a, dr, doc.get("run_id") or doc.get("run") or ""))
    rows.sort(reverse=True)
    real = [r for r in rows if truthy(r[2]) and not truthy(r[3])]
    summary[L] = real[0] if real else None
    print(f"\n--- {L}  ({len(files)} 份落章) ---")
    for mt, f, a, dr, rid in rows[:3]:
        import datetime
        ts = datetime.datetime.fromtimestamp(mt).strftime("%m-%d %H:%M:%S")
        print(f"  {ts}  applied={a!r:6} dry_run={dr!r:6} run={rid!r:24} {os.path.basename(f)}")
    if real:
        mt, f, a, dr, rid = real[0]
        import datetime
        ts = datetime.datetime.fromtimestamp(mt).strftime("%m-%d %H:%M:%S")
        print(f"  ★最近一次真落盘: {ts}  applied={a!r} dry_run={dr!r} run={rid!r}  {f}")
    else:
        print("  ★最近一次真落盘: 无（runs/ 里没有任何 applied=True 且非 dry_run 的落章）")

print("\n" + "=" * 78)
print("汇总（最近一次真落盘 = applied=True 且 dry_run 非 True）")
for L, r in summary.items():
    if r:
        import datetime
        ts = datetime.datetime.fromtimestamp(r[0]).strftime("%Y-%m-%d %H:%M:%S")
        print(f"  {L}: {ts}  run={r[4]!r}  {os.path.basename(r[1])}")
    else:
        print(f"  {L}: 无")

# 各层 runs 目录里最近一次落章（不论是否真落盘）
print("\n各层 runs/ 最新一份落章（不论真落盘与否）")
for L in [f"l{i}" for i in range(0, 7)]:
    files = glob.glob(f"kb/{L}/runs/*.json")
    if not files:
        print(f"  {L}: (无)")
        continue
    f = max(files, key=os.path.getmtime)
    import datetime
    ts = datetime.datetime.fromtimestamp(os.path.getmtime(f)).strftime("%Y-%m-%d %H:%M:%S")
    print(f"  {L}: {ts}  {os.path.basename(f)}")
