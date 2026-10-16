---
id: cg-vid-5d9073b93ebf32cb
title: "[VID-VrvHb94r] 视频画面文字与口播：404237E1-A1A8-4EC8-A809-DB3881502F29.mp4"
collection: 2_内部正负样本库
kb_class: [内部正负样本库]
tier: L1
topic: VrvHb94rpopF
kind: fact
summary: "https://momcozy-in.feishu.cn/wiki/A0fxdtmKxoQbmAxmpXVce7SVnEd 内嵌视频「404237E1-A1A8-4EC8-A809-DB3881502F29.mp4」：画面文字 10 段 / 231 字（带 `#t.` 时间码，时长 153.13s）＋口播转写 327 字（本机 ASR，**无时间码**）"
owner: 刘华丽
evidence_level: L1
data_level: L2
sensitivity_level: L2
half_life_days: 180
created_at: 2026-10-16
valid_until: 2027-04-14
asks:
  - 这条视频（404237E1-A1A8-4EC8-A809-DB3881502F29.mp4）画面里出现了哪些文字
  - 某个时间点画面上写的是什么
  - 这条视频（404237E1-A1A8-4EC8-A809-DB3881502F29.mp4）口播说了什么
  - 画面文字与口播是否一致
not_proves: "画面文字只覆盖**画面上出现的字**，口播转写只覆盖**音轨里说的话** —— 两者都**不含画面内容判定**（婴幼儿安全、产品用法、隐私等画面风险走「视频安全审查」）；**口播转写没有逐句时间码**，不能按时间定位，且 ASR 可能误识别、不能当逐字原文引用；不能证明时效（视频可能已改版）；不能证明该条已过正式验收；不能替代合规/法务意见"
forbidden: "不许把画面文字当口播转写用（反之亦然）；不许把口播转写当逐字原文引用（ASR 有误识别，`script_mismatch` 时尤其）；不许据本条直接判 BLOCK/PASS；不许把派生视图的字段改动当成新库改动（视图不写回）"
---

# 视频画面文字与口播转写：404237E1-A1A8-4EC8-A809-DB3881502F29.mp4

- 所属材料：wiki:A0fxdtmKxoQbmAxmpXVce7SVnEd
- 材料地址：https://momcozy-in.feishu.cn/wiki/A0fxdtmKxoQbmAxmpXVce7SVnEd
- 视频文件：kb/l0/attachments/视频/VrvHb94rpopFnPxm__404237E1-A1A8-4EC8-A809-DB3881502F29.mp4
- 时长 153.13s ｜ 1080×1920 ｜ hevc
- 抽取方式：`ffmpeg(scene)+macOS Vision`（13 帧 → 10 段画面文字）

## 画面文字（按时间窗，锚点可回源）

- `#t.00:00:17-00:00:30`　¿mamajodieee DRAFT
- `#t.00:00:30-00:00:36`　@mamajodieee DRAFT
- `#t.00:00:36-00:01:40`　Gmamajodieee DRAFT
- `#t.00:00:55-00:01:09`　(mamajodieee DRAFT
- `#t.00:01:09-00:01:50`　Smamajodieee DRAFT
- `#t.00:01:19-00:01:33`　KYWAI Amamajodiece DRAFT Pyre!
- `#t.00:01:40-00:01:47`　Gmamajodieee DRAF
- `#t.00:01:50-00:02:10`　KYWAI Smamajodieee DRAFT РУГа
- `#t.00:02:13-00:02:29`　Gmamajodiece DRAFT
- `#t.00:02:29-00:02:30`　Gmamajodiece DRAFT ACAS BUEN •CRECENA AQUI 0089

## 口播转写（本机 ASR）

- 语种 `en-US` ｜ 327 字 ｜ `macOS Speech.framework（本机、on-device）`
- 语种判读：画面文字判读：汉字 0 / 拉丁字母 199 ⇒ **英文优先**（语序 en-US → zh-CN）

At this stage of my life I don't need pumping to be one more thing that makes my day harder I need something that fits into my life and that's exactly why the mom cozy wellness one has been such a good fit for me let me know in the comments if you guys have any questions about the product I'd be more than happy to answer them

> **口播转写**由 `macOS Speech.framework` **本机**完成（on-device、不出机器），
> **没有逐句时间码** —— 不能按时间定位；ASR 可能误识别，不能当逐字原文引用。
> **画面文字**那半**有** `#t.` 时间码，可定位到秒。案例只作参照，不构成规则。