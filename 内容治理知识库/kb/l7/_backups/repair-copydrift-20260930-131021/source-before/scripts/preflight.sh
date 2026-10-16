#!/usr/bin/env bash
# kb-l0-feishu · 阶段 0 前置自检
#
# 用法:
#   bash scripts/preflight.sh              # 默认 bot 身份自检
#   PREFLIGHT_AS=user bash scripts/preflight.sh
#
# 退出码:
#   0 = 全部通过，可以继续
#   1 = 有 BLOCKER，停下并报告"缺什么"，不要绕路硬试
#
# 设计意图：把"认证/授权乱试 2 小时"压缩成一次 30 秒的判定。

set -uo pipefail

AS="${PREFLIGHT_AS:-bot}"
PROFILE="${L8_PROFILE:-dsh-kb}"
BASE_TOKEN="${KB_BASE_TOKEN:-GnRZbIuXraCzf0sGr2UcmZ62nfc}"
TABLE_ID="${KB_TABLE_ID:-tblMGtPfe8ZUsEdP}"

BLOCKERS=0
WARNINGS=0

ok()   { printf '  [ OK ]   %s\n' "$*"; }
warn() { printf '  [WARN]   %s\n' "$*"; WARNINGS=$((WARNINGS+1)); }
bad()  { printf '  [BLOCK]  %s\n' "$*"; BLOCKERS=$((BLOCKERS+1)); }

echo "== kb-l0-feishu 阶段 0 前置自检 =="
echo "身份=$AS   profile=$PROFILE"
echo

# ---- 1. 库根 ----------------------------------------------------------------
echo "[1/6] 库根定位"
KB="${KB_ROOT:-}"
if [ -z "$KB" ]; then
  for cand in "$HOME/.dsh/Momcozy知识库/kb" "$HOME/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理/kb"; do
    if [ -d "$cand/l8" ]; then KB="$(cd "$cand" && pwd -P)"; break; fi
  done
fi
if [ -z "$KB" ] || [ ! -d "$KB/l8" ]; then
  bad "找不到库根（缺 kb/l8）。请设 KB_ROOT=<库根绝对路径>"
else
  ok "库根: $KB"
  echo "         l8 脚本数: $(ls "$KB"/l8/*.py 2>/dev/null | wc -l | tr -d ' ')"
fi
echo

# ---- 2. 锁与并发 ------------------------------------------------------------
echo "[2/6] 并发锁检查"
if [ -n "$KB" ] && [ -e "$KB/.kb.lock" ]; then
  bad "存在 $KB/.kb.lock —— 可能有另一批在跑，先确认再动"
elif [ -n "$KB" ] && [ -d "$KB/.work" ]; then
  recent="$(find "$KB/.work" -type f -newermt '-30 minutes' 2>/dev/null | wc -l | tr -d ' ')"
  if [ "$recent" -gt 0 ]; then
    warn ".work 近 30 分钟有 $recent 个文件写入，确认是否另一批在跑"
  else
    ok ".work 近 30 分钟无写入"
  fi
else
  ok "未发现锁"
fi
echo

# ---- 3. lark-cli ------------------------------------------------------------
echo "[3/6] lark-cli"
export PATH="$HOME/.dsh/bin:$PATH"
LARK="$(command -v lark-cli || true)"
if [ -z "$LARK" ]; then
  bad "lark-cli 不在 PATH（应位于 ~/.dsh/bin/lark-cli）"
else
  ok "lark-cli: $LARK"
  status_out="$(lark-cli auth status --profile "$PROFILE" 2>&1 || true)"
  if printf '%s' "$status_out" | grep -qiE 'ready|valid|ok'; then
    ok "$AS 身份可用"
  else
    if [ "$AS" = "user" ]; then
      bad "$AS 身份不可用 —— 发一条设备码（只放缺的那个 scope，一次只发一条）"
      printf '%s\n' "$status_out" | sed 's/^/         /' | head -8
    else
      warn "$AS 身份状态无法确认，下面用真实读取复核"
      printf '%s\n' "$status_out" | sed 's/^/         /' | head -5
    fi
  fi
fi
echo

# ---- 4. 真实读取复核（决定性的那一步） ---------------------------------------
echo "[4/6] bot 真实读取复核（决定记录层/结构层能不能走 bot）"
if [ -z "${LARK:-}" ]; then
  bad "跳过：lark-cli 不可用"
else
  out="$(lark-cli base +record-list --base-token "$BASE_TOKEN" --table-id "$TABLE_ID" \
         --page-size 1 --as "$AS" --profile "$PROFILE" 2>&1 || true)"
  if printf '%s' "$out" | grep -qE 'record_id|records'; then
    ok "bot 可读「材料收集」→ 记录层/结构层核对不需要设备码"
  elif printf '%s' "$out" | grep -qE '91403|1063002|40403|DENY|forbidden'; then
    bad "资源级 ACL：要所有者在【能调接口的应用(守衡)】上加协作者（用户能打开≠应用能读）"
  elif printf '%s' "$out" | grep -qiE 'token.*(expired|missing)|unauthorized|401'; then
    bad "登录态问题（不是权限）：发一条设备码，10 分钟有效，一次只发一条"
  else
    warn "读取返回未识别，请人工看下面原文"
    printf '%s\n' "$out" | sed 's/^/         /' | head -8
  fi
fi
echo

# ---- 5. python 依赖 ---------------------------------------------------------
echo "[5/6] python3 依赖"
for mod in zstandard yaml; do
  if python3 -c "import $mod" 2>/dev/null; then ok "python3 -m $mod"; else warn "缺 python3 模块: $mod（pip3 install $mod）"; fi
done
echo

# ---- 6. 报告目录 ------------------------------------------------------------
echo "[6/6] 产物目录"
if [ -n "$KB" ] && [ -d "$KB/l8/runs" ]; then
  ok "$KB/l8/runs 可写（本轮产物落这里，RUN=\$(date +%Y%m%d-%H%M)）"
else
  warn "找不到 $KB/l8/runs"
fi
echo

# ---- 结论 -------------------------------------------------------------------
echo "== 结论 =="
if [ "$BLOCKERS" -gt 0 ]; then
  echo "  ❌ $BLOCKERS 个 BLOCKER，$WARNINGS 个 WARNING"
  echo "  → 停下来，把上面的 BLOCK 逐条报告为「缺什么」，不要绕路硬试。"
  exit 1
fi
echo "  ✅ 通过（$WARNINGS 个 WARNING）→ 可以进入阶段 1"
exit 0
