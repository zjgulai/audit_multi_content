import yaml,importlib.util,os,sys
R='kb/l7/registry/'
ry=yaml.safe_load(open(R+'routes.yaml'))['frozen_expectation']['dir_name_map']
def load_alias(p,names=('ALIAS',)):
    src=open(p,encoding='utf-8').read()
    ns={}
    import re
    m=re.search(r'^ALIAS = \{(.*?)^\}',src,re.S|re.M)
    exec("ALIAS={"+m.group(1)+"}",ns)
    return ns['ALIAS']
a1=load_alias('kb/l7/scripts/routes_reconcile.py')
a2=load_alias('_eval-kb-manage/kb_routes_score.py')
print("routes.yaml dir_name_map 行数 :",len(ry))
print("routes_reconcile.py  ALIAS 行数:",len(a1))
print("kb_routes_score.py   ALIAS 行数:",len(a2))
print()
keys=set(ry)|set(a1)|set(a2)
bad=0
for k in sorted(keys):
    v0,v1,v2=ry.get(k),a1.get(k),a2.get(k)
    if not(v0==v1==v2):
        bad+=1
        print("  差异 %-34s routes.yaml=%-16s reconcile=%-16s score=%-16s"%(k,v0,v1,v2))
print("三表取值不一致的键：%d 个"%bad)
