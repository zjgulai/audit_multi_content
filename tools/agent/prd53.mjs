/**
 * prd53.mjs —— **PRD §5.3 三态结论输出规范**的判据（纯函数，无副作用）
 *
 * ── 为什么要有它（2026-10-06，Owner 在飞书私聊里发现三条回话格式不合规）
 *
 * 上游 PRD 从 v1.0 改到 v1.2 时，把 §5.3 拆成 5.3.1/5.3.2/5.3.3，并**引入了
 * `【审查结论：PASS/REVIEW/BLOCK】` 这个标记**（改动登记在
 * `PMO/守衡-上游第三版基线与影响登记-20260922.md` §5.3 那一行）。
 * 同一天，那份记录的第 317 行就把下面这个问句挂在那儿了：
 *
 *   > **② 新的三态输出规范（`【审查结论：…】` + 问题数分流）要不要落进回复卡片模版？**
 *
 * 当时的答案是「记在这里，**没有擅自改任何代码**」。半个月后 Owner 在群里看见的
 * 就是没落地的后果：链路侧其实**已经**按 5.3 产出了结论行（`review_gate.formatChainBlock`
 * 也写了「逐字转述，不许改写」），而**回卡片那一跳把表头改写掉了** ——
 * `【审查结论：REVIEW】共发现 1 处需人工确认。` 变成 `【证据】REVIEW：1 处问题（W-1.54 静音绝对化）`。
 *
 * ── 这一层是「判据」，执行点在 `reply-cards/envelope.mjs`
 *
 * 按 `AGENTS.md` §2.5「形态决策只能有一处」：**模型不写结论行，结论行由代码搬进去**。
 * 所以这里只回答两个问题 ——「链到底给了哪一行」「这一行合不合 5.3」——
 * 真正的改写动作在 `envelope.applyVerdictLine()`，唯一的调用链是
 * `ws_daemon.replyTo → toCardOrText`。
 *
 * ── 判据的边界（写清楚，免得下一轮有人拿它当万能尺）
 *
 *   · 只认 PRD §5.3 定义的三态：`PASS` / `REVIEW` / `BLOCK`。
 *     `NEEDS_INPUT`（依据侧拒答）**不在 5.3 里** —— 它没有规范行可搬，
 *     所以这里对它返回 `null`（不搬、也不编一行出来）。要不要给拒答开第七档，是**另一件**。
 *   · 措辞是**逐字**判的：REVIEW 必须是「需人工确认」、BLOCK 必须是「必须修改」。
 *     这一条不是洁癖 —— 引擎原先两态共用「需处理问题」，而 KB 那条判据只查到
 *     「共发现」为止，于是**跑了半个月没人发现**（`AGENTS.md` §2.4）。
 */

/** 三态标记。**顺序有意义**：`BLOCK` 要排在 `PASS` 前面做前缀匹配时不会互相吃掉，但读起来清楚。 */
export const STATES = ['PASS', 'REVIEW', 'BLOCK'];

/** 结论行：从 `【审查结论：` 起到本行结尾。行内不许有换行（它是「一行结论」）。 */
const LINE_RE = /【审查结论：(PASS|REVIEW|BLOCK)】[^\n]*/;

/**
 * 从一段文本里取出**第一行** `【审查结论：…】…`。
 *
 * @param {string} text
 * @returns {{state:string, line:string}|null}
 */
export function conclusionLine(text) {
  const m = LINE_RE.exec(String(text ?? ''));
  if (!m) return null;
  return { state: m[1], line: m[0].trim() };
}

/**
 * 这一行合不合 PRD §5.3 的**逐字措辞**？
 *
 * 判据按态分开，因为 PRD 对三态是三句不同的话：
 *   · 5.3.1 PASS  —— `【审查结论：PASS】未发现已知底线风险，可转交 @<负责人> 进行 sign-off`
 *   · 5.3.2 REVIEW —— `【审查结论：REVIEW】共发现 N 处需人工确认。`
 *   · 5.3.3 BLOCK  —— `【审查结论：BLOCK】共发现 N 处必须修改。`
 *
 * @param {string} line
 * @returns {{ok:boolean, state:string|null, why:string}}
 */
