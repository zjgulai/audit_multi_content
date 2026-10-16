#!/usr/bin/env bash
# kb-l0-feishu · 阶段 0 前置自检
#
# 用法:
#   bash scripts/preflight.sh              # 默认 bot 身份自检
#   PREFLIGHT_AS=user bash scripts/preflight.sh
#
# 退出码:
#   0 = 全部通过，可以继续
#   1 = 有 BLOCKER，停下并报告"缺什么"，不要绕路硬试
#
# 设计意图：把"认证/授权乱试 2 小时"压缩成一次 30 秒的判定。

set -uo pipefail

AS="${PREFLIGHT_AS:-bot}"
PROFILE="${L8_PROFILE:-dsh-kb}"
BASE_TOKEN="${KB_BASE_TOKEN:-GnRZbIuXraCzf0sGr2UcmZ62nfc}"
TABLE_ID="${KB_TABLE_ID:-tblMGtPfe8ZUsEdP}"

BLOCKERS=0
WARNINGS=0
ADVISORY=0      # 建议级：某身份对某 Base 不成、但另一身份成 → 按矩阵选身份即可，**不算阻断**

ok()   { printf '  [ OK ]   %s\n' "$*"; }
warn() { printf '  [WARN]   %s\n' "$*"; WARNINGS=$((WARNINGS+1)); }
bad()  { printf '  [BLOCK]  %s\n' "$*"; BLOCKERS=$((BLOCKERS+1)); }
advise() { printf '  [ADVISE] %s\n' "$*"; ADVISORY=$((ADVISORY+1)); }

echo "== kb-l0-feishu 阶段 0 前置自检 =="
echo "身份=$AS   profile=$PROFILE"
echo

# ---- 1. 库根 ----------------------------------------------------------------
echo "[1/6] 库根定位"
KB="${KB_ROOT:-}"
if [ -z "$KB" ]; then
  for cand in "$HOME/.dsh/Momcozy知识库/kb" "$HOME/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理/kb"; do
    if [ -d "$cand/l8" ]; then KB="$(cd "$cand" && pwd -P)"; break; fi
  done
fi
if [ -z "$KB" ] || [ ! -d "$KB/l8" ]; then
  bad "找不到库根（缺 kb/l8）。请设 KB_ROOT=<库根绝对路径>"
else
  ok "库根: $KB"
  echo "         l8 脚本数: $(ls "$KB"/l8/*.py 2>/dev/null | wc -l | tr -d ' ')"
fi
echo

# ---- 2. 锁与并发 ------------------------------------------------------------
echo "[2/6] 并发锁检查"
if [ -n "$KB" ] && [ -e "$KB/.kb.lock" ]; then
  bad "存在 $KB/.kb.lock —— 可能有另一批在跑，先确认再动"
elif [ -n "$KB" ] && [ -d "$KB/.work" ]; then
  recent="$(find "$KB/.work" -type f -newermt '-30 minutes' 2>/dev/null | wc -l | tr -d ' ')"
  if [ "$recent" -gt 0 ]; then
    warn ".work 近 30 分钟有 $recent 个文件写入，确认是否另一批在跑"
  else
    ok ".work 近 30 分钟无写入"
  fi
else
  ok "未发现锁"
fi
echo

# ---- 3. lark-cli ------------------------------------------------------------
echo "[3/6] lark-cli"
export PATH="$HOME/.dsh/bin:$PATH"
LARK="$(command -v lark-cli || true)"
if [ -z "$LARK" ]; then
  bad "lark-cli 不在 PATH（应位于 ~/.dsh/bin/lark-cli）"
else
  ok "lark-cli: $LARK"
  status_out="$(lark-cli auth status --profile "$PROFILE" 2>&1 || true)"
  if printf '%s' "$status_out" | grep -qiE 'ready|valid|ok'; then
    ok "$AS 身份可用"
  else
    if [ "$AS" = "user" ]; then
      bad "$AS 身份不可用 —— 发一条设备码（只放缺的那个 scope，一次只发一条）"
      printf '%s\n' "$status_out" | sed 's/^/         /' | head -8
    else
      warn "$AS 身份状态无法确认，下面用真实读取复核"
      printf '%s\n' "$status_out" | sed 's/^/         /' | head -5
    fi
  fi
fi
echo

# ---- 4. 真实读取复核：跨表跨 Base 抽样 + 能力矩阵 -----------------------------
# 2026-09-30 改：原先只探「材料收集」一张表，就出结论"bot 能读 → 记录层/结构层直接用 bot"。
# 实测 bot 对第 2 个 Base 的「专家修订汇总表」「内容公式（仅供参考）」读不到 +field-list，
# 那个结论被外推后，align_l0_schema.py --apply 把两张表的快照刷成了 0 字段。
# 现在按 **每个 Base 至少一张表** 抽样，逐 Base 给结论；结构层另有 field-list 复核。
echo "[4/6] 真实读取复核（跨表跨 Base 抽样 → 能力矩阵）"
if [ -z "${LARK:-}" ]; then
  bad "跳过：lark-cli 不可用"
