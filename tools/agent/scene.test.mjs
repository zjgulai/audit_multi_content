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
import { parseScene, sceneBlock, sceneLine, assertTempPath, sceneRead, SCENE_SYSTEM } from './scene.mjs';

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
  assert.strictEqual((b.match(/（读数里没有）/g) ?? []).length, 6, `六项都要写：\n${b}`);
  const b2 = sceneBlock(parseScene(GOOD).scene);
  assert.ok(!/（读数里没有）/.test(b2.split('\n')[0]), '有内容的那一行不该写「读数里没有」');
});
check('S5c 提示词里两条硬约束必须在（改提示词时不许悄悄掉）', () => {
  assert.ok(/不许判合规/.test(SCENE_SYSTEM), '「不许判合规」掉了 —— 读数会变成第二个判定者');
  assert.ok(/只写你在这张图里真看到的/.test(SCENE_SYSTEM), '「只写看得见的」掉了');
});

const nFail = results.filter((r) => !r.ok).length;
for (const r of results) console.log(`  ${r.ok ? '✅' : '❌'} ${r.id}${r.ok ? '' : `  ← ${r.detail}`}`);
console.log(`\n${nFail ? '❌' : '✅'} scene ${results.length - nFail}/${results.length} 项通过`
  + '（全部注入桩：**一个字节都没发出去**）');
process.exit(nFail ? 1 : 0);
