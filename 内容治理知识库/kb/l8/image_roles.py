#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""image_roles.py —— **图片归属角色**（2026-10-20；「串图」修复 ② 的判据真源）

## 为什么要有它（真单事故，2026-10-20）

用户把飞书表里的一张 Giveaway 长图转发给守衡，守衡回了一条「依据 N-1.39 → 原始出处
`record=recvwC9IMVHb0Q`」。点开那条记录，看到的是**美国 BJs 渠道图**，建议也是讲渠道认知的。

病灶不在匹配层（同图判据是对的：8 个长短语全中），而在**归属**：

  · 一条负面样本记录的 `图片素材` 字段常常装**多组图**；
  · 同一张图还会被**复制挂到多条内容不同的记录**里（实测那张长图挂在 7 条记录上）；
  · L3 把该记录的**全部**图片挂到该记录的**每一条**规则上 ⇒ 「图」与「意见」之间
    在数据结构里**没有对应关系**。

⇒ 任何“这张图出现在这条记录里 ⇒ 引用这条记录的意见”的判据，必然串图。

## 判据（最小版，可机械复算；不靠模型、不靠人工标注）

对每条现存记录 R 的每张图 I（**按字节 sha 去重**后）：

  subject           同时满足两条才算：
                      ① R 去重后**只剩 1 张图**（多张图 ⇒ 无法把某段意见归到某一张）；
                      ② I 的 sha 没有出现在**内容不同**的其它记录里
                         （“内容相同”= `原文反馈` 归一化后逐字相等 ⇒ 同一条素材的多世代，
                           算**同一份**，不算跨记录共享 —— 实测源侧「整体换血」留下了大量
                           `recvw2vgYX*` / `recvw2wE9M*` 同内容成对记录，不归并会把 96% 判成不可归属）
  record_level      ① 不成立（多图记录）⇒ 这条记录的意见**不能**归属到某一确保图片
  shared_reference  ② 不成立（该图出现在内容不同的多条记录里）⇒ 复用附图 / 复制污染
  unknown           拿不到 sha（无媒体台账）⇒ **不放行**（保守：不许拿未知当 subject）

**方向是不对称的**：这张尺子只用来**抑制引用**（非 subject ⇒ 不得作为“这张图的依据”），
不反过来证明“这张图没问题”。抑制方向保守过头只是少报；把 unknown 放行才会造假依据。

## 用法

    python3 kb/l8/image_roles.py                 # 预演：只打普查数字，不落盘
    python3 kb/l8/image_roles.py --apply         # 写 kb/l3/registry/image_roles.json
    python3 kb/l8/image_roles.py --selftest      # 判据自证（含反向对照）

