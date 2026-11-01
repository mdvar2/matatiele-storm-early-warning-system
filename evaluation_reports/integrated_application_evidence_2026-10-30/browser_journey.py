"""Drive the complete local application in a real (headless) browser and capture screenshots.

Development outbox mode only: no SMS is sent. Usage:
  python journey.py OUT_DIR BASE_URL ADMIN_PASSWORD THEME WARN_CMD
WARN_CMD is a shell command that runs the worker's subscriber hook once (outbox) between steps.
"""
import asyncio, base64, json, os, re, shutil, subprocess, sys, tempfile, time, urllib.request
import websockets

CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
OUT, BASE, PASSWORD, THEME, WARN_CMD = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5]
PHONE = '082 123 4567'
log = {}


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
        """Real mouse click (CDP input events) at the centre of the element; Streamlit ignores synthetic clicks on some widgets."""
        box = await self.js(f"""(() => {{ const e = {element_js}; if (!e) return null; e.scrollIntoView({{block: 'center'}});
            const r = e.getBoundingClientRect(); return [r.x + r.width / 2, r.y + r.height / 2]; }})()""")
        if not box:
            return False
        for kind in ('mousePressed', 'mouseReleased'):
            await self.send('Input.dispatchMouseEvent', type=kind, x=box[0], y=box[1], button='left', clickCount=1)
        return True

    async def click(self, label, role='button'):
        selector = '[role=tab]' if role == 'tab' else 'button'
        ok = await self.press(f"[...document.querySelectorAll('{selector}')].find(e => e.innerText.trim().endsWith({json.dumps(label)}) && !e.disabled && e.offsetParent)")
        await asyncio.sleep(3)
        return ok

    async def fill(self, label, value, last=False):
        pick = 'all[all.length - 1]' if last else 'all[0]'
        element = f"(() => {{ const all = [...document.querySelectorAll('input[aria-label={json.dumps(label)}]')].filter(e => e.offsetParent); return {pick}; }})()"
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

    async def shot(self, name, width, height, full=True):
        await self.send('Emulation.setDeviceMetricsOverride', width=width, height=height, deviceScaleFactor=1, mobile=width < 600)
        await asyncio.sleep(2.5)
        await self.js('window.scrollTo(0, 0)')
        d = (await self.send('Page.captureScreenshot', format='png', captureBeyondViewport=full))['data']
        open(os.path.join(OUT, f'{THEME}_{name}.png'), 'wb').write(base64.b64decode(d))


