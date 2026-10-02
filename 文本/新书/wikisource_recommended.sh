#!/usr/bin/env bash
# ============================================================
# wikisource_recommended.sh — 维基文库「推荐优先」一条龙
#   ① 批量抓取（recommended ⭐ 且未入库，可续跑）
#   ② 逐本入库（wikisource_import：**智能分章 + 生成注释**）
#   ③ 释义回填（fill_glosses.py）④ 重建目录/阅读器数据
#
# 用法（任意目录）：
#   bash 文本/新书/wikisource_recommended.sh            # 全量（122 本，耗时较长）
#   bash 文本/新书/wikisource_recommended.sh 10         # 只做前 10 本（试水）
#
# 只想要「入库命令脚本」而不执行：
#   .venv/bin/python 文本/新书/wikisource_batch.py commands
#
# 断点续跑：进度在 文本/新书/_ws_fetch/{fetch_state,ingest_state}.tsv，重跑自动跳过。
# ============================================================
set -euo pipefail

SELF="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"
DIR="$(dirname "$SELF")"
ROOT="$(cd "$DIR/../.." && pwd)"

PY="$ROOT/.venv/bin/python"
if [ ! -x "$PY" ]; then PY="python3"; fi

LIMIT="${1:-}"
BATCH="$DIR/wikisource_batch.py"

GREEN='\033[0;32m'; NC='\033[0m'
step() { echo -e "\n${GREEN}==>${NC} $1"; }

if [ -n "$LIMIT" ]; then
  step "① 抓取（前 ${LIMIT} 本）"
  "$PY" "$BATCH" fetch --limit "$LIMIT"
  step "② 入库 + 释义回填 + 重建（前 ${LIMIT} 本）"
  "$PY" "$BATCH" ingest --limit "$LIMIT"
else
  step "① 抓取（全部推荐清单）"
  "$PY" "$BATCH" fetch
  step "② 入库 + 释义回填 + 重建（全部）"
  "$PY" "$BATCH" ingest
fi

echo -e "\n${GREEN}🎉 完成。检查后若要上线：${NC}"
echo "  git add -A && git commit -m '维基文库入库：推荐清单' && git push"
