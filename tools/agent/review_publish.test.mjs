/**
 * review_publish.test.mjs —— 「**每一个评审任务都必须落表**」这条硬规矩的自证（离线，不碰真飞书）
 *
 *   node tools/agent/review_publish.test.mjs
 *
 * ★ 为什么要有它（Owner 2026-10-05 现场定的两条里的一条）：
 *   那天送了四条素材，链跑完 3.5~17.9 分钟，**表里一行都没有** —— 因为链自己的发布条件是
 *   「有**三态结论**才发」，拒答（`NEEDS_INPUT`）整单被跳过。于是「审过了、结论是拒答」
 *   在盘上零痕迹。规矩改成「每一个评审任务都必须落表」，而**规矩要有执行点**
 *   （`AGENTS.md` §2.4）—— 执行点就是 `review_publish.mjs`，判据就是这一份。
 *
 * ★ 判据的形状（照 `lark_write.test.mjs` 那套）：
 *   每条都用**假客户端真调一次**来证，断的是「哪个接口被调了几次、写进去的是什么」，
 *   不是「源码里有没有那行 if」。每条「不该发生」都配一条**正向对照**。
 *
 * ★ 自证自身不许有副作用（§2.4.4）：留痕被 `SHOUHENG_LARK_WRITES` 指到临时文件，
 *   最后由 C1 断言**真留痕文件在这次运行前后没被动过**。
 */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import crypto from 'node:crypto';

const TMP = path.join(os.tmpdir(), `rp-test-${process.pid}-${Date.now()}.jsonl`);
process.env.SHOUHENG_LARK_WRITES = TMP;          // ★ 必须在 import 之前指走

const REAL_LEDGER = path.join(
  path.dirname(new URL(import.meta.url).pathname), '..', '..', 'PMO', 'logs', 'lark_writes.jsonl');
const realStat = () => { try { const s = fs.statSync(REAL_LEDGER); return `${s.size}:${s.mtimeMs}`; } catch { return 'absent'; } };
const REAL_BEFORE = realStat();

const lw = await import('./lark_write.mjs');
const rp = await import('./review_publish.mjs');

/** 4b 用的「两侧合并置信度」样本（形状 = `dual_track.mergedConfidence()` 的产物）。 */
const MERGED_CONF = Object.freeze({
  value: 0.85, band: 'confirm', kb_band: 'direct', model_band: 'confirm',
  basis: '两侧按 PRD §6.6 三档取更保守一侧：模型侧拉低（库侧 direct ／ 模型侧 confirm）',
});

let nPass = 0; const fails = [];
const ta = async (name, fn) => {
  try { await fn(); nPass += 1; console.log(`  ✅ ${name}`); }
  catch (e) { fails.push(name); console.log(`  ❌ ${name}\n       ${e?.message ?? e}`); }
};
const t = (name, fn) => {
  try { fn(); nPass += 1; console.log(`  ✅ ${name}`); }
  catch (e) { fails.push(name); console.log(`  ❌ ${name}\n       ${e?.message ?? e}`); }
};
const eq = (a, b, m) => {
  const A = JSON.stringify(a), B = JSON.stringify(b);
  if (A !== B) throw new Error(`${m ?? '不相等'}：期望 ${B}，实际 ${A}`);
};
const ok_ = (v, m) => { if (!v) throw new Error(m ?? '断言为假'); };

/* ─────────────────────────── 假飞书客户端 ─────────────────────────── */
const API_OK = (data) => () => ({ code: 0, msg: 'ok', data });

function mkClient(handlers = {}) {
  const calls = [];
  const mk = (key) => async (args) => {
    calls.push({ key, args });
    const h = handlers[key];
    if (typeof h === 'function') return h(args);
    if (h === undefined) throw new Error(`未打桩的调用：${key}`);
    return h;
  };
  const cl = {
    bitable: {
      appTable: { list: mk('appTable.list') },
      appTableField: { list: mk('appTableField.list') },
      appTableRecord: {
        list: mk('appTableRecord.list'),
        batchCreate: mk('appTableRecord.batchCreate'),
        batchGet: mk('appTableRecord.batchGet'),
        batchUpdate: mk('appTableRecord.batchUpdate'),
      },
    },
  };
  return { cl, calls, hit: (k) => calls.filter((c) => c.key === k).length };
}

/** 一次写入的完整桩：list 回给定行，create/update/get 回一个「照抄写入」的成功响应。 */
function install({ rows = [] } = {}) {
  const sent = { created: null, updated: null };
  const c = mkClient({
    'appTable.list': API_OK({ items: [{ table_id: 'tblTEST', name: '评审结论' }] }),
    'appTableRecord.list': API_OK({ items: rows, total: rows.length, has_more: false }),
    'appTableRecord.batchCreate': (args) => {
      sent.created = args?.data?.records?.map((r) => r.fields) ?? null;
      return { code: 0, msg: 'ok', data: { records: [{ record_id: 'recNEW', fields: sent.created?.[0] ?? {} }] } };
    },
    'appTableRecord.batchGet': (args) => {
      const ids = args?.data?.record_ids ?? [];
      const found = rows.filter((r) => ids.includes(r.record_id));
      return { code: 0, msg: 'ok', data: { records: found.length ? found : [{ record_id: ids[0], fields: sent.created?.[0] ?? {} }] } };
    },
    'appTableRecord.batchUpdate': (args) => {
      sent.updated = args?.data?.records ?? null;
      const ids = (args?.data?.records ?? []).map((r) => r.record_id);
      const found = rows.filter((r) => ids.includes(r.record_id));
      // 回读要「改完之后的样子」：拿旧行叠上本次提交的字段
      const merged = (found.length ? found : [{ record_id: ids[0], fields: {} }]).map((r) => {
        const patch = (args?.data?.records ?? []).find((x) => x.record_id === r.record_id)?.fields ?? {};
        return { record_id: r.record_id, fields: { ...r.fields, ...patch } };
      });
      return { code: 0, msg: 'ok', data: { records: merged } };
    },
  });
  lw.__injectClient(c.cl);
  return { c, sent };
}

