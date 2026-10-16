#!/usr/bin/env python3
"""batch3 · L0 范围冻结（scanner 0.5 → 0.6）。

四件事：① 规则库整体不纳入（停用 R6–R10 + 存量 16 条 retracted + 撤下钻边）
        ② 补登记「内容公式（仅供参考）」整表（7 条，R18 → wording）
        ③ 入口筛选口径 材料审核状态 == 通过 → != 空
        ④ field_roles 收归 L0（合并 L3 补丁角色表）
写入范围：kb/l0/**（资源文件追加 / 台账追加 / index 重建 / registry / links 追加 / runs）、kb/l0/_archive/。
源侧全程只读。kb/l1 及以下只读（唯一例外：按任务第 4 件要求在 kb/l3/registry/l3.json 追加「已并入 L0」标注）。
"""
import json, os, re, glob, hashlib, shutil, collections, sys, subprocess

RUN = "20260924-1000"
SCANNER = "0.6"
L0 = "kb/l0"
W = "kb/.work/batch3"
ARCHIVE = f"{L0}/_archive/rulelib-excluded-{RUN}"
ENTRY_BASE, ENTRY_TBL, ENTRY_TBL_NAME = "GnRZbIuXraCzf0sGr2UcmZ62nfc", "tblMGtPfe8ZUsEdP", "材料收集"
FORMULA_BASE, FORMULA_TBL, FORMULA_TBL_NAME = "SKkkbdZi9aRuMzs7ob0cpSYHnQg", "tblVdl0jdK9G4ld3", "内容公式（仅供参考）"
EXCL = {"last_modified_time", "last_modified_by"}

registry = json.load(open(f"{L0}/registry/kb.json", encoding="utf-8"))
FREQ = json.load(open(f"{W}/field_roles_merge.json", encoding="utf-8"))
DIR_MAP, REV = registry["dir_map"], registry["dir_map_reverse"]

# ---------------------------------------------------------------- 既有状态
manifest_path = f"{L0}/manifest.jsonl"
before_lines = [l for l in open(manifest_path, encoding="utf-8") if l.strip()]
before_rows = [json.loads(l) for l in before_lines]
latest_before = {}
for r in before_rows:
    latest_before[r["resource_key"]] = r

def sha(t):
    return hashlib.sha256(t.encode("utf-8")).hexdigest()

