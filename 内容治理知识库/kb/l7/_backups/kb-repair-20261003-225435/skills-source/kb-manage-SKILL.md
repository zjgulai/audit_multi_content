---
name: kb-manage
description: |
  Momcozy 内容治理知识库的**工作流家族管理器**：管注册表、管路由、管生命周期。
  它不干具体的知识库活，只回答「这件事该走哪个成员」和「这个成员现在是什么状态」。
  当用户问「知识库里这几个 skill 怎么分工 / 哪个 skill 负责什么 / 这个说法该走哪个 skill /
  知识库 skill 家族全景 / 成员列表 / skill 注册表 / 路由表 / 家族登记 / 谁负责这条链路 /
  新增一个知识库 skill 要登记到哪 / 停用 / 下线某个成员 / 成员的生命周期与版本」时使用。
  触发词：kb-manage、知识库工作流家族、skill 家族管理、注册表、路由表、家族全景、成员列表、
  家族路由、skill 生命周期、成员启停、登记成员、谁负责、该走哪个 skill、知识库 skill 分工、
  kb family、registry、routing。
  两条链的入口**不在本 skill**：供给链（L0→L7 数据）走 kb-pipeline，评审链（内容能不能用）走 kb-review。
  不适用：创建一个新 skill（走 root-skills-creator）；评测 / 优化 / 诊断 skill 本身
  （走 root-skills-eval / root-skills-opt / root-skills-doctor）；跑知识库链路（走 kb-pipeline）；
  判断一段内容能不能发（走 kb-review）。
version: "1.0.0"
last_updated: 2026-09-29
license: "Proprietary — Momcozy internal use only"
complexity: "standard"
compatibility:
  claude: { status: "native" }
  kimi: { status: "native" }
  cursor: { status: "native" }
  gpt: { status: "bridge", limitations: ["路径分隔符需适配"] }
  minimax: { status: "bridge", limitations: ["长表需分页"] }
  dsh: { status: "native", notes: "skills_check.py 同机可用" }
  codex: { status: "native" }
---

# kb-manage —— 知识库工作流家族管理器

**一句话**：家族管理 = **注册表 + 路由 + 生命周期**。本 skill 只做这三件事，
不做质量评测（那是 `root-skills` 家族），也不跑数据链路（那是 `kb-pipeline`）。

三者只在**一个箭头**上交汇：**新建 / 改动某个成员 skill** 时，走
`kb-manage`（登记）→ `root-skills-creator`（造）→ `root-skills-eval`（评，F1 ≥ 0.90 才放行）
→ `kb-manage`（登记为生产并安装）。

---

## 1. 家族成员（14 个，就按这个口径）

| # | 成员 | 层 | 状态 | 角色 |
|---|---|---|---|---|
| 1 | `kb-manage` | — | 生产 | 家族管理：注册表 + 路由 + 生命周期（本 skill） |
| 2 | `kb-pipeline` | L0–L7 | 生产 | 供给链入口：按 `layers.yaml` 编排 L0→L7 |
| 3 | `kb-review` | — | 生产 | 评审链入口：单条内容「能不能用」走这条 |
| 4 | `kb-check` | — | 生产 | 统一闸门：把全库的 check 一次跑完 |
| 5 | `kb-repair` | — | 生产 | 不过就修：闸门红了按原因码修 |
| 6 | `kb-l0-feishu` | L0 | 生产 | 只对账 L0（飞书侧只读） |
| 7 | `kb-content-review` | L7 | 生产（**链内组件**） | 出三态结论的**依据**：条款号 / 锚点 / 逐字摘录 |
| 8 | `kb-canonical-lookup` | L4 | 生产 | 查询型：这条规则的条款号是多少 / 定稿了吗 |
| 9 | `kb-p0-check` | L5 | 生产 | 查询型：这个是 P0 吗 / 命中哪些 P0 模式 |
| 10 | `kb-recall` | L6 | 生产 | 查询型：按 BM25 + 向量召回单元（已并入原 `kb-retriever`） |
| 11 | `kb-ingest-extractor` | L1/L2 | 规划 | 素材 → 知识单元（本轮只登记，不安装） |
| 12 | `kb-media-extractor` | L1 | 规划 | 图片 / 音视频 → 可入库信息（本轮只登记） |
| 13 | `kb-clause-extractor` | L3 | 规划 | 外部标准 → 条款级单元（本轮只登记） |
| 14 | `brand-product-fact-curator` | L3 | 规划 | SKU 级产品事实基线（本轮只登记） |

