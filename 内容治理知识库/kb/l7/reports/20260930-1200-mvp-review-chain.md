# MVP · 评审链 skills 工作流跑通记录（2026-09-30）

**目标**：用户说一句「**这个评审一下**」（带待审内容）→ 由已装 skills 走完评审链 → 输出带依据的三态结论。
**本轮结论：主路径跑通（触发 ✅ / 取依据 ✅ / 结论 ✅ / 落盘 ✅），但「专项 skill 本体」与「无人值守」两段还没接上。**

---

## 1. 这次实际跑了什么（逐步留证）

| 步骤 | 谁做的 | 证据 |
|---|---|---|
| 输入 | 用户一句话 + 文案 | `FDA approved breast pump. Hospital grade. 100% safe and pain-free. Mimics baby natural nursing to boost supply.` |
| ① 触发（**盲测**） | 一个**新开的 agent**，只给上面那句话 | 它自己选中 **`文案合规审查`**，理由：「纯文字 listing 命中让位规则，专项能识别就直接进专项；`kb-review` 只在专项归属不明时兜底」。**没有**误选 kb-pipeline / kb-review / 产品宣称核验 |
| ② 入口判定 | `kb-review`（本会话加载） | 按 §0 让位表：文字 → `文案合规审查`；跨模态/归属不明才由自己接 |
| ③ 取依据 | `kb-content-review` 的检索协议 + 它的可执行参考实现 `scripts/review.py` | 分层下探：P0 确定性匹配 → 规则层 → 单元层 BM25 → 原文层按 anchor 回 `l0/records/` |
| ④ 结论 | 引擎输出 + 引用契约 | `BLOCK`，10 处问题，逐条带引文/条款号/anchor/sha256/原文出处/建议 |
| ⑤ 落盘 | `review.py` 的 node 明文通道 | `kb/l7/reports/20260930-115756.review.md`（python=node=20009，差 0 → 宿主读得到） |

**检索轨迹（引擎自报，非人工转述）**：
P0 命中 **5**（8.5 ms）｜规则层命中 **11**｜单元层 BM25 最高 **40.58**（门限 8.0，未启用向量补召）｜无法满足引用契约 **1** 条。

**这次用到的 skill（3 个，全部已装）**：`kb-review`（入口/让位）、`kb-content-review`（依据+引用契约）、`文案合规审查`（盲测选中的专项；**本轮未真正加载执行**，见 §4 缺口）。
**用到的引擎**：`kb/l5/matcher.py`（P0）、`kb/l3/candidates/rules.jsonl`（规则层）、`kb/l6/retriever.py`（BM25）、`kb/l4/canonical/*.jsonl`（条款号 join，本轮新接）、`kb/l0/records/**`（按 anchor 取原文）。

## 2. 评审结论（MVP 的实际输出，10 处）

| # | 分类 | 条款号 | 逐字命中 |
|---|---|---|---|
| 1 | 功效宣称-催乳与通乳宣称 | W-1.18 | `H02:boost supply,more milk,triggers letdown` |
| 2 | 功效宣称-疼痛功效承诺 | W-1.53 | `H07:pain-free / H09:mimics baby` |
| 3 | 未分类-未分类 | W-1.8 | `FDA approved, FDA certified, FDA 认证, FDA 批` |
| 4 | 绝对化与安全承诺-虚假安全承诺 | W-1.33 | `safest, most safe, 100% safe, 100% painless, zero risk` |
| 5 | 人物肖像与 AI-AI 合成标识 | W-1.6 | `疼痛功效承诺（pain-free/no pain/…）` |
| 6 | 人物肖像与 AI-AI 合成标识 | W-1.22 | `mimics baby, mimics nursing, copies your…` |
| 7 | 功效宣称-催乳与通乳宣称 | W-1.31 | `删除 safest/100% safe/zero risk/perfect 等虚假安全承诺…` |
| 8 | 背书与资质-医疗场景宣称 | W-1.35 | `M05:hospital grade,hospital-grade / M07:leak` |
| 9 | 背书与资质-医疗场景宣称 | W-1.19 | `hospital grade, 医疗级, 医用级, 军用级` |
| 10 | 背书与资质-等级与资质背书 | W-1.11 | `M05:hospital grade,hospital-grade / M07:leak / U…` |

