#!/usr/bin/env python3
"""L3 规则维度派生（PRD §6.5 风险等级 / 适用范围 ＋ §5.2 模态）。

## 这个模块解决什么

任务拆解 10/12–10/16 行目标 6 / 7 / 8 要求每条规则带上：

| 字段 | PRD 出处 | 要求 |
|---|---|---|
| `risk_level` | §6.5 | **Critical / High / Medium / Low** |
| `applicable_scope` | §6.5 | 适用产品线 / 渠道 / 内容类型 |
| `modality` | §5.2 | 文字 / 图片 / 视频 |

## 为什么要单开一个模块（而不是在蒸馏器里就地补）

`l3_distill.py` 的 `METADATA_FIELDS` 把 **`风险等级`** 显式写进了「元数据」集合 ⇒
字段角色判定为 metadata ⇒ 蒸馏时**丢掉**；然后在 5 条产出路径里，
**只有 1 条**读了风险等级（`l3_distill.py:143/160/161`），
另外 4 条**写死** `p_level="P1", risk_level="unknown"`（:197 / :222 / :248）。
⇒ 结果是 509 条里 **488 条 risk_level=unknown**，而信号一直在源表里。

所以这里把「派生」收成一个**纯函数模块**，蒸馏器与回填脚本共用同一份口径 ——
**不许在别处再写第二份**（与 `kb_governance.py` 同一套做法）。

## 三条纪律

1. **不编。** 源里取不到的，落 `None` ＋ 写进 `derive` 的出处；**不许**用常识补齐。
2. **每个值带出处。** 返回 `derivation` 字典，写明每个字段是从哪来的（源字段名 / 派生依据）。
3. **纯函数。** 不读盘、不写盘；读盘只在 `main` 的探针里做。

## 用法

    python3 kb/l3/kb_rule_dimensions.py --selftest      # 判据自证（不碰真库）
    python3 kb/l3/kb_rule_dimensions.py --probe         # 只读探针：对真库跑一遍，报覆盖缺口
"""

from __future__ import annotations

import argparse
import collections
import glob
import json
import os
import sys

KB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RULES_DEFAULT = os.path.join(KB, "l3", "candidates", "rules.jsonl")
L0_RECORDS = os.path.join(KB, "l0", "records")

# ══════════════════════════════════════════════════════════════════
# 1. 风险等级：源 4 级 → PRD §6.5 的 Critical / High / Medium / Low
# ══════════════════════════════════════════════════════════════════

#: 源「风险等级」字段的取值 → PRD 四级。**这是换词表，不是补空值。**
#: 源侧带色标后缀（如 `高危·红`）⇒ 比对时取 `·` 前的部分。
RISK_LEVEL_MAP = {
    "高危": "Critical",
    "审慎": "High",
    "待复核": "Medium",   # 「待复核」表达的是「需复核确认」而非严重度，取中位；见 NOT_DERIVABLE 说明
    "合规": "Low",
}

#: ★★ 2026-10-12：**四档批量兜底 `P_LEVEL_TO_RISK` 已删除**（它正是本次要修的病）。
#:
#: 旧版：源 `风险等级` 缺失时按 `p_level` 映射（P0→Critical / P1→High / P2→Medium / P3→Low）。
#: 代价（实测）：**840/1018 条**全部落到 `P1 → High` ⇒ **整批同一档、零区分度**。
#: 根因是**拿错了轴** —— `p_level` 是 PRD **§6.2 的优先级层级**，`risk_level` 是
#: **§6.5 的风险等级**，两个轴不能互相顶替。
#:
#: 现在只保留 **P0 一条地板**：
P0_FLOOR = {
    "p_level": "P0",
    "risk_level": "Critical",
    "basis": "层级地板：p_level=P0（PRD §7.3 逐字「命中即驳回，不进入后续审查层级」）",
}

#: 维度 2：源字段「灯色状态」→ **复用既有换词表的色标语汇**（源 `高危·红` / `审慎·黄` /
#: `合规·绿` 用的就是这一套）⇒ 不是新造口径，是向既有口径对齐。
LAMP_COLOR_TO_RISK = {
    "红": "Critical",   # 与 源「高危·红」同档
    "黄": "High",       # 与 源「审慎·黄」同档
    "绿": "Low",        # 与 源「合规·绿」同档
}

#: 维度 3：源字段「修订类型」（专家**逐条手填**的「这条修订是什么性质」）→ PRD §6.2 四档。
#: 值形如 `科学性纠错` / `表述精确化/去绝对化`（复合值按 `/` 拆、**取最高档**）。
#: 每项第三格 `hard`：True = 直接引 PRD 原文；False = **软判**（按 §6.2 四层语义归类）。
REVISION_TYPE_TO_RISK = {
    # High —— PRD §6.2 P1「消费者安全、产品描述准确性」
    "去绝对化": ("High", "PRD §6.2 P1 消费者安全（表述缺少适用边界；**非** §7.3-3 广告绝对化用语）", False),
    "安全警示强化": ("High", "PRD §6.2 P1 消费者安全", True),
    "安全提示补充": ("High", "PRD §6.2 P1 消费者安全", True),
    "安全提示": ("High", "PRD §6.2 P1 消费者安全", True),
    "禁忌说明补充": ("High", "PRD §6.2 P1 消费者安全", True),
    "高风险人群提示": ("High", "PRD §6.2 P1 消费者安全", True),
    "就医指征完善": ("High", "PRD §6.2 P1 消费者安全", False),
    "就医时间阈值收紧": ("High", "PRD §6.2 P1 消费者安全", False),
    "用药安全提示": ("High", "PRD §6.2 P1 消费者安全", False),
    "护理方式纠正": ("High", "PRD §6.2 P1 消费者安全", True),
    "护理方式修正": ("High", "PRD §6.2 P1 消费者安全", True),
    "动作指导补全": ("High", "PRD §6.2 P1 消费者安全（错误示范/危险使用）", True),
    "产品信息更新": ("High", "PRD §6.2 P1 产品描述准确性", True),
    "适用范围说明": ("High", "PRD §6.2 P1 产品描述准确性（功能边界/型号差异）", False),
    # Medium —— PRD §6.2 P2「通识与常识」
    "科学性纠错": ("Medium", "PRD §6.2 P2 通识与常识", True),
    "科学性补充": ("Medium", "PRD §6.2 P2 通识与常识", True),
    "科学性完善": ("Medium", "PRD §6.2 P2 通识与常识", True),
    "表述对齐指南": ("Medium", "PRD §6.2 P2 通识与常识（与权威指南一致）", False),
    "医学内容补充": ("Medium", "PRD §6.2 P2 通识与常识", False),
    "内容补充": ("Medium", "PRD §6.2 P2 通识与常识", False),
    "参考文献规范": ("Medium", "PRD §6.2 P2 通识与常识（依据来源）", False),
    "内容逻辑优化": ("Medium", "PRD §6.2 P2 通识与常识（场景合理性）", False),
    "逻辑清晰化": ("Medium", "PRD §6.2 P2 通识与常识", False),
    "内容不准确": ("Medium", "PRD §6.2 P2 通识与常识", False),
    "内容方向性修改": ("Medium", "PRD §6.2 P2 通识与常识", False),
    "内容修订": ("Medium", "PRD §6.2 P2 通识与常识", False),
    "概念澄清": ("Medium", "PRD §6.2 P2 通识与常识", False),
    "决策支持完善": ("Medium", "PRD §6.2 P2 通识与常识", False),
    "文章定位调整": ("Medium", "PRD §6.2 P2 通识与常识", False),
    # Low —— PRD §6.2 P3「措辞与表达（不涉及硬性拦截）」
    "表述精确化": ("Low", "PRD §6.2 P3 措辞与表达", True),
    "表述完善": ("Low", "PRD §6.2 P3 措辞与表达", True),
    "表述温和化": ("Low", "PRD §6.2 P3 措辞与表达", True),
    "表述简化": ("Low", "PRD §6.2 P3 措辞与表达", True),
    "术语规范": ("Low", "PRD §6.2 P3 措辞与表达", True),
    "内容删减": ("Low", "PRD §6.2 P3 措辞与表达", True),
    "删减": ("Low", "PRD §6.2 P3 措辞与表达", True),
    "文章整体重写建议": ("Low", "PRD §6.2 P3 措辞与表达", True),
    "内容分类调整": ("Low", "PRD §6.2 P3 措辞与表达", True),
    "标题修改建议": ("Low", "PRD §6.2 P3 措辞与表达", True),
    "过度警示修正": ("Low", "PRD §6.2 P3 措辞与表达（反向：降警示力度）", False),
    # unknown —— 专家自己标了「存疑/待讨论」，**不替它定级**
    "存疑/待讨论": (None, "源字段 修订类型=存疑/待讨论 ⇒ **不编**，留 unknown", True),
}

