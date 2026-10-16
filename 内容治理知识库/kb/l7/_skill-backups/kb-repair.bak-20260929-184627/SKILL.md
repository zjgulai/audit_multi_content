---
name: kb-repair
description: |
  Momcozy 内容治理知识库的**修复入口**：闸门红了之后，按原因码定位并修，
  修完重跑同一条闸门证明修好了。
  当用户说「闸门没过帮我修 / 知识库哪里坏了修一下 / 修一下知识库 / 不过就修 /
  把这些失败项修掉 / 副本不一致帮我同步 / 登记表补登记 / 依赖缺失补上 /
  自测缺失补上 / 把信封态修掉 / 路由表和实际对不上帮我改」时使用。
  触发词：不过就修、修知识库、闸门没过、修复失败项、按原因码修、副本同步、
  补登记、补依赖、补自测、修信封、路由对不上、kb-repair。
  不适用（各自点名）：
    · 只体检不修 → 走 **kb-check**（本 skill 必须以一条已红闸门为输入）；
    · 跑 L0→L7 供给链本身 → 走 **kb-pipeline**；
    · 判断一段内容能不能发 → 走 **kb-review**；
    · 造 skill / agent、改 skill 质量 → 走 root-skills-creator / root-skills-opt；
    · 新增或停用家族成员 → 走 **kb-manage**（生命周期动作不在这里）。
version: "1.0.0"
last_updated: 2026-09-29
license: "Proprietary — Momcozy internal use only"
complexity: "standard"
compatibility:
  claude: { status: "native" }
  kimi: { status: "native" }
  cursor: { status: "native" }
  gpt: { status: "bridge", limitations: ["长任务需分步"] }
  minimax: { status: "bridge", limitations: ["需中文优化"] }
  dsh: { status: "native", notes: "kbpy 同机可用" }
  codex: { status: "native" }
---

# kb-repair —— 不过就修

**一句话**：**输入必须是一条已红的闸门**；**输出必须是同一条闸门变绿**。
没有输入就不许开工（那叫 `kb-check`），修完不重跑就不算修好。

## 1. 铁律（四条，逐条都有实测代价）

1. **先答变更协议 5 问**（读者 / 写者 / 判据 / 通道 / 回滚），答不出来就先别动。
2. **先取回滚基线**：改动前把目标文件备份到 `kb/l7/_backups/<动作>-<时间戳>/`。
3. **写通道**：python 写 `.py` / `.txt` / `.md` 会落成**"stat 虚高 4096"的信封态**
   → 一律「python 生成内容 → 写到**无扩展名**临时件 → `cp` 落到目标」。
   直接用 `cp` / bash 重定向 / node 写盘是安全的。
4. **不许拿工具 bug 当数据缺陷**：`skills_check.py` 用 `expanduser`-less 判路径
   （第 1001–1002、1018–1019 行）会把 `~` 开头的路径误报"不存在"——
   正确修法是**把登记表里那两个字段改成库根相对路径**，不是去建一个假文件。

## 2. 原因码 → 修法对照表

| 闸门 / 原因码 | 常见真因 | 修法 | 回滚点 |
|---|---|---|---|
| `skills_check` 1 类 应装未装 | 装漏了 / `source` 指向错 | `cp -R <source> ~/.dsh/skills/<id>/` | `kb/l7/_skill-backups/` |
| `skills_check` 2 类 装了没登记 | 装了但表里没有 / `status=参考` 被装 | 补表；或把副本移出装载位 | 表有 `.bak` |
| `skills_check` 3 类 副本不一致 | 源改了没重装 | 从 `source` 重装（**以源为准**） | `kb/l7/_skill-backups/` |
| `skills_check` 4 类 依赖缺失 | `depends_on_engine` 路径写错 / 写成 `~` | 改成库根相对路径；真缺就先补引擎 | 表有 `.bak` |
| `skills_check` 5 类 自测缺失 | `selftest` 指向删过的文件 | 指向现存自测；确实没有就填 `null`（算"未登记"，不算错） | 表有 `.bak` |
| `layers_check` 引擎不存在 | `layers.yaml` 路径写错 | 按实测路径改表；**不要为了对齐表去搬脚本** | `layers.yaml.bak` |
| `routes_reconcile` 不一致 | 路由表写错 / description 触发词抢活 | **先改 description 再改表**；改完必须重跑触发电测 | 两份都能回滚 |
| 信封态（差值 4096） | 用 python 写了 `.py/.txt/.md` | 用 `cp` 从无扩展名临时件重写 | 原文件已在 `_backups/` |
| `workflow_check` 第 ② 段红 | 冻结基线 vs 活库漂移 | **合法变红**，写"基线漂移"结论，不要"修" | — |

## 3. 标准动作序列

```bash
cd ~/.dsh/Momcozy知识库
# 0) 确认这是真红、不是合法变红（见 kb-check §3）
kb/kbpy l7/scripts/skills_check.py --json
# 1) 备份
#    kb/l7/_backups/<动作>-<YYYYMMDD-HHMMSS>/
# 2) 修（注意写通道）
# 3) 重跑同一条闸门，证明变绿
kb/kbpy l7/scripts/skills_check.py
# 4) 过一遍信封闸门（覆盖 .py/.txt/.md）
python3 tools/envelope_gate.py
```

## 4. 交付物

1. 修前 / 修后**同一条闸门**的输出对照（贴命令与退出码）。
2. **变更记录**：改了哪些文件 + 每文件的五问答案 + 回滚命令。
3. `kb/l7/_backups/<动作>-<时间戳>/` 的回滚基线。

## 5. 何时停下来问人

- 修法涉及 `kb/l0…l6` 的**数据或台账** → 不在授权范围内，先停。
- 需要"重跑链路才能修" → 交回 `kb-pipeline`，并说明为什么（很可能只是幂等键过期）。
- 同一条闸门修了两次还红 → 停，报"判据可能有缺陷"，附两次的证据。
- 要动的文件是 `kb/l7/registry/*.yaml`（登记表 / 层契约 / 路由表）→ 先答五问，
  并确认改动后 `skills_check.py` 仍五类全 0。
