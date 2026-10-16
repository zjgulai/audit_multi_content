#!/usr/bin/env bash
# 确定性隔离 v4：**跑批期间把修复版覆盖到源版位置**（2026-10-04）
#
# 为什么放弃 v3（"把源版挪到根外"）：
#   实测装载位已挪到一切被扫描根之外，**仍有部分轮次解析到源版**
#   （media：a 片对 / b 片错；clause：4 片对 / 2 片错）。
#   即"哪个根赢"**按进程各自裁决**，前置探一条**不足以**保证整轮。
#
# v4 绕开"谁赢"这个问题：**让所有副本内容一致**。
#   把 fix/ 的内容**覆盖**到 ①`~/.dsh/skills/<skill>` ②真源 `kb/l7/skills/<skill>`，
#   原版整目录**移走备份**、退出/崩溃时还原。
#   ⇒ 无论加载器解析到哪个根，读到的都是修复版 ⇒ **按构造确定**，不再依赖裁决顺序。
#   （挂载位本就是 fix 的副本，三处内容一致。）
#
# 崩溃兜底：备份目录存在即视为"未还原"，下次启动先还原。
#
# 用法：bash tools/run_swapfix.sh <skill> <tag> <cases> <outdir> [--timeout 600]
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
BACKUP="${PROJ}/_swap-backup/${SKILL}"
INSTALL="${HOME}/.dsh/skills/${SKILL}"
SOURCE="${KBROOT}/kb/l7/skills/${SKILL}"

restore() {
  for pair in "install:${INSTALL}" "source:${SOURCE}"; do
    name="${pair%%:*}"
    live="${pair#*:}"
    bak="${BACKUP}/${name}"
    if [ -e "${bak}" ]; then
      rm -rf "${live}"
      mkdir -p "$(dirname "${live}")"
      mv "${bak}" "${live}" && echo "[restore] ${name} 已还原"
    fi
  done
  rmdir "${BACKUP}" 2>/dev/null && rmdir "$(dirname "${BACKUP}")" 2>/dev/null
}
trap restore EXIT INT TERM

# ── 崩溃兜底：上次没还原就补还原 ──────────────────────────────────────────
if [ -d "${BACKUP}" ]; then
  echo "[recover] 发现未还原的备份，先还原"
  restore
fi

# ── 覆盖：原版移走备份，fix 覆盖上去 ──────────────────────────────────────
mkdir -p "${BACKUP}"
for pair in "install:${INSTALL}" "source:${SOURCE}"; do
  name="${pair%%:*}"; live="${pair#*:}"
  [ -e "${live}" ] || { echo "!! 缺 ${live}，中止（不动任何东西）"; exit 1; }
  mv "${live}" "${BACKUP}/${name}"
done
for pair in "install:${INSTALL}" "source:${SOURCE}"; do
  name="${pair%%:*}"; live="${pair#*:}"
  cp -R "${FIX}" "${live}"
done
echo "[swap] fix → install + 真源（原版已备份到 ${BACKUP}）"
for pair in "install:${INSTALL}" "source:${SOURCE}"; do
  live="${pair#*:}"
  printf "  %-58s %s\n" "${live}" "$(grep -m1 '^version:' "${live}/SKILL.md" | tr -d ' ')"
done

# ── 自证：三处 description 必须一致 ──────────────────────────────────────
python3 - "${FIX}" "${INSTALL}" "${SOURCE}" "${PROJ}/mounts/${TAG}/${SKILL}" <<'PY'
import re,sys,yaml
def d(p):
    t=open(p+'/SKILL.md',encoding='utf-8').read()
    m=re.match(r'^---\n(.*?)\n---\n',t,re.S)
    return ' '.join(str(yaml.safe_load(m.group(1)).get('description','')).split())
vals=[d(p) for p in sys.argv[1:]]
print(f"[selfcheck] 四处 description 折叠字数: {[len(v) for v in vals]}")
if len(set(vals))!=1:
    print("❌ 不一致 —— **拒跑**"); sys.exit(1)
print("✅ 四处内容一致 ⇒ 无论加载器解析到哪个根，读到的都是修复版")
PY
[ $? -ne 0 ] && exit 1

# ── 跑批 ─────────────────────────────────────────────────────────────────
rm -rf "${OUT}"
echo "[run] ${SKILL} tag=${TAG} out=${OUT}"
python3 tools/run_a.py --skill "${SKILL}" --tag "${TAG}" --cases "${CASES}" \
  --out "${OUT}" --shards 2 --concurrency 1 --timeout "${TIMEOUT}"
rc=$?
echo "[run] run_a exit=${rc}"
exit ${rc}
