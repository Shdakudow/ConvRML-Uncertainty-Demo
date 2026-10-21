"""Check difficulty groups and actual corruption labels in all three experiments."""

import base64
import functools
import http.server
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request

import websocket

REPO = Path(__file__).resolve().parents[1]


class Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def main(base=None):
    server = None
    if base is None:
        server = http.server.ThreadingHTTPServer(
            ("127.0.0.1", 0), functools.partial(Handler, directory=str(REPO))
        )
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{server.server_address[1]}/"
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    profile = tempfile.mkdtemp(prefix="example-browser-")
    log = open("/tmp/example_browser.log", "w")
    chrome = subprocess.Popen(
        [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "--headless=new",
            "--disable-gpu",
            "--no-first-run",
            "--disable-background-networking",
            f"--remote-debugging-port={port}",
            f"--remote-allow-origins=http://localhost:{port}",
            "--user-data-dir=" + profile,
            "about:blank",
        ],
        stdout=log,
        stderr=log,
        start_new_session=True,
    )
    try:
        for _ in range(100):
            try:
                tabs = json.load(
                    urllib.request.urlopen(f"http://localhost:{port}/json")
                )
                tab = next(t for t in tabs if t.get("type") == "page")
                break
            except Exception:
                time.sleep(0.2)
        ws = websocket.create_connection(
            tab["webSocketDebuggerUrl"], origin=f"http://localhost:{port}", timeout=40
        )
        sequence = 0
        errors = []

        def call(method, params=None):
            nonlocal sequence
            sequence += 1
            ws.send(json.dumps(dict(id=sequence, method=method, params=params or {})))
            while True:
                result = json.loads(ws.recv())
                if result.get("method") == "Runtime.exceptionThrown":
                    errors.append(result)
                if result.get("id") == sequence:
                    assert "error" not in result, result
                    return result.get("result", {})

        def js(expression):
            result = call(
                "Runtime.evaluate",
                dict(expression=expression, returnByValue=True, awaitPromise=True),
            )
            assert "exceptionDetails" not in result, result
            return result.get("result", {}).get("value")

        def wait(expression):
            for _ in range(200):
                if js(expression):
                    return
                time.sleep(0.1)
            raise AssertionError(expression)

        def screenshot(name):
            result = call(
                "Page.captureScreenshot", dict(format="png", fromSurface=True)
            )
            Path("/tmp/" + name + ".png").write_bytes(base64.b64decode(result["data"]))

        call("Runtime.enable")
        call("Network.enable")
        call("Network.setCacheDisabled", dict(cacheDisabled=True))
        call(
            "Emulation.setDeviceMetricsOverride",
            dict(width=1440, height=1200, deviceScaleFactor=1, mobile=False),
        )
        expected=json.loads((REPO/'example-categories.json').read_text())
        def ready():
            wait("!!document.querySelector('#exampleFilters') && !document.querySelector('#example').disabled && /[0-9]+ \/ [0-9]+/.test(document.querySelector('#status').textContent)")
        for folder,group in [("","legacy"),("corrected-epoch50/","exp2")]:
            for camera in ['rml','diffuser']:
                call('Page.navigate',dict(url=base+folder+'?camera='+camera))
                ready()
                assert js("document.querySelectorAll('#example option').length")==50
                assert not js("!!document.querySelector('#provenance')")
                assert not js("[...document.querySelectorAll('summary')].some(s=>s.textContent==='Related comparisons')")
                for difficulty,count in [('easy',17),('medium',16),('hard',17)]:
                    js("document.querySelector('#difficultyFilter').value="+json.dumps(difficulty)+";document.querySelector('#difficultyFilter').dispatchEvent(new Event('change'))")
                    ready()
                    assert js("document.querySelectorAll('#example option').length")==count
                    assert js("document.querySelector('#exampleCategory').dataset.difficulty")==difficulty
                    assert js("[...document.querySelectorAll('#example option')].every(o=>o.textContent.includes("+json.dumps(difficulty.title())+"))")
                    before=js("document.querySelector('#example').value")
                    js("document.querySelector('#next').click()")
                    ready()
                    assert js("document.querySelector('#example').value")!=before
                    assert js("document.querySelector('#exampleCategory').dataset.difficulty")==difficulty
                if group=='exp2' and camera=='rml':
                    js("window.scrollTo(0,0)");screenshot('simplified_exp2')
                    assert js("document.querySelectorAll('#historyPlots .plot').length")>=2
                    assert js("document.querySelectorAll('#intervalHistoryPlots .plot').length")==2
        call('Page.navigate',dict(url=base+'raw-diffusercam/?study=corrupted&example=1'))
        ready()
        assert js("document.querySelector('#exampleCategory').textContent").endswith('Missing pixels')
        assert js("document.querySelectorAll('#corruptionFilter option').length")==10
        assert not js("[...document.querySelectorAll('#corruptionFilter option')].some(o=>o.textContent==='Hybrid')")
        manifest=expected['raw']['corrupted']['entries']
        for corruption in sorted(set(e['corruption'] for e in manifest)):
            js("document.querySelector('#corruptionFilter').value="+json.dumps(corruption)+";document.querySelector('#corruptionFilter').dispatchEvent(new Event('change'))")
            ready()
            count=sum(e['corruption']==corruption for e in manifest)
            assert js("document.querySelectorAll('#example option').length")==count
            assert js("document.querySelector('#exampleCategory').textContent").endswith(corruption)
            displayed=int(js("document.querySelector('#example').value"))
            assert manifest[displayed]['corruption']==corruption
            assert manifest[displayed]['id'] in js("document.querySelector('#status').textContent")
        js("window.scrollTo(0,0)");screenshot('simplified_corrupted_raw')
        js("document.querySelector('#study').value='clean';document.querySelector('#study').dispatchEvent(new Event('change'))")
        ready()
        assert not js("!!document.querySelector('#corruptionFilter')")
        js("document.querySelector('#difficultyFilter').value='easy';document.querySelector('#difficultyFilter').dispatchEvent(new Event('change'))")
        ready()
        assert js("document.querySelector('#exampleCategory').dataset.difficulty")=='easy'
        call('Emulation.setDeviceMetricsOverride',dict(width=390,height=844,deviceScaleFactor=1,mobile=True))
        js('window.scrollTo(0,0)')
        assert js("document.documentElement.scrollWidth <= innerWidth+1")
        screenshot('simplified_raw_mobile')
        assert not errors,errors
        print('PASS: Exp1/Exp2 both cameras, shared relative difficulty groups, filtered navigation, nine saved corruption types, exact IDs/counts, clean/corrupted switching, preserved plots, mobile layout.')
        ws.close()
    finally:
        try:
            os.killpg(chrome.pid, signal.SIGTERM)
            chrome.wait(timeout=10)
        except ProcessLookupError:
            pass
        if server:
            server.shutdown()
            server.server_close()
        log.close()
        shutil.rmtree(profile, ignore_errors=True)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
