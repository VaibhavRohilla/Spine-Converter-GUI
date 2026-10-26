"""Optional B5 embedding proof; no desktop application or sandbox overrides."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

try:
    import PySide6
    from PySide6.QtCore import QTimer, QUrl
    from PySide6.QtWebEngineCore import (
        QWebEnginePage, QWebEngineProfile, QWebEngineUrlRequestInterceptor,
        QWebEngineUrlRequestInfo,
    )
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWidgets import QApplication
except ImportError as exc:
    print(json.dumps({'status':'BLOCKED','missing_dependency':str(exc)}))
    raise SystemExit(2)

from fnx_spine_forge.viewer.protocol import ViewerRequest
from fnx_spine_forge.viewer.server import ViewerServer
from fnx_spine_forge.viewer.service import ViewerService
from fnx_spine_forge.viewer.verification import VerificationService
from fnx_spine_forge.json_types import decode_json_object

output=Path(sys.argv[1] if len(sys.argv)>1 else 'docs/evidence/B4/qt')
if output.exists():
    raise SystemExit('Choose a fresh evidence directory; existing Qt evidence is preserved.')
asset=ViewerService().prepare(Path('viewer/fixtures/4.2'),'spineboy-pro.json')
server=ViewerServer((asset,),Path('viewer/dist'))
url=server.start()
app=QApplication(sys.argv)
profile=QWebEngineProfile()

class LocalOnly(QWebEngineUrlRequestInterceptor):
    def interceptRequest(self, info:QWebEngineUrlRequestInfo)->None:
        target=info.requestUrl()
        if target.scheme()=='blob':
            return
        if target.scheme()!='http' or target.host()!='127.0.0.1' or target.port()!=server.http.server_port:
            info.block(True)

interceptor=LocalOnly(profile)
profile.setUrlRequestInterceptor(interceptor)
view=QWebEngineView()
page=QWebEnginePage(profile,view)
view.setPage(page)
view.resize(900,850)
view.show()
view.load(QUrl(url+'frame.html?index=0'))
started=time.monotonic()
phase='loading'
session=''
sequence=0
capture=None
report={'status':'RUNNING','PySide6':PySide6.__version__,'off_the_record':profile.isOffTheRecord(),'sandbox_overrides':False}
commands=[('SET_ANIMATION',{'name':'walk','mix':0}),('SET_VIEWPORT',{'width':512,'height':512,'pixelRatio':2}),('SEEK',{'seconds':.5}),('CAPTURE_FRAME',{}),('DISPOSE',{})]
inflight=False

def finish(status:str,error:str|None=None)->None:
    global phase
    phase='finished'
    report['status']=status
    if error:
        report['error']=error
    output.mkdir(parents=True,exist_ok=True)
    (output/'embedding.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report),flush=True)
    view.close()
    page.deleteLater()
    QTimer.singleShot(100,app.quit)

def ready(value:object)->None:
    global phase,session,inflight
    inflight=False
    if not isinstance(value,str) or not value:
        return
    info=json.loads(value)
    if info.get('state')=='FAILED':
        finish('FAILED','Runtime failed in Qt WebEngine')
    elif info.get('state') in ('READY','PAUSED'):
        session=info['sessionId']
        phase='commands'

def replies(value:object)->None:
    global phase,sequence,inflight,capture
    inflight=False
    if not isinstance(value,str):
        return
    for reply in json.loads(value):
        if not reply['success']:
            finish('FAILED',str(reply['diagnostics']))
            return
        if commands[sequence][0]=='CAPTURE_FRAME':
            capture=decode_json_object(json.dumps(reply['result']),'Qt capture')
            VerificationService().record_capture(asset,capture,output/'capture')
            report['capture_sha256']=capture['sha256']
            report['width']=capture['width']
            report['height']=capture['height']
            report['dpr']=capture['dpr']
        sequence+=1
        if sequence==len(commands):
            report['cleanup']='DISPOSE acknowledged'
            report['communication']='versioned commands and asynchronous reply polling'
            finish('PASSED')
        else:
            phase='commands'

def submitted(value:object)->None:
    global inflight,phase
    inflight=False
    if value is not True:
        finish('FAILED','Typed bridge rejected submission')
    else:
        phase='waiting'

def tick()->None:
    global inflight,phase
    if phase=='finished' or inflight:
        return
    if time.monotonic()-started>45:
        finish('FAILED','Qt renderer/bridge timed out')
        return
    inflight=True
    if phase=='loading':
        page.runJavaScript('window.fnxViewer ? JSON.stringify({...window.fnxViewer.info(),sessionId:window.fnxViewer.sessionId}) : ""',ready)
    elif phase=='commands':
        command,payload=commands[sequence]
        request={'protocolVersion':1,'sessionId':session,'requestId':f'qt-{sequence}','command':command,'payload':payload}
        serialized=json.dumps(json.dumps(ViewerRequest.decode(json.dumps(request)).to_dict()))
        page.runJavaScript('window.fnxBridge.submit('+serialized+')',submitted)
    elif phase=='waiting':
        page.runJavaScript('window.fnxBridge.takeReplies()',replies)

timer=QTimer()
timer.timeout.connect(tick)
timer.start(100)
try:
    app.exec()
finally:
    server.close()
    profile.deleteLater()
raise SystemExit(0 if report['status']=='PASSED' else 1)
