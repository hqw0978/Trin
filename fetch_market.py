
import json
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import akshare as ak
import pandas as pd

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)

def main():
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    print(f"开始抓取 A 股行情：{now.isoformat()}")

    # 请求一次全市场行情，避免重复请求增加限流风险
    df = ak.stock_zh_a_spot_em()

    if df is None or df.empty:
        raise RuntimeError("行情接口返回空数据")

    required = ["代码", "名称", "最新价", "涨跌幅", "成交量"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise RuntimeError(
            f"行情字段发生变化，缺少：{missing}；"
            f"实际字段：{list(df.columns)}"
        )

    df = df.copy()
    df["代码"] = df["代码"].astype(str).str.strip()
    df = df[df["代码"].str.fullmatch(r"\d{6}", na=False)]

    for col in ["最新价", "涨跌幅", "成交量"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # 排除没有有效价格、涨跌幅或成交量的记录
    df = df.dropna(subset=["最新价", "涨跌幅", "成交量"])
    df = df[(df["最新价"] > 0) & (df["成交量"] >= 0)]

    if len(df) < 1000:
        raise RuntimeError(
            f"有效股票仅 {len(df)} 只，数据可能不完整，拒绝发布"
        )

    up = df[df["涨跌幅"] > 0]
    down = df[df["涨跌幅"] < 0]
    flat = df[df["涨跌幅"] == 0]

    up_vol = float(up["成交量"].sum())
    down_vol = float(down["成交量"].sum())

    trin = None
    if len(up) and len(down) and up_vol > 0 and down_vol > 0:
        trin = (len(up) / len(down)) / (up_vol / down_vol)

    result = {
        "date": now.strftime("%Y-%m-%d"),
        "updated_at": now.isoformat(),
        "source": "AkShare / Eastmoney",
        "status": "ok",
        "method": "按个股涨跌幅归类其成交量",
        "volume_unit": "数据源原始单位，尚未独立核验",
        "stock_count": int(len(df)),
        "advancing_count": int(len(up)),
        "declining_count": int(len(down)),
        "unchanged_count": int(len(flat)),
        "advancing_volume": up_vol,
        "declining_volume": down_vol,
        "volume_ratio_up_down": (
            up_vol / down_vol if down_vol > 0 else None
        ),
        "trin": trin,
        "warnings": [
            "需核验全市场覆盖范围及成交量单位",
            "涨跌幅按接口返回值分类，平盘单独统计",
            "这不是逐笔主动买卖量"
        ]
    }

    latest_path = DATA_DIR / "latest.json"
    latest_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    history_path = DATA_DIR / "history.json"
    history = []
    if history_path.exists():
        try:
            history = json.loads(history_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            history = []

    # 同一交易日重复运行时更新当日记录，不重复累加
    history = [
        item for item in history
        if item.get("date") != result["date"]
    ]
    history.append(result)
    history = sorted(history, key=lambda item: item["date"])[-365:]

    history_path.write_text(
        json.dumps(history, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    print(json.dumps(result, ensure_ascii=False, indent=2))
    print("成功生成 data/latest.json 和 data/history.json")

if __name__ == "__main__":
    main()
