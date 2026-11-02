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
PIXELS = Path.home() / ".local/share/convrml-pixel-inspection-20261030/assets"


def main():
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_GET(self):
            try:
                name = self.path.split("?", 1)[0].lstrip("/")
                if name in ("pixel_maps.json", "uncertainty_agreement.json"):
                    payload = json.loads((ROOT / name).read_text())
                    # Serve the exact saved maps locally to make QA independent
                    # of GitHub latency. Only the download address changes.
                    key = "base" if name == "pixel_maps.json" else "pixel_asset_base"
                    payload[key] = (
                        f"http://127.0.0.1:{self.server.server_address[1]}/_pixels"
                    )
                    body = json.dumps(payload).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                if name.endswith(".mp4"):
                    # Match the production host's byte-range support. Without
                    # it Chrome can reset a seek while metadata-only loading.
                    target = Path(self.translate_path(self.path))
                    size = target.stat().st_size
                    start, end = 0, size - 1
                    requested = self.headers.get("Range")
                    if requested:
                        first, last = requested.removeprefix("bytes=").split("-", 1)
                        start = int(first) if first else max(0, size - int(last))
                        end = min(size - 1, int(last)) if first and last else size - 1
                    self.send_response(206 if requested else 200)
                    self.send_header("Content-Type", "video/mp4")
                    self.send_header("Accept-Ranges", "bytes")
                    self.send_header("Content-Length", str(end - start + 1))
                    if requested:
                        self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
                    self.end_headers()
                    with target.open("rb") as stream:
                        stream.seek(start)
                        remaining = end - start + 1
                        while remaining:
                            chunk = stream.read(min(65536, remaining))
                            if not chunk:
                                break
                            self.wfile.write(chunk)
                            remaining -= len(chunk)
                    return
                super().do_GET()
            except (BrokenPipeError, ConnectionResetError):
                # Browsers cancel pending media downloads when changing sequence.
                pass

        def translate_path(self, path):
            name = path.split("?", 1)[0]
            if name.startswith("/_pixels/"):
                target = (PIXELS / name[len("/_pixels/") :]).resolve()
                return (
                    str(target)
                    if target.is_relative_to(PIXELS.resolve())
                    else "/dev/null"
                )
            return super().translate_path(path)

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

        def wait_for(expression):
            for _ in range(200):
                if js(expression):
                    return
                time.sleep(0.05)
            diagnostic = js(
                "JSON.stringify({frame:document.querySelector('#frame')?.value, intensity:document.querySelector('#intensityValues')?.textContent,agreement:document.querySelector('#agreementValues')?.textContent,videos:[...document.querySelectorAll('video')].map(v=>({time:v.currentTime,seeking:v.seeking,ready:v.readyState,paused:v.paused}))})"
            )
            raise AssertionError(
                "Browser state did not become ready: " + expression + " " + diagnostic
            )

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
            wait_for(
                "[...document.querySelectorAll('video')].every(v => v.readyState >= 1 && !v.seeking)"
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
            wait_for(
                f"[...document.querySelectorAll('video')].every(v => !v.seeking && Math.floor(v.currentTime * 20 + 1e-6) === {index})"
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
            wait_for(
                "Number(document.querySelector('#frame').value) === 11 && [...document.querySelectorAll('video')].every(v => !v.seeking)"
            )
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
        agreement = json.loads((ROOT / "uncertainty_agreement.json").read_text())

        def assert_map_counts(selector, expected_row):
            counts = js(
                """(()=>{const c=document.querySelector('"""
                + selector
                + """'),a=c.getContext('2d').getImageData(0,0,c.width,c.height).data,n=[0,0,0];for(let p=0;p<a.length;p+=4){if(a[p]===226&&a[p+1]===195&&a[p+2]===255)n[0]++;if(a[p]===157&&a[p+1]===223&&a[p+2]===210)n[1]++;if(a[p]===249&&a[p+1]===186&&a[p+2]===119)n[2]++;}return n})()"""
            )
            assert counts == [
                expected_row["top10_intersection"],
                expected_row["top10_qutcc_count"] - expected_row["top10_intersection"],
                expected_row["top10_im2im_count"] - expected_row["top10_intersection"],
            ], (counts, expected_row)

        # Compare all selected pixels, not just one automatically chosen patch.
        for name in agreement["videos"]:
            js(
                f"document.querySelector('#videoSelect').value='{name}';document.querySelector('#videoSelect').dispatchEvent(new Event('change'))"
            )
            wait_for(
                "document.querySelector('#videoDisagreement').getAttribute('aria-busy') === 'false' && document.querySelector('#videoDisagreement .agreement-title').textContent.includes('Frame 1')"
            )
            row = agreement["videos"][name]["rows"][0]
            assert js("document.querySelector('#agreementMetric').value") == "overlap"
            assert (
                js(
                    "document.querySelector('#videoDisagreement .agreement-comparison').value"
                )
                == "overlap"
            )
            assert (
                js("document.querySelector('#agreementPlot path').dataset.metric")
                == "top10_iou"
            )
            assert js("document.querySelector('#inspectRankGapTop').hidden")
            assert js("document.querySelector('#trackingControl').hidden")
            assert f"{row['top10_iou']*100:.2f}%" in js(
                "document.querySelector('#agreementValues').textContent"
            )
            assert_map_counts("#videoDisagreement canvas", row)
            # Switching either dropdown updates both the graph and the map.
            js(
                "document.querySelector('#agreementMetric').value='spearman';document.querySelector('#agreementMetric').dispatchEvent(new Event('change'))"
            )
            assert (
                js(
                    "document.querySelector('#videoDisagreement .agreement-comparison').value"
                )
                == "spearman"
            )
            assert (
                js("document.querySelector('#agreementPlot path').dataset.metric")
                == "spearman"
            )
            assert not js("document.querySelector('#inspectRankGapTop').hidden")
            js(
                "document.querySelector('#videoDisagreement .agreement-comparison').value='overlap';document.querySelector('#videoDisagreement .agreement-comparison').dispatchEvent(new Event('change'))"
            )
            assert js("document.querySelector('#agreementMetric').value") == "overlap"
            assert_map_counts("#videoDisagreement canvas", row)
            # Frame seeking must recompute the displayed sets from the new maps.
            index = len(agreement["videos"][name]["rows"]) // 2
            js(f"clearPixel();seekFrame({index})")
            wait_for(
                f"document.querySelector('#videoDisagreement').getAttribute('aria-busy') === 'false' && document.querySelector('#videoDisagreement .agreement-title').textContent.includes('Frame {index+1}')"
            )
            wait_for(
                f"[...document.querySelectorAll('video')].every(v => !v.seeking) && Number(document.querySelector('#frame').value) === {index+1}"
            )
            row = agreement["videos"][name]["rows"][index]
            actual = js("document.querySelector('#agreementValues').textContent")
            assert f"{row['top10_iou']*100:.2f}%" in actual, (
                name,
                index,
                row["top10_iou"],
                actual,
            )
            assert_map_counts("#videoDisagreement canvas", row)
        js("document.querySelector('#agreementSection').scrollIntoView()")
        time.sleep(0.1)
        shot = call("Page.captureScreenshot", dict(format="png", fromSurface=True))
        (work / "overlap-graph-desktop.png").write_bytes(base64.b64decode(shot["data"]))
        for layout, width, height in [("desktop", 1440, 1100), ("mobile", 390, 844)]:
            call(
                "Emulation.setDeviceMetricsOverride",
                dict(
                    width=width, height=height, deviceScaleFactor=1, mobile=width < 500
                ),
            )
            js("document.querySelector('#videoDisagreement').scrollIntoView()")
            time.sleep(0.2)
            assert js("document.documentElement.scrollWidth <= window.innerWidth + 1")
            shot = call("Page.captureScreenshot", dict(format="png", fromSurface=True))
            (work / f"overlap-map-{layout}.png").write_bytes(
                base64.b64decode(shot["data"])
            )
        call(
            "Emulation.setDeviceMetricsOverride",
            dict(width=1440, height=1100, deviceScaleFactor=1, mobile=False),
        )
        call(
            "Page.navigate",
            dict(url=f"http://127.0.0.1:{server.server_address[1]}/named-captures/"),
        )
        wait_for(
            "document.querySelector('#captureAgreement')?.getAttribute('aria-busy') === 'false'"
        )
        for capture, row in agreement["captures"].items():
            js(
                f"document.querySelector('#imageSelect').value='{capture}';document.querySelector('#imageSelect').dispatchEvent(new Event('change'))"
            )
            wait_for(
                "document.querySelector('#viewer').getAttribute('aria-busy') === 'false' && document.querySelector('#captureAgreement').getAttribute('aria-busy') === 'false'"
            )
            assert (
                js(
                    "document.querySelector('#captureAgreement .agreement-comparison').value"
                )
                == "overlap"
            )
            assert_map_counts("#captureAgreement canvas", row)
        js(
            "document.querySelector('#captureAgreement .agreement-comparison').value='spearman';document.querySelector('#captureAgreement .agreement-comparison').dispatchEvent(new Event('change'))"
        )
        assert not js("document.querySelector('#inspectRankGapTop').hidden")
        js(
            "document.querySelector('#captureAgreement .agreement-comparison').value='overlap';document.querySelector('#captureAgreement .agreement-comparison').dispatchEvent(new Event('change'))"
        )
        assert js("document.querySelector('#inspectRankGapTop').hidden")
        call(
            "Page.navigate",
            dict(
                url=f"http://127.0.0.1:{server.server_address[1]}/videos-plot/?video=video1"
            ),
        )
        wait_for(
            "document.querySelectorAll('#intensityPlot path[data-model]').length === 2 && !document.querySelector('#videoSelect').disabled"
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
            "PASS: 5 real videos, exact per-frame Spearman/Pearson values, fixed ±1 axis, plot-click seeking, keyboard seeking, frame-slider synchronization, correct CSV links; Spearman/overlap selector synchronization; exact intersection and exclusive-region pixel counts for five videos and ten named captures; desktop/mobile layout; no JavaScript errors."
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
