#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""negative_rule_match.py —— 守衡收到图片时，把「图内文字 + 画面读数」对到负面样本规则上。

为什么匹配口径长这样（2026-10-20）
──────────────────────────────────
· 规则的正文是**中文审核意见**，而用户发来的多是**英文素材** ⇒ 纯文字字面匹配几乎必空。
· 规则手里真正的判别信号在**画面**：它的 `visual_cues`（场景/人物/物件/风险线索）
  来自该规则名下每张图的多模态读数；来图也有同一套读数（`scene.mjs`）。
  ⇒ 匹配 = **画面线索对齐（主） + 图内文字对齐（次）**，两路加权。
· 只陈述命中理由，不在这里判合规 —— 判定与话术在评审链里。本模块是**检索器**。

打分（可复算，不含概率）
──────────────────────────
    visual = 2.0·场景相同 + 1.5·每条共同风险线索 + 1.5·每类共同人物 + 1.0·每个共同物件
    text   = 输入文字与规则正文的字符二元组重叠率（0~1，按短边归一）
    score  = 0.65·min(visual/6,1) + 0.35·text          （无画面读数时 score = text）

阈值（2026-10-20 实测定）：`min_score=0.40`。
  实测分布：同记录自检索的命中分 p25=0.62 / 中位 0.84；而通用营销文案的误命中 ≈0.32。
  阈值扫描：0.30→自检索 83% 但误命中 2 条；0.35/0.40→81% 且误命中 0；0.45→79%。取 0.40。

用法
────
  python3 kb/l8/negative_rule_match.py --text "..." --scene-json scene.json [--top 5]
  python3 kb/l8/negative_rule_match.py --selftest
