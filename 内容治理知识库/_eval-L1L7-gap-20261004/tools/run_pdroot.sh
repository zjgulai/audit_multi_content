#!/usr/bin/env bash
# 隔离跑批驱动 v5（**最终采用**，2026-10-04）
#
# 手法：把修复版放到 **project-dsh 根**（rank 100，roots() 里最强的一档）
#   = `<projectRoot>/.dsh/skills/<skill>`，projectRoot 由会话 cwd 推得（跑批 cwd 在 /tmp 侧）
#   ⇒ 稳赢 custom(300) 与 user-dsh(400)。
#
# ★ 本手法**不碰** `~/.dsh/skills`、**不碰**真源 `kb/l7/skills` ——
#   只在 `/private/tmp` 与跑批 work-root 下放东西。
#   （v4「把 fix 覆盖到装载位与真源」已弃用：那会动到 @守衡 工作流实际调用的位置。）
#
# 实测：3 个独立探针全部渲染 491 字（修复版），装载位/真源仍为原版 1.1.0 未动。
#
# 流程：放 → **跑前自证** → 跑 → **逐片复核**（六片全绿才算数）→ 清 /tmp 侧。
#
# 用法：bash tools/run_pdroot.sh <skill> <tag> <cases> <outdir> [--timeout 600]
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
KBROOT="$(dirname "${PROJ}")"
FIX="${PROJ}/fix/${SKILL}"
PD="/private/tmp/.dsh/skills"
WORK="/tmp/kb-l1l7-blind-${TAG}"

# ── 硬断言：装载位与真源必须是**原版**（本手法不该动它们）────────────────
for live in "${HOME}/.dsh/skills/${SKILL}" "${KBROOT}/kb/l7/skills/${SKILL}"; do
  if [ ! -d "${live}" ]; then
    echo "!! 缺 ${live} —— 中止（不动任何东西）"; exit 1
  fi
done
echo "[guard] 装载位版本 $(grep -m1 '^version:' "${HOME}/.dsh/skills/${SKILL}/SKILL.md" | tr -d ' ')"
echo "[guard] 真源版本   $(grep -m1 '^version:' "${KBROOT}/kb/l7/skills/${SKILL}/SKILL.md" | tr -d ' ')"
echo "[guard] fix 版本    $(grep -m1 '^version:' "${FIX}/SKILL.md" | tr -d ' ')"

# ── 放修复版到 project-dsh 根（两处候选位置都放，覆盖各种 projectRoot 推断）──
mkdir -p "${PD}" "${WORK}/.dsh/skills" "${WORK}/.git"
rm -rf "${PD}/${SKILL}" "${WORK}/.dsh/skills/${SKILL}"
cp -R "${FIX}" "${PD}/${SKILL}"
cp -R "${FIX}" "${WORK}/.dsh/skills/${SKILL}"
echo "[pdroot] 已在 ${PD}/${SKILL} 与 ${WORK}/.dsh/skills/${SKILL} 放入修复版"

# ── 跑前自证（探一条）────────────────────────────────────────────────────
if ! python3 tools/verify_isolation.py --skill "${SKILL}" --tag "${TAG}"; then
  echo "!! 跑前自证未过 —— 拒跑"; exit 1
fi

# ── 跑批 ─────────────────────────────────────────────────────────────────
rm -rf "${OUT}"
echo "[run] ${SKILL} tag=${TAG} out=${OUT} timeout=${TIMEOUT}s"
python3 tools/run_a.py --skill "${SKILL}" --tag "${TAG}" --cases "${CASES}" \
  --out "${OUT}" --shards 2 --concurrency 1 --timeout "${TIMEOUT}"
rc=$?
echo "[run] run_a exit=${rc}"

# ── 逐片复核（**六片全绿才算数**）────────────────────────────────────────
echo
python3 tools/verify_shards.py --skill "${SKILL}" --run-dir "${OUT}"
vrc=$?

# ── 清 /tmp 侧（只清本项目放的那两处）────────────────────────────────────
rm -rf "${PD}/${SKILL}" "${WORK}/.dsh/skills/${SKILL}"
echo "[clean] 已清 /tmp 侧投放点"
[ -d /private/tmp/.dsh/skills ] && [ -z "$(ls -A /private/tmp/.dsh/skills 2>/dev/null)" ] && rmdir /private/tmp/.dsh/skills 2>/dev/null

if [ ${vrc} -ne 0 ]; then
  echo "★ 结论：**隔离复核未过 ⇒ 数据作废**（跑批本身 exit=${rc}）"
  exit 1
fi
echo "★ 结论：六片全绿 ⇒ **本轮数据可信**（跑批 exit=${rc}）"
exit ${rc}
