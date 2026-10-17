#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ⚠️⚠️ 本文件是 **2026-10-17 第一轮的补丁脚本，已不是最终状态的复现件** ⚠️⚠️
#   它在落盘之后又被改过四轮（Owner 后令「卡片格式不要动」等），那几轮是就地 python 改的。
#   **最终状态的权威记录 = `git diff` ＋ `交付-审查报告改审计报告模式-20261017.md`
#             ＋ `kb/l7/registry/report-output-contract.yaml::fix_20261017_audit_report_format`。**
#   保留它只为两件事：① 五条裁定的锚点长什么样；② 每处替换都必须恰好命中一次的那种纪律。
"""守衡侧审查报告改成「审计报告」模式 —— 一次性补丁（2026-10-17）

Owner 五条裁定（2026-10-17，逐条对应本文件的五个改动块）：
  ① 报告门槛回到 PRD 的 **≥3**（推翻 2026-10-14 那条「<3 也出」的本地要求）
  ② 分论点 **先 P 级、再维度** 两级分组（白板 `P0 → G1/G2/G3 → rule out`）
  ③ 模型侧条目**统一归 P1**（PRD §6.3 第二层＝大模型语义层），行内另标 BLOCK/REVIEW
  ④ 报告六格里的「问题描述」单独成格 —— 模型侧 prompt 新增 `description`
  ⑤ 第三步「@对应角色」：**逐条给承办** ＋ 末尾整单一行（卡片那行照旧保留）

用法：
    python3 apply-report-format-20261017.py --dry-run   # 只校验锚点，不写盘
    python3 apply-report-format-20261017.py             # 落盘（自动 .bak-20261017-reportfmt）

⚠️ 锚点必须**恰好出现一次**（重复的断言点写死次数）—— 对不上就整体退出，不留半成品。
"""

import os
import shutil
import sys

ROOT = "/Users/lute/Project/audit_multi_content/tools"
SUFFIX = ".bak-20261017-reportfmt"
DRY = "--dry-run" in sys.argv


def patch(rel, pairs):
    p = os.path.join(ROOT, rel)
    if not os.path.exists(p):
        raise SystemExit(f"❌ 找不到 {p}")
    src = original = open(p, encoding="utf-8").read()
    for i, (old, new, want) in enumerate(pairs, 1):
        got = src.count(old)
        if got != want:
            raise SystemExit(
                f"❌ {rel} 第 {i} 处锚点：期望出现 {want} 次，实际 {got} 次\n"
                f"   锚点开头：{old[:120]!r}")
        src = src.replace(old, new)
    if src == original:
        raise SystemExit(f"❌ {rel}：没有任何改动")
    print(f"  ✅ {rel}：{len(pairs)} 处锚点全部命中 ｜ {len(original)} → {len(src)} 字节")
    if DRY:
        return
    if not os.path.exists(p + SUFFIX):
        shutil.copy2(p, p + SUFFIX)
        print(f"     备份 → {os.path.basename(p)}{SUFFIX}")
    open(p, "w", encoding="utf-8").write(src)


# ══════════════════════════════════════════════════════════════════════════
# ① agent.mjs —— 报告门槛回到 PRD 的 ≥3
# ══════════════════════════════════════════════════════════════════════════
AGENT_OLD_GATE = """      if (rendered0 && itemsWithAdvice.length > 0) {"""
AGENT_NEW_GATE = """      // ★★ 2026-10-17（Owner 裁定，**推翻 2026-10-14 那条本地要求**）：
      //   「逻辑不变，按照 PRD 问题数量 ≥3 个时才输出审查报告」。
      //   两道条件**同时**要满足，缺一条都会造出坏链接：
      //     · `itemsWithAdvice.length > 0` —— 没有真条目 ⇒ 报告里只有结论行
      //       （「一个点开没内容的链接比空格更坏」，2026-10-15/16 两次定过）；
      //     · `rendered0.total >= REPORT_LINK_MIN_ISSUES` —— 回到 PRD §5.3.4 的门槛。
      //       <3 时**卡片本来就逐条平铺**（`renderMerged` 的 `summarized` 分支），
      //       明细一个字都不在报告里丢 —— 这也是 <3 不需要报告的**理由**，不是妥协。
      //   ⚠️ 与库侧 `feishu_publish.py::REPORT_LINK_MIN_ISSUES`、`dual_track` 的同名常数
      //      **同一个数、同一个口径**（PRD §5.3.4 / §8.3 / §17 三处一致）。
      //   ⚠️ 2026-10-14 的「<3 也出」当时是**为那批 80 行落表**要的；那一批已经跑完，
      //      如将来再需要，走 `--force-report` 之类的显式开关，**不许把门槛再改回去**。
      if (rendered0 && itemsWithAdvice.length > 0
          && rendered0.total >= REPORT_LINK_MIN_ISSUES) {"""

