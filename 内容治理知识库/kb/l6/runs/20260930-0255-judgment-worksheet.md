# L6 自验：人工判定缺口清单（待判 75 对 / 62 个单元）

来源：`kb/l6/runs/20260930-0255-judgment-gap.json`（语料 4,192 段时重出）

## 要你做什么（如果选择自己判）

对下面的每一行，给一个标签：**相关 / 弱相关 / 不相关**。
判据只有一句：**这条单元的内容，是否回答了该查询想找的东西**。

- A 组（催奶增产 / 医生推荐背书 / 无痛吸奶 / 绝对安全承诺 / FDA approved claims / hospital grade pump / more milk supply / best-selling）：
  库里**应当**有对应知识，所以好结果是 Top3 里出现「相关」。
- B 组（汽车保养 / 基金定投 / 钢琴考级 / hiking boots / python asyncio / marathon）：
  故意问的**库外问题**。好结果是 Top3 里**全是「不相关」**（这就是「拒答行为」的度量）。

判完把标签发我，或直接改 `kb/.work/l6_judgments_ab.json` 里对应查询的 `verdict`。

---

## [A 组] FDA approved claims　（待判 5 条）
> 为什么问这个：库里有「FDA approved/certified」检测关键词与豁免词
> 当年人工给的理由（可参考）：1 是「FDA 表述错误（吸奶器是 cleared/registered 而非 approved）」的触发原因，3 是 FDA 检测关键词，4 是 FDA Approved→FDA-cleared 的改写示例，三条直接对题；2 讲未经备案的临床/科学背书，与 FDA 沾边但不是 FDA；5 是鱼类汞含量的 FDA/EPA 膳食建议，只碰了 FDA 这个词。

| 模式 | 名次 | unit_id | 摘录（前 120 字） | 你的标签 |
|---|---|---|---|---|
| bm25_only | 1 | `3f095d15b6c6eb9c4414` | uld be aware that the DSHEA disclaimer or similar statements won’t cure an otherwise deceptive ad, particularly where th | ？ |
| hybrid | 2 | `e772918fd9b93eec5341` | o federal quality standards. The FDA also approves generic drugs and biosimilar medications for patient use. Biosimilars | ？ |
| hybrid | 3 | `a4424c8206b8e8a6bcc8` | FDA 表述错误（吸奶器为 cleared/registered，非 approved/certified） | ？ |
| vector_only | 2 | `af2b9b5f556eb911640e` | FDA cleared, FDA-cleared, FDA registered, FDA 注册 | ？ |
| vector_only | 3 | `a4424c8206b8e8a6bcc8` | FDA 表述错误（吸奶器为 cleared/registered，非 approved/certified） | ？ |

## [A 组] hospital grade pump　（待判 9 条）
> 为什么问这个：库里有 U03:hospital / M05:hospital-grade 命中片段
> 当年人工给的理由（可参考）：1、2、5、6、7 分别是 M05:hospital grade 命中片段、hospital/medical grade 检测关键词、该表述的修改建议与改写示例，全部对题；3 是 HSA 资格广告、4 是德语标题，都不含该表述。

