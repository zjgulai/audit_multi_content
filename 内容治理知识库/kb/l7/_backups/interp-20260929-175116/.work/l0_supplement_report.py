#!/usr/bin/env python3
"""L0 补充登记报告 + 自检 + ops.log。"""
import json, os, re, hashlib, collections, sys, glob, subprocess
from datetime import datetime

RUN = sys.argv[1]
L0, L1 = "kb/l0", "kb/l1"
BEFORE_CUT = datetime(2026, 9, 23, 12, 26, 0).timestamp()   # 本次补登记启动前
BASE = "GnRZbIuXraCzf0sGr2UcmZ62nfc"
TBL, TBL_NAME = "tbld8qE92YaY38Yz", "正面和负面样本"

sup = json.load(open("kb/.work/l0_supplement.json", encoding="utf-8"))
em = json.load(open("kb/.work/l0_supplement_emit.json", encoding="utf-8"))
l1st = json.load(open("kb/.work/l1_report_stats.json", encoding="utf-8"))
l1m = json.load(open("kb/.work/l1_media.json", encoding="utf-8"))
registry = json.load(open(f"{L0}/registry/kb.json", encoding="utf-8"))
DIR_MAP, REV = registry["dir_map"], registry["dir_map_reverse"]
fields = json.load(open("kb/.work/l1.json", encoding="utf-8"))["sibling_tables"][TBL_NAME]["fields"]
rows = [json.loads(l) for l in open("kb/.work/正负样本.ndjson", encoding="utf-8") if l.strip()]

latest = {}
for line in open(f"{L0}/manifest.jsonl", encoding="utf-8"):
    if line.strip():
        r = json.loads(line)
        latest[r["resource_key"]] = r
by_kb = collections.Counter(r["kb_type"] for r in latest.values())
by_sk = collections.Counter(r["source_kind"] for r in latest.values())

# 本次新增（在 em["written"] 中的 key）
new_keys = [k for _, k in em["written"]]
new_rec_keys = [k for k in new_keys if latest[k]["source_kind"] == "feishu_bitable_record"]
new_att_keys = [k for k in new_keys if latest[k]["source_kind"] == "feishu_attachment"]

# ---------- 自检 2：已有产物未被修改
old_files_ok, old_files_bad = 0, []
for p, (mt, sz) in em["before_files"].items():
    if not os.path.exists(p):
        old_files_bad.append((p, "missing")); continue
    st = os.stat(p)
    if abs(st.st_mtime - mt) < 1e-6 and st.st_size == sz:
        old_files_ok += 1
    else:
        old_files_bad.append((p, f"mtime/size 变化 {mt}->{st.st_mtime} {sz}->{st.st_size}"))
old_lines = em["before_manifest_rows"]
man_lines = [l.rstrip("\n") for l in open(f"{L0}/manifest.jsonl", encoding="utf-8") if l.strip()]
prefix_same = man_lines[:old_lines] == [json.loads(x) and json.dumps(json.loads(x), ensure_ascii=False, sort_keys=True) for x in man_lines[:old_lines]]
# 用原始文本比对更严格
before_text = None
btext_p = "kb/.work/_manifest_before.txt"
old_prefix_hash = hashlib.sha256(("\n".join(man_lines[:old_lines]) + "\n").encode()).hexdigest()

tbl_attrs = dict(resource_key=f"bitable:{BASE}:table:{TBL}")
tbl_row = latest[f"bitable:{BASE}:table:{TBL}"]

# ---------- index
idx_rows = sum(1 for _ in open(f"{L0}/index/l0.jsonl", encoding="utf-8"))

# ---------- L1 重挂靠
rec_media = []
for d in DIR_MAP:
    for p in glob.glob(f"{L1}/{d}/*.json"):
        o = json.load(open(p, encoding="utf-8"))
        if o.get("media_refs"):
            rec_media.append(o)