#: 四档的高低序（复合值取最高档时用）
RISK_ORDER = {"Critical": 3, "High": 2, "Medium": 1, "Low": 0}

#: `risk_level` 的「还没判」哨兵 —— **不是空**，与 `modality` 的 `undetermined` 同一个角色
#: （见 `SENTINEL_VALUES` 的说明）。★ 2026-10-12 加：此前 `risk_level_of()` 返回 `None`，
#: 而回填器有一条「推不出就不写 null 占位」的守卫 ⇒ 那 1 条规则（源 `修订类型=存疑/待讨论`）
#: **在文件里留着旧的 `High`** —— 一个已经没有依据的错值。而日更走 `apply_dimensions` 会写
#: `null` ⇒ **两个产出者写出两个值**。现在两边都出哨兵，口径只剩一份。
RISK_LEVEL_UNKNOWN = "unknown"

#: **「未知」哨兵** —— 这些取值不是「已有答案」，是「还没判」的占位。
#: 回填时它们**必须被当成空**，否则回填永远不生效（实测踩过：509 条全被报成冲突）。
SENTINEL_VALUES = frozenset({"unknown", "undetermined", "n/a", "none", "待定", "未知"})

#: 明确记录「哪些字段推不出来」，避免以后有人以为漏做
NOT_DERIVABLE = {
    "modality":
        "★★ 2026-10-12 穷尽复核（任务拆解 10/12–10/16 必须做 #3）：**509 条规则全部推不出模态**。"
        "取证四条，缺一条都不算查过："
        " ① **5 张锚点表的字段逐个列过，没有一张有媒体列** —— "
        "`专家修订汇总表`（修订位置（原文引用）/修订内容/修订原因/修订类型/文章标题）、"
        "`风险文案改写建议库（分型号分渠道）`（16 字段）、`品线内容边界规则库`（12 字段）、"
        "`W1卖点表达边界（品线反馈0910）`（8 字段）、`广告文案明细`（27 字段，媒体类只有 `落地页URL`）；"
        " ② **锚点字段名 0 个含媒体专名**（实测只有 5 种：`修订位置（原文引用）` 401 ／ `风险原句示例` 52 ／ "
        "`边界内容` 21 ／ `建议表达（合规话术）` 19 ／ `命中片段` 16）；"
        " ③ **0 条规则锚在 `负面样本`** —— 而**全库唯一有媒体字段的表就是它**"
        "（`素材类型` 图片 168 ／ 文字 2 ＋ `图片素材` ／ `视频素材` ／ `文字素材`）"
        " ⇒ **信号在库里，只是不在规则的路径上**；"
        " ④ 正文模态词**已实测不可靠**（「文字」139 : 「图片」6 : 「视频」5，且 6/5 是同一句"
        "『文案为空/非文本广告』的说明）。"
        " ⇒ 原一律落 `undetermined`。★★ **2026-10-12 Owner 已签候选 B**（见 `TEXT_ANCHOR_FIELDS`）："
        "锚点字段属「文字改写类」⇒ 判 `text`，并在 `modality_basis` 写明是**签过的口径、非源声明**。"
        " 源里真有媒体字段时（路径①②）**一律以源为准**，口径只在源推不出时生效。"
        " 明细与逐表取证见《交付-目标8-模态结案-20261012.md》。",
    "modality.candidate_ads_type":
        "★ **候选口径 A（未签、未执行）**：`广告文案明细.广告类型` 含 "
        "`图片需求开发广告` 83 ／ `视频需求开发广告` 31 ／ `自适应搜索广告` 84 ／ `产品广告` 55 "
        "—— 是**真的模态信号**（这一格此前从没查过）。"
        " 但它只覆盖**锚在该表的 16 条规则**，且要先答一个问题："
        "**「这条文案规则算不算视频规则」**（规则正文是 Primary Text / Headline，是**文案**；"
        "而它所属的**广告**是视频）—— 那是口径，不是机械补丁。",
    "modality.candidate_text_default":
        "★ **候选口径 B（未签、未执行）**：四张主要来源表（专家修订汇总表 401 ＋ 风险文案改写建议库 52 ＋ "
        "品线内容边界规则库 21 ＋ W1 表 19）的锚点字段分别是「修订位置（原文引用）」「风险原句示例」"
        "「边界内容」「建议表达（合规话术）」—— **全都是在改「文字怎么写」** ⇒ "
        "可论证绝大多数规则的模态是 `text`。"
        " ⚠️ 但这是**从来源性质推**，不是源字段声明；且 PRD §6.5 要的是规则自己的适用内容类型。"
        " **要人签**；签之前一律 `undetermined`。",
    "content_type":
        "PRD §5.2 的「内容类型」= 文字/图片/视频，与 modality 同义 ⇒ 只出一份，不重复造。",
    "applicable_scope.product_line":
        "★★ 2026-10-12 实测（任务拆解 10/12–10/16 必须做 #2）：509 条规则里 **382 条推不出适用产品线**。"
        "成因是**源表没有那一列**：这 382 条的锚点几乎全在 `专家修订汇总表`，"
        "而该表**全部字段**只有「修订位置（原文引用）/ 修订内容 / 修订原因 / 修订类型 / 文章标题」"
        "—— **没有任何产品线 / 适用产品 / 适用型号列**。"
        " ⚠️ **不许从「文章标题」猜品线**：实测 134 种标题**全是科普选题**"
        "（产后漏尿 / 孕期产检清单 / 泌乳 / 生理性涨奶 / 衔乳 / 束腹带 / 哺乳姿势…），"
        "它们是**内容主题**不是**产品线**。"
        " ⇒ 原依赖：**源侧为 `专家修订汇总表` 补「适用产品线 / 渠道」列**。"
        " ★★ **2026-10-12 Owner 裁定改口径**：飞书源**只读、不补列**；这 382 条的来源是**全渠道汇总表**，"
        "⇒ 标「全渠道/通用」（见 `CHANNEL_WIDE_SOURCES`），**不再留 None 等源侧补列**。"
        " 取证与逐表归因见《交付-目标7-适用范围结案-20261012.md》。",
    "applicable_scope.channel":
        "同 product_line：来源为全渠道汇总表且源无该列 ⇒ 标「全渠道/通用」"
        "（Owner 2026-10-12 批准；见 `CHANNEL_WIDE_SOURCES`）。"
        "（现状全库**从源字段真取到**渠道的仅 68 条 —— 那是 ① 路径的结果，与本兜底不是一回事。）",
}


