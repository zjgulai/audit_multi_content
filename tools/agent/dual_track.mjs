/**
 * dual_track.mjs —— 知识库侧 ＋ 模型侧 **双轨合并**（PRD 上游技术方案 §③④ 的落地）
 *
 * ── 这份东西从哪来 ─────────────────────────────────────────────────────
 * 方案原文（`两份内容治理技术方案-精读提炼.md` L164–211，逐字）：
 *
 *   ③知识库 ＋ 大模型 双校验 ── · 知识库规则作为上下文输入大模型，完成二次合规校验
 *   ④结果合并输出 ── · 全量输出知识库与大模型识别的所有问题，无遗漏覆盖全部风险
 *                     合并方式：**同一个问题 → 取交集 ／ 不同的问题 → 走并集**
 *
 *   对齐规则：**位置相同 ＋ 类目相同** → 视为「同一个问题」。
 *
 *   合并规则矩阵（六行，逐字照抄进下面 `mergeFindings` 的分支）：
 *     两轨都命中同一个问题，结论一致   → 取交集｜按该问题严重度计入 —— 双轨确认，置信最高
 *     两轨都命中同一个问题，结论不一致 → 交集冲突｜**降为 REVIEW**，不许任一侧单独定案
 *     只有知识库侧命中                 → 走并集｜按其严重度计入；带条款号／锚点／指纹，可回源
 *     只有模型侧命中                   → 走并集｜保留，标注**无库内依据**；倾向 REVIEW，
 *                                        **不由它单独定 BLOCK**
 *     两侧都没发现问题，且两侧都覆盖   → 取交集｜**PASS —— 这是 PASS 唯一的成立方式**
 *     任一侧没覆盖该主题（拒答）       → 交集不成立｜**拒答，不得输出 PASS**
 *
 * ── 为什么先做「合并」这一块 ─────────────────────────────────────────────
 * 它是这六条规则**唯一可离线断言**的部分：喂两张清单进去，出来的清单必须是确定的。
 * 模型侧那一遍要调 LLM（跑得慢、要花钱、结果不稳），但**合并判据不该因此变成不可测的** ——
 * 所以两侧的产出都只是数据，判定全在这个纯函数里。
 *
 * ── 边界（说清楚，别让它比输入大）────────────────────────────────────────
 * · 本模块**不判断一个 finding 是不是真的**，只做「对齐 / 去重 / 冲突裁决 / 计严重度」。
 * · 它**不产出 PASS**：`mergedState()` 里 PASS 的那一支要求 `kbCovered === true`，
 *   那是知识库侧给的读数，本模块既不猜也不放宽（方案 L209：任一侧没覆盖 → 拒答）。
 * · 「位置」是字符串。两边对同一处的写法不同（「00:12」vs「视频第 12 秒」）**对不上就是两处**——
 *   这是取舍，不是遗漏：宁可并集多留一条，也不许把两条不同的东西合成一条。
 */
import { createHash } from 'node:crypto';
import { basisText as extBasisText } from './ext_basis.mjs';
// ★ 2026-10-09：⑰j 要读 `agent.mjs` 的源文件核「接线那一行」—— 见那条判据的说明。
import { readFileSync } from 'node:fs';
// ★ 2026-10-12：判「PRD 那句有没有被粘上别的东西」用**守衡自己的**合规尺子，
//   不在本文件另抄一份正则（口径只有一处）。
import { conforms as prd53Conforms } from './prd53.mjs';
// ★ 2026-10-14（Owner：收尾动作行与 PRD §5.3.2 不符）：收件人**按问题方向算**，
//   不再是一个硬编码常量。路由真源在库里（`routing-policy.json`），本文件只读不抄。
import { loadRoutingPolicy, loadRoleHandles, reviewOwnersFor, renderReviewAction }
  from './routing.mjs';

/**
 * 路由表与句柄表**读一次**（模块加载时），与库侧 `review_engine.py` 的 `_approvers()`
 * 同口径：**任何异常都当作没读到**，由调用方回落 —— 判据是「拿到的东西」，
 * 不是「文件在不在」。两个表都是 registry 级文件，不是逐单变化的数据；
 * 它们改了要重启守衡才生效（与改任何其它被 import 的模块一样）。
 */
const ROUTING_POLICY = loadRoutingPolicy();
const ROLE_HANDLES = loadRoleHandles();

/** 严重度序（越大越重）。只认三态里的两个可裁剪值 + 空。 */
const SEV_ORDER = { BLOCK: 2, REVIEW: 1, '': 0 };

/**
 * **报告链接门槛** —— PRD §5.3.4 / §8.3 / §17 三处同口径：
 * 「问题数量 **≥3** 时才生成完整报告并返回链接」（1–2 条走逐条输出，不给链接）。
 *
 * ★ 与库侧**同名同口径**：`kb/l7/review-engine/core/feishu_publish.py::REPORT_LINK_MIN_ISSUES`。
 *   那一份还带着一次改判的留痕（2026-10-03 曾置 0，Owner 裁定「都按 PRD 来做」后**回退为 3**）。
 *   两处各写一遍就会各自漂移 —— 所以谁改都要同时改两边，并对住
 *   `dual_track.mjs --selftest` 里「≥3 才有这一行 / <3 必须没有」那一对断言。
 *
 * ★ 门槛挂的是**卡里那个数**（`renderMerged` 的 `total`），不是 `stats.merged`：
 *   实测一单里三个数各不相同（19:08 那张图：total 12 ／ 并进来 7 ／ 旁挂 5）。
 */
export const REPORT_LINK_MIN_ISSUES = 3;

/**
 * 方案 L211 的对齐键：**位置相同 ＋ 类目相同**。
 * ⚠️ **它只当 Map 的键用，谁也不许再把它拆回来**（见下面那段：拆回来丢过东西）。
 */
export const keyOf = (f) => JSON.stringify([String(f?.location ?? '').trim(),
                                            String(f?.category ?? '').trim()]);

const normSev = (s) => {
  const v = String(s ?? '').trim().toUpperCase();
  return v === 'BLOCK' ? 'BLOCK' : (v === 'REVIEW' ? 'REVIEW' : '');
};

/**
 * 两张问题清单 → 一张（方案的六行矩阵逐行实现）。
 *
 * @param {Array} kbFindings    知识库侧（每条至少 `{location, category, severity}`，
 *                              库侧还带 `article_no` / `anchor` / `source_sha256`）
 * @param {Array} modelFindings 模型侧（每条至少 `{location, category, severity, reason}`）
 * @returns {{items:Array, stats:object}}
 */
/* ═══════════ 同源判据（2026-10-08，Owner 裁定「两侧命中的逐字片段有重叠 ⇒ 算同一条」）═══ */

/**
 * 归一化 —— 与标定脚本 `kb/.work/calib_sameorigin.py` **同一口径**（NFKC + 小写 + 只留汉字/数字/字母）。
 * ★ 两处口径必须一致，否则标定出来的门限对不上线上判据。改一处就要改另一处。
 */
export const normText = (s) => String(s ?? '').normalize('NFKC').toLowerCase()
  .replace(/[^0-9a-z\u4e00-\u9fff]+/g, '');

/** 最长公共子串长度（滚动数组）。与标定同一实现。 */
export function lcsLen(a, b) {
  const A = String(a ?? ''), B = String(b ?? '');
  if (!A || !B) return 0;
  const [x, y] = A.length <= B.length ? [A, B] : [B, A];
  let prev = new Array(x.length + 1).fill(0); let best = 0;
  for (const ch of y) {
    const cur = new Array(x.length + 1).fill(0);
    for (let i = 1; i <= x.length; i += 1) {
      if (x[i - 1] === ch) { cur[i] = prev[i - 1] + 1; if (cur[i] > best) best = cur[i]; }
    }
    prev = cur;
  }
  return best;
}

/** 类目族 = 大类（`平台与促销-静音绝对化表述` ⇒ `平台与促销`）。标定里第 3 条约束用它。 */
export const catFamily = (c) => String(c ?? '').split(/[-－]/)[0].trim();

/** 两侧条目各自的「逐字命中片段」—— 同源判据比的就是它。 */
const excerptOf = (f) => normText(f?.excerpt ?? f?.matched_term ?? '');

/**
 * 两条命中的是不是**同一个问题**？—— 三条约束，缺一不可。
 *
 * ★ 判据只有「归一化后**完全相等**」，**不用 R 门限**（2026-10-08 标定后的决定）：
 *   标定（`kb/.work/calib_sameorigin.py`，阴性 n=20000 / 阳性 494 对）显示 R≥4 能收进
 *   99.6% 的阳性、阴性误并约 1% —— **但那个「阳性」样本是「库里同一表达写了多遍」，
 *   那是「库自身冗余」的代理，不是「两侧指同一处」的代理。代理弱，就不拿它当判据。**
 *   同时把 R 值**记进读数**，攒够真实双轨数据再决定要不要启用门限。
 *
 * ★ 一条结构性事实（不写下来下一个人会以为 R 覆盖了全部）：**2 字命中词**（「静音」「限时」）
 *   的 R 最大只能是 2 ⇒ 对它们 R 判据**结构上不可能成立**，只能靠相等。
 *   而实测的重复计数正是这个形状 —— 库侧与模型侧都指「静音」两个字。
 */
export function sameOrigin(a, b) {
  const ea = excerptOf(a); const eb = excerptOf(b);
  if (!ea || !eb) return { same: false, why: '一侧没有逐字命中片段（无从比）', r: 0, equal: false };
  const fa = catFamily(a?.category); const fb = catFamily(b?.category);
  const famOk = !fa || !fb || fa === fb;
  const equal = ea === eb;
  const r = lcsLen(ea, eb);
  // ── 精确相等 ⇒ **算同一条，且不看类目族** ─────────────────────────────────────
  //
  // ★ 这一条是**被测试逼出来的**（2026-10-08）。原设计把「类目族相同」放在前面当硬闸，
  //   而 `⑪` 那条用例用的是**真实事故的形状**：库侧大类「平台与促销」／模型侧「措辞表达」
  //   —— **两侧用的是两套不同的类目词表**（库按自己的表分组，模型按 PRD §5.3 的维度标注），
  //   于是那道闸**永远不成立** ⇒ Owner 那张卡的重复计数**根本修不了**。
  //
  //   所以：**精确相等自证同源**，不需要类目族背书。类目族只在**模糊匹配**（R 门限）时才有用
  //   —— 而模糊本次**没启用**，那道闸留在 `famOk` 里备将来。
  //   代价说清：同一个词可能被两侧当成**不同**问题（「静音」既可能是措辞绝对化、也可能是
  //   产品参数虚假）。那种情况现在会**并成一条**，靠结论里那句注（`same_origin_note`）
  //   让人看见两侧依据、自己判断 —— 而不是靠代码替人决定。
  if (equal) {
    return { same: true, r, equal,
             why: `两侧逐字片段相同（「${String(a?.excerpt ?? a?.matched_term ?? '').trim()}」）`
                  + (famOk ? '' : `；类目族不同（${fa || '—'} ／ ${fb || '—'}）—— 两侧词表不同，**
以逐字片段为准**`) };
  }
  if (!famOk) {
    return { same: false, why: `类目族不同（${fa || '—'} ／ ${fb || '—'}）且逐字片段不相同`,
             r, equal };
  }
  return { same: false, why: '逐字片段不相同（门限判据本次**未启用**，见 sameOrigin 的注释）', r, equal };
}

export function mergeFindings(kbFindings = [], modelFindings = []) {
  const sides = new Map();          // key → { kb, model }
  const pushUnique = (map, f, key) => {
    const prev = map.get(key);
    // 同一侧出现两条同键的：**合并成一条、把两次的原文都留着**（不静默丢）。
    if (prev) prev.raw = [].concat(prev.raw ?? [prev], f);
    else map.set(key, f);
  };
  const kbBy = new Map(); const moBy = new Map();
  for (const f of kbFindings) pushUnique(kbBy, f, keyOf(f));
  for (const f of modelFindings) pushUnique(moBy, f, keyOf(f));

  for (const [k, f] of kbBy) sides.set(k, { kb: f, model: null });

  // ── 先按键配对；**配不上的再走一趟同源判据**（2026-10-08）───────────────────
  //   真事故：库侧报「平台与促销-静音绝对化表述」、模型侧报「措辞表达」，
  //   位置与类目**两个都不同** ⇒ 按原规则是两条 ⇒ 问题数虚高（Owner 那张卡写 4 处、实际 3 处），
  //   而模型只能在正文里写一句「实际 3 处」来补 —— **那是模型在替代码打补丁**。
  const kbLeft = new Set(kbBy.keys());
  let nSameOrigin = 0; const rSeen = [];
  for (const [k, f] of moBy) {
    const cur = sides.get(k);
    if (cur) { cur.model = f; kbLeft.delete(k); continue; }
    // 键对不上 ⇒ 找一条**还没被配上**的库侧条目，试试同源
    let hit = null;
    for (const kk of kbLeft) {
      const so = sameOrigin(kbBy.get(kk), f);
      rSeen.push(so.r);
      if (so.same) { hit = kk; break; }
    }
    if (hit) {
      const kbItem = kbBy.get(hit);
      sides.set(k, { kb: kbItem, model: f, sameOrigin: true, sameOriginR: lcsLen(excerptOf(kbItem), excerptOf(f)) });
      // ★ 库侧那条**已经在 `sides` 里了**（上面先给每个 KB 键都建了位）——
      //   不删掉它，同源合并就会**多出一条重复**（实测：`same_origin=1` 但条目数是 2）。
      //   这是「合并之后忘了销账」，不是判据错。
      sides.delete(hit);
      kbLeft.delete(hit);
      nSameOrigin += 1;
    } else {
      sides.set(k, { kb: null, model: f });
    }
  }

  const items = [];
  let nBoth = 0; let nConflict = 0; let nKbOnly = 0; let nModelOnly = 0;

  for (const [key, { kb, model }] of sides) {
    // ══════════════════════════════════════════════════════════════════════════
    // ★★ 2026-10-13（修一个 **Owner 那张卡上就看得见的真 bug**）：
    //   **不再从 `key` 里 split 回来。**
    // ══════════════════════════════════════════════════════════════════════════
    //   病灶：`keyOf` 原先是 `` `${location}|${category}` ``，而这里写的是
    //     `const [location, category] = key.split('|')` —— **拼起来再拆回去**。
    //   只要 `location` 里本身带 `|`，这个来回就丢东西。实测那一条（P0 快路 H05）：
    //     location = `全文，逐字命中 \`最\s*(好|佳|优|强|安全|低价|便宜|有效|…)\``
    //     ⇒ 拆回来 location = `` 全文，逐字命中 `最\s*(好 ``（**命中正则被腰斩**）
    //        category = `佳`
    //     ⇒ 卡上印出 **`1.【佳】`** 与 **`· 佳类问题：1 个`**，而真维度是
    //        `绝对化与安全承诺-虚假安全承诺`。**读者拿到的是一条被改坏的数据。**
    //
    //   口径：两侧的 `location` / `category` **本来就在对象上** ——
    //     库侧在就用库侧的（与原先拆出来的那一支逐字一致），否则用独立复核那一侧的。
    //     `keyOf` 同时改成了 JSON（分隔符不可能出现在数据里，也不会两组拼成同一个键）。
    const src = kb ?? model;
    const location = String(src?.location ?? '').trim();
    const category = String(src?.category ?? '').trim();
    if (kb && model) {
      const a = normSev(kb.severity); const b = normSev(model.severity);
      if (a === b) {
        // ── 取交集：双轨确认，按该问题严重度计入 ──
        nBoth++;
        // ★ 同源配对（键对不上、靠逐字片段判成同一条）必须**把这个来路说出来** ——
        //   否则读者看到的是「双轨确认」，而实际上两侧的**类目族都不一样**，
        //   那种情况要人自己判断（见 `sameOrigin` 的取舍说明）。
        const _so = sides.get(key);
        const _fa = catFamily(kb?.category); const _fb = catFamily(model?.category);
        const soInfo = _so?.sameOrigin
          ? `；**同源判据**：位置/类目对不上，按两侧逐字片段相同判为同一条`
            + `（R=${_so.sameOriginR ?? 0}）`
            + (_fa && _fb && _fa !== _fb
                ? `；**类目族不同（${_fa} ／ ${_fb}）**—— 两侧用的是两套词表，请人工确认说的是不是同一处`
                : '')
          : '';
        items.push({
          location, category, severity: a, source: 'both', confirmed_by_both: true,
          same_origin: !!sides.get(key)?.sameOrigin,
          // ★ 顶层 reason 必须留一份：渲染（`renderMerged`）读的是它。
          reason: kb.reason ?? model.reason ?? null,
          kb: pickKb(kb), model: pickModel(model),
          note: '两轨都命中同一个问题，结论一致 —— 双轨确认（置信最高）' + soInfo,
        });
      } else {
        // ── 交集冲突：降为 REVIEW，不许任一侧单独定案 ──
        nConflict++;
        items.push({
          location, category, severity: 'REVIEW', source: 'both-conflict',
          reason: kb.reason ?? model.reason ?? null,
          kb: pickKb(kb), model: pickModel(model),
          note: `两轨都命中同一个问题但结论不一致（库侧 ${a || '—'} ／ 模型侧 ${b || '—'}）`
              + ' ⇒ **降为 REVIEW**，连同两侧依据一起转人工；不许任一侧单独定案',
        });
      }
    } else if (kb) {
      // ── 走并集：只有库侧命中，按其严重度计入 ──
      nKbOnly++;
      items.push({
        location, category, severity: normSev(kb.severity), source: 'kb',
        reason: kb.reason ?? null, kb: pickKb(kb), model: null,
        note: '只有知识库侧命中 —— 带条款号／锚点／指纹，可回源',
      });
    } else {
      // ── 走并集：只有模型侧命中 ⇒ 留住，但**不由它单独定 BLOCK** ──
      nModelOnly++;
      const asked = normSev(model.severity);
      items.push({
        location, category, severity: 'REVIEW', source: 'model',
        reason: model.reason ?? null, kb: null, model: pickModel(model),
        asked_severity: asked || null,
        note: '只有模型侧命中 —— **无库内依据**；倾向 REVIEW，不由它单独定 BLOCK'
              + (asked === 'BLOCK' ? '（模型侧报的是 BLOCK，已按本规则降为 REVIEW）' : ''),
      });
    }
  }

  items.sort((x, y) => (SEV_ORDER[y.severity] - SEV_ORDER[x.severity])
    || String(x.category).localeCompare(String(y.category))
    || String(x.location).localeCompare(String(y.location)));

  return {
    items,
    stats: {
      kb: kbFindings.length, model: modelFindings.length, merged: items.length,
      both: nBoth, conflict: nConflict, kb_only: nKbOnly, model_only: nModelOnly,
      // ★ 同源配对（键对不上、但逐字片段相同）与它见到的 R 分布 ——
      //   R 的门限本次**未启用**，先把这个读数收起来，攒够真实数据再定（见 `sameOrigin`）。
      same_origin: nSameOrigin,
      same_origin_r: rSeen.length ? { n: rSeen.length, max: Math.max(...rSeen), min: Math.min(...rSeen) } : null,
      // ★ 合成前后的**恒等式**：合并只许去重、不许凭空多出或少掉。
      //   多出 = 我造了东西；少掉 = 我静默吞了东西。两者都要能被断言抓住。
      identity_ok: items.length === (nBoth + nConflict + nKbOnly + nModelOnly),
    },
  };
}

const pickKb = (f) => ({
  article_no: f?.article_no ?? null, anchor: f?.anchor ?? null,
  source_sha256: f?.source_sha256 ?? null, reason: f?.reason ?? null,
  excerpt: f?.excerpt ?? f?.matched_term ?? null,
  // ★ 2026-10-08：这两格**必须带过来** —— 漏掉它们，`renderMerged` 就永远拿不到库侧
  //   已经产好的「逐字命中文案 + 飞书源直链」，只能退回重建版
  //   （实测印出来是 `《知识库》（未给条款号）（锚点：—）` —— 点不开、也没说命中了什么）。
  //   这就是 bug 本体：判据抓对了、搬运却在这一行把字段丢了。
  basisLine: f?.basisLine ?? null,
  reasonLine: f?.reasonLine ?? null,
  // ★ 2026-10-09：库侧已经产好的「建议」——不搬过来，渲染层只能印硬编码那句
  suggestionLine: f?.suggestionLine ?? null,
});
const pickModel = (f) => ({
  reason: f?.reason ?? null, excerpt: f?.excerpt ?? null, severity: normSev(f?.severity) || null,
  // ★ 2026-10-09：模型侧新增的「可执行改法」字段（见 model_side.mjs）
  suggestion: f?.suggestion ?? null,
  // ★ 2026-10-13：**依据来源 id**（闭集 id，不是 URL）—— 少了这一行，
  //   渲染层的 `extBasisText()` 永远拿到 `{}`，于是「有依据」那条路**一次都不会生效**
  //   （实测：加完提示词与渲染，印出来还是「没给出可核的外部来源」）。
  //   白名单式搬运的代价就是这个：**新字段不加进来就静默消失**。
  source: f?.source ?? null,
  // ★ 2026-10-13（Owner：「模型当然有权限写 url」）：模型自己给的 URL + 来源名 + 核验三态，
  //   三个一起搬 —— 少搬 `url_probe` 就会出现「标了链接却看不出核没核过」。
  source_url: f?.source_url ?? null,
  source_name: f?.source_name ?? null,
  url_probe: f?.url_probe ?? null,
});

/**
 * 合并后的三态。
 *
 * ★ PASS 那一行是**方案的字面规则**，不是我的取舍：
 *   `两侧都没发现问题，且两侧都覆盖到该主题 → PASS —— 这是 PASS 唯一的成立方式`
 *   `任一侧没覆盖该主题（拒答） → 交集不成立 → 拒答，不得输出 PASS`
 *
 *   所以 `kbCovered !== true` 时**永远到不了 PASS** —— 这正是「不许因为加了模型侧
 *   就把原来拒答的单子放行」的执行点。Owner 2026-10-06 的原话是「PASS 门限一个字不改」。
 *
 * @param {{kbCovered:boolean, merged:Array}} a
 * @returns {'PASS'|'REVIEW'|'BLOCK'|'拒答'}
 */
