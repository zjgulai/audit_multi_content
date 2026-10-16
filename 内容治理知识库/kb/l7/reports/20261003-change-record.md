# 2026-10-03 变更记录：把「每次审查都调 L4–L7 + 评审链」接线打通

**用户目标（原话口径）**：用户问一句「这个审核能过吗 / 这个审核一下」→ **自动触发 L4–L7 层 skill ＋ 评审链 skill → 输出报告**。

## 一、改了什么

| # | 文件（源 ＋ 装位副本，均逐字节一致） | 改了什么 | 大小 |
|---|---|---|---|
| 1 | `kb/l7/skills/kb-review/SKILL.md` ＋ `~/.dsh/skills/kb-review/` | 新增 §1.5 层前置（驱动循环）：逐层 RUN 约定、六件事、出报告前置闸门、接线（opt-in）、首跑实测三条硬约束、并发纪律；§2 第 3 步挂引用；§6 加 A0 判据 | 11,399 → **17,861 B** |
| 2 | `内容审查总控/SKILL.md`（源在 `/Users/lute/Desktop/skill/内容治理中文skill/内容审查总控/`）＋ 装位 | 新增 Layer pre-stage 节 ＋ Hard gates 两条（英文，随该文件语域） | 3,275 → **6,209 B** |
| 3 | `kb/l7/skills/kb-content-review/SKILL.md` ＋ 装位 | 新增 §层前置（覆盖被 13 个专项直接接走的路径）＋ opt-in 强度说明 | 20,334 → **22,140 B** |
| 4 | `kb/l7/registry/routes.yaml` | 评审链 note：层前置恒定执行、与让位表无关、逐层 RUN、现状强度 | YAML 校验通过 |
| 5 | `~/.dsh/AGENTS.md` | 执行纪律改为**逐层驱动循环**（②-1..②-3）＋ ②d 审计闸门 ＋ ③ 带 `--require-layer-preflight` ＋ 并发纪律；报告口径改为**每次都出报告** | — |
| 6 | `kb/l7/registry/layers.yaml` | 给 `l4_integrity.py` / `l5_bench.py` / `l6_bench.py` 加「驱动循环默认跳过」注记（无预演档、照跑会写盘） | YAML 校验通过 |
| 7 | `kb/l7/registry/report-output-contract.yaml` | 新增 `applied_20261003`（层前置 ＋ 报告口径 ＋ 误写件登记 ＋ 验收）与 `GAP-RO-5` | 22,356 B |
| 8 | `kb/l7/review-engine/core/with_kb_evidence.py` | **新增 opt-in 层前置闸门** `--require-layer-preflight <BASE>`：逐层调既有审计，任一层红 ⇒ `NEEDS_INPUT` / 退出码 3，**不出三态结论**（判据未新增，仍是一把尺子） | ＋约 90 行 |

## 二、验证（可复跑）

**首跑（`BASE=20261003-0654`，四条判据全过）**

| 判据 | 改造前 | 改造后 |
|---|---|---|
| 三条 `skill_invocation_audit` | ❌ E1 红 / exit 1 | ✅ **红 0 / 黄 1(E5) / exit 0** ×3 |
| `extra.skill_sessions` | `{}` | ✅ L4=`a01f403f…` / L5=`b6599135…` / L6=`b2f61bae…`（**真实子会话 id**） |
| 层侧落章 `skill` = `layers.yaml` 声明 | 无加载 | ✅ `kb-canonical-lookup` / `kb-p0-check` / `kb-recall` |
| 报告落盘 | — | ✅ `kb/l7/reports/20261003-0654.review.md`（python `getsize` = node `statSync` = 6,436） |

`skill_evidence`：`registry_echo` → **`agent_reported`**；`human_involved`：false → **true**。

**新闸门三条用例（2026-10-03 实测）**

| 用例 | 命令 | 结果 |
|---|---|---|
| 层前置过 | `with_kb_evidence.py --text "…" --require-layer-preflight 20261003-0654` | BLOCK（结论照出）＋ 层前置行 `L4=✅/L5=✅/L6=✅ ｜ 红合计 0`，**exit 0** |
| 层前置不过 | 同命令，`--require-layer-preflight 20261003-9999` | **NEEDS_INPUT**、逐层列 `exit/红/黄/sessions`，**exit 3**、不出三态结论 |
| 回归（不带开关） | `with_kb_evidence.py --text "…"` | 与旧版一致（无层前置行），exit 0 |

