#!/usr/bin/env python3
"""routing.test.py —— 「按问题方向转对应专业团队」的判据（PRD §5.3.2 / §9）。

## 为什么需要它

Owner 2026-10-14 报：PRD §5.3.2 **两处**逐字写着

    建议转 @法务 @医学顾问 复核。

而库里发出去的是 `建议转 @内容治理负责人 复核。` —— 一个**硬编码常量**：
收件人不在 PRD 那四个专业团队里，且**不随问题方向变**。

## 反向对照（拆掉修复必须精确变红）

R1 空 rules 的假表 ⇒ 必须回落，方向结果必须消失（证明「按方向」真的在读表）；
R2 假句柄表 ⇒ 必须输出真 @handle（证明「（未配置）」不是恒定的）；
R3 `reason` 塞满方向词 ⇒ 路由**不许**被带偏；
R4 空清单 ⇒ 必须落 fallback（这一支**必然走到**：覆盖缺口恒为空清单）。

用法：`python3 kb/l7/review-engine/core/routing.test.py`
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import routing  # noqa: E402

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


def eq(m: str, got, want) -> None:
    (ok(m) if got == want else no(m, f"得到 {got!r}，预期 {want!r}"))


def head(t: str) -> None:
    print(f"\n{t}")


def at_unconfigured(role: str) -> str:
    """模拟 `review_engine._at`：`l7.json` 的 approvers 句柄全为 null。"""
    return f"@{role}（未配置）"


POLICY = routing.load_policy()
F = lambda cat, **kw: {"location": "全文", "category": cat, "severity": "REVIEW", **kw}  # noqa: E731


def line(items, policy=POLICY, at=at_unconfigured) -> str:
    return routing.review_action_line(items, at, policy)


# ── ① 路由表读到了 ──────────────────────────────────────────────
head("① 路由表 · 读到库里的真源")
if POLICY:
    ok(f"①a 路由表读得到（{POLICY['version']}，{len(POLICY['rules'])} 条 rules）")
else:
    no("①a 路由表读得到", f"没读到：{routing._POLICY_PATH}")
if routing._POLICY_PATH.exists():
    ok("①b 路由表文件真存在（与守衡 `routing.mjs` 读同一份）")
else:
    no("①b 路由表文件真存在", str(routing._POLICY_PATH))

# ── ② 按方向转人 ────────────────────────────────────────────────
head("② 方向 → 收件人 · 不同方向必须转不同的人（Owner 那条要求）")
med = routing.owners_for([F("合规-医疗宣称")], POLICY)["owners"]
loc = routing.owners_for([F("本地化-计量单位")], POLICY)["owners"]
end = routing.owners_for([F("背书与资质")], POLICY)["owners"]
prod = routing.owners_for([F("产品-型号规格")], POLICY)["owners"]

eq("②a 医疗方向 ⇒ 医学顾问 + 法务", sorted(med), sorted(["医学顾问", "法务"]))
eq("②b 本地化方向 ⇒ 北美同事", loc, ["北美同事"])
eq("②c 背书方向 ⇒ 法务 + 渠道负责人", end, ["法务", "渠道负责人"])
eq("②d 产品方向 ⇒ 产品负责人 + 法务", prod, ["产品负责人", "法务"])

if line([F("合规-医疗宣称")]) == line([F("本地化-计量单位")]):
    no("②e 不同方向不许得到同一行", "医疗与本地化得到同一行")
else:
    ok("②e 不同方向得到不同的行（缺陷本身就是「恒为同一个人」）")

# ── ③ 句式与收件人 ──────────────────────────────────────────────
head("③ 收尾句式 · 保 `建议转 … 复核。`，去 `内容治理负责人`")
t = line([F("合规-医疗宣称")])
if t.startswith("建议转 ") and t.rstrip().endswith("复核。"):
    ok("③a 句式合 PRD §5.3.2（建议转 @… 复核。）")
else:
    no("③a 句式合 PRD §5.3.2", t)
if "内容治理负责人" in t:
    no("③b 不许再出现「内容治理负责人」", t)
else:
    ok("③b 不再出现「内容治理负责人」")
if all(o in ["法务", "医学顾问", "专家", "北美同事"] for o in med):
    ok(f"③c 收件人出自 PRD §9 四团队（{' / '.join(med)}）")
else:
    no("③c 收件人须出自 PRD §9 四团队", str(med))

# ── ④ 三种「不知道」都不许编 ────────────────────────────────────
head("④ 不知道就说不知道")
eq("④a 读不到路由表 ⇒ 回落 PRD 默认",
   routing.owners_for([F("合规-医疗宣称")], None)["owners"], routing.PRD_DEFAULT_OWNERS)
eq("④a2 且标明来源是默认值",
   routing.owners_for([F("合规-医疗宣称")], None)["source"], "prd_default")

unknown = line([F("某个没登记过的方向")])
if "未匹配到方向" not in unknown:
    no("④b 未命中要出声", unknown)
else:
    ok("④b 未命中方向时如实标出（不静默当成路由过了）")

part = line([F("合规-医疗宣称"), F("某个没登记过的方向")])
if "1/2 条未匹配到方向" not in part:
    no("④c 部分未命中要给出比例", part)
else:
    ok("④c 部分未命中给出比例（1/2）")

if "（未配置）" not in line([F("合规-医疗宣称")]):
    no("④d 句柄没配要说「未配置」", line([F("合规-医疗宣称")]))
else:
    ok("④d 句柄没配 ⇒ 「角色名（未配置）」，不写死人名")

# ④f ★ 实测抓到的真缺陷：空清单曾渲染成 `建议转  复核。`（没有宾语）。
#     而库侧**覆盖缺口那一支恒为空清单** ⇒ 这条必然走到。
empty = line([])
if "建议转  " in empty and "复核。" in empty and "建议转  复核。" in empty:
    no("④f 空清单不许渲染出空收件人", f"实际：{empty}")
else:
    ok(f"④f 空清单渲染成有宾语的一句（{empty}）")

# ── ⑤ 方向只吃方向字段 ──────────────────────────────────────────
head("⑤ 方向字段才是方向 · `reason` 里的词不许把路由带偏")
d = routing.direction_of({"category": "措辞表达", "reason": "不得宣称医疗功效"})
if "医疗" in d:
    no("⑤a direction_of 不许吃 reason", d)
else:
    ok("⑤a direction_of 只取方向字段（不吃 reason）")
eq("⑤b reason 里的方向词不许改变路由结果",
   routing.owners_for([F("本地化-计量单位", reason="医疗 功效 睡眠 认证 背书 达人 平台 文化")], POLICY)["owners"],
   ["北美同事"])

# ── ⑥ 反向对照 ──────────────────────────────────────────────────
head("⑥ 反向对照 · 喂坏样本必须红")
empty_policy = {"version": "test", "roles": {}, "rules": [], "fallback": []}
r6 = routing.owners_for([F("本地化-计量单位")], empty_policy)["owners"]
eq("⑥a 空 rules 的表 ⇒ 回落 PRD 默认", r6, routing.PRD_DEFAULT_OWNERS)
if r6 == ["北美同事"]:
    no("⑥a2 空表不许还给出方向结果", "退化了却没红")
else:
    ok("⑥a2 空表下方向结果确实消失（说明 ②b 真的在按表算）")

fake_at = lambda role: f"@真句柄-{role}"  # noqa: E731
with_h = line([F("合规-医疗宣称")], POLICY, fake_at)
if "@真句柄-法务" not in with_h:
    no("⑥b 配了句柄就要输出真 @handle", with_h)
else:
    ok(f"⑥b 配了句柄 ⇒ 输出真 @handle（{with_h}）")
if "（未配置）" in with_h:
    no("⑥b2 配了句柄就不许再说未配置", with_h)
else:
    ok("⑥b2 配了句柄就不再说「未配置」")

OLD = "建议转 @内容治理负责人 复核。"
if "内容治理负责人" not in OLD:
    no("⑥c 旧常量样本本身要含那个词", OLD)
else:
    ok("⑥c 旧常量样本确实含「内容治理负责人」⇒ ③b 不是空断言")

def strip_comments(text: str) -> str:
    """剥掉注释再扫（**本判据自己踩过的坑**）。

    ★ 第一版直接 `in` 全文，于是红在**我自己的说明注释**上 ——
      那条注释逐字引用了旧写法（`建议转 @内容治理负责人 复核。`）来解释病灶。
      红在文档上不叫守着，叫噪声：它会逼着后人不敢在注释里写清病灶。
      ⇒ 判据必须只看**可执行代码**。（JS 侧同一坑、同一修法，见 `verify_cards.mjs` J17c。）
    """
    import re
    out = []
    for line in text.split("\n"):
        line = re.sub(r"#.*$", "", line)          # 行内与整行注释
        out.append(line)
    return "\n".join(out)


# ── ⑦ 接线：真引擎的产者不许再产旧行 ────────────────────────────
head("⑦ 接线 · 真产者（review_engine）不许再产旧行 · 且角色名不许丢")
src = strip_comments((HERE / "review_engine.py").read_text(encoding="utf-8"))
if "_at('review_reviewers')" in src and "lines.append(_review_action_line" not in src:
    no("⑦a 两个产者都换了接线", "review_engine 里还是 _at('review_reviewers')")
elif "lines.append(_review_action_line(items)" not in src:
    no("⑦a 两个产者都换了接线", "找不到 _review_action_line 的调用点")
else:
    n = src.count("lines.append(_review_action_line(items)")
    ok(f"⑦a review_engine 的两处产者都接了路由（{n} 处）")

ev = strip_comments((HERE / "with_kb_evidence.py").read_text(encoding="utf-8"))
if "建议转 @内容治理负责人 复核。" in ev:
    no("⑦b with_kb_evidence 的硬编码已消", "那一行还在（代码里，不是注释）")
else:
    ok("⑦b with_kb_evidence 的硬编码常量已消（代码级）")

# ⑦c 反向对照：strip_comments **真的会剥** —— 喂一份只把旧行放在注释里的样本，
#     必须**不**被判红；喂一份放在代码里的，必须被判红。
if "内容治理负责人" in strip_comments("# 建议转 @内容治理负责人 复核。"):
    no("⑦c 反向对照：注释必须被剥掉", "剥不掉 ⇒ ⑦b 会红在文档上")
else:
    ok("⑦c 反向对照：只出现在注释里的旧行不会被判红")
if "内容治理负责人" not in strip_comments('x = "建议转 @内容治理负责人 复核。"'):
    no("⑦c2 反向对照：代码里的旧行必须留得住", "连代码一起剥了 ⇒ ⑦b 变成恒绿")
else:
    ok("⑦c2 反向对照：代码里的旧行仍会被抓（⑦b 不是恒绿）")

# ── ⑧ ★★ 角色名不许丢（当天抓到的**第二个**真缺陷）────────────────
#
#   病灶：`_at()` 只认 `l7.json` 的 **key**（`pass_signoff` 等），而路由传给它的是
#   **角色名**（`法务`）⇒ 查不到 ⇒ 走 `_FALLBACK_ROLE` 兜底成 `@责任人（未配置）`
#   —— **角色名丢了**，业务侧看到「转责任人复核」，比改动前更没法用。
#   修法：拿到的名字是什么就输出什么；只有传进来的是个查不到的 **key** 才用兜底词。
head("⑧ 角色名不许丢 · `_at` 要吃两种入参（key 与角色名）")
try:
    import review_engine as RE
    _at_ok = True
except Exception as e:      # noqa: BLE001
    _at_ok = False
    no("⑧a 能导入 review_engine", repr(e))

if _at_ok:
    # ⑧b 角色名必须原样保留
    got = RE._at("法务")
    if "法务" not in got:
        no("⑧b 角色名必须原样保留", f"_at('法务') = {got}")
    else:
        ok(f"⑧b 角色名原样保留（{got}）")
    # ⑧c 反向对照：**不许**退回兜底词「责任人」
    if "责任人" in got:
        no("⑧c 不许退回兜底词「责任人」", got)
    else:
        ok("⑧c 没有退回兜底词「责任人」")
    # ⑧d 老口径（key）必须**一字不变** —— 改这个函数不许碰坏既有三处
    eq("⑧d key `pass_signoff` 未变", RE._at("pass_signoff"), "@sign-off 责任人（未配置）")
    eq("⑧d2 key `review_reviewers` 未变", RE._at("review_reviewers"), "@复核责任人（未配置）")
    eq("⑧d3 key `block_owner` 未变", RE._at("block_owner"), "@内容方修改责任人（未配置）")
    # ⑧e PRD §5.3.1 的 PASS 行必须仍然合（它也走 `_at`）
    from collections import Counter as _C
    pass_line = RE.render_summary("PASS", [], _C(), None)
    if not re.match(r"^【审查结论：PASS】未发现已知底线风险，可转交 @\S[^\n]*进行 sign-off", pass_line):
        no("⑧e PASS 行仍合 §5.3.1", pass_line)
    else:
        ok("⑧e PASS 行仍合 §5.3.1（`_at` 的改动没碰坏它）")
    # ⑧f 端到端：真产者的输出里必须是**角色名**，不是「责任人」
    t8 = RE._review_action_line([{"category": "合规-医疗宣称"}])
    if "责任人" in t8 or "医学顾问" not in t8:
        no("⑧f 真产者输出角色名", t8)
    else:
        ok(f"⑧f 真产者输出角色名（{t8}）")

# ── 汇总 ────────────────────────────────────────────────────────
print("\n" + "═" * 64)
print(f"通过 {pass_n} 项 · 不通过 {fail_n} 项")
if fail_n:
    print("\n不通过明细：")
    for b in bad:
        print(f"  · {b}")
    print("\n❌ 路由还不合 PRD §5.3.2 / §9，别拿去发群。")
    sys.exit(1)
print("✅ 收件人按问题方向算、句式合 PRD、三种「不知道」都如实说。")