/* ─────────────────────────── 1. 纯函数 ─────────────────────────── */
console.log('\n═══ 1. 内容 ID / 状态 / 结论抽取（纯函数）═══');

const IMG_TEXT = ['5', 'MOMCOZY', 'Bereit Fur Die Nacht，', 'Supermama？', 'Manche Superkrafte',
  'Passen Auf Den', 'Nachttisch', '5615', 'RC', '刘华的', 'ROOT', '刘华丽', '5615 ROOT',
  '"Was Sind Deine Mama-Hacks Fuir Ruhigere Nachte？"', '5615 ROC'].join('\n');

t('内容 ID = AUTO-<sha256(送审文本去尾空白) 前 12 位>，与链算的**同一个**', () => {
  const id = rp.contentIdOf(IMG_TEXT);
  eq(id, 'AUTO-48cac901ac43',
    '与 10-05 那份报告里的 content_id 对不上 —— 对不上就会写出**重复行**');
  // 反向对照：末尾多一个换行**不许**改变 ID（链算的时候用的是去尾空白的那一份）
  eq(rp.contentIdOf(IMG_TEXT + '\n'), id, '尾部空白不该改变内容 ID');
  // 反向对照：内容真变了，ID 必须变
  ok_(rp.contentIdOf(IMG_TEXT + 'x') !== id, '内容变了 ID 却没变 —— 那这个 ID 就不是内容指纹');
  eq(rp.contentIdOf(''), null, '空文本没有内容 ID');
});

t('结论 → 状态：**三态不许进这一格**，机器只落「待审」（PRD §8.2 逐字）', () => {
  // ★★ 2026-10-15（Owner）：「状态按照 prd：待审 / 已修改 / 已发布，现在填的错的」。
  //   PRD §8.2 逐字：「… Agent 结论、置信度、问题数量、问题分类汇总、报告链接 /
  //   人工复核人、复核结论、sign-off 人、发布时间 / **状态：待审 / 已修改 / 已发布**」
  //   ⇒ 三态是 `Agent 结论` 的值域。旧断言把错的行为钉住了（`statusOf('BLOCK')==='BLOCK'`），
  //     所以这条**必须与实现一起改** —— 否则判据本身在保护缺陷。
  eq(rp.statusOf('BLOCK'), '待审', '三态不许进「状态」——它是 `Agent 结论` 的值域');
  eq(rp.statusOf('REVIEW'), '待审'); eq(rp.statusOf('PASS'), '待审');
  eq(rp.statusOf('NEEDS_INPUT'), '待审', '拒答/未测/空同样落「待审」—— 它们都还没有定论，等人');
  eq(rp.statusOf(null), '待审'); eq(rp.statusOf('未测'), '待审');
  // **反向对照**：把结论原样返回（旧实现）⇒ 上面第一条必须不成立。没有它，
  //   这条判据可能只是「所有输入都给待审」的恒真式，看不出实现是否又改回三态。
  const asOld = (c) => (String(c ?? '').toUpperCase().includes('BLOCK') ? 'BLOCK' : '待审');
  ok_(asOld('BLOCK') !== rp.statusOf('BLOCK'), '旧实现（三态照搬）必须与现实现给出不同的值');
});

t('「状态」的人设终态受保护：已修改 / 已发布 不许被机器改回「待审」', () => {
  eq(rp.HUMAN_TERMINAL_STATUS, ['已修改', '已发布'], '终态清单就是 PRD 三档里机器不拥有的那两档');
  ok_(rp.HUMAN_TERMINAL_STATUS.includes('已发布') && !rp.HUMAN_TERMINAL_STATUS.includes('待审'),
      '「待审」是机器的档位，不能被当成终态挡住（第一次送审必须能落上）');
});

t('从链的回答里抽结论：抽不到就回 null，**不猜**', () => {
  eq(rp.conclusionOf('**引擎最终输出：`BLOCK`** ｜ review_id = rv-x'), 'BLOCK');
  eq(rp.conclusionOf('state = NEEDS_INPUT ｜ fails_closed = true'), 'NEEDS_INPUT');
  eq(rp.conclusionOf('这条我没读到，稍后再试'), null, '抽不到就该是 null —— 猜一个等于编结论');
});

