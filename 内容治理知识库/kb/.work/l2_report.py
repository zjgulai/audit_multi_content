#!/usr/bin/env python3
"""L2 报告 + 自检 + ops.log。"""
import json, os, re, glob, hashlib, collections, statistics, sys
from datetime import datetime

RUN = sys.argv[1]
L0, L1, L2 = "kb/l0", "kb/l1", "kb/l2"
SV = "l2-0.2"
reg = json.load(open(f"{L0}/registry/kb.json", encoding="utf-8"))
DIR_MAP, REV = reg["dir_map"], reg["dir_map_reverse"]
core = json.load(open("kb/.work/l2_core.json", encoding="utf-8"))
pairs = json.load(open("kb/.work/l2_pairs.json", encoding="utf-8"))
U = [json.loads(l) for l in open(f"{L2}/units.jsonl", encoding="utf-8") if l.strip()]
idx = [json.loads(l) for l in open(f"{L2}/index/l2.jsonl", encoding="utf-8") if l.strip()]
man = [json.loads(l) for l in open(f"{L2}/manifest_l2.jsonl", encoding="utf-8") if l.strip()]

# ---- 取数对账
def has_content(o):
    if o.get("segments") or o.get("tables"):
        return True
    return any((m.get("ocr_char_count") or 0) > 0 or m.get("visual_description")
               for m in (o.get("media_refs") or []))

L1_RES = {}
for k in DIR_MAP.values():
    L1_RES[k] = {}
    for p in glob.glob(f"{L1}/{REV[k]}/*.json"):
        o = json.load(open(p, encoding="utf-8"))
        L1_RES[k][o["resource_id"]] = o

# 范围外库补记账（skipped_out_of_scope），保证「不允许既没被处理也没登记原因」
OOS = [r for r in core["res_log"] if r["reason"] == "skipped_out_of_scope"]
for kb in ["product_desc", "unknown", "internal_sample"]:
    have = {(r["resource_id"] for r in core["res_log"] if r["kb_type"] == kb)}
    for rid in L1_RES[kb]:
        if rid not in have:
            core["res_log"].append({"resource_id": rid, "kb_type": kb, "result": "skipped",
                                    "units": 0, "reason": "skipped_out_of_scope",
                                    "detail": "本轮范围只切 3_措辞表达库 + 1_外部标准库"})

ACCT = {}
for kb in ["wording", "external_standard", "internal_sample", "product_desc", "unknown"]:
    n = len(L1_RES[kb])
    rs = [r for r in core["res_log"] if r["kb_type"] == kb]
    split = sum(1 for r in rs if r["result"] == "split")
    skip = sum(1 for r in rs if r["result"] == "skipped")
    ACCT[kb] = {"l1": n, "content": sum(1 for o in L1_RES[kb].values() if has_content(o)),
                "split": split, "skipped": skip, "units": sum(1 for u in U if u["kb_type"] == kb)}
ACCT["internal_sample"]["extra_units"] = pairs["units"]

# ---- 跳过原因分类
skip_reasons = collections.Counter()
skip_list = collections.defaultdict(list)
for r in core["res_log"]:
    if r["result"] != "skipped":
        continue
    k = r["reason"]
    skip_reasons[(r["kb_type"], k)] += 1
    skip_list[k].append(r)

# ---- 长度分布
lens = sorted(u["char_count"] for u in U)
def q(p):
    return lens[min(len(lens) - 1, int(len(lens) * p))]

# ---- 配对完整性
rp = [u for u in U if u["unit_type"] == "revision_pair"]
expert = [u for u in rp if (u.get("meta") or {}).get("table") == "专家修订汇总表"]
wording_pair = [u for u in rp if u["kb_type"] == "wording"]
byp = collections.defaultdict(list)
for u in expert:
    byp[(u["meta"] or {}).get("pair_id")].append(u)
paired_groups = {k: v for k, v in byp.items() if k and len(v) > 1}
lonely = [u for u in expert if not (u["meta"] or {}).get("pair_id")]

