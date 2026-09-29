#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
vocab_extract.py — 词汇抽取与分词（古登堡英文 + 繁体中文；绝不截断、绝不按固定长度滑窗）
=================================================================================
目标：从 `data/books/*.json`（单书正本，chapters[{title, content}]）里抽出**完整词**，
      输出 `vocab_raw.json`（记录 = 词 × 书 × 章，含原文上下文窗口）。

英文（正则词形，无滑窗）
  · `RE_EN_WORD`：**拉丁字母**（含带变音符：quâ / nè / ḥū，由 unicodedata 精确生成，不含 CJK）
    串 + **词内**连字符/撇号；连字符词整体保留（Buda-Pesth 一个词），缩写不拆（don’t / o’er）。
  · 归一化：小写 + 弯撇号（’/ʼ）→ ' + 真连字符（‐/‑）→ '-'；原文大小写另存 variants。
  · 过滤：纯数字（正则本身不吐数字）、单字母（仅保留 a / I）、常见停用词。
  · 每个词形都会做「最大词形」校验（前后紧邻字符不能还是字母/连接符）→ 截断即报错。

中文（分词库按词切分，无单字滑窗）
  · 先**逐字**繁→简（trad_simp_map.json，键值均为单字 → str.translate，长度 1:1 保偏移），
    再在 **CJK 连续段内**用 jieba 按词切分；偏移直接映射回原文，展示用字保留繁体原样。
  · 自定义古汉语词典：`--zh-dict`（默认可放 data/guwen_dict.txt）+ 脚本内置常见古汉语
    双字/多字词表；jieba 缺失时自动降级为**双向最大匹配**（只用词典，不造词、不滑窗）。
  · 默认 `HMM=False`（jieba 词典 DAG + 不造词）——古文用 HMM 会造出「发心久/近」式错并。
  · 护栏：jieba 词典含少量语料噪声词条（如 `国之君 20 nr`）；凡「长度≥3 且词典频次
    < `--min-dict-freq`（默认 100）且不在自有词典」的词，退回保守最大匹配重切。
  · 收录：书内总频 >= `--min-freq-zh`（默认 2，即去掉只出现一次的低频词），或用户划选词。
  · 自检：切词结果必须**原样重建**该 CJK 段（拼接所有词 == 原字符串）→ 无截断/丢失/重叠。

输出（vocab_raw.json）
  {"words":[ {word, frequency, total, book_id, book, lang, chapter_id, chapter,
              contexts, …}, … ], "_meta":{生成时间/命令/规则/分词器/书目}, "summary":{统计 + 自检}}
  · 记录粒度由 `--granularity` 决定（**流式写出，内存与书库规模无关**）：
      word（默认）一条 = 一个词（全库聚合）：frequency = 全库词次、total = 全库词次、
                  book_id/chapter_id = 首见出处、books = 出现过该词的书（最多 --books-max 个，
                  book_count 给全集数）；全库 105 本默认约 8.1 万条 / 约 27 MiB
      book      一条 = 词 × 书：frequency = 该书词次、chapters = 出现过章号（"1,3-5,9"）；
                  ≈ 39 万条 / 约 100 MiB（建议配合书名筛选或提高阈值）
      chapter   一条 = 词 × 书 × 章（需求字面格式）：≈ 235 万条 / 约 600 MiB（务必先筛选）
  · `contexts` = 每条记录 `--contexts`（默认 1）个窗口，窗口 = 原文前后各 `--ctx-width`
    （默认 20）字（英文向外扩到词边界，换行折叠为空格）。
  · 文件用 `.part` 临时名写完后原子替换，并**回读校验**（可解析 + 记录数 + 必备字段）；
    自检失败则**不落盘**（除非 --force）。

用法
  python3 vocab_extract.py                          # 全库（105 本）→ vocab_raw.json（按词聚合）
  python3 vocab_extract.py 論語 pg205               # 只处理指定书（book_id 或书名，支持子串）
  python3 vocab_extract.py --lang en                # 只处理英文书
  python3 vocab_extract.py --min-freq-zh=3 --contexts=1 --dry-run   # 先看统计与条数，不写文件
  python3 vocab_extract.py --granularity=book 施公案                 # 每词每书一条
  python3 vocab_extract.py --granularity=chapter 論語                # 需求字面格式（词×书×章）
  python3 vocab_extract.py --select 不亦乐乎,君子   # 用户划选词（无视阈值/停用词，必定收录）
  python3 vocab_extract.py --select-file 我的生词.txt
  python3 vocab_extract.py --zh-dict 文本/新书/data/guwen_dict.txt  # 追加自定义古汉语词表
  python3 vocab_extract.py --selftest               # 规则自测（截断/错切回归）
  python3 vocab_extract.py --no-jieba               # 强制走最大匹配（对照/回归用）

选项：--out=FILE --lang=zh|en|all --granularity=word|book|chapter --min-freq-zh=N --min-freq-en=N
      --contexts=N --ctx-width=N --books-max=N --select=a,b --select-file=FILE
      --zh-dict=FILE（多个用「:」分隔）--min-dict-freq=N --zh-stopwords=FILE --no-builtin-zh-dict
      --hmm --no-jieba --no-cross-lang --limit=N --sort=auto|book|freq --pretty --dry-run
      --no-verify --force --quiet
