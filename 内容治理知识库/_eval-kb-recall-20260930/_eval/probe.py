import os, glob, time, subprocess, sys
base=os.path.expanduser('~/.dsh/sessions')
tag="_eval-kb-recall-20260930-_eval-work-"
while True:
    tot=0
    for r in (1,2,3):
        t="_eval-work-a%d-item-"%r
        ds=[d for d in os.listdir(base) if tag in d and t in d]
        tot+=len(ds)
        print("  a%d 会话桶 %d"%(r,len(ds)), end="")
    print("  %s load=%s"%(time.strftime("%H:%M:%S"), subprocess.run(["uptime"],capture_output=True,text=True).stdout.split("load averages: ")[-1].strip()), flush=True)
    if not subprocess.run(["pgrep","-f","rt.py"],capture_output=True).stdout.strip():
        print("runner exited"); sys.exit(0)
    time.sleep(180)
