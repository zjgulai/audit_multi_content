#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""p0_fastpath.py —— **P0 红线快路**（PRD §6.3 第一层 / §12「P0 层响应 ≤ 1 秒」）

## 它补的是哪个口子

PRD 原文（`内容审查 Agent PRD` v1.2，revision 36，§6.3）：

    第一层：P0 法务合规红线快速扫描（关键词/正则匹配，毫秒级）
        ├── 命中 → 直接 BLOCK，输出问题及依据
        └── 未命中 → 进入第二层

    **执行规则 1**：P0 命中即**停止后续审查**，直接输出 BLOCK，确保法务红线零延迟拦截。

§6.2 的 P0 行更写明：「**无需大模型推理**，正则/关键词命中即输出 BLOCK」。
§12 给的下限是「P0 层响应 ≤ 1 秒」。

而现状（2026-10-05 实测）：素材一律走「四层前置 + 评审链」，
端到端 **4~10 分钟**（四单实测均值 6.25 min）—— P0 命中也不例外。
**差在入口方式**：那条链 79.6% 的时间是通用 agent 自己在探索，而 P0 这一层**不需要 agent**。

本脚本就是那一层的执行体：**确定性匹配 + 组装四段溯源**，实测 **8~10 ms**。

## 铁律（每条都有代价，不是客套）

1. **只对命中短路** —— 只出 `BLOCK`。**永不**产出 PASS / REVIEW。
   未命中一律 `hit=false`，交回原链（L4→L5→L6→L7 + 评审链），**判据一条不放宽**。
2. **不许静默**：结论里必须带 `mode=p0_fastpath` 与「未跑四层前置/评审链」的声明 ——
   库内纪律：缺前置必须**可见**（对照 `--allow-no-layer-preflight` 的 `waived_by_caller` 口径）。
3. **四段溯源齐**（缺一段不许出结论）：
   条款号（L4 直查 `kb/l4/canonical/`）＋ 规则与命中片段（L5 模式 + 匹配器）＋
   `anchor`/`source_sha256`（模式自带）＋ L0 逐字与**可点直链** `entry_url`（`kb/l0/records/`）。
4. **不写库**：只产结论 JSON。落表 / 云文档由调用方按既有发布件做（本脚本不碰 kb/l0–l7 数据）。
5. **它替代不了判定主体**：这一层是**确定性红线**，不是专项审查。
   要走专项（文案/图片/视频/产品宣称/AI 权利/本地化）的场合，命中之后同样要转人/转专项 ——
   本脚本只在结论里写明"这是 P0 确定性拦截"，**不冒充专项结论**。

## 用法

    sh kb/kbpy l5/p0_fastpath.py --text "<素材原文>"           # 人读
    sh kb/kbpy l5/p0_fastpath.py --text "<素材>" --json        # 机读（调用方按 hit 分支）
    sh kb/kbpy l5/p0_fastpath.py --file <path> --json

