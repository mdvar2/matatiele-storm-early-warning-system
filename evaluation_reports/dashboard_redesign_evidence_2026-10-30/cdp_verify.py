"""Headless Chrome (DevTools protocol) measurement and screenshots of the local dashboard.

Each scenario uses a fresh Chrome profile (cold cache). Bytes counted:
  http_bytes = sum of Network.loadingFinished.encodedDataLength (wire bytes incl. headers)
  ws_bytes   = sum of WebSocket frame payloads received + sent (Streamlit's data channel)
External tile and CDN requests are included; nothing is filtered out.
Usage: python cdp_measure.py OUT_DIR BASE_URL ADMIN_PASSWORD
"""
import asyncio, base64, json, os, shutil, subprocess, sys, tempfile, time, urllib.request
import websockets

CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
OUT, BASE, PASSWORD = sys.argv[1], sys.argv[2], sys.argv[3]
THEME = sys.argv[4] if len(sys.argv) > 4 else 'light'


class Page:
    def __init__(self, ws):
        self.ws, self.n, self.pending, self.events = ws, 0, {}, []
        self.http, self.ws_bytes, self.requests, self.last = 0, 0, 0, time.time()

    async def reader(self):
        async for raw in self.ws:
            msg = json.loads(raw)
            if 'id' in msg and msg['id'] in self.pending:
                self.pending.pop(msg['id']).set_result(msg)
                continue
            method, p = msg.get('method'), msg.get('params', {})
            if method == 'Network.loadingFinished':
                self.http += int(p.get('encodedDataLength', 0)); self.requests += 1; self.last = time.time()
            elif method in ('Network.webSocketFrameReceived', 'Network.webSocketFrameSent'):
                r = p['response']; data = r.get('payloadData', '')
                self.ws_bytes += len(base64.b64decode(data)) if r.get('opcode') == 2 else len(data.encode())
                self.last = time.time()

    async def send(self, method, **params):
        self.n += 1
        fut = asyncio.get_event_loop().create_future(); self.pending[self.n] = fut
        await self.ws.send(json.dumps({'id': self.n, 'method': method, 'params': params}))
        return (await asyncio.wait_for(fut, 60)).get('result', {})

    async def js(self, expression):
        r = await self.send('Runtime.evaluate', expression=expression, awaitPromise=True, returnByValue=True)
        return r.get('result', {}).get('value')

    async def wait_text(self, text, timeout=150):
        end = time.time() + timeout
        while time.time() < end:
            if await self.js(f'document.body && document.body.innerText.includes({json.dumps(text)})'):
                return True
            await asyncio.sleep(1)
        return False

    async def idle(self, quiet=6, timeout=90):
        end = time.time() + timeout
        while time.time() < end and time.time() - self.last < quiet:
            await asyncio.sleep(1)

    async def shot(self, name, width, height):
        await self.send('Emulation.setDeviceMetricsOverride', width=width, height=height, deviceScaleFactor=1, mobile=width < 600)
        await asyncio.sleep(2)
        data = (await self.send('Page.captureScreenshot', format='png', captureBeyondViewport=True))['data']
        open(os.path.join(OUT, name), 'wb').write(base64.b64decode(data))


