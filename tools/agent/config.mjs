/**
 * config.mjs —— 守衡的配置与凭据装载
 *
 * 凭据来源（按优先级）：
 *   1. 环境变量
 *   2. ~/.dsh/credentials/shouheng-lark.json   （飞书应用）
 *   3. ~/.dsh/.credentials.yaml                （DSH 凭据库，取其 LLM key）
 *
 * 设计原则：凭据只在内存中流转，任何日志、任何落盘都不打印明文。
 */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

export const AGENT_DIR = path.dirname(fileURLToPath(import.meta.url));
export const TOOLS_DIR = path.resolve(AGENT_DIR, '..');
export const REPO_ROOT = path.resolve(TOOLS_DIR, '..');
export const LOG_DIR   = path.join(REPO_ROOT, 'PMO', 'logs');
// 状态目录：惰性解析，让 SHOUHENG_STATE_DIR 在测试里改了就能生效。
// 写成 import 时常量的话，一旦别的模块先加载了本文件，
// 后面再改环境变量就不会有任何效果 —— 而这种失效是静默的。
export function stateDir() {
  return process.env.SHOUHENG_STATE_DIR
    ? path.resolve(process.env.SHOUHENG_STATE_DIR)
    : path.join(REPO_ROOT, 'PMO', 'shouheng-state');
}
export const STATE_DIR = stateDir();   // 兼容既有引用；需要可覆盖语义时用 stateDir()

/**
 * 确保目录存在。失败只警告，不抛。
 *
 * 原来这里是 import 期无保护的 `fs.mkdirSync(...)`：只要状态目录的路径被一个
 * 同名**文件**占住（残留、误创建、磁盘异常都可能），mkdirSync 抛 EEXIST，
 * 整个进程在加载配置时就直接死掉 —— 守衡会彻底起不来，
 * 而报错指向 config.mjs，跟真实原因（一个占了位的文件）毫无关系。
 *
 * 目录建不出来不该阻止「读取配置」这件只读的事。
 * 真正需要写入的地方（flushSeen）会自己再 mkdir 一次，那里的失败是局部的、可报的。
 */
export function ensureDir(dir) {
  try {
    fs.mkdirSync(dir, { recursive: true });
    return true;
  } catch (e) {
    if (e.code !== 'EEXIST') {
      console.warn(`[cfg] 目录不可用（${dir}）：${e.code ?? e.message}`);
    }
    return false;
  }
}

ensureDir(LOG_DIR);
ensureDir(STATE_DIR);

/** 从 DSH 凭据库取一个 ref 的值（形如 `  KEY: value`） */
function readDshCredential(name) {
  const p = path.join(os.homedir(), '.dsh', '.credentials.yaml');
  let txt;
  try {
    txt = fs.readFileSync(p, 'utf8');
  } catch (e) {
    // 只有「文件不存在」才算正常的「这里没有」。
    // 权限错误、路径是目录等异常必须冒出来 —— 否则会被伪装成
    // 「Key 没配」，而真正的原因是读不到，排查方向会被带偏。
    if (e.code === 'ENOENT') return null;
    throw new Error(`读取凭据文件失败（${p}）：${e.code ?? e.message}`);
  }
  const m = txt.match(new RegExp(`^\\s*${name}:\\s*(\\S+)\\s*$`, 'm'));
  return m?.[1] ?? null;
}

function loadLarkCred() {
  const p = path.join(os.homedir(), '.dsh', 'credentials', 'shouheng-lark.json');
  const j = JSON.parse(fs.readFileSync(p, 'utf8'));
  if (!j.app_id || !j.app_secret) throw new Error('飞书凭据不完整：缺少 app_id / app_secret');
  return { appId: j.app_id, appSecret: j.app_secret };
}

function loadLlmKey() {
  return process.env.DEEPSEEK_API_KEY
      || readDshCredential('DEEPSEEK_API_KEY')
      || (() => { throw new Error('未找到 DEEPSEEK_API_KEY（环境变量与 DSH 凭据库均无）'); })();
}

