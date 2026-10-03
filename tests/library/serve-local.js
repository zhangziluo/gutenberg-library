#!/usr/bin/env node
/* ============================================================
   本地预览服务器（网站/ 静态 + /api/* 走真实 Pages Function）
   ------------------------------------------------------------
   用途：本地模拟「同域代理」环境，人工点开阅读页验证查词面板。
   跑法：node tests/library/serve-local.js [端口]
         → http://127.0.0.1:8788/reader.html?book=論語&index=1
   （与 Cloudflare Pages 的行为一致：静态资源 + functions/ 目录下的同域接口；
     若装了 wrangler，也可直接用 `npx wrangler pages dev 网站` 替代本脚本。）
   ============================================================ */
'use strict';

const fs = require('fs');
const http = require('http');
const path = require('path');
const { pathToFileURL } = require('url');

const SITE = path.resolve(__dirname, '../../网站');
const PORT = parseInt(process.argv[2] || '8788', 10);

const TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.ico': 'image/x-icon',
  '.txt': 'text/plain; charset=utf-8',
};

const fnCache = {};
/** 按 /api/<name> 动态加载 functions/api/<name>.js（与 Pages 的路由行为一致） */
function loadFn(name) {
  if (!/^[a-z0-9-]+$/.test(name)) return Promise.reject(new Error('bad api name: ' + name));
  if (!fnCache[name]) {
    fnCache[name] = import(pathToFileURL(path.join(SITE, 'functions/api/' + name + '.js')).href)
      .catch(function (e) {
        fnCache[name] = null;
        throw new Error('没有这个接口：/api/' + name + '（' + (e && e.message) + '）');
      });
  }
  return fnCache[name];
}

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, 'http://' + (req.headers.host || '127.0.0.1'));

  // ── 同域接口：/api/* → Pages Function ──
  if (url.pathname.startsWith('/api/')) {
    const name = url.pathname.replace(/^\/api\//, '').replace(/\/$/, '');
    try {
      const mod = await loadFn(name);
      if (mod && typeof mod.onRequest === 'function') {
        const fnReq = new Request(url.href, { method: req.method, headers: req.headers });
        const fnRes = await mod.onRequest({ request: fnReq });
        res.writeHead(fnRes.status, Object.fromEntries(fnRes.headers));
        res.end(await fnRes.text());
        return;
      }
    } catch (e) {
      res.writeHead(500, { 'content-type': 'application/json; charset=utf-8' });
      res.end(JSON.stringify({ error: 'local function error', detail: String(e && e.message) }));
      return;
    }
    res.writeHead(404, { 'content-type': 'application/json; charset=utf-8' });
    res.end(JSON.stringify({ error: 'no such api function: ' + name }));
    return;
  }

  // ── 静态资源 ──
  let p = decodeURIComponent(url.pathname);
  if (p === '/' || p.endsWith('/')) p += 'index.html';
  const file = path.join(SITE, p);
  if (!file.startsWith(SITE)) { res.writeHead(403); res.end('forbidden'); return; }
  fs.readFile(file, (err, data) => {
    if (err) { res.writeHead(404, { 'content-type': 'text/plain; charset=utf-8' }); res.end('404'); return; }
    res.writeHead(200, { 'content-type': TYPES[path.extname(file)] || 'application/octet-stream' });
    res.end(data);
  });
});

server.listen(PORT, '127.0.0.1', () => {
  console.log('本地预览：http://127.0.0.1:' + PORT + '/reader.html?book=' +
              encodeURIComponent('論語') + '&index=1');
  console.log('同域接口：http://127.0.0.1:' + PORT +
              '/api/dict?source=wikipedia&lang=zh&q=' + encodeURIComponent('仁'));
});
