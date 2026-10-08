/**
 * review_gate.mjs —— **「这条消息是不是一次送审」这个判断的唯一出处**
 *
 * ── 为什么要有它（2026-10-05，委托方第三次重申「工作流必须走」）
 *
 * 那条链本身是通的（`tools/agent/tools.mjs` 的 `kb_review_chain`，实测跑过
 * 691s / 771s / 1809s 三次，报告与飞书行都落过）。缺的从来不是能力，是**触发**：
 *
 *   · 09:22 有人发了一条视频、**一个字没写** → 守衡把读数描述了一遍就收工，
 *     `PMO/logs/ws_daemon.log:2498` 那一轮**一次工具都没调**，她要的结论一个字没有。
 *   · 根因：路由规则写在**人设里**（「『能不能发 / 审一下』这类问题走 kb_review_chain」），
 *     而**人设是一句声明，不是约束** —— 模型想不起来，就没有任何东西会红。
 *     `AGENTS.md` §2.4：写进文档的每条约束，必须指得出**哪一行在拦它**。
 *
 * 所以这一条从「人设里的一句话」搬成了「**内核自己走的代码**」：
 * `handleMessage` 在把控制权交给模型**之前**，先问 `isSubmission()`；答「是」就直接把链跑完，
 * 再把链的结论交给模型去组织回话。**模型不需要「想起来」要调它。**
 *
 * ── 什么算送审（Owner 2026-10-05 现场定的口径）
 *
 *   · **带了媒材** —— 图 / 视频 / 链接，**只要发就一定算**（不看有没有文字）；
 *   · **纯文字** —— 像送审的才算：**≥ 30 字**，或命中 `REVIEW_WORDS` 里任一词
 *     （「审」「能不能发」「合规」「过审」…）。「在吗」「你能干什么」不算。
 *
 * 判据都是**纯函数**，所以能离线反向对照（`tools/test_agent.mjs` 第 18 组）：
 * 喂一条闲聊必须**不**触发，喂一条光秃秃的媒材必须触发。
 */
import { bodyToText } from './feishu.mjs';

/** 纯文字要多长才「像送审」。不是拍脑袋：一句正经的送审描述基本都过 30 字。 */
export const MIN_REVIEW_CHARS = 30;

/**
 * 「像送审」的词表。**故意只收「意图明确」的**，不收「内容」「文案」这类中性词 ——
 * 后者会让「你上次那段文案写得不错」也触发一次 10~30 分钟的链。
 */
export const REVIEW_WORDS = [
  '审', '过审', '送审', '合规', '违规', '违法', '踩线', '红线',
  '能不能发', '能不能上', '能不能用', '可不可以发', '能不能过', '能不能出',
  '有没有问题', '有没有风险', '有问题吗', '风险吗',
  '依据', '条款', '广告法', '禁用词', '极限词', '绝对化',
  '宣称', '背书', '发布前', '风控', '打回', '驳回',
];

