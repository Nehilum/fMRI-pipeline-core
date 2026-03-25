# Future Development tasks for fMRI-pipeline-core

## 🟢 [RESOLVED] Graceful Degradation for Rest-State/No-Behavior fMRI
**Priority**: High
**Status**: **Resolved via Architecture/Documentation (2026-03)**
**Conclusion**: Instead of changing Python code to guess resting states or forcing users to generate dummy CSVs, the pipeline officially adopts the **Guided Checkpoint Override** paradigm. 
- Scans without behavior logs are safely defaulting to `Exclude` (UNMATCHED_MRI).
- Users simply open `audit_sheet_auto.xlsx`, chronologically identify the resting-state scan using their lab notes, and manually flip it to `Include` with `Task_Name="rest"`.
- This ensures absolute security against accidental inclusion of bad scans while providing a zero-code way to process resting-state data perfectly.
