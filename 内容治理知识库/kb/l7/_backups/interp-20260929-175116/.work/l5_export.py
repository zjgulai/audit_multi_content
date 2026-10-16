#!/usr/bin/env python3
"""第 5 步：P0 可执行导出 —— 规则 → 机器可执行的匹配表。
kb/l0~l2 只读；kb/l3 只追加；产物写 kb/l5。
"""
import json, os, re, hashlib, collections, sys, unicodedata

RUN = sys.argv[1]
L0, L2, L3, L5 = "kb/l0", "kb/l2", "kb/l3", "kb/l5"
EXPORTER_VERSION = "l5-0.1"
KB_VERSION = "v0"
for d in ("index", "registry", "runs"):
    os.makedirs(f"{L5}/{d}", exist_ok=True)

# ---------- 规则（取每个 rule_id 的最新一行）
latest = {}
for l in open(f"{L3}/candidates/rules.jsonl", encoding="utf-8"):
    if l.strip():
        r = json.loads(l); latest[r["rule_id"]] = r

# ---------- 变体扩展表
# 约束：变体必须落在规则已给出的表述范围内（forbidden_expression / suggested_replacement /
# rule_text 里出现过的词），或由「同一语义族的等价说法」保守派生；不得引入源里没有的新事实。
VARIANTS = {
    "H07": {   # 疼痛功效承诺
        "literal": ["pain-free", "painless", "painlessly", "no pain", "zero pain",
                    "indolore", "sans douleur", "schmerzfrei", "sin dolor",
                    "say goodbye to cold, painful"],
        "synonym": ["without pain", "pain relief", "relieve pain", "free of pain",
                    "无痛", "缓解疼痛", "不痛", "告别疼痛"],
        "regex": [r"(no|without|free\s+of|zero)\s+(more\s+)?pain\b",
                  r"\bpain[\s-]*(free|less)\b",
                  r"无\s*痛|缓解\s*疼痛|不\s*会\s*痛"],
    },
    "H02": {   # 催乳/奶量产出承诺
        "literal": ["more milk", "increase milk supply", "increasing milk supply",
                    "increases milk production", "boost supply", "triggers letdown",
                    "easier let-down", "easier letdown", "faster let-down",
                    "improve pumping efficiency", "augmente la production de lait",
                    "mehr milch", "más leche", "plus de lait", "producción de leche"],
        "synonym": ["boost milk", "increase milk", "milk supply boost", "maximize milk",
                    "增产", "催奶", "催乳", "下奶", "奶量提升", "增加奶量"],
        "regex": [r"\b(more|increase[sd]?|boost[s]?|maximi[sz]e[sd]?)\s+(your\s+)?milk\b",
                  r"\blet[\s-]?down\b",
                  r"增\s*产|催\s*奶|催\s*乳|下\s*奶"],
    },
    "H04": {   # 无据的医生/专家推荐背书
        "literal": ["ibclc-recommended", "recommended by 100+ experts", "ob-gyn recommended"],
        "synonym": ["doctor recommended", "doctor-recommended", "expert recommended",
                    "expert-recommended", "expert-tuned", "pediatrician recommended",
                    "医生推荐", "专家推荐", "专家调校", "专家认证推荐"],
        "regex": [r"\b(doctor|physician|pediatrician|expert|ibclc|ob[\s-]?gyn)[\s-]*"
                  r"(recommended|approved|endorsed|backed)\b",
                  r"医生\s*推荐|专家\s*推荐|专家\s*调校"],
    },
    "H05": {   # 虚假安全承诺 / 绝对化适配承诺
        "literal": ["perfect pump"],
        "synonym": ["safest", "100% safe", "100%safe", "zero risk", "risk-free",
                    "fits all breast shapes", "one size fits all",
                    "一定不损伤", "适合所有胸型", "完全安全", "零风险", "绝对安全"],
        "regex": [r"\b(safest|perfect|zero[\s-]?risk|risk[\s-]?free)\b",
                  r"\b100\s*%\s*(safe|safety)\b",
                  r"one[\s-]size[\s-]fits[\s-]all",
                  r"适合\s*所有\s*胸型|完全\s*安全|零\s*风险|绝对\s*安全|一定\s*不\s*损伤"],
    },
    "H09": {   # 拟真吸吮/模仿婴儿
        "literal": ["mimics baby", "mimics baby’s natural nursing"],
        "synonym": ["mimic baby", "mimics a baby", "imitates baby", "baby-like suckling",
                    "模仿婴儿", "模拟婴儿吸吮", "还原婴儿吮吸"],
        "regex": [r"\bmimic(s|king)?\b[^.]{0,30}\bbaby\b",
                  r"模仿\s*婴儿|模拟\s*婴儿|还原\s*婴儿"],
    },
    "U04": {   # 痛点场景 + 消除暗示 → 升级为功效承诺
        "literal": ["painful pumping"],
        "synonym": ["sore nipples", "sore breasts", "clogged ducts"],
        "regex": [r"\b(goodbye|no more|not anymore|relieve[sd]?)\b[^.]{0,40}"
                  r"\b(sore|painful|clogged)\b",
                  r"(告别|不再|摆脱)[^。]{0,20}(疼痛|堵奶|胀痛)"],
    },
    "H06": {   # FDA 表述错误（吸奶器是 cleared/registered，不是 approved/certified）
        # literal 留空是**有意**的：5 条禁用写法已逐字存在于该规则的 forbidden_expression
        # （源：#品线内容边界规则库/recvuJP1LVW6E0/检测关键词，source_sha256 2e8bb36d…），
        # 上面的 src_frags 切分会自动取到；重复列一遍会让溯源混成两处，反而更差。
        "literal": [],
        # 连字符写法**不进 synonym**（2026-09-23 实测更正）：
        # synonym 会被当作「关键词命中片段」，而引用契约要求摘录逐字出现在证据单元里；
        # "FDA-approved" 在源里不存在（源只有空格写法）→ 命中后拿不出逐字原文，
        # 结论会被契约丢弃，表现为「P0 命中却 PASS」。所以改由下面正则承担变体覆盖，
        # 不再用关键词形式宣称一个无法引用的片段。
        "synonym": [],
        "regex": [
            r"\bFDA\s+(approved|certified)\b",       # 源侧「正则表达式」逐字
            r"\bFDA[\s-]*(approved|certified)\b",    # 连字符变体（补源正则的漏洞）
            r"FDA\s*(认证|批准|通过)",                # 中文禁用写法的词形变化
        ],
    },
}

