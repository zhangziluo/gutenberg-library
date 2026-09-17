#!/bin/bash
# ============================================================
# pipeline.sh — 入库后的收尾流水线（一键跑完并提交）
#   ① 释义回填   fill_glosses.py
#   ② 自动分类   scripts/classify_books.py（需 DEEPSEEK_API_KEY；缺失则跳过）
#   ③ 构建合并   deploy/build.sh（产出 dist/）
#   ④ Git 提交   add + commit + push（有变更才提交）
#
# 用法（在 文本/新书/、项目根、任意目录都可调用）：
#   bash 文本/新书/pipeline.sh                # 全流程 + 提交 + 推送
#   bash 文本/新书/pipeline.sh --no-push      # 只提交不推送
#   bash 文本/新书/pipeline.sh --no-commit    # 回填/分类/构建，但不提交
#   bash 文本/新书/pipeline.sh --no-classify  # 跳过 DeepSeek 分类
#   bash 文本/新书/pipeline.sh --offline      # 回填不联网（只用 ECDICT 打底）
#   bash 文本/新书/pipeline.sh --classify-input <文件>   # 指定分类输入（默认 data/books.json）
#
# 注：DEEPSEEK_API_KEY 可写在项目根 .env（本脚本会自动载入；.env 已在 .gitignore 内）
#     分类脚本要求输入为「书对象 JSON 数组」且含 id 字段；本项目默认无 data/books.json，
#     故该步会在提示后自动跳过（不影响回填/构建/提交）。
# ============================================================
set -euo pipefail

SELF="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"
# 项目根 = 本脚本所在目录（文本/新书）的上上级
ROOT="$(cd "$(dirname "$SELF")/../.." && pwd)"
cd "$ROOT"

NO_PUSH=0; NO_CLASSIFY=0; OFFLINE=0; NO_COMMIT=0; CLASSIFY_INPUT="data/books.json"
while [ $# -gt 0 ]; do
  case "$1" in
    --no-push)     NO_PUSH=1; shift ;;
    --no-classify) NO_CLASSIFY=1; shift ;;
    --offline)     OFFLINE=1; shift ;;
    --no-commit)   NO_COMMIT=1; shift ;;
    --classify-input)
      if [ $# -lt 2 ]; then echo "--classify-input 需要一个文件路径"; exit 2; fi
      CLASSIFY_INPUT="$2"; shift 2 ;;
    -h|--help)     sed -n '2,20p' "$SELF"; exit 0 ;;
    *) echo "未知参数：${1}（支持 --no-push / --no-classify / --offline / --no-commit / --classify-input <文件>）"; exit 2 ;;
  esac
done

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
step() { echo -e "\n${GREEN}==>${NC} $1"; }
warn() { echo -e "${YELLOW}⚠${NC} $1"; }
err()  { echo -e "${RED}✗${NC} $1"; }

if [ -f "$ROOT/.env" ]; then
  set -a; . "$ROOT/.env"; set +a
  echo "已载入 .env"
fi

# ── 1. 释义回填 ──
step "词库回填 (fill_glosses.py)"
if [ "$OFFLINE" = "1" ]; then
  python3 "文本/新书/fill_glosses.py" --no-network
else
  python3 "文本/新书/fill_glosses.py"
fi

# ── 2. AI 自动分类 ──
step "AI 自动分类 (scripts/classify_books.py --only-empty)"
if [ "$NO_CLASSIFY" = "1" ]; then
  warn "已指定 --no-classify，跳过"
elif [ ! -f "scripts/classify_books.py" ]; then
  warn "scripts/classify_books.py 不存在，跳过"
elif [ ! -f "$CLASSIFY_INPUT" ]; then
  warn "分类输入不存在（${CLASSIFY_INPUT}；可用 --classify-input <文件> 指定），跳过自动分类"
elif [ -z "${DEEPSEEK_API_KEY:-}" ]; then
  warn "未设置 DEEPSEEK_API_KEY（可写入项目根 .env），跳过自动分类"
else
  python3 scripts/classify_books.py --input "$CLASSIFY_INPUT" --only-empty
fi

# ── 3. 构建合并 ──
step "构建合并 (deploy/build.sh → dist/)"
if [ -f "deploy/build.sh" ]; then
  bash deploy/build.sh
else
  warn "deploy/build.sh 不存在，跳过"
fi

# ── 4. Git 提交 ──
step "Git 提交"
if [ "$NO_COMMIT" = "1" ]; then
  warn "已指定 --no-commit，跳过 Git 提交"
elif git diff --quiet && git diff --cached --quiet; then
  warn "没有检测到变更，跳过 Git 操作"
else
  git add -A
  if git diff --cached --quiet; then
    warn "暂存区无变更，跳过提交"
  else
    NEW=$(git diff --cached --name-only --diff-filter=A | grep -c '^data/books/' || true)
    MOD=$(git diff --cached --name-only --diff-filter=M | grep -c '^data/books/' || true)
    MSG="更新书库"
    if [ "${NEW:-0}" -gt 0 ]; then MSG="$MSG: 新增${NEW}本"; fi
    if [ "${MOD:-0}" -gt 0 ]; then MSG="$MSG, 更新${MOD}本"; fi
    MSG="$MSG ($(date '+%Y-%m-%d %H:%M'))"
    git commit -m "$MSG"
    echo "✅ 已提交：$MSG"
    if [ "$NO_PUSH" = "1" ]; then
      warn "已指定 --no-push，跳过 git push"
    elif git rev-parse --abbrev-ref '@{u}' >/dev/null 2>&1; then
      git push
    else
      warn "当前分支未设置上游，跳过 git push"
    fi
  fi
fi

echo -e "\n${GREEN}✅ pipeline 全部完成（${ROOT}）${NC}"
