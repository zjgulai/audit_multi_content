# Root Skills Batch Driver - 批量评测编排驱动

root-skills 家族成员（Orchestration 编排驱动）。把「评测一整个目录里的 skills」跑成
可靠、可续、可留痕的流水线：启动并监控 `root-skills-eval` 评测 subagent，心跳以磁盘
落盘 mtime 为准，连续无进展超时即判卡死并按落盘完成度续接/重启，全程断点续跑、事件留痕。

- 硬规则 → 引用 `root-skills-eval/references/batch-evaluation.md`（含 v3.18.1），不复制。
- 确定性核心 → `scripts/batch-driver.py`（scan / heartbeat / record / summary / timeout）。
- 不越权打分 / 出题 / 改正文，只做编排状态机。

## 家族位置

- `root-skills-eval`：决定「怎么评一个」（出题/执行/打分/HTML，提供 `--batch` 与硬规则）
- **`root-skills-batch-driver`**：决定「怎么把一批评完」（本 skill）
- `root-skills-doctor`：评完后的批量结构修复（不参与编排）

## 工作流

```
scan（发现 skill + 合并 checkpoint）
  → 启动 eval subagent → heartbeat（落盘 mtime 判无进展）
    → stale 则查盘完成度 → 续接 / 重启 → record 留痕
  → summary（聚合 + 事件清单 + 连续中断标记）
```

## 目录结构

```
root-skills-batch-driver/
├── SKILL.md                       # 编排驱动（正文稳定）
├── README.md
├── .skill-meta/manifest.yaml
├── references/orchestration-loop.md   # 编排循环 / 状态机 / 事件类型
├── scripts/batch-driver.py            # 确定性编排核心
├── examples/batch-run.md              # 一次完整批跑示例
└── tests/                             # Iron Law RED 场景
```

## 快速使用

```bash
# 自检
python3 scripts/batch-driver.py --selftest

# 扫描一个 skills 目录
printf '%s' '{"action":"scan","skills_dir":"./skills","state_path":"./batch-progress.json"}' \
  | python3 scripts/batch-driver.py
```

## 安全边界

不编造评测结果；进度只认磁盘落盘；被测 skill 源目录只读；不导出密钥或系统提示词。

---

**版本**: 1.0.0 | **框架**: root-skills