// ★★ 2026-10-07（Owner 同意）—— **免责句里出现 PASS ≠ 结论是 PASS**。
//   旧判据取全文**第一个**三态词 ⇒ 下面前三条全部抠成 `PASS`（fail-open：把"不能放行"读成放行）。
//   素材 D（表行 `recvxlAvpEWMIX`）就是这么在库侧零读数的情况下落了 `Agent 结论=PASS`。
//   变异自证：把 `conclusionOf` 改回 `/\b(PASS|REVIEW|BLOCK|NEEDS_INPUT)\b/` ⇒ 前三条**精确变红**。
t('★ 免责句/否定句里的三态词**不许**被当成结论（fail-open 防线）', () => {
  eq(rp.conclusionOf('库侧未参与 ⇒ 本条**不得当 PASS 依据**。结论：REVIEW。'), 'REVIEW',
     '有结论行 ⇒ 认结论行那个，不认前面那句免责话');
  eq(rp.conclusionOf('本次没跑到引擎，所以**不能当 PASS**；请重试。'), null,
     '没有结论行 ⇒ 回 null（宁空不猜），**不许**抠成 PASS');
  eq(rp.conclusionOf('链没跑成，结论未知（不是 PASS，也不是 REVIEW）。'), null,
     '「结论未知」不是结论行 ⇒ null');
  eq(rp.conclusionOf('本单不得据此当 PASS。'), null, '免责句单独出现 ⇒ null');
  // 正例：三种**有格式契约**的读数位置仍然要认（判据没被收窄到认不出来）
  eq(rp.conclusionOf('【审查结论：REVIEW】共发现 2 处需人工确认。'), 'REVIEW', 'PRD §5.3 结论行');
  eq(rp.conclusionOf('**结论：BLOCK**（红线命中）'), 'BLOCK', '`结论：` 行');
  eq(rp.conclusionOf('状态：NEEDS_INPUT'), 'NEEDS_INPUT', '`状态：` 行');
});

t('要写的字段只含**机器那一侧**；人填的格子一个都不进去', () => {
  const f = rp.rowFieldsOf({ contentId: 'AUTO-1', question: '审一下', contentType: '社媒图片',
                             conclusion: 'NEEDS_INPUT', issueCount: 5, summary: 'x' });
  eq(f['状态'], '待审');
  eq(f['问题数量'], 5);
  for (const k of rp.HUMAN_FIELDS) ok_(!(k in f), `人填的字段「${k}」不许出现在要写的字段里`);
  // 空值不写：免得把已有的值覆盖成空
  const g = rp.rowFieldsOf({ contentId: 'AUTO-1' });
  ok_(!('置信度' in g) && !('报告链接' in g), '没有值就不该出现在提交里');
});

/* ─────────────────────────── 2. 落表行为 ─────────────────────────── */
console.log('\n═══ 2. 落表：链没发就我们发、链发了就补空字段、人填的不许动 ═══');

await ta('表里这一轮**一行都没有** → 必须新建一行（这就是那条硬规矩的兜底）', async () => {
  const { c, sent } = install({ rows: [] });
  const r = await rp.ensureReviewRow({
    contentId: rp.contentIdOf(IMG_TEXT), question: '审一下这张图能过吗？', contentType: '社媒图片',
    conclusion: 'NEEDS_INPUT', issueCount: 5, summary: '拒答（fail-closed）',
  }, { since: Date.now() - 60_000, question: '审一下这张图能过吗？' });
  eq(r.action, 'created', `该新建，实际 ${r.action}：${r.detail}`);
  eq(r.ok, true);
  eq(c.hit('appTableRecord.batchCreate'), 1, 'batchCreate 必须被调**恰好一次**');
  eq(sent.created[0]['内容 ID'], rp.contentIdOf(IMG_TEXT));
  eq(sent.created[0]['状态'], '待审');
  eq(sent.created[0]['问题数量'], 5);
  for (const k of rp.HUMAN_FIELDS) ok_(!(k in sent.created[0]), `新建时不许写人填的「${k}」`);
  eq(r.readback, 'consistent', `回读必须一致，实际 ${r.readback}：${r.detail}`);
});

await ta('链自己写了那一行 → **补空字段**，不许再建一行', async () => {
  const rows = [{ record_id: 'recCHAIN', fields: {
    '内容 ID': rp.contentIdOf(IMG_TEXT), '写⼊时间': Date.now(), '写入时间': Date.now(),
    '送审问题': '审一下这张图能过吗？', '内容 ID2': undefined,
    'Agent 结论': 'BLOCK', '问题数量': null, '状态': 'BLOCK' } }];
  const { c, sent } = install({ rows });
  const r = await rp.ensureReviewRow({
    contentId: rp.contentIdOf(IMG_TEXT), question: '审一下这张图能过吗？', contentType: '社媒图片',
    conclusion: 'BLOCK', issueCount: 3, summary: '命中 S-1.2',
  }, { since: Date.now() - 60_000, question: '审一下这张图能过吗？' });
  eq(r.action, 'updated', `该补字段，实际 ${r.action}：${r.detail}`);
  eq(c.hit('appTableRecord.batchCreate'), 0, '**一行都不许新建**（否则同一单两行）');
  const patch = sent.updated[0].fields;
  eq(patch['问题数量'], 3, '空着的机器字段要补上');
  eq(patch['问题分类汇总'], '命中 S-1.2');
  ok_(!('Agent 结论' in patch), '**值没变就不写**（本轮 BLOCK＝已有 BLOCK ⇒ 不该产生写入）');
  for (const k of rp.HUMAN_FIELDS) ok_(!(k in patch), `人填的「${k}」不许进补写`);
});

