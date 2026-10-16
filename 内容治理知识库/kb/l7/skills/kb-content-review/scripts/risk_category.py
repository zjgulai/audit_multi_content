#!/usr/bin/env python3
"""`risk_category`（PRD §5.3 的问题维度）—— **唯一实现**。

## 它补的是哪一格

PRD §5.3 逐字：「Agent 输出三态结论时，必须**先标注问题所属维度**，再给出总结和建议。」
PRD §8.3 逐字：「完整问题清单，每条包含：**维度**、位置、问题描述、原因、依据文档链接、修改建议」
PRD §5.4 的 JSON 规范**同时**给两格：`"risk_type": "合规-医疗宣称"` 与 `"risk_category": "合规"`
—— 后者就是本模块产出的那一格（实测：活代码里 `risk_category` **0 命中**）。

## 三条纪律

1. **口径只有一份**：`kb/l7/registry/risk-category-policy.json`。本模块**只读它**，不硬编码映射。
2. **不编**：政策件 `unmapped` 里的类别（`原则性错误` / `文化禁忌` / `未分类` / `unknown`）
   ⇒ `risk_category = None`，并在 `basis` 里写明「待裁」。
   **不给它蒙一个维度** —— 蒙错比留空更坏（留空人会去补，错值人不会回头看）。
3. **纯函数**：不写盘、不联网；政策件读不到 ⇒ 返回 `None` 且 `basis` 写「政策件不可用」，
   **绝不退回到一份内嵌的兜底映射**（那会造出第二份口径）。

## 用法

    python3 kb/l7/skills/kb-content-review/scripts/risk_category.py --selftest
"""

from __future__ import annotations

import argparse
import json
import os
import sys

#: ★★ `realpath` 是**必须的**：本 skill 目录被软链到 `~/.dsh/skills/kb-content-review`
#: （`ls -la ~/.dsh/skills/kb-content-review` = 指向工作区的软链）⇒ 经评审链调用时
#: `__file__` 是**软链路径** `/Users/lute/.dsh/skills/...`，`dirname` 上溯得到的是 `/Users`，
#: 政策件永远读不到。实测踩过两次（`/Users/kb/...` → `/Users/l7/...`）。
#: ⇒ **凡按 `__file__` 定位库内文件，一律先 `realpath`。**
_HERE = os.path.dirname(os.path.realpath(__file__))
#: 本文件真身在 `<root>/kb/l7/skills/kb-content-review/scripts/`；
#: `_HERE` 已经**是 `scripts`** ⇒ 再上溯 **4** 层 = `<root>/kb`
#: （写成 5 层会得到 `<root>`，再拼 `l7/registry/...` 就落到库外 —— 实测踩过一次）。
KB = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(_HERE))))
POLICY = os.path.join(KB, "l7", "registry", "risk-category-policy.json")

#: ★★ 未映射类别的**桶名**（唯一一份）。三个消费端**都从这里取**，不许各写一份字面量：
#:   · 评审链答复正文的分类汇总 —— `review.py::render()`（≥3 条那条分支）
#:   · P0 快路的回执/报告汇总 —— `kb/l5/p0_fastpath.py::_summary_lines()`
#:   · 报告记忆的分组桶 —— `kb/l7/review-engine/core/report_memory.py`（同一个词）
#: 为什么必须只有一份：三处印的是**同一个概念**，各写一份必然漂移成
#: 「未标注 / 待裁 / 其他」三种写法，读者会以为那是三件不同的事。
#: 它是**presentation 词**，不是维度映射 —— 映射仍然只认政策件（见下方 `dimension_of`）。
UNMAPPED_BUCKET = "未标注维度"

_POLICY = None
_POLICY_ERR = None


def load_policy(path: str | None = None) -> dict | None:
    """只读政策件。**读不到就返回 None**，不退回内嵌映射。"""
    global _POLICY, _POLICY_ERR
    p = path or POLICY
    if _POLICY is not None and path is None:
        return _POLICY
    try:
        d = json.load(open(p, encoding="utf-8"))
    except Exception as e:                                   # noqa: BLE001
        _POLICY_ERR = "%s: %s" % (type(e).__name__, e)
        return None
    if path is None:
        _POLICY = d
    return d


def dimension_of(category, sub=None, *, policy: dict | None = None) -> tuple[str | None, str]:
    """库内类别 → (PRD §5.3 维度, 出处)。**取不到就 None，并写明为什么。**"""
    m = policy if policy is not None else load_policy()
    if not m:
        return None, "政策件不可用（%s）⇒ **不编**" % (_POLICY_ERR or "未加载")
    c = str(category or "").strip()
    if not c:
        return None, "类别为空 ⇒ **不编**"
    ent = (m.get("map") or {}).get(c)
    if isinstance(ent, dict) and ent.get("risk_category"):
        hard = "硬引 PRD" if ent.get("hard") else "软判（按 §6.2/§5.2 语义归类）"
        return ent["risk_category"], "类别「%s」⇒ %s（%s：%s）" % (
            c, ent["risk_category"], hard, str(ent.get("prd_basis") or "")[:80])
    un = (m.get("unmapped") or {}).get(c)
    if un:
        return None, "类别「%s」**未映射，待裁** —— %s" % (c, str(un)[:120])
    return None, "类别「%s」不在政策件里（既非 map 也非 unmapped）⇒ **不编**" % c


