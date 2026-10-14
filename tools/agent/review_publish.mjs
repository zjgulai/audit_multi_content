/**
 * review_publish.mjs —— **每一次评审都必须落表**（Owner 2026-10-05 定的硬规矩）
 *
 * ── 为什么要有它（两句话）
 *
 * 那天的真实情况：送了四条素材，链跑完了 3.5~17.9 分钟，**表里一行都没有**。
 * 原因有两层，第二层才是要命的：
 *   ① 链自己的发布条件是「有**三态结论**才发」——`publish.reason = no_conclusion`
 *      就把拒答（`NEEDS_INPUT`）整单跳过了；
 *   ② 于是「评审跑过、但结论是拒答」这件事在**盘上没有任何痕迹** ——
 *      人要问「这单审没审」只能去翻 KB 目录。
 *
 * Owner 的原话是「**每一个评审任务都必须落表**」。所以这条保证放在**我们这一侧**：
 * 链愿意自己发就发（那更好，字段更全）；链没发，**这里补上**。
 * 判据是「表里到底有没有这一行」，不是「链说它发了」。
 *
 * ── 幂等靠什么：内容 ID 的算法是**算出来的**，不是猜的
 *
 * 链给素材算的是 `content_id = "AUTO-" + sha256(送审文本去掉尾部空白).slice(0,12)`
 * —— 这条规则**逐字复算过**：拿 `_rt-img-20261005/rt-img-02-text.txt`（196 字节）
 * 去掉尾部换行后算 sha256，前 12 位正好是 `48cac901ac43`，与报告里的
 * `AUTO-48cac901ac43` 一致。
 * 所以这里能算出**同一个 ID**：先按它查表 —— 有就补空字段（不覆盖人填的），没有才新建。
 * **不做这一步就会出现「同一个内容两行」**，而重复行比缺行更难发现。
 *
 * ── 不覆盖什么（与 `lark_write.mjs` 的删除纪律同一条精神）
 *
 * `人工复核人` / `复核结论` / `sign-off 人` / `审核人` / `发布时间` 是**人的格子**：
 * 补写只补**空着的、且由机器产出的**那些字段，人填过的一律不动。
 */
import crypto from 'node:crypto';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { createRecords, updateRecords, listRecords, flat } from './lark_write.mjs';
import { plainify } from './plain.mjs';

const execFileP = promisify(execFile);

/**
 * **P0 报告投递**（2026-10-06 加）。
 *
 * ── 为什么要有它
 *
 * Owner 2026-10-06 定的口径（三句话，逐条对应一个实现决定）：
 *   ① 「**P0 问题可先在飞书侧响应**」 —— 回执卡在 `runSubmissionGate` 里**先发**
 *      （`notify(ackMessage(...))`），P0 判定在它之后，所以这一步**不在任何响应预算里**；
 *   ② 「**写入云文档报告的时间不统计在 ≤1 秒内**」 —— PRD §12 的「P0 层响应 ≤1s」
 *      量的是 **P0 判定**（`p0_fastpath.py` 的 `elapsed_ms`，实测 9.8 ms），
 *      而「报告生成 ≤30s」是**另一条**指标。⇒ 这里超时按 **30 s** 设，超了就照实说没生成。
 *   ③ 「**补充报告**」 —— 报告不是"以后再说"：这一步**必须**跑，
 *      跑成了就把链接填进回执、填进表行的 `报告链接`；跑不成要**看得见**（返回 detail），
 *      **不许**静默留空、更不许编一个链接。
 *
 * ── 为什么走 `lark-cli` 而不是 Node SDK
 *
 * 与库内发布件 `kb/l7/review-engine/core/feishu_publish.py` **同一条命令、同一个身份**
 * （`--profile dsh-kb --as bot`）：那条路已经把「从第 1 行写、不传 --title（标题就是正文首行 H1）、
 * 用 markdown 导入而不是 append」这些坑趟平了。这里**不复刻它的判据**，只复用它踩平的路。
 * 自己拿 SDK 拼 docx block 会把「markdown → 块」那套转换再写一遍，必错。
 */
export const P0_DOC = Object.freeze({
  profile: process.env.SHOUHENG_LARK_PROFILE ?? 'dsh-kb',
  bin: process.env.SHOUHENG_LARK_CLI ?? path.join(os.homedir(), '.dsh', 'bin', 'lark-cli'),
  timeoutMs: Number(process.env.SHOUHENG_P0_DOC_TIMEOUT_MS ?? 30000),
});

