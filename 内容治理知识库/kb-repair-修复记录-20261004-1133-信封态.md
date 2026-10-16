# kb-repair 修复记录 · 2026-10-04 11:28–11:32（信封态）

**用户指令**：「闸门红了，帮我把它修好，改完再跑一遍同样的闸门证明修好了。」

- **库根（cwd）**：`/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理`
- **RUN**：`REPAIR-20261004-1129-ENV`
- **输入（红闸门）**：**信封闸门 ⑤a′**（全工作区口径，判据读者 = DSH 内置 Electron）→ 修前 `退出码 1`
- **输出（同一条闸门）**：**`退出码 0`｜信封态 0｜两读者一致**（§2）
- **纪律**：只修这 4 个文件；未动 `kb/l0…l6` 数据与台账；未加 `--apply`／`--write-gate`；未删任何锁或认领；未改任何判据；未发布任何东西到飞书。

---

## 0. 一句话结论

全工作区扫到 **4 个信封态文件**（4096 字节信封 ⇒ **宿主/消费方读不了**）。
已用 **`/bin/cp` 通道**修好：**只剥信封，正文一字未改**（4 个文件的正文 sha256 与修前逐字节相同，其中 2 个还与 eval 侧**冻结清单**记录的期望 sha 相同）。
⇒ **同一条闸门复跑 `exit 0`**；同一批文件造成的 **门④ 第 ⑥ 段「文档可见性」也同轮由 FAIL 转 PASS**。

**门④ 剩下的 ②③、门③、门⑥、CI/八层闸门的 L0** **不是「没修」**：
分别是**已登记的判据过期（合法变红，不许修）**、**缺规范输入**、**修法被 failure-playbook 明文禁止照跑**、**要人重新授权** —— 逐条见 §5。

---

## 1. 闸门红在哪（修前读数）

### 1.1 三种扫法，只有一种能看见这批（覆盖面不可互替）

| 扫法 | 命令（cwd = 库根） | 修前退出码 | 修前读数 |
|---|---|---|---|
| **⑤a′ 全工作区**（**本次的红**） | `python3 tools/envelope_gate.py --reader consumer .` | **1** | 扫 **2782** 个 `.py/.txt/.md`｜正常 **2778**｜**信封态 4**｜读不到 0｜**两读者不一致 ⇒ 报红** |
| ⑤a 默认范围 | `python3 tools/envelope_gate.py` | 0 | 该范围 = `kb/l0…l8`、`kb/.work`、`kb/view`、`kb/versions`、`tools`、`_eval-kb-manage` ⇒ **不含** `_eval-*` / `_chk-run-*`，**看不见这 4 个** |
| ⑤b 库自带普查 | `sh kb/kbpy l8/envelope_census.py` | 0 | 只扫 `kb/` 内、只扫 `.md` ⇒ **同样看不见** |

★ **口径红线**：`--reader` 取 **消费方（DSH 内置 Electron）** 才是判据读者。同一命令下的 PATH `node` 只判出 **2** 个
（两个 `.md` 被判绿）⇒ **用 PATH 读者会得到「假绿」**。

### 1.2 4 个信封态文件（判据：同一路径 `python getsize` 与消费方 `node statSync().size` 差 ±4096）

| # | 文件 | python（真值） | node（消费方） | 差 | mtime |
|---|---|---|---|---|---|
| 1 | `_chk-run-PIPE-GATE-20261004-0200/00-index-before.txt` | 9 | 4105 | −4096 | 02:02 |
| 2 | `_chk-run-PIPE-GATE-20261004-0200/09-index-after.txt` | 9 | 4105 | −4096 | 02:04 |
| 3 | `_eval-L0L7-gap-20261003/kb-l0-feishu-fix/SKILL.md` | 17284 | 21380 | −4096 | **10:28** |
| 4 | `_eval-L0L7-gap-20261003/kb-l0-feishu-fix/references/CHANGELOG.md` | 20520 | 24616 | −4096 | **10:34** |

