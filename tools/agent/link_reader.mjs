/**
 * link_reader.mjs —— 只读**匿名公网页面**（HTML / 纯文本）。
 *
 * ★ 2026-10-22 加这条说明：**飞书链接不归这里管**。
 *   飞书网页一律 302 到 `accounts.feishu.cn`（登录页），匿名抓取读不到正文；本机 DNS
 *   还会把它解析到私网地址，于是这里报「域名解析到非公网地址」——**原因指偏了**。
 *   飞书文档该走 `feishu_link.readLink()`（飞书只读接口）。分流点只有那一个，
 *   别在这里加飞书特例：两处都能判，就会出现「一处放行、一处拦截」。
 */
import dns from 'node:dns/promises';
import http from 'node:http';
import https from 'node:https';
import net from 'node:net';
import { gunzipSync, inflateSync, brotliDecompressSync } from 'node:zlib';

/**
 * ★★ 2026-10-23：**1 MB → 4 MB**（Owner 当场裁定 ②）。
 *
 * 为什么改（实测，不是估的）：守衡测试表第 93/95/98/100 行的素材是 **YouTube 观看页**，
 * 实测页面 **1.26–1.29 MB** ⇒ 卡在原来那个 1 MB 上，整条链接送审**一条结论都出不来**
 * （同一批里 7 条 Amazon PDP 是通的 —— 它们对匿名 UA 回的文件更小，所以从没暴露这个上限）。
 *
 * ⚠️ **改的是"闸门高度"，不是"闸门要不要"**：超过新上限**照样硬拒**、照样 fail-closed。
 *   为什么不顺手改成"读满 4 MB 就截断继续" —— 那会把「没读全」静默成「读全了」，
 *   正是本仓反复栽过的那个形状（§2.4）。要放开截断得单独定口径，不在这次改动里。
 * ⚠️ 代价照实说：读一个 4 MB 的页面比 1 MB 多花时间与内存；抽出来的正文仍按
 *   `extractReadableText` 的 30 000 字截断，所以**上限抬高不会让送进模型的正文变长**。
 */
export const MAX_BYTES = 4_000_000;
const MAX_REDIRECTS = 3;
const TIMEOUT_MS = 8_000;

/**
 * ★★ 2026-10-23：**压缩正文必须解压，解不开宁可拒读**（这一条是当天实测的真故障，不是防御性编程）。
 *
 * 病灶（守衡测试表第 55 行，Amazon PDP `https://www.amazon.com/dp/B0FHQJWPTN`）：
 * 本读取器**从不发 `accept-encoding`、也从不看 `content-encoding`**，而 Amazon 对匿名 UA
 * **照样回 gzip**（不合规，但它就这么干）。于是 `Buffer→toString('utf8')` 把**压缩字节当成正文**：
 * 实测读出 30 000 字噪声、**含 136 个 `\u0000`**，开头的 `1f 8b 08` 就是 gzip 魔数。
 * 后端表现**不在这一层**，而是在更下游、更难认的地方：
 *   `execFile` 抛 `The argument 'args[3]' must be a string without null bytes`
 *   —— 链任务串里带了正文，零字节直接把 spawn 打回，读起来像「库忙/闸门红」。
 *   ⇒ 判据得**卡在入口**：正文要么是真文本，要么明说读不到，**不许把噪声喂进链**。
 *
 * 两件事一起做，缺一条都还会漏：
 *   ① 主动要 `identity`（大多数服务器会照办）＋ **服务器不照办时按 `content-encoding` 解压**；
 *   ② 解完仍像二进制（有 `\u0000` 或替换字符成片）⇒ **拒读**，不返回半份噪声。
 * ⚠️ 保留 `looksBinary` 这条只看结果的兜底，是因为**编码头也可能撒谎**（说 identity、其实 gzip）。
 */
export function decodePageBody(raw, contentEncoding = '') {
  const buf = Buffer.isBuffer(raw) ? raw : Buffer.from(String(raw ?? ''), 'utf8');
  const enc = String(contentEncoding ?? '').split(',')[0].trim().toLowerCase();
  try {
    if (!enc || enc === 'identity') return { ok: true, text: buf.toString('utf8') };
    if (enc === 'gzip' || enc === 'x-gzip') return { ok: true, text: gunzipSync(buf).toString('utf8') };
    if (enc === 'br') return { ok: true, text: brotliDecompressSync(buf).toString('utf8') };
    if (enc === 'deflate') {
      // `deflate` 在野外有两种：带 zlib 头与不带（raw）。两种都试，别再让一个站点卡住整单。
      try { return { ok: true, text: inflateSync(buf).toString('utf8') }; }
      catch { return { ok: true, text: inflateSync(buf, { finishFlush: 2 }).toString('utf8') }; }
    }
    return { ok: false, error: `不认识的压缩方式：${enc}（已放弃读取，不当正文用）` };
  } catch (e) {
    return { ok: false, error: `压缩正文解不开（${enc}）：${e?.code ?? e?.message}` };
  }
}