"""
import collections
import datetime
import glob
import json
import os
import re
import sys
import tempfile
import time
import unicodedata

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(BASE))                 # 项目根
BOOKS_DIR = os.path.join(ROOT, 'data', 'books')               # 单书正本
QUICK_BOOKS = os.path.join(BASE, 'quick_books.json')          # key → gid（古登堡编号）
TRAD_SIMP_FILE = os.path.join(BASE, 'trad_simp_map.json')     # 逐字繁→简（1:1）
ZH_DICT_DEFAULT = os.path.join(BASE, 'data', 'guwen_dict.txt')  # 可选自定义古汉语词表
OUT_DEFAULT = os.path.join(BASE, 'vocab_raw.json')

# 逐字繁→简表（main 里载入一次；供划选词命中判定与 summary 统计复用）
_TABLE = {}

# ------------------------------------------------------------
# 一、词形规则（正则；绝不用固定长度滑窗）
# ------------------------------------------------------------
CJK_PAT = r'[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]'
RE_CJK_RUN = re.compile(CJK_PAT + '+')          # CJK 连续段（分词只在这些段内进行）
RE_CJK_CHAR = re.compile(CJK_PAT)


def _latin_letters():
    """拉丁字母字符集（含带变音符：quâ / nè / ḥū 等），由 unicodedata 精确生成。

    只收 Unicode 类别 L* 的字符 → 自动排除 × ÷ ° 等非字母符号；不含 CJK。
    """
    ranges = ((0x0041, 0x005A), (0x0061, 0x007A), (0x00C0, 0x024F), (0x0250, 0x02AF),
              (0x1E00, 0x1EFF), (0x2C60, 0x2C7F), (0xA720, 0xA7FF), (0xFB00, 0xFB06))
    out = []
    for a, b in ranges:
        for cp in range(a, b + 1):
            ch = chr(cp)
            if unicodedata.category(ch).startswith('L'):
                out.append(ch)
    return ''.join(out)


LATIN_LETTERS = _latin_letters()
RE_LT_CHAR = re.compile('[' + LATIN_LETTERS + ']')          # 单个拉丁字母（边界判定用）

# 英文词形：拉丁字母串 + 词内连字符/撇号；破折号 — – 不并入词内（避免把两句粘成一个词）
EN_JOIN_CLASS = "-'’ʼ"    # 词内连接符类：- ' ’ ʼ（连字符置于类首即字面量）
RE_EN_WORD = re.compile('[%s]+(?:[%s][%s]+)*' % (LATIN_LETTERS, EN_JOIN_CLASS, LATIN_LETTERS))
# 连接符集合与 RE_EN_WORD 严格一致（供边界自检 / 上下文外扩使用，避免两处定义走偏）
EN_JOIN = set(EN_JOIN_CLASS)
EN_APOSTROPHE = {'\u2019': "'", '\u02bc': "'"}   # 弯撇号 → 直撇号（` ´ 在语料中是分隔符，不归一）
EN_HYPHEN = {'\u2010': '-', '\u2011': '-'}       # 真连字符 → ASCII '-'
EN_SINGLE_OK = {'a', 'i'}      # 需求：单字母仅保留 a / I

# 常见英文停用词（标准表；**刻意不含 a / i**——需求要求单字母保留 a、I）
EN_STOPWORDS = set("""
about above after again against all am an and any are as at be because been before
being below between both but by can cannot could did do does doing don down during
each few for from further had has have having he her here hers herself him himself
his how if in into is it its itself just me more most my myself no nor not now of
off on once only or other our ours ourselves out over own same she should so some
such than that the their theirs them themselves then there these they this those
through to too under until up very was we were what when where which while who whom
why will with would you your yours yourself yourselves
""".split())

# 内置常见古汉语词表（简体，与「简体化后分词」对齐）：
# 虚词组合 / 称谓 / 制度礼制 / 名物 / 动作情态 / 哲理 / 常见成语（四字）
BUILTIN_ZH_WORDS = """
于是 是以 是故 是乃 所以 所谓 所为 何以 何如 如何 奈何 若何 无乃 得无 不亦 岂不 岂敢
岂能 岂可 岂有 呜呼 嗟乎 嗟夫 而已 云尔 云云 焉耳 耳矣 也已 也夫 矣夫 也者 者也 者乎
者哉 孰与 孰若 与其 不如 不若 莫若 莫如 不惟 不特 非独 非特 非徒 不但 不独 由是 因此
故而 然而 然则 然后 虽然 虽则 纵使 即使 假使 倘若 若使 借使 若夫 且夫 今夫 至若 至于
以及 以至于 及至 迨至 逮至 及乎 及其 及夫 及此 方今 当今 当是时 于是乎 不然 否则
未几 无几 少顷 须臾 俄而 既而 已而 继而 旋即 有顷 片刻 顷刻 少时 少间 良久 有间 逾时
逾年 明年 翌日 次日 他日 异日 来日 明日 昨日 昔日 畴昔 曩者 向者 乡者 先是 初时 当时
尔时 此时 彼时 平生 生平 向来 从来 自古 至今 迄今 于今
天下 天子 诸侯 大夫 卿大夫 百姓 庶民 黎民 兆民 万民 布衣 黔首 匹夫 匹妇 君子 小人
大人 圣人 贤人 愚人 仁者 智者 勇者 丈夫 女子 妇人 孺子 童子 老者 长幼 兄弟 姊妹 父子
母子 夫妇 妻子 儿孙 子孙 后世 后人 古人 今人 前人 乡人 邻人 邦人 国人 邑人 野人 农人
工人 商人 士人 学者 儒者 门人 弟子 门生 后学 门徒 徒众 众人 群臣 大臣 重臣 权臣 佞臣
忠臣 贤臣 良臣 名士 处士 隐士 逸民 遗民
宗庙 社稷 朝廷 宫室 宫殿 楼台 亭榭 城郭 沟壑 田园 山林 江湖 河海 田亩 禾稼 粟米 布帛
丝麻 车马 舟楫 甲兵 干戈 弓矢 戈矛 鼎彝 圭璧 冠冕 衣裳 缙绅 冠带 婚丧 祭祀 祈祷 斋戒
牺牲 卜筮 龟蓍 礼乐 礼义 仁义 道德 忠信 孝悌 廉耻 诚信 忠孝 仁爱 教化 风俗 法令 刑法
赏罚 科举 进士 举人 秀才 状元 翰林 学士 尚书 侍郎 御史 中丞 太守 刺史 县令 知县 知府
节度 观察 司徒 司马 司空 太尉 丞相 宰相 将军 校尉 都尉 参军 主簿 吏部 户部 礼部 兵部
刑部 工部 中书 门下 枢密 台省 郡县 州郡 封疆 疆域 疆土 九卿 三公 五等 册封 封建 分封
世袭 仕宦 宦游 归田 致仕
日月 星辰 风雨 霜雪 雷霆 云雾 山川 江河 湖海 春秋 朝夕 晨昏 昼夜 古今 岁月 光阴 时辰
刻漏 天地 阴阳 五行 四季 草木 花木 鸟兽 虫鱼 虎狼 牛羊 鸡犬 桑麻 稻粱 桃李 松柏 芝兰
尘埃 泥涂 波涛 波澜 泉石 溪涧 峰峦 岩穴 洞穴 幽谷 旷野 荒郊 边塞 关隘 关山 长城 荒漠
往来 出入 进退 升降 往复 观看 听闻 言语 谈笑 哭泣 悲哀 欢喜 忧愁 恐惧 惊骇 奔驰 逃亡
隐匿 潜伏 登临 眺望 徘徊 遨游 游历 稽首 拜谒 谒见 辞别 告别 送别 迎接 询问 应答 教诲
劝谏 讽谏 谏诤 谋划 商议 议论 辩论 争论 思虑 忧虑 欣悦 怨怒 忿怒 悲叹 感叹 叹息 长叹
流泪 涕泣 饥寒 冻馁 疾病 医药 医治 疗疾 死亡 丧葬 殡葬 祭奠 追思
祸福 吉凶 生死 存亡 兴衰 盛衰 治乱 安危 得失 利害 是非 善恶 贤愚 贵贱 贫富 荣辱 功名
富贵 权贵 权势 文章 诗书 典籍 经传 注疏 训诂 音韵 文字 篇章 言辞 谋略 计策 兵谋 战阵
行军 征伐 攻守 战守 粮草 军旅 德行 政事 政务 民生 民事 国事 世事 人事 天命 天数 造化
因果 缘分 志节 节操 气节 器量 气度 胸襟 志向 志趣 才学 才德 名声 名节 声名 声誉
不亦乐乎 无为而治 各得其所 后生可畏 教学相长 克己复礼 明察秋毫 千里之行 三人成虎 上行下效
甚嚣尘上 述而不作 温故知新 小心翼翼 学而不厌 一鸣惊人 以德报怨 因材施教 有教无类 草木皆兵
出尔反尔 祸福无门 仁者爱人 天下太平 不耻下问 博学多闻 知足常乐 安居乐业 千秋万代 百战百胜
老当益壮 自强不息 厚德载物 上善若水 大器晚成 大巧若拙 大智若愚 言行一致 名不副实 画蛇添足
刻舟求剑 守株待兔 亡羊补牢 掩耳盗铃 自相矛盾 杯弓蛇影 望梅止渴 狐假虎威 鹬蚌相争 塞翁失马
因祸得福 因地制宜 因势利导 顺理成章 水到渠成 显而易见 不言而喻 无可奈何
""".split()

# ------------------------------------------------------------
# 二、词典与分词器（jieba 优先，缺失时双向最大匹配降级）
# ------------------------------------------------------------
def load_json(path, fallback=None):
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return fallback


def load_trad_simp_table():
    """逐字繁→简映射表（str.translate 用）。键值均为单字 → 转换后长度不变（偏移 1:1）。"""
    raw = load_json(TRAD_SIMP_FILE, {}) or {}
    tbl = {}
    for k, v in raw.items():
        if isinstance(k, str) and isinstance(v, str) and len(k) == 1 and len(v) == 1:
            tbl[ord(k)] = v
    return tbl


def load_zh_words(paths):
    """读自定义古汉语词表：每行「词 [频次] [词性]」，# 注释/空行忽略。返回 [(词, 频次或 None)]。"""
    words, seen = [], set()
    for p in paths:
        if not p or not os.path.exists(p):
            continue
        with open(p, encoding='utf-8') as f:
            for line in f:
                line = line.split('#', 1)[0].strip()
                if not line:
                    continue
                parts = line.split()
                w = parts[0].strip()
                if not w or w in seen or not RE_CJK_CHAR.search(w):
                    continue
                freq = None
                if len(parts) > 1:
                    try:
                        freq = int(parts[1])
                    except ValueError:
                        freq = None
                seen.add(w)
                words.append((w, freq))
    return words


