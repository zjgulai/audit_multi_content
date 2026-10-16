#!/usr/bin/env python3
"""F11 第二批：登记 L6 范围侧的三个发现。

F11 的结论是「L6 **不需要**重建」——原索引与其核定口径完全一致（重建为幂等空操作：
切词 0 条、embedding 调用 0 次、复用 2088 段、5.5s 完成，bm25/vectors/index 三个产物
mtime 未变，只有 registry 被重写）。但过程中查明三件事，必须留痕：

  OI-L6-001  可用口径把「整页抓取」当知识（根因未修，用 SCOPE.txt 白名单挡住）
  OI-L6-002  SCOPE.txt 机制文档化但未接入建索引侧（已修）
  OI-L6-003  l6_build.py 硬编码 assert len(kept) == 1899，合法增长后无法重跑（已修）
"""
import json
import os
import shutil
import sys

KB = "kb"
REG = f"{KB}/l0/registry/kb.json"
ARCHIVE = f"{KB}/l8/_archive/fix-20260929-094703"
RUN = "20260929-1200"


def main():
    shutil.copy2(REG, f"{ARCHIVE}/kb.json.before-F11b")
    shutil.copy2(f"{KB}/l6/registry/l6.json", f"{ARCHIVE}/l6_registry.at-F11.json")

    r = json.load(open(REG, encoding="utf-8"))
    ids = {o["id"] for o in r["open_issues"]}
    assert not ({"OI-L6-001", "OI-L6-002", "OI-L6-003"} & ids), "已存在，勿重复登记"

    r["open_issues"].append({
        "id": "OI-L6-001",
        "severity": "medium",
        "title": "L2/L3 可用口径把「整页抓取」当知识（83 条巨型 unit 被挡在 L6 之外）",
        "evidence": {
            "usable_recomputed_at_F11": 1982,
            "indexed": 1899,
            "excluded_by_scope_file": 83,
            "excluded_profile": {
                "median_chars": 24703,
                "gt_2000_chars": "82/83",
                "max_chars": 45080,
                "distinct_openings": 7,
                "top_openings": {
                    "Skip to content / Switch to your local store": 60,
                    "Zum Inhalt springen（德）": 9,
                    "Aller au contenu（法）": 5,
                    "Saltar al contenido（西）": 4,
                    "Przejdź do treści（波）": 2,
                },
                "unit_type": "clause（全部）",
                "kb_type": "wording 82 / external_standard 1",
                "source_tables": "#正文（全部）",
                "sources": "momcozy.com 及 ca/de/eu/fr/uk/es/pl/au 各站的产品页/博客页/集合页；另 drugs.dxy.cn 临床指南页 1 条",
            },
            "included_profile": {"median_chars": 67, "gt_2000_chars": "1/1899"},
            "cost_if_included": {
                "total_chars": "292,642 → 2,400,729（×8.2）",
                "estimated_segments": "3,654 → 21,258（×5.8）",
                "consequence": "每个与哺乳/吸奶器相关的查询都会命中巨型产品页，把精确的规则条目挤下去",
            },
            "same_class_already_inside": {
                "unit": "external_standard #l.1-1",
                "chars": 31450,
                "segments": 201,
                "share_of_vector_segments": "201/2088 = 9.6% 的向量段只来自这 1 条 unit",
            },
        },
        "impact": (
            "当前**未**影响 L6 检索质量（SCOPE.txt 白名单已挡住这 83 条）。风险在别处："
            "①L2 每增长一次就会重新引入同类噪声，靠人工核对白名单维持，属长期人力成本；"
            "②已进索引的那条 31,450 字符 unit 占掉 9.6% 的向量段，是同一类问题的存量表现；"
            "③任何直接以「L3 口径过滤结果」为范围的用法（含 L3 蒸馏本身）都会吃到这些整页全文。"
        ),
        "root_cause": (
            "口径只按「字段角色」筛（heading_path 属 content 即收），**没有尺寸或来源护栏**。"
            "整页抓取的正文恰好落在 content 角色下，于是被当成一条 clause。"
        ),
        "fix_by": "L2/L3 口径侧（不属 F11；F11 只做了 L6 侧的止损）",
        "suggested_fix": (
            "在 l6_scope_lib.usable_units() 与 .work/l3_distill2.py 的**同一份口径**里加尺寸/来源闸门，"
            "而不是只依赖 SCOPE.txt 白名单。建议判据（择一或叠加，需 L3 侧确认）："
            "①单 unit 字符数阈值（如 >5,000 视为整页抓取，须先切段或标注）；"
            "②来源为品牌自有站点 URL 且文本以站点外壳开头 → 标 quality_flag 而非直接收；"
            "③把「一条 unit 的最大长度」纳入 L3 体检项。"
        ),
        "status": "open",
        "recorded_at": RUN,
        "mitigation_at_F11": "kb/l6/SCOPE.txt 白名单收录 1,899 条、排除 83 条；排除量在 registry 的 filter_distribution 里可见（*|outside_scope_file: 83）。",
    })

    r["open_issues"].append({
        "id": "OI-L6-002",
        "severity": "medium",
        "title": "SCOPE.txt 机制已文档化但未接入建索引侧，registry 会虚假声明已取子集",
        "evidence": {
            "before": (
                "kb/l6/SCOPE.txt 只被 kb/.work/l6_scope.py（报告器）读；"
                "kb/.work/l6_build.py 走 l6_scope_lib.usable_units()，**不读 SCOPE.txt**。"
                "而 l6_build.py 写 registry 时却记 scope_file = SCOPE.txt（文件存在即记），"
                "等于声称「本次索引按 SCOPE.txt 取了子集」——实际没有。"
            ),
            "why_it_matters": (
                "这是**静默失真的溯源声明**：只读 registry 的人会以为范围受白名单约束，"
                "而实际建索引把全部可用单元都收了。一旦有人创建 SCOPE.txt 想收窄范围，"
                "报告会说收窄了、索引却没收窄，两边永久不一致且无人告警。"
            ),
            "never_triggered_before": "此前从未创建过 kb/l6/SCOPE.txt，所以该缺陷一直未被暴露（属潜在缺陷，非已发生的错）。",
        },
        "impact": "潜在：范围白名单失效 + registry 溯源失真。因从未创建 SCOPE.txt，历史索引本身没错。",
        "resolution": (
            "已修：新增 l6_scope_lib.apply_scope_file()，作为 SCOPE.txt 的**唯一**读取实现，"
            "由 l6_build.py（建索引）与 l6_scope.py（报告）同源调用；"
            "被排除的条数计入 filter_distribution 的 *|outside_scope_file；"
            "registry 新增 scope_file_info（specified / hits / excluded_from_usable / specified_but_not_usable）。"
        ),
        "status": "closed_fixed",
        "recorded_at": RUN,
        "closed_at": RUN,
        "closed_by": "kb/.work/l6_scope_lib.py + kb/.work/l6_build.py",
    })

    r["open_issues"].append({
        "id": "OI-L6-003",
        "severity": "low",
        "title": "l6_build.py 用字面量 1899 当口径护栏，L2/L3 合法增长后无法重跑",
        "evidence": {
            "before": "kb/.work/l6_build.py:67  assert len(kept) == 1899, \"可用单元数 … != 1899，范围口径对不上，停\"",
            "observed": "2026-09-29 F11 重算可用单元得 1,982，直接 AssertionError 撞停（差 +83）。",
            "why_it_matters": (
                "护栏本身是对的（防口径静默漂移），但把「预期范围」钉成字面量，"
                "使**合法**的语料增长与**非法**的口径改坏无法区分，只能改代码才能重跑 —— "
                "而改代码正是最该避免的绕过方式。"
            ),
        },
        "impact": "L6 无法在 L2 增长后重建；每次都要动代码，护栏形同虚设。",
        "resolution": (
            "已修：护栏改为与 registry 里记录的上次范围比对。漂移默认仍停，"
            "必须显式加 --accept-scope-delta（或 L6_ACCEPT_SCOPE_DELTA=1）才放行，"
            "并把**逐 id** 差额（added / removed，含 count）写进 registry 的 scope.scope_delta，"
            "使「这次范围变了什么」可事后复核而非只看总数。"
            "另核实该文件再无其它硬编码数字护栏（其余两处 assert 为模型握手与向量维度一致性，正当）。"
        ),
        "status": "closed_fixed",
        "recorded_at": RUN,
        "closed_at": RUN,
        "closed_by": "kb/.work/l6_build.py",
    })

    r["l6_scope_verification"] = {
        "verified_at": RUN,
        "conclusion": "L6 不需要重建：现有索引与其核定口径完全一致。",
        "how": (
            "把 SCOPE.txt 接进建索引侧后按同一口径重跑，得到幂等空操作 —— "
            "BM25 本次切词 0 条、索引无变化不重写；向量新增/变更 0、复用 2088 段、embedding 调用 0 次；"
            "索引投影 1899 行未变；总耗时 5.5s。"
            "文件系统层证据：bm25/docs.jsonl(14:03:36)、vectors/vectors.jsonl(14:19:19)、"
            "index/l6.jsonl(14:19:19) 三个产物 mtime 均未变，只有 registry/l6.json 被重写。"
        ),
        "references_integrity": (
            "另核：L6 的 1,899 个 unit_id **全部**仍在当前 kb/l2/units.jsonl 内；"
            "1,899 条的 source_sha256 全部命中当前 L2 的 sha 集合；"
            "1,899 条的 anchor 全部仍能在当前 L1 找到。即引用无失效。"
        ),
        "scope_delta_measured": {"prev_indexed": 1899, "now_in_scope": 1982, "added": 83, "removed": 0},
        "why_delta_rejected": "见 OI-L6-001：新增 83 条为整页抓取，纳入会使字符量 ×8.2、估算段数 ×5.8。",
        "command": "python3 kb/.work/l6_build.py 20260929-F11",
    }

    r["changes"].append({
        "run_id": RUN,
        "change": "append+close",
        "keys": ["open_issues", "l6_scope_verification"],
        "note": (
            "F11 第二批：L6 结论为**不需重建**（幂等空操作验证一致）。"
            "新登记 OI-L6-001（口径把整页抓取当知识，根因待 L2/L3 侧修；L6 侧以 SCOPE.txt 止损）；"
            "新登记并关闭 OI-L6-002（SCOPE.txt 未接入建索引侧 → registry 虚假声明取子集）；"
            "新登记并关闭 OI-L6-003（字面量 1899 护栏改为基线比对 + 逐 id 差额留痕）。"
        ),
    })

    with open(REG, "w", encoding="utf-8") as fh:
        json.dump(r, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    print("kb.json 已更新；open_issues 现状：")
    for o in r["open_issues"]:
        print(f"  {o['id']}  {o['status']:20} {o['title']}")


if __name__ == "__main__":
    sys.exit(main())
