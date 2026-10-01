# Active Context（当前状态与下一步）

## 当前（2026-10-01）：维基文库书源 + 书库页重构（封面网格）

> 书库仍 **113 本**；`main` 与 `origin/main` 一致。以下**均已提交**（除非另注）。

### ① 维基文库书源工具链（`文本/新书/wikisource_complete_toolkit/`，4038d61 起）
- 5 文件：`wikisource_toolkit.py`（fetch/list/search）/ `license_detector.py`（许可合规闸门）/
  `epub_builder.py`（EPUB 生成）/ `test_license_offline.py`（离线自检 10 样例）/ `QUICKSTART.md`。
- **合规闸门**：每页调 MediaWiki `prop=templates` 判版权模板（PD/CC/GFDL/GPL/受限/未知），
  `safe_to_use` 才可入库；`--force` 跳过受限页。**两个增强**（f075b16）：子页无直接许可 → **回退继承父页**；
  剔除**非正文子页**（全览/目录/序说/凡例，`NON_CONTENT_SUBPAGES`）。
- **正文提取**（68be37c）：`extract_text_from_html` 重写 — 剥离 `#headerContainer` 页头 / `rt` 注音 /
  `.variant-tooltip` 变体注，按块级元素换行、行内元素拼接（千字文不再逐字拆行）。
- 依赖 `requests`+`beautifulsoup4`+`ebooklib`（已装 `.venv`）；产物 `novels_json/`、`epubs/` 已 gitignore（f5f9715）。

### ② 维基文库 → 书库入库（`文本/新书/wikisource_import.py`，9a0837a）
- `--json novels_json/論語.json --key … --author … --category … --label 篇` → 合规检查 → 写
  `data/books/{key}.json`（含 `section_label` + 每章 `source_url/license/revid`）→ 写 `library-index.json`
  （`source=维基文库`）→ `merge_to_site()` + `slim_books_index`。有重名/重 key 冲突检查；`--no-merge`/`--force`。
- `to_reader()` 支持 `data.section_label` 自定义篇目标签（gutenberg_import + merge_to_site）；
  修 `slim_books_index.py` bug（跳过无 `title` 的非书目 JSON，原先误收 `vocab_final.json`）。
- `add_books.sh` 支持 `--source wikisource`（`--title` 自动抓取 / `--json` 直接入库，ad388d8）。

### ③ 目录页 + 详情页注明来源（f075b16 / b7e04a8）
- `books-data.json` 每本加 `source`（古登堡计划 / 维基文库）→ 目录页卡片徽标 + 全站页脚「双来源」；
  页脚「日程编辑与提醒器」链接 → `https://ics-maker.pages.dev/`（15 个 html）。

### ④ 修复 9 本「整本一节」未分章（527300f，第九批切分器）
- `gaoshi` 高士傳 92 / `wuchuan` 吳船錄 2 / `xingcha` 星槎勝覽 43 / `cipai` 龍川詞 25 / `zhe` 竇娥冤 5 /
  `tangshi` 唐詩三百首 320 / `changsheng` 長生殿 22 / `kuangren` 狂人日記 14 / `exercise` 滬語開路 50。
- 重生成 `data/books/*.json`（**保留原注释**）→ `library-index.json` 章数 + `_site_data` + `books-data.json`。

