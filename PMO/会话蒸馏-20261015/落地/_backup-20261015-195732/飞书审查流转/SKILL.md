---
name: 飞书审查流转
description: |
  把审查结果流转到飞书：发群通知、更新多维表格状态、同步文档、按责任人分派与提醒。触发词：飞书审查流转、发到飞书、飞书群里通知、多维表格、回写状态、同步到飞书文档、提醒相关责任人、按责任人分派、推到飞书、飞书侧更新、更新这条内容的审查状态、内容治理群、feishu adapter。何时不用：生成报告正文（走 审查报告与记忆）、做裁决（走 审查裁决）。

  Adapt the local brand review contract to Feishu group mentions, files, multidimensional tables, cloud documents, status updates, and owner routing without coupling Feishu into the review core.
version: "1.0.1"
last_updated: "2026-10-15"
complexity: "complex"
enabled: "true"
user-invocable: true
---

# Brand Feishu Review Adapter

Treat Feishu as a transport and workflow adapter. Convert incoming messages, attachments, URLs, and batch rows into the local review contract; convert engine results into a concise message, a detailed report link, and a table update.

Preserve `review_id`, input hash, content version, and source URL across every write. Use idempotency on `review_id + content_version`; a repeated webhook must not create a second review. Do not place full sensitive media in messages or table cells when a restricted report link is available.

Required adapter capabilities:

- group mention intake;
- file/link permission check;
- multi-dimensional table read/write;
- cloud document report creation or link registration;
- owner mentions for REVIEW and sign-off;
- status update for resubmission and human conclusion.

If no Feishu connector or credentials are available, expose the same interface through JSON files or webhooks. Use `~/.dsh/Momcozy知识库/kb/l7/review-engine/core/feishu_adapter.py` for the local fallback: it writes a chat message, report link, role-placeholder mentions, and multidimensional-table patch with idempotency on `review_id + content_version`. The core engine must remain runnable without Feishu.

## Review → Feishu, wired (2026-10-03)

Publisher: `kb/l7/review-engine/core/feishu_publish.py`. It reads the destination from
`kb/l7/registry/conclusion-destination.yaml` (never hardcode tokens), renders the report, creates or overwrites
the cloud doc, upserts the table row, and then reads both back.

```bash
# 1) dry-run first (default: writes nothing)
sh kb/kbpy l7/review-engine/core/feishu_publish.py --review-json <engine.json> \
    --content-id <ID> --channel <channel> --product-line <line> --version v1.0
# 2) publish
... --apply                        # a new cloud doc per review
... --apply --doc <docx_token>     # overwrite an existing doc (whole-document replace)
```

Hard rules (all learned by measurement, 2026-10-03):

- **Preconditions**: the engine JSON must carry `layer_preflight.mode=enforced` with `ok` and zero reds.
  A `NEEDS_INPUT` verdict is refused — there is no conclusion to publish. `--allow-waived-preflight` exists but
  marks the run as "not L4-L7 evidenced"; never use it for a real submission.
- **Write from the very first line.** Never pass `docs +create --title`: the CLI prepends a title block, so your
  H1 would become a duplicate second line. Put the report title as the **first line of the markdown** — Feishu
  promotes it to the document title and the body starts immediately after it. Writing into an existing doc uses
  `docs +update --command overwrite` (whole-document replace). **Never `append`** — appending *is* "writing from
  the middle", which this flow explicitly forbids.
- **Idempotency**: the row is upserted on `内容 ID` (`+record-search`, then `+record-batch-update` if it exists,
  otherwise `+record-batch-create`), so republishing never creates a duplicate row.
- **Calling lark-cli by hand?** +record-batch-create --json `{"create_records":[{"<field>": <value>}]}` — fields go **flat** on the record object
  (not nested under `fields`), and select values are **arrays** (`"状态":["BLOCK"]`). `lark-cli` lives in
  `~/.dsh/bin` (not on the default PATH), and this destination needs `--profile dsh-kb --as bot`.
- **L0 locator in every finding (2026-10-03)**: the publisher turns the `anchor`
  (`#table/record_id/field`) back into the **L0 source record** and prints its Feishu `entry_url`, the alignment
  time, the in-repo path, and the matching **L2 unit id** — so a reader can click straight through to the source
  data instead of decoding an anchor by hand. The sha shown is a **comparison against the L0 record value, not a
  recomputation**: the L0 hash input is the `record_fields` blob, which is not stored locally
  (`sha256_input` only records that literal), so local recomputation is structurally impossible.
- **Row order (2026-10-03)**: the registered view is sorted by `写入时间` **descending**, and `写入时间` is an auto
  `created_at` field — so a freshly published report shows up as the **first row** of the table. The publisher does
  **not** write that field; ordering is the view's job. (This is a shared view config change: revert with
  `base +view-set-sort --base-token <t> --table-id <t> --view-id <v> --json '{"sort_config":[]}'`.)
- **Cleanup**: `drive +delete --file-token <docx> --type docx --yes`;
  `base +record-delete --base-token <t> --table-id <t> --record-id <id> --yes`.
- The KB-side `feishu_adapter.py` remains the local JSON fallback and does **not** write Feishu.
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
