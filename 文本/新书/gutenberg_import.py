#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
古登堡新书一体化入库脚本（gutenberg_import）
====================================================
一条命令完成：下载 TXT → 清洗 → 切分 → 按「数据已迁至 网站/_site_data」的新结构四处输出。

  * 下载：顺序执行、每本间隔 ≥5s、不并行；已下载跳过；失败退避(5s/10s/20s)
          重试 ≤3 次；files/ 首选链接 404 自动切 cache/epub 备用
  * 清洗：截取 START/END OF THE PROJECT GUTENBERG EBOOK 之间正文；
          删除开头结尾英文元数据（Produced by/Title:/Author:/Release date/
          Language:/书名:/分隔线/纯 ASCII 行/尾部 End of Project Gutenberg）
  * 切分：复用 build_books 全部切分器（第X回/第X章/第X篇/第X則/卷/篇名/整本/
          易經/山海經/禮記/詩經305篇 等），繁体原样保留
  * 输出（适配移动后的新结构）：
      1) data/books/{key}.json           结构化正本
      2) library-index.json              分类书目索引
      3) 网站/_site_data/{书名}.json      阅读器格式 + 更新 books.json
      4) 网站/assets/data/books-data.json 统一分类数据源（合并 catalog.json 主书）

用法：
  python3 gutenberg_import.py              # 处理全部 BOOKS
  python3 gutenberg_import.py 詩經 麟兒報   # 仅处理指定书名
