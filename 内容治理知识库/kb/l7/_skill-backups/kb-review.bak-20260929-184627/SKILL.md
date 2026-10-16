---
name: kb-review
description: |
  Momcozy 内容治理知识库的**评审链入口**：收到一段待判内容，走评审链给三态结论
  （PASS / REVIEW / BLOCK），并把结论分派给对应的专项成员。
  【先让位】只要能看出**专项归属**，就直接走对应专项，本 skill 不接：
    文字 / 广告用语 / listing、PDP 文案 → brand-text-compliance-review；
    图片 / 主图 / 图上文字 / 婴幼儿画面 → brand-image-safety-review；
    视频 / 短视频 / 画面 / 时间码 / 口播 → brand-video-safety-review（视频安全审查）；
    产品宣称真伪 / SKU 事实 / 认证范围 → brand-product-claim-verifier；
    AI 生成披露 / 肖像商标授权 / 儿童出镜隐私 → brand-ai-provenance-rights-review；
    美国本地化 / 计量单位 / 文化歧义 → brand-us-locale-cultural-review；
    一批素材走发布前审查全流程 → brand-content-review-agent。
  本 skill 承接的是**专项归属不明 / 跨模态 / 只问"整体能不能用"**的那一类：
  当用户说「这段内容能不能发 / 审一下 / 帮我审审 / 合规检查 / 合规审查 / 内容审核 /
  会不会违规 / 能过审吗 / 有没有风险 / 踩线 / 禁用 / 敏感 / 这段能不能用 /
  帮我判一下这条内容 / 该不该拦」而不指明是哪一类专项时使用。
  触发词：内容评审入口、能不能发、审一下、帮我审、合规检查、合规审查、内容审核、
  会不会违规、能过审吗、有没有风险、踩线、禁用、敏感、这段能不能用、kb-review。
  不适用：
    · 跑知识库供给链 / 同步知识库 / L0 到 L7 → 走 **kb-pipeline**；
    · 只对账 L0 / 飞书侧改了什么 → 走 **kb-l0-feishu**；
    · 已给出结论、只追问依据 / 条款号 / 逐字摘录 → 走 **kb-content-review**；
    · 单独查某条规则的条款号 → **kb-canonical-lookup**；是不是 P0 → **kb-p0-check**；
      召回单元 / 查资料 → **kb-recall**；
    · 知识库体检 / 闸门 → **kb-check**；闸门没过的修复 → **kb-repair**；
    · 问这几个 skill 怎么分工 / 注册表 / 路由 → **kb-manage**。
version: "1.0.0"
last_updated: 2026-09-29
license: "Proprietary — Momcozy internal use only"
complexity: "standard"
compatibility:
  claude: { status: "native" }
  kimi: { status: "native" }
  cursor: { status: "native" }
  gpt: { status: "bridge", limitations: ["长依据需分段"] }
  minimax: { status: "bridge", limitations: ["需中文优化"] }
  dsh: { status: "native", notes: "kb_search/kb_read 同机可用" }
  codex: { status: "native" }
---

# kb-review —— 评审链入口

**一句话**：本 skill 是评审链的**入口**，不是审查员。
它的第一动作是**判断该谁接**，第二动作才是承接"没人认领"的那类。

## 0. 第一动作：先让位（这条写在最前面，因为它最容易做错）

```
用户送来待判内容
   │
   ├─ 能识别出专项？──是──▶ 直接走对应 brand-*，本 skill 不接
   │
   └─ 否（专项不明 / 跨模态 / 只问整体能不能用）
          └─▶ 本 skill 承接：走下面 §2 的评审链
```

**让位表**（能识别就交出去，别抢活）：

