# Feishu Content Review Workflows Implementation Plan

> **For agentic workers:** Use this plan task by task with test-driven development. Tickets below are the implementation backlog and completion checklist.

**Goal:** Deliver a reliable Feishu Q&A and content-review loop for final-content text, images, and URLs.

**Architecture:** Keep `review_gate.mjs` as the executable routing authority, `agent.mjs` as the event/material/chain coordinator, and `ws_daemon.mjs` as Feishu ingress/egress. Document the workflow as a composed project skill, but bind each promise to behavior tests so a skill file cannot drift from runtime behavior.

**Tech Stack:** Node.js ESM, existing Feishu SDK, local JavaScript self-tests, existing Python governance verifiers.

**Spec:** `docs/superpowers/specs/2026-10-20-feishu-content-review-workflows-design.md`

## Global Constraints

- Current user scope is text, image, and link input in Feishu; do not add video, files, batch, NAS, approval dispatch, sign-off, or knowledge-base feedback in this plan.
- Keep the project rule that submitted images and links enter the complete review chain; mechanism questions must remain Q&A and must not be reviewed as their own material.
- Do not report PASS for an unrun chain, missing evidence, unreadable image, inaccessible URL, or empty/malformed review response.
- Preserve the existing card contract and use PRD v1.4 states: PASS, non-blocking SUGGEST, REVIEW, BLOCK.
- Tests must not create live Feishu documents, records, or messages; inject publish/send dependencies or use offline fixtures.
- Preserve all pre-existing worktree changes and untracked files; only stage or edit files explicitly listed in a ticket.
- For each modified subsystem, run its project self-certifier. Record failures that predate this plan instead of hiding or relabeling them.

## Review Focus

- Mechanism question includes review keywords — assert it stays on Q&A path and the review chain is not called.
- Long text contains a URL — assert the text remains the review material and the URL is retained as a link, without relabeling the whole submission as link-only.
- Bare image submission — assert correct message/resource identity is used and OCR/vision failure cannot become PASS.
- Bare URL and text-plus-URL — assert link content is read by the existing tool and body text is preserved.
- Duplicate Feishu event or failed outbound card — assert no duplicate chain and a readable same-conversation fallback remains.

---

## Tickets

### Task 1: FEISHU-01 — Repair stale URL-count and P0 test fixtures

**Files:**
- Modify: `tools/test_agent.mjs` (Z55 only)
- Verify: `tools/agent/prd17.mjs`

**Consumes:** Existing `P17.countChars(text)` contract; URL characters are removed before counting.  
**Produces:** Valid end-to-end assertions proving URL characters do not affect visible character count and the P0 workflow uses a currently active P0 example.

- [x] **Step 1: Confirm current RED**

Run: `node tools/test_agent.mjs`  
Expected: Z55 fails with `链接被算进字数了` because its short line is excluded as an entire link line; this is a stale fixture, not a product-code failure.

- [x] **Step 2: Replace the Z55 and Y8 fixtures only**

For Z55, use a long non-link prefix (at least 30 visible characters) followed by a URL, and compare `countChars(prefix + URL)` with `countChars(prefix)`. For Y8, replace the retired “最好” example with an active P0 medical-claim sample such as “这台吸奶器治疗乳腺炎”; update the matching `Q` and card fixture text. Keep all P0 assertions unchanged. Do not change `prd17.mjs` or the external P0 rule registry.

- [x] **Step 3: Run focused and subsystem verification**

Run: `node tools/agent/prd17.mjs --selftest`  
Expected: all module self-tests pass, including direct URL stripping and whole-link-line exclusion.

Run: `node tools/test_agent.mjs`  
Expected: Z55 and Y8 pass; the full suite reports no new failures. If the external ruleset changes again, the exact hit result must be checked before updating the sample.

### Task 2: FEISHU-02 — Add a project-owned Feishu content-review workflow skill

**Files:**
- Create: `agent-skills/飞书内容审核工作流/SKILL.md`
- Modify: `agent-skills/内容合规审查/SKILL.md`
- Modify: `agent-skills/守衡语域/SKILL.md`
- Modify: `tools/verify_skill.py`
- Verify: `tools/verify_cards.mjs`

**Consumes:** Spec sections 2–5; runtime behavior in `review_gate.mjs`, `agent.mjs`, `persona.mjs`.  
**Produces:** A workflow skill with exact Q&A/review branches, three input procedures, failure states, responsibility links, and verifier-backed consistency claims.

