// 复现：P0 确定性命中 + 带图单 ⇒ 图片闸门把 BLOCK 压成 NEEDS_INPUT 并回「证据未通过」拒答
// 用法：node test/_diag/repro_p0_image_refusal.mjs
import { runSubmissionGate } from '../../tools/agent/agent.mjs';
import { parseScene } from '../../tools/agent/scene.mjs';

const P0_RENDERED = [
  '【审查结论：BLOCK】共发现 1 处必须修改。',
  '逐条问题',
  '· 绝对化用语（E-2.124）：图上出现「100%」，无证据支撑。',
  '→ 查看完整问题清单与修改建议：https://example.invalid/docx/P0STUB',
].join('\n');

const P0 = {
  ok: true,
  answer: P0_RENDERED,
  p0_fastpath: { mode: 'p0_fastpath', elapsed_ms: 115.029, matched_patterns: 1, rule_codes: ['V02'],
                 layer_preflight: { mode: 'p0_fastpath', enforced: false, is_pass_basis: false } },
  p0_findings: [{
    rule_code: 'V02', level: 'P0', verdict: 'BLOCK', article_no: 'E-2.124',
    matched: [{ line_text: '100%', span: [0, 4] }], matched_count: 1,
  }],
  advisories: [],
  issue_count: 1,
  confidence: 1.0,
  report: 'https://example.invalid/docx/P0STUB',
  report_path: null,
  report_detail: '自证桩',
  product_line: '', channel: '',
};

const inbound = {
  text: '', imageCount: 1, videoCount: 0,
  images: [{
    index: 1, wlText: 'Choose Any 3 … Nipple Cream 100%', lines: 17,
    scene: { ok: true, scene: parseScene(JSON.stringify({ products: [
      { what: '带盖的透明宽口容器', orientation: '正放' },
      { what: '白色小瓶', orientation: '正放' },
    ] })).scene },
  }],
};

const findings = [
  { location: '图 1 主视觉', category: '商品信息与Listing准确性', severity: 'REVIEW',
    reason: '组合价适用范围含糊', excerpt: 'Choose Any 3 Pay Less than $99', suggestion: '写明适用品类', source: 'none' },
  { location: '图 1 主视觉', category: '推广与价格透明', severity: 'REVIEW',
    reason: '促销价易被误读', excerpt: 'Choose Any 3 Pay Less than $99', suggestion: '补价格规则', source: 'none' },
];

let row = null;
const result = await runSubmissionGate({
  inbound, question: inbound.text, notify: async () => {},
  chainRunner: async () => P0,
  modelSideRunner: async () => ({ ok: true, findings, dropped: [] }),
  publishRunner: async (r) => { row = r; return { ok: true, action: 'skipped', detail: '自证桩' }; },
  mergedReportRunner: async () => ({ ok: true, url: 'https://example.invalid/docx/STUB', detail: '自证桩' }),
  adviceRunner: async () => ({ ok: true, ms: 1, advice: {} }),
  mediaLinksRunner: async () => [],
  mediaUpload: async () => ({ ok: false, reason: '自证桩' }),
  fetchImageForLink: async () => null,
  fetchVideoForLink: async () => null,
  tIngress: Date.now(),
});

console.log('row.conclusion     =', row?.conclusion);
console.log('imageReviewIncomplete =', result.imageReviewIncomplete);
console.log('forcedReply        =', JSON.stringify(String(result.forcedReply ?? '').slice(0, 200)));
console.log('verdict53          =', result.verdict53?.line ?? null);
console.log('p0DirectReply      =', JSON.stringify(String(result.p0DirectReply ?? '').slice(0, 200)));
console.log('dual.state         =', result.dual?.state ?? null);
