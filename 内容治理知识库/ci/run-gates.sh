#!/bin/bash
# run-gates.sh —— KB 闸门在**任意 CI / 调度器**上的单一入口（平台无关）
#
# 为什么要有它（而不是让各平台直接调 `python3 ci/run_gates.py`）：
#   1. **前提自检**：CI 上第一件咬人的事是「库根不在 / 不是权威库根 / 缺 kbpy」——
#      这三样缺任何一样，后面每一把闸门都会报成一个看起来像**数据错**的假红。
#      本脚本先判掉，并给一句人话错因。
#   2. **解释器选择**：闸门约定 `/usr/bin/python3`（见 `kb/.kb-python`，L6 召回需要
#      numpy + fastembed，受管 python 没有）。CI 上 PATH 里的 `python3` 可能是别的。
#      但本 runner 自身只用标准库，所以这里按「有 /usr/bin/python3 就用它」的次序取。
#   3. **一份出口**：Jenkins / 内网自研 / cron / 任何 shell 都能调同一个入口，
#      退出码语义与 `run_gates.py` 完全一致（不另造一套）。
#
# 退出码（与 ci/run_gates.py 同源，**不重新定义**）：
#   0 全过 ｜ 1 有红 ｜ 2 有「无法计算」｜ 3 runner 故障 / 非 blocking 闸门自身报错
#   另有 90 = 本脚本自己判出的「前提不满足」，**故意与上面四档分开**，
#   免得 CI 把「环境没配好」误读成「库里有红」。
#
# 范围（scope）：默认 **full**（12 把 + projection + envelope）。
#   ⚠️ full 下**预期就是红的**：`l0`（取数身份坏）与 `projection`（实测真坏 3/6）都是真红，
#      两件的修法都是**人做**的动作、CI 修不了（见 ci/README.md §6 与 接线手札 §2）。
#      想先要一条绿基线：`KB_GATES_SCOPE=core` 或 `--core`。
#
# 用法：
#   bash ci/run-gates.sh                          # 默认 scope=full，报告落 ci/out
#   bash ci/run-gates.sh --core                   # 只跑 12 把（与现有 launchd 一致）
#   bash ci/run-gates.sh --only l0 projection     # 调试用：只跑其中几把
#   bash ci/run-gates.sh --outdir "$WORKSPACE/ci-out"
#   bash ci/run-gates.sh --strict-warn            # 发布前门禁：告警也算失败
#   KB_GATES_SCOPE=core bash ci/run-gates.sh
#
# 环境变量：KB_GATES_SCOPE（core/full）｜KB_GATES_OUTDIR ｜KB_GATES_TIMEOUT
#           ｜KB_GATES_STRICT_WARN（true/false）｜KB_PYTHON（指定解释器）
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"          # 库根（含 kb/KB-ROOT.json 的那一层）

SCOPE="${KB_GATES_SCOPE:-full}"
OUTDIR="${KB_GATES_OUTDIR:-$ROOT/ci/out}"
TIMEOUT="${KB_GATES_TIMEOUT:-600}"
STRICT="${KB_GATES_STRICT_WARN:-false}"
ONLY=()

while [ $# -gt 0 ]; do
  case "$1" in
    --scope)  SCOPE="${2:-}"; shift 2 ;;
    --core)   SCOPE=core; shift ;;
    --full)   SCOPE=full; shift ;;
    --outdir) OUTDIR="${2:-}"; shift 2 ;;
    --timeout) TIMEOUT="${2:-}"; shift 2 ;;
    --only)   shift; ONLY=(); while [ $# -gt 0 ] && [ "${1#--}" = "$1" ]; do ONLY+=("$1"); shift; done ;;
    --strict-warn) STRICT=true; shift ;;
    # 帮助：打印本文件头注释（从第 2 行到 `set -uo pipefail` 之前），别写死行号 —— 头注释会变长
    -h|--help) awk 'NR>1 && /^set -uo pipefail/ {exit} NR>1 {print}' "$0"; exit 0 ;;
    *) echo "run-gates.sh: 未知参数：$1" >&2; exit 2 ;;
  esac
done

case "$SCOPE" in core|full) ;; *) echo "run-gates.sh: scope 只能是 core 或 full，收到「${SCOPE}」" >&2; exit 2 ;; esac

