# CHK-20261004-1216-REG-ROUTES 体检表（重点：registry ⇄ routes）

- **库根**：`/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理`（含 `kb/KB-ROOT.json`）
- **体检时刻**：2026-10-04 12:07–12:11（**快照读数**，本库存在并发写入者，见 §四）
- **档位**：kb-check **体检档**（六道闸门一次性跑完）
- **预检查**：`python3 .dsh/skills/kb-check/scripts/preflight.py` → exit 0「前置齐，可开跑闸门」；唯一缺项：**赢家表输入无**（预设门③ exit 2）
- **纪律声明**：本次**只读**，未改任何数据；唯一未跑的闸门是 ④（原因见 §一 ④）

---

## 一、体检表（六道）

| # | 闸门 | 命令 | 退出码 | 结论 | 证据 |
|---|---|---|---|---|---|
| ① | 登记表自检 | `sh kb/kbpy l7/scripts/skills_check.py` | **0** | **过** | 五类问题 `1=0 2=0 3=0 4=0 5=0 ｜合计 0`；本项目要用 40（生产 40）/ 已装 40 / 还差 0；装载位 `~/.dsh/skills` 扫到 59 个目录；另「未登记 selftest」62 条（**不算错误**，单独归类） |
| ② | 层契约 | `sh kb/kbpy l7/scripts/layers_check.py` | **0** | **过** | 层数 8（L0…L7 齐全）；六类问题 `1=0 2=0 3=0 4=0 5=0 6=0 ｜合计 0`；DAG 非线形：`L2←L1、L0`／`L3←L0、L2`／`L4←L2、L3`／`L5←L0、L2、L3`／`L6←L0、L2、L3`／`L7←L0、L3、L4、L5、L6` |
| ③ | 路由表对账 | `sh kb/kbpy l7/scripts/routes_reconcile.py <winners>` | **2**（无输入）／**1**（喂历史赢家表） | **未取得当日结论**（缺输入，非"全不一致"） | 无参数：`error: the following arguments are required: winners`；`kb/l7/reports/` 下 `*routes-winners*` **0 个**（实测 `grep -i winner` exit 1）。喂历史赢家表 `_eval-kb-manage/blind_after_r4.winners.txt`（115 行 / 2026-09-29 19:32）：`--alias` → exit 1，`①=5 ②=5 ④=0`，逐条全轮命中 `60/65`；`strict` → exit 1，`①=65 ④=0`（strict 与 alias 口径不同，**不是数据缺陷**） |
| ④ | 链路收口 | `sh kb/kbpy l8/workflow_check.py <RUN>` | **未跑** | **未跑（主动停手）** | 该脚本**无干跑档**且写 `kb/l8/workflow_check_<RUN>.json`（另建 ingest 探针）；实测同一时刻**已有另一会话在跑它**（`ps` → `kb/l8/workflow_check.py CHK-20261004-1215-3GATES`，已运行 41 s）。按 kb-check §6 ALWAYS「发现 `.work` 近 30 分钟大量写入 → 先确认是否有另一批在跑，别按删锁处置」，本轮不并发写同一目录。库内既有登记：`kb/l7/registry/workflow-check-known-drift.yaml`（2026-10-04 11:37 更新）记 ②③ 为**判据过期非数据坏**，2026-10-04 11:35:30 第 7 次独立复现「②③ FAIL 一字未变、其余 7 段全 PASS」 |
| ⑤a | 信封闸门（`.py/.txt/.md`） | `python3 tools/envelope_gate.py` | **0** | **过** | 首次扫描 1989 个文件 `正常 1989 ｜信封态 0 ｜读不到 0`；复跑 1993 个（期间有并发写入）仍 `信封态 0`；两读者交叉核对**一致**（Python `getsize` vs node `statSync`） |
| ⑤b | 信封普查（库自带，只扫 `.md`） | `sh kb/kbpy l8/envelope_census.py` | **0 / 1 / 0（三次）** | **过，但判据不稳定（flaky）** | 12:0x 读数：扫 10398 个 `.md`，**1079 个** node 侧读不到（差值 4096），全部**已分类**（刻意归档 569 / 可再生备份 510）⇒ `OK` exit 0。12:15 复跑 ⇒ **exit 1**：`❌ 必须为 0 活路径 1 个 … 例：l7/skills/视频安全审查/SKILL.md`。12:17 再跑 ⇒ **exit 0**。核对被判红那个文件：`kb/l7/skills/视频安全审查/SKILL.md` python `getsize` 6586 = node `statSync` 6586，mtime 仍是 **Oct 3 12:51**（体检期间未被改）。⇒ **同一文件集三次读数 0/1/0，不可复现**（详见 §五） |
| ⑥ | 投影一致性 | `sh kb/kbpy l8/projection_reconcile.py` | **1** | **真坏**（非判据缺陷；无干跑档，确认只读后跑） | `3/6 项通过，漂移项 3`：`❌R1_source_sha256`（源文件 `rules` 在视图生成后变过：`f27a1409…→743dc623…`）、`❌R2_entry_fingerprint`（509 条条目权威规则已变）、`❌R4_governance_passthrough`（**2036 处**治理字段未传导：`owner/half_life_days/valid_until/effective_from` 各 509）；✅R3/R5/R6。修法（脚本自述）：重跑 `kb/.work/gen-host-library.py` 到 staging 后回填 |