class JiebaSegmenter:
    """jieba 按词切分（词典 DAG；默认不启用 HMM，避免给古文造词）。

    额外护栏：jieba 词典含少量语料噪声词条（如 `国之君 20 nr`），会把古文错并成
    多字词。凡「长度≥3 且词典频次 < min_dict_freq 且不在自有词典内」的词，退回
    **保守最大匹配**（只用自有词典）重切——绝不引入固定长度滑窗。
    """

    def __init__(self, words, hmm=False, min_dict_freq=100):
        import jieba
        self.hmm = hmm
        self.mine = set(w for w, _ in words)
        self.min_freq = max(0, int(min_dict_freq or 0))
        self.splitter = MaxMatchSegmenter(words) if self.min_freq else None
        self.name = ('jieba %s（HMM=%s%s）'
                     % (getattr(jieba, '__version__', '?'), 'on' if hmm else 'off',
                        '，低频多字词条回退保守切分 <%d' % self.min_freq if self.min_freq else ''))
        self.tk = jieba.Tokenizer()
        for w, freq in words:
            self.tk.add_word(w, freq)

    def cut(self, run, base):
        for word, s, e in self.tk.tokenize(run, mode='default', HMM=self.hmm):
            if (self.splitter is not None and len(word) >= 3 and word not in self.mine
                    and self.tk.FREQ.get(word, 0) < self.min_freq):
                for w2, s2, e2 in self.splitter.cut(word, base + s):
                    yield w2, s2, e2
            else:
                yield word, base + s, base + e


class MaxMatchSegmenter:
    """双向最大匹配（jieba 缺失时的降级路径）：只用词典，绝不按固定长度滑窗、不造词。"""

    def __init__(self, words, max_len=10):
        self.name = '双向最大匹配（jieba 未安装，降级）'
        self.vocab = set(w for w, _ in words)
        self.max_len = max([max_len] + [len(w) for w, _ in words])

    def _forward(self, run):
        out, i, n = [], 0, len(run)
        while i < n:
            L = min(self.max_len, n - i)
            while L > 1 and run[i:i + L] not in self.vocab:
                L -= 1
            out.append((run[i:i + L], i, i + L))
            i += L
        return out

    def _backward(self, run):
        out, j = [], len(run)
        while j > 0:
            L = min(self.max_len, j)
            while L > 1 and run[j - L:j] not in self.vocab:
                L -= 1
            out.append((run[j - L:j], j - L, j))
            j -= L
        out.reverse()
        return out

    def cut(self, run, base):
        fwd, bwd = self._forward(run), self._backward(run)
        if len(fwd) != len(bwd):
            best = fwd if len(fwd) < len(bwd) else bwd          # 词数少者胜
        else:
            f1 = sum(1 for w, _, _ in fwd if len(w) == 1)
            b1 = sum(1 for w, _, _ in bwd if len(w) == 1)
            best = fwd if f1 <= b1 else bwd                    # 单字少者胜
        for word, s, e in best:
            yield word, base + s, base + e


def build_zh_segmenter(zh_dicts, use_builtin=True, hmm=False, no_jieba=False, min_dict_freq=100):
    """组装中文分词器：内置古汉语词表 + 自定义词表；jieba 优先，缺失/强制则最大匹配。"""
    words, seen = [], set()
    if use_builtin:
        for w in BUILTIN_ZH_WORDS:
            if w not in seen:
                seen.add(w)
                words.append((w, None))
    for w, freq in load_zh_words(zh_dicts):
        if w not in seen:
            seen.add(w)
            words.append((w, freq))
    if not no_jieba:
        try:
            return JiebaSegmenter(words, hmm=hmm, min_dict_freq=min_dict_freq), len(words)
        except ImportError:
            pass
    return MaxMatchSegmenter(words), len(words)

# ------------------------------------------------------------
# 三、取词与过滤
# ------------------------------------------------------------
def normalize_en(surface):
    """英文归一化：小写 + 弯撇号→' + 真连字符→'-'。"""
    s = surface.lower()
    for k, v in EN_APOSTROPHE.items():
        s = s.replace(k, v)
    for k, v in EN_HYPHEN.items():
        s = s.replace(k, v)
    return s


def en_tokens(text):
    """英文取词：正则匹配**完整词形**（含词内连字符/撇号）→ (归一形, 原文形, start, end)。"""
    for m in RE_EN_WORD.finditer(text):
        surface = m.group(0)
        yield normalize_en(surface), surface, m.start(), m.end()


def en_keep(word):
    """英文收录过滤：单字母（仅 a/I）、纯数字、常见停用词。"""
    if word in EN_SINGLE_OK:
        return True
    if len(word) < 2 or word.isdigit():
        return False
    return word not in EN_STOPWORDS


def zh_keep(word, stopwords):
    """中文收录过滤：全为汉字，且不在（可选）中文停用词表内。"""
    if not word or not all(RE_CJK_CHAR.match(c) for c in word):
        return False
    return word not in stopwords


# ------------------------------------------------------------
# 四、自检（无截断 / 无错切 的硬性校验）
# ------------------------------------------------------------
def verify_en(text, tokens):
    """英文：词形必须是「最大词形」——前后紧邻不能还是拉丁字母；连接符须其后跟字母才算粘连。"""
    for norm, surface, a, b in tokens:
        if RE_EN_WORD.fullmatch(surface) is None:
            return '词形不合规则：%r' % surface
        if normalize_en(surface) != norm:
            return '归一化不一致：%r → %r' % (surface, norm)
        left = RE_LT_CHAR.match(text[a - 1]) if a > 0 else None
        right = RE_LT_CHAR.match(text[b]) if b < len(text) else None
        if left or (a > 1 and text[a - 1] in EN_JOIN and RE_LT_CHAR.match(text[a - 2])):
            return '左边界截断：%r' % text[max(0, a - 6):b + 2]
        if right or (b + 1 < len(text) and text[b] in EN_JOIN and RE_LT_CHAR.match(text[b + 1])):
            return '右边界截断：%r' % text[max(0, a - 2):b + 6]
    return None


