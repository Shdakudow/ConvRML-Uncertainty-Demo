"""Browser-check saved dropout-rate curves and matched test examples."""

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
    profile = tempfile.mkdtemp(prefix="dropout-study-browser-")
    log = open("/tmp/dropout_study_browser.log", "w")
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
        data = json.loads((REPO / "corrected-epoch50/dropout-study/data.json").read_text())
        for camera in ["rml", "diffuser"]:
            call("Page.navigate", dict(url=base + "corrected-epoch50/?camera=" + camera))
            wait("document.querySelector('#dropoutRateStudy')?.dataset.ready==='true'")
            assert js("document.querySelectorAll('.dropout-plots figure').length") == 3
            assert js("document.querySelectorAll('.dropout-plots circle').length") == 27
            js("document.querySelector('#dropoutRateStudy').scrollIntoView()")
            expected = data["cameras"][camera]
            for passes in ["30", "60", "100"]:
                js("document.querySelector('#dropoutPasses').value=" + json.dumps(passes) + ";document.querySelector('#dropoutPasses').dispatchEvent(new Event('change'))")
                values = js("[...document.querySelectorAll('#dropoutRateValues tr')].map(row=>[...row.querySelectorAll('td')].map(td=>td.textContent))")
                for i, rate in enumerate(expected["rates"]):
                    for column, key in enumerate(["ssim", "psnr", "mae"], 1):
                        assert values[i][column] == format(rate["results"][passes][key], ".6f" if key=="mae" else ".5f")
            js("document.querySelector('.dropout-plots circle').dispatchEvent(new Event('mouseenter'))")
            assert '30 passes:' in js("document.querySelector('.dropout-tooltip').textContent"), js("document.querySelector('.dropout-tooltip').textContent")
            assert js("document.querySelector('#dropoutExample option').textContent").startswith('1 · ')
            for index, example in enumerate(expected["examples"]):
                js("document.querySelector('#dropoutExample').value=" + json.dumps(str(index)) + ";document.querySelector('#dropoutExample').dispatchEvent(new Event('change'))")
                wait("[...document.querySelectorAll('#dropoutExampleImages img')].every(e=>e.complete&&e.naturalWidth===256)")
                assert str(example["id"]) in js("document.querySelector('#dropoutExampleName').textContent")
                for arm in ["mc_005", "mc_010"]:
                    assert format(example["models"][arm]["metrics"]["ssim"], '.5f') in js("document.querySelector('#dropoutExampleImages').textContent")
            js("document.querySelector('#dropoutNext').click()")
            assert js("document.querySelector('#dropoutExample').value") == "0"
            assert js("document.querySelector('#dropoutExampleMaps').hidden")
            js("document.querySelector('#dropoutMaps').click()")
            wait("[...document.querySelectorAll('#dropoutExampleMaps img')].every(e=>e.complete&&e.naturalWidth===256)")
            assert not js("document.querySelector('#dropoutExampleMaps').hidden")
            js("document.querySelector('#dropoutRateStudy').scrollIntoView()")
            screenshot("dropout_study_" + camera)
        assert not errors, errors
        call("Emulation.setDeviceMetricsOverride", dict(width=390,height=844,deviceScaleFactor=1,mobile=True))
        js("document.querySelector('#dropoutRateStudy').scrollIntoView()")
        assert js("document.querySelector('#dropoutRateStudy').getBoundingClientRect().right <= innerWidth+1")
        screenshot("dropout_study_mobile")
        print("PASS: both cameras, 27 chart points, exact values at all pass counts, hover/focus, 16 matched test examples, maps, next/wrap, mobile width.")
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
