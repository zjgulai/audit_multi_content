#!/bin/bash
# R13 信封态修复：内容保真重写（python 读真身 → stdin → 消费方运行时写回）
set -u
cd "/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理"
DSH="/Applications/DSH Desktop.app.pre-lute-20260907-111753/Contents/MacOS/DSH Desktop"
BK=$(cat _repair-run-R13-BACKUP.txt)
OUT="_repair-run-REPAIR-$(date +%Y%m%d-%H%M%S)-ENV"
mkdir -p "$OUT"; echo "$OUT" > _repair-run-R13-ENV.outdir

rc=0
while IFS= read -r f; do
  [ -z "$f" ] && continue
  base=$(basename "$f")
  # ① 读真身（python 侧 = 明文）
  python3 -c "import sys,hashlib;b=open(sys.argv[1],'rb').read();sys.stdout.buffer.write(b);open(sys.argv[2],'wb').write(hashlib.sha256(b).hexdigest().encode())" "$f" "$OUT/$base.before.sha" > "$OUT/$base.before.bin"
  before_py_sha=$(cat "$OUT/$base.before.sha")
  # ② 回滚基线（/bin/cp 是明文通道）
  /bin/cp "$f" "$BK/$base.before"
  # ③ 内容保真重写：stdin → 消费方运行时 writeFileSync（自带读回逐字节断言）
  python3 -c "import sys;sys.stdout.buffer.write(open(sys.argv[1],'rb').read())" "$f" \
    | ELECTRON_RUN_AS_NODE=1 "$DSH" kb/.work/write_via_node.mjs "$f" > "$OUT/$base.helper.json" 2>&1
  hrc=$?
  # ④ 复核：python 侧内容未变 ｜ 消费方侧现在能读全
  python3 -c "
import sys,hashlib,os
p=sys.argv[1]
b=open(p,'rb').read()
print(hashlib.sha256(b).hexdigest(), len(b), os.path.getsize(p))
" "$f" > "$OUT/$base.after.py"
  el=$(ELECTRON_RUN_AS_NODE=1 "$DSH" -e 'const fs=require("fs");const b=fs.readFileSync(process.argv[1]);console.log(JSON.stringify({size:fs.statSync(process.argv[1]).size,len:b.length}))' "$f")
  after_py_sha=$(cut -d' ' -f1 "$OUT/$base.after.py")
  echo "$el" > "$OUT/$base.after.electron"
  printf '%-34s helper=%s  content_same=%s  electron=%s\n' "$base" "$hrc" "$([ "$before_py_sha" = "$after_py_sha" ] && echo YES || echo NO)" "$el"
  [ "$hrc" = "0" ] || rc=1
  [ "$before_py_sha" = "$after_py_sha" ] || rc=1
done < /tmp/r13-targets.list
echo "修复脚本退出码=$rc"
exit $rc
