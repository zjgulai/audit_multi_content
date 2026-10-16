# workflow_check 失败项 · 按原因码处置记录（2026-10-04 · kb-repair）

- **库根**：`/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理`（cwd = 库根）
- **闸门**：`kb/l8/workflow_check.py`（9 段；**无干跑档**，跑一次写一份 `kb/l8/workflow_check_<RUN>.json`）
- **触发**：用户「workflow_check 没过，帮我把失败项按原因码修掉，修完复跑」

## 0. 一句话结论

本轮 3 段红，**只有 1 段是真坏、已真修**：

| 段 | 现象 | 原因码 | 本轮 |
|---|---|---|---|
| **⑥ 文档可见性** | 2 个 `.md` 为**信封态**（宿主读不到） | **真坏**（本次新出现，非历史漂移） | ✅ **已真修 → 复跑转绿** |
| ② 权威库 l0~l6 未被改动 | `l3_base1018_matches_L6` / `l3_whole1527_matches_L4` 假 | `gate_red.workflow_check` → **判据过期（合法变红）** | ⛔ 按已登记口径**不改**（见 §4） |
| ③ 前序产物哈希（45 项） | 20 项 mismatch | 同上（+ 1 条真发现） | ⛔ 同上 |

> **为什么没有"全部修绿"**：本库 `kb/l7/registry/failure-playbook.yaml → gate_red.workflow_check` 对 ②③ 明写
> `forbidden`：「**不许把 ②③ 的判据就地改宽而不同时报批（改判据要单独走一轮）**」，且该条 `do` 写
> 「先看是不是**只有** ②③ 红（**其余 7 段是实质判据，红了要真修**）」。
> 本轮正是照这条办：⑥ 是实质判据 ⇒ 真修；②③ 是已登记判据漂移 ⇒ 只登记、不动。

---

## 1. 修前 / 修后对照（同一条闸门，贴命令与退出码）

| 时点 | RUN | 命令 | 退出码 | 未过 |
|---|---|---|---|---|
| 修前（本轮复现） | `20261004-0223` | `sh kb/kbpy l8/workflow_check.py` | **1** | ②③**⑥** |
| **修后（本轮交付）** | `REPAIR-AFTER-20261004-0232` | `sh kb/kbpy l8/workflow_check.py REPAIR-AFTER-20261004-0232` | **1** | ②③ |
| 修后确认（本记录落盘后再跑） | `REPAIR-FINAL-20261004-0234` | 同上（换 RUN） | **1** | ②③ |

> `REPAIR-FINAL` 这一跑是为了证明**本记录自身（一个新增 `.md`）没有把 ⑥ 重新弄红**：
> 它实测 `不可读 510 {'他人产物 hostlib': 510}`，`其他` 仍为 0 ⇒ ⑥ 稳定 PASS。
> （本记录用 `write` 工具落盘，实测 `python getsize = 宿主 statSync = 13519` ⇒ 明文，非信封态。）

```
修前：FAIL ② · FAIL ③ · FAIL ⑥      可见性：工作区 6088 md，不可读 512 {'其他': 2, '他人产物 hostlib': 510}
修后：FAIL ② · FAIL ③ · PASS ⑥      可见性：工作区 6091 md，不可读 510 {'他人产物 hostlib': 510}
```

**⑥ 的转绿是本轮唯一的判定变化**：`其他` 桶 `2 → 0`（判据是 `len(buckets["其他"]) == 0`，`workflow_check.py:188`）。
`他人产物 hostlib` 那 510 个是**他人产物**，判据**本就容忍**（`workflow_check.py:182`），不在修的范围。

### ②③ 的读数「修前=修后」逐字节相同（这是本轮**没偷改**的证据）

对 `REPAIR-AFTER-20261004-0153`（上一轮）与 `REPAIR-AFTER-20261004-0232`（本轮）两份 JSON 的
`legs[②].detail` 与 `legs[③].detail` 做 `json.dumps(sort_keys=True)` 比对：**`identical: True`**（两段都是）。
⇒ 我的修复**没有**触碰任何数据与判据。

---

## 2. ⑥ 的失败项定性（原因码 = 信封态）

