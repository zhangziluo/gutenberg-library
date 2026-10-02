# Tech Context（技术背景与约束）

> 项目：古登堡计划中英电子书在线阅读网站（一堆古书）。本地开发 + Cloudflare Pages 部署。

## 平台硬约束（Cloudflare Pages，无法提升）
- **单文件 ≤ 25 MiB**（超出即构建失败：`Error: Pages only supports files up to 25 MiB`）。
- **静态资源文件总数上限 ≈ 20,000 个**（大量入库时须留意文件数预算）。
- 大文件必须**拆分**或**外挂 R2**，不能打包进单个 JSON 交付。

## 现状核查（2026-09-17）
- 书库共 **106 本**（`library-index.json`：經部 9 / 史部 5 / **子部 77** / 集部 7 / 近現代文學 8；
  `data/books/` 106 个 JSON，其中 12 本英文书）。
- `网站/_site_data/`：**115 个 JSON**；最大的单书约 **4.0 MiB**（施公案 4044 KB、Walden 4032 KB）——
  远低于 25 MiB 上限。轻量索引 `网站/_site_data/books.json` **114 条目 / 13.6 KB**。
- `dist/`（`deploy/build.sh` 产出）：**155 文件 / 100 MB**，最大单文件同上（**未被 git 跟踪**，`.gitignore` 含 `dist/`）。
- 部署方式：Cloudflare Pages，根目录 = `网站`，构建命令 `exit 0`（纯静态直出，不跑 deploy/build.sh）。
- 最近提交：`afe688d`「更新书库: 新增12本, 更新94本」（252 文件 / +1,928,324 −133,223）→ 已推送。

> **追加核查（2026-09-29 晚）**：新增前端词表 `网站/_site_data/vocab_final.json`（45,161 行 **6 元**：
> 词形/简体形/词次/书数/**definition**/**need_ai**；**2.89 MiB** / 3,028,165 B，md5 `db8c77bf0ad554a6fda3cbe02bb2364e`，
> 生成 `2026-09-29T23:05:48`）→ `_site_data` 共 **115 个 JSON**，最大单文件仍 Walden / 施公案（~4.0 MiB）。
> 新增 `tests/vocab-matcher/`（6 文件，**不进部署产物**）；`dist/` ≈ 102 MiB（本地/备用，未跟踪）。
> 词表 2.89 MiB ≪ 25 MiB 上限（`definition_fill.py` 在 >24 MiB 时告警）。

> **追加核查（2026-10-01）**：书库 **113 本**（`data/books/` 113 JSON；`网站/_site_data/` = 113 单书 +
> `books.json` + `vocab_final.json`）。本日新增/变更：
> - **维基文库书源**：`文本/新书/wikisource_complete_toolkit/`（5 文件）+ `文本/新书/wikisource_import.py`；
>   产物 `novels_json/`、`epubs/` 已 gitignore。`add_books.sh --source wikisource` 一键入库。
> - **书库页重写**：新增 `网站/css/library.css`、`网站/js/library.js`，重写 `网站/library.html`（封面网格 +
>   前端分页/筛选/排序）；`book.html` + `js/book.js` 增详情页 hero（大封面/批注者/特色标签/开始阅读）。
> - **数据 schema**：`网站/assets/data/books-data.json` 每本 **18 字段**（新增 `book_id/summary/chapter_count/
>   commentator/highlights/source_url/license/added_at/read_count`；`added_at`/`read_count` 为静态站占位）。
> - **书源**：古登堡下载默认走 **Gutendex**（`gutendex_client.text_urls` 优先，files/cache 三链接兜底）。
> - 近期提交（新→旧）：`487178e` → `71d7901`(流水线自动) → `580ad00` → `e4c93c0` → `6db5d63` → `dd11b63`
>   → `527300f` → `b7e04a8` → `ad388d8` → `68be37c` → `9a0837a` → `f075b16` → `f5f9715` → `4038d61`（维基文库起）。

