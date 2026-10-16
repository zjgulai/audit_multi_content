#!/bin/sh
# kb-check 体检档 六道闸门 sweep —— 只报不改（④ 例外：workflow_check 无干跑档，会写 kb/l8/）
# RUN=CHK-20261004-0810   cwd = 库根
set -u
cd "/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理" || exit 9
OUT="_chk-run-CHK-20261004-0810"
RUN="CHK-20261004-0810"
: > "$OUT/00-exitcodes.txt"

rec() { printf '%s\t%s\n' "$1" "$2" >> "$OUT/00-exitcodes.txt"; }

# ⓪ 预检查（只读）
sh 2>/dev/null; python3 ".dsh/skills/kb-check/scripts/preflight.py" > "$OUT/00-preflight.txt" 2>&1
rec "00-preflight" "$?"

# ① 登记表自检
sh kb/kbpy l7/scripts/skills_check.py > "$OUT/01-skills_check.txt" 2>&1
rec "01-skills_check" "$?"

# ② 层契约自检
sh kb/kbpy l7/scripts/layers_check.py > "$OUT/02-layers_check.txt" 2>&1
rec "02-layers_check" "$?"

# ③ 路由表对账 —— 三种输入面
sh kb/kbpy l7/scripts/routes_reconcile.py > "$OUT/03a-routes-noinput.txt" 2>&1
rec "03a-routes_noinput" "$?"
W="_eval-kb-manage/results_alias/routes-winners_20261004-0327-SUB.txt"
sh kb/kbpy l7/scripts/routes_reconcile.py "$W" > "$OUT/03b-routes-strict.txt" 2>&1
rec "03b-routes_strict" "$?"
sh kb/kbpy l7/scripts/routes_reconcile.py "$W" --alias > "$OUT/03c-routes-alias.txt" 2>&1
rec "03c-routes_alias" "$?"

# ④ 链路收口核验（⚠️ 无干跑档，本次声明写盘：kb/l8/workflow_check_<RUN>.json）
sh kb/kbpy l8/workflow_check.py "$RUN" > "$OUT/04-workflow_check.txt" 2>&1
rec "04-workflow_check" "$?"

# ⑤a 信封闸门（.py/.txt/.md 全量）
python3 tools/envelope_gate.py > "$OUT/05a-envelope_gate.txt" 2>&1
rec "05a-envelope_gate" "$?"

# ⑤b 信封闸门（库自带，只扫 .md）
sh kb/kbpy l8/envelope_census.py > "$OUT/05b-envelope_census.txt" 2>&1
rec "05b-envelope_census" "$?"

# ⑥ 投影一致性（只读调用，不加 --json-out）
sh kb/kbpy l8/projection_reconcile.py > "$OUT/06-projection_reconcile.txt" 2>&1
rec "06-projection_reconcile" "$?"

# ⑦ 宿主视图体检（MCP 工具等价物，只读；本轮由 agent 侧单独调用，这里只记时点）
date "+%Y-%m-%dT%H:%M:%S" > "$OUT/07-host-view-timestamp.txt"

echo "SWEEP DONE"
cat "$OUT/00-exitcodes.txt"
