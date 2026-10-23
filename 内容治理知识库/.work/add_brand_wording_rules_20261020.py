#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""add_brand_wording_rules_20261020.py —— 把「品牌写法一致性」落成**可判条款**（L3 候选规则）。

Owner 2026-10-20 裁定：「定下『品牌写法一致性 / 口号地道度』算可判条款」。
本脚本只做**能判的那一半**，并把判不了的那一半写成事实（见 `kb/l7/registry/brand-wording-policy.yaml`）：

  可判（本脚本写入）：品牌名字标的**字符级**错误写法 —— 数字替换字母、品牌名中插入空格。
      例：`M0m222`（本单实测）、`momc0zy`、`m0mcozy`、`mom cozy`。
      引擎口径：`review.py::layer_rules` 把 `forbidden_expression` 按 , ， ; ； 切开后**逐字命中**
      （`norm()` 会 NFKC + 折叠空白 + **casefold**）。

  **判不了（如实说，不硬凑）**：
      · **大小写**：`norm()` casefold ⇒ `MomCozy` 与 `momcozy` 在引擎里是同一个串，
        任何「大小写不一致」的判据都**不可能**命中。要做，得先改引擎的归一化口径（另一件工单）。
      · **口号「地道度」**：库里没有任何「英语够不够地道」的条款，也不该有 ——
        本库两条**正例**（S-1.101 / S-1.109，Witt 瑞典 2C 展会海报）逐字写着
        「Slogan: Evolving for Mom and Cozy（**与需求方确认过使用这个 slogan**）」，
        即该口号是品牌侧确认使用的。把它判成「不地道」会**与本库正例冲突**。

  所以本规则的证据只来自《Momcozy 品牌文案与字体应用规范》（L0 `wiki__RMTWdHAjFoCI7Ax9VTKcLg0KnSc`，
  rev 153，直链 https://momcozy-in.feishu.cn/wiki/QX0Yw2neriOdA3k1giBciQDsn2c），
  不发明「哪个说法不地道」。

用法：
    python3 .work/add_brand_wording_rules_20261020.py            # 预演（只打印）
    python3 .work/add_brand_wording_rules_20261020.py --apply    # 追加到 L3 候选件（只追加，不改旧行）
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # 内容治理
RULES = os.path.join(ROOT, "kb", "l3", "candidates", "rules.jsonl")

RESOURCE = "wiki__RMTWdHAjFoCI7Ax9VTKcLg0KnSc"
ENTRY_URL = "https://momcozy-in.feishu.cn/wiki/QX0Yw2neriOdA3k1giBciQDsn2c"

# 证据单元：全部取自《Momcozy 品牌文案与字体应用规范》（L2 实测坐标，C1 会逐条回指）
EVIDENCE = [
    {"anchor": "#l.3-19", "unit_id": "3f79c2707e10dbbb231e",
     "source_sha256": "bafe1b20212564437dfc5b12017f02585bacf03de6df54c8bb7e9d3b408535f6",
     "what": "本规范用于统一 Momcozy 品牌传播中文案层级、大小写、字体搭配及信息强调方式"},
    {"anchor": "#h.品牌与渠道的责任边界 / Brand / VI 负责", "unit_id": "47bcbc6f8f461942e40e",
     "source_sha256": "bafe1b20212564437dfc5b12017f02585bacf03de6df54c8bb7e9d3b408535f6",
     "what": "Headline 大小写原则 / Brand Keyword 品牌关键词原则——由 Brand/VI 负责"},
    {"anchor": "#h.多语言与本地化原则", "unit_id": "81c65cde06bd28ebb610",
     "source_sha256": "bafe1b20212564437dfc5b12017f02585bacf03de6df54c8bb7e9d3b408535f6",
     "what": "多语言与本地化时仍须保持 Momcozy 品牌视觉逻辑一致（大小写/标点/换行在列）"},
]

# 禁用片段：**只收字符级**差异（数字替换字母 / 品牌名里插空格）。
# ⚠️ 不收大小写变体 —— 引擎 casefold 会把它们与正确写法归一，收了等于给正确写法判红。
FORBIDDEN = "M0m222,momc0zy,m0mcozy,momco2y,m0mco2y,mom cozy,Mom Cozy"

RULE_TEXT = (
    "规则码 BR-01：命中**品牌名字标的字符级错误写法**（以数字替换字母，或在品牌名中插入空格，"
    "如 M0m222／momc0zy／mom cozy）判定为「品牌写法不一致」；"
    "处理：改为登记写法 momcozy（全小写、品牌名是一个词、不留空格），并核对原图实物字标；"
    "**大小写不一致不在本规则范围内**（引擎归一化会把大小写抹平，判不了，见 brand-wording-policy.yaml）。"
)

REPLACEMENT = "momcozy（登记写法：全小写、一个词、无空格）"


