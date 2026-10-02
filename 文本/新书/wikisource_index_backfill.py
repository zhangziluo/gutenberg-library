#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
wikisource_index_backfill.py — 补齐 wikisource_index.json 里缺失的页面元数据
================================================================================
索引里 `length is None` 的条目（约 300 条）是上次采集超时漏掉的；本脚本只针对
这些页面重取 `prop=info`（长度）与 `prop=links&plnamespace=102`（作者），
写回索引后调用 build_wikisource_index.py 重建 md/tsv。

特点：
  · 断点续跑：每批 JSON 落 `文本/新书/.ws_meta_cache/`（gitignore），重跑只补缺的
  · 稳态重试：curl 短超时 + 退避 + 多并发（zh.wikisource 很慢，requests 易 ReadTimeout）
  · 作者防污染：页头 navbox（如《二十四史》模板）会把整系列作者链进来 → >5 位弃用

用法：
  python3 文本/新书/wikisource_index_backfill.py              # 补 length 为空的条目
  python3 文本/新书/wikisource_index_backfill.py --all        # 连「无作者」的也重取
  python3 文本/新书/wikisource_index_backfill.py --workers 6 --limit 200
"""
import argparse
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

API = 'https://zh.wikisource.org/w/api.php'
UA = 'MyReader/1.0 (index backfill)'
BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(BASE))
INDEX = os.path.join(BASE, 'wikisource_index.json')
CACHE = os.path.join(BASE, '.ws_meta_cache')
BATCH = 25
MAX_AUTHORS = 5          # 超过视为 navbox 污染


def curl(out, params, retries=5):
    """GET 到 out；成功（有 query.pages）返回 dict，否则 None。"""
    for a in range(retries):
        subprocess.run(['curl', '-sS', '--max-time', '20', '--connect-timeout', '10',
                        '-A', UA, '-G', API] +
                       sum([['--data-urlencode', p] for p in params], []) +
                       ['--data-urlencode', 'format=json', '-o', out],
                       capture_output=True)
        try:
            d = json.load(open(out, encoding='utf-8'))
            if d.get('query', {}).get('pages'):
                return d
        except Exception:
            pass
        time.sleep(0.8 * (a + 1))
    return None


def fetch_batch(i, pages):
    """取一批的 info + links（分开请求；合并会明显变慢）。"""
    pi = os.path.join(CACHE, 'i_%04d.json' % i)
    pl = os.path.join(CACHE, 'l_%04d.json' % i)
    joined = '|'.join(pages)
    if not _cached(pi):
        curl(pi, ['action=query', 'titles=' + joined, 'prop=info'])
    if not _cached(pl):
        curl(pl, ['action=query', 'titles=' + joined, 'prop=links',
                  'plnamespace=102', 'pllimit=max'])
    return i


def _cached(path):
    try:
        d = json.load(open(path, encoding='utf-8'))
        return bool(d.get('query', {}).get('pages'))
    except Exception:
        return False


def harvest(cache_dir, n_batches, targets):
    """汇总所有批次的 info/links → {title: {length, authors, missing}}。"""
    meta = {}
    for i in range(n_batches):
        pi = os.path.join(cache_dir, 'i_%04d.json' % i)
        try:
            d = json.load(open(pi, encoding='utf-8'))
        except Exception:
            d = None
        if d:
            for pg in d.get('query', {}).get('pages', {}).values():
                t = pg.get('title')
                if not t:
                    continue
                if 'missing' in pg:
                    meta[t] = {'missing': True}
                else:
                    meta[t] = {'length': pg.get('length')}
        pl = os.path.join(cache_dir, 'l_%04d.json' % i)
        try:
            d = json.load(open(pl, encoding='utf-8'))
        except Exception:
            d = None
        if d:
            for pg in d.get('query', {}).get('pages', {}).values():
                t = pg.get('title')
                if not t:
                    continue
                auth = [l['title'].split(':', 1)[1]
                        for l in (pg.get('links') or [])
                        if l.get('title', '').startswith('Author:')]
                auth = sorted(set(auth))
                meta.setdefault(t, {})['authors'] = (
                    auth if len(auth) <= MAX_AUTHORS else [])
    return meta


def main():
    ap = argparse.ArgumentParser(description='补齐维基文库索引缺失的页面元数据')
    ap.add_argument('--all', action='store_true',
                    help='不只补 length 为空的，连「无作者」的条目也重取')
    ap.add_argument('--workers', type=int, default=6)
    ap.add_argument('--limit', type=int, default=0, help='只处理前 N 条（试跑）')
    ap.add_argument('--no-build', action='store_true',
                    help='不重建 md/tsv（只改 json）')
    args = ap.parse_args()

    if not os.path.exists(INDEX):
        sys.exit('缺少 %s，请先运行 build_wikisource_index.py' % INDEX)
    entries = json.load(open(INDEX, encoding='utf-8'))

    if args.all:
        targets = [e for e in entries if e['length'] is None or not e['authors']]
    else:
        targets = [e for e in entries if e['length'] is None]
    if args.limit:
        targets = targets[:args.limit]

    pages = sorted({e['page'] for e in targets})
    print('待补元数据页面：%d（条目 %d）' % (len(pages), len(targets)), flush=True)
    if not pages:
        print('没有需要补的，退出。')
        return

    os.makedirs(CACHE, exist_ok=True)
    batches = [pages[i:i + BATCH] for i in range(0, len(pages), BATCH)]
    print('批次：%d（每批 %d 条，%d 并发）' % (len(batches), BATCH, args.workers),
          flush=True)

    done = 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        for _ in ex.map(lambda it: fetch_batch(it[0], it[1]),
                        list(enumerate(batches))):
            done += 1
            if done % 5 == 0 or done == len(batches):
                print('  %d/%d 批完成' % (done, len(batches)), flush=True)

    meta = harvest(CACHE, len(batches), pages)
    updated_len = updated_auth = 0
    for e in entries:
        m = meta.get(e['page'])
        if not m:
            continue
        if e['length'] is None and m.get('length') is not None:
            e['length'] = m['length']
            updated_len += 1
        if not e['authors'] and m.get('authors'):
            e['authors'] = m['authors']
            updated_auth += 1

    json.dump(entries, open(INDEX, 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    print('✅ 补长度 %d 条 / 补作者 %d 条' % (updated_len, updated_auth))
    still = sum(1 for e in entries if e['length'] is None)
    print('仍缺长度：%d（多数为确实不存在的重定向/空页）' % still)

    if not args.no_build:
        print('↻ 重建 md / tsv …')
        subprocess.run([sys.executable,
                        os.path.join(BASE, 'build_wikisource_index.py'),
                        '--from-json'])


if __name__ == '__main__':
    main()
