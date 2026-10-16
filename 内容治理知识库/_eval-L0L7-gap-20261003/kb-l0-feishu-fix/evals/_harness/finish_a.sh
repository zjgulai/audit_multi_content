#!/usr/bin/env bash
# A 卷跑完后的收尾链：回填 → 评分 → Output 断言 → YAML → 用例 HTML → 自检 → 过程 HTML
set -euo pipefail
cd "$(dirname "$0")"
RSE=/Users/lute/.dsh/skills/root-skills-eval/scripts
MNT="$(cd ../../../_mount-l0fix/kb-l0-feishu && pwd)"

echo "── 0) 数据健康检查（空回复/会话缺失=0 才继续）"
python3 - <<'PY'
import json,glob,sys
tot=empty=nos=0; ids=set()
for f in glob.glob('a-round-*.jsonl'):
    for l in open(f,encoding='utf-8'):
        if l.strip():
            o=json.loads(l); tot+=1
            if not o.get('reply'): empty+=1
            if not o.get('session_found'): nos+=1
print(f"记录 {tot}/312 | 空回复 {empty} | 会话缺失 {nos}")
sys.exit(1 if (empty or nos or tot!=312) else 0)
PY

echo "── 1) 回填判定"
python3 judge.py

echo "── 2) 触发评分"
python3 "$RSE/score-trigger-eval.py" score-input-a.json --json summary-a.json | tail -25

echo "── 3) Output 断言"
python3 output_assertions.py

echo "── 4) validate-skill（对挂载位，避开 evals/ 目录警告）"
python3 /Users/lute/.dsh/skills/root-skills-creator/scripts/validate-skill.py --json "$MNT" > validate-skill.json
python3 -c "import json;d=json.load(open('validate-skill.json',encoding='utf-8'));print('valid=%s score=%s warnings=%d errors=%d'%(d['valid'],d['score'],len(d['warnings']),len(d['errors'])))"

echo "── 5) 生成修复版 YAML"
python3 make_yaml.py

echo "── 6) 测试用例 HTML（最终版 A 卷）"
python3 "$RSE/build-testcases-html.py" --name kb-l0-feishu --results results-a.json \
        --output ../kb-l0-feishu-test-cases.html

echo "── 7) 输出前自检 15 项"
python3 selfcheck15.py || echo "(15 项自检有异常，见上)"

echo "── 8) 评测过程 HTML"
python3 build_process_html.py
echo "✅ 收尾链完成"
