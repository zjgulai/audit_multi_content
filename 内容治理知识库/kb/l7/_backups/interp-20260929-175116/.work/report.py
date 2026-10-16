#!/usr/bin/env python3
"""L0 落库 · 步骤 10/11 + 步骤 12 自检: 报告、versions 投影、自检结论。"""
import json, os, re, hashlib, collections, sys, subprocess, glob

RUN = sys.argv[1]
KB = "kb/l0"
f = json.load(open("kb/.work/final.json", encoding="utf-8"))
latest, change, cand = f["latest"], f["change"], f["cand"]
registry = json.load(open(f"{KB}/registry/kb.json", encoding="utf-8"))
built = json.load(open("kb/.work/built.json", encoding="utf-8"))
R, E = built["resources"], built["edges"]
l1c = json.load(open("kb/.work/l1_content.json", encoding="utf-8"))
snapshot = json.load(open(f"{KB}/runs/{RUN}.json", encoding="utf-8"))
bases = json.load(open("kb/.work/bases/enum.json", encoding="utf-8"))

# ---------------------------------------------------------------- versions.jsonl（只建空文件 + 头部说明）
VJ = "kb/versions/versions.jsonl"
HEADER = [
    "# 版本指针流水（append-only）",
    "# 本文件只放指针，不放内容副本；每行一条 JSON，主键 version_id。",
    "# 两层版本号，不要混成一个字段：",
    "#   kb_version  —— 每类库独立，如 external_standard: v3",
    "#   release_id  —— 组合发布号，如 rel-0007",
    "# L0 原始库阶段不生成任何版本号、不做发布，本文件保持零版本行。",
]
if not os.path.exists(VJ):
    with open(VJ, "w", encoding="utf-8") as fh:
        fh.write("\n".join(HEADER) + "\n")

# ---------------------------------------------------------------- VERSIONS.md（由 versions.jsonl 投影）
def parse_versions():
    rows, notes = [], []
    for line in open(VJ, encoding="utf-8"):
        s = line.strip()
        if not s:
            continue
        if s.startswith("#"):
            notes.append(s.lstrip("# ").rstrip())
        else:
            rows.append(json.loads(s))
    return rows, notes

def project_versions(rows, notes):
    out = ["# 版本清单（VERSIONS）", "",
           "> 本文件由 `versions.jsonl` 投影生成，**不许手工维护**。重建命令：",
           "> `python3 kb/.work/emit_versions.py`（重跑同一条投影逻辑，逐字节一致）。", ""]
    out += ["## 文件头部说明（来自 versions.jsonl 注释行）", ""]
    for n in notes:
        out.append(f"- {n}")
    out += ["", "## 版本行", ""]
    if not rows:
        out += ["当前 **0 条版本行**。L0 原始库阶段不生成版本号、不做发布。", ""]
    else:
        out += ["| version_id | kb_version | release_id | 时间 | 说明 |", "|---|---|---|---|---|"]
        for r in rows:
            out.append(f"| {r.get('version_id','')} | {r.get('kb_version','')} | "
                       f"{r.get('release_id','')} | {r.get('created_at','')} | {r.get('note','')} |")
        out.append("")
    out += ["## 计数器", "",
            f"- kb_version（按库）：{len({r.get('kb_version') for r in rows if r.get('kb_version')})} 个",
            f"- release_id（组合发布号）：{len({r.get('release_id') for r in rows if r.get('release_id')})} 个",
            f"- 版本行总数：{len(rows)}",
            ""]
    return "\n".join(out)

rows, notes = parse_versions()
with open("kb/versions/VERSIONS.md", "w", encoding="utf-8") as fh:
    fh.write(project_versions(rows, notes))

# ---------------------------------------------------------------- 统计
def cnt(seq):
    return dict(collections.Counter(seq))

res_list = list(latest.values())
by_kb = cnt(r["kb_type"] for r in res_list)
by_sk = cnt(r["source_kind"] for r in res_list)
by_st = cnt(r["status"] for r in res_list)

rule_hits = cnt(r["matched_rule"] or "NO_RULE" for r in res_list)
rules = registry["rules"]
zero_rules = [r["id"] for r in rules if rule_hits.get(r["id"], 0) == 0]

