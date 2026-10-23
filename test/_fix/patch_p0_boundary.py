#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""一次性补丁：让 H03 的**边界表述**「未经备案的临床/科学背书」命中 P0（Owner 2026-10-21 验收）

病灶（实测，不是推断）
----------------------
Owner 把规则库里的「边界内容」逐条送审，H01/H02/H04/H05 都 BLOCK，唯独 H03 回 PASS：

    $ sh kb/kbpy l7/review-engine/core/with_kb_evidence.py \
        --text "未经备案的临床/科学背书" --allow-no-layer-preflight ...
    decision= PASS issues= 0

两层原因，缺一条都修不好：
  ① 覆盖缺口：H03 的 `patterns` 只有 9 个**检测关键词**（clinically proven…），
     而「未经备案的临床/科学背书」是它的**边界表述**（源字段「边界内容」），从来没进过词表。
  ② 白名单吞：只把词加进 `patterns` **仍然 0 命中** —— 整句落在本规则否定白名单
     `(…|未经|…)[^。]{0,20}(…|临床|…)` 的跨度里（「未经」+备案的+「临床」）⇒ `inside()` 判死。

修法（三处，缺一不可）
----------------------
  A. `kb/l5/p0_patterns.jsonl`：H03 加词 + 标 `whitelist_exempt_terms`（**当前生效的那份表**）
  B. `kb/l5/matcher.py`：认 `whitelist_exempt_terms`（规则名逐字出现即命中，白名单不豁免）
     + 自证正例（必须 HIT）与反向对照（否定句仍须 MISS）
  C. 生成器 `kb/.work/l5_export.py`：重建时不再丢（否则下次 `--apply` 静默回退）
  D. `kb/l8/p0_regression.py`：把 `verbatim_rule_text` 词也纳入回归（新词从此**有执行点**）
