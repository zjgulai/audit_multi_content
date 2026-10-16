# kb-l0-feishu

把 Momcozy 内容治理知识库的 **L0（源层）与飞书侧源数据**做每日同步与核对。
飞书侧全程只读；所有写入只落 `kb/` 下。

## Structure

```
kb-l0-feishu/
├── README.md
├── SKILL.md
├── .skill-meta/
│   └── manifest.yaml
├── references/
│   ├── coverage-matrix.md        # 12 类资源的逐类核对口径（进核对前先读）
│   ├── auth-and-permissions.md   # 身份清单 + 权限判定四步法
│   ├── scripts.md                # 各阶段脚本参数与用法
│   ├── gotchas.md                # 已知坑与事故台账（人确认过的）
│   ├── gotchas.proposals.md      # 升级候选（retro.py 机械生成，未经确认不许当依据）
│   └── CHANGELOG.md              # 本 skill 的改动台账（每条都写依据）
├── scripts/
│   ├── preflight.sh              # 阶段 0 前置自检（取代"乱试 2 小时"）
│   └── retro.py                  # 收尾自成长：记本轮事实 + 出升级候选（不自动改判据）
├── evals/
│   └── evals.json                # 评测集（3 条真实用户 prompt + 断言）
├── examples/
└── tests/
    └── red-case.md               # Iron Law RED 用例（待真跑回填）
```

## 自成长（SKILL.md §8）

跑完一轮，收尾执行（**从库内源跑**，不要用 `~/.dsh/skills/…` 那份）：

```bash
python3 kb/l7/skills/kb-l0-feishu/scripts/retro.py $RUN
```

- **事实层（全自动）**：把本轮事实机械推导后追加进 `kb/l8/retro/ledger.ndjson`
  （记录层数字、原因码集合、与上轮差、重复码累计轮数、阶段产物齐不齐），
  并往 `references/gotchas.proposals.md` 追加**升级候选**。候选落点按**库根**解析，
  固定在**库内源**并带「拒绝写装载位」护栏 —— 装载位是只读运行副本。
- **规则层（永不自动改）**：红线、闸门、四态口径、preflight 通过线一律要人确认。
  > 自动化的应该是**发现**，不是**裁决** —— 拿证据自动改判据，等于让被考核的一方自己改考卷。
- **落盘留痕**：任何 skill 文件被改，同一次改动里备份 + CHANGELOG + bump version + 验明文，
  最后**回灌装载位并跑 `skills_check` 证明第 3 类归零**（SKILL.md §8.3 第 5 步）。

## 渐进式披露

| 层 | 何时加载 | 内容 |
|---|---|---|
| frontmatter | 始终 | name / description / 触发词 |
| SKILL.md | 触发时 | 红线、核对范围硬规则、库根、权限判定、10 阶段序列、交付物 |
| `references/` | 需要时 | 逐类口径、权限细节、脚本参数、坑台账、升级候选、改动台账 |
| `scripts/preflight.sh` | 阶段 0 | 一次 30 秒的可执行自检（两身份 × 跨表跨 Base 能力矩阵） |
| `scripts/retro.py` | 收尾 | 记本轮事实 + 出升级候选（只写台账与候选，不动判据） |

## Features

- **覆盖矩阵 + 四态制**：12 类资源逐类出结论，不允许"没提就不查"
- **覆盖率闸门**：`S_feishu ⊆ S_report`，缺类不许收口
- **前置自检**：把认证/授权的试错压缩成一次判定
- **权限判定四步法**：含"库级禁止下载"的决定性实验
- **写操作默认预演**：`--apply` 前先看差异
- **运行档位**：`--check`（无人值守只读）/ `--sync`（需人放行）/ `--full`

## Quick Start

```bash
export PATH="$HOME/.dsh/bin:$PATH"
bash scripts/preflight.sh          # 阶段 0，必须先过

RUN=$(date +%Y%m%d-%H%M)
python3 kb/l8/align_l0_feishu.py $RUN       # 阶段 1 记录层（只读）
python3 kb/l8/align_l0_schema.py $RUN       # 阶段 2 结构层
```

## Compatibility

| 模型 | 状态 | 限制 |
|------|------|------|
| Claude | native | 无 |
| Kimi | native | 无 |
| Cursor | native | 无 |
| dsh | native | 需 lark-cli + python3 同机可用 |
| codex | native | 无 |
| GPT | bridge | 脚本执行需适配 |
| Minimax | bridge | 长表格需简化 |

## 家族关系

- 创建：`root-skills-creator`
- 评估：`root-skills-eval`
- 优化：`root-skills-opt`（只改 `-fix/` 副本）
- 结构体检：`root-skills-doctor`

## License

Proprietary — Momcozy internal use only.
