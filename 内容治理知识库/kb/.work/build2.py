#!/usr/bin/env python3
"""L0 重新落库：资源模型构建（含第 3 层），按 dir_map 分类。
只读 .work/ 缓存（缓存来自源侧只读拉取），所有写入落 kb/。
"""
import json, os, re, hashlib, collections, sys

RUN = sys.argv[1]
KB = "kb/l0"
SCANNER = "0.5"
ENTRY_BASE, ENTRY_TBL, ENTRY_TBL_NAME = "GnRZbIuXraCzf0sGr2UcmZ62nfc", "tblMGtPfe8ZUsEdP", "材料收集"
EXCL = {"last_modified_time", "last_modified_by"}
URL_RE = re.compile(r'https?://[^\s\)\]\>"\']+')
SIB = {"知识库分类说明": "tblZP8jG4tiUL98C", "正面和负面样本": "tbld8qE92YaY38Yz", "规则库": "tblXsrMVkDNZ3oW8"}

registry = json.load(open(f"{KB}/registry/kb.json", encoding="utf-8"))
# L1 目标用本轮重解析的结果；兄弟表 schema 仍取自 l1.json 的 sibling_tables
l1 = json.load(open("kb/.work/l1.json", encoding="utf-8"))
l1["l1_targets"] = json.load(open("kb/.work/links-l1.json", encoding="utf-8"))
l1c = json.load(open("kb/.work/l1_content.json", encoding="utf-8"))
l3 = json.load(open("kb/.work/l3.json", encoding="utf-8"))
bases = json.load(open("kb/.work/bases/enum.json", encoding="utf-8"))
urlc = json.load(open("kb/.work/url_content.json", encoding="utf-8"))
gdoc = json.load(open("kb/.work/gdoc.json", encoding="utf-8"))
base_urls = json.load(open("kb/.work/base_urls.json", encoding="utf-8"))
parent_records = [json.loads(l) for l in open("kb/.work/材料收集.ndjson", encoding="utf-8") if l.strip()]
fields_meta = json.load(open(f"kb/.work/fields-{ENTRY_TBL}.json", encoding="utf-8"))["data"]["fields"]
fid_by_name = {f["name"]: f["id"] for f in fields_meta}
cat_recs = [json.loads(l) for l in open("kb/.work/分类说明.ndjson", encoding="utf-8") if l.strip()]
rules_recs = [json.loads(l) for l in open("kb/.work/规则库.ndjson", encoding="utf-8") if l.strip()]

for k, v in gdoc.items():
    urlc[k] = {"url": k, "status": v["status"], "sha256": v["sha256"], "sha256_state": v["sha256_state"],
               "http_bytes": v["http_bytes"], "text_chars": v["extracted_text_chars"], "title": v["title"],
               "status_reason": v["status_reason"], "extract_method": None}

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

def struct_hash(o):
    return sha(canon(o))

def rule_for(table, hint=None, field_name=None, scope_table=None, scoped=None):
    """R1→R24 顺序，第一条命中即停。资源级优先于表级兜底。"""
    for t in (hint or []):
        if t == "其它":
            continue
        for r in registry["rules"]:
            if (r["match_type"] == "field_value" and r.get("scope_table") == ENTRY_TBL_NAME
                    and r.get("match_value") == t):
                return r["kb_type"], r["id"], f"记录字段值:知识库分类={t}"
    for fname, fval in (scoped or {}).items():
        for r in registry["rules"]:
            if (r["match_type"] == "field_value" and r.get("scope_table") == scope_table
                    and r.get("pattern") == fname and r.get("match_value") == fval):
                return r["kb_type"], r["id"], f"记录字段值:{fname}={fval}"
    if field_name:
        for r in registry["rules"]:
            if r["match_type"] == "field_name" and r["pattern"] == field_name:
                return r["kb_type"], r["id"], f"字段名:{field_name}"
    for r in registry["rules"]:
        if r["match_type"] == "table_name" and r["pattern"] == table:
            if r.get("scope_table") and r["scope_table"] != table:
                continue
            return r["kb_type"], r["id"], f"表名:{table}"
    return "unknown", None, "no_rule_matched"

