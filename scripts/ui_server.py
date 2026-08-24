"""Standalone read-only demo dashboard server.

Only GET endpoints exist. It cannot place orders, transfer, withdraw, or modify account state.
"""
from __future__ import annotations
import base64, hashlib, hmac, json, os, time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlencode
import sys
import httpx

ROOT=Path(__file__).resolve().parents[1]
if __package__ in (None, ''):
    sys.path.insert(0, str(ROOT))
from src.ledger.sqlite import EventLedger
BASE='https://api.bitget.com'
PRODUCT='SUSDT-FUTURES'
SYMBOLS=('SBTCSUSDT','SETHSUSDT','SXRPSUSDT')

def load_env():
    path=ROOT/'.env'
    if not path.exists(): return
    for line in path.read_text().splitlines():
        line=line.strip()
        if line and not line.startswith('#') and '=' in line:
            k,v=line.split('=',1); os.environ.setdefault(k,v)

def signed_get(path, params):
    load_env(); assert os.environ.get('BITGET_PRODUCT_TYPE')==PRODUCT
    query='?'+urlencode(params); request_path=path+query; ts=str(int(time.time()*1000))
    sig=base64.b64encode(hmac.new(os.environ['BITGET_API_SECRET'].encode(),(ts+'GET'+request_path).encode(),hashlib.sha256).digest()).decode()
    headers={'ACCESS-KEY':os.environ['BITGET_API_KEY'],'ACCESS-SIGN':sig,'ACCESS-TIMESTAMP':ts,'ACCESS-PASSPHRASE':os.environ['BITGET_PASSPHRASE'],'Content-Type':'application/json','locale':'en-US'}
    response=httpx.get(BASE+request_path,headers=headers,timeout=10)
    payload=response.json()
    if response.status_code!=200 or payload.get('code')!='00000': raise RuntimeError(f"venue_read_{payload.get('code',response.status_code)}")
    return payload.get('data')

def public_get(path, params):
    response=httpx.get(BASE+path,params=params,timeout=10); payload=response.json()
    if response.status_code!=200 or payload.get('code')!='00000': raise RuntimeError(f"public_read_{payload.get('code',response.status_code)}")
    return payload.get('data')

def ledger_state():
    path=ROOT/'data'/'paper.sqlite3'
    if not path.exists(): return {'mode':'demo-readonly','paper_cycles':0,'latest_terminal':None,'protection':'IDLE','reconciliation':'UNKNOWN','events':[]}
    events=EventLedger(path).all(); terminals=[e for e in events if e['event_type']=='CYCLE_TERMINAL']; failed=[e for e in events if e['event_type']=='PROTECTION_FAILED']
    return {'mode':'demo-readonly','paper_cycles':len(terminals),'latest_terminal':terminals[-1]['payload'] if terminals else None,'protection':'DEGRADED' if failed else 'UNKNOWN','reconciliation':'SYNC' if any(e['event_type']=='POSITION_RECONCILED' and e['payload'].get('in_sync') for e in events) else 'UNKNOWN','events':events[-8:]}

def snapshot():
    accounts=signed_get('/api/v2/mix/account/accounts',{'productType':PRODUCT})
    account=next((x for x in accounts if x.get('marginCoin')=='SUSDT'),{}) if isinstance(accounts,list) else {}
    tickers=public_get('/api/v2/mix/market/tickers',{'productType':PRODUCT})
    by_symbol={x.get('symbol'):x for x in tickers if isinstance(x,dict)}
    markets=[]
    for symbol in SYMBOLS:
        row=by_symbol.get(symbol,{})
        markets.append({'symbol':symbol,'mark':row.get('lastPr'),'bid':row.get('bidPr'),'ask':row.get('askPr'),'ts':row.get('ts')})
    return {'mode':'demo-readonly','product_type':PRODUCT,'equity':account.get('usdtEquity') or account.get('equity'),'available':account.get('available'),'margin_coin':account.get('marginCoin'),'open_positions':[],'markets':markets,'updated_ms':int(time.time()*1000),'activity':[{'title':'Read-only snapshot','detail':'Demo venue account and public tickers refreshed','time':'now'}]}

class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*args,**kwargs): super().__init__(*args,directory=str(ROOT/'ui'),**kwargs)
    def do_POST(self): self.send_error(405,'Read-only dashboard')
    def do_PUT(self): self.send_error(405,'Read-only dashboard')
    def do_DELETE(self): self.send_error(405,'Read-only dashboard')
    def do_GET(self):
        if self.path=='/api/health': return self._json({'ok':True,'mode':'demo-readonly','product_type':PRODUCT,'writable':False})
        if self.path=='/api/state': return self._json(ledger_state())
        if self.path=='/api/snapshot':
            try: return self._json(snapshot())
            except Exception as exc: return self._json({'ok':False,'error':type(exc).__name__},503)
        return super().do_GET()
    def _json(self,obj,status=200):
        raw=json.dumps(obj,sort_keys=True).encode(); self.send_response(status); self.send_header('Content-Type','application/json'); self.send_header('Content-Length',str(len(raw))); self.end_headers(); self.wfile.write(raw)
    def log_message(self,fmt,*args):
        if self.path.startswith('/api/'): return
        super().log_message(fmt,*args)

def main():
    load_env(); server=ThreadingHTTPServer(('127.0.0.1',8765),Handler); print('Northline demo-readonly listening on http://127.0.0.1:8765',flush=True); server.serve_forever()
if __name__=='__main__': main()