| 模式 | 名次 | unit_id | 摘录（前 120 字） | 你的标签 |
|---|---|---|---|---|
| bm25_only | 1 | `e7b64fb3a85179631e00` | Big Member Sale: 20% Off ｜ Code BDMS20 Save 20% ｜ Compact & Portable & Hospital Grade ｜ Momcozy Hospital Grade Breast Pu | ？ |
| bm25_only | 2 | `c1d9ea5384afe5c53ad1` | Momcozy Official ｜ V1 Wearable Breast Pump ｜ Compact & Portable & Hospital Grade ｜ Momcozy Hospital Grade Breast Pump -  | ？ |
| bm25_only | 3 | `ad45009cf856c477d00f` | n modes HygieniKit double pump kit with viral barrier Backlit LCD display with timer Best for: Moms who need a rented ho | ？ |
| hybrid | 1 | `9c7a52a1bc804137cfaa` | ion. It is an easy, budget-friendly way to add hands-free pumping to your routine. Hospital-strength suction up to 260 m | ？ |
| hybrid | 2 | `294b54292b6b4e3fa2b4` | lief™ : Gently ease discomfort and express milk for moms with enlarged breasts Expression Mode : Slow and steady sucklin | ？ |
| hybrid | 3 | `7af03fad93364f08dec7` | enhance milk production. Milk Relief™ : Gently ease discomfort and express milk for moms with enlarged breasts Expressio | ？ |
| vector_only | 1 | `a438915f43849e253688` | Wearable Breast Pumps for UK Mums: In-Bra and Tube-Free 🔥 Autumn Care Event: Get Ready ｜ Up to 30% Off Shop Now Switch t | ？ |
| vector_only | 2 | `a152bcb3c0417b6a5e14` | The Best Breast Pump for Exclusive Pumping Switch to your local store for faster shipping, local pricing, and available  | ？ |
| vector_only | 3 | `f3de1549c178739bb8af` | mmended！ Definitely better output with my own setting . 2 mins stimulation at level 7 then 10 mins expression at level 7 | ？ |

## [A 组] more milk supply　（待判 4 条）
> 为什么问这个：库里有 H02:increasing milk supply 命中片段
> 当年人工给的理由（可参考）：1 是 increase/boost more milk 的正则、2 是 clinically proven to increase supply 的改写示例、3 是 more milk 表述 tricky 的判定理由、5/8 是命中片段、7 是 More Milk Less Stress 改写示例，均对题；4 是同规则的建议表达（更高吸乳效率/减少漏奶），6 是「不必过度收集乳汁」的专家修订，都只是沾边。

| 模式 | 名次 | unit_id | 摘录（前 120 字） | 你的标签 |
|---|---|---|---|---|
| bm25_only | 2 | `09a8613a258d1a362df1` | Pump More Easily & Efficiently ｜ {KeyWord:pump for low milk supply} ｜ Cozy Power By Momcozy ｜ Momcozy® Official ｜ Momcoz | ？ |
| bm25_only | 3 | `6f9d18c14cce4e27cf96` | Pump More Easily & Efficiently ｜ {KeyWord:pump for low milk supply} ｜ Cozy Power By Momcozy ｜ Momcozy® Official ｜ Momcoz | ？ |
| hybrid | 3 | `3149c7d352b014b4d59c` | he charge may not last all day. Willow Go Wearable breast pump is an app connected and controlled. It is made to fit in  | ？ |
| vector_only | 3 | `9d2b1ccd2e20a81079f7` | te ich eine perfekte Milchmenge, (150ml Eine Seite) inzwischen bildet sich sogar weniger Milch durch diese Pumpen, weil  | ？ |

## [A 组] 催奶增产　（待判 4 条）
> 为什么问这个：库里有 H02 增产/奶量承诺的处置与命中片段
> 当年人工给的理由（可参考）：2、3、7 是「删除 more milk/增产催奶/催产素/长期奶量」的修改建议，6 是该规则的触发原因，四条直接对题；1、4、5 是泌乳/催产素术语规范化的专家修订，属同一知识域但不是「增产承诺」本身。

| 模式 | 名次 | unit_id | 摘录（前 120 字） | 你的标签 |
|---|---|---|---|---|
| hybrid | 1 | `3db49273026dc107607a` | prevent mastitis, mastitis treatment, clogged duct cure, 乳腺炎, 堵奶, 通乳, 催乳, 下奶, 追奶, 回奶, 增奶, 增产, 提升奶量, 追奶量, more milk, 增加奶量 | ？ |
| hybrid | 2 | `0fb4da0192cca9dc897d` | H02 催乳/增产/奶量产出承诺（含裸 more milk、催产素、长期奶量、裸奶阵/排空功效claim，无 FDA/临床证据）；放松叙事+限定语（natural let-down/may help）走 M07 语境守卫 | ？ |
| hybrid | 3 | `6fed2dc0dbb8a03e2b30` | H02 催乳/增产/奶量产出承诺（含裸 more milk、催产素、长期奶量、裸奶阵/排空功效claim，无 FDA/临床证据）；放松叙事+限定语（natural let-down/may help）走 M07 语境守卫 | ？ |
| vector_only | 3 | `115c7ea5b20a67b77a72` | （禁用）温热治疗堵奶/乳腺炎、触发催产素、提高长期奶量。 | ？ |

