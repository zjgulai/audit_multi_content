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


def history_action_advice_note(action):
    """Describe the provenance of a historical recommendation without inventing disposition."""
    action = action if isinstance(action, dict) else {}
    if action.get("kind") == "replace" and str(action.get("replacement") or "").strip():
        return "取自源记录的建议原文"
    return "源记录未提供具体修改建议；此条仅为相似历史参考，不构成禁止或打回依据"

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
# ★ 2026-10-21：P0 快路的 V01–V06（E-2.124~E-2.129）**不住 rules.jsonl**，
#   它们住在 external_standard.jsonl。只读前者 ⇒ 这些 P0 命中的 finding 变成
#   「未归类 / 无条款号」，判定从 BLOCK 掉成 REVIEW（实测「全美国销量no.1」）。
EXTERNAL_RULES = os.path.join(ROOT, "kb", "l3", "candidates", "external_standard.jsonl")
MATCHER = os.path.join(ROOT, "kb", "l5", "matcher.py")
ADVICE_BOOK = os.path.join(ROOT, "kb", "l5", "advice_book.py")
L6REG = os.path.join(ROOT, "kb", "l6", "registry", "l6.json")


_ADVICE_BOOK = None


def _advice_book():
    """「建议」兜底改法表（唯一来源 = `kb/l5/advice_book.py`）。

    ★ 2026-10-19（Owner：「**必须给建议**」）：改前本条链路的「建议」只有一个来源
      （规则的 `advice` 格），空了就**整行不印**（BLOCK 卡上连「建议」都没有）。
      实测 17 条 P0 模式里 10 条没有原话 ⇒ 那一档的卡上永远看不到改法。
      ⚠️ 加载失败不许静默：回同签名空壳（通用句），原因打 stderr。
    """
    global _ADVICE_BOOK
    if _ADVICE_BOOK is not None:
        return _ADVICE_BOOK
    try:
        import importlib.util as _ilu                          # noqa: PLC0415 —— 本文件既有惯例：惰性加载
        _spec = _ilu.spec_from_file_location("kb_advice_book_review", ADVICE_BOOK)
        _mod = _ilu.module_from_spec(_spec)
        _spec.loader.exec_module(_mod)
        _ADVICE_BOOK = _mod
    except Exception as e:                                   # noqa: BLE001
        print("[advice_book] ⚠ 兜底改法表加载失败 ⇒ 建议降级为通用句：%s" % e, file=sys.stderr)

        class _Empty:
            @staticmethod
            def fallback(rule_code=None, rule_id=None, hits=()):
                return ("删去命中的违规表述后再提交。", "generic_no_book")

        _ADVICE_BOOK = _Empty()
    return _ADVICE_BOOK


def backfill_advice(findings, state):
    """BLOCK 单的「建议」**补进数据**（Owner 2026-10-19「必须给建议」）。

    为什么补在 `review()` 返回前、而不是渲染时：
      同一条 finding 有三处消费者 —— **卡片**（`render()`）、**报告**（`write_report`）、
      **入口 JSON**（`_finding_to_risk_item → suggestion`）。只在渲染层补，就会
      「卡上有建议、报告里那一格空着」，而这正是本库反复栽过的两端不一致。
    ⇒ 在这里补一次，三处读同一格。**已有建议一个字不改**（库内原话优先）；
      补进来的那句记 `advice_source`（`p0_advice_book:<CODE>` / `generic_*`），查得到出处。

    ⚠️ 只补 BLOCK：PRD §5.3.4 的 REVIEW 模板没有逐条「建议」行（改法是 `建议转 @…复核。`），
      给 REVIEW 逐条补建议＝改 PRD 版式。
    """
    if state != "BLOCK":
        return 0
    book = _advice_book()
    n = 0
    for f in findings or []:
        if not isinstance(f, dict) or str(f.get("action") or "").lower() == "advice":
            continue
        if str(f.get("advice") or "").strip():
            continue
        rid = f.get("rule_id")
        # 命中片段：`excerpt` 是逐字命中那段；没有就用 `position` 之外什么都不给（不编）。
        hits = [str(f.get("excerpt") or "").strip()]
        adv, src = book.fallback(rule_code=f.get("rule_code"), rule_id=rid,
                                 hits=[h for h in hits if h])
        if not str(adv or "").strip():
            continue
        f["advice"] = adv
        f["advice_source"] = src
        n += 1
    return n


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
    # ★ 2026-10-21：外部标准规则（V01–V06 / E-2.12x）与措辞库规则合并成一张表。
    #   先读 rules.jsonl（同名 rule_id 以它为准），再补 external_standard.jsonl 里没有的。
    for _path in (RULES, EXTERNAL_RULES):
        if not os.path.exists(_path):
            continue
        for l in open(_path, encoding="utf-8"):
            if l.strip():
                r = json.loads(l)
                if r.get("rule_id"):
                    latest.setdefault(r["rule_id"], r)
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
# ── ★★ 2026-10-17（Owner：「既然分了11类，就要按照11类的出结果」）：11 类归类 ──────────
# 背景（先说清楚它是什么，免得后人当成源字段）：**「所属类别 / 所属子类」不是源表字段，也不是
#   PRD 原文类目** —— 它是 2026-10-16 会话里由助手提出、Owner 采用的一套 11 类分类体系
#   （真源 = `kb/l3/registry/rule-taxonomy.json`，出处与边界登记在它的 `taxonomy_provenance`）。
# 与既有两格的**关系**（三格并存，互不顶替）：
#   · `risk_type`   = `category-sub`（**库内 8 类规则词表**，`l7.json → vocabulary.categories`）
#   · `risk_category` = **PRD §5.3 四维**（合规/消费者安全/产品描述/措辞表达）
#   · `taxonomy_category` / `taxonomy_subcategory` = **本件新增的 11 类 / 58 子类**
# ⇒ 本件**只增不改**：不动 `risk_type`（`review_engine.route_owners()` 拿它做关键词路由，
#   改它 = 静默降级责任人分派，那份改动单里实测 6 条里 3 条会变），也不动 `risk_category`。
_TAXONOMY_FIELDS = ("taxonomy_category", "taxonomy_subcategory")


def taxonomy_index():
    """`rule_id → {taxonomy_category, taxonomy_subcategory, taxonomy_basis}`。**只读**。

    ★ 为什么要把 `external_standard.jsonl` 也读进来：**P0 快路的 17 条里有 6 条是外部标准规则**
      （E-2.124~E-2.129），它们不住 `candidates/rules.jsonl`。只读 rules.jsonl 的话，
      这 6 条命中的 finding 会**永远是「无 11 类」**，而那恰好是最该分类的红线命中。
    ★ 读不到就返回空表（**不抛**）：本格是附加视图，不许因为它把整条评审链拖死；
      空表的后果是报告里写明「未挂 11 类」，可见、不静默。
    """
    idx = {}
    for rel in ("kb/l3/candidates/rules.jsonl", "kb/l3/candidates/external_standard.jsonl"):
        p = os.path.join(ROOT, rel)
        if not os.path.exists(p):
            continue
        try:
            for line in open(p, encoding="utf-8"):
                if not line.strip():
                    continue
                r = json.loads(line)
                rid = r.get("rule_id")
                cat, sub = r.get("taxonomy_category"), r.get("taxonomy_subcategory")
                if rid and (cat or sub):
                    # ★★ 2026-10-20（W-1.57 那次实测）：`taxonomy_basis` 若是**字符串**，
                    #   `(str).get("version")` 抛 AttributeError ⇒ 外层 `except` 把**整份文件的
                    #   后续行**全部跳过 ⇒ 排在后面的规则统统「不在规则表里」、A3 分类恒空。
                    #   实测：1018 行是 dict、我新加的两行写成字符串 ⇒ 只有它们丢分类，
                    #   而症状看起来像「引擎不认识这条规则」。
                    #   ⇒ 两种形状都认；取不到版本就给默认值，**不再因为一格形状打穿整份索引**。
                    _tb = r.get("taxonomy_basis")
                    idx[rid] = {"taxonomy_category": cat, "taxonomy_subcategory": sub,
                                "taxonomy_basis": ((_tb.get("version") if isinstance(_tb, dict) else None)
                                                   or "kb/l3/registry/rule-taxonomy.json")}
        except Exception:                                    # noqa: BLE001
            continue
    return idx


#: A3 的兜底类名（12 类里的第 12 个；真源 `kb/l3/registry/rule-taxonomy.json`）。
TAX_UNCLASSED = "未归类"


def taxonomy_classes():
    """A3 的 12 类**顺序**（真源 = `kb/l3/registry/rule-taxonomy.json` 的 classes）。

    读不到 ⇒ 返回空表（调用方因此只保证「未归类压最后」，**不编一套顺序**）。
    """
    global _TAX_CLASSES
    if _TAX_CLASSES is None:
        _TAX_CLASSES = []
        try:
            with open(os.path.join(ROOT, "kb", "l3", "registry", "rule-taxonomy.json"),
                      encoding="utf-8") as fh:
                reg = json.load(fh)
            _TAX_CLASSES = [str(c.get("name") or "").strip()
                            for c in (reg.get("classes") or []) if str(c.get("name") or "").strip()]
        except Exception as e:                                  # noqa: BLE001
            print("[taxonomy] ⚠ 12 类注册表读不到 ⇒ 汇总顺序退回字典序：%s" % e, file=sys.stderr)
    return _TAX_CLASSES


_TAX_CLASSES = None


def tax_category(f):
    """这一条的**所属类别**（A3 12 类）；盖不到 ⇒ `未归类`（兜底类，**不编**）。"""
    return str((f or {}).get("taxonomy_category") or "").strip() or TAX_UNCLASSED


def tax_label(f):
    """`<所属类别>-<所属子类>`（卡面/报告的逐条标签）；子类没有就只印类别。"""
    cat = tax_category(f)
    sub = str((f or {}).get("taxonomy_subcategory") or "").strip()
    return ("%s-%s" % (cat, sub)) if sub and cat != TAX_UNCLASSED else cat


# ── ★★ 2026-10-20（Owner：「未归类问题：2 个，不属于所属类别12类中的吗？图片提取规则的
#    时候要归类」）────────────────────────────────────────────────────────────────
# 病灶（当真单核过）：案例层 finding（`sc-…` / `S-1.195` / `N-1.337`）由下面 case 分支直接
#   拼出来，**从来不带 `taxonomy_category`**；而 `taxonomy_index()`（本文件上方）只读
#   `rules.jsonl` + `external_standard.jsonl`，案例层两条都不在 ⇒ `stamp_taxonomy()` 把它们
#   记成 missing ⇒ 报告「所属类别」落 `未归类`（实测一张德国社媒贴的图单里 4 条有 2 条如此）。
# ⇒ 修法：**在提取这一层就归类**（Owner 原话「图片提取规则的时候要归类」），映射表唯一真源
#   `kb/l7/registry/case-taxonomy-map.json`（12 类真源仍是 `rule-taxonomy.json`）。
_CASE_TAX_PATH = os.path.join(ROOT, "kb", "l7", "registry", "case-taxonomy-map.json")
_CASE_TAX = None


def case_taxonomy(reason_category):
    """案例「原因分类」→ A3 12 类。**只在案例层用**；映射不到 ⇒ `未归类`（不编）。

    读不到映射表 ⇒ 返回 `(未归类, None, 原因)`，**不抛**：分类是附加视图，
    不许因为它把整条评审链拖死（与 `taxonomy_index()` 同一条口径）。
    """
    global _CASE_TAX
    if _CASE_TAX is None:
        _CASE_TAX = {}
        try:
            with open(_CASE_TAX_PATH, encoding="utf-8") as fh:
                _CASE_TAX = (json.load(fh) or {}).get("map") or {}
        except Exception as e:                                   # noqa: BLE001
            print("[case_taxonomy] ⚠ 映射表读不到 ⇒ 案例层落未归类：%s" % e, file=sys.stderr)
    key = str(reason_category or "").strip()
    row = _CASE_TAX.get(key) or {}
    cat = str(row.get("taxonomy_category") or "").strip()
    if not cat:
        return (TAX_UNCLASSED, None,
                "案例分类 %r 不在 case-taxonomy-map.json 里 ⇒ A3 留空（**不编**）" % key)
    return (cat, None, "kb/l7/registry/case-taxonomy-map.json（Owner 2026-10-20 采用，非 PRD 原文）")


