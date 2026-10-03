# 一堆古书 · 在线阅读网站

古登堡计划（Project Gutenberg）繁体中文古籍的在线阅读站点。
数据由 `文本/export_json.py` 生成到 `文本/_site_data/`，本站点通过浏览器读取展示。

## 页面结构

| 页面 | 地址 | 说明 |
|------|------|------|
| 首页 | `index.html` | 每日一句、经史子集分类入口、今日一卦 |
| 书目 | `book.html?book=史記` | 按分类分组的篇目列表，支持搜索 |
| 阅读 | `reader.html?book=史記&index=3` | 正文阅读，上一篇/下一篇、字号调节、进度记忆 |
| 检索 | `search.html?q=子曰` | 书目 / 篇目 / 正文关键词 + 离线查词 + 第三方词典外链 |

## 如何运行

站点需要本地 HTTP 服务器（浏览器禁止 `file://` 直接加载 JSON）：

**方式一（推荐，macOS）**：双击 `启动站点.command`，自动启动并打开浏览器。

**方式二（终端）**：在 **项目根目录**（即本文件夹的上一级）运行：

```bash
python3 -m http.server 8000
```

然后访问：http://localhost:8000/网站/index.html

## 在线词典代理（同域 `/api/*`）

查词面板与检索页的**所有在线请求都走同域 Worker**（Pages Function），前端绝不直连第三方
（避免 CORS 与「网络连接已中断」）：

```
GET /api/dict?source=moedict&lang=zh&q=之        → 萌典（www.moedict.tw）
GET /api/dict?source=wiktionary&lang=zh&q=之     → {lang}.wiktionary.org（extracts，截前 500 字）
GET /api/dict?source=wikipedia&lang=zh&q=仁      → {lang}.wikipedia.org
GET /api/dict?source=freedict&lang=en&q=hello    → api.dictionaryapi.dev（英文单词主源）
GET /api/dict?source=unihan&q=国                 → **本站静态分片**（拼音 / 部首 / 笔画，不联网）
GET /api/dict-links?lang=zh&q=之                 → 新窗口链接模板（只返回 URL，不抓页面）
GET /api/translate?q=<文本>&from=zh-Hant&to=en    → MyMemory 翻译

→ 成功 { source, query, result, … }；查不到 → 200 { error:"not found" }；上游失败 → 502 { error:"fetch failed" }
```

- **实现**：`functions/api/{dict,dict-links,translate}.js`（Cloudflare Pages Function，与站点同域部署）。
  转发到各上游（wiki Action API 带 `origin=*`；萌典 `Api-User-Agent`），响应头固定带
  `Access-Control-Allow-Origin: *`，**上游超时 2.5s**（前端 3s 放弃，留返程余量）+ try/catch，
  任何失败都返回 JSON 错误体；`unihan` 走 `env.ASSETS`（零网络）。
- **前端**（`js/dict-api.js` 回退链 + `js/reader.js` 渲染）：
  - 单字：离线（本站词表 · 康熙 · 说文）→ 萌典 → 中文 Wiktionary → Unihan（拼音 / 部首 / 笔画）；
  - 词语（2–5 汉字）：CC-CEDICT → 萌典 → 中文 Wiktionary；
  - 英文单词：Free Dictionary → en.wiktionary；多语种：`{lang}.wiktionary` → Free Dictionary({lang})；
  - 6+ 字符 / 整句：自动切「翻译」Tab（MyMemory），释义 Tab 改为逐词并列查；
  - **离线结果永远显示**；在线全挂 → 「未找到释义」+「在线释义暂不可用」，绝不空白；
  - 结果缓存 localStorage（`${source}:${lang}:${query}`，TTL 7 天）；
  - 「更多词典」折叠区点开才 `window.open`（只跳转，不抓第三方页面、不预取）。
- **本地验证**（模拟同域环境）：

```bash
node tests/library/serve-local.js 8790        # 静态站 + /api/* 走真实 Function
# → http://127.0.0.1:8790/reader.html?book=論語&index=1
# 或（若装了 wrangler）： npx wrangler pages dev 网站
```

> 注：本机到 wikipedia.org 可能不通（函数会返回 `{"error":"fetch failed"}`）；部署到
> Cloudflare 后由边缘节点发起请求，通常可正常取到摘要。

## 全站检索（`search.html`）

