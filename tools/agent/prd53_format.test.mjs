#!/usr/bin/env node
/**
 * prd53_format.test.mjs —— **PRD §5.3 的分段（空行）判据**
 *
 * ## 两条规则（Owner 2026-10-14 分两次说清，**第二次推翻了我第一次的做法**）
 *
 *   Owner 第一次：「审核结论中 1，2...每条之间需要空一行的（不管是小于3条飞书侧输出的，
 *                  还是大于等于3条输出审查报告的），都要跟 prd 对齐」
 *   Owner 第二次（拿真卡片指出）：「问题小于3个，每个问题之间空一行；
 *                  问题大于等于3个，就输出的审查报告每个问题之间空一行，
 *                  **输出的卡片逐条问题是不空行的**」
 *
 *   PRD 的逐字形状（回源飞书 PRD wiki rev 36 ＋ 本地 `kb/.work/prd.md`，两份一致；`␤` = 空行）：
 *
 *   **<3（§5.3.2 逐条）**
 *       【审查结论：REVIEW】共发现 2 处需人工确认。
 *       ␤
 *       1.【合规-医疗宣称】……
 *         原因：…… ／ 依据：……
 *       ␤                                  ← **每条之间空一行**
 *       2.【消费者安全-使用姿势】……
 *       ␤
 *       建议转 @法务 @医学顾问 复核。
 *
 *   **≥3（§5.3.2 汇总）**
 *       【审查结论：REVIEW】共发现 5 处需人工确认。
 *       ␤
 *       · 合规类问题：3 个                  ← 这三行
 *       · 消费者安全类问题：1 个             ← **紧挨着**
 *       · 措辞表达类问题：1 个              ← 中间**没有**空行
 *       ␤
 *       → 完整清单：…（2026-10-19 起为此文案，为 PRD §17 字数让路）
 *       ␤
 *       建议转 @法务 @医学顾问 复核。
 *
 *   ⇒ 结论行后一个空行 · 链接前一个空行 · 动作行前一个空行（两种形状都一样）；
 *     **条目之间**：<3 空一行、**≥3 不空**。
 *
 *   ★ 为什么 ≥3 在卡片上也不空行：卡片上那一组（标题 `逐条问题`）装的**就是**这段汇总
 *     （`envelope.applyVerdictLine` → `blockRows(verdict.block)`），所以「卡片逐条问题不空行」
 *     与「≥3 汇总行不空行」是**同一件事**。报告那一侧另有 `merged_report.mjs` 的 `L.push('')`
 *     逐条空行（不归本判据管，也不许被本判据的改动碰）。
 *
 * ## 反向对照
 *
 *   R1 喂**改前的坏形状**（结论行后 0 个空行、动作行前 3 个）⇒ 必须判得出；
 *   R2 喂**汇总行被空开**的形状（＝我第一版那个错）⇒ ②b 必须红。
 */
import { renderMerged, mergeFindings, evidenceBlock } from './dual_track.mjs';

let pass = 0, fail = 0;
const bad = [];
const ok = (m) => { pass++; console.log(`  ✅ ${m}`); };
const no = (m, w) => { fail++; bad.push(`${m} —— ${w}`); console.log(`  ❌ ${m}\n       ${w}`); };
const head = (t) => console.log(`\n${t}`);

