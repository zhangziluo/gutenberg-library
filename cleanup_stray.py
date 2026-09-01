import os, subprocess, sys
sys.stdout.reconfigure(encoding='utf-8')
ROOT = '/Users/zhangziluo/Downloads/古登堡—在线阅读网站项目'
os.chdir(ROOT)
log = []

# 1) 删除杂散临时文件（已误提交的 tmp_insp*）
for f in ['tmp_insp3.txt', 'tmp_insp3_err.txt', 'tmp_insp4.txt']:
    p = os.path.join(ROOT, f)
    if os.path.exists(p):
        os.remove(p)
        log.append(f'removed {f}')
    else:
        log.append(f'absent {f}')
for f in ['_chk_state.py', '_state_out.txt']:
    p = os.path.join(ROOT, f)
    if os.path.exists(p):
        os.remove(p)
        log.append(f'removed {f}')

# 2) git 暂存 + 提交（若还有变更）
r = subprocess.run(['git', 'status', '--short'], capture_output=True, text=True)
log.append('status: ' + (r.stdout.strip() or '(clean)'))
if r.stdout.strip():
    subprocess.run(['git', 'add', '-A'], capture_output=True, text=True)
    c = subprocess.run(['git', 'commit', '-m', '清理临时调试文件'], capture_output=True, text=True)
    log.append('commit: ' + (c.stdout or c.stderr).strip())

# 3) 最终 git log
r = subprocess.run(['git', 'log', '--oneline', '-3'], capture_output=True, text=True)
log.append('log:\n' + r.stdout.strip())

with open(os.path.join(ROOT, '_cleanup_done.txt'), 'w', encoding='utf-8') as f:
    f.write('\n'.join(log))
