#!/usr/bin/env python3
"""L2 结构化切分：只拆不合。
四类切分器：① 词条 entry ② 修订对 revision_pair ③ 样本 sample ④ 属性 attribute，
外加外部标准的法条 clause 切分。
kb/l0 与 kb/l1 全程只读；产物只写 kb/l2。
"""
import json, os, re, hashlib, collections, sys, glob

RUN = sys.argv[1]
L0, L1, L2 = "kb/l0", "kb/l1", "kb/l2"
SPLITTER_VERSION = "l2-0.2"
registry = json.load(open(f"{L0}/registry/kb.json", encoding="utf-8"))
DIR_MAP, REV = registry["dir_map"], registry["dir_map_reverse"]
SCOPE = ["wording", "external_standard"]          # 本轮只切这两类
OUT_OF_SCOPE = [k for k in DIR_MAP.values() if k not in SCOPE]

os.makedirs(f"{L2}/index", exist_ok=True)
os.makedirs(f"{L2}/by_kb", exist_ok=True)
os.makedirs(f"{L2}/registry", exist_ok=True)
os.makedirs(f"{L2}/runs", exist_ok=True)

# ============================================================ 1) 取数：按「有没有文本内容」
def has_content(o):
    if o.get("segments") or o.get("tables"):
        return True
    for m in (o.get("media_refs") or []):
        if (m.get("ocr_char_count") or 0) > 0 or m.get("visual_description"):
            return True
    return False

prods = {}
for k in DIR_MAP.values():
    prods[k] = {}
    for p in glob.glob(f"{L1}/{REV[k]}/*.json"):
        o = json.load(open(p, encoding="utf-8"))
        prods[k][o["resource_id"]] = o
print("L1 资源总数:", {k: len(v) for k, v in prods.items()})

# L0 记录的 pair 关系（只读；用于形态②配对互指）
L0_PAIR = {}
for p in glob.glob(f"{L0}/records/*/*.json"):
    try:
        d = json.load(open(p, encoding="utf-8"))
    except Exception:
        continue
    pid = (d.get("pair") or {}).get("pair_id")
    if pid:
        L0_PAIR[d["record_id"]] = pid
print(f"L0 中带配对关系的记录：{len(L0_PAIR)} 条")

def segmap(o):
    """kind -> [segments]"""
    d = collections.defaultdict(list)
    for s in (o.get("segments") or []):
        d[s["kind"]].append(s)
    return d

def fv(o, name):
    for s in (o.get("segments") or []):
        if s.get("kind") == "field_value" and s.get("field_name") == name:
            return s
    return None

def fv_all(o, name):
    return [s for s in (o.get("segments") or [])
            if s.get("kind") == "field_value" and s.get("field_name") == name]

def clean(t):
    return re.sub(r'\s+', ' ', str(t or "")).strip()

# ============================================================ 2) 四类切分器
WRITE_FIELDS = ["Primary Text", "Headline", "广告名称"]          # 可直接引用的文案字段

def split_entry(o):
    """词条型：一个词条一个单元（Do not say / Say this instead 列表）。"""
    units = []
    for s in (o.get("segments") or []):
        k = s.get("kind")
        if k in ("field_value", "image_ocr", "image_visual", "paragraph", "list_item"):
            fname = s.get("field_name") or s.get("source_field")
            mm = {"kind": k, "field_name": fname}
            if looks_like_code(s["text"]):
                mm["content_quality_flag"] = "l1_extraction_includes_code"
                mm["content_quality_note"] = "L1 url_text 以 JS 胶水为主，非正文；不丢弃，仅标注"
            units.append(dict(unit_type="entry", text=clean(s["text"]), anchor=s["anchor"],
                              heading_path=(fname if k == "field_value" else None), meta=mm))
    for t in (o.get("tables") or []):
        for row in t["rows"]:
            units.append(dict(unit_type="entry", text=clean(row["text"]), anchor=row["anchor"],
                              heading_path=None, meta={"kind": "table_row"}))
    return units

