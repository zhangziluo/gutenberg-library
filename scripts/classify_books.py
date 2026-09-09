#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
classify_books.py（v2）— 书站自动分类脚本
============================================================
读取书库 JSON（列表，元素含 id/title/author/language/level/category），
调用 DeepSeek API 为每本书输出两个字段：

  * category（中英文通用）：经 / 史 / 子 / 集 / 丛，按内容性质判断，不确定归「子部」
  * level（仅英文书）：初级 / 中级 / 高级，按词汇难度与句长判断
    （中文书不适用：level 字段保持原值空 / "-"）

  用法：
  python3 scripts/classify_books.py                          # 默认读 data/books.json
  python3 scripts/classify_books.py --input data/books.json  # 指定文件
  python3 scripts/classify_books.py --dry-run                # 只打印结果，不写文件
  python3 scripts/classify_books.py --batch-size 20          # 每批 20 本送 API
  python3 scripts/classify_books.py --only-empty             # 只处理空分类的书
  python3 scripts/classify_books.py --force                  # 忽略已有分类，全部重新分
                                                            # （会覆盖 --only-empty 的空分类过滤）

环境变量：
  DEEPSEEK_API_KEY=sk-XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX（必需，勿在仓库提交真实密钥）

行为约定：
  - 写回前先把原 JSON 备份为 {输入路径}.bak（如 data/books.json.bak）
  - 每批请求之间 time.sleep(0.5) 限流
  - 错误只记录到 logs/classify.log，不中断整批流程
  - 默认会把文件中所有书都重新送 API（含已有分类者，返回不同值才会覆盖写回）；
    --only-empty 只送空分类的书；--force 与 --only-empty 同用时空分类过滤失效，全部重分
  - 使用前建议先 --dry-run --only-empty / --force 试水
