---
name: 图片安全审查
description: |
  审查图片素材：图上文字与 OCR 内容、产品与场景准确性、婴幼儿安全（安全座椅/睡眠/喂养/洗浴等）、隐私与孩子出镜，产出带区域证据的结论。触发词：图片安全审查、图片审查、主图能过审吗、审一下图片、图片有没有合规问题、图片合规、婴幼儿安全、图里的场景、产品用法有没有风险、主图上的文字、图上识别出来的内容、孩子出镜、图片隐私、素材图、image safety、image review。何时不用：视频画面（走 视频安全审查）、纯文字（走 文案合规审查）、多条发现汇总裁决（走 审查裁决）。⚠️ **只问「授权 / 肖像 / 商标 / 儿童出镜授权」而不问画面本身**（例如「这张图里的人物肖像授权范围覆盖到这次投放吗」）→ 走 **AI溯源与权利审查**，本 skill 不接：本 skill 管的是**画面本身**的安全与内容风险，不是**权利归属**。

  Review US-market brand images for OCR text, product and scene accuracy, infant and child safety, privacy, AI provenance, endorsement, and other locatable content risks.
version: "1.0.0"
complexity: "complex"
enabled: "true"
user-invocable: true
---

# Brand Image Safety Review

Use the provider-neutral contract in `~/.dsh/Momcozy知识库/kb/l7/review-engine/knowledge-base/multimodal-provider-contract.json` for OCR, object, person, activity, and scene observations. A vendor adapter may use `vision-analysis` or another provider, but it must return the material hash, provider version, coverage status, and region evidence. Add domain rules for car seats, sleep, feeding, washing, bathing, household power, infant handling, privacy, and AI-generated or composited scenes.

Record bounding-box or region descriptions and the image hash for each finding. Pass OCR and textual visual observations through `~/.dsh/Momcozy知识库/kb/l7/review-engine/core/product_fact_integration.py` when the submission has a SKU, so unapproved product claims become REVIEW and missing evidence becomes NEEDS_INPUT. Separate observation from interpretation: “infant is on an adult bed” is evidence; the safety classification and applicable rule are a subsequent finding.

If the image is too small, occluded, or ambiguous to establish a safety fact, emit REVIEW or NEEDS_INPUT rather than PASS. Do not judge aesthetics, typography, or color unless they create a safety, claim, or platform-policy issue.

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
      --decision-owner 图片安全审查          # 判定主体；缺席 ⇒ NEEDS_INPUT（2026-10-03 起默认要求）
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
