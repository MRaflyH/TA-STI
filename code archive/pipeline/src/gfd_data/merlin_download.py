r"""Bulk-download MERLIN cloud-to-ground exports from the KSC Weather Archive.

The archive has no documented API, but its search/export URLs carry the whole
query in a single opaque-looking token::

    /wxarchive/MerlinCloudToGround/Export/BXHPAAABXHPMAAAAAABaAAA
                                          \_____/\_____/\_______/
                                           start    end   filters

Each 7-character block is one datetime, one base-62 digit per field:

    [century][year mod 100][month][day][hour][minute][second]

with the alphabet ``A=0..Z=25, a=26..z=51, 0=52..9=61``. So ``BXHPAAA`` is
century 1, year 23, month 7, day 15, 00:00:00 -> 2023-07-15 00:00:00. The
trailing nine characters are the other search filters at their defaults and are
reproduced verbatim.

This was derived by diffing six tokens generated from controlled searches
(+1 second, +1 minute, +1 hour, +1 day on each endpoint); ``self_test()``
re-checks all six, so a change to the site's encoding fails loudly rather than
silently downloading the wrong period.

NETWORK NOTE: the archive is geo-restricted. A browser-extension VPN is not
enough -- this runs through the OS network stack, so a device-level VPN must be
active. The script says so if the response comes back blocked.

Usage::

    python -m gfd_data.merlin_download --start 2023-01-01 --end 2024-12-31
    python -m gfd_data.merlin_download --self-test
"""

from __future__ import annotations

import argparse
import datetime as dt
import string
import subprocess
import sys
import time
from pathlib import Path

import requests

from . import config as cfg

# macOS ships its trust roots in the Keychain, but Python verifies against
# certifi's bundle instead. Some government sites -- kscweather among them --
# serve a chain that certifi alone cannot complete, so curl succeeds where
# requests raises CERTIFICATE_VERIFY_FAILED. truststore makes Python use the
# same system trust store curl does. Optional: if it is not installed the
# script still runs, and --ca-bundle / --use-curl remain as fallbacks.
try:
    import truststore

    truststore.inject_into_ssl()
    _TRUSTSTORE = True
except ImportError:
    _TRUSTSTORE = False

BASE = "https://kscweather.ksc.nasa.gov/wxarchive/MerlinCloudToGround"
ALPHABET = string.ascii_uppercase + string.ascii_lowercase + string.digits
VALUE = {c: i for i, c in enumerate(ALPHABET)}

# The nine trailing characters, unchanged across every observed token. They
# hold the non-date search filters at their default values.
FILTER_TAIL = "AAAABaAAA"

# The site rejects anything longer with "Please enter a Date Range not greater
# than 30 Days." 29 leaves a margin against off-by-one at the boundaries.
MAX_WINDOW_DAYS = 29

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36"
)


