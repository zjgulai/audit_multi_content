# -*- coding: utf-8 -*-
"""从真实会话 transcript 客观判定「是否加载了哪些 skill」——回填员侧，不进被测会话。"""
import os, sys, json, glob, zstandard

HOME = os.path.expanduser("~")
SESS = os.path.join(HOME, ".dsh", "sessions")

def bucket_name(cwd):
    """DSH 会话桶名 = cwd 的编码形式（对已知样本校验通过）。
    规则：去掉开头 '/'，'/' -> '-'，非 ASCII 字符 -> '~XXXX'，两端各补 '--'。"""
    p = os.path.abspath(cwd).lstrip("/")
    out = []
    for ch in p:
        if ch == "/": out.append("-")
        elif ch.isascii() and (ch.isalnum() or ch in "-_."): out.append(ch)
        else: out.append("~%04X" % ord(ch))
    return "--" + "".join(out) + "--"

def read(path):
    try:
        data = zstandard.ZstdDecompressor().stream_reader(open(path, "rb")).read()
    except Exception:
        return []
    recs = []
    for line in data.decode("utf-8", "replace").splitlines():
        if line.strip():
            try: recs.append(json.loads(line))
            except Exception: pass
    return recs

def transcript_for(cwd):
    b = os.path.join(SESS, bucket_name(cwd))
    fs = glob.glob(os.path.join(b, "*", "session.jsonl.zstd"))
    if not fs: return None
    return max(fs, key=os.path.getmtime)   # 同一条 cwd 重复跑过时取最新一次

def observe(cwd):
    """返回 {skills:[...], loaded:bool, kb_recall:bool, user_msgs:[...]}"""
    f = transcript_for(cwd)
    if not f: return dict(found=False, skills=[], kb_recall=False, user_msgs=[], reply="")
    recs = read(f)
    skills, umsgs = [], []
    for r in recs:
        t = r.get("type")
        if t == "tool/call" and r.get("data", {}).get("name") == "skill":
            try: skills.append(json.loads(r["data"]["arguments"]).get("name"))
            except Exception: pass
        if t == "agent/inbox/spliced":
            for m in r.get("data", {}).get("inserted", []):
                if m.get("role") == "user" and m.get("source", {}).get("kind") == "user":
                    umsgs.append("".join(c.get("text", "") for c in m.get("content", [])))
    return dict(found=True, session_file=f, skills=skills, kb_recall=("kb-recall" in skills), user_msgs=umsgs)

if __name__ == "__main__":
    cwd = sys.argv[1]
    print(json.dumps(observe(cwd), ensure_ascii=False)[:1500])