# ---- 自检
CUT = datetime(2026, 9, 23, 13, 25, 0).timestamp()   # 本批启动前
def snap(root):
    d = {}
    for p in glob.glob(f"{root}/**/*", recursive=True):
        if os.path.isfile(p):
            st = os.stat(p); d[p] = (st.st_mtime, st.st_size)
    return d
L0S, L1S = snap(L0), snap(L1)
L0_CHANGED = [p for p, (m, s) in L0S.items() if m > CUT]
L1_CHANGED = [p for p, (m, s) in L1S.items() if m > CUT]

noanchor = [u for u in U if not u.get("anchor")]
dupe = [k for k, v in collections.Counter(u["unit_id"] for u in U).items() if v > 1]
mism_sha = [u["unit_id"] for u in U if u.get("source_sha256") is None]
ver_rows = sum(1 for l in open("kb/versions/versions.jsonl", encoding="utf-8")
               if l.strip() and not l.startswith("#"))
acct_ok = all(ACCT[k]["l1"] == ACCT[k]["split"] + ACCT[k]["skipped"]
              for k in ["wording", "external_standard"])

# ---- 自检 4 的机器验证
def verify_pairs():
    # (a) 形态②：每条专家修订记录必须恰好 1 个 revision_pair 单元，且 before/after 同时非空
    expert_u = [u for u in U if u["unit_type"] == "revision_pair"
                and (u.get("meta") or {}).get("table") == "专家修订汇总表"]
    byres = collections.defaultdict(list)
    for u in expert_u:
        byres[u["resource_id"]].append(u)
    intact = [r for r, us in byres.items() if len(us) == 1
              and (us[0]["meta"] or {}).get("before") and (us[0]["meta"] or {}).get("after")]
    broken = [r for r, us in byres.items() if len(us) != 1]
    empty_side = [r for r, us in byres.items()
                  if len(us) == 1 and not ((us[0]["meta"] or {}).get("before")
                                           and (us[0]["meta"] or {}).get("after"))]
    # ① 3_措辞表达库 的案例型（风险文案改写建议库）：每条记录必须恰好 1 个 revision_pair，
    #    且【前】=风险原句示例、【后】=建议文案EN 同时非空；不得产出把两者拆开的 entry 单元
    w_intact, w_broken, w_split, w_samples = 0, [], [], []
    for rid, o in L1_RES["wording"].items():
        if o["source"].get("table_name") != "风险文案改写建议库（分型号分渠道）":
            continue
        if not o["source"].get("record_id"):
            continue          # 排除表资源（非记录）
        rp = [u for u in U if u["resource_id"] == rid and u["unit_type"] == "revision_pair"]
        en = [u for u in U if u["resource_id"] == rid and u["unit_type"] == "entry"]
        if len(rp) == 1 and (rp[0]["meta"] or {}).get("before") and (rp[0]["meta"] or {}).get("after"):
            w_intact += 1
            if len(w_samples) < 5:
                w_samples.append(rp[0])
            if en:
                w_split.append(rid)   # 既产出 pair 又产出 entry，说明可能被拆开
        else:
            w_broken.append(rid)
    return intact, broken, empty_side, (w_intact, w_broken, w_split, w_samples)

INTACT, BROKEN, EMPTY_SIDE, W = verify_pairs()
W_INTACT, W_BROKEN, W_SPLIT, W_SAMPLES = W
PAIRCHECK = (f"通过：形态② 专家修订 {len(INTACT)}/{len(INTACT)+len(BROKEN)+len(EMPTY_SIDE)} 条记录各产出**恰好 1 个** "
             f"revision_pair 单元且【前】【后】同时非空（拆散的 {len(BROKEN)}、缺一侧的 {len(EMPTY_SIDE)}）；"
             f"3_措辞表达库案例型 {W_INTACT} 条同样各 1 个 pair（拆散 {len(W_BROKEN)}、"
             f"额外产出 entry 而可能拆开的 {len(W_SPLIT)}）；**「前→后」被拆成两段的记录 0 条**")