# ── ★★ 2026-10-21（Owner：「能跟飞书表中“原因分类”来对齐吗？归属于12类别」）──────────
# 病灶（实测）：图片类审查报告 22 份 / 92 条里 **87 条落 `未归类`（95%）**，文字类只有 2%。
#   图片单的命中恰恰集中在**负面样本层**（N-02 占 65/85 次引用），而这一层 437/437 条
#   从来没有 `taxonomy_category`，`rule-taxonomy.json` 的 638 条与它们 **rule_id 交集 0**。
# ⇒ 修法与案例层同形：**在提取这一层就归类**（Owner 2026-10-20 原话「图片提取规则的时候要归类」），
#   映射表唯一真源 `kb/l7/registry/negative-taxonomy-map.json`（12 类真源仍是 `rule-taxonomy.json`）。
#   ⚠️ 别按 rule_code 一刀切：N-02「原则性错误」64 条横跨安全场景 / 排版 / 设计方向三类，
#   所以映射表用 `by_code` ＋ `overrides_n02`（逐条读了正文的）＋ `default_n02`（入队复核）三层。
_NEG_TAX_PATH = os.path.join(ROOT, "kb", "l7", "registry", "negative-taxonomy-map.json")
_NEG_TAX = None


def negative_taxonomy(code=None, article_no=None):
    """负面样本规则（`N-1.x`）→ A3 12 类。返回 `(category, basis)`；认不出 ⇒ `(None, None)`。

    优先级：`overrides_n02[article_no]`（逐条读过正文）＞ `by_code[rule_code]` ＞
    `default_n02`（仅 N-02）＞ 认不出。**读不到映射表 ⇒ 不抛**、返回 `(None, None)`：
    分类是附加视图，不许因为它把整条评审链拖死（与 `case_taxonomy()` 同一条口径）。
    """
    global _NEG_TAX
    if _NEG_TAX is None:
        _NEG_TAX = {}
        try:
            with open(_NEG_TAX_PATH, encoding="utf-8") as fh:
                _NEG_TAX = json.load(fh) or {}
        except Exception as e:                                   # noqa: BLE001
            print("[negative_taxonomy] ⚠ 映射表读不到 ⇒ 负面样本层落未归类：%s" % e, file=sys.stderr)
    if not _NEG_TAX:
        return (None, None)
    code = str(code or "").strip()
    art = str(article_no or "").strip()
    row, matched = None, None
    if art:
        row = (_NEG_TAX.get("overrides_n02") or {}).get(art)
        matched = "overrides_n02" if row else None
    if not row and code:
        row = (_NEG_TAX.get("by_code") or {}).get(code)
        matched = "by_code" if row else None
    if not row and code == "N-02":
        row = _NEG_TAX.get("default_n02")
        matched = "default_n02" if row else None
    cat = str((row or {}).get("taxonomy_category") or "").strip()
    if not cat:
        return (None, None)
    return (cat, {"version": str((_NEG_TAX.get("meta") or {}).get("created_at") or ""),
                  "source": "kb/l7/registry/negative-taxonomy-map.json",
                  "matched_by": matched,
                  "confidence": (row or {}).get("confidence") or "high",
                  "why": str((row or {}).get("basis") or "")[:160]})



# ── 案例层「命中片段」清洗 ────────────────────────────────────────────────────
# ★★ 2026-10-20（Owner：「依据文档链接中不要写【问题要点】，字数超过 prd 限制了」）：
#   改前是 `reason_analysis[:120]` —— 那是**整段评审留痕**，开头 `【原则性错误】图片 图1 …`，
#   紧接着 `【问题要点】` 与 `1. … 2. … 3. …`。报告「依据文档链接」那一格把它们全抄了进去
#   （实测 181 字，另把**别人的五条要点**塞进了这一单的依据）。⇒ 现在只取**一条**要点：
#   有 `【问题要点】` 就取它后面第一条；没有就用首句。**逐字不改**，只是切一段，仍可回源。
_RE_CASE_POINT = re.compile(r"【\s*问题要点\s*】")
_RE_CASE_ENUM = re.compile(r"(?:^|[\s。；;：:])\d{1,2}\s*[.、．]\s*")
_RE_CASE_TAG = re.compile(r"【[^】]{0,24}】")

_HISTORY_BY_RECORD = None


def _history_text_value(value):
    """L0 stores text fields as {value, raw_verbatim}; return the source text."""
    if isinstance(value, dict):
        return str(value.get("raw_verbatim") or value.get("value") or "").strip()
    return str(value or "").strip()


def history_case_for_record(record_id):
    """Return the full source-side review analysis/advice for a matched image record.

    Prefer L4's stable case payload. If the source record was not promoted to L4,
    fall back to the read-only L0 record. This is historical context, never a new
    normative rule; callers must retain the record-level attribution.
    """
    rid = str(record_id or "").strip()
    if not rid:
        return {}
    global _HISTORY_BY_RECORD
    if _HISTORY_BY_RECORD is None:
        _HISTORY_BY_RECORD = {}
        p = os.path.join(ROOT, "kb", "l4", "canonical", "sample_case.jsonl")
        try:
            with open(p, encoding="utf-8") as fh:
                for line in fh:
                    if not line.strip():
                        continue
                    try:
                        row = json.loads(line)
                    except Exception:
                        continue
                    source_id = str(row.get("resource_id") or "").split("__")[-1]
                    if not source_id:
                        continue
                    old = _HISTORY_BY_RECORD.get(source_id)
                    # Stable canonical rows win; otherwise retain the first source-linked row.
                    if old is None or (row.get("status") == "stable" and old.get("status") != "stable"):
                        _HISTORY_BY_RECORD[source_id] = {
                            "analysis": str(row.get("reason_analysis") or "").strip(),
                            "advice": str(row.get("advice") or "").strip(),
                            "article_no": row.get("article_no"),
                            "status": row.get("status"),
                        }
        except OSError:
            pass
    cached = dict(_HISTORY_BY_RECORD.get(rid) or {})
    # L4 does not yet contain every source case. Read the exact L0 row for the
    # Also fill individual empty fields from L0: a canonical case can preserve
    # the analysis while its advice field is blank even when L0 has a suggestion.
    source = {}
    paths = glob.glob(os.path.join(ROOT, "kb", "l0", "records", "*", rid + ".json"))
    for path in paths:
        try:
            with open(path, encoding="utf-8") as fh:
                row = json.load(fh)
            fields = row.get("fields") or {}
            analysis = _history_text_value(fields.get("具体原因/分析"))
            advice = _history_text_value(fields.get("建议"))
            if analysis or advice:
                source = {"analysis": analysis, "advice": advice,
                          "article_no": None, "status": "L0 source"}
                break
        except (OSError, ValueError):
            continue
    if source:
        return {**source, **{k: v for k, v in cached.items() if v}}
    return cached


def case_excerpt(case, limit=60):
    """案例层的「命中片段」：**一条**要点，去 `【问题要点】` 标记与序号，≤ limit 字。

    返回空串表示这条案例正文里没有可用片段（调用方据此如实说「来源未给引文」，
    不许拿 reason 顶上去 —— 那等于把两格合成一格）。
    """
    raw = str((case or {}).get("reason_analysis") or (case or {}).get("sample_body") or "").strip()
    if not raw:
        return ""
    tail = raw.split("【问题要点】", 1)[1] if "【问题要点】" in raw else raw
    parts = [p.strip() for p in re.split(r"\n|(?=\s?\d{1,2}\s*[.、．])", tail) if p.strip()]
    # ⚠️ 取**最长**那条而不是第一条：实测 S-1.195 的第一条要点是
    #    「【终审-@吴礼芳 】麻烦看看呀」（@某人 + 客套），真正说的是第二/三条
    #    （「图1: 不同族裔的妈妈们…」）。取第一条等于把客套当命中片段。
    cands = []
    for p in parts:
        q = _RE_CASE_TAG.sub("", _RE_CASE_ENUM.sub(" ", p)).strip(" ：:；;，,")
        if len(q) >= 6:                       # 太短的（「麻烦了」）不算要点
            cands.append(q)
    point = max(cands, key=len) if cands else ""
    if len(point) > limit:
        cut = point[:limit]
        for sep in ("。", "；", ";", "，", ","):
            j = cut.rfind(sep)
            if j >= 10:
                cut = cut[:j]
                break
        point = cut.strip()
    return point


def stamp_taxonomy(findings, idx):
    """把 11 类盖到每条 finding 上；**盖不到就留空并写明原因，不编**。

    返回 `{stamped, missing}`（missing = 没有 11 类的条数，报告里要显式写出来）。
    盖不到的两种来路（都如实标）：
      · `rule_id` 不在规则表里 —— 典型是**反例/案例层**（`sc-…`，住 l4 canonical）；
      · 该规则行本身没有 11 类（本批 638 条都有，将来新增源可能没有）。
    """
    st = {"stamped": 0, "missing": 0}
    for f in findings or []:
        if not isinstance(f, dict):
            continue
        t = idx.get(f.get("rule_id") or "")
        if t:
            f["taxonomy_category"] = t["taxonomy_category"]
            f["taxonomy_subcategory"] = t["taxonomy_subcategory"]
            f["taxonomy_basis"] = t["taxonomy_basis"]
            st["stamped"] += 1
        elif str(f.get("taxonomy_category") or "").strip():
            # ★★ 2026-10-20：**条目自己已经带了分类**（案例层，见 `case_taxonomy()`）——
            #   这里不许把它抹成 None。改前这一支是无条件 `= None`，
            #   于是案例层刚归好的类在这一步又被打回「未归类」（一条链上两个写者打架）。
            st["stamped"] += 1
        else:
            f["taxonomy_category"] = None
            f["taxonomy_subcategory"] = None
            f["taxonomy_basis"] = ("该命中不在规则表里（如反例/案例层 sc-… 或覆盖缺口）"
                                   "⇒ 11 类留空，**不编**")
            st["missing"] += 1
    return st


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
                         # ★★ 2026-10-20（W-1.57 品牌写法那次）：**把分类随命中一起带出去**。
                         #   病灶：`layer_rules` 返回的 hit 里没有 taxonomy 两格 ⇒ 引擎从 trace 造
                         #   risk_item 时 `f.get("taxonomy_category")` 恒 None ⇒ 报告写「该命中不在
                         #   规则表里」，而规则行里明明带着 `品牌信任与声誉`。规则自带的分类不许丢。
                         "taxonomy_category": r.get("taxonomy_category"),
                         "taxonomy_subcategory": r.get("taxonomy_subcategory"),
                         "p_level": r.get("p_level"), "risk_level": r.get("risk_level"),
                         "authority": r.get("authority"), "kb_type": r.get("kb_type"),
                         "authority_source_table": r.get("authority_source_table"),
                         "matched_fragments": matched[:8], "anchor": r.get("anchor"),
                         "source_sha256": (r.get("evidence_units") or [{}])[0].get("source_sha256"),
                         "rule_text": r.get("rule_text"), "suggested_replacement": r.get("suggested_replacement")})
    return {"engine": "kb/l3/candidates/rules.jsonl", "kb_type_filter": kb_type,
            "rules_scanned": len(rules), "hits": hits}


