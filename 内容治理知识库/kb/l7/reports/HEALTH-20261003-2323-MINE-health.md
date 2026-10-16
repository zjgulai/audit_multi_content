# kb-check 体检档报告 · HEALTH-20261003-2323-MINE

- 库根：`/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理`（cwd = 库根）
- 权威库：`kb/`（l0…l8）
- 跑法：`kb-check` skill §1 体检档（6 道闸门，逐条记退出码）
- 时间：2026-10-03 23:18–23:23 CST
- 档位声明：**体检档**（不是评审驱动循环的 L7 档）；本档按 §4 产出本报告

---

## 1. 体检表

| # | 闸门 | 退出码 | 结论 | 证据 |
|---|---|---|---|---|
| ① | `l7/scripts/skills_check.py` | **0** | **过** | 五类问题 1=0 2=0 3=0 4=0 5=0；「本项目要用 40 个 / 已装 40 / 还差 0」。未登记 selftest 62 条（脚本自注「不算错误」）。3 跳过（12 个只参考条目未装，不做副本比对）；3 备注（lark-base 本地 1.2.23 > CLI 1.2.22，属超前不告警） |
| ② | `l7/scripts/layers_check.py` | **0** | **过** | 层数 8（L0…L7 无重复）；必填 12 字段齐 + `envelope` 合法 + `python=${KB_PYTHON}`；引擎路径存在性 0；cwd/解释器约定 0；DAG 无环、扇出断言过；干跑档声明 0；**无干跑档清单 0 条**。六类问题合计 0 |
| ③ | `l7/scripts/routes_reconcile.py` | **1** | **过（带口径附注）** | 用 2026-09-29 赢家表 `_eval-kb-manage/blind_v2.winners.txt` + `--cases cases_v2.json` + **`--alias`**：逐条全轮命中 **109/115 = 94.8%** ≥ 门槛 0.90；四节问题 ①=6 ②（同上）**④=0**。不一致仅 6 条：`NONE`×6、`I5`（期望 AI溯源与权利审查，实际 图片安全审查×2 + CLARIFY）、`kb-manage-4`（第三轮被 kb-pipeline 接走） |
| ④ | `l8/workflow_check.py` | **1** | **真红 2 条**，但两条均判为 **合法变红（基线漂移）** | 9 段中 7 段 PASS（①④⑤⑥⑦⑧⑨）；红：② 权威库 l0~l6 未被改动、③ 前序产物哈希（45 项）。裁决 `FAIL`。产物 `kb/l8/workflow_check_HEALTH-20261003-2323-MINE.json` |
| ⑤a | `tools/envelope_gate.py` | **0** | **过** | 1817 个 `.py/.txt/.md`，信封态 **0**，读不到 0；两读者（Electron-node vs PATH-node）交叉一致；结论「活路径上没有信封」 |
| ⑤b | `l8/envelope_census.py` | **0** | **过** | 扫 8688 个 `.md`，其中 1079 个信封态，**全部已分类**：569 刻意归档（`l8/_archive/enveloped-20260923-1520/`）+ 510 可再生产物（`.work/hostlib.bak-20260928-152220/`）。结论 `OK` |
| ⑥ | `l8/projection_reconcile.py` | **1** | **真红 3 条（需修）** | 3/6 通过：R3_id_set ✅ R5_manifest_bytes ✅ R6_tier_dir ✅；红：**R1** 源文件 rules 在视图生成后变过（`f27a14091b2bd782… → 743dc62398311b02…`）、**R2** 509 条条目权威规则已变、**R4** 2036 处治理字段未传导（owner / half_life_days / valid_until / effective_from 各 509） |

### ③ 的口径坑（实测，必须先知道）

同一份赢家表，**不带 `--alias` 会出 66 条假红**：13 个 `brand-*` 成员全部 0/5，因为赢家表里写的是**中文装载目录名**（如 `美国本地化审查`），而路由表里写的是 registry id（`brand-us-locale-cultural-review`）。带 `--alias` 折回后 109/115。**判定 ③ 必须带 `--alias`，否则把口径差报成路由错。**

### ⑤a / ⑤b 数字不冲突（已核）