**结论口径**（kb-check §4 四种）：过 = ①②⑤a⑤b；真坏 = ⑥；未取得 = ③；未跑 = ④（并发停手，非缺陷也非通过）。

---

## 二、registry ⇄ routes 对账（本次重点，逐条给原始证据 + 行号）

### A. 对得上的部分（先说结论，避免误伤）

对账脚本：`_chk-run-CHK-20261004-1216-REG-ROUTES/04-static-crosscheck.py`（本次只读脚本，读 `kb/l7/registry/{skills,routes,layers}.yaml`）
原始读数全部落在 `_chk-run-CHK-20261004-1216-REG-ROUTES/`（`00-` 预检查 / `01-` 门① / `02-` 门② / `03a-c` 门③ / `05-` 静态对账 / `06-` 门⑥ / `07a-b` 门⑤ / `09-` 三表比对 / `11-` 撞平与安装核对 / `12-` 并发进程快照，各自带同名 `.exit`）。

| 检查项 | 结果 | 证据 |
|---|---|---|
| `routes[].to`（11 条）→ 是否都在 `skills.yaml` | **11/11 OK** | `routes.yaml:62-136`（每条 `to:`）对照 `skills.yaml` 顶层 `skills:` 71 个 id |
| `chains[].entry` + `chains[].members`（3 链 / 16 个引用）→ 登记表 | **16/16 OK** | `routes.yaml:30-58` |
| `frozen_expectation.dir_name_map` 的 13 个 key → 登记表 | **13/13 OK** | `routes.yaml:177-190` |
| `dir_name_map` 的 13 个**值** → `~/.dsh/skills/` 真实目录 | **13/13 命中** | 例：`brand-video-safety-review → 视频安全审查`、`brand-ai-provenance-rights-review → AI溯源与权利审查` |
| `layers.yaml` 各层 `skill:` → 登记表 | **9/9 OK** | `layers.yaml:109,154,201,238,294,406,452,539` |
| 门③ 的 `④ 路由表自检`（喂历史赢家表） | **0 条问题** | `kb/l7/scripts/routes_reconcile.py` 输出 `④ 路由表自检 --- 0 条` |

⇒ **静态 id 层面，routes 与 registry「登记表」是对得上的。** 用户前提里"对不上"的部分，不在这层。

### B. 对不上的部分（按可对峙强度排序）

#### B1 ★ 层前置审计的层数：3 vs 4 —— 三处口径，两处说 4、一处说 3【确定不一致】

- `kb/l7/registry/routes.yaml:50-51`：
  > `50: 逐层一 RUN：`<BASE>-L4 / -L5 / -L6 / -L7`；出报告前`
  > `51: `skill_invocation_audit.py --run <BASE>-L{4,5,6}` 必须**红 0**。`
  **同一段内自相矛盾**：50 行把 `-L7` 列为要跑的 RUN，51 行却把 L7 排除在必须红 0 之外。
- `kb/l7/registry/report-output-contract.yaml:364-366`：
  > `364: evidence_gate: "出结论/出报告之前，skill_invocation_audit.py --run <BASE>-L{4,5,6,7} 必须红 0 / 退出码 0；`
  > `365:   **2026-10-03 起 L7 也在闸门内**（原为 L{4,5,6}）；…`
- `kb/l7/registry/report-output-contract.yaml:789`：`- "四条 skill_invocation_audit 红 0（E1/E2 不出现；2026-10-03 起含 <BASE>-L7）"`
- **代码级**：`kb/l7/review-engine/core/with_kb_evidence.py:307` → `LAYER_PREFLIGHT_LAYERS = ("L4", "L5", "L6", "L7")`

