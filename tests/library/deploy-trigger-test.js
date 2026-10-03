/* ============================================================
   CF 构建触发脚本 · 回归测试（不联网）
   ------------------------------------------------------------
   跑法：node tests/library/deploy-trigger-test.js
   验证 deploy/trigger_build.sh 的关键契约：
     1) --dry-run + CF_DEPLOY_HOOK → 只打印将 POST 的钩子（不发请求）
     2) 未知参数 → 退出码 2 + 明确提示
     3) 没有任何凭据时**不报错**（退出 0，给三种办法的提示）——流水线里不能因此中断
     4) --list 无凭据时同样安全退出
   ============================================================ */
'use strict';

const path = require('path');
const { execFileSync } = require('child_process');

const ROOT = path.resolve(__dirname, '..', '..');
const SCRIPT = path.join(ROOT, 'deploy', 'trigger_build.sh');

let pass = 0;
const failed = [];
function ok(cond, name, detail) {
  if (cond) { pass++; console.log('  ✅ ' + name); }
  else { failed.push(name + (detail ? ' — ' + detail : '')); console.log('  ✗ ' + name + (detail ? ' — ' + detail : '')); }
}

function run(args, env) {
  const e = Object.assign({}, process.env, env || {});
  try {
    return { code: 0, out: execFileSync('bash', [SCRIPT].concat(args),
      { env: e, encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] }) };
  } catch (err) {
    return { code: err.status == null ? -1 : err.status,
             out: String(err.stdout || '') + String(err.stderr || '') };
  }
}

const NO_CREDS = { HOME: '/tmp/__no_wrangler_home__', CF_DEPLOY_HOOK: '',
                   CF_API_TOKEN: '', CF_ACCOUNT_ID: '', CF_PAGES_PROJECT: '' };

console.log('deploy/trigger_build.sh');

// 1) 部署钩子分支
let r = run(['--dry-run'], { CF_DEPLOY_HOOK: 'https://example.com/hook' });
ok(r.code === 0 && r.out.indexOf('[dry-run] 将 POST https://example.com/hook') !== -1,
   '--dry-run + 部署钩子 → 只打印不请求', r.out.trim().slice(0, 60));

// 2) 未知参数
r = run(['--oops'], NO_CREDS);
ok(r.code === 2 && r.out.indexOf('未知参数') !== -1, '未知参数 → 退出码 2 + 提示', r.out.trim().slice(0, 60));

// 3) 无凭据也能安全退出（流水线不中断）
r = run(['--dry-run'], NO_CREDS);
ok(r.code === 0, '无凭据时退出码 0（不阻断流水线）', 'code=' + r.code);
ok(r.out.indexOf('未找到 Cloudflare 凭据') !== -1 || r.out.indexOf('将 POST') !== -1,
   '无凭据时给出友好提示', r.out.trim().slice(0, 60));

// 4) --list 同样安全（无凭据时不崩）
r = run(['--list'], NO_CREDS);
ok(r.code === 0, '--list 无凭据时也不崩', 'code=' + r.code);

console.log('\n结果：' + pass + ' 通过 / ' + failed.length + ' 失败');
if (failed.length) failed.forEach(f => console.log('   ✗ ' + f));
process.exit(failed.length ? 1 : 0);
