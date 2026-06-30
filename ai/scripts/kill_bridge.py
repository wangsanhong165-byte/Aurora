import psutil, os, signal, sys
for p in psutil.process_iter(['pid', 'name', 'cmdline']):
    try:
        cmdline = p.info.get('cmdline')
        if not cmdline: continue
        cmd = ' '.join(cmdline)
        if 'uvicorn' in cmd.lower() or ('server.py' in cmd and '9528' in cmd):
            print(f'Killing PID {p.info["pid"]}: {cmd[:120]}')
            p.kill()
    except Exception as e:
        print(f'Error: {e}')
print('done')