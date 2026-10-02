#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
wikisource_batch.py — 维基文库「推荐优先」清单：批量抓取 + 生成/执行入库命令
================================================================================
数据源：`文本/新书/wikisource_index.json`（维基文库索引，含 recommended / in_library）。

三个子命令：
  list       列出候选（默认 = 推荐 ⭐ 且未入库、中土），写 `_ws_fetch/selected.tsv`
  fetch      按清单批量抓取 → `wikisource_complete_toolkit/novels_json/<书名>.json`
  commands   生成「入库命令脚本」`_ws_fetch/ingest_commands.sh`（可人工审阅/改参数）
  ingest     执行入库：wikisource_import（**智能分章 + 生成注释**）→ 批量结束后
             **释义回填** fill_glosses.py → merge_to_site / slim_books_index（可选 build）

状态（断点续跑）：
  `_ws_fetch/fetch_state.tsv`   已抓 / 失败
  `_ws_fetch/ingest_state.tsv`  已入库 / 失败

用法（任意目录；**用项目 .venv 的解释器**，脚本也会自动改用它跑 toolkit）：
  .venv/bin/python 文本/新书/wikisource_batch.py list
  .venv/bin/python 文本/新书/wikisource_batch.py fetch  --limit 10   # 抓 10 本试水
  .venv/bin/python 文本/新书/wikisource_batch.py fetch               # 抓完候选清单
  .venv/bin/python 文本/新书/wikisource_batch.py commands            # 导出命令脚本
  .venv/bin/python 文本/新书/wikisource_batch.py ingest --limit 10   # 入库 + 释义回填
  .venv/bin/python 文本/新书/wikisource_batch.py ingest              # 全部

常用开关：
  --page <子串>  只处理页面标题含该子串的（增量/试跑）
  --all          候选放宽为「所有未入库的中土条目」（默认只取 recommended ⭐）
  --strict       合规更严：不跳过「许可未知」页面（默认跳过，等同 --force）
  --no-gloss     入库后不做释义回填
  --no-merge     入库后不重建目录/阅读器数据
  --build        入库后再跑 deploy/build.sh
  --dry-run      只打印将执行的命令，不实际执行
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(BASE))
INDEX = os.path.join(BASE, 'wikisource_index.json')
TOOLKIT = os.path.join(BASE, 'wikisource_complete_toolkit')
NOVELS = os.path.join(TOOLKIT, 'novels_json')
STATE_DIR = os.path.join(BASE, '_ws_fetch')
SELECTED = os.path.join(STATE_DIR, 'selected.tsv')
FETCH_STATE = os.path.join(STATE_DIR, 'fetch_state.tsv')
INGEST_STATE = os.path.join(STATE_DIR, 'ingest_state.tsv')
CMD_FILE = os.path.join(STATE_DIR, 'ingest_commands.sh')

# 抓取单本的超时（秒）——大部头（资治通鉴等）子页多，给足
FETCH_TIMEOUT = 1800


def _pick_python():
    """优先项目 .venv（toolkit 需要 requests/beautifulsoup4），否则当前解释器。"""
    cand = os.environ.get('WS_PYTHON')
    if cand and os.path.exists(cand):
        return cand
    venv = os.path.join(ROOT, '.venv', 'bin', 'python')
    if os.path.exists(venv):
        return venv
    return sys.executable


PY = _pick_python()


def sanitize(title):
    """与 add_books.sh 一致的文件名归一（toolkit 产物名）。"""
    s = re.sub(r'[^\w\u4e00-\u9fff]+', '_', title).strip('_')
    return s or 'book'


def novel_path(page):
    return os.path.join(NOVELS, sanitize(page) + '.json')


def load_entries():
    if not os.path.exists(INDEX):
        sys.exit('缺少 %s' % INDEX)
    return json.load(open(INDEX, encoding='utf-8'))


def select(entries, all_flag, order='size'):
    out = []
    for e in entries:
        if e['region'] != '中土' or e['in_library']:
            continue
        if all_flag or e.get('recommended'):
            out.append(e)
    if order == 'default':
        # 四部顺序（經→史→子→集→叢）
        out.sort(key=lambda e: (0 if e.get('recommended') else 1, e['bu'], e['title']))
    else:
        # size（默认）：小书在前 —— 先出成果，不被《四庫全書總目提要》这类大部头卡住
        out.sort(key=lambda e: (0 if e.get('recommended') else 1,
                                e['length'] if e['length'] else 10 ** 9,
                                e['title']))
    return out