/**
 * 把一份**本地报告 .md** 投成飞书云文档，返回它的 url。
 *
 * ★ **失败不抛、不阻断结论** —— 报告没生成，P0 的 BLOCK 照样成立（那是两件事）。
 *   所以返回 `{ok, url, detail}`：调用方必须**照 detail 说**，不许把 `url=""` 说成"已出报告"。
 *
 * ★★ `cwd: path.dirname(f)` 不是随手写的（2026-10-06 实测踩过，值得记下来）：
 *   `lark-cli` 的 `@file` **拒绝工作目录之外的文件**。实测四种组合：
 *     · 库内路径 ＋ cwd=库根        → ✅ ；· 库内路径 ＋ cwd=报告所在目录 → ✅
 *     · 库内路径 ＋ cwd=tools/agent → ❌ `--content: invalid file path`
 *     · 库内路径 ＋ cwd=/tmp        → ❌ 同一句错
 *     · /tmp 里的文件 ＋ 任意 cwd   → ✅ （`/tmp` 是它额外放行的）
 *   本函数第一版没设 `cwd`，于是**不管报告写得多好，云文档一律建不出来** ——
 *   而它当时的表现只是「报告：未生成」，看起来像权限问题。
 *   把 cwd 设成**报告自己所在的目录**就有了不依赖任何外部约定的保证：文件必在其 cwd 之下。
 */
export async function publishReportDoc(mdPath) {
  const f = String(mdPath ?? '').trim();
  if (!f) return { ok: false, url: null, detail: '没给报告文件路径' };
  if (!fs.existsSync(f)) return { ok: false, url: null, detail: `报告文件不存在：${f}` };
  try {
    const { stdout } = await execFileP(P0_DOC.bin, [
      '--profile', P0_DOC.profile, 'docs', '+create',
      '--content', `@${f}`, '--doc-format', 'markdown', '--as', 'bot',
    ], { timeout: P0_DOC.timeoutMs, maxBuffer: 8 << 20, cwd: path.dirname(f) });
    let j = null;
    try { j = JSON.parse(String(stdout)); } catch { /* 下面按 raw 报 */ }
    const url = j?.data?.document?.url ?? '';
    if (!url) {
      return { ok: false, url: null,
        detail: `lark-cli 回了但没给 url：${String(stdout).slice(0, 200)}` };
    }
    return { ok: true, url, detail: `云文档已建（${j?.data?.document?.document_id ?? '?'}）` };
  } catch (e) {
    // ★ 把 CLI 的原话带出来 —— 库规「有权限不许说没权限」的反面同样成立：
    //   报错要能区分「没建权限」与「命令写错」，糊成一句「失败了」等于把排查成本转给人。
    const err = String(e?.stderr ?? '').trim() || String(e?.message ?? e);
    return { ok: false, url: null, detail: `建云文档失败：${err.slice(0, 300)}` };
  }
}

/** 评审结论表（Owner 给的落点：wiki Lntdw8XqmifewjkdEckcXYH8nOV → 这张表） */
export const REVIEW_TABLE = Object.freeze({
  appToken: 'RY2UbCRjXaeeWwscUPScVN5AnQc',
  table: 'tblCXPQVzfFWWCon',
});

/**
 * 落表要写哪张表。
 *
 * ★ 2026-10-05 现场踩到的坑，必须记下来（§2.4.4 那个形状的又一例）：
 *   **跑一次自证，往 Owner 的真实飞书表里写了两行。**
 *   `runSubmissionGate` 里那段「保证落表」对**测试桩**也照跑不误 ——
 *   于是单测里 `chainRunner` 返回一句假的 `结论：REVIEW`，就真的在群里那张表上建了一行；
 *   紧接着下一条反向对照（链没跑成）又把那一行的 `状态` 改成「待审」。
 *   自证不但没验出问题，**自己成了问题的来源**。
 *   修法两条，缺一条都不算修好：
 *     ① 落表这一步**可注入**（`publishRunner`，与 `chainRunner` 同一套写法）；
 *     ② 这里留一个**关掉它的闸门**（`SHOUHENG_REVIEW_TABLE=off`），自证默认拉闸 ——
 *        这样即使将来谁漏传了桩，也写不进真表。
 */
