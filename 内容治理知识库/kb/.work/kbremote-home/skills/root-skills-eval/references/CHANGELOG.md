# Changelog
### v3.19.1 (2026-09-07)
- **用例标题自检（build-testcases-html.py）**：`self_check` 新增第 7 项——标题为空或匹配「用例N」格式时拒绝生成（标题必须为出题时写的真实描述，如「电商营销策略-完整方案」）。`--check-only` 同样生效，root-skills-check 通过 `--check-only` 间接继承。
- **通过率含安全/组合标签（build-testcases-html.py）**：「通过率」表追加安全标签/组合标签两行通过率——按用例判定（任一轮 FP 即 FP，与标签表判定一致），调用不进标签统计；标题改为「通过率（按类型 + 安全/组合标签）」，表下附口径注释。
- **调用用例去重**：A 卷「全部用例与每轮 AI 原文回复」**不再包含调用用例**（`CALL_TYPE` 行跳过），调用只出现在「调用用例逐条执行情况」区块，避免重复。
- **缺失 --cases/--process 升级为阻断**：`build-final-report.py` 不再允许缺失占位交付，缺少 `--cases` 或 `--process` 时 exit 2 拒绝生成，`--validate-only` 不受影响。
- **Excel 回填规范**：`batch-evaluation.md` 新增「Excel / 清单回填规范」——报告列必须写入可点击 HYPERLINK 公式（局域网 HTTP URL），禁止只填绝对路径。
- spec 同步：`trigger-eval-cases.md` L266/L271 更新调用去重规则，`build-testcases-html.py` docstring 同步。

### v3.19.0 (2026-09-04)
- **交付目标可配置（不写死路径）**：完成副本与最终报告不再写死 `~/Desktop`。新增 `.batch.yaml` 批配置（`source_dir`/`done_dir`/`report_dir`/`keep_fix_suffix`/`dedupe`）与解析优先级：显式参数/用户指明 > 批配置（`./.batch.yaml` 或 `--batch-config`）> 相对默认（同级 `已执行/`、`评测报告/`）> 兜底 `~/Desktop`。契约见新增 `references/batch-delivery.md`。
- **`build-final-report.py`**：新增 `--batch-config` / `--keep-fix-suffix`；`desktop_fix_check` 增加 `fix_suffix` 参数（`keep_fix_suffix: false` 时校验 `done_dir/{name}` 而非 `{name}-fix`）；`report_dir` 可作 `--output` 缺省目录。
- **命名与去重**：完成副本是否保留 `-fix` 由 `keep_fix_suffix` 决定；目标已有同名默认 `dedupe=newest`（对比文件/版本保留最新，不静默覆盖）。
- 同步 SKILL.md / README / opt / registry 版本至 3.19.0（opt 3.6.0）；新增 5 条回归测试；修复 `tests/test_build_final_report.py` 尾部被二进制垃圾截断导致无法收集的问题（截断乱码、保留全部有效用例）。

### v3.18.1 (2026-09-04)
- **批量并行可靠性（硬性）**：批量 subagent 必须带"无进展超时判定"——默认连续 15 分钟无写入/无产出判疑似中断（complex 放宽到 25 分钟）；先核对磁盘落盘完成度，完成则收尾、未完成则续接或重启，禁止无限等待"完成通知"；进度以磁盘落盘为准。规则见 SKILL.md「批量评估模式」+ `references/batch-evaluation.md`（新增「并行执行与子代理可靠性」章节）。
### v3.18.0 (2026-09-03)
- **🧪 最终版口径固化（优化点 1）**：最终报告「🧪 测试用例」区的通过率 / 逐条用例 / 每轮 AI 原文一律取**最终版**（多版本时 --cases 只内联最终版本重测生成的 test-cases.html，禁止源版/旧版；脚本 A 卷四格对账 + 调用/标签/B 卷区硬校验）。📊 测试报告与 🧭 评测过程保留不变、不贴逐条。
- **公式分散到各轨道数据下方（优化点 2）**：`build-final-report.py` 一·补中轨道 A/B/C 计算公式不再集中放区块开头，改为**分别放在对应轨道数据/分项表下方**（A 公式在 A 六维数据下、B 公式在 B 盲测汇总下、C 公式在 C 分项下）；区块开头保留隐藏 `id=scoring-formulas` 锚点兼容。`self_check_html` 硬校验：锚点 + 三个「📐 轨道 X 计算公式」标题齐全，缺一拒绝生成。
- 同步 SKILL.md / trigger-eval-cases.md / README / manifest / registry 版本至 3.18.0；修复 `scoring_formulas_html()` 兼容函数丢锚点导致 3 个自检回归测试失败的问题。

### v3.17.5 (2026-09-03)
- **分级复测（减少批量复测）**：低分修复流程按修复类型决定复测范围——静态合规修复（frontmatter/章节/编码/目录，不影响触发）走「静态复核模式」，只重算静态六维 + 调用门槛，不重跑 A 卷 3 轮；行为修复（description/触发词/流程/脚本/正文语义）才全量重跑 A 卷 3 轮。报告「修复问题清单」逐条标注「静态复测」。规则见 `low-score-repair-flow.md`。
- **批量预检钩子**：批量评测前由 `root-skills-doctor --batch-preflight` 读 `root-skills-check --export-top-defects` 把已沉淀缺陷纳入预检，静态缺项批量补到副本后再评测（不写回源）。

