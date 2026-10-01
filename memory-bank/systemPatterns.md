# System Patterns（系统模式）

## 书库数据架构（目标设计）
- `_site_data/books_index.json` —— **轻量索引**（书名/篇数/分类，仅目录用）
- `_site_data/books/{id}.json` —— **单本详情**（正文 + 注释，按需下载）

> ⚠️ 现状标注（与目标命名的差异）：当前仓库实际仍是
> `_site_data/books.json`（轻量索引，114 条目 / 13.6 KB）+ `_site_data/{書名}.json`（单本详情，平铺在同目录）。
> 二者遵循**同一条原则**，若日后入库量大，再迁移为 `books_index.json + books/{id}.json` 的目录结构，
> 并同步更新 `common.js` 的 DATA_BASE 解析逻辑（无状态、低成本切换）。

## 核心原则
- **前端按需动态加载**：目录只读索引，正文/注释进单书页才请求对应单书 JSON——避免把全书内容打进单个大文件而触发 25 MiB 上限。
- **大 JSON 必须拆分 / 大词库必须分片**：
  - ECDICT 英汉词典（72.6 万词 / 71.8 MiB）按首字母分片为
    `文本/新书/data/ecdict_en/ecdict_{a..z}.json`（最大 7.4 MiB），
    查询经 `gloss_lib.ecdict_shard()` **惰性加载 + LRU（≤3 片）**；遍历时按首字母聚簇
    （`fill_glosses.gloss_order()`）避免分片抖动 → 全量回填 12.8 s / 峰值 72 MiB
    （对照：整库加载 390 MiB / 数分钟）。
  - 文件数接近 20,000 上限时考虑 R2 + 签名 URL 或改用接口。
- **词典数据本地化 + 可复现**：`parse_ecdict.py` 从 ECDICT 一手 CSV 生成词典数据；
  生成的 `.csv` / 分片 / 缓存 / 常用词表全部 **gitignore**（仓库只留脚本与生成逻辑）。
- **联网步骤必须可降级**：所有外部依赖（Gutendex / 网络词典 / 古登堡 API）都做
  重试 + 熔断 + 本地缓存 + 失败静默回退，任一不可用都不阻断主流程。

## 元数据链（gutenberg_import）
```
① BOOKS 精细配置 / quick_books.json 历史配置（命中即用）
② 本地 raw 头部（Title:/Author:/书名:；英文另认「by 作者」行）
②.b Gutendex（gutendex_client.get_book → meta_from_gutendex）
③ 古登堡 API（?format=json）兜底
→ 仍无书名：中文书要求书名含 CJK，英文书（--lang en）不要求
```
- 单本契约：`cfg = {key, book, author, category, subcategory, source, file, split, gid, [lang]}`。
- 中文/英文同走一条链，不做分支（仅书名 CJK 校验与默认切分不同）。

## 一键脚本（文本/新书/）
- `add_books.sh` = 入库 + 收尾：编号或 `--file 清单` → `gutenberg_import.py` → `pipeline.sh`。
  `--lang auto|zh|en`（auto：清单书名含汉字 → zh；有书名但无汉字 → en；纯编号 → zh）、`--dry-run`、`--no-pipeline`。
- `pipeline.sh` = ①`fill_glosses.py` ②`classify_books.py` ③`deploy/build.sh` ④`git add -A`+commit+push。
  开关：`--no-push` / `--no-commit` / `--no-classify` / `--offline` / `--classify-input <文件>`；自动载入项目根 `.env`。
- 两者都**自推项目根**（`SELF` 绝对路径 → 上溯两级），可在任意目录调用；`--help` 读自身头部注释。
- **词表链路尚未接入 `pipeline.sh`**（2026-09-29 待办）：新书入库后若要刷新前端词表/释义，需手动按序跑
  `vocab_extract.py`（全库 ≈2.5 min）→ `build_vocab_final.py` → `definition_fill.py` → `deploy/build.sh`。
  是否做成 `pipeline.sh --vocab` 可选步骤待定（不默认跑：词表是**全库聚合**产物，逐本入库时没必要每次重算）。
