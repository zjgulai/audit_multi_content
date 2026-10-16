---
name: <kebab-case>
description: |
  <功能一句话>。<触发时机一句话>。
  当用户说"<真实用户会说的表达1>"、"<表达2>"、"<表达3>"时使用。
  触发词：<中文词1>、<中文词2>、<中文词3>、<英文词1>、<英文词2>。
  不适用：<相邻但会误触发的场景>（走 <对应 skill>）。
version: "1.0.0"
complexity: <minimal|standard|complex>
enabled: "true"
disable-model-invocation: false
user-invocable: true
---

# <标题>

<一句话说清这个 Skill 管什么、不管什么。>

---

## 一、<入口判断>

<什么情况下该用这个 Skill；什么情况下该停手改用别的。用可判定的判据，不要写"视情况而定"。>

## 二、<主干流程>

<只写阶段名 + 准出条件，细节指向 references/。>

## 三、<核心闸门 / 最值钱的判断>

<这个 Skill 存在的理由。写清楚"遇到 X 时先看 Y"。>

## 四、<边界与不做什么>

<不适用场景，防误触发。>

---

## 什么时候读哪个文件

| 情况 | 读 |
|---|---|
| | `references/` |

## 常用命令

```bash
python3 scripts/<x>.py
```

<!--
写作纪律（来自 references/judgment-vs-fact.md）：
1. 只写判断，不写事实和常识。删掉任何"模型的默认行为也是对的"的句子。
2. 弱写法三特征——"注意""小心""要保证"——改成可判定的规则。
3. 每条判断必须能追回素材出处（记在 distill-log.md，不写在正文里）。
4. 正文 ≤8000 字符；超了往 references/ 搬。
5. description 是路由触发器不是功能摘要；写用户会怎么说，不是这个 skill 能干什么。
-->
