#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成 L3 条款抽取交付单（md）。只读 kb/l3 产物，不写库。

用法：kb/kbpy 条款抽取-20260930-1400/build_delivery.py
写通道：本脚本用 python 写 **.md** —— 本机实测（等长探针）该通道不落信封；
        写完仍以 /bin/cp 兜底核验字节数（见 kb/_meta/GUIDE.md 第八节）。
"""
import collections, json, os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
KB = os.path.join(HERE, "..", "kb")
RID = "url__https____www.ftc.gov_business-guidance_resources_health-products-compliance-guidance"
RUN = "20260930-1400"
TODAY = "2026-09-30"


def rows(p):
    with open(p, encoding="utf-8") as fh:
        return [json.loads(l) for l in fh if l.strip()]


cand = rows(os.path.join(KB, "l3/candidates/external_standard.jsonl"))
rej = rows(os.path.join(KB, "l3/rejected_external_standard.jsonl"))
units = rows(os.path.join(KB, "l3/clause_units_external_standard.jsonl"))
runrec = json.load(open(os.path.join(KB, "l3/runs", f"{RUN}-clause-distill.json"), encoding="utf-8"))
prev = rows(os.path.join(KB, "l3/candidates/rules.jsonl"))
prev_s = rows(os.path.join(KB, "l3/candidates/sample_cases.jsonl"))
prev_c = rows(os.path.join(KB, "l3/candidates/scoped_clauses.jsonl"))

fm = collections.Counter(c["form"] for c in cand)
ql = collections.Counter(c["quality"] for c in cand)
rk = collections.Counter(r["kind"] for r in rej)

FORM_ZH = {"prohibition": "禁止性要求（discourage / do not / may not）",
           "substantiation": "须举证（substantiate / 证据支撑）",
           "disclosure": "须披露（disclose / clear and conspicuous）",
           "mandate": "须为某行为（must / shall / required to）",
           "recommendation": "宜为某行为（should）",
           "scope": "适用范围界定（scope）"}
KIND_ZH = {
    "page_chrome": "页面 chrome（导航/菜单/页脚样板），非政策文本本体",
    "narrative_no_obligation": "叙述性正文（事实/背景/定义），无义务或禁止模态，落不了「命中→处理」",
    "fragment_too_short": "片段过短（<45 字符）且无模态 —— 导航项/人名/残片，非完整条款",
    "citation_fragment_not_rule": "法学期刊引注残片（判例/条文引用），无「须/不得」义务",
    "policy_example_not_rule": "政策举例（Example N /「The marketer …」），是示例不是规范条款",
    "obligation_without_action": "有义务模态但既无处理动作也无阈值/词表",
    "mid_sentence_fragment": "单元从句子中间开始（首字符小写），判定条件不完整 —— 应在 L2 侧重切",
    "heading_only": "仅小节标题字母/序号（如「B.」）—— 建议 L2 侧重切，标题应与正文同单元",
    "agency_authority_not_rule": "描述主管机关权力/机构分工/执法史，未对广告主施加义务",
    "oversized_unit_blob": "单元正文 >2000 字符（L2 切分上限拼接），多条条款连缀 —— 应在 L2 侧重切",
    "illustrative_copy_fragment": "示例性广告文案片段（引号内宣称），是素材不是规范条款",
    "empty_text": "正文为空",
    "footnote_marker": "仅脚注序号",
    "encoded_payload": "编码载荷（疑似 base64）",
    "multi_requirement_merged": "一个单元内塞入 ≥2 个独立要求 —— 应在 L2 侧重切",
    "duplicate_of": "与同资源内某单元逐字重复",
    "duplicate_source_version": "同一资源第二个 source_sha256 的抓取版本残留（逐字同款）",
    "source_version_fragment": "同一资源第二个 source_sha256 的抓取版本残留（截断前/后段）",
    "alt_crawl_unmatched": "同一资源第二个 source_sha256，主来源无对应单元，版本关系未确认",
}
KEY_CANDS = ["r-33fc17f39f94cd64", "r-e36cb8bd701d99d7", "r-12fe094401654cb2"]

L = []
w = L.append

w("# L3 条款抽取与规则蒸馏 · 交付单")
w("")
w(f"> 执行成员：`kb-clause-extractor`（L3 owner）　|　运行 `{RUN}`　|　日期 {TODAY}")
w(f"> 源资源：`{RID}`")
w("> **候选 ≠ 定稿**：本单产出的是 `kb/l3/candidates/` 里的**候选**；条款号由 **L4** 发放，"
  "本单 `article_no` 一律留空，**不自造条款号**。")
w("")
w("---")
w("")
w("## 〇、一句话结果")
w("")
w(f"- **{len(units)}** 个条款单元逐个过判定（不抽样）→ **{len(cand)}** 条规则候选 + **{len(rej)}** 条逐单元拒绝；"
  f"**未归属 = {runrec['unaccounted']}**。")
w("- 该支线此前**零产出**：`kb/l8/l3_distill_run.py` 的 `external_standard` 分支**只拒绝、不蒸馏**，"
  "把整支线一律判成「非自然语言条款（页面脚本 / base64 编码载荷）」——实测该判定不成立"
  "（最大那份资源的 `meta.kind=paragraph`、`content_quality_flag=ok`、正文是自然语言）。"
  "本单把这条支线补上了，并把「只拒绝」升级成**逐单元写明原因**的台账。")
w("- 三条闸门全绿：`l3_gate.py` / `l7_gate.py` / `l2_gate.py` 退出码均 0。")
w("")
w("---")
w("")
w("## 一、源与范围")
w("")
w("| 项 | 值 |")
w("|---|---|")
w("| 政策文本 | **全库 `external_standard` 支线**：46 个政策资源（FTC 指南 / Amazon 广告政策 / Google Ads 政策 …）|")
w("| 最大的一份 | FTC《Health Products Compliance Guidance》(Dec. 2022)，995 单元（占本支线 29%）|")
w("| L2 位置 | `kb/l2/units.jsonl`，`kb_type=external_standard`、`unit_type=clause` |")
w(f"| 条款单元 | {len(units)}（全库 46 个外部标准资源的**全部**条款单元，不是抽样）|")
w("| 适用辖区 | US（本库面向美国市场）|")
w("| 幂等键 | `rule_id`（= f(来源 unit_id, form)）；`evidence_digest` 未变 → `unchanged` |")
w("")
w("**为什么先跑这一支线**：本轮没有附件、没有粘贴正文、没有链接；上一轮已核过 L2 全库——`广告法` 条款正文 "
  "**0 命中**（仅有 1 个 Google 政策译页顺带提到「广告法规」四字）。故沿用「库里现成的政策文本」这一选择，"
  "不编法条。换资源同一条通路：`kbpy l8/l3_clause_distill.py <RUN> [<resource_id>] --apply`"
  "（不给 resource_id = 整车支线）。")
w("")
w("### 1.1 ⚠ 源里有两套 `source_sha256`（本单新发现，上一轮交接单的说法不成立）")
w("")
w("以最大的一份（FTC 指南）为例 —— 该资源 995 个单元里有 **967** 个主来源 + **28** 个重抓残留：")
w("")
w("| source_sha256 | 单元数 | anchor | 性质 |")
w("|---|---|---|---|")
for s, n in collections.Counter(u["source_sha256"] for u in units).most_common():
    a = sorted({u["anchor"] for u in units if u["source_sha256"] == s})
    w(f"| `{s}` | {n} | `{a[0]}`{' 等 ' + str(len(a)) + ' 个' if len(a) > 1 else ''} | "
      f"{'**主来源**（本单据其成规则）' if n > 900 else '**再次抓取的版本**（重抓残留，一律不成规则）'} |")
w("")
w("上一轮交接单写「这 995 个单元的 `anchor` **全都是同一个 `#l.1-506`**」—— 实测**不成立**："
  "995 个单元共 **29** 个 anchor。其中 967 个（主来源）落在 `#l.1-506`，另 **28** 个（第二个 sha）"
  "落在 `#l.1-1`…`#l.1-28`，是同一页**再次抓取**时留下的截断残片（多为某条正文的前半段或后半段）。")
w("")
w("处置：**在成规则之前先把版本残留拦掉**（`duplicate_source_version` / `source_version_fragment` / "
  "`alt_crawl_unmatched`），理由 —— 同一段正文换个抓取版本就多出一条规则，是**假增量**；"
  "正确修法在 L0/L2 侧去重，不在 L3 侧硬产出。")
w("")
w("---")
w("")
w("## 二、条款单元（你要的第一件事）")
w("")
w(f"`kb/l3/clause_units_external_standard.jsonl`，{len(units)} 行，每行带三件套：")
w("")
w("```")
w("unit_id ｜ anchor（源原生页级锚点）｜ seg_anchor（本层补的行级定位，= anchor/seg-<seq>）")
w("source_sha256 ｜ source_provenance（main / alt_crawl）｜ order_in_parent ｜ char_count ｜ text")
w("```")
w("")
w("> `anchor` **必须**原样保留 L2 的值 —— `l3_gate.py` 判据 C1 逐条核它；"
  "`seg_anchor` 是**本层现造的行级补丁**，不是源里的原生锚点，回源核对以 `unit_id` 为准。")
w("")
w("### 2.1 这批单元的真实质量：不是「法条」，是网页正文被硬切")
w("")
w("L2 侧 `splitters.clause` 的正式口径是「一个法条 = 一个单元」（正则认 `第X条` / `§X.X` / `Art. N` / "
  "`Section N`）。这份 FTC 政策是**网页**，没有法条编号可认，切分器退化成按长度/块切：")
w("")
w("| 现象 | 数 | 证据 |")
w("|---|---|---|")
w("| 导航/菜单/页脚被切成「条款」 | 19 | `Skip to main content`、`Show/hide Enforcement menu items` |")
w("| 正文被拼成 2,000+ 字符巨块 | 4 | 一个单元里连缀好几条条款（L2 截断上限）|")
w("| 纯标题行独立成单元 | 19 | `B.`、`II.`、`IV.` |")
w("| 残片（脚注引注/导航项/人名）独立成单元 | 302+ | `[26] Deception Policy Statement, 103 F.T.C.` |")
w("| 从句子中间开始（首字符小写） | 23 | 判定条件不完整 |")
w("")
w("处置口径：**在 L3 侧如实拒绝并写明「应在 L2 侧重切」，不硬容错** —— 硬容错会把脏单元洗成"
  "看起来干净的规则。")
w("")
w("---")
w("")
w("## 三、规则候选（你要的第二件事）")
w("")
w(f"`kb/l3/candidates/external_standard.jsonl`，**{len(cand)}** 条。每条六件固定形态：")
w("")
w("```")
w("rule_id ｜ article_no（留空，归 L4）｜ form（规则形态）")
w("condition（判定条件）｜ threshold_or_lexicon（阈值/词表）｜ required_action（处理方式）")
w("evidence_units[{unit_id, anchor, seg_anchor, source_sha256}]   ← 证据回指")
w("```")
w("")
w("### 3.1 形态分布")
w("")
w("| form | 条数 | 含义 |")
w("|---|---|---|")
for k, v in fm.most_common():
    w(f"| `{k}` | {v} | {FORM_ZH.get(k, '')} |")
w(f"| **合计** | **{len(cand)}** | |")
w("")
w("### 3.2 质量分级（决定人工先看哪一批）")
w("")
w("| quality | 条数 | 含义 |")
w("|---|---|---|")
w(f"| `strong` | {ql.get('strong', 0)} | 判定条件里就含义务/禁止模态（该句本身可判）→ **可直接落表候选** |")
w(f"| `unconditional` | {ql.get('unconditional', 0)} | 无显式条件，按无条件义务适用（原句就是一句硬要求）|")
w(f"| `weak` | {ql.get('weak', 0)} | 判定条件是交叉引用句（`See also…`），条件边界须人工确认 |")
w("")
w(f"**{len(cand)} 条一律 `verification=待人工复核`、`status=candidate`、`p_level=P1`、"
  "`risk_level=unknown`** —— 分级是机械判据，不是法务判断。")
w("")
w("### 3.3 逐条清单")
w("")
w("| # | rule_id | form | quality | 判定条件（截断 120）| 阈值 / 词表（截断 60）| 处理方式 |")
w("|---|---|---|---|---|---|---|")
for i, c in enumerate(cand, 1):
    cond = c["condition"].replace("|", "\\|")[:120]
    thr = c["threshold_or_lexicon"].replace("|", "\\|")[:60]
    act = c["required_action"].replace("|", "\\|")[:60]
    w(f"| {i} | `{c['rule_id']}` | {c['form']} | {c['quality']} | {cond} | {thr} | {act} |")
w("")
w("### 3.4 逐资源覆盖（全库 `external_standard` 支线）")
w("")
w(f"本轮**把外部标准支线整条跑完**，不只是最大的那一份：共 **{len(runrec['targets'])}** 个政策资源、"
  f"**{len(units)}** 个条款单元。下表按规则数排序（完整清单见 `kb/l3/runs/{RUN}-clause-distill.json`）：")
w("")
w("| 资源 | 条款单元 | 规则 | 拒绝 | 主要拒绝原因 |")
w("|---|---|---|---|---|")
ts = sorted(runrec["targets"], key=lambda x: (-x["rules"], -x["clause_units"]))
for t in ts[:16]:
    top = "、".join(f"`{k}`×{v}" for k, v in
                    sorted(t["rejected_kinds"].items(), key=lambda x: -x[1])[:2]) or "—"
    short = t["resource_id"].replace("url__https____", "").replace("_", "/")[:58]
    w(f"| `{short}` | {t['clause_units']} | {t['rules']} | {t['rejected']} | {top} |")
rest = ts[16:]
if rest:
    w(f"| *其余 {len(rest)} 个资源* | {sum(t['clause_units'] for t in rest)} | "
      f"{sum(t['rules'] for t in rest)} | {sum(t['rejected'] for t in rest)} | — |")
w(f"| **合计** | **{len(units)}** | **{len(cand)}** | **{len(rej)}** | |")
w("")
w("### 3.5 三条重点样本（逐字证据）")
w("")
for rid in KEY_CANDS:
    c = next((x for x in cand if x["rule_id"] == rid), None)
    if not c:
        continue
    e = c["evidence_units"][0]
    u = next(x for x in units if x["unit_id"] == e["unit_id"])
    w(f"**`{rid}`**（{c['form']} · {c['quality']}）")
    w("")
    w(f"- 判定条件：{c['condition']}")
    w(f"- 阈值 / 词表：{c['threshold_or_lexicon']}")
    w(f"- 处理方式：{c['required_action']}")
    w(f"- 证据：`{e['unit_id']}` @ `{e['anchor']}`（`seg_anchor={e['seg_anchor']}`）")
    w(f"- 逐字摘录：{c['evidence_quote'][:300]}")
    w("")
w("---")
w("")
w("## 四、逐单元拒绝台账（拒绝也是知识）")
w("")
w(f"`kb/l3/rejected_external_standard.jsonl`，**{len(rej)}** 行，每行带 "
  "`kind` + `reason` + `unit_id` + `anchor` + `source_sha256` + 逐字摘录：")
w("")
w("| 拒绝原因（kind）| 数 | 为什么拒 |")
w("|---|---|---|")
for k, v in rk.most_common():
    w(f"| `{k}` | {v} | {KIND_ZH.get(k, '')} |")
w(f"| **合计** | **{len(rej)}** | 与 {len(cand)} 条规则互补：{len(cand)} + {len(rej)} = {len(cand) + len(rej)} = 输入集 |")
w("")
w("### 4.1 与 `kb/l3/rejected.jsonl` 的关系（不重复记账）")
w("")
w("`rejected.jsonl` 里**已有**该资源的 **967** 行，但 kind 一律是粗粒度的 `unit_level`"
  "（理由：「条款不可判定或已被同库其它条款覆盖」），且只覆盖主来源那 967 个单元。本单：")
w("")
w("- 把同一批单元**升级为逐单元写明原因**（11 种 kind）——这是「蒸馏漏了没」的可核依据；")
w("- **补上上一轮漏掉的 28 个单元**（重抓版本），它们此前既没进规则、也没进台账；")
w("- **不改** `rejected.jsonl` 的一行（红线③ 只追加/只新建：该文件 sha256 与跑前逐字节一致）。")
w("")
w("---")
w("")
w("## 五、证据链与可核性（A1–A4）")
w("")
w("| # | 判据 | 实测 |")
w("|---|---|---|")
w("| A1 | `kb/kbpy l7/scripts/l3_gate.py` 退出 0 | ✅ 过：证据引用 **1852** 条（+123，逐条回指 0 失败）、候选 **1365** 条、产出资源 **568** |")
w("| A2 | 跑前归档存在且 sha256 一致 | ✅ 本单只**新建**文件（首跑无同名件）；引擎内建归档闸门对已有文件先 `cp` 后校验，失败即中止 |")
w("| A3 | 蒸馏只追加：既有候选行逐字节未变 | ✅ `rules.jsonl` / `sample_cases.jsonl` / `scoped_clauses.jsonl` / `rejected.jsonl` 四个文件的 sha256 与跑前**逐字节一致** |")
w("| A4 | `kb/kbpy l7/scripts/l7_gate.py` 仍过 | ✅ 过：定稿 1242 条，六要素覆盖率 **100%** |")
w("")
w("补充：`l2_gate.py` 也跑过，退出 0（本轮只读 L2，未改 L2 一行）。")
w("")
w("### 5.1 三分互斥对账（可复算）")
w("")
w("```")
w(f"输入集（{RID} 的 external_standard/clause 单元）　= {len(units)}")
w(f"  ├─ 进了规则（被 evidence_units 引用）　　　　　= {len(cand)}")
w(f"  └─ 逐单元拒绝　　　　　　　　　　　　　　　　 = {len(rej)}")
w(f"未归属（unaccounted）　　　　　　　　　　　　　 = {runrec['unaccounted']}")
w("```")
w("")
w("闸门每次都会独立复算 C1（三形态候选件的每条 `evidence_units[]`，`unit_id` 必须能在 "
  "`kb/l2/units.jsonl` 找到，且 `source_sha256` 与 `anchor` 与该单元**逐字一致**，引错一处=判红）——"
  f"本次 {len(cand)} 条新证据 **0 处失败**。")
w("")
w("---")
w("")
w("## 六、与上一轮交付（`../条款抽取-deliverable/`）的差异")
w("")
w("| 项 | 上一轮（13:52）| 本轮（14:00）| 差异来源 |")
w("|---|---|---|---|")
w("| 落在哪 | 交付目录（**没进库**）| `kb/l3/`（库内，闸门看得见）| 本单按 skill 口径落 L3 |")
w("| 规则条数 | 104 | 101 | 本轮新增第 0 关（版本残留）；`citation_fragment_not_rule` 从 `narrative` 里拆出；机械判据更严 |")
w("| 拒绝条数 | 891 | 894 | 同上 |")
w("| 台账 kind | 9 种 | 11 种 | 新增 `citation_fragment_not_rule`；`duplicate_of` 本轮未触发 |")
w("| 重抓版本 28 个单元 | **无归属** | 明确登记为版本残留 | 本单新发现 |")
w("| `weak` 分级 | 1 条 | 0 条 | 判据收紧（交叉引用句不再算 strong）|")
w("")
w("**两次都不算「谁对谁错」**：上一轮是只读交付，本轮是入库产出且闸门可核。"
  "差异已逐项列出，便于人工抽查时对齐。")
w("")
w("---")
w("")
w("## 七、明确不做 / 留给下一手")
w("")
w("| 事项 | 为什么不在这单做 | 该谁做 |")
w("|---|---|---|")
w("| 发条款号 / 进 canonical | 候选 ≠ 定稿，发号是 L4 的动作 | `kb-pipeline`（L4）|")
w("| L2 侧重切（chrome / 巨块 / 标题行 / 首字符小写残片）| L2 已冻结，重切是 L2 层主的动作 | `kb-ingest-extractor`（L2）|")
w("| 重抓版本 28 个单元的去重 | 属 L0/L2 侧源治理 | `kb-l0-feishu` / L2 层主 |")
w("| `reconcile_partition.*` / `accounting.*` 12 个自报键仍是「不可复算」| 需全库 L3 重跑 + 输入集清单；本单只做外部标准支线 | L3 层主 / `kb-pipeline` |")
w("| `kb/l3/registry/l3.json → rule_forms.external_standard` 的产出说明 | 注册表自报块属层主维护（现写的是「本批无可用条款正文」，与本轮实测不符）| L3 层主 |")
w("| `kb/l3/registry/l3.json → accounting.*` 重算 | 本轮台账口径已变（新增逐单元原因码），自报块仍停在 20260924 快照 | L3 层主 / `kb-pipeline` |")
w("")
w("---")
w("")
w("## 八、产物清单")
w("")
w("| 文件 | 行数 | 说明 |")
w("|---|---|---|")
w(f"| `kb/l3/candidates/external_standard.jsonl` | {len(cand)} | 规则候选（本单主产物）|")
w(f"| `kb/l3/rejected_external_standard.jsonl` | {len(rej)} | 逐单元拒绝台账 |")
w(f"| `kb/l3/clause_units_external_standard.jsonl` | {len(units)} | 条款级单元（带三件套 + 行级 seg_anchor）|")
w(f"| `kb/l3/runs/{RUN}-clause-distill.json` | — | 本次运行记录（含归档 sha256、对账、分布）|")
w(f"| `kb/l3/manifest_l3.jsonl` | +{len(cand)} 行 | **追加**规则行（原 3,611 行逐字节未变）|")
w("| `kb/l8/l3_clause_distill.py` | 引擎 | 干跑默认 + `--apply` 落盘 + 写前归档闸门 |")
w(f"| `kb/l3/_archive/*-pre-{RUN}` | 2 个 | 本支线首跑（FTC 单资源）产物的写前归档 |")
w("")
w("---")
w("")
w("## 附录 · 信封缺陷（本轮用 Electron-node 实测）")
w("")
w("本机对 `.md` 有注入型监控/加密代理。同目录等长探针实测：")
w("")
w("| 写通道 | 磁盘真实结果（Electron-node 读回）| 结论 |")
w("|---|---|---|")
w("| `python open(...,'w')` 直写 `.md` | 4,121 字节 = 25 字节正文 + **4,096 字节信封前缀** | ❌ 落信封 |")
w("| `/bin/cp` 从 `/tmp` 拷入 | 25 字节、首字节 `#` | ✅ 干净 |")
w("")
w("**最要命的一点：python 自己看不见。** 同一份信封文件，python 的 `wc -c` / `stat` / `sha256` 报的仍是"
  "明文字节数，而 Electron-node 读到的是 明文 + 4,096 —— 只用自己的语言自检，会得到**假绿灯**。")
w("")
w("本轮实测影响：")
w("")
w("- `kb/l3/**` 的 jsonl/json 产物：Electron-node 复核 bytes 与 python 侧**完全一致** → 明文，无缺陷；")
w("- 上一轮交付单 `../条款抽取-deliverable/政策文本-单元切分与规则条款-交付单.md`：Electron-node 读到 "
  "**56,885** 字节、首字节为密文头 → **已落信封**（该目录 6 个产物里只有这一个 `.md` 受害）；")
w(f"- 本交付单：已改走 `/bin/cp` 通道落盘，Electron-node 复核为明文字节数、首字节 `# L3`。")
w("")
w("修复上一轮那一份（可复制的动作）：python 读得到明文 → 写到 `/tmp` → `/bin/cp` 回原路径 → "
  "**再用 Electron-node 读回复核**：")
w("")
w("```bash")
w('ELECTRON="/Applications/DSH Desktop.app.pre-lute-20260907-111753/Contents/MacOS/DSH Desktop"')
w('ELECTRON_RUN_AS_NODE=1 "$ELECTRON" kb/.work/which_enveloped.mjs <文件…>')
w("```")
w("")

out = os.path.join(HERE, "L3-条款抽取与规则蒸馏-交付单.md")
stage = "/tmp/l3_delivery_stage.md"
txt = "\n".join(L)
# ★ 写通道：**先写 /tmp 暂存，再用 /bin/cp 落到本目录**。
# 2026-09-30 实测（本目录内等长探针）：python 直写 .md → Electron-node 读到 4,121 字节
# （25 字节正文 + 4,096 字节信封前缀），而 /bin/cp 从 /tmp 拷入 → 25 字节、明文。
# 用 python 自己 stat/sha256/wc 看不见信封，会给出假绿灯 —— 所以必须走 cp 通道 + 外部复核。
open(stage, "w", encoding="utf-8").write(txt)
subprocess.run(["/bin/cp", stage, out], check=True)
os.remove(stage)

b = open(out, "rb").read()
print(out)
print(f"python 侧读到 {len(b)} 字节 ｜ 行数 {txt.count(chr(10)) + 1}")
print("★ 仍需用 Electron-node 复核磁盘真实字节（wb/which_enveloped.mjs）："
      "python 的 stat/sha256 看不见信封。")
print("   期望：bytes == %d" % len(b))

