#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
全站句子池构建：从站点书库 JSON 切句 → 按经史子集分类输出
  library/sentences/{category}.json   (jing/shi/zi/ji/modern)
  library/sentence-manifest.json      (每个分类的文件路径与句子数量)
切句规则：以 。．！？；： 为边界；诗词（五/七言或 詩曰/詞曰 标记）按逗号切「句」；
         过滤 <5 字 或 >60 字。
记录：id / text / book / bookId / chapter / anchor / length
用法：python3 文本/build_sentences.py
"""
import os
import re
import json
import gzip

BASE = os.path.dirname(os.path.abspath(__file__))          # 文本/
DATA = os.path.join(BASE, '_site_data')
OUT_DIR = os.path.join(BASE, '..', '网站', 'library', 'sentences')
MANIFEST_OUT = os.path.join(BASE, '..', '网站', 'library', 'sentence-manifest.json')
MODERN_SRC = os.path.join(BASE, '作者手记', '2134.md')

# 书 → (分类, bookId)
BOOK_META = {
    '史記': ('shi', 'shiji'),
    '漢書': ('shi', 'hanshu'),
    '三國志': ('shi', 'sanguozhi'),
    '三國演義': ('shi', 'sanguo-yanyi'),
    '水滸傳': ('zi', 'shuihu-zhuan'),
    '西遊記': ('zi', 'xiyou-ji'),
    '紅樓夢': ('zi', 'honglou-meng'),
    '古文觀止': ('ji', 'gwz'),
}
CATS = ['jing', 'shi', 'zi', 'ji', 'modern']

SENT_END = '。．！？；：'
CLEAN_STRIP = ' \u3000，,、。．！？；：'
MARKER_RE = re.compile(r'^[詩詞诗词赞讚]曰[：:，,]?')


def split_paragraph(para, poetry_next):
    para = para.strip()
    if not para:
        return [], poetry_next
    is_marker = bool(MARKER_RE.match(para))
    # 诗词检测：逗号分段（去标点）长度齐整（全 5 或全 7 等）
    clean_segs = [s.strip(CLEAN_STRIP) for s in re.split(r'[，,、]', para)]
    clean_segs = [s for s in clean_segs if s]
    uniform = (len(clean_segs) >= 2 and clean_segs[0]
               and all(len(s) == len(clean_segs[0]) for s in clean_segs))
    poetry = poetry_next or is_marker or uniform

    if poetry:
        body = para
        if is_marker:
            body = MARKER_RE.sub('', para).strip()
        lines = [s.strip(CLEAN_STRIP) for s in re.split(r'[，,、。．！？；：]', body)]
        lines = [s for s in lines if s]
        return lines, True

    # 散文：按句末标点切（保留句末标点）
    units, buf = [], ''
    for ch in para:
        buf += ch
        if ch in SENT_END:
            units.append(buf)
            buf = ''
    if buf.strip():
        units.append(buf)
    return [u.strip() for u in units if u.strip()], False


def build_for_book(book_name, cat, book_id):
    path = os.path.join(DATA, book_name + '.json')
    if not os.path.exists(path):
        print(f'  ⚠️ 缺少 {path}，跳过')
        return []
    data = json.load(open(path, encoding='utf-8'))
    recs = []
    seen = set()
    for si, sec in enumerate(data.get('sections', [])):
        chapter = sec.get('title', '')
        poetry_next = False
        for pi, para in enumerate(sec.get('paragraphs', [])):
            sents, poetry_next = split_paragraph(para, poetry_next)
            for sj, s in enumerate(sents):
                if not (5 <= len(s) <= 60):
                    continue
                if s in seen:
                    continue
                seen.add(s)
                recs.append({
                    'id': f'{book_id}-{si:03d}-{pi:02d}-{sj:02d}',
                    'text': s,
                    'book': book_name,
                    'bookId': book_id,
                    'chapter': chapter,
                    'anchor': s,
                    'length': len(s),
                })
    return recs

def build_modern():
    if not os.path.exists(MODERN_SRC):
        return []
    text = open(MODERN_SRC, encoding='utf-8').read()
    text = re.sub(r'^#+[^\n]*\n', '', text, flags=re.M)
    text = text.replace('**', '')
    recs, seen = [], set()
    units = []
    buf = ''
    for ch in text:
        buf += ch
        if ch in '。！？\n':
            units.append(buf)
            buf = ''
    if buf.strip():
        units.append(buf)
    for si, u in enumerate(units):
        for piece in re.split(r'[，,、；：]', u):
            s = piece.strip(CLEAN_STRIP)
            if not (5 <= len(s) <= 60):
                continue
            if s in seen:
                continue
            seen.add(s)
            recs.append({
                'id': f'author-notes-{si:03d}-{len(recs):03d}',
                'text': s,
                'book': '作者手记',
                'bookId': 'author-notes',
                'chapter': '作者手记',
                'anchor': s,
                'length': len(s),
            })
    return recs


def gzip_size(recs):
    raw = json.dumps(recs, ensure_ascii=False).encode('utf-8')
    return len(gzip.compress(raw, 9))


def sample(recs, cap):
    if len(recs) <= cap:
        return recs
    step = len(recs) / float(cap)
    return [recs[int(i * step)] for i in range(cap)]


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    all_recs = {c: [] for c in CATS}

    for book_name, (cat, book_id) in BOOK_META.items():
        recs = build_for_book(book_name, cat, book_id)
        all_recs[cat].extend(recs)
        print(f'  {book_name} → {cat}: {len(recs)} 句')

    all_recs['modern'] = build_modern()
    print(f'  作者手记 → modern: {len(all_recs["modern"])} 句')

    manifest = {'generated': '2026-08-31', 'categories': []}
    for cat in CATS:
        recs = all_recs[cat]
        while recs and gzip_size(recs) > 90 * 1024:
            recs = sample(recs, int(len(recs) * 0.9))
        all_recs[cat] = recs
        path = os.path.join(OUT_DIR, f'{cat}.json')
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(recs, f, ensure_ascii=False, separators=(',', ':'))
        print(f'  [{cat}] {len(recs)} 句, 文件 {os.path.getsize(path)/1024:.0f}KB, gzip {gzip_size(recs)/1024:.0f}KB')
        manifest['categories'].append({
            'category': cat,
            'path': f'library/sentences/{cat}.json',
            'count': len(recs),
        })

    os.makedirs(os.path.dirname(MANIFEST_OUT), exist_ok=True)
    with open(MANIFEST_OUT, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, ensure_ascii=False, separators=(',', ':'))
    print(f'✅ manifest: {MANIFEST_OUT} ({os.path.getsize(MANIFEST_OUT)}B)')


if __name__ == '__main__':
    main()

