/**
 * agent.mjs —— 守衡的推理内核（消息进来 → 想 → 用工具 → 出话）
 *
 * 处理一条消息的完整链路：
 *   去重 → 解析 mention → 装上下文 → 载记忆 → 工具循环 → 存记忆（必要时压缩）→ 返回回复
 *
 * 三个容易被忽略但必须做对的地方：
 *   1. 同一会话串行：群里两条消息几乎同时到达时，并发写同一个记忆文件会互相覆盖。
 *   2. 已处理消息去重：长连接重连后服务端可能重推，不做去重会重复回话。
 *   3. 工具循环有上限：模型可能反复调同一个工具，必须有硬闸。
 */
import fs from 'node:fs';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { config, stateDir } from './config.mjs';
import { buildSystemPrompt } from './persona.mjs';
import * as llm from './llm.mjs';
import * as mem from './memory.mjs';
import * as feishu from './feishu.mjs';
import * as vision from './vision.mjs';
import * as sceneMod from './scene.mjs';
// ★ 2026-10-09：OCR 水印摘除（Owner 看出图内文字里的用户名是水印）——见该模块头注
import { stripOcrWatermark } from './ocr_watermark.mjs';
import * as video from './video.mjs';
import { TOOL_SCHEMAS, executeTool, runtimeContext, toolNames, claimStatus, facetsFromMaterial,
         beginChainTurn, chainMemoStats } from './tools.mjs';
import { detectTruncation, annotateTruncation, tailOf, collapseToolMessages, clipToolOutput,
         TOOL_OUTPUT_MAX_CHARS } from './truncate.mjs';
import { parentIdOf, alreadyInHistory, buildQuoteBlock } from './thread.mjs';
import * as reviewGate from './review_gate.mjs';
import { mergeFindings, mergedState, kbFindingsOf, kbCoveredOf, renderMerged, mergeSummary, kbSideOf,
         mergedConfidence, kbNoReadingOf, REPORT_LINK_MIN_ISSUES, evidenceBlock } from './dual_track.mjs';
import { renderMergedReportMd, publishMergedReport } from './merged_report.mjs';
import { reviewModelSide, readingsForModelSide } from './model_side.mjs';
import { generateAdvice } from './advice.mjs';
import * as reviewPublish from './review_publish.mjs';
import { deriveVerdictLine } from './prd53.mjs';
import { foldInto } from './outbound.mjs';

/* ─────────────────── 去重：见过的事件不再处理 ─────────────────── */
// 惰性求值：测试需要把状态目录指到不可写路径来验证失败分支，
// 写成模块常量就再也改不动了（且失效是静默的）。
const seenFile = () => path.join(stateDir(), 'seen-messages.json');
const SEEN_MAX = 500;

function loadSeen() {
  try { return new Set(JSON.parse(fs.readFileSync(seenFile(), 'utf8'))); } catch { return new Set(); }
}
let seen = loadSeen();
let seenDirty = false;
let seenFlushFailed = 0;   // 连续落盘失败次数，用于「只报第一次、恢复时报一次」

export function alreadyHandled(messageId) {
  if (!messageId) return false;
  if (seen.has(messageId)) return true;
  seen.add(messageId);
  seenDirty = true;
  if (seen.size > SEEN_MAX) {                       // 只保留最近的，避免文件无限增长
    const arr = [...seen].slice(-SEEN_MAX);
    seen = new Set(arr);
  }
  return false;
}
export function flushSeen() {
  if (!seenDirty) return;
  try {
    // 写入点自己保证父目录存在：配置加载时的那次 mkdir 是「尽力而为」，
    // 目录若在运行中被删掉，这里补建，而不是让每次落盘都失败。
    fs.mkdirSync(path.dirname(seenFile()), { recursive: true });
    fs.writeFileSync(seenFile(), JSON.stringify([...seen]));
    seenDirty = false;
    if (seenFlushFailed) {            // 恢复后报一次，避免故障期间刷屏
      console.warn(`[seen] 去重表恢复落盘（曾在 ${seenFlushFailed} 次写入失败后成功）`);
      seenFlushFailed = 0;
    }
  } catch (e) {
    // 重要：失败时不能清 seenDirty。
    // 清了就再也不会重写，而这个表决定「重启后是否重复回话」——
    // 它一旦静默丢失，表现是守衡对着同一条消息回两次，且没有任何线索。
    seenFlushFailed++;
    if (seenFlushFailed === 1) {
      console.warn(`[seen] 去重表落盘失败（第 1 次）：${e.code ?? e.message} —— 本次运行仍按内存去重，但重启后可能重复回话`);
    }
  }
}

/* ─────────────────── 串行化：每个会话一把锁 ─────────────────── */
const locks = new Map();
/** 同一 sessionKey 上排队执行，保证记忆文件不会被并发覆盖 */
function withLock(key, fn) {
  const prev = locks.get(key) ?? Promise.resolve();
  const next = prev.then(fn, fn);                   // 前一个失败也要继续排队
  locks.set(key, next.catch(() => {}));
  return next;
}

/* ─────────────────── 兜底话术：工具循环用尽时说什么 ─────────────────── */

/**
 * 工具循环用尽、模型始终没给出最终答复时，替它说一句实话。
 *
 * ★ 硬约束：**正文里不许出现工具名**（2026-09-22 实测事故，见下）。
 *   这条约束由 `tools/verify_cards.mjs` 的 **L6** 守着 —— 它把本函数喂给
 *   `lintCopy()`，并要求**不说话术本身被自己的检测器拦下**。
 *
 * ── 为什么单独拆成函数
 *
 * 原先这句话术是**内联**在工具循环后面的一行字符串拼接，它长这样：
 *
 * ```js
 * '我查了几轮还是没能得出可靠结论，先把已知的告诉你：'
 *   + `我试过 ${toolTrace.map((t) => t.tool).join('、')}，` + '但信息不足。…'
 * ```
 *
 * 一次工具循环里 `run_readonly_command` 会连出十几次，于是正文变成
 * 「我试过 run_readonly_command、run_readonly_command、…（19 次）」——
 * 而 `internalLeak` 规则判「**连续三次同名工具**」为故障，
 * 它在 `verify_cards.mjs` F 段的**正样本正是这句话的形状**。
 *
 * 也就是说：**这句话术 100% 会被自己的检测器拦下**，`envelope.mjs` 把它降级成
 * 「我这次没能把回答组织好」的拒答。2026-09-22 16:34 实测：上游在私聊里问
 * 「你如何读取我 DSH 上的知识库」，两次都跑满 6 轮工具、两次都撞上这一条，
 * **她问了两次、被拒答两次，而盘上没有任何东西记得她欠一条回答。**
 *
 * 根因不是检测器太严（它抓得对），也不是话术不该说「我查不到」——
 * 是**内部详情被写进了正文**。工具名属于排查材料：它已经在 `toolTrace`
 * （进 `meta`、进日志）里，正文只该说人话。
 *
 * @param {Array<{tool:string, ok:boolean}>} toolTrace 本轮实际调过的工具
 * @returns {string} 面向用户的一段话，**不含任何工具名/函数名/轮次上限**
 */
export function fallbackReply(toolTrace = []) {
  const n = toolTrace.length;
  const nFail = toolTrace.filter((t) => !t.ok).length;
  return '这个问题我没答上来 —— 查了几轮，还是没能得出可靠结论。'
    + (n
        ? `\n\n（我这边翻了 ${n} 处${nFail ? `，其中 ${nFail} 处没读通` : '，都能读到，但没拼出答案'}。`
          + '明细留在我这侧，就不往这里贴了。）'
        : '\n\n（我这轮连一次有效检索都没走完。）')
    + '\n\n你把要查的范围再说细一点，我重新来。';
}

/**
 * 「已经取到东西、但一个字都没写出来」时的最后一条路。
 *
 * ★ 2026-09-30 加，起因是一次真事故（本群 19:11 / 19:16）：
 *   她问「用知识库查一下『吸奶器』相关的措辞要求」。模型调了两次 `kb_search`，
 *   工具把 60,349 字原始 JSON 倒进上下文；下一轮**推理把 8000 token 输出预算吃光**
 *   （`finish_reason=length`、正文 0 字），群里收到的是一条**只有截断说明的消息**。
 *   同一形状在 19:05 也发生过一次：工具循环跑满 → 兜底话术「这个问题我没答上来」，
 *   **而盘上答案就在手边**（工具明明都读通了）。
 *
 * 两种「烧光」都不该以「什么都没说」收场，因为**答案的材料已经取回来了**。
 * 这一跳做的事只有一件：把工具返回体折叠成结构摘要，然后**关掉工具**再问一次，
 * 要求它用手上的东西写答案。
 *
 * 为什么关掉工具：再给它工具，它会把同一批查询再跑一遍，然后**再一次**把预算烧光
 * —— 那是同一个坑的第二次。
 *
 * @param {object} opts
 * @param {string} opts.systemPrompt
 * @param {Array}  opts.messages      当轮的完整 messages（含工具结果）
 * @param {string} opts.why           'tool-iters'（循环跑满） | 'empty-length'（烧光没写出字）
 * @returns {Promise<{text:string, usage?:object, finishReason?:string, ok:boolean, error?:string}>}
 */
async function synthesizeFromTools({ systemPrompt, messages, why }) {
  const collapsed = collapseToolMessages(messages);
  const nudge = why === 'empty-length'
    ? '你上一轮的思考把额度用光了，**正文一个字都没写出来**。'
    : `你已经不能再调工具了（本轮工具调用已到上限）。`
    ;
  const finalMessages = [
    ...collapsed,
    { role: 'system', content:
        `${nudge}现在**只许写答案**：直接用上面的材料回话，不要再调任何工具，`
        + '不要再复述原始返回体。\n'
        + '五条要求：\n'
        + '1. 先给结论（一到三句），再给依据；依据要带得出处（条款号 / 文档名 / 规则码）。\n'
        + '2. 材料里没有的**不要补**；确实没查到就直说「这次没查到」，并说清查了什么。\n'
        + '3. 剪过条数或字数时（材料里有 `clip_note` / `〔已折叠〕`）要照实说明'
        + '「我只看了 N 条」，**不许**说成「库里一共只有这些」。\n'
        + '4. 中文，短句，不要复述 JSON，不要贴工具名。\n'
        + '5. 长度控制在 800 字以内。' },
  ];
  try {
    const r = await llm.chat(finalMessages, { tools: [] });
    if (!r.ok) return { ok: false, error: r.error, layer: r.layer };
    return { ok: true, text: String(r.message?.content ?? '').trim(),
             message: r.message,                       // ★ 供 P0 取 reasoning_content
             finishReason: r.finishReason, usage: r.usage };
  } catch (e) {
    return { ok: false, error: `${e?.name ?? 'Error'}: ${e?.message ?? e}` };
  }
}

/**
 * 把一条 assistant 轮写进记忆。**空的那条不许落盘**（2026-09-30 加）。
 *
 * 为什么单独包一层：`mem.append` 那道闸会静默拒收，而「静默」在这里恰好是错的 ——
 * 被拒的那一条是「模型一个字都没写出来」，这件事必须留痕，否则事后只看会话文件
 * 会以为**这一轮压根没发生过**。所以我们自己判一次、自己说一句，再交下去。
 *
 * 判据与 `memory.mjs` 的 `isPersistable` 同源（那边是执行点，这里是留痕点）。
 */
function appendAssistant(sess, msg) {
  const r = mem.append(sess, msg);
  if (!r.stored) {
    console.warn(`[agent] ⚠️ 空 assistant 轮**未写入记忆**：${r.why}`
      + `｜正文 ${String(msg?.content ?? '').length} 字｜tool_calls ${msg?.tool_calls?.length ?? 0}`);
  }
  return r;
}

/**
 * 取出这一轮该**回传**的 `reasoning_content`（2026-09-30 加，P0）。
 *
 * 为什么必须有这一跳：DeepSeek 思考模式下，**带 `tools` 的请求**要求把历史里
 * 每一轮的思维链原样回传，不回传就 400。守衡每轮都带 `tools`，所以这不是可选项。
 * 实测读数在 `PMO/logs/llm_failures.jsonl`：
 *
 *     HTTP 400 code=invalid_request_error
 *     The `reasoning_content` in the thinking mode must be passed back to the API.
 *
 * 唯一一处收口（裁剪也好、开关也好，都只在这里），所以：
 *   · 关掉 → 返回 `{}`，调用点的写法一个字都不用改；
 *   · 超限 → 裁到 `maxChars` 并在**正文之外**留一句可核对的标记，
 *     不静默截断（截了不说 = 事后没人能判断上下文里到底放了什么）。
 *
 * ⚠️ 上限不是洁癖：单轮思维链实测可达 8000 token（≈3 万字）。
 *   无界回传会把「上下文被塞爆 → 推理烧光预算」那个病再造一遍。
 *
 * @param {object} message LLM 返回的 `choices[0].message`（或我们记下的等价物）
 * @returns {{reasoning_content?: string}} 可直接展开进 assistant 轮的对象
 */
export function reasoningToPassBack(message) {
  if (!config.llm.reasoningPassback.enabled) return {};
  const r = message?.reasoning_content;
  if (typeof r !== 'string' || r.length === 0) return {};

  const cap = config.llm.reasoningPassback.maxChars;
  if (r.length <= cap) return { reasoning_content: r };

  console.warn(`[agent] · 思维链超回传预算：${r.length} 字 → 裁到 ${cap} 字`
    + `（只为控制上下文；已发出的正文不受影响）`);
  return {
    reasoning_content: r.slice(0, cap)
      + `\n…〔本轮思维链原长 ${r.length} 字，按 ${cap} 字上限裁剪后回传〕`,
  };
}

/* ─────────────────── 入向内容：文字 + 图内文字 + 视频 ─────────────────── */

/** 一次最多读几张图。是**上限**，不是「读到几张算几张」—— 超出的部分要说话。 */
export const MAX_IMAGES_PER_MESSAGE = 4;

/**
 * 一次最多读几条视频。**故意是 1**（2026-10-05 定的），理由不是省事：
 *   · PRD §12 给视频的响应预算是 **≤60s**，而一条 15 秒的视频实测要 3.5 秒
 *     （抽帧 0.2s + 8 帧 OCR 3.0s + 转写 0.8s）—— 成本随时长与条数线性涨；
 *   · 人一次发两条视频要同时审，是罕见用法；真遇到，多出来的那一条**明说没读**，
 *     让人分开再发（比默默读一半强）。
 */
export const MAX_VIDEOS_PER_MESSAGE = 1;

/** 这几类附件**不在** §2.6 那条窄豁免里 —— 但 «里面的视频» 从 2026-10-05 起在（见下）。 */
const ATTACHMENT_TYPES = new Set(['file', 'media', 'audio']);

/**
 * 把一条消息读成「文字部分 + 图内文字」。**纯读**：不发消息、不碰记忆、不调模型 ——
 * 所以它能被单测直接喂桩（`tools/test_agent.mjs` 第 13 组就是这么跑的）。
 *
 * ★ 为什么要有这个函数（而不是散在 handleMessage 里）：
 *   2026-10-05 那条「评审下下这个图片，能过吗？」被整类拒掉 —— 连**正文**都没读。
 *   根因是 `handleMessage` 里 `if (msg.message_type !== 'text') return 拒答` 这一道
 *   把所有非文本类型一刀切了，而**图文混排恰恰是 post 类型**：
 *   人最常见的发法（写一句话 + 配一张图）正好落在刀口上。
 *
 * ★ 三种「读不到」在这里必须长得不一样（§2.4.1「否定结论不许比输入大」）：
 *   · `attachment` —— 按规矩不取（file/media/audio）；
 *   · `images[i].failed` —— 这一张**取不到**（给原因）；
 *   · `images[i].ocrEmpty` —— 取到了、也跑了 OCR，但**图上没读出文字**。
 *   把后两者说成同一件事，是「把取不到说成没有」。
 *
 * @param {object} msg  im.message.receive_v1 的 `message`
 * @param {{fetchImage?:Function, ocr?:Function}} [deps] 测试注入用；生产走真实现
 */