- [x] **Step 1: Add behavior and consistency checks before doc edits**

Add `verify_skill.py` assertions that the new workflow skill names the code-owned routing authority, names all three in-scope modalities, distinguishes Q&A from review, and states that unreadable/untested input cannot be reported PASS. Add a test for the separate judging-state vs Feishu business-state terminology.

Run: `python3 tools/verify_skill.py --controls`  
Expected: existing controls remain green and each newly added negative fixture is rejected.

- [x] **Step 2: Verify RED on the missing workflow skill**

Run: `python3 tools/verify_skill.py`  
Expected: exit 2 (not tracked / not present) or the named consistency assertion fails; it must not claim the missing workflow skill is valid.

- [x] **Step 3: Add and align the three skill documents**

Keep `内容合规审查` focused on policy/evidence judgment; distinguish local engine disposition layers from PRD business outcomes. Keep `守衡语域` focused on reply expression. Put message ingress, Q&A-vs-review choice, modality steps, failure handling, and exact code/test map in the new workflow skill.

- [x] **Step 4: Run skill self-certification**

Run: `python3 tools/verify_skill.py` and `node tools/verify_cards.mjs`  
Expected: every command in the content skill matches its declared exit expectation; workflow consistency checks pass; card/style contracts remain green.

### Task 3: FEISHU-03 — Add a focused workflow contract test for text, image, link, and Q&A

**Files:**
- Create: `tools/agent/review_workflow.test.mjs`, `tools/agent/link_reader.test.mjs`
- Create: `tools/agent/link_reader.mjs`
- Verify: `tools/agent/review_gate.mjs`, `tools/agent/agent.mjs`
- Modify: `tools/test_agent.mjs` only if this focused test exposes a missing top-level runner hook.

**Consumes:** `isSubmission({ text, imageCount, videoCount })`, `mechanismQuestion(text)`, and `chainInput({ question, inbound })`.  
**Produces:** A deterministic offline contract suite proving routing and material preservation, without calling Feishu or model services.

- [x] **Step 1: Write tests first**

Cover: mechanism question with review keywords → not submission; explicit text review → text; image-only → media; bare URL → link; long text plus URL → text review with original body and URL both preserved by `chainInput`; unreadable image marker remains explicit; link page body reaches chain input; failed fetch is deterministic non-PASS and does not create review input.

- [x] **Step 2: Run the focused test and confirm expected RED**

Run: `node tools/agent/review_workflow.test.mjs`  
Expected: identify any missing contract. A green first run is valid if existing behavior already meets the contract; an import/setup failure is not a behavior RED.

- [x] **Step 3: Implement only uncovered behavior**

Do not change routing if current implementation satisfies the spec. If behavior is missing, add the smallest change to `review_gate.mjs` or `agent.mjs` and preserve the project requirement that submitted media enters the review chain.

- [x] **Step 4: Run focused test and full Agent suite**

Run: `node tools/agent/review_workflow.test.mjs`  
Expected: every modality and Q&A branch passes.

Run: `node tools/test_agent.mjs`  
Expected: suite output names all remaining failures. Do not claim a clean acceptance while Y8 or any new failure remains.

### Task 4: FEISHU-04 — Implement safe link fetch and fail-closed link review

**Files:** `tools/agent/link_reader.mjs`, `tools/agent/review_gate.mjs`, `tools/agent/agent.mjs`, focused tests.

- [x] Normalize HTTP(S), reject private/local targets, resolve and pin public IP, manually revalidate redirects, enforce timeout/body/content-type limits.
- [x] Inject extracted public page text into link-only review chain. Long text with a URL remains on the text route.
- [x] On read failure, return a deterministic non-PASS response and skip chain/publish; do not guess from URL.
- [x] Verify focused behavior and integrate documentation/skill updates.

### Task 5: FEISHU-05 — Record PRD baseline drift as a separate governance blocker

**Files:**
- Create: `PMO/守衡-飞书三条审核工作流-实施验收-20261020.md`
- Verify: `python3 tools/verify_prd_baseline.py`, `python3 tools/verify_depad.py`

**Consumes:** Current upstream v1.4 read and current repository baseline output.  
**Produces:** An evidence record separating this feature's acceptance from the pre-existing stale local PRD snapshot/reference registry.

