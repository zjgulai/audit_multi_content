import yaml,collections,os
sk=yaml.safe_load(open('kb/l7/registry/skills.yaml'))
c=collections.defaultdict(list)
for r in sk['skills']:
    d=r.get('dir_name') or r.get('id')
    c[d].append((r.get('id'),r.get('status')))
bad=[(d,v) for d,v in c.items() if len(v)>1]
print("装载名/登记名撞平组数:",len(bad))
for d,v in bad: print("   撞平:",d,"<-",v)
base=os.path.expanduser('~/.dsh/skills')
dirs=set(os.listdir(base))
# 登记为本项目+生产的成员，是否都有真实目录
miss=[]
for r in sk['skills']:
    if r.get('scope')=='本项目' and r.get('status')=='生产':
        d=r.get('dir_name') or r.get('id')
        if d not in dirs: miss.append((r['id'],d))
print("scope=本项目 & status=生产 但装载位无同名目录:",len(miss),miss)
