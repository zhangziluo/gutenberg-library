# Active Context（当前状态与下一步）

## 当前（进行中）
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
  - 回归链：106 本全量 `_build_one` **0 异常 / 0 空切分** → 入库 29 本 →
    `fill_glosses.py --no-network`（58 文件 / 218,482 条；简繁 91.7%、英文 94.6%；
    英文词 21,331 → 中文释义 94.6%、英文释义 90.3%、音标 76.4%）→ `deploy/build.sh`
    （dist 101 MiB / 155 文件）。

## 已知待办（按优先级）
1. ⚠️ **菜根譚前後集 #24040 源文件错码（待拍板）**：古登堡官方 `pg24040.txt` 正文整体乱码
   （例：`頦菜鈭亦剝剖亙蝎寧`），**重新下载字节完全一致** → 非下载问题；且
   big5/gbk/cp950/euc-* 互转均失败 → **编码不可逆**。方案 A：另取正确源（维基文库等）替换 raw；
   方案 B：从书库撤下（#24050《菜根譚》已可读）。
2. ⚠️ **`fill_glosses.py` 联网预取极慢（性能 bug）**：step 2 的
   `need = sorted(... G.en_word_needs_api(w) ...)` 中 ECDICT 分片被反复重新解析
   （`sample` 显示热点 `builtins.sorted → _json.scan_once_unicode`），3000 预算跑 15 min
   仍不足 200 条。本次已改用 `--no-network`（ECDICT 打底）。修复思路：按 `gloss_order()`
   首字母聚簇遍历 / 预载分片，或直接去掉 step 2。
3. ⚠️ **自动分类未接通**：`scripts/classify_books.py` 默认读 `data/books.json`（本项目**不存在**），
   且需 `DEEPSEEK_API_KEY`；`pipeline.sh` 已有守卫（缺失即提示跳过）。
4. 📋 **待入库批次**：`文本/新书/i.txt` 11 本英文书（37106/1260/1661/174/2701/2600/1400/768/4300/2554/28054）
   —— **用户指示暂不跑**。执行：`bash 文本/新书/add_books.sh --file 文本/新书/i.txt`
5. 📋 英文释义可继续补全：修好性能后 `python3 文本/新书/fill_glosses.py --api-budget=8000`
   （缓存 `data/ecdict_api_cache.json` 持久，可多次累积）。

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
- **`dist/` 未纳入版本库**（`.gitignore` 含 `dist/`）：提交 `afe688d` 内含 252 文件 / 174 MiB 待提交体积，
  网页上线以 Cloudflare 直读 `网站/` 为准，`dist/` 仅本地/备用。
- **网络不稳**：本机到 `raw.githubusercontent.com`（ECDICT 63 MiB 需 git 克隆更稳）与 `gutendex.com`、
  `api.dictionaryapi.dev` 均很慢/不可达；脚本已做重试+熔断+缓存，但联网步骤可能耗时数十分钟。
- 书库若扩到数百本，`_site_data` 平铺单书 + `books.json` 的扩展性需重估（目录化 or R2）。
