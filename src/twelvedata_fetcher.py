from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
import urllib.error
import urllib.parse
import urllib.request
import pandas as pd


BASE_URL = "https://api.twelvedata.com"

# Default symbol mappings for Twelve Data API
# Note: For US Indices on Twelve Data free plan, ETF proxies (QQQ, DIA) provide reliable 1min data.
SYMBOL_MAP = {
    "US100": "QQQ",       # Invesco QQQ Trust (Nasdaq-100 proxy) or IXIC
    "US30": "DIA",        # SPDR Dow Jones Industrial Average ETF (Dow 30 proxy) or DJI
    "XAUUSD": "XAU/USD",  # Spot Gold vs US Dollar
    "EURUSD": "EUR/USD",  # Euro vs US Dollar
}


def load_api_key(env_path: str = ".env") -> str:
    """Reads TWELVE_DATA_API_KEY from environment or .env file."""
    api_key = os.environ.get("TWELVE_DATA_API_KEY")
    if api_key:
        return api_key.strip()

    p = Path(env_path)
    if p.exists():
        with open(p, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("TWELVE_DATA_API_KEY="):
                    val = line.split("=", 1)[1].strip().strip('"').strip("'")
                    if val:
                        return val

    return ""


class TwelveDataFetcher:
    """
    Client for Twelve Data API (https://twelvedata.com/docs/introduction/quickstart).
    Supports fetching M1 historical time series, real-time quotes, and live price feeds.
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or load_api_key()

    def _request(self, endpoint: str, params: Dict[str, Any]) -> Dict[str, Any]:
        if not self.api_key:
            raise ValueError(
                "Missing Twelve Data API Key. Please add TWELVE_DATA_API_KEY to your .env file "
                "or pass it directly to TwelveDataFetcher(api_key='...').\n"
                "Get a free API key at: https://twelvedata.com/pricing"
            )

        query_params = {"apikey": self.api_key, **params}
        encoded_query = urllib.parse.urlencode(query_params)
        url = f"{BASE_URL}/{endpoint}?{encoded_query}"

        req = urllib.request.Request(
            url,
            headers={"User-Agent": "AURUM-Research-Engine/0.4"}
        )

        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            err_msg = e.read().decode("utf-8")
            raise RuntimeError(f"Twelve Data HTTP Error {e.code}: {err_msg}")
        except urllib.error.URLError as e:
            raise RuntimeError(f"Twelve Data Connection Error: {e.reason}")

        if isinstance(data, dict):
            if data.get("status") == "error":
                code = data.get("code", "unknown")
                msg = data.get("message", "unknown error")
                raise RuntimeError(f"Twelve Data API Error [{code}]: {msg}")

        return data

    def get_mapped_symbol(self, symbol: str) -> str:
        sym_clean = symbol.strip().upper()
        return SYMBOL_MAP.get(sym_clean, sym_clean)

    def fetch_time_series(
        self,
        symbol: str,
        interval: str = "1min",
        outputsize: int = 5000,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        timezone: str = "America/New_York"
    ) -> pd.DataFrame:
        """
        Fetches M1 time series candles from Twelve Data API.
        Returns DataFrame with columns: ['time', 'open', 'high', 'low', 'close', 'tick_volume'].
        """
        twelve_symbol = self.get_mapped_symbol(symbol)
        params: Dict[str, Any] = {
            "symbol": twelve_symbol,
            "interval": interval,
            "outputsize": min(outputsize, 5000),
            "timezone": timezone
        }
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date

        data = self._request("time_series", params)

        values = data.get("values", [])
        if not values:
            raise ValueError(f"No time series candles returned for symbol {twelve_symbol}.")

        df = pd.DataFrame(values)
        # Standardize columns to AURUM format
        df = df.rename(columns={"datetime": "time", "volume": "tick_volume"})
        if "tick_volume" not in df.columns:
            df["tick_volume"] = 1.0

        for col in ["open", "high", "low", "close", "tick_volume"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        df["time"] = pd.to_datetime(df["time"])
        # Twelve Data returns newest first; sort ascending
        df = df.sort_values("time").reset_index(drop=True)
        return df[["time", "open", "high", "low", "close", "tick_volume"]]

    def fetch_quote(self, symbol: str) -> Dict[str, Any]:
        """Fetches latest real-time quote snapshot."""
        twelve_symbol = self.get_mapped_symbol(symbol)
        return self._request("quote", {"symbol": twelve_symbol})

    def fetch_price(self, symbol: str) -> float:
        """Fetches current real-time price."""
        twelve_symbol = self.get_mapped_symbol(symbol)
        data = self._request("price", {"symbol": twelve_symbol})
        return float(data.get("price", 0.0))

    def sync_and_save(
        self,
        symbol: str,
        output_dir: str = "data",
        outputsize: int = 5000
    ) -> Path:
        """
        Fetches latest M1 bars from Twelve Data and merges them into data/{symbol}_M1.csv.
        Avoids duplicates and preserves full historical depth.
        """
        out_path = Path(output_dir) / f"{symbol}_M1.csv"
        new_df = self.fetch_time_series(symbol=symbol, interval="1min", outputsize=outputsize)

        if out_path.exists():
            existing_df = pd.read_csv(out_path)
            existing_df["time"] = pd.to_datetime(existing_df["time"])
            combined = pd.concat([existing_df, new_df], ignore_index=True)
            combined = combined.drop_duplicates(subset=["time"]).sort_values("time").reset_index(drop=True)
        else:
            combined = new_df

        out_path.parent.mkdir(parents=True, exist_ok=True)
        combined.to_csv(out_path, index=False)
        print(f"✅ Successfully synced {len(combined)} bars for {symbol} -> {out_path}")
        return out_path


def main():
    parser = argparse.ArgumentParser(description="AURUM Twelve Data Fetcher CLI")
    parser.add_argument("--symbol", type=str, default="US100", help="Asset symbol (US100, US30, XAUUSD, etc.)")
    parser.add_argument("--interval", type=str, default="1min", help="Candle interval (1min, 5min, 15min, etc.)")
    parser.add_argument("--size", type=int, default=500, help="Number of candles (max 5000)")
    parser.add_argument("--quote", action="store_true", help="Fetch real-time quote snapshot")
    parser.add_argument("--price", action="store_true", help="Fetch latest live price")
    parser.add_argument("--sync", action="store_true", help="Sync and save M1 candles to data/ directory")
    parser.add_argument("--apikey", type=str, default=None, help="Twelve Data API Key")

    args = parser.parse_args()

    fetcher = TwelveDataFetcher(api_key=args.apikey)

    if args.quote:
        q = fetcher.fetch_quote(args.symbol)
        print(json.dumps(q, indent=2))
    elif args.price:
        p = fetcher.fetch_price(args.symbol)
        print(f"{args.symbol} Current Price: {p}")
    elif args.sync:
        fetcher.sync_and_save(args.symbol, outputsize=args.size)
    else:
        df = fetcher.fetch_time_series(args.symbol, interval=args.interval, outputsize=args.size)
        print(df.tail(10).to_string(index=False))


if __name__ == "__main__":
    main()
