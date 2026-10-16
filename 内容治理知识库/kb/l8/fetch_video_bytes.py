#!/usr/bin/env python3
"""把 L1 里已登记的**内嵌视频**字节取回本地（只落字节 + 记指纹，**不解读内容**）。

## 背景与边界（2026-10-08）

`kb/l8/extract_l1_video_refs.py` 只做**登记**（token/名字/mime/尺寸/anchor），
`sha256_state=not_downloaded`。本脚本补上**内容层的第一步：取字节**。

**身份与通道（实测，别按旧说法）**：
· `drive +download` 对这些 token 返 **HTTP 403**；
· **`drive +preview --type source_file` 用 `user` 令牌能取回原字节** ——
  实测 3,391,998 字节、魔数 `ftypqt`、与 L0/L1 登记的 `bytes` 逐字节一致。
⇒ 走 `L8_VIDEO_AS`（默认 `user`）。**Owner 2026-10-08 批准**：本条通道限「对齐任务」使用。

## 口径

· **只落字节**：下载 → 算 sha256 → 回写 `media_refs[].media_path/sha256/sha256_state`。
  **不做转写、不做抽帧**（那是 `ingest_videos.py` 的事，见那条工具的抬头）。
· **不猜**：下载失败**如实记 `download_failed` + 原始错误**，不把失败写成"已完成"。
· **可续跑**：文件已在本地且 sha 与登记一致 ⇒ 跳过（不重下）。
· **只在 `--apply` 时写产物**；台账（L0/L1）按库内惯例由调用方最后单独落。

用法：
    python3 kb/l8/fetch_video_bytes.py <RUN>                 # 干跑
    python3 kb/l8/fetch_video_bytes.py <RUN> --apply
    python3 kb/l8/fetch_video_bytes.py <RUN> --apply --only <file_token>[,<token>…]
"""
# ── 解释器守卫（与 l8 其它脚本同源）──
import os as _os, sys as _sys
if not _os.environ.get("KB_INTERP_OK"):
    _d = _os.path.dirname(_os.path.abspath(__file__)); _cfg = None
    while True:
        _p = _os.path.join(_d, ".kb-python")
        if _os.path.isfile(_p):
            _cfg = _p; break
        _q = _os.path.dirname(_d)
        if _q == _d: break
        _d = _q
    if _cfg:
        _want = next((l.split("#", 1)[0].strip() for l in open(_cfg, encoding="utf-8")
                      if l.split("#", 1)[0].strip()), "")
        _want = _os.path.expanduser(_want)
        if (_want and _os.access(_want, _os.X_OK)
                and _os.path.realpath(_want) != _os.path.realpath(_sys.executable)):
            _os.environ["KB_INTERP_OK"] = "1"
            _os.execve(_want, [_want, _os.path.abspath(__file__)] + _sys.argv[1:], dict(_os.environ))
# ──────────────────────────────────────────────────────────────────────────

import glob
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time

RUN = next((a for a in sys.argv[1:] if not a.startswith("--")), time.strftime("%Y%m%d-%H%M"))
APPLY = "--apply" in sys.argv
ONLY = [t for t in (sys.argv[sys.argv.index("--only") + 1].split(",") if "--only" in sys.argv else []) if t]
AS_ID = os.environ.get("L8_VIDEO_AS", "bot")           # ★ 2026-10-10 默认 user→bot
#   2026-10-08 当时实测「只有 user 通道通」（走 `drive +preview --type source_file`）；
#   但 2026-10-09 加了第二级通道 `docs +media-download` 之后，**bot 实测 14/14 全通**。
#   日更在 03:30 而 user 令牌只活 2 小时 ⇒ 默认 user **必然失败**，且"靠 agent 记得设
#   `L8_VIDEO_AS=bot`"不是执行点（本库 §2.4）。⇒ 默认改 bot；确实要 user 就显式设。
PROFILE = os.environ.get("L8_PROFILE", "dsh-kb")
LARK = os.path.expanduser("~/.dsh/bin/lark-cli")
DEST = "kb/l0/attachments/视频"
L1 = "kb/l1"


def sha_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for b in iter(lambda: fh.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def safe_name(tok, name):
    base = os.path.basename(name or tok)
    base = "".join(c if (c.isalnum() or c in "._-（）()") else "_" for c in base)[:80]
    return f"{tok[:16]}__{base}"


def _try_download(out, argv, tag):
    """跑一条下载命令并校验落盘。返回 (ok, err)。"""
    r = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8", errors="replace",
                       timeout=1800,
                       env={**os.environ, "PATH": os.path.expanduser("~/.dsh/bin") + ":" + os.environ.get("PATH", "")})
    try:
        d = json.loads(r.stdout)
    except Exception:
        return False, f"{tag}: " + (r.stdout or r.stderr)[:180]
    if not d.get("ok"):
        return False, f"{tag}: " + json.dumps(d.get("error") or {}, ensure_ascii=False)[:200]
    if not os.path.exists(out):
        return False, f"{tag} 报 ok 但文件不存在"
    return True, None