const F = (category, location, taxonomyCategory = null) => ({
  location, category, severity: 'REVIEW', source: 'kb', kb: { basisLine: '《库》第 1 条' },
  // ★★ 2026-10-19（Owner：「所属类别/所属子类」统一到 A3 12 类）：汇总轴 = A3
  //   （`taxonomyCategory`）⇒ 夹具第三格传 **A3 类名**（不带就全落「未归类」一桶，
  //   量不到「每类一行」，实测 ②b/③b 当场变红 —— 那不是判据错，是夹具没跟上口径）。
  ...(taxonomyCategory ? { taxonomyCategory } : {}),
  // ★★ 2026-10-19（Owner：「问题数量≥3 时要有分类汇总 `· 合规类：X 个 · 消费者安全类：X 个
  //   · 措辞类：X 个`……卡片所有的回复必须跟 PRD 5.3 对齐」）：
  //   **汇总行的轴从 11 类回退到 PRD 四维**（11 类在模型侧条目上盖不上章，实测真单退化成常数桶）。
  //   夹具因此带 `riskCategory`（= 引擎盖过章的 `risk_category`；真 `risk_items` 都带这一格）。
  //   不带也能跑 —— `category` 落在四维里就按它算，落在四维外则如实进「未标注维度」桶。
  ...(taxonomyCategory ? { taxonomyCategory } : {}),
});
// ★ 第三格是 **A3 所属类别**（2026-10-19 起；之前是 11 类 / 四维）—— 夹具别漏解构。
const mk = (...pairs) => mergeFindings(pairs.map(([c, l, t]) => F(c, l, t)), []).items;

/** 两个锚点之间的**空行数**：1 = 恰好一个空行；0 = 紧挨着。`-1` = 没匹配上（本身就是缺陷）。 */
const blanks = (text, re) => {
  const m = re.exec(text);
  return m ? (m[0].match(/\n/g) || []).length - 1 : -1;
};

// 三桶维度（3 + 1 + 1）—— 用来验「汇总行只有一行」＋「一行内多段」这条 PRD §5.3.4 规则
// ★ 2026-10-19：第三格是**维度**（`risk_category` 的受控取值），不是 11 类名 ——
//   11 类名不是四维 ⇒ `dimensionOf()` 返回 null ⇒ 5 条会全落「未标注维度」一桶，
//   那样 ②b/②b3 就量不到「一行多段」这条形状（实测当场变红，是夹具没跟上口径）。
const FIVE = () => mk(['合规', 'a', '合规与受监管宣称'], ['合规', 'b', '合规与受监管宣称'],
  ['合规', 'c', '合规与受监管宣称'], ['消费者安全', 'd', '产品安全与高危使用场景'],
  ['措辞表达', 'e', '母婴知识内容准确性']);
const TWO = () => mk(['合规-医疗宣称', '第1行'], ['消费者安全', '第2行']);

/* ─────────── ① <3 逐条：**每条之间空一行** ─────────── */
head('① <3 逐条 · 结论行 ␤ 每条 ␤ 动作行（条目之间**空一行**）');
{
  const b = renderMerged(TWO(), { state: 'REVIEW' }).block;
  const a = blanks(b, /。\n+1\.【/);
  if (a !== 1) no('①a 结论行后恰好一个空行', `实际 ${a} 个`); else ok('①a 结论行后恰好一个空行');
  // ★ 2026-10-19：原来按「上一条的结尾字符」匹配（`行\n+2.【|）\n+2.【|。\n+2.【`），
  //   而卡面「建议」压到 ≤30 字后结尾变成 `…` ⇒ 判据假红（结构其实没变）。
  //   改成**只看条与条之间的空行**，不依赖上一格的末字符。
  const c = blanks(b, /\n+2\.【/);
  if (c !== 1) no('①b **条目之间空一行**（<3 的规则）', `实际 ${c} 个`); else ok('①b 条目之间恰好一个空行');
  const d = blanks(b, /\n+建议转/);
  if (d !== 1) no('①c 动作行前恰好一个空行', `实际 ${d} 个`); else ok('①c 动作行前恰好一个空行');
  if (/\n\n\n/.test(b)) no('①d 全篇没有连续两个空行', '出现了 \\n\\n\\n');
  else ok('①d 全篇没有连续两个空行');
}

