#!/usr/bin/env node
/**
 * mk_report_small_publish.mjs —— 把 `mk_report_small.py` 生成的 md **逐份建成飞书云文档**。
 *
 * ★ 只做一件事：调**管线自己的发布器** `review_publish.publishReportDoc`。
 *   为什么不自已拼 `lark-cli docs +create`：那个函数里带着两条纪律 ——
 *   ① 偶发失败补一次（`SHOUHENG_P0_DOC_ATTEMPTS`）；② 建完立刻设「组织内可阅读」并**回读确认**，
 *   回读不过就**不给 url**（「一个点不开的链接比空格更坏」）。自己拼一份就等于把它们丢了。
 *
 * ★ 不写任何表：本脚本不 import 落表那条路（`ensureReviewRow` 一次都没调）。
 *
 * 用法：node mg_report_small_publish.mjs <manifest.json>
 */
import fs from 'node:fs';
import path from 'node:path';

import { publishReportDoc } from '/Users/lute/Project/audit_multi_content/tools/agent/review_publish.mjs';

const manifestPath = process.argv[2];
if (!manifestPath) {
  console.error('用法：node mk_report_small_publish.mjs <manifest.json>');
  process.exit(2);
}
const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));
const outPath = path.join(path.dirname(manifestPath), 'reports-small-supplement.json');

const res = fs.existsSync(outPath) ? JSON.parse(fs.readFileSync(outPath, 'utf8')) : {};
for (const [i, m] of manifest.entries()) {
  if (res[m.content_id]?.ok) {                       // 断点续跑：已经建过的不重建（不造孤儿件）
    console.log(`[${i + 1}/${manifest.length}] ${m.content_id} ⇒ 已有 ${res[m.content_id].url}（跳过）`);
    continue;
  }
  const r = await publishReportDoc(m.md, { contentId: m.content_id, at: new Date().toISOString() });
  res[m.content_id] = { ok: r.ok === true, url: r.url ?? null, detail: String(r.detail ?? '').slice(0, 300),
                        issues: m.issues, state: m.state, md: m.md };
  fs.writeFileSync(outPath, JSON.stringify(res, null, 1), 'utf8');   // 每建一份就落盘（断了不重来）
  console.log(`[${i + 1}/${manifest.length}] ${m.content_id} ⇒ ${r.ok ? r.url : '✗ ' + r.detail}`);
}
const ok = Object.values(res).filter((v) => v.ok).length;
console.log(`\n合计 ${Object.keys(res).length} 份 ｜建成 ${ok} ｜失败 ${Object.keys(res).length - ok}`);
console.log(`清单 → ${outPath}`);