def fetch(tok, out, want_bytes):
    """两级通道取字节。返回 (ok, err)。

    ## ★ 2026-10-09：加第二级 `docs +media-download`（这条是**必须的**）

    病灶实测：有 3 个视频（`AfOdbiss…` / `I4H1bS4M…` / `VrvHb94r…`，174/174/180 MB）
    走 `drive +preview --type source_file` **两个身份都报 `981003`（token lookup failed）**
    —— 而**同一个 docx 里的另外 11 个视频全都取得到**，租户、文档权限都不是原因
    （`wiki +node-get` 实测 bot 就能读那个节点）。
    ⇒ 它们是**内嵌在 docx 里的媒体块**，得走**文档媒体**那条通道：

        lark-cli docs +media-download --token <file_token> --output <out>

    实测（bot 身份）：`ok:true`、`content_type: video/mp4`、`size_bytes 174173971`
    —— **与台账登记字节数逐字节一致**，魔数 `ftypmp42`。
    ⇒ 所以这 3 个从来不是「没权限」，是**通道用错了**（skill 红线 8 的原话：
      「对象存在但拿不到正文 → **换通道**，不许判『不可核』」）。

    顺序：preview 优先（对 11 个已验证有效、且拿的是原字节），失败才降级到文档媒体通道。
    """
    ok, err1 = _try_download(out, [LARK, "drive", "+preview", "--file-token", tok,
                                   "--type", "source_file", "--output", out,
                                   "--profile", PROFILE, "--as", AS_ID], "preview")
    if not ok:
        ok, err2 = _try_download(out, [LARK, "docs", "+media-download", "--token", tok,
                                       "--output", out, "--overwrite",
                                       "--profile", PROFILE, "--as", AS_ID], "media-download")
        if not ok:
            return False, f"{err1} ｜ 降级后仍失败 → {err2}"
    got = os.path.getsize(out)
    if want_bytes and got != want_bytes:
        return False, f"字节数不符：拿到 {got}，登记 {want_bytes}"
    return True, None


# ── 收集目标（读 L1 的 media_refs）──
targets = []
for f in sorted(glob.glob(f"{L1}/*/*.json")):
    if "/_archive/" in f:
        continue
    try:
        d = json.load(open(f, encoding="utf-8"))
    except Exception:
        continue
    if not isinstance(d, dict):
        continue
    vids = [m for m in (d.get("media_refs") or [])
            if isinstance(m, dict) and m.get("kind") == "video" and m.get("file_token")]
    for m in vids:
        if ONLY and m["file_token"] not in ONLY:
            continue
        targets.append({"artifact": f, "resource_key": d.get("resource_key"),
                        "token": m["file_token"], "name": m.get("name"),
                        "bytes": m.get("bytes"), "mime": m.get("mime"), "seq": m.get("seq")})

print(f"[{RUN}] 视频字节落库{'【落盘】' if APPLY else '【干跑】'}｜身份={AS_ID}｜目标 {len(targets)} 个"
      f"｜登记合计 {sum(t['bytes'] or 0 for t in targets)/1048576:.1f} MB")
report = []
for t in targets:
    want = int(t["bytes"]) if t["bytes"] else None
    fn = safe_name(t["token"], t["name"])
    out = f"{DEST}/{fn}"
    ent = dict(t)
    if os.path.exists(out) and want and os.path.getsize(out) == want:
        ent.update(size=os.path.getsize(out), sha256=sha_file(out), state="already_local")
        print(f"  = {t['token'][:20]} 已在本地（{want} 字节，跳过）")
        report.append(ent)
        continue
    if not APPLY:
        print(f"  · {t['token'][:20]} → {fn}（{want} 字节）【干跑】")
        ent.update(state="planned")
        report.append(ent)
        continue
    os.makedirs(DEST, exist_ok=True)
    t0 = time.time()
    ok, err = fetch(t["token"], out, want)
    if ok:
        ent.update(size=os.path.getsize(out), sha256=sha_file(out), state="downloaded",
                   seconds=round(time.time() - t0, 1))
        print(f"  ✓ {t['token'][:20]} {ent['size']} 字节 sha={ent['sha256'][:16]}…（{ent['seconds']}s）", flush=True)
    else:
        ent.update(state="download_failed", error=err)
        print(f"  ✗ {t['token'][:20]} 失败：{err}", flush=True)
        if os.path.exists(out) and not want:
            os.remove(out)
    report.append(ent)

# ── 回写 media_refs（只改 media_path/sha256/sha256_state）──
if APPLY:
    byart = {}
    for e in report:
        byart.setdefault(e["artifact"], []).append(e)
    written = 0
    for art, ents in byart.items():
        d = json.load(open(art, encoding="utf-8"))
        changed = False
        for m in (d.get("media_refs") or []):
            if not isinstance(m, dict) or m.get("kind") != "video":
                continue
            for e in ents:
                if m.get("file_token") == e["token"] and e["state"] in ("downloaded", "already_local"):
                    m["media_path"] = f"{DEST}/{safe_name(e['token'], e['name'])}"
                    m["sha256"] = e["sha256"]
                    m["sha256_state"] = "downloaded"
                    m["downloaded_at"] = RUN
                    changed = True
                elif m.get("file_token") == e["token"] and e["state"] == "download_failed":
                    m["sha256_state"] = "download_failed"
                    m["download_error"] = e["error"]
                    changed = True
        if changed:
            tmp = art + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(d, fh, ensure_ascii=False, indent=1)
            json.load(open(tmp, encoding="utf-8"))
            os.replace(tmp, art)
            written += 1
    print(f"  [写入] 回写 media_refs：{written} 个产物")

ok_n = sum(1 for e in report if e["state"] in ("downloaded", "already_local"))
fail_n = sum(1 for e in report if e["state"] == "download_failed")
print(f"  小结：成功 {ok_n} ｜ 失败 {fail_n} ｜ 合计 {sum(e.get('size') or 0 for e in report)/1048576:.1f} MB")
json.dump({"run": RUN, "kind": "video_byte_fetch", "apply": APPLY, "as": AS_ID,
           "ok": ok_n, "failed": fail_n, "results": report},
          open(f"kb/l8/runs/{RUN}-video-fetch.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"  [报告] kb/l8/runs/{RUN}-video-fetch.json")
