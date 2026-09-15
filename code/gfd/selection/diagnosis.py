"""Stage 2 — measure the problems stage 1 surfaced.

    python3 -m gfd.selection.diagnosis
    python3 -m gfd.selection.diagnosis --domain tropis

Stage 1 said what is in the table. Stage 2 asks what is wrong with it, and is
allowed to put a predictor against the target to find out. It still only
measures: nothing here is fitted, filtered or imputed, and no handling follows
from it automatically.

Four concerns, one per section. Section 3 would normally wait on the scaler
choice, which has not been made; it breaks the circularity by measuring **all
three** candidate maps side by side, so it compares options rather than
describing one. Nothing in it presupposes which is chosen.

Note on the target. Stage 1's rule is that it never puts a predictor against
the target, which is what lets it run on the whole table safely. Stage 2 breaks
that rule deliberately, so the statements it produces are arguments for a
**design** choice — drop a column, or impute and flag it — not fitted
parameters. If any statistic here later becomes a selection criterion rather
than an argument, it must be recomputed on training rows only.
"""

from __future__ import annotations

import argparse
import json

import numpy as np
import pandas as pd

from .. import config as cfg
from ..dataset import features as feat
from .prepare import with_derived

# --------------------------------------------------------------------------
# 1. Missingness — what the blank means
# --------------------------------------------------------------------------
# Each undefined field is supposed to follow from a partner being absent. These
# are the stories being tested, not assumptions being applied. `CBH` has no
# single partner column, so cloud water is summed for it.
PARTNERS = {
    "CIN": ("CAPE", "no parcel reaches a level of free convection"),
    "CBH": ("_cloud_water", "no cloud to have a base"),
}

DECILES = np.arange(0.0, 1.01, 0.1)


def null_rate_by_partner(df: pd.DataFrame, col: str, partner: str) -> dict:
    """Null rate of `col` across the partner's deciles.

    If the story holds, the rate collapses toward zero as soon as the partner
    leaves its bottom bin. A rate that stays high in the upper deciles is the
    residual, and the story does not survive it.
    """
    p = df[partner]
    zero = p <= 0
    isna = df[col].isna()
    out = {
        "partner": partner,
        "partner_zero_rows": int(zero.sum()),
        "null_rate_where_partner_zero": float(isna[zero].mean()) if zero.any() else None,
        "null_rate_where_partner_positive": float(isna[~zero].mean()),
        "by_decile": {},
    }
    pos = df.loc[~zero, [partner, col]]
    if len(pos):
        edges = np.unique(pos[partner].quantile(DECILES).to_numpy())
        if len(edges) > 2:
            bins = pd.cut(pos[partner], bins=edges, include_lowest=True, duplicates="drop")
            g = pos[col].isna().groupby(bins, observed=True)
            sizes = g.size()
            for interval, rate in g.mean().items():
                out["by_decile"][f"{interval.left:.4g}..{interval.right:.4g}"] = {
                    "null_rate": float(rate),
                    "n_rows": int(sizes.loc[interval]),
                }
    return out


def residual(df: pd.DataFrame, col: str, partner: str) -> dict:
    """The rows the story does not cover: partner positive, `col` still null."""
    m = df[col].isna() & (df[partner] > 0)
    n_null = int(df[col].isna().sum())
    n = int(m.sum())
    out = {
        "n_rows": n,
        "share_of_all_rows": n / len(df),
        "share_of_nulls": (n / n_null) if n_null else None,
    }
    if n:
        p = df.loc[m, partner]
        out["partner_in_residual"] = {
            "min": float(p.min()), "p25": float(p.quantile(0.25)),
            "p50": float(p.median()), "p75": float(p.quantile(0.75)),
            "p99": float(p.quantile(0.99)), "max": float(p.max()),
        }
        # Small partner values in the residual mean the story survives with a
        # threshold instead of a hard zero. Values reaching the upper tail mean
        # it does not survive at all.
        present = df.loc[df[col].notna(), partner]
        out["partner_percentile_of_residual_max"] = float((present < p.max()).mean())
        out["by_month"] = {
            str(int(k)): float(v) for k, v in m.groupby(df["month_of_year"]).mean().items()
        }
    return out


