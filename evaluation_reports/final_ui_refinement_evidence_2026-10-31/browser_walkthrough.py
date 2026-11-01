"""Home, Forecast, Map, Risk Analysis and About at 1440 / 820 / 390 px in one theme, with map measurements.
  python affected_shots.py OUT_DIR BASE_URL THEME PREFIX
"""
import asyncio, base64, json, os, shutil, subprocess, sys, tempfile, time, urllib.request
import websockets

CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
OUT, BASE, THEME, PREFIX = sys.argv[1:5]
log = {}


async def run(width):
    prof = tempfile.mkdtemp(); port = 9330 + width % 60; mobile = width < 600; h = 800 if mobile else 900
    proc = subprocess.Popen([CHROME, '--headless=new', f'--remote-debugging-port={port}', f'--user-data-dir={prof}', f'--window-size={width},{h}', 'about:blank'],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(40):
            try: t = json.load(urllib.request.urlopen(f'http://127.0.0.1:{port}/json/list', timeout=2)); break
            except Exception: time.sleep(.5)
        n = 0
        async with websockets.connect(next(x['webSocketDebuggerUrl'] for x in t if x['type'] == 'page'), max_size=None) as ws:
            async def send(m, **kw):
                nonlocal n; n += 1; await ws.send(json.dumps({'id': n, 'method': m, 'params': kw}))
                while True:
                    r = json.loads(await ws.recv())
                    if r.get('id') == n: return r.get('result', {})
            async def js(e): return (await send('Runtime.evaluate', expression=e, returnByValue=True)).get('result', {}).get('value')
            async def press(sel):
                box = await js(f"(() => {{ const e = {sel}; if (!e) return null; e.scrollIntoView({{block:'center'}}); const r = e.getBoundingClientRect(); return [r.x + r.width/2, r.y + r.height/2]; }})()")
                if not box: return False
                for kind in ('mousePressed', 'mouseReleased'):
                    await send('Input.dispatchMouseEvent', type=kind, x=box[0], y=box[1], button='left', clickCount=1)
                return True
            async def shot(name):
                await js('window.scrollTo(0,0)'); await asyncio.sleep(1)
                full = await js('document.querySelector("[data-testid=stMain]").scrollHeight')
                await send('Emulation.setDeviceMetricsOverride', width=width, height=max(h, int(full or h)), deviceScaleFactor=1, mobile=mobile); await asyncio.sleep(3)
                data = (await send('Page.captureScreenshot', format='png', captureBeyondViewport=True))['data']
                open(os.path.join(OUT, f'{PREFIX}_{THEME}_{width}_{name}.png'), 'wb').write(base64.b64decode(data))
                await send('Emulation.setDeviceMetricsOverride', width=width, height=h, deviceScaleFactor=1, mobile=mobile); await asyncio.sleep(2)
            async def top(label):
                await press(f"[...document.querySelectorAll('.st-key-top_nav_bar button')].find(e => e.innerText.trim().endsWith('{label}'))"); await asyncio.sleep(8)
            async def menu(label):
                await press("document.querySelector('[data-testid=stExpandSidebarButton]')"); await asyncio.sleep(2)
                await press(f"[...document.querySelectorAll('[data-testid=stSidebar] button')].find(e => e.innerText.trim().endsWith('{label}'))"); await asyncio.sleep(6)
                await press("document.querySelector('[data-testid=stSidebarCollapseButton] button, [data-testid=stSidebarCollapseButton]')"); await asyncio.sleep(2)
            overflow = 'document.documentElement.scrollWidth <= window.innerWidth + 1'
            await send('Emulation.setDeviceMetricsOverride', width=width, height=h, deviceScaleFactor=1, mobile=mobile)
            await send('Page.navigate', url=f'{BASE}/?theme={THEME}')
            for _ in range(120):
                if await js("document.body && document.body.innerText.includes('(model estimate)')"): break
                await asyncio.sleep(1)
            await asyncio.sleep(3)
            log[f'{width}_home'] = {'no_overflow': await js(overflow), 'green_no_warning_card': await js("document.body.innerText.includes('NO WARNING IN EFFECT')")}
            await shot('home')
            await top('Forecast'); log[f'{width}_forecast_no_overflow'] = await js(overflow); await shot('forecast')
            await top('Map'); await js('window.scrollTo(0,0)')
            log[f'{width}_map'] = await js("""(() => { const m = document.querySelector('[data-testid=stDeckGlJsonChart]'); const r = m.getBoundingClientRect();
                return {map_top: Math.round(r.top + window.scrollY), map_height: Math.round(r.height),
                        map_visible_without_scrolling: Math.max(0, Math.round(Math.min(r.bottom, window.innerHeight) - Math.max(r.top, 0))),
                        no_overflow: document.documentElement.scrollWidth <= window.innerWidth + 1}; })()""")
            await shot('map')
            await menu('Risk Analysis'); log[f'{width}_risk_no_overflow'] = await js(overflow); await shot('risk')
            await menu('About'); log[f'{width}_about'] = {'no_overflow': await js(overflow),
                'officials_in_diagram': await js("!!document.querySelector('.flow') && document.querySelector('.flow').innerText.includes('Officials')")}
            await shot('about')
    finally:
        proc.kill(); proc.wait(); shutil.rmtree(prof, ignore_errors=True)


async def main():
    for width in (1440, 820, 390):
        await run(width)
    json.dump(log, open(os.path.join(OUT, f'{PREFIX}_{THEME}.json'), 'w'), indent=1)
    print(json.dumps(log))

asyncio.run(main())
