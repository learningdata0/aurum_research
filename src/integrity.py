from __future__ import annotations

from dataclasses import dataclass, asdict
import hashlib
from pathlib import Path
from typing import Dict, Tuple
import pandas as pd


@dataclass(frozen=True)
class DatasetFingerprint:
    symbol: str
    file_path: str
    sha256_hash: str
    total_bars: int
    start_time: str
    end_time: str
    calendar_days: int
    duplicate_timestamps: int
    invalid_ohlc_bars: int
    expected_gaps: int
    unexpected_session_gaps: int
    critical_opening_range_gaps: int
    off_hour_gaps: int
    data_quality_score: float


def compute_dataset_fingerprint(
    csv_path: str | Path,
    symbol: str = "",
    target_timezone: str = "America/New_York"
) -> DatasetFingerprint:
    """
    Computes a cryptographic and statistical fingerprint of an M1 dataset.
    Classifies gaps into:
      1. EXPECTED GAPS: Weekend market closures (Fri 17:00 NY to Sun 18:00 NY) & Daily Rollovers.
      2. UNEXPECTED SESSION GAPS: Gaps during active NY cash hours (09:30 - 16:00 NY).
      3. CRITICAL OPENING RANGE GAPS: Gaps during 09:30 - 10:30 NY (Opening Range creation).
      4. OFF-HOUR GAPS: Low-volume Asian/European off-peak dropouts.

    Quality score rigorously penalizes UNEXPECTED SESSION and CRITICAL OR gaps.
    """
    p = Path(csv_path)
    if not p.exists():
        raise FileNotFoundError(f"Dataset file not found: {csv_path}")

    # 1. Compute SHA-256 hash of raw file content
    hasher = hashlib.sha256()
    with open(p, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    file_hash = hasher.hexdigest()

    # 2. Parse and analyze dataset
    df = pd.read_csv(p)
    df.columns = [str(c).lower().strip() for c in df.columns]

    total_bars = len(df)
    t = pd.to_datetime(df["time"], errors="coerce")
    valid_t = t.dropna()

    start_time = str(valid_t.min()) if not valid_t.empty else "N/A"
    end_time = str(valid_t.max()) if not valid_t.empty else "N/A"
    calendar_days = (valid_t.max() - valid_t.min()).days if not valid_t.empty else 0

    # Duplicate timestamps check
    dup_count = int(df["time"].duplicated().sum())

    # Invalid OHLC bars check
    invalid_ohlc = 0
    if all(c in df.columns for c in ["open", "high", "low", "close"]):
        h = pd.to_numeric(df["high"], errors="coerce")
        l = pd.to_numeric(df["low"], errors="coerce")
        o = pd.to_numeric(df["open"], errors="coerce")
        c = pd.to_numeric(df["close"], errors="coerce")
        invalid_mask = (h < o) | (h < c) | (l > o) | (l > c) | (l > h)
        invalid_ohlc = int(invalid_mask.sum())

    # 3. Gap Classification (Expected vs Unexpected)
    expected_gaps = 0
    unexpected_session_gaps = 0
    critical_or_gaps = 0
    off_hour_gaps = 0

    if len(valid_t) > 1:
        if valid_t.dt.tz is None:
            t_localized = valid_t.dt.tz_localize("UTC")
        else:
            t_localized = valid_t
        t_ny = t_localized.dt.tz_convert(target_timezone).sort_values().reset_index(drop=True)

        diffs = t_ny.diff()
        gap_indices = diffs[diffs > pd.Timedelta(minutes=1)].index

        for idx in gap_indices:
            prev_t = t_ny.iloc[idx - 1]
            curr_t = t_ny.iloc[idx]

            # A. Weekend Closure: Friday >= 16:30 NY to Sunday >= 17:00 NY
            is_weekend = (prev_t.weekday() == 4 and prev_t.hour >= 16) or (curr_t.weekday() == 6 and curr_t.hour >= 17)
            # B. Daily Rollover Maintenance: 17:00 - 18:00 NY
            is_rollover = (prev_t.hour in (16, 17) and curr_t.hour in (17, 18))

            if is_weekend or is_rollover:
                expected_gaps += 1
            else:
                # Active NY Trading Hours: 09:30 - 16:00 NY
                prev_min = prev_t.hour * 60 + prev_t.minute
                is_in_or = (570 <= prev_min < 630)  # 09:30 to 10:30 NY (Opening Range window)
                is_in_session = (570 <= prev_min < 960)  # 09:30 to 16:00 NY

                if is_in_or:
                    critical_or_gaps += 1
                elif is_in_session:
                    unexpected_session_gaps += 1
                else:
                    off_hour_gaps += 1

    # 4. Strict Quality Score Calculation
    # Expected gaps incur 0 penalty.
    # Critical OR gaps incur heavy penalty (-5.0 pts each).
    # Unexpected session gaps incur moderate penalty (-2.0 pts each).
    # Off-hour gaps incur minor penalty (-0.1 pts each).
    score = 100.0
    score -= critical_or_gaps * 5.0
    score -= unexpected_session_gaps * 2.0
    score -= min(10.0, off_hour_gaps * 0.1)
    score -= min(30.0, dup_count * 2.0)
    score -= min(40.0, invalid_ohlc * 5.0)

    score = max(0.0, round(score, 1))
    inferred_sym = symbol or p.stem.split("_")[0]

    return DatasetFingerprint(
        symbol=inferred_sym,
        file_path=str(p),
        sha256_hash=file_hash,
        total_bars=total_bars,
        start_time=start_time,
        end_time=end_time,
        calendar_days=calendar_days,
        duplicate_timestamps=dup_count,
        invalid_ohlc_bars=invalid_ohlc,
        expected_gaps=expected_gaps,
        unexpected_session_gaps=unexpected_session_gaps,
        critical_opening_range_gaps=critical_or_gaps,
        off_hour_gaps=off_hour_gaps,
        data_quality_score=score
    )


def print_integrity_report(fingerprints: Dict[str, DatasetFingerprint]):
    print("\n=== AURUM v0.6 DATA INTEGRITY & AUDIT REPORT ===")
    for sym, fp in fingerprints.items():
        print(f"\n[{sym}] -> {fp.file_path}")
        print(f"  SHA-256:             {fp.sha256_hash[:16]}...{fp.sha256_hash[-8:]}")
        print(f"  Total Bars:          {fp.total_bars:,} bars ({fp.calendar_days} calendar days)")
        print(f"  Date Span:           {fp.start_time} to {fp.end_time}")
        print(f"  Duplicates:          {fp.duplicate_timestamps} | Invalid OHLC: {fp.invalid_ohlc_bars}")
        print(f"  Expected Gaps:       {fp.expected_gaps} (Weekend / Daily Rollover closures)")
        print(f"  Critical OR Gaps:    {fp.critical_opening_range_gaps} (09:30-10:30 NY Opening Range)")
        print(f"  Unexpected Session:  {fp.unexpected_session_gaps} (09:30-16:00 NY Cash Session)")
        print(f"  Off-Hour Gaps:       {fp.off_hour_gaps} (Asian/European off-peak)")
        print(f"  Data Quality Score:  {fp.data_quality_score} / 100.0")
