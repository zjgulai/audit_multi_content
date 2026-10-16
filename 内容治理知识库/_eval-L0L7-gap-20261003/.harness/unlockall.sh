#!/bin/sh
KB="/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理"
EV="$KB/_eval-L0L7-gap-20261003"
chmod 755 "$EV/_fixrun-kb-check" "$EV/kb-check/evals" 2>/dev/null
chmod 755 "$KB/_eval-kb-check-20261004" "$KB/_eval-kb-check-独立核验-20261003" 2>/dev/null
chmod 644 "$EV/_fixrun-kb-check/cases-a.json" "$EV/_fixrun-kb-check/cases-b.json" 2>/dev/null
echo "UNLOCKED-all"