⇒ 契约表（同一天写明"原为 L{4,5,6}"）与引擎代码都是 **4 层**，只有 `routes.yaml:51` 停在 3 层。**这是一处确定的过期未同步。**

#### B2 ★ `mutual_not_for` 声明"对账器会核"，实际**没有任何代码读它**【确定：声明失真 + 检查缺项】

- `kb/l7/registry/routes.yaml:138`（该段表头）＋ `:140`（段名）：
  > `138: # ─────────────────────────────────────────────── 互斥点名（硬约束，对账器会核）`
  > `140: mutual_not_for:`
- 实际对账器 `kb/l7/scripts/routes_reconcile.py:327-332` 用的是**硬编码的 7 个元组**，不读 yaml：
  > `327:     checks = [`
  > `328:         ("kb-pipeline", "kb-l0-feishu"), ("kb-l0-feishu", "kb-pipeline"),`
  > `329:         ("kb-l0-feishu", "kb-review"), ("kb-pipeline", "kb-review"),`
  > `330:         ("kb-pipeline", "kb-canonical-lookup"), ("kb-pipeline", "kb-p0-check"),`
  > `331:         ("kb-pipeline", "kb-recall"),`
  > `332:     ]`
- 且正文只加载**3 个** skill 的 SKILL.md，其余静默 `continue`（`routes_reconcile.py:300-315`，白名单在 `:305`）：
  > `305:         if not src or sid not in ("kb-pipeline", "kb-l0-feishu", "kb-review"):`
  > `306:             continue`
  > `335-336:  body = body_of(a) / if not body: continue`（跳过后**不报任何东西**）
- 全仓实测：`grep -rn "mutual_not_for" --include=*.py .` → **0 命中**（唯一命中在另一个会话的临时脚本 `_chk-run-CHK-20261004-1130-REGISTRY-ROUTES/10-crosscheck.py`，非库内代码）。

⇒ 结论：`routes.yaml:140-152` 声明的**第 1 对**（`["文案合规审查","视频安全审查"]`，行 148）**从未被任何检查覆盖**；另 6 对（行 154-165）与被硬编码的 7 个方向**逐条对得上**（6 对应 7 个方向，含 `kb-l0-feishu→kb-pipeline` 的反向）。⇒ 这不是"检查没做"，是"**表在说假话**"：台词是"表驱动、对账器会核"，实际是"脚本书里另抄了一份、且第 1 对漏抄"。
**补一句公道话**：这一对**正文里其实成立** —— `~/.dsh/skills/文案合规审查/SKILL.md:4` 点名了「视频画面（走 视频安全审查）」，`~/.dsh/skills/视频安全审查/SKILL.md:4` 点名了「纯文字文案 / 广告用语 / listing、PDP 文案（走 文案合规审查）」。**缺的是机器检查，不是内容。**

#### B3 ★ 门③ 的静态自检被绑在"运行时赢家表"之后 —— 今天**拿不到官方结论**【确定：结构性】

- `kb/l7/scripts/routes_reconcile.py:262-276`：赢家表不存在 → 打印"环境错：赢家表不存在 …"并 **`return 2`**；
- 而 `④ 路由表自检` 从 **`:283`** 才开始 ⇒ 262 行的早退**先于**静态自检。

⇒ 实测后果：`kb/l7/reports/` 下没有 `*routes-winners*`，于是**连"ids 都在登记表里 / 互斥点名成立"这半段纯静态检查也跑不出来**。`routes_reconcile.py:215` 把 `winners` 声明为**必填位置参数**，没有 `--no-winners` 之类的旁路。要今天的数据，只能按 `kb-manage` 的触发电测重生成赢家表（全库无生成者）。

#### B4 `routes.yaml` 同一事实两个数：45 次 vs 88/195【确定为文档不一致；但**不是**数据错，别当把柄用错】

- `routes.yaml:193`：`kb-content-review 此前在 195 次判定里抢走 45 次，是 7 个 brand-* 未过门槛的**唯一根因**；`
- `routes.yaml:205`：`before_65cases: "13 个 brand-* 中 **0 个**过门槛（6/65 逐条全轮命中；kb-content-review 抢走 88/195 次）"`

**两行是同一件事（收窄前的抢活次数）、分母同为 195、分子 45 ≠ 88。** 库内唯一把两者调和的文字在 `skills.yaml:135`：
> 「这 12 个词实测在 195 次判定里抢走 **45** 次（本 agent 复测 harness：**88/195**）」

