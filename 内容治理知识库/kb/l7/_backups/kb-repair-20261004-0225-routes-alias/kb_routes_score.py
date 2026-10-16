#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kb_routes_score.py —— 把「实际被谁接走」的赢家表，按 root-skills-eval 的口径打分。

输入：赢家表（每行 `prompt_id|第1轮赢家|第2轮赢家|第3轮赢家`）
输出：① 每个 expected skill 的 results.json（5 条正例 + 其余为组内近似命中负例）
      ② 调 score-trigger-eval.py 的逐 skill P/R/F1 汇总
      ③ 路由对账表：每条 prompt 的「期望成员 vs 实际接走者」

两类命中口径（都在结果里给出，别混用）：
  strict  —— 赢家 name 必须逐字等于登记表里的成员 id（DSH 的真实装载口径）
  alias   —— 把「中文名但其实没装」的赢家折回它意图指向的成员
             （只有 alias 口径才与冻结基线 `_中文基线.md` 可比）

用法：
  python3 kb_routes_score.py <winners.txt> [--cases cases.json] [--outdir DIR] [--alias]
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

SCORER = os.path.expanduser("~/.dsh/skills/root-skills-eval/scripts/score-trigger-eval.py")

#: 归一化到「登记表里的成员 id」。两类：
#:  ① 装了但目录名 ≠ 登记 id（dir_name 口径）
#:  ② 描述里写了、但**并没有装**的中文名（折回它意图指向的成员）
#: strict 口径不走这张表（只认逐字相等的登记 id）。
ALIAS = {
    # ① 登记 id → 并发翻译轮次后的**真实装载名**（目录名 = frontmatter name）
    "brand-content-review-agent": "内容审查总控",
    "brand-review-intake-router": "送审登记",
    "brand-policy-source-curator": "证据源维护",
    "brand-text-compliance-review": "文案合规审查",
    "brand-product-claim-verifier": "产品宣称核验",
    "brand-image-safety-review": "图片安全审查",
    "brand-video-safety-review": "视频安全审查",
    "brand-us-locale-cultural-review": "美国本地化审查",
    "brand-ai-provenance-rights-review": "AI 溯源与权利审查",
    "brand-review-decision-engine": "审查裁决",
    "brand-review-report-memory": "审查报告与记忆",
    "brand-review-evaluation": "审查流程评测",
    "brand-feishu-review-adapter": "飞书审查流转",
    # ② 只被描述提及、并未安装的中文别名（历史遗留）→ 意图指向的成员
    "内容审查总控旧": "内容审查总控",
}


def canon(name):
    n = (name or "").strip()
    return ALIAS.get(n, n)


def load_cases(path):
    d = json.load(open(path, encoding="utf-8"))
    return d["用例"]


def load_winners(path):
    out = {}
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("|")
        out[parts[0]] = [p.strip() for p in parts[1:4]]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("winners")
    ap.add_argument("--cases", default=os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                    "cases_frozen_only.json"))
    ap.add_argument("--outdir", default=None)
    ap.add_argument("--alias", action="store_true", help="按 alias 口径折回中文名（与冻结基线可比）")
    a = ap.parse_args()

    cases = load_cases(a.cases)
    winners = load_winners(a.winners)
    outdir = a.outdir or os.path.join(os.path.dirname(os.path.abspath(a.winners)),
                                      "results_alias" if a.alias else "results_strict")
    os.makedirs(outdir, exist_ok=True)

    skills = sorted({c["skill"] for c in cases})

    def hit(winner, target):
        w = winner.strip()
        t = target.strip()
        if a.alias:
            w, t = canon(w), canon(t)
        return w == t

    rows = []
    summary = []
    for s in skills:
        res = []
        for c in cases:
            ws = winners.get(c["id"], [])
            rounds = []
            for w in ws:
                if w in ("CLARIFY",):
                    rounds.append("追问")
                elif hit(w, s):
                    rounds.append("触发")
                else:
                    rounds.append("不触发")
            own = (c["skill"] == s)
            res.append({
                "id": c["id"],
                "type": "正例" if own else "近似命中",
                "expected": ("应触发 %s" % s) if own else ("不应触发 %s" % s),
                "rounds": rounds,
            })
        p = os.path.join(outdir, "results_%s.json" % s)
        json.dump({"skill_name": s, "results": res}, open(p, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        out = subprocess.run([sys.executable, SCORER, p], capture_output=True, text=True)
        avg = ""
        for line in out.stdout.splitlines():
            if "3轮平均" in line:
                avg = line.strip()
        summary.append((s, avg))
        print("%-38s %s" % (s, avg))
        if not avg:
            print("   [warn] 打分器未给出平均：\n%s" % (out.stdout + out.stderr)[:400])

    print("\n== 门槛判定（F1 >= 0.90）==")
    for s, avg in summary:
        try:
            f1 = float(avg.split("F1=")[1])
        except Exception:
            f1 = float("nan")
        print("  %-38s F1=%.3f  %s" % (s, f1, "过" if f1 >= 0.90 else "**未过**"))

    # 路由对账表
    rep = os.path.join(outdir, "route_reconcile.md")
    # ⚠️ 写通道：python 直接写 .md 会落成「stat 虚高 4096」的信封态（宿主读成乱码）。
    # 规定：python 生成内容 → 无扩展名临时件 → /bin/cp 落到目标。本脚本自己先踩过这个坑。
    import tempfile
    _tmp = os.path.join(tempfile.gettempdir(), "kb_routes_reconcile.tmp")
    with open(_tmp, "w", encoding="utf-8") as fh:
        fh.write("| 用例 | 期望成员 | 实际接走（第1/2/3轮） | 三轮一致? | 一致? |\n|---|---|---|---|---|\n")
        n_ok = 0
        for c in cases:
            ws = winners.get(c["id"], [])
            cons = "是" if len(set(ws)) == 1 else "否"
            ok = "✅" if all(hit(w, c["skill"]) for w in ws) else "❌"
            if ok == "✅":
                n_ok += 1
            fh.write("| %s | %s | %s | %s | %s |\n" % (c["id"], c["skill"], " / ".join(ws), cons, ok))
        fh.write("\n逐条全轮命中：%d/%d（口径：%s）\n" % (n_ok, len(cases), "alias" if a.alias else "strict"))
    subprocess.run(["/bin/cp", _tmp, rep], check=True)
    print("\n逐条对账表：%s" % rep)
    print("逐条全轮命中：%d/%d（口径：%s）" % (n_ok, len(cases), "alias" if a.alias else "strict"))


if __name__ == "__main__":
    main()
