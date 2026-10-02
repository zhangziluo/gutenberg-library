#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_wikisource_index.py — 生成「维基文库中文电子书索引」
================================================================
数据来源：zh.wikisource.org 的四部（經/史/子/集）分类 + 四庫全書 + 十三經 +
         史書/詩集 等分类成员（离线快照 /tmp/ws_all.json）
         + 页面长度与作者链接（/tmp/ws_meta.json）。

产出（均落在 文本/新书/）：
  wikisource_index.json   结构化索引（供脚本用）
  wikisource_index.md     可读索引（按四部分类，附 fetch 用法）
  wikisource_index.tsv    制表符清单（供批量脚本）

每条字段：title（显示名）/ page（维基文库页面标题，fetch 用它）/ bu / sub /
          region（中土|域外）/ length / authors / versions / in_library / recommended

重新采集数据的命令见 文本/新书/wikisource_index_guide.md。
"""
import json
import os
import re
from collections import Counter, defaultdict
from urllib.parse import quote

BASE = os.path.dirname(os.path.abspath(__file__))
SITE = os.path.dirname(os.path.dirname(BASE))
OUTJP = os.path.join(BASE, 'wikisource_index.json')
OUTMD = os.path.join(BASE, 'wikisource_index.md')
OUTTSV = os.path.join(BASE, 'wikisource_index.tsv')
# 站点用「待入库」预览数据（书库页「待入库」页签读它）
PENDING_JSON = os.path.join(SITE, '网站', 'assets', 'data', 'wikisource-pending.json')

BU_ORDER = ['經部', '史部', '子部', '集部', '叢部']
SUB_ORDER = {
    '經部': ['易', '書', '詩', '禮', '春秋', '四書', '蒙學', '註疏',
             '十三經總義', '總義', '總類'],
    '史部': ['正史', '別史', '編年', '紀事本末', '雜史', '載記', '政書', '目錄',
             '地理', '域外·日本', '域外·朝鮮', '域外·越南', '域外·琉球', '總類'],
    '子部': ['儒家', '道家', '法家', '名家', '兵家', '農家', '醫家', '雜家',
             '小說家', '類書', '藝術', '譜錄', '蒙學', '釋家', '總類'],
    '集部': ['別集', '總集', '詩', '詞', '曲', '文言散文', '總類'],
    '叢部': ['四庫全書'],
}


# 推荐优先清单（显示名；命中即标 ⭐）
RECOMMENDED = set("""
論語 孟子 詩經 尚書 禮記 周易 周禮 儀禮 春秋左氏傳 春秋公羊傳 春秋穀梁傳
孝經 爾雅 說文解字 大戴禮記 千字文 三字經 百家姓 蒙求 龍文鞭影 幼學瓊林
尚書正義 毛詩正義 禮記正義 論語註疏 孟子註疏 周易正義 周禮註疏 儀禮註疏
爾雅註疏 孝經註疏 春秋左傳註疏 春秋公羊傳註疏 春秋穀梁傳註疏
史記 史記三家註 漢書 後漢書 三國志 晉書 宋書 南齊書 梁書 陳書 魏書 北齊書
周書 隋書 南史 北史 舊唐書 新唐書 舊五代史 新五代史 宋史 遼史 金史 元史 明史
資治通鑑 資治通鑑外紀 國語 戰國策 吳越春秋 越絕書 竹書紀年 水經注 洛陽伽藍記
大唐西域記 佛國記 東京夢華錄 夢粱錄 貞觀政要 唐會要 通典 文獻通考 史通
讀史方輿紀要 天下郡國利病書 華陽國志 三輔黃圖 郡齋讀書志 直齋書錄解題
老子 道德經 莊子 南華真經 列子 沖虛至德真經 墨子 荀子 韓非子 管子 孫子集注
吳子 六韜 三略 司馬法 尉繚子 商子 慎子 尹文子 公孫龍子 鬼谷子 呂氏春秋 淮南子
論衡 潛夫論 鹽鐵論 新書 顏氏家訓 抱朴子 世説新語 搜神記 聊齋志異 閱微草堂筆記
太平廣記 容齋隨筆 夢溪筆談 天工開物 本草綱目 傷寒論 金匱要略 神農本草經
齊民要術 茶經 金剛般若波羅蜜經 六祖壇經 弘明集 景德傳燈錄 雲笈七籤 明儒學案
日知錄 菜根譚 幾何原本 九章算術 周髀算經 太玄經 孔子家語 人物志 困學記聞
永樂大典 初學記 藝文類聚 太平御覽 冊府元龜 說苑 新序 揚子法言 文中子中説 意林
三十六計 孫臏兵法 武經總要 紀效新書
楚辭 文選 六臣註文選 玉臺新詠 樂府詩集 全唐詩 唐詩三百首 千家詩 古文觀止
古文辭類纂 文心雕龍 詩品 人間詞話 隨園詩話 花間集 絕妙好詞 西廂記 牡丹亭
長生殿 桃花扇 竇娥冤 琵琶記 李太白文集 杜工部集 白氏長慶集
四庫全書總目提要 四庫全書簡明目錄
""".split())


def norm_name(s):
    return re.sub(r'\s+', '', s or '')


def sort_key(e):
    bu_i = BU_ORDER.index(e['bu']) if e['bu'] in BU_ORDER else 9
    subs = SUB_ORDER.get(e['bu'], [])
    sub_i = subs.index(e['sub']) if e['sub'] in subs else 99
    return (9 if e['region'] == '域外' else 0, bu_i, sub_i,
            -(e['length'] or 0), e['title'])


def refresh_in_library(out):
    """按当前 library-index.json 重算 in_library（新入库的书自动移出「待入库」）。"""
    lib = os.path.join(SITE, 'library-index.json')
    if not os.path.exists(lib):
        return 0
    try:
        d = json.load(open(lib, encoding='utf-8'))
    except Exception:
        return 0
    have = {norm_name(b.get('book', ''))
            for grp in d['categories'] for b in grp['books']}
    changed = 0
    for e in out:
        hit = norm_name(e['title']) in have
        if hit != bool(e.get('in_library')):
            changed += 1
        e['in_library'] = hit
    return changed


def write_pending(out, today=None):
    """写站点「待入库」预览数据：中土未入库条目（推荐优先 + 全部）。"""
    import datetime
    rows = [e for e in out if e['region'] == '中土' and not e['in_library']]
    rows.sort(key=lambda e: (0 if e.get('recommended') else 1,
                             BU_ORDER.index(e['bu']) if e['bu'] in BU_ORDER else 9,
                             -(e['length'] or 0)))
    payload = {
        'title': '维基文库 · 待入库',
        'updated': today or datetime.date.today().isoformat(),
        'source': 'https://zh.wikisource.org',
        'note': '来自中文维基文库四部分类，尚未上架；点卡片可跳转维基文库原页。',
        'total': len(rows),
        'recommended_total': sum(1 for e in rows if e.get('recommended')),
        'books': [{
            'title': e['title'],
            'author': '、'.join(e['authors']) or '',
            'bu': e['bu'],
            'sub': e['sub'],
            'page': e['page'],
            'recommended': bool(e.get('recommended')),
            'size_kb': round(e['length'] / 1024) if e['length'] else 0,
            'url': 'https://zh.wikisource.org/wiki/' + quote(e['page'].replace(' ', '_')),
        } for e in rows],
    }
    os.makedirs(os.path.dirname(PENDING_JSON), exist_ok=True)
    json.dump(payload, open(PENDING_JSON, 'w', encoding='utf-8'),
              ensure_ascii=False)
    print('→ %s（%d 条，其中推荐 %d）'
          % (PENDING_JSON, payload['total'], payload['recommended_total']))


def write_outputs(out):
    """写 json + tsv + md + 站点待入库数据。"""
    ch = refresh_in_library(out)
    if ch:
        print('↻ in_library 刷新：%d 条变动' % ch)
    out.sort(key=sort_key)
    json.dump(out, open(OUTJP, 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)

    with open(OUTTSV, 'w', encoding='utf-8') as f:
        f.write('page\ttitle\tbu\tsub\tregion\tauthors\tlength\tin_library\n')
        for e in out:
            f.write('\t'.join([
                e['page'], e['title'], e['bu'], e['sub'], e['region'],
                '、'.join(e['authors']), str(e['length'] or ''),
                'Y' if e['in_library'] else '',
            ]) + '\n')

    write_markdown(out)
    write_pending(out)
    print('索引 %d 条；中土 %d / 域外 %d；已入库 %d'
          % (len(out), sum(1 for e in out if e['region'] == '中土'),
             sum(1 for e in out if e['region'] == '域外'),
             sum(1 for e in out if e['in_library'])))
    print('按部：', dict(Counter(e['bu'] for e in out if e['region'] == '中土')))
    print('→', OUTJP)
    print('→', OUTMD)
    print('→', OUTTSV)


def main():
    import argparse
    ap = argparse.ArgumentParser(description='由采集快照生成维基文库索引')
    ap.add_argument('--from-json', action='store_true',
                    help='以已存在的 wikisource_index.json 为源，只重建 json/tsv/md'
                         '（元数据补抓后用，勿再动 /tmp 快照）')
    args = ap.parse_args()

    if args.from_json:
        if not os.path.exists(OUTJP):
            raise SystemExit('缺少 %s' % OUTJP)
        write_outputs(json.load(open(OUTJP, encoding='utf-8')))
        return

    for p in ('/tmp/ws_all.json', '/tmp/ws_meta.json'):
        if not os.path.exists(p):
            raise SystemExit(
                '缺少采集快照 %s。\n'
                '本脚本只做「汇总 → 索引」，采集步骤见 文本/新书/wikisource_index_guide.md；'
                '只想按现有 json 重建目录可加 --from-json。' % p)
    rows = json.load(open('/tmp/ws_all.json', encoding='utf-8'))
    meta = json.load(open('/tmp/ws_meta.json', encoding='utf-8'))
    rec_norm = {norm_name(x) for x in RECOMMENDED}

    # 已有的索引（若有）：元数据缺口回填，避免「重新采集」把补抓结果冲掉
    old = {}
    if os.path.exists(OUTJP):
        try:
            old = {e['page']: e for e in json.load(open(OUTJP, encoding='utf-8'))}
        except Exception:
            old = {}

    out = []
    for r in rows:
        m = meta.get(r['page']) or {}
        prev = old.get(r['page']) or {}
        length = m.get('length')
        if length is None:
            length = prev.get('length')
        authors = m.get('authors') or []
        # 页头 navbox（如《二十四史》模板）会把整系列作者都链进来：>5 视为污染，弃用
        if len(authors) > 5:
            authors = []
        if not authors:
            authors = prev.get('authors') or []
        out.append({
            'title': r['title'],
            'page': r['page'],
            'bu': r['bu'],
            'sub': r['sub'],
            'region': '域外' if r['sub'].startswith('域外·') else '中土',
            'length': length,
            'authors': authors,
            'versions': r.get('versions') or [],
            'sources': r.get('sources') or [],
            'in_library': bool(r.get('in_library')) or bool(prev.get('in_library')),
            'recommended': norm_name(r['title']) in rec_norm,
        })
    write_outputs(out)




HEADER = """# 维基文库 · 中文电子书索引

