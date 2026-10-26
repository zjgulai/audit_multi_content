#!/usr/bin/env node
/**
 * scene.test.mjs —— **画面层**的判据（2026-10-15）
 *
 *   node tools/agent/scene.test.mjs
 *
 * ⚠️ **一个字节都不发**：全部走注入的 `fetchImpl` 桩。真网络那一条在
 *    `tools/test_agent.mjs` 的「画面层」一组（真跑试纸），这里只证**判据**。
 *
 * ── 这个文件是为哪一次事故写的
 *
 *   2026-10-15：一张**只有品牌字样**的图被审出「逐字命中 ibclc」——
 *   那是另一个并发单的结论（旁挂串单，另案）。但顺着查下去发现**更缺的一块**：
 *   PRD §5.1 把图片的输入写成两半（**OCR ＋ 基础视觉识别**），而这一层**从来没做**,
 *   两侧吃的都是同一份图内文字 ⇒ PRD 要求的「产品使用 / 人物行为 / 场景风险」
 *   **整类没有东西在判**。起因是 `vision.mjs` 头注那句「模型不吃图」——
 *   当天实测否掉（同一个端点带 image_url ⇒ HTTP 200）。
 *
 * ── 判据分四类（每条都写了「拆掉它会怎样」）
 *
 *   S1 解析：**只认 JSON**（散文/空 ⇒ `ok:false`）——「读不到」与「没有画面」必须分得开
 *   S2 守卫：**只读临时目录里的图**（§2.6 那条加宽的边界就在这一个函数里）
 *   S3 截断：`finish_reason: 'length'` ⇒ **未测**（这是我当场踩的坑，见下）
 *   S4 失败面：HTTP 错 / 超时 / 空内容 ⇒ 一律 `ok:false`，且**永不抛**
 *   S5 反向对照：合法的读数**必须收下**（闸门不许成砖头）+ 摊开时空项要写明「读数里没有」
 */
import assert from 'node:assert';
import { parseScene, sceneBlock, sceneLine, assertTempPath, sceneRead, SCENE_SYSTEM, abnormalContainers, infantSleepReadings } from './scene.mjs';
import { restatePerPanelSleep, checkVisualChecklist } from './visual_checklist.mjs';

const results = [];
const check = (id, fn) => {
  try { fn(); results.push({ id, ok: true }); }
  catch (e) { results.push({ id, ok: false, detail: e.message }); }
};
const checkAsync = async (id, fn) => {
  try { await fn(); results.push({ id, ok: true }); }
  catch (e) { results.push({ id, ok: false, detail: e.message }); }
};

const GOOD = JSON.stringify({
  setting: '厨房',
  people: [{ kind: '婴幼儿', doing: '被抱着' }],
  products: [{ what: '粉色球形物', in_use: false }],
  visible_marks: ['momcozy'],
  risk_cues: ['婴幼儿出镜'],
  unclear: ['月龄'],
});

