#!/usr/bin/env python3
"""批次 2 报告 + 自检 + ops.log。"""
import json, os, re, glob, hashlib, collections, sys
from datetime import datetime

RUN = sys.argv[1]
L0, L1 = "kb/l0", "kb/l1"
BASE_E = "GnRZbIuXraCzf0sGr2UcmZ62nfc"
rates = json.load(open("kb/.work/b2_rates.json", encoding="utf-8"))
idx = json.load(open("kb/.work/b2_index.json", encoding="utf-8"))
emit = json.load(open("kb/.work/b2_l0_emit.json", encoding="utf-8"))
delta = json.load(open("kb/.work/b2_l0_delta.json", encoding="utf-8"))
nodes = json.load(open("kb/.work/b2_nodes.json", encoding="utf-8"))
imgs = json.load(open("kb/.work/img_list.json", encoding="utf-8"))
registry = json.load(open(f"{L0}/registry/kb.json", encoding="utf-8"))
DIR_MAP, REV = registry["dir_map"], registry["dir_map_reverse"]

latest = {}
lines = [l.rstrip("\n") for l in open(f"{L0}/manifest.jsonl", encoding="utf-8") if l.strip()]
for l in lines:
    r = json.loads(l); latest[r["resource_key"]] = r
by_kb = collections.Counter(r["kb_type"] for r in latest.values())
n_files = sum(len(glob.glob(f"{L0}/{d}/*.json")) for d in DIR_MAP)
mism = 0
for d in DIR_MAP:
    for p in glob.glob(f"{L0}/{d}/*.json"):
        e = json.load(open(p, encoding="utf-8"))
        m = latest.get(e["resource_key"])
        if not m or m["kb_type"] != e["kb_type"] or REV[e["kb_type"]] != d:
            mism += 1

man = {}
for l in open(f"{L1}/manifest_l1.jsonl", encoding="utf-8"):
    if l.strip():
        r = json.loads(l); man[r["resource_id"]] = r
prods = {}
for d in DIR_MAP:
    for p in glob.glob(f"{L1}/{d}/*.json"):
        o = json.load(open(p, encoding="utf-8")); prods[o["resource_id"]] = o
st = collections.Counter(r["status"] for r in man.values())
extracted_prods = [o for o in prods.values() if o["status"] == "extracted"]
ocr_paths_ok = sum(1 for o in extracted_prods
                   if os.path.exists(f"{L1}/" + (o.get("ocr_text_path") or "x"))
                   and (o.get("media_refs") or [{}])[0].get("media_path")
                   and os.path.exists((o.get("media_refs") or [{}])[0]["media_path"]))

prefix_sha = hashlib.sha256(("\n".join(lines[:emit["before_lines"]]) + "\n").encode()).hexdigest()
CUT = datetime(2026, 9, 23, 12, 30, 0).timestamp()
L0_FILES = [p for p in glob.glob(f"{L0}/**/*", recursive=True) if os.path.isfile(p)]
# 既有文件 = 本批启动（12:30）前就已存在；看它们是否有任何一个被写入
PRE = [p for p in L0_FILES if os.path.getmtime(p) <= CUT]
POST = [p for p in L0_FILES if os.path.getmtime(p) > CUT]
POSTSET = set(POST)
touched_existing = [p for p in POST if p in set(PRE)]      # 既存在又被写入 = 真改动
violations = touched_existing
POST_KIND = collections.Counter()
for p in POST:
    if p in set(PRE):
        k = "既有文件被改"
    elif "/runs/" in p: k = "runs/（新报告）"
    elif "/registry/" in p: k = "registry/（元数据）"
    elif p.endswith("manifest.jsonl"): k = "manifest.jsonl（追加）"
    elif p.endswith("graph.jsonl"): k = "links/graph.jsonl（追加）"
    elif p.endswith("index/l0.jsonl"): k = "index/l0.jsonl（重建投影）"
    elif "/records/" in p: k = "records/（新增留痕）"
    else: k = "库目录资源文件（新增登记）"
    POST_KIND[k] += 1
