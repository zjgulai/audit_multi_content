---
name: 内容审查总控
description: |
  组织一次完整的发布前内容审查：串起送审、各专项检查、裁决与报告，对一批文字/图片/视频素材给出带证据的最终结论（PASS / REVIEW / BLOCK / NEEDS_INPUT）并指明该找谁。触发词：内容审查总控、发布前审查、送审、走一遍审查、审查全流程、从收素材到出结论、统一结论、最终结论、这批素材一起审、文字图片视频一起审、汇总成一个能不能发的判定、带证据的结论、该找谁、content review agent、pre-publication review。何时不用：只问一段文字能不能发（走 文案合规审查）、要依据条款 / 条款号（走 kb-content-review）、单一素材的专项检查（走 文案合规审查 / 图片安全审查 / 视频安全审查）、送审信息登记（走 送审登记）、把发现汇总裁决（走 审查裁决）。

  Orchestrate local pre-publication review of US-market brand text, image, and video assets for breast pumps, baby monitors, bottle washers, and feeding products. Use when a submission needs versioned PASS, REVIEW, BLOCK, or NEEDS_INPUT decisions, evidence, and human routing.
version: "1.1.1"
last_updated: "2026-10-15"
complexity: "complex"
enabled: "true"
user-invocable: true
---

# Brand Content Review Agent

Use this skill as the workflow entry point. Keep the review core independent from Feishu, model vendors, and storage providers.

## Layer pre-stage (mandatory — runs before any decision)

The publisher-side pre-stage is **not optional and not modality-dependent**: it runs for every submission,
whichever specialist ends up deciding. It prepares evidence; it never decides.

`kb_pipeline.py --via-skill` does **not** call layer skills — it only runs gates, writes the ledger, and
**echoes the `layers.yaml` declarations** into `kb/l7/runs/<RUN>.json`. That field looks identical whether or
not anything was actually loaded (`kb/l7/scripts/skill_invocation_audit.py`), so the pre-stage means:
**load each layer skill with the skill tool first (in the executing session — one execution may cover all four layers), then execute that layer's engines.**

```bash
BASE=$(date +%Y%m%d-%H%M); cd <kb root>          # the parent directory of kb/
for L in L4 L5 L6; do
  RUN=$BASE-$L
  kb/kbpy l7/scripts/kb_pipeline.py --sync --via-skill --only $L --gate-only --run $RUN
  # load layers.yaml Lx.skill via the skill tool -> run the Lx.engine entries ->
  # the process executing the layer writes the stamp kb/lx/runs/<RUN>*.json with --skill <skill-id>
  kb/kbpy l7/scripts/kb_pipeline.py --sync --via-skill --only $L --run $RUN \
      --invoked <skill-id> --skill-session $L=<session-id>
done
kb/kbpy l7/scripts/kb_pipeline.py --sync --via-skill --only L7 --run $BASE-L7    # cross-layer gate: separate run
for R in $BASE-L4 $BASE-L5 $BASE-L6; do kb/kbpy l7/scripts/skill_invocation_audit.py --run $R; done
```

- One RUN id per layer (`<BASE>-L4` / `-L5` / `-L6` / `-L7`): `kb/l7/runs/<RUN>.json` is a single file and a
  multi-layer RUN is overwritten by the last layer, which hides the other layers from the audit.
- Read the layer skill and the engine list from `kb/l7/registry/layers.yaml`; never hard-code them.
- Hard stop: a **red** audit means no decision and no report — go back and actually load + run that layer.
  Yellow `E5` (dry-run stamps) allows a decision, but the report must state that the run produced mechanism
  evidence only; `--apply` needs a separate write approval.
- Wired (2026-10-03): the CLI now **requires** the layer pre-stage by default — pass
  `--require-layer-preflight <BASE>` to `kb/l7/review-engine/core/with_kb_evidence.py`. It re-runs
  `skill_invocation_audit.py` per layer and returns `NEEDS_INPUT` (exit 3) without a three-state conclusion when any
  layer is red **or when no BASE is given**. The audit stays the single ruler; no seventh ruler is created.
  To skip it deliberately, say so explicitly with `--allow-no-layer-preflight`; the payload then records
  `layer_preflight.mode=waived_by_caller` — absence must stay visible.
