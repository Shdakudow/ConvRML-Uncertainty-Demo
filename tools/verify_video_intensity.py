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
EXP4 = Path.home() / ".local/share/convrml-exp4-20261101/assets"
ERRORS = Path.home() / ".local/share/convrml-exp4-errors-20261103/exports"


def main():
    map_requests = []

    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_GET(self):
            try:
                name = self.path.split("?", 1)[0].lstrip("/")
                if name.startswith("_pixels/"):
                    map_requests.append(name)
                if name in ("experiment4/data.json", "experiment4/error-maps.json"):
                    payload = json.loads((ROOT / name).read_text())
                    alias = (
                        "_exp4_errors" if name.endswith("error-maps.json") else "_exp4"
                    )
                    payload["base"] = (
                        f"http://127.0.0.1:{self.server.server_address[1]}/{alias}/"
                    )
                    body = json.dumps(payload).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
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
            for alias, base in (("/_exp4/", EXP4), ("/_exp4_errors/", ERRORS)):
                if name.startswith(alias):
                    target = (base / name[len(alias) :]).resolve()
                    return (
                        str(target)
                        if target.is_relative_to(base.resolve())
                        else "/dev/null"
                    )
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
    work = Path.home() / ".local/share/convrml-video-shared-only-20261104"
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
        assert js(
            "(()=>{const q=document.querySelector('#qutccVideo').getBoundingClientRect(),m=document.querySelector('#videoDisagreement').getBoundingClientRect(),i=document.querySelector('#im2imVideo').getBoundingClientRect(),plots=document.querySelector('.frame-plots').getBoundingClientRect();return q.left<m.left&&m.right<i.left&&m.bottom<plots.top})()"
        )
        assert js(
            "document.querySelector('.top10-key .q-only').textContent.includes('QUTCC top 10% only') && document.querySelector('.top10-key .i-only').textContent.includes('Im2im top 10% only')"
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
            assert js(
                "[...document.querySelectorAll('#intensityMetrics input:checked')].map(e=>e.value)"
            ) == ["spearman"]
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
            assert f"Frame {index+1}\n" in text, text
            for method in ("qutcc", "im2im"):
                value = expected["videos"][name]["models"][method]["rows"][index][
                    "spearman"
                ]
                assert f"{value:.4f}" in text, text
            # Real pointer coordinates are integer CSS pixels. Compute the
            # nearest frame after that rounding, which matters in narrow columns.
            clicked_frame = js(
                """(()=>{const svg=document.querySelector('#intensityPlot'),hit=document.querySelector('#intensityHit'),n=Number(document.querySelector('#frame').max),left=Number(hit.getAttribute('x')),width=Number(hit.getAttribute('width')),p=new DOMPoint(left+width*9/(n-1),100).matrixTransform(svg.getScreenCTM()),event=new MouseEvent('click',{clientX:p.x,clientY:p.y,bubbles:true}),actual=new DOMPoint(event.clientX,event.clientY).matrixTransform(svg.getScreenCTM().inverse()),frame=Math.max(0,Math.min(n-1,Math.round((actual.x-left)/width*(n-1))))+1;hit.dispatchEvent(event);return frame})()"""
            )
            wait_for(
                f"Number(document.querySelector('#frame').value)==={clicked_frame}&&[...document.querySelectorAll('video')].every(v=>!v.seeking)"
            )
            # Focused arrow-key navigation also updates both video frame controls.
            js(
                "document.querySelector('#intensityPlot').dispatchEvent(new KeyboardEvent('keydown',{key:'ArrowRight',bubbles:true}))"
            )
            wait_for(
                f"Number(document.querySelector('#frame').value) === {clicked_frame+1} && [...document.querySelectorAll('video')].every(v => !v.seeking)"
            )
            js(
                "document.querySelector('#intensityMetrics input[value=pearson]').click()"
            )
            text = js("document.querySelector('#intensityValues').textContent")
            assert (
                js(
                    "document.querySelectorAll('#intensityPlot path[data-model]').length"
                )
                == 4
            )
            assert (
                js(
                    "document.querySelectorAll('#intensityPlot path[data-metric=pearson][stroke-dasharray]').length"
                )
                == 2
            )
            assert "Spearman ρ" in text
            assert "Pearson r" in text
            for method in ("qutcc", "im2im"):
                value = expected["videos"][name]["models"][method]["rows"][
                    clicked_frame
                ]["pearson"]
                assert f"{value:.4f}" in text, text
            assert (
                js("document.querySelector('#intensityCSV').getAttribute('href')")
                == f"intensity/{name}.csv"
            )
            js(
                "document.querySelector('#intensityMetrics input[value=pearson]').click()"
            )
        js("document.querySelector('.comparison-stage').scrollIntoView()")
        shot = call("Page.captureScreenshot", dict(format="png", fromSurface=True))
        (work / "top10-desktop.png").write_bytes(base64.b64decode(shot["data"]))
        # Checkbox combinations affect visibility only and retain the selected frame.
        js(
            "document.querySelector('#intensityMetrics input[value=pearson]').click();document.querySelector('#intensityMetrics input[value=spearman]').click()"
        )
        assert (
            js("document.querySelectorAll('#intensityPlot path[data-model]').length")
            == 2
        )
        assert js(
            "[...document.querySelectorAll('#intensityPlot path[data-model]')].every(e=>e.dataset.metric==='pearson')"
        )
        js("document.querySelector('#intensityMetrics input[value=pearson]').click()")
        assert (
            js("document.querySelectorAll('#intensityPlot path[data-model]').length")
            == 0
        )
        assert "Select Spearman or Pearson" in js(
            "document.querySelector('#intensityValues').textContent"
        )
        js("document.querySelector('#intensityMetrics input[value=spearman]').click()")
        assert js("Number(document.querySelector('#frame').value)") == clicked_frame + 1
        # Both plots stay aligned and each can seek the same synchronized videos.
        assert js(
            "(()=>{const a=document.querySelector('#widthSection').getBoundingClientRect(),b=document.querySelector('#intensitySection').getBoundingClientRect();return a.right<b.left&&Math.abs(a.top-b.top)<2})()"
        )
        assert js(
            "Math.abs(document.querySelector('#widthPlot').getBoundingClientRect().top-document.querySelector('#intensityPlot').getBoundingClientRect().top)<2"
        )
        js("document.querySelector('#cumulativeToggle').click()")
        assert (
            js(
                "document.querySelectorAll('#widthPlot polyline[data-series=cumulative]').length"
            )
            == 2
        )
        width_frame = js(
            """(()=>{const svg=document.querySelector('#widthPlot'),hit=document.querySelector('#plotHit'),n=Number(document.querySelector('#frame').max),left=Number(hit.getAttribute('x')),width=Number(hit.getAttribute('width')),p=new DOMPoint(left+width*19/(n-1),100).matrixTransform(svg.getScreenCTM()),event=new MouseEvent('click',{clientX:p.x,clientY:p.y,bubbles:true}),actual=new DOMPoint(event.clientX,event.clientY).matrixTransform(svg.getScreenCTM().inverse()),frame=Math.max(0,Math.min(n-1,Math.round((actual.x-left)/width*(n-1))))+1;hit.dispatchEvent(event);return frame})()"""
        )
        wait_for(
            f"Number(document.querySelector('#frame').value)==={width_frame}&&[...document.querySelectorAll('video')].every(v=>!v.seeking)"
        )
        assert "cumulative" in js("document.querySelector('#plotValues').textContent")
        assert f"Frame {width_frame}" in js(
            "document.querySelector('#intensityValues').textContent"
        )
        js("document.querySelector('.frame-plots').scrollIntoView()")
        shot = call("Page.captureScreenshot", dict(format="png", fromSurface=True))
        (work / "columns-desktop.png").write_bytes(base64.b64decode(shot["data"]))
        call(
            "Emulation.setDeviceMetricsOverride",
            dict(width=390, height=844, deviceScaleFactor=1, mobile=True),
        )
        time.sleep(0.15)
        assert js(
            "(()=>{const a=document.querySelector('#widthSection').getBoundingClientRect(),b=document.querySelector('#intensitySection').getBoundingClientRect();return b.top>=a.bottom&&Math.abs(a.left-b.left)<2})()"
        )
        assert js("document.documentElement.scrollWidth<=innerWidth+1")
        js("document.querySelector('#intensitySection').scrollIntoView()")
        shot = call("Page.captureScreenshot", dict(format="png", fromSurface=True))
        (work / "columns-mobile.png").write_bytes(base64.b64decode(shot["data"]))
        call(
            "Emulation.setDeviceMetricsOverride",
            dict(width=1440, height=1100, deviceScaleFactor=1, mobile=False),
        )
        agreement = json.loads((ROOT / "uncertainty_agreement.json").read_text())

        def assert_map_counts(selector, expected_row):
            counts = js(
                """(()=>{const c=document.querySelector('"""
                + selector
                + """'),a=c.getContext('2d').getImageData(0,0,c.width,c.height).data,n=[0,0,0];for(let p=0;p<a.length;p+=4){if(a[p]===240&&a[p+1]===240&&a[p+2]===240)n[0]++;if(a[p]===0&&a[p+1]===190&&a[p+2]===255)n[1]++;if(a[p]===255&&a[p+1]===112&&a[p+2]===0)n[2]++;}return n})()"""
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
            js("document.querySelector('#sharedOnly').click()")
            wait_for(
                "document.querySelector('#videoDisagreement').getAttribute('aria-busy')==='false' && document.querySelector('.agreement-playback').src.includes('/shared.mp4')"
            )
            shared = dict(
                row,
                top10_qutcc_count=row["top10_intersection"],
                top10_im2im_count=row["top10_intersection"],
            )
            assert_map_counts("#videoDisagreement canvas", shared)
            assert js(
                "getComputedStyle(document.querySelector('.top10-key .q-only')).display==='none'"
            )
            assert js(
                "document.querySelector('.agreement-heading').textContent.includes('Shared')"
            )
            assert js(
                "['qutcc','im2im'].every(m=>document.querySelector('#'+m+'Video').getAttribute('src')===selected.models[m].video)"
            )
            js("document.querySelector('#sharedOnly').click()")
            wait_for(
                "document.querySelector('#videoDisagreement').getAttribute('aria-busy')==='false' && document.querySelector('.agreement-playback').src.includes('/map.mp4')"
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
            wait_for(
                "document.querySelector('#videoDisagreement').getAttribute('aria-busy') === 'false'"
            )
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
        # Playback uses three synchronized, pre-rendered videos. No numerical
        # width-map sidecars should be downloaded while frames advance.
        assert js("!document.querySelector('#showTop10')")
        assert js(
            "['qutcc','im2im'].every(m=>document.querySelector('#'+m+'Video').getAttribute('src')===selected.models[m].video)"
        )
        js("seekFrame(20)")
        wait_for(
            "document.querySelector('#videoDisagreement').getAttribute('aria-busy') === 'false' && [...document.querySelectorAll('video')].every(v=>!v.seeking)"
        )
        time.sleep(0.2)
        before = len(map_requests)
        js("document.querySelector('#play').click()")
        wait_for(
            "[...document.querySelectorAll('video')].every(v=>!v.paused) && Number(document.querySelector('#frame').value)>25"
        )
        assert js(
            "!document.querySelector('.agreement-playback').hidden && document.querySelector('#videoDisagreement canvas').hidden"
        )
        fingerprint = "(()=>{const v=document.querySelector('.agreement-playback'),c=document.createElement('canvas');c.width=48;c.height=27;const x=c.getContext('2d');x.drawImage(v,0,0,48,27);return [...x.getImageData(0,0,48,27).data].reduce((s,n,i)=>(s+n*(i+1))%1000000007,0)})()"
        first = js(fingerprint)
        time.sleep(0.6)
        assert js(fingerprint) != first
        assert js(
            "[...document.querySelectorAll('video')].every(v=>Math.abs(v.currentTime-document.querySelector('#qutccVideo').currentTime)<.12)"
        )
        assert len(map_requests) == before, (before, len(map_requests))
        js("document.querySelector('#sharedOnly').click()")
        wait_for(
            "[...document.querySelectorAll('video')].every(v=>!v.paused && !v.seeking) && document.querySelector('.agreement-playback').src.includes('/shared.mp4')"
        )
        first = js(fingerprint)
        time.sleep(0.4)
        assert js(fingerprint) != first
        assert js(
            "[...document.querySelectorAll('video')].every(v=>Math.abs(v.currentTime-document.querySelector('#qutccVideo').currentTime)<.12)"
        )
        js(
            "document.querySelector('#videoDisagreement').scrollIntoView({behavior:'instant'})"
        )
        shot = call("Page.captureScreenshot", dict(format="png", fromSurface=True))
        (work / "shared-only-desktop.png").write_bytes(base64.b64decode(shot["data"]))
        js("document.querySelector('#sharedOnly').click()")
        wait_for(
            "[...document.querySelectorAll('video')].every(v=>!v.paused && !v.seeking) && document.querySelector('.agreement-playback').src.includes('/map.mp4')"
        )
        js(
            "document.querySelector('#agreementMetric').value='spearman';document.querySelector('#agreementMetric').dispatchEvent(new Event('change'))"
        )
        wait_for(
            "[...document.querySelectorAll('video')].every(v=>!v.paused && !v.seeking) && document.querySelector('.agreement-playback').src.includes('/rank.mp4')"
        )
        assert js(
            "!document.querySelector('.agreement-playback').hidden && document.querySelector('#videoDisagreement canvas').hidden"
        )
        assert js(
            "document.querySelector('#agreementPlot path').dataset.metric==='spearman'"
        )
        assert js(
            "document.querySelector('#videoDisagreement .agreement-map-label').textContent.includes('percentile-rank')"
        )
        first = js(fingerprint)
        time.sleep(0.6)
        assert js(fingerprint) != first
        assert js(
            "[...document.querySelectorAll('video')].every(v=>Math.abs(v.currentTime-document.querySelector('#qutccVideo').currentTime)<.12)"
        )
        assert js(
            "Math.abs(agreementPanel.row.spearman-agreementData.videos[selected.id].rows[Number(document.querySelector('#frame').value)-1].spearman)<1e-10"
        )
        shot = call("Page.captureScreenshot", dict(format="png", fromSurface=True))
        (work / "spearman-playback-desktop.png").write_bytes(
            base64.b64decode(shot["data"])
        )
        js(
            "document.querySelector('#videoDisagreement .agreement-mode').value='width';document.querySelector('#videoDisagreement .agreement-mode').dispatchEvent(new Event('change'))"
        )
        wait_for(
            "[...document.querySelectorAll('video')].every(v=>!v.paused && !v.seeking) && document.querySelector('.agreement-playback').src.includes('/width_gap.mp4')"
        )
        assert js("!document.querySelector('.agreement-playback').hidden")
        assert js(
            "['qutcc','im2im'].every(m=>document.querySelector('#'+m+'Video').getAttribute('src')===selected.models[m].video)"
        )
        js(
            "document.querySelector('#agreementMetric').value='overlap';document.querySelector('#agreementMetric').dispatchEvent(new Event('change'))"
        )
        wait_for(
            "[...document.querySelectorAll('video')].every(v=>!v.paused && !v.seeking) && document.querySelector('.agreement-playback').src.includes('/map.mp4')"
        )
        assert js("!document.querySelector('.agreement-playback').hidden")
        js(
            "document.querySelector('#playbackSpeed').value='0.5';document.querySelector('#playbackSpeed').dispatchEvent(new Event('change'))"
        )
        assert js(
            "[...document.querySelectorAll('video')].every(v=>v.playbackRate===.5)"
        )
        js("document.querySelector('#pause').click()")
        wait_for(
            "document.querySelector('#videoDisagreement').getAttribute('aria-busy') === 'false'"
        )
        assert js(
            "[...document.querySelectorAll('video')].every(v=>v.paused) && document.querySelector('.agreement-playback').hidden && !document.querySelector('#videoDisagreement canvas').hidden"
        )
        current = js("Number(document.querySelector('#frame').value)-1")
        assert_map_counts(
            "#videoDisagreement canvas", agreement["videos"]["video10"]["rows"][current]
        )
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
        call(
            "Page.navigate",
            dict(url=f"http://127.0.0.1:{server.server_address[1]}/experiment4/"),
        )
        wait_for(
            "document.querySelectorAll('#category-tabs button').length===12 && document.querySelectorAll('#learning-ssim polyline').length===2 && !document.querySelector('#panel-overview').hidden"
        )
        assert (
            js(
                "[...document.querySelectorAll('#learningConditions input:checked')].map(e=>e.value).join(',')"
            )
            == "average"
        )
        assert js(
            "[...document.querySelectorAll('#learning-ssim polyline, #learning-psnr polyline')].every(e=>e.getAttribute('points').split(' ').length===100)"
        )
        learning = json.loads((ROOT / "experiment4/learning-data.json").read_text())
        interval_data = json.loads(
            (ROOT / "experiment4/interval-curves.json").read_text()
        )
        wait_for(
            "document.querySelector('#intervalStatus').textContent.includes('checkpoint evaluations complete')"
        )
        for metric in ("ssim", "psnr", "calibration_width", "test_coverage"):
            assert js(
                f"document.querySelector('#learning-{metric}').textContent.includes('Training epoch')"
            )
            assert js(
                f"document.querySelector('#learning-scale-{metric}').textContent.startsWith('Scale: ')"
            )
            assert js(
                f"document.querySelector('#learning-{metric}').parentElement.querySelector('.curve-model-key').textContent.includes('Im2im · dashed')"
            )
        assert js(
            "document.querySelector('#learning-scale-psnr').textContent.includes('dB')"
        )
        assert js(
            "document.querySelector('#learning-scale-test_coverage').textContent.includes('%')"
        )
        assert (
            js(
                "document.querySelector('#learningConditions input[value=fixed_pattern]').parentElement.textContent"
            )
            == "Uneven pixel response"
        )
        for method in ("qutcc", "im2im"):
            score = learning["methods"][method]["history"][-1]["mean"]["ssim"]
            assert f"{score:.4f}" in js(
                "document.querySelector('#learning-values-ssim').textContent"
            )
        js(
            "document.querySelector('#learningConditions input[value=gaussian]').click()"
        )
        assert js("document.querySelectorAll('#learning-ssim polyline').length") == 4
        for metric in ("calibration_width", "test_coverage"):
            assert (
                js(
                    f"document.querySelectorAll('#learning-{metric} circle[data-epoch]').length"
                )
                == 2 * interval_data["completed"]
            )
        js("document.querySelector('#learningConditions input[value=average]').click()")
        assert js("document.querySelectorAll('#learning-ssim polyline').length") == 2
        for metric in ("calibration_width", "test_coverage"):
            assert js(
                f"[...document.querySelectorAll('#learning-{metric} circle[data-epoch]')].every(e=>e.dataset.condition==='gaussian')"
            )
        js("document.querySelector('#learningZoom').click()")
        assert "0.000–1.000" in js(
            "document.querySelector('#learning-scale-ssim').textContent"
        )
        assert "0.0–100.0%" in js(
            "document.querySelector('#learning-scale-test_coverage').textContent"
        )
        js("document.querySelector('#learningZoom').click()")
        assert js(
            "[...document.querySelectorAll('#learning-ssim polyline')].every(e=>e.dataset.condition==='gaussian')"
        )
        js(
            "(()=>{const svg=document.querySelector('#learning-ssim'),p=new DOMPoint(60,100).matrixTransform(svg.getScreenCTM());svg.querySelector('rect').dispatchEvent(new PointerEvent('pointermove',{clientX:p.x,clientY:p.y,bubbles:true}));})()"
        )
        assert "Epoch 1" in js(
            "document.querySelector('#learning-values-ssim').textContent"
        )
        assert js("document.querySelector('#scene').value") == "0"
        assert js("document.querySelectorAll('img[data-kind=error]').length") == 48
        assert js("document.querySelectorAll('.uncertainty-details').length") == 0
        assert (
            js(
                "document.querySelectorAll('.uncertainty-section img[data-kind=width]').length"
            )
            == 48
        )
        # The current layout loads assets only for the active category tab.
        results = json.loads((ROOT / "experiment4/data.json").read_text())
        for condition in results["conditions"]:
            key = condition["id"]
            js(
                f"document.querySelector('#tab-{key}').click();document.querySelectorAll('#panel-{key} img[data-kind=error]').forEach(e=>e.loading='eager')"
            )
            wait_for(
                f"[...document.querySelectorAll('#panel-{key} img[data-kind=error]')].every(e=>e.complete && e.naturalWidth===480 && e.naturalHeight===270)"
            )
            assert js(
                f"[...document.querySelectorAll('#panel-{key} img[data-kind=error]')].every(e=>new URL(e.src).pathname==='/_exp4_errors/errors/{key}/'+e.dataset.arm+'/000.png')"
            )
            assert (
                js("document.querySelectorAll('#tab-panels > :not([hidden])').length")
                == 1
            )
        js("document.querySelector('#tab-gaussian').click()")
        assert js(
            "document.querySelector('#panel-gaussian .reconstructions img').getBoundingClientRect().width > document.querySelector('#panel-gaussian .inputs img').getBoundingClientRect().width * 1.2"
        )
        assert js(
            "document.querySelector('#panel-gaussian .maps img').getBoundingClientRect().width > document.querySelector('#panel-gaussian .reconstructions img').getBoundingClientRect().width"
        )
        assert js(
            "document.querySelector('#panel-gaussian .errors img').getBoundingClientRect().width > document.querySelector('#panel-gaussian .reconstructions img').getBoundingClientRect().width"
        )
        js(
            "document.querySelector('#scene').value='1';document.querySelector('#scene').dispatchEvent(new Event('change'))"
        )
        wait_for(
            "[...document.querySelectorAll('#panel-gaussian img[data-kind=error]')].every(e=>e.complete && e.naturalWidth===480)"
        )
        assert js(
            "[...document.querySelectorAll('#panel-gaussian img[data-kind=error]')].every(e=>e.src.endsWith('/001.png'))"
        )
        wait_for(
            "document.querySelectorAll('#panel-gaussian img[data-kind=width]').length===4"
        )
        js(
            "[...document.querySelectorAll('#panel-gaussian img[data-kind=width]')].forEach(e=>e.loading='eager')"
        )
        wait_for(
            "[...document.querySelectorAll('#panel-gaussian img[data-kind=width]')].every(e=>e.complete && e.naturalWidth===480)"
        )
        # The existing square locator should mark a pixel without opening a
        # panel, changing image dimensions, cropping, or altering the metrics.
        assert js(
            "document.querySelector('#patchToggle')===null && document.querySelector('#patchInspector')===null"
        )
        before_images = js(
            "[...document.querySelectorAll('#panel-gaussian img')].map(e=>[e.src,e.getBoundingClientRect().width,e.getBoundingClientRect().height])"
        )
        before_metrics = js(
            "document.querySelector('#panel-gaussian .scene-metrics').textContent"
        )
        js(
            "document.querySelector('#panel-gaussian .reconstructions img').scrollIntoView({behavior:'instant',block:'center'})"
        )
        wait_for(
            "document.querySelector('#panel-gaussian .reconstructions img').complete && document.querySelector('#panel-gaussian .reconstructions img').naturalWidth===480"
        )

        def click_image(selector, x, y):
            js(
                f"document.querySelector('{selector}').scrollIntoView({{behavior:'instant',block:'center'}})"
            )
            coordinates = js(
                f"(()=>{{const b=document.querySelector('{selector}').getBoundingClientRect(),s=Math.min(b.width/480,b.height/270);return [b.left+(b.width-480*s)/2+({x}+.5)*s,b.top+(b.height-270*s)/2+({y}+.5)*s]}})()"
            )
            js(
                "window.locatorExpected=null;document.addEventListener('click',event=>window.locatorExpected=HeatmapPixels.pointAt(event.target,event,480,270),{once:true,capture:true})"
            )
            call(
                "Input.dispatchMouseEvent",
                dict(
                    type="mousePressed",
                    x=coordinates[0],
                    y=coordinates[1],
                    button="left",
                    buttons=1,
                    clickCount=1,
                ),
            )
            call(
                "Input.dispatchMouseEvent",
                dict(
                    type="mouseReleased",
                    x=coordinates[0],
                    y=coordinates[1],
                    button="left",
                    buttons=0,
                    clickCount=1,
                ),
            )
            point = js("window.locatorExpected")
            assert point is not None
            return f"{point['x']},{point['y']}"

        expected_point = click_image("#panel-gaussian .reconstructions img", 100, 90)
        assert (
            js(
                "document.querySelectorAll('#panel-gaussian .image-locator-marker').length"
            )
            == 13
        )
        assert (
            js(
                "[...document.querySelectorAll('#panel-gaussian .image-locator-marker')].map(e=>e.dataset.point)"
            )
            == [expected_point] * 13
        )
        assert js(
            "[...document.querySelector('#panel-gaussian .image-locator-marker').children].map(e=>e.getAttribute('stroke'))"
        ) == ["#ffffff", "#07111b", "#fff200"]
        assert (
            js(
                "[...document.querySelectorAll('#panel-gaussian img')].map(e=>[e.src,e.getBoundingClientRect().width,e.getBoundingClientRect().height])"
            )
            == before_images
        )
        assert (
            js("document.querySelector('#panel-gaussian .scene-metrics').textContent")
            == before_metrics
        )
        expected_point = click_image("#panel-gaussian .maps img", 470, 260)
        assert js(
            "[...document.querySelectorAll('#panel-gaussian .image-locator-marker')].every(e=>[...e.children].every(r=>Number(r.getAttribute('x'))>=0&&Number(r.getAttribute('y'))>=0&&Number(r.getAttribute('x'))+Number(r.getAttribute('width'))<=480.001&&Number(r.getAttribute('y'))+Number(r.getAttribute('height'))<=270.001))"
        )
        js(
            "document.querySelector('#scene').value='42';document.querySelector('#scene').dispatchEvent(new Event('change'));document.querySelector('#tab-exposure_150').click()"
        )
        assert (
            js(
                "[...document.querySelectorAll('#panel-exposure_150 .image-locator-marker')].map(e=>e.dataset.point)"
            )
            == [expected_point] * 13
        )
        assert (
            js(
                "document.querySelectorAll('#panel-exposure_150 .inputs .image-locator-marker').length"
            )
            == 1
        )
        for layout, width, height in [("desktop", 1440, 1100), ("mobile", 390, 844)]:
            call(
                "Emulation.setDeviceMetricsOverride",
                dict(
                    width=width, height=height, deviceScaleFactor=1, mobile=width < 500
                ),
            )
            expected_point = click_image(
                "#panel-exposure_150 .reconstructions img", 240, 135
            )
            assert (
                js(
                    "[...document.querySelectorAll('#panel-exposure_150 .image-locator-marker')].map(e=>e.dataset.point)"
                )
                == [expected_point] * 13
            )
            assert js("document.documentElement.scrollWidth<=innerWidth+1")
            assert js(
                "(()=>{const r=document.querySelector('#panel-exposure_150 .image-locator-marker rect').getBoundingClientRect();return Math.abs(r.width-24)<1&&Math.abs(r.height-24)<1})()"
            )
            shot = call("Page.captureScreenshot", dict(format="png", fromSurface=True))
            (work / f"exp4-locator-{layout}.png").write_bytes(
                base64.b64decode(shot["data"])
            )
        call("Emulation.setTouchEmulationEnabled", dict(enabled=True, maxTouchPoints=1))
        tap = js(
            "(()=>{const b=document.querySelector('#panel-exposure_150 .reconstructions img').getBoundingClientRect(),s=Math.min(b.width/480,b.height/270);return {x:b.left+(b.width-480*s)/2+200.5*s,y:b.top+(b.height-270*s)/2+110.5*s}})()"
        )
        js(
            "window.locatorExpected=null;document.addEventListener('click',event=>window.locatorExpected=HeatmapPixels.pointAt(event.target,event,480,270),{once:true,capture:true})"
        )
        call(
            "Input.dispatchTouchEvent",
            dict(type="touchStart", touchPoints=[dict(id=0, **tap)]),
        )
        call("Input.dispatchTouchEvent", dict(type="touchEnd", touchPoints=[]))
        wait_for("window.locatorExpected!==null")
        point = js("window.locatorExpected")
        assert (
            js(
                "[...document.querySelectorAll('#panel-exposure_150 .image-locator-marker')].map(e=>e.dataset.point)"
            )
            == [f"{point['x']},{point['y']}"] * 13
        )
        call("Emulation.setTouchEmulationEnabled", dict(enabled=False))
        js(
            "document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}))"
        )
        assert js("document.querySelectorAll('.image-locator-marker').length") == 0
        assert js(
            "[...document.querySelectorAll('#panel-exposure_150 img')].every(e=>e.style.width===''&&e.style.height===''&&e.style.left==='')"
        )
        js("document.querySelector('#tab-gaussian').click()")
        js(
            "for(const id of ['average','gaussian']){const input=document.querySelector('#learningConditions input[value='+id+']');input.checked=true;input.dispatchEvent(new Event('change'));}"
        )
        for layout, width, height in [("desktop", 1440, 1100), ("mobile", 390, 844)]:
            call(
                "Emulation.setDeviceMetricsOverride",
                dict(
                    width=width, height=height, deviceScaleFactor=1, mobile=width < 500
                ),
            )
            for section in ("learningCurves", "panel-gaussian"):
                tab = "overview" if section == "learningCurves" else "gaussian"
                js(
                    f"document.querySelector('#tab-{tab}').click();document.querySelector('#{section}').scrollIntoView({{behavior:'instant'}})"
                )
                time.sleep(0.3)
                assert js("document.documentElement.scrollWidth<=window.innerWidth+1")
                if section == "learningCurves":
                    assert js(
                        "document.querySelector('#learning-ssim').getBoundingClientRect().width / document.querySelector('#learning-ssim').viewBox.baseVal.width * 14 >= 11"
                    )
                else:
                    assert js(
                        "document.querySelector('#panel-gaussian .reconstructions img').getBoundingClientRect().width > document.querySelector('#panel-gaussian .inputs img').getBoundingClientRect().width * 1.2"
                    )
                shot = call(
                    "Page.captureScreenshot", dict(format="png", fromSurface=True)
                )
                (work / f"exp4-{section}-{layout}.png").write_bytes(
                    base64.b64decode(shot["data"])
                )
                if section == "panel-gaussian":
                    for class_name in ("errors", "uncertainty-section"):
                        js(
                            f"document.querySelector('#panel-gaussian .{class_name}').scrollIntoView({{behavior:'instant'}})"
                        )
                        time.sleep(0.15)
                        shot = call(
                            "Page.captureScreenshot",
                            dict(format="png", fromSurface=True),
                        )
                        (work / f"exp4-{class_name}-{layout}.png").write_bytes(
                            base64.b64decode(shot["data"])
                        )
        assert not errors, errors
        print(
            "PASS: existing video comparisons; Exp4 maps, metrics, and learning controls; the shared square locator matches previous experiments; image sizes/content and metrics stay unchanged; common positions, edge bounds, clearing, mouse/mobile taps; desktop/mobile layout; no JavaScript errors."
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