**成员 1–10 是"入口/组件"，11–14 是"规划中的供给侧成员"（`status: 规划`，`trigger_keywords` 留空 = 不参与路由）。**

### 1.1 同一层里"读"与"写"分开（8/9/10 三个查询型 skill 的设计原则）

| 层 | 读（查询，只读，用户可直接问） | 写（重建 / 发号，只由 `kb-pipeline` 在 `--apply` 下触发） |
|---|---|---|
| L4 | `kb-canonical-lookup` | `kb/.work/l4_article.py RUN`（发号 / 晋升 canonical） |
| L5 | `kb-p0-check` | `kb/.work/l5_prep.py RUN` → `kb/.work/l5_export.py RUN` |
| L6 | `kb-recall` | `kb/.work/l6_build.py RUN`（重建 BM25 + 向量索引） |

> ⚠️ **"L0–L3 更新后 L4–L6 自动同步"不靠"做成 skill"实现。**
> skill 跑完**不会**自动调下一个。同步由 `kb-pipeline` 按 `kb/l7/registry/layers.yaml`
> 编排，靠**各层的幂等键**保证重跑安全。查询型 skill 只读，永远不写。

### 1.2 13 个 `brand-*` 消费侧子能力（**保留其 skill 能力**，**不计入上面 14 个**）

它们是**评审链的成员**——由 `kb-review` 或 `内容审查总控` 编排，
**不单独对外当入口**。什么说法该调用哪个：

| 用户的说法 | 调用谁 |
|---|---|
| 文字 / 广告用语 / 宣称措辞 / listing、PDP 文案合规 | `文案合规审查` |
| 图片、主图、素材图、婴幼儿画面安全、图上文字 | `图片安全审查` |
| 视频、短视频、达人视频、画面 / 时间码 / 口播 | `视频安全审查` |
| 产品宣称真伪、SKU 事实、认证范围、测试报告 | `产品宣称核验` |
| AI 生成披露、换脸、肖像 / 商标授权、儿童出镜隐私 | `AI溯源与权利审查` |
| 美国本地化、计量单位、文化歧义、直译腔 | `美国本地化审查` |
| 送审登记、哈希 / SKU / 渠道 / 语言采集 | `送审登记` |
| 多条发现汇总成最终裁决、优先级、责任人 | `审查裁决` |
| 出报告 / 群发摘要 / 存档留痕 / 版本追溯 | `审查报告与记忆` |
| 审查流程本身的准确率、漏放、覆盖率评测 | `审查流程评测` |
| 证据源（法规 / 平台政策）维护与登记 | `证据源维护` |
| 结果同步到飞书群 / 多维表格 / 分派责任人 | `飞书审查流转` |
| 一批素材走**发布前审查全流程**（文字 + 图片 + 视频一起） | `内容审查总控` |

---

## 2. 路由表（意图 → 成员）· 可对账

**路由表不是文档，是数据**：真源 = `kb/l7/registry/routes.yaml`，
对账器 = `kb/l7/scripts/routes_reconcile.py`。

### 2.1 家族级意图（14 个成员）

| 意图（用户怎么说） | 路由到 | 为什么 |
|---|---|---|
| 同步一下知识库 / 跑一遍知识库链路 / 知识库同步到最新 / 全链体检 / L0 到 L7 走一遍 / 知识库该更新了 | `kb-pipeline` | 全链编排 |
| 只对账 L0 / 飞书侧改了什么 / L0 对齐一下 / L0 落库 / 跑一下每日同步 | `kb-l0-feishu` | 只看 L0，不动下游 |
| 这段内容能不能发 / 审一下 / 合规检查 / 会不会违规 / 有没有风险 / 踩线 / 禁用 / 敏感 | `kb-review` | 评审链入口（单条内容） |
| 为什么判 BLOCK / 依据是哪条规则 / 知识库怎么说 / 三态结论的依据 / 逐字摘录 | `kb-content-review` | 链内组件：出依据 |
| 这条规则的条款号是多少 / 这个条款号对应哪条规则 / 这条规则定稿了吗 / 进 canonical 了吗 | `kb-canonical-lookup` | L4 只读查询 |
| 这个是 P0 吗 / 命中哪些 P0 模式 / 优先级是 P0 吗 | `kb-p0-check` | L5 只读查询 |
| 召回一下 / 检索单元 / 知识库里有哪些相关单元 / 从知识库目录回答问题 / 查资料 | `kb-recall` | L6 只读查询（含原 `kb-retriever`） |
| 知识库体检 / 跑一遍所有闸门 / 闸门过没过 / 全库自检 / 信封闸门 | `kb-check` | 统一闸门 |
| 闸门没过帮我修 / 知识库哪里坏了修一下 | `kb-repair` | 不过就修 |
| 知识库这几个 skill 怎么分工 / 谁负责什么 / 这个说法该走哪个 skill / 注册表 / 家族全景 | `kb-manage` | 本 skill |
| 一批素材走发布前审查全流程 / 送审 / 审查全流程 / 给个统一结论 | `内容审查总控` | 端到端多模态入口（消费侧） |

