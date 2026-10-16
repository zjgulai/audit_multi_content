# root-agents 家族文件清单

生成时间：2026-09-17 12:14（由现场重算，替代手工记账）

共 67 个文件，8331610 字节。五个元 agent 合计 318 个测试。

> **家族根只装五环成员与共享资产**：不存在任何业务样例包——业务包是被测对象，由 `root-agent-creater` 产出、落在家族根之外（`target_dir` 显式给）。
> 历史上误收进家族根的业务包与修复副本已移除；测试夹具现在全部由测试现场用 creater 构造，不再依赖仓库内既有包。

## 五环结构

| 环 | agent | stage | 测试 | 职责 |
| --- | --- | --- | --- | --- |
| ① | root-agent-creater | create | 16 | 需求 JSON → 可运行的 agent 包 |
| ② | root-agent-doctor | verify | 56 | 能不能实例化、能不能安全跑 |
| ③ | root-agent-eval | verify | 210 | 答得好不好 + report.json / report.html |
| ④ | root-agent-opt | optimize | 19 | 消费报告归因，在副本上修 |
| ⑤ | root-agent-check | grow | 17 | 跨轮累积证据、固化规则 |

## 关键契约

- 被测包契约：`refs/agent-contract.yaml`（十字段）
- 报告字段：`root-agent-eval/REPORT-TEMPLATE.md`
- 上线判定：`composite_100 >= 85` 且未环境降级（**只看分数**，无审查清单）
- 归因三分派：structural（可自动修）/ content（人审）/ environment（改码无效）

## 文件清单

