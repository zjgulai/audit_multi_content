#!/usr/bin/env python3
"""L3 蒸馏：证据 → 候选规则。
方法论来自已安装的 knowledge-distillation skill（源事实→归一化证据→模式→发现→含义，全程可追溯）。
本文件规格优先于 skill 的通用建议。
kb/l0、kb/l1、kb/l2 全程只读；产物只写 kb/l3。
"""
import json, os, re, hashlib, collections, sys, glob

RUN = sys.argv[1]
L0, L1, L2, L3 = "kb/l0", "kb/l1", "kb/l2", "kb/l3"
DISTILLER_VERSION = "l3-0.1"
KB_VERSION = "v0"

os.makedirs(f"{L3}/candidates", exist_ok=True)
os.makedirs(f"{L3}/canonical", exist_ok=True)
os.makedirs(f"{L3}/index", exist_ok=True)
os.makedirs(f"{L3}/registry", exist_ok=True)
os.makedirs(f"{L3}/runs", exist_ok=True)

U = [json.loads(l) for l in open(f"{L2}/units.jsonl", encoding="utf-8") if l.strip()]
l0reg = json.load(open(f"{L0}/registry/kb.json", encoding="utf-8"))
L0_FR = l0reg["field_roles"]

# ============================================================ 字段角色补全
# L0 的 field_roles 只覆盖 44 个字段（首次落库只登记了入口 Base 的 4 张表 + 3 个关联 Base 的部分），
# L2 出现的字段远多于此。为让「按 field_roles 过滤元数据单元」可执行，补全覆盖 L2 全部字段。
# 判定依据：字段是否承载「可引用的表述/理由/条件」，vs「分类标签/编号/统计/行政状态」。
CONTENT_FIELDS = {
    # —— 文案本体
    "Primary Text", "Headline", "广告名称",
    # —— 命中/判定的表述与理由
    "命中片段", "命中原因", "命中规则", "修改建议",
    "边界内容", "检测关键词", "豁免词", "触发原因", "正则表达式",
    "判定理由", "建议表达（合规话术）", "避免条件/限定要求",
    "风险原句示例", "建议文案EN", "中文释义", "风险表达模式",
    "规则依据与边界", "卖点依据（产品功能）", "小语种参考 FR/DE/ES/IT", "字符数自检",
    "修订位置（原文引用）", "修订内容", "修订原因",
    "备注（如处理结果/建议）", "具体原因/分析", "原文逐字", "对判定的意义",
    "中文摘要", "关联现网规则", "条款位置", "要包含什么",
    "需向对接人收集的问题", "建议字段/材料", "资料名称",
}
METADATA_FIELDS = {
    # —— 分类标签 / 编号 / 统计 / 行政状态（任务点名的正是这类）
    "启用状态", "风险等级", "规则编号", "映射规则编号", "卖点ID", "外部广告ID", "建议编号",
    "处理状态", "抓取状态", "投放状态", "使用状态", "灯色状态", "状态", "分类", "素材类型",
    "边界类型", "判断方式", "表达类型", "文案位置", "文案语种", "渠道", "渠道/市场", "平台",
    "适用型号", "适用产品", "适用品类", "适用渠道", "投放地区", "地区", "主题场景", "阶段",
    "语言", "品线", "广告类型", "广告账号", "广告组", "广告系列Campaign", "数据日期",
    "近7天展示", "近7天点击", "近7天费用USD", "上传人员", "是否需要授权（法务负责）",
    "是否完成医学审查（医疗确认）", "是否完成合规审查（法务确认）", "权威层级（医疗确认）",
    "资料类型(医疗确认)", "适用对象", "发布日期", "父记录", "来源", "文件/链接",
    "知识库", "知识库分类", "材料审核状态", "From", "细分", "备注", "更新频率", "agent使用范围", "负责人",   # 细分=该字段的旧名（飞书现名 备注，field_id fldn4bB 同源）；更新频率 此前漏列
    # L0 field_roles 里显式标为 status / other / link 的，一律视为元数据
    *[k for k, v in L0_FR.items() if v in ("status", "other", "link", "attachment")],
}

