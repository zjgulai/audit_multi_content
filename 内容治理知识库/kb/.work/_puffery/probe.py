import json, subprocess, sys, os
CASES = [
 ("我们最好的吸奶器", "expect_clear", "主观最高级·中文"),
 ("最佳选择", "expect_clear", "主观最高级·中文"),
 ("Our pump is the best on the market", "expect_clear", "主观最高级·英文 best"),
 ("Super strong suction for busy moms", "expect_clear", "夸张词·super"),
 ("超级静音吸奶器，超强吸力", "expect_clear", "夸张词·超级/超强"),
 ("最强电机", "expect_clear", "夸张词·最强"),
 ("100% safe for your baby", "expect_keep", "安全承诺 100% safe"),
 ("The safest pump for every mom", "expect_keep", "安全承诺 safest"),
 ("zero risk pumping", "expect_keep", "安全承诺 zero risk"),
 ("最安全的选择", "expect_keep", "安全承诺 最安全"),
 ("Best-selling breast pump", "expect_keep", "需依据 销量宣称"),
 ("排名第一的吸奶器", "expect_keep", "需依据 排名宣称"),
 ("第一名的吸奶器", "expect_keep", "需依据 排名宣称"),
 ("fits all breast shapes", "expect_keep", "绝对化适配"),
]
rows=[]
for text, exp, why in CASES:
    p = subprocess.run(["sh","kb/kbpy","l5/p0_fastpath.py","--text",text,"--json"],
                       capture_output=True, text=True)
    try: d=json.loads(p.stdout)
    except Exception: d={}
    fs=d.get("findings") or []
    rows.append(dict(text=text, expect=exp, why=why, state=d.get("state"),
        codes=sorted({f.get("rule_code") for f in fs}),
        pats=sorted({m.get("pattern") for f in fs for m in (f.get("matched") or [])})[:6]))
print(f"{'判定':6} {'期望':13} {'state':18} codes / patterns  ← text")
for r in rows:
    ok = "✅" if (r["expect"]=="expect_clear" and not r["codes"]) or (r["expect"]=="expect_keep" and r["codes"]) else "❌"
    print(f"{ok:6} {r['expect']:13} {str(r['state']):18} {','.join(c for c in r['codes'] if c)}|{','.join(p for p in r['pats'] if p)}  ← {r['text']}")
tag = sys.argv[1] if len(sys.argv)>1 else "run"
json.dump(rows, open(f"kb/.work/_puffery/{tag}.json","w"), ensure_ascii=False, indent=1)
