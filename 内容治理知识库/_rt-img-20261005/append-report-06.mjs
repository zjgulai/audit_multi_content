import fs from 'node:fs';

const dir = 'kb/l7/reports';
const src = `${dir}/rv-20261005-121322.feishu.md`;
const dst = `${dir}/rv-20261005-121322.review.md`;

const addendum = `

---

## 附录 · 本单过程与更正（IMG-06）

### A. 结论的来路（务必一起读）
- 引擎 \`with_kb_evidence.py\` 本单**实际输出 = \`NEEDS_INPUT\`（拒答 · 退出码 3）**：
  P0 0 命中、509 条规则 0 命中、L6 召回 Top10 **未召回** S-1.2 的单元 \`f8e2ee3741a6d1b8c307\`（现跑复核）。
- 本 BLOCK **不是引擎产出的**，是判定主体「图片安全审查」按 **Owner 2026-10-05 规则①**
  （自命中已定稿反例/禁区 = 本素材本身有定论，必须登记 findings 并出三态）登记得出。
- 引擎侧缺口记作 **GAP-SELFHIT-1**：对 \`polarity=反例\` / \`semantics\` 以「禁区」开头的条款没有消费者。
  **该缺口未登记进 \`kb/l7/registry\`**（前单 IMG-04/05 也未登记）—— 建议治理侧决定是否补登记。

### B. 更正前两单的两处不实陈述
1. 「库内 sample_case 自带 \`not_proves\`/\`forbidden\`（案例只作参照、不许据本条直接判 BLOCK）」——**不成立**。
   \`kb/l4/canonical/sample_case.jsonl\` 的 S-1.2/S-1.175 **没有**这两个字段（grep 0 命中）。
   那两段文字只在**派生视图生成器的旧备份**里（\`.work/hostlib.bak-20260928-182653/\`、
   \`kb/l7/_backups/interp-20260929-175116/.work/gen-host-library-l4.py:242-243\`），
   是宿主库视图给案例统一盖的「参照」章；当前 live view 只有 \`3_措辞表达库\`、不含案例。
   ⇒ 本单**不作为「活冲突」上报**。
2. 「德语串在 L0『原文反馈』字段末尾」——**不成立**。本单现核：L0 记录
   （\`recvw2vgYXHKgM\` / \`recvw2wE9MmvI2\`）的文本字段（\`具体原因/分析\` / \`原文反馈\` / \`建议\`）
   **都不含德语**；德语 7 行是**图片附件的 OCR**，落在
   - \`kb/l1/2_内部正负样本库/bitable__tbld8qE92YaY38Yz__recvw2vgYXHKgM_fldnvxjaSr_HVTxbd5lPoLgnfxlCCyc60g2nHc.json\`（\`source_sha256=a3c7828f…\`）
   - \`kb/l1/media/recvw2vgYXHKgM/ocr.json\`
   - \`kb/l1/media/_cache/a3c7828f….json\`
   L4 \`sample_body\` 是把该图片 OCR 挂进案例正文，德语因此出现在 canonical。
   **自命中的真实坐标 = 媒体锚点** \`#素材/recvw2vgYXHKgM/图片素材/#img.1\`（不是 \`原文反馈\`）。

### C. 送审信息与留痕
| 项 | 值 |
|---|---|
| BASE | \`RT-20261005-IMG-06\` |
| 引擎封套 | \`_rt-img-20261005/rt-img-06-engine.json\`（\`state=NEEDS_INPUT\`，退出码 3） |
| 组装件 | \`_rt-img-20261005/rt-img-06-decision.json\` |
| 登记件（四段溯源） | \`_rt-img-20261005/rt-img-06-findings-registered.json\` |
| 组装脚本 | \`_rt-img-20261005/build-rt-img-06-decision.py\` |
| 送审文本 | \`_rt-img-20261005/rt-img-06-text.txt\` |
| 层 run | \`kb/l7/runs/RT-20261005-IMG-06-L{4,5,6,7}.json\` |
| 四道审计 | L4/L5/L6/L7 全 exit 0（红 0） |
| 飞书表行 | \`AD-20261005-010\` ／ record \`recvx94s5yoXW5\`（读回 BLOCK / 2 条） |
`;

const body = fs.readFileSync(src, 'utf8');
fs.writeFileSync(dst, body + addendum, 'utf8');
const a = fs.statSync(src).size;
const b = fs.statSync(dst).size;
console.log('src bytes:', a, '| dst bytes:', b);
console.log('first line:', fs.readFileSync(dst, 'utf8').split('\n')[0]);
