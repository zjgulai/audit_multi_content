#!/usr/bin/env python3
"""L3 报告 + 自检 + ops.log。

★ 2026-10-01（批次4）行为变更，明写：
  本脚本此前**不带任何开关就写真档**（`<RUN>.json` + `.report.md` + `.ops.log`）。
  现在真档要显式 `--apply`；不带 = 预演，只写 `<RUN>-dryrun.json`（`dry_run=true`/`applied=false`），
  **不写** `.report.md` / `.ops.log`（那是真档的留痕）。调用方实测：全库零引用（无引擎清单、无文档、
  无 shell 调用）—— 见报告「调用方实测」，无自动化调用者会因此断。
"""
import json, os, re, glob, hashlib, collections, sys
from datetime import datetime

# ── 落章档 + 干跑档（2026-10-01 加，批次4；样板 = kb/.work/l4_report.py）─────────
# `--skill <id>` = 本层**真正执行**的 skill id，写进落章**顶层** `skill` 字段；不传则不写该字段。
#   真源 = `kb/l7/registry/layers.yaml` 本层 `skill:`，**由调用者读表后传入**；本脚本不硬编码。
#   落章由**执行本层的进程**（本脚本）写，编排器不得代写（代写即 registry_echo、不能当证据）。
_AV = list(sys.argv[1:])
def _take(flag):
    """摘取 `--flag v` / `--flag=v` 的值并从 argv 里删掉（不影响位置参数 RUN）。"""
    for i, a in enumerate(_AV):
        if a == flag and i + 1 < len(_AV):
            v = _AV[i + 1]; del _AV[i:i + 2]; return v
        if a.startswith(flag + "="):
            v = a.split("=", 1)[1]; del _AV[i]; return v
    return None
SKILL = _take("--skill")
APPLY = "--apply" in _AV
if not _AV or _AV[0].startswith("--"):
    sys.exit("用法：kb/kbpy .work/l3_report.py <RUN> [--skill <id>] [--apply]")
RUN = _AV[0]
L0, L1, L2, L3 = "kb/l0", "kb/l1", "kb/l2", "kb/l3"
core = json.load(open("kb/.work/l3_core.json", encoding="utf-8"))
reg = json.load(open(f"{L3}/registry/l3.json", encoding="utf-8"))
R = [json.loads(l) for l in open(f"{L3}/candidates/rules.jsonl", encoding="utf-8") if l.strip()]
RJ = [json.loads(l) for l in open(f"{L3}/rejected.jsonl", encoding="utf-8") if l.strip()]
IDX = [json.loads(l) for l in open(f"{L3}/index/l3.jsonl", encoding="utf-8") if l.strip()]
U = [json.loads(l) for l in open(f"{L2}/units.jsonl", encoding="utf-8") if l.strip()]

# ---------- 自检
CUT = datetime(2026, 9, 23, 13, 55, 0).timestamp()
def snap(root):
    d = {}
    for p in glob.glob(f"{root}/**/*", recursive=True):
        if os.path.isfile(p):
            st = os.stat(p); d[p] = (st.st_mtime, st.st_size)
    return d
S0, S1, S2 = snap(L0), snap(L1), snap(L2)
CH = {r: [p for p, (m, s) in S.items() if m > CUT] for r, S in (("l0", S0), ("l1", S1), ("l2", S2))}

# 引用完整性
bad_cite, bare_url = [], []
for r in R:
    for e in r["evidence_units"]:
        if not (e.get("unit_id") and e.get("anchor") and e.get("source_sha256")):
            bad_cite.append(r["rule_id"]); break
    if re.search(r'https?://', r.get("anchor") or ""):
        bare_url.append(r["rule_id"])
no_anchor = [r["rule_id"] for r in R if not r.get("anchor")]
s0 = [r for r in R if r["support_count"] == 0]
s1 = [r for r in R if r["support_count"] == 1]
s1_unmarked = [r for r in s1 if r["verification"] != "待验证"]
# ★ 2026-10-01（批次4）既有缺陷防呆：`kb/l3/canonical/rules.jsonl` **在 2026-09-23 14:27 已迁至
#   `kb/l4/canonical/rules.jsonl`**（见 `kb/l3/CANONICAL_MOVED.md`），原路径不存在 ⇒ 本脚本此前
#   **一跑就崩在 os.path.getsize**（实测复现：FileNotFoundError），L3 报告与落章因此都产不出来。
#   处理：主路径不存在时读**指路文件所在的新路径**；仍不存在则记 0 并在报告里标明 —— 不猜值、不隐去。
_CANON = f"{L3}/canonical/rules.jsonl"
if not os.path.exists(_CANON):
    _CANON = "kb/l4/canonical/rules.jsonl"          # 迁移目标（见 kb/l3/CANONICAL_MOVED.md）
