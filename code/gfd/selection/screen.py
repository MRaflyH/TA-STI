"""Steps 2 to 4 of the pipeline: derive, exclude, rank.

    python3 -m gfd.selection.screen
    python3 -m gfd.selection.screen --domain tropis --n 12

D-21 fixes the sequence and this module runs three of its steps. Nothing is
selected here -- step 5 needs N and step 6 is the ablation.

Step 2, derive. Cyclical time encodings (D-20) plus any other admissible
derivation: a function of existing columns or of a stated external source, with
a physical or cited motivation, given a Bab II paragraph, and ranked on equal
terms with no protection.

Step 3, exclude. One rule: structurally undefined columns go (D-19). D-21
carried a second rule excluding location-identifying columns; D-23 withdrew it.
`lat` and `lon` are ordinary candidates. The test set is the same cells in a
different year, so a model learning that a cell never flashes has learned a
spatial prior, not leaked test information. What the coordinates cost is a
transfer limitation -- 0,0000 effective resolution across domains -- and the
ablation reports it rather than a rule pre-empting it.

Step 4, rank by mRMR. Greedy forward selection maximising relevance minus
redundancy against what is already chosen (Peng, Long & Ding, IEEE TPAMI 2005).
Plain relevance ranking has a known failure -- it selects redundant features,
because it never looks at feature-to-feature relationships -- and `KX` against
`TCWV` at 0,914 is that failure in this data.

**Two targets are ranked separately.** Occurrence is whether the hour flashed
at all, on every training row. Count is how many, on `log1p`, on flashing hours
only. At 94-97% zeros the occurrence question is largely "is this a summer
afternoon", which time and place answer; the count question is "how large is
this storm", which is what the meteorology is for. Ranking only against
occurrence measures half the target (§4 names the target as `flash_count`, not
occurrence), and a feature that ranks low on one may lead the other. Whether
the two orderings differ enough to justify a two-stage model is what this run
is for; it does not settle it, because differing inputs do not prove a split
predicts better. That is the ablation's answer.

Redundancy is **multivariate**, not pairwise. The first version of this module
scored redundancy as the mean absolute Spearman against each chosen feature,
which is the standard formulation and has a hole: it cannot see dependence
involving three or more variables. `cos_sza` is a function of day-of-year, hour
and latitude, so its correlation with any one of them is modest and mRMR
admitted all four as though they were independent. Four columns of time in a
set of ten is what that looks like from the outside.

So redundancy here is the rank R-squared of regressing the candidate on the
already-chosen set: how much of this feature the set can already explain. With
one chosen feature it reduces to rho-squared, so nothing about the method
changes -- it generalises to the multivariate case the original assumes away.
Computed on ranks, so it stays invariant to any monotone rescaling.

Two notes that belong in Bab IV.

*The measures are mixed.* Peng uses mutual information for relevance and for
redundancy. Here relevance is mutual information normalised by the target's
entropy and redundancy is a rank R-squared, both therefore unitless on [0, 1],
so the subtraction is between comparable quantities. It is a deviation from the
original and should be stated as one.

*Rank R-squared sees only monotone dependence.* A feature dependent on the
chosen set in a non-monotone way will not be caught. `VIIWD` has that shape
against the target, so the possibility is not hypothetical.

**This step does not depend on S-5 or S-6.** Mutual information and Spearman
are rank-based, so every monotone rescaling -- min-max, arctan, Yeo-Johnson --
gives an identical ordering. Unlike the ablation, it is not provisional on the
scaling decision.
"""

from __future__ import annotations

import argparse
import json

import numpy as np
import pandas as pd
from sklearn.feature_selection import mutual_info_classif, mutual_info_regression

from .. import config as cfg
from ..dataset import features as feat

TEST_YEAR = 2024
MI_ROWS = 200_000
SEEDS = 5  # the ordering is re-run this many times; a stable order is evidence

# --- step 3, D-21 ---------------------------------------------------------
EXCLUDE_UNDEFINED = ["CIN", "CBH"]          # D-19, the only exclusion rule