export function reviewTable() {
  const raw = String(process.env.SHOUHENG_REVIEW_TABLE ?? '').trim();
  if (!raw) return REVIEW_TABLE;
  if (/^(off|none|0)$/i.test(raw)) return null;         // ← 拉闸
  const [appToken, table] = raw.split('/');
  if (!appToken || !table) return REVIEW_TABLE;
  return { appToken, table };
}

/** 机器可以填的字段；其余（人的格子）一律不碰。 */
export const MACHINE_FIELDS = Object.freeze([
  '内容 ID', '送审问题', '内容类型', '渠道', '产品线', '送审版本',
  'Agent 结论', '置信度', '问题数量', '问题分类汇总', '报告链接', '状态',
]);

/**
 * **结论派生列 —— 允许改写**（2026-10-08，Owner 同意「推荐 B」）。
 *
 * 这几个字段是**本轮结论的函数**，必须跟着结论走；表里其余机器列仍「只补空」。
 *
 * ── 为什么非改不可（两条都是实测，不是推论）
 *   ① **多轮送审时结论会变**：同一文案第三次送审 REVIEW → BLOCK（P0 快路对上）——
 *      「只补空」会让表**定格在第一轮**，卡里 BLOCK、表里还是 REVIEW。这正是 Owner
 *      最初报的那类「同一单两个结论」。
 *   ② **写错的机器列此后永远改不回来**（比①更坏）：实测素材 A 那行 `recvxlTh9b6HYq` ——
 *      `Agent 结论=REVIEW`（**引擎**建行时写的）＋ `问题分类汇总=「未能得出结论（NEEDS_INPUT）」`
 *      （**守衡**后来写的，当时那条判据过宽）⇒ 两格都已填 ⇒ **谁也改不动**，
 *      这一行自相矛盾且**无法自愈**（下一个判据修好了也追不回来）。
 *
 * ── 边界一个字没松
 *   · `HUMAN_FIELDS`（人工复核人／复核结论／sign-off 人／审核人／发布时间）**照旧一个字都不碰**，
 *     哪怕它空着也不替人下笔；
 *   · 其余机器列（内容 ID／送审问题／内容类型／渠道／产品线／送审版本／**报告链接**）照旧「**只补空**」——
 *     那条规则要防的是「模型先写进去的『未指定』把真值永久挡住」，以及报告链接那种
 *     **只该被第一次写进去**的值（复跑不许把旧链接改掉）；
 *   · 值**没变就不写**（免得一次「什么都没变」被记成一次写入、把 `unchanged` 报成 `updated`）。
 */
export const CONCLUSION_DERIVED_FIELDS = Object.freeze([
  '状态', 'Agent 结论', '问题数量', '置信度', '问题分类汇总',
]);

/** 把飞书那几种字段形状摊平成可比较的字符串（文本数组 / 数字 / 链接 / 选项）。 */
function plainOf(v) {
  if (v === undefined || v === null) return '';
  if (Array.isArray(v)) return v.map(plainOf).join('');
  if (typeof v === 'object') {
    if ('text' in v) return plainOf(v.text);
    if ('link' in v) return plainOf(v.link);
    if ('value' in v) return plainOf(v.value);
    if ('name' in v) return plainOf(v.name);
    return JSON.stringify(v);
  }
  return String(v);
}

/** 同值判定：`'3'` 与 `3`、`[{text:'REVIEW'}]` 与 `'REVIEW'` 都算同值。 */
export function sameValue(a, b) {
  const pa = plainOf(a).trim();
  const pb = plainOf(b).trim();
  if (pa === pb) return true;
  const na = Number(pa);
  const nb = Number(pb);
  return pa !== '' && pb !== '' && Number.isFinite(na) && Number.isFinite(nb) && na === nb;
}

