#!/bin/sh
KB="/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理"
EV="$KB/_eval-L0L7-gap-20261003"; RUN="$EV/_fixrun-kb-check"
chmod 644 "$RUN/cases-a.json" "$RUN/cases-b.json" 2>/dev/null
chmod 755 "$EV/kb-check/evals" 2>/dev/null
chmod 755 "$KB/_eval-kb-check-20261004" 2>/dev/null
chmod 755 "$KB/_eval-kb-check-独立核验-20261003" 2>/dev/null
echo "UNLOCKED"
