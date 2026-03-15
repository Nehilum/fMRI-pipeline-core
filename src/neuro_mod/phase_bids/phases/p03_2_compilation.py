import pandas as pd
import json
import logging
import re
from pathlib import Path
from typing import Dict, Optional, Tuple, List
from neuro_mod.phase_bids.core.schema import AuditSchema  # Step 1: 引入 Schema

logger = logging.getLogger(__name__)

class BidsCompilationStep:
    """
    Phase 3b: Compilation Logic (Refactored for Physical File Expansion & Precise Mapping)
    """

    def __init__(self, config: Dict):
        self.config = config
        self.work_dir = Path(config['paths']['work_dir'])
        
        # Step 1: 实例化 Schema 对象
        self.schema = AuditSchema(config)

        # Location of the raw NIfTI/JSONs
        self.nifti_dir = Path(config['paths'].get('nifti_pool', self.work_dir))

        # Load Heuristics from Config
        heuristics = config.get('heuristics', {})
        raw_patterns = heuristics.get('behavior_patterns', {})
        self.behavior_patterns = {k.lower(): v for k, v in raw_patterns.items()}
        
        raw_vol_map = heuristics.get('volume_to_task', {})
        self.volume_to_task = {int(k): v for k, v in raw_vol_map.items()}
        
        # Threshold to group Mag1/Mag2/Phase into one "Set"
        self.fmap_threshold = heuristics.get('fmap_grouping_threshold', 90)
        
        self.intended_for_map = {} 

    def execute(self, excel_path: Optional[Path] = None) -> Tuple[Path, Path]:
        if excel_path is None:
            reviewed_filename = self.config['paths'].get('audit_review_filename', "audit_sheet_reviewed.xlsx")
            excel_path = self.work_dir / reviewed_filename
            logger.info(f"No input path provided, using configured default: {excel_path}")

        logger.info(f"Phase 3b: Starting compilation using input: {excel_path}")
        
        if not excel_path.exists():
            raise FileNotFoundError(f"Input Excel file not found: {excel_path}")

        # Load original Excel (Scan-level)
        self.raw_df = pd.read_excel(excel_path)
        
        # --- Pipeline Steps ---
        # Step 1 now returns a NEW DataFrame (File-level) instead of modifying in-place
        self.df = self._step_1_inference_and_expansion()
        
        # Initialize output columns if not present after expansion
        # Step 2: 使用 schema.col 替换硬编码列名
        new_cols = [
            self.schema.col.datatype, 
            self.schema.col.suffix, 
            self.schema.col.bids_task, 
            self.schema.col.bids_run, 
            self.schema.col.bids_path, 
            self.schema.col.fmap_set_id, 
            self.schema.col.applied_fmap_set, 
            self.schema.col.processing_note
        ]
        for col in new_cols:
            if col not in self.df.columns:
                self.df[col] = None

        self._step_2_grouping()
        self._step_3_path_generation()
        self._step_4_map_intended_for()

        # --- Export ---
        final_filename = self.config['paths'].get('audit_final_filename', "audit_sheet_final.xlsx")
        output_xlsx = self.work_dir / final_filename
        intended_for_filename = self.config['paths'].get('intended_for_filename', "intended_for_map.json")
        output_json = self.work_dir / intended_for_filename

        # Save Final Excel (Ensure Source paths are included for downstream writing)
        # "_dt_temp" is internal, leaving as string literal
        export_cols = [c for c in self.df.columns if c not in ["_dt_temp"]]
        self.df[export_cols].to_excel(output_xlsx, index=False)
        
        with open(output_json, "w") as f:
            json.dump(self.intended_for_map, f, indent=4)

        logger.info(f"Phase 3b Complete. \nExcel: {output_xlsx} \nJSON: {output_json}")
        return output_xlsx, output_json

    # -------------------------------------------------------------------------
    # Helper Methods
    # -------------------------------------------------------------------------

    def _load_json_content(self, json_path: Path) -> Dict:
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Error loading sidecar {json_path}: {e}")
            return {}

    def _parse_volume_count(self, scan_id):
        match = re.search(r'_(\d+)v_', str(scan_id))
        if match:
            return int(match.group(1))
        return None

    def _resolve_func_task(self, row, scan_id):
        """Logic to determine task name from filename or volume count"""
        # Step 2: 替换列名 Behavior_FileName
        beh_file_raw = row.get(self.schema.col.behavior_filename, "")
        if pd.notna(beh_file_raw) and str(beh_file_raw).lower() != "nan":
            beh_file_clean = str(beh_file_raw).strip().lower()
        else:
            beh_file_clean = ""

        # 1. Behavior Pattern Matching
        if beh_file_clean:
            for pattern, task_name in self.behavior_patterns.items():
                if pattern in beh_file_clean:
                    return task_name, None 

        # 2. Volume Count Matching
        vol_count = self._parse_volume_count(scan_id)
        if vol_count in self.volume_to_task:
            task = self.volume_to_task[vol_count]
            return task, f"Task inferred from volume count ({vol_count}v)"

        return "unknown", f"FAILED to resolve task. Beh:{beh_file_clean}, Vol:{vol_count}"

    # -------------------------------------------------------------------------
    # Step 1: Physical File Expansion (Refactored)
    # -------------------------------------------------------------------------
    
    def _step_1_inference_and_expansion(self) -> pd.DataFrame:
        """
        Scans the directory for EVERY row in input Excel.
        Expands 1 DB Row -> N Physical File Rows.
        Determines Mag1/Mag2/Phase logic here.
        """
        logger.info("Step 1: Expanding rows based on physical files...")
        expanded_rows = []

        for idx, row in self.raw_df.iterrows():
            # Step 2: 替换列名 Scan_ID, Inclusion_Status
            scan_id = row.get(self.schema.col.scan_id)
            status = str(row.get(self.schema.col.inclusion_status, "")).lower()
            
            # Define Scan Directory
            scan_dir = self.nifti_dir / str(scan_id)
            if not scan_dir.exists():
                # Fallback check for flat files if dir doesn't exist
                flat_nii = self.nifti_dir / f"{scan_id}.nii.gz"
                if flat_nii.exists():
                    files = [flat_nii]
                else:
                    # Step 3: 替换状态值 Include (保持 lower() 逻辑)
                    if status == self.schema.status.include.lower():
                        logger.warning(f"Scan data missing for {scan_id}")
                    continue
            else:
                # Scan for ALL NIfTIs
                files = list(scan_dir.glob("*.nii.gz"))
                files.sort(key=lambda x: x.name) # Basic alphanumeric sort

            if not files:
                # Step 3: 替换状态值 Include
                if status == self.schema.status.include.lower():
                    logger.warning(f"No NIfTI files found in {scan_dir}")
                continue

            # --- File Loop ---
            # Prepare to identify fmap components if multiple files exist
            for file_path in files:
                # Create a base new row dict
                new_row = row.to_dict()
                
                # [核心重构 1] 记录绝对路径
                # Step 2: 替换列名 Source_Path_Abs
                new_row[self.schema.col.source_path_abs] = str(file_path.resolve())
                
                # Find corresponding JSON
                # Strategy: Look for file with same name but .json
                json_path = file_path.parent / (file_path.name.replace(".nii.gz", ".json").replace(".nii", ".json"))
                
                sidecar = {}
                if json_path.exists():
                    # Step 2: 替换列名 Source_JSON_Abs
                    new_row[self.schema.col.source_json_abs] = str(json_path.resolve())
                    sidecar = self._load_json_content(json_path)
                else:
                    new_row[self.schema.col.source_json_abs] = None
                    # Step 2: 替换列名 Warnings
                    new_row[self.schema.col.warnings] = "Missing JSON Sidecar"

                # Infer Type from JSON (BidsGuess) or manual rules
                bids_guess_str = str(sidecar.get("BidsGuess", "")).lower()
                
                # Primary Type Detection
                primary_type = "unknown"
                # Step 3: 替换 datatype 枚举值 (func, fmap, dwi, anat)
                if self.schema.dtype.func in bids_guess_str: primary_type = self.schema.dtype.func
                elif self.schema.dtype.fmap in bids_guess_str: primary_type = self.schema.dtype.fmap
                elif self.schema.dtype.dwi in bids_guess_str: primary_type = self.schema.dtype.dwi
                elif self.schema.dtype.anat in bids_guess_str: primary_type = self.schema.dtype.anat
                
                # Fallback for empty BidsGuess but Inclusion=Include
                # Step 3: 替换状态值 Include
                if primary_type == "unknown" and status != self.schema.status.include.lower():
                    continue # Skip expanding strictly excluded unknown files

                # Step 2: 替换列名 DataType
                new_row[self.schema.col.datatype] = primary_type

                # --- Specific Logic per Type ---
                
                # A. FMAP Handling (Mag1 vs Mag2 vs Phase)
                # Step 3: 替换 datatype.fmap
                if primary_type == self.schema.dtype.fmap:
                    image_type = sidecar.get("ImageType", [])
                    if isinstance(image_type, str): image_type = [image_type]
                    image_type_upper = [t.upper() for t in image_type]

                    # 1. Try to use explicit EchoNumber
                    echo_num = sidecar.get("EchoNumber", None)
                    
                    if any("PHASE" in t for t in image_type_upper) or "P" in image_type_upper:
                        if "EchoTime1" in sidecar or "EchoTime2" in sidecar:
                            # Step 2: 替换列名 Suffix
                            new_row[self.schema.col.suffix] = "phasediff"
                    
                    elif any("MAGNITUDE" in t for t in image_type_upper) or "M" in image_type_upper:
                        if echo_num:
                            new_row[self.schema.col.suffix] = f"magnitude{echo_num}"
                        else:
                            # Fallback: Inference by filename sorting position for multiple mags
                            if "e2" in file_path.name or "echo2" in file_path.name.lower():
                                new_row[self.schema.col.suffix] = "magnitude2"
                            else:
                                new_row[self.schema.col.suffix] = "magnitude1"
                    else:
                        # Fallback for Fieldmaps that are just simple spin echo
                        new_row[self.schema.col.suffix] = "epi" 

                # B. FUNC Handling
                # Step 3: 替换 datatype.func
                elif primary_type == self.schema.dtype.func:
                    new_row[self.schema.col.suffix] = "bold"
                    # Step 2: 替换列名 Task_Name
                    existing_task = row.get(self.schema.col.task_name_audit)
                    if pd.notna(existing_task) and existing_task not in ["nan", "unknown", ""]:
                        # Step 2: 替换列名 BIDS_Task
                        new_row[self.schema.col.bids_task] = existing_task
                    else:
                        t_name, t_note = self._resolve_func_task(row, scan_id)
                        new_row[self.schema.col.bids_task] = t_name
                        if t_note:
                            # Step 2: 替换列名 Processing_Note
                            new_row[self.schema.col.processing_note] = t_note

                # C. ANAT
                # Step 3: 替换 datatype.anat
                elif primary_type == self.schema.dtype.anat:
                    if "t2w" in bids_guess_str: new_row[self.schema.col.suffix] = "T2w"
                    elif "flair" in bids_guess_str: new_row[self.schema.col.suffix] = "FLAIR"
                    else: new_row[self.schema.col.suffix] = "T1w"

                # D. DWI
                # Step 3: 替换 datatype.dwi
                elif primary_type == self.schema.dtype.dwi:
                    new_row[self.schema.col.suffix] = "dwi"
                    ped = sidecar.get("PhaseEncodingDirection", "")
                    if ped:
                        new_row[self.schema.col.processing_note] = f"dir-{ped.replace('-', 'minus')}"

                expanded_rows.append(new_row)

        return pd.DataFrame(expanded_rows)

    # -------------------------------------------------------------------------
    # Step 2: Grouping (Sets & Runs)
    # -------------------------------------------------------------------------

    def _step_2_grouping(self):
        """
        Assign Run indices and Fmap Set IDs.
        Refactored: Fmap Set ID groups Mag1, Mag2, and Phasediff together based on time.
        """
        logger.info("Step 2: Grouping scans and assigning Set IDs...")
        
        # Helper for sorting
        # Step 2: 替换列名 Canonical_Timestamp
        self.df["_dt_temp"] = pd.to_datetime(self.df[self.schema.col.canonical_timestamp], errors='coerce')

        # 1. Anat & DWI Run Indexing (Standard)
        # Step 3: 替换 datatype.anat, datatype.dwi
        for dtype in [self.schema.dtype.anat, self.schema.dtype.dwi]:
            # Step 2 & 3: 替换列名和状态值
            rows = self.df[
                (self.df[self.schema.col.datatype] == dtype) & 
                (self.df[self.schema.col.inclusion_status].str.lower() == self.schema.status.include.lower())
            ]
            if dtype == self.schema.dtype.anat:
                # Step 2: 替换列名 Subject_ID_BIDS, BIDS_Session, Suffix
                group_cols = [self.schema.col.subject_bids, self.schema.col.session_bids, self.schema.col.suffix]
            else:
                # DWI 保持原样 (包含 Processing_Note 以区分方向)
                # Step 2: 替换列名 Processing_Note
                group_cols = [self.schema.col.subject_bids, self.schema.col.session_bids, self.schema.col.processing_note]

            if not rows.empty:
                for _, group in rows.groupby(group_cols):
                    self._assign_runs(group)

        # 2. Func Run Indexing
        func_rows = self.df[
            (self.df[self.schema.col.datatype] == self.schema.dtype.func) & 
            (self.df[self.schema.col.inclusion_status].str.lower() == self.schema.status.include.lower())
        ]
        if not func_rows.empty:
            # Step 2: 替换列名 BIDS_Task
            for _, group in func_rows.groupby([self.schema.col.subject_bids, self.schema.col.session_bids, self.schema.col.bids_task]):
                self._assign_runs(group)

        # 3. Fmap Grouping -> [核心重构 2] Fmap_Set_ID
        fmap_rows = self.df[
            (self.df[self.schema.col.datatype] == self.schema.dtype.fmap) & 
            (self.df[self.schema.col.inclusion_status].str.lower() == self.schema.status.include.lower())
        ]
        
        if not fmap_rows.empty:
            # Group by Subject + Session first
            for (sub, ses), group in fmap_rows.groupby([self.schema.col.subject_bids, self.schema.col.session_bids]):
                # Sort strictly by time
                sorted_group = group.sort_values("_dt_temp")
                
                current_set_idx = 0
                last_time = None
                
                # Logic: Iterate through sorted files. If time gap > threshold, increment Set ID.
                # Files within the threshold (Mag1, Mag2, Phase) get same Set ID.
                for _, row in sorted_group.iterrows():
                    curr_time = row["_dt_temp"]
                    idx = row.name # DataFrame Index
                    
                    if pd.isna(curr_time):
                        # Without time, we can't group reliably, assume independent or handle manually
                        # Step 2: 替换列名 Scan_ID
                        scan_id = row.get(self.schema.col.scan_id)
                        # Step 2: 替换列名 Fmap_Set_ID
                        self.df.at[idx, self.schema.col.fmap_set_id] = f"set-unknown-{scan_id}"
                        continue
                        
                    if last_time is None:
                        current_set_idx = 1
                    else:
                        delta = (curr_time - last_time).total_seconds()
                        # If delta is large, it's a new acquisition set.
                        # Using abs() just in case, though it should be sorted.
                        if abs(delta) > self.fmap_threshold:
                            current_set_idx += 1
                    
                    last_time = curr_time
                    self.df.at[idx, self.schema.col.fmap_set_id] = f"{current_set_idx:03d}" # e.g., "001"
                
                # Assign Run IDs for fmaps if necessary (usually run-01 if multiple sets of same type exist)
                # ============================================================
                # 【在此处插入代码】回填 BIDS_Run
                # 逻辑：如果当前 Session 中 Set 的总数 > 1，则需要标记 run-01, run-02
                # ============================================================
                total_sets = current_set_idx
                if total_sets > 1:
                    # 再次遍历当前组，将 Set ID 转换为 Run ID
                    for idx, _ in sorted_group.iterrows():
                        # 获取刚刚填入的 Set ID (例如 "001")
                        set_id_str = self.df.at[idx, self.schema.col.fmap_set_id]
                        try:
                            # 只有它是数字型字符串时才转换 (避免处理 "set-unknown")
                            if set_id_str and set_id_str.isdigit():
                                set_num = int(set_id_str)
                                # Step 2: 替换列名 BIDS_Run
                                self.df.at[idx, self.schema.col.bids_run] = f"{set_num:02d}"
                        except ValueError:
                            pass
                # ============================================================

    def _assign_runs(self, group):
        sorted_group = group.sort_values("_dt_temp")
        count = len(sorted_group)
        needs_run = count > 1
        for i, (idx, row) in enumerate(sorted_group.iterrows()):
            if needs_run:
                # Step 2: 替换列名 BIDS_Run
                self.df.at[idx, self.schema.col.bids_run] = f"{i+1:02d}"

    # -------------------------------------------------------------------------
    # Step 3: Path Generation
    # -------------------------------------------------------------------------

    def _step_3_path_generation(self):
        logger.info("Step 3: Generating BIDS paths...")
        for idx, row in self.df.iterrows():
            # Step 2: 替换列名 DataType
            if pd.isna(row[self.schema.col.datatype]): continue 
            # Step 2 & 3: 替换列名 Inclusion_Status, 状态值 Include
            if str(row[self.schema.col.inclusion_status]).lower() != self.schema.status.include.lower(): continue

            # Step 2: 替换列名
            sub = str(row[self.schema.col.subject_bids]).replace("sub-", "")
            ses = str(row[self.schema.col.session_bids]).replace("ses-", "")
            dtype = row[self.schema.col.datatype]
            suffix = row[self.schema.col.suffix]
            run = row[self.schema.col.bids_run]
            task = row.get(self.schema.col.bids_task)
            proc_note = row.get(self.schema.col.processing_note) # holds dir-xxx for dwi
            
            # Construct Parts
            parts = [f"sub-{sub}", f"ses-{ses}"]
            
            # Step 3: 替换 datatype.func
            if dtype == self.schema.dtype.func and task:
                parts.append(f"task-{task}")
            
            # DWI direction
            # Step 3: 替换 datatype.dwi
            if dtype == self.schema.dtype.dwi and proc_note and "dir-" in str(proc_note):
                parts.append(str(proc_note)) # e.g., dir-AP

            # Run
            if run:
                parts.append(f"run-{run}")

            # Discard/Desc prefix
            # (If needed, insert here)

            parts.append(suffix)
            filename = "_".join(parts) + ".nii.gz"
            
            # Step 2: 替换列名 BIDS_Path
            self.df.at[idx, self.schema.col.bids_path] = f"sub-{sub}/ses-{ses}/{dtype}/{filename}"

    # -------------------------------------------------------------------------
    # Step 4: IntendedFor Mapping (Set-based)
    # -------------------------------------------------------------------------

    def _step_4_map_intended_for(self):
        """
        [核心重构 3]
        Map Func -> Fmap Set.
        Then build Dictionary: Key = Fmap BIDS Path, Value = [Func BIDS Paths]
        """
        logger.info("Step 4: Mapping IntendedFor using Set IDs...")
        
        # Filter valid included rows
        # Step 2 & 3: 替换列名 Inclusion_Status, BIDS_Path, 状态值 Include
        valid_df = self.df[
            (self.df[self.schema.col.inclusion_status].str.lower() == self.schema.status.include.lower()) &
            (pd.notna(self.df[self.schema.col.bids_path]))
        ].copy()
        
        # Sort by time to find nearest fieldmap
        valid_df = valid_df.sort_values("_dt_temp")
        
        # Structure to hold mappings: set_id_key -> list of func paths
        # Using a tuple (Subject, Session, SetID) as key to avoid cross-subject clashes
        set_to_funcs = {}

        # Step 2: 替换列名 Subject_ID_BIDS, BIDS_Session
        for (sub, ses), group in valid_df.groupby([self.schema.col.subject_bids, self.schema.col.session_bids]):
            current_fmap_set = None
            last_fmap_time = None
            
            for _, row in group.iterrows():
                # Step 2: 替换列名 DataType
                dtype = row[self.schema.col.datatype]
                
                # Step 3: 替换 datatype.fmap
                if dtype == self.schema.dtype.fmap:
                    # Update current "active" fmap set
                    # Step 2: 替换列名 Fmap_Set_ID
                    f_set = row.get(self.schema.col.fmap_set_id)
                    if f_set:
                        current_fmap_set = f_set
                        last_fmap_time = row["_dt_temp"]
                        
                        # Initialize list for this set if new
                        set_key = (sub, ses, f_set)
                        if set_key not in set_to_funcs:
                            set_to_funcs[set_key] = []
                
                # Step 3: 替换 datatype.func
                elif dtype == self.schema.dtype.func:
                    # Assign Func to current Fmap Set if valid
                    if current_fmap_set and last_fmap_time:
                        # Check time direction/threshold if strict (optional, assuming "most recent previous")
                        # For simplicity: Use the most recent seen Fmap Set
                        set_key = (sub, ses, current_fmap_set)
                        
                        # BIDS Spec: IntendedFor paths are relative to Subject directory (e.g. "ses-01/func/...")
                        # My BIDS_Path is "sub-01/ses-01/func/..." -> Need to strip sub-xx/
                        # Step 2: 替换列名 BIDS_Path
                        full_path = row[self.schema.col.bids_path]
                        relative_path = "/".join(full_path.split("/")[1:]) # remove sub-xx
                        
                        if set_key in set_to_funcs:
                            set_to_funcs[set_key].append(relative_path)
                            
                        # Record in DF for audit
                        # Step 2: 替换列名 Applied_Fmap_Set
                        self.df.at[row.name, self.schema.col.applied_fmap_set] = current_fmap_set

        # Convert Set-based Map to File-based Map (JSON Output)
        # We need to iterate ALL fmap files, find their Set ID, and assign the func list
        self.intended_for_map = {}
        
        # Step 2 & 3: 替换 datatype.fmap
        fmap_files = valid_df[valid_df[self.schema.col.datatype] == self.schema.dtype.fmap]
        
        for _, row in fmap_files.iterrows():
            sub = row[self.schema.col.subject_bids]
            ses = row[self.schema.col.session_bids]
            f_set = row.get(self.schema.col.fmap_set_id)
            bids_path = row[self.schema.col.bids_path]
            
            # Key for my helper dict
            set_key = (sub, ses, f_set)
            
            # Retrieve associated funcs
            associated_funcs = set_to_funcs.get(set_key, [])
            
            # [核心重构 3 输出] Key = Fmap BIDS Path (Relative to root), Value = List of Funcs
            if associated_funcs:
                self.intended_for_map[bids_path] = associated_funcs

        # Clean up temp col
        if "_dt_temp" in self.df.columns:
            self.df.drop(columns=["_dt_temp"], inplace=True)