def split_revision_pair(o):
    """案例型：一对修订 = 一个单元；前、后、原因三者不可拆散。"""
    before = fv_all(o, "修订位置（原文引用）") or fv_all(o, "风险原句示例")
    after = fv_all(o, "修订内容") or fv_all(o, "建议文案EN")
    reason = (fv_all(o, "修订原因") or fv_all(o, "中文释义") or fv_all(o, "判定理由")
              or fv_all(o, "规则依据与边界") or fv_all(o, "备注"))
    b = clean(" ".join(s["text"] for s in before))
    a = clean(" ".join(s["text"] for s in after))
    r = clean(" ".join(s["text"] for s in reason))
    if not (b or a):
        return []
    anchor = (before[0]["anchor"] if before else (after[0]["anchor"] if after else None))
    text = "\n".join(x for x in [f"【前】{b}" if b else "", f"【后】{a}" if a else "",
                                 f"【原因】{r}" if r else ""] if x)
    return [dict(unit_type="revision_pair", text=text, anchor=anchor,
                 heading_path=clean(o["source"].get("table_name")),
                 meta={"before": b, "after": a, "reason": r,
                       "after_anchor": (after[0]["anchor"] if after else None),
                       "pair_id": L0_PAIR.get(o["source"].get("record_id")),
                       "pair_fields": ["修订位置（原文引用）", "修订内容", "修订原因"]})]

JS_SIG = re.compile(r'function\s*\(|var\s+\w+\s*=|window\.|document\.|=>|\(function')

def looks_like_code(t):
    """识别「整段是 JS 胶水而非正文」。仅用于打标，不丢弃、不改写。"""
    if not t:
        return False
    n = len(JS_SIG.findall(t))
    zh = len(re.findall(r'[\u4e00-\u9fff]', t))
    return (n / max(1, len(t) / 1000)) > 5 and zh == 0

def split_long_single_line(txt, anchor):
    """正文落在同一物理行且过长时，按句切分；锚点补字符偏移，仍可回原文定位。
    只拆不合，不改写一字。"""
    if len(txt) < 800:
        return None
    parts, buf, start = [], [], 0
    BOUND = re.compile(r'(?<=[.!?。！？])\s+')
    for m in BOUND.finditer(txt):
        end = m.end()
        seg = txt[start:end]
        if seg.strip():
            parts.append((start, seg.strip()))
        start = end
    if start < len(txt) and txt[start:].strip():
        parts.append((start, txt[start:].strip()))
    if len(parts) <= 1:
        return None
    out = []
    for off, seg in parts:
        out.append(dict(unit_type="clause", text=seg, anchor=anchor,
                        heading_path=None,
                        meta={"kind": "paragraph", "split": "in_line_sentence",
                              "char_offset_in_source": off,
                              "anchor_precision": "segment_plus_char_offset",
                              "source_segment_chars": len(txt)}))
    return out

