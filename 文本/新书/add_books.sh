#!/bin/bash
# ============================================================
# add_books.sh — 一条龙：书源 → 入库 → 收尾流水线
#   支持两个书源：古登堡计划（默认）与 维基文库
#
# 用法（在 文本/新书/、项目根、任意目录都可调用）：
#   # 古登堡计划（默认）
#   bash 文本/新书/add_books.sh 12345 67890             # 直接给编号
#   bash 文本/新书/add_books.sh --file i.txt            # 从列表文件（每行「编号 [书名]」）
#   bash 文本/新书/add_books.sh --file i.txt --lang en  # 显式指定语种
#   bash 文本/新书/add_books.sh --file i.txt --dry-run  # 只预览（不下载、不写文件）
#
#   # 维基文库（--source wikisource）
#   bash 文本/新书/add_books.sh --source wikisource --title "儒林外史" \
#       --key rulin-waishi --author 吳敬梓 --category 子部 --subcategory 小說家 --label 回
#   bash 文本/新书/add_books.sh --source wikisource --json novels_json/論語.json \
#       --author 孔子 --category 經部 --subcategory 四書
#
# 选项：
#   --source gutenberg|wikisource   书源（默认 gutenberg）
#   --file <列表>       从文件读编号（古登堡）；相对路径按「调用时的工作目录」解析
#   --lang auto|zh|en   语种（古登堡；默认 auto：按书名有无汉字判定，纯编号回退 zh）
#   --title <书名>      维基文库页面标题（自动抓取后入库）
#   --json <文件>       维基文库已抓取的 novels_json 文件（跳过抓取）
#   --key <key>         维基文库入库 key（data/books/{key}.json；省略则从书名推导）
#   --author <作者>     作者（默认 佚名）
#   --category <分类>   五部分类（古登堡/维基文库共用；默认 子部）
#   --subcategory <子类> 子分类
#   --label <篇|回|卷|章> 维基文库篇目标签（默认 篇）
#   --force             维基文库存在受限/未知章节时仍导入（跳过它们）
#   --dry-run           古登堡只解析元数据打印预览，不入库、不跑后续流水线
#   --no-pipeline       只入库，不跑 pipeline.sh
#   --xxx [值]          其余参数原样透传给 gutenberg_import.py（古登堡；如 --split hui）
# ============================================================
set -euo pipefail

SELF="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"
DIR="$(dirname "$SELF")"
ROOT="$(cd "$DIR/../.." && pwd)"          # 项目根（文本/新书 的上两级）

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
step() { echo -e "\n${GREEN}==>${NC} $1"; }
warn() { echo -e "${YELLOW}⚠${NC} $1"; }
err()  { echo -e "${RED}✗${NC} $1"; }

# gutenberg_import.py 里「带值」的选项（透传时需连带其后一个参数）
VALUE_OPTS=" ids list id-list split search list-by-lang max "
is_value_opt() { case "$VALUE_OPTS" in *" $1 "*) return 0 ;; *) return 1 ;; esac; }

IDS_FILE=""; LANG_OPT="auto"; DRY=0; NO_PIPE=0
SOURCE="gutenberg"              # gutenberg | wikisource
WS_TITLE=""; WS_JSON=""; WS_KEY=""; WS_AUTHOR=""; CAT=""; SUBCAT=""; WS_LABEL="篇"; WS_FORCE=0
IDS_ARGS=(); FORWARD=()