**库自带闸门**：`kb/l7/scripts/skills_check.py` → 五类问题合计 **0**、结论「全过」、exit 0（源↔装位副本一致）。

## 三、首跑暴露的库内缺口（**已登记，未擅自改引擎**）

1. 三个层引擎无预演档（`l4_integrity.py` / `l5_bench.py` / `l6_bench.py`）→ 已加注记「驱动循环默认跳过」。
2. `--help` 会被真执行（脚本不解析 argv）→ 已写进 skill 的硬约束。
3. `l6_selftest.py` 只认 `--run=<RUN>`（位置参数被静默忽略并回落默认 RUN）→ 已写进硬约束。
4. 「落章存在 ＋ skill 对」不足以证明本跑 ⇒ 只能认 `skill_sessions` ＋ `applied/dry_run`。
5. 跨会话并发：陈旧锁 ＋ 两会话同时恢复 ⇒ 已写进 AGENTS.md 并发纪律。
6. `kb_pipeline.py --check` 本轮被外部 `SIGTERM` 打断，**未取得结论**，不当作通过。

## 四、未做（下一批）

- 多层 RUN 记账覆盖缺陷（`kb/l7/runs/<RUN>.json` 单文件被最后一层覆盖）—— 本轮用「逐层一 RUN」绕过，**未改引擎**。
- 层前置闸门从 opt-in 收紧为**默认开**（机器入口 `kb_api.py` 加载不了 skill，需先给那条路设计等效留痕）—— 见 `GAP-RO-5`。
- L4 的 `l4_report.py` 依赖 `kb/.work/l4_integrity.json`，而该件因「默认跳过」停在 2026-10-02 ⇒ 落章 `verdict=FAIL` 属**继承旧红**，需人裁是否给它开预演档。

---
> 报告落盘走 `node` 通道（`kb/.work/write_via_node.mjs`，写入后读回逐字节比对）。
> 结论与证据均照抄引擎与库文件；本记录不含手写条款号或三态结论。


## 五、第二批（同日）：默认收紧 ＋ 机器入口等效留痕 ＋ 记账合并

1. **③ 闸门收紧为「默认要求」**（`with_kb_evidence.py`）：不给 `--require-layer-preflight <BASE>` ⇒ **拒答**
   （`NEEDS_INPUT` / 退出码 3）；确实不做要**显式** `--allow-no-layer-preflight`，结论记
   `layer_preflight.mode=waived_by_caller`。
   - **翻默认前先量了爆炸半径**（`grep -rn with_kb_evidence`）：`kb_api.py` 与 13 个测试文件都走**模块级**
     `run()`、**不经 CLI**；无 cron/launchd 调用。故收紧只影响 CLI 侧，而 CLI 侧
     （AGENTS.md ＋ 三个 skill 正文 ＋ MVP 手册）已同步改成必带 BASE。
   - **四例实测**：真 BASE → BLOCK / exit 0（带层前置行）；假 BASE → exit 3；**不带 BASE → exit 3（新默认）**；
     显式豁免 → BLOCK ＋ `层前置：未做（mode=waived_by_caller）`。
2. **机器入口等效留痕**（`kb_api.py`）：新增 `ReviewReq.layer_preflight_base`。传了 ⇒ 用**同一份**审计照核
   （红 ⇒ **HTTP 409** ＋ `fails_closed=true` ＋ `gate.verdict=refused`）；不传 ⇒ 响应记
   `layer_preflight.mode=waived_by_api`（**缺前置可见，不许静默**）。
   **已部署并线上实测**：`launchctl kickstart -k gui/$(id -u)/com.dsh.kbapi`，`/health` 200、
   `openapi` 已含新字段；线上三例 = 200/enforced、409/refused、200/waived_by_api。
3. **记账合并**（`kb/l7/scripts/run_record.py`）：同一个 `run_id` 再写一次 ⇒ **合并而非覆盖**
   （列表取并集、`extra` 逐键/逐层合并、标量取新值、`write_merges` 记次数、`previous_at` 留痕）。
   临时目录内单测通过（`skills` 三项并集、`layers=[L4,L5]`、`skill_sessions={L4,L5}`、index 两行）。
   这是登记在 `kb-pipeline/SKILL.md` 的待办「多层 RUN 记账覆盖」的最小修法；**根治口径仍是逐层一个 RUN**。
