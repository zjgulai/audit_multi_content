# 体检表 · CHK-20261004-1126-ENVREG

- **run_id**：`CHK-20261004-1126-ENVREG`
- **时间戳**：2026-10-04 11:26–11:27（命令实测时间，`date` 回读）
- **库根**：`/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理`
- **档位**：体检档（`kb-check` `references/gates.md` 六道闸门）
- **预检查**：`python3 .dsh/skills/kb-check/scripts/preflight.py` → 退出码 **0**（六道脚本齐；**赢家表输入：无**）

## 一、体检表（闸门 → 退出码 → 结论 → 证据）

| # | 闸门 | 退出码 | 结论 | 证据 |
|---|---|---|---|---|
| ① | 登记表自检 `l7/scripts/skills_check.py` | **0** | **过** | 五类 1=0 2=0 3=0 4=0 5=0 合计 0；装载位 `~/.dsh/skills` 59 目录；登记表 71 成员（本项目 52 / 宿主通用 19）；本项目要用 40、已装 40、还差 0 |
| ② | 层契约 `l7/scripts/layers_check.py` | **0** | **过** | 六类 1..6 全 0；L0–L7 八层齐；DAG：L1←L0、L2←L1,L0、L3←L0,L2、L4←L2,L3、L5←L0,L2,L3、L6←L0,L2,L3、L7←L0,L3,L4,L5,L6 |
| ③ | 路由表对账 `l7/scripts/routes_reconcile.py` | **2**（契约位置无输入）<br>**1**（用现存赢家表） | **输入缺失**（非数据坏）<br>+ **真坏 5 条** | 契约位置 `kb/l7/reports/CHK-20261004-1126-ENVREG-routes-winners.json` 不存在 ⇒ exit 2（闸门自己声明「缺输入时不得报绿」）。改用现存 `_eval-kb-manage/results_alias/routes-winners_20261004-0327-SUB.txt --alias` ⇒ 逐条全轮命中 **60/65**，不一致 5 条（I1–I5），全部为 `brand-ai-provenance-rights-review` |
| ④ | 链路收口 `l8/workflow_check.py` | **1**（他会话产物） | **混合**：② 合法变红；③ 待判（疑合法）；⑥ 真坏（2 个非备份文件） | ⚠️ **本会话未跑**（无干跑档、会写 `kb/l8/workflow_check_<RUN>.json`）。引他会话产物 `kb/l8/workflow_check_CHK-20261004-1118-AG.json`（at 2026-10-04 11:23:14）：verdict FAIL，failed_legs = ②③⑥；①②④⑤⑦⑧⑨ PASS。② l0/l1/l2 均 `match_L5_baseline=true`，但 `l3_base1018_matches_L6=false`、`l3_whole1527_matches_L4=false` ⇒ L3 行数基线（1018/1527）与当前不符 = 基线漂移；③ checked 45、mismatch 列 20 项（含 `kb/l7/skills/kb-content-review/scripts/review.py`，即 2026-10-03 三防线改动）；⑥ md_total 6246、enveloped 512 = `{他人产物 hostlib: 510, 其他: 2}` |
| ⑤a | 信封闸门 `tools/envelope_gate.py`（**默认范围**） | **0** | **过**（范围之内） | 扫 **1968** 文件；信封态 **0**；读不到 0；两读者交叉核对**一致**。范围 = `kb/l0…l8`、`kb/.work`、`kb/view`、`kb/versions`、`tools`、`_eval-kb-manage`；`SKIP_DIR_NAMES={__pycache__,.git,node_modules,_archive,_backups,_skill-backups,_stage}`、`SKIP_PREFIXES=("hostlib",)` |
| ⑤a′ | 信封闸门（**扩到全库** `targets="."`） | **1** | **真坏 4 个** | 扫 **2775** 文件；信封态 **4**；两读者交叉核对**不一致 ⇒ 报红**（消费方读者判 4、PATH 读者判 2）。⇒ **默认绿是范围绿，不是全库绿** |
| ⑤b | 信封普查 `l8/envelope_census.py` | **0** | **过**（含 1079 已分类非零） | 扫 10377 `.md`，1079 个 node 侧读不到（差 4096）→ 已分类：刻意归档 569（`l8/_archive/enveloped-20260923-1520/…`）+ 可再生过期备份 510（`.work/hostlib.bak-20260928-152220/…`）；**只扫 `.md`** |
| ⑥ | 投影一致性 `l8/projection_reconcile.py` | **1** | **真坏 3 项** | 3/6 通过。R1 `source_sha256`（`f27a14091b2bd782… → 743dc62398311b02…`）、R2 `entry_fingerprint`（509 条权威规则已变）、R4 `governance_passthrough`（**2036 处**治理字段未传导：`owner`/`half_life_days`/`valid_until`/`effective_from` 各 509）。R3/R5/R6 通过 |

