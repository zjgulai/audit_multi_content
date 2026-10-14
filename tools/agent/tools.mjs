
/**
 * tools.mjs —— 守衡的工具层
 *
 * 每个工具 = { schema, run, scope }。
 *   scope: 'read'  —— 只读，随时可调
 *          'write' —— 会对外产生副作用（发消息、改状态），需谨慎
 *
 * 设计取舍：先只给「读了能答得更好」的工具。写类工具（发消息、改文档）等业务场景
 * 明确后再放开 —— 一个会主动往群里发东西的智能体，权限必须一次一点地给。
 *
 * ★ 2026-09-22 第一次放开（委托方决定）：新增**多维表格写工具**（建表 / 改字段 /
 *   删记录），实现在 ./lark_write.mjs。触发它的是一件具体的事：
 *   李倩怡 16:02 给了落点与口径、16:06 开了编辑权限并说「请写入」，而守衡
 *   16:04 / 16:06 两次在群里答「我做不到」—— 那句对**这个文件**是真的
 *   （当时 11 个工具全是 scope:'read'），但它听起来像「飞书没给权限」，
 *   于是委托方去查控制台。真正该放开的东西一直在这张表里，不在飞书那侧。
 *
 *   ⚠️ `scope` 这个字段**只是标注，不是闸门** —— 它被 `toolNames()` 拼进
 *   系统提示的工具横幅给模型看，全仓没有任何一行拿它做准入判断。
 *   真正的执行点在 lark_write.mjs 的三条纪律：**留痕 / 回读 / 删除前快照**
 *   （每条在 lark_write.test.mjs 里都有能红的断言）。
 *   别把 `scope: 'write'` 当成「挡得住」—— 它挡不住任何东西。
 */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import crypto from 'node:crypto';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { REPO_ROOT } from './config.mjs';
import { beijingDateTime } from './timefmt.mjs';
import * as feishu from './feishu.mjs';
import * as lw from './lark_write.mjs';
import * as kb from './kb_client.mjs';
import * as reviewPublish from './review_publish.mjs';

const execFileP = promisify(execFile);

/** 运行期上下文：由 agent 在处理每条消息时注入，工具通过它感知「现在在哪个群、谁在说话」 */
export const runtimeContext = { chatId: null, chatType: null, senderName: null, senderOpenId: null, messageId: null };

const defs = [];
const register = (name, def) => defs.push({ name, ...def });

/* ─────────────────────────── 只读工具 ─────────────────────────── */

register('now', {
  scope: 'read',
  schema: {
    type: 'function',
    function: {
      name: 'now',
      description: '获取当前日期时间（北京时间）与星期。涉及「今天」「昨天」「还有几天」这类计算时必须先调用。',
      parameters: { type: 'object', properties: {}, required: [] },
    },
  },
  run: async () => {
    // 实现在 timefmt.mjs，与 recent_messages 共用同一份 —— 时间基准只要有两份实现，
    // 就一定会漂移（曾经就是 `now` 给北京时间、`recent_messages` 给 UTC，
    // 导致守衡在群里把 11:12 说成 23:12）。
    return beijingDateTime(new Date());
  },
});

register('current_chat_info', {
  scope: 'read',
  schema: {
    type: 'function',
    function: {
      name: 'current_chat_info',
      description: '获取当前所在会话的信息：群名称、群描述、成员数，以及正在跟你说话的人是谁。不确定自己在哪个群、对方是谁时调用。',
      parameters: { type: 'object', properties: {}, required: [] },
    },
  },
  run: async () => {
    const { chatId, chatType, senderName, senderOpenId } = runtimeContext;
    if (!chatId) return { error: '当前没有会话上下文' };
    const info = chatType === 'p2p' ? { name: '（私聊）' } : await feishu.getChatInfo(chatId);
    return {
      chat_type: chatType === 'p2p' ? '私聊' : '群聊',
      chat_id: chatId,
      chat_name: info?.name ?? null,
      chat_description: info?.description ?? null,
      member_count: info?.memberCount ?? null,
      you_are_talking_to: senderName ?? '(未知)',
      their_open_id: senderOpenId ?? null,
      ...(info?.error ? { error: info.error } : {}),
    };
  },
});

register('list_chat_members', {
  scope: 'read',
  schema: {
    type: 'function',
    function: {
      name: 'list_chat_members',
      description: '列出当前群/会话的成员。需要知道群里有哪些人时调用。',
      parameters: { type: 'object', properties: {}, required: [] },
    },
  },
  run: async () => {
    const { chatId } = runtimeContext;
    if (!chatId) return { error: '当前没有会话上下文' };
    const m = await feishu.listMembers(chatId);
    if (m?.error) return m;
    return { count: m.length, members: m };
  },
});

register('recent_messages', {
  scope: 'read',
  schema: {
    type: 'function',
    function: {
      name: 'recent_messages',
      description: '读取当前群/会话最近的聊天记录，每条带「谁发的」和北京时间。对方提到「刚才」「上面说的」而你不清楚指什么时调用。注意三点：(1) 这里读到的历史包含你自己发过的消息；(2) 最多只能看到最近 50 条，更早的看不到，返回里的 window 字段会告诉你有没有顶到上限；(3) 被撤回的消息只有时间没有内容，撤回了就取不回原文。',
      parameters: {
        type: 'object',
        properties: { limit: { type: 'integer', description: '要读多少条，默认 20，最多 50' } },
        required: [],
      },
    },
  },
  run: async ({ limit = 20 } = {}) => {
    const { chatId } = runtimeContext;
    if (!chatId) return { error: '当前没有会话上下文' };
    const n = Math.max(1, Math.min(50, Number(limit) || 20));
    const msgs = await feishu.listRecentMessages(chatId, n);
    if (msgs?.error) return msgs;
    return {
      count: msgs.length,
      // 窗口边界由 feishu 层给出，不在这里重算 —— 边界是事实，不是推断。
      // 有了它，守衡说「第一次」时才知道自己说的是「本窗口内的第一次」。
      window: msgs.window,
      messages: msgs.map((m) => ({
        at: m.at,
        // 用 feishu 解析好的发送者。原来这里写死 `'用户'`，把接口本来给出的
        // sender.id 丢掉了 —— 守衡于是一致地说「我分辨不出哪条是谁发的」，
        // 而数据一直都在。不要把「有身份的信息」压成「无身份的占位符」。
        from: m.from,
        senderOpenId: m.senderOpenId ?? undefined,
        // 撤回的消息正文取不回，单独标出来。不然它和「一条短消息」长得一样。
        ...(m.recalled ? { recalled: true } : {}),
        text: m.text?.slice(0, 500),
      })),
    };
  },
});

register('lookup_user', {
  scope: 'read',
  schema: {
    type: 'function',
    function: {
      name: 'lookup_user',
      description: '用 open_id 查这个人的显示名。优先在当前群成员里找，找不到才查通讯录。',
      parameters: {
        type: 'object',
        properties: { open_id: { type: 'string', description: '用户的 open_id，形如 ou_xxx' } },
        required: ['open_id'],
      },
    },
  },
  run: async ({ open_id }) => {
    // 带上当前群的 chatId：同群的人走群成员列表即可命中，不需要通讯录权限
    const chatId = runtimeContext.chatId ?? null;
    const { name, source, reason } = await feishu.getUserName(open_id, chatId);
    if (name) return { open_id, name, source };
    return {
      open_id,
      error: '查不到该用户的显示名',
      reason,
      hint: '如实说明你知道对方 open_id 但拿不到姓名，不要猜测或编造称呼。',
    };
  },
});

register('list_workspace', {
  scope: 'read',
  schema: {
    type: 'function',
    function: {
      name: 'list_workspace',
      description: '列出守衡所在工作区的顶层目录与文件。对方问「你都能看到什么」「项目里有什么」时调用。' +
                   '★ 特别提醒：**上游飞书文档的逐字副本就在 `PRD/feishu/` 下**' +
                   '（`内容审查Agent-PRD-v1.0.md`、`美国市场内容治理项目-一页纸计划书.md`、`索引-v1.json`）。' +
                   '别人发来一个飞书文档链接时，先 `list_files` / `search_workspace` 在工作区里找它的副本，' +
                   '**再**决定要不要说「读不到」。',
      parameters: { type: 'object', properties: {}, required: [] },
    },
  },
  run: async () => {
    const entries = fs.readdirSync(REPO_ROOT, { withFileTypes: true })
      .filter((e) => !e.name.startsWith('.'))
      .map((e) => ({ name: e.name, type: e.isDirectory() ? 'dir' : 'file' }));
    return { root: REPO_ROOT, entries };
  },
});

register('read_text_file', {
  scope: 'read',
  schema: {
    type: 'function',
    function: {
      name: 'read_text_file',
      description: '读取工作区内一个文本文件的内容。路径必须是工作区内的相对路径。文件很长时只返回开头部分。',
      parameters: {
        type: 'object',
        properties: {
          rel_path: { type: 'string', description: '相对工作区根目录的路径，例如 PMO/守衡-链路打通确认.md' },
          max_bytes: { type: 'integer', description: '最多读多少字节，默认 20000' },
        },
        required: ['rel_path'],
      },
    },
  },
  run: async ({ rel_path, max_bytes = 20000 }) => {
    const abs = path.resolve(REPO_ROOT, rel_path);
    // 路径逃逸防护：解析后必须仍在工作区内
    if (!abs.startsWith(REPO_ROOT + path.sep) && abs !== REPO_ROOT) {
      return { error: `拒绝访问工作区之外的路径：${rel_path}` };
    }
    if (!fs.existsSync(abs)) return { error: `文件不存在：${rel_path}` };
    const st = fs.statSync(abs);
    if (st.isDirectory()) return { error: `${rel_path} 是目录，不是文件` };
    const cap = Math.max(100, Math.min(200_000, Number(max_bytes) || 20000));
    const buf = fs.readFileSync(abs);
    const slice = buf.subarray(0, cap).toString('utf8');
    return { rel_path, bytes: st.size, truncated: st.size > cap, content: slice };
  },
});

register('list_files', {
  scope: 'read',
  schema: {
    type: 'function',
    function: {
      name: 'list_files',
      description: '按文件名模式在指定目录下查找文件（大小写不敏感的模糊匹配）。想找某个文件但不确定路径时用。',
      parameters: {
        type: 'object',
        properties: {
          pattern: { type: 'string', description: '文件名包含的关键词，例如 "审核" 或 ".md"' },
          sub_dir: { type: 'string', description: '在哪个子目录里找，默认整个工作区' },
          limit: { type: 'integer', description: '最多返回多少条，默认 40' },
        },
        required: ['pattern'],
      },
    },
  },
  run: async ({ pattern, sub_dir = '', limit = 40 }) => {
    const base = sub_dir ? path.resolve(REPO_ROOT, sub_dir) : REPO_ROOT;
    if (!base.startsWith(REPO_ROOT)) return { error: '拒绝访问工作区之外的路径' };
    const needle = String(pattern).toLowerCase();
    const hits = [];
    const walk = (dir, depth) => {
      if (depth > 6 || hits.length >= limit) return;
      let ents = [];
      try { ents = fs.readdirSync(dir, { withFileTypes: true }); } catch { return; }
      for (const e of ents) {
        if (hits.length >= limit) return;
        if (e.name.startsWith('.') || e.name === 'node_modules') continue;
        const full = path.join(dir, e.name);
        if (e.isDirectory()) walk(full, depth + 1);
        else if (e.name.toLowerCase().includes(needle)) hits.push(path.relative(REPO_ROOT, full));
      }
    };
    walk(base, 0);
    return { pattern, matches: hits.length, files: hits };
  },
});

/* ── 全工作区文本检索：它存在的理由就是「给得出分母」 ─────────────────────────
 *
 * 它替掉的是 `grep -rl <词> .` 那条路（2026-09-22 事故，见下一段注释）。三点不同，
 * 每一点都对应一次真实误判：
 *   ① **在 Node 里走 fs，不起子进程** —— 没有 15 秒超时，也就没有被杀掉之后
 *      留下一片空白、被读成「没命中」的可能；
 *   ② **报分母**：`searched_files` / `skipped` / `stopped_early` 必须一起看 ——
 *      「0 命中」只有在 `stopped_early === false` 且 `searched_files > 0` 时才成立
 *      （AGENTS.md §2.4.1：否定结论的输入不能只是「我采的那条通道里没有」）；
 *   ③ 自己剪枝 node_modules / .git / skills 这些大目录，不靠调用方记得。
 */

const SEARCH_SKIP_DIRS = new Set([
  'node_modules', '.git', '.ua', '.vendor', 'dist', 'build', 'skills', '__pycache__',
]);
const SEARCH_TEXT_EXT = new Set([
  '.md', '.json', '.jsonl', '.mjs', '.js', '.ts', '.py', '.sh', '.txt',
  '.csv', '.yml', '.yaml', '.toml', '.plist', '.html', '.css', '.log',
]);

register('search_workspace', {
  scope: 'read',
  schema: {
    type: 'function',
    function: {
      name: 'search_workspace',
      description: '在守衡的工作区里做**全文检索**（不联网、不起子进程、自己剪掉大目录）。' +
                   '想问「某个词/某个 token 在不在工作区里」时用这个，**不要用 `grep -r` 扫全仓**。\n\n' +
                   '★ 返回值必须连着三个数一起读：`searched_files`（真扫了几个文件）、' +
                   '`skipped`、`stopped_early`。**只有当 `stopped_early === false` 且 ' +
                   '`searched_files > 0` 时，「0 命中」才是一句能说的话**；' +
                   '否则那是「未测」，不许说成「没有」。',
      parameters: {
        type: 'object',
        properties: {
          keyword: { type: 'string', description: '要找的文字，区分大小写，按原样子串匹配' },
          sub_dir: { type: 'string', description: '只在哪个子目录里找，例如 PRD 或 PMO；默认整个工作区' },
          limit: { type: 'integer', description: '最多返回多少个命中文件，默认 30' },
          max_files: { type: 'integer', description: '最多扫多少个文件，默认 5000。到顶会明说「没扫完」（不是「没找到」）' },
        },
        required: ['keyword'],
      },
    },
  },
  run: async ({ keyword, sub_dir = '', limit = 30, max_files = 5000 }) => {
    const kw = String(keyword ?? '');
    if (!kw) {
      return { keyword: kw, status: 'untested',
               note: '没给关键词 —— 未测，不是「没有」。' };
    }
    const base = sub_dir ? path.resolve(REPO_ROOT, sub_dir) : REPO_ROOT;
    if (base !== REPO_ROOT && !base.startsWith(REPO_ROOT + path.sep)) {
      return { keyword: kw, status: 'rejected', note: '拒绝访问工作区之外的路径（未测）。' };
    }
    const MAX_FILES = Math.max(1, Math.min(20000, Number(max_files) || 5000));
    const MAX_FILE_BYTES = 2_000_000;
    let searched = 0, skipped = 0, bytes = 0, stoppedEarly = false, matchesCapped = false;
    const hits = [];

    const walk = (dir, depth) => {
      if (stoppedEarly || depth > 8) return;
      let ents = [];
      try { ents = fs.readdirSync(dir, { withFileTypes: true }); } catch { skipped++; return; }
      for (const e of ents) {
        if (stoppedEarly) return;
        const full = path.join(dir, e.name);
        if (e.isDirectory()) {
          if (e.name.startsWith('.') || SEARCH_SKIP_DIRS.has(e.name)) { skipped++; continue; }
          walk(full, depth + 1);
          continue;
        }
        if (!e.isFile() || !SEARCH_TEXT_EXT.has(path.extname(e.name).toLowerCase())) { skipped++; continue; }
        if (searched >= MAX_FILES) { stoppedEarly = true; return; }
        let st, text;
        try {
          st = fs.statSync(full);
          if (st.size > MAX_FILE_BYTES) { skipped++; continue; }
          text = fs.readFileSync(full, 'utf8');
        } catch { skipped++; continue; }
        if (text.includes('\u0000')) { skipped++; continue; }   // 其实是二进制
        searched++; bytes += st.size;
        if (!text.includes(kw)) continue;
        const lines = [];
        text.split('\n').forEach((ln, i) => {
          if (lines.length < 3 && ln.includes(kw)) lines.push({ line: i + 1, text: ln.trim().slice(0, 200) });
        });
        if (hits.length < limit) hits.push({ file: path.relative(REPO_ROOT, full), lines });
        else matchesCapped = true;
      }
    };
    walk(base, 0);

    const denom = `已扫 ${searched} 个文件、跳过 ${skipped} 个（大目录 / 二进制 / 超大文件）`;
    return {
      keyword: kw, status: 'ok',
      searched_files: searched, skipped, bytes_scanned: bytes,
      stopped_early: stoppedEarly, matches_capped: matchesCapped,
      matches: hits.length, files: hits,
      note: stoppedEarly
        ? `⚠️ 这次**没扫完**（到 ${MAX_FILES} 个文件上限就停了，还有没走到的地方）：${denom}。`
          + `所以「没找到」在这半张图上不成立 —— 这是**未测**，不许说成「0 命中」。`
          + `换一个更小的 sub_dir 重试。`
        : `${denom}。`
          + (hits.length === 0
              ? '**0 命中 —— 这一句现在有分母撑着**（范围走完了，不是被截断的）。'
              : `命中 ${hits.length} 个文件${matchesCapped ? '（只列了前若干个，实际不止）' : ''}。`),
    };
  },
});

