/* ============================================================
   在线词典代理 / 前端同域化 · 回归测试（node，无需依赖）
   ------------------------------------------------------------
   跑法：node tests/library/dict-proxy-test.js
   覆盖：
     A. 前端守卫：查词绝不直连第三方，统一走同域 /api/dict
     B. Pages Function（网站/functions/api/dict.js）行为：
        参数校验 / 正常转发（含 origin=*）/ 上游失败 / 页面不存在
        / 网络异常 / CORS 头 / OPTIONS 预检
   ============================================================ */
'use strict';

const fs = require('fs');
const path = require('path');
const { pathToFileURL } = require('url');

const ROOT = path.resolve(__dirname, '..', '..');
const READER = path.join(ROOT, '网站/js/reader.js');
const FN = path.join(ROOT, '网站/functions/api/dict.js');

let pass = 0;
let fail = 0;
function ok(cond, msg) {
  if (cond) { pass++; console.log('  ✅ ' + msg); }
  else { fail++; console.log('  ✗ ' + msg); }
}

/* ---------- A. 前端守卫 ---------- */
console.log('A. 前端（reader.js + dict-api.js）');
{
  const reader = fs.readFileSync(READER, 'utf8');
  const api = fs.readFileSync(path.join(path.dirname(READER), 'dict-api.js'), 'utf8');
  // 去掉注释再检查，避免把说明文字当成代码
  const strip = s => s.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|\s)\/\/.*$/gm, '');
  const code = strip(reader);
  const apiCode = strip(api);
  ok(apiCode.includes("'/api/dict'") && apiCode.includes("'?source='") &&
     apiCode.indexOf('api.dictionaryapi.dev') === -1,
     '在线查词走同域 /api/dict（不在前端拼第三方域名）');
  ok(apiCode.includes("'/api/dict-links'") && apiCode.includes("'/api/translate'"),
     '外链与翻译也走同域 /api/*');
  ok(!code.includes('rest_v1/page/summary'), '不再使用 REST page/summary');
  ok(!/https?:\/\/zh\.(wikipedia|wiktionary)\.org/.test(code) &&
     !/https?:\/\/zh\.(wikipedia|wiktionary)\.org/.test(apiCode),
     '不再直连 zh.wikipedia.org / zh.wiktionary.org');
  ok(!/https?:\/\//.test(apiCode.replace(/https?:\/\/(api\.dictionaryapi\.dev|www\.moedict\.tw)[^\s'"]*/g, '')),
     'dict-api.js 里除注释外没有第三方直连 URL');
  ok(code.includes('在线释义暂不可用'), '在线失败时有兜底文案「在线释义暂不可用」');
  ok(code.includes('未找到释义'), '全部源失败时有「未找到释义」');
}

/* ---------- B. 代理函数 ---------- */
console.log('\nB. Pages Function（/api/dict）');

(async () => {
  const mod = await import(pathToFileURL(FN).href);
  const handler = mod.onRequest;
  ok(typeof handler === 'function', '导出 onRequest');

  const realFetch = globalThis.fetch;
  let lastUrl = null;

  function stubFetch(impl) {
    globalThis.fetch = async (url, init) => {
      lastUrl = String(url);
      return impl(url, init);
    };
  }
  function jsonResponse(body, status = 200) {
    return new Response(JSON.stringify(body), {
      status, headers: { 'content-type': 'application/json' },
    });
  }
  const call = (qs, method = 'GET') => handler({
    request: new Request('https://myfami.cn/api/dict?' + qs, { method }),
  });

  // 1) 缺 q
  let r = await call('source=wikipedia&lang=zh');
  ok(r.status === 400 && (await r.json()).error === 'missing q', '缺 q → 400 {"error":"missing q"}');

  // 2) 非法 source
  r = await call('source=baidu&lang=zh&q=仁');
  ok(r.status === 400 && (await r.json()).error === 'bad source', '非法 source → 400 bad source');

  // 3) 正常
  stubFetch(() => jsonResponse({
    query: { pages: { '123': { pageid: 123, title: '仁', extract: '儒家核心概念，指愛人。' } } },
  }));
  r = await call('source=wikipedia&lang=zh&q=%E4%BB%81');
  const body = await r.json();
  ok(r.status === 200 && body.extract && body.extract.indexOf('儒家') === 0, '正常路径返回 extract');
  ok(r.headers.get('Access-Control-Allow-Origin') === '*', '响应头带 Access-Control-Allow-Origin: *');
  ok(lastUrl.indexOf('action=query') !== -1 && lastUrl.indexOf('origin=*') !== -1,
     '转发到 Action API 且带 origin=*');
  ok(decodeURIComponent(lastUrl).indexOf('titles=仁') !== -1, '把 q 作为 titles 转发');
  ok(lastUrl.indexOf('zh.wikipedia.org') !== -1, 'source=wikipedia 命中 zh.wikipedia.org');

  // 3b) wiktionary 主机不同
  await call('source=wiktionary&lang=zh&q=%E4%BB%81');
  ok(lastUrl.indexOf('zh.wiktionary.org') !== -1, 'source=wiktionary 命中 zh.wiktionary.org');

  // 4) 页面不存在
  stubFetch(() => jsonResponse({ query: { pages: { '-1': { title: '不存在', missing: '' } } } }));
  r = await call('source=wikipedia&lang=zh&q=%E4%B8%8D%E5%AD%98%E5%9C%A8');
  ok(r.status === 200 && (await r.json()).error === 'not found', '页面不存在 → 200 not found');

  // 5) 上游 5xx
  stubFetch(() => jsonResponse({}, 503));
  r = await call('source=wikipedia&lang=zh&q=%E4%BB%81');
  ok(r.status === 502 && (await r.json()).error === 'fetch failed', '上游 5xx → 502 fetch failed');

  // 6) 网络异常 / 超时
  stubFetch(() => { throw new Error('network down'); });
  r = await call('source=wikipedia&lang=zh&q=%E4%BB%81');
  const e6 = await r.json();
  ok(r.status === 502 && e6.error === 'fetch failed', '网络异常 → 502（不抛给前端）');
  ok(r.headers.get('Access-Control-Allow-Origin') === '*', '错误响应也带 CORS 头');

  // 7) OPTIONS 预检
  r = await call('', 'OPTIONS');
  ok(r.status === 204 && r.headers.get('Access-Control-Allow-Origin') === '*',
     'OPTIONS → 204 + CORS 头');

  globalThis.fetch = realFetch;

  console.log('\n结果：' + pass + ' 通过 / ' + fail + ' 失败');
  process.exit(fail ? 1 : 0);
})().catch(e => {
  console.error('测试异常：', e);
  process.exit(2);
});
