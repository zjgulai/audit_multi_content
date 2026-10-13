/**
 * envelope.mjs —— 把「模型写的一段话」变成「一张卡」
 *
 * ── 为什么要有这一层，而不是让模型直接吐卡片 JSON ────────────────────────
 * 两个理由，第二个更要紧：
 *
 * 1. 让模型写完整的 V2 卡片 JSON，等于把「schema 2.0」「header.template 白名单」
 *    「V2 移除了 note」这些知识塞进每一次推理。它会在这些细节上犯错，
 *    而犯错的代价不是样式难看 —— 是**整条消息被服务端拒掉，回复凭空消失**。
 *
 * 2. 模版的真正作用是**约束内容**，不是换皮。`verdict` 只有一个格、
 *    结论只有一个格（`verdict`）—— 这些是槽位，不是建议。
 *    （`boundary` 那一格 2026-10-13 已整格作废，见下。）
 *    所以这一层必须真的把上限**执行**掉，而不是在注释里写「≤60 字」。
 *
 * ── 实测：上限原来一处在读吗 ───────────────────────────────────────────
 * 没有。cards.mjs 里 `VERDICT_MAX = 60`、`MAX_SECTIONS = 3`（`BOUNDARY_MAX` 2026-10-13 随
 * `boundary` 那一格一起作废）
 * 三个常量定义完之后，**整个仓库没有任何代码引用它们**（grep 只有定义行）。
 * 也就是说「结论 ≤60 字」此前是一句注释，模型写 300 字也照发。
 * 这一层就是它们唯一的执行点。
 *
 * ── 超长怎么处理：搬，不是砍 ───────────────────────────────────────────
 * 结论超过 60 字时**不截断**。截断会丢内容，而丢内容比格式难看严重得多。
 * 做法是把超出部分的整句搬到折叠区 —— 内容一个字不少，只是从
 * 「结论」那一格挪到了「边界」那一格。真搬不动了才降级成纯文本，
 * 并且降级理由写进正文（对方要能看出格式为什么变了）。
 */
import {
  BUILDERS, VERDICT_MAX, MAX_SECTIONS, collapsible,
  build, validateCard, renderText, BY_KIND,
} from './registry.mjs';
import { lintCopy } from './registry.mjs';

/** 卡片块的开头标记。选这个形态是因为它在 markdown 里不构成任何语法，误触概率低。 */
export const CARD_MARK = '[[card:';

const s = (x) => (x === null || x === undefined ? '' : String(x));

/** 长度按**字符**算，不是字节。中文一个字就是一个字。 */
const len = (x) => [...s(x)].length;

/* ═══════════════ ① 找块 ═══════════════ */

/**
 * 从回复里切出卡片块。
 *
 * 容错三件事，都是实测会遇到的：
 *   - 模型可能把整块包进 ```json 围栏
 *   - 块前后可能有多余空行或一句「（已整理成卡片）」
 *   - **块后面还有正文** —— 这是最危险的一种：如果只把标记去掉、正文留着，
 *     群里的表现就是「一张卡 + 一段重复的话」。所以前后文一律不信，
 *     只在块**就在回复里**的前提下，把前后文当作要并进折叠区的补充内容。
 *
 * ★ 坏 JSON 也必须报 `found`。
 *   第一版这里直接 return null，于是 `[[card:receipt]]\n{"title":` 这种
 *   截断输出会**原样漏进群里** —— 标记和半截 JSON 一起显示出来。
 *   实测用例逮到过（envelope 自测「坏 JSON」那条）。所以：只要看见标记，
 *   就算解析失败，也要把标记到结尾这段的位置报出来，供调用方剥干净。
 *
 * @returns {{kind:string, data:object|null, before:string, after:string,
 *            blockStart:number, blockEnd:number, error:string|null}|null}
 *          data 为 null 表示找到了块但解析失败，error 说明原因。
 */