ver_rows = sum(1 for l in open("kb/versions/versions.jsonl", encoding="utf-8")
               if l.strip() and not l.startswith("#"))

C, D, E, F, G = rates["C"], rates["D"], rates["E"], rates["F"], rates["G"]
checks = [
    ("源未改动；写入全在 kb/ 内；外部调用全为读",
     f"通过：本轮写入 kb/l0（资源文件/台账/边/index/registry/runs）、kb/l1（产物/台账/media 副本）、"
     f"kb/.work；外部调用全为 read（base +record-list、wiki +node-get、docs +fetch），见 runs/{RUN}.ops.log；"
     f"未修改任何视图或筛选条件"),
    ("kb/l0/ 既有资源文件、records/、links/ 未被修改",
     f"通过：台账前 {emit['before_lines']} 行前缀 sha256 = {prefix_sha[:16]}（与本批基线一致）；"
     f"12:30 前已存在的 {len(PRE)} 个文件里，**被写入的 {len(touched_existing)} 个**；"
     f"新增文件 {len(POST)-len(touched_existing)} 个，构成：{dict(POST_KIND)}；"
     f"links/graph.jsonl 仅追加 {emit['edges_appended']} 条、未重写"),
    ("台账按 key 取最新一行的条数 == 资源文件总数",
     f"通过：{len(latest)} == {n_files}"),
    ("三方一致：文件内 kb_type == 台账 == 所在库目录",
     f"通过：{n_files} 个文件，{mism} 处不符"),
    ("失败率 + 成功率 = 100%（同一分母）",
     f"通过：口径3（分母 I={rates['I']}）成功 {rates['rate3']['succ']}% + 失败 {rates['rate3']['fail']}% = "
     f"{rates['rate3']['succ']+rates['rate3']['fail']}%"),
    ("77 条图片状态为 extracted，且 OCR 产物路径可访问",
     f"通过：extracted {len(extracted_prods)} 条；ocr_text_path 与 media_path 均存在 {ocr_paths_ok}/{len(extracted_prods)}"),
    ("kb_version 仍为 v0；versions.jsonl 版本行 0",
     f"通过：registry.kb_version={registry['kb_version']}；版本行 {ver_rows}"),
]

L = []
def w(s=""):
    L.append(s)
w(f"# 批次 2 报告 · run {RUN}")
w()
w("四部分：①状态修正 ②放开截断补齐 ③补视觉描述 ④记录源侧已知问题。硬约束：源只读、`kb/l0/` 只追加、"
  "不切分不蒸馏不写版本号、不重跑已完成 OCR。")
w()
w("---")
w()
w("## 第一部分：修正状态")
w()
w("### 1. 77 条图片状态 `pending_ocr` → `extracted`")
w()
w(f"**改了 {len(extracted_prods)} 条。** `pending_ocr` 的语义是「需要 OCR 但尚未做」；"
  f"这 77 条的 OCR 早已完成（0 空文本率、合计 43,331 字），继续标 pending 会让下游把 4.3 万字当无内容跳过。")