AGENT_OLD_WHY = """        const _why = !rendered0 ? 'renderMerged 返回 null（没有可并的条目）'
          : `卡内总数 ${rendered0.total} ⇒ 本应已建（走到这里说明上面那一支没进，属异常）`;"""
AGENT_NEW_WHY = """        const _why = !rendered0 ? 'renderMerged 返回 null（没有可并的条目）'
          : (itemsWithAdvice.length === 0
            ? '没有真条目可并（库侧报了几条但明细抠不出来）⇒ 建出来会是空文档'
            : `卡内总数 ${rendered0.total} < ${REPORT_LINK_MIN_ISSUES} ⇒ 按 PRD §5.3.4 本就不出报告`
              + '（卡片已逐条平铺，明细不缺）');"""

# ══════════════════════════════════════════════════════════════════════════
# ② model_side.mjs —— 问题描述单列一格
# ══════════════════════════════════════════════════════════════════════════
MS_OLD_RULE = """  '5. 你出的每一条都**没有库内依据** —— 所以它最高只能到 REVIEW，不要给 BLOCK。',"""
MS_NEW_RULE = """  // ★★ 2026-10-17（Owner 裁定：报告的「问题描述」与「原因」必须分两格）———————
  //   PRD §8.3 的完整清单每条要 `维度 / 位置 / **问题描述** / **原因** / 依据文档链接 / 修改建议`，
  //   而我们此前只出一格 `reason` —— 现象、判据、后果全挤在那一句里，
  //   报告只能拿同一句同时顶替两格（实测 `merged-2026-10-16T02_05_22` 三条全这样）。
  //   ⇒ 现在分开：`description` 说**是什么现象**，`reason` 说**为什么算问题**。
  //   ⚠️ 两格都必填 —— 空 `description` 会让报告那一格只能印「未给」，那不是要求。
  '4c. ★ **`description`（问题描述）与 `reason`（原因）必须分开写**：',
  '    · `description`：**哪里 + 什么现象** —— 让人一眼知道你说的是哪一处（**不写判据**）；',
  '    · `reason`：**为什么这是问题** —— 判据 / 危害 / 美国消费者会怎么误解；**不重复现象**。',
  '    ✗ 反例（两格写成一格）：reason 写「正文只有中文账号名、图上是 momcozY，两者对不上，',
  '      美国消费者读不懂也无法识别广告主」⇒ 现象与判据黏在一起，报告两格只能印同一句。',
  '5. 你出的每一条都**没有库内依据** —— 所以它最高只能到 REVIEW，不要给 BLOCK。',"""

MS_OLD_SHAPE = """  '{"location":"帧 3","category":"消费者安全","severity":"REVIEW","reason":"一句话说清问题",',
  ' "excerpt":"逐字引用的原文","suggestion":"具体怎么改（改哪个词/换成什么/删哪句/补什么）",',
  ' "source":"S11 或 null","source_url":"https://… 或 null","source_name":"来源名 或 null"}',"""
MS_NEW_SHAPE = """  '{"location":"帧 3","category":"消费者安全","severity":"REVIEW",',
  ' "description":"问题描述：哪里 + 什么现象（一句话，不写判据）",',
  ' "reason":"原因：为什么这是问题（判据/危害）",',
  ' "excerpt":"逐字引用的原文","suggestion":"具体怎么改（改哪个词/换成什么/删哪句/补什么）",',
  ' "source":"S11 或 null","source_url":"https://… 或 null","source_name":"来源名 或 null"}',"""

MS_OLD_PARSE = """      reason,
      excerpt: String(raw?.excerpt ?? '').trim() || null,"""
MS_NEW_PARSE = """      reason,
      // ★★ 2026-10-17：**问题描述单列一格**（与 `reason` 分开，见上面提示词 4c）。
      //   缺了**不丢整条**（它是报告的一格，不是判定依据）⇒ 置 null，
      //   由渲染层如实说「未给问题描述」。⚠️ **不把 `reason` 搬过来顶上** ——
      //   那等于自己又把两格合成一格，而且是在源头上造假。
      description: String(raw?.description ?? '').trim() || null,
      excerpt: String(raw?.excerpt ?? '').trim() || null,"""

# ══════════════════════════════════════════════════════════════════════════
# ③ dual_track.mjs
# ══════════════════════════════════════════════════════════════════════════
DT_OLD_ENGINE_ITEM = """      suggestionLine: String(r.suggestion || '').trim() || null,
      kb: { article_no: art, anchor: anc, entry_url: link || null,
            source_sha256: ev.source_sha256 || null, library: ev.library || null, basisLine,
            suggestionLine: String(r.suggestion || '').trim() || null },"""
