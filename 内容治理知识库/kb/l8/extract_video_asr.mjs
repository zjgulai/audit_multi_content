#!/usr/bin/env node
/**
 * extract_video_asr.mjs —— 给 L1 里已登记的**内嵌视频**补**音轨转写**（口播）。
 *
 * ## 为什么要有它（2026-10-09）
 *
 * 视频这条链现在只做了**一半**：`extract_video_keyframes.py` 抽帧 + Vision OCR 出**画面文字**，
 * 但没有**口播转写**。于是 hostlib 里 11 条 `cg-vid-*` 条目只含画面文字，正文还写着一句
 * 「**本机无 ASR，视频字幕未实现**」—— 而**这句话是过期结论**：
 *
 *   · 守衡侧早有跑通的本机 ASR：`tools/agent/asr.mjs` + `.tools/bin/shouheng-asr`
 *     （macOS Speech.framework，**纯本机、零第三方、不出机器**）；
 *   · 实测（10-09 守衡日志）：同一台机器读 68.9 秒视频 →
 *     `抽帧 OCR 8/8 帧（821 字）｜**音轨转写 158 字**`。
 *
 * ⇒ 同一个视频，**守衡现场读有转写、库里那条条目没有**。本脚本把缺的这半补到 L1。
 *
 * ## 边界（照库内惯例：不许把否定结论说得比输入大）
 *
 * · **只补数据，不渲视图** —— hostlib 条目由 `gen-host-library-video.py` 渲（它读本脚本写的字段）。
 *   这样 publish 的失败面**一个都没多**：本脚本不进 publish，也不进日更。
 * · **本机 ASR 给的是整段文本、没有逐句时间码** ⇒ 转写**不可按时间定位**（画面文字那半有 `#t.`）。
 *   这条必须一路带到条目正文与 `not_proves` 里，否则会被当"能定位到秒"用。
 * · `no_speech` / `no_audio_track` 是**读数**（人没说话 / 本来没音轨），**不是失败**；
 *   失败另记 `kind`，不许把两者混成一句"转写没出来"。
 * · `script_mismatch`（所有语种都转不出该语言的字）**带 `suspect` 标记**保留，
 *   但下游不许当逐字原文引用。
 * · **绝不重编 ASR 二进制**（`ensureAsr()` 只在产物缺失时才编；重编会让 TCC 授权失效）。
 *
 * ## 用法
 *
 *     node kb/l8/extract_video_asr.mjs                # 干跑（默认，什么都不写）
 *     node kb/l8/extract_video_asr.mjs --only <tok> --apply    # 只跑一个视频（试点）
 *     node kb/l8/extract_video_asr.mjs --apply                 # 全部
 *
 * 环境变量 `SHOUHENG_AGENT_DIR` 可覆盖跨仓路径（默认指向 audit_multi_content 的 tools/agent）。
 */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { pathToFileURL, fileURLToPath } from 'node:url';

const execFileP = promisify(execFile);

// ★ 必须用 fileURLToPath：本库路径含中文（执行skills / 知识库），
//   `new URL(...).pathname` 会返回**百分号编码**串，dirname 之后就不是真目录了（实测踩过）。
const KB = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');     // …/内容治理/kb
const L1_DIRS = ['1_外部标准库', '2_内部正负样本库', '3_措辞表达库', '4_产品描述库']
  .map((d) => path.join(KB, 'l1', d));
const AGENT_DIR = process.env.SHOUHENG_AGENT_DIR
  || '/Users/lute/Project/audit_multi_content/tools/agent';
const ASR_MOD = path.join(AGENT_DIR, 'asr.mjs');

