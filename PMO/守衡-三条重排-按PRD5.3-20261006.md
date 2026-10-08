# 守衡 · 三条重排（按 PRD §5.3 输出规范）

> 起因：Owner 2026-10-06 07:46–07:51 在飞书私聊问了 3 条，守衡回出去的格式**不符合 PRD §5.3**。
> 本文是**重排后的输出**（可直接照发），以及**检查结果：不符在哪一层**。
> 依据版本：`PRD/feishu/内容审查Agent-PRD-v1.0.md` §5.3（sha256 `8df44f86e0e2f9e2540fbe1c2472eb3850474da23177eae48592658b33888217`，
> `python3 tools/verify_prd_baseline.py` 的 L3 组已核：**上游 = 落盘副本 = 指纹**，2026-10-06 运行时 7 项全过）。

---

## 一 · 检查结果：不符在哪一层

**结论：不是守衡「写歪了」，是它把上游已经给好的规范行改写掉了。**

整条链其实**已经按 5.3 产出了结论行**（`kb/l7/review-engine/core/review_engine.py:212 render_summary()`），
守衡收到的是这段原文，**照实转述**的要求也写在注入语里（「逐字转述，不许改写」）。
但它在**回卡片**那一跳把表头重写了 —— 于是 5.3 的标记丢在中间层，群里看到的是自造标题。

| # | 链路侧原话（引擎产出） | 群里实际收到（守衡卡片标题） | 差在哪 |
|---|---|---|---|
| ① | `【审查结论：PASS】未发现已知底线风险，可转交 sign-off 负责人确认。` | `【PASS（美国口径，0 问题）—— 但「未命中 ≠ 合规」】` | 标记不是 `【审查结论：PASS】`；无「转交 sign-off 负责人」动作 |
| ② | `【P0 红线拦截：BLOCK】命中知识库已定稿的 P0…` | `【P0 红线拦截：BLOCK（H02 / H04）｜与上次同一份结论】` | 应落到 5.3.3 的 `【审查结论：BLOCK】共发现 N 处必须修改。`；缺「共发现 N 处」 |
| ③ | `【审查结论：REVIEW】共发现 1 处需人工确认。` + 逐条 | `【证据】REVIEW：1 处问题（W-1.54 静音绝对化）` | 表头被写成卡片类型名 `【证据】`；缺逐条四要素与「建议转 @复核责任人」 |

### 1.1 三处结构性缺失（三态共有）

1. **结论标记**：5.3 要求 `【审查结论：<态>】`，实际是自造标题。
2. **逐条四要素**（1–2 个问题时）：`【类别-子类】` + 位置 + 引文 + **原因** + **依据（库名 + 版本 + 条款号 + 链接）** —— 实际只有条款号，且埋在「四段溯源」表格里。
3. **尾部动作**：PASS→转 sign-off 责任人；REVIEW→建议转复核责任人；BLOCK→请修改后重新提交。实际三条都没有 `@` 动作。

### 1.2 还有一处**上游自己也没对齐**（不是守衡的错，一并报）

引擎 `render_summary()` 对 REVIEW 与 BLOCK **用了同一句话**：

```python
lines = [f"【审查结论：{decision}】共发现 {len(items)} 处需处理问题。"]
```

而 PRD §5.3 是两句不同的：REVIEW = 「共发现 N 处**需人工确认**」；BLOCK = 「共发现 N 处**必须修改**」。
`kb/l7/review-engine/core/review_engine.py:218` 与 `:229` 两处都写成了「需处理问题」。

**为什么一直没被发现**：KB 侧确实有一条 5.3 判据（`kb/.work/l7_integrity.py:114-124`，
`template_conformance`），但它的断言只到

```python
"REVIEW": "【审查结论：REVIEW】共发现" in a and "建议转" in a,
```

—— **「共发现」后面那半句它没查**。所以「需处理问题」与「必须修改」两种写法都能过闸门。
这正是 `AGENTS.md` §2.4 那个形状：**判据存在，但没盖住出事的那一跳。**