while [ $# -gt 0 ]; do
  case "$1" in
    --file)
      if [ $# -lt 2 ]; then err "--file 需要一个文件路径"; exit 2; fi
      IDS_FILE="$2"; shift 2 ;;
    --lang)
      if [ $# -lt 2 ]; then err "--lang 需要一个值（auto|zh|en）"; exit 2; fi
      LANG_OPT="$2"; shift 2 ;;
    --source)
      if [ $# -lt 2 ]; then err "--source 需要一个值（gutenberg|wikisource）"; exit 2; fi
      SOURCE="$2"; shift 2 ;;
    --title)
      if [ $# -lt 2 ]; then err "--title 需要一个值（维基文库书名）"; exit 2; fi
      WS_TITLE="$2"; shift 2 ;;
    --json)
      if [ $# -lt 2 ]; then err "--json 需要一个值（novels_json 文件路径）"; exit 2; fi
      WS_JSON="$2"; shift 2 ;;
    --key)
      if [ $# -lt 2 ]; then err "--key 需要一个值"; exit 2; fi
      WS_KEY="$2"; shift 2 ;;
    --author)
      if [ $# -lt 2 ]; then err "--author 需要一个值"; exit 2; fi
      WS_AUTHOR="$2"; shift 2 ;;
    --category)
      if [ $# -lt 2 ]; then err "--category 需要一个值"; exit 2; fi
      CAT="$2"; shift 2 ;;
    --subcategory)
      if [ $# -lt 2 ]; then err "--subcategory 需要一个值"; exit 2; fi
      SUBCAT="$2"; shift 2 ;;
    --label)
      if [ $# -lt 2 ]; then err "--label 需要一个值（篇/回/卷/章）"; exit 2; fi
      WS_LABEL="$2"; shift 2 ;;
    --force)       WS_FORCE=1; shift ;;
    --dry-run)     DRY=1; shift ;;
    --no-pipeline) NO_PIPE=1; shift ;;
    -h|--help)     sed -n '2,33p' "$SELF"; exit 0 ;;
    --*)
      if is_value_opt "${1#--}" && [ $# -ge 2 ]; then
        FORWARD+=("$1" "$2"); shift 2
      else
        FORWARD+=("$1"); shift
      fi ;;
    *)
      if [[ "$1" =~ ^[0-9]+$ ]]; then IDS_ARGS+=("$1"); shift
      else err "无法识别参数：$1（编号须为纯数字，或用 --file 指定清单）"; exit 2; fi ;;
  esac
done

case "$SOURCE" in gutenberg|wikisource) : ;; *) err "--source 仅支持 gutenberg|wikisource"; exit 2 ;; esac

# ── 维基文库入库（wikisource_toolkit.py fetch + wikisource_import.py）──
if [ "$SOURCE" = "wikisource" ]; then
  if [ -z "$WS_TITLE" ] && [ -z "$WS_JSON" ]; then
    err "维基文库入库需 --title <书名> 或 --json <novels_json 文件>"; exit 1
  fi
  if [ "$DRY" = "1" ]; then warn "维基文库暂不支持 --dry-run，已忽略"; fi

  # 1) 抓取（给了 --title 才抓；--json 则跳过）
  if [ -n "$WS_TITLE" ]; then
    step "1/3 抓取维基文库（wikisource_toolkit.py fetch「${WS_TITLE}」）"
    ( cd "$DIR/wikisource_complete_toolkit" && python3 wikisource_toolkit.py fetch "$WS_TITLE" )
    WS_FNAME="$(python3 -c 'import sys,re; s=re.sub(r"[^\w\u4e00-\u9fff]+","_",sys.argv[1]).strip("_"); print(s or "book")' "$WS_TITLE")"
    WS_JSON="$DIR/wikisource_complete_toolkit/novels_json/${WS_FNAME}.json"
  fi

  # 2) 入库
  step "2/3 入库（wikisource_import.py --json ${WS_JSON}）"
  IARGS=(--json "$WS_JSON")
  [ -n "$WS_KEY" ] && IARGS+=(--key "$WS_KEY")
  [ -n "$WS_AUTHOR" ] && IARGS+=(--author "$WS_AUTHOR")
  [ -n "$CAT" ] && IARGS+=(--category "$CAT")
  [ -n "$SUBCAT" ] && IARGS+=(--subcategory "$SUBCAT")
  [ -n "$WS_LABEL" ] && IARGS+=(--label "$WS_LABEL")
  [ "$WS_FORCE" = "1" ] && IARGS+=(--force)
  python3 "$DIR/wikisource_import.py" "${IARGS[@]}"

  # 3) 收尾流水线
  if [ "$NO_PIPE" = "1" ]; then warn "已指定 --no-pipeline，跳过收尾流水线"; exit 0; fi
  step "3/3 收尾流水线（pipeline.sh）"
  bash "$DIR/pipeline.sh"
  echo -e "\n${GREEN}🎉 一条龙完成${NC}"
  exit 0
