#!/bin/bash
# daily_via_skill.sh —— 日更**走 skill** 版驱动（与现有 com.kb.pipeline-daily 并排，可一条 launchctl 切回）
#
# 为什么要有它（用户 2026-10-05 裁定：「日更走 skill」）：
#   现有的 com.kb.pipeline-daily → l7/scripts/daily_sync.py 是**脚本直调各层引擎**：
#   跑得对、跑得快，但**一层 skill 都没加载** ⇒ 层侧落章里没有 skill 证据，
#   `skill_invocation_audit.py` 只能读成 `registry_echo`（声明），不是 `agent_reported`（观测）。
#   本脚本把同一件事交给一个 **headless DSH agent** 做：它**能加载 skill**（脚本不能）。
#
# 与现有任务的关系 —— ★★ 2026-10-09：**已改为「只跑本脚本」**（Owner 裁定）
#   · com.kb.pipeline-daily        → daily_sync.py（脚本版）**已 bootout**
#     ⚠️ 此前它只是**声明**"已停用"，**实际仍在跑** —— 实测 2026-10-09 两个日更
#        03:30 同刻起跑（旧版 L0 03:30:18 ／ 新版 03:36:21），靠 `.kb.lock` 撞运气才没交错。
#   · com.kb.pipeline-daily-skill  → 本脚本（**唯一在跑的日更**）
#   ★ **下线脚本版之前必须先补的一环**（2026-10-09 已补）：脚本版每层跑完会调
#     `daily_sync.py::observe()` → `layer_freshness.measure()` 落 sidecar 观测；本脚本原先**没有**
#     这一步（实测 `kb_pipeline.py` 里 `layer_freshness` 命中 0）。而幂等层跑完**不留新落章**
#     ⇒ 那种日子兜底靠的正是 sidecar；不补就下线，某天某层会判陈旧 ⇒ `freshness` 转红
#     ⇒ **评审链 fail-closed 永久拒答**。现由本脚本在 agent 前后各调一次
#     `kb/l8/observe_layers.py`（`--snapshot` / `--land`）补上。
#   ★ 时刻：2026-10-06 起 03:30（日更持全局单槽 12~24 分钟，08:30 会挡住人白天用守衡）。
#     `kb/l8/check_agents_md_drift.py` 的 [credential_horizon] 互校 plist + `~/.dsh/AGENTS.md`。
#   ⇒ **回退**（脚本版随时可 load 回，plist 文件仍在 `~/Library/LaunchAgents/`）：
#       launchctl bootout gui/$(id -u)/com.kb.pipeline-daily-skill
#       launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.kb.pipeline-daily.plist
#
# 用法：
#   bash kb/l8/daily_via_skill.sh                      # 全层（L0,L1..L6,L7）
#   KB_SKILL_LAYERS=L1,L2,L3,L4,L5,L6,L7 bash kb/l8/daily_via_skill.sh   # 跳过 L0（无有效令牌时）
#   KB_SKILL_DRY=1 bash kb/l8/daily_via_skill.sh       # 只让 agent 读任务书并复述计划，不执行任何写
#
# 退出码：0=agent 正常结束 ｜ 3=认领被占（别的会话在跑，本次不跑）｜ 124=超时 ｜ 其他=agent 异常
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
KBPY="$ROOT/kb/kbpy"
TASKFILE="$ROOT/kb/l8/daily_via_skill.md"
DSH_BIN="${KB_SKILL_DSH_BIN:-/Applications/DSH Desktop.app.pre-lute-20260907-111753/Contents/Resources/app.asar.unpacked/node_modules/@deepseek-ai/dsh/lib/bin.js}"
LOGDIR="$HOME/Library/Logs/kb-pipeline-skill"
LOG="$LOGDIR/out.log"
TIMEOUT_S="${KB_SKILL_TIMEOUT_S:-3600}"
LAYERS="${KB_SKILL_LAYERS:-L0,L1,L2,L3,L4,L5,L6,L7}"
BASE="${KB_SKILL_BASE:-daily-$(date +%Y%m%d-%H%M)}"
DRY="${KB_SKILL_DRY:-0}"

mkdir -p "$LOGDIR"
log() { echo "[skill-daily $(date +%H:%M:%S)] $*" | tee -a "$LOG"; }