/** 正文里出现 `\u0000`，或替换字符（U+FFFD）成片 ⇒ 这不是可读文本，是二进制/压缩残留。 */
export function looksBinary(text) {
  const s = String(text ?? '');
  if (!s) return false;
  if (s.includes('\u0000')) return true;
  const bad = (s.match(/\uFFFD/g) || []).length;
  return bad / [...s].length > 0.02;
}

/**
 * 超限判据**单独抽出来**（2026-10-23）：不是为了好看，是为了**能反向对照** ——
 * `link_reader.test.mjs` 里拿同一个字节数喂两个上限，一个必须放行、一个必须拦下，
 * 这样「上限真的变了」这件事有失败信号，而不是靠读常量。
 */
export function overCap(bytes, cap = MAX_BYTES) {
  return Number(bytes) > Number(cap);
}

function isPublicIp(ip) {
  const family = net.isIP(ip);
  if (family === 4) {
    const [a, b] = ip.split('.').map(Number);
    const c = Number(ip.split('.')[2]);
    return !(a === 0 || a === 10 || a === 127 || a >= 224 || (a === 100 && b >= 64 && b <= 127)
      || (a === 169 && b === 254) || (a === 172 && b >= 16 && b <= 31)
      || (a === 192 && b === 168) || (a === 192 && b === 0) || (a === 192 && b === 88 && c === 99)
      || (a === 192 && b === 0 && c === 2) || (a === 198 && (b === 18 || b === 19))
      || (a === 198 && b === 51 && c === 100) || (a === 203 && b === 0 && c === 113));
  }
  // IPv6 is deliberately unsupported until the request pinning path can normalize all textual forms.
  return false;
}

export function normalizePublicUrl(value) {
  let url;
  try { url = new URL(String(value)); } catch { throw new Error('链接格式无效'); }
  if (!['http:', 'https:'].includes(url.protocol)) throw new Error('仅支持 HTTP(S) 链接');
  if (url.username || url.password) throw new Error('不接受含账号凭据的链接');
  if (url.port && !((url.protocol === 'http:' && url.port === '80') || (url.protocol === 'https:' && url.port === '443'))) {
    throw new Error('不支持非标准端口');
  }
  if (url.hostname === 'localhost' || url.hostname.endsWith('.localhost') || url.hostname.endsWith('.local')) {
    throw new Error('目标不是公网地址');
  }
  const literalIp = url.hostname.replace(/^\[|\]$/g, '');
  if (net.isIP(literalIp) && !isPublicIp(literalIp)) throw new Error('目标不是公网地址');
  url.hash = '';
  return url.toString();
}

async function resolvePublic(hostname) {
  const literal = hostname.replace(/^\[|\]$/g, '');
  const records = net.isIP(literal) ? [{ address: literal }] : await dns.lookup(hostname, { all: true, verbatim: true });
  if (!records.length || records.some((r) => !isPublicIp(r.address))) {
    throw new Error(`域名解析到非公网地址，已阻止读取（${hostname}）`);
  }
  return records.map((r) => r.address);
}

