#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
合并 data/books/ 新书 → 站点阅读器数据 + 生成统一分类数据源
  1) 每本新书 → 文本/_site_data/{書名}.json（阅读器格式）
  2) 更新 文本/_site_data/books.json（聚合索引，供书库计数）
  3) 生成 网站/assets/data/books-data.json（统一分类数据源：
     id/title/author/category/subcategory/dynasty/description/cover）
分类：jing/shi/zi/ji/cong；近现代文学 → category=ji + subcategory=modern
"""
import os
import re
import json
from collections import Counter

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(BASE))
DATA_BOOKS = os.path.join(ROOT, 'data', 'books')
SITE_DATA = os.path.join(ROOT, '文本', '_site_data')
ASSETS = os.path.join(ROOT, '网站', 'assets', 'data')

# 分类映射（library-index 分类名 → 新五部 key）
CAT_KEY = {'經部': 'jing', '史部': 'shi', '子部': 'zi', '集部': 'ji',
           '近現代文學': 'ji'}
SUBCAT = {'近現代文學': 'modern'}

PIAN_KEYS = {'zhongguo-xiaoshuo-shilue', 'zhaohua-xishi', 'nanqiang-beidiao-ji',
             'yecao', 'panghuang'}


def reader_label(key):
    if key == 'yijing':
        return None  # 特殊处理
    if key in ('shanshui-qing', 'mulan-qi-nv-zhuan'):
        return '回目'
    if key == 'shanhaijing':
        return '卷'
    if key == 'aq-zhengzhuan':
        return '章'
    if key in PIAN_KEYS:
        return '篇目'
    return '全書'


def to_reader(key, data):
    """data/books 条目 → 阅读器 book 对象。"""
    chapters = data.get('chapters', [])
    cat = reader_label(key)
    sections = []
    for idx, ch in enumerate(chapters, 1):
        if key == 'yijing':
            label = '卦' if str(ch['title']).startswith('第') else '傳'
        else:
            label = cat
        paragraphs = ch.get('content', '').split('\n')
        sections.append({
            'book': data['book'],
            'title': ch['title'],
            'source': data.get('author', '') or '',
            'category': 'other',
            'category_label': label,
            'number': idx,
            'paragraphs': [p for p in paragraphs if p.strip()],
        })
    categories = sorted({s['category_label'] for s in sections})
    return {
        'title': data['book'],
        'section_count': len(sections),
        'categories': categories,
        'sections': sections,
    }


# 朝代与简介（19 本）
DYN = {
    '易經': '先秦（商周）', '山海經': '先秦', '山水情': '清初', '木蘭奇女傳': '清',
    '野草': '1927', '中國小說史略': '1923', '朝花夕拾': '1928', '南腔北調集': '1934',
    '阿Q正傳': '1921', '彷徨': '1926', '狂人日記': '1918',
    '史記': '西漢', '漢書': '東漢', '三國志': '西晉', '三國演義': '明',
    '水滸傳': '明', '西遊記': '明', '紅樓夢': '清', '古文觀止': '清（康熙年間）',
}
DESC = {
    '易經': '群經之首，中華文化的源頭。六十四卦涵蓋天地萬物變化之理，繫辭、說卦等十翼為儒家哲思之樞紐。',
    '山海經': '上古奇書，記山川物產、神話異獸，是中國神話與地理的寶庫。',
    '山水情': '清初才子佳人小說：書生衛旭霞與閨秀的姻緣離合，文辭清麗。',
    '木蘭奇女傳': '清代演義小說：寫木蘭代父從軍、忠孝勇烈的傳奇故事。',
    '野草': '魯迅散文詩集，23 篇晦澀而深邃的心靈獨白，被譽為中國現代文學的「天書」。',
    '中國小說史略': '魯迅開創性的小說史專著，梳理中國小說自神話傳說至清末的源流。',
    '朝花夕拾': '魯迅回憶性散文集，重溫童年與師友，在溫情中見世相。',
    '南腔北調集': '魯迅雜文集，共 51 篇，針砭時事、議論文化，鋒芒畢露。',
    '阿Q正傳': '魯迅中篇小說，以「精神勝利法」寫盡舊中國國民的靈魂創傷。',
    '彷徨': '魯迅第二部小說集，收《祝福》《傷逝》《長明燈》等 11 篇（本版收 8 篇）。',
    '狂人日記': '中國現代文學第一篇白話小說，以狂人日記揭露「吃人」的禮教。',
    '史記': '二十四史之首。太史公「究天人之際，通古今之變，成一家之言」。',
    '漢書': '中國第一部紀傳體斷代史，上起漢高祖、下終王莽。',
    '三國志': '與《史記》《漢書》《後漢書》並稱「前四史」，記魏蜀吳三國鼎立。',
    '三國演義': '中國古典四大名著之一：從桃園三結義到三分歸晉，一部英雄史詩。',
    '水滸傳': '四大名著之一：一百零八好漢聚義梁山，替天行道，快意恩仇。',
    '西遊記': '四大名著之一：唐僧師徒西天取經、歷經九九八十一難的魔幻長篇。',
    '紅樓夢': '四大名著之首：以「一把辛酸淚」，寫盡賈府興衰與寶黛情緣。',
    '古文觀止': '清代流傳最廣的古文選本，上起周秦、下迄明末，共 222 篇。',
}
CATALOG_ID = {
    '史記': 'shiji', '漢書': 'hanshu', '三國志': 'sanguozhi', '三國演義': 'sanguo-yanyi',
    '水滸傳': 'shuihu-zhuan', '西遊記': 'xiyou-ji', '紅樓夢': 'honglou-meng',
    '古文觀止': 'guwen-guangzhi',
}


def main():
    # ---- 1+2) data/books → _site_data ----
    lib_index = json.load(open(os.path.join(ROOT, 'library-index.json'), encoding='utf-8'))
    books_json_path = os.path.join(SITE_DATA, 'books.json')
    books_index = json.load(open(books_json_path, encoding='utf-8'))

    merged_books = []   # 新五部统一列表
    done = set()

    for cat_grp in lib_index['categories']:
        cat_name = cat_grp['name']
        ckey = CAT_KEY[cat_name]
        sub = SUBCAT.get(cat_name, '')
        for entry in cat_grp['books']:
            key = entry['key']
            title = entry['book']
            raw = json.load(open(os.path.join(DATA_BOOKS, key + '.json'), encoding='utf-8'))
            reader = to_reader(key, raw)
            # 写入单书文件
            with open(os.path.join(SITE_DATA, title + '.json'), 'w', encoding='utf-8') as f:
                json.dump(reader, f, ensure_ascii=False, indent=2)
            # 写入聚合 books.json
            books_index[title] = reader
            merged_books.append({
                'id': key, 'title': title, 'author': raw.get('author', '佚名'),
                'category': ckey, 'subcategory': sub, 'dynasty': DYN.get(title, ''),
                'description': DESC.get(title, raw.get('subcategory', '')),
                'sections': reader['section_count'],
                'cover': '',
            })
            done.add(title)
            print(f"  ✅ 合并 {title}（{cat_name} → {ckey}{'·modern' if sub else ''}）{reader['section_count']} 篇")

    # ---- 3) catalog.json 的 8 本主书并入统一数据 ----
    catalog = json.load(open(os.path.join(ASSETS, 'catalog.json'), encoding='utf-8'))
    for part in catalog['parts']:
        ckey = CAT_KEY[part['bu']]
        for b in part['books']:
            title = b['book']
            if title in done:
                continue
            merged_books.append({
                'id': CATALOG_ID.get(title, title), 'title': title,
                'author': b.get('author', '佚名'),
                'category': ckey, 'subcategory': '',
                'dynasty': DYN.get(title, ''),
                'description': b.get('intro', ''),
                'sections': (books_index.get(title) or {}).get('section_count'),
                'cover': '',
            })
            done.add(title)

    # 统一数据源输出
    os.makedirs(ASSETS, exist_ok=True)
    out = {
        'title': '古籍文库 · 统一分类数据源',
        'updated': '2026-09-01',
        'categories': {
            'jing': '經部：儒家經典及歷代注疏（如《論語》《詩經》《易經》等）',
            'shi': '史部：各類史書（如《史記》《資治通鑒》等）',
            'zi': '子部：諸子百家、科技、藝術、宗教等（如《老子》《孫子兵法》《本草綱目》等）',
            'ji': '集部：歷代文人詩文、詞曲、文集（如《李太白集》《文選》等）；現代文學歸入本部下「現代文學」子分類',
            'cong': '叢部：綜合性叢書（如《四庫全書》《永樂大典》等）',
        },
        'books': merged_books,
    }
    out_path = os.path.join(ASSETS, 'books-data.json')
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    # 回写 books.json
    with open(books_json_path, 'w', encoding='utf-8') as f:
        json.dump(books_index, f, ensure_ascii=False, indent=2)

    print(f"✅ 共 {len(merged_books)} 本进入统一数据源 → {os.path.relpath(out_path, ROOT)}")
    cnt = Counter(b['category'] for b in merged_books)
    print('   分类分布:', dict(cnt))


if __name__ == '__main__':
    main()