- 写脚本的硬约束（bash 3.2 + CJK）：变量展开一律 `${VAR}`（`$VAR` 紧跟全角字符会被并入变量名）；
  不用空数组裸展开（`set -u` 会报 unbound）；`set -e` 下避免 `[ ... ] && cmd` 作语句。

## 词汇抽取（vocab_extract.py）
- 源 `data/books/*.json`（单书正本 `chapters[{title, content}]`）→ 产出 `文本/新书/vocab_raw.json`
  （**流式写**：先写 words 数组，收尾补 `_meta`/`summary`，内存与书库规模无关；`.part` 原子替换 + 回读校验）。
- **英文**：正则词形（拉丁字母全集，含变音符；词内连字符/撇号整体保留，破折号不并入）
  → 小写归一 + 弯撇号折叠；过滤纯数字、单字母（仅留 a / I）、常见停用词。**绝不用固定长度滑窗**。
- **中文**：逐字繁→简（`trad_simp_map.json`，键值均单字 → `str.translate`，长度 1:1 保偏移）
  → jieba **只在 CJK 连续段内**按词切分（HMM 关，避免给古文造词）。
  - 词典：内置常见古汉语双/多字词表 + `--zh-dict`（默认 `data/guwen_dict.txt`，可多个）；
  - 护栏：jieba 词典里「长度≥3 且词频 < `--min-dict-freq`（默认 100）且不在自有词典」的
    噪声词条（如 `国之君 20 nr`）**回退双向最大匹配**重切；
  - jieba 缺失 → 全量降级双向最大匹配（只用词典，不造词、不滑窗）。
- **硬保证（每次运行都自检，失败即报错且不落盘）**：
  - 中文：切词是对该 CJK 段的**原样重建**（拼接 == 原文）→ 无截断/丢失/重叠/跨段粘连；
  - 英文：词形必须「最大词形」（前后紧邻不得仍是拉丁字母或连接符）→ 截断必被检出；
  - 写后回读：JSON 可解析 + 记录数一致 + 必备字段齐全。
- **粒度** `--granularity=word|book|chapter`：word（默认，每词一条，全库聚合，~8.1 万条 / ~18 MiB）
  / book（词 × 书，含 `chapters` 章号压缩串）/ chapter（词 × 书 × 章，即需求字面格式）。
- 复原/回归：`--selftest`（对抗性样例：Buda-Pesth / don’t / 变音符 / 数字 / 低频噪声词条 / 自定义词表）。

## 前端标注（`网站/js/vocab-matcher.js`）
- **一处收口**：中文切词（词边界）+ 英文整词 + `<wise>` 渲染 + 词条查询，全在这一个模块里；
  `reader.js` 只负责渲染正文、简繁转换与词卡。**无构建步骤**（ES5 UMD，浏览器 `window.VocabMatcher`、
  Node 里 `require` 可跑自检），与 `网站/` 直出 Cloudflare Pages 的形态一致。
- **算法**：
  - 中文：`网站/_site_data/vocab_final.json`（`build_vocab_final.py` ← `vocab_raw.json`）建 **Trie**，
    在 **CJK 连续段内**做最长前缀匹配（Max Match，`不知 > 不 + 知`）→ 词内**不再散成单字**；
    整词无释义但成分字有释义 → 整词一个标签 + `data-parts`（词卡列成分字）。
  - **行内释义（2026-09-29 晚新增）**：词表行 = `[词形, 简体形, 词次, 书数, definition, need_ai]`
    （`build_vocab_final.py` 4 元 → `definition_fill.py` 回填 6 元）。`hasDef()` 认 `definition`
    （`待补/待補/TBD/空白` 一律不算）并计入 `isGloss()` ⇒ **词表词只要行内有释义就能打标**
    （`kind:gloss/all/rare` 判定与密度过滤同步放行）；`need_ai` 只影响词卡标签（`AI 待補`），不影响打标。
    无释义的词表词仍按旧规则包 `<wise class="… ann-vocab">` + `data-parts` 走成分字兜底。
  - 英文：**整词**正则（拉丁字母 + 词内连接符 + 词尾省略撇号，边界锚定）；
    查找链 整词 → 去词尾省略撇号（`mornin'`→`mornin`）→ 去所有格（`Lear's`→`lear`）
    → 仅在连接符处拆段（`old-fashioned`）。**绝不在字母中间切**（旧实现会把 `mornin'` 截成 `mornin`）。