// ★★ 2026-10-08（Owner 同意「推荐 B」）—— **结论派生列允许改写**。
//   病灶（实测，不是推论）：素材 A 那行 `recvxlTh9b6HYq` 上，
//   `Agent 结论=REVIEW`（引擎建行时写的）＋ `问题分类汇总=「未能得出结论（NEEDS_INPUT）」`
//   （守衡后来写的、当时判据过宽）—— 两格都已填 ⇒ 「只补空」让它们**谁也改不动**，
//   这一行自相矛盾且**无法自愈**；多轮送审结论变化（REVIEW→BLOCK）同样落不了地。
//   变异自证：把 `CONCLUSION_DERIVED_FIELDS` 改成 `['状态']`（回到改动前）⇒ 本组**精确变红**。
await ta('★ 结论派生列：**值变了就要改写**（不许定格在第一轮）', async () => {
  const rows = [{ record_id: 'recDERIV', fields: {
    '写入时间': Date.now(), '送审问题': '审一下这张图能过吗？',
    '内容 ID': rp.contentIdOf(IMG_TEXT),
    'Agent 结论': [{ text: 'REVIEW', type: 'text' }],   // 真实形状：文本字段是数组
    '问题数量': 1, '置信度': 0, '状态': 'REVIEW',
    '问题分类汇总': '链已跑完（145s）。**未能得出结论**（NEEDS_INPUT）｜原因码 `coverage_not_covered`',
    '报告链接': { link: 'https://old.example/doc', text: '审查报告' },
  } }];
  const { sent } = install({ rows });
  const r = await rp.ensureReviewRow({
    contentId: rp.contentIdOf(IMG_TEXT), question: '审一下这张图能过吗？', contentType: '社媒图片',
    conclusion: 'BLOCK', issueCount: 3, confidence: 1, summary: '命中 S-1.2 / S-2.1',
    reportUrl: 'https://new.example/doc',
  }, { since: Date.now() - 60_000, question: '审一下这张图能过吗？' });
  eq(r.action, 'updated');
  const patch = sent.updated[0].fields;
  eq(patch['Agent 结论'], 'BLOCK', '结论变了 ⇒ 必须改写（不许定格 REVIEW）');
  eq(patch['问题数量'], 3, '问题数量跟着本轮结论走');
  eq(patch['置信度'], 1, '置信度跟着本轮结论走');
  eq(patch['问题分类汇总'], '命中 S-1.2 / S-2.1', '汇总列必须换成本轮那份');
  eq(patch['状态'], '待审',
     '**状态不跟结论走**：PRD §8.2 的三档里机器只拥有「待审」；三态只进 `Agent 结论`');
  // 反向对照：**非**派生列照旧只补空 —— 报告链接只该被写一次（复跑不许把旧链接改掉）
  ok_(!('报告链接' in patch), '报告链接不是派生列：已有值 ⇒ 不许改写（否则复跑会把旧链接换掉）');
  ok_(!('内容 ID' in patch) && !('送审问题' in patch), '内容 ID / 送审问题照旧只补空');
  for (const k of rp.HUMAN_FIELDS) ok_(!(k in patch), `人填的「${k}」照旧一个字都不许动`);
});

await ta('反向对照·结论派生列**同值不写**：一次「什么都没变」不许记成一次写入', async () => {
  const rows = [{ record_id: 'recSAME', fields: {
    '写入时间': Date.now(), '送审问题': '审一下这张图能过吗？',
    '内容 ID': rp.contentIdOf(IMG_TEXT),
    'Agent 结论': 'REVIEW', '问题数量': 2, '状态': '待审',   // 机器档位；库里已是本轮该写的值
  } }];
  const { sent } = install({ rows });
  const r = await rp.ensureReviewRow({
    contentId: rp.contentIdOf(IMG_TEXT), question: '审一下这张图能过吗？',
    conclusion: 'REVIEW', issueCount: '2', summary: null,   // 注意：条数给字符串 '2'
  }, { since: Date.now() - 60_000, question: '审一下这张图能过吗？' });
  eq(r.action, 'unchanged', `同值（'2' 与 2 也算同值）不许产生写入，实际 ${r.action}`);
  ok_(!sent.updated, '一次 API 都不该发');
});

await ta('★ 「状态」的人设终态受保护：已修改 / 已发布 不许被机器改回「待审」', async () => {
  const rows = [{ record_id: 'recHUMAN', fields: {
    '写入时间': Date.now(), '送审问题': '审一下这张图能过吗？',
    '内容 ID': rp.contentIdOf(IMG_TEXT),
    'Agent 结论': 'REVIEW', '问题数量': 2, '状态': '已发布',   // ← 人已经处理完了
  } }];
  const { sent } = install({ rows });
  const r = await rp.ensureReviewRow({
    contentId: rp.contentIdOf(IMG_TEXT), question: '审一下这张图能过吗？',
    conclusion: 'REVIEW', issueCount: 2,
  }, { since: Date.now() - 60_000, question: '审一下这张图能过吗？' });
  const patch = (sent.updated ?? [])[0]?.fields ?? {};
  ok_(!('状态' in patch), '「已发布」是人的终态 ⇒ 机器再送审一次也不许把它改回「待审」');
  eq(r.action, 'unchanged', '除了状态没别的可写 ⇒ 这一轮不该产生写入');

  // **反向对照**：把库里换成「待审」（机器的档位）⇒ 同一套输入**必须**照旧能写
  //   （否则「保护终态」会顺手把「第一次送审落状态」也挡掉）。
  const rows2 = [{ record_id: 'recWAIT', fields: { ...rows[0].fields, '状态': '待审', '问题数量': 1 } }];
  const inst2 = install({ rows: rows2 });
  const r2 = await rp.ensureReviewRow({
    contentId: rp.contentIdOf(IMG_TEXT), question: '审一下这张图能过吗？',
    conclusion: 'REVIEW', issueCount: 2,
  }, { since: Date.now() - 60_000, question: '审一下这张图能过吗？' });
  eq(r2.action, 'updated', '库里是「待审」时，本轮该写的东西照旧要写');
  ok_(inst2.sent.updated?.length === 1, '反向对照必须真的发生过一次写入');
});