### v3.17.4 (2026-09-03)
- **发布线统一为 85（第 4 项）**：`market_ready` 从「封顶后 ≥80」提到 **≥85**，与「要不要修 <85 / 修复退出 ≥85」合成一条放行线，消除 80–84.9「可发布 ✅ 却强制修复」死区；研究报告 6.1 的「市场合并 ≥80（B 级）」保留为等级参考（B 级起点），不再作 `market_ready` 数值线。涉及 `MARKET_READY_MIN=85`、`apply_market_ready`、comprehensive-scoring / SKILL / README / release-checklist / 报告公式区文案。新增回归测试 `test_apply_market_ready_line_is_85_not_80`。
- **A 总分定位 + 清理旧状态模型（第 5 项）**：scoring-criteria.md 停用旧单轨 `status`（excellent/good/needs_optimization/needs_refactor）与「发布建议」表，明确「轨道 A 总分只作内容质量参考、不构成任何门槛；A 的 error 经 issues → 轨道 C 封顶 ≤79 间接生效」；快速检查表分母与说明同步。A 前置成本闸门暂缓（与「源只读 / 先源基线再修复」语义冲突，另行决策）。
- **轨道 A 计分口径统一 ÷105（第 1 项）**：scoring-criteria.md 三个示例改为与 `_track_a_total_from_dims` 一致的 ÷105 归一（96.0 / 86.7 / 72.4），删除旧「÷100 后 cap 100」示例与 status 行；新增回归测试 `test_track_a_doc_examples_match_code_division_by_105`，防止文档/代码再次漂移。
- **安全高危封顶机器化（第 2 项）**：新增 `apply_safety_highrisk_cap`——`track_b.security_tag.high_risk > 0` 自动把轨道 C 封顶 ≤79 并 `market_ready=false`（comprehensive-scoring 特殊规则 4 的机器兜底，不再依赖回填员手动压分/补 error）；`apply_score_caps` 与 `apply_market_ready` 的 forced_off 纳入该标记。新增 3 条回归测试。
- **「轨道 A 仍有 error」口径补齐（第 3 项）**：SKILL.md（frontmatter/一键流程/低分自动修复/三道门槛/低分自动接管/低分修复触发）、low-score-repair-flow.md、trigger-eval-cases.md（流程总览/Step 5 自检/Step 6 触发）统一补「或轨道 A 仍有 error」，并注明「已由封顶 ≤79 隐含，单列仅为口径一致/防御」。

### v3.17.3 (2026-09-03)
- **最终版版本一致性（硬性）**：最终报告最后一版 `eval_info.version` 必须等于交付 fix 目录 `SKILL.md version`；生成最终报告后再改 fix（升版本/改 description/修 B 卷）必须用新版本 YAML 重生成并替换最终报告；Excel/清单回填的 修复版本/首次C/修复后C/上线 必须与最终版 YAML/最终报告对账；fix 版本 > 报告版本、或回填分无最终报告支撑（预估当实测）时禁止放行/标记上线。trigger-eval-cases.md Step 5 新增「□ 版本一致性/最终版对齐」自检项。

### v3.17.2 (2026-09-02)
- **收口 P0 工作流**：
  - `build-final-report.py --validate-only` / `build-testcases-html.py --check-only`：check 只跑闸门，不写 HTML、不跑桌面复制。
  - 出报告顺序：评分 →（如需）修复与 B 卷 → check 闸门 → HTML。check 只执行 Step 5.4/5.5，不重跑出题/三轮。
  - `--require-desktop-fix` 仅低分修复（多版本）强制；一次达标不加，不要求 skill 已在桌面。

### v3.17.1 (2026-09-02)
- **🧪 测试用例必须输出最终版 A 卷、B 卷、调用、标签用例（安全/组合）**：
  - `build-testcases-html.py` 增加 `--b-results`；始终渲染「调用用例逐条执行情况」与「B 卷 · 全部用例」（未开卷写「B 卷未执行」）；标签表可含最终版 B 卷带签条目。
  - `build-final-report.py` 多版本硬校验覆盖 A 卷四格对账 + 调用条数 + 标签表 + B 卷区。
  - **📊 测试报告 / 🧭 评测过程章节不贴逐条、结构不变**（B 卷门禁 F1 仍只在 📊/🧭 记汇总）。

### v3.16.9 (2026-09-01)
- **输出前闸门：先检查、漏了补、非原文改回原文，再出报告**：
  - 新增 Step 5.4：生成测试用例 HTML / 最终报告前必须先查漏数据并补齐，再逐条核对**全部用例**每轮 AI 回复；空/模板/要点摘要/截断一律从会话归档改回原文（找不到则重跑该条），都检查过了才输出。
  - Step 5.5 完整性校验改为「有漏必须先补齐再输出」；原文回复校验由「抽查 ≥5 条」改为「全部用例」。
  - `build-testcases-html.py`：截断/省略标记与「要点如下/摘要如下」从 warning 升为 error，拒绝生成。
  - 低分修复流程同步：`low-score-repair-flow.md` 交付改为单一 HTML；生成最终报告前必须先走 Step 5.4 → 5.5。

