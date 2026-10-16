#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""盲测证据提取器（回填员侧工具，不进入被测会话）。

从 DSH 会话归档（~/.dsh/sessions/<cwd-encoded>/<agent-id>/session.jsonl.zstd）里
逐字取证：本会话调用了哪些工具、有没有加载被测 skill、最终回复原文。

用法：
  /usr/bin/python3 session_evidence.py <agent-id> [<agent-id> ...]
  /usr/bin/python3 session_evidence.py --ledger _eval/run-ledger.json --out _eval/evidence-1.json
"""
import argparse
import json
import os
import re
import sys

import zstandard

SESS = os.path.expanduser("~/.dsh/sessions")
MY_CWD = ("/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/"
          "知识库/内容治理")


def encode_cwd(p: str) -> str:
    out = []
    for ch in p:
        if ch == "/":
            out.append("-")
        elif ch.isascii() and (ch.isalnum() or ch in "-_."):
            out.append(ch)
        else:
            out.append("~%04X" % ord(ch))
    return "".join(out) + "--"


def _find_session_dir(agent_id: str):
    """按 agent id 反查会话目录（不靠手工拼 cwd 编码，直接按目录名里的 cwd 关键字筛）。"""
    keys = ("~5185~5BB9~6CBB~7406",)  # 「内容治理」的 UTF-16 编码片段
    for base in sorted(os.listdir(SESS)):
        if not any(k in base for k in keys):
            continue
        cand = os.path.join(SESS, base, agent_id)
        if os.path.isdir(cand):
            return cand
    return None


def read_session(agent_id: str):
    d = _find_session_dir(agent_id)
    if not d:
        return None, f"会话目录不存在（agent={agent_id}）"
    cands = [os.path.join(d, f) for f in os.listdir(d) if f.endswith(".jsonl.zstd")]
    if not cands:
        return None, f"无 session.jsonl.zstd: {d}"
    p = max(cands, key=os.path.getmtime)
    with open(p, "rb") as fh:
        txt = zstandard.ZstdDecompressor().stream_reader(fh).read().decode("utf-8", "replace")
    events = []
    for line in txt.split("\n"):
        if line.strip():
            try:
                events.append(json.loads(line))
            except Exception:
                pass
    return {"path": p, "events": events}, None


def tool_calls(events):
    """按顺序抽取工具调用 [(seq, name, args_str)]。"""
    out = []
    for e in events:
        if e.get("type") != "tool/call":
            continue
        d = e.get("data") or {}
        name = d.get("name") or d.get("tool") or ""
        args = d.get("args") or d.get("arguments") or d.get("input") or ""
        if not isinstance(args, str):
            args = json.dumps(args, ensure_ascii=False)
        out.append((e.get("seq"), name, args))
    return out


def _msg_text(d):
    """从 assistant/message 的 data 里抽 text 部分（跳过 reasoning / tool-call）。"""
    msg = d.get("message") if isinstance(d.get("message"), dict) else d
    content = msg.get("content")
    if isinstance(content, list):
        return "".join(part.get("text", "") for part in content
                       if isinstance(part, dict) and part.get("type") == "text")
    if isinstance(content, str):
        return content
    for k in ("text", "message"):
        if isinstance(msg.get(k), str):
            return msg[k]
    return ""


def final_text(events):
    """最后一个 assistant/message 的正文（= 被测会话的最终回复原文）。"""
    best = ""
    for e in events:
        if e.get("type") != "assistant/message":
            continue
        t = _msg_text(e.get("data") or {})
        if t and t.strip():
            best = t
    return best


def user_text(events):
    for e in events:
        if e.get("type") == "user/message":
            t = _msg_text(e.get("data") or {})
            if t and t.strip():
                return t
    return ""


def injected_skills(events):
    """斜杠点名由宿主自动展开：user 消息里出现 <skill_content name="X"> → 该 skill 已加载。"""
    names = []
    for e in events:
        if e.get("type") != "user/message":
            continue
        t = _msg_text(e.get("data") or "")
        for m in re.finditer(r'<skill_content\s+name="([^"]+)"', t or ""):
            names.append(m.group(1))
    return names


def analyse(agent_id: str, skill: str = "kb-p0-check"):
    sess, err = read_session(agent_id)
    if err:
        return {"agent_id": agent_id, "error": err}
    ev = sess["events"]
    calls = tool_calls(ev)
    skill_calls = [(s, a) for s, n, a in calls if n == "skill"]
    loaded = [a for s, a in skill_calls if f'"{skill}"' in a.replace(" ", "")]
    other_loaded = [a for s, a in skill_calls if a not in loaded]
    injected = injected_skills(ev)
    return {
        "agent_id": agent_id,
        "session_path": sess["path"],
        "n_events": len(ev),
        "user_message": user_text(ev),
        "tools_used": [n for _, n, _ in calls],
        "skill_tool_calls": [a for _, a in skill_calls],
        "injected_skills": injected,
        "loaded_target_skill": bool(loaded) or (skill in injected),
        "loaded_target_via": ("tool" if loaded else ("slash-expand" if skill in injected else "")),
        "loaded_other_skills": other_loaded + [s for s in injected if s != skill],
        "reply": final_text(ev),
        "reply_chars": len(final_text(ev)),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("agent_ids", nargs="*")
    ap.add_argument("--ledger", help="run-ledger.json：{agent_id: {round, case_id, prompt}}")
    ap.add_argument("--out")
    args = ap.parse_args()

    ids = list(args.agent_ids)
    ledger = {}
    if args.ledger and os.path.exists(args.ledger):
        ledger = json.load(open(args.ledger, encoding="utf-8"))
        ids = list(ledger.keys())

    res = {}
    for aid in ids:
        a = analyse(aid)
        if aid in ledger:
            a.update({k: ledger[aid][k] for k in ("round", "case_id") if k in ledger[aid]})
        res[aid] = a
        tag = "LOADED" if a.get("loaded_target_skill") else ("ERR" if a.get("error") else "no")
        print(f"{tag:7} {aid[:8]} round={a.get('round','?')} case={a.get('case_id','?'):>3} "
              f"tools={len(a.get('tools_used') or [])} reply={a.get('reply_chars', 0)}c "
              f"{a.get('error','')}")
    if args.out:
        json.dump(res, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("->", args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
