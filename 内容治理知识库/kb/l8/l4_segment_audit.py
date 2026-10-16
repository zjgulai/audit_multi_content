#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""l4_segment_audit.py —— L4 段位构成审计（**只读**）＋ 基线比对。

## 这条判据是为哪个决定立的（2026-10-10，Owner 同意）

背景：`kb/l8/l3_distill_run.py` 的外部标准段修好后，L3 产出 **526 条**
`form=scoped_clause` 的真条款候选（⑧ 母婴设计常识清单在其中）。它们下一批发号会落进
**E-1 段** —— 而 E-1 段里**已经躺着 375 条 ⑥ 睡眠RAG 的元数据**（样本 `E-1.114` = 「郭嘉」，
L4 自己逐条标着 `evidence_strength: 资料登记元数据（field_value），非条款正文`）。

**同意下来的裁定 = 「E-1 不动」**，三条理由：

1. **顺序错了会先丢落点**：Owner 决策 2 已把 ⑥ 的处置定成「下钻 84 条 URL 取真资料」。
   **下钻还没做** ⇒ 现在清掉那 375 条，⑥ 在库里就只剩空壳；
   而下钻产出的真条款**本来就占 E-1 的新号**，两者不冲突。
2. **`no_reuse`（号不回收）** ⇒ 清了也**不腾号**，`E-1.1–E-1.375` 只是留空。
   **「腾号」不构成清的理由。**
3. **不需要新开段**：`block_by_library` 里 `E-1` 的 `form` 就是 `scoped_clause`，
   **这个形态的本意就是真条款** —— 是 ⑥ 那批**误用**了它（L2 把索引字段当正文抽了出来）。
   **修的是误用，不是形态**；新开 form 要动唯一权威分段表，代价大于收益。

**但必须防它继续变多** ⇒ 本脚本就是那条判据。

## 判据

红：**某个段里「非条款正文」的条数比基线多**（= 又灌进来了）。
黄：非条款正文的条数**比基线少**（可能有人在清 —— 只报，不判红；号不回收，清少不是错）。
绿：与基线一致。

## 用法

    python3 kb/l8/l4_segment_audit.py                 # 只读审计；红退 3
    python3 kb/l8/l4_segment_audit.py --json
    python3 kb/l8/l4_segment_audit.py --accept-baseline   # 刷新基线（**人开闸**：看清报告再刷）
    python3 kb/l8/l4_segment_audit.py --selftest          # 反向对照
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
KB = os.path.join(ROOT, "kb")
CANON = os.path.join(KB, "l4/canonical")
BASELINE = os.path.join(KB, "l4/registry/segment-baseline.json")

#: 「非条款正文」的判据 —— 两条，任一命中即算（都取自 L4 自己的字段，不另造口径）
_NOT_CLAUSE_VARIANTS = {"metadata_field_value"}
_NOT_CLAUSE_MARK = "非条款正文"


def is_clause_text(row: dict) -> bool:
    """这条 canonical 条目**是不是条款正文**。

    ★ 判据只用 L4 自己写下的两处：`variant` 与 `evidence_strength`。
      不新造口径、不看内容长度（长度像元数据但内容是真条款的情形必须留下）。
    """
    if str(row.get("variant") or "") in _NOT_CLAUSE_VARIANTS:
        return False
    if _NOT_CLAUSE_MARK in str(row.get("evidence_strength") or ""):
        return False
    return True


def segment_of(article_no) -> str:
    """`E-1.114` → `E-1`；取不到就归 `（无号）`，**不猜**。"""
    m = re.match(r"^([A-Z]-\d+)\.", str(article_no or ""))
    return m.group(1) if m else "（无号）"


def audit():
    """扫 L4 canonical，按段统计构成。返回 {段: {...}}。"""
    seg = {}
    for p in sorted(glob.glob(os.path.join(CANON, "*.jsonl"))):
        form = os.path.basename(p)[:-6]
        try:
            fh = open(p, encoding="utf-8")
        except OSError:
            continue
        with fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                except json.JSONDecodeError:
                    continue
                s = segment_of(d.get("article_no"))
                e = seg.setdefault(s, {"total": 0, "not_clause_text": 0,
                                       "forms": {}, "samples": []})
                e["total"] += 1
                e["forms"][form] = e["forms"].get(form, 0) + 1
                if not is_clause_text(d):
                    e["not_clause_text"] += 1
                    if len(e["samples"]) < 3:
                        e["samples"].append({"article_no": d.get("article_no"),
                                             "variant": d.get("variant"),
                                             "text": str(d.get("clause_text") or "")[:24]})
    return seg