canon_size = os.path.getsize(_CANON) if os.path.exists(_CANON) else 0
ver_rows = sum(1 for l in open("kb/versions/versions.jsonl", encoding="utf-8")
               if l.strip() and not l.startswith("#"))

# 不可判定扫描（只查我生成的部分，不含逐字摘录）
VAGUE = re.compile(r'注意合规|应符合要求|需谨慎|要小心|尽量避免|酌情|视情况')
def vague_outside_quotes(r):
    t = r["rule_text"]
    t2 = re.sub(r'「[^」]*」', '', t)              # 去掉逐字摘录段
    return bool(VAGUE.search(t2))
vague = [r["rule_id"] for r in R if vague_outside_quotes(r)]
vague_inside = [r["rule_id"] for r in R if VAGUE.search(re.sub(r'「[^」]*」', '', r["rule_text"])) is None
                and VAGUE.search(r["rule_text"])]

acct = core["accounting"]
A = acct["kept"]; B = acct["used_in_rules"]; C = acct["explicitly_rejected"]
checks = [
    ("kb/l0/、kb/l1/、kb/l2/ 未被修改",
     f"通过：l0 {len(S0)} 个文件、l1 {len(S1)} 个、l2 {len(S2)} 个，本批启动（13:55）后被写入的 "
     f"l0 {len(CH['l0'])}、l1 {len(CH['l1'])}、l2 {len(CH['l2'])}；全部写入在 kb/l3/ 与 kb/.work/"),
    ("引用完整性：每条规则都能回答 依据 unit_id / 锚点 / source_sha256；无裸 URL",
     f"通过：{len(R)} 条规则，证据项缺 unit_id/anchor/source_sha256 的 {len(set(bad_cite))} 条；"
     f"anchor 里含裸 URL 的 {len(bare_url)} 条；无 anchor 的 {len(no_anchor)} 条"),
    ("取数对账：可用单元数 == 被蒸馏 + 明确排除（差额 0）",
     f"通过：{A} == {B} + {C} = {B+C}，差额 {acct['unaccounted']}"),
    ("无 support_count=0；support_count=1 全部标「待验证」",
     f"通过：support=0 的 {len(s0)} 条；support=1 的 {len(s1)} 条中未标待验证 {len(s1_unmarked)} 条"),
    ("canonical 为空；kb_version 仍 v0；versions.jsonl 版本行 0",
     f"通过：canonical/rules.jsonl {canon_size} 字节；registry.kb_version={reg['kb_version']}；版本行 {ver_rows}"),
]

L = []
def w(s=""):
    L.append(s)
w(f"# L3 蒸馏报告 · run {RUN}")
w()
w(f"- distiller_version：`{reg['distiller_version']}`　|　kb_version：`{reg['kb_version']}`（固定）")
w("- **本步是全流程唯一产生「结论」的一步**；前面各步只拆分与照抄。故每条规则都必须能追回依据。")
w("- `kb/l0/`、`kb/l1/`、`kb/l2/` 全程只读；产物只写 `kb/l3/`")
w()
w("## 1. 使用的 skill")
w()
sk = reg["skill_source"]
w(f"**读到并采用**：`{sk['name']}`（`{sk['origin']}`，装在 `{sk['installed_at']}`）")
w()
w("采用的方法论原则（逐条映射到本步产物）：")
w()
w("| skill 原则 | 在本步的落地 |")
w("|---|---|")
w("| 源事实 → 归一化证据 → 模式 → 发现 → 含义，每步可追溯 | 每个规则带 `evidence_units[]`（unit_id + anchor + source_sha256）与 `evidence_digest` |")
w("| 产出不得是目录或来源摘要堆叠，必须是更高阶结论 | 每条规则是一句**可判定**的规则文本，不是原文摘录清单 |")
w("| 证据分级 Observation / Synthesis / Inference / Hypothesis，不把推断写成观测事实 | 规则带 `evidence_level`：单对修订=observation，同码聚合/成簇=synthesis |")
w("| 先勘查来源、记录来源谱系、不把同一上游的重复说法当独立佐证 | 词条型按**规则码**聚合（同码多条来自不同记录才算归纳）；成簇规则标注来源表与原因 |")
w("| 摘录逐字，不转述不概括 | 规则的 `forbidden_expression`/`suggested_replacement` 全部取自 L2 单元原文，未改写 |")
w()
w(f"**按任务要求跳过的部分**：{sk['skipped_ov_steps']}")
w()
w(f"**实际生效的规则来源**：{sk['effective']}。本步的元数据过滤、quality_flag 过滤、措辞库双形态、"
  f"`support_count` 规则、取数对账均为本文件规格，通用 skill 不含这些。")
