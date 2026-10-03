# Active Context（当前状态与下一步）

## 当前（2026-10-03）：全站检索 + 查词多源回退/翻译 + 站外白名单/探活 + 分章修复 + 词典/释义面板

> 独立流水线目录 **`~/gutenberg_project/`**（与站点项目解耦）；进度全在 `progress/`，支持断点续跑。
> 站点侧已入库 **61635 本清洗产物**、精选 **600 本英文书**；`网站/_site_data` **792 文件**（790 单书）、
> `dist` **1.0 G / 1346 文件**（Pages 上限 20,000 文件，仍宽裕）。
> 分章修复后的数据已按批次重推完毕；**本轮检索/查词改动已提交推送，CF 构建绿**。

### ① 批量流水线（`~/gutenberg_project/`）
- `scripts/common.py`（路径/进度/日志/磁盘/编码/头部解析/语言判定）、`run_batch.py`（状态机：每次一批 500）。
- **Step1 去重**：扫 `文本/新书/raw` 115 个 txt → 115 书号（数字名 63 + 头部 `EBook#` 43 + 书名反查 9），0 未解析。
- **Step2 语言检测**：`~/downloads/cache/epub` **77941 本全分流** —— 英文 **61656** / 中文 **435** / 其他 **15850**（54 个语言目录）。
  - 策略：**头部 `Language:` 字段优先**（权威）+ langdetect（跳过头部、取 START 后 1000 字符）兜底；`--fix-other` 纠正误判（曾修回 8 本）。
- **Step3 中文维基文库去重**：435 本全查，**344 本维基命中**（移入 `~/gutenberg_zh_dup/`）；串行 + UA + 1.0s 限流 + 429 长退避 + 失败跳过（MAX_FAILS=5）。
- **Step4/5/6**：英文二次去重（`en_todo.txt`）→ 清洗 **61635 本**（`~/gutenberg_cleaned/{id}/`：text.txt / chapters.json / metadata.json，+ `out/books.sql`、`out/book_difficulty.sql`）→ CEFR 分级。
- 用法：`bash ~/gutenberg_project/run.sh`（每批 500、断点续跑）/ `--status` / `run_rest.sh`（P5→P6 长跑）。

### ② 精选 600 本英文书入库
- `scripts/select_books.py`：CEFR A1–B2、词数 8000–150000、**经典优先（小书号在前）+ 分层配额**（A1 100 / A2 180 / B1 200 / B2 120）。
- `scripts/cleaned_to_books.py --annotate`：`~/gutenberg_cleaned/{id}/` → `data/books/pg{id}.json`（含 chapters + 注释）+ 更新 `library-index.json`（子部）。
- 全链路 `run_ingest.sh`：转换 → `merge_to_site` → `fill_glosses --no-network` → `slim_annotations` → `deploy/build.sh`。

### ③ 开源词典引入（`文本/新书/data/`）
- `cedict_words.json` = **CC-CEDICT 19.8 万词条 / 18.4 万多字词**（mdbg 官方，11 MB）
- `kangxi.json` = **康熙字典 48710 字**（samsonhoi，MIT，11.4 MB）
- `shuowen.json` = **说文解字 9815 字**（shuowenjiezi，Apache-2.0，0.5 MB）
- `definition_fill.py` 自动发现 → **词表待补 32214 → 11623（−64%）**，need_ai 45161 → 16165。
- 解析脚本：`~/gutenberg_project/scripts/parse_cedict.py` / `parse_shuowen.py` / `parse_kangxi.py`。

### ④ 右侧释义面板（`reader.html` / `js/reader.js` / `css/style.css`，**仅桌面端**）
- `<aside id="dict-panel">` 固定右侧、默认隐藏；**点击 `<wise>` 或选中任意字词**触发。
- 面板分区：本站释义（annotations/vocab_final + 成分字）→ **康熙字典 / 说文解字**（离线，`_site_data/dict/{kangxi,shuowen}/0..127.json` 按字码点分片，91KB / 4KB 每片）→ **Wiktionary / 维基百科**摘要（前 200 字，**联网失败自动隐藏**）。
- 小屏（≤1099px）CSS 隐藏面板；移动端仍用原快速词卡。分片生成：`scripts/build_dict_shards.py`（`dict_meta.json` shards=128）。

### ⑤ 选词交互：左键查词 / 右键送 AI
- `global-ai.js`：**「选中即填 AI」改为右键（`contextmenu`）触发**（不 preventDefault，保留系统菜单）；豁免名单加 `#dict-panel`。
- `reader.js`：`selectionchange`（去抖 180ms）→ 左键选中正文任意字词（≤24 字、仅正文区）→ 打开右侧面板。

### ⑥ 分章修复（本轮重点）
- **戏剧按「场」（SCENE）拆章**（此前按幕，单章过长）：新增 `_SCENE_EN_RE/_SCENE_LA_RE`（`Scoena/Scena/Scæna/Scaena`），重写 `_drama_marks`（ACT 记录当前幕、SCENE 标题带幕号、**同行 `Actus Primus. Scoena Prima.` 合并为一场**）→ Othello **15 场**、Merry Wives 24 场。
- **根因**：Gutenberg First Folio 版莎剧用**拉丁** `Actus Primus. Scoena Prima.`（旧正则只认 `CHAPTER/BOOK/PART`）；另有英文序数词 `FIRST ACT`（Lady Windermere）、阴性 `Actus Tertia`（Shrew）、目录速览行误当章。
- **扩展规则修复 249 本 → 8 本（96.8%）**：新增**标题式行**模式（`Stave I:` / 大写标题 `STORY OF THE DOOR` / 标题式 `Blue Wednesday`），排除舞台指示（Enter/Exeunt）、角色对白行、目录碎片（<30 字）；同名章去重（保留最长）。
- **源缺标记的 5 本已处理**：Hamlet #1122/#2265（按场 6 章）、Dolly #1203（21 章）、Florentine #1308（6 章）、Troilus #1124 / Misalliance #943（**超长兜底**：>10 万字按段落近似切分）。
- **铁律工具**：`scripts/preview_split.py`（`--ids` / `--suspicious-only` / `--mode auto|chapter|drama|titles`），清单落 `progress/split_issues.txt`（现 8 本，7 本真单篇）。**入库前必跑预览确认分章。**