"""
import os
import re
import json
import datetime
import sys
import time
import subprocess
import urllib.request
import urllib.error
import shutil

BASE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(BASE, 'raw')
ROOT = os.path.dirname(os.path.dirname(BASE))          # 项目根
OUT_DIR = os.path.join(ROOT, 'data', 'books')          # /data/books/
os.makedirs(OUT_DIR, exist_ok=True)
SITE_DATA = os.path.join(ROOT, '网站', '_site_data')    # 网站/_site_data（数据已迁至此）
ASSETS = os.path.join(ROOT, '网站', 'assets', 'data')
os.makedirs(SITE_DATA, exist_ok=True)

# 古登堡 ebook 编号（书名 → #id），用于生成下载链接
EBOOK_ID = {
    '山水情': 25146, '山海經': 25288, '易經': 25501, '木蘭奇女傳': 23938,
    '野草': 25242, '中國小說史略': 25559, '朝花夕拾': 25271, '南腔北調集': 25346,
    '阿Q正傳': 25332, '彷徨': 24042, '狂人日記': 25297, '豆棚閒話': 25328,
    '戲中戲': 24225, '比目魚': 27119, '三字經': 12479, '施公案': 23825,
    '海公案': 54494, '燕丹子': 24068, '狄公案': 27686, '百家姓': 25196,
    '禮記': 24048, '綠牡丹': 27330, '詩經': 23873, '麟兒報': 27399,
}

START_RE = re.compile(r'START OF (?:THE|THIS) PROJECT GUTENBERG')
END_RE = re.compile(r'END OF (?:THE|THIS) PROJECT GUTENBERG')
RE_HUI = re.compile(r'^[ 　]*第([〇○零一二三四五六七八九十百]+)回(?=[ 　:：]|$)')
RE_GUA = re.compile(r'^第[ 　]*([〇○零一二三四五六七八九十百]+)[ 　]*卦$')
RE_BAO = re.compile(r'^《易經﹒([^》]+)》$')
CREDIT_START = re.compile(r'^(Produced by|Prepared by|Transcribed by|Posted by|This file|Copyright|End of|Project Gutenberg|Release date|Title:|Author:|Language:|书名[:：]|書名[:：]|\[eBook)', re.I)
RE_DASH_ONLY = re.compile(r'^[-—=·_~]+$')
RE_ASCII = re.compile(r"^[A-Za-z0-9 \t,.;:!?%$#@&*()\-–—_~/\\+=]+$")

DIGIT = {'〇': 0, '○': 0, '零': 0, '一': 1, '二': 2, '三': 3, '四': 4,
         '五': 5, '六': 6, '七': 7, '八': 8, '九': 9}


def cn_to_int(s):
    """支持 十四/一百 式传统中文数字，也支持 一○/一一/五二一 式位记数字
    （施公案/狄公案等古登堡文本混用：一○=10、一○○=100、五二一=521）。"""
    s = s.replace('〇', '○').replace('零', '○')
    if '十' in s or '百' in s:
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
    # 位记：一○=10、一一=11、五二一=521
    return int(''.join(str(DIGIT[c]) for c in s)) if s else 0


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
def split_hui(body, keep_prefix_title=None, cut_at=None, drop_prefix=False, title_next=False):
    """按「第X回」切分；可选开头补一章（keep_prefix_title=「序」），
    可选从 cut_at 行起截断（如木蘭的「附錄」），
    可选丢弃开头非回目行（drop_prefix，如山水情仅书题），
    title_next=True 时回目在标记行之后的下一个非空行（施公案/戲中戲）。"""
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
    # 去重：仅当两条同号标记之间无正文内容时才合并（保留后者）。
    # 施公案「第一三四回」在正文中重复出现两次（各有内容），须如实保留两章。
    deduped = []
    for m in marks:
        if deduped:
            prev_idx, prev_num, _ = deduped[-1]
            if prev_num == m[1] and not any(body[j].strip() for j in range(prev_idx + 1, m[0])):
                deduped[-1] = m
                continue
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
        tline = None
        if title_next:
            for j in range(idx + 1, end_idx):
                s = body[j].strip()
                if s:
                    title = title + ' ' + re.sub(r'[ \t]+', ' ', s)
                    tline = j
                    break
        raw = body[idx + 1:end_idx]
        if tline is not None:                       # 回目并入标题后，从正文剔除该行
            raw = raw[:tline - (idx + 1)] + raw[tline - (idx + 1) + 1:]
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


# ---------------------------------------------------------------
# 第二批新书切分器
# ---------------------------------------------------------------
RE_ZE = re.compile(r'^[ 　]*第([〇○零一二三四五六七八九十百]+)[ 　]*則[ 　]*(.*)$')
RE_ZE_MAL = re.compile(r'^[ 　]*第[ 　]{2,}([^ 　]{2,15})$')   # 豆棚閒話第十則缺「十則」，仅此一行
RE_LIJI = re.compile(r'^[ 　]+([^　]{2,8}第[〇○零一二三四五六七八九十百]+)$')


def split_ze(body, keep_prefix_title=None):
    """豆棚閒話：按「第X則」切分；开头 弁言 单独成章；
    第十則标记行缺「十則」（第      虎丘山賈清客聯盟）需特殊识别。"""
    marks = []
    for i, l in enumerate(body):
        m = RE_ZE.match(l)
        if m:
            marks.append((i, m.group(2).strip() or re.sub(r'[ 　]+', ' ', l).strip()))
            continue
        m = RE_ZE_MAL.match(l)
        if m:
            marks.append((i, m.group(1)))
    chapters = []
    if marks and marks[0][0] > 0:
        p = paragraphs(body[:marks[0][0]])
        if p:
            chapters.append({'title': keep_prefix_title or p[0][:20], 'content': '\n'.join(p)})
    for k, (idx, title) in enumerate(marks):
        end_idx = marks[k + 1][0] if k + 1 < len(marks) else len(body)
        raw = _trim(body[idx + 1:end_idx])
        chapters.append({'title': title, 'content': '\n'.join(paragraphs(raw))})
    return chapters


def split_juan(body, volumes):
    """燕丹子：按 卷上/卷中/卷下 切分。"""
    marks = []
    for i, l in enumerate(body):
        s = l.strip()
        if s in volumes:
            marks.append((i, s))
    chapters = []
    for k, (idx, name) in enumerate(marks):
        end_idx = marks[k + 1][0] if k + 1 < len(marks) else len(body)
        raw = _trim(body[idx + 1:end_idx])
        chapters.append({'title': name, 'content': '\n'.join(paragraphs(raw))})
    return chapters


def split_liji(body):
    """禮記：按「篇名第X」切分（曲禮上第一 … 喪服四制第四十九）。"""
    marks = []
    for i, l in enumerate(body):
        m = RE_LIJI.match(l)
        if m:
            marks.append((i, m.group(1)))
    chapters = []
    for k, (idx, title) in enumerate(marks):
        end_idx = marks[k + 1][0] if k + 1 < len(marks) else len(body)
        raw = _trim(body[idx + 1:end_idx])
        chapters.append({'title': title, 'content': '\n'.join(paragraphs(raw))})
    return chapters


RE_HUI_NO_DI = re.compile(r'^[ 　]*([〇○零一二三四五六七八九十百]+)回$')


def normalize_hui_no_di(body):
    """古登堡 #27330 綠牡丹：原文本「第二十一回」误作「二十一回」，统一为「第X回」。"""
    out = []
    for l in body:
        m = RE_HUI_NO_DI.match(l)
        if m:
            out.append('第' + m.group(1) + '回')
        else:
            out.append(l)
    return out


# ---------------------------------------------------------------
# 詩經（古登堡 #23873）：毛詩编号 1..305 通贯全書，诗头行如「1.  關睢」
# （个别编号行中有点号前空格，如「226 .  采綠」）。诗名跨風雅頌重出
# （柏舟/谷風/揚之水…），章題统一以「風雅頌卷名·詩名」消歧。
# 诗与诗之间嵌有 卷名行（周南/邶風/鹿鳴之什…）、笙詩註
# （南陔/白華/華黍/由庚/崇丘/由儀 +「笙詩無辭」）、編者註（說見小雅）
# 等无句读行——凡无 、。！？：； 的行一律剔除，僅保留诗句。
# ---------------------------------------------------------------
RE_SJ = re.compile(r'^(\d+)\s*\.\s*(\S.*?)\s*$')

SHIJING_REGIONS = [
    (1, 11, '周南'), (12, 25, '召南'), (26, 44, '邶風'), (45, 54, '鄘風'),
    (55, 64, '衛風'), (65, 74, '王風'), (75, 95, '鄭風'), (96, 106, '齊風'),
    (107, 113, '魏風'), (114, 125, '唐風'), (126, 135, '秦風'),
    (136, 145, '陳風'), (146, 149, '檜風'), (150, 153, '曹風'),
    (154, 160, '豳風'), (161, 234, '小雅'), (235, 265, '大雅'),
    (266, 296, '周頌'), (297, 300, '魯頌'), (301, 305, '商頌'),
]


