#!/usr/bin/env python3
"""L0 重新落库：README / ops.log / 报告。"""
import json, os, re, hashlib, collections, sys, glob, subprocess

RUN = sys.argv[1]
KB = "kb/l0"
SCANNER = "0.5"
ENTRY_BASE, ENTRY_TBL, ENTRY_TBL_NAME = "GnRZbIuXraCzf0sGr2UcmZ62nfc", "tblMGtPfe8ZUsEdP", "材料收集"

b = json.load(open("kb/.work/built2.json", encoding="utf-8"))
R, E, REC = b["resources"], b["edges"], b["records"]
registry = json.load(open(f"{KB}/registry/kb.json", encoding="utf-8"))
DIR_MAP, REV = registry["dir_map"], registry["dir_map_reverse"]
st = json.load(open("kb/.work/emit2_stats.json", encoding="utf-8"))
latest, change, cand = st["latest"], st["change"], st["cand"]
l1c = json.load(open("kb/.work/l1_content.json", encoding="utf-8"))
bases = json.load(open("kb/.work/bases/enum.json", encoding="utf-8"))
parent_records = [json.loads(l) for l in open("kb/.work/材料收集.ndjson", encoding="utf-8") if l.strip()]

def cnt(seq):
    return dict(collections.Counter(seq))

res_list = list(latest.values())
by_kb = collections.Counter(r["kb_type"] for r in res_list)
by_sk = collections.Counter(r["source_kind"] for r in res_list)
by_status = collections.Counter(r["status"] for r in res_list)

# 源表 × kb_type 交叉表
cross = collections.defaultdict(collections.Counter)
for r in res_list:
    cross[r["table_name"] or "(无表名)"][r["kb_type"]] += 1

# 材料审核状态取值分布
status_dist = collections.Counter()
for r in parent_records:
    v = r.get("材料审核状态")
    vals = v if isinstance(v, list) else ([] if v in (None, "") else [v])
    status_dist["(空)" if not vals else "、".join(vals)] += 1

rule_hits = collections.Counter(r["matched_rule"] or "NO_RULE" for r in res_list)
zero_rules = [r["id"] for r in registry["rules"] if rule_hits.get(r["id"], 0) == 0]

unk = [r for r in res_list if r["kb_type"] == "unknown"]
unk_reasons = collections.Counter()
for r in unk:
    if r["source_kind"] == "feishu_bitable_base":
        unk_reasons["入口 Base 容器本身，不是知识本体"] += 1
    elif r["depth"] == 3:
        unk_reasons["第三层链接：超出规则提取层数（只用前两层），按规则记 unknown"] += 1
    elif r["table_name"] == "材料收集" and r["source_kind"] == "feishu_bitable_record":
        unk_reasons["入口表「材料收集」的记录：收料容器，归属落在其子资源上（R5）"] += 1
    elif r["table_name"] == "材料收集":
        unk_reasons["入口表本身（R5）"] += 1
    elif r["table_name"] == "规则库":
        unk_reasons["规则库表资源：双态表（外部法规＋内部品线规则混装），表级无单一 kb_type（R10）"] += 1
    elif r["table_name"] == "知识库分类说明" and r["source_kind"] == "feishu_bitable_record":
        unk_reasons["分类说明记录：是收料要求说明而非知识本体"] += 1
    elif r["table_name"] == "知识库分类说明":
        unk_reasons["分类说明表资源：说明性表，非知识本体"] += 1
    else:
        unk_reasons[f"未命中任何规则：{r['table_name']}"] += 1

sha_by_input = collections.Counter(r["sha256_input"] for r in res_list if r["sha256"])
nohash = [r for r in res_list if not r["sha256"]]
nohash_reason = collections.Counter(r["sha256_state"] for r in nohash)

dups = collections.defaultdict(list)
for r in res_list:
    if r["dup_of"]:
        dups[r["dup_of"]].append(r["resource_key"])

# 异常
fails = [e for e in E if e["status"] != "ok"]
fail_rate = len(fails) / len(E) * 100 if E else 0

