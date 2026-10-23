# DSH 知识库规则加固实施计划

spec：[`2026-10-22-dsh-kb-rule-hardening.md`](../specs/2026-10-22-dsh-kb-rule-hardening.md)

实施状态（2026-10-22）：**Task 1 审计器、测试、PMO 留底和正式知识库入账已完成；活动库验收按设计返回 FAIL，暴露 §6.5 元数据缺口。** 后续规则数据整改需逐条确认，不能用默认值补齐。

## 不变量

- 生产审核入口、skill 路由、让位表、L0–L7 执行顺序和三态输出保持不变。
- 审计器默认只读；不自动修改 `$KB_ROOT`、仓库快照、账本、守衡进程或 skill 文件。
- 找不到真实运行时根/无法读取规则时退出 2；发现规则契约缺口退出 1；只有明确满足契约才退出 0。
- 不从空字段推断法域、负责人、适用内容类型或法务结论。

## Review Focus

1. 活动根从 `tools.mjs` 导出读取，工作目录含空格/Unicode 也能解析；不能依赖硬编码路径。
2. JSONL 空行可接受，损坏行必须点名文件与行号且退出 2。
3. P0 的 L3/L5 集合必须双向比较；不能只检查“规则码在源码出现”。
4. 快路同一规则码可能有多个源规则行；唯一性按 `rule_id` / `pattern_id` 判断，不误报合法规则码复用。
5. 缺少 PRD 元数据不得被 `unknown`、空列表或推断备注算成完整；必须点名 rule_id 和 gap code。

## Task 1：新增只读 KB 规则审计器与单测

**Files:**
- Create: `tools/verify_dsh_kb_rules.py`
- Create: `tools/test_verify_dsh_kb_rules.py`
- Test: `python3 -m unittest tools.test_verify_dsh_kb_rules -v`

**Interfaces:**
- `load_jsonl(path: Path) -> list[dict]`；坏行抛带路径与行号的 `AuditInputError`。
- `discover_runtime_root(repo_root: Path) -> Path`；以 subprocess 导入 `tools.mjs` 读取导出的 `KB_ROOT`，失败抛 `AuditInputError`。
- `audit_kb(root: Path, repo_snapshot: Path | None = None) -> dict`；纯只读，返回 `status`, `checks`, `findings`, `fingerprints`, `workflow_impact`。
- `main(argv: list[str] | None = None) -> int`；支持 `--root`, `--json`, `--selftest`。

- [x] 写测试：完整 fixture 的 P0 规则码与快路集合相等、来源完整时状态通过。
- [x] 运行单测，确认首次失败在 import 缺少模块/函数（RED）。
- [x] 实现 JSONL 解析、运行根发现、契约检查、指纹与状态码。
- [x] 写反例测试：缺码、孤儿码、重复 ID、坏 JSON 行、错误 SHA256、缺来源、缺适用维度分别产生具名 finding。
- [x] 运行测试确认 PASS；再运行内置 `--selftest`。
- [x] 验证 fixture 输入树哈希前后相同；活动 `$KB_ROOT` 路径仅执行读取，并由只读审计回读指纹。
- [x] 运行 P0 matcher、fastpath、regression、L5 integrity、freshness；与本规格改前基线比较。P0 回归通过；L5 integrity 两项存量 FAIL。
- [x] 引擎/skill/KB 自证复跑；`verify_engine_contract` 212/212，skill 路由 S1 与活动副本 S2 通过；总体 skill/KB 检查保留基线红项。
- [x] 使用本机正式 `dsh-kb` `kb.js::ingest()` 人工入口写入 PMO 留底，`read()` 回读 `found=true`，ledger 核对 `action=ingest`、`human=true`；条目 `ref-dsh-kb-rule-hardening-audit-20261022`。`verify_ingest_coverage.py --strict --hours 72` 确认本留底已覆盖，但因窗口内另 12 个历史留底缺条目仍整体退 1。

## Task 2：出具活动规则缺口清单（KBH-02/03 输入）

**Files:**
- Create: `tools/report_dsh_kb_rule_gaps.py`
- Create: `tools/test_report_dsh_kb_rule_gaps.py`
- Create: `PMO/DSH规则缺口清单-活动库快照对比-20261022.md` and `.json`

- [x] 用 JSON 输出逐条汇总 PRD §6.5 缺项、分类/适用范围盘点、九场景未测状态与快照行级差异，见 `PMO/DSH规则缺口清单-活动库快照对比-20261022.json`。
- [x] 不生成/写入任何 L3/L5 数据；无批准映射的场景均保持 `UNMEASURED`。
- [x] 同次读取活动根规则行形成分母；分别列出行数、唯一 rule_id、P0 规则码数；快照差异只做定位，不判权威端。
- [x] JSON 报告写入前拒绝目标目录位于活动库或仓库快照树内；fixture 用例 4/4 通过。

## Task 3：业务裁定后的规则元数据与覆盖整改（依赖 Owner/专业方）