# ---------------- 第 2b 层：负面样本规则（N-1.x，2026-10-20 加） ----------------
def layer_negative_rules(text, scene=None, top=3, min_score=0.45, require_visual=False):
    """按「图内文字 + 画面读数」检索**负面样本规则**（`kb/l3/candidates/negative_rules.jsonl`）。

    为什么单开一层、不并进 `rules.jsonl`：
      · `rules.jsonl` 由 L3 蒸馏**整文件覆盖写**（`l3_distill_run.py`）⇒ 手工追加进去，
        下一次日更会被原样抹掉；
      · 两类规则的形态也不同：那边是「禁用片段逐字命中」，这边是「画面线索 + 图内文字近似」。
    ⇒ 独立语料 + 独立层，**不动**既有规则层一个字；读不到就返回空（不抛、不拖死评审）。

    口径（与 `kb/l8/negative_rule_match.py` 同源）：
      · 命中一律 `REVIEW`（历史审核意见，**不是**判定），`p_level=P2`；
      · 分数与命中理由原样带出（画面/文字两路分列），并给 `matched_images` 供人回看。

    ★★ 2026-10-20（真单事故：图片单的报告里出现「1.挂式衣架: 磨砂亚克力材质…」——
      图里根本没有衣架）：
      `require_visual=True` 时**只留"真的对上了这张图"的命中**：
        · `match_rank >= 2`（同图指纹：图内文字逐字相等/包含），或
        · `visual_score >= 0.30`（画面线索对上了）
      理由：不带这两条的命中，读数是「仅文字相近、画面 0.00」——中文审核意见与英文素材的
      字符二元组偶然重叠（同品牌名 `momcozy` 就够）就能过 0.45 的线，
      **画面完全无关也会进清单**，而报告会把它印成"这张图命中了某某条款"。
      ⚠️ 只对**图片/视频类**素材启用（`require_visual=True` 由调用方按素材形态给）：
        纯文案单没有画面读数，按这条过滤会把整层清空。
      ⚠️ 被过滤的**不静默丢**：条数写进 `dropped_text_only`，报告/留底查得到。
    """
    p = globals().get("NEG_RULES") or os.path.join(ROOT, "kb", "l3", "candidates", "negative_rules.jsonl")
    if not os.path.exists(p):
        return {"engine": "kb/l3/candidates/negative_rules.jsonl", "hits": [], "missing": True,
                "note": "负面样本规则语料不存在（未蒸馏或未落盘）"}
    try:
        sys.path.insert(0, os.path.join(ROOT, "kb", "l8"))
        import negative_rule_match as _N          # noqa: E402
        rules = _N.load_rules(p)
        hits = _N.match(text, scene, top=top, min_score=min_score, rules=rules)
        dropped = []
        if require_visual:
            keep = []
            for h in hits:
                rank = int(h.get("match_rank") or 0)
                vis = float(h.get("visual_score") or 0)
                if rank >= 2 or vis >= 0.30:
                    keep.append(h)
                else:
                    dropped.append({"article_no": h.get("article_no"),
                                    "score": h.get("score"), "visual_score": vis,
                                    "why": "仅文字相近（画面未对上，也不是同图指纹）"})
            hits = keep
        return {"engine": "kb/l3/candidates/negative_rules.jsonl",
                "rules_scanned": len(rules), "hits": hits,
                "require_visual": bool(require_visual),
                "dropped_text_only": dropped}
    except Exception as e:                         # noqa: BLE001 — 附加层不许拖死评审
        return {"engine": "kb/l3/candidates/negative_rules.jsonl", "hits": [],
                "error": "%s: %s" % (type(e).__name__, e)}



# ---------------- 第 2c 层：图身份（pHash + 像素相关；2026-10-21） ----------------
# 为什么单开一层：送审图经飞书重压缩（图字节 sha 变了）、两套 OCR 读法不同（变音符号丢失 /
# 水印行 / 错字），文本与字节 sha 都会失效。图对图（pHash + 像素相关）是同一把尺子：
# 实测同一张图重压缩后相关 ≥0.9988、本单真实附件 0.962；画面不同的图 ≤0.31。
# 命中 ⇒ 取该库内图挂的规则（N-1.x）⇒ REVIEW（历史审核意见；与本库既有口径一致）。
# 边界：本层**不判合规**，只回答「这张图是不是库内某张负面样本图」。
_IDX_CACHE = {"path": None, "rows": None}
_NEGR_CACHE = {"path": None, "rules": None}
_ROLES_CACHE = {"path": None, "roles": None}


def _fp_index():
    p = os.path.join(ROOT, "kb", "l3", "candidates", "negative_image_fp.jsonl")
    if _IDX_CACHE["path"] == p and _IDX_CACHE["rows"] is not None:
        return _IDX_CACHE["rows"]
    rows = None
    if os.path.exists(p):
        try:
            rows = []
            for line in open(p, encoding="utf-8"):
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
        except Exception:
            rows = None
    _IDX_CACHE.update(path=p, rows=rows)
    return rows


def _neg_rules_by_id():
    p = globals().get("NEG_RULES") or os.path.join(ROOT, "kb", "l3", "candidates", "negative_rules.jsonl")
    if _NEGR_CACHE["path"] == p and _NEGR_CACHE["rules"] is not None:
        return _NEGR_CACHE["rules"]
    out = {}
    if os.path.exists(p):
        try:
            for line in open(p, encoding="utf-8"):
                line = line.strip()
                if not line:
                    continue
                r = json.loads(line)
                rid = r.get("rule_id") or r.get("article_no")
                if rid:
                    out[rid] = r
        except Exception:
            out = {}
    _NEGR_CACHE.update(path=p, rules=out)
    return out


def _image_roles():
    p = os.path.join(ROOT, "kb", "l3", "registry", "image_roles.json")
    if _ROLES_CACHE["path"] == p and _ROLES_CACHE["roles"] is not None:
        return _ROLES_CACHE["roles"]
    roles = {"records": {}, "sha": {}, "missing": True}
    if os.path.exists(p):
        try:
            roles = json.load(open(p, encoding="utf-8"))
        except Exception:
            pass
    _ROLES_CACHE.update(path=p, roles=roles)
    return roles


def _role_of(record_id, sha):
    roles = _image_roles()
    if roles.get("missing"):
        return "no_roles_artifact", "image_roles.json 缺件（不门控，按 record 归属）"
    p = (roles.get("records") or {}).get(record_id) or {}
    for im in (p.get("images") or []):
        if sha and (im.get("sha256") or "").lower() == str(sha).lower():
            return im.get("role") or "unknown", im.get("why") or ""
    if sha and (roles.get("sha") or {}).get(sha):
        return roles["sha"][sha], "按 sha 索引取角色"
    return "unknown", "该记录/该图不在 image_roles 产物里（没有媒体台账 sha）"


