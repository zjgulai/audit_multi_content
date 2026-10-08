/**
 * model_side.mjs —— 双轨里的**模型侧那一遍**（PRD 上游技术方案 §③「知识库＋大模型 双校验」）
 *
 * ── 它是什么、不是什么 ─────────────────────────────────────────────────
 * 方案原文：
 *   `模型侧：语义核查与边界判断 → 命中带 位置与理由（无库内依据）`
 *   `**没有主判与辅助之分** —— 每层的两侧都是完整的一遍审查，各自出问题清单`
 *
 * 所以这一遍**不许看知识库**：不给它条款、不给它检索结果、也不给它链的结论。
 * 它只看**素材本身**（图上的字 / 关键帧上的字 / 音轨转写），凭语义与常识出清单。
 * 它出的每一条都**没有库内依据** —— 合并时按方案降为 REVIEW，不由它单独定 BLOCK。
 *
 * ── 为什么提示词里要写死那几条「不许」──────────────────────────────────
 * 这一遍唯一的失败模式是**编**：模型很容易为了「有产出」而把
 * 「我读不到画面」或「这段没字」写成一条问题。那种条目会直接抬高结论严重度，
 * 而它是**无中生有**。所以提示词里三处硬约束 + 解析侧一道闸（`parseFindings` 会丢掉
 * 类目不在闭集、或理由为空的条目，并把丢掉几条**如实报出来**，不静默吞）。
 *
 * ── 失败怎么办 ─────────────────────────────────────────────────────────
 * 模型侧**跑不成不算失败**：返回 `{ok:false}`，调用方回落成**单轨（只有知识库）**，
 * 结论一个字不改。绝不允许「模型侧坏了 ⇒ 这一单没结论」——
 * 那是把一条新增的旁路变成了新的单点故障。
 */

/** 类目闭集（与 PRD §5.3 的「维度标注」同一套词）。不在闭集里的一律丢掉。 */
export const CATEGORIES = Object.freeze([
  '合规', '消费者安全', '措辞表达', '产品描述', '隐私', 'AI 披露', '本地化',
]);

/** 模型侧只看得到文字层。这条要说在前面，否则它会去「评价画面」。 */
export const SYSTEM = [
  '你是内容合规审查里的**模型侧**。它与知识库侧**并行、互不参照**：',
  '你看不到任何知识库条款、检索结果或他人的结论，也不许引用条款号。',
  '你只做一件事：读下面这段**素材的文字层读数**（图上的字 / 视频关键帧上的字 / 音轨转写），',
  '凭语义、常识与平台惯例，列出**你发现的问题**。',
  '',
  '硬约束（违反的条目会被丢弃）：',
  '1. **没有发现就返回空数组 `[]`。** 不许为了「有产出」而编 —— 空的清单是有效结论。',
  '2. **不许把「我看不到画面」写成问题。** 画面层不在你的输入里，那是能力边界，不是内容风险。',
  '3. **不许把「这段没有可读文字」写成问题。** 同上。',
  '4. 每条必须指得出**位置**（第几帧 / 图上哪个位置 / 转写的哪一句）与**理由**。',
  '5. 你出的每一条都**没有库内依据** —— 所以它最高只能到 REVIEW，不要给 BLOCK。',
  '',
  '输出：**只输出一个 JSON 数组**，不要解释、不要 markdown 代码块。每项形如',
  '{"location":"帧 3","category":"消费者安全","severity":"REVIEW","reason":"一句话说清问题","excerpt":"逐字引用的原文"}',
  `category 只能取：${CATEGORIES.join(' / ')}。`,
].join('\n');

/**
 * 拼给模型侧的那一段（**纯函数** —— 喂样本就能断言，不必真调模型）。
 * @param {{readings?:string, question?:string}} a
 * @returns {string}
 */
export function buildPrompt({ readings = '', question = '' } = {}) {
  const q = String(question ?? '').trim();
  const r = String(readings ?? '').trim();
  return [
    q ? `【对方的话】${q}` : '',
    '【素材的文字层读数】',
    r || '（没有读到任何文字 —— 这种情况下应当返回空数组）',
  ].filter(Boolean).join('\n');
}

/**
 * 解析模型侧的输出（**纯函数**）。宽容地取第一个 JSON 数组，但**逐条验**：
 * 类目必须在闭集里、理由必须非空、严重度只认 BLOCK/REVIEW。
 *
 * ★ 丢掉几条要**报出来**（`dropped`），不许静默吞 —— 静默吞的后果是
 *   「模型侧明明报了 5 条，合并里只有 2 条」而没有任何东西说得清另外 3 条去哪了。
 *
 * @returns {{ok:boolean, findings:Array, dropped:Array, error:string|null}}
 */
