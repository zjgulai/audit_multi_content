#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""修复计划 F3 · 补齐 `kb/view/_meta/` 下 7 份加载器真的会读的 YAML。

F3a 纪律（本脚本执行的就是 F3a）：
  初值一律取**与代码兜底值等价的配置**，先做到"接了线、但不放宽也不收紧任何闸门"。
  收紧（require_on_new / layer_counts 基线 / 阈值调整）属于 F3b，单独一轮。

    文件                 顶层键（WIRED_META_KEYS 白名单）      本脚本写入的口径
    ------------------  ------------------------------------  ----------------------------------
    vocabulary.yaml     concepts                              从 l7/registry/l7.json 的受控词表派生
    intake.yaml         gates / triple_verification            gates 取 DEFAULT_GATES；
                                                               triple_verification 取 VERDICT(0.8/0.4)
    health.yaml         circuit_breaker / alerts /             取 ALERT + CIRCUIT_BREAKER 的等价值
                        per_type_half_life_days
    boundaries.yaml     boundaries                            取 DEFAULT_BOUNDARIES 等价值
    index-status.yaml   index / layer_counts / captured_at     index.status=candidate（清 W037）；
                                                               layer_counts 按实际条数（防「条目消失」）
    evidence-groups.yaml groups / ranking / require_on_new    真枚举 + ranking 空 + **require_on_new=false**
    ranking.yaml        weights                               取 DEFAULT_RANKING 等价值

⚠ 为什么 evidence-groups.yaml 必须 require_on_new=false：
   E042 的判据是「缺 evidence_group 且 require_on_new 为真 且 created_at >= 2026-09-22」。
   本库 509 条的 created_at 是 2026-09-23，**晚于切换日** —— 一旦打开开关，
   509 个 W036 告警会**全部升级成 E042 错误**。那属于 F3b 的收紧，不是 F3a。

写通道：`.yaml` 不受 trld 信封影响（只有 `.md` 受影响），可直接用 Python 写。
用法：python3 kb/.work/fix_f3_gen.py [--dry-run]
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
import collections

KB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VIEW = os.path.join(KB, "view")
META = os.path.join(VIEW, "_meta")

# ── 与插件代码逐字段对齐的兜底值（来源：~/.dsh/plugins/dsh-kb/lib/kb.js）──────
ALERT = {
    "freshnessMin": 0.9,
    "conflictMax": 0.05,
    "coverageMin": 0.8,
    "islandMax": 0.2,
    "hallucinationMax": 0.1,
    "evidenceMinCoverage": 0.3,
    "utilizationMaxZero": 0.3,
}
CIRCUIT_BREAKER = 60
VERDICT = {"keep": 0.8, "review": 0.4}
DEFAULT_GATES = {
    "halfLifeFloorDays": 2,
    "halfLifeCacheCeilingDays": 7,
    "fingerprintEnforcement": "warn",
}
DEFAULT_BOUNDARIES = {
    "canonical_write": False,
    "ledger_write": True,
    "baseline_write": True,
    "meta_write": False,
    "provider_call": False,
    "collection_create": False,
}
DEFAULT_RANKING = {
    "expired": 0.3,
    "evidence_L1": 0.6,
    "tier": {"L4": 1.15, "L2": 1.1, "L3": 1.0, "L1": 1.0, "L0": 0.9},
    "superseded": 0.5,
    "archived": 0.3,
    "vocabulary": 5,
    "evidence_group_default": 1.0,
    "kb_class_default": 1.0,
}

HDR = "# 由 kb/.work/fix_f3_gen.py 生成（修复计划 F3a）—— 顶层键必须在加载器 WIRED_META_KEYS 白名单内，\n"


def w(path: str, text: str, dry: bool) -> None:
    if dry:
        print(f"[dry-run] {os.path.relpath(path, KB)}  {len(text)} 字节")
        return
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    print(f"✅ {os.path.relpath(path, KB)}  {len(text)} 字节")


