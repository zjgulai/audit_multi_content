---
name: 产品宣称核验
description: |
  核对产品宣称与产品事实：比对 SKU 事实库、认证范围、测试报告与已批准表述，判断宣称是否有支撑。触发词：产品宣称核验、宣称核对、产品事实、SKU 事实、认证范围、测试报告支撑、产品数据能证明、产品数据能不能证明、已批准的表述、已批准表述比对、比对一下这条产品宣称、核对这条宣称、这条宣称对得上吗、claim verifier。何时不用：文字措辞合规（走 文案合规审查）、图片（走 图片安全审查）、视频（走 视频安全审查）、登记监管依据（走 证据源维护）。

  Extract and verify product claims in US-market brand content against SKU-level product facts, approved wording, tests, certifications, and model/version scope.
version: "1.0.0"
complexity: "complex"
enabled: "true"
user-invocable: true
---

# Brand Product Claim Verifier

Extract both explicit and reasonably implied claims from copy, OCR, subtitles, voice, and visual demonstrations. Normalize each claim to a type such as feature, performance, safety, health, comparison, certification, ranking, or endorsement.

Compare claims against the approved facts for the submitted SKU and version. The staging queue is `~/.dsh/Momcozy知识库/kb/l7/review-engine/knowledge-base/product-fact-approval-queue.json`; the active library is `~/.dsh/Momcozy知识库/kb/l7/review-engine/knowledge-base/product-fact-library.json`. The confirmed approval matrix is `~/.dsh/Momcozy知识库/kb/l7/review-engine/knowledge-base/product-fact-approval-policy.json`. Use `product_fact_gate` in `~/.dsh/Momcozy知识库/kb/l7/review-engine/core/product_fact_queue.py` before treating a product claim as supported. Discovery facts remain unavailable to automatic PASS until all required owner approvals and approved wording are recorded. Distinguish:

Persist role decisions with `~/.dsh/Momcozy知识库/kb/l7/review-engine/core/product_fact_approval.py`. It appends an idempotent event, updates the queue, and rebuilds the active library from approved entries only.

- `supported`: exact model and evidence match;
- `mismatch`: claim conflicts with the model, region, or approved wording;
- `insufficient_evidence`: claim may be true but the required proof is absent;
- `out_of_scope`: no applicable fact is available.

`mismatch` with reliable evidence can be BLOCK; `insufficient_evidence` and `out_of_scope` default to REVIEW. Never treat a generic product page as proof for a different model.

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
      --decision-owner 产品宣称核验          # 判定主体；缺席 ⇒ NEEDS_INPUT（2026-10-03 起默认要求）
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
