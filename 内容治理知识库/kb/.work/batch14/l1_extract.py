#!/usr/bin/env python3
"""§7 L1 补齐：建台账 + 抽取。L0 只读；飞书侧只 read。"""
import json,os,re,subprocess,hashlib,urllib.request,collections,html as H
L0,L1="kb/l0","kb/l1"; RUN="20260924-1630"; EXT="l1-0.1"
ENV=dict(os.environ, PATH=os.path.expanduser("~/.dsh/bin")+":"+os.environ.get("PATH",""))
def sh(*a):
    r=subprocess.run(list(a),capture_output=True,text=True,env=ENV)
    try: return json.loads(r.stdout)
    except Exception: return {"ok":False,"error":{"message":(r.stdout or r.stderr)[:200]}}
def sha(t): return hashlib.sha256(t.encode()).hexdigest()
def strip(h):
    h=re.sub(r'<(title|h1|h2|h3|h4|p|li|br|/p|/li|/h1|/h2|/h3|/h4)[^>]*>','\n',h)
    h=re.sub(r'<[^>]+>','',h); return re.sub(r'\n{2,}','\n',H.unescape(h)).strip()

latest={}
for l in open(f"{L0}/manifest.jsonl",encoding="utf-8"):
    if l.strip():
        r=json.loads(l); latest[r["resource_key"]]=r
L0res={k:v for k,v in latest.items() if v["status"] not in ("gone","retracted") and not k.startswith("audit:")}
rid_of=lambda k:"_".join(re.sub(r'[^0-9A-Za-z._\-]+','_',k.replace(":","__").replace("/","_")).split("_"))[:170]
rid_of=lambda k: re.sub(r'[^0-9A-Za-z._\-]+','_',k.replace(":","__").replace("/","_"))[:170]
l1man=[json.loads(l) for l in open(f"{L1}/manifest_l1.jsonl",encoding="utf-8") if l.strip()]
have={r["resource_id"] for r in l1man}
missing=sorted([(k,v) for k,v in L0res.items() if rid_of(k) not in have],key=lambda x:x[0])
print("L0 ⊖ L1 =",len(missing))
ART_KEYS=set(json.load(open(f"{L1}/9_未归类/bitable__tblMGtPfe8ZUsEdP__recvvg2wL2fF9g.json",encoding="utf-8")).keys())
MAN_KEYS=set(l1man[0].keys())
print("artifact 基准键数",len(ART_KEYS),"| manifest 基准键数",len(MAN_KEYS))
OPS=[]

def write_art(rid,obj):
    miss=ART_KEYS-set(obj); extra=set(obj)-ART_KEYS
    assert not extra, f"{rid} artifact 多出键 {extra}"
    for k in miss: obj[k]="" if k in ("status_reason","kb_type_followed_l0_at_run") else (0 if k.endswith("_count") else ([] if k in ("segments","tables","media_refs") else None))
    d=f"{L1}/9_未归类"
    kt=obj.get("kb_type")
    REV=json.load(open(f"{L0}/registry/kb.json",encoding="utf-8"))["dir_map_reverse"]
    d=f"{L1}/{REV[kt]}"; os.makedirs(d,exist_ok=True)
    p=f"{d}/{rid}.json"; t=p+".tmp"
    with open(t,"w",encoding="utf-8") as fh: json.dump(obj,fh,ensure_ascii=False,indent=1)
    json.load(open(t,encoding="utf-8")); os.replace(t,p); return p

def manrow(rid,rk,v,kt,st,reason,segs,chars,sha256):
    row={"resource_id":rid,"resource_key":rk,"kb_type":kt,"source_kind":v["source_kind"],
         "source_sha256":sha256,"extractor_version":EXT,"status":st,"status_reason":reason,
         "segment_count":segs,"char_count":chars,"media_count":0,"table_count":0,"observed_at":RUN}
    assert not (set(row)-MAN_KEYS), set(row)-MAN_KEYS
    return row