4. **★ 修正上一批的一处判断（重要）**：上一批我写「L4 落章 `verdict=FAIL` 属**继承旧红**」——**这句是错的**。
   用新鲜 scratch 重跑 `l4_integrity.py` **仍 FAIL**：8 项里 `l3_append_only` / `article_numbers` /
   `ledger_coverage` 三项红，且这三项**已登记在 `l7/registry/l4-known-drift.yaml`**（判据侧漂移，非数据坏；
   实质闸门 `l4_gate.py` 的 C1–C6 独立复算另算）。
   故 `layers.yaml` 注记已改成「**驱动循环照跑**」（它只写 `kb/.work/` 下的 scratch，不是库状态；
   注意它 :162 会 subprocess 跑 `l4_article.py <RUN>`，dry-run 安全），并写明：
   **不许把这条 FAIL 读成「L4 数据坏了」，也不许读成「继承旧红」**。
5. **文档与登记同步**：`kb/l7/MVP-评审链-跑通手册.md` 入口命令、三个 skill 正文、
   `~/.dsh/AGENTS.md`、`report-output-contract.yaml` 的 `GAP-RO-5`（状态 →「主体已落地」，
   遗留一问：**API 侧是否也改成「不带 BASE 即 409」** —— 需飞书/守衡侧先传 BASE）。

**第二批验证**：三条审计仍 `红 0`（黄 1 = E5 预演）；引擎四例如上；`skills_check.py` **五类问题 0 / 全过**；
`pytest kb/l7/review-engine/tests` **48 passed**；API 线上三例如上。

---

## 六、第三批（同日）：L7 声明对齐 ＋ 13 专项分类 ＋ 会话级认领（用户点名「动手做第 2、3、4」）

### 项 2｜关闭 L7 的两处**虚假声明**（L7-C1 / L7-C2）
- **L7-C1**：`layers.yaml` 的 L7 条目只登记了 `skill:`、没写 `engine:`，而 `report-output-contract.yaml`
  的 L7 段宣称「四层逐层留痕齐平」；实跑后 L7 **没有落章**（代码级 `EXEMPT_LAYERS["L7"]`，属结构性豁免）。
  → 已在 `layers.yaml` 把 L7 注记写成「**记账 ＋ 会话留痕（`--skill-session L7=<id>`），无层侧落章**」，
  与 `skill_invocation_audit.py` 的 `EXEMPT_LAYERS` 对齐；**没有伪造一个 L7 落章来「凑齐」四层**。
- **L7-C2**：`kb-check/SKILL.md` 原先没分清自己有两个档位 ⇒「驱动循环里跑 L7」与「体检档跑 6 道闸门」
  被混成一句，且引擎清单被**抄了第二份**（库内已因同一事实写三处不一致返工过一次）。
  → `kb-check/SKILL.md` 4,893 → **6,472 B**，新增 **§0 两个档位**：
  · **driver-loop 档** = 只跑 `layers.yaml` 本层 `engine:` 那 3 个引擎；
  · **体检档** = §1 的 6 道闸门（其中 `workflow_check.py` **无干跑档、会写 `kb/l8/`**，评审循环里不许跑）；
  并写明「**引擎清单的唯一真源是 `layers.yaml` 本层 `engine:`**；本节清单是体检档编排，不是第二份事实源」。
  §1 ④ 注记「无干跑档 ＋ 会写盘」，§4 写明 `health.md` **仅体检档**产出。版本 1.1.0。
- **L7-C3**：三处文档对「L7 有没有落章」口径不一致 → 统一为「**无落章、靠 `--skill-session` 会话留痕**」，
  并登记进 `report-output-contract.yaml` 的 `l7_declaration_conflicts_20261003`。

### 项 3｜13 个专项逐一分类（顺手关上「专项绕过层前置」的口子）
逐个读 13 个专项 skill 的**正文**再归类（**不是按名字猜**），每个都追加了 `2026-10-03` 的显式块：

| 分类 | 数量 | 成员 |
|---|---|---|
| **强制链路**（素材审查入口，恒定跑 L4→L5→L6→L7） | 6 | 文案合规审查、图片安全审查、视频安全审查、产品宣称核验、AI溯源与权利审查、美国本地化审查 |
| **层前置**（总控） | 1 | 内容审查总控 |
| **下游指路**（裁决／报告环节，不重复跑层前置，指回入口） | 2 | 审查裁决、审查报告与记忆 |
| **不适用**（不是素材审查入口） | 3 | 送审登记、证据源维护、审查流程评测 |
| **发布件指路**（Review → Feishu，含 L0 locator 与行序规则） | 1 | 飞书审查流转 |

