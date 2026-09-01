#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
古登堡新书下载器（抓取规范强制约束）
  - 每本之间间隔 ≥ 5 秒，顺序下载，不并行
  - 已下载过的书不重复抓取
  - 下载失败自动退避（5s/10s/20s），每本总重试不超过 3 次
  - 首选 files/ 链接，404 时切换 cache/epub 备用链接
输出原始文本到 文本/新书/raw/{书名}.txt（保留原始字节，编码由后续解析器探测）
"""
import os
import sys
import time
import urllib.request
import urllib.error

BASE = os.path.dirname(os.path.abspath(__file__))
RAW_DIR = os.path.join(BASE, 'raw')
os.makedirs(RAW_DIR, exist_ok=True)

# 每本：id / 书名 / 首选+备用链接
BOOKS = [
    {
        'id': 25146, 'name': '山水情',
        'urls': [
            'https://www.gutenberg.org/files/25146/pg25146.txt',
            'https://www.gutenberg.org/cache/epub/25146/pg25146.txt',
        ],
    },
    {
        'id': 25288, 'name': '山海經',
        'urls': [
            'https://www.gutenberg.org/files/25288/25288-0.txt',
            'https://www.gutenberg.org/cache/epub/25288/pg25288.txt',
        ],
    },
    {
        'id': 25501, 'name': '易經',
        'urls': [
            'https://www.gutenberg.org/files/25501/25501-0.txt',
            'https://www.gutenberg.org/cache/epub/25501/pg25501.txt',
        ],
    },
    {
        'id': 23938, 'name': '木蘭奇女傳',
        'urls': [
            'https://www.gutenberg.org/files/23938/23938-0.txt',
            'https://www.gutenberg.org/cache/epub/23938/pg23938.txt',
        ],
    },
    {
        'id': 25242, 'name': '野草',
        'urls': [
            'https://www.gutenberg.org/files/25242/25242-0.txt',
            'https://www.gutenberg.org/cache/epub/25242/pg25242.txt',
        ],
    },
    {
        'id': 25559, 'name': '中國小說史略',
        'urls': [
            'https://www.gutenberg.org/files/25559/25559-0.txt',
            'https://www.gutenberg.org/cache/epub/25559/pg25559.txt',
        ],
    },
    {
        'id': 25271, 'name': '朝花夕拾',
        'urls': [
            'https://www.gutenberg.org/files/25271/25271-0.txt',
            'https://www.gutenberg.org/cache/epub/25271/pg25271.txt',
        ],
    },
    {
        'id': 25346, 'name': '南腔北調集',
        'urls': [
            'https://www.gutenberg.org/files/25346/25346-0.txt',
            'https://www.gutenberg.org/cache/epub/25346/pg25346.txt',
        ],
    },
    {
        'id': 25332, 'name': '阿Q正傳',
        'urls': [
            'https://www.gutenberg.org/files/25332/25332-0.txt',
            'https://www.gutenberg.org/cache/epub/25332/pg25332.txt',
        ],
    },
    {
        'id': 24042, 'name': '彷徨',
        'urls': [
            'https://www.gutenberg.org/files/24042/24042-0.txt',
            'https://www.gutenberg.org/cache/epub/24042/pg24042.txt',
        ],
    },
    {
        'id': 25297, 'name': '狂人日記',
        'urls': [
            'https://www.gutenberg.org/files/25297/25297-0.txt',
            'https://www.gutenberg.org/cache/epub/25297/pg25297.txt',
        ],
    },
    # ---- 第二批新书（2026-09-01 入库） ----
    {
        'id': 25328, 'name': '豆棚閒話',
        'urls': [
            'https://www.gutenberg.org/files/25328/25328-0.txt',
            'https://www.gutenberg.org/cache/epub/25328/pg25328.txt',
        ],
    },
    {
        'id': 24225, 'name': '戲中戲',
        'urls': [
            'https://www.gutenberg.org/files/24225/24225-0.txt',
            'https://www.gutenberg.org/cache/epub/24225/pg24225.txt',
        ],
    },
    {
        'id': 27119, 'name': '比目魚',
        'urls': [
            'https://www.gutenberg.org/files/27119/27119-0.txt',
            'https://www.gutenberg.org/cache/epub/27119/pg27119.txt',
        ],
    },
    {
        'id': 12479, 'name': '三字經',
        'urls': [
            'https://www.gutenberg.org/files/12479/12479-0.txt',
            'https://www.gutenberg.org/cache/epub/12479/pg12479.txt',
        ],
    },
    {
        'id': 23825, 'name': '施公案',
        'urls': [
            'https://www.gutenberg.org/files/23825/23825-0.txt',
            'https://www.gutenberg.org/cache/epub/23825/pg23825.txt',
        ],
    },
    {
        'id': 54494, 'name': '海公案',
        'urls': [
            'https://www.gutenberg.org/files/54494/54494-0.txt',
            'https://www.gutenberg.org/cache/epub/54494/pg54494.txt',
        ],
    },
    {
        'id': 24068, 'name': '燕丹子',
        'urls': [
            'https://www.gutenberg.org/files/24068/24068-0.txt',
            'https://www.gutenberg.org/cache/epub/24068/pg24068.txt',
        ],
    },
    {
        'id': 27686, 'name': '狄公案',
        'urls': [
            'https://www.gutenberg.org/files/27686/27686-0.txt',
            'https://www.gutenberg.org/cache/epub/27686/pg27686.txt',
        ],
    },
    {
        'id': 25196, 'name': '百家姓',
        'urls': [
            'https://www.gutenberg.org/files/25196/25196-0.txt',
            'https://www.gutenberg.org/cache/epub/25196/pg25196.txt',
        ],
    },
    {
        'id': 24048, 'name': '禮記',
        'urls': [
            'https://www.gutenberg.org/files/24048/24048-0.txt',
            'https://www.gutenberg.org/cache/epub/24048/pg24048.txt',
        ],
    },
]

UA = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) gutenberg-library/1.0'}


def fetch(url, retries=3):
    """单链接抓取，退避重试：5s / 10s / 20s。"""
    delay = 5
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=60) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None  # 404 直接判定该链接不可用，不占用重试次数
            print(f'    HTTP {e.code}（第{attempt}次）')
        except Exception as e:
            print(f'    网络错误 {e}（第{attempt}次）')
        if attempt < retries:
            time.sleep(delay)
            delay *= 2
    return None


def download_one(b):
    out = os.path.join(RAW_DIR, f"{b['name']}.txt")
    if os.path.exists(out) and os.path.getsize(out) > 0:
        print(f"  · 已存在，跳过：{b['name']}")
        return True
    print(f"  ⬇ {b['name']}  #{b['id']}")
    for i, url in enumerate(b['urls']):
        data = fetch(url)
        if data:
            with open(out, 'wb') as f:
                f.write(data)
            print(f"    成功（{'首选' if i == 0 else '备用 cache' if i == 1 else f'备用{i+1}'}: {url.split('/')[-1]}） {len(data)} 字节")
            return True
        print(f'    链接不可用: {url}')
    print(f"  ✗ 失败：{b['name']}（两个链接均不可用）")
    return False


def main():
    # 要抓的书
    targets = sys.argv[1:] if len(sys.argv) > 1 else [b['name'] for b in BOOKS]
    ok = 0
    first = True
    for b in BOOKS:
        if b['name'] not in targets:
            continue
        if not first:
            print(f'  ⏳ 间隔 5 秒…')
            time.sleep(5)
        first = False
        if download_one(b):
            ok += 1
    print(f'== 完成：成功 {ok}/{len(targets)} ==')


if __name__ == '__main__':
    main()