def revision_type_of(l0_fields: dict | None) -> tuple[str | None, list[str], list[str]]:
    """源「修订类型」→ (档位, 逐 token 出处, 未映射的 token)。

    ★ 2026-10-12：**先整值查，再拆 `/`**。
      映射表里有复合键（`存疑/待讨论`）；直接按 `/` 拆会把它拆成两个查不到的 token。
      两者结论恰好都是 unknown ⇒ **分布上看不出来**（哑失败），只有读 token 才看得见。
    """
    raw = _first_scalar((l0_fields or {}).get("修订类型"))
    if not raw:
        return None, [], []
    s = str(raw).strip()
    toks = [s] if s in REVISION_TYPE_TO_RISK else [t.strip() for t in s.split("/") if t.strip()]
    best, why, unmapped = None, [], []
    for t in toks:
        m = REVISION_TYPE_TO_RISK.get(t)
        if m is None:
            unmapped.append(t)
            continue
        lvl, basis, hard = m
        why.append("修订类型「%s」⇒ %s（%s%s）" % (t, lvl or "unknown", basis,
                                                "" if hard else "，软判"))
        if lvl and (best is None or RISK_ORDER[lvl] > RISK_ORDER[best]):
            best = lvl
    return best, why, unmapped


def risk_level_of(row: dict, l0_fields: dict | None = None) -> tuple[str | None, str]:
    """维度链取档，返回 (risk_level, 出处)。**取不到就 None，不编。**

        ① 源字段 `风险等级`（换词表，最细的证据）
        ② 源字段 `灯色状态`（复用既有色标口径）
        ③ 源字段 `修订类型`（拆 `/` 取最高档）
        ④ `p_level == "P0"` ⇒ **地板**：不得低于 Critical（PRD §7.3 一票否决）
        ⑤ 都取不到 ⇒ None

    ★ 为什么没有 ④ 之外的任何 `p_level` 兜底：见 `P0_FLOOR` 上方那段（拿错轴）。
    ★ 地板**只提不降**，且**必须留痕**：源/维度与层级冲突时，出处里明写「需人核」——
      静默把 `合规·绿` 抬成 `Critical` 比不抬更坏。
    """
    level, why = None, None

    raw = _first_scalar((l0_fields or {}).get("风险等级"))
    if raw:
        key = str(raw).split("·")[0].strip()
        if key in RISK_LEVEL_MAP:
            level, why = RISK_LEVEL_MAP[key], "源字段 风险等级=%s" % raw
        else:
            why = "源字段 风险等级=%s 不在映射表内（%s）" % (raw, "/".join(RISK_LEVEL_MAP))

    if level is None and why is None:
        lamp_raw = _first_scalar((l0_fields or {}).get("灯色状态"))
        if lamp_raw:
            for c in ("红", "黄", "绿"):
                if c in str(lamp_raw):
                    level = LAMP_COLOR_TO_RISK[c]
                    why = "源字段 灯色状态=%s色（复用既有色标口径）" % c
                    break

    if level is None and why is None:
        lvl, toks_why, unmapped = revision_type_of(l0_fields)
        if toks_why:
            level = lvl
            why = "源字段 修订类型 ｜ " + " ＋ ".join(toks_why)
        elif unmapped:
            return RISK_LEVEL_UNKNOWN, "源字段 修订类型=%s 全部不在映射表内 ⇒ **不编**（留 %s）" % ("/".join(unmapped), RISK_LEVEL_UNKNOWN)

    # ④ P0 地板（PRD §7.3）。**只提不降**，且冲突必须留痕。
    if str(row.get("p_level") or "").strip() == P0_FLOOR["p_level"]:
        if level is None:
            return P0_FLOOR["risk_level"], P0_FLOOR["basis"] + " ⇒ Critical（无其他维度可依）"
        if level != P0_FLOOR["risk_level"]:
            return (P0_FLOOR["risk_level"],
                    "%s ｜ %s ⇒ 由 %s **提到** Critical（**源/维度与层级冲突，需人核**）"
                    % (why, P0_FLOOR["basis"], level))
        return level, why

    return level or RISK_LEVEL_UNKNOWN, why or "源无 风险等级 / 灯色状态 / 修订类型 ⇒ **不编**（留 %s）" % RISK_LEVEL_UNKNOWN


# ══════════════════════════════════════════════════════════════════
# 2. 适用范围：适用产品线 / 渠道 / 内容类型
# ══════════════════════════════════════════════════════════════════

#: 源字段 → 归一到本模块的三个维度。**只做归一，不做语义映射**。
#: 例：源 `平台=["Google"]` 是投放平台、源 `渠道=["Meta"]` 是渠道 ⇒ 同归 `channel`。
SCOPE_SOURCES = {
    "product_line": ("品线", "适用产品", "适用型号", "卖点ID"),
    "channel": ("渠道", "平台", "投放地区", "渠道/市场"),
    "content_type": (),          # 见 NOT_DERIVABLE：与 modality 同义，不重复造
}

#: ★★ 2026-10-12：哪些源字段要**取前缀**而不是整值（字段名 → 分隔符）。
#:
#: `W1卖点表达边界（品线反馈0910）` 表的 `卖点ID = "W1-03"` —— `W1` 是**产品代号**、
#: `03` 是卖点序号。写整值会把 `"W1-03"` 塞进品线列，下游按品线筛**筛不到**。
#:
#: 凭什么是 `W1` 而不是整值（**三条依据，不是猜**）：
#:   ① 该表名逐字就是 `W1卖点表达边界`，`来源` 字段逐字写「品线反馈截图 2026-09-10（W1卖点表达边界）」；
#:   ② **既有 89 条有范围规则的 `product_line` 取值本来就是这类代号**（实测：
#:      `W1 34 / M9 25 / 全型号 24 / M6 23 / M5 21 / Air1 21 / 吸奶器 16 / S12 Pro 5 …`）
#:      ⇒ 取 `W1` 是**向既有口径对齐**，不是新造；
#:   ③ 前缀取不到（值里没有 `-`）⇒ **落空，不编**。
SCOPE_VALUE_PREFIX = {"卖点ID": "-"}

SCOPE_KEYS = ("product_line", "channel", "content_type")

#: ★★ 已签口径（**Owner 2026-10-12**）：来源是**全渠道汇总表**、且源表无该列 ⇒
#: 标「全渠道/通用」，**不再留 None 等源侧补列**。
#:
#: 为什么不是「编一个值」：这 382 条规则锚在 `专家修订汇总表` —— 那是一张**全渠道汇总**的
#: 专家修订记录（字段只有 修订位置（原文引用）/修订内容/修订原因/修订类型/文章标题）。
#: 它**结构上不可能**声明渠道/品线；标「未声明」与标「通用」在下游行为上等价
#: （都等于「不按渠道过滤」），但「通用」是**可读、可核、可替换**的取值，
#: 而 None 会被读成「漏填」。⇒ Owner 批准后按本值落。
#:
#: ⚠️ 边界（**不许外推**）：本值只对**结构上无该列的全渠道汇总来源**成立，
#: **不是**「推不出就填通用」。推得出的一律以源为准（上面 `SCOPE_SOURCES` 那一套）。
#: 尤其**不许**从 `文章标题` 猜品线 —— 实测 134 种标题全是科普选题（产后漏尿/泌乳/生理性涨奶…），
#: 那是**内容主题**不是**产品线**。
CHANNEL_WIDE_SOURCES = frozenset({"专家修订汇总表"})
SCOPE_WIDE_VALUE = "全渠道/通用"
SCOPE_WIDE_BASIS = ("口径：来源「%s」为全渠道汇总表、源表无该列 ⇒ 标「%s」"
                    "（Owner 2026-10-12 批准；**非源字段声明**）")