export function extractCardBlock(text) {
  const src = s(text);
  const at = src.indexOf(CARD_MARK);
  if (at < 0) return null;

  const afterMark = src.slice(at + CARD_MARK.length);
  const close = afterMark.indexOf(']]');
  if (close < 0) return null;                     // 连 `]]` 都没有 → 不是块，是普通文字
  const kind = afterMark.slice(0, close).trim();

  let rest = afterMark.slice(close + 2);
  rest = rest.replace(/^\s*```[a-zA-Z]*\s*/, '');        // 容忍 ```json 围栏
  const b0 = rest.indexOf('{');
  if (b0 < 0) {
    return { kind, data: null, before: src.slice(0, at).trim(), after: '',
             blockStart: at, blockEnd: src.length, error: '标记后没有对象' };
  }

  // 从 `{` 起做括号配对扫描。不能直接 indexOf('}')：
  // 卡片数据里几乎一定有 `{...}`（option、item、表头对象），会切在半路。
  let depth = 0, inStr = false, esc = false, end = -1;
  for (let i = b0; i < rest.length; i++) {
    const ch = rest[i];
    if (inStr) {
      if (esc) esc = false;
      else if (ch === '\\') esc = true;
      else if (ch === '"') inStr = false;
      continue;
    }
    if (ch === '"') { inStr = true; continue; }
    if (ch === '{') depth++;
    else if (ch === '}') { depth--; if (depth === 0) { end = i; break; } }
  }

  // 括号没配上（截断输出）→ 块一直延伸到文本结尾
  if (end < 0) {
    return { kind, data: null, before: src.slice(0, at).trim(), after: '',
             blockStart: at, blockEnd: src.length, error: '对象括号没配平（多半是输出被截断）' };
  }

  let data;
  try { data = JSON.parse(rest.slice(b0, end + 1)); }
  catch (e) { data = null; if (!e) throw e; }

  // ★★ 2026-10-09：**闭合标记必须在这里剥干净**（实测缺陷，线上发过 6 张）──────────
  //   病灶：`[[card:receipt]]\n{…}\n[[/card]]` 解析出来的 `after` 是 **`[[/card]]`** ——
  //   它会被当成「**块外正文**」交给 `enforceLimits` 的 `extra`，而那个循环会把它
  //   **折进卡片的折叠组**（`foldIn`）⇒ 群里就出现一个内容写着 `[[/card]]` 的组。
  //   最小复现（9 行）：`extractCardBlock(RAW).after === '[[/card]]'`，而按 `blockEnd` 切
  //   只剩 `"\n[[/card]]"` —— 两个都说明**闭合标记没被计入块的结束位置**。
  //   线上证据：`ws_outbound.jsonl` 里 6 张卡（最近一张 2026-10-07 08:21）。
  //   修法两层（都要）：① `tail` 里显式剥掉闭合标记（容忍前后空白与 ``` 围栏）；
  //   ② 用**正确的 `blockEnd`** 复核 —— `blockEnd` 此前少了闭合标记的长度
  //      （`close + 2` 只到 kind 的 `]]`，没算 `[[/`）。它没有外部消费者，改它安全。
  // ⚠️ 两个基准别写错：`closeAt` / `end` / `b0` 都是**相对 `rest`**（`rest` 从 kind 的 `]]` 之后开始），
  //   而 `blockEnd` 是**相对 `src`** ⇒ 前缀 = `at + CARD_MARK.length + close + 2`。
  // ⚠️ 闭合标记是**恒定的 `[[/card]]`**，**不是** `[[/${kind}]]`（第一版就写错成后者：
  //   对 `[[card:receipt]]` 会去找 `[[/receipt]]` ⇒ 永远找不到 ⇒ `closeAt=-1` ⇒ 修了等于没修）。
  const srcPrefix = at + CARD_MARK.length + close + 2;
  const closeMark = '[[/card]]';
  const closeAt = rest.indexOf(closeMark, end + 1);
  const tail = (closeAt >= 0 ? rest.slice(end + 1, closeAt) : rest.slice(end + 1))
    .replace(/\s*```\s*$/, '')
    .replace(/^\s*```[a-zA-Z]*\s*/, '')
    .trim();
  const blockEnd = closeAt >= 0 ? srcPrefix + closeAt + closeMark.length : src.length;
  if (data === null || typeof data !== 'object' || Array.isArray(data)) {
    return { kind, data: null, before: src.slice(0, at).trim(), after: tail,
             blockStart: at, blockEnd, error: '对象不是合法 JSON 或不是对象' };
  }
  return { kind, data, before: src.slice(0, at).trim(), after: tail,
           blockStart: at, blockEnd, error: null };
}

/* ═══════════════ ①b PRD §5.3 结论行的执行点 ═══════════════ */

/**
 * 这张卡的「结论格」是哪个字段 —— `title` 优先，退到 `verdict`，都没有就 `null`。
 *
 * ★ 判据按**各类型真实的字段表**（`registry.BY_KIND`）来，不是想当然一律填 `verdict`：
 *   `correction` / `capability-boundary` / `find-nothing` / `alert` / `decision`
 *   这五个类型**两个字段都没有**，硬塞进去的内容会静默消失 ——
 *   同 `FOLD_FIELD` 那条教训（「写了但没人读的字段 = 假槽位」）。
 *
 * 为什么 `title` 优先：PRD §5.3 的结论行是**一条结论**，而 `title` 是对方一眼先看到的
 * 那个格子（`contract.md`：「写结论本身，不写『关于 X 的答复』」）。
 * `evidence` 这类没有 `title` 的类型，结论格就是 `verdict`。
 */
/**
 * 卡面上**确实有 title 格、但注册表不该在 `fields` 里申报**的那几种。
 *
 * ★ 2026-10-06 加：这五种（`correction` / `capability-boundary` / `find-nothing` /
 *   `alert` / `decision`）的构造器**一直在写 title**（`s(d.title ?? '默认')`），
 *   而注册表的 `fields` 只列**模型可以填**的格 —— 它们的 title 是**代码写的**，
 *   所以没申报。后果：`verdictSlotOf()` 找不到结论格 ⇒
 *   **PRD §5.3 结论行无处安放**（实测：模型挑 `find-nothing` 时日志里就是 `落点=no-slot`）。
 *
 *   第一版我把 `title` 加进了 `fields` —— 那是错的：`fields` 会进模型可见的提示词，
 *   一加就有两处变红（`K5 提示词长度`超预算、`I 段`文档项数对不上），
 *   而且等于告诉模型「你给 `find-nothing` 卡写个标题吧」，与「模型不写结论行」相反。
 *   所以这里单独一张表：**进的是落点判据，不进提示词**。
 */
const CODE_WRITTEN_TITLE = new Set([
  'correction', 'capability-boundary', 'find-nothing', 'alert', 'decision',
  // ★ 2026-10-06 第二批（Owner：「title 格补给所有卡片类型」）：
  //   这四种的 `fields` 里有 `verdict`（模型写结论的那一格），于是 `verdictSlotOf`
  //   先命中了 `verdict` ⇒ **PRD §5.3 结论行落到正文第一行、抬头仍是模型自拟的**。
  //   实测就是这两天的真单：模型挑了 `evidence`，抬头没换。
  //   而它们的构造器**同样一直在写 title**（`s(d.title ?? '证据')`）——
  //   抬头存在、只是没申报。补的是**漏报**，不是新造格子。
  'cannot-read', 'receipt', 'turn-diff', 'evidence',
]);

export function verdictSlotOf(kind) {
  const fields = BY_KIND.get(kind)?.fields;
  if (!fields) return null;
  // ★ 顺序即语义：**抬头优先**。
  //   卡面只要有抬头就用抬头 —— 它是这张卡上唯一的「最前面」，
  //   而 PRD §5.3 要的正是「结论行排在最前面」（§5.3 的示例全是抬头那一行）。
  //   旧顺序（先判 `fields` 里的 title、再判 verdict）会让「有 verdict 没申报 title」
  //   的四种卡片把结论行放到正文去 —— 那不是格式问题，是**位置**问题：
  //   业务同事扫一眼看到的是抬头，抬头不对，等于没看到结论。
  if ('title' in fields || CODE_WRITTEN_TITLE.has(kind)) return 'title';
  if ('verdict' in fields) return 'verdict';
  return null;
}

/**
 * **PRD §5.3 结论行的执行点**：把权威结论行搬进这张卡的结论格。
 *
 * ── 为什么要有这一步（2026-10-06）
 *
 * 上游 2026-09-22 给 §5.3 加了 `【审查结论：…】` 标记，当天那份改动登记就把
 * 「要不要落进回复卡片模版？」挂在第 317 行、**没有改任何代码**。半个月后 Owner 在群里
 * 看到的就是它的后果：链路侧按 5.3 产出了结论行、注入语也写了「逐字转述不许改写」，
 * **而回卡片那一跳把表头改写掉了** —— 于是「逐字转述」这四个字在盘上**没有任何执行点**。
 *
 * 现在它有了：结论行的唯一出处是链（或 P0 快路的派生），模型的措辞不再参与这一格。
 * 同 `AGENTS.md` §2.5 的既有分工 —— **模型不写卡片 JSON，也不写结论行**。
 *
 * ── 三个不变量
 *
 *   ① **不许编**：没有权威结论行就**一个字符都不动**（`null` 输入 → `action:'none'`）。
 *      给闲聊硬加一句「【审查结论：PASS】」比格式难看严重得多。
 *   ② **搬不是砍**：模型原来写在结论格里的那句话**进折叠区**，不丢。
 *      （实测那三条里，① 的「但『未命中 ≠ 合规』」正是写在 title 里的边界话，
 *        直接覆盖就把它删了。）
 *   ③ **格子合不上就出声**：类型没有结论格（`slot === null`）或结论行超过该格上限时，
 *      返回 `action:'no-slot'` / `'too-long'` —— 由调用方记读数，**不许静默放过**。
 *
 * @param {string} kind
 * @param {object} data 已经过 `enforceLimits` 的卡片数据（本函数会返回新对象，不改原对象）
 * @param {{state:string,line:string,from:string}|null} verdict
 * @returns {{data:object, action:'none'|'already'|'forced'|'no-slot'|'too-long',
 *            slot:string|null, moved:object|null, why:string}}
 */
export function applyVerdictLine(kind, data, verdict) {
  const none = (why) => ({ data, action: 'none', slot: null, moved: null, why, block: null });
  if (!verdict || !verdict.line) return none('这一轮没有权威结论行（不是送审，或链没给三态）');

  // ── 逐条块：**与结论行同一条分工** —— 模型不写，代码搬（2026-10-06 加）。
  //    Owner 拿 PRD §5.3.3 模板对照实发的 BLOCK 卡片：抬头对、**逐条四要素整块没有**。
  //    根因是正文由模型转述，而它会把一整块逐条压成一句「命中两条 P0，不能发」。
  //    ⚠️ 这一步必须在**结论格那几条提前 return 之前**就算出来 ——
  //    否则「标题恰好已经对了」（action=already）那条路会把块整个漏掉。
  const withBlock = (r) => {
    if (!verdict.block) return { ...r, block: null };
    const bs = blockSlotOf(kind);
    if (!bs) return { ...r, block: { action: 'no-slot', why: `「${kind}」没有能放逐条块的格` } };
    const out = { ...r.data };
    if (bs === 'reasoning') {
      const cur = s(out.reasoning);
      if (cur.includes(verdict.block)) return { ...r, block: { action: 'already', slot: bs } };
      out.reasoning = cur ? `${verdict.block}\n\n${cur}` : verdict.block;
      return { ...r, data: out, block: { action: 'forced', slot: bs } };
    }
    // `groups` 型（如 evidence 卡）：块作为**第一组**，默认展开 —— 它是这条结论的正文，不是附录。
    const groups = Array.isArray(out.groups) ? out.groups : [];
    if (JSON.stringify(groups).includes(verdict.block)) return { ...r, block: { action: 'already', slot: bs } };
    // ★ 2026-10-08 两处改动（Owner：「PRD §5.3 结论块 · 0 是什么意思？**为什么要带 prd**？」）：
    //   ① **不再给 `count: 0`** —— 那是漏填的占位，印出来是「· 0」，而同一块正文写着
    //      「共发现 3 处必须修改」⇒ 标题说 0、正文说 3（10/07–10/08 连发多张卡）。
    //      `cards.mjs` 已改成"有才拼"。条数**只在有结构化真值时才给**
    //      （P0 快路那条在 `prd53.deriveVerdictLine` 里是 `matched_patterns`）；
    //      这里拿不到结构化条数 ⇒ **不给** —— 绝不回头去正则抠那段中文
    //      （库规：库侧的结论与条数一律读结构化字段，不许从中文答案里抠）。
    //   ② 标题去掉内部章节号 —— 这张卡是给业务同事看的，**「PRD §5.3」对他们是零信息量**。
    //      格式仍由 PRD §5.3 规定；要追溯出处看日志里的 `block.action`，不必印在卡面上。
    out.groups = [{ title: '审查结论', content: verdict.block, expanded: true }, ...groups];
    return { ...r, data: out, block: { action: 'forced', slot: bs } };
  };

  const slot = verdictSlotOf(kind);
  if (!slot) {
    return withBlock({ data, action: 'no-slot', slot: null, moved: null,
                       why: `「${kind}」没有结论格（既无 title 也无 verdict）—— 结论行无处安放` });
  }

  const cur = s(data[slot]).trim();
  if (cur === verdict.line) {
    return withBlock({ data, action: 'already', slot, moved: null, why: '结论格已经是这一行' });
  }

  // 结论行超过该格的硬上限 ⇒ 不硬塞（塞进去会被 enforceLimits 搬走，反而更乱）。
  const cap = slot === 'verdict' ? VERDICT_MAX : Infinity;
  if (len(verdict.line) > cap) {
    return withBlock({ data, action: 'too-long', slot, moved: null,
                       why: `结论行 ${len(verdict.line)} 字 > ${slot} 的上限 ${cap} 字` });
  }

  // ① 先把模型原来那句搬进折叠区（**搬不是砍**），② 再落权威结论行。
  //
  // ★★ 2026-10-09（Owner：「prd 没说要『原始回答（原「data-table」卡，逐字搬）』，
  //    现在输出的有，可考虑去掉」）——
  //    这三处折叠组的标题原先写的是**本仓的内部动作**（换了哪张卡、哪一行被替换），
  //    对群里的人是**零信息量**，而且「data-table / receipt」是**内部类型名**。
  //    口径：**内容一个字不丢，标题只说"这是什么"**。
  //    —— 保留「原文照留」这四个字，是因为它承担一个真实语义：
  //       读者得知道**下面这段不是权威结论、是模型原话**（否则两段话看起来像两个结论）。
  let out = { ...data };
  let moved = null;
  if (cur) {
    const [folded, to] = foldIn(kind, { ...out, [slot]: '' },
      `（原文照留：这一段是模型原话，**不是**下方权威结论）\n${data[slot]}`);
    if (to) {
      out = folded;
      moved = { field: slot, to, chars: len(data[slot]), why: `原结论搬进 ${to}` };
    } else {
      // 这个类型没有折叠区、也没有兜底正文格 —— **宁可不换**，也不丢掉模型那句话。
      return withBlock({ data, action: 'no-slot', slot, moved: null,
                         why: `「${kind}」无折叠区可安置原结论，换掉就会丢内容 ⇒ 不换` });
    }
  }
  out[slot] = verdict.line;
  return withBlock({ data: out, action: 'forced', slot, moved, why: `结论行来自 ${verdict.from}` });
}

/**
 * 字段名 → 中文标签（**换卡**时把内容逐字搬过去用）。认不出的字段就用**原名**——
 * 不猜含义、不改写内容：这一步是搬迁，不是改写。
 */
const FIELD_ZH = {
  title: '标题', subtitle: '副标题', verdict: '结论', reasoning: '正文', groups: '分组',
  before: '上一次', after: '这一次', cause: '为什么变', wrong: '错在哪', right: '正确说法',
  can: '能做到', limited: '受限', cannot: '做不到', item: '对象', why: '原因',
  alternative: '替代方案', note: '备注', paths: '可查路径', tried: '试过哪些',
  nextStep: '下一步', what: '发生了什么', impact: '影响', internal: '内部详情', retry: '重试方式',
  ask: '在问什么', options: '选项', recommend: '推荐', evidence: '证据',
  columns: '列', rows: '行', fields: '补充',
};

/**
 * 把一张卡的数据**逐字摊成文字** —— 换卡片类型时用（内容一个字不丢，换的只是外壳）。
 * 与 `foldIn` 的分工：那个是把溢出折进折叠区；这个是**跨类型搬迁**。
 */
export function carryCardText(data) {
  if (!data || typeof data !== 'object') return '';
  const out = [];
  for (const [k, v] of Object.entries(data)) {
    if (v == null || s(v).trim() === '') continue;
    const label = FIELD_ZH[k] ?? k;
    if (Array.isArray(v)) {
      const lines = v.map((x) => {
        if (x && typeof x === 'object') {
          if ('label' in x) return `${x.label}：${x.value}`;
          if ('title' in x && 'content' in x) return `【${x.title}】${x.content}`;
          return Object.entries(x).map(([kk, vv]) => `${kk}：${vv}`).join('；');
        }
        return String(x);
      }).filter((t) => t && s(t).trim());
      if (lines.length) out.push(`${label}：\n${lines.join('\n')}`);
      continue;
    }
    out.push(`${label}：${s(v).trim()}`);
  }
  return out.join('\n');
}

/**
 * 逐条块放哪个格 —— `reasoning` 优先，退到 `groups`，都没有就 `null`（要出声）。
 * 同 `verdictSlotOf` 的纪律：按**各类型真实的字段表**判，不硬塞一个不存在的字段。
 */
export function blockSlotOf(kind) {
  const fields = BY_KIND.get(kind)?.fields;
  if (!fields) return null;
  if ('reasoning' in fields) return 'reasoning';
  if ('groups' in fields) return 'groups';
  return null;
}

/* ═══════════════ ② 执行上限 ═══════════════ */

/**
 * 每个类型的折叠区在哪个字段。
 *
 * 这个表必须按**构造器实际读的字段**来定，不能想当然填 `evidence` ——
 * 第一版就是一律填 `evidence`，结果 `cannot-read`/`decision`/`data-table`
 * 根本没有这个字段，塞进去的内容**静默消失**（J4 用例逮到）。
 * 「写了但没人读的字段 = 假槽位」，这条规矩对信封层同样成立。
 *
 * `null` 表示这个类型没有折叠区，只能落回正文格（见 foldIn）。
 */
const FOLD_FIELD = {
  'query-answer': 'evidence',
  // ★ 2026-10-06 修：这里原来写的是 `'evidence': 'evidence'` —— **该卡没有 `evidence` 这个字段**
  //   （它的字段是 `verdict` / `groups` / `fields`）。于是 `foldIn` 把内容写进
  //   一个**没人渲染的字段**里 ⇒ **静默丢内容**，而它还返回了一个「落到了 evidence」的读数。
  //   这条陈旧条目一直没被发现，因为此前没有任何路径让 `evidence` 卡走到 `foldIn`
  //   —— 直到 2026-10-06 把结论行的落点改成「抬头优先」，它必然要折一次原抬头。
  //   逮到它的是 `W5c`（行为级：不只看判据，看**建出来的那张卡**）。
  'evidence': 'groups',                // groups 是主体，额外内容作为**一组**追加（见 FOLD_GROUPS）
  'capability-boundary': 'evidence',
  'find-nothing': 'tried',
  'alert': 'internal',
  'data-table': 'note',
  'receipt': 'note',
  'turn-diff': null,                   // 没有折叠区
  'correction': null,
  'cannot-read': null,
  'decision': null,
};

/** 没有折叠区时，退回哪个正文格。都是「本来就在说补充信息」的格子。 */
const FALLBACK_SLOT = {
  'turn-diff': 'cause',
  'correction': 'cause',
  'cannot-read': 'why',
  'decision': 'ask',
  'receipt': 'note',
  'data-table': 'note',
};

/**
 * 折叠字段里哪几个是**数组**。
 *
 * ★ 2026-10-06：这张表是被一次真崩溃逼出来的，不是设计出来的。
 *   `foldIn` 原来的判据是 `Array.isArray(d[field])` —— 也就是说**字段类型由「模型有没有给」决定**：
 *   模型给了数组就按数组追加，没给就写成字符串。而 `query-answer` 的构造器是
 *   `d.evidence.join('\n')`（`cards.mjs:193`）⇒ **模型没给 `evidence` 时，一次折叠就把卡片建崩**：
 *   `d.evidence.join is not a function`。后果不是格式难看，是**整张卡降级成纯文本**
 *   （`toCardOrText` 的 `reason` 里写着原因）。
 *
 *   逮到它的是 `tools/test_agent.mjs` 第 20 组 W3 —— 加 PRD §5.3 结论行时第一次真的走到那一步
 *   （结论行要先把原来的 title 折进折叠区，于是必然触发一次 `foldIn`）。
 *   **这条路径一直都在，只是此前没有任何用例把「模型不给 evidence」和「块外有正文」凑到一起。**
 */
const FOLD_IS_ARRAY = new Set(['query-answer']);

/**
 * 折叠目标是**对象数组**（形如 `[{title, content, count, expanded}]`）的类型。
 *
 * ★ 不能并进 `FOLD_IS_ARRAY`：那个分支写的是 `[...cur, text]`，往对象数组里塞一个**字符串**
 *   会让 `capSections` / 构造器读到裸串 —— 那是另一种崩法。形状不同就分开两张表。
 */
const FOLD_GROUPS = new Set(['evidence']);

/**
 * 把一段没有专属格子的内容塞进这张卡。
 * 返回 [新 data, 实际落到的字段名 | null]。落到 null 表示确实没地方放。
 */
function foldIn(kind, d, text) {
  const field = FOLD_FIELD[kind];
  if (field) {
    if (FOLD_GROUPS.has(kind)) {
      const cur = Array.isArray(d[field]) ? d[field] : [];
      return [{ ...d, [field]: [...cur, { title: '（原文照留：模型原话，非权威结论）',
                                         content: text, expanded: false }] }, field];
    }
    if (FOLD_IS_ARRAY.has(kind)) {
      // 类型由**表**决定，不由模型给没给决定 —— 见上面那段。
      const cur = Array.isArray(d[field]) ? d[field] : (d[field] ? [d[field]] : []);
      return [{ ...d, [field]: [...cur, text] }, field];
    }
    return [{ ...d, [field]: d[field] ? `${d[field]}\n${text}` : text }, field];
  }
  const slot = FALLBACK_SLOT[kind];
  if (!slot) return [d, null];
  const cur = s(d[slot]);
  return [{ ...d, [slot]: cur ? `${cur}\n\n（补充）${text}` : `（补充）${text}` }, slot];
}

/**
 * 正文格里的内部记录：搬到折叠区。
 *
 * 为什么必须做这一步，而不是只靠 lint 报警：
 * `alert` 的 `what` / `impact` 是**公开展示**的格子，而默认的 what 文案
 * 是「刚才那条回复是故障输出」—— 模型把工具名写进 `what` 是很自然的事。
 * 2026-09-17 那条连列 27 次工具名的回复就是这么出来的。
 * 报警只能让维护者看见，搬走才能让对方看不见。
 *
 * 优先级：有折叠区就搬进去；没有折叠区（alert 一定有 internal）就交给调用方降级。
 */
const PUBLIC_FIELDS = [
  'title', 'verdict', 'reasoning', 'wrong', 'right', 'cause', 'what', 'impact',
  'ask', 'recommend', 'note', 'nextStep', 'why', 'alternative', 'before', 'after',
];

function scrubInternal(kind, d) {
  const moved = [];
  let out = { ...d };
  for (const f of PUBLIC_FIELDS) {
    if (!out[f]) continue;
    // ★ 判据只有一处：`lintCopy` 的 `internalLeak`（registry.mjs）。
    //   这里原先自带一条**更窄**的正则（少了栈帧与「连续同名工具 ≥3 次」），
    //   于是「检测器报了的，动作未必搬」—— 同一个概念两份判据，
    //   正是 §2.5「形态/判据只能有一处」要防的形状。现在只有一份。
    const hitLeak = lintCopy(s(out[f])).find((h) => h.id === 'internalLeak');
    if (!hitLeak) continue;
    const folded = out[f];
    const hit = foldIn(kind, { ...out, [f]: '' }, `（内部详情，排查用）\n${folded}`);
    if (hit[1] === null) continue;                       // 没地方放 → 留给降级处理
    out = hit[0];
    moved.push({ field: f, to: hit[1], chars: len(folded), why: `正文格 ${f} 里出现了内部标识，已搬进折叠区` });
  }
  return { data: out, moved };
}

/**
 * 把字段搬到它该在的格子里。返回改过的 data 和一份搬迁记录。
 *
 * 只处理「搬得动」的情况。搬不动的（比如 correction 的 wrong 太长）
 * 就原样留着 —— 那是模型说错了话，不是格式问题，硬掰只会掩盖。
 *
 * @param {string} kind
 * @param {object} data
 * @param {string[]} extra 卡片块之外的正文。不会丢，也不会重复出现在群里：
 *                         有折叠区就进折叠区，没有就进本类型的「补充」格。
 */
export function enforceLimits(kind, data, extra = []) {
  let d = { ...data };
  const moved = [];

  // 结论超长：按句切，前 VERDICT_MAX 字留结论，其余**搬进折叠区**。
  // ★ 2026-10-13：原先搬进 `boundary`，而 `boundary` 那一格已整格作废（不上卡）
  //   ⇒ 再往那儿搬就是**静默丢字**。改走 `foldIn`（与「边界超长」「字段超限」同一条路）。
  if (d.verdict && len(d.verdict) > VERDICT_MAX) {
    const chars = [...s(d.verdict)];
    // 优先在句号处断开，退而在上限处断 —— 但都要保证不丢字
    let cut = -1;
    for (let i = Math.min(VERDICT_MAX, chars.length - 1); i > VERDICT_MAX * 0.5; i--) {
      if ('。；！？\n'.includes(chars[i])) { cut = i + 1; break; }
    }
    if (cut < 0) cut = VERDICT_MAX;
    const head = chars.slice(0, cut).join('').trim();
    const spill = chars.slice(cut).join('').trim();
    if (spill) {
      d.verdict = head;
      const [nv, nto] = foldIn(kind, d, spill);
      d = nv;
      moved.push({ field: 'verdict', to: nto ?? '(无格可放)', chars: len(spill),
                   why: `结论超过 ${VERDICT_MAX} 字` });
    }
  }

  // 字段数超限：多出来的字段进折叠区，不丢
  const cap = { 'query-answer': 4, 'receipt': 3, 'data-table': 6 }[kind] ?? 6;
  if (Array.isArray(d.fields) && d.fields.length > cap) {
    const extraFields = d.fields.slice(cap);
    d.fields = d.fields.slice(0, cap);
    const [next, to] = foldIn(kind, d, extraFields.map((f) => `${f.label}：${f.value}`).join('\n'));
    d = next;
    moved.push({ field: 'fields', to: to ?? '(无格可放)', chars: extraFields.length, why: `字段超过 ${cap} 个` });
  }

  // 卡片块之外的正文：一条都不丢。
  for (const text of extra.filter(Boolean)) {
    const [next, to] = foldIn(kind, d, text);
    d = next;
    moved.push({
      field: '块外正文', to: to ?? '(无格可放)', chars: len(text),
      why: to ? `卡片块之外的正文已并入 ${to}` : '卡片块之外有正文，但这个类型没有能承载它的格子（已在日志记录，未发进群）',
    });
  }

  // 正文格里的内部记录 → 折叠区。放在最后，保证前面几轮搬进来的内容也被查一遍。
  const scrubbed = scrubInternal(kind, d);
  d = scrubbed.data;
  moved.push(...scrubbed.moved);

  return { data: d, moved };
}

/* ═══════════════ ②b 段落数上限 —— MAX_SECTIONS 的执行点 ═══════════════ */

/**
 * 卡片**顶层 markdown 块**超过 `MAX_SECTIONS` 时，把多出来的段落搬进折叠区。
 *
 * ★ 为什么在这里、而不在 `enforceLimits` 里：
 *   `enforceLimits` 作用在**数据**上（verdict / boundary 这些格子），
 *   而「顶层 markdown 块有几个」是**建出来的卡**才有的性质 ——
 *   同一个字段在不同卡片类型里可能进正文、也可能进字段表或折叠区。
 *   所以只能在 `build()` 之后数。
 *
 * ★ 口径（与 `cards.mjs` 里 `MAX_SECTIONS` 的注释同源 —— 改一处必须改两处）：
 *   只数 `body.elements` **顶层**的 `markdown`。
 *   `hr` 是分隔线、`collapsible_panel` 是收起区、`column_set` / 字段排是字段表，都不算段落。
 *
 * ★ 搬是搬，砍是砍：搬走的段落**一个字都不改**，整段进折叠区（§2.4）。
 *   丢内容比格式难看严重得多。
 *
 * @param {object} card 已建好的卡
 * @param {number} [max] 上限，默认取 MAX_SECTIONS
 * @returns {{card: object, moved: Array}} 未被改动时 `moved` 为空数组
 */
export function capSections(card, max = MAX_SECTIONS) {
  const els = card && card.body && card.body.elements;
  if (!Array.isArray(els)) return { card, moved: [] };

  const mdIdx = els
    .map((e, i) => (e && e.tag === 'markdown' ? i : -1))
    .filter((i) => i >= 0);
  if (mdIdx.length <= max) return { card, moved: [] };

  const overflowIdx = new Set(mdIdx.slice(max));
  const overflow = els.filter((_, i) => overflowIdx.has(i));
  const kept = els.filter((_, i) => !overflowIdx.has(i));
  kept.push(collapsible(`其余 ${overflow.length} 段（已折叠 · 防复读）`, overflow));

  return {
    card: { ...card, body: { ...card.body, elements: kept } },
    moved: overflow.map((e) => ({
      field: 'sections',
      to: 'collapsible',
      chars: len(e.content || ''),
      why: `顶层段落超过 ${max} 段，第 ${max + 1} 段起搬进折叠区`,
    })),
  };
}

/**
 * 纯文本路径的结论行：PRD §5.3 的结论必须**排在最前面**（PRD 原话「先把结论放在最前面」）。
 *
 * 幂等：文本里已经有这一行就一个字符都不动 —— 否则会变成「结论行 + 又一遍结论行」。
 * 没有结论行（不是送审）时 `verdict` 是 `null`，这里**加不了任何东西**（不许编）。
 */
function leadWithVerdict(text, verdict) {
  const body = s(text);
  if (!verdict || !verdict.line) return body;
  if (body.includes(verdict.line)) return body;
  return body ? `${verdict.line}\n\n${body}` : verdict.line;
}

/* ═══════════════ ③ 建卡 ═══════════════ */

/**
 * 回复文本 → 该发什么。
 *
 * 返回的 `mode` 只有两种，语义是**确定**的：
 *   'card' —— 有一张通过校验的卡，去发卡
 *   'text' —— 没有块（正常纯文本回复）、或块不可用。`reason` 说明是哪种。
 *
 * ★ 无论走哪条路，**mark 之后的内容永远不进正文**。
 *   泄漏一条 `[[card:...]]` 到群里，和泄漏一条 tool_calls 是同一类故障。
 *
 * @param {string} reply 模型给的回复原文
 * @returns {{mode:'card'|'text', card?:object, data?:object, kind?:string,
 *            text:string, reason:string|null, moved:Array, lint:Array, dropped:boolean}}
 */
/**
 * 「我读到了什么」搬进卡片正文**最前面**（2026-10-06 加）。
 *
 * ★ 为什么（Owner 原话：「视频还是无法读取」）：那次他发的 15 秒视频，内核**读成功了** ——
 *   8 帧全抽出来、OCR 成功、音轨确认没人说话 —— 而那三个读数**只进了日志**。
 *   卡片正文通篇在讲知识库自己的事（「覆盖判据不成立」「缺的是库覆盖，补素材无用」），
 *   **一句没讲他视频里有什么**。于是结论读起来就是「它没看我的视频」。
 *
 * 分工与结论行、逐条块**完全一样**：**模型不写，代码搬**。
 * 它排在正文最前面、结论行仍在**标题**里 —— 两样各占一格，谁也不挤谁。
 *
 * @returns {{data:object, action:'none'|'no-slot'|'already'|'forced', slot:string|null, why?:string}}
 */
export function applyMediaRead(kind, data, mediaRead) {
  // ══════════════════════════════════════════════════════════════════════════
  // ⚠️ **本函数当前不生效**（2026-10-13）—— 与 `dual_track.p0ShortReplyBlock` 同一个先例：
  //    **纯函数保留，接线撤了**。撤的理由是 Owner 当场给的原文：
  //    「（视频那一段）我读到了／视频 1 段｜读成功 1 · 失败 0／…／帧上文字：[00:04] …
  //      （共 8 帧有字，全文见报告附录「机读素材读数」）—— **这里多余的回复也去掉**」。
  //
  //    他自己引的就是这个函数的产物（`**我读到了**` ＋ 读数 ＋ 帧上文字预览）。
  //    ⇒ 媒材读数**不再上卡**。它一条都没丢，仍在三处：
  //      · `ws_daemon` 的日志（`📥 读到｜视频 1 段｜读成功 1 · 失败 0` —— 「我真读了」的凭证在那）；
  //      · 会话记忆（`chainBlock` 里的媒材块）；
  //      · **报告附录**「机读素材读数（全文，供回源核对）」（`agent.mediaReadAppendix`）。
  //
  //   ⚠️ 这条改的是 Owner 2026-10-06 的一条要求（「视频还是无法读取」→ 那时把读数搬上卡，
  //      因为卡上通篇在讲库自己的事、一句没讲他视频里有什么）。**两条要求指向相反**，
  //      以**最新这一条**为准；要恢复，把 `toCardOrText` 里那一行接线加回来即可。
  //   ⚠️ 恢复时请一并读 §J14 那组判据（卡面结构不许再被撑开）。
  // ══════════════════════════════════════════════════════════════════════════
  if (!mediaRead) return { data, action: 'none', slot: null, why: '这一轮没有媒材读数' };
  const block = `**我读到了**\n${String(mediaRead).trim()}`;
  const out = { ...data };
  const slot = ['verdict', 'reasoning', 'wrong', 'verdict_text']
    .find((k) => typeof out[k] === 'string');
  if (!slot) return { data, action: 'no-slot', slot: null, why: `「${kind}」没有能放读数的格` };
  if (String(out[slot]).includes('**我读到了**')) return { data, action: 'already', slot };
  out[slot] = out[slot] ? `${block}\n\n${out[slot]}` : block;
  return { data: out, action: 'forced', slot };
}

/**
 * 把**报告链接**放进卡片**可见格**（2026-10-09，Owner 第三次同一个反馈）。
 *
 * ── 为什么不能只放在结论块里
 *
 *   报告链接此前拼在 §5.3 结论块内部（先是在 8 条逐条之后，后挪到块的第 2 行），
 *   而**整块在卡片里是可收起的** —— 实测那张 8 处问题的卡，块被折成
 *   「（已收起 1 条证据：审查结论）」，链接**一个字都看不见**。
 *   从 Owner 的座位上，那就是「没有报告链接」—— 而盘上 docx 明明建好了
 *   （`📄 合并报告已建（问题数 8 ≥ 3）：…`）。
 *
 * ── 做法：与 `applyMediaRead` **完全同构**
 *
 *   把那一行搬进「可见的字符串格」（`verdict` / `reasoning` / `wrong` / `verdict_text`）。
 *   链接是**要人去点的动作**，它与「我读到了」同级 —— 都不该藏在折叠区里。
 *   §2.5：形态决策只有一处，所以这里只负责**往可见格搬**，不决定卡片类型。
 */
export function applyReportLink(kind, data, reportLink) {
  const url = String(reportLink ?? '').trim();
  if (!url) return { data, action: 'none', slot: null, why: '这一轮没有报告链接' };
  const line = `→ 查看完整问题清单与修改建议：${url}`;
  // ══════════════════════════════════════════════════════════════════════════
  // ★★ 2026-10-13（Owner：「这里多余的回复也去掉」）：**先在整张卡里找一遍**。
  // ══════════════════════════════════════════════════════════════════════════
  //   那一行本来就印在 §5.3 块里 —— **结论行下面第二行**，而那一块**默认展开**
  //   （`applyVerdictLine` 给第一组的是 `expanded: true`，已按真实卡片结构核过）。
  //   再往可见格补一份 ⇒ 同一张卡上出现**两次**同一个链接（Owner 那张视频卡就是这样）。
  //
  //   ⚠️ 与上面「为什么必须有它」不冲突：那一条治的是「链接落在**块的最末尾**、
  //     被 8 条逐条顶到看不见的地方」。现在的口径是「**块里已有就不再补**」——
  //     块里没有（非评审单 / 块没搬进来）时**照旧补进可见格**，一个都不许少。
  if (JSON.stringify(data).includes('查看完整问题清单与修改建议')) {
    return { data, action: 'already', slot: null,
             why: '§5.3 块里已经有这一行（默认展开、就在结论行下面第二行）⇒ 不重复' };
  }
  const out = { ...data };
  const slot = ['verdict', 'reasoning', 'wrong', 'verdict_text']
    .find((k) => typeof out[k] === 'string');
  if (!slot) return { data, action: 'no-slot', slot: null, why: `「${kind}」没有能放链接的格` };
  out[slot] = out[slot] ? `${out[slot]}\n\n${line}` : line;
  return { data: out, action: 'forced', slot };
}

export function toCardOrText(reply, { verdict53 = null, reportLink = null } = {}) {
  // ★★ 2026-10-13（Owner 三条里的第 1、2 条）：**查证笔记在成形之前就摘掉** ——
  //   放在最前面（早于 `extractCardBlock`）是有意的：那几行若被模型抄进卡片块里，
  //   晚一步摘就摘不到了（块里的是 JSON 字符串，按行认不出来）。
  //   ⚠️ 摘下来的原文**进 `stripMoved` 留痕**（日志看得见），不是静默丢弃。
  const stripped = stripInternalNotes(reply);
  const stripMoved = stripped.removed.length
    ? [{ field: 'reply', to: '(memory)', chars: stripped.removed.join('\n').length,
         why: `回复里混进了我自己的查证笔记（${stripped.removed.length} 行）——`
            + '它不上卡（Owner 2026-10-13：卡片与报告都不显示，只在记忆里），已摘除' }]
    : [];
  const raw = s(stripped.text);
  let blk = extractCardBlock(raw);

  /* ★★ 2026-10-12（Owner 现场：「守衡的输出格式变了」）—— **评审单不许以纯文本出门** ──────
   *
   * ── 实测（三方对齐，不是推断）
   *
   *   `PMO/logs/ws_outbound.jsonl` ＋ 会话原文 ＋ `ws_daemon.log`，同一天两条形状：
   *     · 16:58 那条 1336 字 ⇒ `mode=reply-card`（卡片），群里渲染正常；
   *     · 19:31 / 19:53 / 19:55 / 19:58 四条 ⇒ `mode=reply`（**纯文本**），
   *       而它们对应的**模型原文里根本没有 `[[card:` 块**（会话逐条核过，
   *       日志那一行也写着 `📋 PRD §5.3 结论行：…｜落点=n/a·-｜逐条块=无`）。
   *   纯文本在飞书里**不渲染 markdown** ⇒ 群里看到的是 `**加粗**`、反引号、
   *   以及一堆 `|`（`persona.mjs` 的卡片规程早就写着这件事）——这就是 Owner 报的「格式变了」。
   *
   * ── 触发与残留（各占一半，别只修一半）
   *
   *   触发：19:31 那一轮的用户消息里被注入了「【请按短卡作答】…正文 ≤ 300 字，不要展开」，
   *   模型照着写了短答、**顺手把卡片块丢了**。那条指令 19:52 已停用并重启，
   *   可是**停用之后模型照样不给卡**（19:58 那条仍无卡块）⇒
   *   「模型会不会给卡」是**概率**，而 PRD §5.3 的结论行是**必须**落下的东西。
   *
   * ── 所以：与结论行、逐条块**同一条分工** —— **模型不写，代码搬**；模型连卡都不给，
   *    **代码自己建一张**（`evidence`：抬头放权威结论行，模型原话逐字进折叠组）。
   *
   *   ⚠️ 提示词那条路**这一步走不通**：`cardContract()` 已顶到 K5 的冻结上限
   *     （实测 `buildSystemPrompt()` 8497/8500，余量 3 字符）—— 想在里面加一句
   *     「评审单一律用卡」，得先删掉等量文字。在腾出空间之前，**这一跳是唯一的执行点**。
   *
   *   ⚠️ 只对**有权威结论行**的单子生效（`verdict53.line` 非空）：闲聊仍是纯文本，
   *     不许借着 PRD 的名义把所有对话都套成卡（J12d 反向对照钉着）。
   */
  // ══════════════════════════════════════════════════════════════════════════
  // ★★ 2026-10-13（Owner：「我到群里@守衡，群聊的格式跟私聊不一样？」）
  //    **评审单的卡片形状由代码定 —— 不看模型这一轮有没有给卡片块。**
  // ══════════════════════════════════════════════════════════════════════════
  //   先钉事实（`PMO/logs/ws_outbound.jsonl` 今日 9 条）：
  //     · 私聊 6 条评审卡 ⇒ 模型**没给**卡 ⇒ 代码建卡 ⇒ 抬头 + 「审查结论」组 + 卡脚；
  //     · 群里 1 条评审卡 ⇒ 模型**给了**卡 ⇒ 用它 ⇒ 抬头 + 模型自拟的四五个分组 + 卡脚。
  //   而**代码里没有任何群/私聊分叉** —— 形态提示词（`cardContract()`）两条路是同一份，
  //   按会话类型变的只有 `# 当前场景` 那一行。⇒ 差别只来自**模型这一轮的心血来潮**。
  //
  //   这正是 §2.5「形态决策只能有一处」要防的东西：形态由掷骰子决定，表现就是「格式随机」。
  //   ⇒ 口径：**只要有 §5.3 块（＝这是一张评审单），卡面就收敛到同一个形状** ——
  //     抬头＝结论行 · 一组「审查结论」＝§5.3 逐条块 · 卡脚＝边界（+报告链接在可见格）。
  //     模型自拟的分组 / 它的结论格 / 块外正文 **都不上卡**（Owner 前三条已经逐条要走的东西），
  //     但它们**一个字都没丢**：它仍是这一轮的回复正文（会话记忆 + `💬 回复 N 字` 日志）。
  //   ⚠️ 2026-10-13：`boundary` 那一格**整格作废**（Owner：整个都隐藏）⇒ 模型写的边界
  //     也**不上卡**（它仍是这一轮回复正文的一部分，会话记忆里有）。
  //   ⚠️ 没有 §5.3 块时（`verdict53.block` 为空）行为**逐字不变**：模型给的卡照用。
  const reviewShape = !!(verdict53 && verdict53.line && verdict53.block) && !!s(raw).trim();
  const shapeMoved = [];
  if (reviewShape) {
    if (blk) {
      shapeMoved.push({ field: 'cardKind', to: 'evidence',
                        why: '评审单 ⇒ 卡面形状由代码定（Owner 2026-10-13：群里与私聊必须一样）'
                           + ' ⇒ 模型自拟的分组/结论格不上卡（原文仍在会话记忆里）' });
    }
    blk = { kind: 'evidence', error: null, before: '', after: '',
            data: { verdict: '', groups: [] } };
  }

  const autoCard = !blk && !!(verdict53 && verdict53.line) && !!s(raw).trim();
  const autoDedup = [];
  if (autoCard) {
    const line = s(verdict53.line).trim();
    let body = raw;
    // ★ 结论行**独占抬头**（2026-10-09 治过一次「结论行印两遍」）：模型原话里若已经把
    //   这一行原样写出来了，就从折叠组里摘掉它 —— 否则抬头一遍、展开组里又一遍。
    //   ⚠️ 摘完就空了 ⇒ **不摘**：宁可重复一次，也不留一个空的组（那比重复更难读）。
    if (line && body.includes(line)) {
      const stripped = body.split(line).join('').replace(/\n{3,}/g, '\n\n').trim();
      if (stripped) {
        body = stripped;
        autoDedup.push({ field: 'verdictLine', to: 'title',
                         why: '模型原话里已经把结论行写出来了 ⇒ 从折叠组里摘掉（抬头独占，不许印两遍）' });
      }
    }
    // ══════════════════════════════════════════════════════════════════════════
    // ★★ 2026-10-13（Owner 当场给的原文）：「去掉下面这些」——
    //    他展开的那一组正是**模型这一轮的整段原话**（标题叫「详细说明」）。
    // ══════════════════════════════════════════════════════════════════════════
    //   他引的原文里有大量**内部读数**：`P0 快路（258.167 ms…）`、`未跑 L4→L5→L6→L7 与评审链`、
    //   `★ 表行（照抄）…行号 recvxPYwEQOSAe…回读 consistent`、`观察：M8 这句跑第 3 次…`。
    //   那些**不是给群里的人看的**（与「库内命中（读数）」同一个病）。
    //
    //   而这一单真正要读的东西**一个字都不在那一组里** —— 它们由**代码**搬进卡：
    //     抬头 = 权威结论行；第一组 = PRD §5.3 逐条块（原因/依据/建议/判定）；卡脚 = P0 边界。
    //     ⇒ 所以那一组**不再建**。
    //
    //   ⚠️ **安全网（与「拿不到报告链接就退回逐条平铺」同一条）**：
    //     **只有 §5.3 块真的搬得进来时才不建那一组**。`verdict53.block` 可能是 null
    //     （`conclusionBlock()` 找不到动作行时），那时卡上会只剩一个抬头 ——
    //     比改动之前**更没法用**。所以那时照旧把原话放进「详细说明」组。
    //   ⚠️ 模型这一轮的原文**没有丢**：它仍是这一轮的回复正文（`ws_daemon` 记
    //     `💬 回复 N 字`，`memory` 也原样存着这一条 assistant 轮）。
    const dropProse = !!verdict53?.block;
    blk = {
      kind: 'evidence',
      error: null,
      before: '',
      after: '',
      // `verdict: ''` 是**留槽位**，不是留空话：`applyReportLink`
      // 只往 `verdict / reasoning / wrong / verdict_text` 里搬，
      // 一个都不给的话，**拿不到 §5.3 块的单子**会连报告链接都没地方落。
      // 留空串 ⇒ 它们搬得进来；而结论行走的是**抬头**（`verdictSlotOf('evidence')='title'`），
      // 两样各占一格，**不会印两遍**。
      data: { verdict: '',
              groups: dropProse ? [] : [{ title: '详细说明', content: body, expanded: true }] },
    };
    if (dropProse) {
      autoDedup.push({ field: 'groups', to: '(不建)',
                       why: '模型原话整组不上卡（Owner 2026-10-13：那一组里是内部读数；'
                          + '要读的三样由代码搬进卡 —— 抬头 / §5.3 逐条块 / 卡脚边界）' });
    }
  }

  if (!blk) {
    const lint = lintCopy(raw);
    const leak = lint.find((h) => h.id === 'internalLeak');
    if (leak) {
      // ★ 纯文本**没有折叠区可放**，而「内部详情只进折叠区」是 §2.4 点名的硬约束；
      //   `agent-skills/守衡语域/SKILL.md` 第 7 条写得更直白：
      //   「**不是改写，是不许写。** 内部详情只进折叠区」。
      //
      //   所以这里既不原样发、也不做改写（改写就违反「不是改写」那句话）——
      //   换成一句诚实的降级说明，原文留在日志里。
      //
      //   2026-09-17 那条真事故（连列 19 次 `list_files` 的 434 字故障输出）**正是纯文本**：
      //   当时它通过了除第 7 条以外的全部内容级检查，而第 7 条在**这条路径上没有执行点**。
      //   检测器（`lintCopy`）一直是对的 —— 缺的是「动作」。
      //
      // ★ 2026-09-22：这句话里「原始内容留在 PMO/logs」曾经是**假的** ——
      //   说出去的时候盘上什么都没有（实测 16:34 那次，`PMO/logs/` 里没有任何新文件）。
      //   现在它有执行点：`ws_daemon.mjs` 的 `dumpDropped()`，接在 `shaped.dropped`
      //   分支上，落点 `PMO/logs/dropped/`。所以**这句话里的路径必须与那里一致** ——
      //   改落点就要同时改这里，`verify_cards.mjs` 的 L7 断言两处对得上。
      return {
        mode: 'text',
        text: '我这次没能把回答组织好 —— 正文里混进了内部记录，已经拦下没发出去。'
            + '原文我留在 PMO/logs/dropped/ 了，需要的话我重新答一次，不会丢。',
        reason: `正文含内部标识（internalLeak×${leak.count}），纯文本没有折叠区可放 → 不原样发`,
        moved: stripMoved,
        lint,
        dropped: true,
      };
    }
    const text = leadWithVerdict(raw, verdict53);
    return { mode: 'text', text, reason: null, moved: stripMoved, lint: lintCopy(text), dropped: false,
             verdict53: verdict53 ? 'text-lead' : null };
  }

  // 找到了标记但数据不可用 → 剥掉整块（含标记与半截 JSON），只留可读的话。
  // 这一步是硬要求：`[[card:...]]` 出现在群里 = 内部格式泄漏，和泄漏 tool_calls 同类。
  if (!blk.data) {
    const text = [blk.before, blk.after].filter(Boolean).join('\n\n').trim()
      || `我这次没能把回答组织成卡片（${blk.error}），上面这条就是我能给出的全部。`;
    return {
      mode: 'text', text, reason: `卡片块不可用：${blk.error}`,
      moved: stripMoved, lint: lintCopy(text), dropped: true,
    };
  }

  // ★★ 评审单的 PRD §5.3 逐条块**必须落得下**（2026-10-07 实测缺口）──────────────
  //   卡片类型由**模型挑**，而 11 种类型里**只有两种**装得下 §5.3 的逐条块：
  //     `query-answer`（有 `reasoning`）与 `evidence`（有 `groups`）—— `blockSlotOf()` 就认这两个。
  //   挑到别的类型（如 `turn-diff` 改口卡、`data-table`、`receipt`…）⇒ `applyVerdictLine`
  //   只能返回 `no-slot`，**块被静默丢掉**，群里就只剩模型自己写的话。
  //   实测（2026-10-07 16:21，Owner 当场报「你改了后就不按 PRD 格式输出了」）：
  //     同一文案第三次送审、合并结论由 REVIEW 变 BLOCK ⇒ 模型挑了 `turn-diff` 去解释差异
  //     ⇒ 日志只留一行 `逐条块=no-slot·-`，卡片照发 ⇒ **§5.3 结论块整块不见了**。
  //   修法：**评审单（`verdict53.block` 非空）＋ 类型装不下 ⇒ 换成 `evidence`**，
  //     并把原卡内容**逐字搬进第一组**（模型写的差异说明一个字不丢；换的是外壳，不是内容）。
  //   为什么不是「拒绝发送」：结论与依据比外壳重要 —— 丢块是缺陷，丢整条回复是更大的缺陷。
  let kd = blk.kind;
  let dd = blk.data;
  const remap = [];
  remap.push(...shapeMoved);
  // ★ 代码建的卡也要**出声**：日志里必须看得见「这一单的卡不是模型给的」——
  //   否则「模型忘了给卡」这件事只会以「格式变了」的样子出现在群里（今天就是这样）。
  if (autoCard) {
    remap.push(...autoDedup);
    remap.push({ field: 'cardKind', to: 'evidence',
                 why: '本单有权威结论行，而模型没给卡片块 ⇒ 代码建卡'
                    + '（纯文本不渲染 markdown，格式会整块丢；判据 J12a–c）' });
  }
  if (verdict53 && verdict53.block && !blockSlotOf(kd)) {
    const carried = carryCardText(dd);
    remap.push({ field: 'cardKind', to: 'evidence',
                 why: `「${kd}」没有能放 §5.3 逐条块的格（既无 reasoning 也无 groups）`
                    + ' ⇒ 换 evidence，原卡内容逐字搬进第二组' });
    dd = { verdict: s(dd?.verdict).trim() || s(dd?.title).trim() || '',
           // ★ 2026-10-09（Owner）：**标题不许出现内部类型名**（「原「data-table」卡」对业务同事
           //   是零信息量）。内容仍**逐字照搬**（`carryCardText` 一个字没动）。
           // ⚠️ 标题要与 `foldIn` 那个（「（原文照留：模型原话，非权威结论）」）**明显不同** ——
           //   两处都写「原文照留」时，读者会把两组当成**同一段的重复**，而它们装的
           //   其实是两样东西：这一组装「原结论格 + 字段表」，那一个装「卡片块之外的正文」。
           // ★ 2026-10-13（Owner）：另一处原先叫「模型原话（原文照留）」的组标题也去掉了
           //   —— 「模型」是我们的内部说法，对群里的人是零信息量。改名后两组标题仍有明显区别。
           groups: [{ title: '原结论（原文照留）', content: carried || '（原卡无正文）',
                      expanded: true }] };
    kd = 'evidence';
    // ★★ 2026-10-09：**结论格在这里就落权威结论行**（治「结论行印两遍」）────────────
    //   病灶（实测复现，文案单那张卡里「【审查结论：REVIEW】」出现 **2 次**）：
    //     · ① `carryCardText` 已把原卡的 `verdict`（模型那句）**逐字搬进 `groups[0]`**，
    //          而换卡后 `dd.verdict` 仍留着**同一句**；
    //     · ② 紧接着 `applyVerdictLine` 看到 `verdict` 槽"有内容且不等于结论行"
    //          ⇒ 走 ①「先把模型原来那句搬进折叠区」那一支 ⇒ **再折一份**，
    //          然后才把结论行写进 `verdict`。
    //     ⇒ 同一句模型原话在卡上出现两次（一次在 `groups[0]`、一次在折叠组，
    //        标题还各不相同），且**结论行也跟着出现两次**。
    //   修法：换卡时**先把结论行放进 `verdict`** ⇒ 后面那次 `applyVerdictLine` 走
    //     `cur === verdict.line` 的 `already` 支 ⇒ **不折、不写** ⇒ 天然不重复。
    //     （原内容已由 `carried` 保住，一个字没丢 —— 「搬是搬，砍是砍」。）
    if (verdict53?.line) dd.verdict = verdict53.line;
  }

  // 块前后还有正文：不是丢弃，是并进这张卡里该放它的格子。
  // 模型多写的话通常是有用的补充，但**不能留在块外** ——
  // 留在块外，群里看到的就是「一张卡 + 一段重复的话」。
  const extra = [blk.before, blk.after].filter(Boolean);
  let v53 = null;
  const built = (() => {
    let { data, moved } = enforceLimits(kd, dd, extra);
    moved.push(...remap);
    // ★ 2026-10-13：摘掉的查证笔记也要留痕（否则「它本来就没写过」与
    //   「写了、被我摘了」在日志里长得一模一样 —— `verify_cards` 的 J13d 钉着）。
    moved.push(...stripMoved);
    // ★ PRD §5.3 结论行必须在 `build()` **之前**落进结论格 ——
    //   建完卡再改 `data` 不会影响已经建出来的那张卡（改了也不报错，只是白改）。
    const applied = applyVerdictLine(kd, data, verdict53);
    data = applied.data;
    if (applied.moved) moved.push(applied.moved);
    // ★★ 2026-10-13：**媒材读数不再上卡**（Owner：「这里多余的回复也去掉」）。
    //   ⇒ 这一跳的接线**撤了**，`mediaRead` 这个选项也一并撤掉 ——
    //     **留一个没人读的入参就是「传了但没人接」那个病**（同一天刚在
    //     `ws_daemon.replyTo` 的 `reportLink` 上抓到一次，见 test_agent 的 Z20b）。
    //   纯函数 `applyMediaRead` 留着（`p0ShortReplyBlock` 那个先例），要恢复就是把这一跳加回来。
    // ⚠️ 2026-10-13：卡脚那一跳**整块已作废**（Owner：「整个都隐藏，不要展示在卡片上」）。
    //   原先这里往卡脚写 P0 边界 ⇒ 现在那一句改走 `dual_track.internalNotes`（记忆侧，答得出来）。
    // ★ 2026-10-09：**报告链接也搬进可见格** —— 它此前只在结论块里，而那一块会被收起
    //   （Owner 第三次反馈「没有报告链接」，而 docx 其实建好了）。
    const rl = applyReportLink(kd, data, reportLink);
    data = rl.data;
    // ★ 2026-10-08：这条搬迁记录原先压的是 `{ what: 'mediaRead', to }` —— 而日志格式器
    //   （`ws_daemon.mjs` 的 `↪ ${m.field} → ${m.to}（${m.why}）`）读的是 `field` / `why`，
    //   于是实测在图片单上打出一行 `↪ undefined → verdict（undefined）`：
    //   看得见「有东西搬进 verdict」，看不见**搬的是什么、为什么**。形状对齐其余搬迁记录。
    v53 = { action: applied.action, slot: applied.slot, why: applied.why,
            from: verdict53?.from ?? null, line: verdict53?.line ?? null,
            // 逐条块的落点也一起带出去 —— 否则日志里只看得到「标题搬了」，
            // 看不到「逐条四要素到底进没进正文」（2026-10-06 Owner 就是在这上面又逮到一次）。
            block: applied.block ?? null };
    try {
      // 先按数据把长度上限执行掉、再建卡，最后按**建出来的卡**数顶层段落。
      // 顺序不能颠倒：段落数只有卡建出来才存在。
      const capped = capSections(build(kd, data));
      if (capped.moved.length) moved.push(...capped.moved);
      return { card: capped.card, data, moved, err: null };
    } catch (e) {
      return { card: null, data, moved, err: e.message };
    }
  })();

  if (!built.card) {
    // 降级：剥掉整块，只发可读的话。不把坏 JSON 吐进群 —— 那是 2026-09-17 那条故障的同类。
    const text = [blk.before, blk.after].filter(Boolean).join('\n\n').trim()
      || `我本想用「${kd}」卡片回答，但这张卡没通过本地校验，所以这条只能以纯文本发出。`;
    return {
      mode: 'text', text,
      reason: `卡片 ${kd} 构建失败：${built.err.split('\n')[0]}`,
      moved: built.moved, lint: lintCopy(text), dropped: true,
    };
  }

  const text = renderText(built.card);
  return {
    mode: 'card', card: built.card, data: built.data, kind: kd,
    text, reason: null, moved: built.moved, lint: lintCopy(text), dropped: false,
    verdict53: v53,
  };
}

/**
 * **守衡自己的「查证笔记」不许进群** —— 在成形之前按行摘掉（纯函数，可离线断言）。
 *
 * ── 为什么要有它（2026-10-13，Owner 三条里的第 1、2 条）
 *
 * Owner 原话：「输出到飞书群包含知识库侧+模型侧的文字，**不要展示在卡片上**，
 * **我问的时候，你要能回答**」，并把那一族口径读数逐条列进了「类似以下的文案都去掉」：
 *
 *   · `知识库侧 未报内容问题；另有 1 条覆盖缺口… ／ 模型侧 7 条（其中 7 条无库内依据…）`
 *   · `ℹ️ 知识库侧给了 **覆盖缺口**（`coverage_not_covered`）…`
 *   · `（问题数 8 ≥ 3 ⇒ 按 PRD §5.3.3 只出分类汇总…）`
 *
 * ── 分工（与结论行、逐条块同一条：**模型不写、代码搬**）
 *
 *   `dual_track.renderMerged` 已经把这几行**从 `block` 里摘掉**（模型没有可逐字转述的源），
 *   它们改走 `internalNotes` → `agent.mjs` 的 `chainBlock`（模型上下文 + **会话记忆**）
 *   ⇒ 这一轮答得出、以后每一轮也答得出（Owner 要的「我问的时候你要能回答」）。
 *
 *   但「模型从不照抄 `chainBlock` 里别的东西」是**概率，不是保证** ——
 *   而这几行一旦被抄进去，就会顺着卡片正文进群。所以这里是**执行点**：
 *   逐行认我们**自己产出的那几种固定形状**，命中即摘，并留痕（`removed`）。
 *
 * ⚠️ 判据**只认我们自己的字符串**（前缀 + 关键片段），不做泛化匹配 ——
 *   实测否掉的写法：「凡出现『知识库侧』就摘」会把**正常句子**一起摘掉
 *   （`知识库侧 3 条与素材相关` 是模型在如实转述，它该留着）。
 *   反向对照（`verify_cards.mjs` 的 J13）钉着这一条：普通句子**必须**原样留下。
 *
 * ⚠️ 摘的是**我们自己生成的行**，不是改写模型的话 ——
 *   与 `internalLeak` 那条「不是改写，是不许写」同源，区别只在于：
 *   那一条没有折叠区时只能**整条拦下**，而这几行有明确的归属（记忆里还有一份），
 *   所以按行摘掉比把整条回复丢掉**代价小得多、也不会丢内容**。
 *
 * @param {string} text 模型这一轮的原文
 * @returns {{text:string, removed:string[]}} 摘完的文本与摘掉的原文行（留痕用）
 */
export function stripInternalNotes(text) {
  const src = s(text);
  if (!src) return { text: src, removed: [] };
  // 我们自己的那几种固定形状（`dual_track.renderMerged` 是唯一产者）。
  const RULES = [
    /^知识库侧 .*／\s*模型侧 /,                       // tally
    /^知识库侧 \*\*本次未参与\*\*/,                    // tally（库侧没读数那一支）
    /^ℹ️ 知识库侧给了 \*\*覆盖缺口\*\*/,               // covNote
    /^⚠️ 知识库侧另有 \*\*\d+ 条\*\*未并进本卡/,        // gapNote（kbN ≥ 3）
    /^⚠️ 知识库侧的结构化读数是 \*\*\d+ 条\*\*/,        // gapNote（kbN < 3）
    /^⚠️ \*\*本次知识库侧没有读数\*\*/,                 // noReadNote
    /^⚠️ 另有 \*\*\d+ 条非权威候选线索\*\*/,            // candNote
    /^（问题数 \*\*\d+ ≥ 3\*\* ⇒ 按 PRD §5\.3\.3 只出分类汇总/,   // 汇总页脚
  ];
  const removed = [];
  const out = [];
  for (const line of src.split('\n')) {
    const t = line.trim();
    // ★ 查证笔记的**整段**（`agent.mjs` 的 chainBlock 里那一段）——
    //   模型把整段抄下来时，这一条比逐行认更早兜住（含它自己的首尾标记）。
    if (/^【★ 我的查证笔记/.test(t)) { removed.push(line); continue; }
    if (/^【★ 查证笔记结束】/.test(t)) { removed.push(line); continue; }
    if (RULES.some((re) => re.test(t))) { removed.push(line); continue; }
    out.push(line);
  }
  if (!removed.length) return { text: src, removed: [] };
  return { text: out.join('\n').replace(/\n{3,}/g, '\n\n').trim(), removed };
}

/**
 * 自证用：一段输出里到底有没有残留内部标记。
 *
 * 两种泄漏必须分开判，因为**修法完全不同**：
 *
 *   文本层 —— 要发出去的正文（含降级文本）里出现 `[[card:` 或 `tool_calls` 之类，
 *             就是故障，一个字符都不许有。这是 2026-09-17 那条回复的同类。
 *   JSON 层 —— 卡片结构里出现内部标识，只有一种情况允许：它**在折叠面板内部**。
 *             折叠区是 `alert` 这个类型存在的理由 —— 内部详情必须有个地方放，
 *             否则模型只能往正文里写。判据是「公开格干净」，不是「整张卡干净」。
 *
 * @param {string} text 要发出去的文本
 */
export function leaksInternalMark(text) {
  const src = s(text);
  return /\[\[card:/.test(src)
      // ★ 判据只有一处：`lintCopy` 的 `internalLeak`。
      //   这里原先自带一条**更窄**的正则 —— 只认 `tool_calls|tool_call_id|finishReason|
      //   reasoning_tokens` 与 `"role":"tool"`，**连 `call_xxx` 与栈帧都不认**。
      //   而 J2 段正是用这个函数断言「发出去的文本里没有内部标记」：
      //   断言用的检测器比实际动作的判据还弱，等于给了它一张假的免罪符。
      || lintCopy(src).some((h) => h.id === 'internalLeak');
}

/** 公开格（非折叠区）的文本。自证用它断言「对方一眼能看到的地方」是干净的。 */
export function publicTextOf(card) {
  const out = [];
  const walk = (els, insideCollapse) => {
    for (const el of els ?? []) {
      if (el.tag === 'collapsible_panel') { walk(el.elements, true); continue; }
      if (insideCollapse) continue;
      if (el.tag === 'markdown') out.push(el.content ?? '');
      else if (el.tag === 'table') {
        out.push((el.columns ?? []).map((c) => c.display_name ?? c.name).join(' '));
        for (const r of el.rows ?? []) out.push(Object.values(r).join(' '));
      } else if (el.tag === 'column_set') for (const c of el.columns ?? []) walk(c.elements, false);
      else if (el.tag === 'code_block') out.push(el.text ?? '');
      else if (el.tag === 'plain_text') out.push(el.content ?? '');
    }
  };
  walk(card?.body?.elements, false);
  return [card?.header?.title?.content ?? '', card?.header?.subtitle?.content ?? '', ...out].join('\n');
}

/** 供 verify 与 CLI 用：哪些常量真的被读了 */
export const ENFORCED = { VERDICT_MAX, MAX_SECTIONS, KINDS: Object.keys(BUILDERS), validateCard, capSections };