### v3.16.8 (2026-09-01)
- **最终报告一·补写明轨道 A/B/C 计算公式**：A 为 `Σ(分项×权重)÷105`；B 为每轮 TP/FP/FN/TN → P/R/F1，三轮平均；C 为六维点数直接相加（Trigger 按 F1 落档，不是 F1×25）。A/B/C 是轨道不是第 1/2/3 轮。`build-final-report.py` 渲染 `id=scoring-formulas`，自检缺公式拒绝生成。
- **历史遗留 ≠ FIXED**：message/status 含「历史遗留」时修复清单标「历史遗留 —」，不得因最终 YAML 未再列出而写成已修复。中文 name / 目录名 / H1 禁止改回英文；manifest 机器 ID 可保留。

### v3.16.7 (2026-09-01)
- **Release 清单按本轮 A/B 卷取证（评测已有 Skill）**：第 3 项只判 Iron Law RED；第 9 项只看本轮 `track_b` 四类是否已执行（有则必须 pass）。禁止把「没 RED 文件」写成「没评测」，禁止因 `tests/` 未在正文声明而 fail 第 9 项。业务 Skill 第 10 项看 gotcha + version/last_updated + 停用条件，不套 manage 家族注册表。
- `build-final-report.py`：每项必须有 evidence；第 9 项在四类已执行时 fail 则拒绝生成；第 3 项 evidence 宣称「无评测/无用例」且本轮已跑 A 卷则拒绝生成。

### v3.16.6 (2026-09-01)
- **报告不得空发（爆款视频分析器 / 营销内容套件最终报告审计）**：
  - 轨道 B：YAML 写 `per_round` 或小写 `tp/fp/fn/tn` 时回填 `track_b.rounds` 为大写四格；平均行须填 TP/FP/FN/TN（或 —），禁止 `colspan` 把四格留空。`validate_report_data` / `self_check_html` 拦截。
  - 轨道 C：`trigger_accuracy` 等别名映射到默认评分依据；读取 `track_c.breakdown`。评分依据空单元格拒绝生成。
  - 「全部用例与每轮 AI 原文回复」必须是会话原文：拦截「触发…，按…输出」模板、≥3 条用例共用同一长回复、长回复去重率过低。
  - 标签表改为「安全 / 组合」且每轮展示 AI 原文回复；调用只出现在全部用例表，禁止重复。

### v3.16.5 (2026-09-01)
- **调用门槛挡上线**：调用仍不进 F1 / 不占四类条数 / 不进 B 卷。A 卷至少 3 条覆盖打本名 / 打成别的 / 没材料，3 轮加载判定全过才算 `call_tag.passed_gate`。未过 → `market_ready=false`、进入修复、禁止交付副本。YAML 缺 `call_tag` 拒绝生成最终报告。opt 旧 YAML 无 call_tag 不挡，新报告 `passed_gate=false` 不能退出修复。

### v3.16.4 (2026-09-01)
- **中英混写改为正例必出配额（占原全英文份额）**：业务以中文提问为主，禁止把正例劈成全中文 / 全英文各一半。出题提示词新增【中英混写】；混写从「若对半会分给全英文」的那一半里出，不占纯中文。A 卷正例：简单 纯中文 4 + 混写 3 + 全英文 1（无英文触发词则 5+3+0）；标准 8+6+2（无则 10+6+0）；复杂 16+12+4（无则 20+12+0）。B 卷正例：有英文触发词 1+1+1，无则 2+1+0。中英混写计为中文题，英文题只计全英文。出题自检 16→17 项（第 17 项紧挨第 16 项）。
- 判定：主体中文且夹 ≥2 个业务英文词（listing / brand voice / tone / ICP 等）；整段英文、只夹一个词、仅品牌名不算。纯英文 Skill 记 na。

### v3.16.3 (2026-09-01)
- **调用跟进生成器（报告审计：品牌声音提取器 29.6%/0.0%）**：规则在 v3.16.2 已写「调用不占条数、不进四格」，`build-testcases-html.py` 未跟上。现分配比例分母只计四类主类型，调用单独列、占比 —；通过率按加载/未加载计，未回填显示「未回填」而不是 0/0 红标。
- **调用结论主语=本 Skill**：斜杠打成别的中文名、回复加载了其他 Skill 时记「未加载」。自检对调用结论 ∈ {加载, 未加载} 做 warning。
- **flaky 改为脚本计算**：`score-trigger-eval.py --json` 按四类主类型 3 轮结论不一致自行列出，不再抄输入里的空 `flaky: []`。

### v3.16.2 (2026-09-01)
- **调用场景 + 中英文触发（出题规则）**：
  - 新增用例类型「调用」：name 只有中文时斜杠只写 `/{中文 name}`，不要英文名；覆盖打对本名 / 打成别的中文名 / 打了没材料。不占 A 卷条数、不进四格、不规定条数。
  - description 同时写了中文、英文触发词时，正例必须两边都有（中文原话 / 英文原话，均不出现 skill 名），漏一边视为出题不合规。
  - 出题自检 14→16 项；`score-trigger-eval.py` 对类型「调用」跳过 TP/FP/FN/TN。
- **description 压回 ≤1024**：交付/排版细节下沉正文；触发词、调用场景、中英正例、不适用、安全边界保留。版本同步 registry / README / manifest。

### v3.16.1 (2026-09-01)
- **正文去沉积（规则不删）**：版本史只留 `CHANGELOG.md` 指针；交付物/依赖去掉重复叙述与版本口吻。A/B 卷维度与配比、六维权重、P/R/F1、三道门槛、盲测、Release 10 项、桌面校验、中文最终包均保留在正文。