def field_role(name):
    if name in CONTENT_FIELDS:
        return "content"
    if name in METADATA_FIELDS:
        return "metadata"
    return "unknown"

# ============================================================ 两道过滤 + 对账
def quality_flagged(u):
    return bool((u.get("meta") or {}).get("content_quality_flag"))

def unit_field(u):
    if u["unit_type"] == "entry":
        return u.get("heading_path")
    if u["unit_type"] == "revision_pair":
        return "(修订对)"
    return None

FILTER = collections.Counter()
filtered = collections.defaultdict(list)
kept = []
for u in U:
    kb = u["kb_type"]
    if kb not in ("wording", "external_standard", "internal_sample"):
        FILTER[(kb, "out_of_scope_kb")] += 1
        filtered["out_of_scope_kb"].append(u)
        continue
    if kb == "internal_sample" and (u.get("meta") or {}).get("table") != "专家修订汇总表":
        FILTER[(kb, "out_of_scope_table")] += 1
        filtered["out_of_scope_table"].append(u)
        continue
    # 过滤 1：元数据字段
    role = None
    if u["unit_type"] == "entry":
        role = field_role(u.get("heading_path"))
        if role != "content":
            reason = "metadata" if role == "metadata" else "metadata_unknown_field"
            FILTER[(kb, reason)] += 1
            filtered[reason].append(u)
            continue
    # 过滤 2：content_quality_flag
    if quality_flagged(u):
        FILTER[(kb, "quality_flag")] += 1
        filtered["quality_flag"].append(u)
        continue
    kept.append(u)

print(f"L2 单元 {len(U)} → 可用 {len(kept)}（过滤 {len(U)-len(kept)}）")
for k, v in sorted(FILTER.items(), key=lambda x: -x[1]):
    print(f"   {k[0]:18s} {k[1]:24s} {v}")

# ============================================================ 归一化证据：按记录聚合
by_rec = collections.defaultdict(lambda: collections.defaultdict(list))
for u in kept:
    by_rec[(u["kb_type"], u["resource_id"])][u["unit_type"]].append(u)

def fv(units, name):
    for u in units:
        if u.get("heading_path") == name:
            return u
    return None

def j(us):
    """unit_id 集合的规范化 hash"""
    ids = sorted(u["unit_id"] for u in us)
    return hashlib.sha1("|".join(ids).encode()).hexdigest()

def ev_ref(u):
    return {"unit_id": u["unit_id"], "anchor": u["anchor"], "source_sha256": u.get("source_sha256")}

def mk_rule_id(kb, us):
    return "r-" + hashlib.sha1(f"{kb}|{j(us)}".encode()).hexdigest()[:16]

rules, rejected = [], []

