# Root Skills Eval

> Skill 评估师 - 双轨评估（静态六维 + 触发评测 + 综合评分）

## 简介

`root-skills-eval` 对 Skill 进行**双轨评估**：

- **轨道 A（静态）**: 基于 Universal Skill Schema v1.1.0 的六维度深度评估 + loading/routing quality 检查，生成结构化 YAML 报告（原版全量保留）。
- **轨道 B（动态）**: A 卷按复杂度出题（简单 25 / 标准 50 / 复杂 100 条；正例/负例/近似/边界 4 类主类型 32%/32%/24%/12%，安全与组合为叠加标签）× 3 轮执行，回填真实结果。
- **轨道 C（综合评分）**: 按《企业 AI Agent Skill 创建评测研究报告》6.1 六维 100 分制评分。

**不含**: A/B 基准评分、token/time 消耗计算（按用户要求去除）。

## 核心特性

- **静态六维度评估**（保留原版）：
  - Schema 合规性 (20%) / Frontmatter 质量 (25%) / Body 内容质量 (30%)
  - 方法论审计 (15%) / 质量门槛达标 (10%) / 目录结构 (5%)
- **触发评测**（新增）：A 卷按复杂度出题（简单25/标准50/复杂100 条 × 3 轮；正例/负例/近似/边界 32%/32%/24%/12%，安全与组合为叠加标签），TP/FP/FN/TN → Precision/Recall/F1
- **安全/组合标签维度**：安全与组合为叠加标签（安全 简单≥4/标准≥6/复杂≥12 条；组合 简单≥4/标准≥8/复杂≥16 条），安全覆盖提示注入/敏感泄露/危险操作/路径越界 4 类攻击面、组合覆盖 4 类路由场景；全部通过 → Safety Boundary 高分；高危问题 → 封顶 C 级。**交付物必须包含安全/组合标签用例数量与执行情况**（最终报告「安全与组合标签用例统计与执行情况」区块，v3.9.0 硬校验）
- **综合评分**（新增）：Trigger Accuracy 25% / Output Quality 25% / Progressive Disclosure 15% / Safety 15% / Script 10% / Spec 10%
- 最终交付物为单一 HTML（v3.13.0）：`scripts/build-final-report.py` 合并多版本 YAML 生成**唯一最终报告**，顶部**目录**导航三大部分「📊 测试报告（原数据统计总览）/ 🧭 评测过程（评测 Skill 流程）/ 🧪 测试用例（逐条用例执行情况）」；低分修复才强制桌面校验（`--require-desktop-fix`），一次达标不加；出 HTML 前 check 用 `--validate-only`
- **全程自主执行**：出题后自动自检，随后自动完成 3 轮评测；低分自动修复，副本达标 + B 卷门禁通过后复制到解析出的**交付目标**（`references/batch-delivery.md`；缺省 `~/Desktop`）交付（**不写回被测 skill 原文**，源保持原样）

## 快速使用

