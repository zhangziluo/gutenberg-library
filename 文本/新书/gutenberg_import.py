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

两种模式：
  ① 精简模式（默认切分 + 自动元数据，一键批量）：
       python3 gutenberg_import.py --ids 新书.txt     # 每行一个古登堡编号
       可选：--split auto|hui|zhang|…  --category 子部  --subcategory 古籍（自动导入）
       标题/作者自动取自 本地(EBOOK_ID/raw 头部) → 古登堡 API；书号对应的
       导入配置（key 为 pg{编号}）持久化于 quick_books.json，后续全量运行一并入库。
       书名非中文的编号会跳过（防止英文/罗马化书名进入中文书库）。
       失败（无中文书名/下载失败/缺原文/切分为空/处理异常等）单独记入
       项目根 logs/gutenberg_import.log；单本失败只跳过、不中断整批，
       运行结束按失败编号去重打印汇总（重复/已入库视为跳过、不计失败）。
  ② 精细模式（现有手动配置，需调切分参数时用）：
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
    # ---- 第五批新书（2026-09-08 批量入库） ----
    '天豹圖': 26904, '梁公九諫': 26886, '長恨歌': 25352, '李娃傳': 24051,
    '玉樓春': 25422, '引鳳蕭': 26921, '今古奇觀': 24230, '後西遊記': 27332,
    # ---- 第六批新书（2026-09-08 批量入库） ----
    '飛跎全傳': 27331, '佛說四十二章經': 23585, '洛神賦': 24041, '晁氏儒言': 43014,
    '水滸後傳': 25217, '幼學瓊林': 52269, '治世餘聞': 26932, '琵琶記': 25246,
    '雪月梅傳': 26739, '龍川詞': 26873,
    # ---- 第七批新书（2026-09-08 批量入库） ----
    '隋唐演義': 23835, '論語': 23839, '滬語開路': 62791, '白圭志': 27023,
    '孟子字義疏證': 25360, '安樂集': 24106, '鄧析子': 7215, '醉醒石': 24027,
    '唐鍾馗平鬼傳': 27329, '春秋繁露': 25385,
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
RE_JIAN = re.compile(r'^[ 　]*第([〇○零一二三四五六七八九十百]+)[ 　]*諫[ 　]*(.*)$')   # 梁公九諫：第X諫
RE_JUAN_N = re.compile(r'^[ 　]*第([〇○零一二三四五六七八九十百]+)[ 　]*卷[ 　]*$')     # 今古奇觀/治世餘聞：第X卷
RE_CHU = re.compile(r'^[ 　]*第([〇○零一二三四五六七八九十百]+)[ 　]*出(?=[ 　:：]|$)')   # 琵琶記：第X出
RE_LUNYU = re.compile(r'^[ 　]*([^　]{1,8})第([〇○零一二三四五六七八九十百]+)$')          # 論語：學而第一
RE_JUAN_XC = re.compile(r'^(.{1,12})卷(上|中|下)[ 　]*$')                                # 卷上/卷中/卷下
RE_FANLU = re.compile(r'^[ 　]+([^　]{1,12})第([〇○零一二三四五六七八九十百]+)[ 　]*$')   # 春秋繁露正文篇题（须缩进）
RE_JQ_CN = re.compile(r'^[ 　]*卷第([〇○零一二三四五六七八九十百]+)[ 　]*$')              # 春秋繁露：卷第一…
RE_JQ_QUE = re.compile(r'^[ 　]*第([〇○零一二三四五六七八九十百]+)[〔\[(]?闕[〕\]）)]?[ 　]*$')  # 春秋繁露：第X[闕]
RE_PAGE_REF = re.compile(r'^【(全書|Ewell)[^】]*】(?:【Ewell[^】]*】)*[ 　]*$')            # 疏證：页码标记行
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


def split_jian(body, keep_prefix_title=None):
    """梁公九諫：按「第X諫」切分；开头「序」单独成章。"""
    marks = []
    for i, l in enumerate(body):
        m = RE_JIAN.match(l)
        if m:
            title = m.group(2).strip() or re.sub(r'[ 　]+', ' ', l).strip()
            marks.append((i, title))
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


def split_juans(body):
    """今古奇觀：按「第X卷」切分；卷名（故事名）在标记行的下一非空行。"""
    marks = []
    for i, l in enumerate(body):
        m = RE_JUAN_N.match(l)
        if m:
            marks.append((i, cn_to_int(m.group(1)), l))
    marks = sorted(set(marks))
    chapters = []
    for k, (idx, num, line) in enumerate(marks):
        end_idx = marks[k + 1][0] if k + 1 < len(marks) else len(body)
        title = re.sub(r'[ 　]+', ' ', line).strip()
        tline = None
        for j in range(idx + 1, end_idx):
            s = body[j].strip()
            if s:
                title = title + ' ' + re.sub(r'[ 　]+', ' ', s)
                tline = j
                break
        raw = body[idx + 1:end_idx]
        if tline is not None:
            raw = raw[:tline - (idx + 1)] + raw[tline - (idx + 1) + 1:]
        raw = _trim(raw)
        chapters.append({'title': title, 'content': '\n'.join(paragraphs(raw))})
    return chapters


def split_chu(body, keep_prefix_title=None, cut_at=None, drop_prefix=False, title_next=False):
    """琵琶記：按「第X出」切分（出目同行），与 split_hui 同构（正则换「出」）。"""
    if cut_at:
        for i, l in enumerate(body):
            if l.strip().startswith(cut_at):
                body = body[:i]
                break
    marks = []
    for i, l in enumerate(body):
        m = RE_CHU.match(l)
        if m:
            marks.append((i, cn_to_int(m.group(1)), l))
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
    if marks and marks[0][0] > 0:
        p = paragraphs(body[:marks[0][0]])
        if p and not drop_prefix:
            chapters.append({'title': keep_prefix_title or p[0][:20], 'content': '\n'.join(p)})
    for k, (idx, num, line) in enumerate(marks):
        end_idx = marks[k + 1][0] if k + 1 < len(marks) else len(body)
        title = re.sub(r'[ \t]+', ' ', line).strip()
        raw = _trim(body[idx + 1:end_idx])
        chapters.append({'title': title, 'content': '\n'.join(paragraphs(raw))})
    return chapters


def split_juan_num(body):
    """治世餘聞：按「第X卷」切分；卷号行本身作标题（无子标题行）。"""
    marks = []
    for i, l in enumerate(body):
        m = RE_JUAN_N.match(l)
        if m:
            marks.append((i, re.sub(r'[ 　]+', ' ', l).strip()))
    chapters = []
    for k, (idx, title) in enumerate(marks):
        end_idx = marks[k + 1][0] if k + 1 < len(marks) else len(body)
        raw = _trim(body[idx + 1:end_idx])
        chapters.append({'title': title, 'content': '\n'.join(paragraphs(raw))})
    return chapters


# 幼學瓊林（#52269）：卷内按 33 篇名切分（天文/地輿/歲時…花木）
YXQL_PIAN = ['天文', '地輿', '歲時', '朝廷', '文臣', '武職',
             '祖孫父子', '兄弟', '夫婦', '叔侄', '師生', '朋友賓主',
             '婚姻', '女子', '外戚', '老幼壽誕', '身體', '衣服',
             '人事', '飲食', '宮室', '器用', '珍寶', '貧富',
             '疾病死喪', '文事', '科第', '制作', '技藝', '訟獄',
             '釋道鬼神', '鳥獸', '花木']