DT_NEW_ENGINE_ITEM = """      suggestionLine: String(r.suggestion || '').trim() || null,
      // ★★ 2026-10-17（Owner：报告按「审计报告」模式重做）：**优先级与维度必须搬过来**。
      //   引擎 `risk_items` 里本来就有（`with_kb_evidence.py::_to_risk_item` 投影了
      //   `priority_tier` / `priority_tier_basis` / `risk_category` / `risk_category_basis`），
      //   而这一层**一格都没带** ⇒ 渲染层拿不到 P 级与维度，
      //   报告只能不分级、不分组（这一步做出来之前它连「先按 P 级」都不可能）。
      //   ⚠️ 这是第三次同一个形状（2026-10-08 `basisLine`、2026-10-09 `suggestionLine`、
      //      今天这两对）—— **搬运漏一格 = 报告少一格**。
      priorityTier: String(r.priority_tier || '').trim().toUpperCase() || null,
      priorityTierBasis: String(r.priority_tier_basis || '').trim() || null,
      riskCategory: String(r.risk_category || '').trim() || null,
      riskCategoryBasis: String(r.risk_category_basis || '').trim() || null,
      kb: { article_no: art, anchor: anc, entry_url: link || null,
            source_sha256: ev.source_sha256 || null, library: ev.library || null, basisLine,
            suggestionLine: String(r.suggestion || '').trim() || null,
            // ⚠️ 必须**同时**挂进 `kb` —— `mergeFindings` 是**白名单式重建**条目
            //   （`pickKb` / `pickModel`），顶层字段到不了渲染层，只有进 `kb` 才活得下来。
            priorityTier: String(r.priority_tier || '').trim().toUpperCase() || null,
            priorityTierBasis: String(r.priority_tier_basis || '').trim() || null,
            riskCategory: String(r.risk_category || '').trim() || null,
            riskCategoryBasis: String(r.risk_category_basis || '').trim() || null },"""

DT_OLD_PICKKB = """  // ★ 2026-10-09：库侧已经产好的「建议」——不搬过来，渲染层只能印硬编码那句
  suggestionLine: f?.suggestionLine ?? null,
});"""
DT_NEW_PICKKB = """  // ★ 2026-10-09：库侧已经产好的「建议」——不搬过来，渲染层只能印硬编码那句
  suggestionLine: f?.suggestionLine ?? null,
  // ★★ 2026-10-17：**优先级与维度**（报告要按 P 级分组、每条要标维度）。
  //   白名单式搬运的代价见 `pickModel` 那段注释：新字段不加进来就**静默消失**。
  priorityTier: f?.priorityTier ?? null,
  priorityTierBasis: f?.priorityTierBasis ?? null,
  riskCategory: f?.riskCategory ?? null,
  riskCategoryBasis: f?.riskCategoryBasis ?? null,
});"""

DT_OLD_PICKMODEL = """const pickModel = (f) => ({
  reason: f?.reason ?? null, excerpt: f?.excerpt ?? null, severity: normSev(f?.severity) || null,"""
DT_NEW_PICKMODEL = """const pickModel = (f) => ({
  reason: f?.reason ?? null, excerpt: f?.excerpt ?? null, severity: normSev(f?.severity) || null,
  // ★★ 2026-10-17：**问题描述**（报告六格里的那一格，见 `model_side.mjs` 提示词 4c）
  description: f?.description ?? null,"""

DT_OLD_ITEMS = """  const items = list.map((f, i) => renderMergedItem(f, i, { must }));"""
DT_NEW_ITEMS = """  // ★★ 2026-10-17（Owner：第三步「根据问题 @对应的角色来执行」）：**逐条给承办**。
  //   原先 `routing` 只算**整单一次**（下面那行收尾），条目上不写谁办
  //   ⇒ 一条本地化问题与一条医学问题，收件人一样，读者还得自己拆。
  //   现在每条按**它自己的方向词**算（同一张路由表、同一条 fallback），
  //   整单那行**照旧保留**（PRD §5.3.2 的收尾句式不许丢）。
  const itemOwners = ownersByItem(list);
  const items = list.map((f, i) => renderMergedItem(f, i, { must, owner: itemOwners[i].text }));"""

DT_OLD_ACTION = """  const routing = reviewOwnersFor(list, ROUTING_POLICY);
  const action = must
    ? '请修改后重新提交。'
    : renderReviewAction(routing.owners, ROLE_HANDLES,
        { unmatched: routing.unmatched, total: list.length,
          // ★ 没有任何条目可路由（空清单）时落这个 —— 与「读不到路由表」同一答案。
          //   库侧覆盖缺口那一支恒为空清单，靠的就是这条（`routing.py` 同口径）。
          fallback: ROUTING_POLICY?.fallback });"""
