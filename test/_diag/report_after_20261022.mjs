// 只读回放：拿 2026-10-22 10:46 那单的**真实**引擎 JSON ＋ 落盘条目，按改后的
// 取数/渲染重新出一份报告与卡片，用来肉眼核对四件事：
//   ① 报告里没有「图片安全审查 skill 全流程结果」这一节；
//   ② 卡片里没有「视觉分析与 OCR」；
//   ③ 知识库命中那条有中性「问题描述」，原因里不出现「历史/相似/匹配分」；
//   ④ 依据格是「表格名称 + 条款号 + 一条链接」。
//
//   node test/_diag/report_after_20261022.mjs
import fs from 'node:fs';
import * as dt from '/Users/lute/project/audit_multi_content/tools/agent/dual_track.mjs';
import { renderMergedReportMd } from '/Users/lute/project/audit_multi_content/tools/agent/merged_report.mjs';

const KB_ROOT = '/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理';
const ENGINE = `${KB_ROOT}/kb/.work/sidecars/engine-20261022-1046-97974.json`;
const RECORD = '/Users/lute/project/audit_multi_content/PMO/shouheng-state/merged-reports/merged-2026-10-22T02_49_21.004Z-1792637361004.json';

const engine = JSON.parse(fs.readFileSync(ENGINE, 'utf8'));
const kb = dt.kbFindingsOf('', engine);
console.log(`[diag] 引擎命中 ${kb.findings.length} 条；候选 ${kb.candidates.length} 条`);

const rec = JSON.parse(fs.readFileSync(RECORD, 'utf8'));
const modelFindings = rec.items.filter((i) => i.source === 'model').map((i) => {
  const [cat, ...rest] = String(i.tax_label ?? '').split('-');
  return {
    location: i.location, category: cat || '未分类', severity: i.severity,
    reason: i.reason, description: i.description, suggestionLine: i.advice,
    taxonomyCategory: cat || null, taxonomySubcategory: rest.join('-') || null,
    source: 'model', basis_kind: i.basis_kind,
    model: { basis_kind: i.basis_kind, description: i.description,
             visual_anchor: String(i.basis_card ?? '').replace(/^基于原图观察：/, '') },
  };
});

const merged = dt.mergeFindings(kb.findings, modelFindings);
const items = merged.items;
const state = 'REVIEW';
const line = `【审查结论：REVIEW】共发现 ${items.length} 处需人工确认。`;

const md = renderMergedReportMd({
  merged: items, total: items.length, state, line,
  question: '审一下这张图', withAppendix: false,
  material: { text: '图片 1 张' },
});

console.log('\n══════════ 报告（after）══════════\n');
console.log(md);
console.log('\n══════════ 校验读数 ══════════');
console.log('报告含 skill 全流程节 :', /图片安全审查 skill 全流程结果/.test(md));
console.log('报告含「历史」/「匹配分」:', /历史|匹配分/.test(md));
console.log('依据格行数             :', (md.match(/依据文档链接/g) || []).length);

const rendered = dt.renderMerged(items, { state });
console.log('\n══════════ 卡片（after）══════════\n');
console.log(rendered.block);
console.log('\n卡片含 视觉分析与 OCR :', /视觉分析与 OCR/.test(rendered.block));
