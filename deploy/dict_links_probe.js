#!/usr/bin/env node
/* ============================================================
   dict_links_probe.js —— 站外词典探活（每周一次）
   ------------------------------------------------------------
   探谁：
     · 國學大師 guoxuedashi      —— HEAD 状态码 + **页面关键字**（识别阿里云拦截页）
     · 中華典藏 zhonghuadiancang —— 域名解析 + 200 状态码（可选关键字）
   不探谁：
     · 漢典 / ctext —— 默认首选，一直可用，无需探活
     · 中文維基詞典 —— 它是「被墙」而非「站点故障」，归「容错外链」开关管，探活无意义
   状态机（写进 网站/_site_data/dict/dict_links.json，前端 js/dict-links.js 读取）：
     ok  → streak_ok+1, streak_fail=0；streak_ok  ≥ 2 → state=enabled（自动展示）
     fail→ streak_fail+1, streak_ok=0；streak_fail ≥ 2 → state=hidden
     未达阈值时**保持原 state**（观察中，不折腾用户）
   ⚠️ 请在**境内网络**跑（本机 cron / 境内服务器）：
     这两个站的问题（未备案被阿里云拦 / 被墙）只在境内网络出现；
     在境外 CI 上跑会把「能通」误判为可用，反而把坏源打开。
   用法：
     node deploy/dict_links_probe.js              # 探活并写状态文件
     node deploy/dict_links_probe.js --dry-run    # 只看结论，不写盘
     node deploy/dict_links_probe.js --only guoxuedashi
     node deploy/dict_links_probe.js --commit     # 写盘后 git add + commit（推送由你决定）
     node deploy/dict_links_probe.js --push       # commit 后再 push（push 会自动触发 CF 构建）
     node deploy/dict_links_probe.js --quiet      # 只输出一行结论（适合 cron 日志）
   每周一次（crontab，周一 09:10）：
     10 9 * * 1 cd /path/to/repo && node deploy/dict_links_probe.js --quiet >> /tmp/dict_probe.log 2>&1
   Worker 化：核心只依赖全局 fetch + Promise，可被 Worker 的 scheduled 事件直接调用
     （把 loadStatus/saveStatus 换成 KV 读写即可）；文件末尾已导出这些函数。
   ============================================================ */
'use strict';

const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');

const ROOT = path.resolve(__dirname, '..');
const STATUS_FILE = path.join(ROOT, '网站', '_site_data', 'dict', 'dict_links.json');
const UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 ' +
           '(KHTML, like Gecko) Chrome/124.0 Safari/537.36 yidaogushu-dict-probe/1.0';

const DEFAULT_POLICY = { promote_after_ok: 2, demote_after_fail: 2 };

/** 拦截页 / 故障页特征：命中即判失败（阿里云未备案拦截、运营商拦截、WAF 拒绝…） */
const BLOCK_PATTERNS = [
  /阿里云/i, /Aliyun/i, /未备案/, /域名未备案/, /网站未备案/, /ICP备案/, /备案信息/,
  /网站暂时无法访问/, /该网站暂时无法/, /域名暂时无法/, /拦截/, /访问被拒绝/,
  /Forbidden/i, /Access Denied/i, /Site not found/i, /连接已重置/
];

/** 真实站点应有特征：至少命中一个，避免把「别的错误页」当成功 */
const SITE_PATTERNS = {
  guoxuedashi: [/國學大師/, /国学大师/, /guoxuedashi/i, /漢典/, /康熙字典/, /古籍/, /說文/],
  zhonghuadiancang: [/中華典藏/, /中华典藏/, /zhonghuadiancang/i, /典藏/, /古籍/, /國學/, /国学/, /詩詞|诗词/]
};

/** 被探活的源（kind: keyword = 状态码 + 关键字都必须过；dns = 只要能解析且 200） */
const PROBED = [
  {
    id: 'guoxuedashi', label: '國學大師', kind: 'keyword',
    url: 'https://www.guoxuedashi.net/',
    why: '未备案被阿里云拦截'
  },
  {
    id: 'zhonghuadiancang', label: '中華典藏', kind: 'dns',
    url: 'https://www.zhonghuadiancang.com/',
    why: '域名失效 / 服务器宕机'
  }
];

/* ---------------- 网络：带超时的 fetch（Worker 里同样可用） ---------------- */
async function fetchWithTimeout(url, opts, ms) {
  const ctl = (typeof AbortController !== 'undefined') ? new AbortController() : null;
  const timer = setTimeout(function () { if (ctl) ctl.abort(); }, ms);
  try {
    return await fetch(url, Object.assign({
      redirect: 'follow', signal: ctl ? ctl.signal : undefined,
      headers: { 'User-Agent': UA, 'Accept': 'text/html,application/xhtml+xml,*/*' }
    }, opts || {}));
  } finally {
    clearTimeout(timer);
  }
}