`workflow_check.py:66-68` 的判据：同一路径 `node statSync().size` ≠ `python os.path.getsize()` ⇒ 信封态。
实测两文件差值**恰为 4096**：

| 文件 | python 读数 | 宿主（Electron `statSync`）读数 | 差值 |
|---|---|---|---|
| `_eval-L0L7-gap-20261003/kb-recall/evals/_eval/STATE.md` | 4866 | **8962** | **+4096** |
| `kb/l7/_backups/install-slot-stray-20261004-022013/install-slot-kb-check/.doctor-backup/doctor-report-20261004-014750.md` | 844 | **4940** | **+4096** |

### 2.1 根因（本轮实测复现，不是推断）

**workspace 内用 python 写文本文件会带 4096 字节信封**；`cp` / bash 重定向 / node 写盘**不带**：

```
python 写 10000 B  → python getsize=10000  宿主 statSync=14096   ENVELOPED +4096
cp 转发同一份      → python getsize=10000  宿主 statSync=10000   plain ✓
bash 重定向        → python getsize=10000  宿主 statSync=10000   plain ✓
```

结构：**正文在前，尾部多出 4096 字节包裹**（`python open().read()` 透明剥掉、`stat`/宿主看得见）。
⇒ 与 `~/.dsh/AGENTS.md`「python 落盘会带 4096 字节信封，宿主读不了」完全一致。

> 注：24 B 的小文件实测**不触发**，10000 B 触发。阈值本轮未细测，**不作为结论**，只说「大文件会触发」这一实测事实。

### 2.2 为什么是「真修」而不是删掉

两个文件都不是垃圾，**都不能删**：

1. `STATE.md` = 一次 `kb-recall` 评测的**断点续跑状态**（活跃记录）。
2. `doctor-report-…md` = 上一次 kb-repair 把装位里多出来的 doctor 产物**移出装载位时的回滚基线**
   —— 该目录自带 `README.revert.txt`，删了就等于**毁掉那次修复的回滚点**。

所以正确修法是 **kb-repair §2 的既有口径：`信封态（差值 4096）→ 用 `cp` 从无扩展名临时件重写`**，
**保内容、只去包裹**。

### 2.3 修法与完整性核对（内容零改动）

```bash
F1="./_eval-L0L7-gap-20261003/kb-recall/evals/_eval/STATE.md"
F2="./kb/l7/_backups/install-slot-stray-20261004-022013/install-slot-kb-check/.doctor-backup/doctor-report-20261004-014750.md"
cp "$F1" /tmp/kbfix_1.bin && cp /tmp/kbfix_1.bin "$F1"     # 读到的本就是明文 ⇒ 回写即为明文
cp "$F2" /tmp/kbfix_2.bin && cp /tmp/kbfix_2.bin "$F2"
chmod 600 "$F1"; chmod 644 "$F2"                            # 还原原权限
```

**先建了完整性判据再动手**：`README.revert.txt` 里记着 `doctor-report` 的
sha256 = `329bae486af8a0e6d1009d3450c9dfd98cb8e3f3417aa8cd53bf3110aaff32df`；
改前 `cp` 出来的明文 sha 与之**逐字相同** ⇒ 证明「信封是**写路径包裹**，不是内容损坏」。

改后复核（三读者）：

| 检查 | 结果 |
|---|---|
| python `getsize` vs 宿主 `statSync` | `4866=4866`、`844=844` ⇒ **PLAIN ✓** |
| 内容 sha256（改前 / 改后） | `a2ba1407…` / `329bae48…` **均未变** |
| 宿主 `readFileSync` 可读性 | `NUL=0`，首行/末行均为正常中文正文 ⇒ **宿主读得到** |
| 权限 | `600` / `644` 与改前一致 |

---

## 3. 本轮改了什么（变更记录 + 五问 + 回滚）