| 文件 | 行数 | 大小 | sha256(前 16) |
| --- | --- | --- | --- |
| `root-agents/MANIFEST.md` | 97 | 7403 B | `（自指，不列）` |
| `root-agents/refs/agent-contract.yaml` | 155 | 10764 B | `b4b81185d27987e8` |
| `root-agents/refs/report-spec.md` | 225 | 11647 B | `b6028edb7b09babe` |
| `root-agents/refs/sources.md` | 22 | 1822 B | `3ef75ba44fb6b872` |
| `root-agents/refs/task-schema.yaml` | 28 | 1973 B | `6a05d74c0aeb1747` |
| `root-agents/refs/tool-policy.md` | 51 | 3285 B | `5ecf714154d740b8` |
| `root-agents/root-agent-check/agent.py` | 665 | 28095 B | `8c98b3da31a437ad` |
| `root-agents/root-agent-check/agent.yaml` | 53 | 2184 B | `f87d63ac05fd9c4e` |
| `root-agents/root-agent-check/evals/cases.json` | 1463 | 58460 B | `e820104861f17de6` |
| `root-agents/root-agent-check/evals/report.html` | 3038 | 232916 B | `17e9558a5bc882b4` |
| `root-agents/root-agent-check/evals/report.json` | 2435 | 222835 B | `a50f2fcfe451a6d6` |
| `root-agents/root-agent-check/evals/results.json` | 3130 | 879799 B | `06b27ce4023aa541` |
| `root-agents/root-agent-check/evals/score.json` | 1137 | 33743 B | `59b016790dbc5800` |
| `root-agents/root-agent-check/memory/growth.json` | 3341 | 186778 B | `4d9065abd10434da` |
| `root-agents/root-agent-check/memory/growth.md` | 28 | 1306 B | `ad9d8ca0019aea71` |
| `root-agents/root-agent-check/prompts/system.md` | 61 | 3149 B | `0100c5aaa9e86c85` |
| `root-agents/root-agent-check/tests/smoke.json` | 23 | 520 B | `794aaae6f90a0ca2` |
| `root-agents/root-agent-check/tests/test_check.py` | 577 | 28183 B | `d99181bec0ff61c7` |
| `root-agents/root-agent-creater/agent.py` | 1015 | 38134 B | `2aa18ff16a24e3e5` |
| `root-agents/root-agent-creater/agent.yaml` | 55 | 2113 B | `793c0f16276a692b` |
| `root-agents/root-agent-creater/evals/cases.json` | 1713 | 55238 B | `994670c54a456ec1` |
| `root-agents/root-agent-creater/evals/report.html` | 2064 | 163742 B | `c4a4e54bb561c28d` |
| `root-agents/root-agent-creater/evals/report.json` | 2596 | 159458 B | `e4182e989de56e70` |
| `root-agents/root-agent-creater/evals/results.json` | 3406 | 439358 B | `6dfff5a2ca4548a1` |
| `root-agents/root-agent-creater/evals/score.json` | 1144 | 34492 B | `a07db15c03d9d03f` |
| `root-agents/root-agent-creater/prompts/system.md` | 38 | 2683 B | `e6981c31de81a100` |
| `root-agents/root-agent-creater/tests/smoke.json` | 49 | 1004 B | `e5785efda21e5706` |
| `root-agents/root-agent-creater/tests/test_create.py` | 207 | 8637 B | `546ee7443a058bf7` |
| `root-agents/root-agent-creater/tests/test_errors.py` | 173 | 6986 B | `700982b5cbfec678` |
| `root-agents/root-agent-doctor/agent.py` | 1831 | 75119 B | `d3e1ac50861f16c8` |
| `root-agents/root-agent-doctor/agent.yaml` | 45 | 2025 B | `a6f1e8c5176ac0a6` |
| `root-agents/root-agent-doctor/evals/cases.json` | 1411 | 47300 B | `f6f88fccae2ae78d` |
| `root-agents/root-agent-doctor/evals/report.html` | 4470 | 255988 B | `922be189dddf0db2` |
| `root-agents/root-agent-doctor/evals/report.json` | 2574 | 220803 B | `fc6ebad075f4c4c5` |
| `root-agents/root-agent-doctor/evals/results.json` | 3309 | 1063625 B | `0f9ff37210501520` |
| `root-agents/root-agent-doctor/evals/score.json` | 1152 | 34044 B | `1ebabde458bd1bae` |
| `root-agents/root-agent-doctor/prompts/system.md` | 64 | 4659 B | `4a176ce7e03f078a` |
| `root-agents/root-agent-doctor/tests/smoke.json` | 37 | 767 B | `540bcf8d133bb9e2` |
| `root-agents/root-agent-doctor/tests/test_doctor.py` | 192 | 6484 B | `9107b52fdc26a7a3` |
| `root-agents/root-agent-doctor/tests/test_doctor_errors.py` | 523 | 22905 B | `a95cf9e343e46e58` |
| `root-agents/root-agent-doctor/tests/test_doctor_extended.py` | 552 | 24613 B | `510fe69c3262627c` |
| `root-agents/root-agent-eval/REPORT-TEMPLATE.md` | 614 | 41538 B | `5f45c57725b47137` |
| `root-agents/root-agent-eval/agent.py` | 9294 | 485948 B | `0756ab8aee64ec1a` |
| `root-agents/root-agent-eval/agent.yaml` | 48 | 1908 B | `888b10b381c76a8e` |
| `root-agents/root-agent-eval/evals/cases.json` | 1371 | 52418 B | `14567f60f12b22b7` |
| `root-agents/root-agent-eval/evals/report.html` | 1707 | 155239 B | `9defe6c9d03a9bcd` |
| `root-agents/root-agent-eval/evals/report.json` | 2473 | 154697 B | `91a758a3f6eadbd7` |
| `root-agents/root-agent-eval/evals/results.json` | 3175 | 440103 B | `04620232e635acc0` |
| `root-agents/root-agent-eval/evals/score.json` | 1155 | 34181 B | `b159b35d51acaa0a` |
| `root-agents/root-agent-eval/prompts/system.md` | 125 | 7674 B | `1a5b184818fd487b` |
| `root-agents/root-agent-eval/render_report.py` | 939 | 53877 B | `862e17a69c7e3739` |
| `root-agents/root-agent-eval/tests/smoke.json` | 37 | 832 B | `2696c8dd7e23f218` |
| `root-agents/root-agent-eval/tests/test_eval.py` | 915 | 42096 B | `cb806583fafd1276` |
| `root-agents/root-agent-eval/tests/test_eval_report.py` | 2110 | 106288 B | `aec349f314cf2b6e` |
| `root-agents/root-agent-eval/tests/test_eval_score.py` | 1255 | 61855 B | `5c4c593d76611b05` |
| `root-agents/root-agent-eval/tests/test_eval_static_extended.py` | 596 | 28055 B | `74c4da6c87c00873` |
| `root-agents/root-agent-eval/tests/test_render_report.py` | 390 | 19336 B | `21a1a47ce7b031ba` |
| `root-agents/root-agent-opt/agent.py` | 804 | 32517 B | `87af1e4f6386f4a5` |
| `root-agents/root-agent-opt/agent.yaml` | 56 | 2196 B | `6640690c6f137add` |
| `root-agents/root-agent-opt/evals/cases.json` | 1375 | 52925 B | `198a5d48f91d91fd` |
| `root-agents/root-agent-opt/evals/report.html` | 3232 | 255134 B | `85a5f5a16dea960c` |
| `root-agents/root-agent-opt/evals/report.json` | 3616 | 235200 B | `adf622837ab4559b` |
| `root-agents/root-agent-opt/evals/results.json` | 4163 | 1600841 B | `f4a2d096a5128b52` |
| `root-agents/root-agent-opt/evals/score.json` | 1446 | 46233 B | `60a949e36796358c` |
| `root-agents/root-agent-opt/prompts/system.md` | 60 | 3566 B | `c4d064fdf6f86bb0` |
| `root-agents/root-agent-opt/tests/smoke.json` | 21 | 450 B | `49bb53d21203330f` |
| `root-agents/root-agent-opt/tests/test_opt.py` | 695 | 32036 B | `6c78922c47b6d5d8` |
