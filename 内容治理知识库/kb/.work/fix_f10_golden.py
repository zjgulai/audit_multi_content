#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""修复计划 F10 · 生成黄金问题集 `<子库>/tests/golden-questions-*.md`（解锁「覆盖率」维度）。

## 加载器怎么读它（`dsh-kb/lib/kb.js → loadGoldenQuestions`）

扫 `<根>/<子库>/tests/golden-questions-*.md`，逐行按 `|` 切，取
`cells[1]` 作题号（须匹配 `^Q\\d+$`）、`cells[2]` 作题干、`cells[3]` 作**期望条目 id**（反引号可有可无）。
`cells.length < 5` 的行跳过（首尾各一个空串）。

**覆盖率 = 黄金问题里 `kb_search` 能在 Top-10 命中期望条目的比例**（`COVERAGE_TOP_K = 10`）。
注意它只测机器可测的那一半 ——「命中」不等于「正文确实覆盖」，后者是人的活。

## 出题纪律（防「自己考自己」）

- **题干来源**：`kb/l7/registry/l7.json → vocabulary` 的类别/子类名（该词表的 `prd_source` 是 PRD §7.2/§7.3）
  ＋ 技术方案 9 案与 L7 自验里的**真实送审原句**。两者都与规则来源表**不重叠**。
- **期望条目的确定**：按该子类的 `codes` 找带对应 `rule_code` 的条目（标题形如 `[H06]`）。
  这是「问 X 类问题应命中 X 类规则」的**原则性映射**，不是"读条目正文反推题目"。
- **绝不**从条目正文摘句子当题干 —— 那样覆盖率会自己考自己，数字好看但没有意义。

## 状态

这是**技术侧种子集**，供 business review 后扩充。真正的题量目标见修复计划（30–50 题起）。
本脚本写出的题目标了 `[seed]` 来源，business 复核定稿后应另存一份并保留本份作对照。

用法：python3 kb/.work/fix_f10_golden.py            # 打印到 stdout
     python3 kb/.work/fix_f10_golden.py --out /tmp/gq.md