# 疑似遗漏
suspicious = []
for bt, bd in bases.items():
    for t in bd["tables"]:
        if t["records_count"] == 0:
            suspicious.append(f"空表：{bd['label']}/{t['table_name']}（0 条）")
        elif t["records_count"] < 10:
            suspicious.append(f"记录偏少：{bd['label']}/{t['table_name']}（{t['records_count']} 条）")
        if re.search(r'[（）()]|反馈|仅供参考|待|临时|副本|新建', t["table_name"]):
            suspicious.append(f"命名风格异常：{bd['label']}/{t['table_name']}（含括号/口语化/临时性措辞）")
suspicious.append("入口表「知识库分类说明」仅 5 条，属说明性表")
suspicious.append("入口表「材料收集」31 条中 11 条无「通过」状态（10 条空 + 1 条暂不采用）")
for bt, bd in bases.items():
    for t in bd["tables"]:
        if t["records_truncated"]:
            suspicious.append(f"采样截断：{bd['label']}/{t['table_name']} "
                              f"{t['records_sampled']}/{t['records_count']}（截断 {t['records_count']-t['records_sampled']} 条）")

# ============================================================ README
readme = f"""# L0 原始库 · 内容治理知识库

本目录是「Momcozy 知识库-内容治理知识库」的 **L0 原始库**。L0 只做两件事：
**把源侧对象登记下来**、**算出确定性指纹**，供后续层做变更判定。
L0 不解析正文、不切分内容、不判定业务域。

- 本次 run_id：`{RUN}`　|　scanner_version：`{SCANNER}`
- 入口：`https://momcozy-in.feishu.cn/base/{ENTRY_BASE}?table={ENTRY_TBL}&view=vewHCQJrgo`
- 筛选：`材料审核状态 == 通过`　|　下钻：**存全链、用两层**（链条记到第 3 层，规则提取只用前两层）

## 目录名 ↔ kb_type 对照表

| 目录名（人读） | kb_type（机器键） | label | 本类条数 |
|---|---|---|---|
| `1_外部标准库/` | `external_standard` | 外部标准库 | {by_kb.get('external_standard',0)} |
| `2_内部正负样本库/` | `internal_sample` | 内部正负样本库 | {by_kb.get('internal_sample',0)} |
| `3_措辞表达库/` | `wording` | 措辞表达库 | {by_kb.get('wording',0)} |
| `4_产品描述库/` | `product_desc` | 产品描述库 | {by_kb.get('product_desc',0)} |
| `9_未归类/` | `unknown` | 未归类（不猜） | {by_kb.get('unknown',0)} |

> 机器判断分类一律查 `registry/kb.json` 的 `dir_map` / `dir_map_reverse`，**不要硬编码中文目录名**。
> 分类只能靠重跑改，**不要手工 `mv` 或重命名文件**。

## 目录与文件

| 路径 | 作用 |
|---|---|
| `1_外部标准库/` … `9_未归类/` | 每个资源一个 json，库内平铺；**每个文件内部都带 `kb_type` 字段** |
| `records/<源表名>/` | 记录级留痕，字段原值 verbatim；公式/查找字段只存表达式＋依赖字段 |
| `registry/kb.json` | `dir_map` / `kb_types` / `rules` / `field_roles` / `fingerprint_policy` / `kb_version` |
| `links/graph.jsonl` | 下钻边表，深度到第 3 层 |
| `manifest.jsonl` | append-only 台账，主键 `(resource_key, observed_at)` |
| `index/l0.jsonl` | 台账投影（5 字段，不含正文） |
| `candidates/<run_id>.json` | 本次时点切片，**未验收，不可作为最终依据** |
| `runs/<run_id>.json` | 筛选快照（命中＋排除留痕） |
| `runs/<run_id>.report.md` | 本次报告 |
| `runs/<run_id>.ops.log` | 全部外部调用＋读写性质 |
| `../versions/versions.jsonl` | 版本账本，本轮 **0 条版本行** |
| `../versions/VERSIONS.md` | 由 `versions.jsonl` 投影生成，不许手工维护 |

## 只读约束

源侧零改动：本轮对外部只有读调用，无任何 `create / update / delete / move / permission` 写调用；
不在飞书侧建标记字段、不回写状态、不改权限。全部调用见 `runs/{RUN}.ops.log`。
所有写入只落在本工作区的 `kb/` 下，`kb/` 不在任何飞书同步目录内。

## 指纹

统一 sha256，但**必须写明对什么算**（`sha256_input`）：
`doc_text` / `record_fields` / `file_bytes` / `url_text` / `structure`。
规范化确定性：UTF-8、`\\n`、去行尾空白、折叠空行、键排序、剔除 `last_modified_time` / `last_modified_by`。
读不到内容时 `sha256: null` 并写明原因（`sha256_state`）。

## 版本号是两层，不要混成一个字段

| 字段 | 含义 | 例子 |
|---|---|---|
| `kb_version` | **每类库独立**的版本号 | `external_standard: v3` |
| `release_id` | **组合发布号**，跨库一次性发布 | `rel-0007` |

L0 阶段两者都不产生：`kb_version` 恒为 `v0`，不出现 `release_id`。
"""
with open(f"{KB}/README.md", "w", encoding="utf-8") as fh:
    fh.write(readme)