> **追加核查（2026-10-02）**：书库大幅扩容 + 释义面板上线 + 分章修复（**工作区未提交、未推送**）。
> - **规模**：`data/books/` ≈ **676 JSON**（`library-index.json` 子部 676）；`网站/_site_data/` **677 JSON**
>   （原 105 中文 + 600 英文精选；同名多版本会互相覆盖）；`dist/` **570 MiB / 977 文件**（未跟踪）。
> - **单文件体积**：最大单书 ≈ **4.3 MiB**（英文书含注释）≪ 25 MiB；词表 `vocab_final.json` ≈ **3.0 MiB**。
> - **词典分片**：`网站/_site_data/dict/{kangxi,shuowen}/0..127.json`（康熙 91 KB/片、说文 4 KB/片，共约 12 MiB / 256 文件），
>   前端按「首字码点 % 128」按需加载。
> - **前端新增**：`reader.html` 的 `<aside id="dict-panel">`（**仅桌面端**，≤1099px 隐藏）+ `reader.js` 面板逻辑；
>   `global-ai.js` 选中填 AI 改为**右键（contextmenu）触发**。
> - **分章规则**（`~/gutenberg_project/scripts/cleaned_to_books.py`）：`CHAPTER/BOOK/PART` + **戏剧 `ACT/SCENE`**
>   （英文 `ACT I` / `FIRST ACT`、拉丁 `Actus Primus` / `Scoena Prima`，**按场拆章**）+ **标题式行**（大写 / Title Case 独立行）；
>   另有碎片过滤（<30 字）、同名章去重（保留最长）、超长兜底（>10 万字按段落近似切分）。`preview_split.py` 为入库前检查工具。
> - **旁路产物**（**不在仓库内**）：`~/gutenberg_project/`（脚本+进度）、`~/gutenberg_cleaned/`（清洗 22G）、
>   `~/gutenberg_en|zh|other|zh_dup/`（分流，other 5.5G）、`~/downloads/cache/epub/`（已清空）。
> - **文件数预算**：`_site_data` 677 + dict 256 ≈ **933 文件**，距 CF Pages 20,000 上限充裕；**若继续全量入库 6 万本会触顶**，需目录化 / R2。


## 部署要点
- `网站/_redirects`：仅含旧分类地址的 301 规则。
- `网站/js/common.js`：`DATA_BASE = '_site_data/'`，按 `_site_data/{書名}.json` 按需拉取单书。
- 首页（`index.html`）由 `daily-sentence.js`（每日一句）/ `home-search.js`（全站搜索）/ `daily-gua.js`（今日一卦）驱动，不依赖 `js/index.js`。
- `网站/js/reader.js`：正文渲染 + 简繁转换 + 注释小卡；**打标交给 `js/vocab-matcher.js`**
  （中文 Trie 最长前缀匹配、英文整词正则 → `<wise data-word data-key>`；TreeWalker + 空闲分批）。
  旧实现（`annotations[].word` 贪心 + 首字索引的**字符滑动**匹配）已删除——它会把 `mornin'` 截成
  `mornin`、把中文词拆成单字散列。

## 数据与脚本（文本/新书/）
- `gutenberg_import.py`：古登堡新书全流程（下载 → 清洗 → 切分 → 注音/难词注释 → 合并到 `_site_data`）。
  - 中文书：`forward_max_split` 词库最大匹配 + 拼音 + 难字注释；各批新增逐本切分器（hui/zhang/chu/ze/juan/lunyu/fanlu…）。
  - 英文书（`--lang en`）：`en_chapter` 切分 + ECDICT 词频挑「英文难词」写 annotations。
  - 元数据链：**本地 raw 头部 → Gutendex → 古登堡 API（兜底）**。
  - 检索/预览（只查不入库）：`--search "词"`、`--list-by-lang en --max N`、`--dry-run`。