### ⑦ 分批推送机制（每批 40 本）
- `scripts/make_batches.py` → `progress/ingest_batches.tsv` + `.md`（15 批 × 40 本）。
- `scripts/batch_scope.py --save/--batch K/--all`：把 `library-index.json` / `books-data.json` / `books.json` **收窄到「累计到第 K 批」**（全量备份在 `progress/full/`，含 `original_titles.json`），保证每批书架渐增、不留 404。
- `push_batch.sh K [--dry-run]`：收窄聚合 → `git add` 本批 40 本 + 聚合 → commit → push。
- `data/books/` 已 **gitignore**（源数据 567M 不入库；CF 构建只需 `网站/_site_data`）。

### ⑧ 英文书按「四部分类法」重分（2026-10-02，本轮）
- **问题**：英文书入库时 `cleaned_to_books.py` 一律写死 `CAT='子部'/SUBCAT='小說家（西洋）'`，
  于是 79 条（52 种）已推送英文书全挤在「子部 · 小說家（西洋）」，与站点「五部分類」卖点不符。
- **方案**：新增 `scripts/reclassify_en_books.py`（`--dry-run` / `--also <副本>` / `--no-data-books`），
  按**传统四部分类法 + 站点既有子类命名**，以 `EN_CLASS`（书名 → 部类/子类）重排：
  - 子部·**小說家（志怪·西洋）** 3：Frankenstein、Dracula、The Arabian Nights
  - 子部·**小說家（公案·西洋）** 1：The Hound of the Baskervilles
  - 子部·**小說家（童話·西洋）** 9：Peter Pan、Jungle Book、Wind in the Willows、A Little Princess、
    Grimms' Fairy Tales、Little Lord Fauntleroy、Looking-Glass、Pinocchio、Bobbsey Twins
  - 子部·**小說家（寓言·西洋）** 1：Fables（Stevenson）
  - 子部·**小說家（西洋）** 9：Anne of Green Gables、A Girl of the Limberlost、The Cash Boy、
    Bab: A Sub-Deb、Cast Upon the Breakers、The Errand Boy、Joe the Hotel Boy、Driven from Home、Dolly Dialogues
  - 子部·**譜錄（食譜）** 1：Recipes Tried and True
  - 集部·**戲曲（西洋）** 27 种 / 55 条：莎剧各版本 + Wilde/Shaw/Congreve/Synge/Goldsmith + Henley&Stevenson
  - 集部·**別集（西洋）** 1：Walden（散文随笔，个人文集）
  - 經部 / 史部 / 叢部：本批英文书无此类（叢部＝跨部之叢書，故索引里**不出现**空分类，与 `merge_to_site` 一致）
- **结果**：`library-index.json` 子部 143→88（英文 79→24）、集部 7→62（英文 0→55），总 172 不变；
  `books-data.json` `zi` 146→91、`ji` 16→71；`data/books/pg*.json` 79 本正本同步。
  同部内排序保持「中文在前、西洋在后」。`网站/_site_data/*.json` 与 `books.json` 不含部类，无需改动。
- **耐久性**：`progress/full/{library-index,books-data}.json` 已用 `--also` 同步（否则下次
  `push_batch.sh K` 走 `batch_scope.py` 会从 FULL 重建、把重分类**回退**）。
- **待办**：`~/gutenberg_project/scripts/cleaned_to_books.py` 仍是写死 子部·小說家（西洋）
  （未推的 500+ 本英文书入库后仍需跑本脚本，或改造该脚本按体裁分类）。

### ⑨ 维基文库中文电子书索引（2026-10-02，新交付）
- **交付物**（`文本/新书/`）：
  - `wikisource_index.md` —— 可读索引（按四部：經/史/子/集/叢，附推荐清单与 `fetch` 用法）
  - `wikisource_index.json` —— 结构化（title/page/bu/sub/region/length/authors/versions/in_library/recommended）
  - `wikisource_index.tsv` —— 制表符清单（供批量脚本）
  - `build_wikisource_index.py` —— 生成脚本；`wikisource_index_guide.md` —— 采集/入库说明
- **规模**：**1642 种**（中土 **1083** · 域外漢籍 **559**），已入库 **13**；推荐 ⭐ 132（未入库 122）。
  部级：經 59 / 史 181 / 子 207 / 集 548 / 叢 88（域外另计）。
- **数据来源**：zh.wikisource 分类树（非臆测）——`Category:十三經`(+7 子类)、`Category:史部`(+13)、
  `Category:子部`(+12)、`Category:集部`(+8)、`Category:四庫全書`、`Category:詩集`、`Category:史書`；
  页面长度/作者由 `prop=info` / `prop=links&plnamespace=102` 批量补全（25 题/批 ×2 请求）。
- **要点/坑**：
  - 网络极不稳：一律 `curl --max-time 18~25 + 低并发 + 多尝试`（`requests` 易 ReadTimeout）；
    **`prop=info|links` 合并成一个请求会显著变慢 → 必须分开**。
  - 子页折叠（`史記/卷018`→`史記`）、版本后缀归一（` (四部叢刊本)`）；同名异本合并为一条（`versions` 记录）。
  - 作者链接会被页头 navbox 污染（如《二十四史》模板 → 新唐書 26 位“作者”）→ **>5 位即弃用**。
  - 顶层分类成员（史/子/集的 68/96/278 页）无细分，归入「總類」，避免误标为 雜史/雜家。
- **用途**：站长按需 `wikisource_toolkit.py fetch "<页面标题>"` 或
  `bash add_books.sh --source wikisource --title "…" --author … --category … --subcategory … --label …` 入库。

