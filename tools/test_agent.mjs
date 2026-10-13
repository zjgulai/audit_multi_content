/**
 * test_agent.mjs —— 守衡内核离线测试
 *
 * 用合成事件跑完整链路（解析 → 记忆 → 工具 → LLM → 回复），不依赖真人 @。
 * 为什么必须做这个：入向链路验证时我用「盯日志」等真人动作，连吃两次空测。
 * 内核的正确性不该由别人的手速决定。
 *
 * 用法：node test_agent.mjs [--live]
 *   默认只测纯本地逻辑（不花 token）；--live 额外跑一次真实 LLM 对话。
 */
import assert from 'node:assert';

// ★ 2026-10-05 现场踩到的坑（§2.4.4 那个形状）：**跑一次自证，往 Owner 的真实飞书表里写了两行。**
//   原因：`runSubmissionGate` 里那段「保证落表」对**测试桩**也照跑不误 ——
//   单测里 `chainRunner` 返回一句假的 `结论：REVIEW`，就真在群里那张表上建了一行。
//   两条防线，缺一条都不算修好：
//     ① 这里拉闸（就算谁漏传了桩，也写不进真表）；
//     ② 单测/子进程一律显式传 `publishRunner` / `chainRunner` 桩。
process.env.SHOUHENG_REVIEW_TABLE = 'off';
import fs from 'node:fs';
import * as feishu from './agent/feishu.mjs';
import { executeTool, runtimeContext, TOOL_SCHEMAS } from './agent/tools.mjs';

const LIVE = process.argv.includes('--live');
let pass = 0, fail = 0;
const ok  = (name, extra = '') => { pass++; console.log(`  ✅ ${name}${extra ? '  ' + extra : ''}`); };
const bad = (name, e) => { fail++; console.log(`  ❌ ${name}\n       ${e}`); };
const t = async (name, fn) => { try { await fn(); ok(name); } catch (e) { bad(name, e.message); } };

/**
 * 数一个模板字符串常量里**未转义**的反引号个数（开头的定界符不算）。
 * 用途见第 10 组：09-22 那次事故是「往人设里写行内代码忘了转义」，
 * 而判据一度写成「渲染结果里不许有反引号」—— 那会把**正确**的转义写法也判红。
 */
function unescapedBackticksInTemplate(src, constName) {
  const i = src.indexOf(`export const ${constName}`);
  if (i < 0) return -1;                       // 找不到常量本身就是错，返回负数让断言炸出来
  const isEscaped = (k) => {
    let bs = 0;
    for (let j = k - 1; j >= 0 && src[j] === '\\'; j--) bs++;
    return bs % 2 === 1;
  };
  // 模板的收尾是「第一个后面跟着分号的未转义反引号」，**不能假设它前面有换行**
  // （实测就是 `…已经生效」。**\`;` 收在一行里 —— 按 '\n\`;' 找会找不到，
  //  于是整段 body 一路吃到文件尾，把后面几个模板字面量全算进来，报出 11 个假阳性）。
  const open = (() => { for (let k = i; k < src.length; k++) if (src[k] === '`' && !isEscaped(k)) return k; return -1; })();
  if (open < 0) return -1;
  let n = 0, close = -1;
  for (let k = open + 1; k < src.length; k++) {
    if (src[k] !== '`' || isEscaped(k)) continue;
    if (/^\s*;/.test(src.slice(k + 1, k + 4))) { close = k; break; }
    n++;
  }
  return close < 0 ? -1 : n;                  // 没有收尾 → 源码本身已坏，报 -1 让断言红
}

console.log('\n═══ 1. mention 还原（守衡能不能知道谁在跟它说话）═══');

await t('还原 @ 占位符为真名', () => {
  const raw = '@_user_1 你好，帮我看看';
  const mentions = [{ key: '@_user_1', name: '李倩怡', id: { open_id: 'ou_test_lee' } }];
  const { display, mentions: resolved } = feishu.resolveMentions(raw, mentions);
  assert.strictEqual(display, '@李倩怡 你好，帮我看看', `实际得到 ${display}`);
  assert.strictEqual(resolved[0].name, '李倩怡');
  assert.strictEqual(resolved[0].openId, 'ou_test_lee');
});

await t('多个 @ 同时还原', () => {
  const raw = '@_user_1 @_user_2 你们看下';
  const mentions = [
    { key: '@_user_1', name: '张三', id: { open_id: 'ou_a' } },
    { key: '@_user_2', name: '李四', id: { open_id: 'ou_b' } },
  ];
  const { display } = feishu.resolveMentions(raw, mentions);
  assert.strictEqual(display, '@张三 @李四 你们看下', `实际得到 ${display}`);
});

await t('识别「@ 的是守衡」（决定群聊是否响应）', () => {
  const yes = feishu.resolveMentions('@_user_1 hi', [{ key: '@_user_1', name: '守衡', id: { open_id: 'cli_aa2243de0438dcd7' } }]);
  assert.strictEqual(feishu.isBotMentioned(yes.mentions), true);
  const no = feishu.resolveMentions('@_user_1 hi', [{ key: '@_user_1', name: '李倩怡', id: { open_id: 'ou_x' } }]);
  assert.strictEqual(feishu.isBotMentioned(no.mentions), false);
});

await t('剥掉 @守衡 本身，只留问题', () => {
  const { display, mentions } = feishu.resolveMentions(
    '@_user_1 你是谁？', [{ key: '@_user_1', name: '守衡', id: { open_id: 'cli_aa2243de0438dcd7' } }]);
  assert.strictEqual(feishu.stripBotMention(display, mentions), '你是谁？');
});

await t('@守衡 与其他 @ 混排时只剥自己', () => {
  const { display, mentions } = feishu.resolveMentions(
    '@_user_1 @_user_2 请回答', [
      { key: '@_user_1', name: '守衡', id: { open_id: 'cli_aa2243de0438dcd7' } },
      { key: '@_user_2', name: '李倩怡', id: { open_id: 'ou_lee' } },
    ]);
  assert.strictEqual(feishu.stripBotMention(display, mentions), '@李倩怡 请回答');
});

console.log('\n═══ 2. 工具层 ═══');

await t('now 工具返回完整北京时间', async () => {
  const r = await executeTool('now', '{}');
  assert.ok(r.ok, r.error);
  // 必须同时含日期、时间、星期 —— 少任何一项都说明格式化不可靠
  assert.ok(/^\d{4}-\d{2}-\d{2}$/.test(r.result.date), `date 格式错：${r.result.date}`);
  assert.ok(/^\d{2}:\d{2}:\d{2}$/.test(r.result.time), `time 格式错：${r.result.time}`);
  assert.ok(/星期/.test(r.result.weekday), `weekday 错：${r.result.weekday}`);
  assert.strictEqual(r.result.beijing_time, `${r.result.date} ${r.result.time} ${r.result.weekday}`);
});

await t('工作区列举可用', async () => {
  runtimeContext.chatId = 'oc_test'; runtimeContext.chatType = 'group';
  const r = await executeTool('list_workspace', '{}');
  assert.ok(r.ok && r.result.entries.length > 0, JSON.stringify(r.result).slice(0, 200));
});

await t('读工作区内文件成功', async () => {
  const r = await executeTool('read_text_file', JSON.stringify({ rel_path: 'PMO/守衡-链路打通确认.md' }));
  assert.ok(r.ok && r.result.content.includes('im.message.receive_v1'), JSON.stringify(r.result).slice(0, 200));
});

await t('路径逃逸被拒绝（安全）', async () => {
  const r = await executeTool('read_text_file', JSON.stringify({ rel_path: '../../../../etc/passwd' }));
  assert.ok(r.ok && r.result.error, '应该返回错误而不是内容');
  assert.ok(/拒绝访问/.test(r.result.error), `实际：${r.result.error}`);
});

await t('写操作命令被白名单拒绝（安全）', async () => {
  for (const c of ['rm -rf /tmp/x', 'curl http://evil.com', 'git push', 'echo hi > /tmp/f', 'ls | grep a']) {
    const r = await executeTool('run_readonly_command', JSON.stringify({ command: c }));
    assert.ok(r.ok && r.result.error, `命令 "${c}" 本应被拒，实际：${JSON.stringify(r.result).slice(0, 120)}`);
  }
});

await t('只读命令可执行', async () => {
  // 注意：这里不用 git —— 本工作区不是 git 仓库（已实测确认）。
  // 测试必须依赖工作区真实存在的性质，否则测的是环境不是代码。
  const r = await executeTool('run_readonly_command', JSON.stringify({ command: 'wc -l PMO/守衡-链路打通确认.md' }));
  assert.ok(r.ok && !r.result.error, JSON.stringify(r.result).slice(0, 300));
  assert.ok(/\d+/.test(r.result.stdout), `stdout 里应有行数，实际：${r.result.stdout}`);
});

await t('非 git 仓库时 git 命令的报错被结构化吞住', async () => {
  const r = await executeTool('run_readonly_command', JSON.stringify({ command: 'git log --oneline -3' }));
  // 命令在白名单内，但环境不是仓库 —— 必须返回结构化错误，不能让异常冒到外面
  assert.ok(r.ok, '工具本身不应抛出');
  assert.ok(r.result.error || r.result.stdout !== undefined);
});

console.log('\n═══ 1b. 空输出不许被读成「0 命中」（2026-09-22 事故，反向对照）═══');

/*
 * 事故原样：守衡执行 `grep -rl <PRD 的 wiki token> .` —— 全仓递归，含 node_modules/、
 * .git/、skills/ 下 777 个压缩包。实测**超过 60 秒都跑不完**（我用 harness 的 60 秒上限
 * 复现过，是被 SIGTERM 杀掉的），而工具只有 15 秒 → 被 timezone 杀掉 →
 * 返回体 { error: "Command failed: …", stdout: "" } → **它只读了 stdout 是空的**，
 * 于是对群里说「我用这个 token 搜了一遍，0 命中」。
 * 真值：那个 token 就在工作区两个文件里。
 *
 * 下面每一条都对着那次误判的一个环节。
 */

await t('超时被杀的返回体里**没有 stdout 这个键** —— 空字符串无从被读成「0 命中」', async () => {
  process.env.SHOUHENG_RO_TIMEOUT_MS = '1';   // 1ms：bash 启动本身都超过它，必定超时
  let r;
  try {
    r = await executeTool('run_readonly_command', JSON.stringify({ command: 'grep -rn 守衡 PMO' }));
  } finally {
    delete process.env.SHOUHENG_RO_TIMEOUT_MS;
  }
  assert.ok(r.ok, '工具本身不应抛出');
  assert.strictEqual(r.result.status, 'timeout', `本应判为超时，实际：${JSON.stringify(r.result).slice(0, 200)}`);
  assert.ok(!('stdout' in r.result),
    `超时时返回体里不许有 stdout —— 空 stdout 会被读成「扫完了、没命中」。实际：${JSON.stringify(r.result).slice(0, 200)}`);
  assert.ok(/未测/.test(r.result.note), `note 里必须写出「未测」：${r.result.note}`);
  assert.ok(/不是「0 命中」/.test(r.result.note), 'note 必须明着堵住「0 命中」这个读法');
});

await t('引发事故的那条命令，在跑之前就被护栏拒绝', async () => {
  const r = await executeTool('run_readonly_command',
    JSON.stringify({ command: 'grep -rl NB55wAq8liEOdKkquL2cgtPEnmg .' }));
  assert.ok(r.ok && r.result.status === 'rejected',
    `本应被护栏拒绝，实际：${JSON.stringify(r.result).slice(0, 200)}`);
  // 它必须给出**下一步**，不能只说「不行」
  assert.ok(/search_workspace/.test(r.result.note), '拒绝时必须给替代路径');
});

await t('护栏不许把正常用法也拦掉（点名子目录的 grep 要放行）', async () => {
  const r = await executeTool('run_readonly_command',
    JSON.stringify({ command: 'grep -rn 守衡 PMO/守衡-链路打通确认.md' }));
  assert.ok(r.ok, '工具本身不应抛出');
  assert.notStrictEqual(r.result.status, 'rejected',
    `点名到具体文件不该被拦，实际：${JSON.stringify(r.result).slice(0, 200)}`);
});

await t('白名单只放行 lark_find.py 的**读**子命令，下载类一律拒绝（§2.6 红线）', async () => {
  // 2026-09-22 起守衡能用 `python3 tools/lark_find.py readdoc <token>` 读飞书文档正文 ——
  // 这符合 §2.6 红线（「读」允许，「取走附件」禁止）。这条断言就是那条红线的执行点：
  // 任何人往白名单里塞 download / medias，这里立刻红。
  for (const c of ['python3 tools/lark_find.py download abc',
                   'python3 tools/lark_find.py medias abc',
                   'python3 tools/lark_find.py export abc']) {
    const r = await executeTool('run_readonly_command', JSON.stringify({ command: c }));
    assert.strictEqual(r.result.status, 'rejected',
      `"${c}" 必须被拒（红线：飞书内容禁止下载），实际：${JSON.stringify(r.result).slice(0, 200)}`);
  }
});

await t('search_workspace 找得到那个 token（对事故的**真阳性**对照）', async () => {
  const r = await executeTool('search_workspace', JSON.stringify({ keyword: 'NB55wAq8liEOdKkquL2cgtPEnmg' }));
  assert.ok(r.ok && r.result.status === 'ok', JSON.stringify(r.result).slice(0, 200));
  assert.ok(r.result.matches >= 1,
    `那次说「0 命中」，真值是至少 1 —— 实际 ${r.result.matches}（扫了 ${r.result.searched_files} 个文件）`);
  assert.strictEqual(r.result.stopped_early, false, '整仓检索不该被截断，否则「0 命中」不成立');
});

await t('search_workspace：0 命中必须带分母，且分母为 0 时不算数', async () => {
  // 关键词必须**当场生成**：写死的字符串会出现在本测试文件自己里，
  // 于是「一定不存在」变成「一定存在」—— 这正是那类「假阴性/假阳性都在骗人」的坑。
  const ghost = `zz${Date.now()}x${Math.random().toString(36).slice(2)}q`;
  const r = await executeTool('search_workspace', JSON.stringify({ keyword: ghost }));
  assert.ok(r.result.searched_files > 0, '分母必须大于 0，否则「没找到」是未测不是 0');
  assert.strictEqual(r.result.matches, 0, `不该命中，实际 ${r.result.matches}`);
  assert.ok(/分母/.test(r.result.note), `0 命中时要说清分母撑着：${r.result.note}`);
});

await t('search_workspace：扫不完时必须说「未测」，不许下「没找到」的结论', async () => {
  const ghost = `zz${Date.now()}x${Math.random().toString(36).slice(2)}q`;
  const r = await executeTool('search_workspace', JSON.stringify({ keyword: ghost, max_files: 3 }));
  assert.strictEqual(r.result.stopped_early, true, '上限这么小必须被截断');
  assert.ok(/未测/.test(r.result.note), `截断时 note 必须说未测：${r.result.note}`);
  // 判据用的是**扫完时才出现的那句话**，而不是「0 命中」三个字 ——
  // 后者会出现在「不许说成 0 命中」这句提示语里，拿它当判据等于自己判自己。
  assert.ok(!/有分母撑着/.test(r.result.note),
    `截断时不许给出「0 命中」的结论句：${r.result.note}`);
});

await t('未知工具给出结构化错误而非崩溃', async () => {
  const r = await executeTool('no_such_tool', '{}');
  assert.strictEqual(r.ok, false);
  assert.ok(/未知工具/.test(r.error));
});

await t('坏 JSON 参数不崩溃', async () => {
  const r = await executeTool('now', '{bad json');
  assert.strictEqual(r.ok, false);
  assert.ok(/JSON/.test(r.error));
});

console.log('\n═══ 3. markdown → 飞书富文本 ═══');

await t('代码块被识别为 code_block（不是一堆星号）', () => {
  const nodes = feishu.__test_mdToPostNodes('说明：\n```js\nconst a = 1;\n```\n结束');
  const flat = JSON.stringify(nodes);
  assert.ok(flat.includes('code_block'), flat.slice(0, 300));
  assert.ok(flat.includes('const a = 1;'), flat.slice(0, 300));
});

await t('粗体与行内代码转成样式节点', () => {
  const nodes = feishu.__test_mdToPostNodes('这是 **重点** 和 `code`');
  const flat = JSON.stringify(nodes);
  assert.ok(flat.includes('"bold"'), flat.slice(0, 300));
  assert.ok(flat.includes('code_inline'), flat.slice(0, 300));
});

await t('未闭合的代码块不吞内容', () => {
  const nodes = feishu.__test_mdToPostNodes('前\n```\n没闭合的内容');
  assert.ok(JSON.stringify(nodes).includes('没闭合的内容'));
});

console.log('\n═══ 4. 记忆压缩的切点安全性（防 API 400）═══');

await t('压缩切点不拆散 tool_calls 与其结果', async () => {
  const mem = await import('./agent/memory.mjs');
  // 构造一段含工具调用的历史：user → assistant(tool_calls) → tool → assistant
  const sess = { key: 'test_boundary', messages: [], summary: '', messageCount: 0 };
  for (let i = 0; i < 6; i++) {
    sess.messages.push({ role: 'user', content: `问题 ${i}` });
    sess.messages.push({ role: 'assistant', content: '', tool_calls: [{ id: `c${i}`, type: 'function', function: { name: 'now', arguments: '{}' } }] });
    sess.messages.push({ role: 'tool', tool_call_id: `c${i}`, content: '{"ok":true}' });
    sess.messages.push({ role: 'assistant', content: `回答 ${i}` });
  }
  const compacted = await mem.compact(sess, async () => '摘要', 5, 5);  // 保留 5 轮 / 超过 5 条触发
  assert.strictEqual(compacted, true, '本应发生压缩');
  // 留下部分的第一条必须是 user —— 否则说明切在了 tool_calls/工具结果中间
  assert.strictEqual(sess.messages[0].role, 'user',
    `切点错误，留首条是 ${sess.messages[0].role}；应回退到 user 边界`);
  // 且留下的序列里，每个 assistant(tool_calls) 后面必须紧跟同数量 tool
  for (let i = 0; i < sess.messages.length; i++) {
    const m = sess.messages[i];
    if (m.role === 'assistant' && m.tool_calls?.length) {
      for (let k = 0; k < m.tool_calls.length; k++) {
        assert.strictEqual(sess.messages[i + 1 + k]?.role, 'tool',
          `第 ${i} 条 assistant(tool_calls) 之后第 ${k + 1} 条不是 tool`);
      }
    }
  }
});

await t('无法回退到边界时放弃压缩而非产生坏序列', async () => {
  const mem = await import('./agent/memory.mjs');
  const sess = { key: 'test_noboundary', messages: [], summary: '', messageCount: 0 };
  // 全是 tool 消息，没有 user 可作为切点
  for (let i = 0; i < 40; i++) sess.messages.push({ role: 'tool', tool_call_id: `t${i}`, content: 'x' });
  const compacted = await mem.compact(sess, async () => '摘要', 5, 5);  // 保留 5 轮 / 超过 5 条触发
  assert.strictEqual(compacted, false, '找不到安全切点时应放弃压缩');
  assert.strictEqual(sess.messages.length, 40, '放弃压缩时不应丢消息');
});

await t('纪要为空时必须放弃压缩（不许「删了历史、什么都没留」）', async () => {
  // ★ 2026-09-22 真事故：`summarize()` 在推理预算被吃光时返回空串，
  //   `compact()` 把它当成纪要写下去，**然后把旧对话全删了**。
  //   盘上的读数：三个会话的 `summary` 全是 0 长度，而日志印了 8 次「保留 N 轮 + 纪要」。
  //   代价不是「这次没压缩」，是「守衡确信地不记得」—— 下一轮它看到的是断头的历史。
  //
  //   这一条守的是**最后一道闸**：它与 summarize 的行为无关，故意的。
  //   喂三个空法（空串 / 纯空白 / undefined），一个都不许通过。
  const mem = await import('./agent/memory.mjs');
  for (const [name, empty] of [['空串', ''], ['纯空白', '\n\n   \t\n'], ['undefined', undefined]]) {
    const sess = { key: `test_emptysummary_${name}`, messages: [], summary: '', messageCount: 0 };
    for (let i = 0; i < 12; i++) {
      sess.messages.push({ role: 'user', content: `问题 ${i}` });
      sess.messages.push({ role: 'assistant', content: `回答 ${i}` });
    }
    const before = sess.messages.length;
    const compacted = await mem.compact(sess, async () => empty, 5, 5);
    assert.strictEqual(compacted, false, `返回${name}时应放弃压缩，实际 compacted=${compacted}`);
    assert.strictEqual(sess.messages.length, before, `返回${name}时不许丢消息（原 ${before} 条）`);
    assert.strictEqual(sess.summary, '', `返回${name}时不许把空白写进纪要`);
  }
  // 反面：非空纪要**必须**照常压缩 —— 否则上面那条可能是「压缩整个坏了」而全绿。
  const sess2 = { key: 'test_emptysummary_ok', messages: [], summary: '', messageCount: 0 };
  for (let i = 0; i < 12; i++) {
    sess2.messages.push({ role: 'user', content: `问题 ${i}` });
    sess2.messages.push({ role: 'assistant', content: `回答 ${i}` });
  }
  const okCompacted = await mem.compact(sess2, async () => '真的纪要', 5, 5);
  assert.strictEqual(okCompacted, true, '有纪要时必须照常压缩（反向对照）');
  assert.strictEqual(sess2.summary, '真的纪要', '纪要应写进去');
});

// ─────────────────────────────────────────────────────────────────────────────
// 5. 查名字的降级链
//
// 背景：2026-09-16 真实群聊里，守衡收到消息却查不出「谁在说话」——
// 它走的是通讯录接口，而本应用没开 contact 权限，返回 99991672。
// 原来的 getUserName 用 `catch { return null }` 把这个原因吃掉了，
// 上层只能看到「查不到」，无法区分「人不在可见范围」还是「接口没权限」。
//
// 本组测试打的是真飞书接口（用真凭证），因为只有真接口才会暴露权限边界：
// 假 mock 会永远返回成功，测不出这个 bug。
// ─────────────────────────────────────────────────────────────────────────────
console.log('\n═══ 5. 查名字的降级链（真接口，验权限边界）═══');

let liveChatId = null;
{
  const { config } = await import('./agent/config.mjs');
  liveChatId = config.allowedChats?.[0] ?? null;
  if (!liveChatId) {
    // 配置里是「不限」时没有群 id，但降级链必须有真群才能验证。
    // 这里让测试自己通过 API 发现群，而不是硬编码一个 id：
    // 硬编码的 id 在换群/换环境后会静默失效，测试会假装通过。
    try {
      const r = await feishu.client.im.chat.list({ params: { page_size: 50 } });
      const chats = r?.data?.items ?? [];
      const pick = chats.find((c) => /守衡|内容治理/.test(c.name ?? '')) ?? chats[0];
      liveChatId = pick?.chat_id ?? null;
      if (liveChatId) console.log(`  （自动发现群：${pick.name ?? '(无名)'} → ${liveChatId}）`);
    } catch (e) {
      console.log(`  （自动发现群失败：${e?.response?.data?.msg ?? e.message}）`);
    }
  }
}
if (!liveChatId) {
  console.log('  ⚠ 找不到任何群，第 5 组无法验证真接口 —— 这不算通过，请检查应用是否在群里');
}

await t('群成员接口可用（降级链的第一条路）', async () => {
  if (!liveChatId) throw new Error('没有配置 allowedChats，跳过真接口验证');
  const members = await feishu.listMembers(liveChatId, 100);
  assert.ok(Array.isArray(members), `期望数组，实际 ${JSON.stringify(members).slice(0, 200)}`);
  assert.ok(members.length > 0, '群成员列表为空，无法验证后续降级');
  assert.ok(members.every((m) => m.name && m.openId), '成员项必须同时有 name 和 openId');
});

await t('带 chatId 时，同群成员能查到真名（不需要通讯录权限）', async () => {
  if (!liveChatId) throw new Error('没有配置 allowedChats，跳过');
  const members = await feishu.listMembers(liveChatId, 100);
  const someone = members[0];
  const r = await feishu.getUserName(someone.openId, liveChatId);
  assert.strictEqual(r.name, someone.name, `期望 ${someone.name}，实际 ${r.name}`);
  assert.strictEqual(r.source, 'chat_member', `应命中群成员这条路，实际 source=${r.source}`);
});

await t('不带 chatId 且通讯录无权限时，如实返回原因而不是静默 null', async () => {
  const r = await feishu.getUserName('ou_00000000000000000000000000000000', null);
  assert.strictEqual(r.name, null, '不存在的 open_id 不应查到名字');
  assert.strictEqual(r.source, 'none');
  // 关键：reason 必须非空。若这里是 null/undefined，说明又退回了静默吞异常。
  assert.ok(r.reason, `必须带出失败原因，实际 reason=${r.reason}`);
  assert.ok(
    /权限|code=|通讯录/.test(r.reason),
    `原因应可读且指向真实原因，实际：${r.reason}`,
  );
});

await t('lookup_user 工具能返回 source，并带上「别编称呼」的提示', async () => {
  const { executeTool, runtimeContext } = await import('./agent/tools.mjs');
  if (!liveChatId) throw new Error('没有配置 allowedChats，跳过');
  const members = await feishu.listMembers(liveChatId, 100);
  runtimeContext.chatId = liveChatId;               // 模拟真实处理时的注入
  const r = await executeTool('lookup_user', JSON.stringify({ open_id: members[0].openId }));
  assert.ok(r.ok, JSON.stringify(r).slice(0, 200));
  assert.strictEqual(r.result.name, members[0].name);
  assert.strictEqual(r.result.source, 'chat_member', `实际 source=${r.result.source}`);
  runtimeContext.chatId = null;
});

await t('查不到时，工具返回的提示明确禁止模型编造称呼', async () => {
  const { executeTool, runtimeContext } = await import('./agent/tools.mjs');
  runtimeContext.chatId = null;                     // 强制走通讯录那条失败路
  const r = await executeTool('lookup_user', JSON.stringify({ open_id: 'ou_00000000000000000000000000000000' }));
  assert.ok(r.ok, '工具本身不应抛出');
  assert.ok(r.result.error, '应返回 error 字段');
  assert.ok(r.result.reason, '应带出 reason');
  assert.ok(/不要猜测|不要编造/.test(r.result.hint ?? ''), `hint 缺失或未禁止编造：${r.result.hint}`);
});

// ─────────────────────────────────────────────────────────────────────────────
// 6. 去重表落盘失败时的行为
//
// 背景：flushSeen 原来写成 `catch {}` —— 写盘失败被完全吞掉。
// 这个表决定「重启后是否重复回话」，它一旦静默丢失，表现是守衡对同一条消息
// 回两次，且日志里没有任何线索。
// 这段必须能注入路径才测得了，所以 STATE_DIR 支持 SHOUHENG_STATE_DIR 覆盖。
// ─────────────────────────────────────────────────────────────────────────────
console.log('\n═══ 6. 去重表落盘失败不静默 ═══');

await t('写盘失败时不清 seenDirty，并打出一条警告', async () => {
  const fs = await import('node:fs');
  const os = await import('node:os');
  const p = await import('node:path');

  // 让 STATE_DIR 指向一个「存在但不可写」的目录：
  // 用文件冒充目录，任何写入都会 ENOTDIR —— 比 chmod 更可靠，且不受 root 影响。
  const tmp = fs.mkdtempSync(p.join(os.tmpdir(), 'shouheng-test-'));
  const fakeDir = p.join(tmp, 'not-a-dir');
  fs.writeFileSync(fakeDir, 'x');
  process.env.SHOUHENG_STATE_DIR = fakeDir;

  const warnings = [];
  const origWarn = console.warn;
  console.warn = (...a) => warnings.push(a.join(' '));

  let mod;
  try {
    // 带 cache-buster，确保重新读取 SHOUHENG_STATE_DIR
    mod = await import(`./agent/agent.mjs?failtest=${Date.now()}`);
    mod.alreadyHandled('om_test_flush_fail_1');
    mod.flushSeen();                 // 第一次：应失败并报一次
    mod.flushSeen();                 // 第二次：不应重复刷屏
  } finally {
    console.warn = origWarn;
    delete process.env.SHOUHENG_STATE_DIR;
    fs.rmSync(tmp, { recursive: true, force: true });
  }

  const seenWarnings = warnings.filter((w) => w.includes('[seen]'));
  assert.strictEqual(seenWarnings.length, 1,
    `应恰好报 1 次（不刷屏），实际 ${seenWarnings.length} 次：${JSON.stringify(seenWarnings)}`);
  assert.ok(/落盘失败/.test(seenWarnings[0]), `警告内容不对：${seenWarnings[0]}`);
  assert.ok(/重复回话/.test(seenWarnings[0]), `警告应说明后果：${seenWarnings[0]}`);
});

await t('恢复可写后重新落盘，并报一次恢复', async () => {
  const fs = await import('node:fs');
  const os = await import('node:os');
  const p = await import('node:path');

  const tmp = fs.mkdtempSync(p.join(os.tmpdir(), 'shouheng-test2-'));
  const fakeDir = p.join(tmp, 'not-a-dir');
  fs.writeFileSync(fakeDir, 'x');
  process.env.SHOUHENG_STATE_DIR = fakeDir;

  const warnings = [];
  const origWarn = console.warn;
  console.warn = (...a) => warnings.push(a.join(' '));

  try {
    const mod = await import(`./agent/agent.mjs?recover=${Date.now()}`);
    mod.alreadyHandled('om_test_recover_1');
    mod.flushSeen();                                  // 失败
    fs.rmSync(fakeDir, { force: true });              // 清掉障碍，让路径可写
    fs.mkdirSync(fakeDir, { recursive: true });
    mod.flushSeen();                                  // 应成功并报恢复
  } finally {
    console.warn = origWarn;
    delete process.env.SHOUHENG_STATE_DIR;
    fs.rmSync(tmp, { recursive: true, force: true });
  }

  const fail = warnings.filter((w) => w.includes('[seen]'));
  assert.ok(fail.some((w) => /落盘失败/.test(w)), '应报过失败');
  assert.ok(fail.some((w) => /恢复落盘/.test(w)),
    `恢复后应报一次，实际警告：${JSON.stringify(fail)}`);
});

await t('状态目录被同名文件占位时，进程仍能启动（不许 EEXIST/ENOTDIR 崩掉）', async () => {
  // 必须在子进程里测：修复前这个场景会直接杀掉进程，
  // 在本进程里测的话「崩溃」会被误读成「测试没通过」，而不是「产品起不来」。
  const { spawnSync } = await import('node:child_process');
  const fs = await import('node:fs');
  const os = await import('node:os');
  const p = await import('node:path');

  const tmp = fs.mkdtempSync(p.join(os.tmpdir(), 'shouheng-boot-'));
  const fakeDir = p.join(tmp, 'not-a-dir');
  fs.writeFileSync(fakeDir, 'x');           // 用文件占住「状态目录」这个路径

  const r = spawnSync(process.execPath, ['--input-type=module', '-e',
    // 用绝对路径：原来写的是 './tools/agent/agent.mjs'，那是相对 cwd 的，
    // 于是这个测试**只在仓库根目录下运行才成立** —— 在 tools/ 里跑就会
    // 报 ERR_MODULE_NOT_FOUND（找不到 tools/tools/agent/agent.mjs）。
    // 子进程加载哪个文件是测试的固有属性，不该取决于你从哪敲的命令。
    `await import(${JSON.stringify(new URL('./agent/agent.mjs', import.meta.url).href)}); console.log('BOOT_OK');`,
  ], {
    cwd: process.cwd(),
    env: { ...process.env, SHOUHENG_STATE_DIR: fakeDir },
    encoding: 'utf8',
    timeout: 30000,
  });
  fs.rmSync(tmp, { recursive: true, force: true });

  assert.strictEqual(r.status, 0,
    `进程应正常退出，实际 status=${r.status}\n stderr: ${(r.stderr || '').slice(-500)}`);
  assert.ok((r.stdout || '').includes('BOOT_OK'),
    `应到达 import 之后的代码，实际 stdout: ${(r.stdout || '').slice(-300)}`);
  assert.ok(!/EEXIST|ENOTDIR: not a directory, mkdir/.test(r.stderr || ''),
    `不应把目录创建失败升级成崩溃：${(r.stderr || '').slice(-300)}`);
});

if (LIVE) {
  console.log('\n═══ 4. 真实 LLM 全链路（会消耗 token）═══');
  const { handleMessage } = await import('./agent/agent.mjs');
  const evt = (text, id) => ({
    sender: { sender_id: { open_id: 'ou_test_lee' }, sender_type: 'user' },
    message: {
      message_id: id, chat_id: 'oc_test_offline', chat_type: 'group', message_type: 'text',
      content: JSON.stringify({ text }),
      mentions: [{ key: '@_user_1', name: '守衡', id: { open_id: 'cli_aa2243de0438dcd7' } },
                 { key: '@_user_2', name: '李倩怡', id: { open_id: 'ou_test_lee' } }],
    },
  });

  for (const [i, q] of [
    '@_user_1 @_user_2 你是谁？用两句话回答。',
    '@_user_1 @_user_2 我刚才问了你什么？',
    '@_user_1 @_user_2 现在几点？',
  ].entries()) {
    const r = await handleMessage(evt(q, `om_test_${Date.now()}_${i}`));
    console.log(`\n  Q${i + 1}: ${q}`);
    console.log(`  A${i + 1}: ${r.reply ?? '（无回复 / ' + r.reason + '）'}`);
    if (r.meta?.toolTrace?.length) console.log(`  工具: ${r.meta.toolTrace.map((t) => t.tool).join(', ')}`);
  }
  const { status } = await import('./agent/agent.mjs');
  console.log('\n  LLM 用量:', JSON.stringify(status().llm, null, 2));
}

// ─────────────────────────────────────────────────────────────────────────────
// 7. 时间基准一致性
//
// 背景（真实事故，不是假想）：`now` 工具返回北京时间，而 `recent_messages`
// 曾经返回 `toISOString()`，也就是 UTC。两种基准并存时，模型会自己再做一次
// 换算 —— 真实的 11:12 被守衡在群里说成「23:12」，一次错 12 小时。
//
// 这类错误必须由测试兜住，因为它在生产里**完全静默**：
// 没有异常、没有报错、日志干净，只是守衡对外说了错的时间。
// 唯一可靠的判据是「格式本身不许出现 UTC 的样子」。
// ─────────────────────────────────────────────────────────────────────────────
console.log('\n═══ 7. 时间基准一致性（北京，不是 UTC）═══');

// 形如 `2026-09-16 12:26:20 星期三`；UTC ISO 那种 `...T04:26:20.117Z` 必须不被接受。
const BEIJING_RE = /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} 星期[日一二三四五六]$/;

await t('守衡格式化的时间不带 UTC 标识（Z / T）', async () => {
  const { beijingDateTime, beijingString } = await import('./agent/timefmt.mjs');
  const s = beijingString(Date.parse('2026-09-16T04:26:20.400Z'));
  assert.ok(BEIJING_RE.test(s), `应为「YYYY-MM-DD HH:mm:ss 星期X」，实际：${s}`);
  assert.ok(!s.includes('Z') && !s.includes('T'),
    `不得混入 UTC 标识（这正是让模型二次换算的诱因）：${s}`);

  const full = beijingDateTime(Date.parse('2026-09-16T04:26:20.400Z'));
  assert.strictEqual(full.date, '2026-09-16');
  assert.strictEqual(full.time, '12:26:20', `UTC 04:26 应为北京 12:26，实际 ${full.time}`);
  assert.strictEqual(full.iso, '2026-09-16T04:26:20.400Z', 'iso 应保留同一瞬间，便于核对');
});

await t('now 工具与 timefmt 同源，且偏移按真实时区计算', async () => {
  const { executeTool } = await import('./agent/tools.mjs');
  const r = await executeTool('now', {});
  assert.strictEqual(r.ok, true, `now 工具失败：${r.error}`);
  assert.ok(BEIJING_RE.test(r.result.beijing_time),
    `now.beijing_time 格式应为「YYYY-MM-DD HH:mm:ss 星期X」，实际：${r.result.beijing_time}`);
  // 不硬编码 +8：将来时区规则若变化，这里会自己发现，而不是继续悄悄算错。
  assert.strictEqual(r.result.timezone, 'Asia/Shanghai (UTC+08:00)',
    `时区标注不对：${r.result.timezone}`);
});

await t('午夜不产生 24:xx 这种非法时刻', async () => {
  const { beijingDateTime } = await import('./agent/timefmt.mjs');
  // 北京时间 00:00–00:59 对应 UTC 前一天 16:xx。
  // en-CA + hour12:false 在午夜可能给出 hour='24'，不归一就会输出「24:05」。
  for (const h of [0, 1, 5, 23]) {
    const utc = Date.UTC(2026, 8, 15, h, 5, 0);   // 北京 = h+8
    const { time } = beijingDateTime(utc);
    const hh = Number(time.slice(0, 2));
    assert.ok(hh >= 0 && hh <= 23, `时刻越界：${time}（UTC ${h}:05）`);
    assert.ok(!time.startsWith('24'), `出现了非法的 24 时：${time}`);
  }
});

await t('时间戳损坏时不抛异常，而是给出可读的占位', async () => {
  const { beijingString } = await import('./agent/timefmt.mjs');
  // 一条坏消息的时间戳不该让整个工具调用失败 —— 那是把局部数据问题升级成功能故障。
  const s = beijingString('not-a-date');
  assert.ok(typeof s === 'string' && s.length > 0, `应返回可读占位，实际：${s}`);
  assert.ok(s.includes('时间未知'), `应说明时间未知，实际：${s}`);
});

// ─────────────────────────────────────────────────────────────────────────────
// 8. 群历史必须能分辨「谁发的」
//
// 背景（真实事故）：群历史接口**是**返回 sender.id 的（实测有值），但工具层
// 把它丢掉、一律显示「用户」。守衡于是看到 7 条消息全是「用户」，
// 据此回答「我分辨不出哪条是谁发的」—— 一个听上去非常合理、但完全错误的结论。
//
// 这类缺陷的性质：**不是能力不足，是自己把信息扔了**。守衡会自信地宣称
// 自己做不到，而数据一直躺在返回值里。所以必须有测试锁住「占位符不许回来」。
// ─────────────────────────────────────────────────────────────────────────────
console.log('\n═══ 8. 群历史能分辨发送者 ═══');

await t('app 消息与 user 消息都被正确归类', async () => {
  const { resolveSender } = await import('./agent/feishu.mjs');
  const map = new Map([['ou_me', '周健'], ['ou_other', '李倩怡']]);

  assert.strictEqual(resolveSender({ senderType: 'app', senderId: 'cli_x' }, map).from, '守衡(你自己)',
    'app 消息应标成守衡自己');
  assert.strictEqual(resolveSender({ senderType: 'user', senderId: 'ou_me' }, map).from, '周健',
    '已知成员应解析出姓名');
  assert.strictEqual(resolveSender({ senderType: 'user', senderId: 'ou_other' }, map).from, '李倩怡',
    '不同成员必须能区分开');
});

await t('未知成员退化为 open_id，而不是「用户」这种无法区分的占位符', async () => {
  const { resolveSender } = await import('./agent/feishu.mjs');
  const map = new Map();   // 空成员表：模拟「拉不到成员列表」

  const r = resolveSender({ senderType: 'user', senderId: 'ou_unknown_person' }, map);
  assert.ok(!/^用户$/.test(r.from),
    `退回无法区分人的「用户」等于重新制造这次的 bug：${r.from}`);
  assert.ok(r.from.includes('ou_unknown_person'),
    `应保留 open_id 以便比对：${r.from}`);
  // 关键：即使解析不出姓名，也必须留下可比对的身份，让「两条是不是同一个人」仍然可判
  assert.strictEqual(r.senderOpenId, 'ou_unknown_person', 'senderOpenId 必须一并带出');
});

await t('接口没给发送者身份时，如实说明，不伪装成普通「用户」', async () => {
  const { resolveSender } = await import('./agent/feishu.mjs');
  const r = resolveSender({ senderType: 'user', senderId: undefined }, new Map());
  assert.ok(r.from.includes('未返回'), `应如实标注接口未返回身份：${r.from}`);
  assert.strictEqual(r.senderOpenId, null);
});

await t('真实群里用户消息解析出姓名（不是 ou_ 开头）', async () => {
  const { executeTool, runtimeContext } = await import('./agent/tools.mjs');
  const feishuMod = await import('./agent/feishu.mjs');
  runtimeContext.chatId = 'oc_49a7cfb2861cffa4365ca8491f398d32';
  runtimeContext.chatType = 'group';

  const members = await feishuMod.listMembers(runtimeContext.chatId);
  const names = new Set((Array.isArray(members) ? members : []).map((u) => u.name));

  const r = await executeTool('recent_messages', { limit: 20 });
  assert.strictEqual(r.ok, true, `recent_messages 失败：${r.error}`);
  const msgs = r.result.messages;
  assert.ok(msgs.length > 0, '应至少取到一条历史消息');

  const userMsgs = msgs.filter((m) => !String(m.from).includes('守衡'));
  assert.ok(userMsgs.length > 0, '本群应有用户消息可供验证');
  for (const m of userMsgs) {
    assert.ok(!/^用户$/.test(m.from), `不得退回「用户」占位符：${JSON.stringify(m).slice(0, 120)}`);
    assert.ok(names.has(m.from),
      `发送者「${m.from}」应是本群成员之一（${[...names].join('、')}）—— 解析不出姓名说明成员表没接上`);
  }

  // 顺带确认时间与身份是同一份数据里出来的，不是拼凑的
  assert.ok(/星期[日一二三四五六]$/.test(msgs[0].at), `时间格式不对：${msgs[0].at}`);
  runtimeContext.chatId = null;
});

// ─────────────────────────────────────────────────────────────────────────────
// 第 9 组：截断守卫。真实事故 —— 779 字回复停在「…里「未做」，
// 守护进程却记「✓ 已发送」。半句话被当成完整回答，用户无从知道它是断的。
// ─────────────────────────────────────────────────────────────────────────────
console.log('\n═══ 9. 截断必须可见（不许把半句话当完整回答发出去）═══');

await t('finish_reason=length 必须被判为截断（哪怕正文看着像正常结尾）', async () => {
  const { detectTruncation } = await import('./agent/truncate.mjs');

  const r = detectTruncation({ finishReason: 'length', text: '这是一段看起来已经写完的话。' });
  assert.strictEqual(r.cut, true, 'finish_reason 是权威信号，不能被文本启发式推翻');
  assert.ok(/length/.test(r.reason), `原因里应包含 length：${r.reason}`);

  const ok = detectTruncation({ finishReason: 'stop', text: '正常收尾的回答。' });
  assert.strictEqual(ok.cut, false, '正常收尾不应误报');
});

await t('回归：事故原文必须被拦住', async () => {
  const { detectTruncation } = await import('./agent/truncate.mjs');

  // 逐字来自 2026-09-16 那条真实回复的结尾
  const incident = '**怎么变好的：** 刚查时工具已经修好并重启了，我重新读了一次历史，发送者字段就出来了。这条也算那份记录里「未做';
  const r = detectTruncation({ finishReason: 'length', text: incident });
  assert.strictEqual(r.cut, true, '这条必须被判为截断');

  // 即使 finish_reason 丢了，文本启发式也要能兜住
  const noFinish = detectTruncation({ finishReason: undefined, text: incident });
  assert.strictEqual(noFinish.cut, true,
    '『未做』这种悬空结尾即使没有 finish_reason 也必须拦住 —— 不能只依赖一个信号');
});

await t('悬空标点与空回复都要拦住', async () => {
  const { detectTruncation } = await import('./agent/truncate.mjs');

  assert.strictEqual(detectTruncation({ finishReason: 'stop', text: '我想说的是，' }).cut, true, '逗号结尾应拦');
  assert.strictEqual(detectTruncation({ finishReason: 'stop', text: '补充说明（' }).cut, true, '左括号结尾应拦');
  assert.strictEqual(detectTruncation({ finishReason: 'stop', text: '空回复应拦' }).cut, false, '有收尾的中文不该拦');
  assert.strictEqual(detectTruncation({ finishReason: 'stop', text: '' }).cut, true, '空回复应拦');
  // 短句不误报：短内容本来就可能没有句号
  assert.strictEqual(detectTruncation({ finishReason: 'stop', text: '好' }).cut, false, '短回答不该误报');
  assert.strictEqual(detectTruncation({ finishReason: 'stop', text: '收到' }).cut, false, '两字回复不该误报');
  // 表格/列表结尾不该误报（Markdown 里本来就常无句号）
  const table = '| # | 时间 | 说的 |\n|---|---|---|\n| 1 | 22:38 | 你是做什么的 |';
  assert.strictEqual(detectTruncation({ finishReason: 'stop', text: table }).cut, false, '表格结尾不该误报');
});

await t('被截断的回复必须带出可见的截断标记，且不留在半句话上', async () => {
  const { annotateTruncation } = await import('./agent/truncate.mjs');

  const incident = '**怎么变好的：** 刚查时工具已经修好并重启了。这条也算那份记录里「未做';
  const out = annotateTruncation(incident, { reason: 'finish_reason=length（额度耗尽）' });

  assert.ok(out.includes('截断'), '必须明说被截断了，用户才知道这不是全部');
  assert.ok(out.includes('接着说'), '要给出可执行的下一步');
  assert.ok(!out.includes('「未做\n'), '不能把半句话原样留在正文里');
  assert.ok(out.startsWith('**怎么变好的：**'), '完整部分应保留');

  // 超长必须被收住，不能一条消息刷屏
  const huge = '一。'.repeat(5000);
  const capped = annotateTruncation(huge, { maxChars: 500 });
  assert.ok(capped.length < 900, `应被长度上限收住，实际 ${capped.length} 字`);
});

await t('配置的 maxTokens 必须留得下思维链（实测 1600 会被吃光）', async () => {
  const { config } = await import('./agent/config.mjs');
  assert.ok(config.llm.maxTokens >= 4000,
    `maxTokens=${config.llm.maxTokens} 太小：DeepSeek 的额度同时覆盖思维链，实测 1600/4000 时 reasoning 会全部吃光、正文 0 字`);
});

console.log('\n═══ 10. 群历史的「看不见」必须由工具给，不由模型推 ═══');

await t('提示词能构建，且人设正文里没有裸反引号', async () => {
  const { buildSystemPrompt, SYSTEM_PROMPT } = await import('./agent/persona.mjs');
  let sp;
  assert.doesNotThrow(() => { sp = buildSystemPrompt(); }, 'SYSTEM_PROMPT 是模板字符串，正文里出现裸反引号会让整个模块语法错误');

  // 事故：往提示词里写 `recent_messages` 做反引号强调，模板字符串提前闭合，
  // 整个 persona.mjs 变成语法错误 —— 而这在跑测试之前完全看不出来。
  //
  // ★ 2026-09-22 修正：原先断言的是「`# 当前时间` 之前的全部正文里不许有反引号」。
  //   **那是误报，而且已经挂了很久** —— `cardContract()` 那段本来就要示范卡片块围栏
  //   （源码里写的是转义反引号 \`\`\`，构建后就是真反引号），它就落在那个区间里。
  //   实测：改之前跑本套件是「41 通过 / 1 失败」，失败的就是这一条。
  //   一个长期误报的检查器会让人开始不看报告（AGENTS.md §2.1.1），所以改成断真正的不变量：
  //   **人设正文（SYSTEM_PROMPT）里一个反引号都不许有**；卡片规程那段单独放行，
  //   但要断言它示范的围栏**真的出现在了成品提示词里**（反过来被「修」没了也要红）。
  // ★ 2026-10-05 第二次修正：上一条 09-22 的修法（「渲染结果里一个反引号都不许有」）
  //   **自己变成了误报** —— 09-30 那次会话在知识库那一行里**故意**写了行内代码
  //   （源码 \`127.0.0.1\`，转义的正确写法），渲染出来就是一对反引号。
  //   于是本套件从那天起一直是红的（实测 `2 !== 0`），而且**没人注意到** ——
  //   这正是 AGENTS.md §2.1.1 那句话本身：一个会误报的检查器会让人开始不看报告。
  //   判据收到真正的危险上：**未转义**的反引号会让模板字符串提前闭合（09-22 那次事故的形状），
  //   转义的写法无害。所以查的是**源码**，不是渲染结果，且必须自带反向对照。
  {
    const fs = await import('node:fs');
    const src = fs.readFileSync(new URL('./agent/persona.mjs', import.meta.url), 'utf8');
    const n = unescapedBackticksInTemplate(src, 'SYSTEM_PROMPT');
    assert.strictEqual(n, 0, `人设模板里有 ${n} 个**未转义**反引号 —— 模板字符串会提前闭合，`
      + '整个 persona.mjs 变成语法错误（09-22 的事故形状）');
    // 反向对照：喂事故形状必须报出来，否则这条也是空转
    const bad = 'export const SYSTEM_PROMPT = `往提示词里写 `recent_messages` 做强调`;';
    assert.ok(unescapedBackticksInTemplate(bad, 'SYSTEM_PROMPT') > 0,
      '反向对照失败：喂未转义反引号没报出来，说明这条判据是空转的');
    // 反面之二：转义写法**不许**被误报（否则又会回到上面那个误报状态）
    const good = 'export const SYSTEM_PROMPT = `走本机 \\`127.0.0.1\\` 的只读接口`;';
    assert.strictEqual(unescapedBackticksInTemplate(good, 'SYSTEM_PROMPT'), 0,
      '转义反引号是正确写法，不许误报');
  }
  assert.ok(sp.includes('[[card:类型]]'), '卡片块的围栏必须真的出现在成品提示词里');
  assert.ok(sp.includes('```'), '围栏的三个反引号必须真的渲染出来（转义写错会静默少掉）');

  assert.ok(sp.includes('只能看到最近 50 条'), '必须写明群历史只看得到最近 50 条');
  assert.ok(sp.includes('撤回的消息，原文取不回'), '必须写明撤回的消息取不回原文');
  // ★ 2026-10-05 加：**媒材本身就算送审**。起因是一次真实事故 ——
  //   有人发了一条视频、一个字没写，守衡把读数描述了一遍就收工，**一次工具都没调**，
  //   而路由规则当时是按问句写的（「能不能发 / 审一下」），光秃秃的媒体消息不匹配任何问句。
  assert.ok(sp.includes('没有文字也一样'), '人设必须写明「带媒材但没文字，也一样走 kb_review_chain」');
  assert.ok(/图 \/ 视频 \/ 飞书文档链接[\s\S]{0,40}送审/.test(sp),
    '那条规则必须点名「图 / 视频 / 飞书文档链接」这三种媒材');
  assert.ok(sp.includes('图片只读得到「字」'), '必须写明：图能读图内文字，但画面本身看不到');
  assert.ok(sp.includes('画面本身你看不到'), '必须写明画面看不见 —— 否则模型会把「读到图上的字」说成「看过这张图」');
  assert.ok(sp.includes('按规矩不取'), '附件必须说成「按规矩不取」，不许说成「没权限 / 能力还没做」');
  assert.ok(sp.includes('「我打不开飞书文档」通常是一句假话'),
    '必须写明：收到飞书链接时先说工作区里有没有那一份，再说读不读得了');
  assert.ok(!/我记不清/.test(sp.replace(/不要用「我记不清」/g, '')),
    '不许把「看不到」说成「记不清」——那是两种不同的东西');
});

await t('recent_messages 返回值必须带窗口边界，且顶到上限时明说', async () => {
  const { listRecentMessages } = await import('./agent/feishu.mjs');
  const msgs = await listRecentMessages('oc_49a7cfb2861cffa4365ca8491f398d32', 5);
  if (msgs?.error) return; // 离线时不联网断言，避免测试依赖网络

  assert.ok(msgs.window, '必须带 window 字段：否则守衡说「第一次」时不知道自己只看到了一截');
  assert.strictEqual(msgs.window.returned, msgs.length);
  assert.strictEqual(msgs.window.atLimit, msgs.length >= 5);
  assert.ok(msgs.window.oldestAt, '必须给出窗口最早一条的时间');

  if (msgs.window.atLimit) {
    assert.ok(/第一次/.test(msgs.window.note), '顶到上限时必须提示「第一次」只在本窗口内成立');
  }

  // 撤回的消息必须带 recalled 标记，否则它和「一条短消息」长得一模一样
  const recalled = msgs.filter((m) => m.recalled);
  for (const m of recalled) {
    assert.ok(!/This message was recalled/.test(m.text), '英文占位符要换成人能读懂的说明');
    assert.ok(/撤回/.test(m.text), '撤回的消息要说明原文取不回');
  }
});

// ─────────────────────────────────────────────────────────────────────────────
// 第 11 组：空回复不许污染记忆、工具返回体不许撑爆上下文。
// 真实事故（2026-09-30 19:11 / 19:16，本群）：她问「用知识库查一下『吸奶器』相关的
// 措辞要求」→ 工具回了 41,262 + 19,087 = 60,349 字原始 JSON → 下一轮推理把 8000 token
// 输出预算吃光（finish_reason=length、正文 0 字）→ 群里收到一条**只有截断说明的消息**。
// 之后**每一步都是这个空回复的连锁反应**：空 assistant 被存进记忆 → 下一轮回放时
// API 400（The reasoning_content … must be passed back）→ 那条 400 被当成「已答」写进
// 记忆 → 补发队列认为她已经被答过，答案永远没发出去。
// ─────────────────────────────────────────────────────────────────────────────
console.log('\n═══ 11. 空回复与超长工具返回体（2026-09-30 事故的三条根因）═══');

await t('空 assistant 轮不许落进记忆（API 会 400，且会被当成「已经答过」）', async () => {
  const mem = await import('./agent/memory.mjs');
  const sess = { key: 'k', messages: [], messageCount: 0 };

  const r1 = mem.append(sess, { role: 'assistant', content: '' });
  assert.strictEqual(r1.stored, false, '空串必须被拒收');
  assert.strictEqual(sess.messages.length, 0, `空串不该进 messages，实际 ${sess.messages.length} 条`);

  // 纯空白与 null 是同一个病的另两种写法 —— 一起拦
  assert.strictEqual(mem.append(sess, { role: 'assistant', content: '  \n\t ' }).stored, false, '纯空白也必须被拒收');
  assert.strictEqual(mem.append(sess, { role: 'assistant', content: null }).stored, false, 'null 也必须被拒收');

  // ── 反面：该放行的三种，一个都不许被误伤（否则会把正常回答也吞掉）
  assert.strictEqual(mem.append(sess, { role: 'assistant', content: '结论：不能单独写「吸奶器」。' }).stored, true,
    '有内容的回答必须照常落盘');
  assert.strictEqual(mem.append(sess, { role: 'assistant', content: '', tool_calls: [{ id: 'c1' }] }).stored, true,
    '带 tool_calls 的空 content 是协议的一部分，**不许**被拦');
  assert.strictEqual(mem.append(sess, { role: 'user', content: '' }).stored, true,
    '只拦 assistant 轮 —— user / tool 轮的判据不同，不该在这一层顺手管');
});

await t('回放时丢掉历史里的坏记录（盘上已经躺着的那两条也要救）', async () => {
  const mem = await import('./agent/memory.mjs');
  const withEmpty = [
    { role: 'system', content: 'S' },
    { role: 'user', content: '用知识库查一下「吸奶器」相关的措辞要求' },
    { role: 'assistant', content: '', tool_calls: [{ id: 'c1', function: { name: 'kb_search' } }] },
    { role: 'tool', tool_call_id: 'c1', content: '{"ok":true}' },
    { role: 'assistant', content: '' },                                   // ← 事故里那条（第 26 条）
    { role: 'assistant', content: '' },                                   // ← 另一条（第 43 条）
    { role: 'user', content: '接着说' },
  ];
  const out = mem.sanitizeForLlm(withEmpty);

  assert.strictEqual(out.filter((m) => m.role === 'assistant' && !String(m.content ?? '').trim()
    && !(m.tool_calls?.length)).length, 0,
    '回放里一个空 assistant 都不许剩下 —— 实测单发必 400（reasoning_content must be passed back）');
  assert.strictEqual(out.length, 5, `应只删掉那两条空 assistant，实际 ${out.length} 条：${JSON.stringify(out.map((m) => m.role))}`);
  assert.deepStrictEqual(out.map((m) => m.role), ['system', 'user', 'assistant', 'tool', 'user'],
    '只删不许重排 —— 顺序变了就是另一个 bug');
  assert.strictEqual(out[3].tool_call_id, 'c1', '配得上 tool_calls 的 tool 结果必须留着');

  // ── 反面：孤儿 tool 结果（前面没有对应的 tool_calls）必须丢掉 —— 实测那也是一种 400
  const orphan = mem.sanitizeForLlm([
    { role: 'system', content: 'S' },
    { role: 'user', content: 'q' },
    { role: 'tool', tool_call_id: 'nope', content: '{"ok":true}' },
    { role: 'assistant', content: '正常的回答。' },
  ]);
  assert.strictEqual(orphan.some((m) => m.role === 'tool'), false, '孤儿 tool 结果会让 API 直接拒收整条请求');
  assert.strictEqual(orphan.length, 3, '除了那条孤儿，其余一条都不许少');

  // 一个 tool 结果只配一次：重复的同样丢掉（重复 id 也是 400 的形状）
  const dup = mem.sanitizeForLlm([
    { role: 'assistant', content: '', tool_calls: [{ id: 'c1' }] },
    { role: 'tool', tool_call_id: 'c1', content: 'a' },
    { role: 'tool', tool_call_id: 'c1', content: 'b' },
  ]);
  assert.strictEqual(dup.filter((m) => m.role === 'tool').length, 1, '同一个 tool_call_id 只许配一个结果');

  // ── 反面之二：干净的历史必须**一条都不动**（否则这一层就成了新的破坏源）
  const clean = [{ role: 'system', content: 'S' }, { role: 'user', content: 'q' },
                 { role: 'assistant', content: '答' }, { role: 'user', content: 'q2' }];
  assert.deepStrictEqual(mem.sanitizeForLlm(clean), clean, '正常对话不许被清洗动到');

  // ★★ 接线断言：清洗必须在**真正的回放出口** `toLlmMessages` 上生效。
  //   只测 `sanitizeForLlm` 是不够的 —— 反向对照实测：把 `toLlmMessages` 里那一行
  //   `return sanitizeForLlm(out)` 改回 `return out`，纯函数那几条**照样全绿**，
  //   而守衡每一轮请求都会带着空 assistant 去换一个 400。
  //   （这正是 AGENTS.md §2.4 那个病：函数写对了，但没人断言它被接上。）
  const sess2 = { summary: '', messages: [
    { role: 'user', content: 'q' },
    { role: 'assistant', content: '' },                 // ← 盘上真出现过的那种坏记录
    { role: 'user', content: '接着说' },
  ] };
  const replay = mem.toLlmMessages(sess2, 'SYS');
  assert.strictEqual(replay.filter((m) => m.role === 'assistant' && !String(m.content ?? '').trim()
    && !(m.tool_calls?.length)).length, 0,
    'toLlmMessages 的出口必须已经清洗过 —— 否则清洗只是一段没人调用的代码');
  assert.strictEqual(replay[0].role, 'system', '系统提示仍必须在最前');
});

await t('工具返回体超过预算必须被真的剪掉（60,349 字的那个形状）', async () => {
  const { clipToolOutput, TOOL_OUTPUT_MAX_CHARS, collapseToolMessages } = await import('./agent/truncate.mjs');

  // 事故里那份返回体的真实尺寸：41,262 + 19,087
  const huge = JSON.stringify({ ok: true, collection: '3_措辞表达库', hitCount: 44,
    hits: Array.from({ length: 44 }, (_, i) => ({ docId: `d${i}`, text: '正例：这款吸奶器采用仿生吸吮技术。'.repeat(40) })) });
  assert.ok(huge.length > 20_000, `样本要够大才有意义，实际 ${huge.length} 字`);

  const clipped = clipToolOutput(huge);
  assert.ok(clipped.length <= TOOL_OUTPUT_MAX_CHARS + 300,
    `必须被剪到上限附近，实际 ${clipped.length} 字（上限 ${TOOL_OUTPUT_MAX_CHARS}）`);
  assert.ok(clipped.includes(String(huge.length)), '剪了多少字要写在里面 —— 裁剪必须可见');
  assert.ok(/没进上下文|截断/.test(clipped), '要明说这是被截断的，不许让调用方以为拿到的是全文');

  // 反面：没超限的不许动一个字符
  const small = JSON.stringify({ ok: true, hits: [{ text: '短' }] });
  assert.strictEqual(clipToolOutput(small), small, '没超预算时不许改写返回体');

  // ★ 兜底合成要的是**没有原始 JSON**：折叠后必须短，且仍指得出「有哪些东西、多少量」
  const msgs = [{ role: 'user', content: 'q' },
                { role: 'assistant', content: '', tool_calls: [{ id: 'c1' }] },
                { role: 'tool', tool_call_id: 'c1', content: huge }];
  const folded = collapseToolMessages(msgs);
  assert.strictEqual(folded.length, 3, '条数不许变 —— tool_call_id 还得配得上 tool_calls');
  assert.strictEqual(folded[2].tool_call_id, 'c1', 'tool_call_id 必须原样保留，否则合成那一跳会 400');
  assert.ok(folded[2].content.length < 600, `折叠后要短，实际 ${folded[2].content.length} 字`);
  assert.ok(folded[2].content.includes('44'), '折叠不许把「量」丢掉 —— 要能说出命中多少条');
  assert.ok(!folded[2].content.includes('仿生吸吮'), '折叠后不许再夹带原始正文');
  assert.deepStrictEqual(folded[0], msgs[0], '非 tool 的消息一条都不许动');
});

await t('kb_search 的返回体有上限，且裁剪**必须报出来**', async () => {
  const kb = await import('./agent/kb_client.mjs');

  // 纯函数式的判据：常量存在且互相自洽
  assert.ok(kb.HITS_RETURN_MAX >= 1 && kb.HITS_RETURN_MAX <= kb.TOPK_MAX,
    `HITS_RETURN_MAX=${kb.HITS_RETURN_MAX} 必须落在 1..${kb.TOPK_MAX}`);
  assert.ok(kb.HIT_TEXT_MAX >= 200 && kb.HIT_TEXT_MAX <= 4000,
    `HIT_TEXT_MAX=${kb.HIT_TEXT_MAX} 不合理：太小会剪掉整条规则，太大等于没剪`);

  // 离线时（连不上对端）跳过实网断言，但上面那两条与网络无关，必须照跑
  let r;
  try { r = await kb.retrieve(kb.COLLECTIONS.wording, '吸奶器', { topK: 50 }); }
  catch { return; }   // 对端不在线是**正常状态之一**，不该让自证变红

  assert.ok(r.hits.length <= kb.HITS_RETURN_MAX,
    `一次塞进上下文的分片数必须 ≤ ${kb.HITS_RETURN_MAX}，实际 ${r.hits.length}`);
  assert.strictEqual(r.hits_returned, r.hits.length, 'hits_returned 必须等于真的回给你的条数');
  assert.strictEqual(r.hits_dropped, r.hitCount - r.hits.length,
    'hits_dropped 必须等于「服务端命中 − 真回给你的」—— 两个读数不许各说各的');
  if (r.hits_dropped > 0 || r.text_clipped > 0) {
    assert.ok(r.clip_note, '剪了就**必须**有一句说明，否则会被读成「库里只有 10 条」');
    assert.ok(/不等于|不许|不要/.test(r.clip_note), '说明里要写清「这不等于库里只有这些」');
  }
  for (const h of r.hits) {
    assert.ok(String(h.text).length <= kb.HIT_TEXT_MAX + 120,
      `单条分片正文应被剪到 ${kb.HIT_TEXT_MAX} 字附近，实际 ${String(h.text).length}`);
  }
  // uniqueDocCount 必须描述**这次交到手里的那几条**，不是服务端全量
  assert.ok(r.uniqueDocCount <= r.hits.length, 'uniqueDocCount 不许大于回给你的分片数（那是旧口径：按全量算）');
});

// ─────────────────────────────────────────────────────────────────────────────
// 第 12 组：模型把**工具调用语法当成正文**吐出来 —— 2026-09-30 实盘撞见的第二种形状。
// 复现：修完上面那批之后实盘重放，模型在正文里直接写框架标记与 invoke/parameter 标签，
// 而当时 `internalLeak` **一条都不命中**（实测 0）——
// 后果是群里看到一段谁也读不懂的尖括号，比半句话更难判断「这是不是全部内容」。
// ─────────────────────────────────────────────────────────────────────────────
console.log('\n═══ 12. 工具调用语法漏进正文（思考模式的第二种泄漏形状）═══');

await t('DSML 框架标记必须被 internalLeak 拦住', async () => {
  const { lintCopy } = await import('./reply-cards/registry.mjs');

  // 逐字来自 2026-09-30 实盘那次模型输出
  const leaked = '<\uFF5C\uFF5CDSML\uFF5C\uFF5C calls>\n'
    + '<\uFF5C\uFF5CDSML\uFF5C\uFF5C invoke name="kb_search">\n'
    + '<\uFF5C\uFF5CDSML\uFF5C\uFF5C parameter name="collection" string="true">3_措辞表达库';
  const hit = lintCopy(leaked).find((h) => h.id === 'internalLeak');
  assert.ok(hit, `这串框架标记必须被拦下 —— 否则群里看到的是谁也读不懂的尖括号。实测命中：${JSON.stringify(lintCopy(leaked))}`);
  assert.ok(hit.count >= 1, `应至少计到 1 处，实际 ${hit.count}`);

  // ── 反面：正经回答里出现 invoke / parameter 这类**正常英文词**时不许误报
  //    （§2.1.1：一个会误报的检查器比没有检查器更糟 —— 判据取的是带全角竖线的标记本身）
  const normal = '这条规则的 parameter 有两个：条款号与生效日期。用 kb_search 查 invoke 的写法即可。';
  assert.strictEqual(lintCopy(normal).filter((h) => h.id === 'internalLeak').length, 0,
    '正常英文词不许被当成泄漏 —— 否则正经回答会被拦下');

  // 反面之二：只有半截标记（没有竖线）也不该报
  const half = '我调了 DSML 里的 kb_search 工具。';
  assert.strictEqual(lintCopy(half).filter((h) => h.id === 'internalLeak').length, 0,
    '光提到 DSML 三个字母不是泄漏，标记形状才是判据');
});


// ─────────────────────────────────────────────────────────────────────────────
// 第 13 组：图文消息进链路 —— 2026-10-05 那条「评审下下这个图片，能过吗？」
//
// 事故形状（逐字取自 PMO/logs/ws_events.jsonl 那一条真实事件）：
// 刘华丽私聊发了一条**图文混排**（飞书里这是 `post` 类型），守衡 **14ms** 回：
//   「这条是「post」，它的正文我读不了 —— 需要的话请把它转成文字发我。」
// 两个错，同一个形状（结论比输入大）：
//   ① 正文就在 payload 里（`bodyToText` 09-22 就修好了），却被整类拒掉 —— 假否定；
//   ② 图片按红线不取（当时对），但话说成「正文我读不了」，她于是没有任何可走的路。
// 修法：正文照读；**人当前发来的图**读图内文字（§2.6 窄豁免，Owner 10-05 确认）；
//       file/media/audio 仍然一次都不取。
//
// ★ 这一组全部用**桩**（不联网、不花 token），所以它是能随时跑的判据，
//   而不是「要真发一条消息才知道」。—— 判据跑不动，等于没有判据。
// ─────────────────────────────────────────────────────────────────────────────
console.log('\n═══ 13. 图文消息：正文读得出来 + 图只读字 + 附件一次都不取 ═══');

// 逐字来自那一条真实事件（`post` 类型，正文 + 一张 940×1162 的图）
const INCIDENT_POST = '{"title":"","content":[[{"tag":"text","text":"评审下下这个图片，能过吗？","style":[]}],'
  + '[{"tag":"img","image_key":"img_v3_02166_ec55a781-048d-400d-9e97-616adba94e0g","width":940,"height":1162}]],'
  + '"content_v2":[[{"tag":"text","text":"评审下下这个图片，能过吗？","style":[]}],'
  + '[{"tag":"img","image_key":"img_v3_02166_ec55a781-048d-400d-9e97-616adba94e0g","width":940,"height":1162}]]}';
const INCIDENT_MID = 'om_x100b63191aeb5ca0b4b07c1c5864afb';
const INCIDENT_KEY = 'img_v3_02166_ec55a781-048d-400d-9e97-616adba94e0g';

await t('回归·事故那条 post 的正文必须读得出来（旧行为是空串）', async () => {
  const { bodyToText } = await import('./agent/feishu.mjs');
  const p = bodyToText('post', INCIDENT_POST);
  assert.strictEqual(p.parsed, true, 'post 必须解析成功 —— 解析不出来就是回到事故现场');
  assert.ok(p.text.includes('评审下下这个图片，能过吗？'), `正文没读出来：${JSON.stringify(p.text)}`);
  assert.ok(p.text.includes('[图片]'), '图在正文里要留一个位置标记，否则模型不知道那句话旁边还有张图');
});

await t('图在哪：只认 post / image 两种形态', async () => {
  const { imageKeysOf } = await import('./agent/feishu.mjs');
  const k1 = imageKeysOf('post', INCIDENT_POST);
  assert.strictEqual(k1.length, 1, `post 里应认出 1 张图，实际 ${k1.length}`);
  assert.strictEqual(k1[0].imageKey, INCIDENT_KEY, 'image_key 必须逐字带出来（取字节就靠它）');
  assert.strictEqual(k1[0].width, 940);
  assert.strictEqual(imageKeysOf('image', '{"image_key":"img_abc"}').length, 1, '单图消息也要认');
  assert.strictEqual(imageKeysOf('image', '{"image_key":"img_abc"}')[0].imageKey, 'img_abc');
});

await t('红线·file / media / audio 一张都不许被当成图', async () => {
  const { imageKeysOf } = await import('./agent/feishu.mjs');
  for (const [type, payload] of [
    ['file', '{"file_key":"file_v3_x","file_name":"a.xlsx"}'],
    ['media', '{"file_key":"file_v3_y","duration":3000}'],
    ['audio', '{"file_key":"file_v3_z","duration":9000}'],
    // 极端形状：附件 payload 里**硬塞**一个 image_key 也不许被认出来
    ['file', '{"file_key":"f","image_key":"img_v3_sneaky"}'],
  ]) {
    assert.deepStrictEqual(imageKeysOf(type, payload), [],
      `${type} 类型不许回任何图 —— 那不在 §2.6 窄豁免里`);
  }
});

await t('行为级·图文混排：真取图 + 真 OCR，图块里带 OCR 文字', async () => {
  const { readInboundContent, buildImageBlock } = await import('./agent/agent.mjs');
  const calls = { fetch: [], ocr: [], cleaned: 0 };
  const deps = {
    fetchImage: async (mid, key) => {
      calls.fetch.push([mid, key]);
      return { path: '/tmp/假图.img', bytes: 745672, error: null, cleanup: () => { calls.cleaned++; } };
    },
    ocr: async (p) => { calls.ocr.push(p); return { ok: true, text: 'Du bist Mama.\nUnd noch so viel mehr.', lines: 2, chars: 39, w: 940, h: 1162 }; },
  };
  const r = await readInboundContent({ message_id: INCIDENT_MID, message_type: 'post', content: INCIDENT_POST }, deps);
  assert.deepStrictEqual(calls.fetch, [[INCIDENT_MID, INCIDENT_KEY]], `取图调用不对：${JSON.stringify(calls.fetch)}`);
  assert.deepStrictEqual(calls.ocr, ['/tmp/假图.img'], 'OCR 必须拿到取回来的那个路径');
  assert.strictEqual(calls.cleaned, 1, '字节用完必须清理 —— 豁免是「过一遍 OCR」，不是「留下来」');
  assert.ok(r.text.includes('评审下下这个图片，能过吗？'), '正文不能因为带图就丢掉');
  const block = buildImageBlock(r);
  assert.ok(block.includes('Du bist Mama.'), '图内文字必须进图块');
  assert.ok(/画面本身/.test(block), '图块必须写明「画面本身看不到」—— 否则模型会把读到的字说成看过这张图');
  assert.ok(/OCR/.test(block), '图块必须写明这是 OCR 读数（可能有识别错误），不许当逐字原文引用');
});

await t('行为级·取不到 ≠ 图上没字（两句话必须不一样）', async () => {
  const { readInboundContent, buildImageBlock } = await import('./agent/agent.mjs');
  const only = { message_id: 'om_test', message_type: 'image', content: '{"image_key":"img_x"}' };

  const fail = await readInboundContent(only, {
    fetchImage: async () => ({ path: null, bytes: 0, error: '取图失败 code=99991672 msg=权限不足', cleanup: () => {} }),
  });
  assert.ok(fail.images[0].failed, '取不到必须落成 failed');
  const bFail = buildImageBlock(fail);
  assert.ok(bFail.includes('这一张我读不到') && bFail.includes('99991672'), `取不到的措辞不对：${bFail}`);
  assert.ok(!/没有可读的文字/.test(bFail), '取不到**不许**说成「图上没字」—— 那是把一个否定结论说过头');

  const empty = await readInboundContent(only, {
    fetchImage: async () => ({ path: '/tmp/空.img', bytes: 1200, error: null, cleanup: () => {} }),
    ocr: async () => ({ ok: true, text: '', lines: 0, chars: 0, w: 10, h: 10 }),
  });
  assert.strictEqual(empty.images[0].ocrEmpty, true, 'OCR 成功但没文字，要落成 ocrEmpty');
  const bEmpty = buildImageBlock(empty);
  assert.ok(bEmpty.includes('没识别出任何文字'), `图上没字的措辞不对：${bEmpty}`);
  assert.ok(!/读不到/.test(bEmpty), '图上没字**不许**说成「我读不到」—— 两件事引出的下一步不同');
});

await t('行为级·OCR 抛异常也要删掉临时件（finally）', async () => {
  const { readInboundContent } = await import('./agent/agent.mjs');
  let cleaned = 0;
  const r = await readInboundContent(
    { message_id: 'om_test', message_type: 'image', content: '{"image_key":"img_x"}' },
    {
      fetchImage: async () => ({ path: '/tmp/图.img', bytes: 10, error: null, cleanup: () => { cleaned++; } }),
      ocr: async () => { throw new Error('OCR 进程炸了'); },
    });
  assert.strictEqual(cleaned, 1, 'OCR 抛了也必须 clean —— 否则一次故障就留下一堆临时图');
  assert.ok(String(r.images[0].failed).includes('取图抛异常') || String(r.images[0].failed).includes('炸了'),
    `异常必须落在 failed 里说清楚，实际：${JSON.stringify(r.images[0])}`);
});

await t('行为级·图数上限：超出的要说话，不许静默少读', async () => {
  const { readInboundContent, buildImageBlock, MAX_IMAGES_PER_MESSAGE } = await import('./agent/agent.mjs');
  let fetches = 0;
  const many = { message_id: 'om_many', message_type: 'post',
    content: JSON.stringify({ content: Array.from({ length: MAX_IMAGES_PER_MESSAGE + 2 },
      (_, i) => [{ tag: 'img', image_key: `img_${i}` }]) }) };
  const r = await readInboundContent(many, {
    fetchImage: async () => { fetches++; return { path: '/tmp/x.img', bytes: 5, error: null, cleanup: () => {} }; },
    ocr: async () => ({ ok: true, text: 'x', lines: 1, chars: 1 }),
  });
  assert.strictEqual(fetches, MAX_IMAGES_PER_MESSAGE, `最多只许取 ${MAX_IMAGES_PER_MESSAGE} 张，实际取了 ${fetches}`);
  assert.strictEqual(r.skippedImages, 2, '没读的那两张必须记数');
  assert.ok(buildImageBlock(r).includes('还有 2 张图'), '没读的必须说出来 —— 静默少读会让结论比输入大');
});

await t('端到端·file 类型走 handleMessage：一次都不取字节，且说「按规矩不取」', async () => {
  const { handleMessage } = await import('./agent/agent.mjs');
  let fetches = 0;
  const r = await handleMessage({
    message: { message_id: `om_file_${Date.now()}`, chat_id: 'oc_test', chat_type: 'p2p',
               message_type: 'file', content: '{"file_key":"file_v3_abc","file_name":"材料.xlsx"}' },
    sender: { sender_id: { open_id: 'ou_test' } },
  }, { deps: { fetchImage: async () => { fetches++; return { path: null, bytes: 0, error: 'x', cleanup: () => {} }; } } });
  assert.strictEqual(fetches, 0, '附件类型一次都不许取字节 —— 这是 §2.6 红线的执行点');
  assert.strictEqual(r.reason, 'attachment_not_taken');
  assert.ok(/按规矩|不让下载/.test(r.reply), `话术要写「规矩」，实际：${r.reply}`);
  assert.ok(/图片/.test(r.reply), '要顺带说清「图片不一样（可以直接发我）」—— 否则她还是不知道下一步能怎么做');
});

await t('端到端·只有图且读不出字 → 如实说 + 给下一步（不许编内容）', async () => {
  const { handleMessage } = await import('./agent/agent.mjs');
  const r = await handleMessage({
    message: { message_id: `om_img_${Date.now()}`, chat_id: 'oc_test', chat_type: 'p2p',
               message_type: 'image', content: '{"image_key":"img_v3_only"}' },
    sender: { sender_id: { open_id: 'ou_test' } },
  }, { deps: {
    fetchImage: async () => ({ path: '/tmp/only.img', bytes: 999, error: null, cleanup: () => {} }),
    ocr: async () => ({ ok: true, text: '   ', lines: 0, chars: 0 }),
  } });
  assert.strictEqual(r.reason, 'image_unreadable');
  assert.ok(/没读出内容/.test(r.reply), `要说清「没读出内容」，实际：${r.reply}`);
  assert.ok(/贴过来|再发/.test(r.reply), '要给一条走得通的路');
});

await t('反向对照·上面几条不是空转（喂旧形状必须红）', async () => {
  const { imageKeysOf } = await import('./agent/feishu.mjs');
  // ① 假否定样本：旧代码按 `JSON.parse(content).text` 读 post → 空串。这个断言证明那条路确实是空的。
  const naive = (() => { try { return JSON.parse(INCIDENT_POST).text ?? ''; } catch { return ''; } })();
  assert.strictEqual(naive, '', '旧的读法在 post 上就该是空 —— 若这条变成非空，说明样本不再代表事故');
  // ② 正面样本非空：证明 imageKeysOf 不是恒回空数组（恒真断言比没有断言更糟）
  assert.ok(imageKeysOf('post', INCIDENT_POST).length > 0, 'imageKeysOf 在真 payload 上必须非空');
  // ③ 附件样本恒空：证明类型闸门真的在（不是碰巧）
  assert.strictEqual(imageKeysOf('file', '{"file_key":"f","image_key":"img_sneaky"}').length, 0,
    '带 image_key 的附件 payload 也必须回空 —— 否则闸门只是「没遇到」而不是「拦住了」');
});


// ─────────────────────────────────────────────────────────────────────────────
// 第 14 组：**这条路的试纸** —— 真跑一次 OCR，而不是喂桩。
//
// 为什么必须有这一组（2026-10-05）：第 13 组全是桩，它证明的是**接线**对不对；
// 「这台机器上 OCR 还跑不跑得起来」它一个字都没说。而这次事故最本质的教训是：
// **守衡读不到图，没有任何东西会变红。** 所以这里放一张本仓自带的试纸
// （`tools/agent/__fixtures__/ocr-sample.png`），每次跑自证都真读一遍：
//   · 读得到 → 这条路是通的（且二进制缺失时会现场编译，编译失败即红）；
//   · 读不到 → 红，并说清是「二进制编不出来」还是「试纸读不出特征串」。
// 反向对照同样重要：**空白试纸必须报「图上没字」，不是「读不出来」** ——
// 只测得出「能读到字」的试纸，测不出「把失败伪装成没字」。
// ─────────────────────────────────────────────────────────────────────────────
console.log('\n═══ 14. 读图的试纸（真跑 OCR；不联网、不碰飞书）═══');

await t('真跑一次 OCR：试纸上的特征串必须读得出来', async () => {
  const v = await import('./agent/vision.mjs');
  assert.ok(fs.existsSync(v.OCR_FIXTURE), `试纸不在：${v.OCR_FIXTURE} —— 没有试纸就没法证明这条路是通的`);
  const r = await v.ocrImage(v.OCR_FIXTURE);
  assert.strictEqual(r.ok, true, `OCR 没跑通（${r.error ?? '未知'}）：${r.detail ?? ''}`);
  assert.ok(String(r.text).toUpperCase().includes(v.OCR_FIXTURE_TOKEN),
    `试纸读到了 ${r.lines} 行，但没有特征串「${v.OCR_FIXTURE_TOKEN}」。读到的是：${String(r.text).slice(0, 200)}`);
});

await t('反向对照·空白试纸必须报「图上没字」，不是「读不出来」', async () => {
  const v = await import('./agent/vision.mjs');
  const b = await v.ocrImage(v.OCR_BLANK_FIXTURE);
  assert.strictEqual(b.ok, true, '空白图必须**成功**返回（ok:true、没有文字），而不是失败');
  assert.strictEqual(String(b.text).trim(), '', `空白图不该读出任何字，实际：${JSON.stringify(b.text)}`);
  assert.notStrictEqual(b.error, 'not_found', '拿错了文件会变成另一种错，这条对照就没意义了');
});

await t('反向对照·文件不存在必须报 not_found（不许伪装成「图上没字」）', async () => {
  const v = await import('./agent/vision.mjs');
  const r = await v.ocrImage('/tmp/绝不存在-ocr-试纸.png');
  assert.strictEqual(r.ok, false);
  assert.strictEqual(r.error, 'not_found', `实际 error=${r.error}`);
  assert.ok(!('text' in r) || !r.text, '读不到时不许回一段空 text（那会被上层读成「图上没字」）');
});

await t('启动自检 preflight：读得出特征串 + 空白对照都对', async () => {
  const v = await import('./agent/vision.mjs');
  const pf = await v.preflight();
  assert.strictEqual(pf.ok, true, `preflight 没过（${pf.error}）：${pf.detail ?? ''}`);
  assert.ok(pf.lines >= 3, `试纸行数太少（${pf.lines}）—— 可能只读到一半`);
  assert.strictEqual(pf.blankOk, true, '反向对照没过：空白试纸没被认成「没字」');
});

// ─────────────────────────────────────────────────────────────────────────────
// 第 15 组：**下次发图的另外两种真实形态**（2026-10-05 补）
//
// 13 组覆盖的是「这条消息里带图」；但真实群/私聊里还有两种常见发法，
// 而它们原先**都会失败**（守衡会回「你这条里没图」—— 而图就在那儿）：
//   ① 「发一张图 → 回它一句『这张能过吗』」：图在**被引用的那条**消息里；
//   ② 群里用富文本（post）@守衡：真实日志里有这个形状（09-23 08:38 那条）。
// 这一组把这两种形状钉住。
// ─────────────────────────────────────────────────────────────────────────────
console.log('\n═══ 15. 引用的那条里的图 + 群里的富文本 @（两种真实形态）═══');

await t('图在被引用的那条消息里（这条只写了一句问话）', async () => {
  const { readInboundContent, buildImageBlock } = await import('./agent/agent.mjs');
  const cur = {
    message_id: 'om_cur', message_type: 'text', content: '{"text":"这张能过吗？"}',
    parent_id: 'om_parent_with_image',
  };
  const calls = [];
  const r = await readInboundContent(cur, {
    // 当前这条没有图 → 必须去读 parent_id 指的那条
    loadParent: async (pid) => {
      calls.push(pid);
      return { msgType: 'post', images: [{ imageKey: 'img_v3_from_parent', width: 800, height: 600 }], text: '' };
    },
    fetchImage: async (mid, key) => ({ path: `/tmp/${key}.img`, bytes: 1234, error: null, cleanup: () => {} }),
    ocr: async () => ({ ok: true, text: '限时五折 立即购买', lines: 2, chars: 10 }),
  });
  assert.deepStrictEqual(calls, ['om_parent_with_image'], `必须只读它引用的那一条，实际读了：${JSON.stringify(calls)}`);
  assert.strictEqual(r.fromParent, true, '要标出「图来自被引用的那条」');
  assert.strictEqual(r.imageCount, 1);
  const b = buildImageBlock(r);
  assert.ok(/引用的那条/.test(b), `图块必须说清来源，实际：${b.slice(0, 120)}`);
  assert.ok(b.includes('限时五折'), '被引用那条里的图，字也要进来');
});

await t('被引用的那条**读不到**时：说「未测」，不许说成「没图」', async () => {
  const { readInboundContent, buildImageBlock } = await import('./agent/agent.mjs');
  const r = await readInboundContent(
    { message_id: 'om_cur2', message_type: 'text', content: '{"text":"这张呢"}', parent_id: 'om_x' },
    { loadParent: async () => ({ error: '回读消息失败 code=230002 msg=不在可见范围' }) });
  assert.strictEqual(r.imageCount, 0);
  assert.strictEqual(r.parentNote?.kind, 'parent_unreadable', `actual=${JSON.stringify(r.parentNote)}`);
  // 图块是空的（没有图），但那句话要在「读不了」那一支里说出来 —— 这里断言数据层
  assert.strictEqual(buildImageBlock(r), '', '没有图时不该产出图块');
  assert.ok(/不在可见范围/.test(r.parentNote.error), '原因要带出来，方便排查');
});

await t('反向对照·**不许翻历史**：没带图、也没引用 → 一张都不许取', async () => {
  const { readInboundContent } = await import('./agent/agent.mjs');
  let fetched = 0, parentReads = 0;
  const r = await readInboundContent(
    { message_id: 'om_plain', message_type: 'text', content: '{"text":"你好"}' },
    { loadParent: async () => { parentReads++; return {}; },
      fetchImage: async () => { fetched++; return { path: null, bytes: 0, error: 'x', cleanup: () => {} }; } });
  assert.strictEqual(fetched, 0, '普通文本消息一次都不许取字节');
  assert.strictEqual(parentReads, 0, '没有 parent_id 时**不许**去读上一条（那正是「翻历史」那条线）');
  assert.strictEqual(r.imageCount, 0);
});

await t('群里的富文本 post（真实 payload 形状）：@守衡 认得出来、正文读得出来', async () => {
  const feishuMod = await import('./agent/feishu.mjs');
  // 逐字取自 PMO/logs/ws_events.jsonl 里 09-23 08:38 那条真实群消息的形状
  const content = '{"title":"","content":[[{"tag":"at","user_id":"@_user_1","user_name":"守衡","style":[]},'
    + '{"tag":"text","text":" 这张图能过吗？","style":[]}],[{"tag":"img","image_key":"img_v3_group_case","width":900,"height":1200}]]}';
  const p = feishuMod.bodyToText('post', content);
  assert.strictEqual(p.parsed, true);
  assert.ok(p.text.includes('@守衡'), `post 的 at 节点要还原成 @真名，实际：${JSON.stringify(p.text)}`);
  const { display, mentions } = feishuMod.resolveMentions(p.text, [
    { key: '@_user_1', name: '守衡', id: { open_id: 'cli_aa2243de0438dcd7' } },
  ]);
  assert.strictEqual(feishuMod.isBotMentioned(mentions), true, 'post 里 @守衡 必须被认出来（否则群里直接跳过不回）');
  // 剥掉 @ 之后应当只剩问题本身 + 一个**图片位置标记**。
  // `[图片]` 是有意留的：它告诉模型「这句话旁边还有一张图」（图的内容在图块里）。
  const q = feishuMod.stripBotMention(display, mentions).trim();
  assert.strictEqual(q, '这张图能过吗？\n[图片]', `实际：${JSON.stringify(q)}`);
  assert.ok(!q.includes('@守衡'), '不能让 @守衡 留在问题里（否则模型会把它当正文去答）');
  assert.strictEqual(feishuMod.imageKeysOf('post', content).length, 1, '群里的 post 也要认出那张图');
});

await t('端到端·群里 post + @守衡 + 图（用桩，不联网）：必须走到模型那一侧', async () => {
  const { readInboundContent, buildImageBlock } = await import('./agent/agent.mjs');
  const content = '{"title":"","content":[[{"tag":"at","user_id":"@_user_1","user_name":"守衡","style":[]},'
    + '{"tag":"text","text":" 这张图能过吗？","style":[]}],[{"tag":"img","image_key":"img_v3_group_case","width":900,"height":1200}]]}';
  const r = await readInboundContent(
    { message_id: 'om_group_post', message_type: 'post', chat_type: 'group', content },
    { fetchImage: async () => ({ path: '/tmp/g.img', bytes: 999, error: null, cleanup: () => {} }),
      ocr: async () => ({ ok: true, text: 'Momcozy 吸奶器 五折', lines: 1, chars: 16, w: 900, h: 1200 }) });
  assert.strictEqual(r.imageCount, 1);
  assert.ok(buildImageBlock(r).includes('Momcozy 吸奶器 五折'), '图上文字要进图块');
  const feishuMod = await import('./agent/feishu.mjs');
  const { display, mentions } = feishuMod.resolveMentions(r.text,
    [{ key: '@_user_1', name: '守衡', id: { open_id: 'cli_aa2243de0438dcd7' } }]);
  assert.strictEqual(feishuMod.isBotMentioned(mentions), true);
  assert.strictEqual(feishuMod.stripBotMention(display, mentions).trim(), '这张图能过吗？\n[图片]');
});

// ─────────────────────────────────────────────────────────────────────────────
// 第 16 组：**视频** —— §2.6 窄豁免 2026-10-05 加宽后的形状。
//
// 背景（真实事故）：10-05 09:22:43 委托方私聊发了一条视频
// （`type=file` + `file_v3_00166_48a0a140…` + `momcozy-…-hero-1080p.mp4`），
// 守衡 **0 毫秒**回了 108 字的拒绝。她随后追问「这个视频能过审吗？」——
// 也就是「发视频」这条路当时**一条都不通**。
//
// 加宽的形状（Owner 现场确认）与图片那条**完全一样**：同一个取字节调用点、
// 同样只写临时目录、同样用完即删、抽帧与转写全在本机。
// 没松的：`file` 里的**非视频附件**（xlsx / pdf / docx…）、群历史、云文档、多维表格。
// 这一组就是把「宽到哪、没到哪」变成会红的断言。
// ─────────────────────────────────────────────────────────────────────────────
console.log('\n═══ 16. 视频那条路（窄豁免加宽后的形状）═══');

const VIDEO_MEDIA_MSG = { message_id: 'om_vid_media', message_type: 'media',
  content: JSON.stringify({ file_key: 'file_v3_00166_48a0a140', file_name: 'hero-1080p.mp4',
                            duration: 14960, image_key: 'img_v3_cover' }) };
const VIDEO_FILE_MSG = { message_id: 'om_vid_file', message_type: 'file',
  content: JSON.stringify({ file_key: 'file_v3_00166_48a0a140',
                            file_name: 'momcozy-one-click-foldable-baby-playard-hero-1080p.mp4' }) };
const XLSX_FILE_MSG = { message_id: 'om_xlsx', message_type: 'file',
  content: JSON.stringify({ file_key: 'file_v3_xlsx', file_name: '2026内容排期.xlsx' }) };
const PDF_FILE_MSG = { message_id: 'om_pdf', message_type: 'file',
  content: JSON.stringify({ file_key: 'file_v3_pdf', file_name: '检测报告.pdf' }) };
const AUDIO_MSG = { message_id: 'om_audio', message_type: 'audio',
  content: JSON.stringify({ file_key: 'file_v3_audio', duration: 3000 }) };

/** 一个「读视频」的桩：把真实现的返回形状照抄一份，但一个字节都不落盘。 */
function stubReadVideo(result) {
  return async () => ({
    ok: true,
    meta: { duration_s: 14.96, w: 1920, h: 1080, fps: 25, has_audio: true, audio_channels: 2, audio_rate: 48000 },
    frames: [{ t_s: 0.94, text: 'MOMCOZY', lines: 1 }, { t_s: 8.42, text: 'MOMCOZY', lines: 1 }],
    framesRead: 2, framesFailed: 0,
    ocrText: '[0.94s] MOMCOZY\n[8.42s] MOMCOZY', ocrChars: 16, ocrTruncated: false,
    transcript: { ok: true, text: 'Meet the playard that folds in one second.', chars: 42, locale: 'en-US' },
    notes: [], ms: 3500, cleanup: () => {},
    ...result,
  });
}

await t('视频在哪：只认 media 与「名字是视频的 file」', () => {
  assert.strictEqual(feishu.videoKeysOf('media', VIDEO_MEDIA_MSG.content).length, 1, 'media 就是视频消息');
  assert.strictEqual(feishu.videoKeysOf('file', VIDEO_FILE_MSG.content).length, 1,
    '名字是 .mp4 的 file 也算视频 —— 委托方那条就是这么发过来的');
  for (const [name, m] of [['xlsx', XLSX_FILE_MSG], ['pdf', PDF_FILE_MSG], ['audio', AUDIO_MSG]]) {
    assert.strictEqual(feishu.videoKeysOf(m.message_type, m.content).length, 0,
      `${name} 不许被当成视频 —— 那不在豁免里`);
  }
  // 图片那条支路不许被视频影响：media 里带 image_key（封面帧）也**不是**一张要读的图
  assert.strictEqual(feishu.imageKeysOf('media', VIDEO_MEDIA_MSG.content).length, 0,
    'media 里的 image_key 是封面帧，不是人发来的图');
});

await t('红线行为级·file 里的非视频附件：一次字节都不许取', async () => {
  const { readInboundContent } = await import('./agent/agent.mjs');
  for (const m of [XLSX_FILE_MSG, PDF_FILE_MSG, AUDIO_MSG]) {
    let fetches = 0;
    const r = await readInboundContent(m, {
      fetchVideo: async () => { fetches++; return { path: '/tmp/不该到这里', bytes: 1, error: null, cleanup: () => {} }; },
      fetchImage: async () => { fetches++; return { path: '/tmp/不该到这里', bytes: 1, error: null, cleanup: () => {} }; },
    });
    assert.strictEqual(fetches, 0, `${m.content} 一次网络调用都不许发（红线）`);
    assert.strictEqual(r.videoCount, 0, `${m.content} 不许被当成视频`);
    assert.ok(r.attachment, '非视频附件仍然要落成 attachment（按规矩不取）');
  }
});

await t('行为级·media 消息：真取字节 + 真读（桩），视频块里带帧文字与转写', async () => {
  const { readInboundContent, buildVideoBlock } = await import('./agent/agent.mjs');
  const calls = { fetch: [], read: [], cleaned: 0 };
  const r = await readInboundContent(VIDEO_MEDIA_MSG, {
    fetchVideo: async (mid, key, opt) => {
      calls.fetch.push([mid, key, opt?.ext]);
      return { path: '/tmp/假视频.mp4', bytes: 13387714, error: null, cleanup: () => { calls.cleaned++; } };
    },
    readVideoFn: async (p) => { calls.read.push(p); return stubReadVideo()(); },
  });
  assert.deepStrictEqual(calls.fetch, [['om_vid_media', 'file_v3_00166_48a0a140', '.mp4']],
    `取视频调用不对：${JSON.stringify(calls.fetch)}`);
  assert.deepStrictEqual(calls.read, ['/tmp/假视频.mp4'], '读视频必须拿到取回来的那个路径');
  assert.strictEqual(calls.cleaned, 1, '字节用完必须清理 —— 豁免是「过一遍」，不是「留下来」');
  const block = buildVideoBlock(r);
  assert.ok(block.includes('MOMCOZY'), '帧上的字必须进视频块');
  assert.ok(block.includes('folds in one second'), '音轨转写必须进视频块');
  assert.ok(/画面/.test(block) && /我看得到|看不到|抽样/.test(block),
    '视频块必须写明「只看到抽样的这几帧」—— 否则模型会说「整条视频我都看了」');
  assert.ok(/14\.96|15/.test(block), '时长要进块（判「够不够 60 秒」要用）');
});

await t('行为级·file 类型的视频消息（真实 payload）也走同一条路', async () => {
  const { readInboundContent, buildVideoBlock } = await import('./agent/agent.mjs');
  const r = await readInboundContent(VIDEO_FILE_MSG, {
    fetchVideo: async () => ({ path: '/tmp/真视频.mp4', bytes: 13387714, error: null, cleanup: () => {} }),
    readVideoFn: async () => stubReadVideo()(),
  });
  assert.strictEqual(r.videoCount, 1);
  assert.strictEqual(r.attachment, null, '是视频就不许再被算成「按规矩不取的附件」');
  assert.ok(buildVideoBlock(r).includes('momcozy-one-click-foldable-baby-playard-hero-1080p.mp4'),
    '文件名要进块（人靠它认自己发的是哪一条）');
});

await t('取不到 ≠ 视频里没东西（两句话必须不一样）', async () => {
  const { readInboundContent, buildVideoBlock } = await import('./agent/agent.mjs');
  const fail = await readInboundContent(VIDEO_MEDIA_MSG, {
    fetchVideo: async () => ({ path: null, bytes: 0, error: '取视频失败 code=99991672 msg=权限不足', cleanup: () => {} }),
  });
  assert.ok(fail.videos[0].failed, '取不到必须落成 failed');
  const b = buildVideoBlock(fail);
  assert.ok(b.includes('这一段我读不到') && b.includes('99991672'), `措辞不对：${b}`);
  assert.ok(!/没有可读文字|没有人说话/.test(b), '取不到**不许**说成「视频里没东西」');
});

await t('三种「声音那侧没有结果」必须分得开', async () => {
  const { readInboundContent, buildVideoBlock } = await import('./agent/agent.mjs');
  const mkVid = (transcript) => readInboundContent(VIDEO_MEDIA_MSG, {
    fetchVideo: async () => ({ path: '/tmp/v.mp4', bytes: 999, error: null, cleanup: () => {} }),
    readVideoFn: async () => stubReadVideo({ transcript })() });
  const deps = { 无音轨: { ok: false, kind: 'no_audio_track' },
                 没人说话: { ok: false, kind: 'no_speech' },
                 未授权: { ok: false, kind: 'not_authorized', hint: '去系统设置里打开语音识别' } };
  const b1 = buildVideoBlock(await mkVid(deps.无音轨));
  assert.ok(/没有音轨/.test(b1) && /是读数，不是转写失败/.test(b1), `无音轨的措辞不对：${b1}`);
  const b2 = buildVideoBlock(await mkVid(deps.没人说话));
  assert.ok(/没有人说话/.test(b2) && /是读数/.test(b2), `没人说话的措辞不对：${b2}`);
  const b3 = buildVideoBlock(await mkVid(deps.未授权));
  assert.ok(/没跑成/.test(b3), `未授权的措辞不对：${b3}`);
  // ★ 判据要分清「说」与「否认」（本项目 V25b 踩过这个坑）：这里出现「没有说话」
  //   是**在否认它**（「不要当成『没有说话』」），那正是要的写法；
  //   要拦的是**把未测直接说成没人说话**。
  assert.ok(/未测/.test(b3), `转写没跑成必须明写成「未测」：${b3}`);
  assert.ok(/不要当成/.test(b3), `必须明写「不要当成『没有说话』」—— 否则上层会把它读成读数：${b3}`);
  assert.ok(!/音轨转写：(是)?.*没有人说话/.test(b3), `未测不许被写成读数：${b3}`);
});

await t('媒材块里必须挂着「这是送审素材 → 走 kb_review_chain」那一句', async () => {
  const { readInboundContent, buildImageBlock, buildVideoBlock, MEDIA_ROUTE_HINT } = await import('./agent/agent.mjs');
  // 图块
  const img = await readInboundContent({ message_id: 'om_r1', message_type: 'image', content: '{"image_key":"img_x"}' },
    { fetchImage: async () => ({ path: '/tmp/r.img', bytes: 9, error: null, cleanup: () => {} }),
      ocr: async () => ({ ok: true, text: 'MOMCOZY 吸奶器', lines: 1, chars: 12 }) });
  const bi = buildImageBlock(img);
  assert.ok(bi.includes(MEDIA_ROUTE_HINT), '图块里必须有这句 —— 否则模型只会描述「我读到了什么」');
  assert.ok(bi.includes('kb_review_chain'), '图块里必须点名那条链');
  // 视频块
  const vid = await readInboundContent(VIDEO_FILE_MSG, {
    fetchVideo: async () => ({ path: '/tmp/r.mp4', bytes: 9, error: null, cleanup: () => {} }),
    readVideoFn: async () => stubReadVideo()() });
  const bv = buildVideoBlock(vid);
  assert.ok(bv.includes(MEDIA_ROUTE_HINT), '视频块里必须有同一句');
  // ★ 反向对照：没有媒材时不许出现这句（否则它就不是「跟着媒材走」的）
  assert.strictEqual(buildImageBlock({ imageCount: 0 }), '', '没有图时图块必须是空的');
  assert.strictEqual(buildVideoBlock({ videoCount: 0 }), '', '没有视频时视频块必须是空的');
});

await t('「带了媒材却没起链」这件事本身必须有个读数（不是一行没出现的日志）', async () => {
  const { mediaWithoutChain } = await import('./agent/agent.mjs');
  const chainOk = { tool: 'kb_review_chain', ok: true };
  // ① 带了视频、起了链 → 没问题
  assert.strictEqual(mediaWithoutChain({ media: { images: 0, videos: 1 }, toolTrace: [chainOk] }), null,
    '起了链就不该报警');
  // ② 带了视频、一次工具都没调 → 必须报（这就是那次事故的形状）
  const r2 = mediaWithoutChain({ media: { images: 0, videos: 1 }, toolTrace: [] });
  assert.ok(r2 && r2.media === 1 && r2.tools.length === 0, `实际 ${JSON.stringify(r2)}`);
  // ③ 带了图、只调了别的工具 → 也要报
  const r3 = mediaWithoutChain({ media: { images: 2, videos: 0 },
                                toolTrace: [{ tool: 'search_workspace', ok: true }] });
  assert.ok(r3 && r3.media === 2 && r3.tools.includes('search_workspace'), `实际 ${JSON.stringify(r3)}`);
  // ④ **反向对照**：没带媒材时永远不许报（否则它对每一轮纯文字都在叫）
  assert.strictEqual(mediaWithoutChain({ media: { images: 0, videos: 0 }, toolTrace: [] }), null,
    '没媒材时这条不适用');
  assert.strictEqual(mediaWithoutChain({}), null, 'meta 缺字段时不许凭空报');
  // ⑤ **反向对照**：链**跑失败**了不算「起了链」—— 那是要说的另一种话
  const r5 = mediaWithoutChain({ media: { images: 1, videos: 0 },
                                toolTrace: [{ tool: 'kb_review_chain', ok: false }] });
  assert.ok(r5, '链失败必须照样报 —— 否则「跑了但没成」会被记成「跑过了」');
});

await t('★ 反向对照·引用那条的视频：取字节必须用**父消息 id**（用当前 id 会 400）', async () => {
  // 2026-10-09 实测出来的真 bug：key 从被引用的那条取到，取字节却用 `msg.message_id`
  // ⇒ `messageResource.get` 拿「当前 id + 父消息的 file_key」去查 ⇒ **HTTP 400**。
  // Owner 连发三次视频全部失败（日志：「视频 1 段（取自你引用的那条消息）｜读成功 0 · 失败 1」）。
  // ★ 上面那条「引用的那条读得到」的测试**用的是桩**（`fetchVideo: async () => …`），
  //   它只数调用次数、**不看参数** ⇒ 抓不到这个。这一条钉的就是**传进去的 id**。
  const { readInboundContent } = await import('./agent/agent.mjs');
  const PARENT_ID = 'om_vid_file';
  const seen = [];
  const r = await readInboundContent(
    { message_id: 'om_ask_vid', message_type: 'text', content: '{"text":"这条能过吗？"}',
      parent_id: PARENT_ID },
    { loadParent: async () => ({ text: '', images: [], videos: feishu.videoKeysOf('file', VIDEO_FILE_MSG.content) }),
      fetchVideo: async (mid, fk) => { seen.push(mid); return { path: '/tmp/q.mp4', bytes: 9, error: null, cleanup: () => {} }; },
      readVideoFn: async () => stubReadVideo()() });
  assert.strictEqual(seen.length, 1, `取视频应当恰好被调 1 次，实际 ${seen.length} 次`);
  assert.strictEqual(seen[0], PARENT_ID,
    `取字节必须用**被引用那条**的消息 id，实际用了 ${seen[0]} —— 用当前 id 会 HTTP 400`);
  assert.notStrictEqual(seen[0], 'om_ask_vid', '不许用当前消息 id 去取父消息的资源');
  assert.strictEqual(r.fromParent, true);
});

await t('反向对照·引用的那条里的视频读得到；没引用 → 一次都不许取', async () => {
  const { readInboundContent, buildVideoBlock } = await import('./agent/agent.mjs');
  const ask = { message_id: 'om_ask_vid', message_type: 'text', content: '{"text":"这条能过吗？"}',
                parent_id: 'om_vid_file' };
  let fetches = 0;
  const quoted = await readInboundContent(ask, {
    loadParent: async () => ({ text: '', images: [], videos: feishu.videoKeysOf('file', VIDEO_FILE_MSG.content) }),
    fetchVideo: async () => { fetches++; return { path: '/tmp/q.mp4', bytes: 9, error: null, cleanup: () => {} }; },
    readVideoFn: async () => stubReadVideo()(),
  });
  assert.strictEqual(fetches, 1, '回复一条带视频的消息时，那条视频必须读得到');
  assert.strictEqual(quoted.fromParent, true);
  assert.ok(buildVideoBlock(quoted).includes('引用的那条消息'), '要写明视频是从引用的那条取的');

  // ★ 独立的第二条：**没有 parent_id 时一条都不许取** ——
  //   「看引用」滑成「顺历史把群里的视频捞一遍」正是红线要防的事。
  let fetches2 = 0;
  const noQuote = await readInboundContent(
    { message_id: 'om_noquote', message_type: 'text', content: '{"text":"视频能过吗？"}' },
    { loadParent: async () => { throw new Error('没有 parent_id 就不该去回读任何东西'); },
      fetchVideo: async () => { fetches2++; return { path: '/tmp/x.mp4', bytes: 9, error: null, cleanup: () => {} }; } });
  assert.strictEqual(fetches2, 0, '没带 parent_id → 一次都不许取（不许翻历史）');
  assert.strictEqual(noQuote.videoCount, 0);
});

await t('端到端·视频读数必须进「真正发给模型的那一轮」（不是只进块就算了）', async () => {
  const { readInboundContent, buildImageBlock, buildVideoBlock, buildUserTurn } = await import('./agent/agent.mjs');
  const r = await readInboundContent(VIDEO_FILE_MSG, {
    fetchVideo: async () => ({ path: '/tmp/e2e.mp4', bytes: 999, error: null, cleanup: () => {} }),
    readVideoFn: async () => stubReadVideo()(),
  });
  const turn = buildUserTurn({
    questionText: '审核下这个视频',
    imageBlock: buildImageBlock(r),      // 这条没有图，块是空的
    videoBlock: buildVideoBlock(r),
  });
  assert.ok(turn.startsWith('审核下这个视频'), `人问的话要排在最前：${turn.slice(0, 40)}`);
  assert.ok(turn.includes('关键帧上的文字'), '帧上的字必须真的进那一轮（只说「读到了」不算）');
  assert.ok(turn.includes('MOMCOZY'), '帧 OCR 的原文必须进那一轮');
  assert.ok(turn.includes('folds in one second'), '音轨转写的原文必须进那一轮');
  assert.ok(turn.includes('momcozy-one-click-foldable-baby-playard-hero-1080p.mp4'), '文件名要进那一轮');
  // ★ 反向对照：没有视频块时，那一轮**不许**凭空多出视频字样 ——
  //   否则上面几条可能只是「块恒非空」，而不是「块真的被拼进去了」。
  assert.strictEqual(buildUserTurn({ questionText: '审核下这个视频' }), '审核下这个视频',
    '没有块时那一轮必须逐字等于人问的话');
  assert.strictEqual(buildUserTurn({ questionText: '', videoBlock: buildVideoBlock(r) }),
    buildVideoBlock(r), '只有视频没有文字时，那一轮就该是视频块本身');
});

await t('端到端·非视频附件走 handleMessage：拒答文案里不许把视频也算进「不取」', async () => {
  const { handleMessage } = await import('./agent/agent.mjs');
  const r = await handleMessage({
    message: { ...XLSX_FILE_MSG, message_id: `om_xlsx_${Date.now()}`, chat_id: 'oc_test', chat_type: 'p2p' },
    sender: { sender_id: { open_id: 'ou_test' } },
  });
  assert.strictEqual(r.reason, 'attachment_not_taken');
  assert.ok(!/附件（文件\/语音\/视频）/.test(r.reply),
    `那句老话术是错的（视频已经能读了），不该再出现：${r.reply}`);
  assert.ok(/视频/.test(r.reply) && /直接发我/.test(r.reply),
    `要顺带说清「视频也能直接发我」—— 否则他再发一遍还是听到同一句：${r.reply}`);
});

await t('端到端·视频读不成 → 如实说失败原因，不许说成「视频里没问题」', async () => {
  const { handleMessage } = await import('./agent/agent.mjs');
  const r = await handleMessage({
    message: { ...VIDEO_FILE_MSG, message_id: `om_vid_fail_${Date.now()}`, chat_id: 'oc_test', chat_type: 'p2p' },
    sender: { sender_id: { open_id: 'ou_test' } },
  }, { deps: { fetchVideo: async () => ({ path: null, bytes: 0, error: '取视频失败 code=99991672 msg=权限不足', cleanup: () => {} }) } });
  assert.strictEqual(r.reason, 'video_unreadable', `实际 reason=${r.reason}`);
  assert.ok(/没读成/.test(r.reply), `要说清没读成：${r.reply}`);
  // ★ 同上：这里出现「没问题」是**在否认它**，那正是要的写法。
  assert.ok(/不是「视频里没问题」/.test(r.reply),
    `读不成时必须**明确否认**「视频里没问题」这个读法：${r.reply}`);
});

// ─────────────────────────────────────────────────────────────────────────────
// 第 17 组：**视频这条路的试纸** —— 真跑一次抽帧 + OCR + 本机转写。
//
// 与第 14 组同一个道理：第 16 组全是桩，它证明的是**接线**对不对；
// 「这台机器上视频还读不读得动」它一个字都没说。这一组拿本仓自带的
// `video-sample.mp4`（15KB，由 `base/video_fixture.m` 生成）真读一遍，
// 再拿 `asr-sample.wav` 真转写一遍。
//
// ★ 转写那两条会红得**很有价值**：它红的时候说的是
//   「语音识别没授权 / 模型没装」—— 这两件事只有人点一下才能解决，
//   而在此之前，群里发视频只会听到一句「听不清」。
// ─────────────────────────────────────────────────────────────────────────────
console.log('\n═══ 17. 视频/语音的试纸（真跑；不联网、不碰飞书）═══');

await t('真跑一次读视频：试纸上的特征串必须读得出来', async () => {
  const v = await import('./agent/video.mjs');
  assert.ok(fs.existsSync(v.VIDEO_FIXTURE), `试纸不在：${v.VIDEO_FIXTURE} —— 没有试纸就没法证明这条路是通的`);
  const r = await v.readVideo(v.VIDEO_FIXTURE, { frames: 3 });
  try {
    assert.strictEqual(r.ok, true, `读视频没跑通（${r.error ?? '未知'}）：${r.detail ?? ''}`);
    assert.ok(r.framesRead >= 1, `一帧都没读成：${JSON.stringify(r.frames)}`);
    assert.ok(String(r.ocrText).toUpperCase().includes(v.VIDEO_FIXTURE_TOKEN),
      `抽帧读了 ${r.framesRead} 帧，但没有特征串「${v.VIDEO_FIXTURE_TOKEN}」：${r.ocrText.slice(0, 200)}`);
    assert.strictEqual(r.meta.duration_s > 0, true, `时长必须读得出来，实际 ${r.meta.duration_s}`);
  } finally { r.cleanup?.(); }
});

await t('反向对照·不是视频的文件必须报错，不许说成「视频里没字」', async () => {
  const v = await import('./agent/video.mjs');
  const png = (await import('./agent/vision.mjs')).OCR_FIXTURE;
  const r = await v.readVideo(png, { frames: 2 });
  try {
    assert.strictEqual(r.ok, false, '拿一张 PNG 当视频喂，必须失败 —— 成功就等于「解不开」被伪装成「读得到」');
    assert.ok(!r.ocrText, '失败时不许回一段空 ocrText（那会被上层读成「画面上没字」）');
  } finally { r.cleanup?.(); }
});

await t('反向对照·文件不存在必须报 not_found（不许伪装成「视频里没字」）', async () => {
  const v = await import('./agent/video.mjs');
  const r = await v.readVideo('/tmp/绝不存在-视频试纸.mp4');
  try {
    assert.strictEqual(r.ok, false);
    assert.strictEqual(r.error, 'not_found', `实际 error=${r.error}`);
  } finally { r.cleanup?.(); }
});

await t('启动自检 video.preflight：抽帧 + OCR 特征串都对', async () => {
  const v = await import('./agent/video.mjs');
  const pf = await v.preflight();
  assert.strictEqual(pf.ok, true, `视频自检没过：${pf.error ?? ''} ${pf.detail ?? ''}`);
  assert.ok(pf.n_frames >= 1, `抽出帧数不对：${pf.n_frames}`);
});

await t('真跑一次本机转写：试纸那句话必须转得出来（这条红了就是「语音识别没授权/模型没装」）', async () => {
  const a = await import('./agent/asr.mjs');
  const pf = await a.preflight();
  assert.strictEqual(pf.ok, true,
    `ASR 自检没过：${pf.error ?? ''} ${pf.hint ?? ''} ${pf.detail ?? ''}\n`
    + '       —— 授权没给或模型没装时，视频的「口播/旁白」这一半就是**未测**（不是「没有人说话」）');
  assert.ok(String(pf.text ?? '').includes(a.ASR_FIXTURE_TOKEN), `转写结果里没有特征串：${pf.text}`);
});

await t('反向对照·音频里没人说话 ≠ 转写没跑成（两种必须分得开）', async () => {
  const a = await import('./agent/asr.mjs');
  // 一段**真音频**：本仓试纸（有人说话）。先证明它转得出来，再证明「没声音」是另一种结果。
  const okRun = await a.transcribe(a.ASR_FIXTURE, { locales: ['zh-CN'] });
  assert.strictEqual(okRun.ok, true, `试纸都转不出来，这条对照就没意义了：${okRun.kind}`);
  // 静音 wav：44 字节头 + 1 秒 22050Hz 单声道 16bit 全零
  const silent = '/tmp/shouheng-silence-control.wav';
  const buf = Buffer.alloc(44 + 22050 * 2, 0);
  buf.write('RIFF', 0); buf.writeUInt32LE(36 + 22050 * 2, 4); buf.write('WAVEfmt ', 8);
  buf.writeUInt32LE(16, 16); buf.writeUInt16LE(1, 20); buf.writeUInt16LE(1, 22);
  buf.writeUInt32LE(22050, 24); buf.writeUInt32LE(22050 * 2, 28); buf.writeUInt16LE(2, 32);
  buf.writeUInt16LE(16, 34); buf.write('data', 36); buf.writeUInt32LE(22050 * 2, 40);
  fs.writeFileSync(silent, buf);
  const quiet = await a.transcribe(silent, { locales: ['zh-CN'] });
  assert.strictEqual(quiet.ok, false);
  assert.strictEqual(quiet.kind, 'no_speech',
    `静音音频必须是「没有人说话」这一类读数，实际 kind=${quiet.kind} error=${quiet.error ?? ''}`);
  assert.ok(quiet.hint, '「没有人说话」必须带一句说明，否则上层会把它写成「转写失败」');
});

// ── 2026-10-08 加的：**语种自洽** —— 「错的结果不许长得像成功的结果」 ──────────
//
// 病灶（当天实测，刘华丽那条 `知识库视频-WhatsApp-2026-10-06.mp4`）：
//   `transcribe()` 是「第一个 `ok` 就 return」，而默认语序 `['zh-CN','en-US']` 中文优先
//   ⇒ **英文音轨被按中文识别**，拿到一段胡话却带 `ok:true` + `on_device:true`；
//   下游 `buildVideoBlock` 原来会把它印成「音轨转写（本机识别，逐字）」，
//   于是守衡拿胡话当口播去引用。**比「读不准」更坏的是它长得像成功。**
//
// ★ 下面两条用例里的字符串**逐字取自当天的实测输出**，不是编的。
await t('语种自洽·实测那段胡话必须判「与 zh-CN 不符」、那段正确英文必须判「自洽」', async () => {
  const a = await import('./agent/asr.mjs');
  // 逐字取自实测：同一段音轨，只换语种
  const GARBAGE_ZH = "Let die for them online one more but if it more one I love the matter "
    + "speed and it's much is for me do dick a bad and thing";
  const GOOD_EN = 'Personalities for the mom cause illness one more because it feels more '
    + 'comfortable I love the mass feature and it is much easier for me to take apart and clean';
  const GOOD_ZH = '守恒语音自检这是一段测试音频用来确认本机转写这条路是通的';

  assert.strictEqual(a.checkScript('zh-CN', GARBAGE_ZH).ok, false,
    '英文音轨被按中文识别出来的胡话，必须判「不符」—— 判成自洽就等于把胡话放行');
  assert.strictEqual(a.checkScript('en-US', GOOD_EN).ok, true, '真英文转写必须判自洽');
  assert.strictEqual(a.checkScript('zh-CN', GOOD_ZH).ok, true, '真中文转写必须判自洽');
  assert.strictEqual(a.checkScript('en-US', GOOD_ZH).ok, false, '中文字按英文识别也要判不符');
  assert.strictEqual(a.checkScript('zh-CN', '').ok, true, '空结果不归这条判（另有 chars=0 的判据）');
  assert.strictEqual(a.checkScript('ja-JP', GARBAGE_ZH).ok, true,
    '不认识的语种**不许判**——认不出来就下结论，就是「比输入大」');
});

await t('语种顺序·画面文字是英文时必须英文优先（否则胡话仍然会发生）', async () => {
  const a = await import('./agent/asr.mjs');
  const en = a.orderLocalesByText('Momcozy Wellness 1 vs Eufy S1 Pro I love the massage feature '
    + 'only 5 washable parts');
  assert.strictEqual(en.locales[0], 'en-US', `英文画面文字必须英文优先，实际 ${JSON.stringify(en.locales)}`);
  assert.ok(en.basis && /拉丁/.test(en.basis), '必须给出可复核的依据，而不是一个写死的顺序');
  const zh = a.orderLocalesByText('中国6岁以下儿童就寝问题和夜醒治疗指南 推荐意见 证据等级 睡眠卫生');
  assert.strictEqual(zh.locales[0], 'zh-CN', `中文画面文字必须中文优先，实际 ${JSON.stringify(zh.locales)}`);
  // 反例：画面没字时**不许装作判出来了**
  const none = a.orderLocalesByText('M5');
  assert.strictEqual(none.decided, false, '可判字符太少时必须承认「语种未定」');
  assert.deepStrictEqual(none.locales, a.ASR_LOCALES, '语种未定时必须回默认语序（顺序不许被悄悄改掉）');
});

await t('★ 主机制·readVideo 必须把「画面文字判出来的语序」真的交给转写（桩，钉接线）', async () => {
  // 这条钉的是**主机制**：画面 OCR 已经先跑完，语种由它定 —— 不是靠写死的顺序。
  // ★ 为什么主机制是排序而不是「事后自洽检查」（同一天实测出来的边界）：
  //   字集检查只能抓一个方向 —— 「该语种的特征字**一个都没有**」。
  //   反方向抓不到：中文音轨按 en-US 识别出来的是**看着像英文的胡话**
  //   （实测试纸：`Show her the Joshua and social opinion you like shit and Benji I see your shit`），
  //   它字面上有拉丁字母、自洽检查会放行。所以**顺序对了才是根本**，自洽检查只当网。
  //
  // ⚠️ 为什么用 `audio-sample.m4a` 而不是 `video-sample.mp4`：后者是**纯画面、没有音轨**
  //   ⇒ `readVideo()` 走 `no_audio_track`、**根本不调 `asrFn`**，接线对不对它一个字都不说。
  const v = await import('./agent/video.mjs');
  const a = await import('./agent/asr.mjs');
  assert.ok(fs.existsSync(a.ASR_AUDIO_FIXTURE),
    `带音轨的试纸不在：${a.ASR_AUDIO_FIXTURE}（生成源码 base/asr_audio_fixture.sh）`);
  let seen = 'NOT_CALLED';
  const stub = async (wav, opt) => {
    seen = opt?.locales ?? null;
    return { ok: false, kind: 'no_audio_track', hint: '（桩：本条只验语序接线，不真转写）' };
  };
  const r = await v.readVideo(a.ASR_AUDIO_FIXTURE, { frames: 2, asrFn: stub });
  try {
    assert.notStrictEqual(seen, 'NOT_CALLED',
      'asrFn 一次都没被调到 —— 那这一段根本没走转写这条路（这条断言就是为它写的）');
    // 这张试纸**没有视频轨** ⇒ 画面文字是空的 ⇒ 语种判不出来 ⇒ **必须回默认语序**
    assert.deepStrictEqual(seen, a.ASR_LOCALES,
      `没有画面文字时必须回默认语序，实际 ${JSON.stringify(seen)}`);
    assert.ok(String(r.transcript?.locale_basis ?? '').includes('语种未定'),
      `语种判不出来时必须**如实写「语种未定」**，实际 ${JSON.stringify(r.transcript?.locale_basis)}`);
  } finally { r.cleanup?.(); }

  // 另一半：有画面文字时，喂给 `orderLocalesByText` 的**必须是画面 OCR 的文本**。
  // 这一截靠源码断言钉住（与 `verify_feishu_index.py` 的 M 段同一个路子：
  // 「唯一调用点」这种接线，行为级测不到，就只能看源码）。
  const src = fs.readFileSync(new URL('./agent/video.mjs', import.meta.url), 'utf8');
  assert.ok(/orderLocalesByText\(frameOcr/.test(src),
    '`video.mjs` 里必须把 `frameOcr` 的文本喂给 `orderLocalesByText()` —— '
    + '换成别的来源（或写死语序）就等于这条修复没做');
});

await t('反向对照·语序不许被写死：中英两种画面文字必须给出**不同**的语序', async () => {
  const a = await import('./agent/asr.mjs');
  const zh = a.orderLocalesByText('中国6岁以下儿童就寝问题和夜醒治疗指南 推荐意见 证据等级 睡眠卫生');
  assert.deepStrictEqual(zh.locales, ['zh-CN', 'en-US'],
    `中文画面文字必须中文优先，实际 ${JSON.stringify(zh.locales)}`);
  const en = a.orderLocalesByText(
    'Momcozy Wellness 1 vs Eufy S1 Pro I love the massage feature only 5 washable parts');
  assert.deepStrictEqual(en.locales, ['en-US', 'zh-CN'],
    `英文画面文字必须英文优先，实际 ${JSON.stringify(en.locales)}`);
  assert.notDeepStrictEqual(zh.locales, en.locales,
    '中英两种画面文字的语序**必须不同** —— 相同就说明语序是写死的，这条修复等于没做');
});

// ─────────────────────────────────────────────────────────────────────────────
// 第 18 组：**送审闸门** —— 「工作流必须走」这句话的执行点。
//
// 委托方 2026-10-05 第三次重申：@守衡 提问/图片/视频/链接 → 走 L4→L5→L6→L7 + 评审链
// → 出报告溯源（L0）→ 写飞书。而那条链一直是通的（跑过 691s / 771s / 1809s），
// **缺的是触发**：在此之前「算不算送审」只写在人设里 —— 人设是声明，不是约束。
// 09:22 那条视频就是证据：模型没想起要调链，读到了 51 个字却给不出结论，
// 而盘上唯一的痕迹是**一行没有出现的日志**。
//
// 这一组验的就是「拦它的那几行」：判据（纯函数）、闸门（能被调用的函数）、
// 以及**接线**（`handleMessage` 真的调了它）。
// ─────────────────────────────────────────────────────────────────────────────
console.log('\n═══ 18. 送审闸门（该走链的必须走，不该走的必须闭嘴）═══');

await t('什么算送审：媒材 / 链接 / 关键词 / 够长 → 走；闲聊 → 不走', async () => {
  const g = await import('./agent/review_gate.mjs');
  const yes = [
    ['光秃秃的视频', { videoCount: 1, text: '' }, 'media'],
    ['光秃秃的图', { imageCount: 1, text: '' }, 'media'],
    ['图 + 一句问', { imageCount: 1, text: '这张能过吗' }, 'media'],
    ['飞书链接', { text: '你读一下 https://momcozy-in.feishu.cn/wiki/abc?table=tbl1' }, 'link'],
    ['外部链接', { text: '看看这个 https://example.com/p/1' }, 'link'],
    ['短问句 + 关键词', { text: '这句能不能发' }, 'text'],
    ['只有关键词', { text: '审一下' }, 'text'],
    ['够长的纯文字', { text: '我们打算下个月在美国站主图里把这句话放上去，想请你先看一下这段文案' }, 'text'],
  ];
  for (const [name, input, kind] of yes) {
    const r = g.isSubmission(input);
    assert.strictEqual(r.yes, true, `${name} 必须判成送审（实际：${r.why}）`);
    assert.strictEqual(r.kind, kind, `${name} 的 kind 应为 ${kind}，实际 ${r.kind}`);
  }
  // ★ 反向对照：不该触发的必须**闭嘴** —— 否则每句「在吗」都跑 10~30 分钟并写一条飞书
  const no = [['在吗', { text: '在吗' }], ['问能力', { text: '你能干什么' }],
              ['短确认', { text: '收到' }], ['空消息', { text: '' }],
              ['空对象', {}]];
  for (const [name, input] of no) {
    const r = g.isSubmission(input);
    assert.strictEqual(r.yes, false, `${name} 不许判成送审（实际：${r.why}）`);
  }
  // 反向对照的第二面：把长度闸门挪掉会怎样 —— 证明那条阈值真的在拦
  const just = '一二三四五六七八九十一二三四五六七八九十一二三四五六七八九';   // 29 字
  assert.strictEqual([...just].length, 29, '样本长度变了，这条对照就没意义了');
  assert.strictEqual(g.isSubmission({ text: just }).yes, false, `29 字（< ${g.MIN_REVIEW_CHARS}）不该触发`);
  assert.strictEqual(g.isSubmission({ text: just + '十' }).yes, true, '30 字该触发');
});

await t('送进链里的素材：按模态分开取，不是把整段提示词塞进去', async () => {
  const g = await import('./agent/review_gate.mjs');
  const inbound = {
    text: '审核下这个视频',
    images: [],
    videos: [{
      index: 1, fileName: 'hero.mp4',
      meta: { duration_s: 14.96, w: 1920, h: 1080 },
      framesRead: 8, frames: [{ t_s: 0.94, text: 'MOMCOZY' }, { t_s: 2.81, text: 'Built to last' }],
      transcript: { ok: true, text: 'Meet the playard that folds in one second.', chars: 42 },
    }],
  };
  const ci = g.chainInput({ question: '审核下这个视频', inbound });
  assert.strictEqual(ci.question, '审核下这个视频', '问句要逐字传');
  assert.ok(ci.text.includes('MOMCOZY') && ci.text.includes('Built to last'), '帧上的字要进素材');
  assert.ok(ci.text.includes('folds in one second'), '音轨转写要进素材');
  assert.ok(ci.text.includes('hero.mp4') && ci.text.includes('15.0s'), '文件名与时长要进素材');
  assert.ok(/抽样/.test(ci.text), '必须写明只能看到抽样几帧 —— 否则链会以为素材就这些');
  assert.deepStrictEqual(ci.media, ['video']);

  // 没人说话 / 没音轨 / 转写没跑成 —— 三种必须分开写，不许都写成「没有说话」
  const mk = (t) => g.chainInput({ question: 'q', inbound: { videos: [{ index: 1, frames: [], transcript: t }] } }).text;
  assert.ok(/没有人说话/.test(mk({ ok: false, kind: 'no_speech' })), 'no_speech 要写「没有人说话」');
  assert.ok(/没有音轨/.test(mk({ ok: false, kind: 'no_audio_track' })), '无音轨要单独写');
  const untested = mk({ ok: false, kind: 'not_authorized' });
  assert.ok(/没跑成/.test(untested) && /未知/.test(untested), `转写没跑成必须写成未知：${untested}`);

  // 链接 / 纯文字两条支路
  assert.ok(g.chainInput({ question: 'q', inbound: { text: '看 https://example.com/x' } }).text.includes('https://example.com/x'));
  assert.strictEqual(g.chainInput({ question: 'q', inbound: { text: '这句能不能发' } }).text, '这句能不能发');
});

await t('链的三种结局必须长得不一样（跑成 / 没跑成 / 回了空的）', async () => {
  const g = await import('./agent/review_gate.mjs');
  const okBlock = g.formatChainBlock({ answer: '结论：REVIEW。依据 W-1.54/M01。', report: 'kb/l7/reports/x.md', record_id: 'recv1' });
  assert.ok(okBlock.includes('REVIEW') && okBlock.includes('W-1.54'), '结论原文要逐字进块');
  assert.ok(/逐字转述，不许改写/.test(okBlock), '必须写明不许改写');
  const errBlock = g.formatChainBlock({ error: '超时' });
  assert.ok(/没跑成/.test(errBlock) && /未知/.test(errBlock), `失败必须写成「结论未知」：${errBlock}`);
  assert.ok(/不是「没问题」，也不是「通过」/.test(errBlock), '必须明确否认「通过」这个读法');
  const emptyBlock = g.formatChainBlock({ answer: '   ' });
  assert.ok(/没有返回结论原文/.test(emptyBlock) && /未知/.test(emptyBlock), '空回答也要落成未知');

  // ★ 信封形状（`executeTool` 回的是 `{tool, ok, result}`）—— 实测踩过一次：
  //   不认它，就会把**跑成的链**写成「没返回结论 → 未知」，安静地把成功说成未知。
  const env = g.formatChainBlock({ tool: 'kb_review_chain', ok: true, result: { answer: '结论：PASS｜依据 W-1.51' } });
  assert.ok(env.includes('PASS') && env.includes('W-1.51'), `信封形状必须能拆出结论：${env.slice(0, 120)}`);
  const envFail = g.formatChainBlock({ tool: 'kb_review_chain', ok: false, error: '超时' });
  assert.ok(/没跑成/.test(envFail) && /未知/.test(envFail), `信封形状的失败也要落成未知：${envFail}`);
});

await t('默认跑法必须**拆掉 executeTool 的信封**（否则成功的链会被写成未知）', async () => {
  const { defaultChainRunner } = await import('./agent/agent.mjs');
  const g = await import('./agent/review_gate.mjs');
  // 直接喂桩给 `formatChainBlock`，验「信封 → 结论」这一跳；
  // `defaultChainRunner` 自己那一跳（真调工具）在下面用源码级断言守住形状。
  const block = g.formatChainBlock({ tool: 'kb_review_chain', ok: true, result: { answer: '结论：REVIEW' } });
  assert.ok(block.includes('结论：REVIEW'), '信封拆不出来的话，这里会变成「未知」');
  const src = fs.readFileSync(new URL('./agent/agent.mjs', import.meta.url), 'utf8')
    .split('\n').filter((l) => !l.trim().startsWith('//')).join('\n');
  assert.ok(/r\?\.ok === false[\s\S]{0,80}r\?\.result/.test(src),
    '`defaultChainRunner` 必须按 `{ok,result}` 拆信封 —— 直接回 executeTool 的返回值就是那个坑');
});

await t('行为级·闸门：该走链的走一次、回执先发、结论排在那一轮最前面', async () => {
  const { runSubmissionGate } = await import('./agent/agent.mjs');
  const calls = { chain: [], acks: [] };
  const inbound = { text: '审核下这个视频', imageCount: 0, videoCount: 1,
    videos: [{ index: 1, fileName: 'hero.mp4', meta: { duration_s: 15 }, framesRead: 8,
               frames: [{ t_s: 0.9, text: 'MOMCOZY' }], transcript: { ok: true, text: 'folds in one second', chars: 18 } }] };
  const r = await runSubmissionGate({
    inbound, question: '审核下这个视频',
    notify: async (t) => { calls.acks.push(t); },
    chainRunner: async (args) => { calls.chain.push(args); return { answer: '结论：REVIEW｜依据 W-1.54' }; },
    publishRunner: async () => ({ ok: true, action: 'skipped', detail: '测试桩：不碰真表' }),
    // ★ 2026-10-09：**必须注入** —— 不注入的话，问题数 ≥3 的夹具会真的在飞书里建一份云文档
    //   （§2.4.4：跑一次自证，改掉了它要保护的东西。实测已发生过一次）。
    mergedReportRunner: async () => ({ ok: true, url: 'https://example.invalid/docx/STUB', detail: '自证桩' }),
    // ★ 2026-10-09：**建议生成也必须注入** —— 它默认真打 LLM。
    //   不注入的话每条跑闸门的自证都会真调模型（实测直接把套件拖到超时）。
    adviceRunner: async ({ items }) => ({ ok: true, ms: 1,
      advice: Object.fromEntries((items || []).map((_, i) => [i, `自证桩给的改法 ${i}`])) }),
  });
  assert.strictEqual(calls.chain.length, 1, '该起链的必须**恰好**起一次');
  assert.strictEqual(calls.acks.length, 1, '必须**先**回一句回执（否则 10~30 分钟里对方以为它没动）');
  assert.ok(/\[\[card:receipt\]\]/.test(calls.acks[0]), `回执要递**卡片块**（发送层负责成形）：${calls.acks[0]}`);
  assert.ok(calls.chain[0].text.includes('MOMCOZY'), '链要拿到本机读到的读数');
  // ★ 判据是**先后**，不是「有没有」：链的结论（含它自己的头注）必须**排在**人问的话**之前** ——
  //   排在后面会被前面几百字的读数盖住，模型就又开始「描述我读到了什么」了。
  const iAns = r.question.indexOf('结论：REVIEW');
  const iQ = r.question.indexOf('审核下这个视频');
  assert.ok(iAns >= 0, '链的结论原文必须进那一轮');
  assert.ok(iQ >= 0, '人问的话不能丢');
  assert.ok(iAns < iQ, `结论必须排在问题**之前**（结论@${iAns} 问题@${iQ}）`);
  assert.ok(/已经跑完/.test(r.question.slice(0, iAns + 1)), '块头要说明链已经跑完');
  assert.strictEqual(r.chainRan, true);
  // ★ 反向对照：闲聊那条**一次都不许起链**（否则每句「在吗」都跑 30 分钟 + 写飞书）
  const quiet = await runSubmissionGate({
    inbound: { text: '在吗', imageCount: 0, videoCount: 0 }, question: '在吗',
    notify: async () => { throw new Error('不该有回执'); },
    chainRunner: async () => { throw new Error('不该起链'); },
    publishRunner: async () => { throw new Error('不该落表'); },
  });
  assert.strictEqual(quiet.gate.yes, false, '闲聊不该判成送审');
  assert.strictEqual(quiet.question, '在吗', '不走链时那一轮必须原样');
  // ★ 反向对照：链没跑成时，块里必须写「结论未知」
  const failed = await runSubmissionGate({
    inbound, question: '审核下这个视频', notify: null,
    chainRunner: async () => { throw new Error('起链炸了'); },
    publishRunner: async () => ({ ok: true, action: 'skipped', detail: '测试桩：不碰真表' }),
    // ★ 2026-10-09：**必须注入** —— 不注入的话，问题数 ≥3 的夹具会真的在飞书里建一份云文档
    //   （§2.4.4：跑一次自证，改掉了它要保护的东西。实测已发生过一次）。
    mergedReportRunner: async () => ({ ok: true, url: 'https://example.invalid/docx/STUB', detail: '自证桩' }),
    // ★ 2026-10-09：**建议生成也必须注入** —— 它默认真打 LLM。
    //   不注入的话每条跑闸门的自证都会真调模型（实测直接把套件拖到超时）。
    adviceRunner: async ({ items }) => ({ ok: true, ms: 1,
      advice: Object.fromEntries((items || []).map((_, i) => [i, `自证桩给的改法 ${i}`])) }),
  });
  assert.strictEqual(failed.chainRan, false);
  assert.ok(/未知/.test(failed.question) && !/^结论/.test(failed.question), '链炸了不许产出结论');
  // ★ 反向对照：**补发重放**不许重跑链（链会真写飞书，重跑 = 同一单写两遍）
  let reran = 0;
  await runSubmissionGate({ inbound, question: 'q', force: true,
    chainRunner: async () => { reran++; return { answer: 'x' }; },
    publishRunner: async () => ({ ok: true, action: 'skipped', detail: '测试桩：不碰真表' }) });
  assert.strictEqual(reran, 0, 'force（补发）时一次都不许起链');
});

await t('回执：**一张「处理中」卡片**，不许带时长估计（Owner 两次现场裁定）', async () => {
  const g = await import('./agent/review_gate.mjs');
  const env = await import('./reply-cards/envelope.mjs');
  const normal = g.ackMessage({ kind: 'media' });
  const queued = g.ackMessage({ kind: 'media' }, { queued: true });

  // ① **不许再给时长估计** —— Owner 原话：「实际时间跟预估的不符，6~30min 可以去掉」。
  //    核过：本机实测一条图 3 分 32 秒（20:08:23 回执 → 20:11:30 链返回），而回执写 6~30 分钟。
  //    估高了不算最坏 —— 最坏是**估得再准也没用**：人要知道的只有「收到了」和「它在动」。
  for (const [name, a] of [['常态', normal], ['排队', queued]]) {
    assert.ok(!/6~30|6-30|30 分钟|分钟/.test(a.plain),
      `${name}回执里还留着时长估计：${a.plain}`);
  }
  // ② 必须是一张**能成形的卡片**（不是一段会被原样发出去的字符串）
  assert.ok(/^\[\[card:receipt\]\]\n\{/.test(normal.block), `回执必须是卡片块：${normal.block}`);
  const shaped = env.toCardByKind ? null : env.toCardOrText(normal.block);
  assert.strictEqual(shaped.mode, 'card', `回执没成形为卡片（会被发成一段裸文本）：${JSON.stringify(shaped).slice(0, 200)}`);
  assert.strictEqual(shaped.dropped, false, `回执卡片被拦下了：${shaped.reason}`);
  const json = JSON.stringify(shaped.card);
  assert.ok(json.includes('处理中'), `卡片标题/正文要有「处理中」：${json.slice(0, 200)}`);
  assert.ok(json.includes('正在处理，请稍等，马上给你结果。'), `正文要照截图那句话：${json.slice(0, 200)}`);
  assert.strictEqual(shaped.kind, 'receipt', '用回执那一种卡片（灰头、只确认不解释）');
  // ③ 排队时才多一句，且两种**必须真的不一样**（否则 queued 是死参数）
  assert.notStrictEqual(normal.block, queued.block, 'queued 参数没起作用');
  assert.ok(/排队/.test(queued.plain) && !/排队/.test(normal.plain),
    '没在排队时不许说排队（谎报会让人以为库很忙）');
  // ④ 反向对照：**纯文本**绝不许被当成卡片（证明上面 ② 不是恒真）
  const asText = env.toCardOrText('正在处理，请稍等，马上给你结果。');
  assert.strictEqual(asText.mode, 'text', '不带卡片标记的纯文本就该走文本 —— 否则 ② 那条判据是恒真的');
});

await t('接线：`handleMessage` 必须**真的调**闸门（不是只 import 它）', async () => {
  const src = fs.readFileSync(new URL('./agent/agent.mjs', import.meta.url), 'utf8');
  // 剥掉注释再找 —— 与 verify_shouheng_ops 的 C5、verify_cards 的 J1a 同一条读法：
  // 判据只看代码，不看解释（本文件里到处在解释这个函数，不剥会恒真）。
  const code = src.split('\n').filter((l) => !l.trim().startsWith('//')).join('\n');
  const calls = code.match(/await\s+runSubmissionGate\s*\(/g) ?? [];
  assert.strictEqual(calls.length, 1,
    `handleMessage 里必须**恰好一处**调用 runSubmissionGate（实际 ${calls.length} 处）——`
    + '闸门定义了却没被调用，就是 §2.4 那条「常量定义了没人用」的老病');
  assert.ok(/export async function runSubmissionGate/.test(code), '闸门自己必须是导出的（判据要能直接调它）');
});

await t('接线·**不许「先用后声明」**（实测崩溃：`chainUnmeasured` TDZ —— 那一单在群里没有回复）', async () => {
  // ★ 这条是**为一个真事故**补的（2026-10-08 现场）：
  //   素材「这条站内广告文案能不能发：M6 吸奶器静音设计，夜里泵奶不吵醒宝宝，一次充电够用一整天」——
  //   **库侧成功了**（旁挂 `REVIEW/1`、表已 update），但出卡阶段内核崩了：
  //     `ReferenceError: Cannot access 'chainUnmeasured' before initialization`（`agent.mjs:1436`）
  //   ⇒ **那一单在群里没有回复**，而且没有任何东西会红。
  //   成因：三处截断/兜底分支把内联判据换成了 `chainUnmeasured`，而它的 `const` 声明在**更后面**
  //   ⇒ `const`/`let` 在那行之前是「已声明未初始化」，读它就是 ReferenceError。**判据对、位置错。**
  //
  // 为什么不让下面那条 `子进程端到端` 兜住：它把 LLM 指向死地址 ⇒ 走的是**报错分支**，
  //   **到不了**那三处「回复被截断 / 工具打光」的分支 —— 判据没盖住的那一跳，就是事故那一跳。
  //
  // 扫描口径（**刻意收窄，宁少不滥**）：只在 `handleMessage` 函数体内查
  //   （跨函数同名会误报 —— 通用扫描实测 32 处噪声，那种判据没人会看）；
  //   只查这张具名清单，要加就往 `WATCH` 里加一行；先剥行尾注释再找（本文件到处在解释这些变量）。
  const src = fs.readFileSync(new URL('./agent/agent.mjs', import.meta.url), 'utf8');
  const lines = src.split('\n').map((l) => l.replace(/\/\/.*$/, ''));
  const start = lines.findIndex((l) => /^export async function handleMessage/.test(l));
  assert.ok(start >= 0, '找不到 handleMessage —— 判据的前提没了，先修判据');
  let end = lines.findIndex((l, i) => i > start && /^export /.test(l));
  if (end < 0) end = lines.length;
  const WATCH = ['chainUnmeasured', 'verdict53Final', 'gate', 'chainRan', 'chainBlock', 'chainMs'];
  for (const name of WATCH) {
    const re = new RegExp(`(^|[^\\w$.])${name}([^\\w$]|$)`);
    let decl = -1; let firstUse = -1;
    for (let i = start; i < end; i++) {
      if (!re.test(lines[i])) continue;
      if (firstUse < 0) firstUse = i;
      if (decl < 0 && new RegExp(`^\\s*(?:const|let|var)\\s+${name}\\b`).test(lines[i])) decl = i;
    }
    if (decl < 0) continue;                       // 这一版里没这个名字 ⇒ 不判（判据不许恒真）
    assert.ok(decl <= firstUse,
      `「${name}」在 ${firstUse + 1} 行就被用了，声明却在 ${decl + 1} 行 —— `
      + '`const`/`let` 在声明之前读它 = ReferenceError（TDZ），而这条路崩了**用户侧只表现为「没有回复」**。'
      + '修法：把声明提到第一个使用点之前（`let … = 初值` 提前，终值在原处重新赋值）');
  }
});

await t('子进程端到端·跑完整条 handleMessage（LLM 指死地址、KB 根不存在）—— 闸门之后那几行有没有塌', async () => {
  // ★ 这条是**为了一个真事故**补的（2026-10-05 现场）：
  //   我把闸门抽成 `runSubmissionGate()` 时，**把 `let gate = null;` 那几行声明一起抽走了**，
  //   于是闸门返回之后的那一行 `gate = g.gate;` 变成对未声明标识符赋值 →
  //   `ReferenceError: gate is not defined`。后果不是少个字段：
  //   **链跑完 17.9 分钟，然后内核在回话前一刻崩掉**，人收到「内部出错了」，链的结论被丢掉。
  //   为什么原来的自证没拦住：`runSubmissionGate` 自己测过（它是好的），
  //   接线断言只查了「handleMessage 里**有没有调用**它」—— **崩溃发生在调用之后的下一行**。
  //   这正是 §2.4.7 那句：判据没盖住的那一跳，就是事故所在的那一跳。
  //
  // 所以这一条**真跑一遍 handleMessage**，而且保证它是离线、不写飞书、不等 30 分钟的：
  //   · `SHOUHENG_KB_ROOT` 指一个不存在的目录 → `kb_review_chain` 立刻回「找不到知识库工作区」；
  //   · `SHOUHENG_LLM_BASE_URL` 指一个没人听的端口 → 模型这一跳立刻失败（走 `llm_error` 分支）；
  //   · `SHOUHENG_STATE_DIR` 指临时目录 → 会话/去重表都写在那儿，**不碰真状态**。
  const { spawnSync } = await import('node:child_process');
  const os = await import('node:os');
  const pathMod = await import('node:path');
  const tmp = fs.mkdtempSync(pathMod.join(os.tmpdir(), 'shouheng-e2e-'));
  const script = `
    process.on('uncaughtException', (e) => { console.log('THREW ' + (e?.message ?? e)); process.exit(3); });
    process.on('unhandledRejection', (e) => { console.log('THREW ' + (e?.message ?? e)); process.exit(3); });
    const { handleMessage } = await import(${JSON.stringify(new URL('./agent/agent.mjs', import.meta.url).href)});
    const r = await handleMessage({
      message: { message_id: 'om_e2e_' + Date.now(), chat_id: 'oc_e2e', chat_type: 'p2p',
                 message_type: 'text',
                 content: JSON.stringify({ text: '这段 listing 文案能不能发：M5 吸奶器是最好的' }) },
      sender: { sender_id: { open_id: 'ou_e2e_test' } },
    }, {
      // 回执只是打印，不真发消息（这一条验的是内核，不是发送层）
      notify: async (t) => { console.log('ACK ' + t.slice(0, 200)); },   // 要够长，才断得到卡片正文
      // ★ 落表用桩：这一条验的是「闸门之后那几跳会不会塌」，不是「表写没写进去」
      //   —— 写表的判据在 review_publish.test.mjs（那边用假客户端，全程离线）。
      publishRunner: async () => { console.log('PUBSTUB'); return { ok: true, action: 'skipped', detail: '桩' }; },
    });
    console.log('RESULT ' + JSON.stringify({ reason: r.reason, gate: r.meta?.gate ?? null,
                                              chain: r.meta?.chain ?? null,
                                              replyHead: String(r.reply ?? '').slice(0, 60) }));
  `;
  const r = spawnSync(process.execPath, ['--input-type=module', '-e', script], {
    encoding: 'utf8', timeout: 120_000,
    env: { ...process.env,
           SHOUHENG_STATE_DIR: tmp,
           SHOUHENG_KB_ROOT: '/tmp/shouheng-绝不存在-的-知识库',
           SHOUHENG_LLM_BASE_URL: 'http://127.0.0.1:9' },
  });
  const out = `${r.stdout ?? ''}\n${r.stderr ?? ''}`;
  try { fs.rmSync(tmp, { recursive: true, force: true }); } catch { /* 收尾失败不影响断言 */ }
  // ① 最要紧的一条：**不许抛**。旧版在这里就是 `gate is not defined`。
  assert.ok(!/THREW|ReferenceError|is not defined/.test(out),
    `闸门之后那一跳塌了（这正是 10-05 现场那次）：\n${out.slice(-500)}`);
  // ② 闸门必须真的判成送审（否则这条用例是空转）
  const m = out.match(/RESULT (\{.*\})/);
  assert.ok(m, `没拿到 RESULT —— 子进程没跑到底：\n${out.slice(-500)}`);
  const res = JSON.parse(m[1]);
  assert.strictEqual(res.gate?.yes, true, `这条消息本该判成送审：${JSON.stringify(res.gate)}`);
  // ③ 链没跑成（KB 根是假的）→ 必须落成 `ran:false`，而且 reply 里要写「未知」
  assert.strictEqual(res.chain?.ran, false, `KB 根不存在时链不该算跑成：${JSON.stringify(res.chain)}`);
  assert.ok(/结论未知|未知/.test(res.replyHead + out), '链没跑成时那一轮必须写「结论未知」');
  // ④ 回执先发（人得知道它在跑）
  // 回执现在递的是**卡片块**（`[[card:receipt]]` + JSON），所以这里判的是「先回了、且是卡片块」
  assert.ok(/ACK \[\[card:receipt\]\]/.test(out), `链启动前必须先回一条「处理中」卡片：${out.slice(-300)}`);
  assert.ok(/正在处理，请稍等/.test(out), '卡片正文要照截图那句话');
});

// ─────────────────────────────────────────────────────────────────────────────
// 第 19 组：**自证自己不许往真表里写东西**（§2.4.4 那个形状的现场实例）
//
// 2026-10-05 实测：`runSubmissionGate` 里那段「保证落表」对**测试桩**也照跑不误 ——
// 单测里 `chainRunner` 返回一句假的 `结论：REVIEW`，就真的在 Owner 的评审表上建了一行；
// 紧接着那条「链没跑成」的反向对照又把它的 `状态` 改成了「待审」。
// **自证不但没验出问题，自己成了问题的来源。**
// 判据不再是「记得传桩」（那要靠自觉），而是**闸门默认就是拉下的**：这一条直接断它。
// ─────────────────────────────────────────────────────────────────────────────
console.log('\n═══ 19. 自证不许往真表里写东西 ═══');

await t('C1 自证进程里，落表闸门必须是**拉下**的（`SHOUHENG_REVIEW_TABLE=off`）', async () => {
  const rp = await import('./agent/review_publish.mjs');
  assert.strictEqual(process.env.SHOUHENG_REVIEW_TABLE, 'off',
    '自证进程没拉闸 —— 一旦哪条用例漏传桩，就会真的往 Owner 的表里写');
  assert.strictEqual(rp.reviewTable(), null, '`reviewTable()` 在拉闸时必须回 null');
  // 反向对照：闸门真能挡住写入（不是「恰好没人调」）
  const r = await rp.ensureReviewRow({ contentId: 'AUTO-x', question: 'q', conclusion: 'PASS' });
  assert.strictEqual(r.action, 'skipped', `拉闸时应当 skipped，实际 ${r.action}`);
  assert.ok(/关掉/.test(r.detail ?? ''), `拒写的理由要说清，实际：${r.detail}`);
});

// ─────────────────────────────────────────────────────────────────────────────
// 第 20 组：**PRD §5.3 结论行必须逐字进卡片**（2026-10-06）
//
// 事故形状（Owner 在飞书私聊里看见的）：链路侧**已经**按 5.3 产出了结论行，
// 注入语也写着「逐字转述，不许改写」—— 而**回卡片那一跳把表头改写掉了**：
//   `【审查结论：REVIEW】共发现 1 处需人工确认。` → `【证据】REVIEW：1 处问题（W-1.54 静音绝对化）`
// 也就是说「逐字转述」这四个字，在盘上**没有任何执行点**（`AGENTS.md` §2.4）。
//
// 修法照 §2.5 的既有分工：**模型不写结论行**，结论行由 `envelope.applyVerdictLine()`
// 从链的返回里搬进卡片的结论格。本组的判据全部是**行为级**（真调 `toCardOrText`），
// 外加四条反向对照 —— 没有反向对照，那些绿只证明「这个函数对什么都点头」。
// ─────────────────────────────────────────────────────────────────────────────
console.log('\n═══ 20. PRD §5.3 结论行（逐字进卡片 + 反向对照）═══');

const { deriveVerdictLine, conforms, leadsWith } = await import('./agent/prd53.mjs');
const { toCardOrText, applyVerdictLine, verdictSlotOf } = await import('./reply-cards/envelope.mjs');

await t('W1 权威结论行的三个来源：链原文 / P0 快路派生 / 都没有 → null（不许编）', () => {
  // ① 链原文里有 5.3 行 → 用它（这就是「链说了算」）
  const fromChain = deriveVerdictLine({
    answer: '状态：REVIEW ｜ 问题数：1\n摘要：【审查结论：REVIEW】共发现 1 处需人工确认。\n1.【平台与促销-静音绝对化表述】…',
  });
  assert.strictEqual(fromChain.state, 'REVIEW');
  assert.strictEqual(fromChain.line, '【审查结论：REVIEW】共发现 1 处需人工确认。');
  assert.strictEqual(fromChain.from, 'chain');

  // ② P0 快路的抬头是「来路标注」，不是 5.3 的结论行 ⇒ 按 §5.3.3 **派生**一行
  const fromP0 = deriveVerdictLine({
    answer: '【P0 红线拦截：BLOCK】命中知识库已定稿的 P0（法务合规红线）确定性模式。\n…',
    p0Fastpath: { matched_patterns: 2, elapsed_ms: 42.9 },
  });
  assert.strictEqual(fromP0.line, '【审查结论：BLOCK】共发现 2 处必须修改。',
    `P0 快路必须派生出 §5.3.3 那一行，实际：${fromP0.line}`);
  assert.strictEqual(fromP0.from, 'p0-fastpath');

  // ③ 拒答（NEEDS_INPUT）**不在 §5.3 里** ⇒ 不搬，也**不许编一行出来**
  assert.strictEqual(deriveVerdictLine({ answer: '【审查结论：NEEDS_INPUT】依据侧拒答（fail-closed）' }), null,
    'NEEDS_INPUT 不在 PRD §5.3 的三态里 —— 这里必须回 null（编一行比不搬更坏）');
  assert.strictEqual(deriveVerdictLine({}), null, '什么都没给时必须回 null');
  // 反向对照：P0 命中数读不出来时**不派生**（「共发现 ? 处」是编的）
  assert.strictEqual(deriveVerdictLine({ answer: 'x', p0Fastpath: { elapsed_ms: 1 } }), null,
    'P0 命中数读不出来时必须回 null —— 不许编一个「共发现 N 处」');
});

await t('W2 兜底判据必须**窄**：回复中间出现 5.3 模板 ≠ 一次审查结论', () => {
  const TMPL = '【审查结论：REVIEW】共发现 1 处需人工确认。';
  // 有人问「PRD 5.3 的 REVIEW 长什么样」，守衡照抄一遍模板 —— **那不是一次审查结论**
  const quoted = `PRD 第 5.3.2 节的模板是这样：\n\n${TMPL}\n\n注意「需人工确认」是逐字的。`;
  assert.strictEqual(deriveVerdictLine({ replyText: quoted }), null,
    '模板被引用在回复中间时不许当成结论 —— 否则问一句模板就会把自己的标题改掉');
  // 排在最前面才算自己在用这一行
  assert.ok(leadsWith(`${TMPL}\n\n上面是结论。`, TMPL), '排在最前面时必须认');
  const atTop = deriveVerdictLine({ replyText: `${TMPL}\n\n明细见报告。` });
  assert.strictEqual(atTop?.line, TMPL);
});

await t('W3 行为级：改写过的卡片标题，必须被换成**逐字**结论行（且原标题不丢）', () => {
  const line = '【审查结论：REVIEW】共发现 1 处需人工确认。';
  // 这条形状**逐字取自 2026-10-06 实发出去的那三条**（PMO/logs/ws_outbound.jsonl）
  const reply = '结论：REVIEW\n\n[[card:query-answer]]\n'
    + JSON.stringify({ title: 'REVIEW：1 处问题（W-1.54 静音绝对化）', verdict: '待转法务复核',
                       boundary: '未命中 ≠ 合规' });
  const r = toCardOrText(reply, { verdict53: { state: 'REVIEW', line, from: 'chain' } });
  assert.strictEqual(r.mode, 'card', `应当建出卡片，实际 ${r.mode}`);
  assert.strictEqual(r.data.title, line, `卡片标题必须是逐字结论行，实际「${r.data.title}」`);
  assert.strictEqual(r.verdict53.action, 'forced');
  // ★ **搬不是砍**：模型原来写在标题里的话必须进折叠区，一个字都不许丢
  const folded = JSON.stringify(r.card);
  assert.ok(folded.includes('W-1.54 静音绝对化'),
    '原标题被覆盖掉了 —— 那里面常写着边界话（如「但『未命中 ≠ 合规』」），丢了比格式难看严重得多');
});

await t('W4 反向对照：不是送审时**一个字符都不许加**', () => {
  const reply = '[[card:query-answer]]\n' + JSON.stringify({ title: '在的', verdict: '有什么事？' });
  const r = toCardOrText(reply, { verdict53: null });
  assert.strictEqual(r.data.title, '在的', '没有权威结论行时不许动标题 —— 给闲聊加一句「审查结论」比格式难看严重得多');
  assert.strictEqual(r.verdict53.action, 'none', '没搬过就不许报「搬过」');
  // 直接调纯函数也验一遍（调用方漏传 opts 时这条兜住）
  const p = applyVerdictLine('query-answer', { title: '在的' }, null);
  assert.strictEqual(p.action, 'none');
  assert.strictEqual(p.data.title, '在的');
});

// ★ 2026-10-06 重写。原版断言的是「`find-nothing` **没有**结论格」——
//   而那正是当时的**病灶**（模型挑到它就 `落点=no-slot`，PRD §5.3 结论行无处安放）。
//   把病灶写成反向对照，等于**把 bug 钉住**：一修好它就红。
//   现在两条分开：**十一种卡片都必须有结论格**（正面），
//   **未登记的类型落到 no-slot 且不许丢内容**（反向对照，仍然有效）。
await t('W5 十一种卡片的结论格**全部**是 title（抬头）', async () => {
  const { BUILDERS } = await import('./reply-cards/registry.mjs');
  const noSlot = Object.keys(BUILDERS ?? {}).filter((k) => !verdictSlotOf(k));
  assert.deepStrictEqual(noSlot, [],
    `这些类型没有结论格，模型挑到它们时 §5.3 结论行就无处安放：${noSlot.join('、')}`);
  // ★ 2026-10-06 Owner 裁定「title 格补给所有卡片类型」：
  //   **落点必须是抬头**，不能是 verdict（正文）。
  //   旧版这里写的是 `assert.strictEqual(verdictSlotOf('evidence'), 'verdict')` ——
  //   那正是当时的**病灶**（模型挑 evidence 时结论行落到正文、抬头仍是模型自拟的），
  //   把病灶钉成判据，一修好它就红。**判据要钉行为，不要钉现状。**
  //   十一种全查，不是抽查两种：漏一种就是漏一条真实的产线路径。
  const wrong = Object.keys(BUILDERS ?? {}).filter((k) => verdictSlotOf(k) !== 'title');
  assert.deepStrictEqual(wrong, [],
    `这些类型的结论格不是抬头（会被放到正文去，业务同事扫抬头看不到结论）：${wrong.join('、')}`);
  for (const k of ['cannot-read', 'receipt', 'turn-diff', 'evidence']) {
    assert.strictEqual(verdictSlotOf(k), 'title', `${k} 的抬头格没被认出来（它的 fields 里只有 verdict）`);
  }
});

await t('W5c 行为级：evidence 卡的 §5.3 结论行必须真的进**抬头**（不是只改判据）', () => {
  // `verdictSlotOf` 只是判据本体 —— 它对了不等于卡上真换了。
  // 这一条走完整 `toCardOrText`，看**建出来的那张卡**的 header。
  const line = '【审查结论：REVIEW】共发现 2 处需人工确认。';
  const reply = '[[card:evidence]]\n' + JSON.stringify({
    title: '模型自拟的抬头', verdict: '模型自述的一句话',
    groups: [{ title: 'g', content: 'c' }],
  });
  const r = toCardOrText(reply, { verdict53: { state: 'REVIEW', line, from: 'chain' } });
  assert.strictEqual(r.card.header.title.content, line,
    `结论行没进抬头，实际：${JSON.stringify(r.card.header.title.content)}`);
  // **搬不是砍**：模型原来那句必须还在卡里（换格子，不是删）
  assert.ok(JSON.stringify(r.card).includes('模型自拟的抬头'),
    '原抬头被砍掉了 —— 搬是搬，砍是砍');
});

await t('W5b 反向对照：**未登记的类型**落到 no-slot，且不许丢内容', () => {
  const line = '【审查结论：BLOCK】共发现 2 处必须修改。';
  assert.strictEqual(verdictSlotOf('__不存在__'), null);
  const r = toCardOrText('[[card:find-nothing]]\n' + JSON.stringify({ paths: ['PMO/'], tried: ['grep'] }),
                         { verdict53: { state: 'BLOCK', line, from: 'chain' } });
  // find-nothing 现在**有**格子了 ⇒ 必须真搬进去，不是静默成功
  assert.strictEqual(r.card.header.title.content, line, '有结论格却没搬进去');
  assert.strictEqual(r.verdict53.action, 'forced');
  // 内容不许丢：原来那些字段还在
  assert.ok(JSON.stringify(r.card.body).includes('grep'), '搬结论行时把正文丢了');
});

await t('W6 评审单：结论行前置（走卡片抬头），且幂等（已有就不再加）', () => {
  const line = '【审查结论：PASS】未发现已知底线风险，可转交 @sign-off 责任人（未配置） 进行 sign-off。';
  const V = { state: 'PASS', line, from: 'chain' };
  // ★ 2026-10-12（Owner 现场：「守衡的输出格式变了」）：**带权威结论行的回复必须建卡**。
  //   旧断言写的是 `mode === 'text'` —— 而那正是 19:31–19:58 四条实发回复的形状：
  //   纯文本在飞书里不渲染 markdown，群里看到的是 `**加粗**`、反引号与一堆 `|`。
  //   行为改动在 `envelope.mjs::toCardOrText`（模型没给卡 ⇒ 代码建一张），
  //   判据在 `verify_cards.mjs` J12a–d。
  const once = toCardOrText('模型自己写的一段话。', { verdict53: V });
  assert.strictEqual(once.mode, 'card', `评审单必须建卡，实际 mode=${once.mode}（reason=${once.reason}）`);
  assert.strictEqual(once.card.header.title.content, line,
    `结论行必须排在最前面（抬头），实际：${JSON.stringify(once.card.header.title.content)}`);
  // 幂等：模型原话里已经把这一行写出来了 ⇒ 从折叠组里摘掉，抬头独占（不许印两遍）
  const twice = toCardOrText(`${line}\n\n模型自己写的一段话。`, { verdict53: V });
  const n = JSON.stringify(twice.card).split(line).length - 1;
  assert.strictEqual(n, 1, `结论行在卡里出现了 ${n} 次 —— 已经有这一行时不许再来一遍`);
  // 反向对照：**没有**权威结论行 ⇒ 仍是纯文本，且一个字符都不许改
  const plain = toCardOrText('模型自己写的一段话。');
  assert.strictEqual(plain.mode, 'text');
  assert.strictEqual(plain.text, '模型自己写的一段话。');
});

await t('W7 措辞判据：REVIEW / BLOCK 两句话必须**不一样**（这是引擎原先抹平的那一处）', () => {
  assert.ok(conforms('【审查结论：REVIEW】共发现 1 处需人工确认。').ok);
  assert.ok(conforms('【审查结论：BLOCK】共发现 2 处必须修改。').ok);
  // 反向对照：引擎原先那句两态共用的话，**必须判不合规**
  assert.ok(!conforms('【审查结论：REVIEW】共发现 1 处需处理问题。').ok,
    '「需处理问题」是引擎 2026-10-06 之前两态共用的写法，PRD §5.3.2 要的是「需人工确认」');
  assert.ok(!conforms('【审查结论：BLOCK】共发现 2 处需处理问题。').ok, 'BLOCK 要的是「必须修改」');
  assert.ok(!conforms('【P0 红线拦截：BLOCK】命中…').ok, '来路标注不是 5.3 的结论行');
});

await t('W8 接线：`replyTo` 必须真的把结论行**传进** toCardOrText（不是只 import）', () => {
  const src = fs.readFileSync(new URL('./ws_daemon.mjs', import.meta.url), 'utf8');
  const strip = (s) => s.replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/[^\n]*/g, '');
  const body = strip(src.slice(src.indexOf('async function replyTo'), src.indexOf('async function safeSend')));
  assert.ok(/deriveVerdictLine\(/.test(body),
    'replyTo 里没有兜底派生 —— 补发那一路（resend 不跑闸门）会拿不到结论行');
  assert.ok(/toCardOrText\([^)]*verdict53/.test(body),
    'replyTo 调 toCardOrText 时**没把 verdict53 传进去** —— 判据就成了注释（§2.4 那个病）');
  // 反向对照：内核算出的那一行必须真的被 daemon 取用
  const onMsg = strip(src.slice(0, src.indexOf('async function replyTo')));
  assert.ok(/meta\?\.verdict53/.test(onMsg), 'onMessage 没有把 meta.verdict53 取出来 —— 内核算了也白算');
});

await t('W9 行为级：**逐条四要素整块**必须进卡片正文（不只是抬头）', () => {
  // 真事（Owner 2026-10-06 08:57 那张 BLOCK 卡）：抬头对了，**逐条整块没有** ——
  // 因为正文由模型转述，它把一整块压成了一句「命中两条 P0，不能发」。
  const ans = ['【审查结论：BLOCK】共发现 2 处必须修改。', '',
    '1.【功效宣称-催乳与通乳宣称】全文，逐字命中 \`increase milk supply\`',
    '  **原因**：H02 催乳/增产/奶量产出承诺',
    '  **依据**：《措辞表达库 v0（试用版，未发布）》第 W-1.18 条（链接：kb/l3/candidates/rules.jsonl#W-1.18）',
    '  **锚点**：#广告文案明细/recvuJYdOb1Rm1/命中片段｜source_sha256：c77f576…',
    '  **判定**：事实（确定性逐字匹配）｜置信度：未给（P0 快路不产出置信度）',
    '  **建议**：删除 more milk 等承诺', '',
    '2.【背书与资质-医生专家推荐】全文，逐字命中 \`doctor recommended\`',
    '  **原因**：H04 无据的医生/专家推荐背书', '',
    '请修改后重新提交。', '', '---', '【来路与边界】…'].join('\n');
  const v = deriveVerdictLine({ answer: ans, p0Fastpath: { matched_patterns: 2 } });
  assert.ok(v.block && v.block.startsWith('【审查结论：BLOCK】'), '块必须从结论行起');
  assert.ok(v.block.endsWith('请修改后重新提交。'), '块必须在动作行止（半截块比不搬更坏）');

  // 复刻那张卡：模型把整块压成了一句话
  const reply = '结论：BLOCK\n\n[[card:query-answer]]\n' + JSON.stringify({
    title: 'P0 红线拦截：BLOCK（H02 / H04）',
    verdict: 'BLOCK：命中 W-1.18 与 W-1.13 两条 P0，不能发',
    reasoning: 'P0 快路确定性匹配（35.559 ms，不动用大模型）—— 红线拦截，不是专项审查结论。' });
  const P0BND = '本结论为 **P0 红线拦截**（确定性匹配，**未跑**专项审查、层前置与评审链），'
             + '**不是 PASS 依据**；若素材属图片 / 视频 / 产品宣称等模态，**仍需转对应专项复核**。';
  const r = toCardOrText(reply, { verdict53: v, boundary: P0BND });
  // ★★ 2026-10-13（Owner：「群聊里跟私聊的格式不一样？」）：**评审单形状由代码定** ——
  //   模型挑的 `query-answer`（正文格是 `reasoning`）不再被沿用，一律收敛到 `evidence`
  //   ＋ 一组「审查结论」，逐条四要素落进**那一组**（不是 `reasoning`）。
  const body = String(r.data?.groups?.[0]?.content ?? '');
  assert.strictEqual(r.kind, 'evidence', `评审单没收敛到 evidence，实际 ${r.kind}`);
  assert.strictEqual(r.data?.groups?.[0]?.title, '审查结论', '第一组标题必须固定');
  // ★ 2026-10-06：Owner 要求**标签加粗**，方便业务同事一眼扫到「原因/依据/建议」。
  //   断言跟着改成加粗形态 —— 不是放宽，是**钉住新形态**（钉不住的格式改动会悄悄退回）。
  for (const k of ['**原因**：', '**依据**：', '**锚点**：', '**判定**：', '**建议**：']) {
    assert.ok(body.includes(k), `逐条块里缺「${k}」—— 这一格正是 Owner 指出没落上的那几行`);
  }
  assert.ok(r.verdict53.block && r.verdict53.block.action === 'forced', '落点读数必须带出来（否则日志里看不到）');
  // ★ 边界改由**代码**给（P0 单）：卡脚必须有它 —— 模型自己那句话不上卡之后，
  //   这是「未跑专项审查 / 仍需转对应专项复核」唯一的落点。
  assert.ok(String(r.data?.boundary ?? '').includes('P0 红线拦截'), '卡脚丢了 P0 边界');
  // ★ 搬不是砍：模型原话仍在**这一轮的回复正文**里（会话记忆 + `💬 回复 N 字`），只是不上卡
  assert.ok(reply.includes('35.559'), '夹具自己变了？');
  assert.ok(!JSON.stringify(r.card ?? {}).includes('35.559'),
    '模型原话又回到卡上了 —— Owner 2026-10-13 要求它整组不上卡');
});

await t('W10 反向对照：PASS（只有一行、没有逐条）不许被硬塞一个空块', () => {
  const ans = '【审查结论：PASS】未发现已知底线风险，可转交 @sign-off 责任人（未配置） 进行 sign-off。\n\n（无问题）';
  const v = deriveVerdictLine({ answer: ans });
  assert.strictEqual(v.block, null, 'PASS 没有逐条块 —— 不许把半截东西当块搬进去');
  const r = toCardOrText('[[card:query-answer]]\n' + JSON.stringify({ title: 'x', verdict: 'y' }), { verdict53: v });
  assert.strictEqual(r.verdict53.block, null, '没有块就不许报「搬过块」');
  // 也没有「没有块就报错」那条路：quietly none 才是对的
  assert.strictEqual(r.data.title, v.line);
});

// ═══ 第 21 组 · 送审单起了链、链却没跑成 ⇒ 必须进补发队列（2026-10-06）═══
//
// 事故（Owner 原话）：「我以后每次发图片/视频给守衡，守衡都可以正常回复了吧？」
// 那次的两张卡是「库忙（exit 3）：这一单未测，没有三态结论」。
// 那条回复**是一条回复**，所以 `reason` 本来是 `ok` ⇒ 入队判据收不到它
// ⇒ 补发队列**连队都没进** ⇒ 「问一次答不上，问十次还是答不上」。
// 与 2026-09-22 补 `tool_exhausted` 是**同一个病**，只是长在送审这条路上。
//
// 三面各一条（标记表 / 入队判据 / 收尾 reason），缺一面另一个方向就恒真。
await t('X1 补发标记：带 chain_not_run 的回复必须被判「没答过」', async () => {
  const rq = await import('./agent/retry_queue.mjs');
  assert.ok(rq.NOT_AN_ANSWER_FLAGS.includes('chain_not_run'),
    '标记没进补发队列的判据表 ⇒ 带它的回复照样会被当成「答过了」');
  const sess = (flag) => ({ messages: [
    { role: 'user', content: '这个图片可以过吗？' },
    { role: 'assistant', content: '【库忙（exit 3）：这一单未测，没有三态结论】',
      ...(flag ? { chain_not_run: true } : {}) },
  ] });
  const item = { text: '这个图片可以过吗？' };
  assert.strictEqual(rq.answeredInMemory(item, sess(true)).answered, false,
    '带标记的回复被判成「答过了」⇒ 永远不会补发（这就是原 bug 的形状）');
  // 反向对照：**不带**标记的普通回复仍必须判「答过了」——
  // 少了这一条，判据写成恒 false 也照样绿，而代价是「什么都重跑一遍、答两遍」。
  assert.strictEqual(rq.answeredInMemory(item, sess(false)).answered, true,
    '反向对照失败：没标记也被当成没答 ⇒ 会答两遍');
});

await t('X2 入队判据：chain_not_run 必须被 daemon 收进补发队列', () => {
  const src = fs.readFileSync(new URL('./ws_daemon.mjs', import.meta.url), 'utf8');
  // 必须是**入队那一条 if** 收它，不是别处出现过就算
  // （§2.4：「名字出现过」不是「它拦得住」）。
  const m = /if \(result\.reason === 'llm_error'[\s\S]{0,240}?\)\s*\{/.exec(src);
  assert.ok(m && m[0].includes('chain_not_run'),
    'chain_not_run 不在入队的那条 if 里 —— 只是出现在别处，等于没接上');
  assert.ok(/const retryable[\s\S]{0,200}?'chain_not_run'[\s\S]{0,80}?\? true/.test(src),
    '可重试判定没把 chain_not_run 当成必定可重试');
});

await t('X3 收尾 reason：**没拿到三态结论**就必须是 chain_not_run（不只是「链报错」）', async () => {
  const src = fs.readFileSync(new URL('./agent/agent.mjs', import.meta.url), 'utf8');
  // ★ 2026-10-08 重写。旧版断言的是 `gate?.yes && !chainRan` —— 那正是**当时的 bug**：
  //   库忙（认领被占）时链是**「跑成」返回**的（`res.error` 为空），旁挂 `state=NEEDS_INPUT /
  //   reason_code=claim_busy`，一次三态都没有。`!chainRan` 对它**恒为假** ⇒
  //   卡片照发「库忙未判」、补发队列 0 条、**永远不补跑**（Owner 截图那一单）。
  //   把病灶写成判据，等于把 bug 钉住。
  //
  // ★★ 2026-10-08 再一次修正（**这条判据自己钉住了另一处缺陷**）：
  //   原先断言的是 `/const chainUnmeasured = !!(gate?.yes && !verdict53Final)/` ——
  //   它把**声明形式**（`const` ＋ 声明位置）也钉住了。而同一天为了修 TDZ
  //   （`Cannot access 'chainUnmeasured' before initialization`：三处截断/兜底分支在**声明之前**就用它，
  //   那一单库侧成功、表已落，却因崩溃**没发出回复卡**）必须把它**提前声明**成 `let`、
  //   终值在原处**重新赋值** ⇒ 断言当场变红，**而红的是正确的修复**。
  //   ⇒ 判据只该管**语义**（判据是 `gate.yes && !verdict53Final`），不管 `const`／`let`；
  //      「声明必须在使用点之前」由上面那条 `接线·不许「先用后声明」` 单独守着。
  assert.ok(/chainUnmeasured\s*=\s*!!\s*\(gate\?\.yes && !verdict53Final && gapIsTemporal\)/.test(src),
    '没有以「拿没拿到三态结论」为判据（verdict53Final 是唯一真源）');
  assert.ok(/chainUnmeasured \? 'chain_not_run' : 'ok'/.test(src),
    "收尾 reason 没用 chainUnmeasured");
  // ★★ 2026-10-08（第二轮）：**「没拿到三态结论」≠「链没跑成」** —— 判据还要看**缺口会不会变**。
  //   为什么必须收窄（Owner 当天截图那张错卡逼出来的）：
  //     PRD §5.3 只定义三态，`NEEDS_INPUT` **没有规范行**
  //     （`prd53.mjs::LINE_RE` 原文：「NEEDS_INPUT（依据侧拒答）**不在 5.3 里**」）
  //     ⇒ 任何拒答单的 `verdict53Final` **必然**是 null ⇒ 旧判据把**语义性拒答**
  //     （`coverage_not_covered`：库里确实没有可依据的条款，**重跑一百次同一个答案**）
  //     也当成瞬态去补发。实测代价（当天日志可核）：命中 2 次，其中一次真的往群里
  //     **补发了一条**（`✓ 已补发 … → om_x100b63401d2d60a4c3add838013e7ec`），
  //     而那一单**当时已经答完了**（回执+正文都发了、表也落了）；`MAX_TRIES=5`、窗口 1 小时
  //     ⇒ 最多白跑 5 条 2~3 分钟的链、群里多 5 条回复。
  assert.ok(/gapIsTemporal\s*=\s*kbBlind \|\| RETRYABLE_REFUSALS\.has\(kbReason\)/.test(src),
    '没有把「缺口会不会变」接进判据 —— 语义性拒答会被反复补发');
  // 「本来会变」的那四个码：**一个都不许少**（少了 ⇒ 库忙那一类又变回「永远不补跑」）
  const rset = /const RETRYABLE_REFUSALS = new Set\(\[([\s\S]*?)\]\)/.exec(src);
  assert.ok(rset, '找不到瞬态原因码集合');
  for (const code of ['claim_busy', 'layer_gate_red', 'layer_audit_red', 'preflight_aborted']) {
    assert.ok(rset[1].includes(`'${code}'`), `瞬态集合里缺 ${code} —— 那一类会重新变成「永远不补跑」`);
  }
  // 反向对照③：**语义性拒答一个字都不许进**这个集合（它们重跑是同一个答案）。
  for (const code of ['coverage_not_covered', 'evidence_side_refused']) {
    assert.ok(!rset[1].includes(code), `${code} 是语义性拒答，不该进补发集合（补了也是同一个答案）`);
  }
  // 反向对照④：不补发的那一类必须**出声**（库规：缺证据要看得见）——
  //   否则「这次不补」与「补发机制坏了」在外部**长得一模一样**。
  assert.ok(/🚫 没拿到三态结论，但\*\*缺口不是瞬态的\*\*/.test(src),
    '不补发的分支没有日志 ⇒ 静默，违反「缺证据必须可见」');
  // 反向对照①：**不许**退回「只看链报没报错」
  assert.ok(!/\(gate\?\.yes && !chainRan\) \? 'chain_not_run'/.test(src),
    '退回旧判据了 —— 库忙那一类会重新变成「永远不补跑」');
  // 反向对照②：verdict53 只可能由三态结论行（或 P0 派生）产生 ⇒ 这个判据不靠字符串猜。
  assert.ok(/verdict53Final = g\?\.verdict53/.test(src), 'verdict53Final 没有以闸门的结论行为源');
  const n = (src.match(/chain_not_run: true/g) ?? []).length;
  assert.ok(n >= 3, `写到会话记忆里的 chain_not_run 标记只有 ${n} 处，应当 ≥3（三条收尾路径）`);
});

// ═══ 第 22 组 · 模型自己调链那条路也要出 §5.3 结论行（2026-10-06）═══
//
// 真事故（Owner 发的截图）：`M9 吸奶器限时优惠中，下单立减 100 元。` —— 23 字、无媒材、
// 无链接、没命中送审词 ⇒ **闸门判「不是送审」**，`runSubmissionGate` 直接回 `verdict53: null`；
// 而**模型自己**调了 `kb_review_chain`（日志里只有 `🔧 工具: kb_review_chain`，
// 没有 `🧭 送审链返回`），拿到结论后自己写抬头 ⇒ 卡片格式与 PRD §5.3 不符。
//
// 这一组守的就是那条路：**凭据是「这一轮真的调成了链」**，不是「回复里像有一行 5.3」。
await t('Y1 模型自调链 ⇒ 回复里的 5.3 行必须被采用', () => {
  const reply = '**结论：REVIEW —— 共发现 1 处需人工确认，转复核责任人。不是 PASS。**\n\n'
    + '```\n状态：REVIEW ｜ 问题数：1\n摘要：【审查结论：REVIEW】共发现 1 处需人工确认。\n```\n\n'
    + '[[card:query-answer]]\n{"title":"REVIEW 1 处：W-1.16「限时」（覆盖不成立）","verdict":"x"}';
  const d = deriveVerdictLine({ replyText: reply, reviewedByTool: true });
  assert.ok(d, '模型自调链那条路没抽出结论行 ⇒ 卡片抬头仍会由模型自便');
  assert.strictEqual(d.state, 'REVIEW');
  assert.strictEqual(d.line, '【审查结论：REVIEW】共发现 1 处需人工确认。');
  assert.strictEqual(d.from, 'reply-tool');
  // 而且它必须**真的能把抬头换掉**
  const r = toCardOrText(reply, { verdict53: d });
  assert.strictEqual(r.card.header.title.content, d.line, '结论行没落进标题');
});

await t('Y2 反向对照：**没调链**时，同样一段回复不许被当成结论', () => {
  // 这一条防的是「有人在问『PRD 5.3 里 PASS 长什么样』，守衡照抄一遍模板」——
  // 少了它，任何含 5.3 字样的回答都会被强行套上结论抬头。
  const reply = 'PRD §5.3 里 PASS 长这样：\n【审查结论：PASS】未发现已知底线风险，可转交 @陈静姝 进行 sign-off。';
  assert.strictEqual(deriveVerdictLine({ replyText: reply }), null, '没调链也认了 —— 会把引用当结论');
  assert.strictEqual(deriveVerdictLine({ replyText: reply, reviewedByTool: false }), null);
});

await t('Y3 接线：内核必须把「这一轮调成了链」当成凭据传下去', () => {
  const src = fs.readFileSync(new URL('./agent/agent.mjs', import.meta.url), 'utf8');
  assert.ok(/toolTrace[\s\S]{0,120}?kb_review_chain[\s\S]{0,40}?ok/.test(src),
    '内核没有拿 toolTrace 里的 kb_review_chain 成功当凭据');
  assert.ok(/reviewedByTool:\s*true/.test(src), '没有把 reviewedByTool 传进 deriveVerdictLine');
  // 反向对照：那个凭据**必须**要求 `ok`（一次失败的链不是一次审查）
  assert.ok(!/kb_review_chain'\)\s*\?/.test(src), '凭据没有校验 ok —— 一次失败的链也会被当成审查过');
});

// ═══ 第 23 组 · 模型侧必须与链**并行**（2026-10-08）═══
//
// 方案 §③ 的原话是「每层的两侧都是完整的一遍审查，**互不等待**」。
// 而实现曾经是串行，且模型侧被绑在 `if (chainRan)` 上 ——
// **链报错/库忙时模型侧根本不跑** ⇒ 那一单用户什么都拿不到。
// Owner 2026-10-08 截图那张库忙卡就是这么来的。
await t('Z1 行为级：**链没跑成**时，模型侧那几条必须还在（不许被 chainRan 掐掉）', async () => {
  const { runSubmissionGate } = await import('./agent/agent.mjs');
  const TEXT = '这条站内广告文案能不能发：M6 吸奶器静音设计，夜里泵奶不吵醒宝宝';
  const g = await runSubmissionGate({
    inbound: { text: TEXT, imageCount: 0, videoCount: 0 },
    question: TEXT,
    notify: null,
    // ★ 2026-10-09：**必须注入** —— 这条夹具问题数 ≥3，不注入会真的在飞书里建一份云文档。
    //   实测：写这一条时忘了注入，跑一次自证就建了一份（§2.4.4 那个病）。
    mergedReportRunner: async () => ({ ok: true, url: 'https://example.invalid/docx/STUB', detail: '自证桩' }),
    // ★ 2026-10-09：**建议生成也必须注入** —— 它默认真打 LLM。
    //   不注入的话每条跑闸门的自证都会真调模型（实测直接把套件拖到超时）。
    adviceRunner: async ({ items }) => ({ ok: true, ms: 1,
      advice: Object.fromEntries((items || []).map((_, i) => [i, `自证桩给的改法 ${i}`])) }),
    // 链**没跑成**（模拟库忙：认领被占、起链抛异常）
    chainRunner: async () => { throw new Error('库忙（模拟）：认领被占'); },
    modelSideRunner: async () => ({ ok: true, dropped: [], ms: 1, findings: [
      { location: '全文', category: '措辞表达', severity: 'REVIEW', reason: '模型侧独立发现的措辞问题' }] }),
    publishRunner: async () => ({ ok: true }),     // 落表桩：**不许真写表**
  });
  assert.ok(g.dual, '链没跑成时双轨整段没跑 —— 模型侧被掐掉了（这就是原 bug）');
  // ★ 2026-10-08：`runSubmissionGate` 返回的 `dual` 是**汇总形状**（`{state, stats, ok, ...}`），
  //   不是内部那个 `{model, kb, merged, ...}` —— 断言按实际形状读，别按我以为的读。
  assert.ok(g.dual.stats.model >= 1,
    `模型侧的产出被丢了，合并读数：${JSON.stringify(g.dual.stats)}`);
  assert.ok(g.dual.stats.merged >= 1, '合并后一条都没有 —— 用户会收到一张空结论');
  assert.notStrictEqual(String(g.dual.state), '拒答', `合并态不该是拒答：${g.dual.state}`);
});

await t('Z2 接线：模型侧必须在 `await chainRunner` **之前**起跑', () => {
  const src = fs.readFileSync(new URL('./agent/agent.mjs', import.meta.url), 'utf8');
  const iP = src.indexOf('const modelSideP =');
  const iC = src.indexOf('res = await chainRunner(input)');
  assert.ok(iP > 0 && iC > 0, '找不到模型侧起跑点或起链点');
  assert.ok(iP < iC, '模型侧在链**之后**才起跑 —— 又退回串行了');
  // 反向对照：模型侧**不许**再被 chainRan 绑住
  assert.ok(!/if \(chainRan\) \{\s*[\s\S]{0,200}?await modelSideP/.test(src),
    '模型侧又被绑回 chainRan 了 —— 链坏掉时用户会重新变成「什么都没有」');
});

// ═══ 第 24 组 · 「轮」与「条数」是两个数，不许混成一个（2026-10-08）═══
//
// 起因：内核里写的是 `turns: sess.messages.length` —— 那是**条数**。而 daemon 把它
// 印成「🗜 历史已压缩（保留 130 轮 + 纪要 5249 字）」，真实含义是 **130 条 ≈ 24 轮**。
// 变量名（`turns`）、措辞（「轮」）、值（条数）三者不一致 —— `AGENTS.md` §2.4.3：
// **说出去的话比手上的依据大。**
//
// ⚠ 这一组要钉住的**不是**「源码里出现了 `countTurns` 这个词」。§2.4 点名的病就是
//   那个：「名字出现过 ≠ 它拦得住」，一条只查标识符存在的断言在有 import 的地方恒真。
//   所以 Z3/Z4 是**行为级与纯函数级**，并且各自带一条反向对照 —— 把任一处退回
//   `messages.length` 都会红（这两个数在真实会话里**必然不相等**）。

await t('Z3 口径：一轮 = 一条 user；assistant / tool 不计轮（反向对照：不许等于条数）', async () => {
  const mem = await import('./agent/memory.mjs');
  // 形状取自真实会话：一轮 = user + assistant(tool_calls) + 若干 tool 结果 + assistant
  const sess = { messages: [
    { role: 'user' }, { role: 'assistant', tool_calls: [{}] }, { role: 'tool' }, { role: 'assistant' },
    { role: 'user' }, { role: 'assistant' },
  ] };
  assert.strictEqual(mem.countTurns(sess), 2, '这个形状是 2 轮');
  assert.strictEqual(sess.messages.length, 6, '这个形状是 6 条');
  // ★ 反向对照：单独看上面那句是恒真的；这一句才真的钉住「不许退回条数」
  assert.notStrictEqual(mem.countTurns(sess), sess.messages.length,
    '轮数 == 条数 —— 又被混成一个数了（日志那句会重新开始说谎）');
  // 取不到时不许猜、不许空着（§2.2 第 7 条）
  assert.strictEqual(mem.countTurns(undefined), 0, 'undefined 会话');
  assert.strictEqual(mem.countTurns({}), 0, '没有 messages 键');
  assert.strictEqual(mem.countTurns({ messages: [{ role: 'user' }, null, { role: 'user' }] }), 2,
    '历史里混了坏记录也必须数得对');
});

await t('Z4 行为级：compact 之后**保留的是 keepTurns 轮**，不是 keepTurns 条', async () => {
  const mem = await import('./agent/memory.mjs');
  // 造 40 轮，每轮 4 条（assistant 带一次工具调用）⇒ 条数远大于轮数
  const messages = [];
  for (let i = 0; i < 40; i++) {
    messages.push({ role: 'user', content: `问题 ${i}` });
    messages.push({ role: 'assistant', tool_calls: [{ id: `c${i}` }] });
    messages.push({ role: 'tool', content: `结果 ${i}` });
    messages.push({ role: 'assistant', content: `回答 ${i}` });
  }
  const sess = { messages, summary: '' };
  const did = await mem.compact(sess, async () => '旧对话纪要', 5, 24);
  assert.ok(did, '160 条 > 触发线 24，必须压');
  assert.strictEqual(mem.countTurns(sess), 5,
    `保留的**轮数**必须是 5，实际 ${mem.countTurns(sess)}`);
  // ★ 反向对照：条数**必然**大于轮数。若这里相等，说明每轮只剩一条 ——
  //   那 Z4 就在测一个不存在的形状（§2.4：一个测不到真东西的断言等于没有）
  assert.ok(sess.messages.length > 5,
    `保留条数 ${sess.messages.length} 不大于 5 —— 这个用例没造出「一轮多条」的形状`);
});

await t('Z5 接线：日志那句必须**两个数一起给**，内核不许退回条数当轮数', () => {
  const d = fs.readFileSync(new URL('./ws_daemon.mjs', import.meta.url), 'utf8');
  assert.ok(/result\.meta\.messages/.test(d), '日志没读 `meta.messages` —— 条数根本没印出来');
  assert.ok(/result\.meta\.turns/.test(d), '日志没读 `meta.turns` —— 轮数丢了');
  // ★ 反向对照：旧的坏形状 —— 只说「保留 N 轮」而不给条数。这一句红了才说明
  //   上面两句不是恒真的（它们只证明两个词出现过，证明不了那句话现在说得对）。
  assert.ok(!/保留 \$\{result\.meta\.turns\} 轮(?!（)/.test(d),
    '又退回「保留 N 轮」的单数形式 —— 那句话比依据大');

  const a = fs.readFileSync(new URL('./agent/agent.mjs', import.meta.url), 'utf8');
  assert.ok(/turns:\s*mem\.countTurns\(sess\)/.test(a),
    '`meta.turns` 没走 `mem.countTurns` —— 口径脱离了唯一那一处');
  assert.ok(!/turns:\s*sess\.messages\.length/.test(a),
    '`meta.turns` 又变回条数了 —— 日志会重新开始说「保留 130 轮」');
});

// ═══ 第 25 组 · 同一条链，一轮里只许跑一次（2026-10-08）═══
//
// 起因（真实事故，Owner 2026-10-08 19:08 那张图）：闸门 **147386ms** 就跑完了，
// 模型又自己调了一遍 `kb_review_chain`（**709739ms**，超时没出结果）⇒
//   ① 人等了 **15 分钟**（`💬 回复 3159 字，耗时 900041ms`）；
//   ② 模型把它那次失败写进了**对外卡片**：「我这次实跑 709 秒没出最终回答」。
// 历史读数：闸门跑成 **72** 次，模型自己又调 **18** 次 —— 不是偶发。
//
// ⚠ 这一组**一次都不许真跑链** —— 真跑会写飞书（§2.4.4：自证不许有副作用）。
//   所以判据全落在纯函数上；而「漏斗真的拦得住」那一条用的是这个组合：
//   **装好缓存 + 故意喂一段坏 JSON**。坏 JSON 在**解析那一跳**才失败，
//   所以「它没报 JSON 错」就证明它命中了缓存、**没有往下走** —— 正反都在零副作用下可证。

await t('Z6 纯判据：命中 / 别的工具 / 没装过 / 过期 / 坏记忆 —— 五个方向各自可分辨', async () => {
  const T = await import('./agent/tools.mjs');
  const env = { tool: 'kb_review_chain', ok: true, result: { answer: 'REVIEW 5 处' } };
  const now = Date.now();
  const memo = { at: now, envelope: env };
  assert.strictEqual(T.chainMemoLookup({ name: 'kb_review_chain', memo, nowMs: now }), env, '装了缓存就该回它');
  assert.strictEqual(T.chainMemoLookup({ name: 'judge_copy', memo, nowMs: now }), null, '别的工具不许吃这条缓存');
  assert.strictEqual(T.chainMemoLookup({ name: 'kb_review_chain', memo: null, nowMs: now }), null, '没装过就照常跑');
  assert.strictEqual(T.chainMemoLookup({ name: 'kb_review_chain', memo: undefined, nowMs: now }), null, 'memo 是 undefined');
  // ★ 反向对照（TTL 是**独立于**「每轮清空」的第二道 —— 少了它，漏一次复位就会串轮）
  assert.strictEqual(T.chainMemoLookup({ name: 'kb_review_chain', memo: { at: now - 31 * 60 * 1000, envelope: env }, nowMs: now }),
    null, '过期 31 分钟必须放行 —— 否则 TTL 是摆设');
  assert.strictEqual(T.chainMemoLookup({ name: 'kb_review_chain', memo: { at: now - 29 * 60 * 1000, envelope: env }, nowMs: now }),
    env, '未过期必须命中 —— 否则 TTL 边界写反了（这一对才把边界钉死）');
  assert.strictEqual(T.chainMemoLookup({ name: 'kb_review_chain', memo: { at: NaN, envelope: env }, nowMs: now }),
    null, '坏记忆当没有 —— 宁可重跑，不可乱答');
  assert.strictEqual(T.chainMemoLookup({ name: 'kb_review_chain', memo: { at: now }, nowMs: now }),
    null, '装着 at 却没有信封 —— 不许回 undefined');
});

await t('Z7 纯判据：**只装跑成的** —— 失败了必须留着重试的机会', async () => {
  const T = await import('./agent/tools.mjs');
  assert.strictEqual(T.chainMemoShouldArm({ name: 'kb_review_chain', result: { answer: 'x' } }), true);
  // ★ 反向对照：缓存一次失败 = 把「结论未知」钉死一整轮
  //   （§2.4.2：未测不许与通过长得一样；重试的机会必须留着）
  assert.strictEqual(T.chainMemoShouldArm({ name: 'kb_review_chain', result: { error: '超时' } }), false,
    '跑失败也被缓存了 —— 这一轮再也没有重试的机会');
  assert.strictEqual(T.chainMemoShouldArm({ name: 'kb_review_chain', result: null }), false, '空结果不许装');
  assert.strictEqual(T.chainMemoShouldArm({ name: 'kb_review_chain', result: 'string' }), false, '非对象不许装');
  assert.strictEqual(T.chainMemoShouldArm({ name: 'judge_copy', result: { answer: 'x' } }), false, '别的工具不许装');
});

await t('Z8 行为级：漏斗上真的拦得住，且拦在解析参数**之前**（零副作用）', async () => {
  const T = await import('./agent/tools.mjs');
  // ① 没装缓存时喂坏 JSON：必须走到**解析**那一跳 ⇒ 报 JSON 错。
  //    这一句同时证明护栏**不是恒真的**（§2.4.4：一个恒真的判据等于没有）。
  T._resetChainMemoForTest();
  const miss = await T.executeTool('kb_review_chain', '这不是 JSON');
  assert.strictEqual(miss.ok, false, '没装缓存却命中了 —— 护栏恒真，等于没有');
  assert.ok(/不是合法 JSON/.test(String(miss.error)), `应当走到解析那一跳，实际：${miss.error}`);

  // ② 装上缓存后再喂同一段坏 JSON：必须**回缓存**，而不是报 JSON 错
  //    ⇒ 证明它拦在解析之前，拦住的正是那一次 5~15 分钟的真发布动作。
  const env = { tool: 'kb_review_chain', ok: true, result: { answer: 'REVIEW 5 处（闸门那次的结果）' } };
  T._armChainMemoForTest(env);
  const hit = await T.executeTool('kb_review_chain', '这不是 JSON');
  assert.strictEqual(hit, env, '装了缓存却没回它 —— 重复跑没被拦住');
  assert.strictEqual(T.chainMemoStats().hit, 1, '命中数没记 —— 这件事就没有读数了（§2.4）');
  assert.strictEqual(T.chainMemoStats().armed, true, '装了却报没装');

  // ③ 复位之后必须立刻放行 —— 这一跳就是「每轮边界」
  T.beginChainTurn();
  assert.strictEqual(T.chainMemoStats().armed, false, 'beginChainTurn 没清掉缓存 —— 会串轮');
  const after = await T.executeTool('kb_review_chain', '这不是 JSON');
  assert.ok(/不是合法 JSON/.test(String(after.error)),
    '复位后仍命中 —— 守衡会拿上一轮的结论去答这一轮的图（方向不对称：漏跑只是慢，串轮是答错）');
  T._resetChainMemoForTest();
});

await t('Z9 接线：`beginChainTurn()` 必须在**调闸门之前**（否则闸门自己那次会被清掉）', () => {
  const src = fs.readFileSync(new URL('./agent/agent.mjs', import.meta.url), 'utf8');
  const iB = src.indexOf('beginChainTurn()');
  const iG = src.indexOf('await runSubmissionGate({');
  assert.ok(iB > 0, '找不到 `beginChainTurn()` 调用 —— 护栏没有每轮边界');
  assert.ok(iG > 0, '找不到 `runSubmissionGate` 调用');
  assert.ok(iB < iG,
    '`beginChainTurn()` 排在闸门**之后** —— 会把闸门刚装上的缓存自己清掉，等于没装');

  // meta 里必须带上这条护栏自己的读数，否则命中只是一个「没出现的日志」
  assert.ok(/chainMemo:\s*chainMemoStats\(\)/.test(src),
    '`meta` 没带 `chainMemo` 读数 —— 护栏有没有生效只能靠猜');
});

await t('Z10 治因：`formatChainBlock` 必须明说「链已经跑完了，不要再调」', async () => {
  const rg = await import('./agent/review_gate.mjs');
  const block = rg.formatChainBlock({ answer: '【审查结论：REVIEW】共发现 5 处需人工确认。' });
  assert.ok(/不要再调 `kb_review_chain`/.test(block),
    '没告诉模型链已经跑过了 —— 它会再跑一遍（那 18 次就是这么来的）');
  // ★ 第二条：模型那次失败的自述**不许进对外正文**（19:08 那张卡就是这么写的）
  assert.ok(/不许把它写进回话/.test(block),
    '没拦住「我实跑 N 秒没出结果」进对外卡片 —— 业务同事会读到内部故障自述');

  // ★ 反向对照：链**没跑成**时不许说「已经跑完、别再调」—— 那是把未知说成完成
  const err = rg.formatChainBlock({ error: '超时' });
  assert.ok(!/不要再调/.test(err), '链没跑成却说「已经跑完，别再调」—— 把未知说成了完成');
  assert.ok(/没跑成|未知/.test(err), '失败分支必须说清这是未知');
  const empty = rg.formatChainBlock({});
  assert.ok(!/不要再调/.test(empty), '没结论却说「已经跑完」');
});

// ═══ 第 26 组 · 「问题数」只能有一个：抬头那个 N 不许再从链的正文里抠（2026-10-08）═══
//
// Owner 的规则原话：「我在飞书侧 @守衡 提问后，双轨并行（知识库+模型），
// **双轨按照 PRD ≧3 个问题输出报告链接到飞书文档**」。
//
// 查下来 PRD 那侧**早就实现了**（KB 的 `feishu_publish.py::REPORT_LINK_MIN_ISSUES = 3`）。
// 坏的是**口径** —— 一单里有三个「问题数」在打架：
//
//   | 数 | 来自谁 | 19:44 那单 | 19:08 那张图 |
//   |---|---|---|---|
//   | 卡片抬头那个数 | 链的结论原文（**正则抠**出来） | — | **12** |
//   | 报告阈值读的数 | 机读旁挂 `issue_count` | **2** | 5 |
//   | 人实际看到的条目 | 双轨合并条数 | **10** | 7 |
//
// 人看到 10 ⇒ 按规则该给链接；阈值读 2 ⇒ `2 < 3` ⇒ 不生成报告 ⇒ **没有链接**。
//
// 这一组钉住的是「N 变成**入参**」这件事（本仓这一半）。接线（`dual_track.mjs` →
// `agent.mjs` → 信封）在另一个会话停手之后再做 —— 判据先立，接线才有东西可对。

await t('Z11 纯判据：由显式条数派生 §5.3 结论行，且派生出来的行当场过 conforms()', async () => {
  const P = await import('./agent/prd53.mjs');
  const rev = P.verdictLineFor({ state: 'REVIEW', n: 10 });
  assert.strictEqual(rev.line, '【审查结论：REVIEW】共发现 10 处需人工确认。');
  assert.strictEqual(rev.state, 'REVIEW');
  // ★ 派生出来的行必须**自己合 §5.3** —— 否则我们是在批量生产不合规的抬头
  assert.strictEqual(rev.conform.ok, true, `派生出来的行不合 §5.3：${rev.conform.why}`);
  const blk = P.verdictLineFor({ state: 'BLOCK', n: 3 });
  assert.strictEqual(blk.line, '【审查结论：BLOCK】共发现 3 处必须修改。');
  assert.strictEqual(blk.conform.ok, true, `派生出来的 BLOCK 行不合 §5.3：${blk.conform.why}`);
});

await t('Z12 纯判据：**编不出数的时候一个都不许编** —— 六个方向各自可分辨', async () => {
  const P = await import('./agent/prd53.mjs');
  // ★ n=0 单独一条，理由与其它不同：`mergedState()` 里「合并 0 条 + 库侧 REVIEW」
  //   会给出 REVIEW（覆盖缺口那一类），而「共发现 0 处需人工确认」**自己跟自己矛盾**。
  assert.strictEqual(P.verdictLineFor({ state: 'REVIEW', n: 0 }), null, '0 处 → 必须退回，不许写「共发现 0 处」');
  assert.strictEqual(P.verdictLineFor({ state: 'REVIEW', n: NaN }), null, 'NaN 不许编');
  assert.strictEqual(P.verdictLineFor({ state: 'REVIEW' }), null, '缺 n 不许编');
  assert.strictEqual(P.verdictLineFor({ state: 'REVIEW', n: -1 }), null, '负数不许编');
  assert.strictEqual(P.verdictLineFor({ state: 'REVIEW', n: 2.5 }), null, '小数不许编');
  // PASS 的 §5.3.1 模板里**没有 N**；拒答 / NEEDS_INPUT 不在 §5.3 里
  assert.strictEqual(P.verdictLineFor({ state: 'PASS', n: 3 }), null, 'PASS 模板无 N，派生不出来');
  assert.strictEqual(P.verdictLineFor({ state: '拒答', n: 3 }), null, '拒答不在 §5.3 里');
  // 反向对照：合法的数**必须**派得出来 —— 否则上面六条恒真（一个全都返回 null 的实现也能过）
  assert.ok(P.verdictLineFor({ state: 'REVIEW', n: 1 }), 'n=1 是合法条数，必须派得出来');
});

await t('Z13 ★ 反向对照：**不给合并数时，行为必须与改动前逐字相同**', async () => {
  const P = await import('./agent/prd53.mjs');
  const A = '【审查结论：REVIEW】共发现 12 处需人工确认。\n\n1.【平台与促销】…\n\n建议转 李倩怡 复核。';
  // 这一条是整组里最重要的反向对照：没有它，接线一旦漏传参数，
  // 卡片会**静默退回**旧口径（抠链的正文），而没有任何东西会红。
  const noMerge = P.deriveVerdictLine({ answer: A });
  assert.strictEqual(noMerge.from, 'chain', '不给合并数时必须仍走第 ① 支');
  assert.ok(/共发现 12 处/.test(noMerge.line), '不给合并数时必须仍用链抠出来的那个数');
  assert.ok(noMerge.block, '不给合并数时 block 必须照旧非空');

  const withMerge = P.deriveVerdictLine({ answer: A, mergedCount: 7, mergedState: 'REVIEW' });
  assert.strictEqual(withMerge.from, 'dual-track-merged', '给了合并数必须走第 ⓪ 支');
  assert.ok(/共发现 7 处需人工确认。/.test(withMerge.line),
    `抬头那个数必须变成双轨合并数，实际：${withMerge.line}`);
  // ★ `block` 必须**与不给时同一个对象/值** —— 逐条块那一格归信封层的 `groups` 管
  //   （实测日志 `逐条块=forced·groups`），这一支去改块就是跟它抢格子。
  assert.strictEqual(withMerge.block, noMerge.block, '第 ⓪ 支不许动 block —— 会跟 groups 抢同一格');

  // 坏读数一律退回第 ① 支（而不是编一个「共发现 0 处」）
  const zero = P.deriveVerdictLine({ answer: A, mergedCount: 0, mergedState: 'REVIEW' });
  assert.strictEqual(zero.from, 'chain', '合并数 0 必须退回链那一行');
  const pass = P.deriveVerdictLine({ answer: A, mergedCount: 3, mergedState: 'PASS' });
  assert.strictEqual(pass.from, 'chain', '合并态 PASS 不许被派生成 REVIEW/BLOCK 行');
  const nan = P.deriveVerdictLine({ answer: A, mergedCount: NaN, mergedState: 'REVIEW' });
  assert.strictEqual(nan.from, 'chain', 'NaN 必须退回，不许编数');
});

await t('Z14 ★ 行为级：卡片抬头那个数必须 == 卡里那个数（`rendered.total`），不是「并进来几条」', async () => {
  const { runSubmissionGate } = await import('./agent/agent.mjs');
  // 夹具**照抄 19:08 那个真实形状**：库侧判到 5 条、但 PRD §5.3.3 规定 ≥3 时只出分类汇总
  // ⇒ 逐条抠不出来（`txtN=0`）⇒ `kbGap = 5`；模型侧 7 条 ⇒ 并进 7 条。
  // 于是 `total = 7 + 5 + 0 = 12`，而 `stats.merged = 7` —— **两个数必然不等**。
  // 这正是那张卡「抬头 12 / 你数出 7 条」的成因，而 12 是**对的**（卡里另有一句
  // 「另有 5 条未并进本卡」）。所以断言必须钉 `total`，不能钉 `merged`。
  const KB_ANSWER = [
    '【审查结论：REVIEW】共发现 5 处需人工确认。',
    '',
    '· 平台与促销类问题：5 个',
    '',
    '建议转 李倩怡 复核。',
  ].join('\n');
  const g = await runSubmissionGate({
    inbound: { text: '审核下这张图', imageCount: 1, videoCount: 0 },
    question: '审核下这张图',
    notify: null,
    // ★ 2026-10-09：**必须注入** —— 这条夹具问题数 ≥3，不注入会真的在飞书里建一份云文档。
    //   实测：写这一条时忘了注入，跑一次自证就建了一份（§2.4.4 那个病）。
    mergedReportRunner: async () => ({ ok: true, url: 'https://example.invalid/docx/STUB', detail: '自证桩' }),
    // ★ 2026-10-09：**建议生成也必须注入** —— 它默认真打 LLM。
    //   不注入的话每条跑闸门的自证都会真调模型（实测直接把套件拖到超时）。
    adviceRunner: async ({ items }) => ({ ok: true, ms: 1,
      advice: Object.fromEntries((items || []).map((_, i) => [i, `自证桩给的改法 ${i}`])) }),
    chainRunner: async () => ({
      answer: KB_ANSWER,
      // 机读旁挂：库侧的**结构化条数**（逐条明细抠不出来时才靠它）
      review: { state: 'REVIEW', issue_count: 5 },
      report: 'https://momcozy-in.feishu.cn/docx/AAA',
    }),
    publishRunner: async () => ({ ok: true, record_id: 'recX' }),
    // ★ 2026-10-09：**必须注入** —— 不注入的话，问题数 ≥3 的夹具会真的在飞书里建一份云文档
    //   （§2.4.4：跑一次自证，改掉了它要保护的东西。实测已发生过一次）。
    mergedReportRunner: async () => ({ ok: true, url: 'https://example.invalid/docx/STUB', detail: '自证桩' }),
    // ★ 2026-10-09：**建议生成也必须注入** —— 它默认真打 LLM。
    //   不注入的话每条跑闸门的自证都会真调模型（实测直接把套件拖到超时）。
    adviceRunner: async ({ items }) => ({ ok: true, ms: 1,
      advice: Object.fromEntries((items || []).map((_, i) => [i, `自证桩给的改法 ${i}`])) }),
    modelSideRunner: async () => ({ ok: true, ms: 10,
      findings: [1, 2, 3, 4, 5, 6, 7].map((n) => ({ category: '本地化', location: `画面 ${n}`, severity: 'REVIEW', reason: 'x' })) }),
  });

  const total = g.dual?.total;
  const mergedN = g.dual?.stats?.merged;
  assert.strictEqual(mergedN, 7, `夹具前提：并进 7 条，实际 ${mergedN}`);
  assert.strictEqual(total, 12, `夹具前提：卡里那个数应是 7+5=12，实际 ${total}`);
  // ★ 前提必须验在**输入/中间量**上，不能验在抬头 `verdict53.line` 上 ——
  //   拿改完之后的输出验前提，等于把「修好了」当成红的（第一版就这么红的）。
  assert.notStrictEqual(total, mergedN, '夹具前提：两个数必须不同，否则这条测不出东西');

  const n = Number((/共发现 (\d+) 处/.exec(g.verdict53?.line ?? '') || [])[1]);
  assert.strictEqual(n, total,
    `抬头说 ${n} 处，而卡里那个数是 ${total} —— 抬头与条目又分家了`);
  // ★ 反向对照：把 `mergedCount` 接成 `items.length`（=7）会让上面那条红 —— 这就是它存在的意义
  assert.notStrictEqual(n, mergedN,
    `抬头接成了「并进来几条」（${mergedN}）—— 会丢掉库侧那 ${total - mergedN} 条，`
    + '并与卡里「另有 N 条未并进本卡」那句话自相矛盾');
});

// ═══ 第 27 组 · 「问题数 ≥3 ⇒ 飞书文档要带报告」（Owner 2026-10-09）═══
//
// Owner 的原话：「我的目标是让守衡输出的问题数量按照 PRD 等于或大于 3 个问题时，
// **写入的飞书文档要带报告**」。
//
// 病灶：报告**只有库侧会建**，而它的门槛读的是**它自己的** `issue_count`。
// 实测 2026-10-09 09:35 那张图：卡上说 6 处（库侧 1 ＋ 模型侧 5），而旁挂 `issue_count = 1`
// ⇒ 库侧不建 docx ⇒ `report_url = null` ⇒ **按 PRD 该给报告，却没有任何链接可给**。
// 现在改由**本仓**建：门槛读**卡里那个数**（`rendered.total`），正文含两侧全部条目。
//
// ⚠ 这一组**用桩**（`mergedReportRunner`）—— 真调会在 Owner 的飞书里建一份云文档。
//   写这一组时就因为忘了注入，跑一次自证真建了一份（§2.4.4 那个病，已修）。

await t('Z15 ★ 行为级：问题数 ≥3 且库侧没给链接 ⇒ 本仓建报告，卡里那一行是**真链接**', async () => {
  const { runSubmissionGate } = await import('./agent/agent.mjs');
  const KB_ANSWER = ['【审查结论：REVIEW】共发现 1 处需人工确认。', '',
    '1.【本地化】图 1', '', '建议转 李倩怡 复核。'].join('\n');
  const STUB = 'https://example.invalid/docx/Z15';
  let called = 0;
  const g = await runSubmissionGate({
    // ★ 2026-10-09：**建议生成必须注入** —— 它默认真打 LLM（漏一处就把套件拖到超时，实测 7.5s/次）
    adviceRunner: async ({ items }) => ({ ok: true, ms: 1,
      advice: Object.fromEntries((items || []).map((_, i) => [i, `自证桩给的改法 ${i}`])) }),
    inbound: { text: '审核下这张图', imageCount: 1, videoCount: 0 },
    question: '审核下这张图', notify: null,
    chainRunner: async () => ({ answer: KB_ANSWER, review: { state: 'REVIEW', issue_count: 1 } }),
    publishRunner: async () => ({ ok: true, record_id: 'recX' }),
    modelSideRunner: async () => ({ ok: true, ms: 1,
      findings: [1, 2, 3, 4, 5].map((n) => ({ category: '本地化', location: `画面 ${n}`, severity: 'REVIEW', reason: 'x' })) }),
    mergedReportRunner: async (md) => {
      called++;
      // 报告正文必须**两侧条目都在**（Owner：「6 个就展示 6 个问题」）。
      // ★ 2026-10-13：两侧**不再各有一个小标题**（Owner 把它们连免责一起列进了「废话」），
      //   所以判据从「有没有那两个标题」改成「**条目在不在、来源标没标**」——
      //   后者才是「这条回不回得了源」，也是那两个标题原先承担的**唯一**信息。
      // ★ 2026-10-13（Owner：「不要出现 知识库侧，模型侧」）：标记改了措辞，
      //   判据跟着改成**新措辞**（去的是词，不是「回不回得了源」这条信息）。
      assert.ok(/\*\*有库内条款依据\*\*/.test(md), '报告缺「有库内条款依据」那条（来源标记没了）');
      assert.ok(/\*\*无库内依据 · 建议转人工\*\*/.test(md), '报告缺「无库内依据」那条（来源标记没了）');
      assert.ok(!/知识库侧|模型侧/.test(md), '「知识库侧/模型侧」又出现了（Owner 点名去掉）');
      assert.ok(!/## 一、知识库侧|## 二、模型侧/.test(md), '两个来源小标题又回来了（Owner 点名去掉）');
      // ★ 2026-10-09：`判定` 如今**带加粗**（Owner 裁定「字段加粗保留」）且**排在 PRD 四要素之后**
      //   ⇒ 原先的 `^ {3}判定：`（非加粗）在这里数出 0 条，把「量条目数」误判成失败。
      //   这一处查的是**条数**、与加粗无关，所以认两种写法（`\*{0,2}`），
      //   避免下次再因排版改动而误红。
      const n = (md.match(/^ {3}\*{0,2}判定\*{0,2}：/gm) || []).length;
      assert.strictEqual(n, 6, `报告里应有 6 条（两侧合计），实际 ${n} 条`);
      assert.ok(md.startsWith('# '), '报告首行必须是 H1（lark-cli markdown 导入的硬要求）');
      return { ok: true, url: STUB, detail: '自证桩' };
    },
  });
  assert.strictEqual(called, 1, '≥3 时没去建报告 —— Owner 的目标没达到');
  const blk = String(g.verdict53?.block ?? '');
  assert.ok(blk.includes(STUB), `卡里那一行不是真链接：${(blk.match(/→ 查看完整问题清单[^\n]*/) || ['(那一行都没有)'])[0].slice(0, 120)}`);
  assert.strictEqual(g.verdict53?.from, 'dual-track-merged', '抬头没走双轨合并那一支');
});

await t('Z16 ★ 反向对照：建报告**失败**时不许说成已出报告，且**不许阻断结论**', async () => {
  const { runSubmissionGate } = await import('./agent/agent.mjs');
  const KB_ANSWER = ['【审查结论：REVIEW】共发现 1 处需人工确认。', '',
    '1.【本地化】图 1', '', '建议转 李倩怡 复核。'].join('\n');
  const g = await runSubmissionGate({
    // ★ 2026-10-09：**建议生成必须注入** —— 它默认真打 LLM（漏一处就把套件拖到超时，实测 7.5s/次）
    adviceRunner: async ({ items }) => ({ ok: true, ms: 1,
      advice: Object.fromEntries((items || []).map((_, i) => [i, `自证桩给的改法 ${i}`])) }),
    inbound: { text: '审核下这张图', imageCount: 1, videoCount: 0 },
    question: '审核下这张图', notify: null,
    chainRunner: async () => ({ answer: KB_ANSWER, review: { state: 'REVIEW', issue_count: 1 } }),
    publishRunner: async () => ({ ok: true, record_id: 'recX' }),
    modelSideRunner: async () => ({ ok: true, ms: 1,
      findings: [1, 2, 3, 4, 5].map((n) => ({ category: '本地化', location: `画面 ${n}`, severity: 'REVIEW', reason: 'x' })) }),
    mergedReportRunner: async () => ({ ok: false, url: null, detail: '建云文档失败：权限不足' }),
  });
  // 结论照样要出来（报告与三态是两件事）
  assert.ok(/共发现 6 处/.test(g.verdict53?.line ?? ''), `结论被报告失败带崩了：${g.verdict53?.line}`);
  const blk = String(g.verdict53?.block ?? '');
  assert.ok(/查看完整问题清单/.test(blk), '连那一行都没了 —— 拿不到也要出声');
  assert.ok(/本次未拿到报告链接/.test(blk), '建失败却没说清 —— 会让人以为没有报告这回事');
  assert.ok(!/momcozy-in\.feishu\.cn/.test(blk), '建失败却编了一个飞书链接');
});

await t('Z17 ★ 接线：建报告那一步**必须可注入**，且默认走本仓的 publishReportDoc', () => {
  const src = fs.readFileSync(new URL('./agent/agent.mjs', import.meta.url), 'utf8');
  assert.ok(/mergedReportRunner\s*=\s*publishMergedReport/.test(src),
    '闸门没有可注入的 mergedReportRunner —— 自证会真的往飞书建文档（§2.4.4）');
  // ★ 2026-10-13：变量名从 `md` 改成 `mdDoc`（报告现在渲染**两份**：投出的这份 ＋ 留底那份），
  //   判据跟着认新名字 —— 它查的是「走没走注入的那个 runner」，与变量叫什么无关。
  assert.ok(/await mergedReportRunner\(md(Doc|Full)?,/.test(src), '接线里没走注入的那个 runner');
  // ★ 反向对照：**不许**绕过注入点去直接调真函数 —— 那会让上面两条恒真
  assert.ok(!/await publishMergedReport\(md/.test(src),
    '接线里直接调了真函数 —— 注入点形同虚设，自证又会建真文档');
  // 门槛必须读**卡里那个数**，不是「并进来几条」
  assert.ok(/rendered0\.total >= REPORT_LINK_MIN_ISSUES/.test(src),
    '门槛没读 `rendered0.total` —— 会退回「并进来几条」，把库侧未并进的那部分丢掉');
});

// ═══ 第 28 组 · 报告链接必须在**收起区之外**（Owner 2026-10-09 第三次反馈）═══
//
// 三次同一个病，每次换一层：
//   ① 第一版：链接拼在 8 条逐条清单**之后** ⇒ 太长看不到
//   ② 第二版：挪到结论块的**第 2 行** ⇒ 而**整块在卡里是收起的**
//      （实测那张 8 处问题的卡：「（已收起 1 条证据：审查结论）」）⇒ 还是看不到
//   ③ 现在：与 `applyMediaRead` 同构，搬进**可见的字符串格**（verdict/reasoning/…）
//
// 判据一句话：**一个必须点开才看得见的链接，等于没有链接。**

await t('Z18 ★ 行为级：报告链接必须进**卡片可见格**，不许只躺在折叠的结论块里', () => {
  const line = '【审查结论：REVIEW】共发现 8 处需人工确认。';
  const reply = '[[card:evidence]]\n' + JSON.stringify({
    title: '模型自拟的抬头', verdict: '**我读到了**\n图 1 张',
    groups: [{ title: '审查结论', content: '结论块（会被收起）' }],
  });
  const URL = 'https://momcozy-in.feishu.cn/docx/VISIBLE';
  const r = toCardOrText(reply, { verdict53: { state: 'REVIEW', line, from: 'chain' },
                                    mediaRead: '图 1 张', reportLink: URL });
  assert.strictEqual(r.mode, 'card', `应当建出卡片，实际 ${r.mode}`);
  // ★ 可见格（verdict）里必须有它 —— 这才是「看得见」的定义
  assert.ok(String(r.data?.verdict ?? '').includes(URL),
    `链接没进可见格（verdict），实际：${JSON.stringify(String(r.data?.verdict ?? '').slice(0, 160))}`);
  assert.ok(/查看完整问题清单与修改建议/.test(String(r.data?.verdict ?? '')), '可见格里缺那一行');
  // **搬不是砍**：「我读到了」那段还得在（换格子，不是删）
  assert.ok(/我读到了/.test(String(r.data?.verdict ?? '')), '把原有读数挤掉了 —— 搬是搬，砍是砍');
});

await t('Z19 反向对照：**没有链接时一个字符都不许加**（不许凭空造一行）', () => {
  const reply = '[[card:evidence]]\n' + JSON.stringify({ title: 'T', verdict: '原样' });
  const r = toCardOrText(reply, { verdict53: null, reportLink: null });
  assert.ok(!/查看完整问题清单/.test(JSON.stringify(r.card)), '没链接却造了一行');
  assert.strictEqual(r.data?.verdict, '原样', '没链接时 verdict 被改动了');
});

await t('Z20 接线：daemon 必须把 meta.reportLink 传给信封（否则上面两条测试全绿而线上依旧没有）', () => {
  const d = fs.readFileSync(new URL('./ws_daemon.mjs', import.meta.url), 'utf8');
  assert.ok(/reportLink:\s*result\.meta\?\.reportLink/.test(d), 'daemon 没把 reportLink 传下去');
  const a = fs.readFileSync(new URL('./agent/agent.mjs', import.meta.url), 'utf8');
  assert.ok(/reportLink:\s*g\.dual\?\.reportUrl/.test(a), 'handleMessage 的 meta 没带 reportLink');
  assert.ok(/reportUrl:\s*dual\.reportUrl/.test(a), '闸门的 dual 读数里没带 reportUrl');
});

await t('Z20b ★ 行为级：传下去的读数**必须真被用上**（Z20 那种源码文本断言挡不住「传了但签名里没接」）', async () => {
  // ★★ 2026-10-13：写这条时真抓到一个 —— `onMessage` 一路传着
  //   `reportLink: result.meta?.reportLink`，而 `replyTo(..., { verdict53, mediaRead })`
  //   的解构签名里**根本没有 reportLink** ⇒ 静默丢弃。Z20 是绿的，因为它只查
  //   **源码里出现过那一行**（§2.4：「名字出现过」不是「它拦得住」）。
  //   ⇒ 判据必须走**行为**：把读数交给那条真的成形路径，看它有没有落到卡上。
  const { toCardOrText } = await import('./reply-cards/envelope.mjs');
  const V = { state: 'BLOCK', line: '【审查结论：BLOCK】共发现 1 处必须修改。',
              from: 'dual-track-merged',
              block: '【审查结论：BLOCK】共发现 1 处必须修改。\n1.【合规】全文\n   原因：x\n请修改后重新提交。' };
  const DOCX = 'https://momcozy-in.feishu.cn/docx/Z20B';   // ⚠️ 别叫 `URL` —— 会遮蔽全局构造函数
  const BND = '本结论为 **P0 红线拦截**（确定性修改、**未跑**专项审查），**不是 PASS 依据**。';
  const r = toCardOrText('模型原话', { verdict53: V, reportLink: DOCX, boundary: BND });
  const card = JSON.stringify(r.card ?? {});
  assert.ok(card.includes(DOCX), '报告链接没落到卡上 —— 那就是被某一跳丢了');
  assert.ok(card.includes('P0 红线拦截'), '卡脚边界没落到卡上');
  // 反向对照：不给就一个都不许有（否则上面两条可能是「恒印一句」）
  const r0 = toCardOrText('模型原话', { verdict53: V });
  assert.ok(!JSON.stringify(r0.card ?? {}).includes(DOCX), '没给链接却印了链接');
  assert.ok(!JSON.stringify(r0.card ?? {}).includes('P0 红线拦截'), '没给边界却印了边界');
  // 接线（源码级，与 Z20 同一层）：签名里必须真的接住这两个读数
  const d = fs.readFileSync(new URL('./ws_daemon.mjs', import.meta.url), 'utf8');
  const sig = (d.match(/async function replyTo\([^)]*\)[^{]*\{/) || [''])[0];
  assert.ok(/reportLink = null/.test(sig), `replyTo 的签名里没有 reportLink：${sig.slice(0, 120)}`);
  assert.ok(/boundary = null/.test(sig), 'replyTo 的签名里没有 boundary');
  assert.ok(/toCardOrText\(rawReply, \{ verdict53: v53, reportLink, boundary \}\)/.test(d),
    'replyTo 没有把这两个读数交给 toCardOrText');
  // ★ 2026-10-13：`mediaRead` 从这条链上**整个撤掉了**（读数不上卡）——
  //   留一个没人读的入参就是「传了但没人接」那个病。撤了就要撤干净：
  assert.ok(!/mediaRead/.test(sig), `replyTo 的签名里还留着没人读的 mediaRead：${sig.slice(0, 120)}`);
  assert.ok(!/mediaRead/.test(d.slice(d.indexOf('const shaped = toCardOrText'), d.indexOf('const shaped = toCardOrText') + 200)),
    'replyTo 还在往 toCardOrText 传 mediaRead');
});
// ═══ 第 29 组 · 报告不许替库侧下「有依据」这个结论（Owner 2026-10-09）═══
//
// 实测那一单：卡上守衡写着「4/4 条依据与素材无关，另 2 条 L0 sha 不一致」，
// 而同一批条目在报告里顶着「**有条款级依据**」这个标题、还带条款号与飞书直链 ——
// **报告比卡片可信得多** ⇒ 链接修好后危害反而被放大。
//
// 改法只做「能与不能」的区分：标题降级为**出处**，并加**常驻**免责。
// 常驻而不是「检测到才写」：`evidence_complete` 那类信号实测是 `undefined`，
// 靠它判会时灵时不灵 —— 而**不确定性必须无条件说出来**（§2.4.2）。

await t('Z21 ★ 报告只留 PRD 字段：两个来源小标题、免责、计数口径全部去掉', async () => {
  // ★★ 2026-10-13（Owner 三条里的第 3 条）：报告要按 PRD 字段输出，把「废话」去掉。
  //   Owner 逐条点名要去掉的：`- 用户原提问：…` / `- 判据：PRD §5.3.4…` /
  //   `## 一、知识库侧（库内条款条目）` / 那段 ⚠️ 免责 / `（本单知识库侧没有并进任何条目。）` /
  //   `## 二、模型侧（无库内依据，只能转人工）` / 那段 blockquote / **整个「三、计数口径」**。
  const M = await import('./agent/merged_report.mjs');
  const md = M.renderMergedReportMd({
    merged: [
      { location: '图上文案', category: '平台与促销', severity: 'REVIEW', source: 'kb',
        reason: 'x', kb: { suggestionLine: '删掉「最」' } },
      { location: '视频 00:12', category: '合规', severity: 'REVIEW', source: 'model',
        reason: 'y', suggestion: '改掉' },
    ],
    total: 2, state: 'REVIEW', line: '【审查结论：REVIEW】共发现 2 处需人工确认。',
    question: '审核这段文案', contentId: 'AUTO-x', at: '2026-10-09', kbTextCount: 1, modelCount: 1 });
  // ★ 更老的那条病灶（2026-10-09）不许回来：标题声称「有条款级依据」＝替库侧下结论
  assert.ok(!/有条款级依据/.test(md), '标题又在声称「有条款级依据」—— 那是替库侧下结论');
  // ★ 本次三处（Owner 逐条点名）
  assert.ok(!/## 一、知识库侧/.test(md), '「一、知识库侧」那个小标题还在（Owner 点名要去掉）');
  assert.ok(!/## 二、模型侧/.test(md), '「二、模型侧」那个小标题还在（Owner 点名要去掉）');
  assert.ok(!/本报告不作核验/.test(md), '那段 ⚠️ 免责还在');
  assert.ok(!/没有并进任何条目/.test(md), '「（本单知识库侧没有并进任何条目。）」还在');
  assert.ok(!/计数口径/.test(md), '「三、计数口径」还在（Owner：下面的内容都不需要）');
  assert.ok(!/^- 判据：/m.test(md), '「- 判据：PRD §5.3.4…」还在');
  assert.ok(!/^- 用户原提问：/m.test(md), '「- 用户原提问：…」还在（它已经挪进标题）');
  // ★★ 反向对照（**这一条最要紧**）：去掉的是**外层的标题与免责**，
  //   条目本身一条都不许少，且**逐条**仍要能看出是哪一侧给的
  //   （「这条回不回得了源」决定下一步，比那两个小标题重要得多）。
  // ★ 2026-10-13（Owner：「不要出现 知识库侧，模型侧」）：标记换成新措辞，
  //   判据跟着换；同时**反着钉一条** —— 那两个词一个都不许回来。
  assert.ok(/\*\*有库内条款依据\*\*/.test(md), '库侧条目丢了来源标记 —— 读者就看不出它回得了源');
  assert.ok(/\*\*无库内依据 · 建议转人工\*\*/.test(md), '无依据那条丢了来源标记 —— 会被当成有依据的');
  assert.ok(!/知识库侧|模型侧/.test(md), '「知识库侧/模型侧」又出现了（Owner 2026-10-13 点名去掉）');
  assert.ok(/1\.【平台与促销】/.test(md) && /2\.【合规】/.test(md),
    '两段合并后编号必须连号（各从 1 开始会被读成两份清单）');
});

await t('Z21b ★ 报告 H1 **固定**「内容审查报告」—— 文案/图片/视频一律（Owner 2026-10-13 第三次改这条）', async () => {
  // Owner 原话：「输出的文档报告标题太乱了，**直接按照原来的「内容审查报告」**」，
  // 并点名「**文案/图片/视频都需要改**」。
  // 上一版是 `<用户原问题> 内容审查报告`，坏在媒材单上 —— 那类消息没有「用户原问题」，
  // `question` 是内核自己拟的**探针**；探针识别漏了一种形状
  // （`【对方这条消息没带视频；下面是它引用的那条消息里附的视频…】`）⇒
  // 整段 3498 字进了 H1（Owner 贴回来的就是那个）。
  const M = await import('./agent/merged_report.mjs');
  const head = (q) => M.renderMergedReportMd({ merged: [], total: 1, state: 'REVIEW',
    line: '【审查结论：REVIEW】共发现 1 处需人工确认。',
    question: q, contentId: 'C', at: '2026-10-12T07:31:24.329Z' }).split('\n')[0];
  // ① **一律**就这一句 —— 文案 / 图片 / 视频三种都一样
  assert.strictEqual(head('这条社媒文案能不能发'), '# 内容审查报告');
  assert.strictEqual(head(''), '# 内容审查报告');
  assert.strictEqual(head(null), '# 内容审查报告');
  // ② **那个漏掉的探针形状**（Owner 贴回来的那一段）一个字符都不许进 H1
  const probe = '【对方这条消息没带视频；下面是它引用的那条消息里附的视频，共 1 段。'
    + '下面每一格是本机读出来的读数：「关键帧上的文字」是按时长均匀抽 8 帧做的 OCR…';
  assert.strictEqual(head(probe), '# 内容审查报告', '探针又被当成标题了');
  // ③ 反向对照：H1 里**不许**出现渲染时刻，也不许出现探针里的任何特征串
  assert.ok(!/2026-10-12T07:31:24/.test(head('x')), 'H1 里还有渲染时刻');
  for (const q of ['这条社媒文案能不能发', probe, '第一行\n第二行']) {
    assert.ok(head(q) === '# 内容审查报告', `H1 不是固定的那一句：${head(q)}`);
  }
  // ④ 探针识别本身也要对（它管的是**留底**里的素材读数附录，不只是标题）
  const { questionForReport } = M;
  assert.strictEqual(questionForReport(probe).isProbe, true, '新形状的探针没被认出来');
  assert.strictEqual(questionForReport('这条社媒文案能不能发').isProbe, false,
    '把真问题误判成探针了 —— 那会把素材读数当成人写的话');
});

await t('Z21c ★ 报告头只留 PRD 字段 ＋ **投出去那份不带附录、留底那份带**（Owner 2026-10-13 第四条）', async () => {
  // Owner 原话：「输出的飞书文档报告，去掉（`- 内容 ID：— ｜ 审查时刻：…` ／
  //   `- 结论：REVIEW ｜ 问题数量：10` ／ **附录下的所有内容**）」。
  //   实测那份报告：149 行里 79 行是附录（7892 字符），正文只占前 70 行。
  const M = await import('./agent/merged_report.mjs');
  const args = {
    merged: [{ location: '[00:04]', category: '合规', severity: 'REVIEW', source: 'model',
               reason: 'r', advice: 'a' }],
    total: 1, state: 'REVIEW', line: '【审查结论：REVIEW】共发现 1 处需人工确认。',
    question: '这条视频能过吗', contentId: '—', at: '2026-10-13T03:11:14.656Z',
    hitsBlock: '【库内命中（读数）】本次检索命中 5 条\n1. `#l.1-2`｜BM25 299.18',
    mediaAppendix: '### 关键帧文字与音轨转写\n\n- **视频 1**（68.9 秒）',
  };
  const doc = M.renderMergedReportMd({ ...args, withAppendix: false });
  const full = M.renderMergedReportMd(args);
  // ① 那两行都不许再出现
  assert.ok(!/^- 内容 ID：/m.test(doc), '「- 内容 ID：…」还在');
  assert.ok(!/^- 结论：/m.test(doc), '「- 结论：…」还在（它与下面的 §5.3 结论行是同一件事说两遍）');
  // ★ 反向对照：**结论与条数一条都没少** —— 它们就在结论行里（这就是那两行能去掉的前提）
  assert.ok(/【审查结论：REVIEW】共发现 1 处需人工确认。/.test(doc), '把结论也一起删了 —— 那这条改动就变成丢信息');
  // ② 投出去那份：一个附录节都不许有
  assert.ok(!/^## 附录/m.test(doc), '投出去的文档里还有附录节');
  assert.ok(!/库内命中（读数）/.test(doc), '投出去那份里还有检索读数');
  assert.ok(!/关键帧文字/.test(doc), '投出去那份里还有媒材读数全文');
  // ③ ★★ **搬不是砍**：留底那份必须**完整**（它是「这条依据怎么来的 / 当时读到什么字」的唯一落点）
  assert.ok(/^## 附录：检索读数/m.test(full), '留底那份丢了检索读数附录');
  assert.ok(/^## 附录：机读素材读数/m.test(full), '留底那份丢了媒材读数附录');
  assert.ok(/库内命中（读数）/.test(full) && /关键帧文字/.test(full), '留底那份的内容被截了');
  // ④ 两份的**条目必须逐字同源**（只差附录那一半）
  const bodyOf = (m) => m.split('\n').filter((l) => /^\d+\.【/.test(l)).join('\n');
  assert.strictEqual(bodyOf(doc), bodyOf(full), '两份的逐条清单不一致 —— 那就成了「两处各写一遍」');
});

await t('Z21d ★ 落盘：投出那份与留底那份**是两个文件**，且路径都从返回值给（不许猜）', async () => {
  const M = await import('./agent/merged_report.mjs');
  const os = await import('node:os');
  const fsx = await import('node:fs');
  const pathx = await import('node:path');
  const dir = fsx.mkdtempSync(pathx.join(os.tmpdir(), 'mr-'));
  const prev = process.env.SHOUHENG_MERGED_REPORT_DIR;
  process.env.SHOUHENG_MERGED_REPORT_DIR = dir;
  try {
    // ⚠️⚠️ **必须注入 `publishDoc`** —— 默认那一跳会真的去飞书建云文档。
    //   这不是假设：写这条自证的第一版就漏了它（§2.4.4 那个病，本仓已栽过两次）。
    const stubPub = async (p) => ({ ok: true, url: 'https://example.invalid/docx/Z21D', detail: `桩：${p}` });
    const pub = await M.publishMergedReport('# 投出\n\n正文', {
      contentId: 'C1', at: 'T', archiveMd: '# 留底\n\n## 附录：检索读数\n\n读数',
      publishDoc: stubPub,
    });
    assert.ok(pub.mdPath && fsx.existsSync(pub.mdPath), `投出那份没落盘：${JSON.stringify(pub).slice(0, 160)}`);
    assert.ok(pub.archivePath && fsx.existsSync(pub.archivePath), '留底那份没落盘');
    assert.ok(/\.full\.md$/.test(pub.archivePath), `留底文件名没带 .full.md：${pub.archivePath}`);
    assert.ok(!/## 附录/.test(fsx.readFileSync(pub.mdPath, 'utf8')), '投出那份带着附录');
    assert.ok(/## 附录/.test(fsx.readFileSync(pub.archivePath, 'utf8')), '留底那份没有附录');
    // 反向对照：**不给 archiveMd 就不写留底**（不留一个空壳文件）
    const pub2 = await M.publishMergedReport('# 投出2', { contentId: 'C2', archiveMd: null,
                                                         publishDoc: stubPub });
    assert.strictEqual(pub2.archivePath, null, '没给留底内容却写了留底文件');
  } finally {
    if (prev === undefined) delete process.env.SHOUHENG_MERGED_REPORT_DIR;
    else process.env.SHOUHENG_MERGED_REPORT_DIR = prev;
    fsx.rmSync(dir, { recursive: true, force: true });
  }
});

await t('Z22 有结构化告警时照搬进正文（缺口留着，但不能装作没有）', async () => {
  const M = await import('./agent/merged_report.mjs');
  const md = M.renderMergedReportMd({ merged: [], total: 0, state: 'REVIEW',
    warnings: ['卡片告警：4/4 条依据与素材无关；2 条 L0 sha 不一致'] });
  assert.ok(/4\/4 条依据与素材无关/.test(md), '传进来的告警没进正文');
});
// ═══ 第 30 组 · 「建议」的唯一产出者（Owner 2026-10-09）═══
//
// Owner 原话：「建议必须具体内容。负面样本『建议』列填充 47% ⇒ **有填的做参考，agent 输出
// 最终具体建议**；没填的不用参考，agent 直接出建议。」
//
// 过去「建议」有**两个产出者**（库侧原话 / 模型原话）⇒ 库侧有值时模型那条被静默丢掉，
// 来源也标不清。现在两侧都回来之后补一次调用，**唯一产出者**。

await t('Z23 ★ 有 advice 就用它，且标注说的是「**参考了什么**」而不是「谁给的」', async () => {
  const T = await import('./agent/dual_track.mjs');
  // ★ 2026-10-09：`建议` 标签如今**带加粗**（Owner 裁定「字段加粗保留」）⇒ 原先的
  //   `/ {3}建议：(.*)/` 抠出空串，把「建议内容对不对」误判成失败。
  //   这一组查的是**建议内容与标注**、与加粗无关 ⇒ 认两种写法。
  const sug = (f) => (T.renderMergedItem(f, 0, { must: false }).match(/ {3}\*{0,2}建议\*{0,2}：(.*)/) || [])[1] || '';
  const withRef = sug({ category: 'a', location: 'b', source: 'kb', reason: 'r',
                        advice: '删掉「最」字，改为「更」', adviceReferencedKb: true });
  assert.ok(/删掉「最」字/.test(withRef), '没采用 advice —— 唯一产出者没生效');
  assert.ok(/参考了库内反例的建议/.test(withRef), '没标「参考了什么」');
  assert.ok(/不是库规原文/.test(withRef), '改法由模型写的，必须说清它不是库规原文');
  const noRef = sug({ category: 'a', location: 'b', source: 'model', reason: 'r',
                      advice: '补一行截止日期', adviceReferencedKb: false });
  assert.ok(/库内无可参考建议/.test(noRef), '库里没填时要明说，不能含糊');
});

await t('Z24 ★ 反向对照：建议生成**失败**时回退（库侧原话 → 模型原话 → 如实说没有），不许编', async () => {
  const T = await import('./agent/dual_track.mjs');
  // ★ 2026-10-09：`建议` 标签如今**带加粗**（Owner 裁定「字段加粗保留」）⇒ 原先的
  //   `/ {3}建议：(.*)/` 抠出空串，把「建议内容对不对」误判成失败。
  //   这一组查的是**建议内容与标注**、与加粗无关 ⇒ 认两种写法。
  const sug = (f) => (T.renderMergedItem(f, 0, { must: false }).match(/ {3}\*{0,2}建议\*{0,2}：(.*)/) || [])[1] || '';
  // advice = null（生成失败）⇒ 回退到库侧原话
  assert.strictEqual(sug({ category: 'a', location: 'b', source: 'kb', reason: 'r', advice: null,
                           kb: { suggestionLine: '库侧原话：改成中文' } }), '库侧原话：改成中文');
  // 连库侧也没有 ⇒ 回退到模型原话
  assert.ok(/模型建议：改成中文/.test(sug({ category: 'a', location: 'b', source: 'model', reason: 'r',
                                           advice: null, suggestion: '模型建议：改成中文' })));
  // 全都没有 ⇒ 如实说没有（不许出现「转对应负责人复核」）
  const none = sug({ category: 'a', location: 'b', source: 'model', reason: 'r', advice: null });
  assert.ok(/两侧都没给修改建议/.test(none), '既没建议又没如实说');
  assert.ok(!/转对应负责人复核/.test(none), '硬编码那句又回来了');
});

await t('Z25 ★ 自证不许真打 LLM：每一处 runSubmissionGate 调用点都必须注入 adviceRunner', () => {
  // §2.4.4 那个病：跑一次自证，真的调了模型。实测漏一处就把套件拖到超时（7.5s/次）。
  const src = fs.readFileSync(new URL('./test_agent.mjs', import.meta.url), 'utf8');
  const lines = src.split('\n');
  const missing = [];
  for (let i = 0; i < lines.length; i++) {
    if (/runSubmissionGate\(\{\s*$/.test(lines[i])) {
      const seg = lines.slice(i + 1, i + 24).join('\n');
      if (!seg.includes('adviceRunner')) missing.push(i + 1);
    }
  }
  assert.deepStrictEqual(missing, [], `这些行上的闸门调用没注入 adviceRunner（会真打 LLM）：${missing.join(', ')}`);
});
await t('Z26 ★ 行为级：库侧条目走生成（参考库侧建议），**模型侧已有的建议直接沿用**', async () => {
  // Owner 的期望原话：「知识库侧 **参考库侧建议** → agent 出最终建议；**模型侧问题就输出模型侧建议**」。
  // 第一版把**所有**条目都送进生成器 ⇒ 模型侧已经写好的一条被重写（白烧一次、详略还可能变差）。
  const { runSubmissionGate } = await import('./agent/agent.mjs');
  const KB = ['【审查结论：REVIEW】共发现 1 处需人工确认。', '',
    '1.【平台与促销】图 1 第 3 行 —— 库侧那条', '  **建议**：删掉「最」字', '',
    '建议转 李倩怡 复核。'].join('\n');
  let sent = null;
  const g = await runSubmissionGate({
    inbound: { text: '审核下这张图', imageCount: 1, videoCount: 0 },
    question: '审核下这张图', notify: null,
    chainRunner: async () => ({ answer: KB, review: { state: 'REVIEW', issue_count: 1 } }),
    publishRunner: async () => ({ ok: true, record_id: 'r' }),
    modelSideRunner: async () => ({ ok: true, ms: 1, findings: [{ category: '本地化', location: '画面 1',
      severity: 'REVIEW', reason: '英文', suggestion: '模型侧自己写的：译成中文' }] }),
    adviceRunner: async ({ items }) => { sent = items;
      return { ok: true, ms: 5, advice: Object.fromEntries(items.map((_, i) => [i, '生成器给的改法 ' + i])) }; },
    mergedReportRunner: async () => ({ ok: true, url: null, detail: '桩' }),
  });
  // ★ 只送「需要生成」的那条（库侧有参考）；模型侧那条不许送（它自己写过）
  assert.strictEqual(sent?.length, 1, `送进生成器的条数应为 1，实际 ${sent?.length}`);
  assert.ok(/图 1 第 3 行/.test(String(sent?.[0]?.location ?? '')), '送进去的不是库侧那条');
  const block = String(g.verdict53?.block ?? '');
  const lines = block.split('\n').filter((l) => /^ {3}\*{0,2}建议\*{0,2}：/.test(l)).map((l) => l.trim());
  assert.strictEqual(lines.length, 2, `应有 2 条建议，实际 ${lines.length}`);
  // 库侧那条：走了生成器，并标「参考了库内反例的建议」
  assert.ok(lines.some((l) => /生成器给的改法/.test(l) && /参考了库内反例的建议/.test(l)),
    '库侧条目没走生成或没标参考：' + JSON.stringify(lines));
  // ★ 模型侧那条：**沿用原话**，且标注是「模型侧给的改法」
  // ★ 2026-10-13：标注措辞改了（不再出现「模型侧」），判据跟着换 —— 查的还是同一件事。
  assert.ok(lines.some((l) => /模型侧自己写的：译成中文/.test(l) && /无库内依据的改法建议/.test(l)),
    '模型侧条目被重写了（应当沿用）：' + JSON.stringify(lines));
  assert.ok(!lines.some((l) => /生成器给的改法/.test(l) && /无库内依据的改法建议/.test(l)),
    '模型侧条目被送进生成器了 —— 与 Owner 的期望不符');
});
// ═══ 第 31 组 · ≥3 时卡片**只出分类汇总 + 报告链接**（PRD §5.3.3，Owner 追问第四次）═══
//
// PRD 权威实现（库侧 `kb/l5/p0_fastpath.py:391`）：
//   `if n >= 3:` → `L.extend(_summary_lines(findings))` + 报告链接。
//
// 而本仓的 `renderMerged` **从来不分条数**，永远把全部条目平铺在卡上 ——
// Owner 看到的「7 个问题都是平铺」**本身就违反 PRD**，而「链接看不见」只是症状
// （条目全在卡上，链接被挤到最后又被收起）。此前三次修复都在治症状。

await t('Z27 ★ 行为级：≥3 ⇒ 只出分类汇总 + 链接（**零条逐条**）；<3 ⇒ 逐条平铺', async () => {
  const T = await import('./agent/dual_track.mjs');
  const mk = (n) => Array.from({ length: n }, (_, i) => ({ location: `画面 ${i}`,
    category: i % 2 ? '本地化' : '平台与促销', severity: 'REVIEW', source: 'model',
    reason: 'x', advice: `改法 ${i}` }));
  const build = (n, url) => {
    const m = T.mergeFindings([], mk(n));
    return T.renderMerged(m.items, { state: 'REVIEW',
      kb: T.kbSideOf({ review: { state: 'REVIEW', issue_count: 0 } }),
      kbTextCount: 0, model: { ok: true, findings: [] }, reportUrlOverride: url });
  };
  const big = build(7, 'https://momcozy-in.feishu.cn/docx/BIG');
  const b7 = String(big.block);
  assert.strictEqual(big.total, 7);
  assert.strictEqual(big.summarized, true, 'total=7 应当走汇总');
  assert.strictEqual((b7.match(/^ *\*{0,2}判定\*{0,2}：/gm) || []).length, 0,
    '≥3 时**不许**在卡上逐条平铺（这正是 Owner 反复看到的那件事）');
  assert.ok(/· .*类问题：\d+ 个/.test(b7), '缺 PRD 要的分类汇总行');
  assert.ok(/查看完整问题清单与修改建议/.test(b7), '缺报告链接');
  // ★★ 2026-10-13（Owner 裁定）：卡上**不再**有「（问题数 N ≥ 3 ⇒ 按 PRD §5.3.3 只出分类汇总…）」
  //   那句页脚 —— 它讲的是我们的口径规矩，业务同事读不懂，Owner 把它列进了「都去掉」。
  //   ⚠️ 判据**反过来钉**：卡上不许有 ＋ **查证笔记里必须有**（搬不是砍，
  //      对方追问「逐条清单去哪了」守衡要答得出来）。
  assert.ok(!/只出分类汇总/.test(b7), '那句口径页脚又回到卡上了（Owner 2026-10-13 点名去掉）');
  assert.ok(/只出分类汇总/.test(String(big.internalNotes)),
    '从卡上撤下来的页脚必须落在 internalNotes 里（搬不是砍）');
  // ★ 反向对照：<3 时必须**照旧逐条平铺**（1–2 条走逐条输出，PRD 就是这么定的）
  const small = build(2, null);
  const b2 = String(small.block);
  assert.strictEqual(small.summarized, false, 'total=2 不该走汇总');
  assert.strictEqual((b2.match(/^ *\*{0,2}判定\*{0,2}：/gm) || []).length, 2, '<3 时必须逐条平铺');
  assert.ok(!/查看完整问题清单/.test(b2), '<3 时不许给链接');
  // 边界：正好 3 条 ⇒ 走汇总（`>=`，与库侧同一个常数）
  // ⚠️ 2026-10-09 晚：这条原先传 null，而安全网（Z31）要求「拿不到链接就退回平铺」
  //   ⇒ 3 条要验「闭区间走汇总」就必须**带上链接**（否则它按安全网退回平铺，是对的）。
  assert.strictEqual(build(3, 'https://momcozy-in.feishu.cn/docx/C3').summarized, true,
    '3 条是闭区间（>=），带链接时必须走汇总');
});

await t('Z28 接线：汇总那一段必须与报告链接**同时出现**（少一个都等于没修）', async () => {
  const T = await import('./agent/dual_track.mjs');
  const m = T.mergeFindings([], Array.from({ length: 5 }, (_, i) => ({ location: `p${i}`,
    category: '合规', severity: 'REVIEW', source: 'model', reason: 'r', advice: 'a' })));
  const withUrl = T.renderMerged(m.items, { state: 'REVIEW',
    kb: T.kbSideOf({ review: { state: 'REVIEW', issue_count: 0 } }), kbTextCount: 0,
    model: { ok: true, findings: [] }, reportUrlOverride: 'https://x/docx/Y' });
  assert.ok(/· 合规类问题：5 个/.test(String(withUrl.block)), '汇总没出');
  assert.ok(/https:\/\/x\/docx\/Y/.test(String(withUrl.block)), '链接没出');
});
// ═══ 第 32 组 · 截断要如实报成截断，且要重试（Owner 那张夜间图的真因）═══
//
// 实测日志：`⚖ 双轨｜模型侧 没跑成：输出里没有 JSON 数组｜raw=1545 字｜
//           raw 首 100 字="[\n {\n \"location\": …`
// **它明明有数组开头** —— 判据却报「没有 JSON 数组」。真因是**输出被腰斩**（额度用尽）。
// 报错指向错误的方向，查的人就永远查不到真因。与 `raw=0` 那个坑同一个形状。

await t('Z29 ★ 三种坏输出必须分得开（不许把「截断」报成「没写数组」）', async () => {
  const M = await import('./agent/model_side.mjs');
  const A = await import('./agent/advice.mjs');
  // ① 真的没写数组（散文）
  assert.match(M.parseFindings('我读了图，有 3 个问题').error, /没有 JSON 数组/);
  assert.match(A.parseAdvice('写的散文').error, /没有 JSON 数组/);
  // ② 截断：**有 `[` 没有 `]`** ⇒ 必须说「被截断」，且带上 raw 长度
  const cut = M.parseFindings('[{"location":"图1","category":"本地化","severity":"REVIEW","reason":"x"');
  assert.match(cut.error, /被截断/, '截断被报成了别的 —— 这正是那张夜间图的真因');
  assert.match(cut.error, /raw=\d+ 字/, '截断必须带上 raw 长度，否则查不出是额度问题');
  assert.ok(!/没有 JSON 数组/.test(cut.error), '又把截断报成「没有数组」了');
  assert.match(A.parseAdvice('[{"i":0,"advice":"改').error, /被截断/);
  // ③ JSON 语法错 ⇒ 第三种，与前两种都不同
  assert.match(M.parseFindings('[{"a":}]').error, /JSON 解析失败/);
});

await t('Z30 ★ 截断/0 字要**重试一次**（额度翻倍），散文不重试（不该白烧）', async () => {
  const M = await import('./agent/model_side.mjs');
  const A = await import('./agent/advice.mjs');
  const OK = '[{"location":"图1","category":"本地化","severity":"REVIEW","reason":"x","suggestion":"译成中文"}]';
  // 模型侧：第一次截断 ⇒ 重试一次并成功
  let n1 = 0; const toks = [];
  const r1 = await M.reviewModelSide({ readings: 'OCR 有字', question: 'q',
    ask: async (p, o) => { n1++; toks.push(o.maxTokens); return n1 === 1 ? '[{"x":' : OK; } });
  assert.strictEqual(n1, 2, `截断时必须重试一次，实际调了 ${n1} 次`);
  assert.ok(toks[1] > toks[0], '重试必须提高额度');
  assert.strictEqual(r1.ok, true, '重试后应当成功');
  // 建议生成：第一次 0 字 ⇒ 重试一次并成功
  let n2 = 0;
  const r2 = await A.generateAdvice({ items: [{ location: 'p', category: 'c', reason: 'r' }],
    ask: async () => { n2++; return n2 === 1 ? '' : '[{"i":0,"advice":"改成中文"}]'; } });
  assert.strictEqual(n2, 2, '0 字时必须重试一次');
  assert.strictEqual(r2.ok, true, '重试后应当成功');
  assert.strictEqual(r2.advice[0], '改成中文');
  // ★ 反向对照：**散文不重试** —— 重试也没用，那是提示词问题，不该白烧一次额度
  let n3 = 0;
  await M.reviewModelSide({ readings: 'OCR 有字', question: 'q',
    ask: async () => { n3++; return '我读到了 3 个问题，分别是……'; } });
  assert.strictEqual(n3, 1, `散文不该重试（白烧额度），实际调了 ${n3} 次`);
});
await t('Z31 ★ 安全网：≥3 但**拿不到报告链接** ⇒ 必须退回逐条平铺（宁可长，不可空）', async () => {
  // 为什么这条必须独立存在：≥3 时卡上只剩汇总行，而**汇总行不含任何可执行内容**。
  // 报告没建成时若仍走汇总，读者拿到的是「合规类问题：7 个」+ 空链接 ——
  // 比改动之前（至少还有 7 条逐条）**更没法用**。实测那一单就是既没建报告、卡上也没链接。
  const T = await import('./agent/dual_track.mjs');
  const mk = (n) => Array.from({ length: n }, (_, i) => ({ location: `p${i}`, category: '合规',
    severity: 'REVIEW', source: 'model', reason: 'x', advice: `a${i}` }));
  const run = (n, url) => { const m = T.mergeFindings([], mk(n));
    return T.renderMerged(m.items, { state: 'REVIEW',
      kb: T.kbSideOf({ review: { state: 'REVIEW', issue_count: 0 } }), kbTextCount: 0,
      model: { ok: true, findings: [] }, reportUrlOverride: url }); };
  const hasLink = run(7, 'https://momcozy-in.feishu.cn/docx/X');
  assert.strictEqual(hasLink.summarized, true);
  assert.strictEqual((String(hasLink.block).match(/^ *\*{0,2}判定\*{0,2}：/gm) || []).length, 0);
  const noLink = run(7, null);
  assert.strictEqual(noLink.summarized, false, '拿不到链接还走汇总 —— 卡片会只剩一行汇总、什么都做不了');
  assert.strictEqual((String(noLink.block).match(/^ *\*{0,2}判定\*{0,2}：/gm) || []).length, 7,
    '拿不到链接时**必须**把 7 条逐条放回卡上');
});
await t('Z32 ★★ 库侧的真文档在 publish.docx 里，不在 report_url —— 不读它就永远平铺', async () => {
  // 真因（Owner「8 条还在平铺」）：旁挂里**两个字段指的是两样东西**：
  //   report_url   = 'kb/l7/reports/20261009-125549.review.md'          ← 本地路径，人点不开
  //   publish.docx = 'https://momcozy-in.feishu.cn/docx/MQsxdnFPjoFEzPx5BCtcJyFunyf'  ← 真文档
  // 我们只读前者 ⇒ 以为「库侧给了链接」⇒ 跳过自己建；而分流判据要求可点的 http ⇒ 退回平铺。
  const T = await import('./agent/dual_track.mjs');
  const DOCX = 'https://momcozy-in.feishu.cn/docx/MQsxdnFPjoFEzPx5BCtcJyFunyf';
  const LOCAL = 'kb/l7/reports/20261009-125549.review.md';
  const mk = (n) => Array.from({ length: n }, (_, i) => ({ location: `p${i}`, category: '合规',
    severity: 'REVIEW', source: 'model', reason: 'x', advice: `a${i}` }));
  const m = T.mergeFindings([], mk(8));
  const render = (side) => T.renderMerged(m.items, { state: 'REVIEW', kb: side, kbTextCount: 0,
    model: { ok: true, findings: [] } });
  // ① 有 publish.docx ⇒ reportUrl 必须取它（不是那个本地路径）
  const withDocx = T.kbSideOf({ review: { state: 'REVIEW', issue_count: 5,
    report_url: LOCAL, publish: { published: true, docx: DOCX } } });
  assert.strictEqual(withDocx.reportUrl, DOCX, '没优先取 publish.docx —— 拿到的还是那个点不开的本地路径');
  const r1 = render(withDocx);
  assert.strictEqual(r1.summarized, true, '有真文档却没走汇总');
  assert.strictEqual((String(r1.block).match(/^ *\*{0,2}判定\*{0,2}：/gm) || []).length, 0, '≥3 且有真链接时不许平铺');
  assert.ok(String(r1.block).includes(DOCX), '卡里没印出那个文档链接');
  // ② 反向对照：**只有本地路径** ⇒ 仍然不许把它当链接，必须退回平铺（人点不开的东西不算链接）
  const onlyLocal = T.kbSideOf({ review: { state: 'REVIEW', issue_count: 5, report_url: LOCAL } });
  const r2 = render(onlyLocal);
  assert.strictEqual(r2.summarized, false, '只有本地路径却走了汇总 —— 卡上会只剩一行汇总、点不开');
  assert.strictEqual((String(r2.block).match(/^ *\*{0,2}判定\*{0,2}：/gm) || []).length, 8, '退回平铺时 8 条必须都在');
});

// ══════════════════════════════════════════════════════════════════════════════
// Z34 ★（2026-10-09，Owner 裁定「2 先于 1」）**库侧有链接时，也必须用本仓那份**
// ══════════════════════════════════════════════════════════════════════════════
//   Owner 的疑问：「发文案给守衡输出的报告格式是对的，发图片和视频就不对了？」
//
//   查清后的成因（反直觉）：那一行 `&& !kbSide?.reportUrl` 让两条路**互斥** ——
//     · 文案单：库侧自己 **1 条（<3）** ⇒ 库侧不建 docx ⇒ 空 ⇒ 本仓建 ⇒ **卡上链接对**；
//     · 图片/视频单：库侧自己 **5 条（≥3）** ⇒ 库侧建了 docx ⇒ 有值 ⇒ **本仓被跳过**
//       ⇒ 卡上链接指向**库侧那份**（只装库侧条目、条目数对不上卡、还把库内案例渲染成「命中」）。
//   ⇒ 口径：**只要卡内 ≥3，就用本仓那份**。库侧那份降为"库侧自己留的档"。
//
//   这一组是那个裁定的**护栏**：拆掉 `!kbSide?.reportUrl` 这个改动，Z34a 必须变红。
{
  const { runSubmissionGate } = await import('./agent/agent.mjs');
  const KBURL = 'https://momcozy-in.feishu.cn/docx/KBSIDE5';   // 库侧自己那份（5 条 ≥3）
  const MERGED = 'https://momcozy-in.feishu.cn/docx/MERGED7';  // 本仓合并那份（卡内 7）
  const KBANS = ['【审查结论：REVIEW】共发现 5 处需人工确认。', '',
    '· 品牌一致性类问题：3 个', '', '建议转 @内容治理负责人 复核。'].join('\n');
  const mkGate = async (runner) => runSubmissionGate({
    adviceRunner: async ({ items }) => ({ ok: true, ms: 1,
      advice: Object.fromEntries((items || []).map((_, i) => [i, `改法 ${i}`])) }),
    inbound: { text: '审一下这张图', imageCount: 1, videoCount: 0 },
    question: '审一下这张图', notify: null,
    // ★ 库侧**给了**链接 —— 这就是图片/视频单的形状（原先在这里被跳过）
    chainRunner: async () => ({ answer: KBANS, review: { state: 'REVIEW', issue_count: 5,
      publish: { published: true, docx: KBURL, record_id: 'recX' },
      report_url: KBURL, report_url_kind: 'feishu_docx' } }),
    publishRunner: async () => ({ ok: true, record_id: 'recX' }),
    modelSideRunner: async () => ({ ok: true, ms: 1,
      findings: [1, 2].map((n) => ({ category: '本地化', location: `画面 ${n}`,
        severity: 'REVIEW', reason: 'x' })) }),
    mergedReportRunner: runner,
  });

  await t('Z34a ★ 库侧有链接时，本仓**仍要**建合并报告，且卡上用它', async () => {
    let called = 0;
    const g = await mkGate(async () => { called++; return { ok: true, url: MERGED, detail: '桩' }; });
    assert.strictEqual(called, 1, '库侧有链接就把本仓这一跳跳过了 —— Owner 的裁定没落地');
    const blk = String(g.verdict53?.block ?? '');
    assert.ok(blk.includes(MERGED), `卡上不是本仓那份：${(blk.match(/docx\/\w+/) || ['(无)'])[0]}`);
    assert.ok(!blk.includes('KBSIDE5'), '卡上还留着库侧那份的链接（两份文档会打架）');
  });

  await t('Z34b 反向对照：本仓建失败 ⇒ 回落库侧那份（有链接好过没链接）', async () => {
    const g = await mkGate(async () => ({ ok: false, url: null, detail: '建失败：桩' }));
    const blk = String(g.verdict53?.block ?? '');
    assert.ok(blk.includes('KBSIDE5'), '建失败时没有回落库侧链接 —— 卡上会变成没有链接');
  });
}

// ══════════════════════════════════════════════════════════════════════════════
// Z35 ★（2026-10-09）**报告正文里的库内原始 HTML 必须转义，否则整份文档被飞书拒收**
// ══════════════════════════════════════════════════════════════════════════════
//   Owner 的问题：「文案是合并报告，图片/视频现在是合并报告吗？这 3 个要改成一致的」。
//
//   查出来的真因**不是** fix #2 没生效，而是**合并报告建了但发不出去**：
//     建云文档失败：invalid <img> local resource tag:
//     XML syntax error on line 1: invalid character entity &#39 (no semicolon)
//
//   库内记录的 `excerpt` **含原始 HTML**（实测那条视频单的命中原文是
//   `>修改字幕</li></ol><img name="image.png" alt="…">` 与 `<table><colgroup>…`）。
//   飞书 `docs +create` 把 markdown 里的 `<…>` **当 HTML 解析** ⇒ 撞坏实体 ⇒ **整份被拒**。
//   为什么"发文案对、发图/视频不对"：文案单命中是纯文本（不含 `<`），图/视频单命中富文本。
//
//   实测（2026-10-09）：那份 12,877 字节的真实报告原样发 `ok:false`；
//   **只**把 `<` `>` 转义后 `ok:true`，且结构一字未损（标题 1 / 二级 4 / 加粗 166 前后一致）。
{
  const { mdBodySafe, mdTextSafe } = await import('./agent/merged_report.mjs');

  await t('Z35a 跨行 HTML 标签所在的行必须整行转义（第一版只认单行标签 ⇒ 漏）', async () => {
    const src = ['# 报告', '', '   命中原文（逐字）：<img name="image.png"',
      ' alt="图片展示了一位女性在厨房">', '', '**加粗**照旧'].join('\n');
    const out = mdBodySafe(src);
    assert.ok(!/<\/?[A-Za-z]/.test(out), `仍有裸标签：${out.slice(0, 120)}`);
    assert.ok(out.includes('&lt;img'), '没转义成实体');
    // ⚠️ 反向对照：**正常 markdown 一个字符都不许动**
    assert.ok(out.startsWith('# 报告'), '标题被改坏');
    assert.ok(out.includes('**加粗**照旧'), '加粗被改坏');
  });

  await t('Z35b 没有 HTML 的正文必须逐字不变（防"顺手全转义"）', async () => {
    const src = ['# 内容审查报告', '', '- 结论：**REVIEW** ｜ 问题数量：**3**',
      '', '| 分类 | 条数 |', '|-|-|', '| 合规 | 1 |', '',
      '1.【本地化】整句', '   **原因**：未标市场', '   **依据**：无库内依据'].join('\n');
    assert.strictEqual(mdBodySafe(src), src, '正常 markdown 被改动了 —— 报告会变丑');
  });

  await t('Z35c 反向对照：**裸实体单独出现不会导致拒收** ⇒ 不许顺手把它也转义', async () => {
    // 实测（2026-10-09）：只含 `&#39;` 的文档飞书照收（`ok:true`）；那个报错是
    // **在 `<img …>` 标签内部**才冒出来的，而标签行已被 Z35a 那条覆盖。
    // 所以这里钉的是「**别过度防守**」：`&#39` 是正常文本，改了就把原文改样了。
    const src = '行内有 &#39 这种裸实体，以及 &#x27 另一种。';
    assert.strictEqual(mdBodySafe(src), src, '把裸实体也转义了 —— 那是过度防守，且改动了原文');
  });

  await t('Z35d 命中原文注入点：hitsBlock 进报告前必须转义', async () => {
    const { renderMergedReportMd } = await import('./agent/merged_report.mjs');
    const md = renderMergedReportMd({
      merged: [], total: 3, state: 'REVIEW', line: '【审查结论：REVIEW】共发现 3 处需人工确认。',
      hitsBlock: '**库内命中（读数）**\n\n1. `#a`｜BM25 1｜internal_sample\n'
        + '   命中原文（逐字）：<table><tr><td>x</td></tr></table>\n   直链：—',
      question: 'q', contentId: 'c', at: 'T', kbGap: 0, kbTextCount: 0, modelCount: 0,
    });
    assert.ok(!/<table>/.test(md), 'hitsBlock 里的 HTML 没转义 ⇒ 这份文档发不出去');
    assert.ok(md.includes('&lt;table&gt;'), '没有转义成实体');
  });
}
// ★★ 2026-10-09 修（**静默空转**，比红更坏）：
//   这里原先有**两块**一模一样的「汇总 + `process.exit`」，而它们**后面还有测试**
//   —— 另一会话追加的「第 27 组」与本次追加的「第 33 组」全在 `exit` 之后，
//   **一次都没跑过**，而上面那行「合计」照样打印得像全绿（数字只统计到 exit 那一刻）。
//   这正是 `AGENTS.md` §2.4 那个病的又一处：**判据写好了，但没有一行代码会执行它**。
//   ⇒ 汇总与退出**只保留文件最后一份**（见文件末尾），中间不许再有。

// ═══ 第 27 组 · 「问题数 ≥3 ⇒ 飞书文档要带报告」（Owner 2026-10-09）═══
//
// Owner 的原话：「我的目标是让守衡输出的问题数量按照 PRD 等于或大于 3 个问题时，
// **写入的飞书文档要带报告**」。
//
// 病灶：报告**只有库侧会建**，而它的门槛读的是**它自己的** `issue_count`。
// 实测 2026-10-09 09:35 那张图：卡上说 6 处（库侧 1 ＋ 模型侧 5），而旁挂 `issue_count = 1`
// ⇒ 库侧不建 docx ⇒ `report_url = null` ⇒ **按 PRD 该给报告，却没有任何链接可给**。
// 现在改由**本仓**建：门槛读**卡里那个数**（`rendered.total`），正文含两侧全部条目。
//
// ⚠ 这一组**用桩**（`mergedReportRunner`）—— 真调会在 Owner 的飞书里建一份云文档。
//   写这一组时就因为忘了注入，跑一次自证真建了一份（§2.4.4 那个病，已修）。

await t('Z15 ★ 行为级：问题数 ≥3 且库侧没给链接 ⇒ 本仓建报告，卡里那一行是**真链接**', async () => {
  const { runSubmissionGate } = await import('./agent/agent.mjs');
  const KB_ANSWER = ['【审查结论：REVIEW】共发现 1 处需人工确认。', '',
    '1.【本地化】图 1', '', '建议转 李倩怡 复核。'].join('\n');
  const STUB = 'https://example.invalid/docx/Z15';
  let called = 0;
  const g = await runSubmissionGate({
    // ★ 2026-10-09：**建议生成必须注入** —— 它默认真打 LLM（漏一处就把套件拖到超时，实测 7.5s/次）
    adviceRunner: async ({ items }) => ({ ok: true, ms: 1,
      advice: Object.fromEntries((items || []).map((_, i) => [i, `自证桩给的改法 ${i}`])) }),
    inbound: { text: '审核下这张图', imageCount: 1, videoCount: 0 },
    question: '审核下这张图', notify: null,
    chainRunner: async () => ({ answer: KB_ANSWER, review: { state: 'REVIEW', issue_count: 1 } }),
    publishRunner: async () => ({ ok: true, record_id: 'recX' }),
    modelSideRunner: async () => ({ ok: true, ms: 1,
      findings: [1, 2, 3, 4, 5].map((n) => ({ category: '本地化', location: `画面 ${n}`, severity: 'REVIEW', reason: 'x' })) }),
    mergedReportRunner: async (md) => {
      called++;
      // 报告正文必须**两侧条目都在**（Owner：「6 个就展示 6 个问题」）。
      // ★ 2026-10-13：两侧**不再各有一个小标题**（Owner 把它们连免责一起列进了「废话」），
      //   所以判据从「有没有那两个标题」改成「**条目在不在、来源标没标**」——
      //   后者才是「这条回不回得了源」，也是那两个标题原先承担的**唯一**信息。
      // ★ 2026-10-13（Owner：「不要出现 知识库侧，模型侧」）：标记改了措辞，
      //   判据跟着改成**新措辞**（去的是词，不是「回不回得了源」这条信息）。
      assert.ok(/\*\*有库内条款依据\*\*/.test(md), '报告缺「有库内条款依据」那条（来源标记没了）');
      assert.ok(/\*\*无库内依据 · 建议转人工\*\*/.test(md), '报告缺「无库内依据」那条（来源标记没了）');
      assert.ok(!/知识库侧|模型侧/.test(md), '「知识库侧/模型侧」又出现了（Owner 点名去掉）');
      assert.ok(!/## 一、知识库侧|## 二、模型侧/.test(md), '两个来源小标题又回来了（Owner 点名去掉）');
      // ★ 2026-10-09：`判定` 如今**带加粗**（Owner 裁定「字段加粗保留」）且**排在 PRD 四要素之后**
      //   ⇒ 原先的 `^ {3}判定：`（非加粗）在这里数出 0 条，把「量条目数」误判成失败。
      //   这一处查的是**条数**、与加粗无关，所以认两种写法（`\*{0,2}`），
      //   避免下次再因排版改动而误红。
      const n = (md.match(/^ {3}\*{0,2}判定\*{0,2}：/gm) || []).length;
      assert.strictEqual(n, 6, `报告里应有 6 条（两侧合计），实际 ${n} 条`);
      assert.ok(md.startsWith('# '), '报告首行必须是 H1（lark-cli markdown 导入的硬要求）');
      return { ok: true, url: STUB, detail: '自证桩' };
    },
  });
  assert.strictEqual(called, 1, '≥3 时没去建报告 —— Owner 的目标没达到');
  const blk = String(g.verdict53?.block ?? '');
  assert.ok(blk.includes(STUB), `卡里那一行不是真链接：${(blk.match(/→ 查看完整问题清单[^\n]*/) || ['(那一行都没有)'])[0].slice(0, 120)}`);
  assert.strictEqual(g.verdict53?.from, 'dual-track-merged', '抬头没走双轨合并那一支');
});

await t('Z16 ★ 反向对照：建报告**失败**时不许说成已出报告，且**不许阻断结论**', async () => {
  const { runSubmissionGate } = await import('./agent/agent.mjs');
  const KB_ANSWER = ['【审查结论：REVIEW】共发现 1 处需人工确认。', '',
    '1.【本地化】图 1', '', '建议转 李倩怡 复核。'].join('\n');
  const g = await runSubmissionGate({
    // ★ 2026-10-09：**建议生成必须注入** —— 它默认真打 LLM（漏一处就把套件拖到超时，实测 7.5s/次）
    adviceRunner: async ({ items }) => ({ ok: true, ms: 1,
      advice: Object.fromEntries((items || []).map((_, i) => [i, `自证桩给的改法 ${i}`])) }),
    inbound: { text: '审核下这张图', imageCount: 1, videoCount: 0 },
    question: '审核下这张图', notify: null,
    chainRunner: async () => ({ answer: KB_ANSWER, review: { state: 'REVIEW', issue_count: 1 } }),
    publishRunner: async () => ({ ok: true, record_id: 'recX' }),
    modelSideRunner: async () => ({ ok: true, ms: 1,
      findings: [1, 2, 3, 4, 5].map((n) => ({ category: '本地化', location: `画面 ${n}`, severity: 'REVIEW', reason: 'x' })) }),
    mergedReportRunner: async () => ({ ok: false, url: null, detail: '建云文档失败：权限不足' }),
  });
  // 结论照样要出来（报告与三态是两件事）
  assert.ok(/共发现 6 处/.test(g.verdict53?.line ?? ''), `结论被报告失败带崩了：${g.verdict53?.line}`);
  const blk = String(g.verdict53?.block ?? '');
  assert.ok(/查看完整问题清单/.test(blk), '连那一行都没了 —— 拿不到也要出声');
  assert.ok(/本次未拿到报告链接/.test(blk), '建失败却没说清 —— 会让人以为没有报告这回事');
  assert.ok(!/momcozy-in\.feishu\.cn/.test(blk), '建失败却编了一个飞书链接');
});

await t('Z17 ★ 接线：建报告那一步**必须可注入**，且默认走本仓的 publishReportDoc', () => {
  const src = fs.readFileSync(new URL('./agent/agent.mjs', import.meta.url), 'utf8');
  assert.ok(/mergedReportRunner\s*=\s*publishMergedReport/.test(src),
    '闸门没有可注入的 mergedReportRunner —— 自证会真的往飞书建文档（§2.4.4）');
  // ★ 2026-10-13：变量名从 `md` 改成 `mdDoc`（报告现在渲染**两份**：投出的这份 ＋ 留底那份），
  //   判据跟着认新名字 —— 它查的是「走没走注入的那个 runner」，与变量叫什么无关。
  assert.ok(/await mergedReportRunner\(md(Doc|Full)?,/.test(src), '接线里没走注入的那个 runner');
  // ★ 反向对照：**不许**绕过注入点去直接调真函数 —— 那会让上面两条恒真
  assert.ok(!/await publishMergedReport\(md/.test(src),
    '接线里直接调了真函数 —— 注入点形同虚设，自证又会建真文档');
  // 门槛必须读**卡里那个数**，不是「并进来几条」
  assert.ok(/rendered0\.total >= REPORT_LINK_MIN_ISSUES/.test(src),
    '门槛没读 `rendered0.total` —— 会退回「并进来几条」，把库侧未并进的那部分丢掉');
});

// ════════════════════════════════════════════════════════════════════════════
// 第 33 组 · **落表读数必须交到模型手上**（2026-10-09）
//
// 真事故（Owner 拿着截图来问的那张卡）：一条图片评审，链停在 **L6 闸门红**
// （`layer_gate_red`／退出码 4）。闸门**照规矩落了表**（`recvxwCWhwCO68`，14:11:57
// update，状态=待审、结论=NEEDS_INPUT），32 秒后发出去的 alert 卡上却写着：
//
//   「**对你有什么影响**：这条素材现在没有结论……**飞书表也没落这一行（拒答档）**。」
//
// —— 与盘上事实相反（`PMO/logs/lark_writes.jsonl` 06:11:57 那条就是这一行）。
// 根因不在模型：`chainBlock`（它唯一看得到的读数）在**链返回时**就定稿了，
// 而落表发生在**那之后**（`runSubmissionGate` 6.0 段）⇒ 读数是空的，模型就用猜的填
// （`AGENTS.md` §2.4.1）。所以修法不是改措辞，是**把读数交出去**：
// 判据（`publishFactBlock`）＋ 接线（拼进 `chainBlock` 再 `buildUserTurn`）＋ 反向对照。
// ────────────────────────────────────────────────────────────────────────────
console.log('\n═══ 33. 落表读数（卡片不许自称「没落表」）═══');

await t('V1 落了表：读数必须带**行号**，并且明写「不许说没有这一行」', async () => {
  const g = await import('./agent/review_gate.mjs');
  const b = g.publishFactBlock({ ok: true, action: 'updated', record_id: 'recvxwCWhwCO68', readback: 'consistent' },
    { conclusion: 'NEEDS_INPUT', status: '待审' });
  assert.ok(b.includes('recvxwCWhwCO68'), `行号没进读数：${b}`);
  assert.ok(b.includes('NEEDS_INPUT') && b.includes('待审'), `结论/状态没进读数：${b}`);
  assert.ok(b.includes('consistent'), `回读读数没进：${b}`);
  assert.ok(/不许.*表里没有这一行/.test(b), '没写明「不许说表里没有这一行」—— 那句话正是事故原话');
  assert.ok(/只许照抄/.test(b), '没写明读数只许照抄');
  // 新建与更新要长得出来（`action` 不许被吞掉，否则人看不出这是新行还是补写）
  const c = g.publishFactBlock({ ok: true, action: 'created', record_id: 'recvNEW' });
  assert.ok(/新建/.test(c) && !/更新/.test(c), `created 被写成了别的动作：${c}`);
});

await t('V2 没落成：**被熔断关掉**与**真失败**必须长得不一样，且都要明说表里没有行', async () => {
  const g = await import('./agent/review_gate.mjs');
  const skipped = g.publishFactBlock({ ok: false, action: 'skipped', detail: '落表被 SHOUHENG_REVIEW_TABLE=off 关掉了' });
  const failed = g.publishFactBlock({ ok: false, action: 'updated', detail: '回读失败：列表读不到' });
  assert.ok(!skipped.includes('失败'), `熔断（故意的）被写成了「失败」：${skipped}`);
  assert.ok(/没有执行/.test(skipped), `熔断必须写成「这一步没有执行」：${skipped}`);
  assert.ok(/失败/.test(failed) && /列表读不到/.test(failed), `真失败没带原因：${failed}`);
  for (const [name, b] of [['skipped', skipped], ['failed', failed]]) {
    assert.ok(/没有行/.test(b), `${name} 没明说表里没有这一行 ⇒ 人不知道要去补`);
    assert.ok(!/已(新建|更新)/.test(b), `${name} 里出现了「已新建/已更新」—— 自相矛盾`);
  }
  // 反向对照：**没有读数**时不许说「表里没有」（那是把「我不知道」说成了「没有」）
  const nul = g.publishFactBlock(null);
  assert.ok(/没有落表读数/.test(nul), `null 读数没写清楚：${nul}`);
  assert.ok(!/没有行/.test(nul), 'null 读数被说成了「表里没有行」—— 「不知道」被说成了「没有」');
  assert.ok(/一个字都不许提表/.test(nul), 'null 读数时没禁止模型谈表 ⇒ 它只能猜');
});

await t('V3 ★ 行为级：链在层闸门红处停下时，模型拿到的读数里**必须**有那一行行号', async () => {
  const { runSubmissionGate } = await import('./agent/agent.mjs');
  // 事故那一单的复核形状：链「跑成」但库侧拒答；闸门照样落表（返回真行号）。
  const g = await runSubmissionGate({
    inbound: { text: '审核下这张图', imageCount: 1, videoCount: 0 },
    question: '审核下这张图', notify: null,
    chainRunner: async () => ({ answer: '结论：NEEDS_INPUT。某层闸门红（layer_gate_red），退出码 4。' }),
    publishRunner: async () => ({ ok: true, action: 'updated', record_id: 'recvxwCWhwCO68', readback: 'consistent' }),
    modelSideRunner: async () => ({ ok: false, findings: [], error: '桩' }),
    adviceRunner: async () => ({ ok: true, advice: {} }),
    mergedReportRunner: async () => ({ ok: true, url: null, detail: '桩' }),
  });
  const turn = String(g.question ?? '');
  assert.ok(turn.includes('recvxwCWhwCO68'), '落表读数没进模型那一轮 ⇒ 它又会去猜表里有没有这一行');
  assert.ok(/落表读数/.test(turn), '读数块没有抬头 ⇒ 模型分不清它是什么');
  assert.ok(/不许.*表里没有这一行/.test(turn), '没把「不许反着说」交给模型');
});

await t('V4 ★ 反向对照：落表**抛异常**时必须落进「没有读数」那一支，不许静默', async () => {
  const { runSubmissionGate } = await import('./agent/agent.mjs');
  const g = await runSubmissionGate({
    inbound: { text: '审核下这张图', imageCount: 1, videoCount: 0 },
    question: '审核下这张图', notify: null,
    chainRunner: async () => ({ answer: '结论：REVIEW。依据 W-1.54。' }),
    publishRunner: async () => { throw new Error('网络断了'); },
    modelSideRunner: async () => ({ ok: false, findings: [], error: '桩' }),
    adviceRunner: async () => ({ ok: true, advice: {} }),
    mergedReportRunner: async () => ({ ok: true, url: null, detail: '桩' }),
  });
  const turn = String(g.question ?? '');
  assert.ok(/没有落表读数/.test(turn), '落表抛异常后读数块没出现 ⇒ 模型对表的状态一无所知却会照写');
  assert.ok(!/已(新建|更新)/.test(turn), '落表失败了却告诉模型「已落表」');
  assert.strictEqual(g.publish, null, '抛异常时 publish 应当是 null（不许编一个结果出来）');
});

await t('V5 ★ 反向对照：**不是送审**的那一轮，一个字符都不许加', async () => {
  const { runSubmissionGate } = await import('./agent/agent.mjs');
  const g = await runSubmissionGate({
    inbound: { text: '在吗', imageCount: 0, videoCount: 0 }, question: '在吗', notify: null,
    chainRunner: async () => { throw new Error('不该被调用'); },
    publishRunner: async () => ({ ok: true, action: 'created', record_id: 'recvXXX' }),
    // ★ 就算「不是送审」这一支也要**显式注入**：`Z25` 那条接线断言要求**每一处**
    //   `runSubmissionGate` 调用点都注入 `adviceRunner`（不注入就会真打 LLM）。
    //   这个桩按设计**永远不会被调用** —— 它存在的意义是「将来判据改了也不会静默打 LLM」。
    adviceRunner: async () => { throw new Error('不是送审，不该走到建议生成'); },
  });
  assert.strictEqual(g.gate?.yes, false, '闲聊被判成了送审');
  const turn = String(g.question ?? '');
  assert.ok(!/落表读数/.test(turn), '没送审却把落表读数塞进了这一轮');
  assert.ok(!/recvXXX/.test(turn), '没送审却泄露了一个行号');
});

await t('V6 ★ 行为级：「问题数量」列必须与卡里那个数**同一个**（Owner 2026-10-09 裁定）', async () => {
  // 原口径（10-07）：表列记**库侧机器读数**，卡里是并集上限 ⇒ 实测卡 7 / 表 5。
  // Owner 看过两轮后定为「统一成卡里那个数」：同一个数在卡片抬头、PRD §5.3.4 的 ≥3
  // 门槛、以及表列必须是同一个，否则人拿表去对卡永远对不上。
  const { runSubmissionGate } = await import('./agent/agent.mjs');
  // 库侧 5 条（旁挂 issue_count=5），模型侧 2 条 ⇒ 合并卡内 7 处
  const KB = ['【审查结论：REVIEW】共发现 5 处需人工确认。', ''].concat(
    [1, 2, 3, 4, 5].map((i) => `${i}.【措辞】图 1 第 ${i} 行 —— 库侧第 ${i} 条\n   **建议**：改法 ${i}\n`)).join('\n');
  let sent = null;
  const g = await runSubmissionGate({
    inbound: { text: '审核下这张图', imageCount: 1, videoCount: 0 },
    question: '审核下这张图', notify: null,
    chainRunner: async () => ({ answer: KB, review: { state: 'REVIEW', issue_count: 5 } }),
    publishRunner: async (row) => { sent = row; return { ok: true, action: 'updated', record_id: 'r1' }; },
    modelSideRunner: async () => ({ ok: true, ms: 1, findings: [
      { category: '本地化', location: '画面 1', severity: 'REVIEW', reason: '英文', suggestion: 's1' },
      { category: '隐私', location: '画面 2', severity: 'REVIEW', reason: '孩子出镜', suggestion: 's2' }] }),
    adviceRunner: async ({ items }) => ({ ok: true, ms: 1, advice: Object.fromEntries(items.map((_, i) => [i, 'a'])) }),
    mergedReportRunner: async () => ({ ok: true, url: null, detail: '桩' }),
  });
  // ★ 读的是 `g.dual.total`（**返回出来的那个形状**）——
  //   函数内部另有一个同名局部 `dual`（带 `.rendered`），两者字段不同：
  //   实测内部对象 `{model,kb,merged,state,rendered,kbSide,reportUrl}`，
  //   而返回给调用方的 `{state,stats,ok,model_ms,overrode,reportUrl,total,kb}`。
  //   第一版断言读了 `g.dual.rendered.total` ⇒ 恒 undefined ⇒ 假红（本次现场踩到）。
  const cardTotal = g.dual?.total ?? null;
  assert.ok(Number.isFinite(cardTotal), `这一单应当有合并总数（卡内那个数），实际 ${cardTotal}`);
  assert.strictEqual(sent?.issueCount, cardTotal,
    `表列「问题数量」${sent?.issueCount} ≠ 卡里那个数 ${cardTotal} —— 两处口径又分开了`);
  // ★ 库侧那个读数**不许丢**：它必须还在汇总格里（差从"看不见"变成"看得见且同一个数"）。
  //   同理这里不能读 `g.dual.kbSide`（那是**函数内部**那个形状的字段）——
  //   本单注入的库侧读数是 5，直接断言这个数在正文里。
  assert.ok(/库侧 5 条机器读数/.test(String(sent?.summary ?? '')),
    `汇总格里没有留下库侧机器读数：${String(sent?.summary ?? '').slice(0, 160)}`);
  assert.ok(/本列「问题数量」按卡里那个数记/.test(String(sent?.summary ?? '')),
    '汇总格没写明这一列的口径（填了数不说口径 = 没人看得懂）');
});

await t('V7 ★ 行为级：本仓建的合并报告，URL 必须**同时**进卡片与表里那一格', async () => {
  // 实测空档（10-09 15:28 那一单 recvxxfQoRewaF／AD-20261009-028）：卡内 3 处 ⇒ 本仓建了
  // 合并报告、URL 进了卡片，而**表里「报告链接」是空的** —— 那一格只认链侧那份
  // （`res.report`），而链侧那单只有 1 条、够不到它自己的 ≥3 门槛。
  // Owner 的原话是「把能填的都填了」⇒ 卡里有的链接，表里也得有。
  const { runSubmissionGate } = await import('./agent/agent.mjs');
  const URL = 'https://momcozy-in.feishu.cn/docx/V7PROBE';
  const KB = ['【审查结论：REVIEW】共发现 1 处需人工确认。', '',
    '1.【措辞】图 1 第 1 行 —— 库侧那条', '   **建议**：改法', ''].join('\n');
  const mk = (rep) => runSubmissionGate({
    inbound: { text: '审核下这张图', imageCount: 1, videoCount: 0 },
    question: '审核下这张图', notify: null,
    chainRunner: async () => ({ answer: KB, review: { state: 'REVIEW', issue_count: 1 } }),
    publishRunner: async (row) => { mk.sent = row; return { ok: true, action: 'updated', record_id: 'r1' }; },
    modelSideRunner: async () => ({ ok: true, ms: 1, findings: [
      { category: '本地化', location: '画面 1', severity: 'REVIEW', reason: '英文', suggestion: 's1' },
      { category: '隐私', location: '画面 2', severity: 'REVIEW', reason: '孩子出镜', suggestion: 's2' }] }),
    adviceRunner: async ({ items }) => ({ ok: true, ms: 1, advice: Object.fromEntries(items.map((_, i) => [i, 'a'])) }),
    mergedReportRunner: async () => rep,
  });
  mk.sent = null;
  const g = await mk({ ok: true, url: URL, detail: '桩' });
  assert.ok(g.dual?.total >= 3, `这一单应当够到报告门槛（卡内 ≥3），实际 ${g.dual?.total}`);
  assert.strictEqual(mk.sent?.reportUrl, URL, `表里「报告链接」没拿到本仓建的合并报告：${mk.sent?.reportUrl}`);
  assert.strictEqual(g.dual?.reportUrl, URL, '信封那条路（卡片）也没拿到 —— 两条路必须同一个 URL');
  // ★ 反向对照：**建不出报告时不许写占位符**（一个点不开的链接比空格更坏）
  mk.sent = null;
  await mk({ ok: false, url: null, detail: '建失败：桩' });
  assert.strictEqual(mk.sent?.reportUrl, null, `没有链接时写进了占位符：${mk.sent?.reportUrl}`);
});

// ══════════════════════════════════════════════════════════════════════════════
// Z33（2026-10-09）**视频时间码必须一路走到卡片**
// ══════════════════════════════════════════════════════════════════════════════
//   Owner 原话：「目前守衡输出的没有视频的时间节点 00:12 这些」。
//
//   病灶：`t_s` 一路都算出来了（`video.mjs` 的 `frameOcr[].t_s`），但帧文本有**三个消费者**
//   各拼各的，其中**两个把 `t_s` 丢掉了**：
//     · 卡片「帧上文字」（`agent.mjs::describeMediaRead`）—— 原先只取 `f.text`；
//     · 模型侧出 findings 的输入（`model_side.mjs::readingsForModelSide`）—— 同上；
//     · 库侧检索文本（`review_gate.mjs`）—— 保留。
//   而提示词却要求模型「指得出**第几帧**」—— 要它指位置，却不给它位置。
//
//   ⇒ 现在三处共用 `video.frameLine`（唯一产者）。这一组就是钉住「卡片与模型侧都带时间码」，
//     外加一条**反向对照**：库侧文本必须**逐字未变**（那一份原先就是对的，不许被顺手改掉）。
{
  const video = await import('./agent/video.mjs');
  const { describeMediaRead } = await import('./agent/agent.mjs');
  const { readingsForModelSide } = await import('./agent/model_side.mjs');
  const FRAMES = [
    { t_s: 0.02, text: 'Momeozy Wellness 1 vs Euiy S1 Pro' },
    { t_s: 8.64, text: 'so letls.compare it with my -Eufy-S1Pro' },
    { t_s: 25.87, text: 'line1\nline2' },
    { t_s: 34.48, failed: 'ocr_threw', detail: 'x' },
    { t_s: 43.10, text: '' },                     // 画面上没字 ⇒ 不该出现一行
  ];
  const inbound = () => ({
    videoCount: 1,
    videos: [{ index: 1, meta: { duration_s: 68.9 }, framesRead: 4, frames: FRAMES,
               transcript: { ok: true, chars: 20, text: 'this is my honest review' } }],
  });

  await t('Z33a 卡片「帧上文字」必须带时间码（Owner 点名的那一条）', async () => {
    const read = String(describeMediaRead(inbound()) ?? '');
    // ★ 2026-10-09：口径改成 Owner 要的 `MM:SS`（`8.64s → [00:08]`、`0.02s → [00:00]`）
    assert.ok(/\[00:08\]/.test(read), `卡上帧文本没有时间码：${read.slice(0, 200)}`);
    assert.ok(/\[00:00\]/.test(read), '第一帧的时间码也必须在');
    assert.ok(!/\[\d+\.\d+s\]/.test(read), '卡上还印着旧的「秒.小数」形状');
  });

  await t('Z33b 模型侧输入必须带时间码＋明说「每行开头是时间码」', async () => {
    const r = readingsForModelSide(inbound());
    assert.ok(/\[00:08\]/.test(r), '模型侧输入没有时间码 ⇒ 它只能编一个「帧 3」');
    assert.ok(/时间码/.test(r), '没告诉模型行首那个数是时间码');
  });

  await t('Z33c 提示词必须要求「视频给时间码」且禁止读音轨编秒数', async () => {
    const { SYSTEM } = await import('./agent/model_side.mjs');
    // ⚠️ `SYSTEM` 是**字符串**（不是数组）—— 第一版在这里调了 `.join('\n')`，
    //    把字符串拆成了字符数组 ⇒ 正则恒不命中、判据假红。踩过一次，写清楚。
    const p = String(SYSTEM);
    assert.ok(/时间码/.test(p), '提示词没要求给时间码');
    assert.ok(/不许编一个秒数/.test(p), '音轨转写没有时间戳这件事没写进提示词 ⇒ 模型会编');
  });

  await t('Z33d 库侧那份帧文本：形状逐字未变，但时间码是 Owner 的 `MM:SS` 口径', async () => {
    const got = FRAMES.map((f) => video.frameLine(f)).filter(Boolean).join('\n');
    // ★ 2026-10-09 改（Owner 第三次点这件事：「还是没展示到几秒 **00:12 格式**没看到」）：
    //   原先这里钉的是 `[0.02s]`（两位小数秒）—— 那是**旧口径**，改后按 `MM:SS` 截断。
    //   这条断言的价值仍是「形状逐字未变」（缩进 / ` / ` 折叠 / 失败帧那行都在），
    //   只是**那一格数字的形状**换成 Owner 要的：`0.02 → 00:00`、`34.48 → 00:34`。
    const want = ['  [00:00] Momeozy Wellness 1 vs Euiy S1 Pro',
                  '  [00:08] so letls.compare it with my -Eufy-S1Pro',
                  '  [00:25] line1 / line2',
                  '  [00:34] （这一帧 OCR 失败：ocr_threw）'].join('\n');
    assert.strictEqual(got, want, '库侧帧文本被改动了');
    // 反向对照：`[12.34s]` 那种带小数的旧形状**不许**再出现（否则就是没改干净）
    assert.ok(!/\[\d+\.\d+s\]/.test(got), '还在印旧的「秒.小数」形状：' + got.slice(0, 80));
  });

  await t('Z33d2 时间码必须是 `MM:SS` 且**提示词同口径**（缺一件都出不来 00:12）', async () => {
    const { mmss } = video;
    // 截断，不四舍五入：Owner 举的例子 `00:12` 对应的原始读数是 `12.91s`
    assert.strictEqual(mmss(12.91), '00:12', '12.91s 必须是 00:12（四舍五入会成 00:13，与 Owner 的卡对不上）');
    assert.strictEqual(mmss(4.30), '00:04', '4.30s 必须是 00:04');
    assert.strictEqual(mmss(60), '01:00', '满 60 秒必须进位成 01:00');
    assert.strictEqual(mmss(125.4), '02:05', '125.4s 必须是 02:05');
    assert.strictEqual(mmss(-1), '00:00', '负秒数不许印负号');
    assert.strictEqual(mmss(NaN), '00:00', 'NaN 不许漏出去（未测不许长得像测过）');
    // ★ 这一半才是「模型会不会输出 00:12」的关键：提示词教它抄的形状
    const { SYSTEM } = await import('./agent/model_side.mjs');
    assert.ok(/行首 `\[00:12\]`/.test(String(SYSTEM)),
      '提示词还在教旧形状 ⇒ 模型会照抄 `[12.34s]`，卡上永远出不来 00:12');
    assert.ok(!/行首 `\[\d+\.\d+s\]`/.test(String(SYSTEM)), '提示词里还留着旧的 `秒.小数` 形状');
  });

  await t('Z33e 画面上没字的帧不许冒出一行；无合法时间码要明说', async () => {
    assert.strictEqual(video.frameLine({ t_s: 43.1, text: '   ' }), null, '空帧不该出一行');
    const noT = video.frameLine({ text: 'abc' });
    assert.ok(/时间码缺失/.test(noT), `没有 t_s 时不许印 NaN 冒充：${noT}`);
  });
}

// ══════════════════════════════════════════════════════════════════════════════
// Z36 ★（2026-10-09）**卡内算术必须闭合**（Owner 报「图表数字对不上」）
// ══════════════════════════════════════════════════════════════════════════════
//   实测那单（16:24）：抬头「共发现 **8** 处」，页脚「知识库侧 **2** 条 ／ 模型侧 **6** 条」——
//   2+6=8 看着对，而**库侧实际并进来 5 条**（双轨读数：库侧 5 ＋ 模型侧 6 ⇒ 合并 8），
//   卡里另一处还写着「REVIEW 5 处」。根因：页脚用「**并进清单里的**库侧条目」，
//   抬头那个数却含「**没并进来的**」⇒ 两个口径不同的数并排印。
//   ⇒ 那之后页脚是「知识库侧 X（结构化读数）＋ 模型侧 Y − 计入 N 处（去重 D）＝ 本卡 N 处」。
//
// ★★ 2026-10-13（Owner 裁定）**那一行整行从卡上撤走了**（它属于「库侧/模型侧的口径读数」那一族）。
//   ⚠️ 但**不变式一条都没松**，只是换了两处落点 —— 判据必须跟着搬，否则等于把这条账删了：
//     ① **查证笔记**里那个算式仍要闭合（它就是原来那行，只是不再上卡）；
//     ② **卡面**改成「分类行相加 ＋ 另有 N 条 ＝ 抬头」——这是 PRD §5.3.3 那一格的算式，
//        同样必须闭合（实测 19:08 那单：抬头 12、分类只有 7 ⇒ 不闭合，读者一眼就看出对不上）。
{
  const T = await import('./agent/dual_track.mjs');
  const mk = (i, c) => ({ location: `p${i}`, category: c, severity: 'REVIEW', source: 'kb',
    reason: 'r', excerpt: `e${i}` });
  const mo = (i) => ({ location: `m${i}`, category: '措辞表达', severity: 'REVIEW',
    source: 'model', reason: 'x' });

  const probe = (kbCnt, kbTextN, modelCnt) => {
    const kbItems = Array.from({ length: kbCnt }, (_, i) => mk(i, '品牌一致性'));
    const modelItems = Array.from({ length: modelCnt }, (_, i) => mo(i));
    const merge = T.mergeFindings(kbItems.slice(0, kbTextN), modelItems);
    const r = T.renderMerged(merge.items, {
      state: 'REVIEW', kb: T.kbSideOf({ review: { state: 'REVIEW', issue_count: kbCnt } }),
      kbTextCount: kbTextN, model: { ok: true, findings: modelItems },
      mergedStats: merge.stats, reportUrlOverride: 'https://x/docx/A' });
    const head = Number((r.block.match(/共发现 (\d+) 处/) || [])[1]);
    // 页脚（那个算式）现在在**查证笔记**里
    const foot = (r.internalNotes.match(/^知识库侧.*$/m) || [''])[0];
    const m = foot.match(/知识库侧 (\d+) 条.*＋ 模型侧 (\d+) 条(?: − 计入 (\d+) 处（去重 (\d+))?/);
    return { head, foot, m, r };
  };

  await t('Z36a 查证笔记里那个算式仍要闭合（四种形状都核）', async () => {
    for (const [kb, txt, moN, label] of [[5, 2, 6, '库侧 5 读数/并进 2/模型 6'],
      [5, 5, 6, '库侧 5/5/6'], [0, 0, 8, '库侧 0'], [3, 3, 0, '只有库侧 3']]) {
      const { head, foot, m } = probe(kb, txt, moN);
      assert.ok(m, `查证笔记里没印出可核的算式（${label}）：${foot}`);
      const lhs = Number(m[1]) + Number(m[2]) - Number(m[4] || 0);
      assert.strictEqual(lhs, head, `${label}：${m[1]}+${m[2]}-${m[4] || 0}=${lhs} ≠ 抬头 ${head}`);
    }
  });

  await t('Z36a2 ★ 卡面的算式也要闭合：分类行相加 ＋「另有 N 条」＝ 抬头（PRD §5.3.3 那一格）', async () => {
    for (const [kb, txt, moN, label] of [[5, 2, 6, '库侧 5 读数/并进 2/模型 6'],
      [5, 5, 6, '库侧 5/5/6'], [0, 0, 8, '库侧 0'], [3, 3, 0, '只有库侧 3']]) {
      const { head, r } = probe(kb, txt, moN);
      const cats = [...r.block.matchAll(/^· .*类问题：(\d+) 个$/gm)].map((x) => Number(x[1]));
      const extra = Number((r.block.match(/^· 另有 \*\*(\d+) 条\*\*/m) || [])[1] || 0);
      const sum = cats.reduce((a, b) => a + b, 0) + extra;
      assert.strictEqual(sum, head, `${label}：分类 ${cats.join('+')} ＋ 另有 ${extra} ＝ ${sum} ≠ 抬头 ${head}`);
    }
  });

  await t('Z36b 查证笔记要标明「库侧那个数是结构化读数」；卡面上**不许**再出现这个算式', async () => {
    const { foot, r } = probe(5, 2, 6);
    // 病灶原样：印成「知识库侧 2 条 ／ 模型侧 6 条」——2 是**并进清单里的**，看着像总数
    assert.ok(/结构化读数/.test(foot), `查证笔记没标明库侧那个数的口径：${foot}`);
    assert.ok(!/^知识库侧 \d+ 条 ／ 模型侧 \d+ 条$/.test(foot), '又退回旧形状（口径不同的两个数并排）');
    // ★ 2026-10-13 反向对照：这一行**不许**再上卡（Owner：「不要展示在卡片上」）
    assert.ok(!/结构化读数/.test(r.block), '口径读数又回到卡面了');
    assert.ok(!/^知识库侧/m.test(r.block), '「知识库侧 …」那一行又回到卡面了');
  });
}

// ══════════════════════════════════════════════════════════════════════════════
// Z37 ★（2026-10-09）**OCR 水印不许当素材内容**（Owner 亲自看出来的根因）
// ══════════════════════════════════════════════════════════════════════════════
//   Owner 原话：「图上文字：5615 RO0 刘华丽 刘华問 ==》这是我，是因为图片上有水印吗？」
//   他判断对：那是飞书文档的协作水印（用户名 + 工号），而它**进了检索** ⇒
//   拿水印里的常用词撞库 ⇒ 撞出一堆无关的内部样本、又被渲染成「命中」进报告。
//
//   判据：**同一串出现在图的不同位置**（水印平铺的定义），坐标由 `vision.normalize`
//   带出（原先被它丢掉，同日修复）。
//   ⚠️ 本组有一条**反向对照**：真内容（`Sep 15 / Week1 / Week4`）**一个都不许删** ——
//     第一版用了"近似变体"判据，把这些日历数据也当水印删了（35 行误删 17 行）。
{
  const { stripOcrWatermark } = await import('./agent/ocr_watermark.mjs');
  // 线上那一单的真实 OCR 文本（逐字，从库内留痕取的）
  const REAL = ['5615 RO0', '刘华丽', '刘华問', '#MomAndMore activity calendar', '5615 R00',
    'Each Group has its own activities—choose the ones you like and join in.', 'Every week：',
    '1topic activity & i+ comment or game', 'Sep 15', 'Mystery', 'activity', 'begins', '5',
    '刘华問', 'Week2', 'Sep8-14', '5615 RC', 'Week1', 'Sep 1-7', '5615 ROOT', 'Week4',
    'Sep 22-28', '5615', '刘华', 'Week3', 'Sep 15-21', '5615', 'Winners', 'announcements',
    'every weekend', '华', '八613', 'MOMCOZY', '1化司', '5615'];
  const text = REAL.join('\n');
  // 坐标：让**真的重复了的**串落在不同位置（刘华問×2、5615×3），其余各就各位
  const pos = { '刘华問': [[0.10, 0.90], [0.60, 0.35]], '5615': [[0.10, 0.85], [0.62, 0.30], [0.30, 0.12]] };
  const seen = {};
  const boxes = REAL.map((t, i) => {
    const p = pos[t];
    let x = 0.05 + (i % 6) * 0.15, y = 0.95 - (i % 12) * 0.07;
    if (p) { const k = (seen[t] = (seen[t] ?? -1) + 1); x = p[Math.min(k, p.length - 1)][0]; y = p[Math.min(k, p.length - 1)][1]; }
    return { t, x, y };
  });

  await t('Z37a 不同位置上的同一串 ⇒ 判水印（且能说出判据）', async () => {
    const r = stripOcrWatermark({ text, boxes });
    assert.strictEqual(r.basis, 'core-tiled-at-different-positions', `判据不对：${r.basis}`);
    assert.ok(r.dropped.length >= 2, `没摘到水印：${r.dropped.length}`);
  });

  await t('Z37b ★ 反向对照：真内容一个都不许删（日历的周次/日期是内容，不是水印）', async () => {
    const r = stripOcrWatermark({ text, boxes });
    const content = ['#MomAndMore activity calendar',
      'Each Group has its own activities—choose the ones you like and join in.',
      'Sep 15', 'Week1', 'Week2', 'Week3', 'Week4', 'Sep 1-7', 'Sep 22-28', 'MOMCOZY', 'Winners'];
    const lost = content.filter((c) => !r.text.includes(c));
    assert.deepStrictEqual(lost, [], `真内容被当水印删了：${lost.join(' / ')}`);
  });

  await t('Z37c 同一串落在**同一处**不许判水印（同处重复是内容，不是平铺）', async () => {
    const r = stripOcrWatermark({ text: 'MOMCOZY\nMOMCOZY', boxes: [{ t: 'MOMCOZY', x: 0.1, y: 0.5 }, { t: 'MOMCOZY', x: 0.11, y: 0.5 }] });
    assert.strictEqual(r.dropped.length, 0, `同处重复被误判成水印：${r.dropped.join(' / ')}`);
  });

  await t('Z37d 没有坐标时退回「字面重复」判据，且不误删真内容', async () => {
    const r = stripOcrWatermark({ text });
    // ★ 2026-10-09 修正：这一条原先只断言 `basis === 'exact-repeat-no-coords'`，
    //   而那个名字**从 v2 起再也印不出来**（`basis` 只在 `cores.length` 上分支 ⇒ 兜底干活也印 `none`）。
    //   断言当时是红的，红得**对**：错的是标签，不是行为。
    //   ⇒ 现在同时钉三件事：① 兜底**真的摘了**（不是"没摘还说摘了"）；
    //     ② 标签**说得出是哪条判据**；③ 真内容（`Sep 15`/`Week1`）一个都不许丢。
    assert.strictEqual(r.basis, 'exact-repeat-no-coords', `判据不对：${r.basis}`);
    assert.ok(r.dropped.length >= 2, `兜底判据没摘到东西，这条断言就变成了空转：${r.dropped.length}`);
    assert.ok(r.dropped.some((d) => /刘华問|5615/.test(d)), `摘的不是水印：${r.dropped.join(' / ')}`);
    assert.ok(r.text.includes('Sep 15') && r.text.includes('Week1'), '无坐标时误删了真内容');

    // ★ 反向对照：**一行都没摘**时必须印 `none`，不许印一个判据名冒充「我摘了」
    const clean = stripOcrWatermark({ text: 'Sep 15\nWeek1\nMOMCOZY' });
    assert.strictEqual(clean.basis, 'none', `没摘任何行却说用了判据：${clean.basis}`);
  });
}

// ══════════════════════════════════════════════════════════════════════════════
// Z38 ★★（2026-10-09）**水印摘除 v2：用真图坐标钉住**（Owner 把原图发过来了）
// ══════════════════════════════════════════════════════════════════════════════
//   这条判据的价值全在**样本是真图**：35 行 OCR + **真实归一化坐标**（本机 OCR 跑真图取回）。
//   前三个候选判据都被它否掉了（写在 `ocr_watermark.mjs` 的注释里，免得下一个人再走一遍）：
//     · 「任意公共子串」⇒ 误删 `Week1/Sep 15`；· 「数字跨 ≥2 行」⇒ 误删 `Sep 15`；
//     · 「数字须与另一个多处数字同行」⇒ 太严（`5615` 全漏）；· 「数字紧邻字母」⇒ 分不开。
//   现在这条：**按数字核心聚类**（`5615R00`/`5615ROOT`/`5615RO`/`5615` 共享 `5615`）。
{
  const { stripOcrWatermark } = await import('./agent/ocr_watermark.mjs');
  // 真图 OCR（1252×1150）逐行 + 真实坐标
  const REAL = [
    ['5615 R00', 0.050, 0.777], ['5615 ROOT', 0.349, 0.930], ['刘华丽', 0.278, 0.910],
    ['刘华丽', 0.874, 0.913], ['#MomAndMore activity calendar', 0.145, 0.844],
    ['Each Group has its own activities—choose the ones you like and join in.', 0.169, 0.805],
    ['刘华丽', 0.573, 0.755], ['50', 0.645, 0.781], ['Every week：', 0.329, 0.638],
    ['1topic activity & i+ comment or game', 0.153, 0.604], ['Sep 15', 0.711, 0.665],
    ['Mystery', 0.732, 0.609], ['activity', 0.735, 0.583], ['begins', 0.740, 0.555],
    ['刘华', 0.872, 0.604], ['Week2', 0.527, 0.490], ['Sep 8-14', 0.523, 0.453],
    ['5615 RO', 0.639, 0.470], ['Week1', 0.184, 0.414], ['Sep 1-7', 0.187, 0.377],
    ['615', 0.366, 0.329], ['ROO', 0.407, 0.337], ['Week4', 0.527, 0.334],
    ['Sep 22-28', 0.517, 0.297], ['5615', 0.940, 0.318], ['刘华', 0.872, 0.297],
    ['Week3', 0.273, 0.259], ['Sep 15-21', 0.268, 0.223], ['5615', 0.646, 0.168],
    ['Winners', 0.752, 0.233], ['announcements', 0.706, 0.209], ['every weekend', 0.714, 0.180],
    ['MOMCOZY', 0.410, 0.017], ['4俗丽', 0.877, 0.009], ['50', 0.941, 0.019],
  ];
  const ocr = () => ({ text: REAL.map((r) => r[0]).join('\n'),
                       boxes: REAL.map((r) => ({ t: r[0], x: r[1], y: r[2] })) });

  await t('Z38a 真图：水印（用户名＋编号各变体）必须全部摘掉', async () => {
    const r = stripOcrWatermark(ocr());
    assert.strictEqual(r.basis, 'core-tiled-at-different-positions', `判据不对：${r.basis}`);
    for (const w of ['刘华丽', '刘华', '5615', '5615 R00', '5615 ROOT', '5615 RO']) {
      assert.ok(!r.text.includes(w), `水印残留：${w}`);
    }
  });

  await t('Z38b ★★ 反向对照：日历的真内容一个都不许删（本组是这条判据的核心价值）', async () => {
    const r = stripOcrWatermark(ocr());
    const content = ['#MomAndMore activity calendar',
      'Each Group has its own activities—choose the ones you like and join in.', 'Every week：',
      '1topic activity & i+ comment or game', 'Sep 15', 'Mystery', 'activity', 'begins',
      'Week1', 'Week2', 'Week3', 'Week4', 'Sep 1-7', 'Sep 8-14', 'Sep 15-21', 'Sep 22-28',
      'Winners', 'announcements', 'every weekend', 'MOMCOZY'];
    const lost = content.filter((c) => !r.text.includes(c));
    assert.deepStrictEqual(lost, [], `真内容被当水印删了：${lost.join(' / ')}`);
  });

  await t('Z38c 只有 2 次重复的**内容**数字不许当核心（防 v2a 那个误删）', async () => {
    // `15` 出现在 `Sep 15` 与 `Sep 15-21` 两行、位置不同 —— 但它**不共享数字核心**
    const r = stripOcrWatermark(ocr());
    assert.ok(!r.cores.includes('15'), '把内容数字 15 当成了水印核心');
  });
}

// ══════════════════════════════════════════════════════════════════════════════
// Z39 ★★（2026-10-09）**水印不许进「给模型看的那一段」**（Owner 第二次来问水印）
// ══════════════════════════════════════════════════════════════════════════════
//   病灶（我自己造成的，第二次才被发现）：
//   同一段图内文字**有两个产者**，改水印时我只改了一个 ——
//     · `describeMediaRead`（卡片那一格）：已改印 `wlText` ⇒ **干净**；
//     · `buildImageBlock`（`buildUserTurn({imageBlock})` ⇒ **喂给模型**）：仍印 `im.text` ⇒ **带水印**。
//   ⇒ 我先答了 Owner「卡片会干净」，却漏了「送进去的还是脏的」：
//     模型与**报告**那一侧继续拿水印当素材内容（Owner 两轮都在追这件事）。
//   ⇒ 这一组同时钉**两个产者**：Z38 只钉「判据本身」，钉不住「接线」。
{
  const { stripOcrWatermark } = await import('./agent/ocr_watermark.mjs');
  const { buildImageBlock, describeMediaRead } = await import('./agent/agent.mjs');
  // 与 Z38 同源的真图 OCR（35 行 + 真实归一化坐标）
  const REAL = [
    ['5615 R00', 0.050, 0.777], ['5615 ROOT', 0.349, 0.930], ['刘华丽', 0.278, 0.910],
    ['刘华丽', 0.874, 0.913], ['#MomAndMore activity calendar', 0.145, 0.844],
    ['Each Group has its own activities—choose the ones you like and join in.', 0.169, 0.805],
    ['刘华丽', 0.573, 0.755], ['50', 0.645, 0.781], ['Every week：', 0.329, 0.638],
    ['1topic activity & i+ comment or game', 0.153, 0.604], ['Sep 15', 0.711, 0.665],
    ['Mystery', 0.732, 0.609], ['activity', 0.735, 0.583], ['begins', 0.740, 0.555],
    ['刘华', 0.872, 0.604], ['Week2', 0.527, 0.490], ['Sep 8-14', 0.523, 0.453],
    ['5615 RO', 0.639, 0.470], ['Week1', 0.184, 0.414], ['Sep 1-7', 0.187, 0.377],
    ['615', 0.366, 0.329], ['ROO', 0.407, 0.337], ['Week4', 0.527, 0.334],
    ['Sep 22-28', 0.517, 0.297], ['5615', 0.940, 0.318], ['刘华', 0.872, 0.297],
    ['Week3', 0.273, 0.259], ['Sep 15-21', 0.268, 0.223], ['5615', 0.646, 0.168],
    ['Winners', 0.752, 0.233], ['announcements', 0.706, 0.209], ['every weekend', 0.714, 0.180],
    ['MOMCOZY', 0.410, 0.017], ['4俗丽', 0.877, 0.009], ['50', 0.941, 0.019],
  ];
  // 逐字复刻 `readInboundContent` 对每张图做的那一跳（真入口要真图字节，这里只需这一跳）
  // ★ 2026-10-09 晚**收口后**的形状：`text` = **摘掉水印那份**（唯一对外文本）、
  //   `textRaw` = OCR 原文（只给诊断与留痕）。测试必须用**生产同形**的数据，
  //   否则「产者各挑各的」那类缺陷在测试里永远看不见 —— 这一版就是这么被抓出来的。
  const strip = () => {
    const text = REAL.map((r) => r[0]).join('\n');
    const boxes = REAL.map((r) => ({ t: r[0], x: r[1], y: r[2] }));
    const wm = stripOcrWatermark({ text, boxes, senderName: '刘华丽' });
    return { index: 1, text: wm.text, textRaw: text, lines: REAL.length, chars: text.length,
             wlText: wm.text, wmDropped: wm.dropped, wmBasis: wm.basis };
  };
  const inbound = () => ({ imageCount: 1, images: [strip()] });

  await t('Z39a ★ 喂给模型的图块不许含水印（这一跳原先印的是 OCR 原文）', async () => {
    const b = buildImageBlock(inbound());
    for (const w of ['刘华丽', '刘华', '5615']) {
      assert.ok(!b.includes(w), `水印进了「给模型看的那一段」：${w}`);
    }
  });

  await t('Z39b ★ 卡片那一格同时也不许含水印（两个产者一起钉）', async () => {
    const read = String(describeMediaRead(inbound()) ?? '');
    for (const w of ['刘华丽', '刘华', '5615']) {
      assert.ok(!read.includes(w), `水印进了卡片：${w}`);
    }
  });

  await t('Z39c ★★ 反向对照：真内容一个都不许丢（送进去的那份）', async () => {
    const b = buildImageBlock(inbound());
    const content = ['#MomAndMore activity calendar', 'Sep 15', 'Week1', 'Week4',
                     'Winners', 'MOMCOZY', 'Every week：'];
    const lost = content.filter((c) => !b.includes(c));
    assert.deepStrictEqual(lost, [], `真内容没进图块：${lost.join(' / ')}`);
  });

  await t('Z39d 摘了水印必须明写「另摘除水印 N 行」，且行数仍报真读数', async () => {
    const b = buildImageBlock(inbound());
    // 行数不许缩水成「正文行数」—— 那是**读到几行**这个真读数（35）
    assert.ok(/35 行/.test(b), `行数不是真读数：${b.slice(0, 120)}`);
    assert.ok(/另摘除水印 \d+ 行/.test(b), '摘了水印却不说 —— 模型会以为行数对不上正文');
    assert.ok(!/另摘除水印 0 行/.test(b), '没摘也印一行「另摘除 0 行」= 噪声');
  });

  await t('Z39e 没有水印时不许凭空多出一句（反向对照）', async () => {
    const clean = { imageCount: 1, images: [{ index: 1, text: 'MOMCOZY\nSep 15', textRaw: 'MOMCOZY\nSep 15',
                                              lines: 2, chars: 13, wlText: 'MOMCOZY\nSep 15',
                                              wmDropped: [], wmBasis: 'none' }] };
    const b = buildImageBlock(clean);
    assert.ok(!/另摘除水印/.test(b), '没摘水印却印了摘除说明');
    assert.ok(b.includes('MOMCOZY') && b.includes('Sep 15'), '无水印时把内容弄丢了');
  });

  await t('Z39f ★★ 模型侧读数也不许含水印（**第三个产者**，Owner 报告里的那两条建议就是它）', async () => {
    const { readingsForModelSide } = await import('./agent/model_side.mjs');
    const r = readingsForModelSide(inbound());
    // 病灶原样（实测那份报告的建议）：模型把水印当"素材里的中文人名"写成了整改建议 ——
    // 「图上出现『刘华丽』『刘华問』三处中文人名，若是参与用户真名，换成昵称或整行删掉」
    // ⇒ 让被审方去改一个图上根本不存在的元素。
    for (const w of ['刘华丽', '刘华', '5615']) {
      assert.ok(!r.includes(w), `水印进了模型侧读数 ⇒ 模型会把它当素材内容写成整改建议：${w}`);
    }
    assert.ok(r.includes('Sep 15') && r.includes('Week1'), '模型侧把真内容弄丢了');
  });

  await t('Z39g 结构：`text` 必须是**摘除后**那份（收口的根据，四处产者不许再各挑各的）', async () => {
    const src = fs.readFileSync(new URL('./agent/agent.mjs', import.meta.url), 'utf8');
    assert.ok(/text:\s*wm\.text,\s*textRaw:\s*r\.text/.test(src),
      '`images.push` 里 `text` 不再是摘除后那份 —— 消费者又会拿到带水印的原文');
    // 诊断日志必须用原文（否则「我到底读到了什么」就没法核了）
    assert.ok(/describeMediaRead\(inbound,\s*\{\s*raw:\s*true\s*\}\)/.test(src),
      '诊断日志没走 raw:true ⇒ 印的是摘除后的，核对时看不到 OCR 真读数');
    // ★ 2026-10-13：卡上那一格**已经撤了**（Owner：媒材读数不上卡）⇒ 这一条改盯
    //   **报告附录**那一份：它必须仍是**摘除后**的（`mediaReadAppendix` 内部走默认参数）。
    //   水印会回到**人眼前**的通道就剩这一条（卡上那条已经不存在了）—— 所以更要盯住它。
    // ⚠️ 判据**只在函数体里找** —— 第一版写成「`mediaReadAppendix` 之后 200 字内出现 raw:true」
    //   就把它**自己的解释文字**扫进来了（实测命中 `…见它自己的头注）。⚠️ 这一行印 **OCR 原文**（raw:true`），
    //   于是真身永远红。这就是 §2.4.4 记的「判据被自己的注释绊倒」——**统一一条读法：注释不算代码**。
    const body = (src.match(/export function mediaReadAppendix\([\s\S]*?\n\}/) || [''])[0];
    assert.ok(body.length > 200, '取不到 mediaReadAppendix 的函数体 —— 判据本身失效');
    assert.ok(!/raw\s*:\s*true/.test(body),
      '报告附录那一份改用了 raw:true ⇒ 水印会回到报告里');
  });
}

// ══════════════════════════════════════════════════════════════════════════════
// Z40 ★★（2026-10-09 晚）**「名字只被 OCR 读出 1 次」也要摘掉**（Owner 连报两次）
// ══════════════════════════════════════════════════════════════════════════════
//   Owner 原话（这一轮）：「图上文字：刘华丽==》**还有我的名字**」。
//   病灶（**接线顺序错了，不是判据错**）：`readInboundContent` 读图那一刻还不知道
//   送审人叫什么（名字要到 `handleMessage` 第 4 步才解析）⇒ 判据只能靠
//   「OCR 有没有把名字读出 ≥2 次、且落在不同位置」去猜。而**同一张图的两次 OCR
//   读数并不一致**（实测：一次 `刘华問`×2 + `刘华丽`×1，另一次 `刘华`×2 + `刘华丽`×3）
//   ⇒ 只读出 1 次时它当不上"平铺核心"⇒ 摘不掉 ⇒ 卡片与报告继续带着名字。
//   水印逐字就是「**用户名 + 工号**」（台账实测 `sender: 刘华丽`）⇒ 名字是**已知的**。
//   ⇒ 现在补一条**与 OCR 读数无关**的判据：行**逐字等于**送审人显示名 ⇒ 水印。
{
  const { stripOcrWatermark } = await import('./agent/ocr_watermark.mjs');
  const box = (t, x, y) => ({ t, x, y });

  await t('Z40a ★ 名字只出现 1 次也必须摘掉（这就是 Owner 报的那一次）', async () => {
    const r = stripOcrWatermark({
      text: ['刘华丽', '#MomAndMore activity calendar', 'Sep 15', 'Week1'].join('\n'),
      boxes: [box('刘华丽', 0.278, 0.910), box('#MomAndMore activity calendar', 0.145, 0.844),
              box('Sep 15', 0.711, 0.665), box('Week1', 0.184, 0.414)],
      senderName: '刘华丽',
    });
    assert.ok(!r.text.includes('刘华丽'), '名字还在 —— 这一条没生效');
    assert.deepStrictEqual(r.dropped, ['刘华丽'], `摘错了：${JSON.stringify(r.dropped)}`);
    // ★ 判据名必须是**它自己那一个**：只靠名字摘到的，不许说成「我证明了它平铺」
    assert.strictEqual(r.basis, 'sender-name-in-ocr', `判据名不对：${r.basis}`);
  });

  await t('Z40b ★★ 反向对照：不传 senderName ⇒ 行为逐字不变（旧判据一个字没松）', async () => {
    const noName = stripOcrWatermark({
      text: ['刘华丽', '#MomAndMore activity calendar', 'Sep 15', 'Week1'].join('\n'),
      boxes: [box('刘华丽', 0.278, 0.910), box('#MomAndMore activity calendar', 0.145, 0.844),
              box('Sep 15', 0.711, 0.665), box('Week1', 0.184, 0.414)],
    });
    assert.strictEqual(noName.dropped.length, 0,
      '不传名字时把只出现一次的行摘了 —— 说明「平铺」判据被顺手放松了（那是误删真内容的方向）');
    assert.strictEqual(noName.basis, 'none', '没摘任何行却印了判据');
  });

  await t('Z40c 拿占位符「(未知名)」当判据 ⇒ 必须不生效（不许拿占位符当证据）', async () => {
    const r = stripOcrWatermark({
      text: '(未知名)\nSep 15', boxes: [box('(未知名)', 0.1, 0.1), box('Sep 15', 0.5, 0.5)],
      senderName: '(未知名)',
    });
    assert.strictEqual(r.dropped.length, 0, '把「(未知名)」当成了水印判据');
  });

  await t('Z40d 名字那一行**恰好是内容**时：只删那一行，别的不许动（边界写实）', async () => {
    const r = stripOcrWatermark({
      text: ['May', 'Week1', 'Sep 15', 'Every week：'].join('\n'),
      boxes: [box('May', 0.5, 0.5), box('Week1', 0.1, 0.4), box('Sep 15', 0.7, 0.6), box('Every week：', 0.3, 0.3)],
      senderName: 'May',
    });
    // 逐字相等 ⇒ 命中；这是**已知的、可接受的**代价（见 ocr_watermark.mjs 的注释：
    // 不做"包含"就是为了把误删面收到最小；正文里恰好只有发送人名字一行的概率极低）
    assert.deepStrictEqual(r.dropped, ['May'], `摘的不是那一行：${JSON.stringify(r.dropped)}`);
    assert.ok(r.text.includes('Week1') && r.text.includes('Sep 15'), '连带把真内容删了');
  });

  await t('Z40e 接线三跳：顺序对 / 入参声明 / 真被调用（缺一跳这条线就断）', async () => {
    const src = fs.readFileSync(new URL('./agent/agent.mjs', import.meta.url), 'utf8');
    const iDef = src.indexOf('const senderNameForWatermark = ()');
    const iRead = src.indexOf('await readInboundContent(msg');
    assert.ok(iDef > 0, '找不到 senderNameForWatermark 的定义');
    assert.ok(iRead > 0, '找不到 readInboundContent 的调用');
    // ① 顺序：名字要在**读图之前**备好
    assert.ok(iDef < iRead,
      '名字的取数函数排在读图**之后** —— 摘水印时又拿不到名字，这一整条等于没接');

    // ② 入参：`readInboundContent` 必须真的声明它（只在调用点传、函数不接 ⇒ 静默丢掉）
    const fnStart = src.indexOf('export async function readInboundContent');
    assert.ok(fnStart > 0, '找不到 readInboundContent 定义');
    const fnBody = src.slice(fnStart, src.indexOf('\n} = {}) {', fnStart) + 10);
    assert.ok(/senderNameForWatermark\s*=\s*null/.test(fnBody),
      'readInboundContent 的入参里没有 senderNameForWatermark —— 传了也没人接（静默丢参数）');

    // ③ 调用：真去取名字、真传给判据（③ 是最容易漏的一跳：参数接了却不用）
    const imgBranch = src.slice(fnStart, src.indexOf('export async function describeMediaRead'));
    assert.ok(/await senderNameForWatermark\(\)/.test(imgBranch),
      'readInboundContent 里从没调过 senderNameForWatermark() —— 参数接了不用');
    assert.ok(/stripOcrWatermark\(\{[^}]*senderName[^}]*\}\)/.test(imgBranch),
      '取到的名字没传给 stripOcrWatermark —— 取了也白取');
  });
}

// ══════════════════════════════════════════════════════════════════════════════
// Z41 ★★（2026-10-09 晚）**卡片只留读数，全文进报告附录**
// ══════════════════════════════════════════════════════════════════════════════
//   Owner 原话：「【图 1 内文字｜35 行，另摘除水印 10 行（不是素材内容）】==》**丑排版**」，
//   并为「把原文挪到附录」这个方向**点了头**（「你下午修复过一次，把排版丑放到附录中==》可以的」）。
//
//   病灶：卡片正文里塞着 **35 行 OCR 碎片**，被 `cut(200)` 切一半、又用 ` / ` 折成一行 ——
//     既不是给人看的（碎片本就不通顺），也不是给回源核对的（切了一半）。
//   结构上它出现在**两个地方**（卡片 + 报告），而两份都是"半截"。
//
//   ⇒ 分工：**卡片给业务看读数**（读到几行、摘掉几行水印），**报告附录给回源核对全文**。
//     ⚠️ **搬不是砍**：全文必须真的落进报告附录（先证明报告接得住，再从卡上撤）。
//     ⚠️ 卡上仍要**看得见**摘了多少行水印（那是"我处理过了"的读数，不是内容）。
{
  const { describeMediaRead, mediaReadAppendix } = await import('./agent/agent.mjs');
  const { renderMergedReportMd } = await import('./agent/merged_report.mjs');
  // 真图真数据（同 Z38/Z39）：35 行 OCR + 真坐标 + 真摘除结果
  const REAL35 = [
    '5615 R00', '刘华丽', '刘华問', '#MomAndMore activity calendar', '5615 R00',
    'Each Group has its own activities—choose the ones you like and join in.', 'Every week：',
    '1topic activity & i+ comment or game', 'Sep 15', 'Mystery', 'activity', 'begins', '5',
    '刘华問', 'Week2', 'Sep8-14', '5615 RC', 'Week1', 'Sep 1-7', '5615 ROOT', 'Week4',
    'Sep 22-28', '5615', '刘华', 'Week3', 'Sep 15-21', '5615', 'Winners', 'announcements',
    'every weekend', '华', '八613', 'MOMCOZY', '1化司', '5615',
  ];
  const inboundImg = () => ({
    imageCount: 1,
    images: [{
      index: 1, lines: 35, chars: 359, truncated: false,
      text: REAL35.filter((l) => !/5615|刘华丽|刘华問|刘华/.test(l)).join('\n'),
      textRaw: REAL35.join('\n'),
      wmDropped: ['5615 R00', '刘华丽', '刘华問', '5615 R00', '刘华問', '5615 RC', '5615 ROOT',
                  '5615', '刘华', '5615'],
      wmBasis: 'core-tiled-at-different-positions',
    }],
  });
  const inboundVid = () => ({
    videoCount: 1,
    videos: [{ index: 1, meta: { duration_s: 68.9 }, framesRead: 2, framesFailed: 0,
               frames: [{ t_s: 4.3, text: 'Momeozy Wellness 1 vs Euiy S1 Pro' },
                        { t_s: 12.91, text: 'Eufy S1 Pro has a single layer' }] }],
  });

  await t('Z41a ★ 卡片那一格**不再塞 OCR 碎片**（只留读数）', async () => {
    const read = String(describeMediaRead(inboundImg()) ?? '');
    // 锚定「图上文字：」那一行里**只有读数**，不许再跟 OCR 碎片
    //   （⚠️ 别拿 `Winners` 这类词判：视频预览里也有同名字幕，会假红 —— 第一版就这么栽的）
    const line = read.split('\n').find((l) => l.startsWith('图上文字：')) ?? '';
    assert.ok(/图 1：读到 35 行/.test(line), `卡上没报读到几行：${line}`);
    assert.ok(/另摘除水印 10 行/.test(line), `卡上没报摘掉几行水印（处理凭据，不许省）：${line}`);
    assert.ok(!/activity calendar|announcements|MOMCOZY/.test(line),
      `图上文字那一行里还塞着 OCR 碎片（就是 Owner 说的「丑排版」）：${line}`);
    assert.ok(/全文见报告附录/.test(line), '卡上撤了原文却没说去哪儿找 —— 那是「砍」不是「搬」');
  });

  await t('Z41b ★★ 报告附录**必须接得住全文**（搬不是砍 —— 先证明有落点）', async () => {
    const md = String(mediaReadAppendix(inboundImg()) ?? '');
    assert.ok(md.includes('#MomAndMore activity calendar'), '报告附录没有全文');
    assert.ok(md.includes('Winners') && md.includes('MOMCOZY'), '附录被截断了 —— 那就不是「搬」是「砍」');
    // 关键：附录里**必须说明它是碎片**，否则下一个人又会拿它当正文去排版
    assert.ok(/碎片|逐行|不要把它当/.test(md), '附录没说明这是 OCR 逐行碎片');
  });

  await t('Z41c ★ 视频那一侧**刻意不同**：帧文字保留带时间码的压缩预览（Owner 点名要 00:12）', async () => {
    const read = String(describeMediaRead(inboundVid()) ?? '');
    // ⚠️ 这里**不许**照图那一侧一起撤掉 —— 帧文字是成句可读的，且 Owner 点名要时间码。
    //    撤的时候 Z33a（时间码必须上卡）当场变红，那一次红得对，所以分开处理。
    assert.ok(read.includes('[00:04]') && read.includes('[00:12]'),
      `卡上丢了时间码（Owner 点名要的那一条）：${read.slice(0, 160)}`);
    assert.ok(read.includes('Eufy S1 Pro has a single layer'), '视频预览里没有任何帧文字了');
    const md = String(mediaReadAppendix(inboundVid()) ?? '');
    assert.ok(md.includes('[00:04]') && md.includes('[00:12]'),
      `报告附录的帧文字没带时间码：${md.slice(0, 160)}`);
    assert.ok(md.includes('Eufy S1 Pro has a single layer'), '附录没收到第二个帧的文字');
  });

  await t('Z41d 反向对照：没带媒材时，附录**不许凭空造一节**出来', async () => {
    assert.strictEqual(String(mediaReadAppendix({}) ?? ''), '', '没有媒材却产出了附录');
    assert.strictEqual(String(mediaReadAppendix(null) ?? ''), '', 'null 入参不许炸');
  });

  await t('Z41e 接线：报告**必须**把这一节带进正文（不接=又一处「改了但没人读」）', async () => {
    const src = fs.readFileSync(new URL('./agent/agent.mjs', import.meta.url), 'utf8');
    assert.ok(/mediaReadAppendix\(inbound\)/.test(src),
      '`renderMergedReportMd` 的调用里没有 `mediaReadAppendix(inbound)` —— 附录没接进报告');
    // 且必须真的传进去（算出来不用 = 白算）
    // ★ 2026-10-13：`renderMergedReportMd` 现在被调**两次**（投出那份 `withAppendix:false`、
    //   留底那份完整），而入参收在一个 `_args` 对象里。判据改成「附录算出来了、且**传进了
    //   那个共用的入参对象**」——写成「离调用点 1200 字内出现 mediaAppendix」会被这次重构误伤。
    const i = src.indexOf('const _args = {');
    assert.ok(i > 0, '找不到渲染报告的入参对象 `_args`（结构变了，判据要跟着走）');
    assert.ok(/mediaAppendix\s*:/.test(src.slice(i, i + 1200)),
      '算出了附录却没传给 `renderMergedReportMd`');
    // 反向对照：**留底那一份必须带附录**（投出那份不带）—— 少这一半，附录就真的没了
    assert.ok(/withAppendix:\s*false/.test(src),
      '没有渲染「投出去那一份」—— 那 Owner 要去掉的附录会照旧投上云文档');
  });

  await t('Z41f 报告渲染器真的会印这一节（纯函数直调）', async () => {
    const apx = String(mediaReadAppendix(inboundImg()) ?? '');
    const md = renderMergedReportMd({ merged: [], total: 0, state: 'REVIEW', line: 'x',
                                      question: '', mediaAppendix: apx });
    assert.ok(md.includes('#MomAndMore activity calendar'), '报告正文里没有附录那一段');
    assert.ok(/^# /m.test(md), '第一行必须仍是 H1（飞书 docs +create 靠它定标题）');
  });
}

await t('Z35 ★ 内部详情不许进正文：指纹与「我工具里没这一步」必须被判红（实测那条）', async () => {
  // Owner 2026-10-09 现场：「在吗」的回复里写着两个 PRD sha 指纹与「重拉基线那一步不在我的工具里」，
  // 而旧 internalLeak（工具名 / call_xxx / 栈 / DSML 标记）**一条都不命中** ⇒ 就这么发出去了。
  const { lintCopy } = await import('./reply-cards/registry.mjs');
  const hit = (t) => lintCopy(t).filter((h) => h.id === 'internalLeak').length;
  const REAL = '在我这儿还是**旧版指纹** 1f871b42fa909e70…，新版是 bc48e2ae893ab3e7… —— '
    + '**重拉基线那一步不在我的工具里**，所以在那之前，凡引用这份 PRD 的判断我都按旧版算。';
  assert.ok(hit(REAL) > 0, '实测那条漏出去了 —— 指纹与能力自述必须被判红');
  assert.ok(hit('重拉基线那一步不在我的工具里') > 0, '能力自述没盖住');
  // ★ **两类判据各要一条只含它的夹具** —— 上面那条同时含指纹与能力自述，
  //   所以「摘掉指纹判据」时它照样红（能力自述那条还在命中）⇒ **变异读不出指纹判据的死活**。
  //   实测过一次：摘掉指纹判据后 Z35 全绿，我一度以为断言没盖住。
  assert.ok(hit('新版指纹是 bc48e2ae893ab3e7') > 0, '指纹这一类没盖住（只含指纹的夹具）');
  assert.ok(hit('那一版是 a1b2c3d4e5f60718') > 0, '纯十六进制指纹没盖住');
  // ★ 反向对照：正经回答一条都不许误报（§2.1.1：会误报的检查器比没有更糟）
  for (const ok of ['这条站内广告文案能不能发：M6 吸奶器静音设计', '订单号 20261009123456 已登记',
                    '审核完成，共发现 3 处需人工确认。', '活动截至 2026 年 10 月 9 日 23:59']) {
    assert.strictEqual(hit(ok), 0, '误报了正经回答：' + ok);
  }
});

await t('Z36 接线：这条规则必须有一个承载它的地方（规程 + 执行点）', async () => {
  // ⚠️ 它**不在提示词里** —— 系统提示词有冻结上限 8500（`verify_cards` 的 K5），
  //   而这条规则写之前就已经贴着顶（8493/8500）。所以承载落在两处：
  //     ① 规程（给人看的判据，`agent-skills/守衡语域/SKILL.md` §2.3）
  //     ② `internalLeak` 检测器（**真的拦它的那一行**）。
  //   §2.4：上限必须有执行点 —— 执行点在检测器，不在提示词。
  const doc = fs.readFileSync(new URL('../agent-skills/守衡语域/SKILL.md', import.meta.url), 'utf8');
  assert.ok(/指纹 \/ 哈希 \/ 版本号/.test(doc), '规程里没点名「指纹」这一类');
  assert.ok(/把该跑的命令给我/.test(doc), '规程里没写「把维护侧的活派成对方待办」这个反面例');
  assert.ok(/没有折叠区可放|没有折叠区所以写进正文/.test(doc), '规程没写清「纯文本时就根本不写」');
  // 执行点必须真的在：检测器拦得住实测那条
  const { lintCopy } = await import('./reply-cards/registry.mjs');
  assert.ok(lintCopy('新版是 bc48e2ae893ab3e7…').some((h) => h.id === 'internalLeak'),
    '检测器没拦住指纹 —— 那这条规则就没有执行点了');
  // 反向对照：提示词不许为了这条规则把冻结上限顶破
  const { buildSystemPrompt } = await import('./agent/persona.mjs');
  assert.ok(buildSystemPrompt().length <= 8500, '提示词超了冻结上限（K5 会红）');
});

await t('Z42 ★ P0 命中那一路的输入不许被「短卡 / 篇幅上限」类指令改写（Owner 2026-10-12 指示恢复 16:57 格式）', async () => {
  // ── 为什么有这一条
  //   2026-10-12 17:54 另一个会话给 P0 命中那一路加了一段「短卡」指令（≤300 字、
  //   只保留结论行/模式与条款号/报告链接），19:31 生效后的第一条 P0 回复就变了样：
  //   两轨计数行 + 逐条明细 + 页脚**全没了**，换来「条款 W-1.33 / L4→L5→L6→L7 / 表行 recvx…」
  //   （两条原文都在 `PMO/logs/ws_outbound.jsonl`）。
  //   Owner 当场指示恢复 —— 那段拼接已停用（见 `agent.mjs` 原位注释）。
  //   ⚠️ 那条改动**没有踩红任何断言**，所以这一条必须补上：判据不能只活在注释里（§2.4）。
  const { runSubmissionGate, P0_SHORT_REPLY_INSTRUCTION } = await import('./agent/agent.mjs');
  const inbound = { text: '审核下这个吸奶器文案：吸奶器M9，是最好的吸奶器', imageCount: 0, videoCount: 0 };
  const r = await runSubmissionGate({
    inbound, question: inbound.text, notify: async () => {},
    // ★ 让链返回 **P0 命中**那一支 —— `p0ShortReplyBlock(res)` 只认 `res.p0_fastpath`
    chainRunner: async () => ({ answer: '【审查结论：BLOCK】占位',
                               p0_fastpath: { elapsed_ms: 48, matched_patterns: 1, rule_codes: ['H05'] } }),
    // ★ 三个注入点一个都不能漏：漏 `modelSideRunner` 会真打 LLM，漏 `mergedReportRunner`
    //   会真在飞书建云文档（§2.4.4 那个病，本仓实测踩过两次）。
    modelSideRunner: async () => ({ ok: true, findings: [] }),
    publishRunner: async () => ({ ok: true, action: 'skipped', detail: '自证桩：不碰真表' }),
    mergedReportRunner: async () => ({ ok: true, url: 'https://example.invalid/docx/STUB', detail: '自证桩' }),
    adviceRunner: async () => ({ ok: true, ms: 1, advice: {} }),
  });
  const turn = String(r.question ?? '');
  // ① 先证明**真的走到了 P0 那一支** —— 否则下面两条是恒真的空断言（本仓记过这个坑）
  assert.ok(turn.includes('P0 快路'), '这一轮没走到 P0 快路那一支 —— 下面两条会退化成恒真');
  // ② 那段短卡指令不许被拼进来
  assert.ok(!turn.includes(P0_SHORT_REPLY_INSTRUCTION), '短卡指令又被拼进来了（Owner 已指示恢复 16:57 格式）');
  // ③ 篇幅上限这一类「靠压缩求短」的指令同样不许出现 —— 短不该以丢掉卡面结构为代价
  assert.ok(!/篇幅上限|≤\s*\d+\s*字/.test(turn), '这一路的输入里不许出现篇幅上限');
  // ④ 反向对照：这条断言**不是恒真** —— 拼进来时必须能红，否则等于没写
  assert.ok(P0_SHORT_REPLY_INSTRUCTION.length > 20
            && (turn + '\n\n' + P0_SHORT_REPLY_INSTRUCTION).includes(P0_SHORT_REPLY_INSTRUCTION),
            '常量是空的 ⇒ 第②条永远不会红，等于没有断言');
});
// 汇总必须放在**所有**分组之后（2026-10-09 修：中间那两块重复的汇总+exit
// 让「第 27 组」与「第 33 组」**从没被执行过**，而合计照样印得像全绿）。
console.log(`\n═══ 合计：通过 ${pass} / 失败 ${fail} ═══`);
process.exit(fail > 0 ? 1 : 0);
