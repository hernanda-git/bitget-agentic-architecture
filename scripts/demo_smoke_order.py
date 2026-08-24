"""One-shot demo smoke order. Refuses live product type and auto-closes.

Run only with DEMO_SMOKE_CONFIRM=1. Secret values are never printed.
"""
from __future__ import annotations
import base64, hashlib, hmac, json, os, time
from urllib.parse import urlencode
import httpx

BASE='https://api.bitget.com'
PRODUCT='SUSDT-FUTURES'
SYMBOL='SXRPSUSDT'

def load_env():
    for line in open('.env'):
        line=line.strip()
        if line and not line.startswith('#') and '=' in line:
            k,v=line.split('=',1); os.environ.setdefault(k,v)

def sign_headers(path, method='GET', body='', demo=False):
    ts=str(int(time.time()*1000)); pre=f'{ts}{method}{path}{body}'
    sig=base64.b64encode(hmac.new(os.environ['BITGET_API_SECRET'].encode(),pre.encode(),hashlib.sha256).digest()).decode()
    h={'ACCESS-KEY':os.environ['BITGET_API_KEY'],'ACCESS-SIGN':sig,'ACCESS-TIMESTAMP':ts,'ACCESS-PASSPHRASE':os.environ['BITGET_PASSPHRASE'],'Content-Type':'application/json','locale':'en-US'}
    if demo: h['paptrading']='1'
    return h

def req(client, method, path, body=None, demo=False):
    payload=json.dumps(body,separators=(',',':')) if body else ''
    r=client.request(method, BASE+path, content=payload or None, headers=sign_headers(path,method,payload,demo), timeout=15)
    data=r.json()
    if r.status_code != 200 or data.get('code')!='00000':
        raise RuntimeError(f"BITGET_DEMO_ERROR http={r.status_code} code={data.get('code')} msg={data.get('msg')}")
    return data.get('data')

def main():
    load_env()
    if os.environ.get('DEMO_SMOKE_CONFIRM')!='1': raise RuntimeError('DEMO_SMOKE_CONFIRM=1 required')
    if os.environ.get('BITGET_PRODUCT_TYPE') != PRODUCT: raise RuntimeError('demo lock refused product type')
    if os.environ.get('BITGET_WITHDRAWALS_ENABLED','0') not in ('0','false','False'): raise RuntimeError('withdrawal lock failed')
    client=httpx.Client()
    ticker=client.get(BASE+'/api/v2/mix/market/ticker',params={'productType':PRODUCT,'symbol':SYMBOL},timeout=15).json()
    if ticker.get('code')!='00000': raise RuntimeError(f"ticker error {ticker.get('code')}")
    price=float(ticker['data'][0]['lastPr'])
    entry=round(price,3); sl=round(price*0.99,3); tp=round(price*1.01,3)
    oid=f'agentic-demo-{int(time.time())}'
    body={'symbol':SYMBOL,'productType':PRODUCT,'marginMode':'crossed','marginCoin':'SUSDT','size':'4','side':'buy','orderType':'market','force':'ioc','tradeSide':'open','clientOid':oid,'presetStopLossPrice':str(sl),'presetStopSurplusPrice':str(tp)}
    placed=req(client,'POST','/api/v2/mix/order/place-order',body,demo=False)
    order_id=str((placed or {}).get('orderId') or '')
    if not order_id: raise RuntimeError('no order id returned')
    time.sleep(1)
    pos=req(client,'GET','/api/v2/mix/position/all-position?productType='+PRODUCT+'&symbol='+SYMBOL)
    rows=pos if isinstance(pos,list) else []
    open_rows=[r for r in rows if float(r.get('total') or 0)>0]
    if not open_rows: raise RuntimeError('order returned but no demo position read back')
    p=open_rows[0]; size=str(p.get('total')); side=str(p.get('holdSide') or 'buy')
    close_oid=f'{oid}-close'
    close_body={'symbol':SYMBOL,'productType':PRODUCT,'marginMode':'crossed','marginCoin':'SUSDT','size':size,'side':'sell' if side=='buy' else 'buy','orderType':'market','force':'ioc','tradeSide':'close','clientOid':close_oid,'reduceOnly':'YES'}
    closed=req(client,'POST','/api/v2/mix/order/place-order',close_body,demo=False)
    time.sleep(1)
    final=req(client,'GET','/api/v2/mix/position/all-position?productType='+PRODUCT+'&symbol='+SYMBOL)
    remaining=sum(float(r.get('total') or 0) for r in (final if isinstance(final,list) else []))
    print(json.dumps({'status':'DEMO_ORDER_CLOSED','product_type':PRODUCT,'symbol':SYMBOL,'quantity':size,'entry_reference':entry,'stop_loss':sl,'take_profit':tp,'order_id_present':bool(order_id),'close_order_id_present':bool((closed or {}).get('orderId')),'remaining_quantity':remaining,'protection_fields':{k:p.get(k) for k in ('stopLoss','takeProfit','liquidationPrice') if k in p}},sort_keys=True))

if __name__=='__main__': main()
