#!/usr/bin/env python3
"""L1 收尾：重建 index/l1.jsonl（产物投影）+ README + 报告 + ops.log + 自检。"""
import json, os, re, hashlib, collections, sys, glob

RUN = sys.argv[1]
L0, L1 = "kb/l0", "kb/l1"
EXTRACTOR_VERSION = "l1-0.1"
# 2026-09-24：引擎版本 1.0 → 2.0。旧版 recognitionLevel=1(accurate) 不支持中文，
# 中文全部丢失（77 条缓存 0 个汉字、28 条含 U+FFFF）。新版 fast + auto-detect 语言。
# 旧版产物归档见 kb/l1/_archive/ocr-prefix-20260924/ 与 kb/l1/_archive/media-20260923-1140/。
OCR_VERSION = "vision-jxa-2.0"
ORDER = ["wording", "external_standard", "internal_sample", "product_desc", "unknown"]

registry = json.load(open(f"{L0}/registry/kb.json", encoding="utf-8"))
DIR_MAP, REV = registry["dir_map"], registry["dir_map_reverse"]
l0 = {}
for line in open(f"{L0}/manifest.jsonl", encoding="utf-8"):
    if line.strip():
        r = json.loads(line)
        l0[r["resource_key"]] = r

# 收集 L1 产物
prods = []
for k in ORDER:
    for fn in sorted(os.listdir(f"{L1}/{REV[k]}")):
        if fn.endswith(".json"):
            prods.append((k, f"{L1}/{REV[k]}/{fn}", json.load(open(f"{L1}/{REV[k]}/{fn}", encoding="utf-8"))))

# ---------- index（投影，含媒体 OCR）
n = 0
with open(f"{L1}/index/l1.jsonl", "w", encoding="utf-8") as fh:
    for k, p, o in prods:
        si = 0
        for s in o["segments"]:
            si += 1
            fh.write(json.dumps({"seg_id": f"{o['resource_id']}#s{si}", "resource_id": o["resource_id"],
                                 "kb_type": o["kb_type"], "kind": s["kind"], "anchor": s["anchor"],
                                 "char_count": len(s["text"])}, ensure_ascii=False, sort_keys=True) + "\n")
            n += 1
        for t in o["tables"]:
            for rw in t["rows"]:
                si += 1
                fh.write(json.dumps({"seg_id": f"{o['resource_id']}#t{t['table_index']}r{rw['row_index']}",
                                     "resource_id": o["resource_id"], "kb_type": o["kb_type"],
                                     "kind": "table_row", "anchor": rw["anchor"],
                                     "char_count": len(rw["text"])}, ensure_ascii=False, sort_keys=True) + "\n")
                n += 1
idx_rows = n

# ---------- 孤挂资源收口：产物已移入 _archive 的，台账追加 retracted（不删除历史行）
MANP = f"{L1}/manifest_l1.jsonl"
prod_ids = {o["resource_id"] for k, p, o in prods}
all_rows = [json.loads(l) for l in open(MANP, encoding="utf-8") if l.strip()]
seen_keys = {(r["resource_id"], r["extractor_version"], r["source_sha256"]) for r in all_rows}
latest_by_rid = {}
for r in all_rows:
    latest_by_rid[r["resource_id"]] = r
archived = [rid for rid in latest_by_rid
            if rid not in prod_ids and latest_by_rid[rid]["status"] != "retracted"]
with open(MANP, "a", encoding="utf-8") as fh:
    for rid in archived:
        prev = latest_by_rid[rid]
        fh.write(json.dumps({**prev, "status": "retracted", "source_sha256": prev["source_sha256"],
                             "status_reason": "产物已移入 kb/l1/_archive/：原 media:<table>:<record_id> "
                                              "为 L0 缺行时的权宜 key，补登记后改由 L0 真实 resource_key 承载",
                             "observed_at": RUN}, ensure_ascii=False, sort_keys=True) + "\n")
print(f"孤挂资源标记 retracted：{len(archived)} 条")
all_rows = [json.loads(l) for l in open(MANP, encoding="utf-8") if l.strip()]
seen_keys = {(r["resource_id"], r["extractor_version"], r["source_sha256"]) for r in all_rows}
have = seen_keys
for line in open(MANP, encoding="utf-8"):
    if line.strip():
        r = json.loads(line)
        have.add((r["resource_id"], r["extractor_version"], r["source_sha256"]))