def verify_zh(run, run_simp, tokens, base=0):
    """中文：分词必须**原样重建**该 CJK 段（拼接 == 原文），且首尾相接、无重叠、无空白。"""
    if ''.join(t[0] for t in tokens) != run:
        return '重建失败（截断/丢失/粘连）：%r' % run[:40]
    if ''.join(t[1] for t in tokens) != run_simp:
        return '简体重建失败：%r' % run_simp[:40]
    pos = base
    for surf, _simp, a, b in tokens:
        if b <= a or a != pos or surf != run[a - base:b - base]:
            return '偏移不连续：%r @ %d-%d（应 %d）' % (surf, a, b, pos)
        for c in surf:
            if not RE_CJK_CHAR.match(c):
                return '词内混入非汉字：%r' % surf
        pos = b
    return None

# ------------------------------------------------------------
# 五、抽词主流程
# ------------------------------------------------------------
def make_context(text, a, b, width, snap_en=False):
    """原文上下文窗口：词前后各 width 字；换行/制表折叠为空格；英文向外扩到词边界。"""
    s, e = max(0, a - width), min(len(text), b + width)
    if snap_en:
        while s > 0 and (RE_LT_CHAR.match(text[s - 1]) or text[s - 1] in EN_JOIN):
            s -= 1
        while e < len(text) and (RE_LT_CHAR.match(text[e]) or text[e] in EN_JOIN):
            e += 1
    return re.sub(r'\s+', ' ', text[s:e]).strip()


def zh_run_tokens(text, seg, table):
    """逐 CJK 连续段产出 (原文段, 简体段, [(原文词, 简体词, start, end), …])。

    先整章逐字繁→简（str.translate，长度不变），再**只在 CJK 段内**按词切分——
    标点/数字/拉丁字母一律不是词的一部分，杜绝跨段粘连与固定长度滑窗。
    """
    simp = text.translate(table)
    if len(simp) != len(text):
        raise AssertionError('繁→简 逐字转换长度不一致：%d → %d' % (len(text), len(simp)))
    for m in RE_CJK_RUN.finditer(simp):
        toks = [(text[s:e], simp[s:e], s, e) for _w, s, e in seg.cut(m.group(0), m.start())]
        yield m.start(), text[m.start():m.end()], m.group(0), toks


def extract_book(path, cfg, seg, table):
    """处理一本 → (acc, pack)：acc = {(lang, word): {total, chapters, variants, simp}}。

    acc 为「本书内」的取词计数表（含每章上下文），记录生成交给 records_by_* / fold_word；
    自检失败时 acc 为 None，pack 带 error/chapter_id。
    """
    data = load_json(path, {}) or {}
    book_id = os.path.basename(path)[:-5]
    book = data.get('book') or book_id
    book_lang = data.get('lang') or 'zh'
    chapters = data.get('chapters') or []
    want_en = cfg['cross_lang'] or book_lang == 'en'
    want_zh = cfg['cross_lang'] or book_lang != 'en'

    acc = {}          # (lang, word) → {'total', 'chapters': {ci: [count, [ctx…]]}, 'variants', 'simp'}
    n_tok = 0
    err = None
    t0 = time.time()

    for ci, ch in enumerate(chapters, 1):
        text = ch.get('content', '') or ''
        title = ch.get('title', '') or ''
        if want_en:
            toks = list(en_tokens(text))
            n_tok += len(toks)
            if cfg['verify']:
                err = err or verify_en(text, toks)
            for norm, surface, a, b in toks:
                e = acc.get(('en', norm))
                if e is None and not (norm in cfg['sel_en'] or en_keep(norm)):
                    continue
                if e is None:
                    e = acc[('en', norm)] = {'total': 0, 'chapters': {}, 'variants': [], 'simp': ''}
                e['total'] += 1
                ce = e['chapters'].setdefault(ci, [0, []])
                ce[0] += 1
                if surface not in e['variants'] and len(e['variants']) < 3:
                    e['variants'].append(surface)
                if len(ce[1]) < cfg['contexts']:
                    c = make_context(text, a, b, cfg['ctx_width'], snap_en=True)
                    if c not in ce[1]:
                        ce[1].append(c)
        if want_zh:
            for base, run_orig, run_simp, toks in zh_run_tokens(text, seg, table):
                n_tok += len(toks)
                if cfg['verify']:
                    err = err or verify_zh(run_orig, run_simp, toks, base)
                for surface, simpw, a, b in toks:
                    if surface not in cfg['sel_zh'] and simpw not in cfg['sel_zh']:
                        if not zh_keep(simpw, cfg['zh_stop']):
                            continue
                    e = acc.get(('zh', surface))
                    if e is None:
                        e = acc[('zh', surface)] = {'total': 0, 'chapters': {}, 'variants': [], 'simp': simpw}
                    e['total'] += 1
                    ce = e['chapters'].setdefault(ci, [0, []])
                    ce[0] += 1
                    if len(ce[1]) < cfg['contexts']:
                        c = make_context(text, a, b, cfg['ctx_width'])
                        if c not in ce[1]:
                            ce[1].append(c)
        if err:
            return None, {'book_id': book_id, 'book': book, 'error': err,
                          'chapter_id': ci, 'chapter': title}

    stat = {'book_id': book_id, 'book': book, 'lang': book_lang, 'chapters': len(chapters),
            'chars': sum(len(ch.get('content', '') or '') for ch in chapters),
            'tokens': n_tok, 'keys': len(acc),
            'seconds': round(time.time() - t0, 2)}
    pack = {'book_id': book_id, 'book': book, 'lang': book_lang, 'stat': stat,
            'titles': [ch.get('title') or '' for ch in chapters]}
    return acc, pack


def is_selected(cfg, lang, word, simp=''):
    """是否用户划选词（划选词无视阈值与停用词）。"""
    return (word in cfg['sel_en']) if lang == 'en' else (
        word in cfg['sel_zh'] or bool(simp and simp in cfg['sel_zh']))


def keep_word(cfg, lang, word, e):
    """收录判定：划选词必收；否则按该词在本书的出现次数 >= 阈值。"""
    return is_selected(cfg, lang, word, e.get('simp', '')) or e['total'] >= (
        cfg['min_freq_en'] if lang == 'en' else cfg['min_freq_zh'])


def rec_head(word, lang, e, cfg):
    """记录公共头部字段（word / lang / simp|variants / selected）。"""
    rec = collections.OrderedDict()
    rec['word'] = word
    rec['lang'] = lang
    if lang == 'zh':
        if e.get('simp') and e['simp'] != word:
            rec['simp'] = e['simp']
    else:
        rec['variants'] = e['variants']
    if is_selected(cfg, lang, word, e.get('simp', '')):
        rec['selected'] = True
    return rec


def compact_ranges(nums):
    """章节号压缩：[1,3,4,5,9] → '1,3-5,9'（控制体积）。"""
    out, nums, i = [], sorted(nums), 0
    while i < len(nums):
        j = i
        while j + 1 < len(nums) and nums[j + 1] == nums[j] + 1:
            j += 1
        if j > i + 1:
            out.append('%d-%d' % (nums[i], nums[j]))
        elif j > i:
            out.append('%d,%d' % (nums[i], nums[j]))
        else:
            out.append(str(nums[i]))
        i = j + 1
    return ','.join(out)

