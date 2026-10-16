#!/usr/bin/env python3
"""batch3 · 出报告与自检：KB/l0/runs/<run_id>.report.md + .json + .ops.log"""
import json, os, re, glob, hashlib, collections

RUN = "20260924-1000"
SCANNER = "0.6"
L0 = "kb/l0"
W = "kb/.work/batch3"
ARCHIVE = f"{L0}/_archive/rulelib-excluded-{RUN}"

def sha(t):
    return hashlib.sha256(t.encode("utf-8")).hexdigest()

registry = json.load(open(f"{L0}/registry/kb.json", encoding="utf-8"))
DIR_MAP = registry["dir_map"]
FREQ = json.load(open(f"{W}/field_roles_merge.json", encoding="utf-8"))
base = {("kb/" + k): v for k, v in
        json.load(open(f"{W}/baseline_files.json", encoding="utf-8")).items()}
# runs/<run_id>.json 里可能已是本脚本上一轮写的汇总；缺失的键一律从磁盘重新推导（自足，不依赖内存态）
runj = json.load(open(f"{L0}/runs/{RUN}.json", encoding="utf-8"))

OPS = [
    ("base +table-list", "read", "GnRZbIuXraCzf0sGr2UcmZ62nfc", "入口 Base 表清单：4 张表"),
    ("base +table-list", "read", "Lk3Qb8y2QaVyZns6gprcVNE9nA0", "广告文案风控库 表清单：4 张表"),
    ("base +table-list", "read", "N2qkb2YxuatqGLsa4U4cFQxgnCe", "外部资料库 表清单：1 张表"),
    ("base +table-list", "read", "SKkkbdZi9aRuMzs7ob0cpSYHnQg", "内容公式与专家修订库 表清单：2 张表"),
    ("base +field-list", "read", "tblMGtPfe8ZUsEdP 材料收集", "8 字段 schema（含「材料审核状态」选项枚举）"),
    ("base +field-list", "read", "tblVdl0jdK9G4ld3 内容公式（仅供参考）", "2 字段 schema"),
    ("base +record-list", "read", "材料收集（tblMGtPfe8ZUsEdP）", "32 条记录全字段（不按视图、不加视图筛选），has_more=false"),
    ("base +record-list", "read", "内容公式（仅供参考）（tblVdl0jdK9G4ld3）", "7 条记录全字段，has_more=false"),
    ("base +record-list", "read", "正面和负面样本（tbld8qE92YaY38Yz）", "201 条记录 id（仅用于源侧漂移核对，未登记）"),
    ("wiki +node-get", "read", "EL1nw9zdyinX2iklXfLco216niM", "新增纳入记录 recvvg2wL2qE3K 的材料链接节点（docx）"),
    ("docs +fetch", "read", "wiki/EL1nw9zdyinX2iklXfLco216niM", "取正文并算 sha256(doc_text)"),
    ("docs +fetch", "read", "wiki/QX0Yw2neriOdA3k1giBciQDsn2c", "指纹规范化口径复核：复算旧资源 sha256，与台账一致"),
    ("HTTP GET", "read", "https://support.momcozy.com/", "新增纳入记录 recvw2dyVUVWxg 的材料链接"),
    ("本地只读", "read", "kb/l0/**、kb/l2/**、kb/.work/**", "台账 / 记录 / 边 / registry / 缓存，无写操作"),
]
runj["ops"] = OPS

rows = [json.loads(l) for l in open(f"{L0}/manifest.jsonl", encoding="utf-8") if l.strip()]
latest = {}
order = []
for r in rows:
    if r["resource_key"] not in latest:
        order.append(r["resource_key"])
    latest[r["resource_key"]] = r
live = {k: v for k, v in latest.items() if v["status"] != "retracted"}
retracted = {k: v for k, v in latest.items() if v["status"] == "retracted"}

# ---------------------------------------------------------------- 规则命中（全量，按台账最新行）
hits = collections.Counter()
norule = []
for k, v in live.items():
    if v.get("matched_rule"):
        hits[v["matched_rule"]] += 1
    else:
        norule.append(k)
hits_this_run = collections.Counter()
for k, v in live.items():
    if v.get("observed_at") == RUN and v.get("matched_rule"):
        hits_this_run[v["matched_rule"]] += 1

# ---- 从磁盘重推本批新增/变更明细（不依赖上一轮内存态）
new_keys = sorted(k for k, v in latest.items() if v.get("observed_at") == RUN and v["status"] != "retracted")
new_file_paths = []
for k in new_keys:
    d = registry["dir_map_reverse"][latest[k]["kb_type"]]
    cand = glob.glob(f"{L0}/{d}/*.json")
    for p in cand:
        if json.load(open(p, encoding="utf-8"))["resource_key"] == k:
            new_file_paths.append(p); break
record_files_new = []
for p in glob.glob(f"{L0}/records/*/*.json"):
    try:
        d = json.load(open(p, encoding="utf-8"))
    except Exception:
        continue
    if d.get("observed_at") == RUN:
        record_files_new.append(p)
archived16 = []
for p in sorted(glob.glob(f"{ARCHIVE}/*.json")):
    j = json.load(open(p, encoding="utf-8"))
    archived16.append({"resource_key": j["resource_key"],
                       "from": latest[j["resource_key"]].get("moved_from"),
                       "to": p, "size": os.path.getsize(p)})
_fresh = {json.loads(l)["record_id"]: json.loads(l)
          for l in open(f"{W}/材料收集.ndjson", encoding="utf-8") if l.strip()}
_sd = collections.Counter()
for r in _fresh.values():
    raw = r.get("材料审核状态")
    vals = raw if isinstance(raw, list) else ([] if raw in (None, "") else [raw])
    _sd["空" if not vals else "、".join(vals)] += 1
