# workflow_check 修复记录 · `REPAIR-20261004-1307-R9` → `REPAIR-20261004-1314-R9-AFTER`（第 9 轮）

- **用户指令**：「workflow_check 没过，帮我把失败项按原因码修掉，修完复跑。」
- **交表时点**：`2026-10-04 13:17 CST`
- **库根（cwd）**：`/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理`
- **闸门**：`kb/kbpy l8/workflow_check.py`（无干跑档，跑它即写 `kb/l8/workflow_check_<RUN>.json`）
- **run_id**：修前 `REPAIR-20261004-1307-R9`（`at=13:07:54`）／ 修后 `REPAIR-20261004-1314-R9-AFTER`（`at=13:13:30`）
- **纪律**：未加 `--apply` / `--write-gate`；未删任何锁或认领文件；**未改任何判据**；未改 `kb/l0~l6` 任何数据或台账；
  **未写任何 run 记录**；未抢循环认领；未重启服务；未向飞书发布任何东西。

---

## 0. 一句话结论（先读这条，它和你的预期不一样）

> **本轮和前面 8 轮不一样：确实修掉了一条实质红（⑥），复跑证明它转绿；但仍有一条修不掉，原因是原因码自己规定不许修。**
>
> 1. **修得掉的**：首跑多出 **⑥ 文档可见性**（一个 **4096 字节信封态** 的 `.md`），按原因码
>    `kb-repair §2「信封态（差值 4096）」` 的修法真修 → 复跑 **⑥ 转 PASS**，全工作区再扫 **信封态 0**（退出码 0）。
> 2. **修不掉的**：**②③**。它们对应的原因码 `kb/l7/registry/failure-playbook.yaml → gate_red.workflow_check`
>    写着「②③ 属**已登记判据漂移** ⇒ **无需修数据**；要它们转绿必须**改判据，单独走一轮**」，
>    `forbidden` 又明写「不许改写历史 run 记录里的 artifact sha」「不许把 L3 回滚到 1527 行时代」
>    「不许把 ②③ 的判据就地改宽而不同时报批」。⇒ 本轮按 `reopen_when` 的**合规默认动作 = 只登记**。
> 3. ⇒ 复跑后：**9 段里只剩 ②③ 红**（⑦ 之外的 7 段全 PASS）。
> **唯一能让闸门变绿的动作是改判据（选项 A），它需要你点头；本会话是子 agent，问不到人，原样带回给委派方（见 §5）。**

---

## 1. 修前 / 修后 同一条闸门对照（命令 ＋ 退出码）

```bash
# 修前
sh kb/kbpy l8/workflow_check.py REPAIR-20261004-1307-R9        # → 退出码 1
# 修（⑥ 的信封态；见 §2）
python3 _repair-run-REPAIR-20261004-1307-R9/fix-envelope.py    # → 退出码 0
# 修后
python3 tools/envelope_gate.py --reader consumer .             # → 退出码 0（扫 3080，信封 0）
sh kb/kbpy l8/workflow_check.py REPAIR-20261004-1314-R9-AFTER  # → 退出码 1
sh kb/kbpy l7/scripts/skills_check.py                          # → 退出码 0（五类全 0）
```

| 段 | 修前 | 修后 | 本轮动作 |
|---|---|---|---|
| ① 环境与版本纪律 | PASS | PASS | — |
| **② 权威库 l0~l6 未被改动** | **FAIL** | **FAIL** | 只登记（原因码明令不许修数据） |
| **③ 前序产物哈希（45 项）** | **FAIL**（20 项 mismatch） | **FAIL**（同 20 项） | 只登记 ＋ 补做来源审计 |
| ④ 分层库 → 生成器 → 视图 | PASS | PASS | — |
| ⑤ 装载位 → 加载器（读工具+体检） | PASS | PASS | — |
| **⑥ 文档可见性（agent 能否读到）** | **FAIL**（`其他` 桶 = 1） | **PASS** | ★ **本轮真修**：信封态 .md → cp 通道重写（§2） |
| ⑦ 消费侧 skill 可用 | PASS | PASS | — |
| ⑧ 工作台与服务 | PASS | PASS | — |
| ⑨ 写入侧（ingest 闸门 + 落盘通道） | PASS | PASS | — |