DT_NEW_ACTION = """  const routing = reviewOwnersFor(list, ROUTING_POLICY);
  // ★★ 2026-10-17：收尾那一行**收口到 `orderActionLine()`** —— 报告（`merged_report.mjs`）
  //   也要印同一行，两处各写一遍必然漂移（本文件已因「两个产者」栽过多次）。
  const action = orderActionLine(list, { must, routing });"""

# 新增的「分级 / 维度 / 承办」判据块 —— 插在 renderMergedItem 之前
DT_ANCHOR_ITEM = """export function renderMergedItem(f, i, { must = false } = {}) {"""
DT_NEW_HELPERS = r"""// ══════════════════════════════════════════════════════════════════════════
// 分级（P0–P3）· 维度 · 承办 —— 报告「分论点」与「执行」两步的判据
// ══════════════════════════════════════════════════════════════════════════
//
// ★★ 2026-10-17（Owner 拿着白板来定格式）。白板画的是：
//
//      总（state + 1句话）  →  分：`P0 → G1/G2/G3 → rule 1 out` ｜ `P1 → rule 2 out`
//      →  执行 @角色
//      圈起来的判定规则：`P0 ≥ 1 → Block` ｜ `P1 ≥ 1 且无 P0 → review` ｜ `Pn ……`
//
// 那一圈**就是 PRD §6.3 的四层执行规则**，而 `P0…P3` 就是那四层：
//   P0 红线（关键词/正则，毫秒级）→ 命中即 BLOCK
//   P1 安全与准确性（**大模型语义理解**）→ 至少 REVIEW
//   P2 通识常识（大模型多模态）→ 同上
//   P3 措辞建议 → **不影响结论**
//
// ── 边界（写清楚，别让它比输入大）────────────────────────────────────────
//   · **库侧**的 P 级只认引擎给的 `priority_tier`（`core/tiering.py` 的单一口径）。
//     拿不到就如实说「未分级」，**不从 severity 反推一个**（BLOCK≠P0：模型侧也能报 BLOCK，
//     而它是 P1）。反推会把「登记过的分级」换成「猜的分级」，比空着更坏。
//   · **模型侧**统一归 P1 —— 这是 PRD §6.3 给「大模型语义层」定的位置，不是我们迁就数据。
//     它自己的 BLOCK/REVIEW 照旧印在 `**优先级**` 那一行里（轻重没丢，只是不冒充 P0）。
//   · **维度**只认 PRD §5.3 的四维度（合规 / 消费者安全 / 产品描述 / 措辞表达）。
//     映射表在 `kb/l7/registry/risk-category-policy.json`，**政策件自己写着
//     「不编，留空待裁」** ⇒ 这里对不上的就标「未映射」，**不硬塞进某一维**。
//     实测影响面：模型侧 7 个类目里「隐私 / AI 披露 / 本地化」三个**现在没有维度**。
//   · **承办**只搬 `routing.mjs` 的算出来的角色位；**句柄没配就写「（未配置）」**，
//     **不编人名**（`kb/l7/registry/l7.json` 的 `approvers.configured` 现在还是 false）。

/** PRD §6.3 的四层（**顺序有意义**：报告按这个次序分组）。 */
export const PRIORITY_LEVELS = Object.freeze(['P0', 'P1', 'P2', 'P3']);

/** 每一层是什么 —— 措辞取自 PRD §6.3 原文，**不是**我们自己起的名字。 */
export const PRIORITY_LABEL = Object.freeze({
  P0: '红线（关键词/正则，**命中即 BLOCK**）',
  P1: '安全与准确性（**大模型语义理解**层）',
  P2: '通识常识（大模型多模态层）',
  P3: '措辞建议（**只出建议、不改结论**）',
});

/** PRD §5.3 的四维度（`risk-category-policy.json` 的 `dimensions` 同一份）。 */
export const PRD_DIMENSIONS = Object.freeze(['合规', '消费者安全', '产品描述', '措辞表达']);

const _isKbSide = (f) => f?.source === 'kb' || f?.source === 'both' || f?.source === 'both-conflict';
const _kbOf = (f) => ((f && typeof f.kb === 'object' && f.kb) ? f.kb : {});

/**
 * 这一条的**优先级**。
 * @returns {{level:string|null, basis:string|null, text:string}}
 */
export function priorityOf(f) {
  const x = (f && typeof f === 'object') ? f : {};
  const kb = _kbOf(x);
  if (_isKbSide(x)) {
    const raw = String(kb.priorityTier || x.priorityTier || '').trim().toUpperCase();
    if (PRIORITY_LEVELS.includes(raw)) {
      return { level: raw, basis: 'kb_tier',
               text: `${raw} — ${PRIORITY_LABEL[raw]}`
                 + (kb.priorityTierBasis ? `（引擎口径：${kb.priorityTierBasis}）` : '') };
    }
    return { level: null, basis: null,
             text: '（**未分级** —— 库侧这一条来路没带 `priority_tier`，**不代定**）' };
  }
  // 模型侧：PRD §6.3 第二层就是「大模型语义理解」，它天然落 P1。
  const sev = String(x.asked_severity || x.severity || 'REVIEW').toUpperCase();
  return { level: 'P1', basis: 'model_side_default',
           text: `P1 — ${PRIORITY_LABEL.P1}`
             + `（模型侧按 PRD §6.3 第二层口径归 P1；**本条自评 ${sev}**）` };
}

/**
 * 这一条的**维度**（PRD §5.3 四维度之一）。
 * @returns {{dimension:string|null, text:string}}
 */
export function dimensionOf(f) {
  const x = (f && typeof f === 'object') ? f : {};
  const kb = _kbOf(x);
  // 库侧优先用引擎盖过章的 `risk_category`；模型侧类目本身就是维度口径（闭集 7 个）。
  const cand = String((_isKbSide(x) ? (kb.riskCategory || x.riskCategory || '') : '')
    || x.category || '').trim();
  if (PRD_DIMENSIONS.includes(cand)) return { dimension: cand, text: cand };
  return { dimension: null,
           text: `（**未映射** —— \`${cand || '未给类别'}\` 不在 PRD §5.3 的四维度`
             + '（合规/消费者安全/产品描述/措辞表达）里；按 `risk-category-policy.json` '
             + '的「不编，留空待裁」**不代填**）' };
}

/**
 * 这一条的**问题描述**（PRD §8.3 六格里的那一格）。
 *
 * 三条口径：
 *   · 有 `description`（模型侧新字段 / 库侧将来也能给）⇒ 直接用它；
 *   · 没有但有逐字命中（`excerpt`）⇒ **如实写成「逐字命中「…」」并标明这是替代**，
 *     因为它确实是「哪里有问题」的原文，但它**不是**模型写的描述；
 *   · 都没有 ⇒ 如实说「未给」，**不把 `reason` 搬过来顶**（那等于两格又合成一格）。
 */
export function descriptionOf(f) {
  const x = (f && typeof f === 'object') ? f : {};
  const d = String(x.description || x.model?.description || '').trim();
  if (d) return { description: d, basis: 'given', text: d };
  const exc = String(x.excerpt || x.model?.excerpt || '').trim();
  if (exc) {
    return { description: exc, basis: 'excerpt',
             text: `逐字命中「${exc}」（**本条未单独给问题描述，此处取的是命中原文**）` };
  }
  return { description: null, basis: null,
           text: '（**未给问题描述** —— 本条只有原因，**不代写**）' };
}

/** 分组表头：P 级。 */
export function priorityHeading(level) {
  if (level === 'UNRANKED') return '未分级（库侧来路没带 `priority_tier`）';
  return `${level} — ${PRIORITY_LABEL[level] ?? ''}`;
}

/** 分组表头：维度。 */
export function dimensionHeading(dim) {
  if (dim === 'UNMAPPED') return '未映射维度（PRD §5.3 四维度未覆盖，按政策件留空待裁）';
  return dim;
}

/**
 * 把条目排成 **P 级 → 维度** 两级分组（报告的「分论点」就是按它印的）。
 *
 * ⚠️ 空等级**不出现**（没命中就别占一行标题）—— 但**分组内的次序是固定的**
 *    （P0→P1→P2→P3；维度按 PRD §5.3 的四维度次序，未映射排最后），
 *    所以同一批条目两次渲染必然同序。
 *
 * @param {Array} items
 * @returns {Array<{level:string, groups:Array<{dimension:string, items:Array}>, count:number}>}
 */
export function groupByPriorityAndDimension(items) {
  const list = Array.isArray(items) ? items : [];
  const byP = new Map();
  for (const f of list) {
    const p = priorityOf(f).level || 'UNRANKED';
    const d = dimensionOf(f).dimension || 'UNMAPPED';
    if (!byP.has(p)) byP.set(p, new Map());
    const m = byP.get(p);
    if (!m.has(d)) m.set(d, []);
    m.get(d).push(f);
  }
  const pOrder = [...PRIORITY_LEVELS, 'UNRANKED'];
  const dOrder = [...PRD_DIMENSIONS, 'UNMAPPED'];
  const out = [];
  for (const p of pOrder) {
    const m = byP.get(p);
    if (!m) continue;
    const groups = dOrder.filter((d) => m.has(d))
      .map((d) => ({ dimension: d, items: m.get(d) }));
    out.push({ level: p, groups, count: groups.reduce((s, g) => s + g.items.length, 0) });
  }
  return out;
}

/**
 * 每条问题该转谁（**逐条**算，不是整单一次）。
 *
 * 与整单那一行的差异：整单是「把全部方向词并起来取并集」，逐条是「这一条自己的方向」。
 * 两种都要 —— 逐条回答「这一处找谁改」，整单回答「这一单转给谁复核」。
 * 方向词一个都没命中 ⇒ 落 `routing-policy.json` 的 `fallback`，并**如实标出来**
 * （「落默认」与「按方向命中」是两件事，读者有权知道）。
 */
export function ownersByItem(items) {
  const list = Array.isArray(items) ? items : [];
  return list.map((f) => {
    const r = reviewOwnersFor([f], ROUTING_POLICY);
    const named = r.owners.map((o) => (ROLE_HANDLES.get(o)
      ? `@${ROLE_HANDLES.get(o)}` : `${o}（未配置）`));
    const text = named.length
      ? named.join('、') + (r.unmatched ? '（**方向词未命中，落 PRD §5.3 默认**）' : '')
      : '（**未给出承办** —— 路由表与默认都没命中，转人工）';
    return { owners: r.owners, unmatched: r.unmatched, text };
  });
}

/**
 * 整单那一行收尾（PRD §5.3.2 / §5.3.3 的「建议转 @… 复核。」／「请修改后重新提交。」）。
 *
 * ★ 2026-10-17：从 `renderMerged` 里抽出来 —— 报告（`merged_report.mjs`）也要印同一行，
 *   两处各写一遍必然漂移（本文件已因「同一个东西两个产出者」栽过多次）。
 */
export function orderActionLine(items, { must = false, routing = null } = {}) {
  const list = Array.isArray(items) ? items : [];
  const r = routing || reviewOwnersFor(list, ROUTING_POLICY);
  if (must) return '请修改后重新提交。';
  return renderReviewAction(r.owners, ROLE_HANDLES,
    { unmatched: r.unmatched, total: list.length,
      // ★ 没有任何条目可路由（空清单）时落这个 —— 与「读不到路由表」同一答案。
      //   库侧覆盖缺口那一支恒为空清单，靠的就是这条（`routing.py` 同口径）。
      fallback: ROUTING_POLICY?.fallback });
}

export function renderMergedItem(f, i, { must = false, owner = null } = {}) {"""

