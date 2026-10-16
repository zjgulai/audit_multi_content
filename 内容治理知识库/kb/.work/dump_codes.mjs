#!/usr/bin/env node
/**
 * L8 · 定向导出指定诊断码的完整消息（loader 侧）。
 *
 * 为什么不用 kb_check 工具：它会把全部明细打出来（实测 477 KB），没法读。
 * loader_probe.mjs 只给计数，而改数据前需要知道**消息里的确切数字**（W023/W025
 * 的消息形如「N/M 条…」）。本脚本按码过滤，只打想要的那几条。
 *
 * 用法：
 *   ELECTRON_RUN_AS_NODE=1 "<DSH>" kb/.work/dump_codes.mjs <root> W019,W023,W025 [maxPerCode]
 * 输出：一行 JSON。
 */
import path from "node:path";

const LIB = path.join(process.env.HOME, ".dsh/plugins/dsh-kb/lib/kb.js");
const { check } = await import(`file://${LIB}`);

const [root, codesArg, maxArg] = process.argv.slice(2);
const codes = new Set((codesArg ?? "").split(",").map((s) => s.trim()).filter(Boolean));
const maxPerCode = Number(maxArg ?? 5);
if (!root || !codes.size) {
  console.error("用法：dump_codes.mjs <root> CODE1,CODE2 [maxPerCode]");
  process.exit(2);
}

const res = check(root, { acceptBaseline: false }) ?? {};
const out = { root, wants: [...codes], found: {}, errors_total: (res.errors ?? []).length, warnings_total: (res.warnings ?? []).length };

for (const bucket of ["errors", "warnings"]) {
  for (const item of res[bucket] ?? []) {
    if (!codes.has(item.code)) continue;
    const slot = (out.found[item.code] ??= { bucket, count: 0, samples: [] });
    slot.count += 1;
    if (slot.samples.length < maxPerCode) slot.samples.push({ file: item.file, msg: item.msg, ...(item.keys ? { keys: item.keys } : {}) });
  }
}
console.log(JSON.stringify(out, null, 1));