/** 文本里的链接（飞书文档/表格/wiki 与外部网页都算）。 */
export const LINK_RE = /https?:\/\/[^\s<>"'）)】\]]+/g;

export function findLinks(text) {
  const m = String(text ?? '').match(LINK_RE);
  return m ? [...new Set(m)] : [];
}

/** 去掉链接与多余空白之后的「正文」，用来判字数与关键词。 */
function bareText(text) {
  return String(text ?? '').replace(LINK_RE, ' ').replace(/\s+/g, ' ').trim();
}

/**
 * 这一条是不是**送审**？
 *
 * @param {{text?:string, imageCount?:number, videoCount?:number}} input
 * @returns {{yes:boolean, kind:'media'|'link'|'text'|null, why:string, links:string[]}}
 */
export function isSubmission({ text = '', imageCount = 0, videoCount = 0 } = {}) {
  const links = findLinks(text);
  const body = bareText(text);

  // ① 媒材：图 / 视频只要发了就算 —— 不看文字（Owner 口径）。
  if (imageCount > 0 || videoCount > 0) {
    const what = [imageCount > 0 ? `图 ${imageCount} 张` : null, videoCount > 0 ? `视频 ${videoCount} 段` : null]
      .filter(Boolean).join(' + ');
    return { yes: true, kind: 'media', why: `带了媒材（${what}）—— 媒材本身就是送审`, links };
  }
  // ② 链接：贴了链接就是要看里面的东西。
  if (links.length) {
    return { yes: true, kind: 'link', why: `贴了链接（${links.length} 条）—— 要读的就在链接里`, links };
  }
  // ③ 纯文字：够长，或命中送审词。
  const hit = REVIEW_WORDS.filter((w) => body.includes(w));
  if (hit.length) {
    return { yes: true, kind: 'text', why: `命中送审词：${hit.slice(0, 3).join('、')}`, links };
  }
  if ([...body].length >= MIN_REVIEW_CHARS) {
    return { yes: true, kind: 'text', why: `正文 ${[...body].length} 字 ≥ ${MIN_REVIEW_CHARS} —— 够长，按送审走`, links };
  }
  return { yes: false, kind: null, why: `正文 ${[...body].length} 字、没命中送审词、也没带媒材`, links };
}

/* ─────────────── 送进链里的东西：问什么、拿什么当素材 ─────────────── */

/**
 * 把这一条消息整理成链的输入。
 *
 * ★ 素材的取法**按模态分开**，不是把整段提示词塞进去：
 *   · 图 / 视频 —— 送**本机读到的读数**（帧上的字 + 音轨转写 + 文件名与时长），
 *     不是送「提示词」；同时明写没读到的那部分（画面本身），否则链会以为素材就这些。
 *   · 链接 —— 送链接本身（链那边自己有 lark 工具会去读）。
 *   · 纯文字 —— 逐字送原文。
 *
 * @param {{question:string, inbound:object}} input
 * @returns {{question:string, text:string, media:string[]}}
 */
export function chainInput({ question = '', inbound = {} } = {}) {
  const parts = [];
  const media = [];

  for (const im of inbound.images ?? []) {
    if (im.text) { parts.push(`【图片 ${im.index} 的图内文字（本机 OCR）】\n${im.text}`); media.push('image'); }
    else if (im.ocrEmpty) parts.push(`【图片 ${im.index}】取到了，但图上没识别出文字。`);
    else parts.push(`【图片 ${im.index}】**没读到**：${im.failed ?? '未读'}。`);
  }
  for (const v of inbound.videos ?? []) {
    media.push('video');
    if (v.failed) { parts.push(`【视频 ${v.index}】**没读到**：${v.failed}。`); continue; }
    const m = v.meta ?? {};
    const lines = [`【视频 ${v.index}｜${v.fileName ?? '未给文件名'}｜${m.duration_s != null ? Number(m.duration_s).toFixed(1) + 's' : '时长未知'}`
      + `${m.w && m.h ? `｜${m.w}×${m.h}` : ''}｜关键帧 ${v.framesRead ?? 0}/${v.frames?.length ?? 0} 帧读成功】`];
    const frames = (v.frames ?? []).filter((f) => f.text)
      .map((f) => `  [${Number(f.t_s).toFixed(2)}s] ${String(f.text).replace(/\n/g, ' / ')}`);
    lines.push(frames.length ? `画面上的字（按时间码）：\n${frames.join('\n')}` : '画面上的字：这几帧里没读出一个字。');
    const t = v.transcript ?? {};
    lines.push(t.ok
      ? (t.chars ? `音轨转写（本机识别）：${t.text}` : '音轨转写：识别器回了空结果（整条音轨没识别出话）。')
      : (t.kind === 'no_audio_track' ? '音轨：这条视频没有音轨（静音片子）。'
        : (t.kind === 'no_speech' ? '音轨：整条音频里没有人说话（是读数，不是没跑成）。'
          : `音轨：**转写没跑成**（${t.kind ?? '未知'}）—— 声音里说了什么未知。`)));
    lines.push('（本机只能看到抽样的这几帧：构图、动作、场景、产品怎么用**不在**上面的字里。）');
    parts.push(lines.join('\n'));
  }
  if ((inbound.images ?? []).length === 0 && (inbound.videos ?? []).length === 0) {
    const links = findLinks(inbound.text ?? '');
    if (links.length) parts.push(`【待读的链接】\n${links.join('\n')}`);
    else if (inbound.text) parts.push(inbound.text);
  }

  return {
    question: question || inbound.text || '（对方只发了素材，没有写问题）',
    text: parts.join('\n\n'),
    media: [...new Set(media)],
  };
}

/* ─────────────── 链的结论怎么交给模型 ─────────────── */

/**
 * 把链的返回包成一段给模型看的读数。
 *
 * ★ 三种结局必须长得不一样（§2.4.1）：
 *   · 跑成了 —— 结论原文照抄，**一个字都不许改写**（依据里有条款号与锚点）；
 *   · 跑失败 / 超时 —— 「**结论未知**」，不许当成通过，也不是「没问题」；
 *   · 链被别的会话占着 —— 「**没有送审**」，同样不是通过。
 */
export function formatChainBlock(result) {
  // ★ 两种形状都认：链自己的返回，以及 `executeTool()` 的那层信封 `{tool, ok, result}`。
  //   认不出来就把一个跑成的链写成「结论未知」—— 那是一种**安静地把成功说成未知**的形状，
  //   实测踩过一次（见 `agent.mjs` 的 `defaultChainRunner`）。
  let r = result ?? {};
  if (r && typeof r === 'object' && ('result' in r || 'ok' in r) && !('answer' in r) && !('error' in r)) {
    r = r.ok === false ? { error: `工具调用失败：${r.error ?? '没给原因'}` } : (r.result ?? {});
  }
  if (r.error) {
    const unknown = /未知|没送审|超时|timeout/i.test(String(r.error));
    return '【★ 知识库那条链**没跑成** —— 这一步的结论是**未知**，不是「没问题」，也不是「通过」。'
      + `\n链的原话：${String(r.error)}`
      + (r.hint ? `\n提示：${String(r.hint)}` : '')
      + '\n**照实说「结论未知」，并说清是哪一种没跑成**；不许替链下结论，也不许把它说成通过。】';
  }
  const answer = String(r.answer ?? '').trim();
  if (!answer) {
    return '【★ 知识库那条链跑完了，但**没有返回结论原文** —— 这等于结论未知，不是通过。照实说。】';
  }

  // ★ P0 快路（2026-10-05）—— 这一支**不是**「那条链跑完了」。
  //   它命中 P0 后**没有跑** L4→L5→L6→L7 层前置，也没有跑评审链。
  //   抬头必须照实说：把一条红线拦截写成「链已跑完、报告已落盘」，
  //   就是拿"完整的审查"冒充一次确定性匹配 —— 库规里「缺前置必须可见、不许静默」正是防这个。
  if (r.p0_fastpath) {
    const p = r.p0_fastpath;
    return '【★ 本单走的是 **P0 快路**（PRD §6.3 第一层 / §12「P0 层响应 ≤ 1 秒」）：'
      + `确定性匹配命中知识库**已定稿的 P0 红线**，**直接 BLOCK**，耗时 **${p.elapsed_ms} ms**`
      + `（命中 ${p.matched_patterns} 条模式：${(p.rule_codes ?? []).join('、')}）。`
      + `**没有跑** L4→L5→L6→L7 层前置，也**没有跑**评审链 —— 它是**红线拦截**，`
      + `不是专项审查结论，**不得当 PASS 依据**。`
      + '**下面是结论原文，逐字转述，不许改写、不许加自己的判断**：\n'
      + `${answer}\n`
      // ★ 2026-10-06：报告链接现在**已经写在结论正文里**（`p0_fastpath.py --report-ref`
      //   把真 url 填进了「查看完整问题清单与修改建议」那一格，PRD §5.3.3 要的那一格）。
      //   所以这里**不再重复贴一遍** —— 重复会让模型以为有两个链接、或者干脆漏掉正文里那个。
      //   没出报告时**不写任何占位**：`r.report` 空就是空，不许编。
      + (r.report
          ? (String(answer).includes(r.report)
              ? '（报告链接已写在上面那段结论里，**照它原样转述、不要重复贴**。）\n'
              : `（报告：${r.report}${r.record_id ? ` ｜ 飞书行：${r.record_id}` : ''}）\n`)
          : '')
      + '—— 回话时把结论放在最前面；★ 不许把这条说成"整条链跑完了"，也不许说成"专项审过了"；'
      + '★ 若素材属图片/视频/产品宣称等模态，结论里那句「仍需转对应专项复核」必须照说。】';
  }

  return '【★ 知识库那条链**已经跑完**了（L4→L5→L6→L7 层前置 + 评审链）。'
    + '**下面是它的结论原文，逐字转述，不许改写、不许加自己的判断**：\n'
    + `${answer}\n`
    + (r.report ? `（报告：${r.report}${r.record_id ? ` ｜ 飞书行：${r.record_id}` : ''}）\n` : '')
    + '—— 回话时把结论放在最前面，依据与边界照它写的说；'
    // ★ 2026-10-06 修正：原话是「报告已落盘、飞书已写」—— **无条件这么写是假陈述**。
    //   实测（2026-10-06 07:47–07:50 三单）：`kb/l7/reports/` **零新增** ——
    //   因为 `with_kb_evidence.py` 的 `write_report` 默认 `False`、且 **CLI 上没有开它的开关**，
    //   它会给依据侧加 `--dry-run` ⇒ 根本不落盘；而 `NEEDS_INPUT` 时发布件也拒发。
    //   所以改成**只按下行括号里的事实说**，没有括号就是这两件没发生。
    + '★ **「报告 / 飞书行」以括号里那一行为准：没有括号 = 这两件没发生**，'
    + '**不许**自己补一句「报告已落盘」。'
    + '★ 若它的结论是「未测 / 结论未知」，那就是**未知**，不许说成通过。】';
}

/**
 * 链一开始就先回一条 —— 而且**回的是卡片，不是一段话**（Owner 2026-10-05 现场给的样子）。
 *
 * ★ 这条改了两处，两处都是 Owner 现场判的：
 *
 *   ① **去掉时长估计**。原话：「实际时间跟预估的不符，6~30min 可以去掉」。
 *      核过是对的：本机实测一条图 **3 分 32 秒**（20:08 那条：20:08:23 回执 → 20:11:30 链返回），
 *      而回执写「6~30 分钟」—— 估高了，而且**估得再准也没有用**：
 *      人真正要知道的只有两件事：**它收到了**、**它在动**。给一个不准的钟，不如不给。
 *      （排队那件事仍然要说，但它只在**真的在排队时**才说，见 `queued`。）
 *
 *   ② **改成卡片**（`receipt` 类型）：截图那张就是
 *      「⏳ 处理中… / 正在处理，请稍等，马上给你结果。」
 *      形态由 `tools/reply-cards/envelope.mjs` 那边校验（判据：`verify_cards.mjs`），
 *      这里只负责**递一个合法的卡片块**过去 —— 模型不写卡片 JSON，这段代码也不手搓 V2 结构。
 *      ★ 2026-10-06：这张卡的配色从「灰头」改成了**淡暗粉**
 *        （表头 `carmine` + 正文 `carmine-50` 色带，委托方在 6 张色卡里挑的 D）。
 *        起因是委托方看截图提的两条：回执不要灰色、任何两类不许撞色 ——
 *        当时回执与能力边界卡都是 grey。配色表在 `reply-cards/cards.mjs` 的 `TONE`，
 *        判据是 `verify_cards.mjs` 的 J9a–J9e。**这里一个字都不用改**，只更新了这句注释。
 *
 * @param {{kind?:string}} gate
 * @param {{queued?:boolean}} [opt] `queued=true` 表示知识库那边**此刻**有人在跑（读锁得知）
 * @returns {{block:string, plain:string}} `block` 给发送层（会成形为卡片）；`plain` 是纯文本兜底与台账用
 */
export function ackMessage(gate, { queued = false } = {}) {
  const note = queued
    ? '知识库那边现在有别的任务在跑（同一时间只准一单），这条要排队，排到了就正常跑。'
    : undefined;
  // ★ 2026-10-05 加（Owner 裁定「建议2：区域不问、直接按美国审、回复抬头固定说明一句」）：
  //   依据 PRD 第一阶段原文——首页「**项目：美国市场内容治理｜第一阶段**」、
  //   能力表「| 市场 | **美国** |」、「外部标准库：**美国法规**、平台政策、行业标准、医学共识、本地常识」。
  //   ⇒ **美国是系统既定口径，不是待用户填的参数**，所以这里**固定声明、不追问**
  //     （呼应 AGENTS.md 既有的「不许追问内容 ID / 渠道 / 产品线 / 版本」那条纪律）。
  const scopeLine = '本次按**美国市场**口径审查（PRD 第一阶段范围）。';
  const card = { title: '⏳ 处理中…', verdict: '正在处理，请稍等，马上给你结果。' };
  card.note = note ? `${scopeLine}\n${note}` : scopeLine;
  return {
    block: `[[card:receipt]]\n${JSON.stringify(card)}`,
    plain: `⏳ 处理中…\n正在处理，请稍等，马上给你结果。\n${card.note}`,
  };
}

/** 纯文本形态（台账 / 兜底）。**不带任何时长估计** —— 见 `ackMessage` 的注释。 */
export function ackText(gate, opt = {}) {
  return ackMessage(gate, opt).plain;
}