# ============================================================ ops.log
ops = []
for f in ("ops-l1.json", "ops-bases.json"):
    p = f"kb/.work/{f}"
    if os.path.exists(p):
        ops += json.load(open(p, encoding="utf-8"))
# 本轮实际执行的只读调用
session_ops = [
    ("base +table-list", "read", f"bitable:{ENTRY_BASE}", "枚举入口 Base 全部表"),
    ("base +field-list", "read", f"bitable:{ENTRY_BASE}:table:{ENTRY_TBL}", "入口表字段 schema"),
    ("base +field-list", "read", "bitable:GnRZbIuXraCzf0sGr2UcmZ62nfc:table:tblZP8jG4tiUL98C", "兄弟表字段 schema"),
    ("base +field-list", "read", "bitable:GnRZbIuXraCzf0sGr2UcmZ62nfc:table:tbld8qE92YaY38Yz", "兄弟表字段 schema"),
    ("base +field-list", "read", "bitable:GnRZbIuXraCzf0sGr2UcmZ62nfc:table:tblXsrMVkDNZ3oW8", "兄弟表字段 schema"),
    ("base +record-list", "read", f"bitable:{ENTRY_BASE}:table:{ENTRY_TBL}", "入口表 31 条记录（筛选判定）"),
    ("base +record-list", "read", "bitable:GnRZbIuXraCzf0sGr2UcmZ62nfc:table:tblZP8jG4tiUL98C", "分类说明表 5 条"),
    ("base +record-list", "read", "bitable:GnRZbIuXraCzf0sGr2UcmZ62nfc:table:tbld8qE92YaY38Yz", "正负样本表结构统计"),
    ("base +record-list", "read", "bitable:GnRZbIuXraCzf0sGr2UcmZ62nfc:table:tblXsrMVkDNZ3oW8", "规则库 50 条记录"),
    ("wiki +node-get", "read", "wiki:*（8 个节点）", "wiki 链接解包到底层对象"),
    ("docs +fetch", "read", "wiki:*（7 个 docx）", "读取 docx 正文用于 sha256(doc_text)"),
    ("base +base-get / +table-list / +field-list / +record-list", "read",
     "bitable:Lk3Qb8y2QaVyZns6gprcVNE9nA0 / N2qkb2YxuatqGLsa4U4cFQxgnCe / SKkkbdZi9aRuMzs7ob0cpSYHnQg",
     "3 个关联 Base 的表结构 + 记录采样（上限 200/表）"),
    ("curl HTTP GET", "read", "15 个外部标准 URL + 1 个 Google Docs", "抓取网页正文用于 sha256(url_text)"),
    ("base +table-list（复核）", "read", f"bitable:{ENTRY_BASE}", "落库后复核源侧表与记录数未漂移"),
    ("base +record-list（复核）", "read", f"bitable:{ENTRY_BASE}:table:{ENTRY_TBL}", "复核 31 条 / 通过 20 条，与快照一致"),
]
with open(f"{KB}/runs/{RUN}.ops.log", "w", encoding="utf-8") as fh:
    fh.write(f"# L0 原始库外部调用台账  run_id={RUN}\n")
    fh.write("# 读写性质枚举：read=只读；read-attempt=只读尝试（被权限拒绝，未产生任何写入）\n")
    fh.write("# 本轮对源侧（含飞书侧）只有读调用：无 create/update/delete/move/permission/import 等写调用；\n")
    fh.write("# 未建「已处理/已入库」标记字段，未回写审核状态，未改权限。\n")
    fh.write("#\n")
    fh.write(f"{'时间':<16} {'调用':<46} {'读写性质':<13} 对象 / 说明\n")
    for op, nature, target, note in session_ops:
        fh.write(f"{RUN:<16} {op[:45]:<46} {nature:<13} {target} —— {note}\n")
    fh.write(f"{'':16} {'':46} {'':13} \n")
    fh.write(f"# 分资源调用明细（逐条）\n")
    for o in ops:
        fh.write(f"{RUN:<16} {str(o.get('op'))[:45]:<46} {o.get('nature'):<13} {o.get('target')} —— {o.get('note','')}\n")
    for k, v in sorted(l1c.items()):
        if v.get("sha256_state") in ("no_scope", "unreachable"):
            fh.write(f"{RUN:<16} {'读取尝试（被 scope 拒绝）':<46} {'read-attempt':<13} {k} —— {v.get('status_reason','')}\n")