def missingness_against_target(df: pd.DataFrame, col: str, partner: str) -> dict:
    t = df[cfg.TARGET]
    isna = df[col].isna()
    total = t.sum()

    def block(mask):
        if not mask.any():
            return None
        tt = t[mask]
        return {
            "n_rows": int(mask.sum()),
            "zero_share": float((tt == 0).mean()),
            "mean_flash": float(tt.mean()),
            "total_flashes": int(tt.sum()),
            "share_of_all_flashes": float(tt.sum() / total) if total else None,
        }

    return {
        "null": block(isna),
        "present": block(~isna),
        "residual_partner_positive_and_null": block(isna & (df[partner] > 0)),
        "null_and_partner_zero": block(isna & (df[partner] <= 0)),
    }


def ceiling(df: pd.DataFrame, col: str, k: int = 8) -> dict:
    """Whether the field is censored above as well as undefined below.

    Stage 1 found subtropis `CIN` maxing at exactly 1000.0 and tropis at 999.5,
    the distribution running right up to each. A pile of rows on one value near
    the top is a ceiling; a thinning tail is not.
    """
    s = df[col].dropna()
    counts = s.value_counts()
    top = counts.index.to_series().nlargest(k)
    return {
        "max": float(s.max()),
        "n_at_max": int((s == s.max()).sum()),
        "n_within_1pct_of_max": int((s >= s.max() * 0.99).sum()),
        "top_values": [{"value": float(v), "n_rows": int(counts.loc[v])} for v in top],
    }


def diagnose_missingness(df: pd.DataFrame) -> dict:
    out = {}
    for col, (partner, story) in PARTNERS.items():
        r = {
            "partner": partner,
            "story": story,
            "null_rate": null_rate_by_partner(df, col, partner),
            "residual": residual(df, col, partner),
            "target": missingness_against_target(df, col, partner),
            "ceiling": ceiling(df, col),
        }
        out[col] = r

        print(f"\n[1] {col} — story: \"{story}\" (partner {partner})")
        nr = r["null_rate"]
        print(f"  null rate, {partner} = 0            "
              f"{(nr['null_rate_where_partner_zero'] or 0):.4f}  ({nr['partner_zero_rows']:,} rows)")
        print(f"  null rate, {partner} > 0            "
              f"{nr['null_rate_where_partner_positive']:.4f}")
        if nr["by_decile"]:
            print(f"  null rate by {partner} decile ({partner} > 0 only)")
            for rng, d in nr["by_decile"].items():
                print(f"    {rng:<30}{d['null_rate']:>8.4f}{d['n_rows']:>12,}")

        rs = r["residual"]
        print(f"  residual: {partner} > 0 and {col} null")
        print(f"    {rs['n_rows']:,} rows — {rs['share_of_all_rows']:.4f} of the table, "
              f"{(rs['share_of_nulls'] or 0):.4f} of all {col} nulls")
        if rs["n_rows"]:
            p = rs["partner_in_residual"]
            print(f"    {partner} there: p50 {p['p50']:.4g}, p99 {p['p99']:.4g}, max {p['max']:.4g}")
            print(f"    that max sits at percentile {rs['partner_percentile_of_residual_max']:.4f} "
                  f"of {partner} where {col} is present")
            print("    residual share by month")
            print("      " + "  ".join(f"{m}:{v:.3f}" for m, v in rs["by_month"].items()))

        print(f"  against the target")
        print(f"    {'group':<36}{'rows':>12}{'zero share':>12}{'mean flash':>12}{'% flashes':>11}")
        for name, b in r["target"].items():
            if b:
                print(f"    {name:<36}{b['n_rows']:>12,}{b['zero_share']:>12.4f}"
                      f"{b['mean_flash']:>12.4f}{(b['share_of_all_flashes'] or 0) * 100:>11.2f}")

        c = r["ceiling"]
        print(f"  ceiling: max {c['max']:.6g}, {c['n_at_max']:,} rows at it, "
              f"{c['n_within_1pct_of_max']:,} within 1%")
        print("    top distinct  " + ", ".join(
            f"{e['value']:.6g}(n={e['n_rows']:,})" for e in c["top_values"]))
    return out