/**
 * **置信度 / 问题数量：永不为空**（Owner 2026-10-06 明令「不允许为空」）。
 *
 * ── 为什么不能只是「拿不到就留空」
 * PRD §8.2 把这两个字段列为**必录**。而引擎在**拒答态**（`NEEDS_INPUT`）**就是不给** confidence
 * （`with_kb_evidence.py` 拒答分支写 `None`），`agent.mjs` 原先按「不许编数」留空 ⇒ 表里出现空列。
 * 这件事 2026-10-05 记过一次（契约里的 `known_leftovers`），2026-10-06 Owner 又现场指出
 * ——「**昨天修复过了，今天又复现了**」。
 * ★ **同一个形状出现两次 ⇒ 留空不是"诚实"，是把问题藏起来**：空格既说不出"引擎没给"，
 *   也说不出"我们没读到"，看表的人只能来问。
 *
 * ── 口径（写进代码，也**拼进汇总列** —— 看表的人不必来问）
 *   · P0 命中            → 问题数 = 引擎命中条数；置信度 = **1.0**（确定性命中，PRD §6.6 不分流）
 *   · 链给出三态值        → 用引擎值（实测 PASS 0.99 / REVIEW 0.78）
 *   · 引擎不给（拒答/未测）→ **0**：**0 = 「没有做出判定」，不是「零风险」**（汇总列写明）
 *   · 读数缺失（旁挂没读到）→ **0** ＋ 汇总列写明「读数缺失」
 *
 * ★ 这就是「不允许为空」的代价：**填了数就必须同时填口径**。
 *   只填一个 0 而不说它是什么意思，比空格更坏 —— 它看起来像一个结论。
 *
 * @param {object} res 链/快路的返回（`res.review` 是旁挂，`res.p0_fastpath` 是 P0 标记）
 * @param {string|null} conclusion 已判定的三态/拒答
 * @returns {{issueCount:number, confidence:number, note:string}} `note` 为空 = 没做任何替换
 */
export function machineNumbers(res = {}, conclusion = null) {
  const rev = res?.review ?? null;
  const fin = (...vals) => vals.find((v) => Number.isFinite(v));
  const p0 = !!res?.p0_fastpath;
  const state = String(conclusion ?? '').toUpperCase();
  // ★ 三种"没数"要**分开说** —— 混成一句会让排查方向全错：
  //   · `missing`：机读旁挂**根本没读到**（文件缺失/不新鲜）⇒ 该去查旁挂，不是查引擎；
  //   · `refused`：引擎**明确不做判定**（拒答/未测）⇒ 库的覆盖不够，不是坏了；
  //   · 其余：引擎给了结论却没给这个量。
  const missing = !rev;
  const refused = state === 'NEEDS_INPUT' || !!rev?.refusal;
  const notes = [];

  let issueCount = fin(rev?.issue_count, res?.issue_count);
  if (issueCount === undefined) {
    issueCount = 0;
    notes.push(p0 ? '问题数量按 **0** 记（P0 未给条数）'
                  : missing ? '问题数量按 **0** 记（**本单没读到引擎读数**）'
                            : '问题数量按 **0** 记（引擎未给出该读数）');
  }
  let confidence = fin(rev?.confidence, res?.confidence);
  if (confidence === undefined) {
    confidence = 0;
    notes.push(missing
      ? '置信度按 **0** 记 —— **本单没读到引擎读数（机读旁挂缺失/不新鲜）**；这个 0 **不是**置信度'
      : refused
        // ★ 这一句是关键：0 必须自带解释，否则会被读成「零风险」。
        ? '置信度按 **0** 记 —— **0 = 引擎未做判定（拒答/未测），不是「零风险」**'
        : '置信度按 **0** 记（引擎未给出该读数）');
  }
  return { issueCount, confidence, note: notes.join('；') };
}

/** 人填的字段：补写时**绝不覆盖**（哪怕它现在是空的，也不替人下笔）。 */
export const HUMAN_FIELDS = Object.freeze([
  '人工复核人', '复核结论', 'sign-off 人', '审核人', '发布时间',
]);

/**
 * 送审文本 → 内容 ID。**与知识库那条链同一个算法**（实测复算过，见文件头）。
 * @param {string} materialText 送进链的素材文本（逐字）
 */
export function contentIdOf(materialText) {
  const t = String(materialText ?? '').replace(/\s+$/, '');
  if (!t) return null;
  return `AUTO-${crypto.createHash('sha256').update(t, 'utf8').digest('hex').slice(0, 12)}`;
}

/** 结论 → 表里的 `状态`。**六档里没有「拒答」**，所以拒答落到「待审」（等人看）。 */
export function statusOf(conclusion) {
  const c = String(conclusion ?? '').toUpperCase();
  if (c.includes('BLOCK')) return 'BLOCK';
  if (c.includes('REVIEW')) return 'REVIEW';
  if (c.includes('PASS')) return 'PASS';
  // NEEDS_INPUT / 拒答 / 未测 / 空 —— 都落到「待审」：**它们都还没有定论，等人**
  return '待审';
}

