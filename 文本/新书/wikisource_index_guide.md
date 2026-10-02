# 维基文库中文电子书索引 · 采集与入库说明

> ⚠️ 本文件与 `wikisource_index.md`（**索引本体**）仅差 `_guide`，
> macOS 文件系统**大小写不敏感**，所以说明文件特意加了 `_guide` 后缀，
> 避免与索引同名相撞（曾因 `WIKISOURCE_INDEX.md` 与 `wikisource_index.md` 同一 inode 而被覆盖）。

## 索引

一套文件（`文本/新书/`）：

| 文件 | 用途 |
|------|------|
| `wikisource_index.md` | **可读索引**：按四部（經/史/子/集/叢）分类，含推荐清单与 `fetch` 用法 |
| `wikisource_index.json` | 结构化数据：`title / page / bu / sub / region / length / authors / versions / in_library / recommended` |
| `wikisource_index.tsv` | 制表符清单：`page title bu sub region authors length in_library`，供批量脚本 |
| `build_wikisource_index.py` | 生成上面三个文件（`--from-json` 只按现有 json 重建目录） |
| `wikisource_index_backfill.py` | 补齐缺失的页面元数据（长度/作者），断点续跑 |
| `wikisource_index_guide.md` | 本文件：采集与入库说明 |

站点侧：`网站/assets/data/wikisource-pending.json`（**「待入库」预览数据**，由
`build_wikisource_index.py` 一并生成，书库页「待入库」页签读取）。

## 批量抓取与入库

```bash
PY=.venv/bin/python        # toolkit 需要 requests/bs4，务必用 .venv（脚本会自动选）

# 一条龙：抓取 → 入库（智能分章 + 生成注释）→ 释义回填 → 重建目录/阅读器数据
bash 文本/新书/wikisource_recommended.sh          # 全部推荐（122 本，耗时较长）
bash 文本/新书/wikisource_recommended.sh 10       # 先试 10 本

# 或分步
$PY 文本/新书/wikisource_batch.py list            # 候选清单 → _ws_fetch/selected.tsv
$PY 文本/新书/wikisource_batch.py fetch           # 批量抓取（可续跑）
$PY 文本/新书/wikisource_batch.py commands        # 生成 _ws_fetch/ingest_commands.sh
$PY 文本/新书/wikisource_batch.py ingest          # 入库 + 释义回填 + 重建
$PY 文本/新书/wikisource_batch.py merge           # 只重建目录/阅读器数据

# 只挑一本 / 增量
$PY 文本/新书/wikisource_batch.py fetch  --page 論語 --retry-failed
$PY 文本/新书/wikisource_batch.py ingest --page 論語
```

候选默认**按体量从小到大**（`--order size`）——先出成果，不被《四庫全書總目提要》
这类大部头卡住；想按四部顺序用 `--order default`。小书约 10 秒/本，大部头可能十几分钟。

断点续跑：进度在 `文本/新书/_ws_fetch/{fetch_state,ingest_state}.tsv`（gitignore），
重跑自动跳过已完成项；`fetch --retry-failed` 重试上次失败的。
正文不足 200 字的抓取结果（红链空壳，如未录入的卷页）会被 `ingest` / `commands` 自动跳过
（`--min-chars N` 可调）。

## 入库脚本内部做了什么

`wikisource_import.py`（被 batch 调用）除原有「转正本 + 更新 library-index + merge」外，新增：

1. **智能分章** `--split auto`（默认）
   - 维基文库很多典籍是「一个页面放全文」，既无子页也无 `==小标题==`，toolkit 只能整页 1 章；
   - 导入时按 **卷/回/篇/章/品/則/節/折** 等标题行再切（`第一卷`、`第一回 標題`、
     `卷一`、`卷十二`、`〔篇名〕`、`序/凡例/跋`…），按「命中行数最多的模式」投票，避免误切；
   - 护栏：≥2 个切分点、每段 ≥40 字（过短并入上段）、切分点前的内容单列「序」；
   - 判出的标签（卷/回/篇…）自动作为阅读器篇目标签 `section_label`（可用 `--label` 覆盖、
     `--split none` 关闭）。
   - 工具链里的 **子页排序**也一并修正：`序/凡例/楔子…` 恒在正文前，中文数字按数值排
     （`卷第一 < 卷第二 < 卷第十`，原先按汉字码位排会乱）。
2. **生成注释**（默认开，`--no-annotate` 关）
   - 复用 `gutenberg_import.annotate_book`：词库最大匹配 → 难字/难词 → 写正本顶层 `annotations`；
   - 随后 `fill_glosses.py` **释义回填**（`zh_cn/zh_tw/en/note/pinyin`）即能把释义补全 ——
     这就是「入库脚本同时完成网站释义回填」的那一步。
   - 顺带修了 `gutenberg_import.merge_pending()` 的历史 bug：`wordbank_pending.json` 实际是
     **纯字表（list）**，旧实现按 dict 处理会 `list.setdefault` 崩，现已兼容两种格式。

`--force`（默认加）：跳过「许可未知」的页面、其余照收；要严格合规用 `--strict`。

## 书库页「待入库」预览

`网站/{library.html,js/library.js,css/library.css}` 新增**范围切换**：

