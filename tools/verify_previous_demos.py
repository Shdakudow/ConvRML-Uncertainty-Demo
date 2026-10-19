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
 log=open('/tmp/previous_demo_chrome.log','w')
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
  for page in ['', 'corrected-latest/', 'corrected-epoch50/']:
   for camera in ['rml','diffuser']:
    call('Page.navigate',{'url':base+page+'?camera='+camera})
    for _ in range(400):
     state=js("document.querySelector('#status')?.textContent||''")
     if state.startswith('1 / '):break
     if 'Could not' in state or 'not yet published' in state:raise RuntimeError(state)
     time.sleep(.2)
    assert state.startswith('1 / '),(page,camera,state)
    assert js("!document.querySelector('#pixelInspector').open")
    assert js("document.querySelectorAll('#pixelRows tr').length")==4
    assert js("[...document.querySelectorAll('.learning-plots')].some(e=>e.getBoundingClientRect().height>0)")
    assert js("document.querySelector('#matrix').closest('details')===null")
    js("document.querySelector('#target').dispatchEvent(new MouseEvent('click',{clientX:100,clientY:100,bubbles:true}))")
    assert js("document.querySelector('#pixelInspector').open")
    js("document.querySelector('#next').click()")
    for _ in range(300):
     state=js("document.querySelector('#status').textContent")
     if state.startswith('2 / '):break
     time.sleep(.2)
    assert state.startswith('2 / '),state
    if page:
     before=js("[...document.querySelectorAll('#matrix canvas')].filter(c=>c.getBoundingClientRect().width>0).length")
     js("document.querySelector('#boundsToggle').click()")
     assert js("[...document.querySelectorAll('#matrix canvas')].filter(c=>c.getBoundingClientRect().width>0).length")>before
     js("document.querySelector('#boundsToggle').click()")
    if page=='corrected-epoch50/':
     assert js("document.querySelectorAll('#intervalHistoryPlots .plot').length")==2
     assert js("document.querySelector('#factorRows').closest('details')!==null")
     if camera=='diffuser':
      assert js("!document.querySelector('#normalizedResults')")
      assert js("document.querySelector('#intervalHistoryPlots').getBoundingClientRect().height>0 && document.querySelector('#historyPlots').getBoundingClientRect().height>0")
      assert js("document.querySelector('#intervalHistoryPlots').textContent.includes('QUTCC · paper-style') && document.querySelector('#historyPlots').textContent.includes('QUTCC · paper-style')")
      assert js("(()=>{for(const id of ['intervalHistoryPlots','historyPlots']){for(const plot of document.querySelectorAll('#'+id+' .plot')){const hit=plot.querySelector('.epoch-hit:last-of-type'),info=JSON.parse(decodeURIComponent(hit.dataset.comparison));if(!info.rows.some(r=>r.name==='QUTCC · paper-style'&&r.value!==null))return false;hit.dispatchEvent(new PointerEvent('pointerenter'));if(!plot.querySelector('.epoch-tooltip').textContent.includes('QUTCC · paper-style'))return false}}return true})()")

      assert js("!document.querySelector('#historyPlots').textContent.includes('QUTCC adaptive · reference')")
      assert js("(()=>{const p=[...document.querySelectorAll('#intervalHistoryPlots .plot')],metrics=['width','coverage'];return p.every((plot,i)=>{const hit=plot.querySelector('.epoch-hit:last-of-type'),v=JSON.parse(decodeURIComponent(hit.dataset.comparison)).rows.find(r=>r.name==='QUTCC · paper-style').value,expected=paperStyleQutcc.evaluations.at(-1).metrics.clipped[metrics[i]]*(i===1?100:1);return Math.abs(v-expected)<1e-10})})()")

    js("window.scrollTo(0,0)")
    shot=call('Page.captureScreenshot',dict(format='png',fromSurface=True,captureBeyondViewport=False))
    Path('/tmp/previous_demo_'+(page.strip('/') or 'legacy')+'_'+camera+'.png').write_bytes(base64.b64decode(shot['data']))
    print(page or 'legacy',camera,state,'controls, curves, pixel inspector and bounds passed',flush=True)
  assert not errors,errors
 finally:
  try:os.killpg(p.pid,signal.SIGTERM);p.wait(timeout=10)
  except ProcessLookupError:pass
  if server:server.shutdown();server.server_close()
  log.close();shutil.rmtree(profile,ignore_errors=True)
if __name__=='__main__':main(sys.argv[1] if len(sys.argv)>1 else None)
