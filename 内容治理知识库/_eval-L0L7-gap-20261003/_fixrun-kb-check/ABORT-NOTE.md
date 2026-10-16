# 作废记录：被中断的半轮（2026-10-04 08:03–08:12）

第一次 workflow 调用**被中断**（工具结果未落盘），只 spawn 了 27 个会话、覆盖 23 条用例。
**整轮作废，不计入任何分数**，理由两条：

1. **不完整**：53 条里只有 23 条跑了，缺失的 30 条没有会话。
2. **自曝泄漏（真事）**：会话 `d6beb87b…`（用例 #8）执行了
   `cat _eval-L0L7-gap-20261003/_fixrun-kb-check/lock.sh` 与 `unlock.sh` ——
   这两个脚本里写着 `cases-a.json` / `cases-b.json` / `kb-check/evals` 的**锁定清单**，
   等于把"这是个评测台、答案键在哪"告诉了被测会话。**答案键本身读不到**（当时已 chmod 000），
   但评测结构被看见 ⇒ 该轮盲测保真度受损。

据此加固（自第二轮方案起生效）：盲测期间把**整个 `_fixrun-kb-check/` 目录 chmod 000**，
而不是只锁里面的两个 json；`lock.sh` / `unlock.sh` 不再留在被测会话可读的位置。
`rounds/DISCARDED-interrupted-partial.json` 是本轮留下的原始取证，仅供审计，**不参与评分**。