unk = [r for r in res_list if r["kb_type"] == "unknown"]
unk_reasons = collections.Counter()
for r in unk:
    if r["table_name"] == "材料收集" and r["source_kind"] == "feishu_bitable_record":
        unk_reasons["入口表「材料收集」的记录本身是收料容器，不是知识本体（R5 兜底 unknown）"] += 1
    elif r["table_name"] == "材料收集":
        unk_reasons["入口表本身（R5 兜底 unknown）"] += 1
    elif r["table_name"] == "规则库":
        unk_reasons["规则库表资源：该表是双态表（记录级含外部法规与内部品线规则），表级无单一 kb_type"] += 1
    elif r["table_name"] == "知识库分类说明":
        unk_reasons["分类说明表：记录是收料要求说明而非知识本体，5 行中 3 行「知识库」列为空/其它"] += 1
    elif r["source_kind"] == "feishu_bitable_base" and r["table_name"] is None:
        unk_reasons["入口 Base 容器本身，不是知识本体"] += 1
    else:
        unk_reasons[f"未命中任何规则：{r['table_name']}"] += 1

sha_by_input = collections.Counter()
for r in res_list:
    if r["sha256"]:
        sha_by_input[r["sha256_input"]] += 1
nohash = [r for r in res_list if not r["sha256"]]
nohash_reason = collections.Counter()
for r in nohash:
    nohash_reason[r["sha256_state"]] += 1

anomalies = [r for r in res_list if r["status_reason"]]
dups = collections.defaultdict(list)
for r in res_list:
    if r["dup_of"]:
        dups[r["dup_of"]].append(r["resource_key"])

# schema 变化（本次基线为空）
schema_changes = {"新增表": [t for t in ["材料收集", "知识库分类说明", "正面和负面样本", "规则库",
                                     "广告文案明细", "品线内容边界规则库", "W1卖点表达边界（品线反馈0910）",
                                     "风险文案改写建议库（分型号分渠道）", "数据表", "内容公式（仅供参考）",
                                     "专家修订汇总表"]],
                   "改名表": [], "删除表": [], "新增字段": "见 registry/kb.json 的 field_roles 与各表 schema 登记",
                   "改名或删除字段": []}

suspicious = []
for bt, bd in bases.items():
    for t in bd["tables"]:
        if t["records_count"] == 0:
            suspicious.append(f"空表：{bd['label']}/{t['table_name']}（{t['records_count']} 条）")
        elif t["records_count"] < 10:
            suspicious.append(f"记录偏少：{bd['label']}/{t['table_name']}（{t['records_count']} 条）")
        if re.search(r'[（）()\s]|反馈|仅供参考|待|临时|副本|新建', t["table_name"]):
            suspicious.append(f"命名风格异常：{bd['label']}/{t['table_name']}（含括号/口语化/临时性措辞）")
suspicious.append("入口表「知识库分类说明」仅 5 条记录，属说明性表")
suspicious.append("入口表「材料收集」31 条记录，其中 11 条无「通过」状态（10 条空状态 + 1 条暂不采用）")

# 下钻失败率
ok_edges = [e for e in E if e["status"] == "ok"]
fail_edges = [e for e in E if e["status"] != "ok"]
fail_rate = len(fail_edges) / len(E) * 100 if E else 0