/**
 * 从链的返回原文里抽 `Agent 结论`。**抽不到就回 null，不猜。**
 *
 * ★★ 2026-10-07 收紧（Owner 同意）—— 旧版是 `\b(PASS|REVIEW|BLOCK|NEEDS_INPUT)\b`，
 *   取**全文第一个**三态词。那是 fail-**open** 的：一句免责话就能把结论抠成 PASS。
 *   实测（三个反例，全部抠成 `PASS`）：
 *     · 「库侧未参与 ⇒ 本条**不得当 PASS 依据**。结论：REVIEW。」
 *     · 「本次没跑到引擎，所以**不能当 PASS**；请重试。」
 *     · 「链没跑成，结论未知（不是 PASS，也不是 REVIEW）。」
 *   素材 D（表行 `recvxlAvpEWMIX`）就是这么在**库侧零读数**的情况下落了 `Agent 结论=PASS`。
 *
 * ⇒ 现在**只认「像读数」的位置**：结论行（`【审查结论：X】` / `结论：X` / `判定：X`）、
 *   状态行（`state = X` / `状态：X`）、以及链原文里的 `引擎最终输出：X`。
 *   这些是**有格式契约**的地方（PRD §5.3 的结论行、引擎报告第一节的 `state = X`）。
 *   其他地方出现三态词**一律不认** —— 宁可不写这一格，也不许把"不能当 PASS"读成 PASS。
 *
 * ⚠️ 代价（已知并接受）：若某个回答用「最终结论为 REVIEW」这种**没有冒号**的写法，
 *   这一格就抽不出来了（回 null ⇒ 不写）。**这比抽错好**：空值人会补，错值人不会回头看。
 */
export function conclusionOf(answer) {
  const s = String(answer ?? '');
  const S = 'PASS|REVIEW|BLOCK|NEEDS_INPUT';
  const m = s.match(new RegExp(
    '(?:【\\s*审查结论\\s*[：:]|审查结论\\s*[：:]|结论\\s*[：:]|判定\\s*[：:]'
    + '|状态\\s*[：:]|state\\s*=\\s*|引擎最终输出\\s*[：:])'
    + '\\s*\\**\\s*`?\\s*(' + S + ')'));
  return m ? m[1] : null;
}

/** 把要写的字段拼成一行（只带**有值**的机器字段；空值不写，免得覆盖成空）。 */
export function rowFieldsOf({
  contentId, question, contentType, channel, productLine, version,
  conclusion, confidence, issueCount, summary, reportUrl,
} = {}) {
  // ★ 2026-10-14：**落库的正文格也要摘 markdown 符号**（Owner：「所有输出中不允许包含 `**` 星号」）。
  //   这张表就是「落库」本身，而它此前**照单全收**上游来的字符串：`问题分类汇总` 里那句
  //   `问题数量按 **0** 记` 是**我们自己的代码**拼的，`送审问题` 是模型/人给的原文 ——
  //   两条路都会把星号带进单元格，而这一格**不经过任何渲染**，星号就是字面字符。
  //   实测（2026-10-14，只读盘点）：表里 294 行中 **164 行**至少有一格带 `**`。
  //   实现只有一份：`agent/plain.mjs`（别在这里再写一遍）。
  //   ⚠️ 只摘**文本格**：数字、链接、选项、人员这些格一个都不动（它们没有 markdown 语义）。
  const f = {};
  const cell = (v) => plainify(String(v));
  if (contentId) f['内容 ID'] = contentId;
  if (question) f['送审问题'] = cell(question).slice(0, 2000);
  if (contentType) f['内容类型'] = cell(contentType).slice(0, 200);
  if (channel) f['渠道'] = cell(channel).slice(0, 200);
  // ★ 产品线（2026-10-06）：Owner 要求「从知识库命中产品线和渠道的都填写进去」。
  //   值由 `kb/l5/l0_facets.py` 出（**唯一取数点**）：**本素材自己的记录**（`品线`）优先，
  //   其次**素材原文**逐字命中受控词；命中的记录**若是规则样本则一律跳过**（不拿样本的投放属性充数）。
  //   取不到就是空 ⇒ 这里不写这一格（**不写「未指定」，也不从素材正文猜**）。
  if (productLine) f['产品线'] = cell(productLine).slice(0, 200);
  if (version) f['送审版本'] = cell(version).slice(0, 200);
  if (conclusion) f['Agent 结论'] = cell(conclusion).slice(0, 200);
  // ★ 这两个字段：调用方应已用 `machineNumbers()` 保证**永不为空**（Owner 2026-10-06 明令）。
  //   这里仍只认有限数 —— 传进来 null 就不写这一格，**不许在这里悄悄补 0**：
  //   「补 0 + 口径」是 `machineNumbers()` 的职责，两处都补会让一个 0 丢掉它的解释。
  if (Number.isFinite(confidence)) f['置信度'] = confidence;
  if (Number.isFinite(issueCount)) f['问题数量'] = issueCount;
  if (summary) f['问题分类汇总'] = cell(summary).slice(0, 20000);
  if (reportUrl) f['报告链接'] = { link: String(reportUrl), text: '审查报告' };
  f['状态'] = statusOf(conclusion);
  return f;
}