13/13 source ↔ `~/.dsh/skills/` **逐字节一致**。

### 项 4｜会话级认领（补上 `kb/.work/.kb.lock` 管不到的会话级窗口）
- 新增 `kb/l7/scripts/kb_loop_claim.py`：`status` / `claim` / `release`，认领文件 `kb/.work/.kb-loop-claim.json`；
  退出码 **0 = 拿到／释放 ｜ 3 = 被别人占着（别抢）｜ 2 = 用法错**。
- 接线三处：`~/.dsh/AGENTS.md`（并发纪律改成两层）、`kb-review/SKILL.md` §1.5、
  `report-output-contract.yaml` 的 `session_claim`。
- **认领是「全局单槽」**：`--base` 只作标识、**不分槽** —— 跑**不同** BASE 的第二个会话照样 exit 3。
  要保护的共享资源（`kb/.work/.kb.lock`、`kb/l7/runs/index.jsonl`、各层 `runs/`）是**全库唯一**的；
  按 BASE 分槽＝把 2026-10-03 的双计／覆盖事故放回来。此条已写死进脚本 docstring，防「顺手改成按 BASE 分槽」。

### 项 4 验证时**实测抓到并修掉两个真缺陷**（不是文档问题，是代码问题）
| 缺陷 | 现象 | 根因 | 修法 |
|---|---|---|---|
| **CLAIM-C1** | `--ttl 0` 被静默升格成 **45 分钟**：认领已 60 分钟仍判「进行中」⇒ 永不陈旧、认领永久卡死 | `float(c.get('ttl_min') or 45)` —— `ttl_min=0` 是 falsy，`or` 把它吃成默认值 | 改成 `45.0 if raw is None else float(raw)`（只有 None／缺失才回落默认） |
| **CLAIM-C2** | `--take-over` **从不生效**：跨会话分支无条件 `return 3`，参数被 argparse 接受却被丢弃 | `take_over` 只在 `same`（同 BASE 且 同 pid／同 session）分支被消费；而它唯一的用途就是**跨会话接手**（上一会话崩了 ⇒ session／pid 必然都不同） | 跨会话分支改为「**陈旧 且 `--take-over`**」才放行并打印接管告警；新鲜时照样拒 |

两个缺陷的共性：**「声明了但代码从不兑现」** —— 与 L7-C1/C2 是同一类病（**申报 ≠ 真相**）。

**第三批验证（可复跑，全部实测）**：
- 认领 **8/8**：① claim exit0 ② 异会话 claim exit3「别抢」③ 新鲜认领 ＋ `--take-over` 仍 exit3
  ④ 认领推到 60 分钟前 ⇒ `status` 报「陈旧（可 --take-over）」exit0 ⑤ 陈旧 ＋ `--take-over` exit0（打印接管告警）
  ⑥ release exit0 ⑦ `--ttl 0` ⇒ 立刻判陈旧、可被接手（CLAIM-C1 已闭）⑧ 收尾 `status` exit0 空、无残留认领文件。
- `skills_check.py`：**五类问题 1=0 2=0 3=0 4=0 5=0 ｜合计 0 ｜ 全过 ｜ 退出码 0**。
- `kb/l7/registry/*.yaml`：**13/13 解析通过**（含改动后的 `report-output-contract.yaml`）。
- 副本一致：`kb-review` ／ `kb-check` ／ 13 专项 **全同**。

**第三批观察到的现场（诚实记录）**：验证期间（10:04–10:05）**另一个会话**在跑同一条循环，写出
`kb/l7/reports/rv-20261003-085818.*`（BASE `RV-20261003-0855`）。**独立复核**（不采信它的自述）：
三层审计 `红 0 / 黄 1（E5 预演落章）`、退出码 0，且该报告第 91–93 行**如实披露了黄 1 与「本单未落盘」** ——
即：**机制在别的会话里也能跑通，诚实报告的口径也立住了**。
但**无法验证**那次运行有没有先认领（认领文件当时不存在；而我自己的自测认领在那段时间确实占着全局槽位）。
⇒ 项 4 只把认领做成「**文档 ＋ 脚本可用**」，**没有任何 hook 强制它** ——
这是本批**未闭合的缺口**，不许读成「已解决」。
**另记一条自测教训**：自测 `claim` 会占用**真槽位**，所以自测必须**秒级 claim＋release**，别边测边说。