/* ─────────── ② ≥3 汇总：**汇总行之间不空行** ─────────── */
head('② ≥3 汇总 · 汇总行**紧挨着**（card 上那一组「逐条问题」就是它）');
{
  const b = renderMerged(FIVE(), { state: 'REVIEW', reportUrlOverride: 'https://feishu.cn/review/x' }).block;
  // ★ 2026-10-15 修判据（**这条在本次改动之前就是红的**，与链接位置那次改动无关）：
  //   原判据写死 `/。\n+·/` —— 它假定结论行之后**紧接**汇总行。而 2026-10-15 Owner 给的逐字格式
  //   在两者之间加了 `逐条问题` 这一行（`dual_track.renderMerged` 的 `bodyText`）⇒
  //   正则匹配不上 ⇒ `blanks()` 回 `-1` ⇒ 判成「不是恰好一个空行」。
  //   判据的**本意**是「结论行之后恰好一个空行」，与它后面第一行是什么无关
  //   ⇒ 改成不绑形状的写法（绑死形状的判据在形状一变就误红，误红比没有判据更坏）。
  const a = blanks(b, /。\n+[^\n]/);
  if (a !== 1) no('②a 结论行后恰好一个空行', `实际 ${a} 个`); else ok('②a 结论行后恰好一个空行');
  // ★★ 2026-10-19（Owner：「问题数量≥3 时要有分类汇总 `· 合规类：X 个 · 消费者安全类：X 个
  //   · 措辞类：X 个`……卡片所有的回复必须跟 PRD 5.3 对齐」）——
  //   **汇总行从「每类一行」改成 PRD §5.3.4 的「一行装完」**。
  //   于是旧判据 `个\n+·`（量行与行之间空不空）**恒为 -1** ⇒ 恒红，比没有判据更坏。
  //   改钉三条，意思不变、形状对齐 PRD：
  //     ②b  汇总行**只有一行**（多行 = 又回到每类一行）
  //     ②b2 「逐条问题」与汇总行之间**不空行**（Owner 2026-10-14 那条原意）
  //     ②b3 **反向对照**：把一行拆成两行 ⇒ ②b 必须红（证明它不是恒绿）
  const sumLines = (t) => String(t).split('\n').filter((l) => /^· /.test(l));
  // ★★ 2026-10-19 第三次（Owner 逐字：「按照下面的格式优化，**目前是写的一行**」）：
  //   **每类一行**、写法 `· <维度>类问题：N 个`；行间**不空行**。
  const sumShape = /^· (?:[^·\n，]+类问题|未归类问题)：\d+ 个$/;
  const sl = sumLines(b);
  if (sl.length < 3) no('②b 汇总行**每类一行**（3 桶 ⇒ 3 行）', JSON.stringify(sl));
  else if (!sl.every((l) => sumShape.test(l))) no('②b 每行形状 = `· <维度>类问题：N 个`', JSON.stringify(sl));
  else ok(`②b 汇总行每类一行且形状照 Owner 给的格式：${sl[0]} …（共 ${sl.length} 行）`);
  const c2 = blanks(b, /逐条问题\n+·/);
  if (c2 !== 0) no('②b2 「逐条问题」与汇总行之间不许空行', `实际 ${c2} 个`);
  else ok('②b2 「逐条问题」与汇总行紧挨着（不空行）');
  // 行与行之间也不许空行（Owner 2026-10-14）
  const spaced = (b.match(/个\n\n· /g) || []).length;
  if (spaced !== 0) no('②b2b 汇总行之间不许空行', `发现 ${spaced} 处`);
  else ok('②b2b 汇总行之间不空行（紧挨着）');
  // 反向对照：缩成一行 ⇒ ②b 必须红（那个版本就是 Owner 说的「目前是写的一行」）
  const ONE = '· 合规与受监管宣称类问题：1 个 · 母婴知识内容准确性类问题：1 个';
  if (sumShape.test(ONE)) no('②b3 反向对照：缩成一行必须判得出', '一行多段竟被当成合规形状');
  else ok('②b3 反向对照：缩成一行判得出来（②b 咬得住上一版）');
  const d = blanks(b, /个\n+→ 完整清单：/);
  if (d !== 1) no('②c 链接前恰好一个空行', `实际 ${d} 个`); else ok('②c 链接前恰好一个空行');
  const e = blanks(b, /\n+建议转/);
  if (e !== 1) no('②d 动作行前恰好一个空行', `实际 ${e} 个`); else ok('②d 动作行前恰好一个空行');
  if (/\n\n\n/.test(b)) no('②e 全篇没有连续两个空行', '出现了 \\n\\n\\n');
  else ok('②e 全篇没有连续两个空行');

  // ★★ ②f（2026-10-16，FIX-033）：**「逐条问题」这一行必须留在块里**。
  //   修卡面上那个「两个逐条问题」时，最容易顺手做错的事就是把这行从 `renderMerged` 删掉。
  //   它**剥不得** —— 块是**多个载体的同一份源**：
  //     · 表行「问题分类汇总」（`agent.mjs` 直接给 `dual.rendered.block`）；
  //     · 报告（`merged_report.mjs`）。
  //   这两个载体**没有组标题**，那一行在它们那里正是 Owner 2026-10-15 给的逐字格式件
  //   （`【审查结论：BLOCK】…` ␤ `逐条问题` ␤ `· XX类问题：N 个`）。
  //   去重只许发生在**有组标题的那一个载体**上（`envelope.blockRows(block, title)`）。
  if (!/^逐条问题$/m.test(b)) {
    no('②f ≥3 的块里必须有「逐条问题」这一行（它是表行与报告的格式件）', b.slice(0, 160));
  } else ok('②f ≥3 的块里「逐条问题」这一行仍在（卡面去重不改块本身）');
  // 反向对照：**1–2 条那条路不许加这一行** —— 那一支是逐条展开，加了就是凭空多一个小标题
  const b2 = renderMerged(TWO(), { state: 'REVIEW' }).block;
  if (/^逐条问题$/m.test(b2)) no('②f2 反向对照：<3 那条路不加「逐条问题」', b2.slice(0, 160));
  else ok('②f2 反向对照：<3 那条路不加「逐条问题」');
}