### 2.2 冻结用例对账（13 个 `brand-*` × 5 条 = 65 条）

- 冻结用例：`/Users/lute/Desktop/skill/内容治理中文skill/_基线用例.json`
- 打分器：`~/.dsh/skills/root-skills-eval/scripts/score-trigger-eval.py`，门槛 **F1 ≥ 0.90**
- 对账方式（**就是这条命令**）：

```bash
# 1) 先把每轮的"实际被谁接走"落盘（每条 prompt 3 轮、每轮一个新 agent，只给提示词）
#    产物：kb/l7/reports/<RUN>-routes-winners.json
# 2) 再拿路由表逐条对账：实际被谁接走 vs 路由表写谁
kb/kbpy l7/scripts/routes_reconcile.py kb/l7/reports/<RUN>-routes-winners.json
```

对账器输出三节：① 逐条 `prompt_id → 期望成员 → 实际成员 → 一致?`；
② 不一致清单（含"被谁抢走"的计数）；③ 按成员的命中率 + 与 `score-trigger-eval.py` 的 F1 交叉核对。

#### 本轮实测（2026-09-29 · 轮 2）

| 口径 | 用例数 | 结果 |
|---|---|---|
| **改动前**（英文 description，kb-content-review 带 12 个泛化词） | 65 条冻结用例 × 3 轮 | 13 个 brand-* **0 个过门槛**；6/65 逐条全轮命中；kb-content-review 抢走 **88/195** 次 |
| **改动后**（收窄 + 并发中文翻译轮次落地 + 4 轮定向修正） | 115 条（65 冻结 + 50 新增成员）× 3 轮 | 23 个成员 **22 个过门槛**；110/115 逐条全轮命中；**我的 10 个成员全部 ≥ 0.90**（最好轮全 1.000） |
| **v2 用例修订后**（只改 `G3`/`I2`，v1 未动） | 115 条 × 3 轮 | 仍 **22/23**；`AI 溯源` 0.440 → **0.222（更差）** → **改用例没修好它**，见变更记录 §9 |

产物：`_eval-kb-manage/blind_before_v2.winners.txt` · `blind_after_r3.winners.txt` ·
`results_final/route_reconcile.md`、`results_r4/route_reconcile.md`（最终轮）。**改前/改后必须用同一协议（盲测）与同一打分器**，见 `_eval-kb-manage/`。

★ 唯一未过门槛的是 `AI溯源与权利审查`（F1 0.333）——根因是**冻结用例集自身的歧义**
（G3 与 I1 语义几乎相同却要求两个不同归属），已记入 `routes.yaml → measured_20260929.known_conflict`，
**不是靠改 description 能修的**。

**口径**：`routes.yaml` 只写"应该由谁接"；"实际谁接走了"是运行时算出来的，**不写回表**。

---

## 3. 生命周期（成员从哪来、到哪去）

