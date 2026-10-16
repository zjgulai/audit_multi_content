#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""按「轮次标签 → childId」精确归集 kb-check 盲测轮次证据（回填员侧工具）。

为什么不用「提示词文本匹配」：同一时间还有另一个会话在跑同一份 A 卷，
文本匹配会把别人的会话混进来（实测 R1 期出现 58 条命中 / 53 条应命中）。
本工具改为从**评测主会话自己的会话日志**里读 tool-workflow/agent-start
事件，拿 label（如 R1-case-17）→ childId 的精确映射，再逐个子会话取证。

用法：
  python3 collect_round.py --owner 92c12bd1-... --prefix R1-case- --out _eval/evidence-r1.json
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

import zstandard

SESS = os.path.expanduser("~/.dsh/sessions")
NS_KEY = "~5185~5BB9~6CBB~7406"   # 「内容治理」cwd 命名空间
TARGET = "kb-check"
dec = zstandard.ZstdDecompressor()
SYS_PREFIXES = ("<system-reminder>", "Current runtime context.", "Instructions from:")


def _session_file(agent_id: str):
    for base in os.listdir(SESS):
        if NS_KEY not in base:
            continue
        p = os.path.join(SESS, base, agent_id)
        if os.path.isdir(p):
            fs = [os.path.join(p, f) for f in os.listdir(p) if f.endswith(".jsonl.zstd")]
            if fs:
                return max(fs, key=os.path.getmtime)
    return None


def read_events(fp: str):
    with open(fp, "rb") as fh:
        txt = dec.stream_reader(fh).read().decode("utf-8", "replace")
    out = []
    for line in txt.split("\n"):
        if line.strip():
            try:
                out.append(json.loads(line))
            except Exception:
                pass
    return out


def _msg_text(d):
    msg = d.get("message") if isinstance(d.get("message"), dict) else d
    content = msg.get("content")
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                t = part.get("text") or ""
                t = re.sub(r'<skill_content name="[^"]+">.*?</skill_content>', '', t, flags=re.S)
                parts.append(t)
        return "".join(parts)
    if isinstance(content, str):
        return content
    for k in ("text", "message"):
        if isinstance(msg.get(k), str):
            return msg[k]
    return ""


def analyse(fp: str):
    evs = read_events(fp)
    m = next((e for e in evs if e.get("type") == "session"), {})
    user_texts, skill_calls, injected, last_assistant, tools = [], [], [], "", []
    for e in evs:
        t = e.get("type")
        if t == "user/message":
            d = e.get("data") or {}
            raw = _msg_text(d) or ""
            if (d.get("source") or {}).get("kind") == "user":
                txt = raw.strip()
                if txt and not txt.startswith(SYS_PREFIXES) and "Instructions from:" not in txt[:200]:
                    user_texts.append(txt)
            for mm in re.finditer(r'<skill_content\s+name="([^"]+)"', json.dumps(d, ensure_ascii=False)):
                injected.append(mm.group(1))
        elif t == "tool/call":
            d = e.get("data") or {}
            nm = d.get("name")
            if nm:
                tools.append(nm)
            if nm == "skill":
                try:
                    a = json.loads(d.get("arguments") or "{}")
                except Exception:
                    a = {}
                if a.get("name"):
                    skill_calls.append(a["name"])
        elif t == "tool/result":
            d = e.get("data") or {}
            if ((d.get("message") or {}).get("source") or {}).get("kind") == "skill":
                mm = re.search(r'<skill_content name="([^"]+)"', json.dumps(d, ensure_ascii=False))
                if mm:
                    injected.append(mm.group(1))
        elif t == "assistant/message":
            txt = _msg_text(e.get("data") or "")
            if txt and txt.strip():
                last_assistant = txt
    tail = last_assistant.strip()[-160:]
    asked = bool(re.search(r"[？?]\s*$", tail)) or bool(re.search(
        r"(请(告诉我|确认|指明)|想问一下|方便说|你要(我|先)|先确认|需要你(确认|提供))", last_assistant))
    others = [s for s in skill_calls + injected if s != TARGET]
    return {
        "session_path": fp,
        "origin": m.get("origin"),
        "delegation_depth": m.get("delegationDepth"),
        "parent_session": m.get("parentSession"),
        "createdAt": m.get("createdAt"),
        "n_events": len(evs),
        "user_texts": user_texts,
        "n_user_texts": len(user_texts),
        "skill_tool_calls": skill_calls,
        "injected_skills": injected,
        "tool_names": sorted(set(tools)),
        "loaded_target_skill": (TARGET in skill_calls) or (TARGET in injected),
        "loaded_any_skill": bool(skill_calls or injected),
        "loaded_other_skills": others,
        "ends_with_question": asked,
        "reply": last_assistant,
        "reply_chars": len(last_assistant),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--owner", required=True, help="评测主会话 id（其日志含 agent-start 标签）")
    ap.add_argument("--prefix", required=True, help="轮次标签前缀，如 R1-case-")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    owner_fp = _session_file(args.owner)
    if not owner_fp:
        print(f"[error] 找不到主会话日志: {args.owner}", file=sys.stderr)
        return 2
    starts = [e for e in read_events(owner_fp) if e.get("type") == "tool-workflow/agent-start"]
    mapping = {}
    for e in starts:
        d = e.get("data") or {}
        lab = str(d.get("label") or "")
        if lab.startswith(args.prefix):
            mapping[lab[len(args.prefix):]] = d.get("childId")
    print(f"主会话 {args.owner[:8]}：{args.prefix} 命中 {len(mapping)} 个子会话")

    out = {}
    for cid in sorted(mapping, key=lambda x: int(x) if x.isdigit() else 10 ** 6):
        aid = mapping[cid]
        fp = _session_file(aid) if aid else None
        if not fp:
            print(f"  [warn] case {cid}: 找不到子会话 {aid}")
            continue
        a = analyse(fp)
        a["agent_id"] = aid
        a["case_id"] = str(cid)
        out[str(cid)] = a
        flag = "LOADED" if a["loaded_target_skill"] else ("ASK" if a["ends_with_question"] else "no")
        extra = "" if a["n_user_texts"] == 1 else f"  ⚠user_texts={a['n_user_texts']}"
        print(f"  case {cid:>3} {flag:<6} {aid[:8]} skills={a['skill_tool_calls'] + a['injected_skills']} "
              f"reply={a['reply_chars']}c{extra}")
    json.dump(out, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"-> {args.out}（{len(out)} 条）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