def _anchor_table_of(anchor) -> str:
    """锚点形如 `#专家修订汇总表/recvXXX/修订位置（原文引用）` ⇒ 取表名；取不到回空串。"""
    s = str(anchor or "").lstrip("#")
    return s.split("/")[0].strip() if s else ""


def applicable_scope_of(l0_fields: dict | None) -> tuple[dict, dict]:
    """返回 (applicable_scope, 出处)。取不到的维度落 None ＋ 记 gap。"""
    f = l0_fields or {}
    out: dict[str, list | None] = {}
    prov: dict[str, str] = {}
    gaps: list[str] = []

    for dim, srcs in SCOPE_SOURCES.items():
        if not srcs:
            out[dim] = None
            gaps.append(dim)
            continue
        vals: list[str] = []
        used: list[str] = []
        for s in srcs:
            got = _as_str_list((f.get(s) or {}).get("value"))
            sep = SCOPE_VALUE_PREFIX.get(s)
            if sep:
                # 取前缀：`W1-03` → `W1`；取不到（无分隔符 / 空）⇒ 丢掉这一格，**不编**
                got = [x.split(sep)[0].strip() for x in got]
                got = [x for x in got if x]
            if got:
                used.append(s + ("（取 `%s` 前段）" % sep if sep else ""))
                for v in got:
                    if v not in vals:
                        vals.append(v)
        if vals:
            out[dim] = vals
            prov[dim] = "源字段 %s" % " + ".join(used)
        else:
            out[dim] = None
            gaps.append(dim)

    out["_derivation"] = prov or None
    meta = {"from": prov or None, "gaps": gaps or None}
    return out, meta


# ══════════════════════════════════════════════════════════════════
# 3. 模态：取不到，落 undetermined（如实登记，不编）
# ══════════════════════════════════════════════════════════════════

#: 模态枚举（PRD §5.2 的三种内容类型）
MODALITY_ENUM = ("text", "image", "video")
MODALITY_UNDETERMINED = "undetermined"

#: 源字段名里出现这些词 ⇒ 可判模态。当前 5 张规则表**一个都没有**，留着等源侧补。
#: ⚠️ 只收**明确承载媒体**的字段名。**不许**收 `文案`/`listing` 这类泛词 ——
#: 实测（2026-10-10 探针）：收了它们会把元数据字段 `文案位置` / `文案语种` 误判成 text，
#: 一次造出 68 条假 text。**误判比 undetermined 坏**：undetermined 有人去补，假值没人回头看。
MODALITY_FIELD_HINTS = {
    "图片素材": "image", "素材图": "image", "主图": "image", "image": "image",
    "视频素材": "video", "video": "video",
}

#: ★★ 已签口径（**Owner 2026-10-12 批准候选 B**）：锚点字段属「文字改写类」⇒ 判 `text`。
#:
#: 为什么可以判：这五个字段全是在改**文字怎么写**（不是承载媒体的格子）——
#: 「修订位置（原文引用）」401 ／「风险原句示例」52 ／「边界内容」21 ／
#: 「建议表达（合规话术）」19 ／「命中片段」16。
#: 为什么必须**签**才能判：这是**从来源性质推**，不是源字段声明；PRD §6.5 要的是规则自己的适用内容类型。
#: ⇒ 签之前一律 `undetermined`；签之后按本条判，并在 `modality_basis` 里写明是**签过的口径**、不是源声明。
#:
#: ⚠️ 与 `MODALITY_FIELD_HINTS` 的分工，别混：
#:   · `MODALITY_FIELD_HINTS` 认**媒体字段名**（图片素材/视频素材）—— 认的是**源里有那一格**；
#:   · 本表认**锚点内容字段名** —— 认的是**规则在改什么**。
#:   **不许**把 `文案位置`/`文案语种` 这类元数据字段名收进来（那是 ③d 守着的坑，会造出假 text）。
TEXT_ANCHOR_FIELDS = frozenset({
    "修订位置（原文引用）", "风险原句示例", "边界内容", "建议表达（合规话术）", "命中片段",
})
TEXT_DEFAULT_BASIS = "锚点字段「%s」属文字改写类 ⇒ 按 Owner 2026-10-12 已签口径（候选B）判 text，非源字段声明"


def modality_of(l0_fields: dict | None, anchor_field: str | None = None) -> tuple[str, str]:
    """返回 (modality, 出处)。**当前恒为 undetermined**，出处写明为什么。"""
    f = l0_fields or {}
    # 路径 ①：源里真有媒体字段 ⇒ 用它（当前 0 条走这条，但源侧补字段后自动生效）
    for name in f:
        low = str(name).lower()
        for hint, mod in MODALITY_FIELD_HINTS.items():
            if hint.lower() in low and _has_value(f[name]):
                return mod, "源字段「%s」承载该模态" % name
    # 路径 ②：锚点字段名带模态词
    if anchor_field:
        low = str(anchor_field).lower()
        for hint, mod in MODALITY_FIELD_HINTS.items():
            if hint.lower() in low:
                return mod, "锚点字段「%s」承载该模态" % anchor_field
    # 路径 ③：★ 已签口径（Owner 2026-10-12，候选 B）——锚点字段属「文字改写类」⇒ text。
    #   放在最后：**源里真有媒体字段（①②）时一律以源为准**，口径只在源推不出时才生效。
    if anchor_field and str(anchor_field).strip() in TEXT_ANCHOR_FIELDS:
        return "text", TEXT_DEFAULT_BASIS % anchor_field
    return MODALITY_UNDETERMINED, "源无媒体字段、锚点字段「%s」亦非媒体字段" % (anchor_field or "—")


# ══════════════════════════════════════════════════════════════════
# 4. 三个字段一次算完
# ══════════════════════════════════════════════════════════════════

DIMENSION_FIELDS = ("risk_level", "risk_level_basis", "applicable_scope",
                    "modality", "modality_basis", "dimensions_derivation")


def _is_placeholder_scope(cur) -> bool:
    """`applicable_scope` 是不是**一格都没填的占位字典**（全 None ＋ 可有 `_derivation`）。

    ★ 2026-10-12 加。病灶：占位字典结构上非空 ⇒ 回填器把它当「已有值」保留 ⇒ 派生值写不进去。
      与「哨兵 `unknown` 不算空」同一类病（那一类当年让 509 条全报冲突）。
      **任何一个维度有真实值 ⇒ 返回 False**（真实值不许被覆盖）。
    """
    if not isinstance(cur, dict):
        return False
    for k, v in cur.items():
        if k == "_derivation":
            continue
        if v not in (None, "", [], {}):
            return False
    return True


def derive(row: dict, l0_fields: dict | None = None, anchor_field: str | None = None) -> dict:
    """对**一行**规则算出维度字段。纯函数，不改 row。"""
    rl, rl_why = risk_level_of(row, l0_fields)
    scope, scope_meta = applicable_scope_of(l0_fields)
    # ★★ 2026-10-12 已签口径：全渠道汇总来源 + 源无该列 ⇒ 标「全渠道/通用」（见 CHANNEL_WIDE_SOURCES）。
    #    只补**仍为 None** 的维度：推得出的一律以源为准，一个字都不动。
    tab = _anchor_table_of(row.get("anchor"))
    if tab in CHANNEL_WIDE_SOURCES:
        prov = dict(scope.get("_derivation") or {})
        for dim in ("product_line", "channel"):
            if scope.get(dim) is None:
                scope[dim] = [SCOPE_WIDE_VALUE]
                prov[dim] = SCOPE_WIDE_BASIS % (tab, SCOPE_WIDE_VALUE)
        if prov:
            scope["_derivation"] = prov
        scope_meta = {"from": prov or None,
                      "gaps": [g for g in (scope_meta.get("gaps") or []) if scope.get(g) is None] or None}
    mod, mod_why = modality_of(l0_fields, anchor_field)
    return {
        "risk_level": rl,
        "risk_level_basis": rl_why,
        "applicable_scope": scope,
        "modality": mod,
        "modality_basis": mod_why,
        "dimensions_derivation": {
            "risk_level": rl_why,
            "applicable_scope": scope_meta,
            "modality": mod_why,
            "not_derivable": sorted(NOT_DERIVABLE),
        },
    }