/* ── S1 解析：只认 JSON ───────────────────────────────────────────────── */
check('S1a 标准 JSON ⇒ 收下，字段齐全', () => {
  const r = parseScene(GOOD);
  assert.strictEqual(r.ok, true, `没收下：${JSON.stringify(r)}`);
  assert.strictEqual(r.scene.setting, '厨房');
  assert.strictEqual(r.scene.people[0].kind, '婴幼儿');
  assert.deepStrictEqual(r.scene.visible_marks, ['momcozy']);
});
check('S1b 包在 ```json 围栏里 ⇒ 脱一层围栏收下（模型常见写法）', () => {
  assert.strictEqual(parseScene('```json\n' + GOOD + '\n```').ok, true);
});
check('S1c ★ 散文 ⇒ **拒**（`ok:false`）—— 把散文当读数就是 §2.4.1 那个病', () => {
  const r = parseScene('这张图看起来是一位妈妈在厨房，没有明显问题。');
  assert.strictEqual(r.ok, false, '散文被当成读数收下了');
  assert.ok(/不是 JSON/.test(r.error), `错误文案没说清是 JSON 的问题：${r.error}`);
});
check('S1d 空内容 ⇒ 拒，且与「没有画面」不是同一句话', () => {
  const r = parseScene('   ');
  assert.strictEqual(r.ok, false);
  assert.ok(/空内容/.test(r.error), r.error);
});
check('S1e 缺字段 ⇒ 收下但**如实留空**（不许拿「未给」冒充事实）', () => {
  const r = parseScene('{}');
  assert.strictEqual(r.ok, true);
  assert.strictEqual(r.scene.setting, '未给');
  assert.deepStrictEqual(r.scene.risk_cues, []);
});
check('S1f 字符串写成数组的地方 ⇒ 归一，不炸', () => {
  const r = parseScene(JSON.stringify({ setting: '浴室', visible_marks: 'momcozy' }));
  assert.deepStrictEqual(r.scene.visible_marks, ['momcozy']);
});
check('S1g ★ 婴儿睡眠场景逐人结构化记录睡姿；缺字段不得默认仰卧', () => {
  const r = parseScene(JSON.stringify({ people: [
    { kind: '婴幼儿', panel: '左上', doing: '闭眼睡觉', sleep_scene: true, sleep_posture: '侧卧', sleep_posture_basis: '身体侧面贴床' },
    { kind: '婴幼儿', panel: '右下', doing: '躺在婴儿床', sleep_scene: true, sleep_posture: '仰卧', sleep_posture_basis: '背部贴床、面部朝上' },
  ] }));
  assert.strictEqual(r.scene.people[0].sleep_posture, '侧卧');
  assert.strictEqual(r.scene.people[0].panel, '左上');
  assert.strictEqual(r.scene.people[0].sleep_posture_basis, '身体侧面贴床');
  assert.strictEqual(r.scene.people[1].sleep_posture, '仰卧');
  assert.strictEqual(parseScene(JSON.stringify({ people: [{ kind: '婴幼儿', doing: '睡觉' }] }))
    .scene.people[0].sleep_posture, '未给', '缺少姿势字段时不许默认成仰卧');
  assert.strictEqual(parseScene(JSON.stringify({ people: [{ kind: '婴幼儿', doing: '被抱着', sleep_posture: '不适用' }] }))
    .scene.people[0].sleep_posture, '不适用');
});
check('S1g-2 ★ 睡眠面板逐个投闸；未知/缺读数不许当成没有睡眠风险', () => {
  const sc = parseScene(JSON.stringify({ people: [
    { kind: '婴幼儿', panel: '左侧', doing: '侧身睡觉', sleep_scene: true, sleep_posture: '侧卧', sleep_posture_basis: '身体侧面贴床' },
    { kind: '婴幼儿', panel: '右侧', doing: '躺着', sleep_scene: null, sleep_posture: '未给' },
    { kind: '婴幼儿', panel: '底部', doing: '被抱着', sleep_scene: false, sleep_posture: '不适用' },
  ] })).scene;
  const rows = infantSleepReadings([sc]);
  assert.strictEqual(rows.length, 2, '明确非睡眠的婴儿不进入睡姿闸；其余面板都必须核对');
  assert.deepStrictEqual(rows.map((x) => [x.panel, x.position]), [['左侧', '侧卧'], ['右侧', '看不清']]);
});
// ★★ 2026-10-16 加（汉字声称闸的确认依据）：`text_script` —— 只报"用的是什么文字"。
check('S1g ★ `text_script` 落在闭集里 ⇒ 收下（汉字声称闸唯一的一手视觉证据）', () => {
  for (const v of ['英文', '中文', '中英混排', '其他文字', '无文字', '无法辨认']) {
    assert.strictEqual(parseScene(JSON.stringify({ text_script: v })).scene.text_script, v, v);
  }
  assert.strictEqual(parseScene('{}').scene.text_script, '未给', '缺字段要如实留「未给」');
});
check('S1h ★ 反向对照：闭集外的自由发挥（「中文和英文混着」）⇒ 落「未给」，不许当证据', () => {
  assert.strictEqual(parseScene(JSON.stringify({ text_script: '中文和英文混着' })).scene.text_script, '未给');
  assert.strictEqual(parseScene(JSON.stringify({ text_script: 'Chinese' })).scene.text_script, '未给');
});

/* ── S2 守卫：只读临时目录 ────────────────────────────────────────────── */
check('S2a 仓内路径 ⇒ **拒**（这是 §2.6 加宽那条边界唯一的执行点）', () => {
  assert.throws(() => assertTempPath('/Users/lute/project/audit_multi_content/PRD/x.png'),
    /只读临时目录/, '仓内图没被拒 —— 边界形同虚设');
});
check('S2b 反向对照：/tmp 下的图 ⇒ 放行（闸门不许成砖头）', () => {
  assert.ok(assertTempPath('/tmp/shouheng-img-abc.png').startsWith('/tmp/'));
});