def split_yxql(body, pieces):
    """幼學瓊林：按 33 篇名切分；「卷一~卷四」卷号行不产生章节并自内容剔除。"""
    marks = []
    for i, l in enumerate(body):
        s = l.strip()
        if RE_JUAN_N.match(s):
            continue
        if s in pieces:
            marks.append((i, s))
    bound = set(pieces)
    chapters = []
    for k, (idx, title) in enumerate(marks):
        end_idx = marks[k + 1][0] if k + 1 < len(marks) else len(body)
        raw = body[idx + 1:end_idx]
        raw = [l for l in raw if not RE_JUAN_N.match(l.strip())]
        raw = [l for l in raw if l.strip() not in bound]
        raw = _trim(raw)
        chapters.append({'title': title, 'content': '\n'.join(paragraphs(raw))})
    return chapters


def split_lunyu(body):
    """論語：按「學而第一…堯曰第二十」篇题切分（每篇下为编号章句）。"""
    marks = []
    for i, l in enumerate(body):
        m = RE_LUNYU.match(l)
        if m:
            marks.append((i, re.sub(r'[ 　]+', ' ', l).strip()))
    chapters = []
    for k, (idx, title) in enumerate(marks):
        end_idx = marks[k + 1][0] if k + 1 < len(marks) else len(body)
        raw = _trim(body[idx + 1:end_idx])
        chapters.append({'title': title, 'content': '\n'.join(paragraphs(raw))})
    return chapters


def split_juan_sc(body, keep_prefix_title=None, drop_prefix=False):
    """孟子字義疏證/安樂集：按「卷上/卷中/卷下」切分（前缀可单独成章）；
    同一卷名重复出现（古籍排版页眉/页脚）只取首次作边界，正文剔除独立卷名行与页码标记行。"""
    marks = []
    seen = set()
    for i, l in enumerate(body):
        m = RE_JUAN_XC.match(l)
        if m:
            name = m.group(2)
            if name in seen:
                continue
            seen.add(name)
            marks.append((i, re.sub(r'[ 　]+', ' ', l).strip()))
    chapters = []
    if marks and marks[0][0] > 0:
        pre = [re.sub(r'【(?:全書|Ewell)[^】]*】', '', l)
               for l in body[:marks[0][0]]
               if not (RE_PAGE_REF.match(l.strip()) or RE_DASH_ONLY.match(l.strip())
                       or RE_JUAN_XC.match(l.strip()))]
        if keep_prefix_title and pre and pre[0].strip() == keep_prefix_title:
            pre = pre[1:]
        p = paragraphs(pre)
        if p and not drop_prefix:
            chapters.append({'title': keep_prefix_title or p[0][:20], 'content': '\n'.join(p)})
    for k, (idx, title) in enumerate(marks):
        end_idx = marks[k + 1][0] if k + 1 < len(marks) else len(body)
        raw = body[idx + 1:end_idx]
        raw = [re.sub(r'【(?:全書|Ewell)[^】]*】', '', l) for l in raw]
        raw = [l for l in raw if not (RE_PAGE_REF.match(l.strip()) or RE_DASH_ONLY.match(l.strip())
                                      or RE_JUAN_XC.match(l.strip()))]
        raw = _trim(raw)
        chapters.append({'title': title, 'content': '\n'.join(paragraphs(raw))})
    return chapters


def split_fanlu(body):
    """春秋繁露：按正文缩进篇题「楚莊王第一…天道施第八十二」切 82 篇；
    跳过开篇目录（未缩进行），剔除「卷第一…卷十七」与「第X[闕]」行。"""
    marks = []
    for i, l in enumerate(body):
        m = RE_FANLU.match(l)
        if m and m.group(1) != '卷':
            marks.append((i, re.sub(r'[ 　]+', ' ', l).strip()))
    chapters = []
    for k, (idx, title) in enumerate(marks):
        end_idx = marks[k + 1][0] if k + 1 < len(marks) else len(body)
        raw = body[idx + 1:end_idx]
        raw = [l for l in raw if not (RE_JQ_CN.match(l.strip()) or RE_JQ_QUE.match(l.strip())
                                      or RE_FANLU.match(l) and RE_FANLU.match(l).group(1) == '卷')]
        raw = _trim(raw)
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


# 李娃傳（#24051）等个别古登堡中文本使用 FE5x 小型标点（﹔﹕﹖﹗﹐），
# 段落聚合依赖全角句读（。！？」：；），故归一为全角。
FE_PUNCT = {'﹔': '；', '﹕': '：', '﹖': '？', '﹗': '！', '﹐': '，', '﹑': '、',
            '﹒': '。', '﹞': '」', '﹝': '「'}


def normalize_fe_punct(body):
    return [''.join(FE_PUNCT.get(c, c) for c in l) for l in body]