def apply_dimensions(rows: list, l0_index: dict | None = None, mode: str = "force",
                     force_fields: frozenset | set | None = None) -> dict:
    """就地为 rows 填维度字段。

    mode="force"      —— 一律重算（日更蒸馏器用）
    mode="fill_empty" —— 只填空的；已有**真实**值与派生值不同时**不覆盖**并记进 conflicts
                         （回填脚本用：它不是权威写方）

    force_fields —— **点名「这一列以派生为准」**。填了的列即使已有真实值也按派生值写，
                    并把被改写的那条**仍然记进 conflicts**（改名 `overrode` 语义：改是改了，
                    但改了什么、从什么改成什么，一条都不许丢）。

    ⚠️ 什么时候才允许用 force_fields：**只在「源值派生的结果本身就是新口径」这一类上**。
    本库实际用例 = `risk_level` 的换词表（源 `高危` → PRD `Critical`）：此时保留旧的中文值，
    会让同一列里中英混排 —— 那不是「保守」，是**更坏的中间态**（下游没法按列判断口径）。
    **不许**拿它来压掉「派生不出来、但人已经判过」的值：那种情况要人来裁，不是脚本。

    ⚠️ **什么叫「空」**：除了 None / "" / {} / []，**「未知」哨兵也算空**。
    本库的哨兵取值：`risk_level` 的 `unknown`、`modality` 的 `undetermined`。
    它们**不是已有答案，是「还没判」的占位**。把哨兵当成已有值，回填就永远不会生效 ——
    实测（2026-10-10 首次 dry-run）：509 条全被报成「冲突、保留 unknown」，一个字段都没填上。
    但**真实值不许被静默覆盖**：不一致时必须看得见（conflicts / overrode）。
    """
    ff = set(force_fields or ())
    st = {"rows": 0, "filled": 0, "kept": 0, "overrode": 0, "conflicts": [],
          "risk_level": collections.Counter(), "modality": collections.Counter(),
          "scope_gaps": collections.Counter()}
    for r in rows:
        st["rows"] += 1
        l0f, af = (None, None)
        if l0_index:
            l0f, af = l0_index(r)
        d = derive(r, l0f, af)

        for key in ("risk_level", "applicable_scope", "modality"):
            cur = r.get(key)
            new = d[key]
            empty = cur in (None, "", {}, []) or (
                isinstance(cur, str) and cur.strip().lower() in SENTINEL_VALUES)
            # ★★ 2026-10-12：`applicable_scope` 的**占位字典**也算空。
            #   病灶（预演时实测）：现值形如 `{"product_line": None, "channel": None,
            #   "content_type": None, "_derivation": None}` —— 语义上「一格都没填」，
            #   但结构上是**非空字典** ⇒ 过不了上面那条判据 ⇒ 派生出的值被当成「冲突」保留，
            #   **回填永远不生效**。这与「哨兵 `unknown` 不算空」是**同一类病**
            #   （见上方 2026-10-10 那条：509 条全报冲突、一个字段都没填上）。
            #   ⚠️ 只对**全 None 的占位**算空；**任何一个维度有真实值就不算空**（真实值不许被覆盖）。
            if not empty and key == "applicable_scope" and _is_placeholder_scope(cur):
                empty = True
            if mode == "fill_empty" and not empty and cur != new and key not in ff:
                st["conflicts"].append({"rule_id": r.get("rule_id"), "field": key,
                                        "kept": cur, "would_be": new})
                st["kept"] += 1
                continue
            if not empty and cur != new and key in ff:
                # 点名以派生为准 ⇒ 写，但**留痕**（改了什么、从什么改成什么）
                st["conflicts"].append({"rule_id": r.get("rule_id"), "field": key,
                                        "kept": new, "was": cur, "overrode": True})
                st["overrode"] += 1
            if empty and not (new in (None, "", {}, [])):
                st["filled"] += 1
            r[key] = new
        for k in ("risk_level_basis", "modality_basis", "dimensions_derivation"):
            r[k] = d[k]
        st["risk_level"][str(d["risk_level"])] += 1
        st["modality"][str(d["modality"])] += 1
        sc = d["applicable_scope"] or {}
        if sc.get("_derivation") is None:
            st["scope_gaps"]["<整条无任何范围>"] += 1
        for g in SCOPE_KEYS:
            if sc.get(g) is None:
                st["scope_gaps"][g] += 1
    return st


# ══════════════════════════════════════════════════════════════════
# 5. 小工具
# ══════════════════════════════════════════════════════════════════

def _has_value(fv) -> bool:
    return bool((fv or {}).get("value")) if isinstance(fv, dict) else bool(fv)


def _first_scalar(fv) -> str | None:
    """L0 字段值可能是 list / str / None，统一取第一个非空标量。"""
    if fv is None:
        return None
    v = fv.get("value") if isinstance(fv, dict) else fv
    if v is None:
        return None
    if isinstance(v, (list, tuple)):
        for x in v:
            if x not in (None, ""):
                return str(x)
        return None
    s = str(v).strip()
    return s or None


def _as_str_list(v) -> list[str]:
    if v is None:
        return []
    if isinstance(v, (list, tuple)):
        return [str(x).strip() for x in v if str(x or "").strip()]
    s = str(v).strip()
    return [s] if s else []


def build_l0_index(root: str = L0_RECORDS):
    """建 (源表, record_id) → 该记录的 fields。只读。"""
    idx = {}
    for f in glob.glob(os.path.join(root, "*", "*.json")):
        try:
            o = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        idx[(o.get("source_table"), o.get("record_id"))] = o.get("fields") or {}
    return idx


def anchor_parts(anchor) -> tuple[str | None, str | None, str | None]:
    """`#表/记录/字段` → (表, 记录, 字段)。"""
    p = str(anchor or "").lstrip("#").split("/")
    return (p[0] if len(p) > 0 else None,
            p[1] if len(p) > 1 else None,
            p[2] if len(p) > 2 else None)


def l0_lookup(idx: dict):
    def _f(row):
        t, rec, fld = anchor_parts(row.get("anchor"))
        return idx.get((t, rec)), fld
    return _f


# ══════════════════════════════════════════════════════════════════
# 6. 判据自证（不碰真库）
# ══════════════════════════════════════════════════════════════════