R, E, REC, P3 = [], [], [], []


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


def add(**kw):
    kw.setdefault("dup_of", None)
    kw.setdefault("moved_from", None)
    kw.setdefault("status_reason", "")
    kw.setdefault("status", "registered")
    kw.setdefault("revision", None)
    kw.setdefault("filter_passed", None)
    R.append(kw)
    return kw

# ============================================================ 1) 入口 Base + 入口表
sib_fields = l1["sibling_tables"]
add(resource_key=f"base:{ENTRY_BASE}", source_kind="feishu_bitable_base", table_name=None,
    table_id=None, record_id=None, field_name=None, field_id=None,
    entry_url=f"https://momcozy-in.feishu.cn/base/{ENTRY_BASE}",
    path="[内容治理]", depth=1, kb_type="unknown", matched_rule=None,
    kb_type_source="no_rule_matched:Base 是容器，不是知识本体",
    sha256=struct_hash({"base_token": ENTRY_BASE, "tables": sorted(list(SIB.values()) + [ENTRY_TBL])}),
    sha256_input="structure", sha256_state="full",
    extra={"note": "入口 Base 容器，仅登记身份与表清单"})
entry_fields = [{"field_id": f["id"], "field_name": f["name"], "type": f["type"],
                 "options": [o.get("name") for o in (f.get("options") or [])] or None,
                 "multiple": f.get("multiple")} for f in fields_meta]
kt_tbl, rid_tbl, kts_tbl = rule_for(ENTRY_TBL_NAME)
add(resource_key=f"bitable:{ENTRY_BASE}:table:{ENTRY_TBL}", source_kind="feishu_bitable_table",
    table_name=ENTRY_TBL_NAME, table_id=ENTRY_TBL, record_id=None, field_name=None, field_id=None,
    entry_url=f"https://momcozy-in.feishu.cn/base/{ENTRY_BASE}?table={ENTRY_TBL}",
    path="[内容治理/入口Base/材料收集]", depth=1,
    # §6.3-1（run 20260924-1512 修）：入口容器表的兜底也走真求值（R5 命中 → unknown 由规则给出）
    kb_type=kt_tbl, matched_rule=rid_tbl, kb_type_source=kts_tbl,
    sha256=struct_hash({"table_id": ENTRY_TBL, "table_name": ENTRY_TBL_NAME, "fields": entry_fields}),
    sha256_input="structure", sha256_state="full",
    extra={"records_count": len(parent_records), "field_count": len(entry_fields), "note": "筛选入口表本身"})
E.append({"from_kind": "feishu_bitable_base", "from_id": f"base:{ENTRY_BASE}",
          "to_kind": "feishu_bitable_table", "to_id": f"table:{ENTRY_TBL}", "depth": 1,
          "field_id": None, "status": "ok", "label": ENTRY_TBL_NAME})

# ============================================================ 2) 兄弟表
sib_counts = {"知识库分类说明": 5, "正面和负面样本": 125, "规则库": 50}
for tname, tid in SIB.items():
    st = sib_fields[tname]
    add(resource_key=f"bitable:{ENTRY_BASE}:table:{tid}", source_kind="feishu_bitable_table",
        table_name=tname, table_id=tid, record_id=None, field_name=None, field_id=None,
        entry_url=f"https://momcozy-in.feishu.cn/base/{ENTRY_BASE}?table={tid}",
        path=f"[内容治理/入口Base/{tname}]", depth=1,
        kb_type=rule_for(tname)[0], matched_rule=rule_for(tname)[1], kb_type_source=rule_for(tname)[2],
        sha256=struct_hash({"table_id": tid, "table_name": tname, "fields": [
            {"field_id": f["field_id"], "field_name": f["field_name"], "type": f["type"],
             "options": f.get("options")} for f in st["fields"]]}),
        sha256_input="structure", sha256_state="full",
        extra={"records_count": sib_counts[tname], "field_count": len(st["fields"]),
               "note": "入口 Base 内同级表，登记表结构；记录随结构下钻登记"})
    E.append({"from_kind": "feishu_bitable_base", "from_id": f"base:{ENTRY_BASE}",
              "to_kind": "feishu_bitable_table", "to_id": f"table:{tid}", "depth": 1,
              "field_id": None, "status": "ok", "label": tname})

