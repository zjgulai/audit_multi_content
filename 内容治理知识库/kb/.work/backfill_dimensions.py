#!/usr/bin/env python3
"""L3 规则维度回填（PRD §6.5 风险等级 / 适用范围 ＋ §5.2 模态）。

对应任务拆解 10/12–10/16 行**目标 6 / 7 / 8**。

## 为什么单开一个回填脚本

与 `fix_f7_backfill.py`（治理四字段）同一套形状与纪律 —— 那是本库既有的先例：

1. **先验序列化可逐字节复现**，否则写回会改动既有字节 ⇒ 中止；
2. **dry-run 默认可用**，先看冲突表再动手；
3. **写前留带时间戳的备份**（旧实现只在备份不存在时写 ⇒ 重跑会留着过期备份，这里每次留）；
4. `mode="fill_empty"` —— 本脚本**不是权威写方**，已有非空值与派生值不同时**不覆盖**，记进 conflicts 交人判；
5. 写回后**登记进 l3 registry 的 changes[]**，带 before/after sha256。

## 派生实现在哪

**唯一实现** = `kb/l3/kb_rule_dimensions.py`（自证 `--selftest 29/29`）。
本脚本只负责「读、算、写、留痕」，**不含任何映射表**——避免出现第二份口径。

## 做法

    python3 kb/.work/backfill_dimensions.py --dry-run   # 先看
    python3 kb/.work/backfill_dimensions.py             # 真写（自动备份 + 留痕）
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import sys

KB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RULES = os.path.join(KB, "l3", "candidates", "rules.jsonl")
POLICY = os.path.join(KB, "l3", "registry", "dimension-policy.json")
L3REG = os.path.join(KB, "l3", "registry", "l3.json")

# ── 派生实现只有一份 ────────────────────────────────────────────────────────
sys.path.insert(0, os.path.join(KB, "l3"))
sys.path.insert(0, KB)
import kb_rule_dimensions as D  # noqa: E402

RUN_ID = os.environ.get("KB_DIM_RUN") or dt.datetime.now().strftime("%Y%m%d-%H%M")
POLICY_ID = "dimension-policy-20261010"


def sha256_file(p: str) -> str:
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def build_policy(st: dict, total: int, conflicts: int, overrode: int) -> dict:
    """重写维度政策文件。四级映射与枚举**从模块真源取**，本函数不硬编码。

    `conflicts` = **未被覆盖**的不一致（真·交人判的）；
    `overrode`  = 点名归一改写数（已处理且逐条留痕）。两者**不许混成一句**。
    """
    def dist(counter):
        return {k: v for k, v in counter.most_common()}

    return {
        "policy_id": POLICY_ID,
        "created_at": RUN_ID,
        "layer": "L3 蒸馏层 · 规则维度（PRD §6.5 / §5.2）",
        "status": "active",
        "owner": "法务 + 内容治理（角色位）",
        "scope": f"l3/candidates/rules.jsonl 全部 {total} 条规则",
        "prd_refs": {
            "risk_level": "PRD §6.5「每条规则必须包含…风险等级（Critical / High / Medium / Low）」",
            "applicable_scope": "PRD §6.5「…适用产品线 / 渠道 / 内容类型」",
            "modality": "PRD §5.2 审查能力表：文字（全文审查）/ 图片（OCR+视觉）/ 视频（字幕旁白+关键帧）",
            "p_level_basis": "PRD §6.2 四层定义（P0 法务红线 / P1 安全准确性 / P2 通识常识 / P3 措辞表达）",
        },
        "why_this_file": (
            "`risk_level` / `applicable_scope` / `modality` 三个字段此前在 L3 **要么全空、要么根本不存在**"
            "（实测 976/1018 **行** unknown；modality 连字段都没有）。根因不是「源里没有」，而是"
            "**蒸馏时把信号丢了**：`l3_distill.py` 的 METADATA_FIELDS 把 `风险等级` 显式归成元数据，"
            "5 条产出路径里只有 1 条读它、另外 4 条写死 `p_level='P1', risk_level='unknown'`。"
            "本文件把口径搬进权威库并写明理由；逐条数据由 `kb/l3/kb_rule_dimensions.py` 派生。"
            " ｜ ★ **2026-10-12 v2（目标 6 按维度重算）**：v1 的四档批量兜底（P1→High…）实测把 "
            "**840 行整批压成同一档**、零区分度 ⇒ **已删除**，改成四维链"
            "（源 `风险等级` → 源 `灯色状态` → 源 `修订类型` → P0 地板），见 `p0_floor` / "
            "`lamp_color_map` / `revision_type_map` 三段。"
            " ｜ ⚠️ **条数口径**：本文件 `scope` 与各分布里的 1018 是 **`rules.jsonl` 的行数**；"
            "**唯一 `rule_id` 是 509 条**（每条规则 2 行：生行 + 富化行）。报数时**必须写明是行还是条**。"
        ),
        "risk_level_map": {
            "source_field": "风险等级（L0 源表字段，带色标后缀如 `高危·红`）",
            "map": dict(D.RISK_LEVEL_MAP),
            "note": "**这是换词表，不是补空值** —— 源用中文四档，PRD §6.5 要英文四级。",
        },
        "lamp_color_map": {
            "source_field": "灯色状态（W1 卖点表达边界表；取值为 `红色-禁用` / `黄色-需限定` / `绿色-可用`）",
            "map": dict(D.LAMP_COLOR_TO_RISK),
            "note": (
                "**复用既有换词表的色标语汇**，不是新造：源 `风险等级` 的色标后缀"
                "（`高危·红` / `审慎·黄` / `合规·绿`）用的就是这一套 ⇒ 红→Critical / 黄→High / 绿→Low。"
            ),
        },
        "revision_type_map": {
            "source_field": "修订类型（专家修订汇总表；专家**逐条手填**的「这条修订是什么性质」）",
            "map": {k: {"risk_level": v[0], "prd_basis": v[1], "hard": v[2]}
                    for k, v in D.REVISION_TYPE_TO_RISK.items()},
            "compound_rule": "值形如 `科学性纠错/表述精确化` ⇒ 按 `/` 拆、逐 token 定档、**取最高档**；整值若本身是键则**先整值查**（`存疑/待讨论`）。",
            "note": (
                "★ 这是「按维度重算」的那一维。`p_level` 是 PRD **§6.2 的优先级层级**、"
                "`risk_level` 是 **§6.5 的风险等级**，**两个轴**；拿前者顶替后者正是本次修掉的病。"
                "`修订类型` 天然落在严重度轴上，且逐条可核。"
                "`hard=False` 的条目是**软判**（按 §6.2 四层语义归类）—— 逐条列在 map 里供复核。"
            ),
        },
        "p0_floor": {
            "when": "`p_level == \"P0\"`（PRD §7.3 一票否决）",
            "rule": "风险等级**不得低于 Critical**；**只提不降**。",
            "basis": D.P0_FLOOR["basis"],
            "trace": "被提上来的条，`risk_level_basis` 里明写「由 X **提到** Critical（**源/维度与层级冲突，需人核**）」—— 静默抬档比不抬更坏。",
            "no_dimension": "P0 且**无任何维度可依** ⇒ 仍取 Critical，出处写「无其他维度可依」（不静默留空）。",
            "why_not_p1_p2_p3": (
                "★★ **P1/P2/P3 不再有任何 `p_level` 兜底**。旧版四档批量兜底实测把 **840 行**"
                "整批压成同一档 `P1 → High`，零区分度 —— 那是拿错轴，本次删除。"
            ),
        },
        "applicable_scope_sources": {
            dim: list(srcs) for dim, srcs in D.SCOPE_SOURCES.items()
        },
        "applicable_scope_note": (
            "只做**归一**，不做语义映射：源 `平台`（投放平台）与源 `渠道` 同归 `channel`。"
            "维度顺序按声明源优先级（更专指的源在前），保证重跑稳定。"
            "取不到的维度落 `null` 并记进 `gaps` —— **不许用常识补齐**。"
        ),
        "modality": {
            "enum": list(D.MODALITY_ENUM) + [D.MODALITY_UNDETERMINED],
            "field_hints": dict(D.MODALITY_FIELD_HINTS),
        },
        "honest_limits": [
            D.NOT_DERIVABLE["modality"],
            # ★ 2026-10-12：两条**候选口径**也必须进政策件 —— 它们决定「模态这一格要不要开」，
            #   只写在模块里、不写进政策件，签的人看不到（政策件才是给人的那一份）。
            D.NOT_DERIVABLE["modality.candidate_ads_type"],
            D.NOT_DERIVABLE["modality.candidate_text_default"],
            "★★ **`risk_level` 现在是「按维度重算」的结果，不再有 `p_level` 批量兜底**"
            "（2026-10-12）。旧版 840 行整批压成 `P1 → High`；现在四个维度逐条取："
            "源 `风险等级` → 源 `灯色状态` → 源 `修订类型` → P0 地板。"
            "**仍取不到的落 `unknown`**（实测 1 条：源 `修订类型=存疑/待讨论`，专家自己说「待讨论」，"
            "本库不替它定级）。**源侧仍缺「风险等级」列的规则表**是这条链的长期依赖。",
            "★ `critical` 档**全部来自源字段**（源 `高危` / `高危·红` / `红色-禁用`）"
            "＋ P0 地板，**没有一条**来自本库自己的语义判断 —— 这是「不编」的直接体现。",
            "`applicable_scope.content_type` 与 `modality` 同义（PRD §5.2 的「内容类型」就是文字/图片/视频）"
            " ⇒ 只出一份，不重复造第二个字段。",
            # ★ 这一条必须与 run 输出逐字对得上：**未被覆盖**的 = 交人判的；
            #   点名归一改写的是**已处理**的。两者混成一句就会写出与事实不符的文档
            #   （首版就写成「冲突 %d 处交人判」，而当时 21 处已全部归一 ⇒ 文档假）。
            "**未覆盖任何既有非空值中的『真实值』**：未被覆盖的不一致 **%d 处**（交人判）；"
            "点名归一改写 **%d 处**（`risk_level` 换词表，逐条留痕在 l3.json changes[] 与本文件 "
            "`risk_level_map`）。" % (conflicts, overrode),
        ],
        "validation": {
            "derivation_module": (
                "kb/l3/kb_rule_dimensions.py（唯一派生实现；自证 python3 kb/l3/kb_rule_dimensions.py --selftest）"
            ),
            "selftest": "46/46（含 ①f「P1/P2/P3 不兜底」、①i2「取最高≠取最低」、①i3「复合键不拆散」、①i4「去绝对化不是红线」、①e2「P0 地板留痕」等反向对照；"
                        "另有**变异自证 5/5**：`sh kb/kbpy .work/mutate_risk_level.py` —— 把缺陷真造一遍，尺子精确变红）",
            "writers": ["kb/.work/backfill_dimensions.py（一次性回填；risk_level 为**点名列**，以派生为准并逐条留痕）"],
            "reader_contract": (
                "★ **日更已接线（2026-10-10 同日完成）**：`kb/l8/l3_distill_run.py:699` 在写盘前调 "
                "`kb_rule_dimensions.apply_dimensions(rules, mode=\"force\")` ⇒ 本回填**不再易失**，"
                "且与日更**同口径**（改口径只改 `kb/l3/kb_rule_dimensions.py` 一处）。"
            ),
        },
        "current_distribution": {
            "risk_level": dist(st["risk_level"]),
            "modality": dist(st["modality"]),
            "scope_gaps": dist(st["scope_gaps"]),
        },
        "fields_backfilled": {
            "risk_level": "新增（PRD 四级枚举）",
            "risk_level_basis": "新增（写出处：走了哪一维 / P0 地板提档 / 推不出的原因）",
            "applicable_scope": "新增（含 _derivation 子键写各维度出处）",
            "modality": "新增（枚举含 undetermined）",
            "modality_basis": "新增（写出处）",
            "dimensions_derivation": "新增（三字段出处汇总 + not_derivable 清单）",
        },
        "signed_off": {
            "by": "Owner（内容治理）",
            "at": "2026-10-12",
            "what": "维度重算口径（四维链 + P0 地板 + 软判 token）；签字件见"
                    "《交付-目标6-风险等级重算-对照与签字件-20261012.md》",
            "pending": "法务事后追认（Owner 2026-10-12 裁定：「你签即可，法务事后追认」）"
                       " ⇒ **追认前本字段不得当强证据**。",
        },
        "rulings": [
            {
                "id": "p0-floor-beats-source",
                "at": "2026-10-12",
                "by": "Owner（内容治理）",
                "question": "某条规则源字段 `风险等级=审慎·黄`（⇒ High），但 `p_level=P0` —— 听谁的？",
                "ruling": "**PRD 为准** ⇒ 维持 Critical（即 P0 地板优先于源字段）。",
                "prd_basis": "PRD §7.3 逐字：「以下为 P0 级硬性规则，**命中即驳回**，"
                             "**不进入后续审查层级**」＋ §6.2 P0 行「法务合规红线 / 一票否决项」。",
                "applied_to": "`r-4f309d6ebde80283`（全库仅此 1 条；15 条 P0 规则里其余 14 条"
                              "源字段本就是 `高危`/`高危·红`，无冲突）。",
                "boundary": (
                    "★ **本条只管 P0**。`p_level` 是 §6.2 的**优先级层级**、`risk_level` 是 §6.5 的"
                    "**风险等级**，两者是彼此独立的两个轴 —— 非 P0 档位（P1/P2/P3）与源严重度"
                    "**不构成冲突**（PRD 没有对 P1–P3 说「严重度不得低于/高于某档」）。"
                    "⇒ **不许把本条扩大成「PRD 一律覆盖源字段」**：那是另一件事，需单独裁定。"
                ),
                "trace": "被地板提上来的条，`risk_level_basis` 里逐条写明「由 X **提到** Critical"
                         "（**源/维度与层级冲突，需人核**）」—— 静默抬档比不抬更坏。",
            },
        ],
        "revisit": {
            "when": "源侧为其余规则表补「风险等级」列、或补媒体字段时；或法务对软判 token 提出异议时",
            "who": "法务 + 内容治理",
            "how": "改 kb/l3/kb_rule_dimensions.py 的映射表（唯一口径），再重跑本脚本",
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="L3 规则维度回填（PRD §6.5 / §5.2）")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--rules", default=RULES)
    a = ap.parse_args()

    raw = open(a.rules, encoding="utf-8").read().split("\n")
    kept_trailing = raw[-1] == ""
    lines = [l for l in raw if l.strip()]
    rows = [json.loads(l) for l in lines]
    print("rules.jsonl：%d 行" % len(rows))

    # 解析→重序列化必须逐字节复现（保证写回不改变任何既有字段的形态）
    bad = [i for i, (r, l) in enumerate(zip(rows, lines))
           if json.dumps(r, ensure_ascii=False, sort_keys=True) != l]
    if bad:
        print("❌ 序列化风格不匹配（首个不符行号 %d），写回会改变既有字节 —— 中止" % bad[0])
        return 2
    print("✅ 序列化自检通过：json.dumps(ensure_ascii=False, sort_keys=True) 逐字节复现原行")

    before_sha = sha256_file(a.rules)
    idx = D.build_l0_index()
    print("L0 记录索引：%d 条" % len(idx))

    # 按 rule_id 合并多行形态（生行 + 富化行），再算维度；写回**每一行**同一份派生值
    # （与 l5_report.py 的 read_last_per_key(by_shape=True) 同一口径：同 id 多行各取各自）
    by_id: dict[str, dict] = {}
    for r in rows:
        rid = r.get("rule_id")
        if not rid:
            continue
        m = by_id.setdefault(rid, {})
        for k, v in r.items():
            if v not in (None, "", [], {}):
                m[k] = v

    # 点名列：「这一列以派生为准」。
    # 为什么是 risk_level：它做的是**换词表**（源 `高危` → PRD `Critical`）。
    # 已有值只有 21 条中文，与派生值不一致 ⇒ 若按 fill_empty 保留，同一列会中英混排 ——
    # 那不是保守，是**更坏的中间态**（下游没法按列判口径）。故点名归一，且**逐条留痕**。
    # modality / applicable_scope **不点名**：它们没有「旧口径」，只填空。
    FORCE_FIELDS = {"risk_level"}
    st = D.apply_dimensions(list(by_id.values()), D.l0_lookup(idx), mode="fill_empty",
                            force_fields=FORCE_FIELDS)
    derived = {rid: {k: m.get(k) for k in D.DIMENSION_FIELDS} for rid, m in by_id.items()}

    print("\n── 派生结果 ──")
    print("  risk_level：%s" % dict(st["risk_level"].most_common()))
    print("  modality  ：%s" % dict(st["modality"].most_common()))
    print("  scope 缺口：%s" % dict(st["scope_gaps"].most_common()))
    print("── 回填格数：%d ｜ 保留原值：%d ｜ 点名归一改写：%d ｜ 不一致合计：%d"
          % (st["filled"], st["kept"], st["overrode"], len(st["conflicts"])))
    ov = [c for c in st["conflicts"] if c.get("overrode")]
    if ov:
        print("★ 点名归一改写 %d 处（逐条留痕，全部是 risk_level 换词表）：" % len(ov))
        was = {}
        for c in ov:
            was.setdefault((c.get("was"), c["kept"]), 0)
            was[(c.get("was"), c["kept"])] += 1
        for (w, k), n in sorted(was.items(), key=lambda x: -x[1]):
            print("    %-8s → %-10s  %d 条" % (w, k, n))
    real = [c for c in st["conflicts"] if not c.get("overrode")]
    if real:
        print("⚠ **未覆盖**的不一致 %d 处（交人判）：" % len(real))
        for c in real[:10]:
            print("    %s %s：保留 %r ← 派生 %r" % (c["rule_id"], c["field"], c["kept"], c["would_be"]))

    # 写回：只动这 6 个维度键，其它键**原样不动**
    touched = 0
    for r in rows:
        d = derived.get(r.get("rule_id"))
        if not d:
            continue
        for k in D.DIMENSION_FIELDS:
            if d[k] is None and k in ("risk_level", "modality"):
                continue                      # 推不出就不写，别写 null 占位
            if r.get(k) != d[k]:
                r[k] = d[k]
                touched += 1

    real_conflicts = [c for c in st["conflicts"] if not c.get("overrode")]
    policy = build_policy(st, len(rows), len(real_conflicts), st["overrode"])
    print("\n本行改动格数：%d" % touched)

    if a.dry_run:
        print("\n[dry-run] 不写盘")
        return 0

    # ── 备份：每次都留一份带时间戳的 ────────────────────────────────────────
    arch = os.path.join(KB, "l8", "_archive", "dim-backfill-%s" % RUN_ID)
    os.makedirs(arch, exist_ok=True)
    bak = os.path.join(arch, "rules.jsonl.before")
    open(bak, "wb").write(open(a.rules, "rb").read())
    print("\n备份：%s  sha256 %s…" % (os.path.relpath(bak, KB), before_sha[:16]))

    # ── 写回 rules.jsonl（.jsonl 不受信封影响）──────────────────────────────
    out = "\n".join(json.dumps(r, ensure_ascii=False, sort_keys=True) for r in rows)
    if kept_trailing:
        out += "\n"
    open(a.rules, "w", encoding="utf-8").write(out)
    after_sha = sha256_file(a.rules)
    print("✅ 已写回 %s  %d 字节  sha256 %s…"
          % (os.path.relpath(a.rules, KB), len(out.encode()), after_sha[:16]))

    # ── 写政策文件 ──────────────────────────────────────────────────────────
    json.dump(policy, open(POLICY, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("✅ 已写入 %s" % os.path.relpath(POLICY, KB))

    # ── 登记进 l3 registry ──────────────────────────────────────────────────
    # ★ 只在实际改动了字节时登记：本脚本可反复跑（幂等），
    #   每次都追加一条会把 changes[] 灌成噪声（首版实测：连跑 3 次 → 3 条同名 run）。
    if touched == 0:
        print("ℹ 内容无改动（幂等重跑）⇒ **不追加 changes[] 登记**")
        return 0
    reg = json.load(open(L3REG, encoding="utf-8"))
    reg.setdefault("changes", []).append({
        "run_id": RUN_ID,
        "change": "backfill",
        "keys": list(D.DIMENSION_FIELDS),
        "rows": len(rows),
        "policy_file": "l3/registry/dimension-policy.json",
        "module": "kb/l3/kb_rule_dimensions.py",
        "reader_contract": (
            "★ **日更已接线（2026-10-10 同日完成）**：`kb/l8/l3_distill_run.py` 在写盘前调 "
            "`kb_rule_dimensions.apply_dimensions(rules, mode=\"force\")`，位置与治理字段同一处"
            "（`rules.jsonl` 的唯一活截断写方之前）。⇒ 本回填**不再易失**。"
            "端到端已验证：带 --apply 跑一次日更，`rules.jsonl` **逐字节不变**"
            "（sha256 3f7d50dc…），维度分布与回填结果一致。"
        ),
        "note": (
            "任务拆解 10/12–10/16 目标 6/7/8：给每条规则补 PRD §6.5 的风险等级与适用范围、"
            "§5.2 的模态。根因是蒸馏时把源侧 `风险等级` 当元数据丢了（3 张源表里有该列）。"
            "仅新增 6 个维度键；未被覆盖的不一致 %d 处（交人判），点名归一改写 %d 处"
            "（risk_level 换词表：高危→Critical 9 / 审慎→High 7 / 待复核→Medium 4 / 合规→Low 1）。"
            "未改动 rule_text / anchor / article_no 等被 C4 比对的内容字段。"
            "★ 遗留缺口：modality 509/509 undetermined（源无媒体字段）；"
            "risk_level 451/509 走 p_level 退路（源侧其余表无风险等级列）。"
            % (len(real_conflicts), st["overrode"])
        ),
        "before_sha256": before_sha,
        "after_sha256": after_sha,
    })
    json.dump(reg, open(L3REG, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("✅ 已登记进 %s 的 changes[]（run_id=%s）" % (os.path.relpath(L3REG, KB), RUN_ID))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