def _selftest() -> int:
    ok = fail = 0
    fails: list[str] = []

    def ck(name, cond, detail=""):
        nonlocal ok, fail
        if cond:
            ok += 1
        else:
            fail += 1
            fails.append("%s %s" % (name, detail))

    F = lambda v: {"value": v}

    # ①a–d 源风险等级 → 四级（含色标后缀）
    for raw, want in (("高危", "Critical"), ("高危·红", "Critical"), ("审慎·黄", "High"),
                      ("待复核", "Medium"), ("合规·绿", "Low")):
        got, why = risk_level_of({"p_level": "P3"}, {"风险等级": F([raw])})
        ck("①[%s]" % raw, got == want, "得到 %r（%s）" % (got, why))
    # ①e ★ 反向对照：**非 P0 时源优先**，不被地板动
    got, why = risk_level_of({"p_level": "P1"}, {"风险等级": F(["合规·绿"])})
    ck("①e 非P0源优先", got == "Low", "得到 %r（%s）" % (got, why))
    # ①e2 P0 地板：源=合规·绿 而 p_level=P0 ⇒ **提到 Critical**，且必须留痕「需人核」
    got, why = risk_level_of({"p_level": "P0"}, {"风险等级": F(["合规·绿"])})
    ck("①e2 P0地板只提不降且留痕",
       got == "Critical" and "提到" in why and "需人核" in why, "得到 %r（%s）" % (got, why))
    # ①f ★★ 本次核心修复：`p_level=P1/P2/P3` **不再兜底**
    #     反向对照 ①f2：只有 P0 才有档 ⇒ 证明不是「把兜底换成另一个兜底」
    for p in ("P1", "P2", "P3"):
        got, why = risk_level_of({"p_level": p}, {})
        ck("①f[%s 不兜底]" % p, got == RISK_LEVEL_UNKNOWN and "不编" in why, "得到 %r（%s）" % (got, why))
    got, why = risk_level_of({"p_level": "P0"}, {})
    ck("①f2 P0地板仍在", got == "Critical" and "无其他维度可依" in why, "得到 %r（%s）" % (got, why))
    # ①g 维度 2：灯色状态（复用既有色标口径）
    for c, want in (("红色-禁用", "Critical"), ("黄色-需限定", "High"), ("绿色-可用", "Low")):
        got, why = risk_level_of({}, {"灯色状态": F([c])})
        ck("①g[%s]" % c, got == want and "色标" in why, "得到 %r（%s）" % (got, why))
    # ①h 维度 3：修订类型单值
    got, why = risk_level_of({}, {"修订类型": F(["安全性提示"])})
    ck("①h 未映射不编", got == RISK_LEVEL_UNKNOWN and "不编" in why, "得到 %r（%s）" % (got, why))
    got, why = risk_level_of({}, {"修订类型": F(["科学性纠错"])})
    ck("①h2 科学性纠错⇒Medium", got == "Medium" and "通识与常识" in why, "得到 %r（%s）" % (got, why))
    # ①i 复合值：`/` 拆、**取最高档**
    #     ★ 反向对照 ①i2 见下：两个 token 分属不同档，取最高与取最低结果不同 ⇒ 判据有区分力
    got, why = risk_level_of({}, {"修订类型": F(["表述精确化/表述对齐指南"])})
    ck("①i 复合取最高", got == "Medium", "得到 %r（%s）" % (got, why))
    got2, _ = risk_level_of({}, {"修订类型": F(["表述精确化"])})
    ck("①i2 反向对照：取最高≠取最低", got2 == "Low" and got != got2,
       "单值 %r / 复合 %r" % (got2, got))
    # ①i3 ★ 整值优先：`存疑/待讨论` 是**一个整键**，不许被拆成两个查不到的 token。
    #      ⚠️ 本条第一版是**恒绿**的（变异自证 M3 抓出来的）：两路输出的字符串
    #      `"/".join(unmapped)` 恰好还原成 `存疑/待讨论` ⇒ 断言分辨不出走的是哪条路。
    #      ⇒ 现在钉「**走的哪条路**」：整值命中时 `unmapped` 必须为空、且出处来自映射表那句。
    got, why = risk_level_of({}, {"修订类型": F(["存疑/待讨论"])})
    _lvl, _why_toks, _unmapped = revision_type_of({"修订类型": F(["存疑/待讨论"])})
    ck("①i3 复合键不拆散",
       got == RISK_LEVEL_UNKNOWN and not _unmapped and "留 unknown" in why and "不在映射表内" not in why,
       "得到 %r ｜ unmapped=%r ｜ %s" % (got, _unmapped, why))
    # ①i4 ★ 反向对照：`去绝对化` **不许**判 Critical（源里它指去掉不成立的适用边界，
    #      不是 §7.3-3 的广告绝对化用语；判错会把红线档撑大）
    got, why = risk_level_of({}, {"修订类型": F(["去绝对化"])})
    ck("①i4 去绝对化不是红线", got == "High", "得到 %r（%s）" % (got, why))
    # ①j 未知取值**不猜**，落 None
    got, why = risk_level_of({"p_level": "P9"}, {"风险等级": F(["未曾见过的等级"])})
    ck("①j 不猜", got == RISK_LEVEL_UNKNOWN and "不在映射表内" in why, "得到 %r（%s）" % (got, why))
    # ①k 全空 ⇒ None（不许回落成一个默认等级）
    got, why = risk_level_of({}, {})
    ck("①k 全空不默认", got == RISK_LEVEL_UNKNOWN, "得到 %r" % got)
    # ①k2 ★ 哨兵必须是「还没判」而不是「一个等级」—— 否则 `fill_empty` 会把它当已有值，
    #     日更永远不会重填它（与 modality 的 undetermined 同一个坑，实测踩过）
    ck("①k2 哨兵被 SENTINEL_VALUES 认作空", RISK_LEVEL_UNKNOWN in SENTINEL_VALUES,
       "哨兵 %r 不在 SENTINEL_VALUES 里 ⇒ fill_empty 会当它是已有值" % RISK_LEVEL_UNKNOWN)

    # ②a 范围：三个源字段归一。
    # ⚠️ 顺序口径：**按 SCOPE_SOURCES 声明的源优先级**排，不按 L0 记录里的字段先后。
    #    这样「渠道」这个更专指的源永远排在泛指的「平台」前面，重跑结果稳定。
    #    （本条判据曾写成 ['Google','Meta']，被自证抓出来是**断言写错**，代码是对的。）
    sc, meta = applicable_scope_of({"品线": F(["吸奶器"]), "平台": F(["Google"]), "渠道": F(["Meta"])})
    ck("②a 归一（源优先级：渠道 > 平台）",
       sc["product_line"] == ["吸奶器"] and sc["channel"] == ["Meta", "Google"],
       "得到 %r" % sc)
    ck("②a2 出处", "品线" in (meta["from"] or {}).get("product_line", ""), "得到 %r" % meta["from"])
    # ②b 去重且保序
    sc, _ = applicable_scope_of({"平台": F(["Google", "Google", "Meta"])})
    ck("②b 去重", sc["channel"] == ["Google", "Meta"], "得到 %r" % sc["channel"])
    # ②c 取不到 ⇒ None ＋ 记 gap，**不编**
    sc, meta = applicable_scope_of({})
    ck("②c 取不到就空", all(sc[k] is None for k in SCOPE_KEYS) and set(meta["gaps"]) >= set(SCOPE_KEYS),
       "得到 %r" % sc)
    # ②d 字符串与列表两种形状都吃
    sc, _ = applicable_scope_of({"品线": F("吸奶器"), "平台": F(["Google"])})
    ck("②d 两种形状", sc["product_line"] == ["吸奶器"] and sc["channel"] == ["Google"],
       "得到 %r" % sc)
    # ②e 空列表不算有值
    sc, _ = applicable_scope_of({"品线": F([])})
    ck("②e 空列表=无", sc["product_line"] is None, "得到 %r" % sc["product_line"])
    # ②f–i ★ 2026-10-12：`卖点ID` 取**前缀**（`W1-03` → `W1`），不是整值。
    #      依据见 `SCOPE_VALUE_PREFIX` 抬头（表名 + 既有 89 条的取值形态）。
    sc, meta = applicable_scope_of({"卖点ID": F(["W1-03"])})
    ck("②f 卖点ID 取前缀", sc["product_line"] == ["W1"],
       "得到 %r（若为 ['W1-03'] ⇒ 整值被写进了品线列，下游按品线筛不到）" % sc["product_line"])
    ck("②f2 出处写明取了前缀", "前段" in (meta["from"] or {}).get("product_line", ""),
       "得到 %r" % meta["from"])
    # ②g ★ 反向对照：把前缀表清空 ⇒ ②f 必须精确变红（证明 ②f 不是恒真）
    ck("②g 前缀表非空", bool(SCOPE_VALUE_PREFIX.get("卖点ID")),
       "前缀表被清空 ⇒ ②f 会得到整值 'W1-03'")
    # ②h 值本身就是代号（无序号）⇒ 照收（`W1` 就是产品代号）。
    #     ⚠️ 本条第一版断言写成「无分隔符 ⇒ 落 None」，**是断言写错、代码是对的**
    #     （被自证当场抓出来；同库先例：`②a` 那条也曾断言写错）。
    sc, _ = applicable_scope_of({"卖点ID": F(["W1"])})
    ck("②h 无序号照收", sc["product_line"] == ["W1"], "得到 %r" % sc["product_line"])
    # ②i 前缀取成空串（`-03`）⇒ **落空，不编**
    sc, _ = applicable_scope_of({"卖点ID": F(["-03"])})
    ck("②i 空前缀落空", sc["product_line"] is None, "得到 %r" % sc["product_line"])
    # ②j 与既有源并存时**都收**（不因为多了前缀源就丢掉 `适用产品`）
    sc, _ = applicable_scope_of({"适用产品": F(["M5"]), "卖点ID": F(["W1-03"])})
    ck("②j 与既有源并存", sc["product_line"] == ["M5", "W1"], "得到 %r" % sc["product_line"])

    # ③a ★ 已签口径（Owner 2026-10-12 候选 B）：锚点字段属文字改写类 ⇒ text
    #    （本条在 2026-10-12 之前断言的是 undetermined —— 那是「**没签之前**不许猜」；
    #      Owner 签字后前提已变，改为钉「签过的口径生效」＋「出处写明非源声明」。）
    mod, why = modality_of({"修订位置（原文引用）": F(["x"])}, "修订位置（原文引用）")
    ck("③a 已签口径生效", mod == "text", "得到 %r" % mod)
    ck("③a2 出处须写明是签过的口径、非源声明",
       ("已签口径" in why) and ("非源字段声明" in why), "得到 %r" % why)
    # ③a3 ★ 反向对照：**源里真有媒体字段时口径不许盖过源**（路径①② 优先于 ③）
    mod, why = modality_of({"图片素材": F(["file_token"])}, "修订位置（原文引用）")
    ck("③a3 源优先于口径", mod == "image", "得到 %r（%s）" % (mod, why))
    # ③b 源侧补了媒体字段 ⇒ 自动生效
    mod, why = modality_of({"图片素材": F(["file_token"])}, None)
    ck("③b 媒体字段生效", mod == "image", "得到 %r（%s）" % (mod, why))
    # ③c 锚点字段含**明确媒体字段名**也认（锚点字段是 `视频素材_关键帧` 这种形态时）
    mod, why = modality_of({}, "视频素材_关键帧")
    ck("③c 锚点含明确媒体字段名", mod == "video", "得到 %r" % mod)
    # ③c2 但锚点只有泛词「视频」⇒ 仍落 undetermined（与 ③d 同一条纪律：泛词不判模态）
    mod, why = modality_of({}, "视频关键帧")
    ck("③c2 泛词不判", mod == MODALITY_UNDETERMINED, "得到 %r" % mod)
    # ③d ★ 反向对照：元数据字段名里的 `文案` 不许判成 text
    #     （真库实测 `文案位置` / `文案语种` 曾造出 68 条假 text；把泛词加回表里 ⇒ 本条精确变红）
    #     ⚠️ 锚点字段取一个**不在** TEXT_ANCHOR_FIELDS 里的 —— 否则口径会先命中，
    #        本条就测不到「元数据字段名」那一问了（变量没隔离）。
    mod, why = modality_of({"文案位置": F(["文首"]), "文案语种": F(["英语"])}, "修订说明（自由文本）")
    ck("③d 元数据不冒充实模态", mod == MODALITY_UNDETERMINED, "得到 %r（%s）" % (mod, why))
    # ③f ★ 反向对照：锚点字段**不在**已签清单里 ⇒ 仍落 undetermined（口径不许外溢）
    mod, why = modality_of({}, "广告类型")
    ck("③f 口径不外溢", mod == MODALITY_UNDETERMINED, "得到 %r" % mod)
    # ③e 无值字段不算数
    mod, why = modality_of({"图片素材": F(None)}, None)
    ck("③e 空值不算", mod == MODALITY_UNDETERMINED, "得到 %r" % mod)

    # ④a derive 一次出齐六个键
    d = derive({"rule_id": "r-x", "p_level": "P1", "anchor": "#表/rec/字段"}, {})
    ck("④a 键齐", all(k in d for k in DIMENSION_FIELDS), "缺少 %r" % [k for k in DIMENSION_FIELDS if k not in d])
    # ④b 每个值都带得出处
    ck("④b 有出处", bool(d["risk_level_basis"]) and bool(d["modality_basis"])
       and "not_derivable" in d["dimensions_derivation"], "得到 %r" % d["dimensions_derivation"])

    # ④c ★ 已签口径（Owner 2026-10-12）：全渠道汇总来源 + 源无该列 ⇒ 标「全渠道/通用」
    d = derive({"rule_id": "r-y", "p_level": "P1",
                "anchor": "#专家修订汇总表/recX/修订位置（原文引用）"}, {})
    ck("④c 全渠道兜底生效",
       d["applicable_scope"].get("product_line") == [SCOPE_WIDE_VALUE]
       and d["applicable_scope"].get("channel") == [SCOPE_WIDE_VALUE],
       "得到 %r" % d["applicable_scope"])
    # ④d ★ 反向对照：**别的表**推不出时**不许**兜底（口径只对全渠道汇总来源成立，不许外溢）
    d = derive({"rule_id": "r-z", "p_level": "P1", "anchor": "#广告文案明细/recY/命中片段"}, {})
    ck("④d 兜底不外溢", d["applicable_scope"].get("product_line") is None,
       "得到 %r" % d["applicable_scope"])
    # ④e ★ 反向对照：源里**有值**时兜底一个字都不动
    d = derive({"rule_id": "r-w", "p_level": "P1",
                "anchor": "#专家修订汇总表/recZ/修订位置（原文引用）"}, {"品线": F(["吸奶器"])})
    ck("④e 源值优先于兜底", d["applicable_scope"].get("product_line") == ["吸奶器"],
       "得到 %r" % d["applicable_scope"])

    # ⑤a force 模式覆盖
    rows = [{"rule_id": "r1", "p_level": "P0", "risk_level": "unknown"}]
    st = apply_dimensions(rows, None, mode="force")
    ck("⑤a force 覆盖", rows[0]["risk_level"] == "Critical", "得到 %r" % rows[0].get("risk_level"))
    # ⑤b fill_empty 模式不覆盖已填且不同 ⇒ 记 conflicts
    rows = [{"rule_id": "r2", "p_level": "P0", "risk_level": "Low"}]
    st = apply_dimensions(rows, None, mode="fill_empty")
    ck("⑤b 不覆盖", rows[0]["risk_level"] == "Low" and st["conflicts"],
       "得到 %r / conflicts=%r" % (rows[0].get("risk_level"), st["conflicts"]))
    # ⑤c fill_empty 但已填且相同 ⇒ 不算冲突
    rows = [{"rule_id": "r3", "p_level": "P0", "risk_level": "Critical"}]
    st = apply_dimensions(rows, None, mode="fill_empty")
    ck("⑤c 相同不算冲突", not st["conflicts"], "得到 %r" % st["conflicts"])
    # ⑤d ★ 哨兵 `unknown` **算空** ⇒ fill_empty 必须把它填上
    #     （首轮 dry-run 实测：不当空 ⇒ 509 条全报冲突、一个字段都没填上）
    rows = [{"rule_id": "r4", "p_level": "P0", "risk_level": "unknown", "modality": "undetermined"}]
    st = apply_dimensions(rows, None, mode="fill_empty")
    ck("⑤d 哨兵算空", rows[0]["risk_level"] == "Critical" and st["filled"] >= 1
       and not st["conflicts"], "得到 %r / conflicts=%r" % (rows[0]["risk_level"], st["conflicts"]))
    # ⑤e 但**真实值**不许被覆盖
    rows = [{"rule_id": "r5", "p_level": "P0", "risk_level": "Low"}]
    st = apply_dimensions(rows, None, mode="fill_empty")
    ck("⑤e 真实值不覆盖", rows[0]["risk_level"] == "Low" and st["conflicts"],
       "得到 %r" % rows[0]["risk_level"])
    # ⑤f 反向对照：把哨兵从 SENTINEL_VALUES 里拿掉 ⇒ ⑤d 必须精确变红
    ck("⑤f 哨兵表非空", "unknown" in SENTINEL_VALUES and "undetermined" in SENTINEL_VALUES,
       "得到 %r" % sorted(SENTINEL_VALUES))
    # ⑤g force_fields：点名的列即使已有真实值也按派生写，但**必须留痕**
    rows = [{"rule_id": "r6", "p_level": "P0", "risk_level": "高危"}]
    st = apply_dimensions(rows, None, mode="fill_empty", force_fields={"risk_level"})
    ck("⑤g 点名列以派生为准且留痕",
       rows[0]["risk_level"] == "Critical" and st["overrode"] == 1
       and st["conflicts"] and st["conflicts"][0].get("overrode") is True
       and st["conflicts"][0].get("was") == "高危",
       "得到 %r / %r" % (rows[0]["risk_level"], st["conflicts"]))
    # ⑤h 没点名的列照旧不覆盖（不许顺手全放开）
    rows = [{"rule_id": "r7", "p_level": "P0", "risk_level": "高危", "modality": "text"}]
    st = apply_dimensions(rows, None, mode="fill_empty", force_fields={"risk_level"})
    ck("⑤h 未点名列不覆盖", rows[0]["modality"] == "text" and not st["overrode"] == 2
       and any(c["field"] == "modality" and not c.get("overrode") for c in st["conflicts"]),
       "得到 %r / %r" % (rows[0]["modality"], st["conflicts"]))
    # ⑤j ★ 2026-10-12：`applicable_scope` 的**占位字典**算空 ⇒ 派生值必须填得进去。
    #     病灶：占位字典结构上非空 ⇒ 被当「已有值」保留 ⇒ 回填**永远不生效**（与哨兵 `unknown` 同类病）。
    _ph = {"_derivation": None, "channel": None, "content_type": None, "product_line": None}
    rows = [{"rule_id": "r9", "applicable_scope": dict(_ph)}]
    _lk = lambda _r: ({"卖点ID": F(["W1-03"])}, None)          # noqa: E731
    st = apply_dimensions(rows, _lk, mode="fill_empty")
    ck("⑤j 占位字典算空 ⇒ 填得上", rows[0]["applicable_scope"].get("product_line") == ["W1"]
       and not st["conflicts"], "得到 %r / conflicts=%r" % (rows[0]["applicable_scope"], st["conflicts"]))
    # ⑤k ★ 反向对照：**有真实值就不算空** —— 不许因为 ⑤j 就顺手把真实值也覆盖掉
    rows = [{"rule_id": "r10", "applicable_scope": {"product_line": ["M5"], "channel": None,
                                                    "content_type": None}}]
    st = apply_dimensions(rows, _lk, mode="fill_empty")
    ck("⑤k 真实值仍不被覆盖", rows[0]["applicable_scope"].get("product_line") == ["M5"]
       and st["conflicts"], "得到 %r / conflicts=%r" % (rows[0]["applicable_scope"], st["conflicts"]))
    # ⑤l 占位判定函数本身：空字典/非字典都不算「占位」（边界）
    ck("⑤l 占位判定边界", _is_placeholder_scope(dict(_ph)) is True
       and _is_placeholder_scope({}) is True
       and _is_placeholder_scope({"channel": ["Meta"]}) is False
       and _is_placeholder_scope(None) is False,
       "得到 %r" % [_is_placeholder_scope(x) for x in (dict(_ph), {}, {"channel": ["Meta"]}, None)])

    # ⑤i 不给 force_fields ⇒ 行为与旧版逐字一致（回退口径）
    rows = [{"rule_id": "r8", "p_level": "P0", "risk_level": "高危"}]
    st = apply_dimensions(rows, None, mode="fill_empty")
    ck("⑤i 缺省不覆盖", rows[0]["risk_level"] == "高危" and st["overrode"] == 0,
       "得到 %r" % rows[0]["risk_level"])

    print("kb_rule_dimensions --selftest：%d/%d" % (ok, ok + fail))
    for f in fails:
        print("  ✗", f)
    return 0 if fail == 0 else 1