# ============================================================ 形态①：词条型（广告文案明细）
# 单元三元组：命中片段（禁用/风险片段）→ 修改建议（替换）＋ 命中原因（依据）＋ 风险等级（分级）
for (kb, rid), grp in sorted(by_rec.items()):
    ents = grp.get("entry", [])
    if not ents:
        continue
    table = ents[0].get("heading_path") and None
    # 判定是否广告文案明细（有命中片段/Primary Text 字段）
    hit = fv(ents, "命中片段")
    fix = fv(ents, "修改建议")
    why = fv(ents, "命中原因")
    risk = fv(ents, "风险等级")
    if hit or fix:
        if not (hit and fix):
            rejected.append({"kind": "entry_pair_incomplete", "resource_id": rid, "kb_type": kb,
                             "reason": "缺 命中片段 或 修改建议，无法构成「禁用→替换」对",
                             "have": [u.get("heading_path") for u in ents]})
            continue
        ev = [x for x in (hit, fix, why, risk) if x]
        text = f"禁用表达：{hit['text']}；建议替换：{fix['text']}"
        if why:
            text += f"；依据：{why['text']}"
        rules.append(dict(
            rule_id=mk_rule_id("wording_entry", ev), kb_type="wording", kb_version=KB_VERSION,
            article_no="", form="entry",
            rule_text=text,
            forbidden_expression=hit["text"], suggested_replacement=fix["text"],
            reason=(why["text"] if why else ""),
            p_level=("P0" if risk and "高危" in risk["text"] else ("P1" if risk and "审慎" in risk["text"] else "P2")),
            risk_level=(risk["text"] if risk else "unknown"),
            scope={"platform": (fv(ents, "平台") or {}).get("text"),
                   "product_line": (fv(ents, "品线") or {}).get("text"),
                   "region": (fv(ents, "投放地区") or {}).get("text"),
                   "lang": (fv(ents, "文案语种") or {}).get("text")},
            anchor=hit["anchor"], evidence_units=[ev_ref(x) for x in ev],
            evidence_digest=j(ev), support_count=len(ev),
            evidence_level="synthesis",
            effective_from="", effective_to="", owner="", status="provisional",
            verification=("待验证" if len(ev) == 1 else "已归纳"),
            supersedes=[], superseded_by=[], superseded_at="",
        ))
        continue
    # 形态①b：边界规则（品线内容边界规则库 / W1卖点表达边界）：边界内容 + 检测关键词 + 豁免词
    bnd = fv(ents, "边界内容")
    if bnd:
        kw = fv(ents, "检测关键词")
        ex = fv(ents, "豁免词")
        reg = fv(ents, "正则表达式")
        sug = fv(ents, "建议表达（合规话术）")
        rls = fv(ents, "规则依据与边界")
        ev = [x for x in (bnd, kw, ex, reg, sug, rls) if x]
        text = f"边界：{bnd['text']}"
        if kw:
            text += f"；触发词：{kw['text']}"
        if ex:
            text += f"；豁免：{ex['text']}"
        if sug:
            text += f"；建议表达：{sug['text']}"
        rules.append(dict(
            rule_id=mk_rule_id("wording_boundary", ev), kb_type="wording", kb_version=KB_VERSION,
            article_no="", form="entry",
            rule_text=text,
            forbidden_expression=(kw["text"] if kw else bnd["text"][:80]),
            suggested_replacement=(sug["text"] if sug else ""),
            reason=(rls["text"] if rls else ""),
            p_level="P1", risk_level="unknown",
            scope={"product_line": (fv(ents, "适用产品") or {}).get("text")},
            anchor=bnd["anchor"], evidence_units=[ev_ref(x) for x in ev],
            evidence_digest=j(ev), support_count=len(ev),
            evidence_level="synthesis",
            effective_from="", effective_to="", owner="", status="provisional",
            verification=("待验证" if len(ev) == 1 else "已归纳"),
            supersedes=[], superseded_by=[], superseded_at="",
        ))
        continue
    # 形态①c：W1 卖点表达边界（建议表达 + 判定理由 + 避免条件）
    sug2 = fv(ents, "建议表达（合规话术）")
    if sug2:
        jr = fv(ents, "判定理由")
        av = fv(ents, "避免条件/限定要求")
        ev = [x for x in (sug2, jr, av) if x]
        text = f"建议表达：{sug2['text']}"
        if av:
            text += f"；限定要求：{av['text']}"
        if jr:
            text += f"；判定理由：{jr['text']}"
        rules.append(dict(
            rule_id=mk_rule_id("wording_saythis", ev), kb_type="wording", kb_version=KB_VERSION,
            article_no="", form="entry",
            rule_text=text, forbidden_expression="", suggested_replacement=sug2["text"],
            reason=(jr["text"] if jr else ""), p_level="P1", risk_level="unknown", scope={},
            anchor=sug2["anchor"], evidence_units=[ev_ref(x) for x in ev],
            evidence_digest=j(ev), support_count=len(ev), evidence_level="synthesis",
            effective_from="", effective_to="", owner="", status="provisional",
            verification=("待验证" if len(ev) == 1 else "已归纳"),
            supersedes=[], superseded_by=[], superseded_at="",
        ))
        continue

