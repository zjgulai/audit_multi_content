cd "/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理"
RUN="CHK-20261004-1118-AG"
D="_chk-run-$RUN"
: > "$D/exitcodes.txt"
run() { # $1=门号 $2=logfile ; 命令从 stdin 读
  local n="$1" f="$D/$2"
  echo "########## $n ##########" > "$f"
  bash -c "$(cat)" >> "$f" 2>&1
  local rc=$?
  echo "$n exit=$rc" | tee -a "$D/exitcodes.txt"
  echo "   -> $f"
}
run "①skills_check" "①-skills_check.out" <<'E'
sh kb/kbpy l7/scripts/skills_check.py
echo "__EXIT=$?"
E
run "②layers_check" "②-layers_check.out" <<'E'
sh kb/kbpy l7/scripts/layers_check.py
echo "__EXIT=$?"
E
run "③routes-nospec" "③a-routes-nospec.out" <<'E'
sh kb/kbpy l7/scripts/routes_reconcile.py "kb/l7/reports/$RUN-routes-winners.json"
echo "__EXIT=$?"
E
run "④workflow_check" "④-workflow_check.out" <<'E'
python3 -u kb/l8/workflow_check.py "$RUN"
echo "__EXIT=$?"
E
run "⑤a-envelope_gate" "⑤a-envelope_gate.out" <<'E'
python3 tools/envelope_gate.py
echo "__EXIT=$?"
E
run "⑤b-envelope_census" "⑤b-envelope_census.out" <<'E'
sh kb/kbpy l8/envelope_census.py
echo "__EXIT=$?"
E
run "⑥projection" "⑥-projection.out" <<'E'
sh kb/kbpy l8/projection_reconcile.py
echo "__EXIT=$?"
E
echo "=== ALL DONE ==="
cat "$D/exitcodes.txt"
