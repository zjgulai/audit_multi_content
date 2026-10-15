/**
 * scene.mjs —— **画面层读数**：把「人发给守衡的那张图」交给**吃图的模型**看一眼，
 * 换回一份**结构化的、只陈述可见事实**的读数。
 *
 * ── 它补的是哪半条范围（2026-10-15）
 *
 *   PRD §5.1 对图片写的是两半：输入 **「OCR + 基础视觉识别」**，
 *   输出依据 **「图片文字、产品使用、人物行为、场景风险」**。
 *   而本项目此前**只做了 OCR 那半** —— 知识库侧与模型侧吃的都是同一份图内文字，
 *   「画面」两侧都没看过。起因是 `vision.mjs` 头注里那句话：
 *   **「守衡的模型是 `deepseek-flash`，不吃图」**。
 *
 *   ★ 那句话**是错的，2026-10-15 当场实测否掉了**（同一天、同一个端点、同一把密钥）：
 *     POST `https://api.deepseek.com/chat/completions`，`model=deepseek-flash`，
 *     content 里带 `{type:'image_url', image_url:{url:'data:image/jpeg;base64,…'}}`
 *     → **HTTP 200**，回答：「一位女士抱着婴儿，一位男士在水槽边洗东西，
 *     厨房台面上放着两个粉色半透明球形容器。」（与那张图的实物一致）。
 *   ⇒ 不需要新引服务商、不需要新密钥：**用项目已经在用的那个端点**。
 *
 * ── 边界（每一条都有执行点，别只当注释读）
 *
 *   · **只读临时目录里的图**：`loadImage()` 会拒绝任何不在 `os.tmpdir()` 之下的路径。
 *     取字节那一步（`feishu.mjs` 的 `fetchMessageResource`，全仓唯一调用点）本来就落临时目录，
 *     用完即删 —— 本模块**不自己取字节、不联网拉图**。
 *   · **只陈述可见事实，不下结论**：提示词写死「不许判合规、不许给建议、不许编看不见的」，
 *     并要求把「看不清 / 这张图里没有」单独列进 `unclear`。
 *     ★ 为什么卡这么死：这份读数会进**模型侧**的输入去参与判定 ——
 *     如果它开始"推理"，那就不再是读数，而是**第二个判定者**，而它没有条款、没有锚点。
 *   · **读不到 ≠ 没有画面**：`ok:false`（超时/网络/JSON 解不出）与
 *     `ok:true` 但字段全空，**必须长得不一样**（与 `vision.mjs` 的 OCR 同一条纪律）。
 *     JSON 解不出时**不许**把散文当读数收下 —— 那正是 §2.4.1 那个病。
 *   · **一个字节都不留在盘上**：本模块不写文件；调用方在 `finally` 里删临时图（既有那条路径）。
 *
 * ── 红线口径（`AGENTS.md` §2.6 窄豁免，2026-10-15 Owner 当场定的加宽）
 *
 *   图片字节此前**不出机器**（只做本机 OCR）。这一层是**唯一**让图片字节离开本机的地方，
 *   而且形状被钉死：**只送人当前发给守衡的那张图**、只送画面层这一件事、
 *   送的是**同一个端点**（与素材文字同一个服务商，不新增第三方）、不归档、不进知识库。
 *   要再开一处、或换成别的服务商 ⇒ **先改 §2.6 与这里的 `SCENE_ENABLED`**。
 */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { config } from './config.mjs';

/** 总开关。关掉 ⇒ 画面层整块不跑，读数如实记「未开」，**不假装读过**。 */
export const SCENE_ENABLED = process.env.SHOUHENG_SCENE === '0' ? false : true;

/** 单张图的字节上限（base64 后约 ×1.37）。超了**如实报**，不截断、不压缩 —— 压缩是另一个决定。 */
export const SCENE_MAX_BYTES = 8 * 1024 * 1024;

/** 一次调用等的上限。画面层是**加分读数**，不许把回话拖死。 */
export const SCENE_TIMEOUT_MS = Number(process.env.SHOUHENG_SCENE_TIMEOUT_MS || 45_000);

/** 体量档位：小图直接发。 */
const EXT_MIME = { '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
                   '.gif': 'image/gif', '.webp': 'image/webp', '.img': 'image/jpeg',
                   '.heic': 'image/heic' };

/**
 * 提示词：**只许陈述看得见的东西**。
 * ⚠️ 改它等于改读数的口径 —— 同时要改 `scene.test.mjs` 里那几条判据（尤其「不许下结论」那条）。
 */
