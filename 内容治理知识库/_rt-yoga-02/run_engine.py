#!/usr/bin/env python3
# RT-20261005-YOGA-02：调评审链引擎出三态结论并自动发飞书（不改引擎、不改发布件）。
# 文本经 argv 直传（不走 shell），避免转义；--loaded-skill 申报本会话真实加载过的 skill。
import subprocess, pathlib, json, sys

here = pathlib.Path(__file__).resolve().parent
root = here.parent
text = (root / "_rt-yoga-02-text.txt").read_text(encoding="utf-8")
BASE = "RT-20261005-YOGA-02"
QUESTION = "这个链接内容审核一下：https://my.feishu.cn/wiki/O0unwH2Cfi29ipk50u2cVdACnMc"

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
       "--question", QUESTION,
       "--json"]
p = subprocess.run(cmd, cwd=str(root), capture_output=True, text=True)
(here / "engine.stdout.json").write_text(p.stdout, encoding="utf-8")
(here / "engine.stderr.log").write_text(p.stderr, encoding="utf-8")
print("exitcode", p.returncode)
print("--- stderr tail ---")
print("\n".join(p.stderr.strip().splitlines()[-25:]))
try:
    d = json.loads(p.stdout)
    dec = d.get("decision", {})
    print("--- decision ---")
    print("state", dec.get("state") or dec.get("decision"),
          "| confidence", dec.get("confidence"),
          "| issue_count", dec.get("issue_count"),
          "| content_id", dec.get("content_id"),
          "| review_id", dec.get("review_id"))
    em = d.get("evidence_meta", {})
    print("layer_preflight", json.dumps(em.get("layer_preflight"), ensure_ascii=False)[:400])
    print("decision_owner", json.dumps(em.get("decision_owner"), ensure_ascii=False)[:400])
    print("publish", json.dumps(em.get("publish"), ensure_ascii=False)[:1200])
except Exception as e:
    print("json parse failed:", e)
    print(p.stdout[:2500])
