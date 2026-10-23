#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""selftest_coverage.py —— **覆盖判据**的自证（2026-10-08 起，随 B/C/D/A 一起长）

    KB_ENTRY=selftest sh kb/kbpy l7/skills/kb-content-review/scripts/selftest_coverage.py

## 为什么要有这个文件

覆盖判据（`coverage_judge` / `rule_cited_resources` / `resources_of_anchors`）原先**没有任何
判据**，只能靠「真跑一遍整链、看结论对不对」来验 —— 那种验法**既慢又碰运气**（要正好有素材
能触发某条分支），而且**改坏了不会红**。实测代价（2026-10-08）：图片单反复落「覆盖缺口」，
排查了一整轮才定位到「同源两锚点对不上」，而这条分支**从来没被测过**。

⇒ 判据抽成纯函数（`coverage_judge`）之后，四条分支与**反向对照**都能离线喂样本判。

## 本文件的不变量（缺一条就不是自证）

1. **每条正例都配反向对照** —— 没有反向对照的判据是「量不出缺陷的尺子」：
   把整个同源归并删掉，B1 照样绿。
2. **全部离线**：不写库、不发飞书、不起链；只读 `kb/l2/units.jsonl`（B6/B7 要真实锚点）。
"""
from __future__ import annotations

import glob as glob_mod
import importlib.util
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
# ★ 知识库根：**先吃 `KB_ROOT` / `KB_SELFTEST_ROOT`，再按自身路径推**（2026-10-08 补）。
#   为什么（实测）：本文件会被装到 `~/.dsh/skills/kb-content-review/scripts/` 下运行
#   （评审链读的就是那份副本 —— 见 `with_kb_evidence.py:58` 的 `KB_CONTENT_REVIEW_PY`），
#   而从那里按 `../../../../..` 推出来的是 **`/Users`**，不是 KB 根。
#   代价实测：活副本上跑自证得 **21/1**，唯一失败的是「找不到素材的 OCR」——
#   **看起来像判据坏了，其实是自证件推错了根**。这种"尺子自己歪"的假红必须消掉。
ROOT = (os.environ.get("KB_SELFTEST_ROOT") or os.environ.get("KB_ROOT")
        or os.path.abspath(os.path.join(HERE, "..", "..", "..", "..", "..")))
REVIEW = os.path.join(HERE, "review.py")

P, F = [], []


def chk(name, cond, extra=""):
    (P if cond else F).append(name)
    print("  %s %s%s" % ("✅" if cond else "❌", name, ("  " + extra) if extra else ""))


def load_review():
    spec = importlib.util.spec_from_file_location("kb_review", REVIEW)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)          # main() 有 __main__ 守卫 ⇒ 只定义、不执行
    return mod


def main():
    rev = load_review()
    print("覆盖判据自证（离线；只读 kb/l2/units.jsonl 取真实锚点）\n")

    # ══════════════════════════════════════════════════════════════════════
    # B 组 —— 同源归并（2026-10-08，Owner 批准 B）
    # ══════════════════════════════════════════════════════════════════════
    THR = 16.0
    A_CITED = "#正面和负面样本/REC-A/原文反馈"      # 被规则引用的那个锚点
    A_MEDIA = "#素材/REC-A/图片素材/#img.1"        # 同一素材的**图上文字**锚点（检索命中的）
    A_OTHER = "#素材/REC-B/图片素材/#img.1"        # 隔壁素材

    def rows(*pairs):
        return [{"anchor": a, "raw_bm25": s} for a, s in pairs]

    # B1 直接命中（原路径）不许坏
    by, _ = rev.coverage_judge(rows((A_CITED, THR + 1)), {A_CITED}, {"REC-A"}, THR)
    chk("B1 直接命中（锚点∈被引池 且过门限）⇒ covered_by=rule", by == "rule", by)

    # B2 ★ B 的核心：锚点不同名、但**同源** ⇒ 算覆盖
    by, det = rev.coverage_judge(rows((A_MEDIA, THR + 1)), {A_CITED}, {"REC-A"}, THR,
                                 resources_of=lambda aa: {A_MEDIA: "REC-A"})
    chk("B2 ★ 同源命中（锚点不同名、resource 相同）⇒ covered_by=same_source",
        by == "same_source" and len(det["same_source_unit_hits"]) == 1, by)

    # B3 ★ 反向对照：**不同源**不许算覆盖（否则「命中隔壁素材」会被算成覆盖）
    by, _ = rev.coverage_judge(rows((A_OTHER, THR + 1)), {A_CITED}, {"REC-A"}, THR,
                               resources_of=lambda aa: {A_OTHER: "REC-B"})
    chk("B3 反向对照：不同 resource ⇒ **不覆盖**（不许把隔壁素材算成覆盖）", by == "", by)

    # B4 ★ 反向对照：同源但**没过门限** ⇒ 不覆盖（**门限一个字没松**）
    by, _ = rev.coverage_judge(rows((A_MEDIA, THR - 0.1)), {A_CITED}, {"REC-A"}, THR,
                               resources_of=lambda aa: {A_MEDIA: "REC-A"})
    chk("B4 反向对照：同源但 BM25 < 覆盖门限 ⇒ **不覆盖**（门限没松）", by == "", by)

    # B5 安全词优先，且它一命中就不必再判同源
    by, _ = rev.coverage_judge(rows((A_OTHER, 1.0)), set(), set(), THR, has_safe_hits=True)
    chk("B5 命中允许表述（安全词）⇒ covered_by=safe_vocabulary", by == "safe_vocabulary", by)

    # ── ★★ 2026-10-23：锚点**同名 ≠ 同源**（位置型锚点撞名把覆盖池污染了）──────────
    #   实测病灶：`#l.1-1` 在 L2 被 **921** 个单元共用；external_standard 并进 rules 后，
    #   它的锚点进了覆盖池 ⇒ 命中**另一份文档**的同名单元也算「被规则引用」
    #   ⇒ 5 条回归样本从 REVIEW（库不认识这个题材）翻成 **PASS**（fail-open）。
    S_SHA_RULE = "a" * 64        # 引用这个锚点的规则，它所依据的那份文档
    S_SHA_MAT = "b" * 64         # 本次素材命中的单元所在的**另一份**文档

    def rows_sha(*triples):
        return [{"anchor": a, "raw_bm25": s, "source_sha256": h} for a, s, h in triples]

    # B8 ★ 反向对照：锚点同名、**文档不同** ⇒ 不许算覆盖（10-23 那 5 条翻 PASS 的形状）
    by, _ = rev.coverage_judge(rows_sha(("#l.1-1", THR + 1, S_SHA_MAT)), {"#l.1-1"}, set(), THR,
                              cited_shas={"#l.1-1": {S_SHA_RULE}})
    chk("B8 ★ 反向对照：锚点同名但 source_sha256 不同（另一份文档）⇒ **不覆盖**", by == "", by)

    # B9 正例：同名**且**同一份文档 ⇒ 仍算覆盖（收窄不许把本该认的也挡掉）
    by, _ = rev.coverage_judge(rows_sha(("#l.1-1", THR + 1, S_SHA_RULE)), {"#l.1-1"}, set(), THR,
                              cited_shas={"#l.1-1": {S_SHA_RULE}})
    chk("B9 同名且同文档（source_sha256 一致）⇒ 仍是 covered_by=rule", by == "rule", by)

    # B10 反向对照：给了 cited_shas，但命中单元**没有** sha ⇒ 不覆盖（保守一侧）
    by, _ = rev.coverage_judge(rows(("#l.1-1", THR + 1)), {"#l.1-1"}, set(), THR,
                              cited_shas={"#l.1-1": {S_SHA_RULE}})
    chk("B10 反向对照：命中单元缺 source_sha256 ⇒ 不覆盖（宁转人工，不放 PASS）", by == "", by)

    # B11 ★ 反向对照：**位置型**锚点（`#l.1-3`，跨文档共用）不许判同源 ——
    #   实测形状：回表取到的是「扫到的第一份文档」的资源，与本次素材无关 ⇒ 覆盖被凭空撑起来。
    #   ⚠️ `cited` 必须空：位置型锚点若进了被引池，命中的就是 `direct` 那一条（B8 管它）。
    #      这里要验的是**同源支路**，所以只给 `cited_res`。
    by, _ = rev.coverage_judge(rows(("#l.1-3", THR + 1)), set(), {"REC-X"}, THR,
                              resources_of=lambda aa: {"#l.1-3": "REC-X"})
    chk("B11 ★ 反向对照：位置型锚点（#l.1-3）**不算同源**（哪怕回表给出 resource）", by == "", by)

    # B12 正例：带记录 id 的锚点照旧算同源（收窄不许把这条该认的也挡掉）
    by, _ = rev.coverage_judge(rows(("#素材/REC-A/图片素材/#img.1", THR + 1)), set(),
                              {"REC-A"}, THR,
                              resources_of=lambda aa: {"#素材/REC-A/图片素材/#img.1": "REC-A"})
    chk("B12 带记录 id 的锚点仍算同源（收窄没把该认的挡掉）", by == "same_source", by)

    # B6 ★★ 地基：两个**真实**锚点回权威表取到的 resource_id 必须相同
    #   若这条不成立，B 的整个前提就是错的（而它会静默地什么都不做）
    import time
    t0 = time.time()
    rmap = rev.resources_of_anchors([
        "#正面和负面样本/recvw2wE9MEpQK/原文反馈",
        "#素材/recvw2wE9MEpQK/图片素材/#img.1"])
    dt = time.time() - t0
    same = rmap.get("#正面和负面样本/recvw2wE9MEpQK/原文反馈") == \
        rmap.get("#素材/recvw2wE9MEpQK/图片素材/#img.1")
    chk("B6 ★ 真实锚点：同素材两个不同名锚点 ⇒ **同一个 resource_id**（%.1fs）" % dt,
        same and bool(rmap.get("#素材/recvw2wE9MEpQK/图片素材/#img.1")),
        json.dumps(rmap, ensure_ascii=False)[:150])

    # B7 反向对照：不同记录的真实锚点 ⇒ resource_id 必须不同
    rmap2 = rev.resources_of_anchors([
        "#素材/recvw2wE9MEpQK/图片素材/#img.1",
        "#广告文案明细/recvuJYdOb1B8v/命中片段"])
    a, b = (rmap2.get("#素材/recvw2wE9MEpQK/图片素材/#img.1"),
            rmap2.get("#广告文案明细/recvuJYdOb1B8v/命中片段"))
    chk("B7 反向对照：不同来源的锚点 ⇒ resource_id 不同", bool(a) and bool(b) and a != b,
        f"{a} vs {b}")

    # B8 收窄：一键多源时**宁可不算**（否则会 fail-open）
    multi = {"r1": {"resource_id": None, "resource_ids": ["RA", "RB"]},
             "r2": {"resource_id": None, "resource_ids": ["RC"]},
             "r3": {"resource_id": "RD"}}
    got = rev.rule_cited_resources(multi)
    chk("B8 收窄：resource_ids 多值**跳过**、单值收、resource_id 单值收",
        got == {"RC", "RD"}, str(sorted(got)))

    # ══════════════════════════════════════════════════════════════════════
    # C 组 —— 取不到 L0 逐字原文时**不许把命中丢掉**（2026-10-08，Owner 批准 C）
    #   ★ 为什么要「打桩 rules 再真跑 review()」：缺口路径**在今天一条真规则都触发不了**
    #     （实测：`rules.jsonl` 里引用不可解析锚点的规则 **0 条**）⇒ 不构造就测不到。
    #     打桩的是**输入**（rules），跑的是**真的** `review()` —— 判定链一步没绕过。
    # ══════════════════════════════════════════════════════════════════════
    FE = "极限绝对化承诺用语自证样本"          # 独一无二，确保只命中这条桩规则
    GAP_ANCHOR = "#正面和负面样本/recvw2wE9MEpQK/原文反馈"   # ★ 实测：这件 L0 **没有 fields** ⇒ 解析不了
    fake = {"r-selftest-gap": {
        "rule_id": "r-selftest-gap", "article_no": "T-9.99", "rule_code": "T99",
        "kb_type": "internal_sample", "p_level": "P1", "risk_level": "中",
        "forbidden_expression": FE, "rule_text": "自证桩规则",
        "reason": "自证用（不是库里的真规则）",
        "anchor": GAP_ANCHOR,
        "evidence_units": [{"anchor": GAP_ANCHOR,
                            "source_sha256": "3034ed5b968769304a9691056d74bb32eee6c58cb312e81405fc07060a4ba6c9",
                            "unit_id": "7b4656e5fcb17dab82a2"}],
    }}
    _orig_load_rules = rev.load_rules
    rev.load_rules = lambda: fake
    try:
        res = rev.review("这句里写了%s这种说法。" % FE, content_type="text", run_id="selftest-gap")
    finally:
        rev.load_rules = _orig_load_rules
    gap_fs = [f for f in res["findings"] if f.get("rule_id") == "r-selftest-gap"]

    chk("C1 ★ 锚点解析不了时，命中**照样出现在 findings 里**（改前是一句 continue ⇒ 整类依据消失）",
        len(gap_fs) == 1, "命中条数=%d（应 1）" % len(gap_fs))
    if gap_fs:
        f0 = gap_fs[0]
        chk("C2 缺口条目显式标了 `verbatim_verified=False` 且写了 `evidence_gap`（不许静默）",
            f0.get("verbatim_verified") is False and bool(f0.get("evidence_gap")),
            str(f0.get("verbatim_verified")))
        chk("C3 缺口条目带 **L0 飞书直链**（D：取不到逐字原文 ≠ 没有直链）",
            str(f0.get("l0_entry_url") or "").startswith("https://"), str(f0.get("l0_entry_url"))[:70])
    chk("C4 `unmet` 里留了痕且标明处置是「照出」而不是「丢掉」",
        any(u.get("disposition") == "output_as_finding_with_gap" for u in res["unmet_citation"]),
        str([u.get("disposition") for u in res["unmet_citation"]]))

    # C5 ★ 反向对照：**能解析**的锚点仍须走原路（`verbatim_verified=True` + 有 verbatim_source）
    #    没有这一条，把 C 写成「一律标缺口」也能让 C1–C4 全绿 —— 那是把闸门拆了。
    #    ★ 摘录必须**从 L0 真值里取**：第一版我随手喂了个 "a"，逐字比对当然不过 ⇒ 是测试写错，
    #      不是判据坏。反向对照自己也得是真样本。
    GOOD_ANCHOR = "#广告文案明细/recvuJYdOb1B8v/命中片段"
    _src0 = rev.resolve_anchor(GOOD_ANCHOR, None)
    _exc = (_src0 or {}).get("verbatim", "")
    _sub = _exc.strip()[:24]
    real_units = rev.resolve_excerpt({"evidence_units": [{"anchor": GOOD_ANCHOR}], "anchor": GOOD_ANCHOR},
                                     _sub) if _sub else None
    chk("C5 反向对照：可解析的锚点 + 真实摘录 ⇒ 走原路（不是「一律标缺口」）",
        bool(real_units) and bool(real_units.get("verbatim")) and real_units.get("anchor") == GOOD_ANCHOR,
        "摘录=%r ⇒ %s" % (_sub[:20], "解析到逐字原文" if real_units else "None"))
    chk("D4 走原路时 `resolve_anchor` 也带回 `entry_url`（两条路都要有直链）",
        str((_src0 or {}).get("entry_url") or "").startswith("https://"),
        str((_src0 or {}).get("entry_url"))[:60])

    # ══════════════════════════════════════════════════════════════════════
    # D 组 —— 依据里必须有 **L0 飞书直链**（2026-10-08，Owner 批准 D）
    # ══════════════════════════════════════════════════════════════════════
    u1 = rev._l0_entry_url(GAP_ANCHOR)
    chk("D1 没有 fields 的 L0 件也能取到直链（这正是缺口路径要的）",
        str(u1 or "").startswith("https://momcozy-in.feishu.cn/"), str(u1)[:70])
    chk("D2 反向对照：**不是记录 id 的锚点** ⇒ 返回 None（不猜、不拼）",
        rev._l0_entry_url("#l.1-0") is None, str(rev._l0_entry_url("#l.1-0")))

    # D3 ★ 端到端：报告正文里必须真的出现飞书直链
    import tempfile
    if gap_fs:
        d = tempfile.mkdtemp(prefix="covreport_")
        try:
            p = rev.write_report({"state": res["state"], "findings": gap_fs,
                                  "unmet_citation": res["unmet_citation"], "trace": res["trace"]},
                                 rev.load_registry(), d, "selftest-gap", apply=True)
            body = open(p, encoding="utf-8").read() if p else ""
            chk("D3 ★ 端到端：报告正文里**真的有**飞书直链",
                "momcozy-in.feishu.cn" in body and "L0 飞书直链" in body,
                "报告 %d 字" % len(body))
        finally:
            import shutil as _sh
            _sh.rmtree(d, ignore_errors=True)

    # ══════════════════════════════════════════════════════════════════════
    # A 组 —— 案例进覆盖池（2026-10-08，Owner 批准 A）
    # ══════════════════════════════════════════════════════════════════════
    cases = rev.load_case_clauses()
    chk("A1 只收 `polarity=反例` 且 `reason_category≠unknown` ⇒ 实测 239 条（296 − 57）",
        len(cases) == 239, "收进 %d 条" % len(cases))
    chk("A2 反向对照：`unknown` 分类与正例**一条都不许进池**",
        all(str(c.get("reason_category") or "").lower() != "unknown" for c in cases)
        and all(c.get("polarity") == "反例" for c in cases),
        "含 unknown 的 %d 条" % sum(1 for c in cases if str(c.get("reason_category") or "").lower() == "unknown"))

    # A3 第四路：命中案例锚点 ⇒ covered_by=case
    C_ANCHOR = "#正面和负面样本/REC-A/原文反馈"
    by4, det4 = rev.coverage_judge(rows((C_ANCHOR, THR + 1)), set(), set(), THR,
                                   case_anchors={C_ANCHOR}, case_resources={"REC-A"})
    chk("A3 ★ 命中 L4 定稿「反例」条款 ⇒ covered_by=case", by4 == "case", by4)

    # A4 反向对照：案例池为空 ⇒ **不覆盖**（不许因为「加了这一路」就把没命中的也放行）
    by5, _ = rev.coverage_judge(rows((C_ANCHOR, THR + 1)), set(), set(), THR)
    chk("A4 反向对照：案例池为空 ⇒ 仍**不覆盖**（没命中的不许放行）", by5 == "", by5)

    # A5 ★★ 端到端：拿**库内那条真实素材的文字**跑整条链 —— 复现 Owner 上报的那一单
    #   改前：`covered_by=""` + `reason_code=coverage_not_covered` + 依据栏空
    #   改后：`covered_by="case"` + findings 里出现 `S-1.99`（带锚点与 L0 直链）
    ocr_path = os.path.join(ROOT, "kb", "l1", "media", "recvw2wE9MEpQK", "ocr.json")
    if os.path.exists(ocr_path):
        _raw = json.load(open(ocr_path, encoding="utf-8"))

        def _walk(o):
            if isinstance(o, str):
                yield o
            elif isinstance(o, dict):
                for v in o.values():
                    yield from _walk(v)
            elif isinstance(o, list):
                for v in o:
                    yield from _walk(v)
        material = " ".join(_walk(_raw))[:2000]
        res5 = rev.review(material, content_type="text", run_id="selftest-case")
        cov5 = res5["trace"]["coverage"]
        chk("A5 ★★ 端到端（真实素材）：**不再落覆盖缺口** —— covered_by=case",
            cov5.get("covered_by") == "case" and cov5.get("covered") is True,
            "covered_by=%r ｜ 池 %d 条案例" % (cov5.get("covered_by"), cov5.get("case_clause_pool", -1)))
        arts = [f.get("article_no") for f in res5["findings"] if f.get("layer", "").startswith("案例层")]
        chk("A6 ★★ 端到端：依据里**真的出现条款号**（S-…）—— 改前依据栏是空的",
            any(str(a or "").startswith("S-") for a in arts), "案例依据条款号=%s" % arts)
        cf = next((f for f in res5["findings"] if f.get("layer", "").startswith("案例层")), None)
        chk("A7 端到端：那条依据带锚点 + source_sha256 + **L0 飞书直链**（四段齐了前三段）",
            bool(cf) and bool(cf.get("anchor")) and bool(cf.get("source_sha256"))
            and str(cf.get("l0_entry_url") or "").startswith("https://"),
            str((cf or {}).get("l0_entry_url"))[:70])
    else:
        chk("A5 端到端：找得到那条素材的 OCR", False, ocr_path)

    # ══════════════════════════════════════════════════════════════════════
    # E 组 —— **依据直链的完整性**（2026-10-09，Owner：「避免下次又出现图或者
    #          文案输出的依据不带飞书链接的」）
    # ══════════════════════════════════════════════════════════════════════
    # ## 为什么另开一组 —— 旧判据 A7 为什么没挡住
    #
    # A7 只挑**一条**终端 finding（案例层那条）验它带不带直链。**实测栽在它上面**：
    # 2026-10-09 Owner 报「图片输出的依据带飞书链接了，怎么文案输出依据没带飞书链接呢？」
    # —— 文案走的是**规则层**出口（`layer="规则层"`），而那个出口**从来没给
    # `l0_entry_url`**；同期 A7 **照样全绿**。⇒ 「**某一条**有链接」≠「**每一个出口**
    # 都有链接」，而 A7 量的是前者。
    #
    # 本组按**出口（`findings.append` 站点）**判，不按样本判：
    # 以后谁再加一条出口、忘了带链接，E1 **必然红**，而 A7 不会。
    # 同一文件里 `findings.append` 共 5 处，改前**两处**没有链接来源
    # （规则层主路 / P0「依据不可逐字回源」）—— 那正是本次故障的全部成因。
    #
    # ## 判据（三条，缺一条都不算长齐）
    #   E1 静态：每个出口都要有**链接来源**（`l0_entry_url`，或非 None 的 `verbatim_source`
    #            —— 渲染层会回落取它的 `entry_url`，那是**另一个合法来源**，不是漏洞）。
    #   E2 反向对照：抹掉某处出口的直链 ⇒ E1 必须**精确**报出那一处（且只报它）。
    #            没有 E2，E1 可能是把恒真的尺子（实现成「永远无缺失」也照样绿）。
    #   E3 动态逐条：跨三条主路各跑一次真素材，**每一条** finding 都要有可点直链。
    #            静态管「代码写了没有」，动态管「运行期真填上了没有」——
    #            `_l0_entry_url()` 取不到时返回 None（**取不到就不编**，这条口径不许改），
    #            但那种情况必须**看得见**，不能静默。
    # ══════════════════════════════════════════════════════════════════════
    lines = open(REVIEW, encoding="utf-8").read().splitlines()

    def _append_blocks(ls):
        """切出每一处 `findings.append(...)` 的整块。

        按**缩进收口**，不做括号配对 —— 块里有 f-string 的 `{...}`，
        纯括号计数会被字符串里的花括号带偏（`reason` 那几行就是）。
        """
        out = []
        for i, ln in enumerate(ls):
            if "findings.append(" not in ln:
                continue
            ind = len(ln) - len(ln.lstrip())
            blk = [ln]
            for j in range(i + 1, min(i + 400, len(ls))):
                s = ls[j]
                if s.strip() == "":
                    blk.append(s)
                    continue
                if (len(s) - len(s.lstrip())) <= ind:
                    break
                blk.append(s)
            out.append((i + 1, "\n".join(blk)))
        return out

    def _has_link_src(blk):
        """这个出口有没有**链接来源**？

        ⚠️ 只认**字段级赋值**，不认注释里提到过 —— 否则一句注释就能把 E1 骗绿。
        ⚠️ `verbatim_source: None` **不算**（878 那条原来就是 None，正是缺的那两处之一）。
        """
        for q in ('"', "'"):
            if (q + "l0_entry_url" + q + ":") in blk:
                return True
            key = q + "verbatim_source" + q + ":"
            k = blk.find(key)
            if k >= 0 and blk[k + len(key):].lstrip()[:4] not in ("None", "null"):
                return True
        return False

    blocks = _append_blocks(lines)
    missing = [n for n, b in blocks if not _has_link_src(b)]
    chk("E1 ★ 静态·**每一个** `findings.append` 出口都带链接来源（l0_entry_url 或非空 verbatim_source）",
        bool(blocks) and not missing,
        "%d 处出口，缺链接来源的行号 %s" % (len(blocks), missing or "无"))

    # E2 反向对照：挑一个**抹掉 `l0_entry_url` 后真的会失去来源**的出口来变异。
    #   ⚠️ 判据要写对：不能只看「块里有没有 `verbatim_source` 这个词」——
    #   实测第一版就是这么写的，结果 5 处出口**一处都选不出来**（E2 自己红了）：
    #   878 那处`"verbatim_source": None`（有键、但**不是**链接来源）被误当成合法来源。
    #   ⇒ 正确的挑法是拿 `_has_link_src` **自己**去试：抹掉后是否真的翻转成 False。
    def _mutate(b):
        return b.replace('"l0_entry_url":', '"MUTATED_AWAY":')

    _cand = next(((n, b) for n, b in blocks
                  if '"l0_entry_url":' in b and not _has_link_src(_mutate(b))), (None, None))
    if _cand[0] is None:
        chk("E2 反向对照：抹掉一处出口的直链 ⇒ E1 **精确**报出它", False,
            "找不到「抹掉 l0_entry_url 后真的失去来源」的出口，变异无从构造")
    else:
        _n0, _b0 = _cand
        _mut = [(n, (_mutate(_b0) if n == _n0 else b)) for n, b in blocks]
        _m_missing = [n for n, b in _mut if not _has_link_src(b)]
        chk("E2 反向对照：抹掉第 %d 行出口的直链 ⇒ E1 **精确**报出它（且只报它）" % _n0,
            _m_missing == [_n0], "变异后报出 %s" % (_m_missing,))

    # E3 动态逐条 —— 三条主路各一条真素材
    _LINK_CASES = [
        ("P0 路", "经 FDA 批准，完全无痛，模拟婴儿吸吮，全网销量第一"),
        ("规则层路", "M6 吸奶器，进口医用级材质，静音低至 30 分贝，全网销量第一"),
        ("组合路", "全网销量第一，FDA 认证，完全无痛，静音 30 分贝"),
    ]
    _tot = _linked = 0
    _bad = []
    _all_f = []          # (样本名, finding) —— 留给 E4 过一遍包装层
    for _cn, _ct in _LINK_CASES:
        _r = rev.review(_ct, content_type="text", run_id="selftest-link")
        for _f in (_r.get("findings") or []):
            _tot += 1
            _all_f.append((_cn, _f))
            _u = str(_f.get("l0_entry_url")
                     or (_f.get("verbatim_source") or {}).get("entry_url") or "")
            if _u.startswith("https://"):
                _linked += 1
            else:
                _bad.append("%s／%s" % (_cn, _f.get("article_no") or _f.get("layer")))
    chk("E3 ★★ 动态·逐条：跨 %d 条主路的**每一条** finding 都带可点直链" % len(_LINK_CASES),
        _tot > 0 and not _bad, "共 %d 条，带直链 %d 条，缺 %s" % (_tot, _linked, _bad or "无"))

    # ── E4 ★★ 动态·**经包装层之后** —— 本次故障的**精确判据** ────────────────
    # 为什么 E1/E3 不够（这是本次最贵的一课，2026-10-09 实测）：
    #   把依据层（`review.py`）的两处直链补回去，**E1/E3 立刻变绿** ——
    #   而故障**仍然存在**。因为卡片读的**不是** `findings`，是包装层产出的 `risk_items`：
    #   `with_kb_evidence._to_risk_item()` 当时只认 `f["l0_entry_url"]`，
    #   **完全不看** `f["verbatim_source"]["entry_url"]`（规则层主路只有后者）
    #   ⇒ `evidence.l0_entry_url` 恒 None ⇒ `evidence_url` 退回本地路径 ⇒ 卡片没链接。
    #   ⇒ 教训：**判据必须落在「消费方真正读的那一层」**。落在产方，修好了也测不出来。
    # 本判据喂的是**真 finding**，量的是**真 risk_item** —— 中间不跳步、不构造。
    _wke_path = os.path.join(ROOT, "kb/l7/review-engine/core/with_kb_evidence.py")
    if not os.path.isfile(_wke_path):
        chk("E4 动态·经包装层：每条 finding 变成 risk_item 后仍带飞书直链", False,
            "找不到包装层 %s" % _wke_path)
    else:
        _spec2 = importlib.util.spec_from_file_location("kb_wke", _wke_path)
        _wke = importlib.util.module_from_spec(_spec2)
        _spec2.loader.exec_module(_wke)
        _rtot = _rok = 0
        _rbad = []
        for _cn, _f in _all_f:
            _it = _wke._to_risk_item(_f)
            _rtot += 1
            _ev = _it.get("evidence") or {}
            _url = str(_ev.get("l0_entry_url") or _it.get("evidence_url") or "")
            if _url.startswith("https://"):
                _rok += 1
            else:
                _rbad.append("%s／%s→%s" % (_cn, _ev.get("article_no") or _f.get("layer"),
                                            _url[:40] or "(空)"))
        chk("E4 ★★ 动态·**经包装层之后**：每条 finding 变成 risk_item 仍带飞书直链"
            "（卡片读的是这一层，不是 findings）",
            _rtot > 0 and not _rbad, "共 %d 条，带直链 %d 条，缺 %s" % (_rtot, _rok, _rbad or "无"))

    # ── E5 反向对照：包装层必须**两种来源都认** ────────────────────────────
    # ⚠️ 这条是 E4 的守卫：E4 喂的样本恰好都走 `l0_entry_url` 时，把回落删掉 E4 也照样绿。
    #    所以另立一条**结构判据**钉住回落本身 —— 删掉回落 ⇒ E5 精确变红。
    if os.path.isfile(_wke_path):
        _src = open(_wke_path, encoding="utf-8").read()
        _fallback = ('f.get("verbatim_source")' in _src) or ("f.get('verbatim_source')" in _src)
        chk("E5 反向对照：包装层源码里**确实**回落读 `verbatim_source.entry_url`"
            "（删掉它就精确变红）",
            _fallback, "回落已在位" if _fallback else "包装层未见 verbatim_source 回落")

    # ── E6 ★ 报告侧：`l0_locate` 不许把 L0 的**路径形态写死** ──────────────
    # 病灶（2026-10-09，Owner 问「依据溯源都会带命中逐字原文+飞书链接了吧」时查出来）：
    #   `feishu_publish.l0_locate` 的 glob 原是 `l0/*/*<rec>.json` —— **只认「两层 + 带前缀」**。
    #   而 L0 件有两种**真实并存**的命名／深度：
    #     · `l0/<分类>/feishu_bitable_record__<base>__<rec>.json`（**带前缀**，两层，1536 份）
    #     · `l0/records/<表名>/<rec>.json`                       （**纯 rec 名**，三层，1813 份）
    #   ⇒ 第二种那 1813 份它**永远返回 None** ⇒ 报告/云文档里那条
    #     只有本地路径、没有「L0 定位（源数据·飞书）」。
    #   ⚠️ 同一锚点、**同一份 L0 件**：`l0_verbatim()` 找得到、`l0_locate()` 找不到
    #   ⇒ 报告里分裂成「**有逐字核对的没有直链，有直链的没有逐字核对**」。
    # 判据：**从两种形态各抽真实 L0 件，两边都必须给得出 entry_url**。
    #   ⚠️ **抽样必须按「文件名形态」抽，不能按目录深度抽** —— 实测第一版按深度抽
    #   （`l0/*/rec*.json`），结果是「**一层 0 份抽样**」：带前缀那 1536 份**一份都没进样本**，
    #   判据成了摆设。**抽样抽不到 = 没测**。（这条判据正是这样照出了我自己的第一版 bug。）
    _l0root = os.path.join(ROOT, "kb", "l0")

    def _rec_of(path, prefixed):
        b = os.path.basename(path)[:-5]
        return b.split("__")[-1] if prefixed else b

    _pre_all = glob_mod.glob(
        os.path.join(_l0root, "*", "feishu_bitable_record__*_rec*.json"))
    # 「纯 rec 名」要**全库任意深度**地找（不能只扫 `records/`）——
    #   实测踩过第二回：只扫 `records/` 时，一条「仅带前缀」的记录若在 `_archive/<表>/<rec>.json`
    #   下还有纯名孪生件，就会被误判成「专属」，于是把带前缀那套 glob 改坏也照样解析得到
    #   ⇒ **判据又绿了**。「专属」必须是**全库范围**的专属。
    _pln_any = glob_mod.glob(os.path.join(_l0root, "**", "rec*.json"), recursive=True)
    _pre_ids, _pln_ids = set(), set()
    for _p in _pre_all:
        _pre_ids.add(_rec_of(_p, True))
    for _p in _pln_any:
        _pln_ids.add(_rec_of(_p, False))
    # ★★ **必须抽「只存在于一种形态」的记录**（这一步是这条判据成不成立的关键）。
    #   实测踩过：第一版直接取前 6 份，而**同一个 rec 常常在两种形态下都有孪生件**
    #   ⇒ 把任一种形态的 glob 改坏，抽样里的记录照样能靠**另一个形态**解析出来
    #   ⇒ **判据全绿，而 bug 就在眼前**（两次变异都没抓住）。
    #   挑「专属记录」之后，改坏任一形态 ⇒ 那一组必然报 None ⇒ 判据精确变红。
    _only_pre = sorted(_pre_ids - _pln_ids)[:6]
    _only_pln = sorted(_pln_ids - _pre_ids)[:6]
    # ⚠️ 实测澄清（2026-10-09，别把它当成判据的缺陷）：
    #   收紧到「全库范围的专属」之后，**`仅带前缀` 恒为 0 份** —— 全库没有任何记录
    #   **只**以带前缀形态存在，每条都有纯名孪生件。⇒ 本条判据**载重的是 `仅纯 rec 名` 那一组**
    #   （正是原始两层 glob 漏掉的那 1813 份）；带前缀那组是**条件项**：有就一起判，
    #   没有不算失败（**不许**为了凑非空而把断言写死成「两组都必须非空」—— 那会让判据
    #   因为一个不成立的前提而永远红）。
    _fp_path = os.path.join(ROOT, "kb/l7/review-engine/core/feishu_publish.py")
    if not os.path.isfile(_fp_path):
        chk("E6 报告侧·两种 L0 形态都要拿得到飞书直链", False, "找不到 %s" % _fp_path)
    else:
        _spec3 = importlib.util.spec_from_file_location("kb_fp", _fp_path)
        _fp = importlib.util.module_from_spec(_spec3)
        _spec3.loader.exec_module(_fp)
        _probe = ([("仅带前缀/两层", r) for r in _only_pre]
                  + [("仅纯rec名/三层", r) for r in _only_pln])
        _lok = 0
        _lbad = []
        for _lay, _rec in _probe:
            _r6 = _fp.l0_locate("#x/%s/f" % _rec, None)
            if (_r6 or {}).get("entry_url"):
                _lok += 1
            else:
                _lbad.append("%s/%s" % (_lay, _rec))
        chk("E6 ★ 报告侧：`l0_locate` 对**只在三层纯 rec 名形态下存在**的记录也给得出飞书直链"
            "（专属记录抽样：仅纯 rec 名 %d 份／仅带前缀 %d 份）—— 不许把路径形态写死"
            % (len(_only_pln), len(_only_pre)),
            # 载重组必须**非空**（抽了个空 = 没测），且抽到的必须全部解析得出。
            bool(_only_pln) and not _lbad,
            "专属记录抽样 %d 份（仅纯rec名 %d／仅带前缀 %d），拿到直链 %d 份，缺 %s"
            % (len(_probe), len(_only_pln), len(_only_pre), _lok, _lbad or "无"))

    n_fail = len(F)
    print("\n自证：通过 %d / 失败 %d" % (len(P), n_fail))
    for x in F:
        print("  · 失败：%s" % x)
    return 1 if n_fail else 0


if __name__ == "__main__":
    os.environ.setdefault("KB_ENTRY", "selftest")
    sys.exit(main())
