#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""description「可见面」自检（机制依据来自宿主代码，非推测）：

    // @deepseek-ai/dsh-tool-skill/lib/index.js
    const DEFAULT_CATALOG_DESCRIPTION_MAX_LENGTH = 500;
    function catalogDescription(value, maxLength) {
      const normalized = value.replaceAll(/\\s+/g, " ").trim();
      return normalized.length <= maxLength ? normalized : `${normalized.slice(0, maxLength - 3)}...`;
    }

⇒ **skill 目录里每条 description 的生效面是 500 字（折叠空白后），不是规范里的 1024 字**；
   >500 的部分对路由模型**完全不可见**。规范上限 1024 只管「能不能通过校验」，不管「模型见不见得到」。

本脚本逐条列出关键规则**在折叠串中的首次出现位置**，并判是否 < 生效面。
用法：python3 check_description_visibility.py <SKILL.md 路径>
"""
import re
import sys

from catalog_visible import render, MAXLEN

RULES = [
    ("触发：只对账 L0", "只对账 L0"), ("触发：L0 同步", "L0 同步"),
    ("触发：飞书侧对账", "飞书侧对账"), ("触发：飞书侧改了什么", "飞书侧改了什么"),
    ("触发：库和飞书一致吗", "库和飞书一致吗"), ("触发：源数据同步", "源数据同步"),
    ("触发：图片视频链接有没有漏", "图片视频链接有没有漏"),
    ("触发：链接下钻两层", "链接下钻两层"), ("触发：attachment 的 OCR 四态", "OCR 四态"),
    ("触发：daily sync", "daily sync"), ("触发：reconcile L0", "reconcile L0"),
    ("欠定：不加载本 skill", "欠定"),
    ("欠定：一句里已给约束就算定", "就算定"),
    ("安全：破坏性或越界一律不加载", "破坏性或越界请求一律不加载"),
    ("安全：rm -rf", "rm -rf"), ("安全：清空", "清空"), ("安全：删记录", "删记录"),
    ("安全：改飞书源", "改飞书源"), ("安全：--apply 写系统文件", "--apply"),
    ("安全：读他人目录", "读他人目录"), ("安全：curl|sh", "curl|sh"),
    ("邻居：kb-pipeline", "kb-pipeline"), ("邻居：lark-base", "lark-base"),
    ("邻居：kb-ingest-extractor", "kb-ingest-extractor"),
    ("邻居：kb-repair", "kb-repair"), ("邻居：kb-review", "kb-review"),
    ("不适用：要出图或文档", "要出图或文档"),
]


def main(path):
    txt = open(path, encoding="utf-8").read()
    desc = re.search(r"description: \|\n(.*?)\nversion: ", txt, re.S).group(1)
    norm = " ".join(desc.split())
    vis = render(desc, MAXLEN)
    cutoff = len(vis) - 3 if len(norm) > MAXLEN else len(norm)
    print(f"description 折叠后总长 = {len(norm)} 字符")
    print(f"规范上限 1024 / **生效上限 {MAXLEN}** ⇒ {'⚠️ 被截断，超出部分不可见' if len(norm)>MAXLEN else '✅ 未截断，全文可见'}")
    print(f"路由器可见区 = 前 {cutoff} 字\n")
    print(f"{'关键规则':<34}{'首次出现位置':>12}  可见?")
    print("-" * 60)
    bad = []
    for label, needle in RULES:
        i = norm.find(needle)
        ok = i >= 0 and i < cutoff
        print(f"{label:<34}{('—' if i<0 else i):>12}  {'✅' if ok else '❌ 不可见'}")
        if not ok:
            bad.append(label)
    print()
    if bad:
        print(f"❌ 不可见规则 {len(bad)} 条：{bad} —— **必须前移到 {cutoff} 字以内**")
    else:
        print(f"✅ 全部 {len(RULES)} 条关键规则均落在可见区内（{cutoff} 字）")
    print("\n可见区末尾 100 字：", vis[-100:])
    return 0 if not bad else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else "../SKILL.md"))
