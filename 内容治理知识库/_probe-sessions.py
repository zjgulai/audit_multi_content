#!/usr/bin/env python3
# 只读扫描：统计「用户请求 → 实际加载了哪个 skill」的真实分布
import zstandard, json, os, sys, collections, re

ROOT = os.path.expanduser("~/.dsh/sessions")
TARGET = "--Users-lute-Documents-skill-test-~6267~884Cskills-~6267~884Cskills-skills-~56DE~5F52~6D4B~8BD5-~77E5~8BC6~5E93-~5185~5BB9~6CBB~7406--"
D = os.path.join(ROOT, TARGET)
dec = zstandard.ZstdDecompressor()

SYS_PREFIXES = ("<system-reminder>", "Current runtime context.", "Instructions from:")
# 出题/盲测注入的识别（这类 subagent 会话不是真实用户流量）
PROBE_MARKERS = ("你是 DSH 宿主里的一个 agent", "只回答一个问题：这条消息会让宿主加载",
                 "只回一行：SKILL=", "不要真的执行任何操作")

def real_user_text(text):
    if not text: return None
    t = text.strip()
    if t.startswith(SYS_PREFIXES): return None
    if "Instructions from:" in t[:200]: return None
    return t

def is_probe(t):
    return any(m in t for m in PROBE_MARKERS)

sessions = []
errors = 0
sids = sorted(os.listdir(D))
for i, sid in enumerate(sids):
    p = os.path.join(D, sid, "session.jsonl.zstd")
    if not os.path.isfile(p): continue
    try:
        with open(p, "rb") as f:
            raw = dec.stream_reader(f).read().decode("utf-8", errors="replace")
    except Exception:
        errors += 1; continue
    meta = None
    events = []
    for line in raw.split("\n"):
        if not line.strip(): continue
        try: o = json.loads(line)
        except Exception: continue
        t = o.get("type")
        if t == "session":
            meta = o
        elif t == "user/message":
            d = o.get("data") or {}
            src = (d.get("source") or {}).get("kind")
            txt = "".join(c.get("text","") for c in (d.get("content") or []) if c.get("type")=="text")
            events.append(("user", src, txt, o.get("seq")))
        elif t == "tool/call":
            d = o.get("data") or {}
            if d.get("name") == "skill":
                try: arg = json.loads(d.get("arguments") or "{}")
                except Exception: arg = {}
                events.append(("skill", arg.get("name"), o.get("seq")))
        elif t == "tool/result":
            d = o.get("data") or {}
            src = ((d.get("message") or {}).get("source") or {}).get("kind")
            if src == "skill":
                m = re.search(r'<skill_content name="([^"]+)"', json.dumps(d, ensure_ascii=False))
                if m: events.append(("skill_inject", m.group(1), o.get("seq")))
    if meta is None: continue
    sessions.append({"sid": sid, "meta": meta, "events": events})

print(f"会话总数 {len(sids)}；解析成功 {len(sessions)}；解压失败 {errors}", file=sys.stderr)

# 分类
by_origin = collections.Counter(s["meta"].get("origin") for s in sessions)
# 父会话 = 非 subagent
parents = [s for s in sessions if s["meta"].get("origin") != "subagent"]
subs    = [s for s in sessions if s["meta"].get("origin") == "subagent"]

out = {"total": len(sids), "parsed": len(sessions), "errors": errors,
       "by_origin": dict(by_origin), "parents": len(parents), "subagents": len(subs)}

# ---- 父会话：真实人类流量 ----
parent_detail = []
auto_route = []      # 用户请求 → 模型自选 skill
explicit  = []       # 用户 /名 显式调用
for s in parents:
    ums = [e for e in s["events"] if e[0] == "user" and e[1] == "user"]
    texts = [real_user_text(e[2]) for e in ums]
    texts = [t for t in texts if t]
    sk = [(e[0], e[1]) for e in s["events"] if e[0] in ("skill", "skill_inject")]
    sk_names = []
    for k, n in sk:
        if n and n not in sk_names: sk_names.append(n)
    if not texts: continue
    probe = any(is_probe(t) for t in texts)
    # 显式 /name 调用
    exp = []
    for t in texts:
        exp += re.findall(r'(?:^|\s)/([A-Za-z0-9_\u4e00-\u9fff-]+)', t)
    parent_detail.append({"sid": s["sid"], "title": (s["meta"].get("title") or "")[:60],
                          "createdAt": s["meta"].get("createdAt"), "probe": probe,
                          "first_user": texts[0][:90].replace("\n", " "),
                          "n_user": len(texts), "skills": sk_names, "explicit": exp})

out["parent_sessions_with_real_user"] = len(parent_detail)
# 真实（非出题）父会话里，模型自选了 skill 的比例
real = [p for p in parent_detail if not p["probe"]]
with_skill = [p for p in real if p["skills"]]
out["real_parent_sessions"] = len(real)
out["real_parent_with_skill_load"] = len(with_skill)
out["real_parent_without_any_skill"] = len(real) - len(with_skill)

# ---- 各 skill 被自动加载的次数（父会话，非出题）----
cnt = collections.Counter()
for p in real:
    for n in p["skills"]: cnt[n] += 1
out["skill_load_counts_real_parents"] = cnt.most_common()

# 显式 /name 调用统计
exp_cnt = collections.Counter()
for p in real:
    for n in p["explicit"]: exp_cnt[n] += 1
out["explicit_slash_counts"] = exp_cnt.most_common()

out["samples"] = sorted(real, key=lambda x: -(x["createdAt"] or 0))[:40]

json.dump(out, open("/tmp/probe-sessions-out.json", "w"), ensure_ascii=False, indent=1)
print(json.dumps({k: v for k, v in out.items() if k != "samples"}, ensure_ascii=False, indent=1))