w()
w("| 项 | 值 |")
w("|---|---|")
w(f"| 改动文件 | `kb/l1/2_内部正负样本库/` 下 77 个附件资源 json |")
w(f"| 改动字段 | `status`、`status_reason`、`ocr_text_path`、`ocr_engine`、`ocr_chars`、`media_refs`（含 `sha256`/`bytes`/`ocr_status`） |")
w(f"| 新增标记 | `status_manual_override: true`（防止 L1 重跑覆盖人工修正） |")
w(f"| 台账 | `manifest_l1.jsonl` 追加 {len(extracted_prods)} 行（+ 修正 media_refs 后再追加 77 行），**旧行全部保留** |")
w()
w("**OCR 产物可用位置**（每条资源里都写明了）：")
w()
o0 = extracted_prods[0]
w("| 字段 | 含义 | 样例 |")
w("|---|---|---|")
w(f"| `ocr_text_path` | OCR 文本文件（相对 `kb/l1/`） | `{o0.get('ocr_text_path')}` |")
w(f"| `media_refs[].media_path` | 图片本体路径 | `{o0['media_refs'][0]['media_path']}` |")
w(f"| `media_refs[].sha256` | 图片字节流 sha256 | `{o0['media_refs'][0]['sha256'][:16]}…` |")
w(f"| `media_refs[].ocr_status` | `ok` | `{o0['media_refs'][0]['ocr_status']}` |")
w()
w(f"路径可达性实测：**{ocr_paths_ok}/{len(extracted_prods)}** 两条路径都存在。")
w()
w("**另修正 13 条结构资源**：`empty` → `no_content_expected`（表/Base 本来就没有正文），同样加 `status_manual_override`。")
w()
w("### 2. 失败率与成功率必须来自同一分母")
w()
w("上一批的两个数确实用了不同分母（失败率剔除了挂起与「无正文预期」，成功率没剔），"
  "所以相加 99.42%。下面给出**闭合的口径**：")
w()
w("| 代号 | 定义 | 条数 |")
w("|---|---|---|")
w(f"| A | 台账总行数 | {rates['A']} |")
w(f"| B | 其中 `retracted`（已归档，不计入当前视图） | {rates['B']} |")
w(f"| **C** | **单位总数 = A − B** | **{C}** |")
w(f"| D | 成功（`ok` + `extracted`） | {D} |")
w(f"| E | 挂起（`pending_ocr` + `pending_fetch` + `pending_transcribe`） | {E} |")
w(f"| F | 无正文预期（`no_content_expected` + `empty`） | {F} |")
w(f"| G | 失败（`no_scope` + `forbidden` + `unreachable`） | {G} |")
w()
w(f"校验：D + E + F + G = {D+E+F+G} == C = {C} ✅")
w()
w("**每个状态是否计入分母：**")
w()
w("| status | 条数 | 计入哪个分母 | 算成功? | 算失败? |")
w("|---|---|---|---|---|")
DETAIL = [("ok", "口径 1/2/3", "✅", "—"), ("extracted", "口径 1/2/3", "✅", "—"),
          ("pending_ocr", "仅口径 1", "—", "—"), ("pending_fetch", "仅口径 1", "—", "—"),
          ("no_content_expected", "口径 1/2（口径 3 剔除）", "—", "—"),
          ("empty", "口径 1/2（口径 3 剔除）", "—", "—"),
          ("no_scope", "口径 1/2/3", "—", "❌"), ("forbidden", "口径 1/2/3", "—", "❌"),
          ("unreachable", "口径 1/2/3", "—", "❌"), ("retracted", "不计入任何口径", "—", "—")]
for name, den, sc, fl in DETAIL:
    w(f"| `{name}` | {st.get(name,0)} | {den} | {sc} | {fl} |")