### ⑩ 维基文库「推荐优先」批量抓取/入库 + 智能分章 + 释义回填 + 书库「待入库」预览（2026-10-02）
- **新增脚本**（`文本/新书/`）：
  - `wikisource_index_backfill.py` —— 补齐索引里缺失的页面元数据（断点续跑，缓存 `.ws_meta_cache/`，gitignore）。
    **实测：301 条待补 → 补长度 249 / 补作者 44，剩 52 条（多为确为空页/重定向）**；
    覆盖率 长度 1341→**1590**、作者 893→**937**。
  - `wikisource_batch.py` —— 子命令 `list / fetch / commands / ingest / merge`；
    按索引的 `recommended` 与 `in_library` 选候选（**122 本**），抓取/入库均断点续跑
    （`_ws_fetch/*.tsv`）；自动选用项目 `.venv` 解释器（toolkit 需 requests）；
    `--page` 支持单本增量，`--strict` 走严格合规（默认 `--force` 跳过许可未知页）。
  - `wikisource_recommended.sh` —— 一条龙：抓取 → 入库 → 释义回填 → 重建。
  - `build_wikisource_index.py` 增 `--from-json`（按现有 json 重建目录，勿再动 /tmp 快照）、
    **元数据缺口回填**（重采集不再冲掉补抓结果）、**`in_library` 自动刷新**（新入库的书自动移出待入库），
    并生成站点「待入库」数据 `网站/assets/data/wikisource-pending.json`。
- **智能分章**（`wikisource_import.py --split auto`）：维基文库多为「一页放全文」，
  导入时按 卷/回/篇/章/品/則/節/折 标题行再切（`第一卷`/`第一回 標題`/`卷一`/`卷十二`/`〔篇名〕`/`序`），
  按「命中最多」的模式投票 + ≥2 切分点 + 每段 ≥40 字；标签自动写入 `section_label`。
  另修 `wikisource_toolkit._sort_key`：`序/凡例/楔子` 恒在前、**中文数字按数值排**
  （`卷第一 < 卷第二 < 卷第十`）；`get_subpages` 新增 `existing_titles()` **过滤红链**
  （父页目录里未创建的卷页，原先只会抓到 missingtitle 空壳）。
- **释义回填**：`wikisource_import.py` 新增 `--annotate`（默认开）——复用
  `gutenberg_import.annotate_book` 生成 `annotations`；批量入库后统一跑 `fill_glosses.py`。
  顺带修 `gutenberg_import.merge_pending()` 历史 bug（`wordbank_pending.json` 实为 **list 字表**，
  旧代码按 dict 处理会 `list.setdefault` 崩）。实测一次回填 **1378 文件 / 213 万条**。
- **书库页「待入库」预览**：`library.html` + `js/library.js` + `css/library.css` 增加
  「本站藏书 / 待入库·维基文库 📥」范围切换 + 「只看推荐 ⭐」；卡片沿用五部配色、
  点击跳维基文库原页（新标签）、URL `?mode=pending`；**每卡附「📋 复制入库命令」**
  （一键复制 `wikisource_batch.py fetch/ingest --page "…"` 到剪贴板，navigator.clipboard
  + execCommand 回退）；数据 1069 条 ≈ 270 KB。测试 `tests/library/library-pending-test.js`
  （jsdom，**17/17 通过**）。
- **候选排序**：`--order size`（默认）**小书在前**——先出成果、不被《四庫全書總目提要》
  这类大部头卡住（实测小书约 10 秒/本）；`--order default` 走四部顺序。
- **已实跑验证（批量，2026-10-03 完成）**：推荐清单 **107 本全部抓完**（新抓 75；空壳重试后仅剩 4 本确无正文），
  分三轮 `ingest --offline` 入库（15 + 50 + 12 + 36 + 5）。**最终：`books-data.json` 195→295 本**
  （古登堡 177 · 维基文库 **118**；中文 216 / 英文 79；篇目 14,773），
  `library-index` **290 条**（經 34 / 史 33 / 子 137 / 集 74 / 近現代文學 8 / 叢 4），
  `data/books` 正本 823、`_site_data` 顶层 792。待入库预览：候选 **952**（推荐 ⭐ 仅剩 4）。
- **入库效果**：智能分章 + 子页切分产出多章书（資治通鑑 267 / 通典 / 夢粱錄 21 / 洛陽伽藍記 8 /
  沖虛至德真經 9 / 孝經註疏 10 …），每本生成注释（200–1300 条）→ `fill_glosses` 回填 → `merge_to_site`。
  **史記（120 卷）/漢書（102 卷）/古文觀止 现走维基文库版**（原先同名时由 `catalog.json` 的「目录主书」占位）。
- **工具修复（本轮）**：
  - `split_by_heading` 适配新版 MediaWiki —— h2 被包进 `<div class="mw-heading">`，
    正文是 wrapper 的兄弟节点（旧代码取 h2 兄弟 → 唐詩三百首等「无子页」书正文全 0）；顺手摘掉标题里的 `[编辑]`。
  - 同一本书内**并发抓页**（`PAGE_WORKERS`，`WS_WORKERS` 可调，默认 4）—— 大书（資治通鑑 267 卷）
    从串行几十分钟降到几分钟；`api_get` 加 3 次递增退避重试。
  - 抓取「成功」以**抓到正文量**判定（toolkit 全页失败仍返回 0 会落空壳 JSON），新增 `empty` 状态与 `--min-chars`。
- **已知缺口**：维基文库这些页**未挂版权模板**（许可判定「未识别」被合规闸门拦下）：
  `四庫全書簡明目錄`、`四庫全書總目提要`、`爾雅`、`尉繚子`。如要入，需人工确认 PD 后用
  `--strict` 之外的路径处理（当前 `wikisource_import` 对全不安全章节会中止）。

### ⑪ 查词面板在线词典：改同域代理（2026-10-03）
- **症状**：右侧释义面板「在线词典」空白，控制台「网络连接已中断」。
- **根因**：`网站/js/reader.js` 的 `fetchOnlineSummary()` **从浏览器直连**
  `https://zh.wikipedia.org|zh.wiktionary.org/api/rest_v1/page/summary/…` → 跨域被拦 / 网络不可达，
  且 `catch` 里是「失败静默不显示」→ 一片空白。
