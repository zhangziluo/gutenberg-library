# Tech Context（技术背景与约束）

> 项目：古登堡计划中文电子书在线阅读网站（一堆古书）。本地开发 + Cloudflare Pages 部署。

## 平台硬约束（Cloudflare Pages，无法提升）
- **单文件 ≤ 25 MiB**（超出即构建失败：`Error: Pages only supports files up to 25 MiB`）。
- **静态资源文件总数上限 ≈ 20,000 个**（大量入库时须留意文件数预算）。
- 大文件必须**拆分**或**外挂 R2**，不能打包进单个 JSON 交付。

## 现状核查（2026-09）
- 书库共 32 本；`网站/_site_data/` 中最大的单书 JSON 约 **4 MiB**（施公案）；轻量索引 `books.json` 仅 **~3 KB**（此前 34 MiB 超限问题已通过「瘦身索引」修复）。
- 部署方式：Cloudflare Pages，根目录 = `网站`，构建命令 `exit 0`（纯静态直出，不跑 deploy/build.sh）。
- `deploy/build.sh` 产出 `dist/`（本地/备用部署用），对 books.json 再做瘦身。

## 部署要点
- `网站/_redirects`：仅含旧分类地址的 301 规则。
- `网站/js/common.js`：`DATA_BASE = '_site_data/'`，按 `_site_data/{書名}.json` 按需拉取单书。
- 首页（`index.html`）由 `daily-sentence.js`（每日一句）/ `home-search.js`（全站搜索）/ `daily-gua.js`（今日一卦）驱动，不依赖 `js/index.js`。

## 数据与脚本（文本/新书/）
- `gutenberg_import.py`：古登堡新书全流程（下载→切分→注音注释→合并到 _site_data）。
- `fill_glosses.py` + `gloss_lib.py`：三语释义回填（数据见 `data/` 子目录：CC-CEDICT / 新华字典 / gloss_override.json 人工精编 / pinyin_readings）。
- `slim_books_index.py`：把 books.json 重建为轻量索引（构建产物也调用）。
- `tradify.js`：opencc 简→繁子进程。