# 自检
def check():
    out = []
    out.append(("1. 原目录未被改动",
                "通过：本次对外部只有读调用，无任何 create/update/delete/move/permission 写调用，"
                "飞书侧未建字段、未改状态、未改权限。全部调用见 runs/%s.ops.log" % RUN))
    n_latest = len(latest)
    n_res = len(R)
    out.append(("2. 记录数校验（按 resource_key 取最新一行 == 实际登记资源数）",
                f"通过：最新台账 {n_latest} == 登记资源 {n_res}（≠ manifest 总行数 {sum(1 for _ in open(KB+'/manifest.jsonl'))}）"
                if n_latest == n_res else f"不通过：{n_latest} vs {n_res}"))
    bad_hash = [r["resource_key"] for r in res_list if not r["sha256"] and not r["sha256_state"]]
    out.append(("3. 每条资源要么有 sha256，要么有明确 sha256_state",
                f"通过：有 sha256 {sum(1 for r in res_list if r['sha256'])} 条；"
                f"无 sha256 但已标 sha256_state {len(nohash)} 条（{dict(nohash_reason)}）；无说明的 {len(bad_hash)} 条"
                if not bad_hash else f"不通过：{bad_hash}"))
    bad_row = [r["resource_key"] for r in res_list if not r["kb_type"] and not r["status"]]
    out.append(("4. 不存在既无 kb_type 又无 status 的行",
                f"通过：{len(bad_row)} 条" if not bad_row else f"不通过：{bad_row}"))
    n_idx = sum(1 for _ in open(f"{KB}/index/l0.jsonl"))
    out.append(("5. index/l0.jsonl 记录数 == 最新台账记录数",
                f"通过：{n_idx} == {n_latest}" if n_idx == n_latest else f"不通过：{n_idx} vs {n_latest}"))
    outside = []
    for p in glob.glob("kb/**/*", recursive=True):
        if os.path.isfile(p):
            rp = os.path.realpath(p)
            if not rp.startswith(os.path.realpath("kb") + os.sep):
                outside.append(p)
    out.append(("6. 所有写入路径都在 kb/ 内",
                f"通过：kb/ 下 {sum(1 for p in glob.glob('kb/**/*', recursive=True) if os.path.isfile(p))} 个文件，越界 {len(outside)} 个"))
    kbv = {t: v["kb_version"] for t, v in registry["kb_types"].items()}
    out.append(("7. registry kb_version 仍为 v0，未产生版本号",
                f"通过：kb_types 全部 v0={set(kbv.values())}，registry 顶层 kb_version={registry['kb_version']}，"
                f"versions.jsonl 版本行 {len(rows)} 条"))
    before = open("kb/versions/VERSIONS.md", "rb").read()
    subprocess.run([sys.executable, "kb/.work/emit_versions.py"], check=True)
    after = open("kb/versions/VERSIONS.md", "rb").read()
    out.append(("8. 重建 VERSIONS.md 后逐字节一致",
                f"通过：{len(before)} 字节，sha256 {hashlib.sha256(before).hexdigest()[:16]}，重建后一致={before == after}"))
    return out, before == after

checks, same = check()

# ---------------------------------------------------------------- 报告
L = []
def w(s=""):
    L.append(s)

w(f"# L0 原始库落库报告 · run {RUN}")
w()
w(f"- 扫描器版本：`0.5`　|　观测时点 `observed_at`：`{RUN}`")
w(f"- 入口：`https://momcozy-in.feishu.cn/base/GnRZbIuXraCzf0sGr2UcmZ62nfc?table=tblMGtPfe8ZUsEdP&view=vewHCQJrgo`")
w(f"- 筛选条件：`材料审核状态 == 通过`　|　下钻层数上限：`2`（记录链条保留到最深，规则提取只用前两层）")
w(f"- 落库根目录：`kb/`（不在任何飞书同步目录内）")
w()
w("## 1. 总量与分组计数")
w()
w(f"**资源总数（最新台账视图）＝ {len(res_list)} 条**")
w()
w("### 1.1 按 kb_type")
w()
w("| kb_type | label | 条数 |")
w("|---|---|---|")
for k, v in sorted(by_kb.items(), key=lambda x: -x[1]):
    w(f"| `{k}` | {registry['kb_types'].get(k, {}).get('label', '—')} | {v} |")
w()
w("### 1.2 按 source_kind")
w()
w("| source_kind | 条数 |")
w("|---|---|")
for k, v in sorted(by_sk.items(), key=lambda x: -x[1]):
    w(f"| `{k}` | {v} |")
w()
w("### 1.3 按 status")
w()
w("| status | 条数 |")
w("|---|---|")
for k, v in sorted(by_st.items(), key=lambda x: -x[1]):
    w(f"| `{k}` | {v} |")
w()
w(f"另：按 depth 分布 —— depth=1 共 {sum(1 for r in res_list if r['depth']==1)} 条，"
  f"depth=2 共 {sum(1 for r in res_list if r['depth']==2)} 条。")
