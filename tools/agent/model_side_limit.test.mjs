/**
 * model_side_limit.test.mjs —— 「字数上限说在**源头**、超了会**重写一次**」的判据。
 *
 * ## 为什么这条必须有判据（Owner 2026-10-19：「原因是不是没讲完？」）
 *
 *   病灶链：提示词**只约束了建议 ≤30**，没约束描述/原因 ≤50
 *     ⇒ 模型写 65–80 字 ⇒ 渲染层按 50 硬切 ⇒ 卡上是「…而实际想表达的应是「只…」。
 *   **没有人报错**：截断是静默的（`clipToLimit` 只回一个字符串，调用点看不出截没截）。
 *
 *   修法有两半，缺一半都白做：
 *     ① 上限写进**提示词**（`SYSTEM` 的 4c2）—— 让它在源头就不超；
 *     ② 万一还超 ⇒ **重写一次**（带「第几条哪一格超了几字」的定向纠正）。
 *
 *   这一份判据盯的就是这两半：**没有它，两步都只是散文**。
 *
 * ## 四条边界（每条都有一个"变坏就会红"的反向对照）
 *
 *   ① 超限 ⇒ 恰好重试**一次**，且纠正里点得出是第几条、哪一格、超几字；
 *   ② 没超 ⇒ **一次都不多调**（不许为了保险每次都重写，那是拿延迟换安心）；
 *   ③ 重试的输出**坏掉**（坏 JSON / 被截断）⇒ **保留第一版**，不许越修越坏；
 *   ④ 重试**共用**同一次预算（截断重试过就不再为字数重试）—— 一单最多两次调用。
 *
 * 跑法：`node agent/model_side_limit.test.mjs`
 */
import test from 'node:test';
import assert from 'node:assert';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import { reviewModelSide, buildPrompt, overLimitOf, SYSTEM } from './model_side.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));

/** 一条**合规**的 finding（描述 12 字 / 原因 10 字 / 建议 8 字）。 */
const OK_ITEM = {
  location: '正文第 1 段', category: '合规', severity: 'REVIEW', nature: '强制',
  description: '标题写了「100%」', reason: '绝对化用语无据支撑', excerpt: '100%',
  suggestion: '删去 100%', taxonomy_category: '合规与受监管宣称', taxonomy_subcategory: null,
  source: null, source_url: null, source_name: null,
};

/** 一条**原因超限**的 finding（80 字 > 50）。 */
const OVER_ITEM = { ...OK_ITEM, reason: '消费者可能误解为全部部件都不能水洗，影响对清洁方式和使用卫生的判断，而实际想表达的应是只有五个可拆部件需要洗。' };

const jsonOf = (arr) => JSON.stringify(arr);

test('① 超字数 ⇒ 重试一次，且纠正点得出「第几条 / 哪一格 / 超几字」', async () => {
  const calls = [];
  const ask = async (prompt) => {
    calls.push(prompt);
    return calls.length === 1 ? jsonOf([OVER_ITEM]) : jsonOf([OK_ITEM]);
  };
  const r = await reviewModelSide({ readings: '素材：Only the detachable parts are washable', ask });
  assert.equal(calls.length, 2, `应恰好调用两次，实际 ${calls.length}`);
  // 纠正必须**定向**：说得出第几条、哪一格 —— 泛泛一句「太长了」它不知道改哪
  assert.match(calls[1], /超字数/, '第二次调用没带字数纠正');
  assert.match(calls[1], /第 1 条/, '纠正里没点名是第几条');
  assert.match(calls[1], /原因/, '纠正里没点名是哪个字段');
  assert.match(calls[1], /50/, '纠正里没给上限数字');
  // 最终用的是**第二版**（合规那条）
  assert.equal(r.ok, true);
  assert.equal(r.findings.length, 1);
  assert.equal(r.findings[0].reason, OK_ITEM.reason, '重试之后仍用第一版（等于白重试）');
});

test('② 反向对照：没超字数 ⇒ **一次都不多调**（不许拿延迟换安心）', async () => {
  const calls = [];
  const ask = async (prompt) => { calls.push(prompt); return jsonOf([OK_ITEM]); };
  const r = await reviewModelSide({ readings: '素材', ask });
  assert.equal(calls.length, 1, `合规的输入不该重试，实际调用 ${calls.length} 次`);
  assert.equal(r.ok, true);
  assert.equal(r.findings.length, 1);
});

test('③ 反向对照：重试输出坏掉 ⇒ **保留第一版**（不许越修越坏）', async () => {
  const calls = [];
  const ask = async (prompt) => {
    calls.push(prompt);
    // 第一版：超字数但**内容有效**；第二版：写坏了（不是 JSON）
    return calls.length === 1 ? jsonOf([OVER_ITEM]) : '这一版我写成散文了，没有数组。';
  };
  const r = await reviewModelSide({ readings: '素材', ask });
  assert.equal(calls.length, 2);
  assert.equal(r.ok, true, '重试写坏之后，第一版也被丢了');
  assert.equal(r.findings.length, 1, '第一版条目丢了 —— 那是「修字数把结果修没了」');
  assert.equal(r.findings[0].reason, OVER_ITEM.reason, '保留的不是第一版');
});

