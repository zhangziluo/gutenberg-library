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
- 写脚本的硬约束（bash 3.2 + CJK）：变量展开一律 `${VAR}`（`$VAR` 紧跟全角字符会被并入变量名）；
  不用空数组裸展开（`set -u` 会报 unbound）；`set -e` 下避免 `[ ... ] && cmd` 作语句。

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