async def scenario(name, path, width, height, wait_for, admin=False):
    profile = tempfile.mkdtemp(prefix='cdp-'); port = 9400 + abs(hash(name)) % 400
    proc = subprocess.Popen([CHROME, '--headless=new', f'--remote-debugging-port={port}', f'--user-data-dir={profile}',
                             '--no-first-run', '--disable-extensions', '--disable-background-networking',
                             '--disable-component-update', '--disable-sync', f'--window-size={width},{height}', 'about:blank'],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(40):
            try:
                targets = json.load(urllib.request.urlopen(f'http://127.0.0.1:{port}/json/list', timeout=2)); break
            except Exception:
                time.sleep(0.5)
        url = next(t['webSocketDebuggerUrl'] for t in targets if t['type'] == 'page')
        async with websockets.connect(url, max_size=None) as ws:
            page = Page(ws); task = asyncio.create_task(page.reader())
            await page.send('Network.enable'); await page.send('Page.enable'); await page.send('Runtime.enable')
            await page.send('Network.setCacheDisabled', cacheDisabled=True)
            await page.send('Emulation.setEmulatedMedia', features=[{'name': 'prefers-color-scheme', 'value': THEME}])
            await page.send('Emulation.setDeviceMetricsOverride', width=width, height=height, deviceScaleFactor=1, mobile=width < 600)
            start = time.time()
            await page.send('Page.navigate', url=BASE + path)
            found = await page.wait_text(wait_for)
            await page.idle()
            result = {'scenario': name, 'url_path': path, 'content_found': found, 'seconds': round(time.time() - start, 1),
                      'http_requests': page.requests, 'http_bytes': page.http, 'websocket_bytes': page.ws_bytes,
                      'total_bytes': page.http + page.ws_bytes}
            await page.shot(f'{THEME}_{name}.png', width, height)
            result['public_admin_text_visible'] = await page.js("document.body.innerText.includes('Administrator')")
            if name == 'dashboard_desktop':
                await page.js("""(() => { const b = [...document.querySelectorAll('button')].find(e => e.innerText.trim().endsWith('Safety Advice')); b && b.click(); })()""")
                result['safety_page'] = await page.wait_text('Full advice for when a storm is close', 40)
                await asyncio.sleep(2)
                await page.shot(f'{THEME}_safety_advice.png', width, 1700)
            if admin:
                await page.js("""(() => { const s = [...document.querySelectorAll('summary')].find(e => e.innerText.includes('Administrator Access')); s && s.click(); return !!s; })()""")
                await asyncio.sleep(2)
                async def sign_in(value):
                    await page.js("""(() => { const i = document.querySelector('input[type=password]'); if (!i) return false;
                        const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
                        set.call(i, %s); i.dispatchEvent(new Event('input', {bubbles: true}));
                        i.dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter', bubbles: true})); return true; })()""" % json.dumps(value))
                    await asyncio.sleep(2)
                    await page.js("""(() => { const b = [...document.querySelectorAll('button')].find(e => e.innerText.includes('Unlock Admin Controls')); b && b.click(); })()""")
                await sign_in('wrong-password')
                result['wrong_password_rejected'] = await page.wait_text('Incorrect password.', 30)
                result['toggle_absent_after_wrong_password'] = await page.js("![...document.querySelectorAll('label')].some(e => e.innerText.includes('Warning simulation'))")
                await sign_in(PASSWORD)
                result['admin_signed_in'] = await page.wait_text('Administrator access enabled', 40)
                await page.js("""(() => { const l = [...document.querySelectorAll('label')].find(e => e.innerText.includes('Warning simulation')); if (!l) return false; (l.querySelector('input') || l).click(); return true; })()""")
                result['simulation_shown'] = await page.wait_text('SIMULATION - NOT A REAL FORECAST OR WARNING', 40)
                await asyncio.sleep(3)
                await page.shot(f'{THEME}_{name}_simulation.png', width, 2600)
                result['sms_preview_shown'] = await page.js("document.body.innerText.includes('It has NOT been sent')")
                await page.js("""(() => { const l = [...document.querySelectorAll('label')].find(e => e.innerText.includes('Warning simulation')); (l.querySelector('input') || l).click(); })()""")
                await asyncio.sleep(4)
                result['reverted_to_genuine'] = await page.js("!document.body.innerText.includes('SIMULATION - NOT A REAL FORECAST OR WARNING')")
                await page.shot(f'{THEME}_{name}_after_disable.png', width, 1400)
            task.cancel()
            return result
    finally:
        proc.kill(); proc.wait(); shutil.rmtree(profile, ignore_errors=True)


async def main():
    results = []
    results.append(await scenario('dashboard_desktop', '/', 1440, 2400, 'model estimate'))
    results.append(await scenario('text_view_mobile', '/?view=text', 390, 1600, 'Safety advice'))
    results.append(await scenario('dashboard_mobile', '/', 390, 3000, 'model estimate'))
    results.append(await scenario('admin_simulation', '/?admin=1', 1440, 1800, 'model estimate', admin=True))
    json.dump(results, open(os.path.join(OUT, f'measurements_{THEME}.json'), 'w'), indent=2)
    print(json.dumps(results, indent=2))

asyncio.run(main())
