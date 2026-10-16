#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kb-check 修复版回归取证 / 回填器（回填员侧，**不进入被测会话**）。

与上一批 `session_evidence.py` 的两处关键差别（上一批由此产生假阴性）：

1. **斜杠调用是「注入式加载」，没有 skill 工具调用**。
   DSH 会把 `/kb-check …` 解析成一条 `source.kind == "skill-invocation"` 的
   `user/message`，正文以 `<skill_content name="kb-check">` 注入；**skill 工具调用数为 0**。
   上一批只认 `skill` 工具调用 + 一个**永远匹配不到**的正则
   （`r'<skill_content\\s+name="([^"]+)"'` 作用在 `json.dumps()` 结果上，
   而 json.dumps 已把 `"` 转义成 `\\"`），于是把「已加载」一律记成「未加载」。
   本脚本同时认三条路径：skill 工具调用 / skill-invocation 注入 / tool/result 注入。

2. **parentSession 隔离**：只统计 `parentSession == MY_SESSION` 的会话；
   另外把全体 parent 分布留痕，用来证明没有把别人的产物算进来。

用法：
    python3 collect.py --cases cases-a.json --round a-round1 --out rounds/a-round1.json
    python3 collect.py --audit            # 只打印 parent 分布与泄漏扫描
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

import zstandard

MY_SESSION = "0c6dd909-2376-42a7-a91a-7478fc6a4b84"   # 本轮修复会话（回填员）
TARGET = "kb-check"
SESS = os.path.expanduser("~/.dsh/sessions")
NS_KEY = "~5185~5BB9~6CBB~7406"                        # 「内容治理」cwd 命名空间
HERE = os.path.dirname(os.path.abspath(__file__))
dec = zstandard.ZstdDecompressor()

# 泄漏扫描：答案键特征串 + 用例文件路径
LEAK_NEEDLES = ["预期结果", "应触发 kb-check", "不应触发 kb-check", "cases-a.json",
                "cases-b.json", "kb-check.xlsx", "kb-check-b-cases.xlsx", "_fixrun-kb-check"]
INJ_RE = re.compile(r'<skill_content\s+name=\\"([^"\\]+)\\"')


def _iter_sessions(since_ms=None):
    """先按文件 mtime 粗筛（快），避免对全库 5400+ 个会话全量解压。"""
    floor = (since_ms / 1000.0 - 120.0) if since_ms else None
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
            if not fs:
                continue
            newest = max(fs, key=os.path.getmtime)
            if floor is not None and os.path.getmtime(newest) < floor:
                continue
            yield aid, newest


def _text_of(dd: dict) -> str:
    """user/message 的正文在 data.content；assistant/message 的在 data.message.content。
    （上一批 L0 线踩过的坑：接错字段 ⇒ reply 恒为空串，若拿它算分就是假分数。）"""
    c = dd.get("content")
    if c is None:
        msg = dd.get("message")
        if isinstance(msg, dict):
            c = msg.get("content")
    if isinstance(c, list):
        return "".join(x.get("text") or "" for x in c
                       if isinstance(x, dict) and x.get("type") == "text")
    if isinstance(c, str):
        return c
    return ""


def analyse(fp: str) -> dict:
    raw = dec.stream_reader(open(fp, "rb")).read().decode("utf-8", "replace")
    evs = []
    for line in raw.split("\n"):
        if line.strip():
            try:
                evs.append(json.loads(line))
            except Exception:
                pass
    meta = next((e for e in evs if e.get("type") == "session"), {}) or {}
    skill_calls, injected, user_texts, last_assistant = [], [], [], ""
    for e in evs:
        t = e.get("type")
        dd = e.get("data") or {}
        if t == "tool/call":
            if dd.get("name") == "skill":
                try:
                    a = json.loads(dd.get("arguments") or "{}")
                except Exception:
                    a = {}
                if a.get("name"):
                    skill_calls.append(a["name"])
        elif t == "user/message":
            src = dd.get("source") or {}
            if src.get("kind") == "skill-invocation" and src.get("name"):
                injected.append(src["name"])
            if src.get("kind") == "user":
                txt = re.sub(r'<skill_content\s+name=.*?</skill_content>', '',
                             _text_of(dd), flags=re.S).strip()
                if txt and not txt.startswith(SYS_PREFIXES) and "Instructions from:" not in txt[:200]:
                    user_texts.append(txt)
        elif t == "tool/result":
            src = (dd.get("message") or {}).get("source") or {}
            if src.get("kind") == "skill" and src.get("name"):
                injected.append(src["name"])
        elif t == "assistant/message":
            txt = _text_of(dd) or ""
            if txt.strip():
                last_assistant = txt
    all_skills = list(dict.fromkeys(skill_calls + injected))
    loaded = (TARGET in skill_calls) or (TARGET in injected)
    leaks = [n for n in LEAK_NEEDLES if n in raw]
    out = {
        "agent_id": os.path.basename(os.path.dirname(fp)),
        "session_id": os.path.basename(os.path.dirname(fp)),
        "replied": None,
        "session_path": fp,
        "parent_session": meta.get("parentSession"),
        "delegation_depth": meta.get("delegationDepth"),
        "origin": meta.get("origin"),
        "cwd": meta.get("cwd"),
        "created_at_ms": meta.get("createdAt"),
        "loaded_target_skill": loaded,
        "skill_tool_calls": skill_calls,
        "injected_skills": injected,
        "all_skills": all_skills,
        "loaded_any_skill": bool(all_skills),
        "user_texts": user_texts,
        "reply": last_assistant,
        "reply_head": last_assistant[:120],
        "reply_chars": len(last_assistant),
        "leak_needles": leaks,
    }
    out["replied"] = bool(last_assistant.strip())
    return out


