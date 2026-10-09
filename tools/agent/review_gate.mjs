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
// ★ 2026-10-09：帧文本改走 `video.frameLine`（**唯一产者**）—— 原先这一处自己拼过一份，
//   与 `video.mjs` / `agent.mjs` 那份是两份实现。`video.mjs` 不引本模块，无循环依赖。
import * as video from './video.mjs';

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
    if (im.text) {
      // ★★ 2026-10-09：喂给链的是**摘掉水印后**的文本（`wlText`），不是 OCR 原文。
      //   为什么（Owner 亲自看出来的根）：图内 OCR 混着**文档水印**（用户名 + 工号，
      //   实测 `5615 RO0 / 刘华丽 / 刘华問`），而这段原文**直接进了 BM25 检索** ⇒
      //   拿水印里的常用词撞库 ⇒ 撞出一堆无关的内部样本、又被渲染成「命中」进报告。
      //   ⇒ 检索用 `wlText`；**原文一个字不丢**（仍进 `im.text`，卡片显示"我读到了什么"用它）。
      //   ⚠️ 摘了要在**给模型的正文里说明** —— 否则模型会以为"图上就这些字"，
      //     把水印里读到的东西当成素材内容去判（那正是要修的病）。
      //   ⚠️ 说明里**只报条数、不列出水印串本身** —— 第一版把串列了出来（"摘除：5615 RO0、刘华丽"），
      //     那等于**又把它们放回给模型的正文里**，模型照样能照着判 ⇒ 修了等于没修。
      const body = String(im.wlText ?? im.text);
      const wmNote = (im.wmDropped?.length)
        ? `\n（本机 OCR 另读到 ${im.wmDropped.length} 行**水印/印章类文字**，`
          + `已从检索文本中摘除，**不要把它们当素材内容**；`
          + `摘除明细见日志与报告，需要核对时由人调取。）`
        : '';
      parts.push(`【图片 ${im.index} 的图内文字（本机 OCR${wmNote ? '，已摘除水印' : ''}）】\n${body}${wmNote}`);
      media.push('image');
    }
    else if (im.ocrEmpty) parts.push(`【图片 ${im.index}】取到了，但图上没识别出文字。`);
    else parts.push(`【图片 ${im.index}】**没读到**：${im.failed ?? '未读'}。`);
  }
  for (const v of inbound.videos ?? []) {
    media.push('video');
    if (v.failed) { parts.push(`【视频 ${v.index}】**没读到**：${v.failed}。`); continue; }
    const m = v.meta ?? {};
    const lines = [`【视频 ${v.index}｜${v.fileName ?? '未给文件名'}｜${m.duration_s != null ? Number(m.duration_s).toFixed(1) + 's' : '时长未知'}`
      + `${m.w && m.h ? `｜${m.w}×${m.h}` : ''}｜关键帧 ${v.framesRead ?? 0}/${v.frames?.length ?? 0} 帧读成功】`];
    // ④ 与卡片/模型侧**共用同一个 `frameLine`**（原先这里自己拼过一份）。输出**逐字不变**。
    const frames = (v.frames ?? []).map((f) => video.frameLine(f)).filter(Boolean);
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
    // ★ 2026-10-08 加：**别再调一次 `kb_review_chain`。**
    //   实测事故（Owner 2026-10-08 19:08 那张图）：闸门 2.5 分钟就跑完了，
    //   而模型又自己调了一遍（709 秒、超时没出结果），于是：
    //     ① 人等了 **15 分钟**（`💬 回复 3159 字，耗时 900041ms`）；
    //     ② 模型把它那次失败写进了**对外卡片** ——「我这次实跑 709 秒没出最终回答」。
    //   拦它的**执行点**在 `tools.mjs` 的 `executeTool`（同一轮再调直接回缓存，不重跑）；
    //   这一句是**治因**：模型原先不知道链已经跑过了 —— §2.4 那句
    //   「人设是声明，不是约束」说的正是这里：两处都要有，缺一处就退回今天这张卡。
    + '★ **这一单的链已经跑完了 —— 不要再调 `kb_review_chain`。**'
    + '结论就是上面这一段：再跑一次要 5~15 分钟，而且会往飞书**再写一遍**。'
    + '★ 若你发现自己已经调过、且那一次**没出结果**，**不许把它写进回话** ——'
    + '上面那段才是这一单的结论。「我实跑 N 秒没出结果」是内部读数，**不进对外正文**。'
    + '★ 若它的结论是「未测 / 结论未知」，那就是**未知**，不许说成通过。】';
}

