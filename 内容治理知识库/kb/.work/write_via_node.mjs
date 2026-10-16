#!/usr/bin/env node
/**
 * 用**消费方运行时**（node/Electron）写文件，写完立刻读回断言。
 *
 * 为什么要单独有个工具（2026-09-29 实测，代价是一轮 509 条 E001）：
 * 这台机器上装了注入型监控/加密代理，**同一份 4,532 字节的 md**：
 *   · shell `cp` 落盘 → node 读到 4,532 字节、首 3 字节 `---`        ✅
 *   · python `shutil.copy2` 落盘 → node 读到 **8,628 字节**、首字节随机 ❌
 *     8,628 = 4,532 + **4,096** —— 即「4096 字节前缀 + 原文」的信封。
 * 而 **Python 的 stat / sha256 / head 对信封完全免疫**：它照样报 4,532 字节、
 * sha256 与源文件一致。所以「用 Python 读首 3 字节来自检」**结构上不可能发现它**，
 * 只会给假绿灯，然后由加载器报 E001 × 509、并把条目基线刷成 0 条。
 *
 * 内容走 **stdin**（管道不是文件，绕开一切按后缀生效的写封装），
 * 目标文件由 node 的 `fs.writeFileSync` 写，写回读逐字节比对。
 *
 * 用法：
 *   printf '%s' "$TEXT" | ELECTRON_RUN_AS_NODE=1 "<DSH>" kb/.work/write_via_node.mjs <目标文件>
 *   some-cmd | ELECTRON_RUN_AS_NODE=1 "<DSH>" kb/.work/write_via_node.mjs <目标文件> --dry
 *
 * 退出码：0 成功且读回一致；1 读回不一致；2 用法错。
 */
import fs from "node:fs";
import path from "node:path";

const argv = process.argv.slice(2);
const dry = argv.includes("--dry");
const target = argv.find((a) => !a.startsWith("--"));
if (!target) {
  console.error("用法：write_via_node.mjs <目标文件> [--dry]（内容从 stdin 读）");
  process.exit(2);
}
const dest = path.resolve(target);

const chunks = [];
for await (const c of process.stdin) chunks.push(c);
const buf = Buffer.concat(chunks);

const out = { dest, dry, bytes_in: buf.length };
if (fs.existsSync(dest)) {
  out.existed = true;
  out.bytes_before = fs.statSync(dest).size;
}
if (dry) {
  out.action = "dry-run：未写盘";
  console.log(JSON.stringify(out));
  process.exit(0);
}

fs.mkdirSync(path.dirname(dest), { recursive: true });
fs.writeFileSync(dest, buf);

// 读回断言 —— 必须由**本运行时**读，这一步是全部意义所在
const back = fs.readFileSync(dest);
out.bytes_after = back.length;
out.identical = back.equals(buf);
out.head = JSON.stringify(back.slice(0, 12).toString("latin1"));
out.sha256 = (await import("node:crypto")).createHash("sha256").update(back).digest("hex").slice(0, 16);
console.log(JSON.stringify(out));
process.exit(out.identical ? 0 : 1);
