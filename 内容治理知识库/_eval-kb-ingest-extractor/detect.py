# -*- coding: utf-8 -*-
"""触发判定（证据式）。

本环境里被测会话「用上某个 skill」有两条真实路径：
  E1 调 `skill` 工具（name = skill 名）—— 显式加载；
  E2 直接读该 skill 的 SKILL.md（read 工具，或 bash cat/sed/head 该文件）—— 隐式加载并应用。
只做了 `ls 目录` / `grep` 的记为弱证据，**不计为触发**（可能只是在判断该不该用）。

判定主语始终是 kb-ingest-extractor：加载了别的 skill 记「未加载」。
"""
import json, os, re, zstandard

ROOT = os.path.expanduser("~/.dsh/sessions")
DEC = zstandard.ZstdDecompressor()
TARGET = "kb-ingest-extractor"

# 任何工具参数里出现这些片段，说明会话碰到了本 skill 的目录
DIR_HINTS = (f"skills/{TARGET}", f"skills/{TARGET}/")
# 读到这两个文件才算真的把指令读进来了
STRONG_HINTS = (f"skills/{TARGET}/SKILL.md",)


def _text_of_args(args):
    if isinstance(args, str):
        return args
    return json.dumps(args, ensure_ascii=False)


def load_calls(session_dir):
    f = os.path.join(session_dir, "session.jsonl.zstd")
    if not os.path.exists(f):
        return None
    objs = [json.loads(l) for l in DEC.stream_reader(open(f, "rb")).read().decode().splitlines() if l.strip()]
    ev = {"skill_tool": False, "strong": [], "weak": [], "other_skills": [], "n_tools": 0}
    for o in objs:
        if o.get("type") != "tool/call":
            continue
        d = o["data"]
        nm, args = d.get("name"), _text_of_args(d.get("arguments"))
        ev["n_tools"] += 1
        if nm == "skill":
            try:
                a = json.loads(args)
            except Exception:
                a = {}
            if str(a.get("name", "")) == TARGET:
                ev["skill_tool"] = True
            elif a.get("name"):
                ev["other_skills"].append(a["name"])
            continue
        if nm in ("bash", "read", "glob", "grep"):
            if any(h in args for h in STRONG_HINTS):
                ev["strong"].append(f"{nm}: {args[:180]}")
            elif any(h in args for h in DIR_HINTS):
                ev["weak"].append(f"{nm}: {args[:180]}")
    ev["triggered"] = ev["skill_tool"] or bool(ev["strong"])
    return ev


if __name__ == "__main__":
    import sys
    r = json.load(open(sys.argv[1], encoding="utf-8"))
    D = ROOT + "/--Users-lute-Documents-skill-test-~6267~884Cskills-~6267~884Cskills-skills-~56DE~5F52~6D4B~8BD5-~77E5~8BC6~5E93-~5185~5BB9~6CBB~7406--"
    for x in r["rows"]:
        if not x.get("session"):
            continue
        ev = load_calls(os.path.join(D, x["session"]))
        x["ev"] = ev
    json.dump(r, open(sys.argv[1], "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    for x in r["rows"]:
        ev = x.get("ev") or {}
        print(f"{x['id']:>3} {x['type']:<5} tool={ev.get('skill_tool')} strong={len(ev.get('strong') or [])} weak={len(ev.get('weak') or [])} other={ev.get('other_skills')} | {x['title']}")
