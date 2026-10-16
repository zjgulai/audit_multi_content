# kb-content-review

用 Momcozy 内容治理知识库（L0–L6）审查内容并输出三态结论的 skill。

- 入口：`SKILL.md`
- 细则：`references/protocols.md`（两段协议）、`references/categories.md`（受控分类词表）
- 参考实现：`scripts/review.py`（`--text` / `--json`；退出码 0 = 有结论，3 = 拒答）
- 输出模板与门限：`kb/l7/output_template.md`、`kb/l7/registry/l7.json`

按 `root-skills-creator` 的 Universal Skill Schema 产出（complex，< 8000 字符）。
