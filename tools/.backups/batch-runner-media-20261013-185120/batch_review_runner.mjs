#!/usr/bin/env node
/**
 * batch_review_runner.mjs —— 本机批跑器：把一张表里的待审素材逐条走**守衡自己的**送审那条路，
 * 再用**守衡自己的身份**把结论发进指定会话（并把结论回填进表）。
 *
 * ── 为什么是这条路（2026-10-13，Owner 原话：「有权限不要说没权限」）────────────
 *
 *   守衡**自己有**发消息的权限（它一直在往那个私聊发主动提醒：`safeSend` → `feishu.sendMarkdown`，
 *   走的是它自己的 `client.im.message.create`），表读写你也给了。
 *   ⇒ 缺的从来不是权限，是**触发**。而触发可以由本机直接调它的内核产生：
 *
 *     `handleMessage()` → `runSubmissionGate()`
 *        （送审闸门 → 回执卡 → 链 → 模型侧 → 双轨合并 → §5.3 结论行）
 *     发那一步用它自己的 `client.im.message.create`（与 `reply-cards/index.mjs::sendCard` 同一条路）。
 *
 *   ⚠️ 先前我把它说成「要么你授权 `im:message`、要么你手动发」—— 那是**把路说窄了**：
 *      那条 `im:message` 只在「以**你的**身份发消息」时才需要，而这条路根本不用它。
 *
 * ── 三条边界（写清楚，别让下一个人以为它等同「你发一条消息」）──────────────────
 *
 *   ① 发出去的是**新消息**，不是「回复某一条」——本机跑没有可引用的真实 message id。
 *      形态（卡片 / §5.3 结论行进抬头 / 双轨计数）与正常回复**完全一致**，差别只在"挂在哪条下面"。
 *   ② 它用**独立会话键**跑模型（`chat_id = oc-batch-<tag>`），**不碰**你和守衡的那份私聊记忆 ——
 *      两个进程写同一个 session 文件会互相覆盖；顺带批跑也不会污染日常对话的上下文。
 *   ③ 它**不进守护进程**：批跑期间你照常和守衡聊天，两条路互不干扰。
 *
 * ── 用法 ────────────────────────────────────────────────────────────────────
 *
 *   node tools/batch_review_runner.mjs --status              # 看进度
 *   node tools/batch_review_runner.mjs --limit 1 --dry-run   # 只打印要跑什么
 *   node tools/batch_review_runner.mjs --limit 1             # 真跑 1 条（证明路通）
 *   node tools/batch_review_runner.mjs --limit 5             # 试跑 5 条
 *   node tools/batch_review_runner.mjs --limit 0             # 全部（0 = 不限）
 */
import fs from 'node:fs';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

import { handleMessage } from './agent/agent.mjs';
import { client, sendMarkdown } from './agent/feishu.mjs';
import { toCardOrText } from './reply-cards/envelope.mjs';
import { recordSend } from './agent/outbound.mjs';
import * as lw from './agent/lark_write.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.dirname(HERE);
const LARK = path.posix.join(process.env.HOME ?? '', '.dsh/bin/lark-cli');
const STATE = path.join(ROOT, 'PMO/shouheng-state/batch-review.json');

// ── 默认值只写在这一个地方 ───────────────────────────────────────────────────
const BASE = 'RY2UbCRjXaeeWwscUPScVN5AnQc';        // 「内容治理问题描述」那个 Base
const TABLE = 'tblavfbMDMeRsulo';                  // 「内容治理数据采集」（80 行）
const CHAT = 'oc_7775e2dacb6f2ebc9789cd6e681de5f7'; // 你和守衡的私聊
const SOURCE = 'batch-review';                      // 台账来源（已在 outbound.SOURCES 里登记）
const F = { id: '内容 ID', text: '采集数据', state: '状态' };
// 结论表的表名/字段与这张采集表**同名**（都照 PRD 那套）——回填就是按 `内容 ID` 把它们搬过来。
const RESULT_TABLE = 'tblCXPQVzfFWWCon';
const RESULT_FIELDS = ['Agent 结论', '状态', '问题数量', '置信度', '报告链接', '问题分类汇总'];
const NUM_FIELDS = new Set(['问题数量', '置信度']);