- **改法**：
  - **新增同域代理** `网站/functions/api/dict.js`（Cloudflare Pages Function）：
    `GET /api/dict?source=wikipedia|wiktionary&lang=zh&q=<字>` →
    转发 `https://{lang}.{host}/w/api.php?action=query&prop=extracts&exintro&explaintext&exchars=400&redirects=1&format=json&**origin=***`；
    8s `AbortController` 超时 + `try/catch`，**任何情况都返回 JSON**（上游失败 `502 {"error":"fetch failed"}`、
    页面不存在 `200 {"error":"not found"}`），响应头固定 `Access-Control-Allow-Origin: *`，带 UA。
  - **前端**：`fetchOnlineSummary(source,label,word)` 改打 `/api/dict`（不再出现任何第三方域名）；
    **只对单个汉字**发在线请求——多字（含选中的文言短句）直接跳过在线，只走离线；
    在线失败时面板底部提示「在线释义暂不可用」（`.dp-warn`），离线康熙/说文照常显示。
  - **配套**：`网站/_headers` 加 `/api/*` → `Access-Control-Allow-Origin: *`；
    `deploy/build.sh` 增加 `网站/functions` → `dist/functions` 复制。
- **本地验证（模拟同域）**：
  - `tests/library/serve-local.js`（静态站 + `/api/*` 走**真实** Function；也可用 `npx wrangler pages dev 网站`）；
    实测：缺 q → 400、坏 source → 400、上游不通 → **502 + JSON + CORS 头**（不空响应）。
  - `tests/library/dict-proxy-test.js`（**18 项**）：参数校验 / `origin=*` / ACAO / 上游失败 / 网络异常 / OPTIONS。
  - `tests/library/dict-panel-e2e-test.js`（jsdom + 真实 Function，**13 项**）：单字只请求同域 `/api/dict`、
    页面**从不**直连 zh.wikipedia/wiktionary、成功出摘要、失败出「在线释义暂不可用」且康熙仍在、
    多字**不发**在线请求。
- **注意**：本机到 wikipedia.org 不通（函数返回 `fetch failed`），但**部署到 Cloudflare 后由边缘节点发起**，通常可取到摘要。

### ⑫ 超大字书自动分片：修 Pages「25 MiB 单文件」部署失败（2026-10-03）
- **症状**：Cloudflare Pages 构建失败 ——
  `Error: Pages only supports files up to 25 MiB in size`，`_site_data/永樂大典.json is 51.4 MiB`。
  （同批还有 冊府元龜 22 / 宋史 17 / 太平御覽 15 / 全唐詩 15 / 讀史方輿紀要 11 / 資治通鑑 9.4 MiB，
  虽未超限但已严重拖慢阅读页加载。）
- **根因**：维基文库这批大部头**正文本身就是巨量**（永樂大典 804 章 / 1580 万字），
  `merge_to_site` 仍按「一本书一个 JSON」写，直接撞上 Pages 硬上限。体积主要在**正文**（46 MiB），
  注释只占 2.3 MiB。
- **改法**（`文本/新书/gutenberg_import.py`）：
  - 新增 `write_site_book()`：单书 JSON > **8 MiB** 即改「**轻主文件 + 正文分片**」——
    主文件 = 目录（title/category_label/number，**无 paragraphs**）+ annotations + `sharded:true`/`part_size:P`；
    `_site_data/{书名}/{k}.json` = 该片 45 篇（含 paragraphs，紧凑 JSON）。
    分片顺序与前端 `orderedSections()` **同序**（`_js_ordered_sections`），故 index 直接映射分片。
  - 新增 `assert_no_oversize()`：merge 结束前扫全目录，**任何文件 > 25 MiB 直接 SystemExit**
    （宁可在本地炸，也不要推到线上才发现）。
  - `网站/js/reader.js`：若 `book.part_size` 且当前篇无 paragraphs → `await` 取 `_site_data/{书名}/{k}.json`
    再渲染（失败仅 `console.warn`，页面仍可用）。`book.js` 只用篇目标题 → 无需改。
  - `deploy/build.sh`：构建末尾加「单文件 ≤25 MiB」硬校验（同样 exit 1）。
- **结果**：8 本自动分片（永樂大典 18 片 / 主文件 2.14 MiB；冊府元龜 8；宋史 6；全唐詩 6；
  太平御覽 5；讀史方輿紀要 4；資治通鑑 4；新唐書 3）。
  **网站/ 最大文件 7.43 MiB，超 25 MiB 文件 0 个**；文件总数 1000→1154（远低于 2 万上限）；
  `dist/` 构建通过（981 M / 1148 文件）。
- **测试**：`tests/library/shard-reader-test.js`（**9/9**）：主文件无 paragraphs、按需请求 `_site_data/永樂大典/2.json`、
  正文渲染 2.4 万字、跨分片（第 190 篇）不串片、书页仍显示「共 804 篇」。
- **锚点定位（分片书）已支持**（同轮补上）：
  - 分片主文件带 **`anchors`**（每篇「首个有内容段落」前 60 字，跳过零宽/空白占位段）→
    `?anchor=<句>` 在分片书里也能定位；`reader.js` 先搜正文（单文件书），搜不到再查 `anchors`。
  - 更根本的一手：`文本/build_sentences.py` 给每条句子加 **`sec`（篇目序号）**，
    首页「开始阅读 →」改为 `?index=<sec>&anchor=<句>` → **分片书 100% 精准直达**（anchor 只用于高亮）。
  - 顺带修 `build_sentences.py` 两处：`DATA` 旧路径 `文本/_site_data` → `网站/_site_data`；
    新增 `ordered_sections()`（**与前端 `orderedSections` 同序**）——否则多分类书（三國志：魏書/蜀書/吳書）
    的 `sec` 会错位（实测错 256 条 → 修后 **0/6141**）。分片书按 parts 拼回读取。
  - 句子池随之刷新：shi 2006 / zi 1795 / ji 2340 条（旧池是 2026-08-31 用旧数据生成的）。
  - `reader.js` anchor 高亮处加 `scrollIntoView` 存在性判断（老环境/测试环境安全）。
- **注意**：分片书若只给 `?anchor=`（不带 `index`），仅当该句落在**篇首 60 字内**才命中；带 `sec`/`index` 则必达。