def author_of(e):
    return (e.get('authors') or ['佚名'])[0]


def filter_page(entries, needle):
    if not needle:
        return entries
    return [e for e in entries if needle in e['page'] or needle in e['title']]


def _read_state(path):
    st = {}
    if os.path.exists(path):
        for line in open(path, encoding='utf-8'):
            p = line.rstrip('\n').split('\t')
            if len(p) >= 2:
                st[p[0]] = p[1]
    return st


def _append_state(path, page, status):
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(path, 'a', encoding='utf-8') as f:
        f.write('%s\t%s\t%s\n' % (page, status, time.strftime('%Y-%m-%d %H:%M:%S')))


def cmd_list(args):
    entries = filter_page(select(load_entries(), args.all, args.order), args.page)
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(SELECTED, 'w', encoding='utf-8') as f:
        f.write('page\ttitle\tauthor\tbu\tsub\tlength\tfetched\n')
        for e in entries:
            f.write('\t'.join([
                e['page'], e['title'], author_of(e), e['bu'], e['sub'],
                str(e['length'] or ''),
                'Y' if os.path.exists(novel_path(e['page'])) else '',
            ]) + '\n')
    print('候选 %d 条（%s）→ %s'
          % (len(entries), '全部未入库中土' if args.all else '推荐 ⭐ 未入库',
             os.path.relpath(SELECTED, ROOT)))
    from collections import Counter
    print('  按部：', dict(Counter(e['bu'] for e in entries)))
    fetched = sum(1 for e in entries if os.path.exists(novel_path(e['page'])))
    print('  已抓取：%d / %d' % (fetched, len(entries)))


def _run(cmd, cwd=None, timeout=None, dry=False):
    print('    $ ' + ' '.join(cmd), flush=True)
    if dry:
        return 0
    try:
        return subprocess.run(cmd, cwd=cwd, timeout=timeout).returncode
    except subprocess.TimeoutExpired:
        print('    ⏱ 超时（%ss），记失败' % timeout, flush=True)
        return 124


def cmd_fetch(args):
    entries = filter_page(select(load_entries(), args.all, args.order), args.page)
    if args.limit:
        entries = entries[:args.limit]
    os.makedirs(NOVELS, exist_ok=True)
    min_chars = args.min_chars or 0
    st = _read_state(FETCH_STATE)
    ok = skip = fail = empty = 0
    for i, e in enumerate(entries, 1):
        page = e['page']
        path = novel_path(page)
        n_have = novel_text_len(path) if os.path.exists(path) else 0
        if n_have >= min_chars:
            skip += 1
            continue
        if st.get(page) in ('fail', 'empty') and not args.retry_failed:
            skip += 1
            continue
        print('\n[%d/%d] %s（%s·%s%s）'
              % (i, len(entries), page, e['bu'], e['sub'],
                 '，%s' % '、'.join(e['authors']) if e['authors'] else ''),
              flush=True)
        rc = _run([PY, 'wikisource_toolkit.py', 'fetch', page],
                  cwd=TOOLKIT, timeout=FETCH_TIMEOUT, dry=args.dry_run)
        if args.dry_run:
            continue
        # 注意：toolkit 即使每个页面都抓失败也返回 0（会存下一个空壳 JSON），
        # 所以「成功」要以**抓到的正文量**为准，不能只看退出码。
        n = novel_text_len(path) if os.path.exists(path) else 0
        if n >= min_chars:
            ok += 1
            _append_state(FETCH_STATE, page, 'ok')
        elif n > 0:
            fail += 1
            print('    ⚠️ 正文过少（%d 字 < %d），记 fail 待重试' % (n, min_chars))
            _append_state(FETCH_STATE, page, 'fail')
        else:
            empty += 1
            print('    ⚠️ 没抓到可用正文（网络失败或红链空壳），记 empty')
            _append_state(FETCH_STATE, page, 'empty')
        time.sleep(1.0)          # 礼貌间隔
    print('\n抓取完成：新抓 %d / 跳过 %d / 失败 %d / 空壳 %d（产物 %s）'
          % (ok, skip, fail, empty, os.path.relpath(NOVELS, ROOT)))
    if fail or empty:
        print('   可重试：加 --retry-failed（fail 与 empty 都会重试）')