await ta('结论派生列的名单本身受判据守着（漏一个就是一类卡住的行）', () => {
  eq(rp.CONCLUSION_DERIVED_FIELDS.slice().sort(),
     ['Agent 结论', '问题分类汇总', '置信度', '状态', '问题数量'].sort(),
     '这五格必须齐 —— 少一格，那一格就会「写错之后永远改不回来」');
  for (const k of rp.CONCLUSION_DERIVED_FIELDS) {
    ok_(rp.MACHINE_FIELDS.includes(k), `「${k}」必须仍在机器字段里（否则永远补不上）`);
    ok_(!rp.HUMAN_FIELDS.includes(k), `「${k}」不许混进人的格子`);
  }
  for (const k of rp.HUMAN_FIELDS) ok_(!rp.CONCLUSION_DERIVED_FIELDS.includes(k),
    `人的格子「${k}」不许被列进可改写名单`);
});

await ta('链那一行**人填过**的格子：一个字节都不许动', async () => {
  const rows = [{ record_id: 'recHUMAN', fields: {
    '写入时间': Date.now(), '送审问题': '审一下这张图能过吗？',
    '人工复核人': [{ id: 'ou_whoever', name: '刘华丽' }], '复核结论': '看过了，不能发',
    'Agent 结论': 'BLOCK' } }];
  const { sent } = install({ rows });
  const r = await rp.ensureReviewRow({
    contentId: rp.contentIdOf(IMG_TEXT), question: '审一下这张图能过吗？',
    conclusion: 'BLOCK', issueCount: 1, summary: 's',
  }, { since: Date.now() - 60_000, question: '审一下这张图能过吗？' });
  eq(r.action, 'updated');
  const patch = sent.updated[0].fields;
  ok_(!('人工复核人' in patch) && !('复核结论' in patch),
    '人填过的格子被写进去了 —— 补写只许补机器那一侧的空格');
});

await ta('反向对照·同一窗口里是**别人的**那一行 → 不许去补它，要自己新建', async () => {
  const rows = [{ record_id: 'recOTHER', fields: {
    '写入时间': Date.now(), '送审问题': '这段 listing 文案能不能发？', 'Agent 结论': 'REVIEW' } }];
  const { c } = install({ rows });
  const r = await rp.ensureReviewRow({
    contentId: 'AUTO-nomatch', question: '审一下这张图能过吗？',
    conclusion: 'NEEDS_INPUT', issueCount: 0, summary: 's',
  }, { since: Date.now() - 60_000, question: '审一下这张图能过吗？' });
  eq(r.action, 'created', `窗口里那一行不是这一单的，必须自己新建（实际 ${r.action}）`);
  eq(c.hit('appTableRecord.batchUpdate'), 0, '不许改别人的行');
});

await ta('反向对照·算不出内容 ID 时**照样要写**（这条保证不能被算 ID 绑架）', async () => {
  const { c, sent } = install({ rows: [] });
  const r = await rp.ensureReviewRow({
    contentId: null, question: '（只有问句，素材算不出 ID）', conclusion: 'NEEDS_INPUT',
    summary: '链没跑成 —— 留痕用',
  }, { since: Date.now() - 60_000, question: '（只有问句，素材算不出 ID）' });
  eq(r.action, 'created', '算不出 ID 也必须落表');
  eq(c.hit('appTableRecord.batchCreate'), 1);
  ok_(!('内容 ID' in sent.created[0]), '算不出就不写那一格，不许编一个');
});

await ta('dry-run：一个字节都不许落盘', async () => {
  const { c } = install({ rows: [] });
  const r = await rp.ensureReviewRow({ contentId: 'AUTO-x', question: 'q', conclusion: 'PASS' },
                                     { dryRun: true, since: Date.now() - 1000, question: 'q' });
  eq(r.action, 'created');
  eq(c.hit('appTableRecord.batchCreate'), 0, 'dry-run 不许真建行');
  eq(c.hit('appTableRecord.batchUpdate'), 0, 'dry-run 不许真改行');
});

/* ─────────────────────────── 3. 接线 ─────────────────────────── */
console.log('\n═══ 3. 接线：闸门返回之后**必须**真的去落表 ═══');

