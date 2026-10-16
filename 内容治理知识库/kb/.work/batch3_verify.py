#!/usr/bin/env python3
"""batch3 验收证据（只读，独立于生成本批产物的脚本）。"""
import json, glob, os, collections, re

KB = "kb"
L0 = f"{KB}/l0"
W = f"{KB}/.work/batch3"
RUN = "20260924-1000"

def load_ledger():
    L, order = {}, []
    for l in open(f"{L0}/manifest.jsonl", encoding="utf-8"):
        if l.strip():
            d = json.loads(l)
            if d["resource_key"] not in L:
                order.append(d["resource_key"])
            L[d["resource_key"]] = d
    return L, order

def line(t):
    print("\n" + "=" * 78 + f"\n### {t}\n" + "=" * 78)

L, order = load_ledger()
live = {k: v for k, v in L.items() if v["status"] != "retracted"}
recs = [json.loads(l) for l in open(f"{W}/材料收集.ndjson", encoding="utf-8") if l.strip()]
fr = json.load(open(f"{W}/field_roles_merge.json", encoding="utf-8"))
reg = json.load(open(f"{L0}/registry/kb.json", encoding="utf-8"))

line("C2/C3 入口筛选：纳入/排除对账 + 新增纳入记录清单")
inc = [r for r in recs if r.get("材料审核状态")]
exc = [r for r in recs if not r.get("材料审核状态")]
by = collections.Counter(("、".join(r["材料审核状态"]) if r.get("材料审核状态") else "空") for r in recs)
print(f"源侧记录总数            : {len(recs)}")
print(f"取值分布                : {dict(by)}")
print(f"纳入（!= 空）           : {len(inc)}  = 通过 {by['通过']} + 暂不采用 {by['暂不采用']}")
print(f"排除（== 空）           : {len(exc)}")
print(f"对账                    : {len(recs)} == {len(inc)} + {len(exc)}  ->  差额 {len(recs)-len(inc)-len(exc)}")
print()
print("本次新增纳入的记录（本批 observed_at 且为入口表记录）：")
newkeys = sorted(k for k, v in L.items()
                 if k.startswith("bitable:tblMGtPfe8ZUsEdP:rec") and v.get("observed_at") == RUN
                 and v["status"] != "retracted")
existing = sorted(k for k, v in L.items()
                  if k.startswith("bitable:tblMGtPfe8ZUsEdP:rec") and v.get("observed_at") != RUN)
print(f"  本批新增 {len(newkeys)} 条；既有（未重发）{len(existing)} 条；合计 {len(newkeys)+len(existing)} 条 == 纳入 {len(inc)}")
for k in newkeys:
    rid = k.split(":")[-1]
    r = next(x for x in recs if x["record_id"] == rid)
    print(f"    {rid}  材料审核状态={r['材料审核状态']}  知识库分类={r['知识库分类']}"
          f"  -> kb_type={L[k]['kb_type']} (rule {L[k]['matched_rule']})  目录={reg['dir_map_reverse'][L[k]['kb_type']]}")
print()
print("新增纳入记录的材料链接子资源：")
for k, v in sorted(L.items()):
    if v.get("observed_at") == RUN and v.get("field_name") == "材料链接":
        print(f"    {k}  -> kb_type={v['kb_type']} (rule {v['matched_rule']})  目录={reg['dir_map_reverse'][v['kb_type']]}"
              f"  sha256_state={v['sha256_state']}")

line("D field_roles")
print(f"D1 补全前字段数                 : {fr['field_roles_before_count']}")
print(f"D2 补全后字段数                 : {fr['field_roles_after_count']}")
print(f"   （其中 L2 实测论域内）        : {len(fr['field_roles_l2_universe_only'])}")
print(f"D3 L2 里实测出现的字段总数       : {fr['coverage']['universe']}")
print(f"   口径 A entry heading_path    : {fr['l2_universe']['counts']['A']}")
print(f"   口径 B revision_pair fields  : {fr['l2_universe']['counts']['B']}")
print(f"   口径 C 切分资源源字段         : {fr['l2_universe']['counts']['C']}")
print(f"D4 仍无角色的字段               : {fr['coverage']['missing_count']}  {fr['coverage']['missing']}")
print(f"D5 覆盖项 6 -> {len(fr['overrides_after'])}，新增：")
for k, v in fr["new_overrides"].items():
    tn, fn = k.split("::", 1)
    c = next(x for x in fr["conflicts"] if x["table"] == tn and x["field"] == fn)
    print(f"     {k} = {v}   （各表实测隐含 {c['tables_implied']}）")
