#!/usr/bin/env python3
"""l0_facets.py —— 从**命中的 L0 记录**里取「产品线 / 渠道」。

Owner 2026-10-06 现场要求：「里面的产品线和渠道都是空或者未指定，
运行任务的时候**从知识库命中**产品线和渠道的都填写进去」。

── 为什么要有它

飞书评审表里那两列**恒空或写「未指定」**，而**库里本来就有** ——
只是没有任何代码去取。素材正文里猜（"M5 吸奶器"⇒产品线 M5）是**猜**；
命中记录里 `品线=[吸奶器]` 是**读数**。这一件只做后者。

── 数据在哪（**逐表实测登记**，不是照名字猜的）

`kb/l0/_archive/schema_snapshots/` 里 11 张 L0 表逐张核过（2026-10-06）。
**只有「内容记录」上的那两列才算数**：

| L0 表 | 取 | 产品线 | 渠道 | 为什么 |
|---|---|---|---|---|
| 广告文案明细 | ✅ | `品线` | `平台` | **投放中的广告**（内容记录）——「这条广告属于哪条产品线/投在哪」 |
| 负面样本 | ✅ | `品线` | `渠道/市场` | **送审素材**（内容记录） |
| 品线内容边界规则库 | ❌ | ~~`适用产品`~~ | — | 那是**规则自己的适用范围**（`W1、M5、M6、M9、Air1`），不是素材的产品线 |
| 风险文案改写建议库（分型号分渠道） | ❌ | ~~`适用型号`~~ | ~~`渠道`~~ | 同上：那是**建议的适用面与分类维度** |
| 其余 7 张 | ❌ | — | — | 两样都没有 |

★ 第三、四行是 **2026-10-06 收紧掉的**（第一版把它们算进来了，**是错的**）：
  实测 H06 命中落在边界规则库，`适用产品 = ["W1","M5","M6","M9","Air1"]` ——
  照第一版会把「五个产品线」标到一条 **M5** 文案上。**填错比留空坏得多**，所以宁可空。

── 三条铁律（每条都有代价）

1. **只认登记过的字段名** —— 取不到就**留空**，不许从别的字段凑、不许从素材正文猜。
   表里已经出现过一次脏数据：`产品线` 那一格被写进了**整段视频读数**（见
   `correction_20261006_p0_report_layout` 之后的现场排查）。**猜测只会再造一条。**
2. **带出来路**：`from` 记下「哪张表 · 哪个字段」，人看表时能回源核对。
3. **只读**：不写库、不写飞书、不碰锁。取不到不是错误（返回空串），不抛异常。
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)                       # = kb/
L0_RECORDS = os.path.join(ROOT, "l0", "records")

#: 产品线类字段名 —— **只认「内容记录」上的那一列**。
#  ★ 2026-10-06 收紧（第一版把 `适用型号`/`适用产品` 也算进来了，**是错的**）：
#    实测 H06 那条命中落在 `品线内容边界规则库`，该记录 `适用产品 = ["W1","M5","M6","M9","Air1"]`
#    —— 那是**规则自己的适用范围**（这条规则管哪些产品），
#    **不是这条素材的产品线**。填进「产品线」列 = 给一条 M5 的文案标上「五个产品线」。
#    `风险文案改写建议库（分型号分渠道）` 的 `适用型号` 同理（那是建议的适用面）。
#    ⇒ 只认 `品线`：它出现在 `广告文案明细`（投放中的广告）与 `负面样本`（送审素材）上，
#      **这两个都是内容记录**，那才是"这条素材属于哪条产品线"。
PRODUCT_FIELDS = ("品线",)
#: 渠道类字段名 —— 同理，只认**内容记录**上的那两列。
#  `广告文案明细.平台`（Google/Meta…）与 `负面样本.渠道/市场`（社媒…）是**实际投放/来源**；
#  `风险文案改写建议库（分型号分渠道）.渠道` 是**规则的分类维度**，不算。
CHANNEL_FIELDS = ("平台", "渠道/市场")

# ── 受控词表（**从库内实测导出**，不是手写的；见 `--vocab`）──────────────────────────
#   2026-10-06 从 `kb/l0/records/` 逐条数出来的取值分布：
#     品线：吸奶器 340 / 其他 62 / 婴幼儿用品 27 / 洗瓶机·喂养 17 / 婴儿监视器 13
#     渠道：Google 262 / 社媒 85 / 其他 34 / Meta 27 / 展会 22 / EDM 18 / 亚马逊 11
#   ★ **catch-all 一律剔除**（`其他`）：它不是"某个产品线"，而是"没归类"。
#     留在表里必然误报 —— 素材里出现「其他产品」四个字就会被填成 `品线=其他`。
PRODUCT_LINE_VOCAB = ("吸奶器", "婴幼儿用品", "洗瓶机/喂养", "婴儿监视器")
CHANNEL_VOCAB = ("Google", "Meta", "亚马逊", "社媒", "EDM", "展会")
#: 英文词按**词边界**匹配（`Google` 不许命中 `Googleplex`）；中文词按逐字包含。
_LATIN = ("Google", "Meta", "EDM")


# ── ★★ 记录路的前置闸：**这条记录是不是本素材本人**（2026-10-06 加；此前是错的）────────
#  ★ 为什么必须有这道闸（实测，2026-10-06）：
#    ② 那条素材 `M6 吸奶器能催奶，模拟婴儿吸吮节奏，还是医生推荐的。` 的命中锚点落在
#    `广告文案明细/recvuJYdOb1Rm1` —— 而那是一条**真实的 Google 广告**：
#    `外部广告ID = GG-12d45aa812b7`、`近7天展示 = 8372`、`近7天费用USD = 117.28`、
#    `平台 = ["Google"]`、`Primary Text = "Pump Anywhere, Hands Completely Free | …"`。
#    它的 `品线/平台` 描述的是**那条样本广告投在哪**，**不是本次送审素材**。
#    旧口径「先命中记录、后素材原文」会把样本的 `平台=Google` 直接烧进本次的「渠道」列 ——
#    卡里、文档里、表行里各写一个值，而那个 Google **无出处**。
#    ⇒ 比空值更坏：空值人会去补，错值人不会再回头看。
#  ★ 新口径（**fail-closed**）：只有确认该记录**就是本素材**时才采信它的字段；
#    否则一律回落「素材原文逐字命中受控词」，并把跳过原因记进 `from`（可核对，不静默）。
MATERIAL_MIN_CHARS = 8


def _norm(s):
    """归一化：去空白与标点、统一小写 —— **只用于同一性比对**，不用于展示。"""
    return re.sub(r"[\s\u3000\-—–|｜/、,，。.．;；:：!！?？\"'“”‘’()（）\[\]【】{}<>《》]+", "",
                  str(s or "")).lower()


def record_is_this_material(fields, text):
    """这条 L0 记录**是不是本次送审素材本人** ⇒ `(bool, 一句话说明)`。

    判据：素材原文归一化后**逐字出现在**该记录任一字段值里（含 `Primary Text` 这类正文列）。
    两条边界：
      · 素材归一化后 < `MATERIAL_MIN_CHARS` 字 ⇒ **不确认**（太短，包含判定会误判）——
        宁可为空，也不拿一条短句去认领一条不相干的记录；
      · 判据是**单向包含**（素材 ∈ 记录），不是相等 —— 记录里常带人工补的批注/处理状态。
    """
    m = _norm(text)
    if len(m) < MATERIAL_MIN_CHARS:
        return False, ("素材归一化后仅 %d 字（< %d）⇒ 无法确认这条记录就是它，**不采信**该记录的字段"
                       % (len(m), MATERIAL_MIN_CHARS))
    if not isinstance(fields, dict):
        return False, "记录没有字段 ⇒ 不采信"
    blob = _norm(" ".join(_flat(v) for v in fields.values()))
    if m and m in blob:
        return True, "素材原文**逐字出现在该记录里** ⇒ 认定该记录就是本素材"
    return False, ("素材原文**不在**该记录里 ⇒ 它是命中记录（规则样本/依据），**不是本素材** ⇒ "
                   "不采信它的品线/平台（那是那条样本自己的投放属性）")


def _flat(v):
    """L0 字段值 → 字符串。

    L0 件的形状是 `{"field_id":..,"field_type":..,"value":..,"raw_verbatim":..}`，
    而 `select` 的 `value` 是**列表**（如 `["吸奶器"]`、`["W1","M5"]`）——
    直接 `str()` 会得到 `['吸奶器']`，写进表里就是一行 Python 字面量。
    """
    if isinstance(v, dict):
        v = v.get("value", v.get("raw_verbatim"))
    if isinstance(v, list):
        v = "、".join(str(x).strip() for x in v if x not in (None, ""))
    if v is None:
        return ""
    return str(v).strip()


def _find_record(record_id, table=None):
    """按 anchor 里的表名 / record_id 找 L0 落盘件。

    ★ 表名对不上时**不盲取**（2026-10-06 加的保险）：
      锚点的第一段有时是**库内标签**而不是 L0 表名（实测 `#素材/recvw7XIUgnJYu/图片素材/#img.1`
      —— `素材` 在 L0 里没有这张表）。这时按 record_id 全库找：
        · 找到**恰好一条** → 用它，并在 `from` 里记下**它真实属于哪张表**（透明，可回源）；
        · 找到**多条**（不同表同 id）→ **一条都不用**，返回 None。
      宁可为空，也不能拿"同 id 的另一张表"的记录充数 —— 那种数据**看起来是真的**。
    """
    if not record_id:
        return None
    if table:
        for c in glob.glob(os.path.join(L0_RECORDS, "*__%s" % table, "%s.json" % record_id)):
            return c
    hits = glob.glob(os.path.join(L0_RECORDS, "**", "%s.json" % record_id), recursive=True)
    return hits[0] if len(hits) == 1 else None


def _record_of(anchor):
    """anchor（`#表名/record_id/字段名`）→ (fields dict, 表名) ；取不到 → (None, None)。"""
    if not anchor or not str(anchor).startswith("#"):
        return None, None
    parts = str(anchor).lstrip("#").split("/")
    if len(parts) < 2:
        return None, None
    table, record_id = parts[0], parts[1]
    path = _find_record(record_id, table)
    if not path:
        return None, table
    try:
        d = json.load(open(path, encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None, table
    fs = d.get("fields")
    return (fs if isinstance(fs, dict) else None), (d.get("source_table") or table)


def _pick(fields, names):
    """按登记顺序取第一个非空 —— 返回 (值, 命中的字段名)。**取不到就 ("", None)**。"""
    if not isinstance(fields, dict):
        return "", None
    for n in names:
        if n in fields:
            v = _flat(fields[n])
            if v:
                return v, n
    return "", None


def facets_for_anchor(anchor, text=""):
    """一个 anchor → `{product_line, channel, from}`。取不到的分量为空串，**不抛错**。

    ★ `text` = 本次送审素材原文：**用来判「这条记录是不是本素材本人」**（见
      `record_is_this_material`）。判不过 ⇒ **不采信该记录的字段**，只把原因记进 `from`。
      不给 `text` 时**一律不采信记录**（fail-closed）—— 宁可空，也不拿样本属性充数。
    """
    fields, table = _record_of(anchor)
    out = {"product_line": "", "channel": "", "from": {}, "table": table or ""}
    if not fields:
        return out
    ok, why = record_is_this_material(fields, text)
    out["identity"] = {"is_material": ok, "why": why}
    if not ok:
        out["from"]["skipped_record"] = "%s：%s" % (table or "?", why)
        return out
    pl, plf = _pick(fields, PRODUCT_FIELDS)
    ch, chf = _pick(fields, CHANNEL_FIELDS)
    out["product_line"], out["channel"] = pl, ch
    if plf:
        out["from"]["product_line"] = "%s.%s" % (table or "?", plf)
    if chf:
        out["from"]["channel"] = "%s.%s" % (table or "?", chf)
    return out


def facets_from_text(text):
    """**素材原文**里逐字命中库内受控词 ⇒ 填。

    ★ 为什么允许这条路（Owner 2026-10-06）：
      图片/视频那类单**没有规则命中**（引擎输出里连 `anchor` 都没有）⇒ 记录里取不到任何东西。
      而素材原文（含本机 OCR / 音轨转写）里**常常直接写着**产品线与渠道
      （「吸奶器」「Google」「展会」…）。
      这与「读记录里的字段」同属**确定性匹配**：候选值**全部来自库内实测词表**，
      **不是**让模型按语义猜「M5 吸奶器 ⇒ 产品线 吸奶器」那种推断。
      （后者正是表里那格曾被写进整段视频读数的成因，**不做**。）

    ★ 三条边界：
      1. **catch-all 不进词表**（`其他`）—— 否则「其他产品」四个字就会填出 `品线=其他`；
      2. **英文按词边界**（`Google` 不许命中 `Googleplex`），中文按逐字包含；
      3. **只在记录取不到时兜底**（调用方 `facets_for_anchors` 保证顺序），
         并把来源标成「素材原文逐字命中受控词」—— 与「命中记录.字段」**分开记**。

    返回值形状与 `facets_for_anchor` 一致：`{product_line, channel, from}`。
    """
    s = str(text or "")
    out = {"product_line": "", "channel": "", "from": {}, "table": "（素材原文）"}
    if not s.strip():
        return out

    def _hit(vocab):
        for w in vocab:
            if w in _LATIN:
                if re.search(r"(?<![A-Za-z])%s(?![A-Za-z])" % re.escape(w), s, re.I):
                    return w
            elif w in s:
                return w
        return ""

    pl = _hit(PRODUCT_LINE_VOCAB)
    ch = _hit(CHANNEL_VOCAB)
    out["product_line"], out["channel"] = pl, ch
    if pl:
        out["from"]["product_line"] = "素材原文逐字命中受控词「%s」" % pl
    if ch:
        out["from"]["channel"] = "素材原文逐字命中受控词「%s」" % ch
    return out


def facets_for_anchors(anchors, text=""):
    """多个 anchor → 一个汇总（每个分量取**第一个非空**，并记下它来自哪条）。

    ★ 顺序是**判据的一部分**（2026-10-06 改）：**先「本素材自己的记录」，后素材原文**。
      · 「本素材自己的记录」= 过了 `record_is_this_material` 那道闸的记录（素材原文逐字在它里面）；
      · **判不过的记录一律跳过**（`records_skipped` 留痕）—— 命中的大多是**规则样本/依据记录**，
        它们的 `品线/平台` 是**那条样本自己的投放属性**，拿来当本次素材的属性就是编数据；
      · 记录取不到 ⇒ 回落「素材原文逐字命中受控词」（`text_fallback=true`）。
      ⚠️ 旧口径是「记录优先、不分是不是本素材」，实测把样本的 `平台=Google` 烧进了本次的「渠道」列。

    ★ 为什么是"第一个非空"而不是"投票"：命中的都是同一批送审素材的相关记录，
      产品线/渠道在同一个素材上应当一致；出现不一致时**不该悄悄合并** ——
      所以这里把**所有**取值都带出来（`all_product_lines` / `all_channels`），
      让调用方与看表的人能看见分歧，而不是被压成一个值。
    """
    res = {"product_line": "", "channel": "", "from": {},
           "all_product_lines": [], "all_channels": [], "anchors_used": 0}
    skipped = []
    for a in anchors or []:
        f = facets_for_anchor(a, text=text)
        ident = f.get("identity") or {}
        if ident and not ident.get("is_material"):
            # ★ 记录不是本素材 ⇒ **跳过**（不采信它的字段），原因留痕、不静默。
            if f.get("table"):
                skipped.append({"anchor": a, "table": f.get("table"), "why": ident.get("why")})
            continue
        if not f["table"] and not f["product_line"] and not f["channel"]:
            continue
        res["anchors_used"] += 1
        if f["product_line"]:
            if f["product_line"] not in res["all_product_lines"]:
                res["all_product_lines"].append(f["product_line"])
            if not res["product_line"]:
                res["product_line"] = f["product_line"]
                res["from"]["product_line"] = f["from"].get("product_line")
        if f["channel"]:
            if f["channel"] not in res["all_channels"]:
                res["all_channels"].append(f["channel"])
            if not res["channel"]:
                res["channel"] = f["channel"]
                res["from"]["channel"] = f["from"].get("channel")
    if skipped:
        res["records_skipped"] = skipped
    # ── 兜底：素材原文（只在**该分量仍为空**时用，来源单独标）────────────────────────
    if (not res["product_line"] or not res["channel"]) and str(text or "").strip():
        t = facets_from_text(text)
        if not res["product_line"] and t["product_line"]:
            res["product_line"] = t["product_line"]
            res["from"]["product_line"] = t["from"]["product_line"]
            res["all_product_lines"].append(t["product_line"])
            res["text_fallback"] = True
        if not res["channel"] and t["channel"]:
            res["channel"] = t["channel"]
            res["from"]["channel"] = t["from"]["channel"]
            res["all_channels"].append(t["channel"])
            res["text_fallback"] = True
    return res


def anchors_in(obj, _out=None):
    """递归挖出 JSON 里所有 `anchor` 值（去重、保序）。

    ★ 为什么递归挖而不是写死路径：引擎 JSON 有两种形状（正常路径在顶层、
      拒答路径在 `decision` 里），`review_run.sh` 的 `pick()` 已经在为这件事兜底。
      这里照同一口径办 —— **不要在第二个地方再写一份路径假设**。
    """
    if _out is None:
        _out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "anchor" and isinstance(v, str) and v.startswith("#") and v not in _out:
                _out.append(v)
            else:
                anchors_in(v, _out)
    elif isinstance(obj, list):
        for v in obj:
            anchors_in(v, _out)
    return _out


def _load_engine_json(path):
    """引擎 stdout 可能带前后噪声 —— 用 raw_decode 逐 `{` 试（与 review_run.sh 同一口径）。"""
    raw = open(path, encoding="utf-8", errors="replace").read()
    dec = json.JSONDecoder()
    for cand in (raw,) + tuple(raw[k:] for k, ch in enumerate(raw) if ch == "{"):
        try:
            return dec.raw_decode(cand.lstrip())[0]
        except Exception:                              # noqa: BLE001
            continue
    return {}


def selftest():
    """判据自证（离线）。样本是**真 anchor、真 L0 件**（2026-10-06 实测值），不是编的。"""
    P, F = [], []

    def chk(name, cond, extra=""):
        (P if cond else F).append(name)
        print("  %s %s%s" % ("✅" if cond else "❌", name, ("  " + extra) if extra else ""))

    # ① 记录路的**准入闸**（2026-10-06 改口径）：只有**本素材自己的记录**才准用。
    #    ★ 旧口径（记录优先、不问是谁的记录）实测出过错：② 那条素材 `M6 吸奶器能催奶…` 的命中
    #      落在 `广告文案明细/recvuJYdOb1Rm1`，而那是一条**真实的 Google 广告**
    #      （`外部广告ID GG-12d45aa812b7` / 展示 8372 / 花费 $117.28）
    #      ⇒ 旧口径把它的 `平台=Google` 烧进了本次的「渠道」列。**错的。**
    a1 = "#广告文案明细/recvuJYdOb1B8v/命中片段"
    f1 = facets_for_anchor(a1)                       # 不给素材 ⇒ fail-closed
    chk("① 不给素材原文 ⇒ **不采信记录**（全空）",
        f1["product_line"] == "" and f1["channel"] == "",
        "%r / %r" % (f1["product_line"], f1["channel"]))
    chk("① 跳过必须留痕（`from.skipped_record` 说明为什么）",
        bool(f1["from"].get("skipped_record")), json.dumps(f1["from"], ensure_ascii=False))

    # ①b **正例对照**：素材**就是**该记录本人 ⇒ 记录路生效。
    #    夹具用该记录自己的 `Primary Text`（真数据，不是我编的）。
    _fs, _tb = _record_of(a1)
    _self_text = _flat((_fs or {}).get("Primary Text"))
    chk("①b 夹具取自真记录（该记录 Primary Text 非空）", bool(_self_text), repr(_self_text[:40]))
    f1b = facets_for_anchor(a1, text=_self_text)
    chk("①b 素材就是该记录本人 ⇒ 取到 产品线=吸奶器 / 渠道=Google",
        f1b["product_line"] == "吸奶器" and f1b["channel"] == "Google",
        "%r / %r" % (f1b["product_line"], f1b["channel"]))
    chk("①b 带出来路（哪张表·哪个字段）",
        f1b["from"].get("product_line", "").endswith(".品线")
        and f1b["from"].get("channel", "").endswith(".平台"),
        json.dumps(f1b["from"], ensure_ascii=False))

    # ①c **负例对照**：素材**不是**该记录 ⇒ 判不过、取不到样本的 Google。
    f1c = facets_for_anchor(a1, text="M6 吸奶器能催奶，模拟婴儿吸吮节奏，还是医生推荐的。")
    chk("①c 素材不是该记录（用②那条真素材）⇒ 取不到样本的 Google",
        f1c["product_line"] == "" and f1c["channel"] == "",
        "产品线=%r 渠道=%r" % (f1c["product_line"], f1c["channel"]))

    # ①d 短素材闸：归一化后 < `MATERIAL_MIN_CHARS` ⇒ 不许认领记录（包含判定会误判）
    f1d = facets_for_anchor(a1, text="吸奶器")
    chk("①d 反向对照：素材太短（< %d 字）⇒ 不确认、取不到值" % MATERIAL_MIN_CHARS,
        f1d["product_line"] == "" and f1d["channel"] == "", json.dumps(f1d, ensure_ascii=False))

    # ② 同一张表的**另一条**记录同样判不过 ⇒ 闸是普遍的，不是针对某一条
    f2 = facets_for_anchor("#广告文案明细/recvuJYdOb1u94/命中片段",
                           text="M6 吸奶器能催奶，模拟婴儿吸吮节奏，还是医生推荐的。")
    chk("② 同表另一条记录同样判不过（产品线/渠道 皆空）",
        f2["product_line"] == "" and f2["channel"] == "",
        "%r / %r" % (f2["product_line"], f2["channel"]))

    # ③ **规则库那两张表不算** —— 它们那两列是**规则自己的适用范围**，不是素材的产品线。
    #    ★ 第一版把 `适用产品`/`适用型号` 也算成产品线，**是错的**：H06 命中的边界规则库
    #      `适用产品 = ["W1","M5","M6","M9","Air1"]` ⇒ 会把「五个产品线」标到一条 M5 文案上。
    #      这一条判据就是那次收紧的守卫。
    f3 = facets_for_anchor("#品线内容边界规则库/recvuJP1LVW6E0/边界内容")
    chk("③ 边界规则库的「适用产品」**不算**产品线（那是规则适用范围）",
        f3["product_line"] == "" and f3["channel"] == "",
        "产品线=%r 渠道=%r" % (f3["product_line"], f3["channel"]))

    # ④ 反向对照：不存在的记录 ⇒ 全空、**不抛错**
    f4 = facets_for_anchor("#不存在的表/rec-nope-000/字段")
    chk("④ 反向对照：查不到 ⇒ 全空且不抛错",
        f4["product_line"] == "" and f4["channel"] == "", json.dumps(f4, ensure_ascii=False))

    # ④b **库内标签锚点**（`#素材/…`）：id 在 L0 里唯一 ⇒ 允许取，但 `from` 必须说出**真实表名**
    f4b = facets_for_anchor("#素材/recvw7XIUgnJYu/图片素材/#img.1")
    chk("④b 库内标签锚点：取到的值必须标明**真实来源表**（不是标签名「素材」）",
        (not f4b["product_line"] and not f4b["channel"])
        or all("素材." not in v for v in (f4b["from"] or {}).values()),
        json.dumps(f4b["from"], ensure_ascii=False))

    # ⑤ 多 anchor 汇总：记录全判不过 ⇒ **回落素材原文**；跳过要留痕、分歧不许静默合并
    m = facets_for_anchors([a1, "#品线内容边界规则库/recvuJP1LVW6E0/边界内容", a1],
                           "在 Google 投的吸奶器广告，帮我审下")
    chk("⑤ 汇总：记录全判不过 ⇒ 回落素材原文（吸奶器 / Google）",
        m["product_line"] == "吸奶器" and m["channel"] == "Google",
        "%r / %r" % (m["product_line"], m["channel"]))
    chk("⑤ 被跳过的记录**如实列出**（`records_skipped`，不静默）",
        isinstance(m.get("records_skipped"), list) and len(m["records_skipped"]) >= 1
        and all(s.get("why") for s in m["records_skipped"]),
        json.dumps((m.get("records_skipped") or [{}])[0], ensure_ascii=False)[:110])
    chk("⑤ 汇总：把所有取值都列出来（不静默合并）",
        isinstance(m["all_product_lines"], list) and len(m["all_product_lines"]) >= 1,
        json.dumps(m["all_product_lines"], ensure_ascii=False))

    # ⑥ 从引擎 JSON 形状里挖 anchor —— 两种真实形状（正常路径 / 拒答路径）都挖得到。
    #    ★ 第一版这里我夹具写错了（写成 `"anchors": [...]`），而真引擎里 key **恰好是 `anchor`**
    #      （`evidence.anchor`）。判据当场红 ⇒ 改夹具、**不改实现**（实现盯的就是真数据）。
    a2 = "#品线内容边界规则库/recvuJP1LVW6E0/边界内容"
    eng = {"risk_items": [{"evidence": {"anchor": a1}}],                  # 正常路径
           "decision": {"risk_items": [{"evidence": {"anchor": a2}}]}}    # 拒答路径（埋在 decision 里）
    got = anchors_in(eng)
    chk("⑥ 递归挖 anchor（正常路径 + 拒答路径两处都挖到）",
        len(got) == 2 and a1 in got and a2 in got, json.dumps(got, ensure_ascii=False))
    m6 = facets_for_anchors(got)
    chk("⑥ 挖出来的 anchor：记录都不是本素材 ⇒ 全空，且**两条都留痕**",
        m6["product_line"] == "" and m6["channel"] == ""
        and len(m6.get("records_skipped") or []) == 2,
        "%r / %r ｜ skipped=%d" % (m6["product_line"], m6["channel"],
                                  len(m6.get("records_skipped") or [])))

    # ⑥b ★ **`top_hit_anchor` 不算命中** —— 它指的是**素材自己的单元**（`#素材/…/#img.1`），
    #     不是知识库条款的来源。把它算进来等于「拿素材给素材自己定产品线」。
    #     （实测这个坑真实存在：2026-10-06 两单图片/视频的 `coverage.top_hit_anchor`
    #       正是素材自身；而那两条的 BM25 最高分也是「自己匹配自己」。）
    eng2 = {"coverage": {"top_hit_anchor": "#素材/recvw7XIUgnJYu/图片素材/#img.1"},
            "risk_items": [{"evidence": {"anchor": a1}}]}
    got2 = anchors_in(eng2)
    chk("⑥b `top_hit_anchor`（素材自身）**不**被当成命中来源",
        got2 == [a1], json.dumps(got2, ensure_ascii=False))

    # ⑦ 反向对照：字段名没登记过的记录**不许**取到值
    chk("⑦ 登记表里没有「专家修订汇总表」的任何字段（它本来就没有）",
        "专家修订汇总表" not in " ".join(PRODUCT_FIELDS + CHANNEL_FIELDS))

    # ══ ⑧ **素材原文兜底**（2026-10-06 加：图片/视频没有规则命中，素材原文是唯一来源）════
    t1 = facets_for_anchors([], "在 Google 投的吸奶器广告，帮我审下")
    chk("⑧ 素材原文逐字命中受控词 ⇒ 两格都取到",
        t1["product_line"] == "吸奶器" and t1["channel"] == "Google",
        "%r / %r" % (t1["product_line"], t1["channel"]))
    chk("⑧ 来源标明是「素材原文逐字命中受控词」（与记录来源分得开）",
        "素材原文" in (t1["from"].get("channel") or ""), json.dumps(t1["from"], ensure_ascii=False))
    # ⑧b **catch-all 必须剔除** —— 否则「其他产品」四个字就会填出 `品线=其他`
    t2 = facets_for_anchors([], "比其他产品更好用，全型号通用")
    chk("⑧b 反向对照：catch-all「其他/全型号」不许命中",
        t2["product_line"] == "" and t2["channel"] == "",
        "%r / %r" % (t2["product_line"], t2["channel"]))
    # ⑧c **词边界**：`Googleplex` 不许命中 `Google`
    t3 = facets_for_anchors([], "we love Googleplex in Mountain View")
    chk("⑧c 反向对照：英文按词边界（Googleplex ≠ Google）", t3["channel"] == "", repr(t3["channel"]))
    # ⑧d **本素材说了什么就填什么**（2026-10-06 改）：记录**不是**本素材 ⇒ 不许拿它的 `平台`
    #     覆盖素材原文；旧判据「记录优先」正是把样本的 Google 烧进本次渠道的那条口径。
    t4 = facets_for_anchors([a1], "这条文案是给展会上用的")
    chk("⑧d 记录不是本素材 ⇒ 不采信它，取素材原文（渠道=展会，不是样本的 Google）",
        t4["channel"] == "展会" and "素材原文" in (t4["from"].get("channel") or ""),
        "%r ← %s" % (t4["channel"], t4["from"].get("channel")))
    # ⑧e 正例：记录**是**本素材 ⇒ 记录优先于素材原文（记录是人工归类过的，可信度更高）。
    #     ⚠️ 这条用**构造夹具**：真库里找不到「`平台` 与正文里的渠道词冲突」的记录
    #        （2026-10-06 扫过 `广告文案明细` 全表，0 条）—— 而这条优先级判据必须能分辨，
    #        故临时把 `L0_RECORDS` 指到一个构造记录上，**不动库里任何文件**。
    import shutil
    import tempfile
    _tmp = tempfile.mkdtemp(prefix="l0facets-selftest-")
    _keep = globals()["L0_RECORDS"]
    try:
        _d = os.path.join(_tmp, "临时表__夹具表")
        os.makedirs(_d, exist_ok=True)
        _fx = {"source_table": "夹具表",
               "fields": {"品线": ["吸奶器"], "平台": ["Google"],
                          "Primary Text": "在展会上发的吸奶器文案，别错过"}}
        with open(os.path.join(_d, "rec-selftest-001.json"), "w", encoding="utf-8") as fh:
            json.dump(_fx, fh, ensure_ascii=False)
        globals()["L0_RECORDS"] = _tmp
        t5 = facets_for_anchors(["#夹具表/rec-selftest-001/Primary Text"],
                                "在展会上发的吸奶器文案，别错过")
        chk("⑧e 记录就是本素材 ⇒ 记录优先（渠道=Google 而素材里写着「展会」）",
            t5["channel"] == "Google" and "夹具表" in (t5["from"].get("channel") or ""),
            "%r ← %s" % (t5["channel"], t5["from"].get("channel")))
    finally:
        globals()["L0_RECORDS"] = _keep
        shutil.rmtree(_tmp, ignore_errors=True)

    print("\n自证：通过 %d / 失败 %d" % (len(P), len(F)))
    for x in F:
        print("  · 失败：%s" % x)
    return 1 if F else 0


def main():
    ap = argparse.ArgumentParser(description="从命中的 L0 记录取 产品线 / 渠道（只读）")
    ap.add_argument("--anchor", action="append", default=[], help="可重复")
    ap.add_argument("--anchors-json", help="JSON 字符串数组")
    ap.add_argument("--engine-json", help="引擎 JSON 文件；自动挖里面的全部 anchor")
    ap.add_argument("--text", help="素材原文（含 OCR/转写）；记录取不到时从它逐字命中受控词")
    ap.add_argument("--vocab", action="store_true", help="打印受控词表（库内实测导出）")
    ap.add_argument("--field-map", action="store_true", help="打印登记表（哪张表有哪两列）")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()

    if a.selftest:
        print("l0_facets · 判据自证（离线；真 anchor / 真 L0 件）")
        return selftest()

    if a.vocab:
        print(json.dumps({"product_lines": list(PRODUCT_LINE_VOCAB),
                          "channels": list(CHANNEL_VOCAB),
                          "excluded_catch_all": ["其他", "全型号"],
                          "latin_word_boundary": list(_LATIN),
                          "source": "kb/l0/records/ 实测取值分布（2026-10-06）"},
                         ensure_ascii=False, indent=1))
        return 0

    if a.field_map:
        print(json.dumps({
            "product_line_fields": list(PRODUCT_FIELDS),
            "channel_fields": list(CHANNEL_FIELDS),
            "content_tables": ["广告文案明细", "负面样本"],
            "excluded_tables": {
                "品线内容边界规则库": "`适用产品` 是**规则的适用范围**，不是素材的产品线",
                "风险文案改写建议库（分型号分渠道）": "`适用型号`/`渠道` 是**建议的适用面与分类维度**",
            },
            "note": "按 kb/l0/_archive/schema_snapshots 逐表实测登记；**只认内容记录**；未登记的一律不取，取不到就留空",
        }, ensure_ascii=False, indent=1))
        return 0

    anchors = list(a.anchor)
    if a.anchors_json:
        try:
            anchors += [x for x in json.loads(a.anchors_json) if isinstance(x, str)]
        except json.JSONDecodeError:
            print("[warn] --anchors-json 不是合法 JSON，忽略", file=sys.stderr)
    if a.engine_json:
        anchors += anchors_in(_load_engine_json(a.engine_json))

    print(json.dumps(facets_for_anchors(anchors, a.text or ""), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
