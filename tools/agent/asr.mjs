/**
 * asr.mjs —— 本机语音转写（macOS Speech.framework），**零第三方依赖、不出机器**
 *
 * ── 它是什么
 *
 * 调本仓自己的 ASR CLI：源码 `base/asr_speech.m`，编译脚本 `base/build_asr.sh`，
 * 产物 `.tools/bin/shouheng-asr` + `.tools/bin/ShouhengASR.app`。
 * 与 `vision.mjs`（Vision OCR）、`video.mjs`（AVFoundation 抽帧）是同一条路子：
 * **只用系统框架，不装 ffmpeg、不装 whisper、不连任何云服务**。
 *
 * 这一条不是洁癖，是 PRD §12「素材不对外泄露」逼出来的：语音转写要是走云端 API，
 * 视频里的口播就出了这台机器。所以 `requiresOnDeviceRecognition = YES` 写死在
 * `base/asr_speech.m` 里，**没有开关**。
 *
 * ── 三条只看代码看不出来的坑（都在 `base/asr_speech.m` 顶上留了读数）
 *
 *   ① 语音识别是 **TCC 隐私服务**：裸 CLI 一调就 `Abort trap: 6`，必须打成 .app
 *      并且**用 `open -n` 启动** —— 所以这个模块**没有 stdout 可读**，
 *      结果是靠 `open -n app --args <音频> <locale> <结果文件>` + **轮询那个文件**拿的。
 *   ② `LSBackgroundOnly` 的 app 弹不出授权框，`requestAuthorization` 的回调永远不来，
 *      进程会一直挂着 —— 表现出来像「识别太慢」，真因是「框没弹出来」。
 *   ③ TCC 对临时签名按 cdhash 记授权：**重编一次二进制，授权就对不上**。
 *      所以 `ensureAsr()` **只在产物缺失时才编译** —— 不要因为「源码改过了」就顺手重编，
 *      那会让人在群里发视频时收到一句「语音识别没授权」。真要重编，得先跟人说一声。
 *
 * ── 三种「没结果」必须长得不一样（AGENTS.md §2.4.1：否定结论不许比输入大）
 *
 *   · `kind:'no_speech'` —— 音频里**没有人说话**（实测一个产品 hero 视频就是这样，
 *     音乐声很大、RMS 2193，但识别器回 `No speech detected(1110)`）。
 *     这是**读数**，不是失败：拿同一段音频拼上已知语音再识别就出字了（做过这个对照）。
 *   · `kind:'not_authorized'` —— 授权没给。**下一步是找人点一下**，不是重试。
 *   · `kind:'timeout'` / `kind:'hung'` —— 没等到结果。挂了多半就是 ②（框弹不出来）。
 */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { REPO_ROOT, AGENT_DIR } from './config.mjs';

const execFileP = promisify(execFile);

const BIN_DIR   = path.join(REPO_ROOT, '.tools', 'bin');
const ASR_BIN   = path.join(BIN_DIR, 'shouheng-asr');
const ASR_APP   = path.join(BIN_DIR, 'ShouhengASR.app');
const ASR_BUILD = path.join(REPO_ROOT, 'base', 'build_asr.sh');

/** 试纸：一句本机合成的普通话，转写回来必须含这个特征串（见 `preflight()`）。 */
export const ASR_FIXTURE = path.join(AGENT_DIR, '__fixtures__', 'asr-sample.wav');
export const ASR_FIXTURE_TOKEN = '守恒语音自检';

/** 默认语种。先判中文再判英文 —— 本项目的素材中英混排，两句都试一遍比只试一句强。 */
export const ASR_LOCALES = ['zh-CN', 'en-US'];
/** 单次转写的墙钟上限（毫秒）。识别本机跑，比实时快，但 `open` 启动本身要几百毫秒。 */
const ASR_TIMEOUT_MS = 90_000;
/** 结果文件轮询间隔 */
const POLL_MS = 120;
/** 音频文件上限：飞书侧视频最大 100MB，这里再收一道，防一次转写把内存打满。 */
const MAX_AUDIO_BYTES = 200 * 1024 * 1024;

let _buildAttempted = false;

export function asrBinAvailable() { return fs.existsSync(ASR_BIN) && fs.existsSync(ASR_APP); }
export function asrAppPath() { return ASR_APP; }

/**
 * 确保 ASR 产物存在；**只在缺失时**编译一次。
 *
 * ★ 为什么是「只在缺失时」而不是「源码新就重编」：重编会换掉二进制的签名，
 *   TCC 那条授权随之失效（见文件头 ③），下一次识别会**挂在那儿等人点弹窗**。
 *   把重编这件事留给「人知情时显式做」，不要藏在启动路径里。
 */