### ⑬ 推送后自动触发 Cloudflare 构建（2026-10-03）
- **背景**：push 后想「顺手触发一次 CF 构建」。先查清现状（用 wrangler 的 OAuth 凭据调 CF API）：
  ```
  3c57e353 main deploy ✅ 02:18:42   ← 锚点定位那次 push 已自动构建并部署成功
  c01a696b main deploy ✅ 01:50:54   ← 分片修复已上线
  e9896ae2 main build  ❌ 01:24:03   ← 用户贴的那次 25 MiB 失败
  ```
  即：**仓库已连 GitHub，push 本身就会自动构建**（这次 push 曾因 GitHub 443 超时失败，后台重试第 3 次成功后自动构建）。
- **新增 `deploy/trigger_build.sh`**：显式触发 / 查看 Pages 部署。凭据按优先级自动选：
  1) `.env` 的 **`CF_DEPLOY_HOOK`**（Pages 控制台部署钩子 URL，推荐、无需 token）
  2) `.env` 的 `CF_API_TOKEN` + `CF_ACCOUNT_ID` + `CF_PAGES_PROJECT`
  3) 回退：本机 `~/.wrangler/config/default.toml` 的 OAuth（自动发现账号/项目）
  `--list` / `--dry-run`；**无凭据时退出 0 只给提示**，绝不阻断流水线。
  （本项目实际值：账号 `55b7fa0b…`、项目 `myfami`、分支 `main`。）
- **接入 `文本/新书/pipeline.sh`**：第 ⑤ 步 —— `git push` **成功后**自动调用（`--no-trigger` 关闭；
  push 失败会 `err` 提示而不继续）。
- **顺带修一个真 bug**：新脚本里 `$a（`、`$code）` 这类「`$变量` 紧跟全角字符」在 **bash 3.2**
  会被并成变量名 → `unbound variable` 直接崩。已全改 `${a}`/`${code}`/`${SRC}`；
  并写了个扫描脚本确认 `deploy/*.sh`、`文本/新书/*.sh` 里同类写法 **0 处**。
- **测试**：`tests/library/deploy-trigger-test.js`（**5/5**，不联网）：部署钩子分支只打印不发请求、
  未知参数退出 2、无凭据退出 0 且给三种办法提示、`--list` 不崩。

### ⑭ 全站检索页 + 离线查词 + CC-CEDICT 分片（2026-10-03，本轮）
- **需求**：标题 + 全文关键词 → 定位到「书 → 篇」；另加离线词典查询 + 第三方词典外链。
  **用户拍板**：检索深度走 **A 方案（目录层 + 快照层）**；第三方用**现有友链四家 + 维基词典**；
  离线词典＝**康熙 + 说文 + 本站词表，CC-CEDICT 也分片部署**。
- **索引**（`文本/build_search_index.py` → `网站/_site_data/search/`，共 12 MB）：
  - **目录层 `titles.json`（0.9 MB）**：790 本书（书名/作者/分类/篇数）+ **24,753 条篇目标题** → 一次加载，书名/篇名秒回。
  - **快照层 `snap/0..63.json`（10.9 MB，64 片）**：每篇「正文前 180 字 + 尾 60 字」，按 `gIdx % 64` 分片
    → 前端 64 片并行 fetch、边到边扫（页面显示「已扫描 N/64 片」）。
  - `meta.json`：`{books:790, sections:24753, snap_shards:64, snap_head:180, snap_tail:60}`；
    参数可用 `--snap-head/--snap-tail/--shards` 调整（`--dry-run` 先看体积）。
  - 篇目顺序**复用 `build_sentences.ordered_sections`**（与 `common.js orderedSections()` 同序）
    → 检索结果里的 `?index=` 能直接跳阅读页（测试比对样本 論語 / 三國志 / 永樂大典 全通过）。
  - 口径权衡：全量倒排（bigram）会是几百 MB，故选「目录 + 前后文快照」；代价＝**篇中段关键词可能漏检**，页面上有明确说明。
- **前端**：`search.html` + `js/search.js` + `js/dict-lookup.js` + `css/search.css`
  - 四块结果：离线查词 / 书目·篇目 / 正文命中（`<mark>` 高亮片段）/ 第三方词典外链（只给链接，不在本站展示第三方内容）。
  - `js/dict-lookup.js`：可复用离线查词 —— **本站词表 → 康熙 → 说文 → CC-CEDICT（按需取分片）**；单字另附「成分字」。
  - `js/home-search.js`：首页搜索框 **回车 → `/search.html?q=…`**；下拉末尾加「🔍 全站检索…」入口（桌面 + 移动端都绑 Enter）。
- **CC-CEDICT 分片部署**：`文本/新书/build_dict_shards.py`（**收进仓库**，原脚本在 `~/gutenberg_project/scripts/`）
  → `_site_data/dict/cedict/0..127.json`（**198,266 条 / 10.9 MB**）；`dict_meta.json` 更新为 3 部词典（kangxi / shuowen / cedict）。
- **第三方词典链接**：漢典 `zdic.net/hans/<q>`、ctext `ctext.org/search.pl?if=gb&searchu=<q>`（**curl 实测 200**）、
  維基詞典 `zh.wiktionary.org/wiki/<q>`；**國學大師 / 中華典藏**被其反爬挡住、本机不可达
  → 国学大师用其站内检索写法、中华典藏退回首页（代码里已注释标明 **待在有网环境核对**，改一行即可）。
- **缓存**：`网站/_headers` 给 `/_site_data/search/*`、`/_site_data/dict/*` 加 `max-age=86400`（查一次当天不再重下）。
- **部署**：`deploy/build.sh` 页面清单**补上 `search.html`**（漏了就是 404，测试里已锁死）；构建后 dist **1,346 文件 / 1.0 G**。
- **测试**：`tests/library/search-test.js`（**43/43**，jsdom）—— 索引一致性（快照覆盖率 / 无重复 / 篇序比对）
  + 端到端（书名 / 篇名 / 正文命中都回查正确、离线查词**只取 1 片**、5 条外链均 `rel=noopener`、
  无命中 / 无查询不报错、首页回车触发跳转、build.sh 含 search.html）。
- ⚠️ **发现（非本轮引入）**：`_site_data` 的 **790 本里有 495 本（古登堡英文批量书）不在 `books-data.json`**，
  即书库页不列它们 —— **检索页目前是它们的主要入口**；README 的「书库现状」表已按实测数字更新（上架 295 本 / 14,773 篇）。