- 信封的**形状**（本会话实测）：真值正文在**前**，4096 字节二进制**尾块**在后（`dd skip=9` 实测首 8 字节为 `300b 4e07 4bfd 7efd`），
  **不是** 10:03 那单遇到过的 NUL 前缀形态。⇒ 「信封是不是 NUL 填充」不能当判据，**只有两读者差值才是**。
- **宿主 `read` 工具实测（判据读者本人）**：修前打开 1 与 3 **直接返回 `binary file`**（读不了）—— 不是理论口径，是可复现的实测。

### 1.3 同一批文件同时也是**门④ 第 ⑥ 段**的失败源（他会话同分钟读数，非本会话）

| 来源 | 读数 |
|---|---|
| `kb/l8/workflow_check_CHK-20261004-1122-WFP.json`（11:22）、`-1124`（11:26）、`-1121-IND`（11:25） | 裁决 `FAIL`；第 ⑥ 段 FAIL，`buckets {'其他': 2, '他人产物 hostlib': 510}`，`other` = 本单修的**那 2 个 `.md`** |

> 「他人产物 hostlib」510 个是判据本就容忍的桶；**唯一进「其他」桶的 2 个就是本单要修的**。

---

## 2. 修前 / 修后对照（**同一条闸门**，贴命令与退出码）

| | 命令 | 退出码 | 读数 |
|---|---|---|---|
| **修前** | `python3 tools/envelope_gate.py --reader consumer .` | **1** | 扫 2782｜正常 2778｜**信封态 4**｜两读者**不一致**（PATH 只判出 2 ⇒ 假绿） |
| **修后** | **同上，逐字同一条命令** | **0** | 扫 2791｜正常 **2791**｜**信封态 0**｜两读者**一致**｜`结论：活路径上没有信封。` |
| 修前 | `python3 tools/envelope_gate.py`（默认范围） | 【本会话未跑】 | 该范围**结构上不含** `_eval-*` / `_chk-run-*` ⇒ 与本单红项无关（他会话同时段读数 1964–1967、0 信封） |
| 修后 | 同上 | 0 | 扫 **1974**｜正常 1974｜**0 信封**【本会话实测】 |
| 修前 | `sh kb/kbpy l8/envelope_census.py` | 【引用】他会话 11:2x 读数 0 | 10373–10376 md，1079 node 侧读不到，**全部已分类**（569 归档＋510 可再生备份）⇒ `OK` |
| 修后 | 同上 | 0 | 扫 **10383** md，1079 已分类，结论 `OK`【本会话实测】 |
| 修前 | `sh kb/kbpy l8/workflow_check.py <RUN>` | 1 | 他会话读数：FAIL **②③⑥**，`其他` 桶 **2** |
| 修后 | `sh kb/kbpy l8/workflow_check.py REPAIR-20261004-1129-ENV` | 1 | FAIL **只剩 ②③**；**⑥ 已 PASS**；`可见性：工作区 6262 md，不可读 510 {'他人产物 hostlib': 510}`（**「其他」桶归零**） |

> 扫描总数在活库上会动（2778 → 2791）：跑闸门期间有 ≥13 路他会话在写同一工作区（§7）。
> 变动的是**总数**，不是判据；两读者的差值判据不受影响。

修后门④逐段原文：

```
知识库工作流体检 · REPAIR-20261004-1129-ENV · 2026-10-04 11:29:54
  PASS  ① 环境与版本纪律
  FAIL  ② 权威库 l0~l6 未被改动          ← 已登记的判据过期，合法变红（本单未动）
  FAIL  ③ 前序产物哈希（45 项）          ← 同上
  PASS  ④ 分层库 → 生成器 → 视图
  PASS  ⑤ 装载位 → 加载器（读工具+体检）
  PASS  ⑥ 文档可见性（agent 能否读到）   ← 本轮由红转绿
  PASS  ⑦ 消费侧 skill 可用
  PASS  ⑧ 工作台与服务
  PASS  ⑨ 写入侧（ingest 闸门 + 落盘通道）
  可见性：工作区 6262 md，不可读 510 {'他人产物 hostlib': 510}
  裁决：FAIL（未过：['② 权威库 l0~l6 未被改动', '③ 前序产物哈希（45 项）']）
```