def records_by_chapter(acc, pack, cfg):
    """粒度 chapter：一条 = 词 × 书 × 章（frequency = 该章次数）。"""
    for (lang, word), e in acc.items():
        if not keep_word(cfg, lang, word, e):
            continue
        for ci in sorted(e['chapters']):
            cnt, ctxs = e['chapters'][ci]
            rec = rec_head(word, lang, e, cfg)
            rec['frequency'] = cnt
            rec['total'] = e['total']
            rec['book_id'] = pack['book_id']
            rec['book'] = pack['book']
            rec['chapter_id'] = ci
            rec['chapter'] = pack['titles'][ci - 1] if ci - 1 < len(pack['titles']) else ''
            rec['contexts'] = ctxs
            yield rec


def records_by_book(acc, pack, cfg):
    """粒度 book：一条 = 词 × 书（frequency = 该书次数，chapters = 出现过章号，chapter_id = 首见章）。"""
    for (lang, word), e in acc.items():
        if not keep_word(cfg, lang, word, e):
            continue
        first = min(e['chapters'])
        ctxs = []
        for ci in sorted(e['chapters']):
            for c in e['chapters'][ci][1]:
                if len(ctxs) < cfg['contexts'] and c not in ctxs:
                    ctxs.append(c)
        rec = rec_head(word, lang, e, cfg)
        rec['frequency'] = e['total']
        rec['total'] = e['total']
        rec['book_id'] = pack['book_id']
        rec['book'] = pack['book']
        rec['chapter_id'] = first
        rec['chapter'] = pack['titles'][first - 1] if first - 1 < len(pack['titles']) else ''
        rec['chapters'] = compact_ranges(e['chapters'].keys())
        rec['contexts'] = ctxs
        yield rec


def fold_word(global_acc, acc, pack, cfg):
    """粒度 word：把单本结果并入全库聚合表（每词一条）。"""
    bid = pack['book_id']
    for (lang, word), e in acc.items():
        if not keep_word(cfg, lang, word, e):
            continue
        first = min(e['chapters'])
        g = global_acc.get((lang, word))
        if g is None:
            g = global_acc[(lang, word)] = {
                'freq': 0, 'simp': e.get('simp', ''), 'variants': list(e['variants']),
                'books': [], 'contexts': [], 'book_id': bid, 'book': pack['book'],
                'chapter_id': first,
                'chapter': pack['titles'][first - 1] if first - 1 < len(pack['titles']) else ''}
        g['freq'] += e['total']
        g['books'].append((bid, e['total']))
        if not g['simp'] and e.get('simp'):
            g['simp'] = e['simp']
        for v in e['variants']:
            if v not in g['variants'] and len(g['variants']) < 3:
                g['variants'].append(v)
        for ci in sorted(e['chapters']):
            for c in e['chapters'][ci][1]:
                if len(g['contexts']) < cfg['contexts'] and c not in g['contexts']:
                    g['contexts'].append(c)


def records_by_word(global_acc, cfg):
    """粒度 word：一条 = 词（全库聚合）；book_id/chapter_id 为首见出处，books = 出现的书（按次数降序）。"""
    for (lang, word), g in global_acc.items():
        rec = collections.OrderedDict()
        rec['word'] = word
        rec['lang'] = lang
        if lang == 'zh':
            if g['simp'] and g['simp'] != word:
                rec['simp'] = g['simp']
        else:
            rec['variants'] = g['variants']
        rec['frequency'] = g['freq']
        rec['total'] = g['freq']
        rec['book_id'] = g['book_id']
        rec['book'] = g['book']
        rec['chapter_id'] = g['chapter_id']
        rec['chapter'] = g['chapter']
        rec['book_count'] = len(g['books'])
        if cfg['books_max'] > 0:
            top = sorted(g['books'], key=lambda x: -x[1])[:cfg['books_max']]
            rec['books'] = ','.join(b for b, _ in top)
        rec['contexts'] = g['contexts']
        if is_selected(cfg, lang, word, g['simp']):
            rec['selected'] = True
        yield rec

class VocabWriter:
    """流式写 vocab_raw.json：先写 words 数组，收尾补 _meta / summary（内存恒定）。"""

    def __init__(self, path, pretty=False, enabled=True):
        self.path = path
        self.pretty = pretty
        self.enabled = enabled
        self.count = 0
        self.f = None
        self._buf = [] if (pretty and enabled) else None
        if enabled:
            self.f = open(path + '.part', 'w', encoding='utf-8')
            self.f.write('{"words":[')

    def add(self, rec):
        self.count += 1
        if not self.enabled:
            return
        if self._buf is not None:                 # --pretty：缓冲后统一缩进写出（仅用于小批量）
            self._buf.append(rec)
            return
        if self.count > 1:
            self.f.write(',')
        self.f.write(json.dumps(rec, ensure_ascii=False, separators=(',', ':')))

    def close(self, meta, summary):
        """收尾：补 _meta / summary 并原子替换落盘。返回文件字节数。"""
        if not self.enabled:
            return 0
        if self._buf is not None:
            body = json.dumps(self._buf, ensure_ascii=False, indent=2)
            self.f.write(body[1:-1])              # 去掉最外层 []
            self._buf = None
        self.f.write(']')                         # 收束 words 数组
        for key, obj in (('_meta', meta), ('summary', summary)):
            self.f.write(',"%s":' % key)
            self.f.write(json.dumps(obj, ensure_ascii=False,
                                    indent=2 if self.pretty else None,
                                    separators=None if self.pretty else (',', ':')))
        self.f.write('}\n')
        self.f.close()
        os.replace(self.path + '.part', self.path)
        return os.path.getsize(self.path)

# ---- WRITER-END ----

# ------------------------------------------------------------
# 六、规则自测（截断 / 错切 回归）
# ------------------------------------------------------------
SELFTEST_EN = ("Buda-Pesth was a nice hyphen-word. don\u2019t stop; o'er the sea, 42 times "
               "(I'm sure); boys' hats, well\u2014known, x-ray, self-esteem, 3.14, A1B2, 'tis so.")