---

## 七、第四批（同日）：**L7 进闸门**，「四层留痕齐平」从口径变成闸门

**用户指令**：「动手改」—— 把 `LAYER_PREFLIGHT_LAYERS` 从 3 层扩成 4 层。

**完整口径（成因 / 前后实证 / 代价 / 回滚）登记在
`kb/l7/registry/report-output-contract.yaml` → `applied_20261003.layer_prestage.l7_in_gate_20261003`
（引用，不复制 —— 契约 #4：同一事实写两处，第二处必然过期）。这里只记本批的**改了什么 ＋ 跑出什么**。

**改了什么**
| 件 | 改动 |
|---|---|
| `kb/l7/review-engine/core/with_kb_evidence.py` | `LAYER_PREFLIGHT_LAYERS` 3 层 → **4 层**（＋`"L7"`）；docstring、`--require-layer-preflight` help、两处拒答文案同步改成 `L4→L5→L6→L7` |
| `kb_api.py` | `layer_preflight_base` 字段说明改成 `-L{4,5,6,7}`（**服务已 kickstart 重启**，PID 83304 → 65243） |
| `~/.dsh/AGENTS.md` | ② 段标题 ＋ **②b**（L7 从「不带凭据可正常跑完」改成**必须带 `--invoked`/`--skill-session`**）＋ **②d 四条审计** |
| `kb/l7/skills/kb-review/SKILL.md` | §1.5 驱动循环的 L7 行补凭据；§1.5 闸门循环加 `<BASE>-L7`；§6 **A0 判据「三条都红 0」→「四条都红 0」** |
| `kb/l7/MVP-评审链-跑通手册.md` | 入口命令注释补 L7 凭据提示 |
| `report-output-contract.yaml` | 新增 `l7_in_gate_20261003`；`evidence_gate` / `verification_20261003` 三条 → 四条 |

**跑出什么（全部实测，可复跑）**
- **改前对照**（同一个 L7=红1 的真实 BASE `RV-20261003-0855`）：
  `层前置：L4=✅ / L5=✅ / L6=✅ ｜ 红合计 0` ＋ **完整 BLOCK 结论（exit 0）** —— L7 根本没露面。
- **改后**同一 BASE 同一条命令 ⇒ `NEEDS_INPUT` / **exit 3**，拒答行逐层列出
  `L7 run=… exit=1 红=1 黄=0 sessions={}`。
- CLI 出口码矩阵 **5/5**：L7红→3 ｜ 四层绿→0 ｜ BASE 不存在→3 ｜ 不给 BASE→3 ｜ 显式豁免→0。
- 机器入口 **3/3**：传 L7红 BASE → **HTTP 409**（`red_total=1`，details 里 L7 红）｜ 传四层绿 BASE → 200 ｜ 不传 → 200 ＋ `mode=waived_by_api`。
- 回归：`pytest kb/l7/review-engine/tests` **48 passed**；`skills_check.py` **五类问题 0 / 全过**；
  `report-output-contract.yaml` 解析通过；`kb-review` 源↔装载位**逐字节一致**。

**新增交付**：`kb/l7/reports/20261003-verify-prompts-3.md`（3 条**裸问**提示词 ＋ 4 条硬指标 ＋ 判废对照表）。

**这条改动的真实后果（要对用户讲清）**：闸门**变严**了 —— 2026-10-03 10:04 那条外来会话的跑法
（L4–L6 齐、L7 无会话痕）**现在会被直接拒答**，直到它补上 L7 的 `--invoked`/`--skill-session`。
这是「四层齐平」的定义，不是回归缺陷。

---

## 八、第五批（同日）：三道防线 —— 层前置只保护「证据管道」，不保护「判定主体」

**触发**：用户问「这张图合规吗」。跑完发现：**L4/L5/L6/L7 四条审计全绿**，
而 `kb-review` 让位表指定的判定主体（`图片安全审查`）**一次都没加载**，报告照样出了、表行照样写了。
用户当场追问 skill 账，遂定三道防线并批准。

**完整口径登记在 `kb/l7/registry/report-output-contract.yaml` →
`applied_20261003.three_defenses_20261003`**（成因 / 三道防线 / **豁免清单** / 实测 / 回滚）。
此处只记**改了什么、跑出什么**。

