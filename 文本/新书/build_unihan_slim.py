#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_unihan_slim.py — 从官方 Unihan 抽出「拼音 / 部首 / 笔画」瘦身分片
================================================================
为什么：查词面板的回退链第 4 级是 Unihan（按 codepoint 查拼音/部首/笔画），
       而这套数据离线自带才靠谱 —— 于是从 UCD 官方 Unihan.zip 抽三个字段：

  Unihan_Readings.txt      kMandarin       → 拼音（普通话）
  Unihan_IRGSources.txt    kRSUnicode      → 部首号.额外笔画
  Unihan_IRGSources.txt    kTotalStrokes   → 总笔画
  Unihan_RadicalStrokeCounts.txt           → 同上，作补漏

产物（与 build_dict_shards.py 同口径：按 **字码点 % 128** 分片）：
  网站/_site_data/dict/unihan/<n>.json   {"之": {"p":"zhī","r":"丿","s":4}, …}
  并把 unihan 条目并入 网站/_site_data/dict/dict_meta.json（前端据此知道有这部词典）

用法：
  python3 文本/新书/build_unihan_slim.py                 # 自动下载 UCD（需联网）并构建
  python3 文本/新书/build_unihan_slim.py --src /tmp/unihan   # 用已解压的目录
  python3 文本/新书/build_unihan_slim.py --zip /tmp/Unihan.zip
  python3 文本/新书/build_unihan_slim.py --dry-run       # 只统计体积