# --------------------------------------------------------------------------
# 2. Zero structure — what shape the 94-97% of zeros has
# --------------------------------------------------------------------------
def zero_runs(df: pd.DataFrame) -> dict:
    """Lengths of consecutive zero-flash hours within a cell.

    A switch-like target sits in long runs; a noisy one alternates. This is the
    evidence for or against a two-stage model (S-7), and it is a property of
    the target alone.

    Dead cells are reported separately: a cell that never flashes is one run
    the length of the record, and pooling it would swamp everything else.
    """
    d = df[["lat", "lon", cfg.TIME_COL, cfg.TARGET]].sort_values(["lat", "lon", cfg.TIME_COL])
    per_cell = d.groupby(["lat", "lon"])[cfg.TARGET].sum()
    live = set(per_cell[per_cell > 0].index)

    key = list(zip(d["lat"].to_numpy(), d["lon"].to_numpy()))
    is_zero = (d[cfg.TARGET].to_numpy() == 0)
    is_live = np.array([k in live for k in key])

    # A new run starts at a cell boundary or a zero/non-zero flip.
    new = np.empty(len(d), dtype=bool)
    new[0] = True
    same_cell = np.array([a == b for a, b in zip(key[1:], key[:-1])])
    new[1:] = (~same_cell) | (is_zero[1:] != is_zero[:-1])
    run_id = np.cumsum(new) - 1
    lengths = np.bincount(run_id)
    starts = np.flatnonzero(new)

    zero_live = lengths[is_zero[starts] & is_live[starts]]
    if not len(zero_live):
        return {}
    q = np.quantile(zero_live, [0.25, 0.50, 0.75, 0.90, 0.99])
    total_zero_rows = int(zero_live.sum())
    return {
        "n_live_cells": len(live),
        "n_zero_runs_live_cells": int(len(zero_live)),
        "run_hours": {
            "p25": float(q[0]), "p50": float(q[1]), "p75": float(q[2]),
            "p90": float(q[3]), "p99": float(q[4]), "max": int(zero_live.max()),
        },
        "share_of_zero_rows_in_runs_over_24h":
            float(zero_live[zero_live > 24].sum() / total_zero_rows),
        "share_of_zero_rows_in_runs_over_168h":
            float(zero_live[zero_live > 168].sum() / total_zero_rows),
    }


def zero_share_by(df: pd.DataFrame, col: str) -> dict:
    g = (df[cfg.TARGET] == 0).groupby(df[col])
    return {str(int(k)): float(v) for k, v in g.mean().items()}


def count_shape(df: pd.DataFrame) -> dict:
    """Is the excess of zeros beyond what a count distribution would give?

    A negative binomial is fitted by moments purely as a yardstick — what
    share of zeros a plain count model would predict at this mean and
    variance. It is a diagnostic, not a model, and nothing downstream uses it.
    """
    t = df[cfg.TARGET].to_numpy()
    mean, var = float(t.mean()), float(t.var())
    obs_zero = float((t == 0).mean())
    out = {
        "mean": mean, "variance": var,
        "var_over_mean": var / mean if mean else None,
        "observed_zero_share": obs_zero,
        "poisson_predicted_zero_share": float(np.exp(-mean)),
    }
    if var > mean > 0:
        r = mean ** 2 / (var - mean)
        p = r / (r + mean)
        out["negbin_r"] = float(r)
        out["negbin_predicted_zero_share"] = float(p ** r)
        out["excess_zero_share_over_negbin"] = obs_zero - float(p ** r)

    nz = t[t > 0]
    out["nonzero"] = {
        "n": int(nz.size),
        "share_equal_to_1": float((nz == 1).mean()),
        "p50": float(np.median(nz)),
        "p90": float(np.quantile(nz, 0.90)),
        "p99": float(np.quantile(nz, 0.99)),
        "max": int(nz.max()),
        "mean": float(nz.mean()),
        "var_over_mean": float(nz.var() / nz.mean()),
    }
    return out


