#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""补丁 4（Owner 2026-10-21：「这是未标注来源的效果数据声明吗？」→「补」）

把「效果百分比宣称」这个**形态**补进 P0，而不是再枚举几个字面词。

病灶
----
P0 词表里跟效果数据有关的**全是字面枚举**：`28% faster` / `30% more milk` / `trusted by 6 million`…
于是 `95% of users saw results in 2 weeks` 这种**同族但换个写法**的句子直接穿过去：
实测 P0 快路 `hit=False`、链回 `REVIEW/0 条`（覆盖缺口，不是 PASS）。

口径（库内原文，不是我编的）
--------------------------
· `kb/l3/candidates/rules.jsonl` → `rule_code=M03`、`p_level=P0`、
  边界「**未标注来源的效果数据声明**」（`r-d00103c52a98512e`，条款号 W-1.51；
  与快路里导出的 `r-4f309d6ebde80283`／W-1.25 **同 rule_code**）
· 处理口径逐字：「**效果百分比/销量/评分声称需附测试来源与口径，否则删除（折扣百分比不在此列）**」
  —— 括号里那句就是本次白名单的依据：**折扣不算效果宣称**。

落点
----
1. `kb/l5/p0_patterns.jsonl`（M03 行 / r-4f309d6ebde80283，**快路里已导出的那条**）：
   `regex_patterns` 加 9 条形态；`whitelist` 加 7 条排除（折扣 / 成分占比）
2. `kb/l5/matcher.py`：自证加 2 正例 + 3 反向对照（折扣、成分、纯时长）
3. `kb/.work/l5_export.py`：常量 `EFFECT_DATA_REGEX` / `EFFECT_DATA_WHITELIST`，重建不丢
4. `kb/l8/p0_regression.py`：正则**没有逐字词**，`match_terms` 收不到 ⇒ 单列 `REGEX_CASES`
   （含反向对照），否则这批正则**没有任何回归守着**

