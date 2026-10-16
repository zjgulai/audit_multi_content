import os, time, subprocess, sys
HERE=os.path.dirname(os.path.abspath(__file__))
def n(f): 
    p=os.path.join(HERE,f)
    return sum(1 for _ in open(p,encoding='utf-8')) if os.path.exists(p) else 0
while True:
    r=[n("a-round-%d.jsonl"%i) for i in (1,2,3)]
    print("%s r1=%d/53 r2=%d/53 r3=%d/53 load=%s" % (time.strftime("%H:%M:%S"), r[0], r[1], r[2],
          subprocess.run(["uptime"],capture_output=True,text=True).stdout.split("load averages: ")[-1].strip()), flush=True)
    if all(x>=53 for x in r): print("ALL THREE ROUNDS DONE"); sys.exit(0)
    if not subprocess.run(["pgrep","-f","run-round.py"],capture_output=True).stdout.strip():
        print("NO RUNNERS LEFT r=%s" % r); sys.exit(1)
    time.sleep(180)