/* ── S3 截断：真事故的判据 ─────────────────────────────────────────────── */
await checkAsync('S3 ★ `finish_reason=length` ⇒ **未测**，不许把半份 JSON 当读数', async () => {
  // 实测原话（2026-10-15，max_tokens=700 时）：`画面读数 JSON 解不出：Expected ',' or ']'
  // after array element in JSON at position 518` —— **报错指向"模型写坏了 JSON"，
  // 而真因是我给的额度不够**。判据必须比**内容的完整性**，不能比那句报错。
  const cut = GOOD.slice(0, 60);
  const r = await sceneRead('/tmp/x.png', {
    fetchImpl: async () => ({ ok: true, json: async () => ({
      choices: [{ finish_reason: 'length', message: { content: cut } }] }) }),
  });
  // ⚠️ 文件不存在 ⇒ 在此之前就会以「读不到那张临时图」失败；要证的是**截断那一支**，
  //    所以这里用 `fs` 真写一个临时文件（真实现读的是盘上那份字节）。
  const fs = await import('node:fs');
  const p = '/tmp/shouheng-scene-test-truncated.jpg';
  fs.writeFileSync(p, Buffer.from([0xff, 0xd8, 0xff, 0x00]));
  try {
    const r2 = await sceneRead(p, {
      fetchImpl: async () => ({ ok: true, json: async () => ({
        choices: [{ finish_reason: 'length', message: { content: cut } }] }) }),
    });
    assert.strictEqual(r2.ok, false, '截断的读数被收下了');
    assert.ok(/截断/.test(r2.error) && /未测/.test(r2.error),
      `截断的错误文案必须说清「截断 + 未测」：${r2.error}`);
  } finally { fs.unlinkSync(p); }
  assert.strictEqual(r.ok, false, '（文件不存在那一支也必须 ok:false）');
});
await checkAsync('S3b ★ 截断后只重试一次并翻倍预算，完整 JSON 才恢复读数', async () => {
  const fs = await import('node:fs');
  const p = '/tmp/shouheng-scene-test-retry.jpg';
  fs.writeFileSync(p, Buffer.from([0xff, 0xd8, 0xff, 0x00]));
  const budgets = [];
  try {
    const r = await sceneRead(p, { maxTokens: 1200, fetchImpl: async (_url, init) => {
      budgets.push(JSON.parse(init.body).max_tokens);
      return { ok: true, json: async () => ({ choices: [budgets.length === 1
        ? { finish_reason: 'length', message: { content: GOOD.slice(0, 60) } }
        : { finish_reason: 'stop', message: { content: GOOD } }] }) };
    } });
    assert.deepStrictEqual(budgets, [1200, 2400], '重试必须有界且把预算翻倍');
    assert.strictEqual(r.ok, true, `完整重试读数应通过：${JSON.stringify(r)}`);
  } finally { fs.unlinkSync(p); }
});

/* ── S4 失败面：一律 ok:false，永不抛 ─────────────────────────────────── */
await checkAsync('S4a HTTP 500 ⇒ ok:false 且带上状态码（不许静默当「没画面」）', async () => {
  const fs = await import('node:fs');
  const p = '/tmp/shouheng-scene-test-http.jpg';
  fs.writeFileSync(p, Buffer.from([0xff, 0xd8, 0xff, 0x00]));
  try {
    const r = await sceneRead(p, { fetchImpl: async () => ({ ok: false, status: 500,
      text: async () => 'boom' }) });
    assert.strictEqual(r.ok, false);
    assert.ok(/HTTP 500/.test(r.error), r.error);
  } finally { fs.unlinkSync(p); }
});
await checkAsync('S4b 网络抛错 / 超时 ⇒ ok:false 且**不抛**（画面层不许拖垮回话）', async () => {
  const fs = await import('node:fs');
  const p = '/tmp/shouheng-scene-test-net.jpg';
  fs.writeFileSync(p, Buffer.from([0xff, 0xd8, 0xff, 0x00]));
  try {
    const r = await sceneRead(p, { fetchImpl: async () => { const e = new Error('fetch failed');
      e.cause = { code: 'ENOTFOUND' }; throw e; } });
    assert.strictEqual(r.ok, false);
    assert.ok(/ENOTFOUND/.test(r.error), `错误里要看得见是哪一层断的：${r.error}`);
  } finally { fs.unlinkSync(p); }
});

