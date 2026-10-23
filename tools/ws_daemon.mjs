#!/usr/bin/env node
/**
 * ws_daemon.mjs —— 守衡 · 常驻入口（v3：接入推理内核）
 *
 * 本文件只做五件事：建立长连接、把事件交给内核、**决定回复用什么形态**、
 * 把回复发出去、管理生命周期。
 * 所有「怎么想」的逻辑都在 agent/ 目录下，怎么「成形」在 reply-cards/ 下，都不在这里。
 *
 * 版本历史：
 *   v1  打印事件 + 写死回复（验证入向链路）
 *   v2  原始事件落盘（为解析层提供真实样本）
 *   v3  接入 agent/: 真理解 + 多轮记忆 + 工具调用
 *
 * 用法：
 *   node ws_daemon.mjs              # 常驻（前台）
 *   node ws_daemon.mjs --probe      # 启动并自检，10 秒后退出
 *   node ws_daemon.mjs --dump-only  # 只落盘原始事件，不回复（排查用）
 */
import * as Lark from '@larksuiteoapi/node-sdk';
import fs from 'node:fs';
import path from 'node:path';

import { config, describeConfig, LOG_DIR, REPO_ROOT, ensureDir, stateDir } from './agent/config.mjs';
import * as feishu from './agent/feishu.mjs';
import { plainify } from './agent/plain.mjs';
import * as vision from './agent/vision.mjs';
import * as scene from './agent/scene.mjs';
import * as video from './agent/video.mjs';
import * as asr from './agent/asr.mjs';
// ★ 2026-10-16：**媒材链接**（送审问题那一格里的图/视频链接）的启动自检 —— 见下面横幅那一条
import * as mediaLink from './agent/media_link.mjs';
import { handleMessage, flushSeen, loadedTools, status, mediaWithoutChain } from './agent/agent.mjs';
// ★ 链的上限只认一个出处（`tools.mjs` 的 `KB_REVIEW_TIMEOUT_MS`）：进度消息里那句
//   「到 N 分钟还没结论我会停下来」必须跟真实闸门一致 —— 写死一个数字就是第二份真相。
import { KB_REVIEW_TIMEOUT_MS } from './agent/tools.mjs';
// ★ 2026-10-20：单实例闸门 —— 防「重启窗口里两个守衡同时在线」（同一条消息答两遍／两单并行）
import * as singleInstance from './agent/single_instance.mjs';
// ★ 拒收账本的**唯一**取路径口（可被 SHOUHENG_IDENTITY_REJECT_LOG 覆盖）—— 从它定义处导入
import { identityRejectCount, KB_ROOT } from './agent/tools.mjs';
import { nonUsCiteCount } from './agent/ext_basis.mjs';
import { toCardOrText } from './reply-cards/envelope.mjs';
import { deriveVerdictLine } from './agent/prd53.mjs';
import { shapeOf } from './reply-cards/registry.mjs';
import { checkNow, checkPending, resolveChat, LARK_DOC_RE, bjDate, loadState, loadPendingState, saveChatId,
         pickAlertTarget,
         recheckDue as baselineRecheckDue } from './agent/prd_baseline.mjs';
import * as outbound from './agent/outbound.mjs';
import * as retryQueue from './agent/retry_queue.mjs';
import { checkExternal, loadState as loadExternalState, recheckDue as externalRecheckDue } from './agent/external_watch.mjs';

const PROBE     = process.argv.includes('--probe');
const DUMP_ONLY = process.argv.includes('--dump-only');

const EVENT_DUMP = path.join(LOG_DIR, 'ws_events.jsonl');
ensureDir(LOG_DIR);   // 失败只警告：日志目录建不出来不该阻止守衡启动

const T0 = Date.now();
const stamp = () => `[+${((Date.now() - T0) / 1000).toFixed(3).padStart(7)}s]`;
const log = (...a) => console.log(stamp(), ...a);

function dumpRaw(kind, data) {
  try { fs.appendFileSync(EVENT_DUMP, JSON.stringify({ at: new Date().toISOString(), kind, data }) + '\n'); }
  catch (e) { log('⚠ 事件落盘失败:', e.message); }
}

const counters = { events: 0, handled: 0, replied: 0, skipped: 0, failed: 0, uncaught: 0 };

/* ─────────── 运行状态（Q2 的 run-state 写方，2026-09-22 加） ───────────
 *
 * ★ 为什么要有这个文件。「守衡现在还在跑吗」原先只能靠在跑的进程上下文去猜：
 *   `ps -o etime=` 在受限环境被拒（`Operation not permitted`），而 launchd 的读数
 *   只说「在不在」，不说「活了多久、心跳还新不新鲜」。自证 E 段因此**恒退 2**。
 *   那不是环境限制，是**选型错误**：进程的生命周期归 launchd 管，而「它自己觉得怎么样」
 *   只有它自己写得出来。所以由守护进程自己写一份**可指得出对象**的读数。
 *
 * ★ 两份读数的分工（都不是孤证）：
 *   · `daemon-run.json` —— 它自己写的：`pid / startedAt / lastBeatAt / 计数`
 *   · launchd `state`+`pid` + `pgrep` + `os.kill(pid,0)` —— 外面看到的
 *   `judge_liveness` 把两边合起来判 `up`/`down`/`stuck`/`untested`（见 verify_shouheng_ops.py）。
 *
 * ★ 心跳过期（>12 分钟没刷新）是**「卡死」**，不是「没在跑」—— 两者要分开，
 *   因为处置不同：前者要重启，后者更要紧（已经在失联了）。
 *
 * ⚠️ 它是**覆盖写**的一份小文件，只有一个写者（本进程）。任何别的检查器都不许写它。
 */
const RUN_STATE_FILE = () => path.join(stateDir(), 'daemon-run.json');
const RUN_STARTED_AT = new Date();
let runStateWrites = 0, runStateFails = 0;

/* ─────────── 长连接的**状态**（2026-10-05 加）───────────
 *
 * ★ 为什么必须有这一块：实测 2026-10-05 07:10，守衡的长连接断了
 *   （`getaddrinfo ENOTFOUND open.feishu.cn` → 之后 `timeout of 15000ms exceeded`），
 *   而**没有任何东西会红**：
 *     · 进程活着、心跳每 5 分钟照打（E3 因此一直是绿的）；
 *     · SDK 自己在重试，但它的错误只进 logger —— **没注册回调，等于报给了空气**；
 *     · 群里那侧看到的是「守衡不回话了」，而盘上一切正常。
 *   这与 §2.4.1 第 5 行是同一个病：**一个会过期的读数，没有任何东西在它过期时变红**。
 *   「进程活着」和「还连着飞书」是两件事，必须分别有读数。
 *
 *   ⇒ 三个后果都要有：**看得见**（心跳里带一行）· **查得到**（写进 run-state 供自证读）·
 *     **能自愈**（重试循环真的死了就重新 start 一次，有上限、有留痕）。
 */
const wsState = {
  connected: false,      // 此刻连着吗（**不猜**：只由 SDK 的回调改）
  readyAt: null,         // 最近一次连上的时刻
  downSince: null,       // 第一次断开的时刻（恢复即清空）
  lastSignalAt: Date.now(),  // 最近一次收到任何 ws 回调的时刻（判「重试循环是不是死了」）
  lastError: null,
  lastErrorAt: null,
  reconnects: 0,         // SDK 报的重连次数
  revives: 0,            // **我们**主动重新 start() 的次数
};
const wsDownMinutes = () => (wsState.downSince ? (Date.now() - wsState.downSince) / 60_000 : 0);

function wsLine() {
  if (wsState.connected) {
    const up = wsState.readyAt ? Math.round((Date.now() - wsState.readyAt) / 60_000) : null;
    return `长连接=✅ 已连${up === null ? '' : ` ${up} 分钟`}`;
  }
  const down = wsDownMinutes();
  return `长连接=⚠️ **断线 ${down < 1 ? '不到 1' : Math.round(down)} 分钟**`
       + `${wsState.lastError ? `（最后错误：${String(wsState.lastError).slice(0, 80)}）` : ''}`
       + `｜重连 ${wsState.reconnects} 次 · 自愈 ${wsState.revives} 次 —— 这段时间群里发的消息收不到`;
}

/**
 * 自愈：**只在重试循环像是死了的时候**才重新 start 一次。
 *
 * 判据（缺一不可）：① 此刻没连着；② 最后一次 ws 回调已经过去 > 6 分钟
 * （SDK 的 reconnectInterval 是 120 秒 —— 6 分钟等于连续三轮都没动静）；
 * ③ 距上次自愈 > 10 分钟（有上限，不许把「断线」变成「每 5 分钟重连风暴」）。
 */
let lastReviveAt = 0;
function maybeReviveWs() {
  if (wsState.connected) return false;
  const quietMin = (Date.now() - wsState.lastSignalAt) / 60_000;
  const sinceReviveMin = (Date.now() - lastReviveAt) / 60_000;
  if (quietMin < 6 || sinceReviveMin < 10) return false;
  lastReviveAt = Date.now();
  wsState.revives++;
  log(`  ★ 长连接断了 ${Math.round(wsDownMinutes())} 分钟，且 ${Math.round(quietMin)} 分钟没有任何重连动静`
      + ` —— 主动重新 start()（第 ${wsState.revives} 次）`);
  void Promise.resolve()
    .then(() => ws.start({ eventDispatcher: dispatcher }))
    .then(() => log('  ★ 重新 start() 已发出'))
    .catch((e) => log(`  ❌ 重新 start() 失败：${e?.message ?? e}`));
  return true;
}