# 白名单：源侧明确允许的表达 / 否定与说明性语境
WHITELIST_COMMON = {
    "negation_patterns": [
        r"\b(does\s*n[o']?t|do\s+not|does\s+not|not\s+intended\s+to|never|no\s+claim)\b"
        r"[^.]{0,40}\b(treat|cure|heal|pain|milk)\b",
        r"(不能|不可以|无法|并非|不是|不做|严禁|禁止)[^。]{0,20}"
        r"(治疗|治愈|预防|无痛|增产|催奶|催乳)",
        # 元语境豁免：整行以「禁用表达：/DO NOT SAY:」这类「列禁用词」标记开头时，
        # 该标记到句末之间是在陈述规则（引用被禁词），不是在承诺功效 → 不判 BLOCK。
        # 只豁免到该句结束符，句号之后的内容照常参与匹配。
        r"^\s*(DO\s+NOT\s+SAY|Do\s+not\s+say|禁用表达|禁用词|禁止表达|禁止使用|禁用|禁止|"
        r"不允许|不得使用|违规表述|违规词|高危词)\s*[:：][^。！？!?]{0,200}",
    ],
    "quotation_patterns": [
        r"[「『\"“][^」』\"”]{0,80}[」』\"”]",       # 引用他方 / 规则自身表述
        r"\b(per|according\s+to|as\s+stated\s+in|cited\s+from)\b[^.]{0,30}",
        r"^(依据|来源|原文|条款)[:：]",
    ],
    "explanation_patterns": [
        r"\b(example|for\s+instance|e\.g\.|such\s+as|note\s+that)\b[^.]{0,30}",
        r"(例如|示例|举例|说明|注)[:：]",
    ],
}
# 源侧规则自带的允许表达（来自「豁免词」「安全词」字段，仅当该 P0 规则有对应来源时并入）
RULE_WHITELIST = {
    "H05": ["best", "#1", "no.1", "no. 1", "排名第一", "第一"],
    "H07": ["comfort", "gentle", "discomfort", "缓解胀满不适", "舒适", "温和"],
    "H02": ["relaxation", "relax", "natural let-down", "放松", "自然奶阵"],
    "H04": ["free ibclc service", "免费 ibclc 服务"],
    # H06 的豁免词逐字来自源侧「豁免词」字段（同 anchor、同 source_sha256 2e8bb36d…）。
    # 没有这张白名单，FDA cleared / FDA registered 会被判 BLOCK —— 而它们恰恰是正确写法。
    "H06": ["FDA cleared", "FDA-cleared", "FDA registered", "FDA 注册"],
}

