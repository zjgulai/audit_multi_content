#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""重扫器：用**修好的注入正则**重新从会话归档里取加载证据（不重跑会话）。

为什么需要它：
  `read_session.analyse` 原正则只认未转义的 `<skill_content name="X">`，而斜杠注入在
  session.jsonl 里落成 `<skill_content name=\\"X\\">`（JSON 转义）⇒ **斜杠路线的加载证据全部漏检**。
  实测代价：调用题 51「/kb-recall」、53「/kb-recall（无材料）」明明是加载了，却被判「未加载」，
  **调用门槛假红**。已修正则；本脚本把已有轮次按新尺子重扫一遍，保证同一批记录用同一把尺子。

用法：
  python3 rescan.py --file rounds/a-round1.jsonl [--out rounds/a-round1.jsonl]
  python3 rescan.py --dir ../_src-v120/rounds --out ../_src-v120/rounds-rescanned
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import read_session as rs  # noqa: E402


def rescan_record(rec: dict) -> dict:
    fp = rec.get("session_path") or ""
    if not fp or not os.path.exists(fp):
        return rec
    try:
        a = rs.analyse(fp, "kb-recall")
    except Exception as exc:  # noqa: BLE001
        rec["rescan_error"] = str(exc)
        return rec
    rec["loaded_target_skill"] = bool(a.get("loaded_target_skill"))
    rec["loaded_any_skill"] = bool(a.get("loaded_any_skill"))
    rec["skill_tool_calls"] = a.get("skill_tool_calls", [])
    rec["injected_skills"] = a.get("injected_skills", [])
    rec["loaded_other_skills"] = a.get("loaded_other_skills", [])
    rec["ends_with_question"] = bool(a.get("ends_with_question"))
    # 会话归档在强杀后仍会补写 ⇒ 用**同一份最终快照**覆盖 reply（比读出瞬间更完整、各条一致）
    rec["reply"] = a.get("reply", "") or ""
    rec["reply_chars"] = len(rec["reply"])
    rec["rescanned"] = True
    # 重新判有效性（口径同 rt2.py）
    loaded, any_skill = rec["loaded_target_skill"], rec["loaded_any_skill"]
    if loaded or any_skill:
        rec["valid"], rec["invalid_reason"] = True, ""
    elif not rec["reply"].strip():
        rec["valid"] = False
        rec["invalid_reason"] = ("timeout_empty_reply（限时空回复，证据不足）"
                                 if rec.get("timed_out") else "empty_reply（空回复，证据不足）")
    elif rec.get("timed_out") and len(rec["reply"].strip()) < 100:
        rec["valid"], rec["invalid_reason"] = False, "timeout_partial_reply（限时半截回复，证据不足）"
    else:
        rec["valid"], rec["invalid_reason"] = True, ""
    return rec


def rescan_file(src: str, dst: str) -> dict:
    rows = [json.loads(l) for l in open(src, encoding="utf-8") if l.strip()]
    before = sum(r.get("loaded_target_skill") for r in rows)
    out = [rescan_record(r) for r in rows]
    after = sum(r.get("loaded_target_skill") for r in out)
    with open(dst, "w", encoding="utf-8") as f:
        for r in out:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return {"file": os.path.basename(src), "n": len(rows),
            "loaded_before": before, "loaded_after": after,
            "invalid_after": sum(1 for r in out if not r.get("valid"))}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file")
    ap.add_argument("--dir")
    ap.add_argument("--out")
    a = ap.parse_args()
    if a.file:
        dst = a.out or a.file
        print(json.dumps(rescan_file(a.file, dst), ensure_ascii=False))
    if a.dir:
        os.makedirs(a.out, exist_ok=True)
        for name in sorted(os.listdir(a.dir)):
            if name.endswith(".jsonl"):
                print(json.dumps(rescan_file(os.path.join(a.dir, name),
                                             os.path.join(a.out, name)), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