/* ── 只读 shell：状态的措辞是硬的，别改回去 ─────────────────────────────────
 *
 * ★ 2026-09-22 事故（这一整段的结构就是为它改的）：
 *   守衡执行 `grep -rl NB55wAq8liEOdKkquL2cgtPEnmg .` —— 全仓递归，含 node_modules/、
 *   .git/、skills/ 下 777 个压缩包，**15 秒被 timeout 杀掉**。它拿到的返回体是：
 *       { error: "Command failed: bash -lc grep -rl ...", stdout: "" }
 *   **error 字段是满的，它只读了 stdout 是空的**，于是说「我用这个 token 在整个工作区
 *   搜了一遍，0 命中」—— 而那个 token 就在工作区两个文件里（`PRD/feishu/索引-v1.json`、
 *   `PRD/PRD差异对照-20260921.md`）。
 *
 *   形状与 AGENTS.md §2.2 第 5 条（macOS 没有 `timeout`，空输出 + rc=127 被读成
 *   「0 命中」）**完全相同**，只是机制从「命令不存在」换成了「命令被超时杀掉」。
 *
 * ★ 契约（三条缺一不可）：
 *   ① 每次返回都带 `status`：`ok` / `rejected` / `timeout` / `failed`；
 *   ② **status !== 'ok' 时，返回体里根本没有 `stdout` 这个键** ——
 *      没有空字符串可读，就不可能被读成「扫完了、没命中」；
 *   ③ status !== 'ok' 时带 `note`，把「未测」两个字直接写出来。
 *   ④ 病态的递归扫描**在跑之前**就被挡掉（`scanGuard`）——
 *      把超时标成「未测」只是止血，**这条命令本来就不该跑**。
 */

/** 递归扫描的目标里出现这些，就是「会扫穿整个仓库」 */
const HEAVY_TARGET = /^(\.|\.\/|\/|node_modules|\.git|skills|\.ua|dist|build|\.vendor)(\/|$)/;

/**
 * 递归扫描护栏 → 返回拒绝理由，或 null 表示放行。
 *
 * 判据**只看目标**，不看 `--include`：`--include` 过滤的是文件，不剪枝目录遍历，
 * 所以 `grep -rn X --include=*.md .` 一样会扫穿 node_modules。
 */
/* ─────────────────── 凭据路径：一律不许读 ─────────────────── */

/**
 * ★ 2026-09-22 加。**它堵的是一个已经被说出口的能力边界。**
 *
 * 起因：守衡自己对外承认过一句话 ——
 *   「我读得到那个凭据文件但不输出其内容 —— **这是策略边界，不是能力边界**。」
 * 那句话是诚实的，也正是问题：`run_readonly_command` 的白名单放行 `cat`，
 * 于是 `cat ~/.dsh/credentials/*.json` **没有任何一行代码在拦**，
 * 挡住它的只有模型的当场判断。§2.4 点名的那个病，长在凭据上。
 *
 * ── 为什么判据是「指得出对象的路径」，而不是模糊文件名匹配
 *
 * 第一版我打算写 `/(secret|token|credential|key)/i` 扫文件名。**实测否掉了**：
 * 仓里有一个 `research/governance/_evidence/R2/_tools/pylibs/pycparser/ply/ctokens.py` ——
 * 它含 `token`，但它是 pycparser 的词法表。一个会误报的检查器比没有检查器更糟
 * （§2.1.1），尤其当它拦的是守衡**自己证据层**里的文件。
 *
 * 所以名单是**逐个点名**的，每一条都指得出这台机器上的真实对象：
 *   `~/.dsh/credentials/shouheng-lark.json`            飞书应用密钥
 *   `~/.dsh/credentials/tencent-cloud-zhoujian-secretkey.csv`  腾讯云密钥
 *   `~/.dsh/.credentials.yaml`                         DSH 凭据
 *   `~/.ssh/`                                         私钥
 *
 * ── 一个必须写下来的**已知边界**（不许当成已经堵死）
 *
 * `read_text_file` / `list_files` / `search_workspace` 三个通道**已经**被
 * `REPO_ROOT` 前缀断言挡住了，而上面这些落点全在仓外 —— 所以真正需要这道闸门的
 * **只有 `run_readonly_command` 一条**。这个结论**不是读代码读出来的，是采出来的**：
 * `tools/agent/secret_path.test.mjs` 对四条通道各喂一个仓外凭据路径，
 * 断言**四条全部拒绝**（一条活着不给另一条作证 —— §2.4.1 第 4 行）。
 */
const HOME_DIR = os.homedir();

/** 不许进入的目录/文件（**逐个点名，不做模糊匹配**） */
const SECRET_PATHS = [
  path.join(HOME_DIR, '.dsh', 'credentials'),
  path.join(HOME_DIR, '.dsh', '.credentials.yaml'),
  path.join(HOME_DIR, '.ssh'),
  path.join(HOME_DIR, '.aws'),
  path.join(HOME_DIR, '.config', 'gh'),
];

/** 按**文件名**拦的（这些名字本身就是凭据，放哪都一样） */
const SECRET_BASENAMES = new Set([
  '.credentials.yaml', '.credentials.yml', '.env',
  '.netrc', '.git-credentials', '.npmrc', '.pypirc',
  'id_rsa', 'id_ed25519', 'id_ecdsa', 'id_dsa',
]);

/**
 * 一个 token 是不是指向凭据。命中返回「命中的那个对象」，否则 null。
 *
 * `$HOME` / 反引号 / `;` 这些在 `run_readonly_command` 里**已经被元字符检查挡掉**，
 * 所以这里只需要处理 `~`。通配符（`cred*`）取**第一颗 `*` 之前**那段当静态前缀，
 * 并要求「静态前缀与某个禁入目录**互为前缀**」—— 这样 `~/.dsh/cred*` 也会被拦。
 */