---

## 3. 变更记录

### 3.1 改动的文件（**4 个**）+ 写入通道

| # | 目标文件 | 写入通道 | 修后真值 sha256（前 16） |
|---|---|---|---|
| 1 | `_chk-run-PIPE-GATE-20261004-0200/00-index-before.txt` | `/bin/cp` 自本单回滚基线 | `de1b743401901520` |
| 2 | `_chk-run-PIPE-GATE-20261004-0200/09-index-after.txt` | `/bin/cp` 自本单回滚基线 | `89cc8d40a0641f6f` |
| 3 | `_eval-L0L7-gap-20261003/kb-l0-feishu-fix/SKILL.md` | `/bin/cp` 自**冻结副本** `_mount-l0fix/kb-l0-feishu/SKILL.md` | `9fea4e8e6f7a92a5` |
| 4 | `_eval-L0L7-gap-20261003/kb-l0-feishu-fix/references/CHANGELOG.md` | `/bin/cp` 自**冻结副本** `_mount-l0fix/kb-l0-feishu/references/CHANGELOG.md` | `ac10cc38966bc2e8` |

**全程没有用 python 直写目标文件**（python 直写会再落成信封；本单只用 `cp` 通道）。

### 3.2 正文有没有被改：**没有**（三重互证）

1. **修前 python 真值 sha == 修后 sha**：`de1b7434…`／`89cc8d40…`／`9fea4e8e…`／`ac10cc38…` 四项修前修后逐字节相同。
2. **与冻结清单互证（独立来源）**：`_eval-L0L7-gap-20261003/_mount-l0fix/freeze-manifest.json`
   记的期望 sha 正是 `SKILL.md=9fea4e8e6f7a92a5d110d11c85bdbf74a7988f26ad2ef2bf048b7f621c8d8ab1`、
   `references/CHANGELOG.md=ac10cc38966bc2e84603d2d948eb8548a4b502be27e32eac72ad17bbb2ea6591` ⇒ 本次只**剥信封**。
3. **读者矩阵**（同一文件，修前 → 修后）：

| 读者 | 修前（`SKILL.md`） | 修后 |
|---|---|---|
| python `getsize` / `read` | 17284 ｜ sha `9fea4e8e…` | 17284 ｜ sha `9fea4e8e…` |
| node（**消费方/Electron**） | **21380** | 17284 |
| 宿主 `read` 工具（判据读者本人） | **`binary file`（读不了）** | **正常读出 221 行** |
| NUL 计数（python 侧） | 0 | 0 |

### 3.3 变更协议 5 问

| # | 问题 | 答案 |
|---|---|---|
| 1 | **读者**（谁读它） | 判据读者 = DSH 内置 Electron（消费方）；闸门 = `tools/envelope_gate.py`（全工作区档）、`kb/l8/workflow_check.py` 第 ⑥ 段；#3/#4 另被 `_eval-L0L7-gap-20261003` 的评测会话与冻结清单读取 |
| 2 | **写者**（谁写它） | **不是库内脚本**：`grep -rn 'kb-l0-feishu-fix' --include='*.py' --include='*.sh'` 命中的都是 eval harness 的**报告脚本**（只读目标）。真正写下这 4 个文件的是**另一路写入方**（#3/#4 mtime 10:28/10:34，落在 `_eval-L0L7-gap-20261003/` 内）—— 见 §6 |
| 3 | **判据**（怎么算修好） | ① `python3 tools/envelope_gate.py --reader consumer .` ⇒ **退出码 0 且信封态 0、两读者一致**；② 门④ 第 ⑥ 段 `其他 == 0`（已复跑证实）；③ 宿主 `read` 能读出正文 |
| 4 | **通道**（用什么写） | **`/bin/cp`**（安全通道）。未用 python 直写目标，也未用「python 生成 → cp」的迂回（源本身就是干净真值） |
| 5 | **回滚** | 见 §4（`kb/l7/_backups/kb-repair-envelope-20261004-1129/`） |

