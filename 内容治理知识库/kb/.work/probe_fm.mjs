import fs from "node:fs";
import path from "node:path";
const LIB = path.join(process.env.HOME, ".dsh/plugins/dsh-kb/lib/kb.js");
const { splitFrontmatter } = await import(`file://${LIB}`);
for (const p of process.argv.slice(2)) {
  const raw = fs.readFileSync(p, "utf8");
  const { meta, body } = splitFrontmatter(raw);
  const first = JSON.stringify(raw.slice(0, 24));
  console.log(JSON.stringify({
    file: path.basename(p), node_sees_first_bytes: first, node_len: raw.length,
    meta_null: meta === null, parse_error: meta?.__parseError ?? null,
    meta_keys: meta && !meta.__parseError ? Object.keys(meta).length : null,
    record_ids: meta?.source?.record_ids ?? null,
    record_ids_type: meta?.source?.record_ids === undefined ? "缺失" : Array.isArray(meta.source.record_ids) ? "数组" : typeof meta.source.record_ids,
    evidence_group: meta?.evidence_group ?? null,
    body_len: body.length,
  }));
}