> 来源：中文维基文库（zh.wikisource.org）四部分类快照。
> 复制下表「页面标题」到 `fetch` 即可下载；`✅` 已入库、`⭐` 推荐优先。
> 生成：`文本/新书/build_wikisource_index.py`（采集说明见 `wikisource_index_guide.md`）。

## 用法

```bash
# 单本抓取（产物 novels_json/<书名>.json）
cd 文本/新书/wikisource_complete_toolkit
python3 wikisource_toolkit.py fetch "論語"      # 参数＝下表「页面标题」

# 一键入库（抓取 → 许可闸门 → data/books → library-index → merge_to_site）
cd 文本/新书
bash add_books.sh --source wikisource --title "論語" \\
     --author 孔子 --category 經部 --subcategory 四書 --label 篇
```

> 合规：`wikisource_toolkit.py` 逐页判定版权模板，仅 `safe_to_use` 页面入库。

"""


def write_markdown(out):
    by_rec = [e for e in out if e['recommended'] and not e['in_library']]
    dom = [e for e in out if e['region'] == '中土']
    wai = [e for e in out if e['region'] == '域外']
    L = [HEADER]
    L.append('共 **%d** 种（中土 %d · 域外漢籍 %d），已入库 **%d** 种。'
             % (len(out), len(dom), len(wai), sum(1 for e in out if e['in_library'])))
    L.append('')
    L.append('## 推荐优先（未入库，⭐ %d 种）' % len(by_rec))
    L.append('')
    for e in by_rec:
        auth = ('　' + '、'.join(e['authors'])) if e['authors'] else ''
        L.append('- ⭐ **%s**%s（%s·%s） —— `fetch "%s"`'
                 % (e['title'], auth, e['bu'], e['sub'], e['page']))
    L.append('')
    emit_sections(L, dom, '中土典籍（按四部）')
    emit_sections(L, wai, '附：域外漢籍（日·朝·越·琉球，可选）')
    open(OUTMD, 'w', encoding='utf-8').write('\n'.join(L) + '\n')


def emit_sections(L, section_rows, title):
    L.append('## ' + title)
    L.append('')
    groups = defaultdict(list)
    for e in section_rows:
        groups[(e['bu'], e['sub'])].append(e)
    for bu in BU_ORDER:
        subs = [s for s in SUB_ORDER.get(bu, []) if (bu, s) in groups]
        subs += [s for (b, s) in groups
                 if b == bu and s not in SUB_ORDER.get(bu, [])]
        if not subs:
            continue
        L.append('### %s' % bu)
        L.append('')
        for sub in subs:
            items = groups[(bu, sub)]
            L.append('#### %s（%d）' % (sub, len(items)))
            L.append('')
            for e in items:
                mark = ' ✅' if e['in_library'] else (' ⭐' if e['recommended'] else '')
                auth = ('　' + '、'.join(e['authors'])) if e['authors'] else ''
                size = ('　%.0f KB' % (e['length'] / 1024)) if e['length'] else ''
                extra = ('（页面：`%s`）' % e['page']) if e['page'] != e['title'] else ''
                L.append('- %s%s%s%s%s' % (e['title'], auth, extra, size, mark))
            L.append('')


if __name__ == '__main__':
    main()