### ⑮ 站外词典白名单 + 每周探活 + 「容错外链」（2026-10-03，本轮）
- **背景**：站外词典不是都能用 —— 國學大師（未备案被阿里云拦截）、中華典藏（域名失效）、
  中文維基詞典（境内直连白屏）。原来 `search.js` 里硬编码 5 条外链，坏源照样渲染、点了白屏。
- **新增 `网站/js/dict-links.js`（白名单 + 状态判定，检索页 / 阅读页 / 设置页共用）**：
  - 基线写在源码：`zdic` / `ctext` **默认展示**（首选，新窗口打开）；`wiktionary-zh`（`needsFallback`）、
    `guoxuedashi`、`zhonghuadiancang`（`probe`）**默认 hidden**。
  - 状态三层：`enabled` 展示 ｜ `fallback` 仅「容错外链」开启时展示 ｜ `hidden` 不展示。
  - **硬规则**：hidden 的源不渲染按钮、`urlOf()` 返回 null（据此绝不建链）、**不预取、不自动请求**；
    外链一律 `target="_blank" rel="noopener"`。全站零 `preconnect/prefetch/dns-prefetch`（测试锁死）。
  - 探活状态读 `_site_data/dict/dict_links.json`（缺失/损坏 → 回退基线，不报错）。
- **新增 `deploy/dict_links_probe.js`（每周探活）**：
  - 只探活 2 个源：**國學大師 = HEAD 状态码 + 页面关键字**（挡阿里云拦截页 / JS 跳转壳页）、
    **中華典藏 = DNS 解析 + HEAD 200**。漢典/ctext 无需探活；維基詞典是「被墙」不是「故障」，不探活。
  - 状态机：连续 **2 次成功 → state=enabled（自动展示）**；连续 **2 次失败 → hidden**；
    未达阈值保持原状态（观察中，不折腾用户）。写回 `dict_links.json`。
  - CLI：`--dry-run` / `--only <id>` / `--timeout <秒>` / `--quiet` / `--commit` / `--push`（隐含 commit）。
    核心只用全局 `fetch` + Promise，可被 Worker `scheduled` 直接调用（把读写换成 KV）。
  - ⚠️ **必须在境内网络跑**（本机 cron）：阿里云拦截与被墙只在境内出现，境外 CI 会把坏源误判为可用。
  - 实跑（本机，2026-10-03）：國學大師 HTTP 200 但**无站点关键字** → 判失败；
    中華典藏 `fetch failed`（DNS）→ 判失败 → 两家 `streak_fail=2 → hidden` ✓。
- **前端接入**：`search.js`（「更多词典」用 `DictLinks.render`，hidden 连元素都不生成）+
  `reader.js`（面板底部新增「更多词典」，并写明「已隐藏 N 个不可用源」）。
  **同时从自动摘要里摘掉中文维基词典**：阅读页在线词典只走维基百科（同域 `/api/dict` 代理），
  维基词典「永不参与任何自动摘要请求」，只在开启容错外链后手动点开。
- **设置页**：`ai-settings.html#dict-links` 新增「词典外链」卡片 —— 「容错外链」开关
  （key `guoxue_dict_fallback_links`）+ 逐源状态表（展示 / 容错展示 / 隐藏 + 为什么隐藏）。
  逻辑抽到 `js/dict-settings.js`（不写在页面内联脚本里，便于 jsdom 测）。
- **友链页**：`links.html` 给中華典藏 / 國學大師 各加一行「已默认隐藏，探活恢复」的说明。
- **踩坑**：`stateOf()` 对 `needsFallback` 源一开始写成「基线 hidden 也要开关点头」→ 开关永远无效
  （`on===false` 短路）；已改为「探活没说 hidden 时由开关决定」。`dict_links.json` 里
  `wiktionary-zh.state` 因此置 `null`（它不参与探活，不该被探活判死）。
- **测试**：`tests/library/dict-links-test.js`（**92/92**）—— 基线 5 源 / 探活覆盖 / 容错开关 /
  hidden 不渲染不预取不发请求（含全站 prefetch 静态扫描）/ 阅读页无 `source=wiktionary` /
  设置页开关写 localStorage / 探活脚本 5 种网络情形 + 状态机 2 次翻转 + parseArgs。
  另更新 `search-test.js`（外链期望 5 → 2，44/44）。全量回归：17/18/13/12/44/92/5 + vocab 66/21/26 全绿。

### ⑯ 查词面板：多源回退 + 翻译 Tab + 新窗口跳转（2026-10-03，本轮）
- **需求**：面板按「输入类型 + 语言」多源回退；所有在线请求必须经 Worker 代理（前端绝不直连）；
  6+ 字符自动切翻译 Tab；外链点开新窗口；缓存 7 天；任何失败都不空白。
- **数据：新增 Unihan 本地库**（`文本/新书/build_unihan_slim.py`）——从 UCD 官方 `Unihan.zip`
  （8.3 MB，unicode.org 本机可达）抽 `kMandarin`（拼音）/ `kRSUnicode`（部首，214 部首表内置）/
  `kTotalStrokes`（笔画）→ `_site_data/dict/unihan/0..127.json`（**102,999 字 / 3 MB / 24 KB 每片**），
  并入 `dict_meta.json`。`--src/--zip/--dry-run`，缓存 zip 到 `/tmp`。
- **Worker（Pages Functions）**：
  - `/api/dict` 重写为多源：`moedict`（萌典，`Api-User-Agent`）/ `wiktionary` / `wikipedia` /
    `freedict`（api.dictionaryapi.dev，**404 归一成 not found**）/ `unihan`（读 `env.ASSETS` 静态分片，
    零网络；本地开发回退自取 URL）。统一 `{source, query, result}`（wiki 源另留顶层 `extract` 兼容旧调用方），
    **上游超时 2.5s**（前端 3s），响应 `cache-control: max-age=86400` + CORS。
  - 新增 `/api/dict-links?lang&q`：各语言新窗口链接模板（zh 漢典/萌典/教育部重編國語辭典/中文 Wiktionary、
    en MW/Cambridge/Collins/Oxford、fr Larousse/CNRTL、de Duden/DWDS、es RAE、it Treccani、ru 维基词典；
    未知语种 → `{lang}.wiktionary` + 英文兜底），**只返回 URL，不抓页面**。
  - 新增 `/api/translate?q&from&to`：MyMemory 代理（繁中→zh-TW、简中→zh-CN 归一；q 截 500 字；配额 403 → 502 JSON）。
