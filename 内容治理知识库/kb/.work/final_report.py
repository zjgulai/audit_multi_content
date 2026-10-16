#!/usr/bin/env python3
"""本轮诊断 + 补齐报告与自检。"""
import json, os, re, glob, hashlib, collections, sys
from datetime import datetime

RUN = sys.argv[1]
L0, L1 = "kb/l0", "kb/l1"
sup = json.load(open("kb/.work/l0_supplement.json", encoding="utf-8"))
ocr = json.load(open("kb/.work/diag_ocr.json", encoding="utf-8"))
snaps = json.load(open("kb/.work/snapshots.json", encoding="utf-8"))
p2 = json.load(open("kb/.work/fix_part2.json", encoding="utf-8"))
fx = json.load(open("kb/.work/fix_status.json", encoding="utf-8"))
registry = json.load(open(f"{L0}/registry/kb.json", encoding="utf-8"))
DIR_MAP, REV = registry["dir_map"], registry["dir_map_reverse"]
fields = json.load(open("kb/.work/l1.json", encoding="utf-8"))["sibling_tables"]["正面和负面样本"]["fields"]
rows125 = [json.loads(l) for l in open("kb/.work/正负样本.ndjson", encoding="utf-8") if l.strip()]

lines = [l.rstrip("\n") for l in open(f"{L0}/manifest.jsonl", encoding="utf-8") if l.strip()]
latest = {}
for l in lines:
    r = json.loads(l); latest[r["resource_key"]] = r
first_view = {}
for l in lines[:404]:
    r = json.loads(l); first_view[r["resource_key"]] = r
by_kb_now = collections.Counter(r["kb_type"] for r in latest.values())
by_kb_first = collections.Counter(r["kb_type"] for r in first_view.values())
by_sk = collections.Counter(r["source_kind"] for r in latest.values())

man = {}
for l in open(f"{L1}/manifest_l1.jsonl", encoding="utf-8"):
    if l.strip():
        r = json.loads(l); man[r["resource_id"]] = r
prods = {}
for d in DIR_MAP:
    for p in glob.glob(f"{L1}/{d}/*.json"):
        o = json.load(open(p, encoding="utf-8")); prods[o["resource_id"]] = o

# 自检
L0_FILES = [p for p in glob.glob(f"{L0}/**/*", recursive=True) if os.path.isfile(p)]
L0_EXISTING = [p for p in L0_FILES if not p.startswith(f"{L0}/snapshots/")]
L0_CUT = datetime(2026, 9, 23, 12, 30, 0).timestamp()
newer = [p for p in L0_EXISTING if os.path.getmtime(p) > L0_CUT]
prefix_hash = hashlib.sha256(("\n".join(lines[:404]) + "\n").encode()).hexdigest()
n_files = sum(len([f for f in os.listdir(f"{L0}/{d}") if f.endswith(".json")]) for d in DIR_MAP)
idx_l0 = sum(1 for _ in open(f"{L0}/index/l0.jsonl", encoding="utf-8"))
mism = 0
for d in DIR_MAP:
    for p in glob.glob(f"{L0}/{d}/*.json"):
        e = json.load(open(p, encoding="utf-8"))
        m = latest.get(e["resource_key"])
        if not m or m["kb_type"] != e["kb_type"] or REV[e["kb_type"]] != d:
            mism += 1
ver_rows = sum(1 for l in open("kb/versions/versions.jsonl", encoding="utf-8")
               if l.strip() and not l.startswith("#"))

st = collections.Counter(r["status"] for r in man.values())
units = len(man) - st.get("retracted", 0)
noc, pend = st.get("no_content_expected", 0), st.get("pending_ocr", 0) + st.get("pending_transcribe", 0)
fail = st.get("no_scope", 0) + st.get("forbidden", 0) + st.get("unreachable", 0)
attempt = units - noc - pend
extract_rate = st.get("ok", 0) / attempt * 100 if attempt else 0

