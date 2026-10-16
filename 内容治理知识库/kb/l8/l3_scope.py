#!/usr/bin/env python3
"""l3_scope.py —— L3 蒸馏的**范围判据**：唯一一把尺子（两个引擎都 import 它）

为什么有这份文件（2026-10-08，实测缺陷）
────────────────────────────────────────────────────────────────
「哪些 L2 单元进得了 L3」这条判据原先**只内联在 `kb/l8/l3_distill_run.py` 里**，
而 `kb/l8/l3_reject_ledger_rebuild.py`（拒绝台账重建）**不知道它**。后果是三层叠加的：

  ① 活引擎在过滤里按 `out_of_scope_table` 剔掉整批单元 —— 它们**从未进门**；
  ② 台账却按「没被规则引用 ⇒ 拒绝」+ 按 `unit_type` 套一句通用理由，把这批写成
     「纯文案样本：源表未给出命中判定或修订建议（sample_only_no_verdict）」；
  ③ `kb/l3/rejected.jsonl` 里 `out_of_scope_table` 出现 **0 次**
     ⇒ **真实剔除原因在台账里完全不可见。**

实测代价（不是假设）：2026-10-08 排查「负面样本 170 条为什么不蒸馏」，
照着台账那句「源表未给出命中判定或修订建议」走，**结论方向整个错掉** ——
那张表其实有 `原因分类`(120/170 非空)、`具体原因/分析`(170/170)、`建议`(**99/170 非空**)。
真实原因是：**那道门压根没让它们进**，而门里也没有把它们做成引擎要的 `revision_pair` 形态。

本模块的作用
────────────────────────────────────────────────────────────────
把判据**搬家**到一处，两边都 import ⇒ 「两把尺子」在结构上不可能分叉。
**本次只搬家，不改判据** —— 与 `l3_distill_run.py` 原内联块逐字一致。
改动判据必须同时被两个消费者看到，这正是本模块存在的理由。

边界
────────────────────────────────────────────────────────────────
· 本模块**只**回答「这个单元进不进 L3、不进的话原因码是什么」，
  不产出规则、不写任何文件、不读 kb/l2 与 kb/l3。
· 它读 `kb/l0/registry/kb.json` 的 `field_roles`（与原引擎同一路径、同一失败方式：
  文件缺失即抛，**不静默降级** —— 静默降级会悄悄改写 METADATA_FIELDS 的成员）。
"""
import json
import os
import importlib.util
from types import SimpleNamespace

# ── ★2026-10-12：`content_quality_flag` 的放行白名单 —— **从唯一真源取，不许在此再抄一份** ──
#   缺陷（实测，Owner 批准修）：L6（`kb/.work/l6_scope_lib.py`）有 `GOOD_QUALITY_FLAGS` 放行名单，
#   而**本模块没有** ⇒ 同一个 flag 两层读成相反的意思 ⇒
#   1,005 条真内容被挡在 L3 之外（含 10/19–10/23 行 #1 要的 FDA 8/8、自有站 714/934）。
#   真源 = `kb/l8/quality_flags.py`（同一目录，紧挨本文件）。L3 与 L6 都 import 它。
#   ★ 不静默降级：真源读不到就**抛**，不许退回「没有白名单」——那会悄悄把缺陷放回来。
def _load_good_quality_flags():
    _p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "quality_flags.py")
    _spec = importlib.util.spec_from_file_location("kb_l8_quality_flags", _p)
    if _spec is None or _spec.loader is None:
        raise RuntimeError(f"quality_flags.py 读不到（{_p}）⇒ 拒绝在缺白名单的情况下运行")
    _m = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_m)
    return _m.GOOD_QUALITY_FLAGS


GOOD_QUALITY_FLAGS = _load_good_quality_flags()

# 与原引擎同一套原因码（`l3_distill_run.py` 的 FILTER 键）
CODES = ("out_of_scope_kb", "out_of_scope_table",
         "metadata", "metadata_unknown_field", "quality_flag",
         # ★ 2026-10-10 加（PRD §2.2）：已声明排除的记录，其单元不许成为规则或依据。
         "rule_eligible_false")

