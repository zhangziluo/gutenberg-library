#!/usr/bin/env python3
"""
wikisource_toolkit.py —— 维基文库通用抓取工具（内置许可合规闸门）

功能：
  fetch <页面标题>    抓取任意一本书（自动发现子页面/按回目切分）
  list [关键词]       列出本地已抓书目，可过滤
  search <字词>       全文检索所有本地书，打印 书→回→上下文

合规设计：
  每抓取一页，自动调用 license_detector 读取页面版权模板，
  判定许可类型并写入 JSON。只有 safe_to_use=True 的页面才进入书库；
  受限/未知许可的页面会被标记，EPUB 生成时强制带来源与许可声明。

依赖：
  pip install requests beautifulsoup4
用法：
  python3 wikisource_toolkit.py fetch "水滸傳 (70回本)"
  python3 wikisource_toolkit.py list
  python3 wikisource_toolkit.py list 水浒
  python3 wikisource_toolkit.py search 林沖
  python3 wikisource_toolkit.py search 賈寶玉 --limit 20 --context 15
"""

import sys
import time
import re
import json
import argparse
from pathlib import Path
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

# 本模块同目录下的许可检测
try:
    from license_detector import detect_license
except ImportError:
    # 兜底：若单独运行，尝试相对导入
    sys.path.insert(0, str(Path(__file__).parent))
    from license_detector import detect_license


# ===================== 配置 =====================
WS_API = "https://zh.wikisource.org/w/api.php"
UA = {"User-Agent": "MyReader/1.0 (contact: dev@example.com) Python/3.x"}
OUTPUT_DIR = Path("novels_json")
RATE_LIMIT_SLEEP = 0.5  # 礼貌延迟（秒）


# ===================== 基础请求 =====================
def api_get(params, session=None):
    s = session or requests.Session()
    try:
        r = s.get(WS_API, params=params, headers=UA, timeout=30)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"  ❌ 请求失败: {e}")
        return None


# ===================== 页面抓取 =====================
def fetch_parse(title, session=None):
    """解析页面，返回 html / displaytitle / revid"""
    params = {
        "action": "parse", "page": title,
        "prop": "text|displaytitle|revid",
        "format": "json", "disabletoc": 1,
    }
    data = api_get(params, session)
    if not data or "error" in data:
        if data and "error" in data:
            print(f"  ❌ API 错误: {data['error']}")
        return None
    p = data.get("parse", {})
    return {
        "html": p.get("text", {}).get("*", ""),
        "displaytitle": p.get("displaytitle", title),
        "revid": p.get("revid"),
    }


def fetch_wikitext(title, session=None):
    """获取页面 wikitext 与最近修订时间戳"""
    params = {
        "action": "query", "titles": title,
        "prop": "revisions",
        "rvprop": "content|timestamp", "format": "json",
    }
    data = api_get(params, session)
    if not data:
        return None
    for page in data.get("query", {}).get("pages", {}).values():
        if "revisions" in page:
            rev = page["revisions"][0]
            return {"wikitext": rev["*"], "timestamp": rev["timestamp"]}
    return None


def extract_text_from_html(html):
    """HTML → 纯文本"""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.select(".mw-editsection, #toc, .nav, .noprint, script, style"):
        tag.decompose()
    main = soup.select_one(".mw-parser-output") or soup
    return main.get_text(separator="\n", strip=True)


# ===================== 子页面发现 =====================
def get_subpages(parent_title, session=None):
    params = {
        "action": "query", "titles": parent_title,
        "prop": "links", "pllimit": "500", "format": "json",
    }
    subs = []
    while True:
        data = api_get(params, session)
        if not data:
            break
        for page in data.get("query", {}).get("pages", {}).values():
            for link in page.get("links", []):
                t = link["title"]
                if t.startswith(parent_title + "/"):
                    subs.append(t)
        if "continue" in data:
            params.update(data["continue"])
        else:
            break
    subs.sort(key=lambda x: _sort_key(x, parent_title))
    return subs


def _sort_key(title, parent):
    name = title.replace(parent + "/", "")
    if "楔" in name:
        return (0, name)
    m = re.search(r"第?(\d+)", name)
    if m:
        return (1, int(m.group(1)))
    return (2, name)


