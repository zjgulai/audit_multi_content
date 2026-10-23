// 只读探针：「同一张图/同一份素材再发一次」会不会复用第一次的结论？
// 不写任何东西：只读结论表 + 只读机读台账。
//   node test/_lat/repeat_review_probe.mjs
import fs from 'node:fs';
import { listRecords } from '/Users/lute/Project/audit_multi_content/tools/agent/lark_write.mjs';

const ROOT = '/Users/lute/Project/audit_multi_content';
const T = { appToken: 'RY2UbCRjXaeeWwscUPScVN5AnQc', table: 'tblCXPQVzfFWWCon' };

// ① 结论表：行数 / 内容 ID 形态 / 重复
const page = await listRecords(T.appToken, T.table, { limit: 500 });
const rows = page?.records ?? [];
const byId = new Map();
let auto = 0, ad = 0;
for (const r of rows) {
  const id = String(r.fields?.['内容 ID'] ?? '');
  if (id.startsWith('AUTO-')) auto++; else if (/^AD-/.test(id)) ad++;
  byId.set(id, (byId.get(id) ?? 0) + 1);
}
const dups = [...byId.entries()].filter(([, n]) => n > 1);
console.log(`① 结论表：${rows.length} 行 ｜ AUTO- 内容指纹 ${auto} 行 ｜ 链侧 AD- 当日序号 ${ad} 行`);
console.log(`   同一内容 ID 出现在多行：${dups.length} 个 —— ${dups.map(([k, n]) => `${k}×${n}`).join('，') || '无'}`);

// ② 机读台账：同一份素材被送审几次、结论会不会变
const led = fs.readFileSync(`${ROOT}/PMO/shouheng-state/confidence-merged.ndjson`, 'utf8')
  .split('\n').filter(Boolean).map((l) => { try { return JSON.parse(l); } catch { return null; } }).filter(Boolean);
const g = new Map();
for (const r of led) {
  const k = r.material_sha8;
  if (!k) continue;
  g.set(k, [...(g.get(k) ?? []), r.state]);
}
const multi = [...g.entries()].filter(([, v]) => v.length > 1);
const flipped = multi.filter(([, v]) => new Set(v).size > 1);
console.log(`② 机读台账：${led.length} 单 ｜ 素材键 ${g.size} 个 ｜ 被重复送审 ≥2 次：${multi.length} 个`);
console.log(`   其中结论**变过**的：${flipped.length} 个（结论一致 ${multi.length - flipped.length} 个）`);
for (const [k, v] of flipped.slice(0, 4)) console.log(`   · ${k} → ${v.join(' → ')}`);
