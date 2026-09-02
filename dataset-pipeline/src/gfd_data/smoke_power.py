"""One-parameter smoke test for the NASA POWER API.

    python -m gfd_data.smoke_power

Fetches T2M for the tropical domain, saves the raw JSON, parses it, and prints
what came back. Run this before the full download so that a shape mismatch
costs you one request instead of twelve.
"""

from __future__ import annotations

from . import config as cfg
from .power import fetch_parameter, parse_power_json


def main() -> None:
    path = fetch_parameter(cfg.TROPIS, "T2M", overwrite=True)
    print(f"\nraw payload: {path}")

    df = parse_power_json(path)
    print(f"\nparsed {len(df):,} records")
    print(df.head(8).to_string(index=False))
    print("\ngrid points :", df[["lat", "lon"]].drop_duplicates().shape[0])
    print("month range :", df["month"].min(), "->", df["month"].max())
    print("value range :", df["value"].min(), "->", df["value"].max())
    print("missing     :", int(df["value"].isna().sum()))


if __name__ == "__main__":
    main()
