from __future__ import annotations
import base64, hashlib, hmac, json, os, time
from urllib.parse import urlencode
import httpx

def main():
    for line in open('.env'):
        line=line.strip()
        if line and not line.startswith('#') and '=' in line:
            k,v=line.split('=',1); os.environ.setdefault(k,v)
    product=os.environ['BITGET_PRODUCT_TYPE']; assert product=='SUSDT-FUTURES'
    path='/api/v2/mix/position/all-position'; query='?'+urlencode({'productType':product,'symbol':'SXRPSUSDT'}); rp=path+query
    ts=str(int(time.time()*1000)); sig=base64.b64encode(hmac.new(os.environ['BITGET_API_SECRET'].encode(),(ts+'GET'+rp).encode(),hashlib.sha256).digest()).decode()
    h={'ACCESS-KEY':os.environ['BITGET_API_KEY'],'ACCESS-SIGN':sig,'ACCESS-TIMESTAMP':ts,'ACCESS-PASSPHRASE':os.environ['BITGET_PASSPHRASE'],'Content-Type':'application/json','locale':'en-US'}
    r=httpx.get('https://api.bitget.com'+rp,headers=h,timeout=15); p=r.json()
    if p.get('code')!='00000': raise RuntimeError(f"READONLY_POSITION_ERROR code={p.get('code')} msg={p.get('msg')}")
    rows=p.get('data') or []; open_rows=[{'symbol':x.get('symbol'),'total':x.get('total'),'holdSide':x.get('holdSide')} for x in rows if float(x.get('total') or 0)>0]
    print(json.dumps({'status':'READ_ONLY_POSITION_OK','product_type':product,'open_positions':open_rows},sort_keys=True))
if __name__=='__main__': main()