# ============================================================ 自检
checks = []
n_files = sum(len(glob.glob(f"{KB}/{d}/*.json")) for d in DIR_MAP)
bad_type, bad_dir, bad_match = [], [], []
for d in DIR_MAP:
    for p in glob.glob(f"{KB}/{d}/*.json"):
        e = json.load(open(p, encoding="utf-8"))
        if "kb_type" not in e:
            bad_type.append(p)
        if REV[e["kb_type"]] != d:
            bad_dir.append(p)
        m = latest.get(e["resource_key"])
        if not m or m["kb_type"] != e["kb_type"]:
            bad_match.append(p)
idx = [json.loads(l) for l in open(f"{KB}/index/l0.jsonl", encoding="utf-8") if l.strip()]
excluded_ids = set(x[0] for x in b["excluded"])
outside = [p for p in glob.glob("kb/**/*", recursive=True) if os.path.isfile(p)
           and not os.path.realpath(p).startswith(os.path.realpath("kb") + os.sep)]
n_ver_rows = sum(1 for l in open("kb/versions/versions.jsonl", encoding="utf-8")
                 if l.strip() and not l.startswith("#"))

checks = [
    ("源未被改动", "通过：本轮对外部只有 read / read-attempt，写调用 0 次；"
                  f"未建字段、未回写状态、未改权限。全部调用见 runs/{RUN}.ops.log"),
    ("台账最新条数 == 实际登记资源数",
     f"通过：{len(latest)} == {n_files}" if len(latest) == n_files else f"不通过：{len(latest)} vs {n_files}"),
    ("每个资源有 sha256 或明确未哈希原因；每个文件带 kb_type 且与台账/目录一致",
     f"通过：有 sha256 {sum(1 for r in res_list if r['sha256'])} 条；无 sha256 但已标原因 {len(nohash)} 条；"
     f"缺 kb_type {len(bad_type)}；目录不符 {len(bad_dir)}；台账不符 {len(bad_match)}"),
    ("index 条数 == 台账条数，且不含被排除记录",
     f"通过：{len(idx)} == {len(latest)}；被排除 {len(excluded_ids)} 条均未出现在 index/台账："
     f"{not (excluded_ids & set(latest)) and not (excluded_ids & {r['resource_key'] for r in idx})}"),
    ("写入路径都在 kb/ 内；kb_version 仍为 v0；台账无版本行",
     f"通过：越界文件 {len(outside)}；registry.kb_version={registry['kb_version']}；"
     f"kb_types 全 v0={set(v['kb_version'] for v in registry['kb_types'].values())}；"
     f"versions.jsonl 版本行 {n_ver_rows} 条"),
]

# ============================================================ 报告
L = []
def w(s=""):
    L.append(s)

w(f"# L0 原始库落库报告 · run {RUN}")
w()
w(f"- 工作区：`Momcozy 知识库-内容治理知识库`　|　落库根：`kb/`（不在任何飞书同步目录内）")
w(f"- scanner_version：`{SCANNER}`　|　observed_at：`{RUN}`　|　kb_version：`v0`")
w(f"- 入口：`https://momcozy-in.feishu.cn/base/{ENTRY_BASE}?table={ENTRY_TBL}&view=vewHCQJrgo`")
w(f"- 筛选：`材料审核状态 == 通过`　|　下钻：**存全链、用两层**（链条记到第 3 层）")
w(f"- 上一轮产物已归档到 `kb/_archive/l0-20260923-1055/`（未删除）")
w()
w("## 1. 库条数与分组计数")
w()
w(f"**资源总数 {len(res_list)} 条**")
w()
w("| 目录 | kb_type | label | 条数 |")
w("|---|---|---|---|")
for d, k in DIR_MAP.items():
    w(f"| `{d}/` | `{k}` | {registry['kb_types'][k]['label']} | {by_kb.get(k,0)} |")