function writeRunState(note = null) {
  const body = {
    pid: process.pid,
    startedAt: RUN_STARTED_AT.toISOString(),
    startedAtBj: new Date(RUN_STARTED_AT.getTime() + 8 * 3600_000).toISOString().replace('Z', '+08:00'),
    startedAtEpoch: Math.floor(RUN_STARTED_AT.getTime() / 1000),
    lastBeatAt: new Date().toISOString(),
    uptimeSeconds: Math.floor((Date.now() - RUN_STARTED_AT.getTime()) / 1000),
    events: counters.events, handled: counters.handled, replied: counters.replied,
    skipped: counters.skipped, failed: counters.failed, uncaught: counters.uncaught,
    llmCalls: status().llm.calls,
    probe: PROBE, dumpOnly: DUMP_ONLY,
    // ★ 长连接读数（2026-10-05）：**「进程活着」与「还连着飞书」必须分开报**。
    //   `verify_shouheng_ops.py` 的 E4 读这三个字段；缺了它们就只能是「未测」。
    wsConnected: wsState.connected,
    wsDownSeconds: wsState.downSince ? Math.round((Date.now() - wsState.downSince) / 1000) : null,
    wsLastError: wsState.lastError ? String(wsState.lastError).slice(0, 200) : null,
    wsReconnects: wsState.reconnects, wsRevives: wsState.revives,
    note,
  };
  try {
    const file = RUN_STATE_FILE();
    ensureDir(path.dirname(file));
    const tmp = `${file}.tmp`;      // 先临时再 rename：读的人不会读到半个文件
    fs.writeFileSync(tmp, JSON.stringify(body, null, 2));
    fs.renameSync(tmp, file);
    runStateWrites++;
    return { ok: true };
  } catch (e) {
    runStateFails++;
    // 写不进去**要说出来**（但只在第一次与每 10 次说一次）：静默失败会让 E 段读到一份
    // 过期的 run-state，而它长得像「进程卡死了」。
    if (runStateFails === 1 || runStateFails % 10 === 0) log(`   ⚠ run-state 写不进去（第 ${runStateFails} 次）:`, e.message);
    return { ok: false, error: e.message };
  }
}

/* ─────────────────────── 事件处理 ─────────────────────── */

/**
 * 这条消息的**真实到达时刻**（ms epoch）—— PRD §12「@Agent 响应 ≤5 秒」的唯一计时起点。
 *
 * ★★ 2026-10-20（Owner 批准 ②）为什么现在才加：
 *   旧的 `group_response_ms` 在**这条路上一词从未拿到过** tIngress —— `handleMessage` 的默认值
 *   是 `null`，闸门里再 `?? Date.now()` 兜底，而那一刻**已经在读图之后**。
 *   ⇒ 这条指标量的是「回执自己发出去花了多久」（实测 1401ms / 383ms），**结构上不可能变红**，
 *   而同期飞书侧真值是 **60 / 120 / 180 秒**。这条尺子要能红，起点就必须是"消息到达"。
 *
 * 取值优先级：消息 `create_time`（飞书服务端盖的，最接近"她按下发送"）→ 本机此刻。
 * ⚠️ `create_time` 只认**落在合理区间**的（不早于 1 分钟前＝允许服务端时钟略快；
 *    不超过 24 小时的迟投/补发）；离谱值一律退回本机此刻，并把来源写进指标行 ——
 *    **不许把两个来源的数混着说**。
 *
 * @returns {{at:number, origin:'create_time'|'local'}}
 */
function ingressMsOf(msg) {
  const now = Date.now();
  const raw = String(msg?.create_time ?? '').trim();
  const n = Number(raw);
  if (raw && Number.isFinite(n) && n > 0) {
    const at = n > 1e12 ? n : n * 1000;      // 飞书给的是毫秒串；万一给了秒串也认
    const ageMs = now - at;
    if (ageMs > -60_000 && ageMs < 24 * 3600_000) return { at, origin: 'create_time' };
  }
  return { at: now, origin: 'local' };
}

