# -*- coding: utf-8 -*-
"""盲测结果回收 + 触发判定 + 三轮合并。

盲测执行方式
------------
每条用例开一个**全新被测会话**（fresh child session），会话只收到「提示词」列原文，
不附加任何说明，也不告知这是评测。执行后本脚本读
~/.dsh/sessions/**/session.jsonl.zstd（DSH 会话归档），按「提示词原文全等」认回会话。

触发判定（主语 = kb-ingest-extractor，四条真实证据，任一成立即算触发）
--------------------------------------------------------------------
E0 harness 注入：slash 点名时 DSH 把 `<skill_content name="kb-ingest-extractor">`
   作为一条 user/message 注入会话（`/kb-ingest-extractor ...`）；
E1 `skill` 工具调用，name == kb-ingest-extractor；
E2 读取该 skill 的 SKILL.md（read 工具，或 bash cat/sed/head/grep 该文件）；
E3 读取该 skill 目录下的其它文件（references/scripts 等）。
只 `ls` 目录不算（可能只是在判断该不该用），记为 weak。

结论口径
--------
调用用例 → 加载 / 未加载；其余 → 触发 / 不触发；边界情况在「预期追问」且未触发、
且回复确为澄清式提问时记「追问」（score-trigger-eval.py 对边界情况支持该取值）。

用法
----
  python3 collect.py --rounds .t0_round1 .t0_round2 .t0_round3 [--b .t0_b] --cases cases_a.json --outdir .
"""
import argparse, glob, json, os, re, time
import zstandard

ROOT = os.path.expanduser("~/.dsh/sessions")
DEC = zstandard.ZstdDecompressor()
SKILL = "kb-ingest-extractor"
INJECT = f'<skill_content name="{SKILL}">'
SELF_DIR = f"skills/{SKILL}"
CLARIFY = re.compile(r"(请(你)?(先)?(告诉|提供|补充|确认|说明|指明)|能否(告诉|提供|补充)|你指的是|具体是哪|哪一个资源|哪一批|哪条资源|麻烦(告诉|提供|补充|确认)|还需要(你)?(提供|补充)|不确定你|确认一下|澄清|请补充|需要你确认)")


def load_objs(path):
    return [json.loads(l) for l in DEC.stream_reader(open(path, "rb")).read().decode("utf-8").splitlines() if l.strip()]


def read_session(sdir):
    f = os.path.join(sdir, "session.jsonl.zstd")
    if not os.path.exists(f):
        return None
    objs = load_objs(f)
    s = {"id": None, "parent": None, "mtime": os.path.getmtime(f) * 1000,
         "prompt": None, "injected": False, "skill_tool": False, "other_skills": [],
         "file_reads": [], "weak": [], "final_text": "", "n_tools": 0}
    for o in objs:
        t = o.get("type")
        if t == "session":
            s["id"], s["parent"] = o.get("id"), o.get("parentSession")
        elif t == "user/message":
            for c in (o.get("data", {}).get("content") or []):
                if c.get("type") != "text":
                    continue
                txt = c.get("text", "")
                if txt.lstrip().startswith(INJECT):
                    s["injected"] = True
                elif s["prompt"] is None and not txt.lstrip().startswith(
                        ("<system-reminder", "Current runtime context", "# AGENTS")):
                    s["prompt"] = txt
        elif t == "tool/call":
            d = o.get("data", {})
            nm = d.get("name")
            raw = d.get("arguments")
            args = raw if isinstance(raw, str) else json.dumps(raw, ensure_ascii=False)
            s["n_tools"] += 1
            if nm == "skill":
                try:
                    a = json.loads(args)
                except Exception:
                    a = {}
                if str(a.get("name", "")) == SKILL:
                    s["skill_tool"] = True
                elif a.get("name"):
                    s["other_skills"].append(a["name"])
            elif nm in ("bash", "read", "glob", "grep") and SELF_DIR in args:
                if re.search(r"(SKILL\.md|cat |sed |head |tail |less |read)", args) and nm != "glob":
                    s["file_reads"].append(f"{nm}: {args[:200]}")
                else:
                    s["weak"].append(f"{nm}: {args[:200]}")
        elif t == "assistant/message":
            msg = o.get("data", {}).get("message", {})
            txt = "".join(c.get("text", "") for c in (msg.get("content") or []) if c.get("type") == "text")
            if txt.strip():
                s["final_text"] = txt
    s["triggered"] = s["injected"] or s["skill_tool"] or bool(s["file_reads"])
    s["evidence"] = ("E0 harness 注入" if s["injected"] else
                     "E1 skill 工具" if s["skill_tool"] else
                     "E2/E3 读 skill 文件" if s["file_reads"] else
                     "weak: 仅列目录" if s["weak"] else "无")
    return s


def scan(since_ms, until_ms=None):
    out = []
    for c in glob.glob(ROOT + "/*/*"):
        f = os.path.join(c, "session.jsonl.zstd")
        if not os.path.exists(f):
            continue
        mt = os.path.getmtime(f) * 1000
        if mt < since_ms or (until_ms and mt > until_ms):
            continue
        try:
            s = read_session(c)
        except Exception:
            continue
        if s:
            s["dir"] = c
            out.append(s)
    return out