def diagnose_zeros(df: pd.DataFrame) -> dict:
    out = {
        "runs": zero_runs(df),
        "by_hour_local": zero_share_by(df, "hour_of_day_local"),
        "by_month": zero_share_by(df, "month_of_year"),
        "shape": count_shape(df),
    }

    print("\n[2] zero structure")
    r = out["runs"]
    if r:
        rh = r["run_hours"]
        print(f"  live cells                   {r['n_live_cells']}")
        print(f"  zero runs in live cells      {r['n_zero_runs_live_cells']:,}")
        print(f"  run length p25/p50/p75       {rh['p25']:.0f} / {rh['p50']:.0f} / {rh['p75']:.0f} h")
        print(f"  run length p90/p99/max       {rh['p90']:.0f} / {rh['p99']:.0f} / {rh['max']:,} h")
        print(f"  zero rows in runs > 24 h     {r['share_of_zero_rows_in_runs_over_24h']:.4f}")
        print(f"  zero rows in runs > 168 h    {r['share_of_zero_rows_in_runs_over_168h']:.4f}")

    h = out["by_hour_local"]
    lo = min(h, key=h.get)
    hi = max(h, key=h.get)
    print(f"  zero share by local hour     min {h[lo]:.4f} at {lo}:00, "
          f"max {h[hi]:.4f} at {hi}:00")
    print("    " + "  ".join(f"{k}:{v:.3f}" for k, v in h.items()))
    m = out["by_month"]
    print("  zero share by month")
    print("    " + "  ".join(f"{k}:{v:.3f}" for k, v in m.items()))

    sh = out["shape"]
    print(f"  observed zero share          {sh['observed_zero_share']:.4f}")
    print(f"  a Poisson would give         {sh['poisson_predicted_zero_share']:.4f}")
    if "negbin_predicted_zero_share" in sh:
        print(f"  a negative binomial would    {sh['negbin_predicted_zero_share']:.4f} "
              f"(excess {sh['excess_zero_share_over_negbin']:+.4f})")
    nz = sh["nonzero"]
    print(f"  non-zero: share equal to 1   {nz['share_equal_to_1']:.4f}")
    print(f"  non-zero p50/p90/p99/max     {nz['p50']:.0f} / {nz['p90']:.0f} / "
          f"{nz['p99']:.0f} / {nz['max']:,}")
    print(f"  non-zero var/mean            {nz['var_over_mean']:.2f}")
    return out



# --------------------------------------------------------------------------
# 3. Which map turns a value into an angle
# --------------------------------------------------------------------------
# Three candidate maps, compared on the same rows. All are fitted on the source
# domain only, which is what the transfer arms do and what S-6 is about.
#
#   minmax      the standard recommendation. Two fitted parameters, and both
#               are single extreme observations -- `CAPE` 22 396 is one row out
#               of 3,4 million and it sets the denominator for all of them.
#   quantile    the same map fitted on p1 and p99 instead, then clipped. One
#               rule, applied uniformly, and a quantile estimated from millions
#               of rows is a stable statistic where a maximum is an accident.
#   arctan      monotone and bounded, so nothing collapses onto a bound. Needs
#               a scale s, taken here as the source interquartile range --
#               a fitted quantity, so this measures whether bounding helps, not
#               whether a parameter-free version would.
#
# A variable with a definitional bound uses that bound instead of any fitted
# one, under every map. `RH2M` is the only candidate that has one.
#
# The quantity reported is effective resolution: the share of the output range
# a domain's middle 50% occupies. A feature arriving at the circuit spread over
# 2% of the dial is close to a constant whatever produced it. Reported both
# within domain and across, because most arms are within-domain and the
# compression problem exists there too.

