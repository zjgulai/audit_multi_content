# JSON Schemas - 评测数据结构规范

定义 evals / grading / benchmark / timing 的 JSON 字段。所有评测产物按此规范生成，保证跨迭代可对比。

## evals.json

评测集，位于 `evals/evals.json`（skill 目录内）或 `<workspace>/evals.json`。

```json
{
  "skill_name": "example-skill",
  "evals": [
    {
      "id": 1,
      "name": "descriptive-name",
      "prompt": "用户的真实任务 prompt",
      "expected_output": "成功结果的人类可读描述",
      "files": ["evals/files/sample.csv"],
      "expectations": [
        "输出包含 X",
        "使用了脚本 Y"
      ]
    }
  ]
}
```

字段：
- `skill_name`: 与 skill frontmatter 的 name 一致
- `evals[].id`: 唯一整数
- `evals[].name`: 描述性名称（不要叫 eval-0，要能看出测什么）
- `evals[].prompt`: 要执行的任务
- `evals[].expected_output`: 成功标准描述
- `evals[].files`: 可选输入文件（相对 skill 根）
- `evals[].expectations`: 可验证断言列表（评分依据）

## grading.json

断言评分结果，位于 `<run-dir>/grading.json`。

```json
{
  "expectations": [
    {
      "text": "输出包含 'John Smith'",
      "passed": true,
      "evidence": "转录第3步: 'Extracted names: John Smith'"
    }
  ],
  "summary": {
    "passed": 2,
    "failed": 1,
    "total": 3,
    "pass_rate": 0.67
  },
  "execution_metrics": {
    "tool_calls": { "Read": 5, "Write": 2, "Bash": 8 },
    "total_tool_calls": 15,
    "total_steps": 6,
    "errors_encountered": 0,
    "output_chars": 12450
  },
  "timing": {
    "executor_duration_seconds": 165.0,
    "grader_duration_seconds": 26.0,
    "total_duration_seconds": 191.0
  }
}
```

关键字段：
- `expectations[]`: 逐条断言，`text` + `passed` + `evidence`（evidence 必填，无证据 = FAIL）
- `summary`: 聚合统计
- `execution_metrics`: 工具调用与输出规模
- `timing`: 耗时

## benchmark.json

聚合基准，位于 `<workspace>/iteration-N/benchmark.json`。

```json
{
  "metadata": {
    "skill_name": "example-skill",
    "timestamp": "2026-01-15T10:30:00Z",
    "evals_run": [1, 2, 3],
    "runs_per_configuration": 1
  },
  "runs": [
    {
      "eval_id": 1,
      "eval_name": "descriptive-name",
      "configuration": "with_skill",
      "result": {
        "pass_rate": 0.85,
        "passed": 6,
        "failed": 1,
        "total": 7,
        "time_seconds": 42.5,
        "tokens": 3800
      }
    }
  ],
  "run_summary": {
    "with_skill": {
      "pass_rate": { "mean": 0.85, "stddev": 0.05 },
      "time_seconds": { "mean": 45.0, "stddev": 12.0 },
      "tokens": { "mean": 3800, "stddev": 400 }
    },
    "without_skill": {
      "pass_rate": { "mean": 0.35, "stddev": 0.08 },
      "time_seconds": { "mean": 32.0, "stddev": 8.0 },
      "tokens": { "mean": 2100, "stddev": 300 }
    },
    "delta": {
      "pass_rate": "+0.50",
      "time_seconds": "+13.0",
      "tokens": "+1700"
    }
  },
  "notes": [
    "断言 '输出是 CSV 文件' 两边都 100% 通过——可能不判别 skill 价值",
    "with_skill 平均多耗时 13s 但 pass_rate 提升 50%"
  ]
}
```

注意：
- `configuration` 必须是 `"with_skill"` / `"without_skill"`（精确字符串）
- `delta` 为 with − without
- `notes`: analyzer 补充的跨用例观察（非判别性断言、高方差 eval、token 代价）

## timing.json

运行耗时，位于 `<run-dir>/timing.json`。

```json
{
  "total_tokens": 84852,
  "duration_ms": 23332,
  "total_duration_seconds": 23.3
}
```

**捕获时机**: subagent 完成通知里带 `total_tokens` 和 `duration_ms`，只在那一刻出现——收到立即保存，不要批量后补。

## 命名约定

- 评测目录用描述性名称（`eval-extract-names/` 而非 `eval-0/`）
- 配置目录用精确值：`with_skill/`、`without_skill/`
- 迭代目录：`iteration-1/`、`iteration-2/`（对应每轮重写）