另外那份判据的输入是 `kb/l7/selftest_*.md` **自验夹具**，不是任何一条真实回话 ——
所以守衡群里发出去什么，它结构性看不见。

### 1.3 一个绕不开的前提：`@` 目前 @ 不出去

PRD 5.3 三态的尾部都是「转 @某人」。但 `kb/l7/registry/l7.json` 的 `approvers` 是：

```json
{"configured": false, "pass_signoff": {"role": "sign-off 责任人", "handle": null},
 "review_reviewers": {"role": "复核责任人", "handle": null},
 "block_owner": {"role": "内容方修改责任人", "handle": null}}
```

KB 自己的契约（`kb/l7/output_template.md` 开头）写着：**「责任人一律从 l7.json 的 approvers 读，不写死人名」**，
未配置时「输出保留角色名并标注『未配置』」。所以下面三条**照契约写角色位**，不编人名、不编 open_id。

补一句事实（**当读数看，不当结论**）：`PMO/上游对接人表.md`（09-22 版）记着
吸奶器品线 Sign-off = Misty Chen 陈静姝、法务对接 = 钱撷羽 Sharon、广告&独立站 Sign-off = 易思琦 Mio。
**该表不是引擎的 approver 配置**，且这些人今天能否解析出 open_id 我没有重测 —— 所以我没把它写成 `@`。
另：这三条是在**私聊**里问的，私聊里 @ 第三人也**不会通知到本人**，它只是路由指示。

---

## 二 · 重排后的三条（可直接照发）

> 格式 = PRD §5.3 原文。三态都未改动（仍是引擎给出的 PASS / BLOCK / REVIEW）。
> `---` 以下是 KB 契约要求的检索轨迹与**必须一并转述的边界**，不要吞。

### ① PASS

**送审原文（逐字）**：`这段 listing 文案能不能发：M5 吸奶器是销量最高，最好用的吸奶器了？帮我看看有没有踩红线`

```
【审查结论：PASS】未发现已知底线风险，可转交 @sign-off 责任人（未配置） 进行 sign-off。

---
检索轨迹摘要：P0 0 命中（137 ms，exit 0）｜规则层 0 命中（扫 509 条）｜单元层 BM25 最高 23.08（覆盖门限 16.0）｜向量补召 未启用｜无法满足引用契约 0 条
覆盖判据：coverage.covered=true（过门限单元 #专家修订汇总表/recvoyJ6L9yTXz 23.08、#广告文案明细/recvuJYdObJwyY 22.92）⇒ 这个 PASS 不是「库不认识这主题」的空过
链条：BASE=20261006-0746｜四层前置 ok=true｜mode=enforced｜四层审计红 0｜判定主体 文案合规审查（mode=declared）
留痕：已落表 recvxdPvkkqLXK（content ID AUTO-81961315ad14）｜问题数 0 < 3，按 PRD 不生成云文档
```

**边界（一行，不许吞）**：未命中 ≠ 合规；`confidence=0.99` 是 `heuristic_not_calibrated`（未校准）；
`rule_version` / `knowledge_version` 均 `unfrozen`；黄 `E5` = 预演落章，不等于真落盘；不能外推到德国/中国等管辖。

**执行者标注（不是改判，是不确定性）**：「销量最高」与「最好用」性质不同 —— 后者是主观最高级，
前者是**可被要求举证的事实性排名声明**。库里 2026-09-09 口径把 ranking/最高级一并放开（所以引擎给 PASS），
但该口径的证据**只到 L6 参考级**、且 H05 那条不是逐字对照「销量最高」这类销量声明。
⇒ **若 M5 的销量第一排名拿不出可核对的来源，建议按 REVIEW 让 sign-off 负责人补一句 substantiation。** 三态未动。

---

### ② BLOCK（走的是 P0 快路）

**送审原文（逐字）**：`Our M5 breast pump is doctor recommended and helps increase milk supply in 3 days.`