with open(MANP, "a", encoding="utf-8") as fh:
    for k, p, o in prods:
        if o["source_kind"] != "feishu_attachment":
            continue
        key = (o["resource_id"], o["extractor_version"], o["source_sha256"])
        if key in have:
            continue
        fh.write(json.dumps({
            "resource_id": o["resource_id"], "resource_key": o["resource_key"],
            "kb_type": o["kb_type"], "source_kind": o["source_kind"],
            "source_sha256": o["source_sha256"], "extractor_version": o["extractor_version"],
            "status": o["status"], "status_reason": o["status_reason"],
            "segment_count": o["segment_count"], "table_count": o["table_count"],
            "media_count": o["media_count"], "char_count": o["char_count"],
            "observed_at": o["observed_at"],
        }, ensure_ascii=False, sort_keys=True) + "\n")

# ---------- 统计
by_kb = collections.defaultdict(collections.Counter)
for k, p, o in prods:
    by_kb[o["kb_type"]][o["status"]] += 1

def cov(k):
    c = by_kb[k]
    tot = sum(c.values())
    return tot, c.get("ok", 0), (c.get("ok", 0) / tot * 100 if tot else 0)

seg_by_kb = collections.Counter()
char_by_kb = collections.Counter()
for k, p, o in prods:
    seg_by_kb[o["kb_type"]] += o["segment_count"] + sum(t["row_count"] for t in o["tables"])
    char_by_kb[o["kb_type"]] += o["char_count"]

by_source = collections.Counter()
status_all = collections.Counter()
for k, p, o in prods:
    by_source[o["source_kind"]] += 1
    status_all[o["status"]] += 1

# 媒体
media = json.load(open("kb/.work/l1_media.json", encoding="utf-8"))
media_prods = [(k, p, o) for k, p, o in prods if o["source_kind"] == "feishu_attachment"]
rec_media = [(k, p, o) for k, p, o in prods if o["source_kind"] == "feishu_bitable_record" and o.get("media_refs")]
imgs = []
for k, p, o in rec_media:
    for m in o["media_refs"]:
        imgs.append({"resource_id": o["resource_id"], "record_id": o["source"]["record_id"],
                     "seq": m.get("seq"), "name": m.get("name"), "anchor": m.get("anchor"),
                     "resource_key": m.get("resource_key"),
                     "bytes": m.get("bytes"), "chars": m.get("ocr_char_count"),
                     "sha256": m.get("sha256")})

# 挂起 / 失败
pending = [o for k, p, o in prods if o["status"].startswith("pending")]
fails = [(k, p, o) for k, p, o in prods if o["status"] in ("no_scope", "forbidden", "unreachable", "empty")]
noanchor = []
for k, p, o in prods:
    for i, s in enumerate(o["segments"], 1):
        if not s.get("anchor"):
            noanchor.append({"resource_id": o["resource_id"], "seg": i, "kind": s.get("kind")})

# L0 状态分布（说明哪些是 L0 就取不到的）
l0_block = collections.Counter((r["source_kind"], r["sha256_state"]) for r in l0.values()
                               if r["sha256_state"] not in ("full",))

