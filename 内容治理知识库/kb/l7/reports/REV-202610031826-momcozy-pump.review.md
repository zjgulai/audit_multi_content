# 审查报告 · Momcozy 穿戴式吸奶器宣称文案（REV-202610031826-momcozy-pump）

**结论：`NEEDS_INPUT`（引擎 fail-closed 拒答，退出码 3）** —— 本次**没有**产出 PASS / REVIEW / BLOCK 三态结论。
拒答原因**不是**内容合规性判断，而是**供给链新鲜度前置未通过**。
下方「读通道证据」是**另行标注的旁证**，**不得**当作三态结论使用。

---

## 一、绑定字段

| 项 | 值 |
|---|---|
| `review_id` | `rv-20261003-184506` |
| `content_id` | `AUTO-7eb6b62e8c2b` |
| `content_version`（content hash，sha256） | `7eb6b62e8c2bb9005dff9a20fc093378a0ce4b8adb792b2f6132eb32098f3993` |
| 送审原文（逐字） | `Momcozy 穿戴式吸奶器，100% 安全无痛，医生推荐，FDA 认证，医院级。` |
| 判定主体 skill | `文案合规审查`（`--decision-owner`，mode = `declared`） |
| 引擎版本 / 规则版本 / 知识版本 | `kb_version = v0`；规则 1018 条候选 / 定稿 canonical 1365 条；**不产生 `release_id`**（版本纪律未破） |
| 层前置 BASE | `REV-202610031826-momcozy-pump`（L4 / L5 / L6 / L7 四个 RUN） |
| 出结论命令 | `kb/l7/review-engine/core/with_kb_evidence.py --require-layer-preflight <BASE> --decision-owner 文案合规审查` |

---

## 二、覆盖率与输入清单

| 项 | 值 |
|---|---|
| 语种 / 市场 | 中文文案（含英文术语 FDA）；美国市场口径 |
| 模态 | **纯文本**（单句宣称），无图片 / 视频 / 链接 |
| 渠道 | `未指定`（按自动化缺省补） |
| 产品线 | `未指定`（按自动化缺省补；本单未传 `--product-line`） |
| 送审版本 | `v1.0`（自动化缺省） |
| 输入权限状态 | 未登记（本单为直接粘贴文本，未走 `送审登记`） |

**四段溯源覆盖**：本次结论为拒答，故**不产出**风险条目四段溯源；下方旁证给出**完整四段**。

---

## 三、层前置（② 前置）实测：红 0

| 层 | RUN | 该层 skill（真加载过） | 落章 | 审计 |
|---|---|---|---|---|
| L4 | `REV-…-L4` | `kb-canonical-lookup` | `kb/l4/runs/…-L4-dryrun.json`（`skill=kb-canonical-lookup`） | ✅ 红 0 ｜ 🟡 E5 |
| L5 | `REV-…-L5` | `kb-p0-check` | `kb/l5/runs/…-L5-dryrun.json`（`skill=kb-p0-check`） | ✅ 红 0 ｜ 🟡 E5 |
| L6 | `REV-…-L6` | `kb-recall` | `kb/l6/runs/…-L6-dryrun.json`（`skill=kb-recall`） | ✅ 红 0 ｜ 🟡 E5 |
| L7 | `REV-…-L7` | `kb-check` | 跨层闸门，豁免层主核 | ✅ 红 0 ｜ 黄 0 |

`skill_invocation_audit.py` 四条全部 **红 0 / 退出码 0**；`skill_evidence = agent_reported`（**非** `registry_echo`）。
**🟡 E5 的含义必须写明**：四层落章**全部来自预演台账**（`dry_run=true` / `applied=false`），
本单的绿只证明「**逐层调用机制通了**」，**不构成**「这些层真落盘过」的证据 —— 本单**未落盘、是机制证据**。
L4/L5/L6 的三个 `l4_integrity` / `l5_integrity` / `l6_integrity` `verdict=FAIL` 项，逐条核对后**全部属已登记判据漂移**
（`l4-known-drift.yaml` / `l5-known-drift.yaml`）；**L6 的 `vector_traceability` FAIL 未登记**（`l6-known-drift.yaml` 不存在），
按「真红、待裁」上报（P0 混入 321 / 回指异常 392，读数来自 `kb/.work/l6_integrity.json`，`run_id=20261002-0006`）。

