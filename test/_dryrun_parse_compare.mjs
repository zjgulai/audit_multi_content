/**
 * 只读干跑：把历史链回答喂给「改动前 / 改动后」两套解析，diff 三样：
 *   ① 结论（Agent 结论）② 结构化条数 ③ 卡片抬头（PRD 结论行）
 * 不写表、不建报告、不调外部接口。
 */
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';

const rp = await import('../tools/agent/review_publish.mjs');
const sf = await import('../tools/agent/skill_findings.mjs');
const prd = await import('../tools/agent/prd53.mjs');

const SESS = new URL('../PMO/shouheng-state/sessions', import.meta.url).pathname;
const files = fs.readdirSync(SESS).filter((f) => f.endsWith('.json'));
const answers = new Map();
for (const f of files) {
  let d; try { d = JSON.parse(fs.readFileSync(path.join(SESS, f), 'utf8')); } catch { continue; }
  for (const m of d.messages ?? []) {
    const c = String(m?.content ?? '');
    if (!c.includes('## 一、审核对象与范围')) continue;
    const start = c.indexOf('## 一、审核对象与范围');
    let end = c.length;
    for (const t of ['—— 回话时', '【★ 飞书评审表', '【★ 这是**送审素材**', '【对方这条消息里附了图', '【图 1 指纹']) {
      const i = c.indexOf(t, start); if (i >= 0 && i < end) end = i;
    }
    const ans = c.slice(start, end).trim();
    if (ans.length < 300) continue;
    const h = crypto.createHash('sha256').update(ans).digest('hex').slice(0, 12);
    if (!answers.has(h)) answers.set(h, ans);
  }
}

const OLD_CONC = (s) => {
  const S = 'PASS\\+SUGGEST|PASS|REVIEW|BLOCK|NEEDS_INPUT|SUGGEST';
  const m = String(s ?? '').match(new RegExp(
    '(?:【\\s*审查结论\\s*[：:]|审查结论\\s*[：:]|结论\\s*[：:]|判定\\s*[：:]'
    + '|状态\\s*[：:]|state\\s*=\\s*|引擎最终输出\\s*[：:])'
    + '\\s*\\**\\s*`?\\s*(' + S + ')'));
  if (!m) return null;
  return m[1] === 'SUGGEST' ? 'PASS+SUGGEST' : m[1];
};

const withEnv = (k, v, fn) => {
  const old = process.env[k];
  try { process.env[k] = v; return fn(); }
  finally { if (old === undefined) delete process.env[k]; else process.env[k] = old; }
};

const rows = [];
for (const [h, ans] of answers) {
  const oldC = OLD_CONC(ans);
  const newC = rp.conclusionOf(ans);
  const oldF = withEnv('SHOUHENG_SKILL_FINDINGS_F', '0', () => sf.skillFindingsOf(ans).findings.length);
  const newF = withEnv('SHOUHENG_SKILL_FINDINGS_F', '1', () => sf.skillFindingsOf(ans).findings.length);
  const vOld = prd.deriveVerdictLine({ mergedState: oldC, mergedCount: oldF });
  const vNew = prd.deriveVerdictLine({ mergedState: newC, mergedCount: newF });
  rows.push({ h, len: ans.length, head: ans.replace(/\s+/g,' ').slice(0, 50), oldC, newC, oldF, newF,
              oldLine: vOld?.line ?? null, newLine: vNew?.line ?? null });
}

const changedC = rows.filter((r) => r.oldC !== r.newC);
const changedF = rows.filter((r) => r.oldF !== r.newF);
const changedL = rows.filter((r) => r.oldLine !== r.newLine);
console.log(`链回答样本：${rows.length} 份（去重后，来自 ${files.length} 个会话文件）`);
console.log(`\n① 结论变化：${changedC.length} 份`);
for (const r of changedC) console.log(`  - ${r.h} 长度${r.len} 「${r.head}…」  ${r.oldC ?? 'null'} → ${r.newC ?? 'null'}`);
console.log(`\n② 结构化条数变化：${changedF.length} 份`);
for (const r of changedF) console.log(`  - ${r.h} 长度${r.len} 「${r.head}…」  ${r.oldF} → ${r.newF} 条${r.newF >= 3 ? '（≥3 ⇒ 会建合并报告）' : ''}`);
console.log(`\n③ 卡片抬头（PRD 结论行）变化：${changedL.length} 份`);
for (const r of changedL) console.log(`  - ${r.h} 「${r.head}…」  ${r.oldLine ?? '（无，模型自拟抬头）'} → ${r.newLine ?? '（无）'}`);
console.log('\n汇总：');
console.log(`  · 会在表里改结论：${changedC.length} 份`);
console.log(`  · 会新建合并报告（条数≥3 且此前<3）：${rows.filter((r) => r.oldF < 3 && r.newF >= 3).length} 份`);
console.log(`  · 卡片抬头会被 PRD 行替换：${changedL.length} 份`);