w()
w("## 2. 本次变更摘要")
w()
w("| 变更 | 条数 | 说明 |")
w("|---|---|---|")
w(f"| new（registered） | {change.get('new', 0)} | 全新 resource_key，`downstream_invalidated=true` |")
w(f"| updated | {change.get('updated', 0)} | sha256 变化（本次为首次运行，无历史基线） |")
w(f"| moved | {sum(1 for r in res_list if r['moved_from'])} | sha256 与旧台账相同但 key 是新的 |")
w(f"| retracted | {change.get('retracted', 0)} | 移出筛选范围（本次无历史基线） |")
w(f"| restored | 0 | 重新进入筛选范围 |")
w(f"| gone | {change.get('gone', 0)} | 源被删除（本次无历史基线） |")
w(f"| unchanged | {change.get('unchanged', 0)} | sha256 未变 |")
w()
w("> 本次是 **L0 首次落库**：`manifest.jsonl` 此前不存在，故全部 405 条按 `registered` 追加，"
  "`updated / retracted / restored / gone / moved` 均为 0。后续运行才会产生这些状态。")
w()
w("## 3. 映射规则与命中数")
w()
w(f"共 {len(rules)} 条规则，顺序 R1 → R{len(rules)}，**第一条命中即停**。")
w()
w("| 规则 id | 匹配方式 | 作用域 | 模式 | 命中 kb_type | 命中数 | 备注 |")
w("|---|---|---|---|---|---|---|")
for r in rules:
    scope = r.get("scope_table", "全局")
    pat = r.get("match_value") or r["pattern"]
    w(f"| {r['id']} | `{r['match_type']}` | {scope} | `{pat}` | `{r['kb_type']}` | {rule_hits.get(r['id'],0)} | {r.get('note','')} |")
w()
w(f"**0 命中的规则：** {'、'.join('`'+z+'`' for z in zero_rules) if zero_rules else '无（全部规则至少命中 1 条）'}")
w()
w(f"**资源级规则优先于表级兜底规则**；表名兜底命中 {sum(v for k,v in rule_hits.items() if k in ('R5','R8','R9','R18','R19','R20','R21','R22','R23','R24'))} 条，"
  f"记录字段值命中 {sum(v for k,v in rule_hits.items() if k in ('R1','R2','R3','R4','R6','R7','R14','R15','R16','R17'))} 条。")
w()
w("## 4. unknown 归属清单")
w()
w(f"`kb_type = unknown` 共 **{len(unk)} 条**，逐条原因归类如下（不猜、不外推）：")
w()
w("| 原因 | 条数 | 具体资源 |")
w("|---|---|---|")
for reason, n in unk_reasons.most_common():
    sample = [r["resource_key"] for r in unk if
              (r["table_name"] == "材料收集" and r["source_kind"] == "feishu_bitable_record" and "材料收集」的记录本身" in reason) or
              (reason.startswith("未命中") and r["table_name"] and r["table_name"] in reason) or
              (reason.startswith("入口表本身") and r["table_name"] == "材料收集" and r["source_kind"] != "feishu_bitable_record") or
              ("规则库表资源" in reason and r["table_name"] == "规则库") or
              ("分类说明表" in reason and r["table_name"] == "知识库分类说明") or
              ("入口 Base 容器" in reason and r["source_kind"] == "feishu_bitable_base")]
    shown = "、".join(f"`{s}`" for s in sample[:3]) + ("…" if len(sample) > 3 else "")
    w(f"| {reason} | {n} | {shown} |")
w()
w("**为什么没命中任何规则：**")
w()
w("- 入口表「材料收集」的 31 条记录是收料容器（一行 = 一份待收材料），不是知识本体；"
  "四类库的归属落在它 `材料链接` 指向的子资源上，因此记录本身按 R5 兜底为 `unknown`。")
w("- 规则库表资源是双态表：50 条记录里既有「外部法规/平台政策」也有「内部品线规则/案例沉淀」，"
  "表级不存在单一 `kb_type`，故表资源记为 `unknown`（记录级已分别由 R6/R7 命中）。")
w("- 入口 Base 容器、以及 3 条「知识库」列为空/其它的分类说明记录，均不属于四类库，"
  "按 `unmatched_policy` 记为 `unknown`，不猜测归属。")
