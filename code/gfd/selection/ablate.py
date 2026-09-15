"""Step 6. Leave-one-out ablation on the selected sets, and the climatology gap.

    python3 -m gfd.selection.ablate
    python3 -m gfd.selection.ablate --domain tropis --n 10

Three things happen here, and the third is the headline.

**Leave-one-out.** Fit on the selected set, then refit once per feature with
that feature removed. The drop in skill is what the feature was worth. This is
the confirmation step of D-21, not the selector: leave-one-out systematically
undervalues correlated features, because removing one lets its partner absorb
the job, and the 2026-09-14 run showed that at scale. Bab VI states the
limitation.

**The climatology gap.** The `full` arm may use `lat`, `lon` and the calendar;
the `meteorology` arm may not. Nothing in the second arm is known in advance of
the weather, so the difference between them is how much of the model's skill is
climatology -- the average lightning for a place and time of year -- and how
much is the atmosphere. §4 calls the model a diagnostic that becomes a forecast
when driven by an NWP system, and only the second arm would survive that
substitution.

Both arms are scored on the same rows with the same estimator, so the gap is a
like-for-like comparison.

**The sweep over N.** The two arms are not one model with features removed --
they are two different selections of the same width, so the comparison is only
fair at a width where both arms can fit what they want. At N = 10 the full arm
spends six slots on space and time and has four left for weather, which is
why "climatology hurts" and "ten slots is too tight" produce the same
signature. Running several widths separates them: if the gap closes as N grows,
the budget was the constraint; if it holds, the climatological features are
genuinely a poor use of a slot.

The sweep also prices N itself. D-22 fixed N = 10 on seed stability and
simulation cost, before the 2026-09-14 ablation showed that ten features score
roughly 0,06 to 0,10 of PR-AUC below twenty-three. Bab IV has to defend that
number, and it is cheaper to defend with the curve beside it.

PROVISIONAL, in two ways that are open on the S-list:

  * the split is 2018-2023 train, 2024 test whole and unreshaped (S-8).
  * features are standardised on training rows (S-5, S-6). Leave-one-out is
    more robust to this than a coefficient method -- each pair is the same
    model with and without one column, scaled identically -- but a feature
    whose verdict flips once scaling is settled is itself telling you the
    scaling choice matters more than assumed.

The estimator is ridge and logistic regression, not the QNN. A feature a linear
model cannot use may still matter to a circuit, so this under-values
non-monotone features -- `VIIWD` is the standing example, high on mutual
information and near zero on Spearman. Read it beside the screen, not instead
of it.
"""

from __future__ import annotations

import argparse
import json

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge, LogisticRegression
from sklearn.metrics import average_precision_score, roc_auc_score

from .. import config as cfg
from .screen import TEST_YEAR, ARMS, build_matrix, screen_arm

# Training rows may be subsampled (§4); test rows never are.
FIT_ROWS = 400_000


def fit_score(Xtr, ytr, Xte, yte, kind, seed):
    """Standardise on training rows, fit, score on the test year.

    `kind` is 'occurrence' -- logistic regression against whether the hour
    flashed, scored by PR-AUC because positives are rare and ROC-AUC flatters
    a rare-positive problem -- or 'count', ridge on log1p over flashing hours
    only, scored by R-squared. Averaged over all rows the count score would be
    swamped by zeros and report almost nothing.
    """
    mu, sd = Xtr.mean(axis=0), Xtr.std(axis=0)
    sd = np.where(sd > 0, sd, 1.0)
    Ztr, Zte = (Xtr - mu) / sd, (Xte - mu) / sd

    if kind == "occurrence":
        m = LogisticRegression(max_iter=2000, random_state=seed)
        m.fit(Ztr, (ytr > 0).astype(int))
        p = m.predict_proba(Zte)[:, 1]
        o = (yte > 0).astype(int)
        return {"pr_auc": float(average_precision_score(o, p)),
                "roc_auc": float(roc_auc_score(o, p))}

    tr, te = ytr > 0, yte > 0
    m = Ridge(alpha=1.0, random_state=seed)
    m.fit(Ztr[tr], np.log1p(ytr[tr]))
    pred, truth = m.predict(Zte[te]), np.log1p(yte[te])
    ss_res = float(((truth - pred) ** 2).sum())
    ss_tot = float(((truth - truth.mean()) ** 2).sum())
    return {"r2": float(1 - ss_res / ss_tot) if ss_tot > 0 else None,
            "n_scored": int(te.sum())}


def primary(kind: str) -> str:
    return "pr_auc" if kind == "occurrence" else "r2"


def ablate_set(train, test, names, kind, seed):
    """Full model, then one refit per feature with it removed."""
    Xtr_all = build_matrix(train)[names]
    Xte_all = build_matrix(test)[names]

    rng = np.random.default_rng(seed)
    idx = rng.choice(len(Xtr_all), size=min(FIT_ROWS, len(Xtr_all)), replace=False)
    A = Xtr_all.iloc[idx].to_numpy(dtype=float)
    ytr = train[cfg.TARGET].to_numpy()[idx]
    B = Xte_all.to_numpy(dtype=float)
    yte = test[cfg.TARGET].to_numpy()

    key = primary(kind)
    full = fit_score(A, ytr, B, yte, kind, seed)
    rows = {}
    for i, n in enumerate(names):
        keep = [j for j in range(len(names)) if j != i]
        s = fit_score(A[:, keep], ytr, B[:, keep], yte, kind, seed)
        rows[n] = {"without": s, "delta": full[key] - s[key]}
    return {"full": full, "features": rows,
            "order": sorted(rows, key=lambda n: -rows[n]["delta"])}