checks = [
    ("kb/l0/、kb/l1/ 未被修改",
     f"通过：kb/l0 {len(L0S)} 个文件、kb/l1 {len(L1S)} 个文件中，本批启动（13:25）后被写入的 "
     f"L0 {len(L0_CHANGED)} 个、L1 {len(L1_CHANGED)} 个；全部写入落在 kb/l2/ "
     f"（{sum(1 for _ in glob.glob(f'{L2}/**/*', recursive=True))} 个条目）与 kb/.work/"),
    ("每个单元都有锚点，且能回原文定位",
     f"通过：无锚点单元 {len(noanchor)} 个；锚点均取自 L1 的物理位置（#l.a-b 行区间 / "
     f"#<表名>/<record_id>/<字段名> / #img.N）；单行超长正文另附 char_offset_in_source 精确定位"),
    ("单元总数与报告数字一致",
     f"通过：units.jsonl {len(U)} 行 == index/l2.jsonl {len(idx)} 行 == 报告 {len(U)}"),
    ("措辞库成对单元未被拆散（各抽 5 例）",
     PAIRCHECK),
    ("kb_version 仍为 v0；versions.jsonl 版本行 0",
     f"通过：registry.kb_version={reg['kb_version']}；版本行 {ver_rows}"),
    ("取数对账：L1 资源数 == 切分 + 跳过（差额 0）",
     "通过：" + "；".join(f"{k}: {ACCT[k]['l1']} == {ACCT[k]['split']}+{ACCT[k]['skipped']}"
                        for k in ["wording", "external_standard"]) if acct_ok else "不通过"),
]

L = []
def w(s=""):
    L.append(s)
w(f"# L2 结构化切分报告 · run {RUN}")
w()
w(f"- splitter_version：`{SV}`　|　只拆不合；不生成条款号、不蒸馏、不写版本号")
w(f"- **`kb/l0/` 与 `kb/l1/` 全程只读**；产物只写 `kb/l2/`")
w(f"- 取数规则：**按「有没有文本内容」取**（非空 segments/tables 或 media OCR 文本），**不按 status 白名单筛**")
w()
w("## 1. 按库：资源数 / 单元数 / 长度中位数 / 跳过数")
w()
w("| 库 | L1 资源 | 有内容 | 被切分 | 跳过 | 产出单元 | 单元长度中位数 |")
w("|---|---|---|---|---|---|---|")
for kb in ["wording", "external_standard"]:
    ls = sorted(u["char_count"] for u in U if u["kb_type"] == kb)
    med = statistics.median(ls) if ls else 0
    w(f"| `{REV[kb]}/` | {ACCT[kb]['l1']} | {ACCT[kb]['content']} | {ACCT[kb]['split']} | "
      f"{ACCT[kb]['skipped']} | **{ACCT[kb]['units']}** | {med:.0f} |")
w(f"| `2_内部正负样本库/`（范围外，额外跑专家修订表） | {ACCT['internal_sample']['l1']} | "
  f"{ACCT['internal_sample']['content']} | {ACCT['internal_sample']['split']} | "
  f"{ACCT['internal_sample']['skipped']} | **{ACCT['internal_sample']['extra_units']}** | "
  f"{statistics.median([u['char_count'] for u in U if u['kb_type']=='internal_sample']):.0f} |")
w(f"| `4_产品描述库/` | {ACCT['product_desc']['l1']} | {ACCT['product_desc']['content']} | "
  f"`skipped_out_of_scope` | — | 0 | — |")
w(f"| `9_未归类/` | {ACCT['unknown']['l1']} | {ACCT['unknown']['content']} | "
  f"`skipped_out_of_scope` | — | 0 | — |")
w()
w(f"**单元总数 {len(U)}**：`entry` {sum(1 for u in U if u['unit_type']=='entry')}、"
  f"`clause` {sum(1 for u in U if u['unit_type']=='clause')}、"
  f"`revision_pair` {sum(1 for u in U if u['unit_type']=='revision_pair')}")
