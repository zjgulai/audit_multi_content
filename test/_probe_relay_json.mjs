#!/usr/bin/env node
/**
 * 中转站第二支探针：**画面层真正要的那件事** —— 「吃图 + 严格 JSON」。
 *
 *   RELAY_BASE=https://…/v1 RELAY_KEY=sk-… node test/_probe_relay_json.mjs
 *
 * 为什么要单独验：`scene.mjs` 的判据里写着「JSON 解不出 ⇒ ok:false，**不许把散文当读数收下**」。
 * 所以换端点时真正的问题不是「能不能吃图」，而是「**回来的还是不是那段 JSON**」——
 * 中转站爱加 ```json 包裹 / 加解释 / 把字段改名，任何一条都会让画面层整块变「未测」，
 * 而日志里只会写「画面读数没读到」，看起来像端点挂了。
 */
import zlib from 'node:zlib';

const BASE = (process.env.RELAY_BASE || '').replace(/\/$/, '');
const KEY = process.env.RELAY_KEY || '';
if (!BASE || !KEY) { console.error('缺 RELAY_BASE / RELAY_KEY'); process.exit(2); }

function makePng() {
  const W = 64, H = 64;
  const raw = Buffer.alloc((W * 3 + 1) * H);
  for (let y = 0; y < H; y++) {
    const r = y * (W * 3 + 1);
    for (let x = 0; x < W; x++) {
      const p = r + 1 + x * 3;
      const white = x > 48 && y > 8 && y < 24;
      raw[p] = white ? 255 : 20; raw[p + 1] = white ? 255 : 60; raw[p + 2] = white ? 255 : 220;
    }
  }
  const crc = (b) => { let c, crc = 0xffffffff; for (let n = 0; n < b.length; n++) { c = (crc ^ b[n]) & 0xff; for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1; crc = (crc >>> 8) ^ c; } return crc ^ 0xffffffff; };
  const ck = (t, d) => { const l = Buffer.alloc(4); l.writeUInt32BE(d.length); const td = Buffer.concat([Buffer.from(t), d]); const c = Buffer.alloc(4); c.writeUInt32BE(crc(td) >>> 0); return Buffer.concat([l, td, c]); };
  const ih = Buffer.alloc(13); ih.writeUInt32BE(W, 0); ih.writeUInt32BE(H, 4); ih[8] = 8; ih[9] = 2;
  return Buffer.concat([Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]), ck('IHDR', ih), ck('IDAT', zlib.deflateSync(raw)), ck('IEND', Buffer.alloc(0))]);
}
const B64 = makePng().toString('base64');

const SYS = '你只陈述画面里看得见的事实，不许判合规、不许给建议。'
  + '只输出一个 JSON 对象，形如 {"scene":"一句话描述","colors":["颜色"],"unclear":["看不清的"]}。'
  + '不要 markdown 代码块，不要解释，不要多余文字。';

const MODELS = (process.env.PROBE_MODELS || 'deepseek-flash,deepseek-v4.1-flash').split(',').map((s) => s.trim()).filter(Boolean);

for (const model of MODELS) {
  const r = await fetch(BASE + '/chat/completions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${KEY}` },
    body: JSON.stringify({
      model,
      messages: [
        { role: 'system', content: SYS },
        { role: 'user', content: [
          { type: 'text', text: '读这张图，按上面的格式给我读数。' },
          { type: 'image_url', image_url: { url: `data:image/png;base64,${B64}` } },
        ] },
      ],
      max_tokens: 400,
      response_format: { type: 'json_object' },
    }),
  });
  const txt = await r.text();
  let msg = null, parsed = null;
  try { const j = JSON.parse(txt); msg = j.choices?.[0]?.message; parsed = JSON.parse(msg?.content ?? ''); } catch {}
  const plain = String(msg?.content ?? txt).replace(/\s+/g, ' ');
  console.log([
    model.padEnd(22),
    `HTTP ${r.status}`.padEnd(9),
    `finish=${msg?.finish_reason ?? '-'}`.padEnd(18),
    `JSON ${parsed ? '✓ 可直接 parse' : '✗ 解不出'}`.padEnd(16),
    `scene=${parsed?.scene ? '有' : '无'}`,
    (parsed ? JSON.stringify(parsed).slice(0, 90) : plain.slice(0, 90)),
  ].join(' '));
}