```
【审查结论：BLOCK】共发现 2 处必须修改。

1.【功效宣称-催乳与通乳宣称】全文，逐字命中「increase milk supply」（H02，命中 2 处）
  原因：H02 催乳/增产/奶量产出承诺（含裸 more milk、催产素、长期奶量、裸奶阵/排空功效 claim，无 FDA/临床证据）
  依据：《措辞表达库 v0（试用版，未发布）》第 W-1.18 条（链接：kb/l3/candidates/rules.jsonl#W-1.18）
  锚点：#广告文案明细/recvuJYdOb1Rm1/命中片段｜source_sha256：c77f576dcc392cb3e763e6462d0259e50fb039f924a4af8e100321197e5be577
  判定：事实（确定性逐字匹配）｜置信度：未给（P0 快路不产出置信度，不代填）
  建议：删除 more milk/增产催奶/催产素/长期奶量/裸奶阵排空承诺；合规替代为放松叙事+限定语，如 relaxation supports your natural let-down, which may help your flow（因为放松，自然奶阵可能更顺畅），只描述自然生理过程、不承诺产品带来结果；faster let-down/提高排空效率在拿到 W1 自身对照数据前禁用
  L0 逐字（可点直链）：https://momcozy-in.feishu.cn/base/Lk3Qb8y2QaVyZns6gprcVNE9nA0?table=tblcbk4XiW6471YN&record=recvuJYdOb1Rm1

2.【背书与资质-医生专家推荐】全文，逐字命中「doctor recommended」（H04，命中 2 处）
  原因：H04 无据的医生/专家推荐背书；M03 未标注来源的效果数据声明；U01 含泌乳顾问/认证头衔，需核实是否真实合作
  依据：《措辞表达库 v0（试用版，未发布）》第 W-1.13 条（链接：kb/l3/candidates/rules.jsonl#W-1.13）
  锚点：#广告文案明细/recvuJYdObV6eR/命中片段｜source_sha256：6059659ad3f649c3ac1ff6ca602fdcd0368094a9d9490fa5dca0319872677af0
  判定：事实（确定性逐字匹配）｜置信度：未给（P0 快路不产出置信度，不代填）
  建议：删除医生/专家/IBCLC/OB-GYN 推荐背书；免费 IBCLC 服务可单独陈述但不得与「推荐」绑定 ▸ 效果百分比/销量/评分声称需附测试来源与口径，否则删除（折扣百分比不在此列）▸ 核验 IBCLC/专家身份、参与方式、程序设计依据与 COI 披露后再保留
  L0 逐字（可点直链）：https://momcozy-in.feishu.cn/base/Lk3Qb8y2QaVyZns6gprcVNE9nA0?table=tblcbk4XiW6471YN&record=recvuJYdObV6eR

请修改后重新提交。

---
检索轨迹摘要：P0 2 命中（42.939 ms）｜规则层 未跑｜单元层 未跑｜向量补召 未跑｜无法满足引用契约 0 条
```

**边界（一行，不许吞）**：**这是 P0 快路**（PRD §6.3 第一层，确定性匹配，不动用大模型）——
**未跑** L4→L5→L6→L7 层前置与评审链，**不是整条链跑完了，也不是专项审过了**，不得当作 PASS 依据；
若素材属图片/视频/产品宣称等模态，**仍需转对应专项复核**。

---

### ③ REVIEW

**送审原文（逐字）**：`这段 listing 文案能不能发：吸奶器静音设计，夜里不吵醒宝宝，续航 8 小时`

```
【审查结论：REVIEW】共发现 1 处需人工确认。

1.【平台与促销-静音绝对化表述】全文，逐字命中「静音」（M01）
  原因：静音程度夸大（边界规则原文：「建议改为 low noise / quiet mode」）｜⚠️ 来源表**未给判定理由**：W-1.54 的 reason 字段为空，不代填
  依据：《措辞表达库 v0（试用版，未发布）》第 W-1.54 条（链接：kb/l3/candidates/rules.jsonl#W-1.54）
  锚点：#品线内容边界规则库/recvuJP1LV2uxa/边界内容｜source_sha256：1bf6ceb91a0d404e52dadd28aa2aa63585b57e03f3ac51a55f58635772e903d2
  判定：事实（规则层逐字命中）｜置信度：中（p_level=P1，risk_level=unknown，authority=None）
  建议：把「静音」改为客观参数或走豁免表述 —— 豁免词为 low noise / quiet mode / low-decibel / silent mode / 静音模式

建议转 @复核责任人（未配置） 复核。

---
检索轨迹摘要：P0 0 命中｜规则层 1 命中（扫 509 条）｜单元层 BM25 未给｜向量补召 未启用｜无法满足引用契约 1 条（见下）
层前置：ok=true / mode=enforced / red_total=0（L4–L7 各一 RUN，四道审计红 0）｜判定主体 文案合规审查（mode=declared）
去向：P1 / 4 business hours / America/Los_Angeles｜留痕：已落表 recvxdQ7ugomVX（content ID AUTO-3478e21e8c94，读回校验一致）
```