def split_clause(o):
    """一个法条一个单元：章/节/条；识别 第X条 / §X.X / Art. X / (1)(a)。"""
    units = []
    segs = o.get("segments") or []
    # 先按正文自然段切，再在段内用法条编号切分
    CLAUSE = re.compile(
        r'(第[〇零一二三四五六七八九十百千0-9]+条(?:之[一二三四五六七八九十])?'
        r'|§+\s*\d+(?:\.\d+)*'
        r'|Art(?:icle)?\.?\s*\d+[A-Za-z]?'
        r'|Section\s+\d+(?:\.\d+)*'
        r'|\b\d+\.\d+(?:\.\d+)*\s)')
    for s in segs:
        txt, anchor = s["text"], s["anchor"]
        k = s.get("kind")
        if k in ("image_ocr", "image_visual"):
            units.append(dict(unit_type="clause", text=clean(txt), anchor=anchor,
                              heading_path=None, meta={"kind": k}))
            continue
        if k == "field_value":
            units.append(dict(unit_type="entry", text=clean(txt), anchor=anchor,
                              heading_path=s.get("field_name"), meta={"kind": k,
                              "field_name": s.get("field_name")}))
            continue
        # ① 无换行的超长正文：按句切，锚点带字符偏移
        sent = split_long_single_line(txt, anchor)
        if sent:
            code = looks_like_code(txt)
            for u in sent:
                u["meta"]["content_quality_flag"] = (
                    "l1_extraction_includes_code" if code else "ok")
                if code:
                    u["meta"]["content_quality_note"] = (
                        "该段来自 L1 的 url_text（extract_method=json_literals），实测以 JS 胶水为主、"
                        "非政策正文。切分器只按句拆，不改写不丢弃；本单元可用性存疑，已在报告登记为 "
                        "L1 抽取质量问题（kb/l1 只读，不就地修）")
            units.extend(sent)
            continue
        # ② 法条编号切分
        parts = CLAUSE.split(txt)
        if len(parts) <= 1:
            if clean(txt):
                u = dict(unit_type="clause", text=clean(txt), anchor=anchor,
                         heading_path=None, meta={"kind": k, "split": "whole_segment"})
                if looks_like_code(txt):
                    u["meta"]["content_quality_flag"] = "l1_extraction_includes_code"
                    u["meta"]["content_quality_note"] = (
                        "L1 的 url_text 以 JS 胶水为主，非政策正文；不丢弃，仅标注")
                units.append(u)
            continue
        # parts = [前置, 编号1, 内容1, 编号2, 内容2, ...]
        head = parts[0].strip()
        i = 1
        while i + 1 <= len(parts) - 1:
            label, body = parts[i], parts[i + 1]
            units.append(dict(unit_type="clause", text=clean(label + " " + body),
                              anchor=anchor, heading_path=None,
                              meta={"kind": k, "clause_label": label.strip(),
                                    "split": "in_segment"}))
            i += 2
        if head and units:
            units[-1]["meta"]["leading_text"] = clean(head)
        elif head:
            units.append(dict(unit_type="clause", text=clean(head), anchor=anchor,
                              heading_path=None, meta={"kind": k, "split": "whole_segment"}))
    for t in (o.get("tables") or []):
        for row in t["rows"]:
            units.append(dict(unit_type="clause", text=clean(row["text"]), anchor=row["anchor"],
                              heading_path=None, meta={"kind": "table_row"}))
    # 法规特例：同一条被切成多段时按 clause_label 合并（物理续接，不是归纳）
    merged = []
    for u in units:
        lbl = (u.get("meta") or {}).get("clause_label")
        if lbl and merged and (merged[-1].get("meta") or {}).get("clause_label") == lbl:
            merged[-1]["text"] = merged[-1]["text"] + "\n" + u["text"]
            merged[-1]["meta"]["joined_parts"] = merged[-1]["meta"].get("joined_parts", 1) + 1
            continue
        merged.append(u)
    return merged

def split_sample(o):
    """一条样本 = 一个单元（内部正负样本库）。本轮不跑，切分器就绪。"""
    parts = []
    for s in (o.get("segments") or []):
        if s.get("kind") in ("image_ocr", "image_visual"):
            parts.append(f"[{s['kind']}] {clean(s['text'])}")
    for s in (o.get("segments") or []):
        if s.get("kind") == "field_value":
            parts.append(f"{s.get('field_name')}: {clean(s['text'])}")
    txt = "\n".join(p for p in parts if p)
    if not txt:
        return []
    anchor = next((s["anchor"] for s in (o.get("segments") or [])), None)
    pol = next((clean(s["text"]) for s in (o.get("segments") or [])
                if s.get("field_name") == "分类"), None)
    return [dict(unit_type="sample", text=txt, anchor=anchor,
                 heading_path=clean(o["source"].get("table_name")),
                 meta={"polarity": pol or "unknown",
                       "note": "极性取自源侧「分类」字段；无该字段则标 unknown"})]

