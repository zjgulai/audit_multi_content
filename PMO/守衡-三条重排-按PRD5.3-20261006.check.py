#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""守衡三条重排件的 PRD §5.3 回验器（一次性留痕件，**不是**已接线的闸门）。

用途：证明 `PMO/守衡-三条重排-按PRD5.3-20261006.md` 里的三条重排输出
      **真的满足 PRD §5.3**，而不是我看着像。

判据两套，缺一套都不算验过：
  ① KB 侧原文 —— `kb/.work/l7_integrity.py:114-122` 的 template_conformance，逐字照搬；
  ② PRD §5.3 逐字措辞 —— ① **只查到「共发现」为止**，没查后半句
     （REVIEW「需人工确认」/ BLOCK「必须修改」）。这正是引擎把两态写成同一句话却一路绿灯的原因。

★ 反向对照是这套判据的一部分，不是附注：
  把**群里实际发出**的那三条（`PMO/logs/ws_outbound.jsonl`，source=reply）喂进来，
  **必须全红**。全绿就说明判据是废的。

用法：
    python3 PMO/守衡-三条重排-按PRD5.3-20261006.check.py
退出码：0 = 重排全绿且实发全红；1 = 任一不符（含「判据没红」）
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "PMO" / "守衡-三条重排-按PRD5.3-20261006.md"
OUTBOUND = ROOT / "PMO" / "logs" / "ws_outbound.jsonl"

# 三条送审的消息 id（飞书私聊 oc_7775e2dacb6f2ebc9789cd6e681de5f7，2026-10-06 07:46–07:51）
MSG_IDS = {
    "om_x100b6377222aa0a4b2e3e61bcd93867": 0,   # PASS
    "om_x100b63773f47cca0b4ce27d63462d4e": 1,   # BLOCK
    "om_x100b63773f3d10a8b12c057f44d6091": 2,   # REVIEW
}


def bare_blocks(text: str) -> list[str]:
    """只抽**裸围栏**块（``` 独占一行、无语言标注）。

    ★ 这个函数第一版写错过，记在这里：把「闭合围栏」当成「起始围栏」，
      于是 ```python 块的**收尾**开了一个新块、正文块全被错位切开，
      **判据对正确的输出也报红**。一个会误报的检查器比没有检查器更糟（AGENTS.md §2.1.1）。
      判据是：带语言标注的围栏只负责「开块」，它自己绝不是一个可抽取的块。
    """
    out, cur, inside, keep = [], [], False, False
    for line in text.split("\n"):
        if line.strip().startswith("```"):
            if inside:
                if keep:
                    out.append("\n".join(cur))
                cur, inside, keep = [], False, False
            else:
                inside, keep, cur = True, line.strip() == "```", []
            continue
        if inside and keep:
            cur.append(line)
    return out


# ── 判据 ①：KB 原文（kb/.work/l7_integrity.py:114-122 的四个 marker）──────────
def kb_markers(a: str) -> dict[str, bool]:
    return {
        "KB·BLOCK": "【审查结论：BLOCK】共发现" in a and "请修改后重新提交。" in a,
        "KB·REVIEW": "【审查结论：REVIEW】共发现" in a and "建议转" in a,
        "KB·PASS": "【审查结论：PASS】未发现已知底线风险，可转交" in a,
        "KB·逐条分流(1-2)": re.search(
            # ★ 2026-10-06：标签要不要加粗属**呈现**，两条都认（`\*{0,2}`）。
            #   这份交付件里的三条是**历史记录**，不为了新格式去改写它；
            #   生产者那一侧的「必须是加粗」另有断言（`kb/.work/l7_integrity.py` 的 template_from_engine）。
            r"1\.【[^】]+】[^\n]*\n\s+\*{0,2}原因\*{0,2}：[^\n]*\n\s+\*{0,2}依据\*{0,2}：[^\n]*\n"
            r"(?:\s+\*{0,2}(?:锚点|source_sha256|判定)\*{0,2}[^\n]*\n)*\s+\*{0,2}建议\*{0,2}：", a) is not None,
    }


# ── 判据 ②：PRD §5.3 的**后半句**（① 没查这一半）───────────────────────────
PRD_PASS = lambda a: "【审查结论：PASS】未发现已知底线风险，可转交" in a
PRD_REVIEW = lambda a: re.search(r"【审查结论：REVIEW】共发现 \d+ 处需人工确认。", a) is not None
PRD_BLOCK = lambda a: re.search(r"【审查结论：BLOCK】共发现 \d+ 处必须修改。", a) is not None

# (态名, PRD 措辞判据, KB 态判据, 是否要求逐条四要素)
CASES = [
    ("① PASS", PRD_PASS, "KB·PASS", False),
    ("② BLOCK", PRD_BLOCK, "KB·BLOCK", True),
    ("③ REVIEW", PRD_REVIEW, "KB·REVIEW", True),
]


def judge(name: str, text: str, prd, kb_key: str, need_detail: bool) -> bool:
    marks = kb_markers(text)
    ok = bool(prd(text)) and marks[kb_key] and (marks["KB·逐条分流(1-2)"] if need_detail else True)
    print(f"  {'✅' if ok else '❌'} {name}"
          f"｜PRD 逐字措辞 {'✅' if prd(text) else '❌'}"
          f"｜KB 态判据 {'✅' if marks[kb_key] else '❌'}"
          f"｜逐条四要素 {'—' if not need_detail else ('✅' if marks['KB·逐条分流(1-2)'] else '❌')}")
    return ok


def main() -> int:
    print("=" * 72)
    print("A · 重排后的三条（应当全绿）")
    print("=" * 72)
    # ★ 按**内容**挑块，不按个数：这份文档自己第三节就有一个「围栏读数块」，
    #   第一版写 `assert len(blocks) == 3`，于是加完回验段之后本检查器自己变红。
    #   判据必须钉在「这三条结论」上，不能钉在「文档里有几个围栏」上。
    blocks = [b for b in bare_blocks(DOC.read_text(encoding="utf-8"))
              if b.lstrip().startswith("【审查结论：")]
    if len(blocks) != 3:
        print(f"❌ 交付件里以「【审查结论：」开头的裸围栏块应为 3 个，实测 {len(blocks)} 个 —— 抽取器或文档坏了")
        return 1
    fixed = [judge(n, b, p, k, d) for (n, p, k, d), b in zip(CASES, blocks)]

    print("\n" + "=" * 72)
    print("B · 反向对照：群里**实际发出**的三条（必须全红）")
    print("=" * 72)
    live: list[bool | None] = [None, None, None]
    for line in OUTBOUND.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if r.get("source") == "reply" and r.get("reply_to") in MSG_IDS:
            i = MSG_IDS[r["reply_to"]]
            name, prd, kb_key, need = CASES[i]
            live[i] = judge(name + " 实发", r.get("text", ""), prd, kb_key, need)
    if any(v is None for v in live):
        print(f"❌ 台账里少读数（{live}）—— 没测到不许当成红，也不许当成绿")
        return 1

    print("\n" + "=" * 72)
    a_ok, b_ok = all(fixed), not any(live)
    print(f"重排后三条：{'✅ 全绿' if a_ok else '❌ 有红'}")
    print(f"实发三条：  {'✅ 全红（判据确实会红）' if b_ok else '❌ 判据没红 —— 它是废的'}")
    print("=" * 72)
    return 0 if (a_ok and b_ok) else 1


if __name__ == "__main__":
    sys.exit(main())
