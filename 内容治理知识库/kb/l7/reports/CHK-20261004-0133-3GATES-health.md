# 体检表 · 三闸门（registry / layers / routes）· 2026-10-04 01:33

**库根**：`/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理`
**档位**：`kb-check` **体检档**（只报不改）｜**RUN**：`CHK-20261004-0133-3GATES`
**本单只回答用户点名的三件**：① registry 自检 ② layer 契约 ③ 路由对账

---

## 一、体检表

| # | 闸门 | 命令 | 退出码 | 结论 |
|---|---|---|---|---|
| ① | 登记表自检（registry） | `kb/kbpy l7/scripts/skills_check.py` | **0** | **过** · 五类问题合计 0 |
| ② | 层契约（layer） | `kb/kbpy l7/scripts/layers_check.py` | **0** | **过** · 六类问题合计 0 |
| ③a | 路由对账（skill 正文原命令） | `kb/kbpy l7/scripts/routes_reconcile.py kb/l7/reports/<RUN>-routes-winners.json` | **2** | **缺输入 · 硬拒**（非绿非红） |
| ③b | 路由对账（库外真实赢家表） | `kb/kbpy l7/scripts/routes_reconcile.py _eval-kb-manage/blind_v2.winners.txt --cases _eval-kb-manage/cases_v2.json --alias` | **1** | **有对账不上 6 条** · 109/115 命中 · ④ 路由表自检 0 条 |
| ④ | 链路收口核验 | `kb/kbpy l8/workflow_check.py <RUN>` | **未跑** | 见 §三 —— **无干跑档、会写 `kb/l8/`**，且**另一会话正在跑它** |
| ⑤ | 信封闸门 | `python3 tools/envelope_gate.py` / `l8/envelope_census.py` | **未跑** | 用户未点名；非本次三件之内 |
| ⑥ | 投影一致性 | `kb/kbpy l8/projection_reconcile.py` | **未跑** | **无干跑档**（只读复核用，不加写参数）；另一会话正在跑 |

---

## 二、③ 为什么是「缺一道」

**两层缺口，必须分开说：**

1. **第一层：库内赢家表根本不存在（硬拒，退出码 2）**
   全库 `find kb -iname '*winner*'` **0 命中**；`kb/l7/reports/` 内只有历史 health 报告，无 `<RUN>-routes-winners.json`。
   对账器行为正确：**缺输入时不报绿、也不静默按「0 条 ⇒ 全不一致」跑**，直接退 2 并打印提示。
   ⇒ 这一格**没有结论**，不是"过"也不是"红"。
2. **第二层：替代输入在库外，且是 5 天前快照**
   真实赢家表 = `_eval-kb-manage/blind_v2.winners.txt`（**115 条 / 2026-09-29 19:58**），
   配套用例表 `_eval-kb-manage/cases_v2.json`（115 条，id 与赢家表逐条对齐）。
   ⇒ ③b 回答的是「**09-29 那轮**实际被谁接走」，**不是「今天被谁接走」**。
   要今天的数据 ⇒ 先按 `kb-manage` 的重做一轮触发电测，重新生成赢家表（本单不代跑）。

**③b 的 6 条不一致（逐条）**

| 用例 | 期望 | 实际（第1/2/3轮） | 定性 |
|---|---|---|---|
| I1 | AI溯源与权利审查 | 视频安全审查 ×3 | 已知用例歧义（`routes.yaml` 登记 I1↔G3 近重复） |
| I2 | AI溯源与权利审查 | NONE / 图片安全审查 / NONE | 已知用例欠定义 |
| I3 | AI溯源与权利审查 | NONE / **AI 溯源与权利审查** / NONE | **判据缺陷（假阴）**：赢家表记的是**改名前的旧名（带空格）**，非数据缺陷 |
| I4 | AI溯源与权利审查 | **AI 溯源与权利审查** / NONE / NONE | 同上（判据缺陷 / 台账早于改名一天） |
| I5 | AI溯源与权利审查 | 图片安全审查 ×2 / CLARIFY | 已知用例歧义（I5↔F5 近重复） |
| `kb-manage-4` | kb-manage | kb-manage / kb-manage / **kb-pipeline** | **真·路由边界异议 —— 唯一要人裁的一条** |

被抢走计数：`NONE` 6 次 / 视频安全审查 3 / 图片安全审查 3 / `AI 溯源与权利审查`（旧名）2 / CLARIFY 1 / kb-pipeline 1。
**结论口径**：3 条已知歧义 + 2 条判据缺陷（**不许报成数据缺陷**）+ **1 条真异议待裁**。
`kb-manage-4`（用例句「知识库该更新了」问归属）：路由表内部自洽（两处都归 `kb-pipeline`），
但 `kb-manage` 触发词含「该走哪个 skill / 谁负责」，元问题强匹配 ⇒ 边界没写死，**交人裁，本单只报不改**。

---

## 三、④⑤⑥ 为什么没跑

| 缺的 | 原因 | 复开条件 |
|---|---|---|
| ④ 链路收口核验 | `l8/workflow_check.py` **无干跑档**，不加参数也会写 `kb/l8/workflow_check_<RUN>.json`；且**实测另一会话（PID 72445 / RUN `CHK-20261004-0130-WFP`）此刻正在跑它** | 等该批收工，或单独报批开写档 |
| ⑤ 信封闸门 | 不在用户点名的三件内；`envelope_census.py` 只扫 `.md`，`.py/.txt` 需另跑 `tools/envelope_gate.py` | 用户点名即可跑（只读） |
| ⑥ 投影一致性 | **无干跑档**；同一并行批正在跑 | 同上 |

**并发纪律（本库实测踩过双计与覆盖）**：本单三道**全部只读**（已核 `skills_check.py` / `layers_check.py` / `routes_reconcile.py` 无写盘调用），
**未跑任何会写库的闸门**，与并行批不冲突、不产生第二条 `index.jsonl` 记账。

---

## 四、边界

- 本单为**静态契约核验**，**不含任何"层已跑完"结论**（那类结论必须带 run_id + 时间戳）。
- `③b` 的三条已知歧义与两条判据缺陷**不在本单翻案**；`kb-manage-4` **只报不改**。
- 结论与证据诚实：③ 的两层缺口与 6 条定性**逐条列出、未合并、未修饰**。