修后逐段读数（`kb/l8/workflow_check_REPAIR-20261004-1314-R9-AFTER.json`）：

```
装载位：509 条 / 信封 0 / E001 None / E046 None / 健康分 79.2 / 检索 [111, 1, 509, 0]
派生链：生成器 11:26:57 408a6d079312b66f 73520B；沙箱产出 510 md / 信封 0
可见性：工作区 6348 md，不可读 510 {'他人产物 hostlib': 510}      ← `其他` 桶 = 0
裁决：FAIL（未过：['② 权威库 l0~l6 未被改动', '③ 前序产物哈希（45 项）']）
```

> 注：⑨ 的 detail 里那句 `[E026] 内容质量分 52.1 < 60` 是**探针自己**的读数（探针正文是刻意短的），
> 第 ⑨ 段的判据是「**闸门生效 + 不留半成品**」（`landed` = 0 个、信封 0），不是「探针要能落盘」。这是设计如此。

**⑥ 转绿的第三方独立确认**（不是我自己的第二次跑，是**另一个会话**同一把闸门的产物）：
`kb/l8/workflow_check_CHK-20261004-1316-HLT.json`，`at=2026-10-04 13:17:00`，`verdict=FAIL`，
`failed_legs=['② …','③ …']`，⑥ 的读数 `{"md_total": 6350, "enveloped": 510, "buckets": {"他人产物 hostlib": 510}, "other": []}`
⇒ **`其他` 桶为空、⑥ PASS**，与我的修后跑结论一致。

**关于本轮的第三次跑（`REPAIR-20261004-1318-R9-FINAL`）**：它在 ⑤ 段的 `loader_probe` 上被卡住
（`DSH … loader_probe.mjs` 进程 8 分钟无进展）—— 原因是**并发评测台把主机压满**
（实测 `load averages: 10.48 12.27 12.86`，同时有 8+ 个 `DSH Desktop --profile eval-l0fix` 子进程）。
该次跑**已由我主动终止并清理进程**（不留半成品），未产出 JSON；
**替代证据**＝上面 13:13:30 的修后跑 ＋ 13:17:00 的第三方跑 ＋ 13:16:52 的全工作区信封扫描（扫 3088 / 信封 0 / 退出码 0）。

---

## 2. ★ 本轮唯一的实质修：⑥ 那个信封态 `.md`（原因码 → 修法 → 证据）

### 2.1 失败项与原因码

| 项 | 对象 | 读数（修前） | 原因码 / 修法出处 |
|---|---|---|---|
| ⑥ 文档可见性 | `_eval-L0L7-gap-20261003/kb-l0-feishu-fix/SKILL.md` | **python `os.path.getsize` = 17358 B ／ node `statSync().size` = 21454 B（Δ **4096**）**，node 侧尾部是二进制而非正文 | `kb-repair §2` 表内「**信封态（差值 4096）**」→「用 `cp` 从**无扩展名**临时件重写」 |

`workflow_check.py` 的 ⑥ 判据本体：`add("⑥ …", len(buckets.get("其他", [])) == 0, vis)` ——
即「工作区里除 `kb/.work/hostlib` 之外的 `.md` 不许有 agent 读不了的」；`enveloped()` 用
**node 侧 size ≠ python 侧 size** 定义信封。**这是一条实质判据**（不是基线类），所以按
`gate_red.workflow_check` 的 do 段「其余 7 段红了要真修」处理。

### 2.2 修法（严格照 kb-repair 铁律③的写通道）

```python
# _repair-run-REPAIR-20261004-1307-R9/fix-envelope.py 的核心三步
body = open(TARGET,"rb").read()          # python 读到的就是**去信封后的正文**（17358 B）
open("/tmp/kb-repair-R9-md-tmp","wb").write(body)   # ← 临时件**无扩展名**，故不加信封
subprocess.run(["/bin/cp","/tmp/kb-repair-R9-md-tmp",TARGET])   # ← 用 cp 落到 .md 目标
```

### 2.3 修前/修后读数（零内容改动的证明）

| 读数 | BEFORE | TMP（无扩展名） | AFTER |
|---|---|---|---|
| python size | 17358 | 17358 | 17358 |
| node size | **21454（Δ4096）** | 17358 | **17358（Δ0）** |
| 信封态 | **是** | 否 | 否 |
| 正文 sha256（python 读） | `76f0cfd53ab60f61…` | `76f0cfd53ab60f61…` | `76f0cfd53ab60f61…` |
| node 读到尾部 | 二进制乱码（`_…`） | 正文 `。\n` | 正文 `。\n` |

