#!/usr/bin/env python3
"""kb-content-review 的参考实现：按 L7 两段协议跑「查 → 答」。

只读 kb/l0~kb/l6（含 kb/l3 的 article_no），只写 kb/l7/reports 与 stdout。

四层下探（顺序写死）：
  1. P0 确定性匹配  → kb/l5/matcher.py（命中即 BLOCK，不走向量）
  2. 规则层        → kb/l3/candidates/rules.jsonl（按 kb_type + 禁用片段逐字命中）
  3. 单元层        → kb/l6/retriever.py（BM25 主；原始分低于门限时才启用向量补）
  4. 原文层        → 按 anchor 回 kb/l0/records/<表>/<记录>.json 取逐字原文，并核对 source_sha256

用法：
  python3 review.py --text "待审文案"
  python3 review.py --file in.txt --content-type text --position "段落 2"
  python3 review.py --text "..." --json
  python3 review.py --text "..." --report-dir kb/l7/reports
退出码：0 = 有结论（PASS/REVIEW/BLOCK）；3 = 拒答；2 = 用法错
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

import argparse, glob, hashlib, json, os, re, subprocess, sys, time, unicodedata

#: 库根判定的六件套：一个都不能少（少哪一个，对应那段协议就跑不了）。
#:   l7.json          → 门限 / 受控词表 / 责任人（引用契约与分流规则的来源）
#:   rules.jsonl      → 规则层（条款号 + 禁用表达）
#:   matcher.py       → P0 确定性匹配
#:   retriever.py     → 单元层 BM25 / 向量
#:   output_template.md → 输出模板
#:   kb.json          → 库名映射（引用契约里不许自造库名）
#:
#: ★ 2026-10-01 补第七/第八件 —— **数据产物**，不是代码。为什么非补不可（两次实测）：
#:   ① 缺 `l6/bm25/meta.json`：`retriever.py` 抛 FileNotFoundError 崩（拿副本做隔离测试时撞到）；
#:   ② 缺 `l5/p0_patterns.jsonl`：`matcher.py:21` 读的是**同目录的模式表数据**，
#:      缺了**不报错**，P0 命中静默变 0 → 同一段文案在真库判 `BLOCK`、在缺文件的副本判 **`PASS`**。
#:      也就是说：**缺数据会表现成"没问题"** —— 这正是本库反复栽的「静默降级」那一类，
#:      而且后果是 "该拦的漏放"，比崩掉更危险。
REQUIRED_FILES = (
    ("l7", "registry", "l7.json"),
    ("l3", "candidates", "rules.jsonl"),
    ("l5", "matcher.py"),
    ("l6", "retriever.py"),
    ("l7", "output_template.md"),
    ("l0", "registry", "kb.json"),
    ("l5", "p0_patterns.jsonl"),      # ★ 数据产物：缺则 P0 静默不通
    ("l6", "bm25", "meta.json"),      # ★ 数据产物：缺则检索直接崩
)

#: 库根标记（`kb/KB-ROOT.json`）：有它就直接认，不必逐件检查。
ROOT_MARKER = ("KB-ROOT.json",)

#: 已知落点（本机现状；换机器/挪库时用 --kb-root 或 KB_ROOT 覆盖）。
COMMON_ROOTS = [
    os.path.expanduser("~/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理"),
    os.path.expanduser("~/.dsh/Momcozy知识库"),
]


def _check_root(path):
    """这个目录算不算库根？返回 (bool, 说明)。

    ★ 2026-10-01 改：KB-ROOT.json 不再**短路**下面的产物检查。
      原先「有标记就直接 True」—— 于是本文件顶上新增的两件**数据产物**
      （`l5/p0_patterns.jsonl` / `l6/bm25/meta.json`）在权威库上**永远不会被校验**
      （权威库恰有该标记），补了等于没补。现在标记只用于**识别**（并挡住派生视图），
      **不代替**产物存在性检查：检查项全是 `os.path.exists`，无加载开销。
    """
    if not path or not os.path.isdir(path):
        return False, "目录不存在"
    kb = os.path.join(path, "kb")
    if not os.path.isdir(kb):
        return False, "没有 kb/ 目录"
    has_marker = os.path.exists(os.path.join(kb, *ROOT_MARKER))
    missing = [os.path.join("kb", *rel) for rel in REQUIRED_FILES
               if not os.path.exists(os.path.join(kb, *rel))]
    if missing:
        # 派生视图（给工作台镜像吃的壳）最容易误判：它顶层也有 _meta/，但只有 3_措辞表达库/。
        if os.path.exists(os.path.join(path, "_meta", "DERIVED.md")) or os.path.exists(
                os.path.join(kb, "_meta", "DERIVED.md")):
            return False, ("这是**派生视图**（服务工作台镜像的壳，见 _meta/DERIVED.md），"
                           "不是权威分层库")
        return False, "缺：" + "、".join(missing[:3]) + ("…" if len(missing) > 3 else "")
    return True, ("有 kb/KB-ROOT.json 标记，且 %d 件产物齐全" % len(REQUIRED_FILES)
                  if has_marker else "%d 件齐全" % len(REQUIRED_FILES))


def _find_root(start, explicit=None):
    """定位知识库根：--kb-root → KB_ROOT → 已知落点 → 从 start 往上找。

    为什么要这一整套：技能装在全局（`~/.dsh/skills/`）时，脚本位置已经不在知识库内，
    只靠「往上找」会走到别的目录上去 —— 实测撞上过派生视图被误判成库根。所以：
    **先按显式配置找，再按已知落点找，最后才往上找**；都不成才报错，报错里列出试过什么。
    """
    tried = []
    candidates = []
    if explicit:
        candidates.append(("--kb-root", explicit))
    if os.environ.get("KB_ROOT"):
        candidates.append(("环境变量 KB_ROOT", os.environ["KB_ROOT"]))
    for path in COMMON_ROOTS:
        candidates.append(("已知落点", path))
    for label, path in candidates:
        if not path:
            continue
        path = os.path.abspath(os.path.expanduser(path))
        ok, why = _check_root(path)
        tried.append(f"{label}={path} → {why}")
        if ok:
            return path
        # **显式指定的路径无效就直接报错**，不许悄悄换一个库继续跑：
        # 使用者明确说了「用这个库」，静默换成别的库会得到一份看起来正常、其实换了依据的报告，
        # 比报错危险得多。（KB_ROOT 与本机已知落点仍允许继续往下试。）
        if label == "--kb-root":
            raise RuntimeError(
                f"--kb-root 指定的目录不是知识库根：{path}\n  原因：{why}\n"
                "  库根要含 kb/KB-ROOT.json **且** l0…l7 的 %d 件产物齐全"
                "（代码件 + 数据产物件，见 REQUIRED_FILES）；"
                "派生视图（只有 3_措辞表达库/ + _meta/DERIVED.md 的壳）不算库根。"
                % len(REQUIRED_FILES)
            )
    d = os.path.abspath(start)
    while True:
        ok, why = _check_root(d)
        tried.append(f"向上查找={d} → {why}")
        if ok:
            return d
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    raise RuntimeError(
        "找不到知识库根目录（要能找到 <根>/kb/l0…l7）。试过：\n  "
        + "\n  ".join(tried)
        + "\n用 --kb-root <知识库根> 或环境变量 KB_ROOT 指定（根目录要含 kb/ 与 l0…l7 这几层）。"
    )


# 模块级 ROOT 只做「尽力而为」：import 期拿不到库不算错（别的工具 import 本模块不该因此挂），
# 真正要用库时（main 开头）会再解析一次，失败就带全景报错。
try:
    ROOT = _find_root(os.path.dirname(os.path.abspath(__file__)))
except RuntimeError:
    ROOT = None
L7 = os.path.join(ROOT, "kb", "l7")
REG_PATH = os.path.join(L7, "registry", "l7.json")
RULES = os.path.join(ROOT, "kb", "l3", "candidates", "rules.jsonl")
MATCHER = os.path.join(ROOT, "kb", "l5", "matcher.py")
L6REG = os.path.join(ROOT, "kb", "l6", "registry", "l6.json")


def norm(s):
    s = unicodedata.normalize("NFKC", s or "")
    return re.sub(r"\s+", " ", s).strip().casefold()


def load_registry():
    return json.load(open(REG_PATH, encoding="utf-8"))


def _l4_article_no_map():
    """rule_id → 条款号（从 kb/l4/canonical/*.jsonl 建，只读）。

    为什么需要（2026-09-30 实测，MVP 被它挡住）：`kb/l3/candidates/rules.jsonl` 里的
    `article_no` 是**空的** —— L4 发号后没有写回候选文件（见 kb/l7/registry/l7.json →
    article_no_source.field_lives_in_was 的说明）。于是引用契约六要素里的「条款号」一直空着，
    报告里印出「第  条」。L4 定稿侧 509/509 条都有条款号，故在**加载时 join 补齐**，
    不改任何文件（口径：只补空值，已有值不动）。
    """
    m, d = {}, os.path.join(ROOT, "kb", "l4", "canonical")
    for p in sorted(glob.glob(os.path.join(d, "*.jsonl"))):
        for l in open(p, encoding="utf-8"):
            if not l.strip():
                continue
            r = json.loads(l)
            if r.get("rule_id") and r.get("article_no"):
                m[r["rule_id"]] = r["article_no"]
    return m


def load_rules():
    latest = {}
    for l in open(RULES, encoding="utf-8"):
        if l.strip():
            r = json.loads(l)
            latest[r["rule_id"]] = r
    amap = _l4_article_no_map()
    filled = 0
    for rid, r in latest.items():
        if not str(r.get("article_no") or "").strip() and amap.get(rid):
            r["article_no"] = amap[rid]
            filled += 1
    if filled:
        print("[fix] 条款号：候选文件缺 %d 条，已从 L4 定稿 join 补齐（只读，不改文件）" % filled)
    return latest


# ---------------- 分类：受控词表 ----------------
def classify(rule, vocab):
    code = (rule.get("rule_code") or "").strip()
    if code and code in vocab["code_map"]:
        return vocab["code_map"][code], f"rule_code={code}"
    blob = " ".join(str(rule.get(k) or "") for k in ("rule_text", "reason", "suggested_replacement"))
    for pat, cat, sub in vocab["keyword_map"]:
        if re.search(pat, blob, re.IGNORECASE):
            return [cat, sub], f"keyword_map:{pat}"
    return list(vocab["categories"]["未分类"]["subs"].keys())[0:1] + [] if False else ["未分类", "未分类"], "fallback"


# ---------------- 第 1 层：P0 ----------------
def layer_p0(text):
    t0 = time.perf_counter()
    p = subprocess.run([sys.executable, MATCHER, "--text", text, "--json"],
                       capture_output=True, text=True)
    elapsed = (time.perf_counter() - t0) * 1000
    out = json.loads(p.stdout) if p.stdout.strip().startswith("{") else {"hits": [], "elapsed_ms": None}
    return {"engine": "kb/l5/matcher.py", "exit_code": p.returncode,
            "total_elapsed_ms": round(elapsed, 2), "engine_elapsed_ms": out.get("elapsed_ms"),
            "hits": out.get("hits", [])}


# ---------------- 第 2 层：规则层 ----------------
def layer_rules(text, rules, kb_type=None):
    tn = norm(text)
    hits = []
    for rid, r in rules.items():
        if kb_type and r.get("kb_type") != kb_type:
            continue
        frags = [x.strip() for x in re.split(r"[,，;；]", r.get("forbidden_expression") or "") if x.strip()]
        matched = []
        for f in frags:
            fn = norm(f)
            if not fn:
                continue
            if re.search(r"[0-9A-Za-z]", fn):
                if re.search(r"(?<![0-9A-Za-z])" + re.escape(fn) + r"(?![0-9A-Za-z])", tn):
                    matched.append(f)
            elif fn in tn:
                matched.append(f)
        if matched:
            hits.append({"rule_id": rid, "article_no": r.get("article_no"), "rule_code": r.get("rule_code"),
                         "p_level": r.get("p_level"), "risk_level": r.get("risk_level"),
                         "authority": r.get("authority"), "kb_type": r.get("kb_type"),
                         "authority_source_table": r.get("authority_source_table"),
                         "matched_fragments": matched[:8], "anchor": r.get("anchor"),
                         "source_sha256": (r.get("evidence_units") or [{}])[0].get("source_sha256"),
                         "rule_text": r.get("rule_text"), "suggested_replacement": r.get("suggested_replacement")})
    return {"engine": "kb/l3/candidates/rules.jsonl", "kb_type_filter": kb_type,
            "rules_scanned": len(rules), "hits": hits}


# ---------------- 第 3 层：单元层（BM25 主 / 向量补） ----------------
def rule_cited_anchors(rules):
    """被规则引用过的证据锚点集合 —— 用来判断检索到的材料是不是「知识库确实管这块」。"""
    out = set()
    for r in rules.values():
        for u in r.get("evidence_units") or []:
            if u.get("anchor"):
                out.add(u["anchor"])
        if r.get("anchor"):
            out.add(r["anchor"])
    return out


def rule_cited_resources(rules):
    """「被引用锚点」所属的**源素材**集合（`resource_id`）—— **同源归并用**（2026-10-08 · B）。

    ## 为什么需要它（实测，2026-10-08）

    同一件素材在 L2 会切成**多个单元**、拿到**多个锚点**，而锚点名字按**字段**分叉：

      `#正面和负面样本/recvw2wE9MEpQK/原文反馈`  ← 案例/规则引用的是这个
      `#素材/recvw2wE9MEpQK/图片素材/#img.1`    ← **图上文字**，检索命中的是这个

    覆盖判据要求「**命中单元** ∈ 被引用锚点池」⇒ **同源不同 unit ⇒ 永远匹配不上**。
    这正是引擎注释里那句的机理：「Top3 全是该图自己的单元，却 `rule_cited_unit_hits=[]`」。
    图片/视频类素材**必然**踩这一条（图上文字的锚点与被引字段的锚点永远不同名）。

    ## 收窄（**不许放宽**）

    只认**能唯一确定来源**的规则：`resource_id` 单值，或 `resource_ids` **恰好一个**。
    一键多源（`resource_ids` 多个）时**宁可不算** —— 否则「命中隔壁素材」会被算成覆盖，
    那是 fail-open 方向，比漏判更坏。
    """
    out = set()
    for r in rules.values():
        rid = r.get("resource_id")
        if rid:
            out.add(rid)
            continue
        rids = [x for x in (r.get("resource_ids") or []) if x]
        if len(rids) == 1:
            out.add(rids[0])          # 恰好一个来源 ⇒ 可唯一确定；多个来源 ⇒ 保守跳过
    return out


def resources_of_anchors(anchors):
    """给定锚点，回 L2 单元表取它们**归属的那件素材**（父记录的 `resource_id`）。

    ## 为什么不用解析字符串（实测，2026-10-08）

    anchor 形如 `#<表>/<记录>/<字段>`，看起来第二段就是记录 id —— 但**只有 60.8% 成立**：
    13,095 条单元里 **4,788 条 anchor 只有一段**（如 `#l.1-0`、`#h.文案信息层级`），
    第二段根本不存在。**解析法会在四成情况下静默失效** —— 所以必须回权威表取。

    ## ★★ 为什么不能直接用单元自己的 `resource_id`（**自证 B6 逼出来的**）

    同一件素材在 L2 会切成**记录级**与**附件级**两类单元，两者的 `resource_id` **不是同一个**：

      `#正面和负面样本/recvw2wE9MEpQK/原文反馈` → `bitable__tbld8qE92YaY38Yz__recvw2wE9MEpQK`
      `#素材/recvw2wE9MEpQK/图片素材/#img.1`    → `…__recvw2wE9MEpQK_fldnvxjaSr_K0DT…`（附件级）

    照字面比 `resource_id` 相等 ⇒ **在最该生效的那条素材上静默变成空操作**
    （这正是 `selftest_coverage.py` B6 第一版变红的原因，不是它写错了）。

    ⇒ 正解在数据里：**父单元自己声明了附件锚点归它**（`media_refs[].anchor` +
      `attachment_unit="merged_into_parent"`）——**是数据声明的归属，不是解析字符串猜的**。
      所以本函数把「附件锚点」归到**父记录**的 `resource_id`，再拿去比。

    ## 为什么要扫 35MB

    `kb/l2/units.jsonl` 是唯一同时有 `anchor` / `resource_id` / `media_refs` 的权威表。
    但**只需要查给到的那几个锚点**（命中的 top 行 ≤5）⇒ 一次流式扫描、覆盖满即提前退出，
    不把全表装进内存。**只在真要判同源时才调**（见调用点条件），常用路径零开销。
    """
    want = {a for a in anchors if a}
    if not want:
        return {}
    own, alias, path = {}, {}, os.path.join(ROOT, "kb", "l2", "units.jsonl")
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                if '"anchor"' not in line:
                    continue
                try:
                    d = json.loads(line)
                except Exception:                              # noqa: BLE001
                    continue
                a = d.get("anchor")
                if a in want:
                    own[a] = d.get("resource_id")
                if '"media_refs"' in line:
                    for m in (d.get("media_refs") or []):
                        ma = (m or {}).get("anchor")
                        if ma in want:
                            # ★ 附件锚点 ⇒ 归到**本单元（父）**的 resource_id
                            alias[ma] = d.get("resource_id")
                if want <= (set(own) | set(alias)):
                    break                                      # 全覆盖就提前退出
    except OSError:
        # 读不到就返回已知的（调用方按「取不到=不算」处理，保守一侧）
        return _merge_owner(own, alias)
    return _merge_owner(own, alias)


def _merge_owner(own, alias):
    """合并「单元自己的 resource_id」与「父单元声明的附件归属」——**附件归属优先**。

    分开写成一个小函数，是为了让「谁优先」这件事**只有一处**、且能被自证点到名：
    附件锚点在两处都会出现（附件单元自己一次、父单元 `media_refs` 一次），
    按父单元的声明走才能得到**父记录**的 id —— 那才是「同源」要比的东西。
    """
    out = dict(own)
    out.update(alias)               # ← 附件锚点被父声明覆盖；记录级锚点 alias 里没有，不受影响
    # ★★ 2026-10-08（第三批）：**再把写法归一**（见 `canon_resource`）。
    return {k: canon_resource(v) for k, v in out.items()}


# ── ★★ 2026-10-08（第三批）：同一个父记录的**三种 resource_id 写法**，归一到一种 ──────
#   `kb/l2/units.jsonl` 是两批入库件拼起来的，**同一张表的同一条记录**写过三种写法：
#     ① `bitable__<表>__<记录>`                        ← 记录级（规则/案例引用侧用的就是它）
#     ② `bitable__<表>__<记录>_fld<字段>_<token>`       ← 附件级（旧批的图片单元）
#     ③ `media_<表>_<记录>`                            ← **另一套命名**（新批的图片单元；
#                                                        来自 L1 媒体目录名 `kb/l1/media/media_<表>_<记录>/`）
#   ② 早就被 `media_refs` 的父子声明归并掉了；**③ 没有任何人归并** ⇒
#     「同源」判据（`rmap[anchor] ∈ cited_res / case_resources`）在**媒体侧 ↔ 引用侧**之间
#     **永远为假**。实测（2026-10-08，床照那张图）：修好 L2 字段、开完 L3 的门、发完号、
#     L4 canonical 已含该记录，**覆盖判据仍然 `covered=false`** —— 卡的就是这一条。
#   ⇒ 归一只做**父记录级**的对齐：把 ②③ 都写成 ① 的形状。**不动任何门限、不动任何判据分支。**
_MEDIA_PREFIX_RE = re.compile(r"^media_([A-Za-z0-9]+)_(recv[A-Za-z0-9]+)$")
_ATTACH_SUFFIX_RE = re.compile(r"^(bitable__[A-Za-z0-9]+__recv[A-Za-z0-9]+)_fld[A-Za-z0-9]+_.+$")


def canon_resource(rid):
    """把同一父记录的三种 `resource_id` 写法归一到记录级（②③ → ①）。

    认不出的写法**原样返回**（保守一侧：宁可不同源，也不许把两条不同记录并成一条）。
    """
    s = str(rid or "").strip()
    if not s:
        return s
    m = _MEDIA_PREFIX_RE.match(s)
    if m:
        return "bitable__%s__%s" % (m.group(1), m.group(2))
    m = _ATTACH_SUFFIX_RE.match(s)
    if m:
        return m.group(1)
    return s


def coverage_judge(unit_rows, cited, cited_res, cov_thr, has_safe_hits=False,
                   resources_of=None, case_anchors=None, case_resources=None):
    """**覆盖判据的纯函数版**（2026-10-08 抽出）—— 返回 `(covered_by, detail)`。

    ★ 为什么抽出来：判定逻辑内联在 `review()` 里时，**只能靠「真跑一遍整链」来测** ——
      那种测法既慢、又碰运气（要正好有素材能触发某条分支）。抽成纯函数之后，
      三条分支（安全词 / 直接命中 / 同源命中）与**反向对照**都能离线喂样本判。

    `covered_by` 取值（**分开报，不许糊成一句**）：
      `"safe_vocabulary"` 命中允许表述（安全词）规则
      `"rule"`            命中一条**被规则引用**的单元（且过覆盖门限）
      `"same_source"`     命中的单元**与被引锚点同源**（`resource_id` 相同）← 2026-10-08 · B
      `""`                三者都没有 ⇒ 不覆盖（调用方按「无命中不等于合规」拒答）
    """
    resources_of = resources_of or resources_of_anchors
    case_anchors, case_resources = case_anchors or set(), case_resources or set()
    # ★★ 2026-10-08（第三批）：**比之前先把两边归一到同一种写法**（见 `canon_resource`）。
    #   为什么非做不可：命中侧（媒体单元）与新批引用侧的 resource_id 写法不同，
    #   直接比 `in` **永远为假** —— 判据会在「库明明认识这个题材」时静默判成没覆盖。
    #   **只归写法，不动门限、不动任何分支。**
    cited_res = {canon_resource(x) for x in cited_res}
    case_resources = {canon_resource(x) for x in case_resources}
    direct = [r for r in unit_rows
              if r.get("anchor") in cited and (r.get("raw_bm25") or 0) >= cov_thr]
    strong = [r for r in unit_rows if (r.get("raw_bm25") or 0) >= cov_thr]
    rmap = resources_of([r.get("anchor") for r in strong]) if strong else {}
    same = []
    if not direct and cited_res and rmap:
        same = [r for r in strong
                if rmap.get(r["anchor"]) and rmap[r["anchor"]] in cited_res]
    # ── ★★ A 第四路：**命中 L4 定稿的「反例 / 禁区」案例**（2026-10-08，Owner 批准 A）──
    #   原判据只认「被规则引用的单元」⇒ 库里 358 条带条款号的案例（181 反例）**一条都进不了池**。
    #   这里把案例当作**独立的一路依据**加进来，**不动前三路的任何判据与门限**。
    case = []
    if not (direct or same) and (case_anchors or case_resources):
        case = [r for r in strong
                if r["anchor"] in case_anchors
                or (rmap.get(r["anchor"]) and rmap[r["anchor"]] in case_resources)]
    detail = {"rule_cited_unit_hits": direct, "same_source_unit_hits": same,
              "case_unit_hits": case, "hit_resource_map": rmap}
    if has_safe_hits:
        return "safe_vocabulary", detail
    if direct:
        return "rule", detail
    if same:
        return "same_source", detail
    if case:
        return "case", detail
    return "", detail


# ══════════════════════════════════════════════════════════════════════════
# 案例层「题材一致性」闸门（2026-10-14 加）—— **实现在独立模块里**
# ══════════════════════════════════════════════════════════════════════════
# 病灶与判据见 `kb/l7/review-engine/core/case_theme.py` 的文件头（那里是单一真源）。
# 为什么不在本文件内联：**本脚本 import 时就会把整条引擎跑起来**（模块级解析 sys.argv
# 并执行）⇒ 内联逻辑**测不了**；抽成可导入模块后，`kb/l8/check_case_thematic_gate.py`
# 才能拿两份**真素材**做反向对照。一份实现，两边共用 —— 测试测的是真东西，不是副本。
def _load_case_theme():
    import importlib.util as _ilu
    _p = os.path.join(ROOT, "kb", "l7", "review-engine", "core", "case_theme.py")
    _spec = _ilu.spec_from_file_location("case_theme", _p)
    _m = _ilu.module_from_spec(_spec)
    _spec.loader.exec_module(_m)
    return _m


_ct = _load_case_theme()
case_subject_terms = _ct.case_subject_terms
case_thematic_ok = _ct.case_thematic_ok


def load_case_clauses():
    """L4 定稿的**「反例 / 禁区」条款** —— 覆盖池里原先**完全没有**它们（2026-10-08 · A）。

    ## 病灶（实测，2026-10-08）

    `kb/l4/canonical/sample_case.jsonl` 有 **358 条、全部带条款号**（如 `S-1.99`）、
    `status=stable`、`valid_until=2027-03-28`、`semantics=禁区：不能这么做 + 为什么` ——
    **是定稿条款**。但它们**不在** `kb/l3/candidates/rules.jsonl` 里（L3 把 `unit_type=sample`
    的单元蒸成「案例」而不是「规则」）⇒ 覆盖判据的池子（只从 rules 建）**看不见它们**
    ⇒ 命中它们的素材永远落「覆盖缺口」。实测：**358 个案例锚点，被 L3 规则引用的 0 个**。

    ## 两条**收窄**（只收该收的，不许放宽）

      · 只收 `polarity=反例` —— 正例（20 条）与 `unknown`（157 条）**不收**：
        「反例」才等于「库明确说不能这么做」，正例不是依据；
      · `reason_category` 为空或 `unknown` ⇒ **不收**（实测 181 条反例里 **57 条**是 `unknown`）——
        拿「连分类都没定」的条目当依据，就是编。
      ⇒ 实测可收 **124 条**（181 − 57）。

    ## 为什么不把它们「蒸成规则」

    `建议`（advice）列**只有 46%（83/181）非空**，而规则的可判定形态是「命中表达 → 处理方式」——
    缺处理方式蒸不出规则（这也正是它们当年被做成「案例」的原因）。
    覆盖判据**不需要 advice**（它只问「库认不认识这个题材」），所以这一步是安全的；
    要真升级成规则，得先补那 98 条 advice —— 那是**数据层的活，另外报批**。
    """
    path = os.path.join(ROOT, "kb", "l4", "canonical", "sample_case.jsonl")
    out = []
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                try:
                    d = json.loads(line)
                except Exception:                              # noqa: BLE001
                    continue
                if d.get("polarity") != "反例":
                    continue
                rc = str(d.get("reason_category") or "").strip()
                if not rc or rc.lower() == "unknown":
                    continue
                if not d.get("anchor"):
                    continue
                # ── ★★ 已销号的条款**不许再当依据**（2026-10-14 加）─────────────────
                #   为什么非加不可：销号只写标记（`status=superseded` ＋ `superseded_by`），
                #   而本函数原先**不读 `status`** ⇒ 被销的号照样进池、照样被引用 ——
                #   而**被销那一侧的 anchor 是死的**（旧代 `#正面和负面样本/recvw2…`，
                #   实测 201 个 record **0 个**还在）⇒ 引擎会继续产出**点不开的直链**。
                #   换句话说：**不加这一条，销号在引擎侧等于没生效（只是化妆）。**
                #   边界：只挡「产出依据」这一路；覆盖池用的是**存活的孪生号**
                #   （实测 61 个被销号**全部**有孪生号在池子里 ⇒ 覆盖不受损）。
                if str(d.get("status") or "").strip().lower() == "superseded":
                    continue
                out.append(d)
    except OSError:
        return []                    # 读不到 ⇒ 空 ⇒ 覆盖判据退回原样（保守一侧，不静默放宽）
    return out


def layer_units(text, reg, top=5):
    import importlib.util
    spec = importlib.util.spec_from_file_location("l6_retriever", os.path.join(ROOT, "kb", "l6", "retriever.py"))
    RT = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(RT)
    l6 = json.load(open(L6REG, encoding="utf-8"))["retrieval_capability"]
    mode_l6 = l6["mode"]
    semantic = bool(l6["semantic_recall"])
    gate = reg["retrieval"]["gate"]
    bm = RT.BM25()
    raw = []
    for name, lst in bm.search(text).items():
        for did, sc, _ in lst[:top]:
            d = bm.docs[did]
            raw.append({"source": name, "unit_id": d["unit_id"], "anchor": d["anchor"],
                        "table": d["table"], "kb_type": d["kb_type"],
                        "source_sha256": d["source_sha256"], "raw_bm25": round(sc, 4),
                        "excerpt": d["text_excerpt"][:200]})
    raw.sort(key=lambda x: -x["raw_bm25"])
    raw = raw[:top]
    bm25_max = raw[0]["raw_bm25"] if raw else 0.0
    used_vector = False
    vec_rows = []
    if bm25_max < gate["bm25_raw_min"] and semantic:
        used_vector = True
        vec = RT.Vectors()
        for did, sc, extra in vec.search(text, top=top):
            d = bm.docs[did]
            vec_rows.append({"source": "vector", "unit_id": d["unit_id"], "anchor": d["anchor"],
                             "table": d["table"], "kb_type": d["kb_type"],
                             "source_sha256": d["source_sha256"], "cosine": round(sc, 4),
                             "segment_index": extra.get("segment_index"),
                             "char_offset": extra.get("char_offset"), "excerpt": d["text_excerpt"][:200]})
        vec_rows.sort(key=lambda x: -x["cosine"])
    cos_max = vec_rows[0]["cosine"] if vec_rows else 0.0
    adopted, discarded = [], []
    for row in raw:
        ok = row["raw_bm25"] >= gate["bm25_raw_min"]
        (adopted if ok else discarded).append(
            {**row, "verdict": "≥ 门限" if ok else "低于门限",
             "reason": "原始分过门限 → 可作参考/待规则层确认" if ok else
                       f"原始分 {row['raw_bm25']} < {gate['bm25_raw_min']}，只能标参考"})
    for row in vec_rows:
        ok = row["cosine"] >= gate["vector_cosine_min"]
        (adopted if ok else discarded).append(
            {**row, "verdict": "≥ 门限（向量）" if ok else "低于门限（向量）",
             "reason": "余弦过门限 → 可作参考/待规则层确认" if ok else
                       f"余弦 {row['cosine']} < {gate['vector_cosine_min']}，只能标参考"})
    return {"engine": "kb/l6/retriever.py", "l6_mode": mode_l6, "semantic_recall": semantic,
            "bm25_max": bm25_max, "cosine_max": cos_max,
            "used_vector": used_vector,
            "no_semantic_annotation": None if semantic else "无语义召回（L6 为 bm25_only，本次结论不含语义检索）",
            "top_bm25": raw, "vector_rows": vec_rows,
            "adopted": adopted, "discarded": discarded, "gate": gate}


# ---------------- 第 4 层：原文层 ----------------
def resolve_anchor(anchor, sha):
    """anchor: #表名/记录id/字段名 → 回 kb/l0/records 取逐字原文；找不到就返回 None（不猜）。"""
    if not anchor or not anchor.startswith("#"):
        return None
    parts = anchor[1:].split("/")
    if len(parts) < 3:
        return None
    table, rec, field = parts[0], parts[1], "/".join(parts[2:])
    base = os.path.join(ROOT, "kb", "l0", "records")
    cands = []
    if os.path.isdir(os.path.join(base, table)):
        cands.append(os.path.join(base, table, f"{rec}.json"))
    for d in sorted(os.listdir(base)) if os.path.isdir(base) else []:
        p = os.path.join(base, d, f"{rec}.json")
        if os.path.exists(p) and p not in cands:
            cands.append(p)
    for p in cands:
        try:
            recj = json.load(open(p, encoding="utf-8"))
        except Exception:
            continue
        f = (recj.get("fields") or {}).get(field)
        if f is None:
            continue
        val = f.get("value")
        if isinstance(val, (dict, list)):
            val = json.dumps(val, ensure_ascii=False)
        if val is None:
            continue
        return {"path": os.path.relpath(p, ROOT), "record_id": recj.get("record_id"),
                "source_table": recj.get("source_table"), "field": field,
                "verbatim": str(val), "raw_verbatim": str(f.get("raw_verbatim") or val),
                "observed_at": recj.get("observed_at"),
                # ★ 2026-10-08（Owner 批准 D）：**L0 飞书直链**。
                #   原先这里只回本地路径 ⇒ 评审链的依据里**一个可点的飞书链接都没有**
                #   （只有 P0 快路的报告有）。库规本来说的就是「要真核对只能点飞书直链」——
                #   那就必须把直链交出去。`entry_url` 是 L0 件自己的字段，**原样搬，不拼**。
                "entry_url": recj.get("entry_url")}
    return None


def _l0_entry_url(anchor):
    """从一个锚点取 **L0 飞书直链** —— **不要求那件 L0 里有字段值**（2026-10-08 · C/D）。

    ## 为什么必须是单独一个函数

    `resolve_anchor()` 的取数口径是「L0 件里必须有 `fields.<字段>` 才算数」。而实测有**一整类**
    L0 件**只有元数据、没有 `fields`**（负面样本表 201 件，见 `kb/l0/2_内部正负样本库/`）
    ⇒ 那类锚点它**必然**返回 None。但那些件**自己有 `entry_url`** ——
    而库规对这类件的原话就是：「要真核对只能点飞书直链」。
    ⇒ 「取不到逐字原文」与「没有直链」是**两件事**，这里只管后者。

    ## 判据（不猜）

    锚点第二段必须**形如记录 id**（`rec` 开头且够长）才去搜；否则返回 None
    （实测 13,095 条单元里 4,788 条锚点只有一段，如 `#l.1-0`、`#h.文案信息层级` —— 那些没有记录可指）。
    搜索**有界**：只试两种已知落点（`kb/l0/records/*/<rec>.json` 与 `kb/l0/<分组>/*<rec>*.json`），
    不做全库递归 —— 这个函数只服务「依据要带直链」，不值得为它走 3,786 个文件。
    """
    parts = (anchor or "").lstrip("#").split("/")
    if len(parts) < 2:
        return None
    rec = parts[1]
    if not rec.startswith("rec") or len(rec) < 10:
        return None                      # 不是记录 id ⇒ 不猜（宁缺不编）
    import glob as _glob
    cands = _glob.glob(os.path.join(ROOT, "kb", "l0", "records", "*", rec + ".json"))
    cands += _glob.glob(os.path.join(ROOT, "kb", "l0", "*", "*" + rec + "*.json"))
    for p in cands:
        if "_archive" in p:
            continue
        try:
            d = json.load(open(p, encoding="utf-8"))
        except Exception:                                      # noqa: BLE001
            continue
        if d.get("entry_url"):
            return d["entry_url"]
    return None


def best_span(verbatim, excerpt, maxlen=60):
    """在原文里取一段仍属逐字的片段（含命中词，两端按标点/空白收边），便于人核对。"""
    v = verbatim or ""
    i = v.casefold().find((excerpt or "").casefold())
    if i < 0:
        return excerpt
    lo = max(0, i - maxlen // 2)
    hi = min(len(v), i + len(excerpt) + maxlen // 2)
    found = False
    for sep in ("。", "\n", "；", ";", "|", "，"):
        j = v.rfind(sep, lo, i)
        if j >= 0:
            lo = j + len(sep)
            found = True
            break
    if not found and lo > 0:
        # 窗口内没有分隔符时，改到**全串范围内最近的分隔符**（含空格）再收边。
        # 否则会从词中间截断 —— 实测把「H02:increase…」切成「02:increase…」，读起来像另一个词。
        for sep in ("。", "\n", "；", ";", "|", "，", " "):
            j = v.rfind(sep, 0, i)
            if j >= 0:
                lo = j + len(sep)
                break
        else:
            lo = 0
    for sep in ("。", "\n", "；", ";", "|"):
        j = v.find(sep, i + len(excerpt), hi)
        if j >= 0:
            hi = j + len(sep)
            break
    span = v[lo:hi].strip()
    # 收边后仍然过长（说明一路没有分隔符）就退回原窗口，避免输出一大段
    limit = len(excerpt) + maxlen * 2
    return span if len(span) <= limit else v[max(0, i - maxlen // 2):hi].strip()


def resolve_excerpt(rule, excerpt, preferred=None):
    """在规则的证据单元里找「原文逐字含该摘录」的那个锚点。
    规则会把很多来源记录的片段汇总在一起，规则自己的 anchor（= 第一个证据单元）不一定含这段，
    所以必须逐个证据单元找，找到才引用；一个都找不到就返回 None（该结论按硬闸门不输出）。"""
    cands = []
    if preferred:
        cands.append({"anchor": preferred, "source_sha256": None})
    for u in rule.get("evidence_units") or []:
        cands.append({"anchor": u.get("anchor"), "source_sha256": u.get("source_sha256")})
    cands.append({"anchor": rule.get("anchor"), "source_sha256": None})
    # 按「字段是否在记录违规」稳定排序：命中片段/检测关键词 优先于 修改建议。
    # 稳定排序保证同优先级内仍按原顺序（preferred → evidence_units → rule.anchor）。
    cands = sorted(cands, key=lambda c: _anchor_field_rank(c.get("anchor")))
    seen = set()
    for c in cands:
        a = c.get("anchor")
        if not a or a in seen:
            continue
        seen.add(a)
        src = resolve_anchor(a, c.get("source_sha256"))
        if src and verify_excerpt(src["verbatim"], excerpt):
            return {**src, "anchor": a, "source_sha256": c.get("source_sha256") or
                    next((u.get("source_sha256") for u in (rule.get("evidence_units") or [])
                          if u.get("anchor") == a), None)}
    return None


def verify_excerpt(verbatim, excerpt):
    """摘录必须能在原文里逐字找到（NFKC + 空白折叠后比对，不做任何改写）。"""
    v, e = norm(verbatim), norm(excerpt)
    return bool(e) and e in v


# ---------------- 出处字段优先级（让摘录落在「记录违规」的字段上）----------------
#
# 为什么需要：同一个记录有多个字段，`命中片段` 是「记录了哪个词违规」，
# `修改建议` 是「怎么改」。若优先解析到 `修改建议`，摘录就会取到改法文本的中间一段，
# 输出成「否则删除（折扣百分比不在此列） ▸ 删除 pain-free/…」这种读不懂的碎片。
# 所以按「是否在记录该违规」给字段排优先级。
_DOC_FIELDS = ("命中片段", "检测关键词", "边界内容", "风险原句示例", "禁用表达", "触发词", "原文逐字")
_ADVICE_FIELDS = ("修改建议", "修订位置", "修改意见", "建议")


def _anchor_field_rank(anchor):
    """字段优先级：0 = 记录违规的字段（首选），2 = 改法类字段（次选），1 = 其余。"""
    tail = (anchor or "").rsplit("/", 1)[-1]
    if any(f in tail for f in _DOC_FIELDS):
        return 0
    if any(f in tail for f in _ADVICE_FIELDS):
        return 2
    return 1


# ---------------- 建议：同源检查 ----------------
#
# 为什么要专门做这一步：l3 的 `suggested_replacement` 是**按记录**汇总的字段，一条记录
# 可能同时命中多个规则码，于是这个字段会是「A 规则的改法 ▸ B 规则的改法」这种拼接串
# （实测 W-1.53 的该字段长 2064 字符）。直接截前 300 字符输出，就会出现「给德语词
# schmerzfrei（H07 疼痛功效）的替换建议，开头却是 M03 效果数据的话」——错配在上游数据里，
# 但用户看到的是本 skill 的输出，所以在本层必须拦掉：**对不上就不输出**。

def _rule_lexicon(rule):
    """本规则自己的禁用片段词表（用来判断一段建议是不是在说本规则）。"""
    toks = set()
    for seg in re.split(r"[；;]", rule.get("forbidden_expression") or ""):
        for t in re.split(r"[,，]", seg):
            t = norm(t)
            if len(t) >= 3:
                toks.add(t)
    return toks


def rule_allowance(rule):
    """从规则原文里取「豁免 / 边界允许」表述 —— 规则级、天然同源，不会被别的规则码污染。"""
    rt = rule.get("rule_text") or ""
    m = re.search(r"豁免[：:]\s*([^；;\n]+)", rt)
    if m:
        return m.group(1).strip()
    m = re.search(r"边界允许[：:]\s*([^；;）)\n]+)", rt)
    if m:
        return m.group(1).strip()
    return ""


def same_source_advice(rule, matched_term):
    """给命中片段配**同源**替换建议；对不上就不输出（宁可只给豁免词）。

    来源① 规则原文的豁免/允许表达 —— 与规则同源，最干净。
    来源② `expression_fix_pairs` 里 fragment 与命中片段一致的条目；其 `fix` 是「 ▸ 」
          拼接串，按「 ▸ 」切句后**只保留提到本规则禁用片段的句子**，属于别的规则码的
          句子直接丢弃 —— 这就是「替换文本与片段同源」检查。

    返回 (建议文本, 同源检查说明)。两条来源都拿不到时，建议为空串并说明原因。
    """
    parts, notes, seen_parts = [], [], set()

    def _add(txt):
        key = norm(txt)
        if key and key not in seen_parts:      # 同一句改法会在多组配对里重复出现，去重
            seen_parts.add(key)
            parts.append(txt)

    allow = rule_allowance(rule)
    if allow:
        _add(f"可改为（本规则豁免表达）：{allow}")

    want = norm(matched_term)
    lex = _rule_lexicon(rule)
    pair_hit = kept_total = dropped_total = 0
    for pair in rule.get("expression_fix_pairs") or []:
        frag = norm(pair.get("fragment"))
        if not frag or not (frag == want or want in frag or frag in want):
            continue
        pair_hit += 1
        clauses = [c.strip() for c in (pair.get("fix") or "").split("▸") if c.strip()]
        kept = [c for c in clauses
                if want in norm(c) or any(t in norm(c) for t in lex)]
        kept_total += len(kept)
        dropped_total += len(clauses) - len(kept)
        for c in kept:
            _add(f"记录级改法：{c}")

    if pair_hit:
        notes.append(f"同源检查：{pair_hit} 组配对命中，保留 {kept_total} 句、"
                     f"丢弃 {dropped_total} 句（属其他规则码）"
                     + ("，去重后建议 %d 条" % len(parts) if parts else "，无同源建议可输出"))
    elif allow:
        notes.append("同源检查：无配对命中，建议全部来自规则原文豁免表达")
    if not parts:
        return "", ("；".join(notes) if notes
                    else "同源检查：既无本规则豁免表达，也无同源配对 → 不给建议")
    return " ｜ ".join(parts), "；".join(notes)


# ---------------- 汇编 ----------------
def review(text, content_type="text", position="全文", report_dir=None, run_id=None, top=5):
    # run_id 必须逐次唯一：以前默认写死 "20260923-1500"，每跑一次就覆盖上一次的报告
    # （实测把自测报告 20260923-1500.review.md 覆盖掉了）。默认取当前时间戳。
    run_id = run_id or time.strftime("%Y%m%d-%H%M%S")
    reg = load_registry()
    rules = load_rules()
    vocab = reg["vocabulary"]
    trace = {}
    t_all = time.perf_counter()
    # ★ 2026-10-10（任务拆解 目标 15/17/19 · PRD §12）：**逐段计时埋点**。
    #   为什么要埋：PRD §12 要「单条文字 ≤10s / 图片 ≤20s / 视频 ≤60s」「报告生成 ≤30s」，
    #   而在此之前**引擎一处计时都没有** —— 没有尺子就谈不了优化（本库 baseline_table 立项时
    #   那句「病根不是算错，是没有尺子就开始量」是同一类问题）。
    #   口径：本对象**只记时间，不参与任何判定**（三态、条款号、分数一个字都不看它）。
    _perf = {}
    _t = time.perf_counter()
    trace["p0"] = layer_p0(text)
    _perf["p0_match_ms"] = round((time.perf_counter() - _t) * 1000, 1)
    _t = time.perf_counter()
    trace["rules"] = layer_rules(text, rules)
    _perf["rule_layer_ms"] = round((time.perf_counter() - _t) * 1000, 1)
    _t = time.perf_counter()
    trace["units"] = layer_units(text, reg, top=top)
    _perf["unit_layer_ms"] = round((time.perf_counter() - _t) * 1000, 1)
    _assemble_t = time.perf_counter()

    findings, unmet = [], []
    p0_rule_ids = set()
    for h in trace["p0"]["hits"]:
        rid = h["rule_id"]
        p0_rule_ids.add(rid)
        r = rules.get(rid, {})
        (cat, sub), basis = classify(r, vocab)
        excerpt = (h["matched"][0]["pattern"] if h.get("matched") else r.get("forbidden_expression") or "")
        src = resolve_excerpt(r, excerpt, preferred=h.get("anchor"))
        if not src:
            # ── 反静默丢（2026-09-30 修，实测漏放；fail-closed，见本文件顶部口径）────────
            # 旧行为：P0 命中、但摘录在该规则证据单元里找不到逐字原文 → 塞进 unmet 后 `continue`，
            # findings 里不留任何痕。而裁决只看 findings（:652 起）→ 这条 P0 **消失**，state 落到 PASS。
            #
            # 实测复现（改动前）：
            #   文本「Momcozy 吸奶器，绝对安全，妈妈放心。」
            #   kb/l5/matcher.py      → BLOCK（H05 命中「绝对安全」）
            #   kb-content-review     → PASS，issue_count=0   ← 红线被静默吞掉
            # 根因：H05 的「绝对安全」是 safest 的**等价说法**（p0_patterns 的
            # variant_sources.synonym_family，basis=equivalent_of:safest），L2/L0 源侧本就没有
            # 这句逐字原文 —— 于是「引用契约」（依据须逐字可回源）这条硬闸门，
            # 把「P0 命中即 BLOCK」那条硬闸门给否掉了。
            #
            # 两条硬闸门撞车时的裁决口径：**红线不得因依据不能逐字回源而降级为消失。**
            # 命中是确定性的（matcher 实跑，非模型推断），故这里照旧输出，但把不确定性标到明面上：
            #   · 出处退到 **P0 模式自己声明**的 anchor / source_sha256
            #     （p0_patterns.jsonl 的真字段，不是编的）；
            #   · 显式 `verbatim_verified=False` + `evidence_gap`，并把同一句话写进 `reason`
            #     —— reason 是下游 API（/review）会透出的那一栏，保证消费方看得到；
            #   · `unmet` 照记（可追溯），但加 `disposition`，说明它**没有**被丢掉。
            unmet.append({"source": "P0", "rule_id": rid, "article_no": r.get("article_no"),
                          "anchor": r.get("anchor"), "excerpt": excerpt[:80],
                          "disposition": "output_as_block_with_gap",
                          "why": "该规则全部证据单元里都找不到这段摘录的逐字原文"
                                 "（等价说法／正则命中）；已按 P0 输出为 BLOCK，出处退到 P0 模式自身"})
            m0 = (h.get("matched") or [{}])[0]
            findings.append({
                "severity": "BLOCK", "layer": "P0 确定性匹配（依据不可逐字回源）",
                # ★ 2026-10-10：P0 确定性命中**显式带 p_level="P0"** ——
                #   它是 L5「P0 命中即 BLOCK」那一条的产物，本层自己就知道它是 P0。
                #   不带的话会掉进分级的兜底路，只能从层文案里猜（能猜对，但那是猜）。
                "p_level": "P0",

                "category": cat, "sub": sub, "position": position,
                "excerpt": excerpt, "matched_term": excerpt,
                "verbatim_verified": False,
                "anchor": h.get("anchor") or r.get("anchor"),
                "source_sha256": h.get("source_sha256"),
                # ★★ 2026-10-09（第八批续）：**这一条分支也补上 L0 飞书直链**。
                #   病灶（实测，同批排查 P0 文案时抓到）：5 处 `findings.append` 里
                #   只有这一处**既没有 `l0_entry_url`、`verbatim_source` 也是 `None`**
                #   ⇒ 卡片「依据」行**一个链接都没有**，与另四处不一致。
                #   实测样本：「经 FDA 批准，完全无痛，模拟婴儿吸吮，全网销量第一」判出 5 条，
                #   `W-1.1`（H09 模式）是唯一没有直链的那条；而它的锚点
                #   `#广告文案明细/recvuJYdOb61lT/命中片段` **经 `_l0_entry_url` 是取得到的**
                #   （→ `…&record=recvuJYdOb61lT`）—— 即「**取得到却没去取**」，不是「取不到」。
                #   注意本分支 `verbatim_verified=False`（依据不可逐字回源）与
                #   「有没有直链」是**两件事**：前者说摘录回验不了，后者说源记录在哪。
                #   判据与另三处**同一个函数**，不新造第二把尺子；取不到仍留 `None`（**不编**）。
                "l0_entry_url": _l0_entry_url(h.get("anchor") or r.get("anchor")),
                "article_no": r.get("article_no"), "rule_id": rid, "rule_code": r.get("rule_code"),
                "pattern_id": h.get("pattern_id"), "match_kind": m0.get("kind"),
                "kb_type": r.get("kb_type"),
                "library": reg["citation_contract"]["libraries"].get(
                    r.get("kb_type") or "unknown", {}).get("label", "未归类（不猜）"),
                "evidence_gap": "「%s」在该规则证据单元里无逐字原文（%s 命中）；本条目出处为 "
                                "L5 P0 模式 %s 自身声明的 anchor / source_sha256，**未经逐字回验**"
                                % (excerpt, m0.get("kind") or "模式", h.get("pattern_id") or ""),
                "reason": f"P0 确定性命中（{h.get('match_note')}）：「{excerpt}」命中规则码 "
                          f"{r.get('rule_code') or rid}。{r.get('reason') or '（来源未给判定理由）'}"
                          f"【依据不可逐字回源：该说法为等价说法／正则命中，源侧无逐字原文；"
                          f"按 L5「P0 命中即 BLOCK」输出，出处为 P0 模式自身，需人工确认】",
                "advice": None,
                "advice_note": "依据不可逐字回源，按硬闸门不给改法建议",
                "fact_or_inference": "事实", "confidence": "中",
                "verbatim_source": None,
                "classification_basis": basis,
            })
            continue
        advice, advice_note = same_source_advice(r, excerpt)
        findings.append({
            "severity": "BLOCK", "layer": "P0 确定性匹配", "category": cat, "sub": sub,
            # ★ 2026-10-10：P0 确定性命中**显式带 p_level="P0"** ——
            #   它是 L5「P0 命中即 BLOCK」那一条的产物，本层自己就知道它是 P0。
            #   不带的话会掉进分级的兜底路，只能从层文案里猜（能猜对，但那是猜）。
            "p_level": "P0",

            "position": position, "excerpt": best_span(src["verbatim"], excerpt), "matched_term": excerpt,
            "anchor": src["anchor"], "source_sha256": src.get("source_sha256"),
            "article_no": r.get("article_no"), "rule_id": rid, "rule_code": r.get("rule_code"),
            "kb_type": r.get("kb_type"), "library": reg["citation_contract"]["libraries"].get(
                r.get("kb_type") or "unknown", {}).get("label", "未归类（不猜）"),
            "reason": f"P0 规则命中（{h['match_note']}）：{r.get('reason') or '（来源未给判定理由）'}",
            "advice": advice or None,
            "advice_note": advice_note,
            "fact_or_inference": "事实", "confidence": "高",
            "verbatim_source": {"path": src["path"], "field": src["field"],
                                 # ★ D（2026-10-08）：L0 飞书直链一并带出去（库规：「要真核对只能点飞书直链」）
                                 "entry_url": src.get("entry_url")},
            "classification_basis": basis,
        })

    for h in trace["rules"]["hits"]:
        if h["rule_id"] in p0_rule_ids:
            continue                                     # P0 已覆盖，不重复计
        r = rules[h["rule_id"]]
        (cat, sub), basis = classify(r, vocab)
        if cat == "表述与术语准确性" and sub == "允许表述（安全词）":
            continue                                     # 允许表述命中不算问题
        excerpt = h["matched_fragments"][0]
        src = resolve_excerpt(r, excerpt, preferred=h.get("anchor"))
        if not src:
            # ★★ 2026-10-08（Owner 批准 C）：**取不到逐字原文，不许把这条命中丢掉。**
            #
            # 沿用本文件里 P0 那条**既有裁定**（上面那段注释的原话）：
            #   「两条硬闸门撞车时的裁决口径：**红线不得因依据不能逐字回源而降级为消失。**」
            # 改前这里是一句 `continue` —— 命中被丢进 unmet、**findings 里什么都不留**。
            #
            # 实测成因（2026-10-08 量到的，不是推测）：**L0 落点分裂** ——
            #   `kb/l0/records/负面样本/` 那 170 件有 `fields`（能回源）；
            #   而 `kb/l0/2_内部正负样本库/feishu_bitable_record__*.json` 那 **201 件只有元数据、没有 `fields`**,
            #   两批记录 id **交集为 0**。负面样本表正是「反例/禁区」的唯一来源
            #   ⇒ 旧行为让**这一整类依据消失**（受影响的锚点 556 条：`素材` 355 + `正面和负面样本` 201）。
            #
            # 处置（**与可解析时同一把尺子，不升不降**）：照出结论，出处退到
            #   「条款号 + 规则锚点 + source_sha256 + **L0 飞书直链**」，显式标 `verbatim_verified=False`。
            #   `unmet` 照记（可追溯），并加 `disposition` 说明它**没有被丢掉**。
            sev, sev_basis = _severity_of(h.get("p_level"), h.get("risk_level"))
            adv, adv_note = same_source_advice(r, excerpt) if sev == "BLOCK" else ("", "")
            findings.append({
                "severity": sev, "layer": "规则层（依据不可逐字回源）",
            # ★ 2026-10-10：把原始层级带给下游分级（走 p_level 主路，不看层文案）
            "p_level": h.get("p_level"), "risk_level": h.get("risk_level"),
                "category": cat, "sub": sub, "position": position,
                "excerpt": excerpt, "matched_term": excerpt,
                "verbatim_verified": False,
                "anchor": h.get("anchor") or r.get("anchor"),
                "source_sha256": (r.get("evidence_units") or [{}])[0].get("source_sha256"),
                "l0_entry_url": _l0_entry_url(h.get("anchor") or r.get("anchor")),
                "article_no": r.get("article_no"), "rule_id": h.get("rule_id"),
                "rule_code": h.get("rule_code"), "kb_type": r.get("kb_type"),
                "library": reg["citation_contract"]["libraries"].get(
                    r.get("kb_type") or "unknown", {}).get("label", "未归类（不猜）"),
                "evidence_gap": "命中是确定性的（规则 `forbidden_expression` 逐字命中），但该锚点的 L0 件"
                                "**本地没有字段值**（负面样本表有一批 L0 件只有元数据）⇒ 摘录无法在本地逐字回验；"
                                "出处退到规则锚点 + source_sha256 + L0 直链，**需人工点开核对**",
                "reason": f"逐字命中「{excerpt}」（规则码 {h.get('rule_code') or h.get('rule_id')}）："
                          f"{r.get('reason') or '（来源未给判定理由）'}"
                          f"【依据不可逐字回源：该锚点的 L0 件本地无字段值；"
                          f"按「红线不得因依据不能逐字回源而降级为消失」输出，需人工确认】",
                "advice": adv or None, "advice_note": adv_note,
                "fact_or_inference": "事实", "confidence": "中",
                "verbatim_source": None, "classification_basis": basis,
            })
            unmet.append({"source": "规则层", "rule_id": h["rule_id"], "article_no": h.get("article_no"),
                          "anchor": h.get("anchor"), "excerpt": excerpt[:80],
                          "disposition": "output_as_finding_with_gap",
                          "why": "该规则全部证据单元里都找不到这段摘录的逐字原文"
                                 "（L0 件本地无字段值）；**已按规则层输出**，出处退到锚点 + L0 直链"})
            continue
        sev, sev_basis = _severity_of(h.get("p_level"), h.get("risk_level"))
        advice, advice_note = same_source_advice(r, excerpt) if sev == "BLOCK" else ("", "")
        findings.append({
            "severity": sev, "layer": "规则层", "category": cat, "sub": sub,
            # ★ 2026-10-10：同上 —— 规则层主路径也必须带 p_level，否则它会掉进兜底
            "p_level": h.get("p_level"), "risk_level": h.get("risk_level"),
            "position": position, "excerpt": best_span(src["verbatim"], excerpt), "matched_term": excerpt,
            "anchor": src["anchor"], "source_sha256": src.get("source_sha256"), "article_no": r.get("article_no"),
            # ★★ 2026-10-08（第八批）：**规则层也要带 L0 飞书直链**。
            #   病灶（Owner 报「图片有链接了、文案还是没有」）：本分支（`layer="规则层"`，
            #   规则 `forbidden_expression` 逐字命中的**主路径**）只给了 `anchor`，
            #   **没给 `l0_entry_url`** —— 而同一文件的**案例层**（`layer="案例层…"`）
            #   和另一个规则分支（「依据不可逐字回源」那条）**都给了**。
            #   ⇒ 包装层拼 `evidence` 时那一格是空的 ⇒ 卡片上的「依据」行没有「原始出处」
            #     ⇒ 读者回不到飞书源记录（库规：「不给直链等于没法定回去」）。
            #   判据与另两处**同一个函数**（`_l0_entry_url`），不新造第二把尺子：
            #   取不到就留 None（**不编**），卡片那一段自然不出现。
            "l0_entry_url": _l0_entry_url(src["anchor"]),
            "rule_id": h.get("rule_id"), "rule_code": h.get("rule_code"), "kb_type": r.get("kb_type"),
            "library": reg["citation_contract"]["libraries"].get(r.get("kb_type") or "unknown", {}).get("label"),
            # ── ★★ 批次19 · 第2块：**直取改 `.get()`**（用户明令「不许漏」的那条）─────────
            # 病灶（实测）：这四处原为 `h['p_level'] / h['risk_level'] / h['authority'] /
            #   h['authority_source_table']` **直取**。对「键存在但值为 None」**仍安全**，
            #   但 **`clause` 形态这 5 个键本身不存在**（见 ledger-read-contract.yaml →
            #   `clause_form_fields_have_no_source`：`authority / rule_kind / p_level_basis /
            #   authority_source_table / risk_evidence_records` 在 clause 形态**无源、留空**）
            #   ⇒ 一旦 clause 行走进本分支即 **KeyError**，整条评审崩掉。
            # 修法：四处改 `.get()`，**判定语义不变** ——
            #   `h.get('p_level') == "P0"` 对「键不存在」得 False，与原意（不是 P0 就不 BLOCK）一致；
            #   `h.get('authority') == "expert"` 同理。**这是补健壮性，不是放松判据。**
            # 取值语义（`clause_form_fields_have_no_source` 的裁定）：**留空 ≠ 缺失** ——
            #   消费方必须容忍空值；空值是「未定义」，不是「否定」。
            "reason": f"逐字命中「{excerpt}」：{r.get('reason') or '（来源未给判定理由）'}"
                      f"（p_level={h.get('p_level')} risk_level={h.get('risk_level')} "
                      f"authority={h.get('authority')}，"
                      f"来源表 {h.get('authority_source_table')}）",
            "advice": advice or None,
            "advice_note": advice_note,
            "fact_or_inference": "事实",
            "confidence": "高" if h.get("authority") == "expert" else "中",
            "verbatim_source": {"path": src["path"], "field": src["field"],
                                 # ★ D（2026-10-08）：L0 飞书直链一并带出去（库规：「要真核对只能点飞书直链」）
                                 "entry_url": src.get("entry_url")},
            "classification_basis": basis,
        })

    # 去重：同一处文案命中多条同义规则（L3 的修订对规则常有大量近义条目）时合并为一条，
    # 保留严重度最高的一条，并把被合并的条款号记进 merged_articles（可追溯，不静默丢）
    order = {"BLOCK": 0, "REVIEW": 1}
    findings.sort(key=lambda f: (order.get(f["severity"], 9), f["category"], f["sub"]))
    by_key, merged = {}, {}
    for f in findings:
        k = (f["category"], f["sub"], norm(f.get("matched_term") or f["excerpt"]))
        if k in by_key:
            merged.setdefault(id(by_key[k]), []).append(f["article_no"])
            if f.get("advice") and not by_key[k].get("advice"):
                by_key[k]["advice"] = f["advice"]
            continue
        by_key[k] = f
    findings = list(by_key.values())
    for f in findings:
        m = merged.get(id(f))
        if m:
            f["merged_articles"] = sorted(set(m))

    # 覆盖信号：内容主题是否落在知识库管辖范围内（决定「无问题」是 PASS 还是拒答）
    cited = rule_cited_anchors(rules)
    cited_res = rule_cited_resources(rules)          # ★ B：被引锚点的**源素材**（一键多源已保守跳过）
    gate_thr = reg["retrieval"]["gate"]["bm25_raw_min"]
    safe_hits = [h for h in trace["rules"]["hits"]
                 if (vocab["code_map"].get((h.get("rule_code") or "").strip()) or [None, None])[1]
                 == "允许表述（安全词）"]
    cov_thr = reg["retrieval"]["gate"].get("coverage_bm25_min", gate_thr)
    # ── ★★ B「同源归并」（2026-10-08，Owner 批准）────────────────────────────
    # 病灶：判据原来看的是「**命中单元**的锚点 ∈ 被引锚点池」。而同一件素材在 L2 有**多个锚点**
    #   （`#…/原文反馈` 被引用、`#素材/…/图片素材/#img.1` 是图上文字、检索命中的是后者）
    #   ⇒ 同源不同 unit ⇒ 永远匹配不上 ⇒ 图片/视频单**必然**落覆盖缺口。
    # 改法：命中的单元与被引锚点**同 `resource_id`** 也算覆盖（判据按**素材**，不按**单元**）。
    # 收窄：只在「直接命中没有」时才去查（省掉 35MB 扫描）；`cited_res` 为空则不查；
    #   锚点取不到 resource_id ⇒ 不认（保守一侧）。**比原来只松「同源」这一条，不松门限。**
    case_clauses = load_case_clauses()          # ★ A：L4 定稿的「反例/禁区」（收窄后实测 124 条）
    covered_by, _cov_detail = coverage_judge(
        trace["units"]["top_bm25"], cited, cited_res, cov_thr,
        has_safe_hits=bool(safe_hits),
        case_anchors={c["anchor"] for c in case_clauses},
        case_resources={c.get("resource_id") for c in case_clauses if c.get("resource_id")})
    trace["coverage"] = {
        "safe_vocabulary_hits": [h["article_no"] for h in safe_hits][:5],
        "rule_cited_unit_hits": [{"anchor": r["anchor"], "raw_bm25": r["raw_bm25"]}
                                 for r in _cov_detail["rule_cited_unit_hits"]][:5],
        "same_source_unit_hits": [{"anchor": r["anchor"], "raw_bm25": r["raw_bm25"],
                                   "resource_id": _cov_detail["hit_resource_map"].get(r["anchor"])}
                                  for r in _cov_detail["same_source_unit_hits"]][:5],
        "case_unit_hits": [{"anchor": r["anchor"], "raw_bm25": r["raw_bm25"],
                            "resource_id": _cov_detail["hit_resource_map"].get(r["anchor"])}
                           for r in _cov_detail["case_unit_hits"]][:5],
        "case_clause_pool": len(case_clauses),
        "rule_cited_anchor_pool": len(cited), "rule_cited_resource_pool": len(cited_res),
        "coverage_bm25_min": cov_thr, "covered_by": covered_by,
        "why": "PASS 必须建立在「知识库认识这个主题」之上：① 命中允许表述（安全词）规则；"
               f"② 单元层 Top3 里有一条既被规则引用、BM25 原始分又 ≥ {cov_thr}（{gate_thr} 的 2 倍）；"
               "②b 该单元**与被引锚点同源**（父记录 `resource_id` 相同）也算 —— 同一素材的图上文字与"
               "原文反馈是同一件东西的两面，把「命中图上文字」判成「没覆盖」在语义上就是错的；"
               "②c 命中 **L4 定稿的「反例/禁区」条款**也算（它们是带条款号的 stable 条款，"
               "只是 L3 把 sample 类单元蒸成「案例」而不是「规则」⇒ 原先池子里一条都没有）；"
               "四者都没有 → 拒答（无命中不等于合规）",
    }
    # ── ★★ A：案例命中**要产出依据**（否则「覆盖成立」了、依据栏还是空的）──────────
    #   形状与规则层命中**逐字段对齐**（library / article_no / anchor / source_sha256 / excerpt），
    #   下游的 `cite()` / `render()` / 发布件 / 双轨合并**一行都不用改**。
    #   severity 取 **REVIEW**（不升 BLOCK）：命中一条反例案例 ≠ 本素材就是那条被否的素材；
    #   要判 BLOCK 需要「自命中」的逐字确证（`selfhit_check.py` 那条路，另外接）。
    _case_by_key = {}
    for c in case_clauses:
        _case_by_key.setdefault(c["anchor"], c)
        if c.get("resource_id"):
            _case_by_key.setdefault("res:" + c["resource_id"], c)
    _seen_case = set()
    for row in _cov_detail["case_unit_hits"]:
        c = _case_by_key.get(row["anchor"]) or _case_by_key.get(
            "res:" + str(_cov_detail["hit_resource_map"].get(row["anchor"])))
        if not c or c["anchor"] in _seen_case:
            continue
        _seen_case.add(c["anchor"])
        # ★★ 题材一致性闸门（2026-10-14）：条款讲的事，本素材里到底有没有？
        #   没有 ⇒ **不产出依据**（但**不影响覆盖判据** —— 覆盖问的是「库认不认识这个题材」）。
        #   被挡下来的全部记进 trace，不静默丢。
        # ★★ 2026-10-14 第二轮：**原先这里传了第三个参数 `row["text_excerpt"]`，那是错的** ——
        #   它是 BM25 的**库内单元**文本（`kb/l6/retriever.py:397` 的 `d["text_excerpt"]`），
        #   对案例条款而言**就是条款自己的话** ⇒ 主题词必然命中 ⇒ **闸门恒过、等于没装**。
        #   实测 S-1.296 的 36 个主题词在它自己单元文本里 **36/36 全中**。
        #   ⇒ 现在只传素材。**别再把这个参数加回来**（`case_theme.py` 的签名也已删掉它）。
        _ok_theme, _why_theme = case_thematic_ok(c, text)
        if not _ok_theme:
            trace.setdefault("coverage", {}).setdefault("case_theme_rejected", []).append({
                "anchor": c["anchor"], "article_no": c.get("article_no"),
                "why": _why_theme})
            continue
        _ra = str(c.get("reason_analysis") or c.get("sample_body") or "")[:120]
        findings.append({
            "severity": "REVIEW", "layer": "案例层（L4 定稿「反例/禁区」）",
            # ★ 2026-10-10：案例层是 L4 定稿的「反例/禁区」。它**不是 P0 确定性匹配**
            #   （那一层走关键词/正则），按 PRD §6.2 归 P1「安全与准确性」。
            #   显式写出来，免得它靠层文案猜（分级的 LAYER_KIND_TO_TIER 也能guess到，
            #   但「能不能 guess 到」不该是设计要求）。
            "p_level": "P1",

            "category": c.get("reason_category") or "反例",
            "sub": "禁区（库内反例条款）",
            "position": position, "excerpt": _ra, "matched_term": row["anchor"],
            "verbatim_verified": False,
            "anchor": c["anchor"], "source_sha256": c.get("source_sha256"),
            "l0_entry_url": _l0_entry_url(c["anchor"]),
            "article_no": c.get("article_no"), "rule_id": c.get("case_id"),
            "kb_type": c.get("kb_type"),
            "library": reg["citation_contract"]["libraries"].get(
                c.get("kb_type") or "unknown", {}).get("label", "未归类（不猜）"),
            "evidence_gap": "本条依据是**库内已定稿的反例条款**（`polarity=反例`、"
                            "`semantics=禁区：不能这么做 + 为什么`），命中判据是「检索命中单元与被引锚点"
                            "**同源**」；该锚点的 L0 件本地无字段值 ⇒ 摘录取自案例记录本身，**需人工点开核对**",
            # ★★ 2026-10-09 晚（Owner 第三次来问，原话：「…了设计美感是好看的…
            #   依据：《内部正负样本库》第 S-1.89 条 ← 命中「…」==》**都是删除 文字**」）：
            #   病灶：`reason` 把**案例记录正文前 80 字**直接拼进「原因」，而那 80 字是
            #   **样本库里某位评审的反馈原话**（实测逐字：「我上午就看到了~设计美感是好看的，
            #   我只是想到了他们之前这类的。原因：不能接受，如果需求方OK，视觉上我是没意见的」）。
            #   两个害处：① 读者以为那是**本素材里的话**（Owner 三次来问）；
            #   ② 那段字里恰好含「图片」「文案」——它**被检索到就是因为这两个词**（检索噪声），
            #     把噪声抄进「原因」等于用噪声解释噪声。
            #   ⇒ 判据改说「按同源/同题材引证」，并把「这段字**不是本素材内容**」写进原因。
            #   ⚠️ **引用仍可回源**：条款号 + 锚点 + source_sha256 + L0 直链都在下面几行，一个字没丢。
            "reason": f"库内反例条款 {c.get('article_no')}（{c.get('reason_category')}）"
                      f"按**同源/同题材**引证 —— 该案例记录的原文（含评审反馈）是库内留痕，"
                      f"**不是本素材里的字**；本单据此给 REVIEW，需人工点开 L0 核对是否真同源",
            "advice": c.get("advice") or None,
            "advice_note": ("advice 取自案例记录；实测 181 条反例里只有 46%% 有 `建议` 列"
                            "（这条%s）" % ("有" if c.get("advice") else "**没有**")),
            "fact_or_inference": "事实", "confidence": "中",
            "verbatim_source": None,
            "classification_basis": "L4 canonical/sample_case.jsonl（polarity=反例）",
        })
    covered = bool(covered_by)
    n = len(findings)
    if any(f["severity"] == "BLOCK" for f in findings):
        state = "BLOCK"
    elif findings:
        state = "REVIEW"
    else:
        state = "PASS" if covered else "拒答"
    _perf["assemble_ms"] = round((time.perf_counter() - _assemble_t) * 1000, 1)
    trace["coverage"]["covered"] = covered
    trace["elapsed_ms"] = round((time.perf_counter() - t_all) * 1000, 1)
    # PRD §12 要按模态判门槛（文字 ≤10s / 图片 ≤20s / 视频 ≤60s）⇒ 把模态与字节数一起记下来，
    # 否则事后没法把一条读数归到哪条门槛上。
    _perf["content_type"] = content_type or "text"
    _perf["text_bytes"] = len((text or "").encode("utf-8"))
    _perf["threshold_s"] = {"text": 10, "image": 20, "video": 60}.get(
        content_type or "text", 10)
    trace["perf"] = _perf

    # ── ★★ 2026-10-12（任务拆解 10/19–10/23 必须做 #1 · PRD §5.3 / §8.3）：问题**维度**标注 ──
    #   病灶：PRD §5.3 逐字「必须**先标注问题所属维度**」、§8.3 逐字要报告每条含「**维度**、位置…」、
    #   §5.4 的 JSON 规范同时给 `risk_type` 与 `risk_category` 两格 —— 而**后者全库 0 命中**。
    #   ⇒ 本处在**返回前统一盖章**（不是改 5 处 `findings.append`：那是一处口径散成五处，
    #     下次有人加第 6 条命中路径必然漏掉一条 —— 本文件自己的注释就记着这个坑）。
    #   口径**只读** `kb/l7/registry/risk-category-policy.json`（唯一一份，本文件不硬编码映射）；
    #   未映射的类别（原则性错误 / 文化禁忌 / 未分类 / unknown）**留空并写明待裁**，**不蒙维度**。
    _stamped_ru, _stamped_rn = 0, 0
    for _f in findings:
        if not isinstance(_f, dict):
            continue
        try:
            _rc.stamp(_f)
        except Exception as _e:                              # noqa: BLE001
            _f["risk_category"] = None
            _f["risk_category_basis"] = "维度模块异常（%s: %s）⇒ **不编**" % (type(_e).__name__, _e)
        if _f.get("risk_category"):
            _stamped_ru += 1
        else:
            _stamped_rn += 1
    trace["risk_category"] = {"with_dimension": _stamped_ru, "unmapped_or_pending": _stamped_rn,
                             "policy": "kb/l7/registry/risk-category-policy.json"}

    return {"state": state, "findings": findings, "unmet_citation": unmet, "trace": trace,
            "registry": {"gate": reg["retrieval"]["gate"], "routing": reg["decision_rules"]["routing"],
                         "approvers": reg["approvers"], "no_hit_semantics": reg["retrieval"]["no_hit_semantics"]},
            "run_id": run_id}


# ---------------- 输出（严格按模板） ----------------
def cite(f, reg):
    ver = "v0（试用版，未发布）"
    url = f"kb/l3/candidates/rules.jsonl#{f['article_no']}"
    return f"《{f['library']} {ver}》第 {f['article_no']} 条（链接：{url}）"


def approve_tail(state, reg):
    ap = reg["approvers"]
    def h(k):
        v = ap.get(k) or {}
        return f"@{v.get('role')}（未配置）" if not v.get("handle") else f"@{v['handle']}"
    return {"PASS": f"未发现已知底线风险，可转交 {h('pass_signoff')} 进行 sign-off",
            "REVIEW": f"建议转 {h('review_reviewers')} 复核。",
            "BLOCK": "请修改后重新提交。"}[state]


def render(result, reg, report_path=None):
    state, fs = result["state"], result["findings"]
    if state == "拒答":
        t = result["trace"]
        u, cov = t["units"], t["coverage"]
        gate_bm = u["gate"]["bm25_raw_min"]
        gate_cos = u["gate"]["vector_cosine_min"]
        cov_thr = cov.get("coverage_bm25_min", gate_bm)
        nhs_key = "hybrid" if (u["used_vector"] and u["semantic_recall"]) else "bm25_only"
        nhs = reg["retrieval"]["no_hit_semantics"][nhs_key]
        lines = ["【审查结论：无法给出结论（拒答）】未检索到可作依据的知识库条目。", "",
                 f"- 查了什么：{json.dumps(result.get('query_words', ''), ensure_ascii=False)}",
                 f"- 用了几种模式：BM25（最高原始分 {u['bm25_max']}）"
                 + (f" ＋向量补召（最高余弦 {u['cosine_max']}）" if u["used_vector"]
                    else f"；向量补召未启用（BM25 最高分已过依据门限 {gate_bm}，没触发补召，本轮无余弦分）"),
                 f"- 逐层为什么没有依据：",
                 f"  1) P0 确定性匹配：{len(t['p0']['hits'])} 命中",
                 f"  2) 规则层：{len(t['rules']['hits'])} 命中 —— 没有规则可以当依据",
                 f"  3) 单元层：BM25 最高 {u['bm25_max']}（依据门限 {gate_bm}，覆盖门限 {cov_thr}）；"
                 f"被规则引用且过覆盖门限的材料 {len(cov['rule_cited_unit_hits'])} 条；"
                 f"命中允许表述（安全词）{len(cov['safe_vocabulary_hits'])} 条",
                 f"  → 结论：没有规则层命中，单元层也没有「知识库确实管这块」的覆盖信号"
                 f"（覆盖门限 {cov_thr} 或安全词），所以既不能给三态结论，也不能说合规",
                 f"- 语义召回标注：{u['no_semantic_annotation'] or '语义召回可用（L6 = vector_plus_bm25）'}",
                 f"- {nhs}"]
        return "\n".join(lines)
    head = {"PASS": "未发现已知底线风险，可转交", "REVIEW": f"共发现 {len(fs)} 处需人工确认。",
            "BLOCK": f"共发现 {len(fs)} 处必须修改。"}[state]
    lines = [f"【审查结论：{state}】{head}"]
    if state == "PASS":
        lines[0] = f"【审查结论：PASS】{approve_tail('PASS', reg)}"
        return "\n".join(lines)
    lines.append("")
    if len(fs) <= 2:
        for i, f in enumerate(fs, 1):
            lines.append(f"{i}.【{f['category']}-{f['sub']}】{f['position']}，{f['excerpt']}")
            lines.append(f"  原因：{f['reason']}")
            lines.append(f"  依据：{cite(f, reg)}")
            lines.append(f"  锚点：{f['anchor']}｜source_sha256：{f['source_sha256']}")
            # ★★ 2026-10-14（Owner 裁定）：逐条块**不再输出「判定：…｜置信度：…」这一行**。
            #   口径：PRD §5.3 逐条模板只有 原因 / 依据 /（BLOCK 才有）建议，三态只在结论行
            #   一处 ⇒ 同一张卡上不许出现两个「判定」。
            #   `f['fact_or_inference']` / `f['confidence']` **仍在引擎 JSON 里**（只改版式）。
            if state == "BLOCK" and f.get("advice"):
                lines.append(f"  建议：{f['advice']}")
            if i != len(fs):
                lines.append("")
    else:
        # ── ★★ 2026-10-12（Owner 批准「推荐 ①」）：分类汇总按**维度**分组 ────────────────
        #   PRD **§5.3.2**「问题数量 ≥ 3 个时，只输出分类汇总 + 报告链接」的逐字示例是：
        #       · 合规类问题：3 个
        #       · 消费者安全类问题：1 个
        #       · 措辞表达类问题：1 个
        #   —— 分的是 **§5.3 的四维**，不是**库内类别**。
        #   改前按 `f["category"]`（功效宣称 / 绝对化与安全承诺 / …）⇒ 真输出是
        #   「· 功效宣称类问题：1 个」，与 PRD 逐字示例**不是同一样东西**。
        #
        #   口径**不抄第二份**：`risk_category` 由 `review()` 返回前统一盖章（唯一真源
        #   `kb/l7/registry/risk-category-policy.json`，实现 `risk_category.py`），本处只读结果。
        #   未映射的四类（原则性错误 / 文化禁忌 / 未分类 / unknown）**单成一桶、如实署名、排在最后**：
        #   **既不丢掉、也不并进「合规」** —— 桶名与 `report_memory` 的「未标注维度」保持同一个词。
        #   ⚠️ 桶**不按**一份写死的四维顺序排（那会是第二份词表）：按首次出现顺序，
        #      只把「未标注维度」压到最后。
        agg = {}
        _bucket = _unmapped_dim_bucket()      # None ⇒ 退回库内类别分组（= 改前行为，且已告警）
        for f in fs:
            k = (f.get("risk_category") or _bucket) if _bucket else (f.get("category") or "未分类")
            agg[k] = agg.get(k, 0) + 1
        for k in sorted(agg, key=lambda x: (x == _bucket,)):
            lines.append(f"· {k}类问题：{agg[k]} 个")
        lines.append("")
        lines.append(f"→ 查看完整问题清单与修改建议：{report_path or '（未写报告，见 --report-dir）'}")
    lines.append("")
    lines.append(approve_tail(state, reg))
    return "\n".join(lines)


# ── l8 补丁（2026-09-23）：报告 .md 必须明文落盘 ───────────────────────
# 本机有一层按后缀生效的写封装：python/perl 写 .md 会落盘成 4096 字节前缀信封，
# 宿主侧 Electron/Node 读取者（agent 的 read 工具、工作台镜像器）拿到的是信封、
# 不是文本 —— 报告等于白写。实测证据见 kb/l8/diagnosis.md（E1–E11）与
# kb/l8/docs_repair_20260923-1535.json。所以 .md 一律交给 node 写，并读回断言。
_NODE_WRITE_AND_VERIFY = r"""
const fs = require("fs"), crypto = require("crypto");
const target = process.env.KB_TARGET;
const want = fs.readFileSync(process.env.KB_SOURCE);      // 已经是最终字节
fs.mkdirSync(require("path").dirname(target), { recursive: true });
fs.writeFileSync(target, want);
const got = fs.readFileSync(target);
const sha = (b) => crypto.createHash("sha256").update(b).digest("hex");
const ok = got.length === want.length && sha(got) === sha(want);
console.log(JSON.stringify({ target, bytes: got.length, ok }));
process.exit(ok ? 0 : 2);
"""


def _resolve_node():
    """找出**能直接用**的 node 运行时列表（本机 PATH 里没有 node），按优先级返回 [(bin, extra_env)]。

    顺序很关键（2026-09-30 实测，MVP 被它挡住一次）：
      原先 ChatGPT 的 cua_node 排第一，而本机那个二进制被 SIGKILL（返回 -9），
      于是 node 通道白白失败、降级成 python 写盘 → 报告落成**信封态**（宿主侧读不到，
      python getsize 与 node statSync 差 -4096）。DSH Electron + ELECTRON_RUN_AS_NODE=1
      是本机实测可用的通道，故排第一；其余候选**逐个试**，不是一试就投降。
    """
    cands = []
    if os.environ.get("KB_NODE_BIN"):
        cands.append((os.environ["KB_NODE_BIN"], {}))
    # ⚠️ 两个 glob 都要留：本机 app 名是 `DSH Desktop.app.pre-lute-…`（`.app` 在中间），
    # 只写 `DSH Desktop*.app/...` 会**匹配不上**，于是掉到 ChatGPT 那个被 SIGKILL 的 node（rc=-9），
    # 再降级成 python 写盘 → 报告变信封态。实测 2026-09-30 就是这么被挡住的。
    for pat in ("/Applications/DSH Desktop*/Contents/MacOS/*",
                "/Applications/DSH Desktop*.app/Contents/MacOS/*"):
        for base in sorted(glob.glob(pat)):
            if os.path.basename(base) == "DSH Desktop" or "DSH Desktop" in base:
                cands.append((base, {"ELECTRON_RUN_AS_NODE": "1"}))
    cands.append(("/Applications/ChatGPT.app/Contents/Resources/cua_node/bin/node", {}))
    return [(c, e) for c, e in cands if c and os.path.exists(c)]


def write_text_plain(path: str, text: str) -> str:
    """把 text 明文写到 path（.md 专用）。返回实际用的通道名。

    node 通道：写前把内容落到一个非 .md 的临时文件，再由 node 读它、写目标、读回断言。
    没 node 时降级为 python 写盘，并打印警告 —— 那条路 agent 可能读不到这份报告。
    """
    import subprocess, tempfile
    cands = _resolve_node()
    if cands:
        fd, tmp = tempfile.mkstemp(prefix="kb-review-", suffix=".txt")
        with os.fdopen(fd, "wb") as fh:
            fh.write(text.encode("utf-8"))
        try:
            for node, extra in cands:                 # 逐个候选试，别一试就降级
                env = dict(os.environ, **extra, KB_TARGET=path, KB_SOURCE=tmp)
                try:
                    proc = subprocess.run([node, "-e", _NODE_WRITE_AND_VERIFY],
                                          capture_output=True, text=True, env=env, timeout=120)
                except Exception as exc:              # noqa: BLE001
                    print("[warn] node 候选不可用（%s）：%s" % (os.path.basename(node), exc))
                    continue
                if proc.returncode == 0:
                    return "node:" + os.path.basename(node)
                print("[warn] node 候选失败（%s，rc=%s）：%s"
                      % (os.path.basename(node), proc.returncode,
                         (proc.stderr or proc.stdout).strip()[:160]))
        finally:
            try:
                os.unlink(tmp)
            except OSError:
                pass
    else:
        print("[warn] 找不到 node 运行时（KB_NODE_BIN / DSH Electron / ChatGPT 都没有）")
    print("[warn] 降级为 python 写盘：宿主侧 agent 可能读不到这份报告（会被封成信封）")
    open(path, "w", encoding="utf-8").write(text)
    return "python-fallback"


def write_report(result, reg, report_dir, run_id, apply=True):
    path = os.path.join(report_dir, f"{run_id}.review.md")
    fs = result["findings"]
    L = [f"# 内容审查完整问题清单（run_id {run_id}）", "",
         f"结论：**{result['state']}**｜问题数：{len(fs)}｜生成时间：{time.strftime('%Y-%m-%d %H:%M:%S')}", ""]
    # ── 接线（2026-10-01 · C 块）：版本绑定 ────────────────────────────────
    # 「审查报告与记忆」SKILL.md :17 要求每份报告绑 review_id + content hash + content version
    # + agent version + rule version + knowledge version。改之前这份报告**一个版本号都没有**。
    # 这里只补一张绑定表，不动结论、不动问题清单里的任何一行。
    _vb = version_binding(result.get("content") or "", reg)
    L += ["## 版本绑定", "",
          f"- review_id：`{run_id}`",
          f"- content hash（= content version）：`{_vb['content_hash']}`",
          f"- agent version：`{_vb['agent_version']}`",
          f"- rule version：`{_vb['rule_version']}`",
          f"- knowledge version：`{_vb['knowledge_version']}`", ""]
    if result.get("content"):
        L += ["## 送审内容", "", "```", result["content"][:2000], "```", ""]
    L += ["## 问题清单", ""]
    for i, f in enumerate(fs, 1):
        # `verbatim_verified=False` = P0 等价说法/正则命中，源侧无逐字原文（见 review() 的口径）。
        # 这类条目**没有** verbatim_source，所以下面三行必须容错，否则报告直接 KeyError。
        verified = f.get("verbatim_verified", True)
        # ★★ 2026-10-09 晚（Owner：「都是删除 文字」）—— 引文那一行改两处：
        #   ① **案例层**的 `excerpt` 取自**案例记录正文**（`review()` 自己写着「该锚点的 L0 件
        #      本地无字段值 ⇒ 摘录取自案例记录本身」）⇒ 它不是"命中"本素材，如实标性质；
        #   ② `verified=False` 那支原先印 `excerpt` **全文（截 200 字）** —— 实测那 200 字正是
        #      样本库里某位评审的反馈原话，读者会当成"我图上的字"。
        #      ⇒ 正文**只留 20 字作定位**（实测那段样本备注本身才 ~52 字 ⇒ 「前 60 字」等于全文，
        #        这一条是被判据抓出来的）。全文仍在机读 JSON 的 `excerpt` + L0 直链里。
        _is_case = "案例" in str(f.get("layer") or "")
        _ex = str(f.get("excerpt") or "")
        if verified and not _is_case:
            _quote_line = f"- 引文（逐字）：{_ex}"
        elif _is_case:
            _quote_line = (f"- 同类案例记录原话（**非本素材内容**，仅留 20 字定位）：{_ex[:20]}…"
                           f"（全文见机读 JSON 的 `excerpt` 与下方 L0 直链）")
        else:
            _quote_line = f"- 命中表达（**非逐字**，源侧无此原文，仅留 20 字）：{_ex[:20]}…"
        # ★★ 2026-10-12（10/19–10/23 行 #5 · PRD §8.3 逐字「完整问题清单，**每条包含：维度**、
        #   位置、问题描述、原因、依据文档链接、修改建议」）：这一行把「维度」补进清单。
        #   改前**整份报告没有「维度」二字**（实测：近 15 份报告命中 0）——
        #   标题行印的是 `【库内类别-子类】`，那是**细分**不是**维度**，两者在 PRD §5.4 里是两格。
        #   本行**只增不改**：标题行、`_quote_line`、其余各行一字未动。
        #   未映射的类别（原则性错误 / 文化禁忌 / 未分类 / unknown）**如实写「未标注维度」＋待裁理由**，
        #   **不蒙一个维度**（蒙错比留空更坏 —— 留空人会去补，错值人不会回头看）。
        _dim = f.get("risk_category")
        _dim_basis = f.get("risk_category_basis")
        if _dim:
            _dim_line = f"- 维度：**{_dim}**" + (f"（{_dim_basis}）" if _dim_basis else "")
        else:
            # ★ 桶名同样**只从唯一真源取**（`risk_category.UNMAPPED_BUCKET`）——
            #   本文件不写那个词的字面量，写了就是第二份口径（三处各写一份必然漂移）。
            _bkt = _unmapped_dim_bucket()
            _label = f"{_bkt}（待裁）" if _bkt else "（维度模块不可用，本格留空）"
            _dim_line = f"- 维度：**{_label}**" + (f" —— {_dim_basis}" if _dim_basis else "")
        L += [f"### {i}.【{f['category']}-{f['sub']}】{f['position']}", "",
              _dim_line,
              _quote_line,
              f"- 原因：{f['reason']}",
              f"- 依据：{cite(f, reg)}",
              f"- 锚点：`{f.get('anchor')}`",
              f"- source_sha256：`{f.get('source_sha256')}`",
              (f"- 原文出处：`{f['verbatim_source']['path']}` 字段 `{f['verbatim_source']['field']}`"
               if f.get("verbatim_source")
               else f"- 原文出处：**无逐字出处** —— {f.get('evidence_gap') or '（依据不可逐字回源）'}"),
              # ★ 2026-10-08（Owner 批准 D）：**L0 飞书直链**。
              #   库规原话：「要真核对只能点飞书直链」—— 那就必须把它交出来。
              #   两个来源都取：命中时 `resolve_anchor` 带回的 `entry_url`，
              #   或缺口路径上由 `_l0_entry_url()` 单独取的（那类 L0 件没有 fields、但有 entry_url）。
              #   **取不到就不写这一行**（宁可空着也不编 —— 一个点不开的链接比没有更坏）。
              # ⚠️ 2026-10-10 修：**取值口径必须与判据逐字一致**。
              #   病灶（实测，2026-10-10 16:02 全链跑红）：判据是
              #     `f.get("l0_entry_url") or (f.get("verbatim_source") or {}).get("entry_url")`
              #   —— **带 get + 回落**；而取值写的是 **直取** `f['l0_entry_url']`。
              #   ⇒ 当 **`l0_entry_url` 这个键本身不存在**、但 `verbatim_source.entry_url` 有值时：
              #     判据**放行**，取值**KeyError**。
              #   ⇒ 整个 `review.py` 崩在报告渲染，链在「③ 出结论」停住
              #     （`review_run.sh` 报「引擎输出无法解析 / 引擎退出码 2」）——
              #     **不是没查到，是报告写不出来**。
              #   为什么以前没炸：`write_report` 只在 **findings >= 3** 时被调用
              #     （`main()` 的 `len(res["findings"]) >= 3 or a.report_dir`）
              #     ⇒ **只有 1–2 条问题的单子走不到这一行**，所以一直藏着。
              #   修法：**取一次、判一次，同一个变量**（不再让判据与取值各写一遍）。
              *(["- L0 飞书直链（点开核对逐字原文）：%s" % _l0u]
                if (_l0u := (f.get("l0_entry_url")
                             or (f.get("verbatim_source") or {}).get("entry_url")))
                else []),
              # ★★ 2026-10-14（Owner 裁定）：报告逐条里同样**去掉「判定：…｜置信度：…」**，
              #   与回执、与 PRD §5.3 逐条模板保持一致（三态只在结论行）。
              f"- 分层：{f['layer']}｜分类依据：{f['classification_basis']}", ""]
        if f.get("advice"):
            L += [f"- 建议：{f['advice']}", ""]
        if f.get("advice_note"):
            # 把「同源检查」的结论写进报告：被丢弃了几句子属于其他规则码的建议，可追溯
            L += [f"- 建议同源检查：{f['advice_note']}", ""]
    if result["unmet_citation"]:
        L += ["## 无法满足引用契约的结论", ""]
        for u in result["unmet_citation"]:
            # disposition：P0 命中走的是「已输出但标了 gap」，规则层走的是「未输出」——
            # 两者都不静默，但处置不同，报告里必须分开写，不能混成一句「未输出」。
            mark = ("**已输出为 BLOCK**（依据不可逐字回源，见问题清单里 `verbatim_verified=False` 的那条）"
                    if u.get("disposition") == "output_as_block_with_gap" else "**未输出**")
            L += [f"- {u['source']}｜{u.get('article_no')}｜{mark}｜{u.get('why')}｜摘录：{u.get('excerpt')}", ""]
    L += ["## 检索轨迹", "", "```json", json.dumps(result["trace"], ensure_ascii=False, indent=1)[:6000], "```", ""]
    body = "\n".join(L)
    # ── 干跑档（l7 补丁 2026-09-29）：不带 --apply 之外的路径，一律先能预演
    # 背景：本 skill 的契约要求「完整清单必须真的写到 reports/」，所以**默认仍落盘**
    # （改默认为干跑会破坏既有契约与 106 份已生成报告的使用方式）；
    # 这里补的是**可预演**能力 —— --dry-run 只打印目标/字节/前 20 行，不写任何文件。
    if not apply:
        print(f"[dry-run] 未落盘。目标：{path}｜{len(body.encode('utf-8'))} 字节｜{len(L)} 行", file=sys.stderr)
        for ln in body.splitlines()[:20]:
            print("  | " + ln, file=sys.stderr)
        if len(L) > 20:
            print(f"  | …（共 {len(L)} 行；加 --apply 或去掉 --dry-run 即落盘）", file=sys.stderr)
        return None
    os.makedirs(report_dir, exist_ok=True)
    channel = write_text_plain(path, body)   # l8 补丁：明文落盘
    # 必须走 stderr：stdout 是 --json 的数据通道，写日志进去会让 json.load / jq 直接崩
    # （实测 `Expecting value: line 1 column 2`，因为日志占掉了第 1 行）。
    print(f"[review] 报告落盘通道：{channel} → {path}", file=sys.stderr)
    return os.path.relpath(path, ROOT)


# ══ 接线（2026-10-01 · C 块）：「报告与记忆」这一跳 ══════════════════════════
# 手册 §五-1 记的断点：「报告与记忆这一跳（审查报告与记忆）没接：结论目前落在
# review.py 的报告里，没走它的模板/存档契约。」被接的另一头是
# `kb/l7/review-engine/core/report_memory.py`（该 SKILL.md :15 明写用它渲染）。
#
# ★ 本段**只做接线**：把本脚本已经算出的结论与依据**改名搬过去**，不重算任何东西。
#   `state` / `findings[].severity` / `layer` / `confidence` 全部原样；
#   这里不合成全局置信度数值、不改三态、不调用 review_engine.decide()（那边一个字没动）。
REPORT_MEMORY_REL = ("kb", "l7", "review-engine", "core", "report_memory.py")
SKILL_MD_REL = ("kb", "l7", "skills", "kb-content-review", "SKILL.md")

# ══ 接线（2026-10-10）：「P0–P3 四层分级」这一跳（任务拆解 目标 12 · PRD §6.2/§6.3）═
# 手册记的断点：引擎里**只有 `priority_tier == "P0"` 的执行分支**，
# 非 P0 一律缺省写成 **P1**，**P2 / P3 无分支**。
# ⇒ PRD §6.3 第二层（P1 安全准确性·语义）与第三层（P2 通识常识·多模态）没实现；
#   PRD §7.2 九域里 7 个域挂在 P1/P2 ⇒ 这 7 个域判不了。
#
# ★ 病灶的形状：**生产者就地硬编码**「不是 P0 就是 P1」——
#   本文件 `_to_risk_item` 原写 `"P0" if "P0" in layer else "P1"`，
#   **看的是层文案里有没有「P0」二字，不是规则的 `p_level`**。
#   于是 `p_level=P2` 的 11 条、`p_level=P3` 的 4 条规则命中了也只报 P1。
# ★ 口径收成一份：`kb/l7/review-engine/core/tiering.py`（自证 `--selftest` 29/29）。
TIERING_REL = ("kb", "l7", "review-engine", "core", "tiering.py")


def _load_tiering():
    """动态加载分级模块。**加载不到就返回 None，让老口径继续跑** ——
    分级是增强，不该让整条评审链因为一个 import 就崩（口径同 `_load_report_memory`）。
    """
    import importlib.util
    p = os.path.join(ROOT, *TIERING_REL) if ROOT else None
    if not p or not os.path.exists(p):
        return None
    try:
        spec = importlib.util.spec_from_file_location("kb_tiering", p)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    except Exception as e:                                    # noqa: BLE001
        print("[tiering] ⚠ 分级模块加载失败，退回老口径（非 P0 即 P1）：%s" % e)
        return None


_TIERING = None


def _tier_of_finding(p_level, layer, severity=None, risk_level=None):
    """返回 (tier, basis)。分级模块在就用它；不在就**逐字退回**老口径（可观测、不静默）。"""
    global _TIERING
    if _TIERING is None:
        _TIERING = _load_tiering() or False
    if _TIERING:
        return _TIERING.tier_of(p_level=p_level, layer=layer,
                                severity=severity, risk_level=risk_level)
    return ("P0" if "P0" in str(layer or "") else "P1",
            "分级模块未加载 ⇒ 老口径（P0 in layer else P1）")


_SEV_WARNED = []


# ── ★★ 2026-10-12：问题**维度**（PRD §5.3 / §8.3）—— 唯一实现在**同目录** ──────────
#   为什么懒加载：与 `_load_tiering` 同一条纪律 —— 维度标注是**增强**，
#   不该让整条评审链因为一个 import 就崩；加载不到就**留空并出声**（不静默、不编）。
_RC = None


def _load_risk_category():
    global _RC
    if _RC is None:
        try:
            import importlib.util
            _p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "risk_category.py")
            _spec = importlib.util.spec_from_file_location("kb_risk_category", _p)
            _m = importlib.util.module_from_spec(_spec)
            _spec.loader.exec_module(_m)
            _RC = _m
        except Exception as e:                                # noqa: BLE001
            print("[risk_category] ⚠ 维度模块加载失败 ⇒ 本单 `risk_category` 留空（**不编**）：%s" % e)
            _RC = False
    return _RC


class _LazyRC:
    """薄代理：调用点写成 `_rc.stamp(f)`，真加载推迟到第一次调用。"""

    def __getattr__(self, k):
        m = _load_risk_category()
        if not m:
            raise RuntimeError("risk_category 模块不可用")
        return getattr(m, k)


_rc = _LazyRC()


def _unmapped_dim_bucket():
    """未映射类别的**桶名** —— 唯一真源 `risk_category.py::UNMAPPED_BUCKET`。

    ★ 本文件**不写桶名字面量**（写了就是第二份口径，正是本库反复栽的那一类）。
    ★ 模块取不到时返回 `None` 并**打印告警**（不静默）：调用方据此退回库内类别分组
      （= 改前行为）。为什么不直接抛：桶名只是**呈现**，而模块真的坏了的话
      `stamp()` 那边早已把每条 `risk_category` 留空 —— 也就是说
      **全部条目会落进同一个桶、一眼就能看出不对**，不会伪装成一个像样的分组。
    """
    try:
        return _rc.UNMAPPED_BUCKET
    except Exception as e:                                    # noqa: BLE001
        print("[risk_category] ⚠ 汇总分组退回落库内类别（桶名真源不可用）：%s" % e,
              file=sys.stderr)
        return None


def _severity_of(p_level, risk_level):
    """命中该判 BLOCK 还是 REVIEW —— **唯一口径在 `tiering.py::severity_for`**。

    ★★ 2026-10-12：修 `review.py:982/1015` 那条**静默死掉的红线子句**。
      原写 `h.get("risk_level") == "高危·红"`，而 2026-10-10 的换词表已把 L3 规则行那一列
      改成**英文** ⇒ 子句恒假（哑失败：不抛异常、不报错、分布上看不出来）。
      实测代价：41 条规则 `risk_level=Critical` 但 `p_level≠P0`，本该 BLOCK 的落了 REVIEW。
      详见 `tiering.CRITICAL_RISK_LEVELS` / `SEVERITY_BLOCK_TIERS` 两处抬头。

    ⚠️ 这里**不许再写一个字面量** —— 病灶的形状就是「生产者就地硬编码一个会过期的值」。
      分级模块加载不到时**逐字退回**旧判定（`P0 or == "高危·红"`），并**出声**（不静默降级）。
    """
    global _TIERING
    if _TIERING is None:
        _TIERING = _load_tiering() or False
    if _TIERING:
        return _TIERING.severity_for(p_level, risk_level)
    if not _SEV_WARNED:
        _SEV_WARNED.append(1)
        print("[tiering] ⚠ 分级模块未加载 ⇒ 严重度判据退回旧字面量"
              "（只认 `高危·红`，**换词表后的 `Critical` 认不出**）—— 本段结论可能低估严重度")
    if str(p_level or "").strip().upper() == "P0" or str(risk_level or "").strip() == "高危·红":
        return "BLOCK", "退回旧口径（分级模块未加载）"
    return "REVIEW", "退回旧口径（分级模块未加载）"


#: 契约要的 next_action —— 逐字取自 kb/l7/output_template.md「尾部动作」四行，不是新判定。
_NEXT_ACTION = {
    "PASS": "转 sign-off 责任人确认送审版本与发布版本一致",
    "REVIEW": "建议转复核责任人复核。",
    "BLOCK": "请修改后重新提交。",
    "拒答": "补齐证据后重新提交。",
}


def _load_report_memory():
    """按解析出的 ROOT 动态加载报告渲染器，返回 (module, path)。

    加载不到**只警告、不让评审失败** —— 报告是产物不是前置（口径同下面的 _write_findings_cache）。
    """
    import importlib.util
    p = os.path.join(ROOT, *REPORT_MEMORY_REL)
    try:
        spec = importlib.util.spec_from_file_location("report_memory", p)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod, p
    except Exception as e:                      # noqa: BLE001
        print("[warn] report_memory 没加载上（%s）：%r" % (p, e), file=sys.stderr)
        return None, p


def _read_json_soft(path):
    try:
        return json.load(open(path, encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _sha256_file(path):
    try:
        h = hashlib.sha256()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def _skill_version():
    """读本 skill SKILL.md frontmatter 的 version —— 版本绑定的真源，不硬编码。"""
    p = os.path.join(ROOT, *SKILL_MD_REL)
    try:
        with open(p, encoding="utf-8") as fh:
            first = fh.readline()
            if first.strip() != "---":
                return None
            for line in fh:
                if line.strip() == "---":
                    break
                if line.startswith("version:"):
                    return line.split(":", 1)[1].strip().strip('"').strip("'")
    except OSError:
        return None
    return None


def version_binding(text, reg):
    """版本绑定：钉死「这份结论是对着哪一版内容 / 哪一版规则 / 哪一版库」。

    契约要求（`审查报告与记忆/SKILL.md` :17）：review_id + content hash + content version
    + agent version + rule version + knowledge version，六项全带。
    **读不到的项写 null，不编**（sources 里记明每一项读的是哪个文件）。
    """
    sha = hashlib.sha256((text or "").encode("utf-8")).hexdigest()
    l3 = _read_json_soft(os.path.join(ROOT, "kb", "l3", "registry", "l3.json"))
    rules_sha = _sha256_file(RULES)
    scheme = (reg.get("article_no_source") or {}).get("scheme_version")
    distiller = l3.get("distiller_version")
    rule_parts = [x for x in (scheme, distiller,
                              ("rules.jsonl@" + rules_sha[:16]) if rules_sha else None) if x]
    ver = _skill_version()
    return {
        "review_id": None,                       # 由调用方按 run_id 填（本脚本的运行标识就是报告名）
        # ★ 2026-10-10：原为 `"text-" + sha[:12]`（本库**第三套**内容 ID 形态）。
        #   PRD §5.4 要 `AD-YYYYMMDD-NNN`，发号真源收成 `core/content_id.py` 一份；
        #   这里**只做形态声明**，不去发表（依据侧不该为发个号去读飞书表）——
        #   真正的业务号由**发号方**（`with_kb_evidence` / 发布件）在发飞书那一刻发。
        #   见 `kb/l7/registry/report-output-contract.yaml::applied_20261010_content_id`。
        "content_id": None,
        "content_id_form": "AD-YYYYMMDD-NNN（PRD §5.4）",
        "content_id_note": ("本入口（依据侧）**不发业务号** —— 发号要读飞书表，"
                            "而依据侧不该为此访问飞书。业务号由发号方在发飞书那一刻发："
                            "`kb/l7/review-engine/core/content_id.py`（唯一实现）。"),
        "content_fingerprint": "text-" + sha[:12],
        "content_hash": sha,
        "content_version": sha,
        "agent_version": ("kb-content-review@" + ver) if ver else "kb-content-review@unknown",
        "rule_version": "+".join(rule_parts) or None,
        "knowledge_version": reg.get("kb_version"),
        "sources": {
            "content_hash": "送审文本 utf-8 的 sha256",
            "agent_version": "/".join(SKILL_MD_REL) + " → frontmatter.version",
            "rule_version": "kb/l7/registry/l7.json → article_no_source.scheme_version"
                            " ＋ kb/l3/registry/l3.json → distiller_version"
                            " ＋ kb/l3/candidates/rules.jsonl 的 sha256[:16]",
            "knowledge_version": "kb/l7/registry/l7.json → kb_version",
        },
    }


def _coverage_block(content_type):
    """报告契约要的 coverage 块：本入口只送审一种模态，其余标 not_applicable。

    这**不是**「OCR/ASR 流水线跑完了」的声明，故 note 里写明口径；逐模态的真实执行情况看 trace。
    """
    cov = {k: "not_applicable" for k in
           ("text", "image", "audio", "video", "ocr", "asr", "keyframes")}
    cov[content_type if content_type in cov else "text"] = "complete"
    cov["note"] = ("本批只送审 %s 一种模态；其余模态不适用（不是缺口）。"
                   "本块是报告契约要求的覆盖状态，不等于 OCR/ASR/关键帧流水线已执行 —— "
                   "后者见 trace。" % content_type)
    return cov


def _decision_reasons(res):
    """把 review.py :709-715 那个 if/elif 链**读出来**（不改它），供 decision_trace 记录。"""
    st, fs = res.get("state"), res.get("findings") or []
    if st == "拒答":
        return ["no_rule_hit_and_no_coverage_signal"]     # 无命中又不认识主题 → 拒答
    if st == "BLOCK":
        return ["any_finding_severity_block"]
    if st == "REVIEW":
        return ["findings_present_without_block"]
    return ["no_findings_and_kb_covers_topic"]


def _tier_trace(res):
    """四层命中计数（PRD §6.2 / §6.3）—— 与 `review_engine.decide()` 的 `tier_trace` 同口径。

    依据侧的 finding 现在都带 `p_level`（2026-10-10 补），所以这里能**按层级**数，
    不再是「不是 P0 就是 P1」。口径与裁决侧一致：**数「命中的」，不是数「拦住的」**。
    """
    c = {"P0": 0, "P1": 0, "P2": 0, "P3": 0, "未标层": 0}
    for f in (res.get("findings") or []):
        t, _ = _tier_of_finding(f.get("p_level"), f.get("layer"),
                                severity=f.get("severity"), risk_level=f.get("risk_level"))
        c[t if t in c else "未标层"] += 1
    return c


def _confidence_flow_note(res):
    """PRD §6.6 置信度分流在**本入口**为什么不适用 —— 必须写出依据，不许静默不写。

    本入口（依据侧）**不合成全局数值置信度**（逐条给 高/中/低，见 `:1715` 那段注释），
    所以没有「一个数」可拿去切 §6.6 的三档。数值置信度与分流都在**裁决侧**
    （`review_engine.decide()` → `decision_trace.confidence_route`）。
    """
    return {
        "applies": False,
        "band": None,
        "calibrated": False,
        "why": ("依据侧**不合成全局数值置信度**（逐条给 高/中/低）⇒ 没有可切三档的数。"
                "PRD §6.6 的数值分档与标注在**裁决侧**生效：见 "
                "`review_engine.decide()` → `decision_trace.confidence_route`；"
                "策略真源 `kb/l7/registry/confidence-policy.json`。"),
        "handled_by": "kb/l7/review-engine/core/review_engine.py::decide()",
    }


def _finding_to_risk_item(f, index):
    """依据 → report_memory 的 risk_items 一条。**只改名、不改值**（映射见 docstring 表）。

    六要素（库名 / 条款号 / anchor / source_sha256 / 逐字摘录）原样塞进 `evidence`，
    并在齐了的时候给出 `evidence_id` / `evidence_url`；不齐就显式写 `evidence_gap`，不静默。
    """
    lib, art = f.get("library"), f.get("article_no")
    anc, sha, exc = f.get("anchor"), f.get("source_sha256"), f.get("excerpt")
    complete = all([lib, art, anc, sha, exc])
    layer = str(f.get("layer") or "")
    _tier, _tier_basis = _tier_of_finding(f.get("p_level"), layer,
                                          severity=f.get("severity"),
                                          risk_level=f.get("risk_level"))
    verified = f.get("verbatim_verified", True)
    cat, sub = f.get("category") or "未分类", f.get("sub") or ""
    sev = f.get("severity")
    item = {
        "risk_id": f.get("rule_id") or ("R%d" % index),
        "risk_type": ("%s-%s" % (cat, sub)) if sub else cat,
        # ★★ 2026-10-12（10/19–10/23 行 #5 · PRD §5.3 / §8.3 / §5.4）：问题**维度**必须跟着搬出去。
        #   病灶（实测，不是预防性设计）：`review()` 返回前**已经**逐条盖了章
        #   （`risk_category` = 合规/消费者安全/产品描述/措辞表达，口径唯一真源
        #    `kb/l7/registry/risk-category-policy.json`），
        #   `with_kb_evidence._to_risk_item` 也把这两格照搬了 —— **唯独本函数没搬**。
        #   ⇒ findings 有、`risk_items` 没有，而 `report_memory.render_markdown` 正是按这一格分组
        #     （读不到才回落 `risk_type`）⇒ PRD §5.3/§8.3「按维度分组展示」在真报告上从未生效。
        #   **量化代价**（2026-10-12 现读 `kb/l7/reports/*.json`，282 份 / 725 条 risk_items）：
        #     `risk_category` 为 None **725/725**；`risk_category_basis` 非空 **0/725**
        #     —— basis 只要盖过章就必然是非空串，**这个 0 本身就证明盖章结果没走到这一步**。
        #   **未映射的类别照旧留 None ＋ basis 写明「待裁」，不蒙维度**（与唯一实现同一条纪律）。
        "risk_category": f.get("risk_category"),
        "risk_category_basis": f.get("risk_category_basis"),
        # priority_tier：**从规则的 `p_level` 取**（任务拆解 目标12 · PRD §6.2 主路）。
        # 改前是 `"P0" if "P0" in layer else "P1"` —— 看的是**层文案里有没有「P0」二字**，
        # 于是 `p_level=P2`（11 条）与 `p_level=P3`（4 条）的规则命中了也只报 P1，
        # PRD §6.3 第二/第三层等于没实现。现在走 `core/tiering.py` 的单一口径，
        # 依据留在 `priority_tier_basis`（可逐条复核它凭什么定这一层）。
        "priority_tier": _tier,
        "priority_tier_basis": _tier_basis,
        "layer": layer,
        "p_level": f.get("p_level"),          # ★ 带上原始层级，供下游复核（不是新判定）
        "risk_level": f.get("risk_level"),    # ★ 2026-10-12 更正：**换词表后是英文档**（Critical/High/Medium/Low/unknown），不再是「中文档（高危·红）」（那条注释已过期）
        "severity": sev,
        "status": "confirmed",
        "action": "block" if str(sev).upper() == "BLOCK" else "review",
        "location": f.get("position") or "未定位",
        "original_text": exc or "",
        "reason": f.get("reason") or "",
        "suggestion": f.get("advice") or "",
        "verbatim_verified": verified,
        "fact_or_inference": f.get("fact_or_inference"),
        "confidence": f.get("confidence"),          # 逐条原样（高/中/低），不合成全局数值
        "evidence": {"library": lib, "article_no": art, "anchor": anc,
                     "source_sha256": sha, "excerpt": exc},
        "source": "kb-content-review",
    }
    if complete:
        item["evidence_id"] = ("《%s v0》第 %s 条 @ %s @ %s%s"
                               % (lib, art, anc, str(sha)[:12],
                                  "" if verified else "（**非逐字**：P0 模式自身声明，未经逐字回验）"))
        item["evidence_url"] = "kb/l3/candidates/rules.jsonl#%s" % art
    else:
        item["evidence_gap"] = "引用契约六要素不全（缺 %s）" % ",".join(
            k for k, v in (("库名", lib), ("条款号", art), ("anchor", anc),
                           ("source_sha256", sha), ("逐字摘录", exc)) if not v)
    if not verified:
        item["evidence_gap"] = f.get("evidence_gap") or item.get("evidence_gap") or "未经逐字回验"
    if f.get("merged_articles"):
        item["merged_articles"] = f["merged_articles"]
    return item


def report_memory_payload(res, reg, text, run_id, content_type="text", position="全文"):
    """把 review.py 的结论翻译成 core/report_memory.py 的输入契约。

    字段映射（左=review.py，右=契约）——**只改名不改值**：

      | review.py                    | report_memory 契约            |
      |------------------------------|-------------------------------|
      | state                        | decision（拒答 → NEEDS_INPUT，原值另存 decision_raw） |
      | findings[]                   | risk_items[]                  |
      | findings[].rule_id           | risk_items[].risk_id          |
      | findings[].category + .sub   | risk_items[].risk_type        |
      | findings[].position          | risk_items[].location         |
      | findings[].excerpt           | risk_items[].original_text    |
      | findings[].advice            | risk_items[].suggestion       |
      | findings[].p_level           | risk_items[].priority_tier（**先读 p_level**；P0–P3 四层，见 core/tiering.py）|
      | findings[].confidence        | risk_items[].confidence       |
      | —（新增）                    | review_id / content_id / content_version /
                                       agent_version / rule_version / knowledge_version |
    """
    vb = version_binding(text, reg)
    vb["review_id"] = run_id
    state = res.get("state")
    cov = _coverage_block(content_type)
    ap = reg.get("approvers") or {}

    def _role(key):
        v = ap.get(key) or {}
        return v.get("role") or key

    owners = {"PASS": [_role("pass_signoff")],
              "REVIEW": [_role("review_reviewers")],
              "BLOCK": [_role("block_owner")]}.get(state, [])
    return {
        "review_id": run_id,
        # ★ 2026-10-10：依据侧**不发业务号**（发号要读飞书表）。报告这一格写**指纹**并注明，
        #   免得报告里「内容 ID」是空的（空会让人以为漏跑了一步）。
        #   表行/云文档那两份由发号方写业务号 —— 两者形态不同是**有意的**，且各自写明出处。
        "content_id": vb.get("content_id") or vb.get("content_fingerprint"),
        "content_id_basis": ("指纹（依据侧不发业务号，发号真源 = "
                             "kb/l7/review-engine/core/content_id.py）"),
        "content_type": content_type,
        "content_version": vb["content_version"],
        "content_hash": vb["content_hash"],
        "agent_version": vb["agent_version"],
        "rule_version": vb["rule_version"],
        "knowledge_version": vb["knowledge_version"],
        "version_binding": vb,
        "decision": "NEEDS_INPUT" if state == "拒答" else state,
        "decision_raw": state,               # 原值：review.py 的「拒答」不是四态之一，不改写它
        # confidence 保持 review.py 的粒度（逐条 高/中/低）；本入口**不合成**全局数值置信度，
        # 免得把「依据侧」的定性判断伪装成已标定的概率（裁决侧的数值置信度属 decide()）。
        "confidence": "未标定（本入口逐条给 高/中/低；全局数值置信度属裁决侧）",
        "input_manifest": {"text": text, "sha256": vb["content_hash"],
                           "modality": [content_type]},
        "coverage": cov,
        "risk_items": [_finding_to_risk_item(f, i) for i, f in enumerate(res.get("findings") or [], 1)],
        "issue_count": len(res.get("findings") or []),
        "report_url": res.get("report_path") or None,
        "next_action": _NEXT_ACTION.get(state, ""),
        "next_owners": owners,
        "sla": {},                           # 本入口不做 SLA 计时（sla.py 属裁决侧），留空不编
        "version_gate": {"reviewed_hash": vb["content_hash"], "release_hash": None,
                         "note": "本入口不掌握发布版本；发布/送审版本比对属裁决侧"
                                 "（review_engine.py:115-119），此处不代替它下结论"},
        "decision_trace": {
            "reasons": _decision_reasons(res),
            "confidence_status": "not_calibrated_by_this_entry",
            "evaluated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "decided_by": "kb-content-review/scripts/review.py（依据侧自身分支，:709-715）",
            "note": "本报告不重算结论；三态由上表 decision_raw 原样带出",
            # ★ 2026-10-10：四层命中计数（PRD §6.2/§6.3，目标 12）与置信度分流去向（§6.6，目标 11）。
            #   加这两格的理由：**报告是给人看的那一面**，而在此之前
            #   「命中的是哪一层」「§6.6 分流有没有生效」在报告里都查不到 ——
            #   分层与分流落了地也看不出来。
            "tier_trace": _tier_trace(res),
            "confidence_route": _confidence_flow_note(res),
        },
        "unmet_citation": res.get("unmet_citation") or [],
    }


def write_report_memory(res, reg, text, report_dir, content_type="text", position="全文", apply=True):
    """渲染 + 存档 report_memory 契约的两份产物：`{review_id}.md` / `{review_id}.json`。

    返回 dict（供 --json 消费）；任何一步失败都只警告并返回 None，**不影响主结论与主报告**。
    """
    mod, p = _load_report_memory()
    if mod is None:
        return None
    payload = report_memory_payload(res, reg, text, res["run_id"], content_type, position)
    md = mod.render_markdown(payload)
    if not apply:
        print("[dry-run] report_memory 未落盘。目标：%s/%s.md ＋ .json｜%d 字节"
              % (report_dir, payload["review_id"], len(md.encode("utf-8"))), file=sys.stderr)
        return None
    os.makedirs(report_dir, exist_ok=True)
    try:
        paths = mod.write_report(payload, report_dir)
    except Exception as e:                      # noqa: BLE001
        print("[warn] report_memory 存档失败：%r" % (e,), file=sys.stderr)
        return None
    # ★ report_memory.write_report 用 Path.write_text 写 .md —— 在本机会撞上 l8 已诊断的
    #   「按后缀生效的写封装 → 4096 字节前缀信封」（见本文件上方 _NODE_WRITE_AND_VERIFY 段），
    #   宿主侧 agent/镜像器读到的是信封而不是文本。所以**同一份 md 再走一遍明文通道**，
    #   由 node 写盘并回读断言（write_text_plain 自带 sha 校验）。
    channel = write_text_plain(paths["markdown_path"], md)
    md_bytes = os.path.getsize(paths["markdown_path"])
    json_bytes = os.path.getsize(paths["json_path"])
    print("[review] 报告记忆落盘通道：%s → %s（md %d 字节 ｜ json %d 字节）"
          % (channel, paths["markdown_path"], md_bytes, json_bytes), file=sys.stderr)
    return {
        "renderer": os.path.relpath(p, ROOT),
        "review_id": payload["review_id"],
        "content_version": payload["content_version"],
        "markdown_path": os.path.relpath(paths["markdown_path"], ROOT),
        "json_path": os.path.relpath(paths["json_path"], ROOT),
        "markdown_bytes": md_bytes,
        "json_bytes": json_bytes,
        "channel": channel,
    }


def _write_findings_cache(path, text, payload):
    """把本次依据落成 run 内中间产物，供同一次评审的裁决侧复用（不再跑第二遍本脚本）。

    格式与校验的**唯一真源**是 `kb/l7/review-engine/core/evidence_cache.py`
    —— 写方有两个（本脚本 + `with_kb_evidence.py`），各写一份迟早漂移，
    而漂移的后果是「把 A 文案的依据算到 B 文案上」。
    这里按 ROOT 动态加载；**加载不到只警告、不让评审失败**（缓存是优化，不是前置）。
    """
    import importlib.util
    p = os.path.join(ROOT, "kb", "l7", "review-engine", "core", "evidence_cache.py")
    try:
        spec = importlib.util.spec_from_file_location("evidence_cache", p)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.write_cache(path, text, payload, source=os.path.abspath(__file__))
    except Exception as e:                    # noqa: BLE001
        print("[warn] findings 缓存没写成：%r" % (e,), file=sys.stderr)
        return None


_ALLOWED_ENTRIES = ("with_kb_evidence", "kb_api", "selftest")


def _entry_gate(argv=None):
    """防线1（2026-10-03）：本脚本是**内部引擎**，不再是对外入口。

    为什么加：能出结论的入口原有**两扇** —— `review-engine/core/with_kb_evidence.py`
    （带层前置闸门 + 判定主体闸门 + 自动发布）与本脚本直调，而**闸门只装在前者上**。
    实测（同日 10:04）有会话直调本脚本 ⇒ 产出的报告 `evidence_meta` 是**空的**：
    没有层前置、没有判定主体、没发飞书、也没有 `<run>.review.md`，而结论照样被当结论用。

    口径与全库既有做法一致：**不静默**。要直调就显式声明身份，别让它长得像正常入口。
    """
    ent = os.environ.get("KB_ENTRY") or ""
    if ent in _ALLOWED_ENTRIES:
        return ent
    av = sys.argv[1:] if argv is None else argv
    if "--i-am-the-entry" in av:
        return "direct_declared"
    print("拒跑：本脚本是**内部引擎**，不是对外入口（防线1，2026-10-03）。")
    print("  对外入口 = kb/l7/review-engine/core/with_kb_evidence.py")
    print("    —— 它带：层前置闸门（L4–L7）+ 判定主体闸门（--decision-owner）+ 默认发飞书。")
    print("  直调本脚本只能得到「没层前置、没判定主体、不发飞书」的**裸结论**，不得当评审结论用。")
    print("  确实要直调（隔离测试 / 参考实现）：显式加 `--i-am-the-entry`，或设 KB_ENTRY=selftest。")
    return None


def main():
    global ROOT
    if _entry_gate() is None:
        sys.exit(2)
    ap = argparse.ArgumentParser()
    ap.add_argument("--i-am-the-entry", action="store_true",
                    help="显式声明「我是故意直调内部引擎的」（防线1 的逃生开关；结论带不上闸门痕迹）")
    ap.add_argument("--kb-root", default=None,
                    help="知识库根（含 kb/ 与 l0…l7 那层）；不给就按 KB_ROOT → 已知落点 → 向上查找")
    ap.add_argument("--text")
    ap.add_argument("--file")
    ap.add_argument("--content-type", default="text", choices=["text", "image", "video"])
    ap.add_argument("--position", default=None)
    # 默认 None，**到 main() 里按真正解析出的库根**再算。
    # 原写死 os.path.join(L7, "reports") —— 那个 L7 是**模块级常量**、按脚本自身位置算，
    # 而 --kb-root 要到 parse 之后才生效 → 默认值永远赢，`--kb-root /tmp/xxx` 也照写真库
    # （2026-10-01 实测：拿副本做隔离测试，报告写进了权威库）。改完 --kb-root 与 --report-dir 才自洽。
    ap.add_argument("--report-dir", default=None,
                    help="报告落盘目录；不给就落到**解析出的库根**的 kb/l7/reports（不再按脚本自身位置）")
    ap.add_argument("--run-id", default=None,
                    help="本次运行的编号，用于报告文件名；省略则取当前时间戳（保证逐次唯一，不互相覆盖）")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--top", type=int, default=5)
    ap.add_argument("--dry-run", action="store_true",
                    help="干跑：只打印将写入的报告路径/字节数/前 20 行，不落盘（预演用）")
    ap.add_argument("--apply", action="store_true",
                    help="显式落盘（本脚本默认即落盘；此开关为兼容库内 --apply 约定，语义等价）")
    ap.add_argument("--findings-out", default=None,
                    help="把本次依据落成 run 内缓存（供同一 RUN 的裁决侧 with_kb_evidence.py "
                         "--findings-from 复用，避免同一段文本把本脚本跑两遍）。带文本指纹，用错文本会被拒")
    ap.add_argument("--skip-freshness-gate", action="store_true",
                    help="**跳过 fail-closed 前置**（供给链新鲜度）。只为反测/夹具存在 —— "
                         "**不许用于真实评审**：跳过它等于允许拿陈旧供给链出结论")
    a = ap.parse_args()
    ROOT = _find_root(os.path.dirname(os.path.abspath(__file__)), a.kb_root)
    globals().update({name: os.path.join(ROOT, *rel) for name, rel in {
        "L7": ("kb", "l7"),
        "REG_PATH": ("kb", "l7", "registry", "l7.json"),
        "RULES": ("kb", "l3", "candidates", "rules.jsonl"),
        "MATCHER": ("kb", "l5", "matcher.py"),
        "L6REG": ("kb", "l6", "registry", "l6.json"),
    }.items()})
    # ★ 报告目录在**库根解析之后**才算：--report-dir 显式给了就用它，没给才落到本库根的 l7/reports。
    #   于是 `--kb-root <副本>` 拿副本做隔离测试时，报告也落在副本里，不碰权威库。
    rep_dir = a.report_dir or os.path.join(L7, "reports")

    # ══════════════════════════════════════════════════════════════════════════
    # ★★ 批次19 · 第1块：**fail-closed 前置条件（代码级阻断）** ────────────────────
    # ══════════════════════════════════════════════════════════════════════════
    # 为什么必须在这里、必须是**代码**：
    #   `kb/l7/scripts/freshness.py` 早就判「关键 data 产物超期 ⇒ 应拒答（退出码 3）」，
    #   但那只是**一个脚本的退出码** —— **评审链照样给 PASS/BLOCK**。
    #   而 SKILL.md:96-122 那段「前置条件」**只是文字约束**（给 agent 读的），
    #   **没有任何代码强制** ⇒ 不读正文、或读了不照做，就绕过去了。
    #   ⇒ 本条把它落成**确定性阻断**：判据不通过 → **退出码 3、结论 NEEDS_INPUT、
    #     绝不产出 PASS/BLOCK**。不靠 SKILL.md 文字、不靠 LLM 自觉。
    # 判据只一份，在 `kb/l7/scripts/review_freshness_gate.py`（API 入口调同一个）。
    # ── ★★ 批次20 · 第3块：`--skip-freshness-gate` 后门**代码层收紧** ──────────────
    # 上一批我留了这个开关只为反测，**代码层没拦**，只在 help 里写「不许用于真实评审」——
    #   那是**靠自觉**，与 SKILL.md 那段文字约束是同一个毛病（本库反复栽在这一点上）。
    # 现改为**双条件 + 审计**：
    #   ① 环境变量 `KB_ALLOW_STALE=1`（显式开）；**且**
    #   ② profile 判定为**非生产**（`KB_PROFILE` 缺失或非 `prod*`）。
    #   两条缺一 ⇒ **直接拒绝**（退出码 2）并打印怎么开。
    #   放行时**必写一条审计**到 `kb/l7/registry/stale_gate_bypass.ndjson`，
    #   含 时点 / 使用人 / 原因 / 影响面（被跳过的判据 + 该库当时的新鲜度结论）。
    if a.skip_freshness_gate:
        _env_ok = os.environ.get("KB_ALLOW_STALE") == "1"
        _prof = (os.environ.get("KB_PROFILE") or "").strip().lower()
        _prof_ok = not _prof.startswith("prod")     # 缺省（空）= 非生产 ⇒ 允许
        if not (_env_ok and _prof_ok):
            print("⛔ `--skip-freshness-gate` 被**代码层拒绝**（不是靠自觉）。", file=sys.stderr)
            print("   需要**同时**满足两条才能开：", file=sys.stderr)
            print("     ① 环境变量 KB_ALLOW_STALE=1        （现在：%s）"
                  % ("已设 ✅" if _env_ok else "**未设 ❌**"), file=sys.stderr)
            print("     ② KB_PROFILE 非生产（不以前缀 prod 开头）（现在：%r → %s）"
                  % (_prof, "通过 ✅" if _prof_ok else "**生产 profile ❌**"), file=sys.stderr)
            print("   例：KB_ALLOW_STALE=1 KB_PROFILE=test kb/kbpy <本脚本> --skip-freshness-gate …",
                  file=sys.stderr)
            print("   ★ 放行会**留审计**（kb/l7/registry/stale_gate_bypass.ndjson）。",
                  file=sys.stderr)
            sys.exit(2)
        # 放行 ⇒ 留审计（**先记后跑**：跑挂了也留得下）
        try:
            import json as _json, time as _time, getpass as _getpass
            _aud = os.path.join(ROOT, "kb", "l7", "registry", "stale_gate_bypass.ndjson")
            os.makedirs(os.path.dirname(_aud), exist_ok=True)
            _now = _info_cur = None
            try:
                sys.path.insert(0, os.path.join(ROOT, "kb", "l7", "scripts"))
                import review_freshness_gate as _fg0
                _, _info_cur = _fg0.check(ROOT)
            except Exception:                                # noqa: BLE001
                _info_cur = {"error": "新鲜度结论取不到"}
            with open(_aud, "a", encoding="utf-8") as _fh:
                _fh.write(_json.dumps({
                    "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "actor": os.environ.get("USER") or _getpass.getuser(),
                    "reason": os.environ.get("KB_ALLOW_STALE_REASON") or "**未给原因**",
                    "gate_skipped": "review_freshness_gate.check()（供给链新鲜度前置）",
                    "library_root": ROOT,
                    "kb_profile": _prof or "(unset)",
                    "freshness_at_bypass": {
                        "health": (_info_cur or {}).get("health"),
                        "stale_layers": (_info_cur or {}).get("stale_layers"),
                        "source": (_info_cur or {}).get("source"),
                    },
                    "impact": ("本次评审**未做**供给链新鲜度前置 ⇒ 结论可能基于陈旧供给链，"
                               "**不得当作放行依据**"),
                    "argv_text_sha8": __import__("hashlib").sha256(
                        (a.text or "").encode("utf-8")).hexdigest()[:8] if a.text else None,
                }, ensure_ascii=False) + "\n")
            print("⚠️ 已跳过供给链新鲜度前置；审计 → %s" % _aud, file=sys.stderr)
        except Exception as _e:                              # noqa: BLE001
            print("⛔ 审计写不下（%r）⇒ **拒绝放行**（无审计的绕过不允许）。" % (_e,),
                  file=sys.stderr)
            sys.exit(2)
    else:
        try:
            sys.path.insert(0, os.path.join(ROOT, "kb", "l7", "scripts"))
            import review_freshness_gate as _fg
            _ok, _info = _fg.check(ROOT)
        except Exception as _e:                      # noqa: BLE001
            # ★ fail-closed：判据**跑不起来**也算不通过（「不知道新不新鲜」≠「新鲜」）
            _ok, _info = False, {"reason": "前置判据跑不起来：%r" % (_e,),
                                 "unreadable": True, "stale": [],
                                 "stale_artifacts": {}, "stale_layers": []}
        if not _ok:
            _ref = _fg.refusal_payload(_info) if "_fg" in dir() else {
                "state": "NEEDS_INPUT", "detail": _info.get("reason"),
                "fails_closed": True}
            _ref["trace"] = {"gate": {"file": "kb/l7/scripts/review_freshness_gate.py",
                                      "called_from": "kb-content-review/scripts/review.py main()",
                                      "verdict": "refused"}}
            _ref["findings"] = []
            _ref["unmet_citation"] = []
            _out = {"state": "NEEDS_INPUT", "content": None, "findings": [],
                    "refusal": _ref, "gate": _ref["trace"]["gate"]}
            print("⛔ **评审链拒答（fail-closed）** —— 供给链不新鲜，**不产出 PASS/BLOCK**。",
                  file=sys.stderr)
            print("   原因：%s" % (_info.get("reason") or "（无）"), file=sys.stderr)
            for _s in (_info.get("stale") or []):
                print("   · %s" % _s.get("text"), file=sys.stderr)
            for _L, _arts in (_info.get("stale_artifacts") or {}).items():
                for _art in _arts:
                    print("     %s：`%s` 落后 %s" % (_L, _art.get("file"), _art.get("age")),
                          file=sys.stderr)
            if _info.get("layer_detail"):
                for _d in _info["layer_detail"]:
                    print("     判据：%s" % (str(_d.get("reason"))[:160]), file=sys.stderr)
            if a.json:
                print(json.dumps(_out, ensure_ascii=False, indent=1))
            else:
                print("⛔ 拒答（NEEDS_INPUT）：供给链不新鲜 —— %s"
                      % (_info.get("reason") or ""))
                print("   该跑哪层：见上面逐条 stale 待办里的 owner/command。")
            # ★ 必须是 `sys.exit` 不是 `return 3` —— 实测踩到：
            #   `main()` 的返回值被本文件末尾的裸 `main()` **丢弃**（`:1411`），
            #   写 `return 3` 的话进程退出码仍是 **0**，调用方（含 `with_kb_evidence.py`
            #   的 subprocess）会以为「正常出结论」。**拒答必须是退出码 3**。
            sys.exit(3)                           # ★ 与库内「拒答」退出码一致

    if a.file:
        text = open(a.file, encoding="utf-8").read()
    elif a.text is not None:
        text = a.text
    else:
        text = sys.stdin.read()
    pos = a.position or {"text": "全文", "image": "图片 1（#img.1）", "video": "视频 00:00（时间戳锚点）"}[a.content_type]
    reg = load_registry()
    res = review(text, a.content_type, pos, rep_dir, a.run_id, a.top)
    res["content"] = text
    res["query_words"] = text[:120]
    path = write_report(res, reg, rep_dir, res["run_id"], apply=not a.dry_run) if (len(res["findings"]) >= 3 or a.report_dir) else None
    # ── 接线（2026-10-01 · C 块）：报告与记忆这一跳 ────────────────────────
    # 手册 §五-1 的断点。走 report_memory 的模板/存档契约，产物 `{review_id}.md` + `.json`。
    # 与上面 write_report 的 `<run>.review.md` **并存**：那份是 output_template.md :12 的
    # A4 契约件（完整清单），这份是「审查报告与记忆」的契约件。两边都是原样带出，不改判定。
    rm = write_report_memory(res, reg, text, rep_dir, a.content_type, pos, apply=not a.dry_run)
    rendered = render(res, reg, path)
    out_obj = {**res, "rendered": rendered, "report_path": path, "report_memory": rm}
    if a.findings_out:
        _write_findings_cache(a.findings_out, text, out_obj)
    if a.json:
        print(json.dumps(out_obj, ensure_ascii=False, indent=1))
    else:
        print(rendered)
        print(f"\n---\n检索轨迹摘要：P0 {len(res['trace']['p0']['hits'])} 命中（{res['trace']['p0']['engine_elapsed_ms']} ms）"
              f"｜规则层 {len(res['trace']['rules']['hits'])} 命中｜单元层 BM25 最高 "
              f"{res['trace']['units']['bm25_max']}（门限 {res['trace']['units']['gate']['bm25_raw_min']}）"
              f"｜向量补召 {'启用' if res['trace']['units']['used_vector'] else '未启用'}"
              f"｜无法满足引用契约 {len(res['unmet_citation'])} 条")
        if path:
            print(f"完整清单：{path}")
        if rm:
            print(f"报告记忆（审查报告与记忆契约）：{rm['markdown_path']} ｜ {rm['json_path']}")
        if a.dry_run and not path and not rm:
            print("（--dry-run：报告未落盘；去掉该参数或加 --apply 即落盘）")
    sys.exit(0 if res["state"] in ("PASS", "REVIEW", "BLOCK") else 3)


if __name__ == "__main__":
    main()
