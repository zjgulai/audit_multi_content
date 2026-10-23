#!/usr/bin/env node
/**
 * 中转站端点能力探针（只发合成数据，不发任何客户素材）
 *
 *   RELAY_BASE=https://…/v1 RELAY_KEY=sk-… node test/_probe_relay.mjs
 *
 * 为什么需要它：守衡换端点不是「改个地址」，它依赖四件能力 ——
 *   ① 纯文本对话；② **工具调用**（每轮都带 tools，出结论靠它）；
 *   ③ **吃图**（画面层整块靠 image_url + base64）；④ DeepSeek 的 `reasoning_content` 回传协议。
 * 少任何一件，换过去之后坏的方式都**不像端点坏了**（见 AGENTS §2.4.1）。
 * 本脚本用**合成图**（现画一张 64×64 纯蓝 PNG），不碰任何真实素材。
 */
import zlib from 'node:zlib';

const BASE = (process.env.RELAY_BASE || '').replace(/\/$/, '');
const KEY = process.env.RELAY_KEY || '';
if (!BASE || !KEY) { console.error('缺 RELAY_BASE / RELAY_KEY'); process.exit(2); }

const MODELS = (process.env.PROBE_MODELS || 'deepseek-flash,deepseek-v4.1-flash').split(',').map((s) => s.trim()).filter(Boolean);

/* ── 现画一张 PNG：64×64 纯蓝，右半边一点白（让「看图」有东西可说） ── */
function makePng() {
  const W = 64, H = 64;
  const raw = Buffer.alloc((W * 3 + 1) * H);
  for (let y = 0; y < H; y++) {
    const row = y * (W * 3 + 1);
    raw[row] = 0;                                  // filter: none
    for (let x = 0; x < W; x++) {
      const p = row + 1 + x * 3;
      const white = x > 48 && y > 8 && y < 24;
      raw[p] = white ? 255 : 20;                   // R
      raw[p + 1] = white ? 255 : 60;               // G
      raw[p + 2] = white ? 255 : 220;              // B
    }
  }
  const chunk = (type, data) => {
    const len = Buffer.alloc(4); len.writeUInt32BE(data.length);
    const td = Buffer.concat([Buffer.from(type, 'ascii'), data]);
    const crc = Buffer.alloc(4); crc.writeUInt32BE(crc32(td) >>> 0);
    return Buffer.concat([len, td, crc]);
  };
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(W, 0); ihdr.writeUInt32BE(H, 4);
  ihdr[8] = 8; ihdr[9] = 2; ihdr[10] = 0; ihdr[11] = 0; ihdr[12] = 0;   // 8bit RGB
  return Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    chunk('IHDR', ihdr),
    chunk('IDAT', zlib.deflateSync(raw)),
    chunk('IEND', Buffer.alloc(0)),
  ]);
}
function crc32(buf) {
  let c, crc = 0xffffffff;
  for (let n = 0; n < buf.length; n++) {
    c = (crc ^ buf[n]) & 0xff;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    crc = (crc >>> 8) ^ c;
  }
  return crc ^ 0xffffffff;
}
const PNG_B64 = makePng().toString('base64');

async function call(payload, timeoutMs = 90_000) {
  const ac = new AbortController();
  const t = setTimeout(() => ac.abort(), timeoutMs);
  const t0 = Date.now();
  try {
    const r = await fetch(BASE + '/chat/completions', {
      method: 'POST',
      signal: ac.signal,
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${KEY}` },
      body: JSON.stringify(payload),
    });
    const txt = await r.text();
    return { status: r.status, ms: Date.now() - t0, txt };
  } catch (e) {
    return { status: 0, ms: Date.now() - t0, txt: `网络/超时：${e.name}` };
  } finally { clearTimeout(t); }
}
const short = (s, n = 150) => String(s ?? '').replace(/\s+/g, ' ').slice(0, n);

const TOOL = {
  type: 'function',
  function: {
    name: 'kb_lookup',
    description: '查知识库里某个 SKU 的价格',
    parameters: { type: 'object', properties: { sku: { type: 'string' } }, required: ['sku'] },
  },
};

const rows = [];
for (const model of MODELS) {
  // ① 纯文本
  const p1 = await call({ model, messages: [{ role: 'user', content: '只回两个字：收到' }], max_tokens: 64 });
  rows.push([model, '① 文本', p1.status, `${p1.ms}ms`, short(JSON.parse(p1.txt || '{}')?.choices?.[0]?.message?.content ?? p1.txt, 60)]);

  // ② 工具调用
  const p2 = await call({
    model,
    messages: [{ role: 'user', content: '用工具查一下 SKU=A1 的价格，别再解释。' }],
    tools: [TOOL], max_tokens: 256,
  });
  let toolOk = '—', reasoning = '—', toolMsg = null;
  try {
    const j = JSON.parse(p2.txt);
    toolMsg = j.choices?.[0]?.message ?? null;
    toolOk = toolMsg?.tool_calls?.length ? `tool_calls=${toolMsg.tool_calls.length}` : '无 tool_calls';
    reasoning = toolMsg?.reasoning_content !== undefined ? `reasoning_content=${String(toolMsg.reasoning_content).length}字` : '无 reasoning_content';
  } catch { toolOk = short(p2.txt, 80); }
  rows.push([model, '② 工具调用', p2.status, `${p2.ms}ms`, `${toolOk}｜${reasoning}`]);

  // ③ 吃图（画面层要的那一半）
  const p3 = await call({
    model,
    messages: [{
      role: 'user',
      content: [
        { type: 'text', text: '这张图主要是什么颜色？右上角有别的颜色吗？只答颜色，两句话以内。' },
        { type: 'image_url', image_url: { url: `data:image/png;base64,${PNG_B64}` } },
      ],
    }],
    max_tokens: 120,
  });
  let vision = short(p3.txt, 90);
  try { vision = short(JSON.parse(p3.txt)?.choices?.[0]?.message?.content ?? p3.txt, 90); } catch {}
  rows.push([model, '③ 吃图', p3.status, `${p3.ms}ms`, vision]);

  // ④ tools + reasoning_content 全量回传（DeepSeek 的硬协议，中转站常不实现）
  if (toolMsg?.tool_calls?.length) {
    const p4 = await call({
      model,
      messages: [
        { role: 'user', content: '用工具查一下 SKU=A1 的价格，别再解释。' },
        { role: 'assistant', content: toolMsg.content ?? '', tool_calls: toolMsg.tool_calls, ...(toolMsg.reasoning_content !== undefined ? { reasoning_content: toolMsg.reasoning_content } : {}) },
        { role: 'tool', tool_call_id: toolMsg.tool_calls[0].id, content: '{"price": 199}' },
      ],
      tools: [TOOL], max_tokens: 256,
    });
    let r4 = short(p4.txt, 90);
    try { r4 = short(JSON.parse(p4.txt)?.choices?.[0]?.message?.content ?? p4.txt, 90); } catch {}
    rows.push([model, '④ 回传协议', p4.status, `${p4.ms}ms`, r4]);
  } else {
    rows.push([model, '④ 回传协议', 'skip', '—', '② 没有 tool_calls ⇒ 无从验']);
  }
}

const w = [26, 14, 6, 10, 100];
console.log(`端点 ${BASE}`);
for (const [m, k, s, ms, d] of rows) {
  console.log([String(m).padEnd(w[0]), String(k).padEnd(w[1]), String(s).padEnd(w[2]), String(ms).padEnd(w[3]), d].join(' '));
}