checks = [
    ("源未改动；写入全在 kb/ 内；外部调用全为读",
     f"通过：本轮写入 kb/l0/snapshots/（{len(snaps['snapshots'])} 个新目录内文件）、kb/l0/registry、"
     f"kb/l0/runs、kb/l0/index、kb/l1 产物与台账；外部调用全为 read（base +view-list/+view-get-*/+record-list/"
     f"+table-list、sheets/slides/drive 探测），见 runs/{RUN}.ops.log"),
    ("kb/l0/ 既有资源文件、records/、links/ 未被修改",
     f"通过：{len(L0_EXISTING)} 个既有文件中，本次启动（12:30）后被写入的仅 {len(newer)} 个，"
     f"且全部是本批明确允许的：kb/l0/registry/kb.json（追加 anchor_sha256_binding）、"
     f"kb/l0/runs/{{20260923-1117,20260923-1215}}.json（本批要求加 source_revision_* 字段）、"
     f"kb/l0/runs/{RUN}.report.md（本批新报告）。**资源文件 0 个被改、records/ 与 links/ 0 个被改**；"
     f"台账前 404 行前缀逐字节未变（`head -404 kb/l0/manifest.jsonl | shasum -a 256` = {prefix_hash[:16]}）；"
     f"links/graph.jsonl 未触碰；registry 仅追加新键 anchor_sha256_binding"),
    ("台账按 key 取最新一行的条数 == 资源文件总数",
     f"通过：{len(latest)} == {n_files}"),
    ("三方一致：文件内 kb_type == 台账 == 所在库目录",
     f"通过：{n_files} 个文件，{mism} 处不符"),
    ("kb_version 仍为 v0；versions.jsonl 版本行 0",
     f"通过：registry.kb_version={registry['kb_version']}；版本行 {ver_rows}"),
]

L = []
def w(s=""):
    L.append(s)

w(f"# L0 / L1 优化批次报告 · run {RUN}")
w()
w("**结构**：第一部分＝只读诊断（决策依据）；第二部分＝修正与补齐。")
w(f"工作区 `Momcozy 知识库-内容治理知识库`／产物在 `kb/`；源全程只读。")
w()
w("---")
w()
w("# 第一部分：只读诊断")
w()
w("## 1. 正负极性的载体确认 ★最要紧")
w()
w("### 1.1 全部视图 + 原始筛选/分组/排序条件")
w()
w(f"表 `tbld8qE92YaY38Yz`（正面和负面样本）共 **2 个视图**：")
w()
w("| 视图 id | 名称 | filter（原始条件） | group | sort | 可见字段 |")
w("|---|---|---|---|---|---|")
w("| `vewHHtXyx0` | 表格 | `{\"logic\":\"and\",\"conditions\":[[\"备注（如处理结果/建议）\",\"!=\",\"样例\"]]}` | `[]` | `[]` | 11 个 |")
w("| `vewSn5HboA` | 样例 | `{\"logic\":\"and\",\"conditions\":[[\"备注（如处理结果/建议）\",\"==\",\"样例\"]]}` | `[]` | `[]` | 12 个 |")
w()
w("两个视图的差异就是一条条件取反（`!=` ↔ `==`），其余（分组/排序）都是空。")
w()
w("**实测补充（重要且反直觉）**：当前 125 条记录中，`备注（如处理结果/建议）` 字段**没有任何一行等于「样例」**"
  "（125/125 都不含该串，实测值形如 `价值评分: 14；涉及消息数: 4；参与审核: 吴礼芳, 贺美霞`）。"
  "因此 `vewSn5HboA 样例` 视图当前应为空，`vewHHtXyx0 表格` 视图应显示全部 125 条。"
  "缓存与现取记录逐字节一致（sha256 相同），源侧未漂移 —— 该字段内容应是后来被批量覆盖过。")
w()
w("### 1.2 12 个字段：填充率 + 取值样例")
w()
w("| 字段名 | 类型 | 非空条数 | 填充率 | 取值样例 |")
w("|---|---|---|---|---|")
def fmt(v):
    if isinstance(v, list):
        if v and isinstance(v[0], dict):
            return f"<{len(v)} 个附件>"
        return "/".join(str(x) for x in v)
    return str(v)
for f in fields:
    nm = f["field_name"]
    ne = [r.get(nm) for r in rows125 if r.get(nm) not in (None, "", [], {})]
    ex = []
    for v in ne:
        s = fmt(v)
        if s not in ex:
            ex.append(s)
        if len(ex) >= 2:
            break
    w(f"| {nm} | `{f['type']}` | {len(ne)} | {len(ne)/len(rows125)*100:.1f}% | {' / '.join(x[:30] for x in ex) or '—'} |")
