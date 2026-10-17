#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""L3 条款抽取 + 规则蒸馏（外部标准支线，v0.1）

补的是哪个洞（2026-09-30 实测）：
  `kb/l8/l3_distill_run.py` 的 `external_standard` 分支**只拒绝、不蒸馏**：
      for rid, grp in ext_rec.items():
          if not cl:  rejected.append(no_clause_text) ; continue
          for u in cl: rejected.append(clause_not_actionable)   # 一律拒
  于是库内**最大的政策文本**（FTC《Health Products Compliance Guidance》，995 个
  `kb_type=external_standard / unit_type=clause` 单元）被压成 995 行「条款文本不可判定：
  非自然语言条款（页面脚本 / base64 编码载荷）」—— 实测该判定**不成立**：该资源的
  `meta.kind` 是 `paragraph`、`content_quality_flag` 是 `ok`，正文是自然语言政策文本。
  这一支线因此长期零产出，`rule_forms.external_standard` 的产出恒为空。

本脚本做什么：
  1. 把该资源的 995 个条款单元**逐个**过判定（不抽样），切成可判定的规则候选；
  2. 每个单元要么进规则（带 `evidence_units[{unit_id, anchor, source_sha256}]`）、
     要么进逐单元拒绝台账（带 `kind` + `reason`）——**三分互斥**：规则引用 ∪ 拒绝 = 输入集；
  3. 产出落在 `kb/l3/`，与 l3_distill_run.py 的候选件**同构**（`l3_gate.py` C1 直接可核）。

三条红线（与 skill `kb-clause-extractor` 一致）：
  ① 跑之前先归档：本脚本**只新建**文件，不覆盖 `candidates/rules.jsonl` / `rejected.jsonl`；
     若目标文件已存在则先 `cp` 到 `l3/_archive/` 并校验 sha256，失败即中止。
  ② 候选 ≠ 定稿：`article_no` 一律留空，条款号由 L4 发放，本层**不自造**。
  ③ 证据逐条回指：`unit_id + anchor + source_sha256` 三件套与 `kb/l2/units.jsonl` 逐字一致。

用法：
    kb/kbpy l8/l3_clause_distill.py <RUN> <resource_id> [--apply]
    （**默认干跑**：只打印将写什么，不落盘）

