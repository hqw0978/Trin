import requests
import json
from datetime import datetime

def fetch():
    url = (
        "https://push2.eastmoney.com/api/qt/clist/get"
        "?pn=1&pz=6000&po=1&np=1&fltt=2&invt=2&fid=f3"
        "&fs=m:0+t:6,m:0+t:80,m:0+t:81,m:1+t:2,m:1+t:23"
        "&fields=f12,f14,f2,f3,f5,f6"
    )
    headers = {
        "User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0.0.0 Safari/537.36",
        "Referer":"https://data.eastmoney.com/"
    }
    resp = requests.get(url, headers=headers, timeout=15)
    data = resp.json()

    adv = 0
    dec = 0
    flat = 0
    up_vol = 0
    down_vol = 0
    amount = 0

    for row in data['data']['diff']:
        chg_pct = float(row['f3'])
        vol = float(row['f5'])
        amt = float(row['f6'])
        amount += amt
        if chg_pct > 0:
            adv +=1
            up_vol += vol
        elif chg_pct < 0:
            dec +=1
            down_vol += vol
        else:
            flat +=1

    total = adv + dec + flat
    upPct = adv / total *100
    downPct = dec / total *100
    flatPct = flat / total *100

    ad_ratio = adv / dec
    vol_ratio = up_vol / down_vol
    trin = ad_ratio / vol_ratio

    # 上证指数
    idx_url = "https://push2.eastmoney.com/api/qt/stock/get?secid=1.000001&fields=f43,f170"
    idx_resp = requests.get(idx_url,headers=headers,timeout=15)
    idx_data = idx_resp.json()
    idxPrice = float(idx_data['data']['f43'])/100
    idxChgVal = float(idx_data['data']['f170'])/100
    idxChg = f"{idxChgVal:+.2f}%"

    result = {
        "adv":adv,
        "dec":dec,
        "flat":flat,
        "total":total,
        "upPct":upPct,
        "downPct":downPct,
        "flatPct":flatPct,
        "trin":trin,
        "totalAmt": amount / 100000000,
        "idxPrice":idxPrice,
        "idxChg": idxChg,
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    with open("data.json","w",encoding="utf-8") as f:
        json.dump(result,f,ensure_ascii=False,indent=2)
    print("data.json generated successfully")
    print(f"TRIN={trin:.3f}, up={adv}, down={dec}")

if __name__ == "__main__":
    fetch()