依据格式（引用契约六要素，逐条如此）：
`《措辞表达库 v0（试用版，未发布）》第 W-1.18 条` + `anchor: #广告文案明细/recvuJYdObWZ2t/命中片段`
+ `source_sha256: 351f2c9d…` + 原文出处 `kb/l0/records/广告文案风控库__广告文案明细/recvuJYdObWZ2t.json` 字段 `命中片段`
+ 逐字引文 + `事实｜置信度：高` + `分层：P0 确定性匹配`。

## 3. 本轮修掉的两个**真缺陷**（都是 MVP 的硬堵点）

### 缺陷 1：结论落盘成「信封态」，宿主读不到（P0 级）

- **现象**：`review.py` 报 `[warn] node 落盘失败（-9）` → 降级 python 写盘 → 报告 python=19888 / node=23984（差 **−4096**）= 信封态，宿主侧读出来是乱码。
- **根因（读码+实测）**：`_resolve_node()` 里 DSH 的 glob 写的是
  `/Applications/DSH Desktop*.app/Contents/MacOS/*`，而本机 app 名是
  **`DSH Desktop.app.pre-lute-20260907-111753`**（`.app` 在中间）→ **glob 匹配不上**；
  于是掉到第二候选 ChatGPT 的 `cua_node`，那个二进制在本机被 **SIGKILL（rc=-9）** → 直接降级 python。
- **修复（最小）**：① glob 补成 `/Applications/DSH Desktop*/Contents/MacOS/*`（两个模式都留）；
  ② node 候选**逐个试**，不再一试就投降。→ 现在通道报 `node:DSH Desktop`，报告 python=node **差 0**。

### 缺陷 2：引用契约缺「条款号」，报告里印出「第  条」

- **现象**：所有依据都是《措辞表达库 v0》第 **（空）** 条。
- **根因**：`review.py` 从 `kb/l3/candidates/rules.jsonl` 读 `article_no`，而**该字段在候选文件里是空的**
  —— L4 发号后没有写回候选文件（注册表 `l7.json → article_no_source.field_lives_in_was` 早有登记）。
- **修复（最小、只读）**：`load_rules()` 里加一次 join —— 从 `kb/l4/canonical/*.jsonl` 建
  `rule_id → article_no` 映射**补齐空值**（实测 **509/509** 连得上）。不改任何库文件。
- **结果**：依据变成 `第 W-1.18 条`、`第 W-1.53 条` …

两处改动都落在 **源副本** `kb/l7/skills/kb-content-review/scripts/review.py`，并 `/bin/cp` 同步到装机位，
两份逐字节一致（`skills_check` 第 3 类里 `kb-content-review` 无告警）。

## 4. 还没跑通的（如实列，不粉饰）

1. **专项 skill 本体没被真正执行**：盲测证明「会被选中」，但这次结论是用 `kb-review` + `kb-content-review` 的协议跑出来的，
   `文案合规审查` 自己的判据/输出契约**没有加载执行**。→ 下一轮：加载它，按它的流程重跑一次，比对两份结论是否一致。
2. **整条链没有一次性留证**：入口 → 专项 → 依据 → 裁决 → 报告这 5 跳，目前是分段验证的，没有一次「一口气跑完并留下每跳证据」的记录。
3. **无人值守未做**：本会话是人在环（我即 agent）。定时触发 agent 的**无头入口仍未确认**（只找到 `~/.dsh/bin/lark-cli`）。
4. **`kb-l0-feishu` 副本不一致**（`skills_check` 第 3 类 1 条）**不是本轮产生的**：安装位 `SKILL.md`/`CHANGELOG.md` mtime 为 10:40、`retro.py` 10:31，源停在 09-29 18:16 —— 另有写入者在改它，本轮未碰。

## 5. 顺带被证伪的一个假设（记下来，免得下次又猜）

我先前判断「『评审一下』不在 `routes.yaml` 的触发说法里（只有『审一下』『帮我审』）= 触发缺口」。
**盲测证伪了**：新 agent 只拿到「这个评审一下」+ 文案，正确选中了文字专项。
→ 结论：**不要因为字面没写上就断定路由会失败**；触发面以盲测为准，不以字面为准。
（仍建议把「评审一下」补进说法表，但它属"锦上添花"，不是堵点。）
