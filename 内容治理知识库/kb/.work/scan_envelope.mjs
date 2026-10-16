import fs from "node:fs";
import path from "node:path";
const root = process.argv[2];
let total = 0, env = 0, ok = 0; const samples = [];
function walk(d) {
  for (const n of fs.readdirSync(d).sort()) {
    const p = path.join(d, n); const st = fs.statSync(p);
    if (st.isDirectory()) walk(p);
    else if (n.endsWith(".md")) {
      total++;
      const b = fs.readFileSync(p);
      if (b.slice(0, 3).toString("latin1") === "---") ok++;
      else { env++; if (samples.length < 5) samples.push({ p: path.relative(root, p), bytes: b.length, head: JSON.stringify(b.slice(0,8).toString("latin1")) }); }
    }
  }
}
walk(path.join(root, "3_措辞表达库"));
console.log(JSON.stringify({ total, plaintext: ok, enveloped: env, samples }, null, 1));
