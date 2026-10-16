#!/usr/bin/env python3
"""batch3 · 件4：把 L3 的补丁角色表合并回 L0 的 field_roles，并检测同名不同角色。

输入（全部只读）：kb/l2/units.jsonl、kb/l2/manifest_l2.jsonl、kb/l0/manifest.jsonl、
                 kb/l0/records/**、kb/.work/bases/enum.json、kb/.work/l1.json
输出：kb/.work/batch3/field_roles_merge.json（供审阅，随后由 batch3_emit.py 落到 registry）

合并规则（L0 是唯一真相）：
  ① 命中 L3 补丁表的 content 集合 → role=content（L3 step1 过滤的唯一依据）
  ② L0 既有角色里已明确的非 text 角色（status/link/attachment/other）→ 保留（既有判断优先）
  ③ 其余：按实测字段类型 + 值形态定角色（link/attachment/status/other/text）
  ④ 同一字段名在不同表隐含角色不一致 → 裸角色取覆盖表数最多者，偏差表写
     field_role_table_overrides「表名::字段名」
"""
import json, glob, collections

L0, L2 = "kb/l0", "kb/l2"
OUT = "kb/.work/batch3/field_roles_merge.json"

L3_CONTENT = [
    "Primary Text", "Headline", "广告名称", "命中片段", "命中原因", "命中规则", "修改建议",
    "边界内容", "检测关键词", "豁免词", "触发原因", "正则表达式", "判定理由",
    "建议表达（合规话术）", "避免条件/限定要求", "风险原句示例", "建议文案EN", "中文释义",
    "风险表达模式", "规则依据与边界", "卖点依据（产品功能）", "小语种参考 FR/DE/ES/IT",
    "字符数自检", "修订位置（原文引用）", "修订内容", "修订原因", "备注（如处理结果/建议）",
    "具体原因/分析", "原文逐字", "对判定的意义", "中文摘要", "关联现网规则", "条款位置",
    "要包含什么", "需向对接人收集的问题", "建议字段/材料", "资料名称",
]
L3_METADATA = [
    "启用状态", "风险等级", "规则编号", "映射规则编号", "卖点ID", "外部广告ID", "建议编号",
    "处理状态", "抓取状态", "投放状态", "使用状态", "灯色状态", "状态", "分类", "素材类型",
    "边界类型", "判断方式", "表达类型", "文案位置", "文案语种", "渠道", "渠道/市场", "平台",
    "适用型号", "适用产品", "适用品类", "适用渠道", "投放地区", "地区", "主题场景", "阶段",
    "语言", "品线", "广告类型", "广告账号", "广告组", "广告系列Campaign", "数据日期",
    "近7天展示", "近7天点击", "近7天费用USD", "上传人员", "是否需要授权（法务负责）",
    "是否完成医学审查（医疗确认）", "是否完成合规审查（法务确认）", "权威层级（医疗确认）",
    "资料类型(医疗确认)", "适用对象", "发布日期", "父记录", "来源", "文件/链接", "知识库",
    "知识库分类", "材料审核状态", "From", "细分", "备注", "更新频率", "agent使用范围", "负责人",   # 细分=该字段的旧名（飞书现名 备注，field_id fldn4bB 同源）；更新频率 此前漏列
]

l0reg = json.load(open(f"{L0}/registry/kb.json", encoding="utf-8"))
L0_FR_OLD = dict(l0reg["field_roles"])
OVERRIDES_OLD = dict(l0reg["field_role_table_overrides"])
L3_METADATA_FULL = L3_METADATA + [k for k, v in L0_FR_OLD.items()
                                 if v in ("status", "other", "link", "attachment")]

# ---------------------------------------------------------------- 实测 L2 字段论域
U = [json.loads(l) for l in open(f"{L2}/units.jsonl", encoding="utf-8") if l.strip()]
A_entry = collections.Counter(u.get("heading_path") for u in U if u["unit_type"] == "entry")
A = {k for k in A_entry if k}
B = set()
for u in U:
    if u["unit_type"] == "revision_pair":
        B |= set((u.get("meta") or {}).get("pair_fields") or [])
split_res = {json.loads(l)["resource_id"] for l in open(f"{L2}/manifest_l2.jsonl", encoding="utf-8")
             if l.strip() and json.loads(l).get("result") == "split"}
idx, C = {}, set()
for p in glob.glob(f"{L0}/records/*/*.json"):
    d = json.load(open(p, encoding="utf-8"))
    if d.get("base_token") and d.get("record_id"):
        idx[f"bitable__{d['base_token']}__{d['record_id']}"] = d
for k in split_res:
    if k in idx:
        C |= set((idx[k].get("fields") or {}).keys())