```bash
# 轨道 A：静态六维评估
/root-skills-eval /path/to/skill-folder

# 轨道 B：触发评测（出题 → 自检 → 3 会话执行 → 评分）
# 出题提示词见 references/trigger-eval-cases.md

# 3 轮结果评分（v3.9.0：--json 输出安全/组合标签统计，供写入 YAML track_b）
python scripts/score-trigger-eval.py results.json --json summary.json

# 生成单版本 HTML 报告（中间产物，供核对）
python scripts/build-html-report.py {name}-evaluation-report.yaml \
    --summary {name}-evaluation-summary.md \
    --checks {name}.xlsx

# 生成测试用例 HTML（最终版 A 卷 / 调用 / 标签；已开卷加 --b-results）
python scripts/build-testcases-html.py --name {name} \
    --results results.json [--b-results b-results.json] --output {name}-test-cases.html

# 一次达标：生成最终报告（不加 --require-desktop-fix）
python scripts/build-final-report.py --name {name} \
    --version "源 v1.0.0" --yaml {name}-evaluation-report.yaml \
    --cases {name}-test-cases.html \
    --process {name}-evaluation-process.html \
    --output {name}-final-report.html

# 低分修复后：必须 --require-desktop-fix
python scripts/build-final-report.py --name {name} \
    --version "源 v1.0.0" --yaml {name}-evaluation-report.yaml \
    --version "第一次修复 v1.1.1" --yaml {name}-fix-evaluation-report.yaml \
    [--version "第二次修复 v1.2.0（最终）" --yaml ...] \
    --cases {name}-test-cases.html \
    --process {name}-evaluation-process.html \
    --require-desktop-fix \
    --output {name}-final-report.html

# check 放行（不生成 HTML）
python scripts/build-final-report.py --validate-only --name {name} \
    --version "最终" --yaml {name}-evaluation-report.yaml [--cases {name}-test-cases.html]
python scripts/build-testcases-html.py --check-only --name {name} --results results.json

# 可选：局域网辅助服务（免拷贝打开；最终交付物本身为单一 HTML，不依赖此服务）
python scripts/serve-lan.py --dir <交付目录> --port 8000
```

## 最终交付物（唯一最终报告 HTML，单一文档 + 顶部目录，任意网络/双击可开）

- `{skill-name}-final-report.html` - **唯一最终报告**：生成前经 check `--validate-only` / `--check-only`；**低分修复必须 `--require-desktop-fix`，一次达标不加**；生成后 `self_check_html` 失败不交付。`--cases/--process` 内联进 🧪 / 🧭。
- `{skill-name}-test-cases.html` 与 `{skill-name}-evaluation-process.html` - **中间产物/存档**（v3.13.0 起不再独立交付）：前者为测试用例 HTML（最终版 A 卷 + 调用逐条 + 标签（安全/组合）+ B 卷逐条或「B 卷未执行」+ 每轮原文，由 `scripts/build-testcases-html.py` 生成，`--b-results` 传入已开卷 B 卷）；后者为评测过程 HTML（Step 5.5 要求含「输出前自检」结论）。两者内容在生成最终报告时内联进唯一交付物。**📊 / 🧭 不贴这些逐条。**
- **交付方式**：提供 `{skill-name}-final-report.html` 文件本身（或任意静态托管/局域网服务地址）即为完整交付物——一个链接、任意网络可打开、无需拷贝其他文件

中间产物（不单独交付，供 opt/存档）：`{skill-name}-evaluation-report.yaml`（结构化报告，供 root-skills-opt 使用）、`{skill-name}-evaluation-summary.md`（摘要源稿）、`{skill-name}.xlsx`（Sheet1 用例 + Sheet2 静态测试 + 3 轮执行结果）。

## 评估流程（双轨）

```
轨道 A: 解析 SKILL.md → 六维度评分 → 问题分类 → YAML 报告
轨道 B: 按复杂度出题（25/50/100 条，安全/组合叠加标签）→ 自动自检 → 3 会话 × 3 轮执行 → 回填
轨道 C: TP/FP/FN/TN 归类 → P/R/F1 → 六维 100 分制 → 等级
交付:   评分 →（如需）修复与 B 卷 → check --validate-only → 生成 HTML（修复路径加 --require-desktop-fix）→ 交付单一 HTML
```

## 发布门槛

三道门槛不得混用（详见 `references/comprehensive-scoring.md`）：

| 决策 | 标准 |
|------|------|
| 要不要修 | 封顶后轨道 C **< 85**（不要用 ≤85）或轨道 A 仍有 error 或 **调用门槛未过** |
| 修完交付副本 | 封顶后轨道 C **≥ 85**（已蕴含 Output ≥ 15）且 B 卷 F1 ≥ 0.85、无高危安全 FP、**调用门槛通过** |
| 能不能标可发布 | `track_c.market_ready`：封顶后轨道 C **≥ 85**、Output ≥ 15、无 error 封顶、**调用门槛通过**（v3.17.4：与修复退出同线；研究报告 80 仅 B 级等级参考） |
| 生产就绪 | 轨道 C ≥ 90 |
| 轨道 B 企业门槛 | P ≥ 0.85，R ≥ 0.85，F1 ≥ 0.90（F1 < 0.85 必须优化 description 重测；这是 **B·F1门槛**，不单独构成可发布） |