| 阶段 | 动作 | 谁做 | 闸门 |
|---|---|---|---|
| 规划 | 在 `skills.yaml` 登记一行 `status: 规划`，`trigger_keywords: []` | `kb-manage` | 无（不安装） |
| 造 | 建 skill 目录（`SKILL.md` + `references/`） | `root-skills-creator` | Iron Law 对比 |
| 评 | 静态六维 + 触发盲测（3 轮） | `root-skills-eval` | **触发 F1 ≥ 0.90**，不达标不登记 |
| 修 | 不达标在副本上修，再评 | `root-skills-opt` | 回归无新增缺陷 |
| 登记 | 写 `kb/l7/registry/skills.yaml`：`status: 生产`、`source`、`selftest` | `kb-manage` | `kb/kbpy l7/scripts/skills_check.py` 五类全 0 |
| 装 | 副本装进 `~/.dsh/skills/<id>/` | `kb-manage` | `skills_check.py` 第 3 类逐文件 cmp 通过 |
| 停用 | `status: 废弃`；安装副本移入 `kb/l7/_skill-backups/` | `kb-manage` | 第 2 类不报"装了但没登记" |

**硬规则**：① 不达标**不得登记**；② `not_for` 必填非空；
③ 同层"读/写"分开，查询型成员只读；④ 停用留痕，不静默删目录。

---

## 4. 注册表（静态真源）

| 文件 | 管什么 |
|---|---|
| `kb/l7/registry/skills.yaml` | 消费侧 skill 的编目与安装状态（**本家族 14 成员 + 13 个 brand-\* 都在这里**） |
| `kb/l7/registry/layers.yaml` | L0–L7 **层契约**：依赖 / 引擎 / 输入输出 / 幂等键 / 闸门 / cwd / 解释器 / 信封 |
| `kb/l7/registry/l7.json` | 引用契约 / 检索门限 / 裁决规则 |
| `kb/l7/registry/routes.yaml` | **路由表**：意图 → 成员 |

三者关系：`skills.yaml` 答"有哪些成员"，`layers.yaml` 答"链路怎么跑"，
`routes.yaml` 答"这句话该谁接"。

### 4.1 注册表判据（跑哪条 check）

```bash
kb/kbpy l7/scripts/skills_check.py      # 五类问题全 0、退出码 0
kb/kbpy l7/scripts/layers_check.py      # layers.yaml 结构 + 引擎存在性 + cwd/python/envelope
kb/kbpy l7/scripts/routes_reconcile.py <winners.json>   # 路由表对账
```

> `skills_check.py` 第 4/5 类判 `depends_on_engine` / `selftest` 路径时**不做 `expanduser`**
> （第 1001–1002、1018–1019 行）：凡 `~` 开头的路径都会被误报"不存在"。
> **登记这两个字段时一律用库根相对路径**（如 `l8/l2_split_run.py`），不要写 `~/...`。

### 4.2 解释器与 cwd（两条例外，别踩）

- **解释器**：受管 external-tools python 缺 numpy / fastembed，L6 召回两者都要
  （`l6/retriever.py:245` `np.load`、`:249` `from fastembed import TextEmbedding`）。
  → 一律 `kb/kbpy <kb 内相对路径> [args]`，或显式 `KB_INTERP_OK=1 /usr/bin/python3 <脚本>`。
- **cwd**：29 个 `kb/l8/*.py` 用 `"kb/..."` 相对路径 → **cwd 必须是 `kb/` 的上一级**
  （`~/.dsh/Momcozy知识库`）。`layers.yaml` 每层都有 `cwd` 字段，就是为它而设。

---

## 5. 何时停下来问人

- 要**新建 / 改动**一个成员 skill：先答完变更协议 5 问（§6），答不出来就先别动。
- 触发电测**没过 0.90**：不许"先装上再说" —— 不达标不得登记。
- 要动 `kb/l0…l6` 的**数据文件或台账**：不在本 skill 范围内，先只读取证。
- 发现 `kb/l2/units.jsonl` 等文件在**你没有写的情况下**行数变了（实测发生过 10551 → 10650）：
  有并发写入者，**任何"层已跑完"的结论必须带 run_id + 时间戳**，不能只看文件状态。

## 6. 变更协议（改任何东西之前先答这 5 问）

1. 这个文件**还有谁读**、走什么通道？
2. 还有谁**写**它？
3. 改完由**哪条既有 check** 判定、那条 check 自己有没有缺陷？
4. 用什么**通道**写？（python 写 `.py/.txt/.md` 会落成"stat 虚高 4096"的信封态 →
   一律「python 生成内容 → 写到无扩展名临时件 → `cp` 落到目标」）
5. 有没有**干净回滚基线**？

答不出来就先别动。变更记录写进 `kb/l7/reports/<RUN>-change-record.md`。
