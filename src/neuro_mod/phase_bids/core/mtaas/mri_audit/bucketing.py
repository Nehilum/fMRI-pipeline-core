# src/mri_audit/bucketing.py
from typing import List, Dict, Tuple
from collections import defaultdict
from datetime import date
from .models import MriEvent, RespEvent, AuditBucket

def create_buckets(mri_events: List[MriEvent], resp_events: List[RespEvent]) -> Dict[Tuple[str, date], AuditBucket]:
    """
    将扁平的事件列表聚合为 (Subject, Date) -> Bucket。
    实现 P1, P2 规则。
    """
    buckets: Dict[Tuple[str, date], AuditBucket] = {}
    
    # 1. 填入 MRI
    for m in mri_events:
        key = (m.experiment_id, m.date_key)
        if key not in buckets:
            buckets[key] = AuditBucket(subject_key=key[0], date_key=key[1])
        buckets[key].mri_events.append(m)
        
    # 2. 填入 Response
    for r in resp_events:
        key = (r.subject_id, r.date_key)
        if key not in buckets:
            buckets[key] = AuditBucket(subject_key=key[0], date_key=key[1])
        buckets[key].resp_events.append(r)
        
    # 3. 排序与清理
    # (确保进入算法前是有序的)
    for b in buckets.values():
        b.sort_events()
        
    return buckets