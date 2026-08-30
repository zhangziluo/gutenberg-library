#!/bin/bash
# 古籍文库 · 本地站点启动器（macOS 双击即可运行）
# 在项目根目录启动 HTTP 服务器，并自动打开浏览器
cd "$(dirname "$0")"
cd ..

PORT=8000
URL="http://localhost:${PORT}/网站/index.html"

echo "================================================"
echo "  古籍文库 · 本地服务器"
echo "  访问地址: ${URL}"
echo "  按 Ctrl+C 停止服务器"
echo "================================================"

# 稍后自动打开浏览器
( sleep 1; open "${URL}" ) &

exec python3 -m http.server "${PORT}"
