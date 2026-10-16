#!/usr/bin/env python3
"""§1/§2 比对复核：10 张表 dump / L0 / 待补 / L0多出。只读。"""
import json, os, collections
RUN="20260924-1610"; L0="kb/l0"
W="kb/.work"
def nd(p): return [json.loads(l) for l in open(p,encoding="utf-8") if l.strip()]
def n(p): return len(nd(p))
latest={}
for l in open(f"{L0}/manifest.jsonl",encoding="utf-8"):
    if l.strip():
        r=json.loads(l); latest[r["resource_key"]]=r
live={k:v for k,v in latest.items() if v["status"] not in ("gone","retracted")}
def _rec_level(d):
    return {k for k,v in d.items() if v.get("table_id")==tid and v.get("record_id")
            and v.get("field_id") is None and v.get("field_name") is None}
def l0_recs(tid):
    """只数「记录级」资源行（field_id/field_name 皆空），不含附件与材料链接子资源。"""
    return _rec_level(live)
def l0_recs_all(tid):
    """含 gone 存量（任务书 §2 的 L0 列口径）—— 只排除 retracted。"""
    return _rec_level({k:v for k,v in latest.items() if v["status"]!="retracted"})
def l0_atts(tid): return {k for k,v in live.items() if v.get("table_id")==tid and v.get("field_id")}
# 专家修订汇总表 / 广告文案明细：p1 + p2 两段
p12=lambda a,b: n(a)+n(b)
TABLES=[
 ("专家修订汇总表","tbl8AI00JZO1iZtp",["full/tbl8AI00JZO1iZtp.p1.ndjson","full/tbl8AI00JZO1iZtp.p2.ndjson"]),
 ("广告文案明细","tblcbk4XiW6471YN",["full/tblcbk4XiW6471YN.p1.ndjson","full/tblcbk4XiW6471YN.p2.ndjson"]),
 ("正面和负面样本","tbld8qE92YaY38Yz",["batch4/正面和负面样本.ndjson"]),
 ("风险文案改写建议库（分型号分渠道）","tblLxUfPz4Wqp2na",["bases/tblLxUfPz4Wqp2na.ndjson"]),
 ("数据表","tblGFyycMc45RMga",["bases/tblGFyycMc45RMga.ndjson"]),
 ("材料收集","tblMGtPfe8ZUsEdP",["/fresh/tblMGtPfe8ZUsEdP.ndjson".lstrip("/")]),
 ("品线内容边界规则库","tblD1MiUK1v5fdjD",["bases/tblD1MiUK1v5fdjD.ndjson"]),
 ("W1卖点表达边界（品线反馈0910）","tblqUTAKFkWheU49",["bases/tblqUTAKFkWheU49.ndjson"]),
 ("内容公式（仅供参考）","tblVdl0jdK9G4ld3",["bases/tblVdl0jdK9G4ld3.ndjson"]),
 ("知识库分类说明","tblZP8jG4tiUL98C",["fresh/tblZP8jG4tiUL98C.ndjson"]),
]
print(f"{'表':<30}{'dump':>6}{'L0':>6}{'待补':>6}{'L0多出':>7}")
out=[]
for name,tid,dumps in TABLES:
    dump=" + ".join(dumps)
    src=set()
    for d in dumps:
        src |= {json.loads(l)["record_id"] for l in open(f"{W}/{d}",encoding="utf-8") if l.strip()}
    l0=l0_recs(tid); l0all=l0_recs_all(tid)
    l0ids={k.split(":")[-1] for k in l0}; l0allids={k.split(":")[-1] for k in l0all}
    pending=sorted(src-l0ids); extra=sorted(l0allids-src)
    print(f"{name:<30}{len(src):>6}{len(l0allids):>6}{len(pending):>6}{len(extra):>7}")
    if pending: print("     待补:",pending)
    out.append({"table":name,"table_id":tid,"dump":dump,"dump_count":len(src),
                "l0_count":len(l0ids),"l0_count_incl_gone":len(l0allids),
                "pending":pending,"l0_extra":extra,
                "gone_legacy":len(l0allids)-len(l0ids)})
excl={"table":"飞书侧-50条规则","table_id":"tblXsrMVkDNZ3oW8","dump":"fresh/tblXsrMVkDNZ3oW8.ndjson",
      "dump_count":n(f"{W}/fresh/tblXsrMVkDNZ3oW8.ndjson"),"l0_count":None,"pending":None,
      "excluded":True,"reason":"§1：整体除外 —— 不读、不比对、不入库"}
out.append(excl)
print(f"{'飞书侧-50条规则（除外）':<30}{excl['dump_count']:>6}{'—':>6}{'—':>6}{'—':>7}")
json.dump({"run_id":RUN,"tables":out},open("kb/.work/batch13/compare.json","w",encoding="utf-8"),ensure_ascii=False,indent=1)
tot=sum(len(t["pending"]) for t in out if t.get("pending"))
print("\n待补合计:",tot)
