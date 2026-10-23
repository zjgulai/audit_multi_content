// 只读复现：合并报告的「依据文档链接」为什么会出现多条一模一样的链接。
//   node test/_diag/dup_basis_repro.mjs
//
// 两个独立缺陷，各有一节：
//   ① dual_track.mjs  mergeFindings()：把合并后的 basisLine **回写**到
//      prev.basisLine / prev.kb.basisLine，下一轮再把这份「已经拼好的」当成一条输入，
//      于是同一条依据每合并一次就复制一遍（4 条 findings → 7 段；3 条 → 4 段）。
//   ② dual_track.mjs  renderMergedItem()：「原始出处」后面的 URL 用 \S+ 取，
//      而中文标点不是空白 ⇒ URL 会把紧跟的「；《…》第」一起吞进链接目标。
import * as dt from '/Users/lute/project/audit_multi_content/tools/agent/dual_track.mjs';

const F = (n) => ({
  location: '顶部，图 1 第 2 处', category: '负面样本', source: 'kb', severity: 'REVIEW',
  basisLine: `《内部正负样本库》第 N-1.${n} 条｜锚点：#负面样本/rec…｜原始出处：https://x.test/rec`,
  kb: { article_no: `N-1.${n}`, anchor: '#负面样本/rec…',
        basisLine: `《内部正负样本库》第 N-1.${n} 条｜锚点：#负面样本/rec…｜原始出处：https://x.test/rec` },
});

console.log('① mergeFindings 的复合重复');
for (const n of [1, 2, 3, 4]) {
  const items = dt.mergeFindings(Array.from({ length: n }, (_, i) => F(i + 307)), []).items;
  const basis = String(items[0]?.kb?.basisLine ?? '');
  const segs = basis.split('；');
  console.log(`  n=${n} 条 findings ⇒ 依据 ${segs.length} 段：${segs.map((s) => (s.match(/N-1\.\d+/) || ['?'])[0]).join(' / ')}`);
}
console.log('  期望：n 条各不相同的条款 ⇒ n 段（每条条款只出现一次）。');

console.log('\n② 链接化时 URL 吞中文');
const raw = '《内部正负样本库》第 N-1.307 条｜原始出处：https://x.test/rec；《内部正负样本库》第 N-1.312 条';
const out = raw.replace(/(原始出处[:：])(https?:\/\/\S+)/,
  (_m, p1, url) => `${p1}[点开核对](${url.replace(/）$/, '')})`);
console.log('  实际：', out);
console.log('  期望：', '原始出处：[点开核对](https://x.test/rec)；《内部正负样本库》第 N-1.312 条');

console.log('\n③ 同一 (位置, 类目) 的模型侧多条 finding 会被折成一条，后几条的 description/reason 不落条目');
const M = (n, desc) => ({ location: '图 1 主视觉', category: '母婴知识内容准确性', severity: 'REVIEW',
  source: 'model', description: desc, reason: `理由 ${n}`, suggestionLine: `改法 ${n}` });
const r = dt.mergeFindings([], [M(1, '缺 AAP 出处'), M(2, '床垫护栏细节含糊'), M(3, '睡姿未讲')]);
console.log('  3 条模型侧 findings ⇒ 条目数', r.items.length,
            '｜条目上只剩描述：', r.items.map((it) => it.model?.description ?? it.description ?? '（空）'));