# ============================================================ 形态②：案例型（修订对）
for (kb, rid), grp in sorted(by_rec.items()):
    for u in grp.get("revision_pair", []):
        m = u.get("meta") or {}
        if not (m.get("before") and m.get("after")):
            rejected.append({"kind": "revision_pair_incomplete", "resource_id": rid, "kb_type": kb,
                             "reason": "修订对缺「前」或「后」，不构成可判定规则",
                             "before_len": len(m.get("before") or ""), "after_len": len(m.get("after") or "")})
            continue
        ev = [u]
        rules.append(dict(
            rule_id=mk_rule_id("wording_revision", ev), kb_type="wording", kb_version=KB_VERSION,
            article_no="", form="revision_pair",
            rule_text=f"原表述：{m['before']}；修订为：{m['after']}"
                      + (f"；修订原因：{m['reason']}" if m.get("reason") else ""),
            forbidden_expression=m["before"], suggested_replacement=m["after"],
            reason=(m.get("reason") or ""),
            p_level="P1", risk_level="unknown",
            scope={"source_table": m.get("table")},
            anchor=u["anchor"], evidence_units=[ev_ref(u)],
            evidence_digest=j(ev), support_count=len(ev), evidence_level="observation",
            effective_from="", effective_to="", owner="", status="provisional",
            verification="待验证",
            pair_ref=u.get("pair_ref") or "",
            supersedes=[], superseded_by=[], superseded_at="",
        ))

# ============================================================ 外部标准库
ext = collections.defaultdict(lambda: collections.defaultdict(list))
for u in kept:
    if u["kb_type"] == "external_standard":
        ext[u["resource_id"]][u["unit_type"]].append(u)
for rid, grp in sorted(ext.items()):
    cl = grp.get("clause", [])
    if not cl:
        rejected.append({"kind": "no_clause_text", "resource_id": rid, "kb_type": "external_standard",
                         "reason": "该资源在 L1/L2 未产出可用条款文本（正文为页面脚本或编码载荷），"
                                   "无法产出「判定条件 + 阈值/词表」形态的规则"})
        continue
    for u in cl:
        rejected.append({"kind": "clause_not_actionable", "resource_id": rid,
                         "kb_type": "external_standard", "unit_id": u["unit_id"],
                         "anchor": u["anchor"],
                         "reason": "条款文本不可判定：非自然语言条款（页面脚本 / 编码载荷），"
                                   "无法给出判定条件与阈值"})

# ============================================================ 幂等台账
MAN = f"{L3}/manifest_l3.jsonl"
prev = {}
if os.path.exists(MAN):
    for l in open(MAN, encoding="utf-8"):
        if l.strip():
            r = json.loads(l)
            prev[r["rule_id"]] = r
new_rules, unchanged = [], 0
for r in rules:
    old = prev.get(r["rule_id"])
    if old and old.get("evidence_digest") == r["evidence_digest"]:
        unchanged += 1
        continue
    new_rules.append(r)

# ============================================================ 落盘
with open(f"{L3}/candidates/rules.jsonl", "w", encoding="utf-8") as fh:
    for r in rules:
        fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
with open(f"{L3}/rejected.jsonl", "w", encoding="utf-8") as fh:
    for r in rejected:
        fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
open(f"{L3}/canonical/rules.jsonl", "w", encoding="utf-8").close()
with open(f"{L3}/index/l3.jsonl", "w", encoding="utf-8") as fh:
    for r in rules:
        fh.write(json.dumps({"rule_id": r["rule_id"], "kb_type": r["kb_type"],
                             "p_level": r["p_level"], "support_count": r["support_count"],
                             "anchor": r["anchor"]}, ensure_ascii=False, sort_keys=True) + "\n")
with open(MAN, "a", encoding="utf-8") as fh:
    for r in rules:
        fh.write(json.dumps({"rule_id": r["rule_id"], "evidence_digest": r["evidence_digest"],
                             "support_count": r["support_count"], "status": "provisional",
                             "distiller_version": DISTILLER_VERSION, "observed_at": RUN},
                            ensure_ascii=False, sort_keys=True) + "\n")