export function conforms(line) {
  const s = String(line ?? '').trim();
  const head = LINE_RE.exec(s);
  if (!head) return { ok: false, state: null, why: '整行里没有【审查结论：<态>】标记' };
  const state = head[1];

  if (state === 'PASS') {
    // ⚠️ 判据**不**要求 @ 后面是一个真句柄：`kb/l7/registry/l7.json` 的 approvers 现在是
    //    `configured: false`，库规要求此时输出「角色名（未配置）」。
    //    第一版写成 `@\S+ 进行 sign-off`，当场把**正确的**夹具判红 —— 会误报的判据比没有更糟，
    //    同一条已经在这套改动里踩过两次了（KB 侧 `l7_integrity.py` 两处）。
    const ok = /^【审查结论：PASS】未发现已知底线风险，可转交 @\S[^\n]*进行 sign-off/.test(s);
    return { ok, state, why: ok ? '与 §5.3.1 逐字一致' : 'PASS 行必须含「未发现已知底线风险，可转交 @…进行 sign-off」' };
  }
  if (state === 'REVIEW') {
    const ok = /^【审查结论：REVIEW】共发现 \d+ 处需人工确认。$/.test(s);
    return { ok, state, why: ok ? '与 §5.3.2 逐字一致' : 'REVIEW 行必须是「共发现 N 处需人工确认。」' };
  }
  const ok = /^【审查结论：BLOCK】共发现 \d+ 处必须修改。$/.test(s);
  return { ok, state, why: ok ? '与 §5.3.3 逐字一致' : 'BLOCK 行必须是「共发现 N 处必须修改。」' };
}

/**
 * 这一行是不是出现在**整段回复的最前面**（跳过空行与 markdown 装饰）。
 *
 * ★ 只用来做**兜底**判据（见 `deriveVerdictLine` 的第 ③ 条）。判据这么窄是有原因的：
 *   「回复里任何地方出现一行 5.3 模板」不等于「这是一条审查结论」——
 *   有人问「PRD 5.3 里 PASS 长什么样」，守衡照抄一遍模板，那**不是**一次审查结论。
 *   排在最前面才算它自己在用这一行。
 */
export function leadsWith(text, line) {
  const rows = String(text ?? '').split('\n').map((x) => x.trim()).filter(Boolean);
  if (!rows.length) return false;
  const first = rows[0].replace(/^[*_>`\s]+|[*_`\s]+$/g, '');
  return first === String(line ?? '').trim();
}

/**
 * **PRD §5.3 的结论块**：从结论行起到**动作行**止（含）。
 *
 * ★ 2026-10-06 加（同一处事故的第二半）。只把**结论行**搬进标题是不够的：
 *   Owner 拿 PRD §5.3.3 的模板对照守衡发出去的 BLOCK 卡片 —— **抬头对了、逐条四要素整块没有**。
 *   根因是卡片的正文（`verdict` / `reasoning`）由**模型转述**，而模型会把一整块「逐条」
 *   压缩成一句「命中 W-1.18 与 W-1.13 两条 P0，不能发」。
 *   修法与结论行同一条（§2.5 的分工）：**模型不写这一块，代码搬**。
 *
 * 动作行按 PRD 的收尾认：BLOCK = `请修改后重新提交。`；REVIEW = `建议转 … 复核。`
 * 没有动作行 ⇒ 返回 null（**不搬半截**：半截块比不搬更容易被读成完整结论）。
 *
 * @param {string} text 链 / P0 快路给的结论原文
 * @returns {string|null}
 */
export function conclusionBlock(text) {
  const s = String(text ?? '');
  const head = LINE_RE.exec(s);
  if (!head) return null;
  const rest = s.slice(head.index);
  const m = /\n(?:请修改后重新提交。|建议转[^\n]*复核。)/.exec(rest);
  if (!m) return null;
  const block = rest.slice(0, m.index + m[0].length).trim();
  // 只有结论行、没有逐条（PASS 就是这样）⇒ 不算「块」，没什么可搬的
  return block.includes('\n') ? block : null;
}