def selftest(cfg, seg, table):
    """跑一组对抗性样例：断言「不截断、不错切、可原样重建」。返回失败数。"""
    ok, bad = 0, []

    def chk(name, cond, detail=''):
        nonlocal ok
        if cond:
            ok += 1
            print('  ✅ %s' % name)
        else:
            bad.append(name)
            print('  ✗ %s  %s' % (name, detail))

    print('== 自测 ①：英文词形（正则，无滑窗）')
    toks = list(en_tokens(SELFTEST_EN))
    norms = [t[0] for t in toks]
    for w in ('buda-pesth', 'hyphen-word', "don't", "o'er", "i'm", 'boys', 'x-ray',
              'self-esteem', 'tis'):
        chk('保留完整词形 %s' % w, w in norms, '实际：%s' % norms)
    chk('连字符词未被截断（无 buda / pesth）', 'buda' not in norms and 'pesth' not in norms)
    chk('纯数字不取词（无 42 / 3.14）', not any(re.fullmatch(r'[0-9.]+', n) for n in norms))
    chk('破折号不并入词（—）', 'well' in norms and 'known' in norms
        and not any('\u2014' in n for n in norms))
    chk('单字母仅留 a / I', en_keep('a') and en_keep('i') and not en_keep('q')
        and not en_keep('b'))
    chk('停用词被过滤', not en_keep('the') and not en_keep('was'))
    chk('边界自检通过', verify_en(SELFTEST_EN, toks) is None, str(verify_en(SELFTEST_EN, toks)))
    trunc = [('hyphen', 'hyphen', 0, 6)]
    chk('截断会被检出（自查能力）',
        (verify_en('hyphen-word', trunc) or '').startswith('右边界截断'))

    print('== 自测 ②：中文分词（按词；原样重建 + 词典生效）')
    cases = ['學而時習之，不亦說乎？', '道可道，非常道。名可名，非常名。',
             '宋人有耕者。田中有株。兔走觸株，折頸而死。', 'ABCD中文123混排（全角括號）！',
             '一 二 三 四 五', '天下之事，天下之民。']
    errs = []
    for c in cases:
        for base, run_orig, run_simp, toks in zh_run_tokens(c, seg, table):
            e = verify_zh(run_orig, run_simp, toks, base)
            if e:
                errs.append((c, e))
    chk('切分可原样重建（无截断/丢失/粘连）', not errs, str(errs[:2]))
    chk('不跨标点/拉丁/数字合并',
        all(RE_CJK_CHAR.search(w) and all(RE_CJK_CHAR.match(ch) for ch in w)
            for _b, _r, _s, ts in zh_run_tokens('ABCD中文123混排！', seg, table) for w, _, _, _ in ts))
    chk('繁→简 生效（词典因此认同多字词）',
        '聖人' in [w for _b, _r, _s, ts in zh_run_tokens('聖人之道，天下歸仁。', seg, table)
                   for w, _sp, _a, _e in ts])
    chk('jieba 低频噪声词条被拆开（之国君 不错并）',
        '國之君' not in [w for _b, _r, _s, ts in zh_run_tokens('齊國之君，諸侯來朝。', seg, table)
                        for w, _sp, _a, _e in ts])

    tmp = os.path.join(tempfile.gettempdir(), 'vocab_selftest_dict.txt')
    with open(tmp, 'w', encoding='utf-8') as f:
        f.write('# 自测词表\n不亦说乎 1000000\n非常道 1000000\n')
    seg2, _n = build_zh_segmenter([tmp], use_builtin=True, hmm=cfg['hmm'],
                                  no_jieba=cfg['no_jieba'],
                                  min_dict_freq=cfg['min_dict_freq'])
    got = [w for _b, _r, _s, ts in zh_run_tokens('學而時習之，不亦說乎？天下非常道也。', seg2, table)
           for w, _sp, _a, _e in ts]
    chk('自定义词表生效（不亦說乎 整体成词）', '不亦說乎' in got, str(got))
    chk('自定义词表生效（非常道 整体成词）', '非常道' in got, str(got))
    seg3, _n3 = build_zh_segmenter([tmp], use_builtin=True, hmm=cfg['hmm'], no_jieba=True,
                                   min_dict_freq=cfg['min_dict_freq'])
    errs3 = [(c, verify_zh(r, s, t, b)) for c in cases
             for b, r, s, t in zh_run_tokens(c, seg3, table)
             if verify_zh(r, s, t, b)]
    chk('最大匹配（降级路径）也可原样重建', not errs3, str(errs3[:2]))
    chk('最大匹配也认自定义词（非常道）',
        '非常道' in [w for _b, _r, _s, ts in zh_run_tokens('天下非常道也。', seg3, table)
                     for w, _sp, _a, _e in ts])

    print('\n自测：%d 通过，%d 失败%s' % (ok, len(bad), ('：' + '；'.join(bad)) if bad else ''))
    return len(bad)

# ------------------------------------------------------------
# 七、CLI
# ------------------------------------------------------------
VALUE_FLAGS = ('out', 'lang', 'min-freq-zh', 'min-freq-en', 'contexts', 'ctx-width',
               'select', 'select-file', 'zh-dict', 'zh-stopwords', 'limit', 'sort',
               'min-dict-freq', 'granularity', 'books-max')


def parse_args(argv):
    """支持 --k=v 与 --k v 两种写法（与 gutenberg_import.py 一致）。"""
    pos, flags, opts = [], set(), {}
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
            (opts.__setitem__(k, v) if k in VALUE_FLAGS else flags.add(k))
            i += 1
            continue
        if body in VALUE_FLAGS:
            if i + 1 >= len(argv):
                print('✗ 参数 --%s 需要值' % body)
                raise SystemExit(2)
            opts[body] = argv[i + 1]
            i += 2
            continue
        flags.add(body)
        i += 1
    return pos, flags, opts


def as_int(opts, key, default):
    try:
        return int(opts[key])
    except (KeyError, TypeError, ValueError):
        return default


def parse_selected(opts, table):
    """用户划选集：--select a,b / --select-file 文件（每行一词，# 注释）。"""
    raw = []
    if opts.get('select'):
        raw += re.split(r'[,，、;；\s]+', opts['select'])
    sf = opts.get('select-file')
    if sf and os.path.exists(sf):
        with open(sf, encoding='utf-8') as f:
            raw += [ln.split('#', 1)[0].strip() for ln in f]
    elif sf:
        print('⚠️ 找不到划选词表：%s' % sf)
    sel_en, sel_zh = set(), set()
    for w in raw:
        w = (w or '').strip()
        if not w:
            continue
        if RE_CJK_CHAR.search(w):
            sel_zh.add(w)
            sel_zh.add(w.translate(table))       # 同时登记简体形，繁体/简体写法都能命中
        else:
            sel_en.add(normalize_en(w))
    return sel_en, sel_zh


def load_zh_stopwords(path):
    words = set()
    if path and os.path.exists(path):
        with open(path, encoding='utf-8') as f:
            for ln in f:
                ln = ln.split('#', 1)[0].strip()
                if ln:
                    words.add(ln)
    elif path:
        print('⚠️ 找不到中文停用词表：%s' % path)
    return words

# ------------------------------------------------------------
# 八、主流程
# ------------------------------------------------------------
def book_candidates(cfg, pos):
    """待处理书单：给了书名或 --lang 时先扫元数据（只取 book/lang，读完即丢）。"""
    paths = sorted(glob.glob(os.path.join(BOOKS_DIR, '*.json')))
    if not pos and cfg['lang'] == 'all':
        return paths
    picked = []
    for p in paths:
        bid = os.path.basename(p)[:-5]
        d = load_json(p, {}) or {}
        title = d.get('book') or bid
        if cfg['lang'] in ('zh', 'en') and (d.get('lang') or 'zh') != cfg['lang']:
            continue
        if pos and not any(q in bid or q in title for q in pos):
            continue
        picked.append(p)
    return picked


def build_cfg(flags, opts, table):
    """CLI → 运行配置。"""
    sel_en, sel_zh = parse_selected(opts, table)
    gid = {}
    for c in (load_json(QUICK_BOOKS, []) or []):
        if isinstance(c, dict) and c.get('key'):
            gid[c['key']] = str(c.get('gid') or '')
    zh_dicts = [p for p in (opts.get('zh-dict') or '').split(':') if p.strip()]
    if os.path.exists(ZH_DICT_DEFAULT):
        zh_dicts.append(ZH_DICT_DEFAULT)
    return {
        'out': opts.get('out') or OUT_DEFAULT,
        'lang': (opts.get('lang') or 'all').lower(),
        'min_freq_zh': as_int(opts, 'min-freq-zh', 2),
        'min_freq_en': as_int(opts, 'min-freq-en', 1),
        'contexts': as_int(opts, 'contexts', 1),
        'ctx_width': as_int(opts, 'ctx-width', 20),
        'books_max': as_int(opts, 'books-max', 8),
        'limit': as_int(opts, 'limit', 0),
        'sort': (opts.get('sort') or 'auto').lower(),
        'granularity': (opts.get('granularity') or 'word').lower(),
        'min_dict_freq': as_int(opts, 'min-dict-freq', 100),
        'zh_dicts': zh_dicts,
        'use_builtin_zh': 'no-builtin-zh-dict' not in flags,
        'zh_stop': load_zh_stopwords(opts.get('zh-stopwords')),
        'cross_lang': 'no-cross-lang' not in flags,
        'hmm': 'hmm' in flags,
        'no_jieba': 'no-jieba' in flags,
        'verify': 'no-verify' not in flags,
        'force': 'force' in flags,
        'pretty': 'pretty' in flags,
        'dry_run': 'dry-run' in flags,
        'quiet': 'quiet' in flags,
        'sel_en': sel_en,
        'sel_zh': sel_zh,
        'gid': gid,
    }