---

## 4. 回滚

- **回滚基线目录**：`kb/l7/_backups/kb-repair-envelope-20261004-1129/`（4 个 `.before` 件，后缀刻意不用 `.md/.txt`，以免自己被信封闸门扫到）
- **回滚命令**（逐条，`/bin/cp <基线> <目标>`）：

```bash
cd "/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理"
BK="kb/l7/_backups/kb-repair-envelope-20261004-1129"
/bin/cp "$BK/_chk-run-PIPE-GATE-20261004-0200_00-index-before.txt.before"   "_chk-run-PIPE-GATE-20261004-0200/00-index-before.txt"
/bin/cp "$BK/_chk-run-PIPE-GATE-20261004-0200_09-index-after.txt.before"    "_chk-run-PIPE-GATE-20261004-0200/09-index-after.txt"
/bin/cp "$BK/_eval-L0L7-gap-20261003_kb-l0-feishu-fix_SKILL.md.before"      "_eval-L0L7-gap-20261003/kb-l0-feishu-fix/SKILL.md"
/bin/cp "$BK/_eval-L0L7-gap-20261003_kb-l0-feishu-fix_references_CHANGELOG.md.before" "_eval-L0L7-gap-20261003/kb-l0-feishu-fix/references/CHANGELOG.md"
```

★ **必须写明的口径**：`cp` 读到的就是**去信封的内容真值**，所以基线里存的是**内容**（9 / 9 / 17284 / 20520 字节），
**不是**带 4096 字节信封的原始字节流。**信封是写入通道的产物，回滚它没有意义也不该回滚**（回了等于把宿主读不了的状态再装回去）。
原始尺寸对已留档：`4105/9`、`4105/9`、`21380/17284`、`24616/20520`。

---

## 5. 本单**未动**的红 —— 逐条给理由，不许读成「全都修好了」

> **来源标注**：本单**亲跑**的是信封闸门（§1、§2）与门④ 修后复跑。下表门③／门⑥／门④ 修前／CI-l0 的读数取自
> **11:22–11:26 同时段他会话的体检产物**【引用】：`kb/l7/reports/CHK-20261004-1122-WFP-health.md`、
> `CHK-20261004-1124-health.md`、`CHK-20261004-1121-IND-health.md`、`kb/l8/workflow_check_CHK-20261004-112*.json`。本单**未**重跑这几道（理由即下表右列）。

| 项 | 读数 | 为什么本单不修 |
|---|---|---|
| **门③** `routes_reconcile` | 规范输入档 `exit 2`（`kb/l7/reports/` 下无 `*-routes-winners.json`，**全库无生成者**）；喂 `_eval-kb-manage/results_alias/routes-winners_20261004-0327-SUB.txt --alias` ⇒ `exit 1`、**60/65**、5 条**全部**落 `brand-ai-provenance-rights-review` | 缺输入属**判据设计**（不得报绿、也不得静默按「全不一致」跑）；5 条不符**已登记**在 `kb/l7/registry/routes.yaml` 的 `known_conflict`，且处置结论明文是「**不再调 description**」；要今日读数须按 `kb-manage` 跑 **65 条 × 3 轮**触发电测 ⇒ **交 kb-manage / 人**，不在读改写范围内 |
| **门⑥** `projection_reconcile` | `exit 1`、**3/6**（❌R1 `source_sha256`、❌R2 509 条、❌R4 2036 处治理字段） | 工具自带的修法「重跑 `gen-host-library.py` 回填」**被 `failure-playbook.yaml` 明文禁止照跑**：视图 `kb/view` 里那 2036 处**带着 2026-09-29 回填的真实分档值**（365×21／90×22／180×466），而**权威侧现在是空的** ⇒ 照提示重生会把**逐条值降级成统一常量**。属**报批动作**，不是修 |
| **门④ ②③** | `FAIL ② 权威库 l0~l6 未被改动`｜`FAIL ③ 前序产物哈希（45 项）` | 已登记于 `kb/l7/registry/workflow-check-known-drift.yaml`：**判据锚在一个已过去的时点**（合法变红，登记**不给豁免**，复跑必然 FAIL）。改判据要**单独走一轮并报批** ⇒ **不许「修」** |
| **CI `l0` 闸门 / 八层闸门 L0** | `exit 1`（红 2） | **取数身份失效**：要**人**重新登录/授权飞书侧，不是代码或数据缺陷 |
| **宿主尺子 `kb_check`** | 健康分 79.2（未熔断）；错误 **454 × E026**（长度维度为主）；告警 2218 × W020 ＋ 10 × W021；孤岛率 0.94 | 工具自注「**机器只报疑似，判归人**」⇒ 交人裁，本单不裁 |

