/**
 * vision.mjs —— 本机图像文字识别（macOS Vision），**零第三方依赖**
 *
 * ── 它是什么
 *
 * 调本仓自己的 OCR CLI：源码 `base/ocr_vision.m`，编译脚本 `base/build_ocr.sh`，
 * 二进制落 `.tools/bin/ocr`。用具名理由：**不引任何 pip/npm 包**，不连任何云服务 ——
 * 图片字节不出这台机器。这也正是它能被放进 §2.6 那条窄豁免里的原因（见下）。
 *
 * ── 为什么是它，不是「让模型看图」
 *
 * 守衡的模型是 `deepseek-flash`，**不吃图**（`llm.mjs` 永远是纯文本 content）。
 * 所以「读图」在本项目里的准确含义是：**OCR 出图内文字**，把文字喂给模型与判定引擎。
 * 「画面本身」（构图、场景、人物在做什么、婴幼儿姿势、产品用法）**不在读数里** ——
 * 这一条必须往上传（`agent.mjs` 的图块头注 + `persona.mjs` 的能力边界），
 * 不许让模型把「我看到了图上的字」说成「我看过这张图」。
 *
 * ── 边界（每一个都在下面有执行点）
 *
 *   · 只认**本机文件**；本模块不下载、不联网（取字节那一步在 `feishu.mjs`，
 *     且是全仓唯一的调用点）。
 *   · 二进制不存在 → 现场编译一次（`base/build_ocr.sh`），失败就如实报 `ocr_unavailable`，
 *     **不静默降级成「图上没字」**（把取不到说成没有，是 §2.4.1 那个病）。
 *   · OCR 认不出来（`ok:false`）与 OCR 认出来是空的（`ok:true, n:0`）**必须分得开** ——
 *     前者是「这一张我读不到」，后者是「这张图里没有可读的文字」。
 *     实测两者都真实存在：`perform_failed` 里有一类是 1×1 像素的懒加载占位图
 *     （`base/media.py` 记的 2/120），那不是「读不出来」，是「本来就没有东西可读」。
 */
import fs from 'node:fs';
import path from 'node:path';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { REPO_ROOT, AGENT_DIR } from './config.mjs';

const execFileP = promisify(execFile);

const OCR_BIN_DIR = path.join(REPO_ROOT, '.tools', 'bin');
const OCR_BIN     = path.join(OCR_BIN_DIR, 'ocr');
const OCR_BUILD   = path.join(REPO_ROOT, 'base', 'build_ocr.sh');

/* ─────────────── 试纸（fixture）：让「这条路还通不通」有一个能重复的读数 ───────────────
 *
 * ★ 2026-10-05 加。起因是这次事故的形状：**守衡读不到图，而没有任何东西会变红** ——
 *   图片这条路原先既没有试纸、也没有启动自检，坏了只能等人在群里发现。
 *   两张图都是本仓资产（各 26KB / 1.7KB，不是从飞书取来的）：
 *     · `ocr-sample.png` —— 图上有 7 行已知文字（中英混排），**必须读得出来**；
 *     · `ocr-blank.png`  —— 200×200 全白，**必须报「图上没字」而不是「读不出来」**。
 *   后者是反向对照：只测得出「能读到字」的试纸，测不出「把失败伪装成没字」。
 */
const FIXTURE_DIR = path.join(AGENT_DIR, '__fixtures__');
export const OCR_FIXTURE = path.join(FIXTURE_DIR, 'ocr-sample.png');
export const OCR_BLANK_FIXTURE = path.join(FIXTURE_DIR, 'ocr-blank.png');
/** 试纸里必须被读到的那串特征（挑一个 OCR 稳定认得出的） */
export const OCR_FIXTURE_TOKEN = 'SHOUHENG OCR FIXTURE';

/**
 * 要认的语种。**多语种是必须的，不是锦上添花**：本项目的素材是跨境电商内容，
 * 实测那批落地页里图内文字大量是 es/de/fr，只给 zh/en 会得到一段「读不出东西」的
 * OCR 结果，而它看起来跟「图上真没字」一模一样（`base/media.py` 的 B1 结论）。
 * Vision 支持这几种；真遇到不支持的语言，本模块会退回 zh/en 再来一次。
 */
export const OCR_LANGS = ['zh-Hans', 'en-US', 'de-DE', 'fr-FR', 'es-ES'];
const FALLBACK_LANGS = ['zh-Hans', 'en-US'];

/** 单张图的 OCR 文字上限（字）。超了截断并明写 —— 不许静默截。 */
export const OCR_MAX_CHARS = 4000;
const OCR_TIMEOUT_MS = 60_000;
/** 单张图的字节上限。飞书侧本身上限 100MB，这里再收一道，防一次 OCR 把内存打满。 */
const MAX_IMAGE_BYTES = 20 * 1024 * 1024;

