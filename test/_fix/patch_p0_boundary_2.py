#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""补丁 2（Owner 2026-10-21 选定「一并补」）：H06 / H08 / H09 的边界表述也进词表
+ 顺手修掉途中发现的**预筛假阴性**（`_pre` 用的是未归一化原词）。

为什么必须先修预筛
------------------
H06 的那句边界表述里带**全角括号/全角逗号**，而 `compile_patterns` 的预筛
`_pre` 是拿 `re.escape(原词)` 拼的 —— 原词没做 NFKC，而待匹配文本做了 ⇒
`_pre.search()` 直接不成立 ⇒ **整条规则在该行被跳过**（kw 正则其实命中在 0）。
实测：`_pre search: False` 而 `kw at 0`。预筛的语义本来是「超集」，用未归一化的词
连超集都不是 —— 这是假阴性，不是性能问题。
修法：`_pre` 用**归一化后**的词拼（`re.escape(norm(k))`），与 `_kw` 的编译口径一致。
"""
import io
import json
import shutil

ROOT = "/Users/lute/project/audit_multi_content/内容治理知识库"
BACKUP = "/Users/lute/project/audit_multi_content/test/_fix/backup"

BND = {
    "H06": "FDA 表述错误（吸奶器为 cleared/registered，非 approved/certified）",
    "H08": "无数据支撑的违法对比 / 贬低竞品",
    "H09": "智能闭环/仿生虚假宣称（自动识别节奏、模拟/复制宝宝、饱腹反馈、降低奶量焦虑）；"
           "W1当前为用户主动调节+保存程序，非闭环生理识别",
}


def backup(rel):
    src = ROOT + "/" + rel
    shutil.copy2(src, BACKUP + "/" + rel.replace("/", "__"))
    return src


def sub_once(text, old, new, what):
    assert text.count(old) == 1, "锚点不唯一：%s" % what
    return text.replace(old, new)


# ---------------------------------------------------------- 1. 模式表（当前生效那份）
p = backup("kb/l5/p0_patterns.jsonl")
rows = [json.loads(l) for l in io.open(p, encoding="utf-8") if l.strip()]
done = 0
for r in rows:
    code = r.get("rule_code")
    if code not in BND:
        continue
    done += 1
    term = BND[code]
    if term not in r["patterns"]:
        r["patterns"] = list(r["patterns"]) + [term]
    mt = list(r.get("match_terms") or [])
    if not any((t or {}).get("term") == term for t in mt):
        mt.append({"anchor": term, "basis": "verbatim_rule_text", "term": term})
    r["match_terms"] = mt
    vs = dict(r.get("variant_sources") or {})
    b = list(vs.get("boundary_from_source") or [])
    if term not in b:
        b.append(term)
    vs["boundary_from_source"] = b
    r["variant_sources"] = vs
assert done == 3, "只命中 %d 条" % done
with io.open(p, "w", encoding="utf-8") as fh:
    for r in rows:
        fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
print("[1] 模式表：H06 / H08 / H09 边界表述已进词表")

# ---------------------------------------------------------- 2. matcher（预筛口径）
p = backup("kb/l5/matcher.py")
s = io.open(p, encoding="utf-8").read()
s = sub_once(s, """        parts = [re.escape(k) for k, _rx, _ex in r["_kw"]] + [p for p, _ in r["_rx"]]""",
"""        # ★ 2026-10-21（补 H06 边界表述时实测到的**假阴性**）：这里原先是 `re.escape(k)`，
        #   而 `k` 是**原词**（未归一化）——待匹配文本却做过 NFKC/空白折叠。
        #   ⇒ 凡是词里带全角括号/全角逗号的，预筛 `search()` 恒不成立 ⇒ **整条规则在该行被跳过**。
        #   实测：H06 的边界表述 `kw at 0` 命中，而同句 `_pre.search(...) == False`。
        #   预筛的语义是「超集」，用未归一化的词连超集都不是。改成与 `_kw` 编译同一口径。
        parts = [re.escape(norm(k)) for k, _rx, _ex in r["_kw"]] + [p for p, _ in r["_rx"]]""",
"预筛 alternation")
s = sub_once(s, """        "未经备案的临床/科学背书",""",
"""        "未经备案的临床/科学背书",
        # ★ 2026-10-21（同上，Owner 选定「一并补」）：H06 的边界表述。
        #   它同时钉住**预筛归一化**那条 bug —— 句里有全角括号，`_pre` 不归一化就整行跳过。
        "FDA 表述错误（吸奶器为 cleared/registered，非 approved/certified）",
        # 同批：H08 / H09 的边界表述
        "无数据支撑的违法对比 / 贬低竞品",
        "智能闭环/仿生虚假宣称（自动识别节奏、模拟/复制宝宝、饱腹反馈、降低奶量焦虑）；"
        "W1当前为用户主动调节+保存程序，非闭环生理识别",""",
"SELFTEST 正例（H06/H08/H09）")
io.open(p, "w", encoding="utf-8").write(s)
print("[2] matcher：预筛改归一化词 + 三条正例")

# ---------------------------------------------------------- 3. 生成器
p = backup("kb/.work/l5_export.py")
s = io.open(p, encoding="utf-8").read()
s = sub_once(s, """        # ★ 2026-10-21（Owner 验收：把「未经备案的临床/科学背书」送审，守衡回了 PASS）：
        #   **规则自己的边界表述**也要能命中 —— 它逐字存在于该规则的 `rule_text`（源字段「边界内容」），
        #   故走 `literal` 表，`grounding()` 会给它 `basis=verbatim_rule_text`（有溯源，不是编的词）。
        #   只加词不够：整句落在否定白名单跨度里 ⇒ 同时进 `WHITELIST_EXEMPT`（见下方常量）。
        "literal": ["未经备案的临床/科学背书"], "synonym": [],
    },""",
"""        # ★ 2026-10-21：**规则自己的边界表述**另外登记在 `BOUNDARY_TERMS`（见下方常量），
        #   不走本表 —— 本表的纪律是「只列源侧命中片段」，边界表述不是命中片段。
        "literal": [], "synonym": [],
    },""", "VARIANTS.H03 回退到零新增词")

s = sub_once(s, """#: 规则名 / 边界表述：逐字出现即命中，**否定白名单一律不豁免**（它是规则名，不是被否定的宣称）。""",
"""#: 规则自己的**边界表述**（源字段「触发原因」/「边界内容」，逐字，一字未改）。
#   为什么要有这一格（2026-10-21，Owner 验收）：Owner 是**按规则库的「触发原因」列逐条送审**的，
#   于是「这句话命不命中自己那条规则」本身就成了验收口径。而 P0 词表原先只收「检测关键词」，
#   边界表述从来没进过 ⇒ H03 `未经备案的临床/科学背书`、H06 `FDA 表述错误（…）`、
#   H08 `无数据支撑的违法对比 / 贬低竞品`、H09 `智能闭环/仿生虚假宣称（…）` 四条送审回来是 PASS。
#   溯源：四句逐字来自 L0「品线内容边界规则库」（recvuJP1dD4jGX / recvuJP1LVW6E0 / recvuJP1LVUEBx /
#   recvuJYdOb61lT）的触发原因字段；H03/H06/H08 也落在各自 `rule_text` 的「边界：…」段里，
#   H09 落在 `reason` 里 —— 故 `grounding()` 的 rule 池自本日起含 `reason`。
#   ⚠️ 代价（明写）：`禁用表达：<边界表述>` 这类清单行也会 BLOCK；取不漏一侧。
BOUNDARY_TERMS = {
    "H03": ["未经备案的临床/科学背书"],
    "H06": ["FDA 表述错误（吸奶器为 cleared/registered，非 approved/certified）"],
    "H08": ["无数据支撑的违法对比 / 贬低竞品"],
    "H09": ["智能闭环/仿生虚假宣称（自动识别节奏、模拟/复制宝宝、饱腹反馈、降低奶量焦虑）；"
            "W1当前为用户主动调节+保存程序，非闭环生理识别"],
}

#: 规则名 / 边界表述：逐字出现即命中，**否定白名单一律不豁免**（它是规则名，不是被否定的宣称）。""",
"BOUNDARY_TERMS 常量")

