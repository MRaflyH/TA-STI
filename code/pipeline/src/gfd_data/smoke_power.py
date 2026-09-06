"""Availability + shape smoke test for the NASA POWER API.

    python -m gfd_data.smoke_power

Probes the configured parameters at the resolution cfg.TIME_FREQ asks for --
one short window, one grid point -- saves the raw JSON, parses it, and prints
what came back. Run this before the full download so that an unavailable
parameter or a changed response shape costs one request instead of hundreds.

At hourly resolution this hits the POINT endpoint, because POWER has no hourly
regional endpoint (it 404s). All hourly parameters go in a single request, so
one probe covers them all -- and the per-parameter table below shows which of
them actually came back with data rather than an all-missing column.

A parameter that fails should be demoted in cfg.POWER_PARAM_FREQ -- to "D" or
"M", where it is fetched at its own resolution and broadcast -- or dropped from
the feature set with a sentence in Bab IV explaining why.
"""

from __future__ import annotations

from . import config as cfg
from .power import (
    ENDPOINT,
    _windows,
    fetch_point,
    fetch_regional,
    native_points,
    parse_power_json,
)


def _probe_window(freq: str, domain: cfg.Domain) -> tuple[str, str]:
    """One short window, enough to prove the endpoint answers."""
    y = domain.year_end
    if freq == "M":
        return (str(y), str(y))
    if freq == "D":
        return (f"{y}0101", f"{y}0131")
    return (f"{y}0101", f"{y}0107")   # one week of hourly is plenty


def _report(df, label: str) -> None:
    for param, chunk in df.groupby("parameter", sort=True):
        missing = int(chunk["value"].isna().sum())
        flag = "  !! ALL MISSING" if missing == len(chunk) else ""
        print(f"  {param:<12s} {label:<8s} {len(chunk):>7,} records  "
              f"{chunk[cfg.TIME_COL].min()} .. {chunk[cfg.TIME_COL].max()}  "
              f"missing {missing:,}{flag}")


def probe_hourly(domain: cfg.Domain) -> list[str]:
    """One point request carrying every hourly parameter. Returns failures."""
    params = [p for p in cfg.POWER_PARAMS if cfg.power_native_freq(p) == "h"]
    if not params:
        return []

    points = native_points(domain)
    lat, lon = points[len(points) // 2]   # somewhere in the middle of the box
    print(f"  {len(points)} native POWER grid points in the {domain.name} box; "
          f"probing ({lat}, {lon})")

    try:
        path = fetch_point(
            domain, lat, lon, params, _probe_window("h", domain), overwrite=True
        )
    except Exception as exc:  # noqa: BLE001
        print(f"  !! hourly point request failed: {str(exc)[:400]}")
        return params

    df = parse_power_json(path)
    _report(df, "hourly")

    returned = set(df["parameter"].unique())
    dead = {p for p in params
            if p not in returned or df.loc[df["parameter"] == p, "value"].isna().all()}
    return sorted(dead)


def probe_coarse(domain: cfg.Domain) -> list[str]:
    """One regional request per non-hourly parameter. Returns failures."""
    failures = []
    for p in cfg.POWER_PARAMS:
        freq = cfg.power_native_freq(p)
        if freq == "h":
            continue
        try:
            path = fetch_regional(
                domain, p, freq, _probe_window(freq, domain), overwrite=True
            )
        except Exception as exc:  # noqa: BLE001
            print(f"  {p:<12s} {ENDPOINT[freq]:<8s} FAILED -- {str(exc)[:200]}")
            failures.append(p)
            continue
        _report(parse_power_json(path), ENDPOINT[freq])
    return failures


def _budget() -> None:
    """What the full fetch will actually cost, per domain and in total.

    Counted the same way `power.fetch_domain` issues them, rather than by the
    point count alone: with POWER_HOURLY_CHUNK = "Y" every point is requested
    once per year, so the point count is a seventh of the real figure. The old
    version of this function printed the point count and was misleading by
    exactly that factor.
    """
    print("\nFull POWER fetch budget "
          f"(TIME_FREQ={cfg.TIME_FREQ!r}, "
          f"POWER_HOURLY_CHUNK={cfg.POWER_HOURLY_CHUNK!r}):")

    grand = 0
    for dom in cfg.DOMAINS.values():
        hourly_params = [p for p in cfg.POWER_PARAMS
                         if cfg.power_native_freq(p) == "h"]
        n_hourly = 0
        if hourly_params:
            n_hourly = len(native_points(dom)) * len(_windows(dom, "h"))

        n_coarse = sum(
            len(_windows(dom, cfg.power_native_freq(p)))
            for p in cfg.POWER_PARAMS
            if cfg.power_native_freq(p) != "h"
        )

        total = n_hourly + n_coarse
        grand += total
        print(f"  {dom.name:<10s} {n_hourly:>4d} point + {n_coarse:>2d} regional "
              f"= {total:>4d} requests")

    print(f"  {'TOTAL':<10s} {grand:>4d} requests, paced 2 s apart")
    print("  Cached files are skipped, so an interrupted run resumes for free.")


def main() -> None:
    domain = cfg.TROPIS
    print(f"POWER smoke test at {cfg.freq_slug()} resolution "
          f"({domain.name} box, one short window)\n")

    dead = probe_hourly(domain) if cfg.TIME_FREQ == "h" else []
    dead += probe_coarse(domain)

    if dead:
        print(
            f"\n{len(dead)} parameter(s) returned nothing usable: {dead}\n"
            f"Demote them in cfg.POWER_PARAM_FREQ, or drop them from the "
            f"feature set."
        )
    else:
        print("\nAll configured parameters returned data at their configured "
              "resolution.")

    _budget()


if __name__ == "__main__":
    main()