export const config = {
  lark: loadLarkCred(),
  llm: {
    apiKey: loadLlmKey(),
    baseUrl: process.env.SHOUHENG_LLM_BASE_URL || 'https://api.deepseek.com',
    // deepseek-flash：快且便宜，适合群聊高频对话；复杂任务可切 deepseek-v4-pro
    model: process.env.SHOUHENG_LLM_MODEL || 'deepseek-flash',
    /** 单会话保留的最大历史轮数（超出后由记忆层压缩） */
    maxTurns: Number(process.env.SHOUHENG_MAX_TURNS || 24),
    /**
     * 单次回复上限。
     * 注意：DeepSeek 的 max_tokens 同时覆盖**思维链 + 正文**（usage.completion_tokens_details.reasoning_tokens）。
     * 实测 1600/4000 会被思维链吃光 —— finish_reason=length 且正文 0 字。
     * 所以这个值必须给足，且必须配合 finishReason 检查（见 truncate.mjs）。
     */
    maxTokens: Number(process.env.SHOUHENG_MAX_TOKENS || 12000),
    /** 工具循环最多迭代几次（防失控） */
    maxToolIters: Number(process.env.SHOUHENG_MAX_TOOL_ITERS || 6),
    /**
     * 思考模式下的 `reasoning_content` 回传（2026-09-30 加，P0）。
     *
     * ★ 依据是 DeepSeek 的硬性协议，不是我们的偏好。原文（Tool Calls 一节）：
     *   「对于携带 `tools` 参数的请求，`reasoning_content` **必须全量回传**给 API
     *     —— 包括没有发生工具调用的轮次。若代码没有正确回传，API 会返回 400。」
     *   https://api-docs.deepseek.com/guides/thinking_mode
     *
     *   守衡**每一轮请求都带 tools**（`TOOL_SCHEMAS`），所以这条规则一直适用。
     *
     * ⚠️ **但不要把它说成那次 400 的成因 —— 实测不支持这个归因。**
     *   2026-09-30 19:31 用真模型 + 真知识库跑了 A/B（同一条提问、同一份返回体，
     *   只切这一个开关），**关掉时同样不报 400，两边都正常答出 1100+ 字**：
     *
     *     | | 开关 ON | 开关 OFF |
     *     |---|---|---|
     *     | result | ok | ok |
     *     | HTTP 400 | 无 | 无 |
     *     | LLM calls | 3 | 4 |
     *     | prompt tokens | 56,225 | 89,022 |
     *
     *   而 `llm_failures.jsonl` 里那条 400（19:09:41）的**近因是上一条空 assistant 轮**
     *   （`{role:'assistant', content:''}`）—— 那一侧由 `memory.mjs` 的
     *   `isPersistable`（写入闸）+ `sanitizeForLlm`（回放闸）负责。
     *   所以本开关的地位是：**照协议补齐，不是修那条 400 的特效药。**
     *   协议的原文要求仍在，且上游随时可能开始严格执行；成本（思维链进上下文）
     *   由 `maxChars` 兜住，真出问题时用 `SHOUHENG_REASONING_PASSBACK=0` 一键回退。
     *
     * ⚠️ 回传**是有代价的**：文档说思维链会被拼进上下文 —— 而本次事故的根因
     *   恰恰是「上下文被塞爆 → 推理烧光输出预算 → 正文 0 字」。所以这里必须带
     *   **字数上限**，不许无界回传：单轮思维链实测可达 8000 token（≈3 万字），
     *   24 轮不设限就是 70 万字 —— 那会把刚修好的病再造一遍。
     *
     *   也可以整块关掉：`SHOUHENG_REASONING_PASSBACK=0`（用于 A/B 对照实测）。
     */
    reasoningPassback: {
      enabled: process.env.SHOUHENG_REASONING_PASSBACK !== '0',
      /** 单轮思维链回传上限（字）。超限处裁断，并留下可核对的标记。 */
      maxChars: Number(process.env.SHOUHENG_REASONING_MAX_CHARS || 6000),
    },
  },
  /**
   * 知识库（**本机**工作台的 kb-serve，只读 OpenAPI）。
   *
   * ★ 2026-10-05 更正：这里原来写「另一台机器上的 DSH 内容治理知识库，走 ngrok」，
   *   **与现状不符**。实测：凭据 `~/.dsh/credentials/shouheng-kb.json` 的 base_url 是
   *   `http://127.0.0.1:4401`（回环），而 `:4401` 是本机 DSH Desktop 托管的
   *   `kb-serve`（`/health` 自报 `db=…/工作台/var/workbench.db`，对外是**派生视图**）。
   *   守衡自己也在本机（launchd `com.shouheng.lark`）。用户态也没有设
   *   `SHOUHENG_KB_BASE_URL`（实测进程环境为空），所以走的确实是回环地址。
   *   ⚠️ 若将来真的改回「库在外机 + 隧道」，请把本注释与凭据一起改，**不要只改一处**。
   *
   * ★ 这里**只放一个开关，不在这里加载凭据**，有两个理由：
   *   1. 它是可降级的外部依赖 —— 服务端关机、隧道过期、域名变更都会让它不可用，
   *      而那是**正常运行状态之一**，不该让守衡整个起不来。凭据装载与失败话术
   *      都在 kb_client.mjs 里，由真正的调用点转成人话。
   *   2. 在 config.mjs 里 import kb_client 会绕成环（kb_client 要 import REPO_ROOT/STATE_DIR）。
   *
   * 设 SHOUHENG_KB_ENABLED=0 可以整块关掉。凭据见 ~/.dsh/credentials/shouheng-kb.json。
   */
  kb: {
    enabled: process.env.SHOUHENG_KB_ENABLED !== '0',
    // ★ 这里**故意没有** quotaPerDay。日上限的唯一真值源是服务端：
    //   检索响应里的 quota.limitPerDay（实测 1000）。本地再配一份，
    //   就是给「余额」造了第二个真值源 —— 上一版正是这么把 used=41
    //   报成余额的（服务端真值 292）。余额一律读 kb_client.quotaState()。
  },
  /** 允许守衡响应的群（空数组 = 不限制）。目前只放打通验证过的那个群。 */
  allowedChats: (process.env.SHOUHENG_ALLOWED_CHATS || '').split(',').map(s => s.trim()).filter(Boolean),
  /** 被 @ 才响应（群聊里避免刷屏）；私聊一律响应 */
  requireMentionInGroup: process.env.SHOUHENG_REQUIRE_MENTION !== '0',
};

