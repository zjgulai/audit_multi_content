/**
 * 判据：Codex 11:52 那版「稳定缓存键」会不会**把盲审结果（判据未跑/画面未测 ⇒ 0 条）当成定论永久粘住**？
 *
 * 只喂桩，不联网、不碰生产状态文件（file 指临时目录）。
 * 场景重现自真实读数：03:48 那次群里 run，模型侧返回 `{ok:true, count:0}`（画面读数被截断，模型被告知不许推断）。
 */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { reviewImageOnce } from '../../tools/agent/image_review_cache.mjs';

const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'imgcache-probe-'));
const img = path.join(dir, 'a.png');
fs.writeFileSync(img, Buffer.from('fake-image-bytes-for-key-only'));
const file = path.join(dir, 'cache.json');

const base = {
  imagePaths: [img],
  model: 'deepseek:deepseek-flash',
  cacheContract: 'SYSTEM\nimage-safety-full-review-v1',
  file,
};

// 第一次：群里那次 —— 画面未测，模型侧如实「没看到任何东西」，返回 ok:true / findings:[]
let calls = 0;
const first = await reviewImageOnce({
  ...base,
  contract: '本轮读数：画面层**未测**（max_tokens 用尽）',
  run: async () => { calls++; return { ok: true, findings: [], dropped: [], ms: 1187 }; },
});

// 第二次：私聊再问同一张图 —— 画面这次读到了，模型侧本该报 4 条
const findings4 = [
  { reason: '婴幼儿跟成人同床' }, { reason: '睡在枕头上' }, { reason: '水印未清理' }, { reason: '斜体排版' },
];
const second = await reviewImageOnce({
  ...base,
  contract: '本轮读数：画面已读到（卧室 / 婴幼儿仰卧 / 同床）',
  run: async () => { calls++; return { ok: true, findings: findings4, dropped: [], ms: 4676 }; },
});

console.log('第一次（盲审）返回条数 =', first.findings.length);
console.log('第二次（同一张图、政策没变、读数更好）返回条数 =', second.findings.length,
            '| cached =', second.cached, '| run 被调用次数 =', calls);
console.log(second.findings.length === 0
  ? '❌ 盲审的 0 条被当成定论复用了 —— 私聊会跟着群里一起变成「1 处」'
  : '✅ 没有复用空结果');
fs.rmSync(dir, { recursive: true, force: true });