/* ─────────── ③ 「链答案 → 卡面」整跳 ─────────── */
head('③ 整跳 · 形状过信封后落到卡面上仍对（卡片上那一组就是块本身）');
{
  const { deriveVerdictLine } = await import('./prd53.mjs');
  const { applyVerdictLine } = await import('../reply-cards/envelope.mjs');
  const { build, renderText } = await import('../reply-cards/index.mjs');

  // ★ 先说清这一跳的**真实路径**（我第一版断言写错过，记在这里）：
  //   `blockSlotOf('query-answer') === 'reasoning'`（**先判 reasoning**）⇒ 块整段进
  //   `data.reasoning` 这个**槽**，**不建 groups**。`groups` 只给**没有 reasoning 字段**的
  //   卡型（`evidence` 等）。所以这里断言的落点是 `reasoning`，不是「逐条问题」那一组
  //   —— 群里那张 `query-answer` 卡上看到的正是 `reasoning` 渲染出来的正文。

  // ≥3：卡面正文里汇总行不许被空开
  const BLOCK5 = renderMerged(FIVE(), { state: 'REVIEW', reportUrlOverride: 'https://feishu.cn/review/x' }).block;
  const r5 = applyVerdictLine('query-answer', { title: 't', verdict: 'v' },
    deriveVerdictLine({ replyText: BLOCK5 }));
  const body5 = String(r5.data.reasoning ?? '');
  if (!body5) no('③a ≥3：块搬进了卡片正文', 'reasoning 是空的');
  else {
    // ★★ 2026-10-19：汇总行现在**只有一行**（PRD §5.3.4 形状）⇒ 旧判据 `个\n+·` 恒 -1。
    //   改钉：卡面正文里汇总行**一行**、「逐条问题」与它之间**不空行**。
    const sum5 = String(body5).split('\n').filter((l) => /^· /.test(l));
    if (sum5.length < 3) no('③b ≥3：卡片正文里汇总行**每类一行**', JSON.stringify(sum5));
    else ok(`③b ≥3：卡片正文里汇总行每类一行（共 ${sum5.length} 行，首行：${sum5[0]}）`);
    const cb2 = blanks(body5, /逐条问题\n+·/);
    if (cb2 !== 0) no('③b3 ≥3：卡面「逐条问题」与汇总行之间不空行', `实际 ${cb2} 个`);
    else ok('③b3 ≥3：卡面「逐条问题」与汇总行紧挨着');
    // ★ 2026-10-17（汇总行改 11 类）：桶名形状从「· XX类问题：N 个」变成「· <维度>类：N 个」，
    //   判据只认**形状**（`· 名称类：N 个`），不绑死名称 —— 绑死的判据在口径一变就误红。
    if (!/· .+类问题：\s*\d+ 个/.test(body5)) no('③b2 正文里装的是汇总行', body5.slice(0, 120));
    else ok('③b2 正文里装的确是汇总行');
  }

  // <3：卡面正文里条目之间要空一行
  const BLOCK2 = renderMerged(TWO(), { state: 'REVIEW' }).block;
  const r2 = applyVerdictLine('query-answer', { title: 't', verdict: 'v' },
    deriveVerdictLine({ replyText: BLOCK2 }));
  const body2 = String(r2.data.reasoning ?? '');
  // ⚠️ 锚点必须落在**逐条首行真正的行尾**上。实测那一行是：
  //     `1.【合规-医疗宣称】第1行  —— **非权威候选线索 · 不构成依据**（无条款号，回不了源）`
  //   ⇒ 行尾是 `）`，**不是** `。`、也不是 `】`。第一版两种都写过，各得 -1（红得没道理）。
  const a = blanks(body2, /。\n+1\.【/);
  // ★ 2026-10-19：建议压到 ≤30 字后行尾是 `…` ⇒ 不再按末字符匹配，只看条间空行
  const b2 = blanks(body2, /\n+2\.【/);
  if (a !== 1 || b2 !== 1) no('③c <3：卡片正文里条目之间仍空一行', `结论后 ${a} 个、条目间 ${b2} 个`);
  else ok('③c <3：卡片正文里条目之间仍空一行');
  // 卡面渲染出来也是同一份（渲染器不改换行）
  const card2 = renderText(build('query-answer', r2.data));
  if (blanks(card2, /\n+2\.【/) !== 1) no('③d 渲染出来的卡面同样保留空行', card2.slice(0, 300));
  else ok('③d 渲染出来的卡面同样保留空行');
}

