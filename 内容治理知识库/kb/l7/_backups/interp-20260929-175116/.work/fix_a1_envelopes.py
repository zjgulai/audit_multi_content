#!/usr/bin/env python3
"""A1：修复活路径上的「4096 字节信封」.md，让 node 侧读者（含 agent 的 read 工具）能读。

判据（精确，不靠猜首字节）：同一路径下 **Python 侧的字节数 != node 侧的字节数**。
实测 1,248 个不一致文件，差值**恒为 4096** —— 即「4096 字节前缀 + 原文」。

不动的部分（都是刻意的）：
  · `kb/l8/_archive/enveloped-*`（569 个）—— **故意归档的信封原文**，是那个写封装机制的证据本体，
    改了就毁证。原注记也要求动冻结层前先重建指纹。
  · `.work/hostlib.bak-20260928-152220/`（510）与 `.work/{kbcheck,kbremote}-home/`（18）
    —— 过期备份与测试沙箱，A2 直接删，不修。

修法：**内容一个字不改**。Python 读到的就是明文（这是信封最阴的地方：Python 侧一切正常），
所以把那份明文经 stdin 交给 node 的 `fs.writeFileSync` 重写，再读回断言。
全程用两份哈希对账：Python 侧修复前后的 sha256 必须相同（内容守恒），node 侧字节数必须与 Python 侧相等。
"""
import json
import os
import subprocess
import sys
import hashlib
import shutil

KB = "kb"
ARCHIVE = f"{KB}/l8/_archive/enveloped-repair-20260929-1200"
DSH = "/Applications/DSH Desktop.app.pre-lute-20260907-111753/Contents/MacOS/DSH Desktop"
WRITER = f"{KB}/.work/write_via_node.mjs"
ENV_LIST = "/tmp/env_list.json"

# 刻意不动的前缀
SKIP = (
    "l8/_archive/enveloped-",       # 信封证据原文归档
    ".work/hostlib.bak-20260928-152220/",   # 过期备份（A2 删）
    ".work/kbcheck-home/",          # 测试沙箱（A2 删）
    ".work/kbremote-home/",         # 测试沙箱（A2 删）
)


def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for b in iter(lambda: fh.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def main():
    lst = json.load(open(ENV_LIST, encoding="utf-8"))
    targets = [x for x in lst if not x["rel"].startswith(SKIP)]
    print(f"待修（活路径）：{len(targets)} 个")
    print(f"跳过（刻意归档/待删备份）：{len(lst) - len(targets)} 个")

    if os.path.isdir(ARCHIVE):
        shutil.rmtree(ARCHIVE)
    ok = fail = 0
    failures = []
    for x in targets:
        rel, p = x["rel"], os.path.join(KB, x["rel"])
        if not os.path.isfile(p):
            fail += 1
            failures.append((rel, "文件不存在"))
            continue
        # ① 内容守恒对账：修复前 Python 侧 sha256
        before = sha256_file(p)
        try:
            text = open(p, "rb").read().decode("utf-8")
        except UnicodeDecodeError as e:
            fail += 1
            failures.append((rel, f"Python 侧不是 UTF-8：{e}"))
            continue
        # ② 内容留底（cp 通道 → 留底本身也是明文，这正是我们要的可回滚状态）
        bak = os.path.join(ARCHIVE, rel)
        os.makedirs(os.path.dirname(bak), exist_ok=True)
        subprocess.run(["cp", p, bak], check=True)
        # ③ 用 node 重写（内容经 stdin，绕开一切文件写封装）
        r = subprocess.run(
            ["env", "ELECTRON_RUN_AS_NODE=1", DSH, WRITER, os.path.abspath(p)],
            input=text.encode("utf-8"), capture_output=True,
        )
        if r.returncode != 0:
            fail += 1
            failures.append((rel, f"node 写失败 rc={r.returncode} out={r.stdout[:120]!r} err={r.stderr[:200]!r}"))
            continue
        try:
            # ⚠ 不要用 splitlines()：node 输出的 head 走 toString("latin1")，
            # 文件头含 C1 控制字符（\x1c / \x85 / \x0b …）时，Python 的 splitlines()
            # **会把它们当换行**，于是 [-1] 取到 JSON 的尾巴 → 报 "Expecting value: line 1 column 1"。
            # 实测 39 个文件被这个 bug 误判为失败。直接整段 parse。
            info = json.loads(r.stdout.decode("utf-8"))
        except Exception as e:
            dump = f"/tmp/a1_fail_{fail}.out"
            open(dump, "wb").write(r.stdout)
            fail += 1
            failures.append((rel, f"读不到 node 的 JSON（{e}）；原始 stdout 存 {dump}"
                                  f"（{len(r.stdout)} 字节，尾 40 字节 {r.stdout[-40:]!r}）"))
            continue
        after = sha256_file(p)
        # ④ 双向断言：内容守恒 + node 也看到同样大小
        if after != before:
            fail += 1
            failures.append((rel, "内容变了（sha256 前后不一致）"))
        elif info["bytes_after"] != x["py"]:
            fail += 1
            failures.append((rel, f"node 侧大小 {info['bytes_after']} != Python 侧 {x['py']}"))
        else:
            ok += 1

    print(f"\n修好 {ok} 个，失败 {fail} 个")
    if failures:
        print("失败明细（前 10）：")
        for rel, why in failures[:10]:
            print(f"  {rel}  ← {why}")
    print(f"内容留底：{ARCHIVE}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
