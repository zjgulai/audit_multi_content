#!/usr/bin/env python3
"""把「被权限挡住」的 84 条 L0 资源逐条探明真实类型。

为什么需要它：
  L0 台账里这 84 条（`status_reason` 含 `drive:file:download`）只记了「读不了字节流」，
  没记「它到底是什么」。于是没法回答两个关键问题：
    ① 这里面有没有其实是**文档/表格/幻灯片**、用现有只读 scope 就能读的？
    ② 真的都是二进制附件的话，是哪些类型（PDF / 图片 / 表格文件…）？
  只有 ① 的答案是「有」，才值得再谈加权限；如果全是 ②，那结论就是
  「这 84 条按设计就不该进正文层」，而不是「我们漏了 84 篇内容」。

做法（全程只读，不下载任何字节流）：
  · `url:` 型（60 条）→ 飞书 wiki 节点，用 wiki +node-get 拿 obj_type / obj_token / title
  · `file:` 型（22 条）→ 已经是 file token，直接问云空间元数据
  · `wiki:` 型（2 条）→ resource_key 里存的是 obj_token，同样走元数据
  输出 kb/.work/blocked84-types.json，并把分布打屏。

用法：
  python3 kb/.work/probe-blocked84.py            # 用缓存（.blocked84.json + 本次结果）
  python3 kb/.work/probe-blocked84.py --refresh  # 重新探飞书
"""
import json
import os
import subprocess
import sys
import collections
import re

WORK = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(WORK, ".blocked84.json")
OUT = os.path.join(WORK, "blocked84-types.json")
LARK = os.path.expanduser("~/.dsh/bin/lark-cli")


def lark_json(args: list[str]) -> dict:
    """调 lark-cli，返回解析后的 JSON（失败也给一个带 ok=false 的壳，不抛）。"""
    try:
        out = subprocess.run([LARK, *args], capture_output=True, text=True, timeout=60).stdout
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": {"message": f"调用失败：{e}"}}
    try:
        return json.loads(out)
    except Exception:  # noqa: BLE001
        return {"ok": False, "error": {"message": f"非 JSON：{out[:120]}"}}


def node_info(url: str) -> dict:
    """wiki 节点 → obj_type / obj_token / title。"""
    d = lark_json(["wiki", "+node-get", "--node-token", url, "--as", "user", "--format", "json"])
    if not d.get("ok"):
        err = d.get("error") or {}
        return {"ok": False, "error": str(err.get("message") or err)[:160]}
    n = d.get("data") or d.get("node") or {}
    return {
        "ok": True,
        "obj_type": n.get("obj_type"),
        "obj_token": n.get("obj_token"),
        "title": n.get("title"),
    }


def drive_meta(token: str) -> dict:
    """云空间文件 token → 名字 / 类型 / 扩展名。"""
    d = lark_json([
        "api", "POST", "/open-apis/drive/v1/metas/batch_query", "--as", "user",
        "--data", json.dumps({"request_docs": [{"doc_token": token, "doc_type": "file"}], "with_url": False}),
    ])
    if not d.get("ok"):
        err = d.get("error") or {}
        return {"ok": False, "error": str(err.get("message") or err)[:160]}
    metas = ((d.get("data") or {}).get("metas") or [])
    if not metas:
        return {"ok": False, "error": "元数据为空（可能无权限）"}
    m = metas[0]
    return {"ok": True, "title": m.get("title"), "ext": m.get("file_ext") or m.get("ext"), "type": m.get("type")}


def classify(rec: dict) -> dict:
    """探一条被挡资源。"""
    key = rec.get("resource_key") or ""
    url = rec.get("entry_url") or ""
    kind = rec.get("source_kind")
    info = {"resource_key": key, "entry_url": url, "source_kind": kind, "path": rec.get("path"),
            "kb_type": rec.get("kb_type")}
    tenant = "hapa8fkuicz" if "hapa8fkuicz" in url else ("momcozy-in" if "momcozy-in" in url else "?")
    info["tenant"] = tenant

    file_token = None
    if kind == "url" or "/wiki/" in url:
        node = node_info(url)
        info["node"] = node
        if node.get("ok"):
            info["obj_type"] = node.get("obj_type")
            info["title"] = node.get("title")
            if node.get("obj_type") == "file":
                file_token = node.get("obj_token")
    if key.startswith("file:"):
        file_token = key.split(":", 1)[1]
    elif key.startswith("wiki:") and file_token is None:
        file_token = key.split(":", 1)[1]
    if file_token is None and "/file/" in url:
        file_token = url.rstrip("/").split("/")[-1]

    if file_token:
        info["file_token"] = file_token
        meta = drive_meta(file_token)
        info["file_meta"] = meta
        if meta.get("ok"):
            info.setdefault("title", meta.get("title"))
            info["ext"] = (meta.get("ext") or "").lower() or None
    info["obj_type"] = info.get("obj_type") or "file"
    return info


def main() -> int:
    refresh = "--refresh" in sys.argv
    recs = json.load(open(SRC, encoding="utf-8"))
    cache = {}
    if not refresh and os.path.isfile(OUT):
        cache = {r["resource_key"]: r for r in json.load(open(OUT, encoding="utf-8")).get("items", [])}

    items = []
    for i, rec in enumerate(recs, 1):
        key = rec.get("resource_key") or ""
        if key in cache and cache[key].get("file_meta", {}).get("ok"):
            items.append(cache[key])
            continue
        r = classify(rec)
        items.append(r)
        flag = "✓" if r.get("file_meta", {}).get("ok") else "·"
        print(f"  [{i:2}/{len(recs)}] {flag} {r.get('obj_type'):5} {str(r.get('ext') or '-'):6} "
              f"{str(r.get('title'))[:44]}", flush=True)

    json.dump({"probed_at": __import__("datetime").date.today().isoformat(), "total": len(items),
               "items": items}, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    def dist(field):
        return collections.Counter(str(r.get(field)) for r in items).most_common()

    print(f"\n{'='*66}\n共 {len(items)} 条\n")
    print("按 obj_type（飞书里的真实对象类型）")
    for k, v in dist("obj_type"):
        print(f"  {v:4}  {k}")
    print("\n按租户")
    for k, v in dist("tenant"):
        print(f"  {v:4}  {k}")
    print("\n按扩展名（元数据可读的）")
    for k, v in dist("ext"):
        print(f"  {v:4}  {k}")
    print("\n按会进哪个子库（kb_type）")
    for k, v in dist("kb_type"):
        print(f"  {v:4}  {k}")
    print("\n按 L0 登记路径")
    for k, v in collections.Counter(str(r.get("path"))[:52] for r in items).most_common():
        print(f"  {v:4}  {k}")
    ok_meta = sum(1 for r in items if r.get("file_meta", {}).get("ok"))
    print(f"\n元数据（标题/类型）现在读得到：{ok_meta}/{len(items)}")
    print(f"字节流仍需 drive:file:download（按你的决定**未申请**）：{len(items)}/{len(items)}")
    print(f"输出：{OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