/**
 * **保证这一单在表里有且只有一行。**
 *
 * @param {object} row 见 `rowFieldsOf`
 * @param {{ctx?:object, dryRun?:boolean}} [opt] `ctx` 会写进写入台账（谁改的）
 * @returns {Promise<{ok:boolean, action:'created'|'updated'|'unchanged'|'skipped',
 *                    record_id?:string, readback?:string, detail?:string}>}
 */
/**
 * 列出表里的行，**把形状读对**。
 *
 * ★ 2026-10-05 实测踩到的坑：`lark_write.listRecords()` 回的是 `{ ok, records: [...] }`，
 *   而我第一版读的是 `page.items` —— 于是**永远读到空数组**，
 *   后果是「链已经写过那一行」也看不见，**每一次都再建一行**（同一单两行）。
 *   它不报错、不抛异常，只是安静地写重。这类错正是 §2.4.1 点名的形状：
 *   接口读通了、`ok:true`，字段名读错 → 产出假数据，而假数据跟真数据长得一模一样。
 *   所以这里**两种键名都试**，都不对就明说「读不出形状」，**不许静默当空表**。
 */
async function readRows(T) {
  const page = await listRecords(T.appToken, T.table, { limit: 500 });
  if (!page?.ok) return { ok: false, detail: `列表读不到：${page?.msg ?? page?.error ?? '未知'}` };
  const rows = page.records ?? page.items;
  if (!Array.isArray(rows)) {
    return { ok: false, detail: `列表返回的形状不认：keys=${Object.keys(page ?? {}).join(',')}`
                              + ' —— 既没有 records 也没有 items' };
  }
  return { ok: true, rows };
}

/**
 * **占位符**：看起来"填了"，其实什么都没说。
 *
 * ★ 2026-10-06 实测踩到：表里那三行（09:48–09:52 那批）的 `产品线` / `渠道` 是 **`未指定`** ——
 *   不是 `rowFieldsOf` 写的（它取不到值就**不写这一格**），是**模型自己**按手册里的
 *   「缺省自动补 AUTO-…/未指定/未指定/v1.0」填进去的。
 *   而 upsert 的纪律是「**非空就不覆盖**」（那是为了不覆盖人填的）⇒
 *   **`未指定` 三个字把真值永久挡在门外**：库里明明有 `品线=吸奶器`，那一格却永远是"未指定"。
 *
 * ⇒ 判据：**占位符按"空"对待**，可以被真值替换。
 *   ⚠️ 只用于 `MACHINE_FIELDS`（机器产出的那些格）—— `HUMAN_FIELDS`（人填的）**一个都不动**，
 *     哪怕人填的就是「未指定」，那也是人的决定，不替他改。
 */
const PLACEHOLDERS = Object.freeze(new Set(['未指定', '无', '待定', '-', '—', 'N/A', 'n/a', 'null', 'None']));

/** 这一格**真的被填了**吗（占位符不算）。 */
function isFilled(v) {
  if (v === undefined || v === null || v === '') return false;
  return !PLACEHOLDERS.has(String(v).trim());
}