const args = process.argv.slice(2);
const has = (f) => args.includes(f);
const val = (f, d) => {
  const i = args.indexOf(f);
  return i >= 0 && args[i + 1] !== undefined ? args[i + 1] : d;
};
const LIMIT = Number(val('--limit', '5'));
const DRY = has('--dry-run');

function loadState() {
  try { return JSON.parse(fs.readFileSync(STATE, 'utf8')); } catch { return { items: {} }; }
}
function saveState(st) {
  fs.mkdirSync(path.dirname(STATE), { recursive: true });
  const tmp = `${STATE}.tmp`;
  fs.writeFileSync(tmp, JSON.stringify(st, null, 2, ), 'utf8');   // 原子写：半份 JSON 等于进度全丢
  fs.renameSync(tmp, STATE);
}

/** 读一张表（**守衡自己的**应用身份：`--profile dsh-kb --as bot`）—— 不借任何新权限。 */
function readTable(table) {
  const out = execFileSync(LARK, ['--profile', 'dsh-kb', 'base', '+record-list',
    '--base-token', BASE, '--table-id', table, '--page-size', '200',
    '--as', 'bot', '--format', 'json'], { cwd: ROOT, encoding: 'utf8', maxBuffer: 32 * 1024 * 1024 });
  const d = JSON.parse(out);
  if (!d.ok) throw new Error(`读表失败：${JSON.stringify(d.error).slice(0, 300)}`);
  const dd = d.data, fields = dd.fields ?? [], ids = dd.record_id_list ?? [];
  const cell = (row, name) => {
    const i = fields.indexOf(name);
    if (i < 0) return '';
    const v = row[i];
    if (Array.isArray(v)) return v.map((x) => (x && typeof x === 'object' ? x.text ?? '' : String(x))).join('');
    return v == null ? '' : v;
  };
  return { fields, rows: (dd.data ?? []).map((row, n) => ({ record_id: ids[n] ?? null, row, cell: (name) => cell(row, name) })) };
}

/** 把结论表里这一条的结果字段搬进采集表（**读回来再写**，不猜字段、不编值）。 */
async function writeBack(contentId, recordId, sinceMs, materialText = '') {
  // ★ 认领方式**不是**按 `内容 ID`：链会给素材**自己编一个**（实测它是 `AD-20261013-001`，
  //   而不是采集表里的 `MC-AMZ-…`）—— 按内容 ID 找会一条都找不到（我第一版就是这么写的）。
  //   改成**按时间窗认领「这一轮刚出现的那一行」**：与 `review_publish.ensureReviewRow`
  //   自己的判据同源（它那句注释写着「判据是时间窗，不是内容 ID」）。
  const res = readTable(RESULT_TABLE);
  // ★★ 认领顺序（2026-10-13 实测修）：**先按素材原文，再按时间窗**。
  //   为什么改：同一单在结论表里**可能有两行**（链侧 `feishu_publish` 自己也 upsert 一行，
  //   实测有的是空行 —— `问题数量=0`、`问题分类汇总` 空）。而时间窗取的是「窗口内最后一行」
  //   ⇒ 一旦链侧那行落在后面，回填就会把**空行**搬进采集表（实测第 2 条就是这么丢的依据块）。
  //   素材原文才是这一单真正的键（与 `--fill-all` 同一份判据，两处不许各写一套）。
  const norm = (t) => String(t ?? '').replace(/<br\s*\/?>/gi, ' ').replace(/\s+/g, ' ').trim().toLowerCase();
  const key = norm(materialText).slice(0, 120);
  const inWindow = res.rows.filter((r) => {
    const t = Date.parse(String(r.cell('写入时间')));
    return Number.isFinite(t) && t >= sinceMs;
  });
  const byText = key ? res.rows.filter((r) => norm(r.cell('送审问题')).startsWith(key)) : [];
  // 候选里挑**信息最全**的那一行（空行永远排在最后）
  const richest = (rows) => rows.slice().sort((a, b) => {
    const score = (r) => (String(r.cell('问题分类汇总') ?? '').length > 0 ? 2 : 0)
      + (Number(r.cell('问题数量') ?? 0) > 0 ? 1 : 0);
    return score(a) - score(b);
  }).pop();
  const hit = byText.length ? richest(byText) : richest(inWindow);
  if (!hit) return { ok: false, why: `结论表里这一单（素材原文 ／ 自 ${new Date(sinceMs).toISOString()} 起）都没有行 —— 不写` };
  return writeFields(recordId, fieldsFrom(hit));
}