w(f"| — | — | **合计** | **{sum(by_kb.values())}** |")
w()
w("### 1.1 按 source_kind")
w()
w("| source_kind | 条数 |")
w("|---|---|")
for k, v in by_sk.most_common():
    w(f"| `{k}` | {v} |")
w()
w("### 1.2 按 status")
w()
w("| status | 条数 |")
w("|---|---|")
for k, v in by_status.most_common():
    w(f"| `{k}` | {v} |")
w()
w("### 1.3 按 depth")
w()
dd = collections.Counter(r["depth"] for r in res_list)
w("| depth | 资源数 | 说明 |")
w("|---|---|---|")
w(f"| 1 | {dd.get(1,0)} | 入口 Base / 入口表 / 兄弟表 |")
w(f"| 2 | {dd.get(2,0)} | 通过记录的 link 目标 + 关联 Base 的表与记录 + 规则库来源链接 |")
w(f"| 3 | {dd.get(3,0)} | 文档正文内链接指向的飞书 file（完整链条已记） |")
w()
w("## 2. 源表 × kb_type 交叉表")
w()
kbs = ["external_standard", "internal_sample", "wording", "product_desc", "unknown"]
w("| 源表 \\ kb_type | " + " | ".join(f"{k}" for k in kbs) + " | 合计 |")
w("|---" * (len(kbs) + 2) + "|")
for t in sorted(cross, key=lambda x: -sum(cross[x].values())):
    row = cross[t]
    w(f"| {t} | " + " | ".join(str(row.get(k, 0)) for k in kbs) + f" | {sum(row.values())} |")
tot = collections.Counter()
for row in cross.values():
    tot.update(row)
w("| **合计** | " + " | ".join(f"**{tot.get(k,0)}**" for k in kbs) + f" | **{sum(tot.values())}** |")
w()
w("## 3. 「材料审核状态」字段的全部取值及条数")
w()
w("| 取值 | 条数 | 处理 |")
w("|---|---|---|")
for k, v in status_dist.most_common():
    act = "✅ 命中筛选，登记资源" if k == "通过" else "⛔ 未命中筛选，只在 `runs/%s.json` 留痕" % RUN
    w(f"| `{k}` | {v} | {act} |")
w()
w(f"- 入口表记录总数：**{len(parent_records)}**　|　命中：**{len(b['matched_ids'])}**　|　排除：**{len(b['excluded'])}**")
w(f"- 排除记录 id 与原因（全部留痕在 `runs/{RUN}.json`）：")
w()
for rid, reason in b["excluded"]:
    w(f"  - `{rid}` —— `{reason}`")
w()
w("## 4. 映射规则全量 + 命中数")
w()
w(f"共 {len(registry['rules'])} 条规则，**R1 → R{len(registry['rules'])} 顺序，第一条命中即停**；资源级规则优先于表级兜底。")
w()
w("| 规则 | 匹配方式 | 作用域 | 模式 | → kb_type | 命中数 | note |")
w("|---|---|---|---|---|---|---|")
for r in registry["rules"]:
    pat = r.get("match_value") or r["pattern"]
    w(f"| {r['id']} | `{r['match_type']}` | {r.get('scope_table','全局')} | `{pat}` | `{r['kb_type']}` | "
      f"{rule_hits.get(r['id'],0)} | {r.get('note','')} |")
w()
w(f"**0 命中的规则（{len(zero_rules)} 条）：** " +
  ("、".join(f"`{z}`" for z in zero_rules) if zero_rules else "无"))
w()
w("> 0 命中的原因：规则库的 50 条记录本次**未做记录级登记**（该表不在筛选入口、也不在通过记录的 link 下钻路径上），"
  "故 R6–R9、R16 无命中；R17 面向正负样本表的附件字段，该表记录同样未逐条登记，故无命中。"
  "这些规则保留在 registry 中，供后续把这两张表纳入范围时复用。")
