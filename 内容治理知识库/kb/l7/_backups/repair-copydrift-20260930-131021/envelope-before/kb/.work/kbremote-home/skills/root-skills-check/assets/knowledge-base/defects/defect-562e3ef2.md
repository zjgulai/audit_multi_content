---
type: defect
title: skill 新建/就地修改后不被运行时发现（watcher 只认新建目录）
source_skill: agent-build-flow
source_report: ac4266e2802803f1
fingerprint: 562e3ef2d558cdf5
ingested_at: 2026-09-15T13:07:54Z
---

## 现象
新建的 skill 在评测过程中从会话的 `available_skills` 目录里消失，`skill(name=...)` 返回
`Error: skill "xxx" is unknown or no longer available`。**所有家族静态校验器仍然 100/100 通过**
（validate-skill.py、check-skill.py 全绿），磁盘文件完好、UTF-8 合法、frontmatter 可被 yaml.safe_load 解析。
盲测因此得到全 0 触发（R=0），数据完全不可用。

## 根因
DSH 的 `dsh-skill-filesystem` 用 chokidar 监听 `~/.dsh/skills`、`~/.agents/skills` 等根目录，
但**只对新建目录触发发现**；对已存在目录内的**就地修改**（改 SKILL.md、删 .DS_Store、重命名 assets 文件）
不会让该 skill 重新进入 catalog，甚至会把它移出。

## 判据（怎么确认是这个原因）
1. `skill(name=...)` 报 unknown，但 `ls -d ~/.dsh/skills/<name>` 存在且结构完整 → 不是文件问题
2. 在 `~/.dsh/skills/` 下新建任意最小 skill（甚至只有 SKILL.md）→ 立刻出现在 catalog
3. 把出问题的目录 `rm -rf` 后 `cp -R` 回来（= 新建目录事件）→ 立刻恢复
4. 用 `grep -oE "join\([^)]{0,80}" @deepseek-ai/dsh-skill-filesystem/lib/index.js` 可看到 4 个发现根

## 修正
- 改完 skill 内容后，**必须**用「删除目录 + 重新创建目录」触发重扫，不能只 `touch` / 只改文件。
- 评测前置检查：跑盲测前先让一个 subagent 确认 `available_skills` 里能看到被测 skill，
  看不到就先做重扫再开测。**不做这一步，盲测结果全废**。
- 静态校验器全绿 ≠ 运行时可加载，二者必须分别验证。

## 影响面
任何「创建/修改 skill 后立刻评测或调用」的流程都会踩到，症状是"skill 明明在磁盘上却加载不了"。
