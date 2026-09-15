"""Leave-one-out ablation. What each feature is worth.

    python3 -m gfd.selection.ablate
    python3 -m gfd.selection.ablate --domain tropis

Fit the model on every feature, then refit 23 more times with one feature
removed each time. The drop in skill is what that feature was worth. This is
the strongest justification available (INSTRUCTIONS §5) and what Bab VI leads
with.

PROVISIONAL. Two inputs are unsettled:

  * the split is 2018-2023 train, 2024 test. S-8.
  * features are standardised on training rows. S-5 and S-6 are open, and
    ridge is scale-sensitive, so a coefficient-based method would move with
    that choice. Leave-one-out is more stable than it looks -- each pair is
    the same model with and without one column, scaled identically -- but a
    feature whose verdict flips once scaling is settled is itself telling you
    that the scaling choice matters more than assumed.

The estimator is ridge, per §5, not the QNN. It is a stand-in whose job is to
rank contributions cheaply and reproducibly. A feature that a linear model
cannot use may still matter to a circuit, so this under-values non-monotone
features -- which is exactly why the screen reports mutual information
alongside, and why both go in Bab VI rather than either alone.

Two targets are scored because they answer different questions. Occurrence is
did it flash at all, and at 94-97% zeros that is most of the problem. Count is
how much, on log1p, and is scored on flashing hours only -- averaged over all
rows it would be swamped by zeros and report almost nothing.
"""

from __future__ import annotations

import argparse
import json

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge, LogisticRegression
from sklearn.metrics import average_precision_score, roc_auc_score

from .. import config as cfg
from ..dataset import features as feat
from .screen import TEST_YEAR, temporal_candidates

# D-19: structurally undefined, dropped from both domains, never imputed.
DROPPED = ["CIN", "CBH"]

# D-20: all five enter the ablation; the ablation decides which survive.
TEMPORAL = ["hour_sin", "hour_cos", "doy_sin", "doy_cos", "cos_sza"]

# Occurrence is fitted on a subsample because logistic regression on millions
# of rows is slow and adds nothing. Training rows may be subsampled (§4); test
# rows never are.
FIT_ROWS = 400_000


def build(df: pd.DataFrame) -> pd.DataFrame:
    cols = {c: df[c].to_numpy()
            for c in feat.CANDIDATES if c in df.columns and c not in DROPPED}
    temps = temporal_candidates(df)
    cols.update({k: v for k, v in temps.items() if k in TEMPORAL})
    return pd.DataFrame(cols, index=df.index)


def score_once(Xtr, ytr_occ, ytr_cnt, Xte, yte_occ, yte_cnt, seed):
    """Fit both heads on the given columns and score on the test year."""
    mu, sd = Xtr.mean(axis=0), Xtr.std(axis=0)
    sd = np.where(sd > 0, sd, 1.0)
    Ztr, Zte = (Xtr - mu) / sd, (Xte - mu) / sd

    clf = LogisticRegression(max_iter=2000, random_state=seed)
    clf.fit(Ztr, ytr_occ)
    p = clf.predict_proba(Zte)[:, 1]

    # Count head on flashing hours only, on log1p per §4.
    m_tr, m_te = ytr_cnt > 0, yte_cnt > 0
    reg = Ridge(alpha=1.0, random_state=seed)
    reg.fit(Ztr[m_tr], np.log1p(ytr_cnt[m_tr]))
    pred = reg.predict(Zte[m_te])
    truth = np.log1p(yte_cnt[m_te])
    ss_res = float(((truth - pred) ** 2).sum())
    ss_tot = float(((truth - truth.mean()) ** 2).sum())

    return {
        "pr_auc": float(average_precision_score(yte_occ, p)),
        "roc_auc": float(roc_auc_score(yte_occ, p)),
        "r2_count_nonzero": float(1 - ss_res / ss_tot) if ss_tot > 0 else None,
    }