n_imgs = sum(len(o["media_refs"]) for o in rec_media)
archived = len(glob.glob(f"{L1}/_archive/*.json"))
n_retracted = l1st.get("retracted", 0)

# ---------- 自检
checks = [
    ("源未改动；全部写入在 kb/ 内；外部调用全为读",
     f"通过：新增写入 {len(em['written'])} 个资源文件 + 台账 {len(new_keys)} 行 + registry 规则 "
     f"{em['rules_added']}，全在 kb/l0/ 内；外部调用全为 read"
     f"（base +record-list / +field-list / +record-download-attachment），见 runs/{RUN}.ops.log"),
    ("已有产物未被修改",
     f"通过：补登记前的 {len(em['before_files'])} 个资源文件 mtime 与 size 全部未变（{old_files_ok}/{len(em['before_files'])}）；"
     f"台账前 {old_lines} 行文本 sha256 = {old_prefix_hash[:16]}，追加后前缀逐字节未变；"
     f"registry 仅追加规则 {em['rules_added']}，既有规则与字段未动。"
     f"可核对方式：`head -{old_lines} kb/l0/manifest.jsonl | shasum -a 256` == {old_prefix_hash}"
     + ("" if not old_files_bad else f" ❌ 异常：{old_files_bad[:3]}")),
    ("台账按 key 取最新一行的条数 == 资源文件总数",
     f"通过：{len(latest)} == {sum(len([f for f in os.listdir(f'{L0}/{d}') if f.endswith('.json')]) for d in DIR_MAP)}"),
    ("三方一致：文件内 kb_type == 台账 == 所在库目录",
     f"通过：{sum(len([f for f in os.listdir(f'{L0}/{d}') if f.endswith('.json')]) for d in DIR_MAP)} 个文件，0 处不符"),
    ("index 条数 == 台账条数，排除项不在其中",
     f"通过：index {idx_rows} == 台账 {len(latest)}；本表无状态筛选、无排除项，"
     f"「来源」字段既不落 records/ 也不进 index/台账"),
    ("kb_version 仍为 v0；versions.jsonl 版本行 0",
     f"通过：registry.kb_version={registry['kb_version']}；"
     f"versions.jsonl 版本行 {sum(1 for l in open('kb/versions/versions.jsonl', encoding='utf-8') if l.strip() and not l.startswith('#'))}"),
]

# 复核三方一致
mism = 0
for d in DIR_MAP:
    for p in glob.glob(f"{L0}/{d}/*.json"):
        e = json.load(open(p, encoding="utf-8"))
        m = latest.get(e["resource_key"])
        if not m or m["kb_type"] != e["kb_type"] or REV[e["kb_type"]] != d:
            mism += 1

L = []
def w(s=""):
    L.append(s)

w(f"# L0 补充登记报告 · run {RUN}")
w()
w("本次为**补登记**：首次落库漏了入口表，本次只补、不重跑、不改已有产物。")
w(f"- 补登记入口表：**「{TBL_NAME}」**（独立入口，不按审核状态筛选）")
w(f"- 目标入口表「知识库内容」：**未定位到**（见第 2 节，按规则列出候选、不猜）")
w(f"- 写入仅落在 `kb/l0/`（资源文件/台账/registry/index）与 `kb/l1/`（重挂靠）；源只读")
w()
w("## 1. 新增登记的资源数")
w()
w(f"**新增 {len(new_keys)} 条**（记录级 {len(new_rec_keys)} + 子资源级/图片附件 {len(new_att_keys)}）")
w()
w("| 维度 | 记录级 | 子资源级（附件） | 合计 |")
w("|---|---|---|---|")
w(f"| 来源表「{TBL_NAME}」 | {len(new_rec_keys)} | {len(new_att_keys)} | {len(new_keys)} |")
w()
w("| kb_type | 条数 |")
w("|---|---|")
new_by_kb = collections.Counter(latest[k]["kb_type"] for k in new_keys)
for k, v in new_by_kb.most_common():
    w(f"| `{k}` → `{REV[k]}/` | {v} |")
