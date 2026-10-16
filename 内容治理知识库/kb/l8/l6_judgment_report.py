#!/usr/bin/env python3
"""把 L6 自验的判定来源摊开报：人判 / 人判∪agent判 / 缺判（只读，不动任何文件）。

## 为什么要有这个（而不是改 l6_selftest.py）

`kb/.work/l6_selftest.py` 是既有自验，判定的唯一来源是 `kb/.work/l6_judgments_ab.json`
（2026-09-23 人工逐条给）。问题是：**判定是绑在 (查询, 单元) 上的**，
索引或检索一变（段数 2,630→2,774→4,192、依据优先权重上线），Top3 里冒出来的单元就换了人，
没判过的新单元 → 该查询算不出分 → 「已判定」从 14/14 掉到 5/14，仪表盘大半变空。

我没有直接改自验脚本（它在 kb/.work 里、被完整性闸门当既有件），
而是另写这个**只读报告器**，把三种读法并排摆出来，并显式报「缺判多少」：

    · 人判 only        —— 权威读法；覆盖少但不含我自己的判断
    · 人判 ∪ agent判   —— 刻度补满；**agent 那部分必须标注来源**，不能当人权使用
    · 缺判（gap）      —— 当前 Top3 里没有任何判定的槽位数；这是「仪表盘瞎了多少」

agent 判定放在单独文件（`kb/.work/l6_judgments_ab.agent-*.json`），**永不覆盖人判文件**。
新增/变更判定必须由人给；本报告器不给判定。

用法：
    python3 kb/l8/l6_judgment_report.py [RUN]        # 只读，打印并写报告
"""
import collections
import glob
import json
import os
import sys
import time

RUN = sys.argv[1] if len(sys.argv) > 1 else time.strftime("%Y%m%d-%H%M")
M = ["bm25_only", "vector_only", "hybrid"]
HUM = "kb/.work/l6_judgments_ab.json"
SEL = "kb/l6/selftest.json"

hum = json.load(open(HUM, encoding="utf-8")) if os.path.exists(HUM) else {}
agent = {}
agent_files = sorted(glob.glob("kb/.work/l6_judgments_ab.agent-*.json"))
for p in agent_files:
    d = json.load(open(p, encoding="utf-8"))
    for k, v in (d.get("verdicts") or {}).items():
        agent.setdefault(k, v)          # 先到的（较早批次）优先，不互相覆盖
sel = json.load(open(SEL, encoding="utf-8"))


def label(q, uid):
    v = (hum.get(q, {}).get("verdict") or {}).get(uid)
    if v:
        return v, "human"
    a = agent.get(f"{q}||{uid}")
    if a:
        return a["verdict"], "agent"
    return None, None


def read(use_agent):
    out = []
    for r in sel["results"]:
        per = {}
        for m in M:
            rel = known = 0
            srcs = set()
            for x in r["modes"][m]["top3"]:
                v, s = label(r["query"], x["unit_id"])
                if v is None or (s == "agent" and not use_agent):
                    continue
                known += 1
                srcs.add(s)
                if v == "相关":
                    rel += 1
            per[m] = {"rel": rel, "known": known, "p3": rel / 3,
                      "hit": (rel > 0) if known else None, "srcs": sorted(srcs)}
        out.append({"q": r["query"], "group": r["group"], "modes": per})
    return out


def summarise(rows):
    s = {}
    for g in ("A", "B"):
        pool = [x for x in rows if x["group"] == g]
        for m in M:
            j = [x for x in pool if x["modes"][m]["hit"] is not None]
            s[f"{g}|{m}"] = None if not j else {
                "n": len(j),
                "hit@3": round(sum(1 for x in j if x["modes"][m]["hit"]) / len(j), 3),
                "p@3": round(sum(x["modes"][m]["p3"] for x in j) / len(j), 3)}
    return s


human_rows, merged_rows = read(False), read(True)
sh, sm = summarise(human_rows), summarise(merged_rows)

# 缺口：当前 Top3 槽位里没有任何判定的数量（按模式、按组）
gap = collections.Counter()
gap_ids = collections.defaultdict(set)
for r in sel["results"]:
    for m in M:
        for x in r["modes"][m]["top3"]:
            v, _ = label(r["query"], x["unit_id"])
            if v is None:
                gap[(r["group"], m)] += 1
                gap_ids[r["query"]].add(x["unit_id"])
total_slots = sum(len(r["modes"][m]["top3"]) for r in sel["results"] for m in M)
gap_total = sum(gap.values())

print(f"[{RUN}] L6 自验判定来源报告（只读）")
print(f"  语料 {sel.get('query_count')} 条查询｜Top3 槽位 {total_slots} 个"
      f"｜人判文件 {len(hum)} 条查询｜agent 文件 {len(agent_files)} 份 / {len(agent)} 对")
print(f"\n{'组|模式':<18}{'人判 only':<24}{'人判 ∪ agent判':<24}")
for k in sorted(sh):
    def f(x):
        return "无可判" if x is None else f"n={x['n']} hit={x['hit@3']} p={x['p@3']}"
    print(f"{k:<18}{f(sh[k]):<24}{f(sm[k]):<24}")
print(f"\n缺判槽位：{gap_total}/{total_slots}"
      f"（其中 A 组 {sum(v for (g, _), v in gap.items() if g == 'A')}"
      f"｜B 组 {sum(v for (g, _), v in gap.items() if g == 'B')}）")
if gap_ids:
    print("  缺判最多的查询：")
    for q, ids in sorted(gap_ids.items(), key=lambda kv: -len(kv[1]))[:6]:
        print(f"    {q:<32}{len(ids)} 个单元待判")
print("\n注：agent 判定是我给的，**不是人权**；要采用需显式确认。人判 only 那一列才是权威读法。")

out = {"run_id": RUN, "kind": "l6_judgment_source_report",
       "query_count": sel.get("query_count"), "slots": total_slots,
       "human_summary": sh, "merged_summary": sm,
       "agent_files": agent_files, "agent_pairs": len(agent),
       "gap_slots": gap_total, "gap_by_group_mode": {f"{g}|{m}": v for (g, m), v in gap.items()},
       "gap_units_by_query": {q: sorted(v) for q, v in gap_ids.items()},
       "note": "人判 only = 权威读法；merged 里 agent 那部分来源不同，不可当人权使用"}
os.makedirs("kb/l6/runs", exist_ok=True)
json.dump(out, open(f"kb/l6/runs/{RUN}-judgment-sources.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print(f"\n[报告] kb/l6/runs/{RUN}-judgment-sources.json")