export async function readInboundContent(msg, {
  fetchImage = feishu.fetchMessageImage,
  fetchVideo = feishu.fetchMessageVideo,
  ocr = vision.ocrImage,
  // ★★ 2026-10-15：**画面层**（PRD §5.1 的「基础视觉识别」那一半）。
  //   此前两侧吃的都是同一份 OCR 文字 ⇒ 画面没人看（详见 `scene.mjs` 头注：
  //   「模型不吃图」那句话当天被实测否掉了 —— 同一个端点 HTTP 200）。
  //   注入点在这里，与 `ocr` 同级：测试要能打桩，否则这条路只能在联网+花 token 下才测得动。
  scene = sceneMod.sceneRead,
  readVideoFn = video.readVideo,
  loadParent = feishu.getMessage,
  // ★★ 2026-10-09（Owner：「图上文字：刘华丽==》**还有我的名字**」）：
  //   一个**异步取数函数** `() => Promise<string|null>`，回**送审人显示名** ——
  //   水印里那个名字的确定性来源（水印逐字就是「用户名 + 工号」）。
  //   只在**真读到图、真要去水印**那一刻调一次（惰性：没带图的对话不付这次查询）。
  //   取不到（没 open_id / 查不到）⇒ 回 null ⇒ 那一条判据不生效，**不抛**。
  senderNameForWatermark = null,
} = {}) {
  const msgType = msg?.message_type ?? 'unknown';
  const content = msg?.content ?? '{}';

  // 正文走 `bodyToText`（post 的富文本 → 纯文本这条路 2026-09-22 就修好了，
  // 只是**从来没有机会被执行** —— 非 text 类型在上一步就被拒了）。
  const parsed = feishu.bodyToText(msgType, content);
  const text = parsed.text ?? '';

  // ── 图 / 视频从哪来：先看这一条，再看**它引用的那一条** ──
  //
  // ★ 为什么必须有第二处（2026-10-05 补）：「发一张图 → 回它一句『这张能过吗』」
  //   和「@守衡 回复某条带图的消息」都是真实用法（实测群历史里 post+parent_id 就有）。
  //   只看当前消息的后果是：守衡回一句「你这条里没图」—— 而图就在它引用的那一条里。
  //   仍然只覆盖**被明确指到的那一条**（`parent_id`），**不翻历史**：
  //   「顺着历史把群里的图/视频捞一遍」不在豁免里，那条线没动。
  //
  // ★ 2026-10-05 同日：视频并进同一条豁免（Owner 现场确认），取法完全一样 ——
  //   所以这两路**共用同一个 parent 回读**，而不是各写一遍（各写一遍就会出现
  //   「回复一条带视频的消息，守衡说没视频」这种一半对一半错的状态）。
  let keys = feishu.imageKeysOf(msgType, content);
  let vidKeys = feishu.videoKeysOf(msgType, content);
  let fromParent = false;
  // ★★ 2026-10-09：**取字节要用「这串 key 属于哪条消息」的 id**。
  //   病灶（实测，Owner 连发三次视频全部失败）：图/视频的 key 从**被引用的那条**取到
  //   （`fromParent=true`），取字节却用 `msg.message_id`（**当前这条**）⇒
  //   `messageResource.get` 拿「当前 id + 父消息的 file_key」去查 ⇒ **HTTP 400**。
  //   实测日志：「视频 1 段（取自你引用的那条消息）｜读成功 0 · 失败 1｜取视频失败 …
  //   status code 400」。⇒ **「群里引用一条视频再 @守衡」这条路被这个 bug 堵死**；
  //   能读通的是**私聊直接发**（key 与 id 同源，不走 fromParent）。
  let srcMsgId = msg?.message_id ?? null;
  let parentNote = null;          // 非 null = 「那条我读不到/没图没视频」这件事本身要说出
  if (!keys.length && !vidKeys.length) {
    const pid = parentIdOf(msg);
    if (pid) {
      let parent = null;
      try { parent = await loadParent(pid); }
      catch (e) { parent = { error: `回读抛异常：${e?.message ?? e}` }; }
      if (parent?.images?.length || parent?.videos?.length) {
        keys = parent.images ?? [];
        vidKeys = parent.videos ?? [];
        fromParent = true;
        // key 来自父消息 ⇒ 取字节必须用**父消息 id**，否则 400
        srcMsgId = parent.messageId || parent.message_id || pid;
        // 被引用那条的**正文**也带上（她可能是「引用一段图文」再问的）。
        if (parent.text && !text) parentNote = { kind: 'parent_text', text: parent.text };
      } else if (parent?.error) {
        // ⚠️ 这是**未测**，不是「引用的那条里没有图」—— 两句话引出的下一步不同
        parentNote = { kind: 'parent_unreadable', error: parent.error, parentId: pid };
      } else {
        parentNote = { kind: 'parent_no_image', parentId: pid };
      }
    }
  }

  const images = [];
  const todo = keys.slice(0, MAX_IMAGES_PER_MESSAGE);

  for (let i = 0; i < todo.length; i++) {
    const k = todo[i];
    let got = null;
    try {
      got = await fetchImage(srcMsgId, k.imageKey);
    } catch (e) {
      got = { path: null, bytes: 0, error: `取图抛异常：${e?.message ?? e}`, cleanup: () => {} };
    }
    try {
      if (got?.error || !got?.path) {
        images.push({ index: i + 1, imageKey: k.imageKey, fromParent, failed: got?.error ?? '取图没有回路径' });
        continue;
      }
      // ── 画面层（2026-10-15 加）：**字节还在盘上**时读一次 ─────────────────────
      //   为什么放在 OCR **之前**、而且与 OCR **互不依赖**：
      //     · PRD §5.1 把图片的输入写成两半（OCR ＋ 基础视觉）⇒ 两条读数各自独立；
      //     · 实测那张「只有品牌字样」的图正好说明：OCR 几乎没字，**画面那一半才是全部信息**；
      //     · 反过来 OCR 失败（占位图/1×1）也不该连带把画面一起丢掉。
      //   失败**不影响**任何既有分支：`sceneRes` 只是挂在每一条 entry 上的一个读数。
      //   ⚠️ 变量名**不许叫 `scene`** —— 那会把上面注入的那个 `scene` 参数**遮蔽掉**
      //      （`let scene` 一写，`scene(got.path)` 当场 `scene is not a function`；
      //       实测就是这么红的第一版）。
      let sceneRes = null;
      try {
        sceneRes = await scene(got.path);
      } catch (e) {
        sceneRes = { ok: false, ms: 0, error: `画面读数抛异常：${e?.message ?? e}` };
      }
      if (sceneRes && !sceneRes.ok && !sceneRes.skipped) {
        console.log(`[agent] 🖼 画面读数**没读到**（不是「没有画面」）：图 ${i + 1}｜${sceneRes.error}`);
      } else if (sceneRes?.ok) {
        console.log(`[agent] 🖼 画面读数｜图 ${i + 1}｜${sceneMod.sceneLine(sceneRes)} · ${sceneRes.ms}ms`);
      }
      const pushImg = (extra) => images.push({
        index: i + 1, imageKey: k.imageKey, fromParent, bytes: got.bytes,
        ...(sceneRes ? { scene: sceneRes } : {}), ...extra,
      });
      // OCR 自己抛也要接住：本模块的契约是「**任何一张图读不到都不该让整条回话失败**」，
      // 而这一条是写测试时才发现的 —— 第一版的 throw 会穿过 finally 冒到 handleMessage 外面，
      // 后果是对方发图那一条消息**连正文都收不到回答**（正好复现我们要修的那个病）。
      let r;
      try {
        r = await ocr(got.path);
      } catch (e) {
        pushImg({ failed: `OCR 抛异常：${e?.message ?? e}` });
        continue;
      }
      if (!r?.ok) {
        // 「这一张我读不到」—— 与下面的「图上没字」分开记。
        pushImg({ failed: `OCR 失败（${r?.error ?? '未知'}）${r?.detail ? '：' + r.detail : ''}`,
                  placeholder: !!r?.placeholder });
      } else if (!r.text || !r.text.trim()) {
        pushImg({ ocrEmpty: true, w: r.w ?? null, h: r.h ?? null });
      } else {
        // ★★ 2026-10-09（Owner 亲自看出「图上文字里的『刘华丽』是水印」）──────────────
        //   图内 OCR 里混着**文档水印**（用户名 + 工号，实测 `5615 RO0 / 刘华丽 / 刘华問`），
        //   它被当成素材内容进了检索 —— 该摘。
        //   ⚠️ **但事后实测证明：它不是那批假命中的根**（我一开始这么写过，已更正）——
        //      那 5 条无关记录与素材**只共用了 `in / or / 5 / 15` 与品牌名 `momcozy`**，
        //      水印 token（`刘华丽` 等）在那 5 条里**一次都没出现**。真因是**门限口径**：
        //      `l6/retriever.py::search_lang` 逐词累加分数、**不按查询长度归一**，
        //      而门限是固定数 ⇒ 长素材下「同长度纯噪声」（实测 49.17）都能过 16.0。
        //      详见 2026-10-09 的实测记录；**改门限是另一件事，未做**。
        //   ⇒ 这里做一次**水印摘除**，且**两份都留着**：
        //     · `text`    = **摘掉水印后** —— 这是**唯一的对外文本**（卡片 / 送进模型 /
        //                   模型侧读数 / 库侧检索 / 落表 / 报告附录 六处都取它）。
        //       ★★ 2026-10-09 晚**收口**（理由见下）：原先 `text` 是原文、另设一个 `wlText`，
        //          三处产者各挑各的 ⇒ 一天之内**连栽两次**：
        //            ① 卡片印原文 ⇒ Owner 看到自己的名字；
        //            ② 模型侧读数（`model_side.mjs`）印原文 ⇒ 模型把水印当"素材里的中文人名"
        //               写进整改建议，等于让被审方去改一个根本不存在的元素。
        //          存两份、让每个读者自己挑 ⇒ 迟早再漏一处。现在**默认就是干净的那份**，
        //          要原文的（只有诊断与留痕）必须**显式**去取 `textRaw`。
        //     · `textRaw` = **OCR 原文**（留痕；核对"OCR 到底读到了什么"用它，一个字不改）；
        //     · `wm*`     = 留痕（摘了哪些行、靠哪条判据）—— 缺了它，摘除就是不可核的。
        const senderName = senderNameForWatermark ? await senderNameForWatermark() : null;
        const wm = stripOcrWatermark({ text: r.text, boxes: r.boxes, senderName });
        pushImg({ text: wm.text, textRaw: r.text,
                      lines: r.lines ?? null, chars: r.chars ?? null,
                      w: r.w ?? null, h: r.h ?? null, truncated: !!r.truncated,
                      // `wlText` 保留为**同一份**（老读者还有人在用；值恒等，不再各挑各的）
                      wlText: wm.text, wmDropped: wm.dropped, wmBasis: wm.basis });
        if (wm.dropped.length) {
          console.log(`[agent] 🚫 图 ${i + 1} 摘除水印 ${wm.dropped.length} 行`
            + `（判据=${wm.basis}）：${wm.dropped.slice(0, 8).join(' / ')}`
            + `${wm.dropped.length > 8 ? ' …' : ''}`);
        }
      }
    } finally {
      // 字节用完就删 —— 豁免的形状是「过一遍 OCR」，**不是「留下来」**。
      // 放在 finally 里：OCR 抛了也要删（否则一次故障就留下一堆临时图）。
      try { got?.cleanup?.(); } catch { /* 删不掉不该让这次回话失败 */ }
    }
  }

  const skipped = keys.length - todo.length;

  // ── 视频：取字节 → 抽帧 OCR + 本机转写（同一条窄豁免，同一个 parent 回读）──
  const videos = [];
  const vTodo = vidKeys.slice(0, MAX_VIDEOS_PER_MESSAGE);
  for (let i = 0; i < vTodo.length; i++) {
    const v = vTodo[i];
    let got = null;
    // 后缀用**原名里的后缀**（只留字母数字），好让临时文件一眼看得出是什么；
    // 解不开的容器由 `readVideo` 如实报，不靠后缀判断。
    const ext = (String(v.fileName ?? '').match(/\.[A-Za-z0-9]{2,5}$/) ?? ['.mp4'])[0].toLowerCase();
    try {
      got = await fetchVideo(srcMsgId, v.fileKey, { ext });
    } catch (e) {
      got = { path: null, bytes: 0, error: `取视频抛异常：${e?.message ?? e}`, cleanup: () => {} };
    }
    try {
      if (got?.error || !got?.path) {
        videos.push({ index: i + 1, fileKey: v.fileKey, fileName: v.fileName, fromParent,
                      bytes: got?.bytes ?? 0, failed: got?.error ?? '取视频没有回路径' });
        continue;
      }
      let r;
      try {
        r = await readVideoFn(got.path, {});       // ← 本机抽帧 + OCR + 转写，全在这一个调用里
      } catch (e) {
        videos.push({ index: i + 1, fileKey: v.fileKey, fileName: v.fileName, fromParent,
                      bytes: got.bytes, failed: `读视频抛异常：${e?.message ?? e}` });
        continue;
      }
      // 抽出来的帧与音频**用完就删**（豁免的形状是「过一遍」，不是「留下来」）。
      try { r?.cleanup?.(); } catch { /* 删不掉不该让这次回话失败 */ }
      if (!r?.ok) {
        videos.push({ index: i + 1, fileKey: v.fileKey, fileName: v.fileName, fromParent,
                      bytes: got.bytes,
                      failed: `读视频失败（${r?.error ?? '未知'}）${r?.detail ? '：' + r.detail : ''}` });
        continue;
      }
      videos.push({
        index: i + 1, fileKey: v.fileKey, fileName: v.fileName, fromParent, bytes: got.bytes,
        meta: r.meta, frames: r.frames, framesRead: r.framesRead, framesFailed: r.framesFailed,
        ocrText: r.ocrText, ocrChars: r.ocrChars, ocrTruncated: r.ocrTruncated,
        transcript: r.transcript, notes: r.notes ?? [], ms: r.ms,
      });
    } finally {
      // 视频字节本身也删（与图片那条同一个 finally 形状）。
      try { got?.cleanup?.(); } catch { /* 同上 */ }
    }
  }
  const skippedVideos = vidKeys.length - vTodo.length;

  return {
    msgType,
    text,
    parsed: parsed.parsed,
    parseNote: parsed.note ?? null,
    /** 消息里一共有几张图（含没读的）—— 含「从被引用那条消息里取的」 */
    imageCount: keys.length,
    /** 图/视频是从**被引用的那条消息**里取的吗（当前这条两样都没有） */
    fromParent,
    /** 被引用那条的读数：「没有 / 没正文 / 读不到（未测）」三者必须分得开 */
    parentNote,
    images,
    skippedImages: skipped > 0 ? skipped : 0,
    /** 消息里一共有几段视频（含没读的） */
    videoCount: vidKeys.length,
    videos,
    skippedVideos: skippedVideos > 0 ? skippedVideos : 0,
    // ★ 附件类型（不在豁免里）；不是附件则 null。
    //   `file` / `media` **只在它们不是视频时**才算「附件」——
    //   「名字是视频的 file」从 2026-10-05 起在豁免里，把它算成附件会让人听到
    //   「视频我不取」，而那条路已经通了（这正是这次要修的那句话）。
    attachment: (ATTACHMENT_TYPES.has(msgType) && !vidKeys.length) ? msgType : null,
  };
}

/**
 * ★ 「带了媒材就要起链」这条规矩的**唯一出处**（2026-10-05 加，Owner 现场确认）。
 *
 * 起因是一次真实事故：有人私聊发了一条视频、**一个字都没写**，守衡把读数描述了一遍就收工了 ——
 * `PMO/logs/ws_daemon.log:2498` 那一轮**一次工具都没调**（回复行前面没有 `🔧 工具:` 那一行），
 * 她要的结论一个字没有。诊断出来是两个缺口叠在一起：
 *   ① 人设那条路由规则是按**问句**写的（「能不能发 / 审一下」），一条光秃秃的媒体消息不匹配；
 *   ② 图块/视频块的头注全在讲「你能判什么、不能判什么」，**一个字没提该走哪条路**。
 *
 * 所以这句话同时挂在图块、视频块，以及人设的「走哪条路」那一节 —— 三处同一句话，
 * 判据在 `tools/test_agent.mjs` 第 16 组（两个块里必须都有它）与第 10 组（人设里必须有它）。
 */
export const MEDIA_ROUTE_HINT =
  '【★ 这是**送审素材**：不管对方写没写「审一下」，都要走 kb_review_chain，'
  + '把上面这段读数当输入交进去 —— 只回一段「我读到了什么」不算回答。'
  + '连「这里没有可判内容」这种结论也必须由链给出，不由你替它下。】';

/**
 * 把入向内容拼成**给模型看的那一段**。
 *
 * ★ 图块的头注不是客套话，它承担三件事，缺一件都会让模型说出比依据大的话：
 *   1. 说清这是 **OCR 读数**，可能有识别错误（不许当成逐字原文去引用）；
 *   2. 说清**画面本身看不见** —— 构图、场景、人物、婴幼儿在做什么、产品怎么用的，
 *      都不在这段文字里。模型必须把这条边界转述出去，否则「这个图能过吗」
 *      会被答成一个它其实没看过画面的结论；
 *   3. 说清图的**来源**（就是对方这条消息里附的），避免和图上印着的文字混淆。
 */
export function buildImageBlock(inbound) {
  if (!inbound?.imageCount) return '';
  // 来源必须说准：是她**这条**带的图，还是她**引用的那条**里的图 ——
  // 说错了，模型会把「她引用的那条里的字」当成「她这条里写的字」去答。
  const src = inbound.fromParent
    ? '对方**这条消息没带图**；下面是**它引用的那条消息**里附的图'
    : '对方这条消息里附了图';
  const quoted = inbound.fromParent && inbound.parentNote?.kind === 'parent_text' && inbound.parentNote.text
    ? `\n（她引用的那条消息，正文逐字是：${String(inbound.parentNote.text).slice(0, 500)}）`
    : '';
  const hasScene = (inbound.images ?? []).some((i) => i?.scene?.ok);
  const parts = [
    `【${src}，共 ${inbound.imageCount} 张。下面每一格是**两条读数**：`
    + `① **本机 OCR 读出的图内文字**（逐字，可能有识别错误；也可能读不全）；`
    + `② **画面读数**（一个吃图的视觉模型看那张图写下的、只陈述看得见的：`
    + `场景 / 人物（含是否婴幼儿）/ 物品是否在用 / 可见商标 / 画面线索）。`
    + (hasScene
      // ★★ 2026-10-15：这一条是**改口径**，不是改措辞 —— 此前写的是「画面本身你看不到」，
      //   因为那时**画面层根本不存在**。现在读数在手，再说"看不到"就是**把有说成没有**；
      //   但也不能放开成"你看过这张图"（那是模型读数，不是原图）。
      ? `②是**模型给的读数，不是原图**：涉及画面的结论**只能依据它**，`
        + `并写明「画面结论依据的是这份读数」；**读数里没写的（月龄、声音、这张图之外的情节）不许推断**；`
        + `②**没读到**时如实说「画面这一层未测」，**不许**说成「画面没问题」。`
      : `②**这一单没有**（画面层没跑或没读到）：涉及画面的结论**不许推断**，`
        + `必须写明「画面我看不到、要看画面得由人来看」。`)
    + `所以：可以按这两条读数做文案、宣称、产品使用、人物行为与场景层面的判定，`
    + `但凡读数没覆盖的部分，都要把边界写出来。${quoted}】`,
  ];
  for (const im of inbound.images) {
    if (im.failed) {
      parts.push(`【图 ${im.index}】**这一张我读不到**：${im.failed}`
        + (im.placeholder ? '（OCR 自己报的尺寸是 1×1 像素级 —— 这类多是占位图/懒加载图，不是「读不出来」）' : '')
        + ` —— 不要猜它的内容。`);
    } else if (im.ocrEmpty) {
      parts.push(`【图 ${im.index}】这一张取到了（${im.bytes} 字节，${im.w ?? '?'}×${im.h ?? '?'} 像素），`
        + `但**没识别出任何文字** —— 这是「图上没有可读的文字」，不是「读不出来」。`);
    } else {
      // ★★ 2026-10-09（Owner 第二次来问「我重测了，水印还在」）：
      //   这一格原先印 `im.text`（**OCR 原文、含水印**）。而同一件事的另一个产者
      //   `describeMediaRead`（卡片那一格）已改印 `wlText` ⇒ **同一段文字两个口径**：
      //   卡片干净、**喂给模型的这段还带着水印** ⇒ 模型与报告那一侧继续拿水印当素材。
      //   ⇒ 现在**统一**：送进模型的也是摘掉水印那份（`wlText`），与喂给链的检索文本同源。
      //   原文一个字没丢（仍在 `im.text`），核对时看日志的摘除明细那一行。
      //   ⚠️ 行数仍报**读到几行**（`im.lines`，是真读数）；另摘几行**明写**，
      //     否则模型会怀疑"显示的行数对不上正文"，或反过来把摘掉的当成没读到。
      const body = String(im.wlText ?? im.text);
      const dropped = im.wmDropped?.length ?? 0;
      parts.push(`【图 ${im.index} 内文字${im.truncated ? '（已截断）' : ''}｜${im.lines ?? '?'} 行`
        + `${dropped ? `，另摘除水印 ${dropped} 行（不是素材内容）` : ''}】\n`
        + `${body}\n【/图 ${im.index}】`);
    }
    // ── ★★ 2026-10-15：**画面读数**（PRD §5.1「基础视觉识别」那一半）───────────
    //   为什么单独一格、且**不放进上面那个 if/else**：两条读数**各自独立** ——
    //   OCR 失败或"图上没字"的图，画面读数照样可能读到东西。
    //   实测那次（2026-10-15 李倩怡那张图）正是这种：OCR 只有品牌字样 `momcozY`，
    //   而画面读数给出了「婴幼儿出镜 / 产品正在被冲洗 / 疑似合成痕迹」——
    //   把它挂在 OCR 的分支里，就会在**最需要它的那一类图上**正好丢掉。
    if (im.scene?.ok) {
      parts.push(`【图 ${im.index} 画面读数（视觉模型的读数，**不是原图**；涉及画面的结论只能依据这一格）】\n`
        + `${sceneMod.sceneBlock(im.scene.scene)}\n【/图 ${im.index} 画面读数】`);
    } else if (im.scene?.skipped) {
      // 「这一单没跑」——**不是**失败、也不是「没有画面」：如实说没跑，别让它看起来像读过
      parts.push(`【图 ${im.index} 画面读数：这一单**没跑**（${im.scene.error ?? '未开'}）】`);
    } else if (im.scene && im.scene.error) {
      parts.push(`【图 ${im.index} 画面读数：**没读到**（${im.scene.error}）—— `
        + `画面这一层是**未测**，不是「没有画面」，也不许据此推断画面】`);
    }
  }
  if (inbound.skippedImages) {
    parts.push(`【还有 ${inbound.skippedImages} 张图**没有读**：一次最多读 ${MAX_IMAGES_PER_MESSAGE} 张。`
      + `需要的话让对方把剩下的单独再发一次。】`);
  }
  parts.push(MEDIA_ROUTE_HINT);
  return parts.join('\n');
}

/**
 * 把入向内容里的**视频**拼成给模型看的那一段。
 *
 * ★ 视频块的头注比图片块更要紧，因为「看视频」这句话最容易说大：
 *   本模块能做到的是 —— **按时长均匀抽 N 帧**（默认 8 帧）→ 读这 N 帧画面上的字；
 *   **把整条音轨**做本机转写（口播/旁白）。做不到的是 —— 逐帧看完整条片子、
 *   看构图/动作/婴幼儿姿势、听语气、看剪辑节奏。
 *   所以「我看了这条视频」是**假话**，必须让模型说的是「我读到了这 8 帧上的字 + 整条音轨的转写」。
 *   这一条是 PRD §11 那条「PASS 误放率」的地基：把抽样说成全量，误放就从这里开始。
 *
 * ★ 三种「声音那侧没有结果」也在这里分开说，不许糊成一句「听不清」：
 *   · 没有音轨 —— 读数（静音片子是合法素材）；
 *   · 有音轨但没人说话 —— 读数（实测产品 hero 片就是这样）；
 *   · 转写没跑成（未授权 / 超时 / 模型没装）—— **未测**，要人看一眼。
 */
export function buildVideoBlock(inbound) {
  if (!inbound?.videoCount) return '';
  const src = inbound.fromParent
    ? '对方**这条消息没带视频**；下面是**它引用的那条消息**里附的视频'
    : '对方这条消息里附了视频';
  const quoted = inbound.fromParent && inbound.parentNote?.kind === 'parent_text' && inbound.parentNote.text
    ? `\n（她引用的那条消息，正文逐字是：${String(inbound.parentNote.text).slice(0, 500)}）`
    : '';
  const parts = [
    `【${src}，共 ${inbound.videoCount} 段。下面每一格是**本机读出来的读数**：`
    + `「关键帧上的文字」是按时长**均匀抽 ${video.VIDEO_MAX_FRAMES} 帧**做的 OCR，`
    + `「音轨转写」是**整条音轨**在本机做的语音识别（开关是 requiresOnDeviceRecognition，音频不出机器）。`
    + `你能据此判断的是：**画面上出现过的字**（硬字幕、贴片文案、logo、包装声明）`
    + `与**整条音轨里说过的话**。`
    + `你**看不到**的是：没抽到的那几帧、构图、场景、人物在做什么、婴幼儿的姿势、`
    + `产品怎么用的、有没有换脸/合成痕迹。`
    + `所以：涉及**画面本身**的结论必须写明「画面我只看得到抽样的这几帧」，`
    + `不许说成「整条视频我都看了」。${quoted}】`,
  ];
  for (const v of inbound.videos) {
    if (v.failed) {
      parts.push(`【视频 ${v.index}】**这一段我读不到**：${v.failed} —— 不要猜它的内容。`
        + `（对方发的是「${v.fileName ?? '未给文件名'}」）`);
      continue;
    }
    const m = v.meta ?? {};
    const head = `【视频 ${v.index}｜${v.fileName ?? '未给文件名'}｜`
      + `${m.duration_s != null ? Number(m.duration_s).toFixed(1) + 's' : '时长未知'}`
      + `${m.w && m.h ? `｜${m.w}×${m.h}` : ''}`
      + `${m.fps ? `｜${Number(m.fps).toFixed(0)}fps` : ''}`
      + `｜关键帧 ${v.framesRead}/${v.frames?.length ?? 0} 帧读成功】`;

    // ── 画面上的字 ──
    // ④ 与卡片/库侧**共用同一个 `frameLine`**（原先这里自己拼过一份，与 video.mjs 那份是
    //    两份实现 —— 改一处忘一处就会漂移，这正是本轮栽的形状）。输出**逐字不变**。
    const frameLines = (v.frames ?? []).map((f) => video.frameLine(f)).filter(Boolean);
    const ocrPart = frameLines.length
      ? `关键帧上的文字（按时间码${v.ocrTruncated ? '，已截断' : ''}）：\n${frameLines.join('\n')}`
      : `关键帧上的文字：**这 ${v.frames?.length ?? 0} 帧里没读出一个字**`
        + `（这是「画面上没有可读文字」，不是「读不出来」—— 除非上面写了某帧 OCR 失败）`;

    // ── 声音 ──
    const t = v.transcript ?? {};
    let audioPart;
    if (t.ok && t.suspect) {
      // ★ 2026-10-08 新增的一格：**结果回来了，但字与被试的语种都不符**。
      //   病灶：英文音轨被按 zh-CN 识别（默认语序中文优先 + 第一个 ok 就 return），
      //   拿到一段胡话却带 `ok:true` ⇒ 原来这里会把它印成「逐字转写」，
      //   于是守衡拿胡话当口播去引用。实测对照见 `asr.mjs::checkScript()` 头注。
      //   ⇒ 这里必须说得比「可能有错」重：它不是「识别不准」，是「这段字大概不是她说的话」。
      audioPart = `音轨转写：**这一格不可信** —— ${t.hint ?? '转写文本与被试语种不符'}\n`
        + `  试过的语种：${(t.tried ?? []).join(' → ')}｜采用的文本（语种标记 ${t.locale}，`
        + `${t.chars} 字）：\n「${t.text}」\n`
        + `  ⇒ 不得把上面这段当逐字口播引用；要谈口播，只能说「这一格**没测准**」，`
        + `并请对方把音轨里的原话贴过来。`;
    } else if (t.ok) {
      // ★ 2026-10-14：长视频的转写是**分段**做的（`asr.mjs` 的 `ASR_CHUNK_SECONDS`——
      //   识别器一次只肯啃 ~2 分钟，整条 57 分钟塞进去一个字都回不来）。
      //   段内逐字、段间按时间顺序相接 ⇒ 「逐字」这个说法仍然成立，
      //   但**必须说出来**：人要知道这行字是 12 段拼的，才好在回听时按 `chunks[].start_s` 对时间。
      audioPart = t.chars
        ? `音轨转写（本机识别，逐字，可能有错；语种 ${t.locale}`
          + `${t.locale_basis ? `，选它的依据：${t.locale_basis}` : ''}`
          + `${t.chunked ? `；**分 ${t.n_chunks} 段转写**，每段 ≤${t.chunk_seconds}s、段间按时间顺序相接`
              + `${t.chunk_fails ? `，其中 ${t.chunk_fails} 段没转成` : ''}` : ''}）：\n「${t.text}」`
        : `音轨转写：识别器回了一个**空结果**（chars=0）—— 这是「整条音轨里没识别出话」，`
          + `不是「转写没跑成」。`;
    } else if (t.kind === 'no_audio_track') {
      audioPart = '音轨：**这条视频没有音轨**（静音片子）—— 是读数，不是转写失败。';
    } else if (t.kind === 'no_speech') {
      audioPart = '音轨转写：**这段音频里没有人说话**（识别器的原话是 No speech detected）——'
        + ' 是读数，不是读不到。多半是纯音乐/音效片。';
    } else {
      audioPart = `音轨转写：**没跑成**（${t.kind ?? '未知'}）`
        + `${t.hint ? ` —— ${t.hint}` : ''}`
        + `。这一格是**未测**：声音里说了什么**我不知道**，不要当成「没有说话」。`;
    }

    parts.push(`${head}\n${ocrPart}\n${audioPart}`
      + (v.notes?.length ? `\n附注：${v.notes.join('；')}` : '')
      + `\n【/视频 ${v.index}】`);
  }
  if (inbound.skippedVideos) {
    parts.push(`【还有 ${inbound.skippedVideos} 段视频**没有读**：一次最多读 ${MAX_VIDEOS_PER_MESSAGE} 段`
      + `（视频要抽帧 + 整条转写，成本随时长涨）。需要的话让对方把剩下的单独再发一次。】`);
  }
  parts.push(MEDIA_ROUTE_HINT);
  return parts.join('\n');
}