def run(cfg, pos, table):
    """执行抽取 → 汇总 → 写文件。返回进程退出码。"""
    seg, n_dict = build_zh_segmenter(cfg['zh_dicts'], use_builtin=cfg['use_builtin_zh'],
                                     hmm=cfg['hmm'], no_jieba=cfg['no_jieba'],
                                     min_dict_freq=cfg['min_dict_freq'])
    if not cfg['quiet']:
        print('分词器：%s ｜ 词典 %d 词 ｜ 阈值：中文总频≥%d、英文总频≥%d ｜ 上下文 %d×%d 字 ｜ 粒度 %s'
              % (seg.name, n_dict, cfg['min_freq_zh'], cfg['min_freq_en'],
                 cfg['contexts'], cfg['ctx_width'], cfg['granularity']))
        if cfg['sel_en'] or cfg['sel_zh']:
            print('用户划选：中文 %d 个、英文 %d 个（无视阈值/停用词）'
                  % (len(cfg['sel_zh']), len(cfg['sel_en'])))

    paths = book_candidates(cfg, pos)
    if cfg['limit'] > 0:
        paths = paths[:cfg['limit']]
    if not paths:
        print('✗ 没有匹配的书（检查书名筛选 / --lang）')
        return 2
    print('== 抽取：%d 本（源 data/books/*.json）' % len(paths))

    writer = VocabWriter(cfg['out'], pretty=cfg['pretty'], enabled=not cfg['dry_run'])
    stats, problems = [], []
    agg = collections.Counter()          # (lang, word) → 全库词次（summary.top 用）
    global_acc = {}                      # 粒度 word 的全库聚合表
    t0 = time.time()
    try:
        for p in paths:
            acc, pack = extract_book(p, cfg, seg, table)
            if acc is None:
                problems.append(pack)
                print('  ✗ %-22s 自检失败：%s（第 %s 章）'
                      % (pack['book_id'], pack.get('error'), pack.get('chapter_id')))
                continue
            if cfg['granularity'] == 'word':
                pack['stat']['records'] = sum(1 for (lg, w), e in acc.items()
                                              if keep_word(cfg, lg, w, e))
                fold_word(global_acc, acc, pack, cfg)
                n_rec = ''
            else:
                gen = (records_by_chapter(acc, pack, cfg) if cfg['granularity'] == 'chapter'
                       else records_by_book(acc, pack, cfg))
                n = 0
                seen = set()
                for rec in gen:                 # 流式写出：内存与书库规模无关
                    k = (rec['lang'], rec['word'])
                    if k not in seen:           # 词次按「词 × 书」只累计一次，避免重复计数
                        seen.add(k)
                        agg[k] += rec['total']
                    writer.add(rec)
                    n += 1
                pack['stat']['records'] = n
                n_rec = '%7d记录' % n
            stats.append(pack['stat'])
            if not cfg['quiet']:
                print('  %-24s %-2s %4d章 %8d词形 %s %5.1fs'
                      % (pack['book_id'], pack['lang'], pack['stat']['chapters'],
                         pack['stat']['keys'], n_rec, pack['stat']['seconds']))
        if cfg['granularity'] == 'word':
            recs = list(records_by_word(global_acc, cfg))
            if cfg['sort'] == 'freq':
                recs.sort(key=lambda r: (-r['frequency'], r['lang'], r['word']))
            else:
                recs.sort(key=lambda r: (r['book_id'], r['chapter_id'], -r['frequency'], r['word']))
            for rec in recs:
                agg[(rec['lang'], rec['word'])] += rec['frequency']
                writer.add(rec)
    except BaseException:
        if writer.f and not writer.f.closed:
            writer.f.close()
        if os.path.exists(cfg['out'] + '.part'):
            os.remove(cfg['out'] + '.part')
        raise
    if writer.count == 0:
        if os.path.exists(cfg['out'] + '.part'):
            writer.f and writer.f.close()
            os.remove(cfg['out'] + '.part')
        print('✗ 没有产出任何记录')
        return 1
    return finalize(cfg, writer, stats, problems, agg, seg, n_dict, time.time() - t0)


def finalize(cfg, writer, stats, problems, agg, seg, n_dict, elapsed):
    """汇总统计 → meta/summary → 落盘（--dry-run 只报条数不写）。返回退出码。"""
    by_lang = {}
    for lg in ('zh', 'en'):
        keys = [(w, c) for (l2, w), c in agg.items() if l2 == lg]
        by_lang[lg] = {
            'words': len(keys),
            'tokens': sum(c for _, c in keys),
            'top': [[w, c] for w, c in sorted(keys, key=lambda x: -x[1])[:20]],
        }
    hit_zh, hit_en = set(), set()
    for (lg, w) in agg:
        if lg == 'zh':
            hit_zh.add(w)
            hit_zh.add(w.translate(_TABLE))
        else:
            hit_en.add(w)
    miss_en = sorted(w for w in cfg['sel_en'] if w not in hit_en)
    miss_zh = sorted(w for w in cfg['sel_zh'] if w not in hit_zh)

    gran_desc = {'word': '词（全库聚合；book_id/chapter_id = 首见出处）',
                 'book': '词 × 书（chapters = 出现过章号）',
                 'chapter': '词 × 书 × 章'}[cfg['granularity']]
    meta = collections.OrderedDict()
    meta['generator'] = 'vocab_extract.py'
    meta['generated'] = datetime.datetime.now().isoformat(timespec='seconds')
    meta['command'] = ' '.join(['python3', '文本/新书/vocab_extract.py'] + sys.argv[1:])
    meta['source'] = 'data/books/*.json（单书正本 chapters[{title, content}]）'
    meta['granularity'] = {'mode': cfg['granularity'], 'records': gran_desc,
                           'sort': cfg['sort'] if cfg['granularity'] == 'word' else '首现顺序'}
    meta['fields'] = {
        'word': '归一化词形（英文小写；中文为原文用字，繁体书即繁体）',
        'lang': 'zh / en（按词形判定，与书语种无关：中文书里的英文词也会抽出）',
        'frequency': '本记录范围内的出现次数（chapter=该章 / book=该书 / word=全库）',
        'total': '该书出现次数（word 粒度下 = 全库次数）',
        'book_id / book': 'data/books 文件名去扩展名 / 书名',
        'chapter_id / chapter': '章序（1 起）/ 章标题（word、book 粒度为首次出现处）',
        'chapters': 'book 粒度：出现过的章号（压缩，如 "1,3-5,9"）',
        'books': 'word 粒度：出现过该词的书（按次数降序，逗号分隔，最多 --books-max 个；'
                 '全集见 book_count）',
        'contexts': '原文上下文窗口（前后各 %d 字；英文扩到词边界，换行折叠为空格）'
                    % cfg['ctx_width'],
        'simp': '中文：简体形（与 word 不同才出现）',
        'variants': '英文：原文大小写/用字变体（最多 3 个，供展示）',
        'selected': 'true = 用户划选词（无视阈值与停用词）',
    }
    meta['rules'] = collections.OrderedDict()
    meta['rules']['en'] = {
        'regex': RE_EN_WORD.pattern,
        'normalize': "小写 + 弯撇号（’ʼ）→ ' + 真连字符（‐‑）→ -",
        'filter': '纯数字、单字母（仅保留 a/I）、%d 个常见停用词' % len(EN_STOPWORDS),
        'min_total_freq': cfg['min_freq_en'],
        'no_truncation': '正则整体匹配 + 最大词形边界自检（前后紧邻不得仍为拉丁字母/连接符）',
    }
    meta['rules']['zh'] = {
        'tokenizer': seg.name,
        't2s': 'trad_simp_map.json 逐字转换（键值均单字，长度 1:1，偏移不变）',
        'dict_words': n_dict,
        'dict_files': cfg['zh_dicts'],
        'builtin_dict': cfg['use_builtin_zh'],
        'min_total_freq': cfg['min_freq_zh'],
        'stopwords': sorted(cfg['zh_stop']),
        'noise_guard': 'jieba 词典中「长度≥3 且频次<%d 且不在自有词典」的词条回退保守切分'
                       % cfg['min_dict_freq'],
        'no_truncation': '只在 CJK 连续段内按词切分；结果必须原样重建该段（拼接 == 原文）',
        'forbidden': '固定长度滑动窗口 / 单字滑动窗口 / 跨标点-数字-拉丁合并',
    }
    meta['books'] = collections.OrderedDict()
    for st in sorted(stats, key=lambda s: s['book_id']):
        meta['books'][st['book_id']] = collections.OrderedDict([
            ('book', st['book']), ('lang', st['lang']),
            ('gutenberg_id', cfg['gid'].get(st['book_id'], '')),
            ('chapters', st['chapters']), ('chars', st['chars']),
            ('keys', st['keys']), ('records', st['records']),
        ])
