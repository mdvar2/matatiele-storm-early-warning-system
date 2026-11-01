"""Final resident walkthrough in a real (headless) browser, with a server restart mid-journey.

Development outbox mode only: no SMS is sent. Run from the app directory with the demo environment loaded:
  python journey_final.py OUT_DIR ADMIN_PASSWORD THEME
Journey: open dashboard -> check risk -> weather map -> register (number + consent) -> code sent ->
SERVER RESTART -> enter code -> active -> eligible warning delivered (worker hook, test probability) ->
manage: status -> unsubscribe -> warning history -> administrator monitoring -> mobile layout.
"""
import asyncio, base64, json, os, re, shutil, subprocess, sys, tempfile, time, urllib.request
import websockets

CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
OUT, PASSWORD, THEME = sys.argv[1], sys.argv[2], sys.argv[3]
PORT, PHONE = 8599, '082 123 4567'
BASE = f'http://127.0.0.1:{PORT}'
log, server = {}, {}


def start_server():
    env = {k: v for k, v in os.environ.items() if not k.startswith(('TWILIO_', 'ALERT_TO', 'GH_TOKEN', 'GITHUB_TOKEN'))}
    env.update(ADMIN_PASSWORD=PASSWORD, PYTHONDONTWRITEBYTECODE='1')
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


def stop_server():
    server['proc'].terminate()
    try:
        server['proc'].wait(15)
    except subprocess.TimeoutExpired:
        server['proc'].kill(); server['proc'].wait()


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

    async def wait(self, needle, timeout=120):
        end = time.time() + timeout
        while time.time() < end:
            if needle in await self.text():
                return True
            await asyncio.sleep(1)
        return False

    async def press(self, element_js):
        """Real mouse click (CDP input events) at the element's centre."""
        box = await self.js(f"""(() => {{ const e = {element_js}; if (!e) return null; e.scrollIntoView({{block: 'center'}});
            const r = e.getBoundingClientRect(); return [r.x + r.width / 2, r.y + r.height / 2]; }})()""")
        if not box:
            return False
        for kind in ('mousePressed', 'mouseReleased'):
            await self.send('Input.dispatchMouseEvent', type=kind, x=box[0], y=box[1], button='left', clickCount=1)
        return True

    async def click(self, label, selector='button'):
        ok = await self.press(f"[...document.querySelectorAll('{selector}')].find(e => e.innerText.trim().endsWith({json.dumps(label)}) && !e.disabled && e.offsetParent)")
        await asyncio.sleep(3)
        return ok

    async def fill(self, label, value):
        element = f"[...document.querySelectorAll('input[aria-label={json.dumps(label)}]')].filter(e => e.offsetParent).pop()"
        ok = await self.press(element)
        if ok:
            await self.js(f"{element}.select()")
            await self.send('Input.insertText', text=value)
        await asyncio.sleep(1.5)
        return ok

    async def tick(self, label_start):
        await self.press(f"[...document.querySelectorAll('[data-testid=stCheckbox]')].find(e => e.innerText.trim().startsWith({json.dumps(label_start)}) && e.offsetParent)?.querySelector('label')")
        await asyncio.sleep(2)
        return await self.js(f"!![...document.querySelectorAll('[data-testid=stCheckbox]')].find(e => e.innerText.trim().startsWith({json.dumps(label_start)}))?.querySelector('input')?.checked")

    async def shot(self, name, width, height):
        await self.send('Emulation.setDeviceMetricsOverride', width=width, height=height, deviceScaleFactor=1, mobile=width < 600)
        await asyncio.sleep(2.5)
        data = (await self.send('Page.captureScreenshot', format='png', captureBeyondViewport=True))['data']
        open(os.path.join(OUT, f'{THEME}_{name}.png'), 'wb').write(base64.b64decode(data))
        await self.send('Emulation.setDeviceMetricsOverride', width=width, height=900 if width >= 600 else 800, deviceScaleFactor=1, mobile=width < 600)

    async def open(self, query=''):
        await self.send('Page.navigate', url=BASE + '/' + query)
        return await self.wait('(model estimate)')


async def browser(width, steps):
    prof = tempfile.mkdtemp(prefix='journey-'); port = 9700 + (width % 97)
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
        proc.kill(); proc.wait(); shutil.rmtree(prof, ignore_errors=True)


def codes():
    path = os.environ['SMS_OUTBOX_PATH']
    rows = [json.loads(line) for line in open(path, encoding='utf-8')] if os.path.exists(path) else []
    return [re.search(r'code is (\d{6})', r['body']).group(1) for r in rows if r['kind'] == 'verification'], rows