**汇总**：本会话亲跑 6 次（①②③×2⑤a×2⑤b⑥），绿 = ①②⑤a(默认)⑤b；红 = ③(输入)③(5 条)⑤a′(4 个)⑥；④ 未亲跑，引他会话产物（红）。

## 二、失败项清单（对象 + 原因码 + 要人做什么 + 复开条件）

| # | 对象 | 原因码 | 要人做什么 | 复开条件 |
|---|---|---|---|---|
| F1 | 门③ 输入 | 缺 `kb/l7/reports/<RUN>-routes-winners.json` | 按 `kb-manage` 触发电测重新生成赢家表并落契约位置 | 文件存在且 `routes_reconcile.py` 退出码 ≠ 2 |
| F2 | `brand-ai-provenance-rights-review`（I1–I5） | 路由未命中：实际被 视频安全审查 / 图片安全审查 / AI 溯源与权利审查 / NONE / CLARIFY 接走 | 核对 `kb/l7/registry/routes.yaml` 让位表与 `AI溯源与权利审查` 的 description 触发词 | alias 口径逐条全轮命中 = 65/65（现 60/65） |
| F3 | `kb/l3` 行数基线 | 基线漂移（活库）：`l3_base1018` / `l3_whole1527` 与当前不符；l0–l2 未变 | 确认基线是否该随活库刷新（**非缺陷**，见 `gotchas.md` §2） | 基线刷新后门④ leg② 转 PASS |
| F4 | 20 项前序产物 | 哈希漂移（45 项中列 20）：`l3/candidates/rules.jsonl`、`l4/registry/l4.json`、`l5/registry/l5.json`、`l6/{bm25,vectors,index,registry}/*`、`l7/skills/kb-content-review/scripts/review.py` 等 | 逐项确认是否均为本次合法重建（`review.py` 已对得上 2026-10-03 三防线改动） | 逐项确认后更新基线 |
| F5 | 4 个信封态文件 | 消费方读者读到 +4096：`_chk-run-PIPE-GATE-20261004-0200/00-index-before.txt`（py=9/node=4105）、同目录 `09-index-after.txt`、`_eval-L0L7-gap-20261003/kb-l0-feishu-fix/SKILL.md`（17284/21380）、同目录 `references/CHANGELOG.md`（20520/24616） | 交 `kb-repair`，**按 node/`/bin/cp` 通道重写**（python 直写会再带信封）；**不要删** — 其中 2 个是评测修复副本、可用性未知 | 全库扫（`targets="."`）信封态 = 0 且两读者一致 |
| F6 | `kb/view` ⇄ 权威分层库 | 投影漂移 R1/R2/R4（R4 = 2036 处治理字段未传导） | 重跑 `kb/.work/gen-host-library.py` 到 staging 后回填；R4 另查生成器是否从规则行读这 4 个字段（F8） | `projection_reconcile.py` 6/6 通过、退出码 0 |

## 三、口径与诚实声明

1. **④ 不是本会话跑的**。`workflow_check.py` 无干跑档、必写 `kb/l8/workflow_check_<RUN>.json`（`gates.md` 门④）；本会话只读交付，未取得写盘许可 ⇒ **只引他会话产物，并标为他会话产物**。其上表所有 ① ② ③ ⑤ ⑥ 均为本会话实测。
2. **③ 的两次退出码不是矛盾**：exit 2 = *输入缺失*（契约位置无赢家表），exit 1 = *有输入时的 5 条不一致*；口径也不同（strict 65/65 不一致是「中文装载名 vs 英文登记 id」的口径差，alias 口径 60/65 才是可比读数）。
3. **⑤a 默认绿有明确边界**：默认 `DEFAULT_ROOTS` 不含库根 `_eval-*` / `_chk-run-*`；扩到全库即 **4 个信封态 + 两读者不一致**。⇒ 引用「信封闸门全过」时**必须连带说明扫描范围**。
4. **⑤b 的「OK」不是零**：10377 个 `.md` 里有 **1079** 个消费方读不到，只是已被分类为「刻意归档 / 可再生备份」；且它**只扫 `.md`**（`.py`/`.txt` 要靠 ⑤a，两工具不可互替）。
5. **并发**：11:24–11:25 期间 `ps` 实测另有会话在跑 `skills_check.py`、`l0_gate.py`、`l5_integrity.py`、`l8/_interp.py`。本会话全程只读；本会话期间 `kb/.work/.kb.lock` **不存在**。本会话唯一新增：本文件 + `_chk-run-CHK-20261004-1126-ENVREG/`（证据留档）+ `_chk-run-LATEST-KBCHECK.txt`。
6. **未做的**：未跑 `workflow_check.py`（写盘）；未修任何红项（本 skill 只报不改，修复走 `kb-repair`）。
