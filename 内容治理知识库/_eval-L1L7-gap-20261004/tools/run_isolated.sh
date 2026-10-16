#!/usr/bin/env bash
# 隔离跑批驱动（**唯一**被验证有效的隔离手段，2026-10-04 实测）
#
# 为什么不能只靠 profile：
#   基线：profile 的 customSkillDirs 指到 skill 目录本身 ⇒ 根贡献 0 条 ⇒ 读源版。
#   修成父目录后：media 生效、**clause 仍读源版**（根因未完全定位，疑同名冲突的层序）。
#   ⇒ 只要隔离可能失效，评出来的就是**源版的分数**，而且**不报错**（最危险的那种错）。
#
# 本脚本的确定性手法：跑批期间把 `~/.dsh/skills/<skill>` 挪到 `.PARKED`，
#   挂载位成为**唯一**来源 ⇒ 会话必读挂载位（media / clause 均已实测 ✓）。
#
# 崩溃兜底：挪开前先把"已挪开"写进 $MARK；任何脚本启动时若发现 MARK 里的 skill
#   仍处于 PARKED 状态，**先还原再继续**（防止崩在跑批中途把服务端 skill 永久挪走）。
#
# 用法：bash tools/run_isolated.sh <skill> <tag> <cases> <outdir> [--timeout 600]
set -u
SKILL="$1"; TAG="$2"; CASES="$3"; OUT="$4"; shift 4 || true
TIMEOUT=600
while [ $# -gt 0 ]; do case "$1" in --timeout) TIMEOUT="$2"; shift 2;; *) shift;; esac; done

cd "$(dirname "$0")/.."
PROJ="$(pwd)"
MARK=""   # 逐件不同，防两件并行互相覆盖（在下面按 skill 拼）
INSTALL="$HOME/.dsh/skills/$SKILL"
PARKED="$INSTALL.PARKED"

restore_one() { # $1=skill
  local i="$HOME/.dsh/skills/$1" p="$HOME/.dsh/skills/$1.PARKED"
  if [ -e "$p" ]; then
    [ -e "$i" ] && { echo "!! 装载位与 PARKED 同时存在，需人工裁决：$i"; return 1; }
    mv "$p" "$i" && echo "[restore] $1 已还原"
  fi
}
# ── 启动即兜底：把上次崩掉留下的 PARKED 全部还原 ──────────────────────
for m in "$PROJ"/.parked-state-*; do
  [ -f "$m" ] || continue
  echo "[recover] 发现未完成的挪开记录 $m，先还原："
  while read -r s; do [ -n "$s" ] && restore_one "$s"; done < "$m"
  rm -f "$m"
done

cleanup() {
  restore_one "$SKILL"
  rm -f "$MARK"
}
trap cleanup EXIT INT TERM

MARK="$PROJ/.parked-state-$SKILL"

# ── 挪开装载位（幂等）────────────────────────────────────────────────
if [ -e "$INSTALL" ] && [ ! -e "$PARKED" ]; then
  mv "$INSTALL" "$PARKED" || { echo "!! 挪开失败"; exit 1; }
  echo "$SKILL" > "$MARK"
  echo "[park] 装载位已挪开：$INSTALL → $PARKED"
elif [ -e "$PARKED" ] && [ ! -e "$INSTALL" ]; then
  echo "$SKILL" > "$MARK"
  echo "[park] 已经是挪开状态，沿用"
else
  echo "!! 装载位状态异常（两者并存或都不在）"; exit 1
fi

# ── 跑批 ──────────────────────────────────────────────────────────────
echo "[run] $SKILL tag=$TAG cases=$CASES out=$OUT timeout=${TIMEOUT}s"
python3 tools/run_a.py --skill "$SKILL" --tag "$TAG" --cases "$CASES" \
  --out "$OUT" --shards 2 --concurrency 1 --timeout "$TIMEOUT"
rc=$?
echo "[run] run_a exit=$rc"
exit $rc
