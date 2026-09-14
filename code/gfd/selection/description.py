"""Stage 1 — generic description. Neutral inventory of the built tables.

    python3 -m gfd.selection.description
    python3 -m gfd.selection.description --domain tropis
    python3 -m gfd.selection.description --no-json

Stage 1 holds no decisions. It measures the table and says what is there; what
to do about any of it is stage 2 or stage 3 (INSTRUCTIONS §5, D-17).

Three rules this module obeys, and they are the reason it can run on the whole
table without a leakage concern:

  * It never measures a predictor against the target. That is the screen, and
    the screen is stage 3 and runs on training rows only.
  * It fits nothing. A whole-table minimum is descriptive; a scaler is not.
  * It drops, fills and filters nothing, and emits no recommendation.

Anything that presupposes a later choice belongs to stage 3, not here: the
redundancy matrix is computed but no redundancy threshold is applied.

Cross-domain range comparison is deliberately absent. It is a stage 2 item in
its own right (D-17) and is measured there, where the scaling question it
feeds is being decided.

Section H reads the tails. Any scaler is defined by the extremes, so a single
sentinel or mis-scaled row sets the range every other value is squeezed into.
Whether a max is one observation or ten thousand identical ones is the
difference between a rare event and a fill value, and only the row counts at
the extreme distinguish them.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .. import config as cfg
from ..dataset import features as feat

QUANTILES = [0.01, 0.25, 0.50, 0.75, 0.99]


# --------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------
def load(domain: str) -> tuple[pd.DataFrame, dict]:
    """The built table and the meta written beside it."""
    path = cfg.processed_table(domain)
    meta_path = cfg.processed_meta(domain)
    if not path.exists():
        raise FileNotFoundError(f"{path} does not exist -- run gfd.dataset.build first.")
    df = pd.read_parquet(path)
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    if not meta:
        print(f"[{domain}] no meta beside the table; contract checks run against features.py only")
    return df, meta


# --------------------------------------------------------------------------
# A. Contract and shape
# --------------------------------------------------------------------------
def describe_contract(df: pd.DataFrame, meta: dict, domain: str) -> dict:
    dom = cfg.DOMAINS[domain]
    cells = df[["lat", "lon"]].drop_duplicates()
    n_cells = len(cells)
    n_hours = df[cfg.TIME_COL].nunique()

    present = set(df.columns)
    known = set(feat.CANDIDATES) | set(feat.EXCLUDE) | set(feat.RAW_TEMPORAL)
    unclassified = [c for c in df.columns if c not in known]
    missing = [c for c in feat.CANDIDATES if c not in present]

    # The table against what built it, which the contract alone cannot catch:
    # a stale parquet satisfies features.py and disagrees with its own meta.
    meta_drift = {}
    if meta:
        for key, actual in (
            ("n_rows", len(df)),
            ("n_cells", n_cells),
        ):
            if key in meta and meta[key] != actual:
                meta_drift[key] = {"meta": meta[key], "table": actual}
        if "columns" in meta and list(meta["columns"]) != list(df.columns):
            meta_drift["columns"] = {
                "only_in_meta": sorted(set(meta["columns"]) - present),
                "only_in_table": sorted(present - set(meta["columns"])),
            }
        if "candidates" in meta and list(meta["candidates"]) != list(feat.CANDIDATES):
            meta_drift["candidates"] = {
                "only_in_meta": sorted(set(meta["candidates"]) - set(feat.CANDIDATES)),
                "only_in_contract": sorted(set(feat.CANDIDATES) - set(meta["candidates"])),
            }

    out = {
        "domain": domain,
        "label": dom.label,
        "n_rows": len(df),
        "n_columns": len(df.columns),
        "n_cells": n_cells,
        "n_hours": n_hours,
        "rows_equal_cells_times_hours": len(df) == n_cells * n_hours,
        "grid_deg": cfg.GRID_DEG,
        "lat_range": [float(cells["lat"].min()), float(cells["lat"].max())],
        "lon_range": [float(cells["lon"].min()), float(cells["lon"].max())],
        "first_time": str(df[cfg.TIME_COL].min()),
        "last_time": str(df[cfg.TIME_COL].max()),
        "n_candidates_declared": len(feat.CANDIDATES),
        "n_candidates_present": len(feat.CANDIDATES) - len(missing),
        "candidates_missing": missing,
        "unclassified_columns": unclassified,
        "raw_temporal_present": [c for c in feat.RAW_TEMPORAL if c in present],
        "meta_drift": meta_drift,
        "dtypes": {c: str(t) for c, t in df.dtypes.items()},
    }

    print(f"\n{'=' * 74}\n{domain.upper()} — {dom.label}\n{'=' * 74}")
    print("\n[A] contract and shape")
    print(f"  rows            {len(df):,}")
    print(f"  columns         {len(df.columns)}")
    print(f"  cells x hours   {n_cells} x {n_hours:,} = {n_cells * n_hours:,}")
    print(f"  period          {out['first_time']} .. {out['last_time']}")
    print(f"  lat / lon       {out['lat_range']} / {out['lon_range']}")
    print(f"  candidates      {out['n_candidates_present']} of {len(feat.CANDIDATES)} present")

    # These print whether or not they are empty. An empty tripwire that only
    # prints when it fires is a tripwire nobody knows is armed (O-9).
    print(f"  unclassified    {unclassified if unclassified else 'none'}")
    print(f"  missing         {missing if missing else 'none'}")
    print(f"  meta drift      {meta_drift if meta_drift else 'none'}")

    if not out["rows_equal_cells_times_hours"]:
        raise AssertionError(
            f"{domain}: {len(df):,} rows but {n_cells} cells x {n_hours:,} hours = "
            f"{n_cells * n_hours:,}. The table is not a complete grid."
        )
    return out


# --------------------------------------------------------------------------
# B. Duplicates
# --------------------------------------------------------------------------
def describe_duplicates(df: pd.DataFrame, domain: str) -> dict:
    key = ["lat", "lon", cfg.TIME_COL]
    n_dup = int(df.duplicated(subset=key).sum())
    out = {"key": key, "n_duplicate_rows": n_dup, "n_full_duplicate_rows": int(df.duplicated().sum())}
    print("\n[B] duplicates")
    print(f"  on {'+'.join(key)}   {n_dup:,}")
    print(f"  whole-row              {out['n_full_duplicate_rows']:,}")
    if n_dup:
        raise AssertionError(
            f"{domain}: {n_dup:,} duplicate cell-hours. D-16 deduplicates strikes in "
            f"dataset/; a duplicate here is a different fault and everything below is unsafe."
        )
    return out


# --------------------------------------------------------------------------
# C. Missingness
# --------------------------------------------------------------------------
def describe_missingness(df: pd.DataFrame) -> dict:
    cands = [c for c in feat.CANDIDATES if c in df.columns]
    nulls = df[cands].isna()
    per_col = {c: int(nulls[c].sum()) for c in cands}
    with_nulls = [c for c, n in per_col.items() if n]

    out = {
        "per_column": {c: {"n": n, "share": n / len(df)} for c, n in per_col.items()},
        "columns_with_nulls": with_nulls,
        "rows_any_candidate_null": int(nulls.any(axis=1).sum()),
        "rows_all_candidates_present": int((~nulls.any(axis=1)).sum()),
        "co_occurrence": {},
        "by_year": {},
        "by_month_of_year": {},
    }

    # Reported as a table. Co-occurrence is not causation and stage 1 does not
    # read it as any -- it is here so stage 2 can see whether two columns go
    # missing together.
    for a in with_nulls:
        out["co_occurrence"][a] = {
            b: float((nulls[a] & nulls[b]).sum() / max(per_col[a], 1))
            for b in with_nulls
            if b != a
        }

    # A null that clusters in a period looks like an acquisition gap; one that
    # scatters looks like a property of the atmosphere. Stage 1 reports the
    # spread and draws neither conclusion.
    for a in with_nulls:
        out["by_year"][a] = {
            str(int(y)): float(v) for y, v in nulls[a].groupby(df["year"]).mean().items()
        }
        out["by_month_of_year"][a] = {
            str(int(m)): float(v)
            for m, v in nulls[a].groupby(df["month_of_year"]).mean().items()
        }

    print("\n[C] missingness")
    print(f"  {'column':<14}{'nulls':>14}{'share':>10}")
    for c in cands:
        n = per_col[c]
        print(f"  {c:<14}{n:>14,}{n / len(df):>10.4f}")
    print(f"  rows with any candidate null   {out['rows_any_candidate_null']:,}")
    print(f"  rows with all present          {out['rows_all_candidates_present']:,}")

    for a in with_nulls:
        print(f"\n  {a} null share by year")
        print("    " + "  ".join(f"{y}:{v:.3f}" for y, v in out["by_year"][a].items()))
        print(f"  {a} null share by month")
        print("    " + "  ".join(f"{m}:{v:.3f}" for m, v in out["by_month_of_year"][a].items()))
        if len(with_nulls) > 1:
            print(f"  {a} null, share of those also null in")
            print("    " + "  ".join(f"{b}:{v:.3f}" for b, v in out["co_occurrence"][a].items()))
    return out


# --------------------------------------------------------------------------
# D. Per-column distribution, candidates only
# --------------------------------------------------------------------------
def describe_distributions(df: pd.DataFrame) -> dict:
    cands = [c for c in feat.CANDIDATES if c in df.columns]
    out = {}
    for c in cands:
        s = df[c].dropna()
        counts = s.value_counts()
        top_val, top_n = (counts.index[0], int(counts.iloc[0])) if len(counts) else (np.nan, 0)
        q = s.quantile(QUANTILES)
        out[c] = {
            "n": int(s.size),
            "mean": float(s.mean()),
            "sd": float(s.std()),
            "min": float(s.min()),
            "p1": float(q.loc[0.01]),
            "p25": float(q.loc[0.25]),
            "p50": float(q.loc[0.50]),
            "p75": float(q.loc[0.75]),
            "p99": float(q.loc[0.99]),
            "max": float(s.max()),
            "skew": float(s.skew()),
            "kurtosis": float(s.kurtosis()),
            "zero_share": float((s == 0).mean()),
            "negative_share": float((s < 0).mean()),
            "n_distinct": int(s.nunique()),
            "is_constant": bool(s.nunique() <= 1),
            # The pile-up. A column can look well spread on quantiles and still
            # be one value on a third of its rows.
            "largest_point_mass_value": float(top_val) if top_n else None,
            "largest_point_mass_share": float(top_n / s.size) if s.size else None,
        }

    print("\n[D] per-column distribution — candidates")
    hdr = f"  {'column':<14}{'min':>12}{'p25':>12}{'p50':>12}{'p75':>12}{'max':>12}{'skew':>9}{'mass':>8}"
    print(hdr)
    for c, d in out.items():
        print(
            f"  {c:<14}{d['min']:>12.4g}{d['p25']:>12.4g}{d['p50']:>12.4g}"
            f"{d['p75']:>12.4g}{d['max']:>12.4g}{d['skew']:>9.2f}"
            f"{(d['largest_point_mass_share'] or 0):>8.3f}"
        )
    flat = [c for c, d in out.items() if d["is_constant"]]
    near = [c for c, d in out.items() if not d["is_constant"] and d["n_distinct"] < 10]
    print(f"  constant        {flat if flat else 'none'}")
    print(f"  under 10 values {near if near else 'none'}")
    print("  'mass' is the share held by the single most frequent value.")
    return out


# --------------------------------------------------------------------------
# E. Target
# --------------------------------------------------------------------------
def describe_target(df: pd.DataFrame) -> dict:
    t = df[cfg.TARGET]
    nz = t[t > 0]
    per_cell = df.groupby(["lat", "lon"])[cfg.TARGET].sum()
    dead = per_cell[per_cell == 0]

    observed = df["coverage"] > 0 if "coverage" in df.columns else pd.Series(True, index=df.index)
    q = nz.quantile(QUANTILES) if len(nz) else None

    out = {
        "n_rows": int(len(t)),
        "zero_share_all_rows": float((t == 0).mean()),
        "n_rows_observed": int(observed.sum()),
        "zero_share_observed_rows": float((t[observed] == 0).mean()) if observed.any() else None,
        "n_nonzero": int(len(nz)),
        "total_flashes": int(t.sum()),
        "mean": float(t.mean()),
        "variance": float(t.var()),
        "var_over_mean": float(t.var() / t.mean()) if t.mean() else None,
        "skew_raw": float(t.skew()),
        "skew_log1p": float(np.log1p(t).skew()),
        "nonzero": {
            "min": float(nz.min()),
            "p1": float(q.loc[0.01]),
            "p25": float(q.loc[0.25]),
            "p50": float(q.loc[0.50]),
            "p75": float(q.loc[0.75]),
            "p99": float(q.loc[0.99]),
            "max": float(nz.max()),
            "mean": float(nz.mean()),
            "skew": float(nz.skew()),
        } if len(nz) else None,
        "n_dead_cells": int(len(dead)),
        "dead_cells": [[float(a), float(b)] for a, b in dead.index],
        "rows_in_dead_cells": int(len(dead) * df[cfg.TIME_COL].nunique()),
        "by_year": {
            str(int(y)): {"total": int(v), "zero_share": float(z)}
            for (y, v), (_, z) in zip(
                t.groupby(df["year"]).sum().items(),
                (t == 0).groupby(df["year"]).mean().items(),
            )
        },
    }

    print(f"\n[E] target — {cfg.TARGET}")
    print(f"  zero share, all rows       {out['zero_share_all_rows']:.4f}")
    if out["zero_share_observed_rows"] is not None:
        print(f"  zero share, coverage > 0   {out['zero_share_observed_rows']:.4f} "
              f"({out['n_rows_observed']:,} rows)")
    print(f"  non-zero cell-hours        {out['n_nonzero']:,}")
    print(f"  total flashes              {out['total_flashes']:,}")
    print(f"  mean / var / var-mean      {out['mean']:.4f} / {out['variance']:.4f} / "
          f"{out['var_over_mean']:.2f}")
    print(f"  skew raw / log1p           {out['skew_raw']:.2f} / {out['skew_log1p']:.2f}")
    if out["nonzero"]:
        n = out["nonzero"]
        print(f"  non-zero p25/p50/p75/max   {n['p25']:.0f} / {n['p50']:.0f} / "
              f"{n['p75']:.0f} / {n['max']:.0f}")
    print(f"  dead cells                 {out['n_dead_cells']} "
          f"({out['rows_in_dead_cells']:,} rows)")
    print(f"  {'year':<8}{'total':>14}{'zero share':>14}")
    for y, d in out["by_year"].items():
        print(f"  {y:<8}{d['total']:>14,}{d['zero_share']:>14.4f}")
    return out


# --------------------------------------------------------------------------
# F. Coverage
# --------------------------------------------------------------------------
def describe_coverage(df: pd.DataFrame) -> dict:
    if "coverage" not in df.columns:
        return {}
    cov = df["coverage"]
    # coverage derives from observed_days / days_in_month, so it is constant
    # within a (cell, month). Both weightings are stated because the record
    # holds two different means for the same field and does not say which is
    # which.
    per_cm = df.groupby(["lat", "lon", "month"], observed=True)["coverage"].first()
    q = cov.quantile(QUANTILES)
    out = {
        "row_weighted_mean": float(cov.mean()),
        "cell_month_weighted_mean": float(per_cm.mean()),
        "median": float(cov.median()),
        "min": float(cov.min()),
        "max": float(cov.max()),
        "p1": float(q.loc[0.01]),
        "p25": float(q.loc[0.25]),
        "p75": float(q.loc[0.75]),
        "p99": float(q.loc[0.99]),
        "n_rows_zero_coverage": int((cov == 0).sum()),
        "n_cell_months": int(len(per_cm)),
        "n_months": int(df["month"].nunique()),
        "cell_months_zero_coverage": int((per_cm == 0).sum()),
    }
    print("\n[F] coverage — reported, never acted on (INSTRUCTIONS §4)")
    print(f"  row-weighted mean          {out['row_weighted_mean']:.4f}")
    print(f"  cell-month-weighted mean   {out['cell_month_weighted_mean']:.4f}")
    print(f"  median / min / max         {out['median']:.4f} / {out['min']:.4f} / {out['max']:.4f}")
    print(f"  p1 / p25 / p75 / p99       {out['p1']:.4f} / {out['p25']:.4f} / "
          f"{out['p75']:.4f} / {out['p99']:.4f}")
    print(f"  rows at zero               {out['n_rows_zero_coverage']:,}")
    print(f"  months / cell-months       {out['n_months']} / {out['n_cell_months']:,}")
    return out


# --------------------------------------------------------------------------
# G. Predictor redundancy
# --------------------------------------------------------------------------
def describe_redundancy(df: pd.DataFrame, top: int = 15) -> dict:
    """Spearman among candidates. No threshold -- a threshold is stage 3.

    A column later dropped on this basis must have it recomputed on training
    rows only. This is a property of the table, not a selection step.
    """
    cands = [c for c in feat.CANDIDATES if c in df.columns]
    rho = df[cands].corr(method="spearman")  # pairwise-complete where nulls exist

    pairs = []
    for i, a in enumerate(cands):
        for b in cands[i + 1:]:
            v = rho.loc[a, b]
            if pd.notna(v):
                pairs.append((a, b, float(v)))
    pairs.sort(key=lambda p: abs(p[2]), reverse=True)

    out = {
        "matrix": {a: {b: (None if pd.isna(rho.loc[a, b]) else float(rho.loc[a, b]))
                       for b in cands} for a in cands},
        "ranked_pairs": [{"a": a, "b": b, "spearman": v} for a, b, v in pairs],
    }
    print(f"\n[G] predictor redundancy — Spearman, top {top} pairs by |rho|, no threshold applied")
    for a, b, v in pairs[:top]:
        print(f"  {a:<14}{b:<14}{v:>9.3f}")
    return out


# --------------------------------------------------------------------------
# H. Tails
# --------------------------------------------------------------------------
def describe_tails(df: pd.DataFrame, k: int = 10, detach: float = 3.0) -> dict:
    """The extreme distinct values of every candidate, with their row counts.

    A max held by one row is a rare event. A max held by ten thousand identical
    rows is a sentinel. The quantiles in section D cannot tell them apart and a
    min-max scaler treats them the same, so the multiplicity is the diagnostic.

    `detach` only decides which columns get their rows printed. It is a
    reporting threshold, not a handling one -- every column appears in the
    summary regardless, and nothing is dropped or flagged for dropping.
    """
    cands = [c for c in feat.CANDIDATES if c in df.columns]
    out = {}
    for c in cands:
        s = df[c].dropna()
        counts = s.value_counts()
        lo = counts.index.to_series().nsmallest(k)
        hi = counts.index.to_series().nlargest(k)
        p50, p999, p001 = s.quantile([0.50, 0.999, 0.001])
        hi_span, lo_span = p999 - p50, p50 - p001
        out[c] = {
            "lowest": [{"value": float(v), "n_rows": int(counts.loc[v])} for v in lo],
            "highest": [{"value": float(v), "n_rows": int(counts.loc[v])} for v in hi],
            "p001": float(p001),
            "p50": float(p50),
            "p999": float(p999),
            "n_above_p999": int((s > p999).sum()),
            "n_below_p001": int((s < p001).sum()),
            # How far past the bulk the extreme sits, in units of the bulk's
            # own spread. Large means one end is detached from everything else.
            "max_detachment": float((s.max() - p999) / hi_span) if hi_span > 0 else None,
            "min_detachment": float((p001 - s.min()) / lo_span) if lo_span > 0 else None,
        }

    print(f"\n[H] tails — {k} most extreme distinct values per candidate, with row counts")
    print(f"  {'column':<14}{'min':>12}{'n':>9}{'max':>12}{'n':>9}{'lo detach':>11}{'hi detach':>11}")
    for c, d in out.items():
        lo0, hi0 = d["lowest"][0], d["highest"][0]
        md, nd = d["max_detachment"], d["min_detachment"]
        print(
            f"  {c:<14}{lo0['value']:>12.4g}{lo0['n_rows']:>9,}{hi0['value']:>12.4g}"
            f"{hi0['n_rows']:>9,}{(-1 if nd is None else nd):>11.1f}"
            f"{(-1 if md is None else md):>11.1f}"
        )
    print("  'n' is how many rows hold that exact value. A large n at an extreme is a")
    print("  sentinel, not an observation. 'detach' is the gap past p99.9 (or below")
    print("  p00.1) measured in units of the p50-to-p99.9 spread; -1 means undefined.")

    flagged = [
        c for c, d in out.items()
        if (d["max_detachment"] or 0) >= detach or (d["min_detachment"] or 0) >= detach
    ]
    print(f"  detached beyond {detach}x  {flagged if flagged else 'none'}")

    for c in flagged:
        for end in ("highest", "lowest"):
            vals = [e["value"] for e in out[c][end][:3]]
            rows = df.loc[df[c].isin(vals), [cfg.TIME_COL, "lat", "lon", c, cfg.TARGET]]
            rows = rows.sort_values(c, ascending=(end == "lowest")).head(k)
            print(f"\n  {c} — {end} rows")
            for _, r in rows.iterrows():
                print(f"    {str(r[cfg.TIME_COL]):<20}{r['lat']:>8.2f}{r['lon']:>9.2f}"
                      f"{r[c]:>14.6g}{'  flash=' + str(int(r[cfg.TARGET])):>14}")
    return out


# --------------------------------------------------------------------------
# Driver
# --------------------------------------------------------------------------
def describe_domain(domain: str) -> dict:
    df, meta = load(domain)
    return {
        "contract": describe_contract(df, meta, domain),
        "duplicates": describe_duplicates(df, domain),
        "missingness": describe_missingness(df),
        "distributions": describe_distributions(df),
        "target": describe_target(df),
        "coverage": describe_coverage(df),
        "redundancy": describe_redundancy(df),
        "tails": describe_tails(df),
    }


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="Stage 1 generic description of the built tables.")
    ap.add_argument("--domain", choices=sorted(cfg.DOMAINS), help="one domain; default both")
    ap.add_argument("--no-json", action="store_true",
                    help=f"print only; otherwise writes {cfg.PROCESSED_DIR}/description_<domain>.json")
    args = ap.parse_args(argv)

    domains = [args.domain] if args.domain else sorted(cfg.DOMAINS)
    results = {d: describe_domain(d) for d in domains}

    if not args.no_json:
        for d, r in results.items():
            p = cfg.PROCESSED_DIR / f"description_{d}.json"
            p.write_text(json.dumps(r, indent=2), encoding="utf-8")
            print(f"\n[write] {p}")
        print("[write] decimal point throughout; the thesis takes commas (INSTRUCTIONS §6)")


if __name__ == "__main__":
    main()