async function onMessage(data) {
  counters.events++;
  dumpRaw('im.message.receive_v1', data);

  const msg = data?.message ?? {};
  const chatId = msg.chat_id;
  // ★ 必须在这里取：再晚几行就把「本机收到」当成了「她发出」。
  const ingress = ingressMsOf(msg);

  // 先落一行「收到了」，保证即使后面崩了，日志也能看出事件确实到了。
  //
  // ★ 2026-10-05 改：原先只认 `JSON.parse(content).text`，于是**图文混排（post）在日志里
  //   一律打成 `原文=""`** —— 事故那天这一行读起来像「她发了一条空消息」，
  //   而真身是「一句话 + 一张图」，两者排查方向完全不同（这正是 `bodyToText` 09-22 修过的同一个病，
  //   只是当时代码路径没走到日志这一侧）。现在走同一份解析，并把**图几张**一起打出来。
  const parsedIn = feishu.bodyToText(msg.message_type, msg.content ?? '{}');
  const preview = parsedIn.text ?? '';
  const inImages = feishu.imageKeysOf(msg.message_type, msg.content ?? '{}').length;
  const mentionNames = (msg.mentions ?? []).map((m) => m.name).filter(Boolean);
  log(`★ 收到消息 chat=${chatId} msg=${msg.message_id}`);
  log(`   type=${msg.message_type} chat_type=${msg.chat_type} mentions=[${mentionNames.join(', ')}]`
      + (inImages ? ` 图=${inImages}张` : ''));
  log(`   原文=${JSON.stringify(preview).slice(0, 200)}`
      + (preview ? '' : (inImages ? '（正文为空，但带图 —— 图的内容由内核读）' : `（${parsedIn.note ?? '解析不出正文'}）`))
      + (msg.parent_id ? ` ｜回复 ${msg.parent_id}` : ''));

  if (DUMP_ONLY) { log('   （--dump-only 模式，不回复）'); return; }

  // ★ **每条消息都记下「最近来过消息的群」**（2026-09-22 补）。
  //
  // 为什么必须有这一行：`resolveChat()`（主动告警往哪儿发）的语义是
  // 「优先用最近来过消息的那个群，取不到才问一次接口」。而原先 `saveChatId` 只在
  // **检查被触发时**才调（`baselineWatch` / `pendingWatch`），检查一天才跑一次 ——
  // 于是那句「最近来过消息的群」实际是「**最近一次触发检查时所在的群**」，
  // 可能已经是几天前的了，而不匹配时它会**静默回落到接口的第一个群**。
  // 一条主动告警发错群，说出口的话就收不回来（§2.4.2：对外说过的话优先）。
  // 记在这里才是那句话的字面意思，而且它自维护 —— 不依赖谁记得去调。
  saveChatId(chatId);

  // 群里被推了飞书文档/维基链接 → 顺手核一次上游基线（**不阻塞回话**）。
  // 为什么挂在这里：她 2026-09-21 10:42 就是这么把 PRD 推进来的 —— 推链接是这条链路上
  // 唯一一个"上游有新东西"的可观测信号。
  if (LARK_DOC_RE.test(preview)) void baselineWatch('link', chatId);

  const t0 = Date.now();
  // ★★ 2026-10-23（Owner 原话：「守衡处理中都 8 分钟了，还没回复」）—— **中途说一声**。
  //   病灶：那一单在链里**静默了 9 分 9 秒**（4B 联网核查的请求发出去就不回来），
  //   群里从头到尾只有那张「⏳ 处理中…」。它既不说进度、也不说卡点，读的人只能猜「是不是死了」。
  //   口径：
  //     · 只发**一条**（到点一次），不轮询、不刷屏；
  //     · 跑完/出错/超时都会 `clearTimeout`，所以正常情况下群里**看不到**这条；
  //     · 说的必须是**真话**：卡在哪、还会不会继续等、等不到会怎样 —— 与那句
  //       「请重新发送原图」「请在…证据齐全后重新审核」是同一类错误的解药：
  //       **把读者能做与不能做的事分开写清**。
  const PROGRESS_MS = Number(process.env.SHOUHENG_PROGRESS_PING_MS || 5 * 60_000);
  const progressTimer = PROGRESS_MS > 0
    ? setTimeout(() => {
        void replyTo(chatId, msg.message_id,
          `【⏳ 还在跑】这一单已经跑了 ${Math.round(PROGRESS_MS / 60000)} 分钟，慢在知识库比对那一步。\n`
          + `有结论我立刻回你；到 ${Math.round(KB_REVIEW_TIMEOUT_MS / 60000)} 分钟还没结论，`
          + '我会停下来把卡在哪写清楚，并自动排进补发队列。\n'
          + '你不用催，也不用重发这张图 —— 卡点在我这侧。',
          msg.chat_type, 'chain-progress').catch(() => {});
      }, PROGRESS_MS)
    : null;
  if (progressTimer && typeof progressTimer.unref === 'function') progressTimer.unref();
  let result;
  try {
    result = await handleMessage(data, {
      // ★ 送审链要跑 6~30 分钟 —— 一开始先回一句，否则对方以为它没动
      //   （09:22 那次就是：她发完视频等了半天，收到的是一段「我读不了」）。
      //   形态决策仍然只有 `replyTo` 一处（§2.5），所以这里走同一个 safeSend。
      // ★ 2026-10-05 改：回执走 `replyTo`（引用她那条消息）而不是 `safeSend`。
      //   两个理由，都不是风格问题：
      //     ① 内核递过来的是**卡片块**（`[[card:receipt]]` + JSON），成形与字段校验
      //        只在 `envelope` 一处做（§2.5：形态决策只能有一处）；`safeSend` 走的是纯 markdown，
      //        会把那个块**原样当字符串发出去**，群里看到的就是一段 `[[card:receipt]]{...}`。
      //     ② 截图那张「⏳ 处理中…」是**引用她消息**的一条卡片 —— 回执属于「回答某一条」，
      //        不是主动喊话，`replyTo` 正是那一条路径（它还负责降级与台账）。
      notify: (text) => replyTo(chatId, msg.message_id, text, msg.chat_type, 'chain-ack'),
      // ★★ 2026-10-20（Owner 批准 ②）：**PRD §12 的计时起点在这里交出去**。
      //   以前这条路不传（`handleMessage` 默认 `null`，闸门里退化成"进闸门那一刻"），
      //   于是那条 ≤5 秒的指标结构上不可能红 —— 详见 `ingressMsOf` 的头注。
      tIngress: ingress.at,
      tIngressOrigin: ingress.origin,
    });
  } catch (e) {
    clearTimeout(progressTimer);
    counters.failed++;
    log(`   ✗ 内核异常: ${e?.stack ?? e?.message ?? e}`);
    await safeSend(chatId, `我处理这条消息时内部出错了，没能回答。\n\n错误：${e?.message ?? e}\n\n（已记录，这是我的问题。）`,
                   'error-fallback', msg.chat_type);
    return;
  }
  clearTimeout(progressTimer);   // 跑完了就别再发进度（发了就是假读数）
  const ms = Date.now() - t0;

  if (!result.reply) {
    counters.skipped++;
    log(`   · 不回复（${result.reason}）`);
    return;
  }

  counters.handled++;
  const trace = result.meta?.toolTrace ?? [];
  if (trace.length) log(`   🔧 工具: ${trace.map((t) => `${t.tool}${t.ok ? '' : '✗'}(${t.ms}ms)`).join(' → ')}`);
  // ★ 2026-10-08 加：「链只跑一次」那条护栏自己的读数。
  //   起因是一次真实事故（Owner 19:08 那张图）：`🔧 工具: kb_review_chain(709739ms)`
  //   明明在闸门跑完 2.5 分钟之后又跑了一遍，人等了 15 分钟 ——
  //   而**这一行本身看不出它是重复的**（709739ms 只说明它慢，不说明它多余）。
  //   有这一行，重复跑从此有读数；没有它，「护栏到底有没有生效」只能靠猜。
  const cm = result.meta?.chainMemo;
  if (cm?.hit) {
    log(`   ♻️ 链缓存命中 ${cm.hit} 次（同一轮里模型又调了 kb_review_chain —— `
      + '已回缓存不重跑；没有这一行它会再花 5~15 分钟并重复写一次飞书）');
  }
  // ★ 2026-10-05 加：**「媒材读到了、却一次链都没起」这个形状现在有读数了。**
  //   那次事故的全部盘上痕迹，就是上面那行 `🔧 工具:` **没有出现** ——
  //   而「一行没出现的日志」不是判据（§2.4.1：判据没盖住的那一跳，就是事故所在的那一跳）。
  //   所以这里每轮问一次：带了图/视频却没成功起过 kb_review_chain → 打一行 ⚠。
  const noChain = mediaWithoutChain(result.meta);
  if (noChain) {
    log(`   ⚠ 该送审却没起链：闸门=${JSON.stringify(noChain.gate)}｜媒材 ${noChain.media} 个`
      + `｜闸门起链=${noChain.chainTried ? (noChain.chainOk ? '跑成' : '没跑成') : '没起'}`
      + `｜本轮工具=${noChain.tools.join(',') || '（一个都没调）'}`
      + ' —— 对方要的是结论，不是「我读到了什么」');
  }
  if (result.meta?.compacted) {
    // ★ 2026-09-22 改：这块**原先无条件**说「+ 纪要」，而 `meta.summary` 就在手边
    //   （写出来之后**从来没有一个地方读过它** —— §2.4 那个病的又一个实例）。
    //   实测：三个会话的 `summary` 全是 0 长度，而日志里印了 8 次「保留 N 轮 + 纪要」。
    //   真相是压缩把旧对话**删掉了但什么都没留下**，而这句话让人以为留下了。
    //   现在按真实字符数分流：有纪要才说「+ 纪要」，没有就说清「纪要为空」。
    const sc = result.meta.summary_chars ?? 0;
    // ★ 2026-10-08 改：`turns` 与「条数」原先**是同一个数**
    //   （内核里写的是 `turns: sess.messages.length`），于是日志印着
    //   「保留 130 轮」而真相是 **130 条 ≈ 24 轮**（`config.llm.maxTurns`）。
    //   与上面那段是同一个形状：**这句话说得比手上的依据大**（§2.4.3）。
    //   现在两个数一起印，各自名副其实；取不到就说「未测」，不拿轮数冒充条数
    //   （§2.2 第 7 条：靠外部读数取不到时必须说未测，不许空着也不许当成 0）。
    const tn = result.meta.turns ?? null;
    const mc = result.meta.messages ?? null;
    const held = tn === null ? '⚠️ 轮数未测'
      : (mc === null ? `${tn} 轮（条数未测）` : `${tn} 轮（${mc} 条）`);
    log(sc > 0
      ? `   🗜 历史已压缩（保留 ${held} + 纪要 ${sc} 字）`
      : `   🗜 历史已压缩（保留 ${held}）⚠️ 纪要为空 —— `
        + '旧对话已删且未留下摘要，这是故障不是省事，见 PMO/logs');
  }
  if (result.meta?.truncated) log('   ⚠️ 回复被长度上限截断（已附截断说明，不是完整回答）');
  // ★ 2026-09-30 加：走过兜底合成就要说出来 —— 这一轮的回答是**折叠工具返回体之后重写的**，
  //   质量与正常轮不同（依据只剩结构摘要）。不写这一行，事后看日志会以为它是正常回答。
  if (result.meta?.synthesized) {
    log(`   ↺ 兜底合成：${result.meta.synthesized === 'empty-length'
      ? '模型烧光额度没写出正文 → 已折叠工具返回体、关掉工具重写一次'
      : '工具循环跑满 → 已折叠工具返回体、关掉工具让它用手上的材料作答'}`);
  }
  if (result.meta?.outbound?.folded) log(`   ↩ 本轮补记外发 ${result.meta.outbound.folded} 条进会话记忆`);
  if (result.meta?.outbound?.untested) log(`   ⚠️ 补记外发未测：${result.meta.outbound.untested}`);

  // ── 答不上 → 入补发队列（Q1-1d）。
  // 「断在哪一层」由 `llm.mjs` 的 `describeError` 给（`meta.llm.layer`），
  // 这里只负责把它连同「哪条消息、哪个群、问的什么」记下来。
  // **只对可重试类失败入队**：HTTP 4xx（鉴权/参数/配额）补发 5 次也是白试。
  //
  // ★ 三种失败都要入队（2026-10-06 补第三种）：
  //   `llm_error`      —— 模型这一拍没调通；
  //   `tool_exhausted` —— 调通了但工具循环跑满、始终没给出最终答复（走兜底话术）。
  //   `chain_not_run`  —— **送审单起了链、链却没跑成**（库忙 exit 3 / 超时 / 层前置红 /
  //                       依据侧没给结论）。它有回复（「这一单未测」），所以 `reason` 本来是
  //                       `ok` ⇒ 这里收不到它 ⇒ **连队都没进** ⇒ 那张图那条视频
  //                       「问一次答不上，问十次还是答不上」。
  //                       与 09-22 补 `tool_exhausted` 是**同一个病**，只是长在送审这条路上
  //                       （Owner 2026-10-06：「每次发图片/视频都必须能正常回复，不能拒答」）。
  if (result.reason === 'llm_error' || result.reason === 'tool_exhausted'
      || result.reason === 'chain_not_run') {
    const m = result.meta?.llm ?? {};
    const item = retryQueue.itemFromEvent(data, { error: result.reply?.slice(0, 200), layer: m.layer });
    if (!item) log('   ⚠ 失败入队未测：事件里抽不出 message_id/chat_id');
    else {
      // 工具跑满 / 链没跑成**都不是**网络问题：`retryable` 只对 `llm_error` 才由层决定。
      // 补发值不值得？值得 —— 补发是**换一条路重跑**（`answer` 会重跑内核），
      // 而库忙、超时、层前置都是**随时间变化**的状态：同一句话隔几分钟再跑很可能就通了。
      const retryable = (result.reason === 'tool_exhausted' || result.reason === 'chain_not_run')
        ? true : m.retryable === true;
      const enq = retryQueue.enqueue({ ...item, retryable });
      log(`   ↻ ${result.reason === 'chain_not_run'
              ? '送审单但链没跑成（库忙/超时/层前置红）'
              : (result.reason === 'tool_exhausted'
                 ? `工具循环跑满（${result.meta?.toolTrace?.length ?? 0} 次调用）`
                 : `模型失败（层=${m.layer ?? '未知'}）`)}，可重试=${retryable} → `
          + (enq.ok ? `已入补发队列（${enq.size} 条）` : `未入队：${enq.why}`));
    }
  }

  // ── 形态决策**不在这里**。（2026-09-22 改）
  // 原先这一块是 `const shaped = toCardOrText(result.reply)`，然后只把 `shaped.card`
  // 传进 `replyTo` —— 于是「谁能定形态」有两个答案：`AGENTS.md` §2.5 说只在 `replyTo`，
  // 代码却在 `onMessage`。**两处都能定形态，错位的表现是群里格式随机**，
  // 而这正是 §2.5 存在的理由。现在这里只把模型的原文交下去，由 `replyTo` 一处决定。
  log(`   💬 回复 ${result.reply.length} 字，耗时 ${ms}ms`);

  // ★ 2026-10-06：把**权威结论行**（PRD §5.3）一路交到 `toCardOrText`。
  //   它是唯一知道「这一轮链给了哪一行」的地方（`meta.verdict53` 由内核算出），
  //   而形态决策仍然只在 `replyTo` 一处做（§2.5）—— 这里只是**递读数**，不定形态。
  const sent = await replyTo(chatId, msg.message_id, result.reply, msg.chat_type, 'reply',
    { verdict53: result.meta?.verdict53 ?? null,
      // ★ 2026-10-22（Owner：「输出的卡片不展示 视觉分析与 OCR」）：
      //   `imageAnalysis` **不再往下传** —— 与 2026-10-13 撤 `mediaRead` 同一条口径：
      //   读数留在日志、会话记忆、报告附录，**都不上卡**；留一个没人读的入参
      //   就是「传了但没人接」那个病（§2.4.4），所以内核那一格也一并撤了。
      // ⚠️ 2026-10-13：`mediaRead` **不再往下传** —— 媒材读数按 Owner 的要求不上卡了
      //   （`envelope.toCardOrText` 那个入参也一并撤掉，免得留下一个没人读的入参）。
      //   读数本身没丢：内核的 `📥 读到｜…` 日志、会话记忆、报告附录三处都在。
      // 2026-10-09: 报告链接 —— 与 mediaRead 同级（都进可见格，都不该藏在折叠区里）
      reportLink: result.meta?.reportLink ?? null });
  // ⚠️ 2026-10-13：`boundary`（卡脚那条边界）**不再往下传** —— Owner 要求
  //   「整个都隐藏，不要展示在卡片上」。它改走 `dual_track.internalNotes`（记忆侧），
  //   于是「未跑专项审查 / 仍需转对应专项复核」这句话**守衡答得出来**，只是不上卡。
  if (sent.ok) { counters.replied++; log(`   ✓ 已发送 ${sent.messageIds.filter(Boolean).join(', ')} [${sent.mode}]`); }
  else { counters.failed++; log(`   ✗ 发送失败: ${sent.error}`); }

  // ★★ 2026-10-21（Owner：「P0 红线问题必须 10 秒内回」）——
  //   **P0 确定性命中那一路的用户实测延迟**（消息 `create_time` → 卡片发出去为止）。
  //
  //   为什么这条读数非有不可（AGENTS.md §2.4：写进文档的上限必须能指出哪一行在量它）：
  //     · 旧世界里 P0 单 p50 **62.1 s**（min 27.3 / max 382），而**没有任何一行**在量它 ——
  //       `group_response_ms` 量的是「⏳ 处理中」那张回执（≤5 s 那条），不是结论；
  //     · 现在命中即停后续审查、直接出结论卡（`result.meta.p0Direct`），这条路必须自带读数，
  //       否则「10 秒」就只是一句话（本仓禁的形状）。
  //   ⚠️ `verdict` 只在**真发出去了**之后才算数：没发出去时写 `FAIL`（那不是"快"，是没送到）。
  //   ⚠️ 起点用 `create_time`（飞书服务端盖的），来源写进 `ingress=` —— 两个来源不许混着说。
  if (result.meta?.p0Direct) {
    const directMs = Date.now() - ingress.at;
    const okNow = directMs <= 10000 && sent.ok;
    log(`[metric] direct_answer_ms=${directMs} prd_limit_ms=10000`
      + ` verdict=${okNow ? 'pass' : 'FAIL'} stage=p0-direct`
      + ` ingress=${ingress.origin} sent=${sent.ok ? 'ok' : 'fail'} chat=${chatId}`);
  }
}

