#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""补丁（Owner 2026-09-21 裁定 A）：**排名/最高级一族退出 P0**，改为非阻断提示。

Owner 原话（本轮）：
    「虚假安全承诺（best/#1/No.1/最佳/最好等排名最高级按2026-09-09口径放开，海外广告允许，
      不再判险）==》既然放开了，为什么还写出来问题？」

裁定 A（已确认）：best / #1 / No.1 / 最佳 / 最好 / 最高级 **不再判险、不进问题清单**；
「第一 / 销量第一」这类中文事实性排名也**不阻断**，只留一句「需补可核验依据」的提示。

为什么改表而不是只改规则文本
--------------------------
同一句话在 09-21 这份报告里被判成 4 处 P0/P1，三处来路（都实测过）：
  ① H05 的 `regex_patterns` 里还留着 `(?:\\bno\\.?\\s*1|#\\s*1)\\b` 与 `最\\s*(…|高|…)`
     —— 10-19 那次「最佳/最好出列」只过滤了 literal/synonym（`exclude` 机制），**正则没出列**；
  ② 10-21 把**规则自己的边界表述**（含「…放开，不再判险」这句）逐字灌进了 `patterns`；
  ③ V03（E-2.126）另有一条 `(?:\\bno\\.?\\s*1…|#\\s*1…)`，同一条 `#1` 被两条规则各报一次。
⇒ 表不改，任何一处都会把「已放开」的东西重新报出来。

代价（明写）
-----------
· PRD §7.3 第 3 条把「最、第一、最佳…」列为绝对化用语 P0（2026-10-09 据此作废过 09-09 的放开）。
  本轮 Owner 把口径**收窄**：排名/最高级一族放开；`100%` / `纯天然` / `最安全` **仍在** P0。
· 事实性排名（销量第一、sold 6 million）仍按「需补可核验依据」处理：数量类留在 V03（P0），
  排名类降为非阻断提示（`p0_fastpath.RANK_ADVISORY_RX`）。
"""
import io
import json
import os
import shutil

ROOTS = [
    ("repo", "/Users/lute/project/audit_multi_content/内容治理知识库"),
    ("live", os.path.expanduser(
        "~/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理")),
]
BACKUP = "/Users/lute/project/audit_multi_content/test/_fix/backup_relax"

RULING = "owner-2026-09-21-A（排名/最高级一族退出 P0；中文事实性排名降为非阻断提示）"

# 逐字命中的边界表述（口径说明，不是触发词）
H05_BND = ("虚假安全承诺（best/#1/No.1/最佳/最好等排名最高级按2026-09-09口径放开，"
           "海外广告允许，不再判险）")

# 退出 P0 的正则（按去掉所有空白后比对，避免转义/空格差异造成「改了等于没改」）
DROP_REGEX = {
    "H05": [
        r"(?:\bno\.?\s*1|#\s*1)\b",
        r"(排名|销量|全网|行业|品类|国内|全球|世界|亚洲)\s*第一",
        r"第一\s*(品牌|选择|名|款|位)",
        r"最佳",
        r"\bbest\b",
    ],
    "V03": [
        r"(?:\bno\.?\s*1\b|\B#\s*1\b|\bnumber\s*one\b)",
        r"(?:销量|销售|出货|售出|累计|全美|全球|全国|全网|美国|北美)[^。，,；;]{0,8}(?:第一|冠军|领先|no\.?\s*1|#\s*1)",
        r"(?:第一|冠军|榜首)[^。，,；;]{0,6}(?:销量|品牌|排名|名)",
        r"\b(?:best[- ]?selling|top[- ]?seller|number[- ]one)\b",
    ],
}
# 整条换掉的正则：`最(…高…)` 里的 `高` 是「最高级」，按裁定 A 放开；`佳`=最佳，同理
REPLACE_REGEX = {
    "H05": [
        (r"最\s*(佳|优|强|安全|低价|便宜|有效|快|大|高|省|舒适)",
         r"最\s*(优|强|安全|低价|便宜|有效|快|大|省|舒适)"),
        (r"最\s*(安全|低价|便宜|有效|快|大|高|省)",
         r"最\s*(安全|低价|便宜|有效|快|大|省)"),
    ],
}
DROP_TERMS = {
    "H05": [H05_BND],
    "V03": ["排名第一", "销量第一", "销量领先"],
}


def _squash(s):
    return "".join(str(s or "").split())


def patch(root):
    p = os.path.join(root, "kb/l5/p0_patterns.jsonl")
    os.makedirs(BACKUP, exist_ok=True)
    shutil.copy2(p, os.path.join(BACKUP, os.path.basename(root) + "__p0_patterns.jsonl"))
    rows = [json.loads(l) for l in io.open(p, encoding="utf-8") if l.strip()]
    touched = {}
    for r in rows:
        code = r.get("rule_code")
        if code not in DROP_REGEX and code not in DROP_TERMS:
            continue
        removed = {"terms": [], "regex": [], "boundary": []}
        # ① 字面词
        drop_terms = {_squash(t) for t in DROP_TERMS.get(code, [])}
        keep = []
        for t in r.get("patterns") or []:
            if _squash(t) in drop_terms:
                removed["terms"].append(t)
            else:
                keep.append(t)
        r["patterns"] = keep
        mt = []
        for t in r.get("match_terms") or []:
            if _squash((t or {}).get("term")) in drop_terms:
                removed["terms"].append((t or {}).get("term"))
            else:
                mt.append(t)
        r["match_terms"] = mt
        # ② 正则
        drop_rx = {_squash(x) for x in DROP_REGEX.get(code, [])}
        rx = []
        for x in r.get("regex_patterns") or []:
            if _squash(x) in drop_rx:
                removed["regex"].append(x)
                continue
            for old, new in REPLACE_REGEX.get(code, []):
                if _squash(x) == _squash(old):
                    removed["regex"].append(x)
                    x = new
                    break
            rx.append(x)
        r["regex_patterns"] = rx
        # ③ 边界表述：口径说明不是触发词（它写着「放开」，把它当触发词＝自证其反）
        vs = dict(r.get("variant_sources") or {})
        bnd = list(vs.get("boundary_from_source") or [])
        kept_bnd = []
        for b in bnd:
            if _squash(b) in drop_terms:
                removed["boundary"].append(b)
            else:
                kept_bnd.append(b)
        vs["boundary_from_source"] = kept_bnd
        # ④ 留痕：出列的东西不许静默消失
        old = dict(vs.get("relaxed_by_ruling") or {})
        if removed["terms"] or removed["regex"] or removed["boundary"]:
            old["ruling"] = RULING
            old["removed_terms"] = sorted(set((old.get("removed_terms") or []) + removed["terms"]))
            old["removed_regex"] = sorted(set((old.get("removed_regex") or []) + removed["regex"]))
            old["removed_boundary"] = sorted(set((old.get("removed_boundary") or [])
                                                 + removed["boundary"]))
            vs["relaxed_by_ruling"] = old
        r["variant_sources"] = vs
        touched[code] = removed
    with io.open(p, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
    return touched


for label, root in ROOTS:
    t = patch(root)
    print("[%s] %s" % (label, os.path.basename(root)))
    for code, rem in sorted(t.items()):
        print("   %-4s terms=%d regex=%d boundary=%d" % (
            code, len(rem["terms"]), len(rem["regex"]), len(rem["boundary"])))
        for x in rem["regex"]:
            print("        - rx %s" % x[:90])
        for x in rem["terms"]:
            print("        - term %s" % str(x)[:90])
