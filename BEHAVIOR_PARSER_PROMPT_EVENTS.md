# 🎬 Phase 5: Behavior Parser Prompt Template (BIDS Events)

This Master Prompt is designed to help you generate a custom Python script that parses your specific behavioral log files (E-Prime, PsychoPy, Presentation, MATLAB, etc.) and generates standardized **BIDS Event files (`_events.tsv`)**.

> [!NOTE]
> BIDS Event files strictly describe the timing of stimuli and user responses during your functional MRI scans. They are typically injected into the BIDS directory during the final assembly stage (Phase 5). 
> 
> *If you need to generate the summary CSV for time alignment (Phase 3 MTAAS), please use `BEHAVIOR_PARSER_PROMPT_MTAAS.md` instead.*

---

## Instructions for Researchers

1. **Copy** the entire text below the "Master Prompt" line.
2. **Paste** it into your AI assistant (ChatGPT, Claude, Gemini).
3. **Attach or Paste** examples of your actual behavioral log files.
4. **Describe your experimental design briefly** (e.g., "Condition A is when users see faces, Condition B is when they see houses").
5. **Run** the generated Python script locally to process all your logs into individual `*_events.tsv` files.

---

## 🚀 Master Prompt (Copy below this line)

**System Role:**
You are an expert Neuroimaging Data Engineer specializing in Python data wrangling and the BIDS (Brain Imaging Data Structure) standard.

**Task:**
I have behavioral log files generated from an fMRI experiment (e.g., E-Prime, PsychoPy, MATLAB). I need you to write a Python script that parses these log files and outputs BIDS-compliant event files (`_events.tsv`). One TSV file should be generated for each functional scan / log file.

**Core Rules & Output Contract (BIDS Events TSV):**
The output MUST be a **tab-separated** file (`.tsv`). According to the BIDS specification, it MUST contain the following mandatory columns, exactly named:
1. `onset`: Start time of the event, measured in seconds from the beginning of the functional MRI scan (usually relative to the first scanner trigger).
2. `duration`: Duration of the event in seconds. (If instantaneous, use `0`).

It SHOULD also optionally contain:
3. `trial_type`: A categorical string defining the condition (e.g., `face`, `house`, `fixation`).
4. `response_time`: The participant's response time in seconds (if applicable).

**Input Data Context:**
Here is a snippet / description of my raw behavior log file:
```text
[[ PASTE YOUR BEHAVIOR LOG HEADERS OR 5 ROWS OF DATA HERE ]]
```

**Experimental Design:**
Here is what my columns mean and how to calculate the onset times:
```text
[[ DESCRIBE HOW TO CALCULATE ONSET (e.g., "Subtract the 'Trigger_Time' column from the 'Stimulus_Start' column and divide by 1000 to get seconds.") ]]
```

**Your Requirements:**
1. Write a robust Python script using `pandas` or built-in `csv` module.
2. Read my raw logs and calculate the `onset` and `duration` accurately in seconds.
3. Map the trial conditions to a clean `trial_type` string.
4. Export the data to `*_events.tsv` files.
5. Provide detailed comments on the mathematical calculation for the `onset` column.
6. Only output the Python code. No conversational filler.
