#!/usr/bin/env python3
# 本会话（session-5ed3514a）独立复跑：调评审链引擎出三态结论并自动发飞书。
# 不改引擎、不改发布件；文本经 argv 直传，避免 shell 转义。
import subprocess, pathlib, json

here = pathlib.Path(__file__).resolve().parent
root = here.parent
text = (root / "_rt-yoga-20261005b" / "yoga-text.txt").read_text(encoding="utf-8")

BASE = "RT-20261005-YOGA-INSIGHT-R4"
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
(here / "engine.stdout.json").write_text(p.stdout, encoding="utf-8")
(here / "engine.stderr.log").write_text(p.stderr, encoding="utf-8")
print("exitcode", p.returncode)
print("--- stderr tail ---")
print("\n".join(p.stderr.strip().splitlines()[-30:]))
try:
    d = json.loads(p.stdout)
    dec = d.get("decision", {})
    print("--- decision ---")
    print("state", dec.get("state") or dec.get("decision"),
          "| confidence", dec.get("confidence"),
          "| issue_count", dec.get("issue_count"),
          "| content_id", dec.get("content_id"),
          "| review_id", dec.get("review_id"))
    print("publish", json.dumps(d.get("evidence_meta", {}).get("publish"), ensure_ascii=False))
    print("layer_preflight ok", d.get("evidence_meta", {}).get("layer_preflight", {}).get("ok"))
    print("decision_owner", json.dumps(d.get("evidence_meta", {}).get("decision_owner"), ensure_ascii=False)[:300])
except Exception as e:
    print("json parse failed:", e)
    print(p.stdout[:2000])
