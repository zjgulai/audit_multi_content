#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""自命中检查器（确定性）—— 素材是不是库里已定稿的「反例 / 禁区」条款本身。

用在哪
------
评审链里有一类结论反复摇摆：素材其实就是**库自己**的样本（图片是样本图、链接是样本页、
文本是样本原文），按平台规则该判 BLOCK。但引擎对「反例 / 禁区」**没有消费者**
（`with_kb_evidence.py` 里 `反例` / `禁区` 零命中），这件事过去全靠 agent 临场裁量 ——
同一个素材换一轮就可能 PASS 也可能 BLOCK（实测：文案单 R1=PASS / R3=REVIEW / R4=REVIEW / R5=PASS）。
本脚本把这件事变成**同输入同输出**的机械判定，供 agent 引用，不由 agent 自由心证。

判据（逐条可复算）
------------------
对每条反例 / 禁区条款（`kb/l4/canonical/sample_case.jsonl`，当前 181 条）：

1. 归一化 —— 去掉空白与标点，只留 `[0-9A-Za-z]` 与中日韩汉字。
2. **逐字段比对**：`sample_body` 与 `advice` **各算各的**，不拼成一段。
   （这不是洁癖：`advice` 中位长度是 **0**（181 条里过半没有这个字段），
   拼起来会用一个空串去稀释分母，把「素材只有样本正文」的真自命中从 1.000 压到 0.71 而漏报。）
3. 求**最长逐字公共串** `R`（真子串，不做编辑距离、不做同义）。
4. 包含比 `ratio = R / min(len(素材), len(该字段))`，取两个字段里较大者。
5. **命中**当且仅当 `ratio >= 0.90` **且** `R >= 80`。

阈值有实测依据，不是拍的
------------------------
拿**库内条款两两**做阴性对照（同域、同表、且大量共用 `【审核 · 日期】` / `**项目名：**`
这类套话，是能构造出的最苛刻的反面样本），n=600 对，**按上面的逐字段判据**测：

| 量 | 值 |
|---|---|
| 比值 p50 / p90 / p99 | 0.088 / 0.185 / 0.333 |
| 第 5 名 | 0.429，但**逐字只剩 3 字** |
| 比值 ≥ 0.90 的对数 | **4 对** —— 全都是**整条包含**（1.000），不是噪声 |

⇒ 加上 `R >= 80` 这道闸后，600 对阴性对照里**误报 0**。
那道闸不是摆设：`advice` 字段极短（中位 0），短字段上的比值天然容易冲到 1.0，
上面第 5–8 名的 0.429 / 0.333 全是 2–3 字的偶然重合 —— `ratio` 单独用会误报，`run` 单独用会漏报，两把一起才分得开。

⚠️ 实测同时暴露一个治理事实（本脚本不修，只如实报）：**4 对条款整条互相包含** ——
S-1.96 ⊂ S-1.12、S-1.20 ⊂ S-1.36、S-1.55 ⊂ S-1.120、S-1.174 ⊂ S-1.3。
若把其中一条的原文当素材喂进来，本脚本会**如实**报另一条命中。

它不做什么
----------
- 不判三态（PASS / REVIEW / BLOCK）—— 只报「是不是库样本」这个事实。
- 不做语义判断：同义改写的自命中**它看不见**（这是取舍，不是遗漏；宁可漏报不可乱报）。
- 图片 / 视频的**文件级**同一性不在这里 —— 那是 `media_refs` / attachment 的比对。
  本脚本只处理**文本**（图片 OCR 文本、视频转写文本、链接正文都可以作为 `--text` 喂进来）。
- 不写库，只读。

用法
----
    sh kb/kbpy l7/review-engine/core/selfhit_check.py --text "<素材文本或它的 OCR / 转写>"
    sh kb/kbpy l7/review-engine/core/selfhit_check.py --text-file /tmp/mat.txt --json