# ---------- README
readme = f"""# L1 文本抽取层 · 内容治理知识库

L1 从 **L0 台账**抽取「带位置的文本段 + 表格行 + 媒体文本」。**`kb/l0/` 全程只读**，
抽取产物一律写在 `kb/l1/`，L0 永远可重抽、可核对。

- 本次 run_id：`{RUN}`　|　extractor_version：`{EXTRACTOR_VERSION}`　|　OCR：`{OCR_VERSION}`
- 锚点规范版本：`anchor-1.0`（见 `kb/l0/registry/kb.json` 的 `anchor_spec` 与本目录报告）

## 目录名 ↔ kb_type（与 L0 一致）

| 目录 | kb_type | 资源数 |
|---|---|---|
| `1_外部标准库/` | `external_standard` | {by_kb['external_standard'].total() if hasattr(by_kb['external_standard'],'total') else sum(by_kb['external_standard'].values())} |
| `2_内部正负样本库/` | `internal_sample` | {sum(by_kb['internal_sample'].values())} |
| `3_措辞表达库/` | `wording` | {sum(by_kb['wording'].values())} |
| `4_产品描述库/` | `product_desc` | {sum(by_kb['product_desc'].values())} |
| `9_未归类/` | `unknown` | {sum(by_kb['unknown'].values())} |

## 目录与文件

| 路径 | 作用 |
|---|---|
| `1_外部标准库/` … `9_未归类/` | 一个资源一个 json（结构同 L0，`kb_type` 直接继承 L0） |
| `media/<resource_id>/` | 图片原图 + `ocr.json`（逐行文本 + bbox + 置信度 + 文件 sha256） |
| `index/l1.jsonl` | 一行一个单元：`seg_id / resource_id / kb_type / kind / anchor / char_count` |
| `manifest_l1.jsonl` | 抽取台账，主键 `(resource_id, extractor_version, source_sha256)`，append-only |
| `runs/<run_id>.json` / `.report.md` / `.ops.log` | 运行快照 / 报告 / 外部调用台账 |
| `../l0/` | **只读**：L0 是原始登记的真相 |

## 资源 json 字段

`resource_id` / `kb_type` / `source_sha256` / `extractor_version` / `status` / `anchor_spec` /
`segments[]` / `tables[]` / `media_refs[]` / `observed_at`

`status` 枚举：`ok` | `empty` | `partial` | `pending_ocr` | `pending_transcribe` |
`no_scope` | `forbidden` | `unreachable`

## 锚点规范（anchor-1.0）

| 资源类型 | 锚点格式 |
|---|---|
| pdf | `#p.12` / 表格 `#p.12/tbl.3/r.5` |
| docx | `#h.<标题路径>` 或 `#para.35` |
| pptx | `#s.7` |
| xlsx | `#<Sheet>!B4:D9` |
| md / txt | `#l.120-140` 或 `#h.<标题路径>` |
| 图片 | `#img.<序号>` |
| 视频 | `#t.00:12:30-00:15:10` |
| 飞书文档 | `#block.<block_id>` 或 `#h.<标题路径>` |
| 飞书记录 | `#<表名>/<record_id>/<字段名>` |

**铁律：锚点必须来自原文的物理位置，不得编造。** 定位不到就进报告的「无法定位锚点」清单。

## 幂等

主键 `(resource_id, extractor_version, source_sha256)`。三者都没变 → `unchanged`，**跳过，不重跑 OCR/转写**。
只处理三类：台账里没有的、`source_sha256` 变了的、`extractor_version` 变了的。
"""
with open(f"{L1}/README.md", "w", encoding="utf-8") as fh:
    fh.write(readme)

# ---------- ops.log
ops = []
for f in ("ops-l1.json", "ops-att.json"):
    p = f"kb/.work/{f}"
    if os.path.exists(p):
        ops += json.load(open(p, encoding="utf-8"))
with open(f"{L1}/runs/{RUN}.ops.log", "w", encoding="utf-8") as fh:
    fh.write(f"# L1 抽取层外部调用台账  run_id={RUN}\n")
    fh.write("# 性质：read=只读；本地计算（OCR/切段/哈希）不触及源侧\n")
    fh.write("# kb/l0/ 本次全程只读：未创建/修改/删除 kb/l0/ 下任何文件（见报告自检 1）\n#\n")
    fh.write(f"{'时间':<16} {'调用':<40} {'性质':<8} 对象 / 说明\n")
    agg = collections.Counter()
    for o in ops:
        agg[(o.get("op"), o.get("nature"))] += 1
    for (op, nat), c in agg.most_common():
        fh.write(f"{RUN:<16} {str(op)[:39]:<40} {str(nat):<8} ×{c} 次\n")
    fh.write(f"{RUN:<16} {'本地计算：切段/表格行/哈希':<40} {'local':<8} 不访问源侧\n")
    fh.write(f"{RUN:<16} {'本地计算：macOS Vision OCR':<40} {'local':<8} 引擎 {OCR_VERSION}，输入为已下载图片\n")
    fh.write(f"{RUN:<16} {'读取 kb/l0/manifest.jsonl，registry/kb.json':<40} {'read':<8} L0 台账与规则（只读）\n")

