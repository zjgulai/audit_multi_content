#!/bin/bash
# LBV4 独立验证：完整评审链（只读档，不带 --apply）
cd "/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理" || exit 9
BASE=LBV4-20261003

skill_of() {
  case "$1" in
    L4) echo kb-canonical-lookup ;;
    L5) echo kb-p0-check ;;
    L6) echo kb-recall ;;
    L7) echo kb-check ;;
  esac
}

echo "===== ① freshness 前置 ====="
sh kb/kbpy l7/scripts/freshness.py >/tmp/lbv4-fresh1.txt 2>&1
echo "  exit=$?  $(tail -1 /tmp/lbv4-fresh1.txt)"

for L in L4 L5 L6; do
  SK=$(skill_of $L)
  echo
  echo "===== $L  skill=$SK  run=$BASE-$L ====="
  echo "--- ②-1 gate-only ---"
  sh kb/kbpy l7/scripts/kb_pipeline.py --sync --via-skill --only $L --gate-only --run $BASE-$L >/tmp/lbv4-$L-gate.txt 2>&1
  echo "  exit=$?"
  grep -E "闸门：|落章引擎 exit|产物变化" /tmp/lbv4-$L-gate.txt | sed 's/^/    /'
  echo "--- ②-3 记账 --invoked $SK ---"
  sh kb/kbpy l7/scripts/kb_pipeline.py --sync --via-skill --only $L --run $BASE-$L \
     --invoked $SK --skill-session $L=LBV4-verify-$L >/tmp/lbv4-$L-rec.txt 2>&1
  echo "  exit=$?"
  grep -E "层侧落章实测" /tmp/lbv4-$L-rec.txt | sed 's/^/    /'
done

echo
echo "===== ②b L7 单独跑 ====="
sh kb/kbpy l7/scripts/kb_pipeline.py --sync --via-skill --only L7 --run $BASE-L7 >/tmp/lbv4-L7.txt 2>&1
echo "  exit=$?"
tail -3 /tmp/lbv4-L7.txt | sed 's/^/    /'

echo
echo "===== ②d 三条审计（红线：必须红 0）====="
for L in L4 L5 L6; do
  sh kb/kbpy l7/scripts/skill_invocation_audit.py --run $BASE-$L >/tmp/lbv4-audit-$L.txt 2>&1
  echo "  $BASE-$L  exit=$?"
  grep -E "结论：|退出码：" /tmp/lbv4-audit-$L.txt | sed 's/^/      /'
done

echo
echo "===== ②c 复判新鲜度 ====="
sh kb/kbpy l7/scripts/freshness.py >/tmp/lbv4-fresh2.txt 2>&1
echo "  exit=$?  $(tail -1 /tmp/lbv4-fresh2.txt)"
echo
echo "===== DONE ====="