| # | 文件 | 动作 | 五问（kb-repair 铁律①） |
|---|---|---|---|
| 1 | `_eval-L0L7-gap-20261003/kb-recall/evals/_eval/STATE.md` | 去信封（`cp` 回写，内容 sha 不变） | **读者**=跑该评测的人 / 宿主 `readFileSync`（原读不到）；**写者**=该评测会话；**判据**=`workflow_check.py:66-68` 的 `node==python` 比大小，改后 4866=4866 转绿；**通道**=`cp`（无信封），**未**走 python 直写；**回滚**=`cp kb/l7/_backups/kb-repair-workflow-envelope-20261004-0230/STATE.md "$F1"` |
| 2 | `kb/l7/_backups/install-slot-stray-20261004-022013/install-slot-kb-check/.doctor-backup/doctor-report-20261004-014750.md` | 同上（内容 sha 仍 `329bae48…`） | **读者**=复核那次装位清理的人（`README.revert.txt` 的回滚基线）；**写者**=root-skills-doctor；**判据**=同上，改后 844=844 转绿；**通道**=`cp`；**回滚**=`cp kb/l7/_backups/kb-repair-workflow-envelope-20261004-0230/doctor-report-20261004-014750.md "$F2" && chmod 644 "$F2"` |
| 3 | `kb/l7/_backups/kb-repair-workflow-envelope-20261004-0230/` | **新建**（回滚基线） | 上述两份**明文副本** + 本记录；sha 见 §2.3 |
| 4 | `kb/l8/workflow_check_20261004-0223.json`、`…_REPAIR-AFTER-20261004-0232.json` | 新增（**闸门自己写的**） | 该脚本无干跑档，跑即写盘（`kb-check §1` 已声明） |
| 5 | 本文件 | 新增 | 交付记录 |

**回滚基线提示（如实披露）**：`cp` 读取信封态文件时**本就透明剥掉包裹**，所以基线副本是**明文**（4866 / 844），
**不是**原封的「明文+4096」状态。这是**有意**的：值得回滚的是**内容**，而信封态本身正是要修掉的缺陷态。
内容 sha 与 `README.revert.txt` 记的值一致（§2.3）⇒ 回滚可逐字验证。

**改完按 kb-repair §5 复核**（本节动过 `kb/l7/_backups/`，故把三条旁证闸门都跑了）：

| 闸门 | 结果 |
|---|---|
| `sh kb/kbpy l7/scripts/skills_check.py` | **exit 0**，五类 `1=0 2=0 3=0 4=0 5=0` |
| `sh kb/kbpy l7/scripts/layers_check.py` | **exit 0**，六类 `1..6 = 0` |
| `python3 tools/envelope_gate.py` | **exit 0**：`正常 1889 ｜ 信封态 0 ｜ 读不到 0` |

---

## 4. ②③ 为什么没修（按已登记原因码，逐条给依据）

依据取自本库**登记在案**的 `kb/l7/registry/failure-playbook.yaml → gate_red.workflow_check`
与 `kb/l7/registry/workflow-check-known-drift.yaml`。三种红的口径取自 `kb-check §3`。

| # | 失败项 | 原因码 | 定性 | 依据（可复算） |
|---|---|---|---|---|
| 1 | `② l3_base1018_matches_L6` | 判据过期 | **合法变红** | `workflow_check.py:112-125` 拿**前缀**哈希去比**整文件**哈希；基线 `kb/.work/l6_integrity.json` 自报 `lines=2036`，活库现 **1018 行** ⇒ 「前 1018 行」**就是整个文件**，结构上不可能相等 |
| 2 | `② l3_whole1527_matches_L4` | 判据过期 | **合法变红** | 基线取自 `kb/l4/runs/20260923-1445.json`（**1527 行时代**）；活库 1018 行 ⇒ 「前 1527 行」= 整文件，恒 false。要它变真只有「把 L3 回滚到 09-23」—— **明令禁止** |
| 3 | `③` 45 项里 20 项 mismatch | 判据过期（+1 真发现） | **合法变红** | `workflow_check.py:128-137` 把 **2026-09-23 四份历史 run 记录**当「当前基线」；09-23 之后各层合法重建过 ⇒ 产物哈希**必然**变。上一轮已独立复算：17 项有更新来源、**3 项哈希级无落章** |

**与上一轮（`workflow_check-修复记录-20261004-0153.md`）逐项一致**（本轮 §1 已证读数逐字节相同）
⇒ 这是**稳定的判据常量**，不是抖动。

