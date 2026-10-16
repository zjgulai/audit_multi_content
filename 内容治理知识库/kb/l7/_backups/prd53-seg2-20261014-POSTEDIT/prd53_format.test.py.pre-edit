#!/usr/bin/env python3
"""prd53_format.test.py —— **PRD §5.3 的分段（空行）判据**（库侧产者）。

## 为什么要有它（Owner 2026-10-14）

Owner 原话：「审核结论中 1，2...每条之间需要空一行的（不管是小于3条飞书侧输出的，
还是大于等于3条输出审查报告的），都要跟 prd 对齐」。

PRD §5.3.2 / §5.3.3 的逐字形状（`␤` = 空行）：

    【审查结论：REVIEW】共发现 2 处需人工确认。
    ␤
    1.【合规-医疗宣称】……
       原因：…… ／ 依据：……
    ␤
    2.【消费者安全-使用姿势】……
    ␤
    建议转 @法务 @医学顾问 复核。

≥3 的汇总形状：**汇总行紧挨着，不空行**（Owner 第二次裁定 —— 卡片上那一组
`逐条问题` 装的**就是**这段汇总，所以「卡片逐条问题不空行」与「≥3 汇总行不空行」是同一件事）。

⇒ **结论行后一个空行 · 链接前一个空行 · 动作行前一个空行**（两种形状都一样）；
  **条目之间**：<3 空一行、**≥3 不空**。

⚠️ 判据要钉的**不只是「有没有空行」，还有「是不是只有一个」** ——
改前实测：**一个空行都没有**（`lines.extend(...)` 首尾相接）。

## 反向对照

R1 故意塞两个空行 ⇒ 「恰好一个」必须红；
R2 故意不塞空行 ⇒ 必须红（证明判据不是恒绿）。

用法：`python3 kb/l7/review-engine/core/prd53_format.test.py`
"""

from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import review_engine as R  # noqa: E402

pass_n = 0
fail_n = 0
bad: list[str] = []


def ok(m: str) -> None:
    global pass_n
    pass_n += 1
    print(f"  ✅ {m}")


def no(m: str, why: str) -> None:
    global fail_n
    fail_n += 1
    bad.append(f"{m} —— {why}")
    print(f"  ❌ {m}\n       {why}")


def head(t: str) -> None:
    print(f"\n{t}")


def blanks(text: str, pattern: str) -> int:
    """两个锚点之间的空行数（`-1` = 没匹配上，本身就是缺陷）。"""
    m = re.search(pattern, text)
    return -1 if not m else len(re.findall(r"\n", m.group(0))) - 1


def item(i: int, cat: str = "合规") -> dict:
    return {
        "risk_id": f"r{i}", "category": cat, "sub": "医疗宣称", "action": "review",
        "priority_tier": "P0", "risk_type": f"{cat}-医疗宣称",
        "location": f"第{i}行", "original_text": "治疗堵奶",
        "reason": "不得出现治疗表述。",
        "evidence": {"library": "库", "article_no": "3.2"},
    }


TWO = R.render_summary("REVIEW", [item(1), item(2)], Counter({"合规": 2}), None)
FIVE = R.render_summary(
    "REVIEW", [item(1), item(2), item(3), item(4, "消费者安全"), item(5, "措辞表达")],
    Counter({"合规": 3, "消费者安全": 1, "措辞表达": 1}), "https://feishu.cn/review/xxx")

# ── ① <3 逐条 ──────────────────────────────────────────────────
head("① <3 逐条 · 结论行 ␤ 每条 ␤ 动作行（各**恰好一个**空行）")
a = blanks(TWO, r"。\n+1\.【")
if a != 1:
    no("①a 结论行后恰好一个空行", f"实际 {a} 个")
else:
    ok("①a 结论行后恰好一个空行")
b = blanks(TWO, r"）\n+2\.【|。\n+2\.【|[^）]。\n+2\.【")
if b != 1:
    no("①b 第 1 条与第 2 条之间恰好一个空行", f"实际 {b} 个")
else:
    ok("①b 条目之间恰好一个空行")
c = blanks(TWO, r"\n+建议转")
if c != 1:
    no("①c 动作行前恰好一个空行", f"实际 {c} 个")
else:
    ok("①c 动作行前恰好一个空行")
if "\n\n\n" in TWO:
    no("①d 全篇没有连续两个空行", "出现了 \\n\\n\\n")
else:
    ok("①d 全篇没有连续两个空行")