export const SCENE_SYSTEM = [
  '你是**画面读数器**，不是审查员。你只做一件事：把这张图里**看得见的事实**列成 JSON。',
  '',
  '硬规矩（违反任何一条，这份读数就是废的）：',
  '1. **只写你在这张图里真看到的**。看不清的、被挡住的、不属于这张图的，一律写进 `unclear`。',
  '2. **不许判合规、不许给建议、不许下结论**（不写「违规」「风险」「建议改为」这类判断）。',
  '3. **不许推断看不见的东西**：月龄只能写「婴幼儿/儿童/成人」这一档，不许写「6 个月」；',
  '   不许推断品牌合作、不许推断声音、不许推断这张图之外的情节。',
  '4. `visible_marks` 只写**图上真有的**商标/文字标识（逐字照抄，认不出就写认不出）。',
  '5. 画面里出现婴幼儿、儿童、可识别人物、产品正在被使用（或贴近人体）时，',
  '   **必须**如实写进 `risk_cues` —— 只陈述「我看到了什么」，不要解释它为什么重要。',
  '',
  '只输出一个 JSON 对象，不要任何解释文字。**每个数组最多 4 项，每项不超过 25 个字**（写要点，不写长句）。',
  '字段：',
  '{',
  '  "setting": "厨房 / 浴室 / 卧室 / 客厅 / 户外 / 影棚 / 其他（或：看不清）",',
  '  "people": [{"kind":"婴幼儿|儿童|成人|分不清","doing":"在做什么（看得见的动作）"}],',
  '  "products": [{"what":"看得见的物品（逐字描述外形即可，认不出牌子就只说外形）","in_use":true}],',
  '  "visible_marks": ["图上真有的商标或文字标识（逐字）"],',
  '  "risk_cues": ["看得见、且与内容审查有关的事实（婴幼儿出镜、产品贴近人体、疑似合成痕迹…）"],',
  '  "unclear": ["看不清或这张图里没有的信息"]',
  '}',
].join('\n');

/** 路径守卫：**只认临时目录里的文件**（见头注那条边界）。 */
export function assertTempPath(p) {
  const abs = path.resolve(String(p ?? ''));
  const tmp = path.resolve(os.tmpdir());
  if (!abs.startsWith(tmp + path.sep) && !abs.startsWith('/tmp' + path.sep)) {
    throw new Error(`画面层只读临时目录里的图（拒绝 ${abs}）—— 取字节那一步落在 ${tmp}，见 §2.6 窄豁免`);
  }
  return abs;
}

/**
 * 把模型回来的文本读成**读数**（纯函数 —— 判据只有这一处，喂样本就能证）。
 *
 * ★ 解不出 JSON ⇒ `ok:false`（**不是**「这张图没画面」）。两种结局必须分得开。
 * @returns {{ok:boolean, scene?:object, error?:string}}
 */
export function parseScene(raw) {
  const s = String(raw ?? '').trim();
  if (!s) return { ok: false, error: '画面模型回了空内容' };
  // 允许它包在 ```json 里 —— 只脱一层围栏，不做别的猜测
  const fenced = s.match(/```(?:json)?\s*([\s\S]*?)```/i);
  const body = (fenced ? fenced[1] : s).trim();
  const start = body.indexOf('{');
  const end = body.lastIndexOf('}');
  if (start < 0 || end <= start) return { ok: false, error: `画面读数不是 JSON（前 80 字：${body.slice(0, 80)}）` };
  let o;
  try { o = JSON.parse(body.slice(start, end + 1)); }
  catch (e) { return { ok: false, error: `画面读数 JSON 解不出：${e?.message ?? e}` }; }
  if (!o || typeof o !== 'object' || Array.isArray(o)) return { ok: false, error: '画面读数不是对象' };
  const arr = (v) => (Array.isArray(v) ? v : (v == null ? [] : [v]));
  return {
    ok: true,
    scene: {
      setting: String(o.setting ?? '').trim() || '未给',
      people: arr(o.people).map((p) => (typeof p === 'string' ? { kind: p, doing: '' } : {
        kind: String(p?.kind ?? '').trim() || '分不清',
        doing: String(p?.doing ?? '').trim(),
      })).filter((p) => p.kind !== '分不清' || p.doing),
      products: arr(o.products).map((p) => (typeof p === 'string' ? { what: p, in_use: null } : {
        what: String(p?.what ?? '').trim(),
        in_use: typeof p?.in_use === 'boolean' ? p.in_use : null,
      })).filter((p) => p.what),
      visible_marks: arr(o.visible_marks).map((x) => String(x).trim()).filter(Boolean),
      risk_cues: arr(o.risk_cues).map((x) => String(x).trim()).filter(Boolean),
      unclear: arr(o.unclear).map((x) => String(x).trim()).filter(Boolean),
    },
  };
}

