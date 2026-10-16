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
## 1. 家族成员（台账，已外置）

**成员表与家族级路由表已外置**：[`references/家族台账与路由表.md`](references/家族台账与路由表.md)
（含 14 个成员逐条、13 个 `brand-*` 子能力、家族级意图路由、冻结用例对账与本轮实测读数。）
★ **真源是 `kb/l7/registry/skills.yaml` 与 `routes.yaml`，不是那个文件、更不是本 skill** ——
要答「有哪些成员 / 这句话该谁接」，**先读 yaml**；那个文件只是可读视图。

## 2. 路由表（意图 → 成员）· 可对账

**路由表不是文档，是数据**：真源 = `kb/l7/registry/routes.yaml`，
对账器 = `kb/l7/scripts/routes_reconcile.py`。

**§2.1 / §2.2 已并入上面那份台账文件。**

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