let _buildAttempted = false;

/** 二进制在不在。测试与自证要用，所以导出。 */
export function ocrBinPath() { return OCR_BIN; }
export function ocrBinAvailable() { return fs.existsSync(OCR_BIN); }

/**
 * 确保 OCR 二进制存在；不在就编译一次。
 * @returns {Promise<{ok:boolean, path?:string, error?:string, detail?:string}>}
 */
export async function ensureOcr() {
  if (fs.existsSync(OCR_BIN)) return { ok: true, path: OCR_BIN };
  if (!fs.existsSync(OCR_BUILD)) {
    return { ok: false, error: 'ocr_build_script_missing', detail: `找不到 ${OCR_BUILD}` };
  }
  if (_buildAttempted) {
    // 同一次进程里只试一次：编译失败是环境问题，每张图重试一遍只会拖长回复时间。
    return { ok: false, error: 'ocr_unavailable', detail: '本次进程里编译已失败过一次，不再重试' };
  }
  _buildAttempted = true;
  try {
    fs.mkdirSync(OCR_BIN_DIR, { recursive: true });
    const r = await execFileP('bash', [OCR_BUILD], { cwd: REPO_ROOT, timeout: 180_000 });
    if (!fs.existsSync(OCR_BIN)) {
      return { ok: false, error: 'ocr_unavailable',
               detail: `编译脚本退出 ${r.code ?? 0} 但二进制没出现：${String(r.stdout ?? '').slice(-300)}` };
    }
    console.warn(`[vision] · OCR 二进制不在，现场编译成功：${String(r.stdout ?? '').trim().split('\n').pop()}`);
    return { ok: true, path: OCR_BIN, built: true };
  } catch (e) {
    return { ok: false, error: 'ocr_unavailable',
             detail: `${e.message}｜${String(e.stdout ?? '').slice(-300)}${String(e.stderr ?? '').slice(-300)}` };
  }
}

/** 把 CLI 的一行 JSON 归一成调用方契约（**解析失败不抛**，回 ok:false + 成因）。 */
function normalize(raw, { langs, wallMs }) {
  let d;
  try { d = JSON.parse(String(raw ?? '').trim()); }
  catch { return { ok: false, error: 'bad_output', detail: String(raw ?? '').slice(0, 200), langs, wallMs }; }

  if (!d?.ok) {
    return {
      ok: false,
      error: d?.error ?? 'unknown',
      w: d?.w ?? null, h: d?.h ?? null,
      // ★ 1×1（或几像素）在实测里是**占位图**，不是「识别失败」。
      //   带上这个标记，调用方才能分开说，而不是笼统写「OCR 失败」。
      placeholder: Number.isFinite(d?.w) && Number.isFinite(d?.h) && d.w <= 2 && d.h <= 2,
      ms: d?.ms ?? null, langs, wallMs,
    };
  }

  const lines = (d.lines ?? []).map((l) => String(l?.t ?? '')).filter((s) => s.trim() !== '');
  let text = lines.join('\n');
  const trunc = text.length > OCR_MAX_CHARS;
  if (trunc) text = `${text.slice(0, OCR_MAX_CHARS)}\n…〔本张图 OCR 文字原长 ${text.length} 字，按 ${OCR_MAX_CHARS} 字上限截断〕`;

  return {
    ok: true,
    text,
    lines: lines.length,          // 识别出多少行
    chars: text.length,
    w: d.w ?? null, h: d.h ?? null,
    ms: d.ms ?? null,
    langs,
    wallMs,
    truncated: trunc,
  };
}

/**
 * 识别一张**本机图片文件**。
 *
 * @param {string} filePath 图片路径（本机，任意常见格式 —— Vision 按内容认格式）
 * @param {{langs?:string[], timeoutMs?:number}} [opt]
 * @returns {Promise<{ok:boolean, text?:string, lines?:number, chars?:number, w?:number, h?:number,
 *                    ms?:number, langs?:string[], truncated?:boolean,
 *                    error?:string, detail?:string, placeholder?:boolean}>}
 */