**轨道 A 总分仅内容质量参考**：不直接构成任何门槛；A 的 error 级问题经 `issues` → 轨道 C 封顶 ≤79 间接生效（见 `comprehensive-scoring.md` 特殊规则 1）。

## 目录结构

```
root-skills-eval/
├── README.md                 # 本文件
├── SKILL.md                  # Skill 定义（双轨评估流程）
├── .skill-meta/
│   └── manifest.yaml         # 元数据
├── scripts/
│   ├── validate-skill.py     # 基础结构验证（原版）
│   ├── score-trigger-eval.py # 触发评测 3 轮评分（含安全/组合叠加标签判定 + --json 标签统计输出）
│   ├── build-html-report.py  # YAML+摘要 → 单版本 HTML 报告（中间产物）
│   ├── build-final-report.py # 多版本 YAML → 唯一最终报告（多次数据对比 + 安全/组合标签统计 + 修复清单）
│   └── serve-lan.py          # 局域网 HTTP 交付服务
├── references/
│   ├── evaluation-guide.md   # 详细评估指南（原版）
│   ├── scoring-criteria.md   # 评分标准详解（原版）
│   ├── loading-routing-evaluation.md # 加载与路由评估模板（原版）
│   ├── batch-evaluation.md   # 批量评估（原版）
│   ├── universal-skill-schema.md    # Schema 标准源（原版）
│   ├── trigger-eval-cases.md # 触发评测出题/执行提示词（按复杂度出题，含安全/组合叠加标签）
│   ├── comprehensive-scoring.md     # 综合评分模型 6.1（含安全标签规则）
│   └── low-score-repair-flow.md     # 低分修复流程（封顶后轨道 C < 85 自动修复，不询问）
├── examples/                 # 示例报告
└── tests/                    # 测试用例
```

## 与 Opt 的联动

```bash
# 方式1: 评估后自动生成优化计划
/root-skills-eval /path/to/skill --auto-opt

# 方式2: 先评估，再优化
/root-skills-eval /path/to/skill
/root-skills-opt /path/to/skill-evaluation-report.yaml
```

opt 为家族版 `root-skills-opt`（v3.2.0+），直接接收本 Skill 的 YAML 报告。

## 相关 Skill

- `root-skills-check` - 出 HTML 前只读闸门（`--validate-only` / `--check-only`）
- `root-skills-opt` - 基于评估报告执行优化（家族版，读取 YAML 报告修复）
- `root-skills-doctor` - 结构/规范静态检查（前置）
- `root-skills-manage` - 家族管理器

## 版本

- 当前版本: 3.18.0
- 结构版本: 1.0
- Schema 版本: 1.1.0

### 版本历史

**v3.18.0** (2026-09-03): 用例区最终版口径固化——🧪 内通过率 / 逐条用例 / AI 原文一律取最终版（--cases 只内联最终版 test-cases.html），📊 / 🧭 保留不变、不贴逐条；轨道 A/B/C 计算公式分散放在各轨道数据/分项表下方（A 在 A 六维数据下、B 在 B 汇总下、C 在 C 分项下，区块开头保留隐藏 id=scoring-formulas 锚点），self_check 硬校验三个 📐 公式标题。

**v3.17.5** (2026-09-03): 分级复测——静态合规修复走静态复核模式不重跑 A 卷 3 轮，行为修复才全量重跑；批量评测前 doctor `--batch-preflight` 读 check `--export-top-defects` 预检。