- `gutendex_client.py`：Gutendex 元数据客户端（同目录，集中管理）。`search_books`（透传参数 + 自动翻页，
  可选 `max_results`/`max_pages` 早停）、`get_book`、`normalize_gutendex_book`；
  请求间隔 0.3s、失败重试 3 次指数退避（0.6/1.2/2.4s）、404 返回 None 由调用方降级。
- `fill_glosses.py` + `gloss_lib.py`：三语释义回填。
  - 中文：`data/cedict_single.json`（CC-CEDICT）/ `xinhua_word.json`（新华字典）/ `gloss_override.json`
    （人工精编）/ `pinyin_readings.json`。
  - 英文：**ECDICT 分片** `data/ecdict_en/ecdict_{a..z}.json`（按首字母，最大 7.4 MiB；`ecdict_shard()` 惰性加载
    + LRU≤3 片）+ `data/common_words_en.json`（前 5000 常用词）；网络词典 `api_*` 主源
    freedictionaryapi.com、备源 dictionaryapi.dev（不可达即熔断），缓存 `data/ecdict_api_cache.json`。
  - CLI：`--no-network`（离线）/ `--api-budget=N`（网络请求预算）。
- `parse_ecdict.py`：下载并解析 ECDICT（MIT）→ 生成按首字母分片的英词释义库与常用词表（本地数据，已 gitignore）。
- `add_books.sh` / `pipeline.sh`：一键入库与收尾流水线（详见 systemPatterns）。
- `vocab_extract.py`：词汇抽取与分词（英文正则词形 + 中文 jieba/双向最大匹配），产出
  `文本/新书/vocab_raw.json`。CLI：`--granularity=word|book|chapter`、`--min-freq-zh/-en`、
  `--contexts/--ctx-width/--books-max`、`--select/--select-file`（划选词）、`--zh-dict/--min-dict-freq`、
  `--selftest`（规则回归）、`--dry-run`。**依赖 `jieba`**（`pip3 install --user --break-system-packages jieba`；
  缺失自动降级双向最大匹配）。全库默认 ≈2.5 min / 8.1 万条 / ~18 MiB。
- `slim_books_index.py`：把 books.json 重建为轻量索引（构建产物也调用）。
- `build_vocab_final.py`：把 `vocab_raw.json` 收敛成**前端词表** `网站/_site_data/vocab_final.json`
  （默认 45,161 条中文多字词 = `[词形, 简体形, 全库词次, 书数]`，**4 元行版本 0.92 MiB**；不收单字，`--with-en` 才收英文词）。
  CLI：`--min-freq/--min-len-zh/--min-len-en/--dry-run/--selftest`；写后回读校验（可解析 + 行数一致 +
  词形合法：中文纯 CJK、英文最大词形）。阅读页 `js/vocab-matcher.js` 用它建 Trie 定**词边界**；
  `_headers` 给它加了 1 天浏览器缓存。（产出为 4 元行；**释义由下一步 `definition_fill.py` 补成 6 元**。）
- `definition_fill.py`（**新增 2026-09-29 晚**，29.6 KB）：给词表**回填释义** —— 4 元行 → 6 元行
  `[词形, 简体形, 词次, 书数, definition, need_ai]`，前端词卡因此可**不依赖单书 `annotations`** 显示词义。
  来源链（整词 → 单字 → 逐字合成 → `待补`）、繁简对齐（`char_variants`）、自我引用清理（`strip_self_ref`）
  与硬保证详见 systemPatterns。**前置**：先跑 `build_vocab_final.py`。
  CLI：`--dry-run / --limit / --out / --zh-word-src / --no-auto-zh-src / --max-len / --network / --selftest`
  （自检 26 项，全绿）。实测：45,161 行 / 有释义 12,947（28.7%，**全部 need_ai**）/ 待补 32,214 /
  **2.89 MiB**。词级中文源（`shuowen.json` / `kangxi.json` / `cedict_words.json` / `hanyu_words.json`）
  **仓库暂无**（`data/` 只有单字源）→ 多字词目前只能逐字合成或 `待补`；放入即自动命中，无需改代码。
