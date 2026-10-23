#!/usr/bin/env bash
# no_publish_env.test.sh —— 判据：`KB_NO_PUBLISH=1` 真的能让链**不往生产结论表落行**。
#
# ── 为什么有它（2026-10-23）
#
# 委托方要求跑批期间「不要改知识库任务表格」，而链的命令行是**守衡侧模板逐字照抄**的 ⇒
# 调用方没有位置塞 `--no-publish`。解法是给 `review_run.sh` 加一个**环境变量闸门**。
# 加闸门这件事本身有风险：**默认行为一旦被改坏，守衡那边所有真单都不再写结论表**，
# 而且不会有任何东西变红（那种"安静地不写了"正是本仓最怕的形状）。
# ⇒ 所以必须有一条**能红的尺子**，而不是注释里写一句"默认不变"。
#
# ── 它怎么判（**读的是 review_run.sh 里那几行真代码，不是我抄的副本**）
#
# 从文件里把三行抽出来（`NO_PUBLISH=` 赋值行、`PUB=()` 初始化、`[ "$NO_PUBLISH" = "1" ] && PUB=(…)`），
# 在子 shell 里按不同环境值**真的求值一次**，看 `PUB` 数组里到底有没有 `--no-publish-to-feishu`。
#
# ── 反向对照（缺了它这条判据就只是注释）
#
# 把抽出来的赋值行**换回 `NO_PUBLISH=0`**（= 假装闸门被删掉），再喂 `KB_NO_PUBLISH=1`：
# 那一步**必须失败**。它失败才证明前面那几条绿是"闸门在起作用"，而不是"这几行怎么跑都绿"。
#
# 用法：`bash kb/l8/no_publish_env.test.sh` —— 全绿退 0，任一红退 1。
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
TARGET="$ROOT/kb/l8/review_run.sh"

PASS=0; FAIL=0
chk() { # chk <名字> <期望> <实到>
  if [ "$2" = "$3" ]; then PASS=$((PASS+1)); printf '  ✅ %s\n' "$1"
  else FAIL=$((FAIL+1)); printf '  ❌ %s｜期望 %q，实到 %q\n' "$1" "$2" "$3"; fi
}

[ -f "$TARGET" ] || { echo "找不到 $TARGET —— 判据的前提不成立，按未测处理（退 2）"; exit 2; }

# ── 抽真代码 ──────────────────────────────────────────────────────────────
SNIPPET="$(grep -E '^(NO_PUBLISH=|PUB=\(\)|\[ "\$NO_PUBLISH" = "1" \])' "$TARGET")"
LINES_N="$(printf '%s\n' "$SNIPPET" | grep -c .)"

echo "── 判据对象：$TARGET"
echo "── 抽出的真代码（$LINES_N 行）："
printf '%s\n' "$SNIPPET" | sed 's/^/     /'

fails=0
[ "$LINES_N" -eq 3 ] || { echo "  ❌ 只抽出 $LINES_N 行（要 3 行）—— 判据前提不成立"; fails=$((fails+1)); }

# ── 求值：给定环境值，`PUB` 里到底有没有那个旗标 ────────────────────────────
PUB_OF() { # PUB_OF <snippet> <KB_NO_PUBLISH 值|UNSET>
  local snip="$1" val="$2"
  if [ "$val" = UNSET ]; then
    env -u KB_NO_PUBLISH bash -c "$snip"$'\n''printf "%s" "${PUB[*]-}"'
  else
    KB_NO_PUBLISH="$val" bash -c "$snip"$'\n''printf "%s" "${PUB[*]-}"'
  fi
}

echo "── 真代码求值"
chk "不设变量 ⇒ 照旧发布（PUB 空 ⇒ 命令行与改动前逐字相同）" "" "$(PUB_OF "$SNIPPET" UNSET)"
chk "KB_NO_PUBLISH=1 ⇒ 不发布" "--no-publish-to-feishu" "$(PUB_OF "$SNIPPET" 1)"
chk "KB_NO_PUBLISH=0 ⇒ 发布（显式关掉闸门）" "" "$(PUB_OF "$SNIPPET" 0)"
chk "KB_NO_PUBLISH=true ⇒ 发布（只认逐字 1，不认 true）" "" "$(PUB_OF "$SNIPPET" true)"
chk "KB_NO_PUBLISH=yes ⇒ 发布（不认 yes）" "" "$(PUB_OF "$SNIPPET" yes)"

echo "── 接线：两个引擎调用点都得把 PUB 带进去（带不进 = 开关是摆设）"
INVOKES="$(grep -c '"\${PUB\[@\]+"\${PUB\[@\]}"}"' "$TARGET")"
chk "PUB 被拼进引擎命令行（应有 2 处：带 --question 与不带）" "2" "$INVOKES"

echo "── 反向对照：把赋值行换回 NO_PUBLISH=0（假装闸门被删）⇒ 上面那条『开』必须失败"
MUTATED="$(printf '%s\n' "$SNIPPET" | sed 's/^NO_PUBLISH=.*/NO_PUBLISH=0/')"
MUT_OUT="$(PUB_OF "$MUTATED" 1)"
if [ "$MUT_OUT" = "" ]; then
  PASS=$((PASS+1)); printf '  ✅ 反向对照成立：闸门被删掉时 KB_NO_PUBLISH=1 **不再生效**（实到 %q）—— 证明前面几条绿是闸门在起作用\n' "$MUT_OUT"
else
  FAIL=$((FAIL+1)); printf '  ❌ 反向对照失败：闸门删掉后仍然生效（实到 %q）⇒ 这条判据分辨不出好坏\n' "$MUT_OUT"
fi

echo
if [ "$fails" -eq 0 ] && [ "$FAIL" -eq 0 ]; then
  echo "no_publish_env：通过 $PASS 项 / 失败 0 项"
  exit 0
fi
echo "no_publish_env：通过 $PASS 项 / 失败 $((FAIL+fails)) 项"
exit 1