async def session(width, height, steps):
    prof = tempfile.mkdtemp(prefix='journey-'); port = 9700 + (width % 97)
    proc = subprocess.Popen([CHROME, '--headless=new', f'--remote-debugging-port={port}', f'--user-data-dir={prof}', '--no-first-run',
                             f'--window-size={width},{height}', 'about:blank'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(40):
            try: targets = json.load(urllib.request.urlopen(f'http://127.0.0.1:{port}/json/list', timeout=2)); break
            except Exception: time.sleep(.5)
        url = next(t['webSocketDebuggerUrl'] for t in targets if t['type'] == 'page')
        async with websockets.connect(url, max_size=None) as ws:
            page = Page(ws); task = asyncio.create_task(page.reader())
            await page.send('Page.enable'); await page.send('Runtime.enable')
            await page.send('Emulation.setEmulatedMedia', features=[{'name': 'prefers-color-scheme', 'value': THEME}])
            await page.send('Emulation.setDeviceMetricsOverride', width=width, height=height, deviceScaleFactor=1, mobile=width < 600)
            await steps(page)
            task.cancel()
    finally:
        proc.kill(); proc.wait(); shutil.rmtree(prof, ignore_errors=True)


async def desktop(page):
    await page.send('Page.navigate', url=BASE + '/?admin=1')
    log['dashboard_loaded'] = await page.wait('(model estimate)')
    await page.shot('01_dashboard', 1440, 2300)
    log['hero_subtitle'] = 'Is a storm likely in Matatiele in the next hour' in await page.text()
    await page.click('SMS Alerts'); log['sms_page'] = await page.wait('DEVELOPMENT MODE')
    await page.shot('02_sms_subscribe_form', 1440, 1500)
    await page.fill('South African mobile number', PHONE)
    log['consent_ticked'] = await page.tick('I agree to receive SMS storm warnings')
    await page.click('Send verification code')
    log['code_screen'] = await page.wait('We sent a 6-digit code to +27 82 *** **67')
    await page.shot('03_sms_enter_code', 1440, 1500)
    code = re.findall(r'code is (\d{6})', await page.text())
    log['code_found_in_dev_outbox'] = bool(code)
    await page.fill('Verification code', code[0])
    await page.click('Verify and activate')
    log['subscription_active'] = await page.wait('Your subscription is active')
    await page.shot('04_sms_active', 1440, 1500)
    # A genuine-format warning decision above 35%, delivered by the worker's subscriber hook to the local outbox.
    hook = subprocess.run(WARN_CMD, shell=True, capture_output=True, text=True)
    log['worker_hook'] = (hook.stdout.strip() or hook.stderr.strip()[-400:])
    # Administrator: sign in and open Administration.
    await page.js("""(() => { const s = [...document.querySelectorAll('summary')].find(e => e.innerText.includes('Administrator Access')); s && s.click(); })()""")
    await asyncio.sleep(2)
    await page.fill('Administrator Password', PASSWORD)
    await page.click('Unlock Admin Controls')
    log['admin_signed_in'] = await page.wait('Administrator access enabled')
    await page.click('Administration'); log['admin_page'] = await page.wait('Active subscribers')
    await page.click('Refresh delivery statuses')
    await page.shot('05_admin_monitoring', 1440, 2400)
    admin_text = await page.text()
    # The deliveries table is a canvas dataframe (masked values visible in the screenshot); assert the full number never appears as text.
    log['admin_full_number_absent'] = not re.search(r'0?82\s?123\s?4567|\+?27821234567', admin_text)
    # Manage subscription: ownership code (after the 60-second resend limit), then unsubscribe.
    await page.click('SMS Alerts'); await page.wait('Manage my subscription')
    await page.click('Manage my subscription', role='tab')
    await asyncio.sleep(62)
    await page.fill('Your registered mobile number', PHONE)
    await page.click('Send code')
    log['manage_code_sent'] = await page.wait('If this number is registered, we sent it a 6-digit code')
    code = re.findall(r'code is (\d{6})', await page.text())
    await page.fill('Verification code', code[0], last=True)
    await page.click('Confirm')
    log['manage_status_shown'] = await page.wait('I want to stop receiving SMS storm warnings')
    await page.shot('06_manage_status', 1440, 1600)
    await page.tick('I want to stop receiving SMS storm warnings')
    await page.click('Unsubscribe')
    log['unsubscribed'] = await page.wait('Unsubscribed')
    await page.shot('07_unsubscribed', 1440, 1600)
    await page.click('Warning History'); log['history_page'] = await page.wait('Storm warnings issued')
    await page.shot('08_warning_history', 1440, 1200)
    await page.click('Safety Advice'); await page.wait('Act now')
    await page.shot('09_safety_advice', 1440, 1800)


async def mobile(page):
    await page.send('Page.navigate', url=BASE + '/')
    log['mobile_loaded'] = await page.wait('(model estimate)')
    await page.shot('10_mobile_dashboard', 390, 2600)
    await page.js("""(() => { const b = [...document.querySelectorAll('.st-key-mobile_nav button')].find(e => e.innerText.includes('SMS Alerts')); b && b.click(); })()""")
    log['mobile_sms_page'] = await page.wait('Manage my subscription')
    await page.shot('11_mobile_sms_alerts', 390, 1700)
    await page.send('Page.navigate', url=BASE + '/?view=text')
    await page.wait('Safety advice')
    await page.shot('12_mobile_text_view', 390, 1400)


async def main():
    await session(1440, 1000, desktop)
    await session(390, 900, mobile)
    json.dump(log, open(os.path.join(OUT, f'journey_{THEME}.json'), 'w'), indent=1)
    print(json.dumps(log, indent=1))

asyncio.run(main())
