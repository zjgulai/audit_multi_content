# 四态口径收口：`SUGGEST` 独立态 → `PASS+SUGGEST`（2026-10-21 · Owner 当场裁定）

> 起因：Owner 贴一张真卡问「守衡输出的报告格跟 prd 不符，总共 4 态 pass / pass+suggest / block / review」。
> 判定依据是**刚拉的线上 PRD**（rev 105，李倩怡 2026-10-21 16:00 改），不是仓库里那份 09-23 的三态副本。

---

## 一、病灶（真单，逐字）

`PMO/logs/ws_outbound.jsonl` **2026-10-21T08:25:57.720Z**（北京时间 16:25，群 `oc_7775…`）：

```
【审查结论：SUGGEST】发现 1 处建议优化，不阻断发布。
PASS/0 ＋ SUGGEST 1 处：改 slogan 的建议需品牌方确认；两处小字待人工放大核
该 slogan 是官方 OUR STORY 页正式标语。
（已收起 1 条证据：证据 · 14 条）
```

问题不在「有几个字」，在**态名**：那一行把 `SUGGEST` 当成**最终态**，
而 PRD rev 105 三处同向都说它是 **PASS 的附属**。

## 二、PRD rev 105 原文（三处，逐字）

拉取方式（只读，未下载任何附件）：

```bash
python3 tools/lark_find.py readdoc PXfBdjTwFokEQixtmTscqm7knNh      # 正文
# §5.3.2 的定义表是**内嵌 spreadsheet**（raw_content 里只有占位），另拉：
#   spreadsheet B1aUs2Vuah8YwjtwWO6cr5MFnUd → 14 张 sheet，读的是 `xcdTpv` / `XWnpiN`
#   values API：/sheets/v2/spreadsheets/{token}/values/{sheet}  （同样只读）
```

| 出处 | 原文 | 指向 |
|---|---|---|
| §5.3.2 内嵌表 `xcdTpv`（rev **105**） | **主状态**只有 `PASS / REVIEW / BLOCK`；PASS 行的**附属信息**＝「可附带 **SUGGEST**（如措辞优化建议）」；动作＝「转 sign-off / brief 提交方；SUGGEST 提示内容方参考」 | SUGGEST 是 **PASS 的附属信息**，不是主状态 |
| §6.3 规则 4 | 「无 P0、P1、P2 明确违规，仅存在 P3 SUGGEST 时，系统最终流转状态（decision 字段）输出为 **PASS**，同时在结论中附带 SUGGEST 建议清单。」 | decision = **PASS** |
| §5.3.4 各状态输出模板 | `【PASS】…` ／ `【SUGGEST】发现 1 处建议优化，不阻断发布：…` ／ `【REVIEW】发现 2 处需人工确认：…` ／ `【BLOCK】发现 2 处必须修改：…` | 四份**输出格式**；SUGGEST 那份是「PASS + 建议清单」的印法 |
| §5.3.4 字数表 `XWnpiN` | 状态列：`PASS / SUGGEST / REVIEW(1-2) / REVIEW(≥3) / BLOCK(1-2) / BLOCK(≥3)` | 统计四桶 |

⇒ 四态 = **PASS / PASS+SUGGEST / REVIEW / BLOCK**（Owner 2026-10-21 的原话同此）。

## 三、Owner 拍的那一处

PRD 自身在「第 2 态的字面」上有张力（§5.3.2 说附属、§5.3.4 样张印 `【SUGGEST】`），
**问过一次、按推荐取的 A**：

> **A（采纳）**：`【审查结论：PASS+SUGGEST】发现 N 处建议优化，不阻断发布。`
> —— 四态在卡面/报告上一眼可数；内部 decision 仍按 §6.3 记 PASS（这一态就是「四桶」的第二桶）。
> B（保留 `【SUGGEST】` 字面、只改统计）与 C（退回 `【PASS】` + 建议段）**没取**。

## 四、改了哪几处（都在 `tools/`）