PHYSICAL_BOUNDS = {"RH2M": (0.0, 100.0)}


def _minmax(x, lo, hi):
    if hi <= lo:
        return np.zeros_like(x)
    return np.clip((x - lo) / (hi - lo), 0.0, 1.0)


def _arctan(x, centre, s):
    if s <= 0:
        return np.full_like(x, 0.5)
    return np.arctan((x - centre) / s) / np.pi + 0.5


def _maps(src: np.ndarray, col: str):
    """Fit all three on the source. Returns name -> callable."""
    lo_p, hi_p = PHYSICAL_BOUNDS.get(col, (None, None))
    lo_x, hi_x = (lo_p, hi_p) if lo_p is not None else (float(src.min()), float(src.max()))
    q1, q99 = np.quantile(src, [0.01, 0.99])
    lo_q, hi_q = (lo_p, hi_p) if lo_p is not None else (float(q1), float(q99))
    med = float(np.median(src))
    iqr = float(np.quantile(src, 0.75) - np.quantile(src, 0.25))
    return {
        "minmax": lambda v: _minmax(v, lo_x, hi_x),
        "quantile": lambda v: _minmax(v, lo_q, hi_q),
        "arctan": lambda v: _arctan(v, med, iqr),
    }, {"physical": lo_p is not None, "extremes": [lo_x, hi_x],
        "quantiles": [lo_q, hi_q], "centre": med, "iqr": iqr}


def _resolution(y: np.ndarray) -> tuple[float, float]:
    """IQR share of the output range, and the share pinned at an extreme."""
    q1, q3 = np.quantile(y, [0.25, 0.75])
    pinned = float(((y <= 1e-12) | (y >= 1.0 - 1e-12)).mean())
    return float(q3 - q1), pinned


def encoding_maps(frames: dict[str, pd.DataFrame], candidates: list[str]) -> dict:
    names = sorted(frames)
    out = {}

    print(f"\n{'=' * 90}\nENCODING MAPS — effective resolution, three candidates (S-6)\n{'=' * 90}")

    for src in names:
        a = frames[src]
        others = [d for d in names if d != src]
        print(f"\n  fitted on {src}")
        print(f"  {'column':<14}{'within: mm':>12}{'qt':>9}{'at':>9}"
              + "".join(f"{tgt[:5] + ': mm':>12}{'qt':>9}{'at':>9}" for tgt in others))
        for c in candidates:
            xa = a[c].dropna().to_numpy()
            if not len(xa):
                continue
            fns, fit = _maps(xa, c)
            row = {"fit": fit, "within": {}, "cross": {}}
            for m, fn in fns.items():
                r, p = _resolution(fn(xa))
                row["within"][m] = {"iqr_share": r, "pinned": p}
            line = f"  {c:<14}" + "".join(
                f"{row['within'][m]['iqr_share']:>12.4f}" if m == "minmax"
                else f"{row['within'][m]['iqr_share']:>9.4f}"
                for m in ("minmax", "quantile", "arctan"))
            for tgt in others:
                xb = frames[tgt][c].dropna().to_numpy()
                row["cross"][tgt] = {}
                for m, fn in fns.items():
                    r, p = _resolution(fn(xb))
                    row["cross"][tgt][m] = {"iqr_share": r, "pinned": p}
                line += "".join(
                    f"{row['cross'][tgt][m]['iqr_share']:>12.4f}" if m == "minmax"
                    else f"{row['cross'][tgt][m]['iqr_share']:>9.4f}"
                    for m in ("minmax", "quantile", "arctan"))
            print(line)
            out[f"{src}/{c}"] = row
        print("  mm = min-max on extremes, qt = min-max on p1/p99 then clip, at = arctan(x/IQR).")
        print("  each number is the share of the output range that domain's middle 50% occupies.")
        print("  higher is better; RH2M uses its definitional bound under all three.")

    # A summary is what the decision turns on, so it prints rather than needing
    # the JSON to be read.
    print(f"\n  --- mean resolution over all candidates ---")
    print(f"  {'':<14}{'minmax':>12}{'quantile':>12}{'arctan':>12}")
    for scope in ("within", "cross"):
        vals = {m: [] for m in ("minmax", "quantile", "arctan")}
        for k, row in out.items():
            for m in vals:
                if scope == "within":
                    vals[m].append(row["within"][m]["iqr_share"])
                else:
                    for tgt in row["cross"]:
                        vals[m].append(row["cross"][tgt][m]["iqr_share"])
        print(f"  {scope:<14}" + "".join(f"{np.mean(vals[m]):>12.4f}"
                                         for m in ("minmax", "quantile", "arctan")))
    return out


