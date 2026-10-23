#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""补丁 3：把前两批修复落到**守衡真正在读的那份知识库**上。

为什么（2026-10-21 14:50 实测，Owner 复测仍 PASS）
--------------------------------------------------
`tools/agent/tools.mjs:1235` 写死了守衡的 KB 根：

    const KB_ROOT = process.env.SHOUHENG_KB_ROOT
      || '/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理';

—— **不是本仓的 `内容治理知识库/`**。前两批补丁打在 repo 上，守衡一个字都没读到（它那份
`p0_patterns.jsonl` 还是 10-20 17:55 的版本，四条边界表述一条都没有）。所以 Owner 复测还是 PASS。

而且两份**不是镜像**：live 那份比 repo 新（`l5_export.py` 已带 2026-10-19「最佳/最好出列」裁定、
`variant_sources` 已带 `dropped_by_ruling`、`rules.jsonl` 大 8KB、mtime 10-20 17:54）。
⇒ **不能整树覆盖**，只能按文件分流：
  · `matcher.py` / `p0_regression.py` / `l5_integrity.py`：live 与 repo HEAD **逐字节相同** ⇒ 直接搬 repo 的当前版本（= HEAD + 前两批补丁）
  · `p0_patterns.jsonl` / `l5_export.py` / `l5.json`：live 与 repo 有漂移 ⇒ **按语义/锚点打补丁**，不覆盖