### v3.16.0 (2026-09-01)
- **三道门槛收口（全家唯一口径）**：
  - 进入修复：封顶后轨道 C **< 85**（**不要用 ≤85**：85 既进又出会空转）
  - 退出修复 / 交付副本：封顶后轨道 C **≥ 85**（Output < 15 会封到 79，自然达不到）且 B 卷 F1 ≥ 0.85
  - 可发布：`track_c.market_ready`（封顶后 ≥80、Output ≥15、无 error 封顶）；生产就绪 ≥90
  - F1 < 0.85 文案改为「未过 B·F1门槛」，不再写成「暂不可发布」
- **对比表做成审计底稿**：列含 Output、可发布、轨道 C（可带「封顶前 x」）；六维不齐不合成总分；总分须与分项对账（封顶后用封顶前总分对账）；`cases_total` 不再默认 50
- **封顶语义**：Output/error 把总分**最高**压到 79，不抬分；等级跟封顶后总分走（88→79 为 C；50 仍是 F，不得写成 C）
- **opt 配套**：`plan-fixes.py` 读封顶后轨道 C + Output ≥15，YAML 88 + Output 12 视为有效 79、未达 85

### v3.15.0 (2026-09-01)
- **报告输出（生成器 + 规范文案）**：
  - 一·补顺序固定为 **轨道 A → 轨道 B（第 1/2/3 轮）→ 轨道 C**；禁止把 3 轮称作「a/b/c 轮」
  - 最终版本必须有 `track_a.total` 与 `track_c.total`；缺失不得视为 0，也不得据此判定暂不可发布；分项在、总分缺时按权重补算
  - 对比表拆分 **B·F1门槛** 与 **轨道C / 可发布**；总结论「可发布」只看 `track_c.market_ready`
  - 评测过程必须含「输出前自检（15 项）」与「盲测：被测会话仅收到提示词列」；页脚固定写「全部通过（15 项）」，禁止「0 项检查全部通过」
  - NA ≠ FIXED；标签表只保留结论不重复 AI 全文；空标签不得渲染字面 `None`；轨道 A 权重按 105 归一
- **评分特殊规则（`comprehensive-scoring.md`）**：
  - Output Quality < 15/25 → 轨道 C 最高 79（C 级），`market_ready=false`（`apply_output_cap` 强制）
  - 抽取类 Skill 的 Output 最低断言：无样本不得写全文案；主张须对应题面；错误处理分支须出现；正例题面自包含（出题第 6 项）机器可检
- 低分修复进入/退出口径在 v3.16.0 收口为「< 85 进 / ≥ 85 出」；本版尚未改生成器对比表审计与封顶语义

### v3.13.3 (2026-09-01)
- **中文最终包规则（eval / doctor / opt 同步）**：`name` 与目录一致且为 Unicode 字母（含中文）即通过；ASCII 仍 kebab-case；中文 name 的 kebab-case 记 **na**（不扣分、不进修复）。低分修复禁止把中文 name / 目录名 / H1 改回英文。单包 `skills._shared` 缺失记 warning，不阻断、不为修它改 name。

### v3.13.2 (2026-09-01)
- **盲测执行（预期结果不得进入被测会话）**：Step 3 拆成回填员 / 被测会话——回填员可读完整 Excel；发给被测会话的只有「提示词」列原文。类型、标题、预期结果、标签、优先级以及「这是评测」说明均不得进入被测会话。预期结果只用于回填之后的 Step 4 评分。B 卷门禁与低分修复同步；输出前自检 14→15 项（新增盲测校验）；顺手修正原执行指令「2轮执行几轮」笔误。

### v3.13.1 (2026-09-01)
- **出题提示词改为写法门禁、不设有资料/无资料条数下限**：正例必须自包含（同一条发给 dsh 与 Codex 都能执行）；有资料则把短样本写进题面、禁止「见附件/打开工作区文件」；无资料则声明「我没有资料提供，请自行搜索资料并作答」。两类按被测 Skill 真实用法选用，自检第 6 项按写法检查、不按条数配比。

