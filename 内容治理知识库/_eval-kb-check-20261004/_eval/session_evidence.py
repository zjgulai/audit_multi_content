#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kb-check 盲测证据提取器（回填员侧工具，**不进入被测会话**）。

从 DSH 会话归档取逐字证据：
  ~/.dsh/sessions/<cwd-encoded>/<agent-id>/session.jsonl.zstd

判定口径（与 root-skills-eval v3.19.1 一致）：
  触发   = 该会话用 skill 工具加载了 kb-check（或 user 消息里注入了 <skill_content name="kb-check">）
  不触发 = 未加载 kb-check（含加载了别的 skill）
  追问   = 未加载任何 skill 且最终回复以追问澄清收尾
  调用类 = 加载 / 未加载（主语是本 skill）

用法：
  python3 session_evidence.py --prompts cases-a.json --since 2026-10-03T22:30:00 --out _eval/evidence-r1.json
  python3 session_evidence.py --match "跑一遍所有闸门"
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys

import zstandard

SESS = os.path.expanduser("~/.dsh/sessions")
NS_KEY = "~5185~5BB9~6CBB~7406"          # 「内容治理」cwd 命名空间
TARGET = "kb-check"
dec = zstandard.ZstdDecompressor()

SYS_PREFIXES = ("<system-reminder>", "Current runtime context.", "Instructions from:")


def _find_all_session_files():
    out = []
    for base in sorted(os.listdir(SESS)):
        if NS_KEY not in base:
            continue
        d = os.path.join(SESS, base)
        if not os.path.isdir(d):
            continue
        for aid in sorted(os.listdir(d)):
            p = os.path.join(d, aid)
            if not os.path.isdir(p):
                continue
            fs = [os.path.join(p, f) for f in os.listdir(p) if f.endswith(".jsonl.zstd")]
            if fs:
                out.append((aid, max(fs, key=os.path.getmtime)))
    return out


def _msg_text(d):
    """从 user/message 或 assistant/message 的 data 里抽 text（跳过 reasoning / tool-call / skill 注入块）。"""
    msg = d.get("message") if isinstance(d.get("message"), dict) else d
    content = msg.get("content")
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                t = part.get("text") or ""
                # 斜杠注入的 skill 正文不是用户原话，剥掉后比对
                t = re.sub(r'<skill_content name="[^"]+">.*?</skill_content>', '', t, flags=re.S)
                parts.append(t)
        return "".join(parts)
    if isinstance(content, str):
        return content
    for k in ("text", "message"):
        if isinstance(msg.get(k), str):
            return msg[k]
    return ""


def read_session(fp):
    with open(fp, "rb") as fh:
        txt = dec.stream_reader(fh).read().decode("utf-8", "replace")
    evs = []
    for line in txt.split("\n"):
        if line.strip():
            try:
                evs.append(json.loads(line))
            except Exception:
                pass
    return evs


def analyse(fp, meta=None):
    evs = read_session(fp)
    m = next((e for e in evs if e.get("type") == "session"), {})
    user_texts, skill_calls, other_skills, injected, last_assistant = [], [], [], [], ""
    injected_raw = []
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
                injected_raw.append(mm.group(1))
        elif t == "tool/call":
            d = e.get("data") or {}
            if d.get("name") == "skill":
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
                    injected_raw.append(mm.group(1))
        elif t == "assistant/message":
            txt = _msg_text(e.get("data") or "")
            if txt and txt.strip():
                last_assistant = txt
    others = [s for s in skill_calls if s != TARGET] + [s for s in injected_raw if s != TARGET]
    asked = bool(re.search(r"[？?]\s*$", last_assistant.strip()[-120:])) or \
            bool(re.search(r"(请(告诉我|确认|指明)|想问一下|方便说|你要(我|先)|先确认|需要你(确认|提供))", last_assistant))
    return {
        "session_path": fp,
        "origin": m.get("origin"),
        "createdAt": m.get("createdAt"),
        "n_events": len(evs),
        "user_texts": user_texts,
        "skill_tool_calls": skill_calls,
        "injected_skills": injected_raw,
        "loaded_target_skill": (TARGET in skill_calls) or (TARGET in injected_raw),
        "loaded_any_skill": bool(skill_calls or injected_raw),
        "loaded_other_skills": others,
        "ends_with_question": asked,
        "reply": last_assistant,
        "reply_chars": len(last_assistant),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompts", help="cases-a.json / cases-b.json：{id: 提示词}")
    ap.add_argument("--since", help="ISO 本地时间，只扫此后的会话文件")
    ap.add_argument("--match", help="只打印含该串的会话")
    ap.add_argument("--out")
    args = ap.parse_args()

    since_ts = dt.datetime.fromisoformat(args.since).timestamp() if args.since else None
    want = {}
    if args.prompts:
        raw = json.load(open(args.prompts, encoding="utf-8"))
        for cid, c in raw.items():
            want[str(c["提示词"]).strip()] = str(cid)

    res = {}
    for aid, fp in _find_all_session_files():
        if since_ts and os.path.getmtime(fp) < since_ts:
            continue
        try:
            a = analyse(fp)
        except Exception as exc:
            print(f"[warn] {aid}: {exc}", file=sys.stderr)
            continue
        a["agent_id"] = aid
        # 会话归属：会话里任一条真实用户消息逐字等于某条用例提示词
        cid = None
        for ut in a["user_texts"]:
            if ut in want:
                cid = want[ut]
                break
        a["case_id"] = cid
        if args.match and args.match not in "\n".join(a["user_texts"]):
            continue
        res[aid] = a
        if cid or args.match:
            print(f"case={str(cid):>4} {'LOADED' if a['loaded_target_skill'] else ('ASK ' if a['ends_with_question'] else 'no  ')} "
                  f"{aid[:8]} skills={a['skill_tool_calls'] + a['injected_skills']} reply={a['reply_chars']}c "
                  f"user0={(a['user_texts'][0] if a['user_texts'] else '')[:40]!r}")
    if args.out:
        json.dump(res, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("->", args.out)
    print(f"共 {len(res)} 个会话（其中命中用例的 {sum(1 for v in res.values() if v['case_id'])} 个）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