def drop_until_heading(body, heading):
    """天豹圖/梁公九諫：正文以「书名/作者」行开头，书名下方才是「序」标题；
    丢弃到「序」标题为止，使 keep_prefix_title 前缀成章时不含书名作者残留。"""
    for k, l in enumerate(body):
        if l.strip() == heading or l.strip().startswith(heading + ' '):
            return body[k:]
    return body


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
    # ---- 第五批新书（2026-09-08 批量入库） ----
    {
        'key': 'tianbao-tu', 'book': '天豹圖', 'author': '佚名',
        'category': '子部', 'subcategory': '小說家（英雄傳奇）',
        'source': 'Project Gutenberg #26904', 'file': '天豹圖.txt',
        'split': 'hui', 'keep_prefix_title': '序', 'drop_until': '序',
        'hui_title_clean': True,
    },
    {
        'key': 'lianggong-jiujian', 'book': '梁公九諫', 'author': '佚名',
        'category': '子部', 'subcategory': '小說家（話本）',
        'source': 'Project Gutenberg #26886', 'file': '梁公九諫.txt',
        'split': 'jian', 'keep_prefix_title': '序', 'drop_until': '序',
    },
    {
        'key': 'changhen-ge', 'book': '長恨歌', 'author': '白居易',
        'category': '集部', 'subcategory': '詩',
        'source': 'Project Gutenberg #25352', 'file': '長恨歌.txt',
        'split': 'single', 'head_drop': 1,   # 删书名/作者行「長恨歌    白居易」
    },
    {
        'key': 'liwa-zhuan', 'book': '李娃傳', 'author': '白行簡',
        'category': '子部', 'subcategory': '小說家（傳奇）',
        'source': 'Project Gutenberg #24051', 'file': '李娃傳.txt',
        'split': 'single',
        'normalize_fe_punct': True,   # 原文本用 FE5x 小型标点（﹔﹕﹖﹗），归一并保证段落
    },
    {
        'key': 'yulou-chun', 'book': '玉樓春', 'author': '白雲道人',
        'category': '子部', 'subcategory': '小說家（才子佳人）',
        'source': 'Project Gutenberg #25422', 'file': '玉樓春.txt',
        'split': 'hui', 'drop_prefix': True, 'hui_title_clean': True,
    },
    {
        'key': 'yinfeng-xiao', 'book': '引鳳蕭', 'author': '半雲友',
        'category': '子部', 'subcategory': '小說家（才子佳人）',
        'source': 'Project Gutenberg #26921', 'file': '引鳳蕭.txt',
        'split': 'hui', 'drop_prefix': True, 'hui_title_clean': True,
    },
    {
        'key': 'jingu-qiguan', 'book': '今古奇觀', 'author': '抱甕老人',
        'category': '子部', 'subcategory': '小說家（話本）',
        'source': 'Project Gutenberg #24230', 'file': '今古奇觀.txt',
        'split': 'juans', 'hui_title_clean': True,
    },
    {
        'key': 'hou-xiyouji', 'book': '後西遊記', 'author': '佚名',
        'category': '子部', 'subcategory': '小說家（神魔）',
        'source': 'Project Gutenberg #27332', 'file': '後西遊記.txt',
        'split': 'hui', 'title_next': True, 'drop_prefix': True,
        'hui_title_clean': True,
    },
    # ---- 第六批新书（2026-09-08 批量入库） ----
    {
        'key': 'feituo-quanzhuan', 'book': '飛跎全傳', 'author': '鄒必顯',
        'category': '子部', 'subcategory': '小說家（神魔）',
        'source': 'Project Gutenberg #27331', 'file': '飛跎全傳.txt',
        'split': 'hui', 'title_next': True, 'keep_prefix_title': '序',
        'drop_until': '序', 'hui_title_clean': True,
    },
    {
        'key': 'foshuo-sishierzhang-jing', 'book': '佛說四十二章經', 'author': '佚名',
        'category': '子部', 'subcategory': '釋家',
        'source': 'Project Gutenberg #23585', 'file': '佛說四十二章經.txt',
        'split': 'single', 'head_drop': 3,   # 删书名行/空行 + 「後漢摩騰、竺法蘭共譯」
    },
    {
        'key': 'luoshen-fu', 'book': '洛神賦', 'author': '曹植',
        'category': '集部', 'subcategory': '賦',
        'source': 'Project Gutenberg #24041', 'file': '洛神賦.txt',
        'split': 'single', 'head_drop': 3,   # 删书名行/空行 + 「作者：曹植」
    },
    {
        'key': 'chaoshi-ruyan', 'book': '晁氏儒言', 'author': '晁說之',
        'category': '子部', 'subcategory': '儒家',
        'source': 'Project Gutenberg #43014', 'file': '晁氏儒言.txt',
        'split': 'single', 'head_drop': 1,   # 删书名行「晁氏儒言」
    },
    {
        'key': 'shuihu-houzhuan', 'book': '水滸後傳', 'author': '陳忱',
        'category': '子部', 'subcategory': '小說家（英雄傳奇）',
        'source': 'Project Gutenberg #25217', 'file': '水滸後傳.txt',
        'split': 'hui', 'hui_title_clean': True,
    },
    {
        'key': 'youxue-qionglin', 'book': '幼學瓊林', 'author': '程允升',
        'category': '經部', 'subcategory': '蒙學',
        'source': 'Project Gutenberg #52269', 'file': '幼學瓊林.txt',
        'split': 'yxql', 'pieces': YXQL_PIAN,
    },
    {
        'key': 'zhishi-yuwen', 'book': '治世餘聞', 'author': '陳洪謨',
        'category': '史部', 'subcategory': '雜史',
        'source': 'Project Gutenberg #26932', 'file': '治世餘聞.txt',
        'split': 'juan_num',
    },
    {
        'key': 'pipa-ji', 'book': '琵琶記', 'author': '高明',
        'category': '集部', 'subcategory': '戲曲',
        'source': 'Project Gutenberg #25246', 'file': '琵琶記.txt',
        'split': 'chu', 'drop_prefix': True, 'hui_title_clean': True,
    },
    {
        'key': 'xueyuemei-zhuan', 'book': '雪月梅傳', 'author': '陳朗',
        'category': '子部', 'subcategory': '小說家（才子佳人）',
        'source': 'Project Gutenberg #26739', 'file': '雪月梅傳.txt',
        'split': 'hui', 'keep_prefix_title': '自序',
        'drop_until': '自序', 'hui_title_clean': True,
    },
    {
        'key': 'longchuan-ci', 'book': '龍川詞', 'author': '陳亮',
        'category': '集部', 'subcategory': '詞',
        'source': 'Project Gutenberg #26873', 'file': '龍川詞.txt',
        'split': 'single', 'head_drop': 1,   # 删作者行「陳亮 著」
    },
    # ---- 第七批新书（2026-09-08 批量入库） ----
    {
        'key': 'suitang-yanyi', 'book': '隋唐演義', 'author': '褚人穫',
        'category': '子部', 'subcategory': '小說家（歷史演義）',
        'source': 'Project Gutenberg #23835', 'file': '隋唐演義.txt',
        'split': 'hui', 'drop_prefix': True, 'hui_title_clean': True,
    },
    {
        'key': 'lunyu', 'book': '論語', 'author': '孔子',
        'category': '經部', 'subcategory': '四書',
        'source': 'Project Gutenberg #23839', 'file': '論語.txt',
        'split': 'lunyu', 'head_drop': 1,   # 删顶部误置的重复章句行
    },
    {
        'key': 'huyu-kailu', 'book': '滬語開路', 'author': '柯羅福特、羅林森',
        'category': '近現代文學', 'subcategory': '語言讀本',
        'source': 'Project Gutenberg #62791', 'file': '滬語開路.txt',
        'split': 'single', 'head_drop': 68,   # 跳封面页与英文引言，正文自「Exercise 1.」起
    },
    {
        'key': 'baigui-zhi', 'book': '白圭志', 'author': '崔象川',
        'category': '子部', 'subcategory': '小說家（才子佳人）',
        'source': 'Project Gutenberg #27023', 'file': '白圭志.txt',
        'split': 'hui', 'drop_prefix': True, 'hui_title_clean': True,
    },
    {
        'key': 'mengzi-ziyi-shuzheng', 'book': '孟子字義疏證', 'author': '戴震',
        'category': '經部', 'subcategory': '四書',
        'source': 'Project Gutenberg #25360', 'file': '孟子字義疏證.txt',
        'split': 'juan_sc', 'keep_prefix_title': '序', 'drop_until': '序',
    },
    {
        'key': 'anle-ji', 'book': '安樂集', 'author': '道綽',
        'category': '子部', 'subcategory': '釋家',
        'source': 'Project Gutenberg #24106', 'file': '安樂集.txt',
        'split': 'juan_sc', 'drop_until': '安樂集卷上',
    },
    {
        'key': 'dengxizi', 'book': '鄧析子', 'author': '鄧析',
        'category': '子部', 'subcategory': '名家',
        'source': 'Project Gutenberg #7215', 'file': '鄧析子.txt',
        'split': 'pieces',
        'pieces': [('無厚篇', '無厚篇'), ('轉辭篇', '轉辭篇')],
    },
    {
        'key': 'zuixing-shi', 'book': '醉醒石', 'author': '東魯古狂生',
        'category': '子部', 'subcategory': '小說家（話本）',
        'source': 'Project Gutenberg #24027', 'file': '醉醒石.txt',
        'split': 'hui', 'drop_prefix': True, 'hui_title_clean': True,
    },
    {
        'key': 'tang-zhongkui-pinggui-zhuan', 'book': '唐鍾馗平鬼傳', 'author': '東山雲中道人',
        'category': '子部', 'subcategory': '小說家（神魔）',
        'source': 'Project Gutenberg #27329', 'file': '唐鍾馗平鬼傳.txt',
        'split': 'hui', 'drop_prefix': True, 'hui_title_clean': True,
    },
    {
        'key': 'chunqiu-fanlu', 'book': '春秋繁露', 'author': '董仲舒',
        'category': '經部', 'subcategory': '春秋',
        'source': 'Project Gutenberg #25385', 'file': '春秋繁露.txt',
        'split': 'fanlu',
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
    'jian': split_jian,
    'juan': split_juan,
    'juans': split_juans,
    'chu': split_chu,
    'juan_num': split_juan_num,
    'yxql': split_yxql,
    'lunyu': split_lunyu,
    'juan_sc': split_juan_sc,
    'fanlu': split_fanlu,
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
               'shigongan', 'haigongan', 'digongan', 'lv-mudan', 'lin-er-bao',
               'tianbao-tu', 'yulou-chun', 'yinfeng-xiao', 'hou-xiyouji',
               'feituo-quanzhuan', 'shuihu-houzhuan', 'xueyuemei-zhuan',
               'suitang-yanyi', 'baigui-zhi', 'zuixing-shi',
               'tang-zhongkui-pinggui-zhuan'):
        return '回目'
    if key in ('shanhaijing', 'yandanzi', 'jingu-qiguan', 'zhishi-yuwen',
               'mengzi-ziyi-shuzheng', 'anle-ji'):
        return '卷'
    if key == 'lianggong-jiujian':
        return '諫'
    if key == 'pipa-ji':
        return '出'
    if key == 'aq-zhengzhuan':
        return '章'
    if key in ('doupen-xianhua',):
        return '則'
    if key in ('liji', 'shijing', 'youxue-qionglin', 'lunyu', 'dengxizi',
               'chunqiu-fanlu'):
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
    # 第五批新书（2026-09-08 批量入库）
    '天豹圖': '清', '梁公九諫': '宋', '長恨歌': '唐', '李娃傳': '唐',
    '玉樓春': '清', '引鳳蕭': '清', '今古奇觀': '明末', '後西遊記': '明末清初',
    # 第六批新书（2026-09-08 批量入库）
    '飛跎全傳': '清（嘉慶）', '佛說四十二章經': '東漢', '洛神賦': '三國魏',
    '晁氏儒言': '宋', '水滸後傳': '清初', '幼學瓊林': '明末清初',
    '治世餘聞': '明', '琵琶記': '元末明初', '雪月梅傳': '清',
    '龍川詞': '南宋',
    # 第七批新书（2026-09-08 批量入库）
    '隋唐演義': '清', '論語': '春秋', '滬語開路': '1915（民國四年）', '白圭志': '清（道光年間）',
    '孟子字義疏證': '清（乾隆年間）', '安樂集': '隋末唐初', '鄧析子': '春秋',
    '醉醒石': '明末', '唐鍾馗平鬼傳': '清', '春秋繁露': '西漢',
    '史記': '西漢', '漢書': '東漢', '三國志': '西晉', '三國演義': '明',
    '水滸傳': '明', '西遊記': '明', '紅樓夢': '清', '古文觀止': '清（康熙年間）',
    # ---- 第八批新书（2026-09-09 批量入库，42 本自动导入） ----
    '抱朴子': '東晉', '西京雜記': '東晉（舊題漢）', '幽明錄': '南朝宋', '明鏡公案': '明',
    '公孫龍子': '戰國', '竇娥冤': '元', '管子': '戰國（託名管仲）', '穆天子传': '先秦',
    '漢武帝別國洞冥記': '漢（舊題）', '日知錄': '明末清初', '海上花列傳': '晚清（1892）',
    '韩非子': '戰國', '風月夢': '清（道光年間）', '鬼谷子': '戰國（舊題）',
    '唐诗三百首': '清（乾隆年間）', '長生殿': '清（康熙年間）', '菜根譚': '明（萬曆年間）',
    '菜根譚前後集': '明（萬曆年間）', '筠州黃檗山斷際禪師傳法心要': '唐', '山水小牘': '唐末五代',
    '高士傳': '西晉', '金剛般若波羅蜜經': '東晉（姚秦譯）', '天妃顯聖錄': '清（乾隆刻本）',
    '三略': '秦漢之際（舊題黃石公）', '明夷待訪錄': '清初', '鹽鐵論': '西漢',
    '一枕奇': '明末清初', '六祖壇經': '唐', '臺灣外紀': '清（康熙年間）',
    '賈誼新書': '西漢', '金石緣': '清（乾隆年間）', '閱微草堂筆記': '清（乾隆年間）',
    '醒夢駢言': '清（乾隆年間）', '虬髯客傳': '唐末', '吳船錄': '南宋',
    '星槎勝覽': '明（正統年間）', '喻世明言': '明（天啟年間）', '平妖傳': '明',
    '東周列國志': '明末清初', '警世通言': '明（天啟年間）', '封氏聞見記': '唐', '搜神記': '東晉',
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
    # 第五批新书（2026-09-08 批量入库）
    '天豹圖': '清代英雄傳奇小說：李榮春仗義疏財、施碧霞賣身葬母，眾豪傑除奸扶正、終保忠良的故事。',
    '梁公九諫': '宋人話本：演梁公狄仁傑九次力諫武則天、力保廬陵王復位，忠肝義膽、直言極諫。',
    '長恨歌': '白居易長篇敘事詩，詠唐玄宗與楊貴妃生離死別之情，纏綿悱惻，千古傳誦。',
    '李娃傳': '唐傳奇名篇，白行簡作：滎陽公子與長安名妓李娃悲歡離合、終諧伉儷，曲盡世情。',
    '玉樓春': '清代才子佳人小說：邵卞嘉父子為奸相盧杞所構陷，歷盡離亂，終得團圓昭雪。',
    '引鳳蕭': '清代才子佳人小說：白眉仙才華絕艷而淡泊功名，於新政風波、家國離亂中守志不移。',
    '今古奇觀': '明代話本小說選集，抱甕老人輯，收話本四十篇，市井百態、勸懲勸善，膾炙人口。',
    '後西遊記': '《西遊記》續書：唐半偈、小行者、豬一戒、沙彌師徒四人西天求解，嬉笑怒罵、別開生面。',
    # 第六批新书（2026-09-08 批量入库）
    '飛跎全傳': '清代神怪諷世小說：敘「跎子」石信出世、進寶封王，滿紙諧謔市語，嬉笑怒罵。',
    '佛說四十二章經': '東漢迦葉摩騰、竺法蘭所譯、現存最早漢傳佛經之一：收佛言四十二章，明心見性、斷欲去愛。',
    '洛神賦': '曹植辭賦名篇：記黃初三年過洛水，夢遇洛神宓妃，驚鴻一瞥、人神殊途，文采斐然。',
    '晁氏儒言': '宋晁說之論學之作：辨王安石《新經義》《字說》之失，侃侃不撓，誠儒者之言。',
    '水滸後傳': '清初陳忱續《水滸》：梁山殘部感舊重聚，抗金報國、遠遁海外，寄寓故國之思。',
    '幼學瓊林': '明清蒙學百科讀物：天文地輿、人事科第、鳥獸花木無所不包，駢文四字朗朗上口，昔日蒙童必讀。',
    '治世餘聞': '明陳洪謨筆記：記弘治一朝朝章國故與宮闈舊聞，多可補正史之闕。',
    '琵琶記': '元高明南戲經典：蔡伯喈、趙五娘夫婦悲歡離合，孝義動人，被譽為「南戲之祖」。',
    '雪月梅傳': '清代才子佳人小說：岑秀才歷雪姐、月娥、小梅諸緣，兼寫豪傑報應、勸懲果報。',
    '龍川詞': '南宋陳亮詞集：豪放俊邁，寄恢復中原之志，〈念奴嬌·登多景樓〉尤為千古名篇。',
    # 第七批新书（2026-09-08 批量入库）
    '隋唐演義': '清代講史演義巨著：自隋文帝平陳寫至唐明皇還都，秦瓊、程咬金、單雄信諸豪傑事蹟，膾炙人口。',
    '論語': '儒家核心經典：孔子與弟子及時人問答之語錄，凡二十篇，宋儒列為「四書」之首。',
    '滬語開路': '一九一五年上海美華書館印行滬語會話讀本：供在滬外僑與傳教士學習上海方言，附英文說明與對話練習。',
    '白圭志': '清代才子佳人小說：張庭瑞與楊菊英歷經離散奇緣，女扮男裝之蘭英登科揚名，奇情迭出。',
    '孟子字義疏證': '清戴震訓詁名篇：就理、天道、性、才、道、仁義禮智等字疏證《孟子》，力闢宋儒理學之非。',
    '安樂集': '唐道綽淨土宗要典：以十二大門廣引經論，明念佛往生之教，勸歸西方安樂淨土。',
    '鄧析子': '舊題春秋鄭人鄧析所作：《無厚》《轉辭》二篇，尚形名之辯，開刑名法家先聲。',
    '醉醒石': '明末話本小說集：凡十五回，寫世態人情、因果報應，取「醉之以酒而醒之以石」之義。',
    '唐鍾馗平鬼傳': '清代神魔小說：鍾馗蒙閻君封為平鬼大元帥，率神荼、鬱壘遍斬世間無恥惡鬼。',
    '春秋繁露': '西漢董仲舒經學哲學著作：以陰陽五行推演《春秋》大義，暢發天人感應、君權神授之說。',
    '史記': '二十四史之首。太史公「究天人之際，通古今之變，成一家之言」。',
    '漢書': '中國第一部紀傳體斷代史，上起漢高祖、下終王莽。',
    '三國志': '與《史記》《漢書》《後漢書》並稱「前四史」，記魏蜀吳三國鼎立。',
    '三國演義': '中國古典四大名著之一：從桃園三結義到三分歸晉，一部英雄史詩。',
    '水滸傳': '四大名著之一：一百零八好漢聚義梁山，替天行道，快意恩仇。',
    '西遊記': '四大名著之一：唐僧師徒西天取經、歷經九九八十一難的魔幻長篇。',
    '紅樓夢': '四大名著之首：以「一把辛酸淚」，寫盡賈府興衰與寶黛情緣。',
    '古文觀止': '清代流傳最廣的古文選本，上起周秦、下迄明末，共 222 篇。',
    # ---- 第八批新书（2026-09-09 批量入库，42 本自动导入） ----
    '抱朴子': '東晉葛洪撰道教名著：內篇論神仙方藥、養生延年，外篇評時政得失、人間世事，為道教思想集大成之作。',
    '西京雜記': '舊題東晉葛洪輯西漢雜史佚聞：記長安宮室苑囿、奇珍異事、典章制度，多為後世小說戲曲所取材。',
    '幽明錄': '南朝宋劉義慶撰志怪小說集：記幽冥鬼神、因果報應之事，為六朝志怪名著。',
    '明鏡公案': '明代公案小說集：記官吏審案斷獄故事，明鏡高懸、懲惡勸善。',
    '公孫龍子': '戰國名家公孫龍之作：白馬非馬、堅白同異之辨，開中國古代邏輯思辨之先聲。',
    '竇娥冤': '元關漢卿雜劇名作：竇娥蒙冤負屈、感天動地、六月飛雪，為元雜劇悲劇之最。',
    '管子': '舊題齊相管仲、實戰國學者託名之作：富國強兵、禮法並用，涵政治、經濟、軍事、哲學諸端。',
    '穆天子传': '先秦古書：記周穆王西征遊歷、會見西王母之傳說，開中國遊仙小說先河。',
    '漢武帝別國洞冥記': '舊題東漢郭憲撰志怪小說：記漢武帝求仙及別國異域珍異之事，辭采瑰麗。',
    '日知錄': '清顧炎武積數十年學問而成之筆記：經義、史學、吏治、財賦、輿地無所不包，開清代樸學先聲。',
    '海上花列傳': '晚清韓邦慶吳語小說：以上海妓院為舞臺寫十里洋場世相，為吳語文學開山之作。',
    '韩非子': '戰國韓非法家集大成之作：主法、術、勢兼治，《五蠹》《說難》等篇膾炙人口。',
    '風月夢': '晚清狹邪小說：寫揚州鹽商子弟冶遊嫖妓、傾家蕩產之世情悲歡，市語方言鮮活。',
    '鬼谷子': '舊題戰國鬼谷子撰縱橫家書：捭闔、揣摩、權謀之術，為縱橫家與謀略學之祖。',
    '唐诗三百首': '清蘅塘退士（孫洙）編唐詩選本：五七言古近體兼備，選詩精當，為最流行之唐詩啟蒙讀物。',
    '長生殿': '清洪昇傳奇名作：寫唐明皇與楊貴妃生死相戀，兼寓家國興亡之慨，與《桃花扇》並稱。',
    '菜根譚': '明洪應明格言集：融儒釋道三家，論修身、處世、出世之道，簡練雋永，膾炙人口。',
    '菜根譚前後集': '明洪應明《菜根譚》別本（古登堡另版）：前後兩集錄處世修身語錄。',
    '筠州黃檗山斷際禪師傳法心要': '唐黃檗希運禪師法語：直指「無心」見性之旨，為臨濟宗重要典籍。',
    '山水小牘': '唐末皇甫枚筆記小說集：多記晚唐神怪軼事、仙蹤靈異，筆致清麗（題名或作《三水小牘》）。',
    '高士傳': '西晉皇甫謐撰：輯上古至魏晉隱逸高潔之士近百人，為中國隱逸傳記之祖。',
    '金剛般若波羅蜜經': '姚秦鳩摩羅什譯大乘要典：「應無所住而生其心」，禪宗與民間持誦最廣之佛經。',
    '天妃顯聖錄': '清代刻本記媽祖（天妃）顯聖事蹟：護漕救難、感應靈異，為媽祖信仰之重要文獻。',
    '三略': '舊題黃石公撰兵書：上中下三略論政略與用兵，與《六韜》並傳，為武經七書之一。',
    '明夷待訪錄': '清初黃宗羲政論名篇：《原君》《原臣》痛斥君主專制，倡「天下為主、君為客」，具啟蒙思想。',
    '鹽鐵論': '西漢桓寬錄昭帝鹽鐵會議：桑弘羊與賢良文學辯論國家經濟政策，為漢代政論之淵藪。',
    '一枕奇': '明末清初華陽散人擬話本小說：借市井故事寫人情世態、勸懲果報。',
    '六祖壇經': '唐禪宗六祖慧能說法、弟子法海集錄：明心見性、頓悟成佛之旨，唯一稱「經」之中國佛教撰述。',
    '臺灣外紀': '清江日昇撰臺灣史事：自鄭芝龍、鄭成功至鄭克塽、施琅平臺，備記明鄭興亡始末。',
    '賈誼新書': '西漢賈誼政論雜著：《過秦》《治安》諸篇論秦亡漢興、治國之策，議論風發，文采冠絕。',
    '金石緣': '清代才子佳人小說：寫林愛珠、金玉之悲歡離合與善惡果報之世情故事。',
    '閱微草堂筆記': '清紀昀晚年志怪筆記：談狐說鬼而寓勸懲，文筆簡淡雋永，與《聊齋誌異》並稱。',
    '醒夢駢言': '清代話本小說集：凡十二回，寫家庭倫常、因果報應，警醒世人、如夢方覺。',
    '虬髯客傳': '唐末杜光庭（舊題）傳奇名篇：風塵三俠虬髯客、李靖、紅拂女，豪俠傳奇之典範。',
    '吳船錄': '南宋范成大出蜀紀行之作：記沿途名勝古蹟、風土人情，為宋代遊記名著。',
    '星槎勝覽': '明費信記隨鄭和下西洋見聞：四十四國風土物產、航路道里，為海上絲路重要文獻。',
    '喻世明言': '明馮夢龍「三言」之首：收話本四十篇，市井傳奇、人情世態，膾炙人口。',
    '平妖傳': '明羅貫中、馮夢龍神魔小說：敘聖姑姑、蛋子和尚等妖狐亂世與文彥博平妖故事。',
    '東周列國志': '明末清初歷史演義：自周幽王烽火戲諸侯至秦始皇一統，列國紛爭、波瀾壯闊。',
    '警世通言': '明馮夢龍「三言」之一：收話本四十篇，《杜十娘怒沉百寶箱》等名篇即出於此。',
    '封氏聞見記': '唐封演筆記：記唐代掌故、典制、風俗、藝文，考據精審，史料價值甚高。',
    '搜神記': '東晉干寶撰志怪小說集：搜輯神仙鬼怪、靈異感應之事，集六朝志怪之大成。',
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
    if cfg.get('drop_until'):
        body = drop_until_heading(body, cfg['drop_until'])   # 天豹圖/梁公九諫：丢弃书名/作者行至「序」标题
    if cfg.get('normalize_hui_no_di'):
        body = normalize_hui_no_di(body)   # 綠牡丹「二十一回」→「第二十一回」
    if cfg.get('normalize_fe_punct'):
        body = normalize_fe_punct(body)    # 李娃傳 FE5x 小型标点 → 全角
    splitter = SPLITTERS[cfg['split']]
    if cfg['split'] in ('hui', 'chu'):
        chapters = splitter(body, cfg.get('keep_prefix_title'), cfg.get('cut_at'),
                            cfg.get('drop_prefix', False), cfg.get('title_next', False))
    elif cfg['split'] in ('shanhaijing', 'juan'):
        chapters = splitter(body, cfg['volumes'])
    elif cfg['split'] in ('yecao', 'pieces', 'yxql'):
        chapters = splitter(body, cfg['pieces'])
    elif cfg['split'] in ('ze', 'jian'):
        chapters = splitter(body, cfg.get('keep_prefix_title'))
    elif cfg['split'] == 'juan_sc':
        chapters = splitter(body, cfg.get('keep_prefix_title'), cfg.get('drop_prefix', False))
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


