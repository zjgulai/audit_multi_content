#!/usr/bin/env python3
"""L6 范围确定：复算「可用单元」= L3 过滤后保留的那批（预期 1,899）。
过滤口径必须与 kb/.work/l3_distill2.py 完全一致，并用 kb/.work/l3_stats.json 的分布对账。
若 kb/l6/SCOPE.txt 存在，则按其中列出的 unit_id 取子集。
kb/l0~l3 只读。
"""
import collections, json, os, sys

L0, L2, L3, L6 = "kb/l0", "kb/l2", "kb/l3", "kb/l6"
# ── 干跑档（批次6 加，2026-10-01）────────────────────────────────────────────
# 行为变更：本脚本此前**运行即写盘**（唯一写点 = 文件末尾那一处 `kb/.work/l6_scope.json`）。
# 现在：不带 `--apply` = 预演（**不写**该证据件，只把对账结果打屏）；带 `--apply` = 真档。
# 为什么要它：本脚本已被**补登进 `layers.yaml` 的 L6 `engine`**（批次6 B 块），
# 而 engine 清单里不许有**不可预演**的引擎（同批次5 给 `l6_selftest.py` 补档的理由）。
# 闸门位次：本段早于第一个副作用（全脚本唯一的写在文件末尾），其余全是 `kb/l0~l3` 只读。
# 命名避撞：**不写** `kb/l6/runs/<RUN>-dryrun.json`（那个名字归 L6 落章引擎 `l6_report.py`）；
# 预演档**不产**任何落章件 —— 本脚本不是落章引擎（L6 的落章引擎是 `l6_report.py`）。
_AV = [a for a in sys.argv[1:]]
APPLY = "--apply" in _AV
if APPLY:
    _AV.remove("--apply")
RUN = _AV[0] if _AV and not _AV[0].startswith("--") else "20260923-1400"
# ──────────────────────────────────────────────────────────────────────────

U = [json.loads(l) for l in open(f"{L2}/units.jsonl", encoding="utf-8") if l.strip()]
l0reg = json.load(open(f"{L0}/registry/kb.json", encoding="utf-8"))
L0_FR = l0reg["field_roles"]

# ↓↓↓ 以下两个集合与 kb/.work/l3_distill2.py 逐字一致，不得各写一份口径 ↓↓↓
CONTENT_FIELDS = {
    "Primary Text", "Headline", "广告名称", "命中片段", "命中原因", "命中规则", "修改建议",
    "边界内容", "检测关键词", "豁免词", "触发原因", "正则表达式", "判定理由",
    "建议表达（合规话术）", "避免条件/限定要求", "风险原句示例", "建议文案EN", "中文释义",
    "风险表达模式", "规则依据与边界", "卖点依据（产品功能）", "小语种参考 FR/DE/ES/IT",
    "字符数自检", "修订位置（原文引用）", "修订内容", "修订原因", "备注（如处理结果/建议）",
    "具体原因/分析", "原文逐字", "对判定的意义", "中文摘要", "关联现网规则", "条款位置",
    "要包含什么", "需向对接人收集的问题", "建议字段/材料", "资料名称",
}
METADATA_FIELDS = {
    "启用状态", "风险等级", "规则编号", "映射规则编号", "卖点ID", "外部广告ID", "建议编号",
    "处理状态", "抓取状态", "投放状态", "使用状态", "灯色状态", "状态", "分类", "素材类型",
    "边界类型", "判断方式", "表达类型", "文案位置", "文案语种", "渠道", "渠道/市场", "平台",
    "适用型号", "适用产品", "适用品类", "适用渠道", "投放地区", "地区", "主题场景", "阶段",
    "语言", "品线", "广告类型", "广告账号", "广告组", "广告系列Campaign", "数据日期",
    "近7天展示", "近7天点击", "近7天费用USD", "上传人员", "是否需要授权（法务负责）",
    "是否完成医学审查（医疗确认）", "是否完成合规审查（法务确认）", "权威层级（医疗确认）",
    "资料类型(医疗确认)", "适用对象", "发布日期", "父记录", "来源", "文件/链接", "知识库",
    "知识库分类", "材料审核状态", "From", "细分", "备注", "更新频率", "agent使用范围", "负责人",   # 细分=该字段的旧名（飞书现名 备注，field_id fldn4bB 同源）；更新频率 此前漏列
    *[k for k, v in L0_FR.items() if v in ("status", "other", "link", "attachment")],
}


