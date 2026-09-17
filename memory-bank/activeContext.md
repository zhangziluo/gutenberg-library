# Active Context（当前状态与下一步）

## 当前（进行中）
- ✅ **英文书入库 + 英汉释义回填链路（2026-09-17）**：书库 60 → **72 本**（子部 65 → 77，新增 12 本古登堡英文书）。
  - 入库书目：Frankenstein#84、Dracula#345、The Hound of the Baskervilles#2852、Walden#205、
    Peter Pan#16、The Jungle Book#236、Anne of Green Gables#45、The Wind in the Willows#289、
    A Little Prince#146、Grimms' Fairy Tales#2591、The Arabian Nights#128、Little Lord Fauntleroy#479。
  - **新词典数据源（无版权打底 + 网络 API）**：
    - `parse_ecdict.py`（新增）：下载并解析 **ECDICT**（skywind3000/ECDICT，MIT）的 `ecdict.csv`
      （77.1 万行 / 725,767 词条）→ 按首字母分片生成 `data/ecdict_en/ecdict_{a..z}.json`
      （26 片，最大 `s` 片 7.4 MiB，**无单文件超 25 MiB**；本地、已 gitignore）
      与 `data/common_words_en.json`（常用词表前 5000）。
    - 分片由 `gloss_lib.ecdict_shard()` **惰性加载 + LRU≤3 片**，`fill_glosses.py` 按首字母聚簇遍历
      （`gloss_order()`）：全量回填 **12.8 s**、峰值内存 **72 MiB**（对照：整库加载 390 MiB / 数分钟）。
    - `gloss_lib.py` 新增英词释义函数：`ecdict_*`（英→中/英/音标，含词形还原与弯引号归一）、
      网络词典 `api_*`（主源 **freedictionaryapi.com**（Wiktionary 派生、免费无 Key、含 IPA），
      备源 dictionaryapi.dev；并发预取 + 本地缓存 `data/ecdict_api_cache.json` + 熔断 + 离线降级）。
    - `fill_glosses.py` 新增英文分支：英文词 → `zh_cn/zh_tw/en` + 音标写入 `pinyin`；
      英文词库另写 `wordbank_en.json`；CLI 支持 `--no-network` / `--api-budget=N`。
  - **英文注释生成**（`gutenberg_import.py`）：`--lang en` 时用 ECDICT 常用词表挑「英文难词」
    （非停用词 + 长度≥3 + 不在常用词表）写 annotations（word 存小写，释义待回填）。
  - **修复**：`split_single()` 未传 `lang='en'` 导致英文折行拼接丢空格（出现 `asplendid` 之类粘词，
    注释数虚高）——已修，Walden 13,753→7,989 等。
  - **前端**：`网站/js/reader.js` 注释匹配对 ASCII 词做**大小写不敏感**（词表小写、正文句首/全大写），
    并修复命中时输出原文大小写（此前输出规范小写会改变正文）。
  - 回填结果：英文注释 50,671 条 → 简体/繁中释义 **97.7%**、音标 75.9%；
    中文书注释 52,298 条（简繁 87.1%、英文 94.3%，与既有口径一致）。
  - `data/books/`、`library-index.json`、`网站/_site_data/`、`books.json`、`books-data.json`、
    `dist/`（deploy/build.sh 重建，最大单文件 4.0 MiB，未触 25 MiB 上限）均已更新。
- ⚠️ **已知待办（切分质量）**：6 本英文书仍为「整本一节」（Walden / The Jungle Book /
  The Wind in the Willows / A Little Prince / Grimms' Fairy Tales / The Arabian Nights）——
  其章节标题为「无缩进小标题 / 全大写标题 / 故事名」，超出当前 `en_chapter`
  （CHAPTER·Part·数字·罗马数字）识别范围，需按书补切分器（可参照中文书的逐本切分器做法）。

## 上一批
- ✅ **第七批古登堡中文书批量入库（10 本，2026-09-08）**：书库 50 → **60 本**。
  - 入库书目：隋唐演義#23835（褚人穫，100回，源文简体）、論語#23839（20篇）、滬語開路#62791（1915 沪语会话读本，跳封面+英文引言自 Exercise 1. 起）、白圭志#27023（16回）、孟子字義疏證#25360（戴震，序+卷上中下）、安樂集#24106（道綽，卷上下；文件开头别书残文已剔除，卷名页眉去重）、鄧析子#7215（無厚/轉辭 2 篇）、醉醒石#24027（15回）、唐鍾馗平鬼傳#27329（16回）、春秋繁露#25385（董仲舒，79 实篇+3 闕，跳过卷首目录）。
  - 新增子类：歷史演義/四書/名家/春秋；滬語開路归近現代文學·語言讀本。
  - `gutenberg_import.py` 新增切分器：`split_lunyu`（論語 篇名第X）、`split_juan_sc`（卷上/中/下，去页眉重复、剔除/剥离【全書…頁】【Ewell…頁】页码标记）、`split_fanlu`（春秋繁露缩进篇题 82 篇）；EBOOK_ID/BOOKS/DYN/DESC/reader_label/SPLITTERS 扩充。
  - `fill_glosses.py` 已重跑；`data/books/`、`library-index.json`、`网站/_site_data/`、`books.json`、`books-data.json`、`dist/`（build.sh 重建）均已更新。
