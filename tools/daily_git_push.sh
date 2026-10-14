#!/usr/bin/env bash
# tools/daily_git_push.sh —— 日更收尾：把当天的改动**提交 + 推送**到 GitHub（尺子门 + 读回校验 + 留痕）
#
# 为什么有它（Owner 2026-10-14：「在日更中设置定时任务一起推到 git」）：
#   实测：本机 90 笔提交躺了三周，远端只有建仓时那个空 README（main = 7bf2c61）。
#   「每天的操作进 GitHub」这件事**在体系里从来没接线**；本脚本就是那条线。
#
# 三条口径（每条都是踩出来的）：
#   ① **只在日更收尾跑** —— 跑到一半的中间态不许进历史（2026-10-13 实测：日更到 L5 时闸门是红的）。
#   ② **落盘前先跑尺子** —— `--ruler=<命令>`；红了 ⇒ **不提交**、留痕、退出码 3。
#   ③ **推完必须读回** —— 远端 HEAD == 本地 HEAD 才算成（本库纪律：接口成功 ≠ 数据落下来）。
#
# 不许做的事：
#   · 不 `push --force`；远端领先（别人推过）⇒ **停下留痕**交人处理（fail-closed）。
#   · 干净就不造空提交。 · 只调 git，不打印任何密钥（密钥在 ~/.ssh）。
#
# 用法：
#   bash tools/daily_git_push.sh --why="daily-20261014-0330 收尾" [--repo <path>] [--ruler <cmd>] [--dry-run]
#   bash tools/daily_git_push.sh --selftest
#
# 退出码：0 = 已推送或干净无改动 ｜ 3 = 有改动但被尺子拦住（没提交）｜ 4 = 推送/读回失败（含远端领先）｜ 2 = 用法或环境错
set -uo pipefail

REPO="/Users/lute/Project/audit_multi_content"
WHY=""; RULER=""; DRY=0; SELFTEST=0; LEDGER=""

while [ $# -gt 0 ]; do
  case "$1" in
    --repo=*)   REPO="${1#--repo=}" ;;
    --repo)     shift; REPO="${1:-}" ;;
    --why=*)    WHY="${1#--why=}" ;;
    --why)      shift; WHY="${1:-}" ;;
    --ruler=*)  RULER="${1#--ruler=}" ;;
    --ruler)    shift; RULER="${1:-}" ;;
    --dry-run)  DRY=1 ;;
    --selftest) SELFTEST=1 ;;
    -h|--help)  sed -n '2,26p' "$0" | sed 's/^# \{0,1\}//'; exit 2 ;;
    *) echo "未知参数: $1"; exit 2 ;;
  esac
  shift
done

log() { printf '[daily-git-push %s] %s\n' "$(date '+%H:%M:%S')" "$*"; }

ledger() {   # $1=repo $2=verdict $3=detail
  [ -n "$LEDGER" ] || return 0
  mkdir -p "$(dirname "$LEDGER")" 2>/dev/null || return 0
  printf '{"at":"%s","repo":"%s","verdict":"%s","detail":"%s","why":"%s"}\n' \
    "$(date '+%Y-%m-%dT%H:%M:%S%z')" "$1" "$2" "$3" "${WHY//\"/\'}" >> "$LEDGER" 2>/dev/null || true
}

push_one() {   # $1=repo ⇒ 0/3/4
  local repo="$1" br head remote_head n
  [ -d "$repo/.git" ] || { log "⛔ 不是 git 仓：$repo"; ledger "$repo" error not-a-repo; return 2; }
  cd "$repo" || return 2
  br="$(git rev-parse --abbrev-ref HEAD)"
  if [ -z "$(git status --porcelain)" ]; then
    log "· $(basename "$repo")：无改动 ⇒ 跳过（不造空提交）"; ledger "$repo" clean no-changes; return 0
  fi
  n="$(git status --porcelain | wc -l | tr -d ' ')"
  log "· $(basename "$repo")：$n 条改动（分支 ${br}）"
  if [ -n "$RULER" ]; then
    log "  跑尺子：$RULER"
    if ! eval "$RULER" >/tmp/daily_git_push.ruler.log 2>&1; then
      log "  ⛔ 尺子红了 ⇒ **不提交** ｜ $(tail -2 /tmp/daily_git_push.ruler.log | tr '\n' ' ' | cut -c1-180)"
      ledger "$repo" blocked ruler-red; return 3
    fi
    log "  ✅ 尺子过"
  fi
  if [ "$DRY" = "1" ]; then
    log "  ⏭ --dry-run：不 add / 不 commit / 不 push"; ledger "$repo" dryrun "$n-dirty"; return 0
  fi
  git add -A || { ledger "$repo" error add-failed; return 4; }
  git commit -q -m "日更收尾自动提交：${WHY:-routine}（$n 个文件）" || { ledger "$repo" error commit-failed; return 4; }
  head="$(git rev-parse HEAD)"; log "  已提交 ${head:0:9}"
  if ! git push origin "$br" >/tmp/daily_git_push.push.log 2>&1; then
    if grep -qE "non-fast-forward|fetch first|\[rejected\]" /tmp/daily_git_push.push.log; then
      log "  ⛔ 远端领先（别人推过）⇒ **不 force**，停下交人处理"; ledger "$repo" blocked remote-ahead; return 4
    fi
    log "  ⛔ push 失败：$(tail -2 /tmp/daily_git_push.push.log | tr '\n' ' ' | cut -c1-200)"
    ledger "$repo" error push-failed; return 4
  fi
  remote_head="$(git ls-remote origin "refs/heads/$br" 2>/dev/null | awk '{print $1}')"
  if [ "$head" = "$remote_head" ]; then
    log "  ✅ 已推送并读回一致：${head:0:9}"; ledger "$repo" pushed "$head"; return 0
  fi
  log "  ⛔ 读回不一致（本地 ${head:0:9} ≠ 远端 ${remote_head:0:9}）"; ledger "$repo" error readback-mismatch; return 4
}