export function mergedState({ kbCovered = false, merged = [], kb = null } = {}) {
  // ★ 2026-10-07 加（Owner 同意，缺陷实测：**库侧零读数却落了 PASS**）——
  //   **「库侧没有读数」⇒ PASS 不可达。**
  //   实测：素材「这条社媒文案能不能发：这批婴幼儿用品的文案里写了医用级」
  //     （表行 `recvxlAvpEWMIX`）— 日志 `[review] ⚠️ 没读到机读旁挂` ⇒ 库侧一个读数都没有，
  //     而它落表的 `Agent 结论` / `状态` 是 **PASS**、`问题数量 0`、`置信度 0`。
  //     同一批的另一条（旁挂读到了、state=NEEDS_INPUT）落的是 `NEEDS_INPUT`/待审 —— 对比之下
  //     差别不在素材，在**有没有读数**。
  //   ⇒ PASS 是唯一的「放行」态、也是唯一不可挽回的错：**没读库就不许放行**。
  //     注意这不是新判据、也不放宽任何东西：`kbCovered` 本来就在「认不出来时判没覆盖」，
  //     这里只是把「**没有读数**」与「**读到了、说覆盖了**」分开 —— 后者才够格 PASS。
  const noReading = kbNoReadingOf(kb);
  // ★ 2026-10-07 改（实测缺陷：库侧红线被降级）—— 两条判据加在**最前面**：
  //   ① **库侧拒答 ⇒ 不许出三态结论**：库没判，就不能拿模型侧的意见冒充"双轨结论"。
  //      （原先拒答被当成「0 条」静默参与合并 ⇒ 用户看到一张 REVIEW 卡，
  //        而表里那行的结论是 NEEDS_INPUT —— 同一单两个结论。）
  //   ② **单调性：只许保持或升级，不许降级**：库侧 BLOCK 命中 ⇒ 合并后必须是 BLOCK。
  //      原先只认「合并条目里有没有 BLOCK」，而库侧的条目是**正则从中文答案里抠**的
  //      （`kbFindingsOf`），PRD §5.3.3 规定 **≥3 条时库侧只出汇总** ⇒ 抠不到 ⇒ 降级。
  if (kb && kb.refused === true) return 'NEEDS_INPUT';
  if (merged.some((f) => f.severity === 'BLOCK')) return 'BLOCK';
  if (kb && String(kb.state).toUpperCase() === 'BLOCK') return 'BLOCK';
  if (merged.length) return 'REVIEW';
  if (kb && String(kb.state).toUpperCase() === 'REVIEW') return 'REVIEW';
  if (noReading) return '拒答';          // 库侧没读数 ⇒ 不出 PASS（理由见上）
  return kbCovered === true ? 'PASS' : '拒答';
}

/** 给报告/卡片用的一行读数（谁贡献了几条），便于人核对「并集到底并了什么」。 */
export function mergeSummary(stats = {}) {
  return `知识库侧 ${stats.kb ?? 0} 条 ／ 模型侧 ${stats.model ?? 0} 条`
    + ` ⇒ 合并 ${stats.merged ?? 0} 条`
    + `（双轨确认 ${stats.both ?? 0} · 冲突降 REVIEW ${stats.conflict ?? 0}`
    + ` · 仅库侧 ${stats.kb_only ?? 0} · 仅模型侧 ${stats.model_only ?? 0}）`;
}

/** 合并结果的指纹：同一对输入必须同输出（用来做「确定性」断言）。 */
export function fingerprint(merged) {
  return createHash('sha256')
    .update(JSON.stringify(merged.map((f) => [f.location, f.category, f.severity, f.source])))
    .digest('hex').slice(0, 16);
}

/* ═══════════════════════════ 自证 ═══════════════════════════ */
/**
 * 六条矩阵规则逐条断言 + 两条反向对照。
 *
 * 为什么每一条都要有：这六行是**方案里逐字写下的判定规则**，而它们全都长得像
 * 「合并两张表」这种一看就懂、写起来却很容易把某一支写反的东西。
 * ★ 尤其第 6 条（任一侧没覆盖 → 拒答）：它是**唯一挡住「加了模型侧就把原来拒答的
 *   单子放行」**的那一行。少了它，双轨改造会静默变成一次**安全放松**（§2.4.1）。
 */