/** DNS 解析检查（Node 专属；在 Worker 里 require 会抛错 → 返回空，不影响结论） */
async function dnsCheck(host) {
  try {
    const dns = require('dns').promises;
    const ips = await dns.resolve4(host);
    return ips[0] || '';
  } catch (e) {
    return '';
  }
}

/* ---------------- 探测单个源（纯函数，便于单测 / Worker 复用） ---------------- */
/**
 * @returns {Promise<{id,label,ok,status,final_url,dns,detail}>}
 *   ok=true 才算探活成功（连续 2 次成功才 enabled）
 */
async function probeOne(src, opts) {
  opts = opts || {};
  const timeout = opts.timeout || 12000;
  const dnsFn = opts.dns || dnsCheck;          // 注入点：单测里别真去查 DNS
  const out = { id: src.id, label: src.label, ok: false, status: 0,
                final_url: src.url, dns: '', detail: '' };
  // ① DNS（Node 下能查就查；查不到不算失败，交给 fetch 判定）
  try {
    out.dns = await dnsFn(new URL(src.url).hostname);
  } catch (e) { out.dns = ''; }

  try {
    // ② HEAD：只看状态码（省流量）
    const head = await fetchWithTimeout(src.url, { method: 'HEAD' }, timeout);
    out.status = head.status;
    out.final_url = head.url || src.url;
    if (!head.ok) {
      out.detail = 'HEAD 返回 HTTP ' + head.status;
      return out;
    }
    // ③ GET：HEAD 没有正文，识别不了拦截页 → 必须抓正文看关键字
    const get = await fetchWithTimeout(src.url, { method: 'GET' }, timeout);
    out.status = get.status;
    out.final_url = get.url || out.final_url;
    if (!get.ok) {
      out.detail = 'GET 返回 HTTP ' + get.status;
      return out;
    }
    const body = (await get.text()).slice(0, 200000);
    const blocks = [];
    BLOCK_PATTERNS.forEach(function (re) {
      const m = body.match(re);
      if (m && blocks.indexOf(m[0]) < 0) blocks.push(m[0]);
    });
    if (blocks.length) {
      out.detail = '命中拦截/故障页特征：' + blocks.slice(0, 3).join('、');
      return out;
    }
    if (src.kind === 'keyword') {
      const hit = (SITE_PATTERNS[src.id] || []).some(function (re) { return re.test(body); });
      if (!hit) {
        out.detail = '页面没有该站特征关键字（疑似跳转到别处/错误页）';
        return out;
      }
      out.ok = true;
      out.detail = 'HEAD/GET 200' + (out.dns ? ' · 解析 ' + out.dns : '') + ' · 关键字正常';
      return out;
    }
    // kind === 'dns'：只要 200 且不是拦截页就算通
    out.ok = true;
    out.detail = 'HEAD/GET 200' + (out.dns ? ' · 解析 ' + out.dns : '') +
                 '（未做关键字强制校验）';
    return out;
  } catch (e) {
    const msg = (e && e.name === 'AbortError') ? ('超时 > ' + Math.round(timeout / 1000) + 's')
                                              : (e && e.message ? e.message : String(e));
    out.detail = '请求失败：' + msg + (out.dns ? '' : '（域名可能无法解析）');
    return out;
  }
}

/* ---------------- 状态机：连续 2 次成功 enabled / 连续 2 次失败 hidden ---------------- */
function applyStreak(prev, result, policy) {
  const p = Object.assign({}, DEFAULT_POLICY, policy || {});
  const st = Object.assign({ state: 'hidden' }, prev || {});
  if (result && result.ok) {
    st.streak_ok = (Number(prev && prev.streak_ok) || 0) + 1;
    st.streak_fail = 0;
  } else {
    st.streak_fail = (Number(prev && prev.streak_fail) || 0) + 1;
    st.streak_ok = 0;
  }
  st.checked_at = new Date().toISOString().slice(0, 10);
  st.detail = (result && result.detail) || '';
  if (st.streak_ok >= p.promote_after_ok) {
    st.state = 'enabled';                       // 连续 2 次成功 → 自动展示
  } else if (st.streak_fail >= p.demote_after_fail) {
    st.state = 'hidden';                        // 连续 2 次失败 → 回到隐藏
  }                                           // 未达阈值：保持原 state（观察中）
  return st;
}

/* ---------------- 状态文件读写 ---------------- */
function loadStatus() {
  try {
    return JSON.parse(fs.readFileSync(STATUS_FILE, 'utf8'));
  } catch (e) {
    return { generated: '', policy: DEFAULT_POLICY, sources: {} };
  }
}

function saveStatus(status) {
  status.generated = new Date().toISOString().slice(0, 10);
  fs.writeFileSync(STATUS_FILE, JSON.stringify(status, null, 1) + '\n', 'utf8');
  return STATUS_FILE;
}