t('`agent.mjs` 的闸门里必须**恰好一处**落表调用，且它是**可注入**的', () => {
  const src = fs.readFileSync(new URL('./agent.mjs', import.meta.url), 'utf8')
    .split('\n').filter((l) => !l.trim().startsWith('//')).join('\n');
  const calls = src.match(/await\s+publishRunner\s*\(/g) ?? [];
  eq(calls.length, 1, `实际 ${calls.length} 处 —— 定义了不调用，就是 §2.4 那条「常量定义了没人用」的老病`);
  // ★ 「可注入」本身也是判据：写死成 `reviewPublish.ensureReviewRow(...)` 的话，
  //   单测里一个假结论就会**真的**往 Owner 的表里写一行（2026-10-05 实测发生过）。
  const inj = src.match(/publishRunner\s*=\s*reviewPublish\.ensureReviewRow/g) ?? [];
  ok_(inj.length >= 2, '`publishRunner` 的默认值要在 handleMessage 与 runSubmissionGate 两处都留着（实际 ' + inj.length + ' 处）');
});

t('送审任务里必须带那两条硬规矩（自命中=反面依据 / 必须落表）', async () => {
  const tools = await import('./tools.mjs');
  const r = tools.REVIEW_HARD_RULES;
  ok_(/自命中/.test(r) && /反面依据/.test(r), '缺「自命中是反面依据」那一条');
  ok_(/不许/.test(r) && /拒答/.test(r), '必须明写「不许以自循论证为由拒答」');
  ok_(/每一个评审任务都必须落表/.test(r), '缺「必须落表」那一条');
  ok_(/tblCXPQVzfFWWCon/.test(r), '得把表的坐标写出来，否则执行者不知道往哪写');
  // 反向对照：这段文本必须真的被拼进任务里（否则它只是仓库里的一段死字符串）
  const src = fs.readFileSync(new URL('./tools.mjs', import.meta.url), 'utf8');
  ok_(/REVIEW_HARD_RULES\]/.test(src) || /REVIEW_HARD_RULES\)/.test(src),
    'REVIEW_HARD_RULES 没有出现在任何拼接里 —— 那就等于没写');
});

/* ─────────── 3.5 落库正文不许带 markdown 星号（Owner 2026-10-14） ───────────
 * 起因：Owner「所有输出中不允许包含 `**` 星号」—— 而**这张表就是「落库」本身**。
 * 实测（只读盘点真表）：294 行里 **164 行**至少有一格带 `**`：
 *   · `问题分类汇总` —— 那句 `问题数量按 **0** 记` 是**我们自己的代码**拼的（`machineNumbers`）；
 *   · `送审问题` —— 模型/人给的原文。
 * 判据是**行为级**的：真调 `rowFieldsOf()`（它是唯一的拼行函数），看拼出来的字段里有没有星号。
 * 反向对照两条：**不该摘的格不许动**（数字/链接），**不该丢的字一个都不许丢**。
 */
console.log('\n═══ 3.5 落库正文不许带 markdown 星号 ═══');

t('落库字段：文本格摘掉 `**`，数字与链接格一个都不动', () => {
  const f = rp.rowFieldsOf({
    contentId: 'AUTO-test',
    question: '这句 **能不能发** ？',
    contentType: 'text',
    channel: '未指定',
    productLine: '吸奶器',
    version: 'v1',
    conclusion: 'REVIEW',
    confidence: 0,
    issueCount: 1,
    summary: '链已跑完（141s）。\n\n**逐条依据**：问题数量按 **0** 记（引擎未给出该读数）',
    reportUrl: 'https://example.feishu.cn/docx/abc',
  });
  const txt = ['送审问题', '内容类型', '渠道', '产品线', '送审版本', 'Agent 结论', '问题分类汇总']
    .map((k) => f[k]).filter((v) => v !== undefined);
  for (const v of txt) eq(String(v).includes('*'), false, `文本格里还有星号：${String(v).slice(0, 120)}`);
  // ★ 反向对照 A：数字格与链接格不许被「顺手统一」
  eq(f['置信度'], 0, '数字格必须原样是 0');
  eq(f['问题数量'], 1, '数字格必须原样是 1');
  eq(typeof f['报告链接'], 'object', '链接格必须是结构化对象，不是字符串');
  eq(String(f['报告链接'].link).includes('*'), false, '链接里本来就没有星号');
  // ★ 反向对照 B：摘的是符号，不是内容
  eq(String(f['送审问题']), '这句 能不能发 ？', '摘符号不许改别的字');
  ok_(String(f['问题分类汇总']).includes('问题数量按 0 记'), '正文一个都不能丢');
  ok_(String(f['问题分类汇总']).includes('逐条依据'), '`**逐条依据**` 要变成 `逐条依据`，不是被删掉');
});

/* ───────────────── 4b. 两侧合并置信度的**两格豁免**（Owner 2026-10-15）─────────────────
 *
 * 为什么非钉不可：这两格是拿 **80 行真数据**核出来的 ——
 *   · **12 行是 P0 命中**：PRD §6.6 逐字「P0 层级规则**不适用置信度分流**，命中即 BLOCK」
 *     ⇒ 本库口径是 **1.0**。不守这一格 ⇒ 它们会被合并数降成 0.93（"确定性命中"被写成"还有不确定"）。
 *   · **40 行是 `0`**（引擎未做判定）：`0` 在本库有专门语义 =「**没有做出判定**」，不是零风险。
 *     拿模型侧的数去顶它 = 给一个**根本没有结论**的单子配一个"确定性"。
 * ★ 反向对照也在下面：普通单不给合并数时，**不许**变成 0.85（否则这条判据可能只是"所有输入都改"）。
 */