/* ── S5 反向对照：合法的读数必须收下 ──────────────────────────────────── */
await checkAsync('S5a 桩返回合法 JSON ⇒ ok:true（不许因为上面那些闸门就把正常路堵死）', async () => {
  const fs = await import('node:fs');
  const p = '/tmp/shouheng-scene-test-good.jpg';
  fs.writeFileSync(p, Buffer.from([0xff, 0xd8, 0xff, 0x00]));
  try {
    const r = await sceneRead(p, { fetchImpl: async () => ({ ok: true, json: async () => ({
      choices: [{ finish_reason: 'stop', message: { content: GOOD } }] }) }) });
    assert.strictEqual(r.ok, true, `正常读数被拒了：${JSON.stringify(r)}`);
    assert.ok(sceneLine(r).includes('婴幼儿'), `一行读数没带上人物：${sceneLine(r)}`);
  } finally { fs.unlinkSync(p); }
});
check('S5b 摊给模型侧时，**空项要写明「读数里没有」**（否则模型会把"没提"当成"没有"）', () => {
  const b = sceneBlock(parseScene('{}').scene);
  assert.strictEqual((b.match(/（读数里没有）/g) ?? []).length, 7, `七项都要写：\n${b}`);
  const b2 = sceneBlock(parseScene(GOOD).scene);
  assert.ok(!/（读数里没有）/.test(b2.split('\n')[0]), '有内容的那一行不该写「读数里没有」');
});
check('S5d ★ 提示词里必须有 `text_script` 那一格与它的 4b 条（掉了 ⇒ 汉字声称闸永远拿不到确认）', () => {
  assert.ok(/"text_script"/.test(SCENE_SYSTEM), '字段表里没有 text_script');
  assert.ok(/只报用的是什么文字/.test(SCENE_SYSTEM), '4b 条（只报脚本、不报内容）掉了');
  assert.ok(/无法辨认/.test(SCENE_SYSTEM), '「看不清就写无法辨认」那条掉了 —— 会逼它猜');
});
check('S5e ★ 反向对照（跨模块）：画面层说「英文/无法辨认」⇒ **不许**被当成确认', () => {
  // 这一条钉的是下游：`ocr_claim_gate.sceneConfirms` 只认「中文 / 中英混排」，
  // 若有人把它放宽成「读数里出现任何文字相关词」，真单（画面说"认不清"）又会降不了级。
  const s1 = sceneBlock(parseScene(JSON.stringify({ text_script: '英文', visible_marks: ['有文字，认不清'] })).scene);
  const s2 = sceneBlock(parseScene(JSON.stringify({ text_script: '无法辨认' })).scene);
  assert.ok(/文字：英文/.test(s1) && /文字：无法辨认/.test(s2), `脚本要摊出来：\n${s1}\n${s2}`);
  assert.ok(!/中文|汉字/.test(s1) && !/中文|汉字/.test(s2), '英文/无法辨认不许被写成中文');
});
check('S5c 提示词里两条硬约束必须在（改提示词时不许悄悄掉）', () => {
  assert.ok(/不许判合规/.test(SCENE_SYSTEM), '「不许判合规」掉了 —— 读数会变成第二个判定者');
  assert.ok(/只写你在这张图里真看到的/.test(SCENE_SYSTEM), '「只写看得见的」掉了');
});
check('S5f ★ 睡姿提示：每个婴儿独立判睡姿；看不清不得默认仰卧', () => {
  assert.ok(/逐个判睡姿/.test(SCENE_SYSTEM), '画面读数没有逐个要求睡姿');
  assert.ok(/侧卧/.test(SCENE_SYSTEM) && /俯卧/.test(SCENE_SYSTEM), '侧卧/俯卧不在提示词中');
  assert.ok(/绝不能默认仰卧/.test(SCENE_SYSTEM), '未读到睡姿仍可能被默认成仰卧');
  assert.ok(/"sleep_posture"/.test(SCENE_SYSTEM), '结构化 schema 没有 sleep_posture');
  const block = sceneBlock(parseScene(JSON.stringify({ people: [
    { kind: '婴幼儿', panel: '右下', doing: '闭眼睡觉', sleep_scene: true, sleep_posture: '侧卧', sleep_posture_basis: '身体侧面贴床' },
  ] })).scene);
  assert.ok(/右下 · 婴幼儿 · 闭眼睡觉 · 睡眠场景：是；睡姿：侧卧 · 姿势依据：身体侧面贴床/.test(block), `逐面板侧卧及依据未传到审核输入：\n${block}`);
});
check('S5g ★ 多面板睡姿必须在最终睡眠核对项逐面板复述；只写总体结论要挡住', () => {
  const rows = [
    { image: '图 1', panel: '左侧面板', position: '侧卧', sleep_scene: true },
    { image: '图 1', panel: '右侧面板', position: '仰卧', sleep_scene: true },
  ];
  const prefix = '婴幼儿姿势：无；产品状态：无；场景关系：无；隐私：无；';
  const omitted = checkVisualChecklist(prefix + '婴儿睡眠位置：有（图 1 有婴儿睡眠场景）。', { sleepPositions: rows });
  assert.strictEqual(omitted.ok, false, '只写总括结论不该通行');
  const complete = checkVisualChecklist(prefix + '婴儿睡眠位置：有（左侧面板婴儿侧卧；右侧面板婴儿仰卧）。', { sleepPositions: rows });
  assert.strictEqual(complete.ok, true, complete.reason);
});
check('S5i ★ 逐面板睡姿：模型不写代码搬（且三条边界一条都不许松）', () => {
  const rows = [
    { image: '图 1', panel: '右上', position: '仰卧', sleep_scene: true },
    { image: '图 1', panel: '右下', position: '仰卧', sleep_scene: true },
  ];
  const prefix = '婴幼儿姿势：无；产品状态：无；场景关系：无；隐私：无；';
  const total = `${prefix}婴儿睡眠位置：有（图 1 有婴儿睡眠场景）。`;
  // 反向对照（正）：先证明**不补就红** —— 否则「补了能过」可能只是闸门本来就绿
  assert.strictEqual(checkVisualChecklist(total, { sleepPositions: rows }).ok, false,
    '只写总括的清单本来就该被挡住（这条不成立 ⇒ 本组自证是恒真）');
  const repaired = restatePerPanelSleep(total, rows);
  assert.strictEqual(repaired.added.length, 2, '两处逐面板姿势都没搬进来');
  assert.ok(/右上＝仰卧/.test(repaired.text) && /右下＝仰卧/.test(repaired.text),
    `补写没有逐面板落在同一行：\n${repaired.text}`);
  assert.strictEqual(checkVisualChecklist(repaired.text, { sleepPositions: rows }).ok, true,
    '补写后闸门仍红 ⇒ 搬的位置不对（必须在「婴儿睡眠位置」那一行内）');
  // 边界③幂等：再跑一遍一个字不加
  assert.strictEqual(restatePerPanelSleep(repaired.text, rows).added.length, 0, '第二遍又补了一次');
  // 边界①：读数没有面板 ⇒ 不补（不许凭总括姿势编出「右上/右下」）
  const noPanel = restatePerPanelSleep(total, [{ image: '图 1', panel: '', position: '仰卧' }]);
  assert.strictEqual(noPanel.text, total, '读数没有面板却补了逐面板 ⇒ 这是编');
  assert.strictEqual(checkVisualChecklist(noPanel.text,
    { sleepPositions: [{ image: '图 1', panel: '', position: '仰卧' }] }).ok, false,
    '没有面板读数时不该被补绿');
  // 边界②：核对项本身不存在 ⇒ 不补（不许替模型造出整项）
  const noItem = '婴幼儿姿势：无；产品状态：无；场景关系：无；隐私：无。';
  assert.strictEqual(restatePerPanelSleep(noItem, rows).text, noItem, '没有那一项却补了 ⇒ 这是造');
  // 边界④：模型自己写对了 ⇒ 不补（不许重复印一遍）
  const done = `${prefix}婴儿睡眠位置：有（右上仰卧；右下仰卧）。`;
  assert.strictEqual(restatePerPanelSleep(done, rows).added.length, 0, '模型已复述却被再补一遍');
});

