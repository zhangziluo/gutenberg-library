#!/bin/bash
# ============================================================
# 一堆古书 · Cloudflare Pages 构建脚本
# 将仓库整理为可直接托管的 dist/：
#   主站(网站/) + 站点数据(网站/_site_data/)
# Cloudflare 设置：构建命令 `bash deploy/build.sh`，输出目录 `dist`
# ============================================================
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DIST="$ROOT/dist"

echo "==> 构建输出目录: $DIST"
rm -rf "$DIST"
mkdir -p "$DIST"

# 1. 主站页面
echo "==> 复制主站页面"
cp -R "$ROOT/网站/index.html" "$ROOT/网站/book.html" "$ROOT/网站/reader.html" "$ROOT/网站/sponsor.html" "$ROOT/网站/library.html" "$ROOT/网站/links.html" "$ROOT/网站/ai-settings.html" "$ROOT/网站/ai-guide.html" "$DIST/"
cp -R "$ROOT/网站/css" "$ROOT/网站/js" "$DIST/"
cp -R "$ROOT/网站/writing" "$DIST/"
cp -R "$ROOT/网站/category" "$DIST/"

# 2. 站点数据：数据已迁至 网站/_site_data，部署为站点根下 /_site_data/
#    （前端 js/common.js DATA_BASE='_site_data/'，即请求 /_site_data/{书名}.json）
echo "==> 复制站点数据"
cp -R "$ROOT/网站/_site_data" "$DIST/_site_data"

# 2.1 books.json 瘦身为轻量目录（正文/注释走单书文件，规避 Cloudflare Pages 25 MiB 单文件上限）
echo "==> 重建轻量书库目录 books.json"
python3 "$ROOT/文本/新书/slim_books_index.py" "$DIST/_site_data"

# 2.5 图片资源（捐助页二维码等）
echo "==> 复制图片资源"
cp -R "$ROOT/网站/assets" "$DIST/assets"

# 3. Cloudflare 辅助文件（_headers / _redirects，如有则带上）
if [ -f "$ROOT/网站/_headers" ]; then
  cp "$ROOT/网站/_headers" "$DIST/_headers"
fi
if [ -f "$ROOT/网站/_redirects" ]; then
  cp "$ROOT/网站/_redirects" "$DIST/_redirects"
fi

# 3.5 Pages Functions（同域代理，如 /api/dict —— 在线词典走它，前端绝不直连第三方）
if [ -d "$ROOT/网站/functions" ]; then
  echo "==> 复制 Pages Functions"
  cp -R "$ROOT/网站/functions" "$DIST/functions"
fi

# 4. 句子池（今日一句：library/sentences/*.json + sentence-manifest.json）
echo "==> 复制句子池"
cp -R "$ROOT/网站/library" "$DIST/library"

# 清理 macOS 垃圾文件
find "$DIST" -name '.DS_Store' -delete

# 硬校验：单文件不得超过 Cloudflare Pages 的 25 MiB 上限
# （超标会让 Pages 构建直接失败；超大字书应在 merge_to_site 里自动分片）
echo "==> 校验单文件体积（Pages 上限 25 MiB）"
python3 - "$DIST" <<'PY'
import os
import sys

limit = 25 * 1024 * 1024
bad = []
for root, _dirs, files in os.walk(sys.argv[1]):
    for fn in files:
        p = os.path.join(root, fn)
        sz = os.path.getsize(p)
        if sz > limit:
            bad.append((os.path.relpath(p, sys.argv[1]), sz))
if bad:
    for rp, sz in sorted(bad, key=lambda x: -x[1]):
        print('❌ 超 25 MiB：%s（%.1f MiB）' % (rp, sz / 1048576.0))
    print('   提示：大部头应在 文本/新书/merge_to_site.py（write_site_book）里自动分片')
    sys.exit(1)
print('  ✅ 无超限文件')
PY

echo "==> 构建完成:"
du -sh "$DIST"
echo "==> 文件数: $(find "$DIST" -type f | wc -l | tr -d ' ')"