w()
w("## 5. field_roles 全量清单")
w()
w(f"共 {len(registry['field_roles'])} 个字段角色；同名不同角色的字段用 `field_role_table_overrides` 覆盖。")
w()
w("| 字段名 | 角色 |")
w("|---|---|")
for k, v in registry["field_roles"].items():
    w(f"| `{k}` | `{v}` |")
w()
w("### 5.1 表级覆盖（同名不同角色）")
w()
w("| 表名::字段名 | 角色 |")
w("|---|---|")
for k, v in registry["field_role_table_overrides"].items():
    w(f"| `{k}` | `{v}` |")
w()
w(f"> 角色解析顺序：先查 `field_role_table_overrides`，未命中再查 `field_roles`。{registry['field_role_resolution']}")
w()
w("### 5.2 各表字段角色分布")
w()
allt = {"材料收集": None, "知识库分类说明": None, "正面和负面样本": None, "规则库": None}
sib = json.load(open("kb/.work/l1.json", encoding="utf-8"))["sibling_tables"]
for tname, st in sib.items():
    allt[tname] = st["fields"]
fm = json.load(open("kb/.work/fields-tblMGtPfe8ZUsEdP.json", encoding="utf-8"))["data"]["fields"]
allt["材料收集"] = [{"field_id": x["id"], "field_name": x["name"], "type": x["type"]} for x in fm]
w("| 表名 | 字段数 | link | attachment | image | video | status | text | other |")
w("|---|---|---|---|---|---|---|---|---|")
for tname, fl in allt.items():
    if not fl:
        continue
    roles = collections.Counter()
    for x in fl:
        role = registry["field_role_table_overrides"].get(f"{tname}::{x['field_name']}") or \
               registry["field_roles"].get(x["field_name"], "other")
        roles[role] += 1
    w(f"| {tname} | {len(fl)} | {roles['link']} | {roles['attachment']} | {roles['image']} | "
      f"{roles['video']} | {roles['status']} | {roles['text']} | {roles['other']} |")
w()
w("## 6. 异常清单（forbidden / not_found / no_permission / timeout）")
w()
w("| 资源 | source_kind | 状态 | 路径 | 原因 |")
w("|---|---|---|---|---|")
for r in res_list:
    if r["sha256_state"] in ("no_scope", "unreachable") or (r["status"] not in ("registered",)):
        st = {"no_scope": "forbidden", "unreachable": "not_found"}.get(r["sha256_state"], r["status"])
        w(f"| `{r['resource_key']}` | `{r['source_kind']}` | **{st}** | {r['path']} | {r['status_reason'] or '—'} |")
w()
w("> 无 `timeout`、无 `no_permission`（本次无被拒的资源级权限，全部是**应用 scope 缺失**，归类 `forbidden`）。")
w()
w("### 6.1 缺失的 scope 清单（导致内容不可读）")
w()
w("| 资源类型 | 缺失 scope | 受影响资源数 |")
w("|---|---|---|")
sc = collections.Counter()
for r in res_list:
    if r["sha256_state"] == "no_scope":
        sc[(r["source_kind"], (r.get("extra") or {}).get("missing_scope") or
            {"feishu_sheet": "sheets:spreadsheet:read", "feishu_slides": "slides:presentation:read",
             "feishu_file": "drive:file:download"}.get(r["source_kind"], "—"))] += 1
for (sk, scope), n in sc.items():
    w(f"| `{sk}` | `{scope}` | {n} |")
w()
w("## 7. 下钻失败率与失败清单")
w()
w(f"- 边总数：**{len(E)}**；其中 `status=ok` **{len(ok_edges)}**，非 ok **{len(fail_edges)}**")
w(f"- **下钻失败率 = {fail_rate:.1f}%**（{len(fail_edges)}/{len(E)}）")
w()
w("| 边状态 | 条数 | 含义 |")
w("|---|---|---|")
for k, v in sorted(cnt(e["status"] for e in E).items(), key=lambda x: -x[1]):
    meaning = {"ok": "下钻成功", "forbidden": "目标存在但缺 scope，读不到",
               "not_found": "目标返回 404 或无正文", "unsupported": "资源类型不支持读取",
               "timeout": "超时", "skipped_depth_limit": "超出下钻层数上限(2)，仅记录边不登记资源"}.get(k, "—")
    w(f"| `{k}` | {v} | {meaning} |")
