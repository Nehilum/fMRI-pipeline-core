import logging
import re
import csv
from pathlib import Path
from typing import List, Dict, Optional, Any, Tuple
from dataclasses import dataclass
from datetime import datetime

# BIDS Converter Imports
from neuro_mod.phase_bids.core.models import ConversionEntry

# MTAAS Core Imports
from .mri_audit.models import MriEvent, RespEvent, AuditBucket
from .mri_audit.loaders import DataLoader
from .mri_audit.bucketing import create_buckets
from .temporal_matcher.solver import TemporalAligner
from .mri_audit.verdict import VerdictJudge

logger = logging.getLogger(__name__)

@dataclass
class MtaasResult:
    status: str = "UNCHECKED"
    task_name: str = ""
    filename: str = ""
    offset: float = 0.0
    comments: str = ""
    is_matched: bool = False

class MtaasAdapter:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.resp_log_path = config['paths'].get('behavior_logs_summary')
        
        self.tr_pattern = re.compile(r"_TR([\d\.]+)")
        self.vol_pattern = re.compile(r"_(\d+)v")
        
        self.loader = DataLoader()
        self.aligner = TemporalAligner(tolerance_sec=config.get('mtaas_tolerance', 5.0))
        self.judge = VerdictJudge()
        
        self.buckets: Dict[Any, AuditBucket] = {}
        self.match_results: Dict[Any, Any] = {}
        self.verdicts: Dict[Any, Any] = {}
        self.task_mapping: Dict[str, str] = {}

    def _compute_offset(self, matched_pair: Tuple, mri_time: float, log_time: float) -> float:
        """
        [新增] 统一计算 Offset 的逻辑，避免代码重复。
        """
        if len(matched_pair) >= 3:
            return matched_pair[2]
        return mri_time - log_time

    def run_audit(self, entries: List[ConversionEntry]) -> Dict[str, MtaasResult]:
        logger.info("Starting MTAAS Audit (Read-Only Mode)...")
        
        results: Dict[str, MtaasResult] = {}
        mri_events: List[MriEvent] = []

        for entry in entries:
            res = MtaasResult(status="SKIPPED")
            if self._is_audit_target(entry):
                m_evt = self._to_mri_event(entry)
                if m_evt:
                    mri_events.append(m_evt)
                    res.status = "UNCHECKED"
                else:
                    res.comments = "Missing Timestamp"
            results[entry.id] = res

        if not mri_events:
            logger.warning("No valid BOLD entries found for auditing.")
            return results

        if not self.resp_log_path or not Path(self.resp_log_path).exists():
            logger.error(f"Log summary not found: {self.resp_log_path}")
            return results
            
        self._load_task_mapping(self.resp_log_path)
        
        try:
            resp_events, _ = self.loader.load_resp(self.resp_log_path)
        except Exception as e:
            logger.error(f"Failed to load response logs: {e}")
            return results

        self.buckets = create_buckets(mri_events, resp_events)

        for key, bucket in self.buckets.items():
            m_times = [e.end_timestamp for e in bucket.mri_events]
            r_times = [e.timestamp for e in bucket.resp_events]

            match_result = self.aligner.align(m_times, r_times)
            verdict = self.judge.judge(match_result, len(m_times), len(r_times))
            
            self.match_results[key] = match_result
            self.verdicts[key] = verdict

            for m_idx, mri_evt in enumerate(bucket.mri_events):
                scan_id = mri_evt.scan_id
                matched_pair = next((p for p in match_result.pairs if p[0] == m_idx), None)
                res = results[scan_id]
                
                if matched_pair:
                    resp_idx = matched_pair[1]
                    resp_evt = bucket.resp_events[resp_idx]
                    
                    res.is_matched = True
                    res.status = "MATCHED"
                    res.task_name = self.task_mapping.get(resp_evt.filename, "unknown")
                    res.filename = resp_evt.filename
                    
                    # [优化] 使用封装函数
                    res.offset = self._compute_offset(
                        matched_pair, 
                        m_times[m_idx], 
                        r_times[resp_idx]
                    )

                    match_desc = f"Matched: {resp_evt.filename}"
                    if verdict.status == "PASS":
                        res.comments = match_desc
                    else:
                        res.comments = f"{match_desc} (Bucket {verdict.status})"
                else:
                    res.status = "UNMATCHED"
                    res.comments = "No matching log found"

        return results

    def generate_csv_report(self, output_path: str) -> None:
        logger.info(f"Generating Truth Table at: {output_path}")
        
        headers = [
            "Subject", "Date", "Bucket_Status", "Flags",
            "MRI_Scan_ID", "MRI_End_Time", 
            "Log_Filename", "Log_Time", 
            "Offset_Sec", "Match_Type"
        ]
        
        rows = []
        
        for key, bucket in self.buckets.items():
            subj, date_obj = key
            verdict = self.verdicts.get(key)
            result = self.match_results.get(key)
            
            if not result: continue

            for m_idx, m_evt in enumerate(bucket.mri_events):
                matched_pair = next((p for p in result.pairs if p[0] == m_idx), None)
                
                row = {
                    "Subject": subj,
                    "Date": date_obj,
                    "Bucket_Status": verdict.status if verdict else "N/A",
                    "Flags": verdict.flags if verdict else "",
                    "MRI_Scan_ID": m_evt.scan_id,
                    "MRI_End_Time": m_evt.end_timestamp,
                }
                
                if matched_pair:
                    r_idx = matched_pair[1]
                    r_evt = bucket.resp_events[r_idx]
                    
                    # [优化] 使用封装函数
                    offset = self._compute_offset(
                        matched_pair, 
                        m_evt.end_timestamp, 
                        r_evt.timestamp
                    )
                    
                    row.update({
                        "Log_Filename": r_evt.filename,
                        "Log_Time": r_evt.timestamp,
                        "Offset_Sec": round(offset, 4),
                        "Match_Type": "MATCHED"
                    })
                else:
                    row.update({
                        "Log_Filename": "",
                        "Log_Time": "",
                        "Offset_Sec": "",
                        "Match_Type": "UNMATCHED_MRI"
                    })
                rows.append(row)

        try:
            with open(output_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=headers)
                writer.writeheader()
                writer.writerows(rows)
        except Exception as e:
            logger.error(f"Failed to write CSV report: {e}")

    # ... 其他辅助函数 (_load_task_mapping, _to_mri_event, _calculate_duration, _is_audit_target) 保持不变 ...
    def _load_task_mapping(self, csv_path: str) -> None:
        self.task_mapping = {}
        try:
            with open(csv_path, 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    fname = (row.get('FileName') or row.get('filename') or row.get('file_name'))
                    task_val = (row.get('Task') or row.get('task'))
                    if fname and task_val:
                        self.task_mapping[fname.strip()] = task_val.strip()
            logger.info(f"Loaded task mapping for {len(self.task_mapping)} files.")
        except Exception as e:
            logger.error(f"Failed to load task mapping from {csv_path}: {e}")

    def _to_mri_event(self, entry: ConversionEntry) -> Optional[MriEvent]:
        ts = entry.time_meta.canonical_timestamp
        if not ts: return None
        return MriEvent(
            scan_id=entry.id,
            experiment_id=entry.source.identity.subject_id_raw,
            timestamp=ts.timestamp(),
            datetime_obj=ts,
            source_row={},
            duration=self._calculate_duration(entry)
        )

    def _calculate_duration(self, entry: ConversionEntry) -> float:
        try:
            tr = 0.0
            if entry.nifti_pool and entry.nifti_pool.sidecar_content:
                tr = entry.nifti_pool.sidecar_content.get('RepetitionTime', 0.0)
            if tr == 0.0:
                match = self.tr_pattern.search(entry.id)
                if match: tr = float(match.group(1))
            match_v = self.vol_pattern.search(entry.id)
            vols = int(match_v.group(1)) if match_v else 0
            return tr * vols
        except Exception:
            return 0.0

    def _is_audit_target(self, entry: ConversionEntry) -> bool:
        return entry.target.datatype == 'func'