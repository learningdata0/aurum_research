import argparse
from datetime import datetime, timedelta
from pathlib import Path
import numpy as np
import pandas as pd


SYMBOL_PROFILES = {
    "US100": {"base_price": 19500.0, "daily_vol": 0.012, "tick_size": 0.25},
    "XAUUSD": {"base_price": 2650.0, "daily_vol": 0.010, "tick_size": 0.01},
    "US30": {"base_price": 42000.0, "daily_vol": 0.009, "tick_size": 1.0},
}


def generate_bars(symbol: str, days: int = 30) -> pd.DataFrame:
    profile = SYMBOL_PROFILES.get(symbol.upper(), {"base_price": 100.0, "daily_vol": 0.01, "tick_size": 0.01})
    base_price = profile["base_price"]
    daily_vol = profile["daily_vol"]
    tick_size = profile["tick_size"]

    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)

    records = []
    current_date = start_date
    current_price = base_price

    # Generate each trading day (skip weekends)
    while current_date <= end_date:
        if current_date.weekday() < 5:  # Monday to Friday
            # Generate M1 bars from 13:00 to 19:00 UTC (covering NY session 14:30 - 17:00)
            day_start = datetime(current_date.year, current_date.month, current_date.day, 13, 0, 0)
            # Minute by minute
            for minute_offset in range(360):
                bar_time = day_start + timedelta(minutes=minute_offset)
                m = bar_time.hour * 60 + bar_time.minute
                # Session volatility multiplier: peak during 14:30 - 16:30
                if 14 * 60 + 30 <= m <= 16 * 60 + 30:
                    vol_factor = 2.5
                else:
                    vol_factor = 0.8

                sigma = (daily_vol / np.sqrt(360)) * vol_factor * current_price
                price_delta = np.random.normal(0, sigma)
                candle_range = abs(np.random.normal(0, sigma * 1.3)) + 2 * tick_size

                o = current_price
                c = o + price_delta
                h = max(o, c) + abs(np.random.normal(0, candle_range * 0.4))
                l = min(o, c) - abs(np.random.normal(0, candle_range * 0.4))
                vol = int(np.random.poisson(150 * vol_factor))

                # Round to tick size
                o = round(o / tick_size) * tick_size
                h = round(h / tick_size) * tick_size
                l = round(l / tick_size) * tick_size
                c = round(c / tick_size) * tick_size
                h = max(h, o, c)
                l = min(l, o, c)

                records.append({
                    "time": bar_time.strftime("%Y-%m-%d %H:%M:%S"),
                    "open": round(o, 2 if tick_size >= 0.01 else 4),
                    "high": round(h, 2 if tick_size >= 0.01 else 4),
                    "low": round(l, 2 if tick_size >= 0.01 else 4),
                    "close": round(c, 2 if tick_size >= 0.01 else 4),
                    "tick_volume": vol,
                })
                current_price = c
        current_date += timedelta(days=1)

    return pd.DataFrame(records)


def main():
    p = argparse.ArgumentParser(description="Generate realistic synthetic M1 data for AURUM backtesting.")
    p.add_argument("--symbol", choices=["US100", "XAUUSD", "US30"], default="US100")
    p.add_argument("--days", type=int, default=45, help="Number of trading days to simulate")
    p.add_argument("--out", default=None, help="Output CSV path (default: data/<symbol>_M1.csv)")
    a = p.parse_args()

    out_path = Path(a.out) if a.out else Path(f"data/{a.symbol}_M1.csv")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"Generating {a.days} days of synthetic M1 data for {a.symbol}...")
    df = generate_bars(a.symbol, a.days)
    df.to_csv(out_path, index=False)
    print(f"Generated {len(df):,} bars -> {out_path}")


if __name__ == "__main__":
    main()