### v3.13.0 (2026-09-03)
- **交付物收敛为单一 HTML + 顶部目录（用户要求：最终输出一个 html 文档，测试报告-评测过程-测试用例）**：最终报告改为**唯一交付物**——顶部**目录**导航三大部分：「📊 测试报告（原数据统计总览）」「🧭 评测过程（评测 Skill 流程）」「🧪 测试用例（逐条用例执行情况）」，全部内容在**同一个文档**内（页内锚点跳转，任意网络/双击 file:// 可开）。测试报告 = 原数据统计总览（总结论 + 多次数据对比 + 三轮执行与评分统计总览 + 分配比例与安全/组合标签用例汇总 + 修复清单 + Release 清单 + 过程摘要）；评测过程 = 评测 Skill 流程（出题自检 / 3 轮执行 / 静态验证 / 低分修复 / B 卷门禁 / 输出前自检）；测试用例 = 逐条用例执行情况（分配比例 / 通过率 / 标签用例逐条执行情况 / 全部用例与每轮 AI 原文回复）
- **移除 v3.12.0 的「三文件 + 底部跳转链接」与 v3.10.0 的 iframe 内嵌**：`--cases/--process` 传测试用例/评测过程 HTML **文件路径**时，`build-final-report.py` 提取其 `<body>` 内容与 `<style>`（选择器加作用域前缀 `.inline-cases`/`.inline-process`，不污染主报告样式），分别内联进「🧪 测试用例」「🧭 评测过程」部分；子页面自身 h1/副标题/页脚剔除、h2 降级为 h3（part-head 为唯一二级标题）；http(s) URL 无法内联 → warning + 外链占位；文件缺失 → warning + 占位注明。测试用例/评测过程 HTML 改为**中间产物/存档**，不再独立交付
- **build-final-report.py 同步**：`deliverable_links()` 移除，新增 `inline_html()`（提取 body/style + 剔除子页 h1/sub/footer + h2 降级）、`_scope_css()`（作用域隔离）、`toc_html()`（顶部目录）；`self_check_html()` 改为校验三大部分锚点（#part-report/#part-process/#part-cases）与目录链接齐全 + 测试用例部分含「全部用例与每轮 AI 原文回复」（--cases 内联时）+ 评测过程部分含「输出前自检」（--process 内联时）；**移除 v3.12.0「最终报告不得出现「标签用例逐条执行情况」」检查**（v3.13.0 起该区块并入最终报告「🧪 测试用例」部分，属预期内容）；粘连检查收紧为「类型标签紧跟 ≥3 位数字或百分比」（避免内联过程内容里「正例16/负例16/…」合法计数误报）；docstring / process_txt / 页脚文案同步
- **build-testcases-html.py 同步**：docstring 与页脚注明 v3.13.0 起为中间产物，内容并入唯一最终报告「🧪 测试用例」部分（不再作为独立交付物）
- **流程同步**：SKILL.md（frontmatter 描述 / 一键全自主交付物描述 / 最终交付物小节重写 / 依赖描述 / 版本历史）、`trigger-eval-cases.md`（Step 5 交付物重写 + Step 5.5 自检项与双保险措辞）、README、manifest（version 3.12.0→3.13.0、description、scripts/workflow 描述）、opt 配套 Eval 版本 3.13.0、manage registry skills.json
- 验证：pytest 62 passed（新增 inline_html / _scope_css / toc_html / 自检目录与三大部分 / 内联原文回复与输出前自检强制等测试）、check-family PASS、manage check 5/5；演示交付物 `eval-v310-demo/bm-brand-voice-extractor-final-report-v3.13.0-demo.html`（浏览器验证：顶部目录三链接页内跳转、测试报告/评测过程/测试用例三部分顺序渲染、标签用例逐条执行情况 13 行、每轮 AI 原文回复全量无截断、无 iframe/无底部跳转链接）

### v3.12.0 (2026-09-03)
- **安全/组合标签用例统计并入「二、测试用例分配比例」（用户反馈：二·补区块拆分）**：最终报告「二·补、安全与组合标签用例统计与执行情况」**移除**——①统计汇总（安全/组合标签用例条数、3 轮判定次数、FP、高危数、执行结论）并入「二、测试用例分配比例」区块内（子标题「安全与组合标签用例汇总（叠加标签，不占主类型总数）」，**格式不变**）；②**逐条执行情况**移至测试用例 HTML「标签用例逐条执行情况」区块（v3.12.0 新增，build-testcases-html.py 渲染：标签 / # / 标题 / 类型 / 1-3 轮结论 / 判定，判定规则与 score-trigger-eval 的 _tag_stats 一致——任一轮归类为 FP 即判 FP，否则通过）
- **六/七 不再内嵌 iframe（用户反馈：只保留跳转链接）**：最终报告取消「六、测试用例（内嵌）/ 七、评测过程（内嵌）」的 iframe srcdoc 内嵌与页内锚点；底部「交付物导航」改为**跳转链接**（📄 测试用例（含逐条执行情况）/ 🧭 评测过程，指向独立 HTML 文件，`--cases/--process` 传文件路径或 http(s) URL 均生成对应链接；文件缺失时 warning + 底部注明未提供）；测试用例与评测过程为独立交付物随最终报告一并交付（v3.10.0 的「单一自包含内嵌」设计按用户反馈回退为「链接交付」）
- **build-final-report.py 同步**：移除 embed_html 内嵌逻辑（新增 `deliverable_links()` 生成跳转链接）；self_check_html 必需区块改为「一/一·补/二/三/四/五」+「二」内必须含「安全与组合标签用例汇总」+ 最终报告不得出现「标签用例逐条执行情况」区块；docstring / process_txt / 底部导航 / 页脚文案同步
- **build-testcases-html.py 同步**：新增 `tag_cases_table()` 渲染「标签用例逐条执行情况」（含安全/组合条数统计与 FP/通过判定）；页脚改为「本文件为独立交付物…由最终报告底部跳转链接打开」
- **流程同步**：SKILL.md（frontmatter 描述 / 最终交付物小节 / 依赖 build-testcases-html.py 描述 / 版本历史）、`trigger-eval-cases.md`（Step 5 交付物 4 条重写 + Step 5.5 标签统计校验/原文回复校验/双保险措辞）、README、manifest（version 3.11.0→3.12.0、description、scripts 描述）、opt 配套 Eval 版本 3.12.0、manage registry skills.json
- 验证：pytest 55 passed（新增 deliverable_links / tag_cases_table / 自检拒绝逐条区块等测试）、check-family PASS、validate 无 error、manage check 5/5

