#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""advice_book.py —— 「建议」这一格在**库内没有原话时**的兜底改法（**唯一来源**）。

## 它补的是哪个口子（Owner 2026-10-19 逐字）

    「守衡的回答中，去掉锚点，**必须给建议**」

改前实测（真单，素材「这款吸奶器绝对是最好用的」）：

    1.【绝对化与安全承诺-绝对化用语】全文，逐字命中 `最好`
      **原因**：按 PRD §7.3 判定（Owner 2026-10-13 同意入选）
      **依据**：《外部标准库 v0（试用版，未发布）》第 E-2.124 条（链接：…）
      **锚点**：#h.7. …｜source_sha256：6671c28…
      **建议**：（来源未给修改建议）
      L0 逐字（可点直链）：https://…

「建议」那一格印的是**占位符** —— 收卡的人看完仍然不知道该改什么。
根因不是渲染层偷懒，而是**取值口只有两个**（`p0_fastpath._suggestion_for`）：
① L3 规则的 `fix_pairs`（按命中片段挑）；② P0 模式表的 `suggested_replacement`。
实测（2026-10-19 现读 `kb/l5/p0_patterns.jsonl` 17 条 P0 模式）：

| 有 `suggested_replacement` | 7 条（H02/H04/H05/H07/H09/M03/U04） |
| **空**（⇒ 落到占位符） | **10 条**（H01/H03/H06/H08/V01–V06） |

⇒ 10/17 的 P0 命中在卡上**永远没有建议**。本文件把这一格补上。

## 三条纪律（每条都对应一次踩过的坑）

1. **不编**：表里的改法**逐条能指回它的出处**（`basis` 字段）——
   H 系取自同码 L0 记录的「边界内容/触发原因/豁免词」，V 系取自 PRD §7.3 的
   一票否决项原文与 §5.3.4 的 BLOCK 模板（模板里就写着「建议：改为…」）。
   **不是**我按常识补的句子。
2. **优先级不动**：库内原话（`fix_pairs` / `suggested_replacement`）**永远先于**本表。
   本表只是「库内没说」时的那一句 —— 一旦某码补齐了原话，那一句自动让位（`selftest` ④ 会提示）。
3. **长度与措辞照 PRD §5.3.3**：修改建议 **≤30 字**、客观指令式（禁「可能 / 建议可以考虑」）。
   `selftest` ② 逐条量长度，超一个字就红。

## 谁在用

- `kb/l5/p0_fastpath.py`（P0 快路回执 ＋ 报告）—— 按 `rule_code` 取。
- `kb/l7/review-engine/core/review_engine.py`（评审链回执）—— 按 `rule_id` 取（唯一键）。

两处都**不再出现**「（来源未给修改建议）」。

## 用法

    python3 kb/l5/advice_book.py --selftest     # 自证（离线，不联网）
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
KB = os.path.dirname(HERE)
PATTERNS = os.path.join(KB, "l5", "p0_patterns.jsonl")

#: PRD §5.3.3「修改建议 ≤30 字」—— 本表每一条都受这一条约束（`selftest` ② 量）。
MAX_CHARS = 30

# ── ★★ 2026-10-20（Owner：「修改建议的 30 字，标点不算字数」）────────────────────
#   改前本文件按 `len(text)` **逐字符**量（连标点、连空格一起算）—— 文件里那句注释写的正是
#   「是逐字符量的」。Owner 现在明确：**标点不计入 30**，所以一句 18 字符、11 实词的建议
#   只能算 11 字。口径本来就在登记件 `kb/l7/registry/prd533-constraints.yaml` 的
#   `counting.advice_no_punct`（2026-10-19 定的），本文件是**漏接的那一处**，不是新口径。
#   ⚠️ 标点类**唯一真源**是登记件；这里不另写一份，运行时从它的 Python 读方
#      `kb/l8/prd533_check.py` 取。取不到就退回下面的最小类，并在 stderr 说一声（不静默）。
_ADVICE_PUNCT_FALLBACK = "，。、；：！？…—～·「」『』（）【】《》〈〉“”‘’,.!?;:()[]{}<>"