check('S5h ★ 睡姿面板方位同义写法可核对，方位不唯一时仍拒绝猜配', () => {
  const prefix = '婴幼儿姿势：无；婴儿睡眠位置：有（逐面板核对姿势）；'
    + '产品状态：无；场景关系：无；隐私：无；';
  const rows = [
    { image: '图 1', panel: '右上', position: '仰卧', sleep_scene: true },
    { image: '图 1', panel: '右下', position: '仰卧', sleep_scene: true },
  ];
  const topBottom = prefix + '位置明细：面板 A（顶部，错误示范）＝仰卧；面板 B（底部，正确示范）＝仰卧。';
  const accepted = checkVisualChecklist(topBottom, { sleepPositions: rows });
  assert.strictEqual(accepted.ok, true, accepted.reason);

  const ambiguousRows = [
    { image: '图 1', panel: '左上', position: '仰卧', sleep_scene: true },
    { image: '图 1', panel: '右上', position: '仰卧', sleep_scene: true },
  ];
  const ambiguous = checkVisualChecklist(prefix + '位置明细：顶部面板为仰卧。', { sleepPositions: ambiguousRows });
  assert.strictEqual(ambiguous.ok, false, '两个上方面板不能被一个「顶部」短语同时匹配');
});

check('S5i ★ 仅接受报告内明确且唯一的「面板 A/B → 右上/右下」映射', () => {
  const rows = [
    { image: '图 1', panel: '右上', position: '仰卧', sleep_scene: true },
    { image: '图 1', panel: '右下', position: '仰卧', sleep_scene: true },
  ];
  const prelude = [
    '视觉核对：婴幼儿姿势=无；婴儿睡眠位置=无（面板 A＝仰卧；面板 B＝仰卧）；产品状态=无；场景关系=有（上下场景对照）；隐私=无',
    '| 面板 A（右上） | 婴幼儿仰卧 |',
    '| 面板 B（右下） | 婴幼儿仰卧 |',
  ].join('\n');
  const accepted = checkVisualChecklist(prelude, { sleepPositions: rows });
  assert.strictEqual(accepted.ok, true,
    `显式映射已唯一对应右上/右下面板，却没有识别 A/B 逐面板复述：${accepted.reason}`);

  const unmapped = checkVisualChecklist(
    '视觉核对：婴幼儿姿势=无；婴儿睡眠位置=无（面板 A＝仰卧；面板 B＝仰卧）；产品状态=无；场景关系=有；隐私=无',
    { sleepPositions: rows });
  assert.strictEqual(unmapped.ok, false, '没有建立 A/B 到画面方位的映射时不应猜配');

  const ambiguousRows = [
    { image: '图 1', panel: '左上', position: '仰卧', sleep_scene: true },
    { image: '图 1', panel: '右上', position: '仰卧', sleep_scene: true },
  ];
  const duplicateLabel = checkVisualChecklist(
    '视觉核对：婴幼儿姿势=无；婴儿睡眠位置=无（面板 A＝仰卧；面板 B＝仰卧）；产品状态=无；场景关系=有；隐私=无\n'
      + '| 面板 A（左上） | 婴幼儿仰卧 |\n| 面板 A（右上） | 婴幼儿仰卧 |',
    { sleepPositions: ambiguousRows });
  assert.strictEqual(duplicateLabel.ok, false, '一个面板标签映射到两个场景时必须拒绝');
});