echo "========================================================================"
echo "KB 闸门 ｜ 平台无关入口 run-gates.sh"
echo "  库根    ：$ROOT"
echo "  范围    ：scope=$SCOPE"
echo "  报告落点：$OUTDIR"
echo "  主机    ：$(hostname 2>/dev/null || echo '?') ｜ 时间 $(date '+%Y-%m-%d %H:%M:%S %Z')"
echo "========================================================================"

# ── 0. 前提自检（缺一样 ⇒ 退出码 90，与四档闸门退出码分开）──────────────────
fail=0
[ -f "$ROOT/kb/KB-ROOT.json" ] || { echo "❌ $ROOT 不是权威库根（缺 kb/KB-ROOT.json）" >&2; fail=1; }
[ -x "$ROOT/kb/kbpy" ]         || { echo "❌ 缺可执行的 kb/kbpy（库内解释器入口）" >&2; fail=1; }
[ -f "$ROOT/ci/run_gates.py" ] || { echo "❌ 缺 $ROOT/ci/run_gates.py" >&2; fail=1; }
if [ "$fail" != 0 ]; then
  echo "   ⇒ 这三样是闸门读活库的前提。**云端托管 runner 上不会有**——闸门必须在" >&2
  echo "     装有这份活库的那台机器上跑（self-hosted runner），见 ci/README.md §4.1。" >&2
  exit 90
fi

# 解释器：优先库内约定的 /usr/bin/python3（只用标准库，但保持一致省得两套口径）
if [ -n "${KB_PYTHON:-}" ]; then PY="$KB_PYTHON"
elif [ -x /usr/bin/python3 ]; then PY=/usr/bin/python3
else PY="$(command -v python3 || true)"; fi
if [ -z "$PY" ] || ! "$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 6) else 1)' 2>/dev/null; then
  echo "❌ 找不到可用的 python3（可用 KB_PYTHON 指定）" >&2; exit 90
fi
# ⚠️ 本文件里**变量后紧跟中文全角标点时必须写 `${VAR}`**：
#    实测 `echo "$PY（…"` 在 UTF-8 locale 下被 bash 解析成变量名 `PY：` ⇒
#    `PY：: unbound variable`（`set -u` 下直接挂掉）。下面一律用花括号。
echo "解释器：${PY}（$("$PY" -V 2>&1)）"

# 在飞提示（**不拦**）：闸门只读、不抢 kb/.work/.kb.lock，可与写档循环并存；
# 但同机跑 L6 会把 l6 这一把从 86s 拖到 300s+。提示一句，免得把「慢」当「挂」。
if pgrep -f 'run_gates.py' >/dev/null 2>&1; then
  echo "⚠️ 已有别的 run_gates.py 在跑：本次会与其**抢 I/O**（l6 那一把可能慢 3–4 倍）。"
fi

# ── 1. 跑（退出码**原样透传**，不在这里重新解释）────────────────────────────
FLAGS=(--scope "$SCOPE" --outdir "$OUTDIR" --timeout "$TIMEOUT")
if [ "${#ONLY[@]}" -gt 0 ]; then FLAGS+=(--only "${ONLY[@]}"); fi
if [ "$STRICT" = "true" ]; then FLAGS+=(--strict-warn); fi
mkdir -p "$OUTDIR"

"$PY" "$ROOT/ci/run_gates.py" "${FLAGS[@]}"
RC=$?

echo
echo "------------------------------------------------------------------------"
echo "闸门退出码：$RC  ｜ 报告："
echo "  $OUTDIR/gates-latest.json"
echo "  $OUTDIR/gates-latest.md"
if [ "$RC" != 0 ]; then
  echo "★ 红/无法计算时**别只看这一个数字**：先看报告里 red 列表，再对照 ci/README.md §6 的成因与处置。"
  echo "  已知的两条真红均为**人做**的动作，CI 改不动："
  echo "    · l0         —— 取数身份（bot「守衡」未加成该 Base 可阅读协作者／user 令牌失效）"
  echo "    · projection —— 投影漂移（实测 6 项过 3），需确认投影生成器是否从规则行读那 4 个字段"
fi
exit $RC