console.log('\n═══ 4b. 两侧合并置信度：P0 与拒答两格豁免 ═══');
t('D1 普通评审单（非 P0、非拒答）⇒ 用两侧合并数', () => {
  const r = rp.machineNumbers({ review: { issue_count: 3, confidence: 0.95 } }, 'REVIEW', MERGED_CONF);
  eq(r.confidence, 0.85, '普通单必须采用两侧合并数');
  ok_(/两侧合并/.test(r.note), '填了合并数就必须同时填口径说明');
});
t('D2 ★ P0 命中 ⇒ **不许**被合并数覆盖（PRD §6.6 不适用分流）', () => {
  const r = rp.machineNumbers({ p0_fastpath: true, confidence: 1.0 }, 'BLOCK', MERGED_CONF);
  eq(r.confidence, 1, 'P0 命中的置信度是确定性命中（本库口径 1.0），不许降成 0.93/0.85');
  ok_(/P0 不适用置信度分流/.test(r.note), '豁免必须写明理由，否则读表的人以为算错了');
});
t('D3 ★ 拒答/未判 ⇒ **不许**被合并数覆盖（0 = 没有做出判定）', () => {
  const r = rp.machineNumbers({ review: { issue_count: 0, confidence: null } }, 'NEEDS_INPUT', MERGED_CONF);
  eq(r.confidence, 0, '拒答态没有可分流的结果，不许拿模型侧的数去顶');
  ok_(/未做判定/.test(r.note), '0 的含义必须自带解释（不能读成"零风险"）');
});
t('D4 ★★ 反向对照：普通单**不给**合并数时不许变成 0.85（否则 D1 只是"所有输入都改"）', () => {
  const r = rp.machineNumbers({ review: { issue_count: 3, confidence: 0.95 } }, 'REVIEW');
  eq(r.confidence, 0.95, '不给合并数 ⇒ 必须逐字回落旧口径（向后兼容，老调用点一行不改）');
});
/* ── 4b2. **覆盖缺口不是拒答**（2026-10-15 修；两行真数据逼出来的）────────────────────────
 * 形状：顶层 `state = REVIEW` ＋ **依据侧**记了 `refusal`（`coverage_not_covered`）。
 *   库侧**没给** confidence（拒答分支写 None），模型侧给了 ⇒ `mergedConfidence()` 已经按
 *   「一侧没给就用另一侧」算出合并数。旧判据 `!!rev?.refusal` 把它当"没判定" ⇒ **丢掉合并数写 0**。
 * 实测两行（同一批 10 行）：
 *   · `MC-US-YT-RLF9-789hh8-WEN`：打印 置信度(两侧合并)=0.85 [confirm]（库侧 — / 模型侧 confirm）⇒ 表里 0
 *   · `MC-US-YT-_xyLF4_AgAw`   ：打印 置信度(两侧合并)=0.93 [direct]（库侧 — / 模型侧 direct）   ⇒ 表里 0
 * 与 `dual_track.mjs::kbSideOf` 的 2026-10-07 口径一致：**判拒答只认顶层 `state`**。
 * ★ 变异自证：把 `review_publish.mjs` 的 `refused` 改回 `state === 'NEEDS_INPUT' || !!rev?.refusal`
 *   ⇒ **D7 精确变红**（合并数被丢掉、写成 0）；D7b 守着另一头（真拒答不许被顶掉）。 */
t('D7 ★ 覆盖缺口（顶层 REVIEW ＋ refusal 有值）⇒ 必须用两侧合并数，不是 0', () => {
  const res = { review: { issue_count: 6, confidence: null,
    refusal: { state: 'NEEDS_INPUT', reason_code: 'coverage_not_covered' } } };
  const r = rp.machineNumbers(res, 'REVIEW', { ...MERGED_CONF, kb_band: null, value: 0.85 });
  eq(r.confidence, 0.85, '库侧没给置信度、模型侧给了 ⇒ 用合并数（Owner：两侧汇总成一个输出）');
  ok_(/coverage_not_covered/.test(r.note), '覆盖缺口是**原因码**，要如实写进口径说明');
  ok_(/不算拒答/.test(r.note), '必须写明「顶层不是拒答 ⇒ 合并数照用」，否则读表的人以为漏了覆盖缺口');
});
t('D7b ★★ 反向对照：**真拒答**（顶层 NEEDS_INPUT）＋ refusal ⇒ 仍然不许被合并数顶掉', () => {
  const res = { review: { issue_count: 0, confidence: null,
    refusal: { state: 'NEEDS_INPUT', reason_code: 'claim_busy' } } };
  const r = rp.machineNumbers(res, 'NEEDS_INPUT', MERGED_CONF);
  eq(r.confidence, 0, '顶层就是拒答 ⇒ 0（没有可分流的结果），不许拿模型侧的数去顶');
});

