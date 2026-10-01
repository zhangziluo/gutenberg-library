# 维基文库阅读器书源工具（内置许可合规闸门）

## 一句话说明

抓取维基文库任意公版书 → 自动判定每一页的版权许可 → 只放行安全的进入书库 → 生成结构化 JSON，阅读器可直接渲染。

---

## 安装与准备

```bash
# 1. 进项目目录，建虚拟环境（推荐）
python3 -m venv venv
source venv/bin/activate

# 2. 装依赖
pip install requests beautifulsoup4
```

> 只需这两个依赖。`beautifulsoup4` 用内置的 `html.parser`，**不需要 lxml**。

---

## 三个命令

### 1. 抓取一本书

```bash
python3 wikisource_toolkit.py fetch "水滸傳 (70回本)"
python3 wikisource_toolkit.py fetch "儒林外史"
python3 wikisource_toolkit.py fetch "史記"
```

过程会自动：
- 发现子页面（回目/卷/章），没有子页就按页面内 `== 标题 ==` 切分
- **每抓一页就判定一次许可**，输出许可统计
- 把许可标签、来源 URL、revid 全部写进 JSON

输出文件：`novels_json/<书名>.json`

### 2. 列出本地书目

```bash
python3 wikisource_toolkit.py list              # 全部
python3 wikisource_toolkit.py list 水浒           # 按关键词过滤
```

每条显示：书名 | 主要许可 | 章节数 | 来源链接，前面有 `✅` 或 `⚠️` 标识是否全部章节安全。

### 3. 全文检索

```bash
python3 wikisource_toolkit.py search 林沖
python3 wikisource_toolkit.py search 賈寶玉 --limit 20 --context 15
```

返回：`哪本书 → 哪一回 → 上下文片段`，每条带该页许可标签。

---

## 许可判定是怎么工作的

工具调用 MediaWiki API 的 `prop=templates`，读取每个页面 transclude 的版权模板，
对照维基文库标准的版权标记命名（`{{PD-old}}`、`{{CC-by-sa}}`、`{{GFDL}}` 等），
输出结构化判定结果。

判定结果字段（`chapters[*]` 里每条都有）：

| 字段 | 含义 |
|------|------|
| `license` | 判定出的许可名称，如「公有领域」「CC BY-SA 4.0」 |
| `license_status` | `pd` / `free` / `restricted` / `unknown` |
| `safe_to_use` | 本页是否可安全纳入内置书源 |
| `attribution_required` | 再分发是否需署名 |
| `share_alike` | 是否要求衍生作品同许可 |
| `license_note` | 给阅读器/用户的合规说明文案 |
| `license_warnings` | 风险提示（如 PD-old-70 须注意美国版权） |

书级汇总在 `compliance` 字段：

```json
"compliance": {
  "safe_to_use": true,
  "unknown_license_pages": [],
  "restricted_license_pages": []
}
```

---

## 判定规则速查

| 页面版权模板 | 判定 | 可否内置 | 义务 |
|------|------|:---:|------|
| `PD-old` / `PD-old-70` / `PD-old-50` 等 | 公有领域 | ✅ | 保留作者署名、尊重完整权（建议仍注底本出处） |
| `CC-by-sa-*` | CC BY-SA | ✅ | 署名来源 + 标许可 + 衍生文本同 SA |
| `CC-by-*` | CC BY | ✅ | 署名来源 + 标许可 |
| `GFDL` | GFDL | ✅ | 署名 + 许可声明（可能与 PD 双许可叠加） |
| `CopyrightedFreeUse` | 有条件 | ⚠️ | 须人工核实附加条件 |
| `Fairuse` | 合理使用 | ❌ | 不适合批量内置 |
| `版权标志`（未确认） | 未知 | ❌ | 跳过，勿用 |
| 无模板 / 未识别 | 未知 | ❌ | 建议换明确公版版本 |

---

## 输出 JSON 结构

