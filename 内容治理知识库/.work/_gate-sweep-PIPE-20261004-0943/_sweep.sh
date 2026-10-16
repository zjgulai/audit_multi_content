set -u
cd "/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理" || exit 9
RUN=PIPE-20261004-0943
D=.work/_gate-sweep-$RUN
PRODS="kb/l0/manifest.jsonl kb/l1/manifest_l1.jsonl kb/l1/index/l1.jsonl kb/l2/units.jsonl kb/l3/candidates/rules.jsonl kb/l3/rejected.jsonl kb/l4/canonical/wording_entry.jsonl kb/l5/p0_patterns.jsonl kb/l6/index/l6.jsonl kb/l6/selftest.json"
shasum -a 256 $PRODS > "$D/before-sha.txt" 2>&1
: > "$D/gate-exit.txt"
for L in 0 1 2 3 4 5 6 7; do
  S=kb/l7/scripts/l${L}_gate.py
  { sh kb/kbpy "$S"; } > "$D/gate-L${L}.txt" 2>&1
  rc=$?
  echo "L${L} exit=${rc}" >> "$D/gate-exit.txt"
  echo "[L${L}] exit=${rc}"
done
sh kb/kbpy l7/scripts/kb_pipeline.py --check > "$D/pipeline-check.txt" 2>&1
echo "pipeline-check exit=$?" >> "$D/gate-exit.txt"
shasum -a 256 $PRODS > "$D/after-sha.txt" 2>&1
echo "=== ZERO-WRITE DIFF ==="
diff "$D/before-sha.txt" "$D/after-sha.txt" && echo "IDENTICAL（关键 data 产物 sha256 全未变）"
echo "=== EXIT TABLE ==="
cat "$D/gate-exit.txt"
echo "=== l7/runs 有无本 RUN ==="
grep -c "$RUN" kb/l7/runs/index.jsonl || echo "index:0"
ls kb/l7/runs/ | grep "$RUN" || echo "runs/: 无本 RUN 文件"
