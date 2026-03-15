# Core Design Philosophy: fMRI-pipeline-core

## Mission Statement
The `fMRI-pipeline-core` project is designed to bridge the gap between raw, messy fMRI data acquisition and high-level, standardized statistical analysis. Our primary goal is to provide a robust, accessible, and transparent pipeline that empowers fMRI researchers—regardless of their programming expertise—to confidently transform DICOM files into publication-ready results.

## The Core Philosophy: "Guided Checkpoints & Modular Execution"

Unlike many "black-box" neuroimaging pipelines that attempt to process data from start to finish without human intervention, `fMRI-pipeline-core` acknowledges a fundamental truth of neuroimaging research: **Raw data is inherently chaotic.** Acquisition times may not align with behavioral logs, runs might be aborted, and file naming conventions are often inconsistent across different operators or scanners.

To handle this reality gracefully, this pipeline is built on the philosophy of **Guided Checkpoints**. 

### 1. Transparency Through Interactivity (Phase 1-5)
The BIDS transformation process is intentionally decoupled into discrete phases. Rather than failing obscurely when metadata doesn't match, the pipeline generates human-readable spreadsheets (e.g., mapping tables). 
*   **The Checkpoint:** Execution pauses, allowing the researcher to open these tables in Excel or CSV viewers. They can manually align timestamps, correct task names, and verify fieldmap intents using their domain knowledge of the specific experimental session.
*   **The Build:** Once verified, the pipeline resumes, safely constructing a fully compliant BIDS dataset based on the researcher's validated mapping.

### 2. High-Performance Containerization Only Where Necessary (Phase 6)
We reject the idea of forcing researchers to install heavy, complex containers (Docker/Singularity) for simple data wrangling. 
*   **Python Native:** Phases 1-5 (BIDS Conversion) and Phase 7+ (Statistical Analysis) are 100% native Python. They can be installed via a simple `pip install` and run anywhere.
*   **Containerized Heavy-Lifting:** Only the pre-processing engine (Phase 6, utilizing fMRIPrep) relies on Singularity or Docker. The pipeline acts as a smart wrapper, automatically generating and executing the complex container commands on behalf of the user, whether on a local workstation or an HPC cluster (e.g., TSUBAME).

### 3. Integrated Downstream Analysis (Phase 7+)
The pipeline does not abandon the researcher after pre-processing. By embracing the modern Python neuroimaging ecosystem (primarily `Nilearn`), it provides seamless downstream analysis capabilities.
*   Since the BIDS `events.tsv` generated in Phase 5 is mathematically pristine, and Phase 6 (fMRIPrep) outputs standardized derivatives, our Phase 7+ modules can automatically ingest this data. 
*   Researchers can perform First-Level GLM, Second-Level group statistics, and even advanced MVPA directly in Jupyter Notebooks, utilizing the output of the pipeline without writing boilerplate data-loading code.

## Architecture Overview

*   **System I: The BIDS Assembler (Phase 1-5)** - pure Python CLI.
*   **System II: The Pre-processing Engine (Phase 6)** - pure Python wrapper for fMRIPrep Singularity/Docker.
*   **System III: The Analysis Suite (Phase 7+)** - pure Python (Nilearn-based) modules for statistical modeling.

## Target Audience
Designed for cognitive neuroscientists, psychologists, and clinical researchers who need a reliable, transparent way to process fMRI data without becoming full-time software engineers.
