#!/usr/bin/env node
/**
 * L8 · 建立/刷新加载器条目基线（`_meta/manifest.json`）。
 *
 * 为什么需要：加载器的 `readManifest(root)` 读 `_meta/manifest.json`，且**要求顶层有
 * `entries` 对象**；读到别的 schema 就返回 `null` → 报 W035「没有条目基线」→
 * 「条目被删掉」与「治理字段被原地改写」两类事故**都发现不了**。
 * 这不是理论风险：2026-09-22 有 6 条 L0-raw 原文存档被整体删除，当时靠 entry_count
 * 和词表死引用**碰巧**才看出来，检查器本身什么都没说。
 *
 * 本库此前一直报 W035 的根因是**文件名冲突**：生成器 `kb/.work/gen-host-library.py`
 * 把 workbench 镜像负载也写到 `_meta/manifest.json`，两个不同 schema 抢一个文件名。
 * 已把镜像负载改名为 `_meta/workbench-mirror.json`（见 W035 的处置），
 * 本脚本负责在腾出来的路径上建立真正的基线。
 *
 * 只读性说明：加载器的 check() 是只读的、不会自建基线（插件测试 test-wiring.mjs:373
 * 明确断言这一点）。所以建基线必须显式调 writeManifest —— 本脚本就是那个显式动作。
 *
 * 用法：
 *   ELECTRON_RUN_AS_NODE=1 "<DSH>" kb/l8/manifest_baseline.mjs <root> [--dry]
 * 输出：一行 JSON。
 */
import path from "node:path";
import fs from "node:fs";

const LIB = path.join(process.env.HOME, ".dsh/plugins/dsh-kb/lib/kb.js");
const { readManifest, writeManifest, MANIFEST_FILE } = await import(`file://${LIB}`);

const [root, ...flags] = process.argv.slice(2);
const dry = flags.includes("--dry");
if (!root) {
  console.error("用法：manifest_baseline.mjs <root> [--dry]");
  process.exit(2);
}

const file = path.join(root, "_meta", MANIFEST_FILE);
const out = { root, manifest_file: `_meta/${MANIFEST_FILE}`, dry };

// 建基线前必须先看清目标路径上现在是什么 —— 防止又一次「覆盖掉别的东西」。
if (fs.existsSync(file)) {
  let doc = null;
  try { doc = JSON.parse(fs.readFileSync(file, "utf8")); } catch { doc = null; }
  const keys = doc && typeof doc === "object" ? Object.keys(doc) : null;
  out.existing = {
    bytes: fs.statSync(file).size,
    parseable: Boolean(doc),
    top_level_keys: keys,
    has_entries: Boolean(doc && typeof doc.entries === "object"),
  };
  if (doc && typeof doc === "object" && !doc.entries) {
    out.REFUSED = "目标路径上已有文件，但顶层没有 entries —— 这看起来是别的 schema（如 workbench 镜像负载）。"
      + "拒绝覆盖：请先把它改名，再建基线。";
    console.log(JSON.stringify(out));
    process.exit(3);
  }
} else {
  out.existing = null;
}

const before = readManifest(root);
out.before_has_baseline = Boolean(before && !before.__parseError);
out.before_entry_count = before?.entries ? Object.keys(before.entries).length : 0;

if (dry) {
  out.action = "dry-run：未写盘";
  console.log(JSON.stringify(out));
  process.exit(0);
}

const res = writeManifest(root, { full: true, previous: before });
out.write_result = res;

const after = readManifest(root);
out.after_has_baseline = Boolean(after && !after.__parseError);
out.after_entry_count = after?.entries ? Object.keys(after.entries).length : 0;
out.after_bytes = fs.existsSync(file) ? fs.statSync(file).size : 0;

console.log(JSON.stringify(out));
process.exit(out.after_has_baseline ? 0 : 1);
