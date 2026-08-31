#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
四大名著（古登堡计划）→ 章回 JSON
  西遊記  #23962  → 100 回（位记/十记混用：第一○回、第十四回、第一○○回）
  紅樓夢  #24264  → 120 回（1-99 用十；100+ 用第一零零回式；部分回目独行、标题在分隔线后）
  三國演義#23950  → 120 回（1-99 用十；100+ 用第一○○回式 ○）
  水滸傳  #23863  → 楔子 + 70 回（金聖歎評本）
输出：sanguo-yanyi.json / shuihu-zhuan.json / xiyou-ji.json / honglou-meng.json
  { "book": 书名, "author": 作者, "chapters": [{ "title": 回目, "content": 正文 }] }
保留繁体原文；删除 Gutenberg 版权/制作人员等元数据；正文取 START/END 之间。
"""
import os
import re
import json

BASE = os.path.dirname(os.path.abspath(__file__))

BOOKS = [
    {
        "key": "xiyou-ji", "book": "西遊記", "author": "吳承恩",
        "file": "xiyou-ji.txt",
    },
    {
        "key": "honglou-meng", "book": "紅樓夢", "author": "曹雪芹",
        "file": "honglou-meng.txt",
    },
    {
        "key": "sanguo-yanyi", "book": "三國演義", "author": "羅貫中",
        "file": "sanguo-yanyi.txt",
    },
    {
        "key": "shuihu-zhuan", "book": "水滸傳", "author": "施耐庵",
        "file": "shuihu-zhuan.txt",
    },
]

DIGIT = {'〇': 0, '○': 0, '零': 0, '一': 1, '二': 2, '三': 3, '四': 4,
         '五': 5, '六': 6, '七': 7, '八': 8, '九': 9}

def parse_hui_num(s):
    """解析『第X回』编号：同时支持标准式（十四=14、八十七=87）与纯位式（一四=14、一○○=100、一一九=119）。"""
    if '十' in s or '百' in s:
        n = 0
        if '百' in s:
            i = s.index('百')
            n += (DIGIT.get(s[i-1], 1) if i > 0 else 1) * 100
            s = s[i+1:]
        if '十' in s:
            i = s.index('十')
            n += (DIGIT.get(s[i-1], 1) if i > 0 else 1) * 10
            s = s[i+1:]
        if s:
            n += DIGIT.get(s[0], 0)
        return n
    n = 0
    for ch in s:
        n = n * 10 + DIGIT[ch]
    return n

# 回目行：第X回 后跟 空白/冒号/行尾（排除『第四回中既將…』正文误匹配）
RE_HUI = re.compile(r'^[ 　]*第([〇○零一二三四五六七八九十百]+)回(?=[ 　:：]|$)')
RE_DASH_ONLY = re.compile(r'^[-—=·_~]+$')
RE_ASCII = re.compile(r"^[A-Za-z0-9 \t,.;:!?%$#@&*()\-–—_~/\\+=]+$")
CREDIT_START = re.compile(r'^(Produced by|Prepared by|Transcribed by|Posted by|This file|Copyright|End of|Project Gutenberg|Release date|Title:|Author:|Language:|\[eBook)', re.I)


def is_blank(s):
    return not s.strip()


def clean_whitespace(s):
    """压缩行内连续空格/制表符，保留全角空格。"""
    s = re.sub(r'[ \t]+', ' ', s).strip()
    return s


def extract_body(lines):
    """取 START/END 标记之间正文；去掉头部制作人员等元数据与尾部结束语。"""
    start = end = None
    for i, l in enumerate(lines):
        if 'START OF' in l and 'PROJECT GUTENBERG' in l.upper():
            start = i
        if 'END OF' in l and 'PROJECT GUTENBERG' in l.upper():
            end = i
    body = lines[start + 1:end] if (start is not None and end is not None) else lines
    # 头部：删 空白/制作人员/纯 ASCII 元数据，直到首个中文内容行
    i = 0
    while i < len(body):
        s = body[i].strip()
        if not s or RE_DASH_ONLY.match(s) or CREDIT_START.match(s) or RE_ASCII.match(s):
            i += 1
            continue
        # 首个中文行（可能是回目或正文）
        break
    body = body[i:]
    # 尾部：删 结束语/空白
    j = len(body)
    while j > 0:
        s = body[j-1].strip()
        if not s or RE_ASCII.match(s) or 'End of' in s or 'Gutenberg' in s:
            j -= 1
            continue
        break
    body = body[:j]
    return body


def split_title_content(rest):
    """把回目行剩余部分拆成 (标题, 混入的正文开头)。
    处理 紅樓 个别回目行混入正文开头（如『…　話』『… 話說賈雨村剛欲過渡，』）。"""
    rest = rest.strip()
    if not rest:
        return rest, ''
    # 1) 明显正文开头：話說/卻說/且說（前有空白）
    m = re.search(r'[ 　](話說|卻說|且說)', rest)
    if m:
        return rest[:m.start()].strip(), rest[m.start():].strip()
    # 2) 回目为两联句，多余的第3段是正文碎片（話/卻/且 单字等）
    parts = [p.strip() for p in rest.split('　')]
    if len(parts) >= 3:
        return '　'.join(parts[:2]).strip(), '　'.join(parts[2:]).strip()
    return rest, ''


def split_chapters(body):
    """按回目行切分章回。返回 [(number, title, content)]。"""
    marks = []   # (idx, number, inline_or_None, is_xiezi)
    for i, l in enumerate(body):
        m = RE_HUI.match(l)
        if m:
            num = parse_hui_num(m.group(1))
            rest = l[m.end():]
            marks.append((i, num, rest, False))
        elif l.strip().startswith('楔子'):
            marks.append((i, 0, l.strip(), True))

    # 去重：相邻同号回目保留后者（紅樓第四十五回回目重复）
    deduped = []
    for m in marks:
        if deduped and deduped[-1][1] == m[1]:
            deduped[-1] = m
        else:
            deduped.append(m)
    marks = deduped

    chapters = []
    for k, (idx, num, inline, is_xiezi) in enumerate(marks):
        end_idx = marks[k+1][0] if k + 1 < len(marks) else len(body)
        if is_xiezi:
            title = clean_whitespace(inline)
            tail = ''
            content_start = idx + 1
        elif inline is not None and inline.strip():
            title, tail = split_title_content(inline)
            title = clean_whitespace(title)
            content_start = idx + 1
        else:
            # 回目独行：标题在后续非空/非分隔线行
            title = None
            tail = ''
            content_start = idx + 1
            for j in range(idx + 1, min(idx + 20, len(body))):
                s = body[j].strip()
                if not s or RE_DASH_ONLY.match(s):
                    continue
                if re.search(r'[\u4e00-\u9fff]', s):
                    title = clean_whitespace(s)
                    content_start = j + 1
                    break
            if title is None:
                title = ''

        # 修复 OCR 残符：标题内 『X@』 → 『　』（紅樓 62/102 回 回目 分隔符损坏）
        title = re.sub(r'[^　]@', '　', title)
        # 去回目前缀分隔符（三國『第一回：』）
        title = re.sub(r'^[：: 　]+', '', title).strip()

        # 正文：tail（混入的正文开头） + 后续行
        raw = body[content_start:end_idx]
        if tail:
            raw = [tail] + raw
        # 去掉前 8 行内的分隔线
        cleaned = []
        for kk, line in enumerate(raw):
            if kk < 8 and RE_DASH_ONLY.match(line.strip()):
                continue
            cleaned.append(line)
        raw = cleaned
        # 去前导 空行/分隔线
        while raw and (not raw[0].strip() or RE_DASH_ONLY.match(raw[0].strip())):
            raw = raw[1:]
        # 去尾部 空行/分隔线/重复回目行
        while raw and (not raw[-1].strip() or RE_DASH_ONLY.match(raw[-1].strip())
                       or RE_HUI.match(raw[-1])):
            raw = raw[:-1]
        content = '\n'.join(raw)
        chapters.append({"title": title, "content": content})
    return chapters



def main():
    for cfg in BOOKS:
        path = os.path.join(BASE, cfg["file"])
        lines = open(path, encoding='utf-8-sig').read().split('\n')
        body = extract_body(lines)
        chapters = split_chapters(body)
        out = {
            "book": cfg["book"],
            "author": cfg["author"],
            "chapters": chapters,
        }
        out_path = os.path.join(BASE, cfg["key"] + '.json')
        with open(out_path, 'w', encoding='utf-8') as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
        total = sum(len(c['content']) for c in chapters)
        print(f"✅ {cfg['book']}: {len(chapters)} 回 | 总字数约 {total:,}")
        print(f"   首回: {chapters[0]['title'][:40]}")
        print(f"   末回: {chapters[-1]['title'][:40]}")
        # 校验编号连续
        nums = []
        for c, m in zip(chapters, [None] + list(range(0, len(chapters)))):
            pass
        print()


if __name__ == '__main__':
    main()