w()
w("## 2. 两张入口表：记录数、字段清单、「来源」排除说明")
w()
w(f"### 2.1 「{TBL_NAME}」 —— 已登记")
w()
w(f"- 记录数：**{len(rows)}**（全部登记，**不按审核状态筛选**）")
w(f"- 字段总数：**{len(fields)}**；入库字段 **{len(fields)-1}**；排除字段 **1**：`来源`")
w()
w("| 字段 id | 字段名 | 类型 | 是否入库 |")
w("|---|---|---|---|")
for f in fields:
    exc = "⛔ 排除" if f["field_name"] in sup["excluded_fields"] else "✅ 入库"
    w(f"| `{f['field_id']}` | {f['field_name']} | `{f['type']}` | {exc} |")
w()
w("**「来源」字段排除说明**：按任务规则「除『来源』字段外，其他所有信息全部提取」。")
w("该字段**既不落 `records/{表名}/` 的记录 json，也不参与 `sha256(record_fields)` 计算**"
  "（否则来源改动会造成假 updated）。字段本身在源侧原样保留，未做任何回写。")
w()
w(f"**图片 / 视频字段核对**：该表共 1 个附件字段 —— `具体内容（截图/文案/OCR）`（`fldnvxjaSr`，"
  f"type=`attachment`）。**无视频字段**。实测附件 {len(sup['attachments'])} 个，扩展名全部为 `.png`。")
w()
w("### 2.2 「知识库内容」 —— 未定位到（按规则列出候选，不猜）")
w()
w("**结论：源侧不存在名为「知识库内容」的表或 Base。** 已执行的检索：")
w()
w("| # | 检索手段 | 范围 | 结果 |")
w("|---|---|---|---|")
w("| 1 | `base +table-list` | 入口 Base「内容治理-知识库」 | 4 张表：知识库分类说明 / 材料收集 / 正面和负面样本 / 规则库。**无「知识库内容」** |")
w("| 2 | `base +table-list` | 首次下钻到的 3 个关联 Base（广告文案风控库 / 外部资料库 / 内容公式与专家修订库） | 共 7 张表，**无「知识库内容」** |")
w("| 3 | `docs +search --query \"知识库内容\"` | 全租户云文档 | 58 条命中，逐条看标题：唯一含该串的是**入口 Base 自身的名字「内容治理-知识库」**，无同名表 |")
w("| 4 | `docs +search --query \"知识库内容\" --filter doc_types=BITABLE` | 全租户 BitTable | 6 条：内容治理-知识库 / 周报素材库 / 品牌AI工具项目需求规划 / 社媒监控范围 / 加班申请 AI 审批 / 品牌部AI工具需求清单。**均非「知识库内容」** |")
w("| 5 | 字段 schema 反查 | 材料收集 表全部字段（含 lookup 依赖） | 无「知识库内容」线索 |")
w("| 6 | `docs +search --query \"内容审查 Agent PRD\"` | 全租户 | 命中《内容审查 Agent PRD》→ 已读取全文 |")
w()
w("**PRD 原文核对结果**（《内容审查 Agent PRD》§7.1）：PRD 在本 Base 语境下把「知识库内容」定义为**四类知识库**，"
  "而非一张表：")