⇒ 真相是**两个不同测量**（45 = 12 个泛化触发词单独测算；88 = 复测 harness 总数），`routes.yaml:193/205` 各写一个、都没写口径 ⇒ 读表的人会认为库内自相矛盾。**建议按"口径未标"结案，不要按"谁改错了数字"结案。**

#### B5 🟡 `dir_name_map` 有 **3 份副本**，而 `routes.yaml` 那一份**没有任何代码读**【结构性风险；当前取值未漂】

| 副本 | 位置 | 行数 |
|---|---|---|
| ① `routes.yaml` `frozen_expectation.dir_name_map` | `routes.yaml:177-190` | 13 |
| ② `routes_reconcile.py` `ALIAS` | `routes_reconcile.py:43-64` | 14 |
| ③ `_eval-kb-manage/kb_routes_score.py` `ALIAS` | `kb_routes_score.py:33-50` | 14 |

- 实测三表**取值 13/13 全一致**（逐键比对 0 处差异）；唯一差异是**遗留键** `内容审查总控旧`：两份脚本有、`routes.yaml` 没有。
- 反向表与空白归一都从**脚本里的 ②** 取（`routes_reconcile.py:116-163`），**不读 ①**。全仓 `grep -rn "dir_name_map\|frozen_expectation" --include=*.py --include=*.sh .`（排除 `_backups`/`.bak`）→ **只有 `kb_api.py:266` 在错误提示字符串里提到它，无一行代码读它**。
- 而 `routes_reconcile.py:110` 自己写着「★ 与 `_eval-kb-manage/kb_routes_score.py` 的同名表必须**同源**」⇒ 库里自己也承认这是"同一事实写两处"。**加上 yaml 那份是第三处，且是全仓唯一声明为"registry 侧别名"的那份**（`kb_api.py:266` 也这么引用它）。

⇒ 今天没漂，但**单点真源已经失守**：改 `routes.yaml:177-190` 不会影响任何判定，改脚本才会。

#### B6 🟡 待裁：`chains.supply.members` 漏了 L1–L3 的三个层 skill

- `routes.yaml:33`：`scope: "知识库**数据**：L0 → L7"`；`routes.yaml:35`：
  > `members: [kb-pipeline, kb-l0-feishu, kb-canonical-lookup, kb-p0-check, kb-recall, kb-check, kb-repair]`
- `layers.yaml` 的层 skill：`109: [kb-l0-feishu]`／**`154: [kb-ingest-extractor, kb-media-extractor]`**／**`201: [kb-ingest-extractor]`**／**`238: [kb-clause-extractor]`**／`294: [kb-canonical-lookup]`／`406: [kb-p0-check]`／`452: [kb-recall]`／`539: [kb-check]`
- 实测 `grep -c` 三个 L1–L3 skill 在 `routes.yaml` 中命中 **0 / 0 / 0**。

**两种读法都自洽，故列"待裁"而不是"真坏"**：
- 读法一（缺陷）：链的 scope 明写 L0→L7，成员表却少了 L1–L3 三层 —— 而 L0/L4–L7 的层 skill 都在。
- 读法二（口径未写明，且我倾向这条）：`members` 实际是"**有自己 route 条目的对外成员**"—— 表里 7 个成员**逐一都有 `routes[].to`**（`routes.yaml:66,72,100,106,113,120,126`），而 L1–L3 三个 skill 在 `routes[].to` 里出现 **0 次**（它们由 kb-pipeline 按 layers.yaml 调，不是用户直呼的入口）。若采读法二，**应在 `routes.yaml:33-38` 的 note 里写明这个口径** —— 现在没写，读表的人无法判定是漏填还是有意省略。

#### B7 🟡 待裁：`kb-check` 的链条归属

- `routes.yaml:35` 把 `kb-check` 列进**供给链** members；`routes.yaml:43` 评审链 members = `[kb-review, kb-content-review, brand-content-review-agent]`（无 kb-check）；
- 但 `layers.yaml:539` 的 L7 层 skill **就是 kb-check**，而 L7 的层前置在两处都被写进**评审链**（`routes.yaml:47-53`、`report-output-contract.yaml:359-366`）。

⇒ 按 layers.yaml，评审链的层前置会用到 kb-check；按 routes.yaml 的链条划分，kb-check 只属于供给链。`layers.yaml:539` 的注释「跨层统一闸门，不是 L7 的层主」可以解释成"它不属于任何一条链"，但那样的话 `routes.yaml:35` 把它写成供给链成员又自相矛盾。**两条读法各错一边，需人裁。**