退出码恒为 0：它只报事实，不阻断链路。
但 `status=error` 时**不许**把结果读成「不命中」—— 那是「没查成」，两者必须分开报。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
KB_ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))  # kb/
CLAUSES = os.path.join(KB_ROOT, "l4", "canonical", "sample_case.jsonl")

DEFAULT_MIN_RATIO = 0.90
DEFAULT_MIN_RUN = 80

_KEEP = re.compile(r"[^0-9A-Za-z\u4e00-\u9fff]+")


def norm(s: str) -> str:
    return _KEEP.sub("", s or "")


def _has_run(short: str, long_: str, t: int) -> bool:
    """short 里有没有长度 t 的窗口原样出现在 long_ 里。"""
    if t <= 0:
        return True
    if t > len(short) or t > len(long_):
        return False
    seen = {short[i:i + t] for i in range(len(short) - t + 1)}
    return any(long_[i:i + t] in seen for i in range(len(long_) - t + 1))


def max_run(a: str, b: str) -> int:
    """最长逐字公共串长度（二分 + 窗口集合，O((n+m) log min(n,m))）。"""
    if not a or not b:
        return 0
    short, long_ = (a, b) if len(a) <= len(b) else (b, a)
    hi = len(short)
    if not _has_run(short, long_, 1):
        return 0
    if _has_run(short, long_, hi):
        return hi
    lo = 1
    while lo < hi - 1:
        mid = (lo + hi) // 2
        if _has_run(short, long_, mid):
            lo = mid
        else:
            hi = mid
    return lo


def load_clauses():
    out = []
    with open(CLAUSES, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            # ★★ 已销号的条款**不许再当依据**（2026-10-14 加，与 `review.py::load_case_clauses` 同一口径）。
            #   为什么：销号只写标记（`status=superseded`），而这里原先**不读 `status`** ⇒
            #   被销的号（anchor 已死）照样参与自命中比对。孪生号正文逐字相同、anchor 是活的
            #   ⇒ 挡掉被销那一侧**不丢发现**，只去掉重复与死链。
            if str(d.get("status") or "").strip().lower() == "superseded":
                continue
            if d.get("polarity") == "反例" or str(d.get("semantics") or "").startswith("禁区"):
                txt = {
                    "sample_body": norm(d.get("sample_body")),
                    "advice": norm(d.get("advice")),
                }
                out.append((d, txt))
    return out


def l0_entry_url(resource_id: str) -> str | None:
    """把条款的 resource_id 接回 L0 那条源记录，取可点直链（四段溯源第四段）。"""
    if not resource_id or not resource_id.startswith("bitable__"):
        return None
    rest = resource_id[len("bitable__"):]  # <table_id>__<record_id>
    path = os.path.join(KB_ROOT, "l0", "2_内部正负样本库",
                        "feishu_bitable_record__%s.json" % rest)
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh).get("entry_url")
    except Exception:
        return None


def check(text: str, min_ratio: float, min_run: int, snippet: int = 200):
    mat = norm(text)
    clauses = load_clauses()
    hits = []
    for d, fields in clauses:
        if not mat:
            continue
        best = None  # (ratio, run, field, frag)
        for fname, ctext in fields.items():
            if not ctext:
                continue
            # 便宜的前置过滤：连 min_run 都凑不出来 ⇒ 不可能命中，不必二分
            short, long_ = (mat, ctext) if len(mat) <= len(ctext) else (ctext, mat)
            if not _has_run(short, long_, min_run):
                continue
            r = max_run(mat, ctext)
            base = min(len(mat), len(ctext))
            if base == 0:
                continue
            ratio = r / base
            if ratio < min_ratio or r < min_run:
                continue
            frag = ""
            for i in range(len(mat) - r + 1):
                if r and mat[i:i + r] in ctext:
                    frag = mat[i:i + r]
                    break
            if best is None or ratio > best[0]:
                best = (ratio, r, fname, frag)
        if best is None:
            continue
        ratio, r, fname, frag = best
        hits.append({
            "article_no": d.get("article_no"),
            "semantics": d.get("semantics"),
            "anchor": d.get("anchor"),
            "source_sha256": d.get("source_sha256"),
            "unit_id": d.get("unit_id"),
            "resource_id": d.get("resource_id"),
            "entry_url": l0_entry_url(d.get("resource_id")),
            "ratio": round(ratio, 3),
            "run": r,
            "matched_field": fname,
            "direction": ("material_in_clause" if len(mat) <= len(fields[fname] or "")
                          else "clause_in_material"),
            "matched_verbatim": frag[:snippet],
            "matched_verbatim_truncated": len(frag) > snippet,
        })
    hits.sort(key=lambda h: (-h["ratio"], -h["run"]))
    return mat, clauses, hits


