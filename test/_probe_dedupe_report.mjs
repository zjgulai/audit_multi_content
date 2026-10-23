// 端到端探针：P0 快路 → kbFindingsOf（去重）→ mergeFindings → 报告渲染
// 目的：证明「同一张回执不再被数第二遍」且报告里不再出现后台语言。
import { execFileSync } from 'node:child_process';
import * as dt from '/Users/lute/project/audit_multi_content/tools/agent/dual_track.mjs';
import { renderMergedReportMd } from '/Users/lute/project/audit_multi_content/tools/agent/merged_report.mjs';

const KB = '/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理';
const TEXT = process.argv[2] || '这款吸奶器最安全，销量第一。';

const out = JSON.parse(execFileSync('sh',
  [KB + '/kb/kbpy', 'l5/p0_fastpath.py', '--text', TEXT, '--json'],
  { cwd: KB, encoding: 'utf8', maxBuffer: 32 << 20 }));

console.log('hit =', out.hit, '｜ findings =', out.findings?.length,
            '｜ advisories =', JSON.stringify(out.advisories || []));

const p0 = {
  answer: out.rendered, p0_findings: out.findings, issue_count: out.issue_count,
  p0_fastpath: { mode: 'p0_fastpath', matched_patterns: out.matched_patterns,
                 rule_codes: (out.findings || []).map((f) => f.rule_code) },
  advisories: out.advisories || [],
};
const kb = dt.kbFindingsOf(p0.answer, null, p0.p0_findings, { text: TEXT });
console.log('kbFindingsOf 条数 =', kb.findings.length,
            '（必须等于 findings 数，否则就是同一张回执被数了两遍）');
console.log('kbFindingsOf 规则码 =', kb.findings.map((f) => f.kb?.article_no || f.rule_code));

const merged = dt.mergeFindings(kb.findings, []);
const md = renderMergedReportMd({
  merged: merged.items, total: merged.items.length, state: 'BLOCK',
  line: `【审查结论：BLOCK】共发现 ${merged.items.length} 处必须修改。`,
  question: TEXT, at: '2026-09-21T00:00:00Z',
  material: { text: TEXT, media: [], links: [] },
  notes: (p0.advisories || []).map((x) => `素材里出现「${x}」这类排名/销量宣称，美国平台会要求可核验的依据，发布前补一句来源与口径`),
  withAppendix: false,
});
console.log('\n════ 报告正文 ════');
console.log(md);

const leaks = [
  ['正则源码（反斜杠转义）', /\\[bBsSwWdD][^`]{0,20}`|\|（1\)/, false],
  ['库内相对路径 kb/', /kb\/l[0-9]/, false],
  ['规则码 H05/V03 之类', /\b[A-Z]\d{2}\b.*命中|命中.*\b[A-Z]\d{2}\b/, false],
  ['「本码」', /本码/, false],
  ['口径说明「不再判险」', /不再判险/, false],
  ['非阻断提示在（销量第一）', /提示（不阻断/, true],
];
let bad = 0;
for (const [name, re, want] of leaks) {
  const got = re.test(md);
  console.log(`${got === want ? '✅' : '❌'} ${name}：${got ? '出现' : '未出现'}`);
  if (got !== want) bad += 1;
}
console.log(bad ? `\n❌ ${bad} 项不符` : '\n✅ 全部符合');
process.exit(bad ? 1 : 0);
