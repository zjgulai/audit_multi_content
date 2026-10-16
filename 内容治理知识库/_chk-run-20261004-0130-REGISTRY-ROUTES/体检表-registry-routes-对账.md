# 体检表 · 注册表 ↔ 路由表 对账（对峙用）

- 库根：`/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理`
- 权威库真身：`kb/`（`kb/KB-ROOT.json`）
- 时间：2026-10-04 01:30 前后
- 口径：只读复核，零写库（未跑 `l8/workflow_check.py` / `projection_reconcile.py`，两者无干跑档会写盘）
- 本单只回答一件事：**registry（`skills.yaml` / `layers.yaml`）与 routes（`routes.yaml`）对不对得上**

---

## 一、四道闸门实测（附退出码）

| 闸门 | 命令 | 退出码 | 判定 |
|---|---|---|---|
| 登记表自检 | `kb/kbpy l7/scripts/skills_check.py` | **0** | 过 · 五类 1=0 2=0 3=0 4=0 5=0 |
| 层契约 | `kb/kbpy l7/scripts/layers_check.py` | **0** | 过 · 六类合计 0 · 8 层齐 |
| 四方对账（含 C7 层↔skill） | `kb/kbpy l7/scripts/skill_conformance.py` | **0** | 过 · 红 0 ｜ 黄 93 |
| 路由表对账 | `kb/kbpy l7/scripts/routes_reconcile.py <赢家表> --alias` | **1** | **不过 · 6 条**（详见 §3.6） |
| 路由表对账（按文档原文命令） | `kb/kbpy l7/scripts/routes_reconcile.py kb/l7/reports/<RUN>-routes-winners.json` | **2** | 环境错：赢家表不存在（库内**无**该文件） |
| 路由表对账（去掉 `--alias`） | 同上加 `_eval-kb-manage/blind_v2.winners.txt` | **1** | **65/65 全不一致 —— 假红，判据缺陷** |

`kb_check` 健康分 **79.1**（熔断线 60）：拉分的是孤岛率 0.94、E026 ×454、W020 ×2218，属条目内容维度，与本单主题无关。

---

## 二、确证的对不上（可直接对峙）

### R1 路由表对账这条闸门**用文档原文命令跑不起来**（缺输入硬拒）

- `kb-check` §1 ③ 写的命令：`kb/kbpy l7/scripts/routes_reconcile.py kb/l7/reports/<RUN>-routes-winners.json`
- 实测：`kb/l7/reports/` 与 `kb/l7/runs/` 下**不存在任何** `*-routes-winners.json`；全库 `find` 为空。
- 代码：`kb/l7/scripts/routes_reconcile.py:202-207` —— 缺文件即 `return 2`（拒绝报绿，这点做对了）。
- 结论：**闸门在，输入从来没人产出。** 它今天的"能跑"是借库外 5 天前的盲测快照（`_eval-kb-manage/blind_v2.winners.txt`，2026-09-29 19:58）。

### R2 同一命令**不加 `--alias` 会把 65 条全部判成不一致**（假红）

- 实测 `… blind_v2.winners.txt`（不带 `--alias`）：`逐条全轮命中：0/65`、`①=65`、退出码 1。
- 逐条形状：`A1：期望 brand-content-review-agent，实际 内容审查总控 / 内容审查总控 / 内容审查总控` —— 实际接走是对的，只是名字是中文装载目录名。
- 代码：`routes_reconcile.py:100-102` `canon()` 的 alias 折回由 `args.alias` 开关控制；不加就逐字比，英文 id ≠ 中文目录名 ⇒ 必然全红。
- 结论：**判据缺陷，非数据缺陷。** 谁按文档半句命令跑，谁就会拿到一份 65 条的红单。

### R3 `--alias` 折回表**硬编码 13 条**，且与 `routes.yaml` 是两份同源副本

- `routes_reconcile.py:44-58` `ALIAS` 13 条；`routes.yaml:177-190` `dir_name_map` 13 条。
- 逐条比对：**13/13 一致**（当前不漂），但**两张表各写一份**。
- 13 个中文装载目录实测**全部存在于** `~/.dsh/skills/`。
- 风险：新增任何中文名成员，两处**都不更新**时 `--alias` 也不会折回，该成员**永久假红**且无人被提醒。
- **违反本库自己的纪律**（`routes.yaml:11` 声称"`to`/`members` 每个 id 必须是 `skills.yaml` 里登记过的成员"，同库还写着"同一事实只写一处"）。

