# src/mri_audit/models.py
from dataclasses import dataclass, field
from typing import List, Dict, Any
from datetime import datetime, date

@dataclass
class MriEvent:
    """代表一行 MRI 扫描记录"""
    scan_id: str
    experiment_id: str
    timestamp: float     # 原始 Machine Start Time
    datetime_obj: datetime
    source_row: Dict[str, Any]
    
    # --- 新增字段 ---
    duration: float = 0.0 # 扫描持续时间 (秒)
    
    @property
    def date_key(self) -> date:
        return self.datetime_obj.date()

    @property
    def end_timestamp(self) -> float:
        """
        用于对齐的时间戳：Scan End Time
        如果无法解析 duration，则退化为 Start Time (虽然不准，但在 try-catch 范围内)
        """
        return self.timestamp + self.duration

# RespEvent 和 AuditBucket 保持不变 ...
@dataclass
class RespEvent:
    filename: str
    subject_id: str
    timestamp: float # File creation time (End time)
    datetime_obj: datetime
    source_row: Dict[str, Any]
    
    @property
    def date_key(self) -> date:
        return self.datetime_obj.date()

@dataclass
class AuditBucket:
    subject_key: str
    date_key: date
    mri_events: List[MriEvent] = field(default_factory=list)
    resp_events: List[RespEvent] = field(default_factory=list)

    def sort_events(self):
        self.mri_events.sort(key=lambda x: x.timestamp)
        self.resp_events.sort(key=lambda x: x.timestamp)