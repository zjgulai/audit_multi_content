#!/bin/bash
# kb-check 体检档 —— 六道统一闸门逐条跑，逐条记退出码（只报不改）
# RUN = CHK-20261004-0110-FULL
ROOT="/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理"
cd "$ROOT" || exit 9
RUN="CHK-20261004-0110-FULL"
OUT="_chk-run-20261004-0110"
mkdir -p "$OUT"

run() {
  n="$1"; label="$2"; shift 2
  echo "===== $n $label ====="
  sh kb/kbpy "$@" > "$OUT/$n-$label.out" 2>&1
  rc=$?
  printf '%s\n' "$rc" > "$OUT/$n-$label.exit"
  echo ">>> $n $label  exit=$rc"
}

# 0 新鲜度（只读，不拒答）
run 0 freshness l7/scripts/freshness.py

# ① 登记表自检
run 1 skills_check l7/scripts/skills_check.py
# ② 层契约自检
run 2 layers_check l7/scripts/layers_check.py
# ③ 路由表对账（缺今日赢家表 ⇒ 预期退出码 2「未判定」）
run 3 routes_reconcile l7/scripts/routes_reconcile.py "kb/l7/reports/$RUN-routes-winners.json"
# ③b 路由表对账（拿盘上唯一在的过期赢家表，只作对照，不当今日判定）
echo "===== 3b routes_reconcile(过期赢家表 2026-09-29) ====="
sh kb/kbpy l7/scripts/routes_reconcile.py --alias _eval-kb-manage/blind_v2.winners.txt \
  > "$OUT/3b-routes-with-old-table.out" 2>&1
rc=$?; printf '%s\n' "$rc" > "$OUT/3b-routes-with-old-table.exit"; echo ">>> 3b routes(旧表) exit=$rc"

# ⑤a 信封闸门（.py/.txt/.md）
echo "===== 5a envelope_gate (python3 tools/) ====="
python3 tools/envelope_gate.py > "$OUT/5a-envelope_gate.out" 2>&1
rc=$?; printf '%s\n' "$rc" > "$OUT/5a-envelope_gate.exit"; echo ">>> 5a envelope_gate  exit=$rc"
# ⑤b 信封普查（.md）
run 5b envelope_census l8/envelope_census.py
# ⑥ 投影一致性
run 6 projection l8/projection_reconcile.py

# ④ 链路收口核验（无干跑档，会写 kb/l8/workflow_check_<RUN>.json）
echo "===== 4 workflow_check (RUN=$RUN) ====="
sh kb/kbpy l8/workflow_check.py "$RUN" > "$OUT/4-workflow_check.out" 2>&1
rc=$?; printf '%s\n' "$rc" > "$OUT/4-workflow_check.exit"; echo ">>> 4 workflow_check  exit=$rc"

echo "===== ALL DONE ====="
for f in "$OUT"/*.exit; do printf '%s\t%s\n' "$(cat "$f")" "$(basename "$f" .exit)"; done