def split_attribute(o):
    """一条属性 = 一个单元，按 SKU + 属性（产品描述库）。本轮不跑，切分器就绪。"""
    units = []
    sku = None
    for s in (o.get("segments") or []):
        if s.get("kind") != "field_value":
            continue
        fn = s.get("field_name") or ""
        if re.search(r'SKU|型号|产品名|品线', fn):
            sku = clean(s["text"])
            break
    for s in (o.get("segments") or []):
        if s.get("kind") != "field_value":
            continue
        units.append(dict(unit_type="attribute", text=clean(s["text"]), anchor=s["anchor"],
                          heading_path=f"{sku or 'unknown'}/{s.get('field_name')}",
                          meta={"sku": sku or "unknown", "attribute": s.get("field_name")}))
    return units

SPLITTERS = {
    "wording": {"entry": split_entry, "revision_pair": split_revision_pair},
    "external_standard": {"clause": split_clause, "entry": split_entry},
    "internal_sample": {"sample": split_sample},          # 就绪，本轮不跑
    "product_desc": {"attribute": split_attribute},        # 就绪，本轮不跑
}

# 表名 -> 用哪个切分器形态
TABLE_FORM = {
    "专家修订汇总表": "revision_pair",
    "风险文案改写建议库（分型号分渠道）": "revision_pair",
    "广告文案明细": "entry",
    "品线内容边界规则库": "entry",
    "W1卖点表达边界（品线反馈0910）": "entry",
}

# ============================================================ 3) 台账（幂等）
MAN = f"{L2}/manifest_l2.jsonl"
prev = {}
if os.path.exists(MAN):
    for l in open(MAN, encoding="utf-8"):
        if l.strip():
            r = json.loads(l)
            prev[(r["resource_id"], r["source_sha256"] or "", r["splitter_version"])] = r

# ============================================================ 4) 主流程
units_all, res_log = [], []
for kb in SCOPE:
    for rid, o in sorted(prods[kb].items()):
        sha = o.get("source_sha256") or ""
        key = (rid, sha, SPLITTER_VERSION)
        if key in prev and prev[key]["result"] in ("split", "skipped"):
            res_log.append({"resource_id": rid, "kb_type": kb, "result": "unchanged",
                            "units": prev[key]["unit_count"], "reason": ""})
            continue
        if not has_content(o):
            reason = o.get("status") or "no_content"
            kind = ("no_content_due_to_scope"
                    if o.get("status") in ("no_scope", "forbidden") or
                       (o.get("sha256_state") in ("no_scope", "forbidden")) else
                    "no_content_due_to_status" if o.get("status") in ("pending_fetch", "unreachable") else
                    "no_content_expected")
            res_log.append({"resource_id": rid, "kb_type": kb, "result": "skipped",
                            "units": 0, "reason": kind,
                            "detail": o.get("status_reason") or "", "status": o.get("status")})
            units_all.append(None)  # 占位，稍后剔除
            units_all.pop()
            continue
        table = o["source"].get("table_name")
        form = TABLE_FORM.get(table)
        fn = None
        if kb == "wording":
            fn = SPLITTERS["wording"].get(form) if form else None
            if fn is None:
                fn = split_entry
        elif form == "revision_pair":
            # 专家修订汇总表在 L0 归 internal_sample（规则 R19），但其形态是"修订对"，
            # 仍用 revision_pair 切分器，保证前/后/原因不拆散
            fn = split_revision_pair
        else:
            fn = split_clause
        got = fn(o)
        # 赋稳定 unit_id 与顺序
        for i, u in enumerate(got, 1):
            u["resource_id"] = rid
            u["kb_type"] = kb
            u["source_sha256"] = o.get("source_sha256")
            u["order_in_parent"] = i
            u["parent_unit_id"] = None
            u["unit_id"] = hashlib.sha1(
                f"{SPLITTER_VERSION}|{rid}|{sha}|{u['unit_type']}|{u['anchor']}|"
                f"{(u.get('meta') or {}).get('char_offset_in_source', '')}|{i}".encode()).hexdigest()[:20]
            u["char_count"] = len(u["text"])
            u.setdefault("heading_path", None)
            u["pair_ref"] = None
        units_all.extend(got)
        res_log.append({"resource_id": rid, "kb_type": kb, "result": "split", "units": len(got),
                        "reason": "", "form": form or "clause", "table": table})
        with open(MAN, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"resource_id": rid, "source_sha256": sha,
                                 "splitter_version": SPLITTER_VERSION, "kb_type": kb,
                                 "result": "split", "unit_count": len(got),
                                 "observed_at": RUN}, ensure_ascii=False, sort_keys=True) + "\n")
    # 记录跳过的（也写台账）
    for r in res_log:
        if r["kb_type"] == kb and r["result"] == "skipped":
            with open(MAN, "a", encoding="utf-8") as fh:
                fh.write(json.dumps({"resource_id": r["resource_id"], "source_sha256":
                    (prods[kb][r["resource_id"]].get("source_sha256") or ""),
                    "splitter_version": SPLITTER_VERSION, "kb_type": kb, "result": "skipped",
                    "unit_count": 0, "observed_at": RUN}, ensure_ascii=False, sort_keys=True) + "\n")