export function parseFindings(text) {
  const s = String(text ?? '');
  const a = s.indexOf('['); const b = s.lastIndexOf(']');
  if (a < 0 || b <= a) return { ok: false, findings: [], dropped: [], error: '输出里没有 JSON 数组' };
  let arr;
  try { arr = JSON.parse(s.slice(a, b + 1)); } catch (e) {
    return { ok: false, findings: [], dropped: [], error: `JSON 解析失败：${e?.message ?? e}` };
  }
  if (!Array.isArray(arr)) return { ok: false, findings: [], dropped: [], error: '解析出来不是数组' };

  const findings = []; const dropped = [];
  for (const [i, raw] of arr.entries()) {
    const reason = String(raw?.reason ?? '').trim();
    const category = String(raw?.category ?? '').trim();
    if (!reason) { dropped.push({ i, why: '理由为空' }); continue; }
    if (!CATEGORIES.includes(category)) { dropped.push({ i, why: `类目不在闭集：${JSON.stringify(category)}` }); continue; }
    const sev = String(raw?.severity ?? '').trim().toUpperCase();
    findings.push({
      location: String(raw?.location ?? '').trim() || '（未给位置）',
      category,
      // 「不由它单独定 BLOCK」在**合并**那一步执行（`dual_track.mergeFindings`）；
      // 这里如实记下它原本要的严重度 —— 不假装它没说过（§2.4.1：读数不许比输入小）。
      severity: sev === 'BLOCK' ? 'BLOCK' : 'REVIEW',
      reason,
      excerpt: String(raw?.excerpt ?? '').trim() || null,
      basis: 'model',      // 无库内依据
    });
  }
  return { ok: true, findings, dropped, error: null };
}

/**
 * 跑模型侧那一遍。
 *
 * @param {{readings:string, question?:string, ask:Function, maxTokens?:number}} a
 *        `ask` 注入（`llm.ask`）—— 生产用它，测试喂桩。
 * @returns {Promise<{ok:boolean, findings:Array, raw?:string, dropped?:Array, ms:number, error?:string}>}
 */
// ★ 2026-10-06 实测：`maxTokens = 1200` 时**正文 0 字**（`raw.length === 0`），
//   报的是「输出里没有 JSON 数组」—— 看起来像模型不听话，其实是**额度被 reasoning 烧光了**。
//   同一个提示词、同一张图：1200 ⇒ 0 字 / 6565ms；4000 ⇒ 1038 字 / 5 条 finding / 8886ms。
//   这就是内核里记过的那个病（`agent.mjs` 的「模型烧光额度没写出正文」），
//   所以这里默认给 4000 并**在日志里报 raw 长度** —— 空正文与「没报问题」必须长得不一样。
export async function reviewModelSide({ readings, question = '', ask, maxTokens = 4000 } = {}) {
  const t0 = Date.now();
  const noRead = !String(readings ?? '').trim();
  // 「没读到任何文字」时**不调模型**：那是确定性的事实，问一次模型只会换来编造。
  if (noRead) return { ok: true, findings: [], ms: 0, skipped: '文字层是空的 —— 模型侧无需跑，也不会编' };
  if (typeof ask !== 'function') return { ok: false, findings: [], ms: 0, error: '没有可用的 llm.ask' };
  try {
    const raw = await ask(buildPrompt({ readings, question }), { system: SYSTEM, maxTokens });
    const p = parseFindings(raw);
    return { ...p, raw, ms: Date.now() - t0 };
  } catch (e) {
    // 模型侧跑不成**不算失败**：调用方回落单轨，结论一个字不改。
    return { ok: false, findings: [], ms: Date.now() - t0, error: `${e?.message ?? e}` };
  }
}

/**
 * 把内核的媒材读数摊成**模型侧要看的文字层**（**纯函数**）。
 *
 * ★ 只给**文字层**：图上的字、关键帧上的字、音轨转写。
 *   画面本身不在这里 —— 这套系统看不到画面（PRD 把「视频深度识别」列为后续扩展），
 *   把「没有画面」喂进去只会换来模型编一段「画面描述」。所以这里给什么，
 *   提示词里就写死「不许评价画面」（见 `SYSTEM`）。
 */
export function readingsForModelSide(inbound) {
  if (!inbound) return '';
  const parts = [];
  // ★ 2026-10-06 补：**纯文案也必须进来**。
  //   原先这里只收媒材的文字层（图上字 / 帧上字 / 转写），于是纯文案单的 readings 是**空串**，
  //   `reviewModelSide` 见空即跳过 ⇒ **文案只有知识库单轨，模型侧那一遍根本没跑**。
  //   而方案要的是「每层都同时开知识库侧＋模型侧」，文案恰恰是**最常见的一态** ——
  //   漏了它，等于「双轨」只对少数带媒材的单子成立。
  //   （这个洞是 Owner 2026-10-06 追问「文案/图片/视频/链接都可以跑知识库+模型吧？」时
  //    逐态核出来的；我原来的四形态自测第①态传了 `ask: null`，**把它盖住了**。）
  const body = String(inbound.text ?? '').trim();
  if (body) parts.push('【素材正文】\n' + body);
  // 链接单：文字层就是那条链接本身（正文内容由链那一侧去读，见 model_side 的边界说明）。
  for (const u of inbound.links ?? []) {
    if (String(u ?? '').trim()) parts.push('【待审链接】\n' + String(u).trim());
  }
  for (const i of inbound.images ?? []) {
    if (String(i?.text ?? '').trim()) parts.push('【图 ' + i.index + ' 上的字】\n' + String(i.text).trim());
  }
  for (const v of inbound.videos ?? []) {
    if (v?.failed) continue;
    const fr = (v.frames ?? []).map((f) => String(typeof f === 'string' ? f : (f?.text ?? '')).trim()).filter(Boolean);
    if (fr.length) parts.push('【视频 ' + v.index + ' 关键帧上的字】\n' + fr.join('\n'));
    const t = v.transcript ?? {};
    if (t.ok && String(t.text ?? '').trim()) parts.push('【视频 ' + v.index + ' 音轨转写】\n' + String(t.text).trim());
  }
  return parts.join('\n\n');
}