def split_shijing(body):
    marks = []
    for i, l in enumerate(body):
        m = RE_SJ.match(l)
        if m:
            marks.append((i, int(m.group(1)), m.group(2)))
    chapters = []
    for k, (idx, num, name) in enumerate(marks):
        end_idx = marks[k + 1][0] if k + 1 < len(marks) else len(body)
        raw = []
        for l in body[idx + 1:end_idx]:
            s = l.strip()
            if not s:
                continue
            core = re.sub(r'[。！？；，、]+$', '', s)
            if core in ('笙詩無辭', '無辭', '南陔', '白華', '華黍', '由庚', '崇丘', '由儀'):
                continue          # 笙詩有目無辭註（可带句号）
            if not re.search(r'[、。！？：；]', s):
                continue          # 卷名行/編者註（說見小雅等）/空行
            raw.append(s)
        region = '詩'
        for a, b, rname in SHIJING_REGIONS:
            if a <= num <= b:
                region = rname
                break
        raw = _trim(raw)
        chapters.append({'title': '%s·%s' % (region, name),
                         'content': '\n'.join(paragraphs(raw))})
    return chapters



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
    # ---- 第二批新书（2026-09-01 入库） ----
    {
        'key': 'doupen-xianhua', 'book': '豆棚閒話', 'author': '艾衲居士',
        'category': '子部', 'subcategory': '小說家（話本）',
        'source': 'Project Gutenberg #25328', 'file': '豆棚閒話.txt',
        'split': 'ze', 'keep_prefix_title': '弁言',
    },
    {
        'key': 'xizhong-xi', 'book': '戲中戲', 'author': '李漁',
        'category': '子部', 'subcategory': '小說家',
        'source': 'Project Gutenberg #24225', 'file': '戲中戲.txt',
        'split': 'hui', 'title_next': True, 'drop_prefix': True,
    },
    {
        'key': 'bimu-yu', 'book': '比目魚', 'author': '李漁',
        'category': '子部', 'subcategory': '小說家',
        'source': 'Project Gutenberg #27119', 'file': '比目魚.txt',
        'split': 'hui', 'drop_prefix': True,
    },
    {
        'key': 'sanzijing', 'book': '三字經', 'author': '佚名',
        'category': '經部', 'subcategory': '蒙學',
        'source': 'Project Gutenberg #12479', 'file': '三字經.txt',
        'split': 'single', 'head_drop': 1,   # 删畸形书名行「三字經》」
    },
    {
        'key': 'shigongan', 'book': '施公案', 'author': '佚名',
        'category': '子部', 'subcategory': '小說家（公案）',
        'source': 'Project Gutenberg #23825', 'file': '施公案.txt',
        'split': 'hui', 'title_next': True, 'drop_prefix': True,
    },
    {
        'key': 'haigongan', 'book': '海公案', 'author': '佚名',
        'category': '子部', 'subcategory': '小說家（公案）',
        'source': 'Project Gutenberg #54494', 'file': '海公案.txt',
        'split': 'hui', 'drop_prefix': True,
    },
    {
        'key': 'yandanzi', 'book': '燕丹子', 'author': '佚名',
        'category': '子部', 'subcategory': '小說家',
        'source': 'Project Gutenberg #24068', 'file': '燕丹子.txt',
        'split': 'juan', 'head_drop': 1,      # 删书名行「燕丹子」
        'volumes': ['燕丹子卷上', '燕丹子卷中', '燕丹子卷下'],
    },
    {
        'key': 'digongan', 'book': '狄公案', 'author': '佚名',
        'category': '子部', 'subcategory': '小說家（公案）',
        'source': 'Project Gutenberg #27686', 'file': '狄公案.txt',
        'split': 'hui', 'drop_prefix': True,
    },
    {
        'key': 'baijiaxing', 'book': '百家姓', 'author': '佚名',
        'category': '經部', 'subcategory': '蒙學',
        'source': 'Project Gutenberg #25196', 'file': '百家姓.txt',
        'split': 'single', 'head_drop': 1,    # 删书名行「百家姓」
    },
    {
        'key': 'liji', 'book': '禮記', 'author': '佚名',
        'category': '經部', 'subcategory': '禮',
        'source': 'Project Gutenberg #24048', 'file': '禮記.txt',
        'split': 'liji',
    },
    # ---- 第三批新书（2026-09-01 入库） ----
    {
        'key': 'lv-mudan', 'book': '綠牡丹', 'author': '佚名',
        'category': '子部', 'subcategory': '小說家（英雄傳奇）',
        'source': 'Project Gutenberg #27330', 'file': '綠牡丹.txt',
        'split': 'hui', 'title_next': True, 'drop_prefix': True,
        'normalize_hui_no_di': True,   # 原文本「第二十一回」误作「二十一回」
    },
    # ---- 第四批新书（2026-09-01 入库） ----
    {
        'key': 'shijing', 'book': '詩經', 'author': '佚名',
        'category': '經部', 'subcategory': '詩',
        'source': 'Project Gutenberg #23873', 'file': '詩經.txt',
        'split': 'shijing',
    },
    {
        'key': 'lin-er-bao', 'book': '麟兒報', 'author': '佚名',
        'category': '子部', 'subcategory': '小說家（才子佳人）',
        'source': 'Project Gutenberg #27399', 'file': '麟兒報.txt',
        'split': 'hui', 'keep_prefix_title': '序',
        'hui_title_clean': True,   # 回目行全角空格塌缩为单空格
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
    'ze': split_ze,
    'juan': split_juan,
    'liji': split_liji,
    'shijing': split_shijing,
}