"""
import io
import json
import os
import shutil
import sys

ROOT = "/Users/lute/project/audit_multi_content/内容治理知识库"
BACKUP = "/Users/lute/project/audit_multi_content/test/_fix/backup"

TERM = "未经备案的临床/科学背书"


def backup(rel):
    src = os.path.join(ROOT, rel)
    dst = os.path.join(BACKUP, rel.replace("/", "__"))
    os.makedirs(BACKUP, exist_ok=True)
    if os.path.exists(src):
        shutil.copy2(src, dst)
    return src


def sub_once(text, old, new, what):
    n = text.count(old)
    assert n == 1, "锚点不唯一（%d 处）：%s" % (n, what)
    return text.replace(old, new)


# ---------------------------------------------------------------- A. 模式表
p = backup("kb/l5/p0_patterns.jsonl")
rows = [json.loads(l) for l in io.open(p, encoding="utf-8") if l.strip()]
hit = 0
for r in rows:
    if r.get("rule_code") != "H03":
        continue
    hit += 1
    if TERM not in r["patterns"]:
        r["patterns"] = list(r["patterns"]) + [TERM]
    mt = list(r.get("match_terms") or [])
    if not any((t or {}).get("term") == TERM for t in mt):
        mt.append({"anchor": TERM, "basis": "verbatim_rule_text", "term": TERM})
    r["match_terms"] = mt
    vs = dict(r.get("variant_sources") or {})
    lit = list(vs.get("literal_from_source") or [])
    if TERM not in lit:
        lit.append(TERM)
    vs["literal_from_source"] = lit
    r["variant_sources"] = vs
    r["whitelist_exempt_terms"] = [TERM]
assert hit == 1, "H03 行数不是 1：%d" % hit
with io.open(p, "w", encoding="utf-8") as fh:
    for r in rows:
        fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
print("[A] 模式表已改：H03 += %s（patterns / match_terms / variant_sources / whitelist_exempt_terms）" % TERM)

# ---------------------------------------------------------------- B. matcher
p = backup("kb/l5/matcher.py")
s = io.open(p, encoding="utf-8").read()

s = sub_once(s, """    for r in rules:
        kws = []
        for kw in r["patterns"]:
            k = norm(kw)
            if not k:
                continue
            if CJK.search(k):
                kws.append((kw, re.compile(re.escape(k))))
            else:
                kws.append((kw, re.compile(r'(?<![A-Za-z0-9])' + re.escape(k) + r'(?![A-Za-z0-9])')))
        r["_kw"] = kws""",
"""    for r in rules:
        # ★ 2026-10-21：规则名/边界表述（`whitelist_exempt_terms`）—— **逐字出现即命中，白名单一律不豁免**。
        #   病灶（实测）：H03 的边界表述「未经备案的临床/科学背书」整句落在本规则否定白名单
        #   `(…|未经|…)[^。]{0,20}(…|临床|…)` 的跨度里（「未经」+「备案的」+「临床」）⇒
        #   只把词加进 `patterns` 仍 **0 命中**（加词等于白加）。它是**规则名**，不是被否定的宣称。
        #   代价（明写）：`禁用表达：<规则名>` 这类清单行也会 BLOCK —— 与 SELFTEST 里
        #   「取不豁免一侧（漏放是真红线）」同口径。
        r["_wl_exempt"] = {norm(t) for t in (r.get("whitelist_exempt_terms") or []) if norm(t)}
        kws = []
        for kw in r["patterns"]:
            k = norm(kw)
            if not k:
                continue
            _ex = k in r["_wl_exempt"]
            if CJK.search(k):
                kws.append((kw, re.compile(re.escape(k)), _ex))
            else:
                kws.append((kw, re.compile(r'(?<![A-Za-z0-9])' + re.escape(k) + r'(?![A-Za-z0-9])'), _ex))
        r["_kw"] = kws""", "compile_patterns 的词表构建")

s = sub_once(s, """        parts = [re.escape(k) for k, _ in r["_kw"]] + [p for p, _ in r["_rx"]]""",
"""        parts = [re.escape(k) for k, _rx, _ex in r["_kw"]] + [p for p, _ in r["_rx"]]""",
"预筛 alternation")

s = sub_once(s, """        for kind, pairs in (("keyword", r["_kw"]), ("regex", r["_rx"])):
            for label, rx in pairs:
                for m in rx.finditer(t):
                    if not inside(m.start(), spans):""",
"""        for kind, pairs in (("keyword", r["_kw"]), ("regex", r["_rx"])):
            for item in pairs:
                label, rx = item[0], item[1]
                # `whitelist_exempt_terms`（规则名/边界表述）：forced=True ⇒ 白名单不参与判定
                forced = bool(item[2]) if kind == "keyword" else False
                for m in rx.finditer(t):
                    if forced or not inside(m.start(), spans):""",
"_line_hits 的白名单判定")

s = sub_once(s, """        "采用无痛设计，缓解疼痛，帮助催奶增产。",""",
"""        # ★ 2026-10-21（Owner 验收：把「未经备案的临床/科学背书」送审，守衡回了 PASS）：
        #   H03 的**边界表述**逐字送审必须命中。改前实测 MISS；补词后**仍 MISS**（被否定白名单吞），
        #   故与 `whitelist_exempt_terms` 一并钉在这里 —— 少一半这条就变红。
        "未经备案的临床/科学背书",
        "采用无痛设计，缓解疼痛，帮助催奶增产。",""", "SELFTEST 正例")

s = sub_once(s, """        "The pump cannot treat mastitis.",""",
"""        "The pump cannot treat mastitis.",
        # ★ 反向对照（同上）：这次改动**不许**把否定句豁免带走 ——
        #   「未经临床证明」是**被否定的宣称**（否定白名单该豁免它），不是规则名。
        "这款产品未经临床证明，也没有科学依据。",""", "SELFTEST 负例")

io.open(p, "w", encoding="utf-8").write(s)
print("[B] matcher.py 已改：whitelist_exempt_terms + 自证正例/反向对照")

# ---------------------------------------------------------------- C. 生成器
p = backup("kb/.work/l5_export.py")
s = io.open(p, encoding="utf-8").read()
s = sub_once(s, """    "H03": {   # 未经备案的临床/科学背书（PRD #L478「功效宣称」→ 一票否决域）
        # 零新增词：禁用写法逐字存在于该规则 forbidden_expression
        # （源：品线内容边界规则库 recvuJP1dD4jGX，严格限制红线/高危），src_frags 自动取到。
        "literal": [], "synonym": [],
    },""",
"""    "H03": {   # 未经备案的临床/科学背书（PRD #L478「功效宣称」→ 一票否决域）
        # 检测关键词零新增词：禁用写法逐字存在于该规则 forbidden_expression
        # （源：品线内容边界规则库 recvuJP1dD4jGX，严格限制红线/高危），src_frags 自动取到。
        # ★ 2026-10-21（Owner 验收：把「未经备案的临床/科学背书」送审，守衡回了 PASS）：
        #   **规则自己的边界表述**也要能命中 —— 它逐字存在于该规则的 `rule_text`（源字段「边界内容」），
        #   故走 `literal` 表，`grounding()` 会给它 `basis=verbatim_rule_text`（有溯源，不是编的词）。
        #   只加词不够：整句落在否定白名单跨度里 ⇒ 同时进 `WHITELIST_EXEMPT`（见下方常量）。
        "literal": ["未经备案的临床/科学背书"], "synonym": [],
    },""", "VARIANTS.H03")

s = sub_once(s, """# ---------- 生成模式
def norm(s):""",
"""#: 规则名 / 边界表述：逐字出现即命中，**否定白名单一律不豁免**（它是规则名，不是被否定的宣称）。
#   病灶（2026-10-21 实测）：H03 的边界表述「未经备案的临床/科学背书」整句落在否定白名单
#   `(…|未经|…)[^。]{0,20}(…|临床|…)` 的跨度里（「未经」+「备案的」+「临床」）⇒ 只加词仍 0 命中。
#   消费方：`kb/l5/matcher.py` 的 `compile_patterns()` / `_line_hits()`（不是注释，是判据）。
WHITELIST_EXEMPT = {"H03": ["未经备案的临床/科学背书"]}


