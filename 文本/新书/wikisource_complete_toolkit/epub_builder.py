#!/usr/bin/env python3
"""
epub_builder.py —— EPUB 生成模块（合规署名页全自动）

支持两种输入：
  1) 从已有 JSON 构建（默认，推荐）
     python3 epub_builder.py build --json novels_json/水滸傳_(70回本).json

  2) 直接从维基文库在线抓取并构建（跳过先存 JSON）
     python3 epub_builder.py build --online "水滸傳 (70回本)"

  3) 列出可构建的书
     python3 epub_builder.py list

  4) 查看某本书的许可概况
     python3 epub_builder.py info --json novels_json/水滸傳_(70回本).json

合规行为：
  - 每个来源页的 URL + revid + 许可标签，自动写进「关于本电子书」页
  - 按章节的 license_status 分组：公有领域 / 自由许可 / 受限 / 未识别
  - CC BY-SA / CC BY / GFDL 类页面自动带完整许可声明
  - 含现代编辑贡献的页面，自动追加「衍生文本以相同许可发布」声明
  - 生成标准 EPUB 3（含 nav / ncx / 封面 / 样式表）

依赖：
  pip install requests beautifulsoup4 ebooklib
"""

import sys
import re
import json
import argparse
from pathlib import Path
from datetime import datetime, timezone
from collections import Counter, defaultdict

try:
    from ebooklib import epub
except ImportError:
    print("❌ 缺少 ebooklib，请运行：pip install ebooklib")
    sys.exit(1)

try:
    from license_detector import detect_license
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent))
    from license_detector import detect_license

from wikisource_toolkit import (  # noqa: E402
    OUTPUT_DIR, fetch_parse, get_subpages, split_by_heading,
    extract_text_from_html, _sort_key, _safe_filename, UA, WS_API,
    judge_page, api_get,
)


# ===================== 清洗 =====================
def clean_html(raw_html):
    """去掉维基编辑痕迹，保留正文结构"""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(raw_html, "html.parser")
    for tag in soup.select(
        ".mw-editsection, #toc, .nav, .noprint, .toc, .ws-header, "
        "script, style, .mw-cite-backlink"
    ):
        tag.decompose()
    main = soup.select_one(".mw-parser-output") or soup
    # 去掉多余空标签
    for t in main.find_all():
        if not t.get_text(strip=True) and not t.find(["img", "br", "hr"]):
            t.decompose()
    return str(main)


# ===================== 从 JSON 加载 =====================
def load_from_json(json_path):
    with open(json_path, encoding="utf-8") as f:
        return json.load(f)


# ===================== 在线抓取构建 =====================
def fetch_online(title, session=None):
    import requests
    s = session or requests.Session()
    subs = get_subpages(title, s)
    use_sub = bool(subs)
    targets = subs if use_sub else [title]
    chapters = []
    for i, t in enumerate(targets, 1):
        print(f"   [{i}/{len(targets)}] {t}")
        r = fetch_parse(t, s)
        if not r:
            continue
        lic = judge_page(t, s, parent_title=title)
        if use_sub:
            items = [{"title": t.split("/")[-1], "html": r["html"]}]
        else:
            sp = split_by_heading(r["html"], r["displaytitle"])
            items = sp if sp else [{"title": r["displaytitle"], "html": r["html"]}]
        for ch in items:
            chapters.append({
                "title": ch["title"],
                "chapter_id": t,
                "source_url": "https://zh.wikisource.org/wiki/" + requests.utils.quote(t.replace(" ", "_")),
                "revid": r["revid"],
                "license": lic["license"],
                "license_status": lic["status"],
                "share_alike": lic["share_alike"],
                "attribution_required": lic["attribution_required"],
                "safe_to_use": lic["safe_to_use"],
                "license_note": lic["note"],
                "license_warnings": lic["warnings"],
                "content_html": ch["html"],
                "content_text": extract_text_from_html(ch["html"]),
                "fetched_at": datetime.now(timezone.utc).isoformat(),
            })
    from collections import Counter
    c = Counter(x["license"] for x in chapters)
    dom = c.most_common(1)[0][0] if c else "未知"
    return {
        "book": title,
        "source": "维基文库",
        "source_base_url": "https://zh.wikisource.org/wiki/" + requests.utils.quote(title.replace(" ", "_")),
        "dominant_license": dom,
        "license_summary": dict(c),
        "total_chapters": len(chapters),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "compliance": {
            "safe_to_use": all(x["safe_to_use"] for x in chapters) if chapters else False,
            "unknown_license_pages": [x["chapter_id"] for x in chapters if x["license_status"] == "unknown"],
            "restricted_license_pages": [{"page": x["chapter_id"], "license": x["license"]}
                                         for x in chapters if not x["safe_to_use"] and x["license_status"] != "unknown"],
        },
        "chapters": chapters,
    }


