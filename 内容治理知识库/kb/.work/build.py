#!/usr/bin/env python3
"""L0 落库 · 步骤 5/6/7/9/10: 资源登记、边表、台账、候选切片、索引。"""
import json, os, re, hashlib, collections, sys

RUN = sys.argv[1]
KB = "kb/l0"
SCANNER = "0.5"
ENTRY_BASE = "GnRZbIuXraCzf0sGr2UcmZ62nfc"
ENTRY_TBL = "tblMGtPfe8ZUsEdP"
ENTRY_TBL_NAME = "材料收集"
EXCLUDE_FIELDS = {"last_modified_time", "last_modified_by"}
URL_RE = re.compile(r'https?://[^\s\)\]\>"\']+')

def sha(t):
    return hashlib.sha256(t.encode("utf-8")).hexdigest()

def canon(o):
    return json.dumps(o, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

def norm_text(s):
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    s = "\n".join(l.rstrip() for l in s.split("\n"))
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()

def rec_hash(fields):
    """record_fields: 按 field_id 升序键序列化后（剔除 exclude_fields）→ sha256"""
    items = sorted(((fid, v) for fid, v in fields.items()), key=lambda x: x[0])
    return sha(canon([["field_id", k, "value", v] for k, v in items]))

def structure_hash(o):
    return sha(canon(o))

SIB = {"知识库分类说明": "tblZP8jG4tiUL98C", "正面和负面样本": "tbld8qE92YaY38Yz", "规则库": "tblXsrMVkDNZ3oW8"}
registry = json.load(open(f"{KB}/registry/kb.json", encoding="utf-8"))
snapshot = json.load(open(f"{KB}/runs/{RUN}.json", encoding="utf-8"))
l1 = json.load(open("kb/.work/l1.json", encoding="utf-8"))
l1c = json.load(open("kb/.work/l1_content.json", encoding="utf-8"))
bases = json.load(open("kb/.work/bases/enum.json", encoding="utf-8"))
urlc = json.load(open("kb/.work/url_content.json", encoding="utf-8"))
parent_records = [json.loads(l) for l in open("kb/.work/材料收集.ndjson", encoding="utf-8") if l.strip()]
fields_meta = json.load(open(f"kb/.work/fields-{ENTRY_TBL}.json", encoding="utf-8"))["data"]["fields"]
fid_by_name = {f["name"]: f["id"] for f in fields_meta}
approved_ids = set(snapshot["matched_record_ids"])

R = []   # 资源登记条目
E = []   # 边表

def add(**kw):
    R.append(kw)
    return kw

def rule_for(table, kb_type_hint=None, field_name=None, scope_table=None, scoped_values=None):
    """按 registry 规则顺序求 kb_type 与命中规则 id。资源级规则先于表级兜底。"""
    rules = registry["rules"]
    # (1) 记录自带的分类单选值
    if kb_type_hint:
        for t in kb_type_hint:
            if t == "其它":
                continue
            for r in rules:
                if r["match_type"] == "field_value" and r.get("scope_table") == ENTRY_TBL_NAME \
                   and r.get("match_value") == t:
                    return r["kb_type"], r["id"], f"记录字段值:知识库分类={t}"
    # (2) scope_table + field_value
    if scope_table and scoped_values:
        for fname, fval in scoped_values.items():
            for r in rules:
                if (r["match_type"] == "field_value" and r.get("scope_table") == scope_table
                        and r.get("pattern") == fname and r.get("match_value") == fval):
                    return r["kb_type"], r["id"], f"记录字段值:{fname}={fval}"
    # (3) 字段名规则
    if field_name:
        for r in rules:
            if r["match_type"] == "field_name" and r["pattern"] == field_name:
                return r["kb_type"], r["id"], f"字段名:{field_name}"
    # (4) 表名兜底（scope_table 限定时只对该表生效）
    for r in rules:
        if r["match_type"] == "table_name" and r["pattern"] == table:
            if r.get("scope_table") and r["scope_table"] != table:
                continue
            return r["kb_type"], r["id"], f"表名:{table}"
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


def rule_for_table_resource(table):
    """表资源级：命中 table_unknown_allowlist 的表本身不归属任何一类库。"""
    allow = registry.get("table_unknown_allowlist", {})
    if table in allow:
        return "unknown", None, f"表资源在 unknown 白名单:{table}（{allow[table]}）"
    return rule_for(table)

# ---------------------------------------------------------------- 1) 入口记录
for r in parent_records:
    rid = r["record_id"]
    fvals = {fid_by_name[k]: v for k, v in r.items() if k in fid_by_name}
    h = rec_hash({k: v for k, v in fvals.items() if k not in EXCLUDE_FIELDS})
    passed = rid in approved_ids
    add(resource_key=f"bitable:{ENTRY_TBL}:{rid}", source_kind="feishu_bitable_record",
        table_name=ENTRY_TBL_NAME, table_id=ENTRY_TBL, record_id=rid,
        field_name=None, field_id=None,
        entry_url=f"https://momcozy-in.feishu.cn/base/{ENTRY_BASE}?table={ENTRY_TBL}&record={rid}",
        path="[内容治理/材料收集]", depth=1,
        # §6.3-1（run 20260924-1512 修）：硬编码 → 真求值
        kb_type=kt, matched_rule=ridr, kb_type_source=kts,
        sha256=h, sha256_input="record_fields", sha256_state="full", revision=None,
        status="registered", status_reason="", filter_passed=passed,
        filter_reason="" if passed else dict((x["record_id"], x["reason"]) for x in snapshot["excluded_records"]).get(rid),
        payload_ref=f"records/{ENTRY_TBL_NAME}/{rid}.json",
        extra={"材料审核状态": r.get("材料审核状态"), "知识库分类": r.get("知识库分类")})
    E.append({"from_kind": "feishu_bitable_base", "from_id": f"base:{ENTRY_BASE}",
              "to_kind": "feishu_bitable_table", "to_id": f"table:{ENTRY_TBL}",
              "depth": 1, "field_id": None, "status": "ok", "label": ENTRY_TBL_NAME})

# ---------------------------------------------------------------- 1b) 入口 Base 与入口表本身
entry_base_fields = [{"field_id": f["id"], "field_name": f["name"], "type": f["type"],
                      "options": [o.get("name") for o in (f.get("options") or [])] or None,
                      "multiple": f.get("multiple")} for f in fields_meta]
add(resource_key=f"base:{ENTRY_BASE}", source_kind="feishu_bitable_base", table_name=None,
    table_id=None, record_id=None, field_name=None, field_id=None,
    entry_url=f"https://momcozy-in.feishu.cn/base/{ENTRY_BASE}", path="[内容治理]", depth=1,
    kb_type="unknown", matched_rule=None, kb_type_source="no_rule_matched:Base 是容器，不是知识本体",
    sha256=structure_hash({"base_token": ENTRY_BASE, "tables": sorted(SIB.values()) + [ENTRY_TBL]}),
    sha256_input="structure", sha256_state="full", revision=None,
    status="registered", status_reason="", filter_passed=None, payload_ref=None,
    extra={"note": "入口 Base 容器，仅登记身份与表清单"})
add(resource_key=f"bitable:{ENTRY_BASE}:table:{ENTRY_TBL}", source_kind="feishu_bitable_table",
    table_name=ENTRY_TBL_NAME, table_id=ENTRY_TBL, record_id=None, field_name=None, field_id=None,
    entry_url=f"https://momcozy-in.feishu.cn/base/{ENTRY_BASE}?table={ENTRY_TBL}",
    path="[内容治理/入口Base/材料收集]", depth=1,
    # §6.3-1（run 20260924-1512 修）：表级兜底仍走真求值（R5 命中即 unknown，由规则自己给出）
    kb_type=kt_table, matched_rule=rid_table, kb_type_source=kts_table,
    sha256=structure_hash({"table_id": ENTRY_TBL, "table_name": ENTRY_TBL_NAME, "fields": entry_base_fields}),
    sha256_input="structure", sha256_state="full", revision=None,
    status="registered", status_reason="", filter_passed=None, payload_ref=None,
    extra={"records_count": len(parent_records), "field_count": len(entry_base_fields),
           "note": "筛选入口表本身"})
# （入口 Base → 入口表 的边已在 1) 建立，此处不重复）

# ---------------------------------------------------------------- 2) 入口 Base 的兄弟表（第一层）
sib_counts = {"知识库分类说明": 5, "正面和负面样本": 125, "规则库": 50}
for tname, tid in SIB.items():
    st = l1["sibling_tables"][tname]
    h = structure_hash({"table_id": tid, "table_name": tname,
                        "fields": [{"field_id": f["field_id"], "field_name": f["field_name"],
                                    "type": f["type"], "options": f.get("options")} for f in st["fields"]]})
    kt, rid_, kts = rule_for_table_resource(tname)
    add(resource_key=f"bitable:{ENTRY_BASE}:table:{tid}", source_kind="feishu_bitable_table",
        table_name=tname, table_id=tid, record_id=None, field_name=None, field_id=None,
        entry_url=f"https://momcozy-in.feishu.cn/base/{ENTRY_BASE}?table={tid}",
        path="[内容治理/入口Base]", depth=1,
        kb_type=kt, matched_rule=rid_, kb_type_source=kts,
        sha256=h, sha256_input="structure", sha256_state="full", revision=None,
        status="registered", status_reason="", filter_passed=None,
        payload_ref=None, extra={"records_count": sib_counts[tname], "field_count": len(st["fields"]),
                                 "note": "入口 Base 内同级表，作为下钻目标登记表结构；记录不在入口表筛选范围内，不逐条登记"})
    E.append({"from_kind": "feishu_bitable_base", "from_id": f"base:{ENTRY_BASE}",
              "to_kind": "feishu_bitable_table", "to_id": f"table:{tid}",
              "depth": 1, "field_id": None, "status": "ok", "label": tname})

# ---------------------------------------------------------------- 3) L1 资源
targets_by_key = {}
for t in l1["l1_targets"]:
    targets_by_key.setdefault(t["resource_key"], []).append(t)

for key, ts in targets_by_key.items():
    t = ts[0]
    rc = l1c.get(key, {})
    hint = t.get("kb_type_hint") or []
    kt, rid_, kts = rule_for(t.get("kind"), kb_type_hint=hint)
    parents = [x["record_id"] for x in ts]
    src_kind = {"wiki": {"docx": "feishu_doc", "file": "feishu_file", "bitable": "feishu_bitable_base"} .get(t.get("obj_type") or "", "feishu_wiki_node"),
                "base": "feishu_bitable_base", "sheets": "feishu_sheet", "slides": "feishu_slides",
                "file": "feishu_file", "url": "url", "docx": "feishu_doc"}.get(t["kind"], "url")
    h = rc.get("sha256")
    state = rc.get("sha256_state")
    if state == "fetch_failed":
        et, es = rc.get("error_type"), (rc.get("error_subtype") or "")
        msg = (rc.get("error") or {}).get("message", "") + str(rc.get("status_reason") or "")
        if "missing_scope" in msg or "missing required scope" in msg or es == "missing_scope" or et == "authorization":
            state, rc["sha256_state"] = "no_scope", "no_scope"
            rc["status_reason"] = "缺少读取所需 scope，未能读取内容并计算 sha256"
        else:
            state, rc["sha256_state"] = "unreachable", "unreachable"
            rc["status_reason"] = (rc.get("status_reason") or "读取失败，无法计算 sha256")
    if state is None:
        state = "full" if h else "unknown"
    entry = add(resource_key=key, source_kind=src_kind, table_name=ENTRY_TBL_NAME, table_id=ENTRY_TBL,
        record_id=parents[0] if len(parents) == 1 else None,
        field_name=t.get("field_name"), field_id=t.get("field_id"),
        entry_url=t["url"], path="[内容治理/材料收集/材料链接]", depth=2,
        kb_type=kt, matched_rule=rid_, kb_type_source=kts,
        sha256=h, sha256_input=rc.get("sha256_input"), sha256_state=state,
        revision=rc.get("revision"), status="registered",
        status_reason=rc.get("status_reason", ""), filter_passed=None, payload_ref=None,
        extra={"url_kind": t["kind"], "obj_type": t.get("obj_type"), "obj_token": t.get("obj_token"),
               "title": rc.get("title") or (t.get("node") or {}).get("title"),
               "chars": rc.get("chars"), "referenced_by_records": parents,
               "kb_type_hint_from_record": hint, "anchor_text": t.get("anchor_text"),
               "urls_in_content": None})
    for p in parents:
        E.append({"from_kind": "feishu_bitable_record", "from_id": f"record:{p}",
                  "to_kind": src_kind, "to_id": key, "depth": 2,
                  "field_id": t.get("field_id"), "status": "ok" if state in ("full", "structure_only", "structure") or h else
                            ("forbidden" if state == "no_scope" else "not_found"),
                  "label": t.get("field_name")})

# ---------------------------------------------------------------- 4) 关联 Base 的表与记录（第二层）
base_keys = {k for k in targets_by_key}
for bt, b in bases.items():
    bkey = f"base:{bt}"
    if bkey in base_keys:
        for tb in b["tables"]:
            tk = f"bitable:{bt}:table:{tb['table_id']}"
            h = structure_hash({"table_id": tb["table_id"], "fields": [
                {"field_id": f["field_id"], "field_name": f["field_name"], "type": f["type"]} for f in tb["fields"]]})
            kt, rid_, kts = rule_for_table_resource(tb["table_name"])
            add(resource_key=tk, source_kind="feishu_bitable_table", table_name=tb["table_name"],
                table_id=tb["table_id"], record_id=None, field_name=None, field_id=None,
                entry_url=f"https://momcozy-in.feishu.cn/base/{bt}?table={tb['table_id']}",
                path=f"[内容治理/关联Base/{b['label']}]", depth=2,
                kb_type=kt, matched_rule=rid_, kb_type_source=kts,
                sha256=h, sha256_input="structure", sha256_state="full", revision=tb.get("rev"),
                status="registered", status_reason="", filter_passed=None, payload_ref=None,
                extra={"records_count": tb["records_count"], "field_count": len(tb["fields"]),
                       "records_sampled": tb["records_sampled"], "records_truncated": tb["records_truncated"],
                       "note": "关联 Base 的表结构；记录采样上限 200 条"})
            E.append({"from_kind": "feishu_bitable_base", "from_id": bkey, "to_kind": "feishu_bitable_table",
                      "to_id": tk, "depth": 2, "field_id": None, "status": "ok", "label": tb["table_name"]})
            for rec in tb["records"]:
                rid = rec["record_id"]
                fvals = {}
                for f in tb["fields"]:
                    if f["field_name"] in rec:
                        fvals[f["field_id"]] = rec[f["field_name"]]
                hh = rec_hash({k: v for k, v in fvals.items() if k not in EXCLUDE_FIELDS})
                rk = f"bitable:{bt}:{rid}"
                kt2, rid2, kts2 = rule_for(tb["table_name"], field_name=None)
                add(resource_key=rk, source_kind="feishu_bitable_record", table_name=tb["table_name"],
                    table_id=tb["table_id"], record_id=rid, field_name=None, field_id=None,
                    entry_url=f"https://momcozy-in.feishu.cn/base/{bt}?table={tb['table_id']}&record={rid}",
                    path=f"[内容治理/关联Base/{b['label']}/{tb['table_name']}]", depth=2,
                    kb_type=kt2, matched_rule=rid2, kb_type_source=kts2,
                    sha256=hh, sha256_input="record_fields", sha256_state="full", revision=None,
                    status="registered", status_reason="", filter_passed=None, payload_ref=None,
                    extra={"note": "下钻第二层记录，字段原值保存在 kb/.work/bases/*.ndjson"})
                E.append({"from_kind": "feishu_bitable_table", "from_id": tk, "to_kind": "feishu_bitable_record",
                          "to_id": rk, "depth": 2, "field_id": None, "status": "ok", "label": tb["table_name"]})

# ---------------------------------------------------------------- 5) 分类说明表记录（第二层）
cat_recs = [json.loads(l) for l in open("kb/.work/分类说明.ndjson", encoding="utf-8") if l.strip()]
cat_fields = l1["sibling_tables"]["知识库分类说明"]["fields"]
CATMAP = {"外部标准": "external_standard", "正面与负面样本": "internal_sample",
          "措辞表达库": "wording", "产品描述库": "product_desc"}
for rec in cat_recs:
    rid = rec["record_id"]
    fvals = {f["field_id"]: rec.get(f["field_name"]) for f in cat_fields}
    h = rec_hash({k: v for k, v in fvals.items() if k not in EXCLUDE_FIELDS})
    kb_name = rec.get("知识库")
    kt, rid_rule, kts_rule = rule_for("知识库分类说明", scope_table="知识库分类说明",
                                      scoped_values={"知识库": kb_name}, field_name="知识库")
    add(resource_key=f"bitable:{SIB['知识库分类说明']}:{rid}", source_kind="feishu_bitable_record",
        table_name="知识库分类说明", table_id=SIB["知识库分类说明"], record_id=rid,
        field_name=None, field_id=None,
        entry_url=f"https://momcozy-in.feishu.cn/base/{ENTRY_BASE}?table={SIB['知识库分类说明']}&record={rid}",
        path="[内容治理/入口Base/知识库分类说明]", depth=2,
        kb_type=kt, matched_rule=rid_rule, kb_type_source=kts_rule,
        sha256=h, sha256_input="record_fields", sha256_state="full", revision=None,
        status="registered", status_reason="", filter_passed=None, payload_ref=None,
        extra={"知识库": kb_name, "负责人": rec.get("负责人")})
    E.append({"from_kind": "feishu_bitable_table", "from_id": f"table:{SIB['知识库分类说明']}",
              "to_kind": "feishu_bitable_record",
              "to_id": f"bitable:{SIB['知识库分类说明']}:{rid}", "depth": 2, "field_id": None,
              "status": "ok", "label": "知识库分类说明"})

# ---------------------------------------------------------------- 6) 规则库「来源链接」外部 URL（第二层）
rules_recs = [json.loads(l) for l in open("kb/.work/规则库.ndjson", encoding="utf-8") if l.strip()]
src_urls = collections.Counter()
for rec in rules_recs:
    for m in URL_RE.finditer(str(rec.get("来源链接") or "")):
        src_urls[m.group(0)] += 1
gdoc = json.load(open("kb/.work/gdoc.json", encoding="utf-8"))
for k, v in gdoc.items():
    urlc[k] = {"url": k, "status": v["status"], "sha256": v["sha256"],
               "sha256_state": v["sha256_state"], "http_bytes": v["http_bytes"],
               "text_chars": v["extracted_text_chars"], "title": v["title"],
               "status_reason": v["status_reason"], "extract_method": None}

for u, n in src_urls.most_common():
    uc = urlc.get(u, {})
    st = uc.get("status")
    state = "full" if st == "ok" else "unreachable"
    add(resource_key=f"url:{u}", source_kind="url", table_name="规则库",
        table_id=SIB["规则库"], record_id=None, field_name="来源链接", field_id="fld1VehxHe",
        entry_url=u, path="[内容治理/入口Base/规则库/来源链接]", depth=2,
        kb_type="external_standard", matched_rule="R11", kb_type_source="field_name:来源链接",
        sha256=uc.get("sha256"), sha256_input="url_text" if st == "ok" else None,
        sha256_state=state, revision=None, status="registered",
        status_reason="" if st == "ok" else (uc.get("status_reason") or "抓取未返回正文（HTTP 404 / 无正文），无法指纹"),
        filter_passed=None, payload_ref=None,
        extra={"referenced_by_rules": n, "http_bytes": uc.get("http_bytes"),
               "text_chars": uc.get("text_chars"), "extract_method": uc.get("extract_method"),
               "note": "规则库来源链接，外部标准原文"})
    E.append({"from_kind": "feishu_bitable_table", "from_id": f"table:{SIB['规则库']}",
              "to_kind": "url", "to_id": f"url:{u}", "depth": 2, "field_id": "fld1VehxIe",
              "status": "ok" if st == "ok" else "not_found", "label": "来源链接"})
    for rec in rules_recs:
        if u in str(rec.get("来源链接") or ""):
            E.append({"from_kind": "feishu_bitable_record", "from_id": f"record:{rec['record_id']}",
                      "to_kind": "url", "to_id": f"url:{u}", "depth": 2, "field_id": "fld1VehxHe",
                      "status": "ok" if st == "ok" else "not_found", "label": "来源链接"})

# ---------------------------------------------------------------- 7) 第三层链接：记录边，不登记资源
l3 = json.load(open("kb/.work/l3.json", encoding="utf-8"))
depth3 = l3["depth3"]
for x in depth3:
    feishu = x["kind"] != "url"
    E.append({"from_kind": "feishu_doc" if x["from"].startswith("wiki:") else "url",
              "from_id": x["from"], "to_kind": x["kind"], "to_id": x["url"],
              "depth": 3, "field_id": None,
              "status": "forbidden" if feishu else "skipped_depth_limit",
              "label": "超出下钻层数上限(2)：仅记录边，不登记资源" if not feishu
                       else "超出下钻层数上限(2) 且缺少读取 scope：仅记录边，不登记资源"})

# 关联 Base 记录里的 URL 字段 → 第三层边（有界采样，仅记录不登记）
bu = json.load(open("kb/.work/base_urls.json", encoding="utf-8"))
import collections as _c
_urls = bu["unique_urls"]
_bad = [u for u in _urls if not re.match(r'^https?://[A-Za-z0-9.\-]+/', u)]
_good = [u for u in _urls if u not in _bad]
_D3_CAP = 60
for u in _good[:_D3_CAP]:
    E.append({"from_kind": "feishu_bitable_record", "from_id": "bitable:" + bt if False else "base-record-field",
              "to_kind": "url", "to_id": u, "depth": 3, "field_id": None,
              "status": "skipped_depth_limit", "label": "关联 Base 记录 URL 字段，超出层数上限，仅记录不登记"})
extra_l3 = {"base_field_urls_unique": len(_urls), "base_field_urls_sampled_as_edges": min(len(_good), _D3_CAP),
            "base_field_urls_truncated": max(0, len(_good) - _D3_CAP),
            "base_field_urls_malformed": len(_bad), "hosts": bu["hosts"]}

# 正文链接信号回填到资源条目
for e in R:
    if e["resource_key"] in l1c:
        e["extra"]["urls_in_content"] = sorted({x["url"] for x in depth3 if x["from"] == e["resource_key"]})

# ---------------------------------------------------------------- 8) dup_of
by_hash = collections.defaultdict(list)
for e in R:
    if e.get("sha256"):
        by_hash[e["sha256"]].append(e)
for h, items in by_hash.items():
    if len(items) > 1:
        items_sorted = sorted(items, key=lambda x: (x["depth"], x["resource_key"]))
        head = items_sorted[0]["resource_key"]
        for it in items_sorted[1:]:
            it["dup_of"] = head

_seen=set(); _ded=[]
for _e in E:
    _k=(_e["from_kind"],_e["from_id"],_e["to_kind"],_e["to_id"],_e.get("field_id"),_e["status"])
    if _k in _seen: continue
    _seen.add(_k); _ded.append(_e)
print(f"边去重: {len(E)} -> {len(_ded)}")
E=_ded

json.dump({"resources": R, "edges": E, "depth3": depth3, "extra_l3": extra_l3},
          open("kb/.work/built.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

STAT = collections.Counter()
print(f"资源条目: {len(R)}  边: {len(E)}  第三层跳过边: {len(depth3)}")
print("按 depth:", dict(collections.Counter(x["depth"] for x in R)))
print("按 source_kind:", dict(collections.Counter(x["source_kind"] for x in R)))
print("按 sha256_state:", dict(collections.Counter(x["sha256_state"] for x in R)))
print("重复组:", {h[:12]: [i["resource_key"] for i in v] for h, v in by_hash.items() if len(v) > 1})
