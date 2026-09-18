# Active Context（当前状态与下一步）

## 当前（进行中）
- ✅ **英文书入库 + 英汉释义回填链路（2026-09-17，已提交推送）**：书库 94 → **106 本**
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

## 已知待办（按优先级）
1. ⚠️ **6 本英文书仍是「整本一节」**：Walden / The Jungle Book / The Wind in the Willows /
   A Little Prince / Grimms' Fairy Tales / The Arabian Nights —— 其章节标题为「无缩进小标题 /
   全大写标题 / 故事名」，超出 `en_chapter`（CHAPTER·Part·数字·罗马数字）识别范围，需按书补切分器。
2. ⚠️ **自动分类未接通**：`scripts/classify_books.py` 默认读 `data/books.json`（本项目**不存在**，历史 3 次运行
   均因此失败），且需 `DEEPSEEK_API_KEY`。已在 `pipeline.sh` 加守卫（缺失即提示跳过，不中断流水线）。
   要启用需：把输入改成项目真实书库（要求「含 id 的 JSON 数组」）并配 `.env`。
3. 📋 **待入库批次**：`文本/新书/i.txt` 已改为 11 本英文书（37106 Little Women、1260 Jane Eyre、
   1661 Sherlock Holmes、174 Dorian Gray、2701 Moby Dick、2600 War and Peace、1400 Great Expectations、
   768 Wuthering Heights、4300 Ulysses、2554 Crime and Punishment、28054 Brothers Karamazov）——
   **用户指示暂不跑**。执行：`bash 文本/新书/add_books.sh --file 文本/新书/i.txt`
4. 📋 英文释义可继续补全：`python3 文本/新书/fill_glosses.py --api-budget=8000`（缓存持久，可多次累积）。

## 上一批（历史，均已入库）
- ✅ 第七批中文书 10 本（2026-09-08）：隋唐演義/論語/滬語開路/白圭志/孟子字義疏證/安樂集/鄧析子/醉醒石/唐鍾馗平鬼傳/春秋繁露；
  新增切分器 `split_lunyu`/`split_juan_sc`/`split_fanlu`。
- ✅ 第六批 10 本：飛跎全傳/佛說四十二章經/洛神賦/晁氏儒言/水滸後傳/幼學瓊林/治世餘聞/琵琶記/雪月梅傳/龍川詞；新增 `split_chu`/`split_juan_num`/`split_yxql`。
- ✅ 第五批 8 本：天豹圖/梁公九諫/長恨歌/李娃傳/玉樓春/引鳳蕭/今古奇觀/後西遊記；新增 `split_jian`/`split_juans`/`drop_until_heading`/`normalize_fe_punct`。
- ✅ 全站页脚兄弟站点链接「日程编辑与提醒器」；三语注释（简/繁/英）+ 三档阅读模式 + 轻量索引 `books.json` 规避 25 MiB；
  AI 阅读器（深度学习）板块已整体移除。

## 待确认/风险
- **`dist/` 未纳入版本库**（`.gitignore` 含 `dist/`）：提交 `afe688d` 内含 252 文件 / 174 MiB 待提交体积，
  网页上线以 Cloudflare 直读 `网站/` 为准，`dist/` 仅本地/备用。
- **网络不稳**：本机到 `raw.githubusercontent.com`（ECDICT 63 MiB 需 git 克隆更稳）与 `gutendex.com`、
  `api.dictionaryapi.dev` 均很慢/不可达；脚本已做重试+熔断+缓存，但联网步骤可能耗时数十分钟。
- 书库若扩到数百本，`_site_data` 平铺单书 + `books.json` 的扩展性需重估（目录化 or R2）。