def ingest_cmd_for(e, strict):
    """单本入库命令（wikisource_import）。"""
    path = novel_path(e['page'])
    cmd = [PY, os.path.join(BASE, 'wikisource_import.py'),
           '--json', path,
           '--title', e['title'],      # 去掉版本后缀的显示名
           '--author', author_of(e),
           '--category', e['bu'],
           '--subcategory', e['sub'],
           '--split', 'auto']          # 智能分章（自动识别 卷/回/篇/章…）
    if not strict:
        cmd.append('--force')         # 跳过「许可未知」页面，其余照收
    cmd.append('--no-merge')          # 逐本不重建；批量结束后统一 rebuild（快得多）
    return cmd


def cmd_commands(args):
    entries = filter_page(select(load_entries(), args.all, args.order), args.page)
    os.makedirs(STATE_DIR, exist_ok=True)
    lines = ['#!/usr/bin/env bash',
             '# 维基文库「推荐清单」入库命令（由 wikisource_batch.py commands 生成）',
             '# 每本：wikisource_import.py —— 内含智能分章 + 生成注释；',
             '# 批量跑完后统一做释义回填（fill_glosses）+ 重建（merge_to_site）。',
             'set -u',
             'cd "$(git -C "$(dirname "$0")" rev-parse --show-toplevel 2>/dev/null || echo .)"',
             '']
    n = 0
    skipped = []
    for e in entries:
        p = novel_path(e['page'])
        if not os.path.exists(p):
            continue
        if novel_text_len(p) < (args.min_chars or 0):
            skipped.append(e['title'])
            continue
        n += 1
        lines.append('echo "==> 《%s》"' % e['title'])
        lines.append(' '.join("'%s'" % a if (' ' in a or '　' in a or not a)
                              else a for a in ingest_cmd_for(e, args.strict)))
        lines.append('')
    if skipped:
        lines.append('# 以下 %d 本抓取结果正文过少（红链/空壳），已跳过：' % len(skipped))
        for t in skipped:
            lines.append('#   - %s' % t)
        lines.append('')
    lines += ['echo "==> 释义回填 fill_glosses.py"',
              '%s 文本/新书/fill_glosses.py' % PY,
              '',
              'echo "==> 重建目录页 + 阅读器数据"',
              '%s 文本/新书/wikisource_batch.py merge' % PY,
              '']
    with open(CMD_FILE, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
    os.chmod(CMD_FILE, 0o755)
    print('已生成 %s（含 %d 本，均已抓取）' % (os.path.relpath(CMD_FILE, ROOT), n))
    print('可直接运行：bash %s' % os.path.relpath(CMD_FILE, ROOT))



def _run_merge():
    """重建目录页 + 阅读器数据（merge_to_site + slim_books_index）。"""
    code = (
        "import os,sys; sys.path.insert(0, %r); "
        "import gutenberg_import, slim_books_index; "
        "gutenberg_import.merge_to_site(); "
        "slim_books_index.slim_into(os.path.join(%r, '网站', '_site_data'))"
        % (BASE, ROOT))
    return _run([PY, '-c', code])


def novel_text_len(path):
    """抓取产物里「可用章节」的正文字数（用于挡掉红链导致空壳的书）。"""
    try:
        d = json.load(open(path, encoding='utf-8'))
    except Exception:
        return 0
    return sum(len(c.get('content_text') or '')
               for c in d.get('chapters', []) if c.get('safe_to_use'))


def cmd_ingest(args):
    entries = filter_page(select(load_entries(), args.all, args.order), args.page)
    if args.limit:
        entries = entries[:args.limit]
    st = _read_state(INGEST_STATE)

    todo, empty = [], []
    for e in entries:
        p = novel_path(e['page'])
        if not os.path.exists(p) or st.get(e['page']) == 'ok':
            continue
        if novel_text_len(p) < (args.min_chars or 0):
            empty.append(e)
        else:
            todo.append(e)
    print('已抓取且未入库：%d 本' % len(todo))
    if empty:
        print('⚠️ 跳过 %d 本（正文过少，多为红链/空壳）：%s'
              % (len(empty), '、'.join(e['title'] for e in empty[:8])))
    if not todo and not args.force_gloss:
        print('没有需要入库的（如需仅重跑释义回填：--force-gloss）')
        return

    ok = fail = 0
    for i, e in enumerate(todo, 1):
        print('\n[%d/%d] 入库《%s》' % (i, len(todo), e['title']), flush=True)
        rc = _run(ingest_cmd_for(e, args.strict), dry=args.dry_run)
        if args.dry_run:
            continue
        if rc == 0:
            ok += 1
            _append_state(INGEST_STATE, e['page'], 'ok')
        else:
            fail += 1
            _append_state(INGEST_STATE, e['page'], 'fail')
    print('\n入库完成：成功 %d / 失败 %d' % (ok, fail))

    if args.dry_run:
        return

    # ── 释义回填（网站释义：zh_cn/zh_tw/en/note）──
    if not args.no_gloss:
        print('\n==> 释义回填（fill_glosses.py）', flush=True)
        gloss_cmd = [PY, os.path.join(BASE, 'fill_glosses.py')]
        if args.offline:
            gloss_cmd.append('--no-network')
        _run(gloss_cmd)

    # ── 重建目录/阅读器数据 ──
    if not args.no_merge:
        print('\n==> 重建目录页 + 阅读器数据（merge_to_site）', flush=True)
        _run_merge()

    if args.build:
        print('\n==> deploy/build.sh', flush=True)
        _run(['bash', os.path.join(ROOT, 'deploy', 'build.sh')])

    print('\n🎉 完成。若要提交：git add -A && git commit -m "维基文库入库：%d 本" && git push'
          % ok)


def cmd_merge(args):
    """重建目录页 + 阅读器数据（merge_to_site + slim_books_index）。"""
    print('==> merge_to_site + slim_books_index')
    rc = _run_merge()
    if rc != 0:
        print('⚠️ 重建失败（退出码 %d）' % rc)
    else:
        print('✅ 已重建 网站/assets/data/books-data.json 与 网站/_site_data/')


def main():
    ap = argparse.ArgumentParser(
        description='维基文库「推荐优先」清单：批量抓取 + 入库（智能分章 + 释义回填）')
    sub = ap.add_subparsers(dest='cmd')

    def common(p):
        p.add_argument('--all', action='store_true',
                       help='候选放宽为「所有未入库的中土条目」')
        p.add_argument('--limit', type=int, default=0, help='只处理前 N 本')
        p.add_argument('--page', default='', help='只处理页面标题含该子串的条目')
        p.add_argument('--order', choices=['size', 'default'], default='size',
                       help='候选排序：size（默认，小书在前）/ default（四部顺序）')
        p.add_argument('--strict', action='store_true',
                       help='合规更严：不跳过「许可未知」页面（默认跳过）')
        p.add_argument('--dry-run', action='store_true', help='只打印命令，不执行')

    p = sub.add_parser('list', help='列出候选清单')
    common(p)
    p = sub.add_parser('fetch', help='批量抓取')
    common(p)
    p.add_argument('--retry-failed', action='store_true', help='重试上次失败/空壳的')
    p.add_argument('--min-chars', type=int, default=200,
                   help='正文字数下限（默认 200；低于此视为抓取失败/红链空壳，记 fail|empty 待重试）')
    p = sub.add_parser('commands', help='生成入库命令脚本')
    common(p)
    p.add_argument('--min-chars', type=int, default=200,
                   help='正文字数下限（默认 200；低于此视为红链空壳，跳过并注释说明）')
    p = sub.add_parser('ingest', help='入库 + 释义回填 + 重建')
    common(p)
    p.add_argument('--no-gloss', action='store_true', help='不做释义回填')
    p.add_argument('--offline', action='store_true', help='回填不联网（只用本地词典）')
    p.add_argument('--no-merge', action='store_true', help='不重建目录/阅读器数据')
    p.add_argument('--build', action='store_true', help='再跑 deploy/build.sh')
    p.add_argument('--force-gloss', action='store_true',
                   help='即使没有待入库的书，也重跑一次释义回填')
    p.add_argument('--min-chars', type=int, default=200,
                   help='正文字数下限（默认 200；低于此视为红链空壳，跳过）')
    p = sub.add_parser('merge', help='只重建目录页 + 阅读器数据')

    args = ap.parse_args()
    if not args.cmd:
        ap.print_help()
        return
    {'list': cmd_list, 'fetch': cmd_fetch,
     'commands': cmd_commands, 'ingest': cmd_ingest,
     'merge': cmd_merge}[args.cmd](args)


if __name__ == '__main__':
    main()

