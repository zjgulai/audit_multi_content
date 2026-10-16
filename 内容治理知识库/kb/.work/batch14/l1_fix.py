#!/usr/bin/env python3
"""§7 L1 收尾：把 3 条非 ok 按既有口径修正 + 判据核验。"""
import json,os,re,hashlib,subprocess,collections,glob
L0,L1="kb/l0","kb/l1"; RUN="20260924-1630"; EXT="l1-0.1"
ENV=dict(os.environ,PATH=os.path.expanduser("~/.dsh/bin")+":"+os.environ.get("PATH",""))
def sh(*a):
    r=subprocess.run(list(a),capture_output=True,text=True,env=ENV)
    try: return json.loads(r.stdout)
    except Exception: return {"ok":False,"error":{"message":(r.stdout or r.stderr)[:200]}}
l1man=[json.loads(l) for l in open(f"{L1}/manifest_l1.jsonl",encoding="utf-8") if l.strip()]
lat={}
for r in l1man: lat[r["resource_id"]]=r
# 既有 base 资源在 L1 里的样子（镜像它的口径）
ex=[r for r in lat.values() if r["source_kind"]=="feishu_bitable_base" and r["observed_at"]!="20260924-1630"]
print("既有 base 资源的 L1 status:",dict(collections.Counter(r["status"] for r in ex)))
for r in ex[:2]: print("   ",json.dumps(r,ensure_ascii=False)[:220])
REV=json.load(open(f"{L0}/registry/kb.json",encoding="utf-8"))["dir_map_reverse"]
rid_of=lambda k: re.sub(r'[^0-9A-Za-z._\-]+','_',k.replace(":","__").replace("/","_"))[:170]
ART_KEYS=set(json.load(open(f"{L1}/9_未归类/bitable__tblMGtPfe8ZUsEdP__recvvg2wL2fF9g.json",encoding="utf-8")).keys())
latest={}
for l in open(f"{L0}/manifest.jsonl",encoding="utf-8"):
    if l.strip():
        r=json.loads(l); latest[r["resource_key"]]=r
FIX=[]
def rewrite(rk,st,reason,segs,srcinfo,ssha):
    rid=rid_of(rk); v=latest[rk]; kt=v["kb_type"]
    art={"resource_id":rid,"resource_key":rk,"kb_type":kt,"source_kind":v["source_kind"],
         "source_sha256":ssha,"extractor_version":EXT,"status":st,"status_reason":reason,
         "anchor_spec":"anchor-1.0","anchor_kind":v["source_kind"],"source":srcinfo,
         "l0_path":v.get("path"),"l0_depth":v.get("depth"),"l0_matched_rule":v.get("matched_rule"),
         "segments":segs,"tables":[],"media_refs":[],"segment_count":len(segs),"table_count":0,
         "media_count":0,"char_count":sum(len(s["text"] or "") for s in segs),"observed_at":RUN}
    for k in ART_KEYS-set(art): art[k]="" if k in ("status_reason","kb_type_followed_l0_at_run") else (0 if k.endswith("_count") else ([] if k in ("segments","tables","media_refs") else None))
    assert not (set(art)-ART_KEYS)
    d=f"{L1}/{REV[kt]}"; os.makedirs(d,exist_ok=True); p=f"{d}/{rid}.json"; t=p+".tmp"
    with open(t,"w",encoding="utf-8") as fh: json.dump(art,fh,ensure_ascii=False,indent=1)
    json.load(open(t,encoding="utf-8")); os.replace(t,p)
    FIX.append({"resource_key":rk,"status":st,"reason":reason[:150],"segments":len(segs)})

# ① wiki → bitable（结构型：与既有 base 同口径）
for rk,tok,title in (("wiki:LLpMwbYEmiX5uSkntPucf893ncf","OShmbLBaPam6YSsCzP0cNOyBn6f","【创意】需求排期与任务管理"),
                     ("base:DXJ6b5cKtaXPQasoayEc74SUnog","DXJ6b5cKtaXPQasoayEc74SUnog","品线SEO任务管理系统")):
    r=sh("lark-cli","base","+table-list","--base-token",tok)
    if r.get("ok"):
        ts=r["data"]["tables"]
        txt="\n".join(f"{t['name']}（{t['records_count']} 条，rev {t.get('rev')}，id {t['id']}）" for t in ts)
        rewrite(rk,"ok","base 结构型资源：本批按 read 抓到表清单（结构），不抽记录正文（记录正文属各记录资源）",
                [{"kind":"paragraph","text":txt,"anchor":"#表清单"}],
                {"base_token":tok,"title":title,"tables":len(ts),"note":"base +table-list（read）"},hashlib.sha256(txt.encode()).hexdigest())
    else:
        rewrite(rk,"unreachable",f"base +table-list 失败：{r.get('error',{}).get('message','')[:120]}",[],
                {"base_token":tok,"title":title},"")
# ② wiki → sheet：CLI 无 sheets 读正文子命令
rk="wiki:EsCdw2A7tiz67Rk8LgMce2TAnEh"
rewrite(rk,"no_scope",
  "wiki 节点已解析（obj_type=sheet, obj_token=ZBAtsIiFSh3TbUt4CNvcoWPgnLe, title=W1卖点匹配证据库_检索阅读版_0827更新）；"
  "但 lark-cli 的 sheets 只有 +revision-get，**没有读正文/读区域的子命令** → 本批不新开抓取通道（避免绕过既有抽取口径），"
  "登记 no_scope 而非静默跳过",[], {"node_token":rk.split(':',1)[1],"obj_type":"sheet",
  "obj_token":"ZBAtsIiFSh3TbUt4CNvcoWPgnLe","title":"W1卖点匹配证据库_检索阅读版_0827更新",
  "blocked_by":"lark-cli sheets 子命令缺失"},"")
# ③ 台账行就地更新（这三条是本批刚追加的，非既有行）
tgt={rid_of(x["resource_key"]) for x in FIX}
out=[]
for r in l1man:
    if r["resource_id"] in tgt and r["observed_at"]==RUN:
        f=[x for x in FIX if rid_of(x["resource_key"])==r["resource_id"]][0]
        r=dict(r); r["status"]=f["status"]; r["status_reason"]=f["reason"]
        p=f"{L1}/{REV[lat[r['resource_id']]['kb_type']]}/{r['resource_id']}.json"
        a=json.load(open(p,encoding="utf-8")); r["segment_count"]=a["segment_count"]; r["char_count"]=a["char_count"]
        r["source_sha256"]=a["source_sha256"]
    out.append(r)
with open(f"{L1}/manifest_l1.jsonl","w",encoding="utf-8") as fh:
    for r in out: fh.write(json.dumps(r,ensure_ascii=False,sort_keys=True)+"\n")
print("\n修正后:",json.dumps(FIX,ensure_ascii=False,indent=1))
json.dump({"fix":FIX},open("kb/.work/batch14/l1_fix.json","w",encoding="utf-8"),ensure_ascii=False,indent=1)
