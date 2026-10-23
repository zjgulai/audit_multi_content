#!/usr/bin/env node
/**
 * kb/.work/scene_batch.mjs —— 给负面样本图库批量做「画面读数」（每图一次多模态）。
 *
 * 为什么复用守衡的 `scene.mjs` 而不是另写提示词
 * ─────────────────────────────────────────────
 * 守衡收图时用的就是它（`agent/scene.mjs`）：同一段 system prompt、同一个端点
 * （`config.llm.baseUrl` + `deepseek-flash`）、同一套输出字段
 * （setting / people / products / visible_marks / text_script / risk_cues / unclear）。
 * 知识库这一侧要跟它**对得上词**，否则"发了图却命不中"就是必然。
 *
 * ★ 治理口径（AGENTS.md §2.6 窄豁免）：`scene.mjs` 只读 `os.tmpdir()` 里的图，
 *   本脚本因此**逐张复制到临时目录 → 调用 → 立刻删除**；不归档副本、不落原图。
 *   每行读数只记 `file_token / sha256 / 读数`，图本身不留在临时目录。
 *
 * 用法：
 *   node kb/.work/scene_batch.mjs --input /tmp/scene_input.json --out kb/l1/media/scene_<RUN>.jsonl [--limit 5] [--conc 4]
 * 断点续跑：输出里已有的 file_token 自动跳过（按行读）。
 */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import crypto from 'node:crypto';

const REPO = '/Users/lute/Project/audit_multi_content/tools/agent';
const { sceneRead } = await import(path.join(REPO, 'scene.mjs'));

const args = process.argv.slice(2);
const argOf = (k, d) => { const i = args.indexOf(k); return i >= 0 ? args[i + 1] : d; };
const INPUT = argOf('--input', '/tmp/scene_input.json');
const OUT = argOf('--out');
const LIMIT = Number(argOf('--limit', '0')) || 0;
const CONC = Number(argOf('--conc', '4')) || 4;
if (!OUT) { console.error('缺 --out'); process.exit(2); }

const items = JSON.parse(fs.readFileSync(INPUT, 'utf8'));

// 断点续跑：已有结果按 file_token 去重
const done = new Set();
if (fs.existsSync(OUT)) {
  for (const line of fs.readFileSync(OUT, 'utf8').split('\n')) {
    if (!line.trim()) continue;
    try { const o = JSON.parse(line); if (o.ok) done.add(o.file_token); } catch { /* 半行忽略 */ }
  }
}
let todo = items.filter((x) => !done.has(x.file_token));
if (LIMIT) todo = todo.slice(0, LIMIT);
console.log(`[scene] 输入 ${items.length} 张 ｜ 已完成 ${done.size} ｜ 本轮待跑 ${todo.length} ｜ 并发 ${CONC}`);

const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'kb-scene-'));
const outFd = fs.openSync(OUT, 'a');
let ok = 0, fail = 0, i = 0;

async function one(x) {
  const ext = path.extname(x.path) || '.png';
  let tmp = path.join(tmpDir, `${x.record_id}-${x.seq}${ext}`);
  let preShrunk = false;
  try {
    // ★ 大图先缩：scene.mjs 在**缩之前**就按 8MB 上限拒收（它自己那句「压缩是另一个决定」），
    //   而本库的负面样本图有 15–26MB 的 PNG ⇒ 不预缩就有 6 张读数**永远为 0**。
    //   缩法跟 scene.mjs 一样用 macOS 自带 sips（不引第三方、不联网），边长 1024。
    const st = fs.statSync(x.path);
    if (st.size > 8 * 1024 * 1024) {
      const small = path.join(tmpDir, `${x.record_id}-${x.seq}.jpg`);
      const { execFileSync } = await import('node:child_process');
      execFileSync('sips', ['-Z', '1024', '-s', 'format', 'jpeg', x.path, '--out', small], { stdio: 'ignore' });
      tmp = small; preShrunk = true;
    } else {
      fs.copyFileSync(x.path, tmp);
    }
    const r = await sceneRead(tmp);
    const row = {
      file_token: x.file_token, record_id: x.record_id, seq: x.seq,
      sha256: x.sha256, ok: !!r.ok, ms: r.ms ?? null, pre_shrunk: preShrunk,
      scene: r.ok ? r.scene : null, error: r.ok ? null : (r.error || '未知'),
      model: 'deepseek-flash/scene.mjs', at: new Date().toISOString(),
    };
    fs.writeSync(outFd, JSON.stringify(row) + '\n');
    if (r.ok) ok++; else fail++;
    return row;
  } catch (e) {
    fs.writeSync(outFd, JSON.stringify({ file_token: x.file_token, record_id: x.record_id,
      seq: x.seq, ok: false, error: `驱动异常：${e?.message ?? e}` }) + '\n');
    fail++;
  } finally {
    try { fs.unlinkSync(tmp); } catch { /* 已删 */ }
  }
}

async function worker() {
  while (i < todo.length) {
    const x = todo[i++];
    const row = await one(x);
    const n = ok + fail;
    if (n % 10 === 0) console.log(`[scene] ${n}/${todo.length}（ok ${ok} / fail ${fail}）`);
  }
}
await Promise.all(Array.from({ length: CONC }, worker));
fs.closeSync(outFd);
try { fs.rmSync(tmpDir, { recursive: true, force: true }); } catch { /* ignore */ }
console.log(`[scene] 完成：ok ${ok} ｜ fail ${fail} → ${OUT}`);
process.exit(fail && !ok ? 3 : 0);
