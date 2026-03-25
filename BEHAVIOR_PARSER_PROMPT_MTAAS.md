# 🧠 Phase 3: Behavior Parser Prompt Template (MTAAS Summary)

This Master Prompt is designed to help you generate a custom Python script that parses your specific behavioral log files (E-Prime, PsychoPy, Presentation, MATLAB, etc.) and generates the exact summary CSV required by the **fMRI-pipeline-core Phase 3 (MTAAS)** for temporal alignment.

> [!IMPORTANT]
> This prompt is ONLY for generating the summary CSV for time alignment. Generating trial-by-trial BIDS `events.tsv` files requires a separate, project-specific prompt or script, as trial conditions heavily depend on your experimental design.

---

## Instructions for Researchers

1. **Copy** the entire text below the "Master Prompt" line.
2. **Paste** it into your AI assistant (ChatGPT, Claude, Gemini).
3. **Attach or Paste** examples of your actual behavioral log files (a few rows of CSV/TXT/MAT), so the AI understands your data structure.
4. **Run** the generated Python script locally to process all your logs into a single `audit_group_summary.csv`.
5. **Point** your `config.yaml` to this generated CSV (`paths.behavior_logs_summary`).

---

## 🚀 Master Prompt (Copy below this line)

**System Role:**
You are an expert Neuroimaging Data Engineer specializing in Python data wrangling and the BIDS standard.

**Task:**
I have behavioral log files generated from an fMRI experiment (e.g., E-Prime, PsychoPy, MATLAB). I need you to write a Python script that parses these log files and outputs a single aggregated CSV file (`audit_group_summary.csv`). This CSV is strictly required by the MTAAS (Meta Time Alignment Audit System) in my pipeline to automatically link functional MRI scans with behavioral logs based on machine timestamps.

**Core Rules & Output Contract:**
The script MUST output a CSV file with EXACTLY the following column names. The pipeline's hardcoded loader relies on these specific strings:

1. `Subject_ScanID`: The raw subject ID matching the DICOM folders (e.g., `sub-01` or `H875574`).
2. `Selected_Files`: A string representing the behavior file name or identifier. **CRITICAL:** This string MUST contain a 14-digit continuous timestamp (`YYYYMMDDHHMMSS`) anywhere within it. The pipeline uses `re.compile(r"(\d{14})")` to extract the time from this column. If your logs only contain standard dates (e.g. `2024-03-05 14:30:22`), your script MUST format it to `20240305143022` and inject it into this column (e.g., `log_20240305143022.csv`).
3. `FileName`: The exact same value as `Selected_Files` (required for redundant compatibility with legacy pipeline mappers). 
4. `Task`: The task name identified from the log (e.g., `rest`, `mod`, `per`). This must match the task names specified in my BIDS configuration.

**Input Data Context:**
Here is a snippet / description of my raw behavior log file:
```text
[[ PASTE YOUR BEHAVIOR LOG HEADERS OR 5 ROWS OF DATA HERE ]]
```

**Your Requirements:**
1. Write a robust Python script using `pandas` or `csv`.
2. Extract the Subject ID, the Exact Start/End Time, and the Task type from my logs.
3. Convert the parsed time into the strict 14-digit format `YYYYMMDDHHMMSS` and synthesize the `Selected_Files` column.
4. Export the final DataFrame to `audit_group_summary.csv`.
5. Include Try/Except blocks to handle missing or corrupted log files gracefully.
6. Only output the Python code, with brief comments explaining the logic.
