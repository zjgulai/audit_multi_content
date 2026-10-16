# defects/ — 漏项模式

每条漏项模式一个文件，命名 `defect-<指纹前8位>.md`。只记「如何发现 + 从哪补」，
不记被测 skill 全文、不记密钥。

## 条目格式

```markdown
---
type: defect
field: <YAML 字段名，如 track_b.call_tag>
found_in: <发现来源报告指纹>
fingerprint: <sha256 前16位>
ingested_at: <ISO 时间>
---

## 现象
<什么字段缺失/异常，怎么在核对时发现>

## 从哪补
<从哪份中间产物回填，回填动作>
```

## 已沉淀示例（真实观察，供参考，不计入 stats）

- 旧版 eval YAML（如 v3.16.2）缺 `track_a`（整段）与 `track_b.call_tag` / `pass_call_gate`，
  只有 `track_b` / `track_c`。核对时 `track-a-total`、`tag-call_tag` 会 fail；回填需从
  会话归档 / 调用场景执行记录补调用条数与 passed_gate，轨道 A 需重跑静态六维。
