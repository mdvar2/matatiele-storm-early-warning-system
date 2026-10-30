"""Measure layout boxes of the local app at phone width (390 px). Usage: python layout_probe.py URL [EXTRA_CSS]"""
import asyncio, json, shutil, subprocess, sys, tempfile, time, urllib.request
import websockets

CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'


async def main(url, extra_css):
    prof = tempfile.mkdtemp(); port = 9578
    p = subprocess.Popen([CHROME, '--headless=new', f'--remote-debugging-port={port}', f'--user-data-dir={prof}', 'about:blank'],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(40):
            try: t = json.load(urllib.request.urlopen(f'http://127.0.0.1:{port}/json/list', timeout=2)); break
            except Exception: time.sleep(.5)
        ws_url = next(x['webSocketDebuggerUrl'] for x in t if x['type'] == 'page'); n = 0
        async with websockets.connect(ws_url, max_size=None) as ws:
            async def send(m, **kw):
                nonlocal n; n += 1; await ws.send(json.dumps({'id': n, 'method': m, 'params': kw}))
                while True:
                    r = json.loads(await ws.recv())
                    if r.get('id') == n: return r.get('result', {})
            async def js(e): return (await send('Runtime.evaluate', expression=e, returnByValue=True)).get('result', {}).get('value')
            await send('Emulation.setDeviceMetricsOverride', width=390, height=900, deviceScaleFactor=1, mobile=True)
            await send('Page.navigate', url=url)
            for _ in range(150):
                if await js("document.body && document.body.innerText.includes('model estimate')"): break
                await asyncio.sleep(1)
            await asyncio.sleep(3)
            if extra_css:
                await js("(() => { const s = document.createElement('style'); s.textContent = %s; document.head.appendChild(s); })()" % json.dumps(extra_css))
                await asyncio.sleep(2)
            rects = await js("""JSON.stringify(['stSidebar','stAppViewContainer','stMain','stMainBlockContainer'].map(id => {
                const e = document.querySelector('[data-testid=' + id + ']'); if (!e) return [id, null];
                const r = e.getBoundingClientRect(), c = getComputedStyle(e);
                return [id, 'left=' + Math.round(r.left), 'w=' + Math.round(r.width), c.position, 'minW=' + c.minWidth, c.display]; }))""")
            print('RECTS', rects)
            print('docWidth', await js('document.documentElement.scrollWidth'), 'viewport', await js('window.innerWidth'))
    finally:
        p.kill(); p.wait(); shutil.rmtree(prof, ignore_errors=True)

asyncio.run(main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else ''))