#### B8 🟡 指向环：让位表到底在哪

- 工作区规则（`~/.dsh/AGENTS.md`）：「填哪个 = 按 kb-review 让位表（**见 `kb/l7/registry/routes.yaml`** —— 别在这儿抄第二份）」
- 但 `routes.yaml:81` 自己写：`"已能识别专项时交给 13 个 brand-*（见 kb-review 的让位表）"` ⇒ **指回 kb-review**。
- 实测 `grep -n "让位" routes.yaml` → 只有 `49` 与 `81` 两处**提到**，**全表没有任何让位表表体**（13 个中文装载名只出现在 `dir_name_map` 里，没有"问题类型 → 判定主体"的映射）。
- 真正的表体在 `~/.dsh/skills/kb-review/SKILL.md:58`「**让位表**（能识别就交出去，别抢活）」。

⇒ 三方指向不一致：外层说在 routes.yaml、routes.yaml 说在 kb-review、实际在 kb-review 的 SKILL.md。这正是本库自己在 AGENTS.md 里点名的坑（「同一事实写三处不一致而返工过一次」）。

---

## 三、失败项清单（对象 / 原因码 / 要人做什么 / 复开条件）

| 对象 | 原因码 | 要人做什么 | 复开条件 |
|---|---|---|---|
| `routes.yaml:51` | `STALE_SCOPE` | 把 `-L{4,5,6}` 改成 `-L{4,5,6,7}`（与 `report-output-contract.yaml:364` 和 `with_kb_evidence.py:307` 对齐） | 三处取值一致 ⇒ 无闸门可复跑，人工比对通过 |
| `routes.yaml:138` + `routes_reconcile.py:327-332` | `DECLARED_NOT_WIRED` | 二选一：① 让 `checks` 由 `routes.yaml.mutual_not_for` 驱动（并把 `:305` 白名单放开到 pair 涉及的全部成员）；② 改表头，不再声称"对账器会核"并标注第 1 对未覆盖 | 改①后：给赢家表跑门③，`④` 出现 brand 对结果；改②后：表头与实际一致 |
| 门③ 输入 | `MISSING_INPUT` | 按 `kb-manage` 的触发电测重生成 `<RUN>-routes-winners.json` 放进 `kb/l7/reports/` | 文件存在且非 0 条 ⇒ 门③ 得出 exit 0/1 的真结论（不再 exit 2） |
| `routes_reconcile.py:262-268` vs `:283` | `ORDERING`（结构性） | 把纯静态的 `④` 拆到赢家表加载**之前**，或加 `--static-only` | 无赢家表时也能跑出 `④` ⇒ registry⇄routes 自检随时可得 |
| `routes.yaml:193` vs `:205` | `DOC_INCONSISTENT` | 给两处补口径（45 = 12 词单独测算 / 88 = 复测 harness），照抄 `skills.yaml:135` 的写法 | 两处口径自洽 |
| `dir_name_map` 三副本 | `SINGLE_SOURCE_BROKEN` | 定一处真源（建议 `routes.yaml`），让两个脚本 `import` 或读它；`内容审查总控旧` 补进 yaml 或明确标注只存于脚本 | 改真源能改变判定 |
| `routes.yaml:35` / `:43` | `SCOPE_UNSPECIFIED` | 写清 `chains[].members` 的口径（"有 route 的对外成员"还是"层 skill 全集"），并按该口径补齐或加注 | 口径行落地，`layers.yaml` 与本表可机械互推 |
| 让位表位置 | `POINTER_CYCLE` | 定一处（`kb-review SKILL.md` 或 `routes.yaml`），另两处都指它、不复制 | 三处指向同一处 |
| 门⑥ 投影 | `REAL_DRIFT` | 重跑 `kb/.work/gen-host-library.py` 到 staging 后回填；（注意：另有会话正在处理同一件事） | `projection_reconcile.py` 6/6 ⇒ exit 0 |
| 门⑤b | `FLAKY_GATE`（**不是数据缺陷**） | 同刻连跑 3 次留证；若要根治，把 `kb/l8/envelope_census.py:59` 的**固定共享 TMP** 改成按 pid/run 唯一（属机制改动，需裁） | 同刻连跑 3 次读数一致 |
| 门④ | **未跑** | 需在**无并发会话**时单独跑（会写 `kb/l8/workflow_check_<RUN>.json`） | 跑出 9 段读数；②③ 按 `workflow-check-known-drift.yaml` 记为判据过期 |