def _phash_path(path):
    """返回 (56bit int, PIL image)；PIL/numpy 不可用或图读不出 ⇒ (None, None)。"""
    try:
        from PIL import Image
        import numpy as np
        Image.MAX_IMAGE_PIXELS = None
        im = Image.open(path).convert("RGB")
        w, h = im.size
        f = max(1, min(w, h) // 128)
        if f > 1:
            im = im.reduce(f)
        g = im.convert("L").resize((32, 32), Image.LANCZOS)
        a = np.asarray(g, dtype=float)
        d = np.fft.rfft2(a)[:8, :8][1:, :]
        med = np.median(d)
        n = 0
        for b in (d > med).flatten():
            n = (n << 1) | (1 if b else 0)
        return n, im
    except Exception:
        return None, None


def _corr(im_a, im_b, s=96):
    try:
        from PIL import Image
        import numpy as np
        a = np.asarray(im_a.convert("L").resize((s, s), Image.LANCZOS), dtype=float).flatten()
        b = np.asarray(im_b.convert("L").resize((s, s), Image.LANCZOS), dtype=float).flatten()
        a = a - a.mean()
        b = b - b.mean()
        with np.errstate(all="ignore"):
            aa = float(a @ a)
            bb = float(b @ b)
            den = (aa ** 0.5) * (bb ** 0.5) if aa > 0 and bb > 0 else 0.0
            return float(a @ b / den) if den > 1e-12 else 0.0
    except Exception:
        return None


def layer_image_identity(image_paths, top=3, max_hamming=10, min_corr=0.90):
    """图身份层：按**图对图**认「这张图是不是库内某张负面样本图」。

    @param image_paths  送审图的本地文件路径（守衡已下载；可多张）
    @returns {engine, checked, hits, candidates, error}
    命中 hit 的形状与 `layer_negative_rules` 一致（下游 findings 装配不用改）；
    `match_rank=4` 表示「图身份」（字节 sha 那一档是 4，逐字/短语是 2/3）。
    """
    out = {"engine": "kb/l3/candidates/negative_image_fp.jsonl", "checked": 0,
           "hits": [], "candidates": [], "error": None}
    paths = [p for p in (image_paths or []) if p]
    if not paths:
        return out
    idx = _fp_index()
    if idx is None:
        out["missing"] = True
        out["error"] = "索引缺件（跑 kb/l8/build_negative_image_fp.py 重建）"
        return out
    rules = _neg_rules_by_id()
    seen = set()
    for p in paths:
        if not os.path.exists(p):
            out.setdefault("missing_files", []).append(p)
            continue
        nq, imq = _phash_path(p)
        if nq is None or imq is None:
            out.setdefault("unreadable", []).append(p)
            continue
        out["checked"] += 1
        cand = []
        for r in idx:
            try:
                d = bin(nq ^ int(r.get("phash") or "0", 16)).count("1")
            except Exception:
                continue
            if d <= max_hamming:
                cand.append((d, r))
        cand.sort(key=lambda x: x[0])
        out["candidates"].append({"image": p, "n": len(cand),
                                  "top": [{"record_id": r.get("record_id"), "seq": r.get("seq"),
                                           "hamming": d} for d, r in cand[:5]]})
        matched = []
        for d, r in cand:
            libp = os.path.join(ROOT, "kb", r.get("path") or "")
            conf = None
            if os.path.exists(libp):
                try:
                    from PIL import Image
                    Image.MAX_IMAGE_PIXELS = None
                    lib = Image.open(libp).convert("RGB")
                    conf = _corr(imq, lib)
                except Exception:
                    conf = None
            if conf is not None and conf >= min_corr:
                matched.append((d, r, conf))
            elif conf is None and d <= 4:
                matched.append((d, r, None))
        # 同图多记录（169 个 sha 对 339 张图）：同内容的副本都要算进来，否则可能漏掉
        # 「用户真正发的那条记录」的规则。上限放宽到 10（按 pHash 距离排序）。
        for d, r, conf in matched[:max(top, 10)]:
            rid = r.get("record_id")
            sha = r.get("sha256")
            for rule_id in (r.get("rule_ids") or []):
                key = (rule_id, rid, sha)
                if key in seen:
                    continue
                seen.add(key)
                rule = rules.get(rule_id)
                if not rule:
                    continue
                ev = (rule.get("evidence_units") or [{}])[0]
                anchor = ev.get("anchor")
                role, why = _role_of(rid, sha)
                out["hits"].append({
                    "article_no": rule.get("article_no"), "rule_id": rule_id,
                    "rule_code": rule.get("rule_code"),
                    "rule_code_label": rule.get("rule_code_label"),
                    "rule_kind": rule.get("rule_kind"),
                    "confidence": rule.get("confidence"),
                    "rule_text": rule.get("rule_text") or "",
                    "action": rule.get("action") or {},
                    "score": 1.0, "visual_score": 1.0, "text_score": 0.0,
                    "why": "图身份：与库内图同一张（pHash 距离 %d%s）"
                           % (d, "" if conf is None else " ｜ 像素相关 %.3f" % conf),
                    "reasons": ["图身份：同一张图（%s seq=%s，pHash 距离 %d%s）"
                                % (rid, r.get("seq"), d,
                                   "" if conf is None else "，相关 %.3f" % conf)],
                    "image_refs": [im.get("file_token") for im in (rule.get("image_refs") or [])][:5],
                    "evidence": [{"anchor": anchor, "source_sha256": ev.get("source_sha256"),
                                  "record_id": rid}],
                    "library_negative_sample": True,
                    "matched_by": "图身份",
                    "record_id": rid,
                    "matched_image": {"record_id": rid, "sha256": sha,
                                      "file_token": r.get("file_token"),
                                      "anchor": "#素材/%s/图片素材/#img.%s" % (rid, r.get("seq"))},
                    "attribution": role,
                    "attribution_why": why,
                    "match_rank": 4,
                    "identity": True,
                    "evidence_gap": "图身份：与库内图同一张（pHash/像素相关），不是本单素材的逐字命中",
                })
    return out


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



def rule_cited_anchor_shas(rules):
    """「被引用锚点」→ 该锚点**所在单元**的 `source_sha256` 集合（**同源校验**用，2026-10-23）。

    ## 为什么需要（实测 2026-10-23，回归集逼出来的）

    L2 的锚点里有**位置型**写法：`#l.1-1` / `#l.1-506` / `#h.<小标题>` —— 它们不是记录身份，
    而是「某页的第 n 个列表项 / 某个小标题」。实测 `kb/l2/units.jsonl` 里 `#l.1-1` 被 **921**
    个单元共用。

    `rule_cited_anchors()` 只比锚点**名字** ⇒ 谁的名字撞上，就算「被规则引用过」。
    2026-10-21 把 `kb/l3/candidates/external_standard.jsonl` 并进 `rules`（那条改动本身是为了让
    V01–V06 / E-2.12x 能被规则层命中）之后，这些规则的**位置型**锚点也进了覆盖池 ⇒ 检索命中的
    单元只要**同名**（哪怕完全是另一份文档）覆盖判据就成立。

    实测代价（回归集 5 条同形）：素材是 AAP 技术报告开头，命中的却是 `uk.momcozy.com` 商品页
    （同锚点 `#l.1-1`，BM25 118.3 / 37.2）⇒ `covered_by=rule` ⇒ 三态从 REVIEW 翻成 **PASS**。
    方向是 **fail-open**（该转人工的放过去了），比漏判更坏。

    ## 判据（**只收窄，不放宽**）

    「被规则引用过」= **锚点相同 且 `source_sha256` 相同**（同一份文档里的同一个锚点）。
    实测 965 个被引锚点在 L2 都有单元、且 sha **逐条一致**（965/965）⇒ 这条收窄对本该认的
    命中**零影响**；记录型锚点（`#广告文案明细/recv…/命中片段`）带记录 id、天然唯一，行为不变。
    取不到 sha 的规则单元**不进池**（保守一侧：宁可判「没覆盖」转人工，也不许放成 PASS）。
    """
    out = {}
    for r in rules.values():
        for u in list(r.get("evidence_units") or []) + [r]:
            if not isinstance(u, dict):
                continue
            a, s = u.get("anchor"), u.get("source_sha256")
            if a and s:
                out.setdefault(a, set()).add(s)
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


_POSITIONAL_ANCHOR_RE = re.compile(r"^#[lh]\.\d")


def anchor_has_identity(a):
    """锚点是否**带身份**（能唯一指回一份文档）—— 判「同源」的前提。

    `#l.1-1` / `#l.1-506` / `#h.<小标题>` 是**页面位置**，不是记录身份：实测 `#l.1-1`
    在 `kb/l2/units.jsonl` 里被 **921** 个单元共用（来自几百份不同的网页）。拿这种锚点去
    `resources_of_anchors()` 回表，取到的是**扫到的第一条**那份文档 —— 与本次素材无关。

    实测代价（2026-10-23，回归集 RC-2694cc2ea7e0 德语文案）：命中锚点 `#l.1-3`，
    回表取到 `support.google.com/adspolicy` 的 resource_id，而那条 resource 在被引池里
    ⇒ 判成「同源」⇒ 覆盖成立 ⇒ 三态从 REVIEW 翻 **PASS**。

    ⇒ 同源支路只认带记录 id 的锚点（`#<表>/rec…/<字段>`、`#素材/rec…/…`）。
      同一份文档的命中不会因此丢：那条路由 `direct`（锚点 + `source_sha256`）兜着。
    """
    return bool(a) and not _POSITIONAL_ANCHOR_RE.match(str(a))


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
                   resources_of=None, case_anchors=None, case_resources=None,
                   cited_shas=None):
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
    # ★★ 2026-10-23：**锚点同名 ≠ 同源**。位置型锚点（`#l.1-1` 被 921 个单元共用）名字到处撞，
    #   只比锚点 ⇒ 命中**别的文档**的同名单元也算「被规则引用」⇒ 覆盖成立 ⇒ REVIEW 翻 PASS
    #   （实测 5 条）。`cited_shas` 给了就要求 **锚点相同 且 source_sha256 相同**；
    #   不给（老调用方 / 自证）行为一个字不变。
    def _cite_ok(_r):
        _a = _r.get("anchor")
        if _a not in cited:
            return False
        if cited_shas is None:
            return True
        _s = _r.get("source_sha256")
        return bool(_s) and _s in (cited_shas.get(_a) or set())

    direct = [r for r in unit_rows
              if _cite_ok(r) and (r.get("raw_bm25") or 0) >= cov_thr]
    strong = [r for r in unit_rows if (r.get("raw_bm25") or 0) >= cov_thr]
    rmap = resources_of([r.get("anchor") for r in strong]) if strong else {}
    same = []
    if not direct and cited_res and rmap:
        # ★ 2026-10-23：**位置型锚点判不了「同源」**（见 `anchor_has_identity`）——
        #   `#l.1-3` 这种锚点回表取到的是「扫到的第一份文档」，与本次素材无关。
        same = [r for r in strong
                if anchor_has_identity(r["anchor"])
                and rmap.get(r["anchor"]) and rmap[r["anchor"]] in cited_res]
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


def _attribution_of(hit):
    """命中的**图片归属角色**（2026-10-20「串图」修复 ②）。

    只有 `subject` 才允许把这条历史意见当成「**这张图**的依据」；其余一律只作线索。

    两个轴别混（都成立才算依据）：
      · `figure_attribution`（self_negative 收窄层）= 规则正文讲的是**不是这张图**（figure/record）；
      · **图片角色**（本函数）= 这张库内图在那条记录里**是不是被审对象**
        （`subject` / `record_level` / `shared_reference` / `unknown`）。
    角色判定真源 = `kb/l3/registry/image_roles.json`（由 `kb/l8/image_roles.py` 生成；判据在
    那个文件头：单图 ∧ 该图未出现在内容不同的其它记录里 ⇒ subject）。本函数只做**翻译**，
    不自己算判据 —— 判据散成两处必然走样。

    · 匹配层（negative_rule_match）已在 hit 里算好 `attribution` ⇒ 直接用；
    · 自命中层（self_negative：`library_negative_sample`）的 hit 只有 record_id
      ⇒ 按**记录**角色代理（记录里有 subject 图才算 subject）；
    · 产物缺失 ⇒ `no_roles_artifact`：**不门控**（抑制装置缺件就停用，别静默把整层清空）。
    """
    a = hit.get("attribution")           # 匹配层算好的图片角色
    if a:
        return a
    root = globals().get("ROOT")
    if not root:
        return "no_roles_artifact"
    p = os.path.join(root, "kb", "l3", "registry", "image_roles.json")
    if not os.path.exists(p):
        return "no_roles_artifact"
    try:
        sys.path.insert(0, os.path.join(root, "kb"))
        import importlib.util as _ilu
        _spec = _ilu.spec_from_file_location(
            "_kb_image_roles_review", os.path.join(root, "kb", "l8", "image_roles.py"))
        _m = _ilu.module_from_spec(_spec)
        _spec.loader.exec_module(_m)
        roles = _m.load_roles(p)
        rid = ((hit.get("evidence") or [{}])[0] or {}).get("record_id") or hit.get("record_id")
        return _m.role_of_record(roles, rid) if rid else "unknown"
    except Exception:                              # noqa: BLE001 —— 归属算不出来不许拖死评审
        return "unknown"


def _load_self_negative():
    """加载「本素材**就是**库里某条负面样本的取证图」这一层（`core/self_negative.py`）。

    与 `_load_case_theme()` **同一个理由**：本脚本 import 时就会把整条引擎跑起来
    （模块级解析 sys.argv 并执行）⇒ 逻辑内联在这里就**测不了**。
    抽成可导入模块后，`python3 kb/l7/review-engine/core/self_negative.py --selftest`
    才能拿正例与反向对照各跑一遍。一份实现，两边共用。
    """
    import importlib.util as _ilu
    _p = os.path.join(ROOT, "kb", "l7", "review-engine", "core", "self_negative.py")
    _spec = _ilu.spec_from_file_location("self_negative", _p)
    _m = _ilu.module_from_spec(_spec)
    _spec.loader.exec_module(_m)
    return _m


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
    rows = []
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                try:
                    rows.append(json.loads(line))
                except Exception:                              # noqa: BLE001
                    continue
    except OSError:
        return []                    # 读不到 ⇒ 空 ⇒ 覆盖判据退回原样（保守一侧，不静默放宽）

    # ── ★★ 2026-10-20：**先折叠成一个条款号一行（取最后一行），再过滤** ────────────
    #   与 `kb/l7/scripts/l4_gate.py::read_last_per_key` 同一条口径
    #   （闸门侧原文：「退役是另起一行，原行逐字节不动」）。
    #   为什么顺序必须是这样（上一版踩过）：退役行是被**追加**在文件末尾的，
    #   若先按 status 过滤再折叠，退役行被滤掉、剩下的**原行（anchor 已死）**反而留了下来
    #   ⇒ 退役在引擎侧等于没生效。实测背景：2026-10-20 有 20 条 `#正面和负面样本/recvw2…`
    #   的源记录随飞书表重建作废，且退役行与原行**同时存在**。
    _folded, _order = {}, []
    for _d in rows:
        _k = str(_d.get("article_no") or "").strip() or ("#%d" % len(_order))
        if _k not in _folded:
            _order.append(_k)
        _folded[_k] = _d
    rows = [_folded[k] for k in _order]

    out = []
    for d in rows:
        # ── 已销号 / 已退役的条款**不许再当依据**（销号口径 2026-10-14 加；退役 2026-10-20 补）
        #   为什么非加不可：销号只写标记（`status=superseded` ＋ `superseded_by`），
        #   而本函数原先**不读 `status`** ⇒ 被销的号照样进池、照样被引用 ——
        #   而**被销那一侧的 anchor 是死的**（旧代 `#正面和负面样本/recvw2…`，
        #   实测 201 个 record **0 个**还在）⇒ 引擎会继续产出**点不开的直链**。
        #   换句话说：**不加这一条，销号/退役在引擎侧等于没生效（只是化妆）。**
        #   边界：只挡「产出依据」这一路；覆盖池用的是**存活的孪生号**
        #   （实测 61 个被销号**全部**有孪生号在池子里 ⇒ 覆盖不受损）。
        if str(d.get("status") or "").strip().lower() in ("superseded", "retired"):
            continue
        if d.get("polarity") != "反例":
            continue
        rc = str(d.get("reason_category") or "").strip()
        if not rc or rc.lower() == "unknown":
            continue
        if not d.get("anchor"):
            continue
        out.append(d)
    return out


#: 「图上文字」外壳 → 块内正文。三种外壳都认（守衡 / 引擎自己 / 早期写法）。
#: ★ 为什么必须认这些外壳：`buildImageBlock` 的产出长这样
#:   `【图 1 内文字｜4 行】\n<body>\n【/图 1】`；而引擎把它并进素材文本后又会再包一层
#:   `【图内文字（本机 OCR，逐字，可能误识、也可能读不全）】\n<body>`。
_IMG_TEXT_PATTERNS = (
    re.compile(r"【图\s*\d*\s*内文字[^】]*】\s*\n(.*?)(?:\n\s*【/图\s*\d*\s*】)", re.S),
    re.compile(r"【图片\s*\d+\s*的图内文字[^】]*】\s*\n(.*?)(?=\n\s*【)", re.S),
    re.compile(r"【图内文字[^】]*】\s*\n(.*?)(?=\n\s*【|\Z)", re.S),
)