cd "$ROOT" || { echo "找不到库根 $ROOT"; exit 2; }
[ -f "$TASKFILE" ] || { log "⛔ 找不到任务书 $TASKFILE"; exit 2; }
[ -f "$DSH_BIN" ]  || { log "⛔ 找不到 dsh CLI $DSH_BIN"; exit 2; }

# 可移植超时（macOS 没有 timeout(1)）
run_timeout() {                     # $1=秒 其余=命令
  local t="$1"; shift
  "$@" & local p=$!
  ( sleep "$t"; kill -TERM "$p" 2>/dev/null; sleep 5; kill -KILL "$p" 2>/dev/null ) & local w=$!
  wait "$p" 2>/dev/null; local rc=$?
  kill "$w" 2>/dev/null; wait "$w" 2>/dev/null
  return $rc
}

log "=========== 日更（走 skill）开始 ｜ BASE=$BASE ｜ 层=$LAYERS ｜ DRY=$DRY ｜ 超时=${TIMEOUT_S}s ==========="

# ① 会话级认领（全局单槽；exit 3 = 别人在跑 ⇒ 不抢，见 AGENTS.md 并发纪律）
#
# ★ 2026-10-06 改两处，两处都是同一次真实事故逼出来的（那把「全局单槽」曾经是**名义上的**）：
#
#   ① `--holder-pid $$` —— 认领必须记**持有者**（本脚本）的 pid。
#      原先什么都不传 ⇒ `claim` 记的是它**自己**的 pid，而它写完就退出 ⇒
#      `_stale()` 的「pid 已不在且过了宽限期」这条**必然命中** ⇒ 任何跑过 5 分钟的日更
#      都被就绪巡检判成「陈旧」并用 `release --force` **抡掉单槽**。
#      实测两次：2026-10-05 10:12:12（daily-20261005-0957，13 分钟）、
#                2026-10-06 08:35:46（daily-20261006-0830，6 分钟）—— 两次 worker 都还活着。
#
#   ② `--session "$SESSION"` —— 与 EXIT trap 用**同一个**会话标识。
#      原先认领记的 session 是 `unknown`，而 `cmd_release` 的鉴权要 pid 或 session 对上 ⇒
#      **trap 那条 release 从来没有成功过**（它只是被 `>/dev/null` 吞了，然后无条件 echo 一句
#      「已释放认领」—— 一句话说出去、却没有任何一行验过它，见 AGENTS.md §2.4.2）。
SESSION="skill-daily-$BASE-$$"
if ! sh "$KBPY" l7/scripts/kb_loop_claim.py claim --base "$BASE" \
       --holder-pid $$ --session "$SESSION" >/dev/null 2>&1; then
  log "⛔ 认领被别的会话占着（claim exit 3）⇒ 本次不跑（**不抢、不 --take-over**）"
  sh "$KBPY" l7/scripts/kb_loop_claim.py status 2>&1 | tail -2 | sed 's/^/    /' | tee -a "$LOG"
  exit 3
fi
log "✅ 已认领 ${BASE}（holder_pid=$$ ｜ session=${SESSION}）"
# ★ trap 里那句「已释放认领」现在是**照实说**的：把 release 的原话打出来，成功失败分得开。
#   原先是 `release >/dev/null 2>&1; echo "已释放认领"` —— 无论 release 退几都印同一句。
trap 'out=$(sh "$KBPY" l7/scripts/kb_loop_claim.py release --base "$BASE" --session "$SESSION" 2>&1); rc=$?; echo "[skill-daily $(date +%H:%M:%S)] 释放认领 rc=$rc ｜ $out" | tee -a "$LOG"' EXIT INT TERM

# ② 组装任务（任务书原文 + 本次参数；**不改写任务书**）
TASK="$(cat "$TASKFILE")

---
## 本次运行参数（由驱动注入）