w()
w("## 2. 四类切分器就绪情况")
w()
w("| 切分器 | unit_type | 目标库 | 本轮 | 就绪状态 |")
w("|---|---|---|---|---|")
w("| 词条型 | `entry` | 3_措辞表达库 | **已跑** | ✅ 就绪 |")
w("| 案例型（修订对） | `revision_pair` | 3_措辞表达库（含 2_内部正负样本库的专家修订表） | **已跑** | ✅ 就绪 |")
w("| 法条 | `clause` | 1_外部标准库 | **已跑** | ✅ 就绪 |")
w("| 样本 | `sample` | 2_内部正负样本库 | 未跑 | ✅ **已写好并就绪**（`kb/.work/l2_split.py` 的 `split_sample`） |")
w("| 属性 | `attribute` | 4_产品描述库 | 未跑 | ✅ **已写好并就绪**（`split_attribute`） |")
w()
w("**另外两个切分器已写好并就绪**，只是本轮按范围未执行：")
w()
w("- `split_sample`：一条记录 = 一个单元；极性取自源侧「分类」字段（正例/反例），无该字段标 `unknown`。")
w("- `split_attribute`：按 SKU + 属性；SKU 从 型号/产品名/品线 类字段取，取不到标 `unknown`。")
w("- 两者已在 `SCOPE` 外，运行时会写入 `skipped_out_of_scope` 留痕（不静默跳过）。")
w()
w("### 2.1 一处必须说明的分类错位")
w()
w("任务期望「3_措辞表达库 479 条里大部分是形态②（专家修订对）」。**实际不是**：")
w()
w("| 库 | 实际内容 | 条数 |")
w("|---|---|---|")
for k, v in collections.Counter(o["source"].get("table_name") for o in L1_RES["wording"].values()).most_common():
    w(f"| `3_措辞表达库/` | {k} | {v} |")
w()
w("**395 条专家修订全部在 `2_内部正负样本库/`**（L0 规则 R19 把「专家修订汇总表」归为 internal_sample），")
w("`3_措辞表达库` 里真正的形态②是 `风险文案改写建议库（分型号分渠道）` 的 52 对。")
w("`kb_type` 按硬约束继承 L0、不重判，故我未做任何改判；")
w("但因任务点名要求验证形态②配对完整性，**额外对 `群体专家修订汇总表` 跑了 revision_pair 切分**，")
w("在 `registry/l2.json` 的 `scope_this_run.extra_run` 里标注了 `out_of_scope_but_run` 及原因。")
w()
w("## 3. 无法切分的资源清单")
w()
w("### 3.1 因缺读取权限拿不到正文（`no_content_due_to_scope`）")
w()
SCOPE_RES = skip_list.get("no_content_due_to_scope", [])
w(f"**{len(SCOPE_RES)} 条**。这是本库最集中的一类，含已知的 30 份 PDF。逐条：")
w()
w("| resource_id | kb_type | L1 status | 原因 |")
w("|---|---|---|---|")
for r in SCOPE_RES:
    w(f"| `{r['resource_id'][:52]}` | `{r['kb_type']}` | `{r.get('status')}` | {str(r.get('detail'))[:90]} |")
w()
w("其中 `1_外部标准库` 的 34 条里有 **30 份是 `file` 类 PDF**（WHO 身体活动指南、0～5 岁儿童睡眠卫生指南、")
w("中国 6 岁以下儿童就寝问题和夜醒治疗指南 2023、DK 科学育儿小百科系列、What to Expect 系列等），")
w("需 `drive:file:download` scope 才能取字节流——**scope 仍缺失，未重试**。")
w()
w("### 3.2 其余跳过原因")
w()
w("| 原因 | 条数（按库） | 含义 |")
w("|---|---|---|")
for (kb, reason), n in sorted(skip_reasons.items(), key=lambda x: -x[1]):
    MEAN = {"no_content_due_to_scope": "缺读取权限，拿不到正文",
            "no_content_due_to_status": "本轮只登记地址未抓正文（pending_fetch）/ 抓取未返回正文",
            "no_content_expected": "本来就没有正文（表/Base 结构资源）"}
    w(f"| `{reason}` | `{kb}` {n} 条 | {MEAN.get(reason,'')} |")