def _sha16(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


def build() -> dict:
    rid = "r-" + _sha16("BR-01|" + RULE_TEXT + "|" + RESOURCE)
    digest = hashlib.sha256(
        (RESOURCE + "|" + ",".join(e["unit_id"] for e in EVIDENCE)).encode("utf-8")).hexdigest()
    return {
        "anchor": EVIDENCE[0]["anchor"],
        "applicable_scope": {"channel": None, "content_type": None, "product_line": ["全型号"]},
        "article_no": "",
        "dimensions_derivation": {
            "modality": "字标/品牌名可能出现在图上，也可能写在文案里；引擎在**图内文字的 OCR 文本**上判 ⇒ 按 text 处理（与 W-2.x 措辞类同一口径）",
            "not_derivable": ["applicable_scope.channel", "applicable_scope.product_line", "content_type"],
        },
        "effective_from": "2026-10-20",
        "effective_to": "",
        "entry_url": ENTRY_URL,
        "evidence_digest": digest,
        "evidence_level": "observation",
        "evidence_units": [{"anchor": e["anchor"], "source_sha256": e["source_sha256"],
                            "unit_id": e["unit_id"]} for e in EVIDENCE],
        "evidence_note": "｜".join(e["what"] for e in EVIDENCE),
        "form": "entry",
        "forbidden_expression": FORBIDDEN,
        "half_life_days": 180,
        "kb_type": "wording",
        "kb_version": "v0",
        "modality": "text",
        "owner": "法务",
        "p_level": "P2",
        "reason": "品牌名字标写法与品牌侧规范不一致（数字替换字母 / 品牌名里插空格），"
                  "美国消费者会把它读成乱码，或误认成非官方账号，品牌识别被稀释",
        "risk_level": "Medium",
        "risk_level_basis": "表达与识别类（非功效宣称、非安全）⇒ P2；不阻断发布，转品牌侧核对写法",
        "rule_code": "BR-01",
        "rule_id": rid,
        "rule_text": RULE_TEXT,
        "scope": {"source_table": "Momcozy 品牌文案与字体应用规范", "records": 0,
                  "source_doc": ENTRY_URL},
        "status": "provisional",
        "suggested_replacement": REPLACEMENT,
        "support_count": 1,
        "taxonomy_basis": "品牌名写法的统一 ⇒ 品牌信任与声誉（A3）；子类留空（本库该类只有「品牌口号与价值主张 / 竞品对比与贬低」两个子类，写法一致性不属于任何一个，不硬塞）",
        "taxonomy_category": "品牌信任与声誉",
        "taxonomy_subcategory": None,
        "variant_basis": "禁用片段里只有 `M0m222` 是**本单实测**（AD-20261020-006 图 1 第 4 行 OCR）；"
                         "其余是按字符替换法生成的同族变体，**不是**已发生的事实，登记在此以便命中，"
                         "不声称它们是历史案例",
        "verification": "待验证",
        "kb_rules_added": "brand-wording-20261020",
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    rule = build()
    print("规则：", rule["rule_id"], "｜条款号：待 L4 发号 ｜行数：1")
    print("禁用片段：", rule["forbidden_expression"])
    print("证据：", [(e["unit_id"], e["anchor"]) for e in EVIDENCE])

    # 幂等：同一 rule_id 已在盘上就拒绝重复追加
    if os.path.exists(RULES):
        for line in open(RULES, encoding="utf-8"):
            if rule["rule_id"] in line:
                print("⏭ 这条规则已经在 %s 里（按 rule_id 幂等）—— 不重复追加" % RULES)
                return 0

    # 证据自检：三个 unit_id 必须在 L2 里，且 sha 对得上（与 L3 闸门 C1 同口径）
    units = {}
    for line in open(os.path.join(ROOT, "kb", "l2", "units.jsonl"), encoding="utf-8"):
        for e in EVIDENCE:
            if e["unit_id"] in line:
                r = json.loads(line)
                if r.get("unit_id") == e["unit_id"]:
                    units[e["unit_id"]] = r
    bad = []
    for e in EVIDENCE:
        u = units.get(e["unit_id"])
        if not u:
            bad.append("%s 不在 L2" % e["unit_id"])
        elif u.get("source_sha256") != e["source_sha256"]:
            bad.append("%s sha 对不上" % e["unit_id"])
    if bad:
        print("❌ 证据自检不过：", "；".join(bad))
        return 3
    print("✅ 证据自检：3/3 单元在 L2，sha 逐条相符")

    if not a.apply:
        print("预演通过。要真写加 --apply（只追加一行，不改任何旧行）")
        return 0

    bak = RULES + ".bak-bradd-" + time.strftime("%Y%m%d-%H%M%S")
    shutil.copy2(RULES, bak)
    before = sum(1 for _ in open(RULES, encoding="utf-8"))
    with open(RULES, "a", encoding="utf-8") as f:
        f.write(json.dumps(rule, ensure_ascii=False) + "\n")
    after = sum(1 for _ in open(RULES, encoding="utf-8"))
    # 校验：只多一行，且新行能解析
    ok_new = False
    for line in open(RULES, encoding="utf-8"):
        if rule["rule_id"] in line:
            ok_new = json.loads(line)["rule_id"] == rule["rule_id"]
    print("✅ 已追加：%d → %d 行｜新行可解析=%s｜备份 %s" % (before, after, ok_new, os.path.basename(bak)))
    return 0 if (after == before + 1 and ok_new) else 4


if __name__ == "__main__":
    sys.exit(main())