# ===================== 许可声明文案生成 =====================
LICENSE_FULL_TEXT = {
    "cc-by-sa-4.0": (
        "知识共享 署名-相同方式共享 4.0 国际许可协议（CC BY-SA 4.0）。"
        "详情见 https://creativecommons.org/licenses/by-sa/4.0/legalcode.zh"
    ),
    "cc-by-sa-3.0": (
        "知识共享 署名-相同方式共享 3.0 未本地化版本（CC BY-SA 3.0）。"
        "详情见 https://creativecommons.org/licenses/by-sa/3.0/legalcode"
    ),
    "cc-by-sa-2.5": (
        "知识共享 署名-相同方式共享 2.5 通用版（CC BY-SA 2.5）。"
    ),
    "cc-by-sa-2.0": (
        "知识共享 署名-相同方式共享 2.0 通用版（CC BY-SA 2.0）。"
    ),
    "cc-by-4.0": (
        "知识共享 署名 4.0 国际许可协议（CC BY 4.0）。"
        "详情见 https://creativecommons.org/licenses/by/4.0/legalcode.zh"
    ),
    "cc-by-3.0": "知识共享 署名 3.0 未本地化版本（CC BY 3.0）。",
    "cc-by-2.5": "知识共享 署名 2.5 通用版（CC BY 2.5）。",
    "cc-by-2.0": "知识共享 署名 2.0 通用版（CC BY 2.0）。",
    "gfdl": "GNU 自由文档许可证（GNU Free Documentation License）。详情见 https://www.gnu.org/licenses/fdl-1.3.zh-cn.html",
    "gpl": "GNU 通用公共许可证（GPL）。",
    "lgpl": "GNU 宽通用公共许可证（LGPL）。",
}


def normalize_license_key(lic_name):
    """把判定出的许可名归一化为 key"""
    n = lic_name.lower()
    for v in ("4.0", "3.0", "2.5", "2.0"):
        if v in n:
            if "by-sa" in n:
                return f"cc-by-sa-{v}"
            if "by" in n:
                return f"cc-by-{v}"
    if "gfdl" in n:
        return "gfdl"
    if "gpl" in n:
        return "lgpl" if "lgpl" in n else "gpl"
    return None


def build_source_table(chapters):
    """生成「逐页来源」表格 HTML"""
    rows = []
    for ch in chapters:
        short = ch["chapter_id"].split("/")[-1]
        rows.append(
            f"<tr><td>{short}</td>"
            f"<td><a href=\"{ch['source_url']}\">{ch['chapter_id']}</a></td>"
            f"<td>{ch['revid'] or '—'}</td>"
            f"<td>{ch['license']}</td></tr>"
        )
    return f"""
    <h2>逐章来源与许可</h2>
    <table border=\"1\" cellpadding=\"6\" cellspacing=\"0\">
      <tr><th>章节</th><th>维基文库页面</th><th>版本号</th><th>许可</th></tr>
      {''.join(rows)}
    </table>
    """


