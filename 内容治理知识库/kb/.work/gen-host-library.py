#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从分层新库（kb/l0…l6）派生一套「宿主库」形态的知识条目，供工作台只读镜像。

为什么要有这个脚本
------------------
工作台（http://127.0.0.1:4317）的知识库是**宿主库的单向只读镜像**，判据写死在
`工作台/apps/server/src/kb/kb-sync.ts`：只认
  <宿主根>/<子库目录>/L{0-raw,1-facts,2-concepts,3-graph,4-contracts}/*.md
（YAML frontmatter + 正文），外加 `<宿主根>/_meta/collections.yaml` 登记表。
而本工作区的新库是**分层 json/jsonl**（l0 素材 / l2 units / l3 规则 / l5 P0 / l6 索引），
两者形态不同 —— 镜像器扫过去一个条目都进不去。

这个脚本只做一件事：把新库里**已经是结论的那一层**（l3 规则，含 l5 P0 判定）渲染成宿主
条目的 md。它是**派生视图**，不是权威库：
  · 不改新库任何文件（只读）；
  · 不新增判断，只做字段搬运与组织（原文照抄，不做摘要式改写）；
  · 版本、生效期、owner 这些新库没有的字段，一律显式标注「派生缺省」，不含糊其辞。

输出
----
  <out>/<子库目录>/<层目录>/<id>.md     —— 每个 rule_id 一条（同一 rule 的 3 个行视图合并）
  <out>/_meta/collections.yaml          —— 子库登记表（workbench 读写它取 owner/status/entry_count）
  <out>/_meta/DERIVED.md                —— 派生说明（这张视图怎么来的、哪些字段是缺省）
  <out>/_meta/derivation.json           —— 溯源台账：每条 md 的来源文件 + sha256 + 规则字段

用法
----
  python3 kb/.work/gen-host-library.py --out /tmp/hostlib
"""

from __future__ import annotations

import argparse
import base64
import collections  # noqa: F401  (仅用 Counter/OrderedDict，别再给局部变量起同名)
import hashlib
import json
import os
import glob
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import date, timedelta

KB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # …/内容治理/kb

# ── 源文件 ──────────────────────────────────────────────────────────────
SRC_RULES = os.path.join(KB, "l3", "candidates", "rules.jsonl")
SRC_L3_REG = os.path.join(KB, "l3", "registry", "l3.json")
SRC_P0 = os.path.join(KB, "l5", "p0_patterns.jsonl")
SRC_UNITS = os.path.join(KB, "l2", "units.jsonl")

# ── 目标形态（与 kb-sync.ts 的 ENTRY_DIRS / frontmatter.ts 的字段一一对应）──
LIBRARY_NAME = "内容治理知识库"
LIBRARY_DISPLAY = "Momcozy知识库 · 内容治理（派生视图）"
LIBRARY_OWNER = "刘华丽"   # ⚠ 这是**库/子库级**的接受人（collections.yaml / kb-classes.yaml / manifest 用），
                          #    与**逐条**的 meta["owner"] 是两件事 —— 后者 F8 起从权威库读。
DOMAIN_OWNER_NOTE = "派生视图统一挂入库接受人；逐条领域 owner 待新库补 owner 字段后回填"

# 层目录只能落在这五个里（镜像器的 ENTRY_DIRS）
#
# ── 修复计划 F5（2026-09-29）：entry / boundary 从 L2-concepts 降到 L1-facts ──
#
# 症状：`kb_check` 报 **E021 × 56** —— 56 条 `form=entry` 落在 L2-concepts、`kind=judgment`，
# 而加载器对「tier != L0 且 kind == judgment」的条目**强制要求 `verification` 映射**
# （5 个子键，见加载器 VERIFICATION_REQUIRED）。
#
# 为什么不直接补 verification：三重验证是**人工判断闸门**。派生视图替人打分，
# 等于把闸门变成自我申报 —— 这正是 l3/registry 把这 56 条判断类概念整体排除的理由
# （逐字："三重验证是人工判断闸门；派生视图无权替人打分，编一个等于把闸门变成自我申报"）。
#
# 所以处置是**降层**：承认它们当前只是「规则的可读投影」，不是已过闸的判断。
# E023 只禁止 `fact` 进 L2/L4，**L1-facts 收 fact 合法**，于是：
#   tier : L2-concepts → L1-facts
#   kind : judgment    → fact
# 等人工过完三重验证，再逐条升回 L2-concepts 并补真的 verification。
TIER_BY_FORM = {
    "entry": "L1-facts",
    "revision_pair": "L1-facts",
    "boundary": "L1-facts",
}
TIER_FALLBACK = "L1-facts"

# ⚠ F8（2026-09-29）：以下三个常量**不再是产出值的来源**，只在权威库缺字段时兜底。
# 产出值来自 `kb/l3/candidates/rules.jsonl` 每行的 owner / half_life_days / valid_until，
# 政策见 `kb/l3/registry/half-life-policy.json`。兜底发生时会写进 derivation 的
# `governance_fallbacks`，**不静默**。
OWNER_FALLBACK = "法务"
DERIVED_HALF_LIFE_DAYS = 180
DATA_LEVEL = "L2"  # 公司内部材料，未含自然人信息；与实际密级无冲突
SENSITIVITY = "L2"

# 风险等级 → 人读标签（原文照搬，只做归一化到单一取值）
ORDER_P_LEVEL = ["P0", "P1", "P2", "P3", "P4"]

# ═══════════════════════════════════════════════════════════════════════
# l8 补丁（第三轮，2026-09-23）：把派生字段对齐到加载器的 schema
#
# 触发原因：E001（读不到 frontmatter）修好之后，露出一整层**词汇表不对齐** ——
# kb_check 报 E002×1018 / E005×509 / E006×509 / E021×509 / W004×509 / W010×509，
# 且孤岛率恒为 1.00。每一条都能在 `~/.dsh/plugins/dsh-kb/lib/kb.js` 找到判据：
#   E005 tier 必须是 L0–L4（TIERS）；E019 tier 值要与所在目录一致（TIER_DIR）
#   E023 kind=fact 不许进 L2/L4；E021 判断类必须有 verification 映射
#   E006 evidence_level 必须是 L1–L5；E036 声明 L2+ 须列 ≥2 个独立来源根
#   W004 source.kind 须在 {file,url,feishu-wiki,feishu-base,meeting,chat}
#   E002 provenance / pii 是必填；E024 provenance 需 {anchor,confidence}
#   孤岛率 = 没被任何条目引用的条目占比（related 恒空 → 1.00）
# ═══════════════════════════════════════════════════════════════════════

# ── 补丁 A：目录名与 tier 值必须拆开 ────────────────────────────────────
# E005 要 L 码，E019 要「tier 值 ↔ 所在目录」一致 ⇒ `tier: L1` 必须待在 `L1-facts/`。
# 旧实现直接把目录名写进 tier（"L1-facts"），E005 × 509。
TIER_VALUE_BY_DIR = {
    "L0-raw": "L0",
    "L1-facts": "L1",
    "L2-concepts": "L2",
    "L3-graph": "L3",
    "L4-contracts": "L4",
}

# ── 补丁 B：judgment / fact 的归属应与层对齐（F5 修订）──────────────────
# E023：kind=fact 不许进 L2/L4（"事实只提供背景，改变不了行为"）。
# 旧分配是反的：entry（判定规则）写成 fact 却放 L2-concepts；
# revision_pair（修订事实记录）写成 judgment 却放 L1-facts。
# 修好 tier 后 E023 会立刻对这 56 条 entry 报错，所以必须一起正过来。
#
# F5 再修订：`entry` 原本标成 `judgment` 放进 L2-concepts，于是撞上 E021×56
# （judgment 必须过三重验证，而派生视图无权代打）。降层后全部为 `fact`，
# 落脚 L1-facts —— E023 不拦 L1，E021 不再适用。
KIND_BY_FORM = {
    "entry": "fact",           # F5：降为事实 —— 未过三重验证前不是「判断」
    "boundary": "fact",        # F5：同上
    "revision_pair": "fact",   # 专家修订的前→后记录 → 事实层
}
KIND_FALLBACK = "fact"

# ── 补丁 C：source.kind 落进枚举，指纹换成 feishu-base 的形态 ──────────
# 旧值 "derived" 不在 SOURCE_KINDS 内 → W004 × 509；且该 kind 没有指纹校验规则
# → W010 × 509。这批规则的来源就是飞书 Base 记录，取 feishu-base，
# 指纹按加载器约定的 `<baseToken>/<tableId>` 形态（见 verifyFingerprint 注释）。
SOURCE_KIND = "feishu-base"

# `evidence_group`（T2）：这条知识「拿来干什么」。枚举必须与 _meta/evidence-groups.yaml
# 的 groups 一致，不许在条目里自创（自创会让同一用途出现几个别名）。
# 本视图全部 509 条都是蒸馏出的可判定规则 → `rule`。理由与「不是别的组」的判据
# 写在赋值处（搜索 EVIDENCE_GROUP）。
EVIDENCE_GROUP = "rule"

# 证据 anchor 里的表名 → 飞书 Base token / tableId（按 kb/l0 登记元数据实测）。
# corroborated_by 也用它：加载器 sourceRootOf() 把 ref 解析成 base token 去重，
# 只有 **≥2 个不同来源根**才算「多来源互证」（E036）。
TABLE_TO_BASE = {
    "专家修订汇总表": "SKkkbdZi9aRuMzs7ob0cpSYHnQg",
    "广告文案明细": "Lk3Qb8y2QaVyZns6gprcVNE9nA0",
    "风险文案改写建议库（分型号分渠道）": "Lk3Qb8y2QaVyZns6gprcVNE9nA0",
    "品线内容边界规则库": "Lk3Qb8y2QaVyZns6gprcVNE9nA0",
    "W1卖点表达边界（品线反馈0910）": "Lk3Qb8y2QaVyZns6gprcVNE9nA0",
}
TABLE_TO_TABLE_ID = {
    "专家修订汇总表": "tbl8AI00JZO1iZtp",
    "广告文案明细": "tblcbk4XiW6471YN",
    "风险文案改写建议库（分型号分渠道）": "tblLxUfPz4Wqp2na",
    "品线内容边界规则库": "tblD1MiUK1v5fdjD",
    "W1卖点表达边界（品线反馈0910）": "tblqUTAKFkWheU49",
}
DEFAULT_BASE = "Lk3Qb8y2QaVyZns6gprcVNE9nA0"
DEFAULT_TABLE_ID = "tblcbk4XiW6471YN"
FEISHU_HOST = "momcozy-in.feishu.cn"

# 同一分组内给每条规则挂几个 related 邻居（用来把孤岛率从 1.00 打下来）
# （原 RELATED_NEIGHBORS_PER_GROUP=3 随 W025 处置 B 一并删除：它只服务于
#  「同主来源表指向紧随其后的 N 条」那条合成边，那条已按人确认的决策删掉。）

# provenance.confidence 的枚举（kb.js: CONFIDENCE = 确定 / 存疑 / 待确认）
CONFIDENCE_CERTAIN = "确定"


# ── l8 优化轮 ①：risk_level 枚举收敛（纯归一，不编造）────────────────────
# 源库（kb/l3）的 risk_level 有 12 种写法、其中 unknown 1417/1527 行：
#   unknown / 高危·红 / 红色-禁用 / 黄色-需限定 / 审慎 / 审慎·黄 / 审慎·黄；高危·红 /
#   审慎·黄；待复核·灰；高危·红 / 待复核 / 绿色-可用 / 合规 / 高危…
# 多值写法（"审慎·黄；高危·红"）的含义是「同时命中多档」，**取最严**（红 > 黄 > 绿）。
# 归一后只留四个值：红 / 黄 / 绿 / 未定级。原始写法不丢，落进 `risk_level_raw`。
# 「未定级」不允许由 p_level 反推 —— 那等于替内容负责人定级；它如实表示「源库没定级」。
RISK_CANON = ("红", "黄", "绿", "未定级")
_RISK_RED = ("红", "高危", "禁用")
_RISK_YELLOW = ("黄", "审慎", "待复核", "限定")
_RISK_GREEN = ("绿", "可用", "合规")


def normalize_risk_level(raw) -> str:
    """把源库的 risk_level 写法归一成 {红, 黄, 绿, 未定级}；空/unknown → 未定级。"""
    s = str(raw or "").strip()
    if not s or s.lower() in ("unknown", "none", "null", "-", "待定"):
        return "未定级"
    if any(k in s for k in _RISK_RED):
        return "红"
    if any(k in s for k in _RISK_YELLOW):
        return "黄"
    if any(k in s for k in _RISK_GREEN):
        return "绿"
    return "未定级"


def tables_of(rows: list) -> "collections.Counter":
    """从 evidence_units 的 anchor（`#<表名>/<record_id>/<字段>`）里数出来源表。

    为什么用 anchor 而不是 authority_source_table：后者实测有 53 条为空，
    且与证据实际落点不一致（见 l3 registry 与线B 对账）。anchor 是逐条证据的坐标，
    是「这条证据实际来自哪张表」的直接记录。
    """
    counter: collections.Counter = collections.Counter()
    for row in rows:
        for unit in row.get("evidence_units") or []:
            anchor = unit.get("anchor") or ""
            if not anchor.startswith("#"):
                continue
            parts = anchor[1:].split("/", 1)
            if parts and parts[0]:
                counter[parts[0]] += 1
    return counter


def bases_of(table_counter: "collections.Counter") -> list:
    """把来源表映射成去重后的 base token 列表（机器可数，用来判「多来源互证」）。"""
    order: list = []
    for table in table_counter:
        base = TABLE_TO_BASE.get(table)
        if base and base not in order:
            order.append(base)
    return order


def build_typed_links(grouped: dict) -> dict:
    """给每条规则挑**带类型的**邻居：只认「同 rule_code」这一条真有依据的关系。

    ── 为什么换掉原来的 related（W025 处置 B，2026-09-29）─────────────────
    旧实现 `build_related_map` 的文档自己写着它有两个依据：
      · 组 1「同 rule_code」—— 真的规则族关系（如 H07 = W-1.6 + W-1.53，组内互指）
      · 组 2「同主来源表」—— 原话是「每条指向稳定序上紧随其后的 N 条，**使全组都有入边**」
    组 2 是**为把孤岛率从 1.00 压到 ≤0.2 而制造的合成边**：邻居只是排序上的下一条，
    与语义毫无关系。于是「孤岛率 = 0.0」这个绿**是造出来的**，不是知识真的互联。

    换法：只保留组 1，落成 `complements`，并**删掉 `related`**。
    加载器只认「related 为空/不存在」才消 W025（把内容搬进 typed keys 不算），
    所以两件事必须一起做。

    ── 这个类型的依据与它的诚实边界 ───────────────────────────────
    `complements`（互补）在这里的含义是**同规则族**：它们共用一个 rule_code，
    是该码下的不同条款。这是**结构上的同族关系，不是语义上论证过的互补** ——
    逐条的语义互补仍要人写。别把它读成「机器判断了这两条互补」。

    为什么不用别的槽：`derived_from`（依据）与 `contrasts_with`（相反）都没有依据 ——
    rule_code 相同的条款之间既不是「谁依据谁」，也不是「互相矛盾」。类型必须由证据决定，
    不能为了让字段好看而挑一个。

    ── 代价（已由人确认接受）────────────────────────────────────
    清掉合成边后能挂上边的只剩 30 条规则（22 个码里成员 ≥2 的 15 个码）。
    孤岛率会从 0.0 升到约 0.94 —— **这才是真的**：472/509 条规则与其他条目
    没有任何真实引用关系。要真正降下来，需要来源表提供真实的关联列
    （本轮核对：`supersedes`/`superseded_by` 全为 0/509，没有真替代边；
    `pair_ref` 有 354/509 但指向 **L2 的 unit_id、不是条目 id**，直接当链接会成死链）→ 属业务动作。
    """
    info: dict = {}
    for rule_id, rows in grouped.items():
        info[rule_id] = pick_best(rows, "rule_code", lambda v: v) or ""

    by_code: dict = {}
    for rid, code in info.items():
        if code:
            by_code.setdefault(code, []).append(rid)

    links: dict = {}
    for _code, members in by_code.items():
        if len(members) < 2:
            # 单成员码挂不上边 —— 显式跳过并留下痕迹，别让它悄悄变成孤岛
            continue
        # 稳定序（article_no, rule_id）保证重跑一致；组内互指（不用成环，组内两两可达）
        ordered = sorted(members)
        for rid in ordered:
            links[rid] = sorted(x for x in ordered if x != rid)
    return {rid: sorted(safe_name(t) for t in targets) for rid, targets in links.items()}


REC_ID_RE = re.compile(r"rec[A-Za-z0-9]{10,}")


def record_ids_of(rows: list) -> list:
    """从证据单元的锚点里取出来源**记录** id（W023 的回填口径）。

    为什么必须存这个：`source.fingerprint` 只有「表/文档 @rev」粒度 ——
    回源时只能判断「这个表变过没有」，判断不了「哪条记录变了」。
    本库已经为此付过代价：pending 里那次回源追「rev 98→367」，实测发现是整批
    规则迁表，最后只能人肉核 5 条。加载器 W023 引的判据很干脆：
    *an anchor not stored at ingest cannot be recovered*。

    为什么这里能**确定**取到：证据单元的锚点形如
    `#专家修订汇总表/recvoyJ6L9s6Mi/修订位置（原文引用）`，记录 id 就在锚点里，
    不是猜的。实测 509/509 行都能取到（每行 1–57 个，均值 2.3）。
    """
    ids: set = set()
    for row in rows:
        for unit in (row.get("evidence_units") or []):
            ids.update(REC_ID_RE.findall(unit.get("anchor") or ""))
    return sorted(ids)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def base64url(text: str) -> str:
    """与 node 的 `Buffer.from(x,'utf8').toString('base64url')` 一致（无 padding）。"""
    return base64.urlsafe_b64encode(text.encode("utf-8")).decode("ascii").rstrip("=")


def render_for_chunking(meta: dict, body: str) -> str:
    """逐字对齐工作台 `apps/server/src/kb/frontmatter.ts#renderForChunking`。

    这不是「另一套实现」，是同一份渲染逻辑的移植：工作台那边用它决定 FTS 里放什么。
    正则对齐时验过（见 kb/.work/diff-render.mjs：同一份 md 两边渲染结果逐字节相同）。
    """
    lines: list[str] = []
    if meta.get("title"):
        lines.append(f"# {meta['title']}")
    if meta.get("summary"):
        lines.append(f"摘要：{meta['summary']}")
    asks = meta.get("asks") or []
    if asks:
        lines.append("\n".join(["能答："] + [f"- {item}" for item in asks]))
    if meta.get("not_proves"):
        lines.append(f"不能证明：{meta['not_proves']}")
    if meta.get("forbidden"):
        lines.append(f"禁止读法：{meta['forbidden']}")
    facts: list[str] = []
    if meta.get("tier"):
        facts.append(f"档位 {meta['tier']}")
    kind = meta.get("kind")
    if kind:
        facts.append("判断" if kind == "judgment" else ("事实" if kind == "fact" else str(kind)))
    if meta.get("evidence_level"):
        facts.append(f"证据级 {meta['evidence_level']}")
    if meta.get("owner"):
        facts.append(f"负责人 {meta['owner']}")
    if meta.get("valid_until"):
        facts.append(f"有效期至 {meta['valid_until']}")
    if facts:
        lines.append(" · ".join(facts))
    if not lines:
        return body
    return "\n".join(lines) + "\n\n" + body


def load_jsonl(path: str) -> list[dict]:
    out: list[dict] = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def yaml_scalar(value) -> str:
    """只写脚本自己能保证读回来的标量与列表项（不引第三方 yaml 库）。

    引号选择有个坑：工作台的 yaml-lite **不解释转义序列**（`"a\\"b"` 读回来带反斜杠）。
    所以值里含 `"` 时不能靠转义，得换单引号包（值里同时含两种引号才退回双引号 + 转义，
    这种值不该出现在知识库条目里）。
    """
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value).replace("\r", " ").replace("\n", " ").strip()
    needs_quote = any(ch in text for ch in ":#{}[],&*!|>'\"%@`") or text == ""
    if not needs_quote:
        return text
    if '"' in text and "'" not in text:
        return "'" + text + "'"
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


# ── l8 补丁（2026-09-23）：归属字段 + 明文写盘 ─────────────────────────
#
# 背景与实测见 `kb/l8/diagnosis.md`：这台机器上有一层**按后缀生效的写封装**，
# python/perl 直接写 `.md` 会落盘成「4096 字节前缀 + 原文」的信封；宿主侧的
# Electron/Node 读取者（加载器 `~/.dsh/plugins/dsh-kb/lib/kb.js`、工作台镜像器）
# 读到的就是信封，frontmatter 切不出来 → 条目全判 E001、被镜像器当非 UTF-8 跳过。
# 而 `cat` / `python3` 侧看到的是明文，所以「文件看起来是好的」。
KB_CLASS_BY_DIR = {
    "1_外部标准库": ["外部标准库"],
    "2_内部正负样本库": ["内部正负样本库"],
    "3_措辞表达库": ["措辞表达库"],
    "4_产品描述库": ["产品描述库"],
}


def kb_classes_yaml() -> str:
    """`_meta/kb-classes.yaml` 的内容 —— **必须与条目里的 kb_class 值同源**。

    加载器 `loadKbClasses()` 读这个文件当枚举；文件不在时枚举为空集，
    任何 kb_class 值都会被判 E046（实测：产出里写了 `kb_class: [措辞表达库]`
    但输出根没有这个文件时，509 条全判 E046）。所以生成器写了 kb_class 就必须
    一起产出本文件。
    """
    lines = [
        "# kb_class 枚举表（加载器 T4 闸门读它）—— 由 kb/.work/gen-host-library.py 生成",
        "# `kb_class` = 这条知识「出自哪一类素材」，四类出自 PRD §5.8。",
        "# 加类要改这里、并在 KB_CLASS_BY_DIR 里加映射；不许在条目里自创（跨系统路由靠它对齐）。",
        "version: 1",
        f"updated_at: '{date.today().isoformat()}'",
        # 这里**故意不写 owner**（W019）：加载器 loadKbClasses() 只读 classes / ranking /
        # multi，从不读 owner —— 一个不生效的顶层键，且整个文件里别的键真的在生效，
        # 最容易被误判成"已接线"。而 owner 的正确落点是 `_meta/collections.yaml`
        # （workbench 从那里按子库取 owner/status/entry_count），那里已写。
        # 三选项里选了"删除"：留下的唯一作用是让人以为它管事。
        "",
        "classes:",
    ]
    for dir_name, labels in sorted(KB_CLASS_BY_DIR.items()):
        lines.append(f"  {labels[0]}: 由 {dir_name} 落盘的条目所用的素材类")
    lines += [
        "",
        "# 只在同一问题命中多个类的条目、需要跨类排序时起作用",
        "ranking:",
    ]
    for rank, dir_name in enumerate(sorted(KB_CLASS_BY_DIR), start=1):
        lines.append(f"  {KB_CLASS_BY_DIR[dir_name][0]}: {rank}")
    lines += [
        "",
        "# 三个开关按白名单语义解析：只有显式 false 才收紧。",
        "# require_on_new 保持 false：本视图条目的 created_at 是派生日期，不是撰写日期。",
        "require_on_new: false",
        "allow_empty: true",
        "multi: true",
        "",
    ]
    return "\n".join(lines)


def insert_kb_class(meta: dict, collection_dir: str) -> dict:
    """把 `kb_class` 插在 `collection` 之后（枚举见 `<宿主根>/_meta/kb-classes.yaml`）。

    为什么要由生成器写这个字段：宿主侧加载器按 `kb_class` 做跨系统路由，缺失只汇总成
    一条 W040、归属就丢了。l8 批次已给存量 509 条逐条回填过；生成器不写的话，
    下一次重新生成会把这批回填整体抹掉。值必须与 `_meta/kb-classes.yaml` 的枚举一致，
    否则加载器判 E046（加类要改那个文件，不许在条目里自创）。

    不属四类的目录（`9_未归类`）**显式写空数组**：加载器区分「写了 `[]`」（判断过、
    不属四类）与「字段缺失」（还没判断过、算待办），两者含义不同。
    """
    value = KB_CLASS_BY_DIR.get(collection_dir, [])
    out: dict = {}
    for key, item in meta.items():
        out[key] = item
        if key == "collection":
            out["kb_class"] = value
    if "kb_class" not in out:
        out["kb_class"] = value
    return out


def write_text_plain(path: str, text: str) -> None:
    """明文落盘 —— **所有 `.md` 都必须走这里**，不要直接 `open(path, "w")`。

    做法：先写到非 `.md` 的临时名，再 `os.replace` 改名。实测（`kb/l8/diagnosis.md`
    的 E5）：直接写 `.md` → node 侧读到 4191 字节信封、frontmatter 正则 false；
    写 `.md.tmp` 再改名 → node 侧读到 95 字节明文、正则 true。
    同一份内容、同一台机器，差别只在「写的时候路径后缀是不是 .md」。

    非 `.md` 后缀（`.yaml` / `.json` / `.txt`）不受影响，本函数对它们同样安全，
    所以这里统一走一条通道，省得以后漏改某个写盘点。
    """
    tmp = path + ".tmp"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(tmp, "w", encoding="utf-8") as handle:
        handle.write(text)
    os.replace(tmp, path)


def resolve_node() -> tuple[list[str], dict]:
    """找一个 node 运行时（返回 argv 前缀 + 追加的环境变量）。

    本机 PATH 里没有 node，所以按「普通 node → 别的 App 自带 node → DSH 的 Electron 运行时」顺序找。
    用 DSH 那条时要加 `ELECTRON_RUN_AS_NODE=1`，否则它会去开 GUI。
    """
    # 顺序有讲究：**DSH 的 Electron 运行时优先** —— 它和加载器是同一个运行时，实测落盘稳定；
    # 实测本机偶发把普通 node 子进程 SIGKILL 掉（-9），而 DSH 运行时那几次都成功。
    if os.environ.get("KB_NODE_BIN") and os.path.exists(os.environ["KB_NODE_BIN"]):
        return [os.environ["KB_NODE_BIN"]], {}
    for app in sorted(glob.glob("/Applications/DSH Desktop*.app/Contents/MacOS/*")):
        if os.path.exists(app):
            return [app], {"ELECTRON_RUN_AS_NODE": "1"}
    for cand in ("/Applications/ChatGPT.app/Contents/Resources/cua_node/bin/node",):
        if os.path.exists(cand):
            return [cand], {}
    return [], {}


def flush_md(payload: list[dict], out_root: str) -> None:
    """把载荷里的 `.md` 交给 node 写盘，并让 node **逐个读回断言**（R2）。

    为什么非 node 不可（本机实测，见 `kb/l8/diagnosis.md`）：
      python / perl 写 `.md`（哪怕是写 `.tmp` 再 `os.replace` 改名）→ 宿主侧 Electron/Node
      读取者（加载器 dsh-kb、工作台镜像器）拿到的是 **4096 字节前缀信封**，
      frontmatter 切不出来 → 条目全判 E001 / 被镜像器当非 UTF-8 跳过；
      而 node / `/bin/cp` / bash 重定向写的 `.md`，两边读到的都是明文。
    所以 `.md` 一律走这条路；python 这边**连碰都不要碰**那些路径 —— 实测只要 python 写过，
    异步的封装层随后就会把该路径变成信封，之后再用 node 覆盖也不保险。

    node 找不到时的退路：用 write_text_plain()（写 .tmp 再改名），并打印醒目警告 ——
    那条路产出的 md 加载器可能读不到，属于降级而不是等价。
    """
    if not payload:
        return
    node, extra_env = resolve_node()
    if node:
        tmp_fd, tmp_path = tempfile.mkstemp(prefix="kb-hostlib-md-", suffix=".json")
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as handle:
            json.dump({"files": payload}, handle, ensure_ascii=False)
        env = dict(os.environ, **extra_env, KB_PAYLOAD=tmp_path, KB_ROOT=out_root)
        # 实测：本机偶发把 node 子进程 SIGKILL 掉（-9，疑似资源竞争/看门狗），所以重试 3 次再降级。
        # 降级到 python 写盘等于放弃「落盘即明文」这条不变量，必须尽量晚发生。
        proc = None
        for attempt in range(3):
            proc = subprocess.run([*node, "-e", _NODE_WRITE_AND_VERIFY], capture_output=True, text=True, env=env)
            if proc.returncode == 0:
                break
            print(f"[gen][warn] node 落盘第 {attempt + 1} 次失败（{proc.returncode}），重试")
            time.sleep(1 + attempt)
        os.unlink(tmp_path)
        if proc.returncode == 0:
            result = json.loads(proc.stdout.strip().splitlines()[-1]) if proc.stdout.strip() else {}
            print(f"[gen] 明文落盘：{result.get('files')} 个 md（node 读回断言全部通过）")
            return
        print(f"[gen][warn] node 落盘失败（{proc.returncode}）：{(proc.stderr or proc.stdout).strip()[:300]}")
        print("[gen][warn] 退回 python 写盘：宿主侧加载器可能读不出这批条目（会被封成信封）")
    else:
        print("[gen][warn] 找不到 node 运行时（KB_NODE_BIN / ChatGPT / DSH Electron 都没有）")
        print("[gen][warn] 退回 python 写盘：宿主侧加载器可能读不出这批条目（会被封成信封）")
    for item in payload:
        write_text_plain(os.path.join(out_root, item["rel"]), item["text"])


# node 侧：写盘 + 逐文件读回断言（字节数 + sha256 + frontmatter 正则）。
# 断言必须由 node 做 —— python 的读通道永远看得到明文，看不到信封，验不出这个问题。
_NODE_WRITE_AND_VERIFY = r"""
const fs = require("fs"), path = require("path"), crypto = require("crypto");
const payload = JSON.parse(fs.readFileSync(process.env.KB_PAYLOAD, "utf8"));
const root = process.env.KB_ROOT;
const FM = /^---\r?\n([\s\S]*?)\r?\n---\r?\n?([\s\S]*)$/;
const sha = (b) => crypto.createHash("sha256").update(b).digest("hex");
const bad = [];
for (const f of payload.files) {
  const target = path.join(root, f.rel);
  const want = Buffer.from(f.text, "utf8");
  fs.mkdirSync(path.dirname(target), { recursive: true });
  fs.writeFileSync(target, want);                       // node 明文写通道
  const got = fs.readFileSync(target);
  const text = got.toString("utf8");
  const needFm = f.rel.endsWith(".md") && !f.rel.startsWith("_meta/");
  if (got.length !== want.length || sha(got) !== sha(want) || (needFm && !FM.test(text))) {
    bad.push(f.rel);
  }
}
console.log(JSON.stringify({ files: payload.files.length, bad: bad }));
process.exit(bad.length ? 2 : 0);
"""


def frontmatter(meta: dict) -> str:
    lines = ["---"]
    for key, value in meta.items():
        if isinstance(value, list):
            if key == "kb_class":
                # l8 补丁：与存量 509 条的回填**同形**（单行 flow 列表）。
                # 块状（`kb_class:` + `  - x`）与 flow 语义等价，加载器两种都认；
                # 同形只是为了重新生成时不产生 509 条无意义的形态漂移。
                lines.append(f"{key}: [" + ", ".join(yaml_scalar(x) for x in value) + "]")
                continue
            lines.append(f"{key}:")
            for item in value:
                lines.append(f"  - {yaml_scalar(item)}")
        elif isinstance(value, dict):
            lines.append(f"{key}:")
            for sub_key, sub_value in value.items():
                if isinstance(sub_value, list):
                    # 嵌套列表（如 `source.record_ids`）必须写成 flow 列表。
                    # 踩过的坑：原先一律走 yaml_scalar(sub_value)，而 yaml_scalar 对
                    # list 做的是 str(value) → 落成 `record_ids: "['recXXX']"` 这样的
                    # **字符串**。加载器 W023 判的是 `Array.isArray(...)`，于是照报不误 ——
                    # 字段填了、告警没消，而且肉眼看着像填对了。与 kb_class 同形（flow）。
                    lines.append(f"  {sub_key}: [" + ", ".join(yaml_scalar(x) for x in sub_value) + "]")
                else:
                    lines.append(f"  {sub_key}: {yaml_scalar(sub_value)}")
        else:
            lines.append(f"{key}: {yaml_scalar(value)}")
    lines.append("---")
    return "\n".join(lines) + "\n"


def safe_name(rule_id: str) -> str:
    return "cg-" + rule_id.replace("/", "_")


def pick_best(rows: list[dict], field: str, rank):
    """同一 rule_id 的多个行视图里挑「信息量最大」的那个取值。"""
    values = [r.get(field) for r in rows if r.get(field) not in (None, "", [], {})]
    if not values:
        return ""
    return sorted(values, key=rank)[0]


# 权威库 `verification` 的取值与优先级（**权威值是这两个，没有「已归纳」**）。
# 顺序 = 越靠前越"强"：已支持（support_count ≥ 2）优于 待验证（support_count = 1）。
# 未登记的值落到 99，且不会静默 —— 见 main() 里对 verification 的注释。
VERIFICATION_ORDER = {"已支持": 0, "待验证": 1}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True, help="输出的宿主库根目录")
    parser.add_argument("--today", default=date.today().isoformat())
    parser.add_argument(
        "--payload-name", default="manifest.json",
        help="工作台镜像载荷的文件名（相对 <out>/_meta/）。"
             "**默认必须保持 manifest.json** —— 发布链把它硬写在三处："
             "kb/.work/gen-host-library-l4.py:366、kb/.work/gen-host-library-product.py:482 "
             "（两者都按此名回补文档）、kb/.work/kb-hostlib-serve.py:25（GET /manifest 读它）、"
             "kb/.work/publish.sh（同步不读 .md、只读这个自包含载荷）。"
             "生成 kb/view 时**必须改成别的名字**（用 workbench-mirror.json）："
             "因为加载器 readManifest() 读 `<root>/_meta/manifest.json` 当**条目基线**，"
             "读到没有 entries 的镜像载荷就返回 null，于是永远报 W035 且「条目被删掉」发现不了。",
    )
    args = parser.parse_args()

    out_root = os.path.abspath(args.out)
    if os.path.isdir(out_root):
        shutil.rmtree(out_root)
    os.makedirs(out_root)

    rules = load_jsonl(SRC_RULES)
    p0_rows = load_jsonl(SRC_P0)
    units = load_jsonl(SRC_UNITS)

    l3_reg = json.load(open(SRC_L3_REG, encoding="utf-8"))
    numbering = (l3_reg.get("numbering") or {})
    type_labels = ((l3_reg.get("scope") or {}).get("type_labels")
                   or {"wording": "措辞表达库", "external_standard": "外部标准库",
                       "internal_sample": "内部正负样本库", "product_desc": "产品描述库",
                       "unknown": "未归类"})
    dir_by_type = ((l3_reg.get("scope") or {}).get("dir_map")
                   or {"wording": "3_措辞表达库", "external_standard": "1_外部标准库",
                       "internal_sample": "2_内部正负样本库", "product_desc": "4_产品描述库",
                       "unknown": "9_未归类"})

    # 证据单元索引：unit_id → unit（正文证据回验用）
    unit_by_id = {u["unit_id"]: u for u in units}

    # P0 判定（l5）：rule_id → pattern
    p0_by_rule = {}
    for row in p0_rows:
        p0_by_rule.setdefault(row.get("rule_id", ""), row)

    # 同一 rule_id 的 3 个行视图合并成 1 条
    grouped: dict[str, list[dict]] = {}
    for row in sorted(rules, key=lambda r: (r.get("article_no") or "zzz", r.get("rule_id", ""))):
        grouped.setdefault(row["rule_id"], []).append(row)

    deriv: list[dict] = []
    manifest_docs: list[dict] = []
    per_collection = collections.Counter()
    skipped: list[dict] = []
    # F8：权威库缺 owner / half_life_days / valid_until 时的兜底留痕。
    # **必须非空可见** —— 静默退回常量正是本库反复踩的「声明了没接线」。
    governance_fallbacks: list[dict] = []

    md_payload: list[dict] = []   # l8 补丁：待落盘的 .md（交给 flush_md 走 node）

    # l8 补丁（第三轮）：related 需要全局视野（要指向别的条目 id），所以先算一遍映射。
    typed_links = build_typed_links(grouped)

    for rule_id, rows in grouped.items():
        head = next((r for r in rows if r.get("article_no")), rows[0])
        kb_type = head.get("kb_type") or "unknown"
        collection_dir = dir_by_type.get(kb_type, "9_未归类")
        form = pick_best(rows, "form", lambda v: 0 if v == "entry" else 1)
        tier = TIER_BY_FORM.get(form, TIER_FALLBACK)          # 目录名（镜像器认这个）
        tier_value = TIER_VALUE_BY_DIR.get(tier, "L1")        # frontmatter 的 tier（加载器认 L 码）
        kind = KIND_BY_FORM.get(form, KIND_FALLBACK)          # judgment / fact 与层对齐

        # l8 补丁（第三轮）：来源表 → base token / tableId；并据此判定证据级
        table_counter = tables_of(rows)
        source_bases = bases_of(table_counter)
        main_table = table_counter.most_common(1)[0][0] if table_counter else ""
        source_base = TABLE_TO_BASE.get(main_table, DEFAULT_BASE)
        source_table_id = TABLE_TO_TABLE_ID.get(main_table, DEFAULT_TABLE_ID)

        rule_code = pick_best(rows, "rule_code", lambda v: v)
        article_no = head.get("article_no") or ""
        # p_level：枚举 P0–P4（加载器 ORDER 之外的写法在这里就被挡掉，不流到视图里）。
        # 「同一规则多行取最严」（P0 最严）是刻意的口径，写在 kb/l8 报告里。
        p_level_raw = pick_best(rows, "p_level", lambda v: ORDER_P_LEVEL.index(v) if v in ORDER_P_LEVEL else 99)
        p_level = p_level_raw if p_level_raw in ORDER_P_LEVEL else "P1"
        # risk_level：① 归一（12 种写法 → 红/黄/绿/未定级），原值保留在 risk_level_raw
        risk_level_raw = pick_best(rows, "risk_level", lambda v: 0 if v not in ("unknown", "") else 1)
        risk_level = normalize_risk_level(risk_level_raw)
        # ── F8 顺手修一个**静默 bug**（2026-09-29 实测发现）────────────────────
        # 原写法：`pick_best(rows, "verification", lambda v: 0 if v == "已归纳" else 1)`
        # 但权威库 `l3/candidates/rules.jsonl` 的实际取值只有 **「待验证」(447) / 「已支持」(62)**，
        # **没有「已归纳」**。于是 rank 恒为 1 → `sorted` 稳定排序 → 退化成「取第一行的值」，
        # 而且一声不吭。这正是本库的招牌病：**枚举与现实的桥断了，代码静默降级**。
        #
        # 同类风险还有一处：视图里 62 条仍是旧标签「已归纳」、权威库已是「已支持」，
        # 说明**视图相对权威库已经陈旧**（p_level 也有 11 条不一致，权威库为准）。
        # 所以本次不是「改个字符串」，而是让视图与权威库重新对齐（重生成 + 回填）。
        verification = pick_best(rows, "verification", lambda v: VERIFICATION_ORDER.get(v, 99))
        status = pick_best(rows, "status", lambda v: v)
        new_evidence_level = pick_best(rows, "evidence_level", lambda v: 0 if v == "synthesis" else 1)
        # 证据级按加载器的定义重算（E006 + E036）：L1–L5 枚举，且声明 L2+ 必须有
        # ≥2 个**不同来源根**。旧实现写的是内部证据分级（observation/synthesis），
        # 既不在枚举内，也没法机器验证"多来源"，所以只承接语义：
        #   observation（单条修订对，单一来源）→ L1（单一来源，只能当线索）
        #   synthesis（跨记录聚合，且有 ≥2 个来源根）→ L2（多来源互证）
        #   synthesis 但只有 1 个来源根 → 降 L1（加载器对 E036 的原话就是"要么补真正
        #   独立的第二来源，要么把 evidence_level 降到 L1"）
        if new_evidence_level == "synthesis" and len(source_bases) >= 2:
            evidence_level = "L2"
            evidence_level_note = f"源库证据级 synthesis，且归属 {len(source_bases)} 个不同来源根（≥2）→ L2（多来源互证）"
        else:
            evidence_level = "L1"
            if new_evidence_level == "synthesis":
                evidence_level_note = (f"源库证据级 synthesis，但只归属 {len(source_bases)} 个来源根（需 ≥2）"
                                       "→ 按加载器 E036 的口径降为 L1（单一来源，只能当线索）")
            else:
                evidence_level_note = "源库证据级 observation（单条修订对、单一来源）→ L1"
        support_count = max((r.get("support_count") or 0) for r in rows)
        rule_text = max((r.get("rule_text") or "" for r in rows), key=len)
        reason = max((r.get("reason") or "" for r in rows), key=len)
        suggested = max((r.get("suggested_replacement") or "" for r in rows), key=len)
        forbidden = max((r.get("forbidden_expression") or "" for r in rows), key=len)
        record_total = max((r.get("scope", {}) or {}).get("records", 0) for r in rows)

        ev_units: list[dict] = []
        seen_units: set[str] = set()
        for r in rows:
            for unit in r.get("evidence_units") or []:
                uid = unit.get("unit_id")
                if uid and uid not in seen_units:
                    seen_units.add(uid)
                    ev_units.append(unit)

        # P0 匹配器（l5）只在 6 条上是真判定；其余条目的「命中表达」来自规则原文里的触发词段
        pattern = p0_by_rule.get(rule_id)
        terms: list[str] = []
        regexes: list[str] = []
        whitelist: list[str] = []
        terms_source = ""
        if pattern:
            terms = [t for t in (pattern.get("patterns") or []) if t]
            regexes = [t for t in (pattern.get("regex_patterns") or []) if t]
            whitelist = [t for t in (pattern.get("whitelist") or []) if t]
            terms_source = f"l5 P0 匹配器 {pattern.get('pattern_id')}"
        elif forbidden:
            terms = [t.strip() for t in forbidden.replace("；", ",").split(",") if t.strip()]
            terms_source = "规则行 forbidden_expression 拆分"
        if not whitelist:
            # 规则原文里的「豁免：…」段就是白名单（照抄，不改写）
            for marker in ("；豁免：", "豁免："):
                if marker in rule_text:
                    tail = rule_text.split(marker, 1)[1]
                    whitelist = [t.strip() for t in tail.replace("；", ",").split(",") if t.strip()]
                    break

        # ── 标题与摘要 ──
        code_or_id = rule_code or (article_no or rule_id)
        label = type_labels.get(kb_type, kb_type)
        hit_head = "；".join(terms[:3]) if terms else ""
        if terms:
            title = f"[{code_or_id}] {label}：命中「{terms[0]}」等 {len(terms)} 类表达"
        else:
            title = f"[{code_or_id}] {label}规则（{len(ev_units)} 条证据）"

        # ①：判定改用**归一后**的 risk_level（原来是子串匹配 raw 值，写法一变就漏判）
        judgement = "禁用/必须修改" if (risk_level == "红" or p_level in ("P0", "P1")) else "需按建议改写"
        action = (suggested or reason or "").split("；")[0][:80]
        summary = (
            f"[{code_or_id}] 判为「{judgement}」（{p_level}·{risk_level}）："
            f"命中表达 {len(terms)} 条、证据单元 {len(ev_units)} 条"
            + (f"、覆盖记录 {record_total} 条" if record_total else "")
            + (f"；处理方式是「{action}」" if action else "")
            + f"。状态 {status}、verification {verification}。"
        )
        if len(summary) > 400:
            summary = summary[:397] + "…"

        asks = [
            f"{code_or_id} 判什么、命中什么算违规",
            f"{code_or_id} 应该怎么改（合规替代写法）",
            f"{code_or_id} 的证据有几条、证据级是什么",
            f"{code_or_id} 是 P 几、风险等级是什么",
        ]
        if hit_head:
            asks.append(f"「{hit_head}」这类表述能不能用")

        not_proves = (
            "不能证明该条已过新库的正式验收（新库 l3 全部为 "
            f"{status or 'provisional'}，l4 canonical 尚未写入）；"
            "不能证明该条可替代合规/法务意见；"
            f"不能证明「{code_or_id}」以外的规则码（未命中 ≠ 合规）"
        )
        forbidden_read = (
            "不许把本条的 P 级/风险等级当成放行结论 —— 未命中本规则不等于内容合规；"
            "不许据本条的 suggested_replacement 直接外发文案，外发前仍需人工复核；"
            "不许把派生视图的字段改动当成新库改动（视图不写回）"
        )

        source_ref = f"kb/l3/candidates/rules.jsonl#{rule_id}" + (f" ∪ kb/l5/p0_patterns.jsonl#{pattern['pattern_id']}" if pattern else "")
        fingerprint = sha256_text(json.dumps(head, ensure_ascii=False, sort_keys=True))[:32]

        # ── 正文 ──
        body: list[str] = []
        body.append(f"# {title}")
        body.append("")
        body.append(f"**条款号**：{article_no or '（本行视图未发条款号）'}　|　**规则码**：{rule_code or '（未登记）'}　|　"
                    f"**rule_id**：`{rule_id}`　|　**判定**：{p_level} · {risk_level}")
        body.append("")
        body.append("## 规则原文（照抄新库，未改写）")
        body.append("")
        body.append(rule_text or "（新库该行为空）")
        body.append("")
        if terms:
            body.append(f"## 命中表达（{len(terms)} 条；来源：{terms_source}）")
            body.append("")
            for term in terms:
                body.append(f"- `{term}`")
            body.append("")
        if regexes:
            body.append("### 正则形态")
            body.append("")
            for item in regexes:
                body.append(f"- `{item}`")
            body.append("")
        if whitelist:
            body.append("### 白名单（命中这些不算违规）")
            body.append("")
            for item in whitelist:
                body.append(f"- {item}")
            body.append("")
        body.append("## 判为违规的依据")
        body.append("")
        body.append(reason or "（新库该行为空）")
        body.append("")
        body.append("## 处理方式 / 合规替代")
        body.append("")
        body.append(suggested or "（新库该行为空）")
        body.append("")
        if forbidden:
            body.append("## 禁用表达汇总")
            body.append("")
            body.append(forbidden)
            body.append("")
        body.append("## 适用范围与证据")
        body.append("")
        body.append(f"- 覆盖记录数：{record_total}")
        body.append(f"- 证据单元数：{len(ev_units)}（support_count 取新库值 {support_count}）")
        body.append(f"- 证据级（新库取值）：{evidence_level or '（空）'}")
        body.append(f"- 验证状态（新库取值）：{verification} · 规则状态：{status}")
        body.append(f"- 形态：{form}　|　库：{type_labels.get(kb_type, kb_type)}（{kb_type}）")
        if pattern:
            body.append(f"- P0 匹配器：`{pattern.get('pattern_id')}`（authority={pattern.get('authority')}，"
                        f"match_note={pattern.get('match_note')}）")
        body.append("")
        body.append("## 证据单元明细（前 30 条，unit_id 可回查 kb/l2/units.jsonl）")
        body.append("")
        for unit in ev_units[:30]:
            uid = unit.get("unit_id")
            anchor = unit.get("anchor") or ""
            text = (unit_by_id.get(uid, {}).get("text") or "").replace("\n", " ")
            if len(text) > 160:
                text = text[:157] + "…"
            body.append(f"- `{uid}`　{anchor}" + (f"　→ {text}" if text else ""))
        if len(ev_units) > 30:
            body.append(f"- …另有 {len(ev_units) - 30} 条，见新库 rules.jsonl 的 evidence_units")
        body.append("")
        body.append("---")
        body.append("")
        body.append(f"> 本条是**派生视图**（由 `kb/.work/gen-host-library.py` 从新库 l3/l5 生成），"
                    f"不是新库的权威条目。字段来源见 frontmatter 的 `provenance`。")

        meta = collections.OrderedDict()
        meta["id"] = safe_name(rule_id)
        meta["title"] = title
        meta["collection"] = collection_dir
        meta["tier"] = tier_value                                 # 补丁 A：L 码，不是目录名
        meta["topic"] = rule_code or "未登记规则码"
        meta["kind"] = kind                                       # 补丁 B：与层对齐
        meta["summary"] = summary
        # ── F8（2026-09-29）：这三个字段改为**从权威库读**，不再由生成器造 ──────
        #
        # 此前 owner / half_life_days / valid_until 都是本文件的常量
        # （LIBRARY_OWNER="刘华丽"、DERIVED_HALF_LIFE_DAYS=180 → valid_until 全是同一个日期）。
        # 后果：补在视图上的值每次重生成都会丢；而且 kb_check 的「新鲜度 1.00」是**假绿**
        # —— 509 条 valid_until 是同一个数，不是「都新鲜」。
        #
        # 现在权威库的每条规则带 owner（角色位）/ half_life_days / valid_until
        # （政策见 `kb/l3/registry/half-life-policy.json`）。**关键性质：valid_until 不随
        # 重生成归零** —— 否则条目永远不过期，等于换一种假绿。
        #
        # 缺字段时回落到政策默认值，但**必须留痕**（写进 derivation 的 fallback 列表），
        # 不许静默退回常量 —— 那正是本库反复踩的「声明了没接线」。
        rule_owner = (head.get("owner") or "").strip()
        rule_hl = head.get("half_life_days")
        rule_vu = (head.get("valid_until") or "").strip()
        rule_ef = (head.get("effective_from") or "").strip()
        if rule_owner and isinstance(rule_hl, int) and rule_hl > 0 and rule_vu and rule_ef:
            meta["owner"] = rule_owner
            meta["half_life_days"] = rule_hl
            meta["valid_until"] = rule_vu
            # 也把 effective_from 带出来：条目只有 valid_until 的话，读者看不到
            # 「这个有效期是怎么算出来的」。带上它，`effective_from + half_life_days`,
            # 就能在条目上当场核对 —— 这是「依据可核对」原则的一部分。
            meta["effective_from"] = rule_ef
        else:
            meta["owner"] = OWNER_FALLBACK
            meta["half_life_days"] = DERIVED_HALF_LIFE_DAYS
            meta["valid_until"] = (date.fromisoformat(args.today)
                                   + timedelta(days=DERIVED_HALF_LIFE_DAYS)).isoformat()
            meta["effective_from"] = args.today
            governance_fallbacks.append({
                "rule_id": rule_id,
                "missing": [k for k, v in (("owner", rule_owner),
                                           ("half_life_days", rule_hl),
                                           ("valid_until", rule_vu),
                                           ("effective_from", rule_ef)) if not v],
            })
        meta["evidence_level"] = evidence_level                   # 补丁 D：L1/L2（见循环头）
        # data_level / sensitivity_level 是**全库统一的密级判断**（内部材料、无自然人信息），
        # 属正当的库级政策常量，保留；但仍在此写明，别让它变成下一个未登记的常量。
        meta["data_level"] = DATA_LEVEL
        meta["sensitivity_level"] = SENSITIVITY
        # created_at 是「本条目（派生视图条目）的生成日」，与规则的 effective_from 不同。
        # 它随重生成更新是**对的**；有效期不由它决定 —— 由权威库的 valid_until 决定。
        meta["created_at"] = args.today
        meta["asks"] = asks
        meta["not_proves"] = not_proves
        meta["forbidden"] = forbidden_read
        # W036 回填：`evidence_group` = 这条「拿来干什么」（枚举见 _meta/evidence-groups.yaml，
        # 与 tier / evidence_level / topic 正交）。
        #
        # 口径：本视图 509 条**全部**是 kb/l3/candidates/rules.jsonl 蒸馏出的
        # **可直接判定的规则** —— 每条都有 p_level + 命中表达 + 处理方式/suggested_replacement，
        # 落在枚举的 `rule`（「可直接判定的红线规则（命中即有问题）」）。
        # 不是 evidence / clause / sample：那三类材料留在 L1 单元层，没有升成条目 ——
        # 本视图只有 3_措辞表达库 一个子库、509 条 L1-facts，没有别的形态。
        #
        # 注意 `evidence_group` 在加载器的 GOVERNANCE_FIELDS 里（它参与检索排序），
        # 所以这次回填是**治理事件**，不是排版调整：得在 _meta/ledger.ndjson 补一行 why，
        # 再刷新条目基线，否则 509 条会一起报 W034「治理字段被原地改写」。
        meta["evidence_group"] = EVIDENCE_GROUP
        # W025 处置 B（2026-09-29，人已确认）：把「同 rule_code」这条**真有依据**的关系
        # 落成带类型的 `complements`，并**删掉 related**。加载器只认「related 为空/不存在」
        # 才消 W025（把内容搬进 typed keys 不算），所以两件事必须一起做。
        # 代价：孤岛率从造出来的 0.0 变成真的约 0.94 —— 见 build_typed_links 的文档。
        # 只有组成员 ≥2 的码才挂得上边，其余条目不写该键（不写空数组：空数组的语义是
        # 「判断过、确实没有」，而这里多数条目只是**还没查到真实关系**，两者含义不同）。
        _links = typed_links.get(rule_id)
        if _links:
            meta["complements"] = _links
        # 补丁 F：source.kind 落进枚举；指纹换成 feishu-base 的坐标形态。
        # 注意 feishu-base 这一支的校验要求（kb.js verifyFingerprint）：
        #   ref 里必须出现 `/base/<token>`，且该 token 必须**在指纹里**，否则
        #   前者报 W012、后者报 E030「坐标不自洽」。所以 ref 改用飞书 Base 坐标，
        #   而不是 l3 的文件路径 —— 后者留在 provenance.anchor 里，出处一样完整。
        meta["source"] = {
            "kind": SOURCE_KIND,
            "ref": f"https://{FEISHU_HOST}/base/{source_base}?table={source_table_id}",
            "fingerprint": f"{source_base}/{source_table_id}",
            # W023 回填：记录级坐标。fingerprint 只到「表 @rev」粒度，回源时判断不了
            # 「哪条记录变了」；record_ids 把记录钉住（值从证据单元锚点里取，不是猜的）。
            # 空列表也是有用信息（表示这条的证据锚点里没有记录级坐标），但不静默 ——
            # 生成报告里单列计数。
            "record_ids": record_ids_of(rows),
            "captured_at": args.today,
        }
        # 补丁 G：provenance 是必填（E002），且需 {anchor, confidence}（E024）。
        # L2 条目的 confidence 必须是「确定」（E024 对 L2/L4 的硬要求）——
        # 这里的「确定」指的是**出处可逐条回查**（unit_id + anchor + sha256 全在，
        # l3 报告实测"缺 unit_id/anchor/sha256 的引用 0 条"），不是对规则业务有效性的判断。
        meta["provenance"] = {
            "anchor": source_ref,
            "confidence": CONFIDENCE_CERTAIN,
        }
        # 补丁 H：pii 是必填（E002），须为映射（E028）。
        # 实测本批 509 条正文不含自然人信息（来源是广告文案与专家修订，非个人信息），
        # 故 detected=false、未做脱敏；strategy 写清为什么不需要脱敏，避免"没写=没判断"。
        meta["pii"] = {
            "detected": False,
            "masked": False,
            "strategy": "未检出自然人信息：正文为广告文案/规则表述与专家修订记录，不含姓名、联系方式等个人数据；如后续来源变化需重新判定",
        }
        # 补丁 I：声明 L2+ 必须给出可机器数一遍的互证来源（E036），
        # 否则 evidence_level 只能是自我申报 —— 加载器原话是"一个恒定的字段等于没有字段"。
        if evidence_level == "L2" and len(source_bases) >= 2:
            meta["corroborated_by"] = [
                f"https://{FEISHU_HOST}/base/{b}" for b in source_bases
            ]
        meta["rule_id"] = rule_id
        meta["article_no"] = article_no
        meta["rule_code"] = rule_code
        meta["p_level"] = p_level
        meta["risk_level"] = risk_level
        # ①：原始写法与「未定级」的原因都留着（不许由 p_level 反推定级）
        if risk_level_raw and risk_level_raw != risk_level:
            meta["risk_level_raw"] = risk_level_raw
        if risk_level == "未定级":
            meta["risk_level_note"] = ("源库 kb/l3 的 risk_level 为 unknown/空 —— 未做人工定级；"
                                       "本视图不据 P 级反推，故标未定级")
        # ③：证据级为什么是这一级，写清楚（降级不能是静默的）
        meta["evidence_level_note"] = evidence_level_note
        meta["rule_status"] = status
        # 补丁 J：`verification` 这个键名归加载器所有，语义是**三重验证映射**
        # （independent_sources / predictive / non_obvious / score / verdict，见 E021）。
        # 旧实现把新库的 `verification` 字符串（"待验证"/"已归纳"）直接塞进这个键，
        # 加载器判「必须是映射」→ E021 × 509。两者是**同名不同义**的两个字段，
        # 所以这里把新库原值改名保留为 `rule_verification`，不再占用 `verification`。
        #
        # 为什么不顺手补一个 verification 映射：三重验证是**人工判断闸门**
        # （加载器原话"判断类内容必须过三重验证才能入库"）。派生视图没有依据去
        # 替人打这三项分；编一个出来等于把闸门变成自我申报。因此**留空**，
        # 让 E021 如实报出"这 56 条判断还没过三重验证"。
        meta["rule_verification"] = verification
        meta["support_count"] = support_count
        meta["form"] = form
        meta["kb_type"] = kb_type
        # 补丁 K：不再写 derived_from —— 它是 LINK_KEY，值却指向文件路径而不是条目 id，
        # 会被当引用边处理；出处信息已完整落在 source.ref 里。
        meta = insert_kb_class(meta, collection_dir)   # l8 补丁：归属字段，紧跟 collection

        rel_dir = os.path.join(out_root, collection_dir, tier)
        path = os.path.join(rel_dir, safe_name(rule_id) + ".md")
        body_text = "\n".join(body).rstrip()
        text = frontmatter(meta) + "\n" + body_text + "\n"
        # l8 补丁（第二轮）：**这里不落盘**，只入载荷 —— 写盘统一交给 flush_md() 走 node。
        # 为什么连「写 .tmp 再改名」都不够：trace 实测（kb/l8/diagnosis.md 的 E8-A）
        # 该路径确实生效（0 次直写 .md、510 次写 .md.tmp + 510 次 os.replace），
        # 产出的 .md 仍被判成信封；而同一目录里由 node 写的 510 个文件 20 秒后仍全明文（E9）。
        md_payload.append({"rel": os.path.relpath(path, out_root), "text": text})

        raw_bytes = text.encode("utf-8")
        # HTTP 取数载荷（见 kb/.work/kb-hostlib-serve.py）：工作台侧读不了这些文件
        # （被加密代理拦成密文），只能走 HTTP 拿这份**同源同内容**的载荷。
        manifest_docs.append({
            "id": meta["id"],
            "collectionId": collection_dir,
            "relPath": os.path.relpath(path, out_root),
            "absPath": path,
            "record": False,
            "title": title,
            "sha256": hashlib.sha256(raw_bytes).hexdigest(),
            # 原文（不是渲染后的切块文本）：工作台侧两条通道都吃「原文 → parseEntry → renderForChunking」，
            # 远程通道只换传输层、不换解析与切块口径，免得出现两套渲染结果。
            "text": text,
            # 顺带算出渲染结果，供对账用（工作台不依赖它）。
            "content": render_for_chunking(meta, "\n" + body_text + "\n"),
            "bytes": len(raw_bytes),
            "entryId": meta["id"],
            "tier": tier,
            "kind": meta["kind"],
            "validUntil": meta["valid_until"],
            "evidenceLevel": meta["evidence_level"],
            "owner": meta["owner"],
            "metaJson": json.dumps(meta, ensure_ascii=False),
        })

        per_collection[f"{collection_dir}/{tier}"] += 1
        deriv.append({
            "id": meta["id"],
            "path": os.path.relpath(path, out_root),
            "collection": collection_dir,
            "tier": tier,
            "kb_type": kb_type,
            "rule_id": rule_id,
            "article_no": article_no,
            "rule_code": rule_code,
            "p_level": p_level,
            "risk_level": risk_level,
            "form": form,
            "support_count": support_count,
            "evidence_units": len(ev_units),
            "fingerprint": fingerprint,
            "bytes": len(raw_bytes),
        })

    # ── l8 补丁：把这一批 .md 交给 node 落盘（并逐个读回断言）──
    flush_md(md_payload, out_root)
    md_payload.clear()   # 已落盘；后面 DERIVED.md 复用同一列表时只带它自己

    # ── _meta ──
    meta_dir = os.path.join(out_root, "_meta")
    os.makedirs(meta_dir, exist_ok=True)

    collection_registry = []
    for dir_name in sorted({d for d in dir_by_type.values()}):
        count = sum(v for k, v in per_collection.items() if k.startswith(dir_name + "/"))
        if count == 0:
            continue  # 空子库不建卡（镜像器同样跳过）
        kb_type = next((t for t, d in dir_by_type.items() if d == dir_name), "unknown")
        collection_registry.append({
            "id": dir_name,
            "name": f"{LIBRARY_NAME} · {type_labels.get(kb_type, dir_name)}",
            "display_name": f"{type_labels.get(kb_type, dir_name)}",
            # 工作台把它当「宿主目录」显示、也当身份的锚 —— HTTP 载荷里必须有。
            "externalRoot": os.path.join(out_root, dir_name),
            "description": f"宿主知识库子库（派生） · {dir_name}/",
            "called_by": ["待定（内容审查 Agent 尚未立项编号）"],
            "owner": LIBRARY_OWNER,
            "status": "derived",
            "source": "kb/l3/candidates/rules.jsonl + kb/l5/p0_patterns.jsonl（派生）",
            "entry_count": count,
            "note": f"{DOMAIN_OWNER_NOTE}。本子库是派生视图，原库为分层 json 结构，见 _meta/DERIVED.md。",
        })

    collections_yaml = []
    collections_yaml.append("# 子库登记表（派生视图，由 kb/.work/gen-host-library.py 生成，勿手工维护）")
    collections_yaml.append("# 字段口径与宿主库一致；status: derived 表示本库不是人工灌入，而是从分层新库派生。")
    collections_yaml.append("version: 1")
    collections_yaml.append(f"updated_at: '{args.today}'")
    collections_yaml.append("")
    collections_yaml.append("library:")
    collections_yaml.append(f"  name: {LIBRARY_DISPLAY}")
    collections_yaml.append(f"  display_name: {LIBRARY_DISPLAY}")
    collections_yaml.append(f"  description: {LIBRARY_NAME}的分层新库（l0-l6）派生出的宿主库视图，供工作台只读镜像检索")
    collections_yaml.append(f"  owner: {LIBRARY_OWNER}")
    collections_yaml.append("")
    collections_yaml.append("collections:")
    for item in collection_registry:
        collections_yaml.append(f"  - id: {yaml_scalar(item['id'])}")
        collections_yaml.append(f"    name: {yaml_scalar(item['name'])}")
        collections_yaml.append(f"    display_name: {yaml_scalar(item['display_name'])}")
        collections_yaml.append("    called_by:")
        for who in item["called_by"]:
            collections_yaml.append(f"      - {yaml_scalar(who)}")
        collections_yaml.append(f"    owner: {yaml_scalar(item['owner'])}")
        collections_yaml.append(f"    status: {yaml_scalar(item['status'])}")
        collections_yaml.append(f"    source: {yaml_scalar(item['source'])}")
        collections_yaml.append(f"    entry_count: {item['entry_count']}")
        collections_yaml.append("    note: |")
        for line in item["note"].splitlines() or [""]:
            collections_yaml.append(f"      {line}")
    with open(os.path.join(meta_dir, "collections.yaml"), "w", encoding="utf-8") as handle:
        handle.write("\n".join(collections_yaml) + "\n")

    # ── HTTP 取数载荷 ────────────────────────────────────────────────────
    # 为什么要有它：这台机器的加密代理（/usr/local/.trld）会让 Electron 读宿主库文件时
    # 拿到密文（实测：同一路径 stat 13084 而 python 看到 8988，读出来不是 UTF-8），
    # 于是「工作台直接读宿主库文件」这条路走不通。工作台改成向本地 HTTP 取这份载荷：
    # 内容与 md 一一对应（同一份 frontmatter + 正文渲染），只是换了个传输层。
    version_hash = sha256_text(json.dumps(
        {
            "collections": collection_registry,
            "docs": [{k: v for k, v in doc.items() if k not in ("metaJson", "text", "content")} for doc in manifest_docs],
        },
        ensure_ascii=False, sort_keys=True,
    ))
    manifest = {
        "manifestVersion": 1,
        "generatedAt": args.today,
        "generator": "kb/.work/gen-host-library.py",
        "version": version_hash,
        "root": out_root,
        "rootExists": True,
        "libraryName": LIBRARY_DISPLAY,
        "libraryDisplayName": LIBRARY_DISPLAY,
        "libraryOwner": LIBRARY_OWNER,
        "collections": collection_registry,
        "issues": [],
        "drift": [],
        "docs": manifest_docs,
        "counts": dict(per_collection),
    }
    write_text_plain(os.path.join(meta_dir, "kb-classes.yaml"), kb_classes_yaml())

    # ── 文件名（W035）──────────────────────────────────────────────────
    # `_meta/manifest.json` 在**两个消费方**那里含义不同：
    #   · 发布链（l4/product 生成器 + kb-hostlib-serve.py + publish.sh）：把它当
    #     **工作台镜像载荷**（自包含 docs[].text/sha256），同步只读它、不读 .md。
    #   · 加载器 kb.js readManifest()：把它当**条目基线**（顶层必须有 entries 对象）。
    # 同一棵树同时满足两者是不可能的：readManifest 读到没有 entries 的载荷就返回 null
    # → 永远报 W035「没有条目基线」，于是「条目被删掉」与「治理字段被原地改写」都发现不了
    # （2026-09-22 六条 L0-raw 原文存档被整体删掉、检查器一声不吭，就是被这个洞放过去的）。
    # 故按**输出目标**分开命名，默认值保持发布链要的 manifest.json，
    # 生成 kb/view 时显式传 --payload-name workbench-mirror.json。
    with open(os.path.join(meta_dir, args.payload_name), "w", encoding="utf-8") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=1)

    total = len(deriv)
    with open(os.path.join(meta_dir, "derivation.json"), "w", encoding="utf-8") as handle:
        json.dump({
            "generated_at": args.today,
            "generator": "kb/.work/gen-host-library.py",
            "sources": {
                "rules": {"path": "kb/l3/candidates/rules.jsonl", "rows": len(rules), "sha256": sha256_text(open(SRC_RULES, encoding="utf-8").read())},
                "p0": {"path": "kb/l5/p0_patterns.jsonl", "rows": len(p0_rows), "sha256": sha256_text(open(SRC_P0, encoding="utf-8").read())},
                "units": {"path": "kb/l2/units.jsonl", "rows": len(units)},
            },
            "grouping": {"by": "rule_id", "logical_rules": len(grouped), "rows_per_rule": "3"},
            # F8：half_life_days 与 owner **不再是派生缺省** —— 它们来自权威库每条规则。
            # 只保留真正属于「库级政策」的 data_level，以及兜底值（并附 fallback 明细）。
            "governance_source": {
                "half_life_days": "kb/l3/candidates/rules.jsonl → 每行 half_life_days（政策见 kb/l3/registry/half-life-policy.json）",
                "valid_until": "kb/l3/candidates/rules.jsonl → 每行 valid_until（= effective_from + half_life_days，**不随重生成归零**）",
                "owner": "kb/l3/candidates/rules.jsonl → 每行 owner（**角色位**，不写死人名）",
            },
            "derived_defaults": {"data_level": DATA_LEVEL, "sensitivity_level": SENSITIVITY},
            "fallback_defaults": {
                "owner": OWNER_FALLBACK,
                "half_life_days": DERIVED_HALF_LIFE_DAYS,
                "note": "仅在权威库缺对应字段时使用；每次兜底都会记进 governance_fallbacks",
            },
            "governance_fallbacks": governance_fallbacks,
            "counts": dict(per_collection),
            "total_entries": total,
            "entries": deriv,
            "skipped": skipped,
        }, handle, ensure_ascii=False, indent=1)

    derived_text = f"""# 派生视图说明（{LIBRARY_NAME}）

> 本目录由 `kb/.work/gen-host-library.py` 生成，**不是**人工灌入的权威知识库。
> 权威库在本工作区的分层库里：`kb/l0`（素材）→ `kb/l1/l2`（单元）→ `kb/l3`（规则）
> → `kb/l4`（条款号）→ `kb/l5`（P0 匹配）→ `kb/l6`（索引）。

## 为什么要有它

工作台（4317）的知识库是宿主库的**单向只读镜像**，判据是
`<根>/<子库>/L{{0-raw,1-facts,2-concepts,3-graph,4-contracts}}/*.md` + `_meta/collections.yaml`。
分层新库是 json/jsonl，镜像器扫不到任何条目 —— 这份视图就是给镜像器吃的那层壳。

## 生成规则（可复核）

| 事项 | 口径 |
|---|---|
| 条目粒度 | 按 `rule_id` 聚成 1 条（新库同一 rule 有 3 个行视图：entry / revision_pair / P0 行），**不是**按 1527 行 |
| 子库划分 | 按 `kb_type` 落目录：1_外部标准库 / 2_内部正负样本库 / 3_措辞表达库 / 4_产品描述库 / 9_未归类 |
| 层目录 | `form=entry → L1-facts`、`form=revision_pair → L1-facts`、`form=boundary → L1-facts`（**F5**：`entry` 原落 `L2-concepts`，因 `E021 × 56` 降层） |
| 正文 | 规则原文 / 命中表达 / 依据 / 处理方式照抄新库字段，**不做摘要式改写** |
| 治理字段来源（**F8**） | `half_life_days` / `valid_until` / `owner` **来自权威库每条规则**（`kb/l3/candidates/rules.jsonl`，政策见 `kb/l3/registry/half-life-policy.json`）—— **不是派生缺省**。`valid_until` 不随重生成归零，所以条目会**真的到期** |
| 缺省字段 | 仅 `data_level={DATA_LEVEL}`、`sensitivity_level={SENSITIVITY}` 是库级密级政策常量（内部材料、无自然人信息）。权威库缺 `owner`/`half_life_days`/`valid_until` 时，兜底为 `{OWNER_FALLBACK}` / `{DERIVED_HALF_LIFE_DAYS}`，并**逐条记进 `derivation.json → governance_fallbacks`**（不静默） |
| 库级接受人 | `{LIBRARY_OWNER}` —— 这是 **collections.yaml / kb-classes.yaml / manifest 的库（子库）owner**，与逐条 `meta.owner` 是两件事 |
| 不改的东西 | 生成过程只读新库；工作台侧是只读镜像（写入会被 `KbReadOnlyError` 拦） |

## 边界（用这条视图时必须知道）

1. 新库 l3 全部是 `provisional`，l4 canonical 仍为空 —— **派生视图不改变这个状态**，它一样没过正式验收。
2. 视图只覆盖「已归纳成规则」的那部分；l2 的 9261 条原始单元、l0 的 1256 份素材**没有**逐条搬进来。
3. 视图与分层库可能不同步：改了新库要重跑生成器 + 重装，见 `kb/.work/gen-host-library.py --out`。
4. `not_proves` / `forbidden` 每一条都写了 —— 别再外推（未命中 ≠ 合规）。
"""
    md_payload.append({"rel": "_meta/DERIVED.md", "text": derived_text})
    flush_md(md_payload, out_root)   # l8 补丁：DERIVED.md 同为 .md，同一趟走 node

    print(f"[gen] 源：rules {len(rules)} 行 → {len(grouped)} 条逻辑规则；p0 {len(p0_rows)} 条；units {len(units)} 条")
    print(f"[gen] 产出：{total} 条条目，落 {len(collection_registry)} 个子库")
    for key, value in sorted(per_collection.items()):
        print(f"[gen]   {key}: {value}")
    print(f"[gen] 输出根：{out_root}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
