#!/bin/bash
# LBV 独立验证：跑 ②-1 gate-only + ②-3 记账，逐层一个 RUN
cd "/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理" || exit 9
BASE=LBV3-20261003

skill_of() {
  case "$1" in
    L4) echo kb-canonical-lookup ;;
    L5) echo kb-p0-check ;;
    L6) echo kb-recall ;;
    L7) echo kb-check ;;
    *)   echo "" ;;
  esac
}

for L in L4 L5 L6; do
  SK=$(skill_of $L)
  echo "########## $L  skill=$SK  run=$BASE-$L ##########"
  echo "--- ②-1 gate-only ---"
  sh kb/kbpy l7/scripts/kb_pipeline.py --sync --via-skill --only $L --gate-only --run $BASE-$L >/tmp/lbv3-$L-gate.txt 2>&1
  echo "  gate exit=$?"
  grep -E "闸门：|落章引擎 exit|run verdict" /tmp/lbv3-$L-gate.txt | sed 's/^/    /'
  echo "--- ②-3 记账（带 --invoked）---"
  sh kb/kbpy l7/scripts/kb_pipeline.py --sync --via-skill --only $L --run $BASE-$L \
     --invoked $SK --skill-session $L=LBV-verify-$L >/tmp/lbv3-$L-rec.txt 2>&1
  echo "  record exit=$?"
  grep -E "层侧落章实测|结论：" /tmp/lbv3-$L-rec.txt | tail -2 | sed 's/^/    /'
  echo
done

echo "########## L7 单独跑（跨层闸门，不带凭据）##########"
sh kb/kbpy l7/scripts/kb_pipeline.py --sync --via-skill --only L7 --run $BASE-L7 >/tmp/lbv3-L7.txt 2>&1
echo "  L7 exit=$?"
tail -4 /tmp/lbv3-L7.txt | sed 's/^/    /'
echo
echo "########## ②d 三条审计 ##########"
for L in L4 L5 L6; do
  echo "--- audit $BASE-$L ---"
  sh kb/kbpy l7/scripts/skill_invocation_audit.py --run $BASE-$L 2>&1 | grep -E "结论：|退出码：|E[0-9] " | sed 's/^/    /'
  echo "    audit exit=${PIPESTATUS[0]}"
done
echo
echo "########## ②c 复判新鲜度 ##########"
sh kb/kbpy l7/scripts/freshness.py >/tmp/lbv3-fresh2.txt 2>&1
echo "  freshness exit=$?"
tail -2 /tmp/lbv3-fresh2.txt | sed 's/^/    /'