- ✅ **第六批古登堡中文书批量入库（10 本，2026-09-08）**：书库 40 → **50 本**。
  - 入库书目：飛跎全傳#27331（序+32回）、佛說四十二章經#23585（首本佛经，單章）、洛神賦#24041（曹植，單章）、晁氏儒言#43014（晁說之，單章）、水滸後傳#25217（40回）、幼學瓊林#52269（33篇/蒙學）、治世餘聞#26932（8卷，库内首本史部书）、琵琶記#25246（高明，42出）、雪月梅傳#26739（自序+50回）、龍川詞#26873（陳亮，單章）。
  - 新增分类子类：釋家/儒家/雜史/戲曲/賦/詞；治世餘聞入史部、幼學瓊林入經部·蒙學、琵琶記入集部·戲曲。
  - `gutenberg_import.py` 新增切分器：`split_chu`（琵琶記第X出）、`split_juan_num`（治世餘聞第X卷）、`split_yxql`（幼學瓊林按 33 篇名；原文本用「叔侄/女子」而非「叔姪/婦女」）；EBOOK_ID/BOOKS/DYN/DESC/reader_label/SPLITTERS 扩充。
  - `fill_glosses.py` 已重跑：wordbank 5804 词条；全库回填 zh 50666 / zh_tw 50666 / en 54997。
  - `data/books/`、`library-index.json`、`网站/_site_data/`、`books.json`、`books-data.json`、`dist/`（build.sh 重建）均已更新。
- ✅ **第五批古登堡中文书批量入库（8 本，2026-09-08）**：书库 32 → **40 本**。
  - 入库书目：天豹圖#26904（41章）、梁公九諫#26886（序+九諫）、長恨歌#25352（白居易，库内首本集部书）、李娃傳#24051（白行簡）、玉樓春#25422、引鳳蕭#26921、今古奇觀#24230（80 卷，此古登堡足本卷一连八十）、後西遊記#27332（Book 2，正文自第二十二回起，至第四十回止）。
  - `gutenberg_import.py` 新增：`split_jian`（梁公九諫「第X諫」）、`split_juans`（今古奇觀「第X卷」）、`drop_until_heading`（书名/作者行截断至「序」标题）、`normalize_fe_punct`（李娃傳 FE5x 小型标点归全角）；EBOOK_ID/BOOKS/DYN/DESC/reader_label/SPLITTERS 均已扩充。
  - `fill_glosses.py` 已重跑：wordbank 5614 词条；全库回填 zh 41850 / zh_tw 41850 / en 45393；新书简体释义覆盖率约 80–95%（李娃傳 汧 等极生僻字无新华字典条目，仅有 CEDICT 英文）。
  - `data/books/`、`library-index.json`、`网站/_site_data/`、`books.json`、`books-data.json`、`dist/`（build.sh 重建）均已更新。
- ✅ **全站页脚新增兄弟站点链接「日程编辑与提醒器」→ `https://ics-editor.zhang409543901.workers.dev/`**：
  - 覆盖 15 个带页脚的页面（首页/书页/阅读/文库/链接/赞助/AI 指南/AI 设置/分类×5/写作×2）；首页追加进既有 `.footer-links`，其余页在 `.footer-note` 与 `.footer-donate` 之间新建一行 `.footer-links`。
  - `css/style.css` 新增 `.footer-links` 通用样式（13px、ink-soft、hover 主题色）；`dist/` 已由 `deploy/build.sh` 重建、与 `网站/` 逐字节一致。
- ✅ 古籍站点注释显示已修复：下划线注释 + 点击卡片，**三语释义（简体/繁体/英文）已上线**。
  - 覆盖：简体 86%、繁体 86%、英文 93.6%（25934 条注释）；420 个最高频字为人工精编。
- ✅ 阅读页三档模式（新手/进阶/专家）与三语注释均保留。
- ✅ Cloudflare 25 MiB 限制已规避：`books.json` 瘦身为轻量索引。
- ✅ AI 阅读器（深度学习 / shiji_reader）板块已整体移除：删除 `网站/public/reader/` 目录、根 `reader` 软链接与 Functions 后端；阅读页「🤖 深度学习」按钮及 ai-guide / ai-settings / README / _redirects / build.sh 中的相关引用一并清理；每页左下角「全局 AI 助手」保留。
- 📦 最近提交：移除 AI 阅读器板块（本次）；此前为 `feat` 页脚兄弟链接 + `docs` memory bank 同步。

## 下一步（规划）
- **古登堡中文书入库（Gutendex API）**：
  - Gutendex 只索引英文书名/作者为主；中文书（Project Gutenberg 中文书目）需另行定位（可用其 language=zh 过滤 + eBook 编号对照）。
  - 走现有流水线：`gutenberg_import.py`（下载 txt → build_books 切分 → 注音注释 → 合并）新增一条 Gutendex 拉取入口。
  - 入库前核算两大约束：**单本 JSON < 25 MiB**、**文件总数 ≤ 20000**（每本 = raw txt + data/books + _site_data 单书，多副本计数）；量大时推进 systemPatterns 里的 `books/{id}.json` 目录化与 R2 方案。

## 待确认/风险
- 若从 32 本扩到数百本，`_site_data` 平铺单书 + books.json 索引的扩展性需重新评估（目录化 or R2）。