# ============================================================
# 精简模式（--ids 书号列表）：
#   本地元数据(EBOOK_ID/BOOKS/raw 头部) → 古登堡 API 自动补全
#   书名/作者；默认切分 auto 一键跑完；配置持久化 quick_books.json
# ============================================================
QUICK_FILE = os.path.join(BASE, 'quick_books.json')

# 失败单独记日志：logs/gutenberg_import.log（追加、带时间戳；写失败不阻断主流程）。
# 同一编号若在多阶段失败（如下载失败后再缺 raw）日志会各记一行作审计，
# 汇总时 _print_failure_summary 按编号去重计数。
FAILURE_LOG = os.path.join(ROOT, 'logs', 'gutenberg_import.log')
_FAILED = []


def log_failure(book_id, reason, detail=''):
    """把一个编号/书名的失败写入 logs/gutenberg_import.log，并暂存 _FAILED 供末尾汇总。"""
    ts = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    line = f'{ts}  #{book_id}  {reason}' + (f'  （{detail}）' if detail else '')
    _FAILED.append((str(book_id), reason))
    try:
        os.makedirs(os.path.dirname(FAILURE_LOG), exist_ok=True)
        with open(FAILURE_LOG, 'a', encoding='utf-8') as f:
            f.write(line + '\n')
    except Exception as e:
        print(f'  ⚠️ 失败日志写入异常：{e}')