# ============================================================ 3) 入口表筛选 + 通过记录登记
matched_ids, excluded = [], []
for r in parent_records:
    st = r.get("材料审核状态")
    vals = st if isinstance(st, list) else ([] if st in (None, "") else [st])
    if not vals:
        excluded.append((r["record_id"], "no_status"))
    elif "通过" in vals:
        matched_ids.append(r["record_id"])
    else:
        excluded.append((r["record_id"], "status_not_passed"))

matched_set = set(matched_ids)
for r in parent_records:
    rid = r["record_id"]
    if rid not in matched_set:
        REC.append({"record_id": rid, "table_name": ENTRY_TBL_NAME, "registered": False,
                    "reason": dict(excluded)[rid]})
        continue
    fvals = {fid_by_name[k]: v for k, v in r.items() if k in fid_by_name}
    kt, ridr, kts = rule_for(ENTRY_TBL_NAME, hint=r.get("知识库分类"))
    add(resource_key=f"bitable:{ENTRY_TBL}:{rid}", source_kind="feishu_bitable_record",
        table_name=ENTRY_TBL_NAME, table_id=ENTRY_TBL, record_id=rid, field_name=None, field_id=None,
        entry_url=f"https://momcozy-in.feishu.cn/base/{ENTRY_BASE}?table={ENTRY_TBL}&record={rid}",
        path="[内容治理/入口Base/材料收集]", depth=1,
        # §6.3-1（run 20260924-1512 修）：原为 kb_type="unknown", matched_rule="R5" 硬编码，
        # 把上面 rule_for() 求出的真结果丢弃了。改为用真结果；「要不要发射单元」改由
        # registry 的 container_policy(C1∧C2∧C3) 决定，不再拿 kb_type 当发射开关。
        kb_type=kt, matched_rule=ridr, kb_type_source=kts,
        sha256=rec_hash(fvals), sha256_input="record_fields", sha256_state="full",
        container=is_container(registry, f"bitable:{ENTRY_TBL}:{rid}", table_name=ENTRY_TBL_NAME),
        filter_passed=True, extra={"材料审核状态": r.get("材料审核状态"),
                                   "知识库分类": r.get("知识库分类"),
                                   "child_kb_types": r.get("知识库分类")})
    REC.append({"record_id": rid, "table_name": ENTRY_TBL_NAME, "registered": True, "reason": ""})

# ============================================================ 4) 第二层：入口记录 → link 目标
targets = {}
for t in l1["l1_targets"]:
    if t["record_id"] not in matched_set:
        continue
    targets.setdefault(t["resource_key"], []).append(t)

SRC_OF = {"wiki": {"docx": "feishu_doc", "file": "feishu_file", "bitable": "feishu_bitable_base"},
          "base": "feishu_bitable_base", "sheets": "feishu_sheet", "slides": "feishu_slides",
          "file": "feishu_file", "url": "url", "docx": "feishu_doc"}

for key, ts in targets.items():
    t = ts[0]
    rc = l1c.get(key, {})
    kt, ridr, kts = rule_for(t["kind"], hint=t.get("kb_type_hint") or [])
    src_kind = SRC_OF.get(t["kind"], {}).get(t.get("obj_type") or "", "url") \
        if t["kind"] == "wiki" else SRC_OF.get(t["kind"], "url")
    parents = [x["record_id"] for x in ts]
    state = rc.get("sha256_state") or ("full" if rc.get("sha256") else "unknown")
    add(resource_key=key, source_kind=src_kind, table_name=ENTRY_TBL_NAME, table_id=ENTRY_TBL,
        record_id=parents[0] if len(parents) == 1 else None,
        field_name=t.get("field_name"), field_id=t.get("field_id"), entry_url=t["url"],
        path="[内容治理/入口Base/材料收集/材料链接]", depth=2,
        kb_type=kt, matched_rule=ridr, kb_type_source=kts,
        sha256=rc.get("sha256"), sha256_input=rc.get("sha256_input"), sha256_state=state,
        revision=rc.get("revision"), status="registered",
        status_reason=rc.get("status_reason") or "", extra={
            "url_kind": t["kind"], "obj_type": t.get("obj_type"), "obj_token": t.get("obj_token"),
            "title": rc.get("title") or (t.get("node") or {}).get("title"), "chars": rc.get("chars"),
            "referenced_by_records": parents, "kb_type_hint_from_record": t.get("kb_type_hint"),
            "anchor_text": t.get("anchor_text"), "missing_scope": rc.get("missing_scope")})
    for p in parents:
        E.append({"from_kind": "feishu_bitable_record", "from_id": f"record:{p}",
                  "to_kind": src_kind, "to_id": key, "depth": 2, "field_id": t.get("field_id"),
                  "status": "ok" if state in ("full", "structure_only") else
                            ("forbidden" if state in ("no_scope", "forbidden") else "not_found"),
                  "label": t.get("field_name")})