/**
 * 补发队列（Q1-1d）：**答不上，不再等于永远答不上。**
 *
 * 判据与幂等全在 `agent/retry_queue.mjs`（三重：队列键 / 台账已答 / 记忆已答），
 * 这里只做两件它做不了的事：
 *   · `answer` —— **重跑内核**（补发的是答案本身，不是一句预先写好的话）；
 *   · `send`  —— 真发出去，且**只走 `replyTo`**（形态决策一处做，§2.5；
 *                发送者仍是本文件 —— `verify_outbound.py` 那张「谁能发消息」的总表不用加行）。
 *
 * 两条纪律：
 *   · **每拍最多补一条** —— 补发那一步本身就是一次模型调用，网络刚好时几条一起补
 *     是三倍花费，而它们已经等了十几分钟，再等 5 分钟不改变什么；
 *   · **失败绝不往群里灌第二条** —— 补发失败只累加次数，到上限落死信、只在日志说。
 */
let retryBusy = false;
async function retryWatch(reason) {
  if (retryBusy) { log('   · 补发跳过（上一拍还在跑）'); return; }
  retryBusy = true;
  try {
    const r = await retryQueue.runTick({
      log,
      answer: (it) => handleMessage(it.event, { force: true }),
      send: (it, text) => replyTo(it.chat_id, it.message_id, text, it.chat_type, 'resend'),
    });
    if (r.acted) {
      log(`   · 补发[${reason}] ${r.sent ? '✓ 已补发' : `未发出（${r.why ?? '仍需等待'}）`}，队列剩 ${r.left} 条`);
    }
  } catch (e) {
    log('   ⚠ 补发自身出错（不影响回话）:', e?.message ?? e);
  } finally { retryBusy = false; }
}

/**
 * 外部标准库（62 条引文）的上游漂移：**触发 + 通报**（`agent/external_watch.mjs` 是判据）。
 *
 * 为什么要有它：`verify_external.py` 早就能回答「那 62 条在上游还逐字对得上吗」，
 * 也有归档、清单和漂移段 —— **缺的是「谁在跑」**。PRD 那篇改了有人会知道，
 * FDA / Amazon / Meta 的政策页改了，此前**我们不会知道**，而这 62 条是要给法务当依据的。
 * 这是 `AGENTS.md` §2.4.2 那个病的最后一个实例。
 *
 * 与 `baselineWatch` 同两条纪律：不阻塞回话（调用点是 `void`）、**未测不得沉默**。
 * ⚠️ 它**会动盘**（真抓 + 写证据层 + append 清单），所以带 3 小时冷却 —— 重启不重抓。
 */
async function externalWatch(reason, chatId) {
  try {
    if (chatId) saveChatId(chatId);
    const r = await checkExternal({ reason });
    if (r.skipped) { log(`   · 外部标准库检查跳过（${r.skipped}）`); return; }
    log(`   · 外部标准库[${reason}] 退出码 ${r.code} · ${r.verdict} —— ${r.why}`
        + (r.note ? ` · ${r.note}` : ''));
    if (!r.say) return;
    const target = chatId ?? await resolveChat();
    if (!target) {
      log('   ⚠ 外部标准库有话说，但还没有可通报的群 —— 只进日志（退 2 不许沉默）');
      return;
    }
    await safeSend(target, r.say, 'proactive-external');
    log(`   · 外部标准库告警已发到 ${target}`);
  } catch (e) {
    log('   ⚠ 外部标准库检查自身出错（不影响回话）:', e?.message ?? e);
  }
}

/**
 * 把**被拦下没发出去**的原文落到 `PMO/logs/dropped/`。
 *
 * 存在理由只有一条：拒答话术对用户说「原始内容留在 PMO/logs」——
 * 这句话必须是真的。见 `replyTo` 里那段注释。
 *
 * 落盘配方按 `AGENTS.md` §2.1：**用 Node 写**（不是 Python），所以不会进
 * 「stat 比真实内容多 4096 字节」的填充态；`.md` / `.sh` 那两格才需要 `depad` 往返，
 * 这里写的是 `.txt`，本就在安全格内。
 *
 * 失败**不许**影响回话：写不进去就只记日志（已经没发出去的东西，不能再拖垮发送）。
 */
function dumpDropped({ messageId, chatId, source, reason, raw }) {
  try {
    const dir = path.join(LOG_DIR, 'dropped');
    ensureDir(dir);
    const at = new Date().toISOString();
    const name = `${at.replace(/[:.]/g, '-')}-${String(messageId ?? 'nomsg').replace(/[^\w-]/g, '')}.txt`;
    fs.writeFileSync(path.join(dir, name),
      `# 被拦下没发出去的原文\n`
      + `at: ${at}\nmessage_id: ${messageId ?? '(无)'}\nchat_id: ${chatId ?? '(无)'}\n`
      + `source: ${source ?? '(无)'}\n原因: ${reason ?? '(无)'}\n`
      + `${'─'.repeat(60)}\n${raw ?? ''}\n`);
    log(`   📥 原文已留证：PMO/logs/dropped/${name}（${[...String(raw ?? '')].length} 字）`);
  } catch (e) {
    log(`   ⚠ 原文留证失败（不影响回话）：${e?.message ?? e}`);
  }
}

/**
 * 发送一条回复。这是**唯一**的格式决策点 —— 也是**唯一**的形态决策点。
 *
 * ★ 形态决策（卡 vs 纯文本）在这里做，参数收的是**模型的原文**，不是已经定好形态的结果。
 *   `AGENTS.md` §2.5：「这个判断只允许在 `replyTo` 里做」。2026-09-22 之前它其实在
 *   `onMessage` 里（`toCardOrText` 在那边调），`replyTo` 只收 `card` —— 两处都碰形态。
 *   现在 `onMessage` 只记一行日志，形态的输入与输出都收在本函数内。
 *   「模型选了哪种形态、有没有被搬迁、有没有踩到 AI 味」仍然全部进日志 ——
 *   否则调模版就只能靠重跑猜。
 *
 * 降级链只有一条，且每一步都有明确的失败原因记录：
 *
 *   有卡片 → reply 卡  ──失败──→ reply 纯文本（正文 = 卡的降级文本）
 *   没有卡 → reply 纯文本 ──失败──→ sendMarkdown 补发
 *
 * ★ 为什么卡片的降级目标也是 reply（而不是 sendCard 新发一条）：
 *   新发一条会断开引用关系 —— 群里看到的是一段悬空的话，不知道在答谁。
 *   守住「引用」比守住「卡片」重要。
 * ★ 为什么每一步都要把原因写进正文：对方看到格式变了，得知道是为什么，
 *   而不是以为守衡改了风格。这是 2026-09-17 那次故障的直接教训 ——
 *   当时它对着一堆内部记录说「✓ 已发送」。
 */
