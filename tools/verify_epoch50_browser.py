import subprocess,time,urllib.request,json,base64,os,signal
from pathlib import Path
import websocket
CHROME='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
log=open('/tmp/epoch50_chrome.log','w')
p=subprocess.Popen([CHROME,'--headless=new','--disable-gpu','--window-size=1440,1100','--no-first-run','--disable-background-networking','--remote-debugging-port=9335','--remote-allow-origins=http://localhost:9335','--user-data-dir=/tmp/epoch50_chrome_profile','about:blank'],stdout=log,stderr=log,start_new_session=True)
try:
 for _ in range(100):
  try:tabs=[t for t in json.load(urllib.request.urlopen('http://localhost:9335/json')) if t.get('type')=='page'];assert tabs;break
  except Exception:time.sleep(.2)
 ws=websocket.create_connection(tabs[0]['webSocketDebuggerUrl'],origin='http://localhost:9335',timeout=45); seq=0
 def call(method,params={}):
  global seq
  seq+=1;ws.send(json.dumps(dict(id=seq,method=method,params=params)))
  while True:
   r=json.loads(ws.recv())
   if r.get('id')==seq:
    if 'error' in r:raise RuntimeError(r)
    return r.get('result',{})
 def js(code):
  r=call('Runtime.evaluate',dict(expression=code,returnByValue=True,awaitPromise=True))
  if 'exceptionDetails' in r:raise RuntimeError(r)
  return r.get('result',{}).get('value')
 call('Emulation.setDeviceMetricsOverride',dict(width=1440,height=1100,deviceScaleFactor=1,mobile=False));call('Network.enable');call('Network.setCacheDisabled',{'cacheDisabled':True})
 import sys
 base=sys.argv[1] if len(sys.argv)>1 else 'http://127.0.0.1:8772/'
 for path in ['corrected-epoch50/?camera=rml','corrected-epoch50/?camera=diffuser']:
  if '--latest-only' in sys.argv and not path.startswith('corrected'):continue
  if '--legacy-only' in sys.argv and path.startswith('corrected'):continue
  if '--rml-only' in sys.argv and 'diffuser' in path:continue
  call('Page.navigate',{'url':base+path})
  for _ in range(150):
   state=js("document.getElementById('status')?.textContent || ''")
   if state.startswith('1 / 50'):break
   if 'Could not' in state:raise RuntimeError(state)
   time.sleep(.2)
  assert state.startswith('1 / 50'),(path,state)
  print(path, js("({status:document.getElementById('status').textContent,canvases:document.querySelectorAll('canvas').length,rows:document.querySelectorAll('#pixelRows tr').length,provenance:document.getElementById('provenance').textContent})"),flush=True)
  js("document.getElementById('next').click()")
  for _ in range(150):
   state=js("document.getElementById('status').textContent")
   if state.startswith('2 / 50'):break
   time.sleep(.2)
  assert state.startswith('2 / 50'),state
  js("document.getElementById('channel').value='1';document.getElementById('channel').dispatchEvent(new Event('change'));document.getElementById('target').dispatchEvent(new MouseEvent('click',{clientX:100,clientY:100,bubbles:true}))")
  assert js("document.querySelectorAll('#pixelRows tr').length")==js('DATASET.methods.length')
  if path.startswith('corrected'):
   if js("!!document.getElementById('qMode')"):
    before=js("({qwidth:example.models.conditioned.metrics.width,others:['im2im','ensemble10','mc_010'].map(k=>example.models[k].metrics.width)})")
    js("document.getElementById('qMode').value='scaled';document.getElementById('qMode').dispatchEvent(new Event('change'))")
    for _ in range(200):
     if js("!busy && qMode==='scaled' && document.getElementById('status').textContent.startsWith('2 / 50')"):break
     time.sleep(.2)
    after=js("({qwidth:example.models.conditioned.metrics.width,others:['im2im','ensemble10','mc_010'].map(k=>example.models[k].metrics.width)})")
    assert before['others']==after['others'],(before,after)
    assert before['qwidth']!=after['qwidth'],(before,after)
    js("document.getElementById('qMode').value='searched';document.getElementById('qMode').dispatchEvent(new Event('change'))")
    for _ in range(200):
     if js("!busy && qMode==='searched' && document.getElementById('status').textContent.startsWith('2 / 50')"):break
     time.sleep(.2)
    assert js("example.models.conditioned.metrics.width")==before['qwidth']
    assert js("document.querySelectorAll('#qComparisonRows tr').length")==3
    print('Quantile switch verified; other methods identical:',before['qwidth'],'vs',after['qwidth'],flush=True)
   if '--expected-epochs' in sys.argv:
    assert js('DATASET.epoch') == 50
   # Verify displayed endpoints and widths match underlying decoded float32 values.
   assert js("(()=>{const m=example.models.im2im,p=point.y*256+point.x;return Math.abs(m.widthRGB[N+p]-(m.upper[N+p]-m.lower[N+p]))<1e-7})()")
   print('Pixel inspection:',js("document.getElementById('pixelRows').innerText"),flush=True)
   if '--screenshot' in sys.argv:
    js("document.getElementById('matrix').scrollIntoView()")
    shot=call('Page.captureScreenshot',dict(format='png',fromSurface=True,captureBeyondViewport=False))
    Path('/tmp/epoch50_'+('diffuser' if 'diffuser' in path else 'rml')+'.png').write_bytes(base64.b64decode(shot['data']))
 print('Browser checks passed',flush=True)
finally:
 try:os.killpg(p.pid,signal.SIGTERM);p.wait(timeout=10)
 except ProcessLookupError:pass
 log.close()