⇒ **正文一字节未改**（sha 前后一致），只是那 4096 B 的二进制尾被去掉。
原样件已备份：`kb/l7/_backups/kb-repair-workflow-R9-20261004-1313/SKILL.md.before`（17358 B，sha 同上）。

### 2.4 ★★ 新机制发现：⑥ 为什么会反复红（**这不是"库坏了"**）

- 该文件 mtime = **13:10:28**，**晚于**我 13:07:54 的首跑 ⇒ 它是在我跑完之后**又被写了一次**。
- `ps` 实测：**另一个活会话的评测台**正在同一棵树里跑 ——
  `bash -c cd ".../_eval-L0L7-gap-20261003/kb-l0-feishu-fix/evals/_harness"; python3 smoke_fp.py --ids … --round 93 --concurrency 8`
  外加多个 `DSH Desktop … --profile eval-l0fix "<prompt>"` 子进程。
- ⇒ **⑥ 的红/绿挂在那个写者的写通道上**：它用 python 通道写 `.md` ⇒ 红；用 `cp`/node 通道 ⇒ 绿。
  第 5 轮那 3 个信封态（同在 `_eval-L0L7-gap-20261003/` 树下、由另一并发会话在 09:31 修掉）是**同一机制**。
- ⇒ **持久修法不在闸门侧**：要让 ⑥ 稳定绿，得让**那个评测台/写者**改走 cp/node 通道。
  本会话已把当前文件修干净（并留下回滚件），但**如果它再用 python 通道写一次，⑥ 会再次变红** ——
  这不是本次修复的回归，而是活写者的行为。

---

## 3. ②③ 独立复算（**不采信库内既有自述**，四项全部重做）

脚本：`_repair-run-REPAIR-20261004-1307-R9/recompute.py`（只读）→ 读数落
`_repair-run-REPAIR-20261004-1307-R9/01-recompute.json`。

### 3.1 ② 的两条子判据「数学上不可能为真」（独立重算）

| 量 | 实测值 |
|---|---|
| `kb/l3/candidates/rules.jsonl` 现行行数 | **1018** |
| 整文件 sha256 | `743dc62398311b0287e1e99fbcc438397ca8c721a0556d534cc69f3ee6eff840` |
| `lines[:1018]` 前缀 sha256 | `743dc62398311b02…` ⇒ **== 整文件**（True） |
| `lines[:1527]` 前缀 sha256 | `743dc62398311b02…` ⇒ **== 整文件**（True） |
| 基线 A：`kb/.work/l6_integrity.json` 记的 `l3_candidates` | `7d00454e80e2a1cc…`，自报 **lines = 2036**（checked_at 2026-10-02 00:10:57） |
| 基线 B：`kb/l4/runs/20260923-1445.json` 记的 `rules.jsonl` | `aa83d1f98bc86857…`（**1527 行时代**的整文件哈希） |
| 现 sha 在 L3 自己的注册表里 | `kb/l3/registry/l3.json → appended_fields.old_lines_untouched.sha256` == 现 sha（**演进有出处**） |

⇒ 判据拿「**前缀**」比「**别的行数时代的整文件**」：活库 1018 行时两条前缀都等于整文件，
而两条基线是 2036 行 / 1527 行时代的整文件哈希 ⇒ **`structurally_impossible: true`**（不回滚 L3 就不可能为真；
回滚 L3 = 毁掉 2026-10-02 的蒸馏，原因码明令禁止）。
另：l0 / l1 / l2 三棵树与 L5 基线**相符**（`match_L5_baseline` 全 True）⇒ 漂移只在 L3，且 L3 有出处。

### 3.2 ③ 的 20 项 mismatch：来源审计 ＋ 存在性

