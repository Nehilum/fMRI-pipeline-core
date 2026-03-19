#!/usr/bin/env python3
"""
fMRI Behavior Parser Template
=============================
This is a template script demonstrating how to convert raw behavioral log files 
(e.g., from E-Prime, Psychtoolbox, PsychoPy) into the standardized formats expected 
by fMRI-pipeline-core.

fMRI-pipeline-core expects TWO things from your behavior data:
1. A summary CSV (audit_group_summary.csv) used for MRI Time Alignment (MTAAS).
2. A directory of BIDS-compliant _events.tsv files for each functional run.

Instructions:
1. Copy this template to your specific research project's `src/` or `scripts/` folder.
2. Implement your specific parsing logic in `parse_raw_log()`.
3. Run this script BEFORE running `fMRI-pipeline-core bids prepare`.
"""

import os
import csv
import pandas as pd
from datetime import datetime
from pathlib import Path

def parse_raw_log(log_filepath):
    """
    TODO: Implement your custom parsing logic here.
    
    Args:
        log_filepath (str or Path): The path to a raw behavior log file.
        
    Returns:
        tuple: (session_info_dict, events_dataframe)
            - session_info_dict MUST contain:
                - 'Subject': string, e.g., 'sub-01'
                - 'Date': string, e.g., '20231001' (YYYYMMDD)
                - 'Log_Filename': string, the name of this log file
                - 'Log_Time': string, the start time (e.g., '14:30:00.000')
                - 'Task': string, the BIDS task name (e.g., 'rest', 'memory')
            - events_dataframe: a pandas DataFrame with BIDS columns 
              (onset, duration, trial_type, etc.)
    """
    # ---------------------------------------------------------
    # Example logic (Replace this with your actual code)
    # ---------------------------------------------------------
    filename = Path(log_filepath).name
    
    # Fake session info
    session_info = {
        'Subject': 'sub-01',
        'Date': '20231001',
        'Log_Filename': filename,
        'Log_Time': '14:30:00.000', # Usually the time of the first TR trigger
        'Task': 'mytask'
    }
    
    # Fake events dataframe
    events_df = pd.DataFrame({
        'onset': [0.0, 5.0, 10.0],
        'duration': [2.0, 2.0, 2.0],
        'trial_type': ['face', 'house', 'face'],
        'response_time': [0.5, 0.6, 0.4]
    })
    
    return session_info, events_df

def main():
    # 1. Define paths (Adjust to your project)
    raw_logs_dir = Path("data/raw_behavior")
    out_events_dir = Path("data/interim/events_tsv")
    out_summary_csv = Path("data/interim/audit_group_summary.csv")
    
    out_events_dir.mkdir(parents=True, exist_ok=True)
    out_summary_csv.parent.mkdir(parents=True, exist_ok=True)
    
    summary_rows = []
    
    # 2. Iterate through all raw logs
    if not raw_logs_dir.exists():
        print(f"Warning: Raw logs directory {raw_logs_dir} doesn't exist.")
        print("Please create it and add your log files, or update the path.")
        return

    for log_file in raw_logs_dir.glob("*.txt"):  # Change extension as needed
        print(f"Processing: {log_file.name}")
        
        # Parse the custom log
        session_info, events_df = parse_raw_log(log_file)
        
        # Save BIDS _events.tsv
        # Naming convention must match the BOLD NIfTI prefix exactly if possible, 
        # or at least be unique enough that Phase 5 can find it by task/run.
        # Often it's enough to name it `{Subject}_task-{Task}_..._events.tsv`
        events_filename = f"{session_info['Subject']}_task-{session_info['Task']}_events.tsv"
        events_df.to_csv(out_events_dir / events_filename, sep='\t', index=False)
        
        # Append to summary
        summary_rows.append(session_info)
        
    # 3. Save the Master Summary CSV for Phase 3 (MTAAS)
    if summary_rows:
        # Standard columns expected by fMRI-pipeline-core's MTAAS
        master_cols = ['Subject', 'Date', 'Log_Filename', 'Log_Time', 'Task']
        
        # You can have extra columns, but the above are critical.
        master_df = pd.DataFrame(summary_rows)
        master_df.to_csv(out_summary_csv, index=False)
        print(f"\nSuccessfully created summary: {out_summary_csv}")
        print(f"Successfully created {len(summary_rows)} event files in: {out_events_dir}")
        print("\nNext step: Update your config.yaml 'events_source' and 'behavior_logs_summary' to point to these outputs.")

if __name__ == "__main__":
    main()
