#!/usr/bin/env python3
"""给工作台的「内容治理Agent」补上 4_产品描述库（绑定 + persona）。

为什么要改：
  产品库（4_产品描述库）原来只有 4 篇，所以这个 agent 只绑了 3 个子库，
  而且 persona 第一句就写着「只依据绑定的 3 个子库作答」——
  两处都会让它在被问产品类问题时**主动拒答**，哪怕库里已经有 104 篇 W1 内容。

顺带把一条实测结论写进 persona（2026-09-28 实测）：
  中文没有分词，**整句话丢进检索会一条都命中不了**
  （「吸奶器可以说医用级吗」→ 0 条；「医用级吸奶器」→ 命中）。
  所以必须要求它传关键词，而不是把用户原话整句塞进去。

用法：
  python3 kb/.work/fix-content-agent.py            # 预览（不写）
  python3 kb/.work/fix-content-agent.py --apply    # 真改
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request

BASE = os.environ.get("WORKBENCH_URL", "http://127.0.0.1:4317")
APPLY = "--apply" in sys.argv

NEW_LIB_BULLET = (
    "- 4_产品描述库（104 篇）：**W1 产品的卖点与表达边界**（PRD §7.1 的第四个库）。"
    "含 02_表达边界**三态**（绿色-可用 / 黄色-需限定 / 红色-禁用）、01_卖点护照、"
    "03_文献研究证据库 56 条、04_内容转译卡、05_验证缺口、06_术语与口径。\n"
)

PRODUCT_RULES = """
【产品库（4_产品描述库）的额外边界，2026-09-28 加】
9. 产品库是**产品口径素材，不是合规规则**。表格里的「绿色-可用」**不等于任何渠道都能发** ——
   它只说「W1 产品侧认可这么说」，品牌、法务与当地合规要求仍要单独满足。
   **不能据产品库判 BLOCK**；要判违规，判据仍须落到 3_措辞表达库的规则条目上。
10. 产品问题要**分开归口**：问「W1 这个卖点能不能这么说」→ 查 4_产品描述库；
    问「某个措辞/功效表述违不违规」→ 查 3_措辞表达库。两库都要查时先各查一遍再综合。
    例：`医用级` 在 4_产品描述库**一次都没出现**（它属于措辞类问题，3_措辞表达库有 9 处）；
    `吸奶器` 在产品库有 14 处。查错库会得到「查不到」，那不是「不存在」。
11. 产品库每条都带 `status_tristate`（绿色-可用 / 黄色-需限定 / 红色-禁用）与使用条件，
    回答时**要把三态和使用条件一起说出来**，不能只挑「建议表达」。
12. **检索词必须是关键词，不许把用户原话整句丢进去**（实测：中文没有分词，
    整句检索会 0 命中）：
      ❌「吸奶器可以说医用级吗」→ 0 条
      ✅「医用级 吸奶器」/「W1-01」/「黄色-需限定」→ 有命中
    多词之间用空格，语义是「这些词都要有」；词之间不必相邻。
13. 短词、编号、三态词（`W1-01`、`绿色-可用`）**能查到**，别因为「词短」就放弃检索。
    若返回 `hitCount: 0` 且带 `fallback: "like"`，那才是「库里确实没有」；
    **没有** `fallback` 字段的 0 命中说明连的是旧端点，要上报、不许当结论。
"""


def req(method: str, path: str, body: dict | None = None) -> dict:
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
    r = urllib.request.Request(BASE + path, data=data, method=method,
                              headers={"content-type": "application/json"})
    with urllib.request.urlopen(r, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> int:
    agents = req("GET", "/api/agents")["agents"]
    target = next((a for a in agents if "内容治理" in a["name"]), None)
    if target is None:
        print("❌ 找不到「内容治理Agent」")
        return 1

    persona = target.get("persona") or ""
    if "4_产品描述库" not in persona:
        # ① 首个句子里的「3 个子库」→「4 个子库」
        persona = persona.replace("只依据绑定的 3 个子库作答", "只依据绑定的 4 个子库作答", 1)
        # ② 在子库清单末尾（3_措辞表达库 那一条之后）插入产品库
        marker = "- 3_措辞表达库（509 篇）："
        idx = persona.find(marker)
        if idx == -1:
            print("❌ persona 里找不到 3_措辞表达库 那一条，没敢乱改")
            return 1
        end = persona.find("\n", idx)
        persona = persona[: end + 1] + NEW_LIB_BULLET + persona[end + 1 :]
        # ③ 追加产品库的边界与检索纪律
        persona = persona.rstrip() + "\n" + PRODUCT_RULES
    new_bindings = sorted(set(target.get("kbCollectionIds") or []) | {"4_产品描述库"})

    print("将把绑定改为：", new_bindings)
    print("persona 长度：", len(target.get("persona") or ""), "→", len(persona))
    if not APPLY:
        print("\n（预览模式，没写。要真改加 --apply）")
        return 0

    out = req("PATCH", f"/api/agents/{target['id']}",
              {"persona": persona, "kbCollectionIds": new_bindings})["agent"]
    print("\n✅ 已更新")
    print("  绑定：", out.get("kbCollectionIds"))
    print("  persona 第一句：", (out.get("persona") or "").split("\n")[0][:70])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
