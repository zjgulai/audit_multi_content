# 规格 → agent.yaml 十字段映射

这一步模型默认会做错：把规格散文整段抄进 yaml，字段对不上，`deliverables` 和业务对不齐。**必须逐字段对照本表。**

---

## 一、十字段契约

```yaml
name: <kebab-case>
version: "<语义化版本>"
interface: cli | http | sdk
run: <启动命令，必须真的可执行>
input: stdin-json
profile: general | code | web-ops
task_types: [...]        # 能承接的维度（说"怎么答"）
deliverables: [...]      # 交出去的东西（说"交什么"）
tools: [...]             # 工具清单（资格判定用）
env: {...}               # 密钥一律 ${managed} 注入
```

| 字段 | 含义 | 决定什么 |
|---|---|---|
| `interface` | 对外形态 | 怎么被调用 |
| `input` | 统一输入协议 | 当前固定 `stdin-json` |
| `profile` | 场景档位 | **维度权重** |
| `task_types` | 能承接的维度 | 出题时哪些维度可出 |
| `deliverables` | 交出去的**东西** | **这个 agent 能干几件活** |
| `tools` | 工具清单 | 出题资格：`case.tool_required ⊆ agent.tools` |

---

## 二、规格段落 → 字段映射

| 规格段落 | 映射到 | 映射规则 |
|---|---|---|
| 实现决策 · 要建/改的模块、接口、架构决策、API 契约 | `interface` / `input` / `profile` | 按对外形态选 `interface`；按场景选 `profile`（通用 `general`、写代码 `code`、网页运营 `web-ops`） |
| 实现决策 · 能力范围（要它干哪些类型的活） | `task_types` | 从六维里挑，**只挑真的会承接的**；挑了就要能被出题 |
| 实现决策 · schema 变更、技术澄清 | `deliverables[].fields` | 每个交付物的字段清单 |
| 用户故事 + 交付物 | `deliverables[]` | 按"交出去的东西"分组，见 `deliverables-rules.md` |
| 实现决策 · 依赖的外部能力 | `tools` | 每个工具写 `name` / `description` / `schema` |
| 附注 · 密钥、端点 | `env` | **一律 `${managed}`，禁止字面量** |
| 测试决策 | 不落 yaml | 影响的是出题方式与判分口径 |
| 范围外 | 不落 yaml | 用来写**职责负例**（不该答什么） |

---

## 三、`task_types` 怎么选（六维）

| 维度 | 什么时候选 |
|---|---|
| `fact_qa` | 有确定答案的事实问答 |
| `reasoning` | 需要多步推理/比较/取舍 |
| `multi_turn` | 需要多轮澄清、上下文承接 |
| `instruction` | 要严格遵守格式/步骤约束 |
| `rag` | 要基于给定资料作答并引用 |
| `safety` | 有明确禁区（这个维度通常都要选） |

**反例**：写代码的 agent 选 `web-ops` —— `profile` 和实际场景不符，维度权重错位，评测分数失真。

---

## 四、完整示例

### 规格里的相关片段

```
实现决策：
- 对外提供一个命令行工具，通过 stdin 读 JSON 请求
- 需要接品牌知识库检索、需要一个计算器做折扣核算
- 请求字段：question（必填）、channel（可选）
- 密钥从环境变量读，不得写入代码

用户故事：
- 作为品牌运营，我想要快速查到一个品牌的历史活动与合规口径，以便回复代理商
- 作为品牌运营，我想要每周拿到一份问题汇总，以便在周会上同步
```

### 映射结果

```yaml
name: brand-pr-agent
version: "0.1.0"
interface: cli
run: python3 agent.py
input: stdin-json
profile: general
task_types: [fact_qa, reasoning, multi_turn, instruction, rag, safety]
deliverables:
  - id: answer
    name: 业务答复
    format: text
    fields: [结论, 依据]
    acceptance: 先给结论再给依据；引用资料时标出来源；没有依据就明说没有，不编造
  - id: weekly_report
    name: 周度问题汇总
    format: markdown
    fields: [本期问题TOP5, 处理率, 待办]
    acceptance: 数字和台账对得上；对不上的在报告里注明差异原因
tools:
  - name: search_kb
    description: 检索品牌知识库
    schema: {}
  - name: calculator
    description: 数值计算
    schema: {}
env:
  API_KEY: ${managed}
```

对照检查：两个用户故事 → 两件活（答复 / 周报），交出去的东西确实不同 ✔；`question` 是输入字段，落到 `input` 协议的约定里，不进 `deliverables` ✔；密钥走 `${managed}` ✔。

---

## 五、五类常见错误

| 错误 | 症状 | 修法 |
|---|---|---|
| 散文直搬 | yaml 里出现整段中文描述、有"等""例如" | 只留字段值，描述性内容进 `description` |
| 字段漏项 | 规格提到 3 个接口，yaml 只写 1 个 | 反向核对：规格每个实现决策都要有落点，落不上的明确写"不落 yaml，原因…" |
| 交付物虚高 | `deliverables` 里混了工具/约束/变体 | 过 `deliverables-rules.md` 的三条淘汰规则 |
| `acceptance` 写成实现细节 | 出现"返回""调用""断言" | 翻译成业务方看得懂、判得了的句子 |
| 字面量密钥 | `env: {API_KEY: sk-xxx}` | 改 `${managed}`。这是**硬门禁**，不通过 |

---

## 六、自检

```bash
python3 scripts/render-contract.py spec.md      # 生成草稿（确定性字段自动填）
python3 scripts/check-flow.py <项目目录>         # 校验契约合规性
```

`check-flow.py` 会检查：十字段齐全、`deliverables` 每件活字段非空、`acceptance` 无实现细节关键词、`env` 无字面量密钥、`run` 命令可解析。**警告不阻断，错误阻断。**
