#!/usr/bin/env python3
"""§4 修正：资源文件名统一为既有约定 <source_kind>__<token|sanitized_url>.json，
并补写 9 条父记录的库目录资源文件（初版只写了记录留痕文件，漏了库目录文件）。"""
import json, os, re, hashlib
L0="kb/l0"; RUN="20260924-1610"
reg=json.load(open(f"{L0}/registry/kb.json",encoding="utf-8")); REV=reg["dir_map_reverse"]
R=json.load(open("kb/.work/batch13/step2_result.json",encoding="utf-8"))
rows=[json.loads(l) for l in open(f"{L0}/manifest.jsonl",encoding="utf-8") if l.strip()]
new={r["resource_key"]:r for r in rows if r.get("change") in
     ("supplement_material_collection","supplement_material_link")}
def rid_of(rk): return re.sub(r'[^0-9A-Za-z._\-]+','_',rk.replace(":","__").replace("/","_"))[:170]
def fname(row):
    """既有约定：<source_kind>__<token 或 sanitized url>.json"""
    rk=row["resource_key"]; sk=row["source_kind"]
    if rk.startswith("url:"):  return f"{sk}__{rid_of(rk)[len('url__'):]}.json"
    if rk.startswith("bitable:") and row.get("record_id"):
        # 既有约定：feishu_bitable_record__<table_id>__<record_id>.json
        return f"{sk}__{row['table_id']}__{row['record_id']}.json"
    return f"{sk}__{rk.split(':',1)[1]}.json"

renamed=[]; wrote=[]
for rk,row in sorted(new.items()):
    d=f"{L0}/{REV[row['kb_type']]}"; os.makedirs(d,exist_ok=True)
    sk=row["source_kind"]
    want=f"{d}/{fname(row)}"
    obj={"resource_key":rk,"source_kind":row["source_kind"],"kb_type":row["kb_type"],
         "matched_rule":row["matched_rule"],"status":row["status"],"entry_url":row["entry_url"],
         "observed_at":RUN,"sha256":row["sha256"],"sha256_state":row["sha256_state"],
         "table_name":row["table_name"],"table_id":row["table_id"],"record_id":row["record_id"],
         "field_name":row["field_name"],"field_id":row["field_id"],"depth":row["depth"],
         "status_reason":row["status_reason"]}
    # 清掉初版错名文件
    for old in (f"{d}/{rid_of(rk)}.json",
                f"{d}/{row['source_kind']}__{row.get('table_id')}:{row.get('record_id')}.json",
                f"{d}/{row['source_kind']}__{rid_of(rk)}.json"):
        if os.path.exists(old) and os.path.abspath(old)!=os.path.abspath(want):
            os.remove(old); renamed.append((old,want))
    tmp=want+".tmp"
    with open(tmp,"w",encoding="utf-8") as fh: json.dump(obj,fh,ensure_ascii=False,indent=1)
    json.load(open(tmp,encoding="utf-8")); os.replace(tmp,want)
    wrote.append(want)
print("删除初版错名文件:",len(renamed))
for a,b in renamed: print("   -",a,"\n     →",b)
print("写出/覆盖:",len(wrote))
dirs={d:len(os.listdir(f"{L0}/{d}")) for d in ("1_外部标准库","2_内部正负样本库","3_措辞表达库","4_产品描述库","9_未归类")}
print("L0 库目录:",dirs,"合计",sum(dirs.values()))
# 父记录的库目录文件单独核
par=[r for r in new.values() if r.get("change")=="supplement_material_collection"]
print("\n9 条父记录 → 库目录文件：")
for r in sorted(par,key=lambda x:x["record_id"]):
    p=f"{L0}/{REV[r['kb_type']]}/{fname(r)}"
    print(f"   {r['record_id']}  {r['kb_type']:<18}{p}  {'OK' if os.path.exists(p) else 'MISS'}")
json.dump({"renamed":renamed,"written":wrote,"l0_dirs":dirs,"total":sum(dirs.values())},
          open("kb/.work/batch13/step2b_result.json","w",encoding="utf-8"),ensure_ascii=False,indent=1)
