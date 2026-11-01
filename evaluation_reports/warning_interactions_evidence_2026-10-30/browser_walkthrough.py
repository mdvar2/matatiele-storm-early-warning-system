"""Browser walkthrough: resident warning interactions and the officials' portal (development outbox mode, nothing sent).

Run from the app directory with the demo environment loaded:
  python journey_warn.py OUT_DIR ADMIN_PASSWORD OFFICIAL_PASSWORD THEME
OFFICIAL_ACCOUNTS must hold an account 'demo.official' with OFFICIAL_PASSWORD. Two development test warnings
(one in effect, one past) are created first with 24_create_dev_test_warning.py and are labelled as tests.
"""
import asyncio, base64, json, os, shutil, subprocess, sys, tempfile, time, urllib.request
import websockets

CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
OUT, ADMIN_PW, OFFICIAL_PW, THEME = sys.argv[1:5]
PORT = 8599
BASE = f'http://127.0.0.1:{PORT}'
log, server = {}, {}


def start_server():
    env = {k: v for k, v in os.environ.items() if not k.startswith(('TWILIO_', 'ALERT_TO', 'GH_TOKEN', 'GITHUB_TOKEN'))}
    env.update(ADMIN_PASSWORD=ADMIN_PW, PYTHONDONTWRITEBYTECODE='1')
    handle = open(os.path.join(OUT, f'server_{THEME}.log'), 'a')
    server['proc'] = subprocess.Popen([sys.executable, '-m', 'streamlit', 'run', '16_dashboard.py', '--server.headless', 'true',
                                       '--server.port', str(PORT), '--browser.gatherUsageStats', 'false', '--server.fileWatcherType', 'none'],
                                      env=env, stdout=handle, stderr=subprocess.STDOUT)
    for _ in range(90):
        try:
            if urllib.request.urlopen(BASE + '/_stcore/health', timeout=2).status == 200:
                return
        except Exception:
            time.sleep(1)
    raise RuntimeError('server did not start')


class Page:
    def __init__(self, ws):
        self.ws, self.n, self.pending = ws, 0, {}

    async def reader(self):
        async for raw in self.ws:
            m = json.loads(raw)
            if 'id' in m and m['id'] in self.pending:
                self.pending.pop(m['id']).set_result(m)

    async def send(self, method, **params):
        self.n += 1; fut = asyncio.get_event_loop().create_future(); self.pending[self.n] = fut
        await self.ws.send(json.dumps({'id': self.n, 'method': method, 'params': params}))
        return (await asyncio.wait_for(fut, 90)).get('result', {})

    async def js(self, expression):
        r = await self.send('Runtime.evaluate', expression=expression, returnByValue=True, awaitPromise=True)
        return r.get('result', {}).get('value')

    async def text(self):
        return await self.js('document.body ? document.body.innerText : ""') or ''

    async def wait(self, needle, timeout=90):
        end = time.time() + timeout
        while time.time() < end:
            if needle in await self.text():
                return True
            await asyncio.sleep(1)
        return False

    async def press(self, element_js):
        box = await self.js(f"""(() => {{ const e = {element_js}; if (!e) return null; e.scrollIntoView({{block: 'center'}});
            const r = e.getBoundingClientRect(); return [r.x + r.width / 2, r.y + r.height / 2]; }})()""")
        if not box:
            return False
        for kind in ('mousePressed', 'mouseReleased'):
            await self.send('Input.dispatchMouseEvent', type=kind, x=box[0], y=box[1], button='left', clickCount=1)
        return True

    async def click(self, label, selector='button', wait=3):
        ok = await self.press(f"[...document.querySelectorAll('{selector}')].find(e => e.innerText.trim().endsWith({json.dumps(label)}) && !e.disabled && e.offsetParent)")
        await asyncio.sleep(wait)
        return ok

    async def fill(self, label, value, tag='input'):
        element = f"[...document.querySelectorAll('{tag}[aria-label={json.dumps(label)}]')].filter(e => e.offsetParent).pop()"
        ok = await self.press(element)
        if ok:
            await self.js(f"{element}.select()")
            await self.send('Input.insertText', text=value)
        await asyncio.sleep(1.5)
        return ok

    async def choose(self, label, option):
        """Open a select box by its label and pick an option."""
        box = f"[...document.querySelectorAll('[data-testid=stSelectbox]')].find(e => e.innerText.includes({json.dumps(label)}))"
        await self.press(f"{box}?.querySelector('input')")
        await asyncio.sleep(1)
        await self.send('Input.insertText', text=option)
        await asyncio.sleep(1)
        for kind in ('keyDown', 'keyUp'):
            await self.send('Input.dispatchKeyEvent', type=kind, key='Enter', code='Enter', windowsVirtualKeyCode=13)
        await asyncio.sleep(1.5)
        return await self.js(f"{box}?.innerText.includes({json.dumps(option)})")

    async def shot(self, name, width, height):
        await self.send('Emulation.setDeviceMetricsOverride', width=width, height=height, deviceScaleFactor=1, mobile=width < 600)
        await asyncio.sleep(3)
        data = (await self.send('Page.captureScreenshot', format='png', captureBeyondViewport=True))['data']
        open(os.path.join(OUT, f'{THEME}_{name}.png'), 'wb').write(base64.b64decode(data))
        await self.send('Emulation.setDeviceMetricsOverride', width=width, height=900 if width >= 600 else 800, deviceScaleFactor=1, mobile=width < 600)

    async def open(self, query=''):
        await self.send('Page.navigate', url=BASE + '/' + query)
        return await self.wait('(model estimate)' if 'portal' not in query else 'Disaster-management decision support')