def frole(n):
    return "content" if n in CONTENT_FIELDS else ("metadata" if n in METADATA_FIELDS else "unknown")


FILTER = collections.Counter()
kept = []
for u in U:
    kb = u["kb_type"]
    if kb not in ("wording", "external_standard", "internal_sample"):
        FILTER[(kb, "out_of_scope_kb")] += 1
        continue
    if kb == "internal_sample" and (u.get("meta") or {}).get("table") != "专家修订汇总表":
        FILTER[(kb, "out_of_scope_table")] += 1
        continue
    if u["unit_type"] == "entry" and frole(u.get("heading_path")) != "content":
        FILTER[(kb, "metadata" if frole(u.get("heading_path")) == "metadata"
                else "metadata_unknown_field")] += 1
        continue
    if (u.get("meta") or {}).get("content_quality_flag"):
        FILTER[(kb, "quality_flag")] += 1
        continue
    kept.append(u)

# ---- 与 L3 对账
stats = json.load(open("kb/.work/l3_stats.json", encoding="utf-8"))
expect = {f"{k[0]}|{k[1]}": v for k, v in
          {(k.split("|")[0], k.split("|")[1]): v for k, v in stats["filtered"].items()}.items()}
got = {f"{k[0]}|{k[1]}": v for k, v in FILTER.items()}
checks = {
    "l2_total": (len(U), stats["accounting"]["l2_total"]),
    "kept": (len(kept), stats["kept"]),
    "filtered_out": (len(U) - len(kept), stats["filtered_out"]),
    "filter_distribution": (got, expect),
}
ok = (len(U) == stats["accounting"]["l2_total"] and len(kept) == stats["kept"]
      and len(U) - len(kept) == stats["filtered_out"] and got == expect)

# ---- SCOPE.txt 子集
scope_note = "无 kb/l6/SCOPE.txt → 对全部可用单元建索引"
scope_file = f"{L6}/SCOPE.txt"
if os.path.exists(scope_file):
    want = [l.strip() for l in open(scope_file, encoding="utf-8") if l.strip()
            and not l.startswith("#")]
    kept_ids = {u["unit_id"] for u in kept}
    miss = [w for w in want if w not in kept_ids]
    kept = [u for u in kept if u["unit_id"] in set(want)]
    scope_note = f"按 kb/l6/SCOPE.txt 取子集：{len(want)} 条指定，命中可用单元 {len(kept)} 条，未命中 {len(miss)}"

# ---- 语言构成（供分语言索引预估）
def cjk(ch):
    o = ord(ch)
    return 0x3400 <= o <= 0x9FFF or 0x3040 <= o <= 0x30FF or 0xF900 <= o <= 0xFAFF


LANG = collections.Counter()
for u in kept:
    t = u.get("text") or ""
    has_cjk = any(cjk(c) for c in t)
    has_lat = any(c.isascii() and c.isalpha() for c in t)
    LANG["中英混排" if has_cjk and has_lat else ("中文" if has_cjk else
          ("英文/拉丁" if has_lat else "无字母"))] += 1

out = {
    "run_id": RUN, "scope_note": scope_note,
    "usable_total": len(kept), "reconcile_ok": ok, "checks": {k: list(v) if isinstance(v, tuple)
                                                             else v for k, v in checks.items()},
    "filter_distribution_got": got, "filter_distribution_expected": expect,
    "lang_composition": dict(LANG),
    "by_kb_type": dict(collections.Counter(u["kb_type"] for u in kept)),
    "unit_ids": [u["unit_id"] for u in kept],
}
if APPLY:
    json.dump(out, open("kb/.work/l6_scope.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"[apply] 证据件已写 → kb/.work/l6_scope.json（reconcile_ok={ok}, run_id={RUN}）")
else:
    print(f"[dry-run] **未写** kb/.work/l6_scope.json（reconcile_ok 本会是 {ok}, run_id={RUN}）"
          f" —— 加 --apply 才落盘")

print(f"L2 单元 {len(U)} → 可用 {len(kept)}（对账 {'PASS' if ok else 'FAIL'}）")
print(f"过滤分布 got={got}")
print(f"过滤分布 exp={expect}")
print(f"语言构成：{dict(LANG)}")
print(f"kb_type：{out['by_kb_type']}")
print(f"范围：{scope_note}")
sys.exit(0 if ok else 1)
