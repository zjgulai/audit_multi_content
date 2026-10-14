#!/usr/bin/env node
/**
 * prd53_format.test.mjs —— **PRD §5.3 的分段（空行）判据**
 *
 * ## 为什么单开一个文件（Owner 2026-10-14）
 *
 *   Owner 原话：「审核结论中 1，2...每条之间需要空一行的（不管是小于3条飞书侧输出的，
 *   还是大于等于3条输出审查报告的），都要跟 prd 对齐」。
 *
 *   PRD §5.3.2 / §5.3.3 的逐字形状（回源飞书 PRD wiki rev 36 ＋ 本地 `kb/.work/prd.md`，
 *   两份一致；`␤` = 空行）：
 *
 *       【审查结论：REVIEW】共发现 2 处需人工确认。
 *       ␤
 *       1.【合规-医疗宣称】……
 *         原因：…… ／ 依据：……
 *       ␤
 *       2.【消费者安全-使用姿势】……
 *       ␤
 *       建议转 @法务 @医学顾问 复核。
 *
 *   ≥3 的汇总形状同时序、同样分段（`· <大类>类问题：N 个` 每行之间也空一行）。
 *
 *   ⇒ **结论行后一个空行 · 条目/汇总行之间一个空行 · 动作行之前一个空行**。
 *
 *   ⚠️ 判据要钉的**不只是「有没有空行」，还有「是不是只有一个」** ——
 *     改前实测的坏形状是：2 条那一路「结论行后 0 个、动作行前 3 个」，
 *     而 ≥3 那一路「链接与动作行之间 2 个」。只判「有没有」会漏掉一半。
 *
 * ## 反向对照
 *
 *   R1 把拼装里的 `\n\n` 退回 `\n`（模拟改前那一版）⇒ 断言必须红；
 *   R2 故意多加一个空行 ⇒ 「只有一个」那条必须红。
 *
 * 用法：`node tools/agent/prd53_format.test.mjs`
 */
import {
  renderMerged, mergeFindings, evidenceBlock, categorySummary,
} from './dual_track.mjs';

let pass = 0, fail = 0;
const bad = [];
const ok = (m) => { pass++; console.log(`  ✅ ${m}`); };
const no = (m, w) => { fail++; bad.push(`${m} —— ${w}`); console.log(`  ❌ ${m}\n       ${w}`); };
const head = (t) => console.log(`\n${t}`);

const F = (category, location) => ({
  location, category, severity: 'REVIEW', source: 'kb', kb: { basisLine: '《库》第 1 条' },
});
const mk = (...pairs) => mergeFindings(pairs.map(([c, l]) => F(c, l)), []).items;

/** 空行数（连续 `\n` 的个数 − 1）：1 = 恰好一个空行。 */
const blanksBetween = (text, re) => {
  const m = re.exec(text);
  return m ? (m[0].match(/\n/g) || []).length - 1 : -1;
};

/* ─────────── ① <3 逐条（卡面 block）─────────── */
head('① <3 逐条 · 结论行 ␤ 每条 ␤ 动作行（各**恰好一个**空行）');
{
  const b = renderMerged(mk(['合规-医疗宣称', '第1行'], ['消费者安全', '第2行']), { state: 'REVIEW' }).block;

  // ①a 结论行之后一个空行
  const a = blanksBetween(b, /。\n+1\.【/);
  if (a !== 1) no('①a 结论行后恰好一个空行', `实际 ${a} 个`); else ok('①a 结论行后恰好一个空行');
  // ①b 两条之间一个空行
  const c = blanksBetween(b, /行\n+2\.【|）\n+2\.【|。\n+2\.【/);
  if (c !== 1) no('①b 第 1 条与第 2 条之间恰好一个空行', `实际 ${c} 个`); else ok('①b 条目之间恰好一个空行');
  // ①c 动作行之前一个空行
  const d = blanksBetween(b, /\n+建议转/);
  if (d !== 1) no('①c 动作行前恰好一个空行', `实际 ${d} 个`); else ok('①c 动作行前恰好一个空行');
  // ①d 全篇**没有**连续两个空行（改前这里正是 3 个）
  if (/\n\n\n/.test(b)) no('①d 全篇没有连续两个空行', '出现了 \\n\\n\\n');
  else ok('①d 全篇没有连续两个空行（改前动作行前是 3 个）');
}

/* ─────────── ② ≥3 汇总（卡面 block）─────────── */
head('② ≥3 汇总 · 结论行 ␤ 每个汇总行 ␤ 链接 ␤ 动作行');
{
  const b = renderMerged(mk(['合规', 'a'], ['合规', 'b'], ['合规', 'c'],
    ['消费者安全', 'd'], ['措辞表达', 'e']),
  { state: 'REVIEW', reportUrlOverride: 'https://feishu.cn/review/x' }).block;

  // ②a 结论行后一个空行（下一行是 `·`）
  const a = blanksBetween(b, /。\n+·/);
  if (a !== 1) no('②a 结论行后恰好一个空行', `实际 ${a} 个`); else ok('②a 结论行后恰好一个空行');
  // ②b **汇总行之间**一个空行（PRD 的 `· …` 三行之间也各空一行）
  const c = blanksBetween(b, /个\n+·/);
  if (c !== 1) no('②b 汇总行之间恰好一个空行', `实际 ${c} 个`); else ok('②b 汇总行之间恰好一个空行');
  // ②c 链接前一个空行、动作行前一个空行
  const d = blanksBetween(b, /个\n+→ 查看/);
  if (d !== 1) no('②c 链接前恰好一个空行', `实际 ${d} 个`); else ok('②c 链接前恰好一个空行');
  const e = blanksBetween(b, /\n+建议转/);
  if (e !== 1) no('②d 动作行前恰好一个空行', `实际 ${e} 个`); else ok('②d 动作行前恰好一个空行');
  if (/\n\n\n/.test(b)) no('②e 全篇没有连续两个空行', '出现了 \\n\\n\\n');
  else ok('②e 全篇没有连续两个空行（改前链接与动作行之间是 2 个）');
}

