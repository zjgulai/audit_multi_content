#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""l3_clause_actionable.py —— 「外部标准 clause 单元能不能蒸成规则」的**唯一判定实现**。

## 为什么有它（2026-10-10 · Owner 批准「目标 5 的 ⑧」时查出来的）

`kb/l8/l3_distill_run.py` 的「外部标准库」整段原本是一段**空壳**：

```python
for u in cl:
    rejected.append({... "reason": "条款文本不可判定：非自然语言条款（页面脚本 / base64 编码载荷），"
                                    "无法给出判定条件与阈值"})
```

**那段里没有任何检测** —— 没有 CJK 占比、没有 base64 特征、没有脚本标签判断。
凡是 `kb_type == "external_standard"` 的 `clause` 单元**一律**拿到这条理由。
⇒ 它是**占位符，却读起来像诊断**。

**后果（2026-10-10 实测）**：

| 量 | 实测 |
|---|---|
| L2 里 `external_standard` 单元 | **clause 4636 ＋ entry 375**，涉 **88 个资源** |
| L3 `rules.jsonl` 1018 行的 `kb_type` | **全部是 `wording`** ⇒ **外部标准库从未产出过一条规则** |
| 被那条假理由拒的 | `clause_not_actionable` **2709 条 / 41 个资源** |
| `entry` 那 375 个单元 | 代码只取 `grp.get("clause")` ⇒ **完全没被处理**（既不成规则，也不进台账） |

连《核定版工单》都被它骗了 —— 原话把「2709 条是『非自然语言条款（页面脚本 / base64 载荷）』」
当成实测结论去解释 ⑥ 蒸不出来的原因。**那是占位符，不是结论。**

## 本模块只做两件事

1. `classify_clause(unit)` —— **真检测**后给出 `(kind, reason)`，理由必须与实测一致；
2. `to_scoped_candidate(unit, ...)` —— 判为可蒸的，产出 **`scoped_clause` 形态**的候选
   （L4 已有该形态 375 条、已占段位 **E-1** ⇒ **不必新开 form、不牵动 L4 发号分段**）。

★ **判据只做分类，不判"内容对不对"**；蒸不出来的**如实进拒绝台账，不许硬凑**。
★ 本模块**不写盘、不读库**（纯函数）—— 写盘由 `l3_distill_run.py` 负责，判定可离线自证。

## 用法

    python3 kb/l8/l3_clause_actionable.py --selftest    # 判据自证（含反向对照）
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
import unicodedata

KB_VERSION = "v0"

# ── 判据阈值（写在这里，**不许散到别处**）───────────────────────────────────
MIN_CHARS = 24            # 低于此长度且无句子结构 ⇒ 视为登记型元数据
CJK_MIN_RATIO = 0.25      # 自然语言中文条款的 CJK 占比下限（实测样本远高于此）
PAYLOAD_MIN_CHARS = 40    # 载荷特征只在够长的串上判（防误伤）

_RE_SCRIPT = re.compile(r"<\s*(script|style|div|span|table|html)\b|function\s*\(|=>\s*\{|\{\s*\"", re.I)
_RE_B64 = re.compile(r"^[A-Za-z0-9+/=]{40,}$")
_RE_WS = re.compile(r"[\u200b-\u200f\u2060\ufeff]")     # 零宽字符（飞书链接文本里常见）
_RE_DROP_BLOCK = re.compile(r"<\s*(script|style)\b.*?<\s*/\s*\1\s*>", re.I | re.S)
_RE_TAG = re.compile(r"<[^>]{0,400}>")
_RE_ENT = re.compile(r"&(nbsp|amp|lt|gt|quot|#\d+|#x[0-9a-f]+);", re.I)
_ENT = {"nbsp": " ", "amp": "&", "lt": "<", "gt": ">", "quot": '"'}
_WORD = re.compile(r"[A-Za-z][A-Za-z'\-]{1,}")


