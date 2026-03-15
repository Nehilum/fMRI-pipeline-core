# src/temporal_matcher/metrics.py
import numpy as np
from typing import List, Tuple
from .models import MatchCandidate

def calculate_metrics(
    source_times: List[float], 
    target_times: List[float], 
    pairs: List[Tuple[int, int]]
) -> MatchCandidate:
    """
    根据给定的匹配对，计算 E_gap, E_res 等指标。
    """
    if not pairs:
        return MatchCandidate([], np.inf, np.inf, np.inf, np.inf, np.inf, 0)

    # 提取配对的时间点
    # m_t: MRI times, r_t: Response times
    m_t = np.array([source_times[i] for i, j in pairs])
    r_t = np.array([target_times[j] for i, j in pairs])

    # 1. 基础 Offset 计算 (M - R)
    offsets = m_t - r_t
    
    # 2. 绝对时间差 (Tie-breaker M4)
    # 绝对值的中位数，用于最后判断哪个解更接近“当下”
    abs_diffs = np.abs(offsets)
    abs_med = np.median(abs_diffs)

    # 3. 稳定性指标 (M3)
    # Global Offset 假设为 offsets 的中位数
    global_offset = np.median(offsets)
    residuals = np.abs(offsets - global_offset)
    res_med = np.median(residuals)
    res_max = np.max(residuals)

    # 4. 间隔一致性指标 (M2 - 核心)
    # 只有当匹配对数量 >= 2 时才能计算间隔
    if len(pairs) < 2:
        # 只有一个点，无法计算间隔，设为 0 (完美) 或特定值
        # 单点匹配主要靠 Offset 稳定性判断
        gap_med = 0.0
        gap_max = 0.0
    else:
        # np.diff 计算相邻元素的差: [t2-t1, t3-t2, ...]
        m_intervals = np.diff(m_t)
        r_intervals = np.diff(r_t)
        
        # 间隔误差: |(Tm_k+1 - Tm_k) - (Tr_k+1 - Tr_k)|
        gap_errors = np.abs(m_intervals - r_intervals)
        
        gap_med = np.median(gap_errors)
        gap_max = np.max(gap_errors)

    return MatchCandidate(
        matched_indices=pairs,
        gap_med=gap_med,
        gap_max=gap_max,
        res_med=res_med,
        res_max=res_max,
        abs_med=abs_med,
        match_count=len(pairs)
    )