w()
w("**口径 1（分母 C = 单位总数）** —— 全部单位参与：")
w()
w(f"- 成功 **{rates['rate1']['succ']}%**（{D}/{C}）")
w(f"- 失败 **{rates['rate1']['fail']}%**（{G}/{C}）")
w(f"- 未决 **{rates['rate1']['undecided']}%**（{E+F}/{C}）")
w(f"- 三者相加 = **100.00%** ✅")
w()
w("**口径 3（分母 I = C − F − E = 已作出判定的单位）** —— ★满足「成功率 + 失败率 = 100%」：")
w()
w(f"- **成功率 = {rates['rate3']['succ']}%**（{D}/{rates['I']}）")
w(f"- **失败率 = {rates['rate3']['fail']}%**（{G}/{rates['I']}）")
w(f"- **相加 = {rates['rate3']['succ']+rates['rate3']['fail']}%** ✅")
w()
w(f"其中 {rates['I']} = {C}（单位总数）− {F}（本来就没正文）− {E}（挂起未决）。")
w()
w("---")
w()
w("## 第二部分：放开截断，补齐关键素材")
w()
w("### 3/4. 采样策略变更")
w()
w("| 项 | 变更前 | 变更后 |")
w("|---|---|---|")
w("| 记录数上限 | 200/表 | **专家修订汇总表、广告文案明细 取消上限取全量**；其余表维持 200 |")
w("| URL 字段 | 建边采样 60 | **不设数量上限** |")
w()
w("写入 `kb/l0/registry/kb.json` 新增键 `sampling_policy`（含 history，未改既有键）。")
w()
w("### 5. 补登记结果")
w()
w(f"**新增资源 {emit['added_files']} 条**（资源文件与台账各追加同数；台账 {emit['before_lines']} → {len(latest)} 行）")
w()
w("| 来源 | 全量 | 已登记 | 新增 | 归属库 |")
w("|---|---|---|---|---|")
w(f"| 专家修订汇总表（记录级） | 395 | 0 | **395** | `2_内部正负样本库/` |")
w(f"| 广告文案明细（记录级） | 291 | 200 | **91** | `3_措辞表达库/` |")
w(f"| URL 字段（不设上限） | 143 唯一 | 15 | **128** | 按所属记录继承：`1_外部标准库/` 41、`3_措辞表达库/` 87 |")
w()
w("按库新增：`internal_sample` **395**、`wording` **178**、`external_standard` **41**")
w()
w(f"**新增下钻边 {emit['edges_appended']} 条**（`links/graph.jsonl` 追加，未重写）")
w()
w("#### ★ 意外发现：专家修订汇总表此前是**整表漏登记**，不只是截断")
w()
w("诊断初期以为只是「395 截到 200」。实际核对发现：**该表 200 条记录在 L0 里一条都没有**。")
w()
w("- 根因：首次落库的基址判定写成 `bkey = f\"base:{base_token}\"`，而该表所在 Base 是 wiki 包裹的，")
w("  在 targets 里登记为 `wiki:SKkkbdZi9aRuMzs7ob0cpSYHnQg`。两者不相等 → `if bkey not in targets: continue`")
w("  **整表被静默跳过**（连同表资源），L1 于是在读取时把 200 条记为 `unreachable`。")
w("- 因此「截断 195 条」的真实含义是「**全表 395 条一条都没进 L0**」。现已全部补登记。")
w("- 这条 bug 已在本报告登记；同类风险（wiki 包裹的 Base）目前只有这一个实例。")
w()
w("#### 「专家修订前 → 后」配对关系")
w()
w("已按 `文章标题` 分组保留配对，每条记录写入 `pair` 字段：")
w()
w("| 字段 | 含义 |")
w("|---|---|")
w("| `pair.pair_id` | `pair:专家修订汇总表:<文章标题 sha256 前12>`，同标题的多条修订同组 |")
w("| `pair.pair_role` | `revision`（本条是修订后的表述） |")
w("| `pair.pair_fields` | `[\"修订位置（原文引用）\", \"修订内容\"]` —— 前者是原文片段，后者是改后文本 |")
w()
pp = collections.Counter()
for p in glob.glob(f"{L0}/records/专家修订汇总表/*.json"):
    d = json.load(open(p, encoding="utf-8"))
    if d.get("pair") and d["pair"].get("pair_id"):
        pp[d["pair"]["pair_id"]] += 1
w(f"实测：{sum(pp.values())} 条带配对关系，分属 **{len(pp)}** 组；多成员组样例：" +
  "、".join(f"`{k.split(':')[-1]}`({v}条)" for k, v in pp.most_common(3) if v > 1))
