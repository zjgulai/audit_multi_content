# Iron Law RED - 基线失败场景（无本 skill 时 agent 会失败）

## 场景

用户给出一份 root-skills-eval 产物，说「核对报告」。

## 无本 skill 时的基线失败（RED）

- agent 没有「核对清单/字段/15 项自检引用 eval、硬校验调用 eval 脚本」的单一入口，容易：
  - 把 eval 的 Step 5.4/5.5 再复制一份，导致两份闸门漂移。
  - 自己重写校验脚本，与 eval 的 `validate_report_data / self_check_html` 不一致。
- agent 没有「自动成长」闭环：核对经验随会话丢弃，同类漏项反复踩坑，知识不沉淀。

## 有本 skill 时的行为（GREEN 断言）

- 核对/回填/放行引用 eval `trigger-eval-cases.md` 的 Step 5.4/5.5，硬校验调用 `--validate-only` / `--check-only`，不复制不重写、不因此生成 HTML、不重跑出题。
- 核对通过或回填成功后，把好结果蒸馏进 `assets/knowledge-base/`，写 delta；相同指纹不重复入库。
- 下次核对先读 `index.yaml` 用已沉淀模式对照。

## 断言

- 输出含「核对报告（放行或阻断）」。
- 输出含「数据资产 delta（新增 N / 跳过 M）」。
- 引用 eval `trigger-eval-cases.md`，不出现第二份核对清单 / 字段表 / 15 项自检的复制。
- 全过 → 含「报告已放行」；有过 → 含「阻断」+ 漏项清单，不含「报告已放行」。