DT_OLD_RETURN = """  return `${i + 1}.【${f.category}${f.sub ? '-' + f.sub : ''}】${f.location}  —— ${origin}\\n`
    + `   **原因**：${f.kb?.reasonLine ?? f.reason ?? '（未给理由）'}\\n`
    + `   **依据**：${basis}\\n`
    + (must ? `   **建议**：${sugLine}\\n` : '')
    // ── ★★ 2026-10-14（Owner 裁定）：**`**判定**` 那一行整行删除** ────────────────────
    //   口径：PRD §5.3 的逐条模板只有 `原因` / `依据` /（BLOCK 才有）`建议`，
    //   三态只出现在**结论行** `【审查结论：X】` 一处 —— 逐条再挂一个「判定」，
    //   同一张卡上就有两个「判定」，业务侧分不清哪个是结论。
    //   ⚠️ 2026-10-09 那次「把它降格成补充行、加粗保留」的裁定**已被本次取代**
    //      （同一 Owner，后令优先）；上面第 1665 行那段注释留作历史，**勿据以恢复该行**。
    //   `verdict` 这个局部量仍算（上面 headline 那段），但**不再有任何输出点**。
    + (!must ? `   **建议**：${sugLine}\\n` : '');"""
DT_NEW_RETURN = """  // ── ★★ 2026-10-17（Owner 裁定：按「审计报告」模式重做）─────────────────────────
  //   一条 = PRD §8.3 的六格：**维度 / 位置 / 问题描述 / 原因 / 依据文档链接 / 修改建议**，
  //   另加两格报告自己需要的：**优先级**（P0–P3，白板 `P0 → G1/G2/G3 → rule` 那一层）
  //   与 **承办**（第三步「@对应的角色」落到**这一条**）。
  //   ⚠️ **第一行一个字没动**：`N.【维度-子类】位置  —— 来源标记` 是 PRD §5.3 的逐条契约
  //      （`countRenderedItems`、`verify_cards` 的 J11、`l7_integrity.py` 都在核这个形状），
  //      所以六格是**加在它下面**，不是替换它。
  //   ⚠️ 加粗不许撤：`verify_cards` / selftest 多处钉着 `**原因**` `**依据**` `**建议**`。
  const pri = priorityOf(f);
  const dim = dimensionOf(f);
  const desc = descriptionOf(f);
  return `${i + 1}.【${f.category}${f.sub ? '-' + f.sub : ''}】${f.location}  —— ${origin}\\n`
    + `   **优先级**：${pri.text}\\n`
    + `   **维度**：${dim.text}\\n`
    + `   **位置**：${f.location}\\n`
    + `   **问题描述**：${desc.text}\\n`
    + `   **原因**：${f.kb?.reasonLine ?? f.reason ?? '（未给理由）'}\\n`
    + `   **依据**：${basis}\\n`
    + `   **建议**：${sugLine}\\n`
    + (owner ? `   **承办**：${owner}\\n` : '')"""