两份库都落：`$KB_ROOT`（守衡真正读的那份）＋ 本仓快照。
"""
import io
import json
import os
import shutil

ROOTS = [
    os.path.expanduser("~/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理/kb"),
    "/Users/lute/project/audit_multi_content/内容治理知识库/kb",
]
BACKUP = "/Users/lute/project/audit_multi_content/test/_fix/backup_pct"

M03_RID = "r-4f309d6ebde80283"

EFFECT_RX = [
    r"\b\d+(?:\.\d+)?\s*%\s*(?:more|less|fewer|faster|slower|better|stronger|longer|quicker|higher|lower)\b",
    r"\b\d+(?:\.\d+)?\s*%\s*(?:increase|decrease|reduction|improvement|boost|lift)\b",
    r"\b\d+(?:\.\d+)?\s*%\s*of\s+(?:users|moms|mothers|customers|participants|women|people|parents|babies|infants)\b"
    r"[^.!?]{0,40}\b(?:saw|see|noticed|reported|experienced|felt|found|had|achieved|got|recommend|love|prefer)\b",
    r"\b\d+(?:\.\d+)?\s*x\s+(?:more|faster|better|stronger|longer|quicker)\b",
    r"\b(?:twice|two\s+times|three\s+times|\d+\s+times)\s+as\s+(?:fast|much|many|effective|strong)\b",
    r"\b\d+(?:\.\d+)?\s*%[^.!?]{0,40}\bin\s+(?:just\s+|only\s+)?\d+(?:\.\d+)?\s*(?:days?|weeks?|months?|hours?)\b",
    r"\d+(?:\.\d+)?\s*%\s*的?\s*(?:用户|妈妈|宝妈|产妇|消费者|受试者|客户)",
    r"\d+(?:\.\d+)?\s*%\s*(?:提升|提高|增加|减少|降低|更快|更好|有效|改善)",
    r"(?:提升|提高|增加|减少|降低)(?:了)?\s*\d+(?:\.\d+)?\s*%",
]
EFFECT_WL = [
    r"\b\d+(?:\.\d+)?\s*%\s*(?:off|discount|sale|savings?|coupon|promo|code)\b",
    r"\b(?:save|saving|save\s+up\s+to|discount)\s*(?:up\s*to\s*)?\d+(?:\.\d+)?\s*%",
    r"\b(?:off|discount|sale|coupon|promo|code)\b[^.!?]{0,20}\d+(?:\.\d+)?\s*%",
    r"\d+(?:\.\d+)?\s*%\s*(?:off|折扣|优惠)",
    r"(?:折扣|优惠|立减|满减)[^。]{0,12}\d+(?:\.\d+)?\s*%",
    r"\b\d+(?:\.\d+)?\s*%\s*(?:cotton|wool|polyester|silicone|steel|plastic|bamboo|bpa|water|ingredients?|recycled)\b",
    r"\d+(?:\.\d+)?\s*%\s*(?:棉|羊毛|聚酯|硅胶|不锈钢|食品级|成分)",
]

GEN_BLOCK = '''
#: ★★ 2026-10-21（Owner：「这是未标注来源的效果数据声明吗？」→「补」）：
#   **效果百分比宣称的形态**（不是再枚举字面词）。
#   病灶：P0 词表里这类全是字面（`28% faster`/`30% more milk`/`trusted by 6 million`），
#   于是 `95% of users saw results in 2 weeks` 这种同族写法直接穿过去（实测快路 hit=False）。
#   口径：L3 `rule_code=M03 / p_level=P0` 边界「未标注来源的效果数据声明」，处理口径逐字
#   「效果百分比/销量/评分声称需附测试来源与口径，否则删除（**折扣百分比不在此列**）」
#   ⇒ 正则抓形态，白名单按括号里那句话把**折扣与成分占比**排除掉。
EFFECT_DATA_REGEX = [
    r"\\b\\d+(?:\\.\\d+)?\\s*%\\s*(?:more|less|fewer|faster|slower|better|stronger|longer|quicker|higher|lower)\\b",
    r"\\b\\d+(?:\\.\\d+)?\\s*%\\s*(?:increase|decrease|reduction|improvement|boost|lift)\\b",
    r"\\b\\d+(?:\\.\\d+)?\\s*%\\s*of\\s+(?:users|moms|mothers|customers|participants|women|people|parents|babies|infants)\\b"
    r"[^.!?]{0,40}\\b(?:saw|see|noticed|reported|experienced|felt|found|had|achieved|got|recommend|love|prefer)\\b",
    r"\\b\\d+(?:\\.\\d+)?\\s*x\\s+(?:more|faster|better|stronger|longer|quicker)\\b",
    r"\\b(?:twice|two\\s+times|three\\s+times|\\d+\\s+times)\\s+as\\s+(?:fast|much|many|effective|strong)\\b",
    r"\\b\\d+(?:\\.\\d+)?\\s*%[^.!?]{0,40}\\bin\\s+(?:just\\s+|only\\s+)?\\d+(?:\\.\\d+)?\\s*(?:days?|weeks?|months?|hours?)\\b",
    r"\\d+(?:\\.\\d+)?\\s*%\\s*的?\\s*(?:用户|妈妈|宝妈|产妇|消费者|受试者|客户)",
    r"\\d+(?:\\.\\d+)?\\s*%\\s*(?:提升|提高|增加|减少|降低|更快|更好|有效|改善)",
    r"(?:提升|提高|增加|减少|降低)(?:了)?\\s*\\d+(?:\\.\\d+)?\\s*%",
]

#: 折扣 / 成分占比 —— **不是效果宣称**（PRD 处理口径原文「折扣百分比不在此列」）。
EFFECT_DATA_WHITELIST = [
    r"\\b\\d+(?:\\.\\d+)?\\s*%\\s*(?:off|discount|sale|savings?|coupon|promo|code)\\b",
    r"\\b(?:save|saving|save\\s+up\\s+to|discount)\\s*(?:up\\s*to\\s*)?\\d+(?:\\.\\d+)?\\s*%",
    r"\\b(?:off|discount|sale|coupon|promo|code)\\b[^.!?]{0,20}\\d+(?:\\.\\d+)?\\s*%",
    r"\\d+(?:\\.\\d+)?\\s*%\\s*(?:off|折扣|优惠)",
    r"(?:折扣|优惠|立减|满减)[^。]{0,12}\\d+(?:\\.\\d+)?\\s*%",
    r"\\b\\d+(?:\\.\\d+)?\\s*%\\s*(?:cotton|wool|polyester|silicone|steel|plastic|bamboo|bpa|water|ingredients?|recycled)\\b",
    r"\\d+(?:\\.\\d+)?\\s*%\\s*(?:棉|羊毛|聚酯|硅胶|不锈钢|食品级|成分)",
]


'''


def backup(root, rel):
    tag = "live" if "Documents" in root else "repo"
    os.makedirs(BACKUP, exist_ok=True)
    shutil.copy2(os.path.join(root, rel), os.path.join(BACKUP, "%s__%s" % (tag, rel.replace("/", "__"))))


def sub_once(text, old, new, what):
    assert text.count(old) == 1, "锚点不唯一（%d）：%s" % (text.count(old), what)
    return text.replace(old, new)


for ROOT in ROOTS:
    tag = "live" if "Documents" in ROOT else "repo"
    print("=== %s（%s）" % (tag, ROOT))

    # 1) 模式表
    rel = "l5/p0_patterns.jsonl"
    p = os.path.join(ROOT, rel)
    backup(ROOT, rel)
    rows = [json.loads(l) for l in io.open(p, encoding="utf-8") if l.strip()]
    hit = 0
    for r in rows:
        if r.get("rule_id") != M03_RID:
            continue
        hit += 1
        rx = list(r.get("regex_patterns") or [])
        for x in EFFECT_RX:
            if x not in rx:
                rx.append(x)
        r["regex_patterns"] = rx
        wl = list(r.get("whitelist") or [])
        for x in EFFECT_WL:
            if x not in wl:
                wl.append(x)
        r["whitelist"] = wl
        vs = dict(r.get("variant_sources") or {})
        vrx = list(vs.get("regex") or [])
        for x in EFFECT_RX:
            if x not in vrx:
                vrx.append(x)
        vs["regex"] = vrx
        vs["effect_data_regex_from"] = (
            "Owner 2026-10-21 裁定补「效果百分比」泛化形态；口径见 L3 M03 "
            "r-d00103c52a98512e（W-1.51）边界「未标注来源的效果数据声明」")
        r["variant_sources"] = vs
    assert hit == 1, "%s: M03 行数=%d" % (tag, hit)
    with io.open(p, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
    print("  [1] p0_patterns.jsonl：M03 += %d 条正则 / %d 条白名单" % (len(EFFECT_RX), len(EFFECT_WL)))

    # 2) matcher 自证
    rel = "l5/matcher.py"
    p = os.path.join(ROOT, rel)
    backup(ROOT, rel)
    s = io.open(p, encoding="utf-8").read()
    if "95% of users saw results in 2 weeks" not in s:
        s = sub_once(s, """        "未经备案的临床/科学背书",""",
"""        "未经备案的临床/科学背书",
        # ★ 2026-10-21（Owner：「这是未标注来源的效果数据声明吗？」→「补」）：
        #   效果百分比的**形态**（不是字面词）—— 改前实测 MISS（词表只有 28% faster / trusted by 6 million）。
        "95% of users saw results in 2 weeks",
        "98% 的用户反馈有效",   # 中文同族：百分比 + 人群