**真发现（③ 不是全假红，仍然挂着，未处理）**：`kb/l7/registry/l7.json` 原地改写未落章
（mtime 2026-10-02、自报 `run_id` 仍是 `20260923-1500`、无任何 run 记录记过现 sha）。
处置需 `kb/.work/l7_article_source_refresh.py <RUN> --apply` + 补一条 L7 run 记录 ——
**属写 `kb/l7` 登记面、要开闸且须独占**，kb-repair 本轮**不做**。

**要 ②③ 真变绿**：只能**单独走一轮「改判据」**（改 `kb/l8/workflow_check.py`，**不是**登记文件），
且改完必须做**反向测试**证明它仍能抓到「未落章改写」那类真漂移。**需要你点头**。

---

## 5. 复盘：⑥ 为什么会红，以及会不会再红

- **直接原因**：两个 `.md` 都是**python 进程**写进 workspace 的（`STATE.md` 由评测会话写；
  `doctor-report` 由 `root-skills-doctor` 的 `skill-doctor.py` 写）。python 写盘 → +4096 包裹 → ⑥ 红。
- **⚠️ 会复发**：只要还有脚本用 python 往 workspace 写 `.md`，⑥ 就会**再次变红**。
  同一形态在本库已**复发过一次**：`install-slot-stray-20261004-013655`（00:23）→ `…-022013`（02:20），
  该目录的 `README.revert.txt` 自己写着「**这是第 2 次复发**」。
- **建议（本轮不做，属独立一轮）**：要么让写 `.md` 的脚本改走 `node`/`cp` 通道，
  要么在 `envelope_gate.py` 上挂一个**去信封修复档**。**这属机制改动，不该由本轮的"修失败项"顺手做掉。**

---

## 6. 并发与适用边界（如实披露）

- 本轮跑闸门时**库内有另一个会话在活动**：`kb/.work/.kb-loop-claim.json` 写着
  `base=20261004-0220`、`at=2026-10-04T02:20:57`、`ttl=45min`，且 `ps -p 69685` 显示**该 pid 已不在**；
  另有 pid `71429` 正在跑「等宽限到 02:25:57 再 `--take-over`」的接管动作。
  **我不抢认领、不跑任何层引擎、不写 `kb/l7/runs/index.jsonl`**；本轮只改 §3 那两个 `.md` + 建回滚基线 + 本记录。
- **并发旁证**（说明 ⑥ 的 `md_total` 从 6088 涨到 6091 不是我造成的）：三次读数
  `6088（0223）→ 6089（我手工盘点）→ 6091（0232）`，**活库在被别的会话推着长**。
  但 **⑥ 的 `其他` 桶 `2 → 0` 是我的修复**，②③ 逐字节未变 ⇒ 结论不被并发影响。
- **本记录只是 `workflow_check` 这一条闸门**，**不等于知识库体检全过**：同期的体检表
  （如 `体检表-20261004-0212-六道闸门.md`）另记 **⑥ 投影一致性**、**⑦ 层闸门 L0**、**③ 路由表对账** 等问题，
  要"全绿"得逐条排期。

---

## 7. 复算命令（只读，任何人可重跑）

```bash
cd "/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理"

# ⑥ 现状：应 PASS，且 其他=0
sh kb/kbpy l8/workflow_check.py <RUN>                       ; echo $?

# 两个文件是否已非信封态（两个数应相等）
python3 -c "import os;print(os.path.getsize('./_eval-L0L7-gap-20261003/kb-recall/evals/_eval/STATE.md'))"
ELECTRON_RUN_AS_NODE=1 "/Applications/DSH Desktop.app.pre-lute-20260907-111753/Contents/MacOS/DSH Desktop" \
  -e 'console.log(require("fs").statSync("./_eval-L0L7-gap-20261003/kb-recall/evals/_eval/STATE.md").size)'

# 内容 sha 应与改前一致 / 与 README.revert.txt 一致
shasum -a 256 "./kb/l7/_backups/install-slot-stray-20261004-022013/install-slot-kb-check/.doctor-backup/doctor-report-20261004-014750.md"
# 期望 329bae486af8a0e6d1009d3450c9dfd98cb8e3f3417aa8cd53bf3110aaff32df

# 旁证闸门
sh kb/kbpy l7/scripts/skills_check.py ; sh kb/kbpy l7/scripts/layers_check.py ; python3 tools/envelope_gate.py
```