**v3.17.4** (2026-09-03): 发布线统一为 85（market_ready 封顶后 ≥85，与修复退出同线；研究报告 80 仅 B 级等级参考）；轨道 A 计分示例统一 ÷105；安全高危（security_tag.high_risk>0）自动封顶 79 + market_ready=false；「轨道 A 仍有 error」进入修复口径三处补齐；scoring-criteria.md 停用旧 status/发布建议、明确 A 总分仅内容参考。

**v3.17.3** (2026-09-03): 最终版版本一致性——最终报告最后一版 eval_info.version 必须等于交付 fix 目录 SKILL.md version；生成最终报告后再改 fix（升版本/改 description/修 B 卷）必须同步重生成并替换最终报告；Excel/清单回填的 修复版本/首次C/修复后C/上线 必须与最终版 YAML/报告对账一致；fix 版本 > 报告版本或无报告支撑时禁止放行/标上线。

**v3.17.2** (2026-09-02): check 用 `--validate-only` / `--check-only` 放行（不写 HTML）；出报告顺序改为评分 → 修复/B 卷（如需）→ check → HTML；`--require-desktop-fix` 仅低分修复强制。

**v3.17.1** (2026-09-02): 「🧪 测试用例」必须输出最终版 A 卷、B 卷、调用、标签用例（安全/组合）；`--b-results` 传入已开卷 B 卷；📊 / 🧭 章节不贴逐条。

**v3.16.9** (2026-09-01): 输出前闸门——漏数据先补齐、全部用例 AI 回复不是原文的改回会话原文，都检查过了才输出报告；截断/摘要回复拒绝生成。

**v3.16.8** (2026-09-01): 最终报告一·补写明轨道 A/B/C 计算公式（A=加权÷105，B=三轮 F1 平均，C=六维相加）；缺公式拒绝生成。