- **本站藏书**（原有行为）/ **待入库 · 维基文库 📥**（新）
- 待入库模式另有「只看推荐 ⭐」勾选（默认开 → 122 本；关掉 → 全部 1070 本候选）
- 卡片沿用五部配色，右上角 📥 徽标、左上角 ⭐，**点击跳维基文库原页**（新标签）；
  支持同一套分类页签、搜索、排序（待入库按体量/书名排）、分页，URL `?mode=pending` 可分享。
- 每张卡片下方有 **「📋 复制入库命令」**：一键复制本机命令
  （`wikisource_batch.py fetch --page "…" --retry-failed && … ingest --page "…"`），
  拿去终端跑即可——脚本内含智能分章 + 释义回填。
- 数据 `网站/assets/data/wikisource-pending.json`（1069 条 ≈ 270 KB，仅中土未入库）。

测试：

```bash
JSDOM_PATH=/tmp/vmtest/node_modules/jsdom node tests/library/library-pending-test.js   # 17 项
```

## 索引内容

来源：**中文维基文库**（`zh.wikisource.org`）的分类树，非人工臆测——
每条都带真实页面标题（可直接喂给 `wikisource_toolkit.py fetch`）。

| 维基文库分类 | → 索引部类 |
|---|---|
| `Category:十三經` 及「周禮 / 孟子 / 易 / 春秋左氏傳 / 春秋公羊傳 / 十三經註疏 / 诗经」 | 經部 |
| `Category:史部` 及「正史 / 別史 / 編年 / 紀事本末 / 雜史 / 載記 / 政書 / 目錄 / 地理 / 日本·朝鮮·越南·琉球典籍」 | 史部 |
| `Category:子部` 及「儒家 / 道家 / 法家 / 兵家 / 農家 / 醫家 / 雜家 / 小說家 / 類書 / 藝術 / 譜錄 / 蒙學」 | 子部 |
| `Category:集部` 及「別集 / 總集 / 俗曲 / 古文觀止 / 古文辭類纂 / 文言散文」 | 集部 |
| `Category:四庫全書` | 叢部 |
| `Category:詩集`、`Category:史書` | 集部·詩 / 史部 |
| 「日本典籍 / 朝鮮典籍 / 越南典籍 / 琉球典籍」 | 单独成节「域外漢籍」（可选） |

> 顶层分类成员（史/子/集 各 68/96/278 页）维基文库未再细分，索引里归入
> 各部「**總類**」，不冒充 雜史/雜家。

## 重新采集（网络不稳时的做法）

三步，全部用 `curl`（短超时 + 低并发 + 多尝试；`requests` 在这个站上易 ReadTimeout）：

1. **分类成员**：
   ```
   action=query&list=categorymembers&cmtitle=Category:X&cmlimit=500&cmtype=page|subcat
   ```
   注意 `cmlimit=500` 是上限，超大分类（如 朝鮮典籍）会截断。
2. **页面长度 + 作者**（**必须分两个请求**，合并成一个会显著变慢）：
   ```
   action=query&titles=A|B|...（25 题/批）&prop=info
   action=query&titles=A|B|...（25 题/批）&prop=links&plnamespace=102&pllimit=max
   ```
   `Author:` 命名空间 = 102；作者链接会被页头 navbox 污染
   （如《二十四史》模板让「新唐書」出现 26 位“作者”）→ 索引里 **>5 位即弃用**。
3. **汇总去重**：子页折叠（`史記/卷018`→`史記`）、版本后缀归一（` (四部叢刊本)`）、
   同名异本合并（`versions` 记录），再与 `library-index.json` 比对标「已入库」。

中间快照（`build_wikisource_index.py` 的输入）：

- `/tmp/ws_all.json` —— 去重后条目（title/page/bu/sub/versions/sources/in_library）
- `/tmp/ws_meta.json` —— 每页 length / authors

> `build_wikisource_index.py` **只做「汇总 → 索引」**；缺快照会直接报错并提示。
> `/tmp` 被清理后需按上面三步重新采集（约 10 分钟，视网络而定）。

## 入库

```bash
# 单本抓取（产物 novels_json/<书名>.json）
cd 文本/新书/wikisource_complete_toolkit
python3 wikisource_toolkit.py fetch "論語"

# 一键（抓取 + 合规闸门 + 写 data/books + library-index + merge_to_site）
cd 文本/新书
bash add_books.sh --source wikisource --title "論語" \
     --author 孔子 --category 經部 --subcategory 四書 --label 篇
```

许可合规由 `wikisource_complete_toolkit/license_detector.py` 逐页判定，
仅 `safe_to_use=True` 的页面进书库。

## 注意

- 索引里的「页面标题」可能带版本后缀（`（四部叢刊本）`/`（四庫全書本）`）：
  **fetch 要用「页面标题」列**，不是显示名。
- 同名异本（如 `搜神記` 与 `搜神記 (四庫全書本)`）已合并为一条，`page` 取先遇到者。
- 卷数/篇数未预取（需逐本抓取才准），`length`（页面字节数）仅作规模参考；
  `四部叢刊本` 的父页常只是目录，正文在子页，故父页 length 很小属正常。