async function replyTo(chatId, messageId, rawReply, chatType = null, source = 'reply',
                       { verdict53 = null, reportLink = null } = {}) {
  // ★ 结论行的**兜底派生**（2026-10-06）：补发队列那一跳（`source='resend'`）走的是
  //   `handleMessage(event, {force:true})`，它**不跑送审闸门**，所以拿不到 `meta.verdict53`。
  //   判据很窄 —— 只有模型自己把一行 5.3 结论**摆在回复最前面**时才认它
  //   （`prd53.leadsWith`）。宁可在这一路上漏搬，也不许把「有人在问 5.3 模板长什么样」
  //   那句回答误当成一条审查结论。
  const v53 = verdict53 ?? deriveVerdictLine({ replyText: rawReply });
  // ★ `mediaRead` 不走兜底派生：它是**内核已经算好的读数**，拿不到就是没有（不猜）。
  // ★★ 2026-10-13（修一个真缺陷）：`reportLink` **原先在这里被丢掉** ——
  //   调用方（`onMessage`）一路传了 `reportLink: result.meta?.reportLink`，
  //   而本函数的解构签名里**没有它** ⇒ 静默丢弃。
  //   旧判据（`test_agent.mjs` 的 Z20）只查了**源码里出现过**
  //   `reportLink: result.meta?.reportLink` 这一行，**没查它真被用上** ——
  //   又一个「名字出现过 ≠ 它拦得住」（§2.4）。现在有行为级判据钉着（Z20b）。
  const shaped = toCardOrText(rawReply, { verdict53: v53, reportLink });
  if (v53) {
    // ★ 措辞不合 5.3 时**出声**：链是结论行的产者，它的措辞会回退，
    //   而回退的表现只是「群里格式不对」—— 那要等到人看见才知道。
    //   这一行让 `PMO/logs/ws_daemon.log` 里能直接查到「哪一条、哪一态、为什么不合规」。
    const c = v53.conform;
    const v = shaped.verdict53 ?? {};
    const blk = v.block ? `${v.block.action}·${v.block.slot ?? '-'}` : '无';
    log(`   📋 PRD §5.3 结论行：${v53.state}（来自 ${v53.from}）`
        + `｜落点=${v.action ?? 'n/a'}·${v.slot ?? '-'}`
        + `｜逐条块=${blk}`
        + `${c && !c.ok ? ` ⚠️ 措辞不合 §5.3：${c.why}` : ''}`);
  }
  for (const m of shaped.moved) log(`   ↪ ${m.field} → ${m.to}（${m.why}）`);
  for (const h of shaped.lint) log(`   ${h.level === 'error' ? '❌' : '⚠️ '} 语域 ${h.id} ×${h.count} ${h.sample}`);
  if (shaped.mode === 'card') log(`   🃏 卡片 ${shaped.kind} · ${shapeOf(shaped.card)}`);
  else if (shaped.dropped) log(`   ⚠️ 卡片降级为文本：${shaped.reason}`);

  // ★ 被拦下的原文落盘（2026-09-22 加）。
  //   为什么必须有这一步：拒答话术里写着「**原始内容留在 PMO/logs**」，
  //   而那句话说出去的时候，**盘上什么都没有** —— 实测 16:34 那次，
  //   `PMO/logs/` 里没有任何新文件，那句话是一句假承诺（§2.4.2 的形状：
  //   承诺里出现的每个名词都要指得出哪一行在做它）。
  //   现在它有了执行点：本条分支就是那一行。原文还留在会话记忆里，但记忆会被压缩，
  //   日志会轮转，只有这里的落盘是「按事故留证」的。
  //   `verify_cards.mjs` 的 **L7** 断言这一步真的接在 `dropped` 分支上。
  if (shaped.dropped) dumpDropped({ messageId, chatId, source, reason: shaped.reason, raw: rawReply });

  const text = shaped.text;
  const card = shaped.card ?? null;

  // ★ 2026-09-22 改成「先把结果收进 `sent`、出口只有一个」。
  //   原先每个分支各自 `return`，于是**留痕要写在四个地方**，漏一处就是一条消息
  //   在台账里查不到 —— 而漏掉的那一处不会有任何东西变红。
  //   现在无论走哪条降级链，出口只有一个，`recordOutbound` 只可能被调一次、
  //   也不可能被跳过（`verify_outbound.py` 的 F 段扫这一段的结构）。
  let sent;
  if (card) {
    const rc = await feishu.replyCard(messageId, card);
    if (rc.ok) {
      sent = { ok: true, messageIds: [rc.messageId], mode: rc.mode };
    } else {
      log(`   ⚠ 卡片 reply 失败（${rc.error}），退成同一条引用里的纯文本`);
      const rt = await feishu.replyMarkdown(messageId, chatId, text);
      sent = rt.ok ? { ...rt, mode: `card-failed→${rt.mode}`, error: rc.error } : rt;
    }
  } else {
    const r = await feishu.replyMarkdown(messageId, chatId, text);
    if (r.ok) {
      sent = r;
    } else {
      log(`   ⚠ reply 失败（${r.error}），改为直接发送`);
      sent = await feishu.sendMarkdown(chatId, text);
    }
  }

  // 留痕。**发失败也记**（`ok:false`）—— 台账要能回答「我们试过没有」，
  // 而不只是「成功过没有」；折进会话记忆的那一步会跳过 `ok:false`（见 outbound.mjs）。
  //
  // ★ `source`（2026-09-22 加）默认 `reply`，补发那一路传 `resend`。为什么必须有这个参数：
  //   「谁答的」在台账里要分得出来 —— `resend` 是**晚十几分钟的补答**，它还要参与
  //   补发队列的三重幂等（`retry_queue.mjs` 的 ②）。两种来源在折记忆时都不折
  //   （见 outbound.mjs 的 `NON_FOLDING`），但它们在台账里必须长得不一样。
  // ★ 2026-10-14：把「**真的发出去了什么**」记进台账（`extra.delivery`）。
  //   为什么必须有这个读数：台账里存的是**模型原文**，而摘符号发生在**发送那一跳** ——
  //   于是「台账那行带 `**`」与「对方看到星号」是**两件不同的事**。
  //   实测踩到（我自己写的判据 H1 就是被这个坑红的）：
  //     `06:44:02Z` 那条 `mode=reply` 台账正文带 8 个星号，**而飞书侧读回来是 0 个**
  //     （`GET /im/v1/messages/{id}`，`star_count=0`，类型 `post`）。
  //   ⇒ 判据要断的是**投递事实**，不是原文长什么样。这一格就是那个事实的唯一来源。
  sent.delivery = { starsRemoved: ((text.match(/\*/g) ?? []).length) - ((plainify(text).match(/\*/g) ?? []).length),
                    sentText: plainify(text) };
  recordOutbound(chatId, sent, { text, source, replyTo: messageId, chatType });
  return sent;
}

/**
 * 主动发送（不属于「回答某一条」的那些话）：基线告警、待收到期提醒、崩溃自报、
 * 进群自我介绍、出错兜底。
 *
 * @param {string} source  这条外发的**性质**，封闭集合见 `agent/outbound.mjs` 的 `SOURCES`。
 *                         刻意**不给默认值** —— 少传一个参数会记成 `unknown:`，
 *                         那在台账里看得见；给个默认值则会静默记成别的东西。
 */
async function safeSend(chatId, text, source, chatType = null) {
  try {
    const sent = await feishu.sendMarkdown(chatId, text);
    // 主动推送同样记「真的发出去了什么」（post 转换器保证不带字面星号；降级支靠 plainify）
    sent.delivery = { starsRemoved: ((text.match(/\*/g) ?? []).length) - ((plainify(text).match(/\*/g) ?? []).length),
                      sentText: plainify(text) };
    recordOutbound(chatId, sent, { text, source, chatType });
  } catch (e) { log('   ✗ 兜底发送也失败:', e.message); }
}

/**
 * 记一条外发到台账（`PMO/logs/ws_outbound.jsonl`，判据在 `agent/outbound.mjs`）。
 *
 * ★ 为什么这件事必须做，而且必须在这里做：
 *   2026-09-22 14:39 那次误答的直接成因之一，是**守衡不记得自己问过什么** ——
 *   而它 14:37:55 问的那一句，是 `send_once.mjs` 手发的，**盘上没有任何痕迹**
 *   （只有 stdout 里一个 `message_id`，以及我事后手抄进文档的时刻）。
 *   于是「她答的是哪一句」在盘上根本无从判起。
 *
 * ★ 台账写不进去**不许影响发送**（与 `dumpRaw` 同一条纪律：日志坏掉不该让服务坏掉），
 *   但也不许静默 —— 它一定要在日志里留一行，因为那意味着**这条消息在台账里查不到**。
 */
function recordOutbound(chatId, sent, { text, source, replyTo = null, chatType = null }) {
  const ids = sent?.messageIds ?? (sent?.messageId ? [sent.messageId] : []);
  const r = outbound.recordSend({
    chatId, chatType, messageIds: ids, text, source,
    mode: sent?.mode ?? null, replyTo,
    ok: sent?.ok !== false, error: sent?.error ?? null,
    // ★ `delivery` = 「发出去的那份正文」的读数（见 `replyTo` 里那段注释）。
    //   没给就是**没记**，判据据此落「未测」而不是「通过」。
    extra: sent?.delivery ? { delivery: { starsRemoved: sent.delivery.starsRemoved,
                                          sentHasStar: /[*]/.test(sent.delivery.sentText) } } : null,
  });
  if (!r.ok) log(`   ⚠ 外发留痕失败（${r.error}）—— 这条消息在台账里查不到`);
  return r;
}

/**
 * 上游 PRD 基线漂移：**触发 + 通报**（`tools/agent/prd_baseline.mjs` 是状态机与判据）。
 *
 * 为什么要在常驻链路里做：2026-09-21 11:52 守衡在群里对上游承诺「改版后得重新拉一次基线
 * 并记新指纹」，当天补出了 `tools/verify_prd_baseline.py` —— 但**那是"命令存在"，
 * 不是"谁在跑"**。没人跑的检查器，和一句没执行点的承诺是同一个形状。
 *
 * 两条纪律写在这里：
 *   1. **不阻塞回话**：调用点全是 `void`，出错只记日志，绝不影响正常回答。
 *   2. **未测不得沉默**：退 2 会说话，且文案里不许出现"没问题"（判据在 prd_baseline 的
 *      `stripNegated` + 离线自测第 6/7/8 条）。
 */