产物是**生成物**（不是手写登记件），随 L0/L1 变化重新生成即可；下游（匹配层 / 评审链）
只读产物，不自己算归属。
"""
import json
import os
import re
import sys
import hashlib
import glob
import datetime

TABLE_ID = "tbld8qE92YaY38Yz"
L0_RECORDS = "kb/l0/records/负面样本"
L1_MEDIA = "kb/l1/2_内部正负样本库"
L0_MANIFEST = "kb/l0/manifest.jsonl"
OUT = "kb/l3/registry/image_roles.json"

SUBJECT, RECORD_LEVEL, SHARED, UNKNOWN = "subject", "record_level", "shared_reference", "unknown"


# ── 归一化：只用于**判同一条素材的多世代**，不参与检索打分 ────────────────────
def norm_text(s):
    s = re.sub(r"\s+", "", str(s or ""))
    return s


def content_key(fields):
    """记录内容键：优先 `原文反馈`（项目方原话，最能代表“这是哪一件素材的评审”）。

    退化链：原文反馈 → 具体原因/分析 + 建议 → 记录 id（必然唯一 ⇒ 不会被误归并）。
    """
    for name in ("原文反馈",):
        v = fields.get(name) or {}
        t = norm_text((v or {}).get("value") if isinstance(v, dict) else v)
        if len(t) >= 40:
            return "fb:" + hashlib.sha256(t.encode("utf-8")).hexdigest()[:16]
    parts = []
    for name in ("具体原因/分析", "建议"):
        v = fields.get(name) or {}
        t = norm_text((v or {}).get("value") if isinstance(v, dict) else v)
        if t:
            parts.append(t)
    if parts:
        return "ra:" + hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]
    return None                                     # 内容取不到 ⇒ 不归并（保守：各算一世）


def _sha_map():
    """token → sha256。两个来源合并（L1 媒体台账优先，L0 附件登记兜底）。

    为什么要两源：184 条现存记录里只有 127 条有 L1 媒体件；只读 L1 会让其余记录的图
    落进 `unknown` ⇒ 整层被抑制。L0 附件登记（`sha256_input=file_bytes`）是同一把尺子的
    另一处落盘，合并没有放宽任何判据。
    """
    out = {}
    for p in sorted(glob.glob(os.path.join(L1_MEDIA, "media_%s_*.json" % TABLE_ID))):
        try:
            d = json.load(open(p, encoding="utf-8"))
        except Exception:                            # noqa: BLE001 —— 坏件跳过，不拖死普查
            continue
        for m in (d.get("media_refs") or []):
            tok, sha = m.get("file_token"), m.get("sha256")
            if tok and sha:
                out[tok] = {"sha256": sha, "seq": m.get("seq"), "bytes": m.get("bytes"),
                            "anchor": m.get("anchor"), "from": "l1_media"}
    if os.path.exists(L0_MANIFEST):
        for line in open(L0_MANIFEST, encoding="utf-8"):
            if not line.strip():
                continue
            try:
                d = json.loads(line)
            except Exception:                        # noqa: BLE001
                continue
            if d.get("source_kind") != "feishu_attachment" or d.get("table_id") != TABLE_ID:
                continue
            if d.get("status") in ("gone", "retracted") or not d.get("sha256"):
                continue
            tok = (d.get("resource_key") or "").rsplit("/", 1)[-1]
            if tok and tok not in out:
                out[tok] = {"sha256": d["sha256"], "seq": None,
                            "bytes": (d.get("extra") or {}).get("size"),
                            "anchor": (d.get("extra") or {}).get("anchor"), "from": "l0_attachment"}
    return out


def load_records():
    """现存负面样本记录（L0 `records/负面样本/*.json`，只取 `status` 未标 gone 的）。"""
    out = {}
    for p in sorted(glob.glob(os.path.join(L0_RECORDS, "*.json"))):
        try:
            d = json.load(open(p, encoding="utf-8"))
        except Exception:                            # noqa: BLE001
            continue
        if str(d.get("status") or "").lower() in ("gone", "retracted"):
            continue
        rid = d.get("record_id") or os.path.splitext(os.path.basename(p))[0]
        out[rid] = d
    return out


def build(records=None, sha_map=None):
    records = records if records is not None else load_records()
    sha_map = sha_map if sha_map is not None else _sha_map()

    prof = {}
    for rid, doc in records.items():
        fields = doc.get("fields") or {}
        atts = (fields.get("图片素材") or {}).get("value") or []
        imgs, seen_raw = [], 0
        for a in atts:
            if not isinstance(a, dict):
                continue
            seen_raw += 1
            tok = a.get("file_token")
            meta = sha_map.get(tok) or {}
            imgs.append({"token": tok, "name": a.get("name"), "size": a.get("size"),
                         "sha256": meta.get("sha256"), "seq": meta.get("seq"),
                         "anchor": meta.get("anchor") or ("#素材/%s/图片素材/#img.%d" % (rid, seen_raw)),
                         "from": meta.get("from")})
        # 按字节 sha 去重（同一条记录里同一张图挂两遍是实测存在的：recvwC9IMVHb0Q 的 s3_1/s3_2）
        ded, seen_sha = [], set()
        for im in imgs:
            s = im.get("sha256")
            if s:
                if s in seen_sha:
                    continue
                seen_sha.add(s)
            ded.append(im)
        prof[rid] = {"record_id": rid, "content_key": content_key(fields),
                     "n_raw": seen_raw, "n_dedup": len(ded), "images": ded,
                     "title": ((fields.get("具体原因/分析") or {}).get("value") or "")[:60]}

    # sha → 出现过的「内容世代」集合
    sha_gens = {}
    for rid, p in prof.items():
        gen = p["content_key"] or ("rec:" + rid)
        p["generation"] = gen
        for im in p["images"]:
            s = im.get("sha256")
            if not s:
                continue
            sha_gens.setdefault(s, set()).add(gen)
    sha_recs = {}
    for rid, p in prof.items():
        for im in p["images"]:
            if im.get("sha256"):
                sha_recs.setdefault(im["sha256"], set()).add(rid)

    # 逐图定角色
    for rid, p in prof.items():
        for im in p["images"]:
            s = im.get("sha256")
            if not s:
                im["role"], im["why"] = UNKNOWN, "没有媒体台账 sha（不放行）"
                continue
            gens = sha_gens.get(s) or set()
            if len(gens) > 1:
                im["role"] = SHARED
                im["why"] = ("同一张图出现在 %d 条**内容不同**的记录里（%s）⇒ 复用附图/复制污染，"
                             "不得作为任何一条记录的意见依据"
                             % (len(sha_recs.get(s) or ()), ", ".join(sorted(sha_recs.get(s) or ())[:4])))
                continue
            if p["n_dedup"] > 1:
                im["role"] = RECORD_LEVEL
                im["why"] = ("该记录去重后有 %d 张图 ⇒ 记录里的意见无法归属到这一张"
                             % p["n_dedup"])
                continue
            im["role"] = SUBJECT
            im["why"] = "该记录去重后仅此 1 张图，且该图未出现在其它内容不同的记录里"

    stats = {"records": len(prof),
             "records_with_images": sum(1 for p in prof.values() if p["images"]),
             "records_multi_image": sum(1 for p in prof.values() if p["n_dedup"] > 1),
             "records_single_image": sum(1 for p in prof.values() if p["n_dedup"] == 1),
             "images_raw": sum(p["n_raw"] for p in prof.values()),
             "images_dedup": sum(len(p["images"]) for p in prof.values()),
             "by_role": {}}
    for p in prof.values():
        for im in p["images"]:
            stats["by_role"][im["role"]] = stats["by_role"].get(im["role"], 0) + 1
    # 「可引用」= 记录层面至少有一张 subject 图（匹配层命中它的图才允许当图级依据）
    stats["records_with_subject_image"] = sum(
        1 for p in prof.values() if any(im["role"] == SUBJECT for im in p["images"]))
    stats["shared_images"] = sum(1 for s, g in sha_gens.items() if len(g) > 1)
    return {"generated_at": datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            "table_id": TABLE_ID,
            "judge": {
                "subject": "记录去重后仅 1 张图 ∧ 该图 sha 未出现在内容不同的其它记录里",
                "record_level": "记录去重后 >1 张图 ⇒ 意见不能归属到某一确保图片",
                "shared_reference": "该图 sha 出现在内容不同的 ≥2 条记录里",
                "unknown": "拿不到 sha ⇒ 不放行",
                "generation_merge": "「原文反馈」归一化后逐字相等 ⇒ 同一条素材的多世代，算同一份",
                "direction": "只用于**抑制**引用；不放行等于少报，不等于通过",
            },
            "stats": stats, "records": prof}


def load_roles(path=OUT):
    """给下游用：返回 {'records':…, 'sha':…, 'stats':…}；文件不存在 ⇒ 空（调用方保守处理）。"""
    if not os.path.exists(path):
        return {"records": {}, "sha": {}, "stats": {}, "missing": True}
    d = json.load(open(path, encoding="utf-8"))
    sha = {}
    for rid, p in (d.get("records") or {}).items():
        for im in p.get("images") or []:
            if im.get("sha256"):
                sha.setdefault(im["sha256"], im.get("role") or UNKNOWN)
    d["sha"] = sha
    return d


def role_of_image(roles, record_id, sha256):
    """某条记录里某张图的角色。取不到 ⇒ unknown（保守）。"""
    p = ((roles.get("records") or {}).get(record_id) or {})
    for im in (p.get("images") or []):
        if sha256 and im.get("sha256") == sha256:
            return im.get("role") or UNKNOWN
    if sha256 and (roles.get("sha") or {}).get(sha256):
        return roles["sha"][sha256]
    return UNKNOWN


def role_of_record(roles, record_id):
    """记录整体能否引用：只有在它有 subject 图时才返回 subject，否则按最常见角色给。"""
    p = ((roles.get("records") or {}).get(record_id) or {})
    if not p:
        return UNKNOWN
    imgs = p.get("images") or []
    if not imgs:
        return UNKNOWN
    if any(im.get("role") == SUBJECT for im in imgs):
        return SUBJECT
    for r in (SHARED, RECORD_LEVEL, UNKNOWN):
        if any(im.get("role") == r for im in imgs):
            return r
    return UNKNOWN


# ── 判据自证 ────────────────────────────────────────────────────────────────
def _mk(rid, tokens, fb, sha_by_tok):
    imgs = [{"file_token": t, "name": t + ".png", "size": 1} for t in tokens]
    return {"record_id": rid, "status": "registered",
            "fields": {"原文反馈": {"value": fb}, "图片素材": {"value": imgs}}}


def selftest():
    cases = []
    sha = {"t_a": {"sha256": "sha_A"}, "t_b": {"sha256": "sha_B"},
           "t_c": {"sha256": "sha_C"}, "t_a2": {"sha256": "sha_A"}}
    # ① 单图 + 独占 ⇒ subject
    recs = {"r1": _mk("r1", ["t_a"], "素材甲 项目方原话 " * 5, sha)}
    d = build(recs, sha)
    cases.append(("① 单图独占 ⇒ subject",
                  d["records"]["r1"]["images"][0]["role"] == SUBJECT, d["stats"]["by_role"]))
    # ② 多图 ⇒ record_level（哪怕图都独占）
    recs = {"r1": _mk("r1", ["t_a", "t_b"], "素材甲 项目方原话 " * 5, sha)}
    d = build(recs, sha)
    cases.append(("② 多图记录 ⇒ record_level",
                  d["records"]["r1"]["images"][0]["role"] == RECORD_LEVEL, d["stats"]["by_role"]))
    # ③ 同一张图跨两条**内容不同**的记录 ⇒ shared_reference（两边都不可引用）
    recs = {"r1": _mk("r1", ["t_a"], "素材甲 项目方原话 " * 5, sha),
            "r2": _mk("r2", ["t_a2"], "素材乙 另一件完全不同的评审 " * 5, sha)}
    d = build(recs, sha)
    cases.append(("③ 跨内容记录共享 ⇒ shared_reference（两条都是）",
                  all(d["records"][r]["images"][0]["role"] == SHARED for r in ("r1", "r2")),
                  d["stats"]["by_role"]))
    # ④ 反向对照：同一张图跨两条**内容相同**的记录（整体换血的多世代）⇒ 仍可 subject
    recs = {"r1": _mk("r1", ["t_a"], "素材甲 项目方原话 " * 5, sha),
            "r2": _mk("r2", ["t_a2"], "素材甲 项目方原话 " * 5, sha)}
    d = build(recs, sha)
    cases.append(("④ 反向对照：同内容多世代不算共享 ⇒ subject",
                  all(d["records"][r]["images"][0]["role"] == SUBJECT for r in ("r1", "r2")),
                  d["stats"]["by_role"]))
    # ⑤ 拿不到 sha ⇒ unknown（不放行）
    recs = {"r1": _mk("r1", ["t_zz"], "素材甲 项目方原话 " * 5, sha)}
    d = build(recs, sha)
    cases.append(("⑤ 无 sha ⇒ unknown（不放行）",
                  d["records"]["r1"]["images"][0]["role"] == UNKNOWN, d["stats"]["by_role"]))
    # ⑥ 同记录内同一张图挂两遍 ⇒ 去重后单图仍 subject（实测 recvwC9IMVHb0Q 的形态）
    recs = {"r1": _mk("r1", ["t_a", "t_a2"], "素材甲 项目方原话 " * 5, sha)}
    d = build(recs, sha)
    cases.append(("⑥ 同记录内同图重复 ⇒ 去重后单图 ⇒ subject",
                  d["records"]["r1"]["images"][0]["role"] == SUBJECT
                  and d["records"]["r1"]["n_raw"] == 2 and d["records"]["r1"]["n_dedup"] == 1,
                  (d["records"]["r1"]["n_raw"], d["records"]["r1"]["n_dedup"])))
    # ⑦ 多图 + 其中一张跨记录共享 ⇒ 该张 shared、另一张 record_level（不是 subject）
    sha2 = dict(sha, t_d={"sha256": "sha_D"})
    recs = {"r1": _mk("r1", ["t_a", "t_d"], "素材甲 项目方原话 " * 5, sha2),
            "r2": _mk("r2", ["t_a2"], "素材乙 另一件完全不同的评审 " * 5, sha2)}
    d = build(recs, sha2)
    roles = {im["sha256"]: im["role"] for im in d["records"]["r1"]["images"]}
    cases.append(("⑦ 多图记录里跨记录共享的那张 ⇒ shared_reference（优先级高于 record_level）",
                  roles.get("sha_A") == SHARED and roles.get("sha_D") == RECORD_LEVEL, roles))
    ok = all(c[1] for c in cases)
    for name, okc, detail in cases:
        print(("  ✅ " if okc else "  ❌ ") + name + ("" if okc else "  ← " + str(detail)))
    print("image_roles selftest %s（%d/%d）" % ("PASS" if ok else "FAIL",
                                               sum(1 for c in cases if c[1]), len(cases)))
    return 0 if ok else 3


def main(argv):
    if "--selftest" in argv:
        return selftest()
    d = build()
    st = d["stats"]
    print(json.dumps(st, ensure_ascii=False, indent=1))
    # 最烫的共享图（同一张图挂最多记录）
    hot = []
    for rid, p in d["records"].items():
        for im in p["images"]:
            if im["role"] == SHARED:
                hot.append((im["why"], rid, (im.get("sha256") or "")[:10], im.get("token")))
    print("\n跨内容共享图（前 6 条，逐条可回源）：")
    for why, rid, s, tok in hot[:6]:
        print("  - %s | rec=%s | sha=%s | tok=%s" % (why[:96], rid, s, tok))
    if "--apply" in argv:
        os.makedirs(os.path.dirname(OUT), exist_ok=True)
        with open(OUT, "w", encoding="utf-8") as fh:
            json.dump(d, fh, ensure_ascii=False, indent=1)
        print("\n已写 %s（%d bytes）" % (OUT, os.path.getsize(OUT)))
    else:
        print("\n（预演：未落盘；加 --apply 才写 %s）" % OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
