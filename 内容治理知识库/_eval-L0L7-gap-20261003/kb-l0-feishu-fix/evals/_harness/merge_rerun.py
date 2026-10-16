#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把补跑结果并回正式归档（a-round-N{|b}.jsonl）。

为什么需要它、以及它**不是**什么：

  · 正式归档 = `_run-v130-120s/`（限时 120s 的 312 条全量），harness 根现在是它的副本；
  · 补跑 = `a-round-N.rerun.jsonl`（限时 420s，只跑**证据不足**那 79 条）；
  · 二者的**触发判定口径逐字相同**（只取 skill_loaded）；补跑改变的只是
    「空回复 / 证据不足」这一格 —— 即 Output 断言的输入，**不改触发结论**。

  ⇒ 合并后必须能回答：「哪一条被换掉了、换前是什么、换后是什么」。故本脚本只**替换**
    (round, n) 级记录，不重排、不增删，并把逐条处置写进 `merge-report.json`。

用法：
  python3 merge_rerun.py --dry-run     # 只看会换什么
  python3 merge_rerun.py               # 真合并（先自动备份到 _run-v130-120s.premerge/）
"""
import argparse
import glob
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ARCHIVE = os.path.join(HERE, "_run-v130-120s")
BACKUP = os.path.join(HERE, "_run-v130-120s.premerge")
FILES = [f"a-round-{n}{s}.jsonl" for n in (1, 2, 3) for s in ("", "b")]


def read_rows(p):
    rows = []
    with open(p, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def rerun_of(tag):
    """一轮的补跑记录：合并 .rerun.jsonl（按 n 去重，后写覆盖先写）。"""
    out = {}
    for p in glob.glob(os.path.join(HERE, f"a-round-{tag}.rerun.jsonl")):
        for r in read_rows(p):
            out[int(r["n"])] = r
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    changed, kept, untested = [], 0, []
    plan = {f: None for f in FILES}
    for f in FILES:
        # ⚠️ 这里**不能用 rstrip("b")**：`"1b".rstrip("b")` → `"1"`，于是 b 分片
        # （n=53–104，本来就轮不到补跑）会去匹配第一轮的补跑记录，把 n=99 这类
        # 同名 id 误当命中、并把真正的记录挡住。切分必须精确。
        body = f[len("a-round-"):-len(".jsonl")]
        is_b = body.endswith("b")
        tag = body[:-1] if is_b else body
        lo, hi = (53, 104) if is_b else (1, 52)
        src = os.path.join(ARCHIVE, f)
        if not os.path.exists(src):
            src = os.path.join(HERE, f)
        rows = read_rows(src)
        rr = rerun_of(tag)
        new, seen = [], set()
        for r in rows:
            n = int(r["n"])
            # 补跑记录只可能落在本分片的 id 区间内；区间外一律不碰。
            if lo <= n <= hi and n in rr:
                seen.add(n)
                old_has = bool((r.get("reply") or "").strip())
                new_has = bool((rr[n].get("reply") or "").strip())
                delta = ("空→有回复" if (not old_has and new_has)
                         else "仍无回复" if not new_has
                         else "替换（本来就有回复，取补跑版）")
                t_old, t_new = bool(r.get("skill_loaded")), bool(rr[n].get("skill_loaded"))
                changed.append({"file": f, "n": n, "delta": delta,
                                "triggered_before": t_old, "triggered_after": t_new,
                                "reply_chars_before": len(r.get("reply") or ""),
                                "reply_chars_after": len(rr[n].get("reply") or "")})
                if not new_has:
                    untested.append((f, n, t_new))
                new.append(rr[n])
            else:
                kept += 1
                new.append(r)
        plan[f] = new

    print(f"逐条处置 {len(changed)} 条（覆盖 {len(FILES)} 个归档文件）；未动 {kept} 条")
    print(f"其中补跑后**仍无回复**：{len(untested)} 条 {[ (f,n,t) for f,n,t in untested ]}")
    trig = [c for c in changed if c["triggered_before"] != c["triggered_after"]]
    print(f"触发结论发生变化的：{len(trig)} 条 {[(c['file'],c['n'],c['triggered_before'],c['triggered_after']) for c in trig]}")
    for c in changed[:10]:
        print(f"  {c['file']} n={c['n']:<4} {c['delta']:<22} "
              f"reply {c['reply_chars_before']}→{c['reply_chars_after']} 字  "
              f"loaded {c['triggered_before']}→{c['triggered_after']}")

    json.dump({"changed": changed, "untested": [{"file": f, "n": n, "triggered": t}
                                                for f, n, t in untested],
               "kept": kept, "trigger_flips": len(trig)},
              open(os.path.join(HERE, "merge-report.json"), "w"), ensure_ascii=False, indent=1)

    if a.dry_run:
        print("\n[dry-run] 未写盘。merge-report.json 已落盘供审。")
        return 0

    if not os.path.exists(BACKUP):
        os.makedirs(BACKUP)
        for f in FILES:
            p = os.path.join(ARCHIVE, f)
            if os.path.exists(p):
                shutil.copy2(p, os.path.join(BACKUP, f))
        print(f"[backup] 合并前归档已备份 → {BACKUP}")
    else:
        print(f"[backup] 已存在备份，未覆盖 → {BACKUP}")

    for f, rows in plan.items():
        if rows is None:
            continue
        dst = os.path.join(HERE, f)
        tmp = dst + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
        os.replace(tmp, dst)
        print(f"[write] {f}: {len(rows)} 条")
    print("\n完成。注意：**触发结论未变**（除非上面列了 trigger_flips）；"
          "变的是「空回复 → 有回复」，即 Output 断言的输入。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