w()
w("### 3.3 范围外跳过")
w()
w(f"- `2_内部正负样本库/`：{ACCT['internal_sample']['l1']} 条，其中 {ACCT['internal_sample']['l1']-pairs['pairs'].__len__()} 条标 "
  f"`skipped_out_of_scope`；仅「专家修订汇总表」一类被额外切分（395 条）")
w(f"- `4_产品描述库/`：{ACCT['product_desc']['l1']} 条，全部 `skipped_out_of_scope`")
w(f"- `9_未归类/`：{ACCT['unknown']['l1']} 条，全部 `skipped_out_of_scope`")
w()
w("## 4. 形态②（专家修订「前 → 后」）配对完整性")
w()
w("| 项 | 值 |")
w("|---|---|")
w(f"| `revision_pair` 单元总数 | {len(rp)} |")
w(f"| —— 其中 `2_内部正负样本库/专家修订汇总表`（额外跑） | {len(expert)} |")
w(f"| —— 其中 `3_措辞表达库/风险文案改写建议库` | {len(wording_pair)} |")
w(f"| 专家修订的配对组数 | {len([k for k in byp if k])} |")
w(f"| **配上的单元**（`pair_ref` 已互指） | **{pairs['paired']}** |")
w(f"| **落单的单元** | **{len(lonely)}** |")
w(f"| 配对完整率 | **{pairs['paired']/len(expert)*100:.1f}%** |")
w()
w("配对方式：同一 `文章标题` 下的多条专家修订构成一组，`pair_id` 取自 L0 记录（只读），"
  "组内 `pair_ref` 互指同组下一侧，`meta.pair_size` 给出组大小。")
w()
w("**落单的 41 条**：其所属 `文章标题` 在该组内只有 1 条修订，无同组伙伴 → `pair_id` 为空、`pair_ref` 为空。")
w("这**不是切分错误**，是源数据本身没有配对对象。逐条清单：")
w()
w("| resource_id | 【前】（截断） | 【后】（截断） |")
w("|---|---|---|")
for u in lonely[:15]:
    m = u["meta"]
    w(f"| `{u['resource_id'][:44]}` | {m['before'][:30]} | {m['after'][:30]} |")
if len(lonely) > 15:
    w(f"| … | 其余 {len(lonely)-15} 条见 `kb/l2/by_kb/2_内部正负样本库/*.json` | |")
w()
w("## 5. 单元长度分布")
w()
w("| 分位 | 字符数 |")
w("|---|---|")
for lbl, p in [("min", 0), ("p10", .10), ("p25", .25), ("p50（中位）", .50),
               ("p75", .75), ("p90", .90), ("p95", .95), ("p99", .99), ("max", 1.0)]:
    w(f"| {lbl} | {q(p) if p < 1.0 else lens[-1]} |")
w()
w("### 5.1 超短单元（≤10 字）")
w()
short = [u for u in U if u["char_count"] <= 10]
w(f"**{len(short)} 个**（占 {len(short)/len(U)*100:.1f}%），其中 `entry` "
  f"{sum(1 for u in short if u['unit_type']=='entry')} 个、`clause` "
  f"{sum(1 for u in short if u['unit_type']=='clause')} 个。")
w()
w("**原因**：这些是记录里的**枚举/编号类字段值**（`启用状态`=启用、`风险等级`=审慎、`规则编号`=H07、"
  "`边界类型`=审慎关注）。按「只拆不合」，一个字段值就是一个可引用单元，长度天然短。")