一次搜四样：**书名 / 作者 / 分类**、**篇目标题**、**正文关键词**（定位到「书 → 篇」）、**单字/词查词**。
首页搜索框（`js/home-search.js`）**回车即到**，下拉末尾也有「🔍 全站检索」入口。

- **索引**（`_site_data/search/`，由 `文本/build_search_index.py` 生成）：
  - 目录层 `titles.json`（0.9 MB）：790 本书 + **24,753 条篇目标题** → 秒回；
  - 快照层 `snap/0..63.json`（10.9 MB）：每篇「正文前 180 字 + 尾 60 字」，前端 64 片**并行取出后扫一遍**
    （页面上有「已扫描 N/64 片」进度）；因此**篇中段的关键词可能漏检**，页面里已注明。
- **篇目下标与阅读页同序**（复用 `js/common.js` 的 `orderedSections()`）→ 结果直接 `reader.html?book=…&index=…`。
- **离线查词**（`js/dict-lookup.js`，按需取分片，不整包下载）：
  `_site_data/vocab_final.json`（本站词表）+ `_site_data/dict/{kangxi,shuowen,cedict}/<首字码点%128>.json`
  （康熙 / 说文 / CC-CEDICT，`dict_meta.json` 里声明分片数与词典清单）。
- **第三方词典只给外链**：漢典 / 中國哲學書電子化計劃 / 維基詞典 / 國學大師 / 中華典藏 —— 点开新窗口，
  结果不在本站展示（`target="_blank" rel="noopener"`）。
- **站外白名单（`js/dict-links.js`）+ 每周探活**：只有 `enabled` 的源才渲染按钮，`hidden` 的源
  **既不渲染、也不预取（无 preconnect/prefetch/dns-prefetch）、更不会发请求**。
  - 默认展示：**漢典**（`zdic.net/hans/<词>`）、**中國哲學書電子化計劃**（`ctext.org/search.pl?...`）；
  - 默认隐藏：**中文維基詞典**（境内直连白屏）→ 到「设置 → 词典外链」开「容错外链」才显示，且**永不参与自动摘要**；
    **國學大師**（未备案被阿里云拦截）、**中華典藏**（域名失效）→ 由 `deploy/dict_links_probe.js`
    **每周探活**：连续 2 次成功自动 `enabled` 展示，连续 2 次失败回到 `hidden`（状态在
    `_site_data/dict/dict_links.json`）。
  - 阅读页在线摘要只走**维基百科**（同域 `/api/dict` 代理）；查词面板底部会写明「已隐藏 N 个不可用源」。
- 缓存：`_headers` 给 `/_site_data/search/*`、`/_site_data/dict/*` 设 `Cache-Control: max-age=86400`。

## 数据更新

文本切分文件变化后，重新导出数据即可（页面无需改动）：

```bash
cd 文本
python3 export_json.py
```

## 目录结构

```
古登堡—在线阅读网站项目/
└── 网站/
    ├── index.html          首页（每日一句 + 五部分类入口）
    ├── book.html           书目（按分类分组 + 搜索）
    ├── reader.html         阅读器（上一篇/下一篇、字号、进度记忆）
    ├── search.html         检索（书目/篇目/正文 + 离线查词 + 第三方外链）
    ├── ai-settings.html    AI 设置（全局 AI 助手 API Key）
    ├── ai-guide.html       AI 新手指南
    ├── css/style.css       样式
    ├── css/search.css      检索页样式
    ├── js/
    │   ├── common.js       公共：数据加载、排序、工具函数
    │   ├── book.js         书目逻辑
    │   ├── reader.js       阅读逻辑
    │   ├── home-search.js  首页搜索框（回车 → search.html）
    │   ├── search.js       检索页逻辑（目录层 + 快照层 + 「更多词典」外链）
    │   ├── dict-links.js   站外词典白名单（默认状态 + 探活结论 + 「容错外链」开关）
    │   ├── dict-api.js     查词 API 客户端（回退链 / 缓存 / 超时，只打同域 /api/*）
    │   ├── dict-settings.js 设置页「词典外链」卡片逻辑
    │   └── dict-lookup.js  离线查词（康熙/说文/词表/CC-CEDICT 分片）
    ├── _site_data/         站点数据（单书 JSON + search/ + dict/ + vocab_final.json）
    └── 启动站点.command     一键启动脚本（macOS）
```

数据路径：`_site_data/*.json`（相对本目录；单书按需加载，检索索引在 `_site_data/search/`，词典分片在 `_site_data/dict/`）。