# 词级溯源表：synonym 里凡不是逐字出现在该规则文本里的词，必须在这里声明它等价于规则的哪个词。
# 锚点词必须真的是该规则自己写过的词（命中片段 或 rule_text/建议替换），否则该词判为「凭空」，
# 直接从匹配表里剔除并记进 variant_sources.dropped_ungrounded（见下面 grounding()）。
# 等价关系的实际内容只有两类：同一词的另一语言写法、同一词的连字符/空格写法。
DERIVATION = {
    ("H02", "boost milk"): "boost supply",
    ("H02", "maximize milk"): "more milk",
    ("H02", "milk supply boost"): "boost supply",
    ("H02", "下奶"): "增产催奶",
    ("H02", "增加奶量"): "increase milk supply",
    ("H02", "奶量提升"): "increase milk supply",
    ("H04", "doctor recommended"): "ob-gyn recommended",
    ("H04", "doctor-recommended"): "ob-gyn recommended",
    ("H04", "expert recommended"): "recommended by 100+ experts",
    ("H04", "expert-recommended"): "recommended by 100+ experts",
    ("H04", "pediatrician recommended"): "ob-gyn recommended",
    ("H04", "专家认证推荐"): "recommended by 100+ experts",
    ("H04", "医生推荐"): "ob-gyn recommended",
    ("H05", "100%safe"): "100% safe",
    ("H05", "risk-free"): "zero risk",
    ("H05", "完全安全"): "100% safe",
    ("H05", "绝对安全"): "safest",
    ("H05", "零风险"): "zero risk",
    ("H07", "free of pain"): "pain-free",
    ("H07", "relieve pain"): "pain relief",
    ("H07", "不痛"): "无痛",
    ("H07", "告别疼痛"): "缓解疼痛",
    ("H09", "baby-like suckling"): "mimics baby",
    ("H09", "imitates baby"): "mimics baby",
    ("H09", "mimic baby"): "mimics baby",
    ("H09", "mimics a baby"): "mimics baby",
    ("H09", "模仿婴儿"): "模拟复制宝宝",
    ("H09", "模拟婴儿吸吮"): "模拟复制宝宝",
    ("H09", "还原婴儿吮吸"): "模拟复制宝宝",
    ("U04", "sore breasts"): "sore",
    ("U04", "sore nipples"): "sore",
    # ⚠ H06 的连字符写法（FDA-approved / FDA-certified）**故意不在这里登记**。
    # 原因：synonym 会被当作「关键词命中片段」，而引用契约要求摘录逐字出现在证据单元里；
    # 源里只有空格写法，"FDA-approved" 逐字不存在 → 即使登记了，命中后也会被契约丢弃，
    # 表现为「P0 命中却 PASS」（实测：state=PASS + unmet_citation 1 条）。
    # 要让连字符写法也能 BLOCK，得先修引用契约（允许 equivalent_of 用锚点词作摘录），
    # 那是 contract 层改动，不在本次范围。当前连字符覆盖只由 VARIANTS["H06"]["regex"] 承担：
    # 能命中、会记进 unmet_citation，但状态仍是 PASS —— 这是已知开口，见本次修复报告。
}

