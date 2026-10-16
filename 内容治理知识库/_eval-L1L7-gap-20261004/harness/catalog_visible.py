#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""精确复刻 @deepseek-ai/dsh-tool-skill 的 catalogDescription（vendored，勿与 L0 工程耦合）。

宿主实现（代码级依据，2026-10-04 三方核实）：
    // @deepseek-ai/dsh-tool-skill/lib/index.js
    //   :18  const DEFAULT_CATALOG_DESCRIPTION_MAX_LENGTH = 500;
    //   :27  catalogDescriptionMaxLength: z.number().default(DEFAULT_CATALOG_DESCRIPTION_MAX_LENGTH)
    //   :338 const normalized = value.replaceAll(/\\s+/g, " ").trim();
    //   :340 return normalized.length <= maxLength ? normalized : `${normalized.slice(0, maxLength - 3)}...`;

⇒ **生效面 = 折叠空白后的前 500 字**；>500 的部分对路由模型完全不可见。
   规范上限 1024 只管「能否通过校验」，不管「模型见不见得到」。
"""
MAXLEN = 500


def norm(desc):
    """等价于 JS 的 value.replaceAll(/\\s+/g, " ").trim()"""
    return " ".join(desc.split())


def render(desc, maxlen=MAXLEN):
    n = norm(desc)
    return n if len(n) <= maxlen else n[: maxlen - 3] + "..."


def cutoff(desc, maxlen=MAXLEN):
    """路由器实际可见的字符数（不含被截断后补的 '...'）。"""
    n = norm(desc)
    return len(n) if len(n) <= maxlen else maxlen - 3
