#!/usr/bin/env python3
"""补跑：2_内部正负样本库 的 专家修订汇总表 → revision_pair 切分（验证形态②配对完整性）。
本轮范围外，但因任务点名要求验证形态②配对，故额外切这一类，标注 out_of_scope_but_run。"""
import json,os,re,hashlib,collections,glob,sys
RUN=sys.argv[1]; L0,L1,L2='kb/l0','kb/l1','kb/l2'; SV='l2-0.1'
L0_PAIR={}
for p in glob.glob(f'{L0}/records/*/*.json'):
    d=json.load(open(p,encoding='utf-8')); pid=(d.get('pair') or {}).get('pair_id')
    if pid: L0_PAIR[d['record_id']]=pid
def clean(t): return re.sub(r'\s+',' ',str(t or '')).strip()
units=[]
for p in sorted(glob.glob(f'{L1}/2_内部正负样本库/*.json')):
    o=json.load(open(p,encoding='utf-8'))
    if o['source'].get('table_name')!='专家修订汇总表': continue
    fv=lambda n:[s for s in (o.get('segments') or []) if s.get('kind')=='field_value' and s.get('field_name')==n]
    b=clean(' '.join(s['text'] for s in fv('修订位置（原文引用）')))
    a=clean(' '.join(s['text'] for s in fv('修订内容')))
    r=clean(' '.join(s['text'] for s in fv('修订原因')))
    if not (b or a): continue
    rid=o['resource_id']; sha=o.get('source_sha256')
    anchor=(fv('修订位置（原文引用）') or fv('修订内容'))[0]['anchor']
    text="\n".join(x for x in [f"【前】{b}" if b else "",f"【后】{a}" if a else "",f"【原因】{r}" if r else ""] if x)
    u={"unit_type":"revision_pair","text":text,"anchor":anchor,
       "heading_path":"专家修订汇总表","resource_id":rid,"kb_type":"internal_sample",
       "source_sha256":sha,"order_in_parent":1,"parent_unit_id":None,
       "meta":{"before":b,"after":a,"reason":r,"pair_id":L0_PAIR.get(o['source'].get('record_id')),
               "pair_fields":["修订位置（原文引用）","修订内容","修订原因"],
               "table":"专家修订汇总表","scope_note":"out_of_scope_but_run（验证形态②配对）"}}
    u["unit_id"]=hashlib.sha1(f"{SV}|{rid}|{sha}|revision_pair|{anchor}|1".encode()).hexdigest()[:20]
    u["char_count"]=len(text); u["pair_ref"]=None
    units.append(u)
# 配对互指
byp=collections.defaultdict(list)
for u in units:
    pid=(u['meta'] or {}).get('pair_id')
    if pid: byp[pid].append(u)
paired=0
for pid,us in byp.items():
    if len(us)>1:
        for i,u in enumerate(us):
            u['pair_ref']=us[(i+1)%len(us)]['unit_id']; u['meta']['pair_size']=len(us); paired+=1
# 追加到 units.jsonl + index
with open(f'{L2}/units.jsonl','a',encoding='utf-8') as fh:
    for u in units: fh.write(json.dumps(u,ensure_ascii=False,sort_keys=True)+"\n")
with open(f'{L2}/index/l2.jsonl','a',encoding='utf-8') as fh:
    for u in units:
        fh.write(json.dumps({"unit_id":u["unit_id"],"kb_type":u["kb_type"],"anchor":u["anchor"],
            "source_sha256":u["source_sha256"],"char_count":u["char_count"]},ensure_ascii=False,sort_keys=True)+"\n")
d=f'{L2}/by_kb/2_内部正负样本库'; os.makedirs(d,exist_ok=True)
grp=collections.defaultdict(list)
for u in units: grp[u['resource_id']].append(u)
for rid,us in grp.items():
    json.dump({"resource_id":rid,"kb_type":"internal_sample","source_sha256":us[0]['source_sha256'],
               "unit_count":len(us),"units":us},open(f'{d}/{rid}.json','w',encoding='utf-8'),ensure_ascii=False,indent=1)
# 台账追加
with open(f'{L2}/manifest_l2.jsonl','a',encoding='utf-8') as fh:
    for rid,us in grp.items():
        fh.write(json.dumps({"resource_id":rid,"source_sha256":us[0]['source_sha256'],
            "splitter_version":SV,"kb_type":"internal_sample","result":"split",
            "unit_count":len(us),"observed_at":RUN},ensure_ascii=False,sort_keys=True)+"\n")
json.dump({"units":len(units),"paired":paired,"pairs":{k:len(v) for k,v in byp.items()}},
          open('kb/.work/l2_pairs.json','w',encoding='utf-8'),ensure_ascii=False)
print(f"专家修订 revision_pair 单元 {len(units)} | 配对互指 {paired} | 组 {len(byp)}")
