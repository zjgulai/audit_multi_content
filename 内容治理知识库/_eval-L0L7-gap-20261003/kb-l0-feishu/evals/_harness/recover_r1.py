#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从各用例的 session.jsonl 逐条重建第 1 轮 1–52 条记录（数据源=真实会话归档）。"""
import importlib.util
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
EVAL = os.path.dirname(HERE)
spec = importlib.util.spec_from_file_location("rr", os.path.join(HERE, "run_round.py"))
rr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rr)
prompts = {x["n"]: x for x in json.load(open(os.path.join(HERE, "round-prompts.json"),
                                            encoding="utf-8"))}
records = []
for n in range(1, 53):
    cwd = os.path.join(EVAL, "_work", "a1", f"item-{n:04d}")
    loaded, reply, sid = rr.read_session(cwd)
    records.append({"id": f"A{n}", "n": n, "round": 1, "paper": "a",
                    "exit_code": 0, "elapsed_s": None, "session_id": sid,
                    "skills_loaded": loaded, "skill_loaded": "kb-l0-feishu" in loaded,
                    "reply": reply, "stdout_tail": "", "stderr_tail": "",
                    "recovered_from_session": True})
    print(n, loaded, len(reply))
with open(os.path.join(HERE, "a-round-1.jsonl"), "w", encoding="utf-8") as f:
    for r in records:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")
print("rebuilt", len(records))