# ============================================================ 5) 第二层：关联 Base → 表 → 记录
for bt, b in bases.items():
    bkey = f"base:{bt}"
    if bkey not in targets:
        continue
    for tb in b["tables"]:
        tk = f"bitable:{bt}:table:{tb['table_id']}"
        kt, ridr, kts = rule_for_table = rule_for(tb["table_name"])
        add(resource_key=tk, source_kind="feishu_bitable_table", table_name=tb["table_name"],
            table_id=tb["table_id"], record_id=None, field_name=None, field_id=None,
            entry_url=f"https://momcozy-in.feishu.cn/base/{bt}?table={tb['table_id']}",
            path=f"[内容治理/关联Base/{b['label']}/{tb['table_name']}]", depth=2,
            kb_type=kt, matched_rule=ridr, kb_type_source=kts,
            sha256=struct_hash({"table_id": tb["table_id"], "fields": [
                {"field_id": f["field_id"], "field_name": f["field_name"], "type": f["type"]}
                for f in tb["fields"]]}),
            sha256_input="structure", sha256_state="full", revision=tb.get("rev"),
            extra={"records_count": tb["records_count"], "field_count": len(tb["fields"]),
                   "records_sampled": tb["records_sampled"], "records_truncated": tb["records_truncated"]})
        E.append({"from_kind": "feishu_bitable_base", "from_id": bkey,
                  "to_kind": "feishu_bitable_table", "to_id": tk, "depth": 2,
                  "field_id": None, "status": "ok", "label": tb["table_name"]})
        for rec in tb["records"]:
            rid = rec["record_id"]
            fvals = {f["field_id"]: rec.get(f["field_name"]) for f in tb["fields"]
                     if f["field_name"] in rec}
            rk = f"bitable:{bt}:{rid}"
            add(resource_key=rk, source_kind="feishu_bitable_record", table_name=tb["table_name"],
                table_id=tb["table_id"], record_id=rid, field_name=None, field_id=None,
                entry_url=f"https://momcozy-in.feishu.cn/base/{bt}?table={tb['table_id']}&record={rid}",
                path=f"[内容治理/关联Base/{b['label']}/{tb['table_name']}]", depth=2,
                kb_type=kt, matched_rule=ridr, kb_type_source=kts,
                sha256=rec_hash(fvals), sha256_input="record_fields", sha256_state="full",
                extra={"source_base": bt, "source_table_id": tb["table_id"]})
            REC.append({"record_id": rid, "table_name": tb["table_name"], "registered": True,
                        "reason": "", "source_base": bt})
            E.append({"from_kind": "feishu_bitable_table", "from_id": tk,
                      "to_kind": "feishu_bitable_record", "to_id": rk, "depth": 2,
                      "field_id": None, "status": "ok", "label": tb["table_name"]})