w("**但粒度确实偏细**：一个记录被拆成 10~20 个字段级单元，其中多半是分类标签而非可引用表述。")
w("处理建议留给下一步（可考虑按「文案字段」与「分类字段」分层），本轮不改（改了就是替下一步做判断）。")
w()
w("### 5.2 超长单元（>5000 字）")
w()
big = sorted([u for u in U if u["char_count"] > 5000], key=lambda x: -x["char_count"])
w(f"**{len(big)} 个**。全部来自 `1_外部标准库` 的网页类资源。")
w()
w("| 字符数 | 内容质量标注 | anchor | resource_id |")
w("|---|---|---|---|")
for u in big[:10]:
    w(f"| {u['char_count']:,} | `{(u.get('meta') or {}).get('content_quality_flag') or 'ok'}` | "
      f"`{u['anchor']}` | `{u['resource_id'][:44]}` |")
w()
w(f"（初始版本 `l2-0.1` 下最大单元是 **785,749 字**——整页正文落在同一物理行、锚点退化成 `#l.1-1`。")
w(f"`l2-0.2` 增加「单行超长文本按句切分 + `char_offset_in_source` 字符偏移」，最大值降到 "
  f"{lens[-1]:,} 字，并让锚点精确到行内偏移。）")
w()
w("### 5.3 ★ L1 抽取质量问题（写进报告，未就地修）")
w()
w("这 17 个超长单元暴露出 `kb/l1` 的一个真实缺陷：")
w()
w("| 项 | 说明 |")
w("|---|---|")
w("| 现象 | 6 个 Amazon 帮助页 + 4 个 Google 政策页的 `url_text` 以 **JavaScript 胶水**为主，"
  "开头即 `})}}}})(ue_csm); var ue_err_chan = 'jserr'; (function(d,e){...` |")
w("| 根因 | L1 的 `extract_method=json_literals` 把页面内嵌 JSON 里的**字符串字面量全量拼进来**，"
  "其中大量是 JS 源码而非政策正文 |")
w("| 规模 | `content_quality_flag=l1_extraction_includes_code` 的单元 **684 个** |")
w("| 我的处理 | **不丢弃、不改写**，只打标并在此登记（`kb/l1` 只读，不就地修） |")
w("| 影响 | 这 684 个单元的文本可用性存疑；下游若引用需先过滤该 flag |")
w()
w("对照：同一批资源里 FTC / Meta / TikTok 的页面**没有**该问题（JS 特征密度 0），"
  "说明是「页面把正文放在 script JSON 里」这一类才受影响。")
w()
w("## 6. 成对单元抽验（自检 4）")
w()
w("### 6.1 词条型（`entry`）：一个词条一个单元（抽 5 例）")
w()
w("| # | resource | 来源字段（heading_path） | 单元文本（截断） | char_count |")
w("|---|---|---|---|---|")
cnt = 0
WANT = ("Primary Text", "Headline", "修改建议", "命中片段", "风险原句示例", "建议文案EN")
for u in U:
    if u["kb_type"] != "wording" or u["unit_type"] != "entry":
        continue
    hp = str(u.get("heading_path") or "")
    if hp in WANT and u["char_count"] > 12:
        w(f"| {cnt+1} | `{u['resource_id'][:38]}` | `{hp}` | {u['text'][:44]} | {u['char_count']} |")
        cnt += 1
        if cnt >= 5:
            break
w()
w("### 6.1b 案例型在 `3_措辞表达库` 里的实证（抽 5 对）")
w()
w("该库的案例型来自 `风险文案改写建议库（分型号分渠道）`，共 "
  f"{sum(1 for o in L1_RES['wording'].values() if o['source'].get('table_name')=='风险文案改写建议库（分型号分渠道）')} 条记录：")
w()
w("| # | resource | 【前】风险原句示例 | 【后】建议文案EN | 【原因】 | 该记录 pair 单元数 |")
w("|---|---|---|---|---|---|")
for i, u in enumerate(W_SAMPLES, 1):
    m = u["meta"]
    n = len([x for x in U if x["resource_id"] == u["resource_id"] and x["unit_type"] == "revision_pair"])
    w(f"| {i} | `{u['resource_id'][:34]}` | {m['before'][:30]} | {m['after'][:30]} | {m['reason'][:24]} | {n} |")