ledger_fields = set()
for l in open(f"{L0}/manifest.jsonl", encoding="utf-8"):
    if l.strip():
        r = json.loads(l)
        if r.get("field_name"):
            ledger_fields.add(r["field_name"])
UNIVERSE = A | B | C | ledger_fields

# ---------------------------------------------------------------- 逐表字段类型
TABLE_FIELDS = collections.defaultdict(dict)
bases = json.load(open("kb/.work/bases/enum.json", encoding="utf-8"))
for bt, v in bases.items():
    for t in v["tables"]:
        for f in t["fields"]:
            TABLE_FIELDS[t["table_name"]][f["field_name"]] = f.get("type")
sib = json.load(open("kb/.work/l1.json", encoding="utf-8"))["sibling_tables"]
for tname, st in sib.items():
    for f in st["fields"]:
        TABLE_FIELDS[tname][f["field_name"]] = f.get("type")
for f in json.load(open("kb/.work/batch3/fields_tblMGtPfe8ZUsEdP.json", encoding="utf-8"))["data"]["fields"]:
    TABLE_FIELDS["材料收集"][f["name"]] = f["type"]
for f in json.load(open("kb/.work/batch3/fields_tblVdl0jdK9G4ld3.json", encoding="utf-8"))["data"]["fields"]:
    TABLE_FIELDS["内容公式（仅供参考）"][f["name"]] = f["type"]

# ---------------------------------------------------------------- 观测值形态（link / attachment 的证据）
SHAPE = collections.defaultdict(collections.Counter)
for p in glob.glob(f"{L0}/records/*/*.json"):
    d = json.load(open(p, encoding="utf-8"))
    tn = d.get("source_table")
    for fn, fv in (d.get("fields") or {}).items():
        v = fv.get("value")
        s = ("empty" if v in (None, "", [], {}) else
             "list<dict>" if isinstance(v, list) and v and isinstance(v[0], dict) else
             "url" if isinstance(v, str) and (v.startswith("http") or
                                              __import__("re").match(r"^\[.*?\]\(https?://", v)) else
             "dict" if isinstance(v, dict) else
             "list" if isinstance(v, list) else
             "str" if isinstance(v, str) else "other")
        SHAPE[(tn, fn)][s] += 1

TOLINK = {"link", "url"}
TOATT = {"attachment", "image", "media", "file"}
TOSTATUS = {"select", "multi_select", "single_select", "multiSelect", "singleSelect"}
TOOTHER = {"number", "datetime", "auto_number", "created_time", "modified_time", "user",
           "created_user", "modified_user", "checkbox", "formula", "lookup", "duplex_link"}

def implied(table, field):
    """某表某字段由实测证据隐含的角色类别。"""
    t = TABLE_FIELDS.get(table, {}).get(field)
    sh = SHAPE.get((table, field), collections.Counter())
    if t in TOLINK:
        return "link"
    if t in TOATT:
        return "attachment"
    if sh.get("url", 0) > 0 and sh.get("list<dict>", 0) == 0:
        return "link"
    if sh.get("list<dict>", 0) > 0:
        return "attachment"
    if t in TOSTATUS or sh.get("list", 0) > 0:
        return "status"
    if t in TOOTHER:
        return "other"
    if t == "text":
        return "text"
    return None

# ---------------------------------------------------------------- 合并
merged, provenance = {}, {}
for f in sorted(UNIVERSE):
    per_table = {tn: implied(tn, f) for tn in TABLE_FIELDS if f in TABLE_FIELDS[tn]}
    per_table = {k: v for k, v in per_table.items() if v}
    if f in L3_CONTENT:                                   # ① L3 content 优先
        merged[f], provenance[f] = "content", "L3 补丁表 content 集合"
        continue
    old = L0_FR_OLD.get(f)
    if old in ("status", "link", "attachment", "other"):   # ② 既有明确角色优先
        merged[f], provenance[f] = old, "L0 既有角色（非 text）"
        continue
    if per_table:                                          # ③ 实测证据
        cnt = collections.Counter(per_table.values())
        best, n = cnt.most_common(1)[0]
        if len(cnt) > 1 and old:                           # 平票时保留 L0 既有 text
            if cnt.get(old, 0) == n:
                best = old
        merged[f], provenance[f] = best, f"实测证据（{dict(cnt)}）"
    elif old:
        merged[f], provenance[f] = old, "L0 既有角色"
    elif f in L3_METADATA_FULL:
        merged[f], provenance[f] = "text", "L3 补丁表 metadata 集合（无实测类型）"
    else:
        merged[f], provenance[f] = "text", "兜底 text（无实测证据，保守不猜）"