# Known in advance for any date, forever: not forecast fields. §4 calls the
# model a diagnostic that becomes a forecast when driven by an NWP system, and
# none of these would come from one. A set built largely on them predicts the
# average lightning for a place and time of year -- real skill, and the same
# answer every year regardless of the weather.
#
# The pipeline is run twice: once with everything, once with these removed. The
# gap between the two arms is how much of the skill is climatology and how much
# is the atmosphere. Neither arm is privileged and no feature is excluded by
# rule -- both are reported.
CLIMATOLOGICAL = ["lat", "lon", "hour_sin", "hour_cos", "doy_sin", "doy_cos", "cos_sza"]

ARMS = {
    "full": "every candidate, D-19 applied",
    "meteorology": "climatological features removed as well",
}


# --- step 2, derivations --------------------------------------------------
def solar_zenith_cos(day_of_year, hour_local, lat_deg):
    decl = np.radians(23.44) * np.sin(2 * np.pi * (day_of_year - 81) / 365.25)
    ha = np.radians(15.0 * (hour_local - 12.0))
    lat = np.radians(lat_deg)
    return np.sin(lat) * np.sin(decl) + np.cos(lat) * np.cos(decl) * np.cos(ha)


def temporal_candidates(df: pd.DataFrame) -> dict[str, np.ndarray]:
    """D-20. Five encodings; the ablation decides which survive."""
    h = df["hour_of_day_local"].to_numpy()
    d = df["day_of_year"].to_numpy()
    return {
        "hour_sin": np.sin(2 * np.pi * h / 24.0),
        "hour_cos": np.cos(2 * np.pi * h / 24.0),
        "doy_sin": np.sin(2 * np.pi * d / 365.25),
        "doy_cos": np.cos(2 * np.pi * d / 365.25),
        "cos_sza": solar_zenith_cos(d, h, df["lat"].to_numpy()),
    }


def derived_candidates(df: pd.DataFrame) -> dict[str, np.ndarray]:
    """Derivations from existing columns. No external source, no freeze touched.

    `dewpoint_depression` -- T2M minus the dew point in matching units. The two
    parents correlate at 0,795 in subtropis, so mRMR will keep one and penalise
    the other; their difference is a distinct quantity, the low-level moisture
    deficit and a proxy for the lifting condensation level. A small depression
    means near-saturated air and a low cloud base.

    `cloud_water` -- column-integrated condensate, liquid plus ice. `TCIW` is
    1st in the subtropis ablation and `TCLW` 1st in the tropis screen, so the
    domains favour different phases; the sum is phase-agnostic.

    Both are ranked against their own parents with no protection, and either
    may lose to the columns it was built from.
    """
    return {
        "dewpoint_depression": df["T2M"].to_numpy() - (df["D2M"].to_numpy() - 273.15),
        "cloud_water": df["TCLW"].to_numpy() + df["TCIW"].to_numpy(),
    }


def build_matrix(df: pd.DataFrame, arm: str = "full") -> pd.DataFrame:
    drop = set(EXCLUDE_UNDEFINED)
    if arm == "meteorology":
        drop |= set(CLIMATOLOGICAL)
    cols = {c: df[c].to_numpy() for c in feat.CANDIDATES
            if c in df.columns and c not in drop}
    cols.update({k: v for k, v in temporal_candidates(df).items() if k not in drop})
    cols.update(derived_candidates(df))
    return pd.DataFrame(cols, index=df.index)


# --- step 4, mRMR ---------------------------------------------------------
def relevance_occurrence(X: pd.DataFrame, occur: pd.Series, seed: int):
    """Normalised mutual information against whether the hour flashed."""
    rs = np.random.default_rng(seed)
    idx = rs.choice(len(X), size=min(MI_ROWS, len(X)), replace=False)
    Xs, os_ = X.iloc[idx], occur.iloc[idx]
    mi = mutual_info_classif(Xs, os_, random_state=seed)
    p = float(os_.mean())
    h_y = -(p * np.log(p) + (1 - p) * np.log(1 - p)) if 0 < p < 1 else 1.0
    meta = {"rows": int(len(Xs)), "base_rate": p, "target_entropy": float(h_y)}
    return pd.Series(mi / h_y, index=X.columns), meta