/** 从结论表的一行里取出要回填的那几格（**空的不写、URL 归一化**）—— 两处调用共用这一份判据。 */
function fieldsFrom(hit) {
  const fields = {};
  for (const name of RESULT_FIELDS) {
    const v = hit.cell(name);
    if (v === '' || v == null) continue;                       // 空的不写（不许把空值刷上去）
    let val = Array.isArray(v) && v.length === 1 && typeof v[0] === 'string' ? v[0]
            : (NUM_FIELDS.has(name) ? Number(v) : String(v));
    // ★ `报告链接` 那一列是 **URL 型字段**：塞 markdown 链接会 `1254068 URLFieldConvFail`
    //   ⇒ **整批 batchUpdate 被拒**（实测：六字段一起写时 ok=false 且 reason 为空，
    //   逐字段二分才看出是这一个字段）。判据里那一步「接口成功 ≠ 数据落下来」正是治它的。
    if (name === '报告链接') {
      const m = /\]\((https?:\/\/[^)]+)\)/.exec(String(val)) || /(https?:\/\/\S+)/.exec(String(val));
      // ★ 而且它要**对象式** `{link, text}` —— 裸字符串也是 `1254068 URLFieldConvFail`（实测三种形状：
      //   裸 URL ✗、带尾斜杠 ✗、`{link,text}` ✓）。这两层是同一个字段的两种坑，一起写在这儿。
      val = { link: m ? m[1] : String(val), text: '审查报告' };
    }
    fields[name] = val;
  }
  return fields;
}

/** 写回一行（带重试；**回读一致**才算成功）。 */
async function writeFields(recordId, fields) {
  // ★ 偶尔会返回一个**没有 code/msg/readback 的 ok:false**（实测两次，原因未定位；
  //   同一批字段单独写、隔一会儿再合并写都成功）。既然没定位到根因，就**不假装它不会发生**：
  //   重试一次 + 每次都要求**回读一致**才算成功 —— 这个判据本来就是 `lark_write` 自带的。
  let r = await lw.updateRecords({ senderName: '批跑器', chatId: CHAT }, BASE, TABLE,
                                 [{ record_id: recordId, fields }]);
  if (r?.ok !== true || r?.readback !== 'consistent') {
    const first = JSON.stringify({ ok: r?.ok, code: r?.code, msg: r?.msg, readback: r?.readback,
                                   detail: String(r?.readback_detail ?? '').slice(0, 120),
                                   keys: Object.keys(r ?? {}) });
    await new Promise((res) => setTimeout(res, 1500));
    r = await lw.updateRecords({ senderName: '批跑器', chatId: CHAT }, BASE, TABLE,
                               [{ record_id: recordId, fields }]);
    if (r?.ok !== true || r?.readback !== 'consistent') {
      r = { ...r, msg: `${r?.msg ?? ''} ｜ 第一次：${first}`.trim() };
    }
  }
  // ★ 「接口返回成功」不等于「数据落下来了」——`lark_write` 自带**回读**，这里必须把它带出来，
  //   否则回填会以「ok」的样子静默失败（今天实测过一次：报 ok、回读是空的）。
  return { ok: r?.ok === true && r?.readback === 'consistent',
           readback: r?.readback ?? '(未回读)',
           detail: [r?.msg, r?.code ? `code=${r.code}` : '', r?.readback_detail, r?.error]
             .filter(Boolean).join(' ｜ ') || '(无错误信息)',
           fields };
}

