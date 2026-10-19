"""Exercise raw-demo loading, pixel values, study switching and curve tooltips."""
import base64,functools,http.server,json,os,signal,socket,subprocess,sys,tempfile,threading,time,urllib.request,shutil
from pathlib import Path
import websocket
REPO=Path(__file__).resolve().parents[1]
ASSETS=Path.home()/'.local/share/convrml-raw-demo-20261019/assets'
class Handler(http.server.SimpleHTTPRequestHandler):
 def translate_path(self,path):
  if path.startswith('/raw-assets/'):
   result=(ASSETS/path.split('?',1)[0][len('/raw-assets/'):]).resolve()
   return str(result) if result.is_relative_to(ASSETS.resolve()) else '/dev/null'
  return super().translate_path(path)
 def log_message(self,*args):pass

def main(base=None):
 server=None
 if not base:
  server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Handler,directory=str(REPO)))
  threading.Thread(target=server.serve_forever,daemon=True).start();base=f'http://127.0.0.1:{server.server_address[1]}/'
 log=open('/tmp/raw_demo_chrome.log','w')
 with socket.socket() as available:available.bind(('127.0.0.1',0));port=available.getsockname()[1]
 profile=tempfile.mkdtemp(prefix='raw-demo-browser-')
 p=subprocess.Popen(['/Applications/Google Chrome.app/Contents/MacOS/Google Chrome','--headless=new','--disable-gpu','--window-size=1440,1100','--no-first-run','--disable-background-networking',f'--remote-debugging-port={port}',f'--remote-allow-origins=http://localhost:{port}','--user-data-dir='+profile,'about:blank'],stdout=log,stderr=log,start_new_session=True)
 try:
  for _ in range(100):
   try:tabs=[t for t in json.load(urllib.request.urlopen(f'http://localhost:{port}/json')) if t.get('type')=='page'];assert tabs;break
   except Exception:time.sleep(.2)
  ws=websocket.create_connection(tabs[0]['webSocketDebuggerUrl'],origin=f'http://localhost:{port}',timeout=60);seq=0;errors=[]
  def call(method,params=None):
   nonlocal seq
   seq+=1;ws.send(json.dumps(dict(id=seq,method=method,params=params or {})))
   while True:
    result=json.loads(ws.recv())
    if result.get('method')=='Runtime.exceptionThrown':errors.append(result)
    if result.get('id')==seq:
     assert 'error' not in result,result
     return result.get('result',{})
  def js(code):
   result=call('Runtime.evaluate',dict(expression=code,returnByValue=True,awaitPromise=True))
   assert 'exceptionDetails' not in result,result
   return result.get('result',{}).get('value')
  call('Runtime.enable');call('Network.enable');call('Network.setCacheDisabled',{'cacheDisabled':True});call('Emulation.setDeviceMetricsOverride',dict(width=1440,height=1100,deviceScaleFactor=1,mobile=False))
  call('Page.navigate',{'url':base+'raw-diffusercam/?study=clean&example=0'})
  def wait_ready(prefix):
   for _ in range(300):
    text=js("document.querySelector('#status')?.textContent||''")
    if text.startswith(prefix):return text
    if text.startswith('Could not'):raise RuntimeError(text)
    time.sleep(.2)
   raise RuntimeError('Loading timeout: '+text)
  print(wait_ready('1 / '),flush=True)
  assert js("!document.querySelector('#pixelInspector').open && !document.querySelector('#calibrationDetails').open")
  for study in ['clean','corrupted']:
   if study=='corrupted':js("document.querySelector('#study').value='corrupted';document.querySelector('#study').dispatchEvent(new Event('change'))");wait_ready('2 / ')
   assert js("document.querySelectorAll('#historyPlots .plot').length")==2
   assert js("document.querySelectorAll('#intervalPlots .plot').length")==2
   assert js("document.querySelectorAll('#aggregateRows tr').length")==2
   assert js("document.querySelectorAll('#matrix canvas').length")==10
   assert js("[...document.querySelectorAll('#matrix canvas')].filter(c=>c.getBoundingClientRect().width>0).length")==6
   js("document.querySelector('#showBounds').click()")
   assert js("[...document.querySelectorAll('#matrix canvas')].filter(c=>c.getBoundingClientRect().width>0).length")==10
   js("document.querySelector('#showBounds').click()")
   assert js("document.querySelector('#measurement').width===480 && document.querySelector('#measurement').height===270")
   assert js("""(()=>{for(const plot of document.querySelectorAll('.plot')){const hit=plot.querySelector('.epoch-hit');hit.dispatchEvent(new PointerEvent('pointerenter'));const tip=plot.querySelector('.tooltip');if(tip.hidden||!tip.textContent.includes('QUTCC')||!tip.textContent.includes('Im2im')||!tip.textContent.includes('Epoch'))throw Error('hover comparison missing');hit.focus();hit.dispatchEvent(new KeyboardEvent('keydown',{key:'ArrowRight',bubbles:true}));if(tip.hidden)throw Error('keyboard tooltip hidden');plot.dispatchEvent(new PointerEvent('pointerleave'));if(!tip.hidden)throw Error('tooltip failed to hide')}return true})()""")
   js("document.querySelector('#target').dispatchEvent(new MouseEvent('click',{clientX:850,clientY:480,bubbles:true}))")
   assert js("document.querySelector('#pixelInspector').open")
   assert js("""(()=>{const row=document.querySelector('#pixelRows tr'),cells=[...row.querySelectorAll('td')].slice(1).map(n=>Number(n.textContent)),N=example.width*example.height,k=point.y*example.width+point.x,m=example.models.qutcc,mean=a=>[0,1,2].reduce((s,c)=>s+a[c*N+k],0)/3,truth=[0,1,2].reduce((s,c)=>s+example.target[c*N+k]/255,0)/3,mae=[0,1,2].reduce((s,c)=>s+Math.abs(example.target[c*N+k]/255-m.prediction[c*N+k]),0)/3,expected=[mean(m.prediction),mean(m.lower),mean(m.upper),mae,mean(m.upper)-mean(m.lower)];return cells.every((v,i)=>Math.abs(v-expected[i])<.000001)})()""")
   js("document.querySelector('#next').click()");print(study,wait_ready('2 / ' if study=='clean' else '3 / '),flush=True)
   assert js("Number(new URL(location.href).searchParams.get('example'))===index")
   assert js("[...document.querySelectorAll('[data-demo-route]')].every(a=>Number(new URL(a.href).searchParams.get('example'))===index)")
   if study=='clean':
    assert js("""(()=>{const row=data.studies.clean.qutcc.evaluations.find(r=>r.epoch===20);if(row.status==='complete')return true;const plot=document.querySelector('#intervalPlots .plot'),hit=plot.querySelector('[data-epoch=\"20\"]');hit.dispatchEvent(new PointerEvent('pointerenter'));const text=plot.querySelector('.tooltip').textContent;if(row.reference){if(!text.includes('Native, uncalibrated'))throw Error('Native reference missing label')}else{if(!plot.querySelector('svg').textContent.includes('×')||!text.includes('Calibration failed'))throw Error('Epoch-20 calibration failure marker missing')}return true})()""")
   js("document.querySelector('#matrix').scrollIntoView()")
   shot=call('Page.captureScreenshot',dict(format='png',fromSurface=True,captureBeyondViewport=False));Path(f'/tmp/raw_demo_{study}.png').write_bytes(base64.b64decode(shot['data']))
   js("document.querySelector('#historyPlots').scrollIntoView()")
   shot=call('Page.captureScreenshot',dict(format='png',fromSurface=True,captureBeyondViewport=False));Path(f'/tmp/raw_demo_{study}_curves.png').write_bytes(base64.b64decode(shot['data']))
  assert not errors,errors
  print('Raw demo: image pairing, exact pixel values, both studies, all curves and hover/keyboard comparisons passed.',flush=True)
 finally:
  try:os.killpg(p.pid,signal.SIGTERM);p.wait(timeout=10)
  except ProcessLookupError:pass
  if server:server.shutdown();server.server_close()
  log.close();shutil.rmtree(profile,ignore_errors=True)
if __name__=='__main__':main(sys.argv[1] if len(sys.argv)>1 else None)
