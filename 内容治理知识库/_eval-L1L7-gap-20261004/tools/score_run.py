#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""评分流水线驱动：把一轮跑批的产物一次算到底，中间不手敲。

链路（**每一步都用已验证过的工具，不在这里重写任何判据**）：
  ① judge.py            A 卷回填（客观加载证据 → 触发/不触发/追问/证据不足）→ score-input-a.json
  ② score-trigger-eval.py（**家族脚本**）→ summary-a.json（per_round / flaky / 安全·组合·调用标签）
  ③ output_assertions.py（按 skill 定制的断言集）→ output-assertions.json
  ④ judge_b.py + 家族脚本（**仅当跑过 B 卷**）→ summary-b.json
  ⑤ make_score.py        → score.json + 评测 YAML（判断项来自 anchors，脚本不发明）

安全护栏：**拒绝对 `_run-*` / `_archive*` 目录写入**（归档是证据 —— 本批曾误写并已还原一次）。

用法：
  python3 tools/score_run.py --skill kb-media-extractor --cases cases/kb-media-extractor \
      --run-dir runs/mediabase-a --anchors anchors/kb-media-extractor.json [--out-json ...] [--out-yaml ...]
"""
import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)
H = os.path.join(PROJ, "harness")
FAMILY = os.path.expanduser("~/.dsh/skills/root-skills-eval/scripts/score-trigger-eval.py")


def run(cmd, **kw):
    p = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if p.returncode != 0:
        print(p.stdout[-2000:])
        print(p.stderr[-2000:], file=sys.stderr)
        raise SystemExit(f"!! 步骤失败（exit={p.returncode}）：{' '.join(str(c) for c in cmd[:4])} …")
    return p.stdout


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skill", required=True)
    ap.add_argument("--cases", required=True)
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--anchors", required=True)
    ap.add_argument("--out-json", default=None)
    ap.add_argument("--out-yaml", default=None)
    ap.add_argument("--skip-b", action="store_true")
    a = ap.parse_args()

    run_dir = os.path.abspath(a.run_dir)
    cases = os.path.abspath(a.cases)
    base = os.path.basename(run_dir.rstrip("/"))
    if base.startswith("_run-") or base.startswith("_archive"):
        raise SystemExit(f"!! 拒绝写入归档/证据目录：{run_dir}")

    # 跑批完整性自检（缺轮次就别往下算，免得算出一个"看起来完整"的分）
    missing = []
    for r in (1, 2, 3):
        if not any(os.path.exists(os.path.join(run_dir, f"a-round-{r}{sfx}.jsonl"))
                   for sfx in ("", "b", "c", "d")):
            missing.append(r)
    if missing:
        raise SystemExit(f"!! 缺 A 卷第 {missing} 轮的产物，拒绝算分（{run_dir}）")

    print("① judge.py（A 卷回填）")
    print(run([sys.executable, os.path.join(H, "judge.py"), "--skill", a.skill,
               "--cases", cases, "--run-dir", run_dir]).strip()[-600:])

    print("\n② score-trigger-eval.py（家族脚本）")
    out = run([sys.executable, FAMILY, os.path.join(run_dir, "score-input-a.json"),
               "--json", os.path.join(run_dir, "summary-a.json")])
    for line in out.split("\n"):
        if any(k in line for k in ("F1", "Trigger", "安全标签", "组合标签", "调用", "✅", "❌")):
            print("   ", line.strip()[:120])

    print("\n③ output_assertions.py（按 skill 定制的断言集）")
    print(run([sys.executable, os.path.join(H, "output_assertions.py"), "--skill", a.skill,
               "--cases", cases, "--run-dir", run_dir]).strip()[-500:])

    if not a.skip_b and any(os.path.exists(os.path.join(run_dir, f"b-round-{r}.jsonl"))
                            for r in (1, 2, 3)):
        print("\n④ judge_b.py + 家族脚本（B 卷门禁）")
        print(run([sys.executable, os.path.join(H, "judge_b.py"), "--skill", a.skill,
                   "--cases", cases, "--run-dir", run_dir]).strip()[-400:])
        run([sys.executable, FAMILY, os.path.join(run_dir, "score-input-b.json"),
             "--json", os.path.join(run_dir, "summary-b.json")])
        sb = json.load(open(os.path.join(run_dir, "summary-b.json"), encoding="utf-8"))
        print(f"    B 卷 F1 = {(sb.get('average') or {}).get('f1')}   "
              f"安全 FP = {(sb.get('security_tag') or {}).get('fp_total')}")

    print("\n⑤ make_score.py（评分 + YAML）")
    cmd = [sys.executable, os.path.join(H, "make_score.py"), "--skill", a.skill,
           "--summary-a", os.path.join(run_dir, "summary-a.json"),
           "--output-assertions", os.path.join(run_dir, "output-assertions.json"),
           "--cases", os.path.join(cases, "cases-meta.json"),
           "--anchors", os.path.abspath(a.anchors),
           "--out-json", a.out_json or os.path.join(run_dir, "score.json")]
    if os.path.exists(os.path.join(run_dir, "summary-b.json")):
        cmd += ["--summary-b", os.path.join(run_dir, "summary-b.json")]
    if a.out_yaml:
        cmd += ["--out-yaml", a.out_yaml]
    print(run(cmd))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
