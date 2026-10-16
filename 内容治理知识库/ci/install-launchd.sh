#!/bin/bash
# install-launchd.sh —— 把 KB 闸门只读巡检装成 launchd 定时任务（幂等，可反复跑）
#
# 为什么要有这个脚本，而不是 README 里那三行 cp/bootstrap：
#   1. launchd 的 StandardOutPath / StandardErrorPath **不会自建目录**；
#      目录不存在时任务起不来或日志丢失 —— 所以先 mkdir -p。
#   2. 库根路径写死在 plist 里。库一旦挪窝，装上去的是个坏任务，而且**不报错**。
#      本脚本会核对 plist 里的路径与当前库根是否一致，不一致就用当前库根重新生成。
#   3. 装完必须**立刻验证**（kickstart），否则要等到 14:00 才知道装没装对。
#      launchd 非 0 退出**不通知**，所以这里等报告落盘并把结论打出来。
#
# 用法：
#   bash ci/install-launchd.sh              # 安装 + 立刻跑一次 + 验证
#   bash ci/install-launchd.sh --no-run     # 只安装，不立刻跑
#   bash ci/install-launchd.sh --wait 1800  # 验证等待窗口（秒，默认 900）
#   bash ci/install-launchd.sh --uninstall  # 卸载
#
# 范围（scope，2026-10-04 14:1x 加）：
#   · 不传 → **沿用模板里的 `--scope`**（模板现为 `full` = 14 把，与 CI 四份配置一致）。
#   · `--scope core` / `--scope full` → 覆盖模板，生成件按你给的那档装。
#   · 环境变量 `KB_GATES_SCOPE` 等效。优先级：--scope > KB_GATES_SCOPE > 模板。
#   ⚠️ 切 `full` 会让本机每日红从 1 把（l0）变 2 把（l0 + projection），两把都是人做的动作。
#      出处与代价见 `ci/launchd/com.kb.gates.plist` 文件头。
#
# 退出码：0 装好**且验证通过** ｜ 1 安装失败 ｜ 2 用法错 ｜ 3 装好了但**没验成**（报告没在等待窗口内出现）
set -euo pipefail

LABEL="com.kb.gates"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"                    # 库根（含 kb/KB-ROOT.json 的那一层）
TPL="$HERE/launchd/$LABEL.plist"
DST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOGDIR="$HOME/Library/Logs/kb-gates"
DOMAIN="gui/$(id -u)"

NO_RUN=0; UNINSTALL=0; DRY_RUN=0; WAIT=900; SCOPE="${KB_GATES_SCOPE:-}"
while [ $# -gt 0 ]; do
  case "$1" in
    --no-run)    NO_RUN=1; shift ;;
    --uninstall) UNINSTALL=1; shift ;;
    --dry-run)   DRY_RUN=1; shift ;;
    --wait)      WAIT="${2:-}"; shift 2 ;;
    --scope)     SCOPE="${2:-}"; shift 2 ;;
    --core)      SCOPE=core; shift ;;
    --full)      SCOPE=full; shift ;;
    -h|--help)   sed -n '2,26p' "$0"; exit 0 ;;
    *) echo "未知参数：$1" >&2; exit 2 ;;
  esac
done
case "$WAIT" in ''|*[!0-9]*) echo "--wait 需要正整数秒" >&2; exit 2 ;; esac
# scope 只认 run_gates.py 明列的两档；拼错就报错，别默许一个跑不起来的命令行进 plist
case "$SCOPE" in '') ;; core|full) ;; *) printf '%s\n' "❌ --scope 只接受 core 或 full，收到的是：[$SCOPE]" >&2; exit 2 ;; esac

if [ "$UNINSTALL" = "1" ]; then
  launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
  rm -f "$DST"
  echo "已卸载 $LABEL（日志保留在 $LOGDIR）"
  exit 0
fi

# ── 0. 前提自检：装之前先确认这是个真库根 ────────────────────────────────────
[ -f "$ROOT/kb/KB-ROOT.json" ] || { echo "❌ $ROOT 不是权威库根（缺 kb/KB-ROOT.json）" >&2; exit 1; }
[ -x "$ROOT/kb/kbpy" ]         || { echo "❌ 缺 kb/kbpy 解释器入口" >&2; exit 1; }
[ -f "$TPL" ]                  || { echo "❌ 找不到模板 $TPL" >&2; exit 1; }
command -v /usr/bin/python3 >/dev/null || { echo "❌ 缺 /usr/bin/python3" >&2; exit 1; }

