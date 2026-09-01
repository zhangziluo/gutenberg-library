#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
新书（古登堡）→ data/books/{key}.json
  * 截取 START/END 之间正文；删除许可证/制作人员等元数据；保留繁体原样
  * 段落聚合：空行分段；段内行接续无空格拼接（适应 Gutenberg 折行）
  * 切分：
      山水情      → 22 回（第X回）
      山海經      → 18 卷（南山經…海內經）
      易經        → 64 卦 + 繫辭上/下傳、說卦、序卦、雜卦 = 69 章
      木蘭奇女傳  → 序 + 32 回（删「附錄 編修記錄」）
      野草        → 24 篇（題辭 + 23 篇）
      中國小說史略→ 題記 + 28 篇
      朝花夕拾    → 10 篇（小引…後記）
      南腔北調集  → 46 篇（删 BB 分隔行）
      阿Q正傳     → 9 章（第X章，标题去全角空格）
      彷徨        → 8 篇（本版缺 幸福的家庭/肥皂/弟兄）
      狂人日記    → 整本 1 章
  * 同时生成 库索引 library-index.json（含分类）
输出格式：
  { "book", "author", "category", "subcategory", "chapters": [{ "title", "content" }] }
"""
import os
import re
import json
import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(BASE, 'raw')
ROOT = os.path.dirname(os.path.dirname(BASE))          # 项目根
OUT_DIR = os.path.join(ROOT, 'data', 'books')          # /data/books/
os.makedirs(OUT_DIR, exist_ok=True)

START_RE = re.compile(r'START OF (?:THE|THIS) PROJECT GUTENBERG')
END_RE = re.compile(r'END OF (?:THE|THIS) PROJECT GUTENBERG')
RE_HUI = re.compile(r'^[ 　]*第([〇○零一二三四五六七八九十百]+)回(?=[ 　:：]|$)')
RE_GUA = re.compile(r'^第[ 　]*([〇○零一二三四五六七八九十百]+)[ 　]*卦$')
RE_BAO = re.compile(r'^《易經﹒([^》]+)》$')
CREDIT_START = re.compile(r'^(Produced by|Prepared by|Transcribed by|Posted by|This file|Copyright|End of|Project Gutenberg|Release date|Title:|Author:|Language:|\[eBook)', re.I)
RE_DASH_ONLY = re.compile(r'^[-—=·_~]+$')
RE_ASCII = re.compile(r"^[A-Za-z0-9 \t,.;:!?%$#@&*()\-–—_~/\\+=]+$")

DIGIT = {'〇': 0, '○': 0, '零': 0, '一': 1, '二': 2, '三': 3, '四': 4,
         '五': 5, '六': 6, '七': 7, '八': 8, '九': 9}


def cn_to_int(s):
    """支持 十四/一四/一百 式的中文数字。"""
    n = 0
    if '百' in s:
        i = s.index('百')
        n += (DIGIT.get(s[i - 1], 1) if i > 0 else 1) * 100
        s = s[i + 1:]
    if '十' in s:
        i = s.index('十')
        n += (DIGIT.get(s[i - 1], 1) if i > 0 else 1) * 10
        s = s[i + 1:]
    if s:
        n += DIGIT.get(s[0], 0)
    return n


# ---------------------------------------------------------------
# 抽取正文（START/END 之间 + 清理头部尾部元数据）
# ---------------------------------------------------------------
def extract_body(lines):
    start = end = None
    for i, l in enumerate(lines):
        if start is None and START_RE.search(l):
            start = i
        if end is None and END_RE.search(l):
            end = i
    body = lines[start + 1:end] if (start is not None and end is not None) else lines
    # 头部：删空白/制作人员/ASCII 元数据/分隔线，直到首个中文内容行
    i = 0
    while i < len(body):
        s = body[i].strip()
        if not s or RE_DASH_ONLY.match(s) or CREDIT_START.match(s) or RE_ASCII.match(s):
            i += 1
            continue
        break
    body = body[i:]
    # 尾部：删空白/ASCII/结束语
    j = len(body)
    while j > 0:
        s = body[j - 1].strip()
        if not s or RE_ASCII.match(s) or 'End of' in s or 'Gutenberg' in s:
            j -= 1
            continue
        break
    body = body[:j]
    # 中间残留的极少数制作行（如野草/山海經 开头 Produced by…）保险起见删掉
    body = [l for l in body if not CREDIT_START.match(l.strip())]
    return body


# ---------------------------------------------------------------
# 段落聚合：空行分段；段内行尾无句读(。！？」：；)则与下行接续拼接
# （山水情行行整句→各成段；木蘭/野草折行散文→拼接；易經爻辞→各成段）
# ---------------------------------------------------------------
SENT_END = ('。', '！', '？', '」', '：', '∶', '；')


def paragraphs(body):
    paras = []
    cur = []
    for l in body:
        s = l.strip()
        if not s:
            if cur:
                paras.append('\n'.join(cur))
                cur = []
            continue
        if cur and not cur[-1].endswith(SENT_END):
            cur[-1] += s          # 折行接续
        else:
            cur.append(s)         # 新段落
    if cur:
        paras.append('\n'.join(cur))
    return paras


# ---------------------------------------------------------------
# 切分器
# ---------------------------------------------------------------
def split_hui(body, keep_prefix_title=None, cut_at=None, drop_prefix=False):
    """按「第X回」切分；可选开头补一章（keep_prefix_title=「序」），
    可选从 cut_at 行起截断（如木蘭的「附錄」），
    可选丢弃开头非回目行（drop_prefix，如山水情仅书题）。"""
    if cut_at:
        for i, l in enumerate(body):
            if l.strip().startswith(cut_at):
                body = body[:i]
                break
    marks = []
    for i, l in enumerate(body):
        m = RE_HUI.match(l)
        if m:
            marks.append((i, cn_to_int(m.group(1)), l))
    # 去重：相邻同号保留后者
    deduped = []
    for m in marks:
        if deduped and deduped[-1][1] == m[1]:
            deduped[-1] = m
        else:
            deduped.append(m)
    marks = deduped

    chapters = []
    # 开头的非回目内容：drop_prefix 时丢弃，否则单独成章（如木蘭「序」）
    if marks and marks[0][0] > 0:
        pre = body[:marks[0][0]]
        p = paragraphs(pre)
        if p and not drop_prefix:
            title = keep_prefix_title or p[0][:20]
            chapters.append({'title': title, 'content': '\n'.join(p)})
    for k, (idx, num, line) in enumerate(marks):
        end_idx = marks[k + 1][0] if k + 1 < len(marks) else len(body)
        title = re.sub(r'[ \t]+', ' ', line).strip()
        raw = body[idx + 1:end_idx]
        while raw and not raw[0].strip():
            raw = raw[1:]
        while raw and not raw[-1].strip():
            raw = raw[:-1]
        content = '\n'.join(paragraphs(raw))
        chapters.append({'title': title, 'content': content})
    return chapters


def split_shanhaijing(body, volumes):
    marks = []
    for i, l in enumerate(body):
        s = l.strip()
        if s in volumes:
            marks.append((i, s))
    chapters = []
    for k, (idx, name) in enumerate(marks):
        end_idx = marks[k + 1][0] if k + 1 < len(marks) else len(body)
        raw = body[idx + 1:end_idx]
        while raw and not raw[0].strip():
            raw = raw[1:]
        while raw and not raw[-1].strip():
            raw = raw[:-1]
        chapters.append({'title': name, 'content': '\n'.join(paragraphs(raw))})
    return chapters


def split_yijing(body):
    marks = []
    for i, l in enumerate(body):
        m = RE_GUA.match(l)
        if m:
            marks.append((i, 'gua', m.group(1), re.sub(r'[ 　]+', '', l)))
            continue
        m = RE_BAO.match(l)
        if m:
            marks.append((i, 'bao', None, m.group(1)))
    chapters = []
    for k, (idx, kind, cn, title) in enumerate(marks):
        end_idx = marks[k + 1][0] if k + 1 < len(marks) else len(body)
        raw = body[idx + 1:end_idx]
        if kind == 'gua':
            # 卦名 = 标题行后的首个非空行
            gua_name = ''
            for j in range(idx + 1, min(idx + 8, len(body))):
                s = body[j].strip()
                if s:
                    gua_name = s
                    break
            t = f'{title} {gua_name}' if gua_name else title
        else:
            t = title
        while raw and not raw[0].strip():
            raw = raw[1:]
        while raw and not raw[-1].strip():
            raw = raw[:-1]
        # 卦名行若为正文首行则剔除（在清空行之后判断）
        if kind == 'gua' and gua_name and raw and raw[0].strip() == gua_name:
            raw = raw[1:]
        chapters.append({'title': t, 'content': '\n'.join(paragraphs(raw))})
    return chapters


def split_yecao(body, pieces):
    marks = []
    for i, l in enumerate(body):
        s = l.strip()
        if s in pieces:
            marks.append((i, s))
    marks = sorted(set(marks))
    chapters = []
    for k, (idx, name) in enumerate(marks):
        end_idx = marks[k + 1][0] if k + 1 < len(marks) else len(body)
        raw = body[idx + 1:end_idx]
        while raw and not raw[0].strip():
            raw = raw[1:]
        while raw and not raw[-1].strip():
            raw = raw[:-1]
        chapters.append({'title': name, 'content': '\n'.join(paragraphs(raw))})
    return chapters


# ---------------------------------------------------------------
# 鲁迅专题 6 本 · 新增切分器
# ---------------------------------------------------------------
RE_ZHANG = re.compile(r'^[ 　]*第([〇○零一二三四五六七八九十百]+)章[ 　]')
RE_PIAN = re.compile(r'^第([〇○零一二三四五六七八九十百]+)篇[ 　]')
RE_NOTE_MARK = re.compile(r'[〔【][0-9０-９]+[〕】]')
RE_BB = re.compile(r'^B[ 　]*B$')


def _trim(raw):
    while raw and not raw[0].strip():
        raw = raw[1:]
    while raw and not raw[-1].strip():
        raw = raw[:-1]
    return raw


def split_zhang(body):
    """阿Q正傳：按「第X章　篇名」切分；标题去全角空格（優　勝　記　略 → 優勝記略）。"""
    marks = []
    for i, l in enumerate(body):
        m = RE_ZHANG.match(l)
        if m:
            marks.append((i, cn_to_int(m.group(1))))
    marks = sorted(set(marks))
    chapters = []
    for k, (idx, num) in enumerate(marks):
        end_idx = marks[k + 1][0] if k + 1 < len(marks) else len(body)
        line = body[idx]
        t = re.sub(r'　', '', line)
        t = re.sub(r'^(.+?章)(.+)$', r'\1 \2', t).strip()
        raw = _trim(body[idx + 1:end_idx])
        chapters.append({'title': t, 'content': '\n'.join(paragraphs(raw))})
    return chapters


def split_pian(body):
    """中國小說史略：題記 + 第X篇；重复标题（第九篇）只取首个作边界，正文内重复篇名行剔除。"""
    marks = []
    seen = set()
    for i, l in enumerate(body):
        s = l.strip()
        if s in ('題記', '後記', '附錄', '小引'):
            if s in seen:
                continue
            seen.add(s)
            marks.append((i, s))
            continue
        m = RE_PIAN.match(s)
        if m:
            if m.group(1) in seen:
                continue
            seen.add(m.group(1))
            marks.append((i, re.sub(r'[ 　]+', ' ', s).strip()))
    bound = {t for _, t in marks}
    chapters = []
    for k, (idx, title) in enumerate(marks):
        end_idx = marks[k + 1][0] if k + 1 < len(marks) else len(body)
        raw = body[idx + 1:end_idx]
        raw = [l for l in raw if re.sub(r'[ 　]+', ' ', l.strip()).strip() not in bound]
        raw = [l for l in raw if not RE_BB.match(l.strip())]
        raw = _trim(raw)
        chapters.append({'title': title, 'content': '\n'.join(paragraphs(raw))})
    return chapters


def split_pieces(body, pieces):
    """按篇名列表切分（朝花夕拾/南腔北調集/彷徨）。
    pieces: [(pattern, title)]，pattern 以 ^ 开头视为正则，否则精确匹配整行。
    去重复相邻同篇名（南腔「題記」）；正文删 BB 分隔行与重复篇名行；标题去〔1〕角标。"""
    marks = []
    for i, l in enumerate(body):
        s = l.strip()
        for pat, title in pieces:
            if pat.startswith('^'):
                if re.search(pat, s):
                    marks.append((i, title))
                    break
            else:
                if s == pat:
                    marks.append((i, title))
                    break
    # 去重：相邻同标题保留首个
    dedup = []
    for m in marks:
        if dedup and dedup[-1][1] == m[1]:
            continue
        dedup.append(m)
    marks = dedup
    bound = {t for _, t in marks}
    chapters = []
    for k, (idx, title) in enumerate(marks):
        end_idx = marks[k + 1][0] if k + 1 < len(marks) else len(body)
        raw = body[idx + 1:end_idx]
        raw = [l for l in raw if l.strip() not in bound]
        raw = [l for l in raw if not RE_BB.match(l.strip())]
        raw = _trim(raw)
        t = RE_NOTE_MARK.sub('', title).strip()
        chapters.append({'title': t, 'content': '\n'.join(paragraphs(raw))})
    return chapters


def split_single(body, title):
    """整本不切分（狂人日記）。"""
    raw = _trim(body)
    return [{'title': title, 'content': '\n'.join(paragraphs(raw))}]

BOOKS = [
    {
        'key': 'shanshui-qing', 'book': '山水情', 'author': '佚名',
        'category': '子部', 'subcategory': '小說家',
        'source': 'Project Gutenberg #25146', 'file': '山水情.txt',
        'split': 'hui', 'drop_prefix': True,
    },
    {
        'key': 'shanhaijing', 'book': '山海經', 'author': '佚名',
        'category': '子部', 'subcategory': '小說家（志怪·地理）',
        'source': 'Project Gutenberg #25288', 'file': '山海經.txt',
        'split': 'shanhaijing',
        'volumes': ['南山經', '西山經', '北山經', '東山經', '中山經',
                    '海外南經', '海外西經', '海外北經', '海外東經',
                    '海內南經', '大荒南經', '海內西經', '海內北經',
                    '海內東經', '大荒東經', '大荒西經', '大荒北經', '海內經'],
    },
    {
        'key': 'yijing', 'book': '易經', 'author': '佚名',
        'category': '經部', 'subcategory': '易',
        'source': 'Project Gutenberg #25501', 'file': '易經.txt',
        'split': 'yijing',
    },
    {
        'key': 'mulan-qi-nv-zhuan', 'book': '木蘭奇女傳', 'author': '佚名',
        'category': '子部', 'subcategory': '小說家',
        'source': 'Project Gutenberg #23938', 'file': '木蘭奇女傳.txt',
        'split': 'hui', 'keep_prefix_title': '序', 'cut_at': '附錄',
    },
    {
        'key': 'yecao', 'book': '野草', 'author': '魯迅',
        'category': '近現代文學', 'subcategory': '魯迅專題',
        'source': 'Project Gutenberg #25242', 'file': '野草.txt',
        'split': 'yecao',
        'pieces': ['《野草》題辭', '秋夜', '影的告別', '求乞者', '我的失戀',
                   '復仇', '復仇 (其二)', '希望', '雪', '風箏', '好的故事',
                   '過客', '死火', '狗的駁詰', '失掉的好地獄', '墓碣文',
                   '頹敗線的顫動', '立論', '死後', '這樣的戰士',
                   '聰明人和傻子和奴才', '臘葉', '淡淡的血痕中', '一覺'],
    },
    {
        'key': 'zhongguo-xiaoshuo-shilue', 'book': '中國小說史略', 'author': '魯迅',
        'category': '近現代文學', 'subcategory': '魯迅專題',
        'source': 'Project Gutenberg #25559', 'file': '中國小說史略.txt',
        'split': 'pian',
    },
    {
        'key': 'zhaohua-xishi', 'book': '朝花夕拾', 'author': '魯迅',
        'category': '近現代文學', 'subcategory': '魯迅專題',
        'source': 'Project Gutenberg #25271', 'file': '朝花夕拾.txt',
        'split': 'pieces',
        'pieces': [('小引', '小引'), ('狗·貓·鼠', '狗·貓·鼠'),
                   ('阿長與山海經', '阿長與山海經'), ('《二十四孝圖》', '《二十四孝圖》'),
                   ('五猖會', '五猖會'), ('無常', '無常'), ('瑣記', '瑣記'),
                   ('藤野先生', '藤野先生'), ('范愛農', '范愛農'), ('后記', '后記')],
    },
    {
        'key': 'nanqiang-beidiao-ji', 'book': '南腔北調集', 'author': '魯迅',
        'category': '近現代文學', 'subcategory': '魯迅專題',
        'source': 'Project Gutenberg #25346', 'file': '南腔北調集.txt',
        'split': 'pieces',
        'pieces': [
            ('“非所計也”', '“非所計也”'), ('連環圖畫”辯護', '連環圖畫”辯護'),
            ('“論語一年”', '“論語一年”'), ('“蜜蜂”与“蜜”', '“蜜蜂”与“蜜”'),
            ('《木刻創作法》序', '《木刻創作法》序'), ('《守常全集》題記', '《守常全集》題記'),
            ('《豎琴》前記', '《豎琴》前記'), ('《蕭伯納在上海》序', '《蕭伯納在上海》序'),
            ('《一個人的受難》序', '《一個人的受難》序'), ('《自選集》自序', '《自選集》自序'),
            ('《總退卻》序', '《總退卻》序'), ('大家降一級試試看', '大家降一級試試看'),
            ('搗鬼心傳', '搗鬼心傳'), ('聲明', '聲明'), ('給文學社信', '給文學社信'),
            ('關于翻譯', '關于翻譯'), ('關于婦女解放', '關于婦女解放'),
            ('關于女人', '關于女人'), ('火', '火'), ('家庭為中國之基本', '家庭為中國之基本'),
            ('經驗', '經驗'), ('看蕭和“看蕭的人們”記', '看蕭和“看蕭的人們”記'),
            ('論“第三种人”', '論“第三种人”'), ('林克多《蘇聯聞見錄》序', '林克多《蘇聯聞見錄》序'),
            ('論“赴難”和“逃難”', '論“赴難”和“逃難”'), ('論翻印木刻', '論翻印木刻'),
            ('漫与', '漫与'), ('辱罵和恐嚇決不是戰斗', '辱罵和恐嚇決不是戰斗'),
            ('沙', '沙'), ('世故三昧', '世故三昧'), ('誰的矛盾', '誰的矛盾'),
            ('談金圣歎', '談金圣歎'), ('題記', '題記'), ('听說夢', '听說夢'),
            ('為了忘卻的記念', '為了忘卻的記念'), ('我們不再受騙了', '我們不再受騙了'),
            ('小品文的危机', '小品文的危机'), ('學生和玉佛', '學生和玉佛'),
            ('諺語', '諺語'), ('謠言世家', '謠言世家'), ('由中國女人的腳', '由中國女人的腳'),
            ('又論“第三种人”', '又論“第三种人”'), ('真假堂吉訶德', '真假堂吉訶德'),
            ('祝《濤聲》', '祝《濤聲》'), ('上海的少女〔１〕', '上海的少女'),
            ('作文秘訣', '作文秘訣'),
        ],
    },
    {
        'key': 'aq-zhengzhuan', 'book': '阿Q正傳', 'author': '魯迅',
        'category': '近現代文學', 'subcategory': '魯迅專題',
        'source': 'Project Gutenberg #25332', 'file': '阿Q正傳.txt',
        'split': 'zhang',
    },
    {
        'key': 'panghuang', 'book': '彷徨', 'author': '魯迅',
        'category': '近現代文學', 'subcategory': '魯迅專題',
        'source': 'Project Gutenberg #24042', 'file': '彷徨.txt',
        'split': 'pieces',
        'pieces': [
            ('^祝福$', '祝福'), (r'^傷逝【1】\s*──', '傷逝──涓生的手記'),
            ('^在酒樓上$', '在酒樓上'), ('^孤獨者$', '孤獨者'), ('^示眾$', '示眾'),
            ('^高老夫子〔１〕$', '高老夫子'), ('^離婚$', '離婚'),
            ('^長明燈〔１〕$', '長明燈'),
        ],
    },
    {
        'key': 'kuangren-riji', 'book': '狂人日記', 'author': '魯迅',
        'category': '近現代文學', 'subcategory': '魯迅專題',
        'source': 'Project Gutenberg #25297', 'file': '狂人日記.txt',
        'split': 'single',
    },
]

SPLITTERS = {
    'hui': split_hui,
    'shanhaijing': split_shanhaijing,
    'yijing': split_yijing,
    'yecao': split_yecao,
    'zhang': split_zhang,
    'pian': split_pian,
    'pieces': split_pieces,
    'single': split_single,
}


def main():
    index_cats = {}
    for cfg in BOOKS:
        lines = open(os.path.join(RAW, cfg['file']), encoding='utf-8-sig').read().split('\n')
        body = extract_body(lines)
        splitter = SPLITTERS[cfg['split']]
        if cfg['split'] == 'hui':
            chapters = splitter(body, cfg.get('keep_prefix_title'), cfg.get('cut_at'),
                                cfg.get('drop_prefix', False))
        elif cfg['split'] == 'shanhaijing':
            chapters = splitter(body, cfg['volumes'])
        elif cfg['split'] in ('yecao', 'pieces'):
            chapters = splitter(body, cfg['pieces'])
        elif cfg['split'] == 'single':
            chapters = splitter(body, cfg['book'])
        else:
            chapters = splitter(body)

        out = {
            'book': cfg['book'],
            'author': cfg['author'],
            'category': cfg['category'],
            'subcategory': cfg['subcategory'],
            'chapters': chapters,
        }
        p = os.path.join(OUT_DIR, cfg['key'] + '.json')
        with open(p, 'w', encoding='utf-8') as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
        total = sum(len(c['content']) for c in chapters)
        print(f"✅ {cfg['book']} ({cfg['key']}) → {os.path.relpath(p, ROOT)}")
        print(f"   {len(chapters)} 章 | 约 {total:,} 字 | 首章: {chapters[0]['title'][:30]} | 末章: {chapters[-1]['title'][:30]}")
        index_cats.setdefault(cfg['category'], []).append({
            'key': cfg['key'],
            'book': cfg['book'],
            'author': cfg['author'],
            'subcategory': cfg['subcategory'],
            'chapters': len(chapters),
            'source': cfg['source'],
            'path': os.path.join('data', 'books', cfg['key'] + '.json'),
        })

    # 生成 library-index.json
    cat_order = ['經部', '史部', '子部', '集部', '近現代文學']
    cats = [
        {'name': c, 'books': index_cats.get(c, [])}
        for c in cat_order
    ]
    index = {
        'title': '古籍文库 · 数据书目索引',
        'description': 'data/books/ 目录下的结构化书目（category: 經部/史部/子部/集部/近現代文學）',
        'generated': datetime.date.today().isoformat(),
        'categories': cats,
    }
    idx_path = os.path.join(ROOT, 'library-index.json')
    with open(idx_path, 'w', encoding='utf-8') as f:
        json.dump(index, f, ensure_ascii=False, indent=2)
    print(f'✅ 生成 {os.path.relpath(idx_path, ROOT)}')
    for c in cats:
        print(f"   {c['name']}: {len(c['books'])} 本")


if __name__ == '__main__':
    main()
