"""Smoke test for the lightning half of the pipeline. No downloads needed.

    python -m gfd_data.smoke_lightning                 # both domains
    python -m gfd_data.smoke_lightning --domain tropis
    python -m gfd_data.smoke_lightning --month 2024-01 # aggregate one month

Runs entirely on the PLN and MERLIN files already on disk. Three checks, in
increasing order of how much they will annoy you if you skip them.

1. TIMEZONE SANITY. The single most dangerous unverified assumption in the
   hourly build. config.TROPIS carries tz="Asia/Jakarta" with a VERIFY comment
   that never mattered at monthly resolution and matters enormously now: if PLN
   exports UTC and the loader localises it as Jakarta, every tropis row is
   displaced by seven hours in exactly the dimension hourly resolution exists
   to capture. The model will train happily on it and produce a plausible
   cross-domain gap that is pure artefact.

   The check is physical, not computational. Convection over West Java peaks in
   the local mid-to-late afternoon; the flash count by local hour should show a
   clear afternoon maximum. A peak in the small hours of the local morning
   means the timezone is wrong. Florida is the control: the same physics, and
   MERLIN is genuinely UTC, so its local-hour peak should also land in the
   afternoon.

2. COVERAGE. Prints every month with its day-coverage and marks which ones
   cfg.MIN_COVERAGE would drop. Read this before accepting 0.9: the gate is not
   neutral, it preferentially removes quiet months, and quiet months are the
   low-target examples the model most needs.

3. ONE MONTH, AGGREGATED. Builds the hourly cell-period table for a single
   month so the shape, the zero share and the target distribution are visible
   before committing to seven years and 589 network requests.
"""

from __future__ import annotations

import argparse

import pandas as pd

from . import config as cfg
from . import lightning as lit

LOADER = {"tropis": lit.load_pln, "subtropis": lit.load_merlin}


def _hour_histogram(strikes: pd.DataFrame, domain: cfg.Domain) -> pd.DataFrame:
    """Flash count by hour of day, in UTC and in the domain's configured tz."""
    ts = strikes["timestamp"]
    utc = ts.dt.tz_convert("UTC")
    local = ts.dt.tz_convert(domain.solar_tz)
    return pd.DataFrame(
        {
            "utc": utc.dt.hour.value_counts().reindex(range(24), fill_value=0),
            "local": local.dt.hour.value_counts().reindex(range(24), fill_value=0),
        }
    )


def _bar(n: int, peak: int, width: int = 40) -> str:
    return "#" * int(round(width * n / peak)) if peak else ""


def check_timezone(strikes: pd.DataFrame, domain: cfg.Domain) -> None:
    print(f"\n--- diurnal cycle [{domain.name}] solar_tz={domain.solar_tz} ---")
    hist = _hour_histogram(strikes, domain)
    peak_local = int(hist["local"].idxmax())
    peak_utc = int(hist["utc"].idxmax())
    top = int(hist["local"].max())

    for h in range(24):
        marker = " <-- peak" if h == peak_local else ""
        print(f"  {h:02d}:00 local  {int(hist.loc[h, 'local']):>9,}  "
              f"{_bar(int(hist.loc[h, 'local']), top)}{marker}")

    print(f"\n  peak local hour : {peak_local:02d}:00 ({domain.tz})")
    print(f"  peak UTC hour   : {peak_utc:02d}:00")

    if 12 <= peak_local <= 21:
        print("  OK -- afternoon/evening peak, consistent with convective "
              "lightning.")
    else:
        print("  !! The peak is NOT in the local afternoon. Either the "
              "configured timezone is wrong, or the source exports a different "
              "clock than assumed. Resolve this with the data provider before "
              "building anything hourly -- do not proceed on the assumption "
              "that it will average out. It will not.")


def check_coverage(strikes: pd.DataFrame, domain: cfg.Domain) -> pd.DataFrame:
    print(f"\n--- monthly coverage [{domain.name}] "
          f"gate = {cfg.MIN_COVERAGE:.0%} ---")
    cov = lit.observed_months(strikes, domain).sort_values("month")

    dropped = cov[cov["coverage"] < cfg.MIN_COVERAGE]
    for r in cov.itertuples():
        flag = "  DROPPED" if r.coverage < cfg.MIN_COVERAGE else ""
        print(f"  {r.month}  {r.observed_days:>2d}/{r.days_in_month:>2d} days  "
              f"{r.coverage:>6.1%}{flag}")

    print(f"\n  months present  : {len(cov)}")
    print(f"  months dropped  : {len(dropped)} at the current gate")
    if len(dropped):
        print(
            "  !! Check WHICH months these are before accepting the gate. If "
            "they cluster in the dry season they are your low-activity "
            "examples, and dropping them biases the target distribution "
            "upward. Lowering cfg.MIN_COVERAGE keeps them at the cost of more "
            "false zeros; there is no setting that avoids both."
        )
    return cov


def check_one_month(strikes: pd.DataFrame, domain: cfg.Domain, month: str) -> None:
    period = pd.Period(month, freq="M")
    ts = strikes["timestamp"]
    naive = lit._bin_timestamps(ts, domain)
    subset = strikes[naive.dt.to_period("M") == period]

    print(f"\n--- one-month aggregate [{domain.name}] {period} ---")
    if subset.empty:
        print(f"  no strikes in {period}; pick another month with --month")
        return

    table = lit.aggregate_gfd(subset, domain, min_coverage=0.0)
    nonzero = table.loc[table["flash_count"] > 0, "flash_count"]

    print(f"  strikes in month  : {len(subset):,}")
    print(f"  rows (cell-{cfg.freq_noun()}s): {len(table):,}")
    print(f"  cells             : {table[['lat','lon']].drop_duplicates().shape[0]}")
    print(f"  periods           : {table[cfg.TIME_COL].nunique():,}")
    print(f"  zero-target share : {(table['flash_count'] == 0).mean():.2%}")
    if len(nonzero):
        print(f"  non-zero counts   : min {int(nonzero.min())}, "
              f"median {int(nonzero.median())}, max {int(nonzero.max())}")
        print(f"  {cfg.TARGET_COLUMN}: "
              f"max {table[cfg.TARGET_COLUMN].max():,.1f}  "
              f"(a single flash in one hour annualises to a large number -- "
              f"this is why flash_count is the honest hourly target)")
    print("\n  head:")
    print(table.head(3).to_string(index=False))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--domain", choices=sorted(cfg.DOMAINS), default=None,
                    help="one domain only (default: both)")
    ap.add_argument("--month", default=None,
                    help="YYYY-MM to aggregate as a shape test")
    ap.add_argument("--skip-aggregate", action="store_true")
    args = ap.parse_args()

    names = [args.domain] if args.domain else list(cfg.DOMAINS)

    for name in names:
        domain = cfg.DOMAINS[name]
        print(f"\n{'=' * 60}\n{name} :: {domain.label}\n{'=' * 60}")
        try:
            strikes = LOADER[name]()
        except FileNotFoundError as exc:
            print(f"  SKIPPED -- {exc}")
            continue

        print(f"  strikes loaded    : {len(strikes):,}")
        print(f"  timestamp span    : {strikes['timestamp'].min()} .. "
              f"{strikes['timestamp'].max()}")

        check_timezone(strikes, domain)
        cov = check_coverage(strikes, domain)

        if not args.skip_aggregate:
            month = args.month or str(cov.loc[cov["observed_days"].idxmax(), "month"])
            check_one_month(strikes, domain, month)


if __name__ == "__main__":
    main()