def main() -> int:
    ap = argparse.ArgumentParser(description="自命中检查器（素材 vs 库内反例/禁区条款，确定性）")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--text", help="素材文本（或其 OCR / 转写文本）")
    g.add_argument("--text-file", help="从文件读素材文本（UTF-8）")
    ap.add_argument("--min-ratio", type=float, default=DEFAULT_MIN_RATIO)
    ap.add_argument("--min-run", type=int, default=DEFAULT_MIN_RUN)
    ap.add_argument("--json", action="store_true", help="输出 JSON（默认人读）")
    a = ap.parse_args()

    out = {
        "mode": "selfhit_check",
        "status": "ok",
        "self_hit": False,
        "hits": [],
        "thresholds": {"min_ratio": a.min_ratio, "min_run": a.min_run},
        "threshold_basis": {
            "control": "库内反例/禁区条款两两，n=600（同域套话最苛刻反面样本），按逐字段判据测",
            "ratio_p50": 0.088, "ratio_p90": 0.185, "ratio_p99": 0.333,
            "fifth_highest": 0.429, "fifth_highest_run": 3,
            "pairs_at_or_above_0_90": 4,
            "note": "≥0.90 的 4 对全是整条包含（1.000）；加 run≥80 后 600 对误报 0",
        },
        "must_not_read_as": [
            "本结果不是三态结论（PASS/REVIEW/BLOCK）",
            "status=error 时不得读成「不命中」",
            "同义改写的自命中看不见（只做逐字比对）",
        ],
    }

    try:
        if a.text_file:
            with open(a.text_file, encoding="utf-8") as fh:
                text = fh.read()
        else:
            text = a.text
        if text is None:
            raise ValueError("素材为空")
        mat, clauses, hits = check(text, a.min_ratio, a.min_run)
        out["material_normalized_chars"] = len(mat)
        out["clauses_scanned"] = len(clauses)
        out["hits"] = hits
        out["self_hit"] = bool(hits)
        if not mat and text is not None:
            out["status"] = "ok"
            out["note"] = "素材归一化后为空（全是标点/空白）—— 无从比对，不是「不命中」"
    except Exception as e:  # 判定失败必须可见，不许静默成 False
        out["status"] = "error"
        out["error"] = "%s: %s" % (type(e).__name__, e)
        out["self_hit"] = None

    if a.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print("自命中检查：%s" % ("命中" if out["self_hit"] else
                                ("查不成" if out["status"] == "error" else "未命中")))
        if out["status"] == "error":
            print("  ⚠ 出错，**不得**读成「不命中」：%s" % out["error"])
        print("  素材归一化字符 %s ｜ 扫过条款 %s 条 ｜ 阈值 ratio≥%s 且 run≥%s"
              % (out.get("material_normalized_chars"), out.get("clauses_scanned"),
                 out["thresholds"]["min_ratio"], out["thresholds"]["min_run"]))
        for h in out["hits"]:
            print("  ● %s  比%.3f  逐字%d 字  字段=%s  %s" %
                  (h["article_no"], h["ratio"], h["run"], h["matched_field"], h["direction"]))
            print("    锚点 %s" % h["anchor"])
            print("    sha  %s" % h["source_sha256"])
            print("    L0   %s" % h["entry_url"])
            print("    逐字 %s%s" % (h["matched_verbatim"],
                                    "…" if h["matched_verbatim_truncated"] else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