test('④ 反向对照：截断重试已经用掉预算 ⇒ 不再为字数重试（一单最多两次调用）', async () => {
  const calls = [];
  const ask = async (prompt) => {
    calls.push(prompt);
    // 第一次：被截断（有 `[` 无 `]`）⇒ 触发截断重试；第二次：合法但超字数
    return calls.length === 1 ? `[${JSON.stringify(OVER_ITEM)}` : jsonOf([OVER_ITEM]);
  };
  const r = await reviewModelSide({ readings: '素材', ask });
  assert.equal(calls.length, 2, `一单最多两次调用（截断一次 + 字数一次就超了），实际 ${calls.length}`);
  assert.equal(r.ok, true);
});

test('⑤ 上限确实写进了**系统提示词**（源头，不是只写在渲染层）', () => {
  const sys = Array.isArray(SYSTEM) ? SYSTEM.join('\n') : String(SYSTEM);
  assert.match(sys, /4c2/, '提示词里没有 4c2 那一条');
  assert.match(sys, /≤50 字/, '提示词没写描述/原因 ≤50 字 —— 那源头就还在写 80 字');
  assert.match(sys, /≤30 字/, '建议 ≤30 字那条不许丢（原有约束）');
  // ⚠️ 反向对照：不许出现「写不下就用省略号」这种把截断合法化的说法
  assert.ok(!/写不下.{0,6}省略号/.test(sys), '提示词里出现了「写不下就用省略号」——那等于允许截断');
});

test('⑥ overLimitOf 认得出超限，且**不误伤**合规条目', () => {
  const rows = overLimitOf([OK_ITEM, OVER_ITEM]);
  assert.equal(rows.length, 1, `应只报第 2 条，实际 ${JSON.stringify(rows)}`);
  assert.equal(rows[0].index, 2);
  assert.ok(rows[0].bad.some((b) => /原因/.test(b.label)), '报的不是「原因」那一格');
  // 反向对照：全合规 ⇒ 0 条（否则每次都会重试）
  assert.equal(overLimitOf([OK_ITEM]).length, 0);
});

test('⑦ buildPrompt 把纠正**追加在输入末尾**（系统提示词保持稳定前缀）', () => {
  const a = buildPrompt({ readings: 'R', question: 'Q' });
  const b = buildPrompt({ readings: 'R', question: 'Q', fixNote: '【上一版超字数了】' });
  assert.ok(!a.includes('超字数'), '不带 fixNote 时不该出现纠正');
  assert.ok(b.includes('超字数'), 'fixNote 没进提示词');
  assert.ok(b.startsWith(a), '纠正不是追加在末尾（会破坏系统前缀的缓存友好性）');
});

test('⑧ 这条判据自身不是恒真：把 overLimitOf 的字段映射改错就必须红', () => {
  // 用 **advice** 字段超限、description/reason 合规的条目：证明映射真的接了 suggestion
  const bad = { ...OK_ITEM, suggestion: '改'.repeat(60) };
  const rows = overLimitOf([bad]);
  assert.equal(rows.length, 1, '建议超限没被认出来（字段映射漏了 suggestion）');
  assert.ok(rows[0].bad.some((b) => /修改建议/.test(b.label)), '报的不是「修改建议」那一格');
  // 源文件里这一跳必须真的读 `suggestion`（有人改成别的字段名 ⇒ 这里红）
  const src = fs.readFileSync(path.join(HERE, 'model_side.mjs'), 'utf8');
  assert.match(src, /advice:\s*f\?\.suggestion/, 'overLimitOf 不再把 suggestion 映射到「修改建议」');
});

test('⑨ 超时预算 ⇒ **一次都不多调**（Owner：修复不能影响工作流）', async () => {
  // ★ 2026-10-19（Owner 的硬约束：「你的所有修复，不能影响工作流」）——
  //   重试是**又一轮 7–10 s 的 LLM 调用**，而模型侧与送审链并行、它晚到就拖后落表与发卡。
  //   预算用尽（这里注入 -1，等价于「第一轮已经太久」）⇒ 宁可让卡面压一句，
  //   也不拿业务在等的时间去换文案完整度。
  const calls = [];
  const ask = async (prompt) => { calls.push(prompt); return jsonOf([OVER_ITEM]); };
  const r = await reviewModelSide({ readings: '素材', ask, retryBudgetMs: -1 });
  assert.equal(calls.length, 1, `超预算时不许重试，实际调用了 ${calls.length} 次`);
  assert.equal(r.ok, true, '跳过重试不许把结果弄丢');
  assert.equal(r.findings.length, 1);
  // 反向对照：同一份输入、预算充足 ⇒ 必须**会**重试（证明跳过是预算造成的，不是逻辑坏了）
  const calls2 = [];
  const ask2 = async (prompt) => {
    calls2.push(prompt);
    return calls2.length === 1 ? jsonOf([OVER_ITEM]) : jsonOf([OK_ITEM]);
  };
  await reviewModelSide({ readings: '素材', ask: ask2, retryBudgetMs: 60000 });
  assert.equal(calls2.length, 2, '预算充足时反而没重试 —— 判据被改坏了');
});