退出码：**恒 0**（命中与否是数据，不是错误）。调用方看 `hit`。
依赖：`kb/l5/matcher.py`（同一份模式表与匹配逻辑，**不重复实现**）。
"""
from __future__ import annotations

import argparse
import glob
import importlib.util
import json
import os
import re
import sys
import time
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
KB = os.path.dirname(HERE)                      # kb/
ROOT = os.path.dirname(KB)
CANON_DIR = os.path.join(KB, "l4/canonical")
L0_RECORDS = os.path.join(KB, "l0/records")


# ══════════════════════════════════════════════════════════════════════════
# 2026-10-21（Owner：「审查报告中不能出现后台语言」）
# ══════════════════════════════════════════════════════════════════════════
# 三样东西**不许**上报告：正则源码、规则码（H05/M07…）、库内相对路径（kb/…）。
# 判断只认形状，不改判定：命中的是哪个词、理由是什么，都是原样。
_RELAX_NOTE_RE = re.compile(r"[（(][^）)]*(?:放开|不再判险|允许)[^）)]*[）)]")
_RULE_CODE_HEAD_RE = re.compile(r"^\s*[A-Z]\d{2}\s*[:：]?\s*")


def _hit_text(m, limit=40):
    """命中的**真实文字**（不是正则源码）。

    `matched[]` 里两格：`pattern` 是**规则侧写法**（正则命中时就是一整条正则），
    `text` 是**真正被命中的那段字**（匹配器的 `m.group(0)`）。
    报告写「逐字命中」⇒ 只能用 `text`；取不到才退回 `pattern`（老收据没有 `text`）。
    """
    m = m or {}
    t = str(m.get("text") or "").strip() or str(m.get("pattern") or "").strip()
    t = t.replace("`", "")
    return (t[:limit] + "…") if len(t) > limit else t


def _business_reason(text, code=None):
    """「原因」的业务版：去规则码前缀、去括号里的口径说明，**判定理由一个字不改**。

    实测那种自相矛盾的印法（2026-10-21 报告 F-02）：
        `H05 虚假安全承诺（best/#1/No.1/最佳/最好等排名最高级按2026-09-09口径放开，
         海外广告允许，不再判险）`
    —— 把「已放开」的口径原样印在一条 P0 的「原因」里，读者只能读出矛盾。
    """
    s = str(text or "").strip()
    if not s:
        return "（来源未给判定理由）"
    s = _RULE_CODE_HEAD_RE.sub("", s)
    s = _RELAX_NOTE_RE.sub("", s).strip()
    s = re.sub(r"\s{2,}", " ", s).strip(" ；;，,、")
    return s or "（来源未给判定理由）"


# ══════════════════════════════════════════════════════════════════════════
# 2026-10-21（Owner 裁定 A 的另一半）：**排名/销量宣称 = 非阻断提示**
# ══════════════════════════════════════════════════════════════════════════
# 裁定原文：「『第一 / 销量第一』这类中文事实性排名仍按『需补可核验依据』提示（**不阻断**）」。
# 为什么它不进 findings：三态只由 P0 命中决定；提示改了结论就等于换个名字继续拦。
# 为什么它不能一个字不说：美国平台（Amazon/FTC）对「#1 best seller」「销量第一」要求可核实依据，
#   全静默等于把这条风险从系统里删掉（本项目：漏放是真红线）。
# ⇒ 只出现在**回执与 P0 报告**的一段话里，不计入问题数、不改结论。
RANK_ADVISORY_RX = [
    r"(?:\bno\.?\s*1\b|\B#\s*1\b|\bnumber[\s-]?one\b)",
    r"\b(?:best[- ]?selling|top[- ]?seller|bestseller|number[- ]one)\b",
    r"(?:排名|销量|全网|行业|品类|国内|全球|世界|亚洲|全美)\s*第一",
    r"第一\s*(?:品牌|选择|名|款|位)",
    r"(?:第一|冠军|榜首)[^。，,；;]{0,6}(?:销量|品牌|排名|名)",
    r"最\s*(?:佳|好|高)",
]
_RANK_ADV_RE = re.compile("|".join(RANK_ADVISORY_RX), re.IGNORECASE)


def _advisories(text):
    """素材里出现的**排名/销量宣称**（非阻断提示；去重、最多 3 条）。"""
    seen = []
    for m in _RANK_ADV_RE.finditer(str(text or "")):
        t = m.group(0).strip()
        if t and t.lower() not in [x.lower() for x in seen]:
            seen.append(t)
        if len(seen) >= 3:
            break
    return seen


def _advisory_line(advisories):
    if not advisories:
        return ""
    return ("另（**不阻断**）：素材里还有%s这类排名/销量宣称 —— 美国平台会要求可核验的依据，"
            "建议发布前补一句来源与口径。**这条不算问题、也不影响上面的结论**。"
            % "、".join("「%s」" % x for x in advisories))

def _load_matcher():
    """复用 kb/l5/matcher.py 的 match() —— 一份模式表、一套匹配逻辑。"""
    p = os.path.join(HERE, "matcher.py")
    spec = importlib.util.spec_from_file_location("p0_matcher", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_ADVICE_BOOK = None
_TAX_ORDER = None


def _advice_book():
    """「建议」兜底改法的**唯一来源** = `kb/l5/advice_book.py`（同一目录，按路径加载）。

    ★ 2026-10-19（Owner 逐字：「**必须给建议**」）：改前这一格只有两个取值口
      （L3 `fix_pairs` / 模式表 `suggested_replacement`），而 17 条 P0 模式里 **10 条**
      两者皆空 ⇒ 卡上印「（来源未给修改建议）」。兜底表补的就是这 10 条。
      ⚠️ 加载失败**不许静默**：回一个同签名空壳（给通用句），并把原因打到 stderr ——
         「兜底表没装上」与「兜底表说没有」必须长得不一样。
    """
    global _ADVICE_BOOK
    if _ADVICE_BOOK is not None:
        return _ADVICE_BOOK
    try:
        p = os.path.join(HERE, "advice_book.py")
        spec = importlib.util.spec_from_file_location("p0_advice_book", p)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _ADVICE_BOOK = mod
    except Exception as e:                                # noqa: BLE001
        print("[advice_book] ⚠ 兜底改法表加载失败 ⇒ 建议降级为通用句：%s" % e, file=sys.stderr)

        class _Empty:                                     # 最小空壳：签名与真模块一致
            @staticmethod
            def fallback(rule_code=None, rule_id=None, hits=()):
                return ("删去命中的违规表述后再提交。", "generic_no_book")

        _ADVICE_BOOK = _Empty()
    return _ADVICE_BOOK


_L4_INDEX = None            # rule_id → 记录（**唯一键**；实测 632 组）
_L4_BY_RC = None            # rule_code → [记录…]（**非唯一**；实测 15 个键一对多）


def _l4_load():
    """读 L4 canonical，**两个键分开存**。一次读盘、两个索引 —— 不许把非唯一键当唯一键用。"""
    global _L4_INDEX, _L4_BY_RC
    if _L4_INDEX is not None:
        return
    _L4_INDEX, _L4_BY_RC = {}, {}
    for p in sorted(glob.glob(os.path.join(CANON_DIR, "*.jsonl"))):
        try:
            with open(p, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        d = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if not d.get("article_no"):
                        continue
                    rec = {
                        "article_no": d.get("article_no"),
                        "form": d.get("form"),
                        "rule_id": d.get("rule_id"),
                        "source_file": os.path.relpath(p, ROOT),
                    }
                    rid = d.get("rule_id")
                    if rid and rid not in _L4_INDEX:        # rule_id 唯一 ⇒ 首个即唯一
                        _L4_INDEX[rid] = rec
                    rc = d.get("rule_code")
                    if rc:
                        _L4_BY_RC.setdefault(rc, []).append(rec)
        except OSError:
            continue


def _l4_clause(rule_id=None, rule_code=None):
    """条款号（L4 定稿层）——**主键 `rule_id`**，`rule_code` 只在一对一时回落。

    ★★ 2026-10-10：主键从 `rule_code` 换成 `rule_id`（**接线缺陷修复，不是重构**）
    ─────────────────────────────────────────────────────────────────────────
    旧实现按 `rule_code` 建索引、注释写「首个命中即采用（与 L4 内的排序一致）」。
    实测（2026-10-10，读 L4 canonical 五个形态件）：
        rule_code → 条款号 共 22 个键，其中 **15 个键一对多**：
            H02 → [W-1.18, W-1.47]      H04 → [W-1.13, W-1.41]
            H05 → [W-1.33, W-1.22]      …
    ⇒ 旧实现的号**取决于文件排序**，没有判据守着；一旦 L4 重建换了顺序、或同一
      rule_code 新增一条，引用的条款号会**静默换人**（错号比空号更坏 —— 空号人会去补，
      错号人不会回头看）。

    **当前 11 条 P0 恰好取对**（逐条实测：按 rule_code 取 == 按 rule_id 取，11/11），
    所以这是**隐患**不是现行事故 —— 修的是"靠巧合"这件事本身。

    本文件里的 `_l3_rule()` 早就写着「★ 为什么用 `rule_id` 而不是 `rule_code`」——
    同一份文件里的两个函数本该用同一种键。

    返回：`{"article_no", "form", "rule_id", "source_file", "via"}`，`via ∈ {rule_id, rule_code}`；
    **取不到就返回 None（不猜）** —— 一对多时宁可让人来核，也不许挑一个。
    """
    _l4_load()
    if rule_id and rule_id in _L4_INDEX:
        r = dict(_L4_INDEX[rule_id])
        r["via"] = "rule_id"
        return r
    if rule_code:
        rows = _L4_BY_RC.get(rule_code) or []
        nos = {x["article_no"] for x in rows}
        if len(nos) == 1:                   # 恰好一个号 ⇒ 该 rule_code 无歧义，可回落
            r = dict(rows[0])
            r["via"] = "rule_code"
            return r
        if len(nos) > 1:                    # ★ 一对多 ⇒ **不猜**（旧实现在这里取了首个）
            return None
    return None


def _l4_clause_miss_reason(rule_id, rule_code):
    """取不到条款号时**把成因写出来** —— 「查不到」与「一对多不敢猜」是两件事，
    混成一句会让人去修一个本来就没坏的东西。"""
    _l4_load()
    if rule_id and rule_id not in _L4_INDEX:
        return "rule_id %s 不在 L4 映射里" % rule_id
    if rule_code:
        nos = {x["article_no"] for x in (_L4_BY_RC.get(rule_code) or [])}
        if len(nos) > 1:
            return "rule_code %s 在 L4 里一对多（%s）⇒ 不猜，需人工核" % (
                rule_code, "、".join(sorted(nos)))
    return "L4 里未按 rule_id/rule_code 查到"


def _l0_verbatim(anchor):
    """L0 逐字 + **可点直链**。

    anchor 形如 `#<表名>/<record_id>/<字段名>`（如 `#广告文案明细/recvuJYdOb1B8v/命中片段`）。
    L0 件在 `kb/l0/records/<源库标签>__<表名>/<record_id>.json`，内含 `entry_url`（飞书那条原始记录）。
    """
    if not anchor or not anchor.startswith("#"):
        return None
    parts = anchor.lstrip("#").split("/")
    if len(parts) < 2:
        return None
    table, record_id = parts[0], parts[1]
    field = parts[2] if len(parts) > 2 else None
    cands = glob.glob(os.path.join(L0_RECORDS, "*__%s" % table, "%s.json" % record_id))
    if not cands:
        cands = glob.glob(os.path.join(L0_RECORDS, "**", "%s.json" % record_id), recursive=True)
    if not cands:
        return {"record_id": record_id, "table": table, "field": field,
                "entry_url": None, "raw_verbatim": None,
                "note": "L0 里找不到这条记录 ⇒ 直链缺失，需人工回源"}
    try:
        d = json.load(open(cands[0], encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    fv = ((d.get("fields") or {}).get(field) or {}) if field else {}
    return {
        "record_id": d.get("record_id") or record_id,
        "table": d.get("source_table") or table,
        "field": field,
        "entry_url": d.get("entry_url"),
        "raw_verbatim": fv.get("raw_verbatim") or fv.get("value"),
        "l0_file": os.path.relpath(cands[0], ROOT),
    }


def _verbatim_with_url(hit, rule):
    """L0 逐字 + **可点直链**；L0 定位不到时，用条款自带的 `resource_id` 还原原件地址。

    ★★ 2026-10-19（Owner：「**依据文档链接**要带飞书源侧链接」，例：
      `依据文档链接：《知识库》第 E-2.124 条 ← 命中「100%」` —— 这一格没有链接）：
      PRD §7.3 那类的 anchor 是 `#h.7. 知识库与规则体系 / 7.3 一票否决项…`，
      **不是记录级坐标** ⇒ `_l0_verbatim()` 找不到 L0 记录 ⇒ `entry_url=None`
      ⇒ 卡上与报告那一格的链接全丢。而这条规则自己带着
      `resource_id = url__momcozy_in.feishu.cn_wiki_NB55…`（**原件的飞书地址**）。
      ⇒ 只补这一格，**不编**：还原不出就保持 null，`note` 里如实说它是缺的。
    """
    vb = _l0_verbatim(hit.get("anchor")) or {}
    if vb.get("entry_url"):
        return vb
    url = _resource_url((rule or {}).get("resource_id"))
    if url:
        vb = dict(vb)
        vb["entry_url"] = url
        vb["entry_url_from"] = "条款 resource_id（原件地址；L0 记录级坐标未命中）"
        vb.pop("note", None)
    return vb


#: `pattern_id → 条款号`（模式表自带那一格）。懒加载一次，跟 `_L3_INDEX` 同一套做法。
_ART_INDEX = None


def _article_of(pattern_id):
    """模式表里这条模式自带的条款号；取不到返回 **None（不编）**。

    ★★ 2026-10-14 加。`matcher.match()` 的返回里**没有** `article_no`，而模式表
      （`kb/l5/p0_patterns.jsonl`，实测 17/17 条都带这一格）**有** ⇒ 不补这一跳，
      渲染层只能写「（来源未给条款号）」。**这不是缺数据，是缺一次搬运。**

    ★ 为什么不从 L3 候选取：`kb/l3/candidates/external_standard.jsonl` **有重复行**
      （同一个 `rule_id` 两行，条款号一格 `E-1.3419`、一格 `E-2.124`，`rule_text` 逐字相同）
      ⇒ 「先读到的先用」等于**随机取一个号**。取证：`kb/l7/registry/layers.yaml:217` 明写
      这 123 条条款级规则「唯一正确的段是 **E-2**」⇒ 模式表那格 `E-2.124` 才是对的。
    """
    global _ART_INDEX
    if _ART_INDEX is None:
        _ART_INDEX = {}
        try:
            with open(os.path.join(KB, "l5/p0_patterns.jsonl"), encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        d = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    pid, art = d.get("pattern_id"), d.get("article_no")
                    if pid and art and pid not in _ART_INDEX:
                        _ART_INDEX[pid] = art
        except OSError:
            pass
    return _ART_INDEX.get(str(pattern_id or ""))


def evaluate(text, report_ref=""):
    """跑一次快路。返回结论 dict（`hit=false` 时只有 mode/elapsed）。

    `report_ref`（2026-10-06）：报告链接，**只填进回执**，本函数不生成报告、不碰 IO ——
    「P0 响应 ≤1s」与「报告生成 ≤30s」是 PRD §12 的两条独立指标，不许在一条路上等另一条。
    """
    t0 = time.perf_counter()
    m = _load_matcher()
    hits = m.match(text)
    dt_ms = round((time.perf_counter() - t0) * 1000, 3)
    # ★★ 2026-10-14：**把模式表自带的 `article_no` 补进命中**。
    #   病灶（实测那条 V02）：`matcher.match()` 只回 `rule_id/rule_code/matched/anchor/…`，
    #   **不回收模式表里的 `article_no`** ⇒ 渲染层取 `finding["article_no"]` 永远拿到 None
    #   ⇒ 依据退化成「第 （来源未给条款号） 条」。**手上有号却说没有。**
    #   为什么信模式表这一格：它与模式表同源、逐条可核；而 L3 候选 `external_standard.jsonl`
    #   **存在重复行**（同一 rule_id 两行：E-1.3419 / E-2.124）⇒ 从 L3 取反而可能取到错的。
    #   取证：`kb/l7/registry/layers.yaml:217` 明写这 123 条条款级规则「唯一正确的段是 E-2」。
    hits = [dict(h, article_no=h.get("article_no") or _article_of(h.get("pattern_id"))) for h in hits]

    out = {
        "mode": "p0_fastpath",
        "hit": bool(hits),
        "elapsed_ms": dt_ms,
        "matched_patterns": len(hits),
        "text_chars": len(text or ""),
        # 可见性：这一条结论**没有**走四层前置与评审链，必须说清楚
        "layer_preflight": {
            "mode": "p0_fastpath",
            "enforced": False,
            "why": "PRD §6.3 第一层：P0 命中即停止后续审查；本结论**未跑** L4→L7 层前置与评审链",
            "is_pass_basis": False,
        },
    }
    if not hits:
        out["state"] = None
        out["next"] = "未命中 P0 ⇒ 交回原链（L4→L5→L6→L7 + 评审链），判据一条不放宽"
        return out

    findings = []
    for h in hits:
        rc = h.get("rule_code")
        findings.append({
            "rule_code": rc,
            "level": h.get("level") or "P0",
            "verdict": h.get("match_note") or "BLOCK",          # 判据来自模式表，不在这里新造
            "pattern_id": h.get("pattern_id"),
            "rule_id": h.get("rule_id"),
            # 段②：规则 / 命中片段（L5 模式 + 匹配器读数）
            "matched": h.get("matched") or [],
            "matched_count": h.get("matched_count"),
            "whitelist_suppressed": h.get("whitelist_suppressed"),
            "suggested_replacement": h.get("suggested_replacement") or "",
            # 段③：锚点 + 指纹（模式自带）
            "anchor": h.get("anchor"),
            "source_sha256": h.get("source_sha256"),
            # ★★ 2026-10-14：**把模式表自带的条款号搬进命中** —— 它原先没被传进来。
            #   病灶（实测那条 V02）：模式表 `p0_patterns.jsonl` 里明写 `article_no="E-2.124"`，
            #   而渲染层取的是 `finding["article_no"]` ⇒ **永远是 None** ⇒ 依据退化成
            #   「第 （来源未给条款号） 条」。**手上有号却说没有**，是最没道理的一种缺。
            #   为什么该信模式表这一格：它与模式表**同源、逐条可核**，且 L3 候选里那条
            #   `external_standard.jsonl` **有重复行**（同一 rule_id 两行、条款号一格 E-1.3419
            #   一格 E-2.124）⇒ 从 L3 取反而可能取到错的那个（见 `_item_fields` 的顺序注释）。
            "article_no": h.get("article_no"),
            # 段①：条款号（L4 直查）
            # ★ 2026-10-10：主键改用 rule_id（唯一）；rule_code 在 L4 里一对多 ⇒ 只作回落
            "clause": _l4_clause(rule_id=h.get("rule_id"), rule_code=rc),
            # 段④：L0 逐字 + 直链
            # ★★ 2026-10-19（Owner：「依据文档链接要带飞书源侧链接」—— 例
            #   `依据文档链接：《知识库》第 E-2.124 条 ← 命中「100%」` 这一格没有链接）：
            #   L0 定位不到记录时（PRD §7.3 那条 `#h.7. …` 就是这种）`entry_url` 是 null；
            #   而规则自带 `resource_id`（= 原件的飞书地址）⇒ 由它还原一条，**不编**。
            "verbatim": _verbatim_with_url(h, _l3_rule(h.get("rule_id"))),
            # ★ PRD §5.3.3 逐条格式要的两格（2026-10-06 加）：
            #   `【类别-子类】` 与 `原因 / 库名 / 版本`。两者都不在 P0 模式表里，
            #   分别从**受控词表**（l7.json 的 vocabulary）与 **L3 规则**（按 rule_id 查）取。
            "_category": _vocabulary().get(rc),
            "_l3": _l3_rule(h.get("rule_id")),
        })

    out["advisories"] = _advisories(text)
    out["state"] = "BLOCK"
    out["findings"] = findings
    out["issue_count"] = len(findings)
    # ── 产品线 / 渠道（Owner 2026-10-06）───────────────────────────────────────────
    #   现场原话：「里面的产品线和渠道都是空或者未指定，运行任务的时候从知识库命中产品线和
    #   渠道的都填写进去」。⇒ 值只从 `kb/l5/l0_facets.py` 出（**唯一取数点**），字段名按实测登记
    #   （`品线`；`平台`/`渠道/市场`），**取不到就留空** —— 不许从素材正文猜、也不许拿规则样本的属性充数。
    out["facets"] = _facets_of(findings, text)
    out["product_line"] = out["facets"].get("product_line") or ""
    out["channel"] = out["facets"].get("channel") or ""
    out["rendered"] = _render(text, findings, report_ref, advisories=out.get("advisories"))
    return out


_VOCAB = None
_FACETS = None


def _facets_mod():
    """导入同层的 `l0_facets`（**产品线 / 渠道的唯一取数点**）。

    ★ 为什么不在这里再写一份「从 L0 取品线/平台」：
      评审链（`kb/l8/review_run.sh` 的机读旁挂）也要**同一份**值。
      两处各写一份 ⇒ 迟早一个取 `品线`、一个取 `适用产品`，同一条素材两个答案。
      所以值只从 `l0_facets.py` 出，本文件与旁挂都调它。
    """
    global _FACETS
    if _FACETS is None:
        p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "l0_facets.py")
        spec = importlib.util.spec_from_file_location("l0_facets", p)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        _FACETS = m
    return _FACETS


def _facets_of(findings, text=""):
    """素材属性（产品线 / 渠道）：**本素材自己的记录**优先，其次**素材原文**；取不到就空。

    ★ 口径（2026-10-06 收紧，见 `l0_facets.record_is_this_material`）：
      命中的 L0 记录**大多是规则样本**（比如那条真实投放的 Google 广告）—— 它的 `品线/平台`
      是**那条样本自己的投放属性**，拿来当本次素材的属性就是编数据。
      ⇒ 只有过了「这条记录是不是本素材本人」那道闸的记录才采信；否则回落素材原文受控词。
    ★ 取不到就空，不抛错、不阻断结论。
    """
    try:
        anchors = [f.get("anchor") for f in (findings or []) if f.get("anchor")]
        return _facets_mod().facets_for_anchors(anchors, text or "")
    except Exception as e:                                   # noqa: BLE001
        return {"product_line": "", "channel": "", "from": {},
                "all_product_lines": [], "all_channels": [], "anchors_used": 0,
                "error": "%s: %s" % (type(e).__name__, e)}


def _vocabulary():
    """`rule_code` → 「类别-子类」。**单一真源 = `kb/l7/registry/l7.json` 的 `vocabulary`。**

    ★ 为什么读 registry 而不是抄一份：`kb/l7/skills/kb-content-review/references/categories.md`
      第一行自己写着「来源：kb/l7/registry/l7.json → vocabulary（**本文件是它的可读投影，
      口径以 registry 为准**）」。抄第二份必然过期 —— 本库已因「同一事实写三处不一致」返工过一次。

    ★ 为什么 P0 快路要它：PRD §5.3.2/§5.3.3 的**逐条**格式要求每条以 `【类别-子类】` 开头，
      而 P0 模式表里只有 `rule_code`，没有类别。映射是静态的，读一次即缓存。
    """
    global _VOCAB
    if _VOCAB is None:
        _VOCAB = {}
        try:
            with open(os.path.join(KB, "l7/registry/l7.json"), encoding="utf-8") as fh:
                cats = (json.load(fh).get("vocabulary") or {}).get("categories") or {}
            for cat, node in cats.items():
                for sub, sn in (node.get("subs") or {}).items():
                    for code in (sn.get("codes") or []):
                        _VOCAB.setdefault(code, "%s-%s" % (cat, sub))
        except (OSError, json.JSONDecodeError, AttributeError):
            pass
    return _VOCAB


_L3_INDEX = None


#: L3 候选件（**按优先级**）。★ 见 `_l3_rule` 的注释：只读第一份会漏掉整类 P0。
_L3_FILES = ("rules.jsonl", "external_standard.jsonl", "sample_cases.jsonl")


def _l3_rule(rule_id):
    """按 `rule_id` 取 L3 规则，只取渲染 §5.3 逐条要用的几格（原因 / 库名 / 版本 / 条款号 / 来源）。

    ★ 为什么用 `rule_id` 而不是 `rule_code`：`REDLINE-CLAUSE-MAP-20260930.md` 明写
      「**`rule_code` 在全库不唯一**……只写『H02 = W-1.18』无法唯一定位；带 `rule_id` 才能回源」。

    ★★ 2026-10-14 修（Owner 报「依据里必须是飞书链接，不许出现『（来源未给库名）』」）：
      **病灶：这个取值口原先只读 `rules.jsonl` 一份文件。**
      而 2026-10-13 起，「外部标准」那一路的条款（Owner 定的可引用依据）落在
      **`external_standard.jsonl`** —— 于是凡是命中那些条款的 P0，这里一律查不到 ⇒
      渲染成 `《（来源未给库名） v0（试用版，未发布）》第 （来源未给条款号） 条`。
      **实测复现**（素材「m8 pro吸奶器是最好的吸奶器」）：
        · 模式表 `kb/l5/p0_patterns.jsonl` 里那条 V02 **明明带着** `article_no=E-2.124`；
        · `external_standard.jsonl:253` 也有它，`kb_type=external_standard`、
          `resource_id=url__momcozy_in.feishu.cn_wiki_NB55wAq8liEOdKkquL2cgtPEnmg`（**飞书 wiki 直链**）；
        · 但索引只读 `rules.jsonl`（`grep` = **0 行**）⇒ 三格全空 ⇒ 业务同事拿到一个点不开的依据。
      ⇒ 现在读**全部**候选件；并且多取一格 `resource_id` —— 那是「这条依据出自哪份原件」，
        渲染层据此给出**可点的飞书直链**（见 `_item_fields`）。
      ⚠️ 优先级 = `_L3_FILES` 的顺序（先读到的先用）：`rules.jsonl` 是主件，
        `external_standard.jsonl` 补它没有的，`sample_cases.jsonl` 最后兜。
    """
    global _L3_INDEX
    if _L3_INDEX is None:
        _L3_INDEX = {}
        for name in _L3_FILES:
            try:
                fh = open(os.path.join(KB, "l3/candidates", name), encoding="utf-8")
            except OSError:
                continue                      # 缺一份不影响其余：**缺什么就少什么**，不静默当成空库
            with fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        d = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    rid = d.get("rule_id")
                    if rid and rid not in _L3_INDEX:
                        _L3_INDEX[rid] = {
                            "reason": d.get("reason"),
                            "kb_type": d.get("kb_type"),
                            "kb_version": d.get("kb_version") or "v0",
                            "article_no": d.get("article_no"),
                            "rule_code": d.get("rule_code"),
                            "fix_pairs": d.get("expression_fix_pairs") or [],
                            "resource_id": d.get("resource_id"),
                            # ★★ 2026-10-19（Owner：「所属类别/所属子类 参考桌面 xlsx 的 12 类」）：
                            #   **所属类别/所属子类 = A3 12 类**（真源 `kb/l3/registry/rule-taxonomy.json`
                            #   ← 桌面 `规则清单-P0-P3-按等级-20261016.xlsx`；638 条逐条带这两格，
                            #   实测 1147/1147 非空）。卡面逐条首行与 ≥3 汇总都改读这两格。
                            "taxonomy_category": d.get("taxonomy_category"),
                            "taxonomy_subcategory": d.get("taxonomy_subcategory"),
                        }
    return _L3_INDEX.get(rule_id)


def _resource_url(resource_id):
    """把条款的 `resource_id` 接成**可点的飞书直链**；接不到就 **None**（宁缺勿假）。

    ★★ 2026-10-14 新增（Owner：「依据这里**必须**给飞书链接」）。三种形状：

      · `bitable__<table>__<record>` —— 库内 `l0/records/` 有对齐件的，读它自己的 `entry_url`
        （与 `review-engine/core/selfhit_check.l0_entry_url()` **同一口径**，不另立一套）。
      · `url__<host>__<path…>__<token>` —— 原件本身就是一条 URL（实测形状：
        `url__momcozy_in.feishu.cn_wiki_NB55wAq8liEOdKkquL2cgtPEnmg` ⇒
        `https://momcozy-in.feishu.cn/wiki/NB55wAq8liEOdKkquL2cgtPEnmg`）。
        ⚠️ 这个编码是**有损**的（域名里的 `-` 与路径里的 `.` 都被写成 `_`）——
        所以**只认能唯一还原的那几类路径**（wiki/docx/sheets/base/file），
        其余一律返回 None。**不猜**：一个点不开的链接比一句「取不到」更坏。
      · 其余前缀（`wiki:` / `docx:` …）—— 这里**不处理**：那类要么得查一次 token，
        要么得走 `_clickable_of` 的完整映射，属评审链那一侧；P0 快路只用上面两种，
        拿不到就如实写「取不到」。

    ⚠️ 纪律：**不许**在这里拼一个"看起来像"的链接。取不到 ⇒ 渲染层写「（取不到直链）」，
      并由 `--selftest` 逐条盯着（见 ⑥c）。
    """
    rid = str(resource_id or "")
    if rid.startswith("bitable__"):
        rest = rid[len("bitable__"):]
        for sub in ("2_内部正负样本库", "1_外部标准库"):
            fp = os.path.join(KB, "l0", sub, "feishu_bitable_record__%s.json" % rest)
            if os.path.exists(fp):
                try:
                    with open(fp, encoding="utf-8") as fh:
                        return json.load(fh).get("entry_url") or None
                except (OSError, json.JSONDecodeError):
                    return None
        return None
    if rid.startswith("url__"):
        body = rid[len("url__"):]
        for kind in ("wiki", "docx", "sheets", "base", "file"):
            marker = "_%s_" % kind
            i = body.rfind(marker)
            if i <= 0:
                continue
            host, token = body[:i], body[i + len(marker):]
            if not re.fullmatch(r"[A-Za-z0-9]{20,30}", token or ""):
                return None                     # token 形状不对 ⇒ 不拼（宁缺勿假）
            host = host.replace("_", "-")       # `momcozy_in.feishu.cn` → `momcozy-in.feishu.cn`
            return "https://%s/%s/%s" % (host, kind, token)
        return None
    return None


# `kb_type` → 人读的库名（四类库，`kb/l7/registry/l7.json` 的受控枚举）。
# ★★ 2026-10-14：键是 L1–L3 的 `kb_type` **真值**。原先只写了四个短名
#   （`external`），而 2026-10-13 起外部标准那一路的 `kb_type` 实际是
#   **`external_standard`** ⇒ 命中它的条款一律渲染成 `《external_standard v0…》`
#   （Owner 2026-10-14 截图里那个「（来源未给库名）」就是它的近亲）。
#   ⇒ 两种写法都认；**认不出就不猜**（保留原样，让人一眼看见）。
#: 12 类里的兜底类名（Owner 2026-10-19 指定的口径；与 `rule-taxonomy.json` 的 classes 一致）。
TAX_UNCLASSED = "未归类"

_LIB_NAME = {"wording": "措辞表达库", "samples": "内部正负样本库",
             "external": "外部标准库", "external_standard": "外部标准库",
             "product": "产品描述库", "product_info": "产品描述库"}


def _suggestion_for(finding, article_no=None):
    """**这一条命中**该改什么 —— 按命中片段从该规则的逐条修订组里挑，不把整张表灌进来。

    ★ 2026-10-06 加，起因是把 §5.3.3 的逐条块接上之后当场暴露的：
      P0 模式表的 `suggested_replacement` 是**该 rule_code 下所有修订组的拼接**
      （实测 W-1.18 那一格连着 26 组、几千字，末尾自己写着「另 26 组同码修订建议见证据单元」）。
      直接填进「建议：」那一格 ⇒ 一条建议几千字，卡片与上下文都会被撑爆。

    ★ 判据是「按**命中片段**挑」，不是「截断了事」：L3 规则的 `expression_fix_pairs`
      每条都带 `fragment`（违规片段）与 `fix`（怎么改）。命中的是 `increase milk supply`，
      就该给那一组的改法。挑不到才退回首组，并**写明还有几组** —— 不假装这就是全部。

    ★★ 2026-10-19（Owner 逐字：「**必须给建议**」）—— **这一格从此恒不返回空**，并返回出处：
      取值顺序（前三档都是**库内原话**，第四档才是我方兜底）：
        ① 按命中片段匹配到的 `fix_pairs`　　　　→ `l3_fix_pair`
        ② 该码首组 `fix_pairs`　　　　　　　　　→ `l3_fix_pair_first`
        ③ 模式表 `suggested_replacement`　　　　→ `pattern_suggested_replacement`
        ④ **兜底改法表**（`kb/l5/advice_book.py`）→ `p0_advice_book:<CODE>` ／ `generic_from_hit`
      改前第 ④ 档不存在，直接印「（来源未给修改建议）」—— 实测 10/17 条 P0 码落在那一档，
      收卡人看完仍不知道改什么。

    @returns `(text, source)`；`source` 是机读来源标记（写进 JSON 与报告，不上卡）。
    """
    rule = finding.get("_l3") or {}
    pairs = rule.get("fix_pairs") or []
    # ★ 2026-10-21：正则命中时 `pattern` 是正则源码，不是文本片段 ⇒ 优先用 `text`
    hit_frags = [(str(m.get("text") or "") if m.get("kind") == "regex" else str(m.get("pattern") or ""))
                 for m in (finding.get("matched") or [])]

    def norm(x):
        return str(x or "").lower().replace(" ", "")

    for p in pairs:
        frag = str(p.get("fragment") or "")
        for h in hit_frags:
            if not h or len(h) > 60:          # 正则那条（\b…）不当片段比
                continue
            a, b2 = norm(frag), norm(h)
            if a and (a in b2 or b2 in a):
                return (_with_pointer(str(p.get("fix") or "").strip() or "（该组未给改法）",
                                      pairs, article_no), "l3_fix_pair")
    if pairs:
        return (_with_pointer(str(pairs[0].get("fix") or "").strip(), pairs, article_no, first=True),
                "l3_fix_pair_first")
    sr = str(finding.get("suggested_replacement") or "").strip()
    if sr:
        return (sr[:300], "pattern_suggested_replacement")
    # ④ 库内**确实没有**原话 ⇒ 兜底表（唯一来源）；它**也不许**返回空。
    return _advice_book().fallback(rule_code=finding.get("rule_code"),
                                   rule_id=finding.get("rule_id"),
                                   hits=hit_frags)


def _with_pointer(fix, pairs, article_no, first=False):
    """给建议补一句**全量在哪儿** —— 不截断，也不假装这一组就是全部。

    库规是「**搬是搬，砍是砍**」：超长内容搬到别的格子、一个字符不丢，不许截断。
    这里那个「别的格子」就是规则文件本身 —— 逐条修订建议的全量在
    `kb/l3/candidates/rules.jsonl#<条款号>`，读者按指针回源即可。

    ★ 条款号必须**由调用方传进来**（用 `clause` 里那个，即「依据」行用的同一个）：
      第一版自己去 L3 规则里摸 `article_no`，而那一格在 L3 候选里是**空的** ⇒
      指针写成「rules.jsonl#（无条款号）」，**一个指向空处的链接**。
      这是端到端预演里**看**出来的（判据没抓到），所以顺手补了自证的 ⑥c。
    """
    if len(pairs) <= 1:
        return fix
    # ★★ 2026-10-21（Owner：「审查报告中不能出现后台语言」）：改前这一句是
    #   `（本码共 12 组修订建议，此处按首组给出；全量见 kb/l3/candidates/rules.jsonl#W-1.33）`
    #   —— 「本码」「kb/l3/…jsonl#」是库内坐标，业务侧读不懂也点不开。
    #   全量**一个字符没丢**：它就在「依据」那一格指向的条款里（可点飞书直链）。
    return "%s（这条条款下另有 %d 组改法，本次按%s给出；全量见「依据」里的条款）" % (
        fix, len(pairs), "首组" if first else "命中片段")


def _five_three_block(findings, report_ref="", text="", advisories=None):
    """PRD §5.3.3 的**逐条块**（问题数 1–2 时逐条输出；≥3 时分类汇总 + 报告链接）。

    ★ 2026-10-06 加。事故：Owner 拿 PRD §5.3.3 的模板对照守衡发出去的 BLOCK 卡片 ——
      **抬头是对的、逐条四要素整块没有**。根因是渲染器有两套，而这一套（P0 快路）
      只出「四段溯源表格」，从没出过 §5.3 的逐条格式。改 `review_engine.py` 那套**改不到这里**。

    ★ 措辞**逐字照 PRD**，不许同义替换（`【审查结论：BLOCK】共发现 N 处必须修改。` /
      `请修改后重新提交。`）。缺的格子写「（来源未给 X）」，**不代填**：
      缺了要看得见，替它圆过去才是真出错。

    ★ `report_ref`（2026-10-06 加）= 报告的**链接或路径**，由调用方给。
      PRD §12 把「P0 层响应 ≤1s」与「报告生成 ≤30s」定成**两条独立指标** ⇒
      **回执不许等报告**：这里只负责把链接填进去，报告本身在回执之后生成。
      为空就照实说「报告稍后补」—— **不编一个链接**（编了等于把没发生的事写成发生了）。
    """
    n = len(findings)
    L = ["【审查结论：BLOCK】共发现 %d 处必须修改。" % n, ""]
    if n >= 3:
        # PRD §5.3.3「≥3 个时只输出分类汇总 + 报告链接」
        # ★ 计数只走 `_summary_lines`（= `_summary_counts`）—— 与报告同一份，见那里的注释。
        L.extend(_summary_lines(findings))
        L.append("")
        L.append("→ 查看完整问题清单与修改建议：%s" % (
            report_ref or "（报告在**回执之后**补，稍后单独发；补到之前这一格不填）"))
        L.append("")
        L.append("请修改后重新提交。")
        return L

    L.extend(_prd_block(_item_fields(findings, text)))
    _adv = _advisory_line(advisories)
    if _adv:
        L.append(_adv)
        L.append("")
    L.append("请修改后重新提交。")
    return L


def _basis_line(lib, ver, art, entry_url):
    """「依据」行 —— PRD §5.3.3 的版式：`《库 版本》第 X 条（链接：<url>）`。

    ★ 2026-10-08（Owner 原话：「**依据中，链接必须是飞书链接，我点击可以打开的**」）：
      改前这里印的是 `kb/l3/candidates/rules.jsonl#W-1.8` —— **库内相对路径，业务同事点不开**；
      而且 L1–L3 是库的**内部加工层**，点进去也没有下一步动作。
      现在链接槽位放 **L0 飞书记录直链**（`entry_url`，取自 `_l0_verbatim`）。

      ⚠️ 取不到时**照实说取不到**，绝不拿库内路径冒充「原始出处」——
         PRD §5.3.3 原文要的是 `（链接：https://...）`，相对路径本来就不满足它。
      ⚠️ 与走链那侧（`review_engine._evidence_line`）**措辞不同、方向一致**：
         那侧今天改成了 `← 逐字命中「…」｜原始出处：<url>`；本侧按 PRD 保持 `（链接：…）` 形状，
         因为 `_prd_block` 的版式是 PRD 逐字契约（selftest ④/⑥c 盯着）。
    """
    if entry_url:
        return "《%s %s（试用版，未发布）》第 %s 条（链接：%s）" % (lib, ver, art, entry_url)
    # ★★ 2026-10-21（Owner：「审查报告中不能出现后台语言」）：
    #   改前这一行印 `（链接：未定位到飞书直链；库内路径 kb/l3/candidates/rules.jsonl#W-1.33）`
    #   —— 库内相对路径业务侧点不开，PRD §5.3.3 要的也是 `（链接：https://…）`。
    #   取不到就**只说取不到**；按条款号回源这件事由「依据」那两格（库名+条款号）承担。
    return ("《%s %s（试用版，未发布）》第 %s 条（链接：未定位到飞书直链）" % (lib, ver, art))


def _item_fields(findings, text=""):
    """每条问题的**六格内容** —— 回执与报告**唯一的抽取点**。

    `text` = 这一单的**素材原文**（链送进来的那份，带 `【图片 N …】`/`【视频 N …】` 块头）。
      2026-10-20 加：位置那一格要按块给形态，就得看原文；只给 `findings` 时位置回落
      `正文第 N 段`（与改前逐字一致，夹具/老调用方行为不变）。

    ★ 2026-10-06 加，起因是 Owner 现场报：「守衡说 3 个问题，云文档里只落 1 个」。
      **实测云文档里三条都在**（三个独立 `<p>`），但**读起来像一条**，根因是版式：
      `1.` 后面**紧跟 `【`（没有空格）** ⇒ markdown 不认成有序列表 ⇒
      三条各是**一堵整段**（实测 776 / 569 / **1127** 字），没有标题层级、进不了文档目录，
      第一屏只看得见第 1 条。**用户看到的是真的，只是原因不是"没写进去"。**

    ⇒ 结论：**内容只能有一套，版式必须按介质分两套**。
      格子的值在这里一次取好，回执与报告都从这里取；两种版式只是排版，不许各抽一套。
      （这一条是「**后续两端数据必须对齐**」的落点：值同源、计数同源，见 `_summary_counts`。）
    """
    items = []
    for i, f in enumerate(findings, 1):
        cl = f.get("clause") or {}
        vb = f.get("verbatim") or {}
        rule = f.get("_l3") or {}
        lib = _LIB_NAME.get(str(rule.get("kb_type") or ""), rule.get("kb_type") or "（来源未给库名）")
        # ★★ 2026-10-14：条款号**先取模式表自带的那一格**。
        #   病灶：`clause` 与 `_l3` 都取不到时原先直接写「（来源未给条款号）」，
        #   而**模式表 `p0_patterns.jsonl` 里本来就带着 `article_no`**
        #   （实测那条 V02：`article_no="E-2.124"`）—— 手上有号却说没有，是最没道理的一种缺。
        #   顺序：L4 canonical（最权威）→ L3 候选 → 模式表自带 → 才算真没有。
        #   ⚠️ 顺序在 2026-10-14 当天**改过一次，这里是第二次的结论**：
        #     第一版写成 `L4 → L3 → 模式表`，实测**踩中一条脏数据** ——
        #     `external_standard.jsonl` 里 **129 个 rule_id 全部重复**（同一 rid 两行，
        #     条款号一格是 `E-1.3419`、另一格是 `E-2.124`，`rule_text` 逐字相同），
        #     于是「先读到的先用」等于**随机取一个号**。
        #     取证：`kb/l7/registry/layers.yaml:217` 明写「这 123 条是**条款级（法条型）**规则…
        #     唯一正确的段是 **E-2**」⇒ `E-2.124` 才是对的那个；`E-1.3419` 是重复行带进来的。
        #     ⇒ 模式表自带的那格**与模式表同源、逐条可核**，优先于可能有重复的 L3 候选。
        #       （L4 canonical 仍最优先：真发过号的以台账为唯一真源。）
        art = (cl.get("article_no") or f.get("article_no")
               or rule.get("article_no") or "（来源未给条款号）")
        # ★ 链接：L0 逐字回源的 `entry_url` 优先；没有就用条款的 `resource_id` 现接一条。
        _entry = (vb or {}).get("entry_url") or _resource_url(rule.get("resource_id")) or ""
        _adv, _adv_src = _suggestion_for(f, art)
        # ★★ 2026-10-19（Owner：「所属类别/所属子类」统一到 A3 12 类）：
        #   卡面逐条首行与 ≥3 汇总都读这两格；**取不到就落 `未归类`**（12 类里的兜底类，
        #   不是我自己造的桶名）—— 12 类名与子类名的真源是 `kb/l3/registry/rule-taxonomy.json`。
        _tax = str(rule.get("taxonomy_category") or f.get("taxonomy_category") or "").strip() or TAX_UNCLASSED
        _taxsub = str(rule.get("taxonomy_subcategory") or f.get("taxonomy_subcategory") or "").strip()
        items.append({
            "n": i,
            "code": f.get("rule_code") or "（来源未给规则码）",
            # ⚠️ `category` = **A1 库内 8 类词表**（内部分类/路由用）——**不再上卡**；
            #   上卡的是下面的 `taxonomy_category` / `taxonomy_subcategory`（A3 12 类）。
            "category": f.get("_category") or "未分类-未分类",
            "taxonomy_category": _tax,
            "taxonomy_subcategory": _taxsub,
            # ★★ 2026-10-19：位置按 **PRD §5.3.3** 精确到段（「正文第 X 段」），不再是写死的「全文」。
            "position": _position_of(f, text),
            # ★★ 2026-10-21（Owner：报告里不许出现后台语言）：原先印的是 `pattern`
            #   —— 正则命中时那是一条**正则源码**，却被写成「逐字命中」。改成真命中文字。
            "quote": "、".join(dict.fromkeys(_hit_text(m) for m in (f.get("matched") or [])[:6])) or "—",
            # ★★ 2026-10-21：去规则码前缀与括号里的口径说明（见 `_business_reason`）。
            "reason": _business_reason(rule.get("reason"), f.get("rule_code")),
            "article_no": art,
            "basis": _basis_line(lib, rule.get("kb_version") or "v0", art, _entry),
            # ⚠️ 这一格**只进报告与 JSON**（四段溯源要用），**不印上卡** ——
            #   PRD §5.3.3/§5.3.4 的逐条字段只有【维度-子类】位置·原文·原因·依据·建议。
            "anchor": "%s｜source_sha256：%s" % (
                f.get("anchor") or "（来源未给锚点）",
                f.get("source_sha256") or "（来源未给指纹）"),
            # ★★ 2026-10-14（Owner 裁定）：`verdict` 这一格**已删** —— 它原先被渲染成逐条块里的
            #   `**判定**：事实（确定性逐字匹配）｜置信度：未给…`，而 PRD §5.3 逐条模板里
            #   没有这一行、三态只在结论行一处。**没有任何下游读它**（`grep verdict`：
            #   只有 `_prd_block` / `_doc_block` 两个渲染点，均已同步删除）⇒ 直接去掉这一格，
            #   不留「渲染删了、数据还在」的半截状态。
            "advice": _adv,
            "advice_source": _adv_src,
            "entry_url": _entry,
        })
    return items


# ── 位置：按**素材块**给形态（PRD §5.3.3 的三形态之一）──────────────────────────
#
# ★★ 2026-10-20（Owner 选「先修位置再验证」）：改前只有一种形态 `正文第 N 段`，
#   不管素材是文案、图还是视频 —— 2026-10-19 那张**图片单**因此印出「正文第 7 段」，
#   而素材里根本没有"正文"。
#   现在按**块**判：链送进来的素材原文本身带块头（`【图片 N …】` / `【视频 N …】`），
#   命中行的行号落在哪个块里，就按那个块的形态给：
#     · 图片块 ⇒ `图 N 第 X 处`（X = 该 finding 在这张图里的第几处命中，从 1 数）
#     · 视频块 ⇒ 该行若带帧时间码（`[12.3s]` 或 `[00:12]`）⇒ `视频 MM:SS`；
#                没带（音轨转写没有词级时间戳）⇒ 如实回落 `正文第 N 段`
#     · 其余（纯文案）⇒ `正文第 N 段`（与 2026-10-19 版逐字一致）
#   ⚠️ 这是**读出来的坐标**，不是编的：块头与行号都是链自己送进来的原文。
#     没有块头（老旁挂 / 夹具只给裸文本）⇒ 一律回落 `正文第 N 段`，行为与改前一致。
_IMG_HEAD = re.compile(r"^【\s*图(?:片)?\s*(\d+)[^】]*】")
_VID_HEAD = re.compile(r"^【\s*视频\s*(\d+)[^】]*】")
_FRAME_TC = re.compile(r"\[(\d+(?:\.\d+)?)\s*s?\]|\[(\d{1,2}):(\d{2})\]")


def _material_blocks(text):
    """把素材原文按块头切段：`[{"kind","index","start","end"}]`（行号 1 起、闭区间）。"""
    lines = (text or "").split("\n")
    out, cur = [], {"kind": "text", "index": None, "start": 1, "end": 0}
    for i, raw in enumerate(lines, start=1):
        mi, mv = _IMG_HEAD.match(raw), _VID_HEAD.match(raw)
        if not (mi or mv):
            continue
        cur["end"] = i - 1
        if cur["end"] >= cur["start"]:
            out.append(cur)
        cur = ({"kind": "img", "index": int(mi.group(1)), "start": i, "end": 0} if mi
               else {"kind": "video", "index": int(mv.group(1)), "start": i, "end": 0})
    cur["end"] = len(lines)
    if cur["end"] >= cur["start"]:
        out.append(cur)
    return out


def _frame_second(line):
    """一行里的帧时间码 ⇒ 秒（读不出返回 None）。"""
    m = _FRAME_TC.search(line or "")
    if not m:
        return None
    if m.group(1) is not None:
        return int(float(m.group(1)))
    return int(m.group(2)) * 60 + int(m.group(3))


def _position_of(finding, text=""):
    """**位置**（PRD §5.3.3 三形态之一：`图 N 第 X 处` / `视频 MM:SS` / `正文第 N 段`）。

    ★ 2026-10-19 加「精确到段」；★ 2026-10-20 加**按素材块给形态**（见上面那段头注）。
      规矩四条：
        · 取不到行号（老旁挂/夹具没带 `line`）⇒ 如实回落 `全文`；
        · 行号落在**图片块**里 ⇒ `图 N 第 X 处`（同图多处 ⇒ `第 X、Y 处`）；
        · 行号落在**视频块**里且该行带时间码 ⇒ `视频 MM:SS`；
        · 其余 ⇒ `正文第 N 段`（多处 ⇒ `正文第 N、M 段`，最多列 3 个）。
    """
    lines = []
    for m in (finding.get("matched") or []):
        ln = m.get("line")
        if isinstance(ln, int) and ln > 0:
            lines.append(ln)
    uniq = sorted(set(lines))
    if not uniq:
        return "全文"
    blocks = _material_blocks(text) if text else []
    src = (text or "").split("\n")
    by_img, vids, txt = {}, [], []
    for ln in uniq:
        b = next((x for x in blocks if x["start"] <= ln <= x["end"]), None)
        if b and b["kind"] == "img":
            by_img.setdefault(b["index"], []).append(ln)
        elif b and b["kind"] == "video":
            sec = _frame_second(src[ln - 1]) if 0 <= ln - 1 < len(src) else None
            if sec is None:
                txt.append(ln)
            else:
                vids.append("视频 %02d:%02d" % (sec // 60, sec % 60))
        else:
            txt.append(ln)
    out = []
    for idx in sorted(by_img):
        ks = list(range(1, len(by_img[idx]) + 1))
        out.append("图 %d 第 %s 处" % (idx, "、".join(str(k) for k in ks[:3])
                                      + ("等" if len(ks) > 3 else "")))
    out.extend(vids)
    if txt:
        shown = txt[:3]
        out.append("正文第 %s 段" % ("、".join(str(x) for x in shown)
                                     + ("等" if len(txt) > len(shown) else "")))
    return "；".join(out) if out else "全文"


_DIM = None


def _load_dimension():
    """加载**维度模块**（唯一实现 = `kb/l7/skills/kb-content-review/scripts/risk_category.py`）。

    ★ 为什么按路径加载（与 `_load_matcher()` 同一手法）：本文件在 `kb/l5/`，而唯一实现在
      L7 的 skill 目录下。写成包导入会造出一条**隐式耦合**（L5 依赖 L7 skill 的内部布局）；
      按路径加载把这条耦合**写在明处** —— 路径改了会当场报错，而不是悄悄走第二条口径。
    ★ 为什么必须共用同一份：**维度映射是口径**。P0 快路自己再写一份 ⇒
      「回执说合规、报告说措辞表达」那类两端打架（本库为「同一事实两处不一致」返工过）。
    """
    global _DIM
    if _DIM is None:
        try:
            _p = os.path.join(KB, "l7", "skills", "kb-content-review", "scripts",
                              "risk_category.py")
            spec = importlib.util.spec_from_file_location("kb_risk_category_l5", _p)
            m = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(m)
            _DIM = m
        except Exception as e:                                # noqa: BLE001
            print("[risk_category] ⚠ 维度模块加载失败 ⇒ 汇总**退回库内类别**（不编维度）：%s" % e,
                  file=sys.stderr)
            _DIM = False
    return _DIM


def _summary_key(f):
    """一条命中的**汇总分组键** —— 2026-10-19 起 = **A3 12 类**（`taxonomy_category`）。

    ★★ 2026-10-19（Owner：「所属类别/所属子类 参考桌面 xlsx 的 12 类…… 统一到 A3」）：
      改前这里按 **A2 PRD 四维**分（`risk_category`），而逐条首行印的是 **A1 8 类词表** ——
      同一张卡上两套轴。现在两处都取 **A3**（`taxonomy_category`，真源
      `kb/l3/registry/rule-taxonomy.json` ← 桌面 xlsx，638 条逐条带这两格）。
      取不到（模型侧条目、反例/案例层 sc-…）⇒ 落 **`未归类`**（12 类里的兜底类，**不是我造的桶名**）。
    """
    rule = f.get("_l3") or {}
    return (str(rule.get("taxonomy_category") or f.get("taxonomy_category") or "").strip()
            or TAX_UNCLASSED)


def _taxonomy_order():
    """A3 的 12 类**展示顺序**（真源 `kb/l3/registry/rule-taxonomy.json` 的 classes 次序）。

    读不到 ⇒ 只保证「未归类压最后」，其余按字典序（**不编一套顺序**）。
    """
    global _TAX_ORDER
    if _TAX_ORDER is None:
        _TAX_ORDER = []
        try:
            with open(os.path.join(KB, "l3/registry/rule-taxonomy.json"), encoding="utf-8") as fh:
                reg = json.load(fh)
            _TAX_ORDER = [str(c.get("name") or "").strip()
                          for c in (reg.get("classes") or []) if str(c.get("name") or "").strip()]
        except Exception as e:                            # noqa: BLE001
            print("[taxonomy] ⚠ 12 类注册表读不到 ⇒ 汇总顺序退回字典序：%s" % e, file=sys.stderr)
    return _TAX_ORDER


def _summary_counts(findings):
    """分类汇总的**计数** —— 回执与报告**同一个计数点**。

    ★ 「两端数据必须对齐」在这里落地：回执上那句「· X类问题：N 个」与报告开头那份汇总
      **必须是同一次 Counter 的结果**。各算一次就会出现「回执说 3、报告说 2」——
      而那正是 Owner 2026-10-06 报的那类事故的**形状**（数量对不上）。
      所以：**只有这一个函数能数数**，谁都不许自己 `counter()` 一遍。

    ★★ 2026-10-12（Owner 批准「推荐 ①」）：**分组键从「库内类别」改成 PRD §5.3 的四维**。
      改前印的是「· 功效宣称类问题：1 个」，而 PRD §5.3.2 的逐字示例是「· 合规类问题：3 个」
      —— 分的是**维度**，不是库内类别。评审链那一端（`review.py::render()` 的 ≥3 分支）
      同批改成同一口径；两端的桶名都取 `risk_category.UNMAPPED_BUCKET`（**不各写一份**）。
      ⚠️ 改的是**分组键**，不是计数：⑥e「两端各算一次、都必须等于 N」那条判据一个字没动。
    """
    from collections import Counter
    return Counter(_summary_key(f) for f in findings)


def _summary_lines(findings):
    """分类汇总（回执与报告共用同一份文本）—— **PRD §5.3.4 的 ≥3 样张形状**。

    ★ 形状逐字照 PRD：**一行**、`·` 分隔、`<维度>类：N 个`
      （样张原文：`· 合规类：X 个 · 消费者安全类：X 个 · 措辞类：X 个` —— 没有「问题」二字）。
      改前是**每类一行**且写成「· X类问题：N 个」：那是 2026-10-12 按 §5.3.2 的理解写的，
      而 §5.3.2 那张表（内嵌表格 `xcdTpv`）里其实**只有 状态/定义/动作 三列**，没有分类汇总样张；
      真正的样张在 §5.3.4 —— 2026-10-19 对着 PRD 正文核出来的。
    ★ 顺序：条数降序 → 并列时按政策件四维顺序（合规/消费者安全/产品描述/措辞表达）→
      「未标注维度」桶**压最后**（既不丢、也不并进任何一类；桶名取 `risk_category.UNMAPPED_BUCKET`，
      **不另写第二份四维词表**）。
    """
    bucket = TAX_UNCLASSED
    order = {name: i for i, name in enumerate(_taxonomy_order())}
    counts = _summary_counts(findings)
    # 顺序照 12 类注册表的固定次序；「未归类」压最后（都没登记时按字典序，不编顺序）
    keys = sorted(counts, key=lambda x: (x == bucket, order.get(x, 99), x))
    # ★ 形状（Owner 2026-10-19 第三次给的格式）：**每类一行**，行间不空行。
    #   兜底类写成 `· 未归类问题：N 个`（它就是 12 类里的兜底，不叫「未归类类问题」）。
    return ["· %s问题：%d 个" % (k if k == bucket else k + "类", counts[k]) for k in keys]


def _prd_block(items):
    """PRD §5.3.3 的逐条块（**回执**用）。**版式逐字照 PRD，不许改**：
    `N.【类别-子类】位置，逐字命中 原文` ＋ 缩进两格的 `**原因**/依据/建议`。

    ★★ 2026-10-14（Owner 裁定）：**`**判定**` 那一行已删** —— PRD §5.3 的逐条模板
      只有 原因 / 依据 /（BLOCK 才有）建议，三态只出现在**结论行** `【审查结论：X】`；
      逐条再挂一个「判定」会让同一张卡上出现两个「判定」，业务侧分不清哪个是结论。
      `_item_fields()` 那份数据里的 `fact_or_inference` / `confidence` **仍在**（只改版式）。

    ★★ 2026-10-19（Owner 逐字，两条）：「**去掉锚点**」「**L0 逐字去掉，飞书链接中依据中已经存在**」
      ＋「**卡片信息必须按照 PRD 字段执行**」。
      改前这一块印 **五行**（原因/依据/**锚点**/建议/**L0 逐字（可点直链）**），其中后两行是
      **库内坐标与重复链接**，PRD §5.3.3/§5.3.4 的逐条字段里**没有它们**：
        · 「锚点」`#表名/rec…/命中片段｜source_sha256：…` 是**回源坐标**，业务侧读不懂；
          实测它还印着一整段 PRD 小节标题（`#h.7. 知识库与规则体系 / 7.3 一票否决项…`）；
        · 「L0 逐字（可点直链）」与上一行「依据」里的 `（链接：…）`**同一个 URL**，印两遍。
      ⇒ 卡片逐条**只留 PRD 那五格**：【维度-子类】位置 · 原文 · 原因 · 依据（含链接）· 建议。
      ⚠️ **溯源没有丢**：`anchor` / `source_sha256` / `entry_url` 仍在 `_item_fields()` 的数据里，
        仍进 **JSON**、仍进 **报告**（`_doc_block` 的「锚点 + 指纹」「L0 逐字（可点直链）」两行
        与 `_provenance()` 的四段溯源表**一个字没动**）—— 少的是**卡上**那两行，不是证据。
        （判据：`kb/l8/e2e_acceptance.py` 的四段溯源、`workflow_smoke` S4 读的都是**报告与 JSON**，
         不是卡片；这两把尺子本批复跑过。）

    ★ 判据（selftest ②③④）逐字盯着这个版式，改它就会红 —— 这是故意的。
      ④ 另有三条**反向对照**：逐条块里一旦再冒出 `**判定**：` / `**锚点**：` / `L0 逐字`，精确变红。
    """
    L = []
    for it in items:
        # ★★ 2026-10-19（Owner：「所属类别/所属子类」统一到 A3 12 类）：
        #   首行标签从 **A1 8 类词表**（`绝对化与安全承诺-绝对化用语`）改成
        #   **A3 12 类**（`合规与受监管宣称-绝对化与最高级用语`）—— 与规则行、报告、汇总同一套。
        #   子类取不到就只印类别（不编一个子类出来）。
        _label = it.get("taxonomy_category") or TAX_UNCLASSED
        if it.get("taxonomy_subcategory"):
            _label += "-" + it["taxonomy_subcategory"]
        L.append("%d.【%s】%s，逐字命中 %s"
                 % (it["n"], _label, it.get("position") or "全文", it["quote"]))
        L.append("  **原因**：%s" % it["reason"])
        L.append("  **依据**：%s" % it["basis"])
        L.append("  **建议**：%s" % it["advice"])
        L.append("")
    return L


def _doc_block(items):
    """报告的逐条块（**云文档**用）：`### 问题 N ｜ 码 ｜ 类别` 进目录 ＋ 每格一行。

    ★ 为什么要另起一套版式（Owner 2026-10-06 现场「只看到 1 个问题」）：
      · **标题层级**：`###` 在飞书云文档里是 Heading 3 ⇒ **进文档目录**，
        打开就能看见「问题 1 / 2 / 3」三条，点哪条跳哪条 —— 「数不出条数」这件事从根上没了；
      · **每格一行**（`- **原因**：…`）：markdown 的无序列表飞书认，渲染成项目符号，
        不再是一堵 1000+ 字的字墙。
      **内容一字不改**（全部取自 `_item_fields`），改的只是排版 —— 这是与回执对齐的前提。

    ★★ 2026-10-19：报告这一版**保留**「锚点 + 指纹」与「L0 逐字（可点直链）」两行
      （删的只是**卡片**上那两行 —— 报告是回源件，四段溯源在这里）；
      同时补两处：① `- **位置**：` 与卡片同一格值（PRD §5.3.3「位置精确到段」）；
      ② 建议若来自**兜底表**（不是库内原话），在格尾如实标出来源 ——
         卡上不许带标记（PRD 五格），报告里必须带（否则读者会以为那是库规原文）。
    """
    L = []
    for it in items:
        L.append("### 问题 %d ｜ %s ｜ %s" % (it["n"], it["code"], it["category"]))
        L.append("")
        L.append("- **位置**：%s" % (it.get("position") or "全文"))
        L.append("- **命中（逐字）**：%s" % it["quote"])
        L.append("- **原因**：%s" % it["reason"])
        L.append("- **依据**：%s" % it["basis"])
        L.append("- **锚点 + 指纹**：%s" % it["anchor"])
        src = str(it.get("advice_source") or "")
        note = ""
        if src.startswith("p0_advice_book") or src.startswith("generic_"):
            note = "（改法来源：%s —— **库内没有原话改法**，按条款边界给的，不是库规原文）" % (
                "P0 兜底改法表 p0_advice_book" if src.startswith("p0_advice_book") else "按命中表述给出的通用改法")
        L.append("- **建议**：%s%s" % (it["advice"], note))
        if it["entry_url"]:
            L.append("- **L0 逐字（可点直链）**：%s" % it["entry_url"])
        L.append("")
    return L


def _md_cell(v):
    """表格单元格转义。**不是洁癖，是实测被切断过**（2026-10-06）。

    命中模式里带正则的「或」`|`（例如 `\\b(safest|perfect|zero[\\s-]?risk)\\b`），
    直接塞进 markdown 表格单元格 ⇒ **列的分隔符就在模式中间** ⇒ 渲染时从第一个 `|` 断掉。
    实测云文档里那一行只剩 `` `\\b(safest` ``，后面的 `perfect` / `zero risk` **全丢了** ——
    而屏幕上的 markdown 源码看起来是好的（终端不按表格渲染），**只有落进云文档才看得见**。
    换行同理（单元格里一行变两行 = 表格结构坏掉）。
    """
    return str(v if v is not None else "—").replace("|", "\\|").replace("\n", " ")


def _provenance(text, findings, summary_only=False):
    """【来路与边界】+ 四段溯源明细 —— **回执与报告共用**。

    ★ 抽出来的理由同 `_item_fields`：这两节是「不许把它读成别的东西」的护栏，
      报告与回执**必须一字不差**；各写一份就会出现「回执有边界、报告没有」这种事故。

    ★ `summary_only`（2026-10-06）：回执在 ≥3 条时**只出分类汇总**（PRD §5.3.3），
      所以那句「完整清单见报告」只对**回执**成立；报告里是全量逐条，写它会自相矛盾。
    """
    L = []
    # ── 以下为**来路与边界**：PRD §5.3 管格式，这一节管「不许把它读成别的东西」。
    #    Owner 2026-10-05 现场定的口径：这是红线拦截，**不得说成整链跑完或专项审过**。
    L.append("【来路与边界】（必须一起读，一条都不许吞）")
    L.append("")
    L.append("- 走的是 **P0 快路**（PRD §6.3 第一层，确定性匹配，**不动用大模型推理**）；")
    L.append("  **本结论未跑 L4→L5→L6→L7 层前置与评审链** —— 它是一条红线拦截，"
             "**不是专项审查结论**，也不能当作 PASS 依据。")
    L.append("- 判定对象（逐字）：%s" % (text or "").replace("\n", " / ")[:200])
    if summary_only and len(findings) >= 3:
        L.append("- 问题数 ≥3 ⇒ 上面只出分类汇总；**完整清单与逐条修改建议在报告里**"
                 "（报告在回执**之后**生成，链接补在上一条）。")
    L.append("")
    L.append("### 附：四段溯源明细（回源用）")
    for i, f in enumerate(findings, 1):
        cl = f.get("clause") or {}
        vb = f.get("verbatim") or {}
        L.append("")
        L.append("**问题 %d ｜ %s（%s）**" % (i, f.get("rule_code"), f.get("level")))
        L.append("")
        L.append("| 段 | 值 |")
        L.append("|---|---|")
        L.append("| ① 条款号（L4） | **%s**%s |" % (
            _md_cell(cl.get("article_no") or "（%s）" % _l4_clause_miss_reason(
                f.get("rule_id"), f.get("rule_code"))),
            _md_cell("（form=%s，%s）" % (cl.get("form"), cl.get("source_file"))) if cl else ""))
        L.append("| ② 命中片段（L3/L5） | %s（命中 %s 处，模式 %s） |" % (
            _md_cell("、".join("`%s`" % m.get("pattern") for m in (f.get("matched") or [])[:6]) or "—"),
            _md_cell(f.get("matched_count")), _md_cell(f.get("pattern_id"))))
        L.append("| ③ 锚点 + 指纹 | `%s` ｜ `%s` |" % (
            _md_cell(f.get("anchor")), _md_cell(f.get("source_sha256"))))
        if vb.get("entry_url"):
            L.append("| ④ L0 逐字（可点直链） | [%s](%s) ｜ 原值 `%s` |" % (
                _md_cell(vb.get("record_id")), _md_cell(vb.get("entry_url")),
                _md_cell((vb.get("raw_verbatim") or "")[:60])))
        else:
            L.append("| ④ L0 逐字 | ⚠️ 直链缺失（%s）—— 需人工回源 |" % _md_cell(vb.get("note") or "未取到"))
        if f.get("whitelist_suppressed"):
            L.append("")
            L.append("- 安全词抑制：%s 处被白名单放行（未计为命中）" % f["whitelist_suppressed"])
    return L


def _report_md(text, findings, generated_at=""):
    """P0 快路的**报告正文**（本地 .md；云端文档按同一份正文投递）。

    ★ 为什么单起一份（2026-10-06，Owner 定）：PRD §12 把「P0 层响应 **≤1s**」与
      「报告生成 **≤30s**」定成**两条各自独立的指标** ⇒ 两件事**不许互相拖累**：
      回执走 `_render`（同步、越快越好），报告走这里（**在回执之后**生成，写完再把链接补进去）。
      「≥3 条只出分类汇总」是 PRD §5.3.3 对**回执**的约束；报告里必须是**全量逐条**，
      否则「查看完整问题清单」这句话就是假的。

    ★★ **两端对齐**（Owner 2026-10-06：「后续两端数据必须对齐」）在这份函数里的三条落法：
      ① **条数**：`共发现 N 处` 的 N 与逐条块的条数**同出 `len(findings)`**，不各算一次；
      ② **计数**：分类汇总走 `_summary_lines`（同一份文本，回执也用这个函数）；
      ③ **值**：每格的正文全部来自 `_item_fields`（回执那套版式也取同一份）。
      ⇒ 判据 ⑥e/⑥f 逐条盯着这三件事（selftest）。
    """
    items = _item_fields(findings, text)
    L = ["# 内容审查报告（P0 快路 · 红线拦截）", ""]
    L.append("【审查结论：BLOCK】共发现 %d 处必须修改。" % len(findings))
    L.append("")
    if generated_at:
        L.append("- 报告生成时间：%s" % generated_at)
        L.append("")
    # ── 产品线 / 渠道（取数口 = `l0_facets`：**本素材自己的记录**优先，其次素材原文）────
    fx = _facets_of(findings, text)
    if fx.get("product_line") or fx.get("channel"):
        L.append("- **产品线 / 渠道**（%s）：**%s** / **%s**" % (
            "、".join(v for v in (fx.get("from") or {}).values() if v) or "（来源未记）",
            fx.get("product_line") or "（本单未取到）",
            fx.get("channel") or "（本单未取到）"))
        L.append("")
    # ── 分类汇总：与飞书回执**同一份计数**（`_summary_lines` 是唯一计数出口）────────
    if len(findings) >= 3:
        L.append("**分类汇总**（与飞书回执同一份计数）：")
        L.append("")
        L.extend(_summary_lines(findings))
        L.append("")
    # ── 一眼数得出条数的索引表（Owner 现场「只看到 1 个问题」时最缺的就是这个）──────
    L.append("| # | 规则码 | 类别 | 条款号 |")
    L.append("|---|---|---|---|")
    for it in items:
        L.append("| %d | %s | %s | %s |" % (
            it["n"], _md_cell(it["code"]), _md_cell(it["category"]), _md_cell(it["article_no"])))
    L.append("")
    L.append("## 一、问题清单与修改建议（全量 %d 条）" % len(items))
    L.append("")
    L.extend(_doc_block(items))
    L.append("请修改后重新提交。")
    L.append("")
    L.append("---")
    L.append("")
    L.extend(_provenance(text, findings))
    return "\n".join(L) + "\n"


def _write_report(path, content):
    """把报告写进 `path`。**必须经 `/bin/cp` 落地**（2026-10-06 实测）。

    为什么不能直接 `open(path,"w")`：这样写出来的文件，**宿主那一侧**看到的是
    一个带 4096 字节信封的版本（实测 `wc -c` 4127 / 真实 31），读起来像 binary。
    机理是环境层面的（`read()` 拿到真内容、`stat` 尺寸被加过），所以：
      · 先写临时件，再 `/bin/cp` 过去 —— 实测 `cp` 出来的**两个观察口径一致**（31/31）；
      · 写完整**回读复核**（长度 + 首行），不一致就当失败抛出去，**不静默**。
    """
    import os
    import subprocess
    d = os.path.dirname(os.path.abspath(path)) or "."
    os.makedirs(d, exist_ok=True)
    tmp = os.path.join(d, ".%s.tmp" % os.path.basename(path))
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(content)
    subprocess.run(["/bin/cp", tmp, path], check=True)
    os.unlink(tmp)
    back = open(path, encoding="utf-8").read()
    if len(back) != len(content):
        raise RuntimeError("报告回读长度不符：写入 %d / 读回 %d（%s）"
                           % (len(content), len(back), path))
    return path


def _render(text, findings, report_ref="", advisories=None):
    """回执正文（PRD §5.3.3）。**这条路是 ≤1s 的** —— 所以它不许做任何 IO。

    ★ `report_ref`（2026-10-06）：报告在回执**之后**生成 ⇒ 这里只**填**链接、不等它。
      为空（还没补上）就照实写「稍后补」，见 `_five_three_block` —— **不编链接**。
    """
    L = list(_five_three_block(findings, report_ref, text,
                               advisories=advisories or _advisories(text)))
    L.append("")
    L.append("---")
    L.append("")
    L.extend(_provenance(text, findings, summary_only=True))
    L.append("")
    L.append("---")
    L.append("下一步：按 PRD §5.3，BLOCK 需「修改后重新提交」；"
             "本单未跑专项审查，**若素材属图片/视频/产品宣称等模态，仍需转对应专项复核**。")
    return "\n".join(L)


def selftest():
    """判据自证（离线，不联网）。**这条路径此前一条判据都没有** —— 2026-10-06 补。

    为什么必须有它：Owner 拿 PRD §5.3.3 的模板对照守衡发出去的 BLOCK 卡片，
    发现**抬头对、逐条四要素整块没有**。而 `_render` 是这条红线路径的**唯一出口**，
    改它之前**没有任何东西会红** —— 也就是说这次改动原本是「改完靠人看」。

    样本是**真实素材**（2026-10-06 08:57 那一单的原话），不是编的。
    """
    import re
    import json as _json_
    P, F = [], []

    def chk(name, cond, extra=""):
        (P if cond else F).append(name)
        print("  %s %s%s" % ("✅" if cond else "❌", name, ("  " + extra) if extra else ""))

    def _sum_keys(text):
        """从回执/报告里取分类汇总 `[(维度, 计数)]` —— 口径 = **每类一行** `· <维度>类问题：N 个`。

        ★ 判据只认这一种形状，且**只认行首**：形状一变（例如又缩成一行用 `·` 分隔），
          取到的就是 `[]` ⇒ ⑥e/⑥e2/⑥g3 立刻红（那正是要看见的信号）。
        """
        out = []
        for ln in str(text).split("\n"):
            m2 = re.match(r"^· (.+?)类问题：(\d+) 个$", ln.strip())
            if m2:
                out.append((m2.group(1), int(m2.group(2))))
        return out

    # ① 真实素材：必须命中，且渲染出 PRD §5.3.3 的逐条块
    TEXT = "这段 listing 文案能不能发：Our M5 breast pump is doctor recommended and helps increase milk supply in 3 days."
    res = evaluate(TEXT)
    chk("① 真实素材命中 P0", res.get("hit") is True, "hits=%s" % (res.get("issue_count")))
    r = res.get("rendered") or ""

    chk("② 首行 = PRD §5.3.3 结论行（逐字）",
        bool(re.match(r"^【审查结论：BLOCK】共发现 \d+ 处必须修改。$", r.split("\n")[0], re.M)),
        repr(r.split("\n")[0]))
    chk("③ 尾部动作 = 「请修改后重新提交。」", "请修改后重新提交。" in r)

    # ④ 逐条四要素：每条必须齐【类别-子类】/ 原因 / 依据 / 建议
    # ★ 判据**不许崩**：表头一旦不合规（正是要抓的那种情形），
    #   原先这里 re.search(...).group(1) 会抛 AttributeError ——
    #   表现是「自证退 1」，但**后面 ④–⑧ 一条都没跑**：看的人只知道红了、
    #   不知道红在哪，而且那不是判据在判，是脚本死了。
    #   实测逮到过一次（把抬头改回旧格式的变异测试）。现在解析不出来就记一条失败，继续往下走。
    _m = re.search(r"共发现 (\d+) 处", r)
    n = int(_m.group(1)) if _m else -1
    chk("④ 逐条条数 == findings 条数", n == res.get("issue_count"),
        "%s vs %s" % (n, res.get("issue_count")))
    DETAIL = re.findall(r"^\d+\.【[^】]+】[^\n]*\n(?:  [^\n]*\n?)+", r, re.M)
    chk("④ 每条都渲染出逐条块", len(DETAIL) == n, "实测 %d 条" % len(DETAIL))
    # ★★ 2026-10-19（Owner：「去掉锚点」「L0 逐字去掉」）：PRD 逐条五格 =
    #   【维度-子类】位置 · 原文 · 原因 · 依据（含链接）· 建议 ⇒ **三行**（原因/依据/建议）。
    want = ("  **原因**：", "  **依据**：《", "  **建议**：")
    miss = [w.strip() for d in DETAIL for w in want if w not in d]
    chk("④ 每条三要素齐全（原因/依据/建议）", not miss, "缺：%s" % miss)
    # ★★ 2026-10-14（Owner 裁定）：逐条块里**不许再有 `**判定**` 行** ——
    #   PRD §5.3 逐条模板只有 原因/依据/（BLOCK 才有）建议，三态只在结论行一处。
    #   这条是**反向对照**：谁把那一行加回来，这里精确变红（而不是只在人眼里看着不对）。
    #   ⚠️ 只查**逐条块**里的加粗标签：`判定对象（逐字）` 是另一格（「审的是哪段素材」），
    #      与本次裁定无关，**不在**这条断言的射程内。
    chk("④ 逐条块不再出现 `**判定**` 行（三态只在结论行）",
        not re.search(r"^\s+\*\*判定\*\*：", r, re.M),
        "命中：%s" % re.findall(r"^\s+\*\*判定\*\*：[^\n]*", r, re.M)[:2])
    # ★★ 2026-10-19（Owner 两条裁定，**各有反向对照**）：
    #   · 卡上**不许**再出现「锚点」那一行（库内坐标，业务侧读不懂；PRD 字段里没有它）
    #   · 卡上**不许**再出现「L0 逐字（可点直链）」那一行（与「依据」里的链接**同一个 URL**）
    _anch = re.findall(r"^\s+\*\*锚点\*\*：[^\n]*", r, re.M)
    chk("④2 卡上不再有 `**锚点**` 行（Owner 2026-10-19）", not _anch, "命中：%s" % _anch[:2])
    _l0 = re.findall(r"^\s*L0 逐字（可点直链）[:：][^\n]*", r, re.M)
    chk("④3 卡上不再有 `L0 逐字（可点直链）` 行（与依据里的链接重复）", not _l0, "命中：%s" % _l0[:2])
    #   反向对照：把这两行**真造回**卡上 ⇒ ④2/④3 必须精确变红（否则它们只是注释）。
    _rmut = r.replace("  **依据**：", "  **锚点**：#自证/recX/命中片段｜source_sha256：deadbeef\n"
                                   "  **依据**：", 1).replace(
                        "  **建议**：", "  L0 逐字（可点直链）：https://example.invalid/x\n  **建议**：", 1)
    chk("④4 反向对照：把锚点/L0 逐字塞回卡上 ⇒ ④2/④3 会红",
        bool(re.findall(r"^\s+\*\*锚点\*\*：[^\n]*", _rmut, re.M))
        and bool(re.findall(r"^\s*L0 逐字（可点直链）[:：][^\n]*", _rmut, re.M)))
    # ★★ 2026-10-19（Owner：「**必须给建议**」）：建议那一格**不许是占位符**。
    #   这个坑是 Owner 拿真卡指出来的（`**建议**：（来源未给修改建议）`）：17 条 P0 里 10 条落到那。
    _fake = re.findall(r"^\s+\*\*建议\*\*：(（来源未给|（两侧都没给|（无）|$)", r, re.M)
    chk("④5 建议不是占位符（「来源未给…」/空）", not _fake, "命中：%s" % _fake[:2])
    _adv_lines = re.findall(r"^\s{2}\*\*建议\*\*：(.*)$", r, re.M)
    chk("④6 每条建议都有正文（条数对得上）",
        len(_adv_lines) == n and all(x.strip() for x in _adv_lines),
        "%d 行 / %d 条 ｜ %r" % (len(_adv_lines), n, _adv_lines[:1]))
    #   反向对照：把建议打回占位符 ⇒ ④5/④6 必须红。
    _amut = re.sub(r"^(  \*\*建议\*\*：).*$", r"\1（来源未给修改建议）", r, count=1, flags=re.M)
    chk("④7 反向对照：建议写回占位符 ⇒ ④5 会红",
        bool(re.findall(r"^\s+\*\*建议\*\*：(（来源未给)", _amut, re.M)))

    # ⑤ 类别-子类是**A3 12 类**的受控取值，不是自造
    #   ★★ 2026-10-19（Owner：「所属类别/所属子类 统一到 A3 12 类」）：判据从 A1 8 类词表
    #   换成 A3 注册表（`kb/l3/registry/rule-taxonomy.json`：12 类 + 58 子类）。
    cats = re.findall(r"^\d+\.【([^】]+)】", r, re.M)
    try:
        _reg = _json_.load(open(os.path.join(KB, "l3/registry/rule-taxonomy.json"), encoding="utf-8"))
        _known_cls = {str(c.get("name") or "").strip() for c in (_reg.get("classes") or [])}
        _known_sub = set((_reg.get("subclass_to_category") or {}))
    except Exception:                                         # noqa: BLE001
        _known_cls, _known_sub = set(), set()
    chk("⑤ 12 类注册表可用（否则下面两条是空转）", len(_known_cls) == 12 and len(_known_sub) == 58,
        "classes=%d ｜subclasses=%d" % (len(_known_cls), len(_known_sub)))
    _bad = []
    for c in cats:
        head, _, tail = c.partition("-")
        if head not in _known_cls or (tail and tail not in _known_sub):
            _bad.append(c)
    chk("⑤ 逐条 `【所属类别-所属子类】` 取自 A3 注册表（不自造）", not _bad and bool(cats),
        "越界：%s ｜实测：%s" % (_bad, cats))
    chk("⑤b 首行标签**不再是 A1 8 类词表**（那是内部分类，不上卡）",
        not any(c in set(_vocabulary().values()) for c in cats),
        "仍出现 A1 标签：%s" % [c for c in cats if c in set(_vocabulary().values())])

    # ⑥ 来路与边界**一条都没被 §5.3 的格式挤掉**（这是 Owner 现场定的硬口径）
    chk("⑥ 边界：明说未跑四层与评审链", "未跑 L4→L5→L6→L7 层前置与评审链" in r)
    chk("⑥ 边界：明说不是专项审查结论", "不是专项审查结论" in r)
    chk("⑥ 边界：附了四段溯源明细（回源用）", "四段溯源明细" in r and "① 条款号（L4）" in r)

    # ⑥b ★ 「建议」那一格的长度必须**有界** —— 2026-10-06 它就是这么爆的：
    #     P0 模式表的 `suggested_replacement` 是该 rule_code 下**所有修订组的拼接**
    #     （实测 W-1.18 连着 26 组、几千字），直接填进「建议：」那一格，
    #     一条建议几千字，卡片与上下文一起被撑爆。现在按命中片段挑，并留一条上限断言。
    longs = [(len(x), x[:40]) for x in re.findall(r"  建议：(.*)$", r, re.M) if len(x) > 800]
    chk("⑥b 「建议」每格 ≤ 800 字（撑爆过一次）", not longs, str(longs))

    # ⑥c 「依据」行的链接槽位必须是**业务同事点得开的飞书直链**。
    #     ★ 2026-10-08 重写（Owner：「依据中，链接必须是飞书链接，我点击可以打开的」）。
    #     旧判据是「指针里的条款号与依据行一致」——它盯的是 `rules.jsonl#W-1.8` 那个库内指针；
    #     换链之后那个对象没有了，**旧判据会恒真**（`ptr` 空 ⇒ `bool(ptr)` 假 ⇒ 反而恒红或恒绿，
    #     取决于写法），所以必须换成**盯链接本身**，否则就成了 §2.4 那种"判据成了注释"。
    #     判据：链接要么是 `http(s)://…`（飞书直链），要么是**明说没定位到**的兜底措辞；
    #     **裸的库内相对路径一律红**（它既点不开、又冒充原始出处）。
    _ok_link = lambda u: u.startswith("http") or u.startswith("未定位到飞书直链")
    ev = re.findall(r"  \*\*依据\*\*：《[^》]+》第 (\S+) 条", r)
    links = re.findall(r"  \*\*依据\*\*：[^\n]*（链接：([^）]*)）", r)
    bad = [u for u in links if not _ok_link(u)]
    chk("⑥c 依据行的链接是飞书直链（点得开）",
        bool(ev) and bool(links) and not bad,
        "依据=%s 链接=%s 非直链=%s" % (ev, [u[:44] for u in links], bad))
    # ⑥c2 反向对照：把链接换回库内路径 ⇒ ⑥c 必须红（拆掉这条，⑥c 就成了摆设）。
    r_mut = r.replace("https://", "kb/l3/candidates/rules.jsonl#")
    links_mut = re.findall(r"  \*\*依据\*\*：[^\n]*（链接：([^）]*)）", r_mut)
    bad_mut = [u for u in links_mut if not _ok_link(u)]
    chk("⑥c2 反向对照：链接换回库内路径 ⇒ ⑥c 会红", bool(bad_mut),
        "变异后非直链=%s" % [u[:44] for u in bad_mut])

    # ★★ ⑥c3/⑥c4（2026-10-14 加，Owner：「依据这里**必须**给飞书链接」）─────────────
    #   病灶（实测那条 V02 命中，素材「m8 pro吸奶器是最好的吸奶器」）：
    #     依据渲染成 `《（来源未给库名） v0（试用版，未发布）》第 （来源未给条款号） 条
    #     （链接：未定位到飞书直链；库内路径 kb/l3/candidates/rules.jsonl#（来源未给条款号））`
    #     —— 一个**点不开、也没有号**的依据，业务同事拿它没法回源。
    #   三条根因（各修一处，这里逐条钉住）：
    #     ① 取值口 `_l3_rule` 只读 `rules.jsonl` 一份，而这条落在 `external_standard.jsonl`；
    #     ② `kb_type` 真值是 `external_standard`，而库名映射表只写了 `external`；
    #     ③ 模式表自带的 `article_no` **根本没被搬进命中** ⇒ 渲染层永远拿不到号。
    #   反向对照：把库名/条款号打回占位符 ⇒ 本条必须红（否则它只是个注释）。
    _bads = [ln.strip()[:90] for ln in r.split("\n") if "**依据**：" in ln
             and ("来源未给库名" in ln or "来源未给条款号" in ln or "未定位到飞书直链" in ln)]
    chk("⑥c3 依据里不许出现「未给库名 / 未给条款号 / 未定位到直链」",
        not _bads, str(_bads))
    #    ⚠️ 变异必须**真造出缺陷**：第一版写成 `r.replace("外部标准库", …)`，
    #      而本自证用的素材根本不命中外部标准那一路 ⇒ **替换 0 处、变异等于没发生**，
    #      判据恒绿（这正是我在别处刚纠过一次的同一个坑）。现在用**通用正则**换掉
    #      「《任意库名 版本》第 任意号 条」里的库名与号，任何素材都改得动。
    _muta = re.sub(r"《[^》]*》第 [^ ]+ 条", "《（来源未给库名） v0》第 （来源未给条款号） 条", r)
    chk("⑥c4 变异真的发生了", _muta != r, "替换 0 处 ⇒ 下面的反向对照是空的")
    _badm = [ln for ln in _muta.split("\n") if "**依据**：" in ln and ("来源未给" in ln)]
    chk("⑥c4 反向对照：打回占位符 ⇒ ⑥c3 会红", bool(_badm), "变异后 %d 行" % len(_badm))

    # ⑥d 表格单元格里的 `|` 必须被转义 —— 2026-10-06 实测**云文档里被切断过**：
    #     命中模式是正则（`\b(safest|perfect|…)\b`），那个「或」**就是列分隔符**，
    #     渲染出来只剩 `` `\b(safest` ``，后面全丢。
    #     ★ 为什么非要有这条判据：**终端上看不出来** —— markdown 源码是完整的，
    #       只有落进云文档（按表格渲染）才现形。人眼在回执里也看不出来。
    tbl = [ln for ln in r.split("\n") if ln.startswith("| ") and ln.rstrip().endswith(" |")]
    badrows = [ln[:70] for ln in tbl if len(re.findall(r"(?<!\\)\|", ln)) != 3]
    chk("⑥d 表格单元格里的 `|` 已转义（被切断过一次）", bool(tbl) and not badrows, str(badrows))

    # ══ ⑥e/⑥f **两端对齐**（Owner 2026-10-06 当场要求：「后续两端数据必须对齐」）══════
    #    「两端」= 飞书回执 ↔ 云文档报告。当天的事故形状是：**回执说 3 条、文档里读出来像 1 条**。
    #    实测文档里三条都在（是版式挤成一堵字墙），但**「数量对不上」这件事必须由机器盯着** ——
    #    人眼对不上时只会觉得"怪"，说不清是少写了还是没渲染出来。
    #    所以这里把三件事钉死：**条数**、**分类计数的和**、**每格的值**。
    #    ★ 用 3 命中的真实素材重跑（原来的样本只有 2 条，走不到 ≥3 那条分支 —— 而那正是出事的分支）。
    BIG = ("Our M5 is the safest breast pump on the market and FDA approved. Totally pain-free.")
    big = evaluate(BIG)
    rcpt = big.get("rendered") or ""
    rep = _report_md(BIG, big.get("findings") or [], "（自证·固定时刻）")
    n_big = big.get("issue_count")
    n_doc = len(re.findall(r"^### 问题 \d+ ｜ ", rep, re.M))
    n_rcpt = int((re.search(r"共发现 (\d+) 处", rcpt) or [0, -1])[1])
    chk("⑥e 三处条数一致：回执 / 报告 / findings（≥3 那条分支）",
        n_big == 3 and n_big == n_doc == n_rcpt, "findings=%s 报告=%s 回执=%s" % (n_big, n_doc, n_rcpt))
    sum_rcpt = sum(n for _, n in _sum_keys(rcpt))
    sum_doc = sum(n for _, n in _sum_keys(rep))
    chk("⑥e 分类汇总计数之和 == 条数（两端各算一次，必须都等于 N）",
        sum_rcpt == n_big and sum_doc == n_big, "回执和=%s 报告和=%s N=%s" % (sum_rcpt, sum_doc, n_big))
    # ★★ 2026-10-19：汇总形状照 **PRD §5.3.4**（一行 `· X类：N 个 · Y类：M 个`）。
    #   形状变了就必须有判据跟着变 —— 否则 `_sum_keys` 只是自己哄自己。
    # ★★ 2026-10-19 第三次（Owner 逐字：「按照下面的格式优化，目前是写的一行」＋
    #   `· <类>类问题：N 个` 每类一行）——
    _sum_rows = [ln for ln in rcpt.split("\n") if ln.startswith("· ")]
    _row_re = r"^· [^·\n，]+类问题：\d+ 个$"
    chk("⑥e2 汇总形状 = 每类一行 `· <维度>类问题：N 个`（Owner 2026-10-19 给的格式）",
        bool(_sum_rows) and all(re.match(_row_re, ln) for ln in _sum_rows),
        str(_sum_rows[:3]))
    chk("⑥e2b 汇总行之间不空行（Owner 2026-10-14 裁定）",
        bool(re.search(r"个\n· ", rcpt)) or len(_sum_rows) == 1,
        "行数=%d" % len(_sum_rows))
    #   反向对照：缩成一行（`· 合规类问题：1 个 · 消费者安全类问题：1 个`）⇒ ⑥e2 必须红。
    _one_line = "· 合规类问题：1 个 · 消费者安全类问题：1 个"
    chk("⑥e3 反向对照：缩回一行 ⇒ ⑥e2 会红",
        not re.match(_row_re, _one_line),
        repr(_one_line))

    # ══ ⑥g **分组键 = 维度**（PRD §5.3.2；Owner 2026-10-12 批准「推荐 ①」）══════════
    #    改前两端印的是**库内类别**：「· 功效宣称类问题：1 个」；
    #    PRD §5.3.2 的逐字示例是「· 合规类问题：3 个」—— 分的是 **§5.3 四维**。
    #    ★ 这是**判据**，所以这里可以写死四维字面量（被测量的生产码不许写 —— 它只读政策件）。
    _m = _load_dimension()
    chk("⑥g 维度模块可用（报告「维度」格仍走 A2）", bool(_m), "得到 %r" % (_m,))
    _keys = sorted({_summary_key(f) for f in (big.get("findings") or [])})
    chk("⑥g2 汇总键 ∈ A3 12 类 ∪ {未归类}（不再出现 A1 库内类别 / A2 四维）",
        bool(_keys) and set(_keys) <= (_known_cls | {"未归类"}), "得到 %r" % (_keys,))
    _kr = [k for k, _ in _sum_keys(rcpt)]
    _kd = [k for k, _ in _sum_keys(rep)]
    chk("⑥g3 两端的分组键**逐字一致**（同一口径，不是各分各的）",
        bool(_kr) and sorted(set(_kr)) == sorted(set(_kd)),
        "回执 %r ｜ 报告 %r" % (_kr, _kd))
    _legacy = re.findall(r"· (功效宣称|绝对化与安全承诺|背书与资质|平台与促销|婴幼儿安全与场景)类",
                         rcpt)
    chk("⑥g3b 回执里不再出现 A1 库内类别键", not _legacy, "命中的库内类别键 %r" % (_legacy,))
    _legacy_dim = re.findall(r"· (合规|消费者安全|产品描述|措辞表达)类问题", rcpt)
    chk("⑥g3c 回执里不再出现 A2 四维键（汇总已切 A3）", not _legacy_dim,
        "命中的四维键 %r" % (_legacy_dim,))
    # ⑥g4 **反向对照**：兜底类名 `未归类` 不许与 12 类里任何一个真类重名 ——
    #      重名 ⇒ 未归类的条目会被并进那个真类（把「不知道」当「合规与受监管宣称」，本库最坏的一类）。
    #    兜底类 `未归类` **本来就是 12 类里的第 12 个**（Owner 的口径）——
    #    所以这条反过来说：它在注册表里**恰好出现一次**、且是**最后一个**（兜底位），
    #    真类（前 11 个）与它不重名。
    _cls_list = [str(c.get("name") or "").strip() for c in (_reg.get("classes") or [])]
    chk("⑥g4 兜底类 `未归类` 在注册表里恰好一次且排最后（反向对照）",
        bool(_cls_list) and _cls_list[-1] == TAX_UNCLASSED
        and _cls_list.count(TAX_UNCLASSED) == 1,
        "12 类：%r" % (_cls_list,))
    chk("⑥g4b 真类（前 %d 个）与兜底类不重名" % (len(_cls_list) - 1),
        bool(_cls_list) and TAX_UNCLASSED not in _cls_list[:-1],
        "真类：%r" % (_cls_list[:-1],))

    # ══ ⑨ 产品线 / 渠道（Owner 2026-10-06：「从知识库命中产品线和渠道的都填写进去」）════
    #    ★ 2026-10-06 改口径（准入闸）：命中的记录**是规则样本** —— 那条 `广告文案明细` 记录
    #      是一条**真实投放的 Google 广告**（外部广告ID GG-12d45aa812b7 / 展示 8372 / 花费 $117.28），
    #      它的 `品线/平台` 是**那条样本自己的投放属性** ⇒ **不许**拿来当本次素材的渠道。
    #      取值只认：**本素材自己的记录**（素材原文逐字在它里面）或**素材原文**受控词命中。
    #    ⚠️ 夹具必须换人：`BIG` 是**英文**样本（`Our M5 is the safest…`），里面**没有**中文受控词
    #      ⇒ 它那两格本来就该是空的（见 ⑨d）。用**中文素材**才验得了「取得对」。
    _CN = "M6 吸奶器能催奶，医生推荐，还模仿婴儿吸吮。"
    _cn = evaluate(_CN)
    _cnfac = _cn.get("facets") or {}
    chk("⑨ 中文素材：产品线取自**素材原文**（吸奶器）",
        _cn.get("product_line") == "吸奶器"
        and "素材原文" in ((_cnfac.get("from") or {}).get("product_line") or ""),
        "%r ← %s" % (_cn.get("product_line"), (_cnfac.get("from") or {}).get("product_line")))
    chk("⑨ 反向对照：命中记录是规则样本 ⇒ **不许**把它的平台（Google）当本次渠道",
        _cn.get("channel") == "", repr(_cn.get("channel")))
    _cnrep = _report_md(_CN, _cn.get("findings") or [], "（自证·固定时刻）")
    chk("⑨ 报告里写出产品线/渠道，且**来源写的是素材原文**（不是「命中记录」）",
        "产品线 / 渠道" in _cnrep and "吸奶器" in _cnrep and "素材原文" in _cnrep,
        " ｜ ".join(l for l in _cnrep.splitlines() if "产品线 / 渠道" in l))
    # ⑨d 反向对照：英文样本没有中文受控词 ⇒ **两格都空**（空是诚实的，不是漏了）
    chk("⑨d 反向对照：英文素材两格都空（不编）",
        not big.get("product_line") and not big.get("channel"),
        "%r / %r" % (big.get("product_line"), big.get("channel")))
    # ⑨c 正例：素材原文**自己写了**渠道 ⇒ 就该填它（不是空、也不是从样本记录借来的）
    _g = evaluate("这条 Google 广告：M6 吸奶器能催奶")
    chk("⑨c 素材原文写了渠道 ⇒ 渠道=Google（来源=素材原文）",
        _g.get("channel") == "Google"
        and "素材原文" in (((_g.get("facets") or {}).get("from") or {}).get("channel") or ""),
        "%r ← %s" % (_g.get("channel"),
                     ((_g.get("facets") or {}).get("from") or {}).get("channel")))
    # ⑨b 反向对照：**取不到就留空**，不许"编一个" —— 干净文案不命中，自然也没有 facets
    _clean = evaluate("吸奶器静音设计，夜里不吵醒宝宝，续航 8 小时")
    chk("⑨b 反向对照：未命中 ⇒ 没有产品线/渠道可写（不是编一个）",
        (_clean.get("hit") is False) and not _clean.get("product_line") and not _clean.get("channel"))
    # ⑥f **值**逐字一致：同一条问题的各格内容，两种版式里必须**一字不差**
    #    （版式允许不同：回执 `  **原因**：`、报告 `- **原因**：`；**值**不许不同）
    #    ★ 这一条**只能用 n≤2 的样本**验：PRD §5.3.3 规定 ≥3 条时**回执只出分类汇总**
    #      ⇒ 那条分支上回执**本来就没有逐条内容**，拿它比是错的（第一版就写错了，判据当场红）。
    #      所以：**条数/计数**在 ≥3 分支上验（⑥e），**逐条的值**在 n≤2 分支上验（⑥f）。
    #    ★★ 2026-10-19：两端比的格子**收窄到卡上真有的那几格**（原因 / 依据 / 位置 / 建议）。
    #      `anchor` 已经从**卡**上撤掉（Owner：「去掉锚点」）⇒ 它还在数据里、还在报告里，
    #      所以改成**单向**断言：报告必须带着它（溯源不许丢），卡不许带（另由 ④2 钉住）。
    items_small = _item_fields(res.get("findings") or [])
    rep_small = _report_md(TEXT, res.get("findings") or [], "")
    _both = tuple(k for k in ("reason", "basis", "advice", "position"))
    diffs = [it["n"] for it in items_small
             if not all(v and v in r and v in rep_small for v in (it[k] for k in _both))]
    chk("⑥f 两端每格的值逐字一致（位置/原因/依据/建议；n≤2 样本）", not diffs, "对不上的第 %s 条" % diffs)
    chk("⑥f3 锚点与指纹**只进报告、不进卡**（溯源没丢，只是不上卡）",
        all(it["anchor"] and it["anchor"] in rep_small and it["anchor"] not in r
            for it in items_small),
        "报告里有=%s 卡上有=%s" % ([it["anchor"] in rep_small for it in items_small],
                                [it["anchor"] in r for it in items_small]))
    # ⑥f2 反向对照：把报告里某一格的**值**改掉 ⇒ ⑥f 必须失配
    #      （第一版改的是条目**标题**，而 ⑥f 比的是**值** ⇒ 反向对照自己不红，等于没验。
    #        反向对照必须打在**判据真正读的那个量**上。）
    v0 = items_small[0]["reason"]
    tampered = rep_small.replace(v0, "（反向对照：此处被改过）", 1)
    chk("⑥f2 反向对照：报告里改掉一格的值 ⇒ ⑥f 会红",
        (v0 in rep_small) and (v0 not in tampered))

    # ══ ⑪ 建议兜底表（2026-10-19，Owner：「必须给建议」）══════════════════════
    #    「建议」这一格现在有第四个取数口 = `kb/l5/advice_book.py`（库内没原话时的那一句）。
    #    它自己的自证（长度 ≤30 字、非占位符、出处不许空、反向对照）在那边跑；
    #    这里钉**接线**：表真被调起来了吗？落到了哪一档？
    _ab = _advice_book()
    chk("⑪ 兜底改法表**装上了**（不是空壳）", hasattr(_ab, "ADVICE") and bool(getattr(_ab, "ADVICE", None)),
        "表内 %d 条" % len(getattr(_ab, "ADVICE", {}) or {}))
    _srcs = [it.get("advice_source") for it in items_small]
    chk("⑪2 每条建议都带来源标记（机读，写进 JSON/报告）",
        all(bool(x) for x in _srcs), str(_srcs))
    _placeholder = [it["n"] for it in items_small if "来源未给修改建议" in str(it["advice"])]
    chk("⑪3 逐条数据里不再有「（来源未给修改建议）」", not _placeholder, str(_placeholder))
    #    真单素材（Owner 截图那一句）原来命中靠的是 `最好`。
    #    ★★ 2026-10-19：按 Owner 裁定「超级/最好这类夸张词不算问题」，`最好` 已从 P0 出列
    #    ⇒ 那句**不再命中**（钉在下面 ⑪7 反向对照里）。
    #    ⑪4/⑪5/⑪6 钉的是「**兜底**改法表 + 位置精确到段 + 卡面印出」这条接线 ⇒ 素材必须
    #    仍然**只命中 V02**（V02 的 suggested_replacement 为空，才会落到兜底表；
    #    换 `最安全` 会先命中 H05，而 H05 自带 L3 修订建议 ⇒ 走 l3_fix_pair，⑪4 的前提就没了）。
    #    实测三个候选只有裸 `100%` 满足：V02 独有且 H05 的 `100%` 正则要求带「安全/有效…」搭配。
    #    断言语义一个字没改。
    _v02 = evaluate("这款吸奶器 100% 值得买。")
    _v02_items = _item_fields(_v02.get("findings") or [])
    chk("⑪4 真单素材（「100%」，V02 独有）落到兜底表，且建议非占位符",
        bool(_v02_items) and _v02_items[0]["advice_source"].startswith("p0_advice_book:")
        and "来源未给" not in _v02_items[0]["advice"],
        "%s ⇒ %r" % (_v02_items[0]["advice_source"] if _v02_items else "—",
                      _v02_items[0]["advice"] if _v02_items else "—"))
    chk("⑪5 位置按 PRD 精确到段（不再是写死的「全文」）",
        bool(_v02_items) and re.match(r"^正文第 \d+ 段$", _v02_items[0]["position"]),
        "%r" % (_v02_items[0]["position"] if _v02_items else "—"))
    _v02_r = _v02.get("rendered") or ""
    chk("⑪6 真单卡面上，位置那一段真的印出来了",
        bool(_v02_items) and ("】%s，逐字命中" % _v02_items[0]["position"]) in _v02_r,
        _v02_r.split("\n")[2] if len(_v02_r.split("\n")) > 2 else "")

    # ★★ 2026-10-19（Owner 裁定 A）：**放开的那一族必须真的不命中** —— 把这次口径改动钉成判据。
    #   素材就是上面改前用的那句（含 `最好`）。谁把 `最佳/最好/最(佳|优|强)` 或 `\bbest\b`
    #   加回 `kb/.work/l5_export.py` 的 H05/V02，这条就**精确变红**。
    #   同时这也是 ⑪4/⑪5/⑪6 改素材的反向对照：证明换词不是为了让闸门变绿而挑的。
    _puff = evaluate("这款吸奶器绝对是最好用的，妈妈值得拥有。")
    chk("⑪7 反向对照：主观最高级「最好」不再判 P0（Owner 2026-10-19 裁定 A）",
        _puff.get("hit") is False,
        "hit=%s codes=%s" % (_puff.get("hit"),
                             sorted({f.get("rule_code") for f in (_puff.get("findings") or [])})))
    # 同一条裁定下**保留族**必须照旧命中 —— 否则上面 ⑪7 可以靠「整族全放开」蒙混过去。
    _keep = evaluate("这款吸奶器 100% safe，零风险。")
    chk("⑪7b 反向对照：保留族（100% safe／零风险）仍判 P0",
        _keep.get("hit") is True,
        "hit=%s codes=%s" % (_keep.get("hit"),
                             sorted({f.get("rule_code") for f in (_keep.get("findings") or [])})))

    # ★★ 2026-10-20（Owner 选「先修位置再验证」）：**位置按素材块给三形态之一**。
    #   素材形状照链的真实送法：块头一行 + 块体若干行（`review_gate.chainInput`）。
    #   ⑪8 图片块 ⇒ `图 N 第 X 处`；⑪9 视频块带时间码 ⇒ `视频 MM:SS`；
    #   ⑪10 反向对照：同样一句素材、**去掉块头** ⇒ 必须回落 `正文第 N 段`
    #        （证明是"读块"在起作用，不是恒真）。
    _img = "【图片 1 的图内文字（本机 OCR）】\n这款吸奶器 100% 值得买。"
    _img_it = _item_fields(evaluate(_img).get("findings") or [], _img)
    chk("⑪8 图片块里的命中 ⇒ 位置按「图 N 第 X 处」",
        bool(_img_it) and re.match(r"^图 1 第 \d+ 处$", _img_it[0]["position"]),
        "%r" % (_img_it[0]["position"] if _img_it else "—"))
    _vid = "【视频 1｜a.mp4｜12.0s｜关键帧 1/1 帧读成功】\n画面上的字（按时间码）：\n[00:07] 这款吸奶器 100% 值得买。"
    _vid_it = _item_fields(evaluate(_vid).get("findings") or [], _vid)
    chk("⑪9 视频块里带时间码的行 ⇒ 位置按「视频 MM:SS」",
        bool(_vid_it) and re.match(r"^视频 \d{2}:\d{2}$", _vid_it[0]["position"]),
        "%r" % (_vid_it[0]["position"] if _vid_it else "—"))
    _bare = "这款吸奶器 100% 值得买。"
    _bare_it = _item_fields(evaluate(_bare).get("findings") or [], _bare)
    chk("⑪10 反向对照：去掉块头 ⇒ 回落「正文第 N 段」（块解析不是恒真）",
        bool(_bare_it) and re.match(r"^正文第 \d+ 段$", _bare_it[0]["position"]),
        "%r" % (_bare_it[0]["position"] if _bare_it else "—"))

    # ⑦ 反向对照：喂一句干净文案必须**不命中**（否则上面那些绿都是空转）
    clean = evaluate("吸奶器静音设计，夜里不吵醒宝宝，续航 8 小时")
    chk("⑦ 反向对照：干净文案不命中 P0", clean.get("hit") is False)

    # ⑧ 反向对照：把逐条块拆掉，上面 ②③④ 必须会红（证明判据不是恒真）
    broken = r.replace("  **原因**：", "  X：").replace("请修改后重新提交。", "")
    ok2 = bool(re.match(r"^【审查结论：BLOCK】共发现 \d+ 处必须修改。$", broken.split("\n")[0], re.M))
    ok3 = "请修改后重新提交。" in broken
    ok4 = not [w.strip() for d in re.findall(r"^\d+\.【[^】]+】[^\n]*\n(?:  [^\n]*\n?)+", broken, re.M)
               for w in ("  **原因**：",) if w not in d]
    chk("⑧ 反向对照：拆掉逐条后 ②/③/④ 会红", ok2 and (not ok3) and (not ok4),
        "首行还绿=%s 尾部还绿=%s 四要素还绿=%s" % (ok2, ok3, ok4))

    # ⑨ 条款号取号键：**唯一键优先、非唯一键不猜**（2026-10-10 · 接线缺陷修复的判据）
    #
    #    病根（改前逐字）：`_l4_clause(rule_code)` 按 `rule_code` 建索引，注释写
    #    「首个命中即采用（与 L4 内的排序一致）」—— 而 L4 里 `rule_code` **不唯一**：
    #    实测 15 个键一对多（H02 → W-1.18 / W-1.47，H04 → W-1.13 / W-1.41 …）。
    #    ⇒ 号取决于**文件排序**，没有判据守着。当前 11 条恰好取对（11/11），
    #      所以修的是"靠巧合"本身 —— **错号比空号更坏**：空号人会去补，错号人不会回头看。
    #    这四条判据拆掉任一条，对应的错法就重新变得"看不见"。
    import json as _json
    with open(os.path.join(KB, "l5/p0_patterns.jsonl"), encoding="utf-8") as _fh:
        _rows = [_json.loads(x) for x in _fh if x.strip()]
    _l4_load()
    _rid2no = {rid: rec["article_no"] for rid, rec in (_L4_INDEX or {}).items()}
    _amb = {rc: sorted({x["article_no"] for x in v})
            for rc, v in (_L4_BY_RC or {}).items()
            if len({x["article_no"] for x in v}) > 1}

    chk("⑩a 判据前提：L4 里确实存在一对多的 rule_code（否则 ⑩c 是空转）",
        bool(_amb), "实测 %d 个键一对多，例：%s" % (len(_amb), list(_amb.items())[:2]))

    _fs = res.get("findings") or []
    chk("⑩b 每条命中的号都走 rule_id（唯一键）取到",
        bool(_fs) and all((f.get("clause") or {}).get("via") == "rule_id" for f in _fs),
        "via=%s" % [(f.get("clause") or {}).get("via") for f in _fs][:5])

    # ⑩c 一对多的 rule_code **单查** ⇒ 必须拒绝给号（改前在这里"取首个"）
    _arc = sorted(_amb)[0] if _amb else None
    _guessed = _l4_clause(rule_code=_arc) if _arc else None
    chk("⑩c 一对多的 rule_code 单查 ⇒ None（不猜）", _guessed is None,
        "rule_code=%s ⇒ %s" % (_arc, _guessed))

    # ⑩c2 反向对照：补上 rule_id 就**必须取得到**（证明 ⑨c 不是"函数恒返回 None"）
    _want_no = _amb[_arc][0] if _arc else None
    _rid = next((r for r, no in _rid2no.items() if no == _want_no), None)
    _got = _l4_clause(rule_id=_rid, rule_code=_arc) if _rid else None
    chk("⑩c2 反向对照：给 rule_id 取得到号（⑩c 不是恒真）",
        bool(_got) and _got.get("article_no") == _want_no,
        "rule_id=%s ⇒ %s" % (_rid, (_got or {}).get("article_no")))

    # ⑨d 模式表顶层带条款号（目标 18「P0 红线法务逐条确认」要用它签字）
    _withno = sum(1 for p in _rows if str(p.get("article_no") or "").strip())
    # ★ 2026-10-13 改：原判据是 `len(_rows) == 11` —— **条数写死**。
    #   为什么必须改：PRD §7.3 的 6 条一票否决红线于 2026-10-13 入选（V01–V06，
    #   条款号 E-1.3419），模式表 11 → **17** 条。写死的等式会把**正确的扩容**判成故障
    #   （实测：内容判据 17/17 全过，只有这个等式红），逼着后人为加规则去改尺子。
    #   改成**下限 + 内容**：① 条数不得少于已交付的基线 11（**表只许长、不许缩** ——
    #   缩了说明规则被误删）；② 每条都必须带 `article_no`（法院签字要用它）。
    #   ★ 与 L5 闸门的 `C_p0_count_recomputable`（`l5_gate.py::_p0_recompute`）**分工不同**：
    #     那一把从 L3 反算「应该有几条」，这一把量「表本身有没有缺条款号」——**不重复造闸门**。
    #   反向对照：抽掉任意一行的 `article_no` ⇒ 本条**精确变红**（`_withno` 少 1）。
    _P0_BASELINE_N = 11
    chk("⑩d P0 模式表 %d 条全带 article_no（下限 %d）" % (len(_rows), _P0_BASELINE_N),
        len(_rows) >= _P0_BASELINE_N and _withno == len(_rows),
        "实测 %d/%d，条数下限 %d" % (_withno, len(_rows), _P0_BASELINE_N))

    print("\n自证：通过 %d / 失败 %d" % (len(P), len(F)))
    for x in F:
        print("  · 失败：%s" % x)
    return 1 if F else 0


def main():
    ap = argparse.ArgumentParser(description="P0 红线快路（PRD §6.3 第一层）")
    ap.add_argument("--text")
    ap.add_argument("--file")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--selftest", action="store_true",
                    help="只跑判据自证（离线）：PRD §5.3.3 逐条块 + 反向对照")
    ap.add_argument("--report-out", metavar="PATH",
                    help="命中时把**完整报告**（全量逐条 + 修改建议 + 四段溯源）写到该路径。"
                         "PRD §12 把「P0 响应 ≤1s」与「报告生成 ≤30s」定成两条独立指标 ⇒ "
                         "本开关**专供回执之后的异步补报告**，不要在出回执那条命令上加它。")
    ap.add_argument("--report-ref", metavar="URL_OR_PATH", default="",
                    help="把报告链接**填进回执**（重渲染用）。报告还没生成时**不要填** —— "
                         "这一格宁可为空，也不许编一个链接。")
    a = ap.parse_args()

    if a.selftest:
        print("P0 快路 · 判据自证（离线；样本取自 2026-10-06 的真实送审）")
        return selftest()

    if a.file:
        text = open(a.file, encoding="utf-8").read()
    elif a.text is not None:
        text = a.text
    else:
        text = sys.stdin.read()

    res = evaluate(text, report_ref=a.report_ref)
    if a.report_out and res.get("hit"):
        _write_report(a.report_out, _report_md(
            text, res.get("findings") or [],
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        res["report_path"] = a.report_out
    if a.json:
        print(json.dumps(res, ensure_ascii=False, indent=1))
    else:
        if res["hit"]:
            print(res["rendered"])
            print()
            print("（快路耗时 %.1f ms ｜ mode=%s%s）" % (
                res["elapsed_ms"], res["mode"],
                " ｜ 报告已写：%s" % res["report_path"] if res.get("report_path") else ""))
        else:
            print("P0 快路：**未命中**（耗时 %.1f ms）⇒ %s"
                  % (res["elapsed_ms"], res["next"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
