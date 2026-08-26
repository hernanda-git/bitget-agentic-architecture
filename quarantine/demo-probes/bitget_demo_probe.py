"""Read-only demo account probe. Never places orders or transfers funds."""
from __future__ import annotations
import base64, hashlib, hmac, json, os, time
from urllib.parse import urlencode
import httpx

PATH='/api/v2/mix/account/accounts'

def signed_headers(key, secret, passphrase, method, request_path, body=''):
    ts=str(int(time.time()*1000))
    prehash=f'{ts}{method.upper()}{request_path}{body}'
    sign=base64.b64encode(hmac.new(secret.encode(),prehash.encode(),hashlib.sha256).digest()).decode()
    return {'ACCESS-KEY':key,'ACCESS-SIGN':sign,'ACCESS-TIMESTAMP':ts,'ACCESS-PASSPHRASE':passphrase,'Content-Type':'application/json','locale':'en-US'}

def main():
    key=os.environ['BITGET_API_KEY']; secret=os.environ['BITGET_API_SECRET']; phrase=os.environ['BITGET_PASSPHRASE']
    product=os.environ.get('BITGET_PRODUCT_TYPE','')
    assert product=='SUSDT-FUTURES', 'demo lock refused non-demo product'
    query='?'+urlencode({'productType':product})
    request_path=PATH+query
    headers=signed_headers(key,secret,phrase,'GET',request_path)
    response=httpx.get(os.environ.get('BITGET_REST_BASE','https://api.bitget.com')+request_path,headers=headers,timeout=15)
    payload=response.json()
    if payload.get('code')!='00000':
        raise RuntimeError(f"BITGET_READONLY_ERROR http={response.status_code} code={payload.get('code')} msg={payload.get('msg')}")
    rows=payload.get('data')
    if not isinstance(rows,list): raise RuntimeError('unexpected account response')
    safe=[]
    for row in rows:
        if isinstance(row,dict):
            safe.append({k:row.get(k) for k in ('marginCoin','available','equity','usdtEquity','accountType') if k in row})
    print(json.dumps({'status':'READ_ONLY_OK','product_type':product,'rows':safe},sort_keys=True))

if __name__=='__main__': main()