# ---------- 选取
# 显式准入（2026-09-23 修 P0-2）：H06 是 P0 红线，但上游 l3 给它的 authority 是 inferred，
# 于是被下面的门槛整条排除 —— P0 匹配器里根本没有它，"命中即 BLOCK" 这条路永远抓不到
# 「FDA approved」，只能靠慢一档的规则层兜（实测 trace：P0 0 命中｜规则层 1 命中）。
#
# 为什么是按码准入、而不是放宽 authority 门槛：
#   authority 是上游赋的值，inferred 表示「没标定」，不等于「权威不足」的判定；
#   而这些码的 forbidden_expression / 正则 / 豁免词都逐字来自源侧同一张表的同一条记录
#   （anchor 一致、source_sha256 一致，见 VARIANTS["H06"] 与 RULE_WHITELIST["H06"]）。
#   若放宽门槛，同码的 inferred 重复行（H02/H04/H05/H07/H09 各多一条）会一起进来，
#   直接触发下面的 rule_code 唯一性断言 —— 那是把变体表套错规则的隐患。
P0_CODE_ALLOWLIST = {"H06"}
P0 = [r for r in latest.values() if r["p_level"] == "P0"]
_sel_base = [r for r in P0 if r["rule_kind"] == "atomic" and r["authority"] in ("expert", "legal")]
_sel_codes = {r.get("rule_code") for r in _sel_base if r.get("rule_code")}
_sel_extra = [r for r in P0
              if r["rule_kind"] == "atomic"
              and (r.get("rule_code") or "") in P0_CODE_ALLOWLIST
              and (r.get("rule_code") or "") not in _sel_codes]
sel = _sel_base + _sel_extra
exc = collections.Counter()
for r in latest.values():
    if r["p_level"] != "P0":
        exc["non_P0"] += 1
    elif r["rule_kind"] != "atomic":
        exc["P0_but_inductive"] += 1
    elif r["authority"] not in ("expert", "legal"):
        if (r.get("rule_code") or "") in P0_CODE_ALLOWLIST:
            exc["P0_admitted_by_allowlist"] += 1
        else:
            exc["P0_but_authority_insufficient"] += 1
print(f"P0 {len(P0)} 条 → 入选 {len(sel)}（其中准入白名单 {len(_sel_extra)}） | 排除 {dict(exc)}")

# 变体表按 rule_code 查表，因此入选规则的 rule_code 必须唯一，否则会把 A 规则的变体套到 B 规则上。
# （全套 1018 条里 rule_code 并不唯一：品线内容边界规则库复用同一套码 H01-H09/M01-M07/U01-U04，但那些是
#  authority=inferred，已被门槛排除；这里只校验入选集合内部不重码。）
_dup = collections.Counter(r.get("rule_code") for r in sel)
dups = {k: v for k, v in _dup.items() if v > 1}
print(f"入选集合 rule_code 唯一性检查：{'PASS' if not dups else 'FAIL ' + str(dups)}")
assert not dups, dups
code_collision_note = ("rule_code 在全套规则里不唯一（品线内容边界规则库复用 H01-H09/M01-M07/U01-U04 码，"
                       "authority=inferred 已按门槛排除）；入选集合内部已校验无重码，变体表按 rule_code 查表安全")

# ---------- 生成模式
def norm(s):
    s = unicodedata.normalize("NFKC", s or "")
    return re.sub(r'\s+', ' ', s).strip()

patterns, no_pattern = [], []