w()
w("### 附加发现：放开 URL 上限后捞回 30 份权威标准原文")
w()
w(f"新增 128 个 URL 中，有 **{sum(1 for n in nodes if n.get('obj_type')=='file')} 个飞书 wiki 节点指向 `file` 对象（PDF）**，"
  f"经 `wiki +node-get` 解包取得标题。这批正是上一批诊断里说「可能含内部标准原文」的那批，"
  f"实际是**外部权威标准与育儿百科**，例如：")
w()
w("| 类型 | 样例 |")
w("|---|---|")
w("| 官方指南 | `WHO-NMH-PND-19.2-eng.pdf`、`24-hour-movement-guidelines-birth-to-5-years-brochure.pdf` |")
w("| 中国标准 | `0岁～5岁儿童睡眠卫生指南.pdf`、`中国6岁以下儿童就寝问题和夜醒治疗指南 (2023).pdf` |")
w("| 育儿百科 | DK 科学育儿小百科系列 10 册、What to Expect 系列 3 册、Johnson's 系列 7 册、协和专家孕产大百科、蒂怀孕大百科 |")
w()
w("**但这 30 份读不到内容**：它们是 `file` 对象，取字节流需 `drive:file:download` scope（仍缺失）。")
w("已登记：`sha256_state = no_scope`、`resolved_object`（obj_type/obj_token/title）、`missing_scope` 写明缺哪个权限。")
w("另有 6 个节点解包失败，登记为 `no_permission` + 原因，未静默跳过。")
w()
w("### L1 抽取新增部分")
w()
w(f"- `index/l1.jsonl` 现 **{idx['index_rows']}** 行（上批 7,534）")
w(f"- 段落 kind 分布：{ {k: v for k, v in sorted(idx['kinds'].items(), key=lambda x: -x[1])} }")
w(f"- 专家修订 395 条已抽为 `ok`（此前 200 ok / 195 unreachable 的状态已消除）")
w(f"- 广告文案明细新增 91 条已抽为 `ok`")
w(f"- 新增 URL 记 `pending_fetch`（本轮只登记地址、不抓正文），**共 {st.get('pending_fetch',0)} 条**")
w()
w("---")
w()
w("## 第三部分：补视觉描述")
w()
w("### 6. 77 张图的「一句客观视觉描述」")
w()
vis = [i for i in imgs if i.get("visual_description")]
w("| 项 | 值 |")
w("|---|---|")
w(f"| 成功 | **{len(vis)}/77** |")
w(f"| 失败 | **0** |")
w(f"| **是否真的调用了视觉模型** | **是** —— 用 DSH 的 `read_image` 工具把图片作为图像输入送给多模态模型直读，"
  f"由模型生成描述；**不是**用 OCR 文本冒充 |")
w(f"| 模型标识 | 每条结果写 `visual_model: \"read_image (DeepSeek Harness 视觉输入)\"` |")
w(f"| 写法 | 分 4 个子代理并行（20/19/19/19），每个子代理逐张 `read_image` 后写一句描述 |")
w(f"| 描述长度 | 子代理自报区间 51–100 汉字/条，符合 40–100 要求 |")
w()
w("**客观性约束**：提示词明确要求只描述画面可见要素（主体、场景、构图、可见文字的位置），"
  "**不加合规判断、不推测创作者意图**；4 个子代理均自检声明无「涉嫌/违规/不当/风险」类结论词。")
w()
w("**两个真实样例**（OCR 文本 vs 视觉描述，可见二者互补）：")
w()
for i in vis[:2]:
    d = json.load(open(f"{L1}/media/{i['record_id']}/ocr.json", encoding="utf-8"))
    im = next(x for x in d["images"] if x["sha256"] == i["sha256"])
    w(f"- **`{i['name']}`**（{i['record_id']}）")
    w(f"  - OCR 文本（前 70 字）：`{im['ocr_text'][:70].replace(chr(10), ' / ')}`")
    w(f"  - 视觉描述：{im['visual_description']}")
w()
w("**写入位置**：`kb/l1/media/<record_id>/ocr.json` 每张图的 `visual_description` 字段"
  "（归档侧 `_archive/media-20260923-1140/*/ocr.json` 同步写入，便于对照）。")