# ══════════════════════════════════════════════════════════════════
# 7. 只读探针（对真库跑，报覆盖缺口）
# ══════════════════════════════════════════════════════════════════

def _probe(rules_path: str = RULES_DEFAULT) -> int:
    idx = build_l0_index()
    print("L0 记录索引：%d 条" % len(idx))

    merged: dict[str, dict] = {}
    for line in open(rules_path, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        o = json.loads(line)
        rid = o.get("rule_id")
        if not rid:
            continue
        m = merged.setdefault(rid, {})
        for k, v in o.items():
            if v not in (None, "", [], {}):
                m[k] = v
    print("L3 规则（按 rule_id 合并）：%d 条\n" % len(merged))

    rows = list(merged.values())
    st = apply_dimensions(rows, l0_lookup(idx), mode="fill_empty")

    print("── 现状（回填前）→ 派生后 ──")
    print("  risk_level 分布（派生后）：")
    for k, v in st["risk_level"].most_common():
        print("     %-12s %4d  (%.1f%%)" % (k, v, 100.0 * v / st["rows"]))
    print("  modality 分布：")
    for k, v in st["modality"].most_common():
        print("     %-12s %4d  (%.1f%%)" % (k, v, 100.0 * v / st["rows"]))
    print("  applicable_scope 缺口：")
    for k, v in st["scope_gaps"].most_common():
        print("     %-14s %4d" % (k, v))

    print("\n── 结论 ──")
    print("  risk_level 有值 %d/%d（其余为 %s，原因见 risk_level_basis）"
          % (st["rows"] - st["risk_level"].get(RISK_LEVEL_UNKNOWN, 0), st["rows"], RISK_LEVEL_UNKNOWN))
    print("  modality  可用   %d/%d（其余为 undetermined，原因见 NOT_DERIVABLE）"
          % (st["rows"] - st["modality"].get(MODALITY_UNDETERMINED, 0), st["rows"]))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="L3 规则维度派生（PRD §6.5 / §5.2）")
    ap.add_argument("--selftest", action="store_true", help="判据自证（不碰真库）")
    ap.add_argument("--probe", action="store_true", help="只读探针：对真库跑一遍")
    ap.add_argument("--rules", default=RULES_DEFAULT)
    a = ap.parse_args()
    if a.selftest:
        return _selftest()
    if a.probe:
        return _probe(a.rules)
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