async function baselineWatch(reason, chatId) {
  try {
    // ★ `saveChatId`，不是 `saveState({ ...loadState(), lastChatId })` —— 后者有两个毛病：
    //   ① `saveState` 默认写的是**基线那份状态文件**，而这里连待收那条链路也走同一个调用，
    //      于是「待收」在写「基线」的文件，还靠 `{ ...loadState() }` 把陈年 `p_*` 键一路带下去；
    //   ② 它住在基线检查的 read→跑子进程（最长 90 秒）→write 窗口里，会被旧快照抹掉。
    if (chatId) saveChatId(chatId);
    /**
     * ★ **目标群在跑检查之前就定下来，并作为 `chatId` 传进状态机。**（2026-09-22 加）
     *
     * 原先的顺序是「先跑检查、之后才 `chatId ?? await resolveChat()`」，于是：
     *   · `[link]` 触发的告警发到**链接所在的那个群**；
     *   · 几十分钟后的收尾走 `resolveChat()`，而它读的是「**最近来过消息的群**」——
     *     这中间群里正常问答过，那个值早就翻页了。
     * 实测后果就是两个群各收到一半：`oc_49a7…` 收到「请给我一分钟重拉一次基线」却
     * **永远收不到收尾**；`oc_7775…` 从没收到过告警，却收到一句「✅ 恢复了」。
     * 详见 `prd_baseline.mjs` 里 `alertChat` 那段。
     *
     * 现在把「这次要说给哪个群」在**说话之前**定下来，让状态机把它连同「说过什么」一起记住；
     * 收尾时状态机用 `sayTo` 把地址还回来，优先级高于 `target` **也高于** `resolveChat()`。
     */
    const target = chatId ?? await resolveChat();
    const r = await checkNow({ reason, chatId: target });
    if (r.skipped) { log(`   · 基线检查跳过（${r.skipped}）`); return; }
    log(`   · 基线检查[${reason}] 退出码 ${r.code} —— ${r.why}${r.note ? ` · ${r.note}` : ''}`);
    if (!r.say) return;
    // ★ `sayTo` ＝「当初那条告警去过哪个群」。即使 `target` 取不到，收尾也回得去。
    // ★ 优先级只在 `pickAlertTarget` 里判一次（收尾地址 > 触发群 > 默认群）。
    const to = pickAlertTarget({ sayTo: r.sayTo, triggerChat: target });
    if (!to) {
      log('   ⚠ 基线检查有话要说，但还没有可通报的群 —— 只进日志（退 2 不许沉默）');
      return;
    }
    await safeSend(to, r.say, 'proactive-baseline');
    log(`   · 基线告警已发到 ${to}${r.sayTo ? '（收尾 —— 回到当初告警的那个群）' : ''}`);
  } catch (e) {
    log('   ⚠ 基线检查自身出错（不影响回话）:', e?.message ?? e);
  }
}

/**
 * 待收清单的到期提醒（判据在 `tools/verify_pending.py`，清单在 `PMO/待收清单-v1.json`）。
 *
 * 为什么要在常驻链路里做：`PRD/PRD差异对照-20260921.md` §五 记着上游 09-18 的承诺
 * 「其它已跟业务沟通接下来两周陆续整理提供」（→ 2026-10-02），而同一天那份对照表
 * **自己就写着「到期没人会提醒」**。这一层就是补上那个「谁在跑」。
 *
 * 与 `baselineWatch` 同两条纪律：不阻塞回话（调用点全是 `void`）、**未测不得沉默**。
 * 措辞上有一条额外的：**不 @ 任何人** —— 到期日是我方推算的，那是问一句，不是催办。
 */
async function pendingWatch(reason, chatId) {
  try {
    if (chatId) saveChatId(chatId);   // 理由同 `baselineWatch`：这里原先写的是**基线**那份状态文件
    // ★ 目标群先定、后跑检查 —— 与 `baselineWatch` 同一个理由（见那里那段）。
    //   这条今天是「将来时」：到期提醒的首次触发在 2026-10-02，而收尾若发到另一个群，
    //   那边的人会看到一句「现在没有到期未收」而不知道在说什么。同一个形状，一次修两处。
    const target = chatId ?? await resolveChat();
    const r = await checkPending({ reason, chatId: target });
    if (r.skipped) { log(`   · 待收检查跳过（${r.skipped}）`); return; }
    log(`   · 待收检查[${reason}] 退出码 ${r.code} —— ${r.why}${r.note ? ` · ${r.note}` : ''}`);
    if (!r.say) return;
    const to = pickAlertTarget({ sayTo: r.sayTo, triggerChat: target });
    if (!to) {
      log('   ⚠ 待收检查有话要说，但还没有可通报的群 —— 只进日志（退 2 不许沉默）');
      return;
    }
    await safeSend(to, r.say, 'proactive-pending');
    log(`   · 待收到期提醒已发到 ${to}${r.sayTo ? '（收尾 —— 回到当初告警的那个群）' : ''}`);
  } catch (e) {
    log('   ⚠ 待收检查自身出错（不影响回话）:', e?.message ?? e);
  }
}

/* ─────────────────────── 事件注册 ─────────────────────── */

// ★★ 2026-10-22：**非消息事件也必须「走完」计数**。
//
//   病灶（本轮审计发现，还没出过事故，但一定会）：`restart_shouheng.sh` 的「正在处理中」
//   判据是 `events > handled+skipped+failed+uncaught`（「有事件还没走完 ⇒ 现在重启会掐断它」）。
//   而下面三个 handler 原先**只 `events++`、从不记任何 done** ⇒ 只要收到过一次
//   `bot.added` / `bot.deleted` / `card.action.trigger`，`events` 就永远比 `done` 多 1，
//   闸门从此**永久**报「有 1 条还没走完、现在重启会掐断它」，也就永远拒绝重启 ——
//   下一个人只能被迫 `--force-inflight`，而那个开关存在的意义正是「不该被日常用到」。
//
//   三个事件的归属（按它们到底做了什么分，不是按名字）：
//     · `bot.added`  → 会发一句欢迎语（真干了活）⇒ `handled++`
//     · `bot.deleted`→ 只记日志（无事可做）    ⇒ `skipped++`
//     · `card.action.trigger` → 只记日志       ⇒ `skipped++`
//   两个删除/交互的分支都用 `try/finally` 记在**同一个 finally** 里：
//   中途抛异常也照样销账 —— 否则「崩了的那个事件」会把闸门永久卡死（比不计数更糟）。
//   判据在 `tools/verify_shouheng_ops.py` 的 **I 段**（含反向对照）。
const handlers = {
  'im.message.receive_v1': onMessage,

  'im.chat.member.bot.added_v1': async (d) => {
    counters.events++; dumpRaw('im.chat.member.bot.added_v1', d);
    try {
      log(`★ 被拉进群 chat=${d?.chat_id}`);
      const info = await feishu.getChatInfo(d?.chat_id);
      await safeSend(d?.chat_id,
        `我是守衡，已加入「${info?.name ?? '本群'}」。\n\n` +
        `我会在这个群里做的事：回答问题、查工作区里的资料、记住我们聊过的上下文。\n` +
        `@我 就能叫我。不 @ 我不会插话。`, 'greeting', 'group');
      counters.handled++;                    // 欢迎语发出去了 = 这条事件走完了
    } catch (e) {
      counters.failed++;                     // 发不出去也要销账，并把原因留成读数
      log('⚠ 欢迎语没发出去（这条事件仍算走完）:', e?.message ?? e);
    }
  },

  'im.chat.member.bot.deleted_v1': async (d) => {
    counters.events++; dumpRaw('im.chat.member.bot.deleted_v1', d);
    try {
      log(`★ 被移出群 chat=${d?.chat_id}`);
    } finally {
      counters.skipped++;                    // 无事可做，但不能不销账
    }
  },

  'card.action.trigger': async (d) => {
    counters.events++; dumpRaw('card.action.trigger', d);
    try {
      log(`★ 卡片交互 ${JSON.stringify(d).slice(0, 400)}`);
      // 卡片交互的回调应答需要返回 toast，这里先只记录；
      // 等真正做出交互卡片的业务场景时再接（不预先写没有调用方的代码）。
    } finally {
      counters.skipped++;                    // 同上：记了日志就等于这条走完了
    }
  },
};

/* ─────────────────────── 启动 ─────────────────────── */

log('='.repeat(74));
log('守衡 · 常驻入口 v3');
for (const [k, v] of Object.entries(describeConfig())) log(`  ${k.padEnd(24)} = ${v}`);
log(`  知识库根(KB_ROOT)       = ${KB_ROOT}`);
// ★ 2026-10-21：这一行是**事故驱动**加的。判据改在本仓 `内容治理知识库/`，而守衡读的是 KB_ROOT ——
//   群里复测仍 PASS，排查绕了一圈。库路径不许只活在 `tools.mjs:1235` 那一行常量里。
log(`  tools                 = ${loadedTools().join(', ')}`);
log(`  事件落盘              = ${path.relative(REPO_ROOT, EVENT_DUMP)}`);
if (DUMP_ONLY) log('  ⚠ --dump-only：只落盘，不回复');
log('='.repeat(74));

/* ───────────── 单实例闸门（2026-10-20 加）─────────────
 * 为什么放在**建连之前**：`--dump-only` 也要占名额（它同样写 ws_events.jsonl），
 * 而真正要防的是「两个进程同时连着飞书」。放到 `ws.start()` 之后，
 * 两个实例已经开始收事件了，闸门就只是事后通知。
 *
 * 判据与反向对照：`agent/single_instance.mjs` ＋ `agent/single_instance.test.mjs`（16/16）。
 * 退出码 75 = ex_tempfail：launchd `KeepAlive{SuccessfulExit:false}` 只在**非零**退出时拉起，
 * 于是新实例会在 `ThrottleInterval`（10s）后重试 —— **等旧的走干净**，而不是并排跑。
 */
const single = singleInstance.acquire();
if (!single.ok) {
  log(`✗ 另一个守衡还活着（${single.why}）—— 本进程不启动，退 ${singleInstance.EXIT_ANOTHER_INSTANCE}`);
  log('  为什么必须这样：两个实例同时在线 ⇒ 同一条消息被答两遍、两条链并行开两单、去重表互相覆盖。');
  process.exit(singleInstance.EXIT_ANOTHER_INSTANCE);
}
log(single.degraded ? `  ⚠ 单实例闸门降级：${single.why}`
                    : `  单实例闸门            = 已占位（pid ${process.pid}）`);

const dispatcher = new Lark.EventDispatcher({}).register(handlers);
const ws = new Lark.WSClient({
  appId: config.lark.appId, appSecret: config.lark.appSecret, loggerLevel: Lark.LoggerLevel.info,
  // ★ 2026-10-05 加：原先这四个回调**一个都没注册** —— 于是 SDK 把「连不上/重连耗尽」
  //   报给了空气，守衡静默失联而盘上全是绿的。现在每一次都改读数、并落一行日志。
  onReady: () => {
    wsState.connected = true; wsState.readyAt = Date.now();
    wsState.downSince = null; wsState.lastSignalAt = Date.now();
  },
  onReconnecting: () => {
    if (!wsState.downSince) wsState.downSince = Date.now();
    wsState.connected = false; wsState.reconnects++;
    wsState.lastSignalAt = Date.now();
    log(`  ⚠️ 长连接断了（第 ${wsState.reconnects} 次重连中）—— 恢复前群里发的消息收不到`);
  },
  onReconnected: () => {
    const down = wsState.downSince ? Math.round((Date.now() - wsState.downSince) / 1000) : null;
    wsState.connected = true; wsState.readyAt = Date.now();
    wsState.downSince = null; wsState.lastSignalAt = Date.now();
    log(`  ✓ 长连接已恢复${down === null ? '' : `（断了约 ${down} 秒）`}`);
  },
  onError: (e) => {
    wsState.lastError = String(e?.message ?? e);
    wsState.lastErrorAt = Date.now();
    wsState.lastSignalAt = Date.now();
    log(`  ❌ 长连接错误：${wsState.lastError}`);
  },
});

