# kb-repair 变更记录 ｜ 信封态让闸门红 · RUN REPAIR-20261003-2345

- **输入（已红的闸门）**：`kb/kbpy l8/workflow_check.py <RUN>` 腿⑥「文档可见性（agent 能否读到）」
- **修的人**：DSH agent（kb-repair）；**只报不改的对照档**是 `kb-check`
- **时间**：2026-10-03 23:41–23:46（CST）
- **库根（cwd）**：`/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理`
- **回滚基线**：`kb/l7/_backups/kb-repair-envelope-ci-20261003-234259/`（原件两份 + 修前闸门产物）
- **未触碰**：`kb/l0…l6` 任何数据与台账；未入库；未加 `--apply`；未动任何登记表 / 层契约 / 路由表

---

## 1. 修前 / 修后：**同一条闸门**的对照

命令（两次完全相同，只有 RUN 不同以免产物互相覆盖）：

```bash
sh kb/kbpy l8/workflow_check.py REPAIR-PREFIX-20261003-2345   # 修前
sh kb/kbpy l8/workflow_check.py REPAIR-AFTER-20261003-2345    # 修后
```

| 腿 | 修前 | 修后 |
|---|---|---|
| ① 环境与版本纪律 | PASS | PASS |
| ② 权威库 l0~l6 未被改动 | **FAIL**（未修，见 §5） | **FAIL**（同前） |
| ③ 前序产物哈希（45 项） | **FAIL**（未修，见 §5） | **FAIL**（同前） |
| ④ 分层库 → 生成器 → 视图 | PASS | PASS |
| ⑤ 装载位 → 加载器 | PASS | PASS |
| **⑥ 文档可见性（agent 能否读到）** | **FAIL** | **PASS** ✅ |
| ⑦ 消费侧 skill 可用 | PASS | PASS |
| ⑧ 工作台与服务 | PASS | PASS |
| ⑨ 写入侧 | PASS | PASS |
| 退出码 | **1** | **1**（红只剩 ②③） |

腿⑥ 的原始判据值（逐字取自两次落盘的 `kb/l8/workflow_check_<RUN>.json`）：

```json
修前: {"md_total": 4952, "enveloped": 511, "buckets": {"他人产物 hostlib": 510, "其他": 1},
       "other": ["./ci/out/gates-latest.md"]}
修后: {"md_total": 4957, "enveloped": 510, "buckets": {"他人产物 hostlib": 510}, "other": []}
```

第三次跑（**最终态**，含本记录文件本身，`REPAIR-FINAL-20261003-2346`）：腿⑥ 仍 **PASS**，
`{"md_total": 4958, "enveloped": 510, "buckets": {"他人产物 hostlib": 510}}`（`其他` 桶空），
退出码 1（红仍只剩 ②③）—— 即 **写完本记录也没把闸门重新弄红**。

> `他人产物 hostlib` 的 510 个是闸门**按桶豁免**的历史备份（`kb/.work/hostlib.bak-*`，1.8 秒可再生），
> 不是本次对象；判据只看 `其他` 桶必须为空。

---

## 2. 根因（真坏，不是判据缺陷）

| 项 | 值 |
|---|---|
| 对象 | `ci/out/gates-latest.md`（2026-10-03 23:33:07 由 CI runner 落盘） |
| 原因码 | **E-ENV-4096 信封态** —— 写通道违规 |
| 写者 | `ci/run_gates.py` 的 `.md` 落盘走 **python `open(mp,"w")`**（原第 293 行） |
| 证据 | python `getsize` **1282** ｜ 消费方读者（宿主 Electron `readFileSync`）**5378** = 1282 + 4096，首字节 `\x88}\x1cn:\x05`（二进制垃圾） |
| 后果 | ① 腿⑥ 判红（`其他` 桶非空）；② **agent 自己读不到 CI 报告**（read 工具走消费方读者） |

写通道对照（同一路径三读者，本次实测）：

```
ci/out/gates-latest.md      python getsize 1282 ｜ 消费方读者 5378 ｜ 首字节乱码   ← 信封
ci/out/gates-latest.json    python getsize 36472 ｜ 消费方读者 36472 ｜ 明文      ← .json 不受影响
ci/README.md                python getsize 9099 ｜ 消费方读者 9099 ｜ 明文
ci/run_gates.py             python getsize 13822 ｜ 消费方读者 13822 ｜ 明文
```

⇒ 只有**由 python 直写的 `.md`** 中了招，`.json` 与 shell/node 通道的产物都是干净的。

---

## 3. 变更协议五问（铁律 1）

| 问 | 答 |
|---|---|
| **读者** | 消费方运行时 = 宿主 Electron `readFileSync`（agent 的 `read` 工具、装配位加载器）；人是第二读者 |
| **写者** | `ci/run_gates.py`（该文件唯一的写者；本次之后仍只有它写 `ci/out/`） |
| **判据** | `kb/l8/workflow_check.py` 腿⑥ `len(buckets["其他"]) == 0`；旁证判据 `tools/envelope_gate.py` 的 `\|py − 消费方读者\| == 4096` |
| **通道** | python 生成内容 → **无扩展名临时件**（`<目标>.tmp-plain`）→ `cp` 落目标（铁律 3）；`.json` 仍走 `json.dump`（实测安全） |
| **回滚** | `cp kb/l7/_backups/kb-repair-envelope-ci-20261003-234259/ci/out/gates-latest.md ci/out/gates-latest.md` 与 `cp .../ci/run_gates.py ci/run_gates.py` |