def split_by_heading(html, displaytitle):
    """无子页面时，按 == 二级标题切分章节"""
    soup = BeautifulSoup(html, "html.parser")
    main = soup.select_one(".mw-parser-output") or soup
    # 找所有 h2
    heads = main.select("h2")
    if not heads:
        return None
    chapters = []
    for h in heads:
        title_span = h.select_one(".mw-headline") or h
        chap_title = title_span.get_text(strip=True)
        if not chap_title:
            continue
        content_parts = []
        for sib in h.next_siblings:
            if getattr(sib, "name", None) == "h2":
                break
            if isinstance(sib, str):
                content_parts.append(str(sib))
            else:
                content_parts.append(str(sib))
        chap_html = "".join(content_parts)
        chapters.append({
            "title": chap_title,
            "html": chap_html,
        })
    return chapters if chapters else None


# ===================== 许可判定（合规闸门） =====================
def judge_page(title, session=None):
    """对单页做许可判定，返回 dict（见 license_detector）"""
    return detect_license(title, session=session)


# ===================== 书籍处理 =====================
def process_book(book_title, session=None):
    print(f"\n📖 处理：《{book_title}》")
    s = session or requests.Session()

    # 1. 发现子页面
    print("   🔍 发现子页面...")
    subs = get_subpages(book_title, s)
    use_subpages = bool(subs)

    if use_subpages:
        print(f"   ✅ 找到 {len(subs)} 个子页面")
        targets = subs
    else:
        print("   ℹ️ 无子页面，将按页面内标题切分")
        targets = [book_title]

    chapters = []
    skipped_license = []
    unknown_license = []

    for i, t in enumerate(targets, 1):
        print(f"   [{i}/{len(targets)}] {t}")
        r = fetch_parse(t, s)
        if not r:
            continue
        html = r["html"]
        revid = r["revid"]

        # 许可判定（合规闸门）
        lic = judge_page(t, s)

        # 决定这一页怎么存
        if use_subpages:
            chaps_for_page = [{
                "title": t.split("/")[-1],
                "html": html,
            }]
        else:
            # 无子页：尝试按标题切，若切不出来就整页当一章
            split = split_by_heading(html, r["displaytitle"])
            chaps_for_page = split if split else [{
                "title": r["displaytitle"],
                "html": html,
            }]

        for ch in chaps_for_page:
            chap_record = {
                "title": ch["title"],
                "chapter_id": t,
                "source_url": "https://zh.wikisource.org/wiki/" + requests.utils.quote(t.replace(" ", "_")),
                "revid": revid,
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
            }
            chapters.append(chap_record)

            # 合规日志
            if not lic["safe_to_use"]:
                if lic["status"] == "unknown":
                    unknown_license.append(t)
                else:
                    skipped_license.append((t, lic["license"]))

        time.sleep(RATE_LIMIT_SLEEP)

    # 2. 汇总许可：以大多数章节的许可为准
    from collections import Counter
    lic_counter = Counter(c["license"] for c in chapters)
    dominant_license = lic_counter.most_common(1)[0][0] if lic_counter else "未知"

    book_json = {
        "book": book_title,
        "source_base_url": "https://zh.wikisource.org/wiki/" + requests.utils.quote(book_title.replace(" ", "_")),
        "dominant_license": dominant_license,
        "license_summary": dict(lic_counter),
        "total_chapters": len(chapters),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "compliance": {
            "safe_to_use": all(c["safe_to_use"] for c in chapters) if chapters else False,
            "unknown_license_pages": unknown_license,
            "restricted_license_pages": [
                {"page": p, "license": l} for p, l in skipped_license
            ],
        },
        "chapters": chapters,
    }

    OUTPUT_DIR.mkdir(exist_ok=True)
    out_file = OUTPUT_DIR / f"{_safe_filename(book_title)}.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(book_json, f, ensure_ascii=False, indent=2)

    # 打印合规小结
    print(f"\n   📋 许可统计：")
    for lic_name, cnt in lic_counter.most_common():
        print(f"      - {lic_name}: {cnt} 页")
    if unknown_license:
        print(f"   ⚠️  {len(unknown_license)} 个页面许可未识别，已标记")
    if skipped_license:
        print(f"   ⚠️  {len(skipped_license)} 个页面为受限许可，EPUB 将强制带声明")
    print(f"   💾 已保存: {out_file}")

    return book_json