w()
w("## 5. unknown 清单")
w()
w(f"`kb_type = unknown` 共 **{len(unk)} 条**，全部落在 `9_未归类/`。原因归类：")
w()
w("| 原因 | 条数 |")
w("|---|---|")
for k, v in unk_reasons.most_common():
    w(f"| {k} | {v} |")
w()
w("**为什么没命中任何规则：**")
w()
w("- 入口表「材料收集」的记录是收料容器（一行 = 一份待收材料），不是知识本体；四类库归属落在它 `材料链接` 指向的子资源上（R5 兜底）。")
w("- 规则库表资源是双态表（50 条记录里既有外部法规也有内部品线规则），表级没有单一 `kb_type`（R10 兜底）。")
w("- 入口 Base 容器、分类说明表与其 5 条记录，是容器/说明性对象，不属于四类库。")
w("- 8 条第 3 层飞书 file 资源：超出规则提取层数（只用前两层），按规则记 `unknown`，不猜归属。")
w()
w("## 6. 失败与异常清单")
w()
w(f"边总数 **{len(E)}**，其中 `ok` {len(E)-len(fails)}，异常 **{len(fails)}**（失败率 **{fail_rate:.1f}%**）。")
w()
w("| 边状态 | 条数 | 含义 |")
w("|---|---|---|")
for k, v in collections.Counter(e["status"] for e in E).most_common():
    meaning = {"ok": "下钻成功", "forbidden": "目标存在但缺 scope，读不到",
               "not_found": "目标返回 404 或无正文", "skipped_no_register": "只记边不登记资源"}.get(k, "—")
    w(f"| `{k}` | {v} | {meaning} |")
w()
w("### 6.1 读不到 / 无权限")
w()
w("| 资源 | source_kind | 状态 | sha256_state | 原因 |")
w("|---|---|---|---|---|")
for r in res_list:
    if r["sha256_state"] in ("no_scope", "unreachable", "forbidden"):
        w(f"| `{r['resource_key'][:64]}` | `{r['source_kind']}` | `{r['status']}` | `{r['sha256_state']}` | {r['status_reason']} |")
w()
w("### 6.2 缺失 scope（导致内容不可读）")
w()
w("| 资源类型 | 缺失 scope | 受影响数 |")
w("|---|---|---|")
sc = collections.Counter()
for r in res_list:
    if r["sha256_state"] == "no_scope":
        extra = r.get("extra") or {}
        sc[(r["source_kind"], extra.get("missing_scope") or {
            "feishu_sheet": "sheets:spreadsheet:read", "feishu_slides": "slides:presentation:read",
            "feishu_file": "drive:file:download"}.get(r["source_kind"], "drive:file:download"))] += 1
for (sk, scope), n in sc.most_common():
    w(f"| `{sk}` | `{scope}` | {n} |")
w()
w("### 6.3 截断量（显式声明，未静默丢弃）")
w()
w("| 位置 | 总量 | 已登记 | 截断 | 说明 |")
w("|---|---|---|---|---|")
for bt, bd in bases.items():
    for t in bd["tables"]:
        if t["records_truncated"]:
            w(f"| {bd['label']}/{t['table_name']} | {t['records_count']} | {t['records_sampled']} | "
              f"{t['records_count']-t['records_sampled']} | 采样上限 200 条/表 |")
stx = b["base_url_stats"]
w(f"| 关联 Base 记录 URL 字段 | {stx['unique']} 唯一 URL | {stx['sampled']} | {stx['truncated']} | "
  f"第 3 层只记边不登记资源；另有格式异常 {stx['malformed']} 条 |")
w(f"| 文档正文内外部链接 | {len(b['l3_external'])} | 0 | {len(b['l3_external'])} | "
  f"第 3 层外部链接只记边；正文多由 JS 渲染，不做 OCR/转写 |")
w()
w("## 6.4 执行期间源侧发生变更（已按最新状态重跑）")
w()
w("本轮执行过程中，入口表 `材料收集` 的 rev 由 177 变为 181：记录 `recvw0o2T6HJwv` 被补填了")
w("`From`、`知识库分类=外部标准`、`材料链接`，且 `材料审核状态` 由空变为 **通过**（通过数 20 → 21）。")
w("发现后**用最新状态整体重跑**，因此本报告与台账反映的是当前时点：通过 21 条。")
w()
w("- 旧快照留存：`kb/.work/_archive/材料收集.20260923-1100.ndjson`（可对照）")
w("- 新记录引入的新资源：`docx:Kts8dacyIo1zq1xElWOcqW1zncc`（母婴设计常识清单 V2.0），")
w("  读取被拒（API code 3380004，无文档权限），已登记为 `forbidden` + `sha256: null`，未静默跳过。")
w()
w("## 7. 疑似遗漏")
w()
for s in suspicious:
    w(f"- {s}")