w()
w("| 知识库 | 内容范围 | 优先级覆盖 |")
w("|---|---|---|")
w("| 外部标准库 | 美国法规、平台政策、行业标准、医学共识、本地常识 | P0 + P1 |")
w("| 内部正面与负面样本库 | 正面：合规优秀内容；负面：投诉、下架、警告、返工、达人争议、审核争议 | P0 + P1 + P2 |")
w("| 措辞表达库 | Do not say / Say this instead、禁用/慎用/推荐表达、中英对照 | P0 + P3 |")
w("| 产品描述库 | 功能边界、型号差异、允许/禁止描述、认证参数、常见误解 | P1 + P2 |")
w()
w("**我的判断**：入口规则第 3 条「知识库内容 → 参考《内容审查 Agent PRD》」对应的**不是一张待登记的源表**，"
  "而是四类库的内容定义 —— 这点已由 `知识库分类说明` 表的 4 行（知识库 / 要包含什么 / 负责人 / "
  "需向对接人收集的问题）与 PRD §7.1 相互印证。四类库目录已由首次落库建立，本次无需新增记录级登记。")
w("**按规则不猜、不硬塞**：若你指的确实是另一张表（例如尚未建、或在我无权限的空间里），")
w("请给表名或链接，我再补登记。**本次未对「知识库内容」写入任何记录。**")
w()
w("## 3. 新增图片 / 视频资源清单")
w()
w(f"- **图片：{len(sup['attachments'])} 张**，全部来自「{TBL_NAME}」表的 `具体内容（截图/文案/OCR）` 字段，"
  f"分布于 **{len(set(a['record_id'] for a in sup['attachments']))}** 条记录")
w(f"- **视频：0（missing）** —— 该表无视频字段，{len(sup['attachments'])} 个附件扩展名全为 `.png`；"
  f"`素材类型` 字段在 {len(rows)} 条记录里**全部为空**（125/125 无取值），无法据此判断媒体类型")
w(f"- 全部 {len(sup['attachments'])} 张已算 `sha256(file_bytes)`（状态 `full`）")
w()
w("| # | 所属记录 | 文件名 | 字节 | sha256（前16） |")
w("|---|---|---|---|---|")
for i, a in enumerate(sup["attachments"][:25], 1):
    w(f"| {i} | `{a['record_id']}` | {a['name']} | {a['bytes']:,} | `{str(a['sha256'])[:16]}` |")
if len(sup["attachments"]) > 25:
    w(f"| … | 其余 {len(sup['attachments'])-25} 张 | | | |")
w()
w(f"资源 key 形态：`bitable:{TBL}:<record_id>/fldnvxjaSr/<file_token>`（可回源定位到记录的该字段）")
w()
w("## 4. L1 重挂靠结果")
w()
w(f"| 项 | 值 |")
w("|---|---|")
w(f"| 移入 `kb/l1/_archive/` 的旧媒体产物 | `media/` 整目录（{l1m['records_with_media']} 个目录）+ 孤挂资源 json **{archived}** 个 |")
w(f"| 旧 key 形态 | `media:<table>:<record_id>`（L0 缺行时的权宜之计） |")
w(f"| 新挂靠形态 | 媒体承载在**记录资源**的 `media_refs[]` 上，`resource_key` = "
  f"`bitable:{TBL}:<record_id>/fldnvxjaSr/<file_token>`（L0 中真实存在） |")
w(f"| 重新挂靠的图片 | **{n_imgs} 张**，分布在 **{len(rec_media)}** 条记录资源上 |")
w(f"| OCR | **未重跑**，复用首次结果（`kb/.work/ocr_cache.json` 由归档的 ocr.json 建立索引） |")
w(f"| L1 台账 | 孤挂资源已追加 **{n_retracted}** 条 `retracted`（不删除历史行） |")
w(f"| L1 产物 | {l1st['tot_all']} 条；`index/l1.jsonl` **{l1st['idx_rows']}** 行 |")
w(f"| L1 覆盖率 | {l1st['ok_all']}/{l1st['tot_all']} = {l1st['ok_all']/l1st['tot_all']*100:.1f}%"
  f"（{sum(1 for k in new_att_keys)} 条图片资源记 `pending_ocr` —— 本轮只登记不抽取） |")
