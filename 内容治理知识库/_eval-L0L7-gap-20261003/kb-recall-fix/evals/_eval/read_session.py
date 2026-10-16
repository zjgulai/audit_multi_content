#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""被测会话证据读取器（回填员侧工具，**不进入被测会话**）。

会话归档：~/.dsh/sessions/<bucket(cwd)>/<uuid>/session.jsonl.zstd
判定口径（root-skills-eval v3.19.1）：
  触发   = 该会话用 skill 工具加载了 kb-recall（或 user 消息里注入了 <skill_content name="kb-recall">）
  不触发 = 未加载 kb-recall（含加载了别的 skill）
  追问   = 未加载任何 skill 且最终回复以追问澄清收尾
"""
from __future__ import annotations

import json
import os
import re
import sys

import zstandard

dec = zstandard.ZstdDecompressor()
SESS = os.path.expanduser("~/.dsh/sessions")


def bucket_name(cwd: str) -> str:
    # ★ 必须走 realpath：macOS 上 /tmp 会被 DSH 解析成 /private/tmp，用 abspath 会找不到会话目录
    p = os.path.realpath(os.path.abspath(cwd)).lstrip("/")
    out = []
    for ch in p:
        if ch == "/":
            out.append("-")
        elif ch.isascii() and (ch.isalnum() or ch in "-_."):
            out.append(ch)
        else:
            out.append("~%04X" % ord(ch))
    return "--" + "".join(out) + "--"


def session_files_top(cwd: str):
    """只返回**本会话直接 spawn 的**一次性会话（delegationDepth == 0）。

    被测模型可能自行 spawn 子会话（上一批实测有会话 spawn 161 个）——那些的
    delegationDepth > 0，必须排除，否则会把别人的记录算进本轮统计。
    """
    out = []
    for aid, fp in session_files(cwd):
        try:
            evs = read_events(fp)
        except Exception:
            continue
        meta = next((e for e in evs if e.get("type") == "session"), {})
        if meta.get("delegationDepth", 0) == 0:
            out.append((aid, fp, meta))
    # ★ 新的在前：同一 cwd 桶里可能留着上一版 description 的旧会话（重跑会复用 cwd），
    #   按 agent id 排序会**挑到旧会话** ⇒ 用 mtime 倒序取最新那条。
    out.sort(key=lambda x: os.path.getmtime(x[1]), reverse=True)
    return out


def session_files(cwd: str):
    d = os.path.join(SESS, bucket_name(cwd))
    if not os.path.isdir(d):
        return []
    out = []
    for aid in sorted(os.listdir(d)):
        p = os.path.join(d, aid)
        if not os.path.isdir(p):
            continue
        fs = [os.path.join(p, f) for f in os.listdir(p) if f.endswith(".jsonl.zstd")]
        if fs:
            out.append((aid, max(fs, key=os.path.getmtime)))
    return out


def read_events(fp: str):
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


def msg_text(d):
    msg = d.get("message") if isinstance(d.get("message"), dict) else d
    content = msg.get("content")
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                t = part.get("text") or ""
                t = re.sub(r'<skill_content name="[^"]+">.*?</skill_content>', "", t, flags=re.S)
                parts.append(t)
        return "".join(parts)
    if isinstance(content, str):
        return content
    for k in ("text", "message"):
        if isinstance(msg.get(k), str):
            return msg[k]
    return ""


INJECT_PAT = re.compile(r'<skill_content\s+name=\\?"([^"\\]+)\\?"')

SYS_PREFIXES = ("<system-reminder>", "Current runtime context.", "Instructions from:")


def analyse(fp: str, target: str = "kb-recall"):
    evs = read_events(fp)
    meta = next((e for e in evs if e.get("type") == "session"), {})
    user_texts, skill_calls, injected, last_assistant = [], [], [], ""
    for e in evs:
        t = e.get("type")
        d = e.get("data") or {}
        if t == "user/message":
            raw = msg_text(d) or ""
            if (d.get("source") or {}).get("kind") == "user":
                txt = raw.strip()
                if txt and not txt.startswith(SYS_PREFIXES) and "Instructions from:" not in txt[:200]:
                    user_texts.append(txt)
            # ★ 必须同时认 **JSON 转义形式**：斜杠注入在 session.jsonl 里落成
            #   <skill_content name=\"kb-recall\">（json.dumps 会把 " 转成 \"）。
            #   旧正则只认未转义的 name="..." ⇒ **斜杠注入的加载证据全部漏检**
            #   （实测 调用题 51/53 明明是加载了，却被判「未加载」，调用门槛假红）。
            for mm in INJECT_PAT.finditer(json.dumps(d, ensure_ascii=False)):
                injected.append(mm.group(1))
        elif t == "tool/call":
            if d.get("name") == "skill":
                try:
                    a = json.loads(d.get("arguments") or "{}")
                except Exception:
                    a = {}
                if a.get("name"):
                    skill_calls.append(a["name"])
        elif t == "tool/result":
            if ((d.get("message") or {}).get("source") or {}).get("kind") == "skill":
                mm = INJECT_PAT.search(json.dumps(d, ensure_ascii=False))
                if mm:
                    injected.append(mm.group(1))
        elif t == "assistant/message":
            txt = msg_text(d)
            if txt and txt.strip():
                last_assistant = txt
    allsk = skill_calls + injected
    others = [s for s in allsk if s != target]
    asked = bool(re.search(r"[？?]\s*$", last_assistant.strip()[-200:])) or bool(
        re.search(r"(请(告诉我|确认|指明|提供|补充)|想问一下|方便说|你要(我|先)|先确认|需要你(确认|提供))", last_assistant)
    )
    return {
        "session_path": fp,
        "cwd": meta.get("cwd"),
        "createdAt": meta.get("createdAt"),
        "n_events": len(evs),
        "user_texts": user_texts,
        "skill_tool_calls": skill_calls,
        "injected_skills": injected,
        "loaded_target_skill": target in allsk,
        "loaded_any_skill": bool(allsk),
        "loaded_other_skills": sorted(set(others)),
        "ends_with_question": asked,
        "reply": last_assistant,
        "reply_chars": len(last_assistant),
    }


if __name__ == "__main__":
    cwd = os.path.abspath(sys.argv[1])
    tgt = sys.argv[2] if len(sys.argv) > 2 else "kb-recall"
    for aid, fp in session_files(cwd):
        a = analyse(fp, tgt)
        print(json.dumps({k: a[k] for k in ("cwd", "loaded_target_skill", "skill_tool_calls",
                                            "loaded_other_skills", "reply_chars", "ends_with_question")},
                         ensure_ascii=False))
        print("USER0:", (a["user_texts"][0][:90] if a["user_texts"] else None))