def grounding(term, code, pool_source, pool_rule):
    """给每个词一个可机验的来源标记；返回 (basis, anchor)。basis=ungrounded 表示凭空，必须剔除。"""
    t = norm(term).casefold()
    if t in pool_source:
        return "verbatim_source", term
    if t in pool_rule:
        return "verbatim_rule_text", term
    anc = DERIVATION.get((code, norm(term)))
    if anc and norm(anc).casefold() in (pool_source + " " + pool_rule):
        return f"equivalent_of:{anc}", anc
    return "ungrounded", None


for r in sorted(sel, key=lambda x: str(x.get("rule_code"))):
    code = r.get("rule_code") or ""
    v = VARIANTS.get(code)
    if not v:
        no_pattern.append({"rule_id": r["rule_id"], "rule_code": code,
                           "reason": "该规则的可匹配片段无法从源侧「命中片段/检测关键词」直接得到，"
                                     "且不属于已定义的语义族，故不生成 pattern"})
        continue
    # 字面片段：全部来自源侧命中片段。分隔符两类都要切：
    #   「；」= L3 汇总多个来源记录时的连接符；「,，」= 源侧单元格内部的并列写法。
    # 不切开就会拼出一个源里不存在的长串（如 "recommended by 100+ experts;ob-gyn recommended"），
    # 导致该片段永远匹配不上。切分只是拆回源侧本来就并列的片段，不新增词。
    src_frags = [norm(x) for x in re.split(r'[,，;；]', r["forbidden_expression"]) if norm(x)]
    lit = sorted({norm(x) for x in (src_frags + v["literal"]) if norm(x)})
    syn = sorted({norm(x) for x in v.get("synonym", []) if norm(x)})
    rx = v.get("regex", [])
    pool_source = norm(r["forbidden_expression"]).casefold()
    pool_rule = norm((r.get("rule_text") or "") + " " + (r.get("suggested_replacement") or "")).casefold()

    # ---- 词级溯源：逐词给 basis，凭空的词不进匹配表
    match_terms, dropped = [], []
    for term in lit + syn:
        basis, anchor = grounding(term, code, pool_source, pool_rule)
        if basis == "ungrounded":
            dropped.append(term)
            continue
        match_terms.append({"term": term, "basis": basis, "anchor": anchor})
    plist = [m["term"] for m in match_terms]
    # 去重：已被更长的词覆盖的短词不再重复计入 keyword
    plist = [p for p in plist if not any(p != q and p in q for q in plist)]
    match_terms = [m for m in match_terms if m["term"] in plist]
    wl = list(WHITELIST_COMMON["negation_patterns"]) + list(WHITELIST_COMMON["quotation_patterns"])
    if code in RULE_WHITELIST:
        wl_note = RULE_WHITELIST[code]
    else:
        wl_note = []
    patterns.append(dict(
        pattern_id="p-" + hashlib.sha1(f"{EXPORTER_VERSION}|{r['rule_id']}".encode()).hexdigest()[:16],
        rule_id=r["rule_id"], rule_code=code,
        anchor=r["anchor"], source_sha256=(r["evidence_units"][0] or {}).get("source_sha256"),
        type="keyword" if plist else "regex",
        patterns=plist,
        match_terms=match_terms,
        regex_patterns=rx,
        whitelist=wl,
        whitelist_allowed_expressions=wl_note,
        suggested_replacement=norm(r["suggested_replacement"]),
        match_note="BLOCK",
        p_level=r["p_level"], authority=r["authority"],
        evidence_units=r["evidence_units"],
        variant_sources={"literal_from_source": lit, "synonym_family": syn, "regex": rx,
                         "dropped_ungrounded": dropped},
    ))
    if dropped:
        print(f"  ! {code} 剔除无溯源的词 {dropped}")

# ---------- 落盘
with open(f"{L5}/p0_patterns.jsonl", "w", encoding="utf-8") as fh:
    for p in patterns:
        fh.write(json.dumps(p, ensure_ascii=False, sort_keys=True) + "\n")
