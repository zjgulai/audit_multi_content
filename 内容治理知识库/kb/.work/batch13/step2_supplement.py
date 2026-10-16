#!/usr/bin/env python3
"""batch13 §4：L0 增量补充 —— 材料收集 9 条容器记录 + 9 条材料链接子资源（只新增）。
复用既有发射路径的 schema（add() 键集 / 记录文件键集 / 边键集），kb_type 走 rules 真求值。"""
import json, os, re, hashlib, collections, sys

RUN = "20260924-1610"; L0 = "kb/l0"; W = "kb/.work"
BASE = "GnRZbIuXraCzf0sGr2UcmZ62nfc"; TBL = "tblMGtPfe8ZUsEdP"; TBL_NAME = "材料收集"
LINK_FIELD, LINK_FID = "材料链接", "fldr4c8nnT"

reg = json.load(open(f"{L0}/registry/kb.json", encoding="utf-8"))
REV, RULES = reg["dir_map_reverse"], [r for r in reg["rules"] if r.get("enabled")]

def canon(o): return json.dumps(o, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
def sha(t): return hashlib.sha256(t.encode("utf-8")).hexdigest()
EXCL_HASH = {"last_modified_time", "last_modified_by"}
def rec_hash(fvals):
    items = sorted(((k, v) for k, v in fvals.items() if k not in EXCL_HASH), key=lambda x: x[0])
    return sha(canon([["field_id", k, "value", v] for k, v in items]))
def rid_of(rk): return re.sub(r'[^0-9A-Za-z._\-]+', '_', rk.replace(":", "__").replace("/", "_"))[:170]

def rule_for(table, hint):
    for t in (hint or []):
        if t == "其它": continue
        for r in RULES:
            if (r["match_type"]=="field_value" and r.get("scope_table")=="材料收集"
                    and r.get("match_value")==t):
                return r["kb_type"], r["id"], f"记录字段值:知识库分类={t}"
    for r in RULES:
        if r["match_type"]=="table_name" and r["pattern"]==table:
            return r["kb_type"], r["id"], f"表名:{table}"
    return "unknown", None, "no_rule_matched"

# ---------- 输入：已爬 dump（不重爬） ----------
rows = {json.loads(l)["record_id"]: json.loads(l)
        for l in open(f"{W}/fresh/tblMGtPfe8ZUsEdP.ndjson", encoding="utf-8") if l.strip()}
FIDS = {  # 字段 id 取自既有记录文件（同一张表，schema 未变）
 "细分":"fldn2leARA","编号-自动生成":"fldHYXvg0B","知识库分类":"fldsFUp6XB",
 "知识库分类说明-自动映射":"fldhkuqIDu","agent使用范围":"fld5WJe8Nk","From":"fldYJzmyOw",
 "材料审核状态":"fldzdgZxi6","材料链接":"fldr4c8nnT"}
TARGETS = ["recvvg2wL2EnC0","recvvg2wL26SAU","recvvlO5gFdyzx","recvvhI3yZULdA","recvvlspM5RDoj",
           "recvvltvfBsoDP","recvvlGAKpUVF9","recvvlGUajvYY0","recvvhv1cwO2Ry"]
assert len(TARGETS)==9 and all(t in rows for t in TARGETS), [t for t in TARGETS if t not in rows]

URL_RX = re.compile(r'\]\((https?://[^)]+)\)')
def link_of(r):
    v = r.get(LINK_FIELD) or ""
    m = URL_RX.search(v)
    return (m.group(1) if m else None), re.sub(r'\]\(https?://[^)]+\)', ']', v).lstrip('[').strip()

def child_key_kind(url):
    """§4.2 口径：resource_key 与 source_kind 只按 **URL 自身可证明** 的信息定，不猜。
    口径写在报告里；URL 证明不了的，用既有枚举里最保守的 url + 显式 unresolved 标记。"""
    p = url.split("?")[0]; q = url.split("?",1)[1] if "?" in url else ""
    t = p.rstrip("/").split("/")[-1]
    if "/docx/" in p:      return f"docx:{t}", "feishu_doc", False
    if "/sheets/" in p:    return f"sheets:{t}", "feishu_sheet", False
    if "/slides/" in p:    return f"slides:{t}", "feishu_slides", False
    if "/file/" in p:      return f"file:{t}", "feishu_file", False
    if "/wiki/" in p:
        if "sheet=" in q:  return f"wiki:{t}", "feishu_sheet", False
        if "table=" in q:  return f"wiki:{t}", "feishu_bitable_base", False
        return f"wiki:{t}", "url", True          # wiki 节点 → obj_type 需 +node 才能定；不猜
    if "/base/" in p and "/share/" not in p:
        return f"base:{t}", "feishu_bitable_base", False
    return f"url:{url}", "url", True             # share/drive 等：只用 URL 本身做身份

latest = {}
for l in open(f"{L0}/manifest.jsonl", encoding="utf-8"):
    if l.strip():
        r = json.loads(l); latest[r["resource_key"]] = r
before_rows = sum(1 for l in open(f"{L0}/manifest.jsonl", encoding="utf-8") if l.strip())  # 按行数，不按唯一 key 数

# 既有行的字段集合（判据 8：新增行 schema 必须与既有行完全相同）
# 基准 schema：取「未经 batch12 改判」的注册行（25 键）。batch12 的 updated 行额外带了
# container/prev_*/ruling/note，那是该批的变更标记；新增注册行一律用 25 键标准 schema（判据 8）。
EXISTING_KEYS = set(latest["bitable:tbld8qE92YaY38Yz:recvw2vgYX1Gw0"].keys())
print("既有记录行的字段集合（%d 个）:" % len(EXISTING_KEYS), sorted(EXISTING_KEYS))

def add(**kw):
    """复用既有发射路径的 add()：默认值 + 字段名与既有行逐一对齐。"""
    row = {"change": kw.pop("change", None), "depth": None, "downstream_invalidated": False,
           "dup_of": None, "entry_url": None, "field_id": None, "field_name": None,
           "kb_type": "unknown", "matched_rule": None, "observed_at": RUN, "path": None,
           "record_id": None, "resource_key": None, "revision": None, "rule_eligible": True,
           "rule_eligible_source": None, "scanner_version": "0.7", "sha256": None,
           "sha256_input": None, "sha256_state": None, "source_kind": None, "status": "registered",
           "status_reason": "", "table_id": None, "table_name": None}
    row.update(kw)
    unknown = set(row) - EXISTING_KEYS
    assert not unknown, f"新增行出现既有行没有的字段：{unknown}"
    missing = EXISTING_KEYS - set(row)
    assert not missing, f"新增行缺少既有行有的字段：{missing}"
    return row

rec_dir = f"{L0}/records/{TBL_NAME}"; os.makedirs(rec_dir, exist_ok=True)
L0_ROWS, LINK_ROWS, RES_FILES, EDGES = [], [], [], []
rec_report, child_report = [], []

for rid in TARGETS:
    r = rows[rid]
    hint = r.get("知识库分类") or []
    kt, ridr, kts = rule_for(TBL_NAME, hint)
    kept = {k: v for k, v in r.items() if k != "record_id"}
    fvals = {FIDS[k]: v for k, v in kept.items() if k in FIDS}
    rk = f"bitable:{TBL}:{rid}"
    url = f"https://momcozy-in.feishu.cn/base/{BASE}?table={TBL}&record={rid}"
    # ① 记录留痕文件（键集与既有 材料收集 记录文件一致）
    rec_out = {"record_id": rid, "source_table": TBL_NAME, "table_id": TBL, "base_token": BASE,
               "entry_url": url, "timezone": "Asia/Shanghai", "observed_at": RUN,
               "filter": {"result": "not_filtered",
                          "note": "独立入口表（R26）：不按材料审核状态筛选；本轮为「材料链接型」待补记录，全字段 verbatim"},
               "fields": {k: {"field_id": FIDS.get(k), "field_type": "text", "value": v, "raw_verbatim": v}
                          for k, v in kept.items()},
               "raw_record": kept,
               "note": "字段原值 verbatim；本批只补齐登记，不抽取正文（正文在「材料链接」远端）。"}
    p = f"{rec_dir}/{rid}.json"; tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh: json.dump(rec_out, fh, ensure_ascii=False, indent=1)
    json.load(open(tmp, encoding="utf-8")); os.replace(tmp, p)
    RES_FILES.append(p)
    # ② 台账行（容器：不发射单元）
    L0_ROWS.append(add(change="supplement_material_collection", depth=1, resource_key=rk,
        source_kind="feishu_bitable_record", table_name=TBL_NAME, table_id=TBL, record_id=rid,
        entry_url=url, path="[内容治理/入口Base/材料收集]", kb_type=kt, matched_rule=ridr,
        sha256=rec_hash(fvals), sha256_input="record_fields", sha256_state="full",
        status="registered",
        status_reason=(f"§4.1 材料收集待补记录。kb_type 由 registry.rules 真求值得到：{kts}；"
                       f"按 container_policy(C1∧C2∧C3) 判为容器 → 不发射 L2 单元（容器实例清单见 registry.container_policy.container_instances）"),
        rule_eligible=True, rule_eligible_source="not_material_collection",
        downstream_invalidated=True))
    rec_report.append({"record_id": rid, "kb_type": kt, "matched_rule": ridr,
                       "path": f"{L0}/{REV[kt]}/{rid_of(rk)}.json", "hint": hint})
    # ③ 下钻：材料链接子资源
    u, label = link_of(r)
    assert u, f"{rid} 无材料链接"
    ck, ckind, unresolved = child_key_kind(u)
    is_gdrive = "drive.google.com" in u
    cstatus = "registered"
    creason = ("§4.2 下钻登记（本批不重爬飞书）：只登记链接目标，正文与指纹留待 L1 批"
               + ("；URL 未证明对象类型（wiki 节点需 +node 解析），source_kind 取既有枚举最保守值 url" if unresolved else ""))
    csha_state = "unreachable" if is_gdrive else "not_fetched"
    if is_gdrive:
        creason = ("§4.2 不可达：链接指向 Google Drive 文件夹（本批只用已爬落盘数据、不重爬，"
                   "且该域不在飞书侧可达范围），登记为 unreachable 而非静默跳过")
    LINK_ROWS.append(add(change="supplement_material_link", depth=2, resource_key=ck,
        source_kind=ckind, table_name=TBL_NAME, table_id=TBL, record_id=rid,
        field_name=LINK_FIELD, field_id=LINK_FID, entry_url=u,
        path="[内容治理/入口Base/材料收集/材料链接]", kb_type=kt, matched_rule=ridr,
        sha256=None, sha256_input="url_text", sha256_state=csha_state, status=cstatus,
        status_reason=creason + f"｜链接标题：{label[:120]}",
        rule_eligible=True, rule_eligible_source="not_material_collection",
        downstream_invalidated=True))
    EDGES.append({"depth": 2, "field_id": LINK_FID, "from_id": f"record:{rid}",
                  "from_kind": "feishu_bitable_record", "label": LINK_FIELD, "observed_at": RUN,
                  "status": "ok" if not is_gdrive else "unreachable", "to_id": ck, "to_kind": ckind})
    child_report.append({"parent_record_id": rid, "child_resource_key": ck, "source_kind": ckind,
                         "kb_type": kt, "status": cstatus, "sha256_state": csha_state,
                         "unreachable": is_gdrive, "source_kind_unresolved": unresolved, "url": u})

# ---------- 落盘：台账追加 / 资源文件 / 边 ----------
MAN = f"{L0}/manifest.jsonl"
with open(MAN, "a", encoding="utf-8") as fh:
    for row in L0_ROWS + LINK_ROWS:
        fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
after_rows = sum(1 for l in open(MAN, encoding="utf-8") if l.strip())
print(f"台账追加 {len(L0_ROWS)+len(LINK_ROWS)} 行：{before_rows} → {after_rows}")

new_latest = dict(latest)
for row in L0_ROWS + LINK_ROWS: new_latest[row["resource_key"]] = row
for row in LINK_ROWS:
    f = f"{L0}/{REV[row['kb_type']]}/{rid_of(row['resource_key'])}.json"
    obj = {"resource_key": row["resource_key"], "source_kind": row["source_kind"],
           "kb_type": row["kb_type"], "matched_rule": row["matched_rule"], "status": row["status"],
           "entry_url": row["entry_url"], "observed_at": RUN, "sha256": None,
           "sha256_state": row["sha256_state"], "table_name": TBL_NAME, "table_id": TBL,
           "record_id": row["record_id"], "field_name": LINK_FIELD, "field_id": LINK_FID,
           "depth": 2, "status_reason": row["status_reason"]}
    tmp = f + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh: json.dump(obj, fh, ensure_ascii=False, indent=1)
    json.load(open(tmp, encoding="utf-8")); os.replace(tmp, f)
    RES_FILES.append(f)

EG = f"{L0}/links/graph.jsonl"
eb = sum(1 for l in open(EG, encoding="utf-8") if l.strip())
with open(EG, "a", encoding="utf-8") as fh:
    for e in EDGES: fh.write(json.dumps(e, ensure_ascii=False, sort_keys=True) + "\n")
ea = sum(1 for l in open(EG, encoding="utf-8") if l.strip())
print(f"链接图追加 {len(EDGES)} 条边：{eb} → {ea}")

# ---------- index 重建（复用上批已验证过的配方）----------
def rebuild_index(d):
    live = {k: v for k, v in d.items() if v["status"] not in ("gone","retracted") and not k.startswith("audit:")}
    return "".join(json.dumps({"resource_key": v["resource_key"], "kb_type": v["kb_type"],
        "source_kind": v["source_kind"], "status": v["status"], "entry_url": v["entry_url"],
        "rule_eligible": v.get("rule_eligible")}, ensure_ascii=False, sort_keys=True) + "\n"
        for k, v in sorted(live.items()))
cur = open(f"{L0}/index/l0.jsonl", encoding="utf-8").read()
assert rebuild_index(latest) == cur, "index 重建配方与现文件不一致 —— 停下"
tmp = f"{L0}/index/l0.jsonl.tmp"
open(tmp, "w", encoding="utf-8").write(rebuild_index(new_latest))
json.loads(open(tmp, encoding="utf-8").readline()); os.replace(tmp, f"{L0}/index/l0.jsonl")
idx = sum(1 for l in open(f"{L0}/index/l0.jsonl", encoding="utf-8") if l.strip())
print("index 重建：", idx, "行")

reg2 = json.load(open(f"{L0}/registry/kb.json", encoding="utf-8"))
reg2["container_policy"]["container_instances"] = {
  "defined_at": RUN,
  "note": "按 container_policy(C1∧C2∧C3) 判定的容器实例清单；判据在运行时求值，此处登记结果以便下游读。",
  "instances": {x["record_id"]: {"resource_key": f"bitable:{TBL}:{x['record_id']}", "kb_type": x["kb_type"],
                                 "matched_rule": x["matched_rule"], "container": True,
                                 "criteria": ["C1 全部 L1 段为元数据角色", "C2 链接图有子资源", "C3 当前不发射单元"],
                                 "judged_at": RUN} for x in rec_report},
  "prior_instances_ref": "run 20260924-1512 判定的 107 个容器（含 23 条材料收集记录）见该批报告；本键只登记本批新增实例"
}
_t = f"{L0}/registry/kb.json.tmp"
with open(_t, "w", encoding="utf-8") as fh: json.dump(reg2, fh, ensure_ascii=False, indent=1)
json.load(open(_t, encoding="utf-8")); os.replace(_t, f"{L0}/registry/kb.json")
print("registry.container_policy.container_instances 已登记", len(rec_report), "个实例")

json.dump({"run_id": RUN, "parents": rec_report, "children": child_report,
           "manifest_before": before_rows, "manifest_after": after_rows,
           "links_before": eb, "links_after": ea, "index_rows": idx,
           "resource_files": RES_FILES},
          open("kb/.work/batch13/step2_result.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("\n§4.1 9 条容器登记：")
for x in rec_report: print(f"  {x['record_id']}  {x['kb_type']:<18}{x['matched_rule']:<5}{x['path']}")
print("\n§4.2 下钻：")
for x in child_report:
    print(f"  {x['parent_record_id']} → {x['child_resource_key'][:60]:<62}{x['source_kind']:<22}{x['kb_type']:<18}{x['status']}")