/**
 * 默认的跑链方式：把 `kb_review_chain` 跑一次，并**拆掉 `executeTool` 的那层信封**。
 *
 * ★ 为什么单独写一个具名函数（而不是内联一行）：这一层**信封**是实测踩出来的坑 ——
 *   `executeTool()` 回的是 `{tool, ok, result}`，**不是**链自己的返回。
 *   第一版写的是 `(args) => executeTool('kb_review_chain', args)`，于是闸门拿到的是那个信封：
 *   `res.error` 是 undefined、`res.answer` 也是 undefined，
 *   结果**每一次送审都会被写成「链跑完了但没返回结论 —— 结论未知」** ——
 *   链明明跑成了、飞书也写了，而回给群里的是「未知」。一个安静地把成功说成未知的形状。
 *   所以这里拆信封，并且 `review_gate.formatChainBlock()` **两种形状都认**
 *   （判据在 `tools/test_agent.mjs` 第 18 组，两种形状各喂一次）。
 */
export async function defaultChainRunner(args) {
  const r = await executeTool('kb_review_chain', args);
  if (r?.ok === false) return { error: r.error ?? '工具调用失败（没给出原因）' };
  return r?.result ?? { error: '工具回了空结果' };
}

/**
 * **送审闸门**：内核自己判「这条是不是送审」，是就**自己把链跑完**，再把结论交回给模型。
 *
 * ── 为什么要由内核做，而不是写进人设
 *
 * 委托方 2026-10-05 第三次重申「工作流必须走：@守衡 提问/图片/视频/链接 → L4→L5→L6→L7 +
 * 评审链 → 出报告溯源（L0）→ 写飞书」。而那条链本身一直是通的（实测跑过 691s / 771s / 1809s）。
 * 缺的从来不是能力，是**触发**：在此之前「算不算送审」只写在人设里，而**人设是声明，不是约束** ——
 * 09:22 那条视频，模型没想起来要调链，读到了 51 个字却给不出结论，
 * 而盘上**唯一的痕迹是一行没有出现的日志**（`PMO/logs/ws_daemon.log:2498`）。
 * `AGENTS.md` §2.4：指不出哪一行在拦它，就等于没拦。**拦它的就是这一个函数。**
 *
 * ── 三条边界（每条都有代价）
 *
 *   ① **判据是纯函数**（`review_gate.isSubmission`），离线可反向对照：
 *      喂「在吗」不许触发、喂一条光秃秃的媒材必须触发。
 *   ② **补发重放不重跑**（`force`）：链会真写飞书，重跑等于同一单写两遍。
 *   ③ **结论排在那一轮的最前面**（`buildUserTurn` 的 `chainBlock`）：排在读数后面会被盖住，
 *      模型就又开始「描述我读到了什么」了 —— 那正是这次要修的病。
 *
 * @returns {Promise<{question:string, gate:object|null, chainBlock:string,
 *                    chainRan:boolean, chainMs:number}>}
 */
