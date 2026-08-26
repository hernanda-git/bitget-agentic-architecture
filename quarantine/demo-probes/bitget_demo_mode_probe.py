"""Read-only probe for Bitget's Demo API-key mode: normal product + paptrading=1."""
from __future__ import annotations
import base64,hashlib,hmac,json,os,time
from urllib.parse import urlencode
import httpx

def main():
    for line in open('.env'):
        line=line.strip()
        if line and not line.startswith('#') and '=' in line:
            k,v=line.split('=',1); os.environ.setdefault(k,v)
    product='USDT-FUTURES'; path='/api/v2/mix/account/accounts'; rp=path+'?'+urlencode({'productType':product})
    ts=str(int(time.time()*1000)); sig=base64.b64encode(hmac.new(os.environ['BITGET_API_SECRET'].encode(),(ts+'GET'+rp).encode(),hashlib.sha256).digest()).decode()
    h={'ACCESS-KEY':os.environ['BITGET_API_KEY'],'ACCESS-SIGN':sig,'ACCESS-TIMESTAMP':ts,'ACCESS-PASSPHRASE':os.environ['BITGET_PASSPHRASE'],'Content-Type':'application/json','locale':'en-US','paptrading':'1'}
    r=httpx.get('https://api.bitget.com'+rp,headers=h,timeout=15); p=r.json()
    if p.get('code')!='00000': raise RuntimeError(f"DEMO_ENV_READ_ERROR code={p.get('code')} msg={p.get('msg')}")
    rows=p.get('data') or []; safe=[]
    for x in rows:
        safe.append({k:x.get(k) for k in ('marginCoin','available','equity','usdtEquity') if k in x})
    print(json.dumps({'status':'DEMO_API_MODE_READ_OK','product_type':product,'paptrading':'1','rows':safe},sort_keys=True))
if __name__=='__main__': main()
