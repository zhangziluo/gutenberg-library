# System Patterns（系统模式）

## 书库数据架构（目标设计）
- `_site_data/books_index.json` —— **轻量索引**（书名/篇数/分类，仅目录用）
- `_site_data/books/{id}.json` —— **单本详情**（正文 + 注释，按需下载）

> ⚠️ 现状标注（与目标命名的差异）：当前仓库实际仍是
> `_site_data/books.json`（轻量索引）+ `_site_data/{書名}.json`（单本详情，平铺在同目录）。
> 二者遵循**同一条原则**，若日后入库量大，再迁移为 `books_index.json + books/{id}.json` 的目录结构，
> 并同步更新 `common.js` 的 DATA_BASE 解析逻辑（无状态、低成本切换）。

## 核心原则
- **前端按需动态加载**：目录只读索引，正文/注释进单书页才请求对应单书 JSON——避免把全书内容打进单个大文件而触发 25 MiB 上限。
- **本地词典数据分片**：ECDICT 英汉词典（72.6 万词 / 71.8 MiB）按首字母分片为
  `文本/新书/data/ecdict_en/ecdict_{a..z}.json`（最大 7.4 MiB），
  查询经 `gloss_lib.ecdict_shard()` 惰性加载 + LRU（≤3 片）；遍历时按首字母聚簇
  （`fill_glosses.gloss_order()`）以避免分片抖动。避免单文件过大、也不把整库读进内存。
- 数据演进方向：大 JSON 必须拆分；文件数接近 20,000 上限时考虑 R2 + 签名 URL 或改用接口。

## 其它关键模式
- **注释三语释义**：annotation 条目 = `word/pinyin/zh_cn/zh_tw/en/note/multi/rare`；
  - 中文书：来源「人工精编 override > 新华字典自动 > CC-CEDICT 英文」，生成见 `fill_glosses.py`。
  - 英文书：难词由 ECDICT 常用词表判定（非停用词且不在前 N 常用词），
    释义来源「ECDICT（中文/英文/音标）> Free Dictionary API 网络英文释义+IPA」；词存小写，
    前端 `reader.js` 对 ASCII 词做大小写不敏感匹配（正文句首可能大写）。
- **三档阅读模式**：新手/进阶/专家 = 字号 + 注释密度；档位存 localStorage(`annLevel`)，前端按 `rare/multi` 过滤。
- **构建双布局**：`网站` 根目录（Cloudflare 直出）与 `dist`（build.sh 产出）两套并存，路径类改动需同时兼容。