fi

case "$LANG_OPT" in auto|zh|en) : ;; *) err "--lang 仅支持 auto|zh|en"; exit 2 ;; esac

# --file 相对路径 → 按调用时 cwd 解析为绝对路径（本脚本自身不 cd）
if [ -n "$IDS_FILE" ]; then
  case "$IDS_FILE" in
    /*) : ;;
    *)  IDS_FILE="$(pwd)/$IDS_FILE" ;;
  esac
  if [ ! -s "$IDS_FILE" ]; then err "找不到或为空：$IDS_FILE"; exit 1; fi
fi

TMP_IDS=""
cleanup() { if [ -n "$TMP_IDS" ] && [ -f "$TMP_IDS" ]; then rm -f "$TMP_IDS"; fi; }
trap cleanup EXIT

if [ -z "$IDS_FILE" ]; then
  if [ "${#IDS_ARGS[@]}" -eq 0 ]; then
    err "没有编号。用法：bash $0 --file i.txt   或   bash $0 12345 67890"
    exit 1
  fi
  TMP_IDS="$(mktemp "${TMPDIR:-/tmp}/_guten_ids.XXXXXX")"
  printf '%s\n' "${IDS_ARGS[@]}" > "$TMP_IDS"
  IDS_FILE="$TMP_IDS"
fi

# 语种自适应：清单书名含汉字 → zh；有书名但全无汉字 → en；无书名（纯编号）→ zh
if [ "$LANG_OPT" = "auto" ]; then
  LANG_OPT="$(python3 -c '
import re, sys
cjk = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
title_seen = False
for line in open(sys.argv[1], encoding="utf-8", errors="replace"):
    m = re.match(r"^\s*#?\s*(\d+)\s*(.*)$", line.strip())
    if not m:
        continue
    rest = m.group(2).strip()
    if not rest:
        continue
    title_seen = True
    if cjk.search(rest):
        print("zh"); sys.exit(0)
print("zh" if not title_seen else "en")
' "$IDS_FILE")"
  echo "已自动判定语种：$LANG_OPT"
fi

# ── 1/2 入库 ──
step "1/2 入库（gutenberg_import.py --ids <清单> --lang ${LANG_OPT}）"
ARGS=(--ids "$IDS_FILE")
if [ "$LANG_OPT" = "en" ]; then ARGS+=(--lang en); fi
[ -n "$CAT" ] && ARGS+=(--category "$CAT")
[ -n "$SUBCAT" ] && ARGS+=(--subcategory "$SUBCAT")
if [ "$DRY" = "1" ]; then ARGS+=(--dry-run); fi
if [ "${#FORWARD[@]}" -gt 0 ]; then ARGS+=("${FORWARD[@]}"); fi
python3 "$DIR/gutenberg_import.py" "${ARGS[@]}"

if [ "$DRY" = "1" ]; then
  warn "--dry-run：仅预览，未下载、未入库、未跑后续流水线"
  exit 0
fi

if [ "$NO_PIPE" = "1" ]; then
  warn "已指定 --no-pipeline，跳过收尾流水线"
  exit 0
fi

# ── 2/2 收尾流水线 ──
step "2/2 收尾流水线（pipeline.sh）"
bash "$DIR/pipeline.sh"

echo -e "\n${GREEN}🎉 一条龙完成${NC}"