⑤a 报 0 个信封、⑤b 报 1079 个，看似矛盾，实为**两个闸门范围不同且都是设计如此**：`tools/envelope_gate.py` 的 `SKIP_DIR_NAMES` 含 `_archive`/`_backups` 等，`SKIP_PREFIXES` 含 `hostlib`；而 ⑤b 的 1079 个正好**全部落在** `l8/_archive/…`（569）与 `.work/hostlib.bak-…`（510）这两个被跳过的桶里。⑤a 自己印的是「**活路径**上没有信封」。两者一致，不构成矛盾。

### ④ 的两条红为什么判「合法变红」（§2 / §3 第 2 类）

| 红项 | 判据 | 证据 |
|---|---|---|
| ② `l3_base1018_matches_L6` | 现 `kb/l3/candidates/rules.jsonl` 前 1018 行 sha vs `kb/.work/l6_integrity.json` 冻结值 | l6 基线记 `lines:2036 / max_mtime 2026-10-02 00:07:19`；**文件实际 mtime 2026-10-02 22:45**，即文件在基线之后被重写 |
| ② `l3_whole1527_matches_L4` | 现文件 sha vs `kb/l4/runs/20260923-1445.json` 里 `aa83d1f9…`（Sep 23 建库记录） | 基线是 **Sep 23**，文件是 **Oct 2**；且 `kb/l3/history/` 有**明文的收敛事件**：`rules-pre-converge-20260924-1230.jsonl` **1527 行** + `rules-superseded-20260924-1230.jsonl` **1018 行**，1527 = 509（现存活规则）+ 1018。检查器里的 `1527` 常量 = 收敛前长度，是历史常量 |
| ② l0/l1/l2 | 三棵树 sha vs L5 冻结基线 | **三条全部 `match_L5_baseline: true`**（l0 4006 / l1 3151 / l2 886 个文件） |
| ③ 45 项哈希 | 现文件 sha vs Sep 23 四个 run 记录的 `artifacts[].sha256` | 20 项不符，**每一项 mtime 都晚于其基线记录**：基线 run 为 Sep 23，文件为 Sep 29–Oct 3（例：`l4/registry/l4.json` Oct 3 21:18、`l6/index/l6.jsonl` Oct 2 22:47、`l7/…/review.py` Oct 3 12:44） |

辅助证据：L3 侧有 **12 条 `applied: true` 的 run 记录**（2026-10-01/02，`rules=509`、`accounted unaccounted=0`、5 项 checks 全「通过」，`skill: kb-clause-extractor`）。

⇒ 两条红都是**「库合法重建过、检查器比的是 Sep 23 / Oct 2 00:13 的旧基线」**，属 §3 第 2 类，不是数据坏了。

---

## 2. 失败项清单（对象 + 原因码 + 要人做什么 + 复开条件）

| # | 对象 | 原因码 | 要人做什么 | 复开条件 |
|---|---|---|---|---|
| F1 | `kb/view/` 投影整体（R1/R2/R4） | **投影过期 + 治理字段未传导**（⑥） | 重跑 `kb/.work/gen-host-library.py` 到 staging 后**回填**；R4 需确认 4 个字段的传导口径 | `projection_reconcile.py` 回到 6/6、退出码 0 |
| F2 | ④ 基线族（`kb/.work/l5_integrity.json`、`kb/.work/l6_integrity.json`、`kb/l4,5,6,7/runs/2026092*`） | **冻结基线过期**（Sep 23 / Oct 2 00:13） | 决定是「接受新基线」还是「回滚到基线」；接受则刷新基线记录 | ④ ②③ 两段转绿，或明确登记「基线漂移、非缺陷」并落进验收口径 |
| F3 | `kb/l3/candidates/rules.jsonl` **2036 行 → 1018 行**（Oct 2 00:13 → 22:45） | **未判定**（见 §3） | 人判：属不属合法收敛 | 找到对应 run 记录或权威说明 |
| F4 | ③ 赢家表 | **输入陈旧 + 口径未锁** | 用今天的数据按 kb-manage 触发电测**重新生成赢家表**；跑 ③ 时**必须带 `--alias`** | 有当日赢家表，且 ③ 在 `--alias` 下仍为 0 不一致 |
| F5 | 装载位 509 条中 **453 条 frontmatter 完整、56 条不完整** | **观察项**（非闸门红：E001/E046 均为 null，④⑤两段 PASS） | 决定是否接纳这 56 条 | 明确口径后补 `_meta` 或降级归类 |

---

## 3. 未判定项（§5：宁可标未判定，不猜）