MAN=[];ART=[];RESULTS=[]
for rk,v in missing:
    rid=rid_of(rk); kt=v["kb_type"]; sk=v["source_kind"]; url=v.get("entry_url")
    segs=[]; st="ok"; reason=""; srcinfo={"url":url}; ssha=v.get("sha256")
    try:
        if sk=="feishu_bitable_record":
            rec=json.load(open(f"{L0}/records/材料收集/{v['record_id']}.json",encoding="utf-8"))
            for k,f in rec["fields"].items():
                val=f.get("value")
                txt="、".join(str(x) for x in val) if isinstance(val,list) else ("" if val is None else str(val))
                segs.append({"kind":"field_value","field_name":k,"text":txt,
                             "anchor":f"#材料收集/{v['record_id']}/{k}"})
            srcinfo={"table_name":"材料收集","record_id":v["record_id"],"field_name":None,"entry_url":url}
        elif sk in ("feishu_doc",) or rk.startswith("wiki:") or rk.startswith("docx:"):
            tok=rk.split(":",1)[1]; obj_type=None
            if rk.startswith("wiki:"):
                r=sh("lark-cli","wiki","+node-get","--node-token",tok); OPS.append({"op":"wiki +node-get","nature":"read","target":tok,"ok":r.get("ok",False)})
                if r.get("ok"):
                    d=r["data"]; obj_type=d["obj_type"]; srcinfo.update({"title":d.get("title"),"obj_type":obj_type,"obj_token":d["obj_token"],"node_token":tok})
                    tok=d["obj_token"]
                else:
                    st="no_scope"; reason=f"wiki +node-get 失败：{r.get('error',{}).get('message','')[:120]}"
            else:
                obj_type="docx"
            if st=="ok":
                r=sh("lark-cli","docs","+fetch","--doc",tok); OPS.append({"op":"docs +fetch","nature":"read","target":tok,"ok":r.get("ok",False)})
                if r.get("ok"):
                    txt=strip(r["data"]["document"]["content"])
                    segs=[{"kind":"paragraph","text":txt,"anchor":"#正文"}]
                    ssha=sha(txt)
                else:
                    st="forbidden" if "permission" in json.dumps(r).lower() else "unreachable"
                    reason=f"docs +fetch 失败：{r.get('error',{}).get('message','')[:120]}"
        elif sk=="feishu_sheet":
            tok=rk.split(":",1)[1] if rk.startswith(("sheets:","wiki:")) else None
            r=sh("lark-cli","sheets","+read","--spreadsheet",tok or "")
            OPS.append({"op":"sheets +read","nature":"read","target":tok,"ok":r.get("ok",False)})
            if r.get("ok"):
                txt=json.dumps(r.get("data"),ensure_ascii=False)[:200000]
                segs=[{"kind":"paragraph","text":txt,"anchor":"#正文"}]; ssha=sha(txt)
            else:
                st="no_scope"; reason=f"sheets +read 失败（命令/权限）：{r.get('error',{}).get('message','')[:120]}"
        elif sk=="feishu_bitable_base":
            st="no_scope"; reason=("base 结构型资源：按既有口径 schema 归 L0 指纹（sha256_state=structure_only），"
                                   "L1 不抽为正文；本批不额外抓取（避免与既有 8 条 base 的处理口径不一致）")
        elif "drive.google.com" in (url or ""):
            st="unreachable"; reason="Google Drive 文件夹：非飞书侧、本批不越域抓取；登记不可达并写明原因"
        elif "drive/folder" in (url or ""):
            st="no_scope"; reason="飞书 drive 文件夹（容器）：按既有口径不抽正文（其内容需枚举子文件，属另一批）"
        else:
            # 外部 URL：尝试 HTTP 抓正文
            try:
                req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0"})
                with urllib.request.urlopen(req,timeout=25) as resp:
                    raw=resp.read(); txt=strip(raw.decode("utf-8","ignore"))
                    srcinfo.update({"http_status":resp.status,"http_bytes":len(raw)})
                    if len(txt.strip())<40: st="empty"; reason="HTTP 200 但正文为空"
                    else:
                        segs=[{"kind":"paragraph","text":txt,"anchor":"#正文"}]; ssha=sha(txt)
                OPS.append({"op":"HTTP GET","nature":"read","target":url,"ok":True})
            except Exception as e:
                st="unreachable"; reason=f"HTTP 抓取失败：{type(e).__name__}: {str(e)[:120]}"
                OPS.append({"op":"HTTP GET","nature":"read","target":url,"ok":False})
    except Exception as e:
        st="failed"; reason=f"抽取异常：{type(e).__name__}: {str(e)[:140]}"
    chars=sum(len(s["text"] or "") for s in segs)
    art={"resource_id":rid,"resource_key":rk,"kb_type":kt,"source_kind":sk,"source_sha256":ssha,
         "extractor_version":EXT,"status":st,"status_reason":reason,"anchor_spec":"anchor-1.0",
         "anchor_kind":sk,"source":srcinfo,"l0_path":v.get("path"),"l0_depth":v.get("depth"),
         "l0_matched_rule":v.get("matched_rule"),"segments":segs,"tables":[],"media_refs":[],
         "segment_count":len(segs),"table_count":0,"media_count":0,"char_count":chars,"observed_at":RUN}
    ART.append(write_art(rid,art))
    MAN.append(manrow(rid,rk,v,kt,st,reason,len(segs),chars,ssha))
    RESULTS.append({"resource_key":rk,"resource_id":rid,"kb_type":kt,"source_kind":sk,"status":st,
                    "segments":len(segs),"chars":chars,"reason":reason[:160]})
# 落盘
with open(f"{L1}/manifest_l1.jsonl","a",encoding="utf-8") as fh:
    for r in MAN: fh.write(json.dumps(r,ensure_ascii=False,sort_keys=True)+"\n")
# index 追加
with open(f"{L1}/index/l1.jsonl","a",encoding="utf-8") as fh:
    for a in [json.load(open(p,encoding="utf-8")) for p in ART]:
        for s in a["segments"]:
            fh.write(json.dumps({"anchor":s["anchor"],"char_count":len(s["text"] or ""),
                "kb_type":a["kb_type"],"resource_id":a["resource_id"],"kind":s["kind"],
                "seg_id":f"{a['resource_id']}#s{a['segments'].index(s)+1}",
                "source_sha256":a["source_sha256"]},ensure_ascii=False,sort_keys=True)+"\n")
print("\n=== L1 新增结果 ===")
for r in RESULTS: print(f"  {r['status']:<14}{r['kb_type']:<18}{r['source_kind']:<24}seg={r['segments']:<3}{r['resource_key'][:60]}")
print("\nstatus 分布:",dict(collections.Counter(r["status"] for r in RESULTS)))
json.dump({"run_id":RUN,"missing_before":len(missing),"results":RESULTS,"ops":OPS,
           "manifest_appended":len(MAN),"artifacts":len(ART)},
          open("kb/.work/batch14/l1_result.json","w",encoding="utf-8"),ensure_ascii=False,indent=1)