/* ---------------- CLI ---------------- */
function parseArgs(argv) {
  const out = { dryRun: false, quiet: false, commit: false, push: false,
                only: '', timeout: 12000, help: false };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--dry-run') out.dryRun = true;
    else if (a === '--quiet' || a === '-q') out.quiet = true;
    else if (a === '--commit') out.commit = true;
    else if (a === '--push') { out.commit = true; out.push = true; }
    else if (a === '--only') out.only = argv[++i] || '';
    else if (a === '--timeout') out.timeout = (parseInt(argv[++i], 10) || 12) * 1000;
    else if (a === '-h' || a === '--help') out.help = true;
  }
  return out;
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (args.help) {
    console.log('用法：node deploy/dict_links_probe.js [--dry-run] [--quiet] [--only <id>] ' +
                '[--timeout <秒>] [--commit] [--push]');
    console.log('可探活的源：' + PROBED.map(function (s) { return s.id; }).join(' / '));
    return 0;
  }
  const status = loadStatus();
  status.policy = Object.assign({}, DEFAULT_POLICY, status.policy || {});
  status.sources = status.sources || {};

  const targets = PROBED.filter(function (s) { return !args.only || s.id === args.only; });
  if (!targets.length) {
    console.error('❌ --only 没有匹配的源：' + args.only +
                  '（可选：' + PROBED.map(function (s) { return s.id; }).join(' / ') + '）');
    return 2;
  }

  const results = [];
  for (const src of targets) {                 // 串行：这两站又慢又不稳，别并发
    const r = await probeOne(src, { timeout: args.timeout });
    results.push(r);
    const st = applyStreak(status.sources[src.id] || {}, r, status.policy);
    st.label = src.label;
    st.why = src.why;
    status.sources[src.id] = st;
  }

  if (args.quiet) {
    console.log(results.map(function (r) {
      return r.id + '=' + (r.ok ? 'ok' : 'fail') + '/' + status.sources[r.id].state;
    }).join(' '));
  } else {
    console.log('站外词典探活（' + new Date().toISOString().slice(0, 16).replace('T', ' ') + '）');
    results.forEach(function (r) {
      const st = status.sources[r.id];
      console.log('  ' + (r.ok ? '✅' : '❌') + ' ' + r.label + '（' + r.id + '）' +
                  '｜HTTP ' + (r.status || '-') + '｜state=' + st.state +
                  '｜连续成功 ' + st.streak_ok + ' 次 / 连续失败 ' + st.streak_fail + ' 次');
      console.log('      ' + r.detail);
    });
    console.log('  规则：连续 ' + status.policy.promote_after_ok + ' 次成功 → enabled（自动展示）；' +
                '连续 ' + status.policy.demote_after_fail + ' 次失败 → hidden');
  }

  if (args.dryRun) {
    if (!args.quiet) console.log('（--dry-run：未写文件）');
    return 0;
  }

  saveStatus(status);
  const rel = path.relative(ROOT, STATUS_FILE);
  if (!args.quiet) console.log('→ 已写 ' + rel);

  if (args.commit) {
    try {
      const dirty = execFileSync('git', ['status', '--porcelain', '--', rel], { cwd: ROOT })
        .toString().trim();
      if (!dirty) {
        if (!args.quiet) console.log('→ 状态无变化，跳过提交');
      } else {
        execFileSync('git', ['add', '--', rel], { cwd: ROOT });
        execFileSync('git', ['commit', '-m', '词典探活：更新 dict_links.json（' + status.generated + '）'],
                     { cwd: ROOT, stdio: args.quiet ? 'ignore' : 'inherit' });
        if (!args.quiet) console.log('→ 已提交');
      }
    } catch (e) {
      console.error('⚠️ 自动提交失败（可手动提交）：' + (e && e.message));
    }
  }

  if (args.push) {
    try {
      execFileSync('git', ['push'], { cwd: ROOT, stdio: args.quiet ? 'ignore' : 'inherit' });
      if (!args.quiet) console.log('→ 已推送（push 会自动触发 Cloudflare 构建）');
    } catch (e) {
      console.error('⚠️ 推送失败：' + (e && e.message));
    }
  }
  return 0;
}

module.exports = {
  probeOne: probeOne, applyStreak: applyStreak, parseArgs: parseArgs,
  loadStatus: loadStatus, saveStatus: saveStatus,
  fetchWithTimeout: fetchWithTimeout, dnsCheck: dnsCheck,
  PROBED: PROBED, BLOCK_PATTERNS: BLOCK_PATTERNS, SITE_PATTERNS: SITE_PATTERNS,
  DEFAULT_POLICY: DEFAULT_POLICY, STATUS_FILE: STATUS_FILE, main: main
};

if (require.main === module) {
  main().then(function (code) { process.exit(code || 0); })
        .catch(function (e) { console.error('探活脚本异常：' + (e && e.message)); process.exit(1); });
}
