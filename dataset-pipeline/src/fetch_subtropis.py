"""Fetch subtropis hourly ERA5, one request per month.

Runs alongside the main gfd_data.era5 process, which is working through
tropis. Same fetch function and therefore the same filenames, so _files
and load_era5 pick these up with no reconciliation.
"""
import time
from gfd_data import era5, config as cfg

d = cfg.SUBTROPIS
todo = [(y, m) for y in range(d.year_start, d.year_end + 1) for m in range(1, 13)]
print(f"[sub] {d.name}: {len(todo)} month-requests")

failed = []
for i, (y, m) in enumerate(todo, 1):
    t0 = time.time()
    try:
        p = era5.fetch_chunk_hourly(d, y, month=m)
        print(f"[sub] {i:3d}/{len(todo)} {y}{m:02d} -> {p.name} ({time.time()-t0:.0f}s)", flush=True)
    except Exception as e:
        failed.append((y, m))
        print(f"[sub] {i:3d}/{len(todo)} {y}{m:02d} FAILED: {type(e).__name__}: {e}", flush=True)
        time.sleep(30)

print(f"[sub] done. {len(failed)} failed: {failed}")
