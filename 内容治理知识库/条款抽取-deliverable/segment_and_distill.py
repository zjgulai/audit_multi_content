#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
政策文本 → 单元切分 + 可判定规则条款
走 kb-clause-extractor（L3 owner）的口径。**本脚本全程只读**：只读 kb/l2/units.jsonl，
产物写到本目录，不碰 kb/l0 ~ kb/l4 任何文件。

用法：
    python3 segment_and_distill.py <policy_resource_id> [--out-prefix NAME]

为什么只读：kb/l8/l3_distill_run.py 会以 "w" 覆盖 kb/l3/rejected.jsonl，
本库真发生过拒绝台账 11,860 行 → 1,053 行的回归。在做归档（红线①）之前不跑它。
"""
import json, re, sys, os, hashlib, html, collections, unicodedata
from urllib.parse import urlparse

KB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "kb")
UNITS = os.path.join(KB, "l2", "units.jsonl")
OUT = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------- 判定用正则
# 义务/禁止模态：命中即「有要求」，未命中即「无判定条件」
MODAL = re.compile(
    r"\b(must(?:\s+not)?|shall(?:\s+not)?|may\s+not|should(?:\s+not)?|"
    r"prohibited|prohibits?|required\s+to|is\s+required|are\s+required|"
    r"cannot|can\s+not|need\s+not|only\s+if|is\s+unlawful|violat\w*|"
    r"liable|responsib\w+\s+for)\b", re.I)
# 判定条件触发词：出现即「有条件」
COND = re.compile(
    r"\b(if|when|where|unless|in\s+the\s+case|in\s+order\s+to|so\s+that|"
    r"before|after|without|whether|fails?\s+to|implies?|implied|"
    r"in\s+light\s+of|with\s+respect\s+to|based\s+on|depending\s+on)\b", re.I)
# 阈值 / 词表（真阈值短语，用于产出 lexicon 字段）
THRESH_TERM = re.compile(
    r"(competent\s+and\s+reliable\s+scientific\s+evidence|"
    r"competent\s+and\s+reliable\s+evidence|"
    r"reasonable\s+basis|randomi[sz]ed(?:\s+clinical)?\s+(?:trial|study|test)?|"
    r"well[- ]controlled(?:\s+clinical)?\s+(?:trial|study)?|"
    r"statistically\s+significant|clear\s+and\s+conspicuous|"
    r"material(?:ly)?|preponderance\s+of\s+the\s+evidence|"
    r"Class\s+[IVX]+|510\(k\)\s+clearance)", re.I)
# 判定「有没有阈值」的宽口径（含引号词表，用于分流，不用于产出）
THRESH = re.compile(THRESH_TERM.pattern + r"|[\"“][^\"”]{2,60}[\"”]", re.I)
# 处理方式（动作动词）
ACTION = re.compile(
    r"\b(substantiat\w+|disclos\w+|discourag\w+|prohibit\w*|correct\w*|"
    r"discontinu\w+|refrain|avoid|review|document|maintain|keep|provide|"
    r"include|state|indicate|monitor|qualif\w+|warn\w*|notif\w+|"
    r"obtain|verify|ensure|comply|remov\w+|cease)\b", re.I)
# 通用动作：模态动词后紧跟的实义动词（should use / must make sure / should report …）
MODAL_VERB = re.compile(
    r"\b(must|shall|should|may not|cannot|can not|are required to|is required to|need not)\b"
    r"\s+(?:not\s+)?(?:also\s+|instead\s+|first\s+|only\s+|then\s+|further\s+)?"
    r"(?:\w+ly\s+)?"
    r"(?!(?:be|not|have|has|had|do|does|did|is|are|was|were|the|a|an|of|to|in|on|at|for|with|that|this|it|its)\b)"
    r"([a-z]{3,})\b", re.I)
# 法学期刊引注形态（法条正文里夹带的 citation 残片，非规范条款）
CITATION = re.compile(
    r"(F\.?\s?Supp|F\.?2d|F\.?3d|U\.?S\.?C|C\.?F\.?R|F\.?T\.?C\.?|LEXIS|"
    r"v\.\s+[A-Z]|at\s+\*\d|\baff.?d\b|Memorandum\s+Opinion|Final\s+Order\s+at|"
    r"\bId\.\s|\bsee\s+also\b|\bciting\b|\baccord\b)", re.I)
EXAMPLE_HEAD = re.compile(
    r"^\s*(?:Example\s+\d+|The\s+marketer\s+(?:airs|runs|sells|posts|claims|states|markets)|"
    r"The\s+advertiser\s+(?:airs|runs|posts|markets))", re.I)
# chrome / 噪声信号
CHROME = re.compile(
    r"(skip\s+to\s+main\s+content|official\s+website\s+of\s+the\s+united\s+states|"
    r"here.?s\s+how\s+you\s+know|show/hide|menu\s+mega|secondary\s+menu|"
    r"search\s+or\s+browse|search\s+small\s+search|view\s+all\s+\w+\s+blog\s+posts|"
    r"report\s+fraud|submit\s+public\s+comments|search\s+the\s+legal\s+library|"
    r"federal\s+government\s+websites\s+often\s+end|"
    r"before\s+sharing\s+sensitive\s+information|the\s+site\s+is\s+secure|"
    r"the\s+https://\s+ensures|español|enforcement\s+menu|advice\s+and\s+guidance\s+menu|"
    r"main\s+navigation|return\s+to\s+top|take\s+action|report\s+identity\s+theft|"
    r"register\s+for\s+do\s+not\s+call|sign\s+up\s+for\s+consumer\s+alerts|"
    r"get\s+business\s+blog\s+updates|browse\s+legal\s+resources|"
    r"search\s+the\s+legal\s+library\s+instead|legal\s+library|"
    r"find\s+legal\s+resources\s+and\s+guidance)", re.I)
MENU_KW = re.compile(
    r"(show/hide|\bmenu\b|search|browse|report\s+fraud|submit\s+public|"
    r"return\s+to\s+top|\bsections\b|cases\s+and\s+proceedings|press\s+release|"
    r"blog\s+posts|enforcement|advocacy\s+and\s+research|advisory\s+opinions|"
    r"cooperation\s+agreements|federal\s+register\s+notices|rulemaking|"
    r"premerger|merger\s+review|anticompetitive|consumer\s+protection|"
    r"get\s+your\s+free|take\s+action|sign\s+up|register\s+for|español|english)", re.I)

def is_chrome(t: str) -> bool:
    """导航/菜单/页脚样板：短行密集 + 菜单词密集 + 无句末标点 —— 三者同时成立才判 chrome"""
    lines = [x.strip() for x in t.split("\n") if x.strip()]
    if not lines:
        return True
    if CHROME.search(t) and len(t) < 400:
        return True
    if "official website of the united states" in t.lower():
        return True
    if re.match(r"^Health Products Compliance Guidance\s*\|", t) or (t.count("|") >= 1 and len(t) < 120 and "compliance guidance |" in t.lower()):
        return True
    short = sum(1 for x in lines if len(x) < 45)
    kw = sum(1 for x in lines if MENU_KW.search(x))
    ends_sentence = t.rstrip().endswith((".", "”", '"', "。"))
    return (len(lines) >= 4 and short / len(lines) >= 0.6
            and kw >= 3 and not ends_sentence)
FOOTNOTE_ONLY = re.compile(r"^\s*(?:\[\d+\]\s*)+[\.\s]*$")
HEADING_ONLY = re.compile(r"^\s*(?:[A-Z]\.|[IVX]+\.|\d+\.)\s*$")
TAG = re.compile(r"</?[a-zA-Z][^>]{0,200}>")
B64LIKE = re.compile(r"^[A-Za-z0-9+/=]{120,}$")

def norm(s: str) -> str:
    s = html.unescape(s)
    s = s.replace("\u00a0", " ").replace("\u200b", "")
    s = unicodedata.normalize("NFKC", s)
    return re.sub(r"[ \t]+", " ", s).strip()

def clean(s: str) -> str:
    """剥标签 + 收空白，用于产出可读正文（不改语义字符）"""
    t = re.sub(r"<br\s*/?>", "\n", s)
    t = re.sub(r"</(p|li|div|tr|h[1-6])>", "\n", t)
    t = TAG.sub(" ", t)
    t = norm(t)
    return re.sub(r"\n{2,}", "\n", t).strip()

def sha(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

def first_sentence(t: str, cap=200) -> str:
    t = t.strip()
    m = re.search(r"[.!?](?:\s|$)", t)
    s = t[:m.end()].strip() if m and m.end() <= cap else t[:cap].strip()
    return s

def clause_sentence(t: str, cap=240) -> str:
    """取「含义务/禁止模态的那一句」完整句：从模态词位置向前找到真正的句首。
    避免把上一句的尾巴当成判定条件（实测 132 条候选里 25 条踩了这个坑）。"""
    mv = MODAL.search(t) or MODAL_VERB.search(t)
    if not mv:
        return first_sentence(t, cap)
    s, e = mv.start(), mv.end()
    back = re.search(r"[.!?](?:\s|$)", t[e:])
    end = e + back.end() if back else len(t)
    head = 0
    for m in re.finditer(r"[.!?]\s+", t[:s]):
        head = m.end()
    if head == 0:
        caps = [m.start() for m in re.finditer(r"(?<![A-Za-z])[A-Z“\"']", t[:s])]
        if caps:
            head = caps[-1] if (s - caps[-1]) <= 90 else caps[0]
    seg = re.sub(r"^\[\d+\]\s*", "", t[head:end].strip()).strip()
    if len(seg) > cap:
        seg = seg[:cap].rstrip() + " …"
    return seg or first_sentence(t, cap)

def lexicon(t: str) -> str:
    """阈值/词表：收合规阈值短语 + 长度 ≥12 的引号短语；短引号（<12）一律丢弃"""
    vals = {m.group(0) for m in THRESH_TERM.finditer(t)}
    for m in re.finditer(r"[“\"]([^”\"]{12,80})[”\"]", t):
        vals.add(f"“{m.group(1)}”")
    return "；".join(sorted(vals)) or "（本条无显式阈值，处理方式为义务动作）"

def quote(t: str, cap=160) -> str:
    t = t.strip()
    return (t[:cap] + " …[截断]") if len(t) > cap else t

def dedupe_key(t: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", t.lower())[:120]

# 规则形态（只允许这些值，与 L3 规则层的 form 词汇表对齐）
def rule_form(t: str):
    if re.search(r"\b(discourag\w*|do\s+not|don.?t)\b", t, re.I): return "prohibition"
    if re.search(r"\bsubstantiat\w+", t, re.I):          return "substantiation"
    if re.search(r"\bdisclos\w+|clear\s+and\s+conspicuous", t, re.I): return "disclosure"
    if re.search(r"\bmust\b|\bshall\b|required\s+to", t, re.I):       return "mandate"
    if re.search(r"\b(may\s+not|cannot|can\s+not|prohibit|unlawful|liable)\b", t, re.I):
        return "prohibition"
    if re.search(r"\bshould\b", t, re.I):                return "recommendation"
    return "scope"

def main():
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(2)
    RID = sys.argv[1]
    prefix = sys.argv[3] if len(sys.argv) > 3 and sys.argv[2] == "--out-prefix" else "policy-clauses"

    raw = [json.loads(l) for l in open(UNITS, encoding="utf-8")]
    mine = [u for u in raw if u.get("resource_id") == RID]
    if not mine:
        print(f"[FATAL] resource_id 在 kb/l2/units.jsonl 里没有单元：{RID}"); sys.exit(3)
    cl = sorted([u for u in mine if u.get("unit_type") == "clause"],
                key=lambda u: u.get("order_in_parent") or 0)
    source_sha = cl[0].get("source_sha256") or mine[0].get("source_sha256") or ""

    units_out, candidates, rejected = [], [], []
    seen = {}
    n_chrome = 0
    for i, u in enumerate(cl):
        uid, anchor, t_raw = u["unit_id"], u["anchor"], u["text"]
        t = clean(t_raw)
        art = []
        if TAG.search(t_raw):                     art.append("html_tag")
        if B64LIKE.match(t_raw.strip()):          art.append("encoded_payload")
        if re.search(r"</?(span|li|ul)\b", t_raw, re.I) and MODAL.search(t) and len(re.findall(r"\b(must|shall|may not|should)\b", t, re.I)) >= 2:
            art.append("multi_requirement_merged")
        if re.search(r"</(li|span)>", t_raw, re.I): art.append("unclosed_markup")

        seg_anchor = f"{anchor}/seg-{i+1}"
        rec = dict(seq=i + 1, unit_id=uid, anchor=anchor, seg_anchor=seg_anchor,
                   source_sha256=u.get("source_sha256", ""), order_in_parent=u.get("order_in_parent"),
                   char_count=len(t), text=t, artifacts=sorted(set(art)))
        units_out.append(rec)

        def reject(kind, reason):
            rejected.append(dict(kind=kind, unit_id=uid, anchor=anchor, seg_anchor=seg_anchor,
                                 char_count=len(t), reason=reason, text=quote(t, 200)))

        if is_chrome(t):
            n_chrome += 1
            reject("page_chrome", "页面 chrome（导航/菜单/页脚样板），非政策文本本体，不参与条款判定")
            continue
        if not t:
            reject("empty_text", "正文为空（抽取未取到内容）"); continue
        if FOOTNOTE_ONLY.match(t):
            reject("footnote_marker", "仅脚注序号，无判定内容"); continue
        if HEADING_ONLY.match(t):
            reject("heading_only", "仅小节标题字母/序号（如「B.」），无判定内容 —— 建议 L2 侧重切，标题应与正文同单元")
            continue
        if B64LIKE.match(t.strip()):
            reject("encoded_payload", "编码载荷（疑似 base64），非自然语言条款"); continue

        has_modal, has_cond = bool(MODAL.search(t)), bool(COND.search(t))
        has_thresh, has_action = bool(THRESH.search(t)), bool(ACTION.search(t))
        mv = MODAL_VERB.search(t)
        modal_pos = (MODAL.search(t) or mv).start() if (MODAL.search(t) or mv) else -1
        has_generic_action = bool(mv)   # MODAL_VERB 的负向先行断言已排除系动词/助动词/冠词
        is_example = bool(EXAMPLE_HEAD.match(t))

        if not has_modal:
            if is_example:
                reject("policy_example_not_rule",
                       "政策举例（Example N / 「The marketer …」情形描述），是示例不是规范条款，"
                       "单独不成规则（其规范结论在对应正文条款）")
            elif any(k in t.lower() for k in ("the ftc can", "the ftc has", "ftc and the food",
                                               "the ftc's", "the commission can", "the ftc provided",
                                               "the ftc issued", "the fda has", "the fda issues")):
                reject("agency_authority_not_rule",
                       "描述主管机关权力/机构分工/执法史，未对广告主施加「须/不得」义务，不构成可判定规则")
            elif len(t) < 45:
                reject("fragment_too_short",
                       f"片段过短（{len(t)} 字符）且无义务/禁止模态，是导航项/人名/残片，非完整条款")
            elif re.match(r"^\s*[“\"']", t) or re.search(r"[”\"']\s*(?:Just below|below|next to)", t, re.I):
                reject("illustrative_copy_fragment",
                       "示例性广告文案片段（引号内的宣称文本），是用来说明问题的素材，不是规范条款")
            else:
                reject("narrative_no_obligation",
                       "叙述性正文：陈述事实/背景/定义，未含义务或禁止模态，落不了「命中→处理」形态")
            continue

        # 句中切片：单元开头不是句首（小写字母起）= 把上一句切了一半
        if re.match(r"^[a-z]", t) and not re.match(r"^[a-z]{1,3}\s*[)\.]", t):
            reject("mid_sentence_fragment",
                   "单元从句子中间开始（首字符小写），是把上一句切了一半的残片，"
                   "判定条件不完整 —— 应在 L2 侧重切，不在 L3 侧补全")
            continue

        # 超大拼接块：L2 把几千字正文塞进一个「条款」单元，判不了单一条件
        if len(t) > 2000:
            reject("oversized_unit_blob",
                   f"单元正文 {len(t)} 字符（L2 切分上限拼接所致），里面是多条条款的连缀，"
                   "给不出单一「判定条件 + 阈值」—— 应在 L2 侧重切，不在 L3 侧硬切")
            continue

        # 有义务/禁止模态 —— 判是否落得了「判定条件 + 阈值或处理方式」
        if not (has_action or has_thresh or has_generic_action):
            reject("obligation_without_action",
                   "有义务模态但既无处理动作也无阈值/词表，无法给出「命中→怎么处理」")
            continue
        if len(art) and "multi_requirement_merged" in art:
            reject("multi_requirement_merged",
                   "一个单元内塞入 ≥2 个独立要求 —— 按「一个法条 = 一个单元」口径该单元本身是脏的，"
                   "应在 L2 侧重切，不在 L3 侧硬容错")
            continue

        k = dedupe_key(t)
        if k in seen:
            reject("duplicate_of", f"与该资源内 seq={seen[k]} 逐字重复，不重复产出规则")
            continue
        seen[k] = i + 1

        text_clean_full = re.sub(r"\s+", " ", t)
        ev = dict(unit_id=uid, anchor=anchor, seg_anchor=seg_anchor,
                  source_sha256=u.get("source_sha256", ""))
        form = rule_form(t)
        cond = clause_sentence(t) if (has_cond or form in ("mandate", "prohibition", "substantiation")) else "（无显式条件，按无条件义务适用）"
        thr = lexicon(t)
        acts = sorted({m.group(0).lower() for m in ACTION.finditer(t)})
        if not acts and mv:
            acts = [mv.group(0).strip().lower()]
        act = "；".join(acts[:6]) or "（未识别到处理动作，须人工补）"
        rid_seed = uid + "|" + form
        candidates.append(dict(
            rule_id="CAND-" + sha(rid_seed)[:16],
            status="candidate",              # ★ 候选 ≠ 定稿
            article_no="",                   # ★ 条款号由 L4 分配，本层不自造
            kb_type="external_standard",
            form=form,
            source=dict(resource_id=RID, unit_id=uid, anchor=anchor, seg_anchor=seg_anchor,
                        source_sha256=u.get("source_sha256", "")),
            condition=cond,
            threshold_or_lexicon=thr,
            required_action=act,
            forbidden_expression="",
            suggested_replacement="",
            rule_text=f"[{form}] 命中条件：{cond} → 处理：{act}（阈值/词表：{thr}）",
            evidence_quote=t if len(t) <= 400 else t[:400] + " …[逐字摘录已截断，全文见 units]",
            evidence_units=[ev],
            evidence_level="cited",          # 有逐字文本 + 锚点 + source_sha256
            applicable_jurisdiction="US",
            effective_from="", effective_to="",
            owner="", verification="待人工复核",
            quality=("strong" if (cond != "（无显式条件，按无条件义务适用）"
                                 and modal_pos >= 0
                                 and cond.find(t[modal_pos:modal_pos + 12]) >= 0
                                 and not re.match(r"^\s*(?:See(?:\s+also)?|As\s+noted|As\s+discussed)", cond, re.I))
                     else ("weak" if cond != "（无显式条件，按无条件义务适用）" else "unconditional")),
            p_level="P1", risk_level="unknown",
            supersedes=[], superseded_by=[],
        ))

    # ---------------- 落盘
    def dump(name, rows):
        p = os.path.join(OUT, name)
        with open(p, "w", encoding="utf-8") as f:
            for r in rows: f.write(json.dumps(r, ensure_ascii=False) + "\n")
        return p

    p_cand = dump(f"{prefix}.candidates.jsonl", candidates)
    p_rej  = dump(f"{prefix}.rejected.jsonl", rejected)
    p_unit = dump(f"{prefix}.units.jsonl", units_out)

    print(json.dumps(dict(
        resource_id=RID, source_sha256=source_sha,
        clause_units_total=len(cl), units_written=len(units_out),
        chrome_units=n_chrome,
        candidates=len(candidates), rejected=len(rejected),
        unaccounted=len(cl) - len(candidates) - len(rejected),
        accounted=len(candidates) + len(rejected),
        reject_kinds=dict(collections.Counter(r["kind"] for r in rejected)),
        forms=dict(collections.Counter(c["form"] for c in candidates)),
        out=[p_cand, p_rej, p_unit],
    ), ensure_ascii=False, indent=1))

if __name__ == "__main__":
    main()