# ④ 同名不同角色 → 覆盖（仅当同一字段名在不同表上实测隐含的角色**互相冲突**才写覆盖，
#    否则该字段名只需一个裸角色，写覆盖是冗余；L3 content 字段另见 evidence_notes）
overrides = dict(OVERRIDES_OLD)
conflicts, evidence_notes = [], []
for f in sorted(UNIVERSE):
    per_table = {tn: implied(tn, f) for tn in TABLE_FIELDS if f in TABLE_FIELDS[tn]}
    per_table = {k: v for k, v in per_table.items() if v}
    if len(set(per_table.values())) <= 1:
        if per_table and f in L3_CONTENT and set(per_table.values()) != {"text"}:
            evidence_notes.append({"field": f, "tables": per_table,
                                   "role_in_use": merged[f],
                                   "note": "L3 补丁表判为 content（本批以其为基准，不改）；"
                                           "但实测字段类型/值形态显示非纯自由文本，交 L3 复核"})
        continue
    for tn, imp in sorted(per_table.items()):
        if imp != merged[f]:
            overrides[f"{tn}::{f}"] = imp
            conflicts.append({"field": f, "table": tn,
                              "field_type": TABLE_FIELDS[tn].get(f),
                              "tables_implied": per_table,
                              "default_role": merged[f], "override_role": imp,
                              "reason": f"同名不同角色：{tn} 实测隐含 {imp}，"
                                        f"其余表隐含 {sorted(set(per_table.values()))}，"
                                        f"裸角色取 {merged[f]}"})
            provenance[f] += f"；{tn} 写覆盖 → {imp}"

missing = sorted(f for f in UNIVERSE if f not in merged)

# ⑤ 落表：既有角色只增不删（L0 里已有但不在 L2 论域内的字段，如规则库专属字段，保留原角色）；
#    L3 补丁表的两侧（content / metadata）按名全局生效，保证 L3 不再需要自己那份表。
FINAL = dict(L0_FR_OLD)
for k in L3_METADATA_FULL:
    FINAL.setdefault(k, "text")                 # L3 判为 metadata 且 L0 无角色 → text
for k in L3_CONTENT:
    FINAL[k] = "content"                        # L3 判为 content → content（全局，不限论域）
for f, r in merged.items():
    FINAL[f] = r                                # 实测论域内的合并结果（已含 ① 的 content 优先）
kept_only = sorted(set(L0_FR_OLD) - set(merged))
dropped = sorted(set(merged) - set(FINAL))
new_overrides = {k: v for k, v in overrides.items() if k not in OVERRIDES_OLD}

json.dump({
    "l2_universe": {"A_entry_heading_path": sorted(A), "B_revision_pair_fields": sorted(B),
                    "C_source_fields_behind_split_resources": sorted(C),
                    "ledger_field_names": sorted(ledger_fields),
                    "universe": sorted(UNIVERSE), "count": len(UNIVERSE),
                    "counts": {"A": len(A), "B": len(B), "C": len(C), "union": len(UNIVERSE)}},
    "field_roles_before_count": len(L0_FR_OLD),
    "field_roles_after": dict(sorted(FINAL.items())),
    "field_roles_after_count": len(FINAL),
    "field_roles_l2_universe_only": dict(sorted(merged.items())),
    "field_roles_kept_not_in_l2_universe": kept_only,
    "provenance": dict(sorted(provenance.items())),
    "overrides_before": OVERRIDES_OLD,
    "overrides_after": dict(sorted(overrides.items())),
    "new_overrides": new_overrides,
    "conflicts": conflicts,
    "evidence_notes": evidence_notes,
    "coverage": {"universe": len(UNIVERSE), "covered": len(UNIVERSE) - len(missing),
                 "missing": missing, "missing_count": len(missing)},
    "l3_patch": {"content": L3_CONTENT, "metadata": sorted(set(L3_METADATA_FULL))},
    "table_field_types": {t: dict(sorted(v.items())) for t, v in sorted(TABLE_FIELDS.items())},
}, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

print(f"L2 字段论域 = {len(UNIVERSE)}  (A={len(A)} B={len(B)} C={len(C)})")
print(f"field_roles  {len(L0_FR_OLD)} → {len(FINAL)}（其中 L2 论域内 {len(merged)}）")
print(f"既有但不在 L2 论域、按只增不删保留的字段 {len(kept_only)}: {kept_only}")
print(f"覆盖 {len(UNIVERSE)-len(missing)}/{len(UNIVERSE)}；遗漏 {len(missing)}: {missing}")
print(f"override {len(OVERRIDES_OLD)} → {len(overrides)}（新增 {len(new_overrides)}）")
for k, v in new_overrides.items():
    print("   +", k, "=", v)
print("角色分布:", dict(collections.Counter(FINAL.values())))
print("实测与 L3 content 判断有出入、留待 L3 复核:", len(evidence_notes))
for n in evidence_notes: print("   ~", n["field"], n["tables"])