---

## 四、拒答载荷（引擎原文）

```
state   = NEEDS_INPUT
reason  = 供给链不新鲜
detail  = **跑层后仍超期 ⇒ 拒答（fail-closed）**：超期层 L0、L1、L2、L3、L4、L5、L6、L7
fails_closed = true ｜ issue_count = 0
next_owners  = ["内容治理负责人"]
```

**拒答判据**：`kb/l7/scripts/review_freshness_gate.py` → 读 `kb/l7/reports/daily-health-latest.json` 的 `stale_layers`，
非空即拒答（**不自己重算**，与 `freshness.py` 同一把尺子）。`stale_layers` 本次为 **8 层全超期**。

### 4.1 为什么自动跑层没救回来（一条实测链，不是推测）

1. 首次出结论时，引擎的自动跑层子进程**返回码 2**（`kb/l7/registry/freshness_autorun.ndjson`，18:40:50）。
   根因：`kb/.work/.kb.lock` 被**上一次超时的 review 调用**留下的**死进程锁**占着
   （`pid=71411 已不在，但没有宣布释放` → `lock.held_dead`）。**这不是数据损坏。**
2. 按库内规定顺序处置（**先判有没有写坏，再删锁**）：
   - `kb_pipeline.py --check` → **全过、硬问题：无、零写自证 ✅**（产出 4001 个文件 mtime 变化 0 个）；
   - 独立复核 5 个权威件 sha256 与会话内实测记录**逐字一致**：
     `kb/l3/candidates/rules.jsonl` `743dc623…eff840`、
     `kb/l4/registry/l4.json` `cf094acd…3982a88`、
     `kb/l5/p0_patterns.jsonl` `470e3fba…570ea8`、
     `kb/l6/registry/l6.json` `93b6c439…7227674`、
     `kb/l6/selftest.json` `b6bad9a8…d90cde`。
   - 确认干净后才删锁。
3. 删锁后重跑，自动跑层**这次真的跑起来了**：`returncode=0`、`ok=true`、耗时 52.3 秒
   （`run_id=20261003-184404-autorun`，跑 L4→L5→L6）。
4. **但 `after_stale_layers` 与 `before_stale_layers` 完全相同**（都 8 层）⇒ 仍超期 ⇒ 仍拒答。

### 4.2 根因（结构性，需人裁）

自动跑层**被代码层禁止写数据**：`review_freshness_gate.py` 的「批30 封顶令」明写
**不许加 `--apply`、不许带 `--write-gate`**。而它要清除的「超期」，判据是
「最近一次**成功 RUN** 距今 > 24 小时」—— **只有真落盘才会刷新**。
⇒ **「自动跑层会跑」不蕴含「自动跑层能消红」**：跑的是预演档，一个字节都不写，超期当然照旧。
本单首次核到的距今是 **29.9 小时**，超期不是今天这一单造成的，而是**上游 L0 侧约 30 小时没有成功同步**。

---

## 五、旁证（**读通道**，非三态结论，不得当 PASS/BLOCK 依据）

> 以下由**只读通道**产出，不经 `review.py` 落章，**不构成本单的三态结论**。
> `kb/l5/matcher.py` 是确定性匹配器，它给的是**优先级分流**，不是放行结论。

### 5.1 P0 匹配（`kb/l5/matcher.py --text "<原文>"`）

结论行 **`BLOCK`**，**3 条 P0 模式命中**：

| 模式 | `pattern_id` | 命中的表达 |
|---|---|---|
| **H04** 无据的医生/专家推荐背书 | `p-521d9d1502ee0bfa` | `医生推荐` |
| **H06** FDA 表述错误 | `p-485c67cc9af960bf` | `FDA 认证` |
| **H07** 疼痛功效承诺 | `p-964b3c2e22b48ade` | `无痛` |

**未命中 ≠ 合规**，本句还有两处**不在这 3 条 P0 里、但在规则层有明确条款**：