/**
 * 由**显式条数**生成 §5.3 的结论行（纯函数）。
 *
 * ── 为什么需要它（2026-10-08，Owner 定的规则）
 *
 * Owner 的规则原话：「我在飞书侧 @守衡 提问后，双轨并行（知识库+模型），
 * **双轨按照 PRD ≧3 个问题输出报告链接到飞书文档**」。
 *
 * 查下来 PRD 那一侧**早就实现了**（`kb/l7/review-engine/core/feishu_publish.py`：
 * `REPORT_LINK_MIN_ISSUES = 3`，且留痕「10-03 曾改判为 0，Owner 裁定后已回退为 3」）。
 * 真正坏的是**口径**：一单里有**三个**「问题数」在打架 ——
 *
 *   | 数 | 来自谁 | 19:44 那单 | 19:08 那张图 |
 *   |---|---|---|---|
 *   | 卡片抬头那个数 | 链的结论原文（被 `conclusionLine` **正则抠**出来） | — | **12** |
 *   | 报告阈值读的数 | 机读旁挂 `issue_count` | **2** | 5 |
 *   | 人实际看到的条目 | 双轨合并条数 | **10** | 7 |
 *
 * 人看到 10 条 ⇒ 按规则该给链接；而阈值读的是 2 ⇒ `2 < 3` ⇒ 不生成报告 ⇒ **没有链接**。
 * 从人的座位上，这条规则就是没生效。
 *
 * ── 这个函数在「统一成一个数」里的位置
 *
 * 抬头那个 N 现在是**从链的正文里抠**出来的（`deriveVerdictLine` 第 ① 支），
 * 所以它天生就是「链自己的数」—— 这就是口径打架的根。
 * 把它变成**入参**之后，抬头、逐条块、报告阈值读的才是**同一个变量**。
 *
 * 这不是新发明：`deriveVerdictLine` 第 ② 支（P0 快路）**早就是**按显式条数派生一行
 * （用 `p0_fastpath.matched_patterns`）。这里只是把同一个形状补到双轨这一支上。
 *
 * @param {{state?:string, n?:number}} input
 * @returns {{state:string, line:string, conform:object}|null}
 *   派生不出来时回 `null` —— **绝不编一个 N**（§2.4：「共发现 ? 处」比不搬更坏）。
 */
export function verdictLineFor({ state, n } = {}) {
  const st = String(state ?? '').toUpperCase();
  const count = Number(n);
  // 只认「≥1 的整数」：
  //   · `undefined` / `NaN` / 字符串 ⇒ 不派生
  //   · 小数、负数 ⇒ 不派生（那是坏读数，不是条数）
  //   · **0 ⇒ 不派生**。这一条是独立的判断，不是顺带：`mergedState()` 里
  //     「合并 0 条 + 库侧 REVIEW」会给出 REVIEW（覆盖缺口那一类），
  //     而 `【审查结论：REVIEW】共发现 0 处需人工确认。` **自己跟自己矛盾**。
  //     那时退回链那一行更诚实 —— 链自己数出了几条，就照它说。
  if (!Number.isInteger(count) || count < 1) return null;

  let line = null;
  if (st === 'REVIEW') line = `【审查结论：REVIEW】共发现 ${count} 处需人工确认。`;
  else if (st === 'BLOCK') line = `【审查结论：BLOCK】共发现 ${count} 处必须修改。`;
  // PASS 的模板（§5.3.1）里**没有 N**，所以派生不出来；拒答 / NEEDS_INPUT 不在 §5.3 里。
  else return null;

  return { state: st, line, conform: conforms(line) };
}

/**
 * **权威结论行**：这一轮该往卡片里搬哪一行。
 *
 * 四条来源，按可靠性排序（前两条是「链说的」，第三条是「模型自己排在最前面的」）：
 *
 *   ⓪ **双轨跑过 ⇒ 用双轨合并数派生**（2026-10-08 加）。
 *      为什么它排在最前：第 ① 支那个 N 是**从链的正文里抠**出来的，
 *      而人在卡片上看到的条目是**双轨合并**之后的 —— 两个数天然不等
 *      （实测 19:08 那张图：抠出来 12、合并 7、阈值读 5）。
 *      报告链接的门槛（PRD §5.3.4「问题数量 ≥3」）挂在哪个数上都不是重点，
 *      重点是**只能有一个数**：抬头、逐条块、阈值读同一个变量。
 *      ★ 传进来的数不合法（缺失 / 0 / NaN / 非整数）时**退回第 ① 支**，
 *        而不是编一个 N —— 派生是**加强**，不是取代兜底。
 *
 *   ① 链返回的结论原文里有 5.3 行 ⇒ **用它**。链是这条结论唯一的产者，也是唯一有权改它的人。
 *   ② 走的 P0 快路 ⇒ 按 §5.3.3 **派生**一行：`【审查结论：BLOCK】共发现 N 处必须修改。`
 *      为什么必须派生：P0 快路的抬头是 `【P0 红线拦截：BLOCK】`（那是**来路**标注，不是结论行），
 *      而 PRD §6.3 第一层明确「P0 命中即停并直接 BLOCK」—— 它就是一条 BLOCK。
 *      不派生的话，P0 这条永远拿不到 5.3 的结论行，而它恰恰是最该被一眼看懂的一态。
 *   ③ 都没有、但模型自己把一行 5.3 结论摆在回复最前面 ⇒ 用它的。
 *      （补发队列重跑那一跳拿不到 `meta`，这是给那条路留的兜底。）
 *
 * @param {{answer?:string, p0Fastpath?:object|null, replyText?:string,
 *          mergedCount?:number|null, mergedState?:string|null}} input
 *   `mergedCount` / `mergedState` 由**双轨合并**那一路传来（`dual_track.mjs`）。
 *   不给就是没跑双轨 ⇒ 行为与本改动之前**逐字相同**（这一条有反向对照守着）。
 * @returns {{state:string, line:string, from:string}|null}
 */