def run(accept=False, as_json=False) -> int:
    seg = audit()
    base = {}
    if os.path.exists(BASELINE):
        try:
            base = (json.load(open(BASELINE, encoding="utf-8")) or {}).get("segments") or {}
        except Exception:                                   # noqa: BLE001
            base = {}

    worse, better = [], []
    for s, e in sorted(seg.items()):
        b = (base.get(s) or {}).get("not_clause_text")
        if b is None:
            continue
        if e["not_clause_text"] > b:
            worse.append((s, b, e["not_clause_text"]))
        elif e["not_clause_text"] < b:
            better.append((s, b, e["not_clause_text"]))

    if as_json:
        print(json.dumps({"segments": seg, "baseline": base,
                          "worse": worse, "better": better}, ensure_ascii=False, indent=1))
    else:
        print("L4 段位构成审计（只读）｜判据：某段「非条款正文」条数**不许比基线多**")
        print("-" * 78)
        print(f"{'段':<8}{'总条数':>8}{'非条款正文':>12}{'基线':>8}   形态")
        for s, e in sorted(seg.items()):
            b = (base.get(s) or {}).get("not_clause_text", "—")
            flag = "❌" if any(x[0] == s for x in worse) else ("🔻" if any(x[0] == s for x in better) else "  ")
            print(f"{s:<8}{e['total']:>8}{e['not_clause_text']:>12}{str(b):>8}   "
                  f"{dict(e['forms'])} {flag}")
        print("-" * 78)
        for s, e in sorted(seg.items()):
            if e["not_clause_text"]:
                print(f"  {s} 里「非条款正文」样本：{e['samples']}")
        print()
        print(f"  基线：{os.path.relpath(BASELINE, ROOT)}"
              f"{'（不存在，跑 --accept-baseline 建）' if not base else ''}")
        for s, b, n in worse:
            print(f"  ❌ {s}：「非条款正文」{b} → {n}（**又灌进来了**）")
        for s, b, n in better:
            print(f"  🔻 {s}：「非条款正文」{b} → {n}（变少，只报不判红 —— 号不回收，清少不是错）")
        print("结论：%s" % ("✅ 与基线一致／无新增" if not worse
                          else "❌ %d 个段比基线差" % len(worse)))

    if accept:
        json.dump({"policy": "E-1 不动；非条款正文只许减不许增（2026-10-10 Owner 同意）",
                   "segments": {s: {"total": e["total"],
                                    "not_clause_text": e["not_clause_text"],
                                    "forms": e["forms"]} for s, e in seg.items()}},
                  open(BASELINE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("已刷新基线 → %s" % os.path.relpath(BASELINE, ROOT))
        return 0
    return 3 if worse else 0


def selftest() -> int:
    """反向对照：证明 `is_clause_text` 不是恒真／恒假。"""
    P, F = [], []

    def chk(n, c, extra=""):
        (P if c else F).append(n)
        print("  %s %s%s" % ("✅" if c else "❌", n, ("  " + extra) if extra else ""))

    real = {"article_no": "E-1.900", "variant": "natural_language_clause",
            "evidence_strength": "**实测**：中文自然语言条款正文（L2 clause 单元逐字）",
            "clause_text": "婴儿睡姿为仰卧，不可趴睡"}
    junk = {"article_no": "E-1.114", "variant": "metadata_field_value",
            "evidence_strength": "资料登记元数据（field_value），非条款正文", "clause_text": "郭嘉"}
    chk("① 真条款 ⇒ 判为条款正文", is_clause_text(real) is True)
    chk("② 反向对照：⑥ 的元数据 ⇒ 判为非条款正文", is_clause_text(junk) is False)
    chk("③ 段号解析：E-1.114 → E-1", segment_of("E-1.114") == "E-1")
    chk("④ 反向对照：无号 ⇒ 归「（无号）」**不猜段**", segment_of("") == "（无号）"
        and segment_of(None) == "（无号）")
    seq = [real, junk]
    chk("⑤ 混合输入下两者不混（证明判据在逐条判，不是整批一个值）",
        [is_clause_text(x) for x in seq] == [True, False])

    print("\n反向对照：通过 %d / 失败 %d" % (len(P), len(F)))
    for x in F:
        print("  · 失败：%s" % x)
    return 1 if F else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="L4 段位构成审计（只读）")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--accept-baseline", action="store_true", help="刷新基线（人开闸）")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        print("l4_segment_audit · 反向对照")
        raise SystemExit(selftest())
    raise SystemExit(run(accept=a.accept_baseline, as_json=a.json))