# ============================================================ registry
reg = {
    "distiller_version": DISTILLER_VERSION,
    "kb_version": KB_VERSION,
    "skill_source": {
        "name": "knowledge-distillation",
        "origin": "https://github.com/volcengine/OpenViking",
        "installed_at": "~/.dsh/skills/knowledge-distillation/SKILL.md",
        "read": True,
        "adopted": [
            "源事实 → 归一化证据 → 模式 → 发现 → 含义，每一步可追溯（evidence_level 字段落地）",
            "产出不得是目录或来源摘要堆叠 —— 每条规则是一句可判定的结论",
            "证据分级：Observation / Synthesis / Inference / Hypothesis，不得把推断写成观测事实",
            "抽样前先勘查来源、记录来源谱系、避免把同一上游的重复说法当成独立佐证",
            "摘录必须逐字，不转述不概括（本步用 unit_id 指向 L2 原文单元保证）",
        ],
        "skipped_ov_steps": "该 skill 依赖 OpenViking CLI（ov add-resource / ov add-skill / ov compile）；"
                            "本机未安装，按任务要求不安装、不调用，相关步骤一律跳过，不计为未完成项",
        "effective": "skill 方法论 + 本文件规格；冲突时以本文件规格为准",
    },
    "classification_note": {
        "table": "专家修订汇总表",
        "l0_kb_type": "internal_sample",
        "used_as": "wording",
        "why": "该表形态是「修订前 → 后」成对语料，属措辞类素材；本轮按措辞素材蒸馏，"
               "但不修改 L0 的分类（kb_type 字段仍按 L0 继承）",
        "status": "待确认",
    },
    "filter_rules": {
        "step1_metadata": {
            "how": "按 kb/l0/registry/kb.json 的 field_roles 过滤；只保留「文案/表述类字段」产生的单元",
            "gap": "L0 的 field_roles 只覆盖 44 个字段（首次落库只登记了入口 Base 4 张表 + 部分关联 Base），"
                   "L2 实际出现 70+ 字段；因此本步补全了一份覆盖 L2 全部字段的角色表，"
                   "依据是字段是否承载「可引用的表述/理由/条件」",
            "content_fields_count": len(CONTENT_FIELDS), "metadata_fields_count": len(METADATA_FIELDS),
        },
        "step2_quality": {"how": "排除 meta.content_quality_flag 非空的单元（L1 把内嵌 JSON 的 JS 当正文）"},
    },
    "rule_forms": {
        "wording": ["entry（禁用表达 + 建议替换 + 依据）", "revision_pair（原表述 + 修订后 + 修订原因）"],
        "external_standard": ["{判定条件, 阈值/词表, 条款锚点, 生效期}"],
    },
    "canonical_policy": "kb/l3/canonical/rules.jsonl 本步只创建空文件；候选→定稿是独立动作（走抽查），"
                        "晋升产生新的定稿记录，不是改名。",
    "supersedes_policy": "rule_id 由 (kb_type + 依据 unit_id 集合 hash) 生成，源不变则 rule_id 不变；"
                         "规则变更时新规则在 supersedes 列出旧 rule_id，旧规则保留并追加 superseded_by/superseded_at；"
                         "检索默认只用未被 superseded_by 的规则。",
    "idempotency": {"key": "rule_id", "unchanged_cond": "evidence_digest 未变 → unchanged，跳过"},
    "citation_discipline": "每条规则的依据是 unit_id + anchor + source_sha256；不引用裸 URL；摘录逐字。",
}
with open(f"{L3}/registry/l3.json", "w", encoding="utf-8") as fh:
    json.dump(reg, fh, ensure_ascii=False, indent=2)
    fh.write("\n")

json.dump({"kept": len(kept), "filtered": {f"{k[0]}|{k[1]}": v for k, v in FILTER.items()},
           "rules": len(rules), "new": len(new_rules), "unchanged": unchanged,
           "rejected": len(rejected),
           "forms": dict(collections.Counter(r.get("form") for r in rules)),
           "rules_by_kb": dict(collections.Counter(r["kb_type"] for r in rules)),
           "support": dict(collections.Counter(r["support_count"] for r in rules)),
           "rejected_kinds": dict(collections.Counter(r["kind"] for r in rejected)),
           "filtered_units": {k: len(v) for k, v in filtered.items()}},
          open("kb/.work/l3_core.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"规则 {len(rules)}（新增 {len(new_rules)} / unchanged {unchanged}）| 拒绝 {len(rejected)}")
print("  形态:", dict(collections.Counter(r.get('form') for r in rules)))
print("  support_count:", dict(collections.Counter(r['support_count'] for r in rules)))
print("  拒绝原因:", dict(collections.Counter(r['kind'] for r in rejected)))
