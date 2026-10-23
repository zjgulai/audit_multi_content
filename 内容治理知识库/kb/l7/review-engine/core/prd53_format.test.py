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


#: 测试用：A2 四维 → A3 12 类（够用即可，不作为口径真源；真源是 `rule-taxonomy.json`）。
_A3_OF = {"合规": "合规与受监管宣称", "消费者安全": "产品安全与高危使用场景",
          "产品描述": "商品信息与Listing准确性", "措辞表达": "母婴知识内容准确性"}
_A3_SUB_OF = {"合规": "绝对化与最高级用语", "消费者安全": "危险行为示范与模仿风险",
              "产品描述": "规格参数与部件", "措辞表达": "哺乳与泌乳"}


def item(i: int, cat: str = "合规") -> dict:
    return {
        "risk_id": f"r{i}", "category": cat, "sub": "医疗宣称", "action": "review",
        "priority_tier": "P0", "risk_type": f"{cat}-医疗宣称",
        # ★ 2026-10-19：分类汇总的轴改成 **PRD 四维**，读的是 `risk_category`
        #   （真 `risk_items` 带这一格 —— `review.py` 返回前统一盖章，真单实测 4/4 都有）。
        #   夹具跟着带上，否则 5 条全落「未标注维度」一桶，量不到多桶形状。
        "risk_category": cat,
        # ★ 2026-10-19（A3 12 类）：真 `risk_items` 带这两格；汇总轴已切 A3。
        #   四个维度各对到一个 A3 类，**一一对应**（否则 3 个维度会塌成 2 个类，量不到「每类一行」）。
        "taxonomy_category": _A3_OF.get(cat, "未归类"),
        "taxonomy_subcategory": _A3_SUB_OF.get(cat, ""),
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
# ★★ 2026-10-19（Owner：「问题数量≥3 时要有分类汇总 `· 合规类：X 个 · 消费者安全类：X 个
#   · 措辞类：X 个`……卡片所有的回复必须跟 PRD 5.3 对齐」）：
#   汇总行从「每类一行」改成 **PRD §5.3.4 的一行**（`· X类：N 个 · Y类：M 个`）。
#   ⇒ 旧判据 `个\n+·`（量行与行之间的空行）**恒为 -1**，恒红比没有判据更坏。
#   改钉三条，意思不变、形状对齐 PRD：汇总行**一行** · 形状照 §5.3.4 · 「逐条问题」与它之间不空行。
# ★★ 2026-10-19 第三次（Owner 逐字给的格式）：「目前是写的一行」⇒ **每类一行**、`· <维度>类问题：N 个`。
_row_re = re.compile(r"^· [^·\n，]+类问题：\d+ 个$")
_sum_rows = [ln for ln in FIVE.split("\n") if ln.startswith("· ")]
if len(_sum_rows) < 3:
    no("②b 汇总行**每类一行**（3 桶 ⇒ 3 行）", f"实际 {len(_sum_rows)} 行：{_sum_rows}")
elif not all(_row_re.match(ln) for ln in _sum_rows):
    no("②b 每行的形状 = `· <维度>类问题：N 个`", str(_sum_rows))
else:
    ok(f"②b 汇总行每类一行且形状照 Owner 给的格式：{_sum_rows[0]} …（共 {len(_sum_rows)} 行）")
# ★ 2026-10-19（A3 轴）：汇总行必须是 **A3 12 类名**，不许再出现 A1/A2 的类名
if any(x in FIVE for x in ("· 合规类问题", "· 消费者安全类问题", "· 措辞表达类问题")):
    no("②b1 汇总轴 = A3（不许是 A2 四维）", [l for l in _sum_rows if "类问题" in l][:2])
else:
    ok("②b1 汇总轴 = A3（未出现 A2 四维类名）")
# Owner 2026-10-14：行与行之间**不空行**
_between = re.findall(r"个\n+· ", FIVE)
_extra = [m for m in _between if m != "个\n· "]
if _extra:
    no("②b2 汇总行之间不许空行", f"发现 {len(_extra)} 处被空开")
else:
    ok("②b2 汇总行之间不空行（紧挨着）")
# 反向对照：缩成一行（`· 合规类问题：1 个 · 消费者安全类问题：1 个`）⇒ ②b 必须红
_one = "· 合规类问题：1 个 · 消费者安全类问题：1 个"
if _row_re.match(_one):
    no("②b3 反向对照：缩成一行必须判得出", "一行多段竟被当成合规形状")
else:
    ok("②b3 反向对照：缩成一行判得出来（②b 咬得住「写的一行」那个版本）")
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
# ★ ③c 汇总行被**缩成一行**（＝我上一版那个错，Owner 说「目前是写的一行」）⇒ ②b 必须咬得住
SUMMARY_ONE = ("【审查结论：REVIEW】共发现 5 处需人工确认。\n\n"
               "· 合规类问题：3 个 · 消费者安全类问题：1 个\n\n→ 查看…\n\n建议转 @法务 复核。")
_n3 = len([ln for ln in SUMMARY_ONE.split("\n") if ln.startswith("· ") and _row_re.match(ln)])
if _n3 == 1:
    no("③c 缩成一行的汇总必须判得出", "一行多段却算作合规行")
else:
    ok(f"③c 缩成一行的汇总判得出来（合规行 {_n3} 行）—— ②b 咬得住那个版本")

# ── ④ 覆盖缺口那一支（另一个产者）也要分段 ──────────────────────
head("④ 覆盖缺口支 · 与 PRD 分段同源")
src = (HERE / "with_kb_evidence.py").read_text(encoding="utf-8")
# 那一支是 `head\n\n说明：\n\n + _item + _hits_block + "\n\n" + _action_line([])`
if re.search(r'_item \+ _hits_block \+ "\\n\\n"', src):
    ok("④a 覆盖缺口支：条目与动作行之间留了空行")
else:
    no("④a 覆盖缺口支：条目与动作行之间留了空行", "找不到 `\\n\\n` 的分段")

# ═══ PRD §5.3.2 **rev 101**：SUGGEST 是 **PASS 的附属标签**，不是结论行 ═══
#
# 改前（同日早些，rev 96 读法）：这里断言 `render_summary("SUGGEST", …)` 出
# `【审查结论：SUGGEST】发现 N 处建议优化，不阻断发布。`。
# rev 101 原文：「SUGGEST｜非强制性问题…**作为 PASS 的附属标签**，不阻断流程。
#               ｜**随 PASS 一起流转，提示内容方。**」＋ PASS 定义「**可包含 SUGGEST 建议**」。
# ⇒ 现在的判据是**三条**：
#   ① 结论行**恒为 PASS**（第四态从卡面消失）；
#   ② 建议作为**附段**跟着走（「建议（不阻断，随 PASS 流转，共 N 条）：」＋ 逐条）；
#   ③ `render_summary("SUGGEST", …)` 必须**硬失败** —— 悄悄降级会让第四态从别处长回来。
head("④b SUGGEST 作为 PASS 的附属标签（PRD §5.3.2 rev 101）")

# 夹具：两条 P3（advice）条目 —— 真 `risk_items` 里 P3 的 action 就是 "advice"
_p3 = []
for _k in (1, 2):
    _it = item(_k)
    _it.update({"priority_tier": "P3", "action": "advice", "severity": "SUGGEST",
                "suggestion": f"改为「第{_k}行的合规写法」"})
    _p3.append(_it)

_pass_sug = R.render_summary("PASS", _p3, Counter(), None)
if not _pass_sug.startswith("【审查结论：PASS】未发现已知底线风险"):
    no("④b PASS＋建议：结论行必须仍是 PASS", _pass_sug[:80])
else:
    ok("④b PASS＋建议：结论行仍是 `【审查结论：PASS】`（第四态不在卡面）")
if "建议（不阻断，随 PASS 流转，共 2 条）：" in _pass_sug:
    ok("④b2 建议作为附段：「不阻断」「随 PASS 流转」逐字在")
else:
    no("④b2 建议作为附段：缺「建议（不阻断，随 PASS 流转，共 N 条）：」这一行", _pass_sug[:200])
if "1.【" in _pass_sug and "2.【" in _pass_sug:
    ok("④b3 建议逐条列出（1./2. 两条都在）")
else:
    no("④b3 建议逐条列出：条号缺失", _pass_sug[:200])
if ("需人工确认" in _pass_sug) or ("必须修改" in _pass_sug) or ("复核" in _pass_sug):
    no("④b4 反向对照：建议段混进了 REVIEW/BLOCK 的措辞或转派话术", _pass_sug[:200])
else:
    ok("④b4 反向对照：建议段没有「需人工确认/必须修改/复核」")

# ④b5 **反向对照（核心）**：给 SUGGEST 当结论渲染 ⇒ 必须硬失败
try:
    R.render_summary("SUGGEST", _p3, Counter(), None)
    no("④b5 反向对照：`render_summary('SUGGEST', …)` 竟渲染成功（第四态会从这条路长回来）", "")
except ValueError:
    ok("④b5 反向对照：`render_summary('SUGGEST', …)` 硬失败（SUGGEST 不是结论态）")

# ④b6 反向对照：没有 P3 时 PASS **不许**长出建议段（否则「附段」变成恒有）
_p0 = [item(1)]
if "建议（不阻断" in R.render_summary("PASS", _p0, Counter(), None):
    no("④b6 反向对照：没有 P3 的 PASS 也出现了建议段", "")
else:
    ok("④b6 反向对照：没有 P3 的 PASS 不长建议段")

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