- **前端 `js/dict-api.js`（新，纯逻辑、可 Node 单测）**：
  - `classify()` 分五类（zh-char / zh-word / en-word / x-word / long）。**踩坑**：最初把「6+ 字符」当成全局规则，
    误伤 `well-known`、`привет` 这类长单词 → 改为只对**汉字串**按 1/2–5/6+ 分类；拉丁词再按书籍语言
    决定走 en 还是 `{lang}` 链。
  - `chainOf()` 回退链 + `lookup()`：**白名单闸门**（`DictLinks.hostHidden`）在请求前判，被墙源直接 skip
    （不建链、不请求）；每级 3s 超时 → 立即降级；结果归一（音标/拼音/词性/释义/wiki 摘要/部首笔画）；
    `skipOffline` 供面板把离线单独渲染。
  - `cachedGet()`：localStorage 缓存，key = `${source}:${lang}:${query}`，**TTL 7 天**；只认
    `result/translatedText/links` 才算成功（防空 JSON 被当成功）。
  - `links()`：Worker 模板 + `filterLinks()` 白名单过滤（被墙源剔除）；接口挂掉 → 回退本地白名单。
  - `splitWords()`：注入的分词器（词表最长匹配）优先，否则汉字 2 字滑窗 + 西文按词；最多 8 段。
  - `simplify()`：萌典/维基返回繁体 → opencc-js（与 reader.js 同款）转简，未加载则原样。
- **前端面板（`reader.js` + `style.css`）**：
  - Tab「释义 / 翻译」；释义 Tab = 在线回退链（来源标注 `dp-src` + 音标 + 词性 + 释义列表 +「尝试过的源」）
    + **离线字典区永远显示**（本站词表 / 康熙 / 说文 / CC-CEDICT + 成分字）。
  - 6+ 字符：自动切「翻译」Tab（自动翻译）+ 释义 Tab 逐词并列查（`.dp-wordbox`）。
  - 「更多词典」折叠区（`.dp-more-head`）：`window.open` 新窗口，只跳转不抓页面；接口不可用时标注回退。
  - 选词处理器上限从 **24 字放宽到 300 字**（否则整句永远进不了面板）。
  - 失败语义：全挂 → 「未找到释义」+「在线释义暂不可用」+「（N 个源因被墙/被拦已跳过）」，**绝不空白**。
- **测试**：新增 `tests/library/dict-fallback-test.js`（**98/98**，纯 Node 无 jsdom）：分类 / 回退链 /
  逐级降级 / 门禁不发请求 / 超时映射 / 缓存 TTL / 英文·多语种链 / 逐词切分 / 外链过滤 / 翻译 /
  三个 Function（moedict·freedict·unihan·dict-links·translate，含 404 归一、env.ASSETS、超时 502、参数校验）。
  `dict-panel-e2e-test.js` **重写为 38 项**（真实 Function + 上游打桩：萌典命中、门禁跳过、全挂降级、
  容错外链放入 wiktionary、多字链、6+ 字符翻译 Tab + 逐词查 + `/api/translate`、缓存、更多词典 3/4 条）。
  全量回归：dict-proxy 21 ｜ dict-links 92 ｜ panel-e2e 38 ｜ dict-fallback 98 ｜ search 44 ｜
  library-pending 17 ｜ shard-reader 12 ｜ deploy-trigger 5 ｜ vocab 66/21/26 —— **全绿**。
- **踩坑（真 bug）**：① 早前的编辑误删 `cachedGet` → 面板报 `cachedGet is not defined`（测试抓住）；
  ② `DictLinks.hiddenHosts()` 原来是「基线 hidden 的静态列表」，没跟随「容错外链」开关 → 闸门永远关着
  （容错开了也不放 wiktionary）；已改为按 `stateOf()` 动态算，并新增 `hostHidden(host)`；
  ③ 萌典 `meanings` 是对象数组，`normalize` 直接 `map(simplify)` 会得到 `[object Object]` → 兼容 `m.def` 与字符串。
- ⚠️ **已知限制**：书籍 JSON 里没有 `lang` 字段 → `reader.js` 的 `bookLang()` 只能按正文推断（汉字 vs 拉丁），
  所以**法/德/西等书里的拉丁词会按英文链查**；要精确支持，请在书数据里补 `lang`（前端已优先读 `book.lang`）。

### ⑰ 线上部署排障：Functions 路由 + 翻译源（2026-10-03，接 ⑯）
- 🐛 **重要发现**：线上 `/api/*` **从未生效过** —— 请求全被 SPA 兜底成首页 HTML（200 text/html），
  前端只能降级到离线词典。定位办法：
  - 线上 `/启动站点.command` 可取（该文件只在 `网站/`）→ 部署根 = `网站/` ✓
  - 但 **CF Pages 只从「项目根目录」（= 仓库根）下的 `functions/` 读 Functions**，不会去构建输出目录里找；
    实现放在 `网站/functions/api/*.js` → 三个接口都没注册。
  - **修复**：新增仓库根 `functions/api/{dict,dict-links,translate}.js`，**只做 `export { onRequest } from '../../网站/functions/api/…'` 的转发层**
    （实现仍只有一份，两种项目布局都能命中）。部署后 `/api/dict` 立即返回真实 JSON ✓
- 🐛 **第二个坑**：`/api/translate` 稳定返回 CF 边缘错误页（16B `error code: 502`，用时 ~1.4s），
  而同一 Function 里 `/api/dict` 访问 moedict / freedict / wikipedia 都正常 ⇒ 是**该上游请求让 isolate 挂掉**。
  已做的加固：`onRequest` 全部包顶层 try/catch（任何意外都返回 JSON，绝不吐 CF 错误页）、
  translate 改**双源**（MyMemory 主 → Google gtx 备，返回 `provider` 标注）、失败带 `tried[]`、
  超时统一 2.5s、UA 改浏览器样。