def stamp(finding: dict, *, policy: dict | None = None) -> dict:
    """就地为一条 finding 打上 `risk_category` 与 `risk_category_basis`。返回该 finding。"""
    cat = finding.get("category")
    lvl, why = dimension_of(cat, finding.get("sub"), policy=policy)
    finding["risk_category"] = lvl
    finding["risk_category_basis"] = why
    return finding


def _selftest() -> int:
    ok = fail = 0
    fails: list[str] = []

    def ck(name, cond, detail=""):
        nonlocal ok, fail
        if cond:
            ok += 1
        else:
            fail += 1
            fails.append("%s %s" % (name, detail))

    pol = load_policy()
    ck("① 政策件可读", isinstance(pol, dict), "得到 %r（%s）" % (type(pol).__name__, _POLICY_ERR))

    # ② 硬引 PRD 的六类（§5.3/§7.3 逐字对得上）
    for cat, want in (("功效宣称", "合规"), ("绝对化与安全承诺", "合规"),
                      ("人物肖像与 AI", "合规"), ("合规红线", "合规"),
                      ("婴幼儿安全与场景", "消费者安全"), ("品牌一致性", "措辞表达"),
                      ("措辞表达", "措辞表达")):
        got, why = dimension_of(cat)
        ck("②[%s]⇒%s" % (cat, want), got == want, "得到 %r（%s）" % (got, why[:60]))

    # ③ 软判的也要有值，且出处必须写明「软判」
    for cat in ("背书与资质", "平台与促销", "表述与术语准确性", "审核问题"):
        got, why = dimension_of(cat)
        ck("③[%s]有维度且标注软判" % cat, got in ("合规", "消费者安全", "产品描述", "措辞表达")
           and "软判" in why, "得到 %r（%s）" % (got, why[:70]))

    # ④ ★★ 未映射的四类**必须留空**（不编）—— 这是本模块最重要的一条
    for cat in ("原则性错误", "文化禁忌", "未分类", "unknown"):
        got, why = dimension_of(cat)
        ck("④[%s]留空且说待裁" % cat, got is None and ("待裁" in why or "不编" in why),
           "得到 %r（%s）" % (got, why[:70]))

    # ⑤ ★ 反向对照：边界——**不许把「不知道」当「合规」**。
    #     把 ④ 的断言放宽成 `got in (None,'合规')` 就会把蒙维度当成通过 ⇒ 本条钉住严格性。
    got, _ = dimension_of("从未见过的类别")
    ck("⑤ 未知类别不蒙（反向对照）", got is None, "得到 %r" % got)

    # ⑥ 空类别 / None 也不蒙
    for v in ("", None, "   "):
        got, _ = dimension_of(v)
        ck("⑥[%r]不蒙" % v, got is None, "得到 %r" % got)

    # ⑦ ★ 政策件读不到 ⇒ **不许**退回内嵌映射（否则等于第二份口径）
    got, why = dimension_of("功效宣称", policy={})
    ck("⑦ 政策件空 ⇒ 不编（无内嵌兜底）", got is None, "得到 %r（%s）" % (got, why[:60]))

    # ⑧ stamp() 只加两个键、不改别的
    f = {"category": "功效宣称", "sub": "催乳与通乳宣称", "reason": "keep-me"}
    before = set(f)
    stamp(f)
    ck("⑧ stamp 只加两键", set(f) == before | {"risk_category", "risk_category_basis"}
       and f["reason"] == "keep-me" and f["risk_category"] == "合规", "得到 %r" % f)

    # ⑨ ★ 政策件**不许**把四个维度写成别的（PRD §5.3 逐字四维）
    ck("⑨ 四维度与 PRD 一致",
       set(pol.get("dimensions") or []) == {"合规", "消费者安全", "产品描述", "措辞表达"},
       "得到 %r" % (pol.get("dimensions") if pol else None))

    # ⑩ ★ Product Descriptions bucket: 政策件**必须显式承认它是空的**（不许假装有）
    ck("⑩ 显式承认「产品描述」当前恒空",
       "产品描述" in str((pol or {}).get("boundary", {}).get("product_desc_empty", "")),
       "boundary.product_desc_empty 没写")

    # ⑪ ★★ 未映射桶名：非空、且**不许与任何一个真维度重名**。
    #     若它写成「合规」，未映射的类别就会被并进合规 —— 把「不知道」当「合规」，
    #     是本模块纪律里**最坏的一类**（§三条纪律 2）。改桶名时这条会精确红。
    ck("⑪ 桶名非空且不与四维重名",
       isinstance(UNMAPPED_BUCKET, str) and UNMAPPED_BUCKET.strip() != ""
       and UNMAPPED_BUCKET not in set((pol or {}).get("dimensions") or []),
       "得到 %r" % (UNMAPPED_BUCKET,))

    # ⑫ ★ 反向对照：桶名**不是** `dimension_of` 会返回的值。
    #     桶名是「取不到维度」的**呈现**，一旦它成了某个真维度，⑪ 就白设了。
    got, _ = dimension_of("从未见过的类别")
    ck("⑫ 桶名不是 dimension_of 的返回值（反向对照）",
       got != UNMAPPED_BUCKET, "得到 %r" % (got,))

    print("risk_category --selftest：%d/%d" % (ok, ok + fail))
    for x in fails:
        print("  ✗", x)
    return 0 if fail == 0 else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="问题维度标注（PRD §5.3 / §8.3）")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--of", help="查一个类别属于哪个维度")
    a = ap.parse_args()
    if a.selftest:
        return _selftest()
    if a.of:
        lvl, why = dimension_of(a.of)
        print("%s ⇒ %s\n  %s" % (a.of, lvl, why))
        return 0
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
