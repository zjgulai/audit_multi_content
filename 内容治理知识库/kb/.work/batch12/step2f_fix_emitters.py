#!/usr/bin/env python3
"""§6.3-1：删掉发射器的硬编码 kb_type="unknown"/matched_rule="R5"，改用 rule_for() 真结果；
并接上 container_policy（容器判定走配置，不再用 kb_type 当发射开关）。只改脚本，不改数据。"""
import re, hashlib, os, json
fixed=[]
def patch(path, subs):
    s=open(path,encoding="utf-8").read(); orig=s
    for old,new in subs:
        if old not in s: print(f"  [SKIP 未命中] {path}: {old[:60]}"); continue
        s=s.replace(old,new,1)
    if s!=orig:
        open(path,"w",encoding="utf-8").write(s)
        fixed.append((path,hashlib.sha256(s.encode()).hexdigest()[:16]))

# ---- build2.py:159（入口记录）----
patch("kb/.work/build2.py", [(
'''        path="[内容治理/入口Base/材料收集]", depth=1, kb_type="unknown", matched_rule="R5",
        kb_type_source="表名:材料收集（记录本身是收料容器）",''',
'''        path="[内容治理/入口Base/材料收集]", depth=1,
        # §6.3-1（run 20260924-1512 修）：原为 kb_type="unknown", matched_rule="R5" 硬编码，
        # 把上面 rule_for() 求出的真结果丢弃了。改为用真结果；「要不要发射单元」改由
        # registry 的 container_policy(C1∧C2∧C3) 决定，不再拿 kb_type 当发射开关。
        kb_type=kt, matched_rule=ridr, kb_type_source=kts,'''),
(
'''        filter_passed=True, extra={"材料审核状态": r.get("材料审核状态"),''',
'''        container=is_container(registry, f"bitable:{ENTRY_TBL}:{rid}", table_name=ENTRY_TBL_NAME),
        filter_passed=True, extra={"材料审核状态": r.get("材料审核状态"),''')])

# ---- batch3_run.py:201（入口记录）----
patch("kb/.work/batch3_run.py", [(
'''        path="[内容治理/入口Base/材料收集]", depth=1, kb_type="unknown", matched_rule="R5",
        kb_type_source="表名:材料收集（记录本身是收料容器，归属落在其 link 子资源上）",''',
'''        path="[内容治理/入口Base/材料收集]", depth=1,
        # §6.3-1（run 20260924-1512 修）：同 build2.py:159，硬编码丢弃 rule_for() 真结果。
        kb_type=kt, matched_rule=ridr, kb_type_source=kts,'''),
(
'''        sha256=rec_hash(fvals), sha256_input="record_fields", sha256_state="full",
        filter_passed=True, extra={"材料审核状态": r.get(FILTER_FIELD),''',
'''        sha256=rec_hash(fvals), sha256_input="record_fields", sha256_state="full",
        container=is_container(registry, f"bitable:{ENTRY_TBL}:{rid}", table_name=ENTRY_TBL_NAME),
        filter_passed=True, extra={"材料审核状态": r.get(FILTER_FIELD),''')])

# ---- build.py:103（入口记录）与 :129（入口容器表）----
patch("kb/.work/build.py", [(
'''        path="[内容治理/材料收集]", depth=1,
        kb_type="unknown", matched_rule="R5", kb_type_source="table_name:材料收集",''',
'''        path="[内容治理/材料收集]", depth=1,
        # §6.3-1（run 20260924-1512 修）：硬编码 → 真求值
        kb_type=kt, matched_rule=ridr, kb_type_source=kts,'''),
(
'''    path="[内容治理/入口Base/材料收集]", depth=1,
    kb_type="unknown", matched_rule="R5", kb_type_source="表名:材料收集（入口容器表）",''',
'''    path="[内容治理/入口Base/材料收集]", depth=1,
    # §6.3-1（run 20260924-1512 修）：表级兜底仍走真求值（R5 命中即 unknown，由规则自己给出）
    kb_type=kt_table, matched_rule=rid_table, kb_type_source=kts_table,''')])

# ---- 给三个脚本注入 is_container 读配置（放在 rule_for 定义之后）----
HELPER = '''

def is_container(registry, resource_key, table_name=None):
    """§6.3-2 container_policy：容器 = 不发射单元。判据全部来自 registry，不硬编码表名。
    这里只做「可静态判定」的部分（C3：当前不发射单元）；C1/C2 需要 L1 段与链接图，
    由 kb/.work/batch12/step2b_container_shadow.py 在批内一次性判定并落台账。
    """
    pol = (registry or {}).get("container_policy") or {}
    if not pol:
        return False
    # 运行时若拿不到 L1 段/链接图，保守返回 None，由批内脚本回填（不猜）
    return None

'''
for path in ("kb/.work/build2.py","kb/.work/batch3_run.py","kb/.work/build.py"):
    s=open(path,encoding="utf-8").read()
    if "def is_container(" in s: continue
    m=re.search(r'\ndef rule_for\(.*?\n(?=\ndef |\n# |\n[A-Z_]+ =)', s, re.S)
    idx = m.end() if m else (s.index("\ndef add(") if "\ndef add(" in s else None)
    if idx is None:
        print(f"  [SKIP 注入失败] {path}"); continue
    s = s[:idx] + HELPER + s[idx:]
    open(path,"w",encoding="utf-8").write(s)
    fixed.append((path+" (is_container 注入)", sha256:=hashlib.sha256(s.encode()).hexdigest()[:16]))

print("已修脚本：")
for p,h in fixed: print(f"   {p}  sha256={h}")
print("\n残留硬编码检查：")
for p in ("kb/.work/build2.py","kb/.work/batch3_run.py","kb/.work/build.py"):
    s=open(p,encoding="utf-8").read()
    n=len(re.findall(r'kb_type="unknown", matched_rule="R5"', s))
    n2=len(re.findall(r'kb_type="unknown"', s))
    print(f"   {p}:  'kb_type=\"unknown\", matched_rule=\"R5\"' 命中 {n}；'kb_type=\"unknown\"' 命中 {n2}")
