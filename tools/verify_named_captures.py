"""Browser-check all named captures, bounds, mobile layout, and tab links."""

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
    profile = tempfile.mkdtemp(prefix="named-captures-browser-")
    log = open("/tmp/named_captures_browser.log", "w")
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
        call("Page.navigate", dict(url=base + "named-captures/"))
        wait("document.querySelector('#status')?.textContent === '1 / 10'")
        expected = json.loads((REPO / "named-captures/data.json").read_text())
        assert js("document.querySelector('#captureTitle').textContent") == "hand.tiff"
        assert js("document.querySelectorAll('#imageSelect option').length") == 10
        assert js("document.querySelectorAll('.model').length") == 2
        assert js("[...document.querySelectorAll('.bounds')].every(e=>e.hidden)")
        assert expected["heatmap"]["min"] == 0 and expected["heatmap"]["max"] == 1
        assert js("document.querySelectorAll('#widthRows tr').length") == 10
        for model in ("qutcc", "im2im"):
            assert f"{expected['mean_interval_width'][model]:.5f}" in js(
                "document.querySelector('#widthAverage').textContent"
            )
        assert js(
            "[...document.querySelectorAll('#viewer img')].every(e=>e.complete && e.naturalWidth===480 && e.naturalHeight===270)"
        )
        screenshot("named_captures_desktop")
        js("document.querySelector('#boundsToggle').click()")
        assert js(
            "[...document.querySelectorAll('.bounds')].every(e=>!e.hidden && e.getBoundingClientRect().height>0)"
        )
        assert js("new URL(location.href).searchParams.get('bounds')") == "1"
        screenshot("named_captures_bounds")
        for index, example in enumerate(expected["examples"]):
            js(
                "document.querySelector('#imageSelect').value="
                + json.dumps(example["id"])
                + ";document.querySelector('#imageSelect').dispatchEvent(new Event('change'))"
            )
            wait(f"document.querySelector('#status').textContent === '{index+1} / 10'")
            assert (
                js("document.querySelector('#captureTitle').textContent")
                == example["name"]
            )
            for key in ["qutcc", "im2im"]:
                for field, suffix in [
                    ("reconstruction", "Prediction"),
                    ("uncertainty", "Width"),
                    ("lower_bound", "Lower"),
                    ("upper_bound", "Upper"),
                ]:
                    assert (
                        js(
                            f"document.querySelector('#{key+suffix}').getAttribute('src').split('?')[0]"
                        )
                        == example["models"][key]["images"][field]
                    )
                width = f"{example['models'][key]['metrics']['mean_interval_width']:.5f}"
                assert width in js(
                    f"document.querySelector('#{key}Metrics').textContent"
                )
            assert js(
                "[...document.querySelectorAll('#viewer img')].every(e=>e.complete && e.naturalWidth===480)"
            )
        js("document.querySelector('#next').click()")
        wait("document.querySelector('#status').textContent==='1 / 10'")
        js("document.querySelector('#previous').click()")
        wait("document.querySelector('#status').textContent==='10 / 10'")
        assert not errors, errors

        call(
            "Page.navigate",
            dict(url=base + "named-captures/?capture=toy_fish&bounds=1"),
        )
        wait(
            "document.querySelector('#captureTitle')?.textContent==='toy_fish.tiff' && document.querySelector('#status').textContent==='8 / 10'"
        )
        assert js("document.querySelector('#boundsToggle').checked")
        call(
            "Emulation.setDeviceMetricsOverride",
            dict(width=390, height=844, deviceScaleFactor=1, mobile=True),
        )
        wait("document.documentElement.scrollWidth <= window.innerWidth + 1")
        screenshot("named_captures_mobile")
        for page in ["", "corrected-epoch50/", "raw-diffusercam/"]:
            call(
                "Page.navigate",
                dict(url=base + page + "?camera=diffuser&capture=toy_fish"),
            )
            wait("!!document.querySelector('[data-demo-route=captures]')?.href")
            assert (
                js("document.querySelectorAll('[data-demo-route=captures]').length")
                == 1
            )
            href = js("document.querySelector('[data-demo-route=captures]').href")
            assert "/named-captures/" in href and "capture=toy_fish" in href, href
            assert (
                js("document.querySelector('[data-demo-route=raw]').href")
                .split("?")[0]
                .endswith("/raw-diffusercam/")
            )
        print(
            "PASS: 10 named captures, 2 Exp3 models, all image/bound paths, exact widths, bounds persistence, navigation, mobile layout."
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
    main(sys.argv[1] if len(sys.argv) > 1 else None)
