#!/bin/bash
# ============================================================
# 古籍文库 · Cloudflare Pages 构建脚本
# 将仓库整理为可直接托管的 dist/：
#   主站(网站/) + 站点数据(文本/_site_data/) + AI 阅读器(/reader/) + Functions(/api/*)
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
cp -R "$ROOT/网站/index.html" "$ROOT/网站/book.html" "$ROOT/网站/reader.html" "$DIST/"
cp -R "$ROOT/网站/css" "$ROOT/网站/js" "$DIST/"
cp -R "$ROOT/网站/writing" "$DIST/"

# 2. 站点数据：页面位于根目录时，../文本/_site_data/ 解析为 /文本/_site_data/
echo "==> 复制站点数据"
mkdir -p "$DIST/文本"
cp -R "$ROOT/文本/_site_data" "$DIST/文本/"

# 3. AI 阅读器 → /reader/（复制真实文件，不依赖软链接）
echo "==> 复制 AI 阅读器"
cp -R "$ROOT/网站/public/reader" "$DIST/reader"
rm -rf "$DIST/reader/functions"    # functions 统一放到输出根，交给 Cloudflare Pages 收集

# 4. Cloudflare Pages Functions（/api/* 路由）
echo "==> 复制 Functions"
cp -R "$ROOT/网站/public/reader/functions" "$DIST/functions"

# 5. Cloudflare 辅助文件（_headers / _redirects，如有则带上）
for f in _headers _redirects; do
  if [ -f "$ROOT/网站/$f" ]; then
    cp "$ROOT/网站/$f" "$DIST/$f"
  fi
done

# 清理 macOS 垃圾文件
find "$DIST" -name '.DS_Store' -delete

echo "==> 构建完成:"
du -sh "$DIST"
echo "==> 文件数: $(find "$DIST" -type f | wc -l | tr -d ' ')"
