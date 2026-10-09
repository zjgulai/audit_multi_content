/**
 * merged_report.mjs —— **「问题数 ≥3 就给一份可点开的完整清单」**（PRD §5.3.4 / §8.3 / §17）
 *
 * ── 为什么要有它（Owner 2026-10-09 的原话）
 *
 * > 「我的目标是让守衡输出的问题数量按照 PRD 等于或大于 3 个问题时，
 * >   **写入的飞书文档要带报告**」
 *
 * 在那之前，报告**只有库侧会生成**，而库侧的门槛读的是**它自己的** `issue_count`
 * （`feishu_publish.py::REPORT_LINK_MIN_ISSUES`）。于是出现这个形状：
 *
 *   卡上说「共发现 **6** 处」（库侧 1 ＋ 模型侧 5）⇒ 按 PRD 该给报告
 *   而旁挂 `issue_count = 1` ⇒ 库侧不生成 docx ⇒ `report_url = null` ⇒ **没有链接可给**
 *
 * 实测就是 2026-10-09 09:35 那张图。所以报告改由**本仓**建：
 * 门槛读**卡里那个数**（`dual_track.renderMerged` 的 `total`），
 * 正文含**两侧全部条目**（Owner：「6 个就展示 6 个问题」）。
 *
 * ── 为什么不调库侧的 `feishu_publish.py`（已查实，别走回头路）
 *
 *   `feishu_publish.py:495` `rid = None` ⇒ `:555` 的 `if rid:` **恒为假**（那段 update 是死代码）
 *   ⇒ `:561` 的 `+record-batch-create` **每次都走** ⇒ 再调一次**必然在业务表里多一行**。
 *   而 `review_publish.publishReportDoc()` **只建文档、不写表**，且与库侧
 *   **同一条命令、同一个身份**（`--profile dsh-kb --as bot`）—— 所以走它。
 *
 * ── 三条纪律
 *
 *   ① **条目措辞只有一处**：每一条都调 `renderMergedItem` —— 报告与卡片逐字同源。
 *   ② **失败不阻断结论**，但**必须照 `detail` 如实说**，不许把空 url 说成「已出报告」。
 *   ③ **正文字数不是门槛**：报告是给「逐条看」用的，卡里放不下的都放这里。
 */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { renderMergedItem, REPORT_LINK_MIN_ISSUES } from './dual_track.mjs';
import { publishReportDoc } from './review_publish.mjs';

/** 报告留底目录（`PMO/shouheng-state/` 是 gitignored 的运行时状态目录）。 */
export function reportDir() {
  const d = process.env.SHOUHENG_MERGED_REPORT_DIR
    || path.join(process.cwd(), '..', 'PMO', 'shouheng-state', 'merged-reports');
  try { fs.mkdirSync(d, { recursive: true }); } catch { /* 建不出来就走下面的兜底 */ }
  return fs.existsSync(d) ? d : os.tmpdir();
}

/**
 * 把**库内原文**变成能安全嵌入 markdown 的字面文本。
 *
 * ★★ 2026-10-09（Owner：「文案是合并报告，图片/视频现在是合并报告吗？这 3 个要改成一致的」）
 *   查出来的真因 —— 不是 fix #2 没生效，而是**合并报告建了但发不出去**：
 *
 *     建云文档失败：invalid <img> local resource tag:
 *     XML syntax error on line 1: invalid character entity &#39 (no semicolon)
 *
 *   库内记录的 `excerpt` **含原始 HTML**（实测那条视频单的命中原文是
 *   `>修改字幕</li></ol><img name="image.png" alt="…">` 与 `<table><colgroup>…`）。
 *   飞书 `docs +create` 会把 markdown 里的 `<…>` **当 HTML 解析** ⇒ 撞上坏实体
 *   ⇒ **整份文档被拒**（不是那一行坏，是整份）。
 *
 *   为什么"发文案对、发图/视频不对"：文案单的命中文案是纯文本（不含 `<`），
 *   图/视频单命中内部样本库的**富文本** ⇒ 必撞。最小复现＋修法都实测过：
 *   那份 12,877 字节的真实报告原样发 `ok:false`；**只**把 `<` `>` 转义后 `ok:true`。
 *
 * ⚠️ 与 KB 侧 `with_kb_evidence.py::md_text_safe` **同一口径**（那边是产者，这边是防线）。
 *   两处都在是有意的：**飞书导入崩掉整份文档**，代价是"报告根本没发出去"，
 *   而这不是守卫过度的场合 —— 转义只影响显示（读者看到 `&lt;img` 而不是 `<img`）。
 */