export async function ensureAsr() {
  if (asrBinAvailable()) return { ok: true, path: ASR_BIN, app: ASR_APP };
  if (!fs.existsSync(ASR_BUILD)) {
    return { ok: false, error: 'asr_build_script_missing', detail: `找不到 ${ASR_BUILD}` };
  }
  if (_buildAttempted) {
    return { ok: false, error: 'asr_unavailable', detail: '本次进程里编译已失败过一次，不再重试' };
  }
  _buildAttempted = true;
  try {
    fs.mkdirSync(BIN_DIR, { recursive: true });
    const r = await execFileP('bash', [ASR_BUILD], { cwd: REPO_ROOT, timeout: 180_000 });
    if (!asrBinAvailable()) {
      return { ok: false, error: 'asr_unavailable',
               detail: `编译脚本退出 ${r.code ?? 0} 但产物没出现：${String(r.stdout ?? '').slice(-300)}` };
    }
    console.warn('[asr] · ASR 产物不在，现场编译成功 —— '
      + '★ 新编的二进制要**再点一次**系统授权框，否则识别会挂住（见 base/asr_speech.m ③）');
    return { ok: true, path: ASR_BIN, app: ASR_APP, built: true };
  } catch (e) {
    return { ok: false, error: 'asr_unavailable',
             detail: `${e.message}｜${String(e.stdout ?? '').slice(-300)}${String(e.stderr ?? '').slice(-300)}` };
  }
}

/** 把 CLI 的错误串归一成调用方契约。**这一步是「三种没结果分开说」的落点。** */
function classifyError(raw) {
  const s = String(raw ?? '');
  if (/not_authorized/i.test(s)) {
    return { kind: 'not_authorized',
             hint: '语音识别授权没给。去「系统设置 → 隐私与安全性 → 语音识别」把 ShouhengASR 打开；'
                 + '若是刚重编过二进制，那条授权会失效（TCC 按 cdhash 记），需要再点一次。' };
  }
  if (/No speech detected/i.test(s)) {
    return { kind: 'no_speech', hint: '这段音频里没有人说话 —— 是读数，不是读不到。' };
  }
  if (/recognizer_unavailable/i.test(s)) {
    return { kind: 'recognizer_unavailable',
             hint: '这个语种的本机识别模型没装（SFSpeechRecognizer.supportsOnDeviceRecognition 或 isAvailable 为假）。'
                 + '按 PRD §12 不许改用云端识别。' };
  }
  if (/timeout/i.test(s)) return { kind: 'timeout', hint: '识别器没在时限内回结果。' };
  if (/not_found/i.test(s)) return { kind: 'not_found' };
  return { kind: 'error' };
}

/** 一轮 `open -n … --args …` + 轮询结果文件。 */
async function runOnce(file, locale, { timeoutMs }) {
  const outPath = path.join(os.tmpdir(),
    `shouheng-asr-${process.pid}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}.json`);
  const t0 = Date.now();
  try {
    // ★ 必须先删干净：结果文件是「存在即完成」的判据，残留会让下一次拿到上一轮的结果。
    try { fs.unlinkSync(outPath); } catch { /* 本来就没有 */ }
    await execFileP('open', ['-n', ASR_APP, '--args', file, locale, outPath], { timeout: 15_000 });
    for (;;) {
      if (fs.existsSync(outPath)) {
        const raw = fs.readFileSync(outPath, 'utf8');
        try { fs.unlinkSync(outPath); } catch { /* 删不掉不影响结果 */ }
        let d;
        try { d = JSON.parse(raw.trim()); }
        catch { return { ok: false, kind: 'bad_output', detail: raw.slice(0, 200), locale, wallMs: Date.now() - t0 }; }
        return { ...d, locale: d.locale ?? locale, wallMs: Date.now() - t0 };
      }
      if (Date.now() - t0 > timeoutMs) {
        // 超时也留痕：把还在挂着的那个进程找出来没有意义，读数本身就够了。
        return { ok: false, kind: 'hang', error: 'no_result_file',
                 detail: `等 ${timeoutMs}ms 没等到结果文件 —— 最常见的成因是授权框没被点（见 base/asr_speech.m ②）`,
                 locale, wallMs: Date.now() - t0 };
      }
      await new Promise((r) => setTimeout(r, POLL_MS));
    }
  } catch (e) {
    return { ok: false, kind: 'spawn_failed', error: String(e?.message ?? e), locale, wallMs: Date.now() - t0 };
  }
}

/**
 * 把一段**本机音频或视频文件**转成文字。
 *
 * @param {string} filePath
 * @param {{locales?:string[], timeoutMs?:number}} [opt]
 * @returns {Promise<{ok:boolean, text?:string, chars?:number, locale?:string, ms?:number,
 *                    callbacks?:number, kind?:string, hint?:string, detail?:string, tried?:string[]}>}
 */
