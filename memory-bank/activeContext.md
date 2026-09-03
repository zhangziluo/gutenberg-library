# Active Context（当前状态与下一步）

## 当前（进行中）
- ✅ 古籍站点注释显示已修复：下划线注释 + 点击卡片，**三语释义（简体/繁体/英文）已上线**。
  - 覆盖：简体 86%、繁体 86%、英文 93.6%（25934 条注释）；420 个最高频字为人工精编。
- ✅ 阅读页三档模式（新手/进阶/专家）、AI 阅读器下划线注释层均已实现。
- ✅ Cloudflare 25 MiB 限制已规避：`books.json` 瘦身为轻量索引。
- ✅ AI 阅读器跳转修复：`/reader/* → /public/reader/*` 200 重写已推送（等待线上验证）。
- 📦 最近提交：`f472ab9`（/reader 重写）；上一提交 `dcca110`（books.json 瘦身 + 三语释义数据）。

## 下一步（规划）
- **古登堡中文书入库（Gutendex API）**：
  - Gutendex 只索引英文书名/作者为主；中文书（Project Gutenberg 中文书目）需另行定位（可用其 language=zh 过滤 + eBook 编号对照）。
  - 走现有流水线：`gutenberg_import.py`（下载 txt → build_books 切分 → 注音注释 → 合并）新增一条 Gutendex 拉取入口。
  - 入库前核算两大约束：**单本 JSON < 25 MiB**、**文件总数 ≤ 20000**（每本 = raw txt + data/books + _site_data 单书，多副本计数）；量大时推进 systemPatterns 里的 `books/{id}.json` 目录化与 R2 方案。

## 待确认/风险
- Cloudflare 线上对「/reader 重写 + 三语注释」的最终验证结果（等用户反馈 build log / 点击现象）。
- 若从 32 本扩到数百本，`_site_data` 平铺单书 + books.json 索引的扩展性需重新评估（目录化 or R2）。
