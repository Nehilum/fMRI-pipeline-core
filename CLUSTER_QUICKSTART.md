# Cluster Quickstart Guide (Singularity)

This guide contains the exact, tested commands for running `fMRI-pipeline-core` on the cluster where native Python/Conda is unavailable.

## 0. Prerequisite: Environment Variables
Run this **once per session** in your terminal to ensure the container can find our code:
```bash
export SINGULARITYENV_PYTHONPATH=/app/src
```

## 1. Phase 1-3.1: BIDS Prepare (Audit)
Generates the initial mapping Excel file.
```bash
singularity exec --bind .:/app,/storage:/storage ../neuro-mod.sif \
    python3 -m neuro_mod.cli bids prepare --config configs/server_test.yaml
```
**Action Required**:
1. Download `work/audit_sheet_auto.xlsx`.
2. Review and save as `work/audit_sheet_reviewed.xlsx`.
3. Upload back to the server directory specified in your config (`work_dir`).

## 2. Phase 3.2-5: BIDS Build (Finalize)
Constructs the actual BIDS directory structure.
```bash
singularity exec --bind .:/app,/storage:/storage ../neuro-mod.sif \
    python3 -m neuro_mod.cli bids build --config configs/server_test.yaml
```

## 3. Phase 6: fMRIPrep (Execution)
Check the generated command (Dry-run):
```bash
singularity exec --bind .:/app,/storage:/storage ../neuro-mod.sif \
    python3 -m neuro_mod.cli fmriprep run --config configs/server_test.yaml --dry-run
```

Run the actual preprocessing:
```bash
singularity exec --bind .:/app,/storage:/storage ../neuro-mod.sif \
    python3 -m neuro_mod.cli fmriprep run --config configs/server_test.yaml
```
```bash
singularity exec --bind .:/app,/storage:/storage ../neuro-mod.sif \
    python3 -m neuro_mod.cli fmriprep run --config configs/server_test.yaml --dry-run > run_fmriprep.sh
bash run_fmriprep.sh
```
## Help
Run `singularity exec ../neuro-mod.sif python3 -m neuro_mod.cli --help` for full command documentation.