"""
import json
import os
import argparse
import logging
import time
from pathlib import Path
from urllib.request import Request, urlopen

API_URL = 'https://api.deepseek.com/chat/completions'
MODEL = 'deepseek-v4-flash'
DEFAULT_INPUT = 'data/books.json'
BATCH_SLEEP = 0.5
LOG_FILE = Path('logs') / 'classify.log'

# category 合法取值（同时兼容传统字形 / 带「部」写法，统一到简体单字或「子部」）
CATEGORY_OK = {'经', '史', '子', '集', '丛', '子部'}
CATEGORY_FIX = {
    '經': '经', '經部': '经', '经部': '经',
    '叢': '丛', '叢部': '丛', '丛部': '丛',
    '史部': '史', '集部': '集', '諸子': '子', '子類': '子',
}
# level 合法取值
LEVEL_OK = {'初级', '中级', '高级'}


def _lang_kind(lang):
    """语言归一：en / zh / None（未知）。"""
    s = str(lang or '').strip().lower()
    if s.startswith('en'):
        return 'en'
    if s.startswith(('zh', 'chi')) or s.startswith('中'):
        return 'zh'
    return None


def is_english(book):
    return _lang_kind(book.get('language')) == 'en'


def needs_classification(book):
    """--only-empty 判定：category 为空，或（英文书且 level 为空/-）→ 需要处理。"""
    cat = str(book.get('category') or '').strip()
    if not cat:
        return True
    if is_english(book):
        lv = str(book.get('level') or '').strip()
        if not lv or lv == '-':
            return True
    return False


def normalize_level(value):
    """level 归一到 初级/中级/高级；'-' 或非法值返回 None（表示不写入）。"""
    if value is None:
        return None
    s = str(value).strip()
    if not s or s == '-':
        return None
    return s if s in LEVEL_OK else None


def normalize_category(value):
    """category 归一到 经/史/子/集/丛/子部；非法值返回 None（表示不写入）。"""
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    s = s.split('/')[0].strip()          # 「子部/古籍」→「子部」
    s = CATEGORY_FIX.get(s, s)
    if s in CATEGORY_OK:
        return s
    return None
PROMPT_TEMPLATE = (
    '请为以下书籍同时输出两个分类标签：\n'
    '1. level（仅英文书需要，中文书填"-"）：初级/中级/高级，按词汇难度和句长判断\n'
    '2. category（中英文通用）：经/史/子/集/丛，按内容性质判断\n'
    '   - 经：宗教经典、道德箴言\n'
    '   - 史：历史、传记、游记、地理\n'
    '   - 子：哲学、科学、小说、戏剧、政治、心理\n'
    '   - 集：诗歌、散文、书信、文学评论\n'
    '   - 丛：合集、全集、选集\n'
    '   - 不确定归"子部"\n'
    '\n'
    '只输出 JSON 数组，格式：[{"id": xxx, "level": "中级", "category": "子部"}, ...]\n'
    '不要输出其他内容。\n'
)


def _strip_fences(text):
    """去掉可能的 ```json / ``` 代码围栏行。"""
    cleaned = []
    for line in text.splitlines():
        if line.strip().lower() in ('```', '```json'):
            continue
        cleaned.append(line)
    return '\n'.join(cleaned)


def parse_classified(content):
    """解析 API 返回的分类 JSON 数组 → [{'id','level','category'}, ...]。
    容忍代码围栏、前后杂文；任何一步失败返回空列表（不抛异常）。"""
    text = _strip_fences(str(content or ''))
    data = None
    for cand in (text, text.strip()):
        try:
            data = json.loads(cand)
            break
        except Exception:
            data = None
    if data is None:
        start, end = text.find('['), text.rfind(']')
        if start != -1 and end > start:
            try:
                data = json.loads(text[start:end + 1])
            except Exception:
                data = None
    if not isinstance(data, list):
        return []
    out = []
    for item in data:
        if not isinstance(item, dict) or item.get('id') is None:
            continue
        out.append({
            'id': str(item.get('id')),
            'level': normalize_level(item.get('level')),
            'category': normalize_category(item.get('category')),
        })
    return out


def chunk_books(books, size):
    for i in range(0, len(books), size):
        yield books[i:i + size]


def build_prompt(batch):
    """组装一批书籍的 prompt。id 数字不带引号、字符串加引号，便于 AI 原样回显。"""
    lines = []
    for idx, b in enumerate(batch, 1):
        raw_id = b.get('id')
        if isinstance(raw_id, int):
            id_txt = str(raw_id)
        else:
            id_txt = '"' + str(raw_id).replace('"', '”') + '"'
        title = str(b.get('title') or '').replace('"', '”')
        author = str(b.get('author') or '未知').replace('"', '”')
        lang = str(b.get('language') or 'zh').strip() or 'zh'
        lines.append('%d. id=%s, title="%s", author="%s", lang=%s'
                     % (idx, id_txt, title, author, lang))
    return PROMPT_TEMPLATE + '\n\n书籍列表：\n' + '\n'.join(lines)
def _setup_logging():
    """配置日志：logs/classify.log + 控制台（stderr）。重复调用安全。"""
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    root = logging.getLogger()
    if root.level == logging.WARNING:
        root.setLevel(logging.INFO)
    fmt = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
    if not any(isinstance(h, logging.FileHandler) for h in root.handlers):
        try:
            fh = logging.FileHandler(str(LOG_FILE), encoding='utf-8')
            fh.setFormatter(fmt)
            root.addHandler(fh)
        except Exception as e:  # 日志文件写不了不阻断主流程
            root.error('无法创建日志文件 %s: %s', LOG_FILE, e)
    if not any(isinstance(h, logging.StreamHandler) for h in root.handlers):
        sh = logging.StreamHandler()
        sh.setFormatter(fmt)
        root.addHandler(sh)


def load_books(path_str):
    """读取并校验书库 JSON；非列表或读取失败抛异常（由 main 捕获记录）。"""
    p = Path(path_str)
    if not p.exists():
        raise FileNotFoundError('输入文件不存在: %s' % p)
    data = json.loads(p.read_text(encoding='utf-8-sig'))
    if not isinstance(data, list):
        raise ValueError('输入文件应为 JSON 数组（每本一个对象）: %s' % p)
    return data


def backup_file(path_str):
    """写回前备份：复制原文件为 {路径}.bak。"""
    src = Path(path_str)
    bak = Path(str(src) + '.bak')
    bak.write_bytes(src.read_bytes())
    logging.info('已备份原文件 → %s', bak)
    return bak


def write_books(path_str, books):
    Path(path_str).write_text(
        json.dumps(books, ensure_ascii=False, indent=2), encoding='utf-8')


def call_api(prompt, api_key):
    """调用 DeepSeek chat/completions，返回 message.content；失败记日志返回 None。"""
    payload = {
        'model': MODEL,
        'messages': [{'role': 'user', 'content': prompt}],
        'temperature': 0,
        'stream': False,
    }
    req = Request(API_URL, data=json.dumps(payload).encode('utf-8'),
                  headers={
                      'Content-Type': 'application/json',
                      'Authorization': 'Bearer ' + api_key,
                  })
    try:
        with urlopen(req, timeout=120) as resp:
            raw = resp.read().decode('utf-8', 'replace')
        data = json.loads(raw)
        return data['choices'][0]['message']['content']
    except Exception as e:
        logging.error('API 请求失败: %s', e)
        return None
def apply_results(batch, parsed):
    """把解析出的分类结果写回 batch 中的书。返回成功更新本数。
    - category 中英文通用，正常覆盖；
    - level 仅英文书写入，中文书保持原值；'-'/非法值不覆盖。"""
    by_id = {}
    for r in parsed:
        if r['id'] not in by_id:
            by_id[r['id']] = r
    changed = 0
    for b in batch:
        key = str(b.get('id'))
        r = by_id.get(key)
        title = str(b.get('title') or '')
        if r is None:
            logging.warning('id=%s（%s）未在 API 返回中，跳过（可下批重试）', key, title)
            continue
        cat, lv = r['category'], r['level']
        if cat is not None:
            old = str(b.get('category') or '').strip()
            if old != cat:
                b['category'] = cat
            else:
                cat = None  # 未实际变化
        if is_english(b):
            if lv is not None:
                old = str(b.get('level') or '').strip()
                if old != lv:
                    b['level'] = lv
                else:
                    lv = None  # 未实际变化
            else:
                logging.info('英文书 id=%s（%s）level 未返回有效值，保持原值', key, title)
        else:
            lv = None  # 中文书 level 一律不动
        if cat is not None or lv is not None:
            changed += 1
        logging.info('分类完成 id=%s title=%s → category=%s level=%s',
                     key, title, b.get('category'), b.get('level'))
    return changed


def main(argv=None):
    parser = argparse.ArgumentParser(
        description='调用 DeepSeek API 为书库 JSON 自动输出四部 category 与英文难度 level')
    parser.add_argument('--input', default=DEFAULT_INPUT,
                        help='书库 JSON 路径（默认 data/books.json）')
    parser.add_argument('--dry-run', action='store_true',
                        help='只打印分类结果，不备份、不写回文件')
    parser.add_argument('--batch-size', type=int, default=20,
                        help='每批送 API 的书数量（默认 20）')
    parser.add_argument('--only-empty', action='store_true',
                        help='只处理 level/category 为空的书')
    parser.add_argument('--force', action='store_true',
                        help='忽略已有分类，把文件里所有书都重新送 API 分类'
                             '（会覆盖 --only-empty 的空分类过滤）')
    args = parser.parse_args(argv)
    _setup_logging()
    logging.info('启动 classify_books v2 input=%s dry_run=%s batch_size=%d only_empty=%s force=%s',
                 args.input, args.dry_run, args.batch_size, args.only_empty, args.force)

    try:
        books = load_books(args.input)
    except Exception as e:
        logging.error('%s', e)
        raise SystemExit(1)
    if args.batch_size < 1:
        logging.error('--batch-size 必须 ≥ 1')
        raise SystemExit(1)

    if args.force:
        targets = list(books)   # --force：忽略已有分类（含 --only-empty 过滤），全部重新分类
        logging.info('--force 已启用：忽略已有分类，全部 %d 本重新送 API 分类', len(targets))
    else:
        targets = [b for b in books if (not args.only_empty) or needs_classification(b)]
    if not targets:
        logging.info('没有需要分类的书（文件为空，或 --only-empty 过滤后已全部分类；如需全量重分请加 --force）')
        return
    if not os.environ.get('DEEPSEEK_API_KEY', '').strip():
        logging.error('未设置环境变量 DEEPSEEK_API_KEY，无法调用 DeepSeek API')
        raise SystemExit(1)
    api_key = os.environ['DEEPSEEK_API_KEY'].strip()

    logging.info('待分类 %d 本，按每批 %d 本分 %d 批',
                 len(targets), args.batch_size,
                 (len(targets) + args.batch_size - 1) // args.batch_size)
    changed = 0
    for batch_no, batch in enumerate(chunk_books(targets, args.batch_size), 1):
        logging.info('── 第 %d 批（%d 本）──', batch_no, len(batch))
        content = call_api(build_prompt(batch), api_key)
        if content is not None:
            parsed = parse_classified(content)
            if not parsed:
                logging.warning('第 %d 批未能解析出分类 JSON，这 %d 本保持原值',
                                batch_no, len(batch))
            else:
                changed += apply_results(batch, parsed)
        # 无论成败，请求间统一留 0.5s 间隔，避免限流
        time.sleep(BATCH_SLEEP)

    # dry-run：只打印结果，不备份、不写回
    if args.dry_run:
        print('\n==== 分类结果（dry-run，未写文件）====')
        for i, b in enumerate(targets, 1):
            print('%3d. [%s] %s（%s）→ category=%s | level=%s'
                  % (i, str(b.get('language') or '?'),
                     b.get('title'), b.get('author'),
                     b.get('category') or '—', b.get('level') or '—'))
        print('共打印 %d 本。' % len(targets))
        logging.info('dry-run 结束：%d 本待分类', len(targets))
        return

    # 正常模式：备份 → 写回
    try:
        backup_file(args.input)
    except Exception as e:
        logging.error('备份失败，中止写回以免数据丢失: %s', e)
        raise SystemExit(1)
    try:
        write_books(args.input, books)
    except Exception as e:
        logging.error('写回 %s 失败: %s', args.input, e)
        raise SystemExit(1)
    logging.info('完成：更新 %d 本，已写回 %s（原文件已备份为 .bak）', changed, args.input)
    print('✅ 完成：更新 %d 本 → %s（备份：%s.bak）' % (changed, args.input, args.input))


if __name__ == '__main__':
    main()