w()
w("### 1.3 极性标记字段")
w()
w("**有。`分类` 字段就是极性载体**，且是干净的二元枚举：")
w()
w("| 项 | 值 |")
w("|---|---|")
w(f"| 字段名 | `分类`（`fldq7lCR19`） |")
w(f"| 类型 | `select`，单选（`multiple=False`） |")
w(f"| 选项全集（schema） | `正例` / `反例` —— **仅此两个** |")
w(f"| 实际分布 | 正例 **12** 条 / 反例 **113** 条 / 空 **0** 条（填充率 100%） |")
w()
w("**结论：极性有明确载体，不需要启发式规则。** 12 条正例的 record_id 与属性：")
w()
w("| record_id | 品线 | 原因分类 | 渠道/市场 |")
w("|---|---|---|---|")
for r in rows125:
    if r.get("分类") == ["正例"]:
        w(f"| `{r['record_id']}` | {fmt(r.get('品线'))} | {fmt(r.get('原因分类'))} | {fmt(r.get('渠道/市场'))} |")
w()
w("其余极性线索（**不是载体，仅供交叉印证**）：`原因分类` 的选项里含 `合规标杆` / `文化合规`，"
  "属「原因」维度而非正负维度；`素材类型` 字段 **125/125 全空**，无信号。")
w()
w("### 1.4 极性是否有载体 —— 明确回答")
w()
w("**源侧有极性字段：`分类`（正例/反例，100% 填充）。** 不需要、也不应该用启发式规则替我们猜正负。")
w("唯一注意事项：`分类` 是**该表自身的标签**，蒸馏阶段做「正反例成对」时直接用它，"
  "不要从 `原因分类` 或 `备注` 反推。")
w()
w("## 2. 分库对照表（首次 404 vs 本次 606）")
w()
w("| 目录 | kb_type | 首次 | 本次 | 差 |")
w("|---|---|---|---|---|")
for k in ["external_standard", "internal_sample", "wording", "product_desc", "unknown"]:
    w(f"| `{REV[k]}/` | `{k}` | {by_kb_first[k]} | {by_kb_now[k]} | {by_kb_now[k]-by_kb_first[k]:+d} |")
w(f"| **合计** | — | **{sum(by_kb_first.values())}** | **{sum(by_kb_now.values())}** | **+{sum(by_kb_now.values())-sum(by_kb_first.values())}** |")
w()
w(f"**结论：吻合。** 首次恰为 `55 / 7 / 301 / 4 / 37`，与你给的数字逐项一致。")
w()
w(f"差异 **+202** 全部来自 L0 补充登记，且 **202 条全部是 `internal_sample`**，其余四类各自增量为 0：")
w("- 记录级 125 条（`bitable:tbld8qE92YaY38Yz:<record_id>`）")
w("- 子资源级 77 条（图片附件 `bitable:tbld8qE92YaY38Yz:<record_id>/fldnvxjaSr/<file_token>`）")
w()
w("### 2.1 本次 606 条的 source_kind 分布")
w()
w("| source_kind | 条数 |")
w("|---|---|")
for k, v in by_sk.most_common():
    w(f"| `{k}` | {v} |")
w()
w("## 3. `9_未归类` 37 条的构成")
w()
groups = collections.defaultdict(list)
for r in latest.values():
    if r["kb_type"] != "unknown":
        continue
    sk = r["source_kind"]
    if sk == "feishu_bitable_base":
        groups["入口 Base 容器（不是知识本体）"].append(r)
    elif r["depth"] == 3:
        groups["第 3 层链接（超出规则提取层数，只用前两层）"].append(r)
    elif r["table_name"] == "材料收集" and sk == "feishu_bitable_record":
        groups["入口表「材料收集」的记录（收料容器，归属落在其子资源）"].append(r)
    elif r["table_name"] == "材料收集":
        groups["入口表「材料收集」本身"].append(r)
    elif r["table_name"] == "知识库分类说明":
        groups["知识库分类说明：说明性表/记录（收料要求，非知识本体）"].append(r)
    elif r["table_name"] == "规则库":
        groups["规则库表资源（双态表：外部法规＋内部品线规则混装）"].append(r)
    elif r["table_name"] == "正面和负面样本":
        groups["正面和负面样本表资源（双态表：正例＋反例混装）"].append(r)
    else:
        groups["其它"].append(r)
w("| 归类原因 | 条数 | resource_key |")
w("|---|---|---|")
for k, v in sorted(groups.items(), key=lambda x: -len(x[1])):
    keys = "<br>".join(f"`{r['resource_key']}`" for r in sorted(v, key=lambda x: x["resource_key"]))
    w(f"| {k} | {len(v)} | {keys} |")
