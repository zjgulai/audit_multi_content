#!/usr/bin/env python3
# 调评审链引擎出三态结论（不改引擎、不改发布件）。文本经 argv 直传，避免 shell 转义。
import subprocess, pathlib, sys, json

root = pathlib.Path(__file__).resolve().parent.parent
text = (pathlib.Path(__file__).resolve().parent / "yoga-text.txt").read_text(encoding="utf-8")

BASE = "RT-20261005-YOGA-INSIGHT-R3"
cmd = ["sh", str(root / "kb/kbpy"), "l7/review-engine/core/with_kb_evidence.py",
       "--text", text,
       "--require-layer-preflight", BASE,
       "--decision-owner", "文案合规审查",
       "--loaded-skill", "文案合规审查",
       "--loaded-skill", "kb-canonical-lookup",
       "--loaded-skill", "kb-p0-check",
       "--loaded-skill", "kb-recall",
       "--loaded-skill", "kb-check",
       "--content-type", "广告洞察文档（竞品素材+AI拟定文案）",
       "--question", "这个链接内容审核一下",
       "--json"]
p = subprocess.run(cmd, cwd=str(root), capture_output=True, text=True)
out = pathlib.Path(__file__).resolve().parent
(out / "engine.stdout.json").write_text(p.stdout, encoding="utf-8")
(out / "engine.stderr.log").write_text(p.stderr, encoding="utf-8")
print("exitcode", p.returncode)
print("--- stderr tail ---")
print("\n".join(p.stderr.strip().splitlines()[-25:]))
try:
    d = json.loads(p.stdout)
    dec = d.get("decision", {})
    print("--- decision ---")
    print("state", dec.get("state") or dec.get("decision"),
          "| confidence", dec.get("confidence"),
          "| issue_count", dec.get("issue_count"))
    print("publish", json.dumps(d.get("evidence_meta", {}).get("publish"), ensure_ascii=False))
except Exception as e:
    print("json parse failed:", e)
    print(p.stdout[:2000])