# ============================================================ 6) 第二层：分类说明表记录
cat_fields = sib_fields["知识库分类说明"]["fields"]
for rec in cat_recs:
    rid = rec["record_id"]
    fvals = {f["field_id"]: rec.get(f["field_name"]) for f in cat_fields}
    kt, ridr, kts = rule_for("知识库分类说明", scope_table="知识库分类说明",
                             scoped={"知识库": rec.get("知识库")}, field_name="知识库")
    rk = f"bitable:{SIB['知识库分类说明']}:{rid}"
    add(resource_key=rk, source_kind="feishu_bitable_record", table_name="知识库分类说明",
        table_id=SIB["知识库分类说明"], record_id=rid, field_name=None, field_id=None,
        entry_url=f"https://momcozy-in.feishu.cn/base/{ENTRY_BASE}?table={SIB['知识库分类说明']}&record={rid}",
        path="[内容治理/入口Base/知识库分类说明]", depth=2,
        kb_type=kt, matched_rule=ridr, kb_type_source=kts,
        sha256=rec_hash(fvals), sha256_input="record_fields", sha256_state="full",
        extra={"知识库": rec.get("知识库"), "负责人": rec.get("负责人")})
    REC.append({"record_id": rid, "table_name": "知识库分类说明", "registered": True, "reason": ""})
    E.append({"from_kind": "feishu_bitable_table", "from_id": f"table:{SIB['知识库分类说明']}",
              "to_kind": "feishu_bitable_record", "to_id": rk, "depth": 2, "field_id": None,
              "status": "ok", "label": "知识库分类说明"})

# ============================================================ 7) 第二层：规则库来源链接 URL
src_urls = collections.Counter()
for rec in rules_recs:
    for m in URL_RE.finditer(str(rec.get("来源链接") or "")):
        src_urls[m.group(0)] += 1
for u, n in src_urls.most_common():
    uc = urlc.get(u, {})
    ok = uc.get("status") == "ok"
    add(resource_key=f"url:{u}", source_kind="url", table_name="规则库",
        table_id=SIB["规则库"], record_id=None, field_name="来源链接", field_id="fld1VehxHe",
        entry_url=u, path="[内容治理/入口Base/规则库/来源链接]", depth=2,
        kb_type="external_standard", matched_rule="R15", kb_type_source="字段名:来源链接",
        sha256=uc.get("sha256"), sha256_input="url_text" if ok else None,
        sha256_state="full" if ok else "unreachable", status="registered",
        status_reason="" if ok else (uc.get("status_reason") or "抓取未返回正文，无法指纹"),
        extra={"referenced_by_rules": n, "http_bytes": uc.get("http_bytes"),
               "text_chars": uc.get("text_chars"), "extract_method": uc.get("extract_method")})
    E.append({"from_kind": "feishu_bitable_table", "from_id": f"table:{SIB['规则库']}",
              "to_kind": "url", "to_id": f"url:{u}", "depth": 2, "field_id": "fld1VehxHe",
              "status": "ok" if ok else "not_found", "label": "来源链接"})

# ============================================================ 8) 第三层：完整链条（登记资源）
l1_keys = set(targets)
for x in l3["depth3"]:
    u, kind = x["url"], x["kind"]
    is_feishu = kind != "url"
    if not is_feishu:
        continue  # 外部网页链接只建边，另行处理
    m = re.search(r'feishu\.cn/(?:wiki|base|sheets|slides|file|docx|docs|drive/folder|record)/([A-Za-z0-9]+)', u)
    tok = m.group(1) if m else hashlib.sha256(u.encode()).hexdigest()[:12]
    src_kind = {"feishu_file": "feishu_file", "feishu_doc": "feishu_doc", "feishu_sheet": "feishu_sheet",
                "feishu_slides": "feishu_slides", "feishu_bitable_base": "feishu_bitable_base",
                "feishu_bitable_record": "feishu_bitable_record", "feishu_wiki_node": "feishu_file"}.get(kind, "feishu_file")
    key = f"{'file' if src_kind == 'feishu_file' else src_kind.replace('feishu_', '')}:{tok}"
    E.append({"from_kind": "feishu_doc" if x["from"].startswith("wiki:") else "url",
              "from_id": x["from"], "to_kind": src_kind, "to_id": key, "depth": 3,
              "field_id": None,
              "status": "forbidden" if key not in targets else "ok",
              "label": "第三层链接" + ("：该资源已在第二层登记，此处仅补链条" if key in targets
                                       else "：因缺 scope 未能读取，仅登记")})
    if key in targets:
        P3.append(key)
        continue
    kt, ridr, kts = rule_for("材料收集", hint=None, field_name=None)
    add(resource_key=key, source_kind=src_kind, table_name=ENTRY_TBL_NAME, table_id=ENTRY_TBL,
        record_id=None, field_name="材料链接", field_id="fldr4c8nnT", entry_url=u,
        path="[内容治理/入口Base/材料收集/材料链接/正文内链接]", depth=3,
        kb_type="unknown", matched_rule=None,
        kb_type_source="超出规则提取层数（前两层），仅登记不归类",
        sha256=None, sha256_input="file_bytes", sha256_state="no_scope", status="registered",
        status_reason="缺少 drive:file:download scope，无法取字节流，不计算 sha256",
        extra={"found_in": x["from"], "note": "第三层链接：完整链条已记录，规则提取不使用本层"})
    P3.append(key)