# ============================================================
# 一、古登堡下载（规范：间隔≥5s / 不并行 / 已下跳过 /
#     失败退避 5s·10s·20s ≤3 次 / files 404 自动切 cache/epub）
# ============================================================
UA = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) gutenberg-library/2.0'}


def book_urls(name):
    """files/{id}.txt → files/{id}-0.txt → cache/epub/pg{id}.txt 依序尝试"""
    i = EBOOK_ID.get(name)
    if not i:
        return []
    return [
        f'https://www.gutenberg.org/files/{i}/{i}.txt',
        f'https://www.gutenberg.org/files/{i}/{i}-0.txt',
        f'https://www.gutenberg.org/cache/epub/{i}/pg{i}.txt',
    ]


def fetch_url(url, retries=3):
    """单链接抓取；404 视为链接不可用（不占重试次数）；其余退避 5/10/20s。"""
    delay = 5
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=60) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            print(f'    HTTP {e.code}（第 {attempt}/{retries} 次）')
        except Exception as e:
            print(f'    网络错误 {e}（第 {attempt}/{retries} 次）')
        if attempt < retries:
            time.sleep(delay)
            delay *= 2
    return None


def download_book(name, raw_dir=RAW):
    """下载 {name}.txt → raw_dir；已存在且非空则跳过。返回 True/False。"""
    out = os.path.join(raw_dir, name + '.txt')
    if os.path.exists(out) and os.path.getsize(out) > 0:
        print(f"  · 已存在，跳过下载：{name}")
        return True
    urls = book_urls(name)
    if not urls:
        print(f"  ✗ 未知 ebook 编号：{name}（请补 EBOOK_ID）")
        return False
    print(f"  ⬇ 下载 {name}  #{EBOOK_ID[name]}")
    for i, url in enumerate(urls):
        data = fetch_url(url)
        if data:
            with open(out, 'wb') as f:
                f.write(data)
            tag = '首选' if i == 0 else '备用-0' if i == 1 else '备用-cache'
            print(f"    成功（{tag}: {url.split('/')[-1]}） {len(data)} 字节")
            return True
        print(f'    链接不可用: {url}')
    print(f"  ✗ 下载失败：{name}")
    return False



# ============================================================
# 二、注音 & 重难字词注释
#   分词：正向最大匹配 wordbank（优先 4→2 字，未匹配落单字）
#   拼音：pinyin-pro（node 子进程 pinyin_helper.js）；多音字候选记录于
#         wordbank.pinyin_notes / 由 wordbank 词条优先；否则取 pinyin-pro 默认
#   重难判定：字频表(常用字)之外 或 多音字 或 入声字
#   注释：书级唯一表 → data/books/{key}.json 顶层 "annotations"
#   待补：单字难字无词库注释 → 并入 wordbank_pending.json（全书/跨书去重）
# ============================================================
WB_DIR = BASE
WORD_BANK = os.path.join(WB_DIR, 'wordbank.json')
PENDING = os.path.join(WB_DIR, 'wordbank_pending.json')
COMMON_HANZI = os.path.join(WB_DIR, 'common_hanzi.json')
RUSHENG_HANZI = os.path.join(WB_DIR, 'rusheng_hanzi.json')
TRAD_SIMP_FILE = os.path.join(WB_DIR, 'trad_simp_map.json')
NODE_HELPER = os.path.join(WB_DIR, 'pinyin_helper.js')

CJK_RE = re.compile(r'[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]')


def _load_json(path, fallback):
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return fallback


def load_wordbank():
    """wordbank.json：忽略 _ 开头的说明键。"""
    d = _load_json(WORD_BANK, {}) or {}
    return {k: v for k, v in d.items() if not str(k).startswith('_')}


def load_common_chars():
    d = _load_json(COMMON_HANZI, {})
    chars = d.get('chars') if isinstance(d, dict) else d
    return set(chars or [])


def load_rusheng():
    d = _load_json(RUSHENG_HANZI, [])
    return set(d or [])


def pinyin_batch(tokens):
    """node pinyin_helper.js 批量注音。失败时返回 {}（不阻断流程）。"""
    if not tokens:
        return {}
    try:
        proc = subprocess.run(
            ['node', NODE_HELPER], input=json.dumps(list(tokens), ensure_ascii=False),
            capture_output=True, text=True, encoding='utf-8', timeout=120, cwd=WB_DIR)
        if proc.returncode != 0:
            print(f'    ⚠️ pinyin 助手异常: {proc.stderr.strip()[:120]}')
            return {}
        return json.loads(proc.stdout)
    except Exception as e:
        print(f'    ⚠️ pinyin 调用失败: {e}')
        return {}