**v3.16.7** (2026-09-01): Release 清单评测已有 Skill 必须先读本轮 A/B 卷——第 9 项四类已执行不得 fail；第 3 项不得写成「没评测」；evidence 必填。
**v3.16.6** (2026-09-01): 报告不得空发——轨道 B 每轮 TP/FP/FN/TN（含 YAML 小写 tp/fp/fn/tn）、轨道 C 评分依据、AI 回复必须是会话原文（禁模板）；标签表只列安全/组合并展示原文，调用不重复。
**v3.16.5** (2026-09-01): 调用门槛挡上线——不进 F1，但未过则不可发布、进入修复、禁止交付副本；至少 3 条覆盖三种斜杠路径。
**v3.16.4** (2026-09-01): 正例中英混写改为必出配额，占原全英文份额、不占纯中文（简单 3 / 标准 6 / 复杂 12）；全英文只留触发探测（1/2/4）；出题自检 16→17 项。
**v3.16.3** (2026-09-01): 调用不进测试用例 HTML 占比分母；通过率按加载/未加载计（禁止 0/0 红标）；`--json` 自行计算 flaky；调用结论主语=本 Skill。
**v3.16.2** (2026-09-01): 调用场景 + 中英触发出题规则；description 压回 ≤1024（交付排版下沉正文）；版本同步 registry / README / manifest。
**v3.16.1** (2026-09-01): 正文去沉积（规则不删）——版本史/交付物/依赖去重述；评分与用例维度保留。
**v3.16.0** (2026-09-01): 三道门槛收口 + 对比表审计底稿——进入修复用封顶后轨道 C &lt; 85（不用 ≤85）；退出 ≥85；可发布只看 `market_ready`；对比表含 Output / 封顶前总分 / 可发布；封顶是「最高」不是「等于该档」；opt 读封顶后轨道 C。
**v3.15.0** (2026-09-01): 报告输出与评分特殊规则——一·补顺序 A→B→C；轨道总分缺失不得视为 0；可发布只看轨道 C；Output&lt;15 封顶 79；自检 15 项 + 盲测关键词；NA≠FIXED。
**v3.13.3** (2026-09-01): 中文最终包——Unicode name 与目录一致即通过、kebab-case 记 na；低分修复禁止改回英文；单包 `skills._shared` 记 warning。
**v3.13.2** (2026-09-01): 盲测执行——回填员读完整表，被测会话只收「提示词」列；类型/标题/预期结果/标签不进被测会话；输出前自检 14→15 项（盲测校验）。
**v3.13.1** (2026-09-01): 出题提示词改为自包含写法门禁——有资料则内嵌短样本、无资料则声明自行搜索；同一条发给 dsh 与 Codex 可执行；不设有资料/无资料条数下限，自检第 6 项按写法检查。
**v3.13.0** (2026-09-03): 交付物收敛为**单一 HTML + 顶部目录**——最终报告为唯一交付物，顶部目录导航三大部分「📊 测试报告（原数据统计总览）/ 🧭 评测过程（评测 Skill 流程）/ 🧪 测试用例（逐条用例执行情况）」；`--cases/--process` 传文件路径时其内容（含样式，作用域隔离）内联进对应部分（标签用例逐条执行情况 + 每轮 AI 原文回复 + 出题自检/低分修复/B 卷门禁/输出前自检全部并入同一文档）；移除 v3.12.0 底部跳转链接与 v3.10.0 iframe 内嵌；测试用例/评测过程 HTML 改为中间产物/存档；self_check 校验目录与三大部分（测试用例部分必含「全部用例与每轮 AI 原文回复」、评测过程部分必含「输出前自检」）。
**v3.12.0** (2026-09-03): 安全/组合标签用例统计汇总并入「二、测试用例分配比例」（格式不变），逐条执行情况移至测试用例 HTML「标签用例逐条执行情况」区块；六/七 不再内嵌 iframe、改为最终报告底部跳转链接（测试用例/评测过程独立 HTML 一并交付）。
**v3.11.0** (2026-09-03): 移除「安全写回」——低分修复只在 `{skill}-fix/` 副本上进行，副本达标 + B 卷门禁（F1 ≥ 0.85 且无高危安全 FP）通过后复制到桌面与源并排交付，被测 skill 原文（含桌面源）任何情况下不写回；`--require-desktop-fix` 桌面校验中源为只读参照；B 卷门禁由「写回前」改为「副本交付前」。

**v3.10.1** (2026-09-03): 测试用例 HTML 强制 AI 原文回复（逐字保留，禁止提炼/概括/截断）；新增 `scripts/build-testcases-html.py` 规范生成器（从评测结果 JSON 渲染全量原文 + 原文回复自检：3 轮回复非空、无截断/提炼标记，失败 exit 2）；执行指令与输出前自检同步（13→14 项，新增原文回复校验）。

**v3.10.0** (2026-09-03):
- 交付物收敛为**单一自包含 HTML**：最终报告内嵌测试用例与评测过程（iframe），底部页内锚点链接，任意网络/双击可开，不再依赖局域网服务与兄弟文件
- 交付前**桌面校验**（`--require-desktop-fix`）：源 Skill 与 `{name}-fix` 修复副本必须先放桌面（缺失自动从工作区复制，否则拒绝生成）
- Release 10 项审查清单新增**「是否影响上线」**列：fail 项必须标注 impact（影响上线/不影响上线），🔴 影响上线 = 发布阻断项
- 输出前**脚本自检**（`self_check_html`）：区块齐全 / 百分比健全（杜绝 1632.0% 类比例异常）/ 无 NaN / 表格单元格无类型标签数字粘连 / 链接可解析，失败 exit 2 不交付；表格单元格自带分隔（文本化不粘连）
- 输出前自检 10→13 项（新增桌面交付校验 / HTML 输出自检 / Release 影响上线判定）；validate_report_data 新增单项百分比与 fail 项 impact 硬校验

**v3.9.1** (2026-08-31): 修复 HTML 渲染器的 Python 3.9–3.11 兼容性、危险链接 scheme 与列表闭合，新增报告回归测试。

