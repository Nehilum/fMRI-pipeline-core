# fMRI Pipeline Core

A robust, interactive, and Python-native pipeline designed to bridge the gap between messy raw fMRI data (DICOM) and standardized statistical analysis. 

Built on the philosophy of **Guided Checkpoints**, it allows researchers to easily intercept, inspect, and correct metadata during BIDS conversion (Phases 1-5), acts as a smart wrapper for heavy pre-processing engines like fMRIPrep (Phase 6), and natively integrates with Nilearn for downstream analysis (Phase 7+).

## Key Features
- **Phase 1-5 (BIDS Assembler):** Pure Python. Generates interactive Excel/CSV mapping tables for researchers to easily fix acquisition/timestamp mismatches before finalizing BIDS conversion. No containers needed.
- **Phase 6 (Pre-processing Engine):** A simple CLI wrapper that automatically generates and executes complex Singularity/Docker commands for fMRIPrep.
- **Phase 7+ (Analysis Suite):** Pure Python statistical modeling using `Nilearn`, directly ingesting the standardized outputs from Phase 5 (`events.tsv`) and Phase 6 (`_desc-preproc_bold.nii.gz`).

## Requirements
- Python 3.9+
- For Phase 6 only: Docker or Singularity installed on your system/cluster.

## Distribution & Deployment Philosophy

`fMRI-pipeline-core` is designed to be a universal toolbox. We separate **Code** from **Environment**:

1.  **Local Development (Mac/PC)**:
    - No containers needed.
    - Simply `pip install -e .` or `conda env create`.
    - Recommended for script development and interactive Phase 3 mapping.

2.  **Cluster Execution (HPC)**:
    - Use the provided `neuro-mod.def` or `Dockerfile` to build an environment image (`.sif`).
    - The code resides inside the image for "one-click" reliability.

3.  **Where to put the .sif file?**
    - **Never** commit `.sif` files to Git.
    - Store the built image in your **Cluster's Shared Storage** (e.g., `/storage/group/bin/`) or in your specific **Study Folder**.
## Philosophy
Please read our [Design Philosophy](DESIGN_PHILOSOPHY.md) to understand why this project embraces interactive checkpoints over black-box automation.