- **渲染契约**：`<wise data-word="完整词形" data-key="词典键" data-lang="zh|en" class="ann-word …">`
  （旧 `.ann-word/.ann-hard/.ann-rare` 类名保留 → CSS/点击逻辑不必改；词卡标题取 `data-word`）。
- **性能**：TreeWalker 收集文本节点 → `requestIdleCallback` 分批写 DOM（每片 ~6 ms，可取消，
  无该 API 则 `setTimeout(8)`）；只对**确有命中**的节点 `replaceChild` 一次（移动端不排错位）。
- **密度与开关**：`window.VOCAB_WRAP = 'gloss'(默认) | 'all' | 'rare'`；`window.VOCAB_FINAL_URL = null`
  可关掉词表（仅用 annotations 单字）。
- **硬保证（自检逐条断言）**：分段拼回 == 原文本（textContent 不变 → 复制/下载/划选/AI 不受影响）、
  英文命中为最大词形、中文命中不跨 CJK 段、重叠取最长。
  `VocabMatcher.selftest()` **66 项（v1.2.0）**；浏览器 `reader.html?vmselftest=1`（纯函数 + DOM 两套）。
  端到端回归在 `tests/vocab-matcher/`（见 techContext）：纯函数 66 / DOM 21 / 集成 26 / 页面冒烟 14。

## 词表释义回填（definition_fill.py，2026-09-29 晚新增）
- 目标：让**词表本身**带释义 → 词卡不必依赖单书 `annotations`（跨书共用一份词义）。
  输入/输出同一个 `网站/_site_data/vocab_final.json`：4 元行 → **6 元行**（`definition`, `need_ai`）。
- **来源链（逐级降级，全部离线）**：
  1. **整词**：`gloss_override.json`（人工精编）→ **词级中文源**（`--zh-word-src` 或多个路径；
     自动发现 `data/` 下 `cedict_words.json`/`shuowen.json`/`kangxi.json`/`hanyu_words.json`）→ need_ai=false；
  2. **单字兜底**：整词无解时，按字查 单字人工覆盖 → 新华字典 → CC-CEDICT（英文释义）→ makemeahanzi；
  3. **逐字合成**：`君：①…；子：①…`（**need_ai=true**，标注为弱释义，供前端提示待精修）；
  4. 全部无解 → `待补`（need_ai=false，前端不显示、不算释义）。
- **英文词**（词表默认不含）：整词精确匹配（**禁前缀/子串**）→ ECDICT 中/英 → `ecdict_api_cache` 缓存；
  `--network` 才发网络请求。
- **繁体与简繁对齐**：
  - 繁体单字键缺失 → **按字回退简体键**（`無學` → `无` + `學`）；
  - **`char_variants()`**：从词表自身推繁↔简单字对应（同长行 `無學`/`无学` 逐位取异 ⇒ 無↔无、學↔学），
    返回 `{字: {对应字…}}`，实测 **3,264 个单字键**（补齐 `trad_simp_map.json` 覆盖不到的漏网字）。
- **`strip_self_ref(t, *chars)`**：剥掉**行首**的「同'X'：」自我引用 —— 正则锚定
  `^同\s*['“"]?\s*X\s*['”"]?\s*[：:]\s*`，X 取「本字 + 其繁简对应字」（新华字典的异体/形近交叉引用：
  `無` 与简体 `无` 的释文都以「同'無'：」起头）。**只剥行首、只剥 X 命中者**：释义**中间**的正常引用
  照旧保留（全库 1,458 行含「可同'否'」「词尾，同'么'」，不可一概删净）。
  实测：全库以「同'X'：」开头的释文 **0 行**。
- **文件结构**：`{"_meta": {...}, "zh": [行…], "en": [行…]}`（4→6 元行数组；`_meta.definition` 记
  `generated` / 生成器 / `zh.pending` / `zh.zh-composite` / `zh._need_ai` / `zh_word_sources` / `sources`）。