def relevance_count(X: pd.DataFrame, count: pd.Series, seed: int):
    """Mutual information against log1p(count), on flashing hours only.

    Normalised by the largest value so the column is comparable within this
    ranking. Continuous-target MI has no entropy to divide by, so unlike the
    occurrence figures these are not comparable across domains -- only the
    order within a domain means anything.
    """
    rs = np.random.default_rng(seed)
    idx = rs.choice(len(X), size=min(MI_ROWS, len(X)), replace=False)
    Xs, ys = X.iloc[idx], np.log1p(count.iloc[idx].to_numpy())
    mi = mutual_info_regression(Xs, ys, random_state=seed)
    top = float(mi.max()) if mi.max() > 0 else 1.0
    meta = {"rows": int(len(Xs)), "mean_log1p_count": float(ys.mean()),
            "normaliser": top, "note": "relative within domain only"}
    return pd.Series(mi / top, index=X.columns), meta


def _rank_r2(R: np.ndarray, cand: int, chosen: list[int]) -> float:
    """Share of the candidate's rank variance the chosen set already explains.

    Least squares of the candidate's ranks on the chosen features' ranks. With
    one chosen feature this is exactly rho-squared, so the pairwise formulation
    is the special case. Ridge-stabilised because the chosen set can be
    collinear -- `doy_sin` and `cos_sza` nearly are.
    """
    A = R[:, chosen]
    A = np.column_stack([np.ones(len(A)), A])
    y = R[:, cand]
    G = A.T @ A + 1e-8 * np.eye(A.shape[1])
    beta = np.linalg.solve(G, A.T @ y)
    resid = y - A @ beta
    ss_tot = float(((y - y.mean()) ** 2).sum())
    return float(1.0 - (resid ** 2).sum() / ss_tot) if ss_tot > 0 else 0.0


def mrmr(rel: pd.Series, ranks: np.ndarray, names: list[str], k: int) -> list[dict]:
    """Greedy forward selection: relevance minus multivariate redundancy."""
    pos = {n: i for i, n in enumerate(names)}
    chosen, steps = [], []
    remaining = list(rel.index)
    for _ in range(min(k, len(remaining))):
        if not chosen:
            pens = {c: 0.0 for c in remaining}
        else:
            ci = [pos[c] for c in chosen]
            pens = {c: max(0.0, min(1.0, _rank_r2(ranks, pos[c], ci))) for c in remaining}
        scores = {c: rel[c] - pens[c] for c in remaining}
        pick = max(scores, key=scores.get)
        steps.append({
            "feature": pick,
            "relevance": float(rel[pick]),
            "redundancy": float(pens[pick]),
            "score": float(scores[pick]),
        })
        chosen.append(pick)
        remaining.remove(pick)
    return steps


def rank_target(X, ranks, names, rel_fn, y, k, label, note):
    rels, orders, meta = [], [], None
    for s_ in range(SEEDS):
        r, meta = rel_fn(X, y, cfg.RANDOM_SEED + s_)
        rels.append(r)
        orders.append([st["feature"] for st in mrmr(r, ranks, names, len(names))])

    rel_mean = pd.concat(rels, axis=1).mean(axis=1)
    steps = mrmr(rel_mean, ranks, names, len(names))
    stability = {c: sum(c in o[:k] for o in orders) / SEEDS for c in names}
    pos = {c: float(np.mean([o.index(c) + 1 for o in orders])) for c in names}
    order = [st["feature"] for st in steps]

    print(f"\n  [{label}] {note}")
    print(f"  {'#':>3}  {'feature':<22}{'relevance':>11}{'redundancy':>12}"
          f"{'score':>10}{'in top-k':>10}{'mean pos':>10}")
    for i, st in enumerate(steps, 1):
        c = st["feature"]
        print(f"  {i:>3}  {c:<22}{st['relevance']:>11.4f}{st['redundancy']:>12.4f}"
              f"{st['score']:>10.4f}{stability[c]:>10.2f}{pos[c]:>10.1f}"
              f"{'  <' if i == k else ''}")
    print(f"  '<' marks position {k}, the D-24 width. 'redundancy' is the share of this")
    print(f"  feature's rank variance the already-chosen set explains.")

    return {"meta": meta, "order": order, "steps": steps,
            "stability_top_k": stability, "mean_position": pos, "selected": order[:k]}