export async function transcribe(filePath, { locales = ASR_LOCALES, timeoutMs = ASR_TIMEOUT_MS } = {}) {
  if (!filePath || !fs.existsSync(filePath)) {
    return { ok: false, kind: 'not_found', detail: `文件不存在：${filePath ?? '(空路径)'}` };
  }
  let size = 0;
  try { size = fs.statSync(filePath).size; } catch { /* 下面按 0 处理 */ }
  if (!size) return { ok: false, kind: 'empty_file', detail: '音频字节是 0 —— 抽出来的就是个空文件' };
  if (size > MAX_AUDIO_BYTES) {
    return { ok: false, kind: 'too_large', detail: `${size} 字节 > 上限 ${MAX_AUDIO_BYTES}` };
  }

  const app = await ensureAsr();
  if (!app.ok) return { ok: false, kind: app.error, detail: app.detail };

  const tried = [];
  let firstFail = null;
  for (const loc of locales) {
    const r = await runOnce(filePath, loc, { timeoutMs });
    tried.push(loc);
    if (r.ok === true) {
      const text = String(r.text ?? '').trim();
      return {
        ok: true, text, chars: text.length, locale: r.locale, ms: r.ms, wallMs: r.wallMs,
        callbacks: r.callbacks ?? null, on_device: r.on_device === true, tried,
      };
    }
    const c = classifyError(r.error ?? r.kind);
    const fail = { ok: false, ...c, error: r.error ?? null, detail: r.detail ?? null,
                   locale: r.locale, ms: r.ms ?? null, wallMs: r.wallMs, tried: [...tried] };
    // `no_speech` 是**读数**：换个语种再试一次没意义（人没说话这件事与语种无关）。
    if (c.kind === 'no_speech') return fail;
    // 授权/模型缺失：换语种也救不回来，但**要说清是哪一个语种**缺。
    if (c.kind === 'not_authorized' || c.kind === 'hang' || c.kind === 'timeout') { if (!firstFail) firstFail = fail; }
    if (!firstFail) firstFail = fail;
  }
  return firstFail ?? { ok: false, kind: 'error', tried };
}

/* ─────────────────── 自检 / 预热（启动时跑一次） ─────────────────── */

/**
 * ASR 这条路的自检：产物在不在（不在就编）→ 拿试纸真跑一次 → 读出特征串才算通。
 *
 * ★ 与 `vision.preflight()` 同一个理由：这条路**坏了不会自己红** ——
 *   群里发视频，守衡只会回一句「听不清」，没人知道是模型没装、授权没给、还是真没说话。
 *   启动横幅里有一行读数，第一屏就能看见。
 *
 * @returns {Promise<{ok:boolean, built?:boolean, ms?:number, locale?:string,
 *                    authorized?:boolean, error?:string, detail?:string, hint?:string}>}
 *   `authorized` 单独报：**授权没给**与**识别不准**是两件事，前者要人点一下。
 */
export async function preflight() {
  const app = await ensureAsr();
  if (!app.ok) return { ok: false, error: app.error, detail: app.detail };
  if (!fs.existsSync(ASR_FIXTURE)) {
    return { ok: false, built: !!app.built, error: 'fixture_missing',
             detail: `试纸不在：${ASR_FIXTURE} —— 没有试纸就无法证明这条路是通的` };
  }
  const r = await transcribe(ASR_FIXTURE, { locales: ['zh-CN'] });
  if (!r.ok) {
    return { ok: false, built: !!app.built, authorized: r.kind !== 'not_authorized',
             error: r.kind ?? 'unknown', hint: r.hint ?? null, detail: r.detail ?? null };
  }
  if (!r.text) {
    // ★ 「通了但一个字都没有」是最容易糊过去的一种：它不是没授权，也不是没说话。
    return { ok: false, built: !!app.built, authorized: true, error: 'empty_transcript',
             detail: `试纸转写回来了，但一个字都没有（chars=0，locale=${r.locale}）—— 别当成「通了」` };
  }
  const hit = r.text.includes(ASR_FIXTURE_TOKEN);
  if (!hit) {
    return { ok: false, built: !!app.built, authorized: true, error: 'fixture_token_missing', ms: r.ms,
             detail: `试纸转写回了 ${r.chars} 字，但没读到特征串「${ASR_FIXTURE_TOKEN}」`
                   + ' —— 多半是识别档位/语言包变了，别当成「通了」',
             text: r.text.slice(0, 200) };
  }
  return { ok: true, built: !!app.built, ms: r.ms, locale: r.locale, authorized: true, text: r.text };
}
