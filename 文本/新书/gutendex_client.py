#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gutendex_client.py — Gutendex（gutendex.com）元数据客户端
========================================================
Gutendex 是 Project Gutenberg 元数据的第三方 JSON 检索服务，**只提供元数据**
（书名/作者/语言/主题/格式链接/下载量），不提供正文下载代理；
正文下载仍走 gutenberg_import.book_urls_by_id 的原 files/cache 三链接。

本模块把全部 Gutendex 调用集中在此，便于日后换自托管实例或加缓存。

对外接口：
  search_books(params: dict) -> list[dict]      # 透传查询参数，自动按 next 翻页
  get_book(gutenberg_id: str) -> dict | None    # 单书原始 book 对象
  normalize_gutendex_book(raw: dict) -> dict    # → 统一字段格式

约定：
  · 翻页请求间隔 ≥0.3s；失败重试 3 次、指数退避（0.6 → 1.2 → 2.4s）。
  · 404 / 网络失败一律返回 None 或 []，由调用方决定降级（不抛异常打断入库流程）。
"""
import json
import time
import urllib.error
import urllib.parse
import urllib.request

GUTENDEX_BASE = 'https://gutendex.com'
GUTENDEX_UA = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                             'gutenberg-library/3.0 (gutendex-client)'}
REQUEST_INTERVAL = 0.3      # 请求间隔（秒）
RETRIES = 3                 # 失败重试次数（指数退避）
RETRY_BASE_DELAY = 0.6      # 首次退避 0.6s → 1.2s → 2.4s
TIMEOUT = 30

_LAST = [0.0]


def _pace():
    """节流：保证两次网络请求间隔 ≥ REQUEST_INTERVAL 秒。"""
    wait = REQUEST_INTERVAL - (time.time() - _LAST[0])
    if wait > 0:
        time.sleep(wait)
    _LAST[0] = time.time()


def _get_json(url):
    """GET + 解析 JSON。404/解析失败/网络异常均返回 None；失败重试 3 次、指数退避。"""
    delay = RETRY_BASE_DELAY
    for attempt in range(RETRIES + 1):
        _pace()
        try:
            req = urllib.request.Request(url, headers=GUTENDEX_UA)
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                return json.loads(resp.read().decode('utf-8', 'replace'))
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None                      # 无此书：不重试
        except Exception:
            pass
        if attempt < RETRIES:
            time.sleep(delay)
            delay *= 2
    return None



def search_books(params, max_results=0, max_pages=0):
    """按查询参数检索书目，自动翻页，返回 results 列表（已拍平）。

    params 透传给 Gutendex /books：search / languages / topic / ids / sort /
    copyright / author_year_start / author_year_end / mime_type 等（page 由本函数接管）。
    默认翻页直到响应 next 为空；任何一页失败即停止（返回已取到的部分）。

    可选早停（CLI 只显示前 N 条时用，避免宽泛查询翻上千页）：
      max_results>0  取够该条数即停
      max_pages>0    最多翻该页数
    """
    out = []
    page = 1
    while True:
        query = dict(params or {})
        query['page'] = page
        url = GUTENDEX_BASE + '/books?' + urllib.parse.urlencode(query)
        data = _get_json(url)
        if not data:
            break
        out.extend(data.get('results') or [])
        if max_results and len(out) >= max_results:
            break
        if max_pages and page >= max_pages:
            break
        if not data.get('next'):
            break
        page += 1
    return out


def get_book(gutenberg_id):
    """取单本书的原始 Gutendex book 对象；无此书/不可用返回 None。"""
    gid = str(gutenberg_id).strip()
    if not gid:
        return None
    data = _get_json('%s/books/%s' % (GUTENDEX_BASE, urllib.parse.quote(gid)))
    return data if isinstance(data, dict) and data.get('id') is not None else None


def normalize_gutendex_book(raw):
    """把 Gutendex book 对象映射为统一字段格式（缺字段一律给安全默认值）。"""
    if not isinstance(raw, dict):
        return {}
    fmt = raw.get('formats') or {}
    authors = raw.get('authors') or []
    return {
        'gutenberg_id': raw.get('id'),
        'title': raw.get('title'),
        'authors': ', '.join(a.get('name', '') for a in authors
                             if isinstance(a, dict)),
        'languages': raw.get('languages', []),
        'subjects': raw.get('subjects', []),
        'bookshelves': raw.get('bookshelves', []),
        'copyright': raw.get('copyright'),
        'download_count': raw.get('download_count', 0),
        'txt_url': (fmt.get('text/plain; charset=utf-8')
                    or fmt.get('text/plain')),
        'html_url': (fmt.get('text/html; charset=utf-8')
                     or fmt.get('text/html')),
        'epub_url': fmt.get('application/epub+zip'),
    }


if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == 'search':
        kw = ' '.join(sys.argv[2:]) or 'dracula'
        rows = search_books({'search': kw})
        print('共 %d 条：' % len(rows))
        for r in rows[:20]:
            print('  %s | %s | %s | %s | %s' % (
                r.get('id'), r.get('title'),
                ', '.join(a.get('name', '') for a in (r.get('authors') or [])),
                ','.join(r.get('languages') or []), r.get('download_count', 0)))
    else:
        gid = sys.argv[1] if len(sys.argv) > 1 else '84'
        raw = get_book(gid)
        print(json.dumps(normalize_gutendex_book(raw), ensure_ascii=False, indent=2)
              if raw else '（无数据：%s）' % gid)