/**
 * 读数 → 摊给**模型侧**看的文本块（**唯一产者**）。
 *
 * ★ 为什么逐项摊开、不压成一句：模型侧要拿它判 PRD 那三类
 *   （产品使用 / 人物行为 / 场景风险），压成一句等于**替它挑掉了它需要的信息**。
 * ★ 空的那几项**明写「（读数里没有）」**：不写，模型会以为"没提就是没有"；
 *   写了它才知道这是读数的边界，而不是事实。
 */
export function sceneBlock(scene) {
  const s = scene ?? {};
  const L = [];
  const line = (k, v, empty) => L.push(`- ${k}：${v && String(v).trim() ? v : (empty ?? '（读数里没有）')}`);
  line('场景', s.setting && s.setting !== '未给' ? s.setting : '');
  line('人物', (s.people ?? []).map((p) => [p.kind, p.doing].filter(Boolean).join(' · ')).join('；'));
  line('物品', (s.products ?? []).map((p) => p.what + (p.in_use === true ? '（正在被使用）' : '')).join('；'));
  line('可见标识', (s.visible_marks ?? []).join('；'));
  line('画面线索', (s.risk_cues ?? []).join('；'));
  line('读数自报看不清的', (s.unclear ?? []).join('；'));
  return L.join('\n');
}

/** 读数 → 一行给人看的短语（日志与报告附录共用；**唯一产者**）。 */export function sceneLine(scene) {
  if (!scene || !scene.ok) return '';
  const s = scene.scene ?? {};
  const parts = [];
  if (s.setting && s.setting !== '未给') parts.push(`场景=${s.setting}`);
  if (s.people?.length) parts.push(`人物=${s.people.map((p) => [p.kind, p.doing].filter(Boolean).join('')).join('、')}`);
  if (s.products?.length) parts.push(`物品=${s.products.map((p) => p.what + (p.in_use ? '（在用）' : '')).join('、')}`);
  if (s.visible_marks?.length) parts.push(`可见标识=${s.visible_marks.join('、')}`);
  if (s.risk_cues?.length) parts.push(`画面线索=${s.risk_cues.join('、')}`);
  return parts.join('｜');
}

/**
 * 跑一次画面层读数。
 *
 * @param {string} imagePath 临时目录里的图（`assertTempPath` 会拒别的路径）
 * @returns {Promise<{ok:boolean, scene?:object, ms:number, error?:string}>}
 *   ⚠️ **永不抛** —— 画面层是加分读数，它失败不该让这次回话失败
 *      （与 `vision.ocrImage` 的调用点同一条纪律：任何一张图读不到都不该让整条回话挂掉）。
 *   ⚠️ `ok:false` 的语义是**「这一张我没读到画面」**，不是「这张图没有画面」。
 */