function readRows() {
  const t = readTable(TABLE);
  const fields = t.fields;
  if (!fields.includes(F.text)) throw new Error(`表里没有「${F.text}」这一列；实际：${fields.join('/')}`);
  if (!fields.includes(F.text)) throw new Error(`表里没有「${F.text}」这一列；实际：${fields.join('/')}`);
  return t.rows.map((r) => ({
    record_id: r.record_id, content_id: String(r.cell(F.id)),
    state: String(r.cell(F.state)), text: String(r.cell(F.text)),
  }));
}

/**
 * 发一条已经过信封层成形的消息 —— **与 `ws_daemon.replyTo` 同一条形态链**，
 * 只差"不挂在某条消息下面"（本机跑没有可引用的 message id）。
 */
async function sendShaped(raw, { verdict53 = null, reportLink = null, progress = null } = {}) {
  const shaped = toCardOrText(String(raw ?? ''), { verdict53, reportLink });
  let sent = null;
  if (shaped.card) {
    try {
      const r = await client.im.message.create({
        params: { receive_id_type: 'chat_id' },
        data: { receive_id: CHAT, msg_type: 'interactive', content: JSON.stringify(shaped.card) },
      });
      sent = { ok: true, mode: 'card', messageIds: [r?.data?.message_id].filter(Boolean) };
    } catch (e) {
      const why = e?.response?.data ? `卡片被拒 code=${e.response.data.code}` : `卡片异常 ${e?.message ?? e}`;
      console.log(`   ⚠ ${why} → 退纯文本`);
    }
  }
  if (!sent) {
    const r = await sendMarkdown(CHAT, shaped.text);
    sent = { ok: r.ok, mode: r.ok ? `text-fallback(${shaped.mode})` : 'none',
             messageIds: r.messageIds ?? [], error: r.error ?? null };
  }
  // 台账：一次外发一条（来源已在 SOURCES + FOLDING 里登记；A17 要求两集合恰好切分 SOURCES）
  recordSend({ chatId: CHAT, chatType: 'p2p', source: SOURCE, mode: sent.mode,
               messageIds: sent.messageIds, text: shaped.text, ok: sent.ok,
               error: sent.error ?? null, extra: progress ?? null });
  return sent;
}

async function runOne(row, tag) {
  // ★ 独立会话键：不碰你和守衡那份私聊记忆（见文件头边界 ②）。
  const sessionKey = `oc-batch-${tag}`;
  const ev = {
    message: {
      message_id: `om_batch_${tag}_${row.content_id}`, chat_id: sessionKey, chat_type: 'p2p',
      message_type: 'text', content: JSON.stringify({ text: row.text }),
    },
    sender: { sender_id: { open_id: 'ou_batch_runner' }, sender_type: 'user' },
  };
  const res = await handleMessage(ev, {
    notify: async (text) => { await sendShaped(text, { progress: { row: row.content_id, kind: 'ack' } }); },
    tIngress: Date.now(),
  });
  const meta = res?.meta ?? {};
  const sent = await sendShaped(res?.reply ?? '', {
    verdict53: meta.verdict53 ?? null, reportLink: meta.reportLink ?? null,
    progress: { row: row.content_id, kind: 'final' },
  });
  return { res, meta, sent, sessionKey };
}

