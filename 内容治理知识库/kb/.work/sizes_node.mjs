import fs from "node:fs"; import path from "node:path";
const root = process.argv[2]; const out = {};
function walk(d){ let es; try{es=fs.readdirSync(d,{withFileTypes:true});}catch{return;}
  for(const e of es){ const p=path.join(d,e.name);
    if(e.isDirectory()){ if(e.name==='node_modules'||e.name==='.git')continue; walk(p); }
    else if(e.name.endsWith('.md')){ try{ out[path.relative(root,p)] = fs.statSync(p).size; }catch{} } } }
walk(root);
fs.writeFileSync(process.argv[3], JSON.stringify(out));