export async function runSubmissionGate({
  inbound, question = '', notify = null,
  // ★ 目标 19（2026-10-10）：消息到达时刻（ms epoch）。PRD §12「飞书群 @Agent 响应时间 ≤5 秒」
  //   量的就是 **tIngress → 回执卡发送完成** 这一段。null ⇒ 不打这条指标（不编数）。
  tIngress = null,
  chainRunner = defaultChainRunner,
  // ★ 模型侧那一遍**必须可注入**（2026-10-06）：它默认会真调 LLM。
  //   不注入的话，将来任何一条「带媒材 + 链跑成」的自证用例都会**真打网络** ——
  //   而 §2.4.4 记的正是这个形状（自证有副作用）。与 chainRunner / publishRunner 同一种做法。
  modelSideRunner = reviewModelSide,
  // ★ 落表这一步**必须可注入** —— 否则单测里一个假结论就会真的往 Owner 的表里写一行
  //   （2026-10-05 实测发生过：自证往真表写了两行，还改了一行的状态）。
  publishRunner = reviewPublish.ensureReviewRow,
  // ★ 2026-10-09：「≥3 时建合并报告」这一步**必须可注入** —— 它默认会**真的在你飞书里建一份云文档**。
  //   不注入的话，任何一条「带媒材 + 链跑成 + 问题数 ≥3」的自证用例都会留下一份真文档
  //   （`Z1`/`Z14` 正是这个形状）—— 与上面 `modelSideRunner`/`publishRunner` 是**同一个形状**
  //   （§2.4.4：跑一次自证，改掉了它要保护的东西）。实测已经发生过一次：写这一条时的探针
  //   真的建了一份文档 `SVqgdEM9KoS5LMxcavmc9QvLntf`。
  mergedReportRunner = publishMergedReport,
  // ★ 2026-10-09：「建议」那一次调用**必须可注入** —— 它默认真打 LLM；
  //   不注入的话每条含条目的自证都会真调模型（与 modelSideRunner 同一个理由）。
  adviceRunner = generateAdvice,
  force = false,
} = {}) {
  if (force) return { question, gate: null, chainBlock: '', chainRan: false, chainMs: 0, verdict53: null };

  const gate = reviewGate.isSubmission({
    text: inbound?.text ?? '',
    imageCount: inbound?.imageCount ?? 0,
    videoCount: inbound?.videoCount ?? 0,
  });
  if (!gate.yes) {
    // ★ 2026-10-14：闸门**判「不是送审」时也要留一行读数** —— 因为一次事故正是
    //   「它判成了送审」。原先这里什么都不打，于是「闸门有没有把这条挡下来」
    //   在盘上是一行不存在的日志（§2.4.1：判据没盖住的那一跳，就是事故所在的那一跳）。
    if (gate.guard) console.log(`[agent] 🧭 送审闸门：不起链 —— ${gate.why}`);
    return { question, gate, chainBlock: '', chainRan: false, chainMs: 0, verdict53: null };
  }

  const input = reviewGate.chainInput({ question, inbound });
  // ★ 2026-10-12（Owner）：「这一步要 6~30 分钟」**是优化前的旧估计，删掉**。
  //   库里早有同一条裁定（`agent/review_gate.mjs:308`：「去掉时长估计」，
  //   依据是实测一条图 3 分 32 秒、而回执写 6~30 分钟）—— 回执卡那侧已改，
  //   但**这行 console 日志漏改**，于是它还在日志里以「守衡自己提示」的样子出现。
  //   判据：`tools/test_agent.mjs` 的「不许再给时长估计」一条（卡片正文口径）。
  console.log(`[agent] 🧭 送审闸门：${gate.kind} —— ${gate.why}｜起链`);
  if (typeof notify === 'function') {
    // ★ 回执要**分开说**「常态 5 分钟」与「在排队」—— 用一个悲观的大区间把两件事糊在一起，
    //   人会以为每条都要半小时（Owner 2026-10-05 当场就是这么读的：「太长了，不正常」）。
    //   排不排队是**读得出来的**：知识库那条循环的认领（`kb_loop_claim`）现在有没有人在持。
    let queued = false;
    try {
      const cs = await claimStatus();
      queued = !!cs && cs.free === false && cs.stale === false && cs.unknown !== true;
    } catch { /* 取不到就不说排队（不谎报） */ }
    // ★ 递过去的是**卡片块**（发送层负责成形）—— 见 `review_gate.ackMessage` 的两条现场裁定。
    //
    // ★★ 目标 19（2026-10-10）：**PRD §12「飞书群 @Agent 响应时间 ≤5 秒」的唯一观测点就在这里。**
    //    为什么是这里：按已定口径（`review_publish.mjs:47`）「P0 问题可先在飞书侧响应」——
    //    回执卡**在跑链之前**发，它就是用户感知到的"响应"；P0 判定在其之后（实测 9.8~27 ms），
    //    不计入这条预算。所以量 `tIngress → 回执卡发送完成` 才是这条指标，不是量整链。
    //    ⚠️ 只记时间、**不参与任何判定**（与 `review.py` 的 `trace.perf` 同一种做法）——
    //    计时器不许改变行为，否则就成了"观测影响被测对象"。
    const _tAck0 = Date.now();
    try { await notify(reviewGate.ackMessage(gate, { queued }).block); }
    catch (e) { console.log(`[agent] · 送审回执没发出去（不影响链）：${e?.message ?? e}`); }
    if (tIngress) {
      const groupResponseMs = Date.now() - tIngress;
      const ackSendMs = _tAck0 - tIngress;
      // 结构化一行，供 `kb/l8/measure_group_response.py` 汇总（**别改字段名**，汇总端按它解析）。
      console.log(`[metric] group_response_ms=${groupResponseMs} ack_decision_ms=${ackSendMs}` +
                  ` prd_limit_ms=5000 verdict=${groupResponseMs <= 5000 ? 'pass' : 'FAIL'}` +
                  ` chat=${gate?.chatId ?? inbound?.chatId ?? '-'}`);
    }
  }
  // ── ★ 2026-10-08：**模型侧与链同时起跑**（方案 §③ 的原话是「互不等待」）──────────
  //
  //   改前是**串行**：`if (chainRan) { await modelSideRunner(...) }` ——
  //   链先跑完（实测 127 / 145 / 417 秒）模型侧才开始，而且**链报错时模型侧根本不跑**
  //   （`if (chainRan)` 把它一起掐掉）⇒ 链库忙/超时的那一单，用户**什么都拿不到**。
  //   实测证据（Owner 2026-10-08 截图那张库忙卡）：链卡在认领上、模型侧本该独立出结论，
  //   却因为绑在 `chainRan` 上而一起没了。
  //
  //   现在：**两路同时起，谁先完谁先等**。链侧慢或坏，模型侧那几条照样进结论
  //   —— 这正是方案说的「没有主判与辅助之分」。
  //   `.catch` 兜在起跑处：模型侧抛异常**不算这一轮失败**，它只是没有产出（边界①）。
  const readings = readingsForModelSide(inbound);
  const modelSideP = modelSideRunner({ readings, question, ask: llm.ask })
    .catch((e) => ({ ok: false, findings: [], dropped: [], ms: 0, error: `${e?.message ?? e}` }));

  const t0 = Date.now();
  let res;
  try { res = await chainRunner(input); }
  catch (e) { res = { error: `起链抛异常：${e?.message ?? e}` }; }
  const chainMs = Date.now() - t0;
  const chainRan = !res?.error;
  let chainBlock = reviewGate.formatChainBlock(res);

  // ── ★ 双轨：**模型侧独立一遍** + 并集合并（2026-10-06）────────────────────
  //
  //   依据：上游技术方案《内容治理技术方案》§③「知识库 ＋ 大模型 双校验」/§④「结果合并输出」——
  //         「模型侧：语义核查与边界判断 → 命中带 位置与理由（**无库内依据**）」
  //         「同一个问题 → 取交集 ／ 不同的问题 → 走并集」
  //   合并判据全在 dual_track.mjs（六行矩阵逐字实现 + 自证 16/7 条）。
  //
  //   ★ 三条边界，一条都不许松：
  //     ① **模型侧跑不成不算失败** —— 回落单轨（只有知识库），结论一个字不改；
  //     ② **模型侧没报东西就不改结论** —— renderMerged 返回 null，仍用链给的那份；
  //     ③ **PASS 门限一个字不改** —— mergedState 要求 kbCovered === true，
  //        而 kbCoveredOf 认不出来时判「没覆盖」（保守一侧）。
  let dual = null;
  {
    try {
      // ★ 与链**并行**起跑的那一路（见上面）：`await` 在这里通常已经完成了。
      //   它**不再**以 `chainRan` 为条件 —— 链没跑成时，模型侧那几条就是这一单的全部产出，
      //   掐掉它等于把「有话说」变成「没话说」。
      const model = await modelSideP;
      // ★★ 2026-10-08（第七批）：**优先用链带回来的引擎 JSON**（结构化逐条依据）。
      //   病灶：从 `answer`（模型组织过的散文）正则抠中文 ⇒ 抠不到就退回重建版
      //   「《知识库》（未给条款号）（锚点：—）」⇒ 命中文字 / 条款号 / 锚点 / 飞书直链全丢。
      //   `res.engine` 是 `review_run.sh` 原样落盘的那份引擎 JSON；读不到就是 null
      //   ⇒ `kbFindingsOf` **原样退回**老路（不许静默少报）。
      // ★★ 2026-10-14：第三格 = P0 快路的**结构化逐条**（`res.p0_findings`）。
      //   没有它，库侧条目只有「命中正则」、没有「逐字命中片段」⇒ `sameOrigin`
      //   恒判「无从比」⇒ 方案 §④「同一个问题 → 取交集」**一次都不成立**
      //   （实测 123 次双轨：`双轨确认`＋`冲突降 REVIEW` 全为 0）。
      //   链那条来路不吃这一格（它走 `res.engine.risk_items`，见 `_kbFromEngineJson`）。
      const kb = kbFindingsOf(res?.answer, res?.engine, res?.p0_findings);
      // ★ 库侧的**结构化读数**（2026-10-07）：结论与条数从这里取 —— 不再只靠正则抠中文答案。
      //   病灶（当天实测，已复现）：PRD §5.3.3 规定问题数 ≥3 时库侧只出分类汇总 ⇒
      //   逐条正则抠不到 ⇒ 库侧被读成「0 条」⇒ 合并把**库侧的 BLOCK 降级成 REVIEW**。
      const kbSide = kbSideOf(res);
      const merged = mergeFindings(kb.findings, model.findings);
      // ★★ 2026-10-14：**模型侧没跑成也要传进合并态**（与 `renderMerged` 里那个同名判据**一处口径**：
      //   `model.ok === false`）。原先只传给卡片文案，**没传进 `mergedState`** ⇒
      //   模型侧解析失败被当成「模型侧 0 条」⇒ 库侧安全词覆盖就能落 **PASS**
      //   （实测 `MC-US-AMZ-B0CWLHKQNT`：模型侧 JSON 解析失败 ⇒ merged=[] ⇒ PASS）。
      const modelFailed = !!(model && model.ok === false);
      const state = mergedState({ kbCovered: kbCoveredOf(res?.answer), merged: merged.items,
                                  kb: kbSide, modelFailed });
      // ── ★★ 2026-10-15（Owner）：置信度 = **两侧各出一个档位 ⇒ 对外只出一个数** ──────────
      //   为什么在这里算：两侧**并行起跑**（见上），只有**合并这一刻**两侧的东西才同时在手
      //   （`kbCovered` / `merged.items` / `model.findings` / `modelFailed`）。
      //   库侧：沿用旁挂里**引擎已算好**的那个数（本处不重算，只分档）；
      //   模型侧：由它自己**已经输出**的命中结构派生（不新增 LLM 字段）；
      //   合并：按 PRD §6.6 三档**取更保守一侧** —— 零自由权重。
      //   模型侧未参与 ⇒ 不产出合并数，退回库侧读数并在 basis 写明（单轨语义不许漂）。
      //   ★★ 2026-10-15（F1 收尾）：**入参这里不许提前 `Number()`** ——
      //   `Number(null) === 0`、`Number('') === 0` ⇒「库侧没有读数」会在进 `mergedConfidence`
      //   之前就被改写成"置信度 0"，然后落进 `focus` 档（0.65）。
      //   `bandOf`/`mergedConfidence` 内部**本来**就按 null 处理（它们的注释就写着这个坑），
      //   是这里多此一举的转换把它毁掉了。⇒ 空值原样透传，交给它们判。
      const kbConfRaw = res?.review?.confidence ?? res?.confidence;
      const kbConfidence = (kbConfRaw === null || kbConfRaw === undefined || kbConfRaw === '')
        ? null
        : (Number.isFinite(Number(kbConfRaw)) ? Number(kbConfRaw) : null);
      const mergedConf = mergedConfidence({
        kbConfidence,
        kbCovered: kbCoveredOf(res?.answer),
        model, modelFailed,
        // ★ `both` = 双轨确认条数（§④「同一个问题取交集」那一格）。
        //   没有它，v1 会把「库侧 PASS/0 条 ＋ 模型侧 2 条」这种**分歧**算成 direct ——
        //   端到端实测（RC-78ce50b3732c）当场抓到这个不自洽，见 dual_track.mjs 里那段注释。
        bothCount: merged.stats?.both ?? 0,
      });
      // ── ★★ 2026-10-15：合并置信度**落一行机读台账** ─────────────────────────────
      //   为什么非落不可：这个数只活在"合并那一刻"的内存里 —— 事后既无法从表行反推
      //   （表行只有结果），也无法从报告反推（报告是散文）。而 Owner 要"两侧统一出一个数"
      //   就必然要**核对历史每一行**，库侧的标定器也**只能读机读件**（不读散文）。
      //   ⇒ 追加式 NDJSON，一行一单；写失败**绝不影响回复**（try/catch，只打日志）。
      //   `KB_CONF_LEDGER` 只给自证/离线验证用（把路径指到临时目录，§2.4.4：自证不许改真数据）。
      try {
        //   ★★ 2026-10-15 实测修：这里原来写的是 `path.join(stateDir, ...)` —— 而
        //   `stateDir` 是从 `config.mjs` 进来的**函数**（`stateDir()`），不是字符串 ⇒
        //   `path.join` 抛 "Received function stateDir" ⇒ **每一单都写不进去**，
        //   而 try/catch 把它降级成一行日志 ⇒ 「台账」这件事**从来没成立过**
        //   （实测：`PMO/shouheng-state/confidence-merged.ndjson` 至今不存在）。
        //   修法 = 调它：`stateDir()`。判据：自证里这条 warn 必须消失，且真跑一单后台账文件出现。
        const lp = process.env.KB_CONF_LEDGER
          || path.join(stateDir(), 'confidence-merged.ndjson');
        // ★ `material_sha8`：按**素材本身**的键。为什么不能用 content_id 当键 ——
        //   实测（2026-10-15）：链"回缓存"时**旁挂不更新** ⇒ `res.review.content_id` 是
        //   **上一单**那个号（四条不同素材落出同一个 `AD-20261015-001`）⇒ 台账按它对齐会串行。
        //   素材哈希永远可得，且与"这一单是哪条素材"一一对应。
        const materialSha8 = createHash('sha256')
          .update(String(inbound?.text ?? ''), 'utf8').digest('hex').slice(0, 8);
        fs.appendFileSync(lp, JSON.stringify({
          at: new Date().toISOString(),
          material_sha8: materialSha8,
          content_id: res?.review?.content_id ?? res?.content_id ?? null,
          state,
          kb_value: kbConfidence,
          kb_band: mergedConf.kb_band, model_band: mergedConf.model_band,
          merged_value: mergedConf.value, band: mergedConf.band,
          model_ok: !!(model && model.ok !== false),
          model_findings: model?.findings?.length ?? null,
          both: merged.stats?.both ?? null, kb_only: merged.stats?.kb_only ?? null,
          model_only: merged.stats?.model_only ?? null,
          basis: mergedConf.basis,
        }) + '\n', 'utf8');
      } catch (e) {
        console.log('[agent] ⚠ 置信度台账没写成（**不影响本单回复**）：' + (e?.message ?? e));
      }
      // ── ★★ 2026-10-09：「建议」的唯一产出者（Owner 的规则）────────────────────
      //   「有填的做参考，agent 输出最终具体建议；没填的 agent 直接出建议」
      //   为什么必须在这里（两侧都回来之后）：模型侧与链**并行**跑，模型侧产出它的发现时
      //   库侧的建议还没到 ⇒「有填的做参考」只能**此刻**做。代价是多一次 LLM 调用。
      //   失败不编：`adviceRunner` 失败就回退到 `renderMergedItem` 里那两套旧逻辑。
      // ★★ 2026-10-09（Owner 追问后的更正）：**只对「需要生成」的条目跑**。
      //   Owner 的期望：「知识库侧 **参考库侧建议** → agent 出最终建议；**模型侧问题就输出模型侧建议**」。
      //   第一版把**所有**条目都送进去了 ⇒ 模型侧本来已经写好的一条建议被**重写**，
      //   既白烧一次生成，两次生成的详略也可能差很多。
      //   判据：有库侧参考 ⇒ 要跑（那就是「参考库侧建议」那条规则）；
      //        没库侧参考但模型侧自己写了 ⇒ **沿用**（`renderMergedItem` 的回退链会印它并标来源）；
      //        都没有 ⇒ 要跑（否则只剩「两侧都没给」）。
      const needsAdvice = (f) => !!((f.kb?.suggestionLine || f.kbAdvice) || !(f.suggestion || f.model?.suggestion));
      const needIdx = merged.items.map((f, i) => (needsAdvice(f) ? i : -1)).filter((i) => i >= 0);
      const needItems = needIdx.map((i) => merged.items[i]);
      let adviceMap = {};
      let adviceNote = null;
      try {
        const ar = await adviceRunner({ items: needItems, readings, question, ask: llm.ask });
        if (ar && ar.ok) {
          needIdx.forEach((origI, k) => { if (ar.advice && ar.advice[k]) adviceMap[origI] = ar.advice[k]; });
          adviceNote = `ok/${ar.ms}ms`;
        } else adviceNote = `失败（回退，不编）：${ar?.error ?? '未知'}`;
      } catch (e) { adviceNote = `异常（回退，不编）：${e?.message ?? e}`; }
      console.log(`[agent] 💡 建议生成：${adviceNote}｜送进去 ${needItems.length} 条（沿用模型侧初稿 ${merged.items.length - needItems.length} 条）｜覆盖 ${Object.keys(adviceMap).length} 条`);
      const itemsWithAdvice = merged.items.map((f, i) => ({
        ...f,
        advice: adviceMap[i] ?? null,
        // 标注说「参考了什么」：库侧那格有值才算参考过（改法始终是模型写的）
        adviceReferencedKb: !!(f.kb?.suggestionLine || f.kbAdvice),
      }));
      const rendered0 = renderMerged(itemsWithAdvice, { state, kb: kbSide, kbTextCount: kb.findings.length, model,
                                                     kbHitsBlock: kb.kbHitsBlock ?? null,
                                                     mergedStats: merged.stats });

      // ── ★ 2026-10-09：**问题数 ≥3 ⇒ 飞书文档要带报告**（Owner 的原话）──────────
      //
      //   病灶：报告只有库侧会建，而它的门槛读的是**它自己的** `issue_count`
      //   （`feishu_publish.py::REPORT_LINK_MIN_ISSUES`）。实测 2026-10-09 09:35 那张图：
      //   卡上说「共发现 **6** 处」（库侧 1 ＋ 模型侧 5）⇒ 按 PRD 该给报告，
      //   而旁挂 `issue_count = 1` ⇒ 库侧不建 docx ⇒ `report_url = null` ⇒ **没有链接可给**。
      //
      //   所以报告改由**本仓**建：门槛读**卡里那个数**（`rendered0.total`），
      //   正文含**两侧全部条目**（Owner：「6 个就展示 6 个问题」）。
      //   走 `review_publish.publishReportDoc()` —— 与库侧同命令同身份，**只建文档不写业务表**
      //   （不去调 `feishu_publish.py`：它 `:495` 的 `rid = None` 让 `:555` 成为死代码 ⇒
      //    每调一次必然在业务表里多一行）。
      //
      //   ★★ 2026-10-09（Owner 裁定「2 先于 1」）：**去掉 `!kbSide?.reportUrl` 这个挡条** ──
      //
      //   Owner 的疑问：「发文案给守衡输出的报告格式是对的，发图片和视频就不对了？」
      //   查清了，成因反直觉 —— 那一行 `!kbSide?.reportUrl` 让两条路**互斥**：
      //     · 文案单：库侧自己 **1 条（<3）** ⇒ 库侧不建 docx ⇒ `kbSide.reportUrl` 空
      //       ⇒ 本仓建了合并报告 ⇒ **卡上链接正确**；
      //     · 图片/视频单：库侧自己 **5 条（≥3）** ⇒ 库侧建了 docx ⇒ `kbSide.reportUrl` 有值
      //       ⇒ **本仓被跳过** ⇒ 卡上链接指向**库侧那份**。
      //   而库侧那份有两个硬伤（我逐字对比过两份文档）：
      //     ① 它**只装库侧条目**，条目数天然对不上卡里那个数（库侧 5 vs 卡内 7）；
      //     ② 它把**库内案例**渲染成「命中」，而守衡那份自带免责
      //        （「库内条目只说明出处，不说明与本次素材相关；相关性以卡片告警为准」）
      //        —— 免责说明正是挡住那个坑的东西。
      //   ⇒ 口径定死：**只要卡内 ≥3，就用本仓那份**。库侧那份降为"库侧自己留的档"，
      //     **不再自动当作卡上的链接**（`reportUrlOverride` 优先于 `kbSide.reportUrl`，
      //     这条在 `renderMerged` 里本来就是这么写的）。
      //
      //   ★ 三条边界（第一条改了，后两条不变）：**卡内 ≥3 一律本仓建**（不再看库侧有没有）；
      //     **失败不阻断结论**（报告与三态是两件事）；**失败必须照 detail 说**
      //     （把 `url=''` 说成「已出报告」是比不建更坏的一面）。
      let reportUrlOverride = null;
      // ★★ 2026-10-14（Owner 本地要求）：「问题数少于 3 个的，也输出审查报告，
      //   格式跟大于 3 个问题数量的审查报告一致」。
      //   ⇒ 去掉「卡内条数 ≥ `REPORT_LINK_MIN_ISSUES` 才建」这道闸：**只要有可并的条目就建**。
      //      （判据 Z17 有一条**反向断言**：源码里不许再出现那个比较式 —— 所以这里也不写它。）
      //   ⚠️ 这是**本地（这批跑/这张表）的要求**，不是 PRD 口径 ——
      //      PRD §5.3.4 / §8.3 与库侧 `feishu_publish.py::REPORT_LINK_MIN_ISSUES = 3` **一个字没动**。
      //      「格式一致」天然成立：报告正文由 `merged_report.mjs` 渲染，它**不按条数分支**
      //      （该件头部明写「不再 import REPORT_LINK_MIN_ISSUES」），<3 与 ≥3 是同一套版式。
      // ★★ 2026-10-15（Owner 报「**链接是空的**」，真单 `MC-US-YT-_xyLF4_AgAw-IMG`）：
      //   **一条条目都没有 ⇒ 不建报告**。
      //   病灶：那一单两侧都没命中（模型侧 0 条 ／ 库侧 `issue_count=0`），
      //   而报告这一跳只看 `rendered0` 真不真 ⇒ 照样建了一份 docx，
      //   里面只有标题 + 结论行 + 「（本单没有并进任何条目。）」⇒ **人点开是空的**，
      //   而卡上还挂着那个链接（「一个点不开的链接比空格更坏」，何况是一个点开没内容的）。
      //   ⇒ 闸改成「**有可并的条目**（`total > 0`）才建」。
      //   ⚠️ Owner 2026-10-14 的本地要求「**<3 也出报告**」**一个字没动**：
      //     只要**有**条目（1 条、2 条都算）就建，格式与 ≥3 完全一致（见下面 Z17 那两条判据）。
      if (rendered0 && rendered0.total > 0) {
        try {
          const at = new Date().toISOString();
          // ★★ 2026-10-13（Owner 第四条）：**渲染两份** ——
          //   投出去的（`mdDoc`）只含 PRD 字段；留底的（`mdFull`）附录照旧完整。
          //   两份的**条目逐字同源**（同一次 `renderMergedReportMd`，只差 `withAppendix`）。
          const _args = {
            // ★ 同一批条目 —— 报告与卡片必须逐字同源（今天已因「两处各写一遍」栽过两次）
            merged: itemsWithAdvice, total: rendered0.total, state, line: rendered0.line,
            // ★ 卡上撤下来的检索读数 → 报告附录（搬不是砍）
            hitsBlock: rendered0.hitsBlock ?? null,
            // ★★ 2026-10-09 晚：卡上撤下来的**媒材读数全文**（Owner 点头「放到附录」）
            mediaAppendix: mediaReadAppendix(inbound),
            question, contentId: kbSide?.contentId ?? '', at,
            kbGap: rendered0.kbGap, kbTextCount: kb.findings.length,
            modelCount: model?.findings?.length ?? 0,
          };
          const mdFull = renderMergedReportMd(_args);
          const mdDoc = renderMergedReportMd({ ..._args, withAppendix: false });
          const pub = await mergedReportRunner(mdDoc, {
            contentId: kbSide?.contentId ?? '', at, archiveMd: mdFull });
          if (pub.ok) {
            reportUrlOverride = pub.url;
            console.log(`[agent] 📄 合并报告已建（问题数 ${rendered0.total}）：${pub.url}`
              + `｜留底（含附录）：${pub.archivePath ?? '(未留)'}`);
          } else {
            console.log(`[agent] ⚠️ 合并报告**没建成**（照实说，不编链接）：${pub.detail}`);
          }
        } catch (e) {
          console.log(`[agent] ⚠️ 合并报告异常（**不阻断结论**）：${e?.message ?? e}`);
        }
      } else {
        // ★★ 2026-10-09：**「跳过了」必须出声**（Owner 问「为什么发图片/视频报告就不对，
        //    发文案就对」——而这一跳当时**一条日志都没有**，只能靠倒推）。
        //   ⚠️ 去掉 `!kbSide?.reportUrl` 挡条之后，走到这里**只剩两种正当原因**
        //      （「库侧已经给了链接」那一种已从结构上消失）：
        //        · `renderMerged` 返回 null（没有可并的条目）；
        //        · ~~卡内总数 < 3（PRD §5.3.4 本就不该给报告）~~
        //          ★ 2026-10-14：**这一种已消失** —— 本地要求改成「<3 也出报告」，
        //            闸只剩「有没有可并的条目」。留此行是为了让下一个人知道它**曾经**是原因。
        const _ru = kbSide?.reportUrl ?? null;
        const _why = !rendered0 ? 'renderMerged 返回 null（没有可并的条目）'
          : `卡内总数 ${rendered0.total} ⇒ 本应已建（走到这里说明上面那一支没进，属异常）`;
        console.log(`[agent] 📄 合并报告：**未建**（${_why}）`
          + `｜卡内总数=${rendered0?.total ?? '—'}｜库侧链接=${_ru ?? '(无)'}`
          + `（kind=${kbSide?.reportUrlKind ?? '—'}）`);
      }
      // ★ 建失败时**仍要看得见**：这一单会回落成「卡上链接指向库侧那份」——
      //   那是**次优**（库侧只装库侧条目），但**有链接好过没链接**。
      //   所以不算失败，只把"回落到了谁"记出来。
      if (!reportUrlOverride && kbSide?.reportUrl) {
        console.log(`[agent] 📄 合并报告没建成 ⇒ **回落库侧那份**（${kbSide.reportUrl}）`
          + '—— 注意：库侧那份只装库侧条目，条目数可能与卡里那个数不一致。');
      }
      const rendered = reportUrlOverride
        // ★ 必须用 itemsWithAdvice —— 有报告链接时走的是这一支，用 merged.items 会把建议丢掉
        ? renderMerged(itemsWithAdvice, { state, kb: kbSide, kbTextCount: kb.findings.length, model,
                                       reportUrlOverride, kbHitsBlock: kb.kbHitsBlock ?? null,
                                       mergedStats: merged.stats })
        : rendered0;
      dual = { model, kb, merged, state, rendered, kbSide, mergedConf, reportUrl: reportUrlOverride };
      // ★ 2026-10-08：**模型侧没跑成时要把 raw 打出来**。
      //   原先只打 `model.error`，而「没跑成」的两种成因——「额度被 reasoning 烧光 ⇒ 正文 0 字」
      //   与「写了散文没写 JSON」——**报的是同一句话**（`输出里没有 JSON 数组`）。
      //   `model_side.mjs:115` 的注释早写着要报 raw 长度，但那一行从来没接上；
      //   实测（Owner 2026-10-08 那张图，日志 `模型侧 没跑成：输出里没有 JSON 数组`）
      //   就是查不下去：不知道是空正文还是散文，也就定不了是加额度还是加解析。
      const modelNote = model.ok
        ? (model.skipped ? '跳过（文字层为空）' : model.findings.length + ' 条 / ' + model.ms + 'ms')
        : ('没跑成：' + model.error
           + (model.raw === undefined
             // 连返回都没拿到（调用抛异常 / 传输失败）—— 与「拿到了但没 JSON」不是一回事
             ? '｜**没有拿到模型返回**（抛异常或传输失败），不是解析问题'
             : `｜raw=${String(model.raw).length} 字`
               + '（0 字 = 额度被 reasoning 烧光；非空 = 写了散文没写 JSON）'
               + `｜raw 首 100 字=${JSON.stringify(String(model.raw).slice(0, 100))}`));
      // ★ 结构化读数与文本抽取**并排打出来** —— 两者不一致时必须看得见（2026-10-07）。
      const kbNote = kbSide.hasSidecar || kbSide.source === 'p0_fastpath'
        ? `${kbSide.source === 'p0_fastpath' ? 'P0 快路' : '机读旁挂'} 结论=${kbSide.state || '—'}`
          + `/${kbSide.issueCount ?? '—'} 条 ｜ 逐条抽出 ${kb.findings.length} 条`
          + (kbSide.refused ? ` ｜ ⛔ **库侧拒答**（${kbSide.reason || '未给原因'}）` : '')
          + (Number.isFinite(kbSide.issueCount) && kbSide.issueCount > kb.findings.length
              ? ' ｜ ⚠️ 明细未抠全（≥3 时库侧按 PRD 只出汇总）' : '')
        : '**读不到机读旁挂**（缺证据要看得见）';
      console.log('[agent] ⚖ 双轨（与链**并行**起跑）｜模型侧 ' + modelNote
        + '｜知识库侧 ' + kbNote
        + ' ⇒ ' + mergeSummary(merged.stats)
        + '｜合并态=' + state
        + '｜改写结论=' + (rendered ? '是' : '否（模型侧没报东西，仍用链给的那份）')
        //   ★ 2026-10-15（F1）：`value` 可能是 `null`（库侧没读数 ⇒ 不出这个数）；
        //     `Number.isFinite(Number(null))` 为真 ⇒ 会打成 `0`（又一次 `null`→`0`）。
        //     没有数就打 `—`，并在后面那格说明档位也是 `—`。
        + '｜置信度(两侧合并)=' + ((mergedConf?.value === null || mergedConf?.value === undefined
            || mergedConf?.value === '' || !Number.isFinite(Number(mergedConf.value))) ? '—' : mergedConf.value)
        + ' [' + (mergedConf?.band ?? '—') + ']'
        + '（库侧 ' + (mergedConf?.kb_band ?? '—') + ' / 模型侧 ' + (mergedConf?.model_band ?? '未参与') + '）'
        + (model.dropped?.length ? '｜⚠ 解析丢掉 ' + model.dropped.length + ' 条：' + model.dropped.map((d) => d.why).join('；') : ''));
      if (rendered) {
        chainBlock = chainBlock
          + '\n\n【★ 双轨合并后的结论（**这一份才是最终的**，代码产出，逐字转述）】：\n'
          + rendered.block;
        // ══════════════════════════════════════════════════════════════════════
        // ★★ 2026-10-13（Owner 裁定）：**查证笔记只进这里 —— 既不上卡，也不进报告正文**
        // ══════════════════════════════════════════════════════════════════════
        //
        //   Owner 原话：「输出到飞书群包含知识库侧+模型侧的文字，**不要展示在卡片上**，
        //   **我问的时候，你要能回答**」，并把那一族口径读数（`知识库侧 … ／ 模型侧 …`、
        //   `ℹ️ 知识库侧给了 覆盖缺口…`、`（问题数 8 ≥ 3 ⇒ 按 PRD §5.3.3 …）`）
        //   逐条列进了「类似以下的文案都去掉」。
        //
        //   位置就是这一处，理由是判据级的：`chainBlock` 是**这一轮**发给模型的正文，
        //   而它同时被 `mem.append` 写进**会话记忆** —— 于是：
        //     · 这一轮：模型看得到 ⇒ 对方问「知识库侧报了几条」它当场答得出来；
        //     · 以后每一轮：记忆里还在 ⇒ 隔一轮再问也答得出来。
        //   而卡片与报告都是从 `rendered.block` 渲染的，**不经过这一段**。
        //
        //   ⚠️ 「不许写进回答」不能只是一句声明（AGENTS.md §2.4）——
        //     执行点有两处：`dual_track` 已经把这几行**从 `block` 里摘掉**
        //     （模型没有可逐字转述的源），信封层还有一道 `stripInternalNotes` 兜底
        //     （模型若照抄，那几行在**进群之前**被拦下并留痕）。
        if (String(rendered.internalNotes ?? '').trim()) {
          chainBlock = chainBlock
            + '\n\n【★ 我的查证笔记 —— **只用来回答对方的追问**。'
            + '它**不上卡、不进报告**：这一轮的回复里**一个字都不许出现**'
            + '（要转述的只有上面那一块）。】\n'
            + String(rendered.internalNotes).trim()
            + '\n【★ 查证笔记结束】';
        }
      }
    } catch (e) {
      dual = null;
      console.log('[agent] ⚠️ 双轨没跑成，回落单轨（结论仍由链给）：' + (e?.message ?? e));
    }
  }
  console.log(`[agent] 🧭 送审链返回：${chainRan ? '跑成' : '没跑成'}｜${chainMs}ms`
    + `${chainRan ? '' : `｜${String(res?.error).slice(0, 120)}`}`);

  // ── 6.0 **每一个评审任务都必须落表**（Owner 2026-10-05 定的硬规矩）
  //
  // ★ 这一条**不能只写在提示词里**：那天送了四条，链跑完 3.5~17.9 分钟，
  //   表里一行都没有 —— 因为链自己的发布条件是「有**三态结论**才发」，
  //   拒答（NEEDS_INPUT）整单被跳过。于是「审过了、结论是拒答」在盘上零痕迹。
  //   现在这段代码是那条规矩的执行点：**链发了就用它那一行（补空字段），没发就我们建一行**。
  //   判据是「表里到底有没有这一行」，不是「链说它发了」。
  let publish = null;
  // ★ 2026-10-09：结论与它对应的表内状态要**活到 `try` 之外** ——
  //   落表读数（下面 `reviewGate.publishFactBlock`）要把它们一起交给模型。
  //   原先 `conclusion` 声明在 `try` 里，出了这个块就取不到（TDZ/作用域），
  //   于是「表里那一行是什么结论」只有表知道，**回话的那一侧看不到** ——
  //   而看不到就会猜（那一张卡就是这么来的）。
  let publishConclusion = null;
  let publishStatus = null;
  try {
    // ★ 结论与两个必录读数**先算好**（`machineNumbers` 需要结论才知道该用哪条口径说明）。
    const chainConclusion = reviewPublish.conclusionOf(res?.answer) ?? (chainRan ? null : 'NEEDS_INPUT');
    // ★★ 表行的结论**必须与用户看到的卡同源**（2026-10-07 实测缺陷）：
    //   卡里写的是**双轨合并后的结论**（`dual.rendered`），而表里原先写的是**链的结论**
    //   （`conclusionOf(res.answer)`）—— 两条来源不同 ⇒ 当天五条**五条都对不上**：
    //     A 表 NEEDS_INPUT ↔ 卡 REVIEW；C 表 BLOCK/3 ↔ 卡 REVIEW/2（**红线在表里是 BLOCK、
    //     在人手里是 REVIEW**）；D 表 PASS ↔ 卡 REVIEW；E 表 NEEDS_INPUT ↔ 卡 REVIEW。
    //   ⇒ 卡里出的是合并结论时，表行就跟它走（`拒答` 落表写作 `NEEDS_INPUT`）；
    //     卡里没出合并结论（模型侧没报东西、回落链条那一段）就仍用链的结论 —— 两者恒一致。
    const mergedConclusion = dual?.rendered
      ? (dual.state === '拒答' ? 'NEEDS_INPUT' : dual.state)
      : null;
    let conclusion = mergedConclusion ?? chainConclusion;
    // ★★ 2026-10-07 加（Owner 同意）—— **库侧没有读数 ⇒ 不许落 PASS**。
    //   为什么（实测，不是假设）：素材「这条社媒文案能不能发：这批婴幼儿用品的文案里写了医用级」
    //     （表行 `recvxlAvpEWMIX`）旁挂没读到 ⇒ 库侧**一个读数都没有**，
    //     而这一行落的是 `Agent 结论=PASS` / `状态=PASS` / `问题数量 0` / `置信度 0`。
    //     同一批另一条（旁挂读到了、`state=NEEDS_INPUT`）落的是 NEEDS_INPUT/待审 ——
    //     差别不在素材，在**有没有读数**。
    //   ⇒ 这条闸是**单向**的（只挡 PASS，不动 BLOCK/REVIEW/NEEDS_INPUT）：
    //     PASS 是唯一的「放行」态，也是唯一不可挽回的错（放出去的物料收不回来）。
    //     而且它**不新造判据**：库侧没读数时，链的结论本来就是 agent 自己写的话，
    //     而「未命中 ≠ 合规」是库的硬口径 —— 没读过库，凭什么说合规。
    const kbReadings = kbSideOf(res);
    const kbNoReading = chainRan && kbNoReadingOf(kbReadings);
    let passBlockedByNoReading = false;
    if (kbNoReading && String(conclusion ?? '').toUpperCase() === 'PASS') {
      conclusion = 'NEEDS_INPUT';
      passBlockedByNoReading = true;
    }
    const nums = reviewPublish.machineNumbers(res, conclusion, dual?.mergedConf);

    // ── 产品线 / 渠道：**先 KB 命中记录，再素材原文兜底**（Owner 2026-10-06）─────────
    //   · 第一优先：命中记录里的 `品线`/`平台`/`渠道/市场`
    //     （P0 快路 ⇒ `res.product_line`；评审链 ⇒ 机读旁挂的 `facets`）
    //   · 兜底：**素材原文**里逐字命中库内受控词 —— 图片/视频那类没有规则命中时，
    //     这是唯一诚实的来源（词表与判据全在库内 `kb/l5/l0_facets.py`，这里只转发）
    //   · 都取不到 ⇒ **空**（不写「未指定」充数，也不让模型猜：
    //     表里那格曾被写进整段视频读数）
    let productLine = String(res?.product_line || res?.review?.facets?.product_line || '').trim();
    let channel = String(res?.channel || res?.review?.facets?.channel || '').trim();
    if ((!productLine || !channel) && input.text) {
      const fb = await facetsFromMaterial(input.text);
      if (!productLine && fb.product_line) productLine = fb.product_line;
      if (!channel && fb.channel) channel = fb.channel;
    }

    // ── 汇总列（顺序语句，不再用三元套三元）──────────────────────────────────────
    //   ★「不许自相矛盾」的老账都在这儿：P0 命中**不许**写「链已跑完」（它根本没跑链）；
    //     拒答**必须**写原因码（否则看表的人不知道是库的缺口还是调用方的缺口）。
    let summaryText;
    if (!chainRan) {
      summaryText = `链**没跑成**（${String(res?.error ?? '未知原因').slice(0, 300)}）—— 本行是为了留痕：`
        + '这一单**没有结论**，不是「没问题」。';
    } else if (res?.p0_fastpath) {
      // ★ P0 命中时**不许**再写「链已跑完」—— 它根本没跑链。这是行内自相矛盾的来源之一。
      summaryText = `**P0 快路**（确定性匹配，${res.p0_fastpath.elapsed_ms} ms ｜ 命中 `
        + `${res.p0_fastpath.matched_patterns} 条 P0 模式`
        + `${res.p0_fastpath.rule_codes?.length ? `：${res.p0_fastpath.rule_codes.join('、')}` : ''}）。`
        + '**未跑** L4→L5→L6→L7 层前置与评审链；置信度按 **1.0** 记'
        + '（= 确定性命中，PRD §6.6：P0 不适用置信度分流）。'
        // ★ 报告成没成，这一格里要看得见（Owner 2026-10-06「补充报告」）。
        //   没成时**写明原因**，不写「待生成」那种含糊话 —— 那句话读起来像"马上就有"。
        + (res?.report
            ? ` 报告：${res.report}`
            : ` 报告：**未生成**（${String(res?.report_detail ?? '未给原因').slice(0, 200)}）`);
    } else if (res?.review?.refusal) {
      // ★ 2026-10-05（Owner 裁定「建议1」）：**拒答必须在表里说明为什么**。
      //   原因码与读数都是**引擎自己算的**（`with_kb_evidence.py` 拒答分支），这里只搬不算。
      // ★ 2026-10-07 修：原先条件写的是 `refusal.reason_code` —— 而**供给链超期那类拒答的
      //   `refusal` 里没有 `reason_code`，只有中文 `reason`**（实测 E 单）。于是这类拒答
      //   掉进下面那条「链已跑完…结论原文见对话与报告」的兜底话术里 —— **一句听起来像
      //   正常结论的话**。现在只要求 `refusal` 存在，原因码与原因哪个有写哪个。
      const rf = res.review.refusal;
      summaryText = `链已跑完（${Math.round(chainMs / 1000)}s）。**未能得出结论**（${conclusion ?? 'NEEDS_INPUT'}）`
        + (rf.reason_code ? `｜原因码 \`${rf.reason_code}\`` : `｜原因 \`${String(rf.reason ?? '未给').slice(0, 60)}\``)
        + (rf.human ? `：${rf.human}` : '')
        + (rf.coverage?.top_hit_anchor
            ? `｜Top 命中 ${rf.coverage.top_hit_anchor}` : '');
    } else if (kbNoReading) {
      // ★ 2026-10-07（Owner 同意）：**库侧没读数**这一格必须自己说清楚 ——
      //   原先它会掉进下面那条「链已跑完…结论原文见对话与报告」的兜底话术，
      //   **那句话读起来像一次正常结论**（实测素材 D 就是这么落表的）。
      summaryText = `链已跑完（${Math.round(chainMs / 1000)}s）。**本单知识库侧没有读数**`
        + '（没跑到引擎 ／ 机读旁挂没落 —— 库忙、层闸门红、或没走 `review_run.sh`）⇒ '
        + '**本次没有知识库三态结论**：本行只作留痕，**不得当通过依据**。'
        + (passBlockedByNoReading
            ? ' ⚠️ 链原文里出现 PASS，**已按闸门改记「未判」** —— 没读过库就不许放行（库口径：未命中 ≠ 合规）。'
            : '');
    } else {
      summaryText = `链已跑完（${Math.round(chainMs / 1000)}s）。结论原文见对话与报告；`
        + '本行由守衡在链返回后核对落表。';
    }
    // ★★ 2026-10-09 **口径统一（Owner 裁定）**：表里「问题数量」改成**卡里那个合并总数**。
    //
    //   原口径（2026-10-07 起）：表里记**库侧机器读数**，卡里是并集上限 ⇒ 两者恒不同，
    //   差额写在这一格里。Owner 看过两轮（卡 7 处 / 表 5）后定为「统一成卡里那个数」：
    //   同一个数在三个地方（卡片抬头、报告门槛 PRD §5.3.4 的 ≥3、表列）必须是**同一个**，
    //   否则人拿着表去对卡永远对不上。
    //   ★ 库侧那个读数**不丢**：它原样留在下面这一格里（「库侧 N 条（机器读数）」），
    //     差从"看不见"变成"看得见且同一个数"。
    //   取值来源仍是 `dual.rendered.total`（PRD §5.3.4 报告门槛读的也是它）——
    //     拿不到合并数（没跑双轨 / 模型侧没报东西）时**回落**库侧读数，行为与改动前逐字相同。
    if (dual?.rendered) {
      const cardTotal = dual.rendered.total ?? null;
      if (Number.isFinite(cardTotal)) {
        summaryText += `｜双轨合并：卡内总数 **${cardTotal} 处**（库侧 ${dual.kbSide?.issueCount ?? '—'} 条机器读数`
          + ` ＋ 模型侧 ${dual.model?.findings?.length ?? 0} 条，重叠未判）；`
          + `**本列「问题数量」按卡里那个数记**（Owner 2026-10-09 定）——`
          + `与库侧机器读数不同时，差在模型侧那几条「无库内依据」的条目上。`;
      }
    }
    // ★ **口径必须跟数一起进表**（Owner 2026-10-06「不允许为空」）：
    //   `machineNumbers()` 在替换过任何一个读数时给出说明（例如「置信度按 0 记 ——
    //   0 = 引擎未做判定，不是"零风险"」）。留空时没人看得懂；**填了 0 却不说口径
    //   同样没人看得懂** —— 一个 0 看起来像一个结论。`note` 为空时不追加任何东西。
    if (nums.note) summaryText += ` ⚠️ ${nums.note}。`;
    // ★ 产品线/渠道为空时**写明为什么空** —— 一个空格说不出是「库里没有」还是「我们没读到」，
    //   而这两件事要人做的动作完全不同（补登记 vs 查取数）。所以**空也要有原因**。
    if (!productLine || !channel) {
      const miss = [!productLine && '产品线', !channel && '渠道'].filter(Boolean).join('、');
      summaryText += ` ⚠️ ${miss}：**库内命中记录与素材原文都没有** ⇒ 留空，需人工补。`;
    }

    // ★ 2026-10-09：**在落表之前**把「这一行会写什么结论/状态」记下来 ——
    //   落表读数（下面那段）要连着结论与状态一起交给模型，缺了哪一个都会让它去猜。
    publishConclusion = conclusion;
    publishStatus = reviewPublish.statusOf(conclusion);

    publish = await publishRunner({
      contentId: reviewPublish.contentIdOf(input.text),
      question: input.question,
      contentType: gate.kind === 'media' ? '图片/视频' : (gate.kind === 'link' ? '链接' : '文字'),
      conclusion,
      // ★ 2026-10-06 **重定口径**（Owner 现场：「置信度**和问题数量不允许为空**」；
      //   并指出「这些问题昨天修复过了，今天又复现了」——昨天那次（10-05）修的是
      //   「引擎给了值却没传出来」，**没修「引擎不给值时留空」**，于是今天原样复现）。
      //   ⇒ 现在走 `reviewPublish.machineNumbers()`：**永不为空**，且填了数就**同时填口径**
      //     （口径拼进下面的 `summary`，看表的人不必来问）。详见那个函数的注释。
      //   取值来源仍是**只搬不算**：P0 ⇒ 快路带出；链 ⇒ 机读旁挂（原样搬自引擎 JSON）。
      //
      // ★★ 2026-10-09 口径统一（Owner 裁定）：**卡里那个合并总数优先**。
      //   理由与写法见上面 `summaryText` 那段注释：同一个数在卡片抬头、PRD §5.3.4 的
      //   ≥3 门槛、以及这一列必须是同一个。拿不到合并数时回落 `nums.issueCount`
      //   （= 改动前的行为，逐字未变）。
      issueCount: Number.isFinite(dual?.rendered?.total) ? dual.rendered.total : nums.issueCount,
      confidence: nums.confidence,
      // ★ 产品线 / 渠道（2026-10-06）：Owner 要求「从知识库命中产品线和渠道的都填写进去」。
      //   · P0 快路 ⇒ `res.product_line` / `res.channel`（`kb/l5/p0_fastpath.py` 从命中记录取）
      //   · 评审链   ⇒ `res.review.facets`（机读旁挂里由 `kb/l5/l0_facets.py` 取，同一个取数点）
      //   **取不到就是空 ⇒ 不写这一格**：不写「未指定」充数，也不从素材正文猜
      //   （表里已经出现过一次脏数据：产品线那一格被写进整段视频读数）。
      productLine: productLine || null,
      channel: channel || null,
      // ★ 报告链接（2026-10-06，Owner「补充报告」）——
      //   PRD §8.2 把「报告链接」列为字段、§8.3 要求问题数 ≥3 时填。
      //   此前**这一格从没被传过**（`rowFieldsOf` 早就支持 `reportUrl`），于是 4 行全空 ——
      //   包括那条 REVIEW/3：报告条件明明满足，链接却没人送过来。
      //   取值：P0 快路 ⇒ `res.report`（`tools.mjs` 建完云文档带出）；
      //         评审链   ⇒ 发布件自己写（它 upsert 同一行，不走这里）。
      //   **空就是空**：没建成不许写占位符 —— 一个点不开的链接比空格更坏。
      //
      // ★★ 2026-10-09 补第三处来源（实测空档）：**本仓建的「双轨合并报告」**。
      //   10-09 15:28 那一单（`recvxxfQoRewaF`／AD-20261009-028）实测：卡内 3 处 ⇒
      //   本仓建了合并报告、URL 也进了卡片（`dual.reportUrl` → 信封的 `reportLink`），
      //   而**表里「报告链接」是空的** —— 因为这一格只认 `res.report`（链侧那份），
      //   而链侧那单只有 1 条、达不到它自己的 ≥3 门槛。
      //   ⇒ Owner 的原话是「把能填的都填了」（2026-10-05），卡里有的链接表里也得有。
      //   ★★ 2026-10-09（Owner：「这 3 个要改成一致的」）**顺序反转** ────────────────
      //   病灶（实测 2026-10-09 16:24 那单，逐字可核）：
      //     卡上链接 = `docx/M7DbdQUvbopAkmxGdsRccGstnTg`（**本仓合并报告**）
      //     表里链接 = `docx/Y2Gxd8BAbonVKrxgPWQcKkwRneb`（**库侧那份**）
      //     ⇒ **同一单两份文档、两个链接**。成因有两层：
      //       ① 这一行的回落顺序把**链侧那份**排在前面，而链侧 `with_kb_evidence`
      //          只在**它自己** ≥3 时建文档（本单库侧正好 5 条 ⇒ 建了）；
      //       ② 链侧建完是把 URL **直接 upsert 进这一行**的，而它跑在守衡落表**之后**
      //          ⇒ 本仓写进去的合并链接被它**覆盖**。
      //     ⇒ 两层一起修：这里**合并报告优先**；`kb_review_chain` 另有一处配套
      //       （`SHOUHENG_OWN_REPORT`：本仓会建报告时，**不让链侧再建它自己那份**）。
      //       「一单一个数、一个链接」——库侧那份只装库侧条目，不是卡上那一份。
      reportUrl: dual?.reportUrl || String(res?.report ?? '').trim() || null,
      // ★ 汇总改成**顺序语句**（2026-10-06）—— 原来是「三元套三元再拼字符串」，
      //   往里加一句口径就写出语法错（实测：`node --check` 报 `Unexpected token ')'`，
      //   而我把 `node --check … | head` 的退出码当成了通过：**管道会吞掉退出码**）。
      //   同一段文字要能被下一个人读懂并安全地改，就别用括号杂技。
      // ★ 2026-10-13（Owner）：「模型侧输出问题必须带依据的 url，**这个要落库**」——
      //   卡上会滚走、报告要另点一次，而**表是这一单最长寿的那份记录**。
      //   依据不进表，等于它没被留住。逐条一行、只列**有依据**的条目（见 `evidenceBlock`）。
      //   ⚠️ 条目在 **`dual.merged.items`**（不是 `dual.items`）—— 我第一版写的就是 `dual.items`，
      //     传进去一个 `undefined`，于是依据块**永远是空**，而日志、卡片、表行都不会报错。
      //     接线判据见 `test_agent.mjs` 的「逐条依据必须接在**真的条目数组**上」。
      //
      // ══════════════════════════════════════════════════════════════════════════
      // ★★ 2026-10-15（Owner 裁定）：**这一格改成 PRD §5.3 的摘要块** ────────────────
      // ══════════════════════════════════════════════════════════════════════════
      //   Owner 原话（两条）：
      //     ① 「80 条的分类问题汇总，直接按照 prd 的要求出问题分类汇总，**覆盖**飞书文档中旧汇总，
      //         不用新建字段」（要的是 PRD §5.3.2/§5.3.3 那三样：结论行 · 分类汇总 · 报告链接）
      //     ② 「模型侧输出问题必须带依据的 url，这个必须要有，**命中知识库侧的也是要带依据的 url**」
      //   ⇒ 一格装两样，顺序即优先级：**PRD 块在上**（人先看到摘要），依据块在下（可回源），
      //     口径说明（⚠️ 那两句）压尾。
      //   ★ 复用**卡片那一份** `dual.rendered.block` —— 它与群里的卡**逐字同源**，
      //     所以 PRD 要的四样（结论行／分类汇总／报告链接／动作行）一个字都不用在这儿重写，
      //     也就不会有第二份口径（本库因为「同一个东西两个产出者」栽过多次）。
      //   ⚠️ 已知缺口（照实写着，别以为已经覆盖）：**模型侧没报东西**时 `rendered` 为 null
      //     （`renderMerged` 那一支要求「有可并的条目」），这一支仍走老写法 `summaryText`。
      //     要把它也 PRD 化，得把 `verdict53`（PRD 结论行）的取值点提到这之前 —— 见
      //     `PMO/` 的待办记录，不在本次改动里硬凑。
      //     原先这里内联一份，卡片那边另一份，正是这一格「同一单两个长相」的来源（FIX-018）。
      // ══════════════════════════════════════════════════════════════════════════
      // ★★ 2026-10-15（Owner）：「**这一格只放 PRD 的『审查结论』块，不要自己加其他内容**」──
      // ──────────────────────────────────────────────────────────────────────────
      //   格式（Owner 给的逐字样例）：
      //     【审查结论：BLOCK】共发现 9 处必须修改。
      //     逐条问题
      //     · 合规类问题：2 个 …
      //     · 另有 3 条（明细在报告里）
      //     → 查看完整问题清单与修改建议：<报告链接>
      //     请修改后重新提交。
      //   ⇒ 直接给**卡片那一份** `dual.rendered.block`（逐字同源 ⇒ 同一单不会有第二种长相）。
      //   此前挂在这一格里的三样**全部撤掉**（它们不是 PRD 要的内容）：
      //     · 【逐条依据（落库留痕）】（带 url）—— 依据在报告里（PRD 的设计＝摘要 ＋ 钻取报告）；
      //     · 「双轨合并：卡内总数…」读数句 —— Owner 2026-10-13 已定这类口径读数不上卡，
      //       同一条理由对表也成立（表与卡是同一条结论的两个落点）；
      //     · ⚠️ 置信度 / 产品线·渠道的口径说明 —— 置信度有它自己那一列。
      //   ⚠️ 与旧裁定（2026-10-09「口径必须跟数一起进表」）冲突 ⇒ **以本条为准**；
      //      行为判据 `test_agent.mjs` 的 V6 已随之改写（原版要求格里有「库侧 N 条机器读数」）。
      summary: (() => {
        const block = String(dual?.rendered?.block ?? '').trim();
        if (block) return block;
        // 模型侧没报东西 ⇒ 没有 `rendered.block`，但这一格仍要是 PRD 形状：
        //   结论行取「合并态派生」或「链自己的答案」；两处都没有（拒答/未判）才回落旧写法。
        const count = Number.isFinite(dual?.rendered?.total) ? dual.rendered.total : nums.issueCount;
        const line = deriveVerdictLine({ mergedState: conclusion, mergedCount: count })?.line
          || deriveVerdictLine({ answer: String(res?.answer ?? '') })?.line || '';
        return line || summaryText;
      })(),
    }, { since: t0 - 1000, question: input.question, ctx: { actor: 'shouheng/review-gate' } });
    console.log(`[agent] 🧭 落表：${publish?.ok ? publish.action : '失败'}`
      + `${publish?.record_id ? `｜${publish.record_id}` : ''}`
      + `｜回读=${publish?.readback ?? '（未回读）'}`
      + `${publish?.ok ? '' : `｜${String(publish?.detail).slice(0, 140)}`}`);
  } catch (e) {
    console.log(`[agent] ⚠️ 落表抛异常（不影响回话）：${e?.message ?? e}`);
  }

  // ── 6.1 **把落表读数交给模型**（2026-10-09）
  //
  // ★ 病灶（Owner 拿着截图来问的那张 alert 卡）：那一单链停在 L6 闸门红，
  //   **表其实落了行**（`recvxwCWhwCO68`／状态=待审），而卡片上写着
  //   「飞书表也没落这一行（拒答档）」—— **与盘上事实相反**。
  //   根因不在模型：`chainBlock`（它唯一看得到的读数）在链返回时就定稿了，
  //   而落表**发生在那之后**，读数从没进过它的上下文 ⇒ §2.4.1
  //   「读数是空的，模型就用猜的填」。修法与 §2.4.4/§2.4.5 同一条：
  //   **把判据放到接线里** —— 读数由代码产出、随 `chainBlock` 一起交出去，
  //   模型只剩「照抄」这一条路可走。
  // ★ 位置必须在 `buildUserTurn` **之前**：那个调用在下面 `return` 里，
  //   而 `chainBlock` 是它唯一的输入来源。
  chainBlock = chainBlock
    ? `${chainBlock}\n\n${reviewGate.publishFactBlock(publish, { conclusion: publishConclusion, status: publishStatus })}`
    : reviewGate.publishFactBlock(publish, { conclusion: publishConclusion, status: publishStatus });

  // ★★ 2026-10-12 19:40（**Owner 现场指示：马上恢复**）——
  //   `p0ShortReplyBlock(res)` 的拼接**已停用**，这一路回到 17:54 之前的行为。
  //
  //   证据（两条都是 `PMO/logs/ws_outbound.jsonl` 的原文，同一条送审单、同一路 P0 命中）：
  //     · 16:58（停用前的样子，1336 字）：两轨计数行「知识库侧 1 条 ＋ 模型侧 1 条 ＝ 本卡 2 处」
  //       ＋ 逐条明细（原因/依据/建议/判定）＋ 页脚「本结论为 P0 红线拦截…」—— 三样都在。
  //     · 19:31（拼接生效后的第一条，309 字）：上面三样**全没了**，取而代之的是
  //       「命中：P0 模式 H05｜条款 **W-1.33**｜逐字命中…」「边界：P0 快路，**未跑** L4→L5→L6→L7…」
  //       「表行：`recvxBEbetGBmm`」—— 条款号、流水线层名、飞书行号都是**内部标识**。
  //   19:31 那张卡与指令**逐条对得上**（保留结论行/模式与条款号/报告链接、不展开明细、309 ≤ 300 字）
  //   ⇒ 这**不是代码写错了，那就是这条指令要的产物**；Owner 不要这个产物。
  //
  //   ⚠️ 常量与纯函数 `p0ShortReplyBlock` **保留**（`tools/agent/p0_short_reply.test.mjs` 在测它们），
  //      但**接线没了 ⇒ 这个功能当前不生效**。要重启这条线，先解决两件事：
  //        ① 「短」不该以丢掉卡面结构为代价（两轨计数行是 Owner 反复要求过的那个数）；
  //        ② 条款号 / 层名 / 飞书行号**不进群**（与「库内命中（读数）」同一个病）。
  //   {
  //     const shortBlock = p0ShortReplyBlock(res);
  //     if (shortBlock) chainBlock = chainBlock ? `${chainBlock}\n\n${shortBlock}` : shortBlock;
  //   }

  return {
    question: buildUserTurn({ questionText: question, chainBlock }),
    gate, chainBlock, chainRan, chainMs, publish,
    // ★ 2026-10-08：`dual` 必须**从这里出去** —— 它是「这一单双轨到底做了什么」的唯一读数，
    //   调用方（`handleMessage` 的 meta）与判据都要用。此前它只活在本函数的局部作用域里，
    //   外面拿不到 —— 于是 `Z1` 那条行为级断言连被测对象都取不到。
    dual,
    // ★ PRD §5.3 结论行的**权威出处**（2026-10-06 加）。
    //   为什么在这里算而不在发送层猜：这一层是**唯一**同时拿得到链原文与 P0 快路读数的地方，
    //   而结论行只许由链（或 P0 派生的那一行）说了算 —— 模型的措辞不参与这一格。
    //   拿不到就回 null（**不编**）：不是送审、链没给三态、拒答（5.3 不管这一态）都会回 null。
    // ★ 双轨合并**改写结论原文**时以它为准（dual.rendered 只在模型侧真报了东西时才非 null）
    //   —— 结论行与逐条块仍由这同一个 deriveVerdictLine 产出，分工没变：模型不写、代码搬。
    //
    // ★★ 2026-10-08/09：**抬头那个 N 改用双轨合并条数**（Owner 的规则：「双轨按照 PRD
    //   ≧3 个问题输出报告链接到飞书文档」）。
    //
    //   病灶（今天才定位到精确那一行）：`dual.rendered.block` 里的 §5.3 结论行是
    //   `renderMerged()` **照搬链的原文**，而合并条数只出现在条目列表里 ——
    //   **抬头与条目从来就没有共用过一个数**。实测三处打架（19:08 那张图：
    //   抬头 12 ／ 阈值读的旁挂 5 ／ 你实际看到 7 条）。
    //   而报告链接的门槛（PRD §5.3.4「问题数量 ≥3」）挂在这三个中的任何一个上，
    //   卡片与规则都会继续各说各的。
    //
    //   现在：抬头、逐条块、以及后面的报告阈值**读同一个变量** = 双轨合并条数。
    //   `deriveVerdictLine` 的第 ⓪ 支（`prd53.mjs`）在拿到合法条数时以它为准；
    //   拿不到（没跑双轨 / 合并 0 条 / 坏读数）就**退回抠链的正文**，行为与改动前逐字相同。
    verdict53: deriveVerdictLine({
      answer: dual?.rendered?.block ?? res?.answer,
      p0Fastpath: res?.p0_fastpath ?? null,
      // ★★ 更正（2026-10-09）：**这里必须用 `rendered.total`，不是 `merged.items.length`。**
      //   两者的口径不同，而 `total` 才是卡里那个数：
      //     `total = 能并的条目 + kbGap（库侧有、但明细没并进来的） + covEntries（覆盖缺口那 1 条）`
      //   （`dual_track.mjs:1140`）。实测 19:08 那单：合并 7 ＋ 库侧未并进 5 = **12** ——
      //   那个 12 **不是**从链的正文里抠的，是 `total` 的正确读数，卡里另有一句
      //   「另有 5 条未并进本卡」。我第一版接成 `items.length`（=7）会**把「+5」丢掉**，
      //   并与卡里那句话自相矛盾 —— 那是个真回归，已改回。
      mergedCount: dual?.rendered?.total ?? null,
      mergedState: dual?.state ?? null,
    }),
    // ★★ 2026-10-08 —— 这两行是**台账**（给日志与补发判据看），**不许把一条正常回复搞崩**。
    //   实测两个崩点（都在同一天的并行双轨改动里进来）：
    //     ① `dual: g?.dual ? …` —— `g` 在这个作用域里**不存在** ⇒ **每次闸门返回**都
    //        `ReferenceError: g is not defined`（`行为级·闸门`＋`子进程端到端`两条判据当场变红，
    //        而线上表现是「每条送审都没有回复」）。已改回 `dual`。
    //     ② `dual.merged.stats` 无保护 —— 链没跑成时 `dual` 在、`merged` 不在 ⇒
    //        `Cannot read properties of undefined (reading 'stats')`（`Z1` 变红）。
    //   ⇒ 台账字段一律**取值容错**：取不到就 `null`，宁可少一个读数，也不许抛。
    // ★★ 2026-10-08（第二轮）：**把库侧拒答的「原因码」带出去**。
    //   为什么非要它：下面 `chainUnmeasured` 要判「值不值得补发」，
    //   而「库忙（认领被占）」与「库里确实没有可依据的条款」在旧判据里**长得一模一样**
    //   （都是「没拿到三态结论」）⇒ 后者被反复补发：同一条最多重跑 5 次链、群里多 5 条回复，
    //   而**重跑一百次还是同一个答案**（它不是瞬态的）。判据要靠这个码，不能靠猜。
    dual: dual ? { state: dual.state, stats: dual.merged?.stats ?? null,
                   ok: dual.model?.ok ?? false,
                   model_ms: dual.model?.ms ?? null, overrode: !!dual.rendered,
                   // ★ 2026-10-15：**两侧合并后的置信度**必须从这里出去 ——
                   //   它是表行那一格的值来源（`machineNumbers(res, conclusion, dual.mergedConf)`），
                   //   不投影出去的话，daemon 的 meta/留痕读不到"这一单最后算出来是几"，
                   //   正是本仓治过的「改了但没人读」。库侧与模型侧两个档位**一并带出**，
                   //   好让事后能回答"这个数是被哪一侧拉低的"。
                   mergedConf: dual.mergedConf
                     ? { value: dual.mergedConf.value ?? null,
                         band: dual.mergedConf.band ?? null,
                         kb_band: dual.mergedConf.kb_band ?? null,
                         model_band: dual.mergedConf.model_band ?? null,
                         basis: dual.mergedConf.basis ?? null }
                     : null,
                   // 2026-10-09: 本仓建的那份合并报告的 URL —— daemon 拿它搬进卡片可见格
                   reportUrl: dual.reportUrl ?? null,
                   // ⚠️ 2026-10-13：`p0Boundary` 那一格撤了 —— 卡脚边界整个不上卡
                   //   （Owner：「整个都隐藏，不要展示在卡片上」）。
                   //   它现在走 `renderMerged` 的 `internalNotes`（记忆侧），答得出来、不上卡。
                   // ★ 2026-10-09：**卡里那个「问题数」**（`rendered.total`）必须从这里出去 ——
                   //   它是 PRD §5.3.4 报告链接门槛（≥3）该读的那个数。
                   //   口径 = 能并的条目 ＋ 库侧未并进的（`kbGap`）＋ 覆盖缺口那 1 条，
                   //   **不等于** `stats.merged`（那个只是「并进来几条」，实测 19:08 是 7，而卡里是 12）。
                   total: dual.rendered?.total ?? null,
                   // 库侧读数的**身份与原因**（取不到就 null，不许编）
                   kb: dual.kbSide ? { has_sidecar: dual.kbSide.hasSidecar === true,
                                       state: dual.kbSide.state || null,
                                       reason: dual.kbSide.reason || null,
                                       refused: dual.kbSide.refused === true,
                                       coverage_gap: dual.kbSide.coverageGap === true } : null,
                 } : null,
  };
}