/** 安全摘要，任何日志都可放心调用 */
export function describeConfig() {
  return {
    larkAppId: config.lark.appId,
    llmModel: config.llm.model,
    llmBaseUrl: config.llm.baseUrl,
    llmKeyLen: config.llm.apiKey.length,
    allowedChats: config.allowedChats.length ? config.allowedChats : '(不限)',
    requireMentionInGroup: config.requireMentionInGroup,
    maxTurns: config.llm.maxTurns,
    // maxTokens 必须进启动横幅：它是「回复被腰斩」的直接成因，
    // 之前 1600 这个值无处可见，事故发生时没人能一眼看出来。
    maxTokens: config.llm.maxTokens,
    // reasoningPassback 同理（2026-09-30 加）：它决定「每轮请求到底带不带
    // 思维链回传」。这个开关**会改变上行的报文体**，所以它必须和 maxTokens
    // 一样一眼可见 —— 否则一次 A/B 对照做完、忘了改回来，事后没人看得出来。
    // 打成 `on(≤6000字)` / `off` 这种一眼能读的形状，不要 `true` / `false`。
    reasoningPassback: config.llm.reasoningPassback.enabled
      ? `on（单轮 ≤${config.llm.reasoningPassback.maxChars} 字）`
      : 'off（SHOUHENG_REASONING_PASSBACK=0）',
  };
}
