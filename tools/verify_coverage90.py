"""Browser checks for near-90% overlays, old calibration bookmark normalization, and exact metrics.

Uses the existing Chrome/CDP fallback when the in-app browser cannot connect.
An optional URL checks the deployed site; otherwise serves this checkout.
"""

import base64
import copy
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

ROOT = Path(__file__).resolve().parents[1]


class Handler(http.server.SimpleHTTPRequestHandler):
    curve_fixture = None

    def log_message(self, *args):
        pass

    def do_GET(self):
        if (
            self.curve_fixture is not None
            and self.path.split("?")[0] == "/coverage90_curves.json"
        ):
            body = json.dumps(self.curve_fixture).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()


def main(base=None, fixture=False):
    expected_curves = json.loads((ROOT / "coverage90_curves.json").read_text())
    if fixture:
        if base:
            raise ValueError("Synthetic rendering fixtures may only be served locally")
        expected_curves = copy.deepcopy(expected_curves)
        rows = expected_curves["groups"]["rml"]["im2im"]
        latest = rows[-1]
        for index in (0, 1):
            rows[index] = dict(copy.deepcopy(latest), epoch=(index + 1) * 5)
        expected_curves["groups"]["rml"]["qutcc"][0] = dict(
            epoch=5, status="failed", error="Synthetic test fixture"
        )
        Handler.curve_fixture = expected_curves
    server = None
    if base is None:
        server = http.server.ThreadingHTTPServer(
            ("127.0.0.1", 0), functools.partial(Handler, directory=str(ROOT))
        )
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{server.server_port}/"
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    profile = tempfile.mkdtemp(prefix="coverage90-browser-")
    log = open("/tmp/coverage90-browser.log", "w")
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
                tab = next(
                    t
                    for t in json.load(
                        urllib.request.urlopen(f"http://localhost:{port}/json")
                    )
                    if t.get("type") == "page"
                )
                break
            except Exception:
                time.sleep(0.2)
        ws = websocket.create_connection(
            tab["webSocketDebuggerUrl"], origin=f"http://localhost:{port}", timeout=90
        )
        sequence, errors = 0, []

        def call(method, params=None):
            nonlocal sequence
            sequence += 1
            ws.send(json.dumps(dict(id=sequence, method=method, params=params or {})))
            while True:
                message = json.loads(ws.recv())
                if message.get("method") == "Runtime.exceptionThrown":
                    errors.append(message)
                if message.get("id") == sequence:
                    assert "error" not in message, message
                    return message.get("result", {})

        def js(expression):
            result = call(
                "Runtime.evaluate",
                dict(expression=expression, returnByValue=True, awaitPromise=True),
            )
            assert "exceptionDetails" not in result, result
            return result.get("result", {}).get("value")

        def wait(expression):
            for _ in range(400):
                if js(expression):
                    return
                status = js("document.querySelector('#status')?.textContent||''")
                assert not any(
                    word in status for word in ["Could not", "not yet published"]
                ), status
                time.sleep(0.15)
            raise AssertionError(
                (expression, js("document.body.innerText.slice(0,1000)"))
            )

        def ready():
            wait(
                "!!document.querySelector('#calibrationLabel') && !document.querySelector('#example').disabled && /[0-9]+ \/ [0-9]+/.test(document.querySelector('#status').textContent)"
            )

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
        metadata = json.loads((ROOT / "coverage90.json").read_text())
        for camera in ["rml", "diffuser"]:
            call(
                "Page.navigate", dict(url=base + "corrected-epoch50/?camera=" + camera)
            )
            ready()
            assert js(
                "Coverage90.active && !document.querySelector('#calibrationMode') && document.querySelector('#calibrationLabel').textContent.includes('Near 90%')"
            )
            expected = metadata["groups"].get(camera, {})
            methods = {
                ("paper_qutcc" if m == "qutcc" else m): e for m, e in expected.items()
            }
            assert sorted(js("Object.keys(example.models)")) == sorted(methods)
            assert js("document.querySelectorAll('#aggregateRows tr').length") == 4
            assert js(
                "document.querySelector('#aggregateRows').closest('table').tHead.textContent.includes('Calibration coverage')"
            )
            assert js("document.querySelector('#analysisPlots').hidden")
            for key, entry in methods.items():
                actual = js("example.models[" + json.dumps(key) + "].metrics")
                assert (
                    abs(actual["width"] - entry["per_image"][0]["clipped"]["width"])
                    < 1e-7
                )
                assert (
                    abs(
                        actual["coverage"]
                        - entry["per_image"][0]["clipped"]["coverage"]
                    )
                    < 1e-7
                )
            expected_epochs = sorted(
                {
                    row["epoch"]
                    for rows in expected_curves["groups"][camera].values()
                    for row in rows
                    if row["status"] == "complete"
                }
            )
            actual_epochs = js(
                "[...new Set([...document.querySelectorAll('#intervalHistoryPlots .epoch-hit')].map(e=>JSON.parse(decodeURIComponent(e.dataset.comparison)).epoch))].sort((a,b)=>a-b)"
            )
            assert actual_epochs == expected_epochs, (actual_epochs, expected_epochs)
            assert js(
                "document.querySelector('#intervalCurveStatus').textContent.includes('/40')"
            )
            if fixture and camera == "rml":
                js(
                    "[...document.querySelectorAll('#intervalHistoryPlots .epoch-hit')].find(e=>JSON.parse(decodeURIComponent(e.dataset.comparison)).epoch===5).dispatchEvent(new PointerEvent('pointerenter'))"
                )
                assert js(
                    "[...document.querySelectorAll('#intervalHistoryPlots .epoch-tooltip')].some(t=>!t.hidden && t.textContent.includes('Calibration failed'))"
                )
            js("document.querySelector('#boundsToggle').click()")
            assert js(
                "document.querySelector('#matrix').classList.contains('show-bounds')"
            )
            js("document.querySelector('#next').click()")
            ready()
            assert js("current") == 1
            js("window.scrollTo(0,0)")
            screenshot("coverage90_" + camera)
            # Old calibration bookmarks use the current calibrated comparison.
            call("Page.navigate", dict(url=base + "corrected-epoch50/?camera=" + camera + "&calibration=reference"))
            ready()
            assert js("Coverage90.active && !new URL(location.href).searchParams.has('calibration')")
            assert sorted(js("Object.keys(example.models)")) == sorted(methods)
            assert js("[...document.querySelectorAll('[data-demo-route]')].every(a=>!new URL(a.href).searchParams.has('calibration'))")

        for study in ["clean"]:
            call("Page.navigate", dict(url=base + "raw-diffusercam/?study=" + study))
            ready()
            assert js("Coverage90.active")
            expected = metadata["groups"].get("raw_" + study, {})
            assert sorted(js("Object.keys(example.models)")) == sorted(expected)
            assert js("document.querySelectorAll('#aggregateRows tr').length") == 2
            assert js("document.querySelectorAll('#intervalPlots .plot').length") == 2
            assert js("document.querySelectorAll('#calibrationRows tr').length") == 20
            failed = sum(
                row["status"] == "failed"
                for rows in expected_curves["groups"]["raw_" + study].values()
                for row in rows
            )
            assert (
                js(
                    "[...document.querySelectorAll('#intervalPlots text')].filter(t=>t.textContent==='×').length"
                )
                == 2 * failed
            )
            assert js(
                "document.querySelector('#calibrationProtocol').textContent.includes('90.0–90.1%')"
            )
            for key, entry in expected.items():
                metrics = js("example.models[" + json.dumps(key) + "].metrics")
                assert (
                    abs(metrics["width"] - entry["per_image"][0]["clipped"]["width"])
                    < 1e-7
                )
            js("document.querySelector('#showBounds').click()")
            assert js(
                "document.querySelector('#matrix').classList.contains('show-bounds')"
            )
            js("document.querySelector('#next').click()")
            ready()
            assert js("index") == 1
            assert not js("!!document.querySelector('#study')")
            js("window.scrollTo(0,0)")
            screenshot("coverage90_raw_" + study)
        call(
            "Emulation.setDeviceMetricsOverride",
            dict(width=390, height=844, deviceScaleFactor=1, mobile=True),
        )
        assert js("document.documentElement.scrollWidth<=innerWidth+1")
        screenshot("coverage90_mobile")
        assert not errors, errors
        print(
            "PASS: Exp2 RML/DiffuserCam, clean raw, exact saved metrics, five-epoch curve provenance, pending/failure distinctions, old calibration bookmark normalization, bounds, navigation, mobile layout."
        )
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
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base", nargs="?")
    parser.add_argument("--fixture", action="store_true")
    args = parser.parse_args()
    main(args.base, args.fixture)
