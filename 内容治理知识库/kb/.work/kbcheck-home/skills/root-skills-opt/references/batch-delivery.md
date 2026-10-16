# 交付目标契约（root-skills-eval / root-skills-opt 共用）

> 为什么存在：**交付路径随批次变化，禁止把路径写死**进技能或脚本。例如某批源池是
> `Pray-skill-fix2/`、完成副本要进 `Pray-skill-fix-已修复/`、报告要进 `ABI-Skills-评测报告/`；
> 下一批可能换成完全不同的目录。因此本契约只定义「交付到**本次解析出的目标**」，不定义具体路径。

## 1. 解析优先级（从高到低）

1. **显式参数 / 用户指明**
   - `build-final-report.py`：`--output`（报告 HTML）、`--desktop-source-root`（源目录）、
     `--desktop-fix-root`（完成副本目录）、`--keep-fix-suffix true|false`（命名）、`--batch-config`（配置路径）。
   - Agent 收到用户口头指定（如「完成副本放 X、报告放 Y」）时等同显式参数。
2. **批配置 `.batch.yaml`**（推荐主力）
   - 位置：当前工作目录的 `./.batch.yaml`，或 `--batch-config <path>` 显式指定。
   - 路径跟着批次走：换批次只改 `.batch.yaml`，技能与脚本零改动。
3. **相对默认**（无配置时）
   - 完成副本：被测源所在批目录的**同级** `已执行/`；
   - 报告：被测源所在批目录的**同级** `评测报告/`。
4. **兜底**：`~/Desktop`（保持历史「桌面与源并排」行为，仅作最后回退）。

## 2. `.batch.yaml` 字段

```yaml
# 示例：81 技能批
source_dir: "Pray-skill-fix2"          # 被测源 Skill 目录（待执行池，可选）
done_dir: "Pray-skill-fix-已修复"       # 完成副本写入目录（可选）
report_dir: "ABI-Skills-评测报告"       # 最终 HTML 报告目录（可选）
keep_fix_suffix: false                 # 完成副本是否保留 "-fix" 后缀；false 则交付名 = {name}
dedupe: newest                         # 目标已存在时：newest | skip | overwrite；默认 newest
```

- 所有路径为**相对当前工作目录**或绝对路径；脚本只做解析不做硬编码。
- `keep_fix_suffix: false` 时，交付校验检查 `done_dir/{name}`（而非 `done_dir/{name}-fix`）。
- `dedupe: newest`：逐文件比较内容与 `SKILL.md version`/`last_updated`，保留最新，禁止静默覆盖。
- `dedupe: skip`：目标已存在且非空则跳过（不覆盖、不报错）。
- `dedupe: overwrite`：目标已存在则整体覆盖（默认不用，避免丢新版）。

## 3. 与脚本参数的映射（build-final-report.py）

| 批配置 | 等价 CLI | 说明 |
|---|---|---|
| `source_dir` | `--desktop-source-root` | 校验源 Skill（只读）所在目录 |
| `done_dir` | `--desktop-fix-root` | 完成副本所在目录（配合 `keep_fix_suffix` 决定 `{name}` / `{name}-fix`） |
| `report_dir` | `--output {report_dir}/{name}-final-report.html` | 最终报告输出 |
| `keep_fix_suffix` | `--keep-fix-suffix true|false` | 完成副本命名 |
| （无） | `--batch-config <path>` | 显式指定批配置；缺省自动读 `./.batch.yaml` |

## 4. 谁在什么时候写哪里

- **root-skills-eval 低分修复流程**：修复在 `{name}-fix/` 副本进行（源只读）；达标 + B 卷门禁后，
  把完成副本写入解析出的 `done_dir`（命名按 `keep_fix_suffix`），最终报告写入 `report_dir`，
  生成报告时加 `--require-desktop-fix` + 对应目录参数（或批配置），由 `desktop_fix_check` 校验后放行。
- **root-skills-opt**：同一交付契约。副本达标 + B 卷门禁后，写入解析出的 `done_dir`，不写回源。
- **一次达标（未进修复）**：不强制 `--require-desktop-fix`；报告仍写入解析出的 `report_dir`。

## 5. 防呆

- 目标目录已存在同名且内容更新 → 保留最新（`dedupe: newest`），并把旧版留档，不直接覆盖。
- 找不到配置又无显式参数 → 回退 `~/Desktop` 并打印提示，不静默改变用户目录结构。
- 报告与 fix 版本一致性：最终报告 `eval_info.version` 必须等于交付副本 `SKILL.md version`
  （沿用「版本一致性/最终版对齐」硬校验），先定版再出报告。
