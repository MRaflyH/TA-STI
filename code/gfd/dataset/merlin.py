"""MERLIN cloud-to-ground strikes from the KSC Weather Archive.

    python3 -m gfd.dataset.merlin --start 2018-01-01 --end 2024-12-31
    python3 -m gfd.dataset.merlin --self-test

The archive is geo-restricted. A browser VPN extension is not enough -- this
goes through the OS network stack, so the VPN has to be device-level. The
script says so if the response comes back blocked.
"""

from __future__ import annotations

import argparse
import datetime as dt
import string
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from .. import config as cfg

# kscweather serves a chain certifi can't complete, so curl works where requests
# raises CERTIFICATE_VERIFY_FAILED. truststore points Python at the Keychain.
# Optional; --use-curl and --ca-bundle are the fallbacks.
try:
    import truststore

    truststore.inject_into_ssl()
    _TRUSTSTORE = True
except ImportError:
    _TRUSTSTORE = False

BASE = "https://kscweather.ksc.nasa.gov/wxarchive/MerlinCloudToGround"

# No documented API. The export URL carries the query in one token: two
# 7-character datetime blocks then the search filters.
#
#     /Export/BXHPAAABXHPMAAAAAABaAAA
#             \_____/\_____/\_______/
#              start    end   filters
#
# Each block is [century][year%100][month][day][hour][minute][second], one
# base-62 digit each. Reverse-engineered by diffing controlled searches, so
# self_test() runs before any bulk download -- a change to the site's encoding
# would otherwise fetch the wrong period silently.
ALPHABET = string.ascii_uppercase + string.ascii_lowercase + string.digits
VALUE = {c: i for i, c in enumerate(ALPHABET)}
FILTER_TAIL = "AAAABaAAA"

# Longer than this and the site refuses: "not greater than 30 Days".
MAX_WINDOW_DAYS = 29

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36"
)

STRIKE_COLUMNS = ["timestamp", "lat", "lon", "peak_current_ka", "polarity", "source"]


# ==========================================================================
# Token codec
# ==========================================================================
def encode_datetime(when: dt.datetime) -> str:
    fields = [
        when.year // 100 - 19,  # 1900s -> 0, 2000s -> 1
        when.year % 100,
        when.month,
        when.day,
        when.hour,
        when.minute,
        when.second,
    ]
    for f in fields:
        if not 0 <= f < len(ALPHABET):
            raise ValueError(f"field {f} out of range for {when!r}")
    return "".join(ALPHABET[f] for f in fields)


def decode_datetime(block: str) -> dt.datetime:
    if len(block) != 7:
        raise ValueError(f"expected 7 characters, got {block!r}")
    c, y, mo, d, h, mi, s = (VALUE[ch] for ch in block)
    return dt.datetime(1900 + c * 100 + y, mo, d, h, mi, s)


def make_token(start: dt.datetime, end: dt.datetime) -> str:
    return encode_datetime(start) + encode_datetime(end) + FILTER_TAIL


def parse_token(token: str) -> tuple[dt.datetime, dt.datetime, str]:
    return decode_datetime(token[:7]), decode_datetime(token[7:14]), token[14:]


def self_test() -> bool:
    """Re-derive every token captured from the live site."""
    cases = [
        ("BXHPAAABXHPMAAAAAABaAAA", "2023-07-15 00:00:00", "2023-07-15 12:00:00"),
        ("BXHPAAABXHPMABAAAABaAAA", "2023-07-15 00:00:00", "2023-07-15 12:00:01"),
        ("BXHPAAABXHPMBAAAAABaAAA", "2023-07-15 00:00:00", "2023-07-15 12:01:00"),
        ("BXHPAAABXHPNAAAAAABaAAA", "2023-07-15 00:00:00", "2023-07-15 13:00:00"),
        ("BXHPAAABXHQMAAAAAABaAAA", "2023-07-15 00:00:00", "2023-07-16 12:00:00"),
        ("BXHPAABBXHPMAAAAAABaAAA", "2023-07-15 00:00:01", "2023-07-15 12:00:00"),
        ("BaJBAt5BaJCAt5AAAABaAAA", "2026-09-01 00:45:57", "2026-09-02 00:45:57"),
    ]
    ok = True
    for expected, s, e in cases:
        got = make_token(dt.datetime.fromisoformat(s), dt.datetime.fromisoformat(e))
        if got != expected:
            ok = False
            print(f"  FAIL {s} .. {e}  {got}  expected {expected}")
        else:
            print(f"  ok   {s} .. {e}  {got}")
    print("self-test:", "all tokens reproduced" if ok else "MISMATCH -- do not download")
    return ok


