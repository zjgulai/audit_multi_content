# root-skills-opt 版本历史
## v3.6.0 (2026-09-04)

- **交付目标可配置（不写死路径）**：与 eval 同一交付契约（`references/batch-delivery.md`）。完成副本写入解析出的 `done_dir`，支持 `.batch.yaml`（`source_dir`/`done_dir`/`report_dir`/`keep_fix_suffix`/`dedupe`）；命名随 `keep_fix_suffix`，目标已存在默认 `dedupe=newest` 保留最新。缺省仍回退 `~/Desktop` 与源并排。
- 配套 Eval 版本 3.19.0。


## v3.5.7 (2026-09-02)

- 出最终 HTML 前调用 check 时，使用 eval `--validate-only` / `--check-only`，不重走出题或三轮。
- 配套 Eval 版本 3.17.2（只读闸门 CLI + 一次达标不加 `--require-desktop-fix`）。

## v3.5.6 (2026-09-01)

- **读取 `release_checklist`**：fail 项进入 `plan-fixes.py`。id 2/4/5/6/7/8/10 在副本补 SKILL.md（第 10 项 R010：维护与退役，不写家族注册表）。id 1/3/9 只复判：第 9 项本轮四类已执行则改为 pass，禁止新造评测文件；第 3 项禁止补造历史 RED。
- 配套 Eval 版本 3.16.9（含输出前闸门 Step 5.4）

## v3.5.5 (2026-09-01)

- **跨成员引用口径**：输出格式不再把 eval 的 `low-score-repair-flow.md` 写成 opt 本地 `references/` 路径；改为「与 eval 的低分修复流程同一口径」。规则本身未改。

## v3.5.4 (2026-09-01)

- **调用门槛**：`effective_track_c()` 读 `track_b.call_tag.passed_gate`。新报告未过 → 不可发布、不能退出修复（C≥85 仍进修复）。旧 YAML 无 call_tag 不挡。
- 配套 Eval 版本 3.16.5

## v3.5.3 (2026-09-01)

- **正文去沉积（规则不删）**：输出格式 / Eval 循环 / 训练纪律去掉重复叙述；S001、budget、留出门、封顶后轨道 C、B 卷 F1、不写回、循环终止条件均保留。
- 配套 Eval 版本 3.16.1

## v3.5.2 (2026-09-01)

- **达标读封顶后轨道 C**：`plan-fixes.py` 新增 `effective_track_c()`。YAML 88 + Output 12 → 有效 79，未达修复退出线 85；Output 缺失不得视为及格；error 同样最高 79。
- 配套 Eval 版本 3.16.0（三道门槛：<85 进 / ≥85 出；可发布看 `market_ready`）

## v3.5.1 (2026-09-01)

- **中文最终包（与 eval / doctor 同步）**：S001 仅修 ASCII kebab-case；中文 / Unicode 字母 name 记 na，禁止改回英文。单包 `skills._shared` 缺失不作为改 name 的理由。
- 配套 Eval 版本 3.15.0（eval v3.15.0：报告 A→B→C、Output&lt;15 封顶 79、可发布只看轨道 C）

## v3.5.0 (2026-09-03)

- **移除「安全写回」，改为「副本交付（不写回被测 skill 原文）」（用户规则）**：所有修复只在 `{skill}-fix/` 副本上进行，被测 skill 原文（含桌面源）**任何情况下不写回、保持原样**；副本达标（≥85）+ eval v3.12.0 B 卷门禁（F1 ≥ 0.85 且无高危安全 FP）通过后，把副本复制到**桌面（~/Desktop）与源并排**交付，删除原「自动备份源文件 → 写回 → 验证 → 回滚」步骤
- Step 5 验证流程同步：达标后先压缩打磨（保持 ≥85）→ dsh+codex 双端冒烟 → B 卷门禁 → 桌面副本交付；验证失败即停滞留档
- 配套 Eval 版本 3.10.1 → 3.12.0

## v3.4.1 (2026-08-31)

- 同步配套 eval v3.9.1，并接入家族根的一键依赖与验证门禁

## v3.4.0 (2026-09-02)

- **训练纪律（借鉴 microsoft/SkillOpt）**：留出验证门（`split-gate.py`，引导/留出切分 + 回归判定 exit 2）、编辑预算（`--budget` 默认 5/轮）、拒绝编辑缓冲（`rejected-edits.yaml`）、跨轮元记忆（`training-log.yaml`）、达标后压缩打磨与 dsh/codex 双端验收
- 修复计划生成器 `plan-fixes.py` 新增 `--budget/--rejected-edits/--training-log` 参数

## v3.3.0 (2026-09-01)

- **全程自主**：判断型修复采用有证据的最佳默认并记录假设，不等待用户确认
- **安全写回**：副本达标后自动备份、记录 diff、写回与验证，失败自动回滚

## v3.2.0 (2026-08-31)

- 引入 85 分修复闭环与同路径副本修复。旧版写回规则已由 v3.3.0 的全自主安全写回取代；更早变更见 README。