export function selftest() {
  let pass = 0; const bad = [];
  const ok = (n) => { pass++; console.log(`  ✅ ${n}`); };
  const no = (n, why) => { console.log(`  ❌ ${n} —— ${why}`); bad.push(n); };
  const eq = (n, got, want) => (JSON.stringify(got) === JSON.stringify(want)
    ? ok(n) : no(n, `期望 ${JSON.stringify(want)}，实得 ${JSON.stringify(got)}`));

  const F = (location, category, severity, extra = {}) => ({ location, category, severity, ...extra });

  // ① 同题同论 → 取交集
  {
    const r = mergeFindings([F('00:12', '合规', 'BLOCK', { article_no: 'W-1.1' })],
                            [F('00:12', '合规', 'BLOCK')]);
    eq('① 同题同论 → 取交集，严重度按该问题计入', [r.items.length, r.items[0].severity, r.items[0].source],
       [1, 'BLOCK', 'both']);
    eq('① 库侧依据被带出来（条款号）', r.items[0].kb.article_no, 'W-1.1');
  }
  // ② 同题冲突 → 降 REVIEW（不许任一侧单独定案）
  {
    const r = mergeFindings([F('00:12', '合规', 'BLOCK')], [F('00:12', '合规', 'REVIEW')]);
    eq('② 同题冲突 → 降为 REVIEW', [r.items.length, r.items[0].severity, r.items[0].source],
       [1, 'REVIEW', 'both-conflict']);
    eq('② 冲突时两侧依据都留着（转人工用）', [!!r.items[0].kb, !!r.items[0].model], [true, true]);
  }
  // ③ 仅库侧 → 走并集，按其严重度计入
  {
    const r = mergeFindings([F('图 1', '消费者安全', 'BLOCK', { article_no: 'S-1.2' })], []);
    eq('③ 仅库侧 → 保留且按其严重度', [r.items.length, r.items[0].severity, r.items[0].source],
       [1, 'BLOCK', 'kb']);
  }
  // ④ 仅模型侧 → 保留，但**不由它单独定 BLOCK**
  {
    const r = mergeFindings([], [F('00:08', '消费者安全', 'BLOCK', { reason: '安全座椅' })]);
    eq('④ 仅模型侧报 BLOCK → 降为 REVIEW', [r.items[0].severity, r.items[0].source],
       ['REVIEW', 'model']);
    eq('④ 它原本要的严重度如实记着（不假装它没说过）', r.items[0].asked_severity, 'BLOCK');
    eq('④ 标注「无库内依据」', /无库内依据/.test(r.items[0].note), true);
  }
  // ④b ★ 模型侧**依据链接**（2026-10-13 Owner：「模型侧输出的问题需要带上依据」）
  //     判据三层：挑中来源 ⇒ 卡里带**真链接**；挑不出 ⇒ 明说没有；手写 URL ⇒ **必须被丢掉**。
  {
    const blkOf = (src) => renderMerged(
      mergeFindings([], [F('全文', '合规', 'REVIEW',
        { reason: 'FDA 批准表述', excerpt: 'FDA approved', suggestion: '删掉', source: src })]).items,
      { state: 'REVIEW', kb: kbSideOf({ review: { state: 'REVIEW', issue_count: 1 } }), kbTextCount: 0 }).block;
    const ok1 = blkOf('S11');
    eq('④b 挑中已登记来源 ⇒ 依据行带真链接（fda.gov）',
       [/fda\.gov/.test(ok1), /外部标准/.test(ok1)], [true, true]);
    const no1 = blkOf(null);
    eq('④b2 ★ 反向对照：两种来源都没给 ⇒ 不许出现任何链接，且明说没有',
       [/https?:\/\//.test(no1), /也没给出外部来源/.test(no1)], [false, true]);
    // ④b4 ★ 模型**自写 URL** 这条路（Owner 亲口：「当然有权限写 url」）——
    //      必须印出来、且带核验状态；核验说「未核」时也必须照印（不许因为取不到就删掉）。
    const F2 = (extra) => ({ location: '全文', category: '合规', severity: 'REVIEW',
      reason: '平台举证要求', suggestion: '补', ...extra });
    const blkUrl = (probe) => renderMerged(
      mergeFindings([], [F2({ source_url: 'https://advertising.amazon.com/help/G6UU66YLSCUYDULQ',
        source_name: 'Amazon Ads · Claims and substantiation', url_probe: probe })]).items,
      { state: 'REVIEW', kb: kbSideOf({ review: { state: 'REVIEW', issue_count: 1 } }), kbTextCount: 0 }).block;
    const u1 = blkUrl({ state: 'ok', http: 200 });
    eq('④b4 ★ 模型自写 URL ⇒ 印出来且标「已核」',
       [/advertising\.amazon\.com/.test(u1), /✅ 已核（HTTP 200）/.test(u1)], [true, true]);
    const u2 = blkUrl({ state: 'unreachable', why: '超时' });
    eq('④b5 ★ 反向对照：取不到也**不许删链接**，只标「未核」',
       [/advertising\.amazon\.com/.test(u2), /未核/.test(u2)], [true, true]);

    const bad1 = blkOf('https://evil.example/fake');
    // ★ ④b3 **口径已变**（Owner 2026-10-13：「模型当然有权限写 url」）：原先断言
    //   「手写 URL 一律丢掉」—— 那是我定的、过头了的规矩。现在 URL 走 `source_url`
    //   这条正规路（照印 + 核验状态，见 ④b4/④b5）；而塞进**闭集 id 那一格**（`source`）
    //   的 URL 仍然不算数：那一格只认 S1…S17，链接一律由 `ext_basis` 按登记表挂。
    eq('④b3 ★ 口子分开：URL 塞进「来源 id」那一格 ⇒ 不算数',
       [/evil\.example/.test(bad1), /也没给出外部来源/.test(bad1)], [false, true]);
  }
  // ④c ★ 逐条依据**落库**（Owner 2026-10-13：「这个要落库」）
  {
    const items = mergeFindings(
      // ⚠️ 夹具形状要照 `kbFindingsOf()` 的**产出**来：`basisLine` 在**条目顶层**
      //   （塞进 `kb:{}` 里会被 `pickKb` 白名单丢掉 —— 我第一版就是这么写的，实测那条没进块）
      [{ location: '全文', category: '措辞表达', severity: 'REVIEW',
         article_no: 'W-1.33', anchor: '#广告文案明细/recv/命中片段',
         basisLine: '依据：《措辞表达库 v0》第 W-1.33 条 ← 逐字命中「最好」｜原始出处：https://momcozy-in.feishu.cn/base/X?record=recv' }],
      //   ⚠️ 两条模型侧条目**类目必须不同**：同位置同类目会被合并成一条（合并规则第一条），
      //      那样就测不出「没有依据的那条不列」。
      [F('全文', '合规', 'REVIEW', { reason: 'FDA 批准表述', suggestion: '删', source: 'S11' }),
       F('第 2 段', '本地化', 'REVIEW', { reason: '没有依据的那条', suggestion: 'x' })]).items;
    const blk = evidenceBlock(items);
    eq('④c 落库块：库侧那条用**它自己的** basisLine（带飞书直链，原样搬）',
       [/逐字命中「最好」/.test(blk), /feishu\.cn\/base/.test(blk)], [true, true]);
    eq('④c2 ★ 模型侧那条把**依据 URL** 落进表里（fda.gov）',
       [/fda\.gov/.test(blk)], [true]);
    eq('④c3 ★ 反向对照：**没有依据的条目一条都不列**（凑数就是撒谎）',
       [/没有依据的那条/.test(blk)], [false]);
    eq('④c4 上限：超过 max 条时明确说「其余见报告」',
       evidenceBlock(items, { max: 1 }).includes('另有 1 条'), true);
    eq('④c5 有依据的条目**全部**列出（库侧 1 + 模型侧 1 = 2 条）',
       (evidenceBlock(items).match(/^\d+\.【/gm) || []).length, 2);
  }
  // ⑤ 两侧都没问题 + 两侧都覆盖 → PASS（方案说这是 PASS 唯一的成立方式）
  {
    const r = mergeFindings([], []);
    eq('⑤ 两侧都没问题且库侧覆盖 → PASS', mergedState({ kbCovered: true, merged: r.items }), 'PASS');
  }
  // ⑥ ★ 任一侧没覆盖 → 拒答，**不得输出 PASS**
  {
    const r = mergeFindings([], []);
    eq('⑥ 库侧没覆盖 → 拒答（不许 PASS）', mergedState({ kbCovered: false, merged: r.items }), '拒答');
    // 反向对照：**模型侧有命中**时，也绝不许因为「有内容可说了」就变成 PASS
    const r2 = mergeFindings([], [F('全片', '措辞表达', 'REVIEW')]);
    eq('⑥ 反向对照：模型侧只有命中、库侧没覆盖 → REVIEW（仍不是 PASS）',
       mergedState({ kbCovered: false, merged: r2.items }), 'REVIEW');
  }
  // ⑦ 恒等式：合并只许去重，不许凭空多出/静默吞掉
  {
    const r = mergeFindings([F('a', 'x', 'REVIEW'), F('a', 'x', 'REVIEW')],
                            [F('b', 'y', 'REVIEW'), F('a', 'x', 'REVIEW')]);
    eq('⑦ 合成前后条数守恒（同一侧同键合并成一条）',
       [r.stats.identity_ok, r.items.length, r.stats.kb, r.stats.model], [true, 2, 2, 2]);
  }
  // ⑧ 确定性：同一对输入必须同输出（合并里不许有随机/时间）
  {
    const kb = [F('00:12', '合规', 'BLOCK', { article_no: 'W-1.1' })];
    const mo = [F('00:12', '合规', 'BLOCK'), F('图 1', '隐私', 'REVIEW')];
    const a = fingerprint(mergeFindings(kb, mo).items);
    const b = fingerprint(mergeFindings(kb, mo).items);
    eq('⑧ 同输入同输出（指纹一致）', a === b, true);
    // 反向对照：**换一个字段**就必须换指纹，否则这条断言恒真、什么也没测
    // 反向对照：**换一个严重度**就必须换指纹 —— 否则这条断言对「指纹」恒真、什么也没测。
    const c = fingerprint(mergeFindings(kb, [F('图 1', '隐私', 'BLOCK')]).items);
    eq('⑧ 反向对照：严重度变了指纹必须变', c !== a, true);
  }
  // ⑨ 反向对照：**位置不同但类目相同 → 不许合并成一条**（对齐规则是两者都要）
  {
    const r = mergeFindings([F('00:12', '合规', 'BLOCK')], [F('00:08', '合规', 'BLOCK')]);
    eq('⑨ 反向对照：位置不同、类目相同 → 仍是两条（并集）', r.items.length, 2);
    const r2 = mergeFindings([F('00:12', '合规', 'BLOCK')], [F('00:12', '安全', 'BLOCK')]);
    eq('⑨ 反向对照：位置相同、类目不同 → 仍是两条（并集）', r2.items.length, 2);
  }

  // ⑩ ★★ **红线不许被降级**（2026-10-07 实测缺陷的回归判据，**必须能红**）─────────────
  //    病灶：库侧判到 **3 条 P0**（H06/H07/H09）时，PRD §5.3.3 要求只出分类汇总 ⇒
  //    逐条正则抠不到 ⇒ 库侧被读成「0 条」⇒ 合并把 BLOCK 改写成 REVIEW。
  //    实测那两条真素材：2 条 ⇒ 抽到 2 条（结论保住 BLOCK）；3 条 ⇒ 抽到 0 条（**降级**）。
  {
    const p0 = kbSideOf({ p0_fastpath: { rule_codes: ['H06', 'H07', 'H09'] }, issue_count: 3 });
    eq('⑩ P0 快路的结构化读数：结论 BLOCK ／ 条数 3',
       [p0.state, p0.issueCount, p0.refused], ['BLOCK', 3, false]);
    const modelTwo = [F('全文', '合规', 'REVIEW'), F('全文', '消费者安全', 'REVIEW')];
    const st = mergedState({ kbCovered: true, merged: modelTwo, kb: p0 });
    eq('⑩ ★ 库侧 3 条 BLOCK ＋ 文本抽出 0 条 ⇒ 合并态必须是 BLOCK（不许降级成 REVIEW）', st, 'BLOCK');
    // 反向对照（防「这条断言恒真」）：**库侧不是 BLOCK** 时，同一批模型侧条目只能到 REVIEW
    const p0r = kbSideOf({ review: { state: 'REVIEW', issue_count: 1 } });
    eq('⑩ 反向对照：库侧 REVIEW ＋ 同一批模型侧条目 ⇒ 合并态 REVIEW（不是 BLOCK）',
       mergedState({ kbCovered: true, merged: modelTwo, kb: p0r }), 'REVIEW');
    // 渲染：库侧条数**必须留着**，且明说明细未并进来、总数是上限。
    // ★★ 2026-10-13（Owner 裁定）：这一族读数**不上卡** —— 改走 `internalNotes`
    //   （模型上下文 + **会话记忆**），卡片与报告都不显示。
    //   判据因此分两面，缺一面都不算数：**笔记里必须有**（一个字没丢）
    //   ＋ **卡面上必须没有**（是搬，不是删）。
    const rd = renderMerged(modelTwo, { state: 'BLOCK', kb: p0, kbTextCount: 0 });
    eq('⑩ 库侧条数＋总数上限＋「明细未并进来」要留着（在查证笔记里）',
       [rd.total, /结构化读数 BLOCK\/3/.test(rd.internalNotes), /上限/.test(rd.internalNotes)],
       [5, true, true]);
    eq('⑩ 反向对照：同一段**不许**再出现在卡面（Owner 2026-10-13：不上卡）',
       [/结构化读数/.test(rd.block), /上限/.test(rd.block)], [false, false]);
  }

  // ⑪ ★★ **库侧拒答 ⇒ 不许出三态结论**（2026-10-07；同一天五条里两条栽在这上面）─────────
  //    病灶：拒答被折算成「0 条」⇒ 用户收到一张像双轨结论的 REVIEW 卡，而表里那行是 NEEDS_INPUT。
  {
    const refused = kbSideOf({ review: { state: 'NEEDS_INPUT', issue_count: 0,
      refusal: { state: 'NEEDS_INPUT', reason: '供给链不新鲜' } } });
    eq('⑪ 机读旁挂的拒答被认出来（**没有 reason_code 也要认**，实测超期拒答只有中文 reason）',
       [refused.refused, refused.reason], [true, '供给链不新鲜']);
    const st = mergedState({ kbCovered: true, merged: [F('全文', '合规', 'REVIEW')], kb: refused });
    eq('⑪ 库侧拒答 ⇒ 合并态 = NEEDS_INPUT（不是 REVIEW）', st, 'NEEDS_INPUT');
    const rd = renderMerged([F('全文', '合规', 'REVIEW')], { state: st, kb: refused, kbTextCount: 0 });
    eq('⑪ 卡里必须写明「不得当通过依据，也不得当拦截依据」',
       [/不得当通过依据/.test(rd.block), /NEEDS_INPUT/.test(rd.line)], [true, true]);
    // 反向对照：**没有 refusal** 的正常 REVIEW 单不许被判成拒答
    const notRefused = kbSideOf({ review: { state: 'REVIEW', issue_count: 1 } });
    eq('⑪ 反向对照：正常 REVIEW 单不许被判成拒答', notRefused.refused, false);
    // ★★ ⑪c **判据不许过宽**：覆盖缺口的形状是「顶层 REVIEW ＋ refusal.state=NEEDS_INPUT」
    //    （`with_kb_evidence.py` 注释原话：「这里如实写 REVIEW：下游读的是这个字段」）。
    //    第一版「有 refusal 就算拒答」把它也改判成 NEEDS_INPUT —— 当天实测逼出来的。
    const cov = kbSideOf({ review: { state: 'REVIEW', issue_count: 1,
      refusal: { state: 'NEEDS_INPUT', reason_code: 'coverage_not_covered',
                 coverage: { covered: false } } } });
    eq('⑪c 覆盖缺口：**不算拒答**（认顶层 state=REVIEW），但要标出 coverageGap',
       [cov.refused, cov.state, cov.coverageGap], [false, 'REVIEW', true]);
    const stCov = mergedState({ kbCovered: false,
      merged: [F('全文', '合规', 'REVIEW')], kb: cov });
    eq('⑪c2 覆盖缺口的合并态 = REVIEW（不是 NEEDS_INPUT）', stCov, 'REVIEW');
    const rdCov = renderMerged([F('全文', '合规', 'REVIEW')],
      { state: stCov, kb: cov, kbTextCount: 0 });
    eq('⑪c3 「库对该题材没有可依据的条款 / 不是发现了内容问题」要留着（在查证笔记里）',
       [/没有可依据的条款/.test(rdCov.internalNotes),
        /不是发现了内容问题/.test(rdCov.internalNotes)], [true, true]);
    eq('⑪c3b 反向对照：这段不许再上卡（Owner 把那句原话列进了「都去掉」）',
       [/coverage_not_covered/.test(rdCov.block), /没有可依据的条款/.test(rdCov.block)], [false, false]);
  }

  // ⑫ 向后兼容：不给 `kb`（读不到旁挂）时，判据必须与改动前**逐字相同**
  {
    eq('⑫ 反向对照：不给 kb ⇒ PASS 门限与原来一致（覆盖成立才 PASS）',
       [mergedState({ kbCovered: true, merged: [] }), mergedState({ kbCovered: false, merged: [] })],
       ['PASS', '拒答']);
    eq('⑫ 反向对照：不给 kb ⇒ 有条目就是 REVIEW（同原来）',
       mergedState({ kbCovered: true, merged: [F('a', 'x', 'REVIEW')] }), 'REVIEW');
  }

  // ⑬ ★★ 2026-10-07（Owner 同意）—— **库侧没有读数 ⇒ PASS 不可达**。
  //   实测缺陷（不是假设）：素材「这条社媒文案能不能发：这批婴幼儿用品的文案里写了医用级」
  //   （表行 `recvxlAvpEWMIX`）—— 日志 `[review] ⚠️ 没读到机读旁挂` ⇒ 库侧**零读数**，
  //   而表里落的是 `Agent 结论=PASS` / `状态=PASS` / `问题数量 0` / `置信度 0`。
  //   同一批另一条（旁挂读到了、`state=NEEDS_INPUT`）落的是 NEEDS_INPUT/待审 ⇒
  //   差别不在素材，在**有没有读数**。
  {
    const noRead = kbSideOf({ answer: '（链的回答原文，但没有任何机读旁挂）' });
    eq('⑬a 无旁挂 ⇒ 认得出「库侧没有读数」',
       [noRead.hasSidecar, noRead.state, kbNoReadingOf(noRead)], [false, '', true]);
    eq('⑬b 库侧没读数 ⇒ 合并态**不许**是 PASS（就算覆盖信号说成立也不许）',
       mergedState({ kbCovered: true, merged: [], kb: noRead }), '拒答');
    eq('⑬c 库侧没读数、模型侧有意见 ⇒ REVIEW（要人看，但绝不是放行）',
       mergedState({ kbCovered: true, merged: [F('全文', '合规', 'REVIEW')], kb: noRead }), 'REVIEW');
    // 反向对照：**有读数**时 PASS 照旧可达 —— 这条闸只挡「没读数」，不是把 PASS 一刀切掉
    const withRead = kbSideOf({ review: { state: 'PASS', issue_count: 0 } });
    eq('⑬d 反向对照：旁挂在、且 state=PASS ⇒ PASS 照旧可达（没被一刀切）',
       mergedState({ kbCovered: true, merged: [], kb: withRead }), 'PASS');
    // 反向对照：P0 快路自带读数（它压根不起链），不许算成「库侧没读数」
    const p0s = kbSideOf({ p0_fastpath: { rule_codes: ['H06'] }, issue_count: 1 });
    eq('⑬e 反向对照：P0 快路有读数 ⇒ 不算「库侧没读数」', kbNoReadingOf(p0s), false);
    // 卡里必须**说明白**：不许与「库侧 0 条」长得一样
    const rdNo = renderMerged([F('全文', '合规', 'REVIEW')],
      { state: 'REVIEW', kb: noRead, kbTextCount: 0 });
    eq('⑬f 「知识库侧本次未参与」要留着（在查证笔记里），且**不许**出现「知识库侧 0 条」',
       [/本次未参与/.test(rdNo.internalNotes), /知识库侧 0 条/.test(rdNo.internalNotes),
        rdNo.kbNoReading], [true, false, true]);
    eq('⑬f2 反向对照：这句也不上卡了（它属于「库侧/模型侧的口径读数」那一族）',
       [/本次未参与/.test(rdNo.block), /本次知识库侧没有读数/.test(rdNo.block)], [false, false]);
    eq('⑬g 要说明：只来自模型侧、无库内依据、**不得据此当 PASS**（仍在查证笔记里）',
       [/不得当通过依据/.test(rdNo.internalNotes), /不得据此当 PASS/.test(rdNo.internalNotes)],
       [true, true]);
  }

  // ⑭ ★★ 2026-10-08（Owner 拿一张图逼出来的两处）────────────────────────────────
  //   病灶一：**覆盖缺口那 1 条**既被 `COVERAGE_CATEGORY` 踢出 findings，又被
  //     `kbGap = kbN − txtN` 从 `issueCount` 里放回来 ⇒ 卡片对一个 `issue_count=1`
  //     的单子说「另有 1 条未并进本卡：PRD §5.3.3 规定问题数 **≥3** 时库侧只出分类汇总」——
  //     解释与事实不符，排查会被带到错方向。
  //   病灶二：模型侧**没跑成**与「跑了没报东西」都写成「模型侧 0 条」。
  {
    // —— 病灶一 ——
    const covK = kbSideOf({ review: { state: 'REVIEW', issue_count: 1,
      refusal: { state: 'NEEDS_INPUT', reason_code: 'coverage_not_covered',
                 coverage: { covered: false, rule_cited_unit_hits: 0 } } } });
    const rdCov1 = renderMerged([], { state: 'REVIEW', kb: covK, kbTextCount: 0 });
    eq('⑭a 覆盖缺口：那 1 条**不许**算进 kbGap（它不是「明细抠不出来」）',
       rdCov1.kbGap, 0);
    eq('⑭b 覆盖缺口：它**算**「需人工确认」⇒ 总数仍是 1（PRD §5.3.2 结论行不变）',
       [rdCov1.total, rdCov1.line], [1, '【审查结论：REVIEW】共发现 1 处需人工确认。']);
    eq('⑭c 覆盖缺口：卡里**不许**再出现「≥3 时库侧只出分类汇总」那句错误解释',
       /≥3 时库侧只出分类汇总/.test(rdCov1.block), false);
    eq('⑭d 覆盖缺口：「未报内容问题」＋「那 1 条就是覆盖缺口」要留着（在查证笔记里）',
       [/未报内容问题/.test(rdCov1.internalNotes),
        /上面那 1 条「需人工确认」就是它/.test(rdCov1.internalNotes)], [true, true]);
    eq('⑭d2 反向对照：这两句都不上卡',
       [/未报内容问题/.test(rdCov1.block), /就是它/.test(rdCov1.block)], [false, false]);
    // 反向对照①：**非**覆盖缺口、kbN=3、明细抠 0 ⇒ §5.3.3 那句**必须**还在（没被一刀切掉）
    const rdBig = renderMerged([], { state: 'REVIEW',
      kb: kbSideOf({ review: { state: 'REVIEW', issue_count: 3 } }), kbTextCount: 0 });
    eq('⑭e 反向对照：kbN=3、明细抠不全 ⇒ §5.3.3 的解释照旧（没被「不上卡」一刀切掉）',
       [/≥3 时库侧只出分类汇总/.test(rdBig.internalNotes), rdBig.kbGap], [true, 3]);
    // 反向对照②：**非**覆盖缺口、kbN=1、明细抠 0 ⇒ 不许说 ≥3，要按真实条数说
    const rdSmall = renderMerged([], { state: 'REVIEW',
      kb: kbSideOf({ review: { state: 'REVIEW', issue_count: 1 } }), kbTextCount: 0 });
    eq('⑭f 反向对照：kbN=1、明细抠不全 ⇒ 说「未达 3 条」而不是「≥3 只出汇总」',
       [/≥3 时库侧只出分类汇总/.test(rdSmall.internalNotes),
        /未达 3 条，不适用 PRD §5\.3\.3/.test(rdSmall.internalNotes)], [false, true]);
    // ══════════════════════════════════════════════════════════════════════
    // ⑭g–⑭i（2026-10-08 第五批）：**报告链接要按来源分档，不许把本地路径当链接**
    // ══════════════════════════════════════════════════════════════════════
    //   病灶：`report_url` 有两种 —— 飞书云文档（人点得开）与本地 `.md`（**人点不开**）。
    //   不分档就会把一条本地路径当链接贴给读者 ⇒ 库规：「一个点不开的链接比空格更坏」。
    const rdLoc = renderMerged([], { state: 'REVIEW',
      kb: kbSideOf({ review: { state: 'REVIEW', issue_count: 3,
        report_url: 'kb/l7/reports/x.review.md', report_url_kind: 'local_path' } }),
      kbTextCount: 0 });
    eq('⑭g 本地路径的报告 ⇒ 必须明说「你点不开」（不许冒充链接）',
       [/你点不开/.test(rdLoc.block), /本地文件路径/.test(rdLoc.block)], [true, true]);
    //   反向对照：**飞书云文档**必须原样贴出来，**不许**也被贴上「你点不开」。
    const rdDoc = renderMerged([], { state: 'REVIEW',
      kb: kbSideOf({ review: { state: 'REVIEW', issue_count: 3,
        report_url: 'https://momcozy-in.feishu.cn/docx/AAAABBBB',
        report_url_kind: 'feishu_docx' } }),
      kbTextCount: 0 });
    eq('⑭h 反向对照：飞书云文档 ⇒ 原样给链接、**不许**说「你点不开」',
       [/https:\/\/momcozy-in\.feishu\.cn\/docx\/AAAABBBB/.test(rdDoc.block),
        /你点不开/.test(rdDoc.block)], [true, false]);
    //   兜底：**旧版旁挂没有 kind** ⇒ 按形态判（http 算链接、其余算本地路径）。
    //   少了这条，没带 kind 的存量读数会被一律当成链接贴出去。
    const rdNoKind = renderMerged([], { state: 'REVIEW',
      kb: kbSideOf({ review: { state: 'REVIEW', issue_count: 3,
        report_url: '/Users/lute/x.review.md' } }),
      kbTextCount: 0 });
    eq('⑭i 兜底：没有 report_url_kind 时按形态判（非 http ⇒ 本地路径）',
       [/你点不开/.test(rdNoKind.block)], [true]);
    // ══════════════════════════════════════════════════════════════════════
    // ⑰a–⑰e（2026-10-09）：**PRD §5.3.4 的报告链接门槛 —— 问题数 ≥3 才出那一行**
    // ══════════════════════════════════════════════════════════════════════
    //   规则是 Owner 2026-10-08 的原话：「双轨按照 PRD ≧3 个问题输出报告链接到飞书文档」。
    //   触发条件**必须**是卡里那个数（`total`）—— 不是「并进来几条」，也不是
    //   「库侧明细抠不出来」。实测一单里三个数各不相同（19:08：total 12 ／ 并进来 7 ／ 旁挂 5）。
    const DOCX = 'https://momcozy-in.feishu.cn/docx/AAAABBBB';
    const mkN = (n, kb) => renderMerged(
      Array.from({ length: n }, (_, i) => ({ location: `画面 ${i}`, category: '本地化',
        severity: 'REVIEW', source: 'model', reason: 'x' })),
      { state: 'REVIEW', kb, kbTextCount: 0 });
    const withDocx   = kbSideOf({ review: { state: 'REVIEW', issue_count: 0, report_url: DOCX, report_url_kind: 'feishu_docx' } });
    const withoutAny = kbSideOf({ review: { state: 'REVIEW', issue_count: 0 } });

    const r3 = mkN(3, withDocx);
    eq('⑰a 问题数 ≥3 且有飞书文档 ⇒ **必须**出「查看完整问题清单与修改建议」那一行',
       [/查看完整问题清单与修改建议/.test(r3.block), r3.block.includes(DOCX)], [true, true]);
    // ★ 反向对照①：**<3 时不许出现**。PRD 说 1–2 条走逐条输出、不给链接 ——
    //   少了这一条，「≥3 才出」就退化成「一律都出」，门槛等于没有。
    const r2 = mkN(2, withDocx);
    eq('⑰b 反向对照：问题数 <3 ⇒ **一个链接行都不许有**（哪怕文档就在手边）',
       [/查看完整问题清单/.test(r2.block)], [false]);
    // ★ 反向对照②：≥3 但**拿不到**链接 ⇒ 不许编，也不许默默不给 —— 要说清是哪种拿不到。
    const r3n = mkN(3, withoutAny);
    eq('⑰c 反向对照：≥3 但没拿到链接 ⇒ 如实说「未拿到」并说清原因，不许编一个链接',
       [/查看完整问题清单与修改建议/.test(r3n.block), /本次未拿到报告链接/.test(r3n.block),
        /https?:\/\//.test(r3n.block)], [true, true, false]);
    // 门槛看的是 `total`，不是「并进来几条」：库侧另有 2 条没并进来 ⇒ total=3 ⇒ 必须出那一行
    const rGap = renderMerged(
      [{ location: '画面 0', category: '本地化', severity: 'REVIEW', source: 'model', reason: 'x' }],
      { state: 'REVIEW', kb: kbSideOf({ review: { state: 'REVIEW', issue_count: 2, report_url: DOCX, report_url_kind: 'feishu_docx' } }),
        kbTextCount: 0, model: { ok: true, findings: [] } });
    eq('⑰d 门槛看的是卡里那个数（total=1+2），不是「并进来几条」',
       [rGap.total, /查看完整问题清单/.test(rGap.block)], [3, true]);
    // 常数与库侧同名同口径 —— 钉住 3，改它必须同时改两边（库侧 `feishu_publish.py`）
    eq('⑰e 门槛常数与库侧同口径（PRD §5.3.4 / §8.3 / §17 三处都是 3）',
       [REPORT_LINK_MIN_ISSUES], [3]);
    // ★★ 2026-10-14（Owner：「修改建议的链接，预期放在『建议转』这行的上面，跟 PRD 对齐」）：
    //   **次序按 PRD 逐字核**（回源飞书 PRD wiki `NB55wAq8liEOdKkquL2cgtPEnmg` rev 36
    //   ＋ 本地 `kb/.work/prd.md`，两份一致）：
    //       结论行 → `· <大类>类问题：N 个` → `→ 查看完整问题清单…` → 动作行
    //   改前拼装写的是 `${line}${reportNote}\n${bodyText}` ⇒ **链接跑到汇总之前**，与 PRD 相反
    //   （Owner 截图当场指出：「跟 prd 对齐，你没改吗？」）。
    //   ⚠️ 2026-10-09 那条诉求**没有作废**：链接不许被埋在逐条之后（会落进可折叠区）。
    //      现在的次序里它紧跟汇总、仍在逐条**之上** ⇒ 两个诉求同时成立。
    //   ⚠️ 判据改钉**三件事的相对次序**，不再钉「在第几行」—— 后者绑死行号，
    //      任何一次次序/行数调整都会误红（而误红的判据比没有判据更坏）。
    eq('⑰f 次序照 PRD：汇总 在 链接 之前，链接 在 动作行 之前（且不埋在逐条之后）',
       [(() => {
         const ls = String(r3.block).split("\n").map((x) => x.trim());
         const iSum = ls.findIndex((l) => /^·/.test(l));
         const iLink = ls.findIndex((l) => /查看完整问题清单/.test(l));
         const iAct = ls.findIndex((l) => /^(建议转|请修改后重新提交)/.test(l));
         return iSum >= 0 && iLink > iSum && iAct > iLink;
       })()], [true]);
    //   ⑰f 的反向对照**不是夹具而是变异**：把 reportNote 挪回逐条之后 ⇒ ⑰f 必红（已实测）。
    // ══════════════════════════════════════════════════════════════════════
    // ⑱a–⑱d（2026-10-09）：**逐条「建议」必须来自两侧的真话，不许甩给人**
    // ══════════════════════════════════════════════════════════════════════
    //   Owner 原话：「守衡输出的建议都是『转对应负责人复核』。我期望的是：
    //   **知识库侧和模型侧都输出具体的修改建议**，而不是甩给人。」
    //   病灶：那一行原先是**硬编码常量**（'转对应负责人复核。'），两侧说了什么都被它盖掉。
    const itemOf = (f) => renderMergedItem(f, 0, { must: false });
    // ★ 2026-10-09：`建议` 标签如今**带加粗**（Owner 裁定「字段加粗保留」）⇒ 原先的
    //   `/ {3}建议：(.*)/` 抠出空串，把这组「建议内容对不对」的自证**全部误判成失败**。
    //   这组查的是**建议内容与标注**、与加粗无关 ⇒ 认两种写法。
    const sugOf = (f) => (itemOf(f).match(/ {3}\*{0,2}建议\*{0,2}：(.*)/) || [])[1] || '';
    const kbSug = sugOf({ category: '平台与促销', location: '第 3 行', source: 'kb', reason: 'x',
                          kb: { suggestionLine: '删掉「限时」二字，改为「活动期间」' } });
    eq('⑱a 库侧给了建议 ⇒ **原话照搬**（那是库规给的改法，可回源）',
       [kbSug], ['删掉「限时」二字，改为「活动期间」']);
    const mdSug = sugOf({ category: '本地化', location: '第 4 行', source: 'model', reason: 'x',
                          suggestion: '把整段译成中文' });
    // ★ 2026-10-13（Owner：「不要出现 知识库侧，模型侧」）：措辞改了，**信息一条没少** ——
    //   仍要照搬那句改法，仍要标明「无库内依据」「不是库规原文」。
    eq('⑱b 只有独立复核给 ⇒ 照搬**并标明来源**（否则会被当成库规要求）',
       [/把整段译成中文/.test(mdSug), /无库内依据的改法建议/.test(mdSug), /不是库规原文/.test(mdSug)],
       [true, true, true]);
    eq('⑱b2 反向对照：**那两个词**一个都不许再出现（卡面与报告共用这条渲染）',
       [/知识库侧/.test(mdSug + itemOf({ category: 'a', location: 'b', source: 'kb', reason: 'r' })),
        /模型侧/.test(mdSug + itemOf({ category: 'a', location: 'b', source: 'model', reason: 'r' }))],
       [false, false]);
    const noneSug = sugOf({ category: '本地化', location: '第 5 行', source: 'model', reason: 'x' });
    eq('⑱c ★ 两侧都没给 ⇒ **如实说没有**，不许用「转人复核」冒充一条建议',
       [/两侧都没给修改建议/.test(noneSug), /转对应负责人复核/.test(noneSug)], [true, false]);
    eq('⑱d ★ 反向对照：**任何一条**都不许再出现硬编码那句（它是这次要修的病灶）',
       [/转对应负责人复核/.test(itemOf({ category: 'a', location: 'b', source: 'model', reason: 'r', suggestion: 's' })),
        /转对应负责人复核/.test(itemOf({ category: 'a', location: 'b', source: 'kb', reason: 'r', kb: { suggestionLine: 's' } }))],
       [false, false]);
    // ★★ ⑱e：**库侧的建议有两条来路，缺一条就是半个修复。**
    //   正则抠逐条块（`kbFindingsOf` 下半段）与**结构化 `risk_items`**（这一段，⑯a 说它优先）。
    //   我第一版只补了正则那条 ⇒ 走引擎 JSON 时库侧的建议**照样被丢**，而 `r.suggestion`
    //   就在手边。这一条断言钉住第二条来路 ——「两个产出者只修了一个」是今天反复栽的形状。
    {
      const eng = { decision: { risk_items: [{
        risk_type: '平台与促销-绝对化', location: '正文第 3 行', reason: '用了最高级',
        suggestion: '删掉「最」字，改为「更」', action: 'review',
        evidence: { library: '措辞表达库 v0', article_no: 'W-1.16', excerpt: '静音', anchor: '#p3' } }] } };
      const kbE = kbFindingsOf('【审查结论：REVIEW】共发现 1 处需人工确认。', eng);
      eq('⑱e ★ 引擎 JSON 那条来路也必须带出库侧建议（只修正则那条 = 半个修复）',
         [kbE.findings[0]?.suggestionLine], ['删掉「最」字，改为「更」']);
    }
    // ══════════════════════════════════════════════════════════════════════
    // ⑮a–⑮c（2026-10-08 第六批）：**库侧条目要优先从引擎结构化 `risk_items` 取**
    // ══════════════════════════════════════════════════════════════════════
    //   病灶：纯逐行正则抠中文 ⇒ 引擎把逐条塞在 `summary` 一个字符串里时**一条都抠不到**
    //   ⇒ `basisLine=null` ⇒ 渲染层退回重建版「《知识库》（未给条款号）（锚点：—）」
    //   ⇒ 命中文字/条款号/锚点/**飞书直链**全丢（Owner 截图那条就是这么来的）。
    const chainshape = [
      '===== ③ 引擎结论 =====',
      JSON.stringify({ decision: { issue_count: 1, risk_items: [{
        risk_type: '原则性错误-禁区（库内反例条款）', location: '全文',
        reason: '库内反例条款 S-1.267（原则性错误）与本素材同源/同题材：…',
        action: 'review',
        evidence: { library: '内部正负样本库', article_no: 'S-1.267',
          anchor: '#负面样本/RECX/具体原因/分析', source_sha256: 'abc123',
          excerpt: '【原则性错误】视频 图 1 主标题醒目柔和…',
          l0_entry_url: 'https://momcozy-in.feishu.cn/base/APP?table=TBL&record=RECX' } }] } }, null, 1),
      '===== ③b 转述模板 =====',
      '1.【原则性错误-禁区（库内反例条款）】全文',
      '   依据：《内部正负样本库 v0》第 S-1.267 条（链接：kb/l3/…）',
    ].join('\n');
    const kf = kbFindingsOf(chainshape);
    eq('⑮a 链回答里带引擎 JSON ⇒ 必须走结构化（条款号＋锚点＋飞书直链都在）',
       [kf.findings.length,
        kf.findings[0]?.kb?.article_no,
        /feishu\.cn\/base/.test(String(kf.findings[0]?.kb?.entry_url ?? ''))],
       [1, 'S-1.267', true]);
    const blk15 = renderMerged(mergeFindings(kf.findings, []).items,
      { state: 'REVIEW', kb: kbSideOf({ review: { state: 'REVIEW', issue_count: 1 } }),
        kbTextCount: kf.findings.length }).block;
    eq('⑮b 端到端：卡里的「依据」行带飞书直链，且**不许**出现重建版的「（未给条款号）」',
       [/feishu\.cn\/base/.test(blk15), /（未给条款号）/.test(blk15)], [true, false]);
    // 反向对照：**没有** risk_items 的回答必须原样退回逐行正则（不许因为换了条路就少报）
    const noJson = '1.【措辞表达】全文\n   原因：命中「限时」\n   依据：《措辞表达库 v0》第 W-1.16 条';
    const kf2 = kbFindingsOf(noJson);
    eq('⑮c 反向对照：没有引擎 JSON ⇒ 退回逐行正则，照旧抽得到（不是静默空）',
       [kf2.findings.length, kf2.findings[0]?.category], [1, '措辞表达']);
    // ══════════════════════════════════════════════════════════════════════
    // ⑯a–⑯b（2026-10-08 第七批）：**链直接带回的引擎 JSON = 主路**
    // ══════════════════════════════════════════════════════════════════════
    //   为什么它是主路：`answer` 是 headless agent 自己组织的**散文**（措辞会被改写、
    //   ≥3 条时按 PRD §5.3.3 连逐条行都没有），而条款号/锚点/命中片段/飞书直链
    //   **只在那份 JSON 里**。实测教训：我曾拿「引擎原始 stdout」当样本验，全绿，
    //   而线上走的是 `answer` ⇒ 修复没生效（Owner 09:22 那张卡）。
    const engObj = { decision: { issue_count: 1, risk_items: [{
      risk_type: '品牌一致性-禁区（库内反例条款）', location: '全文',
      reason: '库内反例条款 S-1.259（品牌一致性）与本素材同源/同题材：…', action: 'review',
      evidence: { library: '内部正负样本库', article_no: 'S-1.259',
        anchor: '#正面和负面样本/REC1/原文反馈', source_sha256: 'deadbeef',
        excerpt: '【品牌一致性】文案 1.挂式衣架：磨砂亚克力材质,搭配透明防滑条。',
        l0_entry_url: 'https://momcozy-in.feishu.cn/base/APP?table=TBL&record=REC1' } }] } };
    // 关键：`answer` **故意不含 JSON**（模拟模型改写过措辞的真实情形）
    const kf3 = kbFindingsOf('（回答里没有 JSON —— 模型自己组织的散文）', engObj);
    eq('⑯a 链带回引擎 JSON ⇒ 即使回答里没有 JSON，也必须出条款号＋锚点＋飞书直链',
       [kf3.findings.length, kf3.findings[0]?.kb?.article_no,
        /feishu\.cn\/base/.test(String(kf3.findings[0]?.kb?.entry_url ?? ''))],
       [1, 'S-1.259', true]);
    const blk16 = renderMerged(mergeFindings(kf3.findings, []).items,
      { state: 'REVIEW', kb: kbSideOf({ review: { state: 'REVIEW', issue_count: 1 } }),
        kbTextCount: kf3.findings.length }).block;
    eq('⑯b 端到端：卡里依据行带飞书直链，且**不许**出现「（未给条款号）」',
       [/feishu\.cn\/base/.test(blk16), /（未给条款号）/.test(blk16)], [true, false]);
    // 反向对照：**engine 为 null** 时不许崩、也不许少报 —— 仍走回答里挖那条路
    eq('⑯c 反向对照：engine=null ⇒ 仍走原路（回答里挖），不崩、不空',
       [kbFindingsOf(noJson, null).findings.length], [1]);
    // —— 病灶二 ——
    const kbOne = kbSideOf({ review: { state: 'REVIEW', issue_count: 1 } });
    const item = [F('全文', '合规', 'REVIEW')];
    const rdFail = renderMerged(item, { state: 'REVIEW', kb: kbOne, kbTextCount: 1,
      model: { ok: false, findings: [], raw: '', ms: 900, error: '输出里没有 JSON 数组' } });
    eq('⑭g 模型侧没跑成 ⇒ 写「没跑成」，**不许**写「模型侧 0 条」（在查证笔记里）',
       [/模型侧 \*\*没跑成\*\*（输出里没有 JSON 数组）/.test(rdFail.internalNotes),
        /模型侧 0 条/.test(rdFail.internalNotes), rdFail.modelFailed], [true, false, true]);
    eq('⑭g2 且要写明「这不等于模型侧看过、没问题」',
       /这不等于「模型侧看过、没问题」/.test(rdFail.internalNotes), true);
    const rdOk = renderMerged(item, { state: 'REVIEW', kb: kbOne, kbTextCount: 1,
      model: { ok: true, findings: [], dropped: [], ms: 900 } });
    eq('⑭h 反向对照：模型侧**跑成且 0 条** ⇒ 照旧写「模型侧 0 条」（不许一刀切）',
       [/模型侧 0 条/.test(rdOk.internalNotes), /没跑成/.test(rdOk.internalNotes), rdOk.modelFailed],
       [true, false, false]);
    eq('⑭i 反向对照：模型侧挂了**不许**改结论行（结论仍由库侧定）',
       [rdFail.line, rdFail.total], [rdOk.line, rdOk.total]);
    // 不给 model（老调用方）时不许凭空说「没跑成」
    const rdNoModel = renderMerged(item, { state: 'REVIEW', kb: kbOne, kbTextCount: 1 });
    eq('⑭j 反向对照：不传 model ⇒ 不许凭空说「没跑成」（向后兼容）',
       rdNoModel.modelFailed, false);
  }

  // ⑮ ★★ 2026-10-08（Owner 同意 ②）：**「库忙」不许写成「没下文」** ──────────────────
  //   病灶：卡原先只写「本次没有知识库三态结论…下一步：先把库侧恢复（跑层/日更）再重审」——
  //   读者读到的是**死局 + 一份他做不了的作业**。而这一单其实**已经进了补发队列**。
  {
    const busy = kbSideOf({ review: { state: 'NEEDS_INPUT', issue_count: 0,
      refusal: { state: 'NEEDS_INPUT', reason_code: 'claim_busy' } } });
    eq('⑮a claim_busy 被认成「库忙」', [busy.refused, busy.reason], [true, 'claim_busy']);
    const rdBusy = renderMerged([], { state: 'NEEDS_INPUT', kb: busy, kbTextCount: 0 });
    eq('⑮b 库忙卡要说「会自己重跑」＋「1 小时内最多 5 次」',
       [/会自己重跑/.test(rdBusy.block), /1 小时内最多 5 次/.test(rdBusy.block), rdBusy.claimBusy],
       [true, true, true]);
    eq('⑮c 库忙卡**不许**把「跑层/日更」当送审人的作业',
       [/先把库侧恢复（跑层\/日更）再重审/.test(rdBusy.block),
        /你不需要做什么/.test(rdBusy.block)], [false, true]);
    eq('⑮d **不许**承诺「会另行告知」—— 实测 deadDrop 只落死信、不通知任何人',
       /另行告知|会通知你|会告知你/.test(rdBusy.block), false);
    // 反向对照：**别的**拒答（如供给链不新鲜）**不许**被说成「已排队、会自动补跑」
    const stale = kbSideOf({ review: { state: 'NEEDS_INPUT', issue_count: 0,
      refusal: { state: 'NEEDS_INPUT', reason: '供给链不新鲜' } } });
    const rdStale = renderMerged([], { state: 'NEEDS_INPUT', kb: stale, kbTextCount: 0 });
    eq('⑮e 反向对照：非库忙的拒答 ⇒ 仍写「跑层/日更」，且**不许**说「会自己重跑」',
       [/先把库侧恢复（跑层\/日更）再重审/.test(rdStale.block),
        /会自己重跑/.test(rdStale.block), rdStale.claimBusy], [true, false, false]);
  }

  // ★★ 2026-10-12（库侧 Owner 裁定 `issue_count` 只算库内依据）：
  //   数改小之后，候选线索必须在卡上有一句；没有候选时**一个字都不许加**（反向对照）。
  {
    const _side = (cn) => kbSideOf({ review: Object.assign(
      { state: 'REVIEW', issue_count: 2 },
      Number.isFinite(cn) ? { candidate_count: cn } : {}) });
    const _mk = (cn) => renderMerged(
      [{ location: '全文', category: '功效宣称', severity: 'REVIEW', source: 'model', reason: 'x' }],
      { state: 'REVIEW', kb: _side(cn), kbTextCount: 2, model: { ok: true, findings: [] } });
    const rCand = _mk(3);
    const rNone = _mk(0);
    eq('㉑a 库侧报了非权威候选 ⇒ 必须说出条数，且写明「不构成依据」（在查证笔记里）',
       [/另有 \*\*3 条非权威候选线索\*\*/.test(rCand.internalNotes),
        /不构成依据/.test(rCand.internalNotes)], [true, true]);
    eq('㉑a2 反向对照：候选提示也不上卡（同一族口径读数）', /非权威候选/.test(rCand.block), false);
    eq('㉑b 反向对照：没有候选（或旧旁挂没这个键）⇒ **一个字都不加**',
       [/非权威候选/.test(rNone.internalNotes), /非权威候选/.test(_mk(undefined).internalNotes)],
       [false, false]);
    eq('㉑c 候选条数**不许进算术**：抬头与 kbGap 与「有没有候选」无关',
       [rCand.total, rNone.total, rCand.kbGap, rNone.kbGap],
       [rNone.total, rNone.total, rNone.kbGap, rNone.kbGap]);
    // ★★ ㉑d/㉑e（2026-10-12，Owner「同意加」那行候选提示之后补的结构判据）：
    //   库侧上一批真踩过这个坑 —— 把候选说明接在 PRD 那句**同一行**上，
    //   而 `conforms()` 是 `$` 锚定、`LINE_RE` 取到行尾 ⇒ 判 false、卡面标题不再是 PRD 那句。
    //   ⇒ 那行候选提示**必须独立成行**。这里用**守衡自己的**尺子判，不另抄正则。
    const _vline = String(rCand.block).split('\n').find((l) => l.includes('【审查结论：')) || '';
    eq('㉑d 候选提示必须**独立一行**：PRD 那句仍逐字合规、且那句里不许出现候选字样',
       [prd53Conforms(_vline).ok, /非权威候选/.test(_vline)], [true, false]);
    const _glued = '【审查结论：REVIEW】共发现 3 处需人工确认。（另有 3 条非权威候选线索，不构成依据）';
    eq('㉑e **反向对照**：把候选提示粘到结论行尾巴上 ⇒ 合规判据必须红（这正是库侧踩过的写法）',
       [prd53Conforms(_glued).ok, prd53Conforms(_vline).why === _glued], [false, false]);
  }

  console.log(`\n自证：通过 ${pass} / 失败 ${bad.length}`);
  return bad.length ? 1 : 0;
}


/* ═══════════ 库侧：从链的结论原文里抽 findings 与覆盖信号 ═══════════ */

/**
 * 库里那条「覆盖缺口」不是**内容问题** —— 它是库在说「我管不到这个题材」。
 * 合并时要把它与真 findings 分开：混在一起会让「问题数量」虚高，
 * 而人看到的是一张写着「发现 1 处问题」却指不出内容问题的单子。
 */
export const COVERAGE_CATEGORY = '覆盖';

/**
 * 从链的结论原文里把**引擎 JSON** 挖出来，拿它的 `risk_items` 当库侧条目（结构化）。
 *
 * 返回 `null` = 「这条路没走通」⇒ 调用方原样退回逐行正则（**不许静默少报**）。
 *
 * 为什么值得单独一条路（2026-10-08 实测，见 `kbFindingsOf` 抬头）：
 *   `risk_items[].evidence` 同时带着 **条款号 / 锚点 / source_sha256 / 命中片段 /
 *   `l0_entry_url`（飞书源直链）** —— 这五样正是「依据」那一行要的东西，
 *   而**逐行正则只捞得到中文**，捞不到其中任何一项。
 */
function _kbFromEngineJson(answer, engine = null) {
  const s = String(answer ?? '');
  // ★★ 2026-10-08（第七批）：**优先用链直接带回来的那份引擎 JSON**（`engine` 参数）。
  //   为什么它是主路而不是备路：`answer` 是 **headless agent 自己组织的散文** ——
  //   措辞会被模型改写，≥3 条时按 PRD §5.3.3 还**没有逐条行**；而结构化字段
  //   （条款号 / 锚点 / `source_sha256` / 命中片段 / `l0_entry_url`）**只在这份 JSON 里**。
  //   ⇒ 链路已把它原样落成机读件（`kb/.work/last_engine_out.json`）。走它就不必猜措辞。
  //   从回答里挖那条**保留**（历史形状仍认、老旁挂仍能用）。
  let obj = (engine && typeof engine === 'object') ? engine : null;
  // ★ 用**花括号配对**提取，不用 `JSON.parse(s.slice(i))` ——
  //   链的回答是「模板行 + 引擎 JSON + 转述模板段」，**JSON 后面还有文本** ⇒
  //   直接 parse 到结尾会因为尾部文本失败，结果是**一条都解析不出来**（静默退回正则）。
  for (let i = obj ? -1 : s.indexOf('{'); i !== -1; i = s.indexOf('{', i + 1)) {
    let depth = 0, inStr = false, esc = false, end = -1;
    for (let j = i; j < s.length; j += 1) {
      const c = s[j];
      if (inStr) {
        if (esc) esc = false;
        else if (c === '\\') esc = true;
        else if (c === '"') inStr = false;
        continue;
      }
      if (c === '"') { inStr = true; continue; }
      if (c === '{') depth += 1;
      else if (c === '}') { depth -= 1; if (depth === 0) { end = j; break; } }
    }
    if (end === -1) continue;
    try { obj = JSON.parse(s.slice(i, end + 1)); break; } catch { /* 这个 { 不是起点，继续 */ }
  }
  if (!obj || typeof obj !== 'object') return null;
  const dec = (obj.decision && typeof obj.decision === 'object') ? obj.decision : obj;
  const rows = Array.isArray(dec.risk_items) ? dec.risk_items : null;
  if (!rows || !rows.length) return null;
  const out = []; let coverage = null;
  for (const r of rows) {
    if (!r || typeof r !== 'object') continue;
    const ev = (r.evidence && typeof r.evidence === 'object') ? r.evidence : {};
    const art = ev.article_no || null;
    const anc = ev.anchor || null;
    const exc = String(ev.excerpt || r.original_text || '').trim().slice(0, 120);
    // 直链：`l0_entry_url` 优先；否则 `evidence_url` 里**只认 http(s)**（本地路径不是链接）
    const link = String(ev.l0_entry_url || '').trim()
      || (/^https?:\/\//i.test(String(r.evidence_url || '')) ? String(r.evidence_url).trim() : '');
    // 依据行：结构化字段拼；**取不到的格子不编**（宁可少一项，不许造）
    const basisLine = `《${ev.library || '知识库'}》${art ? `第 ${art} 条` : '（未给条款号）'}`
      + (exc ? ` ← 命中「${exc}」` : '')
      + (anc ? `｜锚点：${anc}` : '')
      + (link ? `｜原始出处：${link}` : '');
    const rt = String(r.risk_type || '未分类');
    const dash = rt.indexOf('-');
    // ★★ 2026-10-09（② 自证阶段查出来的**真 bug**，不是新功能）：
    //   `category` **优先读引擎自己给的字段**，「按 `-` 拆 `risk_type`」只作回落。
    //   实测引擎的覆盖行是 `{risk_type:'覆盖缺口', category:'覆盖'}` —— `risk_type` 里**没有连字符**，
    //   于是拆出来的类目是 `覆盖缺口`，**不匹配 `COVERAGE_CATEGORY`（`'覆盖'`）**
    //   ⇒ 这一条被**误归进 `findings`**、`coverage` 恒为 `null`。
    //   代价不只是归类好不好看：`coverage.reasonLine` 是**唯一**渲染「库内命中（读数）」的位置
    //   ⇒ Owner 要的「命中原文 + 飞书链接」**永远不会出现**。
    //   ⚠️ 上一轮我拿**合成样本**"验过"这条路，样本里的 `category` 是我自己填的，
    //      **恰好绕开了这个 bug** ⇒ 那次"验证通过"是假的。教训：**样本不对，结论就是假的**；
    //      验一条来路必须喂**真实产出物**（`kb/.work/last_engine_out.json` / `/tmp/_ev*.out`）。
    //   ⇒ 口径：**引擎给了就照搬**，没给才按 `risk_type` 拆（老形状仍然认）。
    const catExplicit = String(r.category || '').trim();
    const category = catExplicit || (dash > 0 ? rt.slice(0, dash) : rt).trim();
    const sub = dash > 0 ? rt.slice(dash + 1).trim()
      : (catExplicit && rt.startsWith(catExplicit) ? rt.slice(catExplicit.length).trim() : '');
    const item = {
      location: String(r.location || '全文').slice(0, 120) || '（未给位置）',
      category,
      sub,
      severity: String(r.action || '').toLowerCase() === 'block' ? 'BLOCK' : 'REVIEW',
      reason: String(r.reason || '').slice(0, 300),
      basis: 'kb', basisLine, reasonLine: String(r.reason || '').slice(0, 300),
      // ★ 2026-10-09：**引擎 JSON 这条来路也要带 `suggestionLine`**。
      //   库侧条目有**两条来路**：正则抠逐条块（`kbFindingsOf` 下半段）与
      //   **结构化 `risk_items`**（这一段，⑯a 说它**优先**）。
      //   我只补了正则那条 ⇒ 走引擎 JSON 时库侧的建议**照样被丢**，
      //   而 `r.suggestion` 就在手边（`review_engine.py:321` 读的正是这个字段）。
      //   教训：补一条「搬运」时要把**这个字段的每一条来路**都数一遍 ——
      //   今天的病全是同一个形状（两个产出者，只修了一个）。
      suggestionLine: String(r.suggestion || '').trim() || null,
      kb: { article_no: art, anchor: anc, entry_url: link || null,
            source_sha256: ev.source_sha256 || null, library: ev.library || null, basisLine,
            suggestionLine: String(r.suggestion || '').trim() || null },
    };
    if (item.category === COVERAGE_CATEGORY) { coverage ??= item; continue; }
    out.push(item);
  }
  return { findings: out, coverage };
}

/**
 * Owner 要的那一块：**命中原文 + 飞书链接**。
 *
 * ⚠️ 为什么单独一个函数、而不是塞进 `coverage.reasonLine`（**这是我今天栽的第二个坑**）：
 *   我第一版把它挂在 `coverage` 上，然后拿合成样本"验过" ⇒ 看着是对的。
 *   可 `agent.mjs:762-768` 里 **`kb.coverage` 压根没被用过** ——
 *   `mergeFindings(kb.findings, model.findings)` 只吃 `findings`，
 *   `renderMerged` 里那条 `covNote` 是**写死的一句话**，不是 `coverage.reasonLine`。
 *   ⇒ 我把字渲染进了**一个没人读的字段**：跑得通、断言绿、卡上一个字都没有。
 *   教训（第三次同一个形状）：**改产出者之前先读消费者**；「我这边验过」不等于「人看得见」。
 *   ⇒ 现在它是一等字段 `kbHitsBlock`，由 `renderMerged` 直接印进卡片正文。
 *
 * 定性（必须跟着一起印，不许省）：
 *   这是**读数**，不是判定依据 —— 命中大多是**别人的素材样本 / 外部材料**，
 *   不构成该素材的合规依据 ⇒ 标注里写死「不得据此当 PASS 依据」。
 *   **它不参与任何判定**（三态一个字不改）。
 *
 * @param {object|null} engine 引擎最终 JSON（`kb/.work/last_engine_out.json`）
 * @returns {string|null} 要印的 markdown 块；没有读数时返回 `null`（**不编**）
 */
export function kbHitsBlockOf(engine) {
  const hits = (engine && typeof engine === 'object')
    ? (((engine.evidence_meta || {}).kb_hits) || null) : null;
  if (!Array.isArray(hits) || !hits.length) return null;
  const rows = hits.slice(0, 8).map((h, i) => {
    const ex = String(h?.excerpt || '').trim();
    const url = String(h?.url || '').trim();
    const sha = String(h?.source_sha256 || '').trim();
    return `${i + 1}. \`${h?.anchor || '(无锚点)'}\`｜BM25 ${h?.bm25 ?? '?'}｜${h?.kb_type || '未标类型'}`
      + (h?.article_no ? `｜条款号 ${h.article_no}` : '')
      + `\n   命中原文（逐字）：${ex || '**该单元没给片段**'}`
      + `\n   飞书直链：${url || '**取不到直链**（该单元没有 L0 直链，别去找）'}`
      + (sha ? `\n   指纹 source_sha256：\`${sha.slice(0, 16)}…\`` : '');
  }).join('\n');
  const more = hits.length > 8 ? `\n（只列前 8 条，本次共 ${hits.length} 条）` : '';
  return `【库内命中（读数）】本次检索命中 ${hits.length} 条，逐条列出**原文与飞书直链**：\n`
    + `${rows}${more}\n`
    + '⚠️ 上面是**读数**：命中的大多是**别人的素材样本 / 外部材料，不是覆盖本素材的条款**，'
    + '**不得据此当 PASS 依据**，也不得当作「本素材已合规」的证明。';
}

/**
 * 从 PRD §5.3 的**逐条块**里抽库侧 findings。
 *
 * 口径：`^\d+.【类目-子类】位置…`（§5.3.2 / §5.3.3 的格式，由 `render_summary` 产出，
 * 并由 `tools/verify_cards.mjs` 的 W 段与 `l7_integrity.py` 钉住）。
 * **类目为「覆盖」的那条不算 finding**，单独返回在 `coverage` 里。
 *
 * @param {string} answer 链给的结论原文
 */
export function kbFindingsOf(answer, engine = null) {
  // ══════════════════════════════════════════════════════════════════════════
  // ★★ 2026-10-08（第六批）：**结构化优先 —— 先找引擎 JSON 的 `risk_items`**。
  // ══════════════════════════════════════════════════════════════════════════
  // 病灶（Owner 报「依据里没有飞书链接 / 有的条目印成《知识库》（未给条款号）（锚点：—）」）：
  //   本函数原先是**纯逐行正则**抠中文答案。而引擎的逐条明细有**两种落法**：
  //     · 链的模板段把它**展开成真行** ⇒ 正则抠得到；
  //     · 引擎 JSON 里它在 `summary` 的**一个字符串**里（换行是转义的 `\n`）⇒ **一行都抠不到**。
  //   抠不到 ⇒ `basisLine = null` ⇒ 渲染层退回重建版（`《知识库》（未给条款号）（锚点：—）`）
  //   ⇒ **命中文字、条款号、锚点、飞书直链全丢**。这解释了「私聊有、群里没有」的飘忽：
  //   它不是群聊坏了，是**这一条的明细有没有被展开成真行**碰运气。
  //   ★ 顺带修掉另一半：库侧判到 **≥3 条**时 PRD §5.3.3 只出分类汇总、**不出逐条**，
  //     正则永远抠不出 —— 而 `risk_items` 是**结构化且完整**的，与条数无关。
  // 口径（两条，缺一条都不算修好）：
  //   ① 只有**真的解析出 `risk_items` 且非空**才走这条路；解不出/为空 ⇒ 原样退回逐行正则
  //      （**不许**因为换了条路就少报东西）；
  //   ② `依据` 行由**结构化字段**拼：库名 + 条款号 + 命中片段 + 锚点 + **L0 飞书直链**
  //      （直链优先 `evidence.l0_entry_url`，其次 `evidence_url` 里像 http 的那个；
  //      两者都没有就**不编**，如实不带链接）。
  const structured = _kbFromEngineJson(answer, engine);
  // ★ 2026-10-09：命中读数**两条来路都要带**（结构化 / 逐行正则）——
  //   它与「明细从哪儿抠出来」无关：数据都在**同一份** `engine` 里。
  //   原先只挂在 `coverage` 上（且只在覆盖缺口时才挂）⇒ 常规单子一个字都没有。
  if (structured) return { ...structured, kbHitsBlock: kbHitsBlockOf(engine) };

  const out = []; let coverage = null;
  const lines = String(answer ?? '').split('\n');
  for (let i = 0; i < lines.length; i += 1) {
    const line = lines[i];
    const m = /^\s*\d+[.、]\s*【([^】]{1,40})】\s*(.*)$/.exec(line);
    if (!m) continue;
    // ★ 2026-10-08：把库侧那条**已经产好的 `依据` 行原样带下来**。
    //   为什么必须搬而不是重建：库侧 `_evidence_line` 现在会带
    //   **逐字命中文案 + 飞书源直链（L0 entry_url）**，而 JS 这一侧**没有** L0 定位能力
    //   （那是 Python 的 `feishu_publish.l0_locate`）。重建只能造出一个更差的版本
    //   （「《知识库》W-1.16（锚点：#…）」—— 点不开、也没说命中什么）。
    //   这就是 §2.4 的「搬是搬」：**能搬就别造**。
    // ★ 逐行抓库侧那两格（原因 / 依据）——**两格都要**：
    //   只抓依据的话，「原因」会退回成位置文字（实测卡片上印的就是
    //   「原因：全文，静音程度夸大…」——那是**位置**，不是原因）。
    let basisLine = null; let reasonLine = null; let suggestionLine = null;
    for (let j = i + 1; j < Math.min(i + 8, lines.length); j += 1) {
      if (/^\s*\d+[.、]\s*【/.test(lines[j])) break;   // 到下一条了就停，别串行
      const b = /^\s*\*{0,2}依据\*{0,2}：\s*(.+)$/.exec(lines[j]);
      if (b) { basisLine = b[1].trim(); continue; }
      const rr = /^\s*\*{0,2}原因\*{0,2}：\s*(.+)$/.exec(lines[j]);
      if (rr) { reasonLine = rr[1].trim(); continue; }
      // ★ 2026-10-09：**「建议」也要抠** —— 库侧 review_engine.py 本来就有 suggestion，
      //   而我们只抠了原因/依据两行，把它丢了 ⇒ 卡片上那一行只能印硬编码的「转对应负责人复核」。
      //   库侧对「没有建议」是诚实的（写「（来源未给修改建议）」）—— 照搬它，别替它编。
      const sg = /^\s*\*{0,2}建议\*{0,2}：\s*(.+)$/.exec(lines[j]);
      if (sg) suggestionLine = sg[1].trim();
    }
    const tag = m[1].trim();
    const dash = tag.indexOf('-');
    const category = (dash > 0 ? tag.slice(0, dash) : tag).trim();
    const sub = dash > 0 ? tag.slice(dash + 1).trim() : '';
    const item = { location: m[2].trim().slice(0, 120) || '（未给位置）', category, sub,
                   severity: /必须修改/.test(String(answer)) ? 'BLOCK' : 'REVIEW',
                   reason: m[2].trim().slice(0, 300), basis: 'kb', suggestionLine,
                   basisLine, reasonLine };
    if (category === COVERAGE_CATEGORY) { coverage ??= item; continue; }
    out.push(item);
  }
  return { findings: out, coverage, kbHitsBlock: kbHitsBlockOf(engine) };
}

/**
 * 库侧的**覆盖信号** —— 从结论原文里认。
 *
 * ⚠️ 这是一个**口径偏弱**的判据，我把弱点写在明处：真正的读数在
 *    `kb/.work/last_review_result.json` 的 `refusal.reason_code` 里，
 *    而它**没有随链的返回传到内核这一层**。所以这里退而认我们自己代码产出的那句话。
 *    两个标记都出自 `with_kb_evidence.py`，改那边必须同时改这里 ——
 *    这条配对由 `--selftest` 的 ⑩ 守着（喂坏样本必须判成「没覆盖」）。
 *
 * ★ 它的方向是**保守**的：认不出来时判「没覆盖」⇒ 到不了 PASS。
 *   判错的代价是多一次人工确认，不是放行。
 */
export function kbCoveredOf(answer) {
  const s = String(answer ?? '');
  if (s.includes('coverage_not_covered') || s.includes('覆盖判据不成立')) return false;
  return true;
}

/**
 * 知识库侧的**结构化读数** —— 结论与条数一律从这里取，**不再靠正则抠中文答案**。
 *
 * 两个来源（按路径选，互斥）：
 *   · `res.p0_fastpath`  —— P0 快路：确定性匹配，命中即 BLOCK（PRD §6.6），条数 = `res.issue_count`
 *   · `res.review`       —— 评审链：机读旁挂 `kb/.work/last_review_result.json`
 *                           （`kb/l8/review_run.sh` 从引擎 JSON 原样落盘；本工具侧
 *                            `readReviewSidecar()` 带「必须晚于本次起链时刻」的新鲜度守卫）
 *
 * ★ 为什么必须新增（2026-10-07 实测缺陷，已复现）：
 *   库侧 findings 原先**只从答案文本里正则抠**（`kbFindingsOf`，只认 `1.【类别-子类】位置…`）。
 *   而 PRD §5.3.3 规定 **问题数 ≥3 时库侧只出分类汇总、不出逐条** ⇒
 *   **库侧只要判到 ≥3 条，就会被读成 0 条**。实测两条真素材：
 *     · 「…已获得 FDA 批准，适合所有胸型」→ 库侧 **2** 条 ⇒ 抽到 2 条 ✅（结论保住 BLOCK）
 *     · 「…已通过 FDA 批准，完全无痛，模拟婴儿吸吮」→ 库侧 **3 条 P0（H06/H07/H09，BLOCK）**
 *       ⇒ 抽到 **0 条** ⇒ 合并态被改写成 **REVIEW**（**红线被降级**）
 *   ⇒ 计数与结论**一律以结构化字段为准**；文本抽取只用来补「逐条明细」，缺了要**看得见**。
 *
 * @returns {{source:string, hasSidecar:boolean, state:string, issueCount:number|null,
 *            refused:boolean, reason:string, ruleCodes:Array<string>, reportUrl:string|null}}
 */
export function kbSideOf(res) {
  const r = (res && typeof res === 'object') ? res : null;

  // ── ① P0 快路：结论由模式表定（命中即 BLOCK），不适用置信度分流 ──
  if (r && r.p0_fastpath && typeof r.p0_fastpath === 'object') {
    const n = Number(r.issue_count);
    return {
      source: 'p0_fastpath', hasSidecar: true, state: 'BLOCK',
      issueCount: Number.isFinite(n) ? n : null,
      refused: false, reason: '',
      ruleCodes: Array.isArray(r.p0_fastpath.rule_codes) ? r.p0_fastpath.rule_codes : [],
      reportUrl: String(r.report ?? '').trim() || null,
    };
  }

  // ── ② 评审链：机读旁挂 ──
  const rev = (r && r.review && typeof r.review === 'object') ? r.review : null;
  const raw = String(rev?.state ?? rev?.decision ?? '').trim().toUpperCase();
  const state = ['PASS', 'REVIEW', 'BLOCK', 'NEEDS_INPUT'].includes(raw) ? raw : '';
  const n = Number(rev?.issue_count);
  const ref = (rev?.refusal && typeof rev.refusal === 'object') ? rev.refusal : null;
  // ★★ 判「拒答」只认**顶层 `state`**，不认「有没有 `refusal` 字段」（2026-10-07 当天收紧）──
  //   为什么（当天实测把它逼出来了，素材「这条展会物料能不能发：M6 吸奶器附赠收纳袋…」）：
  //     引擎对**覆盖缺口**（`coverage_not_covered`）的形状是
  //       `state = REVIEW` ＋ `refusal.state = NEEDS_INPUT`（后者是**依据侧** review.py 的状态），
  //     而 `with_kb_evidence.py` 那句注释是明确的：
  //       「★ 这里如实写 REVIEW：**下游（飞书落表 / 守衡转述）读的是这个字段**。」
  //   ⇒ 顶层 `state` 才是引擎的**答案**；`refusal` 是**出处/原因**。
  //   第一版写成「有 refusal 就算拒答」（还带一条"只认 reason_code 会漏"的理由）——
  //   那条理由对**供给链超期**那类是成立的（它只有中文 reason），
  //   但它同时把**故意给 REVIEW** 的覆盖缺口也改判成 NEEDS_INPUT ⇒ **判据过宽**。
  //   收紧后：超期那类顶层 state 本来就是 `NEEDS_INPUT` ⇒ 该修的一件不少。
  const refused = state === 'NEEDS_INPUT';
  return {
    source: 'chain', hasSidecar: !!rev, state,
    issueCount: Number.isFinite(n) ? n : null,
    refused,
    // 覆盖缺口**不是拒答**：结论仍是 REVIEW，但要单独说明它的含义
    // （「库对该题材没有可依据的条款」⇒ 转人工看覆盖，**不是**发现了内容问题）。
    coverageGap: String(ref?.reason_code ?? '') === 'coverage_not_covered'
      || (ref?.coverage || {}).covered === false || false,
    reason: String(ref?.reason_code ?? ref?.reason ?? '').slice(0, 80),
    ruleCodes: [],
    // ★★ 2026-10-09 晚（Owner「8 条还在平铺」的真因，三个 bug 叠在一起）：
    //
    //   库侧**其实建了真文档**，但它在 `publish.docx` 里，而我们只读 `report_url` ——
    //   而 `report_url` 指的是**本地 `.md` 路径**（人点不开）：
    //     `report_url    = "kb/l7/reports/20261009-125549.review.md"`
    //     `publish.docx  = "https://momcozy-in.feishu.cn/docx/MQsxdnFPjoFEzPx5BCtcJyFunyf"`  ← 真文档
    //   后果三连：① 我们以为「库侧给了链接」⇒ **跳过自己建报告**；
    //             ② 卡里那行印的是「本地文件路径，你点不开」；
    //             ③ 而分流判据要求**可点的 http 链接** ⇒ 判成没有链接 ⇒ **退回逐条平铺**。
    //
    //   修法：**优先取 `publish.docx`**（那才是人点得开的那个），`report_url` 只作兜底。
    //   `report_url_kind` 也据此如实标 —— 它是 `feishu_docx` 才允许被当成链接用。
    reportUrl: (String(rev?.publish?.docx ?? '').trim() || String(rev?.report_url ?? '').trim()) || null,
    // ★ 2026-10-08（第五批）：**「链接」其实有两种** —— 飞书云文档（人点得开）
    //   与本地 `.md` 路径（**人点不开**）。引擎那边如实标了 `report_url_kind`，
    //   这里必须把它带出去；否则卡片会把一条本地路径当链接贴给读者
    //   （库规原话：「一个点不开的链接比空格更坏」）。
    reportUrlKind: String(rev?.report_url_kind ?? '').trim() || null,
    // ★★ 2026-10-12（库侧 Owner 裁定：`issue_count` **只算库内依据**）：
    //   候选条数**单独带出来** —— 数改小之后，若不单独说，读者会以为「库里就报了这几条」，
    //   而实际上还有几条**线索**（源里自己写着"不权威/已被取代"）。
    //   ⚠️ 只读，不参与任何算术：卡上的 `total` 与 `kbGap` 一个字没动。
    candidateCount: Number.isFinite(Number(rev?.candidate_count)) ? Number(rev.candidate_count) : null,
  };
}

/**
 * 「库侧**没有读数**」—— 这一单**根本没拿到库侧结论**，与「库侧说没问题」是两件事。
 *
 * 判据只认结构，不去猜文字：
 *   · **P0 快路** ⇒ 有读数（模式表命中即 BLOCK，本身是库产物；它压根不起链）；
 *   · **评审链** ⇒ 必须**机读旁挂在手、且旁挂里有 `state`**。
 *
 * 旁挂为什么会缺（2026-10-07 实测）：`kb/l8/review_run.sh` 是旁挂的**唯一**写点，
 * 而 `exit 3`（库忙·认领被占）/ `exit 4`（某层闸门红）/ `exit 5`（某层审计红）
 * 都在写旁挂**之前**就退出了；headless agent 若绕过 `review_run.sh` 直接跑引擎，也不写。
 * ⇒ 这几种情况下守衡「读不到引擎读数」，而**表里那格照样可能落 PASS**（实测素材 D）。
 *
 * ★ `kb` 为 `null/undefined`（调用方压根没传库侧）时**不触发**本闸 ——
 *   那是「合并没启用」的回退口径（自证 ⑫ 反向对照守着），不许把它和新闸混在一起。
 */
export function kbNoReadingOf(kb) {
  if (!kb) return false;                                 // 没传库侧 ⇒ 回退口径，不判
  if (kb.source === 'p0_fastpath') return false;         // 快路自带读数
  return !(kb.hasSidecar === true && String(kb.state || '').trim());
}

/** 库侧抽取的自证（与六行矩阵分开，因为它们是**抽取**不是**裁决**）。 */
export function selftestExtract() {
  let pass = 0; const bad = [];
  const ok = (n) => { pass++; console.log(`  ✅ ${n}`); };
  const no = (n, w) => { console.log(`  ❌ ${n} —— ${w}`); bad.push(n); };
  const eq = (n, g, w) => (JSON.stringify(g) === JSON.stringify(w) ? ok(n) : no(n, `期望 ${JSON.stringify(w)}，实得 ${JSON.stringify(g)}`));

  const REAL = '【审查结论：REVIEW】共发现 2 处需人工确认。\n\n'
    + '1.【合规-医疗宣称】视频 00:12 字幕「治疗堵奶」涉嫌医疗宣称。\n   原因：母婴内容不得出现治疗表述。\n'
    + '2.【消费者安全-使用姿势】图片 1 中吸奶器使用姿势可能误导。\n   原因：可能误导消费者。\n\n'
    + '建议转 @法务 @医学顾问 复核。';
  const r = kbFindingsOf(REAL);
  eq('⑩ 逐条块里的两条被抽出来', [r.findings.length, r.findings[0].category, r.findings[0].sub],
     [2, '合规', '医疗宣称']);
  eq('⑩ 严重度按动作行判（「复核」⇒ REVIEW）', r.findings[0].severity, 'REVIEW');

  // ★ 覆盖缺口那条**不算内容问题**：混进来会让「问题数量」虚高
  // ★ 这段是**真实产出**的原文（with_kb_evidence.py 的 _item 模板），不是我编的短句 ——
  //   第一版我图省事用了省略号，于是「覆盖判据不成立」这几个字根本不在样本里，
  //   断言直接红了。**样本写短了会把判据验成另一件事**，所以按真话抄。
  const COV = '【审查结论：REVIEW】共发现 1 处需人工确认。\n\n'
    + '1.【覆盖-知识库覆盖缺口】本次素材的**文字层逐字命中 0 条**，但覆盖判据不成立'
    + '（没有「既被规则引用、又达门限」的单元）——**这不是素材有问题，是库对该题材没有可依据的条款**。\n'
    + '   建议：转人工复核后再定；补素材无用（缺的是库覆盖）。';
  const rc = kbFindingsOf(COV);
  eq('⑩ 覆盖缺口不计入 findings', [rc.findings.length, rc.coverage?.category], [0, '覆盖']);

  eq('⑩ 认得出「覆盖判据不成立」⇒ 没覆盖', kbCoveredOf(COV), false);
  eq('⑩ 认得出 reason_code', kbCoveredOf('…原因码 `coverage_not_covered`：…'), false);
  // 反向对照：正常的三态结论**不许**被判成没覆盖（否则永远到不了 PASS）
  eq('⑩ 反向对照：正常 REVIEW 结论 ⇒ 算覆盖到了', kbCoveredOf(REAL), true);
  eq('⑩ 反向对照：PASS 结论 ⇒ 算覆盖到了',
     kbCoveredOf('【审查结论：PASS】未发现已知底线风险。'), true);

  // ── 同源判据（2026-10-08）────────────────────────────────────────────
  //   真事故：库侧「平台与促销-静音绝对化表述」+ 模型侧「措辞表达」，位置与类目两个都不同
  //   ⇒ 按原规则算两条 ⇒ 问题数虚高（Owner 那张卡写 4 处、实际 3 处）。
  {
    const kb = [{ location: '全文', category: '平台与促销', sub: '静音绝对化表述',
                  severity: 'REVIEW', excerpt: '静音', reason: '逐字命中「静音」', article_no: 'W-1.54' }];
    const mo = [{ location: '整段文案', category: '措辞表达',
                  severity: 'REVIEW', excerpt: '静音', reason: '模型侧独立判定：静音是绝对化表述' }];
    const r = mergeFindings(kb, mo);
    eq('⑪ 同源判据：位置与类目都对不上，但逐字片段相同 ⇒ **合并成一条**', r.items.length, 1);
    eq('⑪ 合出来的那条是「两轨都命中」', r.items[0].source, 'both');
    eq('⑪ 同源配对被计数', r.stats.same_origin, 1);

    // ── 反向对照（2026-10-08 **重写**，因为它与被测设计互斥）────────────────────
    //
    //   旧版断言「命中同一串字但大类不同 ⇒ **不许合并**」，而新设计是「**精确相等就合并**」
    //   （理由见 `sameOrigin`：两侧用的是两套类目词表，那道闸永远不成立 ⇒ 重复计数修不了）。
    //   把旧断言留着，等于**用一个已被推翻的设计去判新设计**。
    //
    //   新设计真正该保证的不是「不合并」，而是「**合并了要让人看见**」——
    //   同一个词可能是两个问题（「静音」既可能是措辞绝对化、也可能是消费者安全），
    //   精确相等看不见语义差别 ⇒ 用**标注**兜，而不是用不合并兜。
    const mo2 = [{ location: '整段文案', category: '消费者安全',
                   severity: 'REVIEW', excerpt: '静音', reason: '说的是婴幼儿睡眠安全' }];
    const r2 = mergeFindings(kb, mo2);
    eq('⑪ 同字不同族 ⇒ 合并（精确相等为准）', r2.items.length, 1);
    eq('⑪ 但**必须标注**类目族不同，让人自己判断', /类目族不同/.test(JSON.stringify(r2.items)), true);
    // 反向对照②：**逐字片段不相同**时不许因为「位置/类目像」就并
    // ⚠️ 位置必须**与库侧不同**：写「全文」的话键就匹配上了（那是原本的规则、合并是对的），
    //    这条用例就**没隔离住要测的东西** —— 第一版我写错了，断言直接红。
    const mo3 = [{ location: '第 2 段', category: '平台与促销', severity: 'REVIEW',
                   excerpt: '完全静音', reason: 'x' }];
    eq('⑪ 反向对照：片段**不相同** ⇒ 不许合并（哪怕位置与类目都对得上）',
       mergeFindings(kb, mo3).items.length, 2);

    // ★ 一条结构性事实，钉住它免得下一个人以为 R 门限覆盖了全部：
    //   2 字命中词的 R 最大只能是 2。
    eq('⑪ 2 字命中词的 R 上界 = 2（R≥4 那类门限对它**结构上不可能成立**）',
       lcsLen(normText('静音'), normText('静音')), 2);
    eq('⑪ 一侧没有命中片段 ⇒ 不同源（不许因为「都没给」就并）',
       sameOrigin({ category: '合规' }, { category: '合规' }).same, false);

    // ★ R 值必须被**记下来**（门限本次不启用，但要攒真实分布）
    const r3 = mergeFindings(kb, [{ location: '别处', category: '平台与促销',
                                    severity: 'REVIEW', excerpt: '限时', reason: 'x' }]);
    eq('⑪ 同源尝试的 R 分布被记进 stats（门限未启用，先攒数据）',
       typeof r3.stats.same_origin_r === 'object' && r3.stats.same_origin_r !== null, true);
  }

  // ── 库侧依据行必须**原样搬**（2026-10-08）───────────────────────────────
  //   卡片逐条块有**两个产者**：库侧 `_evidence_line`（带逐字命中文案 + 飞书源直链）
  //   与 JS 的 `renderMerged`。双轨**改写结论**时用的是后者 ——
  //   如果后者自己重建一句，就会把库侧已经产好的 L0 直链**丢掉**
  //   （第一版就是这样：印出「《知识库》W-1.16（锚点：#…）」，点不开）。
  {
    const KB_LINE = '依据：《措辞表达库 v0》第 W-1.16 条 ← 逐字命中「限时」'
      + '｜原始出处：https://momcozy-in.feishu.cn/base/XXX?table=YYY&record=recvuJP2jyeza5';
    const ans = `【审查结论：REVIEW】共发现 1 处需人工确认。\n\n`
      + `1.【平台与促销-静音绝对化表述】全文，（来源未给引文）\n`
      + `  **原因**：逐字命中「限时」\n  **${KB_LINE}**\n`;
    const q = kbFindingsOf(ans);
    eq('⑫ 库侧依据行被抓下来（逐字命中文案 + 飞书源直链）',
       /逐字命中「限时」/.test(q.findings[0]?.basisLine ?? '') && /https:\/\//.test(q.findings[0]?.basisLine ?? ''), true);
    // renderMerged 必须**原样**用它，不许重建
    const items = [{ location: '全文', category: '平台与促销', severity: 'REVIEW', source: 'kb',
                     reason: 'x', kb: { article_no: 'W-1.16', anchor: '#x/y/z', basisLine: q.findings[0].basisLine } }];
    const out = renderMerged(items, { state: 'REVIEW' });
    eq('⑫ renderMerged 原样搬库侧那句（不重建）', /原始出处：https:\/\//.test(out?.block ?? ''), true);
    eq('⑫ 反向对照：拿不到库侧依据行时才退回重建版（且那版**点不开**，故必须能区分）',
       /锚点：/.test(renderMerged([{ location: '全文', category: '合规', severity: 'REVIEW',
                                     source: 'kb', reason: 'x', kb: { article_no: 'W-1', anchor: '#a/b/c' } }],
                                   { state: 'REVIEW' })?.block ?? ''), true);
  }

  // ── ⑬ 走**完整链路**：kbFindingsOf → mergeFindings → renderMerged ──────────
  //   ★ 为什么必须补这一条：上面 ⑫ 我**手搓了一个带 basisLine 的条目**喂给 renderMerged，
  //     于是它绕过了 `mergeFindings` 里的 `pickKb()` —— 而 bug 恰恰在那里
  //     （`pickKb` 只挑 5 个字段，把 `basisLine` 丢了）。
  //     实测证据：Owner 看到的卡片印着 `《知识库》（未给条款号）（锚点：—）`，
  //     而 `⑫` 照样全绿。**夹具绕过被测环节 = 测了个寂寞。**
  {
    const KB_LINE = '依据：《措辞表达库 v0》第 W-1.54 条 ← 逐字命中「静音」'
      + '｜原始出处：https://momcozy-in.feishu.cn/base/AAA?table=BBB&record=recvuJP2jyeza5';
    const ans = '【审查结论：REVIEW】共发现 1 处需人工确认。\n\n'
      + '1.【平台与促销】全文，静音程度夸大\n'
      + '  **原因**：逐字命中「静音」，静音程度夸大\n'
      + `  **${KB_LINE}**\n`;
    const kb = kbFindingsOf(ans);
    const mo = [{ location: '整段', category: '措辞表达', severity: 'REVIEW',
                  excerpt: '别的词', reason: '模型侧另一条' }];   // 确保走 kb-only 那条支路
    const merged = mergeFindings(kb.findings, mo.findings ?? mo);
    const out = renderMerged(merged.items, { state: 'REVIEW' });
    const blk = out?.block ?? '';
    eq('⑬ 完整链路：依据行带**飞书源直链**（不许退回重建版）', /原始出处：https:\/\//.test(blk), true);
    eq('⑬ 完整链路：依据行带**逐字命中文案**', /逐字命中「静音」/.test(blk), true);
    eq('⑬ 完整链路：不许出现重建版的「（未给条款号）（锚点：」', /（未给条款号）/.test(blk), false);
    eq('⑬ 完整链路：**原因**用库侧那句，不是位置文字',
       // ★ 2026-10-09：标签带加粗了（Owner 裁定）⇒ 正则认两种写法，否则误红。
       /\*{0,2}原因\*{0,2}：逐字命中「静音」，静音程度夸大/.test(blk), true);
    // 反向对照：库侧**没有**依据行时，才允许退回重建版（且必须能区分出来）
    const ans2 = '【审查结论：REVIEW】共发现 1 处需人工确认。\n\n1.【合规】第 1 处\n  **原因**：x\n';
    const o2 = renderMerged(mergeFindings(kbFindingsOf(ans2).findings, []).items, { state: 'REVIEW' });
    eq('⑬ 反向对照：没有依据行时退回重建版（能区分）', /（未给条款号）/.test(o2?.block ?? ''), true);
  }

  // ══════════════════════════════════════════════════════════════════════════
  // ⑭ 2026-10-09：**「命中原文 + 飞书链接」必须真进卡片**（Owner 点名要的那一块）
  // ══════════════════════════════════════════════════════════════════════════
  // 今天连栽两次，两次的形状是同一个，所以判据也按那个形状写：
  //   ① 第一坑：`category` 只按 `risk_type` 拆（引擎的覆盖行**没有连字符**）
  //      ⇒ 覆盖行被误归进 findings、`coverage` 恒 null ⇒ 挂在 coverage 上的渲染**永不执行**。
  //   ② 第二坑（更贵）：修好①之后它"能跑了"，可我把它渲染进 `coverage.reasonLine` ——
  //      而 `agent.mjs` **压根不用 `kb.coverage`**（`mergeFindings` 只吃 findings；
  //      卡片里那句 covNote 是**写死的**）⇒ 渲染进了一个**没人读的字段**。
  //   两坑的共同点：**我验的是产出者，没验消费者**。
  //   ⇒ 判据必须**穿过消费者的边界**：从「引擎 JSON」一路断到 **`renderMerged` 的 `block`**
  //     （那才是守衡真发出去的那段字），而不是断在中间的某个字段上。
  {
    // ★ 样本用**引擎真实产出的形状**（`with_kb_evidence.py:606-608`）：
    //   `risk_type` 是 `覆盖缺口`（**无连字符**），`category` 单独给 `覆盖`。
    //   上一轮的 ⑩ 用的是**渲染后**的文本 `【覆盖-知识库覆盖缺口】`（**有连字符**）——
    //   于是它在"结构化那条来路坏着"的情况下照样绿。**样本形状不对，判据就是假的。**
    const realShape = {
      decision: { risk_items: [{ risk_type: '覆盖缺口', category: '覆盖', sub: '知识库覆盖缺口',
                                 location: '全文', reason: '覆盖判据不成立', action: '转人工' }] },
      evidence_meta: { kb_hits: [
        { anchor: '#l.1-2', bm25: 135.468, kb_type: 'internal_sample', excerpt: '逐字命中的那一段原文',
          url: 'https://momcozy-in.feishu.cn/wiki/TqJSduQE3oBM4uxtHhmcrVtGnPg', source_sha256: 'd3c8b460b9686447'.padEnd(64, 'a') },
      ] },
    };
    const rs = kbFindingsOf('', realShape);
    eq('Ka 引擎真实形状的覆盖行 ⇒ 归 coverage，**不占 findings**',
       [rs.findings.length, rs.coverage?.category], [0, '覆盖']);
    // ↑ 变异自证：把 `category` 改回「只按 risk_type 拆」⇒ 这里变成 [1, '覆盖缺口']，**精确变红**。

    const modelF = { ok: true, findings: [{ location: '00:12', category: '合规', severity: 'REVIEW',
                                            reason: '口播提到疗效', basis: 'model' }] };
    const mg = mergeFindings(rs.findings, modelF.findings);
    const blk = String(renderMerged(mg.items, { state: 'REVIEW', kbTextCount: rs.findings.length,
      model: modelF, kbHitsBlock: rs.kbHitsBlock })?.block ?? '');
    // ★★ 这一条是今天真正的教训：断的是**卡片正文**，不是 `rs.kbHitsBlock`。
    // ★★ 2026-10-09 晚重写（Owner：「业务同事都看不懂」）——**这六条原先钉住的正是要被撤掉的行为。**
    //   旧 Kb–Kg 断言「卡片正文里必须有【库内命中（读数）】…直链…在逐条之前」——
    //   而 Owner 的裁定是：**卡上只放能让人决定下一步的东西**，检索读数属于报告。
    //   断言把旧行为钉死 ⇒ 改对了反而全红（与早先 `W5` 钉住 `verdictSlotOf` 那个 bug 同一个病）。
    //   现在反过来钉：**卡上不许有它，但它必须一条不丢地出现在报告里。**
    eq('Kb 卡片正文里**不许**再出现【库内命中（读数）】（业务同事看不懂的东西不上卡）',
       blk.includes('库内命中（读数）'), false);
    eq('Kc+Kd+Ke+Kf 那些读数字段（命中原文/直链/sha/不得据此当 PASS）也都不上卡',
       [/命中原文（逐字）/, /飞书直链：https:\/\//, /不得据此当 PASS 依据/].some((re) => re.test(blk)), false);
    eq('Kg 读数块必须**原样交出去**（搬是搬、砍是砍 —— 报告要拿它进附录）',
       typeof rs.kbHitsBlock === 'string' && rs.kbHitsBlock.includes('库内命中（读数）'), true);

    // 反向对照：**没有读数就不许印**（不许编一段空壳，也不许印「0 条」冒充读过）
    const noHits = { decision: { risk_items: [{ risk_type: '合规', category: '合规', location: '全文',
                                                reason: 'x', action: 'review' }] }, evidence_meta: {} };
    const nh = kbFindingsOf('', noHits);
    eq('Kh 反向对照：引擎没给 kb_hits ⇒ 不印读数块', nh.kbHitsBlock, null);
    const blk2 = String(renderMerged(mergeFindings(nh.findings, modelF.findings).items,
      { state: 'REVIEW', model: modelF, kbHitsBlock: nh.kbHitsBlock })?.block ?? '');
    eq('Ki 反向对照：卡片正文里也不许冒出【库内命中】', blk2.includes('库内命中'), false);

    // ★★ Kj **接线判据**：`dual_track` 修好了，`agent.mjs` 不传进来照样白搭 ——
    //   今天的第二坑就是"产出者对了、消费者没接"。这条直接读源文件核那一行接线。
    //   为什么值得用源文件断言：这行没有别的运行时判据能覆盖到
    //   （`renderMerged` 收不到参数时**静默**不印，不会报错）。
    const src = readFileSync(new URL('./agent.mjs', import.meta.url), 'utf8');
    eq('Kj agent.mjs 确实把 kbHitsBlock 接进了 renderMerged',
       (src.match(/kbHitsBlock:\s*kb\.kbHitsBlock/g) || []).length >= 2, true);
    // ↑ 两处调用（rendered0 与 rendered）都要接；只接一处 ⇒ 走另一条分支的单子又没有读数。
  }

  // ══════════════════════════════════════════════════════════════════════════
  // ㉒ 2026-10-13：**合并的键不许把内容拆坏**（Owner 那张 P0 卡上就看得见）
  // ══════════════════════════════════════════════════════════════════════════
  //   病灶：`keyOf` 是 `` `${location}|${category}` ``，而 `mergeFindings` 收尾
  //   把它 `key.split('|')` 拆回来。这一条的 `location` 里**本身全是 `|`**
  //   （命中正则 `最\s*(好|佳|优|强|安全|…)`）⇒ 拆回来 location 被腰斩成
  //   `` 全文，逐字命中 `最\s*(好 ``、category 变成 `佳`
  //   ⇒ 卡上印出 **`1.【佳】`** 与 **`· 佳类问题：1 个`**。真维度是 `绝对化与安全承诺-虚假安全承诺`。
  //
  //   判据三层（缺一层都不算）：腰斩的那一条逐字不变 · 反向对照普通条目照旧 · 键不再相撞。
  {
    const PIPE_LOC = '全文，逐字命中 `最\\s*(好|佳|优|强|安全|低价|便宜|有效|快|大|高|省|舒适)`';
    const kbPipe = [{ location: PIPE_LOC, category: '绝对化与安全承诺', sub: '虚假安全承诺',
                      severity: 'BLOCK', source: 'kb', reason: 'H05' }];
    const mPipe = mergeFindings(kbPipe, []);
    eq('㉒a ★ 命中正则里带 `|` 的条目 ⇒ 位置与维度**逐字不变**（旧写法会腰斩成「最\\s*(好」/「佳」）',
       [mPipe.items[0].location, mPipe.items[0].category], [PIPE_LOC, '绝对化与安全承诺']);
    // ↑ 变异自证：把 `const src = kb ?? model` 那两行换回 `key.split('|')` ⇒ 这里
    //   变成 ['全文，逐字命中 `最\\s*(好', '佳']，**精确变红**。
    eq('㉒a2 它照样认得出来是 BLOCK（腰斩会把维度判错，严重度那一格也不能跟着坏）',
       mPipe.items[0].severity, 'BLOCK');
    // 反向对照：**没有 `|` 的普通条目**照旧（不许为了修这一条把配对逻辑改坏）
    const plain = mergeFindings(
      [{ location: '第 3 行', category: '平台与促销', severity: 'REVIEW', source: 'kb', reason: 'x' }],
      [{ location: '第 3 行', category: '平台与促销', severity: 'REVIEW', source: 'model', reason: 'y' }]);
    eq('㉒b 反向对照：不带 `|` 的同位置同维度仍并成一条（双轨确认）',
       [plain.items.length, plain.items[0].source, plain.items[0].location], [1, 'both', '第 3 行']);
    // 键不再相撞：`a|b`+`c` 与 `a`+`b|c` 在旧写法下是**同一个键**（两条并成一条，静默少报）
    const collide = mergeFindings(
      [{ location: 'a|b', category: 'c', severity: 'REVIEW', source: 'kb', reason: '1' },
       { location: 'a', category: 'b|c', severity: 'REVIEW', source: 'kb', reason: '2' }], []);
    eq('㉒c 旧写法下会撞成一个键的两组 ⇒ 现在必须是**两条**（撞了就是静默少报）',
       collide.items.length, 2);
    // 来源标记的措辞：**那两个词一个都不许出现**，而「回不回得了源」这条信息必须还在
    const kbLine = renderMergedItem({ location: 'x', category: '合规', source: 'kb',
                                      severity: 'REVIEW', reason: 'r' }, 0, { must: false });
    const moLine = renderMergedItem({ location: 'x', category: '合规', source: 'model',
                                      severity: 'REVIEW', reason: 'r' }, 0, { must: false });
    eq('㉒d 卡面/报告里不许出现「知识库侧」「模型侧」（Owner 2026-10-13）',
       [/知识库侧/.test(kbLine + moLine), /模型侧/.test(kbLine + moLine)], [false, false]);
    eq('㉒e 但「这一条回不回得了源」必须还在（那才是那个标记的用处）',
       [/有库内条款依据/.test(kbLine), /无库内依据/.test(moLine)], [true, true]);
  }

  console.log(`\n抽取自证：通过 ${pass} / 失败 ${bad.length}`);
  return bad.length ? 1 : 0;
}

/**
 * 渲染**一条**合并条目（§5.3 的四要素：位置＋来源 / 原因 / 依据 / 判定 / 建议）。
 *
 * ★ 2026-10-09 抽出来。原先它是 `renderMerged` 里的一段**内联 `list.map`**，
 *   而「≥3 时另建一份合并报告」（`merged_report.mjs`）要逐条列**同一批**条目 ——
 *   两处各写一遍必然漂移（今天已经因为「同一个东西两个产出者」栽过三次）。
 *   所以**口径只有这一处**：卡片与报告都调它。§2.4 那句「搬是搬」。
 */
/**
 * **逐条依据**（落库用）——把每一条的「依据」压成一行，写进表里的「问题分类汇总」。
 *
 * ── 为什么要有它（Owner 2026-10-13）────────────────────────────────────────
 *   「你修改的模型侧输出问题必须带依据的 url，**这个要落库**」
 *   卡上有了、报告里有了，但**表里没有**：卡片会滚走、报告要另点一次，
 *   而表是这一单最长寿的那份记录。依据不进表，等于它没被留住。
 *
 * ── 三条判据（都在下面 `--selftest` 里对着喂）──────────────────────────────
 *   · 库侧条目用它**自己的** `basisLine`（带飞书直链，原样搬，不许重建）；
 *   · 模型侧条目用 `extBasisText()` 那一行（登记来源 ／ 自写 URL + 核验三态）；
 *   · **没有依据的条目一条都不列** —— 这一节的标题是「依据」，凑数就是撒谎。
 */
export function evidenceBlock(items, { max = 12 } = {}) {
  const lines = [];
  for (const f of items ?? []) {
    const hasKb = f.source === 'kb' || f.source === 'both' || f.source === 'both-conflict';
    const kbLine = hasKb ? (f.kb?.basisLine || f.basisLine || null) : null;
    const ext = f.source === 'model' ? extBasisText(f.model ?? {}) : null;
    const basis = kbLine || (ext?.cited ? ext.line : null);
    if (!basis) continue;                       // 没依据的不列（凑数就是撒谎）
    const what = String(f.reason ?? f.kb?.reasonLine ?? '').replace(/\s+/g, ' ').slice(0, 60);
    lines.push(`${lines.length + 1}.【${f.category ?? '—'}】${String(f.location ?? '').slice(0, 40)}`
      + `${what ? `｜${what}` : ''} → ${basis}`);
  }
  if (!lines.length) return '';
  const head = `\n\n【逐条依据（落库留痕）】`;
  const tail = lines.length > max
    ? `\n…另有 ${lines.length - max} 条，逐字依据见报告。`
    : '';
  // ★ 2026-10-14：编号条目之间也空开一行 —— 与 PRD §5.3 的分段口径同源
  //   （这处不是 PRD 那一块，是查证笔记；但同一张卡里两种编号列表的间距不该不一样）。
  return head + '\n' + lines.slice(0, max).join('\n\n') + tail;
}

/**
 * 数**渲染出来的条目**有几条（卡片正文 / 报告正文通用）。
 *
 * ★★ 2026-10-14（Owner 裁定「去掉『判定』这个字段」）—— **为什么必须新增它**：
 *   在此之前，多处判据（`test_agent.mjs` / `verify_cards.mjs`）拿
 *   `/^ *\*{0,2}判定\*{0,2}：/gm` **当条目计数器**用 —— 因为逐条块里
 *   `**判定**：` 恰好**每条一次**，数它就等于数条目。
 *   那是个**寄生判据**：它量的不是「有几条」，而是「有几行某个字段」。
 *   该字段一删，这些判据会**静默数出 0 条**（`0 === 0`、`0 === 8` 这类断言立刻变红，
 *   而红的原因是"计数器坏了"，不是"条目少了"）—— 红得对不上病。
 *   ⇒ 现在**量真东西**：逐条块的行首编号（`renderMergedItem` 的第一行就是它）。
 *   与排版无关（加不加粗、有没有补充行都不影响），字段增删也不再连带判据。
 *
 * @param {string} text 卡片正文 / 报告正文
 * @returns {number}
 */
export function countRenderedItems(text) {
  return (String(text ?? '').match(/^ *\d+\.【[^】]+】/gm) || []).length;
}

export function renderMergedItem(f, i, { must = false } = {}) {
  // 来源标记（Owner 2026-10-06：「备注下是规则库侧问题，还是模型侧问题」）
  // ★★ 2026-10-13（Owner：「不要出现 知识库侧，模型侧」）——
  //   **去的是那两个词，不是那条信息**。这个标记真正的用处是回答
  //   「**这一条回不回得了源**」（带条款号/锚点/指纹 ⇒ 可回源；不然只能转人工），
  //   而那是下一步动作的依据 ⇒ 换成不带内部说法的措辞，一个字的信息都没少。
  // ★ 2026-10-13（Owner）：「模型侧输出的问题，需要带上依据。写『无库内依据』，
  //   那就放模型侧能查到的依据链接」—— 所以这一格先算出**外部依据**，
  //   有依据就把标记改掉（标记的用处是回答「这条回不回得了源」：只说"无依据"会让人以为查都没法查）。
  const extB = f.source === 'model' ? extBasisText(f.model ?? {}) : null;
  const origin = f.source === 'kb' ? '**有库内条款依据**'
    : (f.source === 'model' ? (extB?.cited ? '**无库内条款 · 依据为外部标准**' : '**无库内依据 · 建议转人工**')
      : (f.source === 'both-conflict' ? '**两侧都命中 · 结论冲突 ⇒ 已降 REVIEW**'
        : '**两侧都命中（可回源）**'));
  // ★ 库侧那条 `依据` 行**原样用**（它带逐字命中文案 + 飞书源直链）。
  //   为什么必须搬、不能重建：L0 定位（`feishu_publish.l0_locate`）是 **Python** 的能力，
  //   JS 这一侧没有 ⇒ 重建只能造出一个更差的版本（「《知识库》W-1.16（锚点：#…）」，
  //   点不开、也没说命中了什么）。§2.4 的「搬是搬」：能搬就别造。
  const hasKb = f.source === 'kb' || f.source === 'both' || f.source === 'both-conflict';
  const kbBasis = (hasKb && (f.kb?.basisLine || f.basisLine)) || null;
  const basis = kbBasis || (f.source === 'kb'
    ? `《知识库》${f.kb?.article_no ?? '（未给条款号）'}（锚点：${f.kb?.anchor ?? '—'}）`
    : (f.source === 'both'
      ? `两侧都命中（库内条款 ${f.kb?.article_no ?? '—'} ／ 独立复核也命中）`
      : (extB?.line ?? '**无库内依据** —— 未落在知识库条款上（独立复核给出的判断）')));
  const verdict = f.source === 'both-conflict'
    ? '**两侧结论不一致 ⇒ 降为 REVIEW，转人工**（不许任一侧单独定案）'
    : (f.severity === 'BLOCK' ? 'BLOCK' : 'REVIEW');
  // ★ 来源标记放**条目第一行末尾**，不动 §5.3 的 `【维度-子类】` ——
  //   那个标签是 PRD 契约（`prd53.conforms` 与 `l7_integrity.py` 都在核它），
  //   往里面塞「模型侧」会把格式一致性判据打破。而来源必须**一眼扫得到**：
  //   库侧条目回得了源、模型侧条目没有依据 —— 这两样的下一步完全不同。
  // ── ★★ 2026-10-09：**「建议」必须来自两侧的真话**（Owner 当场提的）
  //
  //   Owner 原话：「守衡输出的建议都是『转对应负责人复核』。我期望的是：
  //   **知识库侧和模型侧都输出具体的修改建议**，而不是甩给人。」
  //
  //   病灶：这一行原先是**硬编码常量** ——
  //     `建议：${must ? '修改后重新提交。' : '转对应负责人复核。'}`
  //   无论两侧说了什么，它永远印这两个字符串之一。而两侧其实都有东西：
  //     · 库侧 `review_engine.py:321` **本来就有** `suggestion`
  //       （没有时它自己写「（来源未给修改建议）」—— 它对自己的沉默是诚实的）；
  //     · 模型侧由 `model_side.mjs` 的 `suggestion` 字段给（本轮新增，提示词一并改了）。
  //
  //   两侧都没给 ⇒ **如实说没有**，不许用「转人」冒充一条建议 ——
  //   那会让人以为「已经有人看过了」，而真相是**这一条只有现象、没有可执行的改法**。
  const sugKb = (hasKb && (f.kb?.suggestionLine || null)) || null;
  const sugModel = f.suggestion || f.model?.suggestion || null;
  // ── ★★ 2026-10-09：**「建议」的唯一产出者是 `advice.mjs`**（Owner 定的规则）
  //
  //   Owner 原话：「建议必须具体内容。负面样本『建议』列填充 47% ⇒ **有填的做参考，
  //   agent 输出最终具体建议**；没填的不用参考，agent 直接出建议。」
  //
  //   所以优先级变了：**有 `f.advice` 就用它**（那是两侧都回来之后那次调用为这一条
  //   专门写的改法），下面两套「库侧优先 / 模型侧优先」**降级为回退** ——
  //   只在建议生成失败时兜（`advice.mjs` 失败不编）。
  //   为什么过去关于「建议」的毛病都出在这一格：**它曾经有两个产出者**
  //   （库侧原话 / 模型原话）⇒ 库侧有值时模型那条被静默丢掉、来源也标不清。
  const adv = (typeof f.advice === 'string' && f.advice.trim()) ? f.advice.trim() : null;
  // 改法**始终是模型写的** ⇒ 标注说「**参考了什么**」，不说「谁给的」：
  // 说成「库侧给的改法」是假陈述（句子是模型写的）。
  const advRef = f.adviceReferencedKb === true;
  const sugLine = adv
    ? `${adv}（${advRef ? '**参考了库内反例的建议**' : '**库内无可参考建议**'}`
      + ' —— 改法是按素材给出的，**不是库规原文**）'
    : (sugKb
      ? sugKb
      : (sugModel
        ? `${sugModel}（**无库内依据的改法建议** —— 不是库规原文）`
        : '（**两侧都没给修改建议** —— 这一条只有现象，没有可执行的改法；'
          + '**不许把它读成「照此处理即可」**）'));
  // ══════════════════════════════════════════════════════════════════════════
  // ★★ 2026-10-09（Owner 裁定）：**PRD 四要素一行不少、顺序不动；多出来的作为补充行** ──
  //
  //   Owner 原话：「保留 7/8/9/10，但把它们**降格**到 PRD 四要素之后
  //   （PRD 四要素一行不少、顺序不动；多出来的作为补充行），**字段加粗保留**。」
  //
  //   PRD §5.3.2 / §5.3.3 的四要素 = 【维度-子类】位置 · 原因 · 依据 ·（BLOCK 才有）建议。
  //   改前，四要素之间**插着** `判定` 一行，且 `建议` 在 REVIEW 卡上也排在 `判定` **之前**
  //   ⇒ 顺序与 PRD 不一致。现在：
  //     前几行 = PRD 四要素，**顺序逐字照 PRD**（BLOCK：原因/依据/建议；REVIEW：原因/依据）
  //     之后   = 补充行（`判定`、REVIEW 的建议），**加粗保留**（Owner 明确要）
  //   ⚠️ 三个标签的加粗**不许撤** —— `l7_integrity.py:180`（`BLOCK 逐条四要素`）与
  //      `verify_cards.mjs` 的 J11 都钉着 `**原因**`/`**依据**`/`**建议**`。
  //   ⚠️ 「来源标记」（`—— **模型侧**（无库内依据）`）**留在第一行末尾**，理由不变：
  //      它决定这条的下一步（库侧回得了源、模型侧回不了），挪到补充区会让人读到第三行
  //      才知道「这条其实没有依据」。
  return `${i + 1}.【${f.category}${f.sub ? '-' + f.sub : ''}】${f.location}  —— ${origin}\n`
    + `   **原因**：${f.kb?.reasonLine ?? f.reason ?? '（未给理由）'}\n`
    + `   **依据**：${basis}\n`
    + (must ? `   **建议**：${sugLine}\n` : '')
    // ── ★★ 2026-10-14（Owner 裁定）：**`**判定**` 那一行整行删除** ────────────────────
    //   口径：PRD §5.3 的逐条模板只有 `原因` / `依据` /（BLOCK 才有）`建议`，
    //   三态只出现在**结论行** `【审查结论：X】` 一处 —— 逐条再挂一个「判定」，
    //   同一张卡上就有两个「判定」，业务侧分不清哪个是结论。
    //   ⚠️ 2026-10-09 那次「把它降格成补充行、加粗保留」的裁定**已被本次取代**
    //      （同一 Owner，后令优先）；上面第 1665 行那段注释留作历史，**勿据以恢复该行**。
    //   `verdict` 这个局部量仍算（上面 headline 那段），但**不再有任何输出点**。
    + (!must ? `   **建议**：${sugLine}\n` : '');
}

/**
 * 把合并结果渲染成 **PRD §5.3 的结论块**（结论行 + 逐条 + 动作行）。
 *
 * ★ 只在**模型侧真的报了东西**时才调用（见 `agent.mjs` 的 `shouldOverride`）：
 *   模型侧没报 ⇒ 返回 null ⇒ 结论原文**一个字不改**，仍用链给的那份。
 *   这条是「新增旁路不许改变原有行为」的执行点 —— 双轨改造最容易犯的错
 *   就是顺手把原来的单轨结论也改了一遍。
 *
 * ★ 更不许产出 PASS：`state` 由 `mergedState()` 给，而它要求 `kbCovered === true`。
 *
 * @returns {{line:string, block:string}|null}
 */
export function renderMerged(merged, { state, kb = null, kbTextCount = null, model = null,
                                     reportUrlOverride = null, kbHitsBlock = null,
                                     mergedStats = null } = {}) {
  const list = Array.isArray(merged) ? merged : [];
  const n = list.length;
  const kbN = Number.isFinite(kb?.issueCount) ? kb.issueCount : null;
  const txtN = Number.isFinite(kbTextCount) ? kbTextCount : null;
  // ★★ 2026-10-08：**「覆盖缺口那条」与「明细抠不出来」是两件事，原先被混成一件** ──────
  //   病灶（实测，Owner 2026-10-08 拿一张图逼出来的）：
  //     引擎对覆盖缺口的形状是 `state=REVIEW` ＋ `refusal=coverage_not_covered`，
  //     且它把「覆盖-知识库覆盖缺口」当成**一条 finding** 计进 `issue_count`（实测 =1）。
  //     JS 侧早就知道那条不是内容问题（`COVERAGE_CATEGORY` 把它踢出 findings），
  //     **但没把它从 `issueCount` 里踢掉** ⇒ 它又从 `kbGap = kbN − txtN = 1 − 0 = 1` 溜回来，
  //     于是卡片上多出一句「另有 1 条未并进本卡：PRD §5.3.3 规定问题数 ≥3 时库侧只出分类汇总」
  //     —— 而这一单的 `issue_count` 是 **1**，压根不是 ≥3 ⇒ **解释与事实不符**。
  //   现在的口径（三条，缺一条都不算修好）：
  //     ① 覆盖缺口那 1 条**算「需人工确认」**（人确实要去看覆盖）⇒ 进 `total`；
  //     ② 但它**不算「明细抠不出来」** ⇒ 不进 `kbGap`，也不触发那句 ≥3 的解释；
  //     ③ 「抠不全」的解释**按真实原因分支**：≥3 才说 §5.3.3，<3 就如实说抠出几条。
  const covGap = !!kb?.coverageGap;
  // ★★ 2026-10-12：**非权威候选线索**要出声（库侧 `issue_count` 已改成只算库内依据）。
  //   为什么必须单独说：那个数改小之后，"库里报了几条"与"还剩几条线索要人扫一眼"是两件事，
  //   而候选在卡上原本**完全不可见**。措辞与库侧口径一致（见 `review_engine.candidate_note`）。
  const candN = Number.isFinite(kb?.candidateCount) ? kb.candidateCount : 0;
  const candNote = candN > 0
    ? `\n⚠️ 另有 **${candN} 条非权威候选线索**（源规则已声明不权威/已被取代，`
      + `**无库内条款号、不构成依据**）—— 见报告完整清单。`
    : '';
  const covEntries = covGap ? 1 : 0;              // ① 那 1 条覆盖缺口：算「需人工确认」
  const kbMissingDetail = !covGap && kbN != null && kbN > 0 && (txtN == null || kbN > txtN);
  const kbGap = kbMissingDetail ? Math.max(0, kbN - (txtN ?? 0)) : 0;

  // ── 拒答（库侧未判）：不发"结论"，只发「这次谁没判」（2026-10-07 加）──
  //   原先拒答被折算成「0 条」⇒ 用户收到一张形如双轨结论的 REVIEW 卡，
  //   而表里那行的结论是 NEEDS_INPUT —— 同一单两个结论。
  if (state === 'NEEDS_INPUT') {
    // ★ 2026-10-13：同上 —— 去词不去信息。「哪一侧没判」照样说得清（说「审查引擎未判」）。
    const line = `【审查结论：NEEDS_INPUT】**审查引擎未判**（拒答、fail-closed）`
      + (kb?.reason ? `：${kb.reason}` : '') + '。';
    const body = list.length
      ? list.map((f, i) => `${i + 1}.【${f.category}${f.sub ? '-' + f.sub : ''}】${f.location}`
          + `  —— **无库内依据 · 建议转人工**\n   原因：${f.reason ?? '（未给理由）'}\n`
          // ★★ 2026-10-14（Owner 裁定）：拒答卡上的 `判定：REVIEW` 一并删除 ——
          //   三态只出现在上面的结论行（本支路是 `【审查结论：NEEDS_INPUT】`）；
          //   逐条再挂一个「判定：REVIEW」会让同一张卡出现**两个互相打架的三态**。
          + `   建议：**先恢复库侧再定**（本条不能当通过或拦截依据）。`).join('\n\n')
      : '（模型侧本次没报东西。）';
    // ★ 2026-10-08（Owner 同意 ②）：**「库忙」要写成「已排队」，不能写成「没下文」。** ──────
    //   病灶：卡原先只写「本次没有知识库三态结论 … **下一步**：先把库侧恢复（跑层/日更）再重审」——
    //   读者读到的是**死局 + 一份他做不了的作业**（"跑层/日更" 是维护动作，不是送审人的活）。
    //   而实际上这一单**已经进了补发队列**，判据是硬接线：
    //     `agent.mjs` 的 `chainUnmeasured`（＝「链没给出三态结论」，`!= PASS/REVIEW/BLOCK` 全算）
    //     为真 ⇒ 一定 enqueue；重试窗口 **1 小时 / 最多 5 次**，而认领 TTL 是 **45 分钟**
    //     ⇒ **窗口盖得住**（实测日志：`↻ 送审单但链没跑成（库忙…），可重试=true → 已入补发队列`）。
    //   ★★ 但不写「会另行告知」—— 实测 `deadDrop` 只把条目落进死信文件、**不通知任何人**；
    //     写「耗尽会告诉你」就是撒谎。所以如实写「5 次都没跑成就不会再有下文」。
    const isBusy = String(kb?.reason ?? '') === 'claim_busy';
    const queueNote = isBusy
      ? '\n\nℹ️ **这一单会自己重跑**：`claim_busy` = **有别的会话正在跑这条循环**'
        + '（库内明文规矩：同一时间只准一个会话跑），**不是这一单有问题**。'
        + '槽一空出来会**自动补跑**（1 小时内最多 5 次）。'
        + '**若 5 次都没跑成，就不会再有下文** —— 那时请再 @ 我一次。'
        + '（等不及也可以先停掉那个占用会话，再送一次。）'
      : '';
    const nextStep = isBusy
      ? '**下一步**：**你不需要做什么** —— 等自动补跑；或先停掉占用会话再送一次。'
      : '**下一步**：先把库侧恢复（跑层/日更）再重审这一单。';
    return {
      line, total: list.length, kbGap: 0, refused: true, claimBusy: isBusy,
      block: `${line}\n**本次没有三态结论** —— 以下只是**独立复核**的初步观察，`
        + '**不得当通过依据，也不得当拦截依据**。\n\n' + body
        + queueNote
        + `\n\n${nextStep}`,
    };
  }

  // 没有条目、库侧也没缺明细、**也没有覆盖缺口** ⇒ 交回链
  //   （覆盖缺口那条例外：它必须落进卡里，否则「库管不到这个题材」这句话就没了）
  if (!n && !kbMissingDetail && !covEntries) return null;
  const must = state === 'BLOCK';
  // 条数口径：能并的条目 ＋ **库侧结构性条数里没并进来的那部分**（重叠未判 ⇒ 这是上限，写明）
  //           ＋ **覆盖缺口那 1 条**（它不是内容问题，但确实是一处「需人工确认」）
  const total = n + kbGap + covEntries;
  const line = must
    ? `【审查结论：BLOCK】共发现 ${total} 处必须修改。`
    : `【审查结论：REVIEW】共发现 ${total} 处需人工确认。`;
  const items = list.map((f, i) => renderMergedItem(f, i, { must }));
  // ★★ 2026-10-14（Owner 报：与 PRD 不符）—— 收尾动作行的**收件人按问题方向算**。
  //
  //   病灶：这一行原先是常量 `'建议转 @内容治理负责人 复核。'`。PRD §5.3.2 **两处**
  //   （1-2 条与 ≥3 条）逐字都写 `建议转 @法务 @医学顾问 复核。`，§9 写
  //   「REVIEW 自动转**对应**专业团队（法务、医学、专家、北美）」——
  //   而「内容治理负责人」不在那四个团队里，且**不随问题方向变**。
  //
  //   现在：方向词 → `routing-policy.json` 的 rules → owners（有序）→ 有句柄用句柄、
  //   没句柄写「角色名（未配置）」。读不到路由表就回落 PRD §5.3.2 那一对。
  //   ⚠️ 保住的：`建议转 … 复核。` 这个**句式**（PRD §5.3 的收尾），
  //      以及「一个方向都没命中时不许编一个收件人」。
  //   ⚠️ `applyVerdictLine` 只搬**结论行**（`【审查结论：…】`），不碰这一行 ⇒ 两处不打架。
  const routing = reviewOwnersFor(list, ROUTING_POLICY);
  const action = must
    ? '请修改后重新提交。'
    : renderReviewAction(routing.owners, ROLE_HANDLES,
        { unmatched: routing.unmatched, total: list.length,
          // ★ 没有任何条目可路由（空清单）时落这个 —— 与「读不到路由表」同一答案。
          //   库侧覆盖缺口那一支恒为空清单，靠的就是这条（`routing.py` 同口径）。
          fallback: ROUTING_POLICY?.fallback });
  // ★ 块首汇总：**先让人看到「这次是谁在说话」**，而不是读完四条才自己拼出来。
  //   库侧 0 条而模型侧 5 条，与库侧 5 条，是两种完全不同的单子 —— 前者没有一条回得了源。
  const fromKb = list.filter((f) => f.source === 'kb' || f.source === 'both' || f.source === 'both-conflict').length;
  const fromModel = list.filter((f) => f.source === 'model' || f.source === 'both' || f.source === 'both-conflict').length;
  // ★ 库侧**没读数**时不许写「0 条」（2026-10-07，Owner 同意）——
  //   「库判过、没报东西」与「库这次没参与」长得一样，是**最容易被读错**的一处：
  //   实测素材 D 就是因为这一格含糊，加上表里落了 PASS，看起来像"库审过了、没问题"。
  const kbNoReading = kbNoReadingOf(kb);
  // ── 模型侧那一边的措辞（2026-10-08 加）────────────────────────────────────
  //   ★ 同一条纪律，模型侧原先**漏了这一半**：
  //     `renderMerged` 收不到 `model` ⇒「模型侧跑了、确实没报东西」与
  //     「模型侧**没跑成**（解析失败／异常／额度被 reasoning 烧光）」在卡上一模一样，
  //     都写成「模型侧 0 条」。实测（Owner 2026-10-08 那张图）：日志明写
  //     `模型侧 没跑成：输出里没有 JSON 数组`，卡片却写「模型侧 0 条」——
  //     人当场读成「没走模型侧」，排查方向整个错掉。
  const modelFailed = !!(model && model.ok === false);
  const modelErr = modelFailed ? String(model.error ?? '未给原因').slice(0, 120) : '';
  const modelTxt = modelFailed
    ? `模型侧 **没跑成**（${modelErr}）—— 本卡**没有**模型侧条目，`
      + '**这不等于「模型侧看过、没问题」**'
    : (model && model.ok === true && model.skipped
      ? '模型侧 0 条（文字层为空，本就未跑）'
      : `模型侧 ${fromModel} 条`
        + (list.some((f) => f.source === 'model')
          ? `（其中 ${list.filter((f) => f.source === 'model').length} 条**无库内依据**，只能转人工）` : ''));
  const kbContentN = fromKb + kbGap;              // 库侧的**内容问题**条数（不含覆盖缺口）
  // ★★ 2026-10-09：**这一行自己就是一个块，末尾必须有换行** ──────────────────
  //   病灶（实测）：`block` 的拼接是 `${line}${reportNote}\n${tally}${covNote}${bodyText}`，
  //   而 `tally` 与 `covNote` **都没有结尾换行** ⇒ 印出来是
  //     `…模型侧 2 条（其中 2 条**无库内依据**，只能转人工）1.【合规-医疗宣称】视频 00:12 字幕`
  //   —— 编号 1 与汇总行**粘在同一行**。`verify_cards.mjs:633` 的夹具里本来就有
  //   `'知识库侧 3 条 ／ 模型侧 3 条\n\n1.【合规】'`，**是代码与夹具不一致**，
  //   不是设计如此；夹具写得对，所以这条改动不会把判据打红。
  // ★★ 2026-10-09（Owner 报「图表数字对不上」）**页脚算术必须闭合** ──────────────
  //   病灶（实测本单，逐字）：抬头「共发现 **8** 处」，页脚「知识库侧 **2** 条 ／ 模型侧 **6** 条」——
  //   2+6=8 看着对，**而库侧实际并进来的是 5 条**（双轨读数：库侧 5 ＋ 模型侧 6 ⇒ 合并 8）。
  //   读者拿卡一算就不平：库侧 2 ＋ 模型侧 6 ＝ 8 ＝ 抬头，但卡里另一处又写着「REVIEW 5 处」。
  //   根因：页脚用的是「**并进清单里的**库侧条目」（`fromKb`），而抬头那个数是
  //   `n + kbGap + covEntries`（含**没并进来的**库侧条目）⇒ 两个口径不同的数并排印。
  //   ⇒ 改成三个**说得通**的数，且**加起来等于抬头**：
  //        知识库侧 X 条（结构化读数）＋ 模型侧 Y 条 − 两侧指向同一处的 Z 条 = 抬头
  //      （Z＝两轨确认 ＋ 冲突；`mergeFindings` 的 stats 里本来就有，不用另算）
  //   ⚠️ 不许再出现「页脚两个数加起来对不上抬头」的形状。
  const kbStructuralN = Number.isFinite(kbN) ? kbN : fromKb;
  // ★ 去重条数**用差额算**，不另取 stats：
  //   抬头 `total = n + kbGap + covEntries`（`n` = 并集去重后的条数），
  //   而左边两个数之和是 `kbStructuralN + fromModel` ⇒ 差额就是「并集之外多算的」，
  //   它**同时吸收两样东西**：两侧指向同一处的重复（stats.both/conflict）＋ 库侧未并进的 kbGap。
  //   ⇒ 这样「左式 − 差额 ＝ 抬头」**恒成立**，说明文字也不会与 `kbGap` 那段重复计数
  //     （第一版两种都写，印出来是「5+6=11」又「另有 3 条未并进」，自相矛盾）。
  const lhs = kbStructuralN + fromModel;
  const dedupN = Math.max(0, lhs - total);
  const tally = (kbNoReading
    ? `知识库侧 **本次未参与**（没拿到引擎读数） ／ ${modelTxt}`
      + `（**全部无库内依据**，只能转人工）`
    : (covGap && !kbContentN
      // ★ 2026-10-08：覆盖缺口那条**不是内容问题** —— 不许让它与「内容问题」共用同一个计数说法
      ? `知识库侧 **未报内容问题**；另有 **1 条覆盖缺口**（库对该题材没有可依据的条款） ／ ${modelTxt}`
      : `知识库侧 ${kbStructuralN} 条（**结构化读数 ${kb?.state ?? '—'}/${kbN}**）`
        + (modelFailed
          // ⚠️ **模型侧没跑成时，不许把它折进那个算术式** —— 折进去会印成
          //    「模型侧 0 条」或「模型侧 6 条」，而真相是**这一侧根本没跑**。
          //    （自证 ⑭g/⑭g2 钉着这一条：含糊它 = 让人以为"模型看过了、没问题"。）
          ? ` ／ ${modelTxt}`
          : ` ＋ 模型侧 ${fromModel} 条`
            + (dedupN ? ` − 计入 ${total} 处（去重 ${dedupN}：两侧指向同一处 ＋ 库侧未并入的）` : '')
            + ` ＝ 本卡 **${total} 处**（**上限**：两轨重叠未判）`
            + `${covEntries ? '（另 1 条是**覆盖缺口**，不是内容问题）' : ''}`))) + candNote + '\n';
  // ★ 库侧明细缺失是**必须出声**的（2026-10-07）：否则读者会以为库侧真没报东西。
  // ★★ 2026-10-08：**解释必须按真实原因分支**。
  //   原先不分情形一律写「PRD §5.3.3 规定问题数 ≥3 时库侧只出分类汇总」——
  //   而实测那张图的 `issue_count` 是 **1**，压根不是 ≥3 ⇒ 一个 1 条的单子被用 ≥3 的规矩解释，
  //   查的人会往「库侧做了汇总」那个方向找，永远找不到。
  // ★★ 2026-10-08（第五批）：**报告链接按来源分档措辞**。
  //   为什么：`report_url` 可能是**飞书云文档**（人点得开），也可能是**本地 `.md` 路径**
  //   （人**点不开**）—— 引擎用 `report_url_kind` 如实标了是哪一种（见 `kbSideOf`）。
  //   把本地路径当链接贴给读者，就是库规说的「一个点不开的链接比空格更坏」：
  //   读者以为点开就有明细，点了什么都没有，还不会回头怀疑那句话。
  //   拿不到 kind（旧版旁挂）时**按形态兜底判**：`http(s)://` 才算链接，其余按本地路径说。
  // ★ 2026-10-09：`reportUrlOverride` 是**本仓自己建的那份合并报告**的链接（`merged_report.mjs`）。
  //   为什么要有它：库侧只在**它自己的** `issue_count >= 3` 时建 docx，而卡里那个数是
  //   `total`（含模型侧与库侧未并进的）—— 实测 6 vs 1 ⇒ 库侧不给链接，而按 PRD 该给。
  //   传进来时它就是**权威**：本仓建成了就用它，没建成传 null（照实说没拿到）。
  const _ru = reportUrlOverride || kb?.reportUrl || null;
  const _ruKind = kb?.reportUrlKind
    || (_ru ? (/^https?:\/\//i.test(_ru) ? 'feishu_docx' : 'local_path') : null);
  const reportRef = !_ru
    ? '（本次库侧未回报告链接）'
    : (_ruKind === 'local_path'
      ? `：\`${_ru}\` —— **这是本地文件路径，你点不开**；`
        + '要拿到可点开的明细，请让维护侧把该报告发成飞书云文档（`--write-report` 且发布成功时会给 docx 链接）'
      : `：${_ru}`);
  const gapNote = kbMissingDetail
    ? (kbN >= 3
      ? `\n⚠️ 知识库侧另有 **${kbGap} 条**未并进本卡：PRD §5.3.3 规定问题数 ≥3 时库侧只出分类汇总`
        + `，逐条明细在库里${reportRef}`
        + '；**与模型侧的重叠未判 ⇒ 上面那个总数是上限**。'
      : `\n⚠️ 知识库侧的结构化读数是 **${kbN} 条**，本卡只并进 **${txtN ?? 0} 条** —— `
        + '**未达 3 条，不适用 PRD §5.3.3 的「只出分类汇总」**（别往那个方向查）。'
        + `逐条明细在库里${reportRef}`
        + '；**与模型侧的重叠未判 ⇒ 上面那个总数是上限**。')
    : '';
  // ★ 覆盖缺口要单独说清含义（2026-10-07）：结论仍是 REVIEW，
  //   但它是"库管不到这个题材 ⇒ 转人工看覆盖"，不是"发现了内容问题"。
  const covNote = kb?.coverageGap
    ? `\nℹ️ 知识库侧给了 **覆盖缺口**（\`coverage_not_covered\`）：检索有命中，`
      + '但「既被规则引用、又达门限」的单元 0 条 ⇒ **库对该题材没有可依据的条款**。'
      + (covEntries
        // ★★ 2026-10-09：**这句话必须按「列表里到底有没有别的条目」分支** ────────────
        //   病灶（实测视频单 `recvxvLfgsTqHF`）：卡上写「**上面那 1 条「需人工确认」就是它**
        //   —— 它不是内容问题，别去逐条里找」，而**上面那一条其实是模型侧的对比风险**，
        //   覆盖缺口条目**根本没渲染进清单** ⇒ 读者照着这句话去找，找到的是**另一条东西**。
        //   这是「说了假话」，比不说更坏：它会让人把模型侧那条当成库侧覆盖缺口。
        ? (n === 0
          ? '**上面那 1 条「需人工确认」就是它** —— 它不是内容问题，别去逐条里找。'
          : '⚠️ 这条覆盖缺口**本身不占下面清单里的任何一条**（下面那些都是模型侧的）；'
            + '上面那个计数里的 1 是它。')
        : '')
      + '本单 REVIEW 的含义是**转人工看覆盖**，**不是发现了内容问题**；也**不得据此当 PASS**'
      + '（库口径：未命中 ≠ 合规）。\n'
    : '';
  // ★ 库侧没读数：**这一句是硬要求**（2026-10-07，Owner 同意）。
  //   没有它，读者会把"库没参与"读成"库说没问题"，而这两件事的下一步完全不同。
  const noReadNote = kbNoReading
    ? `\n⚠️ **本次知识库侧没有读数**（链没跑到引擎 / 机读旁挂没落 —— 库忙、层闸门红、或没走 `
      + '`review_run.sh`）⇒ 上面这些条目**只来自模型侧、无库内依据**，'
      + '**不得当通过依据**，也**不得据此当 PASS**（本单**不能算放行**）。'
      + '下一步：先确认库侧为什么没跑成，再重审这一单（**补素材无用**）。'
    : '';
  // ── ★ 2026-10-09：**PRD §5.3.4 的报告链接门槛（≥3）** ────────────────────────
  //
  //   规则是 Owner 2026-10-08 定的原话：「我在飞书侧 @守衡 提问后，双轨并行
  //   （知识库+模型），**双轨按照 PRD ≧3 个问题输出报告链接到飞书文档**」。
  //
  //   触发条件**必须**是卡里那个数（`total`）—— 不是 `stats.merged`（那只是「并进来几条」），
  //   也不是「库侧明细抠不出来」（`kbMissingDetail`，上面 `gapNote` 用的那个）。
  //   实测一单里有三个数：`total`=12（卡里写的）／`stats.merged`=7（并进来的）／
  //   旁挂 `issue_count`=5（库侧自己的）。**门槛只能挂在人看到的那个数上**。
  //
  //   门槛值与库侧**同名同口径**（`kb/l7/review-engine/core/feishu_publish.py`：
  //   `REPORT_LINK_MIN_ISSUES = 3`，PRD §5.3.4 / §8.3 / §17 三处一致）。
  //   两处各写一遍会各自漂移，所以这里写死并在断言里对住「≥3 才有这一行」。
  //
  //   ★ 拿不到链接时**如实说、并说清是哪一种拿不到** —— 不许编一个链接，也不许默默不给
  //     （库规：「一个点不开的链接比空格更坏」；而「没说为什么没有」比两者都坏）。
  // ★ 2026-10-14：前导 `\n\n`（**不是 `\n`**）—— PRD §5.3.2 的分段是
  //   `· <大类>类问题：N 个` ␤ `→ 查看完整问题清单…`，两者之间要有空行。
  const reportNote = total >= REPORT_LINK_MIN_ISSUES
    ? '\n\n→ 查看完整问题清单与修改建议：'
      + (!_ru
        ? '**本次未拿到报告链接** —— 库侧这一单没生成完整报告（`issue_count < '
          + REPORT_LINK_MIN_ISSUES + '` 时它按 PRD 不生成；本卡的问题数 `total` 含**模型侧**'
          + '与**库侧未并进的**条目，两者口径不同）。上面逐条已是本卡能给的完整清单。'
        : (_ruKind === 'local_path'
          ? `\`${_ru}\` —— **这是本地文件路径，你点不开**；`
            + '要拿到可点开的明细，请让维护侧把该报告发成飞书云文档。'
          : _ru))
    : '';
  // ★★ 2026-10-09（第二次修）：**报告链接提到抬头下面**，不再放在 8 条逐条之后。
  //
  //   病灶（Owner 当场反馈「还是没修复」）：链接**确实进了卡**，但它在结论块的最末尾 ——
  //   而那一块在飞书里是**可收起**的，8 条清单一铺开，链接就落到折叠区底部。
  //   Owner 的座位上看就是「**没有报告链接**」。
  //   报告链接是**要人去点的动作**（与结论行同级），不是逐条清单的脚注。
  //   判据也简单：一个必须被点开才看得见的链接，等于没有链接。
  // ── ★★ 2026-10-09：**命中原文 + 飞书直链**放进卡片正文 ──────────────────────
  //   位置：**在逐条清单之前**（结论行与读数之后）。
  //   为什么不是放末尾：同一天已经栽过一次 —— 报告链接原先放末尾，而那一块在飞书里是
  //   **可收起**的，8 条清单铺开就把链接压进折叠区，Owner 的座位上看就是「没有链接」。
  //   ⇒ **一个必须点开才看得见的东西，等于没有**。命中原文与直链是 Owner 点名要的，
  //     必须落在会被看到的位置。
  // ★★ 2026-10-09 晚（Owner：「业务同事都看不懂」）：**这块从卡上撤下来，改放报告。**
  //
  //   原先它被直接印进卡片正文。实测业务同事看不到 —— 因为它的内容是
  //   `BM25 205.8807 ｜ 飞书直链：取不到直链 ｜ source_sha256 77ac3d5f…`：
  //   **那是检索过程的读数，不是「哪里有问题、怎么改」。**
  //   判据（与 §5.3 同一条）：**卡上只放「让人能决定下一步」的东西。**
  //
  //   「搬是搬，砍是砍」：这些读数**一条不丢** —— 由 `hitsBlock` 原样返回，
  //   由 `merged_report.renderMergedReportMd` 放进报告的「附录：检索读数」。
  const hitsNote = '';   // ← 卡上不再印（保留这个名字，免得到处改；真正的搬运在 hitsBlock）
  const hitsBlock = kbHitsBlock || null;
  // ══════════════════════════════════════════════════════════════════════════
  // ★★ 2026-10-09（Owner 第三次追问后的**根因修正**）：**≥3 时只出分类汇总 + 报告链接**
  // ══════════════════════════════════════════════════════════════════════════
  //
  //   PRD §5.3.3 的原文（库侧权威实现 `kb/l5/p0_fastpath.py:391`）：
  //     ```
  //     if n >= 3:
  //         # PRD §5.3.3「≥3 个时只输出分类汇总 + 报告链接」
  //         L.extend(_summary_lines(findings))
  //         L.append("→ 查看完整问题清单与修改建议：%s" % report_ref)
  //     ```
  //
  //   而这里**从来不分条数**，永远把全部条目平铺在卡上 ⇒
  //     · Owner 看到「7 个问题都是平铺」—— **那本身就违反 PRD**；
  //     · 「链接看不见」只是**症状**：条目全在卡上，链接被挤到最后、又被收起。
  //   我此前三次修复都在治症状（挪链接位置），**第一次就没读懂这一条**。这是根因。
  //
  //   现在与库侧**同一套判据、同一个常数**（`REPORT_LINK_MIN_ISSUES`）：
  //     ≥3 ⇒ 卡片只出「· <大类>类问题：N 个」＋ 报告链接；逐条清单进报告
  //     <3 ⇒ 逐条平铺（1–2 条走逐条输出，PRD 就是这么定的）
  // ★★ 2026-10-09 晚（安全网，必须与上面那条一起看）：
  //   **只有「报告链接真的拿得到」时，才允许把逐条清单收进报告。**
  //
  //   为什么必须：≥3 时卡上只剩汇总行 —— 而汇总行**不含任何可执行内容**。
  //   若报告没建成（实测那一单：日志里既没有 `📄 合并报告已建` 也没有 `⚠️ 没建成`，
  //   卡上也没看到链接那一行），读者拿到的就是**「平台与促销类问题：2 个」＋一个空的链接位**
  //   —— 比改动之前（至少还有 7 条逐条）**更没法用**。
  //   所以：**拿不到可点的链接 ⇒ 退回逐条平铺**（宁可长，不可空）。
  //   判据看的是 `reportNote` 里到底有没有一个可点的链接，**不是** total 够不够。
  const linkLine = (reportNote.match(/^→ 查看完整问题清单与修改建议：(.*)$/m) || [])[1] || '';
  const hasReportLink = /^https?:\/\//.test(linkLine.trim());
  const summarized = total >= REPORT_LINK_MIN_ISSUES && hasReportLink;
  // ★★ 2026-10-14（Owner：「审核结论中 1，2...每条之间需要空一行的 …… 都要跟 prd 对齐」）──
  //
  //   PRD §5.3.2 / §5.3.3 的逐字形状（回源飞书 PRD wiki rev 36 ＋ 本地 `kb/.work/prd.md`，
  //   两份一致；下面 `␤` 是空行）：
  //
  //       【审查结论：REVIEW】共发现 2 处需人工确认。
  //       ␤
  //       1.【合规-医疗宣称】……
  //         原因：……
  //         依据：……
  //       ␤
  //       2.【消费者安全-使用姿势】……
  //       ␤
  //       建议转 @法务 @医学顾问 复核。
  //
  //   ⇒ **结论行之后一个空行 · 每条之间一个空行 · 动作行之前一个空行**。
  //
  //   改前实测的坏形状（不是「一条空行都没有」这么简单，而是**空行数不对**）：
  //     · 2 条：结论行→第 1 条**没有**空行；第 2 条之后**三个**空行才到动作行；
  //     · ≥3 汇总：链接与动作行之间**两个**空行。
  //   根因是三个空行来源叠在一起（`renderMergedItem` 结尾自带的空行、`items.join('\n\n')`
  //   的分隔、拼装处的 `\n\n`）—— 各加一段就多一段。
  //
  //   ⇒ 口径：**条目在这里先收尾成一个整块**（去掉各自尾随的空行），
  //     块间与块后的空行由**拼装那一处**统一给。空行只有一个来源，就不会再叠。
  const itemBlocks = items.map((b) => String(b ?? '').replace(/\n+$/, ''));
  const bodyText = summarized ? categorySummary(list, total) : itemBlocks.join('\n\n');
  // ══════════════════════════════════════════════════════════════════════════
  // ★★ 2026-10-13（Owner 裁定）：**库侧/模型侧的口径读数与解释不上卡，只留在守衡的记忆里**
  // ══════════════════════════════════════════════════════════════════════════
  //
  //   Owner 原话（三条里第 1、2 条）：
  //     「输出到飞书群包含知识库侧+模型侧的文字，**不要展示在卡片上**，我问的时候，你要能回答」
  //     「类似以下的文案都去掉：知识库侧 未报内容问题…／模型侧 7 条… ／ ℹ️ 知识库侧给了
  //       覆盖缺口（`coverage_not_covered`）… ／（问题数 8 ≥ 3 ⇒ 按 PRD §5.3.3 只出分类汇总…）」
  //
  //   为什么这一整族都搬走（`tally`/`gapNote`/`covNote`/`noReadNote`/`candNote`/汇总页脚）：
  //     它们是**我们自己核对用的口径读数** —— 讲的是「这一单里哪一侧说了话、有几条没并进来、
  //     与 PRD §5.3.3 是什么关系」。对群里的人，那是**零可执行信息**；
  //     而 PRD §5.3.3 给 ≥3 的单子规定的卡面只有四样：结论行 · 分类汇总 · 报告链接 · 动作行。
  //
  //   ★ 但**一个字都没丢**（搬是搬，砍是砍）—— 它们原样从 `internalNotes` 出去，
  //     由 `agent.mjs` 接进 `chainBlock`（= 模型的上下文 + **会话记忆**）：
  //     对方追问「知识库侧报了几条 / 为什么说是覆盖缺口」，守衡答得出来。
  //     ⚠️ 它们**不许**再回到 `block` —— 卡片与报告都是 `block` 渲染的。
  const summaryFootnote = summarized
    ? `（问题数 **${total} ≥ ${REPORT_LINK_MIN_ISSUES}** ⇒ 按 PRD §5.3.3 只出分类汇总，`
      + '逐条清单与修改建议在报告里；1–2 条时才在卡上逐条平铺。）'
    : '';
  // ══════════════════════════════════════════════════════════════════════════
  // ★★ 2026-10-13：**P0 快路那条边界改由代码给**（原先只有模型原话里那一份）
  // ══════════════════════════════════════════════════════════════════════════
  //   为什么必须补：Owner 同一天要求「模型原话那一组从卡上整组去掉」（见 `envelope.mjs`
  //   的 autoCard）。而这条边界**只出现在模型原话里** —— 原话一走，卡上就没有任何东西
  //   说得出「这是红线拦截、**没有跑过专项审查**」了。
  //   而这句话不能丢，它是 Owner 2026-10-12 要求恢复的三样之一
  //   （`agent.mjs` 原位注释记着：「逐条明细 ＋ 页脚『本结论为 P0 红线拦截…』—— 三样都在」）：
  //   少一句，读卡的人就会把一次**确定性匹配**当成「整条链审过了」。
  //   措辞与那一版同源（08:56 那张卡的卡脚），只把模态说全（图/视频/产品宣称），
  //   因为 P0 快路对三类素材走的是同一条路。
  const p0Boundary = kb?.source === 'p0_fastpath'
    ? '本结论为 **P0 红线拦截**（确定性匹配，**未跑**专项审查、层前置与评审链），'
      + '**不是 PASS 依据**；若素材属图片 / 视频 / 产品宣称等模态，**仍需转对应专项复核**。'
    : '';
  // ⚠️ `candNote` 已经拼在 `tally` 里面（见上面那一行 `+ candNote +`），别再列一次。
  // ★★ 2026-10-13（Owner：「整个都隐藏，不要展示在卡片上」）：**P0 快路那条边界也并进这里**。
  //   它原先是卡脚（`boundary` 格），而那一格现在整格作废 ⇒ 不挪过来就是**静默消失**
  //   （「未跑专项审查 / 仍需转对应专项复核」这句话必须还在，只是不上卡）。
  const internalNotes = [tally, gapNote, covNote, noReadNote, p0Boundary,
    summaryFootnote ? `\n${summaryFootnote}` : '']
    .map((x) => String(x ?? '').trim())
    .filter(Boolean).join('\n').trim();
  return {
           line, total, kbGap, refused: false, coverageGap: !!kb?.coverageGap,
           kbNoReading, covEntries, kbContentN, modelFailed, reportNote, summarized,
           // ★ 2026-10-14：**这一单转给谁**（PRD §5.4 的 JSON 规范里就有 `next_owners`）。
           //   与 `action` 同一份读数 —— 卡上印的是它渲染出来的句子，下游（表行 / 报告）
           //   拿到的是结构化的那几个角色位。留痕用，不是第二份口径。
           nextOwners: must ? [] : routing.owners,
           routingSource: routing.source,
           routingVersion: routing.version,
           routingUnmatched: routing.unmatched,
           // ★ 卡上不印了 ⇒ 由这里原样交出去，报告把它放进附录（搬不是砍）
           hitsBlock,
           // ★ 2026-10-13：库侧/模型侧的口径读数与解释 —— **只走这里**（模型上下文 + 记忆），
           //   既不进卡片也不进报告正文。空串 = 这一单没有这类读数。
           internalNotes,
           // ★★ 2026-10-14（Owner：「修改建议的链接，预期放在『建议转』这行的上面，跟 PRD 对齐」）：
           //   **次序修回 PRD §5.3.2 / §5.3.3 的逐字次序**。回源核过飞书 PRD 正文
           //   （wiki `NB55wAq8liEOdKkquL2cgtPEnmg`，rev 36）与本地 `kb/.work/prd.md`，两份一致：
           //       结论行 → `· <大类>类问题：N 个`（分类汇总）→ `→ 查看完整问题清单…` → 动作行
           //   而这里原先写的是 `${line}${reportNote}\n${bodyText}` —— **链接被拼在汇总之前**
           //   ⇒ 群里看到的就是「链接 → 汇总」，与 PRD 相反（Owner 截图当场指出）。
           //   ⚠️ 2026-10-09 那次「链接提到抬头下面」的诉求**没有被推翻**：它要防的是
           //      「链接被埋在 8 条逐条之后、落进可折叠区」—— 现在的次序里 link 仍紧跟在
           //      汇总（≥3 时汇总只有 1–4 行）之后、逐条**之上**，两个诉求同时满足。
           //   ⚠️ 与库侧 `review_engine.render_summary` 同一次序（那边本来就是
           //      `_summary_lines` 再 `→ 查看完整问题清单`），两处不许再各写一份。
           // ★★ 2026-10-14：**分段空行只从这一处给**（PRD §5.3.2 的逐字形状）——
           //   结论行 ␤ 正文（逐条之间已由上面 `bodyText` 的 `join('\n\n')` 空开）␤ 动作行。
           //   拼装点原先写的是 `${summarized ? '' : '\n'}\n\n` —— 逐条那一路因此多出一个空行、
           //   汇总那一路则把「链接→动作行」挤成零空行。现在统一：
           //   `bodyText` 有内容就给一个空行，没有就不留孤立的空行。
           block: `${line}\n\n${bodyText}${reportNote}${hitsNote}`
             + `${bodyText ? '\n\n' : '\n'}${action}` };
}

/**
 * ≥3 时的**分类汇总**（PRD §5.3.3 要的那一格）：`· <大类>类问题：N 个`。
 *
 * ★ 与库侧 `_summary_lines` / `_category_counts` **同口径**：按**大类**（`catFamily`）合并，
 *   不按子类 —— 子类太细，汇总就没意义了。
 * ★ 为什么必须给总数：汇总行加起来可能小于 `total`（库侧有明细没并进来时），
 *   那时只说分类会让人以为「就这么多」⇒ 多出来的那部分要有一行交代。
 *
 * ★★ 2026-10-13（Owner 裁定）：**页脚那句「（问题数 N ≥ 3 ⇒ 按 PRD §5.3.3 只出分类汇总…）」
 *   从卡上撤掉了** —— 它讲的是我们自己的口径规矩，对群里的人是零可执行信息
 *   （Owner 原话把它列进了「类似以下的文案都去掉」那一串）。
 *   它**没有丢**：原样落在 `renderMerged` 的 `internalNotes` 里（守衡凭它答追问），
 *   所以这个函数现在**只产出 PRD §5.3.3 要的那几行**，一句解释都不带。
 */
export function categorySummary(list = [], total = null) {
  const counts = new Map();
  for (const f of list) {
    const fam = catFamily(f?.category) || '未分类';
    counts.set(fam, (counts.get(fam) ?? 0) + 1);
  }
  // ★ 2026-10-14：**行间空一行**（PRD §5.3.2 的 `· …` 三行之间各有一个空行）。
  const rows = [...counts.entries()].sort((a, b) => b[1] - a[1])
    .map(([fam, n]) => `· ${fam}类问题：${n} 个`);
  if (!rows.length) rows.push('·（本次没有并进任何逐条）');
  const n = total ?? list.length;
  if (n > list.length) {
    // ⚠️ 这一行**必须留**：没有它，读者把分类行加起来会小于抬头那个数
    //   （实测 19:08 那单：抬头 12、分类只有 7）—— 那是「卡内算术不闭合」，
    //   比多一句话坏得多。它只说「还有 N 条在哪」，不下口径解释。
    rows.push(`· 另有 **${n - list.length} 条**（明细在报告里）`);
  }
  // 逐行空开（与库侧 `_summary_lines` 同形：那边也是每行之间空一行）
  return rows.join('\n\n');
}

/* ═══════════════════ 运行入口（必须在**文件末尾**）═══════════════════
 * ★ 2026-10-06 踩过：它原先夹在文件中间，而后加的 `COVERAGE_CATEGORY` 是 const ——
 *   运行块先执行 ⇒ **TDZ 报错**（Cannot access before initialization）。
 *   一个自证脚本自己崩掉、连断言都没跑到，比断言写错更糟。
 */
if (process.argv[1] && process.argv[1].endsWith('dual_track.mjs') && process.argv.includes('--selftest')) {
  process.exit(selftest() || selftestExtract());
}