- [x] **Step 1: Record the source/version used by this implementation**

Note that upstream v1.4 was fetched read-only on 2026-10-20 and the local snapshot/index still identify v1.2.

- [x] **Step 2: Re-run the PRD verifier and save a concise evidence extract**

Run: `python3 tools/verify_prd_baseline.py`  
Expected: current upstream drift and reference-registry failures are reported as inherited governance failures; this ticket must not rewrite the upstream PRD.

- [x] **Step 3: Record the result in PMO**

Include exact failed groups, next action, and the distinction between feature tests and PRD baseline status. Do not copy thousands of repeated H3 lines into the PMO record.

### Task 6: FEISHU-06 — Run subsystem self-certifiers and prepare live Feishu acceptance

**Files:**
- Modify: no runtime files unless a previous ticket finds a failing behavior.
- Create/update: `PMO/守衡-飞书三条审核工作流-实施验收-20261020.md`

**Consumes:** Tickets FEISHU-01 through FEISHU-04.  
**Produces:** A checklist of test evidence, known failures, and one precise live Feishu test recipe.

- [x] **Step 1: Run applicable self-certifiers**

Run: `node tools/test_agent.mjs`, `node tools/verify_cards.mjs`, `python3 tools/verify_skill.py`, `python3 tools/verify_engine_contract.py`, `python3 tools/verify_kb.py`, `python3 tools/verify_prd_baseline.py`, `python3 tools/verify_pending.py`, and `python3 tools/verify_depad.py`.

- [x] **Step 2: Compare to baseline**

Expected: list pre-existing failures separately from failures introduced by this plan; a previously failing test is not green merely because it did not change.

- [ ] **Step 3: Live test requires explicit target group and outbound authorization**

Use a dedicated test group and four cases: a process Q&A, text review, image review, and URL review. Verify ingress, exact event correlation, one review-chain run, Feishu write/readback, reply placement, and deduplication. Do not send test messages without the user's explicit test-group authorization.

## Execution Notes

- Existing `main` worktree has substantial uncommitted user work, including changes in `agent.mjs`, `tools.mjs`, `ws_daemon.mjs`, review publishing, and untracked image/test fixtures. Do not reset, stash, or overwrite them. New work stays additive and each code edit is scoped to the listed hunk/file.
- Baseline `node tools/test_agent.mjs` was 288 pass / 2 fail: Y8 used “最好” as a P0 sample even though the active external rule registry releases this ranking term; Z55 used a short line that was excluded as a whole link line. FEISHU-01 refreshes both fixtures while preserving their assertions.
- Baseline `node tools/verify_cards.mjs` passed 348 checks. Baseline engine, KB, pending and PRD baseline verifiers had inherited failures. Their exact results are recorded in the spec/PMO evidence; this plan does not claim they are caused by the Feishu workflow.
- FEISHU-03 focused test `node tools/agent/review_workflow.test.mjs` passes 6/6: mechanism Q&A exclusion, text/image/link routing, text-plus-URL preservation, and unreadable-image failure preservation. Existing routing already met the contract, so no runtime routing behavior was changed.
- FEISHU-02 focused workflow check and anti-controls pass 10/10; `node tools/verify_cards.mjs` passes 348/348. Full `python3 tools/verify_skill.py` remains blocked by inherited command failures (#6 `base/verify_base.py`, #7 engine contract, #8 KB verifier, #9 risk-label checker/reference map).
- Final suite snapshot: `node tools/test_agent.mjs` completed at 290/0; `node tools/agent/prd17.mjs --selftest` passes all cases. `verify_engine_contract.py` is 211/212 (V46e); `verify_kb.py` fails E7 for an overdue upstream promise; `verify_pending.py` fails P-02 quote lookup and overdue P-03; `verify_prd_baseline.py` reports 4561 checks / 4538 failures from stale local snapshots and H3 reference mapping. `verify_depad.py --fix` checksum-preserved and repaired all 313 padded files encountered across two scans, leaving one unrelated credential-file size anomaly for manual handling.
- Live Feishu acceptance is authorized for the dedicated group but not yet run; the Mac is currently locked and CUA could not inspect or operate the native Feishu app. No messages or records were sent. The connected Lark `kb_ingest` tool is unavailable in this execution environment; PMO evidence is local, while knowledge-base ingestion remains an explicit operational follow-up.