# ══════════════════════════════════════════════════════════════════════════
# ④ merged_report.mjs —— 分论点分组 + 执行段
# ══════════════════════════════════════════════════════════════════════════
MR_OLD_IMPORT = """import { renderMergedItem } from './dual_track.mjs';"""
MR_NEW_IMPORT = """import {
  renderMergedItem, groupByPriorityAndDimension, ownersByItem, orderActionLine,
  priorityHeading, dimensionHeading,
} from './dual_track.mjs';

/**
 * 白板那圈判定规则，落成**一行字**（Owner「审计报告」白板居中那个圈）。
 *
 * 为什么放在结论行**下面一行**而不是塞进结论行：`【审查结论：…】` 是 PRD §5.3 的
 * **逐字契约**（`prd53.conforms` 一个字一个字核），多一个标点就不合规。
 * 它也不重复结论 —— 结论是**结果**，这一行是**为什么是这个结果**（P0≥1 才 BLOCK）。
 */
const RULE_LINE = '判定口径：**P0 ≥ 1 处 ⇒ BLOCK**；**P1/P2 命中且无 P0 ⇒ 至少 REVIEW**；'
  + '**P3 只出建议、不改结论**（PRD §6.3 四层执行规则）。';"""

MR_OLD_AFTER_LINE = """  if (line) { L.push(line); L.push(''); }"""
MR_NEW_AFTER_LINE = """  if (line) { L.push(line); L.push(''); }
  // ★★ 2026-10-17（Owner：「审计报告」模式第一步 = 总（state + 1句话））——
  //   那一句**就是上面这行结论行**，不再另起一段总结（同一件事说两遍是 2026-10-13
  //   已经删过一次的毛病）。这里只补白板上那圈**判定口径**，一行。
  L.push(RULE_LINE);
  L.push('');"""