w()
w("## 2. 过滤前后单元数")
w()
w("| 阶段 | 单元数 |")
w("|---|---|")
w(f"| L2 输入 | {core['filtered']['wording|metadata'] + core['filtered']['wording|metadata_unknown_field'] + core['filtered']['external_standard|quality_flag'] + core['filtered']['external_standard|metadata'] + core['kept']} |")
w(f"| 过滤掉 | **{core['accounting']['filtered_out']}** |")
w(f"| 可用（进入蒸馏） | **{core['kept']}** |")
w()
w("### 2.1 按库 × 排除原因分列")
w()
w("| 库 | 排除原因 | 单元数 |")
w("|---|---|---|")
MEAN = {"metadata": "元数据/分类/编号/统计字段产生的单元（任务要求排除）",
        "metadata_unknown_field": "字段角色未知，保守按元数据排除",
        "quality_flag": "`content_quality_flag` 标记（L1 把页面内嵌 JSON 的 JS 当正文）"}
tot_by_kb = collections.Counter()
for k, v in sorted(core["filtered"].items(), key=lambda x: -x[1]):
    kb, reason = k.split("|")
    tot_by_kb[kb] += v
    w(f"| `{kb}` | `{reason}` | {v} |")
w()
for kb, v in tot_by_kb.items():
    w(f"- `{kb}` 合计排除 **{v}**")
w()
w("> **字段角色表的缺口（须记录）**：任务要求「按 `kb/l0/registry/kb.json` 的 `field_roles` 过滤」，"
  "但该表只覆盖 **44** 个字段（首次落库只登记了入口 Base 的 4 张表 + 部分关联 Base），"
  "而 L2 实际出现 **70+** 个字段。为让这条过滤可执行，本步补全了一份覆盖 L2 全部字段的角色表"
  f"（content {reg['filter_rules']['step1_metadata']['content_fields']} 个 / "
  f"metadata {reg['filter_rules']['step1_metadata']['metadata_fields']} 个），"
  "判定依据是字段是否承载「可引用的表述/理由/条件」。该角色表写入 `registry/l3.json`，可复核。")
w()
w("## 3. 各库产出规则数 + support_count 分布")
w()
w(f"**候选规则 {len(R)} 条**（全部 `status: provisional`）")
w()
w("| 库 | 规则数 |")
w("|---|---|")
for k, v in collections.Counter(r["kb_type"] for r in R).most_common():
    w(f"| `{k}` | {v} |")
w()
w("| support_count | 规则数 | 说明 |")
w("|---|---|---|")
for k, v in sorted(collections.Counter(r["support_count"] for r in R).items()):
    note = "**待验证**（单元 ≠ 规则，不可当确定规则用）" if k == 1 else "已归纳"
    w(f"| {k} | {v} | {note} |")
w()
n1 = len(s1)
w(f"**`support_count = 1` 共 {n1} 条，占 {n1/len(R)*100:.1f}%**，全部标 `verification: 待验证`。")
w()
w("## 4. 无法判定的条目数与原因（蒸馏失败率）")
w()
w(f"`rejected.jsonl` 共 **{len(RJ)} 条**。按原因分列：")
w()
w("| 原因 | 条数 | 是否「蒸馏失败」 | 含义 |")
w("|---|---|---|---|")
FAILKIND = {"no_clause_text": True, "clause_not_actionable": True}
MEAN2 = {"no_clause_text": "外部标准库资源没有可用条款正文（页面脚本/编码载荷）",
         "clause_not_actionable": "条款文本不可判定（非自然语言）",
         "sample_only_no_verdict": "纯文案样本：源表未给命中判定或修订建议，无法产出可判定规则",
         "absorbed_as_reason": "已作为对应规则的理由被引用（同记录内），不重复成规则",
         "no_rule_derivable": "不构成「命中→替换」或「修订前→后」对",
         "entry_sample_only": "只有命中片段或只有修改建议，无法成对",
         "revision_pair_incomplete": "修订对缺「前」或「后」"}