# ---- FINALIZE-2 ----

    summary = collections.OrderedDict()
    summary['granularity'] = cfg['granularity']
    summary['books'] = len(stats)
    summary['chapters'] = sum(s['chapters'] for s in stats)
    summary['tokens_scanned'] = sum(s['tokens'] for s in stats)
    summary['records'] = writer.count
    summary['words'] = len(agg)
    summary['by_lang'] = by_lang
    summary['selected'] = {'missing_zh': miss_zh, 'missing_en': miss_en}
    summary['verify'] = {'chapters': sum(s['chapters'] for s in stats),
                         'tokens': sum(s['tokens'] for s in stats),
                         'failures': len(problems), 'details': problems[:10]}
    summary['seconds'] = round(elapsed, 1)

    print('\n== 汇总（%.1fs ｜ 粒度 %s）' % (elapsed, cfg['granularity']))
    for lg, name in (('zh', '中文'), ('en', '英文')):
        d = by_lang[lg]
        print('   %s：词 %d ｜ 词次 %d ｜ top: %s'
              % (name, d['words'], d['tokens'],
                 '、'.join('%s(%d)' % (w, c) for w, c in d['top'][:8])))
    print('   总计：%d 本 / %d 章 / 记录 %d / 唯一词 %d'
          % (summary['books'], summary['chapters'], summary['records'], summary['words']))
    if cfg['sel_en'] or cfg['sel_zh']:
        print('   划选词：未命中 中文 %s ｜ 英文 %s' % (miss_zh or '无', miss_en or '无'))
    if problems:
        print('   ⚠️ 自检失败 %d 本：%s' % (len(problems), [p['book_id'] for p in problems]))
    else:
        print('   ✅ 自检通过：%d 章 / %d 词次全部满足「无截断、无错切、可原样重建」'
              % (summary['verify']['chapters'], summary['verify']['tokens']))

    if problems and not cfg['force']:
        if writer.f and not writer.f.closed:
            writer.f.close()
        if os.path.exists(cfg['out'] + '.part'):
            os.remove(cfg['out'] + '.part')
        print('✗ 存在自检失败，未写出（确认无误可加 --force 强制写出）')
        return 1
    if cfg['dry_run']:
        print('（--dry-run：未写文件）%s ≈ %d 条记录' % (cfg['out'], writer.count))
        return 0
    size = writer.close(meta, summary)
    print('✅ 已写出 %s（%d 条记录，%.1f MiB）' % (cfg['out'], writer.count, size / 1048576.0))
    if not reread_check(cfg['out'], writer.count):
        return 1
    return 0


def reread_check(path, expect):
    """写后回读校验：文件必须能解析、记录数与写出条数一致、必备字段齐全。"""
    try:
        with open(path, encoding='utf-8') as f:
            d = json.load(f)
    except Exception as e:
        print('✗ 回读失败（文件损坏）：%s' % e)
        return False
    words = d.get('words') or []
    need = {'word', 'frequency', 'book_id', 'chapter_id', 'contexts'}
    miss = [k for k in need if k not in (words[0] if words else {})]
    if len(words) != expect or miss or '_meta' not in d or 'summary' not in d:
        print('✗ 回读校验失败：记录 %d（应为 %d）｜ 缺字段 %s｜ _meta/summary %s'
              % (len(words), expect, miss, '_meta' in d and 'summary' in d))
        return False
    print('   ✅ 回读校验：JSON 可解析、%d 条记录、必备字段齐全' % len(words))
    return True



def main():
    pos, flags, opts = parse_args(sys.argv[1:])
    if 'help' in flags or 'h' in flags:
        print(__doc__)
        return 0
    global _TABLE
    _TABLE = load_trad_simp_table()
    table = _TABLE
    if not table:
        print('⚠️ 缺 %s：繁→简 不可用，古文分词质量会退化' % TRAD_SIMP_FILE)
    cfg = build_cfg(flags, opts, table)
    if cfg['lang'] not in ('all', 'zh', 'en'):
        print('✗ --lang 仅支持 all|zh|en（收到 %s）' % cfg['lang'])
        return 2
    if cfg['granularity'] not in ('word', 'book', 'chapter'):
        print('✗ --granularity 仅支持 word|book|chapter（收到 %s）' % cfg['granularity'])
        return 2
    if cfg['sort'] not in ('auto', 'book', 'freq'):
        print('✗ --sort 仅支持 auto|book|freq（收到 %s）' % cfg['sort'])
        return 2
    if cfg['sort'] == 'auto':
        cfg['sort'] = 'freq' if cfg['granularity'] == 'word' else 'book'
    if 'selftest' in flags:
        seg, _n = build_zh_segmenter(cfg['zh_dicts'], use_builtin=cfg['use_builtin_zh'],
                                     hmm=cfg['hmm'], no_jieba=cfg['no_jieba'],
                                     min_dict_freq=cfg['min_dict_freq'])
        print('== vocab_extract 规则自测（分词器：%s）' % seg.name)
        return 1 if selftest(cfg, seg, table) else 0
    return run(cfg, pos, table)


if __name__ == '__main__':
    sys.exit(main())


