from gfd_model import experiments as E
for stage in ("occurrence", "count"):
    for seed in (0, 1, 2):
        print(f"### {stage} seed={seed} ###")
        E.run_sweep("train_rows", stage=stage, seed=seed)