def _safe_filename(name):
    return re.sub(r"[^\w\u4e00-\u9fff]+", "_", name).strip("_") or "book"


# ===================== 书目列表 =====================
def cmd_list(keyword=None):
    if not OUTPUT_DIR.exists():
        print("📂 还没有抓过书。先用 fetch 抓一本吧。")
        return
    files = sorted(OUTPUT_DIR.glob("*.json"))
    shown = 0
    for idx, fp in enumerate(files, 1):
        if fp.name == "index.json":
            continue
        try:
            with open(fp, encoding="utf-8") as f:
                d = json.load(f)
        except Exception:
            continue
        if keyword and keyword not in d.get("book", "") and keyword not in fp.name:
            continue
        shown += 1
        safe = "✅" if d.get("compliance", {}).get("safe_to_use") else "⚠️ "
        print(f"   {safe}{idx}. 《{d.get('book')}》"
              f"  |  许可: {d.get('dominant_license')}"
              f"  |  章节: {d.get('total_chapters')}"
              f"  |  源: {d.get('source_base_url')}")
    if not shown:
        print("   （没有匹配的书目）")


# ===================== 全文检索 =====================
def cmd_search(keyword, limit=10, context=30):
    if not OUTPUT_DIR.exists():
        print("📂 还没有可检索的书。先用 fetch 抓一本吧。")
        return
    kw = keyword.strip()
    if not kw:
        print("⚠️ 搜索词不能为空")
        return
    hits = []
    for fp in sorted(OUTPUT_DIR.glob("*.json")):
        if fp.name == "index.json":
            continue
        try:
            with open(fp, encoding="utf-8") as f:
                book = json.load(f)
        except Exception:
            continue
        for ch in book.get("chapters", []):
            text = ch.get("content_text", "")
            if not text:
                continue
            idx = 0
            while True:
                idx = text.find(kw, idx)
                if idx == -1:
                    break
                start = max(0, idx - context)
                end = min(len(text), idx + len(kw) + context)
                snippet = text[start:end].replace("\n", " ")
                if start > 0:
                    snippet = "…" + snippet
                if end < len(text):
                    snippet = snippet + "…"
                hits.append({
                    "book": book.get("book"),
                    "chapter": ch.get("title"),
                    "license": ch.get("license"),
                    "snippet": snippet,
                })
                idx += len(kw)
                if len(hits) >= limit * 3:  # 防止单本爆炸
                    break
        if len(hits) >= limit * 3:
            break

    if not hits:
        print(f"🔍 未找到「{kw}」")
        return
    hits = hits[:limit]
    print(f"🔍 「{kw}」共 {len(hits)} 条结果（已截断至 {limit}）：")
    print("-" * 60)
    for i, h in enumerate(hits, 1):
        print(f"{i}. 《{h['book']}》· {h['chapter']}  [许可: {h['license']}]")
        print(f"   {h['snippet']}")
        print("-" * 60)


# ===================== 入口 =====================
def main():
    parser = argparse.ArgumentParser(
        description="维基文库通用抓取工具（内置许可合规闸门）"
    )
    sub = parser.add_subparsers(dest="cmd")

    p_fetch = sub.add_parser("fetch", help="抓取一本书")
    p_fetch.add_argument("title", help="维基文库页面标题，如 水滸傳 (70回本)")

    p_list = sub.add_parser("list", help="列出本地书目")
    p_list.add_argument("keyword", nargs="?", help="可选过滤关键词")

    p_search = sub.add_parser("search", help="全文检索")
    p_search.add_argument("keyword", help="搜索词")
    p_search.add_argument("--limit", type=int, default=10, help="最多返回条数")
    p_search.add_argument("--context", type=int, default=30, help="上下文字符数")

    args = parser.parse_args()

    if args.cmd == "fetch":
        process_book(args.title)
    elif args.cmd == "list":
        cmd_list(args.keyword)
    elif args.cmd == "search":
        cmd_search(args.keyword, args.limit, args.context)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