- 口径：扫 `kb/l*/runs/*.json` ∪ `kb/l*/*/runs/*.json`，**排除 `kb/l8`**，共 **1565 份 run 记录**，只读其 `artifacts[]`。
- 结果：**17/20 有 run 记录出处**（现 sha 被某条 run 记录记过）；**3/20 无落章** =
  `kb/l7/skills/kb-content-review/SKILL.md`、`kb/l7/registry/l7.json`、`kb/l7/skills/kb-content-review/scripts/review.py`
  （三者改动各有文档出处：前两者是 2026-10-03「防线1 入口唯一化」同批，登记在
  `kb/l7/registry/report-output-contract.yaml` 的 `applied_20261003`；l7.json 见 3.3）。
- **存在性实测：20/20 全部存在、缺失 0** ⇒ 判据只报「sha 不符」，与「产物被删」是两回事，本轮把两者分开验过。
- ⇒ 与第 4–8 轮**逐项一致**；**没有一项是"无人认领的黑改"**。

### 3.3 `l7.json` 那一项（③ 里唯一的真发现）

与 pre-edit 备份 `kb/l7/_backups/batch18b-20261002-1201/l7.json.pre-edit` 逐字段比对：
**差异恰好 1 个字段**（`article_no_source.field_lives_in` 的措辞「四个形态文件」→「五个」），
现 sha `b36c86f74d86a0a7…`、自报 `run_id` 仍是 `20260923-1500`、无 run 记录记过现 sha。
⇒ 定性不变：**合法改动 + 流程缺落章**（不是内容损坏）。它的 owner_action 要 **开闸** 跑
`kb/.work/l7_article_source_refresh.py <RUN> --apply` 并补一条 L7 run 记录 —— 本轮**未开闸、未写任何 run 记录**。

---

## 4. 失败项清单（对象 ＋ 原因码 ＋ 分类 ＋ 本轮动作 ＋ 复开条件）

| 失败项 | 原因码 | 分类 | 本轮动作 | 复开条件（可执行判据） |
|---|---|---|---|---|
| ⑥ 文档可见性（`_eval-…/kb-l0-feishu-fix/SKILL.md`，Δ4096） | `kb-repair §2 信封态` | **实质红（已修）** | ✅ cp 通道重写；`envelope_gate` 扫 3080 / 信封 0 / 退出 0；复跑 ⑥ → PASS | 已达成（若活写者再用 python 通道写 ⇒ 按同一修法再修一次） |
| ② 权威库 l0~l6 未被改动（L3 两条子判据 false） | `gate_red.workflow_check` ＋ `workflow-check-known-drift.yaml → stale_criteria[0]` | **判据过期（登记）** | 只登记（第 9 条 repro_runs） | 按选项 (A) 改判据后复跑 exit 0 |
| ③ 前序产物哈希（20 项 mismatch） | `gate_red.workflow_check` ＋ `stale_criteria[1]` | **判据过期（登记）**；其中 l7.json 一项含**流程缺落章** | 只登记 ＋ 来源审计（17/3/0） | 同上；另有 (C) 可补落章但**不会转绿** |

---

## 5. ★ 未决决定（**本单唯一卡点**，已连续 9 轮无人回答）

**问题**：②③ 要转绿只有一条路 —— 按 `stale_criteria[*].owner_action` 改
`kb/l8/workflow_check.py` 的 ②③ 判据（② 改「与当前基线比 + 来源可溯才降级」；③ 改「与**最新**一次
申报的 sha 比 + 来源审计，查不到出处仍判红」）。原因码 `gate_red.workflow_check` 的 `forbidden` 明写这条
**要单独走一轮并报批**。

| 选项 | 效果 | 代价 |
|---|---|---|
| **(A) 授权改判据**（＋同时为那 3 项补落章） | **唯一能让闸门转绿（exit 0）** 的路 | 改 `workflow_check.py` ②③ 两段约 15 行 ＋ 一个**反向测试**（故意原地改一个层产物、不落章 ⇒ 新判据**必须仍判红**）；不动 `kb/l0~l6` 数据 |
| **(C) 只补 3 项落章** | **闸门仍 FAIL**（③ 还剩 17 项、② 两条子判据仍假） | 属数据卫生，不是本次「修完复跑」能收口的路；且补落章要写 `kb/l7/runs/` ＋ `index.jsonl` ⇒ 要独占循环 |
| **(B) 维持现状** | 接受长期 FAIL，每轮只登记 ＋ 修实质红（如本轮 ⑥） | 闸门失去辨别力（恒红 ⇒ 真偷改也看不出来） |