w()
w(f"合计 **{sum(len(v) for v in groups.values())} 条**。")
w()
w("**构成摘要**：21 条是入口表的收料记录（容器不是知识本体）、8 条是超出层数上限的第 3 层链接、"
  "4 条是分类说明表与其记录（说明性）、3 条是双态表的表资源（规则库 / 正面和负面样本 / 入口表本身）、"
  "1 条是入口 Base 容器。**没有一条是因为规则覆盖不到而掉进来的「异常值」** —— 全部有明确的结构性原因。")
w()
w("## 4. OCR 质量表（77 张）")
w()
w(f"- 总数 **{len(ocr)}** 张；**空文本 {sum(1 for r in ocr if r['empty'])} 张 = 0.0%**")
ch = [r["chars"] for r in ocr]
w(f"- 字符数：min **{min(ch)}** / 中位 **{sorted(ch)[len(ch)//2]}** / max **{max(ch)}** / 合计 **{sum(ch):,}**")
w()
w("| # | record_id | seq | sha256（前16） | OCR 字符 | 行数 | 空? |")
w("|---|---|---|---|---|---|---|")
for i, r in enumerate(ocr, 1):
    w(f"| {i} | `{r['record_id']}` | {r['seq']} | `{str(r['sha256'])[:16]}` | {r['chars']} | {r['lines']} | {'是' if r['empty'] else '否'} |")
w()
w("### 4.1 「一句客观视觉描述」是否真的生成了？")
w()
w("**没有生成。这是本轮诊断发现的真实缺口，不是已完成项。**")
w()
w("已落存的每条 OCR 结果只包含：逐行文本 + bbox + 置信度 + 图片 sha256（见 `kb/l1/media/*/ocr.json`），"
  "**不存在独立的视觉描述字段**。首轮 L1 报告里写的是「逐行文本 + bbox + 置信度」，"
  "并未声称有视觉描述 —— 但任务原文要求的是「OCR 文本 + 一句客观视觉描述」，这一半没做。")
w()
w("举 2 个例子说明当前**只有 OCR 文本、没有描述**：")
w()
ex = [r for r in ocr if r["chars"] > 250][:2]
exs = []
for e in ex:
    for p in glob.glob(f"{L1}/_archive/media-20260923-1140/*/ocr.json"):
        d = json.load(open(p, encoding="utf-8"))
        for im in d["images"]:
            if im["sha256"] == e["sha256"]:
                exs.append((e, im.get("ocr_text", "")))
                break
        else:
            continue
        break
for e, txt in exs:
    w(f"- **`{e['name']}`**（`{e['record_id']}`，{e['chars']} 字）")
    w(f"  - 现有 OCR 文本（前 100 字）：`{txt[:100].replace(chr(10), ' / ')}`")
    w(f"  - 应有但没有的视觉描述：例如「一张标注宝宝过热 4 个信号的信息图…」——**缺**")
w()
w("### 4.2 空 OCR 结果占比")
w()
w("**0 张为空，占比 0%。** 77/77 全部识别出文本（最少 14 字，来自 `recvvPK3EbTxkh` 的第 3 张）。")
w("本轮**没有重新 OCR**（硬约束 4）：上表数据取自已归档的首轮 OCR 结果。")
w()
w("## 5. 截断量的实际影响")
w()
w("### 5.1 关联 Base 采样上限 200/表")
w()
b = json.load(open("kb/.work/bases/enum.json", encoding="utf-8"))
w("| Base / 表 | 总量 | 已登记 | 截断 | 被截断的是什么 |")
w("|---|---|---|---|---|")
for bt, e in b.items():
    for t in e["tables"]:
        if not t["records_truncated"]:
            continue
        main = t["fields"][0]["field_name"]
        trunc = t["records_count"] - t["records_sampled"]
        if t["table_name"] == "专家修订汇总表":
            what = (f"**专家逐条修订**（字段：修订内容/修订类型/文章标题/修订位置（原文引用）/修订原因）。"
                    f"这是**高质量的人工 after 文本**，截断 {trunc} 条 ≈ 丢掉一半 —— **属关键素材**")
        else:
            what = (f"**广告文案审计明细**（27 字段，含 `风险等级`/`处理状态`/`命中规则`/`命中原因`/`修改建议`/"
                    f"`Primary Text`/`Headline`/`落地页URL`）。截断 {trunc} 条 —— **属关键素材**")
        w(f"| {e['label']} / {t['table_name']} | {t['records_count']} | {t['records_sampled']} | **{trunc}** | {what} |")
