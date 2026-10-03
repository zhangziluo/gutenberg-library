# 一堆古书

> 没什么正经的，就是一堆古书。

一个**中英双语公版书在线阅读站**：中文收古登堡计划（Project Gutenberg）与维基文库（Wikisource）的公版古籍与近现代文学，按 **经、史、子、集、丛** 归类；英文收古登堡计划原版书，也用同一套四部分类。带生僻字即时释义、点词查典（康熙 / 说文 / 在线词典）、三档阅读模式、AI 助手，以及每日一句一卦。

🌐 在线体验：[myfami.cn](https://myfami.cn)（部署中，暂可用 [myfami.pages.dev](https://myfami.pages.dev)）

---

## 这是什么

古登堡计划的中文公版书不算多，但胜在干净；维基文库补上了大量中文古籍（经史子集都有，带校勘与来源）。这个站点把两处的公版文本整理成**带辅助阅读功能的在线版本**——不是简单的 TXT 堆砌，而是试图让古文阅读变得"零障碍"：

- 生僻字、难词在正文里直接标出来，点一下就有拼音和释义；
- 想追更古的义项，右侧面板直接翻《康熙字典》《说文解字》；
- 读累了切"新手"档，注释更密；老手切"专家"档，页面干净。

## 书库现状（2026-10）

| | 数量 |
|---|---|
| 上架图书（`books-data.json`） | **195 本**（中文 116 · 英文 79） |
| 篇目合计 | **7,090 篇** |
| 分类明细（`library-index.json`） | 經 11 · 史 8 · 子 97 · 集 62 · 近現代文學 8 · 叢 1 |
| 书源 | 古登堡计划 **180** 本 · 维基文库 **15** 本 |
| 单书正本（`data/books/`） | 720 个 JSON |
| 阅读器数据（`网站/_site_data/`） | 约 690 个 JSON（单书 + 目录/词表）＋ 康熙·说文分片 256 个 |
| 全站文件 | ≈ 1000（Cloudflare Pages 上限 20,000，还很宽裕） |

英文书不是"外挂"：小说归 **子部·小说家**（志怪 / 公案 / 童话 / 寓言）、戏剧归 **集部·戏曲**、随笔归 **集部·别集**、食谱归 **子部·谱录**——跟中文书用同一套"文化户口本"。

## 核心功能

- 📚 **五部分类** —— 经、史、子、集、丛（另有「近現代文學」归集部）。不是"小说/非小说"这种偷懒分法，是给每本书找个文化户口本。封面按五部配色（经深蓝 / 史赭石 / 子墨绿 / 集暗紫 / 丛深灰）。
- 🔴 **红字释义** —— 正文里的生僻字、难词带下划线，点击即看拼音和释义。不用切出去查字典，阅读流不断。
- 📖 **右侧释义面板**（桌面端）—— 聚合「本站释义 → 康熙字典 / 说文解字（离线分片）→ Wiktionary / 维基百科摘要」；**左键查词、右键送到 AI**。
- 🎚 **三档阅读模式** —— 新手 / 进阶 / 专家＝字号＋注释密度，档位记在本地。
- 🌐 **简体 / 繁体 / 英文** —— 正文可一键简繁互转；释义可在「简中 / 繁中 / English」三语间切换（默认繁中）。
- 📜 **今日一句** —— 每天一句古文，点一下换一条。
- ☯️ **今日一卦** —— 每天一卦，配易经原文。当签抽着玩。
- 🤖 **AI 助手** —— 接入 DeepSeek（自带 Key，存本地），支持问答、翻译、书籍推荐，回答可存为笔记。
- 📥 **书库「待入库」预览** —— 维基文库还有 1000+ 本候选，书库页可直接预览、一键复制入库命令，慢慢搬。
- 🔒 **不登录、无后端** —— 纯静态站，数据全在你自己浏览器里。


## 页面上有什么

| 页面 | 地址 | 说明 |
|---|---|---|
| 首页 | `index.html` | 每日一句、全站搜索、分类入口、今日一卦 |
| 书库 | `library.html` | 封面网格 + 分类页签 + 排序 + 搜索 + 分页；可切「待入库 · 维基文库」 |
| 书目 | `book.html?book=史記` | 详情页（大封面 / 批注者 / 本版特色 / 开始阅读） |
| 阅读 | `reader.html?book=史記&index=3` | 正文 + 注释 + 释义面板，翻章、字号、进度记忆 |
| 分部 | `category/jing.html` 等 | 经 / 史 / 子 / 集 / 丛 五部分类页 |
| 其他 | `ai-settings.html` · `ai-guide.html` · `links.html` · `sponsor.html` · `writing/` | AI 设置 / 新手指南 / 友链 / 捐助 / 网站日志 |

## 数据长什么样

内容全是静态 JSON，分三层：

**1. 单书正本** `data/books/{key}.json`（源数据，体积大，**不进版本库**）

```json
{
  "book": "論語", "author": "孔子",
  "category": "經部", "subcategory": "四書",
  "section_label": "篇", "lang": "zh",
  "chapters": [{ "title": "學而第一", "content": "子曰：學而時習之……" }],
  "annotations": [
    { "word": "慍", "pinyin": "yùn", "zh_cn": "…", "zh_tw": "…", "en": "…",
      "is_difficult": true, "src": "學而第一" }
  ]
}
```

**2. 主索引** `library-index.json` —— 五部分类 + 每本的 key / 书名 / 作者 / 篇数 / 来源

**3. 站点数据**（部署用，全在 `网站/`）

| 文件 | 用途 |
|---|---|
| `网站/_site_data/{书名}.json` | 阅读器单书（正文 + 注释），进阅读页才按需加载 |
| `网站/_site_data/books.json` | 轻量目录索引 |
| `网站/assets/data/books-data.json` | 书库页统一数据源（含来源/许可/简介/特色等 19 个字段） |
| `网站/assets/data/wikisource-pending.json` | 书库「待入库」预览 |
| `网站/_site_data/dict/{kangxi,shuowen}/0..127.json` | 康熙 / 说文按字码点分片，前端按需取 |

> Cloudflare Pages 有 **单文件 ≤ 25 MiB、文件数 ≈ 20,000** 的硬上限，所以正文与注释始终拆到单书文件、按需请求；词典也分片；书库索引只留目录字段。

## 怎么跑起来

纯静态站点，`网站/` 就是部署根：

```bash
# 本地预览（浏览器不允许 file:// 直接读 JSON，需起个服务）
python3 -m http.server 8000
# → http://localhost:8000/网站/index.html
```

macOS 也可以双击 `网站/启动站点.command`。

部署：Cloudflare Pages，根目录 `网站`，构建命令 `exit 0`（直出不跑构建）。`deploy/build.sh` 可另生成一份 `dist/`（本地/备用，已 gitignore）。

项目已与 GitHub 连接，**push 会自动触发 Pages 构建**；若想显式再触发一次（或 push 没触发），用：

```bash
bash deploy/trigger_build.sh            # 触发一次构建
bash deploy/trigger_build.sh --list     # 看最近 5 次部署（提交/阶段/状态）
bash deploy/trigger_build.sh --dry-run  # 只显示将做什么
```

凭据按优先级自动选（都没有就友好退出，不报错）：`.env` 里的 `CF_DEPLOY_HOOK`（**推荐**，Pages 控制台
「设置 → 构建与部署 → 部署钩子」拿 URL）→ `.env` 里的 `CF_API_TOKEN`+`CF_ACCOUNT_ID`+`CF_PAGES_PROJECT`
→ 本机 `npx wrangler login` 的 OAuth 凭据。`文本/新书/pipeline.sh` 已在 `git push` 成功后自动调用它
（`--no-trigger` 可关闭）。

## 工具链（`文本/新书/`）

搬书、标释义、生成词表都在这里。日常两个一键脚本就够：

```bash
# 古登堡计划：按编号入库（编号可用 --file 清单）
bash 文本/新书/add_books.sh 12345 67890

# 维基文库：按页面标题入库（自动过版权合规闸门）
bash 文本/新书/add_books.sh --source wikisource --title "儒林外史" \
     --author 吳敬梓 --category 子部 --subcategory 小說家 --label 回

# 维基文库「推荐清单」批量：抓取 → 入库（智能分章 + 生成注释）→ 释义回填 → 重建
bash 文本/新书/wikisource_recommended.sh 10     # 省略参数＝全部
```

| 脚本 | 作用 |
|---|---|
| `add_books.sh` / `pipeline.sh` | 一条龙：入库（含生成站点数据）→ 释义回填 → 构建 → 提交推送 |
| `gutenberg_import.py` | 古登堡计划入库（下载 → 清洗 → 切分 → 写正本 + 索引） |
| `wikisource_import.py` | 维基文库入库（许可闸门 + **智能分章** + 注释生成） |
| `wikisource_batch.py` | 维基文库索引的批量抓取 / 生成命令 / 入库 / 重建 |
| `merge_to_site.py` | 由 `data/books` + `library-index` 重建 `网站/_site_data` 与 `books-data.json` |
| `fill_glosses.py` `definition_fill.py` | 释义回填（CC-CEDICT / 新华 / 康熙 / 说文 / ECDICT / 网络词典） |
| `vocab_extract.py` `build_vocab_final.py` | 全库词汇抽取 → 前端词表（供正文分词定边界） |
| `build_wikisource_index.py` `wikisource_index_backfill.py` | 维基文库索引生成 / 页面元数据补抓 |

维基文库那套的采集与入库说明见 `文本/新书/wikisource_index_guide.md`。

## 测试

```bash
# 词表 / 分词（无需依赖）
node -e "const V=require('./网站/js/vocab-matcher.js');console.log(V.selftest().pass)"   # 66 项
node tests/vocab-matcher/dom-test.js          # 21 项
node tests/vocab-matcher/integration-test.js  # 26 项（真实书 JSON + 真实词表 + opencc 简繁）

# 书库页（需要 jsdom，仓库无根 package.json，装在临时目录即可）
npm i --prefix /tmp/vmtest jsdom
JSDOM_PATH=/tmp/vmtest/node_modules/jsdom node tests/library/library-pending-test.js    # 17 项
```

## 接下来

- 📥 **继续搬维基文库** —— 索引里还有 1000+ 本候选（书库页「待入库」可预览、可一键复制入库命令），
  抓取/入库脚本都已就绪，一本本搬。
- 📋 **生词本** —— 收藏生词、一键导出 txt（还没开始做）。
- 🎯 **英文练习** —— 用生词生成选择题、crossword、猜谜卡片（在计划里）。

## 如何贡献

### 提书
1. Fork 本仓库
2. 按 `data/books/{key}.json` 格式放一本正本（字段见上文「数据长什么样」），
   中文正文用繁体、段落以 `\n` 分隔
3. 在 `library-index.json` 对应分部里加一条（key / 书名 / 作者 / 篇数 / 来源）
4. 重建站点数据：`python3 文本/新书/merge_to_site.py`
5. 收尾（释义回填 → 构建 → 提交）：`bash 文本/新书/pipeline.sh`
6. 提交 PR

> 更省事的做法是直接用现成工具搬：古登堡编号走 `bash 文本/新书/add_books.sh <编号>`；
> 维基文库走 `bash 文本/新书/add_books.sh --source wikisource --title "<页面标题>"`——
> 它会自动检查该页的版权模板，只放行公版内容，再自动跑切分、生成注释与站点数据。

### 补释义
- 人工精编（优先采用）：`文本/新书/data/gloss_override.json`，键＝字/词，值＝释义
- 离线词典（可整体替换或扩充）：`文本/新书/data/{cedict_words,kangxi,shuowen,xinhua_word}.json`
- 改完跑 `python3 文本/新书/fill_glosses.py` 重新回填到各书 JSON

### 其他
- 提 bug、提功能建议、提交 PR 都欢迎；**书源建议请附公版证明**（古登堡编号，或维基文库页面链接）。

站长是个汉语言文学系毕业生，代码写得一般，纯靠 AI 编程把这个网站做了出来。欢迎各路高手来帮忙。

## 来源与许可

- 文本来源：**古登堡计划（Project Gutenberg）** 与 **中文维基文库（Wikisource）**，皆属公有领域 / 自由许可内容；单书数据保留 `source_url` 与 `license` 以便追溯。
- 本站代码与整理数据开源；文本内容仅供学习研究使用。

