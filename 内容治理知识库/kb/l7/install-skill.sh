#!/usr/bin/env bash
# 把 KB l7 层的 kb-content-review 装到 ~/.dsh/skills/，供宿主 skill 目录加载。
#
# 背景（实测结论，2026-09-23）：
#   本机 trld 监控层会给「经由 Node/Electron 写出的 .md」落下宿主读不懂的加密信封
#   （首字节 88 7d 1c ??）。宿主 = Electron/Node，读到脏字节 → frontmatter 解析失败
#   → skill 不进目录（现象：/skill 列表里查不到 kb-content-review）。
#   反例对照：同样内容用 shell（cat）写出，宿主读到的就是明文，skill 立即进目录。
#   所以安装必须走 shell 写盘，并用 Node 回读校验「不是信封」。
#
# 用法： bash install-skill.sh          安装并校验
#        bash install-skill.sh --check  只校验，不写入（不一致 → exit 2）

set -euo pipefail

SRC="/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理/kb/l7/skills/kb-content-review"
DST="$HOME/.dsh/skills/kb-content-review"
APP="/Applications/DSH Desktop.app.pre-lute-20260907-111753/Contents/MacOS/DSH Desktop"

FILES=(README.md SKILL.md references/categories.md references/protocols.md scripts/review.py)

if [ ! -f "$SRC/SKILL.md" ]; then echo "源不存在：$SRC" >&2; exit 1; fi

if [ "${1:-}" = "--check" ]; then
  drift=0
  for f in "${FILES[@]}"; do
    if ! cmp -s "$SRC/$f" "$DST/$f"; then echo "DRIFT $f"; drift=1; fi
  done
  ELECTRON_RUN_AS_NODE=1 "$APP" -e '
    const fs=require("fs"),p=require("path"),os=require("os");
    const D=p.join(os.homedir(),".dsh/skills/kb-content-review");
    const b=fs.readFileSync(p.join(D,"SKILL.md"));
    const ok=b.slice(0,3).toString("utf8")==="---";
    console.log("node 读 SKILL.md：", b.length, "字节，首 3 字节 =", JSON.stringify(b.slice(0,3).toString("utf8")), ok?"（明文，可解析）":"（信封/脏字节，宿主读不懂）");
    process.exit(ok?0:4);
  ' || drift=1
  if [ "$drift" = 0 ]; then echo "CHECK OK：安装副本与源一致，且宿主可读"; else echo "CHECK FAIL"; exit 2; fi
  exit 0
fi

mkdir -p "$DST/references" "$DST/scripts"
for f in "${FILES[@]}"; do
  cat "$SRC/$f" > "$DST/$f"
done
chmod +x "$DST/scripts/review.py"
echo "已安装到 $DST"

# 校验：逐字节一致 + 宿主可读
fail=0
for f in "${FILES[@]}"; do
  cmp -s "$SRC/$f" "$DST/$f" || { echo "MISMATCH $f"; fail=1; }
done
ELECTRON_RUN_AS_NODE=1 "$APP" -e '
  const fs=require("fs"),p=require("path"),os=require("os");
  const D=p.join(os.homedir(),".dsh/skills/kb-content-review");
  const b=fs.readFileSync(p.join(D,"SKILL.md"));
  if (b.slice(0,3).toString("utf8")!=="---") { console.log("宿主读不懂 SKILL.md（信封）"); process.exit(4); }
  console.log("宿主可读：SKILL.md", b.length, "字节，frontmatter 起始正常");
' || fail=1
[ "$fail" = 0 ] && echo "安装校验通过" || { echo "安装校验失败"; exit 3; }
