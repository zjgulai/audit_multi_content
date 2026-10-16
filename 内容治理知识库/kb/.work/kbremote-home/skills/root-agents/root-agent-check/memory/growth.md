# root-agent-check · 成长记忆

累计 run 数：**11**　活跃规则：**2**

> 本文件由 root-agent-check 写入。规则门槛：同一模式须复现 ≥2 次独立 run 才成立。

## 活跃规则

| 模式 | 归因 | 复现次数 | 可自动修 | 证据 run |
| --- | --- | --- | --- | --- |
| `environment|agent 未给出作答内容（answer 为空或缺失），无法判定能力` | environment | 7 | 否 | real-run-1, real-run-2, t1, wf-r1, wf-r2, wf3-r1, wf3-r2 |
| `structural|<n>/<n> 轮通过；首轮失败原因：agent 未给出可校验的作答内容（` | structural | 2 | 是 | 20260915T112317Z, 20260915T112623Z |

## 成长曲线

| run | 结论 | decisive | 环境阻塞 | 新规则 |
| --- | --- | --- | --- | --- |
| real-run-1 | insufficient_evidence | 0 | 20 | 0 |
| real-run-2 | insufficient_evidence | 0 | 20 | 1 |
| wf-r1 | insufficient_evidence | 0 | 15 | 0 |
| wf-r2 | insufficient_evidence | 0 | 15 | 0 |
| wf3-r1 | insufficient_evidence | 0 | 15 | 0 |
| wf3-r2 | insufficient_evidence | 0 | 15 | 0 |
| t1 | insufficient_evidence | 0 | 15 | 0 |
| 20260914T091603Z | insufficient_evidence | 0 | 50 | 0 |
| 20260914T103407Z | no_growth | 2 | 0 | 0 |
| 20260915T112317Z | insufficient_evidence | 0 | 0 | 0 |
| 20260915T112623Z | insufficient_evidence | 0 | 0 | 1 |