| 文件 | 改法 |
|---|---|
| `tools/agent/prd53.mjs` | `STATES` → `['PASS+SUGGEST','PASS','REVIEW','BLOCK']`；新增 `normState()`（旧名 `SUGGEST` 归一）；`LINE_RE` 收 `PASS\+SUGGEST`（**排在 `PASS` 前**）；`conforms()` 新增该态判据，**旧字面判红**并说清原因；`verdictLineFor()` 派生新行；`conclusionLine()` 多返回 `token`/`legacy` |
| `tools/agent/dual_track.mjs` | `mergedState()` 第 2 态返回 `PASS+SUGGEST`（库侧旧名经 `normState` 归一）；结论行改新字面；`orderActionLine()`／`summarized` 按新态名判 |
| `tools/agent/prd17.mjs` | 新增 `registryState()`：`PASS+SUGGEST → SUGGEST`（真源 `prd17-limits.yaml` 在**另一个仓**，那一行写的是 `SUGGEST`）；`limitOf`/`scopeOf` 走它 |
| `tools/agent/review_publish.mjs` | `conclusionOf()` 收得下 `PASS+SUGGEST`，旧字面归一（改前这一格抽不出来 ⇒ 表里留空白） |
| `tools/agent/merged_record.mjs` | 口径注释同步（state 四态 + 拒答） |
| `tools/agent/merged_report.test.mjs` | 报告结论行正则收 `PASS+SUGGEST` |
| `tools/test_agent.mjs` | Z57/Z58/Z60 的期望值、Z57 新增**两条反向对照**（旧名不合规 / 旧名归一）；prd17 别名断言 |
| `tools/agent/prd53_format.test.mjs` | ②g 组重写：新行被认、缺「不阻断发布」判红、`STATES` 四态、**旧字面能解析但判不合规** |
| `tools/agent/review_publish.test.mjs` | 新增「四态：`PASS+SUGGEST` 抽得出来 / 旧字面归一 / 不被截成 PASS」 |

## 五、自证读数（2026-10-21 17:5x–18:0x，可复跑）

| 命令 | 读数 | 说明 |
|---|---|---|
| `node tools/agent/prd53_format.test.mjs` | **通过 30 / 不通过 0**（原 28） | 新增 ②g6 旧字面组 |
| `node tools/verify_cards.mjs` | **通过 349 / 不通过 0** | 与改前同 |
| `node tools/agent/review_publish.test.mjs` | **通过 45 / 不通过 0**（原 44） | 新增四态那条 |
| `node tools/agent/merged_report.test.mjs` | **通过 13 / 失败 0** | 正则放宽后仍全绿 |
| `node tools/agent/prd17.mjs` | **通过 30 / 不通过 0** | 别名没把字数档位弄丢 |
| `node tools/agent/dual_track.mjs`（`selftest()`） | 通过 141 / 失败 2 | 两条 ④b2/④b3 是**改前就有**的（依据行「非条款依据」措辞，与四态无关，未动） |
| `node tools/test_agent.mjs` | 通过 **290** / 失败 **11**（改前 288 / 11） | 失败集合是改前的**子集**：转写×3、机制问句闸门变异、回执/P0 快达等**环境相关**项；改后反而多绿 2 条（W8b/Z23/Z26/Z49f/Z56/Z59 中 6 条由红转绿，与本次改动无关，属网络/模型抖动） |

行为级抽样（同一夹具，真跑）：

```
【审查结论：PASS+SUGGEST】发现 1 处建议优化，不阻断发布。

1.【品牌信任与声誉】正文第 2 段  —— **非权威候选线索 · 不构成依据**（无条款号，回不了源）
   **原因**：偏口语
   **依据**：《措辞表达库 v0》第 W-2.10 条
   **建议**：改为「高效便捷」
```

`deriveVerdictLine({mergedState:'SUGGEST', mergedCount:2})` ⇒ `【审查结论：PASS+SUGGEST】发现 2 处建议优化，不阻断发布。`
（旧名不会漏，也不会印出独立态。）

## 六、没做 / 还欠着的（别当成已做完）

1. **守衡还没重启** —— `dual_track.mjs` / `envelope.mjs` 都是被 import 的模块，改动**要重启才生效**。
   闸门读数（`bash tools/restart_shouheng.sh --check`，17:5x）：PID 4503、运行 33 分钟、私聊最后一条 17 分钟前、
   **6 个模块在启动后被改过**。重启要走闸门并先问（AGENTS §2.7），**本轮没动**。
2. **PRD 基线仍红** —— `python3 tools/verify_prd_baseline.py` 报「上游改版了」（正文 2026-10-21 16:00、
   《一页纸》10-19 12:15），而本地副本还是 **09-23 的三态版**（`PRD/feishu/内容审查Agent-PRD-v1.0.md` 里
   `SUGGEST` 出现 **0** 次）。§2.4.2 的重拉配方**没执行**（那会改索引指纹，属单独一件事）。
3. **PRD §5.3.4 样张里「结论行之下逐条」那一半没上卡**：`PASS+SUGGEST` 的逐条块仍走
   `conclusionBlock()`，而它只认「请修改后重新提交。」/「建议转…复核。」两种收尾 ⇒ 这一态卡面**只有结论行**
   （建议内容靠模型正文那句）。要补，是**另一条裁定**（会改卡面形状）。
4. **知识库那一侧（另一仓）的 `decision` 仍可能是 `SUGGEST`** —— 本仓只做「读得回来、印得对」；
   跨仓改名要两边一起动，未做。