def screen_arm(train: pd.DataFrame, arm: str, k: int) -> dict:
    X = build_matrix(train, arm)
    names = list(X.columns)
    # One rank transform per matrix, shared by every redundancy computation.
    # Ranks are what make the step invariant to monotone rescaling (S-5, S-6).
    ranks = X.rank(method="average").to_numpy(dtype=float)

    count = train[cfg.TARGET]
    occur = (count > 0).astype(int)
    flashing = count > 0
    Xf = X[flashing]
    ranks_f = Xf.rank(method="average").to_numpy(dtype=float)

    print(f"\n  --- arm: {arm} — {ARMS[arm]}, {len(names)} features ---")
    out = {
        "n_features": len(names),
        "occurrence": rank_target(
            X, ranks, names, relevance_occurrence, occur, k, "occurrence",
            "did the hour flash — all training rows"),
        "count": rank_target(
            Xf, ranks_f, names, relevance_count, count[flashing], k, "count",
            "how many, log1p — flashing hours only"),
    }
    a, b = out["occurrence"]["selected"], out["count"]["selected"]
    out["overlap"] = sorted(set(a) & set(b))
    print(f"\n  the two stages agree on {len(out['overlap'])} of {k}: {out['overlap']}")
    print(f"  occurrence only: {sorted(set(a) - set(b))}")
    print(f"  count only:      {sorted(set(b) - set(a))}")
    return out


def screen_domain(domain: str, k: int) -> dict:
    path = cfg.processed_table(domain)
    if not path.exists():
        raise FileNotFoundError(f"{path} does not exist -- run gfd.dataset.build first.")
    df = pd.read_parquet(path)
    train = df[df["year"] != TEST_YEAR]

    print(f"\n{'=' * 78}\n{domain.upper()} — {cfg.DOMAINS[domain].label}\n{'=' * 78}")
    print(f"  train {len(train):,} rows, {TEST_YEAR} held out and not read")
    print(f"  flashing hours {int((train[cfg.TARGET] > 0).sum()):,}")

    return {arm: screen_arm(train, arm, k) for arm in ARMS}


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="D-21 steps 2 to 4. Nothing is selected.")
    ap.add_argument("--domain", choices=sorted(cfg.DOMAINS))
    ap.add_argument("--n", type=int, default=15, help="width; D-24 sets it at 15")
    ap.add_argument("--no-json", action="store_true")
    args = ap.parse_args(argv)

    domains = [args.domain] if args.domain else sorted(cfg.DOMAINS)
    results = {d: screen_domain(d, args.n) for d in domains}

    for d in sorted(results):
        print(f"\n{'=' * 78}\n{d.upper()} — TOP {args.n}, BOTH ARMS\n{'=' * 78}")
        print(f"  {'#':>3}  {'full occur':<22}{'full count':<22}"
              f"{'meteo occur':<22}{'meteo count':<22}")
        for i in range(args.n):
            r = results[d]
            print(f"  {i + 1:>3}  "
                  f"{r['full']['occurrence']['selected'][i]:<22}"
                  f"{r['full']['count']['selected'][i]:<22}"
                  f"{r['meteorology']['occurrence']['selected'][i]:<22}"
                  f"{r['meteorology']['count']['selected'][i]:<22}")

    print(f"\n{'=' * 78}")
    print("Steps 2-4 only. Nothing is selected and modelled.json is not written.")
    print("Two arms are reported, not one chosen: the gap between them is how much of")
    print("the skill is climatology and how much is the atmosphere, and only the")
    print("ablation can measure that.")
    print("Whether the two stages differ enough to justify a hurdle model is the")
    print("ablation's answer, not this run's — differing inputs do not prove a split")
    print("predicts better. The ordering is invariant to S-5 and S-6: relevance and")
    print("redundancy are both rank-based.")

    if not args.no_json:
        for d, r in results.items():
            p = cfg.PROCESSED_DIR / f"screen_{d}.json"
            p.write_text(json.dumps(r, indent=2), encoding="utf-8")
            print(f"\n[write] {p}")


if __name__ == "__main__":
    main()