# ── 1. vocabulary.yaml ────────────────────────────────────────────────────────
def gen_vocabulary() -> str:
    """从 l7/registry/l7.json 的受控词表派生 concepts。

    aliases 决定**能不能搜到**（扩词后按别名匹配条目正文）；
    entries 只影响排序加分（ranking.vocabulary），所以别名是重点。

    entries 的来源：视图条目标题里的条款号 `[W-2.1]` ⟷ 权威库 l3 规则行的
    `article_no` → `rule_code`。这是可逐条核对的确定性关联，不是猜的。
    """
    reg = json.load(open(os.path.join(KB, "l7", "registry", "l7.json"), encoding="utf-8"))
    vocab = reg.get("vocabulary") or {}
    categories = vocab.get("categories") or {}

    # article_no → rule_code（权威库）
    art2code: dict[str, str] = {}
    for line in open(os.path.join(KB, "l3", "candidates", "rules.jsonl"), encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        r = json.loads(line)
        a, c = r.get("article_no"), r.get("rule_code")
        if a and c:
            art2code[str(a)] = str(c)

    # 视图条目 → 规则码。
    #
    # 标题方括号里装的是**两种东西**，实测：
    #   · L1-facts（453 条，W-2.* 修订对型）→ `[W-2.1]` 是**条款号**，需经 art2code 换规则码
    #   · L2-concepts（56 条，W-1.* 词条型）→ `[H07]` **本身就是规则码**
    # 所以先按条款号查表，查不到再按「本身是规则码」判定 —— 两条路都不中的才算未关联。
    CODE_RE = re.compile(r"^[A-Z]\d+$")
    code2ids: dict[str, list[str]] = collections.defaultdict(list)
    unmatched = 0
    hit_by_article = 0
    hit_by_code = 0
    for f in sorted(glob.glob(os.path.join(VIEW, "3_措辞表达库", "*", "*.md"))):
        txt = open(f, encoding="utf-8", errors="replace").read()
        m = re.match(r"^---\r?\n([\s\S]*?)\r?\n---", txt)
        if not m:
            continue
        fm = m.group(1)
        idm = re.search(r"^id:\s*(\S+)", fm, re.M)
        tm = re.search(r'^title:\s*"?\[([^\]]+)\]', fm, re.M)
        if not (idm and tm):
            unmatched += 1
            continue
        key = tm.group(1).strip()
        code = art2code.get(key)
        if code:
            hit_by_article += 1
        elif CODE_RE.match(key):
            # 兜底：标题里的就是规则码（且不是 UNCODED 这类占位）
            code = key if key != "UNCODED" else None
            if code:
                hit_by_code += 1
        if code:
            code2ids[code].append(idm.group(1))
        else:
            unmatched += 1
    print(f"   关联路径：条款号换码 {hit_by_article} 条 / 标题即码 {hit_by_code} 条 / 未关联 {unmatched} 条")
    print(f"   ⚠ 权威库事实：509 条规则里只有 {len(set(art2code.values()))} 个规则码、{len(art2code)} 条规则带 rule_code"
          f"（其余 {509 - len(art2code)} 条为空）—— 所以 entries 只能覆盖这 {len(art2code)} 条，"
          f"这是**数据缺口**，不是本脚本的关联失败")

    # 子类 → concept
    #
    # 别名是**能不能搜到**的关键（扩词后按别名去匹配条目正文），所以尽量把
    # 三个权威来源里的措辞都抽成别名：① 子类/类别名；② 规则码；③ 子类 label 的枚举词；
    # ④ 该子类对应的 PRD §7.3 一票否决原文措辞（由 `prd_7_3` 编号精确挂接）。
    vetoes = vocab.get("prd_7_3_vetoes") or []

    # PRD §5.3 的输出示例用的是**业务自然叫法**（【合规-医疗宣称】【合规-绝对化用语】
    # 【消费者安全-使用姿势】【消费者安全-车内场景】），它们不是词表里的子类名，
    # 但正是用户实际会输入的词。加载器的 expandTerms 是**双向包含**匹配
    # （`s.includes(t) || t.includes(s)`），所以「医疗宣称」当不了「医疗功效宣称」的
    # 子串、必须**逐字**挂上去才生效。每条都能在 PRD 里指到出处，不是自造：
    #   §5.3.2 示例 → 医疗宣称 / 使用姿势
    #   §5.3.3 示例 → 绝对化用语 / 车内场景
    #   §7.3 七项   → 危险行为示范(5) / 未成年人出镜(6) / AI 深度合成(7)
    PRD_EXAMPLE_ALIASES = {
        "功效宣称": ["医疗宣称", "医疗功效宣称"],
        "绝对化与安全承诺": ["绝对化用语", "绝对化表述"],
        "婴幼儿安全与场景": ["使用姿势", "车内场景", "危险行为示范", "危险示范"],
        "人物肖像与 AI": ["未成年人出镜", "AI 深度合成", "AI 标识"],
        "背书与资质": ["资质背书", "达人背书"],
    }

    def veto_tokens(nums) -> set:
        out = set()
        for n in nums or []:
            for v in vetoes:
                # 形如「2 医疗功效宣称（治疗、预防疾病等）」
                m = re.match(r"^\s*(\d+)\s+(.*)$", str(v))
                if not m or int(m.group(1)) != int(n):
                    continue
                body = m.group(2)
                out.add(body.split("（")[0].split("(")[0].strip())
                for grp in re.findall(r"[（(]([^）)]*)[)）]", body):
                    for piece in re.split(r"[/、,，;；]", grp):
                        piece = piece.strip()
                        if 2 <= len(piece) <= 24:
                            out.add(piece)
        return out

    def label_tokens(label: str) -> set:
        out = set()
        whole = label.split("（")[0].split("(")[0].strip()
        if 2 <= len(whole) <= 24:
            out.add(whole)
        for grp in re.findall(r"[（(]([^）)]*)[)）]", label):
            for piece in re.split(r"[/、,，;；]", grp):
                piece = piece.strip()
                if 2 <= len(piece) <= 24:
                    out.add(piece)
        # 无括号时直接按分隔符切整个 label（实测多数 label 就是这个形态）
        for piece in re.split(r"[/、,，;；]", label):
            piece = piece.strip()
            if 2 <= len(piece) <= 24:
                out.add(piece)
        return out

    concepts = []
    for cat, cbody in categories.items():
        for sub, sbody in (cbody.get("subs") or {}).items():
            codes = [str(c) for c in (sbody.get("codes") or [])]
            if not codes:
                continue
            label = str(sbody.get("label") or "")
            aliases = set()
            aliases.add(sub)
            aliases.add(cat)
            aliases |= set(codes)
            aliases |= label_tokens(label)
            # ⚠ `prd_7_3` 实测挂在**类别级**，子类没有这个键 —— 缺了它会把
            # 「医疗功效宣称 / 绝对化用语 / 最 / 第一 / 100% / 纯天然」这类
            # PRD §7.3 原文措辞全部漏掉。所以子类优先、类别兜底。
            aliases |= veto_tokens(sbody.get("prd_7_3") or cbody.get("prd_7_3"))
            aliases |= set(PRD_EXAMPLE_ALIASES.get(cat, []))
            aliases = {a for a in aliases if 2 <= len(a) <= 24 and a != "UNCODED"}
            entries: list[str] = []
            for c in codes:
                entries += code2ids.get(c, [])
            concepts.append({
                "id": "c-" + "-".join(c.lower() for c in codes),
                "canonical": sub,
                "aliases": sorted(aliases),
                "entries": sorted(set(entries)),
                "collections": ["3_措辞表达库"],
            })
    # 词表里的场景域名也进别名，且给它们一个"域级"概念（无 entries，只做扩词）
    for dom in vocab.get("prd_7_2_domains") or []:
        concepts.append({
            "id": "c-domain-" + re.sub(r"\W+", "-", dom),
            "canonical": dom,
            "aliases": [dom],
            "entries": [],
            "collections": [],
        })

    print(f"   vocabulary：{len(concepts)} 个概念；条款号关联成功率 "
          f"{sum(len(v) for v in code2ids.values())}/{sum(len(v) for v in code2ids.values()) + unmatched}"
          f"（未关联 {unmatched} 条）")

    out = [HDR]
    out.append("# 词表来源：kb/l7/registry/l7.json → vocabulary（受控词表，PRD §7.2 九域 / §7.3 七项一票否决）\n")
    out.append("# 作用：kb_search 检索前把查询词扩成「主词 + 别名」，别名权重 0.5。\n")
    out.append("#       命中概念的 entries 另给排序加分（ranking.yaml 的 vocabulary）。\n")
    out.append("# ⚠ 扩的是查询词，不是把正文拉进检索 —— 「正文不参与检索」的纪律没破。\n")
    out.append("concepts:\n")
    for c in concepts:
        out.append(f"  - id: {c['id']}\n")
        out.append(f"    canonical: {json.dumps(c['canonical'], ensure_ascii=False)}\n")
        out.append("    aliases:\n")
        for a in c["aliases"]:
            out.append(f"      - {json.dumps(a, ensure_ascii=False)}\n")
        if c["entries"]:
            out.append("    entries:\n")
            for e in c["entries"]:
                out.append(f"      - {e}\n")
        else:
            out.append("    entries: []\n")
        if c["collections"]:
            out.append("    collections:\n")
            for x in c["collections"]:
                out.append(f"      - {x}\n")
        else:
            out.append("    collections: []\n")
    return "".join(out)


# ── 2. intake.yaml ───────────────────────────────────────────────────────────
def gen_intake() -> str:
    return (
        HDR
        + "# 顶层键：gates / triple_verification（均在 WIRED_META_KEYS 白名单内）\n"
        + "# F3a 口径：与代码兜底值等价 —— 接线但行为不变。收紧留 F3b。\n\n"
        + "gates:\n"
        + f"  half_life_floor_days: {DEFAULT_GATES['halfLifeFloorDays']}          # 半衰期下限，低于此值硬拒（E029）\n"
        + f"  half_life_cache_ceiling_days: {DEFAULT_GATES['halfLifeCacheCeilingDays']}  # 2–7 天这一档应落缓存层，不该走常规入库\n"
        + f"  fingerprint_enforcement: {DEFAULT_GATES['fingerprintEnforcement']}       # warn / error / off\n\n"
        + "# 三重验证阈值：只对 kind=judgment 生效（原文 L0 与 fact 免验）\n"
        + "triple_verification:\n"
        + "  verdict:\n"
        + f"    keep: '> {VERDICT['keep']}'\n"
        + f"    review: '{VERDICT['review']} ~ {VERDICT['keep']}'\n"
        + f"    discard: '< {VERDICT['review']}'\n"
        + "  score_formula: 得分 ÷ 6      # 三项子分各 0/1/2，满分 6；加载器做算术一致性校验\n"
        + "  rejection_rate:\n"
        + "    normal: 0.5\n"
        + "    below_30: 0.7\n"
        + "    above_90: 0.3\n"
    )


# ── 3. health.yaml ───────────────────────────────────────────────────────────
def gen_health() -> str:
    return (
        HDR
        + "# 顶层键：circuit_breaker / alerts / per_type_half_life_days\n"
        + "# F3a 口径：与 ALERT + CIRCUIT_BREAKER 常量等价 —— 接线但行为不变。\n"
        + "# ⚠ freshness 的写法是「最多多少比例过期」，加载器换算成 freshnessMin = 1 - max_expired_ratio。\n\n"
        + "circuit_breaker:\n"
        + f"  health_score_below: {CIRCUIT_BREAKER}     # 综合健康分低于此值直接判失败（熔断线，不是建议线）\n\n"
        + "alerts:\n"
        + f"  freshness:\n    max_expired_ratio: {round(1 - ALERT['freshnessMin'], 4)}    # → freshnessMin = {ALERT['freshnessMin']}\n"
        + f"  conflict:\n    max_ratio: {ALERT['conflictMax']}          # 未裁决冲突占比上限\n"
        + f"  island:\n    max_ratio: {ALERT['islandMax']}            # 孤岛率上限\n"
        + f"  coverage:\n    min_ratio: {ALERT['coverageMin']}          # 覆盖率下限（需黄金问题集才有分母）\n"
        + f"  hallucination:\n    max_ratio: {ALERT['hallucinationMax']}    # 幻觉率上限\n"
        + f"    min_coverage_to_score: {ALERT['evidenceMinCoverage']}  # 证据回验覆盖到该比例才进健康分分母\n"
        + f"  utilization:\n    max_zero_query_ratio: {ALERT['utilizationMaxZero']}  # 零结果查询占比上限（需查询日志）\n\n"
        + "# 分型半衰期：按 topic 取值，优先于全局值。\n"
        + "# ⚠ F3a 故意留空：一旦声明品类而本库 topic 一个都对不上，会报 W031（配了但用不上）。\n"
        + "#   本库 topic 实际只有「规则 / 知识 / 未登记规则码」，分型口径留待 F3b 与权威库对齐后再定。\n"
        + "per_type_half_life_days: {}\n"
    )


# ── 4. boundaries.yaml ───────────────────────────────────────────────────────
def gen_boundaries() -> str:
    onoff = lambda b: "true" if b else "false"
    return (
        HDR
        + "# 顶层键：boundaries —— 接口级写边界。**缺省一律 false（白名单，不是黑名单）。**\n"
        + "# F3a 口径：取 DEFAULT_BOUNDARIES 等价值。\n\n"
        + "boundaries:\n"
        + f"  canonical_write: {onoff(DEFAULT_BOUNDARIES['canonical_write'])}      # 入库能否直写权威树 → ingest() 的 E040 闸门\n"
        + f"  ledger_write: {onoff(DEFAULT_BOUNDARIES['ledger_write'])}         # 账本必须能写（拒收尝试不许静默消失）\n"
        + f"  baseline_write: {onoff(DEFAULT_BOUNDARIES['baseline_write'])}       # 条目基线必须能写（否则 E039 发现不了删除）\n"
        + f"  meta_write: {onoff(DEFAULT_BOUNDARIES['meta_write'])}           # 治理参数不许 agent 改（声明性）\n"
        + f"  provider_call: {onoff(DEFAULT_BOUNDARIES['provider_call'])}        # 不调外部 provider（本库检索是纯本地机械匹配）\n"
        + f"  collection_create: {onoff(DEFAULT_BOUNDARIES['collection_create'])}   # 不自动开新子库（E018 盯着）\n"
    )


# ── 5. ranking.yaml ──────────────────────────────────────────────────────────
def gen_ranking() -> str:
    t = DEFAULT_RANKING["tier"]
    return (
        HDR
        + "# 顶层键：weights —— 检索排序权重。**权重只影响先后，不影响命中**（不会去掉任何条目）。\n"
        + "# F3a 口径：取 DEFAULT_RANKING 等价值。\n\n"
        + "weights:\n"
        + f"  expired: {DEFAULT_RANKING['expired']}              # 已过期条目降权\n"
        + f"  evidence_L1: {DEFAULT_RANKING['evidence_L1']}            # 证据级 L1 降权\n"
        + "  tier:                    # 层级偏好\n"
        + "".join(f"    {k}: {v}\n" for k, v in t.items())
        + f"  superseded: {DEFAULT_RANKING['superseded']}           # 被取代\n"
        + f"  archived: {DEFAULT_RANKING['archived']}             # 已冻结\n"
        + f"  vocabulary: {DEFAULT_RANKING['vocabulary']}           # 词表点名加分（人工策展信号，非语义相似度）\n"
        + f"  evidence_group_default: {DEFAULT_RANKING['evidence_group_default']}  # 未声明 evidence_group 的中性系数（不因缺字段而惩罚）\n"
        + f"  kb_class_default: {DEFAULT_RANKING['kb_class_default']}      # 同上，未声明 kb_class\n"
    )


# ── 6. evidence-groups.yaml ──────────────────────────────────────────────────
EG_GROUPS = {
    "rule": "可直接判定的红线规则（命中即有问题）",
    "evidence": "支撑判定的依据材料（法规条文、指南、平台政策）",
    "sample": "正负样本案例（参照用，本身不是规则）",
    "clause": "逐字保留的条款原文",
    "clue": "线索型材料（登记元数据、待确认项）",
    "coordinate": "坐标型材料（分类说明、口径定义）",
}


def gen_evidence_groups() -> str:
    out = [HDR]
    out.append("# 顶层键：groups / ranking / require_on_new\n")
    out.append("# 条目「拿来干什么」。与 tier（加工到哪层）/ evidence_level（证据多强）/ topic（规则 vs 知识）正交。\n\n")
    out.append("groups:\n")
    for k, v in EG_GROUPS.items():
        out.append(f"  {k}: {json.dumps(v, ensure_ascii=False)}\n")
    out.append("\n# F3a 口径：ranking 留空 = 全部 1.0（不参与排序偏好），与 DEFAULT_EVIDENCE_GROUPS 等价。\n")
    out.append("# 收紧（按组给系数）留 F3b。\n")
    out.append("ranking: {}\n\n")
    out.append("# ⚠⚠ F3a 必须为 false —— 这是本文件最容易踩的坑：\n")
    out.append("#   E042 判据 = 缺 evidence_group 且 require_on_new 为真 且 created_at >= 2026-09-22。\n")
    out.append("#   本库 509 条 created_at 是 2026-09-23，**晚于切换日** —— 一旦改为 true，\n")
    out.append("#   509 个 W036 告警会全部升级成 E042 错误。回填完 evidence_group 之后才允许打开（F3b）。\n")
    out.append("require_on_new: false\n")
    return "".join(out)


# ── 7. index-status.yaml ─────────────────────────────────────────────────────
def gen_index_status(today: str) -> str:
    counts: collections.Counter = collections.Counter()
    for f in sorted(glob.glob(os.path.join(VIEW, "3_措辞表达库", "*", "*.md"))):
        layer = os.path.basename(os.path.dirname(f))
        tier = {"L0-raw": "L0", "L1-facts": "L1", "L2-concepts": "L2",
                "L3-graph": "L3", "L4-contracts": "L4"}.get(layer)
        if tier:
            counts[tier] += 1
    out = [HDR]
    out.append("# 顶层键：index / layer_counts / captured_at\n")
    out.append("# ⚠ layer_counts 的键必须用 TIER 键（L1，不是层目录名 L1-facts）—— 写错会静默失效（报 W039）。\n")
    out.append("#   判据：actual < declared → E045（删除无留痕）；actual > declared 且 L0 → W038。\n\n")
    out.append("index:\n")
    out.append("  status: candidate          # 合法值 candidate / active / deprecated（声明后清掉 W037）\n")
    out.append("  search_backend_ready: false  # 本视图没有独立检索后端：kb_search 走加载器内的机械匹配\n")
    out.append("  rebuilt_at: null             # 未建索引，无重建时间\n")
    out.append("  version_key: null            # 未发版本（全库 kb_version=v0，无 release_id）\n\n")
    out.append("# F3a 口径：只声明**实际存在**的层。L0/L3/L4 本视图为空且不适用，\n")
    out.append("# 故意不写 —— 写了 L0:0 会让任何一条 L0 原文进库都触发 W038，是假警报。\n")
    out.append("layer_counts:\n")
    for tier in ("L1", "L2"):
        if counts.get(tier):
            out.append(f"  {tier}: {counts[tier]}\n")
    out.append(f"\ncaptured_at: '{today}'\n")
    return "".join(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--today", default="2026-09-29")
    a = ap.parse_args()
    if not os.path.isdir(META):
        print(f"目标不存在：{META}", file=sys.stderr)
        return 1
    print(f"目标：{META}")
    w(os.path.join(META, "vocabulary.yaml"), gen_vocabulary(), a.dry_run)
    w(os.path.join(META, "intake.yaml"), gen_intake(), a.dry_run)
    w(os.path.join(META, "health.yaml"), gen_health(), a.dry_run)
    w(os.path.join(META, "boundaries.yaml"), gen_boundaries(), a.dry_run)
    w(os.path.join(META, "ranking.yaml"), gen_ranking(), a.dry_run)
    w(os.path.join(META, "evidence-groups.yaml"), gen_evidence_groups(), a.dry_run)
    w(os.path.join(META, "index-status.yaml"), gen_index_status(a.today), a.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