# --------------------------------------------------------------------------
# 4. Temporal structure — is the asymmetry a weight or a kind?
# --------------------------------------------------------------------------
def temporal(df: pd.DataFrame, domain: str) -> dict:
    """Diurnal against seasonal amplitude, pooled and per cell.

    Stage 2's first pass found tropis diurnally driven and subtropis seasonally
    driven, from two pooled tables. Per cell is the question that matters: if
    every cell in a domain agrees, one temporal feature serves the domain; if
    cells disagree, no single feature does, and S-3's answer cannot be one
    column per domain.
    """
    t = df[cfg.TARGET]
    zero = (t == 0)

    def amp(by):
        g = zero.groupby(by).mean()
        return float(g.max() - g.min()), g

    di_amp, di = amp(df["hour_of_day_local"])
    se_amp, se = amp(df["month_of_year"])

    per_cell = {}
    for (lat, lon), idx in df.groupby(["lat", "lon"]).groups.items():
        sub = df.loc[idx]
        if sub[cfg.TARGET].sum() == 0:
            continue
        z = (sub[cfg.TARGET] == 0)
        dh = z.groupby(sub["hour_of_day_local"]).mean()
        mh = z.groupby(sub["month_of_year"]).mean()
        fh = sub[cfg.TARGET].groupby(sub["hour_of_day_local"]).mean()
        per_cell[f"{lat},{lon}"] = {
            "diurnal_amplitude": float(dh.max() - dh.min()),
            "seasonal_amplitude": float(mh.max() - mh.min()),
            "peak_hour_local": int(fh.idxmax()),
            "trough_hour_local": int(dh.idxmax()),
            "peak_month": int(sub[cfg.TARGET].groupby(sub["month_of_year"]).mean().idxmax()),
            "total_flashes": int(sub[cfg.TARGET].sum()),
        }

    peaks = [v["peak_hour_local"] for v in per_cell.values()]
    ratios = [v["diurnal_amplitude"] / v["seasonal_amplitude"]
              for v in per_cell.values() if v["seasonal_amplitude"] > 0]

    out = {
        "pooled": {
            "diurnal_amplitude": di_amp,
            "seasonal_amplitude": se_amp,
            "ratio": di_amp / se_amp if se_amp else None,
            "peak_flash_hour_local": int(t.groupby(df["hour_of_day_local"]).mean().idxmax()),
            "peak_flash_month": int(t.groupby(df["month_of_year"]).mean().idxmax()),
        },
        "per_cell": per_cell,
        "peak_hour_spread": {
            "min": int(min(peaks)), "max": int(max(peaks)),
            "distinct": sorted(set(peaks)),
        } if peaks else {},
        "diurnal_over_seasonal": {
            "min": float(min(ratios)), "p50": float(np.median(ratios)),
            "max": float(max(ratios)),
            "n_cells_diurnal_dominant": int(sum(r > 1 for r in ratios)),
            "n_cells": len(ratios),
        } if ratios else {},
    }

    print(f"\n[4] temporal structure")
    p = out["pooled"]
    print(f"  pooled diurnal amplitude     {p['diurnal_amplitude']:.4f}")
    print(f"  pooled seasonal amplitude    {p['seasonal_amplitude']:.4f}")
    print(f"  ratio diurnal/seasonal       {(p['ratio'] or 0):.2f}")
    print(f"  peak flash hour / month      {p['peak_flash_hour_local']}:00 local / month "
          f"{p['peak_flash_month']}")
    if out["peak_hour_spread"]:
        ps = out["peak_hour_spread"]
        print(f"  per-cell peak hour           {ps['min']}:00 to {ps['max']}:00 — {ps['distinct']}")
    if out["diurnal_over_seasonal"]:
        r = out["diurnal_over_seasonal"]
        print(f"  per-cell ratio min/p50/max   {r['min']:.2f} / {r['p50']:.2f} / {r['max']:.2f}")
        print(f"  cells diurnal-dominant       {r['n_cells_diurnal_dominant']} of {r['n_cells']}")
    print(f"  {'cell':<18}{'diurnal':>10}{'seasonal':>10}{'peak h':>8}{'peak m':>8}{'flashes':>12}")
    for k, v in sorted(per_cell.items(), key=lambda kv: -kv[1]["total_flashes"])[:12]:
        print(f"  {k:<18}{v['diurnal_amplitude']:>10.4f}{v['seasonal_amplitude']:>10.4f}"
              f"{v['peak_hour_local']:>8}{v['peak_month']:>8}{v['total_flashes']:>12,}")
    print("  twelve cells with the most flashes; the rest are in the JSON.")
    return out