def clean_text(s) -> str:
    """**把 HTML 外壳剥成正文**（不去就不算"取到真资料"）。

    ★★ 为什么必须有它（2026-10-10 实测）：下钻的外部站是用 `curl` 直接抓的
    **原始 HTML**，`<div>` / `<script>` 满地都是 ⇒ 判据把它整段当成「编码载荷」拒掉，
    而落库的 `clause_text` 也会是**带标签的 HTML**。两侧都得洗。
    """
    t = _RE_DROP_BLOCK.sub(" ", str(s if s is not None else ""))
    t = _RE_TAG.sub(" ", t)
    t = _RE_ENT.sub(lambda m: _ENT.get(m.group(1).lower(), " "), t)
    return re.sub(r"\s+", " ", t).strip()


def _is_natural_language(t: str) -> bool:
    """自然语言判据 —— **中文与拉丁字母各一条路**。

    ★★ 2026-10-10 修：原先只认「CJK 占比 ≥ 0.25」⇒ **英文条款全被判成"不是自然语言中文"**。
    而 PRD §7.1 的外部标准库**明写包含「美国法规、平台政策」** —— 那些**就是英文**。
    只看中文等于把整个英文语料挡在门外。
    拉丁一路的判据取「字母占比 + 词数 + 平均词长」三条，**故意不用"有没有句号"**
    （HTML 洗过之后句读常丢），也**不会**把 base64 串当词（base64 无空格 ⇒ 词数上不去）。
    """
    body = [c for c in t if not c.isspace()]
    if not body:
        return False
    cjk = sum(1 for c in body if "\u4e00" <= c <= "\u9fff")
    if cjk / len(body) >= CJK_MIN_RATIO:
        return True
    words = _WORD.findall(t)
    if len(words) < 8:
        return False
    letters = sum(len(w) for w in words)
    if letters / len(body) < 0.5:
        return False
    avg = letters / len(words)
    return 2.0 <= avg <= 12.0


def _norm(s) -> str:
    s = unicodedata.normalize("NFKC", str(s if s is not None else ""))
    return _RE_WS.sub("", s).strip()


def cjk_ratio(s: str) -> float:
    """中日韩表意字符占比（分母 = 非空白字符数）。"""
    body = [c for c in s if not c.isspace()]
    if not body:
        return 0.0
    cjk = sum(1 for c in body if "\u4e00" <= c <= "\u9fff")
    return cjk / len(body)


def looks_like_payload(s: str) -> bool:
    """**真检测**：脚本 / 编码载荷。"""
    if len(s) < PAYLOAD_MIN_CHARS:
        return False
    if _RE_SCRIPT.search(s):
        return True
    for tok in re.split(r"\s+", s):
        if len(tok) >= 40 and _RE_B64.match(tok):
            return True
    return False


def looks_like_metadata(s: str) -> bool:
    """登记型元数据：短、无断言结构（人名 / 标签 / 地区那种）。

    ★ 判据是**结构**不是长度之一 —— 短但有断言（"不可趴睡"）仍算条款。
    """
    if len(s) > MIN_CHARS:
        return False
    # 有禁止/必须类断言词 ⇒ 不是元数据
    if re.search(r"不可|不得|禁止|必须|应|需|避免|不得出现|注意", s):
        return False
    return True


def classify_clause(unit: dict):
    """给一个 L2 `clause` 单元定性。返回 `(kind, verdict, reason)`。

    `verdict ∈ {"actionable", "not_actionable"}`；`kind` 就是拒绝台账的 `kind`。
    **理由必须与实测一致** —— 这是本模块存在的全部意义。
    """
    raw = _norm(unit.get("text") or unit.get("clause_text") or "")
    if not raw:
        return ("no_clause_text", "not_actionable",
                "clause 单元的 text 为空（L2 侧就没抽到正文）")
    # ★ 先剥 HTML 外壳再判 —— 判据与落库正文都用**洗过的**文本（见 clean_text 的说明）
    text = clean_text(raw)
    if not text:
        return ("no_clause_text", "not_actionable",
                "剥掉 HTML 外壳后正文为空（该单元只有标签/脚本，没有可读文本）")
    ratio = cjk_ratio(text)
    if looks_like_payload(text):
        return ("clause_not_actionable", "not_actionable",
                "条款文本不可判定：**实测**洗净后仍含脚本 / 编码载荷特征"
                "（正则命中 <script|style…> 或 ≥40 位 base64 串）")
    if not _is_natural_language(text):
        return ("clause_not_actionable", "not_actionable",
                "条款文本不可判定：**实测**既非中文自然语言（CJK %.2f < %.2f）"
                "也非拉丁自然语言（字母词 <8 个或字母占比/平均词长越界）" % (ratio, CJK_MIN_RATIO))
    if looks_like_metadata(text):
        return ("clause_not_actionable", "not_actionable",
                "条款文本不可判定：**实测**为登记型元数据（%d 字、无禁止/必须类断言结构），"
                "不构成可判定条款" % len(text))

    lang = "中文" if ratio >= CJK_MIN_RATIO else "拉丁"
    return ("clause_actionable", "actionable",
            "可蒸：%s自然语言（CJK %.2f）、洗净后 %d 字 ⇒ 产出 scoped_clause 候选"
            % (lang, ratio, len(text)))