### ⑤ 书库页重构：列表 → 封面网格（dd11b63 / 6db5d63 / e4c93c0）
- **新增 `网站/css/library.css` + `网站/js/library.js`**，重写 `网站/library.html`：
  - 3:4 封面网格（桌面 5-6 / 平板 3-4 / 手机 2）；封面纯 CSS（方案 B）——五部配色（经深蓝/史赭石/
    子墨绿/集暗紫/丛深灰/**全部棕黄**）、竖排楷体书名 + 作者 + 右下角 `📗/📘`；悬停上浮 4px + 阴影 + 显示简介。
  - **前端分页**（20 本/页，≤20 不分页，`?page=` 保持，切页回顶）；分类 Tab + 排序（热门/最新/书名，
    `Intl.Collator('zh')`）+ 搜索；`?cat/?sort/?q` 同步 URL。**书库页禁装饰性动画**（仅悬停 `transform 0.2s` + 点击反馈）。
- **数据补 18 字段**（`merge_to_site` 生成，保留 `id/description/sections` 兼容）：`book_id / summary /
  chapter_count / commentator / highlights / source_url / license / added_at / read_count`。
  - `commentator`：四大名著（水滸傳·金聖歎 / 三國演義·毛宗崗 / 西遊記·李卓吾 / 紅樓夢·脂硯齋）。
  - `source_url`：古登堡 `Project Gutenberg #XXXX` → `gutenberg.org/ebooks/{gid}`；**目录主书 8 本补
    `CATALOG_GID`**（史記24226/漢書23841/三國志25606/三國演義23950/水滸傳23863/西遊記23962/紅樓夢24264/古文觀止25225，580ad00）。
  - `added_at`/`read_count`：**静态站占位值**（book_id 稳定派生，与前端兜底同算法）；接 FastAPI 后端后替换真值。
- **详情页 hero**（`book.html` + `js/book.js`，e4c93c0）：大封面 + 书名/作者/**批注者** + 简介 + 本版特色标签
  （繁體/注音釋義/分类/来源/许可）+ **[开始阅读]**；元数据取 `books-data.json`，取不到优雅降级。
- 前端数据接口约定见 `网站/js/library.js` 文件头注释；换后端只改 `DATA_URL` 一处。

### ⑥ 古登堡书源默认改走 Gutendex（71d7901 / 487178e）
- `gutendex_client.text_urls(gid)`（取 `formats` 的 `text/plain` 直链）+ `get_book` **进程内缓存**；
  `gutenberg_import.book_urls_by_id`/`book_urls` 改为 **Gutendex 直链优先**，`files/{id}.txt → -0 →
  cache/epub` 三链接兜底；`gutenberg_fetch.py`（遗留下载器）同步。
- **元数据链不变**：本地 raw 头部 → Gutendex → 古登堡 `?format=json`（最后兜底）。
- ⚠️ `71d7901` 是 **pipeline.sh 自动提交**（模板信息「更新书库 (2026-10-01 21:25)」），非规范信息。

### ⏭️ 下一步（待办）
1. **接 FastAPI 后端**：把 `read_count`/`added_at` 换成真值（前端已能直读）；改 `library.js` 的 `DATA_URL`。
2. **维基文库真正入库**：工具链就绪但尚未抓书入库（`千字文` 测试后已回退）；`add_books.sh --source wikisource` 即可。
3. 词表释义精修（32,214 待补 + 12,947 条 need_ai 弱释义）——见下「已完成（2026-09-29）」。
4. 可选：改写 `71d7901` 的提交信息需 `rebase -i` + `push --force`。

## 已完成（2026-09-29）：词表内嵌释义 / 前端匹配重写 / 词汇抽取（均已提交）
### ① 词表内嵌释义：`vocab_final.json` 6 元行 → 词卡直接显示释义（2026-09-29，已提交 3392b02）
- ✅ **`文本/新书/definition_fill.py`（新增，29.6 KB）**：给前端词表 `网站/_site_data/vocab_final.json`
  的每一行**回填释义**，行由 4 元扩成 6 元 —— `[词形, 简体形(可空), 全库词次, 出现书数, definition, need_ai]`。
  - **中文来源链**：整词优先（`gloss_override` → 词级中文源）→ 单字兜底（人工覆盖 → 新华字典 →
    CC-CEDICT 英 → makemeahanzi 英）→ **逐字合成**（`君：…；子：…`，need_ai=true）→ 全无则 `待补`。
  - **词级中文源**：`--zh-word-src` 或 `文本/新书/data/` 自动发现（`cedict_words.json` / `shuowen.json` /
    `kangxi.json` / `hanyu_words.json`）；**当前仓库一个都没有**（只有单字源）→ 多字词只能合成／待补。
  - **英文**：整词精确匹配（禁前缀/子串：`morn` 永不命中 `morning`）→ ECDICT 中文/英文 → 网络词典缓存
    （`--network` 才发请求）。当前词表默认不收英文词（`en: 0 行`）。
  - **繁体逐字合成按字回退简体键**：`無學` → `无` + `學` ⇒ `無：没有；不；學：学习；学问`。
  - **「同'X'：」自我引用清理**：单字释义常以 `同'無'：①…` 开头（新华字典的异体/形近交叉引用）→
    当 X 是本字**或繁简对应字**时去掉该前缀。繁↔简单字对应表**由词表自身推出**（`char_variants()`：
    长度一致且繁简不同的行 ⇒ `無學→无学` 给出 無↔无、學↔学，共 3,264 组），因此简体词 `无不` 的
    「无：同'無'：①没有」也整理成「无：①没有」。**实测：以「同'X'：」开头的释义 0 行**（回归探针已核）；
    库中另有 1,458 行是释义**中间**的正常交叉引用（「可同'否'」「词尾，同'么'」）——必须保留，不可一概删净。
  - **硬保证（每次运行都自检，失败即不落盘）**：行数不变 / 每行 6 元 / **前四元逐项未被改写** /
    `need_ai` 是布尔 / 词形仍合法；`.part` 原子替换 + 写后回读校验。`--selftest` **26 项全绿**
    （对抗性样例：整词优先、逐字合成、繁简回退、英文禁前缀、幂等、`strip_self_ref` / `char_variants`）。
  - **实测（全库）**：45,161 行 ｜ 有释义 **12,947（28.7%）** ｜ 待补 32,214 ｜ need_ai 45,161
    （有释义的**全部**是逐字合成 = 弱释义，故全表 need_ai）｜ **2.89 MiB**（3,028,165 B，
    md5 `db8c77bf0ad554a6fda3cbe02bb2364e`）｜ 生成时刻 `2026-09-29T23:05:48`。
    **远低于 Cloudflare 25 MiB 上限**（>24 MiB 脚本告警）。
  - **用法**：`python3 文本/新书/definition_fill.py`（原地回填）/ `--dry-run` / `--limit N --out /tmp/vf.json`
    / `--zh-word-src 路径` / `--no-auto-zh-src` / `--max-len 160` / `--network` / `--selftest`。
    前置：`python3 文本/新书/build_vocab_final.py`（4 元行）→ 本脚本（6 元行）。
- ✅ **前端链路打通（`vocab-matcher.js` v1.2.0 + `reader.js`）**：
  - `vocab-matcher.js` 行解析：`raw[4]` → `definition`、`raw[5]` → `need_ai`（**原先 `raw[4]` 被当成
    pinyin，属误读**）。新增 `hasDef()` / `PENDING_DEF`（`待补/待補/TBD/空白` 不算释义），
    `isGloss()` 纳入 `definition` ⇒ **词表词只要行内有释义就能标**（`kind` 判定与密度过滤同步放行）；
    导出 `hasDef`；`selftest()` 59 → **66 项**（v1.2.0）。
  - `reader.js`：新增 `ANN_VAGUE_DEF`（占位值不算释义）与 `annGlossText()` 的词表 `definition` 兜底
    （语言槽 `zh_cn/zh_tw/en` 优先 → 词表行 definition）；词卡标签 `詞表詞` / **`AI 待補`**（need_ai=true）。
  - **实测**：点 `無邪` → 词卡「無：①没有（无中生有）；②不、不论（无妨、无论）；③毋、不要；邪：…」
    + 标签「AI 待補」；占位词（如 `獃獃`）不标、不显示。
- ✅ **测试矩阵（`tests/vocab-matcher/`，新增目录，未提交）**：`dom-test.js` 21/21、
  `integration-test.js` **26/26**（新增 D. 词表内嵌释义：6 元行 45,161/45,161 ｜ 有释义 12,947 ｜
  待补 32,214）、`definition-show-test.js`（**新**，jsdom 打开真实页面：内嵌释义命中 22、待补词被误标 0、
  点 `無邪` 词卡显示释义 6/6）、`reader-smoke-test.js` 14/14 ×3 本；`README.md` 同步。
  ```bash
  node -e "const V=require('./网站/js/vocab-matcher.js');const r=V.selftest();console.log(r.pass,r.fail)"
  node tests/vocab-matcher/dom-test.js && node tests/vocab-matcher/integration-test.js
  npm i --prefix /tmp/vmtest jsdom        # 仓库无根 package.json
  export JSDOM_PATH=/tmp/vmtest/node_modules/jsdom
  node tests/vocab-matcher/definition-show-test.js && node tests/vocab-matcher/reader-smoke-test.js
  ```
- ⏭️ **下一步（待办）**：
  1. 想要**真词义**（非逐字合成）：往 `文本/新书/data/` 放 `shuowen.json` / `kangxi.json` /
     `cedict_words.json` / `hanyu_words.json`（或 `--zh-word-src`），重跑即整词命中（**不需要改代码**）；
  2. 32,214 条 `待补` + 12,947 条弱释义（need_ai=true）→ **AI 精修**（前端已用「AI 待補」标出待精修项）；
  3. 词表 `definition` 与单书 `annotations` 存在**同词双份释义**（现规则：语言槽优先、词表兜底）——
     是否统一优先级 / 是否把词表释义回填进 annotations 待定；
  4. ✅ 提交推送：`tests/`、`文本/新书/{build_vocab_final.py,definition_fill.py}`、`网站/js/vocab-matcher.js`、
     `网站/_site_data/vocab_final.json`、`网站/js/reader.js`、`网站/css/style.css`、`网站/reader.html`、
     `网站/_headers`、`文本/新书/vocab_extract.py` —— **已提交**（`b650f4b` / `3392b02`）。

### ② 前端匹配重写 / 词汇抽取重写（2026-09-29，已提交 b650f4b）
- ✅ **前端匹配与标注重写：`网站/js/vocab-matcher.js`（2026-09-29）**：彻底替换 `reader.js` 里
  「按字符索引 + 定长滑窗」的旧匹配（旧实现会把英文截成字母组合、把中文词拆成单字散列）。
  - **英文**：正则**整词**匹配（拉丁字母串 + 词内连接符 + 允许词尾省略撇号，边界锚定）——
    `mornin'` 取整词（旧实现只取到 `mornin`，词卡标题也随之截断）；
    查找链：整词 → 去词尾省略撇号（`mornin'`→`mornin`）→ 去所有格（`Lear's`→`lear`）
    → 仅在连接符处拆段（`old-fashioned` → `old` + `fashioned`）。**绝不在字母中间切**。
  - **中文**：预生成词表 `网站/_site_data/vocab_final.json`（4.5 万词 / 0.92 MiB）建 **Trie**，
    TreeWalker 遍历文本节点做**最长前缀匹配**（Max Match：`不知 > 不 + 知`）；
    命中整体成一个 `<wise>`，词内**不再散成单字**（`人不知` 是一个标签，而不是只标中间的「不」）。
    整词无释义但成分字有释义 → 整词一个标签 + `data-parts`（词卡列成分字释义）；
    繁体词自动挂简/繁双键（`說服` ⇄ `说服`）→「繁→简」显示模式仍能命中（annotations 单字键用
    opencc 兜底补简体形）。
  - **渲染**：命中包 `<wise data-word="完整词形" data-key="词典键" data-lang=zh|en class="ann-word …">`；
    旧 `.ann-word/.ann-hard/.ann-rare` 类名保留（CSS/点击逻辑无需改）；词卡标题 = `data-word`
    （**完整词形**，`HARKER’S`、`mornin'` 不再截断），释义按 `data-key` 查。
  - **性能**：`requestIdleCallback` 分批（每片 ~6 ms；无该 API 用 `setTimeout(8)`），建表与打标都让出
    首屏；重渲染/换档 → 代次 +1，旧任务自动作废；只对**确有命中**的文本节点写 DOM（一次
    `replaceChild` → 移动端不产生多余空文本节点、不排错位）。
    密度策略 `window.VOCAB_WRAP = 'gloss'(默认) | 'all' | 'rare'`；`window.VOCAB_FINAL_URL = null`
    可彻底关掉词表（仅用 annotations）。
  - **数据**：新增 `文本/新书/build_vocab_final.py` → `网站/_site_data/vocab_final.json`
    （行 = `[词形, 简体形, 全库词次, 书数]`；不收单字、默认不收英文词）。词表提供**词边界** + **行内释义**
    —— **现已扩成 6 元行 `[词形, 简体形, 词次, 书数, definition, need_ai]`，见 ①**；
    单书 `annotations` 仍是语言槽（简/繁/英）与人工精编释义的来源。
  - **硬保证 + 自检**：分段拼回 == 原文本（textContent 不变 → 复制/下载/划选/AI 全不受影响）；
    英文命中必为最大词形（前后不接拉丁字母）；中文命中不跨 CJK 段；重叠永远取最长。
    `VocabMatcher.selftest()` 59 项（**已升至 v1.2.0 / 66 项：词表行内嵌释义 definition / need_ai，见 ①**）；
    浏览器内 `reader.html?vmselftest=1` 跑纯函数 + DOM 两套自检。
  - **实测**：纯函数 59/59（**现 66/66**）、DOM 层（Node + 极简 DOM shim：TreeWalker/空闲分批/跳过区/幂等/取消）21/21、
    真实书集成（論語 原文 + 繁→简、Walden、Dracula）23/23（**现 26/26**，新增「D. 词表内嵌释义」）、
    jsdom 页面冒烟（論語 84 个 `<wise>`、
    Walden 1036、Dracula 876；点击词卡标题 = 完整词形）14/14 ×3 本、生成脚本 `--selftest` 11/11；
    建表 論語 197 ms（就地归并优化前 508 ms）、施公案 3.8 万字打标 ~50 ms；
    旧算法对照：論語 317/400 段命中不同（旧把 `不亦樂乎` 拆成 `不/樂/不`），
    `Mornin'` → 旧包 `Mornin` ／ 新包 `Mornin'`。
  - **回归**：`reader.js` 只留渲染 + 简繁转换 + 词卡（打标全交给 vocab-matcher）；`style.css` 增
    `wise{}`（display:inline / word-break:keep-all）与 `.ann-pop-parts`；`reader.html` 引入
    `js/vocab-matcher.js`；`_headers` 给 vocab_final.json 加 1 天缓存；`deploy/build.sh` 无需改
    （整目录复制）→ dist 156 文件 / 102 MiB。
- ✅ **词汇抽取与分词 `vocab_extract.py` 重写（2026-09-29）**：新脚本取代原实现，
  从 `data/books/*.json`（105 本）抽取词汇 → `文本/新书/vocab_raw.json`（**已加入 .gitignore**）。
  - **英文**：正则词形 `[拉丁字母全集]+(?:[词内连接符][拉丁字母]+)*`——`Buda-Pesth`、`don’t`、
    `coöperate`、`quâ` 整体保留；小写归一（弯撇号 ’ʼ→'、真连字符 ‐‑→-），原文大小写存 `variants`；
    过滤纯数字、单字母（仅留 a / I）、126 个常见停用词。**无任何固定长度滑窗**。
  - **中文**：逐字繁→简（`trad_simp_map.json` 键值均单字 → `str.translate` 长度 1:1 保偏移）
    → jieba **只在 CJK 连续段内**按词切分（HMM 关）；词典 = 内置古汉语词表（550 词，虚词组合/
    称谓/制度/名物/常用成语）+ `--zh-dict`（默认 `data/guwen_dict.txt`，支持「词 频次 词性」）。
    例外：jieba 词典含语料噪声词条（如 `国之君 20 nr`）会把古文错并 → 凡「长度≥3 且词典频次
    < `--min-dict-freq`(默认100) 且不在自有词典」的词**回退双向最大匹配**；jieba 缺失则全量降级
    最大匹配（只用词典、不造词、不滑窗）。
  - **硬性自检（每次运行，失败即报错且不落盘）**：① 中文切词必须**原样重建**该 CJK 段
    （拼接 == 原文 → 无截断/丢失/重叠/跨段粘连）；② 英文词形必须是**最大词形**（前后紧邻不得
    仍是拉丁字母/连接符 → 截断必被检出）；③ 写后回读（JSON 可解析 + 记录数一致 + 必备字段）。
    （自检曾当场抓出 3 个真 bug：`en_tokens` 未做弯撇号归一、zh 偏移基准错位、
    Walden 变音符词 `quâ` 被 ASCII 正则截断、南腔北調集 `eAUAnG\`GDOKL` 误报——已全部修掉。）
  - **粒度** `--granularity=word|book|chapter`（默认 word = 每词一条全库聚合；
    book = 词×书（`chapters` 章号压缩串）；chapter = 词×书×章 = 需求字面格式）。
    **流式写**（先写 words，收尾补 `_meta`/`summary`，`.part` 原子替换）→ 内存与书库规模无关。
  - **实测（全库 105 本默认参数）**：137.7 s ｜ 8.1 万条 ｜ 26.7 MiB ｜ 自检 4,316 章 /
    7,341,089 词次全过 ｜ 中文词 53,706（单字 8,545 / 多字 45,161）、英文词 27,719。
  - **独立复核**（`/tmp/audit2.py` 思路）**100% 通过**：81,425 条上下文全部逐字出现在对应章节原文、
    全部含该词；英文全小写、无残留单字母/数字；中文词纯 CJK；无章号越界。
  - **用法**：`python3 文本/新书/vocab_extract.py [书名…] [--granularity=…] [--min-freq-zh=2]
    [--min-freq-en=1] [--contexts=1] [--ctx-width=20] [--books-max=8] [--select 词1,词2]
    [--select-file 生词.txt] [--zh-dict 词典.txt] [--selftest] [--dry-run]`；
    依赖 `jieba`（`pip3 install --user --break-system-packages jieba`，缺失自动降级）。

## 第八批（2026-09-29）— 「整本一节」批量修复（29 本）+ 菜根譚下架
- ✅ **「整本一节」批量修复：第八批 29 本（2026-09-29，已入库+构建）**：为 **23 本中文书 + 6 本英文书**
  逐本定制切分规则，书库仍 106 本但章节结构重排（喻世明言 1→40 卷、日知錄 1→1008 條等）。
  - **新增 15 个切分器**（`gutenberg_import.py`「第八批新书切分器」区）：
    - `juan_cat` 第X卷+篇名同行（明鏡公案/閱微草堂筆記/喻世明言/警世通言/一枕奇）——
      分隔符兼容 Tab／全角空格／**不换行空格 U+00A0**（警世通言用 U+00A0，首版曾漏切）；
    - `pin` 六祖壇經 X品第N；`fen` 金剛經 X分第N；`guofan` 《篇名》韓非子；
      `kuokuo` 〔篇名〕公孫龍子；`jianjiao` 〈篇名〉三略；`mtz` 字间空格「穆 天 子 傳 卷 之 一」；
      `dongming` 《漢武帝別國洞冥記卷第X》；`rizhilu` ●卷X 作前缀 + ○條目 作章；
      `guiguzi` 篇名第X／篇X + 本經陰符七篇七子篇；`baopuzi` 《抱朴子‧篇名》逐條（重名加序）；
      `titles` 白名單標題；`auto_head` 結構式短題（空行後短行 + 其後首个非空行为长行）；
      `fo42` 佛說四十二章經按段落切「序+42章」并按内容去重（源文件正文整体重出一次）；
      `en_titles` 英文按 TOC 標題清單（支持標題折行续行、空章丢弃）。
  - **新增配置能力**：`drop`（正則剔除卷/編/數字序號行）、`dedup_titles`、`maxlen`、
    `drop_until_col0`（英文书跳过封面页与缩进目录，只认顶格行；避免 Walden 封面
    "ON THE DUTY OF CIVIL DISOBEDIENCE" 生成假章）。
  - **英文书元数据修复**：#146 实为 **A Little Princess**（Frances Hodgson Burnett），
    原先记为「A Little Prince / Unknown」；已改并删除陈旧 `网站/_site_data/A Little Prince.json`，
    `slim_books_index.py` 重建 `books.json`（114 本）。
  - 章数结果：日知錄 1008、天妃顯聖錄 88、晁氏儒言 83、賈誼新書 70、Grimms 62、鹽鐵論 60、
    韓非子 53、佛說四十二章經 43（序+42章）、喻世明言/警世通言 各 40、抱朴子 38、
    Arabian Nights 35、管子 34、金剛經 32、閱微草堂筆記 24、明夷待訪錄 21、鬼谷子 19、
    Walden/A Little Princess 各 19、Jungle Book 14、Wind in the Willows 12、一枕奇/六祖壇經 各 10、
    公孫龍子/穆天子傳 各 6、明鏡公案/洞冥記 各 4、三略 3、傳法心要 2。
  - **仍保持「整本一节」**（原文本无标题结构可切，合理保留）：幽明錄、菜根譚、李娃傳、虬髯客傳。
  - **#24040《菜根譚前後集》已撤下书库**（用户拍板，2026-09-29）：古登堡**官方源**正文整体乱码
    （例：`頦菜鈭亦剝剖亙蝎寧銋拙嗆`），重新下载字节完全一致，且 big5/gbk/cp950/euc-* 互转全部失败
    → **编码不可逆**。处理：从 `quick_books.json` 删除 `pg24040`，删 `data/books/pg24040.json`、
    `网站/_site_data/菜根譚前後集.json`，重建 `library-index.json`（105 本：經 9 / 史 5 / 子 76 / 集 7 /
    近現代 8）、`_site_data/books.json`（113 本）与 `books-data.json`（113 本）。
    `raw/24040.txt` 保留作证据；`BOOK_YEAR/BOOK_DESC` 中的「菜根譚前後集」条目为无害遗留（换到正确源可直接复用）。
    另从 `wordbank_pending.json` 裁去 36 个「已不在任何现存书注释里」的乱码孤儿字（7130 → 7094）。
  - 回归链：106 本全量 `_build_one` **0 异常 / 0 空切分** → 入库 29 本 →
    `fill_glosses.py --no-network`（58 文件 / 218,482 条；简繁 91.7%、英文 94.6%；
    英文词 21,331 → 中文释义 94.6%、英文释义 90.3%、音标 76.4%）→ `deploy/build.sh`
    （dist 101 MiB / 155 文件）。

## 已知待办（按优先级）
- ✅ **词级释义已回填（2026-09-29 晚完成，见「已完成（2026-09-29）①」）**：`definition_fill.py` 把词表 4 元行扩成 6 元
  （`definition` / `need_ai`），前端词卡可直接显示释义（不再只能列 `data-parts` 成分字）。
  **但质量未达标**：45,161 行里 12,947 条有释义的**全部是逐字合成**（need_ai=true），另有 32,214 条 `待补`。
  ⏭️ 要真词义：把**词级中文源**放进 `文本/新书/data/`（`cedict_words.json` / `shuowen.json` /
  `kangxi.json` / `hanyu_words.json`，或用 `--zh-word-src`，也可跑 `parse_cedict.py` 生成全量 CC-CEDICT）
  → 重跑 `definition_fill.py` 即整词命中（**无需改代码**）；仍缺的再走 AI 精修（前端已标「AI 待補」）。
- 📋 **标注密度可调（用户观感决定）**：默认 `gloss`（只标有释义的词，≈ 論語 13.7% / 施公案 18.5% 字数），
  `window.VOCAB_WRAP='all'` 则是「词级全标」（論語 26% / 施公案 49%）——切换前建议先看观感。
- ⚠️ **自动分类未接通**：`scripts/classify_books.py` 默认读 `data/books.json`（本项目**不存在**），
  且需 `DEEPSEEK_API_KEY`；`pipeline.sh` 已有守卫（缺失即提示跳过）。
- 📋 **待入库批次**：`i.txt`（**2026-10-01 已移至项目根**）11 本英文书（37106/1260/1661/174/2701/2600/1400/768/4300/2554/28054）
  —— **用户指示暂不跑**。执行：`bash 文本/新书/add_books.sh --file i.txt`
  （入库后若词表要更新，按序跑：`python3 文本/新书/vocab_extract.py` → `build_vocab_final.py` →
  `definition_fill.py` → `bash deploy/build.sh`；词表链路**尚未接入 `pipeline.sh`**，见 systemPatterns）。
- ✅ **英文释义补全已完成**（2026-09-29，见下方第九批）：英文释义 93.1%、音标 84.7%；
  剩余 1,481 个缺释义词已被词典权威标注「确无」。缓存 `data/ecdict_api_cache.json`
  持久（`.gitignore` 已忽略），新增词条后重跑 `--api-budget=8000` 即幂等续补。

## 第九批（2026-09-29）— `fill_glosses.py` 联网预取性能/正确性修复
- **症状**：`--api-budget=3000` 跑 15 min 仍不足 200 条；`sample` 热点落在
  `builtins.sorted → _json.scan_once_unicode`。
- **根因 1（性能）：ECDICT 分片抖动**。step 2 用
  `sorted(w for w in word_pys if G.is_english_word(w) and G.en_word_needs_api(w))`
  ——生成器按**正文出现顺序**惰性求值，随机命中 a..z 各分片（26 片共 72 MiB，
  LRU 仅驻留 3 片），几乎每次判定都要重新 `json.load` 一个 ~3 MiB 分片；
  21,331 个英文词 ≈ 十几分钟（实测 >9 min 未跑完）。
  **修复**：`gloss_lib.en_words_needing_api(words)` — 新增 `ecdict_letter_of()`
  先算分片字母、排序聚簇后再逐词判定（屈折还原只改词尾，各候选原形首字母相同，
  故每片只解析一次）。**实测 >9 min → 2.6 s**。
- **根因 2（正确性）：断网污染缓存**。`_api_fetch` 全来源失败时仍返回 `{'en':'','ph':''}`，
  `api_prefetch.work()` 无条件 `cache[k] = rec`，而 `en_word_needs_api` 见 key 存在即判
  「无需补」→ 这 2075 个词被**永久钉死为无释义**（缓存 2176 条中 2075 条为空记录，
  正是英文释义只有 90.3% 的来源）。
  **修复**：`_api_fetch` 区分「有来源给出 HTTP 响应」（权威结果，含确无此词的空结果，
  可缓存）与「全部来源网络异常」（`_transient`，**不写缓存**）；`api_en`/`api_prefetch`
  据此跳过写入；新增 `api_drop_empty_cache()` 清理历史污染（本次清 2075 条，
  可补词 3388 → 5455）。
- **根因 3（真凶：整轮报废）**：`_api_request` 把词**原样拼进 URL**，而正文里的弯引号
  `’`（`a’most`/`don’t`/`o’er`）等非 ASCII 字符会让 `urlopen` 抛
  `UnicodeEncodeError: 'ascii' codec can't encode character '\u2019'`。这些词按字母序
  **恰好排在队首** → 前 8~20 个请求连续失败 → 来源被误判不可用 → 剩余 5000 个词瞬间
  全废（这正是「15 min 不足 200 条」的真凶）。
  **修复**：新增 `_api_word_param()` —— 弯引号归一（`’`→`'`，与 `_en_base_forms` 一致）
  + `urllib.parse.quote(..., safe='')` percent 编码。
- **配套加固**：
  - 熔断改为**可自愈冷却**（`_API_DEAD` 由 set 改为 name→到期时间戳，`API_DEAD_COOLDOWN=180s`
    后自动复活；连续失败阈值 3 → 8），避免一次抖动永久废掉来源；
  - 404/400 视为来源**权威答复「确无此词」**（可缓存空结果、不计失败、不触发冷却），
    修掉「连续几个生僻词就误杀来源」的隐患；
  - 429 单独处理：读 `Retry-After` → 全局冷却 + 自适应放大最小间隔（`_API_MIN`，上限 2s），
    但**不计入失败**；
  - `api_probe(tries=2)` 预检 + `set_api_interval()`/`--api-interval=秒` 可调间隔；
  - `api_prefetch` 在「来源全部冷却且已全失败」时**提前中止**，不再空转几千词，
    并打印各来源 `_API_LAST_ERR` 最近错误；返回 `(成功, 超预算, 失败)`；
  - `_api_cache_save()` 快照写盘（避免与工作线程竞态）；`work()` 内补 `_API_DIRTY = True`
    （原先增量存盘形同虚设）。
- **实测结果**（`--api-budget=8000`，freedict 单源，3.3 词/秒，~25 min，失败 10 条）：
  英文词 21,331 —— 英文释义 19,299 → **19,850（90.3% → 93.1%）**、
  音标 16,426 → **18,062（76.4% → 84.7%）**、中文释义 20,178（94.6%）；
  缓存 `data/ecdict_api_cache.json` 5,546 条（3,953 条有释义 + 1,593 条权威「确无」）。
  仍缺英文释义的 1,481 个词**全部**已被词典标注「确无」（古拼写 `a’most`、拟声 `aaarh`、
  专名 `abdalla`/`abramoff`、冷僻词 `acant` 等），非程序问题。
  回填 218,170 条 → 24 文件；`deploy/build.sh` 重建 dist（101 MiB / 154 文件）。
- **用法**：`python3 文本/新书/fill_glosses.py --api-budget=8000 [--api-interval=1]`；
  失败词不写缓存，重跑自动续补（幂等）。



## 上一批（2026-09-17，已提交推送）
- ✅ **英文书入库 + 英汉释义回填链路**：书库 94 → **106 本**
  （經部 9 / 史部 5 / **子部 77** / 集部 7 / 近現代文學 8），提交 `afe688d`
  「更新书库: 新增12本, 更新94本」→ 已推送 `origin/main`（`227c579..afe688d`）。
  - 入库书目（12 本古登堡英文书）：Frankenstein#84、Dracula#345、The Hound of the Baskervilles#2852、
    Walden#205、Peter Pan#16、The Jungle Book#236、Anne of Green Gables#45、The Wind in the Willows#289、
    A Little Prince#146、Grimms' Fairy Tales#2591、The Arabian Nights#128、Little Lord Fauntleroy#479。
  - **词典数据源（无版权打底 + 网络 API）**：
    - `parse_ecdict.py`（新增）：解析 **ECDICT**（skywind3000/ECDICT，MIT）`ecdict.csv`
      （77.1 万行 / 725,767 词条）→ 按首字母分片 `data/ecdict_en/ecdict_{a..z}.json`
      （26 片，最大 `s` 片 7.4 MiB，**无单文件超 25 MiB**）+ `data/common_words_en.json`（前 5000 常用词）。
    - `gloss_lib.ecdict_shard()` **惰性加载 + LRU≤3 片**；`fill_glosses.gloss_order()` 按首字母聚簇遍历
      → 全量回填 **12.8 s / 峰值 72 MiB**（对照：整库加载 390 MiB / 数分钟）。
    - 网络词典 `api_*`：主源 **freedictionaryapi.com**（Wiktionary 派生、免费无 Key、含 IPA），
      备源 dictionaryapi.dev（本机不可达 → **熔断**）；并发预取 + 缓存 `data/ecdict_api_cache.json` + 离线降级。
    - `fill_glosses.py` 英文分支：`zh_cn/zh_tw/en` + 音标写入 `pinyin`；英文词库另写 `wordbank_en.json`；
      CLI `--no-network` / `--api-budget=N`。
  - **英文注释生成**：`gutenberg_import.py --lang en` 用 ECDICT 常用词表挑难词（非停用词 + 长度≥3 +
    不在常用词表）写 annotations（word 存小写，释义待回填）。
  - **Gutendex 元数据中间层**：新增 `gutendex_client.py`（`search_books`/`get_book`/`normalize_gutendex_book`），
    `_resolve_quick` 元数据链改为 **本地 raw 头部 → Gutendex → 原古登堡 API（兜底）**；
    新增 CLI `--search "词"`、`--list-by-lang en --max N`（只查不入库）。
  - **新增 `--dry-run`**：只解析元数据打印预览表（编号/标题/作者/切分），**不下载不写文件**（含屏蔽失败日志）；
    未下载原文的书显示元数据 + 切分「待下载」（`_dry_meta_only`）。
  - **修复**：`split_single()` 未传 `lang='en'` 导致英文折行拼接丢空格（`asplendid` 之类粘词，注释数虚高）
    → Walden 13,753→7,989 等；`_resolve_quick` 里 `meta['title']` → `meta.get('title')`（既有 KeyError 崩溃）。
  - **前端** `网站/js/reader.js`：注释匹配对 ASCII 词**大小写不敏感**（词表小写、正文句首/全大写），
    且命中时输出**原文大小写**（此前会改写正文）。
  - 回填结果：英文注释 50,671 条 → 简/繁释义 **97.7%**、音标 75.9%；
    中文书注释 52,298 条（简繁 87.1%、英文 94.3%）。
- ✅ **两个一键脚本（新，已随本次提交）**：
  - `文本/新书/add_books.sh`：编号或 `--file 清单` → 入库 → `pipeline.sh`；`--lang auto|zh|en`（自动判语种）、
    `--dry-run`、`--no-pipeline`，其余参数透传。
  - `文本/新书/pipeline.sh`：①回填 ②分类 ③`deploy/build.sh` ④`git add -A`+commit+push；
    `--no-push` / `--no-commit` / `--no-classify` / `--offline` / `--classify-input <文件>`；
    自动载入项目根 `.env`。两者均自推项目根、可在任意目录调用。

## 更早批次（历史，均已入库）
- ✅ 第七批中文书 10 本（2026-09-08）：隋唐演義/論語/滬語開路/白圭志/孟子字義疏證/安樂集/鄧析子/醉醒石/唐鍾馗平鬼傳/春秋繁露；
  新增切分器 `split_lunyu`/`split_juan_sc`/`split_fanlu`。
- ✅ 第六批 10 本：飛跎全傳/佛說四十二章經/洛神賦/晁氏儒言/水滸後傳/幼學瓊林/治世餘聞/琵琶記/雪月梅傳/龍川詞；新增 `split_chu`/`split_juan_num`/`split_yxql`。
- ✅ 第五批 8 本：天豹圖/梁公九諫/長恨歌/李娃傳/玉樓春/引鳳蕭/今古奇觀/後西遊記；新增 `split_jian`/`split_juans`/`drop_until_heading`/`normalize_fe_punct`。
- ✅ 全站页脚兄弟站点链接「日程编辑与提醒器」；三语注释（简/繁/英）+ 三档阅读模式 + 轻量索引 `books.json` 规避 25 MiB；
  AI 阅读器（深度学习）板块已整体移除。

## 待确认/风险
- **`71d7901` 提交信息非规范**（2026-10-01）：`pipeline.sh` 自动提交把「古登堡书源改走 Gutendex」的代码提交成了
  模板信息「更新书库 (2026-10-01 21:25)」；如需规范信息要 `git rebase -i` + `push --force`。
- **Gutendex 降级延迟**：`gutendex_client._get_json` 重试 3 次 × 30s 超时 ≈ 2 min/本；书源改走 Gutendex 后，
  新书下载会先等这次查询再降级到 files/cache（已加**进程内缓存**，元数据与直链共用一次请求，不重复）。
- **维基文库正文提取局限**：`extract_text_from_html` 已剥离页头/注音/变体注，但 ruby 排版特殊的页面
  （如 `千字文`）仍可能残留换行碎片，入库前建议人工核对。
- **词表释义质量**（2026-09-29 晚，新增）：`vocab_final.json` 里有释义的 12,947 条**全部是逐字合成**
  （`君：…；子：…`，need_ai=true）——只说明成分字义、**不等于整词义**；另有 32,214 条 `待补`。
  要真词义需词级中文源（见「当前 ①」）。前端已用「AI 待補」标签 + 占位过滤，避免以假乱真。
- **同词双份释义**：词表行 `definition` 与单书 `annotations` 各自成源、可能不一致
  （现规则：语言槽 `zh_cn/zh_tw/en` 优先 → 词表 `definition` 兜底，见 `reader.js#annGlossText`）。
- **长任务 + 终端**：本机 VS Code 终端 shell integration 偶发不上报命令完成（显示「Command exited with code 1」
  但命令仍在后台跑）→ 长命令一律 `> /tmp/x.out 2>&1` 重定向后再读文件确认；**回填脚本运行中不要另发终端命令**
  （新命令会尝试关掉旧终端 → 旧进程被杀，可能只留下半截输出或旧版本产物）。
- **`dist/` 未纳入版本库**（`.gitignore` 含 `dist/`）：提交 `afe688d` 内含 252 文件 / 174 MiB 待提交体积，
  网页上线以 Cloudflare 直读 `网站/` 为准，`dist/` 仅本地/备用。
- **网络不稳**：本机到 `raw.githubusercontent.com`（ECDICT 63 MiB 需 git 克隆更稳）与 `gutendex.com`、
  `api.dictionaryapi.dev` 均很慢/不可达；脚本已做重试+熔断+缓存，但联网步骤可能耗时数十分钟。
- 书库若扩到数百本，`_site_data` 平铺单书 + `books.json` 的扩展性需重估（目录化 or R2）。