"""
import hashlib
import io
import json
import os
import shutil
import subprocess

REPO = "/Users/lute/project/audit_multi_content/内容治理知识库/kb"
LIVE = os.path.expanduser("~/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理/kb")
BACKUP = "/Users/lute/project/audit_multi_content/test/_fix/backup_live"

BND = {
    "H03": "未经备案的临床/科学背书",
    "H06": "FDA 表述错误（吸奶器为 cleared/registered，非 approved/certified）",
    "H08": "无数据支撑的违法对比 / 贬低竞品",
    "H09": "智能闭环/仿生虚假宣称（自动识别节奏、模拟/复制宝宝、饱腹反馈、降低奶量焦虑）；"
           "W1当前为用户主动调节+保存程序，非闭环生理识别",
}
EXEMPT = {"H03": [BND["H03"]]}

BOUNDARY_BLOCK = '''
#: 规则自己的**边界表述**（源字段「触发原因」/「边界内容」，逐字，一字未改）。
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

#: 规则名 / 边界表述：逐字出现即命中，**否定白名单一律不豁免**（它是规则名，不是被否定的宣称）。
#   病灶（2026-10-21 实测）：H03 的边界表述「未经备案的临床/科学背书」整句落在否定白名单
#   `(…|未经|…)[^。]{0,20}(…|临床|…)` 的跨度里（「未经」+「备案的」+「临床」）⇒ 只加词仍 0 命中。
#   消费方：`kb/l5/matcher.py` 的 `compile_patterns()` / `_line_hits()`（不是注释，是判据）。
WHITELIST_EXEMPT = {"H03": ["未经备案的临床/科学背书"]}


'''


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def head_sha(rel):
    out = subprocess.run(["git", "-C", "/Users/lute/project/audit_multi_content",
                          "show", "HEAD:内容治理知识库/kb/" + rel],
                         capture_output=True).stdout
    return hashlib.sha256(out).hexdigest()


def backup(rel):
    os.makedirs(BACKUP, exist_ok=True)
    shutil.copy2(os.path.join(LIVE, rel), os.path.join(BACKUP, rel.replace("/", "__")))


def sub_once(text, old, new, what):
    assert text.count(old) == 1, "锚点不唯一（%d）：%s" % (text.count(old), what)
    return text.replace(old, new)


# ---- 1) 三份「与 HEAD 逐字节相同」的文件：直接搬 repo 当前版本（= HEAD + 前两批补丁）
for rel in ("l5/matcher.py", "l8/p0_regression.py", ".work/l5_integrity.py"):
    live_p = os.path.join(LIVE, rel)
    repo_p = os.path.join(REPO, rel)
    assert sha(live_p) == head_sha(rel), "%s 与 repo HEAD 不一致，不能直接搬" % rel
    backup(rel)
    shutil.copy2(repo_p, live_p)
    print("[1] 已搬（同源）：%s" % rel)

# ---- 2) p0_patterns.jsonl：按语义打补丁（保留 live 的 dropped_by_ruling / V02 出列等漂移）
rel = "l5/p0_patterns.jsonl"
p = os.path.join(LIVE, rel)
backup(rel)
rows = [json.loads(l) for l in io.open(p, encoding="utf-8") if l.strip()]
seen = set()
for r in rows:
    code = r.get("rule_code")
    if code not in BND:
        continue
    seen.add(code)
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
    if code in EXEMPT:
        r["whitelist_exempt_terms"] = list(EXEMPT[code])
assert seen == set(BND), "缺规则：%s" % (set(BND) - seen)
with io.open(p, "w", encoding="utf-8") as fh:
    for r in rows:
        fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
print("[2] p0_patterns.jsonl（live）：H03/H06/H08/H09 边界表述已进词表")

# ---- 3) l5_export.py：加 BOUNDARY_TERMS / WHITELIST_EXEMPT、reason 进 rule 池、输出字段
rel = ".work/l5_export.py"
p = os.path.join(LIVE, rel)
backup(rel)
s = io.open(p, encoding="utf-8").read()
s = sub_once(s, """# ---------- 生成模式
def norm(s):""", BOUNDARY_BLOCK.lstrip("\n") + """# ---------- 生成模式
def norm(s):""", "BOUNDARY_TERMS 常量")
s = sub_once(s, """    "H03": {   # 未经备案的临床/科学背书（PRD #L478「功效宣称」→ 一票否决域）
        # 零新增词：禁用写法逐字存在于该规则 forbidden_expression
        # （源：品线内容边界规则库 recvuJP1dD4jGX，严格限制红线/高危），src_frags 自动取到。
        "literal": [], "synonym": [],
    },""",
"""    "H03": {   # 未经备案的临床/科学背书（PRD #L478「功效宣称」→ 一票否决域）
        # 零新增词：禁用写法逐字存在于该规则 forbidden_expression
        # （源：品线内容边界规则库 recvuJP1dD4jGX，严格限制红线/高危），src_frags 自动取到。
        # ★ 2026-10-21：**规则自己的边界表述**另外登记在 `BOUNDARY_TERMS`（见上方常量），
        #   不走本表 —— 本表的纪律是「只列源侧命中片段」，边界表述不是命中片段。
        "literal": [], "synonym": [],
    },""", "VARIANTS.H03 注释")
s = sub_once(s, """    pool_rule = norm((r.get("rule_text") or "") + " " + (r.get("suggested_replacement") or "")).casefold()""",
"""    # ★ 2026-10-21：`reason` 也进 rule 池 —— H09 的边界表述逐字住在 `reason` 里（不在 rule_text）
    pool_rule = norm((r.get("rule_text") or "") + " " + (r.get("suggested_replacement") or "")
                     + " " + (r.get("reason") or "")).casefold()""", "pool_rule 含 reason")
s = sub_once(s, """    plist = [m["term"] for m in match_terms]""",
"""    # ★ 2026-10-21：边界表述直接进匹配表（溯源由 BOUNDARY_TERMS 那张表本身承担，见其注释）
    bnd = [norm(x) for x in (BOUNDARY_TERMS.get(code) or []) if norm(x)]
    for _t in bnd:
        match_terms.append({"term": _t, "basis": "verbatim_rule_text", "anchor": _t})
    plist = [m["term"] for m in match_terms]""", "边界表述进 plist")
s = sub_once(s, """        whitelist=wl,
        whitelist_allowed_expressions=wl_note,""",
"""        whitelist=wl,
        whitelist_allowed_expressions=wl_note,
        # ★ 2026-10-21：规则名/边界表述（逐字出现即命中，白名单不豁免）—— 见上方常量注释
        whitelist_exempt_terms=list(WHITELIST_EXEMPT.get(code) or []),""", "patterns.append 字段")
s = sub_once(s, """                         "dropped_ungrounded": dropped,""",
"""                         "dropped_ungrounded": dropped,
                         "boundary_from_source": bnd,""", "variant_sources 字段")
io.open(p, "w", encoding="utf-8").write(s)
print("[3] l5_export.py（live）：BOUNDARY_TERMS + reason 池 + 输出字段")

# ---- 4) l5.json 的 term_grounding
rel = "l5/registry/l5.json"
p = os.path.join(LIVE, rel)
backup(rel)
d = json.loads(io.open(p, encoding="utf-8").read())
tg = d.get("term_grounding")
if isinstance(tg, dict):
    for t in BND.values():
        tg[t] = "verbatim_rule_text"
    io.open(p, "w", encoding="utf-8").write(json.dumps(d, ensure_ascii=False, indent=2))
    print("[4] l5.json（live）term_grounding += 4")
else:
    print("[4] l5.json 无 term_grounding，跳过")

print("完成。live 备份在 %s" % BACKUP)