def _print_failure_summary():
    """本次运行失败编号汇总（按编号去重），无失败则安静返回。"""
    if not _FAILED:
        return
    fails = sorted({fid for fid, _ in _FAILED})
    print(f"\n❌ 失败 {len(fails)} 个编号 → 详见 {os.path.relpath(FAILURE_LOG, ROOT)}")
    for fid in fails:
        print(f"   ✗ #{fid}")


_ID_RE = re.compile(r'(\d{1,8})')
_RAW_TITLE_RE = re.compile(r'^\s*(?:Title|书名|書名)\s*[:：]\s*(.+?)\s*$', re.I)
_RAW_AUTHOR_RE = re.compile(r'^\s*(?:Author|作者)\s*[:：]\s*(.+?)\s*$', re.I)
_PG_LAST = [0.0]


def _cjk(s):
    return bool(s and CJK_RE.search(s))


def _pg_pace(gap=5.0):
    """网络请求节流：与正文下载同规范（间隔 ≥5s、顺序、不并行）。"""
    remain = gap - (time.time() - _PG_LAST[0])
    if remain > 0:
        print(f'  ⏳ 间隔 {remain:.0f}s…')
        time.sleep(remain)
    _PG_LAST[0] = time.time()


def _read_bytes_lines(path):
    raw = open(path, 'rb').read()
    for enc in ('utf-8-sig', 'gb18030', 'big5'):
        try:
            return raw.decode(enc).splitlines()
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode('utf-8', 'replace').splitlines()