# 形态②配对互指（pair_ref）
bypair = collections.defaultdict(list)
for u in units_all:
    pid = (u.get("meta") or {}).get("pair_id")
    if u["unit_type"] == "revision_pair" and pid:
        bypair[pid].append(u)
paired = 0
for pid, us in bypair.items():
    if len(us) > 1:
        for i, u in enumerate(us):
            u["pair_ref"] = us[(i + 1) % len(us)]["unit_id"]
            (u["meta"])["pair_size"] = len(us)
            paired += 1

# ============================================================ 5) 落盘
with open(f"{L2}/units.jsonl", "w", encoding="utf-8") as fh:
    for u in units_all:
        fh.write(json.dumps(u, ensure_ascii=False, sort_keys=True) + "\n")
with open(f"{L2}/index/l2.jsonl", "w", encoding="utf-8") as fh:
    for u in units_all:
        fh.write(json.dumps({"unit_id": u["unit_id"], "kb_type": u["kb_type"], "anchor": u["anchor"],
                             "source_sha256": u["source_sha256"], "char_count": u["char_count"]},
                            ensure_ascii=False, sort_keys=True) + "\n")
for kb in SCOPE:
    d = f"{L2}/by_kb/{REV[kb]}"
    os.makedirs(d, exist_ok=True)
    grp = collections.defaultdict(list)
    for u in units_all:
        if u["kb_type"] == kb:
            grp[u["resource_id"]].append(u)
    for rid, us in grp.items():
        with open(f"{d}/{rid}.json", "w", encoding="utf-8") as fh:
            json.dump({"resource_id": rid, "kb_type": kb,
                       "source_sha256": us[0]["source_sha256"],
                       "unit_count": len(us), "units": us}, fh, ensure_ascii=False, indent=1)
            fh.write("\n")

json.dump({"res_log": res_log, "units": len(units_all), "paired": paired,
           "pairs": {k: len(v) for k, v in bypair.items()}},
          open("kb/.work/l2_core.json", "w", encoding="utf-8"), ensure_ascii=False)
print(f"单元总数 {len(units_all)} | 配对互指 {paired}")
for kb in SCOPE:
    rs = [r for r in res_log if r["kb_type"] == kb]
    print(f"  {kb:18s} 资源 {len(prods[kb]):4d} | 处理 {sum(1 for r in rs if r['result']=='split'):4d}"
          f" | 跳过 {sum(1 for r in rs if r['result']=='skipped'):4d}"
          f" | 单元 {sum(1 for u in units_all if u['kb_type']==kb):5d}")
