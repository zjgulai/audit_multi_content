# root-agent 来源筛选说明

## 筛选逻辑
按「哪个来源在哪个环节最成熟 / 最权威」来选，不全盘照搬，也不硬凑。

## 映射表（环节 → 来源 → 理由）

| 环节 | 来源 | 筛选理由 |
| --- | --- | --- |
| 编排层（元 agent 调度子 agent） | [openai/openai-agents-python](https://github.com/openai/openai-agents-python) | handoff / agent-as-tool / guardrails 最成熟的开源实现 |
| 编程式派生子 agent | [anthropics/claude-agent-sdk](https://github.com/anthropics/claude-agent-sdk-typescript) | Claude 子 agent 生成最落地 |
| 修复/优化（造/改 agent） | [anthropics/claude-quickstarts](https://github.com/anthropics/claude-quickstarts) + Claude Code subagents | 生成型元 agent 最成熟的开源参考 |
| 评测开放题裁判 | [metauto-ai/agent-as-a-judge](https://github.com/metauto-ai/agent-as-a-judge) | 「用 agent 评 agent」的开源实现（ICML 2025） |
| 难度方法论 | [GAIA](https://huggingface.co/datasets/gaia-benchmark/GAIA)（arXiv 2311.12983） | 唯一有官方 3 级难度（L1/L2/L3）的 benchmark |
| 维度参考 | [AgentBench](https://github.com/THUDM/AgentBench)（arXiv 2308.03688）· [SWE-bench](https://github.com/SWE-bench/SWE-bench)（arXiv 2310.06770） | 覆盖「通用助手 / 多环境 / 代码」三个方向 |
| 底层 LLM | [deepseek-ai/DeepSeek-V3](https://github.com/deepseek-ai/DeepSeek-V3) · DeepSeek-R1 | 被测 agent 可能调用的模型 |

## 两点诚实说明
1. OpenAI 的 **AgentKit（AgentBuilder）** 是托管产品，**未开源**，只能当「造 agent 的 agent」
   的产品级参考，不能直接引用代码。
2. **DeepSeek 官方没有元 agent 编排框架**，它只贡献模型（V3/R1）；编排能力靠
   OpenAI / Anthropic 两家的开源框架实现。