function requestPage(urlString, pinnedIp) {
  return new Promise((resolve, reject) => {
    const url = new URL(urlString);
    const client = url.protocol === 'https:' ? https : http;
    const req = client.request(url, {
      method: 'GET', timeout: TIMEOUT_MS,
      headers: {
        'user-agent': 'ShouhengContentReview/1.0',
        accept: 'text/html,text/plain;q=0.9',
        // ★ 主动要「不压缩」。服务器不照办也不怕：`content-encoding` 会在下面被解掉（见文件头）。
        'accept-encoding': 'identity',
      },
      // Resolve once, validate every DNS answer, and pin the socket to a validated public address.
      lookup: (_hostname, options, cb) => {
        if (typeof options === 'function') { cb = options; options = {}; }
        if (options?.all) cb(null, [{ address: pinnedIp, family: net.isIP(pinnedIp) }]);
        else cb(null, pinnedIp, net.isIP(pinnedIp));
      },
    }, (res) => {
      const chunks = [];
      let bytes = 0;
      res.on('data', (chunk) => {
        bytes += chunk.length;
        if (overCap(bytes)) { req.destroy(new Error(`页面超过 ${MAX_BYTES / 1_000_000} MB 读取上限`)); return; }
        chunks.push(chunk);
      });
      res.on('end', () => resolve({
        status: res.statusCode ?? 0,
        location: res.headers.location,
        contentType: String(res.headers['content-type'] ?? ''),
        contentEncoding: String(res.headers['content-encoding'] ?? ''),
        // 原文**保留字节**：解压必须拿字节做，`toString` 之后就再也解不回来了（这就是当天那个 bug）。
        raw: Buffer.concat(chunks),
        body: Buffer.concat(chunks).toString('utf8'),
      }));
    });
    req.on('timeout', () => req.destroy(new Error('读取页面超时（8 秒）')));
    req.on('error', reject);
    req.end();
  });
}

export function extractReadableText(html) {
  const source = String(html ?? '')
    .replace(/<!--[\s\S]*?-->/g, ' ')
    .replace(/<(script|style|noscript|svg|iframe|template)\b[^>]*>[\s\S]*?<\/\1\s*>/gi, ' ')
    .replace(/<(br|\/p|\/div|\/li|\/h[1-6]|\/article|\/section|\/main|\/tr)\b[^>]*>/gi, '\n')
    .replace(/<[^>]+>/g, ' ')
    .replace(/&nbsp;|&#160;/gi, ' ')
    .replace(/&amp;/gi, '&').replace(/&lt;/gi, '<').replace(/&gt;/gi, '>')
    .replace(/&quot;|&#34;/gi, '"').replace(/&#39;|&apos;/gi, "'")
    .replace(/&#(\d+);/g, (_m, n) => String.fromCodePoint(Math.min(Number(n), 0x10ffff)))
    .replace(/&#x([\da-f]+);/gi, (_m, n) => String.fromCodePoint(Math.min(parseInt(n, 16), 0x10ffff)));
  return source.split(/\n+/).map((s) => s.replace(/\s+/g, ' ').trim()).filter(Boolean).join('\n').slice(0, 30_000);
}

export async function readPublicPage(value, deps = {}) {
  let url = normalizePublicUrl(value);
  const resolve = deps.resolvePublic ?? resolvePublic;
  const request = deps.requestPage ?? requestPage;
  for (let redirects = 0; redirects <= MAX_REDIRECTS; redirects++) {
    const parsed = new URL(url);
    const addresses = await resolve(parsed.hostname);
    if (!Array.isArray(addresses) || !addresses.length || addresses.some((ip) => !isPublicIp(ip))) {
      // 把**跳转后的域名**写进报错：否则「域名解析到非公网地址」会被读成「你贴的那条链接有问题」，
      // 而实际常见的形状是「原链接是公网、它 302 到了登录页/内网地址」（2026-10-22 实测）。
      throw new Error(`域名解析到非公网地址，已阻止读取（${parsed.hostname}）`);
    }
    const response = await request(url, addresses[0]);
    if ([301, 302, 303, 307, 308].includes(response.status)) {
      if (!response.location || redirects === MAX_REDIRECTS) throw new Error('页面重定向次数超限或目标缺失');
      url = normalizePublicUrl(new URL(response.location, url).toString());
      continue;
    }
    if (response.status < 200 || response.status >= 300) throw new Error(`页面读取失败：HTTP ${response.status}`);
    // ── 先解压、再判「像不像文本」（顺序不能反：压缩字节里必然有 \u0000，先判会把正常页面也拦下）──
    const dec = decodePageBody(response.raw ?? response.body ?? '', response.contentEncoding ?? '');
    if (!dec.ok) throw new Error(dec.error);
    if (looksBinary(dec.text)) throw new Error('页面正文不是可读文本（疑似二进制内容），已放弃读取');
    const type = response.contentType.split(';')[0].trim().toLowerCase();
    if (!['text/html', 'text/plain'].includes(type)) throw new Error(`不支持的内容类型：${type || '未知'}`);
    const text = type === 'text/html' ? extractReadableText(dec.text) : String(dec.text).trim().slice(0, 30_000);
    if (!text) throw new Error('页面读取成功但没有可审核的正文');
    return { url, contentType: type, text };
  }
  throw new Error('页面读取失败：重定向异常');
}