MR_OLD_BLOCK = """  if (ordered.length) {
    ordered.forEach((f, i) => { L.push(renderMergedItem(f, i, { must })); L.push(''); });
  } else {
    L.push('（本单没有并进任何条目。）');
    L.push('');
  }"""
MR_NEW_BLOCK = """  if (ordered.length) {
    // ★★ 2026-10-17（Owner：「审计报告」模式第二步 = 分论点；第三步 = 执行）──────────
    //   第二步：先按 **P 级**（白板 `P0 → G1/G2/G3 → rule out` 那一层），再按 **PRD §8.3 的四维度**；
    //          每组的表头带条数，条目编号**跨组连续** 1..N。
    //          为什么编号必须连续：2026-10-13 把两段清单合成一条时踩过 ——
    //          每组各从 1 开始会被读成「几份不同的清单」。
    //   第三步：**按问题算承办**（与卡片同一条路由表），末尾照旧落 PRD §5.3.2 那句收尾。
    L.push('## 一、分论点（P0 → P1 → P2 → P3）');
    L.push('');
    const grouped = groupByPriorityAndDimension(ordered);
    // 承办按**这一条自己的方向词**算；与卡片逐字同源（同一个 `ownersByItem`）
    const itemOwners = ownersByItem(ordered);
    const numOf = new Map();
    let n = 0;
    for (const g of grouped) {
      L.push(`### ${priorityHeading(g.level)} ｜ ${g.count} 条`);
      L.push('');
      for (const dg of g.groups) {
        L.push(`#### ${dimensionHeading(dg.dimension)} ｜ ${dg.items.length} 条`);
        L.push('');
        for (const f of dg.items) {
          const k = ordered.indexOf(f);
          L.push(renderMergedItem(f, n, { must, owner: itemOwners[k]?.text ?? null }));
          L.push('');
          numOf.set(f, n + 1);
          n += 1;
        }
      }
    }
    L.push('## 二、执行（按问题分派）');
    L.push('');
    const byRole = new Map();
    for (const f of ordered) {
      const r = itemOwners[ordered.indexOf(f)];
      for (const role of (r?.owners ?? [])) {
        if (!byRole.has(role)) byRole.set(role, []);
        byRole.get(role).push(numOf.get(f));
      }
    }
    for (const [role, nums] of byRole) {
      L.push(`- **${role}**：第 ${nums.join('、')} 条`);
    }
    L.push('');
    // ⚠️ 这一行是 PRD §5.3.2 的收尾，**句式不许改**（`renderReviewAction` 的产出）
    L.push(orderActionLine(ordered, { must }));
    L.push('');
  } else {
    L.push('（本单没有并进任何条目。）');
    L.push('');
  }"""

