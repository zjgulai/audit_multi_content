# 关键发现：skill 目录只渲染 description 的前 500 字（2026-10-04 实测）

**已确认事实**（字节级）：盲测会话的 `<available_skills>` 目录里，`kb-check` 条目
**实际可见长度 = 500 字符**，尾部为 `...ers_check、workflow_check、envelope gate、kb-check。 **先追问、不要加载本 skill*...`
—— 即目录把每条 description **硬截断到 500 字**（全库 80 条中最长 506、其余 ≤500，均带 `...`）。
被测会话的推理原文也自述：「The description is truncated in the catalog」。

**后果**：`description ≤1024` 是**规范上限**，但**触发面的生效上限只有 500 字**（差一倍）。
第一版修复把「先追问 / 不适用 / 危险请求」写在 500–1023 字区间 ⇒ **对模型完全不可见**，
于是第 1 轮边界六条仍全部误触发（P=0.593 作废轮，见 `DISCARDED-a-round1-描述被截断.json`）。

**修法**：把 description 压到 **≤500 字**，四类负例规则全部落在可见区内；
超过 500 字的部分一律下沉正文（正文是加载后才读，不受此限）。

**这条对 root-skills-eval 是机制性建议**：description 的「触发质量」应按 **500 字可见区**评估，
而不是按 1024 字上限——否则「写了但不生效」会被记成内容缺陷。
