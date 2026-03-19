# 🧙 Phase 1: AI Adapter Prompt Template

This document provides a **Master Prompt** that you can copy and paste into any Large Language Model (like GPT-4, Claude 3, or Gemini 1.5) to automatically generate the Python code required for your specific MRI raw data structure.

---

## Instructions for Researchers

1.  **Copy** the entire content under the "Master Prompt" section below.
2.  **Paste** it into your favorite AI chat window.
3.  **Replace** the section `[[ PASTE YOUR DIRECTORY TREE HERE ]]` with the output of the terminal command `tree -L 3 [Your_Raw_Data_Path]` or a manual description of your files.
4.  **Wait** for the AI to generate your `my_custom_ingestor.py` script.
5.  **Use it** as a reference or plug it into the pipeline's plug-in system.

---

## 🚀 Master Prompt (Copy below this line)

**System Role:** 
You are an expert Neuroimaging Data Engineer specializing in BIDS (Brain Imaging Data Structure) and Python-native fMRI pipelines.

**Task:**
My fMRI raw data structure from the scanner is non-standard. I need you to write a custom Python script (Phase 1 Ingestor) that prepares these files for a standardized processing pipeline. 

**Core Objective:**
Convert my messy raw storage (ZIPs, nested folders, etc.) into a flat, standardized DICOM directory structure while generating a list of `ConversionEntry` objects that track the metadata.

### 📚 The Software "Contract" (Python Interface)
Your generated code **must** follow these class definitions exactly. Do not use external libraries other than standard Python libraries (zipfile, shutil, pathlib, logging, re, dataclasses).

```python
from dataclasses import dataclass, field
from typing import Optional, List, Any
from enum import Enum
from pathlib import Path
from datetime import datetime
from abc import ABC, abstractmethod

# 1. Processing Status
class ProcessStatus(Enum):
    PENDING = "pending"
    SKIPPED = "skipped"
    SUCCESS = "success"
    FAILED = "failed"

# 2. Identity (Who/When/Where)
@dataclass
class SeriesIdentity:
    subject_id_raw: str    # Original Subject ID from folder
    date_folder: str       # Original Session/Date folder name
    scan_folder: str       # Original Scan/Sequence folder name
    time_str_raw: str = "" # Rough time string extracted from filenames (optional)

# 3. Artifacts (Physical Files)
@dataclass
class DicomArtifacts:
    dicom_path: Path      # Path to the directory containing .dcm files

# 4. Record Container
@dataclass
class SeriesRecord:
    identity: SeriesIdentity
    dicom: Optional[DicomArtifacts] = None

# 5. Metadata (Time Alignment)
@dataclass
class TimeMetadata:
    zip_time_raw: str = "" # HHMMSS extracted from zip filename

# 6. The Master Object: ConversionEntry
@dataclass
class ConversionEntry:
    id: str               # Unique ID (e.g. subject_session_scan)
    source: SeriesRecord
    time_meta: TimeMetadata = field(default_factory=TimeMetadata)
    status: ProcessStatus = ProcessStatus.PENDING

# 7. The Base Strategy to Implement
class IngestStrategy(ABC):
    def __init__(self, source_root: Path, target_dicom_root: Path):
        self.source_root = source_root
        self.target_root = target_dicom_root

    @abstractmethod
    def run(self) -> List[ConversionEntry]:
        """
        Implementation logic:
        1. Traverse self.source_root
        2. Identify MRI scans (e.g., zip files or directories)
        3. Extract/Flatten DCM files to self.target_root / subject / session / scan
        4. Populate and return a list of ConversionEntry objects
        """
        pass
```

### 📂 My Current Data Structure
Here is the structure of my raw data (input for `source_root`):
```text
[[ PASTE YOUR DIRECTORY TREE HERE ]]
```

### 🛠️ Your Requirements
1.  Write a class named `CustomIngestor` that inherits from `IngestStrategy`.
2.  Implement the `run()` method.
3.  Include robust error handling (Try/Except) for each scan.
4.  Ensure it "flattens" nested DICOM structures (move all `.dcm` files to the root of the target scan directory).
5.  Extract any rough time information from filenames if possible.
6.  Only output the Python code. No conversational filler.

---
