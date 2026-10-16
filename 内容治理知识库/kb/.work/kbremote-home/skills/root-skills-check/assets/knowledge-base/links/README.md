# links/ — 失效链接模式

每条模式一个文件，命名 `link-<指纹前8位>.md`。只记「失效模式 + 修复方式」，不记整份 HTML。

## 条目格式

```markdown
---
type: link
source_report: <来源报告指纹>
fingerprint: <sha256 前16位>
ingested_at: <ISO 时间>
---

## 失效模式
<哪种链接会失效：目录锚点改名、--cases/--process 传 http(s) 占位、file:// 路径漂移>

## 修复方式
<如何修：更新锚点 id、改传本地文件路径、重建报告>
```
