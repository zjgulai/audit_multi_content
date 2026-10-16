import fs from 'node:fs';

const STAMP = process.argv[2];
const SRC = 'kb/l4/canonical/scoped_clause.jsonl';
const rows = fs.readFileSync(SRC, 'utf8').split('\n').filter(Boolean)
  .map(l => JSON.parse(l))
  .filter(r => typeof r.anchor === 'string' && r.anchor.includes('上传人员'))
  .sort((a, b) => Number(a.article_no.split('.')[1]) - Number(b.article_no.split('.')[1]));

const csvEsc = v => {
  const s = v === null || v === undefined ? '' : String(v);
  return /[",\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
};

const header = ['条款号','上传人姓名','手机号','飞书open_id','库名','版本','条款号状态',
  '源记录ID','源表','clause_id','anchor','source_sha256','证据强度'];

const lines = [header.join(',')];
for (const r of rows) {
  const rec = (r.resource_id || '').split('__').pop();
  lines.push([
    r.article_no, r.clause_text,
    '库内不存在', '库内不存在',
    '外部标准库', 'v0（试用版，未发布）', r.status,
    rec, '数据表', r.clause_id, r.anchor, r.source_sha256, r.evidence_strength,
  ].map(csvEsc).join(','));
}

const csvPath = `上传人员-canonical导出-${STAMP}.csv`;
fs.writeFileSync(csvPath, '\ufeff' + lines.join('\n') + '\n');

const byName = {};
for (const r of rows) byName[r.clause_text] = (byName[r.clause_text] || 0) + 1;
const nums = rows.map(r => Number(r.article_no.split('.')[1]));
const people = Object.entries(byName).filter(([k]) => k !== '创研院知识库');

const md = `# 「上传人员」canonical 导出 · 说明（${STAMP}）

- 入口：\`kb-canonical-lookup\`（L4 定稿与发布层 · 查询档，**只读**）
- 数据源：\`kb/l4/canonical/scoped_clause.jsonl\`（375 行，号段 \`E-1\`）
- 导出件：\`${csvPath}\`（表头 + **${rows.length}** 行）
- 本次未写库、未发号、未晋升、未改 canonical 与台账。

## 一、要的四列，实得两列

| 你要的 | 实测结果 | 结论 |
|---|---|---|
| **条款号** | \`E-1.${nums[0]}\` … \`E-1.${nums[nums.length-1]}\` 区间内 **${rows.length}** 个号（\`status\` 全 \`stable\`） | ✅ 有 |
| **上传人姓名** | ${people.map(([k,v])=>`${k}(${v})`).join(' · ')}，另有「创研院知识库」(${byName['创研院知识库']||0}) 非人名 | ✅ 有 |
| **手机号** | **全库不存在** | ❌ 取不到 |
| **飞书 open_id** | **上传人的 open_id 不存在** | ❌ 取不到 |

## 二、手机号与 open_id 为什么取不到（实测路径）

1. **源字段本身就不带这两样**。源表 \`数据表\`（base \`N2qkb2YxuatqGLsa4U4cFQxgnCe\` / table \`tblGFyycMc45RMga\`）L0 共 32 条记录，
   「上传人员」字段定义 \`{"field_id":"fldiQL5Rgi","field_type":"text"}\` —— **文本型，不是人员型**（本次实测复现）。
   该表 32 条记录的字段类型分布：select 352 / text 96 / number 64 / link 32，**\`field_type=user\` 计数 = 0**。
   飞书只有**人员型（\`user\`）字段**才返回 open_id；文本字段从采集那一刻起就没抓到过 open_id。
2. **表里也没有电话类字段**：字段名里无「手机 / 电话 / phone / mobile」，32 条记录内无手机号形态字符串。
3. **\`ou_\` 标识符：有，但不是上传人的**。全库（\`kb/l0\`–\`kb/l7\`，不含 \`_archive\`）实测 **4 个不同 \`ou_\` 值**，
   全部出现在 **8 个 \`kb/l1/sources/\` 源文件**里，键名是 **\`creator\` / \`owner\`** ——
   即**飞书知识库节点/文档的创建者与所有者**，与「郭嘉 / 尹苗苗」无任何关联；
   \`kb/l0/records/外部资料库__数据表/*.json\` 中 \`ou_\` 命中数 = **0**。
   ⚠️ 因此**不能**把这 4 个 \`ou_\` 当作上传人的 open_id 填进导出件 —— 那是两个不同的关系。

## 三、三个必须一起看的口径问题

1. **这 ${rows.length} 条不是条款正文**。每条自己的 \`evidence_strength\` 写着
   \`资料登记元数据（field_value），非条款正文\`，\`variant = metadata_field_value\`。
   拿 \`E-1.36\` 去引用，引出来的是「郭嘉」两个字，**不是一条规则**。
2. **「创研院知识库」不是人名**（${byName['创研院知识库']||0} 条）——是团队 / 库名。
3. **你说的是「那条记录」，实际是 ${rows.length} 条**（3 个不同取值 × 多条源记录）。要精确到一条，请给**条款号**或**源记录 ID**。

## 四、引用这批号时的硬约束（按 \`kb/l7/registry/l7.json → citation_contract\`）

- 号前缀 \`E\` ⇒ \`kb_type=external_standard\` ⇒ 库名写 **《外部标准库》**，版本 **v0（试用版，未发布）**。
  ⚠️ 但同一份契约的 \`library_of_current_rules\` 写着「其余三类库……**不许拿它们当引用来源**」——
  \`E-1\` 这批号处在两句话的夹缝里，**引用前建议先找人对一次口径**。
- 引用三件套：**条款号 + \`anchor\` + \`source_sha256\`**，缺一不可（CSV 中三列均已给出）。

## 五、关于手机号 / open_id 本身（边界）

这两列**不在本知识库里**，导出件中如实写「库内不存在」，**没有用相近数据顶替、没有外推**。
真要取上传人的 open_id 或手机号，等于回飞书源侧做「姓名 → open_id → 联系方式」的**人事查询**，
属**源系统 PII 读取**，不在 L4 只读查询档范围内，本次**没有**去拉、也没有做任何姓名与 \`ou_\` 的关联。
若确需，请说明用途并确认落在治理范围与合规授权范围内。
`;

const mdPath = `上传人员-canonical导出-${STAMP}.md`;
fs.writeFileSync(mdPath, md);

// read-back verification (both files)
for (const p of [csvPath, mdPath]) {
  const b = fs.readFileSync(p);
  console.log(p, '->', b.length, 'bytes, head:', JSON.stringify(b.toString('utf8', 0, 24)));
}
console.log('rows:', rows.length, 'range:', rows[0].article_no, '..', rows[rows.length-1].article_no);
