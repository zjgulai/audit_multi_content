---
id: cg-vid-4f3ab8ba5f7ea926
title: "[VID-I4H1bS4M] 视频画面文字与口播：FD162D27-BD92-479B-B306-7B4121D2BC07.mp4"
collection: 2_内部正负样本库
kb_class: [内部正负样本库]
tier: L1
topic: I4H1bS4Mso6M
kind: fact
summary: "https://momcozy-in.feishu.cn/wiki/A0fxdtmKxoQbmAxmpXVce7SVnEd 内嵌视频「FD162D27-BD92-479B-B306-7B4121D2BC07.mp4」：画面文字 5 段 / 68 字（带 `#t.` 时间码，时长 148.43s）＋口播转写 551 字（本机 ASR，**无时间码**）"
owner: 刘华丽
evidence_level: L1
data_level: L2
sensitivity_level: L2
half_life_days: 180
created_at: 2026-10-16
valid_until: 2027-04-14
asks:
  - 这条视频（FD162D27-BD92-479B-B306-7B4121D2BC07.mp4）画面里出现了哪些文字
  - 某个时间点画面上写的是什么
  - 这条视频（FD162D27-BD92-479B-B306-7B4121D2BC07.mp4）口播说了什么
  - 画面文字与口播是否一致
not_proves: "画面文字只覆盖**画面上出现的字**，口播转写只覆盖**音轨里说的话** —— 两者都**不含画面内容判定**（婴幼儿安全、产品用法、隐私等画面风险走「视频安全审查」）；**口播转写没有逐句时间码**，不能按时间定位，且 ASR 可能误识别、不能当逐字原文引用；不能证明时效（视频可能已改版）；不能证明该条已过正式验收；不能替代合规/法务意见"
forbidden: "不许把画面文字当口播转写用（反之亦然）；不许把口播转写当逐字原文引用（ASR 有误识别，`script_mismatch` 时尤其）；不许据本条直接判 BLOCK/PASS；不许把派生视图的字段改动当成新库改动（视图不写回）"
---

# 视频画面文字与口播转写：FD162D27-BD92-479B-B306-7B4121D2BC07.mp4

- 所属材料：wiki:A0fxdtmKxoQbmAxmpXVce7SVnEd
- 材料地址：https://momcozy-in.feishu.cn/wiki/A0fxdtmKxoQbmAxmpXVce7SVnEd
- 视频文件：kb/l0/attachments/视频/I4H1bS4Mso6M0oxO__FD162D27-BD92-479B-B306-7B4121D2BC07.mp4
- 时长 148.43s ｜ 1080×1920 ｜ hevc
- 抽取方式：`ffmpeg(scene)+macOS Vision`（13 帧 → 5 段画面文字）

## 画面文字（按时间窗，锚点可回源）

- `#t.00:01:00-00:01:11`　KYWAI pyre
- `#t.00:01:11-00:01:12`　MIN
- `#t.00:01:12-00:01:16`　romer*
- `#t.00:01:16-00:01:31`　٠٤ة فقوم COCIN-
- `#t.00:01:57-00:02:13`　Mave Alm Adds Het wich Sassy Style

## 口播转写（本机 ASR）

- 语种 `en-US` ｜ 551 字 ｜ `macOS Speech.framework（本机、on-device）`
- 语种判读：画面文字判读：汉字 0 / 拉丁字母 50 ⇒ **英文优先**（语序 en-US → zh-CN）

When I'm just trying to take care of both of my kids and my house and I have so many things going on all at once speaking of being a mama of two I have to mention the cleanup there are only five washable parts after use five that means one less thing for me to worry about if you're a pumping mama you know that one of the downsides to pumping is having to wash all of the parts so it honestly is such a relief knowing that doesn't take that long if you're interested in the mom cozy wellness one the link will be in my bio so feel free to go check it

> **口播转写**由 `macOS Speech.framework` **本机**完成（on-device、不出机器），
> **没有逐句时间码** —— 不能按时间定位；ASR 可能误识别，不能当逐字原文引用。
> **画面文字**那半**有** `#t.` 时间码，可定位到秒。案例只作参照，不构成规则。