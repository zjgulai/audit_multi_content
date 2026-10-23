# 零影响提速：补丁 + 复现（2026-10-22）

> 约束（Owner 本轮逐字）：「你修复的内容，不要影响工作流，必要影响图片审查skill整体执行的工作流」
> ⇒ 只重排**互不依赖**的两条读数的时序；判定、四层、评审链、图片安全审查 skill 的
> 六段交付与视觉核对清单、飞书发布，一个字节不动。

## 一、这个补丁做了什么

`tools/agent/agent.mjs` 的 `readInboundContent()`：同一张图的**画面读数**（`scene()`）
与 **OCR**（`ocr()`）原先**串行**（一个 await 完再等下一个），现改为**并发起跑**。

- 为什么可以并发：PRD §5.1 把图片输入写成两半（OCR ＋ 基础视觉），两条读数**互不依赖**；
  代码里原注释（454–457 行）早就写了这一点，只是执行时串着等。
- 行为不变：两条各自失败各自记；OCR 抛错照旧 `pushImg({failed})` 后 `continue`；
  画面读数照旧挂在 `images[i].scene`；日志顺序不变（先「画面读数」后「读到」）。
- 实测依据：那单画面读数 **2791 ms**、OCR 约 **1.5 s** ⇒ 省 `min(两者)` ≈ **1.5–2 s/图**。

## 二、为什么只有这一点

本轮把 5–6 分钟拆完（见 `test/_lat/engine_seg_probe.py` 与两份 perf 台账）：

| 段 | 耗时 | 能不能在「不改工作流」前提下降 |
|---|---|---|
| 读图 | 7.6 s | **能，就是本补丁**（-1.5–2 s） |
| 链内子代理 13 轮 LLM | 117 s | 不能（每轮依赖上一轮工具结果） |
| 链尾长文生成 14 367 字 | 144 s | 不能（要降只能改交付篇幅＝改 skill 口径） |
| 引擎 `review.py` 子进程 | 14.5 s | 不能（真判定 `trace.perf` 10 s，余下是启动+索引） |
| 引擎飞书发布（建文档/开分享/建行/回读） | ~25 s | 不能（那是产物本身的网络写） |
| 链后建议 + 建报告 + 落表 + 写正文 | 56 s | **不能**：正文提示词里含「落表读数」(`publishFactBlock`)，两者是依赖关系，不是可并行的两件事（我先前说能省 2–3 s，收回） |

⇒ **零影响空间合计 ≈ 2 s**，本补丁就是全部。

## 三、怎么应用、怎么验

```bash
cd /Users/lute/project/audit_multi_content
patch -p1 --dry-run < test/_lat/patch/agent-scene-ocr-concurrent.patch   # 先干跑
patch -p1         < test/_lat/patch/agent-scene-ocr-concurrent.patch

# 自证（改哪个子系统就跑哪个）
node tools/test_agent.mjs          # 全量离线断言；重点看读图那几组
node tools/verify_cards.mjs
python3 tools/verify_shouheng_ops.py
```

回滚：

```bash
patch -R -p1 < test/_lat/patch/agent-scene-ocr-concurrent.patch
```

## 四、没做的一项（需要你点头才做）

- 链尾 144 s：交付改「六段各 80–120 字 + 可核对数字」⇒ 预计到 ~3 min。
  但那是改 `图片安全审查` 的交付口径，**与你本轮的约束冲突，故未做。**