### R4 ★ `mutual_not_for` 声明了 **8 组**，**没有任何代码读它**（死条文）

- 实测：`grep -rn "mutual_not_for" --include=*.py kb/ tools/ ci/` → **0 命中**（全库，含 `_backups`）。
- `routes.yaml:140-165` 登记 8 组，其中第 1 组是本次盲测暴露的真歧义：
  - `routes.yaml:148` `pair: ["文案合规审查", "视频安全审查"]`，规则原文在 `:149-152`
- `routes_reconcile.py:266-271` **硬编码 7 对**，内容是**另外 7 组**：
  ```
  ("kb-pipeline","kb-l0-feishu") ("kb-l0-feishu","kb-pipeline")
  ("kb-l0-feishu","kb-review")   ("kb-pipeline","kb-review")
  ("kb-pipeline","kb-canonical-lookup") ("kb-pipeline","kb-p0-check") ("kb-pipeline","kb-recall")
  ```
- ⇒ **第 1 组（文案合规审查 ↔ 视频安全审查）从未被任何闸门核过**；反过来，就算把这行从表里删掉，闸门输出一模一样（0 条）。
- 脚本自己的文档却在骗人：`routes_reconcile.py:13` 写"④ 路由表自检：id 都在 skills.yaml 里、**互斥点名规则都成立**、两条链的入口 not_for 互相点名"。

### R5 ★ ④ 节"路由表自检 = 0 条"**推不出"路由表没问题"**（判据缺口）

- `routes_reconcile.py:222-237` ④ 节只核三类事：`routes[].to` 在登记表 / `routes[].not_for` 非空 / `chains` 的成员与入口在登记表。
- **它不核**：注册表里的成员**有没有路**。
- 实测：`routes.yaml` 只有 **11 条 routes / 10 个不同 `to`**；`skills.yaml` 里本项目 `status=生产` 有 **40 人**。
- 逐个定性结果 —— **既无 route 又无冻结用例的 17 人**：

| 成员 | 层主 | 有 route | 有用例 | 登记处 |
|---|---|---|---|---|
| `kb-ingest-extractor` | **是**（L1、L2） | 无 | 无 | `skills.yaml:834` |
| `kb-media-extractor` | **是**（L1） | 无 | 无 | `skills.yaml:850` |
| `kb-clause-extractor` | **是**（L3） | 无 | 无 | `skills.yaml:866` |
| `brand-product-fact-curator` | 自称 L3 | 无 | 无 | `skills.yaml:882` |
| `lark-base` / `lark-doc` / `lark-drive` / `lark-shared` / `lark-wiki` | — | 无 | 无 | 宿主通用 |
| `root-skills-*` ×7 / `蒸馏` | — | 无 | 无 | — |

- 这四个**层主**的零路由是可对峙点：`layers.yaml:154 / :201 / :238` 明确它们是层主，但 `routes.yaml` 全文 **0 次**提到它们（实测 `grep -c` 三次都是 0），冻结用例里也 **0 条**。
- 另有一批成员**只有用例、没有 intent 级 route**：`brand-review-decision-engine`、`brand-review-report-memory`、`brand-review-evaluation`、`brand-feishu-review-adapter`、`brand-image-safety-review`、`brand-video-safety-review`、`brand-text-compliance-review`、`brand-us-locale-cultural-review`、`brand-policy-source-curator`、`brand-review-intake-router`、`brand-product-claim-verifier`、`brand-ai-provenance-rights-review` —— 它们的路由正确性只能靠那份 **65 条冻结用例**背书。

### R6 注册表与路由表**没人校验的一致性**：层归属

