"""Check the real video brightness plot in local standalone Chrome."""

import base64
import functools
import http.server
import json
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import urllib.request

import websocket

ROOT = Path(__file__).resolve().parents[1]


def main():
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_GET(self):
            try:
                super().do_GET()
            except (BrokenPipeError, ConnectionResetError):
                # Browsers cancel pending media downloads when changing sequence.
                pass

    server = http.server.ThreadingHTTPServer(
        ("127.0.0.1", 0), functools.partial(Quiet, directory=str(ROOT))
    )
    threading.Thread(target=server.serve_forever, daemon=True).start()
    with socket.socket() as available:
        available.bind(("127.0.0.1", 0))
        port = available.getsockname()[1]
    profile = tempfile.mkdtemp(prefix="video-intensity-browser-")
    work = Path.home() / ".local/share/convrml-video-intensity-20261102"
    work.mkdir(parents=True, exist_ok=True)
    log = (work / "chrome.log").open("w")
    process = subprocess.Popen(
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
    )
    ws = None
    try:
        for _ in range(100):
            try:
                tabs = json.load(
                    urllib.request.urlopen(f"http://localhost:{port}/json", timeout=1)
                )
                tab = next(t for t in tabs if t["type"] == "page")
                break
            except Exception:
                time.sleep(0.1)
        else:
            raise RuntimeError("Chrome connection unavailable")
        ws = websocket.create_connection(
            tab["webSocketDebuggerUrl"], origin=f"http://localhost:{port}", timeout=30
        )
        seq = 0
        errors = []

        def call(method, params=None):
            nonlocal seq
            seq += 1
            ws.send(json.dumps(dict(id=seq, method=method, params=params or {})))
            while True:
                value = json.loads(ws.recv())
                if value.get("method") == "Runtime.exceptionThrown":
                    errors.append(value)
                if value.get("id") == seq:
                    if "error" in value:
                        raise RuntimeError(value)
                    return value.get("result", {})

        def js(code):
            value = call(
                "Runtime.evaluate",
                dict(expression=code, returnByValue=True, awaitPromise=True),
            )
            if "exceptionDetails" in value:
                raise RuntimeError(value)
            return value.get("result", {}).get("value")

        call("Runtime.enable")
        call(
            "Emulation.setDeviceMetricsOverride",
            dict(width=1440, height=1100, deviceScaleFactor=1, mobile=False),
        )
        call(
            "Page.navigate",
            dict(
                url=f"http://127.0.0.1:{server.server_address[1]}/videos-plot/?video=video1"
            ),
        )
        for _ in range(200):
            if js(
                "document.querySelectorAll('#intensityPlot path[data-model]').length === 2 && !document.querySelector('#videoSelect').disabled"
            ):
                break
            time.sleep(0.1)
        else:
            raise RuntimeError(
                js("document.querySelector('#intensityValues').textContent")
            )
        expected = json.loads((ROOT / "videos-plot/intensity/data.json").read_text())
        for name in ("video1", "video4", "video6", "video7", "video10"):
            js(
                f"document.querySelector('#videoSelect').value='{name}';document.querySelector('#videoSelect').dispatchEvent(new Event('change'))"
            )
            total = expected["videos"][name]["frames"]
            assert (
                js(
                    "document.querySelectorAll('#intensityPlot path[data-model]').length"
                )
                == 2
            )
            assert js("document.querySelector('#intensityMetric').value") == "spearman"
            assert js(
                "document.querySelector('#intensityPlot').textContent.includes('-1.0') && document.querySelector('#intensityPlot').textContent.includes('1.0')"
            )
            # Selecting a frame must display the exact numerical coefficient.
            index = total // 2
            js(
                f"document.querySelector('#frame').value='{index+1}';document.querySelector('#frame').dispatchEvent(new Event('input'))"
            )
            text = js("document.querySelector('#intensityValues').textContent")
            assert f"Frame {index+1} " in text, text
            for method in ("qutcc", "im2im"):
                value = expected["videos"][name]["models"][method]["rows"][index][
                    "spearman"
                ]
                assert f"{value:.4f}" in text, text
            # The graph itself seeks to frame 10.
            js(
                """(()=>{const svg=document.querySelector('#intensityPlot'),hit=document.querySelector('#intensityHit'),n=Number(document.querySelector('#frame').max),p=new DOMPoint(80+890*9/(n-1),100).matrixTransform(svg.getScreenCTM());hit.dispatchEvent(new MouseEvent('click',{clientX:p.x,clientY:p.y,bubbles:true}));})()"""
            )
            assert js("Number(document.querySelector('#frame').value)") == 10
            # Focused arrow-key navigation also updates both video frame controls.
            js(
                "document.querySelector('#intensityPlot').dispatchEvent(new KeyboardEvent('keydown',{key:'ArrowRight',bubbles:true}))"
            )
            assert js("Number(document.querySelector('#frame').value)") == 11
            js(
                "document.querySelector('#intensityMetric').value='pearson';document.querySelector('#intensityMetric').dispatchEvent(new Event('change'))"
            )
            text = js("document.querySelector('#intensityValues').textContent")
            assert "Pearson r" in text
            for method in ("qutcc", "im2im"):
                value = expected["videos"][name]["models"][method]["rows"][10][
                    "pearson"
                ]
                assert f"{value:.4f}" in text, text
            assert (
                js("document.querySelector('#intensityCSV').getAttribute('href')")
                == f"intensity/{name}.csv"
            )
            js(
                "document.querySelector('#intensityMetric').value='spearman';document.querySelector('#intensityMetric').dispatchEvent(new Event('change'))"
            )
        js(
            "document.querySelector('#videoSelect').value='video1';document.querySelector('#videoSelect').dispatchEvent(new Event('change'))"
        )
        for name, width, height in [("desktop", 1440, 1100), ("mobile", 390, 844)]:
            call(
                "Emulation.setDeviceMetricsOverride",
                dict(
                    width=width, height=height, deviceScaleFactor=1, mobile=width < 500
                ),
            )
            js(
                "document.querySelector('#intensitySection').scrollIntoView({block:'start'})"
            )
            time.sleep(0.25)
            assert js("document.documentElement.scrollWidth <= window.innerWidth + 1")
            shot = call("Page.captureScreenshot", dict(format="png", fromSurface=True))
            (work / (name + ".png")).write_bytes(base64.b64decode(shot["data"]))
        assert not errors, errors
        print(
            "PASS: 5 real videos, exact per-frame Spearman/Pearson values, fixed ±1 axis, plot-click seeking, keyboard seeking, frame-slider synchronization, correct CSV links, desktop/mobile layout, no JavaScript errors."
        )
    finally:
        if ws:
            ws.close()
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        server.shutdown()
        server.server_close()
        log.close()
        shutil.rmtree(profile, ignore_errors=True)


if __name__ == "__main__":
    main()