## [A 组] 医生推荐背书　（待判 3 条）
> 为什么问这个：库里有检测关键词「医生推荐/医师推荐/专家推荐」与触发原因
> 当年人工给的理由（可参考）：1 是触发原因「无据的医生/专家推荐背书」、4 是检测关键词、5 是边界内容，三条直接对题；2 是「未经备案的临床/科学背书」、3 是「等级背书用语需核实认证」，属背书大类但非医生推荐；6 讲的是就医处置、7 讲医院/NICU 场景，只碰了「医生/医院」这个词。

| 模式 | 名次 | unit_id | 摘录（前 120 字） | 你的标签 |
|---|---|---|---|---|
| bm25_only | 3 | `ad83f2317442eda2c56d` | H04 无据的医生/专家推荐背书；M03 未标注来源的效果数据声明；U01 含泌乳顾问/认证头衔，需核实是否真实合作 | ？ |
| hybrid | 3 | `ad83f2317442eda2c56d` | H04 无据的医生/专家推荐背书；M03 未标注来源的效果数据声明；U01 含泌乳顾问/认证头衔，需核实是否真实合作 | ？ |
| vector_only | 3 | `6920e18b7d6324352a72` | at to expect will help your child feel more in control of the exam, easing anxiety. Dangle a carrot. Plan a treat for af | ？ |

## [A 组] 无痛吸奶　（待判 6 条）
> 为什么问这个：库里有 H07 检测关键词「无痛吸奶」
> 当年人工给的理由（可参考）：3 是含「无痛吸奶」的检测关键词、5 是 Pain-Free Pumping 的改写示例，两条对题；其余是广告名称（靠 bigram「吸奶」命中）、手挤奶/吸奶器的专家修订，与「无痛承诺」无关。 另有一条「吸奶时乳头不应有夹痛/拉扯感」的专家修订，属吸奶疼痛话题但不是「无痛承诺」，记弱相关。

| 模式 | 名次 | unit_id | 摘录（前 120 字） | 你的标签 |
|---|---|---|---|---|
| bm25_only | 2 | `beeac59b54fa55a1809a` | 【前】乳房局部硬块或结节：……质地偏硬、无痛感，这类情况多为增生的腺体组织，一般无需特殊处理 【后】删除将质地偏硬、无痛感结节定性为正常增生的表述；修订为：孕晚期若发现乳房有硬块或结节，建议及时就医排查，不应自行判断；并补充相应参考文献支撑 | ？ |
| hybrid | 1 | `cc26fc89813087a7fce8` | 删除 pain-free/no pain/without pain/pain relief/less pain/无痛/缓解疼痛等疼痛功效承诺（含 sans douleur/schmerzfrei/sin dolor），只保留 comfort | ？ |
| hybrid | 2 | `afc25b413550d13fa98a` | 奶时找 到在家的感觉。 宝宝的需求第一，支持公共场所喂奶 不管您在哪里，也不管您和谁在一起，如 果宝宝想吃奶了，您就应该满足他的要求，您 身边的人应当尊重这一点。 如果您觉得很不自在，只要简单地说一声 第五章 宝宝成长期的母乳喂养 45 “ | ？ |
| vector_only | 1 | `9d2b1ccd2e20a81079f7` | te ich eine perfekte Milchmenge, (150ml Eine Seite) inzwischen bildet sich sogar weniger Milch durch diese Pumpen, weil  | ？ |
| vector_only | 2 | `bb2bd89af073181e1c00` | 红糖即可。 ★** 功双 気基酸。 此粥不但能帮助新妈妈催乳， 还能提供新生儿发育所需的 [p349] 318 0,-43 协和专家孕产大百科 剖宫产妈妈如何坐月子 剖宫产不同于自然分娩，由于手术造成了一定的创伤，所以经历了剖宫产的新妈妈在 | ？ |
| vector_only | 3 | `afc25b413550d13fa98a` | 奶时找 到在家的感觉。 宝宝的需求第一，支持公共场所喂奶 不管您在哪里，也不管您和谁在一起，如 果宝宝想吃奶了，您就应该满足他的要求，您 身边的人应当尊重这一点。 如果您觉得很不自在，只要简单地说一声 第五章 宝宝成长期的母乳喂养 45 “ | ？ |

