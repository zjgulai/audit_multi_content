#!/usr/bin/env bash
# 一次性落地：让工作台的镜像器改成「向本地 HTTP 取宿主库」。
#
# 为什么要有这个脚本：工作台目录与 ~/Library/LaunchAgents 都不在本会话的沙箱里，
# 要单独放行一次。做成脚本 + 幂等 + 可回滚，比一串手打命令可复核。
#
# 它做四件事：
#   1. 给工作台打补丁（kb-sync.ts / config.ts / app.ts，见 patch-workbench-kb-remote.py）
#   2. 装宿主库取数服务的 launchd 作业（com.kb-hostlib）—— 它读文件、发 HTTP，
#      不受加密代理对 Electron 的影响
#   3. 给工作台的 launchd 作业加环境变量 WORKBENCH_MOMCOZY_KB_REMOTE
#   4. 重启工作台，让它带着新环境变量起来
#
# 用法：
#   bash setup-kb-remote.sh            # 干跑，只打印将要做什么
#   bash setup-kb-remote.sh --apply    # 真落地
set -uo pipefail

WB="${WB:-/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/工作台}"
# 派生视图：**不放在 ~/.dsh/Momcozy知识库/** —— 那里现在是权威库的软链接入口
# （~/.dsh/Momcozy知识库/kb → 工作区/kb），派生视图放进去会被 kb-content-review 误当库根。
KB_HOSTLIB="${KB_HOSTLIB:-/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理/kb/.work/hostlib}"
SERVE_PY="${SERVE_PY:-/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理/kb/.work/kb-hostlib-serve.py}"
PATCH_PY="${PATCH_PY:-/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理/kb/.work/patch-workbench-kb-remote.py}"
PORT="${KB_HOSTLIB_PORT:-4508}"
LABEL="com.kb-hostlib"
PLIST="$HOME/Library/LaunchAgents/${LABEL}.plist"
APP_PLIST="$HOME/Library/LaunchAgents/com.workbench.app.plist"
LOG_DIR="$HOME/Library/Logs/kb-hostlib"
REMOTE_URL="http://127.0.0.1:${PORT}"

APPLY=0
[ "${1:-}" = "--apply" ] && APPLY=1

say() { printf '[setup] %s\n' "$*"; }
run() { if [ "$APPLY" = 1 ]; then "$@"; else say "（干跑）$*"; fi; }

# ── 0. 前置检查 ─────────────────────────────────────────────────────────
for f in "$WB/apps/server/src/kb/kb-sync.ts" "$SERVE_PY" "$PATCH_PY" "$KB_HOSTLIB/_meta/manifest.json"; do
  [ -e "$f" ] || { say "缺文件：$f"; exit 1; }
done
say "工作台 = $WB"
say "宿主库载荷 = ${KB_HOSTLIB}（$(python3 -c "import json;print(len(json.load(open('${KB_HOSTLIB}/_meta/manifest.json'))['docs']),'条')")）"
say "取数服务 = ${REMOTE_URL}（python3 ${SERVE_PY}）"

# ── 1. 打补丁 ───────────────────────────────────────────────────────────
say "① 打补丁（幂等：锚点对不上就整体中止，不会半改）"
if grep -q "remoteBaseUrl" "$WB/apps/server/src/kb/kb-sync.ts" 2>/dev/null; then
  say "   已经打过（kb-sync.ts 里已有 remoteBaseUrl），跳过"
else
  if [ "$APPLY" = 1 ]; then
    python3 "$PATCH_PY" --wb "$WB" --apply || { say "   打补丁失败，中止"; exit 1; }
  else
    python3 "$PATCH_PY" --wb "$WB" || true
  fi
fi

# ── 2. 装取数服务的 launchd 作业 ─────────────────────────────────────────
say "② 装取数服务作业 $LABEL"
PLIST_BODY=$(cat <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <!-- 由 kb/.work/setup-kb-remote.sh 生成；卸载：launchctl bootout gui/$(id -u)/$LABEL && rm $PLIST -->
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key><array>
    <string>/usr/bin/python3</string>
    <string>$SERVE_PY</string>
    <string>--hostlib</string><string>$KB_HOSTLIB</string>
    <string>--port</string><string>$PORT</string>
    <string>--bind</string><string>127.0.0.1</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>5</integer>
  <key>StandardOutPath</key><string>$LOG_DIR/kb-hostlib.out</string>
  <key>StandardErrorPath</key><string>$LOG_DIR/kb-hostlib.err</string>
</dict>
</plist>
PLIST
)
if [ "$APPLY" = 1 ]; then
  mkdir -p "$LOG_DIR"
  printf '%s\n' "$PLIST_BODY" > "$PLIST"
  launchctl bootout "gui/$(id -u)/$LABEL" >/dev/null 2>&1 || true
  launchctl bootstrap "gui/$(id -u)" "$PLIST" || { say "   bootstrap 失败"; exit 1; }
  for _ in $(seq 1 20); do
    curl -s --max-time 2 "$REMOTE_URL/health" >/dev/null 2>&1 && break
    sleep 0.5
  done
  curl -s --max-time 3 "$REMOTE_URL/health" | head -c 200; echo
else
  say "（干跑）将写入 $PLIST"
  say "（干跑）launchctl bootstrap gui/$(id -u) $PLIST"
fi

# ── 3. 给工作台作业加环境变量 ───────────────────────────────────────────
say "③ 给 com.workbench.app 加 WORKBENCH_MOMCOZY_KB_REMOTE=$REMOTE_URL"
if grep -q "WORKBENCH_MOMCOZY_KB_REMOTE" "$APP_PLIST" 2>/dev/null; then
  say "   已存在，跳过"
elif [ "$APPLY" = 1 ]; then
  cp "$APP_PLIST" "$APP_PLIST.bak-$(date +%Y%m%d-%H%M%S)"
  python3 - "$APP_PLIST" "$REMOTE_URL" <<'PY'
import sys
path, url = sys.argv[1], sys.argv[2]
text = open(path, encoding='utf-8').read()
block = ("  <key>EnvironmentVariables</key><dict>\n"
         f"    <key>WORKBENCH_MOMCOZY_KB_REMOTE</key><string>{url}</string>\n"
         "  </dict>\n")
anchor = "  <key>RunAtLoad</key>"
assert text.count(anchor) == 1, '锚点不是 1 次，未改动'
open(path, 'w', encoding='utf-8').write(text.replace(anchor, block + anchor, 1))
print('[setup]   已写入 EnvironmentVariables')
PY
  launchctl bootout "gui/$(id -u)/com.workbench.app" >/dev/null 2>&1 || true
else
  say "（干跑）将备份并写入 $APP_PLIST"
fi

# ── 4. 重启工作台 ───────────────────────────────────────────────────────
say "④ 重启工作台（带新环境变量）"
if [ "$APPLY" = 1 ]; then
  launchctl bootstrap "gui/$(id -u)" "$APP_PLIST" >/dev/null 2>&1 || true
  launchctl kickstart -k "gui/$(id -u)/com.workbench.app" >/dev/null 2>&1 || true
  for _ in $(seq 1 60); do
    curl -s --max-time 2 "http://127.0.0.1:4317/api/health" >/dev/null 2>&1 && break
    sleep 0.5
  done
  curl -s --max-time 5 "http://127.0.0.1:4317/api/health"; echo
else
  say "（干跑）launchctl kickstart -k gui/$(id -u)/com.workbench.app"
fi

say "完成。验收：curl -s http://127.0.0.1:4317/api/kb/sync | python3 -m json.tool | head -20"