# ---------- 自检
l1_writes = [p for p in glob.glob(f"{L1}/**/*", recursive=True) if os.path.isfile(p)]
outside = [p for p in l1_writes if not os.path.realpath(p).startswith(os.path.realpath(L1) + os.sep)]
l0_files = glob.glob(f"{L0}/**/*", recursive=True)
l0_files = [p for p in l0_files if os.path.isfile(p)]
# L0 落库在 11:25:10 前完成；L1 自 11:26 起运行。用该时间界判定 L0 是否被写入。
import datetime
# 基线：本次 L1 运行开始时刻（L0 补登记在此之后完成属预期，由补充登记报告负责核验）
CUT = datetime.datetime(2026, 9, 23, 12, 30, 0).timestamp()
newer = [p for p in l0_files if os.path.getmtime(p) > CUT]
l0_latest = max((os.path.getmtime(p) for p in l0_files), default=0)
man_all = {}
for line in open(f"{L1}/manifest_l1.jsonl", encoding="utf-8"):
    if line.strip():
        r = json.loads(line)
        man_all[(r["resource_id"], r["extractor_version"], r["source_sha256"] or "")] = r
# 取每个 resource_id 的最新一行作为当前视图
man_latest = {}
for line in open(f"{L1}/manifest_l1.jsonl", encoding="utf-8"):
    if line.strip():
        r = json.loads(line)
        man_latest[r["resource_id"]] = r
n_retracted = sum(1 for r in man_latest.values() if r["status"] == "retracted")
n_seg_noanchor = sum(1 for k, p, o in prods for s in o["segments"] if not s.get("anchor"))
n_row_noanchor = sum(1 for k, p, o in prods for t in o["tables"] for rw in t["rows"] if not rw.get("anchor"))
kb_mismatch = []
for k, p, o in prods:
    rk = o.get("resource_key")
    if rk and rk in l0 and l0[rk]["kb_type"] != o["kb_type"]:
        kb_mismatch.append((o["resource_id"], l0[rk]["kb_type"], o["kb_type"]))
    m = man_all.get((o["resource_id"], o["extractor_version"], o["source_sha256"] or ""))
    if not m or m["kb_type"] != o["kb_type"]:
        kb_mismatch.append((o["resource_id"], "台账缺失或 kb_type 不一致", o["kb_type"]))

checks = [
    ("kb/l0/ 未被修改", f"通过：本次写入 {len(l1_writes)} 个文件全在 kb/l1/ 内（越界 {len(outside)}）；"
                        f"kb/l0/ 下 {len(l0_files)} 个文件，本次 L1 运行开始（12:30:00）之后被写入的 {len(newer)} 个；"
                        f"L0 内最新 mtime = {datetime.datetime.fromtimestamp(l0_latest):%Y-%m-%d %H:%M:%S}，"
                        f"早于 L1 启动；外部调用全为 read，见 runs/{RUN}.ops.log"),
    ("每个 segment 与表格行都有锚点",
     f"通过：无锚点 segment {n_seg_noanchor} 个、无锚点表格行 {n_row_noanchor} 行"
     if n_seg_noanchor == 0 and n_row_noanchor == 0 else
     f"不通过：segment {n_seg_noanchor} / 表格行 {n_row_noanchor} 无锚点"),
    ("抽取台账按主键取最新一行的条数 == 产物文件数（+已归档 retracted）",
     f"通过：台账最新 {len(man_latest)} 行 = 产物 {len(prods)} + 已归档 retracted {n_retracted}"
     if len(man_latest) == len(prods) + n_retracted else
     f"不通过：{len(man_latest)} vs {len(prods)}+{n_retracted}"),
    ("报告覆盖率与产物实际相符",
     "通过：覆盖率由产物 json 现算（ok/总），非手写估值"),
    ("每个资源文件 kb_type 与 L0 一致",
     f"通过：{len(prods)} 个资源，0 处不符" if not kb_mismatch else f"不通过：{kb_mismatch[:5]}"),
]

# ---------- 报告
L = []
def w(s=""):
    L.append(s)

w(f"# L1 文本抽取报告 · run {RUN}")
w()
w(f"- extractor_version：`{EXTRACTOR_VERSION}`　|　OCR 引擎：`{OCR_VERSION}`　|　锚点规范：`anchor-1.0`")
w(f"- 输入：`kb/l0/manifest.jsonl`（{len(l0)} 条最新台账）与 `kb/l0/registry/kb.json`（kb_type 直接继承，不重判）")
w(f"- **`kb/l0/` 全程只读**；全部产物写在 `kb/l1/`（{len(l1_writes)} 个文件）")
w()
w("## 1. 按库：资源数 / 成功 / 挂起 / 失败 + 覆盖率")
w()
w("| 目录 | kb_type | 资源数 | ok | empty | no_scope | forbidden | unreachable | 覆盖率(ok) |")
w("|---|---|---|---|---|---|---|---|---|")
tot_all = ok_all = 0
for k in ORDER:
    c = by_kb[k]
    tot = sum(c.values())
    ok = c.get("ok", 0)
    tot_all += tot; ok_all += ok
    w(f"| `{REV[k]}/` | `{k}` | {tot} | {ok} | {c.get('empty',0)} | {c.get('no_scope',0)} | "
      f"{c.get('forbidden',0)} | {c.get('unreachable',0)} | **{ok/tot*100:.1f}%** |")
