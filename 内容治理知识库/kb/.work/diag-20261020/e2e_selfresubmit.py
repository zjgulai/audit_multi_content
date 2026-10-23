#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""端到端批量验证（只读 · dry-run）—— 拿库内负面样本**自己的图内文字**当素材送进依据侧引擎。

问的问题只有一个：
  把库里那条素材**原样再送一次**，引擎认不认得它出自库里？

判据（从引擎 JSON 里读，不从中文里抠）：
  · state        三态
  · covered_by   覆盖判据归因（case / rule / same_source / safe_vocabulary / 空）
  · findings     产出的依据条数
  · case_theme_rejected  被题材闸门挡下的案例

用法：python3 kb/.work/diag-20261020/e2e_selfresubmit.py [--n 8]
  ⚠️ 只读：不写 kb/l7/reports、不写 kb/l7/runs、不发飞书（--dry-run + 独立 report-dir）。
"""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
AUDIT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "audit_images.out.json")
WORK = os.path.dirname(os.path.abspath(__file__))


def jlines(p):
    out = []
    with open(p, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=8)
    ap.add_argument("--ctype", default="text", choices=["text", "image"],
                    help="送审模态：text（复现 10:07 那单的实际口径）/ image（负样本规则层会跑）")
    a = ap.parse_args()

    rows = json.load(open(AUDIT, encoding="utf-8"))["rows"]
    # 只看「有图内文字」的反例，按语言均摊挑样本
    cand = [r for r in rows if r["has_ocr"]]
    by_lang = {}
    for r in cand:
        by_lang.setdefault(r["ocr_lang"], []).append(r)
    picked = []
    for lang in ("英文", "中英混排"):
        picked += (by_lang.get(lang) or [])[: max(2, a.n // 2)]
    picked = picked[: a.n]

    # 记录 → 图内文字
    units = jlines(os.path.join(ROOT, "kb/l2/units.jsonl"))
    ocr_by_rec = {}
    for u in units:
        if "[image_ocr]" not in str(u.get("text") or ""):
            continue
        m = re.search(r"#素材/([^/]+)/", str(u.get("anchor") or ""))
        if m:
            ocr_by_rec.setdefault(m.group(1), []).append(str(u.get("text")))
    # 案例号 → resource_id → 记录号
    cases = {c.get("article_no"): c
             for c in jlines(os.path.join(ROOT, "kb/l4/canonical/sample_case.jsonl"))}

    results = []
    for r in picked:
        c = cases.get(r["no"]) or {}
        m = re.search(r"(rec[a-zA-Z0-9]+)", str(c.get("resource_id") or ""))
        rec = m.group(1) if m else ""
        txt = "\n".join(ocr_by_rec.get(rec) or [])
        if not txt.strip():
            continue
        # ★ 2026-10-20：**必须照守衡真实送审的格式包一层**。
        #   守衡送图单时，`--material-file` 的正文恒以 `【图片 N 的图内文字（本机 OCR）】` 开头
        #   （见 10:07 那单的 `input_manifest.text`）。库侧「图单判据」认的就是这个标记。
        #   不包这一层，测的就不是真实路径 —— 会得出「修复没生效」的假结论（本脚本自己踩过）。
        tf = tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False,
                                         encoding="utf-8", dir="/tmp")
        tf.write("【图片 1 的图内文字（本机 OCR）】\n" + txt)
        tf.close()
        cmd = [sys.executable,
               os.path.join(ROOT, "kb/l7/skills/kb-content-review/scripts/review.py"),
               "--i-am-the-entry", "--file", tf.name, "--content-type", a.ctype,
               "--json", "--dry-run",
               "--report-dir", os.path.join(WORK, "e2e-rep"),
               "--run-id", "e2e-%s-%s" % (a.ctype, str(r["no"]).replace(".", "-"))]
        try:
            p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=180)
            doc = json.loads(p.stdout)
            cov = (doc.get("trace") or {}).get("coverage") or {}
            results.append({
                "article_no": r["no"], "record": rec, "lang": r["ocr_lang"],
                "judge_kind": r["kind"],
                "state": doc.get("state"), "covered": cov.get("covered"),
                "covered_by": cov.get("covered_by"),
                "findings": len(doc.get("findings") or []),
                "case_hits": len(cov.get("case_unit_hits") or []),
                "case_rejected": len(cov.get("case_theme_rejected") or []),
                "neg_hits": len(((doc.get("trace") or {}).get("negative_rules") or {}).get("hits") or []),
                "rejected_self": any(x.get("article_no") == r["no"]
                                     for x in (cov.get("case_theme_rejected") or [])),
            })
        finally:
            try:
                os.unlink(tf.name)
            except OSError:
                pass

    print(f"{'案例号':<10}{'语言':<8}{'判定':<8}{'state':<8}{'covered_by':<12}"
          f"{'命中/被否':<12}{'负样本命中':<10}{'依据':<6}{'自己那条被否?'}")
    for x in results:
        print(f"{x['article_no']:<10}{x['lang']:<8}{x['judge_kind']:<8}{str(x['state']):<8}"
              f"{str(x['covered_by']):<12}{str(x['case_hits'])+'/'+str(x['case_rejected']):<12}"
              f"{x['neg_hits']:<10}{x['findings']:<6}{x['rejected_self']}")
    out = os.path.join(WORK, "e2e_selfresubmit.%s.json" % a.ctype)
    json.dump(results, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    n_pass = sum(1 for x in results if x["state"] == "PASS")
    n_self = sum(1 for x in results if x["rejected_self"])
    print(f"\n合计 {len(results)} 单｜PASS {n_pass}｜自己那条被题材闸门否掉 {n_self}")
    print(f"明细：{out}")


if __name__ == "__main__":
    main()
