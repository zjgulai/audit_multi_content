#!/bin/bash
# kb_manage_install.sh —— 把 kb-manage 家族这一轮的产物落到装载位与各源目录。
#
# 为什么单独写成一个脚本：**所有写到会话工作区之外的改动都集中在这里**，
# 便于逐行审阅与一次性授权；脚本本身幂等（重复跑结果一致），且每步都打印实际动作。
#
# 范围（只有这些，别扩大）：
#   A. 8 个新成员 → ~/.dsh/skills/<id>/                （kb/l7/skills/<id>/ 是它们的源）
#   B. kb-content-review / kb-l0-feishu 的改后副本 → 装载位（源已在库内改好）
#   C. 视频安全审查 的改后副本 → 装载位 + 它的 registry source（~/Desktop/skill/内容治理中文skill/视频安全审查/）
#   D. brand-content-review-agent 的改后 SKILL.md → 装载位 + registry source + 中文工作副本
#   E. kb-retriever 停用：装载位副本移入 kb/l7/_skill-backups/
#
# 不碰：kb/l0…l6 的任何数据文件与台账；不动飞书侧；不动任何别的 skill。
set -euo pipefail

WS="/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理"
KB="$WS/kb"
SLOT="$HOME/.dsh/skills"
TS="$(date +%Y%m%d-%H%M%S)"
BK="$KB/l7/_skill-backups"

echo "=== kb_manage_install @ $TS ==="
[ -f "$KB/KB-ROOT.json" ] || { echo "FATAL: 不是库根：$KB" >&2; exit 2; }
mkdir -p "$SLOT" "$BK"

# ---- A. 8 个新成员
NEW="kb-manage kb-pipeline kb-review kb-check kb-repair kb-canonical-lookup kb-p0-check kb-recall"
for id in $NEW; do
  src="$KB/l7/skills/$id"
  [ -d "$src" ] || { echo "FATAL: 源目录不存在 $src" >&2; exit 2; }
  [ -f "$src/SKILL.md" ] || { echo "FATAL: 缺 SKILL.md：$src" >&2; exit 2; }
  if [ -d "$SLOT/$id" ]; then
    echo "[A] 已存在，先备份到 $BK/$id.bak-$TS"
    rm -rf "$BK/$id.bak-$TS"; cp -R "$SLOT/$id" "$BK/$id.bak-$TS"
  fi
  rm -rf "$SLOT/$id"
  cp -R "$src" "$SLOT/$id"
  echo "[A] $id  →  $SLOT/$id  ($(find "$SLOT/$id" -type f | wc -l | tr -d ' ') 个文件)"
done

# ---- B. 改后的 kb-content-review / kb-l0-feishu
for id in kb-content-review kb-l0-feishu; do
  src="$KB/l7/skills/$id"
  [ -f "$src/SKILL.md" ] || { echo "FATAL: 缺 $src/SKILL.md" >&2; exit 2; }
  rm -rf "$BK/$id.bak-$TS"; cp -R "$SLOT/$id" "$BK/$id.bak-$TS"
  rm -rf "$SLOT/$id"
  cp -R "$src" "$SLOT/$id"
  echo "[B] ${id}  →  $SLOT/${id} （源 = kb/l7/skills/${id}/）"
done

# ---- C. 视频安全审查（目录名 ≠ 登记 id brand-video-safety-review）
SRC_VID="$KB/l7/skills/视频安全审查"
DST_VID_WS="/Users/lute/Desktop/skill/内容治理中文skill/视频安全审查"
[ -f "$SRC_VID/SKILL.md" ] || { echo "FATAL: 缺 $SRC_VID/SKILL.md" >&2; exit 2; }
rm -rf "$BK/视频安全审查.bak-$TS"; cp -R "$SLOT/视频安全审查" "$BK/视频安全审查.bak-$TS"
cp -f "$SRC_VID/SKILL.md" "$SLOT/视频安全审查/SKILL.md"
echo "[C] 视频安全审查  →  $SLOT/视频安全审查/SKILL.md"
if [ -d "$DST_VID_WS" ]; then
  cp -f "$SRC_VID/SKILL.md" "$DST_VID_WS/SKILL.md"
  echo "[C] 视频安全审查  →  $DST_VID_WS/SKILL.md（registry source）"
else
  echo "[C][warn] registry source 目录不存在，跳过：$DST_VID_WS"
fi

# ---- D. brand-content-review-agent（**已作废，不要再写**）
# 2026-09-29 18:45 一个**并发进程**把这 13 个 brand-* 全部改名为中文名并翻译了 description
# （内容审查总控 / 文案合规审查 / …），本脚本原先"补中文入门口语"的那一步被它**取代**了。
# 为避免与并发写入者互相覆盖，这里**不再写任何 brand-* 的 SKILL.md**。
echo "[D] 跳过：brand-content-review-agent 的中文入口已由并发翻译轮次落地为「内容审查总控」，本脚本不再写它"

# ---- E. kb-retriever 停用（能力已并入 kb-recall）
if [ -d "$SLOT/kb-retriever" ]; then
  rm -rf "$BK/kb-retriever-$TS"
  mv "$SLOT/kb-retriever" "$BK/kb-retriever-$TS"
  echo "[E] kb-retriever 停用：$SLOT/kb-retriever  →  $BK/kb-retriever-$TS"
  echo "[E]   回滚：mv \"$BK/kb-retriever-$TS\" \"$SLOT/kb-retriever\""
else
  echo "[E] kb-retriever 已不在装载位，跳过"
fi

echo "=== 完成。装载位目录数：$(ls -1 "$SLOT" | wc -l | tr -d ' ') ==="