**四段溯源缺口（如实报，不许吞）**：第 ④ 段**不完整** —— 引擎给的 `excerpt` 是**被截断的规则文本**，
**不是完整 L0 逐字**；且引擎未给 L0 `entry_url` 直链，只有 L3 定位 `kb/l3/candidates/rules.jsonl#W-1.54`。
**本次未做 L0 记录值比对，因此不得声称 sha 已核对。** 按引用契约「引用不到本地锚点的结论不许输出」，
这一条**需要补**，回源直链目前拿不出来。

**边界（一条都不许吞）**：
- **未命中 ≠ 合规**：`coverage.covered=false`，原话是「未被规则覆盖的部分**不足以证明合规**」。
  素材里「夜里不吵醒宝宝」「续航 8 小时」两段**本次没有任何依据命中**，不等于它们没问题。
- 层前置：链路转述模板里那行 `ok=None mode=None` 是**模板渲染缺值**；引擎 JSON 实际值是
  `layer_preflight.ok=true` / `mode=enforced` / `red_total=0`。两处不一致，**以引擎 JSON 为准**。
- 黄 `E5` = 机制证据，**不等于真落盘**（L4/L5/L6 三层落章来自预演）。
- 本单引擎**没有**给 `NEEDS_INPUT`，所以「拒答 ≠ 通过」本次不适用；但**也不是 PASS**。

**一处待你确认**：这条送审**原样发了两遍**（`om_x100b63773f3d10a8b12c057f44d6091` 与重复投递）。
两次素材逐字相同 ⇒ `content_id` 相同 ⇒ 按幂等 upsert 只落**一行**。
若这两遍是两个独立送审任务、需要两行记录，请说明；否则视为一次重复发送、已按一条处理。

---

## 三 · 回验：重排后的三条真的过判据吗

**不是「我看着像」—— 用判据跑过，并且证明判据会红。**

```bash
python3 PMO/守衡-三条重排-按PRD5.3-20261006.check.py     # rc=0
```

判据两套，缺一套都不算验过：

| 套 | 内容 | 为什么要有它 |
|---|---|---|
| ① **KB 侧原文** | `kb/.work/l7_integrity.py:114-122` 的四个 marker，逐字照搬 | 库自己认的 5.3 长什么样 |
| ② **PRD 逐字措辞** | REVIEW 必须是「共发现 N 处**需人工确认**」、BLOCK 必须是「共发现 N 处**必须修改**」 | ① **只查到「共发现」为止**，后半句没查 —— 引擎把两态写成同一句话却一路绿灯，就是这里漏的 |

读数（2026-10-06）：

```
A · 重排后的三条
  ✅ ① PASS  ｜PRD 逐字措辞 ✅｜KB 态判据 ✅｜逐条四要素 —
  ✅ ② BLOCK ｜PRD 逐字措辞 ✅｜KB 态判据 ✅｜逐条四要素 ✅
  ✅ ③ REVIEW｜PRD 逐字措辞 ✅｜KB 态判据 ✅｜逐条四要素 ✅

B · 反向对照：群里**实际发出**的那三条（必须全红）
  ❌ ① PASS 实发  ｜PRD ❌｜KB ❌
  ❌ ② BLOCK 实发 ｜PRD ❌｜KB ❌｜逐条四要素 ❌
  ❌ ③ REVIEW 实发｜PRD ❌｜KB ❌｜逐条四要素 ❌

重排后三条：✅ 全绿 ｜ 实发三条：✅ 全红（判据确实会红）｜ rc=0
```

