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

## 部署要点
- `网站/_redirects`：仅含旧分类地址的 301 规则。
- `网站/js/common.js`：`DATA_BASE = '_site_data/'`，按 `_site_data/{書名}.json` 按需拉取单书。
- 首页（`index.html`）由 `daily-sentence.js`（每日一句）/ `home-search.js`（全站搜索）/ `daily-gua.js`（今日一卦）驱动，不依赖 `js/index.js`。
- `网站/js/reader.js`：注释层按 `annotations[].word` 贪心匹配（按长度降序 + 首字索引）；
  对 ASCII 词另做**大小写不敏感**匹配并输出**原文大小写**。

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
- `slim_books_index.py`：把 books.json 重建为轻量索引（构建产物也调用）。
- `tradify.js` / `pinyin_helper.js`：opencc 简→繁、pinyin-pro 注音（node 子进程）。
- `scripts/classify_books.py`：DeepSeek 自动分类（四部 + 英文 level）。**当前未接通**：默认输入
  `data/books.json` 不存在，且需 `DEEPSEEK_API_KEY`；`pipeline.sh` 已加守卫，缺失即跳过。

## 本地环境注意事项
- **本机无 `python`，只有 `python3`**；shell 为 **bash 3.2**（`set -u` 下空数组展开、`$VAR` 紧跟多字节字符
  均会出错，写脚本须用 `${VAR}` 且避免空数组裸展开）。
- 网络到 `raw.githubusercontent.com`、`gutendex.com`、`api.dictionaryapi.dev` 均很慢或不稳定：
  大文件（ECDICT 63 MiB）建议 `git clone` 取；联网步骤可能耗时数十分钟，脚本已内置重试/熔断/缓存。
