/**
 * advice.mjs —— **「建议」的唯一产出者**（Owner 2026-10-09 定的规则）
 *
 * ── Owner 的原话
 *
 * > 「现在是建议必须具体内容。负面样本『建议』列填充 47% ⇒ **有填的做参考，agent 输出最终具体建议**；
 * >   **没填的不用参考，不用管，agent 直接出建议**。」
 *
 * ── 为什么要有它：把「两个产出者」变成一个
 *
 *   在此之前 `建议` 有两个来源 —— 库侧原话（源表那 47%）与模型侧自己写的 —— 于是：
 *     · 库侧给了就印库侧的，模型那条被**静默丢掉**（它可能更贴素材）；
 *     · 来源标不清（「双轨确认」那条其实是库侧给的，却读起来像两侧合成）；
 *     · 库侧没填时，若模型也没给，就只剩一句「转对应负责人复核」。
 *   今天所有关于「建议」的毛病，根都是**两个产出者**。
 *   现在：**条目清单 + 库侧参考（可空） → 一次调用 → 每条一句改法**，唯一产出者。
 *
 * ── 时序：为什么必须等两侧都回来
 *
 *   模型侧与链**并行**跑（链 2~17 分钟，模型侧 ~14 秒）⇒ 模型侧产出它的发现时，
 *   库侧的建议**还没到**。所以「有填的做参考」只能**在两侧都回来之后**补这一次调用。
 *   代价是多一次 LLM 调用（约 5~15 秒），换来的是**不动那条判定链**。
 *
 * ── 三条纪律
 *
 *   ① **参考 ≠ 照抄**：提示词里明说库侧那格是参考，可以为空；最终句子由模型按素材写。
 *   ② **失败不编**：调用失败/解析失败 ⇒ 返回 `{}`，调用方**回退**到原有逻辑（库侧原话 →
 *      模型原话 → 如实说没有）。**绝不**在这里造一句顶上去。
 *   ③ **标注要说「参考了什么」，不是「谁给的」** —— 改法**始终是模型写的**，
 *      所以标成「库侧给的改法」会是假陈述（这也是安全阀，见 `renderMergedItem`）。
 */

const SYSTEM = [
  '你在给一份已经判完的内容审查，**逐条写具体改法**。',
  '每条只写一件事：**怎么改**。改哪个词、换成什么、删哪句、补什么。',
  '',
  '硬约束：',
  '1. **不许写没有动作的话** —— 「转对应负责人复核」「请人工确认」「建议修改」「需进一步核实」',
  '   这类一律不合格：收到它的人还是不知道该改什么。',
  '2. 若某条**确实写不出具体改法**，就写清**缺什么信息才能定**（例：「需要知道投放在哪个平台',
  '   才能定这句促销语合不合规」）—— 那也是可执行的下一步。',
  '3. `reference` 是**库里同类反例的建议原文**，**只是参考**：',
  '   · 有值 ⇒ 照素材改写它（不要原样抄，它讲的可能是别的事）；',
  '   · 空的 ⇒ **不用管**，你自己按素材写。',
  '4. **不许**在改法里声称「库规要求」「条款规定」—— 你是给建议，不是引用规则。',
  '',
  '输出：**只输出一个 JSON 数组**，不要解释、不要 markdown 代码块。每项形如',
  '{"i":0,"advice":"具体怎么改"}',
  '`i` 是给你的条目的序号，必须原样回填。',
].join('\n');

/** 拼给模型的那一段（**纯函数** —— 喂样本就能断言，不必真调模型）。 */
export function buildAdvicePrompt(items = [], { readings = '', question = '' } = {}) {
  const rows = items.map((f, i) => {
    const ref = f.kbAdvice ?? f.kb?.suggestionLine ?? null;
    // 模型侧自己写过的初稿 —— 两轨都命中时，两条都给模型看（它比谁都清楚哪条更贴素材）
    const draft = f.suggestion ?? f.model?.suggestion ?? null;
    return [
      `i=${i}`,
      `位置：${f.location ?? '（未给）'}`,
      `类目：${f.category ?? '（未给）'}${f.sub ? '-' + f.sub : ''}`,
      `原因：${f.reason ?? f.kb?.reasonLine ?? '（未给）'}`,
      `reference：${ref ? String(ref).replace(/\n/g, ' ') : '（空 —— 库里这条没填建议）'}`,
      draft ? `模型侧初稿：${String(draft).replace(/\n/g, ' ')}` : '',
    ].join('\n');
  });
  return [
    '【本单素材（节选）】',
    String(readings || '').slice(0, 2000),
    question ? `【送审时的问题】${question}` : '',
    '',
    `【要你写建议的条目】共 ${items.length} 条`,
    ...rows,
  ].filter(Boolean).join('\n');
}