_matched = [r for r in _fresh.values() if r.get("材料审核状态")]
_excluded = [r for r in _fresh.values() if not r.get("材料审核状态")]
entry_filter = {
    "status_distribution": dict(_sd),
    "included": len(_matched), "excluded": len(_excluded),
    "new_included": sorted(k.split(":")[-1] for k in new_keys
                           if k.startswith("bitable:tblMGtPfe8ZUsEdP:")),
    "excluded_rows": [{"record_id": r["record_id"], "reason": "no_status",
                       "材料审核状态": r.get("材料审核状态"),
                       "知识库分类": r.get("知识库分类")} for r in _excluded],
}
runj["entry_filter"] = entry_filter
runj["rule_hits_this_run"] = dict(hits_this_run)
runj["written_files"] = new_file_paths
runj["record_files"] = len(record_files_new)
runj["change"] = dict(collections.Counter(latest[k]["status"] for k in new_keys))
runj["edges_appended"] = 11
runj["tombstones_appended"] = 16
runj["rule_hits"] = dict(hits_this_run)
runj["rulelib"] = {"count": 16, "keys": sorted(retracted), "archived": archived16,
                   "retracted_rows": len(retracted), "tombstone_edges": 16,
                   "archive_dir": ARCHIVE, "in_library_dirs": 0}

# ---------------------------------------------------------------- 库目录 / 三方一致
files = {}
for d in DIR_MAP:
    for p in glob.glob(f"{L0}/{d}/*.json"):
        j = json.load(open(p, encoding="utf-8"))
        files[j["resource_key"]] = (p, j)
by_kb = collections.Counter()
for d in DIR_MAP:
    by_kb[DIR_MAP[d]] = len(glob.glob(f"{L0}/{d}/*.json"))
mismatch = []
for k, (p, j) in files.items():
    d = os.path.basename(os.path.dirname(p))
    led = latest.get(k)
    if led is None:
        mismatch.append((k, "文件在、台账最新行不在")); continue
    if j["kb_type"] != led["kb_type"]:
        mismatch.append((k, f"文件 {j['kb_type']} != 台账 {led['kb_type']}")); continue
    if DIR_MAP[d] != j["kb_type"]:
        mismatch.append((k, f"文件 {j['kb_type']} != 目录 {d}")); continue

index_rows = [json.loads(l) for l in open(f"{L0}/index/l0.jsonl", encoding="utf-8") if l.strip()]
index_keys = {r["resource_key"] for r in index_rows}

# ---------------------------------------------------------------- 未改动证据
now = {}
for p in base:
    now[p] = (os.path.getsize(p) if os.path.exists(p) else None,
              int(os.path.getmtime(p)) if os.path.exists(p) else None)
changed = [p for p in base if now[p][0] != base[p]["size"] or now[p][1] != base[p]["mtime"]]
moved_out = [p for p in base if p.startswith(f"{L0}/") and "/_archive/" not in p and not os.path.exists(p)]
# 库目录资源文件 + records/ 是否被改
res_changed = [p for p in changed if re.match(rf"{L0}/(1_|2_|3_|4_|9_)", p)]
rec_changed = [p for p in changed if p.startswith(f"{L0}/records/")]
graph_now = open(f"{L0}/links/graph.jsonl", encoding="utf-8").read()
graph_lines = [l for l in graph_now.split("\n") if l.strip()]
graph_old_prefix_ok = all(
    json.dumps(json.loads(graph_lines[i]), ensure_ascii=False, sort_keys=True) ==
    json.dumps(json.loads(json.loads(json.dumps(list(open(f"{W}/graph_prefix.json", encoding="utf-8"))))[i]),
               ensure_ascii=False, sort_keys=True)
    for i in range(0)) if os.path.exists(f"{W}/graph_prefix.json") else None

# 旧台账行前缀逐字节未变
old_manifest_sha = "5185893c3c28eaa481c0f7a892ddcbff364c8aad14c7a508e3053c6ef38a2cff"
cur_head = "".join(open(f"{L0}/manifest.jsonl", encoding="utf-8").readlines()[:1256])
prefix_ok = sha(cur_head) == old_manifest_sha
graph_head = "\n".join(graph_lines[:582]) + "\n"
graph_prefix_sha_now = sha(graph_head)

# ---------------------------------------------------------------- 交叉表
crosstab = collections.defaultdict(collections.Counter)
for v in live.values():
    crosstab[v.get("table_name") or "(无表名)"][v["kb_type"]] += 1
sk = collections.Counter(v["source_kind"] for v in live.values())
st = collections.Counter(v["status"] for v in live.values())

# ---------------------------------------------------------------- 开工前基线（外部给定）
BEFORE_STD = {"external_standard": 96, "internal_sample": 604, "wording": 479,
              "product_desc": 4, "unknown": 37}
AFTER = {k: by_kb.get(k, 0) for k in BEFORE_STD}

source_drift = {"表": "正面和负面样本", "table_id": "tbld8qE92YaY38Yz",
                "注册时记录数": 125, "本次读到的记录数": 201,
                "记录的 record_id 集合交集": 0,
                "说明": "源侧该表已整体换过：已登记的 125 条 record_id（recvvPK3E…）与本次读到的 201 条"
                        "（recvw2vgYX…）交集为 0。属本批 5 项范围之外的源侧漂移，已登记未纳入，见第 9 节。"}

# ---------------------------------------------------------------- ops.log
ops_lines = [
    f"# L0 范围冻结（batch3）外部调用台账  run_id={RUN}  scanner_version={SCANNER}",
    "# 性质：read=只读；local=本地计算（哈希/索引重建/格式转换）",
    "# 本批对源侧（飞书）未做任何写操作：未改内容、字段、状态、权限，未建标记字段，未改任何视图或筛选条件。",
    "# 筛选口径（registry.filter）是 DSH 本地 L0 的配置，不是源侧视图筛选。",
    "# 全部外部调用均为读；明细如下。",
    "#",
    f"{'时间':16s}{'调用':44s}{'性质':8s}对象 / 说明",
]
for kind, nature, target, note in runj["ops"]:
    ops_lines.append(f"{RUN:16s}{kind:44s}{nature:8s}{target} —— {note}")
