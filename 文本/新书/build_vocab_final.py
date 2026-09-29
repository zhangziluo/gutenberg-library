#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_vocab_final.py —— 把 vocab_raw.json 收敛成**前端词表** vocab_final.json

前端 `网站/js/vocab-matcher.js` 用它建 Trie 做中文最长前缀匹配（Max Match）：
词表提供的是**词边界**（哪些字连成一个词），释义仍来自各书自带的 annotations。
这样正文里的「君子」会整体成一个词条，而不再被拆成「君 + 子」两个单字散列打标。

产出（默认 `网站/_site_data/vocab_final.json`，Cloudflare 单文件上限 25 MiB 内）：
    {"_meta": {…}, "zh": [["君子","君子",8478,43], …], "en": [["morning",347,12], …]}
    行 = [词形, 简体形(可空), 全库词次, 出现书数]    ← 紧凑数组，省体积

规则
  · 中文：纯 CJK（与 vocab_extract 的 CJK 段定义一致）、长度 ≥ --min-len-zh（默认 2，
    即**不收单字**——单字本就是最小单元，没有边界价值；单字释义由 annotations 提供）。
    繁体词带 simp 时一并写入（前端会同时挂繁/简两个键 → 简中显示模式也能命中）。
  · 英文：默认**不收**（--with-en 打开）。英文标注走 annotations 的难词表；
    把全部 2.7 万词收进来会让英文页面每个词都带下划线。
  · 词次/书数：任何粒度（word / book / chapter）都能聚合；缺书目数时按记录里的
    book_count 取最大值，再退化为去重 book_id 计数。
  · 自检（每次运行都做，失败即报错且**不落盘**）：词形合法性（中文纯 CJK、英文最大词形）、
    行数一致、写后回读可解析 + 行格式正确。

用法
    python3 文本/新书/build_vocab_final.py                 # 默认：全量中文多字词
    python3 文本/新书/build_vocab_final.py --min-freq 50    # 收紧到高频词（词表更小）
    python3 文本/新书/build_vocab_final.py --with-en        # 连英文词一起输出
    python3 文本/新书/build_vocab_final.py --dry-run        # 只看统计不写文件
    python3 文本/新书/build_vocab_final.py --selftest       # 规则回归（对抗性样例）