def parse_id_list(path):
    """书号列表：每行一个古登堡编号；容忍 pg/URL/空白行；# 开头整行为注释。"""
    ids = []
    for raw in _read_bytes_lines(path):
        line = raw.strip()
        if not line:
            continue
        if line.startswith('#') and not re.match(r'#\s*\d', line):
            continue                      # 纯注释行
        m = _ID_RE.search(line)
        if not m:
            continue
        gid = str(int(m.group(1)))
        if gid not in ids:
            ids.append(gid)
    return ids


def book_urls_by_id(gid):
    """files/{id}.txt → files/{id}-0.txt → cache/epub/pg{id}.txt 依序尝试。"""
    return [
        f'https://www.gutenberg.org/files/{gid}/{gid}.txt',
        f'https://www.gutenberg.org/files/{gid}/{gid}-0.txt',
        f'https://www.gutenberg.org/cache/epub/{gid}/pg{gid}.txt',
    ]


def download_by_id(gid):
    """按编号下载到 raw/{gid}.txt；已存在非空则跳过（间隔 ≥5s）。"""
    out = os.path.join(RAW, gid + '.txt')
    if os.path.exists(out) and os.path.getsize(out) > 0:
        print(f'  · 已存在，跳过下载：raw/{gid}.txt')
        return True
    _pg_pace()
    print(f'  ⬇ 下载 #{gid} → raw/{gid}.txt')
    for i, url in enumerate(book_urls_by_id(gid)):
        data = fetch_url(url)
        if data:
            with open(out, 'wb') as f:
                f.write(data)
            tag = '首选' if i == 0 else '备用-0' if i == 1 else '备用-cache'
            print(f'    成功（{tag}） {len(data)} 字节')
            return True
        print(f'    链接不可用: {url}')
    print(f'  ✗ 下载失败：#{gid}')
    log_failure(gid, '下载失败', 'files/{id}.txt → files/{id}-0.txt → cache/epub/pg{id}.txt 三链接均不可用')
    return False


