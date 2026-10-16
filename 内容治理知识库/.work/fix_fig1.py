#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
改《内容治理-裸模型和知识库方案.html》图 1：
  每一层都必须同时走「知识库侧 + 模型侧」，不分主判与副判。
同步改：图例 / 图注 / 图下对照表 / 建议一说明 / PRD 对照表末列 / 版本变更记录。
"""
import pathlib

P = pathlib.Path("/Users/lute/Desktop/内容治理-裸模型和知识库方案.html")
s = P.read_text(encoding="utf-8")
n = [0]


def rep(old, new, must=True):
    global s
    if old not in s:
        if must:
            raise SystemExit("没找到：\n" + old[:220])
        return
    s = s.replace(old, new, 1)
    n[0] += 1


# ---------------------------------------------------------------- 1. 重画 SVG
i = s.index('<svg viewBox="0 0 980 830"')
j = s.index("</svg>", i) + len("</svg>")

LAYERS = [
    ("P0 层 · 法务合规红线", "#1d5fa8",
     ["关键词 / 正则 / 变体确定性匹配，毫秒级", "命中即成为 BLOCK 候选"],
     ["语义边界核查：等义句、英文屈折、", "连字符变体、隐含声称"]),
    ("P1 层 · 安全与准确性", "#1d5fa8",
     ["外部标准条款；产品描述库的边界规则", ""],
     ["语义理解：危险示范、使用姿势、功能越界", "抽奖要件、价格标注、命名规范"]),
    ("P2 层 · 通识与常识", "#1d5fa8",
     ["内部正负样本（案例参照）", ""],
     ["多模态推理：画面、构图、水印", "肖像、比例、场景合理性"]),
    ("P3 层 · 措辞与表达", "#1d5fa8",
     ["Do not say / Say this instead 词表", ""],
     ["语境判断 ＋ 替代表达建议", "只出建议，不改主结论"]),
]

svg = ['<svg viewBox="0 0 980 880" style="width:100%;height:auto;display:block;font-family:inherit" xmlns="http://www.w3.org/2000/svg">']
svg.append('''  <defs>
    <marker id="f1-g" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6.5" markerHeight="6.5" orient="auto">
      <path d="M0,0 L10,5 L0,10 z" fill="#7c8089"/></marker>
  </defs>''')
# 图例
svg.append('<text x="596" y="26" font-size="12" fill="#7c8089" text-anchor="start">图例</text>')
svg.append('<rect x="646" y="14" width="18" height="18" rx="4" fill="#eef4fc" stroke="#1d5fa8" stroke-width="2"/>')
svg.append('<text x="670" y="28" font-size="12.5" fill="#1d5fa8" font-weight="700" text-anchor="start">知识库侧</text>')
svg.append('<rect x="766" y="14" width="18" height="18" rx="4" fill="#f5eefb" stroke="#7a3fa0" stroke-width="2"/>')
svg.append('<text x="790" y="28" font-size="12.5" fill="#7a3fa0" font-weight="700" text-anchor="start">模型侧</text>')
# 送审素材
svg.append('<rect x="340" y="46" width="300" height="54" rx="12" fill="#f7f8fa" stroke="#c9ccd4" stroke-width="2"/>')
svg.append('<text x="490" y="70" font-size="14.5" fill="#1c1d21" font-weight="700" text-anchor="middle">送审素材</text>')
svg.append('<text x="490" y="90" font-size="12" fill="#7c8089" text-anchor="middle">文字 / 图片 / 视频</text>')
svg.append('<line x1="490" y1="100" x2="490" y2="128" stroke="#7c8089" stroke-width="2" marker-end="url(#f1-g)"/>')
# 四层容器
svg.append('<rect x="30" y="132" width="920" height="540" rx="14" fill="#fcfcfd" stroke="#c9ccd4" stroke-width="2" stroke-dasharray="8 6"/>')
svg.append('<text x="48" y="156" font-size="13.5" fill="#1c1d21" font-weight="700" text-anchor="start">四层同时启动 · 每层「知识库侧 ＋ 模型侧」同时跑 · 层内两侧也互不等待</text>')

y = 168
for title, _, kb, lm in LAYERS:
    svg.append(f'<rect x="46" y="{y}" width="888" height="116" rx="12" fill="#fff" stroke="#c9ccd4" stroke-width="1.5"/>')
    svg.append(f'<text x="60" y="{y+26}" font-size="14" fill="#1c1d21" font-weight="700" text-anchor="start">{title}</text>')
    yb = y + 34
    # 知识库侧
    svg.append(f'<rect x="60" y="{yb}" width="424" height="68" rx="10" fill="#eef4fc" stroke="#1d5fa8" stroke-width="2"/>')
    svg.append(f'<text x="72" y="{yb+22}" font-size="12.5" fill="#1d5fa8" font-weight="700" text-anchor="start">知识库侧 · 完整跑一遍</text>')
    for k, line in enumerate(kb):
        if line:
            svg.append(f'<text x="72" y="{yb+44+k*18}" font-size="12" fill="#1c1d21" text-anchor="start">{line}</text>')
    # 模型侧
    svg.append(f'<rect x="496" y="{yb}" width="424" height="68" rx="10" fill="#f5eefb" stroke="#7a3fa0" stroke-width="2"/>')
    svg.append(f'<text x="508" y="{yb+22}" font-size="12.5" fill="#7a3fa0" font-weight="700" text-anchor="start">模型侧 · 完整跑一遍</text>')
    for k, line in enumerate(lm):
        if line:
            svg.append(f'<text x="508" y="{yb+44+k*18}" font-size="12" fill="#1c1d21" text-anchor="start">{line}</text>')
    y += 126

# 合并 → 三态
svg.append('<line x1="490" y1="672" x2="490" y2="698" stroke="#7c8089" stroke-width="2" marker-end="url(#f1-g)"/>')
svg.append('<rect x="210" y="700" width="560" height="58" rx="12" fill="#f7f8fa" stroke="#c9ccd4" stroke-width="2"/>')
svg.append('<text x="490" y="724" font-size="14" fill="#1c1d21" font-weight="700" text-anchor="middle">合并 · 同一问题取交集，不同问题走并集</text>')
svg.append('<text x="490" y="745" font-size="11.5" fill="#7c8089" text-anchor="middle">P0 命中可先返回 BLOCK（红线零延迟），其余层结果收齐后再并入问题清单</text>')
svg.append('<line x1="490" y1="758" x2="490" y2="784" stroke="#7c8089" stroke-width="2" marker-end="url(#f1-g)"/>')
svg.append('<rect x="300" y="786" width="380" height="62" rx="12" fill="#1c1d21"/>')
svg.append('<text x="490" y="812" fill="#fff" font-size="15" font-weight="700" text-anchor="middle">单一三态结论</text>')
svg.append('<text x="490" y="833" fill="#c9ccd4" font-size="12.5" text-anchor="middle">BLOCK ＞ REVIEW ＞ PASS —— 只降不升</text>')
svg.append('</svg>')

s = s[:i] + "\n".join(svg) + s[j:]
n[0] += 1

# ---------------------------------------------------------------- 2. 图题
rep('<figcaption><b>图 1 · 建议一「串行兜底」怎么跑</b><span class="fsub">一条漏斗，按层分派；<b>不是一个素材跑两遍</b></span></figcaption>',
    '<figcaption><b>图 1 · 建议一怎么跑：四层同时启动，每层两侧同时跑</b>'
    '<span class="fsub"><b>每一层都必须走「知识库 ＋ 模型」，不分主判与副判</b>；两侧各出一遍问题清单，最后合并成单一三态</span></figcaption>')

# ---------------------------------------------------------------- 3. 图注
rep('<p class="figcap">① 命中 P0 就停，模型层零调用（文案类 3/9 案实测如此）；① 没命中，模型层只跑该层规则覆盖不到的残差。</p>',
    '<p class="figcap">四层同时启动，互不等待；每层内部「知识库侧」与「模型侧」也同时跑，各自完整出一遍问题清单，互不等待。'
    '两侧结论在最后一步合并：同一问题取交集，不同问题走并集。P0 命中只让<b>结论</b>先出 BLOCK（红线零延迟），<b>不等于模型侧不启动</b>。</p>')

# ---------------------------------------------------------------- 4. 图下对照表（原来写「谁主判」）
old_callout_start = '<div class="callout kb" style="margin:16px 0 0">'
ci = s.index(old_callout_start)
cj = s.index("</div>", s.index("措辞表达库同时覆盖 P0 与 P3", ci)) + len("</div>")
new_callout = '''<div class="callout kb" style="margin:16px 0 0">
  <p><b>一张对照表把「每层两侧各跑什么」说清 —— 每层都是两侧全跑，不存在主判与副判：</b></p>
  <table class="tight" style="margin:10px 0 8px">
    <thead><tr><th style="width:52px">层</th><th style="width:118px">管什么</th><th style="width:330px">知识库侧跑什么</th><th>模型侧跑什么</th></tr></thead>
    <tbody>
      <tr style="background:var(--kbbg)"><td><b>P0</b></td><td>法务合规红线</td><td>关键词 / 正则 / 变体<b>确定性匹配</b>，每个词有出处（逐字源 / 规则原文 / 等价写法三选一）</td><td>语义边界核查：等义句、英文屈折形态、连字符变体（<code>FDA-approved</code>）、隐含声称</td></tr>
      <tr><td><b>P1</b></td><td>安全与准确性</td><td>外部标准条款、产品描述库的边界规则</td><td>语义理解：危险示范、使用姿势、功能越界；抽奖要件／价格标注／命名规范／产品边界</td></tr>
      <tr><td><b>P2</b></td><td>通识与常识</td><td>内部正负样本（案例参照）</td><td>多模态推理：画面／构图／水印／肖像／比例、场景合理性</td></tr>
      <tr><td><b>P3</b></td><td>措辞与表达</td><td>Do not say / Say this instead 词表</td><td>语境判断并给出替代表达建议（不改变主结论）</td></tr>
    </tbody>
  </table>
  <p><b>三条硬规则：</b>① <b>四层同时启动</b>，每层两侧同时跑，<b>互不等待</b>，层内两侧也不互相等待；② P0 命中时结论可立刻返回 BLOCK（红线零延迟），其余层结果收齐后再并入问题清单；③ <b>没有主判与辅助之分</b> —— 每层的两侧都是完整的一遍审查，各自出问题清单，结论按「同一问题取交集、不同问题走并集」合并（位置相同 + 类目相同 = 同一个问题）。</p>
  <p><b>但要说清现状：</b>按飞书源表实测，四类知识库里<b>只有措辞表达库形成了规则</b>，另外三类还是文档与群聊记录。所以 P1／P2／P3 三层的「知识库侧」<b>目前实际是空的</b>，只有模型侧在跑 —— 这正是 <a href="#s4">§04</a> 要补的地方。</p>
  <p style="margin-bottom:0"><b>另外一个容易混的点：</b>措辞表达库同时覆盖 P0 与 P3 —— 同一个库、同一批知识，<b>能写成关键词／正则的进 P0，要读语境的进 P3</b>。</p>
</div>'''
s = s[:ci] + new_callout + s[cj:]
n[0] += 1

# ---------------------------------------------------------------- 5. 建议一说明句
rep('<p><b>一句话：先走知识库，命中就停；没命中再走模型，模型只吃残差；最后出单一三态。</b>这是把 PRD 6.3 的分层执行流程原样落地，不做二次改造。<br><span class="small">注意：图上的蓝／紫标的是<b>谁主判</b>（知识库 vs 模型），<b>不是「这一层走不走知识库」</b> —— 四层都会用到知识库，P0 由知识库主判，P1／P2／P3 由模型主判、知识库供依据；同一类库也可以同时供两层（措辞表达库覆盖 P0＋P3）。</span></p>',
    '<p><b>一句话：四层同时启动，每一层都同时跑「知识库侧 ＋ 模型侧」，两侧各出一遍问题清单，最后合并成单一三态。</b>这是把 PRD 6.2／6.3 的分层执行流程原样落地，不做二次改造。<br>'
    '<span class="small">注意：<b>没有主判与副判之分</b> —— 图上蓝紫两色标的是<b>同一层里的两侧</b>，不是「这一层归谁判」。四层<span style="color:#1d5fa8;font-weight:700">知识库侧</span>与<span style="color:#7a3fa0;font-weight:700">模型侧</span>都完整跑一遍；同一类库也可以同时供两层（措辞表达库覆盖 P0＋P3）。P0 命中只让<b>结论</b>先出 BLOCK，<b>不等于模型侧不启动</b>。</span></p>')

# ---------------------------------------------------------------- 6. PRD 对照表末列
rep('<thead><tr><th style="width:58px">层</th><th style="width:130px">管什么</th><th style="width:210px">谁来判（PRD 6.2 原文）</th><th>在本建议里</th></tr></thead>',
    '<thead><tr><th style="width:58px">层</th><th style="width:130px">管什么</th><th style="width:210px">PRD 6.2 怎么描述判定</th><th>在本建议里</th></tr></thead>')
rep('<td><b>无需大模型推理</b>，正则／关键词命中即 BLOCK</td><td><b>走知识库</b> · 漏斗 ①，命中即停</td>',
    '<td><b>无需大模型推理</b>，正则／关键词命中即 BLOCK</td><td>知识库侧做<b>确定性匹配</b>；模型侧做<b>语义边界核查</b>，两侧同时跑</td>')
rep('<td>大模型语义理解 ＋ 规则引擎辅助</td><td><b>走模型</b> · 漏斗 ②（可并行）</td>',
    '<td>大模型语义理解 ＋ 规则引擎辅助</td><td>模型侧做语义理解，知识库侧供依据；<b>两侧同时跑</b></td>')
rep('<td>大模型语义理解 ＋ <b>视觉识别</b>（多模态）</td><td><b>走模型</b> · 漏斗 ②（画面都在这层）</td>',
    '<td>大模型语义理解 ＋ <b>视觉识别</b>（多模态）</td><td>模型侧做多模态推理，知识库侧供样本参照；<b>两侧同时跑</b></td>')
rep('<td>大模型生成建议，<b>不涉硬性拦截</b></td><td><b>走模型</b> · 漏斗 ③，不改三态</td>',
    '<td>大模型生成建议，<b>不涉硬性拦截</b></td><td>模型侧出建议，知识库侧供词表；<b>两侧同时跑</b>，不改三态</td>')
rep('<p class="small" style="margin:10px 0 0"><b>PRD 6.3 的四条执行规则：</b>① P0 命中即停止后续审查 → 「命中即停」的出处；② P1 与 P2 可并行 → 允许的是<b>层内并行</b>；③ P3 只出建议、不改结论；④ 多条命中按最高优先级输出 → BLOCK ＞ REVIEW ＞ PASS，也就是「只降不升」。</p>',
    '<p class="small" style="margin:10px 0 0"><b>PRD 6.3 的四条执行规则：</b>① P0 命中即停止后续审查 → 只作用于<b>结论</b>，让 BLOCK 零延迟返回，不改变「每层两侧都跑」；② P1 与 P2 可并行 → 四层本来就同时启动；③ P3 只出建议、不改结论；④ 多条命中按最高优先级输出 → BLOCK ＞ REVIEW ＞ PASS，也就是「只降不升」。</p>')

# ---------------------------------------------------------------- 7. 推荐卡文案
rep('<div class="d">一条漏斗：<b>先走知识库</b>（P0 关键词层，毫秒级）→ 命中即停 → 没命中<b>再走模型</b>（P1／P2 只吃残差）→ 单一三态。<br>\n      <b>不是一个素材跑两遍</b>，模型层的开销按「层」算不按「遍」算。<a href="#rec1">看流程图 ↓</a></div>',
    '<div class="d">四层同时启动，<b>每一层都同时跑「知识库侧 ＋ 模型侧」</b>，两侧各出一遍问题清单，最后合并成单一三态。<br>\n      <b>不分主判与副判</b>；P0 命中只让结论先出 BLOCK（红线零延迟），其余层结果收齐后并入。<a href="#rec1">看流程图 ↓</a></div>')

# ---------------------------------------------------------------- 8. 版本记录
rep('<b>v14 修正</b> 图 1 澄清 <b>P1／P2 层也走知识库</b>（PRD 6.2「大模型语义理解 ＋ 规则引擎辅助」），蓝紫两色标的是<b>谁主判</b>而非「走不走库」；补「各层由谁主判」对照表',
    '<b>v15 修正</b> 图 1 重画：<b>四层每一层都同时跑「知识库侧 ＋ 模型侧」，不分主判与副判</b>；P0 命中只让<b>结论</b>先出 BLOCK，不再等于「模型层不启动」；补「每层两侧各跑什么」对照表&nbsp;·&nbsp; <b>v14 修正</b> 图 1 澄清 P1／P2 层也走知识库（v15 已改为两侧全跑）')
rep('<h1>内容审查 Agent：走知识库还是走模型（v12）</h1>',
    '<h1>内容审查 Agent：走知识库还是走模型（v15）</h1>')

P.write_text(s, encoding="utf-8")
print(f"完成，共 {n[0]} 处替换；文件长度 {len(s)}")