async function main() {
  const rows = readRows();
  const st = loadState();

  if (has('--status')) {
    for (const r of rows) {
      const d = st.items[r.content_id] ?? {};
      console.log(`  ${r.content_id.padEnd(22)} ${r.state.padEnd(6)} ` +
        (d.answered_at ? `已答 ${d.secs}s ${d.state ?? ''}` : d.sent_at ? '已发待答' : '未跑'));
    }
    console.log(`共 ${rows.length} 行 ｜ 已跑 ${Object.keys(st.items).length}`);
    return 0;
  }

  // ── 整表回填：把**结论表里已经有的结论**按素材原文匹配回采集表 ─────────────────
  //   ★ 为什么需要它（Owner 2026-10-13：「只有 3 条数据，要回填结论」）：
  //     守衡在飞书侧被 @ 时，结论写进的是**结论表**（`tblCXPQVzfFWWCon`）；
  //     而采集表（80 行那张）只有本机批跑器在写 ⇒ **人 @ 出来的结论一直没回到这张表**。
  //   匹配键 = 素材原文：采集表的「采集数据」≈ 结论表的「送审问题」
  //     （后者是 `String(question).slice(0,2000)`，就是送审时那段原文）。
  //   取归一化后前 120 字比对；**匹配不上的如实列出来**，绝不按「最像的」硬填（填错比空着坏）。
  if (has('--fill-all')) {
    const res = readTable(RESULT_TABLE);
    const norm = (t) => String(t ?? '').replace(/<br\s*\/?>/gi, ' ').replace(/\s+/g, ' ').trim().toLowerCase();
    let filled = 0; const nomatch = []; const noText = [];
    for (const r of rows) {
      const key = norm(r.text).slice(0, 120);
      if (!key) { noText.push(r.content_id); continue; }
      const hit = res.rows.filter((x) => norm(x.cell('送审问题')).startsWith(key)).pop();
      if (!hit) { nomatch.push(r.content_id); continue; }
      const wb = await writeFields(r.record_id, fieldsFrom(hit));
      st.items[r.content_id] = { ...(st.items[r.content_id] ?? {}), record_id: r.record_id,
        filled_from: '结论表·按素材原文匹配',
        write_back: wb.ok ? 'ok' : `失败：${wb.why ?? wb.detail}`,
        write_back_readback: wb.readback ?? null, write_back_fields: wb.fields ?? null };
      saveState(st);
      if (wb.ok) filled++;
      console.log(`  ${wb.ok ? '✅' : '❌'} ${r.content_id} ｜ ${Object.keys(wb.fields ?? {}).join('/') || (wb.why ?? wb.detail)}`);
    }
    console.log(`\n整表回填：成功 ${filled} ｜ 结论表里还没有（未审） ${nomatch.length} ｜ 素材为空跳过 ${noText.length}`);
    if (nomatch.length) console.log('  尚未审过：' + nomatch.slice(0, 10).join('、') + (nomatch.length > 10 ? ` …共 ${nomatch.length} 条` : ''));
    return 0;
  }

  // ── 补回填：已经答过、但当时还没有回填那一步（或回填失败）的条目 ──────────────
  if (has('--backfill')) {
    const pending = rows.filter((r) => {
      const d = st.items[r.content_id] ?? {};
      return d.answered_at && d.write_back !== 'ok';
    });
    if (!pending.length) { console.log('没有要补回填的'); return 0; }
    for (const r of pending) {
      const d = st.items[r.content_id];
      // 时间窗起点 = 跑完时刻 − 这条耗时（`sent_at` 记的是**跑完**时刻）− 1 分钟宽限。
      //   ★ 第一版只按跑完时刻算，于是窗口**开晚了**：链在 06:29:48 就写好结论行了，
      //     而窗口从 06:30:02 起 ⇒ 明明有行却说「没有新行」。判据要盖住**整条**的运行区间。
      const since = Date.parse(d.ran_from ?? d.sent_at ?? '') - (d.ran_from ? 0 : (Number(d.secs ?? 0) * 1000)) - 60_000;
      const wb = await writeBack(r.content_id, r.record_id ?? d.record_id, Number.isFinite(since) ? since : 0, r.text);
      d.write_back = wb.ok ? 'ok' : `失败：${wb.why ?? wb.detail}`;
      d.write_back_readback = wb.readback ?? null;
      d.write_back_fields = wb.fields ?? null;
      console.log(`  ${r.content_id} → ${wb.ok ? '✅ ' + Object.keys(wb.fields ?? {}).join('/') : '❌ ' + (wb.why ?? wb.detail)}`);
      saveState(st);
    }
    return 0;
  }

  const todo = rows.filter((r) => (r.text || '').trim() && !(st.items[r.content_id] ?? {}).answered_at);
  const batch = LIMIT ? todo.slice(0, LIMIT) : todo;
  if (!batch.length) { console.log('没有要跑的（都跑过了？）'); return 0; }

  const tag = new Date().toISOString().slice(0, 16).replace(/[-:T]/g, '');
  console.log(`本机批跑 ｜ 表 ${TABLE} ｜ 发往 ${CHAT} ｜ 身份 = 守衡自己 ｜ `
    + `${DRY ? '干跑' : '真跑'} ｜ 本轮 ${batch.length} 条（还有 ${todo.length - batch.length} 条没跑）`);

  const t0 = Date.now();
  for (const [i, row] of batch.entries()) {
    console.log(`\n[${i + 1}/${batch.length}] ${row.content_id} ｜ ${[...row.text].length} 字 ｜ 表内状态 ${row.state}`);
    if (DRY) { console.log(`   —— 将逐字送进内核（前 140 字）：${row.text.slice(0, 140).replace(/\n/g, ' ⏎ ')}`); continue; }

    const t = Date.now();
    let out;
    try {
      out = await runOne(row, tag);
    } catch (e) {
      console.log(`   ❌ 内核抛异常：${e?.message ?? e}`);
      st.items[row.content_id] = { record_id: row.record_id, error: String(e?.message ?? e).slice(0, 300), at: new Date().toISOString() };
      saveState(st);
      continue;
    }
    const secs = Number(((Date.now() - t) / 1000).toFixed(1));
    const state = out.meta?.verdict53?.state ?? null;
    console.log(`   ✅ ${secs}s ｜ 三态 ${state ?? '—'} ｜ 链 ${out.meta?.chain?.ran ? '跑成' : '未跑成'} `
      + `｜ 卡片 ${out.sent.mode} ｜ 问题数 ${out.meta?.dual?.total ?? '—'}`);
    console.log(`      回答头：${String(out.res?.reply ?? '').split('\n')[0].slice(0, 70)}`);
    st.items[row.content_id] = {
      record_id: row.record_id, ran_from: new Date(t).toISOString(),
      sent_at: new Date().toISOString(), answered_at: true,
      secs, state, report_url: out.meta?.reportLink ?? null,
      issue_total: out.meta?.dual?.total ?? null,
      reply_reason: out.res?.reason ?? null, mode: out.sent.mode,
      message_ids: out.sent.messageIds ?? [],
      reply_head: String(out.res?.reply ?? '').split('\n').slice(0, 3).join(' ⏎ ').slice(0, 300),
    };
    saveState(st);
    // ── 回填采集表：从结论表把这一条的结果搬过来（守衡的链刚刚自己写进去的那一行）
    const wb = await writeBack(row.content_id, row.record_id, t, row.text);
    st.items[row.content_id].write_back = wb.ok ? 'ok' : `失败：${wb.why ?? wb.detail}`;
    st.items[row.content_id].write_back_readback = wb.readback ?? null;
    st.items[row.content_id].write_back_fields = wb.fields ?? null;
    saveState(st);
    console.log(`   ↳ 回填你的表：${wb.ok ? '✅ ' + Object.keys(wb.fields ?? {}).join('/') : '❌ ' + (wb.why ?? wb.detail)}`);
  }

  const done = Object.values(st.items).filter((d) => d.answered_at);
  const ss = done.map((d) => d.secs).filter(Boolean).sort((a, b) => a - b);
  console.log(`\n本轮 ${((Date.now() - t0) / 1000).toFixed(1)}s ｜ 累计已答 ${done.length} 条`);
  if (ss.length) {
    const mid = ss[Math.floor(ss.length / 2)];
    console.log(`单条：最快 ${ss[0]}s ｜ 中位 ${mid}s ｜ 最慢 ${ss[ss.length - 1]}s `
      + `⇒ 跑满 ${rows.length} 条估 ≈ ${(mid * rows.length / 60).toFixed(0)} 分钟（按中位）`);
  }
  return 0;
}

main().then((c) => process.exit(c)).catch((e) => { console.error('批跑器异常：', e); process.exit(1); });