let shuttingDown = false;
async function shutdown(sig) {
  if (shuttingDown) return;
  shuttingDown = true;
  log(`\n收到 ${sig}，正在收尾…`);
  flushSeen();                                  // 把去重表落盘，重启后不会重复回话
  log(`本次统计：事件 ${counters.events} / 已回答 ${counters.handled} / 已发送 ${counters.replied} / 跳过 ${counters.skipped} / 失败 ${counters.failed} / 未捕获 ${counters.uncaught}`);
  // ★ 2026-10-20（单实例闸门的配套）：**先把长连接关掉，再释放名额**。
  //   顺序反了就是白做这道闸：名额一放，接班进程立刻起来建连，
  //   而这边 `ws.stop()` 还没返回 —— 两条连接并存的那几秒，同一个事件会被两边各处理一次，
  //   正是这道闸要防的东西。
  //   但也不能无限等：`ws.stop()` 在有链在飞时可能拖很久，拖住就等于把接班进程饿死
  //   ⇒ 8 秒上限，超时就照常释放并退出（那时本进程已经不再处理任何事）。
  try {
    await Promise.race([ws.stop?.(), new Promise((r) => setTimeout(r, 8000))]);
  } catch {}
  const rel = singleInstance.release();
  if (!rel.ok) log(`  ⚠ 单实例名额没释放成：${rel.why}`);
  process.exit(0);
}
/* ─────────── 未捕获异常：计数 + 越线在群里自报（**不退出**） ─────────── */

/**
 * ★ 为什么这两条钩子不能只记日志。
 *
 * 原先它们只 `log(...)`。后果是：进程带着**未知状态**继续在群里答话，
 * 而 launchd **永远不会**重启它 —— `KeepAlive{SuccessfulExit:false}` 只在
 * **非零退出**时拉起，而这两条钩子恰恰不退出。
 * 于是「我已经处于未定义状态」这件事唯一痕迹是一行 stdout，
 * 而它**和「一切正常」长得一模一样**（与 §2.7 记的
 * 「`kill -TERM` → `exit 0` → 不拉起」是同一个后果面）。
 *
 * 处置选的是「继续服务，但让未知状态被看见」，而**不是**退出交给 launchd：
 * 若异常是确定性的（每次启动就抛），退出会变成**重启风暴**，
 * 而重启窗口里的群消息会被吃掉且事后补不回来 —— 正是 §2.7 要防的那件事。
 *
 * 窗口：同一分钟内累计到 `UNCAUGHT_REPORT_AT` 自报一次，之后每满一个窗口
 * 再自报一次（不是只报第一次）—— 一条持续报错既不刷屏，也不会报过一次就永远闭嘴。
 */
const UNCAUGHT_REPORT_AT = 3;
const UNCAUGHT_WINDOW_MS = 60_000;
let crashWindow = { start: 0, n: 0 };

function noteCrash(kind, e) {
  counters.uncaught++;
  log(`⚠ ${kind}:`, e?.stack ?? e?.message ?? e);

  const now = Date.now();
  if (now - crashWindow.start > UNCAUGHT_WINDOW_MS) crashWindow = { start: now, n: 0 };
  crashWindow.n++;

  if (crashWindow.n % UNCAUGHT_REPORT_AT === 0) void selfReportCrash(kind, crashWindow.n);
}

/**
 * 在群里自报「我这边内部出错了」。
 * 找不到可通报的群时**必须说清楚只进了日志** —— 不许沉默（§2.4.2：未测不许与通过长得一样）。
 */
async function selfReportCrash(kind, n) {
  try {
    const target = await resolveChat();
    if (!target) {
      log('   ⚠ 内部出错要自报，但还没有可通报的群 —— 只进日志（不许沉默）');
      return;
    }
    await safeSend(target,
      `⚠ 我这边内部出错了 ${n} 次（最近一次：${kind}），**可能答得不可靠**。\n`
      + '已经记录下来；接下来的回答请以我重新查证过的为准。', 'error-fallback');
    log(`   · 内部出错自报已发到 ${target}`);
  } catch (e) {
    log('   ⚠ 内部出错自报也失败了:', e?.message ?? e);
  }
}

process.on('SIGINT',  () => shutdown('Ctrl-C'));
process.on('SIGTERM', () => shutdown('SIGTERM'));
process.on('unhandledRejection', (e) => noteCrash('unhandledRejection', e));
process.on('uncaughtException',  (e) => noteCrash('uncaughtException',  e));

await ws.start({ eventDispatcher: dispatcher });
// ★ 2026-10-05 加：OCR / 读图这条路的**启动自检**。
//   为什么放在启动：第一张图来的时候现场编译要几十秒，而那几十秒花在**某个人正在等的那条回复**上；
//   编译失败（SDK 变了、CLT 升级）更糟 —— 只有那一张图报「读不到」，没有任何东西会红。
//   现在它每次启动都真跑一遍试纸（本仓资产，不联网、不碰飞书），读数就在第一屏。
try {
  const pf = await vision.preflight();
  if (pf.ok) {
    log(`  读图/OCR              = ✅ 就绪（试纸 ${pf.lines} 行 / ${pf.ms}ms`
        + `${pf.built ? ' · 本次现场编译了二进制' : ''}`
        + `${pf.blankOk ? ' · 空白试纸如期报「没字」' : ' · ⚠ 空白试纸没报「没字」'})`);
  } else {
    log(`  读图/OCR              = ❌ 不可用（${pf.error}）${pf.detail ? '：' + String(pf.detail).slice(0, 160) : ''}`);
    log('                          → 人发来的图会回「图我读不出内容」，而不是静默当成「图上没字」');
  }
} catch (e) {
  log(`  读图/OCR              = ⚠️ 未测（自检自己抛了：${e?.message ?? e}）`);
}

// ★★ 2026-10-15 加：**画面层**（PRD §5.1「基础视觉识别」那一半）的启动自检。
//   与读图同形状，代价不同：**这一条真发一次网络请求**（一张 26KB 试纸图 + 一次调用）。
//   为什么仍要放第一屏：这一层断掉的表现是「结论看起来一样、只是少了画面那半」——
//   没有任何东西会红，而 PRD 要求的那三类（产品使用 / 人物行为 / 场景风险）会**整类消失**。
//   ⚠️ 它不影响启动：失败只打一行；`SHOUHENG_SCENE=0` 时如实报「未开」，不假装读过。
try {
  const sp = await scene.preflight();
  if (sp.ok) log(`  画面层(吃图模型)      = ✅ 就绪（试纸 ${String(sp.detail).slice(0, 96)}）`);
  else if (sp.skipped) log(`  画面层(吃图模型)      = ⏸ 未开（${sp.detail}）`);
  else log(`  画面层(吃图模型)      = ❌ 不可用（${String(sp.detail).slice(0, 160)}）`);
  if (!sp.ok && !sp.skipped) {
    log('                          → 图片的「画面」那半会是**未测**（不是「没有画面」）；报告里也这么写');
  }
} catch (e) {
  log(`  画面层(吃图模型)      = ⚠️ 未测（自检自己抛了：${e?.message ?? e}）`);
}

// ★ 2026-10-05 加：**视频**那条路的启动自检（抽帧 → OCR 读画面上的字）。
//   与读图同一个理由，而且这里更急：视频要现场抽帧 + 跑 8 次 OCR，
//   一条断了不会自己红，只会在群里回一句「视频我读不了」。
try {
  const vp = await video.preflight();
  if (vp.ok) {
    log(`  读视频(抽帧+OCR)      = ✅ 就绪（试纸 ${vp.n_frames} 帧 / ${vp.duration_s}s`
        + ` · 抽帧 ${vp.probeMs}ms · OCR ${vp.ocrMs}ms${vp.built ? ' · 本次现场编译了二进制' : ''}）`);
  } else {
    log(`  读视频(抽帧+OCR)      = ❌ 不可用（${vp.error}）${vp.detail ? '：' + String(vp.detail).slice(0, 160) : ''}`);
    log('                          → 人发来的视频会回「没读成」，而不是静默当成「视频里没问题」');
  }
} catch (e) {
  log(`  读视频(抽帧+OCR)      = ⚠️ 未测（自检自己抛了：${e?.message ?? e}）`);
}

// ★★ 2026-10-16 加：**媒材链接**那条路的启动自检。
//   它断掉的表现是「结论表里那一格只有原文、没有链接」—— 与「这一单没有媒材」
//   **长得一模一样**，没有任何东西会红，而 Owner 要的正是「点击就能打开」。
//   它依赖两样本机之外的东西：`lark-cli` 在不在、云空间的上传/权限 scope 还有没有效
//   ⇒ 探法与上面三条同一条：**真跑一次**（建/取当月月夹子，一次 CLI 调用）。
try {
  const mp = await mediaLink.preflight();
  if (mp.ok) log(`  媒材链接(云空间)      = ✅ 就绪（${String(mp.detail).slice(0, 96)}）`);
  else if (mp.skipped) log(`  媒材链接(云空间)      = ⏸ 未开（${mp.detail}）`);
  else log(`  媒材链接(云空间)      = ❌ 不可用（${String(mp.detail).slice(0, 160)}）`);
  if (!mp.ok && !mp.skipped) {
    log('                          → 「送审问题」那一格只会有原文、没有链接（不是「这一单没有媒材」）');
  }
} catch (e) {
  log(`  媒材链接(云空间)      = ⚠️ 未测（自检自己抛了：${e?.message ?? e}）`);
}