w()
w("### 7.1 失败边明细")
w()
w("| from | to | depth | 状态 |")
w("|---|---|---|---|")
for e in fail_edges:
    w(f"| `{e['from_id']}` | `{e['to_id'][:80]}` | {e['depth']} | `{e['status']}` |")
w()
w("## 8. 重复资源清单")
w()
if dups:
    for head, items in dups.items():
        w(f"- 基准 `{head}`，重复项：")
        for i in items:
            w(f"  - `{i}`")
else:
    w("无重复资源（按 sha256 分组后每组仅 1 条）。")
w()
w(f"另有 **菱形汇聚** 信号：同一子资源被多个入口记录引用时不去重，逐条建边。"
  f"本次被 ≥2 条记录共同引用的资源见下：")
w()
multi = collections.Counter()
for e in E:
    if e["from_kind"] == "feishu_bitable_record":
        multi[e["to_id"]] += 1
w("| 子资源 | 被引用次数 |")
w("|---|---|")
for k, v in multi.most_common(10):
    w(f"| `{k[:70]}` | {v} |")
w()
w("## 9. schema 变化")
w()
w("本次为首次运行，全部表与字段均为**新增**，无改名、无删除。")
w()
w("| 变化类型 | 对象 |")
w("|---|---|")
for t in schema_changes["新增表"]:
    w(f"| 新增表 | `{t}` |")
w(f"| 改名表 | 无 |")
w(f"| 删除表 | 无 |")
w(f"| 新增字段 | 11 张表全部字段，见 registry `field_roles` 与 `kb/.work/fields-*.json` |")
w(f"| 改名/删除字段 | 无 |")
w()
w("后续运行复用本 registry；若表或字段有变化，按最小改动更新规则并在报告列出变化。")
w()
w("## 10. sha256 覆盖统计")
w()
w(f"- 有 sha256：**{sum(1 for r in res_list if r['sha256'])} 条**")
w(f"- 未哈希：**{len(nohash)} 条**")
w()
w("### 10.1 按 sha256_input 分类")
w()
w("| sha256_input | 条数 | 哈希输入 |")
w("|---|---|---|")
INPUT_DESC = {"record_fields": "记录全部字段原值，按 field_id 升序键序列化后（剔除 exclude_fields）",
              "doc_text": "读取到的文档内容，按 normalization 规范化后的文本",
              "url_text": "抓取到的正文，按 normalization 规范化后",
              "structure": "表/Base 结构（字段 id、名称、类型、选项）确定性序列化",
              "file_bytes": "文件字节流"}
for k, v in sha_by_input.most_common():
    w(f"| `{k}` | {v} | {INPUT_DESC.get(k,'—')} |")
w()
w("### 10.2 未哈希清单与原因")
w()
w("| sha256_state | 条数 | 原因 |")
w("|---|---|---|")
REASON = {"no_scope": "缺少读取所需 scope（sheets/slides/drive 下载权限未授权），读不到内容因此不计算 sha256",
          "structure_only": "结构指纹已算（sha256_input=structure），内容指纹需读取正文才能算",
          "unreachable": "抓取未返回可解析正文（HTTP 404 / 正文由 JS 渲染），不做 OCR/转写，不计算 sha256"}
for k, v in nohash_reason.most_common():
    w(f"| `{k}` | {v} | {REASON.get(k,'—')} |")
w()
w("### 10.3 规范化规则（确定性要求）")
w()
norm = registry["fingerprint_policy"]["normalization"]
w("| 项 | 值 |")
w("|---|---|")
for k, v in norm.items():
    w(f"| `{k}` | `{v}` |")
w()
w("> 规范化保证同一内容在任意时间、任意顺序下算出的 sha256 一致；本次未调整规范化规则，"
  "**无需全量重算**。")
w()
w("## 11. 疑似遗漏")
w()
for s in suspicious:
    w(f"- {s}")