async def browser(width, steps, profile=None):
    prof = profile or tempfile.mkdtemp(prefix='journey-'); port = 9700 + (width % 97)
    proc = subprocess.Popen([CHROME, '--headless=new', f'--remote-debugging-port={port}', f'--user-data-dir={prof}', '--no-first-run',
                             f'--window-size={width},900', 'about:blank'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(40):
            try: targets = json.load(urllib.request.urlopen(f'http://127.0.0.1:{port}/json/list', timeout=2)); break
            except Exception: time.sleep(.5)
        url = next(t['webSocketDebuggerUrl'] for t in targets if t['type'] == 'page')
        async with websockets.connect(url, max_size=None) as ws:
            page = Page(ws); task = asyncio.create_task(page.reader())
            await page.send('Page.enable'); await page.send('Runtime.enable')
            await page.send('Emulation.setEmulatedMedia', features=[{'name': 'prefers-color-scheme', 'value': THEME}])
            await page.send('Emulation.setDeviceMetricsOverride', width=width, height=900 if width >= 600 else 800, deviceScaleFactor=1, mobile=width < 600)
            await steps(page)
            task.cancel()
    finally:
        proc.kill(); proc.wait()
        if profile is None:
            shutil.rmtree(prof, ignore_errors=True)


async def resident(page):
    log['r1_home_loaded'] = await page.open()
    text = await page.text()
    log['r1_test_banner_not_real'] = 'NOT A REAL WARNING' in text and 'STORM WARNING IN EFFECT' not in text
    log['r1_contacts_tap_to_call'] = await page.js("['10111','10177','112'].every(n => document.querySelector(`a[href='tel:${n}']`))")
    log['r1_hourly_strip'] = 'Next hours' in text
    await page.shot('01_home', 1440, 2600)
    await page.click('Alerts'); log['r2_alerts_page'] = await page.wait('Past warnings')
    log['r2_contacts_on_alerts'] = await page.js("!!document.querySelector(\"a[href='tel:112']\")")
    await page.shot('02_alerts', 1440, 1500)
    await page.click('View', wait=4); log['r3_detail'] = await page.wait('I have read this warning')
    text = await page.text()
    log['r3_detail_parts'] = all(p in text for p in ('Matatiele town', 'Act now', 'DEVELOPMENT TEST', 'does not tell anyone that you are safe'))
    await page.shot('03_warning_detail', 1440, 1800)
    await page.click('I have read this warning', wait=4)
    log['r4_acknowledged'] = await page.wait('Your acknowledgement was recorded')
    await page.shot('04_acknowledged', 1440, 1800)
    # Reload (new session): the device identifier in this browser prevents a second acknowledgement.
    await page.open(); await page.click('Alerts'); await page.wait('Past warnings'); await page.click('View', wait=4)
    log['r5_duplicate_prevented_after_reload'] = await page.wait('You acknowledged this warning on', 40) and 'I have read this warning' not in await page.text()
    await page.shot('04b_after_reload', 1440, 1800)
    await page.click('SMS alerts'); log['r6_sms_view'] = await page.wait('South African mobile number')
    await page.shot('05_sms_alerts', 1440, 1500)


async def mobile(page):
    log['m1_loaded'] = await page.open()
    await page.shot('06_mobile_home', 390, 2900)
    await page.click('Alerts'); await page.wait('Past warnings'); await page.click('View', wait=4)
    log['m2_detail'] = await page.wait('Acknowledge this warning')
    await page.shot('07_mobile_warning', 390, 2400)


async def official(page):
    log['o1_portal'] = await page.open('?portal=officials')
    await page.shot('08_portal_sign_in', 1440, 900)
    await page.fill('Official username', 'demo.official'); await page.fill('Official password', OFFICIAL_PW)
    await page.click('Sign in', wait=5); log['o2_signed_in'] = await page.wait('Signed in as demo.official')
    text = await page.text()
    log['o2_ack_count_visible'] = '1 acknowledgements' in text
    await page.shot('09_portal_active', 1440, 1300)
    await page.click('Review', wait=4); log['o3_details'] = await page.wait('Record review')
    await page.choose('Review or response status', 'Monitoring')
    await page.fill('Operational note (optional)', 'Demonstration note: ward councillor informed by phone; monitoring river levels.', tag='textarea')
    await page.click('Record review', wait=4); log['o4_review_recorded'] = await page.wait('Review recorded.')
    await page.shot('10_portal_review', 1440, 1700)
    await page.click('Geographic risk', wait=6); log['o5_geography'] = await page.wait('Forecast rainfall for the')
    await page.shot('11_portal_geography', 1440, 1500)
    await page.click('History & actions', wait=4); log['o6_history'] = await page.wait('All operational actions')
    record = json.load(open(os.path.join('outputs', 'subscribers', 'operations.json'), encoding='utf-8'))
    log['o6_recorded_actions'] = [(a['official'], a['status'], a['note'][:40]) for a in record['actions']]
    log['o6_reviews'] = {k[-25:]: (v['status'], v['updated_by']) for k, v in record['reviews'].items()}
    log['o3_status_set_to_monitoring'] = any(v['status'] == 'Monitoring' for v in record['reviews'].values())
    log['o6_acknowledgement_counts'] = {k[-25:]: len(v) for k, v in record['acknowledgements'].items()}
    await page.shot('12_portal_history', 1440, 1300)


async def main():
    for hours, probability in (('1', '0.62'), ('-50', '0.48')):
        result = subprocess.run([sys.executable, '24_create_dev_test_warning.py', '--hours-ahead', hours, '--probability', probability],
                                capture_output=True, text=True)
        log[f'test_warning_{hours}'] = (result.stdout or result.stderr).strip()[-200:]
    start_server()
    try:
        await browser(1440, resident)
        await browser(390, mobile)
        await browser(1440, official)
    finally:
        server['proc'].terminate(); server['proc'].wait(20)
    json.dump(log, open(os.path.join(OUT, f'journey_{THEME}.json'), 'w'), indent=1)
    print(json.dumps(log, indent=1))

asyncio.run(main())