else
  # 抽样表：入口 Base 2 张 + 第 2 个 Base 1 张（覆盖 wiki 侧 Base，那里 bot 会失手）
  SAMPLE_TABLES="${KB_SAMPLE_TABLES:-$BASE_TOKEN:$TABLE_ID GnRZbIuXraCzf0sGr2UcmZ62nfc:tbld8qE92YaY38Yz SKkkbdZi9aRuMzs7ob0cpSYHnQg:tbl8AI00JZO1iZtp}"
  # 两个身份都探：结论不是"能不能读"，而是"该用哪个身份"（2026-09-30：bot 对第 2 Base 不成、user 成）
  for idn in bot user; do
    echo "  ── 身份 ${idn}"
    for pair in $SAMPLE_TABLES; do
      b="${pair%%:*}"; t="${pair##*:}"
      out="$(lark-cli base +record-list --base-token "${b}" --table-id "${t}" \
             --page-size 1 --as "${idn}" --profile "${PROFILE}" 2>&1 || true)"
      if printf '%s' "${out}" | grep -qE 'record_id|records'; then
        ok "记录可读  base=${b} table=${t}"
      elif printf '%s' "${out}" | grep -qE '91403|1063002|40403|DENY|forbidden'; then
        advise "该身份记录 ACL 拒  base=${b} table=${t}（换身份再试，两身份都拒才算阻断）"
      elif printf '%s' "${out}" | grep -qiE 'token.*(expired|missing)|unauthorized|401'; then
        warn "登录态未就绪  base=${b} table=${t}（不是权限；发一条设备码，一次只发一条）"
      else
        warn "返回未识别  base=${b} table=${t}"
        printf '%s\n' "${out}" | sed 's/^/         /' | head -4
      fi
      fout="$(lark-cli base +field-list --base-token "${b}" --table-id "${t}" \
              --as "${idn}" --profile "${PROFILE}" --json 2>&1 || true)"
      if printf '%s' "${fout}" | grep -qE '"fields"|field_id'; then
        ok "字段可读  base=${b} table=${t}"
      else
        advise "该身份字段拒读  base=${b} table=${t}  ← 结构层核对该 Base 换身份"
      fi
    done
  done
  echo "  ── 能力矩阵结论（照这个选身份，别把一张表的结论外推到全部）"
  echo "     · 记录可读但字段拒读 → 该 Base 的结构层核对换另一个身份（实测：第 2 个 Base 用 user）"
  echo "     · 两个身份都拒读      → 才是资源级 ACL：要所有者在【守衡】上加可阅读协作者"
  echo "     · 字段读失败时，脚本必须拒写快照（宁红不写 0 字段快照）—— SKILL.md §3.1"
fi
echo

# ---- 5. python 依赖 ---------------------------------------------------------
echo "[5/6] python3 依赖"
for mod in zstandard yaml; do
  if python3 -c "import $mod" 2>/dev/null; then ok "python3 -m $mod"; else warn "缺 python3 模块: $mod（pip3 install $mod）"; fi
done
echo

# ---- 6. 报告目录 ------------------------------------------------------------
echo "[6/6] 产物目录"
if [ -n "$KB" ] && [ -d "$KB/l8/runs" ]; then
  ok "$KB/l8/runs 可写（本轮产物落这里，RUN=\$(date +%Y%m%d-%H%M)）"
else
  warn "找不到 $KB/l8/runs"
fi
echo

# ---- 结论 -------------------------------------------------------------------
echo "== 结论 =="
echo "  BLOCKER 才是「停下并报告缺什么」；ADVISORY 是按能力矩阵选身份的建议，不阻断。"
if [ "$BLOCKERS" -gt 0 ]; then
  echo "  ❌ $BLOCKERS 个 BLOCKER，$WARNINGS 个 WARNING，$ADVISORY 个 ADVISORY"
  echo "  → 停下来，把上面的 BLOCK 逐条报告为「缺什么」，不要绕路硬试。"
  exit 1
fi
if [ "$ADVISORY" -gt 0 ]; then
  echo "  ✅ 通过（$WARNINGS 个 WARNING，$ADVISORY 个 ADVISORY）→ 可以进入阶段 1"
  echo "  ⚠ 先照上面的能力矩阵逐 Base 选身份（记录 / 字段定义 / 附件字节，三种操作身份可能不同）"
else
  echo "  ✅ 通过（$WARNINGS 个 WARNING）→ 可以进入阶段 1"
fi
exit 0