/**
 * **同一内容是不是已经有报告了** —— 有就返回那一份的链接，没有返回 null。
 *
 * ── 为什么需要它（2026-10-06 验证时发现，Owner 批准方案 (c)）
 *
 * 实测形状：同一份素材**复跑**时，`ensureReviewRow` 会按「内容 ID」找到**旧行**、
 * 只补空字段（其余原样保留），可是**云文档那一步已经先新建了一份新的** ⇒
 * 旧行的「报告链接」被「非空不覆盖」挡住，**新报告成了孤儿**（没人能点到的文档）。
 *
 * ── 三个候选方案与为什么选这个（Owner 选定 (c)）
 *   (a) 内容 ID 命中就当不命中 → 新建一行：**会产生重复行**，而重复行比缺行更难发现；
 *   (b) 「报告链接」随最新一次审查更新：行内会**自相矛盾**（汇总写旧审查、链接指新报告）；
 *   (c) **复用旧行已有的链接、不新建文档** ← 选它：既不产孤儿、也不产重复行，行与报告始终一致。
 *       内容 ID 是**送审文本的 sha256** ⇒ 同一 ID 就是**同一份素材**，报告逐字相同，复用语义正确。
 *
 * ── 代价（实测，不估）
 *   多一次查表：`listRecords` 读 15 行 = **1037 ms**。它发生在**回执卡之后**，
 *   不占 PRD §12 的任何一条预算（「P0 层响应 ≤1s」量的是判定，仍 ~12 ms）。
 */
export async function previousReportLink(contentId) {
  const cid = String(contentId ?? '').trim();
  if (!cid) return null;
  const T = reviewTable();
  if (!T) return null;
  const listed = await readRows(T);
  if (!listed.ok) return null;
  const row = listed.rows.find((it) => it?.fields?.['内容 ID'] === cid);
  const v = row?.fields?.['报告链接'];
  if (v === undefined || v === null || v === '') return null;
  // 形状实测两种：`{link,text:'审查报告'}` 与 `{link,text:<url>}` —— 统一从 link 取，
  // 取不到再退回 `flat()`，都取不到就当没有（**不许编**）。
  const url = (typeof v === 'object' && v && typeof v.link === 'string') ? v.link
            : String(flat(v) ?? '').match(/https?:\/\/\S+/)?.[0] ?? '';
  return /^https?:\/\//.test(url) ? url : null;
}