/* ─────────── ④ 查证笔记的逐条依据 ─────────── */
head('④ 查证笔记 · 逐条依据（同一张卡里的另一种编号列表）');
{
  const e = evidenceBlock([
    { category: '合规', location: '第1行', reason: 'r1', source: 'kb', kb: { basisLine: '《库》1' } },
    { category: '合规', location: '第2行', reason: 'r2', source: 'kb', kb: { basisLine: '《库》2' } },
  ]);
  // ⚠️ 锚点落在**行尾**：这一行末尾是依据文本（`《库》1`），不是 `条`（第一版红得没道理）
  const a = blanks(e, /】[^\n]*\n+2\.【/);
  if (a !== 1) no('④a 逐条依据之间恰好一个空行', `实际 ${a} 个\n${e}`);
  else ok('④a 逐条依据之间恰好一个空行');
  if (evidenceBlock([]) !== '') no('④b 反向对照：没依据时不许凭空造', JSON.stringify(evidenceBlock([])));
  else ok('④b 反向对照：没依据时返回空串（不造）');
}

/* ─────────── ⑤ 反向对照 ─────────── */
head('⑤ 反向对照 · 喂坏形状必须红（证明上面不是恒绿）');
{
  // ⑤a 改前那一版：结论行直接接正文（0 个空行）、动作行前 3 个
  const OLD = '【审查结论：REVIEW】共发现 2 处需人工确认。\n1.【合规】a\n\n2.【安全】b\n\n\n建议转 @法务 复核。';
  const a = blanks(OLD, /。\n+1\.【/);
  if (a === 1) no('⑤a 改前的坏形状必须判得出', '旧形状竟算作 1 个空行');
  else ok(`⑤a 改前形状判得出来（结论行后 ${a} 个 ≠ 1）`);

  // ⑤b ★ 汇总行被空开（**我第一版就是这个错**）⇒ ②b 那条判据必须红
  const SUMMARY_SPACED = '【审查结论：REVIEW】共发现 5 处需人工确认。\n\n· 合规类问题：3 个\n\n· 安全类问题：1 个\n\n→ 查看…\n\n建议转 @法务 复核。';
  const c = blanks(SUMMARY_SPACED, /个\n+·/);
  if (c === 0) no('⑤b 汇总行被空开必须判得出', '空开了却算作 0');
  else ok(`⑤b 汇总行被空开判得出来（${c} 个 ≠ 0）—— ②b 咬得住我第一版那个错`);
}