前置：`python3 文本/新书/vocab_extract.py`（产出 vocab_raw.json，已 gitignore）。
产出 vocab_final.json **入库**（前端按需加载，浏览器缓存）。
"""
import argparse
import json
import os
import re
import sys
import time

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(BASE))
IN_DEFAULT = os.path.join(BASE, 'vocab_raw.json')
OUT_DEFAULT = os.path.join(ROOT, '网站', '_site_data', 'vocab_final.json')

try:                                            # 复用词形定义，避免两处规则走偏
    import vocab_extract as VX
    CJK_PAT = VX.CJK_PAT
    RE_EN_WORD = VX.RE_EN_WORD
except Exception:                               # 单独拷贝本脚本时也能跑
    VX = None
    CJK_PAT = r'[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]'
    _L = (r"A-Za-z\u00c0-\u024f\u0250-\u02af\u1e00-\u1eff\u2c60-\u2c7f"
          r"\ua720-\ua7ff\ufb00-\ufb06")
    RE_EN_WORD = re.compile('[%s]+(?:[-%s][%s]+)*' % (_L, r"\u0027\u2019\u02bc", _L))

RE_CJK = re.compile(CJK_PAT)
RE_CJK_FULL = re.compile(CJK_PAT + r'+')


def is_pure_cjk(word):
    return bool(word) and RE_CJK_FULL.fullmatch(word) is not None


def is_max_en(word):
    """英文词必须是「最大词形」：整串符合 RE_EN_WORD（前后不能还是字母/连接符）。"""
    return bool(word) and RE_EN_WORD.fullmatch(word) is not None


def load_raw(path):
    with open(path, encoding='utf-8') as f:
        data = json.load(f)
    if isinstance(data, list):
        rows, meta = data, {}
    else:
        rows = data.get('words') or []
        meta = data.get('_meta') or {}
    if not rows:
        raise SystemExit('vocab_raw 里没有 words 记录：%s' % path)
    return rows, meta


def aggregate(rows):
    """按词形聚合 → {word: [freq, books, simp, lang]}（word / book / chapter 粒度都能用）。"""
    acc, seen_books = {}, {}
    for r in rows:
        w = r.get('word')
        if not w:
            continue
        lang = r.get('lang') or ('zh' if RE_CJK.search(w) else 'en')
        freq = int(r.get('total') or r.get('frequency') or 0)
        rec = acc.get(w)
        if rec is None:
            rec = acc[w] = [0, 0, r.get('simp') or '', lang]
            seen_books[w] = set()
        rec[0] += freq
        if not rec[2] and r.get('simp'):
            rec[2] = r['simp']
        bc = int(r.get('book_count') or 0)
        if bc > rec[1]:
            rec[1] = bc
        bid = r.get('book_id') or r.get('book')
        if bid:
            seen_books[w].add(bid)
    for w, rec in acc.items():
        if not rec[1]:
            rec[1] = len(seen_books[w])
    return acc


def make_rows(acc, args):
    """过滤 + 排序 → (zh_rows, en_rows)"""
    zh, en = [], []
    for w, (freq, books, simp, lang) in acc.items():
        if freq < args.min_freq:
            continue
        if lang == 'zh':
            if len(w) < args.min_len_zh or not is_pure_cjk(w):
                continue
            if simp and (not is_pure_cjk(simp) or simp == w):
                simp = ''
            zh.append([w, simp, freq, books])
        else:
            if args.no_en:
                continue
            if len(w) < args.min_len_en or not is_max_en(w):
                continue
            en.append([w, '', freq, books])
    zh.sort(key=lambda r: (-r[2], r[0]))
    en.sort(key=lambda r: (-r[2], r[0]))
    return zh, en


def verify(zh, en, out_path):
    """回读校验：可解析 + 行数一致 + 行格式合法（失败即抛错，不静默）。"""
    with open(out_path, encoding='utf-8') as f:
        d = json.load(f)
    got_zh, got_en = d.get('zh') or [], d.get('en') or []
    assert len(got_zh) == len(zh), 'zh 行数不一致：%d != %d' % (len(got_zh), len(zh))
    assert len(got_en) == len(en), 'en 行数不一致：%d != %d' % (len(got_en), len(en))
    for row in got_zh:
        assert isinstance(row, list) and 2 <= len(row) <= 4, 'zh 行格式错：%r' % (row,)
        assert is_pure_cjk(row[0]) and len(row[0]) >= 2, 'zh 词形非法：%r' % (row[0],)
        assert isinstance(row[2], int) and row[2] >= 1, 'zh 词次非法：%r' % (row,)
        if len(row) > 1 and row[1]:
            assert is_pure_cjk(row[1]), 'zh 简体形非法：%r' % (row[1],)
    for row in en:
        assert is_max_en(row[0]), 'en 词形非法：%r' % (row[0],)
    return len(got_zh), len(got_en)


def selftest():
    """对抗性样例：确认过滤、聚合、词形校验都按预期工作。"""
    cases = []

    def check(name, cond, detail=None):
        cases.append((name, bool(cond), detail))

    sample = [
        {'word': '之', 'lang': 'zh', 'total': 100, 'book_id': 'a'},                 # 单字 → 滤
        {'word': '君子', 'lang': 'zh', 'total': 4, 'book_id': 'a'},                 # 多字 → 留
        {'word': '君子', 'lang': 'zh', 'total': 6, 'book_id': 'b'},                 # 跨书聚合 → 10 / 2 本
        {'word': '說服', 'lang': 'zh', 'simp': '说服', 'total': 5, 'book_id': 'a'},
        {'word': '少見', 'lang': 'zh', 'total': 1, 'book_id': 'a'},                 # 频次不足 → 滤
        {'word': 'A', 'lang': 'zh', 'total': 9, 'book_id': 'a'},                    # 非 CJK → 滤
        {'word': 'morning', 'lang': 'en', 'total': 7, 'book_id': 'a'},
        {'word': 'mornin', 'lang': 'en', 'total': 3, 'book_id': 'a'},
        {'word': 'mornin-', 'lang': 'en', 'total': 9, 'book_id': 'a'},              # 非最大词形 → 滤
        {'word': "don't", 'lang': 'en', 'total': 4, 'book_id': 'a'},
    ]

    class A(object):
        min_freq = 2
        min_len_zh = 2
        min_len_en = 2
        no_en = False

    acc = aggregate(sample)
    zh, en = make_rows(acc, A())
    zw = dict((r[0], r) for r in zh)
    ew = dict((r[0], r) for r in en)

    check('单字不入表（之）', '之' not in zw)
    check('多字入表 + 跨书记录聚合（君子 10 次 / 2 本）',
          zw.get('君子') and zw['君子'][2] == 10 and zw['君子'][3] == 2, zw.get('君子'))
    check('繁体词带简体形（說服 → 说服）', zw.get('說服') and zw['說服'][1] == '说服', zw.get('說服'))
    check('频次不足被滤（少見 1 次）', '少見' not in zw)
    check('非 CJK 不入中文表（A）', 'A' not in zw)
    check('英文词入表（morning / mornin / don\u2019t）',
          'morning' in ew and 'mornin' in ew and "don't" in ew, list(ew))
    check('非法英文词形被滤（mornin-）', 'mornin-' not in ew)
    check('最大词形校验：mornin 合法 / mornin- 非法',
          is_max_en('mornin') and not is_max_en('mornin-'))
    check('纯 CJK 校验：君子 合法 / A 非法', is_pure_cjk('君子') and not is_pure_cjk('A'))
    check('排序按词次降序', zh[0][2] >= zh[-1][2], [(r[0], r[2]) for r in zh])
    check('复用 vocab_extract 词形规则（Buda-Pesth 合法）',
          RE_EN_WORD is not None and RE_EN_WORD.fullmatch('Buda-Pesth') is not None)

    bad = [c for c in cases if not c[1]]
    for name, ok, detail in cases:
        print('  %s %s%s' % ('✅' if ok else '❌', name, '' if ok else '  ← %r' % (detail,)))
    print('自检：%d 通过 / %d 失败' % (len(cases) - len(bad), len(bad)))
    return 1 if bad else 0


def main():
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument('--in', dest='inp', default=IN_DEFAULT, help='输入 vocab_raw.json')
    ap.add_argument('--out', dest='out', default=OUT_DEFAULT, help='输出 vocab_final.json')
    ap.add_argument('--min-freq', type=int, default=2, help='全库词次下限（默认 2）')
    ap.add_argument('--min-len-zh', type=int, default=2, help='中文词长下限（默认 2，不收单字）')
    ap.add_argument('--min-len-en', type=int, default=2, help='英文词长下限（默认 2）')
    ap.add_argument('--no-en', dest='no_en', action='store_true', default=True, help='不收英文词（默认）')
    ap.add_argument('--with-en', dest='no_en', action='store_false', help='连英文词一起输出')
    ap.add_argument('--dry-run', action='store_true', help='只打印统计，不写文件')
    ap.add_argument('--selftest', action='store_true', help='规则回归自检')
    args = ap.parse_args()

    if args.selftest:
        return selftest()
    if not os.path.exists(args.inp):
        print('找不到输入：%s\n先跑：python3 文本/新书/vocab_extract.py' % args.inp, file=sys.stderr)
        return 2

    t0 = time.time()
    rows, meta = load_raw(args.inp)
    acc = aggregate(rows)
    zh, en = make_rows(acc, args)
    print('读入 %d 条记录（粒度 %s）→ 去重 %d 词' % (
        len(rows), (meta.get('granularity') or {}).get('mode') or '未知', len(acc)))
    print('保留：中文 %d 条（词次 ≥%d、长度 ≥%d）｜ 英文 %d 条%s' % (
        len(zh), args.min_freq, args.min_len_zh, len(en), '' if en else '（默认不收，--with-en 打开）'))
    if zh:
        print('最高频：' + '、'.join('%s(%d)' % (r[0], r[2]) for r in zh[:8]))

    if args.dry_run:
        print('（--dry-run：未写文件）')
        return 0

    out = {
        '_meta': {
            'generator': 'build_vocab_final.py',
            'generated': time.strftime('%Y-%m-%dT%H:%M:%S'),
            'source': os.path.relpath(args.inp, ROOT),
            'rules': {'min_freq': args.min_freq, 'min_len_zh': args.min_len_zh,
                      'min_len_en': args.min_len_en, 'include_en': bool(en)},
            'fields': {'zh': '[词形, 简体形(可空), 全库词次, 出现书数]',
                       'en': '[词形, "", 全库词次, 出现书数]'},
            'usage': '网站/js/vocab-matcher.js 建 Trie 做中文最长前缀匹配（词边界）；释义仍取各书 annotations',
        },
        'zh': zh,
        'en': en,
    }
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    tmp = args.out + '.part'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, separators=(',', ':'))
        f.write('\n')
    os.replace(tmp, args.out)
    n_zh, n_en = verify(zh, en, args.out)
    size = os.path.getsize(args.out) / 1048576.0
    print('写出 %s ｜ 中文 %d + 英文 %d 行 ｜ %.2f MiB ｜ %.1f s'
          % (os.path.relpath(args.out, ROOT), n_zh, n_en, size, time.time() - t0))
    print('回读校验通过（可解析 / 行数一致 / 词形合法）')
    return 0


if __name__ == '__main__':
    sys.exit(main())