const argv = process.argv.slice(2);
const APPLY = argv.includes('--apply');
const ONLY = argv.includes('--only') ? argv[argv.indexOf('--only') + 1] : null;
/** run_id = `<YYYYMMDD-HHMM>`（**本地时间**，与库内其它 RUN 同口径；UTC 会差 8 小时）。 */
function localRunId(d = new Date()) {
  const p = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}-${p(d.getHours())}${p(d.getMinutes())}`;
}
const RUN = (argv.find((a) => !a.startsWith('--') && a !== ONLY)) || localRunId();

/** 把视频的音轨抽成 22.05kHz 单声道 wav（`afconvert` 是系统自带的，不是第三方）。 */
async function extractAudio(videoPath, outWav) {
  try {
    await execFileP('afconvert', ['-f', 'WAVE', '-d', 'LEI16@22050', '-c', '1', videoPath, outWav],
      { timeout: 300_000 });
  } catch (e) {
    return { ok: false, error: 'audio_extract_failed', detail: `${e.message}`.slice(0, 300) };
  }
  let size = 0;
  try { size = fs.statSync(outWav).size; } catch { /* 下面按 0 处理 */ }
  if (!size) return { ok: false, error: 'audio_extract_empty', detail: 'afconvert 退 0，但 wav 是 0 字节' };
  return { ok: true, bytes: size };
}

async function main() {
  if (!fs.existsSync(ASR_MOD)) {
    console.error(`⛔ 找不到 ASR 模块：${ASR_MOD}\n   （可用 SHOUHENG_AGENT_DIR 覆盖跨仓路径）`);
    return 2;
  }
  const { transcribe, orderLocalesByText } = await import(pathToFileURL(ASR_MOD).href);

  // 收集：L1 里带 video_ocr_segments 的产物 → 逐个视频
  const targets = [];
  for (const d of L1_DIRS) {
    if (!fs.existsSync(d)) continue;
    for (const name of fs.readdirSync(d).sort()) {
      if (!name.endsWith('.json')) continue;
      const p = path.join(d, name);
      let rec;
      try { rec = JSON.parse(fs.readFileSync(p, 'utf8')); } catch { continue; }
      if (!rec || !Array.isArray(rec.video_ocr_segments)) continue;
      for (const v of rec.video_ocr_segments) {
        if (ONLY && v.video_token !== ONLY) continue;
        targets.push({ artifactPath: p, rec, v });
      }
    }
  }
  console.log(`[asr] 目标视频 ${targets.length} 个${ONLY ? `（--only ${ONLY}）` : ''}`
    + ` ｜ 模式=${APPLY ? '落盘' : '干跑'}`);
  if (!targets.length) { console.log('[asr] 没有目标 ⇒ 不写'); return 0; }

  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'kb-asr-'));
  const byArtifact = new Map();   // artifactPath → [{v, asr}]
  let okN = 0, readN = 0, failN = 0;

  for (const { artifactPath, v } of targets) {
    const name = v.video_name || v.video_token || 'video';
    const vp = v.video_path ? path.join(KB, '..', v.video_path) : null;
    const absVideo = vp && fs.existsSync(vp) ? vp
      : (v.video_path && fs.existsSync(v.video_path) ? v.video_path : null);
    let asr;
    let localeBasis = null;
    if (!absVideo) {
      asr = { ok: false, kind: 'no_local_bytes',
              detail: '本地没有字节（可能是 981003 取不到的那批）⇒ 转写无从做起，与 ASR 无关' };
      failN++;
    } else {
      const wav = path.join(tmpDir, `${(v.video_token || 'v').slice(0, 16)}.wav`);
      const a = await extractAudio(absVideo, wav);
      if (!a.ok) { asr = a; failN++; }
      else {
        // ★ 语种顺序**必须**按画面 OCR 文本定，不能用默认语序 —— 实测（10-09）：
        //   英文音轨按默认 [zh-CN,en-US] 走，`transcribe()` 第一个语种就 ok（乱码里恰好含 1 个汉字，
        //   `checkScript` 的 `[\u3400-\u9fff]` 只要求"出现"即判自洽）⇒ 回 265 字胡话；
        //   按 `orderLocalesByText` 定成 en-US 后回 **722 字正确英文**。
        //   守衡那条路（`video.mjs:234`）本来就是这么做的，本脚本照抄，不自创。
        const sample = (v.segments || []).map((s) => s.text || '').join('\n');
        const hint = orderLocalesByText(sample);
        localeBasis = hint.basis ?? null;
        const t = await transcribe(wav, { locales: hint.locales });
        if (t.ok === true && t.kind !== 'script_mismatch') {
          asr = { ok: true, kind: 'text', text: t.text, chars: t.chars, locale: t.locale,
                  on_device: t.on_device === true, ms: t.ms ?? null,
                  engine: 'macOS Speech.framework（本机、on-device）' };
          okN++;
        } else if (t.kind === 'no_speech') {
          asr = { ok: false, kind: 'no_speech', read_as: '读数：音轨里没有人说话（不是失败）',
                  locale: t.locale ?? null };
          readN++;
        } else if (t.kind === 'script_mismatch') {
          asr = { ok: true, kind: 'script_mismatch', suspect: true, text: t.text, chars: t.chars,
                  locale: t.locale, hint: t.hint, on_device: t.on_device === true,
                  engine: 'macOS Speech.framework（本机、on-device）' };
          okN++;
        } else {
          asr = { ok: false, kind: t.kind || 'error', detail: t.detail ?? null, locale: t.locale ?? null };
          failN++;
        }
      }
    }
    const chars = asr.chars ?? (asr.text ? asr.text.length : 0);
    console.log(`  · ${String(name).slice(0, 42).padEnd(44)} ${String(asr.kind).padEnd(18)}`
      + ` ${asr.ok ? `${chars} 字` : (asr.detail || asr.read_as || '').slice(0, 60)}`);
    if (!byArtifact.has(artifactPath)) byArtifact.set(artifactPath, []);
    byArtifact.get(artifactPath).push({
      artifactPath, video_token: v.video_token, video_name: v.video_name,
      video_path: v.video_path, duration: v.duration, engine: asr.engine ?? null,
      locale: asr.locale ?? null, locale_basis: localeBasis, on_device: asr.on_device ?? null,
      kind: asr.kind, suspect: asr.suspect ?? false, read_as: asr.read_as ?? null,
      chars, text: asr.text ?? null, detail: asr.detail ?? null,
      extracted_at: RUN,
    });
  }

  console.log(`\n[asr] 结果：有文本 ${okN} ｜ 读数(无人声) ${readN} ｜ 未成 ${failN}`);
  console.log(`[asr] 转写**没有逐句时间码**（本机 ASR 只给整段文本）—— 下游不许当"可定位到秒"用`);

  if (!APPLY) {
    console.log('[asr] 【干跑】未写盘。加 --apply 才把 video_asr_segments 写进 L1 产物。');
    return 0;
  }

  // 落盘：写进对应 L1 产物（与 video_ocr_segments 并列）
  for (const [artifactPath, rows] of byArtifact) {
    const rec = JSON.parse(fs.readFileSync(artifactPath, 'utf8'));
    // ── ★ 2026-10-09：**合并，不整数组替换**（我自己踩的坑，写在这里）──────────────
    // 病灶：第一版直接 `rec.video_asr_segments = rows` ⇒ 用 `--only <一个 token>` 试点时，
    // 该产物里**别的视频的转写被整批抹掉**（实测：`wiki__NPKldCDg…` 3 个视频的转写
    // 变成 1 个，全库「有口播转写」从 13 掉到 11）。这与本批修掉的 `emit` 降级同一个病：
    // **用局部结果覆盖全量状态**。⇒ 按 token 合并；本次没跑到的 token 保留原行。
    const prev = Array.isArray(rec.video_asr_segments) ? rec.video_asr_segments : [];
    const byTok = new Map(prev.map((r) => [r.video_token, r]));
    const _before = byTok.size;
    for (const r of rows) byTok.set(r.video_token, r);
    rec.video_asr_segments = [...byTok.values()];
    if (_before && byTok.size !== _before) {
      console.log(`[asr] 合并：原有 ${_before} 个 → 现 ${byTok.size} 个（本次只跑 ${rows.length} 个，其余保留）`);
    }
    rec.video_asr_segment_count = rows.length;
    rec.video_asr_char_count = rows.reduce((n, r) => n + (r.chars || 0), 0);
    rec.video_asr_extracted_at = RUN;
    const tmp = artifactPath + `.tmp-${process.pid}`;
    fs.writeFileSync(tmp, JSON.stringify(rec, null, 1));   // node 写 = 明文
    fs.renameSync(tmp, artifactPath);
    console.log(`[asr] 已写 ${path.relative(KB, artifactPath)}：`
      + `${rows.length} 个视频 / ${rec.video_asr_char_count} 字`);
  }
  fs.rmSync(tmpDir, { recursive: true, force: true });

  // ── ★ 2026-10-09 接线：写完 L1 就**让派生视图重建**（否则守衡看不到新数据）────────
  // `publish.sh` 的 INPUTS 里**含 L1 的 0 条**，而视频/图片生成器读的**正是 L1** ⇒
  // 跑完 ASR 后 publish 会说「输入未变，跳过重出」，**守衡看不到新条目的口播转写**。
  // 今天实测就撞上，不得不人工 `rm .publish.stamp`。这里在**生产者收尾**失效它
  // （stamp 内容 ≠ 当前输入指纹 ⇒ 下次 publish 必重跑生成器）。
  const stamp = path.join(KB, '.work', '.publish.stamp');
  try {
    if (fs.existsSync(stamp)) { fs.rmSync(stamp); console.log('[接线] 已使 .publish.stamp 失效 ⇒ 下次 publish 会重出派生视图（守衡才看得到）'); }
    else console.log('[接线] .publish.stamp 本就不在 ⇒ 下次 publish 会重出派生视图');
  } catch (e) {
    console.log(`[接线] ⚠️ 失效 stamp 失败（${e?.message ?? e}）—— 请手动跑 kb/.work/publish.sh`);
  }
  return 0;
}

main().then((c) => process.exit(c)).catch((e) => { console.error('⛔', e); process.exit(1); });
