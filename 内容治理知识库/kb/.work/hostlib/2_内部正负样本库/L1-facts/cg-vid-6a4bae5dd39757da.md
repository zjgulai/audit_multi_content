---
id: cg-vid-6a4bae5dd39757da
title: "[VID-Yk85b5TF] 视频画面文字与口播：WhatsApp Video 2026-09-29 at 12.46.21.mp4"
collection: 2_内部正负样本库
kb_class: [内部正负样本库]
tier: L1
topic: Yk85b5TFropm
kind: fact
summary: "https://momcozy-in.feishu.cn/wiki/TqJSduQE3oBM4uxtHhmcrVtGnPg 内嵌视频「WhatsApp Video 2026-09-29 at 12.46.21.mp4」：画面文字 22 段 / 1454 字（带 `#t.` 时间码，时长 62.7s）＋口播转写 45 字（本机 ASR，**无时间码**）"
owner: 刘华丽
evidence_level: L1
data_level: L2
sensitivity_level: L2
half_life_days: 180
created_at: 2026-10-16
valid_until: 2027-04-14
asks:
  - 这条视频（WhatsApp Video 2026-09-29 at 12.46.21.mp4）画面里出现了哪些文字
  - 某个时间点画面上写的是什么
  - 这条视频（WhatsApp Video 2026-09-29 at 12.46.21.mp4）口播说了什么
  - 画面文字与口播是否一致
not_proves: "画面文字只覆盖**画面上出现的字**，口播转写只覆盖**音轨里说的话** —— 两者都**不含画面内容判定**（婴幼儿安全、产品用法、隐私等画面风险走「视频安全审查」）；**口播转写没有逐句时间码**，不能按时间定位，且 ASR 可能误识别、不能当逐字原文引用；不能证明时效（视频可能已改版）；不能证明该条已过正式验收；不能替代合规/法务意见"
forbidden: "不许把画面文字当口播转写用（反之亦然）；不许把口播转写当逐字原文引用（ASR 有误识别，`script_mismatch` 时尤其）；不许据本条直接判 BLOCK/PASS；不许把派生视图的字段改动当成新库改动（视图不写回）"
---

# 视频画面文字与口播转写：WhatsApp Video 2026-09-29 at 12.46.21.mp4

- 所属材料：wiki:TqJSduQE3oBM4uxtHhmcrVtGnPg
- 材料地址：https://momcozy-in.feishu.cn/wiki/TqJSduQE3oBM4uxtHhmcrVtGnPg
- 视频文件：kb/l0/attachments/视频/Yk85b5TFropm2Mxp__WhatsApp_Video_2026-09-29_at_12.46.21.mp4
- 时长 62.7s ｜ 576×1024 ｜ h264
- 抽取方式：`ffmpeg(scene)+macOS Vision`（23 帧 → 22 段画面文字）

## 画面文字（按时间窗，锚点可回源）

- `#t.00:00:00-00:00:02`　I just finished pumping this much with MomCozy Wellness: 1
- `#t.00:00:02-00:00:03`　20）） I just finished pumping this much-with •MomCozy Wellness 1
- `#t.00:00:03-00:00:05`　so let's compare it with my Eufy-S1 Pro
- `#t.00:00:05-00:00:12`　both have heat and massage
- `#t.00:00:12-00:00:13`　which feels more soothing and comfortable to me
- `#t.00:00:13-00:00:15`　D it's 5 zone massage synchronizes with the suction
- `#t.00:00:15-00:00:19`　it's 5 zone massage synchronizes with the suction-
- `#t.00:00:19-00:00:20`　me having the warmth and massage work-together
- `#t.00:00:20-00:00:21`　me-having the warmth and massage work together
- `#t.00:00:21-00:00:25`　with the suction
- `#t.00:00:25-00:00:26`　LIM FILL and helps to get into let down more easily
- `#t.00:00:26-00:00:28`　and helps to get into let down more easily
- `#t.00:00:28-00:00:30`　the Eufy has more customization options
- `#t.00:00:30-00:00:36`　but when I'm pumping multiple times times a day
- `#t.00:00:36-00:00:39`　Momcozy Made for Moms Open 953 RATINGS AGE RATING CHART DEVELOPER 4.3 13+ #164 ***** Years Utilities HONG KONG LU What's New > Version 3.5.1 4d ago 1. Smoother Device Connection - Share devices right after pairing: After pairing, share BM04, BM08 monitors and the WN02 Baby Sound more Preview momcozY Made for Moms One journey, side by side. both offers app control al - P 9:41 For You • You may be ready exercises to help s • Your core is still rec can help rebuild sta Daily Check-ins Pumping th 30m 100 Reminders Feedi
- `#t.00:00:39-00:00:44`　and I also like the Momcozy Wellness 1 has a larger
- `#t.00:00:44-00:00:46`　6 ounce capacity compared with 5 ounces on the Eufy
- `#t.00:00:46-00:00:48`　so I have a little more room during each session
- `#t.00:00:48-00:00:51`　FISONED clean up is also easier just press to release
- `#t.00:00:51-00:00:54`　and there are only five washable parts
- `#t.00:00:54-00:00:55`　the Eufy is a solid option too
- `#t.00:00:55-00:00:56`　but when I look at the overall experience

## 口播转写（本机 ASR）

- 语种 `en-US` ｜ 45 字 ｜ `macOS Speech.framework（本机、on-device）`
- 语种判读：画面文字判读：汉字 0 / 拉丁字母 1131 ⇒ **英文优先**（语序 en-US → zh-CN）

One is a better fit for what I need right now

> **口播转写**由 `macOS Speech.framework` **本机**完成（on-device、不出机器），
> **没有逐句时间码** —— 不能按时间定位；ASR 可能误识别，不能当逐字原文引用。
> **画面文字**那半**有** `#t.` 时间码，可定位到秒。案例只作参照，不构成规则。