**v3.9.0** (2026-09-03): 交付物必须包含安全/组合标签用例统计与执行情况——最终报告新增「安全与组合标签用例统计与执行情况」区块（安全/组合用例数量 + FP/高危 + 逐条 3 轮执行结论）；build-final-report.py 硬校验 track_b.security_tag/combo_tag/tag_cases（缺失拒绝生成）；score-trigger-eval.py 新增组合标签汇总与 --json 输出；输出前自检 9→10 项。

**v3.8.1** (2026-09-02): 输出报告数据格式硬校验（distribution 条数/百分比 + release_checklist 10 项，失败拒绝生成）；flaky 计数剔除空占位；输出前自检 7→9 项。

**v3.8.0** (2026-09-02):
- 最终报告新增「Release 发布前 10 项审查清单」区块（逐项判分 + 通过标准 + 对应参考）

**v3.7.0** (2026-09-02):
- A 卷按复杂度出题：简单 25 / 标准 50 / 复杂 100 条（正例/负例/近似/边界 32%/32%/24%/12%）
- 安全与 Skill 组合改为叠加标签（不占总数）：安全≥4/6/12，组合≥4/8/16（按复杂度）
- B 卷固定 10 条（正例3/负例3/近似3/边界1，安全标签≥2 + 组合标签≥2 可重叠）
- 用例表新增「标签」列；评分脚本支持叠加标签判定

**v3.6.0** (2026-09-02):
- 双卷制：出题生成 A 卷 50 条 + B 卷 10 条留出题（封印，修复流程不可见）；低分修复写回前执行 B 卷最终门禁（F1 ≥ 0.85 且无高危安全 FP 才写回）；自检 12→14 项；最终报告含 A/B 卷成绩（借鉴 SkillOpt held-out gate）

**v3.5.0** (2026-09-01):
- 全程自主：出题、自检、三轮评测、低分修复、达标写回均不等待用户确认
- 写回前自动备份，写回后自动验证，失败自动回滚

**v3.4.0** (2026-09-01):
- 最终交付物标准：交付物统一为 HTML 链接；测试报告只保留一份最终报告（build-final-report.py 合并多版本 YAML，内含 源→第一次修复→第二次修复 三次数据对比 + 修复问题清单）；测试用例与评测过程各一份独立 HTML；YAML/Excel 降为中间产物

**v3.3.2** (2026-09-01):
- 低分自动修复硬性规则（不询问用户、停滞检测、写回前 diff 确认）

**v3.2.0** (2026-08-30):
- 安全测试维度：50 条用例重配（正例16/负例14/近似10/边界4/安全6），覆盖提示注入/敏感泄露/危险命令/路径越界
- HTML 交付：build-html-report.py 生成总结论+摘要 HTML 报告；serve-lan.py 局域网 HTTP 链接交付
- 报告优化：总结论区块 + 人类可读摘要内嵌 + 专业排版

**v3.0.0** (2026-08-27):
- 双轨评估：保留静态六维 + 新增触发评测（50 条 × 3 轮）
- 综合评分对齐研究报告 6.1（不含 A/B 与 token/time）
- 触发评测用例出题/执行提示词固化
- 归属 root-skills 家族

**v2.1.0** (2026-05-31):
- 新增加载与路由质量评估模板
- 明确 negative loading 和 boundary cases 对评分的影响

**v2.0.0** (2026-04-02):
- 重构为六维度评估体系
- 目录结构权重从 15% 降至 5%

**v1.0.0**:
- 初始版本，五维度评估

## 兼容性

| 平台 | 状态 | 备注 |
|------|------|------|
| Claude | native | 完整支持 |
| Cursor | native | 完整支持 |
| Kimi | native | 完整支持 |
| GPT | bridge | 支持评估，输出需适配 |
| MiniMax | bridge | 支持评估，输出需适配 |

---

**双轨评估** | **内容导向** | **Schema 标准** | **框架**: root-skills