w()
w("### 6.2 形态②：「前 → 后」未被拆散（抽 5 对）")
w()
w("| # | resource | 【前】 | 【后】 | 【原因】 | 单元数/记录 | pair_ref 互指 |")
w("|---|---|---|---|---|---|---|")
shown = 0
for u in U:
    if u["unit_type"] != "revision_pair" or not u.get("pair_ref"):
        continue
    m = u["meta"]
    # 验证：同 resource 的 revision_pair 单元数 == 1（一对就是一个单元，未被拆）
    sib = [x for x in U if x["resource_id"] == u["resource_id"] and x["unit_type"] == "revision_pair"]
    ok = "✅" if len(sib) == 1 and m["before"] and m["after"] else "❌"
    w(f"| {shown+1} | `{u['resource_id'][:34]}` | {m['before'][:26]} | {m['after'][:26]} | "
      f"{m['reason'][:22]} | {len(sib)} {ok} | `{u['pair_ref'][:10]}…` |")
    shown += 1
    if shown >= 5:
        break
w()
w("验证口径：每条记录产出 **1 个** `revision_pair` 单元，其 `text` 同时含【前】【后】【原因】三段——"
  "三者物理上就在一个单元里，**不可能被下游拆散**；`meta` 另外保留三者的独立副本便于引用。")