def _punct_re():
    """取标点正则（优先登记件的实现；取不到就用本地最小类，**不静默**）。"""
    try:
        spec = importlib.util.spec_from_file_location(
            "kb_prd533_check", os.path.join(KB, "l8", "prd533_check.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        if hasattr(mod, "ADVICE_PUNCT_RE"):
            return mod.ADVICE_PUNCT_RE
    except Exception as e:                                          # noqa: BLE001
        print("[advice_book] ⚠ 未取到 prd533 的标点类，退回最小类：%s" % e, file=sys.stderr)
    import re as _re
    return _re.compile("[%s]" % _re.escape(_ADVICE_PUNCT_FALLBACK))


def advice_chars(text):
    """修改建议的有效字数：**标点不计入**（去空白、去标点后数）。"""
    import re as _re
    t = _re.sub(r"\s+", "", str(text or ""))
    return len(_punct_re().sub("", t))

#: 兜底改法。**键 = P0 规则码**；`basis` = 这条改法的出处（人可回源，不是装饰）。
ADVICE = {
    "H01": {
        "text": "改为「缓解涨奶」「降低堵奶风险」等边界内表述。",
        "basis": ("L0 #广告文案风控库__品线内容边界规则库/recvuJP1dDHb7E/边界内容"
                  "（原文：「边界允许：缓解涨奶 ease/relieve engorgement、"
                  "降低堵奶风险 reduce the risk of clogged、支持奶阵 let-down」）"),
    },
    "H03": {
        "text": "删去临床/科学背书表述，或补可出示的备案报告。",
        "basis": ("L0 #…/recvuJP1dD4jGX/边界内容（原文：「未经备案的临床/科学背书」）"
                  "—— 边界是「备案」，不是「删」本身"),
    },
    "H06": {
        # ⚠️ 28 字（含英文词与空格）—— PRD §5.3.3「修改建议 ≤30 字」是**逐字符**量的，
        #    英文词比中文占得多，所以这一条只能写最常见的那一种改法；
        #    `registered` 那一种写在 `basis` 里（源头是同一格的豁免词，不丢）。
        "text": "FDA approved 改为 FDA cleared。",
        "basis": ("L0 #…/recvuJP1LVW6E0/触发原因（原文：「吸奶器为 cleared/registered，"
                  "非 approved/certified」）＋ 同记录豁免词「FDA cleared / FDA registered」"),
    },
    "H08": {
        "text": "删去与竞品的比较，只写本产品自身参数。",
        "basis": "L0 #…/recvuJP1LVUEBx/边界内容（原文：「无数据支撑的违法对比 / 贬低竞品」）",
    },
    "V01": {
        "text": "改为正确使用安全座椅（反向安装、系安全带）的画面。",
        "basis": "PRD §7.3-1（车内未使用安全座椅 / 反向安装错误 / 成人未系安全带 / 装副驾 / 独留车内）",
    },
    "V02": {
        "text": "删去最高级表述，改为可核验的具体描述。",
        "basis": ("PRD §7.3-3（绝对化用语：最、第一、最佳、100%、纯天然等）"
                  "＋ PRD §5.3.4 BLOCK 模板「建议：改为『经过安全测试』」"),
    },
    "V03": {
        "text": "删去销量/排名宣称，或补可核验的来源与口径。",
        "basis": "PRD §7.3-4（无依据的销量/排名宣称）",
    },
    "V04": {
        "text": "删去该危险动作，改为符合安全规范的正确示范。",
        "basis": "PRD §7.3-5（危险行为示范：无人看护下水、趴睡、怀抱乘车等）",
    },
    "V05": {
        "text": "删除该儿童镜头，或补监护人书面授权后再用。",
        "basis": "PRD §7.3-6（未成年人未经授权出镜 / 隐私暴露）",
    },
    "V06": {
        "text": "给 AI 生成内容加「AI 生成」标识后再发布。",
        "basis": "PRD §7.3-7（AI 深度合成内容未标识）",
    },
}

#: 通用兜底（**表里没有的码**也必须有建议）。`{hit}` 会被命中的词/片段替换。
GENERIC_WITH_HIT = "删去「{hit}」，不要用近义词替换。"
GENERIC_NO_HIT = "删去命中的违规表述后再提交。"


def _rows():
    """P0 模式表（只读）。读不到返回 `[]` —— 不编。"""
    try:
        with open(PATTERNS, encoding="utf-8") as fh:
            return [json.loads(x) for x in fh if x.strip()]
    except OSError:
        return []


def code_of(rule_code=None, rule_id=None):
    """把 `rule_code` / `rule_id` 归一成模式表里的**规则码**（取不到就给原样）。

    ★ 为什么两把键都要认：P0 快路手上是 `rule_code`，而评审链的 `risk_item`
      只有 `risk_id`（= `rule_id`，见 `review.py::_finding_to_risk_item`）——
      只认一个键，另一边就永远取不到本表（"接了一半"，本库栽过多次）。
    """
    rc = str(rule_code or "").strip().upper()
    if rc:
        return rc
    rid = str(rule_id or "").strip()
    if rid:
        for r in _rows():
            if str(r.get("rule_id") or "") == rid:
                return str(r.get("rule_code") or "").strip().upper() or None
    return None


def fallback(rule_code=None, rule_id=None, hits=()):
    """**这一条**的兜底改法。

    @returns `(text, source)` —— `source` 是机读来源标记，写进产物用：
             `p0_advice_book:<CODE>` ｜ `generic_from_hit` ｜ `generic_no_hit`。
    """
    code = code_of(rule_code, rule_id)
    e = ADVICE.get(code) if code else None
    if e:
        return e["text"], "p0_advice_book:%s" % code
    hit = ""
    for h in (hits or ()):
        s = str(h or "").strip()
        if s:
            hit = s
            break
    if hit:
        # 命中片段可能是一整段正则或一句话 —— 只取前 12 字，别把建议撑爆（PRD ≤30 字）。
        return GENERIC_WITH_HIT.format(hit=hit[:12]), "generic_from_hit"
    return GENERIC_NO_HIT, "generic_no_hit"


def selftest():
    """判据自证（离线）。**每条都带反向对照** —— 否则它就是注释。"""
    global ADVICE          # noqa: PLW0603 —— ⑦ 的两条反向对照要临时改表，跑完在 finally 里还原
    P, F = [], []

    def chk(name, cond, extra=""):
        (P if cond else F).append(name)
        print("  %s %s%s" % ("✅" if cond else "❌", name, ("  " + extra) if extra else ""))

    rows = _rows()
    codes = {str(r.get("rule_code") or "").strip().upper() for r in rows}
    rid_of = {str(r.get("rule_code") or "").strip().upper(): str(r.get("rule_id") or "")
              for r in rows}

    chk("① 读到 P0 模式表（否则下面几条是空转）", bool(rows), "%d 条" % len(rows))
    chk("①2 表里的码都在模式表里（没有拼错的码）",
        bool(codes) and set(ADVICE) <= codes,
        "多出来的：%s" % sorted(set(ADVICE) - codes))

    too_long = [(c, advice_chars(e["text"])) for c, e in ADVICE.items()
                if advice_chars(e["text"]) > MAX_CHARS]
    # ★★ 2026-10-20：量的是**实词字数**（标点不计入）—— 见 `advice_chars()`。
    chk("② 每条建议 ≤%d 字（PRD §5.3.3；**标点不计入**）" % MAX_CHARS, not too_long, str(too_long))

    placeholders = [(c, e["text"]) for c, e in ADVICE.items()
                    if ("来源未给" in e["text"] or not e["text"].strip())]
    chk("③ 每条都不是占位符（「来源未给…」/空串）", not placeholders, str(placeholders))

    no_basis = [c for c, e in ADVICE.items() if not str(e.get("basis") or "").strip()]
    chk("③2 每条都写了出处（basis 不许空 —— 不许编）", not no_basis, str(no_basis))

    vague = [c for c, e in ADVICE.items() if ("可能" in e["text"] or "可以考虑" in e["text"])]
    chk("③3 措辞不许「可能 / 可以考虑」（PRD §5.3.3）", not vague, str(vague))

    # ④ 库内原话优先时的提示（**只提示、不判红**）：某码后来补了原话，本表就该让位。
    filled = [c for c in ADVICE
              if any(str(r.get("rule_code") or "").strip().upper() == c
                     and str(r.get("suggested_replacement") or "").strip() for r in rows)]
    chk("④ 覆盖的码仍是「库内没有原话」的那批（有原话应由原话优先）",
        not filled, "这些码已有原话、本表会自动让位：%s" % filled)

    # ⑤ 两条取键路径都通（rule_code / rule_id），且落点一致。
    sample = "V02" if "V02" in ADVICE else sorted(ADVICE)[0]
    t_code, s_code = fallback(rule_code=sample)
    t_id, s_id = fallback(rule_id=rid_of.get(sample))
    chk("⑤ rule_code 与 rule_id 取到同一条改法",
        bool(t_code) and t_code == t_id and s_code == s_id == "p0_advice_book:%s" % sample,
        "%r / %r ← %r / %r" % (t_code[:12], s_code, t_id[:12], s_id))

    # ⑥ 表外的码也**必须有建议**（这是本文件的底线：绝不留占位符）。
    t_ext, s_ext = fallback(rule_code="ZZ99", hits=["某某表述"])
    chk("⑥ 表外的码 ⇒ 通用改法（非空、带命中项）",
        bool(t_ext.strip()) and "某某表述" in t_ext and s_ext == "generic_from_hit", repr(t_ext[:40]))
    t_nohit, s_nohit = fallback(rule_code=None)
    chk("⑥2 连码和命中都没有 ⇒ 仍给一句可执行的（不空白）",
        bool(t_nohit.strip()) and s_nohit == "generic_no_hit", repr(t_nohit))
    chk("⑥3 通用改法也 ≤%d 字（标点不计入）" % MAX_CHARS,
        advice_chars(t_ext) <= MAX_CHARS and advice_chars(t_nohit) <= MAX_CHARS,
        "%d / %d" % (advice_chars(t_ext), advice_chars(t_nohit)))

    # ⑦ 反向对照：把某条改空 / 改成占位符 ⇒ ②③ **精确变红**（证明判据不是恒真）。
    _bak = dict(ADVICE)
    try:
        ADVICE["V02"] = {"text": "", "basis": "（自证用）"}
        _bad = [c for c, e in ADVICE.items() if not e["text"].strip()]
        chk("⑦ 反向对照：把一条改成空串 ⇒ ③ 会红", bool(_bad), str(_bad))
        ADVICE["V02"] = {"text": "（来源未给修改建议）", "basis": "（自证用）"}
        _ph = [c for c, e in ADVICE.items() if "来源未给" in e["text"]]
        chk("⑦2 反向对照：写回占位符 ⇒ ③ 会红", bool(_ph), str(_ph))
        ADVICE["V02"] = {"text": "改" + ("字" * MAX_CHARS), "basis": "（自证用）"}
        _long = [c for c, e in ADVICE.items() if advice_chars(e["text"]) > MAX_CHARS]
        chk("⑦3 反向对照：超一个字 ⇒ ② 会红", bool(_long), "%s" % _long)
        # ⑦4 **口径对照**（2026-10-20 加）：30 个实词 ＋ 一串标点 ⇒ 仍然过（标点不计入）；
        #   再往上加**实词**才红。这一条钉的就是「标点不算字数」本身 ——
        #   若谁把 `advice_chars` 改回 `len()`，⑦4 会先红，而不是等人来投诉。
        ADVICE["V02"] = {"text": ("改" * MAX_CHARS) + "，。！？；：、", "basis": "（自证用）"}
        _punct_ok = advice_chars(ADVICE["V02"]["text"]) == MAX_CHARS
        ADVICE["V02"] = {"text": ("改" * (MAX_CHARS + 1)) + "，。！？；：、", "basis": "（自证用）"}
        _real_over = [c for c, e in ADVICE.items() if advice_chars(e["text"]) > MAX_CHARS]
        chk("⑦4 口径对照：30 实词＋标点 ⇒ 不红；31 实词 ⇒ 红（标点不计入）",
            _punct_ok and bool(_real_over), "%r / %s" % (_punct_ok, _real_over))
    finally:
        ADVICE.clear()
        ADVICE.update(_bak)

    print("\n自证：通过 %d / 失败 %d" % (len(P), len(F)))
    for x in F:
        print("  · 失败：%s" % x)
    return 1 if F else 0


def main():
    ap = argparse.ArgumentParser(description="「建议」兜底改法（唯一来源）")
    ap.add_argument("--selftest", action="store_true", help="只跑判据自证（离线）")
    ap.add_argument("--code", help="查某一码的兜底改法")
    ap.add_argument("--rule-id", help="按 rule_id 查（评审链只有这个键）")
    ap.add_argument("--hit", help="命中片段（通用兜底会嵌进建议里）")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    txt, src = fallback(rule_code=a.code, rule_id=a.rule_id, hits=[a.hit] if a.hit else ())
    print(json.dumps({"advice": txt, "source": src}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
