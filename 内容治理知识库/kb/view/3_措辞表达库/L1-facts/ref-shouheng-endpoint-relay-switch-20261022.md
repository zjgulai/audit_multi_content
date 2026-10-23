---
asks:
  - 守衡的模型端点为什么从 DeepSeek 官方换到中转站？
  - 换端点时地址、模型名、密钥三件事应该怎么配才切得回来？
  - 中转站是否支持守衡需要的能力（工具调用 / 吃图 / 严格 JSON / reasoning_content 回传）？
  - 哪些模型不能用于画面层？
  - 中转站的 401 / 403 / 402 分别是什么意思、该怎么处置？
  - 密钥为什么不写在 plist 或仓库里？
collection: 3_措辞表达库
corroborated_by:
  - /Users/lute/project/audit_multi_content/tools/agent/config.mjs
  - /Users/lute/project/audit_multi_content/tools/agent/llm.mjs
  - /Users/lute/project/audit_multi_content/tools/test_agent.mjs
  - /Users/lute/project/audit_multi_content/PMO/守衡-端点切中转站-20261022.md
created_at: 2026-10-22
data_level: L2
evidence_group: coordinate
evidence_level: L2
forbidden: 不得把中转站当成“和 DeepSeek 官方同一把 key”；不得把画面层切到 deepseek-v4-pro（实测幻觉）；不得把密钥写进 plist 或仓库文件；不得在未按 §2.6 留痕的情况下把图片字节送到新服务商；不得声称“中转站上的 deepseek-flash 就是某个具体版本”。
half_life_days: 120
id: ref-shouheng-endpoint-relay-switch-20261022
kb_class: []
kind: fact
not_proves: 不证明中转站的算力与模型版本与 DeepSeek 官方一致；不证明长上下文、并发上限、限流策略这些未测项；不证明任何一张具体图片能被正确读出来（只证明这一层链路通）；不证明中转站额度充足；不证明线上已重启生效（重启需按 §2.7 取得同意）。
owner: 刘华丽
pii:
  detected: false
  masked: false
  strategy: 只记录端点配置、探针读数与口径变更，不记录密钥明文。
provenance:
  anchor: PMO/守衡-端点切中转站-20261022.md#切换前的能力探针（全部用**合成图**，没发任何客户素材）
  confidence: 确定
sensitivity_level: L2
source:
  captured_at: 2026-10-22
  fingerprint: c2aff9d661d3f231
  kind: file
  ref: /Users/lute/project/audit_multi_content/PMO/守衡-端点切中转站-20261022.md
summary: DeepSeek 官方端点额度耗尽（67 条 HTTP 402）使主模型/画面层/4B 同时失效，群里的回复退化为代码兜底；切到中转站前先探五项能力（文本、工具调用、吃图、reasoning_content 回传、严格 JSON），并把密钥独立成 SHOUHENG_LLM_API_KEY 落在 ~/.dsh/shouheng-llm.env，使「地址+额度」可一键切换与回退；§2.6 红线口径按日期变更。
tier: L1
title: "[规则执行] 守衡换模型端点：五项能力先探、密钥独立成变量、红线口径按日期留痕"
topic: 守衡模型端点/凭据与切换判据
valid_until: 2027-02-19
---

## 故障事实（2026-10-22 19:23–19:49 北京）

`PMO/logs/llm_failures.jsonl` 出现 **67 条** `HTTP 402 Insufficient Balance`（`model=deepseek-flash`、
`base_url=https://api.deepseek.com`、`retryable:false`）。三处调用同时失效：主模型（`llm.mjs`）、
画面层（`scene.mjs`）、4B 事实核查（`web_search`）。重启后启动横幅第一屏即
`画面层(吃图模型) = ❌ 不可用（HTTP 402）`。

**后果不是「慢」而是「答话退化成代码兜底」**：那段时间群里回复的正文是 `agent.mjs` 里拼出来的字符串，
模型一个字都没写 —— 包括 Owner 截图甩回来的那句「请重新发送原图」。

## 两个根因

1. **地址与密钥耦合**：`loadLlmKey()` 只认 `DEEPSEEK_API_KEY`。要换端点就得改这把 key，
   而「改 key」是**没有判据的动作** —— 改错了只表现为 401，读起来跟「端点坏了」一样。
2. **错误体形状不同**：中转站回 `{"error":"Invalid API key"}`（`error` 是**字符串**）与
   `{"error":{"code":"model_not_allowed"}}`。旧代码只读 `.error.message` ⇒ 把整段原始 JSON 当成"原因"。

## 修法与执行点

| 改哪 | 改什么 |
|---|---|
| `config.mjs` | 新增 `SHOUHENG_LLM_API_KEY`（环境变量 → 凭据库），**优先于** `DEEPSEEK_API_KEY`；新增 `apiKeySource` 并进 `describeConfig()`（横幅只打来源名，**不打值**） |
| `run_shouheng.sh` | 存在 `~/.dsh/shouheng-llm.env`（600）就 `.` 进去，并打印端点配置（地址+模型名，密钥不打） |
| `llm.mjs` | 错误体两种形状都认（字符串 / 对象），`code` 兼容顶层 |
| `agent.mjs` | `humanizeSceneError` 区分「密钥无效 / 模型名不被允许 / 额度不足」—— 三者处置完全不同 |
| `test_agent.mjs` | 假端点记录 `Authorization`：设了新变量必须**真的用它**，不设必须**退回** `DEEPSEEK_API_KEY`（反向对照） |
| `AGENTS.md` §2.6 | 红线口径**按日期**改：`不新增第三方` → `不新增第三方（2026-10-22 起该端点为中转站，Owner 已同意，见 PMO 件）`；其余约束一个字没松 |

## 切换前的五项能力探针（用 64×64 合成图，不发任何素材）

| 能力 | `deepseek-flash`（中转站） |
|---|---|
| 纯文本 | ✅ 798ms |
| 工具调用（`tools`） | ✅ `tool_calls=1` 且带 `reasoning_content` |
| 吃图（`image_url` + base64） | ✅「蓝色。右上角有白色。」 |
| `reasoning_content` 全量回传 | ✅ 200 |
| 吃图 + **严格 JSON**（画面层真正要的） | ✅ 直接 `JSON.parse` 过 |

**反向样本（重要）**：`deepseek-v4-pro` 对同一张纯蓝合成图编出「一个人低头看手机，
手机屏幕上显示微信红包详情页面」 —— 这是「假数据长得跟真数据一样」，画面层**不得**用它。

## 可复用要点

1. **切端点是一次口径变更，不是配置调整**：图片字节与素材文字会经过新的第三方 ⇒ 必须在 §2.6 按日期留痕。
2. **密钥要独立成变量**，否则「地址 + 额度」绑死，切回来还得改 key（而无判据）。
3. **换端点前先探五件事**，缺任何一件，坏掉的方式都不像「端点坏了」：文本、工具调用、吃图、reasoning 回传、严格 JSON。
4. **密钥不进 plist、不进仓库**（两者都在版本库里）；放 `~/.dsh/shouheng-llm.env`（600），删掉即一键切回默认端点。
5. launchd **不继承 shell 环境**，所以必须由启动器去读那个文件，而不是「顺手 export 一下」。