```json
{
  "book": "水滸傳 (70回本)",
  "source_base_url": "https://zh.wikisource.org/wiki/水滸傳_(70回本)",
  "dominant_license": "公有领域（Public Domain）",
  "license_summary": { "公有领域（Public Domain）": 71 },
  "total_chapters": 71,
  "fetched_at": "2026-10-01T14:30:00+00:00",
  "compliance": {
    "safe_to_use": true,
    "unknown_license_pages": [],
    "restricted_license_pages": []
  },
  "chapters": [
    {
      "title": "楔子",
      "chapter_id": "水滸傳 (70回本)/楔子",
      "source_url": "https://zh.wikisource.org/wiki/水滸傳_(70回本)/楔子",
      "revid": 12345678,
      "license": "公有领域（Public Domain）",
      "license_status": "pd",
      "safe_to_use": true,
      "attribution_required": false,
      "share_alike": false,
      "license_note": "原文及批注属公有领域...",
      "license_warnings": [],
      "content_html": "<div class=\"mw-parser-output\">...",
      "content_text": "楔子\n\n張天師祈禳瘟疫...",
      "fetched_at": "2026-10-01T14:30:01+00:00"
    }
  ]
}
```

---

## 阅读器集成建议

1. **白名单机制**：只抓已确认公版的白名单书目，不做开放任意抓取。
2. **来源声明自动化**：每回/每页底部读 `source_url` + `license` + `license_note` 渲染，不用手写。
3. **EPUB 生成**：每本书自带「关于本电子书」页，列各页来源 URL + revid + 许可。
4. **SA 义务的边界**：只对**你新增的独创性表达**（校对、排版、导言）按 CC BY-SA 发布，不必开源整个 App。
5. **不要抓现代校注本**：现代人的校勘、注释、选编可能仍受保护；同名书换公版底本更稳。

---

## 文件说明

| 文件 | 作用 |
|------|------|
| `wikisource_toolkit.py` | 主工具（fetch / list / search） |
| `license_detector.py` | 许可检测模块，可被独立调用或自检 |
| `test_license_offline.py` | 离线验证检测逻辑（无需联网） |

自检许可模块：

```bash
python3 license_detector.py "水滸傳 (70回本)/楔子"
```

离线验证逻辑（沙盒/无网环境也能跑）：

```bash
python3 test_license_offline.py
```

---

## EPUB 生成模块（epub_builder.py）

把 JSON（或直接在线抓）变成合规的 EPUB 电子书，自动写对「关于本电子书」署名页。

### 额外依赖

```bash
pip install ebooklib
```

### 用法

```bash
# 1) 从已有 JSON 构建（推荐）
python3 epub_builder.py build --json novels_json/水滸傳_水浒传（金圣叹七十回本）.json

# 2) 直接在线抓取并构建（跳过存 JSON）
python3 epub_builder.py build --online "水滸傳 (70回本)"

# 3) 指定输出路径
python3 epub_builder.py build --json <file> -o ~/Desktop/水浒传.epub

# 4) 即使有未确认许可也强制生成
python3 epub_builder.py build --json <file> --force

# 5) 列出可构建的书
python3 epub_builder.py list

# 6) 查看某本书许可概况
python3 epub_builder.py info --json <file>
```

### 生成的 EPUB 里有什么

```
EPUB/
├── content.opf        # 标准 OPF，含书名/作者/语言
├── about.xhtml        # 关于本电子书（合规核心页）
├── chap_001.xhtml     # 各回正文，章首带来源/许可标记
├── chap_002.xhtml
├── ...
├── nav.xhtml          # EPUB3 导航
├── toc.ncx            # EPUB2 兼容目录
└── style/main.css     # 中文字体排版样式
```

### 「关于本电子书」页自动包含

- **版权与许可概况**：主要许可 + 各页许可分布统计
- **适用的自由许可全文**：命中 CC BY-SA / CC BY / GFDL 时自动列出对应条款链接
- **衍生文本许可声明**：说明本阅读器新增的校对/排版按何许可发布
- **逐章来源与许可表格**：章节 / 维基文库页面 / 版本号(revid) / 许可，一页一行
- **版权注意事项**：PD-old-70 的美国版权提示、未确认页清单、受限页清单

### 章首自动标记

- 公有领域页：灰色小字「本节来源：维基文库页面链接」
- 自由许可页（CC BY-SA 等）：稍深色的「本节以 XX 许可提供，来源：链接」
- 读者打开任意一章，立刻能看到这章的底本出处

### 合规拦截

- 书内存在 `unknown` 或 `restricted` 许可页时，默认**拒绝生成**并列出风险清单
- 加 `--force` 可强制生成（此时「关于」页会如实列出所有未确认/受限页，不隐瞒）
- 这样保证「一键生成」不会悄悄把高风险文本打包进书库