- 🔧 **诊断探针**（已随代码提交）：`/api/dict?probe=<url>`（只允许 `api.mymemory.translated.net` /
  `translate.googleapis.com` / `www.moedict.tw` 三个主机，避免变开放代理）→ 返回 `{status, size, ms, sample}`，
  用来判定「边缘能否访问某上游」。**待办**：等 GitHub 网络恢复、部署后用它对 MyMemory 做最终判定。
- 🛟 **降级路径**：翻译失败时面板显示「翻译暂不可用（…）」+「右键选中文字送 🤖 AI 助手翻译」；
  释义 Tab（本次主功能）**完全不受影响**：萌典 / Free Dictionary / Unihan / wiki 均已线上实测可用。
- ✅ **线上终验结果（释义链全通）**：
  `source=moedict`（真实萌典：ㄓ/zhī/的、底。+ 英文释义）、`source=unihan`（国 → guó/囗/8 画）、
  `source=freedict`（hello → 音标 + noun/verb/interjection）、`source=wikipedia`（仁 → 真摘要）、
  `/api/dict-links`（4 条 zh 链接）——**全部 200 且内容正确**。
- ❌ **仍未解决**：`/api/translate` **与** `/api/dict?source=translate` 上仍返回 CF 错误页（16B）。
  已排除/已做的：
  - 路由没注册？**否**（OPTIONS→204、缺 q→400 都正常）；上游不可达？**否**——用
    `/api/dict?probe=…` 从边缘实测：MyMemory **429**（免费额度用尽，body 是
    「MYMEMORY WARNING: YOU USED ALL AVAILABLE FREE TRANSLATIONS FOR TODAY…」）、
    gtx **429**（Google 也屏蔽 CF 出口 IP）、moedict 200（76ms）⇒ **边缘能访问上游**。
  - 「非 2xx 未消费 body 会被判 502」的坑已修（统一先 `await r.text()` 再判断）——但 502 仍在。
  - 下一步建议（择一）：① 用**带 Key 的翻译服务**（DeepL / Azure Translator / LibreTranslate 自建），
    Key 放 Pages 环境变量；② 在 CF 面板看那次部署的 **build/runtime 日志**（Functions 的 502 会留痕）；
    ③ 翻译 Tab 直接改为调用站内已有的 **AI 助手（用户自带 DeepSeek Key）**，绕开公共免费翻译的 IP 限流。
- 📌 **公共免费翻译的现实**：MyMemory 匿名额度是 **按出口 IP 每天 5000 字**，而 CF 的出口 IP 是共享的
  ⇒ 即使 502 修好，也可能经常拿到 429。要稳定就得自带 Key。
- ⚠️ **运维提醒**：本机到 github.com:443 偶发长时间不通（本次 push 连续失败 3 次、每次 75s 超时后
  才第 4 次成功）——`git push` 建议写重试循环；`deploy/trigger_build.sh` 也因 wrangler OAuth 过期
  （`Invalid access token`，9109）暂时用不了，需要在面板重新登录 wrangler 或配 `.env` 的 `CF_DEPLOY_HOOK`。


### ⏭️ 下一步（待办）
1. **检索页可优化**：快照层 11 MB 首搜要拉 64 片（已缓存 1 天）；若要更快可上「书名/篇名命中直接命中 + 快照懒加载」或
   缩到 `--snap-head 120 --snap-tail 40`；另可补**简繁折叠**（现在按原文匹配，繁简不同字会漏）。
2. **第三方词典**：國學大師 / 中華典藏 现由「探活」管着（默认 hidden）；它们的**站内搜索 URL 仍未在境内验过** ——
   探活连续 2 次通过后若 URL 不对，改 `网站/js/dict-links.js` 里 `SOURCES` 的 `url()` 一行即可。
   另：把 `deploy/dict_links_probe.js` 挂上**本机 cron**（每周一 09:10，见 README「站外词典探活」）。
3. **495 本英文批量书未上架**：不在 `books-data.json`（书库页不列），目前只能靠检索页进入；如需上架要在合并脚本里补。
4. **多版本莎剧同名覆盖**：`_site_data/{书名}.json` 会被同名后写覆盖（如 Troilus #1124/#1528），如需并存需改名。
5. 词表释义：仍 **待补 11623 + need_ai 16165**（可配 `DEEPSEEK_API_KEY` 做 AI 精修，或再引入词级源）。
6. 可选：改写 `71d7901` 提交信息需 `rebase -i` + `push --force`。
7. 接 FastAPI 后端（`read_count`/`added_at` 真值）—— 沿用 10-01 待办。
8. **书数据补 `lang` 字段**：查词面板的多语种回退依赖它（现在只能按正文猜汉字/拉丁，法德西书会走英文链）。
   在 `merge_to_site` / `gutenberg_import` 写书时带上 `lang` 即可，前端已优先读 `book.lang`。

## 已完成（2026-10-01）：维基文库书源 + 书库页重构（封面网格）

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
- **本轮未提交/未推送**（2026-10-02）：分章修复后的 `网站/_site_data/*.json`（约 600 文件）、`library-index.json`、
  `文本/新书/wordbank_en.json`、`memory-bank/` 仍在工作区；站长按**已推批次**手动重推（`bash ~/gutenberg_project/push_batch.sh K`）。
- **多版本莎剧同名覆盖**：`_site_data/{书名}.json` 以「书名」为键，同名多版本（如 Troilus #1124 / #1528）**后写覆盖前者**；
  如需并存须让书名可区分。
- **分章剩余 8 本**：其中 7 本为**真单篇**（The Secret Sharer / Civil Disobedience / Walking / Amy Foster 等，1 章合理），
  仅 #317《The Culprit Fay, and Other Poems》诗集（多行标题）未拆。
- **`~/gutenberg_*` 占家目录约 28G**（cleaned 22G、other 5.5G、zh_dup 150M 等）；`gutenberg_other`（15850 本非中英文）与
  `gutenberg_zh_dup`（344 本维基重复）在确认后可按需清理（`gutenberg_cleaned` 含注释回填依赖，清理前先确认站点 `_site_data` 已就绪）。