- Wired (2026-10-03, **second gate**): the CLI also **requires the decision owner** — pass
  `--decision-owner <skill-id>` (the specialist named by kb-review's hand-off table, e.g. `图片安全审查`).
  The layer pre-stage proves the **evidence pipeline** ran; it does **not** prove a specialist judged.
  Measured the same day: all four layer audits green while the hand-off table's owner was **never loaded**,
  and the report still went out. Missing owner ⇒ `NEEDS_INPUT` (exit 3) **and the publisher refuses too**
  — "cannot publish" is a signal you can see the same day. Deliberate skip: `--allow-no-decision-owner`
  (records `evidence_meta.decision_owner.mode=waived_by_caller`; absence must stay visible).
- Never author a new gate script for this (library rule: do not build a seventh ruler); check layer stamps by hand.
- Machine entry (`kb_api.py`, `:8787/review`): the bot cannot load skills, so it passes the agent-side BASE as
  `layer_preflight_base` and re-checks it (red ⇒ HTTP 409); without it the response records
  `layer_preflight.mode=waived_by_api` — never use such a conclusion as the basis for PASS.

## Workflow

1. Validate the review payload against `~/.dsh/Momcozy知识库/kb/l7/review-engine/contracts/review-contract.json`.
2. Preserve the input file hash, content version, product line, channel, SKU, and source permissions.
3. Run the relevant modality adapters. They must emit locatable evidence and risk items; they must not decide the final state. For an offline OCR/ASR/keyframe result, use `~/.dsh/Momcozy知识库/kb/l7/review-engine/core/offline_review.py` with `~/.dsh/Momcozy知识库/kb/l7/review-engine/contracts/offline-extraction-result.json`.
4. Run the product-fact gate on claims found in any text, OCR, ASR, or visual extraction before running `brand-review-decision-engine` through `~/.dsh/Momcozy知识库/kb/l7/review-engine/core/review_engine.py`.
   For a text-only smoke test, use `~/.dsh/Momcozy知识库/kb/l7/review-engine/core/review_text.py` to combine the seed scanner and the decision engine.
5. Generate the concise summary and detailed evidence report with `brand-review-report-memory`.
6. Route PASS to sign-off, REVIEW to the relevant specialist, BLOCK back to the submitter, and NEEDS_INPUT back for missing material or metadata.
7. Store the decision with agent, rule, knowledge, model, input hash, and release hash versions.
8. **Publish to Feishu (the engine's default, 2026-10-03 — the user does not have to ask for it).** No flag is
   needed; `--no-publish-to-feishu` opts out. The engine calls `kb/l7/review-engine/core/feishu_publish.py --apply`, writing the cloud doc
   (the report title is the **first line**, body starts there) and upserting the row in the registered
   multidimensional table (keyed on `内容 ID`, so republishing never duplicates).
   Metadata is auto-filled — `AUTO-<content_version[:12]>`, "未指定", "v1.0" — **never ask the submitter for it**.
   A `NEEDS_INPUT` verdict is not published, and a failed publish must be reported as "not published".

## Hard gates

- Never emit PASS when required modality extraction, SKU scope, evidence, permissions, or release-version matching is incomplete.
- Run the layer pre-stage (L4 → L5 → L6 → L7) for every submission. A decision whose three layer runs have not
  passed `skill_invocation_audit` (red 0) is not a decision — it is an opinion.
- Treat P0 keyword hits as candidates until context and evidence are resolved.
- P3 wording suggestions never change the main decision.
- Human conclusions are feedback candidates until an owner approves a rule or sample update.

Read `~/.dsh/Momcozy知识库/kb/l7/review-engine/contracts/review-contract.json` for the shared payload and `~/.dsh/Momcozy知识库/kb/l7/review-engine/PLAN.md` for the workflow boundaries.
---

## 会话蒸馏回灌（2026-10-15）

本 skill 的知识面由**会话蒸馏**持续回灌，两个文件：

- `references/会话蒸馏回灌.md` —— 从 2026-10-05~10-15 的 DSH 会话里蒸出来的
  **可执行动作 / 禁止动作 / 风险点**，每条都带**可回源的依据指针**（`case_id` + `会话:seq` + 逐字引文）。
- `references/自生长台账.md` —— 每轮长了什么、回验过没过、闸门结果。

**怎么用**：

- 处理相关任务**之前**先读这两个文件 —— 里面是别人真踩过的形状，不是通用建议。
- 它们**不修改本 skill 的任何指令**：**与上文任何一条冲突时，以上文为准**。
- 里面的条目是 **E2（草稿级、可审查、未获批）**，不是已批准的规则；要拿它下结论前先看它的依据指针。

**它怎么长**：每日 04:10 由 `com.kb.skill-growth` 自动**追加**（只追加、不改已有行）。
护栏写在 `kb/l7/registry/skill-growth.yaml`：frontmatter / 触发词 / 正文**机器一律不许改**，
每条指针必须逐字回源，一条不过整轮不写，写完必须过 `skills_check.py` 第 3 类否则回滚。