## [A 组] 绝对安全承诺　（待判 4 条）
> 为什么问这个：库里有「绝对安全/完全安全/零风险」类检测关键词
> 当年人工给的理由（可参考）：1、6、7 是「删除 safest/100% safe/zero risk」的修改建议，2 是该规则的触发原因，四条对题；3、4 是名为「整体效果」的广告名称，5 是儿童安全门栏、8 是含乳安全提示，都属于「安全」但完全不同的事。

| 模式 | 名次 | unit_id | 摘录（前 120 字） | 你的标签 |
|---|---|---|---|---|
| hybrid | 1 | `4beaf8c51715498baa3f` | 虚假安全承诺（best/#1/No.1/最佳/最好等排名最高级按2026-09-09口径放开，海外广告允许，不再判险） | ？ |
| vector_only | 1 | `52573b58174354f076ed` | r, to soak your aching feet. If you’ve already had some brief dips in the hot tub, there’s probably no Is Hot Stuff Not  | ？ |
| vector_only | 2 | `0452db7854ed3e46a268` | ntuicyjny ekran wyświetlacza i automatyczne wyłączanie po 30 minutach gwarantują bezstresowe sesje. ·Długie Zasilanie i  | ？ |
| vector_only | 3 | `2869c82aedae9ffcfc5d` | y, Australii, Arabii Saudyjskiej, Francji, Niemiec i niektórych państw UE, w tym darmowa wysyłka w przypadku kwalifikują | ？ |

## [B 组] best hiking boots for winter　（待判 9 条）
> 为什么问这个：语料里 hiking/boots 命中 0
> 当年人工给的理由（可参考）：B 组：全是吸奶器广告文案与卖点话术，「冬季徒步靴」在库里没有任何对应内容（hiking/boots 在语料里 0 命中）。

| 模式 | 名次 | unit_id | 摘录（前 120 字） | 你的标签 |
|---|---|---|---|---|
| bm25_only | 1 | `64251dce552760a13225` | [image_ocr] momcozy Prime Day is live! ·º40%ОFF More Favorites. Mystery Savings. Momcozy must have to an cardbefore oct  | ？ |
| bm25_only | 2 | `08553a709bdbc6f123a9` | [image_ocr] momcozy Boots渠道吸奶器纸托盘陈列设计修改 2026/07/28 momcozy 01-1 Boots渠道吸奶器纸托盘修改 修改要求： 立品背板中有效信息不要被产品遮拦 “品肖极芳放直广品买息信总（仕力杀 | ？ |
| bm25_only | 3 | `ea0cd2e68097cd35e312` | 具体原因/分析: 【审核问题】文案 ·Boots渠道吸奶器纸托盘展示道具已选择方案，需要出图纸给。 【问题要点】 1. ·Boots渠道吸奶器纸托盘展示道具已选择方案，需要出图纸给供应商制作打样 2. 【终审--@牛园园 】麻烦看看呀 原文 | ？ |
| hybrid | 1 | `3f34d11fce41fe672bdb` | boots and soggy snowsuits to deal with. To children, snowdrifts represent a pile of pleasures—snow angels to be made, sn | ？ |
| hybrid | 2 | `17a106fae98de3cbfb6c` | to dress your baby too warmly underneath the sleep sack). Consider buying 2 to 3 seasonally appropriate ones. Sweaters.  | ？ |
| hybrid | 3 | `18ea30cfcca87d53bbdc` | er snowsuit : without a struggle, no matter how cold j it is.” When you’ve just started getting the hang of moving aroun | ？ |
| vector_only | 1 | `3f34d11fce41fe672bdb` | boots and soggy snowsuits to deal with. To children, snowdrifts represent a pile of pleasures—snow angels to be made, sn | ？ |
| vector_only | 2 | `17a106fae98de3cbfb6c` | to dress your baby too warmly underneath the sleep sack). Consider buying 2 to 3 seasonally appropriate ones. Sweaters.  | ？ |
| vector_only | 3 | `cce9aa0de8ee3a6c96a0` | rdly straight. In the meantime, enjoy those adorable baby bows while you can. If you have concerns about your little one | ？ |