export async function ensureReviewRow(row, { ctx = { actor: 'shouheng/review-gate' }, dryRun = false,
                                           since = null, question = null } = {}) {
  const T = reviewTable();
  if (!T) {
    return { ok: false, action: 'skipped',
             detail: '落表被 SHOUHENG_REVIEW_TABLE=off 关掉了（自证专用闸门）—— 没写任何东西' };
  }
  const fields = rowFieldsOf(row);
  const id = fields['内容 ID'];

  // ① 先找「**这一轮刚出现的那一行**」——判据是时间窗，不是内容 ID。
  //
  //   ★ 为什么不能只靠内容 ID 去重：链给素材算的 `content_id` 是拿**它自己抽取的
  //     送审文本**算的（实测：`rt-img-02-text.txt` 196 字节 = 15 行 OCR，去掉尾部空白后
  //     sha256 前 12 位 = `48cac901ac43`），而**我们这边那份 `text` 带着我们加的标题行**
  //     （`【图片 1 的图内文字（本机 OCR）】`），两者**不是同一串字节**，算出来必然不同。
  //     拿两个不同的 ID 去「幂等」，结果是**同一个内容两行** —— 而重复行比缺行更难发现。
  //     所以判据放在**行为**上：链要是自己写了，那一行一定出现在它这次跑的这段时间窗里。
  //     时间窗优先、内容 ID 兜底，两个都不中才新建。
  let found = null;
  if (since) {
    try {
      const listed = await readRows(T);
      if (!listed.ok) return { ok: false, action: 'skipped', detail: listed.detail };
      const fresh = listed.rows.filter((it) => {
        const t = Number(it?.fields?.['写入时间'] ?? 0);
        return t && t >= Number(since) - 120_000;      // 2 分钟余量（表侧钟差/写入排队）
      });
      // 认哪一行：**先认问句**，认不出来地再退到「窗口里唯一那一行」。
      //   ⚠️ 两条都必须成立才敢认，否则宁可自己新建 —— 反向对照就是冲着这条来的：
      //   窗口里只有一行、但那一行是**别人的**（问句对不上）时，认了它 = 把别人的记录改掉。
      const mine = String(question ?? '').trim();
      const qOf = (it) => String(it?.fields?.['送审问题'] ?? '').trim();
      const sameQ = (a, b) => a && b && (a === b || a.includes(b) || b.includes(a));
      found = (mine ? fresh.find((it) => sameQ(qOf(it), mine)) : null)
           // 退路：窗口里**只有**一行，且它没写问句（链可能不写这一格）—— 那才认它
           ?? (fresh.length === 1 && !qOf(fresh[0]) ? fresh[0] : null);
    } catch (e) {
      return { ok: false, action: 'skipped', detail: `列表抛异常：${e?.message ?? e}` };
    }
  }
  // 时间窗没命中 → 再用内容 ID 找一遍（链跑得久、或它把行写在了窗口之前）
  if (!found && id) {
    try {
      const listed = await readRows(T);
      if (listed.ok) found = listed.rows.find((it) => it?.fields?.['内容 ID'] === id) ?? null;
    } catch { /* 上面那条已经报过错了，这里静默兜底 */ }
  }

  // ── ② 算 patch（**已有那一行** → 补空着的机器字段；**结论派生列允许改写**；人填过的一律不动）──
  //   ★ 2026-10-06 把这段**提到 dryRun 之前**：原来 dryRun 在算 patch 之前就 return 了，
  //     于是干跑**看不见它打算写什么** —— 那不叫干跑，那叫表个态。
  //     库规是「**干跑要能看见它要做什么**」：`--dry-run` 的意义就是让人在写之前核对。
  let patch = {};
  if (found) {
    const cur = found.fields ?? {};
    for (const k of MACHINE_FIELDS) {
      if (!(k in fields)) continue;
      // ★ `isFilled()` 而不是 `!== ''`：**占位符（未指定/无/待定…）按"空"算** ——
      //   否则模型先写进去的「未指定」会把真值永久挡住（实测：3 行卡在 `产品线=未指定`）。
      const has = isFilled(cur[k]);
      // ★ 2026-10-08（Owner 同意「推荐 B」）—— **结论派生列允许改写**，其余机器列仍只补空。
      //   `状态` 原先就在这里开过一次口子（「拒答 → 待审」必须能改过来），
      //   现在把同一理由**推广到另外四格**：多轮送审结论会变（REVIEW→BLOCK），
      //   而「只补空」会让表**定格在第一轮**、甚至把一次写错**永久钉死**（见 `CONCLUSION_DERIVED_FIELDS` 注释）。
      if (has && !CONCLUSION_DERIVED_FIELDS.includes(k)) continue;
      // 值没变就不写：免得把一次「什么都没变」记成一次写入（`unchanged` 被报成 `updated`）。
      if (has && sameValue(cur[k], fields[k])) continue;
      patch[k] = fields[k];
    }
  }

  if (dryRun) {
    return { ok: true, action: found ? (Object.keys(patch).length ? 'updated' : 'unchanged') : 'created',
             record_id: found?.record_id ?? null,
             patch,                       // ★ 干跑要能看见**它打算写什么**
             detail: `dry-run：${found
                       ? (Object.keys(patch).length
                           ? `会补这一行的 ${Object.keys(patch).length} 个空字段：${Object.keys(patch).join('、')}`
                           : '这一行的机器字段都填着了，不会写任何东西')
                       : '会新建一行'}`
                     + `${id ? `（内容 ID=${id}）` : '（算不出内容 ID，仍会新建）'}` };
  }

  if (found) {
    if (!Object.keys(patch).length) {
      return { ok: true, action: 'unchanged', record_id: found.record_id, detail: '该填的都填着了' };
    }
    const r = await updateRecords(ctx, T.appToken, T.table,
                                  [{ record_id: found.record_id, fields: patch }]);
    return { ok: !!r?.ok, action: 'updated', record_id: found.record_id,
             readback: r?.readback, detail: r?.readback_detail ?? r?.error ?? null };
  }

  // ③ 没有 → 新建。**这一条就是「每一个评审任务都必须落表」的兜底**。
  //   ★ 算不出内容 ID **也照样写**（只把那一格留空）：这条保证不能被「算 ID」绑架 ——
  //     拒答、超时、链没跑成，都还是要有一行留痕。
  const r = await createRecords(ctx, T.appToken, T.table, [fields]);
  return { ok: !!r?.ok, action: 'created', record_id: (r?.record_ids ?? [])[0] ?? null,
           readback: r?.readback, detail: r?.readback_detail ?? r?.error ?? null };
}
