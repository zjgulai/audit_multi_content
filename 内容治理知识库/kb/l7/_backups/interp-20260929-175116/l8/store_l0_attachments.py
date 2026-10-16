#!/usr/bin/env python3
"""把图片附件字节落到 L0（用户 2026-09-29 口径：OCR 后图片可留在 L0 层）。

结构：
  kb/l0/attachments/<表名>/<record_id>/<file_token>.<ext>
  kb/l0/attachments/_MANIFEST.json     每张：表/记录/字段/token/原名/字节/sha256/落盘路径
  kb/l0/attachments/README.md          定位说明（只作留档与复算；L1+ 读 OCR 文本）
台账：为该批附件追加 sha256_input=file_bytes 的行（此前是 attachment_metadata/metadata_only），
      并带 bytes / local_path —— 让「字节级指纹」名副其实。

身份：bot（守衡）—— 附件下载权限在应用侧。
用法：python3 kb/l8/store_l0_attachments.py 20260929-1740 [--apply]
"""
import hashlib
import json
import os
import subprocess
import sys

RUN = sys.argv[1] if len(sys.argv) > 1 else "20260929-1740"
APPLY = "--apply" in sys.argv
AS_ID, PROFILE = os.environ.get("L8_AS", "bot"), os.environ.get("L8_PROFILE", "dsh-kb")
ENV = dict(os.environ, PATH=os.path.expanduser("~/.dsh/bin") + ":" + os.environ.get("PATH", ""))
BASE, TABLE, TNAME, FID, FNAME = ("GnRZbIuXraCzf0sGr2UcmZ62nfc", "tbld8qE92YaY38Yz", "负面样本",
                                  "fldnvxjaSr", "图片素材")
ROOT = "kb/l0/attachments"

lat = {}
for line in open("kb/l0/manifest.jsonl", encoding="utf-8"):
    if line.strip():
        r = json.loads(line)
        lat[r["resource_key"]] = r
targets = [(k, v) for k, v in lat.items()
           if v["source_kind"] == "feishu_attachment" and v.get("table_id") == TABLE
           and v["status"] not in ("gone", "retracted")]
print(f"待落盘附件行：{len(targets)}")

os.makedirs(ROOT, exist_ok=True)
manifest, rows = [], []
ok = 0
for key, row in sorted(targets):
    tok = key.rsplit("/", 1)[-1]
    rid = row.get("record_id")
    ext = os.path.splitext((row.get("path") or "").split("/")[-1])[1] or ".png"
    name = row.get("status_reason") or ""
    dst_dir = f"{ROOT}/{TNAME}/{rid}"
    dst = f"{dst_dir}/{tok}.png"
    if not (os.path.exists(dst) and os.path.getsize(dst) > 0):
        os.makedirs(dst_dir, exist_ok=True)
        for _ in range(3):
            p = subprocess.run(["lark-cli", "base", "+record-download-attachment", "--base-token", BASE,
                                "--table-id", TABLE, "--record-id", rid, "--file-token", tok,
                                "--output", dst, "--overwrite", "--as", AS_ID, "--profile", PROFILE],
                               capture_output=True, text=True, encoding="utf-8", errors="replace",
                               env=ENV, timeout=300)
            if os.path.exists(dst) and os.path.getsize(dst) > 0:
                break
    if not (os.path.exists(dst) and os.path.getsize(dst) > 0):
        print(f"  ✗ 下载失败 {rid} {tok}")
        continue
    ok += 1
    b = open(dst, "rb").read()
    h = hashlib.sha256(b).hexdigest()
    manifest.append({"resource_key": key, "table": TNAME, "record_id": rid, "field": FNAME,
                     "field_id": FID, "file_token": tok, "bytes": len(b), "sha256": h,
                     "local_path": dst})
    n = dict(row)
    n.update({"sha256": h, "sha256_input": "file_bytes", "sha256_state": "full",
              "bytes": len(b), "local_path": dst, "observed_at": RUN,
              "change": "l0_attachment_bytes_stored",
              "status_reason": "字节已落 L0（用户口径 2026-09-29：OCR 后图片留 L0 作留档与复算）"})
    rows.append(n)

print(f"下载成功 {ok}/{len(targets)}")
if APPLY:
    json.dump({"run": RUN, "table": TNAME, "field": FNAME, "identity": f"{AS_ID}/{PROFILE}",
               "root": ROOT, "count": len(manifest),
               "total_bytes": sum(m["bytes"] for m in manifest),
               "policy": "L0 附件字节副本：只作留档与复算（OCR 重跑）；L1+ 一律读 OCR 文本，不读这里",
               "files": manifest},
              open(f"{ROOT}/_MANIFEST.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    with open(f"{ROOT}/README.md", "w", encoding="utf-8") as fh:
        fh.write(f"""# kb/l0/attachments —— 飞书附件字节副本

- 来源：飞书 Base `{BASE}` 表 `{TNAME}`（{TABLE}）字段 `{FNAME}`（{FID}）
- 结构：`<表名>/<record_id>/<file_token>.png`（文件名=file_token，天然去重且可回源核对）
- 台账：`_MANIFEST.json`；`kb/l0/manifest.jsonl` 里对应行已升级为 `sha256_input=file_bytes`
- 用途：**留档与复算**（OCR 引擎/参数升级时可重跑，无需回源、不受权限变动影响）；审计时看原图
- 边界：**L1 及以上一律读 OCR 文本**，不要读这里的图片；本目录不是知识条目，不参与加载器扫描
- 落盘批：{RUN}（{len(manifest)} 张 / {sum(m['bytes'] for m in manifest)/1048576:.1f} MB）
""")
    with open("kb/l0/manifest.jsonl", "a", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
    reg_p = "kb/l0/registry/kb.json"
    reg = json.load(open(reg_p, encoding="utf-8"))
    reg["attachment_store"] = {
        "layout": f"{ROOT}/<表名>/<record_id>/<file_token>.<ext>",
        "manifest": f"{ROOT}/_MANIFEST.json",
        "policy": "字节副本用于留档与复算；L1+ 读 OCR 文本；不属于知识条目，不参与加载器扫描",
        "registered_at": RUN, "count": len(manifest),
        "ledger_upgrade": "附件行 sha256_input: attachment_metadata → file_bytes（补 bytes/local_path）",
    }
    json.dump(reg, open(reg_p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"已写 _MANIFEST.json / README.md / 台账 +{len(rows)} 行 / registry.attachment_store")
else:
    print("未写入（加 --apply）")