/**
 * 把**闸门这一次落表的读数**交给模型 —— 「飞书表里到底有没有这一行」只许照抄它。
 *
 * ★ 为什么必须有这一段（2026-10-09 实测事故，Owner 拿着截图来问的那张卡）：
 *   那一单是图片评审，链在 **L6 闸门红**处停下（`layer_gate_red`，退出码 4），
 *   闸门**照规矩把这一单落了表**（`recvxwCWhwCO68`，14:11:57 update，状态=待审），
 *   32 秒后发出去的那张 alert 卡里却写着：
 *     「**对你有什么影响**：这条素材现在没有结论……**飞书表也没落这一行（拒答档）**。」
 *   —— **与盘上的事实相反**。而模型不是撒谎：那段「影响」是它自己写的，
 *   `chainBlock`（它唯一能看到的读数）里**根本没有落表这一步的结果** ——
 *   `formatChainBlock()` 在链返回时就定稿了，而落表发生在**它之后**（`runSubmissionGate` 6.0 段）。
 *   §2.4.1 那句话在这里第二次应验：**读数是空的，模型就用猜的填**；
 *   而这一次它猜的方向正好是「表里没有」—— 于是人以为整条链路什么都没留下。
 *
 * ★ 判据只认**这次调用的返回**（`publish` 对象），不认任何字符串推断：
 *   `ok/action` 来自 `ensureReviewRow()`，`record_id` 是它回读到的行号。
 * ★ 三种结局必须长得不一样（§2.4.1）：**落了 / 没落 / 这一步压根没跑**。
 *
 * @param {{ok?:boolean, action?:string, record_id?:string|null, readback?:string|null, detail?:string|null}|null} publish
 * @param {{conclusion?:string|null, status?:string|null}} [ctx] 这一单的结论与它对应的表内状态
 * @returns {string} 给模型看的一段读数（会拼进 `chainBlock`）
 */
export function publishFactBlock(publish, { conclusion = null, status = null } = {}) {
  const p = publish ?? null;
  if (!p) {
    // 走到这里说明落表那一步**没有产出读数**（抛异常被 catch 掉，或闸门根本没跑到那一步）。
    // 「没有读数」不是「没有落表」—— 所以措辞是「不许提表」，不是「说表里没有」。
    return '【★ 飞书评审表**没有落表读数**（这一步没有产出任何结果）—— '
      + '关于表里有没有这一行，**你手上没有任何读数** ⇒ 回话时**一个字都不许提表**：'
      + '别说落了、也别说没落。只说结论本身。】';
  }
  if (p.ok) {
    const action = p.action === 'created' ? '新建'
      : (p.action === 'updated' ? '更新'
        : (p.action === 'unchanged' ? '已是最新（无需改写）' : `写入（${String(p.action ?? '未知动作')}）`));
    return '【★ 飞书评审表**落表读数**（代码产出，**只许照抄、不许自行推断**）：'
      + `**已${action}这一单在表里的那一行**｜行号 \`${p.record_id ?? '（未回读）'}\``
      + `｜结论=${conclusion ?? '（未给）'}｜状态=${status ?? '（未给）'}`
      + `｜回读=${p.readback ?? '（未回读）'}。`
      + '★ **这一行就是这一单在表里的位置** —— 回话里若要提表，只能照这一行说；'
      + '★ **不许**说「表里没有这一行」「没落表」「没留下痕迹」之类与它相反的话。】';
  }
  // 没落成：`skipped`（被熔断闸门关掉）与真失败**不是一回事**，措辞要分开 ——
  // 前者是**故意的**（`SHOUHENG_REVIEW_TABLE=off`，自证专用），后者是故障。
  const detail = String(p.detail ?? p.error ?? '（未给原因）').slice(0, 200);
  const why = p.action === 'skipped'
    ? `落表这一步**没有执行**（skipped）｜原因：${detail}`
    : `落表**失败**｜原因：${detail}`;
  return '【★ 飞书评审表**落表读数**（代码产出，**只许照抄、不许自行推断**）：'
    + `${why}｜行号=${p.record_id ?? '（无）'}。`
    + '⇒ 这一单在表里**没有行**。'
    + '★ 这是**守衡自己这一侧的故障**，不是素材的问题，也不是「库里说它有问题」——'
    + '回话时可以照实说「这一单没能落到表里、需要人看一眼」，'
    + '★ 但**不许**说成「已落表 / 表里有了」。】';
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