def meta_from_raw_file(gid):
    """本地元数据：raw/{gid}.txt 头部 Title/Author（起始标记前 120 行内）。"""
    p = os.path.join(RAW, gid + '.txt')
    if not (os.path.exists(p) and os.path.getsize(p) > 0):
        return None, None
    title = author = None
    for line in _read_bytes_lines(p)[:120]:
        if line.strip().startswith('*** START'):
            break
        if title is None:
            m = _RAW_TITLE_RE.match(line)
            if m:
                title = m.group(1).strip()
        if author is None:
            m = _RAW_AUTHOR_RE.match(line)
            if m:
                author = m.group(1).strip()
        if title is not None and author is not None:
            break
    return (title or None), (author or None)


def _clean_author(a):
    if not a:
        return None
    s = a.strip()
    s = re.sub(r'\s*[（(][^）)]*[-–]?\d{4}[^）)]*[）)]$', '', s).strip()   # 年代尾缀
    s = re.sub(r'[,，]\s*[^,，]*\d{3,4}[^,，]*$', '', s).strip()          # ", 18xx-19xx"
    s = re.sub(r'[\s。．.;;]+$', '', s).strip()
    if s.lower() in ('anonymous', 'unknown'):
        return None
    return s or None


def meta_from_api(gid):
    """古登堡 JSON 接口（?format=json）兜底元数据。
    实测返回形态 ['', [中文书名], [作者], […]]，作者多缺省（佚名）。"""
    _pg_pace()
    data = fetch_url(f'https://www.gutenberg.org/ebooks/{gid}?format=json')
    if not data:
        return {}
    try:
        j = json.loads(data.decode('utf-8', 'replace'))
    except Exception:
        return {}
    title = author = None
    if isinstance(j, dict):
        title = j.get('title')
        names = [a.get('name') for a in (j.get('authors') or [])
                 if isinstance(a, dict) and a.get('name')]
        author = names[0] if names else None
    elif isinstance(j, list) and len(j) >= 2:
        def first(items):
            return next((str(x).strip() for x in (items or [])
                         if isinstance(x, str) and x.strip()), None)
        title = first(j[1])
        if len(j) > 2:
            author = first(j[2])
    if isinstance(title, str):
        title = title.strip()
    if isinstance(author, str):
        author = _clean_author(author)
    return {'title': title or None, 'author': author or None}


def detect_split(body):
    """默认切分规则：数正文标题行，回/章/出/則/篇/卷 取出现最多者；
    命中 <2 次或未识别 → 整本 single（后续可 --split 覆盖或转精细模式微调）。"""
    counts = {'hui': 0, 'zhang': 0, 'chu': 0, 'ze': 0, 'pian': 0, 'juan_num': 0}
    for l in body:
        s = l.strip()
        if RE_HUI.match(s):
            counts['hui'] += 1
        elif RE_ZHANG.match(s):
            counts['zhang'] += 1
        elif RE_CHU.match(s):
            counts['chu'] += 1
        elif RE_ZE.match(s):
            counts['ze'] += 1
        elif RE_PIAN.match(s):
            counts['pian'] += 1
        elif RE_JUAN_N.match(s):
            counts['juan_num'] += 1
    order = ('hui', 'zhang', 'chu', 'ze', 'pian', 'juan_num')
    best = max(order, key=counts.get) if any(counts.values()) else None
    return best if (best and counts[best] >= 2) else 'single'


def _resolve_quick(gid, defaults, split_opt='auto', allow_download=True):
    """把一个书号解析为可入库配置 cfg：
    ① 本地已知编号 → 复用 BOOKS 精细配置；
    ② 否则本地 raw 头部 → 古登堡 API 拉标题/作者，按默认切分规则生成配置。
    返回 cfg 或 None（书名非中文/下载失败等跳过）。"""
    # ① 本地元数据优先：EBOOK_ID/BOOKS 已知书号直接复用其手动配置
    for c in BOOKS:
        if EBOOK_ID.get(c['book']) == int(gid):
            print(f'  ✅ #{gid} 命中本地精细配置（BOOKS）：{c["book"]}')
            return c
    # ①.b 历史精简配置命中（quick_books.json 已导入过的编号）→ 幂等复用，离线也可重跑
    for c in (_load_json(QUICK_FILE, []) or []):
        if isinstance(c, dict) and c.get('gid') == gid:
            print(f'  ✅ #{gid} 命中历史精简配置（quick_books.json）：{c.get("book")}')
            return c
    # ② 本地 raw 已存在 → 先解析头部元数据
    ltitle, lauthor = meta_from_raw_file(gid)
    title = ltitle if _cjk(ltitle) else None
    author = _clean_author(lauthor)
    # 补齐原文（--no-download 时只允许用本地已下载文件）
    raw_path = os.path.join(RAW, gid + '.txt')
    if allow_download and not (os.path.exists(raw_path) and os.path.getsize(raw_path) > 0):
        download_by_id(gid)
    if title is None or author is None:
        ltitle2, lauthor2 = meta_from_raw_file(gid)
        if title is None and _cjk(ltitle2):
            title = ltitle2
        if author is None:
            author = _clean_author(lauthor2)
    # ③ 古登堡 API 兜底（本地解析缺失时）
    if title is None or author is None:
        meta = meta_from_api(gid)
        if title is None and _cjk(meta.get('title')):
            title = meta['title']
        if author is None and meta.get('author'):
            author = meta['author']
    if not title:
        print(f'  ✗ #{gid}：无法确认中文书名（本地无 raw 元数据且 API 不可用），跳过')
        log_failure(gid, '无法确认中文书名', '本地 raw 头部元数据与古登堡 API 均不可用，或书名为非中文')
        return None
    if not (os.path.exists(raw_path) and os.path.getsize(raw_path) > 0):
        print(f'  ✗ #{gid}：缺少原文 raw/{gid}.txt，跳过（可用 --no-download 仅处理已有本地文件）')
        log_failure(gid, '缺少原文', f'raw/{gid}.txt 不存在或为空')
        return None
    if any(c['book'] == title for c in BOOKS):
        print(f'  ✗ #{gid} 书名「{title}」已在 BOOKS 精细配置中，请勿重复导入，跳过')
        return None
    # 默认切分规则
    split = split_opt
    if split == 'auto':
        body = extract_body(_read_bytes_lines(raw_path))
        split = detect_split(body)
        print(f'  ↻ 默认切分识别：{split}')
    cfg = {
        'key': 'pg' + gid,
        'book': title,
        'author': author or '佚名',
        'category': defaults.get('category', '子部'),
        'subcategory': defaults.get('subcategory', '古籍（自动导入）'),
        'source': f'Project Gutenberg #{gid}',
        'file': gid + '.txt',
        'split': split,
        'gid': gid,
    }
    if split in ('hui', 'chu'):
        cfg['drop_prefix'] = True          # 丢弃首个回目标记前的封面/序残留
        cfg['hui_title_clean'] = True
    print(f"  ✅ #{gid} → {title}（作者：{cfg['author']}）key={cfg['key']} split={split}")
    return cfg