"""

from __future__ import annotations

import argparse
import collections
import glob
import json
import os
import re
import sys

KB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VIEW = os.path.join(KB, "view")
COLL = "3_措辞表达库"

# ── 真实送审原句（来源：技术方案 §15 的 9 案 / L7 自验）——与规则来源表不重叠 ──
# (题干, 期望命中的 rule_code 或 (code, 精确 article_no))
REAL_CASES = [
    ("FDA approved 和 FDA cleared 这两个写法，哪个能用？", "H06"),
    ("文案里写「治疗堵奶」，能不能发？", "H01"),
    ("德语站的「schmerzfrei」这个词有问题吗？", "H07"),
    ("西语「Extrae más leche fácilmente」这类表达能发吗？", "H02"),
    ("「100% safe」能不能写在包装主图上？", "H05"),
    ("「hospital grade」「医疗级」这种说法能用吗？", "M05"),
    ("达人内容里写「儿科医生推荐」需要什么前提？", "H04"),
    ("「静音」「whisper-quiet」怎么表述才合规？", "M01"),
    ("「销量第一」「No.1 best seller」需要什么依据？", "M03"),
    ("「比同类产品更好用」这种对比表述能用吗？", "M06"),
    ("文案写「IBCLC 认证」「泌乳顾问调校」可以吗？", "U01"),
    ("「NICU 适用」「医院同款」能写吗？", "U03"),
    ("写「保险可报销」「HSA/FSA 可用」合规吗？", "U02"),
    ("「限时」「最后机会」这类促销话术有风险吗？", "M04"),
    ("「自动识别节奏」「模拟宝宝吸吮」算违规吗？", "H09"),
    ("「临床证明有效」「测试验证」需要什么证据？", "H03"),
    ("「排空效率提升 30%」这类效率宣称能用吗？", "M07"),
    ("「超强吸力」「极致静音」这类绝对化性能词合规吗？", "M02"),
    ("「无痛」「pain-free」能不能用？", "H07"),
    ("「自然回奶」「奶量提升」这类表述有风险吗？", "H02"),
]


def build_entries() -> tuple[list[dict], dict[str, list[str]], dict[str, str]]:
    """返回 (视图条目, code→ids, article_no→id)"""
    ents, by_code = [], collections.defaultdict(list)
    by_article = {}
    for f in sorted(glob.glob(os.path.join(VIEW, COLL, "*", "*.md"))):
        txt = open(f, encoding="utf-8", errors="replace").read()
        m = re.match(r"^---\r?\n([\s\S]*?)\r?\n---", txt)
        if not m:
            continue
        fm = m.group(1)
        i = re.search(r"^id:\s*(\S+)", fm, re.M).group(1)
        t = re.search(r'^title:\s*"?\[([^\]]+)\]', fm, re.M)
        key = t.group(1).strip() if t else ""
        ents.append({"id": i, "key": key, "path": f})
        if re.fullmatch(r"[A-Z]\d+", key):
            by_code[key].append(i)
        if re.fullmatch(r"[WSEP]-\d+\.\d+", key):
            by_article[key] = i
    return ents, by_code, by_article


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    if not os.path.isdir(VIEW):
        print(f"视图不存在：{VIEW}", file=sys.stderr)
        return 2
    ents, by_code, by_article = build_entries()
    if not ents:
        print("视图里没有条目，无法出题", file=sys.stderr)
        return 2
    ids = {e["id"] for e in ents}

    vocab = json.load(open(os.path.join(KB, "l7", "registry", "l7.json"),
                           encoding="utf-8"))["vocabulary"]

    # ── 类别型题目：每个带码子类一题，题干由**类别/子类名 + label** 组织 ──
    qs: list[dict] = []
    for cat, cb in vocab["categories"].items():
        for sub, sb in (cb.get("subs") or {}).items():
            codes = [str(c) for c in (sb.get("codes") or [])]
            if not codes:
                continue
            target = None
            for c in codes:
                if by_code.get(c):
                    target = sorted(by_code[c])[0]
                    break
            if not target:
                continue
            label = (sb.get("label") or "").split("（")[0]
            qs.append({
                "q": f"「{sub}」（{label}）这类表述该怎么判？有哪些禁用表达？",
                "id": target, "src": f"vocabulary·{cat}/{sub}", "codes": codes,
            })

    # ── 真实案例型题目 ──
    for text, code in REAL_CASES:
        cand = sorted(by_code.get(code) or [])
        if not cand:
            print(f"  ⚠ 跳过（无 {code} 条目）：{text[:28]}", file=sys.stderr)
            continue
        qs.append({"q": text, "id": cand[0], "src": f"真实送审句·{code}", "codes": [code]})

    # ── 去重（同 id + 同题干）并校验 id 存在 ──
    seen, final = set(), []
    for x in qs:
        k = (x["q"], x["id"])
        if k in seen:
            continue
        seen.add(k)
        if x["id"] not in ids:
            print(f"  ❌ 期望条目不存在：{x['id']}", file=sys.stderr)
            return 3
        final.append(x)

    L = []
    L.append("# 黄金问题集（内容治理 · 措辞表达库）— 技术侧种子集")
    L.append("")
    L.append("> 本文件由 `kb/.work/fix_f10_golden.py` 生成。加载器读它的方式是：")
    L.append("> `<子库>/tests/golden-questions-*.md` 里按 `|` 切、`cells[1]` 为题号、`cells[3]` 为**期望条目 id**。")
    L.append("> **覆盖率 = 这些题里 `kb_search` 能在 Top-10 命中期望条目的比例。**")
    L.append(">")
    L.append("> ⚠ **这是种子集，不是定稿**。题干来源两处、都与规则来源表不重叠：")
    L.append("> ① `kb/l7/registry/l7.json → vocabulary` 的类别/子类名（该词表的 prd_source 是 PRD §7.2/§7.3）；")
    L.append("> ② 技术方案 9 案与 L7 自验里的**真实送审原句**。")
    L.append("> **没有**从条目正文摘句子当题干 —— 那样覆盖率就是自己考自己。")
    L.append(">")
    L.append("> 覆盖率只测机器可测的那一半：**「命中」不等于「正文确实覆盖」**，后者是人的活。")
    L.append("> 定稿应由能用这本库的人复核/扩充（目标 30–50 题起），另存一份保留本份作对照。")
    L.append("")
    L.append(f"共 {len(final)} 题。")
    L.append("")
    L.append("| 题号 | 题干 | 期望条目 |")
    L.append("|---|---|---|")
    for i, x in enumerate(final, 1):
        L.append(f"| Q{i} | {x['q']} | `{x['id']}` |")
    L.append("")
    L.append("## 出题依据（同一份，便于复核）")
    L.append("")
    L.append("> ⚠ 本表的首列**故意不写 `Q\\d+`**：加载器是按行扫 `|`、只要 `cells[1]` 匹配 `^Q\\d+$` 就收一道题。")
    L.append("> 若这里也用 Q 编号，同一批题会被收两遍（第二遍的「期望条目」是规则码而非条目 id），")
    L.append("> 覆盖率会被稀释一半 —— 实测第一次就踩了：38 题被收成 76 题、覆盖率从约 0.92 掉到 0.46。")
    L.append("")
    L.append("| 依据 | 来源 | 目标规则码 |")
    L.append("|---|---|---|")
    for i, x in enumerate(final, 1):
        L.append(f"| 依据{i} | {x['src']} | {' / '.join(x['codes'])} |")
    L.append("")
    out = "\n".join(L)

    if a.out:
        open(a.out, "w", encoding="utf-8").write(out)
        print(f"✅ 写入 {a.out}  （{len(final)} 题，{len(out.encode())} 字节）")
    else:
        print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