/* ─────────────────── 主处理函数 ─────────────────── */

/**
 * 把「人问的话 + 图块 + 视频块」拼成**真正发给模型的那一轮**。
 *
 * ★ 为什么把它拆成一个**能被调用**的纯函数（2026-10-05 晚）：
 *   现场那次验收里，视频读到了（8/8 帧、51 字、音轨无人说话），
 *   但**回复是用另一条消息的那一轮生成的** —— 两条消息（先发视频、再单独发一句
 *   「审核下这个视频」）本来就是**两轮**，而「单独发一句」那一条没有 `parent_id`，
 *   按 §2.6 就不该去捞那条视频。人看到的却是「我拿不到那 51 个字」，很像接线断了。
 *   当时没有任何断言看得住这一跳 —— 第 15 组那条「必须走到模型那一侧」其实只走到
 *   `readInboundContent`，**名字比它验的事大**（§2.4.1）。
 *   现在这一跳有了名字、有了调用点，判据能真的走进去（第 16 组那条端到端）。
 */
/**
 * 这一轮**带了媒材、却没起链**吗？（纯函数，可被单测直接调用）
 *
 * ★ 为什么要有它（2026-10-05）：那次事故的表现就是「视频读到了、结论一个字没有」，
 *   而在盘上，这个形状**只是一行没有出现的日志** —— 没有任何东西会红。
 *   判据不能只写在人设里（那是**声明**）：这里把它变成一个**能被调用**的读数，
 *   由 daemon 在每一轮回复之后问一次，答「是」就打一行 `⚠`。
 *
 * @param {{media?:{images?:number,videos?:number}, toolTrace?:Array<{tool:string,ok:boolean}>}} meta
 * @returns {null|{media:number, tools:string[]}} 没起链时回读数，起了链（或本来就没媒材）回 null
 */