def clause_id_of(unit: dict) -> str:
    """候选 id —— 由 `resource_id + unit_id` 派生（确定性、可复算，不随行序变）。"""
    key = "%s|%s" % (unit.get("resource_id") or "", unit.get("unit_id") or "")
    return "scl-m-" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]


def to_scoped_candidate(unit: dict) -> dict:
    """把判为 `actionable` 的 clause 单元做成 `scoped_clause` 形态的候选。

    ★ 形态字段对齐 L4 canonical 的 `scoped_clause.jsonl`（少治理四字段 —— 那四个由 L4 补）。
    ★ **不许编**：`source_sha256` / `anchor` / `unit_id` 全部原样取自 L2 单元。
    """
    # ★ 落库正文必须是**洗净后的**（不许把 HTML 标签写进条款正文）
    text = clean_text(_norm(unit.get("text") or ""))
    return {
        "clause_id": clause_id_of(unit),
        "kb_type": "external_standard",
        "kb_version": KB_VERSION,
        "form": "scoped_clause",
        "variant": "natural_language_clause",
        "clause_text": text,
        "char_count": len(text),
        "evidence_strength": "**实测**：自然语言条款正文（L2 clause 单元，已剥 HTML 外壳）",
        "resource_id": unit.get("resource_id"),
        "unit_id": unit.get("unit_id"),
        "unit_ids": [unit.get("unit_id")] if unit.get("unit_id") else [],
        "anchor": unit.get("anchor"),
        "source_sha256": unit.get("source_sha256"),
        "observed_at": unit.get("observed_at") or "",
        "effective_period": "",
        "term_list": [],
        "threshold": None,
        "owner": "",
        "status": "provisional",
        "quality_flag": "derived_by=l8/l3_clause_actionable.py",
    }


