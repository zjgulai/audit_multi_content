#!/usr/bin/env bash
# 隔离跑批驱动 v3（2026-10-04）—— **v1 / v2 都别再用了**
#
# v1 的 bug：启动时还原**所有** `.parked-state-*`（并行时会把正在跑的那件还回去）。
# v2 的 bug：★ park 落点在 `~/.dsh/skills/<skill>.PARKED` —— **还在被扫描的根里面**！
#            加载器扫 `<root>/*/SKILL.md`，`.PARKED` 目录照样算一个 skill，
#            条目名取自 frontmatter 的 `name`（仍是 `<skill>`）⇒ park 没把它移出扫描范围。
#            实测：clausefix 那轮 park 显示生效（在位=N PARKED=Y），
#            但会话渲染出来**仍是源版**，整轮 159 条再次作废。
# v2/v3 初版共同踩的坑：**未加花括号的 `$VAR` 紧跟多字节字符**（如 `$PARKED）`），
#            本机 locale 下 bash 会把多字节字符首字节吞进变量名 ⇒ `unbound variable` 当场崩。
#            ⇒ 本文件**所有**变量展开一律写 `${VAR}`。
#
# v3 的确定性手法：把装载位挪到**任何被扫描的根之外** —— `~/.dsh/_parked-skills/<skill>`。
#   被扫描的根（dsh-skill-filesystem/lib/index.js:roots）：
#     <projectRoot>/.dsh/skills(100) / <projectRoot>/.agents/skills(200) /
#     customSkillDirs(300) / ~/.dsh/skills(400) / ~/.agents/skills(500) / bundled
#   `~/.dsh/_parked-skills` 不在其中 ⇒ user-dsh 里这个名字彻底不存在 ⇒ 挂载位必被读到。
#
# 用法：bash tools/run_isolated_v3.sh <skill> <tag> <cases> <outdir> [--timeout 600]
set -u
SKILL="$1"
TAG="$2"
CASES="$3"
OUT="$4"
shift 4 || true
TIMEOUT=600
while [ $# -gt 0 ]; do
  case "$1" in
    --timeout) TIMEOUT="$2"; shift 2 ;;
    *) shift ;;
  esac
done

cd "$(dirname "$0")/.."
PROJ="$(pwd)"
INSTALL="${HOME}/.dsh/skills/${SKILL}"
INROOT_PARKED="${INSTALL}.PARKED"
PARKDIR="${HOME}/.dsh/_parked-skills"
PARKED="${PARKDIR}/${SKILL}"
MARK="${PROJ}/.parked-state-${SKILL}"

restore_self() {
  if [ -e "${PARKED}" ]; then
    if [ -e "${INSTALL}" ]; then
      echo "!! 装载位与 park 副本同时存在，需人工裁决：${INSTALL} / ${PARKED}"
      return 1
    fi
    mkdir -p "$(dirname "${INSTALL}")"
    mv "${PARKED}" "${INSTALL}" && echo "[restore] ${SKILL} 已还原"
  fi
  rm -f "${MARK}"
}
trap restore_self EXIT INT TERM

# ── 清掉 v2 留下的"根内 park"隐患：它会被继续当 skill 扫到 ────────────────
if [ -e "${INROOT_PARKED}" ] && [ ! -e "${INSTALL}" ]; then
  echo "[fix] 发现根内 park（${INROOT_PARKED}）—— 会被当 skill 扫到，先回位"
  mv "${INROOT_PARKED}" "${INSTALL}"
fi
# ── 只兜底本 skill ────────────────────────────────────────────────────────
if [ -e "${PARKED}" ] && [ ! -e "${INSTALL}" ]; then
  echo "[recover] 本 skill 上次未还原，先还原再重新挪开"
  restore_self
fi

# ── 挪到扫描根之外（幂等）────────────────────────────────────────────────
mkdir -p "${PARKDIR}"
if [ -e "${INSTALL}" ] && [ ! -e "${PARKED}" ]; then
  mv "${INSTALL}" "${PARKED}" || { echo "!! 挪开失败"; exit 1; }
  echo "${SKILL}" > "${MARK}"
  echo "[park] ${INSTALL} → ${PARKED}（已在一切被扫描的根之外）"
else
  echo "!! 装载位状态异常（在位=$([ -e "${INSTALL}" ] && echo Y || echo N) park=$([ -e "${PARKED}" ] && echo Y || echo N)）"
  exit 1
fi

# ── 开跑前**强制**自证：渲染出来的必须是挂载位那一份 ──────────────────────
echo "[preflight] 核验隔离（读源版即拒跑）"
if ! python3 tools/verify_isolation.py --skill "${SKILL}" --tag "${TAG}"; then
  echo "!! 隔离核验未过 —— **拒跑**（不跑，好过再白跑一轮）"
  exit 1
fi

echo "[run] ${SKILL} tag=${TAG} cases=${CASES} out=${OUT} timeout=${TIMEOUT}s"
python3 tools/run_a.py --skill "${SKILL}" --tag "${TAG}" --cases "${CASES}" \
  --out "${OUT}" --shards 2 --concurrency 1 --timeout "${TIMEOUT}"
rc=$?
echo "[run] run_a exit=${rc}"
exit ${rc}