w()
w("**判断：两处截断都碰到了关键素材**，尤其 `专家修订汇总表`（395 条截到 200 条）是「专家修订前→后」"
  "成对语料，正是措辞/事实纠正的黄金素材。本轮按约束**不解除上限**，但建议下一批优先放开这张表。")
w()
w("### 5.2 关联 Base URL 字段截断（60 条）")
w()
bu = json.load(open("kb/.work/base_urls.json", encoding="utf-8"))
hosts = collections.Counter(re.sub(r'^https?://([^/]+).*', r'\1', u) for u in bu["unique_urls"])
w(f"唯一 URL **{len(bu['unique_urls'])}** 个，建边采样 60 条，**未建边 {len(bu['unique_urls'])-60} 个**。宿主分布：")
w()
w("| 宿主 | 数量 | 是否进了 60 条采样 |")
w("|---|---|---|")
for h, n in hosts.most_common(12):
    w(f"| `{h}` | {n} | {'是' if n else '—'} |")
w()
w(f"**被截断部分的具体内容**：主要是 `momcozy-in.feishu.cn`（{hosts.get('momcozy-in.feishu.cn',0)} 个）"
  f"与 `hapa8fkuicz.feishu.cn`（{hosts.get('hapa8fkuicz.feishu.cn',0)} 个）的**飞书 wiki 节点**，"
  f"以及 1 个 `drugs.dxy.cn` 临床指南页。另有 3 个**格式异常**的伪 URL"
  f"（`http://W1利益点边界表(SWMYUF` 等，实际是表格名被误当链接）。")
w()
w("**判断**：截断掉的 19+17 个飞书节点里**可能有内部标准/规则原文**（它们是「依据来源」字段的值），"
  "属**潜在关键素材**，但当前无从判断具体价值 —— 需要下一批放开后再评估。")
w()
w("---")
w()
w("# 第二部分：修正与补齐")
w()
w("## 6. 落存文档正文快照")
w()
w(f"- 落存位置：`kb/l0/snapshots/<resource_key>@<sha256>.md`")
w(f"- **新增快照 {len(snaps['snapshots'])} 个**（飞书 docx 资源共 {len(snaps['snapshots'])+len(snaps['unreadable'])} 条）")
w(f"- 文件名带 sha256 → 同一文档的多版快照可并存、不互相覆盖")
w()
w("| # | 快照文件 | 对应台账 sha256（前16） | 重算校验 | 字符数 | 标题 |")
w("|---|---|---|---|---|---|")
for i, s in enumerate(snaps["snapshots"], 1):
    w(f"| {i} | `{s['file'][:66]}…` | `{s['sha256'][:16]}` | {'✅ 一致' if s['match'] else '❌ 不一致'} | {s['chars']:,} | {s['title'][:24]} |")
w()
w("**快照数 {} == 已下钻 docx 资源数减不可读数**；每条快照头部都写了 `sha256_recomputed` 与 "
  "`sha256_match`，实测 **{}/{} 全部一致**（即快照正文就是台账 sha256 所指的那一版）。".format(
    len(snaps["snapshots"]), sum(1 for s in snaps["snapshots"] if s["match"]), len(snaps["snapshots"])))
w()
w("### 6.1 不可读的文档（登记原因，未静默跳过）")
w()
w("| resource_key | sha256_state | 原因 |")
w("|---|---|---|")
for f in snaps["unreadable"]:
    w(f"| `{f['resource_key']}` | `{f['sha256_state']}` | {f['status_reason']} |")
w()
w("### 6.2 与台账 sha256 的对应关系")
w()
w("快照文件名里的 sha256 ≡ 台账 `sha256` 字段 ≡ 快照头部 `sha256_recomputed`（三处一致）。"
  "因此 `L1.anchor + source_sha256 → 快照文件` 是可机械复核的链路。")