def image_text_blocks(text, max_blocks=3, max_chars=2000):
    """从素材文本里抽出「图上文字」块（去重、限量）—— 供**单独再查一次**。

    ## 为什么（2026-10-20 实测，MOMCOZY 图 1）

    素材文本一半是 **4 行英文 OCR（`MOMCOZY / Evolving for / mom and cozy / M0m222`）**、
    一半是**中文画面读数**（影棚 / 无人物 / 物品…）。`layer_units` 原先只拿**整段**查一次，
    而 BM25 分**中英两个子索引各算各的**、原始分不可比：
      · 中文那路 rank1 = 368.095（`#l.1-2`，无关长文档）
      · 英文那路里真正同源的那条 = **46.367**（`#负面样本/recvw7XIUgFaLV/具体原因/分析`）
    ⇒ 按原始分混排后英文那路被整体挤出 top5 ⇒ 覆盖判据 `rule_cited_unit_hits=0`
      ⇒ 判成 `coverage_not_covered` 拒答。**库其实认识这张图**（该单元正被 L4 条款 N-1.185 取证）。

    ⇒ 图上文字是**区分度最高的那段**，必须**单独再查一次**，并把结果与主查询**按排名融合**
      （不是按原始分相加 —— 见 `layer_units` 里的 RRF）。
    """
    out = []
    for pat in _IMG_TEXT_PATTERNS:
        for m in pat.finditer(text or ""):
            body = re.sub(r"^\s*【[^】]*】\s*", "", (m.group(1) or "").strip()).strip()
            if len(body) < 4 or body in out:
                continue
            out.append(body[:max_chars])
            if len(out) >= max_blocks:
                return out
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
    _env = os.environ.get("KB_IMG_TEXT_RECALL", "").strip().lower()
    # ★★ 收窄（2026-10-20，回归实测后改）：**只有素材里真带「图上文字」块时才走新路径**。
    #   第一版把 RRF 用到了所有素材 ⇒ 回归集 solid 80 条里 **9 条三态漂移**
    #   （其中 5 条 REVIEW→PASS，属 fail-open 方向）—— 那是"顺手改了别的素材的召回"，
    #   与 Owner 的「不影响工作流」直接冲突。纯文字单必须**逐字保持老口径**。
    _blocks = [] if _env in ("off", "0", "false", "no") else image_text_blocks(text)
    if not _blocks:
        # ── **老路径**（2026-10-20 之前的行为），只给反向对照 / 紧急回退用 ──────────
        #   口径：分语言各取 top-k → 按**原始分**混排 → 取 top。
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
        _legacy = True
    else:
        _legacy = False
    # ★★ 2026-10-20（Owner 批准 B）：主查询 ＋ 每个「图上文字」块各查一次，**按排名融合（RRF）**。
    #   为什么不按原始分：`bm.search()` 返回的是**中/英两个子索引各自的原始分**，而两个子索引的
    #   N / avgdl 不同 ⇒ 原始分**不可比**。原先 `raw.sort(key=-raw_bm25)` 等于让中文那一路
    #   无条件压过英文那一路（实测 368 vs 46）。RRF 只看**各自的名次**，天然免疫这个不可比。
    #   口径与 L6 自己的 BM25×向量融合一致（`retriever.py`：RRF k=60），没有新造一把尺子。
    if not _legacy:
        queries = [("main", text)]
        if os.environ.get("KB_IMG_TEXT_EXTRA", "").strip().lower() not in ("off", "0", "false", "no"):
            for i, blk in enumerate(_blocks):
                queries.append(("img_text#%d" % (i + 1), blk))
        K_RRF = 60
        depth = max(top * 2, 10)
        pooled = {}
        for qname, q in queries:
            for lname, lst in bm.search(q).items():
                for rank, (did, sc, _) in enumerate(lst[:depth], 1):
                    d = bm.docs[did]
                    uid = d["unit_id"]
                    row = pooled.get(uid)
                    if row is None:
                        pooled[uid] = {"source": lname, "unit_id": uid, "anchor": d["anchor"],
                                       "table": d["table"], "kb_type": d["kb_type"],
                                       "source_sha256": d["source_sha256"],
                                       "raw_bm25": round(sc, 4),
                                       "rrf": round(1.0 / (K_RRF + rank), 8),
                                       "queries": [qname],
                                       "excerpt": d["text_excerpt"][:200]}
                    else:
                        row["rrf"] = round(row["rrf"] + 1.0 / (K_RRF + rank), 8)
                        if sc > row["raw_bm25"]:
                            row["raw_bm25"] = round(sc, 4)
                            row["source"] = lname
                        if qname not in row["queries"]:
                            row["queries"].append(qname)
        raw = sorted(pooled.values(), key=lambda r: (-r["rrf"], -r["raw_bm25"]))[:top]
        bm25_max = max((r["raw_bm25"] for r in raw), default=0.0)
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

# ── 位置归一化（2026-10-20）───────────────────────────────────────────────────
# 真单读数：同一条链里出现过 `图片 1（#img.1）`、`图 1 第 2–3 处（主标题）` 两种非三形态写法，
# 报告「位置」那一列因此指不到地方。这里**只做可证明不丢信息的三件事**：
#   ① 去括号补语 ② 范围取首个 ③ `图片 N`→`图 N`（`[00:12]`→`视频 00:12` 同理由）。
# ⚠️ **不补**「第 X 处」：推不出处的就不许编 —— 出口闸 `kb/l8/material_evidence_gate.py` 会判红，
#   那正是要它响的场合（宁可红，也不要一个看起来精确、其实编出来的位置）。
_RE_PAREN = re.compile(r"[（(][^（）()]*[）)]")
_RE_RANGE = re.compile(r"第\s*(\d+)\s*[–—\-~～至]\s*\d+\s*处")
_RE_IMG_PREFIX = re.compile(r"^图片\s*(\d+)")
_RE_VID_TC = re.compile(r"^\[?(\d{1,2}):(\d{2})\]?$")
_RE_VID_PREFIX_TC = re.compile(r"^视频\s*\[?(\d{1,2}):(\d{2})\]?$")


def _normalize_position(pos):
    """位置归一化：去括号补语 / 范围取首个 / `图片 N`→`图 N` / `[MM:SS]`→`视频 MM:SS`。"""
    s = str(pos or "").strip()
    if not s:
        return s
    s = _RE_PAREN.sub("", s).strip()
    s = _RE_RANGE.sub(r"第 \1 处", s)
    s = _RE_IMG_PREFIX.sub(r"图 \1", s)
    m = _RE_VID_TC.match(s) or _RE_VID_PREFIX_TC.match(s)
    if m:
        s = "视频 %s:%s" % (m.group(1), m.group(2))
    return re.sub(r"\s+", " ", s).strip()