# ── ② ≥3 汇总 ──────────────────────────────────────────────────
head("② ≥3 汇总 · 结论行 ␤ 汇总行（**紧挨着**）␤ 链接 ␤ 动作行")
a = blanks(FIVE, r"。\n+·")
if a != 1:
    no("②a 结论行后恰好一个空行", f"实际 {a} 个")
else:
    ok("②a 结论行后恰好一个空行")
# ★★ Owner 第二次裁定：汇总行**紧挨着**（卡片上那一组「逐条问题」装的**就是**这段汇总）
b = blanks(FIVE, r"个\n+·")
if b != 0:
    no("②b **汇总行之间不许空行**（≥3 的规则）", f"实际 {b} 个空行（应 0）")
else:
    ok("②b 汇总行之间不空行（紧挨着）")
c = blanks(FIVE, r"个\n+→ 查看")
if c != 1:
    no("②c 链接前恰好一个空行", f"实际 {c} 个")
else:
    ok("②c 链接前恰好一个空行")
d = blanks(FIVE, r"\n+建议转")
if d != 1:
    no("②d 动作行前恰好一个空行", f"实际 {d} 个")
else:
    ok("②d 动作行前恰好一个空行")
if "\n\n\n" in FIVE:
    no("②e 全篇没有连续两个空行", "出现了 \\n\\n\\n")
else:
    ok("②e 全篇没有连续两个空行")

# ── ③ 反向对照 ─────────────────────────────────────────────────
head("③ 反向对照 · 喂坏形状必须红（证明上面不是恒绿）")
OLD = ("【审查结论：REVIEW】共发现 2 处需人工确认。\n"
       "1.【合规】a\n  原因：r\n"
       "2.【安全】b\n  原因：r\n"
       "建议转 @法务 复核。")
# ⚠️ 锚点写成模块级常量：Python 3.9 的 f-string 表达式里不许出现反斜杠
_A1 = r"。\n+1\.【"
_n1 = blanks(OLD, _A1)
if _n1 == 1:
    no("③a 改前形状必须判得出不符", "旧形状竟算作 1 个空行")
else:
    ok(f"③a 改前形状判得出来（结论行后 {_n1} 个空行 ≠ 1）")
TWO_BLANKS = "【审查结论：REVIEW】共发现 2 处需人工确认。\n\n\n1.【合规】a\n\n建议转 @法务 复核。"
_n2 = blanks(TWO_BLANKS, _A1)
if _n2 == 1:
    no("③b 「恰好一个」必须咬得住多出来的空行", "喂了两个却算作 1")
else:
    ok(f"③b 多出来的空行会被判出（{_n2} ≠ 1）")
# ★ ③c 汇总行被空开（＝我第一版那个错）⇒ ②b 必须咬得住
_A2 = r"个\n+·"
SUMMARY_SPACED = ("【审查结论：REVIEW】共发现 5 处需人工确认。\n\n"
                  "· 合规类问题：3 个\n\n· 安全类问题：1 个\n\n→ 查看…\n\n建议转 @法务 复核。")
_n3 = blanks(SUMMARY_SPACED, _A2)
if _n3 == 0:
    no("③c 汇总行被空开必须判得出", "空开了却算作 0")
else:
    ok(f"③c 汇总行被空开判得出来（{_n3} ≠ 0）—— ②b 咬得住我第一版那个错")

# ── ④ 覆盖缺口那一支（另一个产者）也要分段 ──────────────────────
head("④ 覆盖缺口支 · 与 PRD 分段同源")
src = (HERE / "with_kb_evidence.py").read_text(encoding="utf-8")
# 那一支是 `head\n\n说明：\n\n + _item + _hits_block + "\n\n" + _action_line([])`
if re.search(r'_item \+ _hits_block \+ "\\n\\n"', src):
    ok("④a 覆盖缺口支：条目与动作行之间留了空行")
else:
    no("④a 覆盖缺口支：条目与动作行之间留了空行", "找不到 `\\n\\n` 的分段")

# ── 汇总 ───────────────────────────────────────────────────────
print("\n" + "═" * 64)
print(f"通过 {pass_n} 项 · 不通过 {fail_n} 项")
if fail_n:
    print("\n不通过明细：")
    for x in bad:
        print(f"  · {x}")
    print("\n❌ 分段与 PRD §5.3 不符，别拿去发群。")
    sys.exit(1)
print("✅ 结论行 ␤ 条目 ␤ 动作行 —— 各恰好一个空行，且没有连续空行。")
