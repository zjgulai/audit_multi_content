#!/bin/sh
# kb-pipeline §4 收口四件套（补齐「一遍闸门」）—— 附 pre/post 归因，逐条写清谁写的
set -u
cd "/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理" || exit 2

RUN=GATE-20261004-1142
OUT="_gate-run-$RUN"
mkdir -p "$OUT"

snap(){
  for f in kb/l0/manifest.jsonl kb/l2/units.jsonl kb/l3/candidates/rules.jsonl kb/l3/rejected.jsonl \
           kb/l4/registry/l4.json kb/l5/p0_patterns.jsonl kb/l6/registry/l6.json kb/l7/runs/index.jsonl; do
    [ -f "$f" ] && printf '%s %s %s\n' "$(stat -f %z "$f")" "$(shasum -a 256 "$f" | cut -c1-16)" "$f"
  done
  echo "RUNFILES $(find kb/l7/runs -maxdepth 1 -name '*.json' | wc -l | tr -d ' ')"
}

date
snap > "$OUT/pre4.sha"
echo "=== 本次收口前的账本行数 ==="; wc -l < kb/l7/runs/index.jsonl

rm -f "$OUT/10-exits.txt"
r(){ nm="$1"; shift; t0=$(date +%s); "$@" >"$OUT/$nm.txt" 2>&1; ec=$?; t1=$(date +%s); \
     echo "$nm exit=$ec secs=$((t1-t0))" | tee -a "$OUT/10-exits.txt"; }

echo "=== ① workflow_check（L7 收口核验）==="
r 10-workflow_check sh kb/kbpy l8/workflow_check.py "$RUN"
echo "=== ② skills_check（登记表五类）==="
r 11-skills_check sh kb/kbpy l7/scripts/skills_check.py
echo "=== ③ envelope_census（信封普查，只扫 .md）==="
r 12-envelope_census sh kb/kbpy l8/envelope_census.py
echo "=== ④ skill_conformance（C7 层↔skill 双向对账）==="
r 13-skill_conformance sh kb/kbpy l7/scripts/skill_conformance.py

echo "=== 收口后归因 ==="
snap > "$OUT/post4.sha"
diff "$OUT/pre4.sha" "$OUT/post4.sha" > "$OUT/sha4-diff.txt" 2>&1 && \
  echo "归因：✅ 8 项库文件 + run 文件数 全未变" | tee -a "$OUT/10-exits.txt" || \
  { echo "归因：⚠️ 有变化（逐行如下）" | tee -a "$OUT/10-exits.txt"; cat "$OUT/sha4-diff.txt"; }
echo "=== 本窗口内 kb/l7 下被改/新建的文件 ==="
find kb/l7 -newermt '2026-10-04 11:47:00' -type f ! -path '*/reports/*' | head -20
date
echo "=== done ==="
cat "$OUT/10-exits.txt"