SYS_PREFIXES = ("<system-reminder>", "Current runtime context.", "Instructions from:")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases")
    ap.add_argument("--round")
    ap.add_argument("--out")
    ap.add_argument("--audit", action="store_true")
    ap.add_argument("--all", action="store_true",
                    help="同一条用例保留**全部**会话（不取最新），用于按创建顺序切轮")
    ap.add_argument("--since", type=float, default=None,
                    help="只要 createdAt(epoch ms) 不早于该值的会话；用来把冒烟/上一轮排除在轮次外")
    ap.add_argument("--mine-only", action="store_true", default=True)
    args = ap.parse_args()

    want = {}
    if args.cases:
        raw = json.load(open(os.path.join(HERE, args.cases), encoding="utf-8"))
        for cid, c in raw.items():
            want[str(c["提示词"]).strip()] = str(cid)

    mine, others, parent_dist, incomplete = {}, 0, {}, []
    for aid, fp in _iter_sessions(args.since):
        try:
            a = analyse(fp)
        except Exception as exc:
            print(f"[warn] {aid}: {exc}", file=sys.stderr)
            continue
        par = a["parent_session"]
        parent_dist[par] = parent_dist.get(par, 0) + 1
        if par != MY_SESSION:
            others += 1
            continue
        if args.since is not None and (a.get("created_at_ms") or 0) < args.since:  # 二次精确过滤
            others += 1
            continue
        cid = None
        for ut in a["user_texts"]:
            if ut in want:
                cid = want[ut]
                break
        a["case_id"] = cid
        if cid:
            # 有效性闸门：被中断/无回复的会话**不算数**（既不算触发也不算不触发），
            # 否则「跑到一半被掐」会被误记成 TN，把 P 虚高。
            if not a.get("replied"):
                incomplete.append({"case_id": cid, "session_id": a["agent_id"],
                                   "reply_chars": a["reply_chars"]})
                continue
            mine.setdefault(cid, []).append(a)
    for cid in list(mine):
        mine[cid].sort(key=lambda x: x.get("created_at_ms") or 0)
        if not args.all:
            mine[cid] = mine[cid][-1:]   # 默认取最新，避免冒烟/重试混轮

    print(f"parentSession == {MY_SESSION[:12]} 的会话命中用例："
          f"{sum(len(v) for v in mine.values())} 个（涉及 {len(mine)} 条用例）")
    print(f"其它 parent / 窗口外的会话（**不计入**）：{others} 个")
    print(f"有 parent 命中但无回复（**不计入**）：{len(incomplete)} 个")
    if args.audit:
        top = sorted(parent_dist.items(), key=lambda x: -x[1])[:8]
        print("parent 分布 top8：", [(str(k)[:12], v) for k, v in top])
        leaks = [k for k, v in mine.items() for a in v if a["leak_needles"]]
        print(f"泄漏命中的用例（读了答案键特征串）：{sorted(set(leaks)) or '无'}")
        print(f"无回复/被中断（不计入）：{len(incomplete)} 个 {incomplete[:6]}")

    if args.out:
        os.makedirs(os.path.join(HERE, "rounds"), exist_ok=True)
        json.dump(mine, open(os.path.join(HERE, args.out), "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        print("->", args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
