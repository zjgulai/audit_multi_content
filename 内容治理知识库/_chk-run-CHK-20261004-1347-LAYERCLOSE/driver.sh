#!/bin/sh
# CHK-20261004-1347-LAYERCLOSE —— kb-check 体检档
#   六道统一闸门（①登记表 ②层契约 ③路由对账 ④链路收口 ⑤信封 ⑥投影）
#   + 八层闸门 L0–L7 + kb_pipeline.py --check（零写自证）
#   + 逐层收口证据（逐份读 runs/*.json 字段，不按文件名猜）
# 纪律：只报不改。未 --apply、未 --sync、未 --write-gate、未改任何数据/注册表/判据。
# 声明：门④ workflow_check.py 无干跑档，本次将写 kb/l8/workflow_check_$RUN.json（唯一进入 kb/ 的写）
set -u
RUN=CHK-20261004-1347-LAYERCLOSE
ROOT="/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理"
cd "$ROOT" || exit 1
D="$ROOT/_chk-run-$RUN"
mkdir -p "$D"

{
  echo "RUN=$RUN"
  echo "cwd=$ROOT"
  date '+%F %T'
  echo "declare: 门④ workflow_check.py 无干跑档 -> 将写 kb/l8/workflow_check_$RUN.json"
  echo "declare: 其余命令默认只读；未加 --apply/--sync/--write-gate"
} > "$D/00-declare.txt"

echo "=== claim before ===" > "$D/00-claim-before.txt"
sh kb/kbpy l7/scripts/kb_loop_claim.py status >> "$D/00-claim-before.txt" 2>&1
echo "exit=$?" >> "$D/00-claim-before.txt"

# ---- 阶段A：数据指纹（前后比对，做零写自证） ----
: > "$D/00-pre.sha"
for f in kb/l0/manifest.jsonl kb/l1/units.jsonl kb/l2/units.jsonl \
         kb/l3/candidates/rules.jsonl kb/l3/rejected.jsonl \
         kb/l4/registry/l4.json kb/l5/p0_patterns.jsonl kb/l6/registry/l6.json; do
  if [ -f "$f" ]; then
    printf '%s %s\n' "$(shasum -a 256 "$f" | cut -c1-16)" "$f" >> "$D/00-pre.sha"
  else
    printf '%s %s\n' "MISSING" "$f" >> "$D/00-pre.sha"
  fi
done
wc -l < kb/l7/runs/index.jsonl > "$D/00-pre-index-lines.txt"

run1() { # run1 <label> <outfile> <cmd...>
  lbl=$1; out=$2; shift 2
  { echo "\$ $*"; } > "$out"
  "$@" >> "$out" 2>&1
  echo "$?" > "$out.exit"
  echo "[$lbl] exit=$(cat "$out.exit")"
}

# ---- 六道统一闸门 ----
run1 01 "$D/01.out" sh kb/kbpy l7/scripts/skills_check.py
run1 02 "$D/02.out" sh kb/kbpy l7/scripts/layers_check.py
run1 03 "$D/03.out" sh kb/kbpy l7/scripts/routes_reconcile.py "kb/l7/reports/$RUN-routes-winners.json"
run1 04 "$D/04.out" sh kb/kbpy l8/workflow_check.py "$RUN"
run1 05a "$D/05a.out" python3 tools/envelope_gate.py
run1 05b "$D/05b.out" sh kb/kbpy l8/envelope_census.py
run1 06 "$D/06.out" sh kb/kbpy l8/projection_reconcile.py

# ---- 八层闸门 ----
for L in l0 l1 l2 l3 l4 l5 l6 l7; do
  run1 "$L" "$D/g-$L.out" sh kb/kbpy "l7/scripts/${L}_gate.py"
done

# ---- 八层闸门全景（含零写自证） ----
run1 pc "$D/pc.out" sh kb/kbpy l7/scripts/kb_pipeline.py --check

# ---- 阶段C：后指纹 ----
: > "$D/99-post.sha"
for f in kb/l0/manifest.jsonl kb/l1/units.jsonl kb/l2/units.jsonl \
         kb/l3/candidates/rules.jsonl kb/l3/rejected.jsonl \
         kb/l4/registry/l4.json kb/l5/p0_patterns.jsonl kb/l6/registry/l6.json; do
  if [ -f "$f" ]; then
    printf '%s %s\n' "$(shasum -a 256 "$f" | cut -c1-16)" "$f" >> "$D/99-post.sha"
  else
    printf '%s %s\n' "MISSING" "$f" >> "$D/99-post.sha"
  fi
done
wc -l < kb/l7/runs/index.jsonl > "$D/99-post-index-lines.txt"
diff "$D/00-pre.sha" "$D/99-post.sha" > "$D/99-sha-diff.txt" 2>&1
echo "sha_diff_exit=$?" >> "$D/99-sha-diff.txt"

# ---- 逐层收口证据（只读探针，逐份读字段） ----
/usr/bin/python3 "$D/layer_stamps.py" > "$D/07-layer-stamps.txt" 2>&1
echo "exit=$?" >> "$D/07-layer-stamps.txt"

echo "=== claim after ===" > "$D/99-claim-after.txt"
sh kb/kbpy l7/scripts/kb_loop_claim.py status >> "$D/99-claim-after.txt" 2>&1
date '+%F %T' > "$D/99-done.txt"
echo "ALLDONE"