# ══════════════════════════════════════════════════════════════════════
def selftest() -> int:
    """判据自证（离线，不读库、不写盘）。**每条判据都配反向对照。**"""
    P, F = [], []

    def chk(name, cond, extra=""):
        (P if cond else F).append(name)
        print("  %s %s%s" % ("✅" if cond else "❌", name, ("  " + extra) if extra else ""))

    # ① 真实样本（母婴设计常识清单 V2.0 的 clause 单元，2026-10-10 逐字取自 kb/l2/units.jsonl）
    REAL = {
        "unit_id": "d6800a3309f5d76dc6c6",
        "resource_id": "docx__Kts8dacyIo1zq1xElWOcqW1zncc",
        "anchor": "#正文/p2",
        "source_sha256": "x" * 64,
        "text": ("宝宝月龄与动作能力匹配（不会出现\"新生儿自己坐着\"等错误） 抱姿正确（小月龄托头颈，"
                 "单手竖抱≥6个月） 小月龄宝宝不可被举起/举过头顶 婴儿睡姿为仰卧，不可趴睡"
                 "（不到1岁绝对不可趴睡） 婴儿床内无玩偶/被子/枕头"),
    }
    k, v, why = classify_clause(REAL)
    chk("① 真实中文条款 ⇒ 判为可蒸（**不再被那条假理由吃掉**）",
        v == "actionable", "%s ｜ %s" % (k, why[:70]))
    chk("①b 产出的候选形态对（form=scoped_clause、id 可复算）",
        to_scoped_candidate(REAL)["form"] == "scoped_clause"
        and clause_id_of(REAL) == clause_id_of(dict(REAL)),
        clause_id_of(REAL))

    # ② **反向对照**：喂一条真的 base64 载荷 ⇒ 必须仍判非自然语言
    B64 = dict(REAL, text="QWxsIG1vdGhlcnMgbmVlZCBsb3ZlIGFuZCBjYXJlIHZlcnkgbXVjaCBpbmRlZWQ9PQ==")
    k2, v2, why2 = classify_clause(B64)
    chk("② 反向对照：真 base64 载荷 ⇒ 仍判「非自然语言」（新判据没把闸门关掉）",
        v2 == "not_actionable" and "编码载荷" in why2, why2[:70])

    # ②b 反向对照：纯脚本/标签、洗净后无正文 ⇒ **必须**判不可蒸。
    #   ★ 判据只钉**判决**（not_actionable）不钉理由文案 —— 洗净后剩下的残字可能落进
    #     「元数据」那一档，理由不同但结论一致；钉死文案会让判据随实现措辞变红（那是噪声）。
    SCR = dict(REAL, text="<div class=\"x\"><script>var a=1;function f(){return 2}</script></div>")
    chk("②b 反向对照：纯脚本/标签 ⇒ 判不可蒸",
        classify_clause(SCR)[1] == "not_actionable", classify_clause(SCR)[2][:60])

    # ⑦ ★★ 本批修复的**主判据**：英文条款必须可蒸 —— PRD §7.1 的外部标准库
    #    明写包含「美国法规、平台政策」，那些**就是英文**；旧判据只认 CJK ⇒ 整片英文语料被挡在门外。
    EN = dict(REAL, unit_id="en-1", text=(
        "<div class=\"body\"><p>Infants should always be placed on their back to sleep for every "
        "sleep time. Soft bedding, pillows and toys should never be placed in the crib with the baby. "
        "Bed sharing is not recommended because it increases the risk of suffocation.</p></div>"))
    k7, v7, why7 = classify_clause(EN)
    chk("⑦ 英文条款（夹在 HTML 里）⇒ **必须判可蒸**", v7 == "actionable", why7[:74])
    # ⑦b 反向对照：HTML 洗完后**正文必须不含标签**
    chk("⑦b 候选正文已剥 HTML（不含 `<` 标签）",
        "<div" not in to_scoped_candidate(EN)["clause_text"]
        and "Infants should always" in to_scoped_candidate(EN)["clause_text"])

    # ③ 元数据（⑥ 睡眠RAG 那种："郭嘉"）⇒ 判元数据，**且理由必须说"元数据"，不许说 base64**
    META = dict(REAL, text="郭嘉")
    k3, v3, why3 = classify_clause(META)
    chk("③ ⑥ 那种元数据 ⇒ 判不可蒸，且理由是「元数据」**不是**「base64」",
        v3 == "not_actionable" and "元数据" in why3 and "base64" not in why3, why3[:70])

    # ④ 短但有断言 ⇒ **不许**判成元数据（反向对照：防"短=元数据"这种懒判据）
    SHORT = dict(REAL, text="不可趴睡")
    chk("④ 反向对照：短但有断言（「不可趴睡」）⇒ 不许判成元数据",
        classify_clause(SHORT)[1] == "actionable", classify_clause(SHORT)[2][:60])

    # ⑤ 空文本 ⇒ 单独一档（与"不可判定"分开报）
    chk("⑤ 空文本 ⇒ kind=no_clause_text（不与「不可判定」混为一档）",
        classify_clause({"text": ""})[0] == "no_clause_text")

    # ⑥ **理由诚实性**：可蒸的理由里必须出现实测数字（CJK 占比 / 字数）
    _, _, why6 = classify_clause(REAL)
    chk("⑥ 可蒸的理由里带**实测数字**（不是空话）",
        bool(re.search(r"CJK \d\.\d\d", why6)) and "字" in why6, why6[:70])

    print("\n自证：通过 %d / 失败 %d" % (len(P), len(F)))
    for x in F:
        print("  · 失败：%s" % x)
    return 1 if F else 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        print("l3_clause_actionable · 判据自证（离线；真实样本取自 kb/l2/units.jsonl）")
        raise SystemExit(selftest())
    print(__doc__)
    raise SystemExit(0)