> ⚠️ **写这个检查器时我自己先错了两版，都记在这里**（同 `AGENTS.md` §2.1.1 那个形状：
> 判据自己坏了，比没有判据更糟 —— 它会让人开始不看报告）：
>
> 1. 抽「围栏块」的正则把**闭合围栏**当成了**起始围栏**，于是 ```` ```python ```` 块的收尾
>    开了一个新块、三个正文块全被错位切开 —— **判据对正确的输出也报红**。
>    判据已收进 `.check.py` 的 `bare_blocks()` 注释：**带语言标注的围栏只负责开块，它自己绝不是一个可抽取的块。**
> 2. 第一版写 `assert len(裸围栏块) == 3`，于是**本文档自己第三节那个「围栏读数块」**
>    把它顶红了 —— 加完回验段、检查器当场变红。
>    判据改成**按内容挑块**（只取以 `【审查结论：` 开头的块），不再钉在「文档里有几个围栏」上。

---

## 四 · 复现

```bash
# PRD 基线（L3 必须过：上游 = 落盘副本 = 指纹）
python3 tools/verify_prd_baseline.py

# PRD §5.3 原文
sed -n '184,263p' PRD/feishu/内容审查Agent-PRD-v1.0.md

# 引擎产出（问题的真正产地）
sed -n '212,234p' "$KB/kb/l7/review-engine/core/review_engine.py"

# KB 侧那条 5.3 判据（注意：它只查到「共发现」为止，且输入是自验夹具）
sed -n '112,124p' "$KB/kb/.work/l7_integrity.py"

# KB 权威输出模板与受控分类词表
sed -n '1,60p' "$KB/kb/l7/output_template.md"
grep -n "催乳与通乳\|医生专家推荐\|静音绝对化" "$KB/kb/l7/skills/kb-content-review/references/categories.md"

# 责任位（未配置 —— 所以 @ 不出去，不许编人名）
python3 -c "import json;print(json.load(open('$KB/kb/l7/registry/l7.json'))['approvers'])"
```

（`KB=/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理`）

---

## 五 · 已落成硬约束（2026-10-06，Owner 选定「落成硬约束」）

### 5.1 两层，缺一层都不算修好（§2.4.2 的「判据 + 触发者」）

| 层 | 改了什么 | 落在哪 |
|---|---|---|
| **生产者** | 引擎的 REVIEW / BLOCK 措辞**分开**（原先是同一句话）；逐条四要素补齐（类别-子类 · 位置 · 引文 · 原因 · 依据 · 锚点 · 判定 · 建议）；责任人从 `l7.json` 的 `approvers` 读，**未配置就写「（未配置）」不编人名** | `kb/l7/review-engine/core/review_engine.py`（库侧） |
| **判据** | PRD §5.3 的逐字措辞判据（`conforms`）+ 权威结论行的三个来源（`deriveVerdictLine`） | `tools/agent/prd53.mjs`（新） |
| **执行点** | 结论行**由代码搬进卡片的结论格**，模型的措辞不再参与这一格（同 §2.5「模型不写卡片 JSON」那条分工） | `tools/reply-cards/envelope.mjs` 的 `applyVerdictLine()` |
| **触发者** | 内核算出权威结论行 → `meta.verdict53` → `ws_daemon.replyTo` → `toCardOrText`，全部走**唯一**那条发送路径 | `agent/agent.mjs` · `ws_daemon.mjs` |
| **判据也要盖住真产出** | KB 那条 `template_conformance` 原先**只查自验夹具**；新增 `template_from_engine` 把引擎**真的调起来**，三态各断言一次 | `kb/.work/l7_integrity.py`（库侧） |
| **行为级断言** | 第 20 组 8 条（W1–W8），含 4 条反向对照 | `tools/test_agent.mjs` |

### 5.2 端到端回放：拿**真实的三条**跑一遍修完的代码

```
✅ ① PASS   权威行（来自 chain，措辞合规）：【审查结论：PASS】未发现已知底线风险，可转交 @sign-off 责任人（未配置） 进行 sign-off。
            落点：forced → title ｜ 原标题那句「未命中 ≠ 合规」✅ 折进折叠区，一个字没丢
