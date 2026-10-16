# Eval Loop - 真实运行验证（对比评测循环）

**核心原则**: Iron Law 的 RED/GREEN/REFACTOR 必须**真跑**，不是手工填报告。

本方法把 `iron-law-testing.md` 的检查点升级为可执行的对比评测：用真实用户 prompt 同时运行 with-skill 和 without-skill 两个 agent，用断言判定 PASS/FAIL，量化差异。回答的唯一标准是：**带 skill 的结果有没有真的变好**。

## 何时使用

- 创建新 Skill 时验证"没有它 agent 会失败"（RED）
- 修改已有 Skill 时验证"新版比旧版好"（GREEN/REFACTOR）
- 发布前评估"这个 skill 到底值不值"

## 评测循环总览

```
准备评测集 → 并行运行 (with/without) → 断言评分 → 聚合基准 → 反馈重写 → 下一轮
```

## Step 1: 准备评测集 (evals.json)

每个 Skill 在 `evals/evals.json` 下保存评测集。字段规范见 `references/schemas.md`。

要点：
- 2-3 条**真实用户会说的话**（不是"测试 skill"这种空话）
- 每条配 `expected_output`（成功的样子）+ `expectations`（可验证断言列表）
- 断言必须客观可验证、有区分度：通过即"真做了"，不通过即"没做对"

## Step 2: 并行运行 with/without

对每条评测 prompt，**同一轮**启动两个运行：

| 运行 | 创建新 Skill | 改进已有 Skill |
|------|-------------|---------------|
| **with_skill** | 加载目标 Skill | 加载新版 |
| **without_skill** | 不加载任何 Skill | 加载旧版快照（改前先 `cp -r <skill> <workspace>/skill-snapshot/`） |

组织方式：
```
<workspace>/iteration-1/
├── eval-<id>/
│   ├── with_skill/outputs/     ← 带 skill 的运行结果
│   └── without_skill/outputs/  ← 基线运行结果
```

每轮迭代存到 `iteration-N/`，方便对比前后。

## Step 3: 断言评分 (grading)

对每个运行结果，逐条断言判定：
- **PASS**: 有明确证据且反映真实完成（不是表面合规——"文件存在"不等于"内容正确"）
- **FAIL**: 无证据、证据矛盾、或证据表面化

**铁律**: 举证责任在断言方——无证据即 FAIL。

对每条 FAIL，记录 `evidence`（引用具体输出/转写）。结果存 `grading.json`，字段规范见 `references/schemas.md`。

## Step 4: 聚合基准 (benchmark)

汇总所有运行的断言结果，输出对比：

| 指标 | 含义 |
|------|------|
| pass_rate | 断言通过率（with vs without 的 delta 是核心） |
| time | 平均耗时（skill 是否拖慢） |
| tokens | 平均 token（skill 是否更贵） |

**判定**:
- with 明显优于 without（pass_rate delta > 0）→ skill 有价值
- 两边差不多 → 断言可能非判别性，或 skill 无价值
- with 更慢更贵且提升有限 → 考虑删减 skill 内容

## Step 5: 反馈重写 (iteration loop)

- 把运行结果（qualitative 输出 + quantitative 数据）展示给用户
- 收集用户反馈，聚焦有具体投诉的用例
- 重写 skill → 进入 `iteration-N+1`
- 停止条件：用户满意 / 反馈全空 / 无实质进展

## 家族联动：内容评分与自动优化

内容静态评分与自动优化走 **root-skills 家族版**：

```text
内容评分 → 调用 root-skills-eval（六维度 + 触发评测 + 综合评分）
封顶后轨道 C < 85 或调用门槛未过 → 低分修复（建 {skill}-fix/ 副本，root-skills-opt 只改副本，不询问、不写回源）
封顶后轨道 C >= 85 且调用门槛通过 → 进入发布门禁（一次达标不必跑 opt；交付物就是正在创建的目录）
```

opt 永不把修复写回正在创建的 skill 目录。release 若走了修复，交付物是桌面与源并排的 `{name}-fix`，不是改过的源。

root-skills-eval 产出 YAML 评估报告，可直接作为 root-skills-opt 输入。本 Skill 只负责编排与动态评测，不重复实现静态评分逻辑。

## DSH 环境适配

- 用并行 subagent 实现 with/without 同时运行（一次调用同时启动）
- 定时/完成数据（total_tokens、duration_ms）在完成通知中捕获，立即存入 `timing.json`
- 无 subagent 环境：串行运行 + 跳过基线，仅作 sanity check（标注"降级模式"）

## 常见问题

**Q: 修改已有 Skill 需要 RED 吗？**
A: 需要。先跑旧版基线，再改、再对比。

**Q: 小改动也要全套评测？**
A: 影响核心流程的改动需要；局部小改可只跑相关 eval。

**Q: 如何判断 REFACTOR 足够？**
A: 压力场景变体（时间压力、模糊需求、异常输入）都能稳定通过，连续 3 次无新问题。