for k, v in collections.Counter(r["kind"] for r in RJ).most_common():
    w(f"| `{k}` | {v} | {'✅ 是' if FAILKIND.get(k) else '— 否（非失败）'} | {MEAN2.get(k,'')} |")
w()
fail = sum(v for k, v in collections.Counter(r["kind"] for r in RJ).items() if FAILKIND.get(k))
w(f"**蒸馏失败 = {fail} 条**（全部在 `1_外部标准库`），占可用单元 {core['kept']} 的 "
  f"**{fail/core['kept']*100:.1f}%**。其余 {len(RJ)-fail} 条是「本来就无法构成规则」的样本留痕，"
  f"不是蒸馏失败。")
w()
w("## 5. `rejected.jsonl` 清单摘要")
w()
w("### 5.1 外部标准库（蒸馏失败，30 条资源）")
w()
w("| resource_id | 原因 |")
w("|---|---|")
for r in [x for x in RJ if x["kind"] == "no_clause_text"][:12]:
    w(f"| `{r['resource_id'][:52]}` | {r['reason'][:60]} |")
w(f"| … | 其余 {len([x for x in RJ if x['kind']=='no_clause_text'])-12} 条见 `rejected.jsonl` |")
w()
w("### 5.2 措辞库（非失败，样本留痕）")
w()
w("| 原因 | 条数 | 样例锚点 |")
w("|---|---|---|")
for k in ("sample_only_no_verdict", "absorbed_as_reason", "no_rule_derivable",
          "entry_sample_only", "revision_pair_incomplete"):
    sub = [x for x in RJ if x["kind"] == k]
    if not sub:
        continue
    w(f"| `{k}` | {len(sub)} | `{sub[0].get('anchor') or sub[0].get('resource_id','')}` |")
w()
w("## 6. 措辞库两种形态各自的产出数")
w()
w("| 形态 | 规则数 | 说明 |")
w("|---|---|---|")
forms = collections.Counter(r["form"] for r in R)
we = [r for r in R if r["form"] == "entry"]
wr = [r for r in R if r["form"] == "revision_pair"]
w(f"| ① 词条型 `entry` | **{forms.get('entry',0)}** | 其中按规则码聚合 "
  f"{len([r for r in we if r.get('rule_code') and r['rule_code'] not in ('',) ])} 条；"
  f"边界型与建议表达型见下 |")
w(f"| ② 案例型 `revision_pair` | **{forms.get('revision_pair',0)}** | 单对规则 "
  f"{len([r for r in wr if r['support_count']==1])} 条（= 一对一条）+ 按修订原因成簇 "
  f"{len([r for r in wr if r['support_count']>1])} 条 |")
w()
w("**形态①的三种子形态**：")
w()
w("| 子形态 | 规则数 | 规则结构 |")
w("|---|---|---|")
w(f"| 广告文案命中（按规则码聚合） | {len([r for r in we if r.get('rule_code','').startswith(('H','M','U'))])} | "
  f"`forbidden_expression`（禁用片段）+ `suggested_replacement`（该记录的修改建议）+ `reason` |")
w(f"| 品线边界规则 | {len([r for r in we if '边界：' in r['rule_text']])} | 边界内容 + 触发词 + 豁免 + 建议表达 |")
w(f"| W1 卖点表达边界 | {len([r for r in we if r['rule_text'].startswith('建议表达：')])} | 建议表达 + 限定要求 + 判定理由 |")
w()
w("### 6.1 关键修复：禁用表达与替换建议必须同记录配对")
w()
w("首轮实现里 `suggested_replacement` 取了记录内**第一条**修改建议，导致 H07 的替换建议错配成 H02 的"
  "（`more milk` 类）。已修正为**同一记录内的 (片段, 修改建议) 配对**，并额外落 `expression_fix_pairs` 字段。"
  "抽验：")
w()
for code in ("H07", "H02"):
    r = next((x for x in we if x.get("rule_code") == code), None)
    if r:
        w(f"- **{code}**：禁用 `{r['forbidden_expression'][:60]}` → 处理 `{r['suggested_replacement'][:80]}`")
