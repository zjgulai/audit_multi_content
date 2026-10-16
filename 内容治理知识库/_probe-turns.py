#!/usr/bin/env python3
# 逐轮关联：每条真实用户消息 → 该轮之后紧跟的 skill 加载
import zstandard, json, os, collections, re, datetime

ROOT = os.path.expanduser("~/.dsh/sessions")
TARGET = "--Users-lute-Documents-skill-test-~6267~884Cskills-~6267~884Cskills-skills-~56DE~5F52~6D4B~8BD5-~77E5~8BC6~5E93-~5185~5BB9~6CBB~7406--"
D = os.path.join(ROOT, TARGET)
dec = zstandard.ZstdDecompressor()
SYS_PREFIXES = ("<system-reminder>", "Current runtime context.", "Instructions from:")
PROBE = ("你是 DSH 宿主里的一个 agent", "只回答一个问题：这条消息会让宿主加载", "只回一行：SKILL=")

# 评审类请求的语言特征（不问 skill 名，问这件事）
REVIEW_PAT = re.compile(r"评审一下|审核一下|审一下|帮我审|帮忙审|能不能发|能不能过审|能过审吗|能过吗|合规检查|审一审|审下|这段内容能不能|这条能不能|判.*能不能用|发布前审查|走一遍审查|这个评审|把这条审|素材审查|内容审查")

def real_text(t):
    t = (t or "").strip()
    if not t or t.startswith(SYS_PREFIXES) or "Instructions from:" in t[:200]: return None
    return t

rows = []
sids = sorted(os.listdir(D))
for sid in sids:
    p = os.path.join(D, sid, "session.jsonl.zstd")
    if not os.path.isfile(p): continue
    try:
        with open(p, "rb") as f:
            raw = dec.stream_reader(f).read().decode("utf-8", errors="replace")
    except Exception: continue
    meta = None; ev = []
    for line in raw.split("\n"):
        if not line.strip(): continue
        try: o = json.loads(line)
        except Exception: continue
        t = o.get("type"); seq = o.get("seq", 0)
        if t == "session": meta = o
        elif t == "user/message":
            d = o.get("data") or {}
            if (d.get("source") or {}).get("kind") != "user": continue
            txt = "".join(c.get("text","") for c in (d.get("content") or []) if c.get("type")=="text")
            if real_text(txt): ev.append((seq, "u", txt))
        elif t == "tool/call":
            d = o.get("data") or {}
            if d.get("name") == "skill":
                try: arg = json.loads(d.get("arguments") or "{}")
                except Exception: arg = {}
                if arg.get("name"): ev.append((seq, "s", arg["name"]))
        elif t == "tool/result":
            d = o.get("data") or {}
            if ((d.get("message") or {}).get("source") or {}).get("kind") == "skill":
                m = re.search(r'<skill_content name="([^"]+)"', json.dumps(d, ensure_ascii=False))
                if m: ev.append((seq, "s", m.group(1)))
    if meta is None or meta.get("origin") == "subagent": continue
    ev.sort(key=lambda x: x[0])
    # 逐轮：每条用户消息后、下一条用户消息前加载的 skill
    cur = None
    for seq, kind, val in ev:
        if kind == "u":
            if cur: rows.append(cur)
            cur = {"sid": sid, "ts": meta.get("createdAt"), "text": val, "skills": []}
        elif kind == "s" and cur is not None:
            if val not in cur["skills"]: cur["skills"].append(val)
    if cur: rows.append(cur)

print(f"父会话真实用户轮次总数: {len(rows)}")
probe = [r for r in rows if any(m in r["text"] for m in PROBE)]
real  = [r for r in rows if not any(m in r["text"] for m in PROBE)]
print(f"  其中出题/注入轮: {len(probe)}   真实轮: {len(real)}")

rev = [r for r in real if REVIEW_PAT.search(r["text"])]
print(f"\n命中【评审类语言特征】的真实轮: {len(rev)}")
loaded = [r for r in rev if r["skills"]]
none_  = [r for r in rev if not r["skills"]]
print(f"  加载了 skill: {len(loaded)}   未加载任何 skill: {len(none_)}")
if rev:
    print(f"  命中率 = {len(loaded)}/{len(rev)} = {len(loaded)/len(rev)*100:.0f}%")

print("\n=== 评审类轮次逐条（最近 30）===")
for r in sorted(rev, key=lambda x: -(x["ts"] or 0))[:30]:
    ts = datetime.datetime.fromtimestamp((r["ts"] or 0)/1000).strftime('%m-%d %H:%M') if r["ts"] else "?"
    one = r["text"].replace("\n"," ")[:78]
    print(f"[{ts}] {'✅' if r['skills'] else '❌'} {r['skills'] if r['skills'] else '（无）'}")
    print(f"          {one}")

# 层 skill 是否被自动加载过
LAYER = {"kb-l0-feishu","kb-ingest-extractor","kb-media-extractor","kb-clause-extractor",
         "kb-canonical-lookup","kb-p0-check","kb-recall","kb-check"}
allskill = collections.Counter()
for r in real:
    for s in r["skills"]: allskill[s]+=1
print("\n=== 真实轮里被加载的 skill 全量计数 ===")
for n,c in allskill.most_common(): print(f"  {c:4d}  {n}  {'← 层 skill' if n in LAYER else ''}")
json.dump({"rows":rows,"review":rev}, open("/tmp/probe-turns.json","w"), ensure_ascii=False, indent=1)
