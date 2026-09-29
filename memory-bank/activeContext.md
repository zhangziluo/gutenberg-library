# Active Context（当前状态与下一步）

## 当前（进行中）
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

## 已知待办（按优先级）
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
1. ⚠️ **自动分类未接通**：`scripts/classify_books.py` 默认读 `data/books.json`（本项目**不存在**），
   且需 `DEEPSEEK_API_KEY`；`pipeline.sh` 已有守卫（缺失即提示跳过）。
2. 📋 **待入库批次**：`文本/新书/i.txt` 11 本英文书（37106/1260/1661/174/2701/2600/1400/768/4300/2554/28054）
   —— **用户指示暂不跑**。执行：`bash 文本/新书/add_books.sh --file 文本/新书/i.txt`
3. ✅ **英文释义补全已完成**（2026-09-29，见下方第九批）：英文释义 93.1%、音标 84.7%；
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
- **`dist/` 未纳入版本库**（`.gitignore` 含 `dist/`）：提交 `afe688d` 内含 252 文件 / 174 MiB 待提交体积，
  网页上线以 Cloudflare 直读 `网站/` 为准，`dist/` 仅本地/备用。
- **网络不稳**：本机到 `raw.githubusercontent.com`（ECDICT 63 MiB 需 git 克隆更稳）与 `gutendex.com`、
  `api.dictionaryapi.dev` 均很慢/不可达；脚本已做重试+熔断+缓存，但联网步骤可能耗时数十分钟。
- 书库若扩到数百本，`_site_data` 平铺单书 + `books.json` 的扩展性需重估（目录化 or R2）。
