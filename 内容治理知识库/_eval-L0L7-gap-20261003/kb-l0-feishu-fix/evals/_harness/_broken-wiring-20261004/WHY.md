# 接线修复前的坏数据（**不可用于评分**）

根因：`run_round.session_dir_for()` 用 `os.path.abspath(cwd)` 拼会话目录名，而 macOS 上
`/tmp` 是 `/private/tmp` 的软链接 ⇒ 算出 `--tmp-…`、真实目录是 `--private-tmp-…`
⇒ `read_session` 永远找不到会话 ⇒ `reply=""`、`skills_loaded=[]`、`session_id=None`。

若拿这 15 条去评分，**所有用例都会被判"不触发"**，P/R/F1 全是假的。故整批作废、另存此处留痕。
修复见 `run_round.py` 顶部「2026-10-04 接线修复」三节（realpath + fail loud + 旁路字段）。