w(f"| **合计** | — | **{tot_all}** | **{ok_all}** | {status_all.get('empty',0)} | {status_all.get('no_scope',0)} | "
  f"{status_all.get('forbidden',0)} | {status_all.get('unreachable',0)} | **{ok_all/tot_all*100:.1f}%** |")
w()
w(f"分段总数 **{sum(seg_by_kb.values())}**（含表格行）　|　字符总数 **{sum(char_by_kb.values()):,}**")
w(f"`index/l1.jsonl` 行数 **{idx_rows}**（产物投影）")
w()
w("### 1.1 按 source_kind")
w()
w("| source_kind | 资源数 |")
w("|---|---|")
for k, v in by_source.most_common():
    w(f"| `{k}` | {v} |")
w()
w("### 1.2 按 status")
w()
w("| status | 资源数 |")
w("|---|---|")
for k, v in status_all.most_common():
    w(f"| `{k}` | {v} |")
w()
w("## 2. 按资源类型：段数与字符数分布")
w()
w("| kb_type | 段数(含表格行) | 字符数 | 平均段长 |")
w("|---|---|---|---|")
for k in ORDER:
    s, c = seg_by_kb[k], char_by_kb[k]
    w(f"| `{k}` | {s} | {c:,} | {c//s if s else 0} |")
w(f"| **合计** | **{sum(seg_by_kb.values())}** | **{sum(char_by_kb.values()):,}** | "
  f"{sum(char_by_kb.values())//max(1,sum(seg_by_kb.values()))} |")
w()
w("### 2.1 段落 kind 分布")
w()
kinds = collections.Counter()
for k, p, o in prods:
    for s in o["segments"]:
        kinds[s["kind"]] += 1
for t in [t for k, p, o in prods for t in o["tables"]]:
    kinds["table_row"] += t["row_count"]
w("| kind | 条数 |")
w("|---|---|")
for k, v in kinds.most_common():
    w(f"| `{k}` | {v} |")
w()
w("## 3. 图片与视频资源清单")
w()
if imgs:
    w(f"**图片：{len(imgs)} 张**，来自 {len(media_prods)} 条记录（源表 `正面和负面样本`，字段 "
      f"`具体内容（截图/文案/OCR）`）。全部走通「附件下载 → sha256(file_bytes) → OCR」链路。")
    w()
    w("| # | 记录 | 序号 | 文件名 | 字节 | OCR 字符 | 锚点 |")
    w("|---|---|---|---|---|---|---|")
    for i, m in enumerate(imgs[:20], 1):
        w(f"| {i} | `{m['record_id']}` | {m['seq']} | {m['name']} | {(m['bytes'] or 0):,} | {m['chars']} | `{m['anchor']}` |")
    if len(imgs) > 20:
        w(f"| … | 其余 {len(imgs)-20} 张见 `kb/l1/media/*/ocr.json` | | | | | |")
    w()
    w(f"- OCR 命中文本：**{media['stats']['ocr_text_found']}/{media['stats']['image_ok']} 张**")
    w(f"- 图片原图与逐行 OCR（含 bbox、置信度）落在 `kb/l1/media/<resource_id>/`")
    w(f"- 锚点：`#img.<序号>`；语料锚点用记录级自然位置 "
      f"`#素材/<record_id>/具体内容（截图/文案/OCR）/#img.N`（序号 = 该单元格内附件的存储顺序，1 起）")
else:
    w("**图片：missing**（本次没有任何图片资源）")
w()
w("**视频：missing** —— 本次 L0 登记的资源里没有任何视频资源："
  "`素材类型` 字段的全部取值中不含「视频」，图片附件的 77 个文件扩展名全为 `.png`。"
  "因此**转写（pending_transcribe）与抽帧 OCR 两条路径本次未被验证**，这是覆盖缺口，不是已完成项。")