---

## 4. 改了什么（2 个文件）

| 文件 | 改动 | 性质 |
|---|---|---|
| `ci/run_gates.py` | 新增 `write_text_plain(path, text)`（无扩展名临时件 → `cp`），`.md` 落盘改调它；`.json` 不动 | **根因修复**（不修则下次 CI 复发） |
| `ci/out/gates-latest.md` | 用**修好后的同一个函数**重写：逻辑内容逐字未变（`sha256(logical)` 前后同为 `8b6959496acfdf99…`），只换落盘编码 | 存量修复 |

**根因修复的端到端证明**（不跑全量 CI —— 那会触发 `l5_gate` 重刷 `kb/.work/l5_integrity.json`，等于把腿② 的冻结基线悄悄刷新，故**主动避让**）：

```bash
python3 ci/run_gates.py --only layers --outdir /tmp/ci-proof    # 退出码 0
# /tmp/ci-proof/gates-latest.md  python=379 ｜ 消费方读者=379 ｜ 首字节 '# KB 闸门体检 ｜ 20'  ⇒ 明文
```

即：**修好后的 runner 自己落盘，不再产生信封。**

---

## 5. 本次**没有**修的红，以及为什么（不许拿它们凑"全绿"）

| 仍红项 | 定性（按 `kb-check` §3） | 为什么不动 |
|---|---|---|
| ④ 腿② 权威库 l0~l6 未被改动 | **合法变红（含判据缺陷）** | `l3_lines=1018`，而腿内硬编码比 `l3[:1527]`（`kb/l8/workflow_check.py:116`），L3 早在 2026-09-24 收敛 1527→509、当前 1018 行 ⇒ 该子项**结构上不可能为真**；要"修"只能改判据（机制改动，待裁）或刷新基线（人裁），**都不能靠改数据** |
| ④ 腿③ 前序产物哈希 45 项 | **合法变红** | 基线记的是 2026-09-23 的产物；其后 L3–L7 被重建过。**活库正常演进 ≠ 坏了**，刷新基线是人裁动作 |
| ⑥ 投影一致性 `projection_reconcile.py`（R1/R2/R4，exit 1） | **真·落后（需重跑链路）** | 修法 = 重跑 `kb/.work/gen-host-library.py` 到 staging 后回填；且 R4 有 2036 处治理字段**全缺**，像生成器压根没读这 4 个字段（F8），重跑可能白跑 ⇒ 属"要重跑链路才能修"，按 kb-repair §5 **交回 kb-pipeline**，不在本次授权内 |
| ③ 路由对账（exit 2 / 赢家表口径分歧） | **缺输入 + 口径待裁** | 赢家表是触发评测的运行时产物，全库无脚本自动生成；且默认口径（英文 id）与 `routes.yaml:dir_name_map`（中文目录名）冲突，属机制改动待裁 |
| 派生视图健康分（孤岛率 0.94 ❌、`E026` 454 条） | **真值，非假红** | 需**业务侧给真实关联列**；GUIDE 已登记"不要靠删条目降指标" |

---

## 6. 两条"下次别踩"的建议（**未实施**，属机制改动）

1. **`tools/envelope_gate.py` 的默认扫描范围不含 `ci/`**（`DEFAULT_ROOTS` 里没有它）。
   本次能抓到纯属**腿⑥**覆盖了工作区全部 `.md`；`ci/` 下的 `.py/.txt` 若落信封，⑤ 看不见。
   → 建议把 `"ci"` 加进 `DEFAULT_ROOTS`（一行改动，**留给人裁**，本次未动闸门口径）。
2. **`kb/l8/workflow_check.py:116` 的 `l3[:1527]` 是陈旧常量**（现行数据 1018 行），
   建议改为按记录里的口径取值或直接读 `l3_lines`（同上，待裁）。

---

## 7. 附录：命令回放与复开条件

```bash
cd "/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理"

# 修前（红）
sh kb/kbpy l8/workflow_check.py REPAIR-PREFIX-20261003-2345 ; echo $?   # 1（②③⑥ 红）
# 修后（同一条闸门）
sh kb/kbpy l8/workflow_check.py REPAIR-AFTER-20261003-2345  ; echo $?   # 1（②③ 红，⑥ 转 PASS）
# 旁证
python3 tools/envelope_gate.py        ; echo $?   # 0（1830 文件 / 信封 0）
sh kb/kbpy l8/envelope_census.py      ; echo $?   # 0（1079 个 .md 信封全部已分类）
sh kb/kbpy l7/scripts/skills_check.py ; echo $?   # 0（五类全 0）
sh kb/kbpy l7/scripts/layers_check.py ; echo $?   # 0（六类全 0）
sh kb/kbpy l8/projection_reconcile.py ; echo $?   # 1（R1/R2/R4 —— 未修，见 §5）
```

- **本次修复的复开条件**（已满足）：腿⑥ `其他` 桶为空 ⇒ PASS；`ci/out/gates-latest.md` 两读者同为 1282 字节、首行 `# KB 闸门体检`。
- **回归条件**：任何人再用 python 直写 `ci/out/*.md`（或 `ci/run_gates.py` 被改回 `open(mp,"w")`）⇒ 腿⑥ 立即转红。