# ══════════════════════════════════════════════════════════════════════════
# ⑤ test_agent.mjs —— Z17 跟着裁定改（两处副本，同一段断言）
# ══════════════════════════════════════════════════════════════════════════
TA_OLD_ASSERT = """  assert.ok(/if \\(rendered0 && itemsWithAdvice\\.length > 0\\) \\{/.test(src),
    '报告闸不见了、或没挂在「条目」上 —— 会重建空报告（Owner 2026-10-15/16）');
  assert.ok(!/rendered0\\.total >= REPORT_LINK_MIN_ISSUES/.test(src),
    '`>= REPORT_LINK_MIN_ISSUES` 被加回来了 —— 那会让 <3 的行又没有报告');"""
TA_NEW_ASSERT = """  // ★★ 2026-10-17（Owner 裁定，**推翻 2026-10-14 那条本地要求**）：
  //   「逻辑不变，按照 PRD 问题数量 ≥3 个时才输出审查报告」⇒ 闸回到**两道条件**。
  //   ① 必须有**真条目**（否则建出来是空文档，2026-10-15/16 两次定过）；
  //   ② 卡内那个数必须 **≥ REPORT_LINK_MIN_ISSUES**（PRD §5.3.4）。
  assert.ok(/itemsWithAdvice\\.length > 0/.test(src),
    '报告闸丢了「必须有真条目」这一半 —— 会重建空报告（Owner 2026-10-15/16）');
  assert.ok(/rendered0\\.total >= REPORT_LINK_MIN_ISSUES/.test(src),
    '报告闸丢了 `>= REPORT_LINK_MIN_ISSUES` 这一半 —— 1–2 条的单子又会建报告（违反 PRD §5.3.4）');
  // ★ 反向对照：把门槛改成 `> 0`（= 只要有条目就建）⇒ 上面那条必须精确变红。
  //   变异体只在内存里做，不碰盘。
  {
    const body = src.match(/if \\(rendered0 && itemsWithAdvice\\.length > 0(?s:.*?)\\) \\{/)?.[0] ?? '';
    const mutated = body.replace(/rendered0\\.total >= REPORT_LINK_MIN_ISSUES/, 'rendered0.total > 0');
    assert.ok(body && !/rendered0\\.total >= REPORT_LINK_MIN_ISSUES/.test(mutated),
      '反向对照失效：把 ≥3 改成 >0 之后，判据的输入没有变化');
    assert.ok(!/rendered0\\.total >= REPORT_LINK_MIN_ISSUES/.test(mutated),
      '反向对照失效：门槛真的被改掉了却没反映出来');
  }"""


def main():
    print(f"{'[预演]' if DRY else '[落盘]'} 守衡侧审查报告格式 · 2026-10-17\n")

    patch("agent/agent.mjs", [
        (AGENT_OLD_GATE, AGENT_NEW_GATE, 1),
        (AGENT_OLD_WHY, AGENT_NEW_WHY, 1),
    ])

    patch("agent/model_side.mjs", [
        (MS_OLD_RULE, MS_NEW_RULE, 1),
        (MS_OLD_SHAPE, MS_NEW_SHAPE, 1),
        (MS_OLD_PARSE, MS_NEW_PARSE, 1),
    ])

    patch("agent/dual_track.mjs", [
        (DT_OLD_ENGINE_ITEM, DT_NEW_ENGINE_ITEM, 1),
        (DT_OLD_PICKKB, DT_NEW_PICKKB, 1),
        (DT_OLD_PICKMODEL, DT_NEW_PICKMODEL, 1),
        (DT_OLD_ITEMS, DT_NEW_ITEMS, 1),
        (DT_OLD_ACTION, DT_NEW_ACTION, 1),
        (DT_ANCHOR_ITEM, DT_NEW_HELPERS, 1),
        (DT_OLD_RETURN, DT_NEW_RETURN, 1),
    ])

    patch("agent/merged_report.mjs", [
        (MR_OLD_IMPORT, MR_NEW_IMPORT, 1),
        (MR_OLD_AFTER_LINE, MR_NEW_AFTER_LINE, 1),
        (MR_OLD_BLOCK, MR_NEW_BLOCK, 1),
    ])

    patch("test_agent.mjs", [
        (TA_OLD_ASSERT, TA_NEW_ASSERT, 2),
    ])

    print("\n全部锚点命中。" + ("（预演，未写盘）" if DRY else "已落盘（含 .bak 备份）。"))


if __name__ == "__main__":
    main()