def _load_quick_configs():
    """入库全集 = BOOKS（手动，优先） + quick_books.json（精简历史）。"""
    quick = _load_json(QUICK_FILE, []) or []
    quick = [c for c in quick if isinstance(c, dict) and c.get('key')]
    out = list(BOOKS)
    keys = {c['key'] for c in out}
    books = {c['book'] for c in out}
    for c in quick:
        if c['key'] in keys or c.get('book') in books:
            continue
        out.append(c)
        keys.add(c['key'])
        books.add(c.get('book'))
    return out


def _save_quick_configs(configs):
    """把 BOOKS 之外的动态配置持久化（保证后续全量运行/站点合并不丢精简书）。"""
    extra = [c for c in configs if c.get('gid')]
    with open(QUICK_FILE, 'w', encoding='utf-8') as f:
        json.dump(extra, f, ensure_ascii=False, indent=2)
    print(f'  💾 精简配置已持久化 → {os.path.relpath(QUICK_FILE, BASE)}')



def main():
    # ---- 参数解析：支持取值参数（--ids FILE / --split auto / --category …） ----
    pos, flags, opts = [], set(), {}
    VALUE_FLAGS = ('ids', 'list', 'id-list', 'split', 'category', 'subcategory')
    argv = sys.argv[1:]
    i = 0
    while i < len(argv):
        a = argv[i]
        if not a.startswith('--'):
            pos.append(a)
            i += 1
            continue
        body = a[2:]
        if '=' in body:
            k, v = body.split('=', 1)
            if k in VALUE_FLAGS:
                opts[k] = v
            else:
                flags.add(k)
            i += 1
            continue
        if body in VALUE_FLAGS:
            if i + 1 >= len(argv):
                print(f'✗ 参数 --{body} 需要值')
                return
            opts[body] = argv[i + 1]
            i += 2
            continue
        flags.add(body)
        i += 1

    quick_file = opts.get('ids') or opts.get('list') or opts.get('id-list')
    do_annotate = 'no-annotate' not in flags
    do_merge = 'no-merge' not in flags
    do_download = 'no-download' not in flags
    do_catalog = 'catalog' in flags

    # 精细模式（手动书名/BOOKS）与精简模式（--ids 书号列表）互斥
    if pos and quick_file:
        print('✗ 不能同时传书名与 --ids；精细：python3 gutenberg_import.py [书名…]；'
              '精简：python3 gutenberg_import.py --ids 列表.txt')
        return

    # 入库配置全集 = 手动 BOOKS + 精简模式历史配置（quick_books.json）
    configs = _load_quick_configs()

    if quick_file:
        if not os.path.exists(quick_file):
            print(f'✗ 找不到书号列表文件：{quick_file}')
            return
        ids = parse_id_list(quick_file)
        if not ids:
            print(f'✗ 书号列表为空或格式不符：{quick_file}（每行一个古登堡编号）')
            return
        split_opt = opts.get('split', 'auto')
        if split_opt != 'auto' and split_opt not in SPLITTERS:
            print(f'✗ 未知切分规则：{split_opt}（可选 auto 或 {", ".join(sorted(SPLITTERS))}）')
            return
        quick_defaults = {
            'category': opts.get('category', '子部'),
            'subcategory': opts.get('subcategory', '古籍（自动导入）'),
        }
        added, targets = [], []
        for gid in ids:
            cfg = _resolve_quick(gid, quick_defaults, split_opt, do_download)
            if cfg is None:
                continue
            if any(c['key'] == cfg['key'] for c in configs):   # 已在配置（含 BOOKS 已知书号）
                if cfg['book'] not in targets:
                    targets.append(cfg['book'])
                continue
            if any(c['book'] == cfg['book'] for c in configs):
                print(f'  ⚠️ #{gid} 书名「{cfg["book"]}」已入库，跳过（同名不同版请改用精细模式）')
                continue
            configs.append(cfg)
            added.append(cfg)
            targets.append(cfg['book'])
        if added:
            _save_quick_configs(configs)
        names = targets
        if not names:
            print('== 精简导入：无可处理的编号（详见上方提示）==')
            _print_failure_summary()
            return
        print(f'  精简模式：本次处理 {len(names)} 本（列表 {len(ids)} 个编号）')
    else:
        names = pos
        if not names:
            names = [] if do_catalog else [cfg['book'] for cfg in configs]

    if names:
        targets = names
    else:
        targets = []

    reports = {}
    built = {}

    # 0) 补齐缺失的 raw（顺序下载、间隔 ≥5s、不并行、已存在跳过；精简编号走 gid 下载器）
    if do_download:
        last = None
        for cfg in configs:
            if cfg['book'] not in targets:
                continue
            rp = os.path.join(RAW, cfg['file'])
            if os.path.exists(rp) and os.path.getsize(rp) > 0:
                continue
            if cfg.get('gid'):
                download_by_id(cfg['gid'])
            else:
                if last:
                    gap = 5 - (time.time() - last)
                    if gap > 0:
                        print(f'  ⏳ 间隔 {gap:.0f}s…')
                        time.sleep(gap)
                download_book(cfg['book'])
                last = time.time()

    # 1) 目标书：清洗→切分→注音注释→写 data/books/{key}.json
    #    逐本 try/except：任何一本失败只记日志并跳过，不中断整批（汇总见 _print_failure_summary）
    ok_n = 0
    for cfg in configs:
        if cfg['book'] not in targets:
            continue
        id_label = cfg.get('gid') or cfg['key']
        rp = os.path.join(RAW, cfg['file'])
        if not (os.path.exists(rp) and os.path.getsize(rp) > 0):
            print(f"  ✗ 缺 raw：{cfg['book']}（请联网下载或补齐 raw/{cfg['file']}）")
            log_failure(id_label, '缺少原文', f'raw/{cfg["file"]} 不存在或为空')
            continue
        try:
            out = _build_one(cfg)
            chapters = out['chapters']
            if not chapters:
                print(f"  ✗ 切分为空：{cfg['book']}（{cfg['key']}，split={cfg.get('split')}），跳过")
                log_failure(id_label, '切分为空（0 章）',
                            f"split={cfg.get('split')}，需改 --split 或转精细模式微调")
                continue
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
            ok_n += 1
        except Exception as e:
            print(f"  ✗ 处理失败：{cfg['book']}（{cfg['key']}）— {e}")
            log_failure(id_label, '处理异常', repr(e))

    if _FAILED:
        print(f'\n  （成功 {ok_n} 本；失败明细：）')
    _print_failure_summary()

    # 2) library-index.json（全量 BOOKS + 精简配置；本次未处理的从 data/books 磁盘读）
    index_cats = {}
    for cfg in configs:
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