# ==========================================================================
# Token codec
# ==========================================================================
def encode_datetime(when: dt.datetime) -> str:
    """Encode one datetime as a 7-character token block."""
    fields = [
        when.year // 100 - 19,   # century index: 1900s -> 0, 2000s -> 1
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
    """Decode a 7-character token block back to a datetime."""
    if len(block) != 7:
        raise ValueError(f"expected 7 characters, got {block!r}")
    c, y, mo, d, h, mi, s = (VALUE[ch] for ch in block)
    return dt.datetime(1900 + c * 100 + y, mo, d, h, mi, s)


def make_token(start: dt.datetime, end: dt.datetime) -> str:
    """Build the full search/export token for a datetime range."""
    return encode_datetime(start) + encode_datetime(end) + FILTER_TAIL


def parse_token(token: str) -> tuple[dt.datetime, dt.datetime, str]:
    """Inverse of :func:`make_token`. Useful for checking a URL by hand."""
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
        start = dt.datetime.fromisoformat(s)
        end = dt.datetime.fromisoformat(e)
        got = make_token(start, end)
        mark = "ok  " if got == expected else "FAIL"
        if got != expected:
            ok = False
        print(f"  {mark} {s} .. {e}  {got}" + ("" if got == expected else f"  expected {expected}"))
    print("self-test:", "all tokens reproduced" if ok else "MISMATCH -- do not bulk download")
    return ok


# ==========================================================================
# Download
# ==========================================================================
def windows(
    start: dt.date, end: dt.date, days: int = MAX_WINDOW_DAYS
) -> list[tuple[dt.datetime, dt.datetime]]:
    """Split a date range into non-overlapping windows within the site's cap."""
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
        r = s.get(f"{BASE}", timeout=(30, 120))
        r.raise_for_status()
    except requests.exceptions.SSLError as exc:
        raise SystemExit(
            f"TLS verification failed: {exc}\n\n"
            "curl can reach this site but Python cannot, which means the chain\n"
            "cannot be completed from certifi's bundle alone. In order of\n"
            "preference:\n"
            "  1. pip install truststore   (uses the macOS Keychain, like curl)\n"
            "  2. pip install --upgrade certifi\n"
            "  3. --use-curl               (shell out to curl for transport)\n"
            "  4. --ca-bundle /path/to/chain.pem\n"
        ) from exc
    return s


def curl_get(url: str, referer: str | None = None, timeout: int = 300) -> str:
    """Fetch via the curl binary, which trusts the macOS Keychain.

    A fallback for the case where the system trusts the site but Python does
    not. Slower and cookie-less, but it works when nothing else does.
    """
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
    """Download one window. Returns the saved path, or None if it was skipped."""
    token = make_token(start, end)
    dest = out_dir / f"merlin_{start:%Y%m%d}_{end:%Y%m%d}.csv"

    if dest.exists() and not overwrite:
        print(f"  cached  {dest.name}")
        return dest

    url = f"{BASE}/Export/{token}"
    referer = f"{BASE}/Search/{token}/Page/1"

    text = None
    for attempt in range(1, retries + 1):
        try:
            if session is None:
                text = curl_get(url, referer, timeout)
            else:
                resp = session.get(url, headers={"Referer": referer},
                                   timeout=(30, timeout))
                resp.raise_for_status()
                text = resp.text
            break
        except Exception as exc:  # noqa: BLE001 -- report and retry anything
            wait = 5 * attempt
            if attempt == retries:
                print(f"  !! failed after {retries} attempts: "
                      f"{type(exc).__name__}: {exc}")
                return None
            print(f"  .. attempt {attempt} failed ({type(exc).__name__}), "
                  f"retrying in {wait}s")
            time.sleep(wait)

    class _R:  # keep the rest of the function unchanged
        pass

    resp = _R()
    resp.text = text

    if not looks_like_csv(resp.text):
        raw = out_dir / f"FAILED_{start:%Y%m%d}_{end:%Y%m%d}.html"
        raw.write_text(resp.text, encoding="utf-8")
        snippet = " ".join(resp.text.split())[:180]
        print(f"  !! not CSV for {start:%Y-%m-%d}..{end:%Y-%m-%d}; saved {raw.name}")
        print(f"     {snippet}")
        if "not greater than 30" in resp.text:
            print("     -> window too long; lower --window-days")
        elif "access" in resp.text.lower() or "denied" in resp.text.lower():
            print("     -> looks geo-blocked; is the DEVICE vpn on, not just the browser?")
        return None

    dest.write_text(resp.text, encoding="utf-8")
    rows = resp.text.count("\n") - 1
    print(f"  saved   {dest.name}  ({rows:,} strikes, {len(resp.text)/1e6:.2f} MB)")
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
    """Download every window covering ``start``..``end``."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    wins = windows(start, end, window_days)
    print(f"{len(wins)} windows of up to {window_days} days, {start} .. {end}")

    if use_curl:
        print("transport: curl (system trust store)")
        session = None
    else:
        print(f"transport: requests"
              + (" + truststore (system trust store)" if _TRUSTSTORE else " + certifi"))
        session = make_session(ca_bundle)

    saved = []
    for i, (a, b) in enumerate(wins, 1):
        print(f"[{i}/{len(wins)}] {a:%Y-%m-%d} .. {b:%Y-%m-%d}")
        p = fetch_window(session, a, b, out_dir, overwrite=overwrite)
        if p:
            saved.append(p)
        if i < len(wins):
            time.sleep(pause_s)  # the archive is a small public service

    print(f"\n{len(saved)} of {len(wins)} windows saved to {out_dir}")
    if len(saved) < len(wins):
        print("re-run to retry the failures; successful windows are cached")
    return saved


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--start", help="first date, YYYY-MM-DD")
    ap.add_argument("--end", help="last date, YYYY-MM-DD")
    ap.add_argument("--out", default=str(cfg.RAW_MERLIN_DIR))
    ap.add_argument("--window-days", type=int, default=MAX_WINDOW_DAYS)
    ap.add_argument("--pause", type=float, default=3.0)
    ap.add_argument("--overwrite", action="store_true")
    ap.add_argument("--use-curl", action="store_true",
                    help="fetch via the curl binary, which trusts the OS "
                         "keychain; use when Python raises "
                         "CERTIFICATE_VERIFY_FAILED but curl works")
    ap.add_argument("--ca-bundle", default=None,
                    help="path to a PEM bundle to verify against")
    ap.add_argument("--self-test", action="store_true",
                    help="check the token codec against known tokens and exit")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the windows and their URLs without downloading")
    args = ap.parse_args()

    if args.self_test:
        sys.exit(0 if self_test() else 1)

    if not (args.start and args.end):
        ap.error("--start and --end are required unless --self-test is given")

    start = dt.date.fromisoformat(args.start)
    end = dt.date.fromisoformat(args.end)

    if not self_test():
        sys.exit("token codec failed its self-test; aborting")
    print()

    if args.dry_run:
        for a, b in windows(start, end, args.window_days):
            print(f"{a:%Y-%m-%d} .. {b:%Y-%m-%d}  {BASE}/Export/{make_token(a, b)}")
        return

    download_range(start, end, args.out, args.window_days, args.pause,
                   args.overwrite, args.use_curl, args.ca_bundle)


if __name__ == "__main__":
    main()