- `tradify.js` / `pinyin_helper.js`：opencc 简→繁、pinyin-pro 注音（node 子进程）。
- `scripts/classify_books.py`：DeepSeek 自动分类（四部 + 英文 level）。**当前未接通**：默认输入
  `data/books.json` 不存在，且需 `DEEPSEEK_API_KEY`；`pipeline.sh` 已加守卫，缺失即跳过。
- `scripts/reclassify_en_books.py`（**新增 2026-10-02**）：按四部分类法重分「已入库英文书」——
  内置 `EN_CLASS`（书名 → 部类/子类）映射，把 `library-index.json`（跨部搬移 + 改 subcategory）、
  `网站/assets/data/books-data.json`（category key / subcategory / summary）与 `data/books/pg*.json`
  一并改写；`--dry-run` 预览、`--also <副本>` 同步 `progress/full/` 备份（防分批推送回退）。
  写入前自检「英文书全覆盖 + 分类 key 合法」，失败不落盘。当前结果：英文 79 条 → 子部 24 / 集部 55。

### 维基文库书源 / 书库页（新增 2026-10-01）
- `wikisource_complete_toolkit/{wikisource_toolkit.py,license_detector.py,epub_builder.py,test_license_offline.py,QUICKSTART.md}`：
  维基文库抓取（`fetch`/`list`/`search`）+ 许可合规闸门（`prop=templates`）+ EPUB 生成；依赖 `requests`/
  `beautifulsoup4`/`ebooklib`（已装 `.venv`）。产物 `novels_json/`、`epubs/` 已 gitignore。
- `wikisource_import.py`：`novels_json/{书名}.json` → `data/books/{key}.json` + `library-index.json`
  （`source=维基文库`）+ `merge_to_site()`/`slim_books_index()`；`--key/--author/--category/--subcategory/
  --label/--no-merge/--force`。
- `build_wikisource_index.py` + `wikisource_index.{md,json,tsv}`（**新增 2026-10-02**）：
  **维基文库中文电子书索引**（1642 种：中土 1083 / 域外漢籍 559；已入库 14；推荐 ⭐132）。
  数据源为 zh.wikisource 的 四部/四庫全書/十三經 等分类快照 + `prop=info`（长度）与
  `prop=links&plnamespace=102`（作者，>5 位视为 navbox 污染弃用）。采集/入库说明见 `wikisource_index_guide.md`。
  `--from-json` 只按现有 json 重建目录；**元数据缺口回填** + **`in_library` 自动刷新**；
  同时生成 `网站/assets/data/wikisource-pending.json`（书库页「待入库」预览数据）。
- 维基文库批量流水线（**新增 2026-10-02**）：
  - `wikisource_index_backfill.py`：补抓缺失页面元数据（断点续跑；`.ws_meta_cache/` 已 gitignore）。
    实测长度覆盖 1341→1590、作者 893→937（301→剩 52）。
  - `wikisource_batch.py`：`list/fetch/commands/ingest/merge`；候选＝推荐 ⭐ 未入库（122 本）；
    断点续跑（`_ws_fetch/*.tsv`）；自动用 `.venv` 解释器跑 toolkit；`ingest` = 逐本入库
    （智能分章 + 生成注释）→ `fill_glosses.py` 释义回填 → `merge_to_site`（可选 build）。
  - `wikisource_recommended.sh`：上面三步的一条龙。
  - `wikisource_import.py` 新增 `--title`（去版本后缀）/`--split auto|none`（智能分章）/
    `--label`（缺省按分章结果判定）/`--annotate`（默认开，复用 `annotate_book`）。
  - `wikisource_toolkit.py`：`_sort_key` 前置篇（序/凡例/楔子）恒在前 + 中文数字按数值排；
    `get_subpages` 经 `existing_titles()` **过滤红链**（避免 missingtitle 空壳）。
  - `gutenberg_import.merge_pending()` 兼容 list 字表（原 dict-only 会崩）。
  - 书库页「待入库」预览：`library.html/js/library.js/css/library.css` 范围切换 + 「只看推荐 ⭐」+
    卡片「📋 复制入库命令」；测试 `tests/library/library-pending-test.js`（jsdom，17 项）。
  - `merge_to_site.py` 改为**薄封装**（原来那份独立实现 `CAT_KEY` 缺「叢部」、遇 叢部 书会 KeyError，
    且无人调用）→ 统一委托 `gutenberg_import.merge_to_site()` + `slim_books_index`，
    新增 `--dry-run`。CLI 不变：`python3 文本/新书/merge_to_site.py`。
  - **README.md 重写**（2026-10-02）：书库现状数字（195 本 / 7090 篇 / 六部明细 / 双书源）、
    核心功能（释义面板、三档、简繁+三语、待入库预览）、页面/数据三层结构、跑起来与部署、
    工具链表、测试命令、贡献流程（数据 schema 真实化，删掉已不存在的 `books/[分类]/…` 与 `data/glossary.json`）、
    来源与许可；并加回「接下来」路线（继续搬维基文库 / 生词本 / 英文练习）。