export function mediaWithoutChain(meta) {
  const m = meta?.media ?? {};
  const n = (m.images ?? 0) + (m.videos ?? 0);
  // ★ 2026-10-05 改：判据从「带了媒材」升级为「**闸门判成送审**」。
  //   闸门（内核自己跑的）会把该起链的那些先跑掉，所以这个函数现在的职责是**兜底**：
  //   闸门判成送审、却既没跑成链、模型自己也没补上 —— 那就是真的漏了，必须喊出来。
  const gateYes = meta?.gate?.yes === true;
  if (!n && !gateYes) return null;          // 既没媒材、闸门也没判送审 → 这条不适用
  const chain = meta?.chain ?? null;
  if (chain?.ran) return null;              // 闸门跑成了
  const trace = meta?.toolTrace ?? [];
  // 只认**成功**的那一次：`ok:false` 的链等于没跑成，那正是要说的另一种话。
  if (trace.some((t) => t.tool === 'kb_review_chain' && t.ok)) return null;
  return { media: n, gate: meta?.gate ?? null,
           chainTried: !!chain, chainOk: chain?.ran === true,
           tools: trace.map((t) => t.tool) };
}

/**
 * 「这一轮到底读到了什么」——**纯函数**，给一句人话读数（没有媒材时返回 null）。
 *
 * ★ 为什么把它抽出来（2026-10-06，Owner 原话：「视频还是无法读取」）：
 *   这条读数原先**只进日志**。于是卡片正文通篇在讲知识库自己的事
 *   （「覆盖判据不成立」「缺的是库覆盖，补素材无用」），**一句没讲他视频里有什么** ——
 *   委托方读到的就是「它没看我的视频」，而日志里明明写着
 *   「15.0s｜帧 OCR 8/8（51 字）｜音轨里没人说话」。
 *
 *   现在同一份读数**两处共用**：日志一行、卡片正文一块（`meta.mediaRead` → 信封）。
 *   两处各拼一遍迟早会不一致，所以只留这一个产者 —— 与 §2.5「形态决策只能有一处」
 *   同一条道理：同一件事有两个产者，错位只是时间问题。
 *
 * @param {object|null} inbound `readInboundContent()` 的产物
 * @param {{raw?:boolean}} [opt] `raw:true` ⇒ 用 **OCR 原文**（`textRaw`）而不是摘除后的文本。
 *        ★ 2026-10-09 晚加：这一格原先**同时**供卡片与诊断日志用，而两者要的不是一回事 ——
 *          卡片要**干净**（水印对读者没有信息量），日志要**原文**（"我到底读到了什么"是排查的锚点，
 *          摘除后印出来，核对时就看不到 OCR 真读成什么样了；当天我就因此差点把
 *          「生产摘 9 行、我这台摘 10 行」的差异读错）。
 *        ⚠️ 默认 `false` = 摘除后那份 ⇒ **卡片（唯一的生产调用）行为一个字不变**。
 * @returns {string|null}
 */
export function describeMediaRead(inbound, { raw = false } = {}) {
  if (!inbound) return null;
  const cut = (s, n = 200) => {
    const t = String(s ?? '').replace(/\s+/g, ' ').trim();
    return t.length > n ? `${t.slice(0, n)}…` : t;
  };
  // ★★ 2026-10-09（Owner：「目前守衡输出的没有视频的时间节点 00:12 这些」）——
  //   这一行原先**只取 `f.text`、丢掉 `t_s`** ⇒ 卡上「帧上文字」没有时间码，
  //   而同一份读数交给库侧那份是带时间码的 ⇒ 委托方拿着卡**无法去片子里定位**。
  //   现在改走 `video.frameLine`（**唯一产者**，见其头注），帧号/时间码与库里那份同源。
  const frameText = (f) => cut(video.frameLine(f, { indent: false }) ?? '');
  const out = [];

  const imgs = inbound.images ?? [];
  if (inbound.imageCount) {
    // ⚠️ 判据用 `textRaw`（**OCR 真读到了什么**）：OCR 读到、但全被判为水印时，
    //    `text` 会是空的 —— 那是「读到了、但都不算素材内容」，**不是「图上没字」**。
    const got = imgs.filter((i) => i.textRaw ?? i.text);
    const failed = imgs.filter((i) => i.failed);
    const empty = imgs.filter((i) => i.ocrEmpty);
    const chars = imgs.reduce((a, i) => a + (i.chars ?? 0), 0);
    out.push(`图 ${inbound.imageCount} 张${inbound.fromParent ? '（取自你引用的那条消息）' : ''}`
      + `｜读出文字 ${got.length} 张（共 ${chars} 字）`
      + (empty.length ? `｜图上没字 ${empty.length} 张` : '')
      + (failed.length ? `｜**读失败 ${failed.length} 张**` : '')
      + (inbound.skippedImages ? `｜超上限未读 ${inbound.skippedImages} 张` : ''));
    // ★★ 2026-10-09（Owner 两次重测都问这件事）**卡上也不再显示水印** ──────────────
    //   上一版这里印的是 `i.text`（OCR 原文、含水印），理由是"让人看到我读到了什么"。
    //   按 Owner 反馈定：**水印对读者没有信息量**。
    //   ⇒ 改印 `wlText`（摘掉水印那份）——**与喂给链的检索文本同源**（同一个字段，
    //     不再两处各拼一遍）；原文一个字没丢（仍在 `i.text`），核对时看日志的摘除明细。
    //   ⚠️ 摘掉的行**只报条数、不列内容** —— 列出来等于把水印又放回卡上（第一版就是这样，等于没摘）。
    if (got.length) {
      // ★★ 2026-10-09 晚（Owner：「【图 1 内文字｜35 行，另摘除水印 10 行】==》丑排版」）：
      //   卡上从前把 35 行碎片折成一行、切到 200 字。**两头不讨好**：
      //   业务读不懂（碎片本就不通顺），回源也核不了（切了一半）。
      //   ⇒ 卡上**只留读数**（读到几行、摘掉几行水印），**全文进报告附录**
      //     （`mediaReadAppendix`，唯一落点，一个字不丢；Owner 已点头这个方向）。
      //   ⚠️ 摘掉水印的行**只报条数、不列内容** —— 列出来等于把水印又搬回卡上。
      //   ⚠️ 原文**没有删**：`i.text` 仍在 `inbound` 里，报告附录印的就是它。
      const parts = got.map((i) => {
        const n = i.wmDropped?.length ?? 0;
        return `图 ${i.index}：读到 ${i.lines ?? '?'} 行${n ? `，另摘除水印 ${n} 行` : ''}`;
      });
      out.push(`图上文字：${parts.join(' ／ ')}（**全文见报告附录**「机读素材读数」）`);
    }
    for (const f of failed) out.push(`图 ${f.index} 读失败：${f.failed}`);
  }

  const vids = inbound.videos ?? [];
  if (inbound.videoCount) {
    const failed = vids.filter((v) => v.failed);
    out.push(`视频 ${inbound.videoCount} 段${inbound.fromParent ? '（取自你引用的那条消息）' : ''}`
      + `｜读成功 ${vids.length - failed.length} · 失败 ${failed.length}`
      + (inbound.skippedVideos ? `｜超上限未读 ${inbound.skippedVideos} 段` : ''));
    for (const v of vids) {
      if (v.failed) { out.push(`视频 ${v.index} 读失败：${v.failed}`); continue; }
      const t = v.transcript ?? {};
      const audio = t.ok ? `音轨转写 ${t.chars ?? 0} 字`
        : (t.kind === 'no_audio_track' ? '**没有音轨**'
          : (t.kind === 'no_speech' ? '音轨里没人说话' : `音轨转写没跑成（${t.kind ?? '?'}）`));
      out.push(`视频 ${v.index}：${Number(v.meta?.duration_s ?? 0).toFixed(1)} 秒`
        + `｜抽帧 OCR ${v.framesRead ?? 0}/${v.frames?.length ?? 0} 帧（共 ${v.ocrChars ?? 0} 字）｜${audio}`);
      // ★★ 2026-10-09 晚（Owner：「【图 1 内文字｜35 行，另摘除水印 10 行】==》**丑排版**」）：
      //   卡上**不再平铺图内文字全文** —— 那 35 行 OCR 碎片被 `cut(200)` 切一半、
      //   又用 ` / ` 折成一行：既不是给人看的（碎片本就不通顺），也不是给回源核对的（切了一半）。
      //   ⇒ **图**：卡片只留读数（读到几行、摘掉几行水印），全文进报告附录（`mediaReadAppendix`）。
      //   ⚠️ **视频不一样，这是刻意的，别顺手统一**：帧文字是**成句的一句话**
      //     （`Eufy S1 Pro has a single layer`，可读），而且 Owner **点名要卡上看得见时间码**
      //     （`[00:12]`）—— 把整块撤掉会连那个一起弄没（Z33a 就是这条，撤的时候当场变红）。
      //     ⇒ 视频保留**带时间码的压缩预览**（前几帧），全文仍进附录。
      const per = (v.frames ?? []).map(frameText).filter(Boolean);
      const preview = per.slice(0, 3);
      out.push(preview.length
        ? `帧上文字：${cut(preview.join(' ／ '), 150)}`
          + (per.length > preview.length
            ? `…（共 ${per.length} 帧有字，**全文见报告附录**「机读素材读数」）` : '')
        : '帧上文字：**一帧都没读到字**（这不等于「画面没问题」）');
    }
  }
  return out.length ? out.join('\n') : null;
}

/**
 * 报告附录：**媒材读数的全文**（图内文字 + 关键帧文字/转写）—— 与卡片那格**分工**。
 *
 * ★★ 2026-10-09 晚加（Owner 点头：「把排版丑放到附录中==》可以的」）：
 *   卡片上原先把 35 行 OCR 碎片折成一行、切到 200 字 —— **两头不讨好**：
 *   业务读不懂（碎片本就不通顺），回源也核不了（切了一半）。
 *   ⇒ 全文搬到**报告附录**（唯一落点），卡片只留读数。**搬不是砍**：
 *     · 图：`text`（摘除水印后那份，与卡/模型/链同源）+ 另摘了几行（只报条数，不列内容）；
 *     · 视频：`frameLine()` 逐帧（**带时间码**，`[00:12]` 口径）+ 音轨转写；
 *     · 读不到/没字的**如实写**（未测 ≠ 没有）。
 *   ⚠️ 没有媒材 ⇒ 回**空串**（不许凭空造一节 —— 报告里多一节空壳也是噪声）。
 *   ⚠️ 这里印的是**机读碎片**，必须自带说明：否则下一个人又会拿它当"素材的排版"去读。
 *
 * @param {object|null} inbound `readInboundContent()` 的产物
 * @returns {string} markdown 片段（空串 = 这一节不印）
 */
export function mediaReadAppendix(inbound) {
  if (!inbound || (!inbound.imageCount && !inbound.videoCount)) return '';
  const L = [];
  const imgs = inbound.images ?? [];
  if (inbound.imageCount && imgs.length) {
    L.push('### 图内文字（本机 OCR 逐行碎片）');
    L.push('');
    L.push('> ⚠️ 这是**逐行碎片** —— 版面的列关系在 OCR 那一步就丢了，**读起来不通顺是正常的**。');
    L.push('> 用途只有一个：核对「当时到底读到了什么字」。**不要把它当素材的排版或正文。**');
    L.push('> 水印/印章类文字**已摘除**（摘了几行只说条数、不列内容 —— 列出来等于把水印又搬回来）。');
    L.push('');
    for (const i of imgs) {
      if (i.failed) { L.push(`- **图 ${i.index}**：读失败（${i.failed}）`); continue; }
      const n = i.wmDropped?.length ?? 0;
      L.push(`- **图 ${i.index}**（读到 ${i.lines ?? '?'} 行${i.truncated ? ' · 已按字数上限截断' : ''}`
        + `${n ? ` · 另摘除水印 ${n} 行` : ''}${i.wmBasis && i.wmBasis !== 'none' ? ` · 判据 \`${i.wmBasis}\`` : ''}）：`);
      L.push('');
      L.push('```');
      L.push(String(i.text ?? '').trim() || '（这一张没读出文字）');
      L.push('```');
      L.push('');
    }
  }
  const vids = inbound.videos ?? [];
  // ── ★★ 2026-10-15：**画面读数**（PRD §5.1「基础视觉识别」那一半）──────────────
  //   为什么单开一节而不是并进「图内文字」：两者是**两种读数**，
  //   一个是**原图里真有的字节**（OCR 逐行碎片），一个是**模型看图的描述**。
  //   混在一节里，读报告的人会分不清「这句话是图上印的」还是「模型说的」——
  //   而这条区分恰恰是这份报告能不能被复核的前提（§2.4.1：读数是谁的）。
  if (inbound.imageCount && imgs.some((i) => i?.scene)) {
    L.push('### 画面读数（视觉模型看图的描述 —— **不是原图，也不是图上印的字**）');
    L.push('');
    L.push('> ⚠️ 这一节由**吃图的模型**看一眼那张图写出，只陈述看得见的（场景/人物/物品/可见标识/画面线索）。');
    L.push('> 它是**读数**：可以据此判「产品使用 / 人物行为 / 场景风险」，但**读数里没写的不要推断**。');
    L.push('> 三种结局分得开：**有读数** ／ **读了没读到**（未测）／ **这一单没跑画面层**。');
    L.push('');
    for (const i of imgs) {
      const sc = i?.scene;
      if (!sc) { L.push(`- **图 ${i.index}**：这一单没跑画面层`); continue; }
      if (sc.skipped) { L.push(`- **图 ${i.index}**：这一单**没跑**画面层（${sc.error ?? '未开'}）`); continue; }
      if (!sc.ok) { L.push(`- **图 ${i.index}**：**没读到**（${sc.error}）—— 画面层是**未测**，不是「没有画面」`); continue; }
      L.push(`- **图 ${i.index}**（${sc.ms}ms）：`);
      L.push('');
      L.push('```');
      L.push(sceneMod.sceneBlock(sc.scene));
      L.push('```');
      L.push('');
    }
  }
  if (inbound.videoCount && vids.length) {
    L.push('### 关键帧文字与音轨转写');
    L.push('');
    for (const v of vids) {
      if (v.failed) { L.push(`- **视频 ${v.index}**：读失败（${v.failed}）`); continue; }
      L.push(`- **视频 ${v.index}**（${Number(v.meta?.duration_s ?? 0).toFixed(1)} 秒 · `
        + `抽帧 OCR ${v.framesRead ?? 0}/${v.frames?.length ?? 0} 帧）：`);
      L.push('');
      const per = (v.frames ?? []).map((f) => video.frameLine(f, { indent: false })).filter(Boolean);
      L.push('```');
      L.push(per.length ? per.join('\n') : '（一帧都没读到字）');
      L.push('```');
      L.push('');
      const t = v.transcript ?? {};
      if (t.ok && String(t.text ?? '').trim()) {
        L.push('音轨转写：');
        L.push('');
        L.push('```');
        L.push(String(t.text).trim());
        L.push('```');
        L.push('');
      } else {
        L.push(`音轨：${t.kind === 'no_audio_track' ? '**没有音轨**'
          : (t.kind === 'no_speech' ? '音轨里没人说话' : `转写没跑成（${t.kind ?? '未测'}）`)}`);
        L.push('');
      }
    }
  }
  return L.join('\n').trim();
}

/**
 * ★ 2026-10-12（Owner 同意「先只动 P0 命中那一路」）：P0 确定性命中时的**短卡**要求。
 *
 * 依据（实测，不是感觉）：同一条真实送审单的结果卡是 **2903 字 / 54541 ms**
 * （守衡日志逐字 `💬 回复 2903 字，耗时 54541ms`），而这一路的判定**早在 48 ms 就定了**
 * （`🚦 P0 命中 ⇒ 直接 BLOCK，不起链：H05｜48.297 ms`）——
 * 逐条明细与修改建议都在**报告**里，群里再展开一遍没有增量，
 * 却把 PRD §12「单条文字 ≤ 10 s」拖到 50 s 以上（Owner 2026-10-12 裁定的口径 = 用户等多久）。
 *
 * ★ 为什么**不会**弄丢 PRD §5.3 合规块：结论块由**代码强制**落进卡
 *   （`applyVerdictLine` ＋ `blockSlotOf` 的类型回退），**不依赖模型的措辞** ——
 *   短答只压缩「叙述」，不压缩「结论行 / 命中模式与条款号 / 报告链接」这三样必须项。
 */
export const P0_SHORT_REPLY_INSTRUCTION = [
  '【本条是 P0 红线**确定性命中**（关键词/正则匹配，不是模型推断）—— 请按**短卡**作答】',
  '必须保留：① 三态结论行；② 命中的 P0 模式与条款号；③ 报告链接（有就写，没有就说明原因）。',
  '不要展开：逐条明细、修改建议全文、读数复述 —— 那些都在上面那份报告里，群里重复一遍没有增量。',
  '篇幅上限：正文 ≤ 300 字（不含结论行与链接）。',
].join('\n');

/**
 * 判定「这一单要不要附短卡要求」。**纯函数** ⇒ `p0_short_reply.test.mjs` 直接喂夹具验它。
 * 只认 `p0_fastpath`（= 链**没跑**、判定是确定性的）；
 * **评审链 / 拒答 / 普通对话一律不附** —— 那些场合的正文是要给人看的实质内容。
 */
export function p0ShortReplyBlock(res) {
  return res && res.p0_fastpath ? P0_SHORT_REPLY_INSTRUCTION : '';
}

export function buildUserTurn({ questionText = '', imageBlock = '', videoBlock = '', chainBlock = '' } = {}) {
  // 图块拼在问题**后面**：模型先读人问的话，再读图上的字，顺序与人发消息的顺序一致。
  // 视频块排在最后（它最长），顺序是「她问的话 → 图上的字 → 视频读数」。
  let q = questionText ?? '';
  if (imageBlock) q = q ? `${q}\n\n${imageBlock}` : imageBlock;
  if (videoBlock) q = q ? `${q}\n\n${videoBlock}` : videoBlock;
  // ★ 链的结论排在**最前**（它在问题之前）：它是这一轮的**结论**，不是补充材料 ——
  //   排在后面会被前面几百字的读数盖住，模型就又开始「描述我读到了什么」了。
  if (chainBlock) q = q ? `${chainBlock}\n\n${q}` : chainBlock;
  return q;
}
/**
 * 处理一条飞书消息，返回要发出的回复文本（不负责发送）。
 * @param {object} event  im.message.receive_v1 的 data
 * @returns {Promise<{reply:string|null, reason?:string, sessionKey?:string, meta?:object}>}
 */
