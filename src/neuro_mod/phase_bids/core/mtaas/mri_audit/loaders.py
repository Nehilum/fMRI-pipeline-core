# src/mri_audit/loaders.py
import pandas as pd
import re
from datetime import datetime
from typing import List, Tuple, Dict
from .models import MriEvent, RespEvent

CONFIG = {
    "mri": {
        "col_subj": "Experiment_ID",
        "col_scan": "Scan_ID",
        "col_time": "Machine_Timestamp"
    },
    "resp": {
        "col_subj": "Subject_ScanID",
        "col_file": "Selected_Files"
    }
}

class DataLoader:
    def __init__(self, config: Dict = CONFIG):
        self.cfg = config
        self.ts_pattern = re.compile(r"(\d{14})")
        
        # --- 新增：Scan Duration 解析正则 ---
        # 匹配 _TRxxx_ 和 _xxxv_
        # 示例: ..._TR1_2iso_294v_... -> TR=1, v=294
        # 兼容浮点数 TR (如 TR1.5)
        self.tr_pattern = re.compile(r"_TR([\d\.]+)")
        self.vol_pattern = re.compile(r"_(\d+)v")

    def _calculate_duration(self, scan_id: str) -> float:
        """
        从 Scan_ID 解析时长。
        如果解析失败（如 T1w 结构像通常没有 v 数），返回 0.0。
        """
        try:
            # 提取 TR
            tr_match = self.tr_pattern.search(scan_id)
            # 提取 Volumes
            vol_match = self.vol_pattern.search(scan_id)
            
            if tr_match and vol_match:
                tr = float(tr_match.group(1))
                vols = int(vol_match.group(1))
                return tr * vols
            
            # 如果没有匹配到 (例如 Localizer 或 T1w 可能命名规则不同)
            # 可以在这里记录 warning，或者默认为 0
            return 0.0
        except Exception:
            return 0.0

    def load_mri(self, file_path: str) -> Tuple[List[MriEvent], List[dict]]:
        df = pd.read_excel(file_path)
        valid_events = []
        error_rows = []
        cols = self.cfg['mri']
        
        for _, row in df.iterrows():
            raw_row = row.to_dict()
            subj = row.get(cols['col_subj'])
            scan = row.get(cols['col_scan'])
            time_raw = row.get(cols['col_time'])
            
            if pd.isna(subj) or pd.isna(scan) or pd.isna(time_raw):
                raw_row['error_type'] = 'MISSING_FIELDS'
                error_rows.append(raw_row)
                continue

            dt_obj = None
            try:
                if isinstance(time_raw, datetime):
                    dt_obj = time_raw
                else:
                    dt_obj = pd.to_datetime(time_raw).to_pydatetime()
            except Exception:
                raw_row['error_type'] = 'ERROR_MRI_TIME_PARSE'
                error_rows.append(raw_row)
                continue
            
            # --- 计算 Duration ---
            duration = self._calculate_duration(str(scan))
            
            event = MriEvent(
                scan_id=str(scan),
                experiment_id=str(subj),
                timestamp=dt_obj.timestamp(),
                datetime_obj=dt_obj,
                source_row=raw_row,
                duration=duration # 存入模型
            )
            valid_events.append(event)
            
        return valid_events, error_rows

    # load_resp 保持不变 ...
    def load_resp(self, file_path: str) -> Tuple[List[RespEvent], List[dict]]:
        # ... (与之前代码一致)
        df = pd.read_csv(file_path)
        valid_events = []
        error_rows = []
        cols = self.cfg['resp']
        for _, row in df.iterrows():
            raw_row = row.to_dict()
            subj = row.get(cols['col_subj'])
            fname = row.get(cols['col_file'])
            if pd.isna(subj) or pd.isna(fname):
                raw_row['error_type'] = 'MISSING_FIELDS'
                error_rows.append(raw_row)
                continue
            match = self.ts_pattern.search(str(fname))
            if not match:
                raw_row['error_type'] = 'ERROR_RESP_TIME_PARSE'
                error_rows.append(raw_row)
                continue
            ts_str = match.group(1)
            try:
                dt_obj = datetime.strptime(ts_str, "%Y%m%d%H%M%S")
            except ValueError:
                raw_row['error_type'] = 'ERROR_RESP_TIME_FORMAT'
                error_rows.append(raw_row)
                continue
            event = RespEvent(
                filename=str(fname),
                subject_id=str(subj),
                timestamp=dt_obj.timestamp(),
                datetime_obj=dt_obj,
                source_row=raw_row
            )
            valid_events.append(event)
        return valid_events, error_rows