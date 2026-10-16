#!/bin/bash
# 安装「中文斜杠调用名」补丁 dsh-chinese-skill-patch。
# 先检查是否已安装，已安装则跳过，不用重复安装（幂等）。
# 优先从 npm 安装；npm 不可达时才退回本包 vendor/ 里的离线副本。
# 装完后必须完全退出并重新打开 DSH Desktop，再新开会话输入 /视频安全审查
set -uo pipefail

PKG="dsh-chinese-skill-patch"
HERE="$(cd "$(dirname "$0")" && pwd)"
VENDOR="${HERE}/vendor/${PKG}"

# --- 找到 dsh CLI：PATH → 本机已知落点 → DSH Desktop 自带 CLI 目录 ---
find_dsh() {
  if command -v dsh >/dev/null 2>&1; then command -v dsh; return 0; fi
  local c
  for c in "${HOME}/.dsh/profiles/node_modules/.bin/dsh" "${HOME}/Library/pnpm/dsh"; do
    if [ -x "${c}" ]; then echo "${c}"; return 0; fi
  done
  c=$(ls -d "${HOME}/Library/Application Support/DSH Desktop/cli"/*/bin/dsh 2>/dev/null | head -1)
  if [ -n "${c}" ] && [ -x "${c}" ]; then echo "${c}"; return 0; fi
  return 1
}

export PATH="${HOME}/Library/pnpm/bin:${HOME}/Library/Application Support/DSH Desktop/runtime-commands/bin:/usr/local/bin:/opt/homebrew/bin:${PATH}"

DSH_BIN="$(find_dsh || true)"
if [ -z "${DSH_BIN}" ]; then
  echo "未找到 dsh 命令。"
  echo "请先安装并打开一次 DSH Desktop，或执行：npm install -g @deepseek-ai/dsh"
  read -r -p "按回车关闭…" _
  exit 1
fi
echo "使用 CLI：${DSH_BIN}"
echo "安装来源：npm ${PKG}（npm 不可达时退回 ${VENDOR}）"
echo

is_npm_install() {
  python3 -c "
import json, sys
p = json.load(open(sys.argv[1]))
d = p.get('dependencies') or {}
spec = str(d.get('dsh-chinese-skill-patch') or '')
npm = bool(spec) and not spec.startswith(('link:', 'file:', '/'))
sys.exit(0 if npm else 1)
" "$1"
}

installed=0
skipped=0
failed=0
for profile in desktop web; do
  PJ="${HOME}/.dsh/profiles/${profile}/package.json"
  if [ ! -f "${PJ}" ]; then
    echo "跳过 ${profile}（本机没有这个 profile）"
    continue
  fi
  if is_npm_install "${PJ}"; then
    echo "跳过 ${profile}（已安装 ${PKG}，已安装则跳过）"
    skipped=$((skipped + 1))
    echo
    continue
  fi
  echo "正在从 npm 安装到 profile：${profile}"
  if "${DSH_BIN}" plugin --profile "${profile}" add "${PKG}"; then
    echo "✓ ${profile} 已从 npm 安装 ${PKG}"
    installed=$((installed + 1))
  elif [ -d "${VENDOR}" ]; then
    echo "npm 不可达，退回本地离线副本：${VENDOR}"
    if "${DSH_BIN}" plugin --profile "${profile}" add "${VENDOR}"; then
      echo "✓ ${profile} 已从本地离线副本安装 ${PKG}"
      installed=$((installed + 1))
    else
      echo "✗ ${profile} 安装失败（npm 与本地副本都没成功）"
      failed=$((failed + 1))
    fi
  else
    echo "✗ ${profile} 安装失败（npm 不可达，且没有 ${VENDOR}）"
    failed=$((failed + 1))
  fi
  echo
done

if [ "${installed}" -eq 0 ] && [ "${skipped}" -eq 0 ]; then
  echo "没有成功写入任何 profile。请确认已至少打开过一次 DSH Desktop。"
  read -r -p "按回车关闭…" _
  exit 1
fi

echo "----------------------------------------"
if [ "${skipped}" -gt 0 ]; then echo "有 ${skipped} 个 profile 已安装，已跳过（不重复安装）。"; fi
echo "补丁新写入 ${installed} 个 profile。"
if [ "${failed}" -gt 0 ]; then echo "有 ${failed} 个 profile 失败，可把上面的报错发给管理员。"; fi
echo
echo "接下来请务必："
echo "  1. 完全退出 DSH Desktop（不是只关窗口）"
echo "  2. 重新打开 DSH Desktop"
echo "  3. 新开一个会话，输入：/视频安全审查"
echo "----------------------------------------"
read -r -p "按回车关闭…" _
exit 0