# ── 1. 日志目录（launchd 不自建）───────────────────────────────────────────
mkdir -p "$LOGDIR"

# ── 2. 生成 plist：把模板里的库根换成**当前**库根（库挪窝也装不错）────────────
TMP="$(mktemp -t kb-gates-plist)"
trap 'rm -f "$TMP"' EXIT
# 模板里的旧路径 = ProgramArguments 里 `cd "<库根>"` 的那个路径，用当前 ROOT 替换。
# ⚠️ 别把 `&&` 写进正则：plist 里它是 XML 转义过的 `&amp;&amp;`（实测踩过，匹配不到）。
OLD="$(sed -n 's|.*cd "\([^"]*\)".*|\1|p' "$TPL" | head -1)"
if [ -z "$OLD" ]; then
  echo "❌ 模板里没解析出库根路径（模板结构可能被改过）：$TPL" >&2; exit 1
fi
# 用 python 做替换：路径含中文与 & 时 sed 易出错
/usr/bin/python3 - "$TPL" "$TMP" "$OLD" "$ROOT" "$HOME" "$SCOPE" <<'PY'
import re
import sys
tpl, out, old, new, home, scope = sys.argv[1:7]
s = open(tpl, encoding="utf-8").read()
s = s.replace('cd "%s"' % old, 'cd "%s"' % new)
# 日志路径按当前 HOME 修正（plist 不展开 ~）
s = s.replace("/Users/lute/Library/Logs/kb-gates", home + "/Library/Logs/kb-gates")
# HOME 环境变量按当前 HOME 修正（L0 要调 lark-cli，依赖 HOME）
s = s.replace("<string>/Users/lute</string>", "<string>%s</string>" % home)
# --outdir 用**字面量路径**，不依赖 launchd 是否继承 HOME
s = s.replace('--outdir "$HOME/Library/Logs/kb-gates"',
              '--outdir "%s/Library/Logs/kb-gates"' % home)
# scope 覆盖（仅当调用方显式给了才动；不给则**沿用模板**里那一档）
# ⚠️ 幂等：模板可能已有 `--scope full`，先归一化再按需写回，免得叠成 `--scope full --scope core`
if scope:
    if re.search(r"--scope\s+\S+", s):
        s = re.sub(r"--scope\s+\S+", "--scope %s" % scope, s)
    else:
        s = s.replace("exec /usr/bin/python3 -u ci/run_gates.py ",
                      "exec /usr/bin/python3 -u ci/run_gates.py --scope %s " % scope)
open(out, "w", encoding="utf-8").write(s)
PY
plutil -lint "$TMP" >/dev/null || { echo "❌ 生成的 plist 语法不过" >&2; exit 1; }

if [ "$OLD" != "$ROOT" ]; then
  echo "⚠️ 模板里的库根是「$OLD」，当前库根是「$ROOT」——已按当前库根生成"
fi

# ── 2b. 在飞守卫（**必须放在 bootout 之前**）─────────────────────────────────
# 并发纪律（本库硬规矩：同一条循环同一时间只准一个），外加一条实测教训：
#   `launchctl bootout` 会**杀掉正在跑的作业**。所以「先 bootout 再检查有没有在跑」
#   这个顺序是错的 —— 检查永远看不到那个刚被杀掉的进程（2026-10-04 实测踩过：
#   重装把一次跑到一半的巡检打断了）。
#   ⇒ 在飞时**整个重装都跳过**（不 bootout、不 cp、不 bootstrap、不 kickstart），
#     只等它出报告并验证。要更新 plist，请等它跑完再来一次。
INFLIGHT="$(ps -eo pid=,command= 2>/dev/null | grep -F 'run_gates.py' | grep -F "$LOGDIR" | grep -v grep | head -1 || true)"
SKIP_INSTALL=0
if [ -n "$INFLIGHT" ] && [ "$DRY_RUN" != "1" ]; then
  SKIP_INSTALL=1
  echo "⚠️ 已有一次巡检在跑，**本次不重装、不触发**（bootout 会打断它）："
  echo "   ${INFLIGHT# }" | cut -c1-200; echo
  echo "   ⇒ 只等它出报告并验证。要更新 plist，等它跑完再执行一次本脚本。"
fi

# ── 3. 安装（幂等：先踢掉旧载入，再放文件、再载入）────────────────────────────
if [ "$DRY_RUN" = "1" ]; then
  echo "（--dry-run：只生成不安装）解析出的模板库根：$OLD"
  echo "（--dry-run：将要安装到的库根）      ：$ROOT"
  echo "（--dry-run：scope 覆盖）            ：${SCOPE:-<未给，沿用模板>}"
  echo "--- 生成的 plist 关键三行 ---"
  grep -nE 'cd "|StandardOutPath|StandardErrorPath|StartCalendarInterval' "$TMP"
  echo "--- 生成件实际会用的 scope（从命令行抠出来，不是声明） ---"
  sed -n 's|.*run_gates.py \(.*\)--outdir.*|\1|p' "$TMP" | head -1 | sed 's/^/    run_gates.py /'
  cp "$TMP" "$HERE/out/com.kb.gates.generated.plist"
  echo "--- 完整件已落：ci/out/com.kb.gates.generated.plist ---"
  plutil -lint "$HERE/out/com.kb.gates.generated.plist"
  exit 0
fi

if [ "$SKIP_INSTALL" = "1" ]; then
  # 不重装：只做验证（下面的 BEFORE / 等待 / 报告读取照走）
  :
else
  launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
  cp "$TMP" "$DST"
  launchctl bootstrap "$DOMAIN" "$DST" 2>/dev/null || launchctl bootstrap "$DOMAIN" "$DST"
  echo "✅ 已装载 $LABEL ｜ 计划：每日 14:00（本机时区）"
  echo "   库根：$ROOT"
  echo "   日志：$LOGDIR/{out,err}.log ｜ 报告：$LOGDIR/gates-latest.{json,md}"
fi

if [ "$NO_RUN" = "1" ]; then
  echo "（--no-run：没有立刻跑。手动跑一次：launchctl kickstart -p $DOMAIN/$LABEL）"
  exit 0
fi

# ── 4. 立刻验证：kickstart 并等报告落盘 ───────────────────────────────────
BEFORE=0
[ -f "$LOGDIR/gates-latest.json" ] && BEFORE=$(stat -f %m "$LOGDIR/gates-latest.json")

if [ "$SKIP_INSTALL" = "1" ]; then
  echo "⏳ 等那一次巡检出报告（等待窗口 ${WAIT}s）…"
else
  launchctl kickstart -p "$DOMAIN/$LABEL" >/dev/null
  echo "⏳ 已触发一次，等报告落盘（等待窗口 ${WAIT}s）…"
fi
echo "   实测参考：空闲约 2.5 分钟；但同机若有别的会话在跑 L6（检索/体检），"
echo "   l6 一把能从 86s 涨到 311s、全量到 10 分钟以上 —— 撞上就把 --wait 放大。"

ok=0
for i in $(seq 1 $(( (WAIT + 4) / 5 ))); do
  sleep 5
  if [ -f "$LOGDIR/gates-latest.json" ]; then
    NOW=$(stat -f %m "$LOGDIR/gates-latest.json")
    [ "$NOW" -gt "$BEFORE" ] && { ok=1; break; }
  fi
done

if [ "$ok" != "1" ]; then
  echo "⚠️ 装好了，但**没验成**：等待窗口 ${WAIT}s 内没等到新报告。" >&2
  if pgrep -f 'run_gates.py' >/dev/null 2>&1; then
    echo "   实测任务**仍在跑**（run_gates.py 进程还在）—— 多半只是被别的会话拖慢了。" >&2
    echo "   稍后自己看：$LOGDIR/gates-latest.json 的 exit_code / summary" >&2
  else
    echo "   没有 run_gates.py 进程在跑 ⇒ 可能真挂了，看 $LOGDIR/err.log" >&2
  fi
  echo "   （这不是安装失败：计划任务已装载，14:00 照样会跑。）" >&2
  exit 3
fi

/usr/bin/python3 - "$LOGDIR/gates-latest.json" <<'PY'
import json, sys
d = json.load(open(sys.argv[1], encoding="utf-8"))
s = d["summary"]
print("── 安装验证：本次实测 ──────────────────────────────")
print("  时间      ：%s" % d["generated_at"])
print("  退出码    ：%s   （0 全过 ｜ 1 有红 ｜ 2 无法计算 ｜ 3 runner 故障）" % d["exit_code"])
print("  过 %d/%d ｜ 红 %s ｜ 无法计算 %s ｜ 告警 %s" % (
    len(s["passed"]), s["total"], s["red"] or "无", s["blocked"] or "无", s["warn"] or "无"))
print("────────────────────────────────────────────────────")
print("提示：launchd 非 0 退出**不会**通知你，红了要自己看上面这个文件。")
PY
echo
echo "卸载：bash ci/install-launchd.sh --uninstall"