def forward_max_split(text, vocab):
    """正向最大匹配：长度 4→2 的 wordbank 词优先；未匹配按单字切分。不切标点/非汉字。"""
    tokens = []
    i, n = 0, len(text)
    while i < n:
        if not CJK_RE.match(text[i]):
            i += 1
            continue
        hit = None
        for L in (4, 3, 2):
            if i + L <= n and text[i:i + L] in vocab:
                hit = text[i:i + L]
                break
        if hit:
            tokens.append(hit)
            i += len(hit)
        else:
            tokens.append(text[i])
            i += 1
    return tokens


def _char_difficult(ch, common, rusheng, pin):
    """单字重难判定：字频外（繁体先转简） / 多音 / 入声。"""
    simp = _trad_simp().get(ch, ch)
    if ch not in common and simp not in common:
        return True
    if ch in rusheng:
        return True
    if pin.get(ch, {}).get('multiple'):
        return True
    return False


_TRAD_CACHE = None


def _trad_simp():
    global _TRAD_CACHE
    if _TRAD_CACHE is None:
        _TRAD_CACHE = _load_json(TRAD_SIMP_FILE, {}) or {}
    return _TRAD_CACHE


def _iter_chapter_paragraphs(chapters):
    """data/books chapters 流 → (章节标题, 段落)。"""
    for ch in chapters:
        t = ch.get('title', '')
        for para in ch.get('content', '').split('\n'):
            yield t, para


def _iter_reader_paragraphs(sections):
    """阅读器 sections 流 → (篇目标题, 段落)。"""
    for s in sections or []:
        t = s.get('title', '')
        for para in (s.get('paragraphs') or []):
            yield t, para


def _build_annotations(first_src, wb, common, rusheng):
    """核心判定：拼音批处理 + wordbank/难字逻辑 → (annotations 列表, pending)。"""
    need_py = [t for t in first_src
               if not (wb.get(t) and wb.get(t).get('pinyin'))]
    pin = pinyin_batch(need_py)
    anns = {}
    pending = {}
    for tok, src in first_src.items():
        entry = wb.get(tok)
        if entry:
            pinyin = entry.get('pinyin') or pin.get(tok, {}).get('pinyin', '')
            if len(tok) == 1:
                difficult = bool(entry.get('is_difficult')) or _char_difficult(tok, common, rusheng, pin)
            else:
                difficult = bool(entry.get('is_difficult')) or any(
                    _char_difficult(c, common, rusheng, pin) for c in tok)
            anns[tok] = {
                'word': tok, 'pinyin': pinyin,
                'zh_cn': entry.get('zh_cn'), 'zh_tw': entry.get('zh_tw'),
                'en': entry.get('en'),
                'note': entry.get('note'),
                'is_difficult': difficult, 'src': src,
            }
            continue
        # 单字难字：常用且非多音且非入声 → 不标；其余标注并记待补
        if len(tok) == 1 and _char_difficult(tok, common, rusheng, pin):
            anns[tok] = {
                'word': tok, 'pinyin': pin.get(tok, {}).get('pinyin', ''),
                'zh_cn': None, 'zh_tw': None, 'en': None, 'note': None,
                'is_difficult': True, 'src': src,
            }
            pending[tok] = {'src': src, 'reason': '难字未录词库（缺 zh_cn/en/note）'}
        # 多字非词库 token 不直接产生（最大匹配只会吐出词库词或单字）
    return list(anns.values()), pending


def annotate_units(title, unit_paragraphs, reports):
    """通用全书注释：任意 (章节标题, 段落) 流。reports 以 title 为键。"""
    wb = load_wordbank()
    common = load_common_chars()
    rusheng = load_rusheng()
    first_src = {}
    for sec_title, para in unit_paragraphs:
        for tok in forward_max_split(para, wb):
            if tok not in first_src:
                first_src[tok] = sec_title
    anns, pending = _build_annotations(first_src, wb, common, rusheng)
    matched = sum(1 for t in first_src if t in wb)
    reports[title] = {
        'book': title,
        'unique_chars': sum(1 for t in first_src if len(t) == 1),
        'unique_words': sum(1 for t in first_src if len(t) > 1),
        'wordbank_hits': matched,
        'annotations': len(anns),
        'pending': len(pending),
    }
    return anns, pending


def annotate_book(cfg, chapters, reports):
    """data/books 书目（chapters 格式）适配器。返回 (annotations, pending)。"""
    return annotate_units(cfg['book'], _iter_chapter_paragraphs(chapters), reports)


def annotate_reader_book(title, sections, reports):
    """阅读器数据（sections.paragraphs 格式）适配器。返回 (annotations, pending)。"""
    return annotate_units(title, _iter_reader_paragraphs(sections), reports)


