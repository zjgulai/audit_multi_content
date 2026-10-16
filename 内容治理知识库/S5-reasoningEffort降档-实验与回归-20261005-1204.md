# S5 · reasoningEffort 降档：实验、质量回归与生产验证

**日期** 2026-10-05 ｜ **改动面**：**只影响 `dsh --profile headless`**（守衡的 `kb_review_chain`、日更驱动）
｜ **全局设置未动**（交互会话仍 `max`）

## 一、机制（为什么必须这么做）

- `reasoningEffort` **刻意不是 profile 配置字段** —— 属**设置层**
  （`@deepseek-ai/dsh-agent-default-model` README 原话）；headless app 自己也没有 `--model/--effort` 开关。
- 唯一能做到「只影响本 profile」的路：用 `@deepseek-ai/dsh-settings-file` 的 `config.path`
  **把设置文档指到本 profile 自己那份**，由 profile 的 `cordis.patch.yml` 落这条覆盖。

落点（两处）：
- `~/.dsh/profiles/headless/settings.yaml` —— 全局设置的副本，**只改一行** `reasoningEffort: max → high`
- `~/.dsh/profiles/headless/cordis.patch.yml` —— `- id: settings / config.path: <上面那份>`

## 二、质量回归（3 单，同一素材、同一 task 文本）

| 素材 | 基线（max） | 降档（high） | 结论是否一致 |
|---|---|---|---|
| 文案 | 329.3 s ｜ `PASS` 0 问题 conf 0.99 | **120.2 s** | ✅ 一致（且同样指出「销量最高」需补来源） |
| 图片 | 303.1 s ｜ `BLOCK`（S-1.2） | 537.1 s | ✅ 一致（**该单输入不同，不可比**；它反而更慢） |
| 链接 | 611.5 s ｜ `BLOCK` 9 问题 conf 0.97 | **222.3 s** | ✅ 一致 |

- **三个干净可比样本中的两个：2.7×**；图片那单输入不同、且变慢 ⇒ **降档不保证更快**，取决于那一单要做多少轮。
- **3/3 结论逐项一致**（状态 / 问题数 / 置信度 / 条款号都对得上）。

**结构性的安全理由**（比样本更重要）：三态结论由 **引擎（确定性）** 产出，
LLM 只负责编排与转述；编排出错时 `skill_invocation_audit` + `--require-layer-preflight` 会 fail-closed。

## 三、生产验证（走守衡真实闸门）

| | 基线（max） | 改后 |
|---|---|---|
| 文案单链耗时 | 329.3 s | **142.3 s（2.3×，省 3.1 min）** |
| 结论 | `PASS` 0 问题 conf 0.99 | **完全一致** |
| 层前置 | — | `mode=enforced` 红 0 |
| 飞书落表 | `recvx8QgurQ5T4` | `updated recvx90E5NDCVk`，**回读一致** |

## 四、过程中出过一次事故（如实记账）

**第一次切换把生产改挂了**：我用 `grep -v '^ui-onboarding:'` 删了设置文件的顶层键，
**却留下它缩进的子行** ⇒ YAML 非法 ⇒ `dsh --profile headless` 起不来 ⇒
守衡那一单 2.3 s 就失败（闸门正确报「结论未知」并落了一行表）。

- **根因不是机制，是我的构造方式**；更关键的是**我验错了对象** ——
  `--dump-config` 只证明"路径被覆盖"，**不证明"那份文件能解析"**（解析发生在 boot）。
- **恢复**：从 `~/.dsh/profiles/headless/.backups-20261005-120019/` 还原 `cordis.patch.yml` → 2 分钟内生产恢复。
- **重做时的三条防线**：① 干净 `cp` + 单行 awk（不再用会掏空键的 grep）；
  ② **先 `yaml.safe_load` 验解析**；③ **先 `--patch` 指向同一份文件做启动测试**，
  通过了才切换 profile 自己的 patch。

## 五、回退（一条命令）

```bash
cp ~/.dsh/profiles/headless/.backups-20261005-120019/cordis.patch.yml.bak \
   ~/.dsh/profiles/headless/cordis.patch.yml        # 恢复成 []，推理档立刻回到 max
```

## 六、漂移提醒（唯一的新维护点）

`~/.dsh/profiles/headless/settings.yaml` 是全局设置的**副本**。全局若换模型/provider，
必须同步过来，否则 headless 链会用一份过期设置。自查：
```bash
diff <(grep -v reasoningEffort ~/.dsh/settings.yaml) \
     <(grep -v reasoningEffort ~/.dsh/profiles/headless/settings.yaml)   # 应无输出
```

---

# ★ 最终裁定（同日 12:35，四单整批实测之后）—— **已回退**

## 为什么要推翻上面第三节那个「2.3×」

上面第三节拿的是**单次样本**（文案单 142.3 s vs 基线 329.3 s）。在**同一档位（high）下再跑同一条素材**，
得到 **391.3 s** —— 同设置的两次相差 **2.75×**。⇒ 那次 2.3× 是**离群样本**，不是档位效应。

## 四单整批对比（每档各 4 单，同一批素材、同一条链）

| 档位 | 各单墙钟（s） | 合计 | 均值 | 区间 |
|---|---|---|---|---|
| **max**（S5 前） | 329.3 / 303.1 / 234.1 / 611.5 | 1478.0 | 369.5 | 234–612 |
| **high**（S5 后） | 395.1 / 379.1 / 380.4 / 393.1 | **1547.7** | **386.9** | 379–395 |

- ⇒ **降档这一轮反而慢 4.7%**；而**档位内**方差高达 2.6×（`high` 另有 120.2 / 142.3 两个快样本）。
- ⇒ **S5 的端到端收益无法证明**。质量侧仍然成立（3/3 结论逐项一致）——**问题是它没换来时间**。

## 裁定

**已回退**（2026-10-05 12:35）：`cordis.patch.yml` 还原为 `[]`，`settings.yaml` 改名
`settings.yaml.disabled-S5-20261005`。生产验证：headless 正常、走全局设置（`max`）、无残留认领/锁。

理由：**没被证明有效的改动不留在生产** —— 它带一个新维护点（设置副本会漂移），却换不来可测的时间。

**若要重开**（例如你图的是**省 token 成本**而不是省时间 —— `high` 每轮思考更少，API 费用更低）：
```bash
P=~/.dsh/profiles/headless
mv "$P/settings.yaml.disabled-S5-20261005" "$P/settings.yaml"
printf -- '- id: settings\n  config:\n    path: %s/settings.yaml\n' "$P" >> "$P/cordis.patch.yml"
node <dsh bin> --profile headless "只答：ok"     # 必须先验启动，再上线
```

## 从这件事学到的（写给下一个改这条链的人）

1. **端到端方差 ≫ 单点差异**：同素材同设置实测 120–391 s。**任何"提速 X 分钟"的说法，必须给区间与样本数**，单次对比不算数。
2. **真正的确定性收益在脚本侧**（四层前置 832.6 s → 7.7 s，可复算、无方差）；
   端到端剩下的时间由 agent 自己的轮数与探索深度决定，**那一层要靠改流程，不是改档位**。
3. **验错对象 = 没验**：第一次切换用 `--dump-config` 验「路径被覆盖」，却没验「那份文件能解析」（解析发生在 boot）⇒ 生产挂 2 分钟。