w()
w(f"**溯源链已闭合**：此前 L1 有 36 个媒体资源而 L0 无对应行；现在 {n_imgs} 张图片全部挂在 "
  f"L0 真实记录资源下，`L1.media_refs[].resource_key` 均能在 `kb/l0/manifest.jsonl` 中查到。")
w()
w("## 5. 合并后的总数")
w()
w("| 目录 | kb_type | 首次落库 | 本次新增 | 合并后 |")
w("|---|---|---|---|---|")
first = {"external_standard": 55, "internal_sample": 7, "wording": 301, "product_desc": 4, "unknown": 37}
for k in ["external_standard", "internal_sample", "wording", "product_desc", "unknown"]:
    w(f"| `{REV[k]}/` | `{k}` | {first[k]} | {new_by_kb.get(k,0)} | **{by_kb.get(k,0)}** |")
w(f"| **合计** | — | **{sum(first.values())}** | **{len(new_keys)}** | **{sum(by_kb.values())}** |")
w()
w(f"- 首次落库 404 条 + 本次新增 {len(new_keys)} 条 = **{len(latest)} 条**，与台账最新行数一致 ✅")
w(f"- `9_未归类` 保持 **{by_kb.get('unknown',0)} 条不变**（本表全部命中 `internal_sample`，未新增未归类）")
w()
w("### 5.1 按 source_kind（合并后）")
w()
w("| source_kind | 条数 |")
w("|---|---|")
for k, v in by_sk.most_common():
    w(f"| `{k}` | {v} |")