"""
import argparse
import json
import os
import re
import sys
import shutil
import subprocess
import tempfile
import urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))            # 文本/新书
ROOT = os.path.dirname(os.path.dirname(BASE))
OUT = os.path.join(ROOT, '网站', '_site_data', 'dict')
META = os.path.join(OUT, 'dict_meta.json')
SHARDS = 128
UNIHAN_URL = 'https://www.unicode.org/Public/UCD/latest/ucd/Unihan.zip'

# 康熙部首 1..214（kRSUnicode 的部首号 → 部首字）
RADICALS = list('一丨丶丿乙亅二亠人儿入八冂冖冫几凵刀力勹匕匚匸十卜卩厂厶又口囗土士夂夊夕大女子宀寸小尢尸屮山巛工己巾干幺广廴廾弋弓彐彡彳心戈戶手支攴文斗斤方无日曰月木欠止歹殳毋比毛氏气水火爪父爻爿片牙牛犬玄玉瓜瓦甘生用田疋疒癶白皮皿目矛矢石示禸禾穴立竹米糸缶网羊羽老而耒耳聿肉臣自至臼舌舛舟艮色艸虍虫血行衣襾見角言谷豆豕豸貝赤走足身車辛辰辵邑酉釆里金長門阜隶隹雨青非面革韋韭音頁風飛食首香馬骨高髟鬥鬯鬲鬼魚鳥鹵鹿麥麻黃黍黑黹黽鼎鼓鼠鼻齊齒龍龜龠')

LINE = re.compile(r'^U\+([0-9A-F]{4,6})\t(kMandarin|kRSUnicode|kTotalStrokes)\t(.+?)\s*$')
PINYIN_SRC = os.path.join(BASE, 'data', 'pinyin_readings.json')


def fetch_zip(cache):
    if os.path.exists(cache) and os.path.getsize(cache) > 1_000_000:
        print('  用缓存 %s' % cache)
        return cache
    print('  下载 %s …' % UNIHAN_URL)
    os.makedirs(os.path.dirname(cache), exist_ok=True)
    urllib.request.urlretrieve(UNIHAN_URL, cache)
    print('  ✅ %.1f MB' % (os.path.getsize(cache) / 1048576.0))
    return cache


def extract(zip_path, dest):
    if shutil.which('unzip'):
        subprocess.check_call(['unzip', '-o', '-q', zip_path, '-d', dest])
    else:
        import zipfile
        with zipfile.ZipFile(zip_path) as z:
            z.extractall(dest)
    return dest


def parse_dir(d):
    """→ {字: {p:拼音, r:部首字, s:总笔画}}"""
    out = {}
    files = ['Unihan_Readings.txt', 'Unihan_IRGSources.txt', 'Unihan_RadicalStrokeCounts.txt']
    for fn in files:
        p = os.path.join(d, fn)
        if not os.path.exists(p):
            print('  ⚠ 缺 %s，跳过' % fn)
            continue
        n = 0
        with open(p, encoding='utf-8', errors='ignore') as f:
            for line in f:
                if line.startswith('#') or '\t' not in line:
                    continue
                m = LINE.match(line)
                if not m:
                    continue
                cp, field, val = int(m.group(1), 16), m.group(2), m.group(3).strip()
                ch = chr(cp)
                rec = out.setdefault(ch, {})
                if field == 'kMandarin':
                    rec['p'] = val.split()[0]          # 有些字有多个读音，取第一个
                elif field == 'kRSUnicode':
                    # 形如 "4.3" / "4.3'"（简化字另列）→ 只取部首号
                    num = val.split('.')[0].strip("'")
                    if num.isdigit() and 1 <= int(num) <= 214:
                        rec['r'] = RADICALS[int(num) - 1]
                elif field == 'kTotalStrokes':
                    first = val.split()[0]
                    if first.isdigit():
                        rec['s'] = int(first)
                n += 1
        print('  %-34s 读入 %d 行' % (fn, n))
    return {k: v for k, v in out.items() if v}


def fill_pinyin(data):
    """用本地 data/pinyin_readings.json 补 kMandarin 没覆盖到的拼音（只补已有字）。"""
    if not os.path.exists(PINYIN_SRC):
        print('  （无 %s，跳过补拼音）' % os.path.relpath(PINYIN_SRC, ROOT))
        return 0
    src = json.load(open(PINYIN_SRC, encoding='utf-8'))
    filled = 0
    for ch, rec in data.items():
        if rec.get('p') or ch not in src:
            continue
        py = (src[ch] or {}).get('pinyin') or ''
        py = py.strip()
        if py and py != ch:                 # 数据里有「拼音=字本身」的占位，跳过
            rec['p'] = py
            filled += 1
    print('  补拼音 %d 字（来自 pinyin_readings.json）' % filled)
    return filled


def write_shards(data, dry):
    buckets = {}
    for ch, rec in data.items():
        buckets.setdefault(ord(ch) % SHARDS, {})[ch] = rec
    approx = sum(len(json.dumps(b, ensure_ascii=False, separators=(',', ':')).encode())
                 for b in buckets.values())
    print('  统一汉字 %d 字 → %d 片（≈ %.2f MB，平均 %.0f KB/片）'
          % (len(data), len(buckets), approx / 1048576.0, approx / 1024.0 / max(1, len(buckets))))
    if dry:
        return approx
    outdir = os.path.join(OUT, 'unihan')
    os.makedirs(outdir, exist_ok=True)
    for f in os.listdir(outdir):
        if f.endswith('.json'):
            os.remove(os.path.join(outdir, f))
    real = 0
    for n, b in buckets.items():
        p = os.path.join(outdir, '%d.json' % n)
        with open(p, 'w', encoding='utf-8') as fh:
            json.dump(b, fh, ensure_ascii=False, separators=(',', ':'))
        real += os.path.getsize(p)
    print('  ✅ 已写 %s（%.2f MB）' % (os.path.relpath(outdir, ROOT), real / 1048576.0))
    return real


def merge_meta(entries, size, dry):
    old = {}
    if os.path.exists(META):
        try:
            old = json.load(open(META, encoding='utf-8'))
        except Exception:
            old = {}
    by_name = {d['name']: d for d in (old.get('dicts') or [])
               if isinstance(d, dict) and d.get('name')}
    by_name['unihan'] = {'name': 'unihan', 'label': '統一漢字（拼音 · 部首 · 筆畫）',
                         'entries': entries, 'size_kb': round(size / 1024.0)}
    order = ['kangxi', 'shuowen', 'cedict', 'unihan']
    old['dicts'] = [by_name[n] for n in order if n in by_name]
    old.setdefault('shards', SHARDS)
    if dry:
        print('（--dry-run：未写 dict_meta.json）')
        return
    with open(META, 'w', encoding='utf-8') as f:
        json.dump(old, f, ensure_ascii=False, indent=1)
    print('  ✅ dict_meta.json 已并入 unihan（%d 字）' % entries)


def main():
    ap = argparse.ArgumentParser(description='Unihan 瘦身分片：拼音 / 部首 / 笔画')
    ap.add_argument('--src', help='已解压的 Unihan 目录（含 Unihan_*.txt）')
    ap.add_argument('--zip', help='Unihan.zip 路径（自动解压）')
    ap.add_argument('--dry-run', action='store_true', help='只统计体积')
    args = ap.parse_args()

    if args.src:
        d = args.src
    elif args.zip:
        d = extract(args.zip, tempfile.mkdtemp(prefix='unihan_'))
    else:
        cache = os.path.join(tempfile.gettempdir(), 'Unihan.zip')
        d = extract(fetch_zip(cache), tempfile.mkdtemp(prefix='unihan_'))

    data = parse_dir(d)
    if not data:
        sys.exit('❌ 没解析到任何 Unihan 数据（检查 --src / --zip）')
    fill_pinyin(data)
    with_p = sum(1 for v in data.values() if v.get('p'))
    with_s = sum(1 for v in data.values() if v.get('s'))
    with_r = sum(1 for v in data.values() if v.get('r'))
    print('  合并 %d 字（拼音 %d · 笔画 %d · 部首 %d）' % (len(data), with_p, with_s, with_r))
    for ch in ('之', '國', '国'):
        if ch in data:
            print('    样例 %s → %s' % (ch, json.dumps(data[ch], ensure_ascii=False)))

    size = write_shards(data, args.dry_run)
    merge_meta(len(data), size, args.dry_run)


if __name__ == '__main__':
    main()