export async function handleMessage(event, {
  force = false,
  deps = undefined,
  // ★ 目标 19（2026-10-10）：**消息到达时刻**（ms epoch）。由 `ws_daemon.onMessage` 在收到
  //   事件那一刻打；不给就退回"进 handleMessage 的这一刻"（会少算排队/调度那几毫秒，
  //   ⇒ **报告里必须写明取的是哪一个**，不许把两个数混着说）。
  tIngress = null,
  // ★ 链要跑 10~30 分钟：一开始就回一句，否则对方以为它没动（09:22 那次就是这样）。
  notify = null,
  // 跑链那一步的注入点（测试必须注入桩 —— 不注入就会真起一条 30 分钟的链并写飞书）。
  //
  // ★ 2026-10-05 现场踩到的第二个坑：这里原先内联写着 `(args) => executeTool(...)` ——
  //   而 `executeTool` 回的是**信封** `{tool, ok, result}`，不是链的返回。
  //   于是同一个「怎么跑链」有了**两个默认值**，而 `handleMessage` 显式把这个传下去，
  //   **盖住了 `runSubmissionGate` 里那个正确拆信封的默认值**。
  //   表现：链明明没跑成（KB 根不存在），日志和 `meta.chain.ran` 却写「**跑成**」——
  //   而 `mediaWithoutChain()` 那条兜底棘轮看的正是 `chain.ran`，
  //   于是「该送审却没起链」这个警报**在链没跑成的时候反而闭嘴**。
  //   修法：默认值只留一个（下面那个具名函数），这里只做转发。
  chainRunner = defaultChainRunner,
  publishRunner = reviewPublish.ensureReviewRow,
  // ★ 2026-10-06：`handleMessage` **转发**它，所以自己也必须声明它。
  //   不声明就转发 = 未声明标识符 = **直接抛 ReferenceError**，
  //   而它抛在闸门之后那一跳上 —— 现场表现是「链跑完了却没有回话」。
  //   实测就是这么红的：`THREW modelSideRunner is not defined`。
  modelSideRunner = reviewModelSide,
  // ★ 2026-10-09：转发给闸门（见那里的注释）—— 不声明就转发 = ReferenceError
  mergedReportRunner = publishMergedReport,
  adviceRunner = generateAdvice,
} = {}) {
  const msg     = event?.message ?? {};
  const sender  = event?.sender ?? {};
  const chatId  = msg.chat_id;
  const chatType = msg.chat_type;                    // 'group' | 'p2p'
  const senderOpenId = sender?.sender_id?.open_id ?? sender?.sender_id?.user_id ?? '';

  // ── 1. 去重必须**最先**做。
  // 放在类型判断之后是错的：非文本消息（图片/文件）会绕过去重，
  // 服务端重推同一条时会重复回话，用户看到守衡对同一张图说两遍「我读不了」。
  //
  // ★ `force`（2026-09-22 加，Q1-1d）：**补发**要重放同一条消息，而它必然已在去重表里。
  //   所以补发那一路显式绕过去重 —— 但它绕过的**只有这一道**，幂等的另外两道
  //   （台账已答 / 记忆已答）由 `retry_queue.mjs` 自己判，那两道才是防「答两遍」的。
  if (!force && alreadyHandled(msg.message_id)) {
    return { reply: null, reason: 'duplicate', meta: { message_id: msg.message_id } };
  }

  // ── 2. 把这一条读成「文字 + 图内文字」。
  //
  // ★ 2026-10-05 改：原先这一步是 `if (msg.message_type !== 'text') return 拒答`。
  //   那次事故（06:37 私聊「评审下下这个图片，能过吗？」+ 配图）暴露了两个错，
  //   而且是**同一个形状**——「结论比输入大」：
  //     · 图文混排在飞书里是 **post** 类型 → 连**正文**都被扔掉，
  //       而 `bodyToText`（09-22 就修好了）本来读得出来；
  //     · 图片按红线不取 —— 这一半**当时是对的**，但话说错了：
  //       「它的正文我读不了」让人以为缺个开关，于是她没有任何可走的路。
  //   现在：正文照读；**人当前发来的图**读图内文字（§2.6 窄豁免，Owner 10-05 确认）；
  //   file/media/audio 仍然不取，而且明确说「按规矩不取」。
  //  `deps` 只是给测试注入桩用的（生产调用点一个字都不用改）——
  //  没有它，「取图 + OCR」这条路只能在联网 + 花 token 的情况下才测得动，
  //  而那等于没有可跑的判据（AGENTS.md §2.4：指不出哪一行在拦它，就等于没拦）。
  //
  // ── 2.5 送审人显示名：**必须在读图之前**备好（2026-10-09 晚，Owner：「还有我的名字」）──
  //
  // ★ 病灶（**接线顺序错了**，不是判据错）：`readInboundContent` 就是下一行（读图 + 摘水印），
  //   而名字原先要到第 4 步（`not_mentioned` 判断之后，约 1550 行）才解析出来 ——
  //   ⇒ **摘水印的时候还不知道送审人叫什么**，判据只能靠「OCR 有没有把名字读出 2 次」去猜。
  //   而同一张图两次 OCR 的读数**并不一致**（实测：一次 `刘华問`×2+`刘华丽`×1，
  //   另一次 `刘华`×2+`刘华丽`×3）⇒ 名字只被读出 1 次时就当不上"平铺核心"、摘不掉，
  //   于是卡片与报告继续带着它（Owner 连报两次）。
  //   水印逐字就是「**用户名 + 工号**」（台账实测 `sender: 刘华丽`）⇒ 名字是**已知的**，不该猜。
  //
  // ★ 为什么是**惰性取数**而不是在这里 await：没带图的普通对话不该多付一次名字查询。
  //   传下去的是个**取数函数**，`readInboundContent` 只在真读到图、真要去水印那一刻调它；
  //   底层 `feishu.getUserName` 自带群成员缓存 ⇒ 第 4 步再调一次是缓存命中、不重复花钱。
  let _senderNameForWm;
  const senderNameForWatermark = () => {
    if (_senderNameForWm === undefined) {
      _senderNameForWm = senderOpenId
        ? feishu.getUserName(senderOpenId, chatId).then((x) => x?.name ?? null).catch(() => null)
        : Promise.resolve(null);
    }
    return _senderNameForWm;
  };
  const inbound = await readInboundContent(msg,
    deps ? { ...deps, senderNameForWatermark } : { senderNameForWatermark });
  // 日志留一行读数：**「守衡有没有真的读到图」不该只能靠群里看回复来判断**。
  // 这一行也是排查的锚点（图几张、OCR 多少字、哪几张失败、是不是从引用的那条取的）。
  if (inbound.parentNote?.kind === 'parent_unreadable') {
    console.log(`[agent] ⚠️ 图未测：这条没带图，它引用的 ${inbound.parentNote.parentId} 读不到（${inbound.parentNote.error}）`);
  }
  // ★ 2026-10-06：原先图、视频各拼一段日志，而**同一份读数不进卡片**。见 `describeMediaRead`。
  // ⚠️ 2026-10-13：原先这里还算一份**摘除后**的读数给卡片用（`describeMediaRead(inbound)`）；
  //   读数不上卡之后那一份**没有消费者了** ⇒ 拿掉，免得留下一个算了没人读的变量
  //   （「算了没人读」与「传了没人接」是同一个病）。要用的是下面 `raw:true` 这一份日志，
  //   以及 `mediaReadAppendix(inbound)`（报告附录那份是**摘除后**的，见它自己的头注）。
  // ⚠️ 这一行印 **OCR 原文**（`raw:true`）：它是"我到底读到了什么"的排查锚点，
  //   摘除后印出来就看不到 OCR 真读成什么样了（水印摘了哪些行另有「🚫 摘除水印」那一行）。
  const mediaReadRaw = describeMediaRead(inbound, { raw: true });
  if (mediaReadRaw) console.log(`[agent] 📥 读到｜${mediaReadRaw.replace(/\n/g, ' ⏎ ')}`);
  const imageBlock = buildImageBlock(inbound);
  const videoBlock = buildVideoBlock(inbound);
  // ★ 判据是「**读成功过**」，不是「读出了内容」：一条视频抽帧成功、音轨里没人说话，
  //   那也是一个**要如实回答的读数**（「画面上这 8 帧没有可读文字、音轨里没人说话」），
  //   而不是走「我读不了」那条拒答 —— 后者会让人以为缺个开关，再去发一遍还是同一句。
  const videoRead = inbound.videos.some((v) => !v.failed);
  const hasAnything = !!inbound.text || inbound.images.some((i) => i.text) || videoRead;

  if (!hasAnything) {
    const meta = { message_type: msg.message_type, image_count: inbound.imageCount,
                   video_count: inbound.videoCount };
    // ⓐ 附件（file / media / audio 里的**非视频**）：**按规矩不取**，并给一条走得通的路。
    //   ★ 这段文案 2026-10-05 改过一次，因为**它当时是错的**：
    //     原文写着「附件（文件/语音/**视频**）我不取」—— 而视频那条路当天已经通了。
    //     照那句说，对方会把视频再发一遍，还是听到同样一句话（与 06:37 那次同一个形状：
    //     **话说得比能做的窄，于是人以为缺个开关**）。
    if (inbound.attachment) {
      return { reply: '附件（表格/文档/语音这类）我不取 —— 飞书上的内容公司不让下载，它们只有下载这一条通道。\n'
                    + '要审的话，把里面的文字贴过来；或者存成飞书云文档发我，云文档我能直接读。\n'
                    + '**图片和视频不一样**：图你直接发我，我读图上的字；'
                    + '视频你也直接发我，我抽关键帧读画面上的字、再在**本机**把口播转成文字。',
               reason: 'attachment_not_taken', meta };
    }
    // ⓑ 视频一段都没读成 → 如实说失败原因（**不许**编内容，也不许说成「视频里没东西」）。
    if (inbound.videoCount) {
      const why = inbound.videos.map((v) => `视频 ${v.index}：${v.failed ?? '未读'}`).join('；');
      return { reply: `你发的那段视频我**没读成**（${why}）。\n`
                    + '这不是「视频里没问题」—— 是我这一段没读到。'
                    + '可以再发一次；如果是格式比较偏（比如非常规编码），转成 mp4 再发我一次。',
               reason: 'video_unreadable', meta };
    }
    // ⓒ 有图但一张都没读出来 → 如实说，并给出下一步（**不许**编内容）。
    if (inbound.imageCount) {
      const why = inbound.images.map((i) => `图 ${i.index}：${i.failed ?? (i.ocrEmpty ? '图上没识别出文字' : '未读')}`).join('；');
      return { reply: `你这条里的图我**没读出内容**（${why}）。\n`
                    + '如果是图上文字太小或图形化排版，可以把文字贴过来；'
                    + '也可以换一张更清晰的截图再发我一次。',
               reason: 'image_unreadable', meta };
    }
    // ⓓ 其余非文本类型（卡片 / 表情 / 位置…）：照实说没解析出来 + 是哪种没解析出来。
    //   ★ 若这条是在**回复**另一条、而那条我读不到 —— 必须说「未测」，不许说成「没有图」。
    const quoteNote = inbound.parentNote?.kind === 'parent_unreadable'
      ? `\n另外：你这条是在回复某一条，而**那条我读不到**（${inbound.parentNote.error}）——`
        + '所以那里面有没有图或视频，我不知道，也不会去猜。'
      : '';
    return { reply: `这条是「${msg.message_type}」，它的正文我读不了`
                  + `${inbound.parseNote ? `（${inbound.parseNote}）` : ''} —— 需要的话请把它转成文字发我。`
                  + quoteNote,
             reason: 'unsupported_type', meta: { ...meta, parseNote: inbound.parseNote } };
  }

  // ── 3. 解析正文与 mention
  //    `inbound.text` 已经是可读正文（post 也在内）；mention 还原仍然照旧。
  const rawText = inbound.text;
  const { display, mentions } = feishu.resolveMentions(rawText, msg.mentions);
  const botMentioned = feishu.isBotMentioned(mentions);
  let question = buildUserTurn({
    questionText: botMentioned ? feishu.stripBotMention(display, mentions) : display.trim(),
    imageBlock, videoBlock,
  });

  // 名字的解析与「惰性取数函数」都在上游第 2.5 步（读图之前）—— 这里不再重复一份。

  // ── 4. 群聊里「不 @ 不理」，避免刷屏；私聊一律响应
  if (chatType === 'group' && config.requireMentionInGroup && !botMentioned) {
    return { reply: null, reason: 'not_mentioned' };
  }  if (config.allowedChats.length && !config.allowedChats.includes(chatId)) {
    return { reply: null, reason: 'chat_not_allowed', meta: { chatId } };
  }

  // 已知名字的三条来源，按可信度与代价排序：
  //   1) 消息 mentions 里带的名字（零成本，但只覆盖「被 @ 的人」）
  //   2) 群成员列表（已有权限，覆盖同群所有人）
  //   3) 通讯录单查（需额外权限，未开通则失败）
  let senderName = mentions.find((m) => m.openId === senderOpenId)?.name || null;
  let senderNameSource = senderName ? 'mention' : null;
  let senderNameReason = null;
  if (!senderName && senderOpenId) {
    const looked = await feishu.getUserName(senderOpenId, chatId);
    senderName = looked.name;
    senderNameSource = looked.source;
    if (!senderName) {
      // 查不到就如实告诉模型，别让它编一个称呼
      senderName = '(未知名)';
      senderNameSource = 'unresolved';
      senderNameReason = looked.reason;
    }
  }
  const senderNameKnown = senderNameSource !== 'unresolved';

  // ── 5. 会话与记忆
  const key = mem.sessionKey({ chatId, chatType, senderOpenId });
  return withLock(key, async () => {
    const sess = mem.load(key);
    if (!sess.title && chatType === 'group') {
      const info = await feishu.getChatInfo(chatId);
      mem.setTitle(sess, info?.name ?? null);
    } else if (!sess.title && chatType === 'p2p') {
      mem.setTitle(sess, `${senderName} 的私聊`);
    }

    // 注入运行期上下文，工具据此知道「现在在哪、跟谁说话」
    // senderNameKnown=false 时，senderName 是「(未知名)」占位符而非真名，
    // 一并告知模型，避免它把这个占位符当成真名去称呼对方。
    Object.assign(runtimeContext, {
      chatId, chatType, senderName, senderOpenId, messageId: msg.message_id,
      senderNameKnown,
      ...(senderNameKnown ? {} : { senderNameUnavailableReason: senderNameReason }),
    });

    // ── 5.4 把「我说过、但记忆里没有的」补进来（2026-09-22 加）
    //
    // ★ 为什么必须有这一步：`mem.append` 只在**回复循环**里调，而守衡**主动说出的话**
    //   （`send_once.mjs` 手发的、基线告警、待收提醒、崩溃自报）都不经过那里。
    //   后果在 09-22 14:39 变成了对外的：她 14:39:34 回「归我」，而守衡的上下文里
    //   **只有她那句话、没有自己 14:37:55 问过的那一句** —— 它看到的是一句悬空的回答，
    //   往上接到了 27 小时前的话题上，答成「那三条过期内容归你」并发了出去。
    //   台账（`outbound.mjs`）记着那条问话，这一步把它折回记忆。
    //
    // ★ 位置是**判据的一部分**，不能挪：
    //   · 必须在 §5.5 **之前** —— 折进来之后再问「上文在不在历史里」，那条问话就已经在了，
    //     同一个上文不会既进历史又进引用块（两遍就是噪音，还会让模型以为问了两遍）；
    //   · 必须在 `mem.append(sess, { role: 'user', ... })` **之前** —— 它问的话要在
    //     她的回答**上面**，否则模型读到的是「先答后问」。
    //
    // ⚠️ 三种情形在日志里长得不一样（**取不到 ≠ 没有要补的**）：
    //   · 补了 N 条 → 记一行，带上 message_id；
    //   · 没有要补的 → 记一行「无新增」（这是正常的，不是失败）；
    //   · **读数采不到**（台账读不出 / 有坏行 / 只读了尾部）→ 记 **未测**，不许当成「没有」。
    let outboundFold = { folded: 0, plan: { entries: [], untested: null } };
    try {
      outboundFold = foldInto(sess, chatId);
      const p = outboundFold.plan;
      if (outboundFold.folded) {
        const ids = p.entries.map((e) => (e.message_ids ?? []).join('+') || '(无 id)').join(', ');
        console.log(`[agent] ↩ 补记外发 ${outboundFold.folded} 条进会话记忆：${ids}`);
      } else if (p.untested) {
        console.log(`[agent] ⚠️ 补记外发未测：${p.untested}`);
      } else {
        console.log(`[agent] · 补记外发：无新增（台账里没有「我说过但记忆里没有」的话）`);
      }
    } catch (e) {
      // 补记失败不该让这次回话失败 —— 但那一定是**未测**，不能静默。
      console.log(`[agent] ⚠️ 补记外发未测：这一步抛了 ${e?.message ?? e}`);
      outboundFold = { folded: 0, plan: { entries: [], untested: `抛异常：${e?.message ?? e}` } };
    }

    // ── 5.5 「这条消息在回复哪一句」—— 把上文摆到模型面前（2026-09-22 加）
    //
    // ★ 为什么必须有这一步（一次真实的外部误答，不是推演）：
    //   09-22 14:37:55 我方主动推送问了「117 条签核归谁」；她 14:39:34 用**话题回复**答「归我」。
    //   `im.message.receive_v1` 事件里 `parent_id` / `root_id` **都指着我方那条消息** ——
    //   飞书把线索完整送来了。而 `ws_daemon.mjs` 的 `onMessage` 从不读这两个字段，
    //   加上主动推送不进会话记忆（`memory.append` 只在回复循环里调），
    //   模型看到的是一句**悬空的「归我」**，往上接到 27 小时前的话题上，
    //   14:39:51 答成了「那三条过期内容归你」并**发了出去**。
    //
    //   两条根因里，这一条**不碰 import 图、不用改 memory.append** ——
    //   一次回读就能让守衡看见自己问过什么（实测机器人读得回自己发的消息，
    //   含 `send_once.mjs` 发的主动推送，见 PMO/守衡-误答登记-20260922.md §3.2.1）。
    //
    // ⚠️ 三种情形必须在**日志里长得不一样**（取不到 ≠ 没有上文）：
    //   · 不是回复        → 不引（正常）
    //   · 已在会话历史里  → 不引（避免同一个上文出现两遍）
    //   · **读不到**      → 说「未测」，不许当成「没有上文」
    let parentBlock = null;
    const parentId = parentIdOf(msg);
    if (parentId) {
      const parent = await feishu.getMessage(parentId);
      if (parent?.error) {
        // ⚠️ **不能静默降级。** 她很可能正是在答一句我们读不到的话；
        // 这时「装作没有上文」与「以为没有上文」都会重演 14:39 那次误答。
        // 也不能只说一句"读不到"就完 —— 得告诉模型**这时该怎么做**，
        // 否则它仍会自己找一句最近的话接上去（那正是上次发生的事）。
        console.log(`[agent] ⚠️ 引用上文未测：回读 ${parentId} 失败（${parent.error}）`);
        parentBlock = [
          '〔引用上文 · 未测〕对方这条消息是在回复某一条，但**我读不到那一条**。',
          `· 回读 ${parentId} 失败：${parent.error}`,
          '· 所以：**不要在看不见上文的情况下猜她在答什么**，也不要把最近说过的一句当成她答的那一句。',
          '  要接话就先说清"你回复的那条我读不到"，再问她是哪一件事。',
          '〔引用上文结束〕',
        ].join('\n');
      } else if (!alreadyInHistory(sess.messages, parent.text)) {
        parentBlock = buildQuoteBlock({
          from: parent.from,
          text: parent.text,
          at: parent.at,
        });
        console.log(`[agent] ↩ 引用上文 ${parentId}（${parent.from}｜${parent.text.length} 字）`);
      } else {
        console.log(`[agent] · 引用上文跳过：${parentId} 的内容已在会话历史里`);
      }
    }

    // ── 5.9 **送审闸门**：内核先跑链，再让模型说话（见 `runSubmissionGate` 的头注）
    //
    // ★ 2026-10-05 现场踩到的坑，逐字记下来：把闸门抽成函数时，**把 `let gate = null;`
    //   那四行声明一起抽走了**，于是这里变成对**未声明标识符**赋值 —— ESM 是严格模式，
    //   直接 `ReferenceError: gate is not defined`。后果不是「少一个字段」，是：
    //   **链跑完 17.9 分钟、然后内核在回话前一刻崩掉**，人收到的是
    //   「我处理这条消息时内部出错了…gate is not defined」，而链的结论被丢掉。
    //   为什么自证没拦住：`runSubmissionGate` 自己测过（它是好的），
    //   接线断言只查了「handleMessage 里有没有调用它」—— **而崩溃发生在调用之后那一行**。
    //   补的判据见 `tools/test_agent.mjs` 第 18 组那条 `子进程端到端`：
    //   它真跑一遍 handleMessage（LLM 指向死地址、KB 根指向不存在），
    //   所以「调用之后还有没有塌」从此有人看着。
    // ★ 2026-10-08：**这一轮的边界** —— 清掉上一轮「链已经跑过」的记忆。
    //
    //   必须在这里（**调闸门之前**），理由有两条，缺一条都会答错：
    //     ① 闸门自己就要跑链，跑完那一次会**装上**缓存 —— 清空得比它早。
    //     ② 一轮 = 一条入站消息 = 一次送审。上一轮的结论若漏到这一轮，
    //        守衡会拿**一张没审过的图**的结论去答话 —— 方向不对称：
    //        漏跑只是慢，串轮是答错。
    //   另一条绕过这里的路径由 `tools.mjs` 的 TTL 兜（两道独立护栏）。
    const chainMemoPrevHits = beginChainTurn();
    if (chainMemoPrevHits > 0) {
      console.log(`[agent] · 上一轮链缓存命中 ${chainMemoPrevHits} 次（这一轮已复位）`);
    }
    const g = await runSubmissionGate({ inbound, question, notify, chainRunner, publishRunner, modelSideRunner,
                                    mergedReportRunner, adviceRunner, force,
                                    // ★ 目标 19：把「消息到达时刻」带进闸门，好量「@ → 回执卡」那一段。
                                    //   没给就退回此刻（并会被标成 origin=handle_entry，不许当 ingress 报）。
                                    tIngress: tIngress ?? Date.now() });
    const gate = g.gate;
    const chainRan = g.chainRan;

    // ⚠️ 2026-10-08：`chainUnmeasured` 由**另一个会话**在同一文件里声明（见下方 `let`）——
    //    两边同时改同一个文件撞过一次（重复声明 → SyntaxError）。这里不再重复声明。
    const chainMs = g.chainMs;
    question = g.question;

    // ★★ 2026-10-08 修（**实测崩溃，不是推演**）—— `chainUnmeasured` 的**提前声明**。
    //
    //   现场：素材「这条站内广告文案能不能发：M6 吸奶器静音设计，夜里泵奶不吵醒宝宝，
    //   一次充电够用一整天」（10:24 那一轮）——**库侧成功了**（旁挂 `REVIEW/1`、表已 update），
    //   但出卡阶段内核崩了：
    //     `✗ 内核异常: ReferenceError: Cannot access 'chainUnmeasured' before initialization`
    //     `at agent.mjs:1436:37`
    //   ⇒ **那一单在群里没有回复**（崩溃后日志再无输出），而且没有任何东西会红。
    //
    //   成因：同一天早些时候的改动把**三处截断/兜底分支**里的内联判据
    //   `gate?.yes && !chainRan` 统一换成了 `chainUnmeasured`（判据本身**是对的、更严格**：
    //   库忙时链是「跑成」返回的，`!chainRan` 会漏掉那一整类）——
    //   但那三处（`~:1425` / `~:1453` / `~:1510`）在函数体里**早于** `const chainUnmeasured`（`~:1578`）
    //   的执行位置 ⇒ **TDZ**：`const`/`let` 在那行之前处于「已声明未初始化」，读它就是 ReferenceError。
    //   **判据没错，位置错了。**
    //
    //   修法：把这个变量提前到**闸门刚回来**的地方声明（此刻 `g.verdict53` 已经定了），
    //   终值仍在原处**重新赋值**（那里额外能拿到 `verdict53Final` 的 `derive` 回落）。
    //   ⚠️ 为什么不干脆把整条 `const` 往上挪：`verdict53Final` 依赖 `reply`，而 `reply`
    //      要等这一轮跑完 —— 早于它的只有 `g?.verdict53` 这一半，够这三处用。
    /** 闸门判了送审、但（此刻还）没有三态结论 ⇒ 这一轮不是答案，补发队列应当重跑。 */
    let chainUnmeasured = !!(gate?.yes && !g?.verdict53);

    const userTurn = chatType === 'group' ? `【${senderName}】${question}` : question;
    const turnContent = parentBlock ? `${parentBlock}\n\n${userTurn}` : userTurn;
    // ★ `force`（补发）时**不重复 append 同一个用户轮**：上一轮失败前已经 append 过一次
    //   （失败发生在工具循环里，用户轮早在它之前就进内存了），再 append 一次会让守衡
    //   「记得她问了两遍」。判据是「最后一条 user 轮与本次逐字相同」，不是「force 就不 append」——
    //   万一上次是在 append 之前就崩了，这一轮必须把问题补进记忆，否则它就真丢了。
    const lastUser = [...(sess.messages ?? [])].reverse().find((m) => m?.role === 'user');
    if (force && lastUser && lastUser.content === turnContent) {
      console.log('[agent] ↩ 补发重放：用户轮已在记忆里，不重复 append');
    } else {
      mem.append(sess, { role: 'user', content: turnContent, name: senderName });
    }

    // ── 6. 工具循环
    const systemPrompt = buildSystemPrompt(
      chatType === 'group'
        ? `\n# 当前场景\n你在群聊「${sess.title ?? chatId}」里，正在回复 ${senderName}。群里其他人也会看到你的回答，所以不要输出私密信息，也不要假设只有一个人在听。`
        : `\n# 当前场景\n你在与 ${senderName} 私聊。`
    );

    const toolTrace = [];
    let reply = null;
    let llmError = null;
    let llmFailure = null;             // ★ 整条失败体（layer/chain/attempts/retryable），不只那句 error
    let truncated = false;
    let toolExhausted = false;         // ★ 走没走兜底话术（决定 reason，`retry_queue` 靠它补发）
    // ★ 2026-10-08：**「链跑成」不等于「有结论」**。
    //   真事故（Owner 截图）：库忙（认领被占）时链**正常返回**（日志写 `🧭 送审链返回：跑成`），
    //   而旁挂是 `state=NEEDS_INPUT / reason_code=claim_busy` —— **一次三态都没有**。
    //   上一轮我把「没测」的判据写成 `!chainRan`，于是这一种**根本不触发**：
    //   卡片照发（「库忙未判」）、补发队列 0 条、**永远不补跑**。
    //   判据改成「**链没给出三态结论**」—— PASS/REVIEW/BLOCK 之外的一切都算没测，
    //   不管它是报错、拒答、库忙还是超时。
    let synthesized = null;            // ★ 走过「兜底合成」的话记下触发原因（tool-iters / empty-length）

    for (let iter = 0; iter < config.llm.maxToolIters; iter++) {
      const messages = mem.toLlmMessages(sess, systemPrompt);
      const r = await llm.chat(messages, { tools: TOOL_SCHEMAS });

      if (!r.ok) { llmError = r.error; llmFailure = r; break; }

      const m = r.message ?? {};
      const toolCalls = m.tool_calls ?? [];

      if (toolCalls.length === 0) {
        reply = (m.content ?? '').trim();

        // 截断检查：拿到 finishReason 却不用，半句话就会被当成完整回答发出去。
        // 真实事故：779 字回复停在「…里「未做」，日志却记「✓ 已发送」。
        const cut = detectTruncation({ finishReason: r.finishReason, text: reply });

        // ★ 2026-09-30 新增一支：**一个字都没写出来**（`finish_reason=length` + 正文 0 字）。
        //   它与「半句话被腰斩」是两种故障，处置也不同：
        //     · 腰斩 —— 写了一半，材料已经用上，交给 annotateTruncation 标出来即可；
        //     · 空 —— **什么都没说**，而材料在手边。此时该做的是**关掉工具再写一次**，
        //       不是把一句「被长度上限截断了」当成回答发进群（事故里就是这么发的，
        //       用户看到的是一条只有说明、没有内容的回复）。
        const empty = reply.length === 0;
        if (empty && cut.cut && toolTrace.length) {
          const s = await synthesizeFromTools({ systemPrompt, messages, why: 'empty-length' });
          synthesized = 'empty-length';
          const got = s.ok ? String(s.text ?? '').trim() : '';
          const rTok = s.usage?.completion_tokens_details?.reasoning_tokens ?? null;
          console.warn(
            `[agent] ⚠️ 模型烧光额度没写出正文（${cut.reason}）→ 已折叠工具返回体、关掉工具重写一次`
            + `｜工具结果 ${messages.filter((x) => x.role === 'tool').length} 份`
            + `｜重写后正文 ${got.length} 字｜reasoning ${rTok ?? '?'} tok`
            + (got ? '' : `｜**重写也没写出正文**${s.ok ? '' : `（失败：${s.error}）`}`)
          );
          if (got) {
            reply = got;
            // 重写这一跳自己也可能被截在半句上 —— 同一把尺子再量一次，不搞双重标准。
            const cut2 = detectTruncation({ finishReason: s.finishReason, text: reply });
            if (cut2.cut) { reply = annotateTruncation(reply, { reason: cut2.reason }); truncated = true; }
            // ★ 带上 `truncated` 这个**结构标记**（见 retry_queue.mjs 的 NOT_AN_ANSWER_FLAGS）：
            //   截断说明长得像一条回答，不带标记的话补发队列会以为她已经答过了。
            appendAssistant(sess, { role: 'assistant', content: reply,
                                    ...(truncated ? { truncated: true } : {}),
                                    ...(chainUnmeasured ? { chain_not_run: true } : {}),
                                    ...reasoningToPassBack(s.message) });
            break;
          }
          // 重写仍是空 → **这一轮真的没有答案**。落回兜底话术（它至少是一句人话），
          // 不是把一句「被截断了」当成回答 —— 事故里发进群的那条正是后者：
          // 通篇只有说明、没有一个字的答案，而她还以为那是全部内容。
          console.warn('[agent] ⚠️ 兜底合成也没写出正文 → 改用兜底话术（这一轮确实没答上来）');
          toolExhausted = true;
          reply = fallbackReply(toolTrace);
          appendAssistant(sess, { role: 'assistant', content: reply, tool_exhausted: true, truncated: true,
                                  ...reasoningToPassBack(m) });
          break;
        }

        if (cut.cut) {
          const reasoning = r.usage?.completion_tokens_details?.reasoning_tokens ?? null;
          console.warn(
            `[agent] ⚠️ 回复被截断：${cut.reason}` +
            `｜正文 ${reply.length} 字｜reasoning ${reasoning ?? '?'} tok` +
            `｜结尾「${tailOf(reply)}」`
          );
          reply = annotateTruncation(reply, { reason: cut.reason });
          truncated = true;
        }

        appendAssistant(sess, { role: 'assistant', content: reply,
                                ...(truncated ? { truncated: true } : {}),
                                ...(chainUnmeasured ? { chain_not_run: true } : {}),
                                ...reasoningToPassBack(m) });
        break;
      }

      // 有工具调用：把 assistant 的 tool_calls 存进历史，再逐个执行
      appendAssistant(sess, { role: 'assistant', content: m.content ?? '', tool_calls: toolCalls,
                              ...reasoningToPassBack(m) });

      for (const tc of toolCalls) {
        const name = tc.function?.name;
        const t0 = Date.now();
        const out = await executeTool(name, tc.function?.arguments);
        toolTrace.push({ tool: name, ok: out.ok, ms: Date.now() - t0,
                         args: String(tc.function?.arguments ?? '').slice(0, 300),
                         error: out.ok ? undefined : out.error });
        // ★ 工具返回体的**最后一道字数闸**就设在这里（§2.4：上限必须有执行点）。
        //   `executeTool` 收口处已经剪过（`boundToolResult`），这里是**独立**的一道 ——
        //   因为「工具自己守规矩」不该是这条不变量成立的前提：任何一条路径把
        //   大对象塞进 memory，都会在下一次请求里挤掉模型的正文额度。
        //   实测：60,349 字工具结果 → 模型 reasoning 8000 tok、正文 0 字。
        const raw = JSON.stringify(out.ok ? out.result : { error: out.error });
        const body = raw.length > TOOL_OUTPUT_MAX_CHARS
          ? clipToolOutput(raw)
          : raw.slice(0, 60_000);
        if (raw.length > TOOL_OUTPUT_MAX_CHARS) {
          console.warn(`[agent] ⚠️ 工具返回体超预算：${name} ${raw.length} 字 → 入库前截到 ${TOOL_OUTPUT_MAX_CHARS} 字`);
        }
        mem.append(sess, { role: 'tool', tool_call_id: tc.id, content: body });
      }
      // 循环继续：让模型看到工具结果后决定是继续查还是作答
    }

    if (reply === null && !llmError) {
      // ── 工具循环用尽。**先试「兜底合成」，再考虑兜底话术**（2026-09-30 加）
      //
      // 原先是直接跳到兜底话术：「这个问题我没答上来 —— 查了几轮，还是没能得出可靠结论」。
      // 而 19:05 那次实测里，**工具 12 次调用一次都没失败**（`其中失败 0 次`），
      // 材料全都读到手了 —— 说「没答上来」对她是误导，对我方是**白丢一次本来能答的机会**。
      // 现在先关掉工具让它用手上的材料写一遍；只有**它也写不出来**才说兜底话术。
      const messages = mem.toLlmMessages(sess, systemPrompt);
      const s = await synthesizeFromTools({ systemPrompt, messages, why: 'tool-iters' });
      const got = s.ok ? String(s.text ?? '').trim() : '';
      synthesized = 'tool-iters';
      console.warn(
        `[agent] ⚠️ 工具循环用尽：上限 ${config.llm.maxToolIters} 轮 / 实调 ${toolTrace.length} 次`
        + `｜工具 ${[...new Set(toolTrace.map((t) => t.tool))].join(',') || '（无）'}`
        + `｜其中失败 ${toolTrace.filter((t) => !t.ok).length} 次`
        + ` → 已折叠工具返回体、关掉工具让它用手上的材料写一次：正文 ${got.length} 字`
        + (got ? '' : `（也没写出来${s.ok ? '' : `：${s.error}`} → 落兜底话术）`)
      );
      if (got) {
        reply = got;
        const cut2 = detectTruncation({ finishReason: s.finishReason, text: reply });
        if (cut2.cut) { reply = annotateTruncation(reply, { reason: cut2.reason }); truncated = true; }
        appendAssistant(sess, { role: 'assistant', content: reply,
                                ...(truncated ? { truncated: true } : {}),
                                ...(chainUnmeasured ? { chain_not_run: true } : {}),
                                ...reasoningToPassBack(s.message) });
      } else {
        toolExhausted = true;
        // 工具循环用尽仍未给出最终答复。文案见 `fallbackReply()` —— 它有一条硬约束
        // （不许出现工具名），由 `verify_cards.mjs` 的 L6 断言。
        reply = fallbackReply(toolTrace);
        // 工具名只进日志：可排查，但**不进正文**（正文那份由上面那个函数产生）。
        // ★ `tool_exhausted` 是**结构标记**，与 `llm_error` 同一用途：告诉补发队列
        //   「这条 assistant 不是真回答」。没有它，`answeredInMemory()` 会把兜底话术
        //   当成真回答，于是「答不上」就真的变成「永远答不上」——
        //   2026-09-22 她连问两次都得到兜底话术，而队列一条都补不出去。
        appendAssistant(sess, { role: 'assistant', content: reply, tool_exhausted: true,
                                ...reasoningToPassBack(s.message) });
      }
    }

    // ── 7. 压缩与落盘
    let compacted = false;
    try { compacted = await mem.compact(sess, llm.summarize); }
    catch (e) { console.error('[agent] 压缩异常', e?.message ?? e); }
    mem.save(sess);
    // 去重表必须**立即**落盘：只在退出时写的话，进程被 kill -9 时这次消息不在表里，
    // launchd 拉起后服务端若重推同一条，守衡会重复回话。
    flushSeen();

    if (llmError) {
      const notice = `我这边调用模型失败了，没法回答这个问题。\n\n失败原因：${llmError}\n\n（这是我的问题，不是你的输入有问题。）`;
      // ★ 1c（2026-09-22 加）：**群里看得见的话，记忆里必须也有**。
      //   原先这个分支直接 return，`mem.append` 只在回复循环里调 —— 于是守衡事后想不起
      //   自己说过「答不了」：她 15:40 问「你刚才为什么说答不了」，它的会话里只有
      //   她 15:29 的问题和 15:42 的正常答复，中间那次失败**在它的记忆里不存在**。
      //   `llm_error: true` 是给补发队列看的**结构标记**（不是靠比对那句文案）：
      //   「这条 assistant 不是真回答」。`toLlmMessages` 只取 role/content，不会漏给模型。
      mem.append(sess, { role: 'assistant', content: notice, llm_error: true });
      mem.save(sess);
      return { reply: notice, reason: 'llm_error', sessionKey: key,
               // ★ 2026-10-05 补：这一条原先**不带** `gate` / `chain` / `media` ——
               //   于是「模型这一跳失败」的时候，`mediaWithoutChain()` 那条棘轮读不到闸门读数，
               //   只能闭嘴。而「链跑了、模型又失败」恰恰是最该被看见的一种：
               //   结论算出来了、却没送到人手上。读数缺一格，警报就少一处。
               meta: { toolTrace,
                       media: { images: inbound.imageCount, videos: inbound.videoCount },
                       gate: gate ? { yes: gate.yes, kind: gate.kind, why: gate.why } : null,
                       chain: gate?.yes ? { ran: chainRan, ms: chainMs,
                                        publish: g.publish ? { ok: g.publish.ok,
                                                               action: g.publish.action,
                                                               record_id: g.publish.record_id ?? null } : null } : null,
                       llm: { layer: llmFailure?.layer ?? '未知',
                                        retryable: llmFailure?.retryable === true,
                                        attempts: llmFailure?.attempts?.length ?? 0,
                                        chain: llmFailure?.chain ?? [] } } };
    }

    // ── 「这一单**到底有没有三态结论**」——报错、拒答、库忙、超时都算「没有」 ──────────
    //
    // ★ 2026-10-08 修。上一轮我把判据写成 `!chainRan`（= 链报错），漏掉了一整类：
    //   **库忙（认领被占）时链是「跑成」返回的**（日志写 `🧭 送审链返回：跑成`），
    //   而旁挂是 `state=NEEDS_INPUT / reason_code=claim_busy` —— 一次三态都没有。
    //   后果（Owner 截图那一单）：卡片照发「库忙未判」、**补发队列 0 条、永远不补跑**。
    //   判据改成「链有没有给出 PASS/REVIEW/BLOCK」—— 比 `!chainRan` 严格得多，
    //   而且**不依赖任何字符串猜测**：`verdict53` 只可能由三态结论行（或 P0 派生）产生，
    //   `NEEDS_INPUT` 那一类根本没有 §5.3 行可抽（`LINE_RE` 只认三态）。
    const verdict53Final = g?.verdict53
      ?? ((toolTrace ?? []).some((x) => x.tool === 'kb_review_chain' && x.ok)
           ? deriveVerdictLine({ replyText: reply ?? '', reviewedByTool: true })
           : null);
    /** 闸门判了送审，但**没拿到三态结论** —— 还要看**这个缺口是不是会变的**，才决定补不补发。 */
    //
    // ══════════════════════════════════════════════════════════════════════════
    // ★★ 2026-10-08（第二轮修）：**「没拿到三态结论」不等于「链没跑成」。**
    // ══════════════════════════════════════════════════════════════════════════
    // 旧判据 `gate?.yes && !verdict53Final` 把两件**性质相反**的事混成了一件：
    //   · **瞬态** —— 库忙（认领被占）/ 某层闸门红 / 层审计红 / 前置异常退出。
    //     这些**本来会变**，隔几分钟再跑很可能就通了 ⇒ **该补发**（这就是旧判据的初衷）。
    //   · **语义** —— 引擎真的判过了，只是**库里没有可依据的条款**
    //     （`coverage_not_covered` / `evidence_side_refused`）⇒ 并入 `NEEDS_INPUT`。
    //     **重跑一百次还是同一个答案**，补发只是：白跑一条 2~3 分钟的链 + 群里多一条重复回复。
    // 为什么旧判据必然把它们混起来：PRD §5.3 只定义三态，`NEEDS_INPUT` **没有规范行**
    //   （`prd53.mjs::LINE_RE` 原文：「NEEDS_INPUT（依据侧拒答）**不在 5.3 里**」）
    //   ⇒ 任何拒答单的 `verdict53Final` **必然**是 null ⇒ **一律**被判成"链没跑成"。
    // 实测代价（当天日志，可核）：命中 2 次；其中一次真的往群里**补发了一条**
    //   （`✓ 已补发 … → om_x100b63401d2d60a4c3add838013e7ec`），而那一单**当时已经答完了**
    //   （回执+正文都发出去了、表也落了）。`MAX_TRIES=5`、窗口 1 小时 ⇒ 最多重跑 5 次。
    //
    // ⇒ 判据改成**读原因码**（不再用"有没有三态行"当代理）：
    //   只有「**本来会变**」的缺口才补 —— ① 连旁挂都没拿到（读不到 ⇒ 不知道，值得再探一次）；
    //   ② 原因码落在**资源/时序**那四个里。
    //   **语义类（coverage_not_covered / evidence_side_refused）与「未知」一律不补** ——
    //   那几种情况下引擎**已经判过了**，再跑是同一个答案。
    //   ⚠️ 这条**只收窄补发**：结论、三态、落表、闸门一个字节没动，也不放宽任何判据。
    const RETRYABLE_REFUSALS = new Set(['claim_busy', 'layer_gate_red',
                                         'layer_audit_red', 'preflight_aborted']);
    const kbDual = (g?.dual && typeof g.dual === 'object') ? (g.dual.kb ?? null) : null;
    const kbBlind = !(kbDual?.has_sidecar === true);
    const kbReason = String(kbDual?.reason ?? '').trim();
    const gapIsTemporal = kbBlind || RETRYABLE_REFUSALS.has(kbReason);
    chainUnmeasured = !!(gate?.yes && !verdict53Final && gapIsTemporal);
    // ★ 缺证据要**看得见**（库规）：不补发的那一类必须有一行日志说明「为什么这次不补」，
    //   否则「不补发」与「补发机制坏了」在外部长得一模一样 —— 正是本仓禁的那种形状。
    if (gate?.yes && !verdict53Final && !gapIsTemporal) {
      console.log('[agent] 🚫 没拿到三态结论，但**缺口不是瞬态的** ⇒ 不补发（补了也是同一个答案）'
        + `｜库侧读数=${kbDual?.has_sidecar === true ? (kbDual?.state || '—') : '无旁挂'}`
        + `｜原因码=${kbReason || '（未给）'}`
        + '｜补发只认资源/时序类：claim_busy / layer_gate_red / layer_audit_red / preflight_aborted。');
    }

    return { reply: reply || null,
             // ★ 2026-10-06 加第三种 reason `chain_not_run`（Owner：「每次发图片/视频都必须
             //   能正常回复，不能拒答」）。形状与 09-22 那次的 `tool_exhausted` **一模一样**：
             //   送审单起了链、链却没跑成（库忙 exit 3 / 超时 / 层前置红 / 依据侧没给结论）时，
             //   守衡照样有一条回复（「这一单未测，没有三态结论」）⇒ `reason` 本来是 `ok`
             //   ⇒ `ws_daemon` 的入队判据不收它 ⇒ 补发队列**连队都没进**，
             //   于是「问一次答不上，问十次还是答不上」。
             //   判据与 `chain_not_run` 那个记忆标记**同源**（`gate?.yes && !chainRan`），
             //   两处必须一起动：入队靠 reason，防「答两遍」靠记忆标记。
             reason: reply
               ? (toolExhausted ? 'tool_exhausted'
                  : (chainUnmeasured ? 'chain_not_run' : 'ok'))
               : 'empty_reply',
             sessionKey: key,
             meta: { toolTrace, compacted, summary_chars: (sess.summary ?? '').length,
                     truncated, synthesized,
                     // ★ 2026-10-08：`turns` 原先 = `sess.messages.length` —— 那是**条数**。
                     //   而 `ws_daemon.mjs` 把它印成「保留 N 轮」，于是日志上写着
                     //   「🗜 历史已压缩（保留 130 轮 + 纪要 5249 字）」，真实含义是
                     //   **130 条 ≈ 24 轮**（`config.llm.maxTurns`）。变量名、措辞、
                     //   实际的值三者不一致 —— `AGENTS.md` §2.4.3：说出去的话比依据大。
                     //   现在两个数一起给，各自名副其实：
                     //     `turns`    —— 按 `mem.countTurns` 的口径（几条 `user`，与 `compact` 同源）
                     //     `messages` —— 条数（含 assistant / tool）
                     //   ⚠ 口径只许有一处：要改「轮」的定义就去改 `memory.mjs::countTurns`，
                     //     不要在这里另写一个 filter。
                     turns: mem.countTurns(sess), messages: sess.messages.length,
                     // ★ 这一轮带了几个媒材 —— daemon 拿它问 `mediaWithoutChain()`：
                     //   「读到了、却没起链」这个形状**必须有个读数**，否则它只是一行没出现的日志。
                     media: { images: inbound.imageCount, videos: inbound.videoCount },
                     // ★ 2026-10-05 加：送审闸门自己的读数 —— 判没判、判成什么、链跑成没有、花了多久。
                     //   没有这三个数，「闸门到底有没有生效」就只能靠猜（而猜错的方向是「以为它跑了」）。
                     gate: gate ? { yes: gate.yes, kind: gate.kind, why: gate.why } : null,
                     // ★ 2026-10-13 加：**这一单落到结论表的哪一行**。
                     //   为什么加：本机批跑器要把结论回填进采集表，而媒体行**没法按素材原文认领**
                     //   （图片行送的是 post、链记的「送审问题」是图注；视频行送的是 media、
                     //    链记的是一段生成的块头 ⇒ 文本键结构上对不上；退到时间窗又会捡到
                     //    链侧那行**空的**）。实测栽过两次：`问题数量` 先被写成 0，视频行被写成 PASS/0。
                     //   ⇒ 让内核把**它自己刚写的那一行**报出来，回填就不必猜。
                     //   形态与上面「模型跳失败」那条路**逐字同形**（那边本来就有 publish 这一格）。
                     chain: gate?.yes ? { ran: chainRan, ms: chainMs,
                       publish: g?.publish ? { ok: g.publish.ok, action: g.publish.action,
                                               record_id: g.publish.record_id ?? null } : null } : null,
                     // ★ 2026-10-08 加：「链只跑一次」那条护栏自己的读数。
                     //   没有它，命中只是一个**没出现的日志**（§2.4 那个病）——
                     //   而这件事的代价是十几分钟 + 一次重复写飞书，必须看得见。
                     chainMemo: chainMemoStats(),
                     // ★ 2026-10-09 加：**「问题数」这唯一的那个数**（Owner 的规则要的那一个）。
                     //   抬头（`verdict53.line`）、逐条块、以及 PRD §5.3.4 的
                     //   **报告链接门槛（≥3）** 必须读同一个变量。
                     //   口径 = `dual_track.mjs:1140` 的 `total`：
                     //     **能并的条目 ＋ 库侧有明细但没并进来的（kbGap）＋ 覆盖缺口那 1 条。**
                     //   ⚠ 它不是 `stats.merged`：实测 19:08 那单 `merged=7` 而 `total=12`
                     //     （另有 5 条库侧明细未并进卡里，卡里写了一句话说明）。
                     //   为 null = 这一轮没跑双轨 ⇒ 抬头退回抠块/链的正文，
                     //   行为与改动前逐字相同（反向对照见 `test_agent.mjs` 的 `Z13`）。
                     mergedCount: g.dual?.total ?? null,
                     mergedState: g.dual?.state ?? null,
                     // ★ 2026-10-06 加：PRD §5.3 的权威结论行 —— daemon 把它一路交到
                     //   `replyTo → toCardOrText`，由信封层**搬进卡片的结论格**。
                     //   没有它，「逐字转述、不许改写」就只是一句写在提示词里的声明，
                     //   而实测证明模型会改写（Owner 看见的那三条就是）。
                     // ★ 2026-10-06：闸门没判送审、**但模型自己调了 `kb_review_chain`** 的那条路 ——
                     //   原先这里只认 `g?.verdict53`，于是那条路上的卡片抬头由模型自便
                     //   （Owner 发的 `REVIEW 1 处：W-1.16「限时」（覆盖不成立）` 就是这么来的）。
                     //   凭据是**这一轮真的调成了链**（`toolTrace` 里有一次 `ok` 的
                     //   `kb_review_chain`），不是「回复里出现了一行像 5.3 的字」。
                     verdict53: verdict53Final,
                     // ⚠️ 2026-10-13：**`mediaRead` 这一格撤了** —— 媒材读数按 Owner 的要求不上卡
                     //   （他 2026-10-06 说「视频还是无法读取」，那时读数搬上了卡；
                     //    2026-10-13 他把那一整段贴回来说「这里多余的回复也去掉」。两条相反，以最新为准）。
                     //   读数仍有三处落点：`📥 读到｜…` 日志（`raw:true`）、会话记忆、报告附录。
                     // 2026-10-09: 报告链接走**可见格**（结论块会被收起，藏里面等于没有）
                     reportLink: g.dual?.reportUrl ?? null,
                     outbound: { folded: outboundFold.folded, untested: outboundFold.plan.untested } } };
  });
}

/* ─────────────────── 供外部查询的运行时信息 ─────────────────── */

export function status() {
  return {
    model: config.llm.model,
    llm: llm.stats,
    tools: toolNames(),
    sessions: mem.listSessions(),
    maxTurns: config.llm.maxTurns,
    maxToolIters: config.llm.maxToolIters,
  };
}

/** 供 daemon 在启动时打印，确认工具与模型都装载成功 */
export function loadedTools() { return toolNames(); }
