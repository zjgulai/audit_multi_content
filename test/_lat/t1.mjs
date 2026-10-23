// 只读探针：量 readRows / previousReportLink 的真实耗时（不写任何东西）
const t0 = Date.now();
const m = await import('/Users/lute/project/audit_multi_content/tools/agent/review_publish.mjs');
console.log('import ms', Date.now() - t0);
const t1 = Date.now();
const link = await m.previousReportLink('AUTO-3a6d91937443');
console.log('previousReportLink ms', Date.now() - t1, 'link=', link);
const t2 = Date.now();
const T = m.reviewTable();
const pub = await import('/Users/lute/project/audit_multi_content/tools/agent/publish_feishu.mjs').catch(() => null);
console.log('table', JSON.stringify(T));