- **F3（L3 文件 2036→1018 行）**：我能证的是「文件在 l6 基线之后被重写过」，**证不了**这次变化是否合法收敛。已查到的 L3 run 记录（10-01/10-02 共 12 条）**都记 `rules=509`**，没有任何一条记 `2036` 或说明这次减半。**不下结论。**
- **R4 的根因**：⑥ 给的修法是「确认投影生成器是否从规则行读这 4 个字段（F8）」。**合理推测**：生成器**读了**——`grep` 实测 `owner` 29 次、`half_life_days` 15 次、`valid_until` 19 次、`effective_from` 8 次。所以 R4 更可能是**同一次视图过期**的连带结果，而不是生成器缺字段。**推翻条件**：重跑生成器后 R4 仍在 2036 处。（此条是推测，未按结论采信。）

---

## 4. 并发写者告警（本次体检的独立发现）

跑体检时**另有 4+ 个会话在并发跑同一套 kb-check**。以下是从 `ps` 快照读到的**非本会话**命令行（我全程只跑过 `skills_check` / `layers_check` / `routes_reconcile` / `envelope_gate` / `envelope_census` / `projection_reconcile` / `workflow_check`，且只用过 `HEALTH-20261003-2323-MINE` 这一个 RUN id）：

```
RUN=HEALTH-20261003-2321-C ...          ← 非本会话
RUN=HEALTH-20261003-CHK2327 ...         ← 非本会话
RUN="HEALTH-$(date +%Y%m%d-%H%M%S)" ... ← 非本会话
KBROOT="…" ; cd "$KBROOT" || exit 9; …  ← 非本会话
sh kb/kbpy l8/workflow_check.py HEALTH-2026…   ← 非本会话，正在跑 ④
sh kb/kbpy l7/scripts/daily_health.py --no-gates … ← 非本会话
```

- `kb/.work/` 近 30 分钟持续被写：`l5_integrity.json` 23:17、`l5_integrity.json` 又于 23:18 被 l5_gate 刷新、`publish.log` 23:14（1.8 MB）。**⇒ 命中 skill §5 停止条件第 2 条。**
- 另有一条**评审循环**在跑：`REVIEW-20261003-2311-吸奶器静音续航-L4/L5/L6/L7`（23:12–23:14），`kb/.work/.review-base.txt` = `REVIEW-20261003-2233-吸奶器静音续航`。
- **无 `.kb.lock`**（`kb/.work/.kb.lock` 不存在），故未按陈旧锁处置，**没有删任何锁**。
- 已存在一份别人的独立核验：`_eval-kb-check-独立核验-20261003/kb-check-独立核验报告-20261003.md`（23:13）。

**关于 ④ 的处置**：④ 是体检档里唯一写盘闸门（无干跑档）。我**先核了它写哪儿**再决定跑：`SANDBOX_BASE=/tmp/l8-wfcheck`，且 `wfcheck-{RUN}` / `ingest-{RUN}` / `ingest_probe_{RUN}.mjs` / `workflow_check_{RUN}.json` **全部按 RUN id 分槽**，ingest 探针写的是 `/tmp` 沙箱、**不碰 `kb/l0…l7`**。⇒ 与并发会话不撞车、不动共享状态，故用唯一 RUN id 跑完并落自己的产物。**本次体检没有写 `kb/l0…l7` 任何数据。**

---

## 5. 结论

- **6 道闸门：① ② ③ ⑤a ⑤b 过；④ 红 2 条（合法变红/基线漂移，非缺陷）；⑥ 红 3 条（真坏，需回填）。**
- **最该动的只有一件**：**回填 `kb/view/` 投影**（F1）。⑥ 的失败是**派生视图停在 2026-09-29**（`kb/view/_meta/derivation.json` 的 `generated_at: 2026-09-29`）而权威库在 10-02/10-03 重建过——而宿主 `kb_*` 工具读的正是这个视图，**它的新鲜度直接决定检索/体检看到的是不是旧库**。
- **不许当结论的两条**：④ 的两条红**不是**数据缺陷（是基线过期）；③ 的 66 条**不是**路由错（是不带 `--alias` 的口径差）。
- **留在人手上的**：F3（L3 减半，未判定）、F2（基线接受还是回滚）、F4（重出当日赢家表）。

---

生成：`kb-check` skill 体检档 · RUN `HEALTH-20261003-2323-MINE` · 2026-10-03 23:23 CST
产物：`kb/l8/workflow_check_HEALTH-20261003-2323-MINE.json`、本文件