- [ ] 根据 KBH-02 缺口表逐条获得来源、市场、内容类型、责任方和有效期确认。
- [ ] 将确认内容写入权威源并生成 L3/L5；不直接编辑派生文件。
- [ ] 运行生成器 dry-run，对扩容守卫差异逐项解释；没有批准不加 `--accept-p0-expansion`。
- [ ] 加规则正反例后跑 P0 与跨模态回归；只有用例与报告均可追溯才申请生效。

## Task 4：输出与 skill 工作流兼容验收

- [x] 本轮旧/新版本逐项 A/B 判为 N/A：变更只涉及只读缺口报告、L8 自证标签与验收文档，没有修改审核入口、路由、skill、L0–L7、matcher、L5 模式或报告生成器；以改动面审查和既有 E2E 自证验收，不把活动库/仓库快照误作新旧版本。
- [x] 审计器输入不完整/PRD 词表漂移退出 2，真实规则缺口退出 1；不输出 PASS。报告生成成功与规则通过状态分开。
- [x] 当前复跑 `python3 tools/verify_engine_contract.py`（212/212）、`node tools/test_agent.mjs`（306/306）、`node tools/verify_cards.mjs`（350/350）。`verify_skill.py` 的 S1/S2 工作流检查通过；总自证有 4 项存量不符（#6 基座命令退出码、#8 KB E7、#9 风险标签盘漂移及缺少还原账）；细节记入 KBH04A/05 验收 PMO。KB E7 与 L5 integrity 存量失败未改。
- [x] 本 ticket 没有修改生产入口、skill、规则路由或 L0–L7 调用链；守衡运维自证重启前后全过，重启后 `wsConnected=true`。
- [x] 固定未来 A/B 基线规则：如后续改到生产链，必须先冻结同一已验收版本代码与输入 fixture，再逐项比较路由、skill、层前置、三态和报告字段；当前仓库 `HEAD` 与活动 KB 快照不是可互换的版本基线。

## Task 5：知识库登记与落库闭环

- [x] 创建带判据路径的 PMO 留底。
- [x] 六份本轮 DSH 相关 PMO 留底均有正式 `dsh-kb` `kb.js::ingest()` 人工入口记录并 `read()` 回读；本轮验收的两条版本记录为 `ref-dsh-kbh04a-kbh05-acceptance-20261022` 与最终四样例补充 `ref-dsh-kbh04a-kbh05-acceptance-fixture-v2-20261022`，其余包含 `ref-dsh-regression-trace-matrix-20261022`、`ref-dsh-kb-rule-hardening-audit-20261022`、`ref-dsh-rule-gap-report-activity-snapshot-20261022`、`ref-dsh-rule-gap-summary-20261022`、`ref-dsh-p0-regression-label-20261022`。摘要首次 L2 入库因同根来源不构成互证被拒，按规则降为 L1 后成功；P0 标签条目首次因正文不足 200 字被拒，补充后成功；拒绝和成功均留账。
- [x] 运行 `python3 tools/verify_ingest_coverage.py --strict --hours 72`；本轮 PMO 均已覆盖，窗口内其他历史留底缺失数以当次命令读数为准，详见 PMO 报告。
- [x] 已确认权威 ingest API 可用；不适用“无权威入口时标未闭合”的回退分支。

## Task 6：KBH-04 / KBH-05 专项回归清单

- [x] 复跑现有活动 matcher、P0 fastpath、L8 P0 regression（活动库 19 模式/175 用例、仓库快照 17 模式/162 用例）及 agent/card 回归（305/305、350/350）。自证标签从实际模式数生成，并由 `tools/test_p0_regression_labels.py` 防止再写死。
- [x] 盘点现有 P0 逐码正例计数、共享边界反例、L7 测试编号和 PRD §7.2 九场景读数，保存于 `PMO/DSH专项回归追溯矩阵-20261022.md` 并正式入库；矩阵明确区分 TESTED / PARTIAL / UNMEASURED。
- [x] **KBH-04A（自动化）**：`tools/report_dsh_kb_rule_evidence.py` 按 `rule_id` 生成正例、来源锚点和实际命中测试编号索引；活动库读数 639 个 ID / 19 TESTED / 169 正例 169 命中 / 620 UNMEASURED。没有逐 ID 关联的条目标为未测，不猜映射。
- [ ] **KBH-04B（依赖裁定）**：为适用规则逐条确认否定/引用/全角/英文边界反例和预期结论；未裁定不纳入通过分母。
- [x] **KBH-05（自动化 + 固定 fixture）**：`tools/agent/prd53_acceptance.fixtures.json` 与 `prd53_acceptance.test.mjs` 固定 REVIEW 2/3 条与 BLOCK 2/4 条样例，执行三态、报告、证据、唯一计数和动作回执；L7 同图身份及外层回执顺序链接 N1/N2/N4 与 W1/W7/W10/Y4/Y5。使用保留域 URL 仅验透传，不宣称真实外链可达。
