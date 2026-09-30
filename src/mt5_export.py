import argparse
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path


def load_env(env_path: Path) -> dict:
    env = {}
    if env_path.exists():
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip().strip("\"'")
    return env


def main():
    p = argparse.ArgumentParser(description="Export historical bars from MetaTrader 5.")
    p.add_argument("--symbol", required=True, help="Symbol to export (e.g., US100, XAUUSD, US30)")
    p.add_argument("--days", type=int, default=730, help="Number of historical days to fetch (default: 730)")
    p.add_argument("--timeframe", choices=["M1", "M5", "M15", "H1", "D1"], default="M1", help="Timeframe (default: M1)")
    p.add_argument("--out", required=True, help="Output CSV path (e.g. data/US100_M1.csv)")
    p.add_argument("--server", default=None, help="MT5 Server name (default from .env)")
    p.add_argument("--login", type=int, default=None, help="MT5 Login ID (default from .env)")
    p.add_argument("--password", default=None, help="MT5 Password (default from .env)")
    p.add_argument("--path", default=None, help="Path to terminal64.exe (optional)")
    a = p.parse_args()

    # Load defaults from .env if present
    env_file = Path(__file__).resolve().parent.parent / ".env"
    env = load_env(env_file)

    server = a.server or os.environ.get("MT5_SERVER") or env.get("MT5_SERVER")
    login = a.login or (int(os.environ.get("MT5_LOGIN")) if os.environ.get("MT5_LOGIN") else None) or (int(env.get("MT5_LOGIN")) if env.get("MT5_LOGIN") else None)
    password = a.password or os.environ.get("MT5_PASSWORD") or env.get("MT5_PASSWORD")
    terminal_path = a.path or os.environ.get("MT5_PATH") or env.get("MT5_PATH")

    try:
        import MetaTrader5 as mt5
    except ImportError:
        print("\n[ERROR] The 'MetaTrader5' Python package is not available or not supported on this platform.", file=sys.stderr)
        print(f"Current OS: {sys.platform}. MetaTrader5 Python API requires Windows or a Wine-based Python environment.", file=sys.stderr)
        print("\n[RECOMMENDATION FOR MACOS USERS]:", file=sys.stderr)
        print("Use the provided MQL5 script located at 'src/mql5/AurumExport.mq5'.", file=sys.stderr)
        print("Copy it to your MT5 Terminal 'MQL5/Scripts' directory, run it on your chart, and it will export the exact CSV needed.\n", file=sys.stderr)
        sys.exit(1)

    import pandas as pd

    tf_map = {
        "M1": mt5.TIMEFRAME_M1,
        "M5": mt5.TIMEFRAME_M5,
        "M15": mt5.TIMEFRAME_M15,
        "H1": mt5.TIMEFRAME_H1,
        "D1": mt5.TIMEFRAME_D1,
    }

    init_kwargs = {}
    if terminal_path:
        init_kwargs["path"] = terminal_path
    if login and password and server:
        init_kwargs["login"] = login
        init_kwargs["password"] = password
        init_kwargs["server"] = server
        print(f"Initializing MT5 connection with server: {server}, login: {login}...")
    else:
        print("Initializing MT5 with default active terminal session...")

    if not mt5.initialize(**init_kwargs):
        raise RuntimeError(f"MT5 initialize failed: {mt5.last_error()}")

    if login and password and server:
        authorized = mt5.login(login=login, password=password, server=server)
        if not authorized:
            raise RuntimeError(f"MT5 login failed for account {login} on {server}: {mt5.last_error()}")
        print(f"Successfully logged into account {login} on {server}.")

    target_symbol = a.symbol
    if not mt5.symbol_select(target_symbol, True):
        # Try finding similar symbol names in broker market watch
        all_symbols = [s.name for s in mt5.symbols_get() or []]
        matches = [s for s in all_symbols if target_symbol.upper() in s.upper()]
        if matches:
            target_symbol = matches[0]
            print(f"Original symbol '{a.symbol}' not found. Matched broker symbol '{target_symbol}'.")
            mt5.symbol_select(target_symbol, True)
        else:
            raise RuntimeError(f"Cannot select {a.symbol} or any matching symbol: {mt5.last_error()}")

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=a.days)
    print(f"Fetching {a.days} days of {a.timeframe} data for {target_symbol} from {start.date()} to {end.date()}...")

    rates = mt5.copy_rates_range(target_symbol, tf_map[a.timeframe], start, end)
    mt5.shutdown()

    if rates is None or len(rates) == 0:
        raise RuntimeError("No rates returned. Check broker symbol name, internet connection, and available history.")

    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    keep = [c for c in ["time", "open", "high", "low", "close", "tick_volume"] if c in df.columns]
    out_dir = Path(a.out).parent
    out_dir.mkdir(parents=True, exist_ok=True)
    df[keep].to_csv(a.out, index=False)
    print(f"Successfully exported {len(df):,} bars -> {a.out}")


if __name__ == "__main__":
    main()
