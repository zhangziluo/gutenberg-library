#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_dict_shards.py — 把离线词典拆成「按需加载」的分片（仓库内版本）
================================================================
为什么分片：康熙 11.9 MB / CC-CEDICT 11.5 MB，整包加载太慢；按**首字码点 % N**
分片后，前端查某字/某词只取 1 片（浏览器缓存后基本瞬时）。

源（文本/新书/data/，均 gitignore 于外部生成）：
  kangxi.json        {字: 康熙释义}          48710 条
  shuowen.json       {字: 说文释义}           9815 条
  cedict_words.json  {词: 英文释义}         198266 条（CC-CEDICT）
产物：
  网站/_site_data/dict/<name>/<n>.json      n = ord(首字) % shards
  网站/_site_data/dict/dict_meta.json       {shards, dicts:[{name,label,entries,size_kb}], note}

用法：
  python3 文本/新书/build_dict_shards.py            # 默认 128 片
  python3 文本/新书/build_dict_shards.py --only cedict
"""
import argparse
import json
import os

BASE = os.path.dirname(os.path.abspath(__file__))          # 文本/新书
ROOT = os.path.dirname(os.path.dirname(BASE))
SRC = os.path.join(BASE, 'data')
OUT = os.path.join(ROOT, '网站', '_site_data', 'dict')

# (输出名, 展示名, 源文件名) —— 源在 文本/新书/data/<src>.json
DICTS = [('kangxi', '康熙字典', 'kangxi'),
         ('shuowen', '说文解字', 'shuowen'),
         ('cedict', 'CC-CEDICT 英汉', 'cedict_words')]


def shard(name, srcname, shards):
    src = os.path.join(SRC, srcname + '.json')
    if not os.path.exists(src):
        print('⚠ 缺 %s，跳过' % src)
        return None
    d = json.load(open(src, encoding='utf-8'))
    buckets = {}
    for w, gloss in d.items():
        if not w:
            continue
        buckets.setdefault(ord(w[0]) % shards, {})[w] = gloss
    outdir = os.path.join(OUT, name)
    os.makedirs(outdir, exist_ok=True)
    # 清掉旧分片（片数变更时不残留）
    for f in os.listdir(outdir):
        if f.endswith('.json'):
            os.remove(os.path.join(outdir, f))
    total = 0
    for n, b in buckets.items():
        p = os.path.join(outdir, '%d.json' % n)
        with open(p, 'w', encoding='utf-8') as fh:
            json.dump(b, fh, ensure_ascii=False, separators=(',', ':'))
        total += os.path.getsize(p)
    print('  %-8s %6d 条 → %d 片（%.1f MB，平均 %.0f KB/片）'
          % (name, len(d), len(buckets), total / 1048576.0,
             total / 1024.0 / max(1, len(buckets))))
    return {'name': name, 'entries': len(d), 'size_kb': round(total / 1024.0)}


def main():
    ap = argparse.ArgumentParser(description='离线词典分片')
    ap.add_argument('--shards', type=int, default=128)
    ap.add_argument('--only', default='', help='只处理某个词典（kangxi/shuowen/cedict）')
    args = ap.parse_args()

    os.makedirs(OUT, exist_ok=True)
    info = []
    for name, label, srcname in DICTS:
        if args.only and args.only != name:
            continue
        r = shard(name, srcname, args.shards)
        if r:
            r['label'] = label
            info.append(r)

    meta_path = os.path.join(OUT, 'dict_meta.json')
    old = {}
    if os.path.exists(meta_path):
        try:
            old = json.load(open(meta_path, encoding='utf-8'))
        except Exception:
            old = {}
    # 合并旧信息（--only 时不丢其它词典）
    merged = {d['name']: d for d in (old.get('dicts') or []) if isinstance(d, dict) and d.get('name')}
    for d in info:
        merged[d['name']] = d
    order = [n for n, _l, _s in DICTS]
    dicts = [merged[n] for n in order if n in merged]
    with open(meta_path, 'w', encoding='utf-8') as f:
        json.dump({'shards': args.shards, 'dicts': dicts,
                   'note': '按「首字码点 % shards」取分片：_site_data/dict/<name>/<n>.json'},
                  f, ensure_ascii=False, indent=1)
    print('✅ dict_meta.json：%s' % '、'.join('%s(%d)' % (d['name'], d['entries']) for d in dicts))


if __name__ == '__main__':
    main()