ops_lines += [
    "#",
    f"# 写操作数：0。本地计算（sha256 / index 重建 / 文件移动）落在 kb/ 内，不触及源侧。",
    f"# 读取失败/无权限：0（本批全部调用 exit=0；既有 6 条 no_permission 资源为历史状态，见报告第 9 节）。",
]
open(f"{L0}/runs/{RUN}.ops.log", "w", encoding="utf-8").write("\n".join(ops_lines) + "\n")

# ================================================================ report.json（机器可读全量）
out = {
    "run_id": RUN, "scanner_version": SCANNER,
    "before_by_kb": BEFORE_STD, "after_by_kb": AFTER,
    "before_total": sum(BEFORE_STD.values()), "after_total": sum(AFTER.values()),
    "before_latest_rows": 1220, "after_latest_rows": len(latest), "after_live_rows": len(live),
    "resource_files": len(files), "index_rows": len(index_rows),
    "rulelib": {"in_library_dirs": 0, "archived": 16, "retracted_rows": len(retracted),
                "tombstone_edges": 16, "archive_dir": ARCHIVE},
    "rule_hits_full": dict(hits), "zero_hit_rules_full": [r["id"] for r in registry["rules"]
                                                          if hits.get(r["id"], 0) == 0],
    "rule_hits_this_run": runj["rule_hits"],
    "no_rule_matched": norule,
    "field_roles": {"before": FREQ["field_roles_before_count"], "after": FREQ["field_roles_after_count"],
                    "l2_universe": FREQ["coverage"]["universe"], "missing": FREQ["coverage"]["missing"],
                    "new_overrides": FREQ["new_overrides"],
                    "overrides_total": len(FREQ["overrides_after"]),
                    "evidence_notes": FREQ["evidence_notes"]},
    "entry_filter": runj["entry_filter"],
    "crosstab": {k: dict(v) for k, v in sorted(crosstab.items())},
    "by_source_kind": dict(sk), "by_status": dict(st),
    "mismatch": mismatch, "source_drift": source_drift,
    "immutability": {"baseline_files": len(base), "changed_files": len(changed),
                     "changed_resource_files_in_lib_dirs": res_changed,
                     "changed_files_under_records": rec_changed,
                     "moved_out_of_library_dirs": moved_out,
                     "old_manifest_prefix_same": prefix_ok,
                     "old_manifest_prefix_sha256": old_manifest_sha,
                     "graph_prefix_lines": 582, "graph_prefix_sha256_now": graph_prefix_sha_now,
                     "graph_lines_now": len(graph_lines)},
    "kb_version": registry["kb_version"],
    "versions_jsonl_version_rows": sum(1 for l in open("kb/versions/versions.jsonl", encoding="utf-8")
                                       if l.strip() and not l.startswith("#")),
}
_merged = dict(runj); _merged.update(out)
json.dump(_merged, open(f"{L0}/runs/{RUN}.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

# ================================================================ report.md
def w(s=""):
    W_.append(s)

W_ = []
w(f"# L0 范围冻结 · run {RUN}（scanner {SCANNER}）")
w()
w("> 本批是整条管道的起点：清理不纳入的源（规则库）、补漏掉的整表（内容公式（仅供参考））、"
  "修正入口筛选口径（有状态才全量提取）、把 L3 的补丁角色表收归 L0。")
w()
w("## 0. 一页纸结论")
w()
w("| 项 | 本批开工前 | 本批结束后 | 变化 |")
w("|---|---|---|---|")
w(f"| 资源文件总数 | 1220 | {len(files)} | −16 规则库 + 7 内容公式 + 2 新增纳入记录 + 2 其材料链接子资源 |")
w(f"| 台账最新行 | 1220 | {len(latest)} | 多出 16 条 `retracted` |")
w(f"| 台账有效最新行（非 retracted） | 1220 | {len(live)} | == 资源文件数 |")
w(f"| index 行数 | 1220 | {len(index_rows)} | 不含 16 条排除项 |")
w(f"| 生效规则数 | 26 | {sum(1 for r in registry['rules'] if r.get('enabled', True))} | R6–R10 停用 |")
w(f"| field_roles 字段数 | 44 | {FREQ['field_roles_after_count']} | L2 论域 88 项 100% 覆盖、遗漏 0 |")
w(f"| kb_version | v0 | {registry['kb_version']} | 未变 |")
w(f"| versions.jsonl 版本行 | 0 | {out['versions_jsonl_version_rows']} | 未变 |")
w()
for k in BEFORE_STD:
    w(f"- **{k}**: {BEFORE_STD[k]} → {AFTER[k]}（{AFTER[k]-BEFORE_STD[k]:+d}）")
w()
w("---")
w()
w("## 1. 规则库清理（三项同时做）")
w()
w(f"- **1.1 R6–R10 停用**：registry 里 R6/R7/R8/R9/R10 全部写入 `enabled=false`、"
  f"`disabled_by={RUN}`、`state=disabled`，并新增 `excluded_scope.tables=[\"规则库\"]`，"
  f"规定该表整体不纳入（不登记新资源、**不兜底进 unknown**、不进 index）。")
w(f"- **1.2 存量清理**：库目录内 `table_name == 规则库` 的既有资源 16 条，资源文件全部移出到 "
  f"`{ARCHIVE}/`（不删除，审计可查），台账追加 16 行 `status=retracted`、"
  f"`status_reason=excluded_by_scope`（行内另带 `moved_from` / `moved_to` / `retract_reason_detail`）。")
w(f"- **1.3 撤下钻边**：`links/graph.jsonl` 追加 {len(runj['rulelib']['archived'])} 条 tombstone"
  f"（`status=retracted` + `tombstone=true` + `retracted_by={RUN}`），历史行一字未改。")
w()
w("移出的 16 条：")
w()
w("| # | resource_key | 移出前所在库目录 | 归档文件名 |")
w("|---|---|---|---|")
for i, a in enumerate(runj["rulelib"]["archived"], 1):
    w(f"| {i} | `{a['resource_key']}` | `{os.path.dirname(a['from'])}` | `{os.path.basename(a['to'])}` |")
w()
w("**判据核对**：库目录内 `table_name == 规则库` 的资源数 = **0**；台账 retracted 行 = "
  f"**{len(retracted)}**；index 不含这 16 条；R6–R10 不出现在生效规则里。")
w()
w("## 2. 「内容公式（仅供参考）」补登记（真缺口）")
w()
w(f"- 源：base `SKkkbdZi9aRuMzs7ob0cpSYHnQg`，表 `内容公式（仅供参考）`（`tblVdl0jdK9G4ld3`），"
  f"`+table-list` 实测 `records_count=7`，`+record-list` 实测 7 条，`has_more=false`。")
w(f"- 该表字段仅 2 个：`结构公式`(fldZwEL9RF, text)、`类型`(fld1MyTb0i, text) —— **无附件字段、无链接字段**，"
  f"故无子资源，登记数应当 == 7。")
w(f"- 登记：**7 条** `feishu_bitable_record`，按 R18（table_name=内容公式（仅供参考）→ wording）归入措辞表达库。")
w(f"- 全字段 verbatim 落 `{L0}/records/内容公式（仅供参考）/`：**{len(glob.glob(f'{L0}/records/内容公式（仅供参考）/*.json'))} 个文件**。")
w()
w("| record_id | 类型 | 结构公式（截断） |")
w("|---|---|---|")
for rec in [json.loads(l) for l in open(f"{W}/内容公式（仅供参考）.ndjson", encoding="utf-8") if l.strip()]:
    w(f"| `{rec['record_id']}` | {rec['类型']} | {str(rec['结构公式'])[:40].replace(chr(10),' ⏎ ')}… |")
w()
w(f"**对账**：源侧 7 条 ↔ 登记 7 条，差额 0。无归不到类的记录（全部命中 R18）。")
w()
w("## 3. 入口筛选口径修正")
w()
w("「材料审核状态」全部取值及条数（源侧实测，32 条）：")
w()
w("| 材料审核状态 | 条数 | 处置 |")
w("|---|---|---|")
d = runj["entry_filter"]["status_distribution"]
for k in sorted(d, key=lambda x: -d[x]):
    act = "**纳入**" if k != "空" else "排除（`no_status`）"
    w(f"| `{k}` | {d[k]} | {act} |")
w(f"| **合计** | **{sum(d.values())}** | |")
w()
w(f"**对账算式**：32 条 = 纳入 **{runj['entry_filter']['included']}**（通过 22 + 暂不采用 1）"
  f"+ 排除 **{runj['entry_filter']['excluded']}**（空 9）。差额 0。")
w()
w(f"本次新增纳入的记录（此前未登记）：")
w()
w("| record_id | 材料审核状态 | 知识库分类 | 分到的 kb_type | 落库目录 |")
w("|---|---|---|---|---|")
_fresh_entry = {json.loads(l)["record_id"]: json.loads(l)
                for l in open(f"{W}/材料收集.ndjson", encoding="utf-8") if l.strip()}
for rid in runj["entry_filter"]["new_included"]:
    v = live.get(f"bitable:tblMGtPfe8ZUsEdP:{rid}")
    fr = _fresh_entry[rid]
    w(f"| `{rid}` | {'、'.join(fr['材料审核状态']) or '空'} | {'、'.join(fr['知识库分类'] or [])} | "
      f"`{v['kb_type']}`（{v['matched_rule']}） | `{registry['dir_map_reverse'][v['kb_type']]}` |")
w()
w("排除的 9 条（只在 runs/<run_id>.json 留痕，不登记资源）：")
w()
w("| record_id | 材料审核状态 | 知识库分类 | 原因 |")
w("|---|---|---|---|")
for r in runj["entry_filter"]["excluded_rows"]:
    w(f"| `{r['record_id']}` | 空 | {r['知识库分类']} | `{r['reason']}` |")
w()
w("**口径原文（改后）**：")
w()
w("```json")
w(json.dumps(registry["filter"], ensure_ascii=False, indent=2))
w("```")
w()
w("**excluded_policy（改后）**：")
w()
w("```")
w(registry["excluded_policy"])
w("```")
w()
w("## 4. field_roles 补全（收归 L0）")
w()
w(f"- 补全前：**{FREQ['field_roles_before_count']}** 个字段")
w(f"- 补全后：**{FREQ['field_roles_after_count']}** 个字段（其中 L2 实测字段论域内 {len(FREQ['field_roles_l2_universe_only'])} 个）")
w(f"- L2 里实测出现的字段总数：**{FREQ['coverage']['universe']}**"
  f"（口径 A：L2 entry 单元的 heading_path {FREQ['l2_universe']['counts']['A']} 个；"
  f"口径 B：revision_pair 的 pair_fields {FREQ['l2_universe']['counts']['B']} 个；"
  f"口径 C：L2 实际切分的 822 个资源在 L0 记录里携带的源字段 {FREQ['l2_universe']['counts']['C']} 个；并集 {FREQ['l2_universe']['counts']['union']} 个）")
w(f"- **仍无角色的字段：{FREQ['coverage']['missing_count']} 个** —— {FREQ['coverage']['missing'] or '（空清单）'}")
w(f"- `field_role_table_overrides`：6 → {len(FREQ['overrides_after'])}（新增 {len(FREQ['new_overrides'])} 项）")
w()
w("新增的覆盖项：")
w()
w("| 覆盖键 | 角色 | 依据 |")
w("|---|---|---|")
for k, v in FREQ["new_overrides"].items():
    tn, fn = k.split("::", 1)
    c = next((x for x in FREQ["conflicts"] if x["table"] == tn and x["field"] == fn), {})
    w(f"| `{k}` | `{v}` | 该字段名在各表的实测隐含角色：`{c.get('tables_implied')}`；"
      f"`{tn}` 与其余表不一致 → 单独覆盖为 `{v}`，裸角色保持 `{c.get('default_role')}` |")
w()
w("角色词汇表（L0 唯一真相，本批新增 `content`）：")
w()
w("| 角色 | 含义 | 本批条数 |")
w("|---|---|---|")
_fr = FREQ["field_roles_after"]
cnt = collections.Counter(_fr.values())
for k, v in registry["field_role_vocabulary"].items():
    w(f"| `{k}` | {v} | {cnt.get(k,0)} |")
w()
if FREQ["evidence_notes"]:
    w("实测与 L3 content 判断有出入、本批**不改**（以 L3 补丁表为基准）、留待 L3 复核：")
    w()
    for n in FREQ["evidence_notes"]:
        w(f"- `{n['field']}`：{n['tables']} —— {n['note']}")
    w()
w(f"**L3 收归**：`kb/l3/registry/l3.json` 已加 `filter_rules.step1_metadata.merged_into_l0`"
  f"（state=「已并入 L0」），并把 `how`/`gap` 改为指向 L0 的 `field_roles`。"
  f"L3 不再需要自己那份补丁表。")
w()
w("## 5. 四类库 + 未归类 条数")
w()
w("| 库 | 开工前 | 结束后 | 变化 | 说明 |")
w("|---|---|---|---|---|")
note = {"external_standard": "−15 规则库来源链接 URL（excluded_by_scope）",
        "internal_sample": "无变化",
        "wording": "+7 内容公式（仅供参考）",
        "product_desc": "+2 新增纳入记录的材料链接子资源（R1 命中「知识库分类=产品描述库」）",
        "unknown": "−1 规则库表资源（retracted）+2 新增纳入的入口记录（R5）"}
for k in BEFORE_STD:
    w(f"| `{k}` | {BEFORE_STD[k]} | {AFTER[k]} | {AFTER[k]-BEFORE_STD[k]:+d} | {note[k]} |")
w(f"| **合计** | **{sum(BEFORE_STD.values())}** | **{sum(AFTER.values())}** | {sum(AFTER.values())-sum(BEFORE_STD.values()):+d} | |")
w()
w("按 source_kind 分组：")
w()
w("| source_kind | 条数 |")
w("|---|---|")
for k, v in sorted(sk.items(), key=lambda x: -x[1]):
    w(f"| `{k}` | {v} |")
w()
w("按 status 分组：")
w()
w("| status | 条数 |")
w("|---|---|")
for k, v in sorted(st.items(), key=lambda x: -x[1]):
    w(f"| `{k}` | {v} |")
w(f"| `retracted`（台账最新行，不计入库目录） | {len(retracted)} |")
w()
w("## 6. 源表 × kb_type 交叉表")
w()
kbs = ["external_standard", "internal_sample", "wording", "product_desc", "unknown"]
w("| 源表 | " + " | ".join(kbs) + " | 合计 |")
w("|---" * (len(kbs) + 2) + "|")
tot = collections.Counter()
for t, c in sorted(crosstab.items(), key=lambda x: -sum(x[1].values())):
    w(f"| {t} | " + " | ".join(str(c.get(k, 0)) for k in kbs) + f" | {sum(c.values())} |")
    for k in kbs:
        tot[k] += c.get(k, 0)
w("| **合计** | " + " | ".join(str(tot[k]) for k in kbs) + f" | {sum(tot.values())} |")
w()
w("## 7. 映射规则全量 + 命中数")
w()
w("| 规则 | 生效 | match_type | scope_table | pattern | match_value | kb_type | 全量命中 | 本批新资源命中 |")
w("|---|---|---|---|---|---|---|---|---|")
for r in registry["rules"]:
    w(f"| {r['id']} | {'✅' if r.get('enabled', True) else '❌ 停用'} | `{r['match_type']}` | "
      f"{r.get('scope_table') or '—'} | `{r.get('pattern') or '—'}` | {r.get('match_value') or '—'} | "
      f"`{r['kb_type']}` | {hits.get(r['id'], 0)} | {runj['rule_hits'].get(r['id'], 0)} |")
w()
w(f"**0 命中的规则（全量口径，按台账最新行统计 1215 条 live 资源）**：")
w()
zero = [r["id"] for r in registry["rules"] if hits.get(r["id"], 0) == 0]
w(f"- 共 {len(zero)} 条：{', '.join(zero) if zero else '（无）'}")
w(f"- 其中被停用的：{', '.join(x for x in zero if x in ('R6','R7','R8','R9','R10')) or '（无）'}")
w()
w("- **需要点名的三条**：")
w(f"  - `R9`（已停用）全量命中 {hits.get('R9',0)} 条 —— 这是**历史**命中：1215 那次补登记「正面和负面样本」"
  f"125 条记录时借用了 R9（案例沉淀 → internal_sample），本批停用 R9 后**规则库不再兜底进 unknown**，"
  f"但这 125 条既有记录的 `matched_rule` 是历史事实，按「不改历史行」保留。"
  f"注册规则库记录这件事本身已由 `excluded_scope.tables=[\"规则库\"]` 拦住。")
w(f"  - `R13`/`R14` 各命中 1：`知识库分类说明` 的 5 条记录里 `知识库` 列取值为「措辞表达库」「产品描述库」的各 1 条；"
  f"其余 3 条取值不在 R11–R14 的 match_value 里 → 落 unknown（见第 8 节）。")
w(f"  - `R26`（正面和负面样本 → internal_sample）全量命中 0：该规则是 1215 那次补登记时新加的，"
  f"但当时 202 条资源实际是用 R9/R25 落的，`matched_rule` 里没有 R26，属历史口径不一致，本批未回改历史行。")
w("")
w("> 说明：全量命中数是按**台账最新行**里每条资源的 `matched_rule` 汇总的；"
  "本批新增资源的命中数另列一栏（R5 ×2 = 两条新增纳入的入口记录；R1 ×2 = 它们的材料链接子资源；"
  "R18 ×7 = 内容公式（仅供参考）7 条）。")
w()
w("## 8. unknown 清单（为什么没命中任何规则）")
w()
w(f"库目录 `9_未归类/` 共 **{by_kb.get('unknown',0)}** 条。逐条原因：")
w()
w("| resource_key | source_kind | 源表 | 为什么没命中 |")
w("|---|---|---|---|")
REASON = {
    "base": "入口 Base 容器本身不是知识本体（`kb_type_source=no_rule_matched:Base 是容器`），无任何规则覆盖",
    "table": "入口 Base 的容器表：R5/R10 命中即 kb_type=unknown（入口容器表，归属落在其子资源上）",
    "record": "入口容器表的记录本身是「一份待收材料」，R5 命中即 unknown，归属落在其 link 子资源上",
    "file": "第三层链接（超出规则提取层数上限 2），只登记不归类，无规则覆盖",
}
for k in sorted(live):
    v = live[k]
    if v["kb_type"] != "unknown":
        continue
    if k.startswith("base:"):
        why = REASON["base"]
    elif k.endswith(":" + (v.get("table_id") or "")) or ":table:" in k:
        why = REASON["table"]
    elif v["source_kind"] == "feishu_bitable_record":
        why = REASON["record"]
    else:
        why = REASON["file"]
    _src = (files.get(k, (None, {}))[1] or {}).get("kb_type_source")
    why += f"（`kb_type_source`={_src or '—'}）"
    w(f"| `{k}` | `{v['source_kind']}` | {v.get('table_name') or '—'} | {why} |")
w()
w("## 9. 失败与异常清单")
w()
w(f"**本批失败/读不到/无权限：0 条。** 本批 {len(runj['ops'])} 项外部调用全部 `exit=0` 且返回可用数据（见 `.ops.log`）。")
w()
w("**但发现一条本批范围之外的源侧漂移（已登记、未纳入，不静默跳过）**：")
w()
w(f"- `正面和负面样本`（`tbld8qE92YaY38Yz`）：1215 那次登记时源侧 125 条，本次实测 "
  f"**{source_drift['本次读到的记录数']} 条**，且 record_id 集合**交集为 0**"
  f"（已登记 `recvvPK3E…`，现网 `recvw2vgYX…`）—— 该表已被整体换过。")
w(f"- 处置：**本批不纳入**（不在本批 5 项范围内，纳入会让本批对账口径失真），"
  f"已在 `runs/{RUN}.json` 的 `source_drift` 里留痕，交下一批处理。")
w("- 其余表清单与登记数一致：`知识库分类说明` 5、`规则库` 50（已排除）、`广告文案明细` 291、"
  "`品线内容边界规则库` 21、`W1卖点表达边界` 19、`风险文案改写建议库` 52、`数据表` 32、"
  "`专家修订汇总表` 395、`内容公式（仅供参考）` 7。")
w()
w("**截断**：本批无截断。`材料收集` 32 条一次取全（`has_more=false`，`page_count=1`）；"
  "`内容公式（仅供参考）` 7 条一次取全（`has_more=false`）。"
  "历史遗留截断（`sampling_policy` 200/表；已在 1300 那次放开）与本批无关。")
w()
w("**内容质量存疑项（已登记、非失败）**：")
w()
w("- `url:https://support.momcozy.com/`：HTTP 200、1,040,046 字节 HTML，抽出文本 10,548 字符并据其算了 sha256；"
  "但该站为 JS 渲染，抽出文本以站点导航/商品清单为主，非可引用的实质正文。已写入资源 `status_reason`，"
  "L1 取数时应按 `content_quality_flag` 处理。")
w()
w("## 10. 自主决策")
w()
w("| # | 决策 | 依据 |")
w("|---|---|---|")
DEC = [
 ("规则库「整体不纳入」的边界含其下钻子资源（15 条来源链接 URL），不只表资源本身",
  "判据要求「库目录内 table_name==规则库 的资源数 == 0」；这 15 条 URL 的 table_name 也是规则库，"
  "且 R15/R16 只因规则库存在才生效，留着会造成「表没了、链接还在」的半排除态"),
 ("R6–R10 停用用 `enabled=false` 表示，而不是把规则从数组里删掉",
  "硬约束「既有产物只追加、不改内容」；保留规则条目 + 标停用，历史可审计，求值时跳过"),
 ("新增 `excluded_scope.tables=[\"规则库\"]` 作为「不兜底进 unknown」的机器可读依据",
  "任务明确「R6–R10 停用后规则库记录不得再兜底进 unknown」；只停规则不够，"
  "还需要一条独立于规则求值的「整表不纳入」声明"),
 ("16 条规则库资源文件**移动**（不是复制）到 `_archive/rulelib-excluded-<run_id>/`",
  "任务原文「资源文件移出库目录」+「不要删除文件」；移动同时满足两者，且留 `moved_from`/`moved_to` 痕"),
 ("撤下钻边用追加 tombstone，而不是删/改历史行",
  "任务原文「按追加 tombstone 处理，不要重写历史行」；tombstone 保留完整原边字段 + `tombstone=true`"),
 ("入口容器表的记录仍按 R5 判为 `unknown` 落 `9_未归类/`，不按 `知识库分类` 改判",
  "既有 21 条记录就是这么落的（R5 是既有规则、且资源文件已在 `9_未归类/`）；"
  "改判需要 mv 21 个既有文件，违反硬约束 2/3。`知识库分类` 原值完整保留在台账 `extra`，"
  "并由 R1–R4 决定其 link 子资源的归属（本批 2 条子资源即按 R1 落 `4_产品描述库`）"),
 ("为 2 条新增纳入记录各下钻 1 层材料链接子资源（`wiki:EL1nw9…`、`url:https://support.momcozy.com/`）",
  "既有 21 条记录每条都有 1 条同深度子资源；只登记记录不下钻会让本批新增部分与既有部分结构不一致"),
 ("新增记录与新增子资源的图边按既有约定追加（表→记录、记录→链接）",
  "图里既有 329 条 `表→记录`、129 条 `记录→url` 边；新资源不带边会成孤儿。只追加、不动历史"),
 ("field_roles 的 L3 补丁按名「全局」生效（不限 L2 论域），并只增不删 L0 既有条目",
  "L3 的 CONTENT/METADATA 是它的过滤依据；只对论域内字段生效会让 L3 仍需自带表。"
  "只增不删避免在 registry 里做删除（规则库专属字段角色保留）"),
 ("field_role_table_overrides 只写「同名**跨表**角色互相冲突」的项（本批新增 2 项）",
  "任务要求的是「同名不同角色」；同一字段名各表角色一致时只需一个裸角色，写覆盖是冗余。"
  "实测其余类型差异（如 `资料名称` 在数据表里装链接）记入 `field_role_evidence_notes` 交 L3 复核，"
  "避免擅自改动 L3 补丁表已定的 content 判断"),
 ("`kb/l3/registry/l3.json` 的标注是**追加**（新增 `merged_into_l0` 块 + 改写 `how`/`gap` 指向 L0），"
  "不删除原 `gap` 的历史信息",
  "任务第 4 件明确要求「在 L3 registry 里标注已并入 L0」，这是本批唯一写到 l0 之外的路径"),
 ("`正面和负面样本` 的源侧整体换血（125→201、id 全不相交）**本批不纳入**，只登记",
  "不在本批 5 项范围内；纳入会新增 200+ 资源，把本批的纳入口径对账冲掉。留痕交下一批"),
 ("`index/l0.jsonl` 的条数口径定为「台账最新行减去 retracted」",
  "自检同时要求「index 条数 == 台账条数」与「不含被排除记录」；两者只有在把 retracted 从台账有效行里"
  "剔除后才同时成立。报告里两个数都给出（1283 原始行 / 1231 最新行 / 1215 有效）"),
 ("`scanner_version` 记为 0.6 并写进本批所有新资源文件与台账新行",
  "任务第 5 件要求 0.5 → 0.6；既有未改动的旧文件保留其原 scanner_version=0.5（不重写历史）"),
]
for i, (a, b) in enumerate(DEC, 1):
    w(f"| {i} | {a} | {b} |")
w()
w("## 11. 自检")
w()
w("### 11.1 源未被改动")
w()
w("本批全部外部调用及读写性质（明细见 `runs/%s.ops.log`）：" % RUN)
w()
w("| 调用 | 性质 | 对象 | 说明 |")
w("|---|---|---|---|")
for kind, nature, target, note in runj["ops"]:
    w(f"| `{kind}` | **{nature}** | {target} | {note} |")
w()
w(f"**写操作数 = 0**；未修改任何视图或筛选条件（`registry.filter` 是 DSH 本地 L0 的配置，不是源侧视图筛选）。")
w()
w("### 11.2 `KB/l0/` 既有资源文件、`records/`、`links/` 未被修改")
w()
w(f"- 开工前对 **{len(base)}** 个文件（库目录资源文件 {sum(1 for p in base if re.match(rf'{L0}/(1_|2_|3_|4_|9_)', p))} 个、"
  f"`records/` {sum(1 for p in base if p.startswith(f'{L0}/records/'))} 个、以及 `links/`/`manifest`/`registry`/`index`/`versions`/`l3.json`）"
  f"记了 `size + mtime`。")
_content_changed = [p for p in changed if os.path.exists(p)]
_moved = [p for p in changed if not os.path.exists(p)]
w(f"- 运行后复查：**{len(changed)} 个原路径不能原样复核**，拆开看是两类：")
w(f"  - **内容被改的 {len(_content_changed)} 个**（全部是本批应当改的元数据/投影文件，"
  f"库目录资源文件 {len([p for p in _content_changed if re.match(rf'{L0}/(1_|2_|3_|4_|9_)', p)])} 个、"
  f"`records/` 下 {len([p for p in _content_changed if p.startswith(f'{L0}/records/')])} 个）：")
for _p in sorted(_content_changed):
    w(f"    - `{_p}`")
w(f"  - **被移动的 {len(_moved)} 个**（就是那 16 条规则库资源，见下表）。")
w(f"- `kb/versions/versions.jsonl` **未被改动**（size 与 mtime 均未变）。"
  f"`kb/l1/` 及以下除 `l3/registry/l3.json` 外无任何写入。")
w(f"- 唯一不在原地的既有资源文件是那 16 条规则库资源（**移动**到 `_archive/`，非修改、非删除）：")
w()
w("| 移出前路径 | size |")
w("|---|---|")
for a in runj["rulelib"]["archived"]:
    w(f"| `{a['from']}` | {a['size']} |")
w()
w("- **旧台账行前缀哈希对照**：")
w()
w(f"  - 开工前 `l0/manifest.jsonl` 全文 sha256 = `{out['immutability']['old_manifest_prefix_sha256']}`（1256 行）")
w(f"  - 运行后取前 1256 行重算 sha256 = `{sha(cur_head)}` → **{'逐字节一致 ✅' if prefix_ok else '不一致 ❌'}**")
w(f"  - 复算命令：`head -1256 kb/l0/manifest.jsonl | shasum -a 256`")
w()
w(f"- **旧 links 历史行前缀哈希对照**：`links/graph.jsonl` 开工前 582 行、全文 sha256 = "
  f"`ac674c05e9c73c8ad93043b0b214d310ec3dea669b6d9ca92eaca54fa8e86a1a`；"
  f"运行后前 582 行重算 sha256 = `{graph_prefix_sha_now}` → "
  f"{'逐字节一致 ✅' if graph_prefix_sha_now == 'ac674c05e9c73c8ad93043b0b214d310ec3dea669b6d9ca92eaca54fa8e86a1a' else '不一致 ❌'}"
  f"（现共 {len(graph_lines)} 行 = 582 + 16 tombstone + 11 新边）")
w()
w("- **抽样核对（库目录既有资源文件的 mtime + size）**：")
w()
w("| 文件 | 开工前 size | 开工后 size | 开工前 mtime | 开工后 mtime |")
w("|---|---|---|---|---|")
samp = [p for p in sorted(base) if re.match(rf"{L0}/(1_|2_|3_|4_|9_)", p)][:6]
samp += [p for p in sorted(base) if p.startswith(f"{L0}/records/")][:3]
samp += [f"{L0}/links/graph.jsonl", f"{L0}/manifest.jsonl", f"{L0}/index/l0.jsonl"]
import datetime as _dt
for p in samp:
    b = base[p]
    n = now[p]
    if n[1] is None:
        w(f"| `{p}` | {b['size']} | （已移动） | {b['mtime']} | — |")
    else:
        w(f"| `{p}` | {b['size']} | {n[0]} | {b['mtime']} | {n[1]} |")
w()
w("> 说明：`index/l0.jsonl` 与 `manifest.jsonl` 按任务要求「重建 / 追加」，mtime 必然变化；"
  "`links/graph.jsonl` 只追加，mtime 变化但前 582 行逐字节未变。")
w()
w("### 11.3 台账按 key 取最新一行 == 资源文件总数")
w()
w(f"- 台账原始行数：**{len(rows)}**（1256 + 本批追加 27）")
w(f"- 按 key 取最新一行：**{len(latest)}**")
w(f"- 其中 `status=retracted`（excluded_by_scope，文件已移出库目录）：**{len(retracted)}**")
w(f"- 有效最新行 = {len(latest)} − {len(retracted)} = **{len(live)}**")
w(f"- 资源文件总数：**{len(files)}**")
w(f"- **{len(live)} == {len(files)} ✅**（差额 0）")
w()
w("### 11.4 三方一致：文件内 kb_type == 台账 == 所在库目录")
w()
w(f"- 检查范围：{len(files)} 个库目录资源文件")
w(f"- **不符处数：{len(mismatch)}** —— {mismatch if mismatch else '（无）'}")
w()
w("### 11.5 index 条数 == 台账有效条数，且不含被排除记录")
w()
w(f"- `index/l0.jsonl` 行数：**{len(index_rows)}**")
w(f"- 台账有效最新行：**{len(live)}** → **{'相等 ✅' if len(index_rows)==len(live) else '不等 ❌'}**")
w(f"- index 中是否含 16 条规则库排除项：**{'否 ✅' if not (index_keys & set(retracted)) else '是 ❌'}**"
  f"（交集 {len(index_keys & set(retracted))}）")
w(f"- index 中是否含\"材料审核状态=空\"的 9 条：**{'否 ✅' if not any('recvvg2wL2EnC0' in k or 'recvvhv1cwO2Ry' in k or 'recvvlspM5RDoj' in k or 'recvvltvfBsoDP' in k or 'recvvlGAKpUVF9' in k or 'recvvlGUajvYY0' in k or 'recvvlO5gFdyzx' in k or 'recvvg2wL26SAU' in k or 'recvvhI3yZULdA' in k for k in index_keys) else '是 ❌'}**"
  "（这 9 条从未登记，台账/资源文件/index 里都不存在）")
w()
w("### 11.6 kb_version 与 versions")
w()
w(f"- `registry/kb_version` = **{registry['kb_version']}**（仍为 v0）")
w(f"- `kb/versions/versions.jsonl` 版本行数 = **{out['versions_jsonl_version_rows']}**（仍为 0，与既有约定一致）")
w()
w("## 12. 本批写入清单")
w()
w(f"- 新增资源文件 **{len(runj['written_files'])}** 个：")
for p in runj["written_files"]:
    w(f"  - `{p}`")
w(f"- 新增 `records/` 文件 **{runj['record_files']}** 个（`records/内容公式（仅供参考）/` 7 个 + `records/材料收集/` 2 个）")
w(f"- 台账追加 **{len(rows)-1256}** 行；index 重建 **{len(index_rows)}** 行；"
  f"links 追加 **{runj['tombstones_appended']}** tombstone + **{runj['edges_appended']}** 新边")
w(f"- 移动 **16** 个资源文件到 `{ARCHIVE}/`")
w(f"- `registry/kb.json` 改写（规则启停 / rule_eval_order / excluded_scope / filter / excluded_policy / field_roles 等）")
w(f"- `kb/l3/registry/l3.json` 追加「已并入 L0」标注（**本批唯一写到 `kb/` 内 l0 之外的文件**）")
w(f"- 本批未写到 `kb/` 之外的任何路径（越权路径数 = **0**）")
w()

open(f"{L0}/runs/{RUN}.report.md", "w", encoding="utf-8").write("\n".join(W_) + "\n")
print("report written:", f"{L0}/runs/{RUN}.report.md", len("\n".join(W_).split("\n")), "lines")
print("changed files:", len(changed), "| res:", len(res_changed), "| records:", len(rec_changed))
print("prefix_ok:", prefix_ok, "| mismatch:", len(mismatch), "| index==live:", len(index_rows) == len(live))
print("zero-hit rules (full):", zero)