**改了什么**
| 件 | 改动 |
|---|---|
| `kb-content-review/scripts/review.py`（源＋装载位） | **防线1**：新增 `_entry_gate()` —— 只认 `KB_ENTRY ∈ {with_kb_evidence, kb_api, selftest}` 或显式 `--i-am-the-entry`，否则打印拒跑说明并 `exit 2` |
| `kb/l7/review-engine/core/with_kb_evidence.py` | subprocess env 带 `KB_ENTRY=with_kb_evidence`；新增 `--decision-owner` / `--allow-no-decision-owner` / `--loaded-skill`；**判定主体 fail-closed**（缺 ⇒ NEEDS_INPUT / exit 3）；`evidence_meta.decision_owner` + `loaded_skills` 留痕；人读输出加「判定主体：」行 |
| `kb/l7/scripts/run_record.py`（调用侧） | run 记录带 `extra={"decision_owner":…, "loaded_skills":[…]}`,—— 原 `skills=["kb-content-review","审查裁决"]` 是**硬编码**，正是「判定主体缺席也看不出来」的原因；**不动那行**，另开 extra 记真值 |
| `kb/l7/review-engine/core/feishu_publish.py` | **防线2 终点**：无 `decision_owner` ⇒ **拒发 exit 3**（可 `--allow-no-decision-owner`）；**形状守卫**：`decision` 不是对象（后门裸报告形态）⇒ 干净拒发 exit 2 |
| `kb-content-review/SKILL.md`（源＋装载位） | 原第 264 行「本 skill 的**可执行参考实现**：`scripts/review.py`」→ 改为「**内部引擎，不是对外入口**」；§层前置补判定主体闸门；并更正原「层前置与新鲜度**同一强度**」那句（它只对其中一扇门成立） |
| 6 个强制链路专项 ＋ `内容审查总控` | 强制链路块的引擎命令补 `--decision-owner <本 skill 名>`，并加一条「判定主体默认要求」说明。**13/13 source↔install 逐字节一致** |

**跑出什么（全部实测）**
- **防线1**：直调 `review.py` ⇒ `exit 2` + 拒跑说明；`KB_ENTRY=selftest` 或 `--i-am-the-entry` ⇒ 正常出结论（`--text x` ⇒ 拒答 exit 3；有依据的话 ⇒ 出结论）。
  爆炸半径已核：`kb_api.py` **不** subprocess 跑 `review.py`（调同一份判据）⇒ 机器入口不受影响。
- **防线2**：引擎不给 `--decision-owner` ⇒ `NEEDS_INPUT` / **exit 3**；给了 ⇒ BLOCK / exit 0，
  行内打印 `判定主体：产品宣称核验（declared）`；发布件对「有层前置但摘掉判定主体」⇒ **拒发 exit 3**。
- **防线3**：run 记录 `kb/l7/runs/20261003-124616.json` 的 `extra.decision_owner` 四字段齐
  （`skill/mode/declared_by/loaded_skills`）。
- **形状守卫**：拿「无闸门那扇门」产出的 `kb/l7/reports/20261003-110652.json` 喂发布件 ⇒
  原行为是 **AttributeError 带栈崩（exit 1）**（看起来像脚本坏了，其实是用错入口），现为干净拒发 exit 2。
- **回归**：`pytest kb/l7/review-engine/tests` **48 passed**；`skills_check.py` **五类问题 0 / 全过**；
  `report-output-contract.yaml` 解析通过。
- **补做原单**：真正加载 `图片安全审查` 后，以 `--decision-owner 图片安全审查 --loaded-skill 图片安全审查`
  重跑（复用 BASE `20261003-1108`）⇒ `REVIEW` / 2 处，行内带 `判定主体：图片安全审查（declared）`；
  飞书按内容 ID **upsert 同一行** `recvwX7TnR8QYP`（未新增），报告首行 = 标题。

**这条改动的真实后果**：闸门**再严一层** —— 任何「跑完层前置就出结论、但没说谁判的」的跑法，
现在会拿到 `NEEDS_INPUT`；即使显式豁免，**飞书也发不出去**。这正是「判定主体缺席必须看得见」的意思。

---

## 九、第六批（同日 20:4x）：新鲜度记账断了 —— 为什么"日更 GREEN"却"评审链拒答"