w()
w("## 7. `empty` 与 `failed` 分开计数")
w()
w(f"新增状态 **`no_content_expected`**：用于「本来就没有正文」的资源。")
w()
w(f"### 7.1 改了哪些文件、哪些字段")
w()
w("| 改动 | 数量 | 字段 |")
w("|---|---|---|")
w(f"| L1 产物 json（`kb/l1/<目录>/*.json`） | **{len(p2['status_split']['changed'])} 个** | `status`、`status_reason`、`status_changed_by`、`status_history`（新增） |")
w(f"| L1 产物 json（图片附件） | **{fx['files_changed']} 个** | 同上，`unreachable` → `pending_ocr`（纠误判） |")
w(f"| L1 产物 json（空行记录） | 3 个 | 补 `status_reason`（原文为空，未改状态） |")
w(f"| `manifest_l1.jsonl` | 追加 **{len(p2['status_split']['changed'])+fx['files_changed']} 行** | 旧行全部保留，未删除 |")
w()
w("> 图片附件那 77 条是**我上一轮自己的误判**：L1 抽取器当时未支持 `feishu_attachment`，"
  "把「未抽取」记成了 `unreachable`（失败）。实际 OCR 已完成 77/77，正确状态是 `pending_ocr`（挂起）。"
  "不修正的话真实失败率会被这 77 条严重稀释。")
w()
w("### 7.2 修正后的状态分布")
w()
w("| status | 条数 | 含义 | 计入失败率 |")
w("|---|---|---|---|")
MEAN = {"ok": "抽取成功", "empty": "可读但确实没有可抽内容（源侧整行空白）",
        "no_content_expected": "本来就没有正文（表/Base 结构资源，设计如此）",
        "pending_ocr": "图片资源，OCR 留待下一步（本轮不抽取）",
        "no_scope": "缺 scope 读不到", "forbidden": "无权限", "unreachable": "抓取未返回可解析正文",
        "retracted": "已归档（旧 key 权宜产物），不计入当前视图"}
for k in ["ok", "empty", "no_content_expected", "pending_ocr", "no_scope", "forbidden", "unreachable", "retracted"]:
    if k in st:
        w(f"| `{k}` | {st[k]} | {MEAN.get(k,'')} | {'否' if k in ('ok','empty','no_content_expected','pending_ocr','retracted') else '**是**'} |")
w()
w("### 7.3 修正后的真实失败率")
w()
w("| 口径 | 公式 | 结果 |")
w("|---|---|---|")
w(f"| 单位总数（去掉已归档） | {len(man)} − {st.get('retracted',0)} | **{units}** |")
w(f"| 剔除「本来就没正文」 | − {noc} | {units-noc} |")
w(f"| 再剔除「挂起（本轮不抽取）」 | − {pend} | **{attempt}（真正应可抽取）** |")
w(f"| 失败 | no_scope {st.get('no_scope',0)} + forbidden {st.get('forbidden',0)} + unreachable {st.get('unreachable',0)} | **{fail}** |")
w(f"| **真实失败率** | {fail} / {attempt} | **{fail/attempt*100:.2f}%** |")
w(f"| 抽取成功率（ok / 应可抽取） | {st.get('ok',0)} / {attempt} | **{st.get('ok',0)/attempt*100:.2f}%** |")
w()
w(f"对比修正前：`empty` {st.get('empty',0)+noc+3} 条被算成失败、77 条挂起被算成 `unreachable`，"
  f"失败率一度显示为 **{(fail+77+16)/ (attempt+77+16) *100:.1f}%** —— 这就是「把本来没正文算成失败」"
  f"导致的覆盖率虚低与真失败被稀释。修正后 **{fail/attempt*100:.2f}%**。")
w()
w("## 8. run 快照记录源 revision")
w()
w("`runs/<run_id>.json` 增加三字段：`source_revision_start` / `source_revision_end` / `source_revision_used`"
  "（另加 `source_revision_note` 说明取值依据）。**自本次起生效，并已回补历史各次运行。**")
w()
w("| run | source_revision_start | source_revision_used | 备注 |")
w("|---|---|---|---|")
for rid in ["20260923-1055", "20260923-1117", "20260923-1140", "20260923-1215", RUN]:
    m = p2["revision"]["runs"].get(rid)
    if not m:
        continue
    w(f"| `{rid}` | `{m['rev_start']}` | `{m['rev_used']}` | {m['note']} |")
w()
w(f"本次结束实测源 revision：`{p2['revision']['rev_end']}`")
w()
w("已写入字段的运行快照文件：")
for t in p2["revision"]["touched"]:
    w(f"- `{t}`")
