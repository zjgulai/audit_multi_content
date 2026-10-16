#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v1.3.0 盲测回填（修后复测）。

与 v1.2.0 的 collect.py 的唯一差别：识别「以向用户追问收尾」的会话。

机理：被测侧是**一次性盲测会话**，没有上游可以回答 `ask_user_question`。
这类会话的 transcript 末尾是一个 `tool/call(name=ask_user_question)`
但永远等不到配对的 `tool/result`，因此**不会产生 `turn/end`**。
会话本身的判定行为（有没有加载 kb-canonical-lookup、有没有追问）已经完整
落盘，直接从原文读，不做推断、不补造。

结论口径（与 v1.2.0 三轮一致，仅把「追问」的识别做成可机检）：
  触发   = 该会话加载了 kb-canonical-lookup
  不触发 = 未加载本 skill（含加载了别的 skill）
  追问   = 未加载任何 skill，且以追问澄清收尾（ask_user_question 未获答复，或回复以追问为主）
  加载/未加载 = 调用类
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dsh_sess import scan  # noqa: E402

SESS_ROOT = os.path.expanduser("~/.dsh/sessions")
BUCKET = ("--Users-lute-Documents-skill-test-~6267~884Cskills-~6267~884Cskills-"
          "skills-~56DE~5F52~6D4B~8BD5-~77E5~8BC6~5E93-~5185~5BB9~6CBB~7406--")
TARGET = "kb-canonical-lookup"
ASK_MARKERS = ("请问", "哪一条", "哪条", "是指", "指的是", "麻烦", "可以告诉我",
               "需要你", "请提供", "说说", "哪个", "给我")


def text_of(rec):
    out = []
    for b in rec.get("data", {}).get("message", {}).get("content", []) or []:
        if isinstance(b, dict) and b.get("type") == "text":
            out.append(b.get("text", ""))
    return "".join(out)


def session_path(sid):
    p = os.path.join(SESS_ROOT, BUCKET, sid, "session.jsonl.zstd")
    if os.path.exists(p):
        return p
    for d in os.listdir(SESS_ROOT):
        p = os.path.join(SESS_ROOT, d, sid, "session.jsonl.zstd")
        if os.path.exists(p):
            return p
    return None


def collect_one(sid):
    p = session_path(sid)
    if not p:
        return {"session": sid, "error": "session file not found"}
    recs = scan(p)
    skill_calls, all_calls = [], []
    user_texts, replies = [], []
    finished = False
    n_call = n_res = 0
    last_call = None
    for r in recs:
        t = r.get("type")
        if t == "tool/call":
            nm = r.get("data", {}).get("name")
            all_calls.append(nm)
            n_call += 1
            last_call = r
            if nm == "skill":
                try:
                    skill_calls.append(json.loads(r["data"]["arguments"]).get("name"))
                except Exception:
                    skill_calls.append(r["data"].get("arguments"))
        elif t == "tool/result":
            n_res += 1
        elif t == "user/message":
            c = r.get("data", {}).get("content") or []
            txt = "".join(b.get("text", "") for b in c if isinstance(b, dict) and b.get("type") == "text")
            if txt:
                user_texts.append(txt)
        elif t == "assistant/message":
            replies.append(text_of(r))
        elif t == "turn/end":
            finished = True

    # 未配对的最后一个 tool/call = 正在等结果
    pending_tool, pending_args = None, None
    if n_call > n_res and last_call is not None:
        pending_tool = last_call.get("data", {}).get("name")
        pending_args = last_call.get("data", {}).get("arguments")
    awaiting_user = (pending_tool == "ask_user_question")

    final = replies[-1] if replies else ""
    if awaiting_user:
        # 会话以 ask_user_question 收尾时，提问本身就是它这一轮的可见回复：
        # 逐字取出来写进 reply，避免「回复为空」被误读成「什么都没答」。
        try:
            qs = json.loads(pending_args).get("questions", [])
        except Exception:
            qs = []
        parts = []
        for q in qs:
            parts.append(q.get("question", ""))
            for o in (q.get("options") or []):
                lbl = o.get("label", "") if isinstance(o, dict) else str(o)
                parts.append("  - " + lbl)
        ask_body = "\n".join(p for p in parts if p)
        if ask_body:
            final = ((final + "\n\n") if final else "") + \
                "【向用户追问 · ask_user_question（一次性盲测会话，未获答复）】\n" + ask_body
    other_skills = [s for s in skill_calls if s and s != TARGET]
    hit = TARGET in skill_calls

    asks_in_text = any(m in final for m in ASK_MARKERS) or final.count("？") >= 1
    if hit:
        concl = "触发"
    elif awaiting_user:
        concl = "追问"
    elif other_skills:
        concl = "不触发"
    else:
        short = len(final) <= 700
        concl = "追问" if (short and asks_in_text and final) else "不触发"

    return {
        "session": sid, "error": None, "finished": finished,
        "awaiting_user": awaiting_user,
        "pending_tool": pending_tool,
        "ask_text": (pending_args or "") if awaiting_user else "",
        "n_tool_lead": n_call - n_res,
        "skill_calls": skill_calls, "other_skills": other_skills,
        "n_tool_calls": len(all_calls),
        "prompt": user_texts[0] if user_texts else "",
        "n_user_texts": len(user_texts),
        "reply": final, "auto_conclusion": concl,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--map", required=True)
    ap.add_argument("--round", required=True)
    ap.add_argument("--cases", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    cases = {str(c["id"]): c for c in json.load(open(args.cases, encoding="utf-8"))["cases"]}
    mapping = json.load(open(args.map, encoding="utf-8"))
    out = {}
    for cid, sid in mapping.items():
        rec = collect_one(sid)
        c = cases.get(cid, {})
        rec["id"] = cid
        rec["title"] = c.get("title", "")
        rec["type"] = c.get("type", "")
        rec["expect"] = c.get("expect", "")
        rec["tags"] = c.get("tags", "")
        rec["prio"] = c.get("prio", "")
        rec["blind_ok"] = (rec["prompt"].strip() == (c.get("prompt", "").strip()))
        out[cid] = rec
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    bad = [k for k, v in out.items() if v.get("error") or not v.get("blind_ok")]
    err = [k for k, v in out.items() if v.get("error")]
    unfin = [k for k, v in out.items() if not v.get("finished") and not v.get("awaiting_user")]
    awaitu = [k for k, v in out.items() if v.get("awaiting_user")]
    print(f"[round {args.round}] 收集 {len(out)} 条；盲测题面不一致 {bad}；读取失败 {err}；"
          f"仍在跑 {unfin}；以追问收尾 {awaitu}")
    for cid in sorted(out, key=lambda x: int(x) if x.isdigit() else 999):
        v = out[cid]
        tgt = "加载" if TARGET in (v.get("skill_calls") or []) else (
            "未加载" if v.get("type") == "调用" else "")
        print(f"  #{cid:>3} {v.get('type','')} concl={v.get('auto_conclusion')} "
              f"skills={v.get('skill_calls')} other={v.get('other_skills')} "
              f"reply_len={len(v.get('reply',''))} await={v.get('awaiting_user')} {tgt}")


if __name__ == "__main__":
    main()