s = sub_once(s, """    pool_rule = norm((r.get("rule_text") or "") + " " + (r.get("suggested_replacement") or "")).casefold()""",
"""    # ★ 2026-10-21：`reason` 也进 rule 池 —— H09 的边界表述逐字住在 `reason` 里（不在 rule_text）
    pool_rule = norm((r.get("rule_text") or "") + " " + (r.get("suggested_replacement") or "")
                     + " " + (r.get("reason") or "")).casefold()""",
"pool_rule 含 reason")

s = sub_once(s, """    plist = [m["term"] for m in match_terms]""",
"""    # ★ 2026-10-21：边界表述直接进匹配表（溯源由 BOUNDARY_TERMS 那张表本身承担，见其注释）
    bnd = [norm(x) for x in (BOUNDARY_TERMS.get(code) or []) if norm(x)]
    for _t in bnd:
        match_terms.append({"term": _t, "basis": "verbatim_rule_text", "anchor": _t})
    plist = [m["term"] for m in match_terms]""",
"边界表述进 plist")

s = sub_once(s, """                         "dropped_ungrounded": dropped},""",
"""                         "dropped_ungrounded": dropped, "boundary_from_source": bnd},""",
"variant_sources 带 boundary_from_source")
io.open(p, "w", encoding="utf-8").write(s)
print("[3] 生成器：BOUNDARY_TERMS + reason 进 rule 池 + 输出 boundary_from_source")

# ---------------------------------------------------------- 4. L5 完整性检查的 rule 池
p = backup("kb/.work/l5_integrity.py")
s = io.open(p, encoding="utf-8").read()
s = sub_once(s, """    pool_rule = norm((r.get("rule_text") or "") + " " + (r.get("suggested_replacement") or ""))""",
"""    # ★ 2026-10-21：`reason` 也算规则自己的文本（H09 的边界表述住在 `reason` 里）
    pool_rule = norm((r.get("rule_text") or "") + " " + (r.get("suggested_replacement") or "")
                     + " " + (r.get("reason") or ""))""",
"l5_integrity 的 pool_rule")
s = s.replace('"verbatim_rule_text（逐字在 rule_text 或建议替换里）/ "',
              '"verbatim_rule_text（逐字在 rule_text / 建议替换 / reason 里）/ "')
io.open(p, "w", encoding="utf-8").write(s)
print("[4] l5_integrity：rule 池含 reason")

# ---------------------------------------------------------- 5. registry 的 term_grounding
p = backup("kb/l5/registry/l5.json")
d = json.loads(io.open(p, encoding="utf-8").read())
tg = d.get("term_grounding")
if isinstance(tg, dict):
    for t in BND.values():
        tg[t] = "verbatim_rule_text"
    io.open(p, "w", encoding="utf-8").write(json.dumps(d, ensure_ascii=False, indent=2))
    print("[5] l5.json term_grounding += 3")

print("完成。")