export async function ocrImage(filePath, { langs = OCR_LANGS, timeoutMs = OCR_TIMEOUT_MS } = {}) {
  if (!filePath || !fs.existsSync(filePath)) {
    return { ok: false, error: 'not_found', detail: `图片文件不存在：${filePath ?? '(空路径)'}` };
  }
  let size = 0;
  try { size = fs.statSync(filePath).size; } catch { /* 下面按 0 处理 */ }
  if (!size) return { ok: false, error: 'empty_file', detail: '图片字节是 0 —— 取回来的就是个空文件' };
  if (size > MAX_IMAGE_BYTES) {
    return { ok: false, error: 'too_large', detail: `${size} 字节 > 上限 ${MAX_IMAGE_BYTES}` };
  }

  const bin = await ensureOcr();
  if (!bin.ok) return { ok: false, error: bin.error, detail: bin.detail };

  const attempt = async (useLangs) => {
    const t0 = Date.now();
    try {
      const r = await execFileP(bin.path, [filePath, ...useLangs], { timeout: timeoutMs, maxBuffer: 1 << 24 });
      return normalize(r.stdout, { langs: useLangs, wallMs: Date.now() - t0 });
    } catch (e) {
      if (e.killed || e.signal) return { ok: false, error: 'timeout', detail: `超过 ${timeoutMs}ms`, langs: useLangs };
      return { ok: false, error: 'spawn_failed', detail: String(e.message ?? e), langs: useLangs };
    }
  };

  const first = await attempt(langs);
  // 失败且用的不是兜底语言表 → 用最保守的 zh/en 再来一次。
  // 依据：`recognitionLanguages` 里出现运行时不支持的语种时整次请求会失败，
  // 而那时**整张图一个字都读不到**，看起来跟「图上没字」一样（这是个会骗人的静默降级）。
  if (!first.ok && first.error !== 'not_found' && first.error !== 'too_large'
      && langs.join(',') !== FALLBACK_LANGS.join(',')) {
    const second = await attempt(FALLBACK_LANGS);
    return second.ok ? { ...second, note: `多语种那次失败（${first.error}），已按 ${FALLBACK_LANGS.join('+')} 重试成功` } : second;
  }
  return first;
}

/* ─────────────────── 自检 / 预热（启动时跑一次） ─────────────────── */

/**
 * OCR 这条路的**自检**：二进制在不在（不在就编）→ 拿试纸真跑一次 → 读出特征串才算通。
 *
 * ★ 为什么要它（而不是等第一张图来了再说）：
 *   · **慢**：二进制不在时现场编译要几十秒，而这个时间会花在**某个人正在等的那条回复**上；
 *   · **静默**：编译失败（SDK 变了、CLT 升级）只会让**那一张图**报「读不到」，
 *     而没有任何东西会红 —— 与 10-05 这次事故是同一个形状，只是低了一层。
 *
 * 返回的读数会被 `ws_daemon.mjs` 打进启动横幅，所以「守衡现在读不读得了图」
 * 在日志第一屏就能看见，不用等有人发图。
 *
 * @returns {Promise<{ok:boolean, bin:boolean, built?:boolean, lines?:number, ms?:number,
 *                    blankOk?:boolean, error?:string, detail?:string}>}
 *   `blankOk` 是**反向对照**：空白试纸必须报「没字」（`ok:true, n:0`），
 *   而不是报失败 —— 否则「读不出来的」会被伪装成「图上没字」。
 */
export async function preflight() {
  const bin = await ensureOcr();
  if (!bin.ok) return { ok: false, bin: false, error: bin.error, detail: bin.detail };

  if (!fs.existsSync(OCR_FIXTURE)) {
    return { ok: false, bin: true, built: !!bin.built, error: 'fixture_missing',
             detail: `试纸不在：${OCR_FIXTURE} —— 没有试纸就无法证明这条路是通的` };
  }

  const r = await ocrImage(OCR_FIXTURE);
  if (!r.ok) {
    return { ok: false, bin: true, built: !!bin.built, error: r.error, detail: r.detail,
             note: '二进制在，但试纸读不出来 —— 图这条路现在是断的' };
  }
  const hit = String(r.text ?? '').toUpperCase().includes(OCR_FIXTURE_TOKEN);
  if (!hit) {
    return { ok: false, bin: true, built: !!bin.built, lines: r.lines, ms: r.ms,
             error: 'fixture_token_missing',
             detail: `试纸读了 ${r.lines} 行，但没读到特征串「${OCR_FIXTURE_TOKEN}」—— `
                   + '多半是语言包/识别档位变了，别当成「通了」',
             text: String(r.text ?? '').slice(0, 200) };
  }

  // 反向对照：空白图必须落进「没字」，不是「失败」
  let blankOk = false;
  let blankNote = null;
  if (fs.existsSync(OCR_BLANK_FIXTURE)) {
    const b = await ocrImage(OCR_BLANK_FIXTURE);
    blankOk = b.ok === true && !String(b.text ?? '').trim();
    if (!blankOk) blankNote = `空白试纸回了 ok=${b.ok} error=${b.error ?? '-'} —— 空白图必须报「没字」`;
  }

  return { ok: true, bin: true, built: !!bin.built, lines: r.lines, ms: r.ms,
           blankOk, ...(blankNote ? { blankNote } : {}) };
}