| 能识别的专项 | 交给谁 |
|---|---|
| 文字 / 广告用语 / listing、PDP / 字幕口播转写 | `brand-text-compliance-review` |
| 图片 / 主图 / 素材图 / 图上文字 / 婴幼儿画面 | `brand-image-safety-review` |
| 视频 / 短视频 / 达人视频 / 画面 / 时间码 | `brand-video-safety-review`（`视频安全审查`） |
| 产品宣称真伪 / SKU 事实 / 认证范围 / 测试报告 | `brand-product-claim-verifier` |
| AI 生成披露 / 换脸 / 肖像商标授权 / 儿童出镜隐私 | `brand-ai-provenance-rights-review` |
| 美国本地化 / 计量单位 / 文化歧义 / 直译腔 | `brand-us-locale-cultural-review` |
| 一批素材的发布前审查全流程（多模态 + 统一结论） | `brand-content-review-agent` |
| 送审登记 / 哈希 / SKU / 渠道采集 | `brand-review-intake-router` |
| 多条发现汇总成最终裁决 / 优先级 / 责任人 | `brand-review-decision-engine` |
| 出报告 / 群发摘要 / 存档留痕 | `brand-review-report-memory` |
| 审查流程本身的准确率 / 漏放评测 | `brand-review-evaluation` |
| 证据源（法规 / 平台政策）维护登记 | `brand-policy-source-curator` |
| 结果同步到飞书 / 多维表格 / 分派 | `brand-feishu-review-adapter` |

**为什么不自己全干**：专项成员各有判据、证据要求与 not_for。入口全干 =
专项成员永远拿不到自己的活（这正是 `brand-text-compliance-review` F1 掉到 0.111 的机制）。

## 1. 第二动作：承接

只有下面三种情况由本 skill 接：

1. **专项归属不明** —— 用户只说"这段能不能用""有没有风险"，看不出是哪一类。
2. **跨模态** —— 一段内容同时含文字 + 图片 + 视频，且用户要**一个**结论。
   （若用户要的是"发布前审查全流程 + 版本留痕"，改走 `brand-content-review-agent`。）
3. **只要一个整体判定** —— 用户不要分项报告，只要"能不能过"。

## 2. 评审链（承接后照这个顺序走）

1. **冻结输入**：记下内容原文、来源、版本、渠道、SKU（有就给）。**改一个字就是新版本。**
2. **定专项**：按 §0 让位表逐类过一遍。**认领不了任何专项**才继续第 3 步。
3. **取依据**：调 `kb-content-review` 的检索协议（L3 规则 → L5 P0 → L6 召回），
   拿条款号 + 锚点 + `source_sha256` + 逐字摘录。
   - 只查条款号 → `kb-canonical-lookup`；只问是不是 P0 → `kb-p0-check`；
     只要召回候选 → `kb-recall`。
4. **给三态结论**：`PASS` / `REVIEW` / `BLOCK`，逐条附依据。
   **依据不足就按 `no_hit_semantics` 拒答，不许拿常识补。**
5. **分派**：BLOCK 退回提交人；REVIEW 交对应专项；PASS 交签核。

## 3. 三条不许

- **不许不检索就答**：没有条款号 + 逐字摘录的结论，算幻觉。
- **不许替专项下判**：认出专项就交出去；替它判 = 它的 F1 归零。
- **不许把"没查到"说成"没问题"**：查不到要明说"知识库查不到"。

## 4. 与其他成员的关系

| 关系 | 成员 | 说明 |
|---|---|---|
| 上游（供给） | `kb-pipeline` | 规则/索引过期时先跑链路，再评审 |
| 链内组件（出依据） | `kb-content-review` | 结论 → 条款号 / 锚点 / 逐字摘录 |
| 只读查询 | `kb-canonical-lookup` / `kb-p0-check` / `kb-recall` | 不写库 |
| 专项成员 | 13 个 `brand-*` | 见 §0 让位表 |
| 家族管理 | `kb-manage` | 路由表变更、成员启停 |

## 5. 何时停下来问人

- 内容里有**看不见的模态**（用户说"还有几张图"但没给）：先要素材，不要凭描述判。
- 结论会是 BLOCK 但依据只有一条 L6 召回（证据级不够）：标 REVIEW + 列出缺什么证据。
- 用户要"改到能过"：那是改写，不是评审，先确认范围再动。