| 原文片段 | 条款号 | `p_level` | 规则要点（L3） |
|---|---|---|---|
| `100% 安全` | （P0 H05 的英文侧 `100% safe` 命中；中文 `100% 安全` 本次**未触发** H05 正则） | P0（英文侧） | 虚假安全承诺须删 |
| `医院级` | **W-1.19** | **P1** | 等级背书用语需核实是否有对应认证；触发词含 `hospital grade` / `医疗级` / `医用级` |
| `医院级` | **W-1.11** | P2 | 命中「hospital grade」判违规；**`hospital/medical grade 需认证依据，否则删除`** |
| `医院级` | **W-2.4** | P1 | 原表述 `Hospital-Grade` → 修订为 `Without certification, drop 'hospital grade'; state specs (e.g. double-motor -295 mmHg).` |

### 5.2 四段溯源（缺一段不许出结论 —— 旁证部分**四段齐**）

**① 条款号（L4）**：`W-1.11` / `W-1.19` / `W-2.4`（另有 P0 侧 `H04`/`H05`/`H06`/`H07`）
**② 规则与命中片段（L3）**：
- `W-1.19`：`边界：等级背书用语（需核实是否有对应认证）；触发词：military grade, medical grade silicone, hospital grade, 医疗级, 医用级, 军用级`
- `W-1.11`：`规则码 M05：命中「hospital grade…」判定为违规；处理：「hospital grade,hospital-grade」→ 删除…▸ hospital/medical grade 需认证依据，否则删除`
- `W-2.4`：`原表述：Hospital-Grade Wearable Power / Medical Grade Suction；修订为：Without certification, drop 'hospital grade'; state specs…`

**③ 单元与锚点 `anchor` / `source_sha256`（L2/L1）**：

| 条款号 | `unit_id` | `anchor` | `source_sha256` |
|---|---|---|---|
| W-1.11 | `0e8a16219d4ff3533a03` | `#广告文案明细/recvuJYdObBgjg/命中片段` | `1ca01a6690922a697e9d428439674863df67709688a6b32fe846705603f5e011` |
| W-1.19 | `1d44547abcccad250986` | `#品线内容边界规则库/recvuJP2jyPiol/边界内容` | `da6b33667bbd74317bc3f204a4a19914a27e9785ff62ea83740809c580375bb5` |
| W-2.4 | `d65b13e0301fa0fbaf60` | `#风险文案改写建议库/recvuNn6ejv2Ik/风险原句示例` | `04e5e32f9b967db6d08dcf1fa7966a4ab9d213e47883621498926a81202699b7` |
| H04 | — | `#广告文案明细/recvuJYdObV6eR/命中片段` | `6059659ad3f649c3ac1ff6ca602fdcd0368094a9d9490fa5dca0319872677af0` |
| H06 | — | `#品线内容边界规则库/recvuJP1LVW6E0/边界内容` | `2e8bb36d6edf7c4971132b69ff6d39819a5a0e0e8043e9001e096be1bc2a02d6` |
| H07 | — | `#广告文案明细/recvuJYdOb1u94/命中片段` | `1e3bd4c1ca097ee1b7f0011014ff91c1012b258c1e691525e0df454790b4c011` |

**④ 逐字原文 + L0 直链 + sha 核对**（L0 `.json` 的 `entry_url`，就是飞书侧那条原始记录）：

- **H06 最要命的一条**：L0 逐字原文写的是
  **「FDA 表述错误（吸奶器为 cleared/registered，非 approved/certified）」**，
  且**豁免词**是 `FDA cleared, FDA-cleared, FDA registered, FDA 注册`，
  **检测关键词**才是 `FDA approved, FDA certified, FDA 认证, FDA 批准, FDA 通过`。
  ⇒ **`FDA 认证` 正落在违规侧**；按库内口径，吸奶器是 **cleared/registered**，**不是** approved/certified。
  🔗 <https://momcozy-in.feishu.cn/base/Lk3Qb8y2QaVyZns6gprcVNE9nA0?table=tblD1MiUK1v5fdjD&record=recvuJP1LVW6E0>
