#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""修上游 l3 `suggested_replacement` 的超长拼接 blob（③b）。

真实根因（2026-09-23 实测，逐层回溯）：
  1) 源表「广告文案明细」的 `修改建议` 单元格**本身就常常是多段建议用 ` ▸ ` 拼接**，
     且**首段未必对应该记录命中的片段**。例：记录 recvuJYdOb1u94 命中片段是
     `schmerzfrei`，而它的 `修改建议` = 「效果百分比/销量/评分声称需附测试来源与口径… ▸
     删除 pain-free/… 疼痛功效承诺…」—— 首段讲的是效果百分比，与命中片段无关。
     （已核对 l2/by_kb/3_措辞表达库/bitable__Lk3Qb8y2QaVyZns6gprcVNE9nA0__recvuJYdOb1u94.json
      的 `#广告文案明细/recvuJYdOb1u94/修改建议` 单元，确认不是 l3 二次加工出来的。）
  2) l3 蒸馏（`kb/.work/l3_distill2.py`）在同一个 rule_code 桶里，把**最多 8 条记录**的
     `修改建议` 用 `；` 串成一个 `suggested_replacement`：
     `"；".join(f"「{fr}」→ 删除/替换为：{fx}" for fr, fx in pair_pairs[:8])`。
     于是每个片段都被挂上「一长串、且首段常常错位」的建议 → 最长 2945 字符，
     39 条规则 > 500 字符。
  3) 结果是读取侧拿到「片段 A → 属于 B 的建议」。review.py 已加**同源检查**在运行时拦掉，
     但数据层仍是脏的（工作台/其它消费者看到的就是这条 blob）。

本脚本的修法（只改 `suggested_replacement` 一个字段，不动分层、不动其它字段）：
  - 该字段改为**单一、最具体**的一条建议：在 `expression_fix_pairs` 里取 fix 最短的那对
    （多段拼接越少 → 越接近「就这条片段该怎么说」）；
  - 完整的逐片段映射继续保留在 `expression_fix_pairs`（原本就在），不丢信息；
  - 逐条打印 before/after，人工可核对；`--apply` 才写回，且自动备份。

用法：
  python3 fix-l3-blob.py --dry-run
  python3 fix-l3-blob.py --apply
"""
from __future__ import annotations

import argparse
import json
import shutil
import time
from pathlib import Path

KB = Path("/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理/kb")
RULES = KB / "l3" / "candidates" / "rules.jsonl"
THRESHOLD = 500


def load_rules() -> list[dict]:
    return [json.loads(l) for l in RULES.read_text(encoding="utf-8").splitlines() if l.strip()]


def most_specific(rule: dict) -> str:
    """在 expression_fix_pairs 里挑最具体的一条建议（fix 最短、且非空）。"""
    cands = []
    for p in rule.get("expression_fix_pairs") or []:
        fx = str(p.get("fix") or "").strip()
        fr = str(p.get("fragment") or "").strip()
        if fx and fr:
            cands.append((len(fx), fx))
    if not cands:
        return ""
    cands.sort(key=lambda t: (t[0], t[1]))
    return cands[0][1]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    rules = load_rules()
    long_rules = [r for r in rules if len(str(r.get("suggested_replacement") or "")) > THRESHOLD]
    uniq = {}
    for r in long_rules:
        uniq.setdefault(r.get("rule_id"), r)

    changes = []
    for rid, r in uniq.items():
        new = most_specific(r)
        old = str(r.get("suggested_replacement") or "")
        if new and new != old:
            changes.append({"rule_id": rid, "article_no": r.get("article_no"), "rule_code": r.get("rule_code"),
                            "old_len": len(old), "new_len": len(new), "new_head": new[:160]})

    print(f"规则总行数 {len(rules)}；suggested_replacement > {THRESHOLD} 字符的行 {len(long_rules)} 条（唯一 rule_id {len(uniq)} 条）")
    print(f"可改写 {len(changes)} 条：")
    for c in changes[:12]:
        print("-" * 70)
        print(f"{c['rule_id']} {c['article_no']} {c['rule_code']} :: {c['old_len']} → {c['new_len']}")
        print("  new:", c["new_head"])

    if not a.apply:
        print("\n（dry-run：未写库。核对无误后加 --apply）")
        return

    bak = RULES.with_name(RULES.name + ".bak-" + time.strftime("%Y%m%d-%H%M%S"))
    shutil.copy2(RULES, bak)
    by_id = {c["rule_id"]: c for c in changes}
    out = []
    for r in rules:
        if r.get("rule_id") in by_id:
            r = dict(r)
            r["suggested_replacement"] = most_specific(r)
        out.append(r)
    RULES.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in out), encoding="utf-8")
    print(f"\n已写回 {RULES}（改写 {len(changes)} 条；备份 {bak.name}）")
    print("写回后请重跑：kb_check（宿主）确认健康分与闸门未回退。")


if __name__ == "__main__":
    main()
