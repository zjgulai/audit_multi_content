#!/usr/bin/env node
/**
 * 修复计划 F6 · 把 56 条 `form=entry` 从 L2-concepts 迁到 L1-facts，并改 tier/kind。
 *
 * 为什么必须用 node 写：本机 trld 注入层按**发起写入调用的进程**决定落盘形态。
 * 受控实验（2026-09-29，同一段 34 字节内容、五个写入者）：
 *
 *   cat src > f.md              → 明文 ✅
 *   cp src f.md                 → 明文 ✅
 *   <DSH> node fs.writeFileSync → 明文 ✅
 *   sed 's/…/' src > f.md       → 信封 ❌（4130 字节，首字节 88 7d 1c）
 *   python3 open(...,"w")       → 信封 ❌
 *   perl -e 'print'             → 信封 ❌
 *
 * ⚠ 这条**修正了 kb/l8 记录的措辞**「bash 内建重定向写的 .md 是明文」——
 *   真正决定形态的是写入者，不是有没有重定向：`sed >` 也是重定向，但它落信封。
 *   往装载位写 .md 一律走 node / `cat` / `cp`，**不要用 sed / awk / python / perl**。
 *
 * 迁移内容（每条恰好 2 行）：
 *   tier: L2        → tier: L1
 *   kind: judgment  → kind: fact
 * 目录：L2-concepts/ → L1-facts/
 *
 * 用法：ELECTRON_RUN_AS_NODE=1 "<DSH>" kb/.work/fix_f6_migrate.mjs [--dry-run]
 *       （加 --from-backup 从归档的迁移前副本重做，用于修掉一次信封事故）
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

// ⚠ 不能用 `new URL(import.meta.url).pathname` —— 本工作区路径含中文，
// 它返回的是**百分号编码**串（%E6%89%A7%E8%A1%8C…），fs 找不到目录。
const KB = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const VIEW = path.join(KB, "view", "3_措辞表达库");
const DST = path.join(VIEW, "L1-facts");
const ARCHIVE = path.join(
  KB, "l8", "_archive", "fix-20260929-094703", "L2-concepts-before-F6",
);

const dryRun = process.argv.includes("--dry-run");
const fromBackup = process.argv.includes("--from-backup");
const SRC = fromBackup ? ARCHIVE : path.join(VIEW, "L2-concepts");

if (!fs.existsSync(SRC)) {
  console.error(`源目录不存在：${SRC}`);
  process.exit(1);
}
if (!fs.existsSync(DST)) {
  console.error(`目标目录不存在：${DST}`);
  process.exit(1);
}

const files = fs.readdirSync(SRC).filter((f) => f.endsWith(".md")).sort();
console.log(`源：${SRC}`);
console.log(`目标：${DST}`);
console.log(`待处理：${files.length} 条${dryRun ? "（dry-run）" : ""}\n`);

let written = 0;
let skipped = 0;
let bad = 0;

for (const f of files) {
  const srcPath = path.join(SRC, f);
  const dstPath = path.join(DST, f);
  const text = fs.readFileSync(srcPath, "utf8");

  // 只改这两行，其余逐字节保留
  const before = text;
  const after = before
    .replace(/^tier: L2$/m, "tier: L1")
    .replace(/^kind: judgment$/m, "kind: fact");

  // 先断言「改前确实是要改的样子、改后确实改到了」
  const problems = [];
  if (!/^tier: L2$/m.test(before)) problems.push("改前不是 tier: L2");
  if (!/^kind: judgment$/m.test(before)) problems.push("改前不是 kind: judgment");
  if (!/^tier: L1$/m.test(after)) problems.push("改后不是 tier: L1");
  if (!/^kind: fact$/m.test(after)) problems.push("改后不是 kind: fact");
  // data_level / sensitivity_level 的 L2 **不许被碰到**
  if (/^data_level: L2$/m.test(before) !== /^data_level: L2$/m.test(after)) {
    problems.push("误改了 data_level");
  }
  if (/^sensitivity_level: L2$/m.test(before) !== /^sensitivity_level: L2$/m.test(after)) {
    problems.push("误改了 sensitivity_level");
  }
  // 行数必须一致
  if (before.split("\n").length !== after.split("\n").length) {
    problems.push("行数变了");
  }
  if (problems.length) {
    console.error(`  ❌ ${f}：${problems.join(" / ")}`);
    bad += 1;
    continue;
  }

  if (srcPath === dstPath) {
    skipped += 1;
    continue;
  }

  if (!dryRun) {
    // node 写 = 明文通道
    fs.writeFileSync(dstPath, after);
    // 读回断言：必须明文、且与预期逐字节一致
    const rb = fs.readFileSync(dstPath);
    const head = rb.slice(0, 3).toString("utf8");
    if (head !== "---") {
      console.error(`  ❌ ${f}：读回不是明文（首 3 字节 ${JSON.stringify(head)}）`);
      bad += 1;
      continue;
    }
    if (Buffer.from(after, "utf8").compare(rb) !== 0) {
      console.error(`  ❌ ${f}：读回内容与预期不一致`);
      bad += 1;
      continue;
    }
    // ⚠ 归档副本**永不删除** —— 它是唯一能重做一次的原始件
  }
  written += 1;
}

console.log(`\n写入 ${written} 条，跳过 ${skipped} 条，异常 ${bad} 条`);

// 汇总校验
if (!dryRun && !fromBackup) {
  const now = fs.readdirSync(DST).filter((f) => f.endsWith(".md"));
  let plain = 0;
  let env = 0;
  for (const f of now) {
    const b = fs.readFileSync(path.join(DST, f));
    if (b.slice(0, 3).toString("utf8") === "---") plain += 1;
    else {
      env += 1;
      console.error(`  ❌ 信封残留：${f}（${b.length} 字节）`);
    }
  }
  console.log(`L1-facts：${now.length} 条 —— 明文 ${plain} / 信封 ${env}`);
  const left = fs.existsSync(path.join(VIEW, "L2-concepts"))
    ? fs.readdirSync(path.join(VIEW, "L2-concepts")).filter((f) => f.endsWith(".md")).length
    : 0;
  console.log(`L2-concepts 残留：${left} 条`);
}
process.exit(bad > 0 ? 1 : 0);
