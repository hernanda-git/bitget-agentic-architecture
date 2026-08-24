from __future__ import annotations
import base64,hashlib,hmac,json,os,time
from urllib.parse import urlencode
import httpx

def main():
    for line in open('.env'):
        line=line.strip()
        if line and not line.startswith('#') and '=' in line:
            k,v=line.split('=',1); os.environ.setdefault(k,v)
    product='SUSDT-FUTURES'; path='/api/v2/mix/account/account'; rp=path+'?'+urlencode({'symbol':'SXRPSUSDT','productType':product})
    ts=str(int(time.time()*1000)); sig=base64.b64encode(hmac.new(os.environ['BITGET_API_SECRET'].encode(),(ts+'GET'+rp).encode(),hashlib.sha256).digest()).decode()
    h={'ACCESS-KEY':os.environ['BITGET_API_KEY'],'ACCESS-SIGN':sig,'ACCESS-TIMESTAMP':ts,'ACCESS-PASSPHRASE':os.environ['BITGET_PASSPHRASE'],'Content-Type':'application/json','locale':'en-US'}
    p=httpx.get('https://api.bitget.com'+rp,headers=h,timeout=15).json()
    if p.get('code')!='00000': raise RuntimeError(f"ACCOUNT_READ_ERROR code={p.get('code')} msg={p.get('msg')}")
    x=p.get('data') or {}; print(json.dumps({'status':'ACCOUNT_READ_OK','product_type':product,'posMode':x.get('posMode'),'marginMode':x.get('marginMode'),'symbol':x.get('symbol')},sort_keys=True))
if __name__=='__main__': main()
