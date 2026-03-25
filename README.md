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
## 🤖 AI-Assisted Configuration (The Prompt Paradigm)
To make `fMRI-pipeline-core` universally applicable, it enforces a strict boundary between project-specific data logs and standardized pipelining.

The core pipeline **does not** automatically parse your specific E-Prime, Psychtoolbox, or PsychoPy logs, nor does it natively understand every hospital's DICOM folder structure.

Instead, we embrace an **AI-Assisted Configuration paradigm**. You don't need to write complicated parsers from scratch. We provide **Master Prompts** that you can copy to an LLM (ChatGPT, Claude) to instantly generate the Python code required for your specific data correctly:

1. [PHASE_1_AI_PROMPT_TEMPLATE.md](PHASE_1_AI_PROMPT_TEMPLATE.md): Generates a custom `IngestStrategy` script to flatten your messy raw MRI DICOMs into a standard sequence format.
2. [BEHAVIOR_PARSER_PROMPT_MTAAS.md](BEHAVIOR_PARSER_PROMPT_MTAAS.md): Generates a script to extract the **Behavior Summary CSV (`audit_group_summary.csv`)** from your logs. This file is strictly required by Phase 3 (MTAAS) to temporally align functional scans.
3. [BEHAVIOR_PARSER_PROMPT_EVENTS.md](BEHAVIOR_PARSER_PROMPT_EVENTS.md): Generates a script to extract BIDS standard **`_events.tsv`** files from your logs. These are injected during Phase 5 for downstream task analysis.

> **Note**: We still provide fallback templates for manual edits in the `templates/` directory, including a boilerplate Python parser (`behavior_parser_template.py`), but using the AI prompts is the recommended, zero-friction path.

## ⏸️ Handling Resting-State and Aborted Scans (The Excel Checkpoint)
Because this pipeline relies on strict behavioral time-matching (MTAAS), functional MRI scans that lack behavioral log files (like resting-state scans, or scans that were aborted midway) will be automatically flagged as **Exclude** during Phase 3 due to missing logs.

**Do not panic. You do not need to write fake CSVs or modify code.** You simply use the pipeline's built-in **Guided Checkpoint** feature:
1. When Phase 3 pauses, open the auto-generated `audit_sheet_auto.xlsx`.
2. Look at your chronological list of scans. Cross-reference them with your handwritten or digital experiment logbook.
3. Find the row for your valid resting-state scan (which will be marked as `Exclude`). 
4. Manually change the dropdown to **`Include`**, and type **`rest`** in the `Task_Name` column.
5. Save the Excel file as `audit_sheet_reviewed.xlsx`.
6. Proceed to Phase 4/5. The pipeline will respect your override and perfectly convert it into a standard `task-rest` BIDS file.
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