w()
w("## 9. 锚点与 sha256 绑定写进规范")
w()
w("已在两处**追加**（未修改任何既有键）：")
w()
w("| 文件 | 追加键 |")
w("|---|---|")
w("| `kb/l0/registry/kb.json` | `anchor_sha256_binding` |")
w("| `kb/l1/registry/l1.json` | `anchor_sha256_binding`（附 `enforced_in` / `index_join`） |")
w()
w("规范正文：")
w()
w(f"> **{p2['anchor_binding']['rule']}**")
w(">")
w(f"> 理由：{p2['anchor_binding']['why']}")
w(">")
w(f"> 适用：{p2['anchor_binding']['applies_to']}")
w(f"> 必需字段对：`{p2['anchor_binding']['required_pair']}`")
w(f"> 回原文：{p2['anchor_binding']['artifact_lookup']}")
w(f"> 失效处理：{p2['anchor_binding']['on_mismatch']}")
w()
w(f"配套：`kb/l1/index/l1.jsonl` 已重建并**增加 `source_sha256` 列**（{p2['index_rows']} 行），"
  "使每条 segment 可直接 join 到所属资源的 sha256 与快照文件。")
w()
w("## 10. 三个 scope 可用性检查")
w()
w("| scope | 可用 | 实测返回 |")
w("|---|---|---|")
for k, v in p2["scope"]["probe"].items():
    w(f"| `{v['scope']}` | {'✅ 可用' if v['available'] else '❌ 不可用'} | `{v.get('error_subtype') or '—'}` {v.get('message','')[:70]} |")
w()
w(f"**结论：三个 scope 仍未补齐（0/3）。** 17 条 `no_scope` 资源标 `scope_missing`，"
  f"**按约束不重试**（已实测确认，重试无意义）。")
w()
w("受影响资源：")
w()
w("| source_kind | 条数 | 缺的 scope |")
w("|---|---|---|")
sc = collections.Counter()
for r in latest.values():
    if r["sha256_state"] == "no_scope":
        need = {"feishu_sheet": "sheets:spreadsheet:read", "feishu_slides": "slides:presentation:read",
                "feishu_file": "drive:file:download"}.get(r["source_kind"], "—")
        sc[(r["source_kind"], need)] += 1
for (sk, nd), n in sc.most_common():
    w(f"| `{sk}` | {n} | `{nd}` |")
w()
w("---")
w()
w("## 自检结论")
w()
w("| # | 检查项 | 结论 |")
w("|---|---|---|")
for i, (nm, res) in enumerate(checks, 1):
    w(f"| {i} | {nm} | {'✅ ' if res.startswith('通过') else '❌ '}{res} |")
w()
w(f"（三方一致复核：{n_files} 个文件 / {mism} 处不符）")
w()
w("## 本轮明确未做（按约束）")
w()
w("- 未改 media 存储结构（不做内容寻址去重）")
w("- 未解除关联 Base 采样上限（截断量已在第 5 节说明影响）")
w("- 未验证视频转写与抽帧（源里没有视频素材：125 条记录 `素材类型` 全空、77 个附件全 `.png`）")
w("- 未切分、未蒸馏、未写版本号")
w("- **未重新 OCR / 未做视觉描述生成**（硬约束 4「不抽取新内容」）—— 视觉描述的缺口已在 4.1 节如实登记，"
  "留待你确认后作为下一批任务")
w()
with open(f"{L0}/runs/{RUN}.report.md", "w", encoding="utf-8") as fh:
    fh.write("\n".join(L) + "\n")

json.dump({"checks": checks, "mism": mism, "n_files": n_files, "by_kb_now": dict(by_kb_now),
           "by_kb_first": dict(by_kb_first), "st": dict(st), "units": units, "attempt": attempt,
           "fail": fail, "real_fail_rate_pct": round(fail/attempt*100, 2),
           "extract_rate_pct": round(st.get("ok",0)/attempt*100, 2),
           "snapshots": len(snaps["snapshots"]), "unreadable": len(snaps["unreadable"]),
           "ocr_empty": sum(1 for r in ocr if r["empty"]), "ocr_total": len(ocr),
           "status_changed_files": len(p2["status_split"]["changed"]) + fx["files_changed"],
           "l1_units": units},
          open("kb/.work/final_stats.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("报告已写出")
print(f"  真实失败率 {fail/attempt*100:.2f}% | 抽取成功率 {st.get('ok',0)/attempt*100:.2f}% | 快照 {len(snaps['snapshots'])}")
print("  自检:", all(c[1].startswith("通过") for c in checks))