/* ─────────── ③ 「链答案 → 卡面」整跳（真形状，不只手拼 block）─────────── */
head('③ 整跳 · 真形状的链答案过信封后，卡面上的分段仍对');
{
  const { deriveVerdictLine } = await import('./prd53.mjs');
  const { applyVerdictLine } = await import('../reply-cards/envelope.mjs');
  const { build, renderText } = await import('../reply-cards/index.js').catch(() => import('../reply-cards/index.mjs'));

  const ANS = [
    '【审查结论：REVIEW】共发现 2 处需人工确认。', '',
    '1.【合规-医疗宣称】视频 00:12 字幕涉嫌医疗宣称。', '  原因：不得出现治疗表述。', '',
    '2.【消费者安全-使用姿势】图片 1 姿势可能误导。', '  原因：姿势可能误导消费者。', '',
    '建议转 @法务（未配置） @医学顾问（未配置） 复核。',
  ].join('\n');
  const r = applyVerdictLine('query-answer', { title: 't', verdict: 'v' },
    deriveVerdictLine({ replyText: ANS }));
  const card = renderText(build('query-answer', r.data));
  // 卡面走的是 `reasoning` 槽：块整段搬进去，所以分段随块
  const a = blanksBetween(card, /。\n+1\.【/);
  if (a !== 1) no('③a 卡面：结论行后恰好一个空行', `实际 ${a} 个\n${card.slice(0, 400)}`);
  else ok('③a 卡面：结论行后恰好一个空行');
  const b2 = blanksBetween(card, /。\n+2\.【/);
  if (b2 !== 1) no('③b 卡面：条目之间恰好一个空行', `实际 ${b2} 个`);
  else ok('③b 卡面：条目之间恰好一个空行');
  const c2 = blanksBetween(card, /\n+建议转/);
  if (c2 !== 1) no('③c 卡面：动作行前恰好一个空行', `实际 ${c2} 个`);
  else ok('③c 卡面：动作行前恰好一个空行');
}

/* ─────────── ④ 顺带：其他编号列表的分段 ─────────── */
head('④ 其他编号列表 · 查证笔记的逐条依据也空开');
{
  const e = evidenceBlock([
    { category: '合规', location: '第1行', reason: 'r1', source: 'kb', kb: { basisLine: '《库》1' } },
    { category: '合规', location: '第2行', reason: 'r2', source: 'kb', kb: { basisLine: '《库》2' } },
  ]);
  // ⚠️ 锚点要落在**行尾**：这一行的最后一个字符是依据文本（`《库》1`），不是 `条`。
  //   第一版写成 /条\n+2\.【/ ⇒ 实际得到 -1（没匹配上）而**红得没道理**。
  const a = blanksBetween(e, /】[^\n]*\n+2\.【/);
  if (a !== 1) no('④a 逐条依据之间恰好一个空行', `实际 ${a} 个\n${e}`);
  else ok('④a 逐条依据之间恰好一个空行');
  // 空清单不许凭空多出东西（反向对照）
  if (evidenceBlock([]) !== '') no('④b 反向对照：没依据时不许凭空造', JSON.stringify(evidenceBlock([])));
  else ok('④b 反向对照：没依据时返回空串（不造）');
}

/* ─────────── ⑤ 反向对照 · 拆掉修复必须精确变红 ─────────── */
head('⑤ 反向对照 · 喂坏形状必须红（证明上面不是恒绿）');
{
  // ⑤a 改前那一版的拼装：结论行直接接正文（无空行）
  const OLD = '【审查结论：REVIEW】共发现 2 处需人工确认。\n1.【合规】a\n\n2.【安全】b\n\n\n建议转 @法务 复核。';
  const a = blanksBetween(OLD, /。\n+1\.【/);
  if (a === 1) no('⑤a 坏形状必须被 blank 数判出不符', '旧形状竟算作 1 个空行');
  else ok(`⑤a 改前形状判得出来（结论行后 ${a} 个空行 ≠ 1）`);
  if (!/\n\n\n/.test(OLD)) no('⑤b 坏形状必须带连续空行', '构造的坏样本里没有 \\n\\n\\n');
  else ok('⑤b 改前形状确实含连续两个空行（①d 不是空断言）');

  // ⑤c 「只有一个」这条咬得住：故意塞两个
  const TWO = '【审查结论：REVIEW】共发现 2 处需人工确认。\n\n\n1.【合规】a\n\n建议转 @法务 复核。';
  const c = blanksBetween(TWO, /。\n+1\.【/);
  if (c === 1) no('⑤c 「恰好一个」必须咬得住多出来的空行', '喂了两个空行却算作 1');
  else ok(`⑤c 多出来的空行会被判出（${c} ≠ 1）`);
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
console.log('✅ 结论行 ␤ 条目 ␤ 动作行 —— 各恰好一个空行，且没有连续空行。');