def verdict(s, cs):
    exp = cs["expected"]
    if cs["type"] == "调用":
        return "加载" if s["triggered"] else "未加载"
    if s["triggered"]:
        return "触发"
    if cs["type"] == "边界情况" and "追问" in exp:
        r = s["final_text"] or ""
        if CLARIFY.search(r) or r.rstrip().endswith(("？", "?")):
            return "追问"
    return "不触发"


def run_round(since_ms, cases, tag, outdir, extra_cases=None, until_ms=None):
    cs_all = list(cases) + list(extra_cases or [])
    sessions = scan(since_ms, until_ms)
    by_prompt = {}
    for s in sessions:
        if s["prompt"]:
            by_prompt.setdefault(s["prompt"].strip(), []).append(s)
    rows, missing = [], []
    for cs in cs_all:
        cands = sorted(by_prompt.get(cs["prompt"].strip()) or [], key=lambda x: x["mtime"], reverse=True)
        if not cands:
            missing.append(cs["id"])
            rows.append({**{k: cs[k] for k in ("id", "type", "title", "tags", "expected", "prompt")},
                         "session": None, "evidence": "缺会话", "conclusion": "", "reply": ""})
            continue
        s = cands[0]
        rows.append({**{k: cs[k] for k in ("id", "type", "title", "tags", "expected", "prompt")},
                     "session": s["id"], "evidence": s["evidence"], "other_skills": s["other_skills"],
                     "n_tools": s["n_tools"], "conclusion": verdict(s, cs), "reply": s["final_text"] or ""})
    doc = {"skill_name": SKILL, "round": tag, "since_ms": since_ms, "rows": rows, "missing": missing}
    p = os.path.join(outdir, f"rows_{tag}.json")
    json.dump(doc, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    from collections import Counter
    print(f"[{tag}] cases={len(rows)} missing={missing} 结论={dict(Counter(r['conclusion'] for r in rows))}")
    print(f"[{tag}] 证据={dict(Counter(r['evidence'] for r in rows))}")
    empty = [r["id"] for r in rows if r["session"] and not r["reply"]]
    if empty:
        print(f"[{tag}] 空回复(须重跑): {empty}")
    return doc


def merge(docs, cases, outdir, name):
    """三轮合并成两个格式：
    - {name}            : rounds = [{结论, 回复}]  → build-testcases-html.py 用
    - {name%%.json}_flat.json : rounds = [结论]    → score-trigger-eval.py 用（它的逐轮归类只吃字符串）
    """
    by_id = {cs["id"]: cs for cs in cases}
    results, flat = [], []
    for cid, cs in by_id.items():
        rounds = []
        for d in docs:
            r = next((x for x in d["rows"] if x["id"] == cid), None)
            rounds.append({"结论": (r or {}).get("conclusion", ""), "回复": (r or {}).get("reply", "")})
        results.append({"id": cid, "type": cs["type"], "title": cs["title"], "tags": cs["tags"],
                        "expected": cs["expected"], "prompt": cs["prompt"], "rounds": rounds})
        flat.append({"id": cid, "type": cs["type"], "title": cs["title"], "tags": cs["tags"],
                     "expected": cs["expected"], "prompt": cs["prompt"],
                     "rounds": [x["结论"] for x in rounds]})
    json.dump({"skill_name": SKILL, "results": results},
              open(os.path.join(outdir, name), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    flat_name = name.replace(".json", "") + "_flat.json"
    json.dump({"skill_name": SKILL, "results": flat},
              open(os.path.join(outdir, flat_name), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"[merge] {name} + {flat_name}: {len(results)} 条 × {len(docs)} 轮")
    return doc_placeholder(results)


def doc_placeholder(results):
    return {"skill_name": SKILL, "results": results}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", nargs="+", required=True, help="每轮的起始 epoch(ms) 文件路径")
    ap.add_argument("--tags", nargs="+", default=None, help="每轮标签，与 --rounds 对齐（默认 r1/r2/r3）")
    ap.add_argument("--until", nargs="+", default=None,
                    help="每轮的窗口上界 epoch(ms) 文件路径；防止后一轮的会话被前一轮认领（默认取下一轮 t0，末轮取当前时间）")
    ap.add_argument("--cases", required=True)
    ap.add_argument("--extra", default=None, help="额外用例 json（如调用场景单独文件）")
    ap.add_argument("--outdir", default=".")
    ap.add_argument("--merge-out", default=None)
    a = ap.parse_args()
    cases = json.load(open(a.cases, encoding="utf-8"))["cases"]
    extra = json.load(open(a.extra, encoding="utf-8"))["cases"] if a.extra else None
    docs = []
    tags = a.tags or [f"r{i}" for i in range(1, len(a.rounds) + 1)]
    starts = [int(open(tf).read().strip()) for tf in a.rounds]
    if a.until:
        ends = [int(open(tf).read().strip()) for tf in a.until]
    else:
        ends = starts[1:] + [int(time.time() * 1000) + 60000]
    for t0, t1, tg in zip(starts, ends, tags):
        docs.append(run_round(t0, cases, tg, a.outdir, extra, t1))
    if a.merge_out:
        merge(docs, cases + (extra or []), a.outdir, a.merge_out)