**完整口径（根因 / 三项修复 / 新攻击面 / 回滚）登记在
`kb/l7/registry/report-output-contract.yaml` → `applied_20261003.freshness_ledger_fix_20261003`**
（引用，不复制）。此处只记**改了什么、跑出什么**。

**根因一句话**：`measure()` —— sidecar（`kb/l7/registry/layer_run_freshness.json`）的**唯一写入者**
—— **全库没有任何生产调用点**。于是 L4/L5/L6 的观测时间冻结在 **10-02 13:22**，
`judge()` 拿它算年龄 = **31.2 小时 > 24 小时 ⇒ 永久拒答**；**当天 08:30 日更其实跑成功过、体检 GREEN**。

**改了什么**
| 修复 | 件 | 改动 |
|---|---|---|
| **4** | `kb/l7/scripts/layer_freshness.py` | `run_at` / `run_age` **同源更新**；新增 `run_at_source` 让时间来源可见 |
| **2** | 同上 | 落章时间 vs sidecar 观测时间**取较新者**；且**只认 `provenance=measured`**（`seeded_from_disk` 是补记，不认） |
| **1** | `kb/l7/scripts/daily_sync.py` | 新增 `_freshness()` + `observe()`：每层**测前**取 `output_fingerprint`/`watermark_digest`，`kb_pipeline --apply` 跑完**立刻 `measure()`** 落真实观测 |
| 登记 | `report-output-contract.yaml` | 新增 `freshness_ledger_fix_20261003`（含 `new_attack_surface` 与未做的收紧项） |
| **1b** | `kb/l7/scripts/daily_sync.py` | **用户复查时发现的洞**：修复1 只覆盖 `WRITE_LAYERS`（L1–L6），**L0 与 L7 没覆盖** —— 而 **L0 当时只剩 8 分钟就翻红**（判据来源=落章 mtime 10-02 21:02）。补：步骤①后观测 **L0**、步骤③（体检）后观测 **L7** |

**跑出什么（全部实测）**
- **修复 1 验证成功**：日更 6 层逐层打出 `↳ 新鲜度观测已落：change_state=no_new_input provenance=measured 水位未变=True`；
  日更收尾 `L0对齐 exit=0 ｜ 写档完成 L1,L2,L3,L4,L5,L6 ｜ 失败 无 ｜ 体检 exit=0`
- sidecar 现在 L1–L6 全是 `provenance=measured`、`at=10-03 20:47/20:49`、note 带「修复1」
- `judge()` **8 层全 fresh**；`review_freshness_gate.py` **exit 0（放行）**
- **日更没删数据**：跑前 8,967 文件基线，240 行差异**全部是 mtime 变化、size 一字不差**（0 个文件真的消失）；
  另新增 273 个主要是 `kb/l8/_stage/feishu-align/20261003-2043/*`（L0 对齐正常暂存）＋ 我自己改的契约件
- **本单端到端跑通**：`BLOCK` ｜ 层前置四层 ✅ 红合计 0（**四个真 UUID**）｜ `判定主体：文案合规审查（declared）`
  ｜ 飞书云文档**整篇覆盖复用既有链接**（`KEHsdqSFdobIUqxVA3gcFVQSn3g`）＋ 表行**更新既有行** `recvwZqG2JtPIR`
  ｜ 本地 `kb/l7/reports/rv-20261003-205302.feishu.md`（9,335 B，首行=标题）
- 四条审计 `红 0`（L4–L6 黄1=E5，L7 红0黄0）；无残留锁、无残留认领、探针件已清；`skills_check` 五类问题 0

**过程中踩到并如实记录的两条**
1. **陈旧锁挡停第一次日更**：`kb/.work/.kb.lock` 是 **18:53 的 autorun** 留下的（`pid=79877` 已死、未宣布释放）。
   按库规**先 `kb_pipeline.py --check`（全过、硬问题无、零写自证）再删锁**，锁副本留 `/tmp/kb.lock.stale-20261003-185311.bak`。
   ⇒ **autorun 会漏锁**（`AUTORUN_TIMEOUT=180s` 超时/被杀时不释放）—— 登记待办。
2. **我自己的告警是假警报**：第一次看 diff 时我用 `awk '{print $3}'` 取路径，**取到的是文件大小**，
   于是把 240 个"mtime 变了"的文件误读成"文件消失"。**逐个 `-e` 核过：真的不存在 = 0 个。**
   ⇒ 记一条教训：**判"文件没了"必须逐个 stat，别拿 diff 行数当结论。**