- BASE = \`$BASE\`
- 要跑的层 = \`$LAYERS\`（**只跑这些**；没列出的层不要碰）
- 库根 = \`$ROOT\`"

if [ "$DRY" = "1" ]; then
  TASK="$TASK

---
## ★ 本次是**只读预演**（KB_SKILL_DRY=1）

**不要执行任何写操作、不要跑任何层引擎、不要记账。**
只做三件事：① 读 \`kb/l7/registry/layers.yaml\` 列出各层 skill 与 engine；
② 用 \`skill\` 工具加载 \`kb-l0-feishu\`（证明加载通路可用）；③ 复述你打算怎么跑这次日更（分步）。
完成即结束。"
fi

# ③ 交给 headless agent（cwd 已在库根 ⇒ 会加载本库的 AGENTS.md 纪律）
#    ★ 必须**带超时**：agent 挂住时若不走 124 分支，认领会被拖到 TTL 才过期，
#      而「陈旧认领」正是 2026-10-04 那次白等 30 分钟的成因（AGENTS.md 有记录）。
# ★ 2026-10-09：「逐层落新鲜度观测」这一步，脚本版有、skill 版原先没有 ——
#   实测：`kb_pipeline.py` 里 `layer_freshness` 命中 0；sidecar 八层的 note 全写着
#   「daily_sync.py 写档后落的真实观测（修复1）」。而 `judge()` 的**首选**来源虽然是层落章的
#   mtime，但**幂等层跑完不留新落章**（`修复2` 原文：L1/L3/L5/L6 的落章 mtime 停在 23.6h）
#   ⇒ 那种日子兜底靠的正是 sidecar。**不补这一步，脚本版一下线，某天某层就会判陈旧，
#   而 freshness 转红 ⇒ 评审链 fail-closed 永久拒答。**
#   测前先取指纹/水位，好让 `measure()` 能**现算复核**产物到底变没变（保守方向）。
if [ "$DRY" = "1" ]; then
  log "⏭ 只读预演（DRY=1）⇒ 不取测前指纹、不落观测（避免把「没跑」记成「跑过」）"
else
  python3 kb/l8/observe_layers.py "$BASE" --snapshot --layers "$LAYERS" 2>&1 | tee -a "$LOG"
fi

log "▶ 起 headless agent（cwd=${ROOT}，超时 ${TIMEOUT_S}s，RUN_ID=${BASE}）"
# ★ 注入 KB_PIPELINE_RUN_ID：落章引擎（kb/l7/scripts/stamp_meta.py:41）读它写 pipeline_run_id；
#   不注入则该键为 None，审计 E2 查不到本 RUN（2026-10-05 预演实测得出）。
KB_PIPELINE_RUN_ID="$BASE" run_timeout "$TIMEOUT_S" node "$DSH_BIN" --profile headless "$TASK" >>"$LOG" 2>&1
rc=$?
log "◀ agent 结束 exit=${rc}"

# ★ 2026-10-09：逐层落观测（与脚本版 `daily_sync.py` 的 `observe()` 同位、同语义）。
#   语义：观测 ≠ 变更 —— 它记「本 RUN 里这一层跑过、退出码多少」，幂等日也记。
#   失败**如实记**：`measure()` 在退出码非 0 时强制 `change_state=blocked`，
#   而 `judge()` 把 blocked 判成「不算跑过 ⇒ 陈旧」⇒ 不会把失败记成跑过（fail-closed）。
#   某层找不到本 RUN 的**非预演**落章 ⇒ **不落观测**并明着打出来（不许谎报跑过）。
if [ "$DRY" = "1" ]; then
  log "⏭ 只读预演（DRY=1）⇒ 不落观测"
else
  python3 kb/l8/observe_layers.py "$BASE" --land --agent-rc "$rc" --layers "$LAYERS" 2>&1 | tee -a "$LOG"
  log "   （该步退出码 3 = 有层没落章、已明示；**不改变日更本身的退出码**）"
fi

# ★ 2026-10-09（Owner 裁定「推荐 A」）：**日更摘要 → 推守衡私聊**。
#   为什么要有：实测日更**什么都不推**（本脚本 / 任务书 / daily_health.py / l0_daily_sync.py
#   四处零发送动作；daily_health.py 自己写着「要接告警请读 daily-health-latest.json」，
#   而从来没人接）。全库唯一的推送方是就绪巡检，它推的是「守衡能不能用」，**不含一条数据变更**。
#   口径照 kb-l0-feishu 的 coverage-matrix：**12 类 × 四态**，每类一行 = 类型+状态+条数+原因码。
if [ "$DRY" = "1" ]; then
  log "⏭ 只读预演（DRY=1）⇒ 不推日更摘要（避免报一次没跑过的日更）"
else
  python3 kb/l8/daily_digest.py "$BASE" --push 2>&1 | tee -a "$LOG"
  log "   （摘要推送失败**不改变日更退出码**；上面那行会显示 ✅/❌）"
fi

# ★ 2026-10-10（PRD §16 应对后半句「**P0 层定期回归测试**」／ §15「**P0 层漏报率 = 0**」）：
#   11 条 P0 红线是确定性正则 —— **正则不会自己坏**，但改模式表 / 词表 / `article_no` 接线
#   会**静默**让某条红线漏放，而 P0 漏放 = **红线直接发出去**（最坏一类）。
#   本步**只观测**：红了**不改变日更退出码**（理由与上面两条一致 —— 日更是数据作业，
#   红线回归是另一条判据；拿它拦日更会把「一条红线读不到」升级成「整条数据链停摆」）。
#   ★ 但它**必须喊出来**：红了打一行 `P0_REGRESSION=FAIL`，由摘要/巡检按它告警。
if [ "$DRY" = "1" ]; then
  log "⏭ 只读预演（DRY=1）⇒ 跳过 P0 层回归测试"
else
  _p0out=$(python3 kb/l8/p0_regression.py 2>&1); _p0rc=$?
  printf '%s\n' "$_p0out" >> "$LOG"
  printf '%s\n' "$_p0out" | tail -3 | sed 's/^/   /'
  if [ "$_p0rc" = "0" ]; then
    log "   ✅ P0 层回归：11 条红线对逐字源表达**全部仍命中**（漏报率 0）"
  else
    log "   ❌ P0_REGRESSION=FAIL（rc=$_p0rc）—— ⚠️ **红线可能漏放**！" \
        "跑 python3 kb/l8/p0_regression.py 看逐条，先查模式表/词表/article_no 接线"
  fi
fi

# ★ 2026-10-14（Owner：「在日更中设置定时任务一起推到 git」）：**日更收尾自动提交并推送**。
#   为什么放这里：跑到一半的中间态不许进 git 历史（2026-10-13 实测：日更跑到 L5 时闸门是红的）。
#   脚本自带三道门：干净就跳过（不造空提交）｜`--ruler` 红了**不提交**｜推完**读回校验**（远端 HEAD == 本地 HEAD）；
#   另外**绝不 force**：远端领先就停下留痕交人（fail-closed）。台账 PMO/logs/daily-git-push.ndjson。
#   ★ 尺子用 workflow_smoke（Owner 定的「改动不许弄坏工作流」那把尺子）——**当前绿**。
#     ⚠️ 不用 test_agent.mjs：它此刻红 3 项（别的会话在途修改），拿它当门会让「当天所有改动都记不进版本」。
#   ★ 与上面几条同档：**不改变日更退出码**（git 推不上去不该让数据链停摆），但**必须喊出来**。
GIT_PUSH_SH="${SHOUHENG_GIT_PUSH_SH:-/Users/lute/Project/audit_multi_content/tools/daily_git_push.sh}"
if [ "$DRY" = "1" ]; then
  log "⏭ 只读预演（DRY=1）⇒ 跳过日更收尾的 git 提交推送"
elif [ -x "$GIT_PUSH_SH" ]; then
  _gitout=$(bash "$GIT_PUSH_SH" --why="daily-${BASE} 收尾（日更自动提交）" \
             --ruler="cd '$ROOT' && python3 kb/l8/workflow_smoke.py" 2>&1); _gitrc=$?
  printf '%s\n' "$_gitout" >> "$LOG"
  printf '%s\n' "$_gitout" | sed 's/^/   /'
  case "$_gitrc" in
    0) log "   ✅ 日更收尾 git：已提交并推送（或本就无改动）" ;;
    3) log "   ❌ GIT_PUSH=BLOCKED（尺子红 ⇒ 未提交）—— 先跑 python3 kb/l8/workflow_smoke.py 看红项" ;;
    *) log "   ❌ GIT_PUSH=FAIL（rc=$_gitrc）—— 见上面输出与 PMO/logs/daily-git-push.ndjson" ;;
  esac
else
  log "⛔ 找不到 git 推送脚本 $GIT_PUSH_SH ⇒ 跳过（不影响日更退出码）"
fi

case "$rc" in
  0)   log "日更（走 skill）结束 ｜ 成败看 agent 报告里的四条审计与 freshness" ;;
  124) log "⛔ 超时（${TIMEOUT_S}s）—— 认领会在退出时释放；下轮由 kb_review_chain / 巡检自愈" ;;
  *)   log "⛔ agent 异常退出（exit=${rc}）" ;;
esac
exit "$rc"