def build_about_page(book_data):
    """生成「关于本电子书」XHTML 内容"""
    book = book_data.get("book", "未知书名")
    base_url = book_data.get("source_base_url", "")
    dom = book_data.get("dominant_license", "未知")
    chapters = book_data.get("chapters", [])
    comp = book_data.get("compliance", {})

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # 按许可分组统计
    lic_counter = Counter(c["license"] for c in chapters)
    lic_rows = "".join(
        f"<li>{name}：{cnt} 页</li>" for name, cnt in lic_counter.most_common()
    )

    # 自由许可列表（用于 SA 声明）
    free_licenses = []
    for c in chapters:
        key = normalize_license_key(c["license"])
        if key and key not in free_licenses:
            free_licenses.append(key)
    free_licenses = sorted(set(free_licenses))

    # 许可全文声明
    lic_blocks = []
    for key in free_licenses:
        text = LICENSE_FULL_TEXT.get(key)
        if text:
            lic_blocks.append(f"<li>{text}</li>")
    if lic_blocks:
        lic_full = f"<h2>适用的自由许可</h2><ul>{''.join(lic_blocks)}</ul>"
    else:
        lic_full = ""

    # 衍生声明
    sa_list = [c for c in chapters if c.get("share_alike")]
    if sa_list:
        sa_decl = (
            "<p><strong>衍生文本许可声明：</strong>本电子书中属于公有领域的原文与批注不作额外限制；"
            "本阅读器对其所做的校对、分段、排版与导言等新增独创性表达，"
            "依据其所基于页面的自由许可（见上）以相同许可发布。</p>"
        )
    else:
        sa_decl = (
            "<p><strong>衍生文本许可声明：</strong>本电子书原文及批注均属公有领域，"
            "本阅读器对其所做的校对、分段与排版亦仅供自由使用，无任何额外限制。</p>"
        )

    # 风险提示
    warnings_html = ""
    all_warnings = []
    for c in chapters:
        all_warnings.extend(c.get("license_warnings", []))
    if all_warnings:
        items = "".join(f"<li>{w}</li>" for w in dict.fromkeys(all_warnings))
        warnings_html = f"<h2>版权注意事项</h2><ul>{items}</ul>"

    # 未识别/受限页提示
    issues = []
    for p in comp.get("unknown_license_pages", []):
        issues.append(f"<li>许可未识别：{p}</li>")
    for item in comp.get("restricted_license_pages", []):
        issues.append(f"<li>受限许可（{item['license']}）：{item['page']}</li>")
    issues_html = ""
    if issues:
        issues_html = (
            f"<h2>合规提示</h2><p>以下页面许可未完全自动确认，使用时应留意：</p>"
            f"<ul>{''.join(issues)}</ul>"
        )

    return f"""<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
<head><title>关于本电子书</title></head>
<body>
  <h1>关于本电子书</h1>
  <p>本书《{book}》文本整理自 <a href="{base_url}">中文维基文库</a>（Wikisource）。</p>
  <p>生成时间：{now}</p>

  <h2>版权与许可概况</h2>
  <p>主要许可：<strong>{dom}</strong></p>
  <p>各页许可分布：</p>
  <ul>{lic_rows}</ul>

  {lic_full}

  {sa_decl}

  <h2>署名与来源</h2>
  <p>本书各章节内容均来自维基文库的对应页面。原作作者署名及底本出处见各章节来源。
  使用与再分发时，请保留本页所列的来源链接与许可声明。</p>

  {build_source_table(chapters)}

  {warnings_html}
  {issues_html}
</body>
</html>"""


# ===================== 构建 EPUB =====================
CSS = """
body { font-family: "Songti SC", "SimSun", "Noto Serif CJK SC", serif;
       line-height: 1.9; font-size: 1.05em; margin: 1em; text-align: justify; }
h1 { text-align: center; font-size: 1.6em; margin: 1.5em 0 1em; }
h2 { font-size: 1.25em; margin-top: 1.5em; border-bottom: 1px solid #999; padding-bottom: .3em; }
p { margin: 0.8em 0; text-indent: 2em; }
.annotation { color: #555; font-style: italic; }
table { border-collapse: collapse; width: 100%; font-size: 0.85em; }
th, td { border: 1px solid #888; padding: 4px 6px; text-align: left; }
a { color: #0645AD; text-decoration: none; }
"""


def build_epub(book_data, out_path):
    book = epub.EpubBook()
    title = book_data.get("book", "未知书名")
    book.set_identifier("ws-" + _safe_filename(title) + "-" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S"))
    book.set_title(title)
    book.set_language("zh")

    # 作者：尽力从书名推断
    author_guess = _guess_author(title)
    if author_guess:
        book.add_author(author_guess)

    # 关于页（合规核心）
    about = epub.EpubHtml(title="关于本电子书", file_name="about.xhtml", lang="zh")
    about.content = build_about_page(book_data)
    book.add_item(about)

    # 章节
    spine_items = [about]
    toc = [epub.Link("about.xhtml", "关于本电子书", "about")]
    chapters = book_data.get("chapters", [])

    for i, ch in enumerate(chapters, 1):
        c = epub.EpubHtml(
            title=ch["title"],
            file_name=f"chap_{i:03d}.xhtml",
            lang="zh",
        )
        body = clean_html(ch.get("content_html", ""))
        # 在章首标注许可（仅自由许可页，帮助读者识别）
        if ch.get("attribution_required") or ch.get("share_alike"):
            notice = (
                f'<p style="font-size:.8em;color:#666;text-indent:0;">'
                f'（本节以 {ch["license"]} 提供，来源：'
                f'<a href="{ch["source_url"]}">{ch["chapter_id"]}</a>）</p>'
            )
        else:
            notice = (
                f'<p style="font-size:.8em;color:#999;text-indent:0;">'
                f'（本节来源：<a href="{ch["source_url"]}">{ch["chapter_id"]}</a>）</p>'
            )
        c.content = (
            f"<html xmlns=\"http://www.w3.org/1999/xhtml\">"
            f"<head><title>{ch['title']}</title></head>"
            f"<body><h1>{ch['title']}</h1>{notice}{body}</body></html>"
        )
        book.add_item(c)
        spine_items.append(c)
        toc.append(c)

    book.toc = tuple(toc)
    book.spine = spine_items
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())

    # 样式表
    nav_css = epub.EpubItem(
        uid="nav-css", file_name="style/main.css",
        media_type="text/css", content=CSS
    )
    book.add_item(nav_css)

    epub.write_epub(out_path, book, {})
    return out_path