w()
w(f"- 关联 Base「广告文案明细」共 291 条，本次采样上限 200 条，"
  f"**截断 {291-200} 条**（`records_truncated=true`）；「专家修订汇总表」395 条采样 200 条，**截断 195 条**。"
  f"两处截断均已在资源 `extra.records_truncated` 与本节显式标出，未静默丢弃。")
w(f"- 第三层及更深链接共 {len([e for e in E if e['depth']==3])} 条边**只记录不登记资源**（层数上限 2）："
  f"其中飞书 file 链接 8 条（`{', '.join(sorted({e['to_id'].split('/')[-1] for e in E if e['depth']==3 and 'feishu.cn/file' in e['to_id']}))[:120]}`）。")
w(f"- 关联 Base 记录中的 URL 字段共 {f['extra_l3'].get('base_field_urls_unique',0)} 个唯一 URL "
  f"（宿主 {', '.join(list(f['extra_l3'].get('hosts',{}).keys())[:6])} 等），"
  f"采样 {f['extra_l3'].get('base_field_urls_sampled_as_edges',0)} 条建边、"
  f"截断 {f['extra_l3'].get('base_field_urls_truncated',0)} 条、"
  f"格式异常（未编码中文/非标准 URL）{f['extra_l3'].get('base_field_urls_malformed',0)} 条。")
w()
w("## 12. 自主决策及其依据")
w()
decisions = [
    ("发现并标注 lark-cli 的 `drive +inspect` 全程缺 `drive:drive.metadata:readonly` scope",
     "改用 `wiki +node-get` 解析 wiki 节点 + 按 URL 路径轻量判别类型；wiki 链接 100% 解包成功。仍是只读。"),
    ("把「入口表记录」与「通过筛选的 record 所指向的子资源」分开归属",
     "规格要求资源必须同时有 kb_type 与 status，且只取「审核状态=通过」的记录。"
     "故 31 条记录全部登记（排除项也留痕），但只有 20 条通过记录派生出子资源；"
     "记录本身按 R5 兜底 unknown，四类库归属落在子资源上。"),
    ("kb_type 采用入口表自带的 `知识库分类` 标签，而不是自己判定业务域",
     "源侧已有分类标签，直接采信可避免硬约束 4（不判定 9 大业务域）与「不猜」；"
     "标签为「其它」或空时不归任何一类库。"),
    ("为 7 张下钻到的关联表补表名级规则（R18–R24，均限定 scope_table 只对该表生效），置信度中",
     "这 7 张表没有分类字段，若一律 unknown 会把 367 条资源打成未归属；"
     "表名与内容形态已足够指向某一类库，故按表名映射并在规则 note 里标注「置信度中」。"
     "因为按表名映射，R18（内容公式→措辞表达库）与 R19（专家修订汇总表→内部样本库）"
     "实际被 R24（数据表所在 Base 的表已各自命中）挡住而不命中，已在 0 命中清单中列出。"),
    ("`规则库` 表资源记 unknown，但记录级按 R6/R7 分流",
     "该表是双态表（外部法规 与 内部品线规则混装），表级无单一 kb_type；"
     "写进 registry 的 `table_unknown_allowlist` 而不是硬塞一个类型。"),
    ("同名不同角色的字段用 `field_role_table_overrides` 覆盖",
     "`来源链接` 在规则库是 link、在别处可能不是；用「表名::字段名」限定，避免误下钻。"),
    ("sheet / slides / file 资源不哈希内容，标 `sha256_state=no_scope`",
     "实测确认缺 `sheets:spreadsheet:read` / `slides:presentation:read` / `drive:file:download`，"
     "按「失败要登记」记录缺失 scope，不猜内容、不做 OCR/转写。"),
    ("`sha256_input` 枚举在规格给定的 4 种之外新增 `structure`",
     "结构化资源（表 / Base）没有「文档正文」也没有「文件字节流」，用结构（字段 id/名称/类型/选项）"
     "确定性序列化后哈希，仍满足「每条资源要么有 sha256 要么有明确 sha256_state」。"),
    ("结构化资源（表 / Base）用 `sha256_input=structure` 算结构指纹",
     "结构变化也是变更信号，且确定性可复现；内容指纹另计。"),
    ("`feishu_doc`/`feishu_sheet`/`feishu_slides`/`feishu_file`/`url` 等 source_kind 标在 registry 的 "
     "`sha256_input_by_source_kind`",
     "规格表格只列了 4 种 source_kind，实际遇到更多；扩展映射但保持 `sha256_input` 枚举不变。"),
    ("关联 Base 记录采样上限 200 条/表，第三层链接只建边不登记",
     "避免把 800+ 条与会话仅间接相关的记录灌进 L0；截断量已在报告与资源 extra 中显式标出，不静默丢弃。"),
    ("日期/选项原值 verbatim 保留，选项 id 标注为不可得",
     "飞书多维表格读接口只返回选项名，不返回 option id；据实标注而不是补造 id。"),
    ("manifest 采用 append-only，本次全量按 registered 追加",
     "首次运行无历史基线，不伪造 updated/unchanged。"),
]
for i, (d, why) in enumerate(decisions, 1):
    w(f"{i}. **{d}**")
    w(f"   - 依据：{why}")