✅ ② BLOCK  权威行（来自 p0-fastpath，措辞合规）：【审查结论：BLOCK】共发现 2 处必须修改。
            落点：forced → title（P0 快路的抬头是**来路标注**，不是 5.3 的结论行 ⇒ 按 §5.3.3 派生）
✅ ③ REVIEW 权威行（来自 chain，措辞合规）：【审查结论：REVIEW】共发现 1 处需人工确认。
            落点：forced → verdict（`evidence` 卡没有 title，结论格就是 verdict）
```

复现（脚本在 `/tmp`，不落库；落地版判据是 `tools/test_agent.mjs` 第 20 组）：

```bash
node /tmp/replay53.mjs     # rc=0
```

### 5.3 自证读数（改前 → 改后）

| 自证 | 改前 | 改后 |
|---|---|---|
| `node tools/verify_cards.mjs` | 254 项全过 | **256 项全过**（+L5 两条反向对照） |
| `node tools/test_agent.mjs` | 101 项全过 | **109 项全过**（+第 20 组 8 条） |
| `python3 tools/verify_depad.py` | 全绿 | 全绿 |
| `kb/.work/l7_integrity.py` 的 `template_conformance` | 6 项全过（**但只查夹具**） | 6 项全过 + `template_from_engine` 7 项全过 |
| `python3 tools/verify_prd_baseline.py` | 15 项红（既有） | **15 项红（既有，与本次无关）** |
| `python3 tools/verify_outbound.py` | 11 项红（既有） | **11 项红（既有 —— 已用「撤掉本次改动再跑」证明同数）** |

### 5.4 路上逮到的三个真缺陷（都不是「顺手」发现的，是判据逼出来的）

1. **`foldIn` 的字段类型由「模型给没给」决定** —— `query-answer` 的 `evidence` 构造器要 `d.evidence.join('\n')`，
   而模型没给 evidence 时折叠一次就写成字符串 ⇒ **整张卡建崩、降级成纯文本**。
   这条路径一直都在，只是此前没有用例把「模型不给 evidence」和「块外有正文」凑到一起。
   逮到它的是第 20 组 **W3**。修法：把数组型折叠字段写成表（`FOLD_IS_ARRAY`），类型由表决定。
2. **`verify_cards.mjs` 的 L5「内核不碰卡片」被注释绊红** —— 我往 `agent.mjs` 加了一句解释
   「结论行怎么交到信封层」的注释，里面写着 `toCardOrText`，于是**内核一行卡片逻辑都没有，L5 却红了**。
   这是同一个坑的**第二次**（09-22 那次红的是 L3）。按 `AGENTS.md` §2.4.4 的既定修法：
   **不是把注释改得更绕，是给扫描器统一一条读法** —— 剥注释后再扫，并补上它一直缺的**两条反向对照**
   （喂真代码必须命中 / 喂注释必须不命中）。
3. **用 Python 的 `write_text` 改那三份文档 → 触发填充态（+4096B）** ——
   正是 `PMO/填充态-环境特性-实测史.md` 记过的那一格。`verify_depad.py` 当场抓到，已 `--fix` 修好；
   后续写 `.json` 一律改回 **Node**。

### 5.5 ★ 还没生效：**守衡跑的还是旧代码**

Node 不热重载 —— 上面这些代码改动**要重启守衡才生效**。
按 `AGENTS.md` §2.7，重启只许走闸门（先跑不带 `--yes` 的那条，把人念的东西念出来，得到明确同意再带 `--yes`）：

```bash
bash tools/restart_shouheng.sh            # 只报告影响面，拒绝（退 3）
bash tools/restart_shouheng.sh --yes --why="PRD §5.3 结论行的执行点已接线并自证全绿"
```

⚠️ 重启窗口里群里发的消息**不会被回答，也不会留下任何记录**（事件从长连接推进来，进程不在就是丢了）。

---

## 六 · 补记（2026-10-06 09:0x）：**「四层评审链」与「P0 快路」是两套渲染器**

Owner 拿 PRD §5.3.3 的模板对照实发的 BLOCK 卡片，指出**抬头对、逐条四要素整块没有**。
核下来的结论：**上一轮那批改动只改到了两套渲染器里的一套。**

| PRD §5.3.3 | 四层评审链 `review_engine.py` | **P0 快路 `p0_fastpath.py`** |
|---|---|---|
| `【审查结论：BLOCK】共发现 N 处必须修改。` | ✅ 上轮已改 | ✅ 载体强制派生（`来自 p0-fastpath｜落点=forced·title`） |
| 逐条四要素 | ✅ 上轮已改 | ❌ **从未出过 §5.3 格式**，只出「四段溯源表格」 |
| `请修改后重新提交。` | ✅ 上轮已改 | ❌ 只有「下一步：按 PRD §5.3，BLOCK 需…」 |

**AND 卡片正文由模型转述** —— 生产者出对了也会被压成一句。所以两层都补：

### 6.1 生产者（`kb/l5/p0_fastpath.py`，子进程 ⇒ **改完即时生效，不需重启**）

- `_five_three_block()`：先出 §5.3.3 的逐条块，**再**接「来路与边界」+「附：四段溯源明细」（原有内容一条不丢）。
- `【类别-子类】` 取自**受控词表**（`kb/l7/registry/l7.json` 的 `vocabulary`）—— `categories.md` 自己写着「本文件是它的可读投影，口径以 registry 为准」。
- `原因 / 库名 / 版本` 按 **`rule_id`** 查 L3（`rule_code` 全库不唯一，`REDLINE-CLAUSE-MAP` 明写）。
- **建议那一格**改成按命中的片段挑那一组修订建议：原先填的 `suggested_replacement` 是该 rule_code 下**所有修订组的拼接**（W-1.18 连着 34 组、几千字），会把卡片撑爆。
- 新增 `--selftest`（**这条红线路径此前一条自证都没有**）：15 项，样本是真实送审，含 3 条反向对照。

### 6.2 载体（`tools/agent/prd53.mjs` + `tools/reply-cards/envelope.mjs`）

- `conclusionBlock()`：从结论行到**动作行**（含）抠出整块；没有动作行 ⇒ 回 `null`（**不搬半截**）。
- `applyVerdictLine()` 现在把**逐条块**也搬进卡片正文（`reasoning`，`evidence` 类走 `groups` 首组），模型自己那句话**接在块后面不丢**。
- 日志加读数：`｜逐条块=forced·reasoning`。

### 6.3 过程中自己踩到并修掉的三处

1. **自证会崩**：表头不合规时 `re.search(...).group(1)` 抛 `AttributeError` —— 退 1 但**后面 4 条一条没跑**，看着像红、其实什么都没判。改成「记一条失败、继续跑」。
2. **指针指向空处**：`_with_pointer` 自己去 L3 摸 `article_no`，而那格是空的 ⇒ 写出 `rules.jsonl#（无条款号）`。改成由 `clause` 传入，并补断言 ⑥c（指针号必须与「依据」行一致）。
3. **重复边界**：`tools.mjs` 又写了一遍「本单走的是 P0 快路…未跑层前置…」，与渲染器自带的整节重复（模型当两句分别转述）。已收掉，只留渲染器没有的耗时/条数。

### 6.4 读数

| 自证 | 读数 |
|---|---|
| `sh kb/kbpy l5/p0_fastpath.py --selftest` | **15/15**（变异：抬头改回旧格式 → rc=1、4 条具名失败） |
| `node tools/test_agent.mjs` | **111/111**（新增 W9 逐条块进正文 / W10 PASS 不许硬塞空块） |
| `node tools/verify_cards.mjs` | 258/258 |
| 快路端到端耗时 | **0.10–0.11 s**（PRD §12 要求 ≤1 s） |
