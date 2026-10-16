---
name: 美国本地化审查
description: |
  审查美国市场的本地化表达：计量单位、育儿语境、美式英语地道度、直译腔与文化歧义。触发词：美国本地化审查、美国本地化、美式英语、计量单位、毫升、盎司、单位换算、育儿语境、文化歧义、文化误解、直译腔、美国消费者能看懂吗、本地习惯、读着别扭、localization、locale review。何时不用：广告法与措辞合规（走 文案合规审查）、整体能否发布（走 内容审查总控）、产品宣称真伪（走 产品宣称核验）。

  Review US English, units, parenting context, creator language, ambiguity, and cultural or local-market issues that could change consumer understanding or create brand risk.
version: "1.0.0"
complexity: "complex"
enabled: "true"
user-invocable: true
---

# Brand Us Locale Cultural Review

Check whether wording, units, dates, age ranges, safety terms, caregiver roles, creator slang, or implied context would be understood by a US audience as intended. Distinguish harmless style preference from a material misunderstanding, safety implication, or platform-policy issue.

Preserve the original wording, the US interpretation, and the reason the interpretation matters. Route ambiguous or culturally dependent cases to the North America reviewer. Do not use this skill to judge visual taste or to rewrite copy for conversion.

## 必读基线（2026-10-13 加）

本 skill 的判定**必须落在证据上**，不许凭模型常识自由发挥。两处基线在 `references/`：

| 文件 | 内容 | 语料（可回源） | 什么时候读 |
|---|---|---|---|
| `references/us-locale-baseline.md` | **怎么说**：计量单位（正文语域 vs 规格表语域）、温度、美式拼写、美国语境锚点 | 品牌美国站博客 **164 篇 / 1,659,599 字**（`momcozy.com/blogs/*.atom`） | 判**表达形态**时读（单位、拼写、用词） |
| `references/us-locale-baseline-2-judgments.md` | **说什么 / 不说什么**：6 类判例（禁说 vs 可说、产品名全称与首现、个人体验优先、反广告感叙事、横评不站队、CTA） | 客户与钛动对 **5 份达人稿**的 **47 条**实际反馈（`kb/l0/snapshots/`） | 判**内容口径与文化适配**时读 |

**能力边界（照实说，别把本 skill 当全能）**：

- ✅ **判得了**：一段**英文**够不够美国（单位顺序、拼写、语境锚点、是否像广告、是否站队）。
- ⚠️ **判得弱**：**中文直译成英文行不行** —— references 语料是母语者原生英文，
  **直译腔的负样本为零**（专家扫 5 类直译信号，全语料 **0 处**）。
  判这类问题时**必须写明依据不足**，别给强结论。
- ❌ **判不了**：**文化禁忌**（语料只有"说了什么"，没有"不说什么"）⇒ 禁忌类**转人工**，
  **不许**用常识补。
- ⚠️ **两条判例里的红线的定位**：`references/…-2-judgments.md` 的 **R1 禁说 vs 可说**
  是**品牌内容口径**，**不是**平台政策、**不是**法务结论、**不是**已发号条款。
  引用时把它**降格**成"客户曾这么要求"，**不许升格**成合规依据 —— 合规归 文案合规审查。

**与引擎拒答的关系**：references 缺失/读不到 ⇒ 按「**无基线**」判，并在结论里**明写"未使用 references"**；
**不许**因为读不到就凭常识给强结论。

## 强制链路（2026-10-03 起，**默认动作，用户不必提醒**）

用户只丢一句「这个能过审吗 / 审一下」＋素材时，**下面三跳必须自己走完**，
不许回头追问元数据、不许只给本地报告、不许停在"结论已出、还没发"：

```bash
cd <库根>                                   # kb/ 的上一级
BASE=$(date +%Y%m%d-%H%M)
# ① 四层前置（L4→L5→L6→L7）**一次执行跑完**（2026-10-05 起，不再逐层起 subagent）：
bash kb/l8/review_preflight.sh --base "$BASE" --session "$DSH_SESSION_ID"
#    层→skill 现读 layers.yaml；每层仍是自己的 RUN（<BASE>-L4…-L7）；跑法真源 = kb-review §1.5

# ②+③ 出结论 + **自动发飞书**（一条命令；发布是**引擎默认**，无需 flag；
#      --content-id 不给就自动生成 AUTO-<content_version 前 12 位>）
sh kb/kbpy l7/review-engine/core/with_kb_evidence.py --text "<素材原文>" \
    --require-layer-preflight $BASE \
      --decision-owner 美国本地化审查          # 判定主体；缺席 ⇒ NEEDS_INPUT（2026-10-03 起默认要求）
      # 发布默认开；要关才加 --no-publish-to-feishu
```

- **层前置**：不给 BASE 引擎**自己拒答**（NEEDS_INPUT / 退出码 3）—— 跳不过去。
- **判定主体**：`--decision-owner <本 skill 的 name>` 同样**默认要求**（2026-10-03 加）——
  层前置只证明「**证据管道**通了」，**不证明「有人按专项规程判过」**（实测：四层审计全绿而判定主体缺席，报告照样出）。
  缺席 ⇒ 引擎拒答（NEEDS_INPUT / 退出码 3），**发布件也拒发**；显式豁免写 `--allow-no-decision-owner`。
  跑法见 `kb-review §1.5`（六件事 + 逐层 RUN + **四条**审计红 0 —— L4/L5/L6/L7，2026-10-03 起四层齐平，L7 也在闸门内）。
- **发布**：引擎**默认**就调 `feishu_publish.py --apply`（**不存在** `--publish-to-feishu` 这个开关；要关才加 `--no-publish-to-feishu`，结论里会留 `publish.published=false`），写**云文档**（正文**从第 1 行开始**）
  ＋「内容治理」多维表格行（按 内容 ID upsert，重复发布不新增）。
- **元数据自动化**：内容 ID / 渠道 / 产品线 / 版本**都不必问用户** —— 缺省分别是
  `AUTO-<content_version 前 12 位>` / `未指定` / `未指定` / `v1.0`，人工复核时再补。
- **例外**：结论是 `NEEDS_INPUT` 时**不发**（没有结论可发）；发布失败要如实报"没发出去"，不许当成功。
