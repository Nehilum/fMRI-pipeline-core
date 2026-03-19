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

## The Behavior Data Contract (Input Requirements)
To make `fMRI-pipeline-core` universally applicable, it enforces a strict boundary between project-specific data logging and standardized pipelining.

The pipeline **does not** parse E-Prime, Psychtoolbox, or PsychoPy logs. Instead, your project must provide two standardized inputs:
1. **Behavior Summary CSV (`audit_group_summary.csv`)**: Used by Phase 3 MTAAS to temporally align your scans and identify aborted runs. Must contain `Subject`, `Date`, `Log_Filename`, `Log_Time`, and `Task`.
2. **BIDS Events (`_events.tsv`)**: Standard BIDS event files for Phase 5 injection.

> **Note**: We provide templates for these inputs in the `templates/` directory, including a boilerplate Python parser (`behavior_parser_template.py`) you can adapt for your own experiments.

## Distribution & Deployment Philosophy (Docker vs. Singularity)

`fMRI-pipeline-core` is designed to be a universal toolbox. We separate **Code** from **Environment**:

1.  **Local Development (Mac/PC)**:
    - No containers needed. Simply `pip install -e .` or `conda env create`.
    - Recommended for script development and interactive Phase 3 mapping.

2.  **Open-Source Distribution (Docker)**:
    - For general users and the wider BIDS community, Docker is the universal standard for shipping environments. A Dockerfile is provided to build or pull the image anywhere.

3.  **Cluster Execution / HPC (Singularity)**:
    - High-Performance Computing (HPC) clusters usually prohibit Docker (requires root). Therefore, **Singularity (Apptainer)** is the execution standard.
    - Users can effortlessly convert the Docker image to a Singularity image for server use:
      `singularity build neuro-mod.sif docker://your-username/neuro-mod`
    - Alternatively, use the provided `neuro-mod.def` to build the `.sif` file directly.
    - **Where to put the .sif file?** Never commit `.sif` files to Git. Store the built image in your Cluster's Shared Storage (e.g., `/storage/group/bin/`).
## Philosophy
Please read our [Design Philosophy](DESIGN_PHILOSOPHY.md) to understand why this project embraces interactive checkpoints over black-box automation.