def merge_pending(book_key, pending):
    """跨书/全书去重写入 wordbank_pending.json。"""
    if not pending:
        return 0
    store = _load_json(PENDING, {}) or {}
    add = 0
    for tok, meta in pending.items():
        e = store.setdefault(tok, {'books': [], 'first_src': '', 'reason': meta.get('reason', '')})
        if book_key not in e['books']:
            e['books'].append(book_key)
        if not e.get('first_src'):
            e['first_src'] = meta.get('src', '')
        add += 1
    with open(PENDING, 'w', encoding='utf-8') as f:
        json.dump(store, f, ensure_ascii=False, indent=2)
    return add



# ============================================================
# 三、站点数据合并（适配「数据已迁至 网站/_site_data」的新结构）
#   1) data/books/* → 网站/_site_data/{书名}.json（阅读器格式）
#   2) 更新 网站/_site_data/books.json
#   3) 生成 网站/assets/data/books-data.json（合并 catalog.json 主书）
# ============================================================
CAT_KEY = {'經部': 'jing', '史部': 'shi', '子部': 'zi', '集部': 'ji',
           '近現代文學': 'ji'}
SUBCAT = {'近現代文學': 'modern'}
PIAN_KEYS = {'zhongguo-xiaoshuo-shilue', 'zhaohua-xishi', 'nanqiang-beidiao-ji',
             'yecao', 'panghuang'}


def books_index_entry(title, book):
    """books.json 只保留轻量目录字段（正文/注释在单书文件 _site_data/{書名}.json）。
    原因：Cloudflare Pages 单文件上限 25 MiB；全量书库聚合含正文+注释会超限。"""
    return {
        'title': title,
        'section_count': book.get('section_count', 0) or 0,
        'categories': book.get('categories', []) or [],
    }


def reader_label(key):
    if key == 'yijing':
        return None  # 特殊处理
    if key in ('shanshui-qing', 'mulan-qi-nv-zhuan', 'xizhong-xi', 'bimu-yu',
               'shigongan', 'haigongan', 'digongan', 'lv-mudan', 'lin-er-bao'):
        return '回目'
    if key in ('shanhaijing', 'yandanzi'):
        return '卷'
    if key == 'aq-zhengzhuan':
        return '章'
    if key in ('doupen-xianhua',):
        return '則'
    if key in ('liji', 'shijing'):
        return '篇'
    if key in PIAN_KEYS:
        return '篇目'
    return '全書'


def to_reader(key, data):
    """data/books 条目 → 阅读器 book 对象（章节字段；忽略 annotations 等扩展）。"""
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


