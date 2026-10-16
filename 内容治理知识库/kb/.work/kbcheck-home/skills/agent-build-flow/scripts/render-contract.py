#!/usr/bin/env python3
"""把规格里的确定性部分渲染成 agent.yaml 草稿。

用法:
    python3 render-contract.py <spec.md>                 # 打印到 stdout
    python3 render-contract.py <spec.md> -o agent.yaml   # 写文件
    python3 render-contract.py <spec.md> --name foo-agent

只填**能从规格里确定性读出来的**字段。读不出来的：
  - 留 <TODO: ...> 占位
  - 在文件末尾的 `# 待人工确认` 区域逐条列出来

绝不猜。猜错的契约会让评测覆盖不到真正要交的活。
"""
import re
import sys
from pathlib import Path

def TODO(msg):
    """占位符。注意不是 str.format 模板——msg 里可能有 % 或 {}。"""
    return "<TODO: " + msg + ">"

PROFILE_HINTS = [
    ("web-ops", ["页面操作", "浏览器", "爬取", "网页操作", "web-ops", "后台操作"]),
    ("code", ["代码", "编码", "仓库", "重构", "测试用例生成", "review"]),
    ("general", ["问答", "客服", "咨询", "写作", "汇总", "答复", "报告"]),
]

INTERFACE_HINTS = [
    ("http", ["http", "API 服务", "接口服务", "服务化"]),
    ("sdk", ["sdk", "库调用", "嵌入"]),
    ("cli", ["命令行", "cli", "终端", "脚本调用"]),
]

TASK_TYPE_HINTS = [
    ("safety", ["安全", "禁止", "不得", "脱敏", "红线", "合规"]),
    ("rag", ["知识库", "检索", "资料", "文档库", "引用"]),
    ("multi_turn", ["多轮", "追问", "澄清", "对话"]),
    ("instruction", ["格式", "字段", "模板", "严格按", "步骤"]),
    ("reasoning", ["推理", "比较", "取舍", "判断", "分析"]),
    ("fact_qa", ["问答", "查", "事实", "口径", "答复"]),
]


def read_text(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def section(text: str, *titles) -> str:
    """抓 markdown 里某个二级/三级标题下的内容。"""
    lines = text.splitlines()
    out, capturing, level = [], False, 0
    for line in lines:
        m = re.match(r"^(#{1,6})\s*(.+?)\s*$", line)
        if m:
            h_level, h_title = len(m.group(1)), m.group(2)
            if capturing and h_level <= level:
                break
            if any(t in h_title for t in titles):
                capturing, level = True, h_level
                continue
        if capturing:
            out.append(line)
    return "\n".join(out).strip()


def norm_slug(s: str) -> str:
    s = s.strip().lower()
    s = re.sub(r"[\s_]+", "-", s)
    s = re.sub(r"[^a-z0-9-]", "", s)
    s = re.sub(r"-{2,}", "-", s).strip("-")
    return s


def guess_profile(text: str):
    for profile, hints in PROFILE_HINTS:
        if any(h in text for h in hints):
            return profile, hints
    return None, None


def guess_interface(text: str):
    for iface, hints in INTERFACE_HINTS:
        if any(h.lower() in text.lower() for h in hints):
            return iface, hints
    return None, None


def guess_task_types(text: str):
    hit, reasons = [], []
    for tt, hints in TASK_TYPE_HINTS:
        matched = [h for h in hints if h in text]
        if matched:
            hit.append(tt)
            reasons.append((tt, matched[:2]))
    return hit, reasons


def find_deliverables(spec_text: str):
    """从「交付物」段或「用户故事」段提取候选交付物。

    判据：交出去的东西不一样才算一件活。
    这里只做**候选提取**，最终去重与淘汰必须人工判断——见 references/deliverables-rules.md。
    """
    cands = []

    # 优先级 1: 显式表格  | id | name | format | fields | acceptance |
    block = section(spec_text, "交付物", "deliverables")
    if block:
        for line in block.splitlines():
            if not line.strip().startswith("|"):
                continue
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) < 3:
                continue
            if set("".join(cells)) <= set("-: "):
                continue
            if cells[0].lower() in ("id", "编号") or "acceptance" in " ".join(cells).lower():
                continue
            cands.append({
                "id": norm_slug(cells[0]) or None,
                "name": cells[1] or None,
                "format": cells[2] if len(cells) > 2 else None,
                "fields": [f.strip() for f in re.split(r"[、,，/]", cells[3]) if f.strip()] if len(cells) > 3 else [],
                "acceptance": cells[4] if len(cells) > 4 else None,
            })

    if cands:
        return cands, "显式交付物表格"

    # 优先级 2: 用户故事里"我想要 <产物>"
    stories = section(spec_text, "用户故事")
    for m in re.finditer(r"我想要(.+?)(?:，|,)?以便", stories):
        want = m.group(1).strip()
        want = re.sub(r"^(一个|一份|一条|能|可以|快速|直接)", "", want).strip()
        if want:
            cands.append({
                "id": None, "name": want, "format": None,
                "fields": [], "acceptance": None,
            })
    if cands:
        return cands, "用户故事（需人工去重：同一产物只算一件活）"

    return [], "未找到"


def yaml_list(items, indent):
    pad = " " * indent
    return "\n".join(f"{pad}- {i}" for i in items)