# --------------------------------------------------------------------------
# Driver
# --------------------------------------------------------------------------
def load(domain: str) -> pd.DataFrame:
    path = cfg.processed_table(domain)
    if not path.exists():
        raise FileNotFoundError(f"{path} does not exist -- run gfd.dataset.build first.")
    df = pd.read_parquet(path)
    df["_cloud_water"] = df["TCLW"] + df["TCIW"]
    return df


def diagnose_domain(domain: str, df: pd.DataFrame) -> dict:
    print(f"\n{'=' * 74}\n{domain.upper()} — {cfg.DOMAINS[domain].label}\n{'=' * 74}")
    return {
        "missingness": diagnose_missingness(df),
        "zeros": diagnose_zeros(df),
        "temporal": temporal(df, domain),
    }


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="Stage 2 diagnosis of the built tables.")
    ap.add_argument("--domain", choices=sorted(cfg.DOMAINS), help="one domain; default both")
    ap.add_argument("--no-json", action="store_true")
    args = ap.parse_args(argv)

    domains = [args.domain] if args.domain else sorted(cfg.DOMAINS)
    frames = {d: load(d) for d in domains}
    results = {d: diagnose_domain(d, frames[d]) for d in domains}

    # Derived features are scaled and encoded like any other, so they belong in
    # this comparison. `cos_sza` in particular: D-27 excluded `lat` and `lon`
    # from the shared transfer set for carrying no cross-domain information,
    # and `cos_sza` is computed from latitude. Whether it inherits that was
    # left unmeasured by D-27 and is answered here.
    frames = {d: with_derived(f).assign(**{c: f[c] for c in ("lat", "lon")})
              for d, f in frames.items()}
    cands = list(frames[domains[0]].columns)
    cross = encoding_maps(frames, cands) if len(domains) > 1 else {}

    if not args.no_json:
        for d, r in results.items():
            p = cfg.PROCESSED_DIR / f"diagnosis_{d}.json"
            p.write_text(json.dumps(r, indent=2), encoding="utf-8")
            print(f"\n[write] {p}")
        if cross:
            p = cfg.PROCESSED_DIR / "diagnosis_encoding_maps.json"
            p.write_text(json.dumps(cross, indent=2), encoding="utf-8")
            print(f"[write] {p}")


if __name__ == "__main__":
    main()