export function secretPathHit(token) {
  const raw = String(token ?? '').trim().replace(/^["']|["',]+$/g, '');
  if (!raw) return null;
  const expanded = raw.startsWith('~/') ? path.join(HOME_DIR, raw.slice(2))
    : raw === '~' ? HOME_DIR
    : raw;
  const globAt = expanded.search(/[*?[]/);
  const staticPart = globAt >= 0 ? expanded.slice(0, globAt) : expanded;
  const abs = path.resolve(REPO_ROOT, staticPart);
  for (const p of SECRET_PATHS) {
    const under = abs === p || abs.startsWith(p + path.sep);
    // 通配符那一侧：`staticPrefix*` 能匹配到的**任何**路径，都是 `startsWith(staticPart)` 的路径。
    // 所以「这颗通配符有没有可能落进禁入目录」= 「禁入目录是否以静态前缀开头」。
    // ★ 第一版我写成 `p.startsWith(abs + path.sep)`，**当场被 A7 抓到**：
    //   前缀 `…/.dsh/cred` 加一个斜杠就成了 `…/.dsh/cred/`，而 `credentials` 不以它开头 ——
    //   于是一个明明会被 glob 展开到凭据目录的写法被判成安全。**判据比要拦的东西弱了一格。**
    const couldGlobIn = globAt >= 0 && p.startsWith(abs);
    if (under || couldGlobIn) return `${p}${path.sep}`;
  }
  if (globAt < 0 && SECRET_BASENAMES.has(path.basename(abs))) return path.basename(abs);
  return null;
}

/** 扫整条命令的每个 token。命中就返回一句要发回去的拒绝话术。 */
function secretGuard(cmd) {
  for (const token of String(cmd ?? '').split(/\s+/)) {
    const hit = secretPathHit(token);
    if (hit) {
      return '🔒 已拒绝：这条命令指向**凭据文件**（' + hit + '）。\n'
        + '这是**策略边界**，不是「我读不到」—— 白名单主动挡住了它，所以本次结论是「未测」，'
        + '不是「文件不存在」，也不是「里面没有」。\n'
        + '要读的话走另一条路：把**非凭据**的内容放到工作区或飞书文档里。';
    }
  }
  return null;
}

function scanGuard(cmd) {
  const parts = cmd.split(/\s+/).filter(Boolean);
  const [bin, ...rest] = parts;
  const flags = rest.filter((p) => p.startsWith('-'));
  const bare = rest.filter((p) => !p.startsWith('-'));

  const isGrep = bin === 'grep' || bin === 'rg';
  const isFind = bin === 'find';
  const isLs = bin === 'ls';
  if (!isGrep && !isFind && !isLs) return null;

  const recursive = bin === 'rg' || isLs
    ? flags.some((f) => /^-[a-zA-Z]*[rR]/.test(f) || f === '--recursive')
    : flags.some((f) => /^-[a-zA-Z]*[rR]/.test(f) || f === '--recursive');
  const bounded = flags.some((f) => /^-maxdepth/.test(f));

  // grep/rg 的第一个非选项是 pattern，其余才是路径；find / ls 的非选项全是路径
  const targets = isGrep ? bare.slice(1) : bare;
  if (isLs && !recursive) return null;
  if (!recursive && !isFind) return null;

  const unbounded = targets.length === 0 || targets.some((t) => HEAVY_TARGET.test(t));
  if (!unbounded || bounded) return null;

  return '⚠️ 已拒绝：这条命令会递归整个工作区（含 node_modules/、.git/、'
       + 'skills/ 下 777 个压缩包），15 秒必然超时 —— **而超时后 stdout 是空的，'
       + '空输出不等于没命中。** 改用下面任一种（都能给得出「扫了多少」这个分母）：\n'
       + '  · `search_workspace` —— 专为「这段文字在不在工作区」造的，自己限范围、报分母；\n'
       + '  · 点名子目录：`grep -rn \'关键词\' PMO PRD tools research`；\n'
       + '  · `find <子目录> -maxdepth 3 -name \'*.md\'`。';
}

register('run_readonly_command', {
  scope: 'read',
  schema: {
    type: 'function',
    function: {
      name: 'run_readonly_command',
      description: '在工作区执行一条**只读** shell 命令并返回输出（例如 git log、wc -l、grep 统计）。' +
                   '只允许白名单里的只读命令；任何写操作、删除、安装、网络请求都会被拒绝。\n\n' +
                   '★ 读返回值的规矩，别搞错：**只有 `status === "ok"` 且 `stdout` 为空，' +
                   '才是「命令跑完了、没有命中」。** 其它 status 下一律**没有 stdout 字段**，' +
                   '那是「我没测到」，不是「0 命中」—— 请照 `note` 里的提示换一条命令重试，' +
                   '**不要拿这个结果去下否定结论。**',
      parameters: {
        type: 'object',
        properties: { command: { type: 'string', description: '要执行的命令，例如 "git log --oneline -5"' } },
        required: ['command'],
      },
    },
  },
  run: async ({ command }) => {
    // 白名单：只读命令前缀。宁可少给，不要给错。
    const ALLOW = /^(git\s+(log|status|diff|show|branch|remote|tag)|ls|cat|head|tail|wc|grep|rg|find|file|stat|du|df|date|pwd|echo|node\s+--version|npm\s+ls|python3?\s+--version|python3?\s+tools\/lark_find\.py\s+(search|read|readdoc|tables|fields|records|wiki))\b/;
    const cmd = String(command ?? '').trim();
    if (!ALLOW.test(cmd)) {
      return { command: cmd, status: 'rejected',
               error: `命令不在只读白名单内，已拒绝：${cmd.slice(0, 80)}`,
               note: '白名单以外的东西我没有执行过 —— 所以对你问的事，'
                   + '这次的答案是「未测」，不是「没有」。' };
    }
    if (/[;&|><`$]/.test(cmd)) {
      return { command: cmd, status: 'rejected',
               error: '命令含管道/重定向/命令替换等元字符，已拒绝',
               note: '未执行 —— 这次的答案是「未测」。' };
    }
    const guard = scanGuard(cmd);
    if (guard) return { command: cmd, status: 'rejected', error: guard, note: guard };

    // ★ 凭据路径：**在 scanGuard 之后、execFile 之前**，而且与它分开写 ——
    //   两条规则拦的是完全不同的东西（一条怕超时，一条怕泄漏），混在一个函数里
    //   会让两边都难读，也会让「哪条规则红了」说不清。
    const secret = secretGuard(cmd);
    if (secret) return { command: cmd, status: 'rejected', error: secret, note: secret };

    // ★ 测试缝：超时那条路必须能被真跑一遍，否则它只是「构造上应该对」。
    //   生产不设这个环境变量，就是 15 秒。
    const budget = Number(process.env.SHOUHENG_RO_TIMEOUT_MS) > 0
      ? Number(process.env.SHOUHENG_RO_TIMEOUT_MS) : 15_000;
    try {
      const { stdout, stderr } = await execFileP('bash', ['-lc', cmd],
        { cwd: REPO_ROOT, timeout: budget, maxBuffer: 1 << 20 });
      return { command: cmd, status: 'ok', stdout: stdout.slice(0, 8000), stderr: stderr.slice(0, 2000) };
    } catch (e) {
      // 超时被 SIGTERM 杀掉 / 输出超过 maxBuffer —— 两种都**没有**完整输出
      const killed = e?.killed === true || e?.signal != null;
      const overflow = e?.code === 'ERR_CHILD_PROCESS_STDIO_MAXBUFFER';
      const why = killed ? `命令在 ${Math.round(budget / 1000)} 秒内没跑完，已被杀掉`
                : overflow ? `命令输出超过 1MB 上限，已被截断`
                : `命令非零退出：${String(e?.message ?? e).slice(0, 300)}`;
      // ★ 故意**不带 stdout** —— 见本段顶部契约 ②
      return {
        command: cmd, status: killed ? 'timeout' : 'failed',
        error: why,
        bytes_captured: String(e?.stdout ?? '').length,
        note: `⚠️ 未测：${why}。**这次没有可用的输出，所以「有没有命中」我答不了 —— `
            + `这不是「0 命中」，也不是「没有」。** 请换一条范围更小的命令重试，`
            + `或改用 search_workspace（它会报扫了多少个文件）。`,
        stderr: String(e?.stderr ?? '').slice(0, 1500),
      };
    }
  },
});

/* ─────────────────────────── 内容合规判定（只读工具之一）─────────────────────────── */

const JUDGE_PY = path.join(REPO_ROOT, 'research', 'governance', 'skeleton', 'judge.py');

register('judge_copy', {
  // ★ scope 定为 read 的理由必须写下来，否则下一个人会以为是标错了：
  //   本工具不碰任何业务数据 —— 不改记录状态、不发消息、不写飞书。
  //   它唯一产生的持久副作用是往本地追加一条**回执**（append-only 的 jsonl），
  //   而那条回执是 ADR-0005 约束 5 强制要求的：「没有 receipt 的判定不算发生过」。
  //   所以「写回执」不是副作用，是这个工具的**定义的一部分**；关掉它，判定就不存在。
  scope: 'read',
  schema: {
    type: 'function',
    function: {
      name: 'judge_copy',
      description:
        '对一段广告文案做内容合规判定。返回：判定档位、命中的规则编号、命中的**原文位置与片段**、' +
        '降级/放行证据、规则与词表版本、边界声明（这条判定判断不了什么）、以及处置层。\n' +
        '什么时候用：有人贴一段文案问「这个能不能发」「有没有问题」「判一下」。\n' +
        '★ 四条必须照实转述的限制，不要简化掉：\n' +
        '(1) 结论是**建议**，不是决定。工具只补证据，不替人过门 —— 你不能因为返回了 auto_pass 就说「已通过」。\n' +
        '(2) 返回 catch_all（零命中）**不等于合规**，含义是「规则库没有覆盖它」。必须转人工。\n' +
        '(3) 每次都读 boundary_statement.unknowns，那里写的是本判定的覆盖边界；' +
        '通常包含「不按品线过滤」「部分守卫词未接线」「只看文本不看图片视频」。\n' +
        '(4) 回执里的 `unconfirmed_notice` 不为 null 时**必须转述出去** —— 它说的是' +
        '「这次引用的外部标准还没经过法务确认，所以这是研究结论、不是法务裁定」。' +
        '62 条外部标准今天**全部**是研究稿，所以这句话现在每次都会出现；' +
        '省掉它，一次研究就会被读成一次法务裁定（Q22 要防的正是这个）。' +
        '回执里还带 `evidence_ref`（依据《外部标准库》第几条、可点开的链接）与 `ratified`。\n' +
        '每次调用都会留下一条回执（run_id），可以在返回里引用它。',
      parameters: {
        type: 'object',
        properties: {
          text: { type: 'string', description: '要判定的文案原文（Primary Text 与 Headline 拼起来即可）。必须逐字传入，不要改写或翻译。' },
          product_line: { type: 'string', description: '品线，例如「吸奶器」。注意：当前规则库没有品线字段，它只进回执，不改变判定。' },
          locale: { type: 'string', description: '文案语种代码，例如 en / zh / de / fr / es。非 en/zh 时工具会在边界声明里提示词表覆盖不均。' },
          platform: { type: 'string', description: '投放平台，例如 Meta / TikTok。' },
          ad_id: { type: 'string', description: '外部广告 ID（如果是在审某条已有记录）。' },
        },
        required: ['text'],
      },
    },
  },
  run: async ({ text, product_line, locale, platform, ad_id } = {}) => {
    const body = String(text ?? '');
    if (!body.trim()) return { error: '文案为空，无法判定' };
    const tmp = path.join(
      os.tmpdir(),
      `judge-${process.pid}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}.txt`,
    );
    try {
      // 走临时文件而不是 --text：文案可能很长（落地页正文），也可能含引号与换行。
      // 走 argv 会同时碰到长度上限和转义问题，走文件两个都没有。
      fs.writeFileSync(tmp, body, 'utf8');
      const args = [JUDGE_PY, '--text-file', tmp, '--json', '--brief', '--receipt',
                    '--origin', 'shouheng'];
      if (product_line) args.push('--product-line', String(product_line));
      if (locale)       args.push('--locale', String(locale));
      if (platform)     args.push('--platform', String(platform));
      if (ad_id)        args.push('--ad-id', String(ad_id));
      const { stdout } = await execFileP('python3', args, {
        cwd: REPO_ROOT, timeout: 30_000, maxBuffer: 1 << 24,
      });
      const r = JSON.parse(stdout);
      // 引擎的硬断言（词表通道不变量 / 主题树漂移）失败时是 exit 2/3 且带 stderr，
      // 那种情况下 stdout 不是 JSON，上面的 JSON.parse 会抛，由 executeTool 兜住。
      return r;
    } catch (e) {
      const stderr = String(e.stderr ?? '').trim();
      return {
        error: `判定引擎执行失败：${e.message}`,
        ...(stderr ? { stderr: stderr.slice(0, 2000) } : {}),
        ...(e.code === 2 || e.code === 3
          ? { hint: '这是引擎的使用点硬断言（词表通道不变量 / 主题树校验）失败，不是你的输入问题。' +
                  '按 ADR-0008/0009，此时**本次评测结论不可用**，不要去猜判定结果。' }
          : {}),
      };
    } finally {
      try { fs.unlinkSync(tmp); } catch { /* 临时文件清理失败不该影响判定结果 */ }
    }
  },
});

/* ─────────────────── 多维表格：读（2026-09-22 加）─────────────────── */

/** app_token 从哪来 —— 每个写工具的 description 都要重复说一遍，因为这个参数
 *  是模型最容易编的东西（编出来的 token 会得到 404，而不是「你没权限」）。 */
const TOKEN_HINT =
  'app_token 从飞书链接里取：`https://xxx.feishu.cn/base/<app_token>?table=<table_id>`。' +
  '不确定有哪些 Base 时先调 lark_base_known。**不要凭印象编 token** —— 编出来的会 404。';

const TBL_HINT = 'table 可以给**表名**（如「规则库」），也可以给 table_id（tbl 开头）。给错名字会返回该 Base 里实际有哪些表。';

register('lark_base_known', {
  scope: 'read',
  schema: {
    type: 'function',
    function: {
      name: 'lark_base_known',
      description: '列出我们记录过的业务 Base（名称 + app_token + 用途）。对方只说「规则库」而没给链接时，先调这个。',
      parameters: { type: 'object', properties: {}, required: [] },
    },
  },
  run: async () => ({ bases: lw.KNOWN_BASES, note: '这里只有我们记过的。对方给了别的链接就用链接里的 token。' }),
});

register('lark_base_tables', {
  scope: 'read',
  schema: {
    type: 'function',
    function: {
      name: 'lark_base_tables',
      description: `列出某个 Base 里的所有数据表及各自的记录数。\n${TOKEN_HINT}`,
      parameters: { type: 'object', properties: { app_token: { type: 'string' } }, required: ['app_token'] },
    },
  },
  run: async ({ app_token }) => lw.listTables(app_token),
});

register('lark_base_fields', {
  scope: 'read',
  schema: {
    type: 'function',
    function: {
      name: 'lark_base_fields',
      description: `列出某张表的字段（列）定义：名称、类型、单选/多选的选项。\n写记录前**必须先看这个**，否则字段名对不上会静默写空。\n${TOKEN_HINT}\n${TBL_HINT}`,
      parameters: {
        type: 'object',
        properties: { app_token: { type: 'string' }, table: { type: 'string' } },
        required: ['app_token', 'table'],
      },
    },
  },
  run: async ({ app_token, table }) => lw.listFields(app_token, table),
});

register('lark_base_records', {
  scope: 'read',
  schema: {
    type: 'function',
    function: {
      name: 'lark_base_records',
      description: `读某张表的记录（默认 20 条，每次最多 500 条）。\n${TOKEN_HINT}\n${TBL_HINT}`,
      parameters: {
        type: 'object',
        properties: {
          app_token: { type: 'string' }, table: { type: 'string' },
          limit: { type: 'number', description: '要读多少条，默认 20，上限 500' },
          page_token: { type: 'string', description: '翻页游标（上一页返回的）' },
        },
        required: ['app_token', 'table'],
      },
    },
  },
  run: async ({ app_token, table, limit, page_token }) =>
    lw.listRecords(app_token, table, { limit, pageToken: page_token }),
});

/* ─────────────────── 多维表格：写（2026-09-22 委托方决定放开）─────────────────── */

/**
 * 写工具的 description 里有三段是**必须**转述的（写在这里、也在 lark_write.test.mjs 里断言过）：
 *   · 结果里有 readback 字段：consistent / mismatch / untested
 *   · **untested 和 mismatch 都不许说成「做好了」** —— 照实说「我没验成」
 *   · 结果里 record_ids 要留着，因为那是「下一步改哪条」的唯一凭据
 * 原因见 AGENTS.md §2.4.2：这个仓库今天刚发过一条把「字节变了」说成「上游改了」的假警报。
 */
const WRITE_HINT =
  '\n★ 返回值里一定有 `readback`：`consistent`（写进去并读回来比对一致）/ ' +
  '`mismatch`（读回来对不上）/ `untested`（回读失败，**没验成**）。\n' +
  '`mismatch` 和 `untested` **都不许说成「做好了」** —— 照实说哪一条没对上、或者"我没验成"。\n' +
  '返回值里还有 `ledger`（有没有留痕）与 `ledger_path`。留痕失败也要说出来。';

/**
 * 删除类工具的专用说明（2026-09-22 委托方定「两段式」后加）。
 * ★ 这里写的不是建议，是**代码已经这么做了**：`delete*` 三个函数在没带 `confirmed`
 *   时一律走 `proposeDelete()`，**一个删除请求都不发**。说明与行为的对应关系
 *   由 lark_write.test.mjs 的 D 段断言守着。
 */
const PROPOSE_HINT =
  '\n★ **它只提议、不执行。** 返回 `will`（一句人话，说明将要删掉什么）与 `pending: true`。\n' +
  '你要做的只有一件：**把 `will` 那句原样发出去**，然后等。\n' +
  '对方在**下一条消息**里明确确认之后，才调 `lark_base_confirm_delete`。\n' +
  '⚠️ 不要在同一次回答里既提议又确认 —— 确认只有在**另一条消息**里才算数，\n' +
  '同一条消息自我确认会被拒（`same_message`），而且那等于把两段式白做了。';

register('lark_base_create_table', {
  scope: 'write',
  schema: {
    type: 'function',
    function: {
      name: 'lark_base_create_table',
      description:
        '在 Base 里新建一张数据表。\n' +
        '★ 该 Base 里已有同名表时会**直接拒绝**（不会建出第二张同义表）—— 那是保护，不是错误。\n' +
        '字段类型 type 可以给数字也可以给中文名：文本 1 / 数字 2 / 单选 3 / 多选 4 / 日期 5 / ' +
        '复选框 7 / 人员 11 / 电话 13 / URL 15 / 附件 17 / 单向关联 18。' +
        '**类型不认识时会拒绝，不会默认成文本**（默认成文本的字段能建出来，但存进去的全变字符串，且没有任何东西会红）。\n' +
        `单选项用 options 传候选值数组。\n${TOKEN_HINT}${WRITE_HINT}`,
      parameters: {
        type: 'object',
        properties: {
          app_token: { type: 'string' },
          name: { type: 'string', description: '新表的名字' },
          fields: {
            type: 'array',
            description: '字段定义数组',
            items: {
              type: 'object',
              properties: {
                name: { type: 'string' }, type: { type: ['string', 'number'] },
                options: { type: 'array', items: { type: 'string' }, description: '单选/多选的候选值' },
              },
              required: ['name', 'type'],
            },
          },
        },
        required: ['app_token', 'name', 'fields'],
      },
    },
  },
  run: async ({ app_token, name, fields }) => lw.createTable(runtimeContext, app_token, name, fields),
});

register('lark_base_create_field', {
  scope: 'write',
  schema: {
    type: 'function',
    function: {
      name: 'lark_base_create_field',
      description: `给已有的表加一列。类型取值同 lark_base_create_table。\n${TOKEN_HINT}\n${TBL_HINT}${WRITE_HINT}`,
      parameters: {
        type: 'object',
        properties: {
          app_token: { type: 'string' }, table: { type: 'string' },
          field: {
            type: 'object',
            properties: {
              name: { type: 'string' }, type: { type: ['string', 'number'] },
              options: { type: 'array', items: { type: 'string' } },
            },
            required: ['name', 'type'],
          },
        },
        required: ['app_token', 'table', 'field'],
      },
    },
  },
  run: async ({ app_token, table, field }) => lw.createField(runtimeContext, app_token, table, field),
});

register('lark_base_update_field', {
  scope: 'write',
  schema: {
    type: 'function',
    function: {
      name: 'lark_base_update_field',
      description:
        '改一个已有字段（改名 / 改类型）。改之前旧定义会先落进留痕文件。\n' +
        '⚠️ 改类型可能让已有数据失配 —— 改完一定要看 readback。\n' +
        `\n${TOKEN_HINT}\n${TBL_HINT}${WRITE_HINT}`,
      parameters: {
        type: 'object',
        properties: {
          app_token: { type: 'string' }, table: { type: 'string' },
          field_name: { type: 'string', description: '要改的字段现在的名字' },
          patch: {
            type: 'object',
            properties: { name: { type: 'string' }, type: { type: ['string', 'number'] } },
            description: '要改成什么；至少给一个',
          },
        },
        required: ['app_token', 'table', 'field_name', 'patch'],
      },
    },
  },
  run: async ({ app_token, table, field_name, patch }) =>
    lw.updateField(runtimeContext, app_token, table, field_name, patch),
});

register('lark_base_delete_field', {
  scope: 'write',
  schema: {
    type: 'function',
    function: {
      name: 'lark_base_delete_field',
      description:
        '**提议**删掉一列。★ 这个工具**不会真删** —— 它只把「要删哪一列、那列有多少条非空」摆出来，\n' +
        '并把这件事挂起等着。要把 `will` 那句话原样说给对方，等他**在另一条消息里**说确认，\n' +
        '再调 `lark_base_confirm_delete`。删列会连带那一列的全部数据。\n' +
        `${TOKEN_HINT}\n${TBL_HINT}${PROPOSE_HINT}`,
      parameters: {
        type: 'object',
        properties: {
          app_token: { type: 'string' }, table: { type: 'string' },
          field_name: { type: 'string' },
        },
        required: ['app_token', 'table', 'field_name'],
      },
    },
  },
  run: async ({ app_token, table, field_name }) => lw.deleteField(runtimeContext, app_token, table, field_name),
});

register('lark_base_delete_table', {
  scope: 'write',
  schema: {
    type: 'function',
    function: {
      name: 'lark_base_delete_table',
      description:
        '**提议**删掉整张表。★ 这个工具**不会真删** —— 它只把「哪张表、几列、几条记录」摆出来并挂起等待。\n' +
        '要把 `will` 那句话原样说给对方，等他**在另一条消息里**说确认，再调 `lark_base_confirm_delete`。\n' +
        '真删之前会把「表 + 全部字段 + 最多 500 条记录」完整搬进留痕；搬不全就拒绝执行。\n' +
        `${TOKEN_HINT}\n${TBL_HINT}${PROPOSE_HINT}`,
      parameters: {
        type: 'object',
        properties: { app_token: { type: 'string' }, table: { type: 'string' } },
        required: ['app_token', 'table'],
      },
    },
  },
  run: async ({ app_token, table }) => lw.deleteTable(runtimeContext, app_token, table),
});

register('lark_base_create_records', {
  scope: 'write',
  schema: {
    type: 'function',
    function: {
      name: 'lark_base_create_records',
      description:
        '往表里批量新增记录。records 是**字段名 → 值**的对象数组，字段名必须和 lark_base_fields 返回的一致。\n' +
        '多选字段传字符串数组；日期传毫秒时间戳（数字）；URL 字段传 `{"link":"https://…","text":"显示文字"}`。\n' +
        '一次最多 500 条，超了会**拒绝**（不会静默截断 —— 截断会让人以为全写进去了）。\n' +
        '写完会按返回的 record_id 逐条读回来比对，`record_ids` 要留着（后面改哪条靠它）。\n' +
        `${TOKEN_HINT}\n${TBL_HINT}${WRITE_HINT}`,
      parameters: {
        type: 'object',
        properties: {
          app_token: { type: 'string' }, table: { type: 'string' },
          records: { type: 'array', items: { type: 'object' }, description: '每条是 {字段名: 值}' },
        },
        required: ['app_token', 'table', 'records'],
      },
    },
  },
  run: async ({ app_token, table, records }) => lw.createRecords(runtimeContext, app_token, table, records),
});

register('lark_base_update_records', {
  scope: 'write',
  schema: {
    type: 'function',
    function: {
      name: 'lark_base_update_records',
      description:
        '批量改已有记录。每条要带 record_id（lark_base_records 或 create 的返回值里拿）。\n' +
        '改之前旧值会先落进留痕文件。一次最多 500 条。\n' +
        `${TOKEN_HINT}\n${TBL_HINT}${WRITE_HINT}`,
      parameters: {
        type: 'object',
        properties: {
          app_token: { type: 'string' }, table: { type: 'string' },
          records: {
            type: 'array', items: { type: 'object' },
            description: '每条是 {record_id, fields:{字段名: 新值}}',
          },
        },
        required: ['app_token', 'table', 'records'],
      },
    },
  },
  run: async ({ app_token, table, records }) => lw.updateRecords(runtimeContext, app_token, table, records),
});

register('lark_base_delete_records', {
  scope: 'write',
  schema: {
    type: 'function',
    function: {
      name: 'lark_base_delete_records',
      description:
        '**提议**按 record_id 删记录。★ 这个工具**不会真删** —— 它只把「哪几条、那几条长什么样」摆出来并挂起等待。\n' +
        '要把 `will` 那句话原样说给对方，等他**在另一条消息里**说确认，再调 `lark_base_confirm_delete`。\n' +
        '真删之前会把这几条的完整内容先搬进留痕；读不回旧值、或读回条数对不上，一律拒绝执行。\n' +
        `${TOKEN_HINT}\n${TBL_HINT}${PROPOSE_HINT}`,
      parameters: {
        type: 'object',
        properties: {
          app_token: { type: 'string' }, table: { type: 'string' },
          record_ids: { type: 'array', items: { type: 'string' }, description: '要删的 record_id 列表' },
        },
        required: ['app_token', 'table', 'record_ids'],
      },
    },
  },
  run: async ({ app_token, table, record_ids }) => lw.deleteRecords(runtimeContext, app_token, table, record_ids),
});

/* ─────────────── 两段式第二步：确认 / 取消（2026-09-22 委托方定）─────────────── */

register('lark_base_confirm_delete', {
  scope: 'write',
  schema: {
    type: 'function',
    function: {
      name: 'lark_base_confirm_delete',
      description:
        '执行上一条**已提议**的删除。★ 只有在对方**在另一条消息里**明确说「确认 / 删吧 / 好」之后才调它。\n' +
        '三种情况会被拒，拒了就是没删：`no_pending`（没有待确认的）/ `expired`（提议过了 15 分钟）/\n' +
        '`same_message`（**在发起删除的那一条消息里自我确认** —— 那不算确认，重新等对方回一句）。\n' +
        '被拒时**不要换个说法再试**，把拒的理由告诉对方就行。\n' +
        '执行之后同样返回 `readback` 三态；`mismatch`/`untested` 不许说成「删好了」。',
      parameters: { type: 'object', properties: {}, required: [] },
    },
  },
  run: async () => lw.confirmDelete(runtimeContext),
});

register('lark_base_cancel_delete', {
  scope: 'write',
  schema: {
    type: 'function',
    function: {
      name: 'lark_base_cancel_delete',
      description:
        '取消上一条已提议但还没确认的删除（对方说「算了 / 不用了 / 先别删」时用；同一条消息里也可以取消）。\n' +
        '返回 `cancelled: true` 与 `what`（被取消的是哪一件事）。',
      parameters: { type: 'object', properties: {}, required: [] },
    },
  },
  run: async () => lw.cancelDelete(runtimeContext),
});

/* ─────────────── 知识库检索：kb_search / kb_status ─────────────── */

/**
 * ★★ 重建件说明（2026-10-03）—— 这两个工具是**重建**的，不是原文。
 *
 * ── 事故
 * `tools.mjs` 在磁盘上被误删（`git status` 记为 `D`）。恢复时从 HEAD 取回，
 * 而 HEAD 是 **2026-09-24** 的版本 —— 这两个工具是那之后加进**工作树**的、
 * **从没提交过**，于是随删除一起没了。**没提交 ≠ 没在用。**
 *
 * ── 怎么发现恢复错了
 * 守衡启动时会把工具清单写进 `PMO/logs/ws_daemon.log`（`loadedTools()`，注释写着
 * 「确认工具与模型都装载成功」）。那份清单是 **27 个**、含 `kb_search(read) kb_status(read)`；
 * 而 HEAD 版只有 **25 个**、这两个一个都没有。**日志比 git 记得多。**
 *
 * ── 怎么重建（契约不是猜的，是抄的）
 *   · `kb_client.test.mjs` 的 **E1–E7 就是这两个工具的规格**（它从 `tools.mjs` 取
 *     `executeTool` / `toolNames`，所以原文必然注册在本文件里）；
 *   · `judge_evidence.mjs` 顶段写明「只把 kb_search 挂成**第 26 件**工具」——
 *     与「HEAD 25 件 + kb_search + kb_status = 27 件」严丝合缝；
 *   · 客户端 API 全在 `kb_client.mjs`（该文件未丢失）。
 *   重建后必须跑 `node kb_client.test.mjs`，E1–E7 全过才算还上（它全程离线，不碰真凭据与真配额）。
 *
 * ── 为什么「未查成」必须是独立形态（E4/E5/E6 守的就是这条）
 * 检索失败（配额用尽 / 连不上 / 429）**绝不能**返回空 `hits`：一个空数组到了模型手里，
 * 会被读成「查过了，知识库里没有」—— 而真相是「这次没查到」。这两句在**判定**上恰好相反：
 * 前者能被拿来支持「合规」，后者只能转人工。所以失败时**连 `hits` 这个键都不给**（E5），
 * 给 `[]` 也算错。
 */

/** 检索失败时的统一形态。话术里**必须**含「不是「没有命中」」这句（E6 守它）。 */
function kbUntested(why, extra = {}) {
  return {
    is_untested: true,
    // ★ 故意**不给** hits 键 —— 理由见上面那段。
    reason: why,
    note: `⚠️ 本次**没有查成**（${why}）。这是「未测」，**不是「没有命中」** —— `
        + '不许把这次结果读成「知识库里没有这条」，更不许拿它当合规依据。'
        + '要么照实说「我没查成」，要么转人工。',
    ...extra,
  };
}

register('kb_search', {
  scope: 'read',
  schema: {
    type: 'function',
    function: {
      name: 'kb_search',
      description:
        '在 Momcozy 内容治理知识库里检索条文分片。返回命中分片（docId / docTitle / chunkId / 正文 / ' +
        'score 及其含义）、排序可信度、配额真值。\n' +
        '什么时候用：要「知识库怎么规定的」「有没有相关条文」这类**依据**时。\n' +
        '★ 三条必须照实转述的边界：\n' +
        '(1) 返回的是**分片**(chunk)不是完整规则，而且**没有取全文的端点** —— ' +
        '不许把一片当成一条规则的全部。\n' +
        '(2) `order_is_meaningful=false` 时**顺序不可信**（查询词不足 3 个字符时服务端回退成词频序）。' +
        '别按返回顺序下结论；`query_hint` 里有改写建议。\n' +
        '(3) 返回 `is_untested=true` 是**没查成**（配额用尽 / 连不上），**不是「没有命中」** —— ' +
        '这种时候连 `hits` 都不会有。必须照实说「我没查成」。',
      parameters: {
        type: 'object',
        properties: {
          query: { type: 'string', description: '查询词。★ 中文请给 **3 个字以上**，否则服务端走词频序、顺序不可信。' },
          collection: { type: 'string', description: '限定子库 id（如 3_措辞表达库 / 1_外部标准库 / 2_内部正负样本库）。省略则用默认子库。' },
          topK: { type: 'number', description: `要几条候选（上限 ${kb.TOPK_MAX}，默认 ${kb.TOPK_DEFAULT}）。回给模型的条数另有更小的上限（${kb.HITS_RETURN_MAX}）。` },
        },
        required: ['query'],
      },
    },
  },
  run: async ({ query, collection, topK } = {}) => {
    const q = String(query ?? '').trim();
    if (!q) return kbUntested('查询词为空');
    const coll = String(collection ?? '').trim() || kb.COLLECTIONS.wording;
    // 配额闸门：宁可少查，也不要把日配额烧穿（60/分、1000/天，见 kb_client 顶部实测）。
    if (!kb.canSpend(1)) {
      return kbUntested('知识库日配额已用尽（服务端最近一次回报）',
                        { collection: coll, quota: kb.quotaState() });
    }
    try {
      return await kb.retrieve(coll, q, { topK: Number(topK) || undefined });
    } catch (e) {
      return kbUntested(`检索失败 ${e?.code ?? e?.name ?? 'ERROR'}：${e?.message ?? e}`,
                        { collection: coll, quota: kb.quotaState() });
    }
  },
});

register('kb_status', {
  scope: 'read',
  schema: {
    type: 'function',
    function: {
      name: 'kb_status',
      description:
        '看知识库接上了没有、有哪些子库、配额还剩多少。\n' +
        '什么时候用：检索没查成时先判「是配置/网络问题还是配额问题」；或要回答「守衡到底连着知识库没有」。\n' +
        '★ 探活（GET /health）**免鉴权、不消耗配额**；列子库与检索要消耗。\n' +
        '★ 余额是**服务端上一次回报**的真值，转述时必须连 `asOf` 一起说 —— 别把它说成「此刻还剩多少」。',
      parameters: { type: 'object', properties: {}, required: [] },
    },
  },
  run: async () => {
    const p = await kb.ping();                    // 免费探活：0 配额、约 0.2 秒
    const described = kb.describeKb();
    const out = {
      connected: p.ok === true,
      baseUrl: described?.baseUrl ?? null,
      health: { httpStatus: p.httpStatus, service: p.service ?? null, elapsedMs: p.elapsedMs, note: p.note },
      quota: kb.quotaState(),
      collections: Object.values(kb.COLLECTIONS),
    };
    // E7：连不上时**必须**给出 error 字符串 —— 「配额问题」与「配置/网络问题」要一眼分得开。
    if (!p.ok) {
      out.error = String(p.note ?? '探活失败');
      out.note = '⚠️ 探活没通，所以「库里有没有这条」**现在无法回答**。这是「没查成」，不是「没有」。';
    } else {
      out.note = '探活通。注意：探活只证明**隧道通、服务端活着**，**不证明 key 还有效** —— '
               + '那得靠一次真检索（或列子库）才知道。';
    }
    return out;
  },
});

/* ─────────────── 知识库审查链（2026-10-03 加）─────────────── */

/**
 * `kb_review_chain` —— 把一条待审内容交给**知识库那条链**去判。
 *
 * ── 为什么守衡自己判不了、必须外派一个 DSH agent
 *
 * 守衡的 `judge_copy` 走的是 `JUDGE_PY`（本仓自己的判定引擎 + 自己的词表/外部标准库），
 * 那是**一套栈**；Momcozy 知识库是**另一套栈**：
 *   L4 发号 → L5 P0 → L6 召回 → L7 跨层闸门 → 评审链出三态（PASS/REVIEW/BLOCK）
 *   → 落报告 → 发飞书。
 * 那条链的每一步都要求执行者**能加载 skill**：**逐层**用 `skill` 工具把本层
 * skill 读进上下文，而且**库里的审计会核这件事**（`skill_invocation_audit.py`，红 1 就拒答）。
 * `skill` 工具是 **DSH 独有的**。守衡是个 node 进程，它加载不了 skill —— 但它能 spawn 一个 DSH agent。
 *
 * `dsh --profile headless "<task>"` 就是为此造的（`@deepseek-ai/dsh-headless` 自述：
 * "Answer one task, stream reasoning to stderr, print the final assistant message, and exit."）。
 * ★ 实测（2026-10-03 22:26，问「Momcozy 穿戴式吸奶器，三种模式九档吸力，单双边可选。」）：
 *   四层 + 评审链全自动跑完 —— 四条审计红 0、`mode=enforced`、报告落
 *   `kb/l7/reports/rv-20261003-223320.feishu.md`、飞书表行 `recvwZSX3lygJe`。**全程无人提醒。**
 *
 * ── 三条纪律（每条都有代价，不是客套）
 *
 *   ① **不许追问**：内容 ID / 渠道 / 产品线 / 版本这些缺省字段，知识库侧**会自己补**
 *      （它的 AGENTS.md 明文要求「缺省自动补，不许追问」）。这里再问一遍，
 *      等于把一个已经解决的问题又推回给人。
 *   ② **超时要长、超时要说"未知"**：一单要跑四层（2026-10-05 起四层由**一次执行**跑完，不再逐层起 subagent），2026-10-05 实测：**四层前置侧 832.6 s → 7.7 s**（同一天同一条链）；但**端到端仍是 4~10 分钟**（四类素材实测均值 6.25 分钟）—— 因为其中**约八成是 agent 自己在想**（实测一单 326.6 s 里模型生成 259.8 s）。
 *      给 30 分钟。**超时不要编结论** —— 半条链的结论比没有结论更危险
 *      （层前置没跑完就出三态，正是库里那三条防线要防的事）。
 *   ③ **原文逐字传**：`question` + `text` 原样交给 DSH，**不改写、不翻译、不总结**。
 *      判定对象一变，依据就不再指向它 —— 而报告里的锚点/条款号是按原文取的。
 *
 * ── 为什么 scope 是 'write'（本文件只标了三个 read 之外的第一个）
 *
 * 因为它**会往飞书写东西**：结论 ≥3 个问题时写云文档，并按内容 ID 幂等 upsert 一条表行。
 * （按本文件顶部那段：`scope` 只是标注、不是闸门 —— 但标错方向会骗下一个读代码的人，
 *   所以这里按真实副作用标。真正拦不拦，看调用方要不要给。）
 */
const KB_ROOT = process.env.SHOUHENG_KB_ROOT
  || '/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理';
const DSH_BIN = process.env.SHOUHENG_DSH_BIN
  || '/Applications/DSH Desktop.app.pre-lute-20260907-111753/Contents/Resources/app.asar.unpacked'
     + '/node_modules/@deepseek-ai/dsh/lib/bin.js';
const KB_REVIEW_TIMEOUT_MS = Number(process.env.SHOUHENG_KB_REVIEW_TIMEOUT_MS || 30 * 60_000);

/**
 * 跑批前把「认领」这道门清干净 —— 2026-10-05 事故驱动（用户实测：10-04 22:18 那次
 * 整整卡满 30 分钟才超时，10-05 仍然不行）。
 *
 * 病因：`kb/.work/.kb-loop-claim.json` 的持有者 pid 已死，但 **TTL 45 分钟还没到**。
 *   `kb_loop_claim.py claim` 遇到「已被占」一律 exit 3，而 **`--take-over` 只在陈旧时才放行**
 *   ⇒ 链子卡在门口进不去、又不报错，只能等 TTL —— 等到了 30 分钟上限，回报一张 alert 卡片。
 *   ★ 更糟的是 TTL 过期**不会自动放行**（`claim` 对陈旧认领默认仍拒），
 *     所以**一次崩溃 = 此后每一条 @守衡 都静默失败**，直到有人手工 `--take-over` / `release --force`。
 *
 * 本函数做两件事：
 *   ① 陈旧认领（pid 已死 / 超 TTL）→ **当场 `release --force`**（这正是脚本自己承认可以接手的状态）；
 *   ② 新鲜认领（别的会话**正在跑**）→ **立刻回话说"库忙"**，而不是耗满 30 分钟才说超时。
 *      —— 不抢是对的（库规：同一时间只准一个会话跑这条循环），但"不抢"不等于"陪着等"。
 *
 * 返回 {blocked, detail, action}。**预检本身出错不阻断**（fail-open）——
 * 宁可让链子按原样去撞，也不要因为预检脚本崩了就永远送不了审。
 */
/**
 * **只读**地问一句：知识库那条循环现在有没有人在跑？（给回执用）
 *
 * ★ 与 `preflightClaim()` 的区别：那个会**顺手释放陈旧认领**（有副作用），
 *   这个一个字节都不改 —— 回执这一步只想知道「要不要说排队」，不该动任何东西。
 *   超时给得短（8 秒）：它是**回话之前**跑的，慢了就等于让人多等。
 *
 * @returns {Promise<{free:boolean, stale:boolean, detail:string}>}
 */
// ══════════════════════════════════════════════════════════════════════════
// ★★ 2026-10-08 **根因修复**：非零退出是**结果**，不是**异常**
// ══════════════════════════════════════════════════════════════════════════
// **病灶（当天实测到根因，Owner 问「库忙彻底解决了吗」逼出来的）**：
//   `kb_loop_claim.py status` 的契约是「**exit 3 = 被别人占着**」（脚本头注第 32 行），
//   而 `promisify(execFile)` **在非零退出上会 reject** ⇒ 「被占」这个信号
//   **永远以异常的形式到达**，`const { stdout } = await execFileP(...)` 那一行直接抛。
//
//   于是 `preflightClaim()` 里那个 `blocked: true` 分支是**死代码**：
//   它要检测的情形，恰好就是它抛异常的情形。实测原话（认领正被占着时实调）：
//     code=3 ｜ STDOUT="**进行中** ｜ 会话=session-11298093… ｜ BASE=20261008-1730"
//     ⇒ 返回值 {blocked:false, detail:"认领预检跳过（Command failed: sh … status）"}
//   **⇒ 守衡的认领预检从来没有生效过一次**：每次送审都直接起链，链内部才被拒
//     （`kb/l8/review_run.sh` exit 3）⇒ 用户拿到的是一张**库忙卡**。
//   同一个 bug 还咬了 `claimStatus()` ⇒ **回执卡从来说不出「在排队」**，
//   只会报常态 ETA（`agent.mjs:678` 那条分支等于也废了）。
//
// **为什么这条特别坏**：catch 把失败降级成「不 blocked」，**一行日志都不打**，
//   于是「预检坏了」与「预检说空闲」在外部**长得一模一样**。这正是库规
//   「缺证据必须可见，不许静默」要禁的形状 —— 一个安静地把失效说成正常的形状。
//
// **修法**：`runCapture` 把退出码**收下来**（REJECT 只留给「根本起不来」）。
//   判据：只有 code ∈ {0, 3} 才算**拿到了答案**（那两个码是脚本契约里写死的）；
//   其余码（含 ENOENT / 超时被杀）一律当「读不到」⇒ 调用方走各自的 fail-open，
//   但**必须出声**（`console.log`），不许再静默。
async function runCapture(file, args, opts = {}) {
  try {
    const { stdout, stderr } = await execFileP(file, args, opts);
    return { code: 0, stdout: String(stdout ?? ''), stderr: String(stderr ?? '') };
  } catch (e) {
    // execFile 在「非零退出」与「超时被杀」两种情况下都 reject，且都带上
    // stdout / stderr / code（Node ≥ 12）——所以异常里**有**我们要的答案。
    if (e && (typeof e.code === 'number' || e.stdout !== undefined)) {
      return { code: typeof e.code === 'number' ? e.code : -1,
               stdout: String(e.stdout ?? ''), stderr: String(e.stderr ?? ''),
               signal: e.signal ?? null, killed: e.killed === true, err: e };
    }
    throw e;                       // 真的起不来（ENOENT/权限）⇒ 照旧抛
  }
}

/**
 * **纯函数**：把 `status` 的 `{code, stdout}` 解析成三态。
 *
 * 抽成纯函数**就是为了能被离线自证**（`claim_wait.test.mjs`）：这个 bug
 * （exit 3 = 被占，而 execFile 在非零退出上 reject）**只有真的占一次槽才碰得到**，
 * 而「测试去占真库的槽」既慢又污染真库 ⇒ 把判据抽出来，喂**逐字真实样本**。
 *
 * **只认 code ∈ {0,3}**（脚本头注第 32 行的契约）；其余码一律抛
 * ⇒ 调用方 fail-open 但**必须出声**。
 * 三态与 `kb_loop_claim.py::cmd_status()` 逐行对应：
 *   exit 0 + 「无认领」 ⇒ free ｜ exit 0 + 「陈旧」 ⇒ stale
 *   exit 3 + 「进行中」 ⇒ busy ｜ exit 3 + 「读不出」⇒ **也当 busy**
 * （最后那条照脚本自己的口径：「保守起见先别跑，人工看一眼再决定」。）
 */
export function parseClaimStatus({ code, stdout, stderr = '', killed = false } = {}) {
  if (code !== 0 && code !== 3) {
    throw new Error(`status 退出码 ${code}（契约只认 0/3）`
      + (stderr ? `，stderr=${String(stderr).trim().slice(0, 200)}` : '')
      + (killed ? '（超时被杀）' : ''));
  }
  const s = String(stdout ?? '').trim();
  if (s.includes('无认领')) return { state: 'free', detail: '空闲（无认领）', code };
  if (s.includes('陈旧')) return { state: 'stale', detail: s.slice(0, 200), code };
  return { state: 'busy', detail: s.slice(0, 300), code };
}

async function probeClaimStateOnce(timeoutMs = 30_000) {
  const KBPY = path.join(KB_ROOT, 'kb', 'kbpy');
  const CLAIM = path.join(KB_ROOT, 'kb', 'l7', 'scripts', 'kb_loop_claim.py');
  const r = await runCapture('sh', [KBPY, CLAIM, 'status'],
    { cwd: KB_ROOT, timeout: timeoutMs, maxBuffer: 1 << 20 });
  return parseClaimStatus(r);
}

export async function claimStatus({ timeoutMs = 8000 } = {}) {
  try {
    const st = await probeClaimStateOnce(timeoutMs);
    return { free: st.state === 'free', stale: st.state === 'stale',
             busy: st.state === 'busy', detail: st.detail };
  } catch (e) {
    // 取不到就说「不知道」—— 回执退回常态那套话（不谎报排队，也不谎报空闲）
    console.log(`[claim] ⚠️ 认领状态读不到（回执将按"不知道"处理）：${e?.message ?? e}`);
    return { free: false, stale: false, unknown: true, detail: `状态读不到：${e?.message ?? e}` };
  }
}

// ══════════════════════════════════════════════════════════════════════════
// 认领预检（2026-10-08，Owner：「彻底解决库忙，不是解决这单」）
// ══════════════════════════════════════════════════════════════════════════
// 这一节当天改过**两轮**，两轮都要记着，否则会照着旧注释把缺陷改回来。
//
// ── 第 1 轮：修「预检从来没生效过」的退出码 bug（**这轮是纯 bug，与设计无关**）──
//   `kb_loop_claim.py status` 的契约是「**exit 3 = 被占**」，而 `promisify(execFile)`
//   **在非零退出上 reject** ⇒ `blocked: true` 那个分支是**死代码**，
//   每次送审都直接起链、链内部才被拒 ⇒ 用户拿到库忙卡。
//   同一个 bug 还咬了 `claimStatus()`（回执卡靠它决定说不说「排队」）。
//   ⇒ 修法：`runCapture()` 把非零退出当**结果**收下来。
//
// ── 第 2 轮：**把「排队等槽」删掉**（认领改成按 RUN 分槽之后，等待变成等一个不会发生的阻塞）
//   · 第 1 轮时认领还是「**全局单槽**」，所以我加了「被占就排队等 ≤10 分钟」；
//   · 但实测槽被持有**最长 1,659 秒（27.7 分钟）**、中位 34 秒 ⇒ 10 分钟**盖不住**，
//     等完还是库忙卡 —— 那句「排到了就正常跑」依然兑现不了；
//   · 真正的病根是**锁开大了**：持有单位是「会话」，要保护的却是「一次运行的写集」。
//     改成**按 RUN 分槽**（`kb_loop_claim.py` ①）之后，评审链的 RUN（`YYYYMMDD-HHMM`）
//     与供给链的（`daily-YYYYMMDD-HHMM`）**永不相等** ⇒ 「别人在跑」**根本挡不住本单**。
//   ⇒ 于是这里的等待是**等一个不会发生的阻塞**，删掉它才是对的 —— 留着反而会把
//     「别人在跑」重新变成一种延迟的库忙。
//
// ★ 现在这一节的职责只剩两条：
//   ① 陈旧认领 ⇒ **当场释放**（自愈，唯一还会动盘的分支）；
//   ② 别的 RUN 在跑 ⇒ **记下来（`ran_by`）但绝不拦**。
// ★ 残余（rare，且是**正确行为**不是缺陷）：两次评审落在**同一分钟** ⇒ RUN 同名 ⇒
//   链内部 `review_preflight.sh` 照旧 exit 3（fail-closed），这一单按库忙处理并由补发队列重试。
//   **那一刻的库忙是真的。**

/** 探一次认领状态（**只读**，一个字节都不改）。解析口径见 `probeClaimStateOnce`。 */
const probeClaimState = () => probeClaimStateOnce(30_000);

/** 释放陈旧认领（**有副作用**，只在这一种状态下调）。 */
async function releaseStaleClaim() {
  const KBPY = path.join(KB_ROOT, 'kb', 'kbpy');
  const CLAIM = path.join(KB_ROOT, 'kb', 'l7', 'scripts', 'kb_loop_claim.py');
  const r = await runCapture('sh', [KBPY, CLAIM, 'release', '--force'],
    { cwd: KB_ROOT, timeout: 30_000, maxBuffer: 1 << 20 });
  if (r.code !== 0) {
    throw new Error(`release --force 退出码 ${r.code}`
      + (r.stderr ? `，stderr=${r.stderr.trim().slice(0, 200)}` : ''));
  }
}

/**
 * 认领预检：空闲即过；陈旧即释放；**新鲜则排队等**（等不到才 blocked）。
 *
 * 依赖项全部可注入（`probe` / `releaseStale` / `sleep` / `now` / `log`）——
 * 为的是**这条等待逻辑能被离线自证**（`claim_wait.test.mjs`）：不注入就只能靠
 * 「真的去占一次槽」来测，那种测法既慢又会污染真库。
 * 默认参数 = 生产行为；调用点 `preflightClaim()` **一个字不用改**。
 */
export async function preflightClaim({
  probe = probeClaimState,
  releaseStale = releaseStaleClaim,
  now = () => Date.now(),
} = {}) {
  const t0 = now();
  const done = (extra) => ({ blocked: false, waited_ms: now() - t0, ...extra });
  try {
    const st = await probe();
    // ── 陈旧 ⇒ 自愈（唯一还会动盘的分支；这是"顺手的清理"，不是闸门）──
    if (st.state === 'stale') {
      await releaseStale();
      return done({ action: 'released_stale_claim',
                    detail: '检测到陈旧认领，已自动释放：' + st.detail });
    }
    // ★★ 2026-10-08（① 落地后）：**别的 RUN 在跑，不再拦、也不再等。** ──────────
    //   为什么（这条是 ① 的直接推论，不是"放宽"）：认领已改成**按 RUN 分槽**，
    //   而本链的 RUN 是**链内现取的时间戳**（`YYYYMMDD-HHMM`），供给链的是
    //   `daily-YYYYMMDD-HHMM` ⇒ **两者永不相等**。所以「别人在跑」**根本挡不住本单**，
    //   在这里等 10 分钟是等一个**不会发生的阻塞** —— 那正是库忙卡的另一种形状。
    //   ⚠️ 残余（rare，且是**正确行为**不是缺陷）：两次评审若落在**同一分钟**，
    //     RUN 会同名 ⇒ 链内部 `review_preflight.sh` 照旧 exit 3（fail-closed），
    //     这一单按库忙处理并由补发队列重试。**那一刻的库忙是真的。**
    //   判据：`claim_preflight.test.mjs` 的 ①（拆回"见谁都拦" ⇒ 精确变红）。
    return done({ action: st.state === 'free' ? undefined : 'foreign_run_running',
                  ran_by: st.detail,
                  detail: st.state === 'free'
                    ? '空闲（无认领）'
                    : '有别的 RUN 在跑（不阻塞本单，按 RUN 分槽）：' + st.detail });
  } catch (e) {
    // 探不到 / 释放失败 ⇒ 不 blocked，照跑。
    // ★ 这不是 fail-open 的口子：真正的强制在**链内部**（`kb/l8/review_preflight.sh`
    //   自己还会认领一次，同 RUN 被占就 exit 3）⇒ 这一层只是**提前**看一眼。
    return done({ detail: `认领预检跳过（${e?.message ?? e}）` });
  }
}

/**
 * 送审任务里**每次都要带上的两条硬规矩**（Owner 2026-10-05 现场定的）。
 *
 * ★ 为什么要带在**任务文本**里，而不是只写在工具描述里：
 *   工具描述是给**守衡**看的（什么时候调它），任务文本是给**链的执行者**看的（怎么判）。
 *   这两条改的是链的判定口径，不是守衡的调用时机 —— 写错地方等于没写。
 *
 * ★ 为什么这两条必须成对出现：
 *   ① 那天送了四条素材，链跑完 3.5~17.9 分钟，**表里一行都没有** ——
 *      因为链的发布条件是「有**三态结论**才发」，拒答整单被跳过，
 *      于是「审过了、结论是拒答」在盘上零痕迹。Owner 的原话是「**每一个评审任务都必须落表**」。
 *   ② 而那条图片素材**本来就是库里的案例**（与 `sample_case #32` 逐字重合，条款号 S-1.2，
 *      `polarity=反例`、`semantics=禁区`）。链认出了它，却以「自命中 / 同源留痕 / 循环论证」
 *      为由**降级成「交人裁」并最终拒答**。Owner 的裁定：**那是反面依据 —— 它指出问题所在，
 *      不是拒答的理由。** 用这条素材自己的历史案例判它自己，正是要的答案。
 *
 * ★ 守衡这一侧**不依赖**链照做：链返回后 `runSubmissionGate` 会核对「表里到底有没有这一行」，
 *   没有就自己补（`review_publish.mjs`）。这两条是**让链做对**，那一段是**保证不漏**。
 */
export const REVIEW_HARD_RULES = [
  '【本次送审的两条硬规矩（Owner 2026-10-05 现场定的，优先于默认流程）】',
  '1. **「自命中」是反面依据，不是拒答的理由。** 若本素材在库里命中**已定稿的反例/禁区条款**',
  '   （`polarity=反例`，或 `semantics` 以「禁区」开头，例如 S-1.2），那是**这条素材本身有定论**：',
  '   必须把它**登记为 findings**（带条款号 + anchor + source_sha256 + 逐字摘录）并据此出三态结论',
  '   （通常 BLOCK）。**不许**以「自命中 / 同源留痕 / 循环论证」为由把它降级成「交人裁」或拒答。',
  '2. **每一个评审任务都必须落表。** 无论结论是三态还是拒答/未测，都要往飞书多维表格',
  '   （app_token `RY2UbCRjXaeeWwscUPScVN5AnQc` / table `tblCXPQVzfFWWCon`）写一行并回读；',
  '   字段按 PRD：内容 ID、产品线、渠道、内容类型、送审版本、Agent 结论、置信度、问题数量、',
  '   问题分类汇总、报告链接、人工复核人、复核结论、sign-off 人、发布时间、状态。',
  '   拒答时 `状态` 填「待审」（PRD 六档里没有「拒答」）。',
].join('\n');

/* ── ★ P0 快路（2026-10-05 加）───────────────────────────────────────────────
 * 依据：PRD §6.3 第一层「P0 命中即**停止后续审查**，直接输出 BLOCK」+ §12「P0 层响应 ≤ 1 秒」
 *       + §6.2 P0 行「**无需大模型推理**，正则/关键词命中即输出 BLOCK」。
 *
 * 为什么放在**入口**而不是链内：链内跑一次要 4~10 分钟（2026-10-05 四单实测均值 6.25 min，
 * 其中约八成是通用 agent 自己在探索），而 PRD 要 ≤1 秒。**命中就不 spawn agent**
 * 是唯一满足它的做法（实测快路墙钟 0.13 s）。
 *
 * 边界（判据全部写死在库内 `kb/l5/p0_fastpath.py`，这里只转发，不在这里新造判据）：
 *   · 只对**命中**短路、只出 BLOCK —— **永不**产出 PASS / REVIEW；
 *   · 未命中一律回落原链（L4→L5→L6→L7 + 评审链），判据一条不放宽；
 *   · 结论自带 `mode=p0_fastpath` 与「未跑层前置」声明 —— **不许静默**；
 *   · 它是**只读**的：不碰 kb/.work/.kb.lock、也不写库 ⇒ 所以放在 claim **之前**，
 *     不去抢那条全局单槽（抢了反而让真正的重单更难跑）。
 */
async function runP0FastPath(text, { reportOut = null, reportRef = '' } = {}) {
  const s = String(text ?? '');
  if (!s.trim()) return { hit: false };
  const tmp = path.join(os.tmpdir(), `p0-fastpath-${process.pid}-${Date.now()}.txt`);
  const args = [path.join(KB_ROOT, 'kb/kbpy'), 'l5/p0_fastpath.py', '--file', tmp, '--json'];
  // ★ `--report-out`（2026-10-06）：报告**随判定一起落盘**，只多约 10 ms
  //   （报告正文 = 判定结果的重渲染，不重跑匹配、不联网）。
  //   它**不改变**这条快路的「只读、不抢锁」性质：落点是 `kb/.work/p0_reports/`（工作区临时区），
  //   不是 kb/l0–l7 的层数据，也不碰 `kb/.work/.kb.lock`。
  if (reportOut) args.push('--report-out', reportOut);
  // ★ `--report-ref`：第二次进来只把「报告链接」那一格换成真 url。
  //   它是**纯确定性函数**（同输入必同输出），所以重渲染不会让结论漂移。
  if (reportRef) args.push('--report-ref', reportRef);
  try {
    fs.writeFileSync(tmp, s, 'utf8');      // 走 --file：素材可能很长（视频转写），别撑爆 argv
    const { stdout } = await execFileP('sh', args,
      { cwd: KB_ROOT, timeout: 20000, maxBuffer: 8 << 20 });
    return JSON.parse(String(stdout));
  } finally {
    try { fs.unlinkSync(tmp); } catch { /* 临时件清不掉不影响结论 */ }
  }
}

/**
 * 读「机读旁挂」`kb/.work/last_review_result.json`（由 `kb/l8/review_run.sh` 写）。
 *
 * ★ 为什么需要它（Owner 2026-10-05 指出「BLOCK 却问题数量空」「拒答却问题数量 0」自相矛盾）：
 *   链跑在**另一个 dsh 进程**里，本工具只拿得到它的**最终文本** ——
 *   「问题数量 / 置信度」这些字段本来就在引擎 JSON 里，却传不出来，于是表里恒空。
 *   `review_run.sh` 跑完把引擎 JSON 的这些字段**原样**落一份小文件，这里读回来。
 *
 * 四条纪律：
 *   ① **只在新鲜时采纳** —— `at` 必须晚于本次起链时刻；
 *   ② ★★ **必须是本单的** —— `token` 必须等于本次起链注入的那个（见下）；
 *   ③ **不做任何换算** —— 引擎给什么就是什么；引擎给 null 就留 null（**不许编**）；
 *   ④ 读不到就**不带这个字段**（落表侧保持原样），**不抛错、不阻断链**。
 *
 * ══════════════════════════════════════════════════════════════════════════
 * ★★ 2026-10-08 **身份核对**（Owner 当天截图那一单逼出来的根因）
 * ══════════════════════════════════════════════════════════════════════════
 * **病灶**：旁挂是**一个固定文件**（`kb/.work/last_review_result.json`），
 *   **每一次跑都整份覆盖**——原链、补发、P0、任何并发单，全写同一个路径。
 *   而采纳判据原先**只有时间**（`at >= sinceMs - 2000`）。
 *   注释当时写的是「防读到上一单的，张冠李戴比没有更坏」——**它只挡住了"上一单"，
 *   挡不住"同时在跑的另一单"**：链要跑 2~3 分钟，这期间任何别的跑写完旁挂，
 *   本单读完 **必然** 拿到**最后写的那一份**，也就是**别人的结论**。
 *
 * **实测（Owner 2026-10-08 那张卡，逐条可核）**：
 *   · 用户发的图，当天被送 6 次，六轮 OCR **逐字相同**（624 字，`ROO MOMCOZY … oay … selcted suppoft`），
 *     对应内容 ID `AUTO-11edb5e80c35`（报告 `kb/l7/reports/20261008-171250.review.md`）；
 *   · 而守衡那张卡里引用的却是 `AUTO-a5c77a1ef763`——**另一张图**（报告 `20261008-171611`）；
 *   · 读旁挂的那一刻，文件里躺的是 `base=RT-20261008-IMG-BEDSHARE`、`content_id=AUTO-43d672880536`
 *     —— **第三单**的读数。`base` 这个身份字段**一直就在旁挂里，从来没有人核过**。
 *   ⇒ 后果不只是"数字不对"：结论、问题数、甚至卡片引用的**内容 ID** 都会变成别人的，
 *     人会照着一张图的审查史去看**另一张图**的结论（Owner 当场就报"回复是错误的"）。
 *
 * **修法（不依赖任何一方"记得传"，也不需要 env 穿透）**：旁挂里**新增身份字段
 *   `text_sha8` = `sha256(question + "\n" + text)` 前 8 位**，由 `review_run.sh` 在
 *   **两个写入点**各自算一遍写进去；这里用**本单自己那份 question/text** 独立算一遍，
 *   **只采纳指纹相符的那一份**。
 *   · 为什么是它：判据正是我们真正要保证的那件事 ——「**这份旁挂是不是审这段文本产生的**」。
 *   · 试过并且**否掉**的方案：起链时生成一次性令牌、经 env 注入子进程。**实测穿不过去** ——
 *     2026-10-08 照本工具的方式起 `dsh --profile headless`、注入
 *     `SHOUHENG_REVIEW_TOKEN=TOKPROBE-7f3a91c2`，让 headless agent 的 bash
 *     `echo $SHOUHENG_REVIEW_TOKEN` ⇒ 回 `TOKEN=`（**空**）。那一侧的 bash **不继承** env。
 *     ⇒ 那条路写进注释就是**假承诺**，已删。
 *   · 缺指纹 / 指纹不符 ⇒ **当作没读到**（回落「库侧没读数」），并**出声**。
 *     **宁缺勿错**：库规原话「张冠李戴比没有更坏」——这一条现在才真的成立。
 */
function readReviewSidecar(sinceMs, textSha8, contentId, reviewToken = '') {
  try {
    const p = path.join(KB_ROOT, 'kb/.work/last_review_result.json');
    const j = JSON.parse(fs.readFileSync(p, 'utf8'));
    const at = Date.parse(j?.at ?? '');
    if (!Number.isFinite(at) || !Number.isFinite(sinceMs) || at < sinceMs - 2000) return null;
    // ── ★★ 身份核对：**只告警，不拒收**（2026-10-08 第二次回修，理由见下）──────────
    //   为什么从「拒收」退回「告警」：**实测证明这两把锁对不上，而且不是偶尔对不上**。
    //   现场数据（委托方 p2p 发同一张床照图，日志逐字）：
    //     本单（守衡）文本指纹=de388f11 ｜ 内容ID=AUTO-de388f119542
    //     旁挂（链）  指纹=23da57f1 ｜ 内容ID=AUTO-23da57f188f4
    //   ——**两把锁内部是自洽的**（守衡那对互相印证 ⇒ 算式没错），
    //   但链算出来的内容身份与守衡那段文本的哈希**根本不是一个值**：
    //   链的报告 `kb/l7/reports/rv-20261008-180741.feishu.md` 写着
    //   `content_version：23da57f188f45c66dd553f00e122949705cfa18d5fcdc5191d1306954e257b3f`，
    //   而同一份报告的 `用户原提问` 是 **「审一下：这条送审素材能不能发」**（**链自己拟的话**，
    //   委托方那张图的消息正文是空的）⇒ **链的内容身份算在「它自己组装的那段文本」上**，
    //   不等于守衡递出去的素材文本。
    //   ⇒ 判据与事实不符时，**错的是判据**：继续拒收的代价是**每一单都丢掉库侧读数**
    //     （委托方当场看到「知识库侧本次未参与」，误以为库忙复现）。
    //   ⇒ 退回**时间口径**（原行为），把不一致**降级为一行告警**：
    //     证据留着（两个指纹都打出来），但**不再拿它挡读数**。
    //   ★ 待办（**没做完，别当已完成**）：真正的身份要么走链自己回传的 `review_id` /
    //     `publish.record_id`（答案里与旁挂里都有，且与文本构造无关），要么让
    //     `review_run.sh` 回写一个**由守衡注入、链原样带回**的随机数（env 走不通，
    //     已实测；需要走参数）。**在下一次动它之前，先把「链到底拿哪段文本算 content_version」
    //     查清** —— 否则又是一次猜。
    const wantSha = String(textSha8 ?? '').trim();
    const gotSha = String(j?.text_sha8 ?? '').trim();
    const wantCid = String(contentId ?? '').trim();
    const gotCid = String(j?.content_id ?? '').trim();
    const bySha = !!wantSha && !!gotSha && gotSha === wantSha;
    const byCid = !!wantCid && !!gotCid && gotCid === wantCid;
    // ★★ 2026-10-09（Owner 裁定「1 旁挂身份对齐」）：**第一把锁 = 一次性令牌**
    //   它是我这一侧造的那个素材文件路径，链侧 `--material-file` 收到什么就原样回写什么。
    //   **与"模型怎么组装文本"完全无关** —— 而这正是原先两把锁一起失效的原因。
    const wantTok = String(reviewToken ?? '').trim();
    const gotTok = String(j?.review_token ?? '').trim();
    const byToken = !!wantTok && !!gotTok && gotTok === wantTok;
    if (!byToken && !bySha && !byCid) {
      // ⚠️ 失败要**分得开是哪一级断的**（否则下次还得倒推）：
      //   · `gotTok` 空 ⇒ headless **没把 `--material-file` 带过去**（这一档要靠它逐字转发）；
      //   · `gotTok` 有值但不等于 wantTok ⇒ 链读的是**别人那份素材文件**（并发/补发串了）；
      //   · 两把文本锁也不成立 ⇒ 落到模型逐字那一档，而它不可靠（今天 6/6 没对上）。
      const why = !wantTok
        ? '本单没造素材文件（写 /tmp 失败）⇒ 只有文本两把锁，而它们今天 6/6 没对上'
        : (!gotTok
          ? '链侧**没收到 --material-file**（旁挂 review_token 为空）⇒ headless 没把路径带过去'
          : '链侧读的是**另一份素材文件**（review_token 不相等）⇒ 并发/补发串单');
      console.log(`[review] ⚠️ 旁挂身份对不上（**不拒收，按时间口径采纳**）`
        + `｜令牌=${byToken ? '✅' : '❌'}（旁挂=${gotTok || '（空）'}）`
        + `｜文本指纹 ${bySha ? '✅' : '❌'}（本单=${wantSha || '（无）'} 旁挂=${gotSha || '（缺）'}）`
        + `｜内容ID ${byCid ? '✅' : '❌'}（本单=${wantCid || '（无）'} 旁挂=${gotCid || '（缺）'}）`
        + `｜旁挂 base=${j?.base ?? '?'}｜旁挂 at=${j?.at ?? '?'}`
        + `｜断在哪一级：${why}`);
    } else {
      // ★ 成功也要出声（一行）：否则"这一单到底靠哪把锁认下来的"无从统计
      console.log(`[review] ✅ 旁挂身份对齐（${byToken ? '令牌' : (bySha ? '文本指纹' : '内容ID')}）`
        + `｜base=${j?.base ?? '?'}`);
    }
    return j;
  } catch {
    return null;   // 文件不在 / 不是 JSON ⇒ 当作没有（**不是**「结论为空」）
  }
}


/**
 * **产品线 / 渠道的兜底取数**：素材原文里逐字命中库内受控词（Owner 2026-10-06）。
 *
 * 为什么要兜底：图片/视频那类单**没有规则命中**（引擎输出里连 `anchor` 都没有），
 * 记录里取不到任何东西；而素材原文（含本机 OCR / 音轨转写）里**常常直接写着**
 * 「吸奶器」「Google」「展会」。
 * ★ 判据（词表、词边界、catch-all 剔除、**「这条记录是不是本素材本人」的准入闸**）
 *   **全部在库内** `kb/l5/l0_facets.py` —— 这里只转发，**不在这边新造一条**。库那边改了，这里自动跟着变。
 * ★ 取不到 ⇒ 返回空串（**不写「未指定」充数**，也不让模型猜）。
 */
export async function facetsFromMaterial(text) {
  const s = String(text ?? '').trim();
  if (!s) return { product_line: '', channel: '', from: {} };
  try {
    const { stdout } = await execFileP('sh',
      [path.join(KB_ROOT, 'kb/kbpy'), 'l5/l0_facets.py', '--text', s],
      { cwd: KB_ROOT, timeout: 20000, maxBuffer: 8 << 20 });
    const d = JSON.parse(String(stdout));
    return { product_line: d.product_line || '', channel: d.channel || '', from: d.from || {} };
  } catch (e) {
    console.log(`[facets] ⚠️ 素材兜底取数没跑成（不影响结论，产品线/渠道留空）：${e?.message ?? e}`);
    return { product_line: '', channel: '', from: {} };
  }
}


/* ── ★ 评审链执行手册（2026-10-05 加）──────────────────────────────────────
 * 目的：把 headless agent 从「探索者」压成「执行者」。
 *   实测它一单做 63 次工具调用（含一次 42 秒的全库递归 grep）、反复重跑闸门与重读同一文件，
 *   而四层前置只占 7.7 秒 ⇒ 时间花在「自己发明流程」上。
 * 真源 = 库内那一页 `kb/l8/review_playbook.md`：**读它、不复制它**（库内契约 #4：
 *   同一事实写两处，第二处必然过期）。
 * ⚠️ 读不到时**出声**（console.warn），不许静默返回空串 ——
 *   静默失效＝手册悄悄不生效而无人察觉，正是本库最忌讳的形状。
 * ⚠️ 位置必须在 `fs` / `path` / `KB_ROOT` 都就绪**之后**：2026-10-05 踩过 ——
 *   插到文件头上时 IIFE 在 import 之前执行，被 undefined 吞掉、返回空串而无人知道。
 */
export const REVIEW_PLAYBOOK = (() => {
  try {
    return fs.readFileSync(path.join(KB_ROOT, 'kb/l8/review_playbook.md'), 'utf8').trim();
  } catch (e) {
    console.warn(`[playbook] ⚠️ 读不到 kb/l8/review_playbook.md：${e?.message ?? e} —— 本单按 AGENTS.md 自行编排`);
    return '';
  }
})();
register('kb_review_chain', {
  scope: 'write',
  schema: {
    type: 'function',
    function: {
      name: 'kb_review_chain',
      description:
        '把一条待审内容交给 **Momcozy 知识库那条审查链**判：逐层跑 L4→L5→L6→L7（**逐层真的加载该层 skill**、四层由一次执行跑完、' +
        '真的加载该层 skill）→ 评审链出三态结论（PASS / REVIEW / BLOCK）→ 落报告 → 发飞书。\n' +
        '什么时候用：有人贴一段素材（文案 / 图片 / 视频 / 产品宣称）问「这个能不能发 / 有没有问题 / 审一下」' +
        '，而他要的是**知识库条款级依据**（条款号 + 命中片段 + 锚点 + L0 逐字原文）。\n' +
        '与 `judge_copy` 的分工：`judge_copy` 走本仓自己的判定引擎（快、秒级、返回档位与规则编号）；' +
        '本工具走知识库那条链（慢、分钟级、带 L0–L3 溯源与飞书留痕）。**要溯源就用本工具。**\n' +
        '★ 三条必须照实转述的限制：\n' +
        '(1) **这是一次真实发布动作**：结论问题数 ≥3 时它会写飞书云文档，并 upsert 一条表行 —— ' +
        '不是干跑。\n' +
        '(2) **耗时分钟级**（2026-10-05 四类素材实测 4~10 分钟；四层前置侧已从 832.6 s 降到 7.7 s，余下大头上是模型自己的生成时间），期间不要以为它卡死了。超时返回的是「结论未知」，' +
        '**不许当成通过**。\n' +
        '(3) 返回的 `answer` 是知识库 agent 的**最终回答原文**（含它自己写的边界声明与 E5 黄提示）。' +
        '**照实转述，不要简化掉边界** —— 库规里「未命中 ≠ 合规」是硬口径，省掉它会把一次「没查到」读成一次「没问题」。\n' +
        '原文里若出现另一会话抢了全局认领槽，那是**并发如实登记**，不是本工具失败。',
      parameters: {
        type: 'object',
        properties: {
          question: {
            type: 'string',
            description: '提问原文，**逐字**传入（例如「这句广告语能不能发？」）。不要改写、不要总结。',
          },
          text: {
            type: 'string',
            description: '待审素材原文，**逐字**传入。文案/字幕/产品宣称贴原文；图片或视频贴描述或链接。不要翻译、不要润色。',
          },
        },
        required: ['question'],
      },
    },
  },
  run: async ({ question, text } = {}) => {
    // ══════════════════════════════════════════════════════════════════════════
    // ★★ 2026-10-09（Owner 裁定「1 旁挂身份对齐」）**素材落文件 + 一次性令牌**
    // ══════════════════════════════════════════════════════════════════════════
    //   根因（今天每一单都复现，6 次）：旁挂的身份判据是
    //   「把喂给链的文本哈希一遍」，而**喂进去的那段文本是 headless 里的模型自己组装的** ——
    //   playbook 只写了「逐字传入」，没有任何东西能保证它逐字。于是指纹**从来没对上过**，
    //   身份核对恒不成立 ⇒ 退化成「按时间口径采纳」⇒ 「链接指向上一张图」。
    //
    //   ⇒ 修法：**把身份从"文本"换成"这次运行自己造的那份文件"**。
    //     · 本函数把素材写成 `/tmp/shouheng-material-<sha8>-<rand>.txt`；
    //     · 把**路径**写进 task，并明确要求原样带进 `review_run.sh --material-file <路径>`；
    //     · 链侧以文件为准（`--material-file` 覆盖 `--text`）⇒ **两边哈希同一份字节**；
    //     · 链侧把**收到的路径**原样回写成旁挂的 `review_token`（与文本构造完全无关）。
    //   ⇒ 守衡这一侧只需核：旁挂的 `review_token` == 我刚造的那个路径。
    //     ⚠️ 三级判据（令牌 > 文件指纹 > 内容 ID），**任一成立即认**；全不成立才拒。
    //       若 headless 没把 `--material-file` 带过去，旁挂 `review_token` 会是空 ⇒
    //        自动落到「文件指纹」那一级（此时才依赖模型逐字），仍对不上才拒 ——
    //        所以这两种失败**必须在日志里分得开**（见下面的 why 串）。
    let materialPath = '';
    let materialSha8 = '';
    {
      const t = String(text ?? '').replace(/[ \t\r\n]+$/, '');
      materialSha8 = crypto.createHash('sha256').update(t, 'utf8').digest('hex').slice(0, 8);
      // ⚠️ **用 `/tmp`，不用 `os.tmpdir()`**：后者在 macOS 上是
      //    `/var/folders/.../T`（`drwx------`，仅属主可进）。虽然守衡与 headless 都以
      //    `lute` 跑、理论上读得到，但这是**靠权限巧合**；`/tmp` 是双方确定可读的公开位，
      //    也是飞书 CLI 的既有约定（`lark-cli` 的 `@file` 只认 cwd 之下或 `/tmp` 之下 ——
      //    见库规那条实测）。素材文件本身不含机密（就是送审素材），放这里无额外暴露。
      materialPath = `/tmp/shouheng-material-${materialSha8}-${Date.now().toString(36)}.txt`;
      try { fs.writeFileSync(materialPath, String(text ?? ''), 'utf8'); }
      catch { materialPath = ''; }        // 写不成就退回老路（不阻断送审）
    }
    const materialRule = materialPath
      ? `\n【★ 本单素材已落盘，路径如下 —— **必须原样带给链**】\n`
        + `${materialPath}\n`
        + `调链时用 \`bash kb/l8/review_run.sh ... --material-file ${materialPath}\`，`
        + `**不要**自己把素材正文重新拼一遍再传（那样两边算出的指纹会对不上，`
        + `库里就认不出这份旁挂是本单的）。\n`
    : '';
    const task = [String(question ?? ''), String(text ?? ''), materialRule, REVIEW_HARD_RULES, REVIEW_PLAYBOOK]
      .map((s) => s.trim()).filter(Boolean).join('\n');
    // ── 素材文件用后即删（不留在盘上）────────────────────────────────────────
    //   删在 `finally` 里：链**跑成 / 跑败 / 超时**三种结局都要删，
    //   否则 `/tmp` 会攒下一堆送审素材（而它们是可以拼出客户内容的）。
    //   ⚠️ 删除**必须在链跑完之后** —— 链侧要读它算指纹。
    const cleanupMaterial = () => { if (materialPath) { try { fs.unlinkSync(materialPath); } catch { /* 已删/不存在都无妨 */ } } };
    if (!task) return { error: '问题和素材都为空，没有可送审的内容' };
    if (!fs.existsSync(DSH_BIN)) {
      return { error: `找不到 dsh CLI：${DSH_BIN}（可用环境变量 SHOUHENG_DSH_BIN 覆盖）` };
    }
    if (!fs.existsSync(KB_ROOT)) {
      return { error: `找不到知识库工作区：${KB_ROOT}（可用环境变量 SHOUHENG_KB_ROOT 覆盖）` };
    }

    // ── ★ P0 快路（2026-10-05）：PRD §6.3 第一层 / §12「P0 层响应 ≤ 1 秒」 ──────
    //    放在 claim **之前**：快路只读（模式表 + L4 canonical + L0 记录），
    //    不碰 kb/.work/.kb.lock、也不写库 ⇒ 不该去抢那条全局单槽。
    //    命中 ⇒ **不 spawn agent**（实测 0.13 s，对照走链 4~10 分钟）；
    //    未命中 ⇒ 原样往下走；快路**自身出错也照样回落**原链（不许因为快路坏了就不审）。
    let p0 = null;
    // 判定对象取**素材**（text）；没有素材才退回提问。
    // 为什么不把两者合并扫：提问里可能出现「这条有没有 safest 这种词？」——
    // 把提问也当判定对象会**误报红线**（假 BLOCK）。
    // ★ 提到 try 外面（2026-10-06）：报告那一步要用**同一个**判定对象重渲染，
    //   若它只在 try 里可见，就得在下面再算一遍 —— 两份"同一个东西"迟早会不一致。
    const p0Target = String(text ?? '').trim() || String(question ?? '').trim();
    // 报告落点：`kb/.work/p0_reports/`（工作区临时区，不写层数据）。带时间戳 + pid，
    // 同一秒两单也不会互相覆盖（实测并发单槽，但仍不留这个隐患）。
    const p0ReportPath = path.join(KB_ROOT, 'kb/.work/p0_reports',
      `${new Date().toISOString().replace(/[-:T]/g, '').slice(0, 14)}-${process.pid}.p0.md`);
    try {
      p0 = await runP0FastPath(p0Target, { reportOut: p0ReportPath });
    } catch (e) {
      p0 = null;
      console.log(`[p0] ⚠️ 快路没跑成，回落原链：${e?.message ?? e}`);
    }
    if (p0?.hit) {
      // ── ★ P0 报告（2026-10-06，Owner 三条口径）─────────────────────────────
      //   ① 「P0 问题可先在飞书侧响应」 ⇒ 回执卡在 `runSubmissionGate` 里**已经先发过了**
      //      （`notify(ackMessage(...))` 在调本工具之前），所以这一步**不占任何响应预算**；
      //   ② 「写入云文档报告的时间不统计在 ≤1 秒内」 ⇒ PRD §12 的「P0 层响应 ≤1s」
      //      量的是**判定**（`p0.elapsed_ms`，实测 9.8 ms），「报告生成」是另一条 ≤30s 的指标；
      //   ③ 「补充报告」 ⇒ 报告**必须**跑，跑成了把链接填进回执（PRD §5.3.3 要求 ≥3 条时出报告链接），
      //      跑不成要**看得见**（`report_detail` 带出 CLI 原话），**不许静默留空、更不许编链接**。
      let reportUrl = null;
      let reportDetail = '';
      // ── ★ **同一内容已有报告就复用，不新建**（Owner 2026-10-06 选定方案 (c)）──────────
      //   实测的病：同一份素材**复跑**时，`ensureReviewRow` 会按「内容 ID」找到**旧行**，
      //   而它的「报告链接」被「非空不覆盖」挡住了 ⇒ 这里新建的那一份**没人能点到**（孤儿文档）。
      //   (a) 改成新建一行 ⇒ 会多出**重复行**（比缺行更难发现）；
      //   (b) 改成覆盖旧链接 ⇒ 行内**自相矛盾**（汇总写旧审查、链接指新报告）；
      //   (c) **复用旧链接、不新建** ← 选它：不产孤儿、不产重复行、行与报告始终一致。
      //   为什么复用是对的：**内容 ID 是送审文本的 sha256** ⇒ 同一 ID 就是**同一份素材**，
      //   报告逐字相同。代价：多一次查表（实测 15 行 **~1.0 s**），发生在**回执卡之后**，
      //   不占 PRD §12 任何一条预算（「P0 层响应 ≤1s」量的是判定，仍 ~12 ms）。
      const p0ContentId = reviewPublish.contentIdOf(String(text ?? ''));
      const prevReport = await reviewPublish.previousReportLink(p0ContentId);
      if (prevReport) {
        reportUrl = prevReport;
        reportDetail = `复用同一内容已有的报告（内容 ID ${p0ContentId}）：${prevReport}`;
        console.log(`[p0] ♻️ 同一内容已有报告，复用不新建：${prevReport}`);
      } else if (p0.report_path) {
        const pub = await reviewPublish.publishReportDoc(p0.report_path);
        reportDetail = pub.detail;
        if (pub.ok) {
          reportUrl = pub.url;
          console.log(`[p0] 📄 报告已出：${pub.url}`);
        } else {
          console.log(`[p0] ⚠️ 报告没出（结论不受影响）：${pub.detail}`);
        }
      } else {
        reportDetail = '快路没给出 report_path（未落报告文件）';
        console.log(`[p0] ⚠️ ${reportDetail}`);
      }
      // ★ 拿到真链接就**重渲染一次回执**，把「报告链接」那一格填上（PRD §5.3.3）。
      //   没拿到就保留原文那句「报告在回执之后补」——那是实话，改掉它才是撒谎。
      let rendered = String(p0.rendered ?? '');
      if (reportUrl) {
        try {
          const again = await runP0FastPath(p0Target, { reportRef: reportUrl });
          if (again?.rendered) rendered = String(again.rendered);
        } catch (e) {
          console.log(`[p0] ⚠️ 回执重渲染失败（保留原回执，报告链接改由表行与落表摘要带出）：${e?.message ?? e}`);
        }
      }
      // ── ★ 两端对齐的运行期核对（Owner 2026-10-06：「后续两端数据必须对齐」）────────
      //   当天的事故形状：**回执说 3 条、云文档里读出来像 1 条**。
      //   根因是版式（已修），但那件事暴露了一个更根本的问题：
      //   「回执说的条数」与「报告里的条目数」**没有任何东西在运行时对照过**。
      //   所以这里加一道**生产期**核对（不能只写在自检里 —— 自检跑不到真实素材）：
      //     ① 回执正文里 `共发现 N 处` 的 N（**重渲染之后**的最终文本）
      //     ② 结构化字段 `p0.issue_count`（= findings 长度，落表「问题数量」用的就是它）
      //     ③ 报告文件里 `### 问题 N ｜` 的条数
      //   三处不一致 ⇒ **必须看得见**（日志 + 落进 report_detail，汇总格里会带出来）。
      //   **不许静默**：数量对不上时，看表的人只会觉得"怪"，说不出哪里错。
      let alignNote = '';
      try {
        const stated = Number((rendered.match(/共发现\s*(\d+)\s*处/) || [])[1]);
        let items = null;
        if (p0.report_path && fs.existsSync(p0.report_path)) {
          items = (fs.readFileSync(p0.report_path, 'utf8').match(/^### 问题 \d+ ｜ /gm) || []).length;
        }
        const expect = p0.issue_count;
        const bad = [];
        if (stated !== expect) bad.push(`回执写 ${stated}`);
        if (items !== null && items !== expect) bad.push(`报告里 ${items}`);
        if (bad.length) {
          alignNote = `⚠️ **两端条数对不上**：结构化=${expect} ｜ ${bad.join(' ｜ ')}。`;
          console.log(`[p0] ${alignNote}`);
        } else {
          console.log(`[p0] ✓ 两端对齐：回执 ${stated} ｜ 结构化 ${expect}`
            + ` ｜ 报告 ${items === null ? '（未落盘）' : items}`);
        }
      } catch (e) {
        alignNote = `（两端对齐核对没跑成：${e?.message ?? e}）`;
        console.log(`[p0] ⚠️ ${alignNote}`);
      }
      // ★ 2026-10-06：这里原先**又写了一遍**「本单走的是 P0 快路…未跑层前置…不是专项审查结论」。
      //   而 `kb/l5/p0_fastpath.py` 的 `_render()` 现在自己带一整节「来路与边界」——
      //   两处一说，模型就会当成两句不同的话分别转述（实测卡片里就是两段重复）。
      //   所以这一段**只留渲染器没有的那两个读数**（耗时 / 命中条数），边界不再重说。
      const answer = rendered.trim()
        + `\n\n（本单走 P0 快路：确定性匹配 ${p0.elapsed_ms} ms ｜ 命中 ${p0.matched_patterns} 条 P0 模式。）`;
      console.log(`[p0] 🚦 P0 命中 ⇒ 直接 BLOCK，不起链：${(p0.findings ?? []).map((f) => f.rule_code).join(',')}`
        + `｜${p0.elapsed_ms} ms`);
      return {
        ok: true,
        answer,
        p0_fastpath: {
          mode: p0.mode,
          elapsed_ms: p0.elapsed_ms,
          matched_patterns: p0.matched_patterns,
          rule_codes: (p0.findings ?? []).map((f) => f.rule_code),
          layer_preflight: p0.layer_preflight,
        },
        // ★★ 2026-10-14：「同问题取交集」缺的那一格 —— P0 的**结构化逐条**原样带出去。
        //   病灶：双轨的对齐判据比的是两侧的**逐字命中片段**，而库侧条目一直只有
        //   「命中正则」（实测 `最\s*(好|佳|…)`）；模型侧给的是**逐字引用的原句**
        //   ⇒ 两者永远不重叠 ⇒ **交集在实测 123 次双轨里一次都没成立过**。
        //   这一格**只搬不算**（值来自 CLI 自己的 `matched[].{line_text, span}`），
        //   不新增判据、不改任何结论、不改任何版式。
        p0_findings: Array.isArray(p0.findings) ? p0.findings : [],
        // ★ 2026-10-05（Owner 指出 BLOCK 却问题数量空 = 自相矛盾）：把引擎**已经给出**的
        //   结构化字段带出去。原先只带 mode/elapsed/patterns，落表侧取不到 ⇒ 表里恒空。
        //   **值来自 `kb/l5/p0_fastpath.py` 自己的输出，这里只搬不算。**
        issue_count: p0.issue_count,
        // P0 是**确定性匹配**（正则/关键词命中），PRD §6.6 明写「P0 层级规则**不适用置信度分流**，
        //   命中即 BLOCK」⇒ 不参与分流，但 **§8.2 要求该字段必须记录** ⇒ 记 1.0 = 「确定性命中」。
        //   这是**取值口径**，不是算出来的概率 —— 汇总列里会写明。
        confidence: 1.0,
        // ★ 报告（2026-10-06）：`report` 是**云文档链接**（没建成就是空串，**不是**"待生成"的占位）；
        //   `report_path` 是本地 .md；`report_detail` 是「成没成、为什么」的原话。
        //   `review_gate.formatChainBlock` 读 `report` 那一格 —— 空就什么都不显示（不许编）。
        report: reportUrl ?? '',
        report_path: p0.report_path ?? null,
        // ★ `align_note`（2026-10-06）：非空 = **两端条数对不上**，它是**给落表用的**——
        //   `agent.mjs` 会把它拼进「问题分类汇总」，于是**在表里看得见**。
        //   空串 = 三处一致（回执 / 结构化 / 报告条目数），正常情形。
        report_detail: reportDetail + alignNote,
        align_note: alignNote,
        // ★ 产品线 / 渠道（2026-10-06）：值来自 `kb/l5/p0_fastpath.py` 的 `facets`
        //   —— 它从**命中的 L0 记录**里取（`品线`/`适用产品`、`渠道/市场`/`渠道`/`平台`）。
        //   取不到就是空串 ⇒ 落表侧**不写这一格**（不许写「未指定」充数，更不许从素材正文猜）。
        product_line: p0.product_line ?? '',
        channel: p0.channel ?? '',
      };
    }

    // ★ 前置：清一下陈旧的跑批认领（自愈）。
    //   2026-10-05 加；2026-10-08 一天里改了两轮，**以 `preflightClaim()` 头注为准**：
    //     第 1 轮修掉「预检因退出码 bug 恒不生效」；第 2 轮随认领改成**按 RUN 分槽**，
    //     把「被占就排队等 ≤10 分钟」**删掉** —— 对方的 RUN 与本单永不相等，
    //     等它只是在等一个不会发生的阻塞。⇒ **`blocked` 今天恒为 false。**
    //   ⚠️ 这个分支**留着**（不删）：它是「库忙卡」的唯一落点，`preflightClaim` 若将来
    //     因为任何原因重新可能返回 `blocked`（比如又把某个判定加回预检），
    //     卡这条路必须还在 —— 删掉它等于让那种改动**静默地**把结论吞掉。
    const pre = await preflightClaim();
    if (pre.blocked) {
      console.log(`[claim] ⛔ 预检判定本单不能跑（等了 ${pre.waited_min ?? 0} 分钟，探了 ${pre.polls} 次）`
        + ` ⇒ 本单没送审：${String(pre.detail).slice(0, 160)}`);
      return {
        error: `知识库**跑批认领没拿到**`
             + (pre.waited_min ? `（我**替你排队等了 ${pre.waited_min} 分钟**）` : '')
             + ' ⇒ 本次**没有送审**。'
             + '这不是"审过了"、也不是"通过"——是**结论未知**。',
        claim_status: pre.detail,
        claim_busy: true,
        waited_min: pre.waited_min ?? 0,
        hint: '库规要求「同一个 RUN 同一时间只准一个会话跑」，所以这里**不抢**；'
            + '要抢只能在对方**陈旧**时才放行（脚本口径），而陈旧是它自己判的。'
            + '**这一单已进补发队列**（1 小时内最多 5 次）——它会自动重试；'
            + `也可手工看是谁占着：cd "${KB_ROOT}" && sh kb/kbpy l7/scripts/kb_loop_claim.py status`
            + '（`history` 看今天被占了几次、占了多久）。',
      };
    }
    const t0 = Date.now();
    // ★★ 本单身份指纹（详见 readReviewSidecar 头注）：
    //   `sha256(question + "\n" + text)` 前 8 位 —— 判据是**这次到底审的是哪段文本**。
    //   ★ 为什么不用「env 注入一次性令牌」：**实测穿不过去**。
    //     2026-10-08 照 `kb_review_chain` 的方式起 `dsh --profile headless`、
    //     注入 `SHOUHENG_REVIEW_TOKEN=TOKPROBE-7f3a91c2`，让它 `echo $SHOUHENG_REVIEW_TOKEN`
    //     ⇒ 回的是 `TOKEN=`（**空**）。headless agent 那一侧的 bash **不继承**本进程的 env，
    //     所以「令牌经 env 穿透」是**不成立的机制**，写进注释就是假承诺（库规禁这种形状）。
    //   ⇒ 改用**内容身份**：**只哈希素材文本**，并额外认**链自己算的内容 ID**
    //     （`contentIdOf`，与链同一算法 —— 落表一直在用它，从没出现过重复行）。
    //
    //   ★★ 2026-10-08 **当天就回修了一次，把误伤记在这里**：
    //     第一版哈希的是 `question + "\n" + text`，判据成了「**同一次提问** ＋ 同一段文本」——
    //     **太严，当场误伤**。实测（委托方截图那一单）：同一张图（bed-share）
    //     被 **p2p 新单**与**补发单**各跑一次，`question` 不同（「审核下这张图」vs 原话）
    //     ⇒ 指纹不符 ⇒ **把本来可用的读数拒掉了** ⇒ 卡片回落成「知识库侧本次未参与（没拿到引擎读数）」
    //     ⇒ 委托方看到的就是**「库忙又复现了」**（`[review] ⛔ 机读旁挂不是本单的｜本单文本指纹=b5e33261
    //     旁挂指纹=16c5f528｜旁挂 base=RT-20261008-173328-IMG-BEDSHARE`）。
    //     **同一内容换句话问，仍然是同一内容** —— 判据该按内容，不该按提问。
    //
    //   ★ 两处 rstrip 必须同口径：这里用**只去 ASCII 尾空白**（`[ \t\r\n]`），
    //     不用 JS 的 `\s`（**含 U+3000**）、也不用 bash 的 `[[:space:]]`（**看 locale**）——
    //     那两个在两端会对不齐，而「对不齐」的表现就是**静默拒收**。
    const textForKey = String(text ?? '').replace(/[ \t\r\n]+$/, '');
    const textSha8 = crypto.createHash('sha256').update(textForKey, 'utf8').digest('hex').slice(0, 8);
    // 链自己那份内容 ID（`AUTO-<sha256(文本)[:12]>`）—— 拿它当**第二把锁**：
    // 两把锁任意一把对上就认（同一内容的不同问法走这条），**两把都对不上才拒**。
    const contentId = reviewPublish.contentIdOf(String(text ?? ''));
    try {
      // cwd 必须是知识库工作区：链上每一步都按 `kb/...` 相对路径找脚本，
      // 而且 AGENTS.md 的工作区指令由 cwd 决定 —— cwd 不对，跑出来的就不是那条链。
      const { stdout } = await execFileP('node', [DSH_BIN, '--profile', 'headless', task], {
        cwd: KB_ROOT, timeout: KB_REVIEW_TIMEOUT_MS, maxBuffer: 8 << 20,
      });
      const answer = String(stdout ?? '').trim();
      if (!answer) {
        return {
          error: 'DSH 跑完但**没有输出最终回答** —— 链可能断在中途。**这等于结论未知，不是通过。**',
          elapsed_ms: Date.now() - t0,
        };
      }
      const sidecar = readReviewSidecar(t0, textSha8, contentId, materialPath);
      // ★ 链已跑完、旁挂已读 ⇒ 素材文件**用完就删**（三档结局都走这里之外的 catch 也删）
      cleanupMaterial();
      // ★★ 2026-10-08（第七批）：**把「链到底给了我们什么样的回答」原样留一份**。
      //   为什么要留（**这是我自己踩的坑，记在这免得再踩**）：
      //     我改 `dual_track.kbFindingsOf`（结构化优先）时，拿**引擎的原始 stdout**
      //     当样本验的 —— 那片 JSON 里有完整的 `risk_items`（条款号/锚点/`l0_entry_url`），
      //     测下来「全绿」。**而守衡真正拿到的是 `answer` = headless agent 的最终回答**，
      //     那是**模型自己组织过的文本**，未必含原始 JSON。
      //     ⇒ 用错样本 ⇒ 线上依旧印「《知识库》（未给条款号）（锚点：—）」，而我的判据全绿。
      //   ⇒ 现在把 answer 落一份（**只留前 20000 字符**，够看形状），
      //     下一轮就能拿**真实样本**复现，不再靠猜。**排查用的中间件，不是产物。**
      try {
        const cap = path.join(KB_ROOT, 'kb/.work/last_chain_answer.txt');
        fs.writeFileSync(cap, `# at=${new Date().toISOString()}\n`
          + `# base=${sidecar?.base ?? '?'} ｜ answer 长度=${answer.length}\n`
          + answer.slice(0, 20000));
      } catch (e) {
        console.log(`[review] ⚠️ answer 留样没写成（不影响结论）：${e?.message ?? e}`);
      }
      if (!sidecar) {
        // ★ 缺旁挂要**出声**（库规：缺证据必须可见，不许静默）——
        //   但它**不阻断**：链本身跑成了，结论仍然照转述。
        console.log('[review] ⚠️ 没读到机读旁挂（kb/.work/last_review_result.json 缺失或不新鲜）'
          + ' ⇒ 本单的「问题数量/置信度」落表时会是空的。');
      }
      // ★★ 2026-10-08（第七批）：引擎 JSON（结构化逐条依据）—— 与旁挂同一条新鲜度纪律。
      //   读不到 / 不新鲜 ⇒ 不带这个字段，下游**原样退回**从 `answer` 抠中文的老路
      //   （不许因为新路没通就少报东西）。
      let engineJson = null;
      try {
        const ep = path.join(KB_ROOT, 'kb/.work/last_engine_out.json');
        const raw = fs.readFileSync(ep, 'utf8');
        const at = fs.statSync(ep).mtimeMs;
        if (Number.isFinite(t0) && at >= t0 - 2000) engineJson = JSON.parse(raw);
        else console.log('[review] ⚠️ 引擎 JSON 不新鲜（早于本次起链）⇒ 不带结构化读数。');
      } catch (e) {
        console.log(`[review] ⚠️ 读不到引擎 JSON（${e?.code ?? e?.message}）⇒ 本单逐条依据退回从回答里抠。`);
      }
      return { ok: true, answer, elapsed_ms: Date.now() - t0,
               ...(sidecar ? { review: sidecar } : {}),
               // ★★ 2026-10-08（第七批）：**引擎 JSON 作为结构化读数带出去**。
               //   它是「逐条依据」的唯一权威源（条款号 / 锚点 / source_sha256 /
               //   命中片段 / `l0_entry_url` 飞书直链），由 `review_run.sh` 原样落盘。
               //   为什么不让下游从 `answer` 里正则抠：那是**模型组织过的散文**，
               //   措辞会变、≥3 条时还没有逐条行 ⇒ 抠不到就退回重建版（实测的病灶）。
               //   与旁挂同一条纪律：**只在新鲜时采纳**（`at` 必须晚于本次起链时刻）。
               ...(engineJson ? { engine: engineJson } : {}),
               // 自愈过就把这件事带出去（库规：缺前置/异常必须可见，不许静默）
               ...(pre.action ? { preflight: { action: pre.action, detail: pre.detail } } : {}) };
    } catch (e) {
      // execFile 超时后 kill 掉子进程：`killed` 为真或 `code` 为 null。
      const timedOut = e?.killed === true || e?.code === null;
      // ★ 素材文件用后即删（**失败路径也要删** —— 链跑败/超时同样不该把它留在盘上）
      cleanupMaterial();
      return {
        error: timedOut
          ? `审查链超时（${Math.round(KB_REVIEW_TIMEOUT_MS / 60000)} 分钟）—— **结论未知，不要当成通过**`
          : `审查链执行失败：${e?.message ?? e}`,
        ...(e?.stdout ? { partial_stdout: String(e.stdout).slice(-3000) } : {}),
        ...(e?.stderr ? { stderr: String(e.stderr).slice(-3000) } : {}),
        elapsed_ms: Date.now() - t0,
      };
    }
  },
});

/* ─────────────────────────── 对外暴露 ─────────────────────────── */

export const TOOL_SCHEMAS = defs.map((d) => d.schema);

const byName = new Map(defs.map((d) => [d.name, d]));

export function toolNames() { return defs.map((d) => `${d.name}(${d.scope})`); }

/**
 * 执行一个工具调用。任何异常都被兜住并转成结构化错误 ——
 * 工具炸掉不应该让整条回复消失，守衡应当能告诉用户「我查这个失败了」。
 */
/* ═══════════════ 同一条链，一轮里只许跑一次（2026-10-08）═══════════════
 *
 * ── 为什么需要这一块：实测的一次真实事故（Owner 2026-10-08 19:08 那张图）
 *
 *   19:08:55  有人发图 @守衡
 *   19:09:00  回执卡「⏳ 处理中…」
 *   19:11:30  `🧭 送审链返回：跑成｜147386ms`       ← 闸门跑完了，2.5 分钟
 *   19:11:30  `🧭 落表：updated｜recvxsiDhAWPoU`    ← 结论也落库了
 *   19:23:55  `🔧 工具: kb_review_chain(709739ms)`  ← ★ 模型**又自己跑了一遍**
 *   19:23:57  回复 3159 字，耗时 **900041ms**
 *
 *   也就是说：**2.5 分钟就判完了，人等了 15 分钟。** 而且第二遍那 709 秒
 *   **超时没出结果**，模型就把这句写进了对外卡片：
 *   「我这次实跑 709 秒没出最终回答（结论未知，非通过）」——
 *   业务同事收到的是**内部故障自述**，还带着自相矛盾的数字（抬头 12 处 / 正文 5 处）。
 *
 * ── 为什么会各跑一遍：两个各自都对的部件合起来必然撞车（`AGENTS.md` §2.4.5）
 *
 *   · 闸门：`defaultChainRunner` → `executeTool('kb_review_chain', …)`（`agent.mjs`），
 *     跑完把结论注入提示词（`chainBlock`）。它以为「跑完了模型就知道」。
 *   · 人设：`persona.mjs` 写着「这类问题，走 `kb_review_chain`」。它以为「没人跑过」。
 *   **两边都不知道对方存在**，盘上没有任何一处告诉模型「链已经跑完了」。
 *   历史读数：闸门跑成 **72** 次，模型自己又调 **18** 次 —— 不是偶发。
 *
 * ── 代价不止是慢
 *
 *   工具描述自己写着「**这是一次真实发布动作**」：重跑 = 往飞书**再写一遍**，
 *   而第二遍**没有**闸门那行 `落表` 记账。所以这一块同时修两件事：延迟 + 重复写。
 *
 * ── 判据为什么定在 `executeTool`（唯一漏斗），不是 `kb_review_chain.run`
 *
 *   闸门与模型**都**经 `executeTool`（前者经 `defaultChainRunner` 转发）。
 *   装在漏斗上，一处就盖住两条路 —— 与 §2.4「上限必须有执行点」同一条思路：
 *   执行点越少越好，且必须**能指出是哪一行在拦它**。
 *
 * ── 三道护栏，缺一道都可能出错（方向不对称：漏跑只是慢，**串轮是答错**）
 *
 *   ① **每轮清空**：`agent.mjs` 在调闸门**之前**调 `beginChainTurn()`。
 *      漏了它，上一轮的结论会被下一轮拿去答一张**没审过的图** —— 这是唯一危险的方向。
 *   ② **TTL**：`CHAIN_MEMO_TTL_MS`。独立于 ① 的第二道，专治「某条路径绕过了 ①」。
 *      链本身要跑十几分钟，所以 TTL 从**跑完**那一刻起算，不是从起跑。
 *   ③ **命中要出声**：每次命中打一行 `[agent] ♻️`，并有 `chainMemoStats()` 计数。
 *      否则「它到底有没有生效」只能靠猜（§2.4：没红过的断言不算验证过它）。
 */
const CHAIN_MEMO_TOOL = 'kb_review_chain';
const CHAIN_MEMO_TTL_MS = 30 * 60 * 1000;

let chainMemo = null;      // { at:number, envelope:{tool,ok,result} } —— 只装**跑成**的结果
let chainMemoHits = 0;

/** 一轮的边界：清空上一次的记忆并结算命中数。返回**上一轮**命中了几次。 */
export function beginChainTurn() {
  const prevHits = chainMemoHits;
  chainMemo = null;
  chainMemoHits = 0;
  return prevHits;
}

/** 给日志/`meta` 用的读数：这一轮命中过几次、现在有没有装着缓存。 */
export function chainMemoStats() {
  return { hit: chainMemoHits, armed: !!chainMemo };
}

/* ── 两条**纯**判据。为什么要单独抽出来（§2.4：判据要能被调用）───────────────
 * 真跑一遍 `executeTool('kb_review_chain', …)` 会**真的起一条链、真的写飞书**
 * —— 拿它当自证手段，正是 §2.4.4 那个病（跑一次自证，改掉了它要保护的东西）。
 * 所以「该不该回缓存」「该不该装缓存」这两跳必须是**纯函数**：
 * 断言直接喂构造出来的 memo/result，一次副作用都不产生。
 */

/** 该不该回缓存。命中返回那个信封，否则返回 null（null = 照常真跑）。 */
export function chainMemoLookup({ name, memo, nowMs = Date.now() } = {}) {
  if (name !== CHAIN_MEMO_TOOL) return null;      // 只管这一条链，别的工具照旧
  if (!memo || !memo.envelope) return null;       // 没装过
  if (!Number.isFinite(memo.at)) return null;     // 坏的记忆当没有 —— 宁可重跑，不可乱答
  if (nowMs - memo.at > CHAIN_MEMO_TTL_MS) return null;   // 过期
  return memo.envelope;
}

/** 该不该把这一次的结果装进缓存。**只装跑成的**：`{error}` 是「结论未知」。 */
export function chainMemoShouldArm({ name, result } = {}) {
  if (name !== CHAIN_MEMO_TOOL) return false;
  if (!result || typeof result !== 'object') return false;
  // 缓存一次失败 = 把「结论未知」钉死一整轮，后面每一次调用都拿不到重试的机会
  // —— §2.4.2：未测不许与通过长得一样。
  return !result.error;
}

/** 只给自证用 —— 让断言能从干净状态起跑、并能构造一个「已经跑过链」的现场。 */
export function _resetChainMemoForTest() { chainMemo = null; chainMemoHits = 0; }
export function _armChainMemoForTest(envelope, at = Date.now()) { chainMemo = { at, envelope }; }

export async function executeTool(name, argsJson) {
  const def = byName.get(name);
  if (!def) return { tool: name, ok: false, error: `未知工具：${name}` };

  // ★ 护栏：同一个漏斗、同一轮、同一条链 —— 第二次直接回缓存，不再真跑一遍。
  //   放在 `byName` 判定**之后**：未知工具仍照旧报错，缓存不改错误语义。
  //   放在解析参数**之前**：参数坏不坏都不影响「这一轮已经跑过了」这个事实，
  //   而缓存可用时无须为一个注定不执行的调用先解析 JSON。
  const hit = chainMemoLookup({ name, memo: chainMemo });
  if (hit) {
    chainMemoHits++;
    console.log(`[agent] ♻️ 这一轮**已经跑过链** —— ${name} 再调一次**回缓存、不重跑**`
      + `（省掉一次真发布动作：不重复写飞书、不再等十几分钟）`);
    return hit;
  }

  let args = {};
  if (argsJson && typeof argsJson === 'string') {
    try { args = JSON.parse(argsJson); }
    catch { return { tool: name, ok: false, error: `参数不是合法 JSON：${argsJson.slice(0, 200)}` }; }
  } else if (argsJson && typeof argsJson === 'object') { args = argsJson; }

  try {
    const result = await def.run(args);
    const envelope = { tool: name, ok: true, result };
    if (chainMemoShouldArm({ name, result })) chainMemo = { at: Date.now(), envelope };
    return envelope;
  } catch (e) {
    return { tool: name, ok: false, error: `${e?.name ?? 'Error'}: ${e?.message ?? e}` };
  }
}