# ==========================================================================
# Download
# ==========================================================================
def windows(start: dt.date, end: dt.date, days: int = MAX_WINDOW_DAYS):
    """Split a date range into windows within the site's 30-day cap."""
    out = []
    cursor = start
    while cursor <= end:
        stop = min(cursor + dt.timedelta(days=days - 1), end)
        out.append(
            (
                dt.datetime.combine(cursor, dt.time(0, 0, 0)),
                dt.datetime.combine(stop, dt.time(23, 59, 59)),
            )
        )
        cursor = stop + dt.timedelta(days=1)
    return out


def make_session(ca_bundle: str | None = None) -> requests.Session:
    """A session that has visited the site once, so it carries its cookies."""
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "en"})
    if ca_bundle:
        s.verify = ca_bundle
    try:
        s.get(BASE, timeout=(30, 120)).raise_for_status()
    except requests.exceptions.SSLError as exc:
        raise SystemExit(
            f"TLS verification failed: {exc}\n"
            "curl reaches this site and Python can't, so the chain needs the system\n"
            "trust store. In order of preference:\n"
            "  pip install truststore\n"
            "  pip install --upgrade certifi\n"
            "  --use-curl\n"
            "  --ca-bundle /path/to/chain.pem"
        ) from exc
    return s


def curl_get(url: str, referer: str | None = None, timeout: int = 300) -> str:
    """Fetch through curl, which trusts the Keychain."""
    cmd = ["curl", "-sS", "--fail", "--max-time", str(timeout),
           "-A", USER_AGENT, "-H", "Accept-Language: en"]
    if referer:
        cmd += ["-H", f"Referer: {referer}"]
    cmd.append(url)
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"curl failed ({proc.returncode}): {proc.stderr.strip()}")
    return proc.stdout


def looks_like_csv(text: str) -> bool:
    head = text.lstrip()[:200].lower()
    return head.startswith('"date"') or head.startswith("date,")


def fetch_window(
    session: requests.Session | None,
    start: dt.datetime,
    end: dt.datetime,
    out_dir: Path,
    overwrite: bool = False,
    timeout: int = 300,
    retries: int = 3,
) -> Path | None:
    """One window. None if it failed."""
    token = make_token(start, end)
    dest = out_dir / f"merlin_{start:%Y%m%d}_{end:%Y%m%d}.csv"

    if dest.exists() and not overwrite:
        print(f"  cached {dest.name}")
        return dest

    url = f"{BASE}/Export/{token}"
    referer = f"{BASE}/Search/{token}/Page/1"

    text = None
    for attempt in range(1, retries + 1):
        try:
            if session is None:
                text = curl_get(url, referer, timeout)
            else:
                resp = session.get(url, headers={"Referer": referer}, timeout=(30, timeout))
                resp.raise_for_status()
                text = resp.text
            break
        except Exception as exc:  # noqa: BLE001 -- retry anything
            if attempt == retries:
                print(f"  !! failed after {retries} attempts: {type(exc).__name__}: {exc}")
                return None
            wait = 5 * attempt
            print(f"  .. attempt {attempt} failed ({type(exc).__name__}), retry in {wait}s")
            time.sleep(wait)

    if not looks_like_csv(text):
        raw = out_dir / f"FAILED_{start:%Y%m%d}_{end:%Y%m%d}.html"
        raw.write_text(text, encoding="utf-8")
        print(f"  !! not CSV, saved {raw.name}: {' '.join(text.split())[:180]}")
        if "not greater than 30" in text:
            print("     -> window too long, lower --window-days")
        elif "denied" in text.lower() or "access" in text.lower():
            print("     -> looks geo-blocked. Is the DEVICE vpn on, not just the browser?")
        return None

    dest.write_text(text, encoding="utf-8")
    print(f"  saved  {dest.name} ({text.count(chr(10)) - 1:,} strikes)")
    return dest