export function deriveVerdictLine({ answer = '', p0Fastpath = null, replyText = '', reviewedByTool = false,
                                    mergedCount = null, mergedState: mState = null } = {}) {
  // ── ⓪ 双轨合并数优先（见函数头那段注释）────────────────────────────────
  //
  //   `block` 这一格**照第 ① 支的写法原样给**（`conclusionBlock(answer)`），
  //   不自己造一个块 —— 逐条块由信封层的 `groups` 那一跳负责
  //   （实测日志：`逐条块=forced·groups`），这里改块会与它抢同一格。
  //   所以本支相对改动之前，**唯一**的差别就是那一行里的 N。
  const derived = verdictLineFor({ state: mState, n: mergedCount });
  if (derived) {
    return { ...derived, from: 'dual-track-merged', block: conclusionBlock(answer) };
  }

  const fromChain = conclusionLine(answer);
  // ★ 每一条来源都带上 `conform` 读数（2026-10-06 加）：
  //   链是这一行的**产者**，而它自己的措辞也会回退（实测：2026-10-06 之前
  //   REVIEW 与 BLOCK 共用「共发现 N 处需处理问题」，跑了半个月没有东西变红）。
  //   搬进来的时候顺手判一次，不合规就在发送层记一行 —— **回退必须看得见**，
  //   而不是等到人又在群里发现格式不对（AGENTS.md §2.4.1 第 5 行：
  //   一个会过期的读数，必须有东西在它过期时出声）。
  if (fromChain) return { ...fromChain, from: 'chain', conform: conforms(fromChain.line),
                          block: conclusionBlock(answer) };

  if (p0Fastpath) {
    const n = Number(p0Fastpath.matched_patterns);
    if (Number.isFinite(n) && n > 0) {
      const line = `【审查结论：BLOCK】共发现 ${n} 处必须修改。`;
      return { state: 'BLOCK', line, from: 'p0-fastpath', conform: conforms(line),
               block: conclusionBlock(answer) };
    }
    // 命中数读不出来 ⇒ **不派生**（编一个「共发现 ? 处」比不搬更坏）。
    return null;
  }

  const fromReply = conclusionLine(replyText);
  if (fromReply && leadsWith(replyText, fromReply.line)) {
    return { ...fromReply, from: 'reply', conform: conforms(fromReply.line),
             block: conclusionBlock(replyText) };
  }

  // ── ④ **闸门没判它是送审，但模型自己调了 `kb_review_chain`**（2026-10-06 加）────────
  //
  //   真事故（Owner 发的截图）：`M9 吸奶器限时优惠中，下单立减 100 元。`
  //   —— 23 字、无媒材、无链接、没命中送审词 ⇒ **闸门判「不是送审」**，
  //   于是 `runSubmissionGate` 直接返回 `verdict53: null`；而模型**自己**决定调了链
  //   （日志里只有 `🔧 工具: kb_review_chain(97179ms)`，没有 `🧭 送审链返回`），
  //   拿到结论后自己写了抬头 `REVIEW 1 处：W-1.16「限时」（覆盖不成立）`。
  //   ⇒ 卡片格式与 PRD §5.3 不符，**而守衡这一侧没有任何东西察觉**。
  //
  //   `reviewedByTool === true` 是这一支的**唯一凭据**：这一轮真的调过 `kb_review_chain`
  //   且成功了。有了它，「回复里出现一行合 §5.3 的结论」就**是**这次审查的结论，
  //   而不是「有人在问 5.3 模板长什么样」——③ 之所以要求「排在最前面」，防的正是后一种；
  //   而那种对话**不会伴随一次成功的送审调用**。
  if (fromReply && reviewedByTool && conforms(fromReply.line).ok) {
    return { ...fromReply, from: 'reply-tool', conform: conforms(fromReply.line),
             block: conclusionBlock(replyText) };
  }
  return null;
}
