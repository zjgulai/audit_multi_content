import fs from "node:fs";
import path from "node:path";
const out = [];
for (const p of process.argv.slice(2)) {
  let b;
  try { b = fs.readFileSync(p); } catch (e) { out.push({ p, err: String(e.message) }); continue; }
  out.push({ p: path.basename(path.dirname(p)) + "/" + path.basename(p), bytes: b.length, head: JSON.stringify(b.slice(0, 12).toString("latin1")) });
}
console.log(JSON.stringify(out, null, 1));