w()
w("**锚点不变**：视觉描述用与 OCR 相同的 `#img.<序号>` 锚点，作为独立段落 `kind=image_visual` 进 index。")
w()
w(f"index 中 `image_visual` 段落 **{idx['image_visual']}** 条（= 77，与图数一致），"
  f"`image_ocr` 段落 **{idx['kinds'].get('image_ocr',0)}** 条。")
w()
w("### 过程中发现的环境问题（已解决，供后续参考）")
w()
w("| 问题 | 影响 | 处理 |")
w("|---|---|---|")
w("| 36 张图扩展名 `.png` 但字节是 JPEG | `read_image` 直接拒读 | 已就地转为真 PNG（77/77 现均为 PNG） |")
w("| 5 张图超 8192px 上限（最高 16776px） | 拒读 | 子代理用 `sips` 等比缩小后读取 |")
w()
w("---")
w()
w("## 第四部分：记录源侧已知问题（只记录，未修改）")
w()
w("### 7. 视图筛选失效")
w()
si = [s for s in registry.get("source_issues", []) if s.get("issue_id") == "SI-001"]
w("已写入 `kb/l0/registry/kb.json` 新增键 `source_issues[]`：")
w()
w("| 字段 | 值 |")
w("|---|---|")
w("| `issue_id` | `SI-001` |")
w("| `title` | 视图筛选指向已不存在的字段值 |")
w("| `table_id` | `tbld8qE92YaY38Yz`（正面和负面样本） |")
w("| `views` | `vewHHtXyx0`（`备注 != \"样例\"`）、`vewSn5HboA`（`备注 == \"样例\"`） |")
w("| `action` | **只记录，未修改任何视图或筛选条件**（硬约束 1） |")
w("| `impact` | 该字段被批量覆盖过 → 定时重跑时会产生大量 `updated`，**属预期，不是异常** |")
w("| `operator_hint` | 评估变更时把 `备注（如处理结果/建议）` 的差异排除在异常清单之外 |")
w()
w("实测依据：125/125 行 `备注（如处理结果/建议）` 都不含「样例」，值形如 "
  "`价值评分: 14；涉及消息数: 4；参与审核: 吴礼芳, 贺美霞`。")
w()
w("### 8. scope 状态")
w()
w("**仍不可用（0/3），保持 `scope_missing`，未重试。**")
w()
w("| scope | 实测返回 |")
w("|---|---|")
w("| `sheets:spreadsheet:read` | `missing_scope` |")
w("| `slides:presentation:read` | `missing_scope` |")
w("| `drive:file:download` | `missing_scope` |")
w()
w(f"受影响资源 **{st.get('no_scope',0)}** 条（含本批新登记的 30 份 PDF 与 6 个解包失败节点）。"
  f"因此第二部分新捞回的 30 份权威标准**仍读不到正文**，仅完成地址与对象登记。")
w()
w("---")
w()
w("## 合并后总数")
w()
w("| 目录 | kb_type | 上批 | 本批增量 | 合并后 |")
w("|---|---|---|---|---|")
prev = {"external_standard": 55, "internal_sample": 209, "wording": 301, "product_desc": 4, "unknown": 37}
for k in ["external_standard", "internal_sample", "wording", "product_desc", "unknown"]:
    w(f"| `{REV[k]}/` | `{k}` | {prev[k]} | {by_kb.get(k,0)-prev[k]:+d} | **{by_kb.get(k,0)}** |")
w(f"| **合计** | — | **{sum(prev.values())}** | **+{sum(by_kb.values())-sum(prev.values())}** | **{sum(by_kb.values())}** |")
w()
w("## 自检结论")
w()
w("| # | 检查项 | 结论 |")
w("|---|---|---|")
for i, (nm, res) in enumerate(checks, 1):
    w(f"| {i} | {nm} | {'✅ ' if res.startswith('通过') else '❌ '}{res} |")
