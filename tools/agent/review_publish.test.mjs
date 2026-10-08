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

t('结论 → 状态：三态照搬，「拒答/未测/空」一律落「待审」', () => {
  eq(rp.statusOf('BLOCK'), 'BLOCK'); eq(rp.statusOf('REVIEW'), 'REVIEW'); eq(rp.statusOf('PASS'), 'PASS');
  eq(rp.statusOf('NEEDS_INPUT'), '待审', '拒答必须落「待审」—— PRD 六档里没有「拒答」');
  eq(rp.statusOf(null), '待审'); eq(rp.statusOf('未测'), '待审');
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
  eq(patch['状态'], 'BLOCK', '状态照旧跟着结论走');
  // 反向对照：**非**派生列照旧只补空 —— 报告链接只该被写一次（复跑不许把旧链接改掉）
  ok_(!('报告链接' in patch), '报告链接不是派生列：已有值 ⇒ 不许改写（否则复跑会把旧链接换掉）');
  ok_(!('内容 ID' in patch) && !('送审问题' in patch), '内容 ID / 送审问题照旧只补空');
  for (const k of rp.HUMAN_FIELDS) ok_(!(k in patch), `人填的「${k}」照旧一个字都不许动`);
});

await ta('反向对照·结论派生列**同值不写**：一次「什么都没变」不许记成一次写入', async () => {
  const rows = [{ record_id: 'recSAME', fields: {
    '写入时间': Date.now(), '送审问题': '审一下这张图能过吗？',
    '内容 ID': rp.contentIdOf(IMG_TEXT),
    'Agent 结论': 'REVIEW', '问题数量': 2, '状态': 'REVIEW',
  } }];
  const { sent } = install({ rows });
  const r = await rp.ensureReviewRow({
    contentId: rp.contentIdOf(IMG_TEXT), question: '审一下这张图能过吗？',
    conclusion: 'REVIEW', issueCount: '2', summary: null,   // 注意：条数给字符串 '2'
  }, { since: Date.now() - 60_000, question: '审一下这张图能过吗？' });
  eq(r.action, 'unchanged', `同值（'2' 与 2 也算同值）不许产生写入，实际 ${r.action}`);
  ok_(!sent.updated, '一次 API 都不该发');
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

/* ─────────────────────────── 4. 自证自身无副作用 ─────────────────────────── */
console.log('\n═══ 4. 自证自身不许有副作用 ═══');
t('C1 真留痕文件在这次运行前后**没被动过**', () => {
  eq(realStat(), REAL_BEFORE, '自证写了真台账 —— 那等于跑一次自证就改掉了它要保护的东西（§2.4.4）');
});

try { fs.rmSync(TMP, { force: true }); } catch { /* 收尾失败不影响结论 */ }

console.log(`\n═══ 合计：通过 ${nPass} / 失败 ${fails.length} ═══`);
if (fails.length) { console.log('失败明细：'); for (const f of fails) console.log('  ·', f); }
process.exit(fails.length ? 1 : 0);