3. **L0 与飞书侧仍未完全对齐（同日 20:54 回执，用户复查时核出）**：
   `{"same": 612, "only_feishu": 10, "only_l0": 0, "changed": 0, "pull_failed": 2}`
   —— **查清了，两个独立结论，都不是"管线卡住"**：
   · **`only_feishu: 10` 是准入规则正常工作** —— 逐条原因全同：`准入未过：材料审核状态=[] != ["通过"]`
     （飞书侧那 10 条材料**尚未审核通过**，L0 准入要求该字段 `== ["通过"]`）⇒ **故意不入库，符合设计**。
     ★ **更正我上一轮的说法**：我说过"自动拉取实际没生效" —— **那句是错的**；`auto_apply: true` 生效了，
     是**准入闸门**挡的。summary 一字不变是因为**没人去飞书侧点通过**，不是管线卡住。
   · **`pull_failed: 2` 是 2 张表权限不足，且库里 2026-09-30 就登记过**：
     `kb/l7/registry/l0-expected-diffs.yaml` 的 **EX-2**（专家修订汇总表 `tbl8AI00JZO1iZtp`）与
     **EX-3**（内容公式（仅供参考） `tblVdl0jdK9G4ld3`），`code 91403`、`expected: 1`，reason 原文：
     「**资源级 ACL：bot 身份（守衡）不在该表的协作者里。「用户自己打开得开」≠「应用读得到」，
     是两套权限**…… **重试 / 换身份都没用**」⇒ **要人在飞书侧把「守衡」加为协作者**（我做不到）。
     独立复核：bot 读该 base ⇒ `91403`；bot 读另一个 base（`GnRZ…`）⇒ ✅ 正常。
   · **但有个副作用没人报**：那两张表的 L0 副本停在 **09-23 12:48（395 条）/ 09-24 10:04（7 条）**
     —— **10 天 / 9 天前的快照**，而 `daily_health` 只报 `pull_failed` 计数（登记过 ⇒ GREEN 是对的），
     **不报"这两张表的副本已经多旧"**。⇒ 登记待办：**已登记的 pull_failed 表，要暴露其 L0 副本年龄**。

## 十、收紧项（同日 21:2x）：`measured` 必须能核对到**真运行**

上一条留的洞（「任何能写 sidecar 的东西都能让 8 层瞬间变新鲜」）已堵。`layer_freshness.py` 新增
**`_trace_exists()`**：采信 `provenance=measured` 的时间**之前**，先拿它的 `run_id` 核对真运行；
核对不上 ⇒ **不采信**（退回落章时间）并写 `sidecar_time_rejected`。

**判据（★ 别改成通配 —— 第一版就是那么写的，实测把洞又打开了）**：认三种**精确**形态
`kb/l7/runs/<rid>.json` ／ `kb/<layer>/runs/<rid>.json` ／ `kb/l8/runs/<rid>-l0-align.json`。
第一版加过 `<rid>-*.json` 兜底，结果那条伪造的 rid 正好有 `kb/l7/runs/<rid>-L4.json`（层记账件）
⇒ **通配一匹配就放行**；而它的层侧产物还是 `-dryrun.json` 干跑件，库规明写「干跑档不算跑过」。

**实测**：伪造 rid `REV-202610031826-momcozy-pump` → `_trace_exists=False`（**抓得住**）；
日更 rid `20261003-2055` → True；旧 `20261002-1330-L4` → False。
配套把 `daily_sync.py` 的 L7 观测改成用 **`_newest_l7_run()` 取真产物名**当 rid（原用墙钟，
`20261003-2059` 核对不到 ⇒ 白落一次）。第三次日更后：**八层全部**
`run_at_source=sidecar 观测（provenance=measured＋run_id 已核对）`、距翻红 23.9–24.0h、闸门 exit 0。

**同一时段发现并发（记录，未处置）**：第三次日更（21:17–21:23）期间**另一个会话正在跑**
（`session-29c8d8fe…`，BASE `20261003-2102`，21:2x 仍在跑 `--only L6 --gate-only`）——
**认领槽被它持有**，我**没有抢**（`release` 按规被拒）。它的认领显示「陈旧」，但那正是
**CLAIM-C3**（认领 pid 必死 ⇒ 超 5 分钟必判陈旧）的又一次现场复现。
