"""UI walkthrough: every page at desktop / tablet / mobile in a chosen theme, the theme switch and its persistence,
and the officials' portal. Development outbox mode only (nothing is sent).
  python ui_shots.py OUT_DIR BASE_URL THEME OFFICIAL_PASSWORD
"""
import asyncio, base64, json, os, shutil, subprocess, sys, tempfile, time, urllib.request
import websockets

CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
OUT, BASE, THEME, OFFICIAL_PW = sys.argv[1:5]
log = {}


class Browser:
    def __init__(self, width):
        self.width, self.mobile = width, width < 600

    async def __aenter__(self):
        self.prof = tempfile.mkdtemp(); port = 9500 + self.width % 90
        self.proc = subprocess.Popen([CHROME, '--headless=new', f'--remote-debugging-port={port}', f'--user-data-dir={self.prof}',
                                      f'--window-size={self.width},900', 'about:blank'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(40):
            try: t = json.load(urllib.request.urlopen(f'http://127.0.0.1:{port}/json/list', timeout=2)); break
            except Exception: time.sleep(.5)
        self.ws = await websockets.connect(next(x['webSocketDebuggerUrl'] for x in t if x['type'] == 'page'), max_size=None)
        self.n = 0
        await self.metrics(900 if not self.mobile else 800)
        return self

    async def __aexit__(self, *exc):
        await self.ws.close(); self.proc.kill(); self.proc.wait(); shutil.rmtree(self.prof, ignore_errors=True)

    async def send(self, m, **kw):
        self.n += 1; await self.ws.send(json.dumps({'id': self.n, 'method': m, 'params': kw}))
        while True:
            r = json.loads(await self.ws.recv())
            if r.get('id') == self.n: return r.get('result', {})

    async def js(self, e):
        return (await self.send('Runtime.evaluate', expression=e, returnByValue=True)).get('result', {}).get('value')

    async def metrics(self, height):
        await self.send('Emulation.setDeviceMetricsOverride', width=self.width, height=height, deviceScaleFactor=1, mobile=self.mobile)

    async def press(self, sel):
        box = await self.js(f"(() => {{ const e = {sel}; if (!e) return null; e.scrollIntoView({{block:'center'}}); const r = e.getBoundingClientRect(); return [r.x + r.width/2, r.y + r.height/2]; }})()")
        if not box: return False
        for kind in ('mousePressed', 'mouseReleased'):
            await self.send('Input.dispatchMouseEvent', type=kind, x=box[0], y=box[1], button='left', clickCount=1)
        return True

    async def open(self, query=''):
        await self.send('Page.navigate', url=BASE + '/' + query)
        for _ in range(120):
            if await self.js("document.body && (document.body.innerText.includes('(model estimate)') || document.body.innerText.includes('Disaster-management'))"):
                break
            await asyncio.sleep(1)
        await asyncio.sleep(4)

    async def dark(self):
        return await self.js("[...document.querySelectorAll('style')].some(s => s.textContent.includes('@media all {'))")

    async def shot(self, name, height):
        await self.metrics(height); await asyncio.sleep(3); await self.js('window.scrollTo(0,0)')
        data = (await self.send('Page.captureScreenshot', format='png', captureBeyondViewport=True))['data']
        open(os.path.join(OUT, f'{THEME}_{self.width}_{name}.png'), 'wb').write(base64.b64decode(data))
        await self.metrics(900 if not self.mobile else 800)

    async def top(self, label):
        await self.press(f"[...document.querySelectorAll('.st-key-top_nav_bar button')].find(e => e.innerText.trim().endsWith('{label}'))")
        await asyncio.sleep(7)

    async def menu(self, label):
        await self.press("document.querySelector('[data-testid=stExpandSidebarButton]')"); await asyncio.sleep(2)
        await self.press(f"[...document.querySelectorAll('[data-testid=stSidebar] button')].find(e => e.innerText.trim().endsWith('{label}'))")
        await asyncio.sleep(6)
        if self.mobile:
            await self.press("document.querySelector('[data-testid=stSidebarCollapseButton] button, [data-testid=stSidebarCollapseButton]')"); await asyncio.sleep(2)


def overflow_js():
    return "document.documentElement.scrollWidth <= window.innerWidth + 1"


async def pages(width):
    async with Browser(width) as b:
        await b.open(f'?theme={THEME}')
        log[f'{width}_theme_applied'] = (await b.dark()) == (THEME == 'dark')
        log[f'{width}_no_horizontal_overflow_home'] = await b.js(overflow_js())
        await b.shot('01_home', 2600 if b.mobile else 1900)
        for label, name in (('Forecast', '02_forecast'), ('Map', '03_map'), ('Safety', '04_safety')):
            await b.top(label)
            log[f'{width}_{label}_overflow_ok'] = await b.js(overflow_js())
            if width != 820 or name == '03_map':
                await b.shot(name, 2400 if b.mobile else 1500)
        for label, name in (('Alerts', '05_alerts'), ('Risk Analysis', '06_risk'), ('Historical Data', '07_history'), ('About', '08_about')):
            await b.menu(label)
            log[f'{width}_{label}_theme_kept'] = (await b.dark()) == (THEME == 'dark')
            log[f'{width}_{label}_overflow_ok'] = await b.js(overflow_js())
            if width == 1440 or name in ('05_alerts', '08_about'):
                await b.shot(name, 2200 if b.mobile else 1400)


async def switch_and_persistence():
    """Click the real switch, change page, then reload WITHOUT ?theme: the browser remembers the choice."""
    async with Browser(1440) as b:
        await b.open('')
        start = await b.dark()
        await b.press("[...document.querySelectorAll('.st-key-header_tools [data-testid=stCheckbox] label')].pop()"); await asyncio.sleep(5)
        log['switch_changes_theme'] = (await b.dark()) != start
        log['switch_has_accessible_state'] = await b.js("(() => { const i = document.querySelector('.st-key-header_tools input[type=checkbox]'); return !!i && i.getAttribute('aria-checked') !== null || (i && typeof i.checked === 'boolean'); })()")
        await b.top('Forecast')
        log['theme_kept_after_navigation'] = (await b.dark()) != start
        await b.open('')  # plain reload, no ?theme in the link
        await asyncio.sleep(4)
        log['theme_kept_after_refresh_without_link'] = (await b.dark()) != start
        await b.shot('09_switch_after_refresh', 900)


async def portal():
    async with Browser(1440) as b:
        await b.open(f'?portal=officials&theme={THEME}')
        await b.press("[...document.querySelectorAll('input[aria-label=\"Official username\"]')].pop()")
        await b.send('Input.insertText', text='demo.official')
        await b.press("[...document.querySelectorAll('input[aria-label=\"Official password\"]')].pop()")
        await b.send('Input.insertText', text=OFFICIAL_PW)
        await b.press("[...document.querySelectorAll('button')].find(e => e.innerText.trim() === 'Sign in')"); await asyncio.sleep(6)
        log['portal_signed_in'] = 'Signed in as demo.official' in await b.js('document.body.innerText')
        log['portal_theme'] = (await b.dark()) == (THEME == 'dark')
        await b.shot('10_portal_active', 1200)
        await b.press("[...document.querySelectorAll('button')].find(e => e.innerText.trim().endsWith('History & actions'))"); await asyncio.sleep(5)
        await b.shot('11_portal_history', 1200)


async def warning_detail():
    async with Browser(390) as b:
        await b.open(f'?theme={THEME}')
        await b.menu('Alerts')
        await b.press("[...document.querySelectorAll('button')].find(e => e.innerText.trim() === 'View')"); await asyncio.sleep(6)
        log['mobile_warning_detail'] = 'Acknowledge this warning' in await b.js('document.body.innerText')
        log['mobile_call_buttons'] = await b.js("['10111','10177','112'].every(n => document.querySelector(`a[href='tel:${n}']`))")
        await b.shot('12_warning_detail', 2400)


async def main():
    for width in (1440, 820, 390):
        await pages(width)
    if THEME == 'light':
        await switch_and_persistence()
    r = subprocess.run([sys.executable, '24_create_dev_test_warning.py', '--hours-ahead', '1'], capture_output=True, text=True)
    log['test_warning'] = (r.stdout or r.stderr).strip()[-120:]
    await warning_detail()
    await portal()
    json.dump(log, open(os.path.join(OUT, f'ui_{THEME}.json'), 'w'), indent=1)
    print(json.dumps(log, indent=1))

asyncio.run(main())