def review(text, content_type="text", position="全文", report_dir=None, run_id=None, top=5, scene=None, image_paths=None):
    position = _normalize_position(position)   # ★ 2026-10-20：位置三形态归一化（见上方 helper）
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
    # ── 第 2b 层：负面样本规则（只有图片类或有画面读数时才跑；文本类默认不引入）──
    # ★ 2026-10-20：**正文里带画面读数 ⇒ 按图片处理**。
    #   为什么：守衡把每张图的画面读数拼进送审正文（`【/图 N 画面读数】`），但
    #   `--content-type` 是 headless 里的模型自己选的（模板只说"三选一"）——
    #   选成 text 时这一层就不会跑，而素材明明是图。判据放在**素材自身**上，
    #   不依赖上游选对：只要有画面读数字块，就当图片走。
    # ★★ 2026-10-20（P0 收口）：**再加一路「图内文字（本机 OCR）」**。
    #   上一版只认画面读数块，而 10:07 那单的 `--text` 里**只有 OCR、没有画面读数**
    #   （画面读数进了 `question`，没进素材文件）⇒ 兜底条件不成立 ⇒ 整层没跑 ⇒ PASS。
    #   实测同一天：`content_type=text` → PASS/0 条；`content_type=image` → REVIEW/5 条。
    #   守衡送审的图单，正文**恒以** `【图片 N 的图内文字（本机 OCR）】` 开头 ——
    #   这就是现成的、不依赖上游把 `--content-type` 选对的信号。
    #   判据：`kb/l8/check_negative_rule_trigger.py`（A 组三条触发路 ＋ B 组三条不许误触发）。
    _looks_image = (("画面读数" in text) or ("【/图" in text)
                    or ("图内文字（本机 OCR）" in text))
    if (content_type == "image") or (scene is not None) or _looks_image:
        _t = time.perf_counter()
        trace["negative_rules"] = layer_negative_rules(
            text, scene, top=max(top, 3),
            # ★★ 2026-10-20：图片/视频类素材要求"真的对上这张图"（同图指纹或画面线索），
            #   否则「仅文字相近、画面 0.00」也会进清单 —— 那是把别家素材的历史意见印成本单命中。
            require_visual=_looks_image or (str(content_type or "").lower() in ("image", "video")))
        _perf["negative_rule_layer_ms"] = round((time.perf_counter() - _t) * 1000, 1)
        trace["negative_rules"]["scene_provided"] = scene is not None
    _t = time.perf_counter()
    trace["units"] = layer_units(text, reg, top=top)
    _perf["unit_layer_ms"] = round((time.perf_counter() - _t) * 1000, 1)
    # ── ★★ 2026-10-20（Owner 真单：「339 中的图片没命中知识库」，而引擎给了 PASS）──────
    #   病灶：图片单的三条身份判据（图字节 sha / 逐字包含 / 行重合）会因**传输形态**失效
    #   （聊天图与附件原件字节不同、两套 OCR 读得不同），而 `require_visual` 又把
    #   「仅文字相近」整批丢掉 ⇒ 负面样本规则层 0 命中 ⇒ 覆盖被一个**安全词**撑起来
    #   （实测 `wearable`）⇒ 无 findings ⇒ **PASS**，而那张图在库里正是负面样本。
    #   兜底判据：**单元层已经把它召回了**（实测 BM25 308），命中单元自带的 `source_sha256`
    #   与规则 `image_refs[].sha256` 是同一把尺子（都是图字节）⇒ 用它们确认「同一张图」，
    #   完全不依赖送审侧把 sha 传对、也不依赖两套 OCR 读得一样。
    #   口径：与 N-1.x 那层**同一条**（历史审核意见 ⇒ REVIEW，不 BLOCK）；去重按条款号。
    try:
        _sn = _load_self_negative()
        _sn_hits = _sn.self_negative_hits((trace.get("units") or {}).get("top_bm25") or [],
                                          top=max(top, 3))
    except Exception as _e:                              # noqa: BLE001 — 附加层不许拖死评审
        _sn_hits = []
        trace["library_negative_sample"] = {"error": "%s: %s" % (type(_e).__name__, _e)}
    if _sn_hits:
        _nr = trace.get("negative_rules")
        if not isinstance(_nr, dict):
            _nr = {"engine": "kb/l3/candidates/negative_rules.jsonl", "hits": [],
                   "self_reference_only": True}
            trace["negative_rules"] = _nr
        _have = {(h.get("article_no") or "") for h in (_nr.get("hits") or [])}
        _added = [h for h in _sn_hits if (h.get("article_no") or "") not in _have]
        _nr.setdefault("hits", []).extend(_added)
        # ★ 两个读数必须分开记（实测踩过）：`detected` = 同图判据认出几条，
        #   `added` = 其中**新**并入 findings 几条（相似度那层可能已经命中同一条规则）。
        #   覆盖那条闸门看的是 `detected` —— 否则「判据成立但被去重」会被读成「判据没成立」，
        #   闸门就白装了（本库反复栽在「判据在、读数错」上）。
        _nr["library_negative_sample"] = {
            "detected": len(_sn_hits),
            "added": len(_added),
            "hits": [{"article_no": h.get("article_no"), "record_id": h.get("record_id"),
                      "matched_by": h.get("matched_by"), "unit_anchor": h.get("unit_anchor"),
                      "unit_bm25": h.get("unit_raw_bm25")}
                     for h in _sn_hits[:5]],
            "note": "本素材命中的库内单元与规则取证图**同图**（图字节 sha256 / 取证锚点相同）"
                    "⇒ 这张图在知识库里是**负面样本**（历史审核已判「不能这么做」），"
                    "判 **REVIEW**（不判 BLOCK）；"
                    "⚠️ 这条判据不依赖送审侧传对 sha，也不依赖两套 OCR 读得一样",
        }
    # ── 第 2c 层：图身份（2026-10-21）—— **图对图**认，不依赖 OCR / 图字节 sha ──
    #   病根（2026-10-21 德国海报）：生产文本丢变音符号 + 夹水印行 ⇒ 文本层 0 命中；
    #   图字节 sha 又被飞书重压缩打掉 ⇒ 两条身份判据都失效。图身份层只用 pHash/像素相关。
    if image_paths:
        try:
            _idn = layer_image_identity(image_paths, top=max(top, 3))
        except Exception as _e:                          # noqa: BLE001 — 附加层不许拖死评审
            _idn = {"engine": "kb/l3/candidates/negative_image_fp.jsonl", "hits": [],
                    "error": "%s: %s" % (type(_e).__name__, _e)}
        trace["image_identity"] = _idn
        if _idn.get("hits"):
            if "_sn" not in dir():
                _sn = _load_self_negative()
            _nr = trace.get("negative_rules")
            if not isinstance(_nr, dict):
                _nr = {"engine": "kb/l3/candidates/negative_rules.jsonl", "hits": []}
                trace["negative_rules"] = _nr
            _merged, _merge_counts = _sn.merge_image_identity_hits(
                _nr.get("hits") or [], _idn["hits"])
            _nr["hits"] = _merged
            _added = _idn["hits"]
            _nr["image_identity"] = {"checked": _idn.get("checked"),
                                     "detected": len(_idn["hits"]),
                                     "added": _merge_counts["added"],
                                     "upgraded": _merge_counts["replaced"]}
    # ── ★★ 2026-10-20（Owner 实测：「我发了图片，回复的问题是其他图片的」）──────────────
    #   病灶：规则的取证图是**整条记录的全部图**，而规则正文常常只讲其中一张 ——
    #   实测同一记录 5 张图产出 4 条规则，正文分别写「图1」「图2」「图3」「图4」，
    #   而四条规则的 `image_refs` **全都是那 5 张** ⇒ 发的是图4，卡上却印了图1/图2/图3 的意见。
    #   另有一类跨记录聚合的规则（实测一条覆盖 14 条记录 / 43 张图）对任何图都可能命中。
    #   ⇒ 在**两层命中合并之后**统一收窄（只收窄「讲哪张图」这一层，不改任何评分与门槛）：
    #     ① 跨记录聚合 ⇒ 图片级不认；② 正文写「图N」⇒ N 必须等于本素材对上的取证图 seq；
    #     ③ 无「图N」的记录级意见保留，但在读数里标 `attribution=record`（不许说成「这张图命中」）。
    #     被丢掉的全部进 `negative_rules.narrowed_out`（**不静默丢**）。
    try:
        _nr2 = trace.get("negative_rules") or {}
        _raw_hits = _nr2.get("hits") or []
        if _raw_hits:
            if "_sn" not in dir():          # 上面那段 try 失败过 ⇒ 这里自己再装一次（不许因它整层不跑）
                _sn = _load_self_negative()
            _unit_shas = {(u.get("source_sha256") or "").lower()
                          for u in ((trace.get("units") or {}).get("top_bm25") or [])}
            _sub_shas = _sn.image_shas_in(text)
            _kept, _narrowed = _sn.narrow_negative_hits(
                _raw_hits, submitted_shas=_sub_shas, unit_shas=_unit_shas)
            if _narrowed:
                _nr2["hits"] = _kept
                _nr2["narrowed_out"] = _narrowed
                _nr2["narrowed_note"] = (
                    "被剔掉的都是「讲的不是这张图」的命中：跨记录聚合，或正文写「图N」而本素材对上的"
                    "取证图是别的序号。判据见 `kb/l7/review-engine/core/self_negative.py::narrow_negative_hits`")
    except Exception as _e:                              # noqa: BLE001 — 收窄层不许拖死评审
        trace.setdefault("negative_rules", {})["narrow_error"] = "%s: %s" % (type(_e).__name__, _e)
    _assemble_t = time.perf_counter()

    findings, unmet = [], []
    p0_rule_ids = set()
    for h in trace["p0"]["hits"]:
        rid = h["rule_id"]
        p0_rule_ids.add(rid)
        r = rules.get(rid, {})
        (cat, sub), basis = classify(r, vocab)
        # ★ 2026-10-21：正则命中时 `pattern` 是**正则源码**，拿它当「逐字摘录」既读不懂、
        #   也不满足引用契约；`matched[].text` 是真正被命中的那段文本（matcher 2026-10-21 起记）。
        excerpt = ((h["matched"][0].get("text") or h["matched"][0]["pattern"])
                   if h.get("matched") else r.get("forbidden_expression") or "")
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

    # ── 负面样本规则（N-1.x）→ findings（2026-10-20）────────────────────────
    # 定位：**历史审核意见**，一律 REVIEW（不当判定依据，也不据此 BLOCK）。
    # 依据六要素齐（库名/条款号/锚点/sha/摘录/直链）⇒ 可回源；`verbatim_verified` 照实写 False：
    # 本层没有回 L0 逐字重算（规则文本是蒸馏时从源记录字段逐字取的，但这里不重复核）。
    #
    # ★★ 2026-10-20（真单事故：图片单报告印出「1.挂式衣架: 磨砂亚克力材质…」，图里没有衣架）：
    #   `excerpt` / `matched_term` **不再取规则正文** —— 规则正文是**历史记录自己的话**，
    #   不是这一单素材里的字。把它印进「命中描述」等于给读者看一段素材里不存在的原文。
    #   现在：`excerpt` 留空（报告那一格印 `—`，那是诚实的）；规则原文另存 `history_rule_text`
    #   供回源核对，**不许**再冒充逐字命中。同批的第二处收口见 `require_visual`（画面 0.00 不入清单）。
    #
    # ★★ 2026-10-20 第二轮（**串图**，Owner 真单：发 Giveaway 长图，回的链接是 BJs 渠道记录）：
    #   「同图」判得对，但**归属**不对 —— 那条记录里装着 4 张图（2 张 BJs + 这张长图重复两次），
    #   而那张长图还挂在另外 2 条**内容完全不同**的记录里。把这种记录的意见印成「这张图的依据」
    #   就是串图。⇒ 现在**只有 `attribution == "subject"` 才进 findings**：
    #     subject           = 该记录按图字节去重后仅 1 张图，且该图未出现在内容不同的其它记录里
    #     其它（record_level / shared_reference / unknown / semantic）⇒ **只作线索**，
    #     写进 `negative_rules.not_subject`（不静默丢，报告/留底查得到），并且
    #     **单独撑不起 PASS**（见下面 state 收口：无 findings 且有线索 ⇒ 拒答，不是通过）。
    #
    # ★★ 2026-10-20 第三轮（Owner：「我在飞书侧发图片，就是无法命中这些规则」）——
    #   **只有 subject 才可引用**这条把召回压到 ~5%：库内 288 张去重图里 subject 只有 **15 张**
    #   （`kb/l3/registry/image_roles.json`：shared_reference 182 / record_level 91）。
    #   而「记录里有多张图」并**不等于**"这条意见不指向这张图" —— 只要命中是**图级锚定**的
    #   （`figure_anchored`：对上了这条规则的某张取证图）且规则正文没有讲别的图号，
    #   这条意见就是**这条记录**的意见，可以引用，但必须**如实标成记录级**（见下面的 reason 后缀）。
    #   `shared_reference` 仍然一律挡：同一张图挂在**内容不同**的多条记录里，意见指向哪条是真说不清。
    # ★★ 2026-10-20 第四轮（Owner：「触发规则了，就必须输出命中知识库」＋「串图不能接受」）：
    #   上一轮只有 `subject` / 图级锚定的 `record_level` 才进 findings ⇒ **52% 的库内图回拒答**。
    #   Owner 的要求两条同时成立，所以这里**不再丢弃命中**，而是**把"这条意见凭什么算"标出来**：
    #     figure —— 规则正文讲「图N」且 N 就是本素材对上的那张 ⇒ 才算「**这张图**的意见」
    #     record —— 规则是**记录级**意见（正文没写图号），本图在该记录里 ⇒ 「**该记录**的历史意见」
    #     shared —— 这张图在库里是**复用图**（同一张图挂在内容不同的多条记录里）
    #               ⇒ 「**同图历史意见**（该图还出现在记录 …）」，它属于那条记录，不专指本图
    #     unknown —— 连"对上了哪张取证图"都定不下来（semantic / 归属产物缺失）⇒ 仍只作线索，不算命中
    #   **三条硬约束（防串图）**：
    #     ① `unknown` 一律不进 findings；② 任何一条 finding 都**不许**被说成「这张图命中」
    #     除非证据类就是 `figure`；③ `require_visual`（只在同图/画面真对上时才收）一个字不动。
    # ★★ 2026-10-20 第五轮（Owner 真单：图片单里出现「Figma 链接」「项目背景：亚马逊多语言修改」
    #   「麻烦看看呀」三条当意见）—— **规则质量问题，不是归属问题**：
    #   476 条 N-1.x 里只有 **132 条（28%）带规范内容**；245 条是 `observation`（纯观察）、
    #   35 条 `brief`（需求描述）、39 条 `non_substantive`（@提醒/客套）。
    #   把它们印成"历史审核意见"就是串图观感的真正来源。
    #   ⇒ 只引用**有规范内容**的规则（point/advice ＋ 正文非 URL/非 @提醒/≥10 字），
    #     其余**如实记进 `negative_rules.not_substantive`**（不静默丢，报告/留底查得到）。
    _RE_URL = re.compile(r"https?://|www\.", re.I)

    def _substantive_rule(h):
        t = str(h.get("rule_text") or "").strip()
        if str(h.get("rule_kind") or "") not in ("point", "advice"):
            return False, "规则类型=%s（非 point/advice ⇒ 不是可引用的审核意见）" % h.get("rule_kind")
        if len(t) < 10:
            return False, "规则正文过短（%d 字）" % len(t)
        if _RE_URL.search(t):
            return False, "规则正文是链接/附件引用（不是意见）"
        if t.startswith("@") or t.count("@") >= 2:
            return False, "规则正文是 @ 提醒（不是意见）"
        return True, ""

    _ns_seen, _ns_lines = set(), []
    _nonsub_lines = []
    for h in (trace.get("negative_rules") or {}).get("hits", []):
        _ok_sub, _why_sub = _substantive_rule(h)
        if not _ok_sub:
            _nonsub_lines.append({"article_no": h.get("article_no"), "rule_kind": h.get("rule_kind"),
                                  "why": _why_sub, "rule_text": (h.get("rule_text") or "")[:80]})
            continue
        _attr = _attribution_of(h)
        _fig_anchored = (bool(h.get("figure_anchored"))
                         or int(h.get("match_rank") or 0) >= 2
                         or bool(h.get("library_negative_sample")))
        _fig_attr = str(h.get("figure_attribution") or "")
        _mi = h.get("matched_image") or {}
        if _attr == "semantic" or _attr == "unknown":
            _cls = "unknown"
        elif _fig_anchored and _fig_attr == "figure":
            _cls = "figure"
        elif _attr == "shared_reference":
            # 复用图：图在、记录也在，但这张图挂在**内容不同**的多条记录里 ⇒ 只能算同图历史意见
            _cls = "shared"
        elif _fig_anchored:
            _cls = "record"
        else:
            _cls = "unknown"
        if _cls == "unknown":
            _key = (h.get("article_no"), _mi.get("record_id"), _mi.get("sha256"))
            if _key not in _ns_seen:
                _ns_seen.add(_key)
                _ns_lines.append({
                    "article_no": h.get("article_no"),
                    "rule_kind": h.get("rule_kind"),
                    "attribution": _attr,
                    "why": (h.get("attribution_why") or "") or "对不上任何一张取证图（semantic/unknown）⇒ 只作线索",
                    "record_id": _mi.get("record_id"),
                    "file_token": _mi.get("file_token"),
                    "image_sha256": _mi.get("sha256"),
                    "image_anchor": _mi.get("anchor"),
                    "score": h.get("score"),
                    "history_rule_text": (h.get("rule_text") or "")[:120],
                })
            continue
        ev = (h.get("evidence") or [{}])[0]
        act = h.get("action") or {}
        _history_record_id = (ev.get("record_id") or _mi.get("record_id")
                              or h.get("record_id"))
        _history_case = history_case_for_record(_history_record_id)
        # ★★ 2026-10-21：负面样本层此前**从不带 A3** ⇒ 图片单 95% 落「未归类」。
        #   `stamp_taxonomy()` 有一条「条目自己带了分类就别抹掉」的分支，所以这里盖完即生效；
        #   盖不到（映射表里没有）⇒ 留 None，报告照旧落兜底类，**不编**。
        _nt_cat, _nt_basis = negative_taxonomy(h.get("rule_code"), h.get("article_no"))
        findings.append({
            "severity": "REVIEW",
            "layer": "负面样本规则（N-1.x）",
            "p_level": "P2",
            "category": "负面样本", "sub": h.get("rule_code_label") or h.get("rule_code") or "未分类",
            "taxonomy_category": _nt_cat,
            "taxonomy_subcategory": None,
            "taxonomy_basis": _nt_basis,
            "position": position,
            "excerpt": "",
            "matched_term": "",
            "history_rule_text": h.get("rule_text") or "",
            "history_analysis": _history_case.get("analysis") or "",
            "history_advice": _history_case.get("advice") or "",
            "history_record_id": _history_record_id or "",
            "history_scope": "record_level",
            "verbatim_verified": False,
            "anchor": ev.get("anchor"),
            "source_sha256": ev.get("source_sha256"),
            "l0_entry_url": _l0_entry_url(ev.get("anchor")),
            "article_no": h.get("article_no"), "rule_id": h.get("rule_id"),
            "rule_code": h.get("rule_code"), "kb_type": "internal_sample",
            "library": "内部正负样本库（负面样本规则·历史审核意见）",
            "evidence_gap": h.get("evidence_gap")
                            or ("历史审核意见：命中是**相似召回**，不是本单素材的逐字命中；"
                                "规则原文见 history_rule_text（蒸馏时逐字取自源记录字段）"),
            "attribution": _attribution_of(h),
            "figure_attribution": h.get("figure_attribution"),
            "evidence_class": _cls,
            "evidence_class_label": {
                "figure": "这张图的历史意见（规则正文按图号对上了本图）",
                "record": "该记录的历史意见（本图在该记录里；正文未按图号指定）",
                "shared": "同图历史意见（本图是库内复用图，该图还出现在其它记录）",
            }.get(_cls, ""),
            "reason": "相似历史审核意见（%s·参考）：匹配分 %.2f（画面 %.2f / 文字 %.2f）｜%s｜⚠️ 非本单素材逐字命中"
                      % (h.get("rule_kind") or "point", h.get("score") or 0,
                         h.get("visual_score") or 0, h.get("text_score") or 0,
                         "；".join(h.get("reasons") or [])[:120] or "仅文字相近")
                      + {"figure": "",
                         "record": "｜该历史意见未指定图号，按**记录级意见**展示；不代表本图独立判定",
                         "shared": "｜该意见为**同图历史意见**：本图在库里是复用图，"
                                   "该图还出现在其它内容不同的记录里 ⇒ 它属于那条记录，**不专指本图**",
                         }.get(_cls, ""),
            "advice": (act.get("replacement") or None) if act.get("kind") == "replace" else None,
            "advice_note": history_action_advice_note(act),
            "fact_or_inference": "事实",
            "confidence": "中" if (h.get("rule_kind") == "point") else "低",
            "matched_images": h.get("image_refs") or [],
            # 报告渲染要这一格（实测 KeyError：write_report 第 1827 行）
            "classification_basis": "负面样本规则 N-1.x：rule_code=%s（%s）；语料=内部正负样本库"
                                    % (h.get("rule_code"), h.get("rule_kind") or "point"),
        })

    # 去重：同一处文案命中多条同义规则（L3 的修订对规则常有大量近义条目）时合并为一条，
    # 保留严重度最高的一条，并把被合并的条款号记进 merged_articles（可追溯，不静默丢）
    order = {"BLOCK": 0, "REVIEW": 1}
    findings.sort(key=lambda f: (order.get(f["severity"], 9), f["category"], f["sub"]))
    by_key, merged = {}, {}
    for f in findings:
        k = (f["category"], f["sub"], norm(f.get("matched_term") or f["excerpt"]))
        # ★ 2026-10-20 第三轮：负面样本规则（N-1.x）的 `excerpt` / `matched_term` 是**故意留空**的
        #   （规则正文是历史记录自己的话，不许冒充本单逐字命中）⇒ 去重键退化成只剩
        #   (类别, 子类)，把**五条不同的历史意见合并成一条**（实测 17:11 那单：命中 5 条、只剩 1 条）。
        #   ⇒ 两格都空时把**条款号**并入键：不同规则各自成条，同一条规则仍只出现一次。
        if not (f.get("matched_term") or f.get("excerpt")):
            k = k + (f.get("article_no") or f.get("rule_id") or "",)
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
    cited_shas = rule_cited_anchor_shas(rules)          # ★ 2026-10-23：锚点同名 ≠ 同源
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
        case_resources={c.get("resource_id") for c in case_clauses if c.get("resource_id")},
        cited_shas=cited_shas)
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
    # ── ★★ 2026-10-20：安全词**不单独**支撑 PASS（反 fail-open 的第二半）───────────
    #   实测那一单的覆盖是 `covered_by=safe_vocabulary` —— 靠规则层命中一个**安全词**
    #   （`wearable`）撑起来的，而素材本身在库里是**负面样本**。
    #   口径：当「同一张图 = 库内负面样本」这一事实成立时，**不许**只用安全词解释覆盖；
    #   照实记进 trace（报告里看得见），判定由上面那条 findings 走 REVIEW。
    #   ⚠️ 只在**这一种组合**下收窄：不把「安全词不能支撑 PASS」推广到所有单
    #     （纯文案单命中允许表述、且无任何问题 ⇒ PASS 是既有且正确的形状）。
    if (covered_by == "safe_vocabulary"
            and ((trace.get("negative_rules") or {}).get("library_negative_sample") or {}).get("detected")):
        trace["coverage"]["safe_vocabulary_alone_insufficient"] = (
            "安全词命中（%s）**不单独**支撑 PASS：本素材与库内负面样本同图"
            "（见 negative_rules.library_negative_sample）⇒ 判 REVIEW，不是通过"
            % "、".join(trace["coverage"].get("safe_vocabulary_hits") or []))
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
        _ra = case_excerpt(c)
        # ★★ 2026-10-20：案例层**在提取这一层就归类**（Owner：「图片提取规则的时候要归类」），
        #   不分类的后果是报告落「未归类」（实测一张图单 4 条有 2 条如此）。
        _tax_cat, _tax_sub, _tax_basis = case_taxonomy(c.get("reason_category"))
        _art = c.get("article_no")
        # 问题描述（PRD §8.3 六格之一）：**必须有**（Owner 2026-10-20「不允许出现这样的回答，
        #   必须有问题描述」）。案例层不许拿 excerpt 顶描述（那会把别人的原文当本单的描述），
        #   所以用「库内反例 + 问题要点」如实写，并标明**非本单画面**。
        _desc = ("库内反例 %s 的问题要点：%s（非本单画面）" % (_art, _ra)) if (_art and _ra) else (
            "库内反例 %s 命中（非本单画面，需人工核对同源）" % _art if _art else "")
        findings.append({
            "severity": "REVIEW", "layer": "案例层（L4 定稿「反例/禁区」）",
            # ★ 2026-10-10：案例层是 L4 定稿的「反例/禁区」。它**不是 P0 确定性匹配**
            #   （那一层走关键词/正则），按 PRD §6.2 归 P1「安全与准确性」。
            #   显式写出来，免得它靠层文案猜（分级的 LAYER_KIND_TO_TIER 也能guess到，
            #   但「能不能 guess 到」不该是设计要求）。
            "p_level": "P1",

            "category": c.get("reason_category") or "反例",
            "sub": "禁区（库内反例条款）",
            # A3 12 类：案例层**自带**（不再指望 stamp_taxonomy 去规则表里找 —— 案例层不在那张表里）
            "taxonomy_category": _tax_cat,
            "taxonomy_subcategory": _tax_sub,
            "taxonomy_basis": _tax_basis,
            "description": _desc,
            "position": position, "excerpt": _ra, "matched_term": row["anchor"],
            "history_analysis": c.get("reason_analysis") or "",
            "history_advice": c.get("advice") or "",
            "history_record_id": str(c.get("resource_id") or "").split("__")[-1],
            "history_scope": "record_level",
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
    # ── ★★ 2026-10-20（串图修复 ②）：**非 subject 的同图命中，单独撑不起 PASS** ────────
    #   病灶：Giveaway 长图命中的是 BJs/Costco/品牌日 三条记录 —— 那张图只是它们的**附图**，
    #   该图还跨 3 条内容不同的记录。把这些命中挡在 findings 之外后，会留下「0 findings」；
    #   这时若覆盖信号（安全词/同源单元）成立，旧逻辑会判 **PASS** ⇒ 等于把「串图」换成
    #   「未命中即通过」，方向从假依据变成假放行，更坏。
    #   口径：有这类线索、又没有别的 findings ⇒ **拒答（覆盖缺口）**，并把理由写进 trace：
    #   它既不是「通过」，也不是「发现了内容问题」，而是「库里没有针对这张图的意见，需人工看覆盖」。
    #   ⚠️ 只挡 PASS 一个方向：BLOCK/REVIEW/NEEDS_INPUT 一个字不动。
    # ★★ 2026-10-20 补（实测崩溃，非假设）：`trace["negative_rules"]` 只在
    #   「图片/视频单」那一路才被初始化（见上面的 `_looks_image` 分支）——
    #   **纯文字单**这一路从来没建过这个键，而下面几行是无条件写的 ⇒
    #   文字类素材一律 `KeyError: 'negative_rules'`，整单跑不出来（引擎 exit 2）。
    #   兜底不是"跳过判据"，而是把"这一层本单没跑"如实记进 trace（fail-visible）。
    trace.setdefault("negative_rules", {
        "engine": "kb/l3/candidates/negative_rules.jsonl",
        "hits": [],
        "not_run": "本单不是图片/视频（或正文里没有画面读数/图内文字）⇒ 负面样本规则层没跑",
    })
    trace["negative_rules"]["not_subject"] = _ns_lines
    trace["negative_rules"]["not_subject_count"] = len(_ns_lines)
    trace["negative_rules"]["not_substantive"] = _nonsub_lines
    trace["negative_rules"]["not_substantive_count"] = len(_nonsub_lines)
    trace["negative_rules"]["attribution_gate"] = (
        "subject_or_record_level_anchored" if _ns_lines or findings is not None else "n/a")
    _covered_by_before = covered_by
    covered = bool(covered_by)
    if _ns_lines and not findings:
        covered = False
        trace["coverage"]["coverage_gap"] = True
        trace["coverage"]["coverage_gap_reason"] = (
            "库内有**同图**命中（%d 条规则 / 涉及记录 %d 个），但那张图在这些记录里是"
            "**跨内容复用的复用图**（同一张图挂在内容不同的多条记录里）⇒ 意见指向哪条记录说不清，"
            "**不作为依据**；库内无针对这张图的意见 ⇒ 覆盖缺口，需人工看覆盖，"
            "**不得据此当 PASS（未命中 ≠ 合规）**"
            % (len(_ns_lines), len({x.get("record_id") for x in _ns_lines if x.get("record_id")})))
        trace["coverage"]["covered_by_before_attribution_gate"] = _covered_by_before
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

    # ── ★★ 2026-10-17：11 类归类盖章（附加视图，不动上面两格）────────────────────
    _tax_st = stamp_taxonomy(findings, taxonomy_index())
    trace["taxonomy"] = {"with_class": _tax_st["stamped"], "without_class": _tax_st["missing"],
                         "policy": "kb/l3/registry/rule-taxonomy.json（人工口径，Owner 采用；非源字段）"}

    # ── ★★ 2026-10-19（Owner：「必须给建议」）：BLOCK 单的「建议」在这里补进**数据** ────
    #   补在**返回前**而不是渲染时：卡片（`render()`）、报告（`write_report`）、
    #   入口 JSON（`_finding_to_risk_item → suggestion`）三处读同一格，才不会两端打架。
    _adv_n = backfill_advice(findings, state)
    if _adv_n:
        trace["advice_fallback_n"] = _adv_n
        print("[review] 建议兜底补入 %d 条（库内无原话改法，按 kb/l5/advice_book.py 给）" % _adv_n,
              file=sys.stderr)

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
            # ★★ 2026-10-19（Owner：「所属类别/所属子类」统一到 A3 12 类）：
            #   首行标签从 **A1 8 类词表**（`f['category']-f['sub']`）换成 **A3 12 类**
            #   （`taxonomy_category` / `taxonomy_subcategory`，真源 `rule-taxonomy.json`）。
            #   盖不到（模型侧条目 / 反例案例层 sc-…）⇒ 印 **`未归类`**（12 类的兜底类）。
            _tax_lbl = tax_label(f)
            lines.append(f"{i}.【{_tax_lbl}】{f['position']}，{f['excerpt']}")
            lines.append(f"  原因：{f['reason']}")
            lines.append(f"  依据：{cite(f, reg)}")
            # ★★ 2026-10-19（Owner 逐字：「**去掉锚点**」＋「卡片信息必须按照 PRD 字段执行」）——
            #   **这一行不再上卡**。它是**库内坐标**（`#广告文案明细/rec…/命中片段`）+ 指纹，
            #   业务侧读不懂、PRD §5.3.3/§5.3.4 的逐条字段里也没有它。
            #   ⚠️ 溯源没有丢：`f['anchor']` / `f['source_sha256']` 仍在 findings / 报告
            #      （`write_report` 的「- 锚点：`…`」「逐条四段」）与入口 JSON 里 —— 删的只是卡上那一行。
            # ★★ 2026-10-14（Owner 裁定）：逐条块**不再输出「判定：…｜置信度：…」这一行**。
            #   口径：PRD §5.3 逐条模板只有 原因 / 依据 /（BLOCK 才有）建议，三态只在结论行
            #   一处 ⇒ 同一张卡上不许出现两个「判定」。
            #   `f['fact_or_inference']` / `f['confidence']` **仍在引擎 JSON 里**（只改版式）。
            # ★★ 2026-10-19（Owner：「**必须给建议**」）：`advice` 现在由 `backfill_advice()`
            #   在 `review()` 返回前补过（BLOCK 单**恒有值**）⇒ 这里不再需要「有才印」的隐式空行。
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
        #
        # ★★ 2026-10-17 曾按 Owner 令把这一格**改成 11 类**（`taxonomy_category`），
        #   2026-10-19 **已回退到 PRD 四维**，理由（两条，都是实测）：
        #     ① Owner 2026-10-19 再次裁定「卡片所有的回复必须跟 PRD §5.3 对齐」，
        #        而 §5.3.4 的 ≥3 样张逐字是 `· 合规类：X 个 · 消费者安全类：X 个 · 措辞类：X 个`；
        #     ② 11 类在**模型侧条目上根本盖不上章**（`stamp_taxonomy` 只认规则表里的 rule_id），
        #        实测真单（4 条全是模型侧/外部标准）⇒ 4 条全落 `· 未归 11 类问题：4 个`
        #        ⇒ **分类汇总退化成一个常数桶**，比「分组不准」更坏：读卡的人拿不到任何分布。
        #   ⚠️ 11 类**没有消失**：它仍在报告（`report_memory.taxonomy_section_lines()` 的「按所属类别汇总（12 类）」段）
        #      与逐条标签里 —— 那里每条都能盖到，也不会顶掉 PRD 的分类汇总。
        #
        # ★★ 形状（Owner 2026-10-19 第三次给的样子）：**每类一行**、`· <维度>类问题：N 个`。
        #   条数降序；并列时按政策件四维顺序；「未标注维度」桶**压最后**（不并进任何一类）。
        # ★★ 2026-10-19（Owner：「所属类别/所属子类」统一到 A3 12 类）：
        #   汇总的轴从 **A2 PRD 四维**（`risk_category`）换成 **A3 12 类**（`taxonomy_category`）——
        #   与逐条首行、规则行、报告同一套。盖不到的落 **`未归类`**（12 类里的兜底类）。
        agg = {}
        for f in fs:
            agg[tax_category(f)] = agg.get(tax_category(f), 0) + 1
        _order = {n: i for i, n in enumerate(taxonomy_classes())}
        _bucket = TAX_UNCLASSED
        _keys = sorted(agg, key=lambda x: (x == _bucket, _order.get(x, 99), x))
        # * 形状（Owner 2026-10-19 给的格式）：**每类一行**，行间不空行；兜底写 `· 未归类问题：N 个`。
        lines.extend("· %s问题：%d 个" % (k if k == _bucket else k + "类", agg[k]) for k in _keys)
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
        # ── 历史：2026-10-12 这里曾补过一行 `- 维度：**<四维>**`（当时 PRD §8.3 要求清单含「维度」）。
        #    2026-10-19 Owner 定「**整个知识库都要同步** 卡上 12 类」后，那一行**已撤掉**；
        #    原来它承担的两件事（① 每条说得出归类 ② 未映射不编）**都还在**：
        #    ① 由下面 `- 所属类别 / 所属子类：` 那一格承担（恒印，盖不到写 `未归类`）；
        #    ② 同上 —— `未归类` 就是 12 类的兜底类，不是编出来的类名。
        # ★★ 2026-10-19（Owner：「报告要同步 卡上 12 类呀，**整个知识库都要同步**」）——
        #   **`- 维度：**` 这一行整行撤掉**。理由：下一行 `- 所属类别 / 所属子类：` 已经是
        #   Owner 定的那套 A3 12 类；再留一行四维，同一份报告里两套分类并排
        #   （实测真报告：维度=消费者安全 而 所属类别=合规与受监管宣称 —— 读者只能怀疑哪个对）。
        #   ⚠️ `risk_category` / `risk_category_basis` **仍在机读 JSON 里**（路由与统计还在用），
        #      撤掉的是**报告里那一行字**，不是数据。
        # ★ 2026-10-17：11 类那一格（附加视图，只增不改）。取不到就**不印**（不写「未分类」冒充）。
        # ★ 2026-10-19：这一格就是 Owner 说的「所属类别 / 所属子类」（A3 12 类）。
        #   改名并**恒印**（盖不到就写 `未归类`）—— 报告与卡面同一套标签。
        _tax_line = "- 所属类别 / 所属子类：**%s**%s" % (
            tax_category(f),
            (" / %s" % f["taxonomy_subcategory"]) if (f.get("taxonomy_subcategory")
                                                      and f.get("taxonomy_category")) else "")
        L += [f"### {i}.【{tax_label(f)}】{f['position']}", "",
              _tax_line] + [
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
    # ── ★ 2026-10-17：11 类汇总段（Owner：「既然分了11类，就要按照11类的出结果」）──────
    # 实现**只有一份** = `report_memory.taxonomy_section_lines()`；本处只调它，不写第二份。
    # 位置：排在「问题清单 / 引用契约」之后、「检索轨迹」之前 —— 附加视图，不动既有段落。
    try:
        _rm = _load_report_memory()[0]
        _tax = _rm.taxonomy_section_lines(fs) if _rm else []
    except Exception:                                     # noqa: BLE001
        _tax = []
    if _tax:
        L += _tax
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
        # ★ 2026-10-17：11 类 / 58 子类（附加视图）。盖不到就是 None + basis 写明原因，不编。
        "taxonomy_category": f.get("taxonomy_category"),
        "taxonomy_subcategory": f.get("taxonomy_subcategory"),
        "taxonomy_basis": f.get("taxonomy_basis"),
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
    _trace = res.get("trace") if isinstance(res.get("trace"), dict) else {}
    _identity = _trace.get("image_identity") if isinstance(_trace.get("image_identity"), dict) else {}
    _negative = _trace.get("negative_rules") if isinstance(_trace.get("negative_rules"), dict) else {}
    _identity_hits = _identity.get("hits") if isinstance(_identity.get("hits"), list) else []
    _negative_hits = _negative.get("hits") if isinstance(_negative.get("hits"), list) else []
    _image_audit = None
    if _identity or _negative:
        _identity_merge = _negative.get("image_identity") if isinstance(_negative.get("image_identity"), dict) else {}
        _image_audit = {
            "checked": bool(_identity.get("checked")),
            "detected": int(_identity.get("detected", len(_identity_hits)) or 0),
            "added": int(_identity_merge.get("added", 0) or 0),
            "upgraded": int(_identity_merge.get("upgraded", 0) or 0),
            "hits": [{k: h.get(k) for k in ("article_no", "rule_id", "record_id", "matched_by",
                                              "match_rank", "attribution", "figure_attribution") if h.get(k) is not None}
                     for h in (_identity_hits or _negative_hits)[:10]],
        }
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
            **({"image_identity": _image_audit} if _image_audit is not None else {}),
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
    ap.add_argument("--image", action="append", default=None, metavar="PATH",
                    help="送审图文件（可重复）。给了就走「图身份」层（pHash/像素相关），"
                         "不依赖 OCR / 图字节 sha；不给 ⇒ 行为与改动前逐字一致。")
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
    ap.add_argument("--scene-json", default=None,
                    help="画面读数 JSON（守衡 scene.mjs 的输出；图片类素材传它会启用「负面样本规则」层）")
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
        "NEG_RULES": ("kb", "l3", "candidates", "negative_rules.jsonl"),
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
    scene = None
    if a.scene_json:
        try:
            _sc = json.load(open(a.scene_json, encoding="utf-8"))
            # 守衡 scene.mjs 的返回有两种形状：{ok, scene:{...}} 或直接 {...}（读数本体）
            scene = _sc.get("scene") if isinstance(_sc, dict) and isinstance(_sc.get("scene"), dict) else _sc
            if not isinstance(scene, dict):
                scene = None
        except Exception as e:                       # noqa: BLE001
            print("[scene] ⚠ 画面读数读不出（%s）⇒ 本层只按文字匹配：%s" % (a.scene_json, e),
                  file=sys.stderr)
    res = review(text, a.content_type, pos, rep_dir, a.run_id, a.top, scene=scene, image_paths=a.image)
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