print("   既有 6 项（未改）:")
for k, v in fr["overrides_before"].items():
    print(f"     {k} = {v}")
print("   实测与 L3 content 判断有出入、留待 L3 复核:")
for n in fr["evidence_notes"]:
    print(f"     {n['field']} {n['tables']}")
print("   角色分布:", dict(collections.Counter(fr["field_roles_after"].values())))
print("   实测论域 88 字段全表:")
for f, r in fr["field_roles_l2_universe_only"].items():
    print(f"     {r:11s} {f}")
l3 = json.load(open(f"{KB}/l3/registry/l3.json", encoding="utf-8"))
print(f"D6 L3 registry merged_into_l0 : state={l3['filter_rules']['step1_metadata']['merged_into_l0']['state']!r}")

line("E 重跑扫描器 / G6 路径")
print(f"E1 run_id={RUN}  scanner_version=0.6")
scv = collections.Counter(v.get("scanner_version") for v in L.values())
print(f"   台账最新行的 scanner_version 分布: {dict(scv)}")
print(f"E2 台账按 key 取最新一行        : {len(L)}")
print(f"   其中 status=retracted        : {sum(1 for v in L.values() if v['status']=='retracted')}")
print(f"   有效最新行（非 retracted）    : {len(live)}")
files = {}
for d in reg["dir_map"]:
    for p in glob.glob(f"{L0}/{d}/*.json"):
        j = json.load(open(p, encoding="utf-8"))
        files[j["resource_key"]] = (p, j)
print(f"E3 资源文件总数                 : {len(files)}")
print(f"E4 E2(有效) vs E3               : {len(live)} vs {len(files)}  差额 {len(live)-len(files)}")
print(f"E5 index/l0.jsonl 行数          : {sum(1 for l in open(f'{L0}/index/l0.jsonl', encoding='utf-8') if l.strip())}")
mis = []
for k, (p, j) in files.items():
    d = os.path.basename(os.path.dirname(p))
    led = L.get(k)
    if led is None or j["kb_type"] != led["kb_type"] or reg["dir_map"][d] != j["kb_type"]:
        mis.append(k)
print(f"E6 三方一致不符数               : {len(mis)}  {mis}")
print(f"E7 库目录条数                   : " + "  ".join(
    f"{reg['dir_map'][d]}={len(glob.glob(f'{L0}/{d}/*.json'))}" for d in reg["dir_map"]))
print(f"   合计 {sum(len(glob.glob(f'{L0}/{d}/*.json')) for d in reg['dir_map'])}")

line("F 未改动证据")
print(f"F3 kb_version={reg['kb_version']!r}; versions.jsonl 版本行数="
      f"{sum(1 for l in open(f'{KB}/versions/versions.jsonl', encoding='utf-8') if l.strip() and not l.startswith('#'))}")

line("G1 unknown 清单")
unk = {k: v for k, v in live.items() if v["kb_type"] == "unknown"}
print(f"unknown 共 {len(unk)} 条")
for k, v in unk.items():
    src = (files.get(k, (None, {}))[1] or {}).get("kb_type_source")
    print(f"  {k}  | {v['source_kind']} | {v.get('table_name')} | {v['matched_rule']} | {src}")

line("G2 规则命中（全量，按台账最新行）与 0 命中规则")
hits = collections.Counter(v["matched_rule"] for v in live.values() if v.get("matched_rule"))
for r in reg["rules"]:
    e = "生效" if r.get("enabled", True) else "停用"
    print(f"  {r['id']:4s} {e}  match_type={r['match_type']:12s} scope={r.get('scope_table') or '-':24s} "
          f"-> {r['kb_type']:18s} 全量命中={hits.get(r['id'],0)}  本批新资源命中="
          f"{collections.Counter(v['matched_rule'] for k,v in live.items() if v.get('observed_at')==RUN and v.get('matched_rule')).get(r['id'],0)}")
print("0 命中的规则:", [r["id"] for r in reg["rules"] if hits.get(r["id"], 0) == 0])
print("no_rule_matched 的资源:", [k for k, v in live.items() if not v.get("matched_rule")])