# ---------- 生成模式
def norm(s):""", "WHITELIST_EXEMPT 常量")

s = sub_once(s, """        whitelist=wl,
        whitelist_allowed_expressions=wl_note,""",
"""        whitelist=wl,
        whitelist_allowed_expressions=wl_note,
        # ★ 2026-10-21：规则名/边界表述（逐字出现即命中，白名单不豁免）—— 见上方常量注释
        whitelist_exempt_terms=list(WHITELIST_EXEMPT.get(code) or []),""", "patterns.append 的字段")

io.open(p, "w", encoding="utf-8").write(s)
print("[C] 生成器 l5_export.py 已改：重建不再丢")

# ---------------------------------------------------------------- D. 回归
p = backup("kb/l8/p0_regression.py")
s = io.open(p, encoding="utf-8").read()
s = sub_once(s, """            if (t.get("basis") or "") != "verbatim_source":
                continue""",
"""            # ★ 2026-10-21：`verbatim_rule_text` 也收 —— 它们**逐字取自规则自己的边界/处理字段**
            #   （如 H03 的边界表述「未经备案的临床/科学背书」，源字段「边界内容」），
            #   同样属于「P0 规则应命中」；不收的话这类新增词**永远没有回归守着**。
            #   实测（宽化前）：19 条 verbatim_rule_text 词 **19/19 命中** ⇒ 不引入假红。
            if (t.get("basis") or "") not in ("verbatim_source", "verbatim_rule_text"):
                continue""", "positive_cases 的 basis 过滤")

s = sub_once(s, """    print("★ 用例 = 每条模式的 `match_terms` 里 basis=verbatim_source 的**逐字源表达**（不自己编）\\n")""",
"""    print("★ 用例 = 每条模式的 `match_terms` 里 basis=verbatim_source / verbatim_rule_text 的"
          "**逐字源表达**（不自己编；后者=规则自己的边界/处理字段，2026-10-21 起纳入）\\n")""",
"run() 的说明行")
io.open(p, "w", encoding="utf-8").write(s)
print("[D] p0_regression.py 已改：verbatim_rule_text 纳入回归")

# ---------------------------------------------------------------- 附：l5.json 的 term_grounding
p = backup("kb/l5/registry/l5.json")
d = json.loads(io.open(p, encoding="utf-8").read())
tg = d.get("term_grounding")
if isinstance(tg, dict):
    tg[TERM] = "verbatim_rule_text"
    io.open(p, "w", encoding="utf-8").write(json.dumps(d, ensure_ascii=False, indent=2))
    print("[E] l5.json term_grounding += %s" % TERM)
else:
    print("[E] l5.json 没有 term_grounding，跳过")

print("完成。")