// ═══ PRD §5.3.2 四态（2026-10-19 Owner 同步 §5.3.2/§17）：SUGGEST 必须被认，非法态仍拒 ═══
//
// 为什么要这条：四态落地前，守衡 `prd53.mjs` 的 `LINE_RE` 只认三态 ——
// 知识库一旦输出 `【SUGGEST】…`，这里就判「没拿到结论」⇒ 进补发队列重跑、表行记「未判」。
// 这是 `prd-v1.3-alignment.yaml::changes[A]` 当初「不做四态」的第一条理由，现在先把它拆掉。
{
  const P = await import('./prd53.mjs');
  const sugLine = '【审查结论：SUGGEST】发现 1 处建议优化，不阻断发布：1.【措辞表达】正文第 2 段「超级好用」偏口语。建议：改为「高效便捷」。';
  const res = P.conforms(sugLine);
  if (!res.ok) no('②g SUGGEST 行没被认（PRD §5.3.2 四态）', res.why);
  else ok('②g SUGGEST 行按 §5.3.4 样张被认');
  // ★ 卡面那种写法（句号收尾、逐条在下一行）也必须认 —— 否则「自家产出不合自家判据」
  const cardForm = '【审查结论：SUGGEST】发现 3 处建议优化，不阻断发布。';
  if (!P.conforms(cardForm).ok) no('②g5 卡面那种 SUGGEST 行（句号收尾）没被认', P.conforms(cardForm).why);
  else ok('②g5 卡面那种 SUGGEST 行（句号收尾）也认');
  // 反向对照 ①：去掉「不阻断发布」⇒ 必须红（那句是 SUGGEST 与 REVIEW 的分界）
  const noHint = '【审查结论：SUGGEST】发现 1 处建议优化：1.【措辞表达】…';
  if (P.conforms(noHint).ok) no('②g2 反向对照：SUGGEST 少了「不阻断发布」仍判合规', noHint);
  else ok('②g2 反向对照：SUGGEST 少了「不阻断发布」判得出');
  // 反向对照 ②：自造态必须仍拒 —— 四态是**闭集**，不是"什么都认"
  if (P.conforms('【审查结论：FOO】发现 1 处…').ok) no('②g3 反向对照：自造态 FOO 竟通过');
  else ok('②g3 反向对照：自造态仍拒');
  // 反向对照 ③：`STATES` 里必须真的是四态（漏一个就回到三态）
  if (P.STATES.join('/') !== 'PASS/SUGGEST/REVIEW/BLOCK') no('②g4 STATES 不是四态', P.STATES.join('/'));
  else ok('②g4 STATES = PASS/SUGGEST/REVIEW/BLOCK');
}

/* ─────────── 汇总 ─────────── */
console.log(`\n${'═'.repeat(64)}`);
console.log(`通过 ${pass} 项 · 不通过 ${fail} 项`);
if (fail) {
  console.log('\n不通过明细：');
  for (const b of bad) console.log(`  · ${b}`);
  console.log('\n❌ 分段与 PRD §5.3 不符，别拿去发群。');
  process.exit(1);
}
console.log('✅ <3 条目之间空一行；≥3 汇总行紧挨着；结论行后/链接前/动作行前各一个空行。');
