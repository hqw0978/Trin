#!/usr/bin/env python3
"""A股市场广度 TRIN — 数据源：新浪财经。

东方财富 push2 接口会拒绝海外/机房 IP，GitHub Actions 上必然失败，
所以这里改用新浪的行情列表接口（每页 100 只，翻页取全市场）。
只用标准库，不需要 pip install。
"""
import json
import time
import urllib.request
from datetime import datetime, timedelta, timezone

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)
BASE = "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php"
# 市场广度（TRIN）的通行口径是沪深两市，不含北交所；
# 想算全市场就把这里改成 True。
INCLUDE_BSE = False
CST = timezone(timedelta(hours=8))

# 别把数据源用秃了：两次真实抓取之间至少隔这么久，且只在开市时段抓。
# workflow 每 10 分钟触发一次，但绝大多数会在这里直接跳过。
MIN_REFRESH_MINUTES = 30
PAGE_SLEEP = 0.3


def get(url, referer="https://finance.sina.com.cn/", timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": referer})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def trading_time(now=None):
    """A 股开市时段（含集合竞价前后几分钟的缓冲）。"""
    now = now or datetime.now(CST)
    if now.weekday() >= 5:
        return False
    hm = now.hour * 60 + now.minute
    return (9 * 60 + 25 <= hm <= 11 * 60 + 35) or (12 * 60 + 55 <= hm <= 15 * 60 + 5)


def last_update():
    """上一份 data.json 的时间；没有或解析不了就返回 None。"""
    try:
        with open("data.json", encoding="utf-8") as f:
            return datetime.strptime(json.load(f)["time"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=CST)
    except Exception:
        return None


def market_rows():
    """全市场 A 股（含北交所）逐页拉取。"""
    count = int(json.loads(get(f"{BASE}/Market_Center.getHQNodeStockCount?node=hs_a")))
    rows, page = [], 1
    while len(rows) < count and page <= 80:
        url = (
            f"{BASE}/Market_Center.getHQNodeData?page={page}&num=100"
            "&sort=symbol&asc=1&node=hs_a&symbol=&_s_r_a=page"
        )
        try:
            batch = json.loads(get(url))
        except Exception as exc:  # 单页失败不推翻整次采集
            print(f"page {page} skipped: {exc}")
            batch = []
        if not batch:
            break
        rows.extend(batch)
        page += 1
        time.sleep(PAGE_SLEEP)
    if not INCLUDE_BSE:
        rows = [r for r in rows if not str(r.get("symbol", "")).startswith("bj")]
    return count, rows


def index_quote():
    """上证指数：当前价与涨跌幅。"""
    raw = get("https://hq.sinajs.cn/list=sh000001").decode("gbk", "replace")
    fields = raw.split('"')[1].split(",")
    prev_close, price = float(fields[2]), float(fields[3])
    return price, (price - prev_close) / prev_close * 100


def fetch():
    now = datetime.now(CST)
    if not trading_time(now):
        print(f"{now:%H:%M} 非交易时段，跳过（保持收盘数据）")
        return
    prev = last_update()
    if prev is not None:
        age = (now - prev).total_seconds() / 60
        if 0 <= age < MIN_REFRESH_MINUTES:
            print(f"上次更新才 {age:.0f} 分钟，跳过（阈值 {MIN_REFRESH_MINUTES} 分钟）")
            return

    count, rows = market_rows()

    adv = dec = flat = 0
    up_vol = down_vol = 0.0
    amount = 0.0

    for row in rows:
        try:
            chg = float(row.get("changepercent") or 0)
            vol = float(row.get("volume") or 0)
            amt = float(row.get("amount") or 0)
        except (TypeError, ValueError):
            continue
        amount += amt
        if chg > 0:
            adv += 1
            up_vol += vol
        elif chg < 0:
            dec += 1
            down_vol += vol
        else:
            flat += 1

    total = adv + dec + flat
    if total == 0:
        raise SystemExit("没有取到任何行情数据")
    if adv == 0 or dec == 0 or down_vol == 0:
        raise SystemExit(f"数据不完整，暂不计算：up={adv} down={dec} downVol={down_vol}")

    idx_price, idx_chg_val = index_quote()

    result = {
        "adv": adv,
        "dec": dec,
        "flat": flat,
        "total": total,
        "upPct": adv / total * 100,
        "downPct": dec / total * 100,
        "flatPct": flat / total * 100,
        "trin": (adv / dec) / (up_vol / down_vol),
        "totalAmt": amount / 100000000,
        "idxPrice": idx_price,
        "idxChg": f"{idx_chg_val:+.2f}%",
        "time": now.strftime("%Y-%m-%d %H:%M:%S"),
        "source": "sina",
        "universe": "沪深A股" if not INCLUDE_BSE else "沪深京A股",
    }

    # 数字没变就不落盘，免得每分钟一个提交
    try:
        with open("data.json", encoding="utf-8") as f:
            old = json.load(f)
        same = all(old.get(k) == result[k] for k in ("adv", "dec", "flat", "trin", "totalAmt"))
        if same:
            print("数据与上一份一致，不写文件")
            return
    except FileNotFoundError:
        pass

    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"rows={len(rows)}/{count} total={total}")
    print(f"TRIN={result['trin']:.3f}, up={adv}, down={dec}, flat={flat}")
    print(f"INDEX={idx_price:.2f} {result['idxChg']}, amount={result['totalAmt']:.0f}亿")


if __name__ == "__main__":
    fetch()