- **H04**：L0「命中原因」逐字 = `H04 无据的医生/专家推荐背书；…`；
  「修改建议」= `删除医生/专家/IBCLC/OB-GYN 推荐背书；免费 IBCLC 服务可单独陈述但不得与“推荐”绑定`
  🔗 <https://momcozy-in.feishu.cn/base/Lk3Qb8y2QaVyZns6gprcVNE9nA0?table=tblcbk4XiW6471YN&record=recvuJYdObV6eR>
- **H05**：L0「修改建议」= `删除 safest/100% safe/zero risk/perfect 等虚假安全承诺，以及 fits all breast shapes/one size fits all/一定不损伤/适合所有胸型等绝对化适配承诺`
  🔗 <https://momcozy-in.feishu.cn/base/Lk3Qb8y2QaVyZns6gprcVNE9nA0?table=tblcbk4XiW6471YN&record=recvuJYdOb1B8v>
- **H07**：L0「命中原因」= `…H07 疼痛功效承诺（pain-free/no pain/without pain/pain relief/less pain/缓解疼痛等；吸奶疼痛因人而异，只可讲 comfort/gentle 舒适与缓解胀满不适 discomfort）`
  🔗 <https://momcozy-in.feishu.cn/base/Lk3Qb8y2QaVyZns6gprcVNE9nA0?table=tblcbk4XiW6471YN&record=recvuJYdOb1u94>

**sha 的措辞红线（照库内规定）**：上列 `source_sha256` 只能写
**「与 L0 记录值比对一致」**，**不许**写「重算通过」—— L0 的 sha 输入是 `record_fields` 这个字段 blob，
本地 L0 件**不含**该 blob（本次实测 `sha256_input` / `sha256` / `sha256_state` **三字段均为 `None`**，
与「本地结构上不可能重算」一致）；要真核对只能点上面的飞书直链。

---

## 六、决策轨迹（decision trace）

1. 收素材（纯文本一句）→ 判专项归属 → **`文案合规审查`**（纯文本，不带视频/图片；与 `视频安全审查` 的分界按 `routes.yaml` 的 `mutual_not_for`：「脱离视频的纯文本」归文案）。
2. 跑层前置 L4 → L5 → L6（每层一 RUN、每层切 subagent 用 skill 工具加载该层 skill）＋ L7 单独跑。
3. 四条 `skill_invocation_audit` → 红 0 → 放行出结论。
4. 出结论（`with_kb_evidence.py`）→ 新鲜度前置 `review_freshness_gate` **拒答** → `NEEDS_INPUT` / 退出码 3。
5. 处置死锁 → 复跑 → 自动跑层 rc=0 但 `after_stale_layers` 未变 → **仍拒答**。
6. 飞书发布：**跳过**（结论是 `NEEDS_INPUT`，没有三态结论可发）—— 未发云文档、未写表行。

---

## 七、校准状态与版本门（calibration / version gate）

| 字段 | 值 |
|---|---|
| `confidence` | `null`（拒答，无置信度） |
| 校准状态 | **未校准** —— 本单没有金标对照，拒答不是判定准确率的样本 |
| 版本门 | **未通过**：供给链超期 ⇒ 依 `review_freshness_gate` 不得输出 PASS/BLOCK |
| 人工复核 | 未做（`canonical` 为 `machine-promoted`，只可当「已编号的定稿快照」，**不可当已发布版本**） |
| 已知未修缺口 | `kb_api.py` 只有层前置闸门、**无 `decision_owner` 闸门**（`grep -n decision_owner kb_api.py` 0 命中）⇒ bot 侧结论不得当 PASS 依据 |

---

## 八、原始模型结果与人工结论（并存，不许只留一份）

- **原始引擎结果**：`NEEDS_INPUT`（拒答），`issue_count = 0`，`fails_closed = true` —— **原样保留**。
- **人工结论**：**尚未作出**。本报告不含人工改判；
  若人工据第五节旁证另作判断，须**另起一份**并同时保留本条引擎原始结果。
- **人工反馈 → 候选条目**：需由 owner 接受后才成立，本次**未提交**任何候选条目。