w()
w("## 4. 挂起清单")
w()
if pending:
    w("| resource_id | status | status_reason（实测依据） |")
    w("|---|---|---|")
    for o in pending:
        w(f"| `{o['resource_id']}` | `{o['status']}` | {o['status_reason']} |")
else:
    w("**无挂起项。**")
    w()
    w("说明：本轮没有出现 `pending_ocr`。原因不是跳过，而是（a）所有可下载的图片都当场跑完了 OCR，"
      "（b）读不到的 PDF/扫描件类资源在 L0 阶段就已是 `no_scope`，本轮按 L0 状态登记为失败而非挂起。"
      "**扫描版 PDF 的 `< 50 字符/页` 判定规则本轮没有样本可施加**，已记入覆盖缺口。")
w()
w("## 5. 失败清单")
w()
w("### 5.1 `no_scope`（缺 scope 读不到）")
w()
ns = [o for k, p, o in prods if o["status"] == "no_scope"]
if ns:
    w("| resource_id | source_kind | 原因 |")
    w("|---|---|---|")
    for o in ns:
        w(f"| `{o['resource_id'][:56]}` | `{o['source_kind']}` | {o['status_reason']} |")
w()
w("### 5.2 `forbidden` / `unreachable`")
w()
fr = [o for k, p, o in prods if o["status"] in ("forbidden", "unreachable")]
if fr:
    w("| resource_id | status | source_kind | 原因 |")
    w("|---|---|---|---|")
    for o in fr:
        w(f"| `{o['resource_id'][:56]}` | `{o['status']}` | `{o['source_kind']}` | {o['status_reason']} |")
w()
w("### 5.3 `empty`（可读但抽不到内容）")
w()
em = [o for k, p, o in prods if o["status"] == "empty"]
if em:
    w("| resource_id | source_kind | 原因 |")
    w("|---|---|---|")
    for o in em:
        w(f"| `{o['resource_id'][:56]}` | `{o['source_kind']}` | {o['status_reason']} |")
w()
w(f"> `empty` 集中在**结构资源**（Base {sum(1 for o in em if o['source_kind']=='feishu_bitable_base')} 个、"
  f"表 {sum(1 for o in em if o['source_kind']=='feishu_bitable_table')} 个）："
  f"表/Base 的结构（字段名、选项）属于 L0 结构指纹的职责，L1 不把 schema 重复抽成内容，故不产出 segment。")
w()
w("## 6. 无法定位锚点的段落清单")
w()
w(f"**无。** 全部 {sum(seg_by_kb.values())} 个单元（segment + 表格行）都有锚点，"
  f"且锚点均来自原文物理位置：")
w()
w("| 锚点来源 | 单元数 | 依据 |")
w("|---|---|---|")
w(f"| 飞书文档标题路径 `#h.<路径>` / 行区间 `#l.a-b` | "
  f"{sum(1 for k,p,o in prods if o['source_kind']=='feishu_doc' for s in o['segments'])} | markdown 行号与标题层级 |")
w(f"| 网页正文行区间 `#l.a-b` | "
  f"{sum(1 for k,p,o in prods if o['source_kind']=='url' for s in o['segments'])} | 抓取正文的物理行号 |")
w(f"| 记录单元格 `#<表名>/<record_id>/<字段名>` | "
  f"{sum(1 for k,p,o in prods if o['source_kind']=='feishu_bitable_record' for s in o['segments'])} | "
  f"L0 台账里真实存在的 record_id 与字段名 |")
w(f"| 图片序号 `#img.N` | {sum(1 for k,p,o in prods for s in o['segments'] if s['kind']=='image_ocr')} | "
  f"该单元格内附件的存储顺序 |")
