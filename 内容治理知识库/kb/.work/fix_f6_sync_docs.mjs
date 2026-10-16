#!/usr/bin/env node
/**
 * 修复计划 F6 · 同步三份**文档性引用**（`.md`，必须走 node 写通道）。
 *
 * 迁移把 56 条从 L2-concepts 挪到了 L1-facts，但三份 md 里仍写着旧构成：
 *   · `_meta/DERIVED.md`      层目录映射表写着 `form=entry → L2-concepts`
 *   · `_meta/GUIDE.md`        条目构成写着「L1-facts 453 + L2-concepts 56」
 *   · `_meta/entry-schema.md` 仍把 E021×56 写成「待办」，实际已处置
 *
 * ⚠ 写通道：`.md` 只能用 node / `cat` / `cp`。受控实验证明 `sed` / `python` / `perl`
 *   写的 `.md` 会落成 4096 字节前缀信封，Electron 侧（加载器、工作台镜像器）读成密文 → E001。
 *
 * 用法：ELECTRON_RUN_AS_NODE=1 "<DSH>" kb/.work/fix_f6_sync_docs.mjs [--dry-run]
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const KB = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const META = path.join(KB, "view", "_meta");
const dryRun = process.argv.includes("--dry-run");

/** 每项：文件、原文、新文。原文必须**恰好出现一次**，否则中止（防误替换）。 */
const EDITS = [
  {
    file: "DERIVED.md",
    from: "| 层目录 | `form=entry → L2-concepts`，`form=revision_pair → L1-facts` |",
    to:
      "| 层目录 | `form=entry → L1-facts`、`form=revision_pair → L1-facts`、" +
      "`form=boundary → L1-facts`（**F5 修订**：`entry` 原落 `L2-concepts`，因 `E021 × 56` 降层，见下） |",
  },
  {
    file: "GUIDE.md",
    from: "| 条目 | 509 条（`L1-facts` 453 + `L2-concepts` 56） |",
    to:
      "| 条目 | 509 条（**全部落在 `L1-facts`**；`L2-concepts` 现为空 —— " +
      "F5 把这 56 条 `form=entry` 从 `L2-concepts`/`judgment` 降为 `L1-facts`/`fact`，理由见 `_meta/entry-schema.md` §五） |",
  },
  {
    file: "entry-schema.md",
    from:
      "> ⚠ **本视图当前 56 条 `L2-concepts` 全部缺 `verification`**（E021 × 56）。\n" +
      "> 原因是派生视图生成器拒绝为判断类条目代打三重验证分 —— 那等于把闸门变成自我申报。\n" +
      "> 处置见修复计划：这 56 条应**降级为 `L1-facts` + `kind: fact`**（E023 只禁止 `fact` 进 L2/L4），\n" +
      "> 待人工过闸后再升回 L2。",
    to:
      "> ✅ **已处置（修复计划 F5 / F6，2026-09-29）**：原先 56 条 `form=entry` 落在 `L2-concepts`、\n" +
      "> `kind: judgment`，而 judgment 强制要求 `verification`（5 个子键）→ 报 `E021 × 56`。\n" +
      "> **没有**给它们补 `verification` —— 三重验证是**人工判断闸门**，派生视图替人打分\n" +
      "> 等于把闸门变成自我申报（`kb/l3/registry/l3.json` 排除这 56 条判断类概念用的是同一条理由）。\n" +
      "> 实际处置是**降层**：`tier: L2 → L1`、目录 `L2-concepts/ → L1-facts/`、`kind: judgment → fact`。\n" +
      "> E023 只禁止 `fact` 进 L2/L4，**L1-facts 收 fact 合法**，于是 E021 与 E023 同时不再适用。\n" +
      "> 实测：`E021 56 → 0`，`errors 508 → 452`（其余 452 条为 E026，见修复报告 F2 §三）。\n" +
      ">\n" +
      "> **回填路径**：等人工过完三重验证后，逐条补真的 `verification` 并升回 `L2-concepts` + `judgment`。\n" +
      "> `L2-concepts/` 目录保留为空，就是给这一步留的位置。",
  },
];

let failed = 0;
for (const e of EDITS) {
  const p = path.join(META, e.file);
  if (!fs.existsSync(p)) {
    console.error(`❌ 文件不存在：${e.file}`);
    failed += 1;
    continue;
  }
  const text = fs.readFileSync(p, "utf8");
  const occurrences = text.split(e.from).length - 1;
  if (occurrences !== 1) {
    console.error(`❌ ${e.file}：原文出现 ${occurrences} 次（要求恰好 1 次），中止该处替换`);
    failed += 1;
    continue;
  }
  const after = text.replace(e.from, e.to);
  if (dryRun) {
    console.log(`[dry-run] ${e.file}  ${text.length} → ${after.length} 字节`);
    continue;
  }
  fs.writeFileSync(p, after);          // node 写 = 明文通道
  const rb = fs.readFileSync(p);
  // 读回逐字节一致**本身就是明文判据**：信封会在前面加 4096 字节、并换掉首字节，
  // 所以只要内容相等就不可能落成信封。（这几份 md 不以 `---` 开头，别再拿它当判据。）
  if (rb.toString("utf8") !== after) {
    console.error(`❌ ${e.file}：读回内容不一致（可能落了信封）`);
    failed += 1;
    continue;
  }
  console.log(`✅ ${e.file}  ${text.length} → ${after.length} 字节（读回一致、明文）`);
}
process.exit(failed > 0 ? 1 : 0);