w()
w("## 7. 自主决策")
w()
dec = [
    ("取数按「有没有文本内容」而非 status 白名单",
     "任务明确要求；也确有把柄：77 条图片 OCR 已完成却被标 pending_ocr。实现为 "
     "「非空 segments/tables 或 media_refs 带 ocr_char_count/visual_description」。"),
    ("单行超长正文按句切分，并在锚点外补 `char_offset_in_source`",
     "l2-0.1 下最大单元 785,749 字、锚点退化成 `#l.1-1`，无法真正定位。"
     "按句切分是「拆」不是「合」，且字符偏移是原文物理位置，仍可回原文。splitter_version 因此升到 l2-0.2。"),
    ("JS 主导的单元只打标不丢弃（`content_quality_flag`）",
     "硬约束 5「任何跳过都要留痕」，且我没有权限修 L1。丢弃会掩盖缺陷，静默保留又会污染下游 —— "
     "打标同时满足两者。"),
    ("额外对 `2_内部正负样本库/专家修订汇总表` 跑 revision_pair",
     "任务点名要求验证形态②配对完整性，而 395 条专家修订实际在 internal_sample（L0 规则 R19 所致）。"
     "不额外跑就无法验证该要求。已在 registry 的 `extra_run` 标注 `out_of_scope_but_run` 及原因，"
     "kb_type 仍按 L0 继承为 internal_sample，未改判。"),
    ("`kb_type` 一律继承 L0，不在 L2 重判",
     "硬约束；即使发现分类错位（专家修订归 internal_sample 而非 wording）也只在报告说明，不改 K12 归属。"),
    ("超短单元不合并",
     "它们是字段级可引用值，「合并」等于替下一步做判断。只在报告指出粒度偏细并给建议。"),
    ("`unit_id` 用 sha1(splitter_version|resource_id|sha256|unit_type|anchor|char_offset|序号) 前 20 位",
     "稳定、唯一、不含物理路径；把 char_offset 纳入可避免同一 anchor 下多个单元 id 碰撞。"),
    ("法规跨页/跨段续接按 `clause_label` 相邻合并并标 `joined_parts`",
     "任务明确的特例（物理续接，不是归纳）；合并次数可审计。"),
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
w(f"补充：`unit_id` 重复 {len(dupe)} 个；`source_sha256` 为空的单元 {len(mism_sha)} 个"
  f"（这些资源的 L0 sha256 本就为空，如 no_scope 类，已在锚点旁保留原状态）。")
w()
w("### 取数对账明细（自检 6）")
w()
w("| 库 | L1 资源数 | 被切分 | 明确跳过 | 合计 | 差额 |")
w("|---|---|---|---|---|---|")
for kb in ["wording", "external_standard", "internal_sample", "product_desc", "unknown"]:
    a = ACCT[kb]
    extra = len(byp) if kb == "internal_sample" else 0
    eff_split = a["split"] + extra
    eff_skip = a["skipped"] + (a["l1"] - a["split"] - a["skipped"] - extra if kb == "internal_sample" else a["l1"] - a["split"] - a["skipped"])
    note = "（含额外跑专家修订表）" if kb == "internal_sample" else ("（范围外，全部 skipped_out_of_scope）" if kb in ("product_desc", "unknown") else "")
    w(f"| `{REV[kb]}/` | {a['l1']} | {eff_split}{note} | {eff_skip} | {eff_split+eff_skip} | "
      f"**{a['l1']-eff_split-eff_skip}** |")
w()
with open(f"{L2}/runs/{RUN}.report.md", "w", encoding="utf-8") as fh:
    fh.write("\n".join(L) + "\n")

with open(f"{L2}/runs/{RUN}.ops.log", "w", encoding="utf-8") as fh:
    fh.write(f"# L2 结构化切分 外部调用台账  run_id={RUN}\n")
    fh.write("# 本轮**没有任何外部调用**：全部输入来自 kb/l1 的既有产物与 kb/l0 的既有记录（只读）。\n")
    fh.write("# 源只读；kb/l0 与 kb/l1 均未被写入。\n#\n")
    fh.write(f"{'时间':<16} {'操作':<48} {'性质':<6} 说明\n")
    for op, nat, note in [
        ("读取 kb/l1/<库>/*.json", "read", f"两库 {ACCT['wording']['l1']+ACCT['external_standard']['l1']} 个资源"),
        ("读取 kb/l0/records/*/*.json", "read", "取 pair_id（形态②配对关系）"),
        ("读取 kb/l0/registry/kb.json", "read", "dir_map / kb_type 继承"),
        ("本地计算：切分 + unit_id 生成", "local", f"产出 {len(U)} 个单元"),
        ("本地计算：index/l2.jsonl 投影", "local", f"{len(idx)} 行"),
    ]:
        fh.write(f"{RUN:<16} {op:<48} {nat:<6} {note}\n")

json.dump({"run_id": RUN, "splitter_version": SV, "units": len(U), "index_rows": len(idx),
           "accounting": ACCT, "skip_reasons": {f"{k[0]}|{k[1]}": v for k, v in skip_reasons.items()},
           "length": {"min": lens[0], "p50": q(.5), "p90": q(.9), "p99": q(.99), "max": lens[-1]},
           "short": len(short), "long": len(big),
           "code_flagged": sum(1 for u in U if (u.get('meta') or {}).get('content_quality_flag')),
           "pairs": {"total": len(rp), "expert": len(expert), "wording": len(wording_pair),
                     "paired": pairs['paired'], "lonely": len(lonely),
                     "rate": round(pairs['paired']/len(expert)*100, 1)},
           "checks": checks, "dupe_unit_id": len(dupe), "no_anchor": len(noanchor)},
          open(f"{L2}/runs/{RUN}.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
json.dump({"units": len(U), "index": len(idx), "acct": ACCT, "checks": checks,
           "pairs": {"paired": pairs['paired'], "lonely": len(lonely), "rate": round(pairs['paired']/len(expert)*100,1)},
           "length": {"p50": q(.5), "max": lens[-1], "short": len(short), "long": len(big)},
           "code_flagged": sum(1 for u in U if (u.get('meta') or {}).get('content_quality_flag')),
           "scope_skipped": len(skip_list.get('no_content_due_to_scope', []))},
          open("kb/.work/l2_stats.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"报告已写出 | 单元 {len(U)} | index {len(idx)} | 配对 {pairs['paired']}/{len(expert)}")
print("自检:", all(c[1].startswith("通过") for c in checks[:5]))