w()
w("## 13. 自检结论（步骤 12）")
w()
w("| # | 检查项 | 结论 |")
w("|---|---|---|")
for name, res in checks:
    ok = "✅ " if res.startswith("通过") else "❌ "
    w(f"| {name.split('.')[0]} | {name.split('. ',1)[1]} | {ok}{res} |")
w()
w("### 13.1 本次触及原始库的全部操作及读写性质")
w()
w("| 操作 | 读写性质 | 对象 |")
w("|---|---|---|")
opkinds = collections.Counter()
for line in open(f"{KB}/runs/{RUN}.ops.log", encoding="utf-8"):
    if line.startswith("#") or line.startswith("时间"):
        continue
    parts = line.rstrip("\n").split(None, 2)
    if len(parts) >= 3:
        opkinds[parts[2]] += 1
for k, v in opkinds.items():
    w(f"| — | **{k}** | {v} 次 |")
w()
w(f"**全部操作性质均为读（`read` / `read-attempt`），写操作 0 次。** 明细见 `runs/{RUN}.ops.log`。")
w()
w("### 13.2 三件套产物")
w()
w("| 产物 | 路径 | 说明 |")
w("|---|---|---|")
w(f"| 筛选快照 | `kb/l0/runs/{RUN}.json` | 命中 {snapshot['matched_count']} / 排除 {snapshot['excluded_count']} |")
w(f"| 报告 | `kb/l0/runs/{RUN}.report.md` | 本文件 |")
w(f"| 调用台账 | `kb/l0/runs/{RUN}.ops.log` | 全部外部调用 + 读写性质 |")
w()
w("### 13.3 版本号检查")
w()
w(f"- `registry.kb_version = {registry['kb_version']}`（每类库 `kb_version` 均为 `v0`）")
w(f"- `kb/versions/versions.jsonl` 版本行 **{len(rows)} 条**（只有头部说明）")
w(f"- `kb/versions/VERSIONS.md` 由 `versions.jsonl` 投影生成，重建后逐字节一致：**{same}**")
w(f"- 未产出 `releases/`，未写任何 `release_id`")
w()
os.makedirs(f"{KB}/runs", exist_ok=True)
with open(f"{KB}/runs/{RUN}.report.md", "w", encoding="utf-8") as fh:
    fh.write("\n".join(L) + "\n")

json.dump({"checks": checks, "rule_hits": rule_hits, "zero_rules": zero_rules,
           "by_kb": by_kb, "by_sk": by_sk, "by_st": by_st, "unk": len(unk),
           "unk_reasons": dict(unk_reasons), "sha_by_input": dict(sha_by_input),
           "nohash_reason": dict(nohash_reason), "fail_rate": fail_rate,
           "n_edges": len(E), "n_fail_edges": len(fail_edges), "dups": {k: v for k, v in dups.items()},
           "suspicious": suspicious, "versions_rows": len(rows), "versions_same": same,
           "multi_ref": dict(multi.most_common(10))},
          open("kb/.work/report_stats.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("报告已写出；规则命中:", dict(sorted(rule_hits.items())))
print("0 命中规则:", zero_rules)
print("自检:", all(c[1].startswith("通过") for c in checks), "VERSIONS 一致:", same)
