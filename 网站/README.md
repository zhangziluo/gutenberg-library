# 一堆古书 · 在线阅读网站

古登堡计划（Project Gutenberg）繁体中文古籍的在线阅读站点。
数据由 `文本/export_json.py` 生成到 `文本/_site_data/`，本站点通过浏览器读取展示。

## 页面结构

| 页面 | 地址 | 说明 |
|------|------|------|
| 首页 | `index.html` | 每日一句、经史子集分类入口、今日一卦 |
| 书目 | `book.html?book=史記` | 按分类分组的篇目列表，支持搜索 |
| 阅读 | `reader.html?book=史記&index=3` | 正文阅读，上一篇/下一篇、字号调节、进度记忆 |

## 如何运行

站点需要本地 HTTP 服务器（浏览器禁止 `file://` 直接加载 JSON）：

**方式一（推荐，macOS）**：双击 `启动站点.command`，自动启动并打开浏览器。

**方式二（终端）**：在 **项目根目录**（即本文件夹的上一级）运行：

```bash
python3 -m http.server 8000
```

然后访问：http://localhost:8000/网站/index.html

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
    ├── ai-settings.html    AI 设置（全局 AI 助手 API Key）
    ├── ai-guide.html       AI 新手指南
    ├── css/style.css       样式
    ├── js/
    │   ├── common.js       公共：数据加载、排序、工具函数
    │   ├── book.js         书目逻辑
    │   └── reader.js       阅读逻辑
    └── 启动站点.command     一键启动脚本（macOS）
```

数据路径：`../文本/_site_data/*.json`（相对本目录）。