### v3.11.0 (2026-09-03)
- **移除「安全写回」，改为「副本交付（不写回被测 skill 原文）」（用户规则）**：低分修复流程全程只在 `{skill}-fix/` 副本上修复，源文件（含桌面源）**任何情况下不写回、保持原样**；副本达标（≥85）+ B 卷门禁（F1 ≥ 0.85 且无高危安全 FP）通过后，将修复副本复制到**桌面（~/Desktop）与源并排**交付，不执行原「自动备份源文件 → 写回 → 验证 → 回滚」步骤
- **B 卷门禁定位调整**：由「写回前最终门禁」改为「副本交付前最终门禁」——通过才允许交付副本，未通过禁止交付（源文件保持原样，副本与 B 卷结果留档）
- **桌面交付校验语义同步**（`--require-desktop-fix`）：`~/Desktop/{name}` 源为**只读参照**（仅校验存在、不改动），`~/Desktop/{name}-fix` 修复副本必须就位（缺失且工作区存在时自动复制到桌面），否则拒绝生成最终报告（exit 2）
- **流程同步**：SKILL.md（低分修复流程/B 卷门禁/桌面交付校验/版本历史）、`low-score-repair-flow.md`（规则 4/5 重写）、`trigger-eval-cases.md`（Step 1/6/5.5 措辞）、README、manifest（version 3.10.1→3.11.0、writeback 字段更新）

### v3.10.1 (2026-09-03)
- **测试用例 HTML 强制 AI 原文回复（问题：交付物只含提炼总结，缺原文）**：交付物「AI 回复」列必须为 AI 实际返回的**原文逐字**（含 markdown/换行/列表/表格），禁止提炼、概括、改写、截断、省略号——源头规则写入 trigger-eval-cases.md Step 3 执行指令（回填「ai实际返回结果」改为「逐字原样粘贴，禁止提炼总结」）与 Step 5 交付物要求
- **新增规范生成器 `scripts/build-testcases-html.py`**：从评测结果 JSON（与 score-trigger-eval.py 同源）生成测试用例 HTML——用例表 + 分配比例（含安全/组合叠加标签）+ 通过率 + **每轮 AI 原文回复（white-space:pre-wrap 全量渲染，不截断）**；内置**原文回复自检**（3 轮回复非空、轮次齐全、无截断/提炼标记、打印回复字数统计），失败 exit 2 不交付（`--allow-empty-replies` 仅历史补档逃生）
- **输出前自检 13→14 项**：Step 5.5 新增「原文回复校验」（抽查 ≥5 条与真实会话原文逐字一致；由 build-testcases-html.py 生成且自检通过）；SKILL.md 一键流程/交付物/依赖同步；manifest scripts 5→6、tests 4→5
- 历史评测数据补档：旧测试用例 HTML 若为摘要版，需用真实会话原文重建（round JSON 摘要无法还原原文时，从执行记录/会话归档逐字回补）

### v3.10.0 (2026-09-03)
- **交付物收敛为单一自包含 HTML（问题 1：链接打不开）**：`build-final-report.py` 的 `--cases/--process` 传文件路径时，把测试用例与评测过程**内嵌**进最终报告（iframe srcdoc），底部「测试用例 / 评测过程」变为**页内锚点链接**——一个 HTML、任意网络/双击（file://）可开，不再依赖局域网服务与兄弟文件；传 http(s) URL 时保持外链
- **交付前桌面校验（问题 2：修复副本未放桌面）**：新增 `--require-desktop-fix` 门禁——生成最终报告前必须确认 `~/Desktop/{name}`（源）与 `~/Desktop/{name}-fix`（修复副本）已就位（低分修复时）；修复副本缺失但工作区存在 `{name}-fix/` 时自动复制到桌面（`--desktop-fix-source` 可指定源），否则**拒绝生成**（exit 2）——先放桌面，才输出最终交付物
- **Release 清单新增「是否影响上线」（问题 5）**：`release_checklist` fail 项必须标注 `impact`（影响上线 / 不影响上线 + 原因，缺失即拒绝生成）；报告新增「是否影响上线」列 + 「✅ 通过 X 项 / ❌ 未通过 Y 项 / — 不适用 Z 项」汇总徽章；🔴 影响上线 = 发布阻断项（剩余风险显著提示），🟡 不影响上线 = 剩余风险
- **输出前脚本自检（问题 4：格式混乱「正例1632.0%」）**：新增 `self_check_html()`——生成 HTML 后、写盘前核对：必需区块齐全 / 分配比例百分比健全（单项 ∈ (0,100.5]，杜绝 1632.0% 类比例异常）/ 单元格无 NaN/None / 表格单元格无类型标签与数字粘连（如「正例16」）/ Release 区块含判分与「是否影响上线」列 / 链接可解析（锚点 id 存在、无 javascript:/data:）；自检结论写入页脚「输出前自检：全部通过」，失败 exit 2 不交付
- **单元格分隔符（问题 4）**：分配比例 / 标签汇总 / 对比表单元格内容自带尾随空格（`正例 ` / `16 条 ` / `32.0% `），文本化、复制、纯文本预览不再出现「正例1632.0%」式粘连
- **validate_report_data 扩展**：distribution 单项百分比 ∈ (0,100.5] 硬校验；`validate_report_warnings()` 新增 tag_cases 逐条数与 security_tag/combo_tag 声明条数一致性软校验（汇总表与逐条表打架时提示）
- **流程同步**：SKILL.md 最终交付物/低分修复流程/轨道 A Step 4 同步（内嵌交付 + 桌面校验 + impact 强制）；trigger-eval-cases.md Step 5 交付方式重写、Step 5.5 输出前自检 10→13 项（新增桌面交付校验 / HTML 输出自检 / Release 影响上线判定）；release-checklist.md 增加 impact 字段定义与发布门禁语义
- 历史评测数据重建最终报告：旧 YAML 缺 impact/tag_cases 时需 `--allow-missing-release` 逃生，或人工补 impact 后正常生成