# 朝代与简介（新书 + catalog 主书共用）
DYN = {
    '易經': '先秦（商周）', '山海經': '先秦', '山水情': '清初', '木蘭奇女傳': '清',
    '野草': '1927', '中國小說史略': '1923', '朝花夕拾': '1928', '南腔北調集': '1934',
    '阿Q正傳': '1921', '彷徨': '1926', '狂人日記': '1918',
    '豆棚閒話': '清初', '戲中戲': '清', '比目魚': '清', '三字經': '宋',
    '施公案': '清', '海公案': '明', '燕丹子': '先秦', '狄公案': '清',
    '百家姓': '宋', '禮記': '先秦至漢', '綠牡丹': '清（道光年間）',
    '詩經': '西周至春秋', '麟兒報': '清',
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
    '豆棚閒話': '清初話本小說集，十二則閒話借豆棚聚談起興，以古諷今、嬉笑怒罵。',
    '戲中戲': '李漁所作：譚楚玉與劉藐姑因戲結緣，歷盡磨難終成眷屬的故事。',
    '比目魚': '李漁代表作：譚楚玉、劉藐姑以死殉情、死後化作比目魚的傳奇故事。',
    '三字經': '中國古代影響最大的蒙學讀物，三字一句，涵蓋倫理、歷史與常識。',
    '施公案': '清代公案俠義小說，敘施世綸審案斷獄、與黃天霸等俠客懲惡扶善。',
    '海公案': '明代公案小說，演海瑞為官斷案、剛正不阿、懲奸除惡的傳奇故事。',
    '燕丹子': '先秦雜史小說，記燕太子丹使荊軻刺秦的故事，被譽為武俠小說之祖。',
    '狄公案': '清代公案小說，敘狄仁傑任昌平縣令時明察秋毫、屢破奇案。',
    '百家姓': '中國古代蒙學讀物，四字一句，收錄常見姓氏數百個。',
    '禮記': '儒家經典之一，記先秦禮制與禮學思想，內含《大學》《中庸》等名篇。',
    '綠牡丹': '清代武俠英雄傳奇小說：敘駱宏勛、花振芳、鮑自安等豪傑於武周之世懲奸除惡、扶唐復國，恩怨江湖、快意恩仇。',
    '詩經': '中國最早的詩歌總集，收西周初年至春秋中葉詩歌三百零五篇，分風、雅、頌，儒家「五經」之一。',
    '麟兒報': '清代才子佳人小說：廉小村雪中濟丐仙得吉壤，生子廉清，與幸尚書之女歷盡波折終成眷屬，寓善惡果報之勸。',
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


def backup_site_data():
    """跑合并前备份 网站/_site_data → 文本/新书/backups/_site_data_<时间戳>。"""
    if not os.path.isdir(SITE_DATA):
        return None
    ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    dst = os.path.join(WB_DIR, 'backups', '_site_data_' + ts)
    shutil.copytree(SITE_DATA, dst)
    print(f'  💾 已备份 {os.path.relpath(SITE_DATA, ROOT)} → {os.path.relpath(dst, ROOT)}')
    return dst


def merge_to_site():
    """按 library-index 重写阅读器单书文件 + books.json + books-data.json（含 catalog 主书）。"""
    lib_index = json.load(open(os.path.join(ROOT, 'library-index.json'), encoding='utf-8'))
    os.makedirs(SITE_DATA, exist_ok=True)
    books_json_path = os.path.join(SITE_DATA, 'books.json')
    books_index = json.load(open(books_json_path, encoding='utf-8'))

    merged_books = []
    done = set()
    for cat_grp in lib_index['categories']:
        cat_name = cat_grp['name']
        ckey = CAT_KEY[cat_name]
        sub = SUBCAT.get(cat_name, '')
        for entry in cat_grp['books']:
            key = entry['key']
            title = entry['book']
            raw = json.load(open(os.path.join(OUT_DIR, key + '.json'), encoding='utf-8'))
            reader = to_reader(key, raw)
            reader['annotations'] = raw.get('annotations', [])   # 统一前端口径：24本注释镜像到 _site_data
            with open(os.path.join(SITE_DATA, title + '.json'), 'w', encoding='utf-8') as f:
                json.dump(reader, f, ensure_ascii=False, indent=2)
            books_index[title] = books_index_entry(title, reader)   # books.json 仅存轻量目录
            merged_books.append({
                'id': key, 'title': title, 'author': raw.get('author', '佚名'),
                'category': ckey, 'subcategory': sub, 'dynasty': DYN.get(title, ''),
                'description': DESC.get(title, raw.get('subcategory', '')),
                'sections': reader['section_count'],
                'cover': '',
            })
            done.add(title)
            print(f"  ✅ 合并 {title}（{cat_name} → {ckey}{'·modern' if sub else ''}）{reader['section_count']} 篇")

    # catalog.json 的 8 本主书并入统一数据源
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

    os.makedirs(ASSETS, exist_ok=True)
    out = {
        'title': '一堆古书 · 统一分类数据源',
        'updated': datetime.date.today().isoformat(),
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
    with open(books_json_path, 'w', encoding='utf-8') as f:
        json.dump(books_index, f, ensure_ascii=False, indent=2)
    print(f"✅ 共 {len(merged_books)} 本进入统一数据源 → {os.path.relpath(out_path, ROOT)}")


def _build_one(cfg):
    """清洗(英文头尾标记/元数据)→切分 → 返回 out dict（未含 annotations）。"""
    lines = open(os.path.join(RAW, cfg['file']), encoding='utf-8-sig').read().split('\n')
    body = extract_body(lines)
    if cfg.get('head_drop'):
        body = body[cfg['head_drop']:]     # 删开头畸形书名行（三字經》/百家姓/燕丹子）
    if cfg.get('normalize_hui_no_di'):
        body = normalize_hui_no_di(body)   # 綠牡丹「二十一回」→「第二十一回」
    splitter = SPLITTERS[cfg['split']]
    if cfg['split'] == 'hui':
        chapters = splitter(body, cfg.get('keep_prefix_title'), cfg.get('cut_at'),
                            cfg.get('drop_prefix', False), cfg.get('title_next', False))
    elif cfg['split'] in ('shanhaijing', 'juan'):
        chapters = splitter(body, cfg['volumes'])
    elif cfg['split'] in ('yecao', 'pieces'):
        chapters = splitter(body, cfg['pieces'])
    elif cfg['split'] == 'ze':
        chapters = splitter(body, cfg.get('keep_prefix_title'))
    elif cfg['split'] == 'single':
        chapters = splitter(body, cfg['book'])
    else:
        chapters = splitter(body)
    if cfg.get('hui_title_clean'):
        chapters = [
            {'title': re.sub(r'[ 　]+', ' ', c['title']).strip(), 'content': c['content']}
            for c in chapters
        ]
    return {
        'book': cfg['book'], 'author': cfg['author'],
        'category': cfg['category'], 'subcategory': cfg['subcategory'],
        'chapters': chapters,
    }


def _index_entry(cfg, out):
    return {
        'key': cfg['key'], 'book': cfg['book'], 'author': cfg['author'],
        'subcategory': cfg['subcategory'], 'chapters': len(out['chapters']),
        'source': cfg['source'],
        'path': os.path.join('data', 'books', cfg['key'] + '.json'),
    }


# 目录主书（非古登堡新书流水线，正文在 网站/_site_data/{書名}.json）
CATALOG_TITLES = ['史記', '漢書', '三國志', '三國演義', '水滸傳',
                  '西遊記', '紅樓夢', '古文觀止']


def annotate_catalog_books():
    """为 8 本目录主书生成注释并写回 _site_data 单书文件 + books.json 聚合。"""
    os.makedirs(SITE_DATA, exist_ok=True)
    books_json_path = os.path.join(SITE_DATA, 'books.json')
    books_index = json.load(open(books_json_path, encoding='utf-8'))
    reports = {}
    changed = False
    for title in CATALOG_TITLES:
        p = os.path.join(SITE_DATA, title + '.json')
        if not os.path.exists(p):
            print(f'  ⚠️ 缺文件，跳过：{p}')
            continue
        data = json.load(open(p, encoding='utf-8'))
        anns, pending = annotate_reader_book(title, data.get('sections', []), reports)
        data['annotations'] = anns
        with open(p, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        if title in books_index:
            books_index[title] = books_index_entry(title, data)  # books.json 仅存轻量目录
        merge_pending(title, pending)
        changed = True
        print(f"  ✅ {title} → annotations {len(anns)} 条" +
              (f"（待补 +{len(pending)}）" if pending else ''))
    if changed:
        with open(books_json_path, 'w', encoding='utf-8') as f:
            json.dump(books_index, f, ensure_ascii=False, indent=2)
    if reports:
        print('\n==== 目录主书匹配报告 ====')
        for key, r in reports.items():
            print(f"  {r['book']}: 唯一字 {r['unique_chars']} / 词 {r['unique_words']} | "
                  f"词库命中 {r['wordbank_hits']} | 注释 {r['annotations']} 条 | 待补 {r['pending']}")


def main():
    flags = {a for a in sys.argv[1:] if a.startswith('--')}
    names = [a for a in sys.argv[1:] if not a.startswith('--')]
    do_annotate = '--no-annotate' not in flags
    do_merge = '--no-merge' not in flags
    do_download = '--no-download' not in flags
    do_catalog = '--catalog' in flags
    if names:
        targets = names
    else:
        targets = [] if do_catalog else [cfg['book'] for cfg in BOOKS]

    reports = {}
    built = {}

    # 0) 补齐缺失的 raw（顺序下载、间隔 ≥5s、不并行、已存在跳过）
    if do_download:
        last = None
        for cfg in BOOKS:
            if cfg['book'] not in targets:
                continue
            rp = os.path.join(RAW, cfg['file'])
            if os.path.exists(rp) and os.path.getsize(rp) > 0:
                continue
            if last:
                gap = 5 - (time.time() - last)
                if gap > 0:
                    print(f'  ⏳ 间隔 {gap:.0f}s…')
                    time.sleep(gap)
            download_book(cfg['book'])
            last = time.time()

    # 1) 目标书：清洗→切分→注音注释→写 data/books/{key}.json
    for cfg in BOOKS:
        if cfg['book'] not in targets:
            continue
        rp = os.path.join(RAW, cfg['file'])
        if not (os.path.exists(rp) and os.path.getsize(rp) > 0):
            print(f"  ✗ 缺 raw：{cfg['book']}（请联网下载或补齐 raw/{cfg['file']}）")
            continue
        out = _build_one(cfg)
        chapters = out['chapters']
        ann_note = ''
        if do_annotate:
            anns, pending = annotate_book(cfg, chapters, reports)
            out['annotations'] = anns
            n_pend = merge_pending(cfg['key'], pending)
            ann_note = f" | 注释 {len(anns)} 条" + (f"（待补 +{n_pend}）" if n_pend else '')
        p = os.path.join(OUT_DIR, cfg['key'] + '.json')
        with open(p, 'w', encoding='utf-8') as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
        total = sum(len(c['content']) for c in chapters)
        print(f"✅ {cfg['book']} ({cfg['key']}) → {os.path.relpath(p, ROOT)}")
        print(f"   {len(chapters)} 章 | 约 {total:,} 字 | 首章: {chapters[0]['title'][:30]} | 末章: {chapters[-1]['title'][:30]}{ann_note}")
        built[cfg['key']] = out

    # 2) library-index.json（全量 BOOKS；本次未处理的从 data/books 磁盘读）
    index_cats = {}
    for cfg in BOOKS:
        out = built.get(cfg['key'])
        if out is None:
            disk = os.path.join(OUT_DIR, cfg['key'] + '.json')
            if not os.path.exists(disk):
                continue
            out = json.load(open(disk, encoding='utf-8'))
        index_cats.setdefault(cfg['category'], []).append(_index_entry(cfg, out))
    cat_order = ['經部', '史部', '子部', '集部', '近現代文學']
    cats = [{'name': c, 'books': index_cats.get(c, [])} for c in cat_order]
    index = {
        'title': '一堆古书 · 数据书目索引',
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

    # 3) 站点合并 / 目录主书注音（先备份 _site_data）
    if do_merge or do_catalog:
        backup_site_data()
    if do_merge:
        merge_to_site()
    if do_catalog:
        annotate_catalog_books()

    # 4) 每本书匹配报告
    if reports:
        print('\n==== 匹配报告 ====')
        for key, r in reports.items():
            print(f"  {r['book']}: 唯一字 {r['unique_chars']} / 词 {r['unique_words']} | "
                  f"词库命中 {r['wordbank_hits']} | 注释 {r['annotations']} 条 | 待补 {r['pending']}")



if __name__ == '__main__':
    main()