export const mdTextSafe = (s) => String(s ?? '')
  .replace(/</g, '&lt;').replace(/>/g, '&gt;')
  // ★ 2026-10-09（Owner 在报告里看到「~~」）：`~` 也要转义 —— 库内原文带 `~~…~~`
  //   （某人批注痕迹），印进 markdown 后被飞书渲染成**删除线** ⇒「依据」那一行被划掉、
  //   字段名与内容糊在一起（实测印成 `~~**~~依据~~**~~：…`）。
  //   `~` 在报告里**不承担任何 markdown 作用**（我们不用删除线）⇒ 转义无副作用；
  //   不转义则**原文观感被改**，读者会以为那段是被删掉的东西。
  .replace(/~/g, '&#126;');

/** 来源归到两段里 —— 与 Owner 的要求一致：「库侧问题＋模型侧问题」。 */
const isKbSide = (f) => f.source === 'kb' || f.source === 'both' || f.source === 'both-conflict';

/**
 * 报告头那一行「用户原提问」该印什么。
 *
 * 只有**媒材**的单子上，`input.question` 是内核自己拟的那段**探针**（给模型看的读数指令），
 * 不是对方写的话。原样印进报告头 ⇒ 报告被 35 行 OCR 片段 + 操作规程占满（Owner 报「太丑」）。
 *
 * 判据：探针的头注有固定形状（`【对方这条消息里附了…` / `【图片 N…` / `【图 N…` /
 * `【视频 N…` / `【待读的链接】`）。**只认这些开头**；认不出就**原样印**
 * （宁可长，不可错删 —— 万一是人真的写了以「【」开头的话）。
 *
 * @returns {string} 要印的内容；空串 = 这一行不印
 */
export function questionForReport(question) {
  const raw = String(question ?? '').trim();
  if (!raw) return { userLine: '', material: '' };
  // 探针（给模型看的读数指令）：**不进报告正文**，只把里面的素材读数摘出来放附录。
  if (/^【(对方这条消息里附了|图片\s*\d|图\s*\d|视频\s*\d|待读的链接)/.test(raw)) {
    return { userLine: '（对方**只发了素材**，没有写问题）', material: raw };
  }
  return { userLine: raw, material: '' };
}

/**
 * 渲染合并报告 markdown（**纯函数**，不碰磁盘、不碰网络 ⇒ 可以直接断言）。
 *
 * ⚠️ 第一行**必须是 H1**：`lark-cli docs +create --doc-format markdown` 靠它决定
 *    文档标题（与库侧 `feishu_publish.py` 那句 `assert body.startswith("# ")` 同一条约束）。
 *
 * @returns {string}
 */