def _guess_author(title):
    mapping = {
        "水浒": "施耐庵（原著）；金圣叹（批评）",
        "三国": "罗贯中",
        "西游": "吴承恩",
        "红楼": "曹雪芹",
        "儒林": "吴敬梓",
        "史记": "司马迁",
    }
    for k, v in mapping.items():
        if k in title:
            return v
    return None


# ===================== CLI =====================
def cmd_build(args):
    if args.online:
        print(f"🌐 在线抓取：《{args.online}》")
        book_data = fetch_online(args.online)
    elif args.json:
        print(f"📄 读取 JSON：{args.json}")
        book_data = load_from_json(args.json)
    else:
        print("❌ 必须指定 --json 或 --online")
        sys.exit(1)

    if not book_data.get("chapters"):
        print("❌ 没有章节内容，无法生成 EPUB")
        sys.exit(1)

    comp = book_data.get("compliance", {})
    if not comp.get("safe_to_use") and not args.force:
        print("⚠️  本书存在许可未确认/受限的页面：")
        for p in comp.get("unknown_license_pages", []):
            print(f"    未识别：{p}")
        for item in comp.get("restricted_license_pages", []):
            print(f"    受限（{item['license']}）：{item['page']}")
        print("    如需强制生成，请加 --force")
        sys.exit(1)

    out = Path(args.output) if args.output else Path("epubs") / f"{_safe_filename(book_data.get('book','book'))}.epub"
    out.parent.mkdir(parents=True, exist_ok=True)
    build_epub(book_data, str(out))
    print(f"✅ EPUB 已生成：{out}")
    print(f"   章节数：{book_data.get('total_chapters')}")
    print(f"   主要许可：{book_data.get('dominant_license')}")


def cmd_list(args):
    if not OUTPUT_DIR.exists():
        print("📂 没有已抓取的书籍")
        return
    for fp in sorted(OUTPUT_DIR.glob("*.json")):
        if fp.name == "index.json":
            continue
        try:
            with open(fp, encoding="utf-8") as f:
                d = json.load(f)
        except Exception:
            continue
        icon = "✅" if d.get("compliance", {}).get("safe_to_use") else "⚠️ "
        print(f"  {icon}{d.get('book')}  |  {d.get('dominant_license')}  |  {d.get('total_chapters')} 章")


def cmd_info(args):
    if not args.json:
        print("❌ 需指定 --json")
        sys.exit(1)
    d = load_from_json(args.json)
    print(f"书名：{d.get('book')}")
    print(f"源页：{d.get('source_base_url')}")
    print(f"主要许可：{d.get('dominant_license')}")
    print(f"章节数：{d.get('total_chapters')}")
    print(f"安全可用：{d.get('compliance', {}).get('safe_to_use')}")
    print("许可分布：")
    for name, cnt in d.get("license_summary", {}).items():
        print(f"   - {name}: {cnt}")


def main():
    parser = argparse.ArgumentParser(description="EPUB 生成模块（内置合规署名页）")
    sub = parser.add_subparsers(dest="cmd")

    p_build = sub.add_parser("build", help="生成 EPUB")
    g = p_build.add_mutually_exclusive_group(required=True)
    g.add_argument("--json", help="从已有 JSON 构建")
    g.add_argument("--online", help="直接从维基文库抓取并构建")
    p_build.add_argument("-o", "--output", help="输出 EPUB 路径")
    p_build.add_argument("--force", action="store_true", help="即使存在未确认许可也强制生成")

    sub.add_parser("list", help="列出可构建的书")

    p_info = sub.add_parser("info", help="查看某本书许可概况")
    p_info.add_argument("--json", required=True)

    args = parser.parse_args()
    if args.cmd == "build":
        cmd_build(args)
    elif args.cmd == "list":
        cmd_list(args)
    elif args.cmd == "info":
        cmd_info(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
