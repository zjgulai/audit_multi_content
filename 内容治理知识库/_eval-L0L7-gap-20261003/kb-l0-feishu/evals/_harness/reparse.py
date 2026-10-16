#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用修好的解析器重读已跑轮次的 session（不改提示词、不重跑会话）：
补记斜杠调用注入的 skill 加载，并统一 reply 取法。"""
import importlib.util
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from jsonl_io import read_records  # noqa: E402

spec = importlib.util.spec_from_file_location("rr", os.path.join(HERE, "run_round.py"))
rr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rr)
EVAL = os.path.dirname(HERE)


def reparse(path):
    recs = read_records(path)
    out = []
    for r in recs:
        cwd = os.path.join(EVAL, "_work", f"{r['paper']}{r['round']}",
                           f"item-{r['n']:04d}")
        if not os.path.isdir(cwd) and r.get("reparsed_from"):
            cwd = r["reparsed_from"]
        loaded, reply, sid = rr.read_session(cwd)
        if loaded or reply:
            r["skills_loaded"] = loaded
            r["skill_loaded"] = "kb-l0-feishu" in loaded
            r["reply"] = reply
            r["session_id"] = sid
        out.append(r)
    with open(path, "w", encoding="utf-8") as f:
        for r in out:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"{os.path.basename(path)}: {len(out)} 条已按新解析器重写")
    for r in out:
        if r["n"] >= 100 or (r.get("skill_loaded") and r["paper"] == "a"):
            pass
    return out


if __name__ == "__main__":
    for p in sys.argv[1:]:
        reparse(p)
