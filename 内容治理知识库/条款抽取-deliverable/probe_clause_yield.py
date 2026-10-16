#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""probe_clause_yield.py —— 条款语料**只读探针**：先量，再决定要不要改蒸馏器。

为什么先探针：`kb/l8/l3_distill_run.py` 的 `for u in cl:` 无条件拒绝全部 clause 单元
（2026-09-30 取证单第三节）。改它之前必须先量清楚三件事，否则改完也说不清改对了没有：

  1. 库里到底有多少 clause 单元进了蒸馏的输入集（kept）；
  2. 按「判定条件 + 处理方式 + 证据三件套」的口径，**能蒸出候选**的有多少；
  3. 蒸不出来的那些，**逐单元的具体理由**是什么（不是一句通用话覆盖）。

本脚本**全程只读**：只读 kb/l2/units.jsonl 与 kb/l0/registry/kb.json，
产物只写到本目录（stdout + --json 指定的文件），不碰 kb/ 下任何文件。

用法：
    python3 probe_clause_yield.py                 # 人读报告
    python3 probe_clause_yield.py --json out.json # 机读明细
"""
import json, os, re, sys, html, unicodedata, collections, hashlib

HERE = os.path.dirname(os.path.abspath(__file__))
KB = os.path.join(HERE, "..", "kb")
UNITS = os.path.join(KB, "l2", "units.jsonl")

# ---------------------------------------------------------------- 文本归一化
TAG = re.compile(r"</?[a-zA-Z][^>]{0,200}>")
SCRIPT_BLOCK = re.compile(r"<(script|style)\b[^>]*>.*?</\1>", re.I | re.S)
JS_NOISE = re.compile(
    r"(function\s*\(|var\s+\w+\s*=|window\.|document\.|\}\)\s*\)|;\s*\}?\s*$|"
    r"ue_csm|jserr|\$\s*\(|\.push\(|typeof\s|===|!=|&&|\|\|)", re.I)
HEXLIKE = re.compile(r"^(?:[0-9a-f]{16,}|[A-Za-z0-9+/=]{120,})$")


def norm_text(s: str) -> str:
    """剥标签/脚本 + 收空白。不改语义字符（与 L1 的逐字口径保持一致）。"""
    t = html.unescape(s or "")
    t = SCRIPT_BLOCK.sub(" ", t)
    t = re.sub(r"<br\s*/?>", "\n", t)
    t = re.sub(r"</(p|li|div|tr|h[1-6]|span|td)>", "\n", t)
    t = TAG.sub(" ", t)
    t = t.replace("\u00a0", " ").replace("\u200b", "")
    t = unicodedata.normalize("NFKC", t)
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n{2,}", "\n", t)
    return t.strip()


# ---------------------------------------------------------------- 判定用正则
MODAL = re.compile(
    r"\b(must(?:\s+not)?|shall(?:\s+not)?|may\s+not|should(?:\s+not)?|"
    r"prohibited|prohibits?|is\s+required|are\s+required|required\s+to|"
    r"cannot|can\s+not|is\s+unlawful|it\s+is\s+illegal)\b", re.I)
MODAL_ZH = re.compile(r"(不得|禁止|应当|必须|严禁|须)")
ACTION = re.compile(
    r"\b(substantiat\w+|disclos\w+|discourag\w+|prohibit\w*|correct\w*|discontinu\w+|"
    r"refrain|avoid|review|document|maintain|keep|provide|include|state|indicate|"
    r"monitor|qualif\w+|warn\w*|notif\w+|obtain|verify|ensure|comply|remov\w+|cease)\b", re.I)
COND = re.compile(
    r"\b(if|when|where|unless|in\s+the\s+case|in\s+order\s+to|so\s+that|before|after|"
    r"without|whether|fails?\s+to|implies?|implied|in\s+light\s+of|with\s+respect\s+to|"
    r"based\s+on|depending\s+on)\b", re.I)
THRESH = re.compile(
    r"(competent\s+and\s+reliable\s+scientific\s+evidence|reasonable\s+basis|"
    r"randomi[sz]ed|clinical\s+(?:trial|study|test)|well[- ]controlled|"
    r"statistically\s+significant|clear\s+and\s+conspicuous|material|"
    r"substantiat\w+|preponderance|Class\s+[IVX]+|510\(k\)|"
    r"[\"“][^\"”]{2,60}[\"”]|\d+\s*(?:%|percent|days?|hours?|mg|mcg|IU)\b)", re.I)
FOOTNOTE = re.compile(r"^\s*(?:\[\d+\]|\(\d+\)|\d+\.)\s")
QUOTE_ONLY = re.compile(r"^\s*[\"“]")
CHROME = re.compile(
    r"(all rights reserved|privacy policy|terms of service|cookie|skip to main content|"
    r"official website of the united states|here.?s how you know|show/hide|"
    r"try searching again|how can i help|please try again|sign in|log in)", re.I)
SENT_SPLIT = re.compile(r"(?<=[.!?;。；])\s+")


def alpha_ratio(t: str) -> float:
    if not t:
        return 0.0
    letters = sum(1 for c in t if c.isalpha() or c.isspace() or c in ".,;:()[]\"'%-/’“”")
    return letters / len(t)


def judge(text: str) -> dict:
    """对一个 clause 单元的**逐单元判定**：产出判定条件 + 阈值/词表 + 处理方式，或给出具体拒绝理由。

    返回 {"verdict": "rule"|"reject", "reason": <kind>, "detail": <逐单元理由>, ...}
    """
    t = norm_text(text)
    n = len(t)
    if n < 25:
        return {"verdict": "reject", "reason": "clause_too_short",
                "detail": "条款正文不足 25 字（切分碎屑 / 标题序号 / 空段）"}
    if HEXLIKE.match(t.replace("\n", "")):
        return {"verdict": "reject", "reason": "clause_encoded_payload",
                "detail": "整段是编码载荷（hex / base64），非自然语言条款"}
    h = t[:1200]
    m = MODAL.search(h) or MODAL_ZH.search(h)
    if not m:
        return {"verdict": "reject", "reason": "clause_no_modal",
                "detail": "1200 字内无义务/禁止模态（must/shall/may not/不得/应当），"
                          "不构成「命中 → 处理」形态"}
    if CHROME.search(t[:200]) and n < 120:
        return {"verdict": "reject", "reason": "clause_page_chrome",
                "detail": "页面样板/导航文案，非政策条款本体"}
    if alpha_ratio(t) < 0.80:
        return {"verdict": "reject", "reason": "clause_code_noise",
                "detail": "控制字符/符号占比过高（L1 抽正文时把页面脚本一并抽入），非可判定条款"}
    if JS_NOISE.search(t):
        return {"verdict": "reject", "reason": "clause_code_noise",
                "detail": "含脚本特征（function/var/window/=== 等），非可判定条款"}
    # 定位承载义务的那一句
    sents = [s for s in SENT_SPLIT.split(t) if s.strip()]
    key = next((s.strip() for s in sents if (MODAL.search(s) or MODAL_ZH.search(s))), t[:400])
    if FOOTNOTE.match(key) and len(key) < 200:
        return {"verdict": "reject", "reason": "clause_footnote_only",
                "detail": "命中模态的是脚注/引注行，不是条款正文"}
    if len(key) < 25:
        return {"verdict": "reject", "reason": "clause_key_sentence_too_short",
                "detail": "承载模态的句子不足 25 字，取不到完整判定条件"}
    act = sorted({x.lower() for x in ACTION.findall(key)}) or \
          sorted({x.lower() for x in ACTION.findall(t[:600])})
    if not act:
        return {"verdict": "reject", "reason": "clause_no_action",
                "detail": "有义务模态但取不到处理方式（substantiate/disclose/prohibit…）"}
    cond = key if COND.search(key) else ""
    thr = sorted({x.strip() for x in THRESH.findall(key)})
    if not cond and not thr:
        # 既不显式给条件、也没有阈值/词表 —— 记 scope 型（义务面），仍可判定
        pass
    return {"verdict": "rule", "reason": "", "detail": "",
            "condition": cond or key, "threshold": thr, "actions": act,
            "key_sentence": key, "clean_text": t}


def main():
    U = [json.loads(l) for l in open(UNITS, encoding="utf-8") if l.strip()]
    # 与 l3_distill_run.py 同口径的前置过滤（只复算到「进不进输入集」这一步）
    kept = [u for u in U if u.get("kb_type") in ("wording", "external_standard", "internal_sample")
            and not (u.get("meta") or {}).get("content_quality_flag")]
    cl_all = [u for u in U if u.get("unit_type") == "clause"]
    cl_kept = [u for u in kept if u.get("unit_type") == "clause"]
    cl_ext = [u for u in cl_kept if u.get("kb_type") == "external_standard"]

    rep = {"l2_units": len(U), "kept": len(kept),
           "clause_all": len(cl_all), "clause_kept": len(cl_kept),
           "clause_kept_external_standard": len(cl_ext)}
    per = collections.Counter()
    detail = []
    for u in cl_kept:
        v = judge(u["text"])
        per[(u.get("kb_type"), v["verdict"], v["reason"])] += 1
        detail.append({"unit_id": u["unit_id"], "resource_id": u["resource_id"],
                       "kb_type": u.get("kb_type"), "anchor": u["anchor"],
                       "chars": len(norm_text(u["text"])), "verdict": v["verdict"],
                       "reason": v["reason"], "detail": v["detail"],
                       "condition": v.get("condition", ""), "threshold": v.get("threshold", []),
                       "actions": v.get("actions", [])})
    rep["per_kind"] = {f"{a}|{b}|{c}": n for (a, b, c), n in sorted(per.items())}
    rep["verdict_totals"] = dict(collections.Counter(
        (k.split("|")[1]) for k, n in rep["per_kind"].items() for _ in range(n)))
    # 资源维度
    res_rule = {d["resource_id"] for d in detail if d["verdict"] == "rule"}
    rep["resources_with_rules"] = len(res_rule)
    by_res = collections.Counter(d["resource_id"] for d in detail if d["verdict"] == "rule")
    rep["top_resources"] = [[r, n] for r, n in by_res.most_common(15)]

    if "--json" in sys.argv:
        p = sys.argv[sys.argv.index("--json") + 1]
        json.dump({"summary": rep, "detail": detail}, open(p, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        print("明细已写：%s" % p)

    print("=" * 78)
    print("clause 语料只读探针（输入集口径 = l3_distill_run.py 的 kept）")
    print("=" * 78)
    for k in ("l2_units", "kept", "clause_all", "clause_kept", "clause_kept_external_standard",
              "resources_with_rules"):
        print(f"  {k:34s} {rep[k]}")
    print("\n逐单元判定分布：")
    for k, n in sorted(rep["per_kind"].items(), key=lambda x: -x[1]):
        print(f"  {n:5d}  {k}")
    print("\n可蒸出候选的资源 top15：")
    for r, n in rep["top_resources"]:
        print(f"  {n:5d}  {r[:100]}")


if __name__ == "__main__":
    main()