---

## 6. 机制：信封是谁写出来的？（本会话实测；**仍未落到「可改的代码」**）

1. **不是库内脚本**：全工作区 `grep -rn 'kb-l0-feishu-fix' --include='*.py' --include='*.sh'` 命中的只有 eval harness 的**报告/自检脚本**
   （`build_process_html.py`、`selfcheck15.py`、`make_yaml.py`、`finish_a.sh`），它们**不写**这 2 个 `.md`。
2. **不是本会话的写通道**：本会话在工作区内做了**写通道探针**（`_probe-env-20261004-1133/`，6 个文件，测完已删），
   四条通道 **python 直写 `.txt`／python 直写无扩展名／shell 重定向／`cp`** 全部 `python == stat`、**信封 0**
   ⇒ 在这个会话里怎么用 python 写都**写不出信封**。
3. **结论（推测，标注为推测）**：信封来自**另一路写入方**（10:28 / 10:34 在 `_eval-L0L7-gap-20261003/` 内改 `SKILL.md` 与 `CHANGELOG.md` 的那个会话/工具链）
   的通道特征。**成立条件**：那一路的写工具与我的写工具不是同一实现。**什么会推翻它**：若在别的会话里复现出同样 4 条通道产生信封，则说明是**目录/策略级**差异而非会话级。
4. ⇒ **本单只能修状态，修不了那条通道**（它不是库内脚本、不在本会话可改的代码里）。
   复发条件与责任方在此登记：**同一目录再被那一路写一次，还会再红**（09:49 → 10:28 → 10:34 已复发两轮）。

---

## 7. 并发与边界（不说会读过头）

1. **并发披露（实测）**：跑闸门期间 `ps` 实测同时有别的会话在跑 `tools/envelope_gate.py`、`l8/envelope_census.py`、
   `l8/projection_reconcile.py`、`l7/scripts/routes_reconcile.py`；`kb/l7/runs/`、`kb/l8/`、`kb/.work/l5_integrity.json` 同期有新落盘。
   本会话**未认领循环、未删任何锁/认领文件、未接手任何会话**；`.kb.lock` 与认领文件本会话**均未创建也未删除**。
2. **本会话写盘清单（全部先声明）**：
   - 4 个被修文件（§3.1）；
   - `kb/l7/_backups/kb-repair-envelope-20261004-1129/**`（回滚基线 4 件）；
   - `_repair-run-REPAIR-20261004-1129-ENV/**`（8 个原始留底，逐条可回放）；
   - `kb/l8/workflow_check_REPAIR-20261004-1129-ENV.json`（**门④ 无干跑档，跑它即写盘**，已在 §2 声明）；
   - 本记录（工作区根 ＋ 留底目录各一份）。
   **其余零写盘**：未动 `kb/l0…l6`、未动任何 registry、未发布任何东西到飞书。
3. **本记录自身的信封自证**：修后全工作区扫描（**2791 个文件，含本记录**）信封态 **0** ⇒ 本记录不是信封态。
4. **"全库通过"类结论本单不给**：本单只证明**信封闸门这一条**转绿（＋门④ 第 ⑥ 段）。
