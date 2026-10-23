#!/usr/bin/env python3
"""步骤1：桌面规则清单 vs KB 权威库 · 逐条逐字段比对（只读）。

口径：
- 表 638 行 = 措辞库 509（rules.jsonl 唯一 rule_id）＋ 外部标准 129（external_standard.jsonl）。
- rules.jsonl 共 1018 行 = 509 条规则 × 2 行（生行 article_no 空 ＋ 富化行 article_no 有）；
  取「富化行」为比对基准（L4 发号后的值），并单独记录生行差异。
- 富化字段 authority / rule_kind 的真源是 manifest_l3.jsonl（kb_ledger.rules_enriched_view）。
"""
import json, os, sys, collections, hashlib
KB = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(KB, 'kb'))
from openpyxl import load_workbook

XLSX = os.path.expanduser('~/Desktop/规则清单-P0-P3-按等级-20261016.xlsx')

def load_kb():
    import kb_ledger
    rows, stats = kb_ledger.rules_enriched_view(
        f'{KB}/kb/l3/candidates/rules.jsonl', f'{KB}/kb/l3/manifest_l3.jsonl')
    ext = {}
    for line in open(f'{KB}/kb/l3/candidates/external_standard.jsonl', encoding='utf-8'):
        if line.strip():
            r = json.loads(line); ext[r['rule_id']] = r
    return rows, ext, stats

def load_table():
    wb = load_workbook(XLSX, data_only=True)
    ws = wb['全部规则 (P0-P3)']
    hdr = [ws.cell(row=5, column=c).value for c in range(1, 44)]
    out = []
    for r in range(6, ws.max_row + 1):
        v = [ws.cell(row=r, column=c).value for c in range(1, 44)]
        if all(x is None for x in v):
            continue
        out.append(dict(zip(hdr, v)))
    return out

def norm(v):
    if v is None: return ''
    if isinstance(v, (list, tuple)): return ' / '.join(norm(x) for x in v)
    return str(v).strip()

def main():
    rows, ext, stats = load_kb()
    tb = load_table()
    print('KB 富化视图：', stats)
    t_rules = {r['规则ID(rule_id)']: r for r in tb if r['来源候选件'] == 'rules'}
    t_ext = {r['规则ID(rule_id)']: r for r in tb if r['来源候选件'] == 'external_standard'}
    print(f'表：rules={len(t_rules)} ext={len(t_ext)} ｜ KB：rules={len(rows)} ext={len(ext)}')

    # 字段映射：表列 → KB 键
    MAP_RULES = [
        ('条款号', 'article_no'), ('规则码(rule_code)', 'rule_code'),
        ('命中表达(forbidden_expression)', 'forbidden_expression'),
        ('规则内容(rule_text)', 'rule_text'), ('判定原因(reason)', 'reason'),
        ('建议改法(suggested_replacement)', 'suggested_replacement'),
        ('处理动作(required_action)', 'required_action'),
        ('修改对照(expression_fix_pairs)', 'expression_fix_pairs'),
        ('形态(form)', 'form'), ('知识库类型(kb_type)', 'kb_type'),
        ('证据级(evidence_level)', 'evidence_level'), ('证据摘要(evidence_digest)', 'evidence_digest'),
        ('生效日', 'effective_from'), ('有效期至', 'effective_to'),
        ('半衰期(天)', 'half_life_days'), ('负责人', 'owner'),
        ('模态', 'modality'), ('锚点(anchor)', 'anchor'),
        ('来源记录数(support_count)', 'support_count'),
        ('风险等级', 'risk_level'), ('核验状态(verification)', 'verification'),
        ('优先级', 'p_level'),
    ]
    MAP_EXT = MAP_RULES + [
        ('命中条件(condition)', 'condition'), ('逐字证据(evidence_quote)', 'evidence_quote'),
        ('质量(quality)', 'quality'), ('状态(status)', 'rule_status'),
        ('适用辖区', 'applicable_jurisdiction'),
    ]
    def compare(name, tset, kbset, mapping):
        print(f'\n===== {name} =====')
        only_t = set(tset) - set(kbset); only_k = set(kbset) - set(tset)
        print(f'rule_id 集合：表独有 {len(only_t)} ｜ 库独有 {len(only_k)}')
        for rid in list(only_t)[:5]: print('  表独有:', rid)
        for rid in list(only_k)[:5]: print('  库独有:', rid)
        for col, key in mapping:
            bad = []
            for rid in set(tset) & set(kbset):
                tv = norm(tset[rid].get(col)); kv = norm(kbset[rid].get(key))
                if tv != kv:
                    bad.append((rid, tv, kv))
            mark = 'OK ' if not bad else 'XX '
            print(f'{mark}{col:<34}→ {key:<26} 不一致 {len(bad)}')
            for rid, tv, kv in bad[:3]:
                print(f'      {rid}: 表={tv[:70]!r} 库={kv[:70]!r}')
        return (set(tset) - set(kbset), set(kbset) - set(tset))

    compare('措辞库 rules（表509 / 库509）', t_rules, rows, MAP_RULES)
    compare('外部标准 external_standard（表129 / 库129）', t_ext, ext, MAP_EXT)

    # 表的附加列（库里根本没有对应字段的）
    print('\n===== 表有、库无对应字段的列（需新造或来源不同）=====')
    allkeys = set()
    for r in list(rows.values()) + list(ext.values()): allkeys |= set(r.keys())
    for col in ['可否被 P0 拦截', '不可拦截原因', '所属类别', '所属子类', '实际触发表达（P0 模式表，含同义/变体扩展）',
                '触发串数', '正则数', '白名单数', '适用范围', '规则性质(rule_kind)', '权威来源(authority)',
                '证据单元数', 'PRD维度(risk_category)']:
        print(f'  {col}')
    print('\nKB 全字段：', sorted(allkeys))

if __name__ == '__main__':
    main()