/**
 * 解析模型侧的建议输出（**纯函数**，宽容取第一个 JSON 数组）。
 * @returns {{ok:boolean, advice:Object<number,string>, error?:string}}
 */
export function parseAdvice(text) {
  const s = String(text ?? '');
  const a = s.indexOf('[');
  const b = s.lastIndexOf(']');
  // ★★ 2026-10-09 实测：**截断必须如实报成截断**，不许报成「没写数组」——
  //   与 `model_side.mjs` 同一条判据：报错指向错误的方向，查的人就永远查不到真因。
  if (a < 0) return { ok: false, advice: {}, error: '输出里没有 JSON 数组' };
  if (b <= a) {
    return { ok: false, advice: {},
             error: `输出**被截断**（有数组开头、没有结尾）—— 多半是额度用尽被腰斩｜raw=${s.length} 字` };
  }

  let arr;
  try { arr = JSON.parse(s.slice(a, b + 1)); }
  catch (e) { return { ok: false, advice: {}, error: `JSON 解析失败：${e?.message ?? e}` }; }
  if (!Array.isArray(arr)) return { ok: false, advice: {}, error: '不是数组' };
  const advice = {};
  for (const raw of arr) {
    const i = Number(raw?.i);
    const t = String(raw?.advice ?? '').trim();
    if (!Number.isInteger(i) || i < 0 || !t) continue;
    advice[i] = t;
  }
  return { ok: true, advice };
}

/**
 * 跑这一次调用。**失败回空对象，由调用方回退** —— 这里绝不编一句。
 * @returns {Promise<{ok:boolean, advice:Object, error?:string, ms:number, raw?:string}>}
 */
// ★ 2026-10-09：与模型侧同理 —— 截断就腰斩，所以额度从 2000 提到 4000。
export async function generateAdvice({ items = [], readings = '', question = '', ask, maxTokens = 4000 } = {}) {
  const t0 = Date.now();
  if (!items.length) return { ok: true, advice: {}, ms: 0 };
  if (typeof ask !== 'function') return { ok: false, advice: {}, ms: 0, error: '没给 ask（LLM 入口）' };
  const prompt = buildAdvicePrompt(items, { readings, question });
  let r;
  // ★ `ask` 的真实签名是 `ask(用户提示词, { system, maxTokens })` 且**返回字符串**
  //   —— 与 `model_side.mjs:132` 一致。第一版我猜成了 `ask({system,user})` 收 `{text}`，那是错的。
  try { r = await ask(prompt, { system: SYSTEM, maxTokens, temperature: 0 }); }  // ★ 2026-10-16 同上：建议也进报告，须确定
  catch (e) { return { ok: false, advice: {}, ms: Date.now() - t0, error: `${e?.name ?? 'Error'}: ${e?.message ?? e}` }; }
  // ★★ 2026-10-09：**截断或 0 字就重试一次**（额度翻倍）—— 与 `model_side.mjs` 同一条兜底。
  //   实测那一单的建议生成是 `raw=0 字`（**额度被 reasoning 烧光**，不是解析问题）⇒
  //   一次空转就把「具体建议」整条丢掉，卡片回退成库侧原话照搬。
  //   只对「截断」与「0 字」重试：真写了散文（非空且无 `[`）重试没用，那是提示词问题。
  //   （原先这里只有一行**注释**写着「截断就重试」而代码里没有 —— 注释不是约束，已补成真的。）
  let txt = String(r ?? '');
  let p = parseAdvice(txt);
  if (!p.ok && (/被截断/.test(String(p.error ?? '')) || txt.length === 0)) {
    console.log(`[agent] ↻ 建议生成输出${txt.length === 0 ? '为 0 字（额度被 reasoning 烧光）' : '被截断'}，`
      + `重试一次（额度 ${maxTokens} → ${maxTokens * 2}）`);
    try {
      r = await ask(prompt, { system: SYSTEM, maxTokens: maxTokens * 2, temperature: 0 });
      txt = String(r ?? '');
      p = parseAdvice(txt);
    } catch (e) { /* 重试也失败 ⇒ 走下面的回退，不编 */ }
  }
  if (!p.ok) {
    return { ok: false, advice: {}, ms: Date.now() - t0, raw: txt.length,
             error: `${p.error}｜raw=${txt.length} 字${txt.length ? '' : '（0 字 = 额度被 reasoning 烧光，不是解析问题）'}` };
  }
  return { ok: true, advice: p.advice, ms: Date.now() - t0, raw: txt.length };
}