with open(f"{L5}/index/l5.jsonl", "w", encoding="utf-8") as fh:
    for p in patterns:
        fh.write(json.dumps({"pattern_id": p["pattern_id"], "rule_id": p["rule_id"],
                             "type": p["type"], "match_note": p["match_note"]},
                            ensure_ascii=False, sort_keys=True) + "\n")

n_pat = sum(len(p["patterns"]) for p in patterns)
n_rx = sum(len(p["regex_patterns"]) for p in patterns)
n_wl = sum(1 for p in patterns if p["whitelist"])
json.dump({"exporter_version": EXPORTER_VERSION, "kb_version": KB_VERSION,
           "selection": {"p_level": "P0", "rule_kind": "atomic", "authority": ["expert", "legal"],
                         "code_allowlist": sorted(P0_CODE_ALLOWLIST),
                         "code_allowlist_note": "上游 authority=inferred 但证据逐字可溯的 P0 红线，"
                                                "按码准入（2026-09-23 补 H06）；不是放宽 authority 门槛"},
           "rule_code_uniqueness": code_collision_note,
           "excluded": dict(exc),
           "variant_policy": {
               "literal_from_source": "全部取自源侧规则 evidence 的「命中片段/检测关键词」，"
                                      "按「；」(L3 跨记录连接符) 与「,，」(源侧单元格内并列) 切开后逐条成 pattern",
               "synonym_family": "同一语义族的等价说法，且必须出现在该规则的 suggested_replacement / rule_text 的表述范围内",
               "regex": "处理词形变化（复数/时态/连字符/中英变体）与「场景+消除暗示」组合式命中",
               "no_new_knowledge": "每条 pattern 都回指已存在的 rule_id；未引入源里没有的事实",
               "word_level_grounding": "逐词给出 basis：verbatim_source（逐字来自该规则的命中片段）/"
                                       "verbatim_rule_text（逐字来自该规则的 rule_text 或建议替换）/ "
                                       "equivalent_of:<锚点词>（同一词的另一种语言或连字符写法，锚点词必须是该规则自己写过的词）。"
                                       "三种都对不上 → 判为凭空，不进匹配表，记进 variant_sources.dropped_ungrounded",
           },
           "term_grounding": {m["term"]: m["basis"] for p in patterns for m in p["match_terms"]},
           "whitelist_policy": {
               "negation": WHITELIST_COMMON["negation_patterns"],
               "quotation": WHITELIST_COMMON["quotation_patterns"],
               "rule_specific_allowed": RULE_WHITELIST,
               "why": "没有例外清单，误报会把 BLOCK 精确率（PRD 要求 ≥95%）拉下来",
           },
           "normalization": {"unicode": "NFKC", "whitespace": "collapse", "casefold": True,
                             "note": "匹配前统一做 NFKC + 空白折叠 + casefold，抵消全角/大小写/多空格差异"},
           "match_note_enum": ["BLOCK"]},
          open(f"{L5}/registry/l5.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
json.dump(no_pattern, open(f"{L5}/registry/l5_no_pattern.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
basis_cnt = collections.Counter(m["basis"].split(":")[0] for p in patterns for m in p["match_terms"])
n_drop = sum(len(p["variant_sources"]["dropped_ungrounded"]) for p in patterns)
print(f"模式 {len(patterns)} 条 | keyword 式 {n_pat} | regex 式 {n_rx} | 有白名单 {n_wl} | 无法生成 {len(no_pattern)}")
print(f"词级溯源 {dict(basis_cnt)} | 剔除凭空词 {n_drop}")
json.dump({"patterns": len(patterns), "keyword": n_pat, "regex": n_rx, "whitelist": n_wl,
           "no_pattern": no_pattern, "excluded": dict(exc), "p0_total": len(P0),
           "selected": len(sel), "term_basis": dict(basis_cnt), "dropped_ungrounded": n_drop,
           "match_terms": {p["rule_code"]: p["match_terms"] for p in patterns}},
          open("kb/.work/l5_patterns.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
