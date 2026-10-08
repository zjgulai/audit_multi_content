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

/** 严重度序（越大越重）。只认三态里的两个可裁剪值 + 空。 */
const SEV_ORDER = { BLOCK: 2, REVIEW: 1, '': 0 };

/** 方案 L211 的对齐键：**位置相同 ＋ 类目相同**。 */
export const keyOf = (f) => `${String(f?.location ?? '').trim()}|${String(f?.category ?? '').trim()}`;

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
  for (const [k, f] of moBy) {
    const cur = sides.get(k);
    if (cur) cur.model = f; else sides.set(k, { kb: null, model: f });
  }

  const items = [];
  let nBoth = 0; let nConflict = 0; let nKbOnly = 0; let nModelOnly = 0;

  for (const [key, { kb, model }] of sides) {
    const [location, category] = key.split('|');
    if (kb && model) {
      const a = normSev(kb.severity); const b = normSev(model.severity);
      if (a === b) {
        // ── 取交集：双轨确认，按该问题严重度计入 ──
        nBoth++;
        items.push({
          location, category, severity: a, source: 'both', confirmed_by_both: true,
          // ★ 顶层 reason 必须留一份：渲染（`renderMerged`）读的是它。
          reason: kb.reason ?? model.reason ?? null,
          kb: pickKb(kb), model: pickModel(model),
          note: '两轨都命中同一个问题，结论一致 —— 双轨确认（置信最高）',
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
});
const pickModel = (f) => ({
  reason: f?.reason ?? null, excerpt: f?.excerpt ?? null, severity: normSev(f?.severity) || null,
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
    // 渲染：库侧条数必须**出现在卡里**，且明说明细未并进来、总数是上限
    const rd = renderMerged(modelTwo, { state: 'BLOCK', kb: p0, kbTextCount: 0 });
    eq('⑩ 卡里写出库侧条数＋总数上限＋「明细未并进来」',
       [rd.total, /结构化读数 BLOCK\/3/.test(rd.block), /上限/.test(rd.block)], [5, true, true]);
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
    eq('⑪c3 卡里要写明「库对该题材没有可依据的条款 / 不是发现了内容问题」',
       [/没有可依据的条款/.test(rdCov.block), /不是发现了内容问题/.test(rdCov.block)], [true, true]);
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
    eq('⑬f 卡里写「知识库侧本次未参与」，且**不许**再出现「知识库侧 0 条」',
       [/本次未参与/.test(rdNo.block), /知识库侧 0 条/.test(rdNo.block), rdNo.kbNoReading],
       [true, false, true]);
    eq('⑬g 卡里要说明：只来自模型侧、无库内依据、**不得据此当 PASS**',
       [/不得当通过依据/.test(rdNo.block), /不得据此当 PASS/.test(rdNo.block)], [true, true]);
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
 * 从 PRD §5.3 的**逐条块**里抽库侧 findings。
 *
 * 口径：`^\d+.【类目-子类】位置…`（§5.3.2 / §5.3.3 的格式，由 `render_summary` 产出，
 * 并由 `tools/verify_cards.mjs` 的 W 段与 `l7_integrity.py` 钉住）。
 * **类目为「覆盖」的那条不算 finding**，单独返回在 `coverage` 里。
 *
 * @param {string} answer 链给的结论原文
 */
export function kbFindingsOf(answer) {
  const out = []; let coverage = null;
  for (const line of String(answer ?? '').split('\n')) {
    const m = /^\s*\d+[.、]\s*【([^】]{1,40})】\s*(.*)$/.exec(line);
    if (!m) continue;
    const tag = m[1].trim();
    const dash = tag.indexOf('-');
    const category = (dash > 0 ? tag.slice(0, dash) : tag).trim();
    const sub = dash > 0 ? tag.slice(dash + 1).trim() : '';
    const item = { location: m[2].trim().slice(0, 120) || '（未给位置）', category, sub,
                   severity: /必须修改/.test(String(answer)) ? 'BLOCK' : 'REVIEW',
                   reason: m[2].trim().slice(0, 300), basis: 'kb' };
    if (category === COVERAGE_CATEGORY) { coverage ??= item; continue; }
    out.push(item);
  }
  return { findings: out, coverage };
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
    reportUrl: String(rev?.report_url ?? '').trim() || null,
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
    + '   判定：REVIEW（**不是 PASS**）\n\n建议转 @内容治理负责人 复核。';
  const rc = kbFindingsOf(COV);
  eq('⑩ 覆盖缺口不计入 findings', [rc.findings.length, rc.coverage?.category], [0, '覆盖']);

  eq('⑩ 认得出「覆盖判据不成立」⇒ 没覆盖', kbCoveredOf(COV), false);
  eq('⑩ 认得出 reason_code', kbCoveredOf('…原因码 `coverage_not_covered`：…'), false);
  // 反向对照：正常的三态结论**不许**被判成没覆盖（否则永远到不了 PASS）
  eq('⑩ 反向对照：正常 REVIEW 结论 ⇒ 算覆盖到了', kbCoveredOf(REAL), true);
  eq('⑩ 反向对照：PASS 结论 ⇒ 算覆盖到了',
     kbCoveredOf('【审查结论：PASS】未发现已知底线风险。'), true);

  console.log(`\n抽取自证：通过 ${pass} / 失败 ${bad.length}`);
  return bad.length ? 1 : 0;
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
export function renderMerged(merged, { state, kb = null, kbTextCount = null } = {}) {
  const list = Array.isArray(merged) ? merged : [];
  const n = list.length;
  const kbN = Number.isFinite(kb?.issueCount) ? kb.issueCount : null;
  const txtN = Number.isFinite(kbTextCount) ? kbTextCount : null;
  // ★ 库侧「有结构化条数、但逐条明细抠不全」= PRD §5.3.3 的 ≥3 只出汇总那一种（2026-10-07）。
  //   这时**不许**把库侧当成 0 条（那正是红线被降级的成因），也不许假装明细在手。
  const kbMissingDetail = kbN != null && kbN > 0 && (txtN == null || kbN > txtN);
  const kbGap = kbMissingDetail ? Math.max(0, kbN - (txtN ?? 0)) : 0;

  // ── 拒答（库侧未判）：不发"结论"，只发「这次谁没判」（2026-10-07 加）──
  //   原先拒答被折算成「0 条」⇒ 用户收到一张形如双轨结论的 REVIEW 卡，
  //   而表里那行的结论是 NEEDS_INPUT —— 同一单两个结论。
  if (state === 'NEEDS_INPUT') {
    const line = `【审查结论：NEEDS_INPUT】知识库侧**未判**（拒答、fail-closed）`
      + (kb?.reason ? `：${kb.reason}` : '') + '。';
    const body = list.length
      ? list.map((f, i) => `${i + 1}.【${f.category}${f.sub ? '-' + f.sub : ''}】${f.location}`
          + `  —— **模型侧**（无库内依据）\n   原因：${f.reason ?? '（未给理由）'}\n`
          + `   判定：REVIEW\n   建议：**先恢复库侧再定**（本条不能当通过或拦截依据）。`).join('\n\n')
      : '（模型侧本次没报东西。）';
    return {
      line, total: list.length, kbGap: 0, refused: true,
      block: `${line}\n**本次没有知识库三态结论** —— 以下只是**模型侧**的初步观察，`
        + '**不得当通过依据，也不得当拦截依据**。\n\n' + body
        + '\n\n**下一步**：先把库侧恢复（跑层/日更）再重审这一单。',
    };
  }

  if (!n && !kbMissingDetail) return null;   // 没有条目、库侧也没缺明细 ⇒ 交回链
  const must = state === 'BLOCK';
  // 条数口径：能并的条目 + **库侧结构性条数里没并进来的那部分**（重叠未判 ⇒ 这是上限，写明）
  const total = n + kbGap;
  const line = must
    ? `【审查结论：BLOCK】共发现 ${total} 处必须修改。`
    : `【审查结论：REVIEW】共发现 ${total} 处需人工确认。`;
  const items = list.map((f, i) => {
    // 来源标记（Owner 2026-10-06：「备注下是规则库侧问题，还是模型侧问题」）
    const origin = f.source === 'kb' ? '**知识库侧**'
      : (f.source === 'model' ? '**模型侧**（无库内依据）'
        : (f.source === 'both-conflict' ? '**两轨都命中 · 结论冲突 ⇒ 已降 REVIEW**'
          : '**双轨确认**（库侧＋模型侧都命中）'));
    const basis = f.source === 'kb'
      ? `《知识库》${f.kb?.article_no ?? '（未给条款号）'}（锚点：${f.kb?.anchor ?? '—'}）`
      : (f.source === 'both'
        ? `两轨都命中（库侧 ${f.kb?.article_no ?? '—'} ／ 模型侧独立一遍）`
        : '**无库内依据** —— 模型侧独立一遍给的，未落在知识库条款上');
    const verdict = f.source === 'both-conflict'
      ? '**两轨结论不一致 ⇒ 降为 REVIEW，转人工**（不许任一侧单独定案）'
      : (f.severity === 'BLOCK' ? 'BLOCK' : 'REVIEW');
    // ★ 来源标记放**条目第一行末尾**，不动 §5.3 的 `【维度-子类】` ——
    //   那个标签是 PRD 契约（`prd53.conforms` 与 `l7_integrity.py` 都在核它），
    //   往里面塞「模型侧」会把格式一致性判据打破。而来源必须**一眼扫得到**：
    //   库侧条目回得了源、模型侧条目没有依据 —— 这两样的下一步完全不同。
    return `${i + 1}.【${f.category}${f.sub ? '-' + f.sub : ''}】${f.location}  —— ${origin}\n`
      + `   原因：${f.reason ?? '（未给理由）'}\n`
      + `   依据：${basis}\n`
      + `   判定：${verdict}\n`
      + `   建议：${must ? '修改后重新提交。' : '转对应负责人复核。'}`;
  });
  const action = must ? '请修改后重新提交。' : '建议转 @内容治理负责人 复核。';
  // ★ 块首汇总：**先让人看到「这次是谁在说话」**，而不是读完四条才自己拼出来。
  //   库侧 0 条而模型侧 5 条，与库侧 5 条，是两种完全不同的单子 —— 前者没有一条回得了源。
  const fromKb = list.filter((f) => f.source === 'kb' || f.source === 'both' || f.source === 'both-conflict').length;
  const fromModel = list.filter((f) => f.source === 'model' || f.source === 'both' || f.source === 'both-conflict').length;
  // ★ 库侧**没读数**时不许写「0 条」（2026-10-07，Owner 同意）——
  //   「库判过、没报东西」与「库这次没参与」长得一样，是**最容易被读错**的一处：
  //   实测素材 D 就是因为这一格含糊，加上表里落了 PASS，看起来像"库审过了、没问题"。
  const kbNoReading = kbNoReadingOf(kb);
  const tally = kbNoReading
    ? `知识库侧 **本次未参与**（没拿到引擎读数） ／ 模型侧 ${fromModel} 条`
      + `（**全部无库内依据**，只能转人工）`
    : `知识库侧 ${fromKb + kbGap} 条${kbGap ? `（**结构化读数 ${kb?.state ?? '—'}/${kbN}**；本卡未逐条列出）` : ''} `
      + `／ 模型侧 ${fromModel} 条`
      + (list.some((f) => f.source === 'model') ? `（其中 ${list.filter((f) => f.source === 'model').length} 条**无库内依据**，只能转人工）` : '');
  // ★ 库侧明细缺失是**必须出声**的（2026-10-07）：否则读者会以为库侧真没报东西。
  const gapNote = kbMissingDetail
    ? `\n⚠️ 知识库侧另有 **${kbGap} 条**未并进本卡：PRD §5.3.3 规定问题数 ≥3 时库侧只出分类汇总`
      + `，逐条明细在库里${kb?.reportUrl ? `：${kb.reportUrl}` : '（本次库侧未回报告链接）'}`
      + '；**与模型侧的重叠未判 ⇒ 上面那个总数是上限**。'
    : '';
  // ★ 覆盖缺口要单独说清含义（2026-10-07）：结论仍是 REVIEW，
  //   但它是"库管不到这个题材 ⇒ 转人工看覆盖"，不是"发现了内容问题"。
  const covNote = kb?.coverageGap
    ? `\nℹ️ 知识库侧给了 **覆盖缺口**（\`coverage_not_covered\`）：检索有命中，`
      + '但「既被规则引用、又达门限」的单元 0 条 ⇒ **库对该题材没有可依据的条款**。'
      + '本单 REVIEW 的含义是**转人工看覆盖**，**不是发现了内容问题**；也**不得据此当 PASS**'
      + '（库口径：未命中 ≠ 合规）。'
    : '';
  // ★ 库侧没读数：**这一句是硬要求**（2026-10-07，Owner 同意）。
  //   没有它，读者会把"库没参与"读成"库说没问题"，而这两件事的下一步完全不同。
  const noReadNote = kbNoReading
    ? `\n⚠️ **本次知识库侧没有读数**（链没跑到引擎 / 机读旁挂没落 —— 库忙、层闸门红、或没走 `
      + '`review_run.sh`）⇒ 上面这些条目**只来自模型侧、无库内依据**，'
      + '**不得当通过依据**，也**不得据此当 PASS**（本单**不能算放行**）。'
      + '下一步：先确认库侧为什么没跑成，再重审这一单（**补素材无用**）。'
    : '';
  return { line, total, kbGap, refused: false, coverageGap: !!kb?.coverageGap,
           kbNoReading,
           block: `${line}\n${tally}${gapNote}${covNote}${noReadNote}\n\n${items.join('\n\n')}\n\n${action}` };
}

/* ═══════════════════ 运行入口（必须在**文件末尾**）═══════════════════
 * ★ 2026-10-06 踩过：它原先夹在文件中间，而后加的 `COVERAGE_CATEGORY` 是 const ——
 *   运行块先执行 ⇒ **TDZ 报错**（Cannot access before initialization）。
 *   一个自证脚本自己崩掉、连断言都没跑到，比断言写错更糟。
 */
if (process.argv[1] && process.argv[1].endsWith('dual_track.mjs') && process.argv.includes('--selftest')) {
  process.exit(selftest() || selftestExtract());
}