# ══════════════════════════════════════════════════════════════════════════
# ★★ 2026-10-08 **Owner 裁定：开这道门**（原先只收「专家修订汇总表」）
# ══════════════════════════════════════════════════════════════════════════
# 原判据（本节改动前，逐字）：
#     `if kb == "internal_sample" and (u["meta"] or {}).get("table") != "专家修订汇总表":`
# ⇒ `负面样本` / `正面和负面样本` 两张表**整批被剔**（实测 736 条），
#   后果不是「蒸不出来」，是**从未进门**；而同一批单元**在样例侧还在被用**
#   （402 个 case 引用了其中 201 条）⇒ 引擎自相矛盾。矛盾与数字登记在
#   `kb/l7/registry/ledger-read-contract.yaml::out_of_scope_table_vs_sample_cases`，
#   条目的 `not_done` 原文是「供 Owner 裁定；裁定前不写盘」。
#
# Owner 2026-10-08 的决定：**开**，但分两步 ——「先跑 2 个数据，流程跑通，
#   验证通过后，跑全部的」。本常量即为「开」的落点。
#
# ★ 边界（只说这一步开了什么、没开什么）：
#   · 只**扩表**：`internal_sample` 从 1 张表扩到 3 张表；`wording` / `external_standard`
#     两类**一个字没动**；`metadata` / `metadata_unknown_field` / `quality_flag` 三道门
#     **一个字没动**；`out_of_scope_kb` 一个字没动。
#   · **不是放宽判据**：门里那三张表本来就有 `原因分类` / `具体原因/分析` / `建议`
#     （实测 负面样本：`原因分类` 120/170、`具体原因/分析` 170/170、`建议` 99/170 非空），
#     进得来之后照样要过 `revision_pair` 形态与后续每一道闸。
# ── ★2026-10-13：`INTERNAL_SAMPLE_TABLES` 也**搬家到唯一真源**，本处只取、不再自己写一份 ──
#   这是「同一个常量两份定义」的**第二个标本**（第一个是 `GOOD_QUALITY_FLAGS`，已在上方修掉）。
#   `quality_flags.py` 头部当时就登记了它「各写了一份 … 本次未一并合并」——本行就是那次登记的落地。
#   真源 = `kb/l8/internal_sample_tables.py`（同一目录，紧挨本文件）。
#   ★ 注意（**别顺手统一**）：合并的是**名单**，不是**判据**。
#     L6 那侧另有一道 `_is_bitable` 守卫（2026-10-08 为修假阳性所加），本模块没有；
#     实测因此有 **386 条**结论不同。那是**已登记、未裁**的分歧，
#     要动它会改 L3 蒸馏输出 ⇒ 改评审链召回。见该文件头部与
#     `核定-internal_sample两把尺子的386条分歧-20261013.md`。
#   ★ 不静默降级：真源读不到就**抛**。
def _load_internal_sample_tables():
    _p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "internal_sample_tables.py")
    _spec = importlib.util.spec_from_file_location("kb_l8_internal_sample_tables", _p)
    if _spec is None or _spec.loader is None:
        raise RuntimeError(f"internal_sample_tables.py 读不到（{_p}）⇒ 拒绝在缺名单的情况下运行")
    _m = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_m)
    return _m.INTERNAL_SAMPLE_TABLES


INTERNAL_SAMPLE_TABLES = _load_internal_sample_tables()


def _src_table_of(u):
    """这个 L2 单元来自哪张表？**两批入库件写法不同，得三处都认**（2026-10-08 实测）。

    为什么不能只看 `meta.table`（原判据的写法）：
      · 「专家修订汇总表」那批：`meta.table` 有值 ⇒ 原判据认得出；
      · 「正面和负面样本」那批：`meta = {field_name: null, kind: "sample", source_fields: [...]}`
        —— **没有 `table` 键**；
      · 「负面样本」那批：`meta = {field_name: "负面样本", kind: "paragraph"}`
        —— **把表名塞进了 `field_name`**。
    ⇒ 只看 `meta.table` 的后果：**除了第一批，其余全被判成「不在范围内」**（实测 233/233 被挡），
      而人看到的理由还是「它来自某张表」——**理由里那个来源名，正是判据自己读不出来的那个字段**。
    取值顺序：`meta.table` → `heading_path` → `meta.field_name`。
      `heading_path` 两批都可靠（旧批 `正面和负面样本`、新批 `负面样本`），列在中间当兜底。
    """
    meta = u.get("meta") or {}
    for v in (meta.get("table"), u.get("heading_path"), meta.get("field_name")):
        s = str(v).strip() if v is not None else ""
        if s:
            return s
    return "（meta 未给来源）"