def download_range(
    start: dt.date,
    end: dt.date,
    out_dir: str | Path = cfg.RAW_MERLIN_DIR,
    window_days: int = MAX_WINDOW_DAYS,
    pause_s: float = 3.0,
    overwrite: bool = False,
    use_curl: bool = False,
    ca_bundle: str | None = None,
) -> list[Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    wins = windows(start, end, window_days)
    print(f"{len(wins)} windows of up to {window_days} days, {start} .. {end}")

    if use_curl:
        print("transport: curl")
        session = None
    else:
        print("transport: requests +", "truststore" if _TRUSTSTORE else "certifi")
        session = make_session(ca_bundle)

    saved = []
    for i, (a, b) in enumerate(wins, 1):
        print(f"[{i}/{len(wins)}] {a:%Y-%m-%d} .. {b:%Y-%m-%d}")
        p = fetch_window(session, a, b, out_dir, overwrite=overwrite)
        if p:
            saved.append(p)
        if i < len(wins):
            time.sleep(pause_s)

    print(f"\n{len(saved)} of {len(wins)} windows saved to {out_dir}")
    if len(saved) < len(wins):
        print("re-run to retry the failures; successful windows are cached")
    return saved


# ==========================================================================
# Load
# ==========================================================================
def load_file(path: str | Path) -> pd.DataFrame:
    path = Path(path)
    df = pd.read_csv(path, dtype=str)
    df = df.rename(columns=lambda c: str(c).strip())

    missing = {"Date", "Time", "Latitude", "Longitude"} - set(df.columns)
    if missing:
        raise ValueError(f"{path.name}: missing columns {sorted(missing)}")

    # 7 fractional digits; pandas stops at microseconds.
    time_str = df["Time"].str.replace(r"(\.\d{6})\d+", r"\1", regex=True)
    ts = pd.to_datetime(
        df["Date"].str.strip() + " " + time_str.str.strip(),
        format="%m/%d/%Y %H:%M:%S.%f",
        errors="coerce",
    )

    signal = pd.to_numeric(df.get("Signal Strength"), errors="coerce")
    out = pd.DataFrame(
        {
            "timestamp": ts,
            "lat": pd.to_numeric(df["Latitude"], errors="coerce"),
            "lon": pd.to_numeric(df["Longitude"], errors="coerce"),
            "peak_current_ka": signal,
            "polarity": np.where(signal >= 0, "positive", "negative"),
            "source": f"merlin:{path.name}",
        }
    )
    out = out.dropna(subset=["timestamp", "lat", "lon"])
    out["timestamp"] = out["timestamp"].dt.tz_localize("UTC")
    return out[STRIKE_COLUMNS].reset_index(drop=True)


def load(directory: str | Path = cfg.RAW_MERLIN_DIR, pattern: str = "*.csv") -> pd.DataFrame:
    """Every export. Windows overlap, so exact duplicates are dropped."""
    files = sorted(Path(directory).glob(pattern))
    if not files:
        raise FileNotFoundError(f"no MERLIN exports matching {pattern!r} under {directory}")

    strikes = pd.concat([load_file(f) for f in files], ignore_index=True)
    before = len(strikes)
    strikes = strikes.drop_duplicates(subset=["timestamp", "lat", "lon", "peak_current_ka"])
    if before - len(strikes):
        print(f"[merlin] dropped {before - len(strikes):,} duplicates across overlapping exports")

    return strikes.sort_values("timestamp").reset_index(drop=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--start", help="first date, YYYY-MM-DD")
    ap.add_argument("--end", help="last date, YYYY-MM-DD")
    ap.add_argument("--out", default=str(cfg.RAW_MERLIN_DIR))
    ap.add_argument("--window-days", type=int, default=MAX_WINDOW_DAYS)
    ap.add_argument("--pause", type=float, default=3.0)
    ap.add_argument("--overwrite", action="store_true")
    ap.add_argument("--use-curl", action="store_true",
                    help="fetch via curl when Python raises CERTIFICATE_VERIFY_FAILED")
    ap.add_argument("--ca-bundle", default=None)
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the windows and URLs without downloading")
    args = ap.parse_args()

    if args.self_test:
        sys.exit(0 if self_test() else 1)

    if not (args.start and args.end):
        ap.error("--start and --end are required unless --self-test is given")

    start = dt.date.fromisoformat(args.start)
    end = dt.date.fromisoformat(args.end)

    if not self_test():
        sys.exit("token codec failed its self-test, aborting")
    print()

    if args.dry_run:
        for a, b in windows(start, end, args.window_days):
            print(f"{a:%Y-%m-%d} .. {b:%Y-%m-%d}  {BASE}/Export/{make_token(a, b)}")
        return

    download_range(start, end, args.out, args.window_days, args.pause,
                   args.overwrite, args.use_curl, args.ca_bundle)


if __name__ == "__main__":
    main()