## [B 组] how to train for a marathon　（待判 9 条）
> 为什么问这个：语料无马拉松训练内容（仅 how/to/for 这类功能词重叠）
> 当年人工给的理由（可参考）：B 组：命中的是「How to Use Momcozy M5 Smart」「假胯宽居家训练」「0-5 岁身体活动指南」等，都不是马拉松训练；只有 how/to/training 这类词面重叠。

| 模式 | 名次 | unit_id | 摘录（前 120 字） | 你的标签 |
|---|---|---|---|---|
| bm25_only | 1 | `7c8da381a07155233c47` | r it. Preparing now (both your body and mind—since both are involved in how you experience pain) should help reduce the  | ？ |
| bm25_only | 2 | `87addf1db681c6691131` | or pee (most tots show obvious signs that a poop is coming, while around half indicate they’re about to pee), suggest to | ？ |
| bm25_only | 3 | `e1a9baf9b49aeaef88e2` | about to go, hold him or her over the potty and make a specific sound (such as “pssss”) to cue your baby that it’s time  | ？ |
| hybrid | 1 | `7c8da381a07155233c47` | r it. Preparing now (both your body and mind—since both are involved in how you experience pain) should help reduce the  | ？ |
| hybrid | 2 | `e1a9baf9b49aeaef88e2` | about to go, hold him or her over the potty and make a specific sound (such as “pssss”) to cue your baby that it’s time  | ？ |
| hybrid | 3 | `b29bf12c14aa8b8b1360` | 290-292 that help build large-motor skills, 290 to help encourage walking, 70 with small pieces, 293-296, 413 Traffic, s | ？ |
| vector_only | 1 | `7c8da381a07155233c47` | r it. Preparing now (both your body and mind—since both are involved in how you experience pain) should help reduce the  | ？ |
| vector_only | 2 | `851e959533f6e426c40b` | your feet, and wiggling your toes. Also try contracting the muscles in your abdomen and buttocks (a sort of sitting pelv | ？ |
| vector_only | 3 | `dc23a333c96b0c1fbf3f` | 产假，其中产前可以休假15天；难产的， 增加产假15天；生育多胞胎的，每多生育1个婴儿， 增加产假15天。女职工怀孕未满4个月流产的，享受 15天产假；怀孕满4个月流产的，享受42天产假。 新修订的《人口与计划生育法》中取消了晚婚晚 育假， | ？ |

## [B 组] python asyncio tutorial　（待判 3 条）
> 为什么问这个：语料里 python/asyncio 命中 0
> 当年人工给的理由（可参考）：B 组：命中 ASMR unboxing、吸奶器说明书、法伯睡眠宝典、专家证言，与 python/asyncio 无关（语料里 0 命中）。 新出现一条专家证言广告名称，无关。

| 模式 | 名次 | unit_id | 摘录（前 120 字） | 你的标签 |
|---|---|---|---|---|
| bm25_only | 3 | `e7a82c29fd0ae1b017f9` | to her. Do sit-ups in bed next to her while she’s doing her neck rolls. Ask her “in” for a date. She may not be able to  | ？ |
| vector_only | 2 | `29719208128f3d89d58a` | 易地 拿起和放下。 玩具箱 智力拼图玩具 挑选一套拼图玩具，最多 不要超过6块或7块，对于宝宝 来说把这些小“块块”拼到一 起不会是太令人害怕的任务。 制作精良、上面带有简单清晰 图案的木制拼图是最适合给宝 宝的小手拿着 的，而且很容易 吸 | ？ |
| vector_only | 3 | `97ab815c1cd2699d4b38` | but reminders are. When you’re alone and your toddler forgets to say “please,” ask “What’s the magic word?” When he or s | ？ |

## [B 组] 基金定投和股票的区别　（待判 5 条）
> 为什么问这个：语料里 基金/定投/股票/理财 命中 0
> 当年人工给的理由（可参考）：B 组：全是母乳喂养/生理术语的专家修订段落，库里没有基金/股票内容（0 命中）。 新出现一条德语折扣标题（15% Rabatt），无关。

| 模式 | 名次 | unit_id | 摘录（前 120 字） | 你的标签 |
|---|---|---|---|---|
| bm25_only | 3 | `259c6e3b689202a9ee51` | 具体原因/分析: 【原则性错误】文案 终审@吴礼芳 麻烦看看这个呀。 原文反馈: 【审核 · 2026-09-14 22:59 · 李新】终审@吴礼芳 麻烦看看这个呀:YouAreTheBest: 项目名：欧洲社媒（德国）Schedule  | ？ |
| hybrid | 3 | `40221d0f33b3a15c6999` | matters when pumping in shared spaces like offices, cafes, or public areas. The M9 operates at an impressively quiet ≤42 | ？ |
| vector_only | 1 | `40221d0f33b3a15c6999` | matters when pumping in shared spaces like offices, cafes, or public areas. The M9 operates at an impressively quiet ≤42 | ？ |
| vector_only | 2 | `8fb68c24c2f4cae5037a` | nly so you can get your practitioner’s take on cord blood banking, but also so you can make sure he or she is willing an | ？ |
| vector_only | 3 | `b0c58c5a73a6a75e88c5` | 具体原因/分析: 【措辞表达】文案 设计要求：按照brief要求替换原本EDM的货币符号和部分数。 【问题要点】 1. 设计要求：按照brief要求替换原本EDM的货币符号和部分数字，不改变设计部分内容 2. 【初审-@张悦 】麻烦看看呀  | ？ |

## [B 组] 汽车保养周期多久一次　（待判 6 条）
> 为什么问这个：语料里 汽车/保养/机油/轮胎 命中 0
> 当年人工给的理由（可参考）：B 组：命中的都是含「周期/一次/多久」的孕产与哺乳内容（月经周期、吸奶时长、超声时间窗、精子生成周期），与汽车保养无关。 新出现一条吸力档位调节的专家修订，与汽车保养无关。

| 模式 | 名次 | unit_id | 摘录（前 120 字） | 你的标签 |
|---|---|---|---|---|
| bm25_only | 1 | `6124e5624ab36e96842b` | 具体原因/分析: 【措辞表达】文案 【终审-@吴礼芳 】姐姐再看看调整了吸奶器比例大小后的呀。 【问题要点】 1. 【终审-@吴礼芳 】姐姐再看看调整了吸奶器比例大小后的呀 2. 设计要求头图需要将M5 smart吸奶器/M6吸奶器/清洗机 | ？ |
| bm25_only | 3 | `7e56971133c9b5443161` | 具体原因/分析: 【品牌一致性】文案 头图建议：宝宝与妈妈在客厅、餐厅等居家空间中互动，体现秋日自。 【问题要点】 1. 头图建议：宝宝与妈妈在客厅、餐厅等居家空间中互动，体现秋日自然光，前景可以摆放核心产品，自选产品即可（这里选了BS03 | ？ |
| hybrid | 1 | `1facc67c8ba7fdea5a2e` | “洛娜小时候，我 更喜欢用吊带和 她一起出去玩， 而不是用手推车， 这会给我更多自 由的空间。她也 会感觉到安全， 并且喜欢这种亲 密的感觉。” 安妮，5个月洛娜的母亲。 [p57] 第七章 宝宝的户外安全 55 第七章 宝宝的户外安全 和 | ？ |
| vector_only | 1 | `f84e40b20a281a73957b` | t oder eine Rückerstattung. Bitte beachten Sie, dass die Garantiezeiten je nach Produktkategorie variieren: Kinderwagen  | ？ |
| vector_only | 2 | `dea0d639f97d6ff8235d` | Jahre, abhängig von der Produktkategorie. Die Garantie deckt Ausfälle ab, die durch nicht-menschliche Faktoren verursach | ？ |
| vector_only | 3 | `0452db7854ed3e46a268` | ntuicyjny ekran wyświetlacza i automatyczne wyłączanie po 30 minutach gwarantują bezstresowe sesje. ·Długie Zasilanie i  | ？ |

## [B 组] 钢琴考级曲目推荐　（待判 8 条）
> 为什么问这个：语料无钢琴考级内容（仅「推荐」这类通用词重叠）
> 当年人工给的理由（可参考）：B 组：靠「推荐」这个通用词命中了推荐背书规则、豁免词、婴语/抱姿专家修订等，与钢琴考级无关。

| 模式 | 名次 | unit_id | 摘录（前 120 字） | 你的标签 |
|---|---|---|---|---|
| bm25_only | 2 | `557c6118bb484b3d94ab` | 【前】DHA / Omega-3 DHA参与胎儿大脑与视网膜的发育……在备孕期间通过日常饮食规律补充 【后】删除或修订DHA/Omega-3段落，明确说明DHA推荐主要适用于妊娠期和哺乳期，备孕期暂无专项推荐 【原因】妊娠期和哺乳期有DHA | ？ |
| bm25_only | 3 | `8dbff7f2b8c5b602cf70` | 【前】喂奶前排出少量前奶（作为第一推荐方法） 【后】将调整哺乳姿势（半躺式）改为第一推荐；将喂奶前排出少量前奶调整为第二点，并修正操作描述：稍微排出少量即可，或采用剪刀手姿势夹住乳头减缓乳汁流出 【原因】该方法并非主要推荐，应优先推荐调整哺 | ？ |
| hybrid | 1 | `9da7eb5e16e8a83989a7` | 总之，以精液不入阴道为好。另外，精液 中的前列腺素被阴道黏膜吸收后，可促使怀孕后的子 宫发生强烈的收缩，不仅会引起准妈妈腹痛，还易导 致流产、早产。 [p209] ‹178 协和专家孕产大百科 孕早期（1~12周） 1 2 3 4 5 6  | ？ |
| hybrid | 2 | `900ae391b5bf7ea1565c` | 保持快乐的心情，你的宝宝也会跟着快乐起来。 孕期也能穿得漂亮 孕妇装就是肥大的裤子？怀孕了就买不到好看的 衣服了？当然不是，怀孕也能穿得漂亮。色调明快、 款式别致的服装在孕期你都可以尝试。 要知道，专门的孕妇装只有在怀孕中后期才用得 着，之 | ？ |
| hybrid | 3 | `a93d3a9b1e3ed37436b8` | 这对准妈妈和胎宝宝没有什么影响。 事实上，准妈妈对烟味、酒味特别敏感。另外，准爸 爸还要检讨一下自己有没有别的不良习惯，例如不刮 胡子、不经常换衣服等，这些都可能对准妈妈的健康 和心情产生不利的影响。 和准妈妈一起给宝宝起名 在孕期，准爸爸 | ？ |
| vector_only | 1 | `900ae391b5bf7ea1565c` | 保持快乐的心情，你的宝宝也会跟着快乐起来。 孕期也能穿得漂亮 孕妇装就是肥大的裤子？怀孕了就买不到好看的 衣服了？当然不是，怀孕也能穿得漂亮。色调明快、 款式别致的服装在孕期你都可以尝试。 要知道，专门的孕妇装只有在怀孕中后期才用得 着，之 | ？ |
| vector_only | 2 | `9da7eb5e16e8a83989a7` | 总之，以精液不入阴道为好。另外，精液 中的前列腺素被阴道黏膜吸收后，可促使怀孕后的子 宫发生强烈的收缩，不仅会引起准妈妈腹痛，还易导 致流产、早产。 [p209] ‹178 协和专家孕产大百科 孕早期（1~12周） 1 2 3 4 5 6  | ？ |
| vector_only | 3 | `c4577f9a1d0f5ef1da9a` | paper, I’ll get a wispy line.” 15 to 18 months. Now it’s time for drawing with a purpose—though that purpose will still  | ？ |
