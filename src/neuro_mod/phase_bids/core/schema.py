import logging
import pandas as pd
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

class AuditSchema:
    """
    Centralized Schema Handler.
    Usage:
        schema = AuditSchema(config)
        
        # Access column names
        df[schema.col.scan_id] 
        
        # Access status values
        if row[schema.col.inclusion_status] == schema.status.include:
            ...
    """

    def __init__(self, config: Dict):
        if 'excel_schema' not in config:
            raise ValueError("Config missing 'excel_schema' section.")
        
        self._cfg = config['excel_schema']
        
        # Initialize Categories
        self.col = self._Columns(self._cfg['columns'])
        self.status = self._Status(self._cfg['enums']['status'])
        self.dtype = self._Datatype(self._cfg['enums']['datatype'])

    # ---------------------------------------------------------
    # Nested Classes for Property Access (df[schema.col.scan_id])
    # ---------------------------------------------------------
    class _Columns:
        def __init__(self, col_map: Dict):
            # Phase 3a
            self.scan_id = col_map['scan_id']
            self.experiment_id = col_map['experiment_id']
            self.subject_raw = col_map['subject_raw']
            self.subject_bids = col_map['subject_bids']
            self.session_bids = col_map['session_bids']
            self.protocol_name = col_map['protocol_name']
            self.date_folder = col_map['date_folder']
            self.canonical_timestamp = col_map['canonical_timestamp']
            self.sidecar_time_raw = col_map['sidecar_time_raw']
            
            # Audit
            self.inclusion_status = col_map['inclusion_status']
            self.decision_source = col_map['decision_source']
            self.decision_rationale = col_map['decision_rationale']
            self.discard_prefix = col_map['discard_prefix']
            
            # Behavior / MTAAS
            self.behavior_filename = col_map['behavior_filename']
            self.task_name_audit = col_map['task_name_audit']
            self.mtaas_status = col_map['mtaas_status']
            self.mtaas_offset = col_map['mtaas_offset']
            
            # Phase 3b (Physical)
            self.source_path_abs = col_map['source_path_abs']
            self.source_json_abs = col_map['source_json_abs']
            self.warnings = col_map['warnings']
            
            # Phase 3b (BIDS)
            self.datatype = col_map['datatype']
            self.suffix = col_map['suffix']
            self.bids_task = col_map['bids_task']
            self.bids_run = col_map['bids_run']
            self.bids_path = col_map['bids_path']
            self.processing_note = col_map['processing_note']
            
            # Mapping
            self.fmap_set_id = col_map['fmap_set_id']
            self.applied_fmap_set = col_map['applied_fmap_set']

        def get_required_for_phase3b(self) -> List[str]:
            """Returns columns required to START Phase 3b"""
            return [
                self.scan_id, self.subject_bids, self.session_bids,
                self.inclusion_status, self.behavior_filename
            ]

        def get_required_for_phase5(self) -> List[str]:
            """Returns columns required to START Phase 5"""
            return [
                self.source_path_abs, self.bids_path, self.datatype
            ]

    class _Status:
        def __init__(self, status_map: Dict):
            self.include = status_map['include']
            self.exclude = status_map['exclude']

    class _Datatype:
        def __init__(self, type_map: Dict):
            self.func = type_map['func']
            self.anat = type_map['anat']
            self.dwi = type_map['dwi']
            self.fmap = type_map['fmap']
            self.discard = type_map['discard']
            self.derived = type_map['derived']
    # ---------------------------------------------------------
    # Validation Logic
    # ---------------------------------------------------------
    def validate_input_df(self, df: pd.DataFrame, phase: str = "general"):
        """
        Validates that the input DataFrame complies with the Schema.
        Raises ValueError if critical columns are missing.
        """
        if df is None or df.empty:
            raise ValueError("Input DataFrame is empty.")

        # 1. Determine required columns based on Phase
        required = []
        if phase == "phase3b":
            required = self.col.get_required_for_phase3b()
        elif phase == "phase4" or phase == "phase5":
            required = self.col.get_required_for_phase5()
        
        # 2. Check existence
        missing = [c for c in required if c not in df.columns]
        if missing:
            raise ValueError(f"Schema Validation Failed for {phase}. Missing columns: {missing}")
            
        # 3. Validate Status Values (Warning only to allow partial audits)
        if self.col.inclusion_status in df.columns:
            # Normalize status (strip whitespace)
            # 注意：不改变原 df，只做检查
            unique_status = df[self.col.inclusion_status].astype(str).str.strip().unique()
            valid_set = {self.status.include, self.status.exclude}
            
            # Check if there are values that are NOT in valid_set (ignoring nan/None for now)
            unknowns = [x for x in unique_status if x not in valid_set and x.lower() != 'nan']
            if unknowns:
                logger.warning(f"Schema Warning: Found undefined status values in Excel: {unknowns}")

        logger.info(f"Schema validation passed for {phase}.")