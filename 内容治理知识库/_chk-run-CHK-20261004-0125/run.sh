#!/bin/bash
# kb-check 体检档 六道闸门 · 只读（④ 按设计写 kb/l8/workflow_check_<RUN>.json）
cd "/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理" || exit 1
RUN=CHK-20261004-0125
D="_chk-run-$RUN"
run() {
  local tag="$1"; shift
  echo "===== $tag :: $* ====="
  "$@" > "$D/$tag.out" 2>&1
  local rc=$?
  echo "$rc" > "$D/$tag.exit"
  echo "[exit=$rc]"
  tail -6 "$D/$tag.out"
  echo
}
echo "### 0 新鲜度前置（只读，不拒答） $(date '+%F %T')"
sh kb/kbpy l7/scripts/freshness.py > "$D/0-freshness.out" 2>&1; echo "$?" > "$D/0-freshness.exit"
echo "[exit=$(cat $D/0-freshness.exit)]"; tail -4 "$D/0-freshness.out"; echo

run 1-skills_check      sh kb/kbpy l7/scripts/skills_check.py
run 2-layers_check      sh kb/kbpy l7/scripts/layers_check.py
run 3a-routes-missing   sh kb/kbpy l7/scripts/routes_reconcile.py "kb/l7/reports/$RUN-routes-winners.json"
run 3b-routes-oldref    sh kb/kbpy l7/scripts/routes_reconcile.py --alias _eval-kb-manage/blind_v2.winners.txt
run 4-workflow_check    sh kb/kbpy l8/workflow_check.py "$RUN"
run 5a-envelope_gate    python3 tools/envelope_gate.py
run 5b-envelope_census  sh kb/kbpy l8/envelope_census.py
run 6-projection        sh kb/kbpy l8/projection_reconcile.py
echo "### 完成 $(date '+%F %T')"