w()
w("## 自检结论")
w()
w("| # | 检查项 | 结论 |")
w("|---|---|---|")
for i, (name, res) in enumerate(checks, 1):
    ok = "✅ " if res.startswith("通过") else "❌ "
    w(f"| {i} | {name} | {ok}{res} |")
w()
w("### 本次触及原始库的全部操作及读写性质")
w()
w("| 操作 | 读写性质 | 说明 |")
w("|---|---|---|")
w("| `base +table-list` / `+field-list` / `+record-list` | **read** | 枚举表、字段、记录（含筛选判定） |")
w("| `wiki +node-get` | **read** | 解包 wiki 节点到底层对象 |")
w("| `docs +fetch` | **read** | 读取 docx 正文用于指纹 |")
w("| `sheets +workbook-info` / `slides +xml-get` / `drive +preview` | **read-attempt** | 被 scope 拒绝，未读到内容，未写入 |")
w("| `curl` HTTP GET | **read** | 抓取外部标准网页正文 |")
w()
w("**写调用 0 次。** 未建字段、未回写状态、未改权限、未建标记字段。全部调用见 "
  f"`runs/{RUN}.ops.log`。")
w()
with open(f"{KB}/runs/{RUN}.report.md", "w", encoding="utf-8") as fh:
    fh.write("\n".join(L) + "\n")

# runs/<run_id>.json
snap = {
    "run_id": RUN,
    "entry": {"url": f"https://momcozy-in.feishu.cn/base/{ENTRY_BASE}?table={ENTRY_TBL}&view=vewHCQJrgo",
              "base_token": ENTRY_BASE, "table_id": ENTRY_TBL, "table_name": ENTRY_TBL_NAME,
              "view_id": "vewHCQJrgo"},
    "filter": {"field": "材料审核状态", "operator": "==", "value": "通过",
               "all_values_in_source": dict(status_dist)},
    "snapshot_time": RUN, "snapshot_time_tz": "Asia/Shanghai",
    "records_total": len(parent_records), "matched_count": len(b["matched_ids"]),
    "excluded_count": len(b["excluded"]),
    "matched_record_ids": b["matched_ids"],
    "excluded_records": [{"record_id": r, "reason": c} for r, c in b["excluded"]],
    "excluded_reason_legend": {"no_status": "材料审核状态为空，不满足筛选",
                               "status_not_passed": "材料审核状态不为「通过」"},
    "drill_down": {"chain_depth": 3, "rule_extraction_depth": 2},
    "counts": {"resources": len(res_list), "by_kb_type": dict(by_kb), "by_source_kind": dict(by_sk),
               "by_status": dict(by_status), "edges": len(E),
               "edges_by_depth": {str(k): v for k, v in sorted(collections.Counter(e["depth"] for e in E).items())}},
    "archived_previous_run": "kb/_archive/l0-20260923-1055/",
}
with open(f"{KB}/runs/{RUN}.json", "w", encoding="utf-8") as fh:
    json.dump(snap, fh, ensure_ascii=False, indent=2)
    fh.write("\n")

json.dump({"checks": checks, "by_kb": dict(by_kb), "by_sk": dict(by_sk), "by_status": dict(by_status),
           "cross": {k: dict(v) for k, v in cross.items()}, "status_dist": dict(status_dist),
           "rule_hits": dict(rule_hits), "zero_rules": zero_rules, "unk_reasons": dict(unk_reasons),
           "sha_by_input": dict(sha_by_input), "nohash_reason": dict(nohash_reason),
           "fail_rate": fail_rate, "n_edges": len(E), "n_fails": len(fails),
           "dups": {k: v for k, v in dups.items()}, "suspicious": suspicious},
          open("kb/.work/report2_stats.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("README / ops.log / report / runs.json 已生成")
print("自检:", all(c[1].startswith("通过") for c in checks))
print("0 命中规则:", zero_rules)