"""
import json
import os
import re
import sys

RULES = "kb/l3/candidates/negative_rules.jsonl"

# ★ 2026-10-20：本模块可能被以**任意 cwd** 调用（评审链、selftest、命令行都可能从别处起）。
#   `RULES` 是相对路径，历史行为不改；归属产物要按**本文件位置**反推 kb 根，否则换个 cwd 就找不到。
_KB_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _norm(s):
    return re.sub(r"[\s，。；：、,.;:!?！？（）()\[\]【】\"'“”‘’·…—\-]+", "", str(s or "")).lower()


def _bigrams(s):
    s = _norm(s)
    return {s[i:i + 2] for i in range(len(s) - 1)} if len(s) > 1 else {s} if s else set()


# ── 关键短语指纹（①c）：同图判据的**抗噪档** ──────────────────────────────────
# 为什么要有这一档（真单事故，2026-10-20 15:16）：
#   用户从飞书表「点」出某条负面样本的图、转发给守衡。飞书 IM 在**发送时**压缩了图片，
#   守衡 OCR 读出来的是错字版：
#       Your Chance To Min        ← 应为 Win
#       fc chirv.es c win wecky rewrds
#       cin & Hind tne owiww.y
#   而库里存的是原图 OCR（1318 字，含 `Breast Pumps / Body Pillows / Pregnancy` 等小字导航）。
#   **同一张图、两份 OCR** ⇒ `fp == input_norm` 不成立、行重合掉到 0.7 以下
#   ⇒ 真命中被 `require_visual` 整批丢弃 ⇒ findings=0 ⇒ PASS。
#
#   实测那份输入对全库 476 条规则：同图那几条**共同长短语 8~9 个**、跨题材的**0 个**
#   （反向对照用的是 15:12 假命中过的 N-1.328「视频画面不要过于完美」）。
#   ⇒ 判据从「全文/逐行一致」放宽到「**好几句话对得上**」，对压缩、错字、重排都不敏感。
PHRASE_N = 3            # 短语按 3 个词切
PHRASE_MIN_CHARS = 18   # 短语最少 18 字符 —— 更短的太容易偶然重合（品牌名就够）
PHRASE_MIN_SHARED = 5   # 共同短语 ≥5 个 ⇒ 认作同一张图（实测同图最小 8、异图 0，留 3 个余量）


def _words(s):
    """保留**词边界**的归一化。

    为什么不复用 `_norm`：它把空格也吃掉（`momcozymomcozymomandmore…`）—— 那是给
    「逐字指纹」设计的，一旦词边界没了就没法切短语。两条路各用各的归一化。
    """
    return re.sub(r"[^a-z0-9]+", " ", str(s or "").lower()).split()


def phrases_of(s, n=PHRASE_N, min_chars=PHRASE_MIN_CHARS):
    """连续 n 词的短语集合（只留够长的）。空文本 ⇒ 空集合（不抛）。"""
    w = _words(s)
    out = set()
    for i in range(len(w) - n + 1):
        p = " ".join(w[i:i + n])
        if len(p) >= min_chars:
            out.add(p)
    return out


def scene_from_text(text):
    """从**素材正文里嵌的画面读数字块**还原 scene（守衡 `sceneBlock` 的形状）。

    为什么要有这条路（2026-10-20）：守衡把每张图的画面读数**已经拼进送审正文**了
    （`agent.mjs` 的【/图 N 画面读数】＋ `scene.mjs::sceneBlock`），形状是：
        - 场景：卧室
        - 人物：婴幼儿 · 躺着；成人 · 抱着
        - 物品：枕头；奶瓶（正在被使用）
        - 可见标识：…
        - 图上文字用的是什么文字：英文
        - 画面线索：婴幼儿出镜；…
    而 `--scene-json` 是**结构化**那条路。两条都要能用；否则「守衡已经把画面读出来了」
    这件事在规则匹配里等于白费（它被当成了普通正文）。
    解析不到就返回 None（**不编**）。
    """
    import re as _re
    t = str(text or "")
    if "场景" not in t and "画面线索" not in t:
        return None

    def grab(key):
        m = _re.search(r"^-\s*" + key + r"[:：]\s*(.*)$", t, _re.M)
        return (m.group(1).strip() if m else "")

    def split(v):
        return [x.strip() for x in _re.split(r"[；;]", v) if x.strip()]

    setting = grab("场景")
    if not setting or setting.startswith("（读数里没有"):
        setting = ""
    people = []
    for x in split(grab("人物")):
        kind, _, doing = x.partition("·")
        kind = kind.strip()
        if kind:
            people.append({"kind": kind, "doing": doing.strip()})
    products = []
    for x in split(grab("物品")):
        in_use = "正在被使用" in x
        what = x.replace("（正在被使用）", "").strip()
        if what and not what.startswith("（读数里没有"):
            products.append({"what": what, "in_use": in_use})
    risks = [x for x in split(grab("画面线索")) if not x.startswith("（读数里没有")]
    if not (setting or people or products or risks):
        return None
    return {"setting": setting or "", "people": people, "products": products,
            "risk_cues": risks, "visible_marks": [], "text_script": "", "unclear": []}


def strip_scene_blocks(text):
    """把正文里的【/图 N 画面读数】块剥掉 —— 只用于**文字重叠**那一侧。

    为什么：画面读数那几十个字的「- 场景：… / - 人物：…」会把字符二元组的分母撑大，
    实测让「文字分」从 0.8 掉到 0.5 量级，反而把真命中挤下去（325 张图：83% → 74%）。
    画面信息已经有专门一路（`scene_cues`），文字这一路只该看**素材本来的文字**。
    """
    import re as _re
    t = str(text or "")
    # 画面读数块：`【图 N 画面读数（…）】…【/图 N 画面读数】` ⇒ 整块删掉
    t = _re.sub(r"【图\s*\d+\s*画面读数[^】]*】[\s\S]*?【/图\s*\d+\s*画面读数】", "", t)
    # 守衡的图内文字外壳：`【图 N 内文字…】\n<body>\n【/图 N】` ⇒ 只留 body
    # ★★ 2026-10-20 修：这一条此前**从来没匹配上过**。正则写的是「图内文字」，
    #   而 `agent.mjs:639` 实际产出的外壳是 `【图 ${i} 内文字｜${lines} 行】`（**少一个「图」**）。
    #   代价：外壳行一直留在正文里，进 `input_lines` 后**稀释行重合率**（29 行 OCR + 2 行外壳
    #   ⇒ 分母 31），也把 `29 行` 这类元信息混进短语。两种写法都收（`(?:图\s*)?`）。
    t = _re.sub(r"【图\s*\d+\s*(?:图\s*)?内文字[^】]*】\s*([\s\S]*?)\s*【/图\s*\d+】", r"\1", t)
    return t


def rule_cues(r):
    """规则的一侧线索：显式 visual_cues + 正文里的关键名词（长词切出来当线索）。"""
    cues = {"setting": set(), "people": set(), "products": set(), "risks": set()}
    for c in (r.get("visual_cues") or []):
        if ":" in c:
            k, v = c.split(":", 1)
            if k == "场景":
                cues["setting"].add(v)
            elif k == "人物":
                cues["people"].add(v)
            elif k == "物件":
                cues["products"].add(v[:12])
            elif k == "线索":
                cues["risks"].add(v)
    return cues


def scene_cues(scene):
    cues = {"setting": set(), "people": set(), "products": set(), "risks": set()}
    if not scene:
        return cues
    st = str(scene.get("setting") or "")
    if st and not st.startswith(("未给", "看不清")):
        cues["setting"].add(st.split("（")[0])
    for p in (scene.get("people") or []):
        k = str(p.get("kind") or "").strip()
        if k and k != "分不清":
            cues["people"].add(k)
    for p in (scene.get("products") or []):
        w = str(p.get("what") or "").strip()
        if w:
            cues["products"].add(w[:12])
    for c in (scene.get("risk_cues") or []):
        cues["risks"].add(str(c)[:20])
    return cues


def _overlap(a, b):
    """字符二元组重叠（用于物件/线索的模糊对上，如「婴儿车」vs「婴儿推车」）。"""
    A, B = _bigrams("".join(a)), _bigrams("".join(b))
    if not A or not B:
        return 0.0
    return len(A & B) / max(1, min(len(A), len(B)))


def _cue_weights(rules):
    """线索 IDF：越常见的线索越不值钱（「人物:成人」「线索:婴幼儿出镜」几乎每条都有）。"""
    import math
    df = {}
    for r in rules:
        cs = rule_cues(r)
        seen = set()
        for cat in cs:
            for v in cs[cat]:
                seen.add(cat + "|" + v)
        for k in seen:
            df[k] = df.get(k, 0) + 1
    n = max(1, len(rules))
    return lambda cat, v: 1.0 + math.log((1 + n) / (1 + df.get(cat + "|" + v, 0)))


_SHA_RE = None


def image_shas_in(text):
    """从素材正文里抓**图片指纹**（`sha256=<64 hex>`），返回小写集合。

    为什么它是第一优先级：OCR 文本两套引擎会给出不同结果（守衡用 base/ocr_vision，
    知识库用 ocr.jxa.js），逐字比对会失配；而**图片字节的 sha256 是同一把尺子** ——
    同一个文件两边算出来必然相同。守衡只需把这张图的 sha 写进正文一行。
    """
    import re as _re
    return {m.group(1).lower() for m in _re.finditer(r"sha256\s*[=:]\s*([0-9a-fA-F]{64})", str(text or ""))}


def rule_fingerprints(rule, min_len=1):
    """规则名下每张图的**图内文字指纹**（归一化后的整段 OCR）。

    用途：来图与库内某张图**就是同一张**（或同一版素材）时，OCR 会逐字重合 ⇒ 直接判命中 1.0。
    这是「库内图必须 100% 命中」那条硬要求的落点 —— 不做相似度，做**逐字包含**。
    """
    out = []
    for im in (rule.get("image_refs") or []):
        t = _norm(im.get("ocr_text") or "")
        # ★ 2026-10-20（串图修复 ②）：**按下标对齐**，OCR 不足的图留 None 占位 ——
        #   原先直接跳过，会让 `fingerprints[i]` 与 `image_refs[i]` 错位，
        #   命中后说不清「到底是库里哪一张图对上了」，而归属判据要的正是这一格。
        out.append(t if len(t) >= min_len else None)
    return out


_FP_CACHE = {}
_LINES_CACHE = {}


def lines_of(text):
    """归一化后的**行集合**（去空、去短行）。

    为什么要有它：守衡会先把**水印行**（用户名/工号，如「刘华丽」「5615 ROOT」）从素材正文里摘掉
    （`ocr_watermark.mjs`，2026-10-09 Owner 定的）。摘掉之后输入与库内 OCR **不再逐字相等**，
    但**行集合仍是子集** ⇒ 用行重合率兜住这批图（实测 339 张里有 23 张带水印字样）。
    """
    out = set()
    for ln in str(text or "").splitlines():
        n = _norm(ln)
        if len(n) >= 4:
            out.add(n)
    return out


def fp_lines_of(rule):
    rid = rule.get("rule_id")
    if rid in _LINES_CACHE:
        return _LINES_CACHE[rid]
    v = [lines_of(im.get("ocr_text") or "") for im in (rule.get("image_refs") or [])]
    _LINES_CACHE[rid] = v
    return v


def line_overlap(inp_lines, fp_lines):
    """输入行落在该图行集合里的比例（0~1）。输入行 <4 时不判（太短没有判别力）。"""
    if len(inp_lines) < 4 or not fp_lines:
        return 0.0
    best = 0.0
    for fl in fp_lines:
        if not fl:
            continue
        best = max(best, len(inp_lines & fl) / max(1, len(inp_lines)))
    return best


def fp_of(rule):
    """规则指纹**算一次、进程内复用**。

    为什么必须缓存：476 条规则 × 每张图一次查询 ⇒ 每轮都要对每条规则的全部 OCR 文本做归一化，
    实测把 339 张图的验收拖到超过 60 秒（超时被杀）。缓存后只在首轮付一次成本。
    """
    rid = rule.get("rule_id")
    if rid in _FP_CACHE:
        return _FP_CACHE[rid]
    v = rule_fingerprints(rule)
    _FP_CACHE[rid] = v
    return v


_PHRASES_CACHE = {}


def fp_phrases_of(rule):
    """规则名下每张图的**短语集合**（①c 用）。缓存理由同 `fp_of`。"""
    rid = rule.get("rule_id")
    if rid in _PHRASES_CACHE:
        return _PHRASES_CACHE[rid]
    v = [phrases_of(im.get("ocr_text") or "") for im in (rule.get("image_refs") or [])]
    _PHRASES_CACHE[rid] = v
    return v


def score_rule(rule, rcues, input_text, input_cues, w=None, fingerprints=None, input_norm=None,
               fp_lines=None, inp_lines=None, input_shas=None, fp_phrases=None, input_phrases=None,
               matched=None):
    """`matched`（2026-10-20 加）：调用方传进来的 dict，同图命中时写回
    `matched["image"]`＝**触发命中的那张库内图**（image_refs 里的那一项）。

    为什么必须带出来：归属判据（串图修复 ②）要回答的不是「哪条规则命中」，
    而是「**库里哪一张图**对上了、那张图在这条记录里是什么角色」。没有这一格，
    就只能退化成按记录归属 —— 那正是串图的成因。
    """
    w = w or (lambda cat, v: 1.0)
    hit_w = 0.0
    total_w = 0.0
    reasons = []
    for cat in ("setting", "people", "products", "risks"):
        for a in input_cues[cat]:
            total_w += w(cat, a)
    # 场景：完全相同 / 粗类相近
    matched_scene = set()
    for a in input_cues["setting"]:
        for b in rcues["setting"]:
            if a == b:
                hit_w += w("setting", a)
                reasons.append("场景一致：%s" % a)
                matched_scene.add(a)
                break
            if ("室内" in a and "室内" in b) or ("户外" in a and "户外" in b):
                hit_w += 0.5 * w("setting", a)
                reasons.append("场景相近：%s≈%s" % (a, b))
                matched_scene.add(a)
                break
    # 风险线索：包含关系即算
    for a in input_cues["risks"]:
        for b in rcues["risks"]:
            if a == b or a in b or b in a:
                hit_w += w("risks", a)
                reasons.append("风险线索：%s" % a)
                break
    # 人物类型
    for a in input_cues["people"] & rcues["people"]:
        hit_w += w("people", a)
        reasons.append("人物：%s" % a)
    # 物件：二元组重叠 ≥0.5
    for a in input_cues["products"]:
        for b in rcues["products"]:
            # ★ 收紧（2026-10-20 实测）：0.5 太松 —— 「白色背景板」vs「白色背心与蓝色长裙」
            #   靠一个「白色」就当同一个物件。改成：共同字 ≥4 且重叠率 ≥0.66。
            if len(a) >= 4 and len(b) >= 4 and _overlap(a, b) >= 0.66:
                hit_w += w("products", a)
                reasons.append("物件：%s≈%s" % (a, b))
                break
    # ── ① 同图指纹（逐字包含）⇒ 直接 1.0 ──────────────────────────────────
    # ── ⓿ 图片指纹：图字节 sha256 相等 ⇒ 就是同一张图（与 OCR 引擎无关，最强判据）
    if input_shas:
        for im in (rule.get("image_refs") or []):
            if (im.get("sha256") or "").lower() in input_shas:
                if isinstance(matched, dict):
                    matched["image"] = im
                return 1.0, 1.0, 1.0, ["图片指纹：字节 sha256 相同（%s…）" % (im.get("sha256") or "")[:12]], "同图", 4
    _imgs = rule.get("image_refs") or []
    if fingerprints and input_norm:
        for _i, fp in enumerate(fingerprints):
            if not fp:                       # 该图没有 OCR ⇒ 占位，跳过（下标不动）
                continue
            # ① 逐字相等（**任意长度**都收）：输入就是这张图的 OCR ⇒ 就是同一张图。
            #    长度不设下限：实测有 2 字 OCR 的图（「妈妈」），设下限会让它们永远命不中。
            #    假阳性风险由「整串相等」自身兜住 —— 只有同一串文字才算。
            if fp == input_norm:
                if isinstance(matched, dict) and _i < len(_imgs):
                    matched["image"] = _imgs[_i]
                return 1.0, 1.0, 1.0, ["同图指纹：图内文字逐字相等（%d 字）" % len(fp)], "同图", 3
            # ② 长指纹被完整包含（素材正文带前后缀时）：≥24 字且占比 ≥50%。
            #    ⚠️ 不能一律用 `in`：8~20 字的短指纹会在大段 OCR 里被偶然包含
            #    （实测 top1 从 83% 掉到 54%，假「同图」把真命中挤掉）。
            if fp in input_norm:
                slack = len(input_norm) - len(fp)
                # ②a 长指纹：≥24 字且占输入 ≥50%（正文前后带了大段别的内容时，仍算同图）
                # ②b 短指纹：只在**输入几乎就是这张图的文字**时才算（前后缀 ≤60 字）——
                #     守衡的「【图 N 图内文字…】…【/图 N】」外壳约 20~40 字，走这一支。
                if len(fp) >= 24 and len(fp) >= 0.5 * len(input_norm):
                    if isinstance(matched, dict) and _i < len(_imgs):
                        matched["image"] = _imgs[_i]
                    return 1.0, 1.0, 1.0, ["同图指纹：图内文字逐字包含（%d 字，前后缀 %d）" % (len(fp), slack)], "同图", 2
    # ①b 行级兜底：守衡摘掉水印行后仍能认出来（行重合率 ≥0.7）
    if fp_lines and inp_lines:
        _best, _bi = 0.0, -1
        for _i, fl in enumerate(fp_lines):
            if not fl:
                continue
            _o = len(inp_lines & fl) / max(1, len(inp_lines)) if len(inp_lines) >= 4 else 0.0
            if _o > _best:
                _best, _bi = _o, _i
        lo = _best
        if lo >= 0.7:
            if isinstance(matched, dict) and 0 <= _bi < len(_imgs):
                matched["image"] = _imgs[_bi]
            return 1.0, 1.0, lo, ["同图指纹：图内文字行重合 %.0f%%（水印行被摘除也能认）" % (lo * 100)], "同图", 2
    # ── ①c 关键短语指纹（2026-10-20 加；**抗噪档**，见文件头 PHRASE_MIN_SHARED 那段）──────
    #   排在 ①②①b 之后、视觉/文字算分之前：前三条路要求"文字几乎一样"，这一条只要求
    #   "**好几句话对得上**" —— 压缩、错字、重排都不影响，但跨题材凑不出来。
    #   ⚠️ 它**不放宽假命中的口子**：跨题材规则实测 0 个共同短语，而阈值要 5 个。
    if fp_phrases and input_phrases:
        best_shared, best_i = 0, -1
        for _i, ph in enumerate(fp_phrases):
            n = len(ph & input_phrases)
            if n > best_shared:
                best_shared, best_i = n, _i
        if best_shared >= PHRASE_MIN_SHARED:
            if isinstance(matched, dict) and 0 <= best_i < len(_imgs):
                matched["image"] = _imgs[best_i]
            return (1.0, 1.0, 1.0,
                    ["同图指纹：共同关键短语 %d 个（图内文字有压缩/错字也能认）" % best_shared],
                    "同图", 2)
    visual = min(1.0, hit_w / max(total_w, 1e-6)) if total_w else 0.0

    # 文字路：规则正文 + 它名下每张图的 OCR（来图与历史图常常是同一套英文文案）
    # ★ 2026-10-20 修：原先按 min 长度归一 ⇒ 规则侧只有几个字时，重叠两三个二元组就满分 1.00，
    #   实测把「Mom-to-Mom Chats」这种短文本抬成 1.00 并挤掉真命中。改成按 max 归一 + 至少 3 个共同二元组。
    A = _bigrams(input_text)
    best_txt = 0.0
    if A:
        B = _bigrams(rule.get("rule_text") or "")
        if B and len(A & B) >= 3:
            best_txt = len(A & B) / max(len(A), len(B))
        for im in (rule.get("image_refs") or []):
            C = _bigrams(im.get("ocr_text") or "")
            if C and len(A & C) >= 3:
                best_txt = max(best_txt, 1.2 * len(A & C) / max(len(A), len(C)))
        best_txt = min(best_txt, 1.0)
    text = best_txt

    # ★ 落判据（2026-10-20）：**只对上"场景"不算命中** —— 实测通用营销文案 + 影棚读数
    #   会靠「场景一致：影棚」凑到 0.32 并压过阈值。要求至少一条**非场景**线索，
    #   或文字重叠 ≥0.30，才允许进入候选。
    non_scene = any("场景" not in r for r in reasons)
    if input_cues["setting"] and not non_scene and best_txt < 0.30:
        return 0.0, visual, text, [], "仅场景一致（不计命中）", 0
    has_scene = any(input_cues[c] for c in input_cues)
    if has_scene and A:
        score = 0.6 * visual + 0.4 * text
        why = "画面+文字"
    elif has_scene:
        score = visual
        why = "仅画面"
    else:
        score = text
        why = "仅文字"
    return score, visual, text, reasons, why, 0


def load_rules(path=RULES):
    out = []
    if not os.path.exists(path):
        return out
    for line in open(path, encoding="utf-8"):
        if line.strip():
            out.append(json.loads(line))
    return out


def _image_roles():
    """图片归属角色（`kb/l3/registry/image_roles.json`，由 `kb/l8/image_roles.py` 生成）。

    ⚠️ 文件不存在 ⇒ 返回 missing 标记，**不做归属门控**（并让调用方把这件事写进 trace）。
    为什么不 fail-closed：门控是**抑制**装置，产物缺失时把它当成“全部不可引用”会让整层
    静默失效（比串图更难发现）。缺件靠 `image_roles --selftest` + 评审链的 trace 曝光。
    """
    global _ROLES_CACHE
    if _ROLES_CACHE is not None:
        return _ROLES_CACHE
    p = os.path.join(_KB_ROOT, "l3", "registry", "image_roles.json")
    if not os.path.exists(p):
        _ROLES_CACHE = {"records": {}, "sha": {}, "stats": {}, "missing": True}
        return _ROLES_CACHE
    try:
        sys.path.insert(0, _KB_ROOT)
        import importlib.util as _ilu
        _spec = _ilu.spec_from_file_location(
            "_kb_image_roles", os.path.join(_KB_ROOT, "l8", "image_roles.py"))
        _mod = _ilu.module_from_spec(_spec)
        _spec.loader.exec_module(_mod)
        _ROLES_CACHE = _mod.load_roles(p)
    except Exception:                              # noqa: BLE001 —— 归属算不出来不影响检索
        _ROLES_CACHE = {"records": {}, "sha": {}, "stats": {}, "error": "load_failed"}
    return _ROLES_CACHE


_ROLES_CACHE = None


def _attribution_for(rule, matched_img):
    """把「命中的那张库内图」翻成归属角色。取不到 ⇒ unknown（保守：调用方按不可引用处理）。"""
    roles = _image_roles()
    if roles.get("missing") or roles.get("error"):
        return "no_roles_artifact", (roles.get("error") or "missing artifact")
    if not matched_img:
        return "semantic", "只对上画面/文字线索，没有图片身份（不是同图）"
    rid = matched_img.get("record_id")
    sha = matched_img.get("sha256")
    p = (roles.get("records") or {}).get(rid) or {}
    for im in (p.get("images") or []):
        if sha and im.get("sha256") == sha:
            return im.get("role") or "unknown", im.get("why") or ""
    if sha and (roles.get("sha") or {}).get(sha):
        return roles["sha"][sha], "按 sha 索引取角色"
    return "unknown", "该记录/该图不在 image_roles 产物里（没有媒体台账 sha）"


def match(text="", scene=None, top=5, min_score=0.40, rules=None):
    rules = rules if rules is not None else load_rules()
    if scene is None:
        scene = scene_from_text(text)      # 守衡把画面读数拼在正文里 ⇒ 自动启用画面路
    text = strip_scene_blocks(text)        # 文字重叠只看素材本来的文字（理由见该函数头注）
    in_cues = scene_cues(scene)
    input_norm = _norm(text)
    input_lines = lines_of(text)
    input_shas = image_shas_in(text)
    input_phrases = phrases_of(text)        # ①c：整段只算一次
    w = _cue_weights(rules)
    hits = []
    for r in rules:
        _mi = {}
        sc, vis, txt, reasons, why, rank = score_rule(r, rule_cues(r), text, in_cues, w,
                                                fingerprints=fp_of(r),
                                                input_norm=input_norm,
                                                fp_lines=fp_lines_of(r),
                                                inp_lines=input_lines,
                                                input_shas=input_shas,
                                                fp_phrases=fp_phrases_of(r),
                                                input_phrases=input_phrases,
                                                matched=_mi)
        if sc < min_score:
            continue
        _mimg = _mi.get("image") or None
        _attr, _attr_why = _attribution_for(r, _mimg)
        hits.append({"article_no": r.get("article_no"), "rule_id": r.get("rule_id"), "match_rank": rank,
                     "rule_code": r.get("rule_code"), "rule_kind": r.get("rule_kind"),
                     "confidence": r.get("confidence"),
                     "rule_text": r.get("rule_text"),
                     "action": r.get("action"),
                     "score": round(sc, 3), "visual_score": round(vis, 2), "text_score": round(txt, 3),
                     # ★ 2026-10-20（串图修复 ②）：命中的是**哪一张库内图** + 它的归属角色
                     #   （subject / record_level / shared_reference / unknown / semantic）。
                     #   只有 subject 才允许被评审链当成「这张图的依据」。
                     "attribution": _attr, "attribution_why": _attr_why,
                     "matched_image": ({"record_id": (_mimg or {}).get("record_id"),
                                        "file_token": (_mimg or {}).get("file_token"),
                                        "sha256": (_mimg or {}).get("sha256"),
                                        "anchor": (_mimg or {}).get("anchor"),
                                        "seq": (_mimg or {}).get("seq")} if _mimg else None),
                     "image_refs": [im.get("file_token") for im in (r.get("image_refs") or [])][:5],
                     "evidence": (r.get("evidence_units") or [])[:1]})
    hits.sort(key=lambda x: (-x["score"], -x.get("match_rank", 0)))
    return hits[:top]


def selftest():
    rules = [
        {"article_no": "N-1.9", "rule_id": "r1", "rule_text": "宝宝睡在柔软的枕头上，呈现危险的错误睡眠场景",
         "visual_cues": ["场景:卧室", "人物:婴幼儿", "物件:枕头", "线索:婴幼儿出镜"],
         "action": {"kind": "prohibit", "replacement": None}, "image_refs": [], "evidence_units": []},
        {"article_no": "N-1.44", "rule_id": "r2", "rule_text": "EDM 版头的单词错了，mounths 应为 months",
         "visual_cues": ["场景:影棚", "物件:版头"], "action": {"kind": "prohibit", "replacement": None},
         "image_refs": [], "evidence_units": []},
    ]
    cases = []
    # 正例：宝宝睡枕头 + 卧室
    h = match("", {"setting": "卧室", "people": [{"kind": "婴幼儿", "doing": "躺在枕头上"}],
                   "products": [{"what": "枕头"}], "risk_cues": ["婴幼儿出镜"]}, rules=rules)
    cases.append(("宝宝睡枕头 → 命中 N-1.9", bool(h) and h[0]["article_no"] == "N-1.9", h[:1]))
    # 反例：厨房里的成人 → 不该命中睡眠规则
    h2 = match("", {"setting": "厨房", "people": [{"kind": "成人", "doing": "做饭"}],
                    "products": [{"what": "锅"}], "risk_cues": []}, rules=rules)
    cases.append(("厨房做饭 → 不命中", not h2, h2[:1]))
    # 文字路：英文 OCR 提到 mounths
    h3 = match("Flash sale mounths end soon", None, rules=rules)
    cases.append(("文字命中（若词形一致）", True, h3[:1]))   # 中英不互通 ⇒ 只验不抛

    # ── ①c 关键短语指纹（2026-10-20 真单回归：飞书 IM 压缩导致同图认不出）──────────────
    # 这两段都是**真实读数**（2026-10-20 15:16 那单）：库版是表附件的原图 OCR，
    # 压缩版是守衡收到 IM 压缩图后读出来的（`Your Chance To Min` / `fc chirv.es c win wecky rewrds`）。
    LIB_OCR = ("MOmCOZY\nMomcozy Mom and More\nYour Chance To Win\nA Momcozy M5\nWearable Breast Pump\n"
               "Giveaway\nJoin the Momcozy Fans Club\nfor weekly rewards and real mom support.\n"
               "Easy to Join.\nRewards to Win.\nReal Moms. Real Support.\nHow to enter\n1.Join the group\n"
               "2.Find the featured post\n3.Enter the giveaway\nFind the #MomAndMore giveaway post\n"
               "and follow the instructions to enter.\nWherever you are in motherhood,\n"
               "there's a place for you here.")
    COMPRESSED = ("【图 1 内文字｜29 行】\nMOmCOZY\nMomcozy Mom and More\nYour Chance To Min\nA Momcozy W1\n"
                  "Wearable Breast Pump\nGiveaway 4\nJoin the Momcozy Fans Club\nfor weekly rewards and real\n"
                  "nom support.\nEasy to Join.\nRewards to Win.\nHow to enter\n1.Join the group\n"
                  "ioin tho Momcory Fara Chb\n2.Find the featured post\n"
                  "soction at the top cfthe Facobook group\n3.Enter the giveaway\n"
                  "Find the #MamAndMare giveanay Poot\nand folkow the instructions to onter.\n"
                  "Wherever you are in motherhood，\nthere's a place for you here.\nJon other moms、\n【/图 1】")
    GIVEAWAY = {"article_no": "N-1.39", "rule_id": "r3", "rule_text": "修复产品细节、光影、清晰度，替换奶瓶清洗剂片包装图",
                "visual_cues": [], "action": {"kind": "prohibit", "replacement": None},
                "image_refs": [{"anchor": "#素材/recX/图片素材/#img.1", "ocr_text": LIB_OCR}],
                "evidence_units": []}
    # 反向对照：15:12 那单**真的假命中过**的跨题材规则（视频画面 / 中文审核意见）
    OTHER = {"article_no": "N-1.328", "rule_id": "r4", "rule_text": "视频 需求里特意写画面不要过于完美",
             "visual_cues": [], "action": {"kind": "prohibit", "replacement": None},
             "image_refs": [{"anchor": "#素材/recY/图片素材/#img.1",
                             "ocr_text": "【原则性错误】视频 需求里特意写画面不要过于完美，"
                                         "现在的画面就是感觉太完美了，妈妈的状态也太完美了"}],
             "evidence_units": []}
    h4 = match(COMPRESSED, None, rules=[GIVEAWAY, OTHER])
    cases.append(("①c 压缩图仍认得出同图 → N-1.39 命中且 rank≥2",
                  any(x["article_no"] == "N-1.39" and x["match_rank"] >= 2 for x in h4), h4[:1]))
    cases.append(("①c 反向对照：跨题材 N-1.328 **不许**被认成同图",
                  not any(x["article_no"] == "N-1.328" and x["match_rank"] >= 2 for x in h4), h4[:2]))
    # 反向对照②：**同品牌、连导航栏都同款、同题材，但不是同一张图**（实测只凑到 3 个共同短语：
    #   `enter the giveaway` / `the instructions to` / `wearable breast pump`）。
    #   ★ 阈值 5 的**区分力全靠这一条量**：把 PHRASE_MIN_SHARED 改到 3 以下 ⇒ 本条精确变红。
    NEAR_OCR = ("momCOZY\nBreast Pumps\nBras\nBody Pillows\nPregnancy\nA Momcozy M5\n"
                "wearable breast pump\ncould be yours\nWin a Momcozy\nM5 wearable breast pump\n"
                "How to enter\n1.Join the group\n2.Find the featured post\n"
                "3.Enter the giveaway\nFind the Breastfeeding Month giveaway\n"
                "post and follow the instructions to enter.")
    NEAR = {"article_no": "N-1.999", "rule_id": "r5", "rule_text": "同品牌近邻图（不是同一张）",
            "visual_cues": [], "action": {"kind": "prohibit", "replacement": None},
            "image_refs": [{"anchor": "#素材/recZ/图片素材/#img.2", "ocr_text": NEAR_OCR}],
            "evidence_units": []}
    h6 = match(COMPRESSED, None, rules=[GIVEAWAY, NEAR])
    cases.append(("①c 反向对照②：同品牌近邻图（仅 3 个短语）**不许**被认成同图",
                  not any(x["article_no"] == "N-1.999" and x["match_rank"] >= 2 for x in h6), h6[:2]))
    # 反向对照②：同一份库版 OCR 原样输入（无噪声）⇒ 仍走①②，不许因为新分支改变旧行为
    h5 = match(LIB_OCR, None, rules=[GIVEAWAY])
    cases.append(("①c 不夺权：无噪声输入仍命中（rank 3 逐字档）",
                  bool(h5) and h5[0]["match_rank"] == 3, h5[:1]))
    # 反向对照③：外壳必须被剥掉（2026-10-20 修的第二个 bug：正则原写「图内文字」）
    cases.append(("外壳剥离：「内文字｜29 行」不许留在正文里",
                  "29 行" not in strip_scene_blocks(COMPRESSED), strip_scene_blocks(COMPRESSED)[:40]))
    ok = all(c[1] for c in cases)
    for name, okc, _ in cases:
        print(("  ✅ " if okc else "  ❌ ") + name)
    print("selftest %s（%d/%d）" % ("PASS" if ok else "FAIL", sum(1 for c in cases if c[1]), len(cases)))
    return 0 if ok else 3


def main(argv):
    if "--selftest" in argv:
        return selftest()
    text = ""
    scene = None
    top = 5
    for i, a in enumerate(argv):
        if a == "--text" and i + 1 < len(argv):
            text = argv[i + 1]
        elif a == "--scene-json" and i + 1 < len(argv):
            scene = json.load(open(argv[i + 1], encoding="utf-8"))
        elif a == "--top" and i + 1 < len(argv):
            top = int(argv[i + 1])
    hits = match(text, scene, top=top)
    print(json.dumps({"hits": hits, "count": len(hits)}, ensure_ascii=False, indent=1))
    return 0 if hits else 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
