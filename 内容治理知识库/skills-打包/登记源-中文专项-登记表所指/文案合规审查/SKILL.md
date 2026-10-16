---
name: 文案合规审查
description: |
  审查文字类素材（listing、详情页、社媒文案、字幕、口播转写）的广告法与平台合规：广告用语、绝对化用语、违规宣称、背书表述与措辞风险。触发词：文案合规审查、文字合规、文案审查、listing 文案、详情页文案、社媒文案、广告用语、广告法风险、违规宣称、绝对化用语、踩线的说法、背书表述、措辞合不合规、字幕有没有问题、口播转写里有没有问题、这段文字审一下、把文案筛一遍、text compliance、caption review。何时不用：图片素材（走 图片安全审查）、视频画面（走 视频安全审查）、产品宣称真伪与 SKU 事实、认证范围（走 产品宣称核验）、要依据是什么、条款号多少（走 kb-content-review）。

  Review US-market captions, listings, PDP copy, social copy, OCR text, subtitles, and voice transcripts for advertising, safety, product-claim, endorsement, and wording risks.
version: "1.0.0"
complexity: "complex"
enabled: "true"
user-invocable: true
---

# Brand Text Compliance Review

Extract claims before editing language. Use `~/.dsh/Momcozy知识库/kb/l7/review-engine/core/rule_engine.py` for deterministic candidate scanning, then check medical or health implications, safety promises, absolute or ranking language, unsupported numbers, testimonials and endorsements, required disclosures, product/model accuracy, and channel-specific restrictions.

Every finding must include the original text, exact location, risk type, priority tier, reason, evidence reference, and suggested action. Use `copy-editor` only for P3 clarity and wording suggestions; it must not override legal, medical, safety, or product-fact findings.

When context changes the meaning of a flagged phrase, mark it `uncertain` and route REVIEW. Do not block a phrase merely because a token appears in a negation, warning, quote, or comparison.

---

## 判据的两条来源（**两条都必须跑**，2026-09-30 实测补）

1. **候选扫描**：`python3 kb/l7/review-engine/core/rule_engine.py "<text>" [--product-line … --channel …]`
   —— 它只有 **5 条** US 种子规则（`treat / cure / prevent / eliminates germs / safe for baby /
   sponsored / paid partnership / affiliate / doctor recommends / IBCLC recommends`），
   输出的是**候选**（`status: uncertain`、`action: review`），**不是结论**。
2. **依据（真正的判据主体）**：走 `kb-content-review` 的检索协议 ——
   P0 匹配（`kb/l5/matcher.py`）→ 规则层 509 条（`kb/l3/candidates/rules.jsonl`）→ BM25（`kb/l6/retriever.py`），
   每条结论都要带**条款号 + anchor + source_sha256 + 逐字摘录**。

### 为什么两条都跑（实测，不是理论）

同一段文案 `FDA approved breast pump. Hospital grade. 100% safe and pain-free. Mimics baby natural nursing to boost supply.`：

| 只跑 | 结果 |
|---|---|
| 第 1 条（候选扫描） | **0 候选**（这段里没有那 10 个种子词） |
| 第 2 条（509 条规则 + P0 + BM25） | **10 处 BLOCK**，条款号 W-1.6 / W-1.8 / W-1.11 / W-1.18 / W-1.19 / W-1.22 / W-1.31 / W-1.33 / W-1.35 / W-1.53 |

→ **「候选 0 条」不等于合规**。只凭第 1 条给 PASS = **漏放**（该拦的没拦）。
→ 验收判据：**没有第 2 条的依据，不得输出 PASS**；第 1 条只用来补充 P0 优先级与渠道/品线适用性。

### 两个已知坑

- `--product-line` / `--channel` 的取值必须用 `seed-rules.json` 里的**词表原样**
  （品线：`吸奶器` / `Baby Monitor` / `Bottle Washer`；渠道：`Amazon` / `Google` / `Instagram` /
  `TikTok` / `YouTube` / `独立站`）。写错（例：传 `breast pump` 而不是 `吸奶器`）会把**所有规则过滤掉**，
  得到 0 候选 —— 实测踩过。
- 结论里的**库名**只能写知识库真实存在的四类库（当前引用一律《措辞表达库》），
  不许写《合规措辞库》这类不存在的库名。

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
      --decision-owner 文案合规审查          # 判定主体；缺席 ⇒ NEEDS_INPUT（2026-10-03 起默认要求）
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