export async function sceneRead(imagePath, { model = config.llm.model, timeoutMs = SCENE_TIMEOUT_MS,
                                         maxTokens = 1200, fetchImpl = fetch } = {}) {
  const t0 = Date.now();
  // ★ 关掉时是 **`skipped`**（这一单没跑），不是 `ok:false` 的失败 ——
  //   三种结局必须分得开：**没跑**（skipped）／**没读到**（未测）／**读到了**。
  //   第一版这里只回 `ok:false`，于是「功能关着」在报告里被印成「没读到（未测）」，
  //   而两者引出的下一步完全不同（一个是没人开，一个是环境/网络出问题）。
  if (!SCENE_ENABLED) return { ok: false, skipped: true, ms: 0, error: '画面层未开（SHOUHENG_SCENE=0）' };
  let abs;
  try { abs = assertTempPath(imagePath); }
  catch (e) { return { ok: false, ms: Date.now() - t0, error: e.message }; }
  let buf;
  try { buf = fs.readFileSync(abs); }
  catch (e) { return { ok: false, ms: Date.now() - t0, error: `读不到那张临时图：${e?.code ?? e?.message}` }; }
  if (!buf.length) return { ok: false, ms: Date.now() - t0, error: '那张临时图是 0 字节' };
  if (buf.length > SCENE_MAX_BYTES) {
    return { ok: false, ms: Date.now() - t0,
             error: `图太大（${buf.length}B > ${SCENE_MAX_BYTES}B）⇒ 没送模型（不压缩、不截断，压缩是另一个决定）` };
  }
  const mime = EXT_MIME[path.extname(abs).toLowerCase()] ?? 'image/jpeg';
  const body = {
    model, max_tokens: maxTokens, temperature: 0,
    messages: [
      { role: 'system', content: SCENE_SYSTEM },
      { role: 'user', content: [
        { type: 'text', text: '读这一张。只输出 JSON。' },
        { type: 'image_url', image_url: { url: `data:${mime};base64,${buf.toString('base64')}` } },
      ] },
    ],
  };
  const ac = new AbortController();
  const timer = setTimeout(() => ac.abort(), timeoutMs);
  try {
    const r = await fetchImpl(config.llm.baseUrl.replace(/\/$/, '') + '/chat/completions', {
      method: 'POST', signal: ac.signal,
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${config.llm.apiKey}` },
      body: JSON.stringify(body),
    });
    if (!r.ok) {
      const t = await r.text().catch(() => '');
      return { ok: false, ms: Date.now() - t0, error: `画面模型 HTTP ${r.status}：${t.slice(0, 200)}` };
    }
    const j = await r.json();
    const choice = j?.choices?.[0] ?? {};
    const raw = choice?.message?.content ?? '';
    // ★★ 2026-10-15 当场踩到并修掉：**`finish_reason: 'length'` 的 JSON 是被切开的**，
    //   而 `JSON.parse` 只会报一句「position 518 处少了 `,`」—— **指向完全无关的方向**
    //   （我第一版就是先怀疑模型写坏了 JSON，其实是我给 700 tokens 不够）。
    //   判据必须比**内容的完整性**，不能比那句报错：
    //   截断 ⇒ **未测**（`ok:false`），**不许**把半份读数收下，也不许说成「没有画面」。
    if (choice?.finish_reason === 'length') {
      return { ok: false, ms: Date.now() - t0,
               error: `画面读数**被截断**（max_tokens=${maxTokens} 用尽）⇒ 这一张的画面层是**未测**`
                 + '（不是「没有画面」，也不是「读数是空的」）' };
    }
    const p = parseScene(raw);
    return p.ok ? { ok: true, scene: p.scene, ms: Date.now() - t0 }
                : { ok: false, ms: Date.now() - t0, error: p.error };
  } catch (e) {
    const why = e?.name === 'AbortError' ? `超时（${timeoutMs}ms）` : `${e?.cause?.code ?? e?.name ?? 'Error'}: ${e?.message ?? e}`;
    return { ok: false, ms: Date.now() - t0, error: why };
  } finally {
    clearTimeout(timer);
  }
}

/**
 * 启动试纸：**这条路还通不通，第一屏就要看得见**（与 `vision.preflight` 同一形状）。
 *
 * 用本仓资产图（`tools/agent/__fixtures__/ocr-sample.png`，26KB，不是从飞书取来的），
 * 真跑一次；读数里必须**至少有一项看得见的字段** —— 只测「HTTP 200」测不出「它其实什么都没看」。
 */
export async function preflight({ fetchImpl = fetch } = {}) {
  if (!SCENE_ENABLED) return { ok: false, skipped: true, detail: '画面层未开（SHOUHENG_SCENE=0）' };
  const fixture = path.join(import.meta.dirname, '__fixtures__', 'ocr-sample.png');
  if (!fs.existsSync(fixture)) return { ok: false, detail: `试纸不在：${fixture}` };
  // 试纸在仓里、不在临时目录 ⇒ 复制一份到临时目录再跑（守卫不开口子）
  const tmp = path.join(os.tmpdir(), `shouheng-scene-preflight-${process.pid}.png`);
  try {
    fs.copyFileSync(fixture, tmp);
    const r = await sceneRead(tmp, { fetchImpl, timeoutMs: 30_000 });
    if (!r.ok) return { ok: false, detail: r.error };
    const line = sceneLine(r);
    return { ok: !!line, detail: `${line || '（读数全空 —— 它其实什么都没看）'} · ${r.ms}ms`, scene: r.scene };
  } finally {
    try { fs.unlinkSync(tmp); } catch { /* 删不掉不影响读数 */ }
  }
}