def ablate_domain(domain: str) -> dict:
    path = cfg.processed_table(domain)
    if not path.exists():
        raise FileNotFoundError(f"{path} does not exist -- run gfd.dataset.build first.")
    df = pd.read_parquet(path)

    tr_mask = df["year"] != TEST_YEAR
    train, test = df[tr_mask], df[~tr_mask]
    Xtr_all, Xte_all = build(train), build(test)
    names = list(Xtr_all.columns)

    rng = np.random.default_rng(cfg.RANDOM_SEED)
    idx = rng.choice(len(Xtr_all), size=min(FIT_ROWS, len(Xtr_all)), replace=False)
    Xtr_all = Xtr_all.iloc[idx]
    ytr = train[cfg.TARGET].to_numpy()[idx]
    yte = test[cfg.TARGET].to_numpy()

    print(f"\n{'=' * 80}\n{domain.upper()} — {cfg.DOMAINS[domain].label}\n{'=' * 80}")
    print(f"  train {len(Xtr_all):,} sampled from {int(tr_mask.sum()):,} rows, "
          f"2018-{TEST_YEAR - 1}")
    print(f"  test  {len(test):,} rows, {TEST_YEAR}, whole and unreshaped (§4)")
    print(f"  features {len(names)} — {len(names) - len(TEMPORAL)} meteorological "
          f"+ {len(TEMPORAL)} temporal")
    print(f"  test zero share {float((yte == 0).mean()):.4f}, "
          f"flashing hours {int((yte > 0).sum()):,}")

    A = Xtr_all.to_numpy(dtype=float)
    B = Xte_all.to_numpy(dtype=float)
    otr, ote = (ytr > 0).astype(int), (yte > 0).astype(int)

    full = score_once(A, otr, ytr, B, ote, yte, cfg.RANDOM_SEED)
    print(f"\n  full model   PR-AUC {full['pr_auc']:.4f}   ROC-AUC {full['roc_auc']:.4f}"
          f"   R2(count|flash) {full['r2_count_nonzero']:.4f}")

    rows = {}
    for i, name in enumerate(names):
        keep = [j for j in range(len(names)) if j != i]
        s = score_once(A[:, keep], otr, ytr, B[:, keep], ote, yte, cfg.RANDOM_SEED)
        rows[name] = {
            "without": s,
            "delta_pr_auc": full["pr_auc"] - s["pr_auc"],
            "delta_roc_auc": full["roc_auc"] - s["roc_auc"],
            "delta_r2": (full["r2_count_nonzero"] - s["r2_count_nonzero"])
            if full["r2_count_nonzero"] is not None else None,
        }

    order = sorted(rows, key=lambda k: -rows[k]["delta_pr_auc"])
    print(f"\n  leave-one-out — drop in skill when the feature is removed")
    print(f"  {'feature':<14}{'d PR-AUC':>12}{'d ROC-AUC':>12}{'d R2':>12}{'':>4}")
    for n in order:
        r = rows[n]
        flag = "  <-" if r["delta_pr_auc"] <= 0 else ""
        print(f"  {n:<14}{r['delta_pr_auc']:>12.5f}{r['delta_roc_auc']:>12.5f}"
              f"{(r['delta_r2'] or 0):>12.5f}{flag}")
    print("  positive means the model got worse without it. '<-' marks features whose")
    print("  removal left occurrence skill equal or better — they paid for no qubit.")

    return {"full": full, "n_features": len(names), "features": rows, "order": order}


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="Provisional leave-one-out ablation.")
    ap.add_argument("--domain", choices=sorted(cfg.DOMAINS), help="one domain; default both")
    ap.add_argument("--no-json", action="store_true")
    args = ap.parse_args(argv)

    domains = [args.domain] if args.domain else sorted(cfg.DOMAINS)
    results = {d: ablate_domain(d) for d in domains}

    print(f"\n{'=' * 80}")
    print("PROVISIONAL. The split is S-8 and the scaling is S-5/S-6. Ridge is a stand-in")
    print("for the QNN and under-values non-monotone features — read beside the screen's")
    print("mutual information, not instead of it. Nothing is selected; modelled.json is")
    print("not written.")

    if not args.no_json:
        for d, r in results.items():
            p = cfg.PROCESSED_DIR / f"ablation_{d}.json"
            p.write_text(json.dumps(r, indent=2), encoding="utf-8")
            print(f"\n[write] {p}")


if __name__ == "__main__":
    main()
