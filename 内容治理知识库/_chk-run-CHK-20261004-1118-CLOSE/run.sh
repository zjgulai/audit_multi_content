#!/bin/sh
# kb-check 体检档 · 六道统一闸门 + 逐层闸门（L0–L7）· 只报不改
# RUN = CHK-20261004-1118-CLOSE   本脚本唯一的写盘产物 = 本目录 + kb/l8/workflow_check_<RUN>.json（门④ 按设计）
set -u
ROOT="/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理"
D="$ROOT/_chk-run-CHK-20261004-1118-CLOSE"
RUN="CHK-20261004-1118-CLOSE"
cd "$ROOT" || exit 9

go() { # go <tag> <cmd...>
  tag="$1"; shift
  "$@" > "$D/$tag.out" 2> "$D/$tag.err"
  echo $? > "$D/$tag.exit"
  printf '%-14s exit=%s\n' "$tag" "$(cat "$D/$tag.exit")"
}

echo "== 六道统一闸门 =="
go 01-skills      sh kb/kbpy l7/scripts/skills_check.py
go 02-layers      sh kb/kbpy l7/scripts/layers_check.py
go 03-routes      sh kb/kbpy l7/scripts/routes_reconcile.py
go 04-workflow    sh kb/kbpy l8/workflow_check.py "$RUN"
go 05a-envgate    python3 tools/envelope_gate.py
go 05b-envcensus  sh kb/kbpy l8/envelope_census.py
go 06-projection  sh kb/kbpy l8/projection_reconcile.py

echo "== 逐层闸门 L0–L7（零写档） =="
go pipe-check     sh kb/kbpy l7/scripts/kb_pipeline.py --check

echo "== 逐层单独（l0..l7 各层 gate 直跑） =="
for L in 0 1 2 3 4 5 6 7; do
  go "layer-L$L" sh kb/kbpy "l7/scripts/l${L}_gate.py"
done

echo "== 本批 RT-20261004-LISTING 逐层落章字段 =="
for L in 4 5 6; do
  for f in "$ROOT/kb/l$L/runs/RT-20261004-LISTING-L$L-dryrun.json" "$ROOT/kb/l$L/runs/RT-20261004-LISTING-L$L-selftest-dryrun.json"; do
    [ -f "$f" ] && echo "--- $f" && python3 -c "import json,sys;d=json.load(open(sys.argv[1]));print({k:d.get(k) for k in ('run_id','layer','dry_run','applied','skill','at','ts')})" "$f"
  done
done
echo "ALL-DONE"