def canon(o):
    return json.dumps(o, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

def norm_text(s):
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    s = "\n".join(l.rstrip() for l in s.split("\n"))
    return re.sub(r"\n{3,}", "\n\n", s).strip()

def rec_hash(fvals):
    items = sorted(((k, v) for k, v in fvals.items() if k not in EXCL), key=lambda x: x[0])
    return sha(canon([["field_id", k, "value", v] for k, v in items]))

def slug(u):
    s = re.sub(r'^https?://', '', u)
    return re.sub(r'[^0-9A-Za-z._\-]+', '_', s).strip('_')[:90]

def fname(resource_key, source_kind):
    if resource_key.startswith("url:"):
        return f"url__{slug(resource_key[4:])}.json"
    ident = resource_key.split(":", 1)[1].replace(":", "__").replace("/", "_")
    return f"{source_kind}__{ident}.json"

OPS = []          # 外部调用台账
def op(kind, nature, target, note):
    OPS.append((kind, nature, target, note))

# ---------------------------------------------------------------- 规则求值（0.6：跳过停用规则）
DISABLED = {"R6", "R7", "R8", "R9", "R10"}
ACTIVE_RULES = [r for r in registry["rules"] if r["id"] not in DISABLED]
RULE_HITS = collections.Counter()

def rule_for(table, hint=None, field_name=None, scope_table=None, scoped=None):
    for t in (hint or []):
        if t == "其它":
            continue
        for r in ACTIVE_RULES:
            if (r["match_type"] == "field_value" and r.get("scope_table") == ENTRY_TBL_NAME
                    and r.get("match_value") == t):
                RULE_HITS[r["id"]] += 1
                return r["kb_type"], r["id"], f"记录字段值:知识库分类={t}"
    for fnam, fval in (scoped or {}).items():
        for r in ACTIVE_RULES:
            if (r["match_type"] == "field_value" and r.get("scope_table") == scope_table
                    and r.get("pattern") == fnam and r.get("match_value") == fval):
                RULE_HITS[r["id"]] += 1
                return r["kb_type"], r["id"], f"记录字段值:{fnam}={fval}"
    if field_name:
        for r in ACTIVE_RULES:
            if r["match_type"] == "field_name" and r["pattern"] == field_name:
                RULE_HITS[r["id"]] += 1
                return r["kb_type"], r["id"], f"字段名:{field_name}"
    for r in ACTIVE_RULES:
        if r["match_type"] == "table_name" and r["pattern"] == table:
            if r.get("scope_table") and r["scope_table"] != table:
                continue
            RULE_HITS[r["id"]] += 1
            return r["kb_type"], r["id"], f"表名:{table}"
    RULE_HITS["(no_rule_matched)"] += 1
    return "unknown", None, "no_rule_matched"


def is_container(registry, resource_key, table_name=None):
    """§6.3-2 container_policy：容器 = 不发射单元。判据全部来自 registry，不硬编码表名。
    这里只做「可静态判定」的部分（C3：当前不发射单元）；C1/C2 需要 L1 段与链接图，
    由 kb/.work/batch12/step2b_container_shadow.py 在批内一次性判定并落台账。
    """
    pol = (registry or {}).get("container_policy") or {}
    if not pol:
        return False
    # 运行时若拿不到 L1 段/链接图，保守返回 None，由批内脚本回填（不猜）
    return None


# ================================================================ 读源（只读）
op("base +table-list", "read", "GnRZbIuXraCzf0sGr2UcmZ62nfc", "入口 Base 表清单：4 张表")
op("base +table-list", "read", "Lk3Qb8y2QaVyZns6gprcVNE9nA0", "广告文案风控库 表清单：4 张表")
op("base +table-list", "read", "N2qkb2YxuatqGLsa4U4cFQxgnCe", "外部资料库 表清单：1 张表")
op("base +table-list", "read", "SKkkbdZi9aRuMzs7ob0cpSYHnQg", "内容公式与专家修订库 表清单：2 张表")
op("base +field-list", "read", f"{ENTRY_TBL} 材料收集 / {FORMULA_TBL} 内容公式（仅供参考）", "8 字段 / 2 字段 schema")
op("base +record-list", "read", "材料收集（tblMGtPfe8ZUsEdP）", "32 条记录全字段（不按视图、不加视图筛选）")
op("base +record-list", "read", "内容公式（仅供参考）（tblVdl0jdK9G4ld3）", "7 条记录全字段")
op("base +record-list", "read", "正面和负面样本（tbld8qE92YaY38Yz）", "201 条记录 id（仅用于差集核对，未登记）")
op("wiki +node-get", "read", "EL1nw9zdyinX2iklXfLco216niM", "新增纳入记录 recvvg2wL2qE3K 的材料链接节点")
op("docs +fetch", "read", "wiki/EL1nw9zdyinX2iklXfLco216niM", "取正文计算 sha256(doc_text)")
op("docs +fetch", "read", "wiki/QX0Yw2neriOdA3k1giBciQDsn2c", "指纹规范化口径复核（复算旧资源 sha256，一致）")
op("HTTP GET", "read", "https://support.momcozy.com/", "新增纳入记录 recvw2dyVUVWxg 的材料链接")
op("本地只读", "read", "kb/l0/**, kb/l2/**, kb/.work/**", "台账/记录/边/registry/缓存，无写操作")

parent = [json.loads(l) for l in open(f"{W}/材料收集.ndjson", encoding="utf-8") if l.strip()]
formula = [json.loads(l) for l in open(f"{W}/内容公式（仅供参考）.ndjson", encoding="utf-8") if l.strip()]
fmeta_entry = json.load(open(f"{W}/fields_tblMGtPfe8ZUsEdP.json", encoding="utf-8"))["data"]["fields"]
fmeta_formula = json.load(open(f"{W}/fields_tblVdl0jdK9G4ld3.json", encoding="utf-8"))["data"]["fields"]
fid_entry = {f["name"]: f["id"] for f in fmeta_entry}
fid_formula = {f["name"]: f["id"] for f in fmeta_formula}
doc_el = json.load(open(f"{W}/fetch_EL1nw9.json", encoding="utf-8"))["data"]["document"]
node_el = json.load(open(f"{W}/node_EL1nw9.json", encoding="utf-8"))["data"]

# ================================================================ 件1：规则库整体不纳入
RULELIB = sorted(k for k, v in latest_before.items() if v.get("table_name") == "规则库")
assert len(RULELIB) == 16, f"规则库存量资源数不是 16，而是 {len(RULELIB)}"

lib_dirs = [DIR_MAP[d] and d for d in DIR_MAP]
file_index = {}
for d in DIR_MAP:
    for p in glob.glob(f"{L0}/{d}/*.json"):
        try:
            j = json.load(open(p, encoding="utf-8"))
        except Exception:
            continue
        file_index[j["resource_key"]] = p

os.makedirs(ARCHIVE, exist_ok=True)
archived = []
for k in RULELIB:
    src = file_index.get(k)
    if not src:
        archived.append({"resource_key": k, "moved": False, "reason": "库目录内找不到资源文件"})
        continue
    dst = f"{ARCHIVE}/{os.path.basename(src)}"
    shutil.move(src, dst)
    archived.append({"resource_key": k, "moved": True, "from": src, "to": dst,
                     "size": os.path.getsize(dst), "sha256_file": sha(open(dst, encoding="utf-8").read())})

# 撤下钻边（追加 tombstone）
graph_path = f"{L0}/links/graph.jsonl"
edges_before = [json.loads(l) for l in open(graph_path, encoding="utf-8") if l.strip()]
def edge_targets_rulelib(e):
    return e["to_id"] in set(RULELIB) | {"table:tblXsrMVkDNZ3oW8"} | \
           {k.replace(f"bitable:{ENTRY_BASE}:table:", "table:") for k in RULELIB}
tomb = []
for e in edges_before:
    if edge_targets_rulelib(e):
        t = dict(e)
        t["status"] = "retracted"
        t["tombstone"] = True
        t["retracted_by"] = RUN
        t["label"] = f"撤下钻边：目标表「规则库」按 excluded_by_scope 整体不纳入 [{RUN}]"
        tomb.append(t)

# ================================================================ 件3：入口筛选口径 + 新增纳入记录
FILTER_FIELD = "材料审核状态"
status_dist = collections.Counter()
matched, excluded = [], []
for r in parent:
    raw = r.get(FILTER_FIELD)
    vals = raw if isinstance(raw, list) else ([] if raw in (None, "") else [raw])
    key = "空" if not vals else "、".join(vals)
    status_dist[key] += 1
    (matched if vals else excluded).append(r)
matched_ids = {r["record_id"] for r in matched}
excluded_rows = [{"record_id": r["record_id"], "reason": "no_status",
                  "材料审核状态": r.get("材料审核状态"), "知识库分类": r.get("知识库分类")}
                 for r in excluded]

# ================================================================ 资源条目
R, E, REC = [], [], []

def add(**kw):
    kw.setdefault("dup_of", None); kw.setdefault("moved_from", None)
    kw.setdefault("status_reason", ""); kw.setdefault("status", "registered")
    kw.setdefault("revision", None); kw.setdefault("filter_passed", None)
    R.append(kw); return kw

prev_keys = set(latest_before)
new_entry_ids, new_child_keys = [], []

# --- 3a) 新增纳入的入口记录（只有 2 条是本批新纳入的；既有 21 条不重发）
for r in matched:
    rid = r["record_id"]
    if f"bitable:{ENTRY_TBL}:{rid}" in prev_keys:
        REC.append({"record_id": rid, "table_name": ENTRY_TBL_NAME, "registered": True,
                    "new_this_run": False, "reason": ""})
        continue
    fvals = {fid_entry[k]: v for k, v in r.items() if k in fid_entry}
    add(resource_key=f"bitable:{ENTRY_TBL}:{rid}", source_kind="feishu_bitable_record",
        table_name=ENTRY_TBL_NAME, table_id=ENTRY_TBL, record_id=rid, field_name=None, field_id=None,
        entry_url=f"https://momcozy-in.feishu.cn/base/{ENTRY_BASE}?table={ENTRY_TBL}&record={rid}",
        path="[内容治理/入口Base/材料收集]", depth=1,
        # §6.3-1（run 20260924-1512 修）：同 build2.py:159，硬编码丢弃 rule_for() 真结果。
        kb_type=kt, matched_rule=ridr, kb_type_source=kts,
        sha256=rec_hash(fvals), sha256_input="record_fields", sha256_state="full",
        container=is_container(registry, f"bitable:{ENTRY_TBL}:{rid}", table_name=ENTRY_TBL_NAME),
        filter_passed=True, extra={"材料审核状态": r.get(FILTER_FIELD),
                                   "知识库分类": r.get("知识库分类"),
                                   "included_by": f"filter {FILTER_FIELD} != 空（{RUN}）",
                                   "all_fields": {k: v for k, v in r.items() if k != "record_id"}})
    RULE_HITS["R5"] += 1
    new_entry_ids.append(rid)
    REC.append({"record_id": rid, "table_name": ENTRY_TBL_NAME, "registered": True,
                "new_this_run": True, "reason": ""})
    E.append({"from_kind": "feishu_bitable_table", "from_id": f"table:{ENTRY_TBL}",
              "to_kind": "feishu_bitable_record", "to_id": f"bitable:{ENTRY_TBL}:{rid}",
              "depth": 1, "field_id": None, "status": "ok",
              "label": f"{ENTRY_TBL_NAME}（{RUN} 新增纳入）"})

# --- 3b) 新增纳入记录的「材料链接」子资源（与既有 21 条同口径下钻一层）
LINK_RE = re.compile(r'^\s*\[.*?\]\((https?://[^\s\)]+)\)|^\s*(https?://\S+)\s*$')
for r in matched:
    rid = r["record_id"]
    if rid not in new_entry_ids:
        continue
    raw = str(r.get("材料链接") or "")
    m = LINK_RE.match(raw.strip())
    url = (m.group(1) or m.group(2)) if m else None
    if not url:
        REC.append({"record_id": rid, "table_name": ENTRY_TBL_NAME, "registered": True,
                    "new_this_run": True, "reason": "材料链接无法解析出 URL，未建子资源"})
        continue
    hint = r.get("知识库分类")
    if "feishu.cn/wiki/" in url:
        tok = re.search(r'/wiki/([A-Za-z0-9]+)', url).group(1)
        key = f"wiki:{tok}"
        kt, ridr, kts = rule_for("wiki", hint=hint)
        if tok == node_el["node_token"]:
            rc = {"sha256": sha(norm_text(doc_el["content"])), "sha256_state": "full",
                  "sha256_input": "doc_text", "revision": doc_el.get("revision_id"),
                  "title": node_el.get("title"), "chars": len(doc_el["content"]),
                  "status_reason": ""}
            sk, obj_type, obj_token = "feishu_doc", node_el.get("obj_type"), node_el.get("obj_token")
        else:
            rc = {"sha256": None, "sha256_state": "unknown", "sha256_input": None, "revision": None,
                  "title": None, "chars": None, "status_reason": "本轮未读取该节点正文，指纹标 unknown"}
            sk, obj_type, obj_token = "feishu_doc", None, None
    else:
        key = f"url:{url}"
        kt, ridr, kts = rule_for("url", hint=hint)
        sk, obj_type, obj_token = "url", None, None
        if url == "https://support.momcozy.com/":
            rawb = open(f"{W}/url_support_momcozy.html", "rb").read()
            html = rawb.decode("utf-8", "replace")
            import html as H
            t = re.sub(r'(?is)<(script|style)[^>]*>.*?</\1>', ' ', html)
            t = H.unescape(re.sub(r'(?s)<[^>]+>', ' ', t))
            t = re.sub(r'[ \t\xa0]+', ' ', t)
            t = "\n".join(l.strip() for l in t.split("\n"))
            t = re.sub(r"\n{3,}", "\n\n", t).strip()
            rc = {"sha256": sha(t), "sha256_state": "full", "sha256_input": "url_text",
                  "revision": None, "title": "Momcozy | Leading the Way in Breastfeeding Comfort | Momcozy Support",
                  "chars": len(t), "status_reason":
                      "HTML 可读且抽出正文文本并据此计算 sha256；但该站为 JS 渲染，抽出的文本以站点导航/商品清单为主，"
                      "实质正文质量存疑（详见报告第 9 节）"}
        else:
            rc = {"sha256": None, "sha256_state": "not_fetched", "sha256_input": "url_text",
                  "revision": None, "title": None, "chars": None,
                  "status_reason": "本轮未抓取该 URL 正文，指纹标 not_fetched"}
    add(resource_key=key, source_kind=sk, table_name=ENTRY_TBL_NAME, table_id=ENTRY_TBL,
        record_id=rid, field_name="材料链接", field_id="fldr4c8nnT", entry_url=url,
        path="[内容治理/入口Base/材料收集/材料链接]", depth=2,
        kb_type=kt, matched_rule=ridr, kb_type_source=kts,
        sha256=rc["sha256"], sha256_input=rc["sha256_input"], sha256_state=rc["sha256_state"],
        revision=rc["revision"],
        status_reason=rc["status_reason"], extra={"url_kind": "wiki" if sk == "feishu_doc" else "url",
            "obj_type": obj_type, "obj_token": obj_token, "title": rc["title"], "chars": rc["chars"],
            "referenced_by_records": [rid], "kb_type_hint_from_record": hint,
            "included_by": f"filter {FILTER_FIELD} != 空（{RUN}）"})
    new_child_keys.append(key)
    E.append({"from_kind": "feishu_bitable_record", "from_id": f"record:{rid}",
              "to_kind": sk, "to_id": key, "depth": 2, "field_id": "fldr4c8nnT",
              "status": "ok" if rc["sha256_state"] == "full" else "not_found",
              "label": "材料链接（新增纳入记录）"})

# --- 2) 内容公式（仅供参考）7 条
formula_table_key = f"bitable:{FORMULA_BASE}:table:{FORMULA_TBL}"
for rec in formula:
    rid = rec["record_id"]
    kt_f, rid_f, kts_f = rule_for(FORMULA_TBL_NAME)   # 逐条求值，命中数按资源计（勿提到循环外）
    fvals = {fid_formula[k]: v for k, v in rec.items() if k in fid_formula}
    add(resource_key=f"bitable:{FORMULA_BASE}:{rid}", source_kind="feishu_bitable_record",
        table_name=FORMULA_TBL_NAME, table_id=FORMULA_TBL, record_id=rid,
        field_name=None, field_id=None,
        entry_url=f"https://momcozy-in.feishu.cn/base/{FORMULA_BASE}?table={FORMULA_TBL}&record={rid}",
        path=f"[内容治理/关联Base/内容公式与专家修订库/{FORMULA_TBL_NAME}]", depth=2,
        kb_type=kt_f, matched_rule=rid_f, kb_type_source=kts_f,
        sha256=rec_hash(fvals), sha256_input="record_fields", sha256_state="full",
        extra={"source_base": FORMULA_BASE, "supplemental": True,
               "backfill_reason": "该表整表从未登记（真缺口），本批按 R18 补登记",
               "all_fields": {k: v for k, v in rec.items() if k != "record_id"}})
    REC.append({"record_id": rid, "table_name": FORMULA_TBL_NAME, "registered": True,
                "new_this_run": True, "reason": ""})
    E.append({"from_kind": "feishu_bitable_table", "from_id": formula_table_key,
              "to_kind": "feishu_bitable_record", "to_id": f"bitable:{FORMULA_BASE}:{rid}",
              "depth": 2, "field_id": None, "status": "ok",
              "label": f"{FORMULA_TBL_NAME}（{RUN} 补登记）"})

# ================================================================ 计算变更类型
def change_state(key, new_sha):
    old = latest_before.get(key)
    if old is None:
        return "registered"
    if new_sha and old.get("sha256") and new_sha != old["sha256"]:
        return "updated"
    return "unchanged"

for e in R:
    e["status"] = change_state(e["resource_key"], e.get("sha256"))
    e["downstream_invalidated"] = e["status"] in ("registered", "updated", "retracted", "gone")

# ================================================================ 写资源文件
written, skipped = [], []
for e in R:
    d = REV[e["kb_type"]]
    os.makedirs(f"{L0}/{d}", exist_ok=True)
    p = f"{L0}/{d}/{fname(e['resource_key'], e['source_kind'])}"
    if os.path.exists(p):
        skipped.append(p); continue
    payload = {"resource_key": e["resource_key"], "source_kind": e["source_kind"],
               "kb_type": e["kb_type"], "matched_rule": e["matched_rule"],
               "kb_type_source": e["kb_type_source"],
               "source": {"table_name": e["table_name"], "table_id": e["table_id"],
                          "record_id": e["record_id"], "field_name": e["field_name"],
                          "field_id": e["field_id"]},
               "entry_url": e["entry_url"], "path": e["path"], "depth": e["depth"],
               "sha256": e["sha256"], "sha256_input": e["sha256_input"],
               "sha256_state": e["sha256_state"], "revision": e["revision"],
               "dup_of": None, "moved_from": None, "status": e["status"],
               "status_reason": e["status_reason"], "filter_passed": e["filter_passed"],
               "observed_at": RUN, "scanner_version": SCANNER, "extra": e.get("extra")}
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2); fh.write("\n")
    written.append(p)