---

## 四、并发与口径声明（读这份表前必看）

1. **本库存在并发写入者，本次全程是快照读数。** 体检期间实测：
   - `ps` 抓到另一会话正在跑 `kb/l8/workflow_check.py CHK-20261004-1215-3GATES`（会写 `kb/l8/`）与 `l7/scripts/kb_pipeline.py --check`；
   - `kb/.work/publish.log`、`kb/.work/l5_integrity.json` 在体检前 30 分钟内有写入；
   - 仓库根有大量 `_chk-run-CHK-*-REGISTRY-ROUTES` / `*-REG-LAY-ROUTES` 运行目录（最新 `20261004-1210-REG-LAY-ROUTES`，与本次体检同时刻）；
   - `kb/.work/.kb.lock` **不存在**（无持久锁）。⇒ 因此**本轮不跑 ④**（唯一会写盘的闸门），避免两会话同写 `kb/l8/`。
2. **门③ 用历史赢家表得结论时，必须标注它是历史数据**：`_eval-kb-manage/blind_after_r4.winners.txt`（115 行 / mtime 2026-09-29 19:32），**不是今天的数据**。用它跑出的 `④=0`、`①=5` 只能说明"静态自检在 2026-09-29 那批赢家表上成立"，不能代替当日对账。
3. **`strict` 口径的 `①=65` 不是缺陷**：strict 只认逐字相等的登记 id，而实际接走者记的是中文装载名 ⇒ 必然全不一致。要比就两端口径一致（`--alias`）。
4. **门⑤b 的 `1079` 不是缺陷**：该普查的判据是"读不到的 .md 是否都在已分类白名单里"，实测 1079 个全部归类（569 刻意归档 + 510 可再生备份）⇒ exit 0。但**别把它的 `OK` 转述成"信封态 0 个"**，那是 `⑤a` 的读数。
5. **未做的事**：没写库数据、没改任何 `kb/l0–l6` 内容、没删锁、没跑有写盘副作用的闸门（④），未按 `--apply` 做任何动作。本次唯一写进 `kb/` 的是本报告 `kb/l7/reports/CHK-20261004-1216-REG-ROUTES-health.md`（`/bin/cp` 通道，写后 Python `getsize` 与 node `statSync` 均 19262，**无信封**）。

---

## 五、门⑤b 的不稳定读数（单列，因为**别拿它去对峙**）

同一份库、同一批文件、同一条命令，**4 分钟内三次读数不一致**：

| 时刻 | 命令 | 退出码 | 读数 |
|---|---|---|---|
| 12:07 | `sh kb/kbpy l8/envelope_census.py` | **0** | `结论：OK`（1079 个已分类） |
| 12:15 | 同上（`07b-envelope_census.txt`） | **1** | `❌ 必须为 0 活路径 1 个 … 例：l7/skills/视频安全审查/SKILL.md` / `结论：FAIL（活路径 1 个）` |
| 12:17 | 同上（`07b-run1.txt`） | **0** | `结论：OK` |
| 12:17+ | 同上（`07b-run2.txt`） | （超 60 s，未取到终值） | — |

**已确认事实**：
- 被判红的那一个文件在被判红前后**两读者读数一致**（`kb/l7/skills/视频安全审查/SKILL.md`：python `getsize` **6586** = node `statSync` **6586**），且 **mtime 停在 Oct 3 12:51**，体检期间没人改它；
- 该闸门**先把整棵树交给一个 node 子进程扫**（`kb/l8/envelope_census.py:86-90`），**再**由 Python 侧走一遍同一棵树（`kb/l8/envelope_census.py:99-105`），两次遍历**时间不同**，判据是 `py[rel] != node[rel]`（`:111`）；
- 该闸门用**固定共享临时路径** `/tmp/kb_envelope_census_node.json`（`kb/l8/envelope_census.py:59`），实测该文件在 12:17 仍存在（951612 B）；同一时刻本机有多个会话在跑同一批闸门。

**合理推测（不是结论）**：不稳定来自"共享固定 TMP + 两次不同时刻的遍历 + 多会话并发"这三者之一或组合 —— 但这只是**推测**。

**无法验证**：12:15 那一次**具体**是哪个环节把 6586 读成了 6586±4096。本地结构上判断不了，所以**本条只报"判据不稳定"，不报"数据坏了"**。如果要拿它去对峙，请先**同刻连跑 3 次**并把三次读数一起摆出来。