### v3.9.1 (2026-08-31)
- 修复 `build-html-report.py` 的 Python 3.9–3.11 f-string 兼容性
- 拒绝 `javascript:` / `data:` 主动内容链接并正确闭合 Markdown 列表
- 新增单版本 HTML 与 v3.9 最终报告数据校验回归测试

### v3.9.0 (2026-09-03)
- **交付物必须包含安全/组合标签用例统计与执行情况**：最终报告新增「安全与组合标签用例统计与执行情况」区块——①汇总表：安全/组合标签用例数量（条数）、3 轮判定次数、FP 次数、高危数、执行结论（✅ 全部通过 / ⚠️ 误触发 / ❌ 高危）；②逐条执行表：每条标签用例的 3 轮结论与判定（数据来自 `track_b.tag_cases`）
- **输出数据格式硬校验扩展**：`build-final-report.py` 的 `validate_report_data()` 新增第 4 类校验——最终版本 YAML 的 `track_b.security_tag` / `track_b.combo_tag` 必须含用例数量（cases），`tag_cases` 必须为合法列表；缺失即**拒绝生成最终报告**（exit 2，`--allow-missing-release` 逃生阀仅限历史数据重建）
- **评分脚本支持标签统计输出**：`score-trigger-eval.py` 新增组合标签维度汇总（条数 + FP）与 `--json` 模式——输出 `security_tag` / `combo_tag` / `tag_cases`（逐条执行情况）机器可读 summary，直接抄入评测 YAML 的 track_b
- **流程同步**：`trigger-eval-cases.md` Step 4 新增组合标签判定与「记录标签统计（v3.9.0 强制）」、Step 5 交付物新增标签统计区块要求、Step 5.5 输出前自检 9→10 项（新增「标签统计校验」）；SKILL.md 轨道 B Step B3 与一键流程同步
- 历史评测数据（v3.8.1 及更早 YAML 缺 security_tag/combo_tag）重建最终报告时需用 `--allow-missing-release`

### v3.8.1 (2026-09-02)
- **输出报告数据格式硬校验**：`build-final-report.py` 新增 `validate_report_data()`——对**最终版本** YAML 校验 ① `track_b.distribution` 条数合计 == `cases_total`、百分比合计 ≈ 100%；② `release_checklist` 10 项齐全（id 1-10，status ∈ pass/fail/na）。校验失败**拒绝生成最终报告**（exit 2），杜绝「区块在、判分全空」「百分比对不上」的报告；历史数据重建可用 `--allow-missing-release` 逃生阀（warning + 继续）
- **flaky 计数修正**：新增 `_flaky_count()` 剔除空占位条目（id: 0 / title: none / conclusions: []），修复 0 flaky 却显示 1 的虚报
- **输出前自检 7 → 9 项**：`trigger-eval-cases.md` Step 5.5 新增「报告数据格式校验」与「Release 清单校验」两项，并明确自检结论必须写入评测过程 HTML；Agent 自检与脚本硬校验双保险
- `release-checklist.md` 由「缺失时降级为未判分」改为「缺失即拒绝生成」；SKILL.md 轨道 A Step 4 标注强制校验；manifest `schema.output` 将 `release_checklist` 从 `optional_keys` 提升为最终版本必填（历史版本可缺）

### v3.8.0 (2026-09-02)
- **Release 发布前 10 项审查清单**：最终报告新增「Release 发布前 10 项审查清单」区块——逐项判分（✅ 通过 / ❌ 未通过 / — 不适用）+ 通过标准 + 对应参考，从最终版本 YAML 的 `release_checklist` 字段渲染；判分规则与字段定义见新增 `references/release-checklist.md`（creator `pre-launch-checklist.md` 同源副本）
- 轨道 A 静态评估新增 Step 4「Release 10 项审查清单判分」；`build-final-report.py` 新增 `release_checklist_html` 渲染区块；manifest `schema.output` 新增 `optional_keys: release_checklist`

### v3.7.1 (2026-09-02)
- **输出前自检（7 项）**：生成最终报告前强制执行——格式 / 完整性 / 一致性 / 逻辑 / 边界 / 安全 / 引用七项校验，未全部通过禁止输出；自检结论（全部通过 / 存在异常）写入评测过程
- `trigger-eval-cases.md` Step 5 之后新增「输出前自检 7 项」章节；`SKILL.md` 一键流程自检改为「出题 14 项 + 输出前 7 项」

### v3.7.0 (2026-09-02)
- **A 卷按复杂度出题**：出题规模由被测 Skill 的 `complexity` 决定——简单 25 条（8/8/6/3）、标准 50 条（16/16/12/6）、复杂 100 条（32/32/24/12），主类型统一为四类（正例/负例/近似命中/边界情况，比例 32%/32%/24%/12%）
- **安全与 Skill 组合改为叠加标签**：不再作为独立主类型计数，而是标注在主类型用例上（不额外增加总数）。安全标签覆盖 4 类攻击面（提示注入/敏感信息泄露/危险操作/路径权限越界），下限 简单≥4 / 标准≥6 / 复杂≥12；组合标签覆盖 4 类场景（当前主导/他 Skill 主导/顺序协作/职责冲突），下限 简单≥4 / 标准≥8 / 复杂≥16
- **B 卷固定 10 条**：正例 3 / 负例 3 / 近似命中 3 / 边界 1（30%/30%/30%/10%，最接近 32/32/24/12 的整数分配），安全标签≥2 + 组合标签≥2（可重叠），题面与 A 卷独立、修复全程封存
- 用例表新增「标签」列；评分脚本 `score-trigger-eval.py` 支持叠加标签判定；自检清单 14 项更新为复杂度配比 + 标签覆盖