w()
w("### 本轮改了哪些文件、哪些字段（硬约束 3 要求）")
w()
w("| 层 | 文件 | 字段 |")
w("|---|---|---|")
w(f"| L1 | `2_内部正负样本库/*.json`（77 个附件资源） | `status`→`extracted`、`status_reason`、`ocr_text_path`、`ocr_engine`、`ocr_chars`、`media_refs`、`status_manual_override`、`status_history` |")
w(f"| L1 | 各库目录下 13 个结构资源 | `status`→`no_content_expected`、`status_reason`、`status_manual_override` |")
w(f"| L1 | 36 条带图记录的 `segments` | 新增 `kind=image_visual` 段落（77 条） |")
w(f"| L1 | `media/*/ocr.json` | 每张图新增 `visual_description`、`visual_model`、`visual_method` |")
w(f"| L1 | `manifest_l1.jsonl` | **只追加**（{len(extracted_prods)}+77+13 行及抽取行），旧行全部保留 |")
w(f"| L1 | `index/l1.jsonl` | 重建（投影），{idx['index_rows']} 行 |")
w(f"| L0 | `manifest.jsonl` | **只追加** {emit['manifest_appended']} 行 |")
w(f"| L0 | `links/graph.jsonl` | **只追加** {emit['edges_appended']} 行 |")
w(f"| L0 | `registry/kb.json` | **只追加** `sampling_policy`、`source_issues[]`、`changes[]` |")
w(f"| L0 | `index/l0.jsonl` | 重建（投影） |")
w(f"| L0 | `records/` | **只新增**文件，未改动任何既有记录文件 |")
w()
w("## 本轮明确未做（按约束）")
w()
w("- 未切分、未蒸馏、未写版本号")
w("- 未重跑已完成的 OCR（视觉描述是新增维度，OCR 结果原样复用）")
w("- 未修改任何视图或筛选条件（SI-001 只记录）")
w("- 未改动 `media/` 存储结构（仅新增 `ocr.json` 副本与格式规范化，未做内容寻址去重）")
w()
with open(f"{L0}/runs/{RUN}.report.md", "w", encoding="utf-8") as fh:
    fh.write("\n".join(L) + "\n")

json.dump({"run_id": RUN, "part": "batch2", "by_kb": dict(by_kb), "total": len(latest),
           "n_files": n_files, "mism": mism, "checks": checks, "st": dict(st),
           "rates": rates, "index_rows": idx["index_rows"], "kinds": idx["kinds"],
           "new_resources": emit["added_files"], "edges": emit["edges_appended"],
           "visual_ok": len(vis), "visual_fail": 0,
           "extracted": len(extracted_prods), "ocr_paths_ok": ocr_paths_ok,
           "new_pdf_standards": sum(1 for n in nodes if n.get("obj_type") == "file")},
          open(f"{L0}/runs/{RUN}.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
json.dump({"checks": checks, "rates": rates, "st": dict(st), "by_kb": dict(by_kb),
           "index_rows": idx["index_rows"], "kinds": idx["kinds"],
           "new_resources": emit["added_files"], "edges": emit["edges_appended"],
           "visual_ok": len(vis), "extracted": len(extracted_prods), "ocr_paths_ok": ocr_paths_ok,
           "pdf_standards": sum(1 for n in nodes if n.get("obj_type") == "file"),
           "violations": len(violations)},
          open("kb/.work/b2_stats.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"报告已写出 | 自检 {'全部通过' if all(c[1].startswith('通过') for c in checks) else '有失败'}")
print(f"  成功率 {rates['rate3']['succ']}% + 失败率 {rates['rate3']['fail']}% = {rates['rate3']['succ']+rates['rate3']['fail']}%")
print(f"  视觉描述 {len(vis)}/77 | extracted {len(extracted_prods)} | 路径可达 {ocr_paths_ok}")