# ============================================================ 9) 第三层：外部链接只建边
depth3_external = [x for x in l3["depth3"] if x["kind"] == "url"]
for x in depth3_external:
    E.append({"from_kind": "feishu_doc" if x["from"].startswith("wiki:") else "url",
              "from_id": x["from"], "to_kind": "url", "to_id": x["url"], "depth": 3,
              "field_id": None, "status": "skipped_no_register",
              "label": "第三层外部链接：只记边不登记资源（不做 OCR/转写，正文多为 JS 渲染）"})

# 关联 Base 记录里的 URL 字段 → 第三层边（有界采样）
_urls = base_urls["unique_urls"] if isinstance(base_urls, dict) else []
_bad = [u for u in _urls if not re.match(r'^https?://[A-Za-z0-9.\-]+/', u)]
_good = [u for u in _urls if u not in _bad]
CAP = 60
for u in _good[:CAP]:
    E.append({"from_kind": "feishu_bitable_record", "from_id": "关联Base记录URL字段",
              "to_kind": "url", "to_id": u, "depth": 3, "field_id": None,
              "status": "skipped_no_register", "label": "关联 Base 记录 URL 字段，只记边不登记资源"})

# ============================================================ 10) dup_of + 去重
by_hash = collections.defaultdict(list)
for e in R:
    if e.get("sha256"):
        by_hash[e["sha256"]].append(e)
for h, items in by_hash.items():
    if len(items) > 1:
        head = sorted(items, key=lambda x: (x["depth"], x["resource_key"]))[0]["resource_key"]
        for it in sorted(items, key=lambda x: (x["depth"], x["resource_key"]))[1:]:
            it["dup_of"] = head

_seen, _ded = set(), []
for e in E:
    k = (e["from_kind"], e["from_id"], e["to_kind"], e["to_id"], e.get("field_id"), e["status"])
    if k in _seen:
        continue
    _seen.add(k)
    _ded.append(e)
E = _ded

out = {"resources": R, "edges": E, "records": REC, "excluded": excluded,
       "matched_ids": matched_ids, "l3_external": depth3_external, "l3_resources": P3,
       "base_url_stats": {"unique": len(_urls), "sampled": min(len(_good), CAP),
                          "truncated": max(0, len(_good) - CAP), "malformed": len(_bad),
                          "hosts": base_urls.get("hosts", {})}}
json.dump(out, open("kb/.work/built2.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

print(f"资源 {len(R)} | 记录留痕 {len(REC)}（登记 {sum(1 for x in REC if x['registered'])}，排除 {len(excluded)}）")
print(f"边 {len(E)}（d1={sum(1 for e in E if e['depth']==1)} d2={sum(1 for e in E if e['depth']==2)} d3={sum(1 for e in E if e['depth']==3)}）")
print("按 depth 资源:", dict(collections.Counter(x["depth"] for x in R)))
print("按 kb_type:", dict(collections.Counter(x["kb_type"] for x in R)))
print("按 source_kind:", dict(collections.Counter(x["source_kind"] for x in R)))
print("按 sha256_state:", dict(collections.Counter(x["sha256_state"] for x in R)))
print("重复组:", {h[:12]: len(v) for h, v in by_hash.items() if len(v) > 1})