def render(spec_path: Path, name_override):
    spec = read_text(spec_path)

    title_m = re.search(r"^#\s*规格[:：]?\s*(.+)$", spec, re.M)
    raw_name = name_override or (title_m.group(1).strip() if title_m else "")
    slug = norm_slug(raw_name) or None
    if slug in (None, "", "agent", "skill"):
        slug = None
        todos_name = True
    else:
        todos_name = False

    impl = section(spec, "实现决策")
    scope_out = section(spec, "范围外")
    todos = []

    if todos_name:
        todos.append(
            "name：规格标题里没留下可用的 ASCII 名字（中文会被清掉），"
            "人工定一个 kebab-case 名，例：brand-pr-agent"
        )

    # 交付物
    dels, how = find_deliverables(spec)
    if not dels:
        todos.append("deliverables：规格里没抽出候选，人工补（判据见 references/deliverables-rules.md）")
    elif how.startswith("用户故事"):
        todos.append(
            f"deliverables：从用户故事抽了 {len(dels)} 条候选，**必须人工去重**"
            "——交出去的东西一样的要合并成一件活"
        )

    # profile
    profile, phits = guess_profile(impl)
    if not profile:
        todos.append("profile：推断不出档位，人工选 general / code / web-ops（决定维度权重）")
        profile = "general"

    # interface
    iface, ihits = guess_interface(impl)
    if not iface:
        todos.append("interface：推断不出对外形态，人工选 cli / http / sdk")
        iface = "cli"

    # task_types
    tts, treasons = guess_task_types(spec)
    if not tts:
        todos.append("task_types：推断不出能力维度，人工从六维里挑")
        tts = ["fact_qa", "safety"]

    # acceptance 缺失
    for i, d in enumerate(dels, 1):
        if not d.get("acceptance"):
            todos.append(
                f"deliverables[{i}].acceptance：没读到，人工用**业务语言**补"
                "（回到阶段 1 第 5 问「怎么算成功」）"
            )
        if not d.get("id"):
            d["id"] = norm_slug(d.get("name") or f"deliverable-{i}") or f"deliverable-{i}"

    # 范围外 → 职责负例提示
    if not scope_out:
        todos.append("范围外：规格里没写，补上（用来写职责负例，防误触发）")

    todos.append("tools：工具清单必须人工确认（出题资格判定靠它：case.tool_required ⊆ tools）")
    todos.append("每件活都要能写出一条工作流（输入 → 步骤 → 交付物），写不出的不是一件活")

    # ---- 组装 ----
    out = []
    out.append("# 由 render-contract.py 生成草稿 —— 待人工确认后才能发布")
    out.append(f"# 来源规格: {spec_path}")
    out.append(f"# 交付物抽取方式: {how}")
    out.append("")
    out.append(f"name: {slug or TODO('kebab-case 名字')}")
    out.append('version: "0.1.0"')
    out.append(f"interface: {iface}" + (f"  # 由「{ihits[0]}」推断" if ihits else ""))
    out.append(f"run: {TODO('启动命令，必须真的可执行')}")
    out.append("input: stdin-json")
    out.append(f"profile: {profile}" + (f"  # 由「{phits[0]}」推断" if phits else ""))
    out.append("task_types:")
    for t in tts:
        reason = next((r for tt, r in treasons if tt == t), None)
        out.append(f"  - {t}" + (f"  # 「{'、'.join(reason)}」" if reason else ""))
    out.append("deliverables:")
    if dels:
        for d in dels:
            out.append(f"  - id: {d['id']}")
            out.append(f"    name: {d.get('name') or TODO('业务方看得懂的名字')}")
            out.append(f"    format: {d.get('format') or TODO('text|markdown|json|file')}")
            fields = d.get("fields") or []
            if fields:
                out.append("    fields:")
                out.extend(f"      - {f}" for f in fields)
            else:
                out.append(f"    fields: [{TODO('字段1, 字段2')}]")
            out.append(f"    acceptance: {d.get('acceptance') or TODO('用业务语言写')}")
    else:
        out.append(f"  - id: {TODO('kebab-id')}")
        out.append(f"    name: {TODO('名字')}")
        out.append("    format: text")
        out.append(f"    fields: [{TODO('字段1, 字段2')}]")
        out.append(f"    acceptance: {TODO('用业务语言写')}")
    out.append("tools:")
    out.append(f"  - name: {TODO('tool_name')}")
    out.append(f"    description: {TODO('这个工具干什么')}")
    out.append("    schema: {}")
    out.append("env:")
    out.append("  API_KEY: ${managed}")
    out.append("")
    out.append("# ---- 待人工确认 ----")
    for i, t in enumerate(todos, 1):
        out.append(f"# {i}. {t}")
    out.append("#")
    out.append("# 确认完跑: python3 scripts/check-flow.py <项目目录>")
    return "\n".join(out) + "\n"


def main(argv):
    args = [a for a in argv[1:]]
    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
        return 0

    spec_path = Path(args[0])
    if not spec_path.is_file():
        print(f"错误: 找不到 {spec_path}", file=sys.stderr)
        return 2

    out_path, name_override = None, None
    i = 1
    while i < len(args):
        if args[i] in ("-o", "--output") and i + 1 < len(args):
            out_path = Path(args[i + 1]); i += 2; continue
        if args[i] == "--name" and i + 1 < len(args):
            name_override = args[i + 1]; i += 2; continue
        i += 1

    text = render(spec_path, name_override)
    if out_path:
        out_path.write_text(text, encoding="utf-8")
        print(f"已写入 {out_path}")
        print("下一步: 逐条处理文件末尾的「待人工确认」，再跑 check-flow.py")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