- **硬保证（自检不过即不落盘）**：行数不变、每行 6 元、**前四元逐项一致**（词形/简体/词次/书数不被改写）、
  `need_ai` 为布尔、词形仍合法；`.part` 原子替换 + 写后回读。`--selftest` 26 项（含 strip_self_ref /
  char_variants / 整词优先 / 英文禁前缀 / 幂等）。
- CLI：`--dry-run`、`--limit N --out 路径`、`--zh-word-src`、`--no-auto-zh-src`、`--max-len`、`--network`、`--selftest`。
- 规模（全库实测）：45,161 行 / 有释义 12,947（28.7%，**全部 need_ai**）/ 待补 32,214 / 2.89 MiB。

## 维基文库书源（`文本/新书/wikisource_complete_toolkit/` + `wikisource_import.py`）
- **工具链**：`wikisource_toolkit.py`（`fetch`/`list`/`search`）、`license_detector.py`（许可合规闸门）、
  `epub_builder.py`（EPUB）、`test_license_offline.py`（离线自检 10 样例）、`QUICKSTART.md`。
  依赖 `requests`+`beautifulsoup4`（EPUB 另需 `ebooklib`）；产物 `novels_json/`、`epubs/` 已 gitignore。
- **合规闸门（硬约束）**：抓每页调 MediaWiki `prop=templates` 读版权模板 → `pd/free/restricted/unknown`；
  **只有 `safe_to_use=True` 的页可入库**，受限/未知页默认中止（`--force` 跳过）。两个增强：
  - **子页许可继承**：子页 `status=unknown` 时**回退查父页许可**并继承（带 `inherited_from`）——
    解决「同书部分子页未直接挂 `PD-old` → 误判未识别」（如《論語》各篇）。
  - **非正文子页过滤**：`NON_CONTENT_SUBPAGES` 剔除「全览/目录/序说/凡例」等（全览是 Wikisource
    自动生成的全文页，务必剔除）。
- **正文提取**：`extract_text_from_html` 剥离 `#headerContainer`/`.ws-header` 页头、`rt` 注音、
  `.variant-tooltip` 变体注、脚本样式；**按块级元素换行、行内元素拼接**（不再 `get_text(separator="\n")`
  把每个行内元素拆行）→ 带注音古籍（千字文）也能得干净文本。
- **入库（`wikisource_import.py`）**：`novels_json/{书名}.json` → `data/books/{key}.json`（`section_label`
  = 篇/回/卷/章；每章存 `source_url`/`license`/`revid` 供追溯）→ `library-index.json`（`source=维基文库`）
  → `merge_to_site()` + `slim_books_index()`。**重名/重 key 冲突检查**（站内按书名定位，不可重名）；
  `--no-merge`（只转不入库）/`--force`（跳过受限章）。
- **`add_books.sh --source wikisource`**：`--title`（自动 `wikisource_toolkit.py fetch` 后入库）或
  `--json`（已抓取文件直接入库）；`--author/--category/--subcategory/--key/--label/--force`。
- `to_reader()` 支持 `data.section_label` 覆盖默认篇目标签（`reader_label(key)`）。

## 书库页（封面网格 `library.html` + `library.css` + `library.js`）
- **结构**：筛选栏（分类 Tab + 排序 + 搜索）+ `.lib-grid` 封面网格 + `.lib-pagination` 分页。
- **数据**：`fetch('assets/data/books-data.json')`（静态 JSON 即「API」；换 FastAPI 只改 `DATA_URL` 一处），
  `normalizeBook()` 映射到统一 schema（新字段缺失优雅回退）。
- **前端分页**（纯 JS，不做服务端分页）：`PER_PAGE=20`；`totalPages<=1` 隐藏分页栏；
  `?cat/?sort/?q/?page` 同步 URL（`history.replaceState`）；切页 `window.scrollTo({top:0})`。