- `skills.yaml:127` `kb-content-review` → `layer: L7`；但 `layers.yaml:539` L7 的 `skill: [kb-check]`，而 `kb-content-review` 在 `layers.yaml` 里**不是任何层的层主**。
- `skills.yaml:888` `brand-product-fact-curator` → `layer: "L3"`；`layers.yaml:238` L3 的层主是 `kb-clause-extractor`，该成员同样**不是层主**。
- `skills.yaml:840` `kb-ingest-extractor` → `layer: "L1/L2"`（合并写法），`layers.yaml` 拆成 L1、L2 两条（`:154`、`:201`）—— 值不相等，只有人眼看得出是同一件事。
- `skills.yaml:598` `kb-retriever` → `layer: "L0/L1"` 且 `status: 废弃`。
- 实测 `skills_check.py` **不核** `layer` 字段（`grep -n layer` 命中的 5 处全在打印/统计：`:912/:914/:1097/:1100/:1113`）；`layers_check.py` 只核 `layers.yaml` 里声明过的 skill；`skill_conformance.py` 的 C7 报红 0。
- ⇒ 这三个不一致**落在所有闸门的缝里**。

### R7 路由表自述的"现状"已过期

- `routes.yaml:52` 写：层前置「现状：**文字约束**，未落成代码级阻断（登记见 GAP-RO-5）」。
- 实际：`~/.dsh/AGENTS.md:158 / :160` 记明 2026-10-03 起 `--require-layer-preflight` 与 `--decision-owner` **都是代码级默认阻断**。
- ⇒ 注册表里这条状态是**过期描述**，谁照着它对峙会讲错版本。

### R8 `AGENTS.md` 的路由片段仍是**手抄版**（可复算的产物没接上）

- `kb/l7/scripts/route_snippet_gen.py` 的用途就是消除第二份事实（`:3-20`），自带 `--check` 漂移校验（`:25`）。
- 实测 `--check ~/.dsh/AGENTS.md` → **退出码 1**：`找不到生成标记（<!-- BEGIN route_snippet_gen … -->）—— 说明它还是手抄版，不是产物`。
- 且该脚本**不被任何闸门调用**（`grep` 只命中它自己的注释）。

---

## 三、终判不一致清单（`--alias` 口径，6 条）

命令：`kb/kbpy l7/scripts/routes_reconcile.py _eval-kb-manage/blind_v2.winners.txt --cases _eval-kb-manage/cases_v2.json --alias`
结果：`逐条全轮命中：109/115`、`①=6 ②=6 ④=0`、退出码 1。

| 用例 | 期望 | 实际（3 轮） | 定性 |
|---|---|---|---|
| I1 | AI溯源与权利审查 | 视频安全审查 ×3 | 用例歧义（`routes.yaml:239-243` 已登记 I1↔G3 近重复） |
| I2 | AI溯源与权利审查 | NONE / 图片安全审查 / NONE | 用例欠定义（`routes.yaml:253-254` 已登记） |
| I3 | AI溯源与权利审查 | NONE / **AI 溯源与权利审查** / NONE | **台账旧名**：带空格名只在 09-29 赢家表里（改名发生在 09-30） |
| I4 | AI溯源与权利审查 | **AI 溯源与权利审查** / NONE / NONE | 同上 |
| I5 | AI溯源与权利审查 | 图片安全审查 ×2 / CLARIFY | 用例歧义（`routes.yaml:247` 自认"这才是主因"） |
| `kb-manage-4` | kb-manage | kb-manage / kb-manage / **kb-pipeline** | **真·路由边界异议 · 要人裁**（见 §4） |

成员命中率：22/23 成员 15/15 轮；`kb-manage` 14/15；`AI溯源与权利审查` **0/15**。

---

## 四、要人裁的三件事（本单不裁）

1. **`知识库该更新了` 归谁**：`routes.yaml:65` `say[5]` 与 `skills.yaml`（kb-pipeline 的 `trigger_keywords`）都判给 **kb-pipeline**；但 `kb-manage` 的触发词含"该走哪个 skill / 谁负责"这类**问归属的元问题**，实测 kb-manage 4/5 轮胜。要么给 kb-manage 补 `not_for`，要么承认这是边缘用例。
2. **`文案合规审查` ↔ `视频安全审查` 的互斥点名**要不要补进 ④ 节判据（现在表里写了、码里没核，见 R4）。补 = 改判据；不补 = 表里那 10 行应标注"仅登记、不生效"。
3. **AI 溯源 0/15** 要不要动：`routes.yaml:248` 已明确"不再改用例、也不再调 description（避免过拟合 judge）"，但该成员当前 **0/15 轮命中、F1 曾 0.440 → v2 实验更差 0.222**，是唯一未过门槛的成员。