""", "SELFTEST 正例（效果百分比）")
    if "Save 20% off with code MOM20." not in s:
        s = sub_once(s, """        "这款产品未经临床证明，也没有科学依据。",""",
"""        "这款产品未经临床证明，也没有科学依据。",
        # ★ 反向对照（效果百分比）——**折扣不是效果宣称**（PRD 处理口径原文「折扣百分比不在此列」）；
        #   成分占比、纯时长同理。这三条钉住白名单：拆掉 EFFECT_DATA_WHITELIST 立刻变红。
        "Save 20% off with code MOM20.",
        "95% cotton, 5% spandex.",
        "The discount is 15% and delivery in 2 weeks.",
""", "SELFTEST 负例（折扣/成分）")
    io.open(p, "w", encoding="utf-8").write(s)
    print("  [2] matcher.py：+2 正例 / +3 反向对照")

    # 3) 生成器
    rel = ".work/l5_export.py"
    p = os.path.join(ROOT, rel)
    backup(ROOT, rel)
    s = io.open(p, encoding="utf-8").read()
    if "EFFECT_DATA_REGEX" not in s:
        s = sub_once(s, """# ---------- 生成模式
def norm(s):""", GEN_BLOCK.lstrip("\n") + """# ---------- 生成模式
def norm(s):""", "EFFECT_DATA_REGEX 常量")
        s = sub_once(s, """    plist = [m["term"] for m in match_terms]""",
"""    # ★ 2026-10-21：效果百分比**形态**（见 EFFECT_DATA_REGEX 注释）—— 只挂在该 rule_code 上
    if code == "M03":
        rx = list(rx) + [x for x in EFFECT_DATA_REGEX if x not in rx]
    plist = [m["term"] for m in match_terms]""", "M03 正则注入")
        s = sub_once(s, """        whitelist=wl,
        whitelist_allowed_expressions=wl_note,""",
"""        whitelist=(wl + (list(EFFECT_DATA_WHITELIST) if code == "M03" else [])),
        whitelist_allowed_expressions=wl_note,""", "M03 白名单注入")
    io.open(p, "w", encoding="utf-8").write(s)
    print("  [3] l5_export.py：重建不丢")

    # 4) 回归
    rel = "l8/p0_regression.py"
    p = os.path.join(ROOT, rel)
    backup(ROOT, rel)
    s = io.open(p, encoding="utf-8").read()
    if "REGEX_CASES" not in s:
        s = sub_once(s, """#: 反向对照用的无关文本（**不许**命中任何 P0 模式）