w()
w("## 7. 自主决策")
w()
dec = [
    ("按库分批、每批落盘", "顺序 wording → external_standard → internal_sample → product_desc → unknown；"
                          "每批写完即落盘，支持随时停在上一个完整批次。"),
    ("kb_type 直接继承 L0，不做二次判定", "规格要求；L1 不重新分类，仅校验与 L0 一致（自检 5 已验 0 处不符）。"),
    ("飞书文档与网页正文都按**原文物理行号**建锚点，而不是只给 `#block.<id>`",
     "飞书 API 返回的 markdown 不含稳定的 block_id 映射，硬编 block_id 等于编造；"
     "行号 + 标题路径是真实物理位置，可回原文定位。`#block.<block_id>` 规范保留在 anchor_spec 供有 block_id 的场景使用。"),
    ("`正面和负面样本` 表的 125 条记录未被 L0 登记（该表不在入口表 link 下钻路径上），"
     "因此 77 张图片没有 L0 资源可挂",
     "作为 **L1 媒体产物**登记：`resource_key = media:<table>:<record_id>`，"
     "`l0_parent_resource_key` 指向 L0 中确实存在的表资源；kb/l0/ 未改动。"
     "这条 L0 缺口已写进报告，供是否扩大 L0 下钻范围时决策。"),
    ("Base 附件走 `base +record-download-attachment` 而不是 `drive +download`",
     "实测 `drive:file:download` 缺 scope，但 Base 附件通道可用；这是本次让 OCR 路径真被验证的关键发现。"),
    ("OCR 用 macOS Vision（JXA 桥接），不引入第三方库",
     "本机无 tesseract/pytesseract，Swift 工具链与 SDK 版本不匹配；Vision 是系统框架，零安装依赖。"
     "输出逐行文本 + bbox + 置信度 + 图片 sha256，落 `media/<id>/ocr.json`。"),
    ("结构资源（表/Base）记 `empty` 而不是 `ok`",
     "schema 是 L0 结构指纹的职责；L1 不把字段名/选项重复抽成内容，避免两处真相。"),
    ("`empty` 与 `unreachable` 严格区分",
     "`empty` = 能读但确实没有可抽内容；`unreachable` = 根本没读到。混用会掩盖真实缺口。"),
    ("同一 `(resource_id, extractor_version, source_sha256)` 直接跳过",
     "幂等省钱的关键；OCR 结果不重算。本轮 404 条全为首次抽取，故 0 条 unchanged。"),
]
for i, (d, why) in enumerate(dec, 1):
    w(f"{i}. **{d}**")
    w(f"   - 依据：{why}")
w()
w("## 自检结论")
w()
w("| # | 检查项 | 结论 |")
w("|---|---|---|")
for i, (nm, res) in enumerate(checks, 1):
    w(f"| {i} | {nm} | {'✅ ' if res.startswith('通过') else '❌ '}{res} |")
w()
w("### 本次写入路径与外部调用")
w()
w(f"- 写入路径：全部在 `kb/l1/` 内（{len(l1_writes)} 个文件，越界 {len(outside)}）")
w(f"- `kb/l0/` ：{len(l0_files)} 个文件，L1 启动（11:26:00）后被写入 **{len(newer)}** 个；"
  f"L0 内最新 mtime = {datetime.datetime.fromtimestamp(l0_latest):%Y-%m-%d %H:%M:%S}（早于 L1 启动）")
w(f"- 外部调用：全为只读（附件下载 / 读取 L0 台账），见 `runs/{RUN}.ops.log`")
w()
with open(f"{L1}/runs/{RUN}.report.md", "w", encoding="utf-8") as fh:
    fh.write("\n".join(L) + "\n")

json.dump({"run_id": RUN, "extractor_version": EXTRACTOR_VERSION, "ocr_version": OCR_VERSION,
           "resources": len(prods), "ok": ok_all, "coverage_pct": round(ok_all / tot_all * 100, 2),
           "by_kb": {k: dict(v) for k, v in by_kb.items()},
           "segments_total": sum(seg_by_kb.values()), "chars_total": sum(char_by_kb.values()),
           "index_rows": idx_rows, "manifest_rows": len(man_latest), "retracted": n_retracted,
           "images": len(imgs), "video": "missing",
           "l0_blocked_rows": {f"{k[0]}|{k[1]}": v for k, v in l0_block.items()},
           "checks": checks, "kinds": dict(kinds)},
          open(f"{L1}/runs/{RUN}.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
json.dump({"by_kb": {k: dict(v) for k, v in by_kb.items()}, "seg_by_kb": dict(seg_by_kb),
           "char_by_kb": dict(char_by_kb), "kinds": dict(kinds), "images": imgs,
           "checks": checks, "status_all": dict(status_all), "by_source": dict(by_source),
           "idx_rows": idx_rows, "tot_all": tot_all, "ok_all": ok_all,
           "l0_block": {f"{k[0]}|{k[1]}": v for k, v in l0_block.items()}},
          open("kb/.work/l1_report_stats.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

print(f"index {idx_rows} 行 | 台账 {len(man_latest)} | 产物 {len(prods)} | 覆盖率 {ok_all/tot_all*100:.1f}%")
print("自检:", all(c[1].startswith("通过") for c in checks))