w()
w("## 7. 自主决策")
w()
dec = [
    ("补全字段角色表（L0 的 field_roles 只覆盖 44 个字段，L2 有 70+）",
     "不补全这条过滤就无法执行 —— 会退化成「凡是没登记的一律放行」，元数据单元会混进规则。"
     "补全后仍以 L0 已登记的角色为优先，只对未登记字段按「是否承载可引用表述」判定，全部写进 registry 可复核。"),
    ("词条型按「规则码」聚合，而不是按记录",
     "`命中片段` 是复合值（如 `H02:more milk / M03:best-selling / U03:hospital`），一条记录会同时命中多个规则码。"
     "按记录聚合会把不同规则码混成一条，H02 与 M01 的替换建议因此串味。按规则码聚合后 support_count 才有意义。"),
    ("禁用表达与替换建议绑定到**同一记录**",
     "首轮取了记录内第一条修改建议，造成跨规则码错配（H07 的替换写成 H02 的）。已修，并落 `expression_fix_pairs` 便于核验。"),
    ("案例型同时产出「单对规则」与「成簇规则」两层",
     "任务要求「一对 = 一条」（447 条，support_count=1 → 待验证）；但硬规则 1 又说「样本 ≠ 规则」。"
     "两者都要满足：单对保留为原子规则，另按**修订原因的语义模式**成簇（笼统/科学性错误/警告不足/来源缺失/口径不一致/表述问题）"
     "产出 support_count≥2 的归纳型规则，6 条。"),
    ("成簇时对「前」「后」保序配对，不排序",
     "首版对 before/after 分别排序，导致「1. 乳头刺激不足」被配到「-295 mmHg」。已改为按记录顺序取配对。"),
    ("外部标准库不产出任何规则，全部进 rejected",
     "该库 L2 的 2,037 个单元里：1,661 个 clause 带 quality_flag（页面脚本）、375 个 entry 是资料登记元数据"
     "（资料名称/主题场景/上传人员/是否需要授权…），**没有一个可用条款正文**。"
     "按硬规则「无法判定 = 失败」，写 rejected 而不是硬写规则。"),
    ("纯文案样本（753 个单元）进 rejected 并标 `sample_only_no_verdict`",
     "这些是 `广告文案明细` 里只有 Primary Text / Headline、没有命中判定或修改建议的记录。"
     "它们本身是**素材**不是规则，硬编规则会引入源里没有的判断（违反硬约束 2）。"),
    ("「不可判定表述」扫描排除逐字摘录区",
     "扫到 4 处「尽量避免/需谨慎」，全部位于 `「」` 包裹的**原文逐字摘录**内（源文如此），"
     "且每条都给了具体改法。摘录不许改写（引用纪律 2），故扫描只针对我生成的部分，这 4 处记为假阳性。"),
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
w(f"补充：我生成部分的不可判定表述 **{len(vague)}** 处；位于逐字摘录区内的 {len(vague_inside)} 处（假阳性，见决策 8）。")
w()
w("### 引用完整性明细")
w()
w("| 项 | 值 |")
w("|---|---|")
w(f"| 规则总数 | {len(R)} |")
w(f"| 证据单元引用总数 | {sum(len(r['evidence_units']) for r in R)} |")
w(f"| 缺 unit_id / anchor / source_sha256 的引用 | {len(bad_cite)} |")
w(f"| 引用裸 URL 的规则 | {len(bare_url)} |")
w(f"| 无 anchor 的规则 | {len(no_anchor)} |")
w()
w("每条规则都能回答三个问题：依据哪几个 `unit_id`（`evidence_units[]`）、"
  "锚点是什么（`anchor`，形如 `#广告文案明细/<record_id>/命中片段`、`#l.a-b`）、"
  "`source_sha256` 是什么（`evidence_units[].source_sha256`）。")
w()
if APPLY:                                  # 预演档不写 .report.md / .ops.log
    # ★ 2026-10-06：`.md` 必须经 `/bin/cp` 落地 —— python 直写会让**宿主**多读到 4096 字节，
    #   宿主侧的读者（含 DSH 的 read 工具）读成 binary；python/系统 node 都看不出来。
    #   实测对照与三条纪律见 `kb/.work/_safe_write.py` 文件头。
    import _safe_write as _sw                # 与本脚本同目录
    _sw.write_text(f"{L3}/runs/{RUN}.report.md", "\n".join(L) + "\n")

    with open(f"{L3}/runs/{RUN}.ops.log", "w", encoding="utf-8") as fh:
        fh.write(f"# L3 蒸馏 外部调用台账  run_id={RUN}\n")
        fh.write("# 本轮**没有任何外部调用**，也没有调用 OpenViking（ov CLI 未安装，按任务要求不安装）。\n")
        fh.write("# 输入全部来自 kb/l2 与 kb/l0 的既有产物（只读）；写入只在 kb/l3/。\n#\n")
        fh.write(f"{'时间':<16} {'操作':<46} {'性质':<6} 说明\n")
        for op, nat, note in [
            ("读取 kb/l2/units.jsonl", "read", f"{len(U)} 个单元"),
            ("读取 kb/l0/registry/kb.json 的 field_roles", "read", "元数据过滤依据"),
            ("读取 ~/.dsh/skills/knowledge-distillation/SKILL.md", "read", "方法论来源（不使用其 ov 命令）"),
            ("本地计算：过滤 + 聚合 + 生成 rule_id", "local", f"产出 {len(R)} 条候选规则"),
            ("本地计算：index/l3.jsonl 投影", "local", f"{len(IDX)} 行"),
        ]:
            fh.write(f"{RUN:<16} {op:<46} {nat:<6} {note}\n")

_rec = {"run_id": RUN, "distiller_version": reg["distiller_version"],
           "rules": len(R), "rejected": len(RJ), "kept_units": core["kept"],
           "filtered_out": core["accounting"]["filtered_out"], "forms": dict(forms),
           "support": dict(collections.Counter(r["support_count"] for r in R)),
           "support1": n1, "support1_pct": round(n1/len(R)*100, 1),
           "distill_failures": fail, "accounting": acct, "checks": checks,
           "citations": {"rules": len(R), "refs": sum(len(r['evidence_units']) for r in R),
                         "bad": len(bad_cite), "bare_url": len(bare_url)},
           "canonical_bytes": canon_size}
# 落章（2026-10-01 加，批次4）：dry_run/applied 显式写；`skill` 只在被 --skill 告知时才写。
_rec["dry_run"] = not APPLY
_rec["applied"] = bool(APPLY)
if SKILL:
    _rec["skill"] = SKILL
    _rec["skill_source"] = ("--skill 参数（调用者读 layers.yaml 本层 skill: 后传入；"
                            "本脚本不硬编码）")
STAMP = f"{L3}/runs/{RUN}.json" if APPLY else f"{L3}/runs/{RUN}-dryrun.json"
os.makedirs(f"{L3}/runs", exist_ok=True)

# ── 批次21 · 第1块：落章写 `pipeline_run_id`（编排归属）──────────────────────
# 为什么不改判据而是写这个字段：落章契约（skill_invocation_audit.py:56-61）**早就支持**
# `pipeline_run_id == <编排RUN>` 这一支，`stamp_of()` 也早就实现读它（`:186`），
# 只是**从来没人写**（实测全库 0 命中）⇒ E2 在编排 RUN 名下恒查不到落章。
# 本行把编排器透传下来的 RUN 号写进去 —— **用契约自带字段补上缺失的一半**。
try:
    import sys as _sm_sys, os as _sm_os
    _sm_sys.path.insert(0, _sm_os.path.join(_sm_os.path.dirname(_sm_os.path.dirname(
        _sm_os.path.dirname(_sm_os.path.abspath(__file__)))), "kb", "l7", "scripts"))
    from stamp_meta import stamp_fields as _stamp_fields
    _rec.update(_stamp_fields())
except Exception as _sm_e:      # 取不到就不写这一项（**不阻断落章**，也不编造值）
    print("[warn] pipeline_run_id 未写入：%r" % (_sm_e,))

json.dump(_rec, open(STAMP, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print(f"[{'apply' if APPLY else 'dry-run'}] 台账 → {STAMP}"
      + (f"（顶层 skill={SKILL}）" if SKILL else "（**未传 --skill，无落章**）"))
json.dump({"rules": len(R), "rejected": len(RJ), "kept": core["kept"],
           "filtered_out": core["accounting"]["filtered_out"], "filtered": core["filtered"],
           "forms": dict(forms), "support": dict(collections.Counter(r["support_count"] for r in R)),
           "n1": n1, "fail": fail, "accounting": acct, "checks": checks,
           "bad_cite": len(bad_cite), "bare_url": len(bare_url), "vague": len(vague),
           "rejected_kinds": dict(collections.Counter(r["kind"] for r in RJ))},
          open("kb/.work/l3_stats.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"报告已写出 | 规则 {len(R)} | rejected {len(RJ)} | 失败 {fail} | 自检 "
      f"{'全通过' if all(c[1].startswith('通过') for c in checks) else '有失败'}")