check('S5j ★ 表格中睡姿结论行后的逐面板明细必须纳入同一核对项', () => {
  const rows = [
    { image: '图 1', panel: '右上', position: '仰卧', sleep_scene: true },
    { image: '图 1', panel: '右下', position: '仰卧', sleep_scene: true },
  ];
  const report = [
    '| 类别 | 结论 | 依据 |',
    '|---|---|---|',
    '| 婴幼儿姿势 | 无 | 两处均仰卧 |',
    '| 婴儿睡眠位置 | 无 | 本图睡姿符合仰卧要求 |',
    '| 面板 A（右上） | 仰卧 | 图 1 右上婴儿仰卧 |',
    '| 面板 B（右下） | 仰卧 | 图 1 右下婴儿仰卧 |',
    '| 产品状态 | 无 | 无异常 |',
    '| 场景关系 | 有 | 上下两处场景并置 |',
    '| 隐私 | 无 | 无可识别信息 |',
  ].join('\n');
  const accepted = checkVisualChecklist(report, { sleepPositions: rows });
  assert.strictEqual(accepted.ok, true,
    `视觉清单已用表格逐面板复述两处仰卧，仍被误拒：${accepted.reason}`);

  const omitted = report.replace('| 面板 B（右下） | 仰卧 | 图 1 右下婴儿仰卧 |\n', '');
  const rejected = checkVisualChecklist(omitted, { sleepPositions: rows });
  assert.strictEqual(rejected.ok, false, '缺右下面板时必须继续拒绝');
  assert.match(rejected.reason, /右下/);
});

