#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""盲测回填：按会话 id 取真实会话原文 + 触发判定。

- 结论口径：加载了 kb-canonical-lookup = 触发（调用类记「加载」）；
  加载了别的 skill = 不触发（调用类记「未加载」）；未加载任何 skill 且回复以追问澄清为主 = 追问。
- 同时做盲测校验：会话里第一条用户文本必须逐字等于题面。
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
ASK_MARKERS = ("请问", "哪一条", "哪条", "是指", "指的是", "麻烦", "可以告诉我", "需要你", "请提供", "说说")


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
    # 兜底：全库搜同名会话目录
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
    for r in recs:
        t = r.get("type")
        if t == "tool/call":
            nm = r.get("data", {}).get("name")
            all_calls.append(nm)
            if nm == "skill":
                try:
                    skill_calls.append(json.loads(r["data"]["arguments"]).get("name"))
                except Exception:
                    skill_calls.append(r["data"].get("arguments"))
        elif t == "user/message":
            c = r.get("data", {}).get("content") or []
            txt = "".join(b.get("text", "") for b in c if isinstance(b, dict) and b.get("type") == "text")
            if txt:
                user_texts.append(txt)
        elif t == "assistant/message":
            replies.append(text_of(r))
        elif t == "turn/end":
            finished = True
    final = replies[-1] if replies else ""
    other_skills = [s for s in skill_calls if s and s != TARGET]
    hit = TARGET in skill_calls
    if hit:
        concl = "触发"
    elif other_skills:
        concl = "不触发"
    else:
        short = len(final) <= 700
        asks = any(m in final for m in ASK_MARKERS) or final.count("？") >= 1
        concl = "追问" if (short and asks and final) else "不触发"
    return {
        "session": sid, "error": None, "finished": finished,
        "skill_calls": skill_calls, "other_skills": other_skills,
        "n_tool_calls": len(all_calls),
        "prompt": user_texts[0] if user_texts else "",
        "n_user_texts": len(user_texts),
        "reply": final, "auto_conclusion": concl,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--map", required=True, help="round 映射 JSON：{case_id: session_id}")
    ap.add_argument("--round", required=True, help="轮次号 1/2/3")
    ap.add_argument("--cases", required=True, help="cases_a.json")
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
    unfin = [k for k, v in out.items() if not v.get("finished")]
    print(f"[round {args.round}] 收集 {len(out)} 条；盲测题面不一致 {bad}；读取失败 {err}；未收尾 {unfin}")
    for cid in sorted(out, key=lambda x: int(x) if x.isdigit() else 999):
        v = out[cid]
        tgt = "加载" if TARGET in (v.get("skill_calls") or []) else (
            "未加载" if v.get("type") == "调用" else "")
        print(f"  #{cid:>3} {v.get('type','')} concl={v.get('auto_conclusion')} "
              f"skills={v.get('skill_calls')} other={v.get('other_skills')} "
              f"reply_len={len(v.get('reply',''))} {tgt}")


if __name__ == "__main__":
    main()