export function renderMergedReportMd({
  merged = [], total = 0, state = '', line = '', question = '',
  contentId = '', at = '', kbGap = 0, kbTextCount = 0, modelCount = 0,
  // Owner 2026-10-09: 结构化告警（可选）—— 有就照搬进正文，没有也不能装作没有（常驻免责已在正文里）
  warnings = [],
  // ★ 2026-10-09：**从卡上撤下来的检索读数**（`kbHitsBlock`）—— 原样进附录，一条不丢。
  //   为什么搬到这儿：卡上那块业务同事看不懂（`BM25 205.88 ｜ 取不到直链 ｜ sha…`），
  //   但它是查证时的依据 ⇒ 不能砍，只能挪（搬是搬，砍是砍）。
  hitsBlock = null,
} = {}) {
  const kbItems = merged.filter(isKbSide);
  const modelItems = merged.filter((f) => !isKbSide(f));
  const must = String(state).toUpperCase() === 'BLOCK';

  const L = [];
  L.push(`# 内容审查报告 · ${contentId || at || '（未给内容 ID）'}`);
  L.push('');
  // ★★ 2026-10-09（Owner：「里面的【图 1 内文字｜35 行】，展示的太丑了」）──────────
  //   病灶：只有媒材的单子上，`input.question` 是**内核自己拟的那段探针**，
  //   而报告把它**整段逐字**印进报告头 —— 实测那份报告头里赫然是
  //   `【对方这条消息里附了图…】` + `【图 1 内文字｜35 行】` + **35 行 OCR 片段**
  //   + `【/图 1】` + 一大段操作规程 ⇒ 报告头被"给模型看的内部指令"占满，
  //   读者看到的是一堆断行的碎字（Owner 原话「太丑」）。
  //   ⚠️ **一个字都没丢**：素材读数本来就在报告正文里（逐条引文 / 附录检索读数）；
  //      这段探针是**指令**、不是内容。认出来时**如实说清**「对方只发了素材、没写问题」，
  //      不留空（留空会让人以为漏印）。
  const q = questionForReport(question);
  if (q.userLine) L.push(`- 用户原提问：${q.userLine}`);
  L.push(`- 内容 ID：\`${contentId || '—'}\` ｜ 审查时刻：${at || '—'}`);
  L.push(`- 结论：**${state || '—'}** ｜ 问题数量：**${total}**`
    + `（知识库侧 ${kbItems.length} 条 ／ 模型侧 ${modelItems.length} 条）`);
  L.push(`- 判据：PRD §5.3.4「问题数量 ≥ ${REPORT_LINK_MIN_ISSUES} 时生成完整报告并返回链接」`);
  L.push('');
  if (line) { L.push(line); L.push(''); }

  // ★★ 2026-10-09（Owner 反馈）：**这一段原先的标题是一句「声称」，不是事实。**
  //
  //   原话是 `## 一、知识库侧（有条款级依据）` —— 而实测那一单（原则性图）：
  //   卡上守衡自己写着「我读了云文档：**4/4 条依据与素材无关**，另 2 条 L0 sha 不一致」，
  //   而这四条在报告里顶着「**有条款级依据**」这个标题、还带条款号与飞书直链 ——
  //   **报告比卡片可信得多**，于是修好链接反而放大了危害。
  //
  //   改法两层，都只做**能与不能**的区分，不替库侧下结论：
  //     ① 标题从「有条款级依据」改成「库内条款条目」—— 只说**出处**，不下「所以它就对」的判断；
  //     ② 加一条**常驻免责**：相关性未经本报告核验，且**卡片上有告警时以卡片为准**。
  //   为什么常驻而不是「检测到才写」：我手上那个信号（`evidence_complete`）在这一单里是
  //   `undefined`，靠它判会时灵时不灵 —— 而**不确定性必须无条件说出来**，
  //   不能等到「我确信有问题」才说（§2.4.2：未测不许与通过长得一样）。
  const warnBlock = [
    '> ⚠️ **本段条目来自库内条款表 —— 这只说明它们的出处，不说明它们与本次素材相关。**',
    '> 条目与素材的**相关性、以及依据指纹（`source_sha256`）是否对得上，本报告不作核验**。',
    '> 守衡在卡片上若给出了相关性 / sha 告警，**以卡片为准**，并以那条告警决定是否采信本段。',
    ...(warnings || []).map((w) => `> ⚠️ ${w}`),
    '',
  ];
  L.push(`## 一、知识库侧（库内条款条目）—— ${kbItems.length} 条`);
  L.push('');
  L.push(...warnBlock);
  if (kbItems.length) {
    kbItems.forEach((f, i) => { L.push(renderMergedItem(f, i, { must })); L.push(''); });
  } else {
    L.push('（本单知识库侧没有并进任何条目。）');
    L.push('');
  }

  L.push(`## 二、模型侧（无库内依据，只能转人工）—— ${modelItems.length} 条`);
  L.push('');
  L.push('> 这一段里的条目**没有落在任何知识库条款上** —— 它们是模型独立一遍给的判断，');
  L.push('> **不得当通过依据，也不得据此当拦截依据**。下一步是转人工，不是照它改稿。');
  L.push('');
  if (modelItems.length) {
    modelItems.forEach((f, i) => { L.push(renderMergedItem(f, i, { must })); L.push(''); });
  } else {
    L.push('（本单模型侧没有并进任何条目。）');
    L.push('');
  }

  // ── 计数口径必须说清：`total` 是**卡里那个数**，它不等于「上面列出的条数」之和
  //    当库侧判到 ≥3 只出分类汇总时，明细抠不出来 ⇒ `kbGap > 0` ⇒ 上面列不全。
  //    不说清就会出现「报告里 6 条、卡上说 10 处」这种看起来像 bug 的差异。
  L.push('## 三、计数口径');
  L.push('');
  L.push(`- 本单**问题总数 ${total}** ＝ 已列出的 ${merged.length} 条`
    + (kbGap > 0 ? ` ＋ 知识库侧**另有 ${kbGap} 条未并进**（PRD §5.3.3：库侧问题数 ≥3 时只出分类汇总，`
      + '逐条明细在库内，未进本报告）' : '')
    + '。');
  L.push(`- 知识库侧结构化读数 ${kbTextCount} 条 ／ 模型侧 ${modelCount} 条。`);
  L.push('- 两轨**重叠未判** ⇒ 总数是**上限**（同一条问题若两侧都命中会被算两次，'
    + '`mergeFindings` 只在「位置与类目都相同」时并成一条）。');
  L.push('');
  // ── 附录：检索读数（从卡上撤下来的那一块，原样搬过来）────────────────────
  if (String(hitsBlock ?? '').trim()) {
    L.push('## 附录：检索读数');
    L.push('');
    L.push('> 这一段是**库内检索的过程读数**（命中单元、BM25 分、指纹、能否取到 L0 直链）。');
    L.push('> 它**不是审查结论**，也不进卡 —— 卡上只放能让人决定下一步的东西（PRD §5.3）。');
    L.push('> 查证「这条依据是怎么来的」时才需要它。');
    L.push('');
    // ★ `mdTextSafe`：检索命中里**含库内原始 HTML** ⇒ 不转义会让飞书拒收整份文档
    L.push(mdTextSafe(String(hitsBlock).trim()));
    L.push('');
  }
  // ── 附录：机读素材读数（**原样，不作可读化**）──────────────────────────────
  //   ★ 2026-10-09（Owner：「里面的【图 1 内文字｜35 行】，展示的太丑了」）：
  //     真相是**它本来就不可读** —— OCR 是**逐行碎片**（版面的列关系在 OCR 那一步就丢了）。
  //     实测：把它机械合并成段落只会**把不同栏的字揉在一起**（试过，读起来更糟）。
  //     ⇒ 所以**不假装它可读**：从正文挪到附录、如实标明「机读碎片，供回源核对」，
  //       正文里只留各条的引文与命中原话。
  //     ⚠️ 一个字不丢（搬是搬，砍是砍）——它仍是唯一能核对"当时读到了什么"的原始读数。
  if (q.material) {
    L.push('## 附录：机读素材读数（原样，供回源核对）');
    L.push('');
    L.push('> ⚠️ 这一段是**本机 OCR 的逐行碎片** —— 版面的列关系在 OCR 那一步就丢了，');
    L.push('> 因此它**读起来不通顺是正常的**（机械合并只会把不同栏的字揉在一起，试过，更糟）。');
    L.push('> 它的用途只有一个：核对"当时到底读到了什么字"。**不要把它当素材的排版或正文。**');
    L.push('');
    L.push(q.material);
    L.push('');
  }
  L.push('---');
  L.push('');
  L.push('*本报告由守衡在**本机**渲染后投成云文档；条目措辞与卡片逐字同源*'
    + '（同一函数 `dual_track.renderMergedItem`）。');
  return L.join('\n');
}

