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

// ★ 2026-10-09：帧文本走 `video.frameLine`（**唯一产者**）—— 原先这一处自己拼过一份，
//   且**丢掉了 `t_s`** ⇒ 模型出 findings 时看不到时间码，却被告知要「指得出第几帧」。
//   `video.mjs` 不引本模块，无循环依赖。
import * as video from './video.mjs';

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
  // ★ 2026-10-09（Owner：「守衡输出的没有视频的时间节点」）：原先只写「第几帧」，
  //   而输入里**根本没有帧号** ⇒ 模型只能编一个「帧 3」，或干脆写「（未给位置）」。
  //   措辞里有两条边界，都是**能力边界**，不许让模型以为它能给更多：
  //     · 视频**只能给到帧的时间码**（8 帧是**均匀抽样**，不是逐帧 ⇒ 时间码是「这附近」）；
  //     · **音轨转写没有词级时间戳**（`asr.mjs` 只回整段文本）⇒ 口播类问题**给不出秒数**，
  //       要它如实说「转写第 N 段 / 原句」，**不许编一个时间**。
  '4. 每条必须指得出**位置**与**理由**。位置按素材类型给：'
    // ★ 2026-10-09（Owner 第三次点：「还是没展示到几秒 **00:12 格式**没看到」）：
    //   这一句原先教的是「行首 `[12.34s]`，直接抄那个数」—— 而 `video.frameLine` 现在
    //   印的是 `[00:12]`（`MM:SS`，按整秒截断）。**两边必须同口径**：
    //   提示词里留着旧形状，模型就会照着旧形状"抄"一个 `[12.34s]` 回去。
    + '视频关键帧上的字 ⇒ **给该帧的时间码**（行首 `[00:12]` 那种 `分:秒`，直接抄那个数）；'
    + '音轨转写 ⇒ 给**转写里的第几段 / 原句**（转写**没有**时间戳，**不许编一个秒数**）；'
    + '图上的字 ⇒ 给图上位置（如「主标题」「右下角贴片」）；素材正文 ⇒ 给所在句子。',
  '4b. ★ **每条都要给 suggestion：具体怎么改** —— 改哪个词、换成什么、删哪一句、补什么。',
  '    不许写「转对应负责人复核」「请人工确认」「建议修改」这类**没有动作**的话：',
  '    收到它的人还是不知道改什么。写不出具体改法时，就写清**缺什么信息才能定**（例如',
  '    「需要知道投放的是哪个平台才能定这句话合不合规」）—— 那也是可执行的下一步。',
  '5. 你出的每一条都**没有库内依据** —— 所以它最高只能到 REVIEW，不要给 BLOCK。',
  '',
  '输出：**只输出一个 JSON 数组**，不要解释、不要 markdown 代码块。每项形如',
  '{"location":"帧 3","category":"消费者安全","severity":"REVIEW","reason":"一句话说清问题",',
  ' "excerpt":"逐字引用的原文","suggestion":"具体怎么改（改哪个词/换成什么/删哪句/补什么）"}',
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
  if (a < 0) return { ok: false, findings: [], dropped: [], error: '输出里没有 JSON 数组' };
  // ★★ 2026-10-09 实测（Owner 那张夜间图）：**输出被截断时报错了方向。**
  //   日志写 `raw=1545 字`、首 100 字是 `"[\n {\n \"location\": …` —— 它**有**数组开头，
  //   只是**没有结尾**（额度用尽被腰斩），而判据把它报成「**输出里没有 JSON 数组**」⇒
  //   查的人会往「模型没照格式写」那个方向查，永远查不到真因（额度）。
  //   与 `raw=0` 那个坑（额度被 reasoning 烧光）是**同一个形状**：报错指向错误的方向。
  //   所以先判「有没有结尾」，再判「有没有开头」。
  if (b <= a) {
    return { ok: false, findings: [], dropped: [],
             error: `输出**被截断**（有数组开头、没有结尾）—— 不是「没写数组」，`
               + `多半是额度用尽被腰斩｜raw=${s.length} 字` };
  }
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
      // ★ 2026-10-09：模型侧的**可执行改法**（Owner：「不要甩给人」）。
      //   缺了不丢整条（它是补充信息，不是判定依据）；但为空时置 null，
      //   由渲染层如实说「两侧都没给修改建议」，**不许**替它编一句。
      suggestion: String(raw?.suggestion ?? '').trim() || null,
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
// ★ 2026-10-09 实测：`maxTokens=4000` 时输出被**腰斩**（`raw=1545 字`、有 `[` 无 `]`）
//   ⇒ 从 4000 提到 8000，并在下面加了「截断就重试一次」。
export async function reviewModelSide({ readings, question = '', ask, maxTokens = 8000 } = {}) {
  const t0 = Date.now();
  const noRead = !String(readings ?? '').trim();
  // 「没读到任何文字」时**不调模型**：那是确定性的事实，问一次模型只会换来编造。
  if (noRead) return { ok: true, findings: [], ms: 0, skipped: '文字层是空的 —— 模型侧无需跑，也不会编' };
  if (typeof ask !== 'function') return { ok: false, findings: [], ms: 0, error: '没有可用的 llm.ask' };
  try {
    let raw = await ask(buildPrompt({ readings, question }), { system: SYSTEM, maxTokens });
    let p = parseFindings(raw);
    // ★★ 2026-10-09：**截断就重试一次**（额度翻倍）。不重试的话，一次腰斩就把模型侧整条丢掉，
    //   用户拿到的卡里只剩库侧条目 —— 实测那张夜间图就是这样（`raw=1545 字`、无结尾）。
    //   只对「截断」重试：真没写数组（散文）重试也没用，那是提示词问题，不该白烧一次。
    if (!p.ok && /被截断/.test(String(p.error ?? ''))) {
      console.log(`[agent] ↻ 模型侧输出被截断，重试一次（额度 ${maxTokens} → ${maxTokens * 2}）`);
      raw = await ask(buildPrompt({ readings, question }), { system: SYSTEM, maxTokens: maxTokens * 2 });
      p = parseFindings(raw);
    }
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
    // ★★ 2026-10-09 晚（Owner：「报告链接中有文字是删除的」那条的**第二重代价**）：
    //   这一格原先取 `i.text`，而 `i.text` 那时是 **OCR 原文、含水印**
    //   ⇒ 模型侧读数里带着「刘华丽 / 刘华問 / 5615 RO0」，于是它把水印写成了
    //   **素材里的内容问题**：实测那份报告的建议写着「图上反复出现『5615 RO0』…
    //   看起来是设计残留或误贴」「图上出现『刘华丽』『刘华問』三处中文人名，若是参与
    //   用户真名，换成昵称或整行删掉」—— **让被审方去改一个图上根本不存在的元素**。
    //   ⇒ 现在 `i.text` 本身就是**摘掉水印的那份**（唯一对外文本，见 `agent.mjs` 收口注释），
    //     这里不需要再挑字段：**同一件事不许再有第二个产者各挑各的**（今天已因它栽两次）。
    if (String(i?.text ?? '').trim()) parts.push('【图 ' + i.index + ' 上的字】\n' + String(i.text).trim());
  }
  for (const v of inbound.videos ?? []) {
    if (v?.failed) continue;
    // ★★ 2026-10-09（Owner：「目前守衡输出的没有视频的时间节点 00:12 这些」）──────
    //   这一行原先**只取 `f.text`、丢掉 `t_s`** ⇒ 模型出 findings 时**看不到时间码**，
    //   而提示词第 4 条却要求它「指得出**第几帧**」—— 要它指位置，却不给它位置，
    //   实测 outcome 就是 `location` 里出现「帧 3」「（未给位置）」这类**不可核**的值。
    //   现在改走 `video.frameLine`（唯一产者）⇒ 时间码随帧一起进输入，
    //   与卡片、库侧**同源同格式**。提示词里的要求也同步改成「时间码」。
    const fr = (v.frames ?? []).map((f) => video.frameLine(f)).filter(Boolean);
    if (fr.length) parts.push('【视频 ' + v.index + ' 关键帧上的字（每行开头是该帧的时间码）】\n' + fr.join('\n'));
    const t = v.transcript ?? {};
    if (t.ok && String(t.text ?? '').trim()) parts.push('【视频 ' + v.index + ' 音轨转写】\n' + String(t.text).trim());
  }
  return parts.join('\n\n');
}