def climatology_gap(out: dict, k: int) -> dict:
    print(f"\n  --- the climatology gap, N = {k} ---")
    print(f"  {'target':<14}{'full':>12}{'meteorology':>14}{'gap':>12}{'share':>10}")
    gaps = {}
    for kind in ("occurrence", "count"):
        key = primary(kind)
        f = out[f"full/{kind}"]["full"][key]
        m = out[f"meteorology/{kind}"]["full"][key]
        gaps[kind] = {"full": f, "meteorology": m, "gap": f - m,
                      "meteorology_share": (m / f) if f else None}
        print(f"  {kind:<14}{f:>12.4f}{m:>14.4f}{f - m:>12.4f}"
              f"{(m / f if f else 0):>10.3f}")
    print("  'share' is how much of the full model's skill survives when nothing known")
    print("  in advance of the weather is allowed. Above 1 means the meteorology arm")
    print("  scored higher, which at a tight N means the climatological features were")
    print("  displacing better predictors rather than adding to them.")
    return gaps


def run_width(train, test, k: int, verbose: bool) -> dict:
    # The selection is re-derived rather than read from a file, so the ablation
    # can never score a set the screen did not produce (§3). Its printing is
    # suppressed -- the screen's own command is where that output belongs.
    import io, contextlib
    with contextlib.redirect_stdout(io.StringIO()):
        sel = {arm: screen_arm(train, arm, k) for arm in ARMS}

    out = {}
    for arm in ARMS:
        for kind in ("occurrence", "count"):
            names = sel[arm][kind]["selected"]
            r = ablate_set(train, test, names, kind, cfg.RANDOM_SEED)
            out[f"{arm}/{kind}"] = {"features": names, **r}
            if not verbose:
                continue
            key = primary(kind)
            print(f"\n  --- {arm} / {kind} — {len(names)} features ---")
            print(f"  full model {key} {r['full'][key]:.4f}")
            print(f"  {'feature':<22}{'delta ' + key:>14}{'':>6}")
            for n in r["order"]:
                d = r["features"][n]["delta"]
                print(f"  {n:<22}{d:>14.5f}{'  <-' if d <= 0 else '':>6}")
            print("  positive means the model got worse without it; '<-' means its removal")
            print("  left the model equal or better, so it paid for no qubit.")

    out["climatology_gap"] = climatology_gap(out, k)
    return out


def run_domain(domain: str, k: int, widths: list[int]) -> dict:
    path = cfg.processed_table(domain)
    if not path.exists():
        raise FileNotFoundError(f"{path} does not exist -- run gfd.dataset.build first.")
    df = pd.read_parquet(path)
    train, test = df[df["year"] != TEST_YEAR], df[df["year"] == TEST_YEAR]

    print(f"\n{'=' * 80}\n{domain.upper()} — {cfg.DOMAINS[domain].label}\n{'=' * 80}")
    print(f"  train {len(train):,} rows 2018-{TEST_YEAR - 1}, "
          f"subsampled to {min(FIT_ROWS, len(train)):,} for fitting")
    print(f"  test  {len(test):,} rows {TEST_YEAR}, whole and unreshaped (§4); "
          f"zero share {float((test[cfg.TARGET] == 0).mean()):.4f}")

    out = {f"N={k}": run_width(train, test, k, verbose=True)}
    for w in widths:
        if w != k:
            print(f"\n  ...sweeping N = {w}")
            out[f"N={w}"] = run_width(train, test, w, verbose=False)

    print(f"\n  --- the gap across widths ---")
    print(f"  {'N':>4}{'occ full':>11}{'occ meteo':>11}{'occ share':>11}"
          f"{'cnt full':>11}{'cnt meteo':>11}{'cnt share':>11}")
    for w in sorted({k, *widths}):
        g = out[f"N={w}"]["climatology_gap"]
        o, c = g["occurrence"], g["count"]
        print(f"  {w:>4}{o['full']:>11.4f}{o['meteorology']:>11.4f}"
              f"{o['meteorology_share']:>11.3f}{c['full']:>11.4f}"
              f"{c['meteorology']:>11.4f}{c['meteorology_share']:>11.3f}")
    print("  a share that falls toward 1 as N grows means the budget was the constraint,")
    print("  not the climatological features. a share that holds means they are a poor")
    print("  use of a slot at any width.")
    return out


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="D-21 step 6, on the selected sets.")
    ap.add_argument("--domain", choices=sorted(cfg.DOMAINS))
    ap.add_argument("--n", type=int, default=15, help="width reported in full; D-24 sets it at 15")
    ap.add_argument("--sweep", type=int, nargs="*", default=[8, 12, 15, 18],
                    help="extra widths for the gap curve; the meteorology arm has 18 features")
    ap.add_argument("--no-json", action="store_true")
    args = ap.parse_args(argv)

    domains = [args.domain] if args.domain else sorted(cfg.DOMAINS)
    results = {d: run_domain(d, args.n, args.sweep) for d in domains}

    print(f"\n{'=' * 80}")
    print("PROVISIONAL. The split is S-8 and the scaling is S-5/S-6. Ridge and logistic")
    print("regression stand in for the QNN and under-value non-monotone features, so")
    print("read this beside the screen's mutual information. Leave-one-out confirms and")
    print("does not select (D-21 step 6): it undervalues correlated features, because")
    print("removing one lets its partner absorb the job. modelled.json is not written.")

    if not args.no_json:
        for d, r in results.items():
            p = cfg.PROCESSED_DIR / f"ablation_{d}.json"
            p.write_text(json.dumps(r, indent=2), encoding="utf-8")
            print(f"\n[write] {p}")


if __name__ == "__main__":
    main()