def build_scope(l0_registry_path="kb/l0/registry/kb.json"):
    """构造范围判据。`l0_registry_path` 与原引擎同一路径口径。

    返回带 `CONTENT_FIELDS` / `METADATA_FIELDS` / `L0_FR` / `frole()` / `exclusion_of()` 的对象。
    """
    with open(l0_registry_path, encoding="utf-8") as f:
        l0reg = json.load(f)
    L0_FR = l0reg["field_roles"]

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
        "知识库分类", "材料审核状态", "From", "细分", "备注", "更新频率", "agent使用范围", "负责人",
        *[k for k, v in L0_FR.items() if v in ("status", "other", "link", "attachment")],
    }

    def frole(n):
        return "content" if n in CONTENT_FIELDS else ("metadata" if n in METADATA_FIELDS else "unknown")

    def exclusion_of(u):
        """这个 L2 单元进不进 L3？

        返回 `(code, detail)`：进得去 ⇒ `(None, None)`；进不去 ⇒ 原因码 + 人话解释。
        **判据与原引擎内联块逐字一致**（只把 `u["x"]` 换成 `u.get("x")`，
        对缺字段的脏行由「抛」变「跳过」；实测 12266 条单元两者结果全等，见迁移时的等价性核对）。
        """
        kb = u.get("kb_type")
        if kb not in ("wording", "external_standard", "internal_sample"):
            return ("out_of_scope_kb",
                    f"kb_type={kb!r} 不在 L3 蒸馏范围（只吃 wording / external_standard / internal_sample）")
        # ── ★★ 2026-10-10 加：**PRD §2.2 排除项不许进 L3** ──────────────────────
        #  这是「已声明不许成为依据」的记录，`rule_eligible=false` 由
        #  `kb/l0/registry/kb.json → rule_eligible_overrides` 声明（权威登记件
        #  `kb/l7/registry/source-readonly.yaml → prd_scope_exclusions`），
        #  L1 manifest 与 L2 units 已按它落值（`kb/l8/apply_rule_eligible_overrides.py`）。
        #
        #  ★ 为什么必须补在**这里**（实测缺陷，不是预防性设计）：
        #    目标 23 的落地只覆盖到 **L2**（判据 `check_source_readonly.py` 的 C8 只量
        #    `kb/l2/units.jsonl`），**L3 是漏的**。实测 2026-10-10：
        #    那 3 份红人 Brief 在 `kb/l3/candidates/scoped_clauses.jsonl` 里产出
        #    **94 条候选**，**全部已拿到 E-1 条款号**（E-1.1275 / E-1.2103 / …）。
        #    正文就是 Brief 本身（`MOMCOZY · CREATOR CONTENT BRIEF …`）。
        #    ⇒ 不补这一道，那 94 条会随「定稿 → 接消费者」变成**可引用依据**，
        #      正好是 PRD §2.2「不审 brief」要避免的事。
        #
        #  ★ 判据放在**这一把共用尺子**上（两个引擎都 import 它）⇒ 拒绝台账重建
        #    （`l3_reject_ledger_rebuild.py`）也会看到同一个口径，不会又分家。
        if u.get("rule_eligible") is False:
            return ("rule_eligible_false",
                    "该单元来自**已声明排除**的记录（PRD §2.2 非目标：不审 brief / 脚本 / AI 文案"
                    "等生产中间物）⇒ `rule_eligible=false`，**留在库里可读，但不许成为规则或依据**"
                    "（判据 `check_source_readonly.py` 的 C8）")
        if kb == "internal_sample" and _src_table_of(u) not in INTERNAL_SAMPLE_TABLES:
            return ("out_of_scope_table",
                    f"internal_sample 只收 {INTERNAL_SAMPLE_TABLES}，本单元来自「{_src_table_of(u)}」"
                    " ⇒ 在活引擎第一道过滤就被剔，**从未进入蒸馏**（不是「蒸不出来」）")
        if u.get("unit_type") == "entry" and frole(u.get("heading_path")) != "content":
            r = "metadata" if frole(u.get("heading_path")) == "metadata" else "metadata_unknown_field"
            return (r, "登记型字段值（元数据），不含可判定内容")
        if (u.get("meta") or {}).get("content_quality_flag") not in (None, "") \
                and (u.get("meta") or {}).get("content_quality_flag") not in GOOD_QUALITY_FLAGS:
            # ★2026-10-12 改：原为 `if (...).get("content_quality_flag"):` —— **真值判断、无白名单**，
            #   于是把 L6 已判定为「干净正文」的标记（Owner 2026-09-29 / 09-30 两次核定）
            #   也一并挡掉。现在与 L6 **同一个判断式、同一份名单**（真源 `kb/l8/quality_flags.py`）。
            #   注意 `flag == "ok"` **仍然照挡** —— 那 977 条实测是 CDN 图片 URL 汤，
            #   属另一个独立缺陷（见 `核定-自有站与FDA为何不成规则-两把尺子-20261012.md` §4）。
            #   名单里**不在**的标记，行为与改动前**逐字一致**（照挡）。
            return ("quality_flag", "上游标了 content_quality_flag（且不在「干净正文」白名单里）⇒ 不进蒸馏")
        return (None, None)

    return SimpleNamespace(CONTENT_FIELDS=CONTENT_FIELDS, METADATA_FIELDS=METADATA_FIELDS,
                           L0_FR=L0_FR, frole=frole, exclusion_of=exclusion_of, CODES=CODES)