# ================================================================ 写 records/（verbatim 留痕）
n_rec = 0
os.makedirs(f"{L0}/records/{FORMULA_TBL_NAME}", exist_ok=True)
for rec in formula:
    rid = rec["record_id"]
    p = f"{L0}/records/{FORMULA_TBL_NAME}/{rid}.json"
    if os.path.exists(p):
        continue
    fields = {}
    for f in fmeta_formula:
        v = rec.get(f["name"])
        fields[f["name"]] = {"field_id": f["id"], "field_type": f["type"],
                             "value": v, "raw_verbatim": v}
    json.dump({"record_id": rid, "source_table": FORMULA_TBL_NAME, "table_id": FORMULA_TBL,
               "base_token": FORMULA_BASE, "source_base_label": "内容公式与专家修订库",
               "entry_url": f"https://momcozy-in.feishu.cn/base/{FORMULA_BASE}?table={FORMULA_TBL}&record={rid}",
               "timezone": "Asia/Shanghai", "observed_at": RUN,
               "filter": {"result": "not_in_entry_table_scope",
                          "note": "非筛选入口表；本批补登记整表，全字段 verbatim，未做状态筛选"},
               "fields": fields,
               "raw_record": {k: v for k, v in rec.items()},
               "note": f"字段原值 verbatim；补登记整表（{RUN}）。scanner_version={SCANNER}。"},
              open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    n_rec += 1

os.makedirs(f"{L0}/records/{ENTRY_TBL_NAME}", exist_ok=True)
for r in matched:
    rid = r["record_id"]
    p = f"{L0}/records/{ENTRY_TBL_NAME}/{rid}.json"
    if os.path.exists(p):
        continue
    fields = {}
    for f in fmeta_entry:
        v = r.get(f["name"])
        fields[f["name"]] = {"field_id": f["id"], "field_type": f["type"],
                             "value": v, "raw_verbatim": v}
    json.dump({"record_id": rid, "source_table": ENTRY_TBL_NAME, "table_id": ENTRY_TBL,
               "base_token": ENTRY_BASE,
               "entry_url": f"https://momcozy-in.feishu.cn/base/{ENTRY_BASE}?table={ENTRY_TBL}&record={rid}",
               "timezone": "Asia/Shanghai", "observed_at": RUN,
               "filter": {"result": "passed", "field": FILTER_FIELD,
                          "operator": "!=", "value": "空",
                          "note": f"口径修正后纳入（{RUN}）：材料审核状态 != 空"},
               "fields": fields, "raw_record": {k: v for k, v in r.items()},
               "note": f"字段原值 verbatim；入口表全字段提取。scanner_version={SCANNER}。"},
              open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    n_rec += 1

# ================================================================ 写边（追加）+ tombstone
new_edges = []
for e in E:
    new_edges.append({"from_kind": e["from_kind"], "from_id": e["from_id"],
                      "to_kind": e["to_kind"], "to_id": e["to_id"], "depth": e["depth"],
                      "field_id": e["field_id"], "status": e["status"], "label": e["label"],
                      "observed_at": RUN})
with open(graph_path, "a", encoding="utf-8") as fh:
    for e in tomb + new_edges:
        fh.write(json.dumps(e, ensure_ascii=False, sort_keys=True) + "\n")

# ================================================================ 写台账（追加）
rows = []
for e in R:
    rows.append({k: e.get(k) for k in
                 ("resource_key", "source_kind", "table_name", "table_id", "record_id",
                  "field_name", "field_id", "entry_url", "path", "depth", "kb_type",
                  "matched_rule", "sha256", "sha256_input", "sha256_state", "revision",
                  "dup_of", "status", "status_reason")})
    rows[-1]["downstream_invalidated"] = e["downstream_invalidated"]
    rows[-1]["observed_at"] = RUN
    rows[-1]["scanner_version"] = SCANNER
for k in RULELIB:
    old = latest_before[k]
    rows.append({"resource_key": k, "source_kind": old["source_kind"],
                 "table_name": old["table_name"], "table_id": old["table_id"],
                 "record_id": old["record_id"], "field_name": old["field_name"],
                 "field_id": old["field_id"], "entry_url": old["entry_url"],
                 "path": old["path"], "depth": old["depth"], "kb_type": old["kb_type"],
                 "matched_rule": old["matched_rule"], "sha256": old["sha256"],
                 "sha256_input": old["sha256_input"], "sha256_state": old["sha256_state"],
                 "revision": old["revision"], "dup_of": old["dup_of"],
                 "status": "retracted", "status_reason": "excluded_by_scope",
                 "downstream_invalidated": True, "observed_at": RUN,
                 "scanner_version": SCANNER,
                 "moved_from": next((a["from"] for a in archived
                                     if a["resource_key"] == k and a["moved"]), None),
                 "moved_to": next((a["to"] for a in archived
                                   if a["resource_key"] == k and a["moved"]), None),
                 "retract_reason_detail":
                     "用户口径：「全部」不包含规则库，连存量一起清；R6–R10 停用后规则库整体不纳入，"
                     "不得兜底进 unknown。资源文件已移出库目录到 " + ARCHIVE + "，审计可查"})
with open(manifest_path, "a", encoding="utf-8") as fh:
    for r in rows:
        fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")

# ================================================================ 重建 index
latest = {}
for l in open(manifest_path, encoding="utf-8"):
    if l.strip():
        r = json.loads(l); latest[r["resource_key"]] = r
live = {k: v for k, v in latest.items() if v["status"] != "retracted"}
with open(f"{L0}/index/l0.jsonl", "w", encoding="utf-8") as fh:
    for k in sorted(live):
        r = live[k]
        fh.write(json.dumps({"resource_key": r["resource_key"], "kb_type": r["kb_type"],
                             "source_kind": r["source_kind"], "status": r["status"],
                             "entry_url": r["entry_url"]}, ensure_ascii=False, sort_keys=True) + "\n")

# ================================================================ registry 更新
reg = json.load(open(f"{L0}/registry/kb.json", encoding="utf-8"))
reg["_comment"] = ("L0 原始库映射规则。机器判断分类一律查 dir_map，不要硬编码中文目录名。"
                   "分类只能靠重跑改，不手工 mv/重命名。"
                   "规则生效与否看每条规则的 enabled（缺省为 true）；停用规则不参与求值。")
for r in reg["rules"]:
    if r["id"] in DISABLED:
        r["enabled"] = False
        r["disabled_by"] = RUN
        r["state"] = "disabled"
        r["disabled_reason"] = ("用户口径：「全部」不包含规则库。规则库整体不纳入 L0，"
                               "R6–R10（scope_table=规则库）全部停用，规则库记录不再兜底进 unknown。")
    else:
        r.setdefault("enabled", True)
        r.setdefault("state", "active")
reg["rule_eval_order"] = (
    "按 rules 数组自然顺序求值，**跳过 enabled=false 的规则**，第一条命中即停。"
    "本批停用 R6 → R10（scope_table=规则库）后，生效顺序为："
    "R1 → R2 → R3 → R4 → R5 → R11 → R12 → R13 → R14 → R15 → R16 → R17 → R18 → R19 → R20 → "
    "R21 → R22 → R23 → R24 → R25 → R26（即 R1 → R26 顺序，跳过 R6–R10）。"
    "资源级规则（字段值 / 字段名）优先于表级兜底。命中不到任何生效规则 → kb_type=unknown，"
    "落到 9_未归类/，单独汇总，不猜。"
    "例外：excluded_scope.tables 里的表整体不纳入，既不登记新资源也不兜底进 unknown。")
reg["rule_eval_order_prev"] = ("R1 → R24 顺序，第一条命中即停。资源级规则（字段值 / 字段名）优先于表级兜底。"
                               "命中不到任何规则 → kb_type=unknown，落到 9_未归类/，单独汇总，不猜。")
reg["excluded_scope"] = {
    "tables": ["规则库"],
    "policy": "整体不纳入：不登记资源、不进库目录、不进 index；既有存量登记为 retracted",
    "reason": "用户口径：「全部」不包含规则库，连存量一起清",
    "by_rule_state": "R6–R10 已 enabled=false，规则库记录不会再兜底进 unknown",
    "since": RUN,
    "archived_to": ARCHIVE,
    "archived_resource_count": sum(1 for a in archived if a["moved"]),
}
reg["filter"] = {"field": FILTER_FIELD, "operator": "!=", "value": "空",
                 "value_semantics": "空 = 该字段无值（[] / null / \"\"）",
                 "changed_at": RUN,
                 "prev": {"field": FILTER_FIELD, "operator": "==", "value": "通过"},
                 "reason": "用户口径：「有状态」才全量提取所有字段。实测 32 条：通过 22 / 暂不采用 1 / 空 9",
                 "expected_included": 23}
reg["excluded_policy"] = (
    "未命中筛选的记录只在 runs/<run_id>.json 留痕，不登记资源、不进库目录、不进索引。"
    "原因枚举（本批扩充，不再只写 status_not_passed）："
    "no_status = 筛选字段为空（本批 9 条）；"
    "excluded_by_scope = 该表按用户口径整体不纳入（本批 规则库 16 条存量 retracted）；"
    "out_of_scope_kb = 记录所属 kb_type 不在本轮范围内；"
    "dup = 与既有资源同 sha256 的重复项。"
    "已废弃：status_not_passed（口径由 == 通过 改为 != 空 后，「暂不采用」改为纳入，该枚举不再产生）。")
reg["field_roles"] = FREQ["field_roles_after"]
reg["field_role_table_overrides"] = FREQ["overrides_after"]
reg["field_role_vocabulary"] = {
    "content": "承载可引用的表述 / 理由 / 条件 —— L3 step1 只保留这一类字段产生的单元",
    "text": "自由文本，但不承载可引用表述（人名、路径、说明性文字）→ 视为元数据",
    "status": "状态 / 分类标签（单选、多选、枚举）",
    "link": "链接字段（URL 文本、link 类型字段）",
    "attachment": "附件字段（图片 / 文件）",
    "other": "编号 / 统计 / 日期 / 行政标记等其余元数据",
}
reg["field_role_resolution"] = ("先查 field_role_table_overrides 的「表名::字段名」，未命中再查 field_roles 裸字段名。"
                                "同名不同角色必须写覆盖。L0 是唯一真相：下游不得自建补丁角色表。")
reg["field_role_evidence_notes"] = FREQ["evidence_notes"]
reg["field_role_coverage"] = {
    "l2_universe_size": FREQ["coverage"]["universe"],
    "covered": FREQ["coverage"]["covered"],
    "missing_count": FREQ["coverage"]["missing_count"],
    "l2_universe_counts": FREQ["l2_universe"]["counts"],
    "measured_at": RUN,
}
reg.setdefault("supplemental_registrations", []).append({
    "run_id": RUN,
    "what": "补登记入口 Base 兄弟表「内容公式（仅供参考）」（tblVdl0jdK9G4ld3）整表 7 条记录（该表此前 0 条登记）",
    "rules_added": [], "rules_disabled": sorted(DISABLED),
    "note": "R18（table_name=内容公式（仅供参考）→ wording）此前已在 registry 里，本次是补数据、不是补规则。",
})
reg.setdefault("changes", []).append({
    "run_id": RUN, "change": "update",
    "keys": ["rules[].enabled（R6–R10 停用）", "rule_eval_order", "excluded_scope", "filter",
             "excluded_policy", "field_roles", "field_role_table_overrides", "field_role_vocabulary",
             "field_role_resolution", "field_role_evidence_notes", "field_role_coverage",
             "supplemental_registrations[]"],
    "note": "本批允许改 registry（口径修正的本体）；kb/l0 既有资源文件、台账旧行、links 历史行一律未改。",
    "scanner_version": SCANNER,
})
with open(f"{L0}/registry/kb.json", "w", encoding="utf-8") as fh:
    json.dump(reg, fh, ensure_ascii=False, indent=2); fh.write("\n")

# ================================================================ L3 registry 标注
l3p = "kb/l3/registry/l3.json"
l3 = json.load(open(l3p, encoding="utf-8"))
l3["filter_rules"]["step1_metadata"]["merged_into_l0"] = {
    "at": RUN, "by": "L0 batch3", "state": "已并入 L0",
    "note": ("原先 L3 在 l3_distill.py / l3_distill2.py 里自建的 CONTENT_FIELDS(37) / METADATA_FIELDS(71) "
             "补丁角色表，已合并回 kb/l0/registry/kb.json 的 field_roles（44 → 118 项，"
             "L2 实测字段论域 88 项 100% 覆盖、0 遗漏）。L0 是唯一真相，L3 不再需要自己那份补丁表："
             "unit 的 heading_path 直接查 L0 field_roles，role == 'content' 即保留，其余视为元数据。"),
    "l0_field_roles_count": FREQ["field_roles_after_count"],
    "l2_universe_covered": f'{FREQ["coverage"]["covered"]}/{FREQ["coverage"]["universe"]}',
    "new_table_overrides": FREQ["new_overrides"],
}
l3["filter_rules"]["step1_metadata"]["how"] = (
    "按 kb/l0/registry/kb.json 的 field_roles 过滤（L0 为唯一真相），只保留 role == 'content' "
    "的「文案/表述类字段」产生的单元；其余角色（text/status/link/attachment/other）一律视为元数据")
l3["filter_rules"]["step1_metadata"]["gap"] = (
    "已闭合（" + RUN + "）：原缺口为「L0 的 field_roles 只覆盖 44 个字段，L2 实际出现 70+ 个」，"
    "本批在 L0 侧补全并收归，L3 侧不再保留补丁角色表。")
with open(l3p, "w", encoding="utf-8") as fh:
    json.dump(l3, fh, ensure_ascii=False, indent=2); fh.write("\n")

# ================================================================ 自检数据
def dirdist():
    c = collections.Counter()
    for d in DIR_MAP:
        c[DIR_MAP[d]] = len(glob.glob(f"{L0}/{d}/*.json"))
    return c

files_now = {}
for d in DIR_MAP:
    for p in glob.glob(f"{L0}/{d}/*.json"):
        j = json.load(open(p, encoding="utf-8"))
        files_now[j["resource_key"]] = (p, j)
mismatch = []
for k, (p, j) in files_now.items():
    d = os.path.basename(os.path.dirname(p))
    led = latest.get(k)
    if led is None:
        mismatch.append((k, "文件存在但台账无最新行")); continue
    if j["kb_type"] != led["kb_type"]:
        mismatch.append((k, f"文件 kb_type={j['kb_type']} != 台账 {led['kb_type']}")); continue
    if DIR_MAP[d] != j["kb_type"]:
        mismatch.append((k, f"文件 kb_type={j['kb_type']} != 所在目录 {d}")); continue

index_rows = sum(1 for l in open(f"{L0}/index/l0.jsonl", encoding="utf-8") if l.strip())
report = {
    "run_id": RUN, "scanner_version": SCANNER, "part": "batch3 · L0 范围冻结",
    "before": {"latest_rows": len(latest_before), "files": sum(dirdist().values()),
               "by_kb": dict(collections.Counter(v["kb_type"] for v in latest_before.values()))},
    "after": {"files": len(files_now), "by_kb": dict(dirdist()), "index_rows": index_rows},
    "rule_eval_order": reg["rule_eval_order"],
    "rules": [{"id": r["id"], "enabled": r.get("enabled", True), "kb_type": r["kb_type"],
               "scope_table": r.get("scope_table"), "match_type": r["match_type"],
               "pattern": r.get("pattern"), "match_value": r.get("match_value"),
               "hits_this_run": RULE_HITS.get(r["id"], 0)} for r in reg["rules"]],
    "zero_hit_rules": [r["id"] for r in reg["rules"] if RULE_HITS.get(r["id"], 0) == 0],
    "rulelib": {"count": len(RULELIB), "keys": RULELIB, "archived": archived,
                "retracted_rows": len(RULELIB), "tombstone_edges": len(tomb),
                "archive_dir": ARCHIVE},
    "formula_table": {"source_records": len(formula), "registered": 7,
                      "record_ids": [r["record_id"] for r in formula],
                      "files": [p for p in written if FORMULA_BASE in p]},
    "entry_filter": {"status_distribution": dict(status_dist),
                     "included": len(matched), "excluded": len(excluded),
                     "new_included": new_entry_ids, "excluded_rows": excluded_rows},
    "field_roles": {"before": FREQ["field_roles_before_count"],
                    "after": FREQ["field_roles_after_count"],
                    "l2_universe": FREQ["coverage"]["universe"],
                    "covered": FREQ["coverage"]["covered"],
                    "missing": FREQ["coverage"]["missing"],
                    "new_overrides": FREQ["new_overrides"],
                    "evidence_notes": FREQ["evidence_notes"]},
    "change": dict(collections.Counter(e["status"] for e in R)),
    "written_files": written, "skipped_existing": skipped, "record_files": n_rec,
    "edges_appended": len(new_edges), "tombstones_appended": len(tomb),
    "mismatch": mismatch, "ops": OPS, "rule_hits": dict(RULE_HITS),
}
json.dump(report, open(f"{L0}/runs/{RUN}.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(json.dumps({k: report[k] for k in ("before", "after", "change", "rule_hits", "zero_hit_rules",
                                         "edges_appended", "tombstones_appended", "record_files",
                                         "mismatch")}, ensure_ascii=False, indent=1))
print("台账新增行:", len(rows), "| 资源文件新增:", len(written), "| 跳过:", len(skipped))
print("规则库归档:", sum(1 for a in archived if a["moved"]), "→", ARCHIVE)
print("入口筛选:", dict(status_dist), "纳入", len(matched), "排除", len(excluded))
