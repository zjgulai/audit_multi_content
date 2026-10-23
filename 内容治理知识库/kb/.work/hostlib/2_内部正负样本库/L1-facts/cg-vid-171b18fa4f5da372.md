---
id: cg-vid-171b18fa4f5da372
title: "[VID-Oe5GbcvB] 视频画面文字与口播：WhatsApp Video 2026-09-19 at 04.27.57.mp4"
collection: 2_内部正负样本库
kb_class: [内部正负样本库]
tier: L1
topic: Oe5GbcvBwoLQ
kind: fact
summary: "https://momcozy-in.feishu.cn/wiki/YNnwdkTULoJLccxKnypcHwsinBZ 内嵌视频「WhatsApp Video 2026-09-19 at 04.27.57.mp4」：画面文字 10 段 / 231 字（带 `#t.` 时间码，时长 99.84s）＋口播转写 795 字（本机 ASR，**无时间码**）"
owner: 刘华丽
evidence_level: L1
data_level: L2
sensitivity_level: L2
half_life_days: 180
created_at: 2026-10-22
valid_until: 2027-04-20
asks:
  - 这条视频（WhatsApp Video 2026-09-19 at 04.27.57.mp4）画面里出现了哪些文字
  - 某个时间点画面上写的是什么
  - 这条视频（WhatsApp Video 2026-09-19 at 04.27.57.mp4）口播说了什么
  - 画面文字与口播是否一致
not_proves: "画面文字只覆盖**画面上出现的字**，口播转写只覆盖**音轨里说的话** —— 两者都**不含画面内容判定**（婴幼儿安全、产品用法、隐私等画面风险走「视频安全审查」）；**口播转写没有逐句时间码**，不能按时间定位，且 ASR 可能误识别、不能当逐字原文引用；不能证明时效（视频可能已改版）；不能证明该条已过正式验收；不能替代合规/法务意见"
forbidden: "不许把画面文字当口播转写用（反之亦然）；不许把口播转写当逐字原文引用（ASR 有误识别，`script_mismatch` 时尤其）；不许据本条直接判 BLOCK/PASS；不许把派生视图的字段改动当成新库改动（视图不写回）"
---

# 视频画面文字与口播转写：WhatsApp Video 2026-09-19 at 04.27.57.mp4

- 所属材料：wiki:YNnwdkTULoJLccxKnypcHwsinBZ
- 材料地址：https://momcozy-in.feishu.cn/wiki/YNnwdkTULoJLccxKnypcHwsinBZ
- 视频文件：kb/l0/attachments/视频/Oe5GbcvBwoLQCKxR__WhatsApp_Video_2026-09-19_at_04.27.57.mp4
- 时长 99.84s ｜ 464×832 ｜ h264
- 抽取方式：`ffmpeg(scene)+macOS Vision`（30 帧 → 10 段画面文字）

## 画面文字（按时间窗，锚点可回源）

- `#t.00:00:04-00:00:05`　zy IS 1 e ufy s2
- `#t.00:00:34-00:00:36`　3419
- `#t.00:00:41-00:00:47`　5-Zone Suction-Synced Massage
- `#t.00:00:56-00:01:02`　Dou
- `#t.00:01:07-00:01:11`　180- 6 150 — - 120ー4 90 3
- `#t.00:01:11-00:01:12`　150 120 •4 90 3 60 6 oz vs. 5 oz Capacity
- `#t.00:01:12-00:01:15`　180 120 - 150 - - 120 - 90 60 6 oz vs. 5 oz Capacity
- `#t.00:01:15-00:01:18`　- 180 6 oz vs. 5 oz Capacity
- `#t.00:01:22-00:01:28`　ORT - (١)
- `#t.00:01:37-00:01:38`　180 一150 - 120 90 60 RET

## 口播转写（本机 ASR）

- 语种 `en-US` ｜ 795 字 ｜ `macOS Speech.framework（本机、on-device）`
- 语种判读：画面文字判读：汉字 1 / 拉丁字母 84 ⇒ **英文优先**（语序 en-US → zh-CN）

On this one uses a pattern in true double layer it feels really secure and fits comfortably so I don't have to constantly think about whether everything is sitting where it should the mom because he want this one also holds up to 6 ounces compared to the 5 ounces with UV that extra capacity gives me a little more breathing room which makes my pumping routine feel that much easier and then there's a cleanup the mom because he wants one has just five washable parts compared with six on the UV Cowan one also gives me up to 10 pumping only sessions and one single charge using both I realize what I want from a pump has changed the UVU pro makes sense if portability is your priority but for me cover has become much more important and that's why mom cozy wellness one has become my go to pump

> **口播转写**由 `macOS Speech.framework` **本机**完成（on-device、不出机器），
> **没有逐句时间码** —— 不能按时间定位；ASR 可能误识别，不能当逐字原文引用。
> **画面文字**那半**有** `#t.` 时间码，可定位到秒。案例只作参照，不构成规则。