selftest() {
  local P=0 F=0 tmp remote work rc before after
  chk() { if [ "$2" = "1" ]; then P=$((P+1)); printf '  ✅ %s\n' "$1"; else F=$((F+1)); printf '  ❌ %s ｜ %s\n' "$1" "$3"; fi; }
  tmp="$(mktemp -d)"; remote="$tmp/remote.git"; work="$tmp/work"
  git init -q --bare "$remote" || { echo "裸远端建不起来"; return 1; }
  git init -q -b main "$work"; cd "$work" || return 1
  git config user.email t@example.com; git config user.name tester
  printf 'a\n' > a.txt; git add -A; git commit -qm init
  git remote add origin "$remote"; git push -q origin main
  LEDGER="$tmp/ledger.ndjson"; WHY="selftest"; REPO="$work"

  # ① 干净 ⇒ 跳过、不造空提交
  before="$(git rev-list --count HEAD)"; push_one "$work" >/dev/null 2>&1; rc=$?; after="$(git rev-list --count HEAD)"
  chk "① 干净仓 ⇒ rc=0 且**不造空提交**（提交数不变）" "$([ "$rc" = 0 ] && [ "$before" = "$after" ] && echo 1 || echo 0)" "rc=$rc ${before}→$after"

  # ② 脏 ⇒ 提交 + 推送 + 读回一致
  printf 'b\n' > b.txt; git add -A
  push_one "$work" >/dev/null 2>&1; rc=$?
  local lh rh; lh="$(git rev-parse HEAD)"; rh="$(git ls-remote origin refs/heads/main | awk '{print $1}')"
  chk "② 有改动 ⇒ rc=0 且远端 HEAD == 本地 HEAD（真推上去）" "$([ "$rc" = 0 ] && [ "$lh" = "$rh" ] && echo 1 || echo 0)" "rc=$rc $lh vs $rh"

  # ③ 尺子红 ⇒ **不提交**
  printf 'c\n' > c.txt; before="$(git rev-list --count HEAD)"
  RULER="false" push_one "$work" >/dev/null 2>&1; rc=$?; after="$(git rev-list --count HEAD)"
  chk "③ 尺子红 ⇒ rc=3 且**没有新提交**（不把坏状态钉进历史）" "$([ "$rc" = 3 ] && [ "$before" = "$after" ] && echo 1 || echo 0)" "rc=$rc ${before}→$after"
  RULER=""

  # ④ 远端领先 ⇒ 不 force、退出 4、远端不动
  printf 'd\n' > d.txt   # ← 故意**不提交**：要测的是「提交后 push 被拒」这一步
  local other="$tmp/other"; git clone -q "$remote" "$other" 2>/dev/null
  ( cd "$other" && git config user.email t@example.com && git config user.name other && printf 'x\n' > x.txt && git add -A && git commit -qm other-push && git push -q origin main )
  local rh_before rh_after; rh_before="$(git ls-remote origin refs/heads/main | awk '{print $1}')"
  push_one "$work" >/dev/null 2>&1; rc=$?; rh_after="$(git ls-remote origin refs/heads/main | awk '{print $1}')"
  chk "④ 远端领先 ⇒ rc=4、**不 force**（远端仍是别人的提交）" "$([ "$rc" = 4 ] && [ "$rh_before" = "$rh_after" ] && echo 1 || echo 0)" "rc=$rc"

  # ⑤ --dry-run ⇒ 什么都不动
  printf 'e\n' > e.txt; before="$(git rev-list --count HEAD)"
  DRY=1 push_one "$work" >/dev/null 2>&1; rc=$?; after="$(git rev-list --count HEAD)"; DRY=0
  chk "⑤ --dry-run ⇒ rc=0 且提交数不变" "$([ "$rc" = 0 ] && [ "$before" = "$after" ] && echo 1 || echo 0)" "rc=$rc ${before}→$after"

  # ⑥ 留痕：台账里有 pushed 与 blocked 两类
  local lp lb; lp="$(grep -c '"verdict":"pushed"' "$LEDGER" 2>/dev/null || echo 0)"; lb="$(grep -c '"verdict":"blocked"' "$LEDGER" 2>/dev/null || echo 0)"
  chk "⑥ 留痕：台账同时记下 pushed 与 blocked（不只记成功）" "$([ "$lp" -ge 1 ] && [ "$lb" -ge 1 ] && echo 1 || echo 0)" "pushed=$lp blocked=$lb"

  cd /; rm -rf "$tmp"
  printf '\n反向对照：通过 %d / 失败 %d\n' "$P" "$F"
  [ "$F" = 0 ]
}

if [ "$SELFTEST" = "1" ]; then selftest; exit $?; fi
[ -n "$WHY" ] || log "⚠️ 没给 --why（提交信息会写成 routine）"
LEDGER="${DAILY_GIT_PUSH_LEDGER:-$REPO/PMO/logs/daily-git-push.ndjson}"
rc_all=0; push_one "$REPO" || rc_all=$?
log "结束 rc=$rc_all ｜ 台账：$LEDGER"
exit "$rc_all"
