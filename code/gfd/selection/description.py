"""What the built tables look like, in the terms the handling decisions need.

    python3 -m gfd.selection.description
    python3 -m gfd.selection.description --domain tropis

Every function here answers a decision that is still open. Nothing is included
because it is customary: no mode, no NaN profile (measured at 0% for every
predictor in both domains), no column count.

    zero_structure      are the zeros structured or scattered  -> O-3, and
                        whether a two-stage model is worth it
    zero_runs           how long a dry spell lasts             -> same
    coverage_vs_target  does a coverage gate remove bad data
                        or remove quiet seasons                -> D-8's deferral
    nonzero_scale       does log1p suit the non-zero tail      -> checks D-3
    predictor_ranges    how far apart the predictors sit       -> scaling
    domain_shift        do the two domains occupy the same
                        predictor space                        -> the whole
                        cross-domain claim
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from .. import config as cfg
from ..dataset import features as feat


def load_table(domain: cfg.Domain, columns: list[str] | None = None) -> pd.DataFrame:
    path = cfg.PROCESSED_DIR / f"gfd_{domain.name}_hourly.parquet"
    if not path.exists():
        raise FileNotFoundError(f"{path} -- run `python3 -m gfd.dataset.build` first")
    return pd.read_parquet(path, columns=columns)


def present_predictors(table: pd.DataFrame) -> list[str]:
    """Candidates that made it into this table. Never a hardcoded count."""
    return [c for c in feat.CANDIDATES if c in table.columns]


# ==========================================================================
# Zero structure
# ==========================================================================
def zero_structure(table: pd.DataFrame, name: str) -> None:
    """Zero share sliced three ways.

    The overall figure is already known. What decides the handling is whether
    the zeros sit somewhere -- a cell that never flashes is a different object
    from a quiet 3 a.m. in an active one, and only the second is a real
    observation of no lightning.
    """
    t = table
    print(f"\n=== {name}: where the zeros are ===")
    print(f"overall zero share {float((t[cfg.TARGET] == 0).mean()):.2%} "
          f"of {len(t):,} rows")

    per_cell = t.groupby(["lat", "lon"])[cfg.TARGET].agg(["sum", "size"])
    per_cell["zero_share"] = 1 - t.groupby(["lat", "lon"])[cfg.TARGET].apply(
        lambda s: (s > 0).mean()
    )
    dead = per_cell[per_cell["sum"] == 0]
    print(f"\ncells: {len(per_cell)} total, {len(dead)} never flash "
          f"({len(dead) * len(t) / max(len(per_cell), 1) / max(len(t), 1):.1%} of rows)")
    print(f"  zero share across live cells: "
          f"min {per_cell.loc[per_cell['sum'] > 0, 'zero_share'].min():.2%}, "
          f"max {per_cell.loc[per_cell['sum'] > 0, 'zero_share'].max():.2%}")
    if len(dead):
        print("  dead cells:")
        for (la, lo) in dead.index:
            print(f"    {la:>7.2f} {lo:>8.2f}")

    by_hour = t.groupby("hour_of_day_local")[cfg.TARGET].apply(lambda s: (s == 0).mean())
    print(f"\nby local hour: min {by_hour.min():.2%} at {int(by_hour.idxmin()):02d}:00, "
          f"max {by_hour.max():.2%} at {int(by_hour.idxmax()):02d}:00, "
          f"spread {by_hour.max() - by_hour.min():.1%} points")

    by_month = t.groupby("month_of_year")[cfg.TARGET].apply(lambda s: (s == 0).mean())
    print(f"by month     : min {by_month.min():.2%} in month {int(by_month.idxmin())}, "
          f"max {by_month.max():.2%} in month {int(by_month.idxmax())}, "
          f"spread {by_month.max() - by_month.min():.1%} points")
    print("\n  A large spread means the zeros are predictable from the "
          "predictors already in the table, and a model can learn them.")


def zero_runs(table: pd.DataFrame, name: str) -> None:
    """Length of consecutive zero-flash hours within a cell.

    Decides whether zero-inflation is worth modelling separately. Long runs
    mean the target is mostly a regime that switches on and off; short
    scattered zeros mean one continuous process with many small values.
    """
    # Dead cells would otherwise contribute one run the length of the record
    # each, and dominate every quantile below. A cell that never flashes is not
    # having a dry spell.
    live = table.groupby(["lat", "lon"])[cfg.TARGET].transform("sum") > 0
    dropped = int((~live).sum())
    t = table.loc[live, ["lat", "lon", cfg.TIME_COL, cfg.TARGET]].sort_values(
        ["lat", "lon", cfg.TIME_COL]
    )
    if t.empty:
        print(f"\n=== {name}: no live cells ===")
        return
    is_zero = (t[cfg.TARGET] == 0).to_numpy()
    cell = (t["lat"].astype(str) + "_" + t["lon"].astype(str)).to_numpy()

    # A run breaks when the zero/non-zero state flips or the cell changes.
    boundary = np.empty(len(t), dtype=bool)
    boundary[0] = True
    boundary[1:] = (is_zero[1:] != is_zero[:-1]) | (cell[1:] != cell[:-1])
    run_id = np.cumsum(boundary)

    runs = pd.DataFrame({"run": run_id, "zero": is_zero})
    lengths = runs.groupby("run")["zero"].agg(["size", "first"])
    zero_runs_len = lengths.loc[lengths["first"], "size"]

    print(f"\n=== {name}: consecutive zero hours within a live cell ===")
    print(f"{len(zero_runs_len):,} zero runs across "
          f"{t[['lat','lon']].drop_duplicates().shape[0]} live cells "
          f"({dropped:,} rows in never-flashing cells excluded)")
    for q in (0.5, 0.75, 0.9, 0.99):
        print(f"  p{int(q * 100):<3d} {zero_runs_len.quantile(q):>8,.0f} hours")
    print(f"  max  {zero_runs_len.max():>8,.0f} hours "
          f"({zero_runs_len.max() / 24:,.0f} days)")
    print(f"  share of zero rows inside runs longer than 7 days: "
          f"{zero_runs_len[zero_runs_len > 168].sum() / zero_runs_len.sum():.1%}")


# ==========================================================================
# Coverage
# ==========================================================================
def coverage_vs_target(table: pd.DataFrame, name: str) -> None:
    """Does a coverage gate remove bad data, or remove quiet seasons?

    D-8 kept every month and pushed this decision here. `coverage` counts a day
    with no lightning anywhere in the box as unobserved, so it is partly a
    measure of the weather rather than of the detector. If low-coverage months
    are also low-target months, a gate removes exactly the low-target examples
    the model needs.
    """
    per_month = (
        table.assign(_m=pd.PeriodIndex(table[cfg.TIME_COL]).asfreq("M"))
        .groupby("_m")
        .agg(coverage=("coverage", "first"),
             mean_flash=(cfg.TARGET, "mean"),
             active_share=(cfg.TARGET, lambda s: (s > 0).mean()))
    )

    print(f"\n=== {name}: coverage against activity, by month ===")
    print(f"{len(per_month)} months. Spearman(coverage, mean flash_count) = "
          f"{per_month['coverage'].corr(per_month['mean_flash'], method='spearman'):.3f}")

    bins = [-0.01, 0.25, 0.5, 0.75, 0.9, 1.01]
    grouped = per_month.groupby(pd.cut(per_month["coverage"], bins), observed=True)
    print(f"\n{'coverage band':<16s} {'months':>7s} {'mean flash':>12s} {'active rows':>12s}")
    for band, g in grouped:
        print(f"{str(band):<16s} {len(g):>7d} {g['mean_flash'].mean():>12.4f} "
              f"{g['active_share'].mean():>11.2%}")
    print("\n  A positive correlation means the gate is a weather filter, "
          "not a data-quality filter.")


# ==========================================================================
# Target scale
# ==========================================================================
def nonzero_scale(table: pd.DataFrame, name: str) -> None:
    """The non-zero tail, and whether log1p tames it.

    D-3 fixed log1p already. This checks the decision rather than assuming it:
    the transform behaves very differently against a tail reaching 12 than one
    reaching 800.
    """
    nz = table.loc[table[cfg.TARGET] > 0, cfg.TARGET]
    print(f"\n=== {name}: non-zero flash counts ===")
    print(f"{len(nz):,} rows, min {int(nz.min())}, max {int(nz.max())}")
    for q in (0.5, 0.9, 0.99, 0.999):
        print(f"  p{q * 100:<5g} {nz.quantile(q):>8,.0f}")
    print(f"  skew raw {nz.skew():>8.2f}   log1p {np.log1p(nz).skew():>8.2f}")
    print(f"  share of all flashes in the top 1% of rows: "
          f"{nz.nlargest(max(len(nz) // 100, 1)).sum() / nz.sum():.1%}")


# ==========================================================================
# Predictors
# ==========================================================================
def predictor_ranges(table: pd.DataFrame, name: str) -> None:
    """How far apart the predictors sit, and how skewed each is.

    Decides the scaler. Angle encoding needs a bounded range, and a predictor
    spanning orders of magnitude will dominate a distance-based method before
    any of that.
    """
    cols = present_predictors(table)
    d = table[cols].describe().T
    d["skew"] = table[cols].skew()
    d["zero_share"] = (table[cols] == 0).mean()

    print(f"\n=== {name}: predictor scales ({len(cols)} present) ===")
    print(f"{'':<16s} {'min':>12s} {'median':>12s} {'max':>12s} {'skew':>8s} {'=0':>7s}")
    for c in cols:
        r = d.loc[c]
        print(f"{c:<16s} {r['min']:>12.4g} {r['50%']:>12.4g} {r['max']:>12.4g} "
              f"{r['skew']:>8.2f} {r['zero_share']:>6.1%}")

    spans = (d["max"] - d["min"]).replace(0, np.nan)
    print(f"\n  widest span / narrowest span = {spans.max() / spans.min():,.0f}x")


# ==========================================================================
# Cross-domain
# ==========================================================================
def domain_shift(tables: dict[str, pd.DataFrame]) -> None:
    """Do the two domains occupy the same predictor space?

    If they do not, a model that transfers poorly may be reporting domain
    shift rather than a failure to generalise -- and the cross-domain gap is
    the number this thesis reports. Measured here so it can be stated rather
    than discovered.
    """
    names = list(tables)
    if len(names) < 2:
        print("\n(domain shift needs both tables)")
        return

    a, b = tables[names[0]], tables[names[1]]
    cols = [c for c in present_predictors(a) if c in present_predictors(b)]

    print(f"\n=== domain shift: {names[0]} against {names[1]} ===")
    print(f"{'':<16s} {'median A':>12s} {'median B':>12s} {'ratio':>8s} {'overlap':>9s}")
    for c in cols:
        ma, mb = a[c].median(), b[c].median()
        # Share of B inside A's 1st-99th percentile band.
        lo, hi = a[c].quantile([0.01, 0.99])
        inside = float(((b[c] >= lo) & (b[c] <= hi)).mean())
        ratio = mb / ma if ma not in (0, np.nan) else np.nan
        flag = "  <-- little overlap" if inside < 0.8 else ""
        print(f"{c:<16s} {ma:>12.4g} {mb:>12.4g} {ratio:>8.2f} {inside:>8.1%}{flag}")
    print("\n  Overlap is the share of domain B's values inside domain A's "
          "1st-99th percentile band.")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--domain", choices=sorted(cfg.DOMAINS), default=None)
    ap.add_argument("--skip-runs", action="store_true",
                    help="skip the zero-run scan, which sorts the whole table")
    args = ap.parse_args()

    domains = [cfg.DOMAINS[args.domain]] if args.domain else list(cfg.DOMAINS.values())
    tables: dict[str, pd.DataFrame] = {}

    for d in domains:
        t = load_table(d)
        tables[d.name] = t
        print(f"\n{'=' * 68}\n{d.name} :: {d.label}\n{'=' * 68}")
        zero_structure(t, d.name)
        if not args.skip_runs:
            zero_runs(t, d.name)
        coverage_vs_target(t, d.name)
        nonzero_scale(t, d.name)
        predictor_ranges(t, d.name)

    if len(tables) > 1:
        domain_shift(tables)


if __name__ == "__main__":
    main()