async def desktop(page):
    log['1_dashboard_loaded'] = await page.open('?admin=1')
    text = await page.text()
    log['1_current_risk_shown'] = 'storm risk (model estimate)' in text and 'chance of a storm' in text
    log['1_weather_tile_shown'] = 'Weather · next hour (forecast)' in text and 'not an observation' in text
    log['1_sms_button_visible'] = 'Get free SMS storm warnings' in text
    await page.shot('01_homepage', 1440, 2400)
    await page.click('Weather Map'); log['2_weather_map'] = await page.wait('Rainfall forecast map')
    await asyncio.sleep(6); await page.shot('02_weather_map', 1440, 1400)
    await page.click('Dashboard'); await page.wait('Get free SMS storm warnings')
    await page.click('Get free SMS storm warnings'); log['3_sms_page_from_homepage_button'] = await page.wait('Manage my subscription')
    await page.fill('South African mobile number', PHONE)
    log['3_consent_ticked'] = await page.tick('I agree to receive SMS storm warnings')
    await page.shot('03_registration_form', 1440, 1500)
    await page.click('Send verification code')
    log['4_code_sent'] = await page.wait('We sent a 6-digit code to +27 82 *** **67')
    await page.shot('04_verification_code_sent', 1440, 1500)
    server['code_sent_at'] = time.time()
    # Restart the application between receiving the code and entering it.
    stop_server(); start_server()
    log['5_server_restarted'] = True
    await page.open('?admin=1')
    await page.click('SMS Alerts'); await page.wait('Already received a code?')
    log['5_session_was_reset'] = 'We sent a 6-digit code' not in await page.text()
    await page.press("[...document.querySelectorAll('summary')].find(e => e.innerText.includes('Already received a code?'))"); await asyncio.sleep(2)
    await page.fill('Mobile number you registered', PHONE)
    await page.fill('Code from the SMS', codes()[0][-1])
    await page.click('Verify and activate', selector='[data-testid=stExpanderDetails] button')
    log['5_active_after_restart'] = await page.wait('Your subscription is active')
    await page.shot('05_verified_active_after_restart', 1440, 1500)
    # An eligible warning reaches the active subscriber (worker hook; test probability, not a forecast).
    hook = subprocess.run([sys.executable, '-c', "import os, subscriber_alerts as a, pandas as pd; "
                           "h=(pd.Timestamp.now(tz='UTC').floor('h')+pd.Timedelta(hours=1)).isoformat(); "
                           "print(a.run_for_worker(h, .62, .35, dict(os.environ, SUBSCRIBER_ALERTS_ENABLED='true')))"],
                          capture_output=True, text=True)
    log['6_warning_hook'] = hook.stdout.strip() or hook.stderr.strip()[-300:]
    log['6_warning_in_outbox'] = any(r['kind'] == 'warning' and r['to'] == '+27 82 *** **67' for r in codes()[1])
    # Manage: ownership code (after the 60-second resend limit), status, unsubscribe.
    await page.click('Manage my subscription', selector='[role=tab]')
    await asyncio.sleep(max(0, 63 - (time.time() - server['code_sent_at'])))
    await page.fill('Your registered mobile number', PHONE)
    await page.click('Send code')
    log['7_manage_code_sent'] = await page.wait('If this number is registered, we sent it a 6-digit code')
    await page.fill('Verification code', codes()[0][-1])
    await page.click('Confirm')
    log['7_status_active'] = await page.wait('I want to stop receiving SMS storm warnings')
    await page.shot('06_subscriber_status', 1440, 1700)
    await page.tick('I want to stop receiving SMS storm warnings')
    await page.click('Unsubscribe')
    log['8_unsubscribed'] = await page.wait('You have been unsubscribed')
    await page.shot('07_unsubscribed', 1440, 1700)
    hook = subprocess.run([sys.executable, '-c', "import os, subscriber_alerts as a, pandas as pd; "
                           "h=(pd.Timestamp.now(tz='UTC').floor('h')+pd.Timedelta(hours=2)).isoformat(); "
                           "print(a.run_for_worker(h, .62, .35, dict(os.environ, SUBSCRIBER_ALERTS_ENABLED='true')))"],
                          capture_output=True, text=True)
    log['8_next_warning_after_unsubscribe'] = hook.stdout.strip()
    await page.click('Warning History'); log['9_history_page'] = await page.wait('Storm warnings issued')
    await page.shot('08_warning_history', 1440, 1100)
    await page.press("[...document.querySelectorAll('summary')].find(e => e.innerText.includes('Administrator Access'))"); await asyncio.sleep(2)
    await page.fill('Administrator Password', PASSWORD)
    await page.click('Unlock Admin Controls')
    log['10_admin_signed_in'] = await page.wait('Administrator access enabled')
    await page.click('Administration'); log['10_admin_page'] = await page.wait('Active subscribers')
    admin_text = await page.text()
    log['10_admin_full_number_absent'] = not re.search(r'0?82\s?123\s?4567|\+?27821234567', admin_text)
    await page.shot('09_administrator', 1440, 2400)


async def mobile(page):
    log['11_mobile_loaded'] = await page.open()
    await page.shot('10_mobile_homepage', 390, 2300)
    await page.press("[...document.querySelectorAll('.st-key-mobile_nav button')].find(e => e.innerText.includes('SMS Alerts'))")
    log['11_mobile_sms_page'] = await page.wait('Manage my subscription')
    await page.shot('11_mobile_sms_alerts', 390, 1700)


async def main():
    start_server()
    try:
        await browser(1440, desktop)
        await browser(390, mobile)
    finally:
        stop_server()
    json.dump(log, open(os.path.join(OUT, f'journey_{THEME}.json'), 'w'), indent=1)
    print(json.dumps(log, indent=1))

asyncio.run(main())
