# Future Development tasks for fMRI-pipeline-core

## Graceful Degradation for Rest-State/No-Behavior fMRI
**Priority**: High
**Description**: Currently, Phase 3 (MTAAS) strictly expects `behavior_logs_summary` to evaluate functional scans. If a user only has resting-state fMRI (which produces no behavioral logs), the pipeline might fail or aggressively exclude scans.
**Action Items**:
- Add a configuration toggle (e.g., `enable_mtaas: false` or automatically detect empty `behavior_logs_summary`).
- If skipped, safely default to setting all valid `func` scans' `inclusion_status` to `"Include"`.
- Ensure Phase 5 skips looking for `_events.tsv` for resting-state scans (which is already somewhat handled via a try-except/warning, but should be formalized).
