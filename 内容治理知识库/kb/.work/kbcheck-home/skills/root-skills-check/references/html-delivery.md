# HTML 交付链接（硬规则）

核对/放行若产出 Excel 或报告入口，必须让人**双击 HTML 就能看**，不依赖本机路径、不依赖局域网、不依赖 Excel 的 `file://`。

这条是 ABI 评测表反复打不开链接后的硬规则。下次写清单链接先读本文件。

## 必须

- 每份最终报告是**单一自包含 HTML**（CSS、用例、过程全内联）。
- 报告目录里有 `index.html`，用**相对路径**指向 `{Skill}-final-report.html`。
- Excel「报告」列：相对路径（与 xlsx 同目录写文件名；xlsx 在上一级写 `报告目录/文件名`）。
- 桌面可再放总目录 HTML，相对链进报告文件夹，作为主入口。

## 完成标准

用浏览器打开 `index.html`（或桌面总目录 HTML），点进任意一份能看到全文。这才算链接交付完成。Excel 点不开不算交付失败，但 Excel 也不得再写 `file://`。

## 正向写法

相对路径：`index.html`、`品牌声音提取器-final-report.html`、`ABI-Skills-评测报告/index.html`。