NEGATIVE = "今天天气不错，我们去公园走走吧。\"""",
"""#: 反向对照用的无关文本（**不许**命中任何 P0 模式）
NEGATIVE = "今天天气不错，我们去公园走走吧。"

#: `regex_patterns` 的正例 —— **正则不是「逐字词」**，`match_terms` 收不到它们，
#: 光靠上面那条路径等于「这批正则没有任何回归守着」。2026-10-21 加（效果百分比形态）。
REGEX_CASES = {
    "M03": ["95% of users saw results in 2 weeks",
            "30% more milk in just 2 weeks",
            "98% 的用户反馈有效",
            "提升 30% 的奶量"],
}

#: 正则的**反向对照**：折扣 / 成分占比 / 纯时长 —— 必须**不**命中该规则。
REGEX_NEGATIVES = {
    "M03": ["Save 20% off with code MOM20.",
            "95% cotton, 5% spandex.",
            "The discount is 15% and delivery in 2 weeks."],
}\"""", "REGEX_CASES 常量")
        s = sub_once(s, """        out.append({"rule_code": p.get("rule_code"), "rule_id": p.get("rule_id"),
                    "article_no": p.get("article_no"), "terms": terms})""",
"""        terms = terms + list(REGEX_CASES.get(p.get("rule_code")) or [])
        out.append({"rule_code": p.get("rule_code"), "rule_id": p.get("rule_id"),
                    "article_no": p.get("article_no"), "terms": terms})""", "positive_cases 并入正则用例")
        s = sub_once(s, """    neg_res = m.evaluate(NEGATIVE)""",
"""    # 正则的反向对照（折扣/成分/纯时长）：命中即为**误伤**，必须 0
    regex_neg_bad = []
    for code, texts in REGEX_NEGATIVES.items():
        for t in texts:
            cs = codes_of(m.evaluate(t)) or set()
            if code in cs:
                regex_neg_bad.append(t)
    neg_res = m.evaluate(NEGATIVE)""", "正则反向对照")
        s = sub_once(s, """            "neg_hit": (None if neg_codes is None else len(neg_codes)),""",
"""            "neg_hit": (None if neg_codes is None else len(neg_codes)),
            "regex_neg_bad": regex_neg_bad,""", "返回体")
        s = sub_once(s, """    print("反向对照（无关文本）：命中 %s（必须是 0）" % r["neg_hit"])""",
"""    print("反向对照（无关文本）：命中 %s（必须是 0）" % r["neg_hit"])
    print("反向对照（折扣/成分/纯时长）：误伤 %d（必须是 0）%s"
          % (len(r["regex_neg_bad"]), ("：" + "；".join(r["regex_neg_bad"])) if r["regex_neg_bad"] else ""))""",
"打印")
        s = sub_once(s, """    ok = (r["missed"] <= MISS_LIMIT and r["neg_hit"] == 0 and not r["no_case"] and not r["engine_odd"])""",
"""    ok = (r["missed"] <= MISS_LIMIT and r["neg_hit"] == 0 and not r["no_case"]
          and not r["engine_odd"] and not r["regex_neg_bad"])""", "ok 判据")
        s = sub_once(s, """    ck("③ 反向对照：无关文本**不许命中**（判据不是恒真）", r["neg_hit"] == 0, "neg_hit=%s" % r["neg_hit"])""",
"""    ck("③ 反向对照：无关文本**不许命中**（判据不是恒真）", r["neg_hit"] == 0, "neg_hit=%s" % r["neg_hit"])
    ck("③b 反向对照：折扣/成分占比**不许**被当成效果宣称", not r["regex_neg_bad"],
       "误伤=%s" % r["regex_neg_bad"])""", "selftest 断言")
    io.open(p, "w", encoding="utf-8").write(s)
    print("  [4] p0_regression.py：正则用例 + 反向对照")
print("完成。")