check('S5k ★ 编号清单的后续依据行与「面板 A（上）/B（下）」必须被识别', () => {
  const rows = [
    { image: '图 1', panel: '右上', position: '仰卧', sleep_scene: true },
    { image: '图 1', panel: '右下', position: '仰卧', sleep_scene: true },
  ];
  const answer = [
    '**面板 A —— 错误示范（上，y≈ 90–440）**',
    '**面板 B —— AAP 建议示范（下，y≈ 560–1100）**',
    '## 七、视觉核对清单',
    '**1. 婴幼儿姿势：有**',
    '- 依据：面板 A 躯干蜷曲、面部呈侧向轮廓；面板 B 双臂上举、平躺（仰卧清晰）。',
    '**2. 婴儿睡眠位置：未测**',
    '- 面板 A：看不清。原因：面部呈侧向轮廓，无法判定仰卧/侧卧；画面读数记“仰卧”与实看不一致。',
    '- 面板 B：仰卧，脸与躯干正面朝上。',
    '**3. 产品状态：有**',
    '- 依据：面板 B 婴儿床结构完整、床垫平整、床内无松散物；面板 A 床面有软枕和被褥。',
    '**4. 场景关系：有**',
    '- 依据：面板 A 成人婴儿共床；面板 B 同房不同床。',
    '**5. 隐私：无**',
    '- 依据：画面为插画，无可识别真人信息。',
  ].join('\n');
  const accepted = checkVisualChecklist(answer, { sleepPositions: rows });
  assert.strictEqual(accepted.ok, true,
    `完整依据在类别后的独立条目中，且 A/B 映射明确，仍被误拒：${accepted.reason}`);

  const noBasis = answer.replace('- 依据：面板 B 婴儿床结构完整、床垫平整、床内无松散物；面板 A 床面有软枕和被褥。', '');
  const rejected = checkVisualChecklist(noBasis, { sleepPositions: rows });
  assert.strictEqual(rejected.ok, false, '移除「有」类依据后仍必须拒绝');
  assert.match(rejected.reason, /产品状态/);
});

check('S5l ★ 实际审核表用「上图/下图」逐面板写睡姿时必须通过，且结论只读本格首项', () => {
  const rows = [{ image: '图 1', panel: '右下', position: '仰卧', sleep_scene: true }];
  const answer = [
    '| 类别 | 结论 | 依据 |',
    '|---|---|---|',
    '| 婴幼儿姿势 | 无 | 上图：仰卧（脸朝上）；下图：仰卧（脸朝上） |',
    '| 婴儿睡眠位置 | 无（侧卧/俯卧） | 上图＝仰卧；下图＝仰卧。床共享风险另见“场景关系”＝有。上图婴儿在成人床仰卧；下图婴儿在独立婴儿床仰卧。 |',
    '| 产品状态 | 有 | 上图成人床有松散被褥；下图婴儿床内无松散物。 |',
    '| 场景关系 | 有 | 上图成人与婴儿同床；下图分床。 |',
    '| 隐私 | 无 | 插画中无可识别真人信息。 |',
  ].join('\n');
  const result = checkVisualChecklist(answer, { sleepPositions: rows });
  assert.strictEqual(result.ok, true,
    `上图/下图已逐面板复述右下仰卧，但仍被误拒：${result.reason}`);
  assert.strictEqual(result.found.infant_sleep_position.verdict, '无',
    '睡眠位置结论应取该格开头的「无」，不应被依据里的「场景关系＝有」覆盖');
});

check('S5m ★ 表格里写「同上」是指代上一行那句原因（2026-10-22 生产误拒），但跨结论/无前项仍拒绝', () => {
  // 病灶：真实链回答第七节写的是
  //   | 产品状态 | **未测** | 画面层未测；OCR 里无产品名/产品物件可推 |
  //   | 场景关系 | **未测** | 同上 |
  // 旧判据把「同上」当「只有 2 个字 ⇒ 没给原因」⇒ 整份合格报告被判成流程没完成，
  // 群里收到「请重新发送原图」，对方重发了四次。
  const ok = [
    '| 类别 | 结论 | 依据 |',
    '|---|---|---|',
    '| 婴幼儿姿势 | **未测** | 画面读数没跑到（画面模型 HTTP 402），本模型不接受图像输入 |',
    '| 婴儿睡眠位置 | **未测** | 同上。无法判定画面有无睡眠场景，故不写「无」 |',
    '| 产品状态 | **未测** | 画面层未测；OCR 里无产品名/产品物件可推 |',
    '| 场景关系 | **未测** | 同上 |',
    '| 隐私 | **未测** | 同上（OCR 中的人名字样只作线索，不能当画面隐私结论） |',
  ].join('\n');
  const passed = checkVisualChecklist(ok);
  assert.strictEqual(passed.ok, true, `「同上」指的是上一行那句原因，却被判成没给原因：${passed.reason}`);
  assert.strictEqual(passed.found.scene_relation.basis, '画面层未测；OCR 里无产品名/产品物件可推',
    '继承来的理由不对（不是紧挨着上一条那句）');

  // 反向对照一：上一行自己也把原因删掉 ⇒ 不许凭空造出理由，必须重新红
  const noReason = ok.replace('| 产品状态 | **未测** | 画面层未测；OCR 里无产品名/产品物件可推 |',
    '| 产品状态 | **未测** |  |');
  const red = checkVisualChecklist(noReason);
  assert.strictEqual(red.ok, false, '上一行没原因了，「同上」还被放过 ⇒ 判据被改松');
  assert.match(red.reason, /场景关系/);

  // 反向对照二：结论不同却写「同上」⇒ 含义不明，宁可判红也不猜
  const crossVerdict = ok.replace('| 产品状态 | **未测** | 画面层未测；OCR 里无产品名/产品物件可推 |',
    '| 产品状态 | **有** | 画面里床头柜上放着倒置的奶瓶 |');
  assert.strictEqual(checkVisualChecklist(crossVerdict).ok, false,
    '跨结论的「同上」被当成继承 ⇒ 判据太松');

  // 反向对照三：五类全写「未测」、一个原因都不给 ⇒ 仍必须红（这条是本组的地基）
  assert.strictEqual(checkVisualChecklist(
    '婴幼儿姿势=未测；婴儿睡眠位置=未测；产品状态=未测；场景关系=未测；隐私=未测').ok, false,
  '五类都只写「未测」不给原因也被放过');
});