/* ── 4c. 「这个数未标定」必须**写在产出它的地方**（Owner 2026-10-15 裁 ①）───────────────
 * 为什么非钉不可：那张表是**机器逐行重写**的（批跑器把结论表的汇总整格抄进采集表，
 *   实测 2026-10-15 一小时重写 28 行）⇒ 表里手改一句标注会被下一次回填**抹掉**。
 *   写在代码里，才每行、每轮都自带。
 * 变异自证：把 `CONF_UNCALIBRATED` 从两处注记里删掉 ⇒ **D1b / D5 精确变红**。
 */
console.log('\n═══ 4c. 置信度「未标定」声明（不得用作分流依据）═══');
t('D1b 用了两侧合并数 ⇒ 注记必须带「未标定 / 不得用作分流依据」', () => {
  const r = rp.machineNumbers({ review: { issue_count: 3, confidence: 0.95 } }, 'REVIEW', MERGED_CONF);
  ok_(/未标定/.test(r.note), '标定结论必须跟着数走，否则读表的人以为这个数很硬');
  ok_(/不得用作分流依据/.test(r.note), '★ 这句是 Owner 裁定的口径，不许省');
});
t('D5 库侧单轨（无合并数、引擎给了数）⇒ **也要**带这句，不许出现"裸数"', () => {
  const r = rp.machineNumbers({ review: { issue_count: 3, confidence: 0.95 } }, 'REVIEW');
  eq(r.confidence, 0.95, '值照旧回落（与 D4 同一条）');
  ok_(/未标定/.test(r.note) && /不得用作分流依据/.test(r.note), '库侧单轨那个数同样没标定 ⇒ 必须自带声明');
});
t('D5b 反向对照：P0 / 拒答两格**不许**被套上这句（它们不是两侧合并数，另有 PRD 口径）', () => {
  const p0 = rp.machineNumbers({ p0_fastpath: true, confidence: 1.0 }, 'BLOCK', MERGED_CONF);
  ok_(!/未标定/.test(p0.note), 'P0 的 1.0 是 PRD §6.6 明文口径，不是"未标定的合并数"');
  const rf = rp.machineNumbers({ review: { issue_count: 0, confidence: null } }, 'NEEDS_INPUT', MERGED_CONF);
  ok_(!/未标定/.test(rf.note), '拒答的 0 有专门语义（没有做出判定），别混进这句');
});

/* ── 4d. F1：`Number(null) === 0` —— 「**没有**合并数」不许被当成「置信度 0」（2026-10-15）─────
 * 来由：F1 让 `mergedConfidence` 在**库侧没有读数**时返回 `value: null`（不出这个数）。
 *   而旧写法 `Number(mergedConf?.value)` 把 null 变成 **0**、`Number.isFinite(0)` 为真
 *   ⇒ 表里落一个 0、注记却写「档位 —」。这是本库栽过的同一类陷阱（见 `bandOf` 的注释），
 *   换了个变量名又长了一次。
 * 变异自证：把守卫退回 `Number(mergedConf?.value)` ⇒ D6 **精确变红**（落 0 且带"两侧合并"注记）。
 */
console.log('\n═══ 4d. F1：没有合并数 ≠ 置信度 0 ═══');
const NO_READING = Object.freeze({ value: null, band: null, kb_band: null, model_band: 'direct',
  basis: '库侧没有置信度读数（拒答/覆盖缺口/未测）⇒ 不出这个数；模型侧单轨不构成置信度' });
t('D6 ★ 合并数是 null（库侧没读数）⇒ 不许落 0＋「两侧合并」注记，必须走"没有读数"那条', () => {
  const r = rp.machineNumbers({ review: { issue_count: 0, confidence: null } }, 'REVIEW', NO_READING);
  eq(r.confidence, 0, '没有可用的数 ⇒ 按本库口径记 0（0 = 没有做出判定）');
  ok_(!/两侧合并 · 档位/.test(r.note), '★ 没有数就不许出现"档位 —"那种自相矛盾的注记');
  ok_(/置信度按 \*\*0\*\* 记/.test(r.note), '0 必须自带解释，否则会被读成"零风险"');
});
t('D6b 反向对照：合并数缺失、但**引擎给了数** ⇒ 照旧用引擎那个数（守卫不许一刀切）', () => {
  const r = rp.machineNumbers({ review: { issue_count: 3, confidence: 0.95 } }, 'REVIEW', NO_READING);
  eq(r.confidence, 0.95, '引擎有读数时照旧回落，不许因为合并数缺失就把 0.95 抹成 0');
  ok_(!/两侧合并 · 档位/.test(r.note), '没用合并数就不许写"两侧合并"');
  ok_(/不得用作分流依据/.test(r.note), '回落出来的数同样未标定 ⇒ 仍要自带声明');
});

/* ─────────────────────────── 5. 自证自身无副作用 ─────────────────────────── */
console.log('\n═══ 5. 自证自身不许有副作用 ═══');
t('C1 真留痕文件在这次运行前后**没被动过**', () => {
  eq(realStat(), REAL_BEFORE, '自证写了真台账 —— 那等于跑一次自证就改掉了它要保护的东西（§2.4.4）');
});

try { fs.rmSync(TMP, { force: true }); } catch { /* 收尾失败不影响结论 */ }

console.log(`\n═══ 合计：通过 ${nPass} / 失败 ${fails.length} ═══`);
if (fails.length) { console.log('失败明细：'); for (const f of fails) console.log('  ·', f); }
process.exit(fails.length ? 1 : 0);