// ★ 2026-10-05 加：**语音转写**那条路的启动自检（本机识别试纸里那句话）。
//   ★ 这一行是有意做得显眼的：它红的时候，视频的「口播/旁白」那一半就是**未测**——
//     而 PRD §12 不许改用云端识别，所以唯一的修法是**人去点一次系统授权**
//     （或把本机语言模型装上）。这里把该说的话直接写在第一屏，不让人去猜。
try {
  const ap = await asr.preflight();
  if (ap.ok) {
    log(`  语音转写(本机)        = ✅ 就绪（试纸「${String(ap.text ?? '').slice(0, 24)}…」/ ${ap.ms}ms · 语种 ${ap.locale}）`);
  } else {
    log(`  语音转写(本机)        = ❌ 不可用（${ap.error}）${ap.detail ? '：' + String(ap.detail).slice(0, 160) : ''}`);
    if (ap.hint) log(`                          → ${String(ap.hint).slice(0, 200)}`);
    log('                          → 视频的「口播/旁白」这一半会标成**未测**（不是「没有人说话」）');
  }
} catch (e) {
  log(`  语音转写(本机)        = ⚠️ 未测（自检自己抛了：${e?.message ?? e}）`);
}

log('✓ 长连接已启动，等待事件（断线由 SDK 自动重连）');

// 启动即核一次上游基线：重启后第一时间知道手上那份 PRD 是不是最新版
// （`--dump-only` 不跑 —— 那个模式是排查用，不该产生任何对外动作）
if (!DUMP_ONLY) void baselineWatch('startup');
// 启动也核一次待收清单：**到期这件事和基线一样，重启后才该被想起来**
if (!DUMP_ONLY) void pendingWatch('startup');
// 外部标准库（62 条）同样在启动时核一次 —— 它带 3 小时冷却，重启不会变成抓取风暴。
// **不传 chatId**：它不知道是哪个群把它叫起来的，往「最近来过消息的群」发才不唐突。
if (!DUMP_ONLY) void externalWatch('startup');
// ★ run-state 第一次落盘**必须在 `ws.start()` 之后**：这份读数的语义是
//   「长连接起来了、我开始接事件了」，写在启动之前会把「正在连」报成「已在跑」。
writeRunState('startup');

/**
 * **身份拒收**的可见读数（2026-10-16 加，Owner 问「这问题彻底修复了吗」时查出的缺口）。
 *
 * 拒收本身是**正确行为**（不把别人的结论当本单的），所以**不加硬闸**；
 * 要看见的是「**它开始频繁发生**」—— 那意味着那把锁又失效了，
 * 表现是「每一单都少了库侧依据」而没人知道（历史实测令牌转发 34 次里只成功 1 次）。
 *
 * 口径：**只在计数变了的时候出声**（每 5 分钟一拍，不变就不刷屏）；
 * 读不到文件就说 0（那条路本来就没发生过）；读抛了**不说**（不编）。
 */
let lastRejectSeen = null;
function identityRejectLine() {
  const n = identityRejectCount();
  if (n === null) return null;           // 读抛了 ⇒ 不说（**不许**当成 0 报）
  const prev = lastRejectSeen;
  lastRejectSeen = n;
  if (prev === null || n === prev) return null;
  return `⚠ 身份拒收 +${n - prev}（累计 ${n}）—— 见 PMO/logs/identity-reject.ndjson｜`
       + '连续出现说明那把锁又失效了（表现：每单都少了库侧依据，而卡片上只写「库侧没读数」）';
}

/**
 * **被辖区挡下的引用**的可见读数（2026-10-16 加，紧接着上面那条）。
 *
 * 口径：菜单只列美国来源，**解析也只认美国来源**（非美国 id ⇒ 不给链接、按「无库内依据」写）。
 * 拒挂是**正确行为**，所以要看的不是"拒了多少"，而是「**它开始出现**」——
 * 那意味着模型在点一个它**看不到 id** 的来源（猜的），或者哪天菜单又被改宽了。
 * 与身份拒收同一条口径：只在计数变了的时候出声；读不到说 0；读抛了不说（不编）。
 */
let lastNonUsSeen = null;
function nonUsCiteLine() {
  const n = nonUsCiteCount();
  if (n === null) return null;           // 读抛了 ⇒ 不说（**不许**当成 0 报）
  const prev = lastNonUsSeen;
  lastNonUsSeen = n;
  if (prev === null || n === prev) return null;
  return `⚠ 域外依据被挡 +${n - prev}（累计 ${n}）—— 见 PMO/logs/nonus-cite.ndjson｜`
       + '出现说明它在点一个菜单里没有的来源（猜的），或菜单又被改宽了；'
       + '被挡的条目按「无库内依据」写，不会带域外链接出去';
}

// 每 5 分钟打一次心跳，方便判断进程是活着还是卡死
const hb = setInterval(() => {
  log(`· 心跳 事件 ${counters.events} 已回答 ${counters.handled} 失败 ${counters.failed} 未捕获 ${counters.uncaught} | LLM 调用 ${status().llm.calls}`);
  { const rl = identityRejectLine(); if (rl) log(`  ${rl}`); }
  { const nl = nonUsCiteLine(); if (nl) log(`  ${nl}`); }
  // ★ 每一拍都把长连接状态说出来（断的时候还会带错误与断线时长）——
  //   「守衡还连着飞书吗」从此是一个**每分钟都在刷新的读数**，不用等人发现它不回话。
  log(`  ${wsLine()}`);
  maybeReviveWs();
  writeRunState();                       // Q2：心跳刷新 lastBeatAt（E1d 靠新鲜度判「卡死」）
  rotateLogIfHuge();
  // 每日兜底：**她"基于评估重新修改"已经推过的那一篇时，群里不会有新链接** ——
  // 这正是「只在收到链接时跑」漏掉的那一种，也是她原话描述的那一种。
  if (!DUMP_ONLY && loadState().lastDay !== bjDate()) void baselineWatch('daily');
  // 待收清单同理换日兜底：到期日的比较对象就是「今天」，而今天只有换日时才会变。
  // ★ 读的是**待收那一份**状态文件（`prd-pending-watch.json`）—— 两个检查共写一份
  //   会互相覆盖：基线那次是「读 → 等网络 3 秒 → 写」，写回去的是旧快照。
  if (!DUMP_ONLY && loadPendingState().p_lastDay !== bjDate()) void pendingWatch('daily');
  // ★ 外部标准库换日兜底（Q4-4d）：**状态文件必须独立**（`external-watch.json`，第三份）。
  //   上游会不会在我们不看的时刻改 —— 这一层把发现窗口缩到 1 天，缩不到 0；
  //   边界写在状态里（`lastRunAt`），不是写在谁脑子里。
  if (!DUMP_ONLY && loadExternalState().lastDay !== bjDate()) void externalWatch('daily');
  /**
   * ── ★ 被跳过的那次检查，冷却一过就补回来（2026-09-22 加，`…误答登记…` §十三）──────
   *
   * 上面那三个 `daily` 兜底只解决「换日」，**不解决「跳过」**：
   * `checkNow` / `checkExternal` 在冷却期内的行为是 `return { skipped }`，
   * 而**冷却是「跳过」，不是「重排」** —— 原先没有任何一行在冷却过期后补跑。
   *
   * 实测代价（§十三 13.3）：一次落在冷却窗口里的重启，让基线检查被推到换日，
   * 漂移发现窗口从 30 分钟被撑到约 24 小时；更要紧的是这期间状态文件一直写着
   * `lastState: "drift"`，**而基线其实早已转绿** —— 一个会过期的读数，
   * 没有任何东西在它过期时变红。
   *
   * ★ 判据不在这一行：`recheckDue()` 是两处各自的**纯函数**（`prd_baseline.mjs` /
   *   `external_watch.mjs`），各有正反两条断言。这一行只回答「谁在跑它」——
   *   `AGENTS.md` §2.4.2 那两层，缺一层都不算兑现。
   *
   * ★ **它不会变成轮询**：`recheckDue` 的第一条就是「没有 `staleSince` 就返回 null」，
   *   而 `staleSince` **只在真的跳过过一次时才被写下**、真跑一次就清空。
   *   所以这一行的触发条件是「本次进程里确实欠了一次检查，且现在允许补了」 ——
   *   不是「距离上次检查过了多久」。（反面对照见两处 `--selftest`。）
   */
  if (!DUMP_ONLY) {
    const due = baselineRecheckDue(loadState());
    if (due) { log(`   ↻ 基线检查补跑（${due}）`); void baselineWatch('deferred'); }
    const edue = externalRecheckDue(loadExternalState());
    if (edue) { log(`   ↻ 外部标准库补跑（${edue}）`); void externalWatch('deferred'); }
  }
  // ★ 补发队列每拍一次（Q1-1d）：「网络恢复了没有」不用另做探针 ——
  //   补发那一次尝试本身就是探针（计划 §1.5）。队列空时它立刻返回，零成本。
  if (!DUMP_ONLY) void retryWatch('tick');
}, 5 * 60_000);
hb.unref?.();

/**
 * 日志自轮转。
 * 为什么必须做：launchd 把 stdout 无条件追加到 ws_daemon.log，不轮转的话
 * 这个文件会一直长，几个月后能把磁盘撑满 —— 而且出问题的时候正好是最需要日志的时候。
 * 只在超过阈值时切一次，保留上一份，不做复杂的分代。
 */
const SELF_LOG = process.env.SHOUHENG_SELF_LOG || path.join(LOG_DIR, 'ws_daemon.log');
const MAX_LOG_BYTES = 20 * 1024 * 1024;   // 20MB
let rotating = false;
function rotateLogIfHuge() {
  if (rotating) return;
  try {
    if (!fs.existsSync(SELF_LOG)) return;
    if (fs.statSync(SELF_LOG).size < MAX_LOG_BYTES) return;
    rotating = true;
    fs.renameSync(SELF_LOG, `${SELF_LOG}.1`);   // 旧的覆盖上一份 .1
    rotating = false;
  } catch { rotating = false; }
}

if (PROBE) {
  setTimeout(async () => {
    log('--probe 自检结束，退出。');
    const s = status();
    log('LLM 统计:', JSON.stringify(s.llm));
    await shutdown('probe 完成');
  }, 10_000);
}