check('S6a ★ 容器朝向：闭集收下、同义归一、闭集外**不猜**（2026-10-21「奶瓶倒着放」）', () => {

  const mk = (o) => parseScene(JSON.stringify({ products: [{ what: '白色小奶瓶', orientation: o }] })).scene.products[0].orientation;
  assert.strictEqual(mk('倒置'), '倒置', '闭集内的值必须收下');
  assert.strictEqual(mk('口朝下'), '倒置', '同义写法「口朝下」要归一到倒置（否则等于白读）');
  assert.strictEqual(mk('歪歪扭扭'), '未给', '闭集外的说法必须落未给 —— 猜出来的朝向比漏掉更坏');
  assert.strictEqual(mk(''), '未给', '没给朝向 ⇒ 未给（不许默认成正放）');
});
check('S6b ★ 渲染：物品行带「朝向：…」，未给的不印（不把没读到的东西印成事实）', () => {
  const s1 = sceneBlock(parseScene(JSON.stringify({ products: [{ what: '白色小奶瓶', orientation: '倒置' }] })).scene);
  const s2 = sceneBlock(parseScene(JSON.stringify({ products: [{ what: '婴儿床' }] })).scene);
  assert.ok(/白色小奶瓶（朝向：倒置）/.test(s1), '物品行没印朝向：' + s1);
  assert.ok(!/朝向/.test(s2), '未给的朝向被印出来了：' + s2);
});
check('S6c ★ abnormalContainers：只挑「容器 ＋ 姿态异常」，非容器/正放都不算', () => {
  const sc = parseScene(JSON.stringify({ products: [
    { what: '白色小奶瓶', orientation: '口朝下' },
    { what: '保温杯', orientation: '正放' },
    { what: '木制婴儿床', orientation: '侧放' },
  ] })).scene;
  const got = abnormalContainers(sc);
  assert.strictEqual(got.length, 1, '应只挑出奶瓶，实得 ' + JSON.stringify(got));
  assert.strictEqual(got[0].orientation, '倒置', '同义归一没生效');
});
check('S6d ★ 提示词：容器必列 ＋ orientation 闭集必须在（改提示词不许悄悄掉）', () => {
  assert.ok(/容器类物件/.test(SCENE_SYSTEM), '「容器类物件必须逐个写进 products」那条掉了 —— 读数会继续时有时无');
  assert.ok(/orientation/.test(SCENE_SYSTEM), '字段表里没有 orientation');
  assert.ok(/看不清\"，不许猜|不许猜/.test(SCENE_SYSTEM), '「看不清就写看不清，不许猜」那条掉了');
});
const nFail = results.filter((r) => !r.ok).length;
for (const r of results) console.log(`  ${r.ok ? '✅' : '❌'} ${r.id}${r.ok ? '' : `  ← ${r.detail}`}`);
console.log(`\n${nFail ? '❌' : '✅'} scene ${results.length - nFail}/${results.length} 项通过`
  + '（全部注入桩：**一个字节都没发出去**）');
process.exit(nFail ? 1 : 0);
