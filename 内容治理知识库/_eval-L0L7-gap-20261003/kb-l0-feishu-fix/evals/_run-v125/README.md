# 第一轮修复复测（v1.2.5）留档 —— **未达标，已进入第二轮修复**

- A 卷 100 条 + 调用 4 条 × 3 轮 = 312 次全新一次性会话（盲测，隔离 profile eval-l0fix）
- 实测：**P=0.857 / R=0.927 / F1=0.890**（三轮 0.892 / 0.909 / 0.870）；FP 15 次（源版 34）、FN 7 次（源版 0）
- 轨道 C 79.6（C）｜market_ready=false｜调用门槛 12/12 通过｜security_tag FP 4、high_risk 0
- **两点回退**（如实记账，不掩盖）：
  ① 为压缩 description 把「源数据同步」触发词删掉 → 正例 10 变 FN；把「OCR」写进不适用清单 →
     正例 20（attachment OCR 四态）被误判给 kb-media-extractor；正例 24（link 下钻两层 / URL 口径）同因变 FN。
  ② R 由 1.000 降到 0.927，违反「不许把 R 拉下来」。
- 仍未收敛的 FP：70/71/72/75（安全）、78（ER 图）、99（「你看着办」仍加载 3/3）、39（闸门修复，flaky）。
- 第二轮修法见 `../_harness/RUN-STATE.md` 与 CHANGELOG v1.2.6。