### v3.6.0 (2026-09-02)
- **双卷制（借鉴 microsoft/SkillOpt held-out gate）**：出题阶段生成 A 卷 50 条（正例16/负例14/近似10/边界4/安全6）+ **B 卷 10 条独立留出题**（正例3/负例3/近似2/边界1/安全1，比例参照 A 卷），B 卷存 `{name}-b-cases.xlsx` 并**封印**（修复/opt 全流程不可见，防过拟合）
- **写回前 B 卷最终门禁**：副本达标（≥85）后开卷执行 B 卷 10 条 × 3 轮，**B 卷 3 轮平均 F1 ≥ 0.85 且无高危安全 FP 才允许写回**；未通过禁止写回（源文件保持原样，按停滞规则结束，报告注明原因摘要，不贴 B 卷题面）；A 卷一次达标（未进入修复）不执行 B 卷
- 自检清单 12→14 项（B 卷配比、B 卷独立性）；最终报告新增 A/B 卷成绩区块；B 卷文件为封印存档，不交付、不进 opt 读取路径
- `trigger-eval-cases.md` 出题提示词新增 B 卷出题与封印规则（Step 1/6）；`low-score-repair-flow.md` 写回流程插入 B 卷门禁

### v3.5.0 (2026-09-01)
- **全程自主**：用例生成后自动自检并直接执行三轮评测；低分自动修复；达标后自动备份、写回与回归验证，不设置用户确认节点
- **安全写回**：写回前保存带时间戳的恢复副本与 diff；结构验证或回归评测失败时自动回滚，并把证据写入评测过程

### v3.4.0 (2026-09-01)
- **最终交付物标准**：交付物统一为 HTML 链接；测试报告只保留**一份最终报告** `{skill-name}-final-report.html`——新增 `scripts/build-final-report.py` 合并多版本 YAML（源 → 第一次修复 → 第二次修复 的三次数据对比表 + 修复问题清单 + 用例分配比例 + 底部链接），不再交付多份分版报告
- 测试用例（`{skill-name}-test-cases.html`）与评测过程（`{skill-name}-evaluation-process.html`）为独立 HTML 交付物；YAML/MD/Excel 降为中间产物（供 opt/存档，不单独交付）
- description 与低分修复流程补充「只保留一份最终报告、三次数据对比」规则；每次重测 YAML 必须保留供合并

### v3.3.2 (2026-09-01)
- **低分自动修复（硬性规则，写回源文件）**：总分 ≤85 时**自动**进入「低分修复流程」，禁止询问用户"是否启动修复"；流程内唯一人工节点为达标后写回源文件前的 diff 确认；新增「禁止询问的措辞」与停滞检测（连续 3 轮不提升即停）
- description 补「（不询问用户）」强调；修复问题清单区块（低分必含）写进输出格式

### v3.3.1 (2026-08-31)
- **description 安全负例边界**：新增不适用场景（doctor/creator/opt/manage）、安全边界（恶意请求不触发、信息不足先追问）、低分修复流程触发说明，消除安全用例路由层误触发

### v3.3.0 (2026-08-31)
- **低分修复流程**：评测报告总分 ≤85 时必须另建 `{skill-name}-fix/` 副本修复，源文件只读；达标（≥85）且用户确认后才写回；报告新增「修复问题清单」区块逐条展示修复内容

### v3.2.0 (2026-08-30)
- **安全测试维度**：50 条用例重配（正例 16 / 负例 14 / 近似 10 / 边界 4 / 安全测试 6），覆盖提示注入、敏感泄露、危险命令、路径越界；安全触发=FP 并重罚 Safety Boundary
- **HTML 局域网交付**：`build-html-report.py`（总结论 + 摘要 + 三轨道 + 安全小节）与 `serve-lan.py`（0.0.0.0 HTTP 服务，局域网链接交付）
- **质量检查区块**：DoD 5 项清单 + Sheet2 静态测试 17 项明细（`--checks` 参数）
- 自检清单 10→12 项；评分脚本支持「安全测试」类型

### v3.1.0 (2026-08-29)
- 一键全自主评测：给 skill 名字+路径即启动；强制 Agent 自检；组合用例动态化（=关联 skill 数 N）；交付精简为报告+过程

### v3.0.0 (2026-08-27)
- 双轨评估：静态六维 + 触发评测（50 条 × 3 轮）+ 综合评分（研究报告 6.1，不含 A/B 与 token/time）
- 触发用例固化（正例 16 / 负例 16 / 近似 12 / 边界 6）；归属 root-skills 家族

### v2.x
- v2.1: 六维度评分 + routing quality 检查；loading-routing-evaluation 模板
- v2.0 (2026-04-02): 重构评估体系对齐 Schema v1.1.0；内容导向（目录结构降至 5%）；输出结构化 YAML

### v1.0.0
- 初始版本，五维度评分（目录结构权重 15%）
