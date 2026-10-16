#!/usr/bin/env bash
# 隔离跑批驱动 v2（2026-10-04）
#
# 与 v1 的差别（v1 有两个 bug，别再回去用 v1）：
#  ① v1 启动时扫**所有** `.parked-state-*` 并逐个还原 —— 两件并行时，
#     后启动的那件会把**正在跑**的那件的装载位还回去（差点发生）。
#     v2 只认**本 skill 自己**的挪开记录，绝不碰别人的。
#  ② v1 被 python 写过，bash 读到坏字节（`m�: unbound variable`）。v2 是纯文本落盘。
#
# 为什么要挪开装载位（这是**唯一**被实测有效的隔离手段）：
#   `customSkillDirs` 修正为父目录后，媒体件生效、**clause 仍读源版**
#   （根因未完全定位，疑同名冲突的层序）。只要隔离可能失效，
#   评出来的就是**源版**分数，而且**不报错** —— 最危险的那种错。
#   实测：把 `~/.dsh/skills/<skill>` 挪到 `.PARKED` 后，会话必读挂载位（media / clause 均 ✓）。
#
# 用法：bash tools/run_isolated_v2.sh <skill> <tag> <cases> <outdir> [--timeout 600]
set -u
SKILL="$1"; TAG="$2"; CASES="$3"; OUT="$4"; shift 4 || true
TIMEOUT=600
while [ $# -gt 0 ]; do
  case "$1" in
    --timeout) TIMEOUT="$2"; shift 2 ;;
    *) shift ;;
  esac
done

cd "$(dirname "$0")/.."
PROJ="$(pwd)"
INSTALL="$HOME/.dsh/skills/$SKILL"
PARKED="$INSTALL.PARKED"
MARK="$PROJ/.parked-state-$SKILL"

restore_self() {
  if [ -e "$PARKED" ]; then
    if [ -e "$INSTALL" ]; then
      echo "!! 装载位与 PARKED 同时存在，需人工裁决：$INSTALL"
      return 1
    fi
    mv "$PARKED" "$INSTALL" && echo "[restore] $SKILL 已还原"
  fi
  rm -f "$MARK"
}
trap restore_self EXIT INT TERM

# ── 只兜底**本 skill**：上次崩在跑批中途，装载位可能还挂着 ──────────────
if [ -e "$PARKED" ] && [ ! -e "$INSTALL" ]; then
  echo "[recover] 发现本 skill 上次未还原，先还原再重新挪开"
  restore_self
fi

# ── 挪开装载位（幂等）──────────────────────────────────────────────────
if [ -e "$INSTALL" ] && [ ! -e "$PARKED" ]; then
  mv "$INSTALL" "$PARKED" || { echo "!! 挪开失败"; exit 1; }
  echo "$SKILL" > "$MARK"
  echo "[park] $INSTALL → $PARKED"
else
  echo "!! 装载位状态异常（在位=$([ -e "$INSTALL" ] && echo Y || echo N) PARKED=$([ -e "$PARKED" ] && echo Y || echo N)）"
  exit 1
fi

echo "[run] $SKILL tag=$TAG cases=$CASES out=$OUT timeout=${TIMEOUT}s"
python3 tools/run_a.py --skill "$SKILL" --tag "$TAG" --cases "$CASES" \
  --out "$OUT" --shards 2 --concurrency 1 --timeout "$TIMEOUT"
rc=$?
echo "[run] run_a exit=$rc"
exit $rc