---

## 五、文档/注释与代码不一致（低风险，但会被拿去对峙翻车）

| 处 | 写的是 | 实际 |
|---|---|---|
| `routes_reconcile.py:13` | ④ 节会核"互斥点名规则都成立" | 互斥点名靠 `:266-271` 硬编码 7 对，**不读表**；表里第 1 组从未被核 |
| `routes.yaml:52` | 层前置是"文字约束" | 10-03 起已代码级默认阻断 |
| `routes.yaml:205-206` | "23 个成员中 22 个过门槛" | 与 `kb-manage/SKILL.md:142` 同口径；但该数是 09-29 快照，且 v2 实验后 AI 溯源 0.222 |
| `routes_reconcile.py:40` `SCORER` 常量 | `~/.dsh/skills/root-skills-eval/scripts/score-trigger-eval.py` | `:337-341` 里 F1 交叉核对实际**被跳过**，只打印一行备注 |
| `kb-check` §1 ③ 命令 | 用 `kb/l7/reports/<RUN>-routes-winners.json` | 不写 `--alias`；且该文件全库不存在 |

---

## 六、明确没问题的部分（别误伤）

- `routes[].to` 11 条**全在**登记表；`chains` 三个链的成员与入口**全在册**。
- `dir_name_map` 13 条 ↔ `skills.yaml` 的 `dir_name` **13/13 反查一致**；13 个中文目录**全部真装**。
- `layers.yaml` 8 层的 `skill:` 字段 **全部在登记表**（`skill_conformance.py` C7 红 0）。
- 09-29 之后**新增的 9 个成员**（`kb-check`/`kb-canonical-lookup`/`kb-l0-feishu`/`kb-manage`/`kb-p0-check`/`kb-pipeline`/`kb-recall`/`kb-repair`/`kb-review`）**全部已有 route** —— 注册表长、路由表没跟上这件事，在这批成员上**没有发生**。
- `skills.yaml` 的五类自检 0/0/0/0/0；副本一致、依赖、自测全过。

---

## 七、证据复现（逐条命令）

```bash
cd "/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理"

# R1 缺输入硬拒
kb/kbpy l7/scripts/routes_reconcile.py kb/l7/reports/X-routes-winners.json ; echo $?   # 2

# R2 假红 65 条
kb/kbpy l7/scripts/routes_reconcile.py _eval-kb-manage/blind_v2.winners.txt ; echo $?  # 1 · 0/65

# R4 死条文
grep -rn "mutual_not_for" --include=*.py kb/ tools/ ci/          # 0 命中
sed -n '266,271p' kb/l7/scripts/routes_reconcile.py              # 硬编码 7 对
sed -n '140,165p' kb/l7/registry/routes.yaml                     # 表里 8 组

# R5 层主零路由
grep -c "kb-ingest-extractor"  kb/l7/registry/routes.yaml        # 0
grep -c "kb-media-extractor"   kb/l7/registry/routes.yaml        # 0
grep -c "kb-clause-extractor"  kb/l7/registry/routes.yaml        # 0
grep -c "brand-product-fact-curator" kb/l7/registry/routes.yaml  # 0

# R6 层归属缝
sed -n '127p;840p;888p;598p' kb/l7/registry/skills.yaml
sed -n '238p;539p' kb/l7/registry/layers.yaml

# R8 手抄版
kb/kbpy l7/scripts/route_snippet_gen.py --check ~/.dsh/AGENTS.md ; echo $?  # 1
```

---

## 八、本单的边界（诚实声明）

- 本单是**静态契约核验 + 一份 09-29 运行时快照**的对账，**不含**"今天实际被谁接走"。要今天的数，得按 `kb-manage` 的触发电测**重新生成赢家表**再跑 R2 那条命令。
- 未跑 `l8/workflow_check.py`、`l8/projection_reconcile.py`（无干跑档、会写盘），未做信封闸门全量扫描。
- §2 全部结论均已逐条复算；§4 三项属判断，不是结论。