幂等键：`rule_id`（= f(source unit_id, form)）；`evidence_digest` 未变 → `unchanged`。
"""
# ── 解释器守卫（2026-09-29）：不合格就用 kb/.kb-python 指定的解释器重跑自己 ──
import os as _os, sys as _sys
if not _os.environ.get("KB_INTERP_OK"):
    _d = _os.path.dirname(_os.path.abspath(__file__)); _cfg = None
    while True:
        _p = _os.path.join(_d, ".kb-python")
        if _os.path.isfile(_p):
            _cfg = _p
            break
        _q = _os.path.dirname(_d)
        if _q == _d:
            break
        _d = _q
    if _cfg:
        _want = next((l.split("#", 1)[0].strip() for l in open(_cfg, encoding="utf-8")
                      if l.split("#", 1)[0].strip()), "")
        _want = _os.path.expanduser(_want)
        if (_want and _os.access(_want, _os.X_OK)
                and _os.path.realpath(_want) != _os.path.realpath(_sys.executable)):
            _os.environ["KB_INTERP_OK"] = "1"
            _os.execve(_want, [_want, _os.path.abspath(__file__)] + _sys.argv[1:], dict(_os.environ))
# ──────────────────────────────────────────────────────────────────────────

import collections, hashlib, html, json, os, re, shutil, sys, unicodedata

APPLY = "--apply" in sys.argv
if APPLY:
    sys.argv.remove("--apply")
pos = [a for a in sys.argv[1:] if not a.startswith("--")]
RUN = pos[0] if pos else "20260930-0000"
RID_FILTER = pos[1] if len(pos) > 1 else ""

HERE = os.path.dirname(os.path.abspath(__file__))
KB = os.path.dirname(HERE)
L2, L3 = os.path.join(KB, "l2"), os.path.join(KB, "l3")
DV, KBV = "l3-clause-0.1", "v0"
OUT_CAND = os.path.join(L3, "candidates", "external_standard.jsonl")
OUT_REJ = os.path.join(L3, "rejected_external_standard.jsonl")
OUT_MAN = os.path.join(L3, "manifest_l3.jsonl")
OUT_RUN = os.path.join(L3, "runs", f"{RUN}-clause-distill.json")
ARCH_DIR = os.path.join(L3, "_archive")

# ── 落盘闸门：必须早于本脚本的**第一个副作用** ──────────────────────────────
if not APPLY:
    print(f"[dry-run] {os.path.basename(os.path.abspath(__file__))} 未落盘。")
    print("[dry-run] 本脚本会写入：")
    print(f"[dry-run]   {os.path.relpath(OUT_CAND, KB)}   （新建或整体重写该资源的外部标准候选件）")
    print(f"[dry-run]   {os.path.relpath(OUT_REJ, KB)}    （新建或整体重写逐单元拒绝台账）")
    print(f"[dry-run]   {os.path.relpath(OUT_MAN, KB)}    （**追加**规则行）")
    print(f"[dry-run]   {os.path.relpath(OUT_RUN, KB)}    （本次运行记录）")
    print("[dry-run] 已有同名文件会先归档到 kb/l3/_archive/ 并校验 sha256，失败即中止。")
    print("[dry-run] 加 --apply 才落盘。")


def sha_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for b in iter(lambda: fh.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def archive(path, tag):
    """红线①：写之前先归档 + 校验 sha256。返回归档路径与摘要。"""
    if not os.path.exists(path):
        return None, None
    os.makedirs(ARCH_DIR, exist_ok=True)
    dst = os.path.join(ARCH_DIR, f"{os.path.basename(path)}-pre-{tag}")
    src_sha = sha_file(path)
    shutil.copyfile(path, dst)                      # 只归档，不动源
    if sha_file(dst) != src_sha:
        raise SystemExit(f"[FATAL] 归档校验失败（sha256 不一致）：{dst}")
    return dst, src_sha


# ══════════════════════════════════════════════════════ 判定规则（正则）
MODAL = re.compile(
    # ★ 2026-10-13 加中文分支。为什么必须要它（实测，不是预防性设计）：
    #   本库是**中文库**，而原先这份正则 **100% 英文** ⇒ 任何中文条款都过不了
    #   「第 2 关：没有义务/禁止模态 → 不成规则」⇒ **一律被拒**。
    #   实测规模：L2 里 `unit_type=clause` 且含中文的单元 **882 条**，
    #   其中含 必须/不得/禁止/严禁/应当 的 **413 条** —— 这 413 条此前**一条都进不了规则**。
    #   实测个案：内容审查 Agent PRD（`url__…NB55…`）3 个 clause 单元分别含
    #   必须×3/不得×2/禁止×2/须×3，全部被判 `narrative_no_obligation` 或
    #   `illustrative_copy_fragment`，`rules: 0`。
    # ⚠️ 中文**不能**套 `\b` —— 汉语无词边界，且 CJK 落在 `\w` 里 ⇒ `\b必须\b` 在中文句内恒不匹配。
    #    所以中文这一支放在 `\b(…)\b` **之外**。
    # ⚠️ 取值取**保守集**：只要「须」不要裸「应」（裸「应」会命中 相应/对应/适应 等叙述词）。
    r"\b(must(?:\s+not)?|shall(?:\s+not)?|may\s+not|should(?:\s+not)?|prohibited|prohibits?|"
    r"required\s+to|is\s+required|are\s+required|cannot|can\s+not|need\s+not|only\s+if|"
    r"is\s+unlawful|violat\w*|liable|responsib\w+\s+for)\b"
    r"|必须|不得|禁止|严禁|应当|须|不可|不允许", re.I)
COND = re.compile(
    r"\b(if|when|where|unless|in\s+the\s+case|in\s+order\s+to|so\s+that|before|after|without|"
    r"whether|fails?\s+to|implies?|implied|in\s+light\s+of|with\s+respect\s+to|based\s+on|"
    r"depending\s+on)\b", re.I)
THRESH_TERM = re.compile(
    r"(competent\s+and\s+reliable\s+scientific\s+evidence|competent\s+and\s+reliable\s+evidence|"
    r"reasonable\s+basis|randomi[sz]ed(?:\s+clinical)?\s+(?:trial|study|test)?|"
    r"well[- ]controlled(?:\s+clinical)?\s+(?:trial|study)?|statistically\s+significant|"
    r"clear\s+and\s+conspicuous|material(?:ly)?|preponderance\s+of\s+the\s+evidence|"
    r"Class\s+[IVX]+|510\(k\)\s+clearance)", re.I)
THRESH = re.compile(THRESH_TERM.pattern + r"|[\"“][^\"”]{2,60}[\"”]", re.I)
ACTION = re.compile(
    r"\b(substantiat\w+|disclos\w+|discourag\w+|prohibit\w*|correct\w*|discontinu\w+|refrain|"
    r"avoid|review|document|maintain|keep|provide|include|state|indicate|monitor|qualif\w+|"
    r"warn\w*|notif\w+|obtain|verify|ensure|comply|remov\w+|cease)\b", re.I)
# ★ 2026-10-13：**试过给 ACTION 加中文分支，已撤回** —— 留痕在此，别重复试。
#   动机与 MODAL 同源（本库是中文库，原先是纯英文）。实测两版都产噪声、且都**没能**让
#   PRD §7.3 出规则：
#     · 宽版（审查/审核/复核/记录/提供/保存/留存…）⇒ PRD 出 **8 条**，其中 **7 条是
#       `form=scope` 噪声**（rule_text 全是「（无显式条件，按无条件义务适用） → 处理：审查」），
#       唯一的 `prohibition` 来自 §7.1 的**表格行**，不是 §7.3；
#     · 窄版（去掉行政通用词，只留 披露/标注/删除/停止/纠正/确保/证明…）⇒ 出 **4 条，仍全是噪声**。
#   ⇒ 噪声来源不在 ACTION，而在**上游**：§5.2/§5.3/§5.4 这类**功能规格章节**本身就含
#     「标注」「记录」等动词，被 `scope` 形态当成了无条件的规则。
#     **该修的是 scope 形态的准入（要有可判定的命中条件），不是往 ACTION 里堆词。**
#   ⇒ 故 ACTION 保持**原样（纯英文）**；MODAL 的中文分支**保留**（那一条是对的：
#     中文条款此前 100% 过不了第 2 关，实测受影响 clause 单元 413 条）。
MODAL_VERB = re.compile(
    r"\b(must|shall|should|may not|cannot|can not|are required to|is required to|need not)\b"
    r"\s+(?:not\s+)?(?:also\s+|instead\s+|first\s+|only\s+|then\s+|further\s+)?(?:\w+ly\s+)?"
    r"(?!(?:be|not|have|has|had|do|does|did|is|are|was|were|the|a|an|of|to|in|on|at|for|with|"
    r"that|this|it|its)\b)([a-z]{3,})\b", re.I)
CITATION = re.compile(
    r"(F\.?\s?Supp|F\.?2d|F\.?3d|U\.?S\.?C|C\.?F\.?R|F\.?T\.?C\.?|LEXIS|v\.\s+[A-Z]|at\s+\*\d|"
    r"\baff.?d\b|Memorandum\s+Opinion|Final\s+Order\s+at|\bId\.\s|\bsee\s+also\b|\bciting\b|\baccord\b)", re.I)
EXAMPLE_HEAD = re.compile(
    r"^\s*(?:Example\s+\d+|The\s+marketer\s+(?:airs|runs|sells|posts|claims|states|markets)|"
    r"The\s+advertiser\s+(?:airs|runs|posts|markets))", re.I)
CHROME = re.compile(
    r"(skip\s+to\s+main\s+content|official\s+website\s+of\s+the\s+united\s+states|here.?s\s+how\s+you\s+know|"
    r"show/hide|menu\s+mega|secondary\s+menu|search\s+or\s+browse|search\s+small\s+search|"
    r"view\s+all\s+\w+\s+blog\s+posts|report\s+fraud|submit\s+public\s+comments|search\s+the\s+legal\s+library|"
    r"federal\s+government\s+websites\s+often\s+end|before\s+sharing\s+sensitive\s+information|"
    r"the\s+site\s+is\s+secure|the\s+https://\s+ensures|español|enforcement\s+menu|"
    r"advice\s+and\s+guidance\s+menu|main\s+navigation|return\s+to\s+top|take\s+action|"
    r"report\s+identity\s+theft|register\s+for\s+do\s+not\s+call|sign\s+up\s+for\s+consumer\s+alerts|"
    r"get\s+business\s+blog\s+updates|browse\s+legal\s+resources|search\s+the\s+legal\s+library\s+instead|"
    r"legal\s+library|find\s+legal\s+resources\s+and\s+guidance)", re.I)
MENU_KW = re.compile(
    r"(show/hide|\bmenu\b|search|browse|report\s+fraud|submit\s+public|return\s+to\s+top|\bsections\b|"
    r"cases\s+and\s+proceedings|press\s+release|blog\s+posts|enforcement|advocacy\s+and\s+research|"
    r"advisory\s+opinions|cooperation\s+agreements|federal\s+register\s+notices|rulemaking|premerger|"
    r"merger\s+review|anticompetitive|consumer\s+protection|get\s+your\s+free|take\s+action|sign\s+up|"
    r"register\s+for|español|english)", re.I)
FOOTNOTE_ONLY = re.compile(r"^\s*(?:\[\d+\]\s*)+[\.\s]*$")
HEADING_ONLY = re.compile(r"^\s*(?:[A-Z]\.|[IVX]+\.|\d+\.)\s*$")
TAG = re.compile(r"</?[a-zA-Z][^>]{0,200}>")
B64LIKE = re.compile(r"^[A-Za-z0-9+/=]{120,}$")
AUTHORITY = ("the ftc can", "the ftc has", "ftc and the food", "the ftc's", "the commission can",
             "the ftc provided", "the ftc issued", "the fda has", "the fda issues")


def is_chrome(t):
    lines = [x.strip() for x in t.split("\n") if x.strip()]
    if not lines:
        return True
    if CHROME.search(t) and len(t) < 400:
        return True
    if "official website of the united states" in t.lower():
        return True
    if re.match(r"^Health Products Compliance Guidance\s*\|", t) or \
       (t.count("|") >= 1 and len(t) < 120 and "compliance guidance |" in t.lower()):
        return True
    short = sum(1 for x in lines if len(x) < 45)
    kw = sum(1 for x in lines if MENU_KW.search(x))
    return (len(lines) >= 4 and short / len(lines) >= 0.6 and kw >= 3
            and not t.rstrip().endswith((".", "”", '"', "。")))


def norm(s):
    s = html.unescape(s).replace("\u00a0", " ").replace("\u200b", "")
    return re.sub(r"[ \t]+", " ", unicodedata.normalize("NFKC", s)).strip()


def clean(s):
    t = re.sub(r"<br\s*/?>", "\n", s)
    t = re.sub(r"</(p|li|div|tr|h[1-6])>", "\n", t)
    t = TAG.sub(" ", t)
    return re.sub(r"\n{2,}", "\n", norm(t)).strip()


def sha(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def first_sentence(t, cap=200):
    t = t.strip()
    m = re.search(r"[.!?](?:\s|$)", t)
    return t[:m.end()].strip() if m and m.end() <= cap else t[:cap].strip()


def clause_sentence(t, cap=240):
    """取「含义务/禁止模态的那一句」完整句：从模态词向前找到真正的句首。"""
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


def lexicon(t):
    vals = {m.group(0) for m in THRESH_TERM.finditer(t)}
    for m in re.finditer(r"[“\"]([^”\"]{12,80})[”\"]", t):
        vals.add(f"“{m.group(1)}”")
    return "；".join(sorted(vals)) or "（本条无显式阈值，处理方式为义务动作）"


def quote(t, cap=200):
    t = t.strip()
    return (t[:cap] + " …[截断]") if len(t) > cap else t


def dedupe_key(t):
    return re.sub(r"[^a-z0-9]+", "", t.lower())[:120]


def rule_form(t):
    if re.search(r"\b(discourag\w*|do\s+not|don.?t)\b", t, re.I):
        return "prohibition"
    if re.search(r"\bsubstantiat\w+", t, re.I):
        return "substantiation"
    if re.search(r"\bdisclos\w+|clear\s+and\s+conspicuous", t, re.I):
        return "disclosure"
    if re.search(r"\bmust\b|\bshall\b|required\s+to", t, re.I):
        return "mandate"
    if re.search(r"\b(may\s+not|cannot|can\s+not|prohibit|unlawful|liable)\b", t, re.I):
        return "prohibition"
    if re.search(r"\bshould\b", t, re.I):
        return "recommendation"
    return "scope"


# ══════════════════════════════════════════════════════ 抽取 + 蒸馏
def distill_resource(units):
    """逐个单元过判定。返回 (rules, rejected, clauses)。"""
    # 主来源 = 该资源里单元数最多的那个 source_sha256（其余 sha 是再次抓取的版本）
    sha_cnt = collections.Counter(u.get("source_sha256", "") for u in units)
    main_sha = sha_cnt.most_common(1)[0][0]
    # 跨 sha 的版本残留配对（O(n)）：两两「逐字相同」或「一方是另一方前缀」（重抓时截断）。
    # 只按前 60 字符分桶比较，避免 O(n²)。
    by_text, pref_buckets = {}, collections.defaultdict(list)
    for u in units:
        if u.get("source_sha256") != main_sha:
            continue
        t = u["text"].strip()
        by_text.setdefault(t, u["unit_id"])
        pref_buckets[t[:60]].append((t, u["unit_id"]))
    for b in pref_buckets.values():                      # 桶内按短→长，便于前缀判定
        b.sort(key=lambda x: len(x[0]))

    def version_remnant(t):
        """alt 单元是否为主来源的版本残留？返回 (kind_or_None, 对应主来源 unit_id)。"""
        s = t.strip()
        if not s:
            return None, None
        sib = by_text.get(s)
        if sib:
            return "duplicate_source_version", sib
        for mt, muid in pref_buckets.get(s[:60], ()):
            if mt.startswith(s) or s.startswith(mt):
                return "source_version_fragment", muid
        return None, None

    rules, rejected, clauses = [], [], []
    seen, n = {}, 0
    for i, u in enumerate(units):
        uid, anchor, raw = u["unit_id"], u["anchor"], u["text"]
        main = (u.get("source_sha256") == main_sha)
        t = clean(raw)
        art = []
        if TAG.search(raw):
            art.append("html_tag")
        if B64LIKE.match(raw.strip()):
            art.append("encoded_payload")
        if re.search(r"</?(span|li|ul)\b", raw, re.I) and MODAL.search(t) and \
           len(re.findall(r"\b(must|shall|may not|should)\b", t, re.I)) >= 2:
            art.append("multi_requirement_merged")
        if re.search(r"</(li|span)>", raw, re.I):
            art.append("unclosed_markup")

        seg_anchor = f"{anchor}/seg-{i + 1}"
        clauses.append(dict(seq=i + 1, unit_id=uid, anchor=anchor, seg_anchor=seg_anchor,
                            source_sha256=u.get("source_sha256", ""),
                            source_provenance=("main" if main else "alt_crawl"),
                            order_in_parent=u.get("order_in_parent"), char_count=len(t),
                            text=t, artifacts=sorted(set(art))))

        def reject(kind, reason):
            rejected.append(dict(kind=kind, unit_id=uid, anchor=anchor, seg_anchor=seg_anchor,
                                 resource_id=u["resource_id"], kb_type=u.get("kb_type"),
                                 unit_type=u.get("unit_type"), char_count=len(t),
                                 source_sha256=u.get("source_sha256", ""),
                                 source_provenance=("main" if main else "alt_crawl"),
                                 reason=reason, text=quote(t, 200)))

        # ── 第 0 关：抓取版本残留（同一资源出现第二个 source_sha256）
        # 判据：同资源里单元数最多的 sha 视为主来源；其余 sha 的单元在成规则前一律先登记，
        #       避免「同一段正文换个抓取版本就多出一条规则」。
        if not main:
            vkind, sib = version_remnant(t)
            if vkind:
                why = ("与主来源单元 %s 逐字相同" % sib if vkind == "duplicate_source_version"
                       else "是主来源单元 %s 的截断前/后段（逐字前缀关系）" % sib)
                reject(vkind,
                       f"同一资源存在第二个 source_sha256（本单元属于重抓版本）：{why}，属抓取版本残留，不蒸馏"
                       " —— 应在 L0/L2 侧去重，不在 L3 侧把同一段正文重复产出成规则")
            else:
                reject("alt_crawl_unmatched",
                       "同一资源存在第二个 source_sha256（本单元属于重抓版本）：主来源里既无逐字同款、"
                       "也无前缀关系的对应单元，版本关系无法确认，不蒸馏 —— 应在 L0/L2 侧核清抓取版本")
            continue

        # ── 第 1 关：不是条款文本本体
        if is_chrome(t):
            reject("page_chrome", "页面 chrome（导航/菜单/页脚样板），非政策文本本体，不参与条款判定"); continue
        if not t:
            reject("empty_text", "正文为空（抽取未取到内容）"); continue
        if FOOTNOTE_ONLY.match(t):
            reject("footnote_marker", "仅脚注序号，无判定内容"); continue
        if HEADING_ONLY.match(t):
            reject("heading_only", "仅小节标题字母/序号（如「B.」），无判定内容 —— 建议 L2 侧重切，标题应与正文同单元"); continue
        if B64LIKE.match(t.strip()):
            reject("encoded_payload", "编码载荷（疑似 base64），非自然语言条款"); continue

        has_modal, has_cond = bool(MODAL.search(t)), bool(COND.search(t))
        has_thresh, has_action = bool(THRESH.search(t)), bool(ACTION.search(t))
        mv = MODAL_VERB.search(t)
        modal_hit = MODAL.search(t) or mv
        is_example = bool(EXAMPLE_HEAD.match(t))

        # ── 第 2 关：没有义务/禁止模态 → 不成规则
        if not has_modal:
            if is_example:
                reject("policy_example_not_rule",
                       "政策举例（Example N /「The marketer …」情形描述），是示例不是规范条款，"
                       "单独不成规则（其规范结论在对应正文条款）")
            elif any(k in t.lower() for k in AUTHORITY):
                reject("agency_authority_not_rule",
                       "描述主管机关权力/机构分工/执法史，未对广告主施加「须/不得」义务，不构成可判定规则")
            elif CITATION.search(t):
                reject("citation_fragment_not_rule",
                       "法学期刊引注残片（判例/条文引用），无「须/不得」义务，不构成可判定规则")
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

        # ── 第 3 关：有模态，但判定条件保不住
        if re.match(r"^[a-z]", t) and not re.match(r"^[a-z]{1,3}\s*[)\.]", t):
            reject("mid_sentence_fragment",
                   "单元从句子中间开始（首字符小写），是把上一句切了一半的残片，判定条件不完整"
                   " —— 应在 L2 侧重切，不在 L3 侧补全")
            continue
        if len(t) > 2000:
            reject("oversized_unit_blob",
                   f"单元正文 {len(t)} 字符（L2 切分上限拼接所致），里面是多条条款的连缀，"
                   "给不出单一「判定条件 + 阈值」—— 应在 L2 侧重切，不在 L3 侧硬切")
            continue
        if not (has_action or has_thresh or bool(mv)):
            reject("obligation_without_action",
                   "有义务模态但既无处理动作也无阈值/词表，无法给出「命中→怎么处理」")
            continue
        if "multi_requirement_merged" in art:
            reject("multi_requirement_merged",
                   "一个单元内塞入 ≥2 个独立要求 —— 按「一个法条 = 一个单元」口径该单元本身是脏的，"
                   "应在 L2 侧重切，不在 L3 侧硬容错")
            continue

        k = dedupe_key(t)
        if k in seen:
            reject("duplicate_of", f"与该资源内 seq={seen[k]} 逐字重复，不重复产出规则")
            continue
        seen[k] = i + 1

        # ── 成规则
        ev = dict(unit_id=uid, anchor=anchor, seg_anchor=seg_anchor,
                  source_sha256=u.get("source_sha256", ""))
        form = rule_form(t)
        cond = (clause_sentence(t) if (has_cond or form in ("mandate", "prohibition", "substantiation"))
                else "（无显式条件，按无条件义务适用）")
        thr = lexicon(t)
        acts = sorted({m.group(0).lower() for m in ACTION.finditer(t)})
        if not acts and mv:
            acts = [mv.group(0).strip().lower()]
        act = "；".join(acts[:6]) or "（未识别到处理动作，须人工补）"
        pos_ok = modal_hit is not None and modal_hit.start() >= 0 and \
            cond.find(t[modal_hit.start():modal_hit.start() + 12]) >= 0
        rules.append(dict(
            rule_id="r-" + sha(uid + "|" + form)[:16],
            status="candidate",              # ★ 候选 ≠ 定稿
            article_no="",                   # ★ 条款号由 L4 发放，本层不自造
            kb_type="external_standard",
            form_scope="external_standard",  # ★ 支线标识：与 wording 支线的 form 不混
            **{"form": form},
            resource_id=u["resource_id"],
            source_provenance="main",        # ★ 主来源 sha 的单元；重抓版本一律不进规则
            source=dict(resource_id=u["resource_id"], unit_id=uid, anchor=anchor,
                        seg_anchor=seg_anchor, source_sha256=u.get("source_sha256", "")),
            condition=cond,
            threshold_or_lexicon=thr,
            required_action=act,
            forbidden_expression="",
            suggested_replacement="",
            rule_text=f"[{form}] 命中条件：{cond} → 处理：{act}（阈值/词表：{thr}）",
            evidence_quote=(t if len(t) <= 400 else t[:400] + " …[逐字摘录已截断，全文见 clause_units]"),
            evidence_units=[ev],
            evidence_digest=sha(uid + "|" + t),
            evidence_level="cited",
            applicable_jurisdiction="US",
            effective_from="", effective_to="",
            owner="", verification="待人工复核", rule_status="provisional",
            quality=("strong" if (cond != "（无显式条件，按无条件义务适用）" and pos_ok
                                 and not re.match(r"^\s*(?:See(?:\s+also)?|As\s+noted|As\s+discussed)",
                                                  cond, re.I))
                     else ("weak" if cond != "（无显式条件，按无条件义务适用）" else "unconditional")),
            p_level="P1", risk_level="unknown",
            supersedes=[], superseded_by="", superseded_at="",
            distiller_version=DV, observed_at=RUN,
        ))
        n += 1
    return rules, rejected, clauses


def main():
    U = [json.loads(l) for l in open(os.path.join(L2, "units.jsonl"), encoding="utf-8") if l.strip()]
    res = collections.defaultdict(list)
    for u in U:
        if u.get("kb_type") == "external_standard" and u.get("unit_type") == "clause":
            res[u["resource_id"]].append(u)
    targets = ([RID_FILTER] if RID_FILTER else sorted(res))
    if RID_FILTER and RID_FILTER not in res:
        raise SystemExit(f"[FATAL] 该资源在 L2 里没有 external_standard/clause 单元：{RID_FILTER}")

    all_rules, all_rej, all_units, parts = [], [], [], []
    for rid in targets:
        units = sorted(res[rid], key=lambda u: u.get("order_in_parent") or 0)
        r, j, c = distill_resource(units)
        used = {e["unit_id"] for x in r for e in x["evidence_units"]}
        rej_u = {x["unit_id"] for x in j}
        unacc = {u["unit_id"] for u in units} - used - rej_u
        sha_cnt = collections.Counter(u.get("source_sha256", "") for u in units)
        main_sha = sha_cnt.most_common(1)[0][0]
        parts.append(dict(resource_id=rid, clause_units=len(units), rules=len(r),
                          rejected=len(j), unaccounted=len(unacc),
                          source_sha256=sorted(sha_cnt),
                          main_source_sha256=main_sha,
                          alt_crawl_units=len(units) - sha_cnt[main_sha],
                          forms=dict(collections.Counter(x["form"] for x in r)),
                          rejected_kinds=dict(collections.Counter(x["kind"] for x in j))))
        all_rules += r; all_rej += j; all_units += c
        if unacc:
            raise SystemExit(f"[FATAL] 取数对账不为 0（{rid}）：{len(unacc)} 个单元没归属 → {sorted(unacc)[:5]}")

    # 幂等：与现行 manifest 比 evidence_digest
    prev = {}
    if os.path.exists(OUT_MAN):
        for l in open(OUT_MAN, encoding="utf-8"):
            if l.strip():
                d = json.loads(l)
                if d.get("rule_id") and d.get("form_scope") == "external_standard":
                    prev[d["rule_id"]] = d
    new = unchanged = 0
    for x in all_rules:
        o = prev.get(x["rule_id"])
        if o and o.get("evidence_digest") == x["evidence_digest"]:
            unchanged += 1
        else:
            new += 1

    print(json.dumps(dict(run=RUN, apply=APPLY, targets=parts,
                          rules=len(all_rules), rejected=len(all_rej), clause_units=len(all_units),
                          new=new, unchanged=unchanged,
                          forms=dict(collections.Counter(x["form"] for x in all_rules)),
                          quality=dict(collections.Counter(x["quality"] for x in all_rules)),
                          rejected_kinds=dict(collections.Counter(x["kind"] for x in all_rej)),
                          unaccounted=0), ensure_ascii=False, indent=1))
    if not APPLY:
        print("[dry-run] 未落盘。加 --apply 落盘。")
        return 0

    # ── 落盘（先归档，后写）
    arch = {}
    for p, tag in ((OUT_CAND, RUN), (OUT_REJ, RUN)):
        a, s = archive(p, tag)
        arch[os.path.relpath(p, KB)] = {"archived_to": os.path.relpath(a, KB) if a else None,
                                        "sha256": s}
    os.makedirs(os.path.dirname(OUT_CAND), exist_ok=True)

    def _merge(path, rows, key):
        """按 `key` 合并：**保留既有行**（key 不在新集里的），再把新行接在后面。

        ★ 2026-10-13 修（实测缺陷，不是预防性设计）。原先这两处是
          `open(..., "w")` **无条件覆盖**，而**同一个引擎**写的 `OUT_MAN`
          （`:543`）是 `"a"` **追加**（作者还特意注了「★ 追加，不覆盖」）
          ⇒ 两者语义不一致：manifest 累积全库规则，候选件只留最后一个资源。
        **实测**（重定向副本，预置活库的 246 行、只跑 1 个资源）：
          246 行 → **8 行** —— amazon / google 等多个资源的 **238 行规则候选被冲掉**，
          而 manifest 里那些 `rule_id` 仍在 ⇒ **悬空引用**。
        候选件是**全库共享**的（与 manifest 同域），必须按 `rule_id` 合并；
        拒绝台账按 `unit_id` 合并（同一单元重跑时以新判为准）。
        归档仍在前面做（`archive()`），合并不取消留底。
        """
        new_keys = {r.get(key) for r in rows}
        old = []
        if os.path.exists(path):
            for line in open(path, encoding="utf-8"):
                if not line.strip():
                    continue
                try:
                    d = json.loads(line)
                except ValueError:
                    continue
                if d.get(key) not in new_keys:
                    old.append(d)
        return old, rows

    _old_c, _new_c = _merge(OUT_CAND, all_rules, "rule_id")
    _old_r, _new_r = _merge(OUT_REJ, all_rej, "unit_id")
    # ── 人工口径：所属类别 / 所属子类 / p_level（2026-10-17）────────────────────
    # ★ 为什么也要接在这一处：本函数对**既有行是「保留原样」**（`_merge` 的 old 段），
    #   但**重蒸过的资源**那几行是**新建的**（`all_rules`）⇒ 那几行不带人工口径。
    #   两条来源都盖一遍，才不会出现「同一份候选件里一半有归类、一半没有」。
    # 真源 = `kb/l3/registry/rule-taxonomy.json`；实现 = kb_rule_dimensions.apply_taxonomy（唯一一份）。
    # ★ 不改 risk_level（另一个轴），只盖这三格 + `taxonomy_basis`。
    sys.path.insert(0, os.path.join(KB, "l3"))
    import kb_rule_dimensions as _kb_dim_tax          # noqa: E402  （唯一实现）
    try:
        _tax = _kb_dim_tax.load_taxonomy(_kb_dim_tax.TAXONOMY_DEFAULT)
    except FileNotFoundError:
        _tax = None
        if APPLY:
            print("[规则归类] ⚠ 注册表不在位（%s）⇒ 本轮不盖归类/优先级（**不静默**）"
                  % os.path.relpath(_kb_dim_tax.TAXONOMY_DEFAULT, KB))
    if _tax:
        _st1 = _kb_dim_tax.apply_taxonomy(_new_c, _tax, mode="force")
        _st2 = _kb_dim_tax.apply_taxonomy(_old_c, _tax, mode="force")
        if APPLY:
            print("[规则归类] 注册表 %s：新 %d 条 / 既有 %d 条 已盖（p_level 变更 %d 条 ｜ 冲突 %d）"
                  % (_tax["version"], _st1["matched"], _st2["matched"],
                     _st1["p_level_changed"] + _st2["p_level_changed"],
                     len(_st1["conflicts"]) + len(_st2["conflicts"])))
    with open(OUT_CAND, "w", encoding="utf-8") as fh:
        for x in _old_c + _new_c:
            fh.write(json.dumps(x, ensure_ascii=False, sort_keys=True) + "\n")
    with open(OUT_REJ, "w", encoding="utf-8") as fh:
        for x in _old_r + _new_r:
            fh.write(json.dumps(x, ensure_ascii=False, sort_keys=True) + "\n")
    if APPLY:
        print("[合并] 候选件 保留既有 %d 行 + 新 %d 行；拒绝台账 保留既有 %d 行 + 新 %d 行"
              % (len(_old_c), len(_new_c), len(_old_r), len(_new_r)))
    with open(os.path.join(L3, "clause_units_external_standard.jsonl"), "w", encoding="utf-8") as fh:
        for x in all_units:
            fh.write(json.dumps(x, ensure_ascii=False, sort_keys=True) + "\n")
    with open(OUT_MAN, "a", encoding="utf-8") as fh:      # ★ 追加，不覆盖
        for x in all_rules:
            fh.write(json.dumps({"rule_id": x["rule_id"], "evidence_digest": x["evidence_digest"],
                                 "support_count": 1, "form": x["form"],
                                 "form_scope": "external_standard", "status": "provisional",
                                 "distiller_version": DV, "observed_at": RUN},
                                ensure_ascii=False, sort_keys=True) + "\n")
    rec = dict(run=RUN, distiller_version=DV, kb_version=KBV, applied_at=RUN,
               targets=parts, rules=len(all_rules), rejected=len(all_rej),
               clause_units=len(all_units), new=new, unchanged=unchanged,
               unaccounted=0, archives=arch,
               outputs=[os.path.relpath(OUT_CAND, KB), os.path.relpath(OUT_REJ, KB),
                        os.path.relpath(os.path.join(L3, "clause_units_external_standard.jsonl"), KB)],
               note="候选 ≠ 定稿；article_no 留空由 L4 发放；拒绝台账与 candidates/rules.jsonl 分离")
    with open(OUT_RUN, "w", encoding="utf-8") as fh:
        json.dump(rec, fh, ensure_ascii=False, indent=2, sort_keys=True); fh.write("\n")
    print(f"[apply] 落盘完成：规则 {len(all_rules)}（新 {new} / unchanged {unchanged}）"
          f"｜拒绝 {len(all_rej)}｜单元 {len(all_units)}｜run 记录 {os.path.relpath(OUT_RUN, KB)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
