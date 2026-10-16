# 链接模式：离线相对路径 HTML，禁止 file:// 绝对路径

失效（已反复踩坑）：Excel 写 `file:///Users/lute/.../*.html`。Mac Excel 打不开；换机器/换网更打不开。未编码与 percent-encode 都失败。

正确交付（永久性、任意网络、双击即开）：

1. 每份评测报告必须是**单一自包含 HTML**（CSS/用例/过程全内联，无外链资源、无局域网服务）。
2. 同目录放 `index.html`，用**相对路径**链到 `{Skill}-final-report.html`。
3. Excel「报告」列 hyperlink 只写相对路径。禁止 `file://`。
4. 桌面再放一份总目录 HTML，相对链进报告文件夹，作为主入口。
5. 验收：用浏览器打开 `index.html`，点进任一份报告能看全文。