- **封面纯 CSS（方案 B，不生成图片）**：`aspect-ratio:3/4` + `.cover-{jing|shi|zi|ji|cong|all}` 底色
  （经深蓝/史赭石/子墨绿/集暗紫/丛深灰/**全部棕黄**）；书名 `writing-mode:vertical-rl` 竖排楷体；
  右下角 `📗`（古登堡）/`📘`（维基文库）；悬停 `translateY(-4px)` + 阴影 + 底部渐显 `summary`。
  **「全部」Tab 统一棕黄，分类 Tab 用该部底色**。
- **排序**：热门=`read_count`、最新=`added_at`、书名=`Intl.Collator('zh')`（拼音序，无需额外数据）。
- **动画约束**：书库页**禁装饰性动画**（无翻书/粒子/视差/轮播/转场），仅卡片悬停 `transform 0.2s ease`
  与 `:active` 点击反馈。
- **详情页 hero**（`book.html` + `js/book.js`）：大封面 + 书名/作者/**批注者** + 简介 + 本版特色标签 +
  `[开始阅读]`；元数据从 `books-data.json` 按 `title` 匹配（`loadBookMeta()`），取不到降级为只用 title。

## 书库目录数据 schema（`网站/assets/data/books-data.json`）
- `merge_to_site()`（gutenberg_import + merge_to_site）逐本生成，**保留旧字段兼容**：`id/title/author/
  category/subcategory/dynasty/description/sections/source/cover` + 新增 `book_id（=id）/ summary（=description）
  / chapter_count（=sections）/ commentator / highlights / source_url / license / added_at / read_count`。
- **推导规则**：`source_label()`（源串→古登堡计划/维基文库）；`source_url_from()`（`#XXXX`→
  `gutenberg.org/ebooks/{gid}`）；`license_from()`（古登堡→公有领域）；`highlights_for()`（繁體 + 有
  annotations 则注音釋義）；`COMMENTATOR`（四大名著批注者）；`CATALOG_GID`（**目录主书 8 本**：史記
  24226/漢書23841/三國志25606/三國演義23950/水滸傳23863/西遊記23962/紅樓夢24264/古文觀止25225）；
  `_placeholder_added_at/_read_count()`（由 book_id 稳定派生，**静态站占位**，与前端 JS 兜底同算法）。
- `books.json`（轻量索引）走 `slim_books_index.py`（indent=1，**跳过无 `title` 的非书目 JSON**）。

## 古登堡书源（默认走 Gutendex）
- **元数据链**：本地 raw 头部 → **Gutendex**（`meta_from_gutendex`）→ 古登堡 `?format=json`（最后兜底）。
- **正文直链**：`book_urls_by_id`/`book_urls` → **Gutendex `text_urls(gid)` 优先**（取 `formats` 的
  `text/plain` 各编码），`files/{id}.txt → -0 → cache/epub/pg{id}.txt` 三链接兜底。
- `gutendex_client.get_book()` **进程内缓存**（元数据与直链共用一次请求）；`_get_json` 重试 3 × 30s
  = 最多 ~2 min/本（不可达时降级）。`gutenberg_fetch.py`（遗留下载器）同步。

## 其它关键模式
- **注释三语释义**：annotation 条目 = `word/pinyin/zh_cn/zh_tw/en/note/multi/rare`；
  - 中文书：来源「人工精编 override > 新华字典自动 > CC-CEDICT 英文」，生成见 `fill_glosses.py`。
  - 英文书：难词由 ECDICT 常用词表判定（非停用词 + 长度≥3 + 不在前 N 常用词），
    释义来源「ECDICT（中文/英文/音标）> 网络词典字典（英文释义 + IPA）> 缓存」；词存小写，
    前端 `reader.js` 对 ASCII 词做大小写不敏感匹配（正文句首可能大写）。
  - 当前覆盖：中文书 52,298 条注释（简繁 87.1%、英文 94.3%）；英文书 50,671 条（简繁 97.7%、音标 75.9%）。
- **词库双轨**：`wordbank.json`（中文单字/词，供分词最大匹配复用）与 `wordbank_en.json`（英文难词）。
- **三档阅读模式**：新手/进阶/专家 = 字号 + 注释密度；档位存 localStorage(`annLevel`)，前端按 `rare/multi` 过滤。
- **构建双布局**：`网站` 根目录（Cloudflare 直出，部署根）+ `dist`（`deploy/build.sh` 产出，**gitignore**、
  仅本地/备用）两套并存，路径类改动需同时兼容。
- **只读预览（--dry-run）**：解析元数据打印预览表后即返回，**不下载、不入库、不写文件**（连失败日志也临时屏蔽）；
  有原文显示实际切分器，未下载则只显示元数据 + 切分标「待下载」。