- `网站/{library.html,css/library.css,js/library.js}`：封面网格书库页（前端分页 20/页 + 分类 Tab + 排序 + 搜索，
  `?cat/?sort/?q/?page`）；`book.html` + `js/book.js` 详情页 hero。
- `books-data.json` 生成器（`merge_to_site`）新增：`source_label/source_url_from/license_from/highlights_for/
  COMMENTATOR/CATALOG_GID/_placeholder_added_at/_placeholder_read_count`。

## 测试（`tests/vocab-matcher/`，本地开发用，**不进部署产物**）
- 6 文件：`dom-shim.js`（极简 DOM）/ `dom-test.js`（21 项）/ `integration-test.js`（26 项：真实书 JSON +
  真实 `vocab_final.json` + opencc 简繁）/ `definition-show-test.js`（jsdom 真实页面，6 项）/
  `reader-smoke-test.js`（14 项，`BOOK=` 换书）/ `README.md`（跑法）。
- 跑法（**仓库无根 `package.json`**，jsdom 装在 `/tmp`，用 `JSDOM_PATH` 指定）：
  ```bash
  node -e "const V=require('./网站/js/vocab-matcher.js');console.log(V.selftest().pass)"  # 66
  node tests/vocab-matcher/dom-test.js && node tests/vocab-matcher/integration-test.js     # 21 / 26
  npm i --prefix /tmp/vmtest jsdom && export JSDOM_PATH=/tmp/vmtest/node_modules/jsdom     # 首次
  node tests/vocab-matcher/definition-show-test.js && node tests/vocab-matcher/reader-smoke-test.js
  ```
- 当前状态（2026-09-29 晚，对最终 `vocab_final.json`）：**66/0、21/0、26/0、6/0、14/0 全绿**。

## 本地环境注意事项
- **本机无 `python`，只有 `python3`**；shell 为 **bash 3.2**（`set -u` 下空数组展开、`$VAR` 紧跟多字节字符
  均会出错，写脚本须用 `${VAR}` 且避免空数组裸展开）。
- **VS Code 终端 shell integration 不稳**（2026-09-29）：偶发不上报命令完成（显示
  「Command exited with code 1」但进程仍在跑），且**终端一次只应跑一条长任务**——新命令会尝试复用/关闭旧终端，
  把正在跑的回填进程杀掉，留下半截输出或旧版本产物（曾导致 `vocab_final.json` 被上一轮写盘覆盖）。
  长命令一律 `cmd > /tmp/x.out 2>&1` 重定向 → **读文件**确认 `EXIT=`/统计行；用 `ps`/`stat` 核对产物 mtime。
- 网络到 `raw.githubusercontent.com`、`gutendex.com`、`api.dictionaryapi.dev` 均很慢或不稳定：
  大文件（ECDICT 63 MiB）建议 `git clone` 取；联网步骤可能耗时数十分钟，脚本已内置重试/熔断/缓存。