# ══════════════════════════════════════════════════════════════════════════
# 拒绝口径：**「拒绝」到底指哪一批单元**（Owner 2026-10-08 裁定取 C）
# ══════════════════════════════════════════════════════════════════════════
#
# 为什么要有这一节：库里有**两个写入者**都在往「拒绝台账」里写，而它们算的
# **不是同一个集合**（实测：2581 vs 8103）。不先定口径，分家就是把两份不同的东西
# 塞进一个文件 —— 只是把「重复」换成「矛盾」。
#
# 三套口径（2026-10-08 实测于本库）：
#
#   A 活引擎   = kept − rule        = **2581**
#      毛病：含 **361** 条「被样例用了」的 —— 它们其实已经被用上，不该算拒绝。
#      （登记在 kb/l3/registry/l3.json → accounting.explicitly_rejected）
#
#   B 重建脚本 = all − rule − case  = **8103**
#      毛病：含 **5883** 条「被门剔掉的」—— 它们压根没参与蒸馏，
#      那是**范围问题**（门没覆盖），不是「拒绝」。
#
#   C ★权威★  = kept − rule − case = **2220**   ← Owner 2026-10-08 裁定
#      含义：**进了门、蒸馏跑了、但这单元没成规则** —— 这正是「拒绝台账」的原义。
#
# 分解（实测）：C 2220 ／ 只在A不在B 361（=A−C）／ 只在B不在A 5883（=B−C）
#   校验：2220 + 361 = 2581 ✓ ｜ 2220 + 5883 = 8103 ✓
#
# ★★ 与「范围外」的关系（别混）：被门剔掉的 5883 条**不属于任何口径的「拒绝」**。
#   它们是 `exclusion_of()` 的产物 —— 即**本模块本身就能重算的纯函数**，
#   所以**不必存快照**，要清单时现算：
#       [u for u in L2单元 if exclusion_of(u)[0]]
#   这条设计避免了「为了看得见范围外，就得把它也算进拒绝」这个错误合流。
#
# ★ 一处必须写明的事实：C 里的「没被样例用」比的是 `kb/l3/candidates/sample_cases.jsonl`，
#   而该文件 **2026-10-01 10:07 起冻结**（只有 `.work/batch7_*`/`batch8_run.py` 这些
#   **历史一次性脚本**写过它；`layers.yaml` 声明的三个 L3 引擎**都不读写它**）。
#   ⇒ 「被样例用」是一个**冻结判据**：口径稳定、可复算、不漂。
#     这是好事，但**别把它读成「样例还在演进」**。

#: 三套口径的代号 → (人话名字, 是否权威)
CALIBERS = {
    "A": ("kept − rule_cited（活引擎原口径）", False),
    "B": ("all − rule_cited − case_cited（重建脚本原口径）", False),
    "C": ("kept − rule_cited − case_cited（★权威，Owner 2026-10-08 裁定）", True),
}
AUTHORITATIVE_CALIBER = "C"


def rejection_sets(all_ids, kept_ids, rule_cited, case_cited):
    """按三套口径算拒绝集，返回 `{"A": set, "B": set, "C": set}`（纯函数，可断言）。"""
    all_ids, kept_ids = set(all_ids), set(kept_ids)
    rule_cited, case_cited = set(rule_cited), set(case_cited)
    return {
        "A": kept_ids - rule_cited,
        "B": all_ids - rule_cited - case_cited,
        "C": kept_ids - rule_cited - case_cited,
    }


def out_of_scope_units(units, scope):
    """**范围外**清单（被门剔掉的）—— 与「拒绝」分开的另一个指标。

    它是 `scope.exclusion_of()` 的纯函数产物，故**不存快照、随时现算**。
    （`scope` 由 `build_scope(...)` 给出 —— `exclusion_of` 是它的闭包，不是模块级函数。）
    """
    return [(u, scope.exclusion_of(u)) for u in units if scope.exclusion_of(u)[0]]