/**
 * 把报告 md 落盘并投成飞书云文档。
 *
 * ★ 失败**不抛**（`publishReportDoc` 自己就不抛），返回 `{ ok, url, detail, mdPath }`：
 *   调用方必须**照 `detail` 说** —— 库规「有权限不许说没权限」的反面同样成立，
 *   而「把 url='' 说成已出报告」是更坏的那一面。
 */
/**
 * 投出去之前的**最后一道兜底**：把「明显不是 markdown 的裸标签行」里的 `<` `>` 转义。
 *
 * ★ 为什么还要这一道（上面已经有两处精准转义）：报告的**其它片段**也可能注入库内原文
 *   （`_evidence_line` 的逐字命中、`_item_lines` 的引文……），而我**没有**穷举过所有注入点。
 *   而这一跳失败的代价是**整份文档发不出去**（实测：12,877 字节的报告被整体拒收），
 *   不是"少一行"。
 *
 * ★ 判据要**窄**（否则会把正常 markdown 一起转义，报告就变丑了）：
 *   逐行看，**只有「行内出现了 `</` 或 `<字母`」的行**才整行转义 —— 那种行不可能是
 *   正常 markdown（正常写法里不会在正文行内裸用 `<`），而是**从库内搬进来的 HTML**。
 *   ⚠️ 第一版只转义「单行内的完整标签 `<\/?[A-Za-z][^>\n]*>`」⇒ **漏了跨行标签**
 *     （实测那份报告的 `<img name="image.png"\n alt="…">` 横跨两行）⇒ 仍然发不出去。
 *     所以判据按**行**判、不按标签判。
 *   ⚠️ 第二版顺手加了 `&#\d`（裸实体）—— **实测不需要**：只含 `&#39` 的文档
 *     飞书照收（`ok:true`）。那个报错是**在标签内部**才冒出来的，而标签行已被上面那条覆盖。
 *     ⇒ 拿掉了，避免过度防守（`&#39` 是正常文本，转义它反而把原文改样）。
 */
export function mdBodySafe(md) {
  return String(md ?? '').split('\n')
    .map((line) => (/<\/?[A-Za-z]/.test(line) ? mdTextSafe(line) : line))
    .join('\n');
}

export async function publishMergedReport(md, { contentId = '', at = '' } = {}) {
  const safe = String(contentId || at || 'report').replace(/[^\w.-]+/g, '_').slice(0, 80);
  const mdPath = path.join(reportDir(), `merged-${safe}-${Date.now()}.md`);
  const body = mdBodySafe(md);
  try {
    fs.writeFileSync(mdPath, body);          // ★ Node 写（不是 Python）—— 不进 +4096 填充态
  } catch (e) {
    return { ok: false, url: null, mdPath: null, detail: `报告落盘失败：${e?.message ?? e}` };
  }
  const r = await publishReportDoc(mdPath);
  return { ...r, mdPath };
}