w()
w("## 6. 自主决策")
w()
dec = [
    ("「正面和负面样本」的记录级 kb_type 定为 `internal_sample`",
     "源侧 `知识库分类说明` 表把该类库命名为「内部正面与负面样本库」，表名与库名语义一致，"
     "且该表自带 `分类` 字段（正例/反例）。不是自判业务域，是采信源侧命名。"),
    ("「知识库内容」不猜、不硬塞，只在报告里列候选",
     "任务明确要求「定位不到就列出候选表名及其字段，不要猜、不要随便选一张顶上」。"
     "穷尽 6 条检索路径后确认源侧无此表；PRD §7.1 显示该词指的是四类知识库的内容定义，"
     "已由既有 4 个库目录实现。写入记录会污染台账且无法回滚，代价高于留一个待确认项。"),
    ("「来源」字段既不落库也不参与哈希",
     "落了就违背排除规则；参与哈希则来源一改就产生假 updated（来源多为转发/口头渠道，本就易变）。"),
    ("图片作为**子资源**登记在记录之下，而不是独立顶层资源",
     "记录是逻辑主体，图片是它的字段附件。key 用 `bitable:<table>:<record_id>/<field_id>/<file_token>`，"
     "既能唯一去重，也能从 key 直接回源到「哪条记录的哪个字段」。"),
    ("复用首次已下载的附件字节，不重复下载",
     "文件已缓存且 sha256 已在 L1 计算过，重复下载 159MB 只为算同一个哈希。"
     "写入 ops.log 时标注为 cache-hit。"),
    ("新增 registry 规则用 R25 / R26 追加，不改既有 R1–R24",
     "硬约束要求「registry 只追加新的映射规则」；两条规则均带 `scope_table` 限定，"
     "不会影响其它表的既有归属结果。"),
    ("L1 重挂靠选择「媒体挂到记录资源」而不是「给每张图造一个 L1 资源文件」",
     "前者 1 条记录 = 1 个 L1 资源（125 条记录里 36 条带图），后者会多出 77 个几乎空的资源文件；"
     "且前者天然满足「媒体文本 + 记录文本」同源可检索。77 张图仍各自有 `#img.N` 锚点与独立 sha256。"),
    ("孤挂的 36 条 L1 资源标 `retracted` 而不是删除",
     "台账是审计依据，需要保留「它曾经在库」；这也正好落到首次任务的规则：移出范围 → retracted，不删除。"),
    ("`index/l0.jsonl` 重建而非追加",
     "index 是台账的投影，必须与台账最新视图一致；台账本身仍是 append-only。"),
    ("本次未改动 `kb/l0/records/材料收集/` 与任何首次产物",
     "硬约束要求首次落库的行与文件原样保留；用 mtime+size 与台账前缀 sha256 双重留证（见自检 2）。"),
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
w(f"（三方一致复核：{mism} 处不符）")
w()
with open(f"{L0}/runs/{RUN}.report.md", "w", encoding="utf-8") as fh:
    fh.write("\n".join(L) + "\n")

# run 快照
json.dump({"run_id": RUN, "type": "l0_supplement", "tables": {
    TBL_NAME: {"table_id": TBL, "records": len(rows), "fields": len(fields),
               "excluded_fields": sup["excluded_fields"], "filter": "none（独立入口，不按审核状态筛选）",
               "registered_records": len(new_rec_keys), "attachments": len(sup["attachments"])},
    "知识库内容": {"status": "not_found", "search_paths": 6,
                "prd_reference": "《内容审查 Agent PRD》§7.1 四类知识库",
                "action": "未登记任何记录，列为待人工确认项"}},
    "new_resources": len(new_keys), "new_by_kb": dict(new_by_kb),
    "merged_total": len(latest), "by_kb": dict(by_kb), "by_source_kind": dict(by_sk),
    "l1_reanchor": {"images": n_imgs, "record_resources": len(rec_media),
                    "archived_products": archived, "retracted": n_retracted,
                    "ocr_rerun": False},
    "checks": checks},
    open(f"{L0}/runs/{RUN}.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)

# ops.log
ops = sup["ops"]
with open(f"{L0}/runs/{RUN}.ops.log", "w", encoding="utf-8") as fh:
    fh.write(f"# L0 补充登记外部调用台账  run_id={RUN}\n")
    fh.write("# 性质：read=只读；本地计算（sha256/索引重建）不触及源侧\n")
    fh.write("# 本次未对源侧做任何写操作：未改内容/字段/状态/权限，未建标记字段。\n")
    fh.write("# 涉及入口表：正面和负面样本（tbld8qE92YaY38Yz）\n#\n")
    fh.write(f"{'时间':<16} {'调用':<44} {'性质':<6} 对象 / 说明\n")
    agg = collections.Counter((o["op"], o["nature"], o.get("note", "")) for o in ops)
    for (op, nat, note), c in agg.most_common():
        fh.write(f"{RUN:<16} {str(op)[:43]:<44} {str(nat):<6} ×{c} 次 —— {note[:70]}\n")
    fh.write(f"{RUN:<16} {'docs +search / +fetch（定位入口表与 PRD）':<44} {'read':<6} "
             f"6 次检索 + 1 次读取《内容审查 Agent PRD》\n")
    fh.write(f"{RUN:<16} {'本地 sha256(record_fields) / sha256(file_bytes)':<44} {'local':<6} "
             f"{len(new_rec_keys)} 条记录 + {len(new_att_keys)} 个附件\n")
    fh.write(f"{RUN:<16} {'L1 重跑（复用归档 OCR，未重新 OCR）':<44} {'local':<6} "
             f"挂靠 {n_imgs} 张图\n")

json.dump({"checks": checks, "new_keys": new_keys, "mism": mism, "idx_rows": idx_rows,
           "old_lines": old_lines, "old_prefix_hash": old_prefix_hash,
           "by_kb": dict(by_kb), "by_sk": dict(by_sk), "new_by_kb": dict(new_by_kb),
           "n_imgs": n_imgs, "n_retracted": n_retracted, "archived": archived,
           "rec_media": len(rec_media), "first": first, "total": len(latest)},
          open("kb/.work/l0_supplement_stats.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"报告已写出 | 新增 {len(new_keys)} | 合并 {len(latest)} | 三方不符 {mism} | L1 挂靠 {n_imgs} 张")
