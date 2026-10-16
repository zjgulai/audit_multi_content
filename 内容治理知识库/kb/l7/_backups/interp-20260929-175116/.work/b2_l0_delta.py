#!/usr/bin/env python3
"""第 3/4/5 项：放开截断后补登记（只追加）。
增量：专家修订汇总表 395（首次因 bkey 前缀 bug 整表漏掉）＋ 广告文案明细 91 ＋ URL 128。
"""
import json, os, re, hashlib, collections, sys, glob
from datetime import datetime

RUN = sys.argv[1]
L0 = "kb/l0"
SCANNER = "0.5"
EXCL_HASH = {"last_modified_time", "last_modified_by"}
TABLES = {
    "专家修订汇总表": {"base": "SKkkbdZi9aRuMzs7ob0cpSYHnQg", "tid": "tbl8AI00JZO1iZtp",
                  "label": "内容公式与专家修订库", "pair": True,
                  "pair_fields": ("修订位置（原文引用）", "修订内容")},
    "广告文案明细": {"base": "Lk3Qb8y2QaVyZns6gprcVNE9nA0", "tid": "tblcbk4XiW6471YN",
                 "label": "广告文案风控库", "pair": False, "pair_fields": None},
}
START = datetime.now().timestamp()

def canon(o):
    return json.dumps(o, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

def sha(t):
    return hashlib.sha256(t.encode("utf-8")).hexdigest()

def rec_hash(fvals):
    items = sorted(((k, v) for k, v in fvals.items() if k not in EXCL_HASH), key=lambda x: x[0])
    return sha(canon([["field_id", k, "value", v] for k, v in items]))

def rid_of(rk):
    return re.sub(r'[^0-9A-Za-z._\-]+', '_', rk.replace(":", "__").replace("/", "_"))[:150]

registry = json.load(open(f"{L0}/registry/kb.json", encoding="utf-8"))
DIR_MAP, REV = registry["dir_map"], registry["dir_map_reverse"]
full = json.load(open("kb/.work/full_records.json", encoding="utf-8"))
fu = json.load(open("kb/.work/full_urls.json", encoding="utf-8"))
enum = json.load(open("kb/.work/bases/enum.json", encoding="utf-8"))

# ---------- 基线
before_files = {}
for d in DIR_MAP:
    for p in glob.glob(f"{L0}/{d}/*.json"):
        st = os.stat(p); before_files[p] = (st.st_mtime, st.st_size)
before_lines = [l.rstrip("\n") for l in open(f"{L0}/manifest.jsonl", encoding="utf-8") if l.strip()]
manifest_sha_before = sha("\n".join(before_lines) + "\n")
latest = {}
for l in before_lines:
    r = json.loads(l); latest[r["resource_key"]] = r
print(f"基线：资源文件 {len(before_files)} | 台账 {len(before_lines)} 行 sha256={manifest_sha_before[:16]}")

ops = []
new_res = []
by_table = collections.Counter()

for tname, meta in TABLES.items():
    d = full[tname]
    tid, bt = meta["tid"], meta["base"]
    # 字段 schema（从 enum 取）
    tb = next(t for e in enum.values() for t in e["tables"] if t["table_id"] == tid)
    fields = tb["fields"]
    fid_by_name = {f["field_name"]: f["field_id"] for f in fields}
    fname_by_fid = {f["field_id"]: f["field_name"] for f in fields}
    kt, rule = "internal_sample", "R19"
    if tname == "广告文案明细":
        kt, rule = "wording", "R20"
    rec_dir = f"{L0}/records/{tname}"
    os.makedirs(rec_dir, exist_ok=True)
    # 配对关系：按 (文章标题) 分组给出 pair_id
    pairs = collections.defaultdict(list)
    if meta["pair"]:
        for r in d["records"]:
            pairs[str(r.get("文章标题"))].append(r["record_id"])
    added = 0
    for r in d["records"]:
        rid = r["record_id"]
        rk = f"bitable:{bt}:{rid}"
        if rk in latest:
            continue
        fvals = {fid_by_name[k]: v for k, v in r.items() if k in fid_by_name}
        h = rec_hash(fvals)
        url = f"https://momcozy-in.feishu.cn/base/{bt}?table={tid}&record={rid}"
        pair_id = None
        if meta["pair"]:
            grp = pairs.get(str(r.get("文章标题")) or "", [])
            if len(grp) > 1:
                pair_id = f"pair:{tname}:{sha(str(r.get('文章标题')))[:12]}"
        # 记录留痕
        out = {"record_id": rid, "source_table": tname, "table_id": tid, "base_token": bt,
               "entry_url": url, "timezone": "Asia/Shanghai", "observed_at": RUN,
               "filter": {"result": "not_filtered", "note": "非筛选入口表；本次为放开截断后的全量补登记"},
               "fields": {k: {"field_id": fid_by_name.get(k), "field_type": None, "value": v,
                              "raw_verbatim": v} for k, v in r.items() if k != "record_id"},
               "pair": ({"pair_id": pair_id, "pair_role": "revision",
                         "pair_fields": list(meta["pair_fields"]),
                         "note": "同一文章标题下的多条专家修订构成一组「修订前→后」；"
                                 "修订位置（原文引用）= 原文片段，修订内容 = 改后文本"}
                        if pair_id else None),
               "raw_record": r, "note": "字段原值 verbatim。"}
        with open(f"{rec_dir}/{rid}.json", "w", encoding="utf-8") as fh:
            json.dump(out, fh, ensure_ascii=False, indent=1); fh.write("\n")
        new_res.append(dict(resource_key=rk, source_kind="feishu_bitable_record", table_name=tname,
            table_id=tid, record_id=rid, field_name=None, field_id=None, entry_url=url,
            path=f"[内容治理/关联Base/{meta['label']}/{tname}]", depth=2, kb_type=kt,
            matched_rule=rule, kb_type_source=f"表名:{tname}",
            sha256=h, sha256_input="record_fields", sha256_state="full", revision=None,
            status="registered", status_reason="", filter_passed=None,
            extra={"source_base": bt, "backfill_reason": "放开 200/表 采样上限后补全全量",
                   "pair_id": pair_id, "pair_fields": list(meta["pair_fields"]) if meta["pair_fields"] else None}))
        added += 1
    by_table[tname] = added
    print(f"  {tname}: 补登记 {added} 条（全量 {len(d['records'])}，已存在 {len(d['records'])-added}）")

# ---------- URL 全量（不设上限）
new_urls = []
for u, info in fu["unique"].items():
    rk = f"url:{u}"
    if rk in latest:
        continue
    new_urls.append((u, info))
print(f"  URL: 补登记 {len(new_urls)} 个（唯一 {len(fu['unique'])}，已存在 {len(fu['unique'])-len(new_urls)}）")

json.dump({"new_res": new_res, "new_urls": new_urls, "by_table": dict(by_table),
           "before_lines": len(before_lines), "manifest_sha_before": manifest_sha_before,
           "before_files": {k: list(v) for k, v in before_files.items()}, "start_ts": START},
          open("kb/.work/b2_l0_delta.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("增量数据已写出")