**本会话问不到人**：`ask_user_question` 被宿主拒，原文
「human interaction is unavailable while the calling agent is owned by another live agent」
⇒ **该决定原样带回给委派方**（工具自身的指示也是「include the unresolved question or decision in the
child agent's final result」）。

**另一条并发前提**：`kb_loop_claim.py status` 报「陈旧（可 --take-over）」（BASE `PIPE-20261004-1257`，pid 9157 已不在），
但实测**确有活会话在写**（评测台 8 并发 ＋ `freshness.py` ＋ `roundtrip_check.py`）
⇒ 即便拿到 (A)/(C)，补落章前也要先确认活进程停了，否则是并发双写。

---

## 6. 变更记录（改了哪些文件 ＋ 五问 ＋ 回滚）

| 文件 | 动作 | 说明 |
|---|---|---|
| `_eval-L0L7-gap-20261003/kb-l0-feishu-fix/SKILL.md` | **改**（cp 通道） | 去掉 4096 B 二进制尾；正文 sha 前后一致（零内容改动） |
| `kb/l7/registry/workflow-check-known-drift.yaml` | **改**（edit 工具） | 第 9 轮登记：`last_reverified` / `repro_runs` 第 9 条 / `still_unanswered_at` |
| `kb/l8/workflow_check_REPAIR-20261004-1307-R9.json`、`…REPAIR-20261004-1314-R9-AFTER.json` | **建** | 闸门自身产物（每次跑必写） |
| `_repair-run-REPAIR-20261004-1307-R9/`（`recompute.py` / `fix-envelope.py` / `01–06*.json,txt`） | **建** | 本轮证据（只读复算 ＋ 修复前后读数） |
| `kb/l7/_backups/kb-repair-workflow-R9-20261004-1313/` | **建** | 回滚基线：`SKILL.md.before`、`workflow-check-known-drift.yaml.before`、`workflow_check.py.before`、`BEFORE.sha256` |

**变更协议 5 问**（kb-repair 铁律①）：

- **读者**：跑 `kb-check` 体检档的人 / 看 `workflow_check` 报告的人 / 准备把 ②③ 修绿的人 / 写日报的人。
- **写者**：本轮 kb-repair 会话（第 9 轮）；后续由维护 `kb/l7/registry` 的人按 `owner_action` 更新。
- **判据**：本轮的改动**不改变任何闸门语义** —— 登记文件今天没有任何脚本读它（文件头自述，且
  `grep -rl` 未发现读取者）；修 SKILL.md 只是把"读不了的 md"变成"读得了的 md"，不参与任何判定常量。
- **通道**：`.md` 走 **`cp`（无扩展名临时件）**；`.yaml` 走 edit 工具（都不用 python 直写，防 4096 信封）；
  证据文件走 write 工具/`bash` 重定向，**落地后已用「node size == python size」逐个验过**。
- **回滚**：
  ```bash
  cp kb/l7/_backups/kb-repair-workflow-R9-20261004-1313/SKILL.md.before \
     _eval-L0L7-gap-20261003/kb-l0-feishu-fix/SKILL.md
  cp kb/l7/_backups/kb-repair-workflow-R9-20261004-1313/workflow-check-known-drift.yaml.before \
     kb/l7/registry/workflow-check-known-drift.yaml
  ```

**改后复核**：`skills_check.py` → 五类问题 `1=0 2=0 3=0 4=0 5=0`、退出码 0；
`workflow-check-known-drift.yaml` YAML 可解析（`repro_runs` 现 9 条）；
`envelope_gate.py --reader consumer .` → 扫 3088 / 信封 0 / 退出码 0。

---

## 7. 写盘清单（先声明再跑 —— 本轮全部落在上面 §6，另无其它）

未写：`kb/l0~l6` 任何数据与台账、任何 run 记录、`kb/l7/runs/index.jsonl`、任何锁文件、任何服务配置。
未做：`--apply`、`--write-gate`、`--take-over`、删锁、向飞书发布。

---

## 8. 一句话收口

> **失败项按原因码分两类：⑥ 属"实质红"，本轮已真修并复跑转绿；②③ 属"判据过期"，原因码明文规定
> 不许用改数据的方式修，转绿只能改判据，而改判据要报批 —— 这个决定（A/B/C）已连续 9 轮无人回答，
> 原样带回给委派方。**
