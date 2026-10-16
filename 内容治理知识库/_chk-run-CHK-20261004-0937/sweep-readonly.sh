set -u
cd "/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理"
D=_chk-run-CHK-20261004-0937
run() { name="$1"; shift; echo "$*" > "$D/$name.cmd"; "$@" > "$D/$name.out" 2>&1; echo $? > "$D/$name.exit"; }
echo "RUN=CHK-20261004-0937  started $(date '+%F %T')" > "$D/RUN.txt"
run 01-skills       sh kb/kbpy l7/scripts/skills_check.py
run 02-layers       sh kb/kbpy l7/scripts/layers_check.py
run 03-routes       sh kb/kbpy l7/scripts/routes_reconcile.py
run 04-workflow     sh kb/kbpy l8/workflow_check.py CHK-20261004-0937
run 05a-envelope    python3 tools/envelope_gate.py
run 05a2-envelope-out python3 tools/envelope_gate.py _eval-L0L7-gap-20261003
run 05b-census      sh kb/kbpy l8/envelope_census.py
run 06-projection   sh kb/kbpy l8/projection_reconcile.py
echo "done $(date '+%F %T')" >> "$D/RUN.txt"
for f in "$D"/*.exit; do n=$(basename "$f" .exit); printf '%-20s exit=%s\n' "$n" "$(cat "$f")"; done
